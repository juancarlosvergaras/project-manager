// Ingreso unificado. El usuario escribe el usuario y la clave que ya usa en alguna de las aplicaciones.
// El portal las verifica contra los conectores en el orden configurado, crea o actualiza la cuenta del portal,
// vincula la identidad externa y abre la sesion. Las claves no se guardan en el portal.
import crypto from 'node:crypto';
import { db, auditar } from './db.js';
import { config } from './config.js';
import { verificarCredenciales } from './conector.js';

const intentos = new Map(); // control simple de intentos por usuario e IP
const MAX_INTENTOS = 8;
const VENTANA_MS = 15 * 60 * 1000;

function bloqueado(clave) {
  const r = intentos.get(clave);
  if (!r) return false;
  if (Date.now() - r.inicio > VENTANA_MS) { intentos.delete(clave); return false; }
  return r.n >= MAX_INTENTOS;
}
function registrarIntento(clave) {
  const r = intentos.get(clave);
  if (!r || Date.now() - r.inicio > VENTANA_MS) intentos.set(clave, { n: 1, inicio: Date.now() });
  else r.n += 1;
}

export async function ingresar({ usuario, clave, ip, agente }) {
  usuario = String(usuario || '').trim().toLowerCase();
  if (!usuario || !clave) return { ok: false, error: 'Escriba su usuario y su clave.' };
  const llave = `${usuario}|${ip}`;
  if (bloqueado(llave)) return { ok: false, error: 'Demasiados intentos. Espere quince minutos e intente de nuevo.' };

  const errores = [];
  for (const app of config.apps) {
    let r;
    try {
      r = await verificarCredenciales(app, usuario, clave);
    } catch (e) {
      errores.push(`${app.nombre}: ${e.message}`);
      auditar('conector_error', { app: app.clave, detalle: e.message, ip });
      continue;
    }
    if (!r.ok) continue;

    const correo = String(r.correo || (usuario.includes('@') ? usuario : '')).toLowerCase();
    if (!correo) { errores.push(`${app.nombre}: la aplicación no devolvió un correo para vincular la cuenta.`); continue; }

    const tx = db.prepare('SELECT * FROM usuarios WHERE correo = ?').get(correo);
    let usuarioId;
    if (tx) {
      usuarioId = tx.id;
      db.prepare('UPDATE usuarios SET nombre = COALESCE(?, nombre), ultimo_ingreso = datetime(\'now\') WHERE id = ?').run(r.nombre || null, usuarioId);
    } else {
      const rol = config.administradores.includes(correo) ? 'administrador' : 'usuario';
      usuarioId = db.prepare('INSERT INTO usuarios (correo, nombre, rol, ultimo_ingreso) VALUES (?, ?, ?, datetime(\'now\'))')
        .run(correo, r.nombre || null, rol).lastInsertRowid;
      auditar('usuario_creado', { usuarioId, app: app.clave, ip });
    }
    db.prepare(`INSERT INTO identidades (usuario_id, app, id_externo, usuario_externo, rol_externo)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(app, id_externo) DO UPDATE SET usuario_id = excluded.usuario_id, usuario_externo = excluded.usuario_externo,
                rol_externo = excluded.rol_externo, verificado_en = datetime('now')`)
      .run(usuarioId, app.clave, String(r.id), r.usuario || usuario, r.rol || null);

    const sesion = crearSesion(usuarioId, ip, agente);
    auditar('ingreso', { usuarioId, app: app.clave, ip });
    intentos.delete(llave);
    return { ok: true, sesion, usuarioId, app: app.clave };
  }

  registrarIntento(llave);
  auditar('ingreso_fallido', { detalle: `${usuario} · ${errores.join(' | ') || 'credenciales no válidas'}`, ip });
  if (errores.length === config.apps.length && config.apps.length) {
    return { ok: false, error: 'No fue posible contactar las aplicaciones para verificar su clave. Intente en unos minutos.' };
  }
  return { ok: false, error: 'Usuario o clave no válidos en las aplicaciones conectadas.' };
}

export function crearSesion(usuarioId, ip, agente) {
  const id = crypto.randomBytes(32).toString('base64url');
  const expira = new Date(Date.now() + config.horasSesion * 3600 * 1000).toISOString();
  db.prepare('INSERT INTO sesiones (id, usuario_id, expira_en, ip, agente) VALUES (?, ?, ?, ?, ?)').run(id, usuarioId, expira, ip, (agente || '').slice(0, 200));
  return { id, expira };
}

export function firmarCookie(valor) {
  const f = crypto.createHmac('sha256', config.claveSesion).update(valor).digest('base64url');
  return `${valor}.${f}`;
}
export function leerCookieFirmada(valorFirmado) {
  if (!valorFirmado) return null;
  const i = valorFirmado.lastIndexOf('.');
  if (i < 0) return null;
  const valor = valorFirmado.slice(0, i), f = valorFirmado.slice(i + 1);
  const esperado = crypto.createHmac('sha256', config.claveSesion).update(valor).digest('base64url');
  if (f.length !== esperado.length || !crypto.timingSafeEqual(Buffer.from(f), Buffer.from(esperado))) return null;
  return valor;
}

export function usuarioDeSesion(sesionId) {
  if (!sesionId) return null;
  const s = db.prepare('SELECT s.*, u.correo, u.nombre, u.rol FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id WHERE s.id = ?').get(sesionId);
  if (!s) return null;
  if (new Date(s.expira_en) < new Date()) { db.prepare('DELETE FROM sesiones WHERE id = ?').run(sesionId); return null; }
  return { id: s.usuario_id, correo: s.correo, nombre: s.nombre, rol: s.rol, sesionId: s.id };
}

export function cerrarSesion(sesionId) {
  if (sesionId) db.prepare('DELETE FROM sesiones WHERE id = ?').run(sesionId);
}

export function identidades(usuarioId) {
  return db.prepare('SELECT * FROM identidades WHERE usuario_id = ?').all(usuarioId);
}
