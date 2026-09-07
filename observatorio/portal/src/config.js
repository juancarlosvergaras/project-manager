// Carga la configuracion desde variables de entorno y, si existe, desde el archivo .env.
import fs from 'node:fs';
import path from 'node:path';

function cargarEnv(ruta) {
  if (!fs.existsSync(ruta)) return;
  for (const linea of fs.readFileSync(ruta, 'utf8').split('\n')) {
    const l = linea.trim();
    if (!l || l.startsWith('#')) continue;
    const i = l.indexOf('=');
    if (i < 0) continue;
    const k = l.slice(0, i).trim();
    const v = l.slice(i + 1).trim().replace(/^"(.*)"$/, '$1');
    if (process.env[k] === undefined) process.env[k] = v;
  }
}
cargarEnv(path.resolve(process.cwd(), '.env'));

const env = process.env;

function apps() {
  const claves = new Set();
  for (const k of Object.keys(env)) {
    const m = /^APP_([A-Z0-9]+)_/.exec(k);
    if (m) claves.add(m[1]);
  }
  return [...claves]
    .map((c) => ({
      clave: c.toLowerCase(),
      nombre: env[`APP_${c}_NOMBRE`] || c,
      url: (env[`APP_${c}_URL`] || '').replace(/\/$/, ''),
      conector: env[`APP_${c}_CONECTOR`] || '',
      secreto: env[`APP_${c}_SECRETO`] || '',
      orden: Number(env[`APP_${c}_ORDEN`] || 99),
    }))
    .filter((a) => a.conector && a.secreto)
    .sort((a, b) => a.orden - b.orden);
}

export const config = {
  puerto: Number(env.PUERTO || 8100),
  urlPublica: (env.URL_PUBLICA || `http://localhost:${env.PUERTO || 8100}`).replace(/\/$/, ''),
  claveSesion: env.CLAVE_SESION || 'clave-de-desarrollo-no-usar-en-produccion',
  rutaBd: env.RUTA_BD || './datos/portal.sqlite',
  horasSesion: Number(env.HORAS_SESION || 10),
  minutosRecoleccion: Number(env.MINUTOS_RECOLECCION || 60),
  administradores: (env.ADMINISTRADORES || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean),
  apps: apps(),
  produccion: env.NODE_ENV === 'production',
};

if (config.produccion && config.claveSesion.length < 32) {
  throw new Error('CLAVE_SESION debe tener al menos 32 caracteres en produccion.');
}
