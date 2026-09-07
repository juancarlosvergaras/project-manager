// Cliente del conector desplegado en cada aplicacion. Todas las llamadas van firmadas con HMAC-SHA256
// usando el secreto compartido de la aplicacion. El portal nunca accede a las bases de datos de las aplicaciones.
import crypto from 'node:crypto';
import { config } from './config.js';

const TOLERANCIA_SEG = 300;

export function appPorClave(clave) {
  return config.apps.find((a) => a.clave === clave);
}

function firmar(secreto, partes) {
  return crypto.createHmac('sha256', secreto).update(partes.join('\n')).digest('hex');
}

// Llama a una accion del conector con un cuerpo JSON firmado.
export async function llamarConector(app, accion, cuerpo = {}) {
  const ts = String(Math.floor(Date.now() / 1000));
  const nonce = crypto.randomBytes(12).toString('hex');
  const body = JSON.stringify({ accion, ...cuerpo });
  const firma = firmar(app.secreto, ['POST', accion, ts, nonce, body]);
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 15000);
  try {
    const res = await fetch(app.conector, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Obs-Timestamp': ts,
        'X-Obs-Nonce': nonce,
        'X-Obs-Signature': firma,
        'X-Obs-Portal': config.urlPublica,
      },
      body,
      signal: ctrl.signal,
    });
    const texto = await res.text();
    let json;
    try { json = JSON.parse(texto); } catch { throw new Error(`Respuesta no válida del conector (${res.status}): ${texto.slice(0, 120)}`); }
    if (!res.ok) throw new Error(json.error || `Error ${res.status} del conector`);
    return json;
  } finally {
    clearTimeout(t);
  }
}

// Verifica usuario y clave contra la aplicacion. La aplicacion hace la comprobacion con su propio codigo.
export async function verificarCredenciales(app, usuario, clave) {
  return llamarConector(app, 'verificar', { usuario, clave });
}

// Token de un solo uso para abrir la aplicacion con la sesion ya iniciada.
export function crearTokenSso(app, { correo, idExterno, usuarioExterno, jti }) {
  const payload = {
    app: app.clave,
    correo,
    id_externo: idExterno,
    usuario_externo: usuarioExterno,
    jti,
    exp: Math.floor(Date.now() / 1000) + 60,
    portal: config.urlPublica,
  };
  const datos = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const firma = firmar(app.secreto, ['SSO', datos]);
  return `${datos}.${firma}`;
}

export function urlSso(app, token) {
  const base = app.conectorPublico || app.conector;
  const sep = base.includes('?') ? '&' : '?';
  return `${base}${sep}accion=sso&token=${encodeURIComponent(token)}`;
}

// Pide un conjunto de datos de la aplicacion para el tablero.
export async function exportar(app, conjunto, desde = null) {
  return llamarConector(app, 'exportar', { conjunto, desde });
}

export async function estadoConector(app) {
  return llamarConector(app, 'estado', {});
}

export { TOLERANCIA_SEG };
