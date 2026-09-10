// Módulo de cuestionarios del portal: definición del instrumento, validación de las respuestas, cálculo de
// puntajes por dimensión, página pública de diligenciamiento y persistencia en la base de datos del portal.
//
// Una definición es un objeto JSON con esta forma (ver src/ejemplos/*.json para tres instrumentos completos):
//   { titulo, subtitulo, intro: ["párrafo con **negritas**"], politicas: {mostrar, posicion: 'inicio'|'final', titulo, textos, etiqueta},
//     progreso: {barra}, pasos: [{etiqueta, bloques: [...]}], cierre: {boton, titulo, mensaje},
//     identificacion: {correo, nombre, entidad, documento, departamento, municipio}, duplicados: {campos, mensaje},
//     calculo: {modo: 'suma'|'promedio', niveles, dimensiones: [{clave, nombre, descripcion}]}, tablero: {graficos, indicadores} }
// Los bloques de cada paso son secciones, textos, leyendas, bloques condicionales o preguntas de estos tipos:
//   texto_corto, parrafo, numero, fecha, seleccion, unica, multiple, escala, rubrica, si_no, ranking, archivo, entidad,
//   departamento, municipio, casilla. Cada pregunta tiene nombre (identificador), etiqueta, ayuda, requerido, numero,
//   y según el tipo opciones, niveles, min/max, extremos, otro, items, dimension.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { db, auditar } from './db.js';
import { config } from './config.js';
import { nivelDe } from './indicadores.js';

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)));
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---------------------------------------------------------------- catálogo de tipos
export const TIPOS = {
  seccion: { nombre: 'Encabezado de sección', responde: false },
  texto: { nombre: 'Texto explicativo', responde: false },
  leyenda: { nombre: 'Leyenda de escala', responde: false },
  condicional: { nombre: 'Bloque condicional', responde: false },
  texto_corto: { nombre: 'Texto corto', responde: true },
  parrafo: { nombre: 'Párrafo (texto largo)', responde: true },
  numero: { nombre: 'Número', responde: true },
  fecha: { nombre: 'Fecha', responde: true },
  seleccion: { nombre: 'Lista desplegable', responde: true, opciones: true },
  unica: { nombre: 'Opción única', responde: true, opciones: true },
  multiple: { nombre: 'Opción múltiple', responde: true, opciones: true },
  escala: { nombre: 'Escala numérica (círculos)', responde: true, numerica: true },
  rubrica: { nombre: 'Rúbrica de niveles', responde: true, numerica: true },
  si_no: { nombre: 'Sí / No', responde: true, numerica: true },
  ranking: { nombre: 'Ordenar por prioridad', responde: true },
  archivo: { nombre: 'Archivo adjunto', responde: true },
  entidad: { nombre: 'Entidad pública (autocompletar)', responde: true },
  departamento: { nombre: 'Departamento', responde: true },
  municipio: { nombre: 'Municipio', responde: true },
  casilla: { nombre: 'Casilla de verificación', responde: true },
};

export const DEFINICION_VACIA = () => ({
  titulo: 'Nuevo cuestionario',
  subtitulo: '',
  intro: ['Describa aquí el propósito del cuestionario, a quién va dirigido y el tiempo estimado de diligenciamiento.'],
  politicas: { mostrar: true, posicion: 'inicio', titulo: 'Términos y Política de Tratamiento de Datos', textos: [POLITICA_MINTIC, POLITICA_UDEC], etiqueta: 'Autorizo el tratamiento de mis datos personales conforme a lo descrito' },
  progreso: { barra: true },
  pasos: [{ etiqueta: 'Datos', bloques: [
    { tipo: 'seccion', numero: '1', titulo: 'Identificación', icono: '🪪' },
    { tipo: 'texto_corto', nombre: 'nombre', etiqueta: 'Nombre completo', requerido: true },
    { tipo: 'texto_corto', nombre: 'correo', etiqueta: 'Correo electrónico', formato: 'email', requerido: true },
  ] }],
  cierre: { boton: 'Enviar respuestas', titulo: '¡Gracias por su respuesta!', mensaje: 'Sus respuestas fueron registradas correctamente.' },
  identificacion: { correo: 'correo', nombre: 'nombre' },
  duplicados: { campos: [], mensaje: 'Ya existe una respuesta registrada con estos datos.' },
  calculo: { modo: 'promedio', niveles: false, dimensiones: [] },
  tablero: { graficos: [], indicadores: [] },
});

export const POLITICA_MINTIC = 'El Ministerio / Fondo Único de TIC se permite solicitar autorización para realizar el tratamiento de sus datos personales, la cual tiene como finalidad: gestionar el proceso de recolección de información, seguimiento y eventual acompañamiento de las entidades participantes del Proyecto IA para el Estado, y compartir información con aliados estratégicos en la ejecución técnica que facilitarán las actividades del proyecto. Para tal fin, usted reconoce que el registro y autorización para el tratamiento de su información personal lo realiza de manera voluntaria y que conoce los derechos que detenta, especialmente a conocer, actualizar y rectificar su información personal, revocar la autorización y solicitar la supresión del dato, los cuales podrá ejercer a través de minticresponde@mintic.gov.co, la línea telefónica gratuita nacional 01-800-0914014 o en el Punto de Atención al Ciudadano ubicado en el Edificio Murillo Toro, carrera 8 a entre calles 12 y 13 en Bogotá, Colombia. La información suministrada será tratada por el Ministerio/Fondo Único de Tecnologías de la Información y las Comunicaciones como responsable del tratamiento, de acuerdo con la Ley 1581 de 2012 y la Política de Tratamiento de Datos Personales, descrita en la Resolución 2238 de 2024 del Ministerio de TIC, o aquella que la modifique, derogue o sustituya, la cual puede consultar en https://www.mintic.gov.co/portal/inicio/Secciones-auxiliares/Politicas/2627:Politicas-de-Privacidad-y-Condiciones-de-Uso';
export const POLITICA_UDEC = 'Autorización de tratamiento de datos – Universidad de Cartagena (UdeC). Adicionalmente, quien diligencia manifiesta que ha leído y acepta los Términos de Uso y el Aviso de Privacidad de la Universidad de Cartagena (UdeC) y autoriza el tratamiento de sus datos personales por parte de UdeC, en calidad de responsable del tratamiento, para las siguientes finalidades: gestionar el diligenciamiento del instrumento, análisis y consolidación de resultados, seguimiento y acompañamiento, comunicaciones informativas y operativas, control de calidad del servicio, fines estadísticos e institucionales, seguridad de la información y cumplimiento de obligaciones legales y contractuales, así como la transmisión y/o transferencia a aliados tecnológicos y académicos estrictamente necesarios para la ejecución del proyecto y bajo acuerdos de protección de datos. El titular podrá ejercer sus derechos de conocer, actualizar, rectificar y suprimir sus datos, así como revocar la autorización, mediante el correo datospersonales@unicartagena.edu.co, o de manera presencial en la Oficina Asesora de Planeación – Datos Personales, Cra. 6 No. 36-100, Centro de Cartagena de Indias, CP 130001, Bolívar, Colombia, PBX (+57) 3164390360 ext. 165. La política de tratamiento de datos de UdeC puede consultarse en https://www.unicartagena.edu.co/proteccion-de-datos. UdeC realizará el tratamiento conforme a la Ley 1581 de 2012, sus decretos reglamentarios y las demás normas aplicables.';

