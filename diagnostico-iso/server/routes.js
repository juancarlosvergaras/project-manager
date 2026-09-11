// API REST de la herramienta de diagnóstico ISO 9001.
import { randomUUID } from 'node:crypto';
import { Router, HttpError } from './router.js';
import { getDb, log, VALORACIONES, ROLES, CAPACIDADES, puede } from './db.js';
import { calcularIndicadores, compararVersiones, NIVELES, cmpNumeral } from './scoring.js';
import * as auth from './auth.js';

export const api = new Router();
const db = () => getDb();
const ROLES_VALIDOS = Object.keys(ROLES);

// ---------- helpers ----------
function orgOr404(id) {
  const o = db().prepare('SELECT * FROM organizaciones WHERE id = ? AND activa = 1').get(id);
  if (!o) throw new HttpError(404, 'Organización no encontrada');
  return o;
}
function esMiembro(usuario, orgId) {
  if (puede(usuario, 'ver_todas')) return true;
  return !!db().prepare('SELECT 1 FROM organizacion_miembros WHERE organizacion_id = ? AND usuario_id = ?').get(orgId, usuario.id);
}
// Acceso a una organización con una capacidad concreta (el rol es global; la membresía define el alcance).
function requiereAccesoOrg(ctx, orgId, capacidad = null) {
  if (!esMiembro(ctx.usuario, orgId)) throw new HttpError(403, 'No tiene acceso a esta organización');
  if (capacidad && !puede(ctx.usuario, capacidad)) throw new HttpError(403, 'Su rol (' + ROLES[ctx.usuario.rol].etiqueta + ') no permite esta acción');
}
function diagOr404(id) {
  const d = db().prepare('SELECT * FROM diagnosticos WHERE id = ?').get(id);
  if (!d) throw new HttpError(404, 'Diagnóstico no encontrado');
  return d;
}
function itemsVigentes(instrumentoId) {
  return db().prepare('SELECT * FROM instrumento_items WHERE instrumento_id = ? AND activo = 1').all(instrumentoId).sort(ordenItems);
}
function itemsDe(diag) {
  return db().prepare('SELECT i.* FROM diagnostico_items di JOIN instrumento_items i ON i.id = di.item_id WHERE di.diagnostico_id = ?').all(diag.id).sort(ordenItems);
}
function ordenItems(a, b) { return a.capitulo - b.capitulo || cmpNumeral(a.numeral, b.numeral) || a.orden - b.orden; }
function respuestasDe(diagId) {
  const m = new Map();
  for (const r of db().prepare('SELECT * FROM respuestas WHERE diagnostico_id = ?').all(diagId)) m.set(r.item_id, r);
  return m;
}
function indicadoresDe(diag) { return calcularIndicadores(itemsDe(diag), respuestasDe(diag.id)); }
function resumenDiag(d) {
  const ind = indicadoresDe(d);
  return {
    id: d.id, organizacion_id: d.organizacion_id, instrumento_id: d.instrumento_id, version_numero: d.version_numero, titulo: d.titulo, fecha: d.fecha,
    estado: d.estado, notas: d.notas, base_version_id: d.base_version_id, creado_en: d.creado_en, cerrado_en: d.cerrado_en,
    total_items: ind.total_items, cumplimiento: ind.cumplimiento, brecha_total: ind.brecha_total, avance_diligenciamiento: ind.avance_diligenciamiento, nivel: ind.nivel.nombre, conteo: ind.conteo,
  };
}
function str(v, max = 4000) { if (v === undefined || v === null) return null; const s = String(v).trim(); return s ? s.slice(0, max) : null; }
function publico(u) { const { password_hash, gestor_cookie, ...x } = u; return { ...x, capacidades: CAPACIDADES[x.rol] || [] }; }

// ---------- sesión y configuración ----------
api.get('/api/config', (ctx) => ctx.json({
  version: process.env.APP_VERSION || '',
  escala: 'cumple=1, cumple_parcial=0.5, no_cumple=0, no_aplica=excluida',
  auth: { modo: auth.authConfig.mode, gestor: auth.authConfig.gestorHabilitado, local: auth.authConfig.localHabilitado || auth.authConfig.gestorCredenciales, credenciales_gestor: auth.authConfig.gestorCredenciales, gestor_nombre: auth.authConfig.gestorNombre, gestor_url: auth.authConfig.gestorUrl, app_url: auth.authConfig.appUrl },
  valoraciones: Object.entries(VALORACIONES).map(([clave, v]) => ({ clave, ...v })),
  roles: Object.entries(ROLES).map(([clave, r]) => ({ clave, ...r, capacidades: CAPACIDADES[clave] })),
  niveles: NIVELES,
}));
api.get('/api/me', (ctx) => ctx.json({ usuario: ctx.usuario ? publico(ctx.usuario) : null }));

