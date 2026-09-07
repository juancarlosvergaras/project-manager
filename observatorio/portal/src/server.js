// Servidor HTTP del portal. Sin dependencias externas.
import http from 'node:http';
import crypto from 'node:crypto';
import { config } from './config.js';
import { db, auditar } from './db.js';
import { ingresar, firmarCookie, leerCookieFirmada, usuarioDeSesion, cerrarSesion, identidades } from './auth.js';
import { appPorClave, crearTokenSso, urlSso, verificarCredenciales, estadoConector } from './conector.js';
import { recolectarTodo, programarRecoleccion, resumenTablero } from './recolector.js';
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
    'Content-Security-Policy': "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'none'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
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
function conCsrf(htmlStr, usuario) { return usuario ? htmlStr.replace(/<form method="post"/g, `<form method="post"`).replace(/(<form method="post"[^>]*>)/g, `$1<input type="hidden" name="_csrf" value="${csrfDe(usuario.sesionId)}">`) : htmlStr; }

const servidor = http.createServer(async (req, res) => {
  const url = new URL(req.url, config.urlPublica);
  const ruta = url.pathname.replace(/\/+$/, '') || '/';
  const ip = ipDe(req);
  const ck = cookies(req);
  const usuario = usuarioDeSesion(leerCookieFirmada(ck[COOKIE]));
  const render = (h, estado) => html(res, conCsrf(h, usuario), estado);

  try {
    if (ruta === '/salud') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ ok: true, apps: config.apps.map((a) => a.clave) })); }

    if (ruta === '/' ) return redirigir(res, usuario ? '/escritorio' : '/ingresar');

    if (ruta === '/ingresar' && req.method === 'GET') {
      if (usuario) return redirigir(res, '/escritorio');
      return render(V.vistaIngreso({ apps: config.apps }));
    }
    if (ruta === '/ingresar' && req.method === 'POST') {
      const c = await leerCuerpo(req);
      const r = await ingresar({ usuario: c.usuario, clave: c.clave, ip, agente: req.headers['user-agent'] });
      if (!r.ok) return render(V.vistaIngreso({ apps: config.apps, error: r.error, usuarioPrevio: c.usuario }), 401);
      setCookie(res, COOKIE, firmarCookie(r.sesion.id), { maxAge: config.horasSesion * 3600 });
      const destino = url.searchParams.get('siguiente');
      const seguro = destino && destino.startsWith('/') && !destino.startsWith('//') && !destino.includes('\\');
      return redirigir(res, seguro ? destino : '/escritorio');
    }
    if (ruta === '/salir' && req.method === 'POST') {
      const c = await leerCuerpo(req);
      if (usuario && !csrfValido(usuario, c)) return redirigir(res, '/escritorio');
      if (usuario) { cerrarSesion(usuario.sesionId); auditar('salida', { usuarioId: usuario.id, ip }); }
      setCookie(res, COOKIE, '', { maxAge: 0 });
      return redirigir(res, '/ingresar');
    }

    if (!usuario) return redirigir(res, '/ingresar?siguiente=' + encodeURIComponent(ruta));

    if (ruta === '/escritorio') return render(V.vistaEscritorio({ usuario, apps: config.apps, ids: identidades(usuario.id), resumen: resumenTablero() }));
    if (ruta === '/tablero') return render(V.vistaTablero({ usuario, resumen: resumenTablero() }));
    if (ruta === '/cuenta') {
      const sesiones = db.prepare('SELECT * FROM sesiones WHERE usuario_id = ? ORDER BY creada_en DESC').all(usuario.id);
      return render(V.vistaCuenta({ usuario, ids: identidades(usuario.id), apps: config.apps, sesiones }));
    }

    // Abrir una aplicacion con la sesion ya iniciada.
    let m = /^\/abrir\/([a-z0-9_-]+)$/.exec(ruta);
    if (m) {
      const app = appPorClave(m[1]);
      if (!app) return render(V.vistaMensaje({ usuario, titulo: 'Aplicación no encontrada', texto: 'La aplicación solicitada no está configurada en el portal.' }), 404);
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
      if (req.method === 'GET') return render(V.vistaVincular({ usuario, app }));
      const c = await leerCuerpo(req);
      if (!csrfValido(usuario, c)) return render(V.vistaVincular({ usuario, app, error: 'La sesión cambió. Intente de nuevo.' }), 403);
      let r;
      try { r = await verificarCredenciales(app, String(c.usuario || '').trim(), c.clave || ''); } catch (e) { return render(V.vistaVincular({ usuario, app, error: 'No fue posible contactar la aplicación. ' + e.message }), 502); }
      if (!r.ok) { auditar('vinculo_fallido', { usuarioId: usuario.id, app: app.clave, ip }); return render(V.vistaVincular({ usuario, app, error: 'Usuario o clave no válidos en ' + app.nombre + '.' }), 401); }
      db.prepare(`INSERT INTO identidades (usuario_id, app, id_externo, usuario_externo, rol_externo) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT(app, id_externo) DO UPDATE SET usuario_id = excluded.usuario_id, usuario_externo = excluded.usuario_externo, rol_externo = excluded.rol_externo, verificado_en = datetime('now')`)
        .run(usuario.id, app.clave, String(r.id), r.usuario || c.usuario, r.rol || null);
      auditar('vinculo', { usuarioId: usuario.id, app: app.clave, ip });
      return redirigir(res, '/cuenta');
    }

    // Administracion.
    if (ruta.startsWith('/admin')) {
      if (usuario.rol !== 'administrador') return render(V.vistaMensaje({ usuario, titulo: 'Sin permiso', texto: 'Esta sección es solo para administradores del portal.' }), 403);
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
      return render(V.vistaAdmin({ usuario, apps: config.apps, estados, usuarios, auditoria, mensaje }));
    }

    return render(V.vistaMensaje({ usuario, titulo: 'Página no encontrada', texto: 'La dirección solicitada no existe en el portal.' }), 404);
  } catch (e) {
    console.error(e);
    auditar('error', { detalle: e.message, ip });
    return html(res, V.vistaMensaje({ usuario, titulo: 'Ocurrió un error', texto: 'El portal no pudo completar la acción. Intente de nuevo o escriba a soporte.' }), 500);
  }
});

servidor.listen(config.puerto, () => {
  console.log(`Portal del Observatorio en ${config.urlPublica} (puerto ${config.puerto}). Aplicaciones: ${config.apps.map((a) => a.clave).join(', ') || 'ninguna configurada'}.`);
  programarRecoleccion();
});
