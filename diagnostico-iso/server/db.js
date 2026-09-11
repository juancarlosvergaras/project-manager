// Capa de datos: SQLite embebido (node:sqlite), esquema, migraciones y datos semilla.
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Escala de valoración. "No aplica" no suma ni resta: se excluye del denominador del cumplimiento.
export const VALORACIONES = {
  cumple:         { etiqueta: 'Cumple',              peso: 1.0, orden: 1, aplica: true },
  cumple_parcial: { etiqueta: 'Cumple parcialmente', peso: 0.5, orden: 2, aplica: true },
  no_cumple:      { etiqueta: 'No cumple',           peso: 0.0, orden: 3, aplica: true },
  no_aplica:      { etiqueta: 'No aplica',           peso: 0.0, orden: 4, aplica: false },
};

// Roles globales de la herramienta y sus capacidades.
export const ROLES = {
  admin:   { etiqueta: 'Administrador', descripcion: 'Todo: organizaciones, usuarios, cuestionario, versiones e indicadores de todas las organizaciones.' },
  editor:  { etiqueta: 'Editor',        descripcion: 'En sus organizaciones: ve indicadores e históricos, crea, cierra y elimina versiones y diligencia el cuestionario. No modifica el cuestionario.' },
  auditor: { etiqueta: 'Auditor',       descripcion: 'En sus organizaciones: ve la versión en diligenciamiento y la alimenta con valoraciones y textos.' },
  usuario: { etiqueta: 'Usuario',       descripcion: 'En sus organizaciones: consulta el tablero de resultados y genera informes.' },
};
export const CAPACIDADES = {
  admin:   ['ver_indicadores', 'diligenciar', 'gestionar_versiones', 'gestionar_organizaciones', 'gestionar_usuarios', 'editar_instrumento', 'ver_todas'],
  editor:  ['ver_indicadores', 'diligenciar', 'gestionar_versiones'],
  auditor: ['diligenciar'],
  usuario: ['ver_indicadores'],
};
export function puede(usuario, capacidad) { return !!usuario && (CAPACIDADES[usuario.rol] || []).includes(capacidad); }

const SCHEMA = `
CREATE TABLE IF NOT EXISTS usuarios (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  nombre TEXT NOT NULL,
  rol TEXT NOT NULL DEFAULT 'usuario',            -- admin | editor | auditor | usuario
  rol_manual INTEGER NOT NULL DEFAULT 0,          -- 1: el rol lo fijó un administrador aquí y no se sincroniza desde el gestor
  origen TEXT NOT NULL DEFAULT 'local',           -- local | gestor
  gestor_id TEXT,
  password_hash TEXT,
  activo INTEGER NOT NULL DEFAULT 1,
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  ultimo_acceso TEXT
);
CREATE TABLE IF NOT EXISTS sesiones (
  id TEXT PRIMARY KEY,
  usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  expira_en TEXT NOT NULL,
  gestor_cookie TEXT
);
CREATE TABLE IF NOT EXISTS organizaciones (
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  sigla TEXT,
  nit TEXT,
  sector TEXT,
  ciudad TEXT,
  pais TEXT DEFAULT 'Colombia',
  contacto_nombre TEXT,
  contacto_email TEXT,
  descripcion TEXT,
  creado_por TEXT REFERENCES usuarios(id),
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  activa INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS organizacion_miembros (
  organizacion_id TEXT NOT NULL REFERENCES organizaciones(id) ON DELETE CASCADE,
  usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  rol TEXT NOT NULL DEFAULT 'editor',             -- editor | lector
  asignado_en TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (organizacion_id, usuario_id)
);
CREATE TABLE IF NOT EXISTS instrumentos (
  id TEXT PRIMARY KEY,
  clave TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  version TEXT NOT NULL,
  descripcion TEXT,
  activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS instrumento_items (
  id TEXT PRIMARY KEY,
  instrumento_id TEXT NOT NULL REFERENCES instrumentos(id) ON DELETE CASCADE,
  codigo TEXT NOT NULL,
  capitulo INTEGER NOT NULL,
  capitulo_nombre TEXT NOT NULL,
  numeral TEXT NOT NULL,
  pregunta TEXT NOT NULL,
  responsable_sugerido TEXT,
  orden INTEGER NOT NULL,
  activo INTEGER NOT NULL DEFAULT 1,
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (instrumento_id, codigo)
);
-- Preguntas que componen cada versión (instantánea): al quitar o agregar preguntas del cuestionario,
-- las versiones cerradas conservan las suyas y las abiertas y nuevas usan el cuestionario vigente.
CREATE TABLE IF NOT EXISTS diagnostico_items (
  diagnostico_id TEXT NOT NULL REFERENCES diagnosticos(id) ON DELETE CASCADE,
  item_id TEXT NOT NULL REFERENCES instrumento_items(id),
  PRIMARY KEY (diagnostico_id, item_id)
);
CREATE TABLE IF NOT EXISTS diagnosticos (
  id TEXT PRIMARY KEY,
  organizacion_id TEXT NOT NULL REFERENCES organizaciones(id) ON DELETE CASCADE,
  instrumento_id TEXT NOT NULL REFERENCES instrumentos(id),
  version_numero INTEGER NOT NULL,
  titulo TEXT NOT NULL,
  fecha TEXT NOT NULL,
  notas TEXT,
  estado TEXT NOT NULL DEFAULT 'en_diligenciamiento', -- en_diligenciamiento | cerrado
  base_version_id TEXT REFERENCES diagnosticos(id),
  creado_por TEXT REFERENCES usuarios(id),
  creado_en TEXT NOT NULL DEFAULT (datetime('now')),
  cerrado_en TEXT,
  cerrado_por TEXT REFERENCES usuarios(id),
  UNIQUE (organizacion_id, version_numero)
);
CREATE TABLE IF NOT EXISTS respuestas (
  diagnostico_id TEXT NOT NULL REFERENCES diagnosticos(id) ON DELETE CASCADE,
  item_id TEXT NOT NULL REFERENCES instrumento_items(id),
  valoracion TEXT,                                -- cumple | cumple_parcial | no_cumple | no_aplica | NULL
  estado_origen TEXT,
  evidencia TEXT,
  observaciones TEXT,
  responsable TEXT,
  actualizado_en TEXT NOT NULL DEFAULT (datetime('now')),
  actualizado_por TEXT REFERENCES usuarios(id),
  PRIMARY KEY (diagnostico_id, item_id)
);
CREATE TABLE IF NOT EXISTS bitacora (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL DEFAULT (datetime('now')),
  usuario_id TEXT,
  accion TEXT NOT NULL,
  entidad TEXT,
  entidad_id TEXT,
  detalle TEXT
);
CREATE INDEX IF NOT EXISTS idx_diag_org ON diagnosticos(organizacion_id, version_numero);
CREATE INDEX IF NOT EXISTS idx_resp_diag ON respuestas(diagnostico_id);
`;