// ---------------------------------------------------------------- utilidades sobre la definición
export function normalizar(def) {
  const d = JSON.parse(JSON.stringify(def || {}));
  d.titulo = String(d.titulo || 'Cuestionario');
  d.subtitulo = String(d.subtitulo || '');
  d.intro = Array.isArray(d.intro) ? d.intro.map(String) : d.intro ? [String(d.intro)] : [];
  d.politicas = Object.assign({ mostrar: false, posicion: 'inicio', titulo: 'Términos y Política de Tratamiento de Datos', textos: [], etiqueta: 'Autorizo el tratamiento de mis datos personales conforme a lo descrito' }, d.politicas || {});
  d.politicas.textos = Array.isArray(d.politicas.textos) ? d.politicas.textos : [];
  d.progreso = Object.assign({ barra: false }, d.progreso || {});
  d.pasos = Array.isArray(d.pasos) && d.pasos.length ? d.pasos : [{ etiqueta: 'Paso 1', bloques: [] }];
  d.pasos.forEach((p, i) => { p.etiqueta = String(p.etiqueta || `Paso ${i + 1}`); p.bloques = Array.isArray(p.bloques) ? p.bloques : []; });
  d.cierre = Object.assign({ boton: 'Enviar respuestas', titulo: '¡Gracias por su respuesta!', mensaje: 'Sus respuestas fueron registradas correctamente.' }, d.cierre || {});
  d.identificacion = d.identificacion || {};
  d.duplicados = Object.assign({ campos: [], mensaje: 'Ya existe una respuesta registrada con estos datos.' }, d.duplicados || {});
  d.duplicados.campos = Array.isArray(d.duplicados.campos) ? d.duplicados.campos : [];
  d.calculo = Object.assign({ modo: 'promedio', niveles: false, dimensiones: [] }, d.calculo || {});
  d.calculo.dimensiones = Array.isArray(d.calculo.dimensiones) ? d.calculo.dimensiones : [];
  d.tablero = Object.assign({ graficos: [], indicadores: [] }, d.tablero || {});
  return d;
}

// Recorre todos los bloques (incluidos los de los condicionales) llamando fn(bloque, contexto).
export function recorrer(def, fn) {
  const visitar = (bloques, ctx) => {
    for (const b of bloques || []) {
      fn(b, ctx);
      if (b.tipo === 'condicional') visitar(b.bloques, { ...ctx, condiciones: [...ctx.condiciones, b.condicion || {}] });
    }
  };
  (def.pasos || []).forEach((p, i) => visitar(p.bloques, { paso: i, condiciones: [] }));
}

// Preguntas que se responden, en orden, con las condiciones que las muestran.
export function camposDe(def) {
  const out = [];
  recorrer(def, (b, ctx) => { if (TIPOS[b.tipo] && TIPOS[b.tipo].responde && b.nombre) out.push({ ...b, _paso: ctx.paso, _condiciones: ctx.condiciones }); });
  return out;
}

export function opcionesDe(campo) {
  if (campo.tipo === 'si_no') return [{ valor: '1', texto: 'Sí' }, { valor: '0', texto: 'No' }];
  if (campo.tipo === 'rubrica') return (campo.niveles || []).map((n) => typeof n === 'object' ? { valor: String(n.valor), texto: String(n.texto) } : { valor: String(n), texto: String(n) });
  if (campo.tipo === 'escala') { const out = []; for (let v = Number(campo.min ?? 1); v <= Number(campo.max ?? 5); v++) out.push({ valor: String(v), texto: String(v) }); return out; }
  return (campo.opciones || []).map((o) => typeof o === 'object' ? { valor: String(o.valor), texto: String(o.texto ?? o.valor) } : { valor: String(o), texto: String(o) });
}

export function textoDeOpcion(campo, valor) {
  const o = opcionesDe(campo).find((x) => x.valor === String(valor));
  return o ? o.texto : String(valor ?? '');
}

export function valorMaximo(campo) {
  if (campo.tipo === 'escala') return Number(campo.max ?? 5);
  if (campo.tipo === 'si_no') return 1;
  if (campo.tipo === 'rubrica') return Math.max(...opcionesDe(campo).map((o) => Number(o.valor)).filter((n) => !Number.isNaN(n)), 0);
  if (campo.tipo === 'numero') return Number(campo.max ?? 0);
  return 0;
}

export function condicionCumplida(cond, datos) {
  if (!cond || !cond.campo) return true;
  const v = datos[cond.campo];
  const lista = Array.isArray(v) ? v.map(String) : v == null || v === '' ? [] : [String(v)];
  const esperado = String(cond.valor ?? '');
  switch (cond.operador || '==') {
    case '==': return lista.includes(esperado);
    case '!=': return !lista.includes(esperado);
    case 'vacio': return lista.length === 0;
    case 'no_vacio': return lista.length > 0;
    case 'contiene': return lista.some((x) => x.toLowerCase().includes(esperado.toLowerCase()));
    default: return true;
  }
}

export function esVisible(campo, datos) { return (campo._condiciones || []).every((c) => condicionCumplida(c, datos)); }

export function clavePara(titulo) {
  const base = String(titulo || 'cuestionario').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'cuestionario';
  let clave = base, n = 2;
  while (db.prepare('SELECT 1 FROM cuestionarios WHERE clave = ?').get(clave)) clave = `${base}-${n++}`;
  return clave;
}

// Revisión estructural de una definición escrita en el editor. Devuelve una lista de problemas (vacía si está bien).
export function validarDefinicion(def) {
  const problemas = [];
  if (!def || typeof def !== 'object') return ['La definición debe ser un objeto JSON.'];
  if (!String(def.titulo || '').trim()) problemas.push('El cuestionario necesita un título.');
  if (!Array.isArray(def.pasos) || !def.pasos.length) problemas.push('Debe haber al menos un paso.');
  const nombres = new Set();
  camposDe(normalizar(def)).forEach((c) => {
    if (!/^[a-z][a-z0-9_]{0,60}$/i.test(c.nombre)) problemas.push(`El identificador «${c.nombre}» solo admite letras, números y guion bajo, y debe empezar por letra.`);
    if (nombres.has(c.nombre)) problemas.push(`El identificador «${c.nombre}» está repetido.`);
    nombres.add(c.nombre);
    if (TIPOS[c.tipo] && TIPOS[c.tipo].opciones && !opcionesDe(c).length) problemas.push(`La pregunta «${c.etiqueta || c.nombre}» no tiene opciones.`);
    if (c.tipo === 'ranking' && !(c.items || []).length) problemas.push(`La pregunta «${c.etiqueta || c.nombre}» no tiene elementos para ordenar.`);
  });
  return problemas;
}

