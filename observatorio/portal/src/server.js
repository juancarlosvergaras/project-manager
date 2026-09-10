// Servidor HTTP del portal. Sin dependencias externas.
import http from 'node:http';
import crypto from 'node:crypto';
import { config } from './config.js';
import { db, auditar } from './db.js';
import { ingresar, firmarCookie, leerCookieFirmada, usuarioDeSesion, cerrarSesion, identidades } from './auth.js';
import { appPorClave, crearTokenSso, urlSso, verificarCredenciales, estadoConector } from './conector.js';
import { recolectarTodo, programarRecoleccion, resumenTablero, datosCompletos } from './recolector.js';
import { calcularIndicadores } from './indicadores.js';
import * as C from './cuestionarios.js';
import * as K from './campanias.js';
import * as VC from './vistas_cuestionarios.js';
import { correoConfigurado } from './correo.js';
import { leerHoja } from './hoja.js';
import { svgQr } from './qr.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const RAIZ_ESTATICA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'static');
const TIPOS = { '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.json': 'application/json; charset=utf-8' };
function servirEstatico(ruta, res) {
  const rel = path.normalize(decodeURIComponent(ruta.replace(/^\/static\//, ''))).replace(/^(\.\.[\/\\])+/, '');
  const archivo = path.join(RAIZ_ESTATICA, rel);
  if (!archivo.startsWith(RAIZ_ESTATICA) || !fs.existsSync(archivo) || fs.statSync(archivo).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': TIPOS[path.extname(archivo)] || 'application/octet-stream', 'Cache-Control': 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff' });
  fs.createReadStream(archivo).pipe(res);
}
import * as V from './vistas.js';

const COOKIE = 'onia_sesion';

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
const CSP_PORTAL = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; frame-ancestors 'none'; form-action 'self'";
// La página pública de los cuestionarios carga sus tipografías institucionales desde fonts.bunny.net.
const CSP_CUESTIONARIO = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.bunny.net; script-src 'self'; font-src 'self' https://fonts.bunny.net; connect-src 'self'; frame-ancestors 'none'; form-action 'self'";
function html(res, cuerpo, estado = 200, csp = CSP_PORTAL) {
  const cab = { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin',
    'Content-Security-Policy': csp, 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()' };
  if (config.urlPublica.startsWith('https://')) cab['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains';
  res.writeHead(estado, cab);
  res.end(cuerpo);
  return true; // las rutas devuelven algo distinto de undefined cuando ya respondieron
}
function json(res, obj, estado = 200) { res.writeHead(estado, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(obj)); return true; }
function redirigir(res, a) { res.writeHead(303, { Location: a }); res.end(); return true; }
function svg(res, contenido, nombre, descargar = false) {
  res.writeHead(200, { 'Content-Type': 'image/svg+xml; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...(descargar ? { 'Content-Disposition': `attachment; filename="${nombre}"` } : {}) });
  res.end(contenido);
  return true;
}
function leerCrudo(req, limite) {
  return new Promise((ok, fallo) => {
    const trozos = []; let total = 0;
    req.on('data', (c) => { total += c.length; if (total > limite) { fallo(new Error('Cuerpo demasiado grande')); req.destroy(); return; } trozos.push(c); });
    req.on('end', () => ok(Buffer.concat(trozos))); req.on('error', fallo);
  });
}
// Convierte pares nombre=valor en un objeto; los nombres terminados en [] se agrupan en arreglos.
function agrupar(pares) {
  const out = {};
  for (const [k, v] of pares) {
    if (k.endsWith('[]')) { const n = k.slice(0, -2); (out[n] = out[n] || []).push(v); }
    else if (out[k] === undefined) out[k] = v;
    else if (Array.isArray(out[k])) out[k].push(v);
    else out[k] = [out[k], v];
  }
  return out;
}
async function leerCuerpo(req) {
  const tipo = String(req.headers['content-type'] || '');
  const crudo = await leerCrudo(req, tipo.startsWith('application/json') ? 4 * 1024 * 1024 : 256 * 1024);
  if (tipo.startsWith('application/json')) { try { return JSON.parse(crudo.toString('utf8') || '{}'); } catch { return {}; } }
  return agrupar([...new URLSearchParams(crudo.toString('utf8'))]);
}
// Lectura de un envío de cuestionario: multipart/form-data (con archivos) o formulario clásico.
async function leerEnvio(req) {
  const tipo = String(req.headers['content-type'] || '');
  const crudo = await leerCrudo(req, 24 * 1024 * 1024);
  const m = /boundary=("?)([^";]+)\1/.exec(tipo);
  if (!tipo.startsWith('multipart/form-data') || !m) return { campos: agrupar([...new URLSearchParams(crudo.toString('utf8'))]), archivos: {} };
  const limite = Buffer.from('--' + m[2]);
  const pares = []; const archivos = {};
  let pos = crudo.indexOf(limite);
  while (pos >= 0) {
    const inicio = pos + limite.length;
    if (crudo.slice(inicio, inicio + 2).toString() === '--') break;
    const fin = crudo.indexOf(limite, inicio);
    if (fin < 0) break;
    const parte = crudo.slice(inicio + 2, fin - 2); // salta CRLF inicial y final
    const sep = parte.indexOf('\r\n\r\n');
    if (sep >= 0) {
      const cabeceras = parte.slice(0, sep).toString('utf8');
      const cuerpo = parte.slice(sep + 4);
      const nombre = (/name="([^"]*)"/.exec(cabeceras) || [])[1];
      const archivo = (/filename="([^"]*)"/.exec(cabeceras) || [])[1];
      if (nombre != null) {
        if (archivo != null) { if (archivo && cuerpo.length) archivos[nombre] = { nombre: archivo, tipo: (/Content-Type:\s*([^\r\n]+)/i.exec(cabeceras) || [, 'application/octet-stream'])[1].trim(), datos: cuerpo }; }
        else pares.push([nombre, cuerpo.toString('utf8')]);
      }
    }
    pos = fin;
  }
  return { campos: agrupar(pares), archivos };
}
function ipDe(req) { return (req.headers['x-forwarded-for'] || '').split(',')[0].trim() || req.socket.remoteAddress || ''; }

// Token anti falsificacion ligado a la sesion.
function csrfDe(sesionId) { return crypto.createHmac('sha256', config.claveSesion).update('csrf:' + sesionId).digest('base64url').slice(0, 32); }
function csrfValido(usuario, cuerpo) { return usuario && cuerpo._csrf && cuerpo._csrf === csrfDe(usuario.sesionId); }
function conCsrf(htmlStr, usuario) { return usuario ? htmlStr.replace(/(<form\b[^>]*\bmethod="post"[^>]*>)/gi, `$1<input type="hidden" name="_csrf" value="${csrfDe(usuario.sesionId)}">`) : htmlStr; }
const comun = (usuario) => ({ usuario, apps: config.apps, ids: usuario ? identidades(usuario.id) : [] });

const servidor = http.createServer(async (req, res) => {
  const url = new URL(req.url, config.urlPublica);
  const ruta = url.pathname.replace(/\/+$/, '') || '/';
  const ip = ipDe(req);
  const ck = cookies(req);
  const usuario = usuarioDeSesion(leerCookieFirmada(ck[COOKIE]));
  const render = (h, estado) => html(res, conCsrf(h, usuario), estado);
  const esAdmin = usuario && usuario.rol === 'administrador';
  let m;

  try {
    if (ruta.startsWith('/static/')) return servirEstatico(ruta, res);
    if (ruta === '/salud') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ ok: true, apps: config.apps.map((a) => a.clave) })); }

    // Sin sesión, el portal muestra solo la página del Observatorio con las encuestas habilitadas; el resto es de administradores.
    if (ruta === '/' && !usuario) return render(V.vistaAcerca({ ...comun(usuario), encuestas: C.encuestasHabilitadas() }));
    if (ruta === '/') return render(V.vistaInicio({ ...comun(usuario), indicadores: calcularIndicadores(datosCompletos()), cuestionarios: C.resumenParaTablero(), encuestas: C.encuestasHabilitadas() }));
    if (ruta === '/acerca') return render(V.vistaAcerca({ ...comun(usuario), encuestas: C.encuestasHabilitadas() }));

    // ---------------------------------------------------------------- cuestionarios: páginas públicas
    m = /^\/c\/([a-z0-9-]+)(?:\/t\/([A-Za-z0-9_-]+))?$/.exec(ruta);
    if (m && req.method === 'GET') {
      const c = C.cuestionarioPorClave(m[1]);
      const vistaPrevia = url.searchParams.get('vista_previa') === '1' && esAdmin;
      if (!c) return html(res, V.vistaMensaje({ ...comun(usuario), titulo: 'Cuestionario no encontrado', texto: 'La dirección no corresponde a ningún cuestionario del Observatorio.' }), 404);
      if (c.estado !== 'publicado' && !vistaPrevia) return html(res, V.vistaMensaje({ ...comun(usuario), titulo: 'Cuestionario no disponible', texto: c.estado === 'cerrado' ? 'Este cuestionario ya cerró y no recibe más respuestas. Gracias por su interés.' : 'Este cuestionario todavía no está publicado.' }), 404);
      const valores = {}; let token = '';
      if (m[2]) {
        const dest = K.destinatarioPorToken(m[2]);
        if (!dest || dest.campania.cuestionario_id !== c.id) return html(res, V.vistaMensaje({ ...comun(usuario), titulo: 'Enlace no válido', texto: 'El enlace personal no corresponde a este cuestionario. Puede responderlo con el enlace público.', enlace: `/c/${c.clave}`, textoEnlace: 'Abrir el cuestionario' }), 404);
        if (dest.estado === 'respondido' && !vistaPrevia) return html(res, V.vistaMensaje({ ...comun(usuario), titulo: 'Respuesta ya registrada', texto: 'Este enlace personal ya se utilizó para responder el cuestionario. Gracias por su participación.' }));
        const idn = c.definicion.identificacion || {};
        if (idn.correo) valores[idn.correo] = dest.correo;
        if (idn.nombre && dest.nombre) valores[idn.nombre] = dest.nombre;
        if (idn.entidad && dest.entidad) valores[idn.entidad] = dest.entidad;
        token = m[2];
      }
      return html(res, C.renderPublico({ definicion: c.definicion, clave: c.clave, token, valores, vistaPrevia }), 200, CSP_CUESTIONARIO);
    }
    // Código QR del enlace público (se genera con la dirección pública vigente, así que sigue a cualquier cambio de dominio).
    m = /^\/c\/([a-z0-9-]+)\/qr\.svg$/.exec(ruta);
    if (m && req.method === 'GET') {
      const c = C.cuestionarioPorClave(m[1]);
      if (!c || (c.estado !== 'publicado' && !esAdmin)) { res.writeHead(404); res.end(); return true; }
      return svg(res, svgQr(`${config.urlPublica}/c/${c.clave}`, { pie: url.searchParams.get('pie') === '0' ? '' : 'Escanee para responder' }), `qr-${c.clave}.svg`, url.searchParams.get('descargar') === '1');
    }
    m = /^\/c\/([a-z0-9-]+)\/existe$/.exec(ruta);
    if (m && req.method === 'GET') {
      const c = C.cuestionarioPorClave(m[1]);
      if (!c) return json(res, { existe: false }, 404);
      const existe = C.existeDuplicado(c, url.searchParams.get('campo') || '', url.searchParams.get('valor') || '');
      return json(res, { existe, mensaje: existe ? C.normalizar(c.definicion).duplicados.mensaje : '' });
    }
    m = /^\/c\/([a-z0-9-]+)\/enviar$/.exec(ruta);
    if (m && req.method === 'POST') {
      const c = C.cuestionarioPorClave(m[1]);
      if (!c) return json(res, { ok: false, mensaje: 'El cuestionario no existe.' }, 404);
      const vistaPrevia = url.searchParams.get('vista_previa') === '1' && esAdmin;
      if (c.estado !== 'publicado' && !vistaPrevia) return json(res, { ok: false, titulo: 'Cuestionario cerrado', mensaje: 'Este cuestionario no recibe respuestas en este momento.' }, 403);
      let envio;
      try { envio = await leerEnvio(req); } catch (e) { return json(res, { ok: false, mensaje: 'El envío es demasiado grande. Reduzca el tamaño de los archivos adjuntos.' }, 413); }
      const d = C.normalizar(c.definicion);
      const r = C.validarEnvio(d, envio.campos, envio.archivos);
      if (!r.ok) return json(res, { ok: false, titulo: 'Revise las respuestas', errores: r.errores }, 400);
      let dest = null;
      const token = String(envio.campos._token || '');
      if (token && !vistaPrevia) {
        dest = K.destinatarioPorToken(token);
        if (!dest || dest.campania.cuestionario_id !== c.id) dest = null;
        else if (dest.estado === 'respondido') return json(res, { ok: false, titulo: 'Respuesta ya registrada', mensaje: 'Este enlace personal ya se utilizó para responder.' }, 409);
      }
      if (!vistaPrevia) for (const campo of d.duplicados.campos) if (C.existeDuplicado(c, campo, r.datos[campo])) return json(res, { ok: false, titulo: 'Respuesta ya registrada', mensaje: d.duplicados.mensaje }, 409);
      if (vistaPrevia) return json(res, { ok: true, vistaPrevia: true, puntajes: C.calcularPuntajes(d, r.datos) });
      const id = C.guardarRespuesta({ cuestionario: c, datos: r.datos, archivos: envio.archivos, campaniaId: dest ? dest.campania_id : null, destinatarioId: dest ? dest.id : null, ip, agente: req.headers['user-agent'] });
      return json(res, { ok: true, id });
    }

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
    if (ruta === '/aplicativos') return render(V.vistaAplicativos({ ...comun(usuario), resumen: resumenTablero(), cuestionariosPublicados: C.listarCuestionarios().filter((c) => c.estado === 'publicado').length }));
    if (ruta === '/tablero') { const periodo = url.searchParams.get('periodo') || ''; return render(V.vistaTablero({ ...comun(usuario), resumen: resumenTablero(), indicadores: calcularIndicadores(datosCompletos()), cuestionarios: C.resumenParaTablero(periodo || null), periodo, periodos: C.periodosDisponibles() })); }
    if (ruta === '/cuenta') {
      const sesiones = db.prepare('SELECT * FROM sesiones WHERE usuario_id = ? ORDER BY creada_en DESC').all(usuario.id);
      return render(V.vistaCuenta({ ...comun(usuario), sesiones }));
    }

    // Abrir una aplicacion con la sesion ya iniciada.
    m = /^\/abrir\/([a-z0-9_-]+)$/.exec(ruta);
    if (m) {
      const app = appPorClave(m[1]);
      if (!app) return render(V.vistaMensaje({ ...comun(usuario), titulo: 'Aplicación no encontrada', texto: 'La aplicación solicitada no está configurada en el portal.' }), 404);
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
      if (req.method === 'GET') return render(V.vistaVincular({ ...comun(usuario), app }));
      const c = await leerCuerpo(req);
      if (!csrfValido(usuario, c)) return render(V.vistaVincular({ ...comun(usuario), app, error: 'La sesión cambió. Intente de nuevo.' }), 403);
      let r;
      try { r = await verificarCredenciales(app, String(c.usuario || '').trim(), c.clave || ''); } catch (e) { return render(V.vistaVincular({ ...comun(usuario), app, error: 'No fue posible contactar la aplicación. ' + e.message }), 502); }
      if (!r.ok) { auditar('vinculo_fallido', { usuarioId: usuario.id, app: app.clave, ip }); return render(V.vistaVincular({ ...comun(usuario), app, error: 'Usuario o clave no válidos en ' + app.nombre + '.' }), 401); }
      db.prepare(`INSERT INTO identidades (usuario_id, app, id_externo, usuario_externo, rol_externo) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT(app, id_externo) DO UPDATE SET usuario_id = excluded.usuario_id, usuario_externo = excluded.usuario_externo, rol_externo = excluded.rol_externo, verificado_en = datetime('now')`)
        .run(usuario.id, app.clave, String(r.id), r.usuario || c.usuario, r.rol || null);
      auditar('vinculo', { usuarioId: usuario.id, app: app.clave, ip });
      return redirigir(res, '/cuenta');
    }

    // ---------------------------------------------------------------- cuestionarios y campañas (administradores)
    if (ruta.startsWith('/cuestionarios') || ruta.startsWith('/campanias')) {
      // Cualquier usuario del portal ve los cuestionarios publicados como un aplicativo más; la gestión es de administradores.
      if (!esAdmin && ruta === '/cuestionarios' && req.method === 'GET') return render(VC.vistaCuestionariosParaTodos({ ...comun(usuario), lista: C.listarCuestionarios().filter((c) => c.estado === 'publicado') }));
      if (!esAdmin) return render(V.vistaMensaje({ ...comun(usuario), titulo: 'Sin permiso', texto: 'La gestión de cuestionarios es solo para administradores del portal.' }), 403);
      const r = await rutasCuestionarios({ req, res, ruta, url, usuario, ip, render });
      if (r !== undefined) return r;
    }

    // Administracion.
    if (ruta.startsWith('/admin')) {
      if (!esAdmin) return render(V.vistaMensaje({ ...comun(usuario), titulo: 'Sin permiso', texto: 'Esta sección es solo para administradores del portal.' }), 403);
      let mensaje = '';
      // Cuentas: cambiar el rol de una cuenta o registrar por correo una cuenta administradora.
      let mm = /^\/admin\/usuarios\/(\d+)\/rol$/.exec(ruta);
      if (mm && req.method === 'POST') {
        const c = await leerCuerpo(req);
        if (!csrfValido(usuario, c)) return redirigir(res, '/admin');
        const objetivo = db.prepare('SELECT * FROM usuarios WHERE id = ?').get(Number(mm[1]));
        const rol = c.rol === 'administrador' ? 'administrador' : 'usuario';
        if (!objetivo) mensaje = 'La cuenta no existe.';
        else if (objetivo.id === usuario.id && rol !== 'administrador') mensaje = 'No puede quitarse a sí mismo el rol de administrador.';
        else { db.prepare('UPDATE usuarios SET rol = ? WHERE id = ?').run(rol, objetivo.id); auditar('rol_cambiado', { usuarioId: usuario.id, detalle: `${objetivo.correo} -> ${rol}`, ip }); mensaje = `${objetivo.correo} ahora es ${rol}.`; }
      }
      if (ruta === '/admin/usuarios' && req.method === 'POST') {
        const c = await leerCuerpo(req);
        if (!csrfValido(usuario, c)) return redirigir(res, '/admin');
        const correo = String(c.correo || '').trim().toLowerCase();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correo)) mensaje = 'Escriba un correo válido.';
        else {
          const existente = db.prepare('SELECT * FROM usuarios WHERE correo = ?').get(correo);
          if (existente) { db.prepare("UPDATE usuarios SET rol = 'administrador' WHERE id = ?").run(existente.id); mensaje = `${correo} ya tenía cuenta; ahora es administrador.`; }
          else { db.prepare("INSERT INTO usuarios (correo, rol) VALUES (?, 'administrador')").run(correo); mensaje = `${correo} quedó registrado como administrador. Entrará con su usuario y clave de cualquier aplicativo conectado que use ese correo.`; }
          auditar('administrador_agregado', { usuarioId: usuario.id, detalle: correo, ip });
        }
      }
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
      return render(V.vistaAdmin({ ...comun(usuario), estados, usuarios, auditoria, mensaje }));
    }

    return render(V.vistaMensaje({ ...comun(usuario), titulo: 'Página no encontrada', texto: 'La dirección solicitada no existe en el portal.' }), 404);
  } catch (e) {
    console.error(e);
    auditar('error', { detalle: e.message, ip });
    if (res.headersSent) { try { res.end(); } catch {} return; }
    if ((req.headers.accept || '').includes('application/json')) return json(res, { ok: false, mensaje: 'El portal no pudo completar la acción.' }, 500);
    return html(res, V.vistaMensaje({ ...comun(usuario), titulo: 'Ocurrió un error', texto: 'El portal no pudo completar la acción. Intente de nuevo o escriba a soporte.' }), 500);
  }
});

