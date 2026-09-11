// Autenticación: sesiones propias + integración con el sistema de usuarios de gestor.proyectoia.org.
//
// Modos (variable AUTH_MODE):
//   gestor : solo se aceptan usuarios autenticados por gestor.proyectoia.org (SSO por token o cookie compartida).
//   local  : usuarios y contraseñas propios (útil para desarrollo o contingencia).
//   mixto  : ambos (predeterminado).
//
// Contrato esperado con gestor.proyectoia.org (todo configurable por variables de entorno):
//   1) Redirección de inicio de sesión:   GESTOR_LOGIN_URL?<GESTOR_REDIRECT_PARAM>=<url de retorno>
//   2) Retorno con token:                 /auth/gestor/callback?<GESTOR_TOKEN_PARAM>=<token>
//   3) Validación del token, en este orden de preferencia:
//      a) GESTOR_USERINFO_URL: GET con "Authorization: Bearer <token>" que responde JSON con id/email/nombre/rol.
//      b) Firma JWT local: GESTOR_JWT_SECRET (HS256) o GESTOR_JWT_PUBLIC_KEY (RS256), con reclamos sub/email/name/role.
//   4) Alternativa por cookie compartida en el dominio .proyectoia.org: GESTOR_SESSION_COOKIE + GESTOR_USERINFO_URL.
import { createHmac, randomBytes, scryptSync, timingSafeEqual, createVerify, createHash } from 'node:crypto';
import { getDb, log } from './db.js';
import { HttpError } from './router.js';

const MODE = (process.env.AUTH_MODE || 'mixto').toLowerCase();
const SESSION_COOKIE = process.env.SESSION_COOKIE || 'diso_sesion';
const SESSION_DAYS = Number(process.env.SESSION_DAYS || 14);
const SECRET = process.env.SESSION_SECRET || (process.env.NODE_ENV === 'production' ? null : 'secreto-de-desarrollo');
if (!SECRET) throw new Error('SESSION_SECRET es obligatorio en producción');

export const authConfig = {
  mode: MODE,
  gestorHabilitado: MODE !== 'local' && !!process.env.GESTOR_LOGIN_URL,
  gestorCredenciales: MODE !== 'local' && !!process.env.GESTOR_LOGIN_API,
  localHabilitado: MODE !== 'gestor',
  gestorNombre: process.env.GESTOR_NOMBRE || 'Gestor ProyectoIA',
  gestorUrl: process.env.GESTOR_URL || 'https://gestor.proyectoia.org',
  appUrl: process.env.APP_PROYECTOIA_URL || 'https://app.proyectoia.org',
};