// ---------------------------------------------------------------- limpieza y validación de un envío
// `cuerpo` es el objeto de campos recibido (los nombres con [] llegan como arreglos) y `archivos` un objeto
// {campo: {nombre, tipo, datos}}. Devuelve {ok, errores, datos}.
export function validarEnvio(def, cuerpo, archivos = {}) {
  const d = normalizar(def);
  const campos = camposDe(d);
  const datos = {};
  const errores = [];
  const texto = (v) => (Array.isArray(v) ? v[0] : v == null ? '' : String(v)).trim();

  // Primera pasada: recoger valores crudos para poder evaluar condiciones.
  for (const c of campos) {
    const crudo = cuerpo[c.nombre];
    if (c.tipo === 'multiple') datos[c.nombre] = (Array.isArray(crudo) ? crudo : crudo == null || crudo === '' ? [] : [crudo]).map(String);
    else if (c.tipo === 'ranking') { const r = {}; for (const it of c.items || []) { const v = texto(cuerpo[it.nombre]); if (v) r[it.nombre] = Number(v); } datos[c.nombre] = r; }
    else if (c.tipo === 'archivo') datos[c.nombre] = archivos[c.nombre] ? { archivo: archivos[c.nombre].nombre, tipo: archivos[c.nombre].tipo, tamano: archivos[c.nombre].datos.length } : null;
    else if (c.tipo === 'casilla') datos[c.nombre] = texto(crudo) ? '1' : '';
    else datos[c.nombre] = texto(crudo);
    if (c.otro && cuerpo[`${c.nombre}_otro`] != null) datos[`${c.nombre}_otro`] = texto(cuerpo[`${c.nombre}_otro`]).slice(0, 500);
  }
  if (d.politicas.mostrar) {
    if (!texto(cuerpo.acepta_politicas)) errores.push({ campo: 'acepta_politicas', mensaje: 'Debe aceptar la política de tratamiento de datos.' });
    datos.acepta_politicas = '1';
  }

  // Segunda pasada: validar solo lo visible.
  for (const c of campos) {
    if (!esVisible(c, datos)) { delete datos[c.nombre]; delete datos[`${c.nombre}_otro`]; continue; }
    const v = datos[c.nombre];
    const et = c.etiqueta || c.nombre;
    const vacio = v == null || v === '' || (Array.isArray(v) && !v.length) || (c.tipo === 'ranking' && !Object.keys(v).length);
    if (c.requerido && vacio) { errores.push({ campo: c.nombre, mensaje: `Falta responder «${et}».` }); continue; }
    if (vacio) continue;
    switch (c.tipo) {
      case 'texto_corto': case 'entidad':
        if (v.length > 500) errores.push({ campo: c.nombre, mensaje: `«${et}» es demasiado largo.` });
        if (c.formato === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) errores.push({ campo: c.nombre, mensaje: `«${et}» no es un correo válido.` });
        if (c.formato === 'url' && !/^https?:\/\/\S+$/i.test(v)) errores.push({ campo: c.nombre, mensaje: `«${et}» debe ser una dirección web que empiece por http.` });
        break;
      case 'parrafo': if (v.length > 20000) errores.push({ campo: c.nombre, mensaje: `«${et}» es demasiado largo.` }); break;
      case 'numero': { const n = Number(v); if (Number.isNaN(n)) errores.push({ campo: c.nombre, mensaje: `«${et}» debe ser un número.` }); else { if (c.min != null && n < Number(c.min)) errores.push({ campo: c.nombre, mensaje: `«${et}» no puede ser menor que ${c.min}.` }); if (c.max != null && n > Number(c.max)) errores.push({ campo: c.nombre, mensaje: `«${et}» no puede ser mayor que ${c.max}.` }); datos[c.nombre] = n; } break; }
      case 'fecha': if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) errores.push({ campo: c.nombre, mensaje: `«${et}» debe ser una fecha.` }); break;
      case 'seleccion': case 'unica': case 'escala': case 'rubrica': case 'si_no':
        if (!opcionesDe(c).some((o) => o.valor === String(v))) errores.push({ campo: c.nombre, mensaje: `«${et}» tiene un valor que no está entre las opciones.` });
        break;
      case 'multiple': {
        const ops = new Set(opcionesDe(c).map((o) => o.valor));
        if (v.some((x) => !ops.has(x))) errores.push({ campo: c.nombre, mensaje: `«${et}» tiene un valor que no está entre las opciones.` });
        if (c.max && v.length > Number(c.max)) errores.push({ campo: c.nombre, mensaje: `En «${et}» solo puede elegir ${c.max} opciones.` });
        break;
      }
      case 'ranking': {
        const vals = Object.values(v);
        const items = c.items || [];
        if (vals.length < items.length) errores.push({ campo: c.nombre, mensaje: `Debe asignar un valor a cada elemento de «${et}».` });
        if (new Set(vals).size !== vals.length) errores.push({ campo: c.nombre, mensaje: `En «${et}» no puede repetir valores.` });
        if (vals.some((x) => Number.isNaN(x) || x < Number(c.min ?? 1) || x > Number(c.max ?? items.length))) errores.push({ campo: c.nombre, mensaje: `En «${et}» hay un valor fuera de rango.` });
        break;
      }
      case 'archivo': {
        const maxMb = Number(c.max_mb || 10);
        if (v.tamano > maxMb * 1024 * 1024) errores.push({ campo: c.nombre, mensaje: `El archivo de «${et}» supera ${maxMb} MB.` });
        if (!/\.(pdf|docx?|xlsx?|csv|txt|png|jpe?g|gif|webp|zip)$/i.test(v.archivo)) errores.push({ campo: c.nombre, mensaje: `El archivo de «${et}» debe ser PDF, Word, Excel, CSV, texto, imagen o ZIP.` });
        break;
      }
      case 'departamento': case 'municipio': if (v.length > 120) errores.push({ campo: c.nombre, mensaje: `«${et}» es demasiado largo.` }); break;
      default: break;
    }
  }
  return { ok: !errores.length, errores, datos };
}

// ---------------------------------------------------------------- puntajes por dimensión
export function calcularPuntajes(def, datos) {
  const d = normalizar(def);
  const acumulado = {};
  let total = 0, maxTotal = 0, n = 0;
  for (const c of camposDe(d)) {
    if (!TIPOS[c.tipo].numerica && c.tipo !== 'numero') continue;
    const v = Number(datos[c.nombre]);
    if (datos[c.nombre] == null || datos[c.nombre] === '' || Number.isNaN(v)) continue;
    const max = valorMaximo(c);
    const peso = Number(c.peso || 1);
    total += v * peso; maxTotal += max * peso; n++;
    if (c.dimension) {
      const a = acumulado[c.dimension] = acumulado[c.dimension] || { suma: 0, max: 0, n: 0 };
      a.suma += v * peso; a.max += max * peso; a.n++;
    }
  }
  const dimensiones = {};
  const declaradas = d.calculo.dimensiones.map((x) => x.clave);
  for (const clave of [...declaradas, ...Object.keys(acumulado).filter((k) => !declaradas.includes(k))]) {
    const a = acumulado[clave];
    if (!a) continue;
    const def = d.calculo.dimensiones.find((x) => x.clave === clave) || {};
    const promedio = a.n ? a.suma / a.n : null;
    dimensiones[clave] = { nombre: def.nombre || clave, suma: a.suma, max: a.max, n: a.n, promedio: promedio == null ? null : Math.round(promedio * 100) / 100,
      valor: d.calculo.modo === 'suma' ? a.suma : (promedio == null ? null : Math.round(promedio * 100) / 100),
      nivel: d.calculo.niveles && promedio != null ? (nivelDe(promedio) || {}).nombre || null : null };
  }
  const valores = Object.values(dimensiones).map((x) => x.promedio).filter((x) => x != null);
  const global = valores.length ? valores.reduce((s, x) => s + x, 0) / valores.length : (n ? total / n : null);
  return { dimensiones, total, max_total: maxTotal, n, promedio: n ? Math.round((total / n) * 100) / 100 : null,
    global: global == null ? null : Math.round(global * 100) / 100, nivel: d.calculo.niveles && global != null ? (nivelDe(global) || {}).nombre || null : null };
}

// ---------------------------------------------------------------- texto con formato ligero
// Admite **negritas**, saltos de línea y convierte direcciones web y correos en enlaces.
export function md(texto) {
  let t = esc(texto);
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(https?:\/\/[^\s<]+[^\s<.,;:)])/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  t = t.replace(/(^|[\s(])([\w.+-]+@[\w-]+\.[\w.-]+)/g, '$1<a href="mailto:$2">$2</a>');
  return t.replace(/\n/g, '<br>');
}

// ---------------------------------------------------------------- página pública
function etiquetaDe(c, conNumero = true) {
  const num = conNumero && c.numero != null && c.numero !== '' ? `${esc(c.numero)}. ` : '';
  return `${num}${esc(c.etiqueta || '')}${c.requerido ? ' <span class="req">*</span>' : ''}`;
}
const ayudaDe = (c, clase = 'mb-1') => (c.ayuda ? `<small class="form-text text-muted d-block ${clase}">${md(c.ayuda)}</small>` : '');
const otroDe = (c, valores) => (c.otro ? `<div class="otro-wrap" data-otro-de="${esc(c.nombre)}" data-otro-valor="${esc(c.otro.valor ?? 'Otros')}" hidden><input type="text" class="form-control" name="${esc(c.nombre)}_otro" maxlength="500" placeholder="${esc(c.otro.etiqueta || 'Especifique')}" value="${esc(valores[`${c.nombre}_otro`] || '')}"></div>` : '');
const id = (c, suf = '') => `c_${c.nombre}${suf}`;