// Rutas de administración de cuestionarios y campañas. Devuelve undefined si la ruta no es suya.
async function rutasCuestionarios({ req, res, ruta, url, usuario, ip, render }) {
  const base = comun(usuario);
  const smtpOk = correoConfigurado();
  const q = (k) => url.searchParams.get(k) || '';
  const volver = (a, m, e) => redirigir(res, a + (m ? `?m=${encodeURIComponent(m)}` : e ? `?e=${encodeURIComponent(e)}` : ''));
  const cuerpoValidado = async () => { const c = await leerCuerpo(req); if (!csrfValido(usuario, c)) throw Object.assign(new Error('La sesión cambió. Intente de nuevo.'), { csrf: true }); return c; };
  let m;

  if (ruta === '/cuestionarios' && req.method === 'GET') return render(VC.vistaCuestionarios({ ...base, lista: C.listarCuestionarios(), mensaje: q('m') || q('e'), smtpOk }));

  // Editor: GET muestra, POST recibe la definición en JSON.
  m = /^\/cuestionarios\/(nuevo|(\d+)\/editar)$/.exec(ruta);
  if (m) {
    const c = m[2] ? C.obtenerCuestionario(Number(m[2])) : null;
    if (m[2] && !c) return render(V.vistaMensaje({ ...base, titulo: 'Cuestionario no encontrado', texto: 'El cuestionario no existe.', enlace: '/cuestionarios', textoEnlace: 'Volver a la lista' }), 404);
    if (req.method === 'GET') return render(VC.vistaEditor({ ...base, cuestionario: c, csrf: csrfDe(usuario.sesionId) }));
    const cuerpo = await leerCuerpo(req);
    if (!csrfValido(usuario, cuerpo)) return json(res, { ok: false, mensaje: 'La sesión cambió. Recargue la página e intente de nuevo.' }, 403);
    const def = cuerpo.definicion;
    const problemas = C.validarDefinicion(def);
    if (problemas.length) return json(res, { ok: false, problemas }, 400);
    const guardado = c ? C.actualizarCuestionario(c.id, { definicion: def }) : C.crearCuestionario({ titulo: def.titulo, definicion: def, usuarioId: usuario.id });
    auditar(c ? 'cuestionario_editado' : 'cuestionario_creado', { usuarioId: usuario.id, app: 'cuestionarios', detalle: guardado.clave, ip });
    return json(res, { ok: true, id: guardado.id, clave: guardado.clave, version: guardado.version, editarUrl: `/cuestionarios/${guardado.id}/editar` });
  }

  m = /^\/cuestionarios\/(\d+)\/campanias$/.exec(ruta);
  if (m && req.method === 'GET') { const c = C.obtenerCuestionario(Number(m[1])); if (!c) return undefined; return render(VC.vistaCampanias({ ...base, cuestionario: c, campanias: K.listarCampanias(c.id), mensaje: q('m'), error: q('e'), smtpOk })); }

  m = /^\/cuestionarios\/(\d+)(?:\/(.*))?$/.exec(ruta);
  if (m) {
    const c = C.obtenerCuestionario(Number(m[1]));
    if (!c) return render(V.vistaMensaje({ ...base, titulo: 'Cuestionario no encontrado', texto: 'El cuestionario no existe.', enlace: '/cuestionarios', textoEnlace: 'Volver a la lista' }), 404);
    const resto = m[2] || '';
    if (req.method === 'GET' && (resto === '' || resto === 'respuestas.csv')) {
      const filtros = { buscar: q('buscar'), campania: q('campania'), periodo: q('periodo'), desde: q('desde'), hasta: q('hasta') };
      for (const [k, v] of url.searchParams) if (k.startsWith('f_')) filtros[k] = v;
      let filas = C.listarRespuestas(c.id, { campaniaId: filtros.campania ? Number(filtros.campania) : null, periodo: filtros.periodo || null, desde: filtros.desde || null, hasta: filtros.hasta || null, buscar: filtros.buscar, limite: 100000 });
      for (const [k, v] of Object.entries(filtros)) if (k.startsWith('f_') && v) { const campo = k.slice(2); filas = filas.filter((r) => { const x = r.datos[campo]; return Array.isArray(x) ? x.map(String).includes(v) : String(x ?? '') === v; }); }
      if (resto === 'respuestas.csv') {
        res.writeHead(200, { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': `attachment; filename="respuestas-${c.clave}-${new Date().toISOString().slice(0, 10)}.csv"`, 'Cache-Control': 'no-store' });
        res.end(C.csvDe(c.definicion, filas));
        return true;
      }
      return render(VC.vistaResultados({ ...base, cuestionario: c, resumen: C.resumenRespuestas(c.definicion, filas), filas, filtros, campanias: K.listarCampanias(c.id), periodos: C.periodosDisponibles(c.id), pagina: Math.max(1, Number(q('pagina') || 1)) }));
    }
    let a = /^respuestas\/(\d+)\/archivo\/([a-z0-9_]+)$/i.exec(resto);
    if (a && req.method === 'GET') {
      const r = C.obtenerRespuesta(Number(a[1]));
      const info = r && r.cuestionario_id === c.id && r.datos[a[2]];
      if (!info || !info.ruta) { res.writeHead(404); res.end(); return true; }
      const archivo = path.join(C.carpetaArchivos(c.id, r.id), path.basename(info.ruta));
      if (!fs.existsSync(archivo)) { res.writeHead(404); res.end(); return true; }
      res.writeHead(200, { 'Content-Type': 'application/octet-stream', 'Content-Disposition': `attachment; filename="${encodeURIComponent(info.archivo || 'archivo')}"`, 'X-Content-Type-Options': 'nosniff' });
      fs.createReadStream(archivo).pipe(res);
      return true;
    }
    // Importación de respuestas anteriores desde Excel o CSV: archivo, propuesta de correspondencia y confirmación.
    if (resto === 'importar' && req.method === 'GET') return render(VC.vistaImportar({ ...base, cuestionario: c, campanias: K.listarCampanias(c.id), campaniaSeleccionada: q('campania') }));
    if (resto === 'importar' && req.method === 'POST') {
      let envio;
      try { envio = await leerEnvio(req); } catch (e) { return render(VC.vistaImportar({ ...base, cuestionario: c, campanias: K.listarCampanias(c.id), error: 'El archivo es demasiado grande (máximo 20 MB).' }), 413); }
      if (!csrfValido(usuario, envio.campos)) return volver(`/cuestionarios/${c.id}/importar`, '', 'La sesión cambió. Intente de nuevo.');
      const a = envio.archivos.archivo;
      if (!a) return render(VC.vistaImportar({ ...base, cuestionario: c, campanias: K.listarCampanias(c.id), error: 'No llegó ningún archivo.' }), 400);
      let hoja;
      try { hoja = leerHoja(a.datos, a.nombre); } catch (e) { return render(VC.vistaImportar({ ...base, cuestionario: c, campanias: K.listarCampanias(c.id), error: 'No se pudo leer el archivo: ' + e.message }), 400); }
      if (!hoja.columnas.length || !hoja.filas.length) return render(VC.vistaImportar({ ...base, cuestionario: c, campanias: K.listarCampanias(c.id), error: 'El archivo no tiene una fila de encabezados seguida de datos.' }), 400);
      const token = C.tokenNuevo();
      fs.writeFileSync(path.join(C.carpetaImportaciones(), `${token}.json`), JSON.stringify({ cuestionarioId: c.id, archivo: a.nombre, columnas: hoja.columnas, filas: hoja.filas, creado: Date.now() }));
      return render(VC.vistaImportarMapeo({ ...base, cuestionario: c, token, columnas: hoja.columnas, muestra: hoja.filas.slice(0, 5), total: hoja.filas.length, sugerencias: C.sugerirMapeo(c.definicion, hoja.columnas), destinos: C.destinosDeImportacion(c.definicion), campanias: K.listarCampanias(c.id), campaniaSeleccionada: envio.campos.campania, nuevaCampania: envio.campos.nueva_campania, archivo: a.nombre, periodo: envio.campos.periodo }));
    }
    if (req.method !== 'POST') return undefined;
    let cuerpo;
    try { cuerpo = await cuerpoValidado(); } catch (e) { return volver(`/cuestionarios/${c.id}`, '', e.message); }
    a = /^importar\/([A-Za-z0-9_-]+)$/.exec(resto);
    if (a) {
      const ruta = path.join(C.carpetaImportaciones(), `${a[1]}.json`);
      if (!fs.existsSync(ruta)) return volver(`/cuestionarios/${c.id}/importar`, '', 'La sesión de importación caducó. Vuelva a subir el archivo.');
      const guardado = JSON.parse(fs.readFileSync(ruta, 'utf8'));
      if (guardado.cuestionarioId !== c.id) return volver(`/cuestionarios/${c.id}/importar`, '', 'El archivo no corresponde a este cuestionario.');
      const mapeo = {};
      for (const [k, v] of Object.entries(cuerpo)) if (k.startsWith('col_') && v) mapeo[k.slice(4)] = String(v);
      if (!Object.keys(mapeo).length) return volver(`/cuestionarios/${c.id}/importar`, '', 'No se asignó ninguna columna a una pregunta.');
      let campaniaId = Number(cuerpo.campania);
      if (!campaniaId || cuerpo.campania === 'nueva') {
        const k = K.crearCampania({ cuestionarioId: c.id, nombre: String(cuerpo.nueva_campania || `Importación ${guardado.archivo}`).trim(), asunto: 'Importación de respuestas anteriores', cuerpo: `Respuestas importadas del archivo ${guardado.archivo}.`, usuarioId: usuario.id, periodo: cuerpo.periodo });
        db.prepare("UPDATE campanias SET estado = 'importada', ultimo_resultado = ? WHERE id = ?").run(`Importado de ${guardado.archivo}`, k.id);
        campaniaId = k.id;
      }
      const r = C.importarRespuestas({ cuestionario: c, campaniaId, mapeo, filas: guardado.filas, omitirDuplicados: !!cuerpo.omitir_duplicados, usuarioId: usuario.id });
      fs.rmSync(ruta, { force: true });
      auditar('importacion_archivo', { usuarioId: usuario.id, app: 'cuestionarios', detalle: `${c.clave}: ${guardado.archivo} → ${r.importadas} filas`, ip });
      return volver(`/cuestionarios/${c.id}`, `Importación terminada: ${r.importadas} respuestas importadas, ${r.omitidas} omitidas por duplicadas, ${r.vacias} filas vacías${r.problemas.length ? `. Problemas: ${r.problemas.slice(0, 5).join(' | ')}` : ''}.`);
    }
    if (resto === 'estado') { C.cambiarEstado(c.id, String(cuerpo.estado)); auditar('cuestionario_estado', { usuarioId: usuario.id, app: 'cuestionarios', detalle: `${c.clave}: ${cuerpo.estado}`, ip }); return volver('/cuestionarios', `«${c.definicion.titulo}» ahora está en estado ${cuerpo.estado}.`); }
    if (resto === 'duplicar') { const n = C.duplicarCuestionario(c.id, usuario.id); auditar('cuestionario_duplicado', { usuarioId: usuario.id, app: 'cuestionarios', detalle: `${c.clave} -> ${n.clave}`, ip }); return redirigir(res, `/cuestionarios/${n.id}/editar`); }
    if (resto === 'eliminar') { if (c.protegido) return volver('/cuestionarios', '', 'Los ejemplos del proyecto no se pueden eliminar.'); C.eliminarCuestionario(c.id); auditar('cuestionario_eliminado', { usuarioId: usuario.id, app: 'cuestionarios', detalle: c.clave, ip }); return volver('/cuestionarios', `Se eliminó «${c.definicion.titulo}».`); }
    a = /^respuestas\/(\d+)\/eliminar$/.exec(resto);
    if (a) { const r = C.obtenerRespuesta(Number(a[1])); if (r && r.cuestionario_id === c.id) { C.eliminarRespuesta(r.id); auditar('respuesta_eliminada', { usuarioId: usuario.id, app: 'cuestionarios', detalle: `${c.clave} #${r.id}`, ip }); } return redirigir(res, `/cuestionarios/${c.id}`); }
    if (resto === 'campanias') {
      const lista = K.interpretarLista(cuerpo.destinatarios);
      const programadaEn = K.aUtc(cuerpo.programada_en);
      if (cuerpo.programada_en && !programadaEn) return volver(`/cuestionarios/${c.id}/campanias`, '', 'La fecha de programación no es válida.');
      if (programadaEn && !smtpOk) return volver(`/cuestionarios/${c.id}/campanias`, '', 'No se puede programar un envío sin servidor de correo configurado.');
      const k = K.crearCampania({ cuestionarioId: c.id, nombre: String(cuerpo.nombre || '').trim(), asunto: String(cuerpo.asunto || '').trim(), cuerpo: String(cuerpo.cuerpo || ''), programadaEn, usuarioId: usuario.id, periodo: cuerpo.periodo });
      const n = K.agregarDestinatarios(k.id, lista);
      auditar('campania_creada', { usuarioId: usuario.id, app: 'cuestionarios', detalle: `${k.nombre}: ${n} destinatarios`, ip });
      return volver(`/campanias/${k.id}`, `Campaña creada con ${n} destinatarios${programadaEn ? ', programada' : ''}.`);
    }
    return undefined;
  }

  // Campañas.
  m = /^\/campanias\/(\d+)(?:\/(.*))?$/.exec(ruta);
  if (m) {
    const k = K.obtenerCampania(Number(m[1]));
    if (!k) return render(V.vistaMensaje({ ...base, titulo: 'Campaña no encontrada', texto: 'La campaña no existe.', enlace: '/cuestionarios', textoEnlace: 'Volver' }), 404);
    const c = C.obtenerCuestionario(k.cuestionario_id);
    const resto = m[2] || '';
    const pagina = (mensaje, error) => render(VC.vistaCampania({ ...base, cuestionario: c, campania: K.obtenerCampania(k.id), destinatarios: K.destinatariosDe(k.id), mensaje, error, previa: K.vistaPreviaCorreo(k), smtpOk, enviando: K.estaEnviando(k.id) }));
    if (req.method === 'GET' && resto === '') return pagina(q('m'), q('e'));
    // QR de los enlaces personales: uno por destinatario o la hoja imprimible con todos.
    const dq = /^destinatarios\/(\d+)\/qr\.svg$/.exec(resto);
    if (dq && req.method === 'GET') {
      const d = K.destinatariosDe(k.id).find((x) => x.id === Number(dq[1]));
      if (!d) { res.writeHead(404); res.end(); return true; }
      return svg(res, svgQr(K.enlaceDe(c.clave, d.token), { pie: d.entidad || d.nombre || d.correo }), `qr-${c.clave}-${d.id}.svg`, q('descargar') === '1');
    }
    if (resto === 'qr' && req.method === 'GET') return html(res, VC.vistaCampaniaQr({ cuestionario: c, campania: k, destinatarios: K.destinatariosDe(k.id), qrDe: (d) => svgQr(K.enlaceDe(c.clave, d.token), { escala: 4, margen: 2 }), qrPublico: svgQr(`${config.urlPublica}/c/${c.clave}`, { escala: 4, margen: 2 }) }));
    if (req.method !== 'POST') return undefined;
    let cuerpo;
    try { cuerpo = await cuerpoValidado(); } catch (e) { return pagina('', e.message); }
    try {
      if (resto === 'enviar') { const r = await K.enviarCampania(k.id); return volver(`/campanias/${k.id}`, `Envío iniciado a ${r.destinatarios} destinatarios. Recargue para ver el avance.`); }
      if (resto === 'recordar') { const r = await K.enviarCampania(k.id, { recordatorio: true, prefijoAsunto: 'Recordatorio: ' }); return volver(`/campanias/${k.id}`, `Recordatorio en camino a ${r.destinatarios} destinatarios.`); }
      if (resto === 'prueba') { await K.enviarPrueba(k.id, String(cuerpo.correo || usuario.correo).trim()); return volver(`/campanias/${k.id}`, `Correo de prueba enviado a ${cuerpo.correo || usuario.correo}.`); }
      if (resto === 'programar') { const f = K.aUtc(cuerpo.programada_en); if (!f) throw new Error('La fecha no es válida.'); if (!smtpOk) throw new Error('No se puede programar sin servidor de correo configurado.'); K.actualizarCampania(k.id, { programadaEn: f }); auditar('campania_programada', { usuarioId: usuario.id, app: 'cuestionarios', detalle: `${k.nombre}: ${f}`, ip }); return volver(`/campanias/${k.id}`, 'Campaña programada.'); }
      if (resto === 'cancelar') { K.cancelarCampania(k.id); return volver(`/campanias/${k.id}`, 'Programación cancelada.'); }
      if (resto === 'editar') { K.actualizarCampania(k.id, { nombre: String(cuerpo.nombre || '').trim(), asunto: String(cuerpo.asunto || '').trim(), cuerpo: String(cuerpo.cuerpo || ''), programadaEn: k.programada_en, periodo: cuerpo.periodo }); return volver(`/campanias/${k.id}`, 'Campaña guardada.'); }
      if (resto === 'destinatarios') { const n = K.agregarDestinatarios(k.id, K.interpretarLista(cuerpo.destinatarios)); return volver(`/campanias/${k.id}`, `${n} destinatarios agregados.`); }
      if (resto === 'eliminar') { K.eliminarCampania(k.id); auditar('campania_eliminada', { usuarioId: usuario.id, app: 'cuestionarios', detalle: k.nombre, ip }); return volver(`/cuestionarios/${c.id}/campanias`, `Se eliminó la campaña «${k.nombre}».`); }
      const d = /^destinatarios\/(\d+)\/quitar$/.exec(resto);
      if (d) { K.quitarDestinatario(k.id, Number(d[1])); return redirigir(res, `/campanias/${k.id}`); }
    } catch (e) {
      return pagina('', e.message);
    }
  }
  return undefined;
}

servidor.listen(config.puerto, () => {
  console.log(`Portal del Observatorio en ${config.urlPublica} (puerto ${config.puerto}). Aplicaciones: ${config.apps.map((a) => a.clave).join(', ') || 'ninguna configurada'}.`);
  // Las cuentas listadas en ADMINISTRADORES reciben el rol aunque se hayan creado antes de estar en la lista.
  for (const correo of config.administradores) db.prepare("UPDATE usuarios SET rol = 'administrador' WHERE correo = ? AND rol != 'administrador'").run(correo);
  const sembrados = C.sembrarEjemplos();
  if (sembrados) console.log(`Cuestionarios de ejemplo cargados: ${sembrados}.`);
  console.log(correoConfigurado() ? `Correo configurado por ${config.smtp.host}:${config.smtp.puerto} (${config.smtp.seguridad}).` : 'Correo sin configurar: las campañas no se enviarán hasta definir SMTP_HOST y CORREO_DESDE.');
  programarRecoleccion();
  K.programarEnvios();
});