let db;

export function openDb(path = process.env.DB_PATH || join(__dirname, '..', 'data', 'diagnostico.sqlite')) {
  if (db) return db;
  if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
  db = new DatabaseSync(path);
  db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000;');
  db.exec(SCHEMA);
  migrar(db);
  seed(db);
  return db;
}

export function getDb() { if (!db) return openDb(); return db; }
export function closeDb() { if (db) { db.close(); db = undefined; } }

export function log(usuarioId, accion, entidad, entidadId, detalle) {
  getDb().prepare('INSERT INTO bitacora (usuario_id, accion, entidad, entidad_id, detalle) VALUES (?,?,?,?,?)')
    .run(usuarioId ?? null, accion, entidad ?? null, entidadId ?? null, detalle ? JSON.stringify(detalle) : null);
}

// ---------- Migraciones sobre bases existentes ----------
function migrar(db) {
  const cols = db.prepare('PRAGMA table_info(sesiones)').all().map(c => c.name);
  if (!cols.includes('gestor_cookie')) db.exec('ALTER TABLE sesiones ADD COLUMN gestor_cookie TEXT');
  const colsU = db.prepare('PRAGMA table_info(usuarios)').all().map(c => c.name);
  if (!colsU.includes('cargo')) db.exec('ALTER TABLE usuarios ADD COLUMN cargo TEXT');
  if (!colsU.includes('sincronizado_en')) db.exec('ALTER TABLE usuarios ADD COLUMN sincronizado_en TEXT');
  if (!colsU.includes('rol_manual')) db.exec('ALTER TABLE usuarios ADD COLUMN rol_manual INTEGER NOT NULL DEFAULT 0');
  const colsI = db.prepare('PRAGMA table_info(instrumento_items)').all().map(c => c.name);
  if (!colsI.includes('activo')) db.exec('ALTER TABLE instrumento_items ADD COLUMN activo INTEGER NOT NULL DEFAULT 1');
  if (!colsI.includes('creado_en')) db.exec("ALTER TABLE instrumento_items ADD COLUMN creado_en TEXT NOT NULL DEFAULT ''");
  // Rol "consultor" (modelo anterior) pasa a "editor"
  db.exec("UPDATE usuarios SET rol = 'editor' WHERE rol = 'consultor'");
  // Escala anterior: "sin_evidencia" (sin evidencia verificable) equivale a "no cumple"; se conserva la etiqueta de origen
  db.exec("UPDATE respuestas SET estado_origen = COALESCE(estado_origen, 'Sin evidencia'), valoracion = 'no_cumple' WHERE valoracion = 'sin_evidencia'");
  db.exec("UPDATE organizacion_miembros SET rol = (SELECT rol FROM usuarios u WHERE u.id = organizacion_miembros.usuario_id) WHERE rol NOT IN ('editor','auditor','usuario') OR rol IS NULL");
  // Instantánea de preguntas para versiones creadas antes de existir diagnostico_items
  db.exec(`INSERT OR IGNORE INTO diagnostico_items (diagnostico_id, item_id)
           SELECT d.id, i.id FROM diagnosticos d JOIN instrumento_items i ON i.instrumento_id = d.instrumento_id
           WHERE NOT EXISTS (SELECT 1 FROM diagnostico_items x WHERE x.diagnostico_id = d.id)`);
}