// ---------- utilidades de cookies y firma ----------
export function parseCookies(req) {
  const out = {};
  for (const part of (req.headers.cookie || '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}
function sign(value) { return value + '.' + createHmac('sha256', SECRET).update(value).digest('base64url'); }
function unsign(signed) {
  if (!signed) return null;
  const i = signed.lastIndexOf('.');
  if (i < 0) return null;
  const value = signed.slice(0, i);
  const expected = sign(value);
  if (expected.length !== signed.length) return null;
  return timingSafeEqual(Buffer.from(expected), Buffer.from(signed)) ? value : null;
}
function cookieHeader(name, value, { maxAge, secure } = {}) {
  let c = `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; SameSite=Lax`;
  if (secure) c += '; Secure';
  if (maxAge !== undefined) c += `; Max-Age=${maxAge}`;
  return c;
}
function isSecure(req) {
  return req.headers['x-forwarded-proto'] === 'https' || process.env.FORCE_SECURE_COOKIE === '1';
}

// ---------- contraseñas locales ----------
export function hashPassword(pw) {
  const salt = randomBytes(16).toString('hex');
  return 'scrypt$' + salt + '$' + scryptSync(pw, salt, 64).toString('hex');
}
export function verifyPassword(pw, hash) {
  if (!hash || !hash.startsWith('scrypt$')) return false;
  const [, salt, h] = hash.split('$');
  const calc = scryptSync(pw, salt, 64);
  const stored = Buffer.from(h, 'hex');
  return calc.length === stored.length && timingSafeEqual(calc, stored);
}

// ---------- sesiones ----------
export function crearSesion(res, req, usuarioId, gestorCookie = null) {
  const db = getDb();
  const id = randomBytes(24).toString('base64url');
  const expira = new Date(Date.now() + SESSION_DAYS * 86400000).toISOString();
  db.prepare('INSERT INTO sesiones (id, usuario_id, expira_en, gestor_cookie) VALUES (?,?,?,?)').run(id, usuarioId, expira, gestorCookie);
  db.prepare("UPDATE usuarios SET ultimo_acceso = datetime('now') WHERE id = ?").run(usuarioId);
  res.setHeader('Set-Cookie', cookieHeader(SESSION_COOKIE, sign(id), { maxAge: SESSION_DAYS * 86400, secure: isSecure(req) }));
}
export function cerrarSesion(req, res) {
  const id = unsign(parseCookies(req)[SESSION_COOKIE]);
  if (id) getDb().prepare('DELETE FROM sesiones WHERE id = ?').run(id);
  res.setHeader('Set-Cookie', cookieHeader(SESSION_COOKIE, '', { maxAge: 0, secure: isSecure(req) }));
}
export function usuarioActual(req) {
  const id = unsign(parseCookies(req)[SESSION_COOKIE]);
  if (!id) return null;
  const row = getDb().prepare(`SELECT u.*, s.gestor_cookie AS _gestor_cookie FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id
                               WHERE s.id = ? AND s.expira_en > datetime('now') AND u.activo = 1`).get(id);
  if (!row) return null;
  const { password_hash, _gestor_cookie, ...u } = row;
  Object.defineProperty(u, 'gestor_cookie', { value: _gestor_cookie ?? null, enumerable: false });
  return u;
}

// ---------- middlewares ----------
export function requiereSesion(ctx) {
  if (!ctx.usuario) throw new HttpError(401, 'Sesión requerida');
}
export function requiereRol(...roles) {
  return (ctx) => {
    requiereSesion(ctx);
    if (!roles.includes(ctx.usuario.rol)) throw new HttpError(403, 'No tiene permisos para esta acción');
  };
}

// ---------- inicio de sesión local ----------
export async function loginConCredenciales(email, password) {
  email = String(email || '').trim(); password = String(password || '');
  if (!email || !password) throw new HttpError(400, 'Ingrese correo y contraseña');
  // 1) Usuarios del gestor de proyectos (validación delegada)
  if (authConfig.gestorCredenciales) {
    const u = await loginDelegadoGestor(email, password);
    if (u) return u;
  }
  // 2) Usuarios locales de esta herramienta
  if (authConfig.localHabilitado) {
    const u = getDb().prepare('SELECT * FROM usuarios WHERE email = ? AND activo = 1 AND password_hash IS NOT NULL').get(email);
    if (u && verifyPassword(password, u.password_hash)) return u;
  }
  if (!authConfig.localHabilitado && !authConfig.gestorCredenciales) throw new HttpError(403, 'El acceso con contraseña está deshabilitado. Use el ingreso por ' + authConfig.gestorNombre + '.');
  throw new HttpError(401, 'Correo o contraseña incorrectos');
}
export function loginLocal(email, password) {
  if (!authConfig.localHabilitado) throw new HttpError(403, 'El acceso local está deshabilitado. Use el ingreso por ' + authConfig.gestorNombre + '.');
  const u = getDb().prepare('SELECT * FROM usuarios WHERE email = ? AND activo = 1').get(String(email || '').trim());
  if (!u || !verifyPassword(String(password || ''), u.password_hash)) throw new HttpError(401, 'Correo o contraseña incorrectos');
  return u;
}

// ---------- validación delegada: el gestor comprueba correo y contraseña ----------
// GESTOR_LOGIN_API  = https://gestor.proyectoia.org/api/login   (POST JSON con las credenciales)
// GESTOR_SESION_API = https://gestor.proyectoia.org/api/sesion  (GET con la cookie devuelta; responde el perfil)
// Los nombres de campo se envían con varios alias (email/correo/usuario, password/clave/contrasena) para
// acoplarse al gestor sin modificarlo. GESTOR_LOGIN_CAMPOS permite fijarlos: "correo,clave".
function cuerpoCredenciales(email, password) {
  const fijos = (process.env.GESTOR_LOGIN_CAMPOS || '').split(',').map(x => x.trim()).filter(Boolean);
  if (fijos.length === 2) return { [fijos[0]]: email, [fijos[1]]: password };
  return { email, correo: email, usuario: email, username: email, password, clave: password, contrasena: password, contraseña: password };
}
export async function loginDelegadoGestor(email, password) {
  const loginUrl = process.env.GESTOR_LOGIN_API;
  if (!loginUrl) return null;
  let r;
  try {
    r = await fetch(loginUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(cuerpoCredenciales(email, password)), signal: AbortSignal.timeout(8000), redirect: 'manual' });
  } catch (e) { throw new HttpError(503, authConfig.gestorNombre + ' no respondió: ' + e.message); }
  if (r.status === 401 || r.status === 403 || r.status === 400) return null;      // credenciales rechazadas
  if (!r.ok && r.status !== 302) throw new HttpError(502, authConfig.gestorNombre + ' respondió HTTP ' + r.status);
  let perfil = {};
  try { perfil = await r.json(); } catch { }
  perfil = perfil.usuario ?? perfil.user ?? perfil.data ?? perfil;
  if (perfil && typeof perfil === 'object' && perfil.ok === false) return null;
  const cookies = (typeof r.headers.getSetCookie === 'function' ? r.headers.getSetCookie() : [r.headers.get('set-cookie')].filter(Boolean)).map(c => c.split(';')[0]).join('; ');
  const token = perfil.token ?? perfil.access_token ?? perfil.jwt ?? null;
  const sesionUrl = process.env.GESTOR_SESION_API;
  if (sesionUrl && (cookies || token)) {
    try {
      const headers = { Accept: 'application/json' };
      if (cookies) headers.Cookie = cookies;
      if (token) headers.Authorization = 'Bearer ' + token;
      const s2 = await fetch(sesionUrl, { headers, signal: AbortSignal.timeout(8000) });
      if (s2.ok) { const j = await s2.json(); perfil = { ...perfil, ...(j.usuario ?? j.user ?? j.data ?? j) }; }
    } catch { }
  }
  if (!perfil.email && !perfil.correo && !perfil.usuario) perfil.email = email;   // el gestor validó, el correo es el ingresado
  const u = upsertUsuarioGestor(perfil);
  u.gestor_cookie = cookies || null;
  return u;
}

// ---------- sincronización del listado de usuarios del gestor ----------
// GESTOR_USUARIOS_API (por defecto <GESTOR_URL>/api/usuarios) se consulta con la cookie de sesión del
// administrador que ingresó por el gestor. Cada usuario recibido se crea o actualiza localmente (origen gestor).
export async function sincronizarUsuariosGestor(cookie) {
  const url = process.env.GESTOR_USUARIOS_API || (authConfig.gestorUrl.replace(/\/$/, '') + '/api/usuarios');
  if (!cookie) throw new HttpError(400, 'Para sincronizar debe haber ingresado con un usuario de ' + authConfig.gestorNombre);
  let r;
  try { r = await fetch(url, { headers: { Accept: 'application/json', Cookie: cookie }, signal: AbortSignal.timeout(10000) }); }
  catch (e) { throw new HttpError(503, authConfig.gestorNombre + ' no respondió: ' + e.message); }
  if (r.status === 401 || r.status === 403) throw new HttpError(403, authConfig.gestorNombre + ' no autorizó el listado de usuarios con su sesión');
  if (!r.ok) throw new HttpError(502, authConfig.gestorNombre + ' respondió HTTP ' + r.status + ' en ' + url);
  const j = await r.json();
  const lista = Array.isArray(j) ? j : (j.usuarios ?? j.users ?? j.data ?? j.items ?? []);
  if (!Array.isArray(lista)) throw new HttpError(502, 'Formato de usuarios no reconocido en ' + url);
  const db = getDb();
  let creados = 0, actualizados = 0, omitidos = 0;
  for (const p of lista) {
    try {
      const antes = db.prepare('SELECT COUNT(*) c FROM usuarios').get().c;
      const u = upsertUsuarioGestor(p, { desdeSincronizacion: true });
      const despues = db.prepare('SELECT COUNT(*) c FROM usuarios').get().c;
      if (despues > antes) creados++; else actualizados++;
      db.prepare("UPDATE usuarios SET cargo = COALESCE(?, cargo), activo = ?, sincronizado_en = datetime('now') WHERE id = ?")
        .run(String(p.cargo ?? p.dependencia ?? p.area ?? '') || null, (p.activo === false || p.activo === 0 || p.estado === 'inactivo') ? 0 : 1, u.id);
    } catch { omitidos++; }
  }
  return { total: lista.length, creados, actualizados, omitidos };
}

// Usuario administrador inicial en modo local (ADMIN_EMAIL / ADMIN_PASSWORD).
export function asegurarAdminInicial() {
  const db = getDb();
  const n = db.prepare('SELECT COUNT(*) c FROM usuarios').get().c;
  if (n > 0) return;
  const email = process.env.ADMIN_EMAIL || 'admin@proyectoia.org';
  const pw = process.env.ADMIN_PASSWORD || 'admin1234';
  db.prepare('INSERT INTO usuarios (id, email, nombre, rol, origen, password_hash) VALUES (?,?,?,?,?,?)')
    .run(randomBytes(8).toString('hex'), email, process.env.ADMIN_NOMBRE || 'Administrador', 'admin', 'local', hashPassword(pw));
  console.log(`[auth] Usuario administrador inicial creado: ${email}` + (process.env.ADMIN_PASSWORD ? '' : ' (contraseña predeterminada: admin1234, cámbiela)'));
}

// ---------- integración con gestor.proyectoia.org ----------
export function urlLoginGestor(retorno) {
  const base = process.env.GESTOR_LOGIN_URL;
  if (!base) throw new HttpError(503, 'La integración con ' + authConfig.gestorNombre + ' no está configurada (GESTOR_LOGIN_URL).');
  const u = new URL(base);
  u.searchParams.set(process.env.GESTOR_REDIRECT_PARAM || 'redirect_uri', retorno);
  if (process.env.GESTOR_CLIENT_ID) u.searchParams.set('client_id', process.env.GESTOR_CLIENT_ID);
  return u.toString();
}

function b64urlJson(s) { return JSON.parse(Buffer.from(s, 'base64url').toString('utf8')); }

export function verificarJwt(token) {
  const parts = token.split('.');
  if (parts.length !== 3) throw new HttpError(401, 'Token inválido');
  const [h, p, s] = parts;
  const header = b64urlJson(h);
  const data = h + '.' + p;
  let ok = false;
  if (process.env.GESTOR_JWT_SECRET && /^HS(256|384|512)$/.test(header.alg)) {
    const alg = 'sha' + header.alg.slice(2);
    const calc = createHmac(alg, process.env.GESTOR_JWT_SECRET).update(data).digest();
    const sig = Buffer.from(s, 'base64url');
    ok = calc.length === sig.length && timingSafeEqual(calc, sig);
  } else if (process.env.GESTOR_JWT_PUBLIC_KEY && /^RS(256|384|512)$/.test(header.alg)) {
    const v = createVerify('RSA-SHA' + header.alg.slice(2));
    v.update(data);
    ok = v.verify(process.env.GESTOR_JWT_PUBLIC_KEY.replace(/\\n/g, '\n'), Buffer.from(s, 'base64url'));
  } else {
    throw new HttpError(503, 'No hay clave configurada para verificar el token de ' + authConfig.gestorNombre);
  }
  if (!ok) throw new HttpError(401, 'Firma del token inválida');
  const payload = b64urlJson(p);
  const now = Math.floor(Date.now() / 1000);
  if (payload.exp && payload.exp < now) throw new HttpError(401, 'Token expirado');
  if (process.env.GESTOR_JWT_ISSUER && payload.iss !== process.env.GESTOR_JWT_ISSUER) throw new HttpError(401, 'Emisor del token no reconocido');
  if (process.env.GESTOR_JWT_AUDIENCE && payload.aud !== process.env.GESTOR_JWT_AUDIENCE) throw new HttpError(401, 'Audiencia del token no reconocida');
  return payload;
}

async function consultarUserinfo(token, cookie) {
  const url = process.env.GESTOR_USERINFO_URL;
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  if (cookie) headers.Cookie = cookie;
  if (process.env.GESTOR_API_KEY) headers['X-Api-Key'] = process.env.GESTOR_API_KEY;
  const r = await fetch(url, { headers, signal: AbortSignal.timeout(8000) });
  if (!r.ok) throw new HttpError(401, `${authConfig.gestorNombre} rechazó la credencial (HTTP ${r.status})`);
  const j = await r.json();
  return j.user ?? j.usuario ?? j.data ?? j;
}

function normalizarPerfil(p) {
  const id = String(p.id ?? p.sub ?? p.user_id ?? p.usuario_id ?? '');
  const email = String(p.email ?? p.correo ?? p.usuario ?? p.username ?? p.login ?? '').trim();
  const nombre = String(p.nombre ?? p.name ?? p.nombre_completo ?? p.full_name ?? email.split('@')[0] ?? 'Usuario').trim();
  const rolesAdmin = (process.env.GESTOR_ADMIN_ROLES || 'admin,administrador,superadmin').split(',').map(s => s.trim().toLowerCase());
  const rolesConsultor = (process.env.GESTOR_CONSULTOR_ROLES || 'consultor,auditor,gestor,docente').split(',').map(s => s.trim().toLowerCase());
  const rolesRaw = [].concat(p.rol ?? p.role ?? p.roles ?? p.perfil ?? []).map(x => String(typeof x === 'object' ? (x.name ?? x.nombre ?? '') : x).toLowerCase());
  let rol = 'usuario';
  if (rolesRaw.some(r => rolesAdmin.includes(r))) rol = 'admin';
  else if (rolesRaw.some(r => rolesConsultor.includes(r))) rol = 'consultor';
  if (!email) throw new HttpError(401, 'El perfil recibido de ' + authConfig.gestorNombre + ' no incluye correo electrónico');
  return { gestor_id: id || createHash('sha1').update(email).digest('hex'), email, nombre, rol };
}

export function upsertUsuarioGestor(perfil, { desdeSincronizacion = false } = {}) {
  const db = getDb();
  const p = normalizarPerfil(perfil);
  let u = db.prepare('SELECT * FROM usuarios WHERE (origen = ? AND gestor_id = ?) OR email = ?').get('gestor', p.gestor_id, p.email);
  if (!u) {
    const id = randomBytes(8).toString('hex');
    db.prepare('INSERT INTO usuarios (id, email, nombre, rol, origen, gestor_id) VALUES (?,?,?,?,?,?)').run(id, p.email, p.nombre, p.rol, 'gestor', p.gestor_id);
    u = db.prepare('SELECT * FROM usuarios WHERE id = ?').get(id);
    log(id, 'usuario.creado_desde_gestor', 'usuario', id, { email: p.email, rol: p.rol });
  } else {
    // Se sincronizan nombre y rol con el gestor salvo que el rol local sea admin asignado manualmente.
    const rol = (u.origen === 'local' && u.rol === 'admin') ? u.rol : p.rol;
    db.prepare('UPDATE usuarios SET nombre = ?, rol = ?, origen = ?, gestor_id = ? WHERE id = ?').run(p.nombre, rol, 'gestor', p.gestor_id, u.id);
    u = db.prepare('SELECT * FROM usuarios WHERE id = ?').get(u.id);
  }
  if (!u.activo && !desdeSincronizacion) throw new HttpError(403, 'El usuario está inactivo en esta herramienta');
  return u;
}

export async function autenticarConGestor({ token, cookieCompartida }) {
  if (!authConfig.gestorHabilitado && MODE === 'local') throw new HttpError(403, 'Modo local: integración con gestor deshabilitada');
  let perfil;
  if (process.env.GESTOR_USERINFO_URL) {
    perfil = await consultarUserinfo(token, cookieCompartida);
  } else if (token) {
    perfil = verificarJwt(token);
  } else {
    throw new HttpError(503, 'Configure GESTOR_USERINFO_URL o una clave JWT para validar credenciales de ' + authConfig.gestorNombre);
  }
  return upsertUsuarioGestor(perfil);
}

// Intento silencioso por cookie compartida del dominio (.proyectoia.org).
export async function intentarSsoPorCookie(req) {
  const name = process.env.GESTOR_SESSION_COOKIE;
  if (!name || !process.env.GESTOR_USERINFO_URL) return null;
  const cookies = parseCookies(req);
  if (!cookies[name]) return null;
  try {
    return await autenticarConGestor({ cookieCompartida: `${name}=${encodeURIComponent(cookies[name])}` });
  } catch { return null; }
}
