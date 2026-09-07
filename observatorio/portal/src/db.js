// Base de datos propia del portal. Nunca escribe en las bases de datos de las aplicaciones.
import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';
import { config } from './config.js';

fs.mkdirSync(path.dirname(path.resolve(config.rutaBd)), { recursive: true });
export const db = new DatabaseSync(config.rutaBd);
db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');

db.exec(`
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY,
  correo TEXT UNIQUE NOT NULL,
  nombre TEXT,
  rol TEXT NOT NULL DEFAULT 'usuario',
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  ultimo_ingreso TEXT
);
CREATE TABLE IF NOT EXISTS identidades (
  id INTEGER PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  app TEXT NOT NULL,
  id_externo TEXT NOT NULL,
  usuario_externo TEXT,
  rol_externo TEXT,
  verificado_en TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(app, id_externo)
);
CREATE TABLE IF NOT EXISTS sesiones (
  id TEXT PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  creada_en TEXT NOT NULL DEFAULT (datetime('now')),
  expira_en TEXT NOT NULL,
  ip TEXT,
  agente TEXT
);
CREATE TABLE IF NOT EXISTS tokens_sso (
  jti TEXT PRIMARY KEY,
  app TEXT NOT NULL,
  usuario_id INTEGER NOT NULL,
  emitido_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS recolecciones (
  id INTEGER PRIMARY KEY,
  app TEXT NOT NULL,
  conjunto TEXT NOT NULL,
  filas INTEGER NOT NULL,
  datos TEXT NOT NULL,
  estado TEXT NOT NULL,
  detalle TEXT,
  recolectado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_recolecciones ON recolecciones(app, conjunto, recolectado_en DESC);
CREATE TABLE IF NOT EXISTS auditoria (
  id INTEGER PRIMARY KEY,
  evento TEXT NOT NULL,
  usuario_id INTEGER,
  app TEXT,
  detalle TEXT,
  ip TEXT,
  ocurrido_en TEXT NOT NULL DEFAULT (datetime('now'))
);
`);

export function auditar(evento, { usuarioId = null, app = null, detalle = null, ip = null } = {}) {
  db.prepare('INSERT INTO auditoria (evento, usuario_id, app, detalle, ip) VALUES (?, ?, ?, ?, ?)')
    .run(evento, usuarioId, app, detalle ? String(detalle).slice(0, 500) : null, ip);
}

export function ultimaRecoleccion(app, conjunto) {
  return db.prepare('SELECT * FROM recolecciones WHERE app = ? AND conjunto = ? AND estado = ? ORDER BY recolectado_en DESC LIMIT 1')
    .get(app, conjunto, 'ok');
}