function renderCampo(c, valores) {
  const v = valores[c.nombre];
  const sel = (x) => (v != null && String(v) === String(x) ? ' checked' : '');
  switch (c.tipo) {
    case 'seccion': return `<div class="section-header"><span class="section-badge">${esc(c.numero ?? '')}</span>${c.icono ? `<span class="section-icon" aria-hidden="true">${esc(c.icono)}</span>` : ''}<span class="section-title">${esc(c.titulo)}</span></div>`;
    case 'texto': return `<p class="texto-guia">${md(c.texto)}</p>`;
    case 'leyenda': return `<div class="legend-card"><h5 class="legend-title">${esc(c.titulo)}</h5>${c.descripcion ? `<p class="legend-desc">${md(c.descripcion)}</p>` : ''}<div class="legend-grid">${(c.items || []).map((it) => `<div class="legend-item legend-item--n${esc(it.nivel ?? '')}"><span class="legend-badge">${esc(it.etiqueta)}</span><span class="legend-text">${esc(it.texto)}</span></div>`).join('')}</div></div>`;
    case 'condicional': return `<div class="conditional-block" data-condicion='${esc(JSON.stringify(c.condicion || {}))}'>${(c.bloques || []).map((b) => envolver(b, renderCampo(b, valores))).join('')}</div>`;
    case 'texto_corto': case 'entidad': {
      const tipo = c.formato === 'email' ? 'email' : c.formato === 'url' ? 'url' : c.formato === 'tel' ? 'tel' : 'text';
      const extra = c.tipo === 'entidad' ? ' autocomplete="off" data-entidad="1"' : '';
      return `<label for="${id(c)}">${etiquetaDe(c)}</label><input type="${tipo}" class="form-control" id="${id(c)}" name="${esc(c.nombre)}" maxlength="500"${c.requerido ? ' required' : ''}${c.placeholder ? ` placeholder="${esc(c.placeholder)}"` : ''} value="${esc(v || '')}"${extra}>${c.tipo === 'entidad' ? '<div class="list-group entidad-sugerencias" hidden></div>' : ''}${ayudaDe(c)}`;
    }
    case 'numero': return `<label for="${id(c)}">${etiquetaDe(c)}</label><input type="number" class="form-control" id="${id(c)}" name="${esc(c.nombre)}"${c.min != null ? ` min="${esc(c.min)}"` : ''}${c.max != null ? ` max="${esc(c.max)}"` : ''}${c.requerido ? ' required' : ''} value="${esc(v ?? '')}">${ayudaDe(c)}`;
    case 'fecha': return `<label for="${id(c)}">${etiquetaDe(c)}</label><input type="date" class="form-control" id="${id(c)}" name="${esc(c.nombre)}"${c.requerido ? ' required' : ''} value="${esc(v || '')}">${ayudaDe(c)}`;
    case 'parrafo': return `<label for="${id(c)}">${etiquetaDe(c)}</label>${ayudaDe(c, 'mb-2')}<textarea class="form-control" id="${id(c)}" name="${esc(c.nombre)}" rows="${Number(c.filas || 4)}" maxlength="20000"${c.requerido ? ' required' : ''}${c.placeholder ? ` placeholder="${esc(c.placeholder)}"` : ''}>${esc(v || '')}</textarea>`;
    case 'seleccion': return `<label for="${id(c)}">${etiquetaDe(c)}</label>${ayudaDe(c, 'mb-2')}<select class="form-control" id="${id(c)}" name="${esc(c.nombre)}"${c.requerido ? ' required' : ''}${c.otro ? ' data-otro-select="1"' : ''}><option value="">Seleccione...</option>${opcionesDe(c).map((o) => `<option value="${esc(o.valor)}"${v != null && String(v) === o.valor ? ' selected' : ''}>${esc(o.texto)}</option>`).join('')}</select>${otroDe(c, valores)}`;
    case 'departamento': return `<label for="${id(c)}">${etiquetaDe(c)}</label><select class="form-control" id="${id(c)}" name="${esc(c.nombre)}"${c.requerido ? ' required' : ''} data-departamento="1" data-valor="${esc(v || '')}"><option value="">Seleccione...</option></select>${ayudaDe(c)}`;
    case 'municipio': return `<label for="${id(c)}">${etiquetaDe(c)}</label><select class="form-control" id="${id(c)}" name="${esc(c.nombre)}"${c.requerido ? ' required' : ''} data-municipio="${esc(c.depende_de || 'departamento')}" data-valor="${esc(v || '')}"><option value="">Seleccione primero un departamento...</option></select>${ayudaDe(c)}`;
    case 'unica': return `<div class="pregunta-grupo" id="${id(c, '_group')}"><label>${etiquetaDe(c)}</label>${ayudaDe(c)}${opcionesDe(c).map((o, i) => `<div class="form-check"><input class="form-check-input" type="radio" name="${esc(c.nombre)}" id="${id(c, '_' + i)}" value="${esc(o.valor)}"${c.requerido ? ' required' : ''}${sel(o.valor)}><label class="form-check-label" for="${id(c, '_' + i)}">${esc(o.texto)}</label></div>`).join('')}${otroDe(c, valores)}</div>`;
    case 'multiple': {
      const marcados = new Set((Array.isArray(v) ? v : []).map(String));
      const items = opcionesDe(c).map((o, i) => `<div class="form-check${c.en_linea ? ' form-check-inline' : ''}"><input class="form-check-input" type="checkbox" name="${esc(c.nombre)}[]" id="${id(c, '_' + i)}" value="${esc(o.valor)}"${marcados.has(o.valor) ? ' checked' : ''}><label class="form-check-label" for="${id(c, '_' + i)}">${esc(o.texto)}</label></div>`).join('');
      return `<label>${etiquetaDe(c)}</label>${ayudaDe(c)}<div class="${c.en_linea ? 'rubrica-escala' : 'checkbox-group'}" data-checkbox-group="${esc(c.nombre)}"${c.max ? ` data-max="${Number(c.max)}"` : ''}${c.requerido ? ' data-min="1"' : ''}>${items}</div>${c.max ? `<small class="form-text text-muted d-block mb-1">Seleccione máximo ${Number(c.max)} opciones.</small>` : ''}${otroDe(c, valores)}`;
    }
    case 'escala': {
      const ops = opcionesDe(c);
      return `<div class="likert-row"><label>${etiquetaDe(c)}</label>${ayudaDe(c)}<div class="likert-scale">${ops.map((o) => `<div class="likert-option"><input class="form-check-input" type="radio" name="${esc(c.nombre)}" id="${id(c, '_' + o.valor)}" value="${esc(o.valor)}"${c.requerido ? ' required' : ''}${sel(o.valor)}><label class="form-check-label" for="${id(c, '_' + o.valor)}">${esc(o.texto)}</label></div>`).join('')}</div>${c.extremos && c.extremos.length ? `<div class="likert-caption"><span>${esc(c.extremos[0])}</span><span>${esc(c.extremos[1] || '')}</span></div>` : ''}</div>`;
    }
    case 'rubrica': case 'si_no': {
      const ops = opcionesDe(c);
      return `<label>${etiquetaDe(c)}</label>${ayudaDe(c, 'mb-2')}<div class="rubrica-escala"${c.tipo === 'si_no' ? ' data-si-no="1"' : ''}>${ops.map((o) => `<div class="form-check form-check-inline"><input class="form-check-input" type="radio" name="${esc(c.nombre)}" id="${id(c, '_' + o.valor)}" value="${esc(o.valor)}"${c.requerido ? ' required' : ''}${sel(o.valor)}><label class="form-check-label" for="${id(c, '_' + o.valor)}">${c.tipo === 'rubrica' && /^\d+$/.test(o.valor) && !/^\d/.test(o.texto) ? `${esc(o.valor)} - ` : ''}${esc(o.texto)}</label></div>`).join('')}</div>`;
    }
    case 'ranking': {
      const n = Number(c.max ?? (c.items || []).length);
      const min = Number(c.min ?? 1);
      const vals = v && typeof v === 'object' ? v : {};
      return `<label>${etiquetaDe(c)}</label>${ayudaDe(c)}<div class="ranking" data-ranking="${esc(c.nombre)}">${(c.items || []).map((it) => `<div class="row align-items-center mb-2 ranking-fila"><div class="col-8">${esc(it.texto)}</div><div class="col-4"><select class="form-control ranking-select" name="${esc(it.nombre)}" required><option value="">--</option>${Array.from({ length: n - min + 1 }, (_, i) => i + min).map((k) => `<option value="${k}"${String(vals[it.nombre]) === String(k) ? ' selected' : ''}>${k}</option>`).join('')}</select></div></div>`).join('')}</div>`;
    }
    case 'archivo': return `<label for="${id(c)}" class="mt-2">${etiquetaDe(c, false)}</label><input type="file" class="form-control" id="${id(c)}" name="${esc(c.nombre)}"${c.acepta ? ` accept="${esc(c.acepta)}"` : ''}${c.requerido ? ' required' : ''} data-max-mb="${Number(c.max_mb || 10)}">${ayudaDe(c)}`;
    case 'casilla': return `<div class="form-check"><input class="form-check-input" type="checkbox" name="${esc(c.nombre)}" id="${id(c)}" value="1"${c.requerido ? ' required' : ''}${v ? ' checked' : ''}><label class="form-check-label" for="${id(c)}">${etiquetaDe(c)}</label></div>${ayudaDe(c)}`;
    default: return `<div class="alert alert-warning">Tipo de bloque desconocido: ${esc(c.tipo)}</div>`;
  }
}

