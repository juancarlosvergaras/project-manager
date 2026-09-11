// API REST de la herramienta de diagnóstico ISO 9001.
import { randomUUID } from 'node:crypto';
import { Router, HttpError } from './router.js';
import { getDb, log, VALORACIONES } from './db.js';
import { calcularIndicadores, compararVersiones, NIVELES } from './scoring.js';
import * as auth from './auth.js';

export const api = new Router();
const db = () => getDb();

// ---------- helpers ----------
function esAdmin(u) { return u.rol === 'admin'; }
function esGestorGlobal(u) { return u.rol === 'admin' || u.rol === 'consultor'; }

function orgOr404(id) {
  const o = db().prepare('SELECT * FROM organizaciones WHERE id = ?').get(id);
  if (!o) throw new HttpError(404, 'Organización no encontrada');
  return o;
}
function rolEnOrg(usuario, orgId) {
  if (esGestorGlobal(usuario)) return 'editor';
  const m = db().prepare('SELECT rol FROM organizacion_miembros WHERE organizacion_id = ? AND usuario_id = ?').get(orgId, usuario.id);
  return m ? m.rol : null;
}
function requiereAccesoOrg(ctx, orgId, minimo = 'lector') {
  const rol = rolEnOrg(ctx.usuario, orgId);
  if (!rol) throw new HttpError(403, 'No tiene acceso a esta organización');
  if (minimo === 'editor' && rol !== 'editor') throw new HttpError(403, 'Solo lectura en esta organización');
  return rol;
}
function diagOr404(id) {
  const d = db().prepare('SELECT * FROM diagnosticos WHERE id = ?').get(id);
  if (!d) throw new HttpError(404, 'Diagnóstico no encontrado');
  return d;
}
function itemsDe(instrumentoId) {
  return db().prepare('SELECT * FROM instrumento_items WHERE instrumento_id = ? ORDER BY orden').all(instrumentoId);
}
function respuestasDe(diagId) {
  const m = new Map();
  for (const r of db().prepare('SELECT * FROM respuestas WHERE diagnostico_id = ?').all(diagId)) m.set(r.item_id, r);
  return m;
}
function indicadoresDe(diag) {
  return calcularIndicadores(itemsDe(diag.instrumento_id), respuestasDe(diag.id));
}
function resumenDiag(d) {
  const ind = indicadoresDe(d);
  return {
    id: d.id, organizacion_id: d.organizacion_id, instrumento_id: d.instrumento_id, version_numero: d.version_numero, titulo: d.titulo, fecha: d.fecha,
    estado: d.estado, notas: d.notas, base_version_id: d.base_version_id, creado_en: d.creado_en, cerrado_en: d.cerrado_en,
    cumplimiento: ind.cumplimiento, brecha_total: ind.brecha_total, avance_diligenciamiento: ind.avance_diligenciamiento, nivel: ind.nivel.nombre, conteo: ind.conteo,
  };
}
function str(v, max = 4000) { if (v === undefined || v === null) return null; const s = String(v).trim(); return s ? s.slice(0, max) : null; }

// ---------- sesión ----------
api.get('/api/config', (ctx) => ctx.json({
  auth: { modo: auth.authConfig.mode, gestor: auth.authConfig.gestorHabilitado, local: auth.authConfig.localHabilitado || auth.authConfig.gestorCredenciales, credenciales_gestor: auth.authConfig.gestorCredenciales, gestor_nombre: auth.authConfig.gestorNombre, gestor_url: auth.authConfig.gestorUrl, app_url: auth.authConfig.appUrl },
  valoraciones: Object.entries(VALORACIONES).map(([clave, v]) => ({ clave, ...v })),
  niveles: NIVELES,
}));

api.get('/api/me', (ctx) => ctx.json({ usuario: ctx.usuario }));