// ---------- Datos semilla ----------
function seed(db) {
  seedInstrumento(db);
  seedCasoHuc(db);
}

export function seedInstrumento(db) {
  const file = join(__dirname, 'seed', 'instrumento-iso9001.json');
  if (!existsSync(file)) return;
  const inst = JSON.parse(readFileSync(file, 'utf8'));
  const existente = db.prepare('SELECT id FROM instrumentos WHERE clave = ?').get(inst.clave);
  if (existente) return existente.id;
  const id = randomUUID();
  db.exec('BEGIN');
  try {
    db.prepare('INSERT INTO instrumentos (id, clave, nombre, version, descripcion) VALUES (?,?,?,?,?)')
      .run(id, inst.clave, inst.nombre, inst.version, inst.descripcion);
    const ins = db.prepare('INSERT INTO instrumento_items (id, instrumento_id, codigo, capitulo, capitulo_nombre, numeral, pregunta, responsable_sugerido, orden) VALUES (?,?,?,?,?,?,?,?,?)');
    for (const it of inst.items) {
      ins.run(randomUUID(), id, it.codigo, it.capitulo, it.capitulo_nombre, it.numeral, it.pregunta, it.responsable_sugerido ?? null, it.orden);
    }
    db.exec('COMMIT');
  } catch (e) { db.exec('ROLLBACK'); throw e; }
  return id;
}

export function seedCasoHuc(db) {
  const file = join(__dirname, 'seed', 'caso-huc.json');
  if (!existsSync(file)) return;
  const caso = JSON.parse(readFileSync(file, 'utf8'));
  const yaExiste = db.prepare('SELECT id FROM organizaciones WHERE nombre = ?').get(caso.organizacion.nombre);
  if (yaExiste) return yaExiste.id;
  const inst = db.prepare('SELECT id FROM instrumentos WHERE clave = ?').get(caso.diagnostico.instrumento);
  if (!inst) return;
  const orgId = randomUUID();
  const diagId = randomUUID();
  db.exec('BEGIN');
  try {
    const o = caso.organizacion;
    db.prepare('INSERT INTO organizaciones (id, nombre, sigla, sector, ciudad, pais, descripcion) VALUES (?,?,?,?,?,?,?)')
      .run(orgId, o.nombre, o.sigla ?? null, o.sector ?? null, o.ciudad ?? null, o.pais ?? 'Colombia', o.descripcion ?? null);
    const d = caso.diagnostico;
    db.prepare(`INSERT INTO diagnosticos (id, organizacion_id, instrumento_id, version_numero, titulo, fecha, notas, estado, cerrado_en)
                VALUES (?,?,?,?,?,?,?,?,?)`)
      .run(diagId, orgId, inst.id, 1, d.titulo, d.fecha, d.notas ?? null, d.estado ?? 'cerrado', d.estado === 'cerrado' ? d.fecha + ' 00:00:00' : null);
    const item = db.prepare('SELECT id FROM instrumento_items WHERE instrumento_id = ? AND codigo = ?');
    const ins = db.prepare('INSERT INTO respuestas (diagnostico_id, item_id, valoracion, estado_origen, evidencia, observaciones, responsable) VALUES (?,?,?,?,?,?,?)');
    for (const r of caso.respuestas) {
      const it = item.get(inst.id, r.codigo);
      if (!it) continue;
      const val = r.valoracion === 'sin_evidencia' ? 'no_cumple' : r.valoracion;
      ins.run(diagId, it.id, val, r.estado_origen ?? null, r.evidencia ?? null, r.observaciones ?? null, r.responsable ?? null);
    }
    db.prepare('INSERT OR IGNORE INTO diagnostico_items (diagnostico_id, item_id) SELECT ?, id FROM instrumento_items WHERE instrumento_id = ?').run(diagId, inst.id);
    db.exec('COMMIT');
  } catch (e) { db.exec('ROLLBACK'); throw e; }
  return orgId;
}