function envolver(b, html) {
  if (['seccion', 'texto', 'leyenda', 'condicional'].includes(b.tipo)) return html;
  return `<div class="row"><div class="col-12 mb-3 pregunta" data-pregunta="${esc(b.nombre || '')}">${html}</div></div>`;
}

function bloquePoliticas(p, valores) {
  return `<div class="politicas"><strong>${esc(p.titulo)}</strong>${p.textos.map((t) => `<p>${md(t)}</p>`).join('')}
  <div class="form-group form-check mb-2"><input type="checkbox" class="form-check-input form-check-input-term" id="acepta_politicas" name="acepta_politicas" value="1" required${valores.acepta_politicas ? ' checked' : ''}><label class="form-check-label" for="acepta_politicas">${esc(p.etiqueta)} <span class="req">(*)</span></label></div></div>`;
}

// Página completa de diligenciamiento. `valores` permite prellenar campos (por ejemplo desde un enlace personal de campaña).
export function renderPublico({ definicion, clave, token = '', valores = {}, vistaPrevia = false, urlPublica = config.urlPublica }) {
  const d = normalizar(definicion);
  const total = d.pasos.length;
  const gate = d.politicas.mostrar && d.politicas.posicion !== 'final';
  const pasos = d.pasos.map((p, i) => {
    const n = i + 1;
    const ultimo = n === total;
    const cuerpo = p.bloques.map((b) => envolver(b, renderCampo(b, valores))).join('\n');
    const politicasFinal = ultimo && d.politicas.mostrar && d.politicas.posicion === 'final' ? bloquePoliticas(d.politicas, valores) : '';
    const nav = `<div class="step-nav">${n > 1 ? `<button type="button" class="btn-step btn-prev-step" id="btn-prev-${n}">&larr; Anterior</button>` : ''}${ultimo
      ? `<button type="submit" class="btn btn-primary btn-submit-step" id="btn-submit">${esc(d.cierre.boton)} &#10148;</button>`
      : `<button type="button" class="btn-step btn-next-step" id="btn-next-${n}">Continuar &rarr;</button>`}</div>`;
    return `<div class="form-step${n === 1 ? ' active' : ''}" data-step="${n}">${cuerpo}${politicasFinal}${nav}</div>`;
  }).join('\n');
  const indicador = d.pasos.map((p, i) => `<div class="step-item${i === 0 ? ' active' : ''}" data-step="${i + 1}"><div class="step-dot"><span>${i + 1}</span></div><div class="step-label">${esc(p.etiqueta)}</div></div>`).join('');
  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(d.titulo)}</title>
<link rel="icon" type="image/png" href="/static/img/escudo-unicartagena.png">
<link rel="preconnect" href="https://fonts.bunny.net">
<link href="https://fonts.bunny.net/css?family=instrument-sans:400,500,600&family=syne:600,700,800&family=plus-jakarta-sans:400,500,600,700" rel="stylesheet">
<link href="/static/vendor/bootstrap.min.css" rel="stylesheet">
<link href="/static/css/cuestionario.css" rel="stylesheet">
</head>
<body class="pagina-cuestionario">
${vistaPrevia ? '<div class="franja-vista-previa">Vista previa del cuestionario. Las respuestas que envíe aquí no se guardan.</div>' : ''}
<main class="cuestionario-marco">
<div class="contenido-formulario-inscripcion" id="presentacion">
  <div class="contenido-formulario-header">
    <div class="contenido-logo-group"><img src="/static/img/logo-mintic.png" alt="Ministerio TIC" class="contenido-img-titulo"><img src="/static/img/logo-unicartagena.png" alt="Universidad de Cartagena" class="contenido-img-titulo"></div>
    <h3 class="contenido-formulario-title">${esc(d.titulo)}</h3>
    ${d.subtitulo ? `<p class="contenido-formulario-subtitulo">${esc(d.subtitulo)}</p>` : ''}
  </div>
  ${d.intro.map((t) => `<p>${md(t)}</p>`).join('\n')}
  ${gate ? bloquePoliticas(d.politicas, valores) : ''}
</div>
<form id="cuestionario" class="cuestionario-form${gate ? '' : ' visible'}" method="post" action="/c/${esc(clave)}/enviar${vistaPrevia ? '?vista_previa=1' : ''}" enctype="multipart/form-data" novalidate
  data-clave="${esc(clave)}" data-total="${total}" data-borrador="cuestionario:${esc(clave)}:${esc(token || 'publico')}" data-existe="/c/${esc(clave)}/existe" data-duplicados='${esc(JSON.stringify(d.duplicados.campos))}'>
  <input type="hidden" name="_token" value="${esc(token)}">
  ${d.progreso.barra ? `<div class="steps-progress-meta"><span id="steps-progress-text">Paso 1 de ${total}</span><div class="steps-progress-bar"><div class="steps-progress-bar-fill" id="steps-progress-bar-fill" style="width:${Math.round(100 / total)}%"></div></div></div>` : ''}
  <div class="steps-progress" id="steps-progress"><div class="step-connector"></div>${indicador}</div>
  ${pasos}
</form>
<div class="contenido-formulario-inscripcion cierre" id="cierre" hidden>
  <div class="cierre-icono">&#10004;</div>
  <h3 class="contenido-formulario-title">${esc(d.cierre.titulo)}</h3>
  <p>${md(d.cierre.mensaje)}</p>
  <p class="cierre-pie">Observatorio Nacional de Inteligencia Artificial · Proyecto IA para el Estado · Universidad de Cartagena y Ministerio TIC</p>
</div>
</main>
<div class="aviso" id="aviso" hidden><div class="aviso-caja" role="dialog" aria-modal="true"><div class="aviso-icono" id="aviso-icono"></div><h4 id="aviso-titulo"></h4><p id="aviso-texto"></p><button type="button" class="btn btn-primary" id="aviso-cerrar">Entendido</button></div></div>
<script src="/static/js/cuestionario.js"></script>
</body>
</html>`;
}

// ---------------------------------------------------------------- persistencia
const filaCuestionario = (r) => r && ({ ...r, definicion: JSON.parse(r.definicion) });

export function listarCuestionarios() {
  return db.prepare(`SELECT c.*, (SELECT COUNT(*) FROM respuestas r WHERE r.cuestionario_id = c.id) AS respuestas,
      (SELECT MAX(enviado_en) FROM respuestas r WHERE r.cuestionario_id = c.id) AS ultima_respuesta,
      (SELECT COUNT(*) FROM campanias k WHERE k.cuestionario_id = c.id) AS campanias
    FROM cuestionarios c ORDER BY c.actualizado_en DESC`).all().map(filaCuestionario);
}
export function obtenerCuestionario(id) { return filaCuestionario(db.prepare('SELECT * FROM cuestionarios WHERE id = ?').get(id)); }
export function cuestionarioPorClave(clave) { return filaCuestionario(db.prepare('SELECT * FROM cuestionarios WHERE clave = ?').get(clave)); }

export function crearCuestionario({ titulo, definicion, clave = null, origen = 'propio', protegido = 0, estado = 'borrador', usuarioId = null }) {
  const d = normalizar(definicion);
  d.titulo = titulo || d.titulo;
  const k = clave || clavePara(d.titulo);
  const r = db.prepare('INSERT INTO cuestionarios (clave, titulo, definicion, origen, protegido, estado, creado_por) VALUES (?, ?, ?, ?, ?, ?, ?)')
    .run(k, d.titulo, JSON.stringify(d), origen, protegido ? 1 : 0, estado, usuarioId);
  return obtenerCuestionario(r.lastInsertRowid);
}

export function actualizarCuestionario(id, { definicion, titulo }) {
  const d = normalizar(definicion);
  if (titulo) d.titulo = titulo;
  db.prepare("UPDATE cuestionarios SET titulo = ?, definicion = ?, version = version + 1, actualizado_en = datetime('now') WHERE id = ?").run(d.titulo, JSON.stringify(d), id);
  return obtenerCuestionario(id);
}

export function cambiarEstado(id, estado) {
  if (!['borrador', 'publicado', 'cerrado'].includes(estado)) throw new Error('Estado no válido');
  db.prepare("UPDATE cuestionarios SET estado = ?, actualizado_en = datetime('now') WHERE id = ?").run(estado, id);
}

export function duplicarCuestionario(id, usuarioId) {
  const c = obtenerCuestionario(id);
  if (!c) return null;
  const d = c.definicion;
  d.titulo = `${d.titulo} (copia)`;
  return crearCuestionario({ titulo: d.titulo, definicion: d, origen: 'propio', protegido: 0, estado: 'borrador', usuarioId });
}

export function eliminarCuestionario(id) {
  db.prepare('DELETE FROM respuestas WHERE cuestionario_id = ?').run(id);
  db.prepare('DELETE FROM destinatarios WHERE campania_id IN (SELECT id FROM campanias WHERE cuestionario_id = ?)').run(id);
  db.prepare('DELETE FROM campanias WHERE cuestionario_id = ?').run(id);
  db.prepare('DELETE FROM cuestionarios WHERE id = ?').run(id);
  fs.rmSync(carpetaArchivos(id), { recursive: true, force: true });
}

export function carpetaArchivos(cuestionarioId, respuestaId = null) {
  const base = path.join(path.dirname(path.resolve(config.rutaBd)), 'archivos', String(cuestionarioId));
  return respuestaId ? path.join(base, String(respuestaId)) : base;
}

export function existeDuplicado(cuestionario, campo, valor) {
  const d = normalizar(cuestionario.definicion);
  if (!d.duplicados.campos.includes(campo) || !valor) return false;
  const v = String(valor).trim().toLowerCase();
  const r = db.prepare("SELECT 1 FROM respuestas WHERE cuestionario_id = ? AND lower(trim(json_extract(datos, '$.' || ?))) = ? LIMIT 1").get(cuestionario.id, campo, v);
  return !!r;
}

export function guardarRespuesta({ cuestionario, datos, archivos = {}, campaniaId = null, destinatarioId = null, ip = '', agente = '', enviadoEn = null }) {
  const d = normalizar(cuestionario.definicion);
  const puntajes = calcularPuntajes(d, datos);
  const idn = d.identificacion || {};
  const tomar = (k) => (idn[k] && datos[idn[k]] != null ? String(datos[idn[k]]).slice(0, 300) : null);
  const r = db.prepare(`INSERT INTO respuestas (cuestionario_id, campania_id, destinatario_id, datos, puntajes, correo, nombre, entidad, ip, agente, enviado_en)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))`)
    .run(cuestionario.id, campaniaId, destinatarioId, JSON.stringify(datos), JSON.stringify(puntajes), tomar('correo'), tomar('nombre'), tomar('entidad'), ip, String(agente || '').slice(0, 200), enviadoEn);
  const respuestaId = Number(r.lastInsertRowid);
  // Archivos adjuntos: se guardan en disco, fuera de la base de datos, y en los datos queda la referencia.
  const nombres = Object.keys(archivos);
  if (nombres.length) {
    const carpeta = carpetaArchivos(cuestionario.id, respuestaId);
    fs.mkdirSync(carpeta, { recursive: true });
    for (const campo of nombres) {
      const a = archivos[campo];
      const seguro = String(a.nombre || 'archivo').replace(/[^\w.\-]+/g, '_').slice(-120);
      fs.writeFileSync(path.join(carpeta, `${campo}__${seguro}`), a.datos);
      datos[campo] = { archivo: a.nombre, tipo: a.tipo, tamano: a.datos.length, ruta: `${campo}__${seguro}` };
    }
    db.prepare('UPDATE respuestas SET datos = ? WHERE id = ?').run(JSON.stringify(datos), respuestaId);
  }
  if (destinatarioId) db.prepare("UPDATE destinatarios SET estado = 'respondido', respondido_en = datetime('now'), respuesta_id = ? WHERE id = ?").run(respuestaId, destinatarioId);
  auditar('respuesta', { app: 'cuestionarios', detalle: `${cuestionario.clave} #${respuestaId}`, ip });
  return respuestaId;
}

export function listarRespuestas(cuestionarioId, { campaniaId = null, desde = null, hasta = null, buscar = '', limite = 5000 } = {}) {
  let sql = 'SELECT * FROM respuestas WHERE cuestionario_id = ?';
  const params = [cuestionarioId];
  if (campaniaId) { sql += ' AND campania_id = ?'; params.push(campaniaId); }
  if (desde) { sql += ' AND enviado_en >= ?'; params.push(desde); }
  if (hasta) { sql += ' AND enviado_en <= ?'; params.push(hasta + ' 23:59:59'); }
  if (buscar) { sql += ' AND (lower(datos) LIKE ? OR lower(coalesce(correo, \'\')) LIKE ?)'; const b = `%${buscar.toLowerCase()}%`; params.push(b, b); }
  sql += ' ORDER BY enviado_en DESC, id DESC LIMIT ?'; params.push(limite);
  return db.prepare(sql).all(...params).map((r) => ({ ...r, datos: JSON.parse(r.datos), puntajes: JSON.parse(r.puntajes || '{}') }));
}
export function obtenerRespuesta(id) { const r = db.prepare('SELECT * FROM respuestas WHERE id = ?').get(id); return r && { ...r, datos: JSON.parse(r.datos), puntajes: JSON.parse(r.puntajes || '{}') }; }
export function eliminarRespuesta(id) {
  const r = obtenerRespuesta(id);
  if (!r) return;
  db.prepare('DELETE FROM respuestas WHERE id = ?').run(id);
  if (r.destinatario_id) db.prepare("UPDATE destinatarios SET estado = 'enviado', respondido_en = NULL, respuesta_id = NULL WHERE id = ?").run(r.destinatario_id);
  fs.rmSync(carpetaArchivos(r.cuestionario_id, id), { recursive: true, force: true });
}

// ---------------------------------------------------------------- resúmenes para el tablero
export function resumenRespuestas(def, filas) {
  const d = normalizar(def);
  const campos = camposDe(d);
  const hoy = new Date().toISOString().slice(0, 10);
  const porDia = new Map();
  for (let i = 29; i >= 0; i--) { const f = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10); porDia.set(f, 0); }
  let recibidasHoy = 0;
  for (const r of filas) { const f = String(r.enviado_en).slice(0, 10); if (porDia.has(f)) porDia.set(f, porDia.get(f) + 1); if (f === hoy) recibidasHoy++; }
  const conteos = {};
  const promedios = {};
  for (const c of campos) {
    if (['seleccion', 'unica', 'multiple', 'si_no', 'rubrica', 'departamento', 'municipio', 'escala', 'casilla'].includes(c.tipo)) {
      const m = new Map();
      for (const r of filas) { const v = r.datos[c.nombre]; if (v == null || v === '') continue; for (const x of Array.isArray(v) ? v : [v]) m.set(String(x), (m.get(String(x)) || 0) + 1); }
      const orden = TIPOS[c.tipo].opciones || TIPOS[c.tipo].numerica ? opcionesDe(c).map((o) => o.valor) : [...m.keys()].sort((a, b) => (m.get(b) || 0) - (m.get(a) || 0));
      conteos[c.nombre] = orden.filter((k) => m.has(k)).map((k) => ({ valor: k, texto: textoDeOpcion(c, k), n: m.get(k) }));
      for (const [k, n] of m) if (!orden.includes(k)) conteos[c.nombre].push({ valor: k, texto: k, n });
    }
    if (TIPOS[c.tipo].numerica || c.tipo === 'numero') {
      const vals = filas.map((r) => Number(r.datos[c.nombre])).filter((x) => !Number.isNaN(x) && filas.length);
      const validos = filas.filter((r) => r.datos[c.nombre] != null && r.datos[c.nombre] !== '').map((r) => Number(r.datos[c.nombre])).filter((x) => !Number.isNaN(x));
      if (validos.length) promedios[c.nombre] = { etiqueta: c.etiqueta, dimension: c.dimension || null, promedio: Math.round((validos.reduce((s, x) => s + x, 0) / validos.length) * 100) / 100, max: valorMaximo(c), n: validos.length };
      void vals;
    }
  }
  const dimensiones = {};
  for (const dim of d.calculo.dimensiones) {
    const vals = filas.map((r) => r.puntajes && r.puntajes.dimensiones && r.puntajes.dimensiones[dim.clave]).filter(Boolean);
    if (!vals.length) continue;
    const prom = (k) => Math.round((vals.reduce((s, x) => s + (x[k] || 0), 0) / vals.length) * 100) / 100;
    dimensiones[dim.clave] = { nombre: dim.nombre, descripcion: dim.descripcion || '', n: vals.length, suma: prom('suma'), promedio: prom('promedio'), max: vals[0].max,
      valor: d.calculo.modo === 'suma' ? prom('suma') : prom('promedio'), nivel: d.calculo.niveles ? (nivelDe(prom('promedio')) || {}).nombre || null : null };
  }
  const totales = filas.map((r) => r.puntajes && r.puntajes.total).filter((x) => typeof x === 'number');
  const indicadores = (d.tablero.indicadores || []).map((ind) => {
    const n = filas.filter((r) => { const v = r.datos[ind.campo]; const lista = (Array.isArray(v) ? v : [v]).map(String); return (ind.contar || []).some((c) => lista.some((x) => (ind.empieza_por ? x.startsWith(c) : x === c))); }).length;
    return { nombre: ind.nombre, n };
  });
  return { total: filas.length, recibidasHoy, porDia: [...porDia.entries()].map(([dia, n]) => ({ dia, n })), conteos, promedios, dimensiones, indicadores,
    puntajePromedio: totales.length ? Math.round((totales.reduce((s, x) => s + x, 0) / totales.length) * 10) / 10 : null,
    puntajeMax: filas.length && filas[0].puntajes ? filas[0].puntajes.max_total : null,
    entidades: new Set(filas.map((r) => (r.entidad || '').trim().toLowerCase()).filter(Boolean)).size };
}

