// Servidor HTTP del portal. Sin dependencias externas.
import http from 'node:http';
import crypto from 'node:crypto';
import { config } from './config.js';
import { db, auditar } from './db.js';
import { ingresar, firmarCookie, leerCookieFirmada, usuarioDeSesion, cerrarSesion, identidades } from './auth.js';
import { appPorClave, crearTokenSso, urlSso, verificarCredenciales, estadoConector } from './conector.js';
import { recolectarTodo, programarRecoleccion, resumenTablero, datosCompletos } from './recolector.js';
import { calcularIndicadores } from './indicadores.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ_ESTATICA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'static');
const TIPOS = { '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff2': 'font/woff2' };
function servirEstatico(ruta, res) {
  const rel = path.normalize(decodeURIComponent(ruta.replace(/^\/static\//, ''))).replace(/^(\.\.[\/\\])+/, '');
  const archivo = path.join(RAIZ_ESTATICA, rel);
  if (!archivo.startsWith(RAIZ_ESTATICA) || !fs.existsSync(archivo) || fs.statSync(archivo).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': TIPOS[path.extname(archivo)] || 'application/octet-stream', 'Cache-Control': 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff' });
  fs.createReadStream(archivo).pipe(res);
}
import * as V from './vistas.js';

const COOKIE = 'onia_sesion';
const CSRF = 'onia_csrf';

function cookies(req) {
  const out = {};
  for (const p of (req.headers.cookie || '').split(';')) { const i = p.indexOf('='); if (i > 0) out[p.slice(0, i).trim()] = decodeURIComponent(p.slice(i + 1).trim()); }
  return out;
}
function setCookie(res, nombre, valor, { maxAge = null, httpOnly = true } = {}) {
  const partes = [`${nombre}=${encodeURIComponent(valor)}`, 'Path=/', 'SameSite=Lax'];
  if (httpOnly) partes.push('HttpOnly');
  if (config.urlPublica.startsWith('https://')) partes.push('Secure');
  if (maxAge !== null) partes.push(`Max-Age=${maxAge}`);
  res.appendHeader('Set-Cookie', partes.join('; '));
}
function html(res, cuerpo, estado = 200) {
  const cab = { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin',
    'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; frame-ancestors 'none'; form-action 'self'",
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()' };
  if (config.urlPublica.startsWith('https://')) cab['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains';
  res.writeHead(estado, cab);
  res.end(cuerpo);
}
function redirigir(res, a) { res.writeHead(303, { Location: a }); res.end(); }
function leerCuerpo(req) {
  return new Promise((ok, fallo) => {
    let d = ''; req.on('data', (c) => { d += c; if (d.length > 64 * 1024) { fallo(new Error('Cuerpo demasiado grande')); req.destroy(); } });
    req.on('end', () => ok(Object.fromEntries(new URLSearchParams(d)))); req.on('error', fallo);
  });
}
function ipDe(req) { return (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || req.socket.remoteAddress || ''; }

// Token anti falsificacion ligado a la sesion.
function csrfDe(sesionId) { return crypto.createHmac('sha256', config.claveSesion).update('csrf:' + sesionId).digest('base64url').slice(0, 32); }
function csrfValido(usuario, cuerpo) { return usuario && cuerpo._csrf && cuerpo._csrf === csrfDe(usuario.sesionId); }
function conCsrf(htmlStr, usuario) { return usuario ? htmlStr.replace(/(<form\b[^>]*\bmethod="post"[^>]*>)/gi, `$1<input type="hidden" name="_csrf" value="${csrfDe(usuario.sesionId)}">`) : htmlStr; }

const servidor = http.createServer(async (req, res) => {
  const url = new URL(req.url, config.urlPublica);
  const ruta = url.pathname.replace(/\/+$/, '') || '/';
  const ip = ipDe(req);
  const ck = cookies(req);
  const usuario = usuarioDeSesion(leerCookieFirmada(ck[COOKIE]));
  const render = (h, estado) => html(res, conCsrf(h, usuario), estado);

  try {
    if (ruta.startsWith('/static/')) return servirEstatico(ruta, res);
    if (ruta === '/salud') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ ok: true, apps: config.apps.map((a) => a.clave) })); }

    if (ruta === '/') return render(V.vistaInicio({ usuario, apps: config.apps, indicadores: calcularIndicadores(datosCompletos()), ids: usuario ? identidades(usuario.id) : [] }));
    if (ruta === '/acerca') return render(V.vistaAcerca({ usuario, apps: config.apps, ids: usuario ? identidades(usuario.id) : [] }));

    if (ruta === '/ingresar' && req.method === 'GET') {
      if (usuario) return redirigir(res, '/aplicativos');
      return render(V.vistaIngreso({ apps: config.apps }));
    }
    if (ruta === '/ingresar' && req.method === 'POST') {
      const c = await leerCuerpo(req);
      const r = await ingresar({ usuario: c.usuario, clave: c.clave, ip, agente: req.headers['user-agent'] });
      if (!r.ok) return render(V.vistaIngreso({ apps: config.apps, error: r.error, usuarioPrevio: c.usuario }), 401);
      setCookie(res, COOKIE, firmarCookie(r.sesion.id), { maxAge: config.horasSesion * 3600 });
      const destino = url.searchParams.get('siguiente');
      const seguro = destino && destino.startsWith('/') && !destino.startsWith('//') && !destino.includes('\\');
      return redirigir(res, seguro ? destino : '/aplicativos');
    }
    if (ruta === '/salir' && req.method === 'POST') {
      const c = await leerCuerpo(req);
      if (usuario && !csrfValido(usuario, c)) return redirigir(res, '/aplicativos');
      if (usuario) { cerrarSesion(usuario.sesionId); auditar('salida', { usuarioId: usuario.id, ip }); }
      setCookie(res, COOKIE, '', { maxAge: 0 });
      return redirigir(res, '/ingresar');
    }

    if (!usuario) return redirigir(res, '/ingresar?siguiente=' + encodeURIComponent(ruta));

    if (ruta === '/escritorio') return redirigir(res, '/aplicativos');
    if (ruta === '/aplicativos') return render(V.vistaAplicativos({ usuario, apps: config.apps, ids: identidades(usuario.id), resumen: resumenTablero() }));
    if (ruta === '/tablero') return render(V.vistaTablero({ usuario, apps: config.apps, ids: identidades(usuario.id), resumen: resumenTablero(), indicadores: calcularIndicadores(datosCompletos()) }));
    if (ruta === '/cuenta') {
      const sesiones = db.prepare('SELECT * FROM sesiones WHERE usuario_id = ? ORDER BY creada_en DESC').all(usuario.id);
      return render(V.vistaCuenta({ usuario, ids: identidades(usuario.id), apps: config.apps, sesiones }));
    }

    // Abrir una aplicacion con la sesion ya iniciada.
    let m = /^\/abrir\/([a-z0-9_-]+)$/.exec(ruta);
    if (m) {
      const app = appPorClave(m[1]);
      if (!app) return render(V.vistaMensaje({ usuario, apps: config.apps, titulo: 'Aplicación no encontrada', texto: 'La aplicación solicitada no está configurada en el portal.' }), 404);
      const id = identidades(usuario.id).find((i) => i.app === app.clave);
      if (!id) return redirigir(res, `/vincular/${app.clave}`);
      const jti = crypto.randomBytes(16).toString('hex');
      db.prepare('INSERT INTO tokens_sso (jti, app, usuario_id) VALUES (?, ?, ?)').run(jti, app.clave, usuario.id);
      db.prepare("DELETE FROM tokens_sso WHERE emitido_en < datetime('now', '-1 day')").run();
      auditar('sso_emitido', { usuarioId: usuario.id, app: app.clave, ip });
      return redirigir(res, urlSso(app, crearTokenSso(app, { correo: usuario.correo, idExterno: id.id_externo, usuarioExterno: id.usuario_externo, jti })));
    }

    // Vincular una cuenta de otra aplicacion.
    m = /^\/vincular\/([a-z0-9_-]+)$/.exec(ruta);
    if (m) {
      const app = appPorClave(m[1]);
      if (!app) return redirigir(res, '/cuenta');
      if (req.method === 'GET') return render(V.vistaVincular({ usuario, app, apps: config.apps, ids: identidades(usuario.id) }));
      const c = await leerCuerpo(req);
      if (!csrfValido(usuario, c)) return render(V.vistaVincular({ usuario, app, apps: config.apps, ids: identidades(usuario.id), error: 'La sesión cambió. Intente de nuevo.' }), 403);
      let r;
      try { r = await verificarCredenciales(app, String(c.usuario || '').trim(), c.clave || ''); } catch (e) { return render(V.vistaVincular({ usuario, app, apps: config.apps, ids: identidades(usuario.id), error: 'No fue posible contactar la aplicación. ' + e.message }), 502); }
      if (!r.ok) { auditar('vinculo_fallido', { usuarioId: usuario.id, app: app.clave, ip }); return render(V.vistaVincular({ usuario, app, apps: config.apps, ids: identidades(usuario.id), error: 'Usuario o clave no válidos en ' + app.nombre + '.' }), 401); }
      db.prepare(`INSERT INTO identidades (usuario_id, app, id_externo, usuario_externo, rol_externo) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT(app, id_externo) DO UPDATE SET usuario_id = excluded.usuario_id, usuario_externo = excluded.usuario_externo, rol_externo = excluded.rol_externo, verificado_en = datetime('now')`)
        .run(usuario.id, app.clave, String(r.id), r.usuario || c.usuario, r.rol || null);
      auditar('vinculo', { usuarioId: usuario.id, app: app.clave, ip });
      return redirigir(res, '/cuenta');
    }

    // Administracion.
    if (ruta.startsWith('/admin')) {
      if (usuario.rol !== 'administrador') return render(V.vistaMensaje({ usuario, apps: config.apps, titulo: 'Sin permiso', texto: 'Esta sección es solo para administradores del portal.' }), 403);
      let mensaje = '';
      if (ruta === '/admin/recolectar' && req.method === 'POST') {
        const c = await leerCuerpo(req);
        if (!csrfValido(usuario, c)) return redirigir(res, '/admin');
        const r = await recolectarTodo();
        auditar('recoleccion_manual', { usuarioId: usuario.id, detalle: JSON.stringify(r), ip });
        mensaje = 'Recolección ejecutada. ' + Object.entries(r).map(([a, xs]) => `${a}: ${xs.map((x) => `${x.conjunto} ${x.estado}${x.filas != null ? ' (' + x.filas + ')' : ''}`).join(', ')}`).join(' · ');
      }
      const estados = await Promise.all(config.apps.map(async (app) => { try { const e = await estadoConector(app); return { app, ok: true, ...e }; } catch (e) { return { app, ok: false, error: e.message }; } }));
      const usuarios = db.prepare('SELECT u.*, (SELECT COUNT(*) FROM identidades i WHERE i.usuario_id = u.id) AS vinculos FROM usuarios u ORDER BY ultimo_ingreso DESC LIMIT 50').all();
      const auditoria = db.prepare('SELECT * FROM auditoria ORDER BY id DESC LIMIT 40').all();
      return render(V.vistaAdmin({ usuario, apps: config.apps, ids: identidades(usuario.id), estados, usuarios, auditoria, mensaje }));
    }

    return render(V.vistaMensaje({ usuario, apps: config.apps, titulo: 'Página no encontrada', texto: 'La dirección solicitada no existe en el portal.' }), 404);
  } catch (e) {
    console.error(e);
    auditar('error', { detalle: e.message, ip });
    return html(res, V.vistaMensaje({ usuario, apps: config.apps, titulo: 'Ocurrió un error', texto: 'El portal no pudo completar la acción. Intente de nuevo o escriba a soporte.' }), 500);
  }
});

servidor.listen(config.puerto, () => {
  console.log(`Portal del Observatorio en ${config.urlPublica} (puerto ${config.puerto}). Aplicaciones: ${config.apps.map((a) => a.clave).join(', ') || 'ninguna configurada'}.`);
  programarRecoleccion();
});
