// Recoleccion de datos para el tablero. Pide a cada conector sus conjuntos de datos y los guarda en el portal.
// Solo lectura sobre las aplicaciones. Se ejecuta por intervalo o a peticion del administrador.
import { db, auditar } from './db.js';
import { config } from './config.js';
import { exportar, estadoConector } from './conector.js';

export async function recolectarApp(app) {
  const resultados = [];
  let estado;
  try {
    estado = await estadoConector(app);
  } catch (e) {
    db.prepare('INSERT INTO recolecciones (app, conjunto, filas, datos, estado, detalle) VALUES (?, ?, 0, ?, ?, ?)')
      .run(app.clave, '_estado', '[]', 'error', e.message);
    auditar('recoleccion_error', { app: app.clave, detalle: e.message });
    return [{ conjunto: '_estado', estado: 'error', detalle: e.message }];
  }
  const conjuntos = Array.isArray(estado.conjuntos) ? estado.conjuntos : [];
  for (const conjunto of conjuntos) {
    try {
      const r = await exportar(app, conjunto);
      const filas = Array.isArray(r.filas) ? r.filas : [];
      db.prepare('INSERT INTO recolecciones (app, conjunto, filas, datos, estado, detalle) VALUES (?, ?, ?, ?, ?, ?)')
        .run(app.clave, conjunto, filas.length, JSON.stringify(filas), 'ok', r.descripcion || null);
      resultados.push({ conjunto, estado: 'ok', filas: filas.length });
    } catch (e) {
      db.prepare('INSERT INTO recolecciones (app, conjunto, filas, datos, estado, detalle) VALUES (?, ?, 0, ?, ?, ?)')
        .run(app.clave, conjunto, '[]', 'error', e.message);
      auditar('recoleccion_error', { app: app.clave, detalle: `${conjunto}: ${e.message}` });
      resultados.push({ conjunto, estado: 'error', detalle: e.message });
    }
  }
  // Conserva solo las diez ultimas recolecciones por conjunto para que la base no crezca sin control.
  db.prepare(`DELETE FROM recolecciones WHERE app = ? AND id NOT IN (
      SELECT id FROM recolecciones r2 WHERE r2.app = recolecciones.app AND r2.conjunto = recolecciones.conjunto ORDER BY recolectado_en DESC LIMIT 10)`).run(app.clave);
  auditar('recoleccion', { app: app.clave, detalle: JSON.stringify(resultados) });
  return resultados;
}

export async function recolectarTodo() {
  const salida = {};
  for (const app of config.apps) salida[app.clave] = await recolectarApp(app);
  return salida;
}

export function programarRecoleccion() {
  if (!config.minutosRecoleccion) return;
  const ms = config.minutosRecoleccion * 60 * 1000;
  setTimeout(() => recolectarTodo().catch(() => {}), 20000);
  setInterval(() => recolectarTodo().catch(() => {}), ms);
}

// Resumen para el tablero a partir de la ultima recoleccion exitosa de cada conjunto.
export function resumenTablero() {
  const apps = config.apps.map((app) => {
    const conjuntos = db.prepare(`SELECT conjunto, MAX(recolectado_en) AS fecha FROM recolecciones WHERE app = ? AND estado = 'ok' AND conjunto != '_estado' GROUP BY conjunto`).all(app.clave);
    const detalle = conjuntos.map((c) => {
      const r = db.prepare('SELECT * FROM recolecciones WHERE app = ? AND conjunto = ? AND estado = ? ORDER BY recolectado_en DESC LIMIT 1').get(app.clave, c.conjunto, 'ok');
      const filas = JSON.parse(r.datos);
      return { conjunto: c.conjunto, fecha: r.recolectado_en, filas: r.filas, descripcion: r.detalle, muestra: filas.slice(0, 5), columnas: filas.length ? Object.keys(filas[0]) : [], series: serieMensual(filas) };
    });
    const ultimoError = db.prepare('SELECT * FROM recolecciones WHERE app = ? AND estado = ? ORDER BY recolectado_en DESC LIMIT 1').get(app.clave, 'error');
    return { app, conjuntos: detalle, ultimoError };
  });
  return apps;
}

// Si las filas traen una columna de fecha (fecha, creado_en, created_at), agrupa por mes para el grafico.
function serieMensual(filas) {
  if (!filas.length) return null;
  const col = ['fecha', 'creado_en', 'created_at', 'fecha_registro', 'registrado_en'].find((c) => c in filas[0]);
  if (!col) return null;
  const m = new Map();
  for (const f of filas) {
    const d = String(f[col] || '').slice(0, 7);
    if (!/^\d{4}-\d{2}$/.test(d)) continue;
    m.set(d, (m.get(d) || 0) + 1);
  }
  if (!m.size) return null;
  return [...m.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-12).map(([mes, n]) => ({ mes, n }));
}