// Resumen de todos los cuestionarios publicados para la portada y el cuadro de mando del Observatorio.
export function resumenParaTablero() {
  return listarCuestionarios().filter((c) => c.estado !== 'borrador' || c.respuestas > 0).map((c) => {
    const filas = listarRespuestas(c.id, { limite: 100000 });
    const r = resumenRespuestas(c.definicion, filas);
    return { id: c.id, clave: c.clave, titulo: c.definicion.titulo, estado: c.estado, respuestas: r.total, ultima: c.ultima_respuesta, entidades: r.entidades, dimensiones: r.dimensiones, niveles: !!c.definicion.calculo.niveles, campanias: c.campanias };
  });
}

// ---------------------------------------------------------------- exportación
export function csvDe(def, filas) {
  const d = normalizar(def);
  const campos = camposDe(d);
  const cab = ['id', 'fecha', 'campaña', 'correo', 'nombre', 'entidad', ...campos.flatMap((c) => (c.otro ? [c.nombre, `${c.nombre}_otro`] : c.tipo === 'ranking' ? (c.items || []).map((it) => it.nombre) : [c.nombre])), ...d.calculo.dimensiones.map((x) => `puntaje_${x.clave}`), 'puntaje_total', 'puntaje_maximo'];
  const celda = (v) => { const s = v == null ? '' : Array.isArray(v) ? v.join(' | ') : typeof v === 'object' ? (v.archivo || JSON.stringify(v)) : String(v); return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const lineas = [cab.join(';')];
  for (const r of filas) {
    const fila = [r.id, r.enviado_en, r.campania_id || '', r.correo || '', r.nombre || '', r.entidad || ''];
    for (const c of campos) {
      if (c.tipo === 'ranking') { const v = r.datos[c.nombre] || {}; for (const it of c.items || []) fila.push(v[it.nombre] ?? ''); continue; }
      fila.push(r.datos[c.nombre]);
      if (c.otro) fila.push(r.datos[`${c.nombre}_otro`]);
    }
    for (const x of d.calculo.dimensiones) fila.push(r.puntajes && r.puntajes.dimensiones && r.puntajes.dimensiones[x.clave] ? r.puntajes.dimensiones[x.clave].valor : '');
    fila.push(r.puntajes ? r.puntajes.total : '', r.puntajes ? r.puntajes.max_total : '');
    lineas.push(fila.map(celda).join(';'));
  }
  return '\uFEFF' + lineas.join('\r\n');
}

// ---------------------------------------------------------------- ejemplos de fábrica
// Los tres instrumentos ya aplicados por el proyecto se cargan como ejemplos protegidos la primera vez que arranca el portal.
export const EJEMPLOS = [
  { clave: 'informacion-no-verificada', archivo: 'informacion-no-verificada.json' },
  { clave: 'autodiagnostico-integrado', archivo: 'autodiagnostico-integrado.json' },
  { clave: 'diagnostico-infraestructura', archivo: 'diagnostico-infraestructura.json' },
];
export function sembrarEjemplos() {
  let n = 0;
  for (const e of EJEMPLOS) {
    if (cuestionarioPorClave(e.clave)) continue;
    const ruta = path.join(RAIZ, 'ejemplos', e.archivo);
    if (!fs.existsSync(ruta)) continue;
    const def = JSON.parse(fs.readFileSync(ruta, 'utf8'));
    crearCuestionario({ titulo: def.titulo, definicion: def, clave: e.clave, origen: 'ejemplo', protegido: 1, estado: 'publicado' });
    n++;
  }
  return n;
}

export function tokenNuevo() { return crypto.randomBytes(18).toString('base64url'); }

// ---------------------------------------------------------------- importación desde hojas de cálculo
// Trae las respuestas que ya se recogieron con los formularios anteriores (exportadas a Excel o CSV) dentro de una campaña.
const normTexto = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/^\d+[.)]\s*/, '').replace(/\s*\(?\*\)?\s*$/, '').replace(/[^a-z0-9]+/g, ' ').trim();
function similitud(a, b) {
  if (!a || !b) return 0;
  if (a === b) return 1;
  const big = (s) => { const out = new Map(); for (let i = 0; i < s.length - 1; i++) { const k = s.slice(i, i + 2); out.set(k, (out.get(k) || 0) + 1); } return out; };
  const A = big(a), B = big(b);
  let comun = 0;
  for (const [k, n] of A) if (B.has(k)) comun += Math.min(n, B.get(k));
  return (2 * comun) / ((a.length - 1) + (b.length - 1));
}