api.post('/api/auth/local/login', async (ctx) => {
  const b = await ctx.body();
  const u = await auth.loginConCredenciales(b.email, b.password);
  auth.crearSesion(ctx.res, ctx.req, u.id, u.gestor_cookie ?? null);
  log(u.id, u.origen === 'gestor' ? 'sesion.inicio_gestor' : 'sesion.inicio_local', 'usuario', u.id);
  const { password_hash, ...usuario } = u;
  ctx.json({ usuario });
});
api.post('/api/auth/logout', (ctx) => { auth.cerrarSesion(ctx.req, ctx.res); ctx.json({ ok: true }); });
api.post('/api/auth/gestor/token', async (ctx) => {
  // Alternativa para clientes que ya poseen un token del gestor (p. ej. app.proyectoia.org abre esta herramienta con el token).
  const b = await ctx.body();
  const u = await auth.autenticarConGestor({ token: str(b.token, 8000) });
  auth.crearSesion(ctx.res, ctx.req, u.id);
  log(u.id, 'sesion.inicio_gestor_token', 'usuario', u.id);
  const { password_hash, ...usuario } = u;
  ctx.json({ usuario });
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
api.get('/api/usuarios', auth.requiereRol('admin', 'consultor'), (ctx) => {
  const q = '%' + (ctx.query.q || '') + '%';
  ctx.json({ puede_sincronizar: !!ctx.usuario.gestor_cookie, usuarios: db().prepare(`SELECT u.id, u.email, u.nombre, u.rol, u.origen, u.activo, u.creado_en, u.ultimo_acceso, u.cargo, u.sincronizado_en,
      (SELECT COUNT(*) FROM organizacion_miembros m JOIN organizaciones o ON o.id = m.organizacion_id AND o.activa = 1 WHERE m.usuario_id = u.id) AS total_organizaciones,
      (SELECT GROUP_CONCAT(COALESCE(o.sigla, o.nombre), ' · ') FROM organizacion_miembros m JOIN organizaciones o ON o.id = m.organizacion_id AND o.activa = 1 WHERE m.usuario_id = u.id) AS organizaciones
      FROM usuarios u WHERE u.email LIKE ? OR u.nombre LIKE ? ORDER BY u.nombre LIMIT 200`).all(q, q) });
});
api.post('/api/usuarios/sincronizar', auth.requiereRol('admin', 'consultor'), async (ctx) => {
  const r = await auth.sincronizarUsuariosGestor(ctx.usuario.gestor_cookie);
  log(ctx.usuario.id, 'usuarios.sincronizados_gestor', 'usuario', null, r);
  ctx.json(r);
});
api.post('/api/usuarios', auth.requiereRol('admin'), async (ctx) => {
  const b = await ctx.body();
  const email = str(b.email, 200); const nombre = str(b.nombre, 200);
  if (!email || !email.includes('@')) throw new HttpError(400, 'Correo inválido');
  if (!nombre) throw new HttpError(400, 'Nombre requerido');
  const rol = ['admin', 'consultor', 'usuario'].includes(b.rol) ? b.rol : 'usuario';
  if (db().prepare('SELECT 1 FROM usuarios WHERE email = ?').get(email)) throw new HttpError(409, 'Ya existe un usuario con ese correo');
  const id = randomUUID().slice(0, 16);
  const pw = String(b.password || '');
  if (pw.length < 8) throw new HttpError(400, 'La contraseña debe tener al menos 8 caracteres');
  db().prepare('INSERT INTO usuarios (id, email, nombre, rol, origen, password_hash) VALUES (?,?,?,?,?,?)').run(id, email, nombre, rol, 'local', auth.hashPassword(pw));
  log(ctx.usuario.id, 'usuario.creado', 'usuario', id, { email, rol });
  ctx.json({ id }, 201);
});
api.put('/api/usuarios/:id', auth.requiereRol('admin'), async (ctx) => {
  const b = await ctx.body();
  const u = db().prepare('SELECT * FROM usuarios WHERE id = ?').get(ctx.params.id);
  if (!u) throw new HttpError(404, 'Usuario no encontrado');
  const rol = ['admin', 'consultor', 'usuario'].includes(b.rol) ? b.rol : u.rol;
  const activo = b.activo === undefined ? u.activo : (b.activo ? 1 : 0);
  if (u.id === ctx.usuario.id && (rol !== 'admin' || !activo)) throw new HttpError(400, 'No puede degradar ni desactivar su propio usuario');
  db().prepare('UPDATE usuarios SET nombre = ?, rol = ?, activo = ? WHERE id = ?').run(str(b.nombre, 200) || u.nombre, rol, activo, u.id);
  if (b.password && u.origen === 'local') {
    if (String(b.password).length < 8) throw new HttpError(400, 'La contraseña debe tener al menos 8 caracteres');
    db().prepare('UPDATE usuarios SET password_hash = ? WHERE id = ?').run(auth.hashPassword(String(b.password)), u.id);
  }
  log(ctx.usuario.id, 'usuario.actualizado', 'usuario', u.id, { rol, activo });
  ctx.json({ ok: true });
});

// Asignación de organizaciones a un usuario (una o varias), al estilo de la asignación de proyectos del gestor.
api.get('/api/usuarios/:id/organizaciones', auth.requiereRol('admin', 'consultor'), (ctx) => {
  const u = db().prepare('SELECT id, email, nombre, rol FROM usuarios WHERE id = ?').get(ctx.params.id);
  if (!u) throw new HttpError(404, 'Usuario no encontrado');
  const orgs = db().prepare(`SELECT o.id, o.nombre, o.sigla, o.sector, o.ciudad, m.rol AS rol_asignado, m.asignado_en
                             FROM organizaciones o LEFT JOIN organizacion_miembros m ON m.organizacion_id = o.id AND m.usuario_id = ?
                             WHERE o.activa = 1 ORDER BY o.nombre`).all(u.id);
  ctx.json({ usuario: u, organizaciones: orgs.map(o => ({ ...o, asignada: !!o.rol_asignado })) });
});
api.put('/api/usuarios/:id/organizaciones', auth.requiereRol('admin', 'consultor'), async (ctx) => {
  const u = db().prepare('SELECT id FROM usuarios WHERE id = ?').get(ctx.params.id);
  if (!u) throw new HttpError(404, 'Usuario no encontrado');
  const b = await ctx.body();
  const lista = Array.isArray(b.organizaciones) ? b.organizaciones : [];
  const validas = new Set(db().prepare('SELECT id FROM organizaciones WHERE activa = 1').all().map(o => o.id));
  const deseadas = new Map();
  for (const x of lista) {
    const id = typeof x === 'string' ? x : x?.id;
    if (!validas.has(id)) throw new HttpError(400, 'Organización no válida: ' + id);
    deseadas.set(id, (typeof x === 'object' && x?.rol === 'lector') ? 'lector' : 'editor');
  }
  const actuales = new Map(db().prepare('SELECT organizacion_id, rol FROM organizacion_miembros WHERE usuario_id = ?').all(u.id).map(m => [m.organizacion_id, m.rol]));
  db().exec('BEGIN');
  try {
    if (b.reemplazar !== false) {
      const del = db().prepare('DELETE FROM organizacion_miembros WHERE usuario_id = ? AND organizacion_id = ?');
      for (const id of actuales.keys()) if (!deseadas.has(id)) del.run(u.id, id);
    }
    const up = db().prepare('INSERT INTO organizacion_miembros (organizacion_id, usuario_id, rol) VALUES (?,?,?) ON CONFLICT(organizacion_id, usuario_id) DO UPDATE SET rol = excluded.rol');
    for (const [id, rol] of deseadas) up.run(id, u.id, rol);
    db().exec('COMMIT');
  } catch (e) { db().exec('ROLLBACK'); throw e; }
  log(ctx.usuario.id, 'usuario.organizaciones_asignadas', 'usuario', u.id, { organizaciones: [...deseadas.keys()] });
  ctx.json({ ok: true, asignadas: deseadas.size });
});

// ---------- instrumentos ----------
api.get('/api/instrumentos', auth.requiereSesion, (ctx) => {
  ctx.json({ instrumentos: db().prepare('SELECT i.*, (SELECT COUNT(*) FROM instrumento_items t WHERE t.instrumento_id = i.id) AS total_items FROM instrumentos i WHERE activo = 1').all() });
});
api.get('/api/instrumentos/:id/items', (ctx) => {
  // Público para permitir imprimir el formato en blanco sin sesión.
  const inst = db().prepare('SELECT * FROM instrumentos WHERE id = ? OR clave = ?').get(ctx.params.id, ctx.params.id);
  if (!inst) throw new HttpError(404, 'Instrumento no encontrado');
  ctx.json({ instrumento: inst, items: itemsDe(inst.id) });
});

// ---------- organizaciones ----------
api.get('/api/organizaciones', auth.requiereSesion, (ctx) => {
  const u = ctx.usuario;
  const sql = `SELECT o.*,
      (SELECT COUNT(*) FROM diagnosticos d WHERE d.organizacion_id = o.id) AS total_versiones,
      (SELECT MAX(d.version_numero) FROM diagnosticos d WHERE d.organizacion_id = o.id) AS ultima_version,
      (SELECT COUNT(*) FROM organizacion_miembros m WHERE m.organizacion_id = o.id) AS total_miembros
     FROM organizaciones o WHERE o.activa = 1 ` +
    (esGestorGlobal(u) ? '' : 'AND o.id IN (SELECT organizacion_id FROM organizacion_miembros WHERE usuario_id = ?) ') +
    'ORDER BY o.nombre';
  const orgs = esGestorGlobal(u) ? db().prepare(sql).all() : db().prepare(sql).all(u.id);
  // Cumplimiento de la última versión de cada organización.
  const ult = db().prepare('SELECT * FROM diagnosticos WHERE organizacion_id = ? ORDER BY version_numero DESC LIMIT 1');
  for (const o of orgs) {
    const d = ult.get(o.id);
    o.ultimo_diagnostico = d ? resumenDiag(d) : null;
    o.mi_rol = rolEnOrg(u, o.id);
  }
  ctx.json({ organizaciones: orgs });
});

api.post('/api/organizaciones', auth.requiereRol('admin', 'consultor'), async (ctx) => {
  const b = await ctx.body();
  const nombre = str(b.nombre, 300);
  if (!nombre) throw new HttpError(400, 'El nombre de la organización es obligatorio');
  const id = randomUUID();
  db().prepare(`INSERT INTO organizaciones (id, nombre, sigla, nit, sector, ciudad, pais, contacto_nombre, contacto_email, descripcion, creado_por)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)`)
    .run(id, nombre, str(b.sigla, 50), str(b.nit, 50), str(b.sector, 120), str(b.ciudad, 120), str(b.pais, 120) || 'Colombia', str(b.contacto_nombre, 200), str(b.contacto_email, 200), str(b.descripcion, 2000), ctx.usuario.id);
  log(ctx.usuario.id, 'organizacion.creada', 'organizacion', id, { nombre });
  ctx.json({ id }, 201);
});

api.get('/api/organizaciones/:id', auth.requiereSesion, (ctx) => {
  const o = orgOr404(ctx.params.id);
  const rol = requiereAccesoOrg(ctx, o.id);
  const diags = db().prepare('SELECT * FROM diagnosticos WHERE organizacion_id = ? ORDER BY version_numero DESC').all(o.id).map(resumenDiag);
  const miembros = esGestorGlobal(ctx.usuario)
    ? db().prepare('SELECT m.rol, m.asignado_en, u.id, u.email, u.nombre, u.origen FROM organizacion_miembros m JOIN usuarios u ON u.id = m.usuario_id WHERE m.organizacion_id = ? ORDER BY u.nombre').all(o.id)
    : [];
  ctx.json({ organizacion: o, mi_rol: rol, diagnosticos: diags, miembros });
});

api.put('/api/organizaciones/:id', auth.requiereRol('admin', 'consultor'), async (ctx) => {
  const o = orgOr404(ctx.params.id);
  const b = await ctx.body();
  db().prepare(`UPDATE organizaciones SET nombre = ?, sigla = ?, nit = ?, sector = ?, ciudad = ?, pais = ?, contacto_nombre = ?, contacto_email = ?, descripcion = ? WHERE id = ?`)
    .run(str(b.nombre, 300) || o.nombre, str(b.sigla, 50), str(b.nit, 50), str(b.sector, 120), str(b.ciudad, 120), str(b.pais, 120) || 'Colombia', str(b.contacto_nombre, 200), str(b.contacto_email, 200), str(b.descripcion, 2000), o.id);
  log(ctx.usuario.id, 'organizacion.actualizada', 'organizacion', o.id);
  ctx.json({ ok: true });
});
api.delete('/api/organizaciones/:id', auth.requiereRol('admin'), (ctx) => {
  const o = orgOr404(ctx.params.id);
  db().prepare('UPDATE organizaciones SET activa = 0 WHERE id = ?').run(o.id);
  log(ctx.usuario.id, 'organizacion.desactivada', 'organizacion', o.id);
  ctx.json({ ok: true });
});

// Asignación de usuarios a una organización (por correo; si no existe y hay modo local, se puede crear con contraseña).
api.post('/api/organizaciones/:id/miembros', auth.requiereRol('admin', 'consultor'), async (ctx) => {
  const o = orgOr404(ctx.params.id);
  const b = await ctx.body();
  const email = str(b.email, 200);
  if (!email || !email.includes('@')) throw new HttpError(400, 'Correo inválido');
  let u = db().prepare('SELECT * FROM usuarios WHERE email = ?').get(email);
  if (!u) {
    if (!auth.authConfig.localHabilitado && !b.crear) throw new HttpError(404, 'El usuario no existe. Debe registrarse primero en ' + auth.authConfig.gestorNombre + ' e ingresar una vez a esta herramienta.');
    const id = randomUUID().slice(0, 16);
    const pw = String(b.password || '');
    if (auth.authConfig.localHabilitado && pw && pw.length < 8) throw new HttpError(400, 'La contraseña debe tener al menos 8 caracteres');
    db().prepare('INSERT INTO usuarios (id, email, nombre, rol, origen, password_hash) VALUES (?,?,?,?,?,?)')
      .run(id, email, str(b.nombre, 200) || email.split('@')[0], 'usuario', pw ? 'local' : 'gestor', pw ? auth.hashPassword(pw) : null);
    u = db().prepare('SELECT * FROM usuarios WHERE id = ?').get(id);
    log(ctx.usuario.id, 'usuario.creado_por_asignacion', 'usuario', id, { email });
  }
  const rol = b.rol === 'lector' ? 'lector' : 'editor';
  db().prepare('INSERT INTO organizacion_miembros (organizacion_id, usuario_id, rol) VALUES (?,?,?) ON CONFLICT(organizacion_id, usuario_id) DO UPDATE SET rol = excluded.rol').run(o.id, u.id, rol);
  log(ctx.usuario.id, 'organizacion.miembro_asignado', 'organizacion', o.id, { usuario: u.id, rol });
  ctx.json({ ok: true, usuario: { id: u.id, email: u.email, nombre: u.nombre, rol } }, 201);
});
api.delete('/api/organizaciones/:id/miembros/:usuarioId', auth.requiereRol('admin', 'consultor'), (ctx) => {
  db().prepare('DELETE FROM organizacion_miembros WHERE organizacion_id = ? AND usuario_id = ?').run(ctx.params.id, ctx.params.usuarioId);
  log(ctx.usuario.id, 'organizacion.miembro_retirado', 'organizacion', ctx.params.id, { usuario: ctx.params.usuarioId });
  ctx.json({ ok: true });
});

// ---------- diagnósticos (versiones) ----------
api.post('/api/organizaciones/:id/diagnosticos', auth.requiereSesion, async (ctx) => {
  const o = orgOr404(ctx.params.id);
  requiereAccesoOrg(ctx, o.id, 'editor');
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
    if (base) {
      const modo = b.modo_copia || 'completa'; // completa | solo_textos | ninguna
      if (modo !== 'ninguna') {
        db().prepare(`INSERT INTO respuestas (diagnostico_id, item_id, valoracion, estado_origen, evidencia, observaciones, responsable, actualizado_por)
                      SELECT ?, item_id, ${modo === 'completa' ? 'valoracion' : 'NULL'}, NULL, evidencia, observaciones, responsable, ? FROM respuestas WHERE diagnostico_id = ?`)
          .run(id, ctx.usuario.id, base.id);
      }
    }
    db().exec('COMMIT');
  } catch (e) { db().exec('ROLLBACK'); throw e; }
  log(ctx.usuario.id, 'diagnostico.creado', 'diagnostico', id, { organizacion: o.id, version: ver, base: base?.id ?? null });
  ctx.json({ id, version_numero: ver }, 201);
});

api.get('/api/diagnosticos/:id', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  const rol = requiereAccesoOrg(ctx, d.organizacion_id);
  const o = orgOr404(d.organizacion_id);
  const items = itemsDe(d.instrumento_id);
  const resp = respuestasDe(d.id);
  const inst = db().prepare('SELECT * FROM instrumentos WHERE id = ?').get(d.instrumento_id);
  ctx.json({
    diagnostico: resumenDiag(d), organizacion: o, instrumento: inst, mi_rol: rol, editable: rol === 'editor' && d.estado === 'en_diligenciamiento',
    items: items.map(it => ({ ...it, respuesta: resp.get(it.id) ?? null })),
  });
});