api.post('/api/auth/local/login', async (ctx) => {
  const b = await ctx.body();
  const u = await auth.loginConCredenciales(b.email, b.password);
  auth.crearSesion(ctx.res, ctx.req, u.id, u.gestor_cookie ?? null);
  log(u.id, u.origen === 'gestor' ? 'sesion.inicio_gestor' : 'sesion.inicio_local', 'usuario', u.id);
  ctx.json({ usuario: publico(u) });
});
api.post('/api/auth/logout', (ctx) => { auth.cerrarSesion(ctx.req, ctx.res); ctx.json({ ok: true }); });
api.post('/api/auth/gestor/token', async (ctx) => {
  const b = await ctx.body();
  const u = await auth.autenticarConGestor({ token: str(b.token, 8000) });
  auth.crearSesion(ctx.res, ctx.req, u.id);
  log(u.id, 'sesion.inicio_gestor_token', 'usuario', u.id);
  ctx.json({ usuario: publico(u) });
});
api.post('/api/auth/cambiar-password', auth.requiereSesion, async (ctx) => {
  const b = await ctx.body();
  const u = db().prepare('SELECT * FROM usuarios WHERE id = ?').get(ctx.usuario.id);
  if (u.origen !== 'local') throw new HttpError(400, 'La contraseña se administra en ' + auth.authConfig.gestorNombre);
  if (!auth.verifyPassword(String(b.actual || ''), u.password_hash)) throw new HttpError(401, 'Contraseña actual incorrecta');
  if (String(b.nueva || '').length < 8) throw new HttpError(400, 'La nueva contraseña debe tener al menos 8 caracteres');
  db().prepare('UPDATE usuarios SET password_hash = ? WHERE id = ?').run(auth.hashPassword(String(b.nueva)), u.id);
  ctx.json({ ok: true });
});

// ---------- usuarios (administración) ----------
api.get('/api/usuarios', auth.requiereCapacidad('gestionar_usuarios'), (ctx) => {
  const q = '%' + (ctx.query.q || '') + '%';
  ctx.json({
    puede_sincronizar: !!ctx.usuario.gestor_cookie,
    sincronizacion: { automatica: auth.fuenteSyncConfigurada(), ultima: auth.estadoSync.ultima, resultado: auth.estadoSync.resultado, error: auth.estadoSync.error },
    usuarios: db().prepare(`SELECT u.id, u.email, u.nombre, u.rol, u.rol_manual, u.origen, u.activo, u.creado_en, u.ultimo_acceso, u.cargo, u.sincronizado_en,
      (SELECT COUNT(*) FROM organizacion_miembros m JOIN organizaciones o ON o.id = m.organizacion_id AND o.activa = 1 WHERE m.usuario_id = u.id) AS total_organizaciones,
      (SELECT GROUP_CONCAT(COALESCE(o.sigla, o.nombre), ' · ') FROM organizacion_miembros m JOIN organizaciones o ON o.id = m.organizacion_id AND o.activa = 1 WHERE m.usuario_id = u.id) AS organizaciones
      FROM usuarios u WHERE u.email LIKE ? OR u.nombre LIKE ? ORDER BY u.activo DESC, u.nombre LIMIT 500`).all(q, q),
  });
});
api.post('/api/usuarios/sincronizar', auth.requiereCapacidad('gestionar_usuarios'), async (ctx) => {
  const r = await auth.sincronizarUsuariosGestor(ctx.usuario.gestor_cookie);
  log(ctx.usuario.id, 'usuarios.sincronizados_gestor', 'usuario', null, r);
  ctx.json(r);
});
api.post('/api/usuarios', auth.requiereCapacidad('gestionar_usuarios'), async (ctx) => {
  const b = await ctx.body();
  const email = str(b.email, 200); const nombre = str(b.nombre, 200);
  if (!email) throw new HttpError(400, 'Correo o usuario requerido');
  if (!nombre) throw new HttpError(400, 'Nombre requerido');
  const rol = ROLES_VALIDOS.includes(b.rol) ? b.rol : 'usuario';
  if (db().prepare('SELECT 1 FROM usuarios WHERE email = ?').get(email)) throw new HttpError(409, 'Ya existe un usuario con ese correo');
  const id = randomUUID().slice(0, 16);
  const pw = String(b.password || '');
  if (pw.length < 8) throw new HttpError(400, 'La contraseña debe tener al menos 8 caracteres');
  db().prepare('INSERT INTO usuarios (id, email, nombre, rol, rol_manual, origen, password_hash, cargo) VALUES (?,?,?,?,1,?,?,?)').run(id, email, nombre, rol, 'local', auth.hashPassword(pw), str(b.cargo, 200));
  log(ctx.usuario.id, 'usuario.creado', 'usuario', id, { email, rol });
  ctx.json({ id }, 201);
});
api.put('/api/usuarios/:id', auth.requiereCapacidad('gestionar_usuarios'), async (ctx) => {
  const b = await ctx.body();
  const u = db().prepare('SELECT * FROM usuarios WHERE id = ?').get(ctx.params.id);
  if (!u) throw new HttpError(404, 'Usuario no encontrado');
  const rol = ROLES_VALIDOS.includes(b.rol) ? b.rol : u.rol;
  const activo = b.activo === undefined ? u.activo : (b.activo ? 1 : 0);
  if (u.id === ctx.usuario.id && (rol !== 'admin' || !activo)) throw new HttpError(400, 'No puede degradar ni desactivar su propio usuario');
  const rolManual = rol !== u.rol ? 1 : u.rol_manual;
  db().prepare('UPDATE usuarios SET nombre = ?, rol = ?, rol_manual = ?, activo = ?, cargo = COALESCE(?, cargo) WHERE id = ?').run(str(b.nombre, 200) || u.nombre, rol, rolManual, activo, str(b.cargo, 200), u.id);
  db().prepare('UPDATE organizacion_miembros SET rol = ? WHERE usuario_id = ?').run(rol, u.id);
  if (b.password && u.origen === 'local') {
    if (String(b.password).length < 8) throw new HttpError(400, 'La contraseña debe tener al menos 8 caracteres');
    db().prepare('UPDATE usuarios SET password_hash = ? WHERE id = ?').run(auth.hashPassword(String(b.password)), u.id);
  }
  log(ctx.usuario.id, 'usuario.actualizado', 'usuario', u.id, { rol, activo });
  ctx.json({ ok: true });
});