// Destinos posibles de una columna: cada pregunta, los campos «otro», los elementos de un ranking y la fecha de envío.
export function destinosDeImportacion(def) {
  const d = normalizar(def);
  const out = [{ clave: '_fecha', texto: 'Fecha de envío', claves: ['fecha', 'fecha de envio', 'enviado en', 'created at', 'registrado', 'fecha registro', 'fecha de registro', 'fecha de diligenciamiento'] }];
  for (const c of camposDe(d)) {
    if (c.tipo === 'ranking') { for (const it of c.items || []) out.push({ clave: `${c.nombre}::${it.nombre}`, texto: `${c.etiqueta} · ${it.texto}`, claves: [normTexto(it.texto), normTexto(it.nombre)], campo: c, item: it }); continue; }
    out.push({ clave: c.nombre, texto: `${c.numero != null && c.numero !== '' ? c.numero + '. ' : ''}${c.etiqueta}`, claves: [normTexto(c.etiqueta), normTexto(c.nombre), normTexto(c.nombre.replace(/_/g, ' '))], campo: c });
    if (c.otro) out.push({ clave: `${c.nombre}_otro`, texto: `${c.etiqueta} · ${c.otro.etiqueta || 'Otro, ¿cuál?'}`, claves: [normTexto(c.etiqueta) + ' otro', normTexto(c.nombre) + ' otro', normTexto(c.nombre.replace(/_/g, ' ')) + ' otro', normTexto(c.etiqueta) + ' especifique'], campo: c, otro: true });
  }
  return out;
}