api.put('/api/diagnosticos/:id', auth.requiereSesion, async (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'editor');
  const b = await ctx.body();
  db().prepare('UPDATE diagnosticos SET titulo = ?, fecha = ?, notas = ? WHERE id = ?').run(str(b.titulo, 300) || d.titulo, str(b.fecha, 10) || d.fecha, str(b.notas, 4000), d.id);
  ctx.json({ ok: true });
});

api.put('/api/diagnosticos/:id/respuestas/:itemId', auth.requiereSesion, async (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id, 'editor');
  if (d.estado !== 'en_diligenciamiento') throw new HttpError(409, 'La versión está cerrada. Cree una nueva versión para registrar cambios.');
  const it = db().prepare('SELECT id FROM instrumento_items WHERE id = ? AND instrumento_id = ?').get(ctx.params.itemId, d.instrumento_id);
  if (!it) throw new HttpError(404, 'Pregunta no encontrada en el instrumento de esta versión');
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
  requiereAccesoOrg(ctx, d.organizacion_id, 'editor');
  if (d.estado === 'cerrado') throw new HttpError(409, 'La versión ya está cerrada');
  db().prepare("UPDATE diagnosticos SET estado = 'cerrado', cerrado_en = datetime('now'), cerrado_por = ? WHERE id = ?").run(ctx.usuario.id, d.id);
  log(ctx.usuario.id, 'diagnostico.cerrado', 'diagnostico', d.id);
  ctx.json({ ok: true });
});
api.post('/api/diagnosticos/:id/reabrir', auth.requiereRol('admin', 'consultor'), (ctx) => {
  const d = diagOr404(ctx.params.id);
  const abierto = db().prepare("SELECT version_numero FROM diagnosticos WHERE organizacion_id = ? AND estado = 'en_diligenciamiento' AND id <> ?").get(d.organizacion_id, d.id);
  if (abierto) throw new HttpError(409, `La versión ${abierto.version_numero} ya está en diligenciamiento`);
  db().prepare("UPDATE diagnosticos SET estado = 'en_diligenciamiento', cerrado_en = NULL, cerrado_por = NULL WHERE id = ?").run(d.id);
  log(ctx.usuario.id, 'diagnostico.reabierto', 'diagnostico', d.id);
  ctx.json({ ok: true });
});
api.delete('/api/diagnosticos/:id', auth.requiereRol('admin', 'consultor'), (ctx) => {
  const d = diagOr404(ctx.params.id);
  db().prepare('DELETE FROM diagnosticos WHERE id = ?').run(d.id);
  log(ctx.usuario.id, 'diagnostico.eliminado', 'diagnostico', d.id, { organizacion: d.organizacion_id, version: d.version_numero });
  ctx.json({ ok: true });
});