// Organizaciones asignadas a un usuario (una o varias). El alcance lo da la membresía; el rol es el del usuario.
api.get('/api/usuarios/:id/organizaciones', auth.requiereCapacidad('gestionar_usuarios'), (ctx) => {
  const u = db().prepare('SELECT id, email, nombre, rol FROM usuarios WHERE id = ?').get(ctx.params.id);
  if (!u) throw new HttpError(404, 'Usuario no encontrado');
  const orgs = db().prepare(`SELECT o.id, o.nombre, o.sigla, o.sector, o.ciudad, m.asignado_en
                             FROM organizaciones o LEFT JOIN organizacion_miembros m ON m.organizacion_id = o.id AND m.usuario_id = ?
                             WHERE o.activa = 1 ORDER BY o.nombre`).all(u.id);
  ctx.json({ usuario: u, organizaciones: orgs.map(o => ({ ...o, asignada: !!o.asignado_en })) });
});
api.put('/api/usuarios/:id/organizaciones', auth.requiereCapacidad('gestionar_usuarios'), async (ctx) => {
  const u = db().prepare('SELECT id, rol FROM usuarios WHERE id = ?').get(ctx.params.id);
  if (!u) throw new HttpError(404, 'Usuario no encontrado');
  const b = await ctx.body();
  const lista = Array.isArray(b.organizaciones) ? b.organizaciones : [];
  const validas = new Set(db().prepare('SELECT id FROM organizaciones WHERE activa = 1').all().map(o => o.id));
  const deseadas = new Set();
  for (const x of lista) {
    const id = typeof x === 'string' ? x : x?.id;
    if (!validas.has(id)) throw new HttpError(400, 'Organización no válida: ' + id);
    deseadas.add(id);
  }
  db().exec('BEGIN');
  try {
    if (b.reemplazar !== false) {
      const actuales = db().prepare('SELECT organizacion_id FROM organizacion_miembros WHERE usuario_id = ?').all(u.id).map(m => m.organizacion_id);
      const del = db().prepare('DELETE FROM organizacion_miembros WHERE usuario_id = ? AND organizacion_id = ?');
      for (const id of actuales) if (!deseadas.has(id)) del.run(u.id, id);
    }
    const up = db().prepare('INSERT INTO organizacion_miembros (organizacion_id, usuario_id, rol) VALUES (?,?,?) ON CONFLICT(organizacion_id, usuario_id) DO UPDATE SET rol = excluded.rol');
    for (const id of deseadas) up.run(id, u.id, u.rol);
    db().exec('COMMIT');
  } catch (e) { db().exec('ROLLBACK'); throw e; }
  log(ctx.usuario.id, 'usuario.organizaciones_asignadas', 'usuario', u.id, { organizaciones: [...deseadas] });
  ctx.json({ ok: true, asignadas: deseadas.size });
});

