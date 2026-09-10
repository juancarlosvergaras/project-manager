// Campañas de aplicación de cuestionarios: lista de destinatarios, enlace personal por persona, envío inmediato
// o programado, recordatorios a quienes no han respondido y seguimiento de cada envío.
import { db, auditar } from './db.js';
import { config } from './config.js';
import { enviarCorreo, correoConfigurado } from './correo.js';
import { obtenerCuestionario, tokenNuevo, md } from './cuestionarios.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const CUERPO_POR_DEFECTO = `Estimado(a) {{nombre}}:

Le invitamos a responder el cuestionario «{{cuestionario}}» del Observatorio Nacional de Inteligencia Artificial, dentro del Proyecto IA para el Estado que ejecuta la Universidad de Cartagena con el Ministerio TIC.

Puede responderlo en el siguiente enlace personal:
{{enlace}}

El enlace es personal e intransferible. Si tiene alguna duda, responda a este correo.

Gracias por su participación.`;

const ASUNTO_POR_DEFECTO = 'Invitación a responder: {{cuestionario}}';

// ---------------------------------------------------------------- consultas
const conConteos = (k) => k && {
  ...k,
  total: db.prepare('SELECT COUNT(*) AS n FROM destinatarios WHERE campania_id = ?').get(k.id).n,
  enviados: db.prepare("SELECT COUNT(*) AS n FROM destinatarios WHERE campania_id = ? AND estado IN ('enviado', 'respondido')").get(k.id).n,
  respondidos: db.prepare("SELECT COUNT(*) AS n FROM destinatarios WHERE campania_id = ? AND estado = 'respondido'").get(k.id).n,
  errores: db.prepare("SELECT COUNT(*) AS n FROM destinatarios WHERE campania_id = ? AND estado = 'error'").get(k.id).n,
  pendientes: db.prepare("SELECT COUNT(*) AS n FROM destinatarios WHERE campania_id = ? AND estado = 'pendiente'").get(k.id).n,
};
export function listarCampanias(cuestionarioId = null) {
  const filas = cuestionarioId ? db.prepare('SELECT * FROM campanias WHERE cuestionario_id = ? ORDER BY id DESC').all(cuestionarioId) : db.prepare('SELECT * FROM campanias ORDER BY id DESC').all();
  return filas.map(conConteos);
}
export function obtenerCampania(id) { return conConteos(db.prepare('SELECT * FROM campanias WHERE id = ?').get(id)); }
export function destinatariosDe(campaniaId) { return db.prepare('SELECT * FROM destinatarios WHERE campania_id = ? ORDER BY id').all(campaniaId); }
export function destinatarioPorToken(token) {
  const d = db.prepare('SELECT * FROM destinatarios WHERE token = ?').get(token);
  if (!d) return null;
  return { ...d, campania: obtenerCampania(d.campania_id) };
}

// ---------------------------------------------------------------- creación y edición
export function crearCampania({ cuestionarioId, nombre, asunto, cuerpo, programadaEn = null, usuarioId = null }) {
  const r = db.prepare('INSERT INTO campanias (cuestionario_id, nombre, asunto, cuerpo, programada_en, estado, creado_por) VALUES (?, ?, ?, ?, ?, ?, ?)')
    .run(cuestionarioId, nombre || 'Campaña', asunto || ASUNTO_POR_DEFECTO, cuerpo || CUERPO_POR_DEFECTO, programadaEn, programadaEn ? 'programada' : 'borrador', usuarioId);
  return obtenerCampania(r.lastInsertRowid);
}
export function actualizarCampania(id, { nombre, asunto, cuerpo, programadaEn }) {
  const k = obtenerCampania(id);
  if (!k) return null;
  // Programar vale en cualquier momento (también para una campaña ya enviada: llegará a los pendientes); solo no mientras se envía.
  let estado = k.estado;
  if (k.estado !== 'enviando') {
    if (programadaEn) estado = 'programada';
    else if (k.estado === 'programada') estado = k.enviada_en ? 'enviada' : 'borrador';
  }
  db.prepare('UPDATE campanias SET nombre = ?, asunto = ?, cuerpo = ?, programada_en = ?, estado = ? WHERE id = ?')
    .run(nombre || k.nombre, asunto || k.asunto, cuerpo || k.cuerpo, k.estado === 'enviando' ? k.programada_en : (programadaEn || null), estado, id);
  return obtenerCampania(id);
}
// Quita la programación: la campaña vuelve a «enviada» si ya se envió alguna vez, o a «sin enviar».
export function cancelarCampania(id) { db.prepare("UPDATE campanias SET programada_en = NULL, estado = CASE WHEN enviada_en IS NULL THEN 'borrador' ELSE 'enviada' END WHERE id = ? AND estado = 'programada'").run(id); }
export function eliminarCampania(id) {
  db.prepare('UPDATE respuestas SET campania_id = NULL, destinatario_id = NULL WHERE campania_id = ?').run(id);
  db.prepare('DELETE FROM destinatarios WHERE campania_id = ?').run(id);
  db.prepare('DELETE FROM campanias WHERE id = ?').run(id);
}

// Interpreta una lista pegada: una persona por línea, con correo y opcionalmente nombre y entidad separados por
// punto y coma, coma o tabulador. Acepta también una cabecera "correo;nombre;entidad" y la salta.
export function interpretarLista(texto) {
  const out = [];
  const vistos = new Set();
  for (const linea of String(texto || '').split(/\r?\n/)) {
    const l = linea.trim();
    if (!l) continue;
    const partes = l.split(/\t|;|,(?![^"]*"(?:[^"]*"[^"]*")*[^"]*$)/).map((x) => x.trim().replace(/^"|"$/g, ''));
    const correo = (partes.find((x) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(x)) || '').toLowerCase();
    if (!correo) continue;
    if (vistos.has(correo)) continue;
    vistos.add(correo);
    const resto = partes.filter((x) => x.toLowerCase() !== correo);
    out.push({ correo, nombre: (resto[0] || '').slice(0, 200), entidad: (resto[1] || '').slice(0, 300) });
  }
  return out;
}

export function agregarDestinatarios(campaniaId, lista) {
  const existentes = new Set(destinatariosDe(campaniaId).map((d) => d.correo));
  const ins = db.prepare('INSERT INTO destinatarios (campania_id, correo, nombre, entidad, token) VALUES (?, ?, ?, ?, ?)');
  let n = 0;
  for (const p of lista) {
    if (existentes.has(p.correo)) continue;
    ins.run(campaniaId, p.correo, p.nombre || null, p.entidad || null, tokenNuevo());
    existentes.add(p.correo); n++;
  }
  return n;
}
export function quitarDestinatario(campaniaId, destinatarioId) { db.prepare('DELETE FROM destinatarios WHERE id = ? AND campania_id = ? AND estado != ?').run(destinatarioId, campaniaId, 'respondido'); }

// ---------------------------------------------------------------- mensajes
export function enlaceDe(clave, token) { return `${config.urlPublica}/c/${clave}/t/${token}`; }

export function plantilla(texto, vars) { return String(texto || '').replace(/\{\{\s*(\w+)\s*\}\}/g, (_, k) => (vars[k] != null ? String(vars[k]) : '')); }

// Cuerpo HTML institucional a partir del texto plano de la campaña. Cada párrafo va en su bloque y el enlace se
// vuelve un botón, además de quedar escrito por si el correo no muestra botones.
export function htmlCorreo({ titulo, cuerpoTexto, enlace, boton = 'Responder el cuestionario' }) {
  const parrafos = String(cuerpoTexto).split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean)
    .map((p) => (p === enlace ? `<p style="margin:18px 0"><a href="${esc(enlace)}" style="display:inline-block;background:#184fa4;color:#fff;text-decoration:none;font-weight:700;padding:12px 22px;border-radius:8px">${esc(boton)}</a></p><p style="font-size:13px;color:#60718a">Si el botón no funciona, copie este enlace en su navegador:<br><a href="${esc(enlace)}" style="color:#184fa4">${esc(enlace)}</a></p>` : `<p style="margin:0 0 14px">${md(p)}</p>`))
    .join('');
  return `<!DOCTYPE html><html lang="es"><body style="margin:0;background:#f4f6fb;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1a2540">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6fb;padding:24px 0"><tr><td align="center">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" style="max-width:600px;width:100%;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 4px 24px rgba(10,30,80,.12)">