// Para cada columna del archivo propone el destino más parecido (o ninguno).
export function sugerirMapeo(def, columnas) {
  const destinos = destinosDeImportacion(def);
  const usados = new Set();
  return columnas.map((col, i) => {
    const n = normTexto(col);
    let mejor = null, puntaje = 0;
    for (const dst of destinos) {
      if (usados.has(dst.clave)) continue;
      for (const k of dst.claves) {
        const s = k === n ? 1 : similitud(n, k);
        if (s > puntaje) { puntaje = s; mejor = dst; }
      }
    }
    if (mejor && puntaje >= 0.55) { usados.add(mejor.clave); return { indice: i, columna: col, destino: mejor.clave, confianza: Math.round(puntaje * 100) }; }
    return { indice: i, columna: col, destino: '', confianza: 0 };
  });
}

// Fecha escrita como dd/mm/aaaa hh:mm, aaaa-mm-dd hh:mm o ISO, en hora de Colombia, a UTC para la base de datos.
export function fechaAIso(texto) {
  const t = String(texto || '').trim();
  if (!t) return null;
  let m = /^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?/.exec(t);
  let d;
  if (m) d = new Date(`${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}T${(m[4] || '0').padStart(2, '0')}:${m[5] || '00'}:${m[6] || '00'}-05:00`);
  else if ((m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?(Z|[+-]\d{2}:?\d{2})?/.exec(t))) d = new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4] || '00'}:${m[5] || '00'}:${m[6] || '00'}${m[7] ? m[7] : '-05:00'}`);
  else d = new Date(t);
  return Number.isNaN(d.getTime()) ? null : d.toISOString().slice(0, 19).replace('T', ' ');
}

function valorImportado(c, crudo) {
  const t = String(crudo ?? '').trim();
  if (t === '') return c.tipo === 'multiple' ? [] : '';
  const ops = opcionesDe(c);
  const buscar = (x) => { const n = normTexto(x); return ops.find((o) => normTexto(o.texto) === n || normTexto(o.valor) === n) || ops.find((o) => n && (normTexto(o.texto).startsWith(n) || n.startsWith(normTexto(o.texto)))); };
  switch (c.tipo) {
    case 'multiple': {
      const partes = t.includes(';') || t.includes('|') ? t.split(/\s*[;|]\s*/) : (buscar(t) ? [t] : t.split(/\s*,\s*(?=[A-ZÁÉÍÓÚ])/));
      return partes.map((p) => p.trim()).filter(Boolean).map((p) => { const o = buscar(p); return o ? o.valor : p; });
    }
    case 'si_no': { const n = normTexto(t); if (['1', 'si', 'yes', 'true', 'verdadero', 'x'].includes(n)) return '1'; if (['0', 'no', 'false', 'falso'].includes(n)) return '0'; return t; }
    case 'escala': case 'rubrica': { const num = /^\s*(\d+)/.exec(t); if (num && ops.some((o) => o.valor === num[1])) return num[1]; const o = buscar(t); return o ? o.valor : t; }
    case 'seleccion': case 'unica': { const o = buscar(t); return o ? o.valor : t; }
    case 'numero': { const n = Number(t.replace(',', '.')); return Number.isNaN(n) ? t : n; }
    case 'casilla': return ['1', 'si', 'sí', 'x', 'true', 'verdadero'].includes(t.toLowerCase()) ? '1' : '';
    case 'archivo': return t ? { archivo: t, importado: true } : null;
    default: return t.slice(0, 20000);
  }
}

// Convierte una fila del archivo en los datos de una respuesta según el mapeo {indiceColumna: destino}.
export function filaARespuesta(def, mapeo, fila) {
  const d = normalizar(def);
  const campos = camposDe(d);
  const datos = {}; let fecha = null;
  for (const [i, destino] of Object.entries(mapeo)) {
    if (!destino) continue;
    const crudo = fila[Number(i)];
    if (destino === '_fecha') { fecha = fechaAIso(crudo); continue; }
    if (destino.includes('::')) { const [nombre, item] = destino.split('::'); const v = Number(String(crudo).trim()); if (!Number.isNaN(v) && String(crudo).trim() !== '') { datos[nombre] = datos[nombre] || {}; datos[nombre][item] = v; } continue; }
    if (destino.endsWith('_otro') && !campos.some((c) => c.nombre === destino)) { if (String(crudo ?? '').trim()) datos[destino] = String(crudo).trim().slice(0, 500); continue; }
    const c = campos.find((x) => x.nombre === destino);
    if (!c) continue;
    const v = valorImportado(c, crudo);
    if (v !== '' && v !== null && !(Array.isArray(v) && !v.length)) datos[c.nombre] = v;
  }
  if (d.politicas.mostrar) datos.acepta_politicas = '1';
  datos._importado = true;
  return { datos, fecha, vacia: !Object.keys(datos).some((k) => !k.startsWith('_') && k !== 'acepta_politicas') };
}

export function importarRespuestas({ cuestionario, campaniaId, mapeo, filas, omitirDuplicados = true, usuarioId = null }) {
  const d = normalizar(cuestionario.definicion);
  const idn = d.identificacion || {};
  let importadas = 0, omitidas = 0, vacias = 0;
  const problemas = [];
  const insDest = db.prepare("INSERT INTO destinatarios (campania_id, correo, nombre, entidad, token, estado, respondido_en, respuesta_id) VALUES (?, ?, ?, ?, ?, 'respondido', ?, ?)");
  filas.forEach((fila, n) => {
    const { datos, fecha, vacia } = filaARespuesta(d, mapeo, fila);
    if (vacia) { vacias++; return; }
    if (omitirDuplicados && d.duplicados.campos.some((campo) => datos[campo] && existeDuplicado(cuestionario, campo, datos[campo]))) { omitidas++; return; }
    try {
      const id = guardarRespuesta({ cuestionario, datos, campaniaId, ip: 'importación', agente: `importación de archivo por usuario ${usuarioId || ''}`, enviadoEn: fecha });
      const correo = idn.correo && datos[idn.correo] ? String(datos[idn.correo]).toLowerCase().trim() : '';
      if (campaniaId && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correo) && !db.prepare('SELECT 1 FROM destinatarios WHERE campania_id = ? AND correo = ?').get(campaniaId, correo)) {
        insDest.run(campaniaId, correo, idn.nombre ? String(datos[idn.nombre] || '').slice(0, 200) || null : null, idn.entidad ? String(datos[idn.entidad] || '').slice(0, 300) || null : null, tokenNuevo(), fecha || new Date().toISOString().slice(0, 19).replace('T', ' '), id);
      }
      importadas++;
    } catch (e) { problemas.push(`Fila ${n + 2}: ${e.message}`); }
  });
  auditar('importacion', { usuarioId, app: 'cuestionarios', detalle: `${cuestionario.clave}: ${importadas} importadas, ${omitidas} duplicadas, ${vacias} vacías` });
  return { importadas, omitidas, vacias, problemas };
}

export function carpetaImportaciones() {
  const c = path.join(path.dirname(path.resolve(config.rutaBd)), 'importaciones');
  fs.mkdirSync(c, { recursive: true });
  return c;
}