// ---------- instrumento (cuestionario) ----------
api.get('/api/instrumentos', auth.requiereSesion, (ctx) => {
  ctx.json({ instrumentos: db().prepare('SELECT i.*, (SELECT COUNT(*) FROM instrumento_items t WHERE t.instrumento_id = i.id AND t.activo = 1) AS total_items FROM instrumentos i WHERE activo = 1').all() });
});
api.get('/api/instrumentos/:id/items', (ctx) => {
  // Público para permitir imprimir el formato en blanco sin sesión.
  const inst = db().prepare('SELECT * FROM instrumentos WHERE id = ? OR clave = ?').get(ctx.params.id, ctx.params.id);
  if (!inst) throw new HttpError(404, 'Instrumento no encontrado');
  const todos = ctx.query.todos === '1';
  const items = todos ? db().prepare('SELECT * FROM instrumento_items WHERE instrumento_id = ?').all(inst.id).sort(ordenItems) : itemsVigentes(inst.id);
  const uso = db().prepare('SELECT item_id, COUNT(*) c FROM diagnostico_items GROUP BY item_id').all().reduce((m, r) => (m[r.item_id] = r.c, m), {});
  ctx.json({ instrumento: inst, items: items.map(i => ({ ...i, versiones_en_uso: uso[i.id] || 0 })) });
});
function validarItem(b, actual = {}) {
  const capitulo = Number(b.capitulo ?? actual.capitulo);
  if (!(capitulo >= 4 && capitulo <= 10)) throw new HttpError(400, 'El capítulo debe estar entre 4 y 10');
  const numeral = str(b.numeral, 20) ?? actual.numeral;
  if (!numeral || !/^\d+(\.\d+)*$/.test(numeral) || Number(numeral.split('.')[0]) !== capitulo) throw new HttpError(400, 'El numeral debe pertenecer al capítulo indicado (p. ej. ' + capitulo + '.1)');
  const pregunta = str(b.pregunta, 1000) ?? actual.pregunta;
  if (!pregunta) throw new HttpError(400, 'La pregunta es obligatoria');
  const CAP = { 4: 'Contexto de la organización', 5: 'Liderazgo', 6: 'Planificación', 7: 'Apoyo', 8: 'Operación', 9: 'Evaluación del desempeño', 10: 'Mejora' };
  return { capitulo, capitulo_nombre: CAP[capitulo], numeral, pregunta, responsable_sugerido: str(b.responsable_sugerido, 300) ?? actual.responsable_sugerido ?? null };
}
api.post('/api/instrumentos/:id/items', auth.requiereCapacidad('editar_instrumento'), async (ctx) => {
  const inst = db().prepare('SELECT * FROM instrumentos WHERE id = ? OR clave = ?').get(ctx.params.id, ctx.params.id);
  if (!inst) throw new HttpError(404, 'Instrumento no encontrado');
  const b = await ctx.body();
  const v = validarItem(b);
  const n = db().prepare('SELECT COALESCE(MAX(CAST(SUBSTR(codigo, 5) AS INTEGER)), 0) m FROM instrumento_items WHERE instrumento_id = ?').get(inst.id).m + 1;
  const codigo = str(b.codigo, 20) || ('ISO-' + String(n).padStart(3, '0'));
  if (db().prepare('SELECT 1 FROM instrumento_items WHERE instrumento_id = ? AND codigo = ?').get(inst.id, codigo)) throw new HttpError(409, 'Ya existe una pregunta con el código ' + codigo);
  const orden = db().prepare('SELECT COALESCE(MAX(orden), 0) m FROM instrumento_items WHERE instrumento_id = ?').get(inst.id).m + 1;
  const id = randomUUID();
  db().exec('BEGIN');
  try {
    db().prepare("INSERT INTO instrumento_items (id, instrumento_id, codigo, capitulo, capitulo_nombre, numeral, pregunta, responsable_sugerido, orden, activo, creado_en) VALUES (?,?,?,?,?,?,?,?,?,1,datetime('now'))")
      .run(id, inst.id, codigo, v.capitulo, v.capitulo_nombre, v.numeral, v.pregunta, v.responsable_sugerido, orden);
    // Las versiones en diligenciamiento incorporan la pregunta nueva; las cerradas no cambian.
    db().prepare("INSERT OR IGNORE INTO diagnostico_items (diagnostico_id, item_id) SELECT id, ? FROM diagnosticos WHERE instrumento_id = ? AND estado = 'en_diligenciamiento'").run(id, inst.id);
    db().exec('COMMIT');
  } catch (e) { db().exec('ROLLBACK'); throw e; }
  log(ctx.usuario.id, 'instrumento.pregunta_agregada', 'item', id, { codigo, numeral: v.numeral });
  ctx.json({ id, codigo }, 201);
});
api.put('/api/instrumentos/:id/items/:itemId', auth.requiereCapacidad('editar_instrumento'), async (ctx) => {
  const it = db().prepare('SELECT * FROM instrumento_items WHERE id = ?').get(ctx.params.itemId);
  if (!it) throw new HttpError(404, 'Pregunta no encontrada');
  const b = await ctx.body();
  const v = validarItem(b, it);
  db().prepare('UPDATE instrumento_items SET capitulo = ?, capitulo_nombre = ?, numeral = ?, pregunta = ?, responsable_sugerido = ? WHERE id = ?')
    .run(v.capitulo, v.capitulo_nombre, v.numeral, v.pregunta, v.responsable_sugerido, it.id);
  log(ctx.usuario.id, 'instrumento.pregunta_editada', 'item', it.id, { codigo: it.codigo });
  ctx.json({ ok: true });
});
api.delete('/api/instrumentos/:id/items/:itemId', auth.requiereCapacidad('editar_instrumento'), (ctx) => {
  const it = db().prepare('SELECT * FROM instrumento_items WHERE id = ?').get(ctx.params.itemId);
  if (!it) throw new HttpError(404, 'Pregunta no encontrada');
  db().exec('BEGIN');
  try {
    db().prepare('UPDATE instrumento_items SET activo = 0 WHERE id = ?').run(it.id);
    // Sale de las versiones en diligenciamiento; las cerradas la conservan como registro histórico.
    db().prepare("DELETE FROM diagnostico_items WHERE item_id = ? AND diagnostico_id IN (SELECT id FROM diagnosticos WHERE estado = 'en_diligenciamiento')").run(it.id);
    db().exec('COMMIT');
  } catch (e) { db().exec('ROLLBACK'); throw e; }
  log(ctx.usuario.id, 'instrumento.pregunta_retirada', 'item', it.id, { codigo: it.codigo });
  ctx.json({ ok: true });
});
api.post('/api/instrumentos/:id/items/:itemId/restaurar', auth.requiereCapacidad('editar_instrumento'), (ctx) => {
  const it = db().prepare('SELECT * FROM instrumento_items WHERE id = ?').get(ctx.params.itemId);
  if (!it) throw new HttpError(404, 'Pregunta no encontrada');
  db().prepare('UPDATE instrumento_items SET activo = 1 WHERE id = ?').run(it.id);
  db().prepare("INSERT OR IGNORE INTO diagnostico_items (diagnostico_id, item_id) SELECT id, ? FROM diagnosticos WHERE instrumento_id = ? AND estado = 'en_diligenciamiento'").run(it.id, it.instrumento_id);
  ctx.json({ ok: true });
});