<tr><td style="background:linear-gradient(135deg,#0d3272,#184fa4,#1d63d4);padding:22px 28px;color:#fff"><div style="font-size:12px;letter-spacing:.6px;text-transform:uppercase;opacity:.85">Observatorio Nacional de Inteligencia Artificial</div><div style="font-size:19px;font-weight:700;margin-top:6px">${esc(titulo)}</div></td></tr>
<tr><td style="padding:26px 28px;font-size:15px;line-height:1.6">${parrafos}</td></tr>
<tr><td style="padding:16px 28px;background:#f6f9ff;color:#60718a;font-size:12px;line-height:1.5">Proyecto IA para el Estado · Universidad de Cartagena y Ministerio de Tecnologías de la Información y las Comunicaciones.<br>Este mensaje se envió desde el portal del Observatorio a la dirección registrada en la campaña.</td></tr>
</table></td></tr></table></body></html>`;
}

function variablesDe(k, cuestionario, d) {
  return { nombre: d.nombre || 'participante', correo: d.correo, entidad: d.entidad || '', cuestionario: cuestionario.definicion.titulo, enlace: enlaceDe(cuestionario.clave, d.token),
    fecha_limite: k.cierra_en || '' };
}

export function vistaPreviaCorreo(k, destinatario = null) {
  const c = obtenerCuestionario(k.cuestionario_id);
  const d = destinatario || { nombre: 'Nombre de ejemplo', correo: 'persona@entidad.gov.co', entidad: 'Entidad de ejemplo', token: 'ENLACE-DE-EJEMPLO' };
  const vars = variablesDe(k, c, d);
  return { asunto: plantilla(k.asunto, vars), html: htmlCorreo({ titulo: c.definicion.titulo, cuerpoTexto: plantilla(k.cuerpo, vars), enlace: vars.enlace }), texto: plantilla(k.cuerpo, vars) };
}

// ---------------------------------------------------------------- envío
const enviando = new Set();
const pausa = (ms) => new Promise((ok) => setTimeout(ok, ms));

// Envía la campaña a los destinatarios pendientes (o, con recordatorio, a los que aún no responden). Corre en segundo
// plano: devuelve enseguida y el estado se sigue desde la página de la campaña.
export async function enviarCampania(id, { recordatorio = false, prefijoAsunto = '' } = {}) {
  const k = obtenerCampania(id);
  if (!k) throw new Error('La campaña no existe.');
  if (!correoConfigurado()) throw new Error('El servidor de correo no está configurado. Defina SMTP_HOST, SMTP_USUARIO, SMTP_CLAVE y CORREO_DESDE en el archivo .env del portal.');
  if (enviando.has(id)) throw new Error('Esta campaña ya se está enviando.');
  const c = obtenerCuestionario(k.cuestionario_id);
  if (!c || c.estado !== 'publicado') throw new Error('El cuestionario debe estar publicado para poder enviarlo.');
  const objetivo = recordatorio
    ? db.prepare("SELECT * FROM destinatarios WHERE campania_id = ? AND estado IN ('enviado', 'error') ORDER BY id").all(id)
    : db.prepare("SELECT * FROM destinatarios WHERE campania_id = ? AND estado IN ('pendiente', 'error') ORDER BY id").all(id);
  if (!objetivo.length) throw new Error(recordatorio ? 'No hay destinatarios a quienes recordar.' : 'No hay destinatarios pendientes de envío.');
  enviando.add(id);
  db.prepare("UPDATE campanias SET estado = 'enviando', programada_en = NULL WHERE id = ?").run(id);
  auditar(recordatorio ? 'campania_recordatorio' : 'campania_envio', { app: 'cuestionarios', detalle: `${k.nombre}: ${objetivo.length} destinatarios` });
  (async () => {
    let ok = 0, mal = 0;
    for (const d of objetivo) {
      const vars = variablesDe(k, c, d);
      const asunto = (prefijoAsunto || '') + plantilla(k.asunto, vars);
      try {
        await enviarCorreo({ para: d.correo, nombrePara: d.nombre || '', asunto, html: htmlCorreo({ titulo: c.definicion.titulo, cuerpoTexto: plantilla(k.cuerpo, vars), enlace: vars.enlace }), texto: plantilla(k.cuerpo, vars), responderA: config.smtp.responderA });
        db.prepare("UPDATE destinatarios SET estado = CASE WHEN estado = 'respondido' THEN estado ELSE 'enviado' END, enviado_en = datetime('now'), error = NULL, envios = envios + 1 WHERE id = ?").run(d.id);
        ok++;
      } catch (e) {
        db.prepare("UPDATE destinatarios SET estado = 'error', error = ?, envios = envios + 1 WHERE id = ?").run(String(e.message).slice(0, 300), d.id);
        mal++;
      }
      await pausa(config.smtp.pausaMs);
    }
    db.prepare("UPDATE campanias SET estado = 'enviada', enviada_en = datetime('now'), ultimo_resultado = ? WHERE id = ?").run(`${ok} enviados, ${mal} con error`, id);
    auditar('campania_terminada', { app: 'cuestionarios', detalle: `${k.nombre}: ${ok} enviados, ${mal} con error` });
    enviando.delete(id);
  })().catch((e) => { enviando.delete(id); db.prepare("UPDATE campanias SET estado = 'enviada', ultimo_resultado = ? WHERE id = ?").run('Error: ' + e.message, id); });
  return { destinatarios: objetivo.length };
}

export function estaEnviando(id) { return enviando.has(id); }

export async function enviarPrueba(id, correo) {
  const k = obtenerCampania(id);
  const c = obtenerCuestionario(k.cuestionario_id);
  const vars = variablesDe(k, c, { nombre: 'Prueba', correo, entidad: 'Entidad de prueba', token: 'prueba' });
  await enviarCorreo({ para: correo, asunto: '[Prueba] ' + plantilla(k.asunto, vars), html: htmlCorreo({ titulo: c.definicion.titulo, cuerpoTexto: plantilla(k.cuerpo, vars), enlace: vars.enlace }), texto: plantilla(k.cuerpo, vars) });
}

// Revisa cada minuto si hay campañas programadas cuya hora ya llegó.
export function programarEnvios() {
  const revisar = () => {
    for (const k of db.prepare("SELECT id FROM campanias WHERE estado = 'programada' AND programada_en IS NOT NULL AND programada_en <= ?").all(new Date().toISOString())) {
      enviarCampania(k.id).catch((e) => { db.prepare("UPDATE campanias SET estado = CASE WHEN enviada_en IS NULL THEN 'borrador' ELSE 'enviada' END, programada_en = NULL, ultimo_resultado = ? WHERE id = ?").run('No se pudo enviar lo programado: ' + e.message, k.id); auditar('campania_error', { app: 'cuestionarios', detalle: e.message }); });
    }
  };
  setTimeout(revisar, 15000);
  setInterval(revisar, 60000);
}

// La hora que escribe el administrador está en la hora de Colombia (UTC-5, sin horario de verano).
export function aUtc(fechaLocal) {
  if (!fechaLocal) return null;
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(String(fechaLocal));
  if (!m) return null;
  const d = new Date(`${m[1]}T${m[2]}:00-05:00`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}
export function aLocal(iso) {
  if (!iso) return '';
  const d = new Date(String(iso).includes('T') ? iso : iso.replace(' ', 'T') + 'Z');
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Bogota', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(d).replace(' ', 'T');
}