api.get('/api/diagnosticos/:id/indicadores', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id);
  ctx.json({ diagnostico: resumenDiag(d), organizacion: orgOr404(d.organizacion_id), indicadores: indicadoresDe(d) });
});

api.get('/api/organizaciones/:id/historico', auth.requiereSesion, (ctx) => {
  const o = orgOr404(ctx.params.id);
  requiereAccesoOrg(ctx, o.id);
  const diags = db().prepare('SELECT * FROM diagnosticos WHERE organizacion_id = ? ORDER BY version_numero').all(o.id);
  const serie = diags.map(d => { const ind = indicadoresDe(d); return { id: d.id, version_numero: d.version_numero, titulo: d.titulo, fecha: d.fecha, estado: d.estado, cumplimiento: ind.cumplimiento, brecha_total: ind.brecha_total, nivel: ind.nivel.nombre, conteo: ind.conteo, por_capitulo: ind.por_capitulo.map(c => ({ capitulo: c.capitulo, nombre: c.nombre, cumplimiento: c.cumplimiento })) }; });
  ctx.json({ organizacion: o, historico: serie });
});

api.get('/api/diagnosticos/:id/comparar/:otroId', auth.requiereSesion, (ctx) => {
  const a = diagOr404(ctx.params.otroId), b = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, a.organizacion_id); requiereAccesoOrg(ctx, b.organizacion_id);
  const indA = indicadoresDe(a), indB = indicadoresDe(b);
  // Cambios ítem a ítem
  const ra = respuestasDe(a.id), rb = respuestasDe(b.id);
  const cambios = itemsDe(b.instrumento_id).map(it => ({ codigo: it.codigo, numeral: it.numeral, pregunta: it.pregunta, antes: ra.get(it.id)?.valoracion ?? null, despues: rb.get(it.id)?.valoracion ?? null }))
    .filter(c => c.antes !== c.despues);
  ctx.json({ base: resumenDiag(a), actual: resumenDiag(b), comparacion: compararVersiones(indA, indB), cambios });
});

api.get('/api/diagnosticos/:id/export.csv', auth.requiereSesion, (ctx) => {
  const d = diagOr404(ctx.params.id);
  requiereAccesoOrg(ctx, d.organizacion_id);
  const o = orgOr404(d.organizacion_id);
  const resp = respuestasDe(d.id);
  const esc = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  const filas = [['ID', 'Capítulo', 'Numeral ISO', 'Pregunta', 'Valoración', 'Estado de origen', 'Evidencia', 'Observaciones', 'Responsable'].map(esc).join(';')];
  for (const it of itemsDe(d.instrumento_id)) {
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