// ---------- organizaciones ----------
api.get('/api/organizaciones', auth.requiereSesion, (ctx) => {
  const u = ctx.usuario;
  const sql = `SELECT o.*,
      (SELECT COUNT(*) FROM diagnosticos d WHERE d.organizacion_id = o.id) AS total_versiones,
      (SELECT MAX(d.version_numero) FROM diagnosticos d WHERE d.organizacion_id = o.id) AS ultima_version,
      (SELECT COUNT(*) FROM organizacion_miembros m WHERE m.organizacion_id = o.id) AS total_miembros
     FROM organizaciones o WHERE o.activa = 1 ` +
    (puede(u, 'ver_todas') ? '' : 'AND o.id IN (SELECT organizacion_id FROM organizacion_miembros WHERE usuario_id = ?) ') +
    'ORDER BY o.nombre';
  const orgs = puede(u, 'ver_todas') ? db().prepare(sql).all() : db().prepare(sql).all(u.id);
  const ult = db().prepare('SELECT * FROM diagnosticos WHERE organizacion_id = ? ORDER BY version_numero DESC LIMIT 1');
  const abierto = db().prepare("SELECT * FROM diagnosticos WHERE organizacion_id = ? AND estado = 'en_diligenciamiento' LIMIT 1");
  for (const o of orgs) {
    const d = ult.get(o.id); const a = abierto.get(o.id);
    o.ultimo_diagnostico = d ? resumenDiag(d) : null;
    o.diagnostico_abierto = a ? { id: a.id, version_numero: a.version_numero, titulo: a.titulo } : null;
  }
  ctx.json({ organizaciones: orgs });
});
api.post('/api/organizaciones', auth.requiereCapacidad('gestionar_organizaciones'), async (ctx) => {
  const b = await ctx.body();
  const nombre = str(b.nombre, 300);
  if (!nombre) throw new HttpError(400, 'El nombre de la organización es obligatorio');
  const id = randomUUID();
  db().prepare(`INSERT INTO organizaciones (id, nombre, sigla, nit, sector, ciudad, pais, contacto_nombre, contacto_email, descripcion, creado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?)`)
    .run(id, nombre, str(b.sigla, 50), str(b.nit, 50), str(b.sector, 120), str(b.ciudad, 120), str(b.pais, 120) || 'Colombia', str(b.contacto_nombre, 200), str(b.contacto_email, 200), str(b.descripcion, 2000), ctx.usuario.id);
  log(ctx.usuario.id, 'organizacion.creada', 'organizacion', id, { nombre });
  ctx.json({ id }, 201);
});
api.get('/api/organizaciones/:id', auth.requiereSesion, (ctx) => {
  const o = orgOr404(ctx.params.id);
  requiereAccesoOrg(ctx, o.id);
  const diags = db().prepare('SELECT * FROM diagnosticos WHERE organizacion_id = ? ORDER BY version_numero DESC').all(o.id).map(resumenDiag);
  const miembros = puede(ctx.usuario, 'gestionar_usuarios')
    ? db().prepare('SELECT u.rol, m.asignado_en, u.id, u.email, u.nombre, u.origen, u.cargo FROM organizacion_miembros m JOIN usuarios u ON u.id = m.usuario_id WHERE m.organizacion_id = ? ORDER BY u.nombre').all(o.id)
    : [];
  ctx.json({ organizacion: o, capacidades: CAPACIDADES[ctx.usuario.rol], diagnosticos: diags, miembros });
});
api.put('/api/organizaciones/:id', auth.requiereCapacidad('gestionar_organizaciones'), async (ctx) => {
  const o = orgOr404(ctx.params.id);
  const b = await ctx.body();
  db().prepare(`UPDATE organizaciones SET nombre = ?, sigla = ?, nit = ?, sector = ?, ciudad = ?, pais = ?, contacto_nombre = ?, contacto_email = ?, descripcion = ? WHERE id = ?`)
    .run(str(b.nombre, 300) || o.nombre, str(b.sigla, 50), str(b.nit, 50), str(b.sector, 120), str(b.ciudad, 120), str(b.pais, 120) || 'Colombia', str(b.contacto_nombre, 200), str(b.contacto_email, 200), str(b.descripcion, 2000), o.id);
  log(ctx.usuario.id, 'organizacion.actualizada', 'organizacion', o.id);
  ctx.json({ ok: true });
});
api.delete('/api/organizaciones/:id', auth.requiereCapacidad('gestionar_organizaciones'), (ctx) => {
  const o = orgOr404(ctx.params.id);
  db().prepare('UPDATE organizaciones SET activa = 0 WHERE id = ?').run(o.id);
  log(ctx.usuario.id, 'organizacion.desactivada', 'organizacion', o.id);
  ctx.json({ ok: true });
});
api.post('/api/organizaciones/:id/miembros', auth.requiereCapacidad('gestionar_usuarios'), async (ctx) => {
  const o = orgOr404(ctx.params.id);
  const b = await ctx.body();
  const email = str(b.email, 200);
  if (!email) throw new HttpError(400, 'Correo o usuario requerido');
  let u = db().prepare('SELECT * FROM usuarios WHERE email = ?').get(email);
  if (!u) {
    const id = randomUUID().slice(0, 16);
    const pw = String(b.password || '');
    if (pw && pw.length < 8) throw new HttpError(400, 'La contraseña debe tener al menos 8 caracteres');
    const rol = ROLES_VALIDOS.includes(b.rol) && b.rol !== 'admin' ? b.rol : 'usuario';
    db().prepare('INSERT INTO usuarios (id, email, nombre, rol, rol_manual, origen, password_hash) VALUES (?,?,?,?,1,?,?)')
      .run(id, email, str(b.nombre, 200) || email.split('@')[0], rol, pw ? 'local' : 'gestor', pw ? auth.hashPassword(pw) : null);
    u = db().prepare('SELECT * FROM usuarios WHERE id = ?').get(id);
    log(ctx.usuario.id, 'usuario.creado_por_asignacion', 'usuario', id, { email, rol });
  }
  db().prepare('INSERT INTO organizacion_miembros (organizacion_id, usuario_id, rol) VALUES (?,?,?) ON CONFLICT(organizacion_id, usuario_id) DO UPDATE SET rol = excluded.rol').run(o.id, u.id, u.rol);
  log(ctx.usuario.id, 'organizacion.miembro_asignado', 'organizacion', o.id, { usuario: u.id });
  ctx.json({ ok: true, usuario: { id: u.id, email: u.email, nombre: u.nombre, rol: u.rol } }, 201);
});
api.delete('/api/organizaciones/:id/miembros/:usuarioId', auth.requiereCapacidad('gestionar_usuarios'), (ctx) => {
  db().prepare('DELETE FROM organizacion_miembros WHERE organizacion_id = ? AND usuario_id = ?').run(ctx.params.id, ctx.params.usuarioId);
  log(ctx.usuario.id, 'organizacion.miembro_retirado', 'organizacion', ctx.params.id, { usuario: ctx.params.usuarioId });
  ctx.json({ ok: true });
});

