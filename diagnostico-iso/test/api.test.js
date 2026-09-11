// Pruebas de integración de la API sobre una base de datos en memoria y un servidor efímero.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 3999 + Math.floor(Math.random() * 500);
const base = `http://127.0.0.1:${PORT}`;
let proc, cookie = '';

async function call(path, { method = 'GET', body, raw = false } = {}) {
  const r = await fetch(base + path, { method, headers: { 'Content-Type': 'application/json', Cookie: cookie }, body: body ? JSON.stringify(body) : undefined, redirect: 'manual' });
  const sc = r.headers.get('set-cookie'); if (sc) cookie = sc.split(';')[0];
  if (raw) return r;
  const data = await r.json().catch(() => ({}));
  return { status: r.status, data };
}

before(async () => {
  proc = spawn(process.execPath, ['--no-warnings=ExperimentalWarning', 'server/index.js'], { cwd: root, env: { ...process.env, PORT: String(PORT), AUTH_MODE: 'local', DB_PATH: ':memory:', SESSION_SECRET: 'prueba', ADMIN_PASSWORD: 'clave-prueba-123' }, stdio: ['ignore', 'pipe', 'pipe'] });
  await new Promise((res, rej) => { proc.stdout.on('data', d => { if (String(d).includes('escuchando')) res(); }); proc.stderr.on('data', d => process.stderr.write(d)); proc.on('exit', c => rej(new Error('servidor terminó ' + c))); });
});
after(() => proc.kill());

test('rechaza acceso sin sesión y acepta credenciales locales', async () => {
  assert.equal((await call('/api/organizaciones')).status, 401);
  const bad = await call('/api/auth/local/login', { method: 'POST', body: { email: 'admin@proyectoia.org', password: 'x' } });
  assert.equal(bad.status, 401);
  const ok = await call('/api/auth/local/login', { method: 'POST', body: { email: 'admin@proyectoia.org', password: 'clave-prueba-123' } });
  assert.equal(ok.status, 200); assert.equal(ok.data.usuario.rol, 'admin');
});

test('el caso HUC viene precargado con 98 respuestas y sus indicadores', async () => {
  const { data } = await call('/api/organizaciones');
  const huc = data.organizaciones.find(o => o.sigla === 'HUC');
  assert.ok(huc, 'existe la organización HUC');
  assert.equal(huc.ultimo_diagnostico.estado, 'cerrado');
  const ind = await call(`/api/diagnosticos/${huc.ultimo_diagnostico.id}/indicadores`);
  assert.equal(ind.data.indicadores.total_items, 98);
  assert.equal(ind.data.indicadores.cumplimiento, 13.8);
  assert.deepEqual(ind.data.indicadores.conteo, { cumple: 0, cumple_parcial: 27, no_cumple: 9, sin_evidencia: 62, sin_valorar: 0 });
  const det = await call(`/api/diagnosticos/${huc.ultimo_diagnostico.id}`);
  assert.equal(det.data.items.filter(i => i.respuesta?.estado_origen === 'Antecedente por verificar').length, 15);
  assert.equal(det.data.editable, false);
});

test('flujo completo: organización, asignación de usuario, versión, respuestas, cierre, histórico y comparación', async () => {
  const org = await call('/api/organizaciones', { method: 'POST', body: { nombre: 'Universidad de Prueba', sigla: 'UP', sector: 'Educación' } });
  assert.equal(org.status, 201);
  const m = await call(`/api/organizaciones/${org.data.id}/miembros`, { method: 'POST', body: { email: 'evaluador@prueba.org', nombre: 'Evaluador', password: 'clave-evaluador', rol: 'editor' } });
  assert.equal(m.status, 201);
  const v1 = await call(`/api/organizaciones/${org.data.id}/diagnosticos`, { method: 'POST', body: { titulo: 'Línea base' } });
  assert.equal(v1.status, 201); assert.equal(v1.data.version_numero, 1);
  const dup = await call(`/api/organizaciones/${org.data.id}/diagnosticos`, { method: 'POST', body: {} });
  assert.equal(dup.status, 409, 'no permite dos versiones abiertas');
  const det = await call(`/api/diagnosticos/${v1.data.id}`);
  const [i1, i2] = det.data.items;
  const r1 = await call(`/api/diagnosticos/${v1.data.id}/respuestas/${i1.id}`, { method: 'PUT', body: { valoracion: 'cumple', evidencia: 'Acta 01' } });
  assert.equal(r1.status, 200); assert.equal(r1.data.resumen.conteo.cumple, 1);
  const r2 = await call(`/api/diagnosticos/${v1.data.id}/respuestas/${i2.id}`, { method: 'PUT', body: { valoracion: 'invalida' } });
  assert.equal(r2.status, 400);
  await call(`/api/diagnosticos/${v1.data.id}/respuestas/${i2.id}`, { method: 'PUT', body: { valoracion: 'cumple_parcial' } });
  const cierre = await call(`/api/diagnosticos/${v1.data.id}/cerrar`, { method: 'POST' });
  assert.equal(cierre.status, 200);
  const bloqueado = await call(`/api/diagnosticos/${v1.data.id}/respuestas/${i1.id}`, { method: 'PUT', body: { valoracion: 'no_cumple' } });
  assert.equal(bloqueado.status, 409, 'versión cerrada no se edita');
  const v2 = await call(`/api/organizaciones/${org.data.id}/diagnosticos`, { method: 'POST', body: { desde_version_id: v1.data.id, modo_copia: 'completa' } });
  assert.equal(v2.data.version_numero, 2);
  await call(`/api/diagnosticos/${v2.data.id}/respuestas/${i2.id}`, { method: 'PUT', body: { valoracion: 'cumple' } });
  const h = await call(`/api/organizaciones/${org.data.id}/historico`);
  assert.equal(h.data.historico.length, 2);
  assert.ok(h.data.historico[1].cumplimiento > h.data.historico[0].cumplimiento);
  const c = await call(`/api/diagnosticos/${v2.data.id}/comparar/${v1.data.id}`);
  assert.equal(c.data.cambios.length, 1);
  assert.equal(c.data.cambios[0].despues, 'cumple');
  const csv = await call(`/api/diagnosticos/${v2.data.id}/export.csv`, { raw: true });
  assert.equal(csv.status, 200); assert.match(await csv.text(), /ISO-001/);

  // El evaluador solo ve su organización
  const adminCookie = cookie; cookie = '';
  await call('/api/auth/local/login', { method: 'POST', body: { email: 'evaluador@prueba.org', password: 'clave-evaluador' } });
  const mias = await call('/api/organizaciones');
  assert.deepEqual(mias.data.organizaciones.map(o => o.sigla), ['UP']);
  const huc = await call('/api/organizaciones');
  assert.equal((await call('/api/usuarios')).status, 403);
  cookie = adminCookie;
});

test('el formato en blanco es público', async () => {
  cookie = '';
  const r = await call('/api/instrumentos/iso9001-2015-amd1-2024/items');
  assert.equal(r.status, 200); assert.equal(r.data.items.length, 98);
});