// ---------- diagnósticos (versiones) ----------
api.post('/api/organizaciones/:id/diagnosticos', auth.requiereSesion, async (ctx) => {
  const o = orgOr404(ctx.params.id);
  requiereAccesoOrg(ctx, o.id, 'gestionar_versiones');
  const b = await ctx.body();
  const inst = db().prepare('SELECT * FROM instrumentos WHERE (id = ? OR clave = ?) AND activo = 1').get(b.instrumento_id || '', b.instrumento_id || 'iso9001-2015-amd1-2024');
  if (!inst) throw new HttpError(400, 'Instrumento no válido');
  const abierto = db().prepare("SELECT id, version_numero FROM diagnosticos WHERE organizacion_id = ? AND estado = 'en_diligenciamiento'").get(o.id);
  if (abierto && !b.forzar) throw new HttpError(409, `La versión ${abierto.version_numero} sigue en diligenciamiento. Ciérrela antes de crear una nueva o continúe diligenciándola.`, { diagnostico_id: abierto.id });
  const ver = (db().prepare('SELECT COALESCE(MAX(version_numero),0) m FROM diagnosticos WHERE organizacion_id = ?').get(o.id).m) + 1;
  const id = randomUUID();
  const fecha = str(b.fecha, 10) || new Date().toISOString().slice(0, 10);
  const titulo = str(b.titulo, 300) || `Diagnóstico ISO 9001 – versión ${ver}`;
  let base = null;
  if (b.desde_version_id) {
    base = diagOr404(b.desde_version_id);
    if (base.organizacion_id !== o.id) throw new HttpError(400, 'La versión base pertenece a otra organización');
  }
  db().exec('BEGIN');
  try {
    db().prepare('INSERT INTO diagnosticos (id, organizacion_id, instrumento_id, version_numero, titulo, fecha, notas, base_version_id, creado_por) VALUES (?,?,?,?,?,?,?,?,?)')
      .run(id, o.id, inst.id, ver, titulo, fecha, str(b.notas, 4000), base ? base.id : null, ctx.usuario.id);
    // La nueva versión usa el cuestionario vigente (preguntas activas).
    db().prepare('INSERT INTO diagnostico_items (diagnostico_id, item_id) SELECT ?, id FROM instrumento_items WHERE instrumento_id = ? AND activo = 1').run(id, inst.id);
    if (base) {
      const modo = b.modo_copia || 'completa'; // completa | solo_textos | ninguna
      if (modo !== 'ninguna') {
        db().prepare(`INSERT INTO respuestas (diagnostico_id, item_id, valoracion, estado_origen, evidencia, observaciones, responsable, actualizado_por)
                      SELECT ?, r.item_id, ${modo === 'completa' ? 'r.valoracion' : 'NULL'}, NULL, r.evidencia, r.observaciones, r.responsable, ?
                      FROM respuestas r WHERE r.diagnostico_id = ? AND r.item_id IN (SELECT item_id FROM diagnostico_items WHERE diagnostico_id = ?)`)
          .run(id, ctx.usuario.id, base.id, id);
      }
    }
    db().exec('COMMIT');
  } catch (e) { db().exec('ROLLBACK'); throw e; }
  log(ctx.usuario.id, 'diagnostico.creado', 'diagnostico', id, { organizacion: o.id, version: ver, base: base?.id ?? null });
  ctx.json({ id, version_numero: ver }, 201);
});

api.get('/api/diagnosticos/:id', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id);
  const o = orgOr404(d.organizacion_id);
  const items = itemsDe(d);
  const resp = respuestasDe(d.id);
  const inst = db().prepare('SELECT * FROM instrumentos WHERE id = ?').get(d.instrumento_id);
  ctx.json({
    diagnostico: resumenDiag(d), organizacion: o, instrumento: inst, capacidades: CAPACIDADES[ctx.usuario.rol],
    editable: puede(ctx.usuario, 'diligenciar') && d.estado === 'en_diligenciamiento',
    items: items.map(it => ({ ...it, respuesta: resp.get(it.id) ?? null })),
  });
});
api.put('/api/diagnosticos/:id', auth.requiereSesion, async (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'gestionar_versiones');
  const b = await ctx.body();
  db().prepare('UPDATE diagnosticos SET titulo = ?, fecha = ?, notas = ? WHERE id = ?').run(str(b.titulo, 300) || d.titulo, str(b.fecha, 10) || d.fecha, str(b.notas, 4000), d.id);
  ctx.json({ ok: true });
});
api.put('/api/diagnosticos/:id/respuestas/:itemId', auth.requiereSesion, async (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'diligenciar');
  if (d.estado !== 'en_diligenciamiento') throw new HttpError(409, 'La versión está cerrada. Cree una nueva versión para registrar cambios.');
  const it = db().prepare('SELECT item_id AS id FROM diagnostico_items WHERE diagnostico_id = ? AND item_id = ?').get(d.id, ctx.params.itemId);
  if (!it) throw new HttpError(404, 'Pregunta no encontrada en esta versión');
  const b = await ctx.body();
  const val = b.valoracion === null || b.valoracion === '' ? null : b.valoracion;
  if (val && !VALORACIONES[val]) throw new HttpError(400, 'Valoración no válida');
  const prev = db().prepare('SELECT * FROM respuestas WHERE diagnostico_id = ? AND item_id = ?').get(d.id, it.id) ?? {};
  const nuevo = {
    valoracion: b.valoracion === undefined ? prev.valoracion ?? null : val,
    evidencia: b.evidencia === undefined ? prev.evidencia ?? null : str(b.evidencia),
    observaciones: b.observaciones === undefined ? prev.observaciones ?? null : str(b.observaciones),
    responsable: b.responsable === undefined ? prev.responsable ?? null : str(b.responsable, 300),
  };
  db().prepare(`INSERT INTO respuestas (diagnostico_id, item_id, valoracion, estado_origen, evidencia, observaciones, responsable, actualizado_en, actualizado_por)
                VALUES (?,?,?,?,?,?,?,datetime('now'),?)
                ON CONFLICT(diagnostico_id, item_id) DO UPDATE SET valoracion = excluded.valoracion, evidencia = excluded.evidencia, observaciones = excluded.observaciones,
                  responsable = excluded.responsable, actualizado_en = excluded.actualizado_en, actualizado_por = excluded.actualizado_por`)
    .run(d.id, it.id, nuevo.valoracion, prev.estado_origen ?? null, nuevo.evidencia, nuevo.observaciones, nuevo.responsable, ctx.usuario.id);
  const ind = indicadoresDe(d);
  ctx.json({ ok: true, respuesta: { ...nuevo, item_id: it.id }, resumen: { cumplimiento: ind.cumplimiento, brecha_total: ind.brecha_total, avance_diligenciamiento: ind.avance_diligenciamiento, conteo: ind.conteo } });
});
api.post('/api/diagnosticos/:id/cerrar', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'gestionar_versiones');
  if (d.estado === 'cerrado') throw new HttpError(409, 'La versión ya está cerrada');
  db().prepare("UPDATE diagnosticos SET estado = 'cerrado', cerrado_en = datetime('now'), cerrado_por = ? WHERE id = ?").run(ctx.usuario.id, d.id);
  log(ctx.usuario.id, 'diagnostico.cerrado', 'diagnostico', d.id);
  ctx.json({ ok: true });
});
api.post('/api/diagnosticos/:id/reabrir', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'gestionar_versiones');
  const abierto = db().prepare("SELECT version_numero FROM diagnosticos WHERE organizacion_id = ? AND estado = 'en_diligenciamiento' AND id <> ?").get(d.organizacion_id, d.id);
  if (abierto) throw new HttpError(409, `La versión ${abierto.version_numero} ya está en diligenciamiento`);
  db().prepare("UPDATE diagnosticos SET estado = 'en_diligenciamiento', cerrado_en = NULL, cerrado_por = NULL WHERE id = ?").run(d.id);
  log(ctx.usuario.id, 'diagnostico.reabierto', 'diagnostico', d.id);
  ctx.json({ ok: true });
});
api.delete('/api/diagnosticos/:id', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'gestionar_versiones');
  db().prepare('DELETE FROM diagnosticos WHERE id = ?').run(d.id);
  log(ctx.usuario.id, 'diagnostico.eliminado', 'diagnostico', d.id, { organizacion: d.organizacion_id, version: d.version_numero });
  ctx.json({ ok: true });
});
api.get('/api/diagnosticos/:id/indicadores', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'ver_indicadores');
  ctx.json({ diagnostico: resumenDiag(d), organizacion: orgOr404(d.organizacion_id), indicadores: indicadoresDe(d), capacidades: CAPACIDADES[ctx.usuario.rol] });
});
api.get('/api/organizaciones/:id/historico', auth.requiereSesion, (ctx) => {
  const o = orgOr404(ctx.params.id);
  requiereAccesoOrg(ctx, o.id, 'ver_indicadores');
  const diags = db().prepare('SELECT * FROM diagnosticos WHERE organizacion_id = ? ORDER BY version_numero').all(o.id);
  const serie = diags.map(d => { const ind = indicadoresDe(d); return { id: d.id, version_numero: d.version_numero, titulo: d.titulo, fecha: d.fecha, estado: d.estado, cumplimiento: ind.cumplimiento, brecha_total: ind.brecha_total, nivel: ind.nivel.nombre, conteo: ind.conteo, por_capitulo: ind.por_capitulo.map(c => ({ capitulo: c.capitulo, nombre: c.nombre, cumplimiento: c.cumplimiento })) }; });
  ctx.json({ organizacion: o, historico: serie });
});
api.get('/api/diagnosticos/:id/comparar/:otroId', auth.requiereSesion, (ctx) => {
  const a = diagOr404(ctx.params.otroId), b = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, a.organizacion_id, 'ver_indicadores'); requiereAccesoOrg(ctx, b.organizacion_id, 'ver_indicadores');
  const indA = indicadoresDe(a), indB = indicadoresDe(b);
  const ra = respuestasDe(a.id), rb = respuestasDe(b.id);
  const cambios = itemsDe(b).map(it => ({ codigo: it.codigo, numeral: it.numeral, pregunta: it.pregunta, antes: ra.get(it.id)?.valoracion ?? null, despues: rb.get(it.id)?.valoracion ?? null }))
    .filter(c => c.antes !== c.despues);
  ctx.json({ base: resumenDiag(a), actual: resumenDiag(b), comparacion: compararVersiones(indA, indB), cambios });
});
api.get('/api/diagnosticos/:id/export.csv', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'ver_indicadores');
  const o = orgOr404(d.organizacion_id);
  const resp = respuestasDe(d.id);
  const esc = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  const filas = [['ID', 'Capítulo', 'Numeral ISO', 'Pregunta', 'Valoración', 'Estado de origen', 'Evidencia', 'Observaciones', 'Responsable'].map(esc).join(';')];
  for (const it of itemsDe(d)) {
    const r = resp.get(it.id) ?? {};
    filas.push([it.codigo, it.capitulo, it.numeral, it.pregunta, r.valoracion ? VALORACIONES[r.valoracion].etiqueta : '', r.estado_origen ?? '', r.evidencia ?? '', r.observaciones ?? '', r.responsable ?? it.responsable_sugerido ?? ''].map(esc).join(';'));
  }
  const nombre = `diagnostico_${(o.sigla || o.nombre).replace(/[^\w]+/g, '_')}_v${d.version_numero}.csv`;
  ctx.res.writeHead(200, { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': `attachment; filename="${nombre}"` });
  ctx.res.end('﻿' + filas.join('\r\n'));
});
api.get('/api/bitacora', auth.requiereRol('admin'), (ctx) => {
  ctx.json({ bitacora: db().prepare('SELECT b.*, u.email FROM bitacora b LEFT JOIN usuarios u ON u.id = b.usuario_id ORDER BY b.id DESC LIMIT 300').all() });
});
