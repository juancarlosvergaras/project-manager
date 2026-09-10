// Páginas de administración del módulo de cuestionarios: lista, editor, resultados y campañas.
import { pagina } from './vistas.js';
import { normalizar, camposDe, opcionesDe, textoDeOpcion, TIPOS, POLITICA_MINTIC, POLITICA_UDEC, DEFINICION_VACIA } from './cuestionarios.js';
import { CUERPO_POR_DEFECTO, aLocal, enlaceDe, periodoActual } from './campanias.js';
import { config } from './config.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n, d = 0) => Number(n || 0).toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d });
const fechaCo = (iso) => {
  if (!iso) return '';
  const d = new Date(String(iso).includes('T') ? iso : String(iso).replace(' ', 'T') + 'Z');
  if (Number.isNaN(d.getTime())) return String(iso);
  return new Intl.DateTimeFormat('es-CO', { timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(d).replace(',', '');
};
const jsonSeguro = (o) => JSON.stringify(o).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
const PALETA = ['#184fa4', '#1d63d4', '#2f9e63', '#e9b121', '#7c4dff', '#0fb5c8', '#ce1126', '#60718a', '#0d3272', '#b5880d'];
const badgeEstado = (e) => ({ borrador: '<span class="badge bg-secondary">Borrador</span>', publicado: '<span class="badge bg-success">Publicado</span>', cerrado: '<span class="badge bg-dark">Cerrado</span>' }[e] || esc(e));
const badgeCampania = (e) => ({ borrador: '<span class="badge bg-secondary">Sin enviar</span>', programada: '<span class="badge bg-warning text-dark">Programada</span>', enviando: '<span class="badge bg-info text-dark">Enviando</span>', enviada: '<span class="badge bg-success">Enviada</span>', cancelada: '<span class="badge bg-dark">Cancelada</span>', importada: '<span class="badge bg-info text-dark">Importada de archivo</span>' }[e] || esc(e));
const badgeDestinatario = (e) => ({ pendiente: '<span class="badge bg-secondary">Pendiente</span>', enviado: '<span class="badge bg-primary">Enviado</span>', respondido: '<span class="badge bg-success">Respondió</span>', error: '<span class="badge bg-danger">Error</span>' }[e] || esc(e));

// ---------------------------------------------------------------- gráficos SVG
function donut(series, titulo) {
  const total = series.reduce((s, x) => s + x.n, 0);
  if (!total) return `<p class="text-muted small mb-0">Sin datos para «${esc(titulo)}».</p>`;
  const R = 54, r = 34, cx = 70, cy = 70;
  let ang = -Math.PI / 2, paths = '';
  series.forEach((s, i) => {
    const a = (s.n / total) * Math.PI * 2;
    const x1 = cx + R * Math.cos(ang), y1 = cy + R * Math.sin(ang), x2 = cx + R * Math.cos(ang + a), y2 = cy + R * Math.sin(ang + a);
    const xi1 = cx + r * Math.cos(ang + a), yi1 = cy + r * Math.sin(ang + a), xi2 = cx + r * Math.cos(ang), yi2 = cy + r * Math.sin(ang);
    const grande = a > Math.PI ? 1 : 0;
    paths += a >= Math.PI * 2 - 0.0001
      ? `<circle cx="${cx}" cy="${cy}" r="${(R + r) / 2}" fill="none" stroke="${PALETA[i % PALETA.length]}" stroke-width="${R - r}"><title>${esc(s.texto)}: ${s.n}</title></circle>`
      : `<path d="M${x1.toFixed(2)},${y1.toFixed(2)} A${R},${R} 0 ${grande} 1 ${x2.toFixed(2)},${y2.toFixed(2)} L${xi1.toFixed(2)},${yi1.toFixed(2)} A${r},${r} 0 ${grande} 0 ${xi2.toFixed(2)},${yi2.toFixed(2)} Z" fill="${PALETA[i % PALETA.length]}"><title>${esc(s.texto)}: ${s.n} (${Math.round((s.n / total) * 100)} %)</title></path>`;
    ang += a;
  });
  const leyenda = series.map((s, i) => `<li><span class="leyenda-punto" style="background:${PALETA[i % PALETA.length]}"></span>${esc(s.texto.length > 34 ? s.texto.slice(0, 33) + '…' : s.texto)} <span class="text-muted">${s.n} · ${Math.round((s.n / total) * 100)} %</span></li>`).join('');
  return `<div class="grafico-dona"><svg viewBox="0 0 140 140" role="img" aria-label="${esc(titulo)}">${paths}<text x="70" y="75" text-anchor="middle" font-size="18" font-weight="700" fill="#1a2540">${total}</text></svg><ul class="leyenda-dona">${leyenda}</ul></div>`;
}
function barrasH(items) {
  if (!items.length) return '<p class="text-muted small mb-0">Sin datos.</p>';
  return `<div class="barras-h">${items.map((it, i) => `<div class="barra-h"><div class="barra-h-etiqueta" title="${esc(it.texto)}">${esc(it.texto.length > 46 ? it.texto.slice(0, 45) + '…' : it.texto)}</div><div class="barra-h-pista"><div class="barra-h-relleno" style="width:${it.max ? Math.min(100, Math.round((it.valor / it.max) * 100)) : 0}%;background:${PALETA[i % PALETA.length]}"></div></div><div class="barra-h-valor">${fmt(it.valor, 2)}${it.max ? ` / ${fmt(it.max)}` : ''}</div></div>`).join('')}</div>`;
}
function barrasDia(serie) {
  const W = 560, H = 150, pl = 30, pb = 26, pt = 8, max = Math.max(...serie.map((s) => s.n), 1);
  const bw = Math.max(6, (W - pl - 10) / serie.length - 4);
  const sx = (i) => pl + (i + 0.5) * ((W - pl - 10) / serie.length), sy = (v) => pt + (1 - v / max) * (H - pb - pt);
  let out = `<svg viewBox="0 0 ${W} ${H}" class="grafico" role="img" aria-label="Respuestas por día">`;
  for (let t = 0; t <= 3; t++) { const v = Math.round((max * t) / 3); const y = sy(v); out += `<line x1="${pl}" x2="${W - 6}" y1="${y}" y2="${y}" class="g"/><text x="${pl - 6}" y="${y + 3}" text-anchor="end">${v}</text>`; }
  serie.forEach((s, i) => { const x = sx(i) - bw / 2, y = sy(s.n); out += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${(sy(0) - y).toFixed(1)}" rx="2" class="barra"><title>${esc(s.dia)}: ${s.n}</title></rect>`; if (i % 5 === 0) out += `<text x="${sx(i)}" y="${H - 8}" text-anchor="middle">${esc(s.dia.slice(5).replace('-', '/'))}</text>`; });
  return out + '</svg>';
}

// ---------------------------------------------------------------- lista
export function vistaCuestionarios({ usuario, apps, ids, lista, mensaje = '', smtpOk }) {
  const filas = lista.map((c) => {
    const d = normalizar(c.definicion);
    const preguntas = camposDe(d).length;
    const enlace = `${config.urlPublica}/c/${c.clave}`;
    return `<tr>
      <td><a class="fw-semibold" href="/cuestionarios/${c.id}">${esc(d.titulo)}</a><div class="small text-muted">${badgeEstado(c.estado)} ${c.origen === 'ejemplo' ? '<span class="badge bg-info text-dark">Ejemplo del proyecto</span>' : ''} · ${d.pasos.length} pasos · ${preguntas} preguntas · versión ${c.version}</div></td>
      <td class="text-end"><a href="/cuestionarios/${c.id}">${fmt(c.respuestas)}</a><div class="small text-muted">${c.ultima_respuesta ? fechaCo(c.ultima_respuesta) : 'sin respuestas'}</div></td>
      <td class="text-end"><a href="/cuestionarios/${c.id}/campanias">${fmt(c.campanias)}</a></td>
      <td><div class="input-group input-group-sm"><input class="form-control" readonly value="${esc(enlace)}"><button class="btn btn-outline-secondary" type="button" data-copiar="${esc(enlace)}">Copiar</button></div><div class="d-flex align-items-center gap-2 mt-1"><img class="qr-mini" src="/c/${esc(c.clave)}/qr.svg?pie=0" alt="QR de ${esc(d.titulo)}"><a class="small" href="/c/${esc(c.clave)}/qr.svg?descargar=1">Descargar QR</a></div></td>
      <td class="text-nowrap"><div class="btn-group btn-group-sm">
        <a class="btn btn-outline-primary" href="/cuestionarios/${c.id}">Resultados</a>
        <a class="btn btn-outline-primary" href="/cuestionarios/${c.id}/editar">Editar</a>
        <a class="btn btn-outline-primary" href="/cuestionarios/${c.id}/campanias">Campañas</a>
        <a class="btn btn-outline-secondary" href="/c/${esc(c.clave)}?vista_previa=1" target="_blank" rel="noopener">Vista previa</a>
      </div>
      <div class="btn-group btn-group-sm mt-1">
        <form method="post" action="/cuestionarios/${c.id}/duplicar" class="d-inline"><button class="btn btn-outline-secondary">Duplicar</button></form>
        ${c.estado !== 'publicado' ? `<form method="post" action="/cuestionarios/${c.id}/estado" class="d-inline"><input type="hidden" name="estado" value="publicado"><button class="btn btn-outline-success">Publicar</button></form>` : `<form method="post" action="/cuestionarios/${c.id}/estado" class="d-inline"><input type="hidden" name="estado" value="cerrado"><button class="btn btn-outline-dark">Cerrar</button></form>`}
        ${c.protegido ? '' : `<form method="post" action="/cuestionarios/${c.id}/eliminar" class="d-inline" data-confirmar="Se eliminará el cuestionario «${esc(d.titulo)}» con sus ${c.respuestas} respuestas y sus campañas. ¿Continuar?"><button class="btn btn-outline-danger">Eliminar</button></form>`}
      </div></td></tr>`;
  }).join('');
  return pagina({ usuario, apps, ids, ruta: 'cuestionarios', titulo: 'Cuestionarios', cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Cuestionarios</h1><p>Instrumentos del Observatorio.</p></div>
<div class="mintic-page-intro-note"><strong>${lista.length} cuestionarios</strong><a class="btn btn-sm btn-primary mt-1" href="/cuestionarios/nuevo">Nuevo cuestionario</a></div></div>
${mensaje ? `<div class="alert alert-info">${esc(mensaje)}</div>` : ''}
${smtpOk ? '' : '<div class="alert alert-warning py-2 small"><strong>Correo sin configurar.</strong> Las campañas se pueden preparar, pero no se enviarán hasta definir <code>SMTP_HOST</code>, <code>SMTP_USUARIO</code>, <code>SMTP_CLAVE</code> y <code>CORREO_DESDE</code> en el archivo <code>.env</code> del portal.</div>'}
<div class="card"><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead><tr><th>Cuestionario</th><th class="text-end">Respuestas</th><th class="text-end">Campañas</th><th style="width:26%">Enlace público</th><th>Acciones</th></tr></thead><tbody>${filas || '<tr><td colspan="5" class="text-muted p-4">Todavía no hay cuestionarios. Cree uno nuevo o duplique un ejemplo.</td></tr>'}</tbody></table></div></div></div>
<script src="/static/js/cuestionarios-admin.js"></script>` });
}

// Lista para usuarios que no administran: los cuestionarios publicados, listos para responder o compartir.
export function vistaCuestionariosParaTodos({ usuario, apps, ids, lista }) {
  const tarjetas = lista.map((c) => {
    const d = normalizar(c.definicion);
    const enlace = `${config.urlPublica}/c/${c.clave}`;
    return `<div class="col-md-6 col-xl-4"><div class="card h-100 border-primary"><div class="card-body d-flex flex-column">
      <h2 class="h5 text-primary">${esc(d.titulo)}</h2>
      <p class="small text-muted flex-grow-1">${esc(d.subtitulo || (d.intro[0] || '').replace(/\*\*/g, '').slice(0, 160))}</p>
      <div class="small text-muted mb-2">${d.pasos.length} pasos · ${camposDe(d).length} preguntas · ${fmt(c.respuestas)} respuestas</div>
      <div class="d-flex gap-2"><a class="btn btn-primary" href="/c/${esc(c.clave)}" target="_blank" rel="noopener">Responder</a><button class="btn btn-outline-secondary" type="button" data-copiar="${esc(enlace)}">Copiar enlace</button></div>
    </div></div></div>`;
  }).join('');
  return pagina({ usuario, apps, ids, ruta: 'cuestionarios', titulo: 'Cuestionarios del Observatorio', cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Cuestionarios del Observatorio</h1><p>Instrumentos del proyecto IA para el Estado abiertos para diligenciar. Cada uno tiene un enlace que puede compartir con su entidad.</p></div>
<div class="mintic-page-intro-note"><strong>${lista.length} cuestionarios publicados</strong>La gestión de los instrumentos y sus resultados corresponde al equipo del Observatorio.</div></div>
<div class="row g-4">${tarjetas || '<div class="col-12"><p class="text-muted">No hay cuestionarios publicados en este momento.</p></div>'}</div>
<script src="/static/js/cuestionarios-admin.js"></script>` });
}

// Hoja imprimible con el QR del enlace público y un QR por destinatario (para entregar en mano o por otros canales).
export function vistaCampaniaQr({ cuestionario, campania: k, destinatarios, qrDe, qrPublico }) {
  const d = normalizar(cuestionario.definicion);
  const tarjeta = (svgStr, titulo, sub, enlace) => `<div class="tarjeta"><div class="qr">${svgStr}</div><div class="texto"><strong>${esc(titulo)}</strong>${sub ? `<div>${esc(sub)}</div>` : ''}<div class="enlace">${esc(enlace)}</div></div></div>`;
  return `<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Códigos QR · ${esc(k.nombre)}</title>
<style>body{font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#1a2540;margin:24px}h1{font-size:1.3rem;color:#184fa4;margin:0 0 4px}p{margin:0 0 16px;color:#60718a;font-size:.9rem}.rejilla{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}.tarjeta{display:flex;gap:12px;border:1px solid #dfe5ef;border-radius:10px;padding:10px;break-inside:avoid;align-items:center}.qr svg{width:140px;height:auto;display:block}.texto{font-size:.85rem;min-width:0}.texto strong{display:block;font-size:.95rem;margin-bottom:2px}.enlace{font-family:monospace;font-size:.68rem;color:#60718a;word-break:break-all;margin-top:4px}.publico{border-color:#184fa4;background:#f5f8ff;margin-bottom:16px}.no-imprimir{margin-bottom:14px}@media print{.no-imprimir{display:none}body{margin:8mm}}</style></head><body>
<div class="no-imprimir"><button onclick="window.print()" style="padding:6px 14px;font-weight:700;background:#184fa4;color:#fff;border:0;border-radius:6px;cursor:pointer">Imprimir</button></div>
<h1>${esc(d.titulo)}</h1><p>Campaña «${esc(k.nombre)}»${k.periodo ? ` · periodo ${esc(k.periodo)}` : ''}. Cada código abre el enlace personal de la persona; el primero es el enlace público del cuestionario.</p>
<div class="tarjeta publico">${tarjeta(qrPublico, 'Enlace público (cualquier persona)', d.subtitulo || '', `${config.urlPublica}/c/${cuestionario.clave}`).replace('<div class="tarjeta">', '').replace(/<\/div>$/, '')}</div>
<div class="rejilla">${destinatarios.map((x) => tarjeta(qrDe(x), x.nombre || x.correo, [x.entidad, x.nombre ? x.correo : ''].filter(Boolean).join(' · '), enlaceDe(cuestionario.clave, x.token))).join('')}</div>
</body></html>`;
}

// ---------------------------------------------------------------- importación de respuestas anteriores
function selectorCampania(campanias, seleccion, nuevaCampania, periodo = '') {
  return `<div class="row g-2"><div class="col-md-6"><label class="form-label small mb-1">Campaña donde quedan las respuestas</label><select class="form-select form-select-sm" name="campania">
    <option value="nueva"${seleccion === 'nueva' || !seleccion ? ' selected' : ''}>Crear una campaña nueva para esta importación</option>
    ${campanias.map((k) => `<option value="${k.id}"${String(seleccion) === String(k.id) ? ' selected' : ''}>${esc(k.nombre)} (${fmt(k.total)} destinatarios)</option>`).join('')}</select></div>
    <div class="col-md-4"><label class="form-label small mb-1">Nombre de la campaña nueva (si aplica)</label><input class="form-control form-control-sm" name="nueva_campania" value="${esc(nuevaCampania || `Importación ${new Date().toISOString().slice(0, 10)}`)}"></div>
    <div class="col-md-2"><label class="form-label small mb-1">Periodo (corte)</label><input class="form-control form-control-sm" name="periodo" value="${esc(periodo || periodoActual())}" maxlength="40"></div></div>`;
}

export function vistaImportar({ usuario, apps, ids, cuestionario, campanias, campaniaSeleccionada = '', error = '' }) {
  const d = normalizar(cuestionario.definicion);
  return pagina({ usuario, apps, ids, ruta: 'cuestionarios', titulo: `Importar · ${d.titulo}`, cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Importar respuestas anteriores</h1><p><strong>${esc(d.titulo)}</strong>. Archivo Excel (.xlsx) o CSV exportado del formulario anterior.</p>
<div class="d-flex gap-2 mt-2"><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}">Resultados</a><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/campanias">Campañas</a></div></div></div>
${error ? `<div class="alert alert-danger">${esc(error)}</div>` : ''}
<div class="card"><div class="card-header">Paso 1 de 2. Archivo</div><div class="card-body"><form method="post" action="/cuestionarios/${cuestionario.id}/importar" enctype="multipart/form-data" data-working-text="Leyendo el archivo...">
  <div class="mb-3"><label class="form-label">Archivo exportado (.xlsx o .csv, hasta 20 MB)</label><input type="file" class="form-control" name="archivo" accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required><div class="form-text">Se usa la primera hoja. La primera fila con varias celdas de texto se toma como encabezado.</div></div>
  ${selectorCampania(campanias, campaniaSeleccionada, '')}
  <button class="btn btn-primary mt-3">Leer el archivo y proponer el mapeo</button>
</form></div></div>` });
}

export function vistaImportarMapeo({ usuario, apps, ids, cuestionario, token, columnas, muestra, total, sugerencias, destinos, campanias, campaniaSeleccionada, nuevaCampania, archivo, periodo = '' }) {
  const d = normalizar(cuestionario.definicion);
  const filas = columnas.map((col, i) => {
    const s = sugerencias[i] || {};
    const ejemplo = (muestra.map((f) => f[i]).find((v) => v !== '' && v != null) || '');
    return `<tr><td><strong>${esc(col)}</strong></td><td class="small text-muted">${esc(String(ejemplo).slice(0, 80))}</td><td><select class="form-select form-select-sm" name="col_${i}"><option value="">(no importar)</option>${destinos.map((x) => `<option value="${esc(x.clave)}"${s.destino === x.clave ? ' selected' : ''}>${esc(x.texto.length > 90 ? x.texto.slice(0, 89) + '…' : x.texto)}</option>`).join('')}</select></td><td class="text-center">${s.destino ? `<span class="badge ${s.confianza >= 90 ? 'bg-success' : 'bg-warning text-dark'}">${s.confianza} %</span>` : '<span class="badge bg-light text-secondary border">sin propuesta</span>'}</td></tr>`;
  }).join('');
  const propuestas = sugerencias.filter((s) => s.destino).length;
  return pagina({ usuario, apps, ids, ruta: 'cuestionarios', titulo: `Importar · ${d.titulo}`, cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Importar respuestas anteriores</h1><p><strong>${esc(d.titulo)}</strong> · archivo <code>${esc(archivo)}</code> con <strong>${fmt(total)}</strong> filas y ${columnas.length} columnas. El portal propuso destino para ${propuestas} columnas; revise y ajuste antes de importar.</p></div>
</div>
<form method="post" action="/cuestionarios/${cuestionario.id}/importar/${esc(token)}" data-working-text="Importando...">
<div class="card mb-3"><div class="card-header">Paso 2 de 2. Correspondencia de columnas</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm align-middle mb-0"><thead class="table-light"><tr><th style="width:28%">Columna del archivo</th><th style="width:26%">Ejemplo</th><th>Pregunta del cuestionario</th><th class="text-center">Confianza</th></tr></thead><tbody>${filas}</tbody></table></div></div></div>
<div class="card"><div class="card-body">
  ${selectorCampania(campanias, campaniaSeleccionada, nuevaCampania, periodo)}
  <div class="form-check mt-3"><input class="form-check-input" type="checkbox" name="omitir_duplicados" id="omitir_duplicados" value="1" checked><label class="form-check-label" for="omitir_duplicados">Omitir las filas que repitan una respuesta ya registrada según las reglas de duplicados del cuestionario (${d.duplicados.campos.length ? esc(d.duplicados.campos.join(', ')) : 'este cuestionario no tiene campos únicos definidos'})</label></div>
  <div class="d-flex gap-2 mt-3"><button class="btn btn-primary">Importar ${fmt(total)} filas</button><a class="btn btn-outline-secondary" href="/cuestionarios/${cuestionario.id}/importar">Elegir otro archivo</a></div>
</div></div>
</form>` });
}

// ---------------------------------------------------------------- editor
export function vistaEditor({ usuario, apps, ids, cuestionario, csrf }) {
  const nuevo = !cuestionario;
  const datos = {
    id: nuevo ? null : cuestionario.id,
    clave: nuevo ? null : cuestionario.clave,
    csrf,
    guardarUrl: nuevo ? '/cuestionarios/nuevo' : `/cuestionarios/${cuestionario.id}/editar`,
    vistaPreviaUrl: nuevo ? '' : `/c/${cuestionario.clave}?vista_previa=1`,
    listaUrl: '/cuestionarios',
    definicion: nuevo ? DEFINICION_VACIA() : cuestionario.definicion,
    tipos: TIPOS,
    politicasBase: [POLITICA_MINTIC, POLITICA_UDEC],
  };
  return pagina({ usuario, apps, ids, ruta: 'cuestionarios', titulo: nuevo ? 'Nuevo cuestionario' : `Editar · ${cuestionario.definicion.titulo}`, cuerpo: `
<div class="mintic-page-intro mb-3"><div><h1>${nuevo ? 'Nuevo cuestionario' : 'Editar cuestionario'}</h1><p>${nuevo ? 'Defina los pasos, las preguntas, las políticas de datos y las reglas de cálculo. Todo se puede cambiar después.' : `${badgeEstado(cuestionario.estado)} · versión ${cuestionario.version} · enlace público <code>${esc(config.urlPublica)}/c/${esc(cuestionario.clave)}</code>${cuestionario.protegido ? ' · <span class="badge bg-info text-dark">Ejemplo protegido</span>' : ''}`}</p></div>
${nuevo ? '' : `<div class="mintic-page-intro-note"><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}">Resultados</a> <a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/campanias">Campañas</a></div>`}</div>
${cuestionario && cuestionario.protegido ? '<div class="alert alert-info py-2 small">Este es uno de los ejemplos del proyecto. Se puede editar, pero si quiere conservarlo intacto como referencia, duplíquelo desde la lista y edite la copia.</div>' : ''}
<div id="editor" class="editor"></div>
<script type="application/json" id="editor-datos">${jsonSeguro(datos)}</script>
<script src="/static/js/editor.js"></script>` });
}

// ---------------------------------------------------------------- resultados
export function vistaResultados({ usuario, apps, ids, cuestionario, resumen, filas, filtros, campanias, periodos = [], pagina: pag = 1, porPagina = 100 }) {
  const d = normalizar(cuestionario.definicion);
  const campos = camposDe(d);
  const idn = d.identificacion || {};
  const enlace = `${config.urlPublica}/c/${cuestionario.clave}`;
  const graficos = (d.tablero.graficos.length ? d.tablero.graficos : campos.filter((c) => ['seleccion', 'unica', 'si_no', 'rubrica'].includes(c.tipo)).slice(0, 4).map((c) => c.nombre))
    .map((n) => campos.find((c) => c.nombre === n)).filter(Boolean);
  const porDim = {};
  for (const [nombre, p] of Object.entries(resumen.promedios)) { const k = p.dimension || '_'; (porDim[k] = porDim[k] || []).push({ texto: p.etiqueta, valor: p.promedio, max: p.max, nombre }); }
  const columnas = [['correo', 'Correo'], ['nombre', 'Nombre'], ['entidad', 'Entidad'], ['documento', 'Documento'], ['departamento', 'Departamento']].filter(([k]) => idn[k]);
  const inicio = (pag - 1) * porPagina;
  const pagFilas = filas.slice(inicio, inicio + porPagina);
  const totalPaginas = Math.max(1, Math.ceil(filas.length / porPagina));
  const qs = (extra) => { const p = new URLSearchParams({ ...filtros, ...extra }); for (const [k, v] of [...p]) if (!v) p.delete(k); return p.toString(); };
  const valorMostrado = (c, v) => {
    if (v == null || v === '') return '<span class="text-muted">—</span>';
    if (c.tipo === 'archivo' && typeof v === 'object') return `${esc(v.archivo)} <span class="text-muted small">(${fmt(v.tamano / 1024)} KB)</span>`;
    if (c.tipo === 'ranking' && typeof v === 'object') return (c.items || []).map((it) => `${esc(it.texto)}: <strong>${esc(v[it.nombre] ?? '—')}</strong>`).join(' · ');
    if (Array.isArray(v)) return v.map((x) => esc(textoDeOpcion(c, x))).join('; ');
    return esc(textoDeOpcion(c, v));
  };
  const detalle = (r) => `<div class="detalle-respuesta">${d.pasos.map((p) => `<div class="detalle-paso"><h6>${esc(p.etiqueta)}</h6><dl>${campos.filter((c) => c._paso === d.pasos.indexOf(p)).map((c) => `<div><dt>${c.numero != null && c.numero !== '' ? esc(c.numero) + '. ' : ''}${esc(c.etiqueta)}</dt><dd>${c.tipo === 'archivo' && r.datos[c.nombre] ? `<a href="/cuestionarios/${cuestionario.id}/respuestas/${r.id}/archivo/${esc(c.nombre)}">${valorMostrado(c, r.datos[c.nombre])}</a>` : valorMostrado(c, r.datos[c.nombre])}${r.datos[`${c.nombre}_otro`] ? ` <span class="text-muted">(${esc(r.datos[`${c.nombre}_otro`])})</span>` : ''}</dd></div>`).join('')}</dl></div>`).join('')}
    ${r.puntajes && r.puntajes.dimensiones && Object.keys(r.puntajes.dimensiones).length ? `<div class="detalle-paso"><h6>Puntajes</h6><dl>${Object.entries(r.puntajes.dimensiones).map(([k, x]) => `<div><dt>${esc(x.nombre || k)}</dt><dd><strong>${fmt(x.valor, 2)}</strong>${d.calculo.modo === 'suma' ? ` / ${fmt(x.max)}` : ''}${x.nivel ? ` · ${esc(x.nivel)}` : ''}</dd></div>`).join('')}<div><dt>Total</dt><dd><strong>${fmt(r.puntajes.total)}</strong> / ${fmt(r.puntajes.max_total)}${r.puntajes.nivel ? ` · ${esc(r.puntajes.nivel)}` : ''}</dd></div></dl></div>` : ''}
    <div class="small text-muted">Registrada el ${fechaCo(r.enviado_en)} desde ${esc(r.ip || '')}${r.campania_id ? ` · campaña ${esc((campanias.find((k) => k.id === r.campania_id) || {}).nombre || r.campania_id)}` : ''}.
      <form method="post" action="/cuestionarios/${cuestionario.id}/respuestas/${r.id}/eliminar" class="d-inline ms-2" data-confirmar="¿Eliminar esta respuesta? No se puede deshacer."><button class="btn btn-sm btn-outline-danger py-0">Eliminar respuesta</button></form></div></div>`;
  const tabla = pagFilas.map((r, i) => `<tr><td>${inicio + i + 1}</td>${columnas.map(([k]) => `<td>${esc(String(r.datos[idn[k]] ?? '').slice(0, 40))}</td>`).join('')}<td class="text-end">${r.puntajes && r.puntajes.max_total ? `<span class="badge bg-primary">${fmt(r.puntajes.total)}/${fmt(r.puntajes.max_total)}</span>` : ''}</td><td class="small text-nowrap">${fechaCo(r.enviado_en)}</td><td><button class="btn btn-sm btn-outline-primary py-0" type="button" data-detalles="det-${r.id}">Ver</button></td></tr><tr id="det-${r.id}" hidden><td colspan="${columnas.length + 4}" class="bg-light">${detalle(r)}</td></tr>`).join('');
  return pagina({ usuario, apps, ids, ruta: 'cuestionarios', titulo: `Resultados · ${d.titulo}`, cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>${esc(d.titulo)}</h1><p>${badgeEstado(cuestionario.estado)} ${cuestionario.origen === 'ejemplo' ? '<span class="badge bg-info text-dark">Ejemplo del proyecto</span>' : ''} · ${esc(d.subtitulo || 'Panel de resultados del cuestionario.')}</p>
  <div class="d-flex gap-2 flex-wrap mt-2"><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/editar">Editar</a><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/campanias">Campañas (${campanias.length})</a><a class="btn btn-sm btn-outline-secondary" href="/c/${esc(cuestionario.clave)}${cuestionario.estado === 'publicado' ? '' : '?vista_previa=1'}" target="_blank" rel="noopener">Abrir el cuestionario</a><button class="btn btn-sm btn-outline-secondary" type="button" data-copiar="${esc(enlace)}">Copiar enlace público</button><a class="btn btn-sm btn-primary" href="/cuestionarios/${cuestionario.id}/respuestas.csv?${qs({})}">Exportar a hoja de cálculo</a><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/importar">Importar respuestas (Excel o CSV)</a><a class="btn btn-sm btn-outline-secondary" href="/cuestionarios">Todos los cuestionarios</a></div></div>
<div class="mintic-page-intro-note"><strong>Enlace público</strong><code class="small">${esc(enlace)}</code><div class="d-flex align-items-center gap-2 mt-2"><img class="qr-mini" src="/c/${esc(cuestionario.clave)}/qr.svg?pie=0" alt="Código QR del enlace público"><a class="small" href="/c/${esc(cuestionario.clave)}/qr.svg?descargar=1">Descargar QR</a></div></div></div>
<div class="row g-3 mb-4">
  <div class="col-md-3 col-6"><div class="card kpi border-primary"><div class="card-body"><h3>${fmt(resumen.total)}</h3><small>Respuestas recibidas</small></div></div></div>
  <div class="col-md-3 col-6"><div class="card kpi border-success"><div class="card-body"><h3>${fmt(resumen.recibidasHoy)}</h3><small>Recibidas hoy</small></div></div></div>
  ${idn.entidad ? `<div class="col-md-3 col-6"><div class="card kpi border-info"><div class="card-body"><h3>${fmt(resumen.entidades)}</h3><small>Entidades distintas</small></div></div></div>` : ''}
  ${resumen.puntajePromedio != null ? `<div class="col-md-3 col-6"><div class="card kpi border-warning"><div class="card-body"><h3>${fmt(resumen.puntajePromedio, 1)}</h3><small>Puntaje promedio (máx. ${fmt(resumen.puntajeMax)})</small></div></div></div>` : ''}
  ${Object.entries(resumen.dimensiones).map(([k, x]) => `<div class="col-md-3 col-6"><div class="card kpi"><div class="card-body"><h3>${fmt(x.valor, d.calculo.modo === 'suma' ? 1 : 2)}${x.nivel ? ` <span class="badge nivel-${['Inicial', 'Gestionado', 'Definido', 'Avanzado', 'Optimizado'].indexOf(x.nivel) + 1}">${esc(x.nivel)}</span>` : ''}</h3><small>${esc(x.nombre)}${d.calculo.modo === 'suma' ? ` (máx. ${fmt(x.max)})` : ' (promedio 1 a 5)'}</small></div></div></div>`).join('')}
  ${resumen.indicadores.map((x) => `<div class="col-md-3 col-6"><div class="card kpi"><div class="card-body"><h3>${fmt(x.n)}</h3><small>${esc(x.nombre)}</small></div></div></div>`).join('')}
</div>
<h2 class="h5">Análisis de respuestas</h2>
<div class="row g-3 mb-4">
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Respuestas por día (últimos 30 días)</div><div class="card-body">${barrasDia(resumen.porDia)}</div></div></div>
  ${graficos.map((c) => `<div class="col-lg-3 col-md-6"><div class="card h-100"><div class="card-header small">${esc(c.etiqueta.length > 60 ? c.etiqueta.slice(0, 59) + '…' : c.etiqueta)}</div><div class="card-body">${donut(resumen.conteos[c.nombre] || [], c.etiqueta)}</div></div></div>`).join('')}
  ${Object.entries(porDim).map(([k, items]) => `<div class="col-lg-6"><div class="card h-100"><div class="card-header">${k === '_' ? 'Promedio por pregunta numérica' : `Promedio por ítem · ${esc((d.calculo.dimensiones.find((x) => x.clave === k) || {}).nombre || k)}`}</div><div class="card-body">${barrasH(items)}</div></div></div>`).join('')}
</div>
<div class="card mb-4"><div class="card-header">Filtros</div><div class="card-body"><form method="get" class="row g-2 align-items-end">
  <div class="col-md-3"><label class="form-label small mb-1">Buscar</label><input class="form-control form-control-sm" name="buscar" value="${esc(filtros.buscar || '')}" placeholder="correo, entidad, texto..."></div>
  <div class="col-md-2"><label class="form-label small mb-1">Periodo</label><select class="form-select form-select-sm" name="periodo"><option value="">Todos</option>${periodos.map((p) => `<option value="${esc(p)}"${filtros.periodo === p ? ' selected' : ''}>${esc(p)}</option>`).join('')}</select></div>
  <div class="col-md-3"><label class="form-label small mb-1">Campaña</label><select class="form-select form-select-sm" name="campania"><option value="">Todas (incluye enlace público)</option>${campanias.map((k) => `<option value="${k.id}"${String(filtros.campania) === String(k.id) ? ' selected' : ''}>${esc(k.nombre)}${k.periodo ? ` (${esc(k.periodo)})` : ''}</option>`).join('')}</select></div>
  ${graficos.slice(0, 1).map((c) => `<div class="col-md-2"><label class="form-label small mb-1">${esc(c.etiqueta.slice(0, 28))}</label><select class="form-select form-select-sm" name="f_${esc(c.nombre)}"><option value="">Todos</option>${opcionesDe(c).map((o) => `<option value="${esc(o.valor)}"${filtros[`f_${c.nombre}`] === o.valor ? ' selected' : ''}>${esc(o.texto.slice(0, 40))}</option>`).join('')}</select></div>`).join('')}
  <div class="col-md-2"><label class="form-label small mb-1">Desde</label><input type="date" class="form-control form-control-sm" name="desde" value="${esc(filtros.desde || '')}"></div>
  <div class="col-md-2"><label class="form-label small mb-1">Hasta</label><input type="date" class="form-control form-control-sm" name="hasta" value="${esc(filtros.hasta || '')}"></div>
  <div class="col-md-3 d-flex gap-2"><button class="btn btn-sm btn-primary">Aplicar filtros</button><a class="btn btn-sm btn-outline-secondary" href="/cuestionarios/${cuestionario.id}">Limpiar</a></div>
</form></div></div>
<div class="card"><div class="card-header d-flex justify-content-between align-items-center"><span>Respuestas registradas <span class="badge bg-primary">${fmt(filas.length)}</span></span>${totalPaginas > 1 ? `<nav class="small">${Array.from({ length: totalPaginas }, (_, i) => i + 1).map((n) => n === pag ? `<strong class="mx-1">${n}</strong>` : `<a class="mx-1" href="?${qs({ pagina: n })}">${n}</a>`).join('')}</nav>` : ''}</div>
<div class="card-body p-0"><div class="table-responsive"><table class="table table-sm table-hover align-middle mb-0"><thead class="table-dark"><tr><th>#</th>${columnas.map(([, t]) => `<th>${t}</th>`).join('')}<th class="text-end">Puntaje</th><th>Fecha</th><th></th></tr></thead><tbody>${tabla || `<tr><td colspan="${columnas.length + 4}" class="text-muted p-4">Sin respuestas${Object.values(filtros).some(Boolean) ? ' con estos filtros' : ' todavía'}.</td></tr>`}</tbody></table></div></div></div>
<script src="/static/js/cuestionarios-admin.js"></script>` });
}

// ---------------------------------------------------------------- campañas
export function vistaCampanias({ usuario, apps, ids, cuestionario, campanias, mensaje = '', error = '', smtpOk }) {
  const d = normalizar(cuestionario.definicion);
  const filas = campanias.map((k) => `<tr><td><a class="fw-semibold" href="/campanias/${k.id}">${esc(k.nombre)}</a><div class="small text-muted">${esc(k.asunto)}</div></td><td><span class="badge bg-light text-primary border">${esc(k.periodo || '')}</span></td><td>${badgeCampania(k.estado)}${k.estado === 'programada' && k.programada_en ? `<div class="small text-muted">${fechaCo(k.programada_en)}</div>` : ''}${k.enviada_en ? `<div class="small text-muted">${fechaCo(k.enviada_en)}</div>` : ''}</td><td class="text-end">${fmt(k.total)}</td><td class="text-end">${fmt(k.enviados)}</td><td class="text-end">${fmt(k.respondidos)}${k.enviados ? ` <span class="text-muted small">(${Math.round((k.respondidos / k.enviados) * 100)} %)</span>` : ''}</td><td class="text-end">${k.errores ? `<span class="text-danger">${fmt(k.errores)}</span>` : '0'}</td><td><a class="btn btn-sm btn-outline-primary" href="/campanias/${k.id}">Ver</a></td></tr>`).join('');
  return pagina({ usuario, apps, ids, ruta: 'cuestionarios', titulo: `Campañas · ${d.titulo}`, cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Campañas de aplicación</h1><p><strong>${esc(d.titulo)}</strong> ${badgeEstado(cuestionario.estado)}.</p>
<div class="d-flex gap-2 mt-2 flex-wrap"><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}">Resultados</a><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/editar">Editar cuestionario</a><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/importar">Importar respuestas anteriores (Excel o CSV)</a><a class="btn btn-sm btn-outline-secondary" href="/cuestionarios">Todos los cuestionarios</a></div></div></div>
${mensaje ? `<div class="alert alert-success">${esc(mensaje)}</div>` : ''}${error ? `<div class="alert alert-danger">${esc(error)}</div>` : ''}
${smtpOk ? '' : '<div class="alert alert-warning py-2 small"><strong>Correo sin configurar.</strong> Puede crear la campaña y obtener los enlaces personales, pero el envío automático requiere <code>SMTP_HOST</code>, <code>SMTP_USUARIO</code>, <code>SMTP_CLAVE</code> y <code>CORREO_DESDE</code> en el archivo <code>.env</code>.</div>'}
${cuestionario.estado !== 'publicado' ? '<div class="alert alert-warning py-2 small">El cuestionario no está publicado: las campañas no se enviarán hasta publicarlo.</div>' : ''}
<div class="card mb-4"><div class="card-header">Campañas</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead><tr><th>Campaña</th><th>Periodo</th><th>Estado</th><th class="text-end">Destinatarios</th><th class="text-end">Enviados</th><th class="text-end">Respondieron</th><th class="text-end">Errores</th><th></th></tr></thead><tbody>${filas || '<tr><td colspan="8" class="text-muted p-3">Sin campañas todavía.</td></tr>'}</tbody></table></div></div></div>
<div class="card"><div class="card-header">Nueva campaña</div><div class="card-body"><form method="post" action="/cuestionarios/${cuestionario.id}/campanias" data-working-text="Creando...">
  <div class="row g-3">
    <div class="col-md-4"><label class="form-label">Nombre de la campaña</label><input class="form-control" name="nombre" required placeholder="Ej. Entidades territoriales 2026"></div>
    <div class="col-md-2"><label class="form-label">Periodo (corte)</label><input class="form-control" name="periodo" value="${esc(periodoActual())}" required maxlength="40"></div>
    <div class="col-md-6"><label class="form-label">Asunto del correo</label><input class="form-control" name="asunto" required value="Invitación a responder: ${esc(d.titulo)}"></div>
    <div class="col-md-6"><label class="form-label">Mensaje</label><textarea class="form-control" name="cuerpo" rows="12" required>${esc(CUERPO_POR_DEFECTO.replace(/\{\{\s*cuestionario\s*\}\}/g, d.titulo))}</textarea><div class="form-text">Variables por persona: <code>{{nombre}}</code>, <code>{{entidad}}</code>, <code>{{enlace}}</code>.</div></div>
    <div class="col-md-6"><label class="form-label">Destinatarios</label><textarea class="form-control font-monospace" id="lista-destinatarios" name="destinatarios" rows="12" placeholder="correo@entidad.gov.co; Nombre Apellido; Alcaldía de Ejemplo&#10;otro@entidad.gov.co"></textarea><div class="form-text">Una persona por línea: correo; nombre; entidad. <span id="contador-destinatarios" class="fw-semibold"></span></div></div>
    <div class="col-md-4"><label class="form-label">Programar el envío (hora de Colombia)</label><input type="datetime-local" class="form-control" name="programada_en"></div>
    <div class="col-md-8 d-flex align-items-end"><button class="btn btn-primary">Crear campaña</button></div>
  </div></form></div></div>
<script src="/static/js/cuestionarios-admin.js"></script>` });
}

export function vistaCampania({ usuario, apps, ids, cuestionario, campania: k, destinatarios, mensaje = '', error = '', previa, smtpOk, enviando }) {
  const d = normalizar(cuestionario.definicion);
  const cuerpoPrevia = (previa.html.match(/<body[^>]*>([\s\S]*)<\/body>/) || [, previa.html])[1];
  const filas = destinatarios.map((x, i) => `<tr><td>${i + 1}</td><td>${esc(x.correo)}<div class="small text-muted">${esc(x.nombre || '')}${x.entidad ? ' · ' + esc(x.entidad) : ''}</div></td><td>${badgeDestinatario(x.estado)}${x.error ? `<div class="small text-danger">${esc(x.error)}</div>` : ''}</td><td class="small text-nowrap">${x.enviado_en ? fechaCo(x.enviado_en) + (x.envios > 1 ? ` <span class="text-muted">(${x.envios} envíos)</span>` : '') : ''}</td><td class="small text-nowrap">${x.respondido_en ? fechaCo(x.respondido_en) : ''}</td><td class="text-nowrap"><a class="btn btn-sm btn-outline-primary py-0" href="${esc(enlaceDe(cuestionario.clave, x.token))}" target="_blank" rel="noopener">Abrir enlace</a> <button class="btn btn-sm btn-outline-secondary py-0" type="button" data-copiar="${esc(enlaceDe(cuestionario.clave, x.token))}">Copiar</button> <a class="btn btn-sm btn-outline-secondary py-0" href="/campanias/${k.id}/destinatarios/${x.id}/qr.svg" target="_blank" rel="noopener">QR</a></td><td>${x.estado === 'respondido' ? '' : `<form method="post" action="/campanias/${k.id}/destinatarios/${x.id}/quitar" class="d-inline"><button class="btn btn-sm btn-outline-danger py-0">Quitar</button></form>`}</td></tr>`).join('');
  const puedeEnviar = smtpOk && cuestionario.estado === 'publicado' && !enviando && k.estado !== 'enviando';
  return pagina({ usuario, apps, ids, ruta: 'cuestionarios', titulo: `Campaña · ${k.nombre}`, cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>${esc(k.nombre)}</h1><p>${badgeCampania(k.estado)} · periodo <strong>${esc(k.periodo || 'sin periodo')}</strong> · Cuestionario <a href="/cuestionarios/${cuestionario.id}">${esc(d.titulo)}</a> ${badgeEstado(cuestionario.estado)}${k.programada_en ? ` · programada para el ${fechaCo(k.programada_en)}` : ''}${k.enviada_en ? ` · enviada el ${fechaCo(k.enviada_en)}` : ''}${k.ultimo_resultado ? ` · ${esc(k.ultimo_resultado)}` : ''}</p>
<div class="d-flex gap-2 mt-2 flex-wrap"><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/campanias">Todas las campañas</a><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}?campania=${k.id}">Respuestas de esta campaña</a><a class="btn btn-sm btn-outline-primary" href="/cuestionarios/${cuestionario.id}/importar?campania=${k.id}">Importar respuestas a esta campaña</a><a class="btn btn-sm btn-outline-secondary" href="/campanias/${k.id}/qr" target="_blank" rel="noopener">Hoja de códigos QR</a></div></div>
<div class="mintic-page-intro-note"><strong>Enlace del cuestionario</strong><a class="small" href="${esc(config.urlPublica)}/c/${esc(cuestionario.clave)}" target="_blank" rel="noopener">${esc(config.urlPublica)}/c/${esc(cuestionario.clave)}</a><div class="d-flex align-items-center gap-2 mt-2"><a href="/c/${esc(cuestionario.clave)}/qr.svg" target="_blank" rel="noopener"><img class="qr-mini" src="/c/${esc(cuestionario.clave)}/qr.svg?pie=0" alt="QR del enlace"></a><div class="d-flex flex-column gap-1"><button class="btn btn-sm btn-outline-secondary py-0" type="button" data-copiar="${esc(config.urlPublica)}/c/${esc(cuestionario.clave)}">Copiar enlace</button><a class="btn btn-sm btn-outline-secondary py-0" href="/c/${esc(cuestionario.clave)}/qr.svg?descargar=1">Descargar QR</a></div></div></div></div>
${mensaje ? `<div class="alert alert-success">${esc(mensaje)}</div>` : ''}${error ? `<div class="alert alert-danger">${esc(error)}</div>` : ''}
${enviando || k.estado === 'enviando' ? '<div class="alert alert-info py-2">La campaña se está enviando. Recargue la página para ver el avance.</div>' : ''}
<div class="row g-3 mb-4">
  <div class="col-md-2 col-6"><div class="card kpi"><div class="card-body"><h3>${fmt(k.total)}</h3><small>Destinatarios</small></div></div></div>
  <div class="col-md-2 col-6"><div class="card kpi border-primary"><div class="card-body"><h3>${fmt(k.enviados)}</h3><small>Enviados</small></div></div></div>
  <div class="col-md-2 col-6"><div class="card kpi border-success"><div class="card-body"><h3>${fmt(k.respondidos)}</h3><small>Respondieron${k.enviados ? ` (${Math.round((k.respondidos / k.enviados) * 100)} %)` : ''}</small></div></div></div>
  <div class="col-md-2 col-6"><div class="card kpi border-secondary"><div class="card-body"><h3>${fmt(k.pendientes)}</h3><small>Pendientes de envío</small></div></div></div>
  <div class="col-md-2 col-6"><div class="card kpi border-danger"><div class="card-body"><h3>${fmt(k.errores)}</h3><small>Con error</small></div></div></div>
</div>
<div class="row g-4">
  <div class="col-lg-7">
    <div class="card mb-4"><div class="card-header">Envío</div><div class="card-body">
      ${smtpOk ? '' : '<div class="alert alert-warning py-2 small mb-3">El correo no está configurado en el portal. Copie los enlaces personales de la tabla y envíelos por otro medio, o configure el SMTP en <code>.env</code>.</div>'}
      <div class="d-flex flex-wrap gap-2 align-items-center">
        <form method="post" action="/campanias/${k.id}/enviar" data-confirmar="Se enviará el correo ahora a ${k.pendientes + k.errores} destinatarios pendientes. ¿Continuar?"><button class="btn btn-primary"${puedeEnviar && (k.pendientes + k.errores) > 0 ? '' : ' disabled'}>Enviar ahora a los pendientes (${k.pendientes + k.errores})</button></form>
        <form method="post" action="/campanias/${k.id}/recordar" data-confirmar="Se enviará un recordatorio a quienes recibieron el correo y no han respondido. ¿Continuar?"><button class="btn btn-outline-primary"${puedeEnviar && (k.enviados - k.respondidos) > 0 ? '' : ' disabled'}>Recordar a quienes no han respondido (${Math.max(0, k.enviados - k.respondidos)})</button></form>
        <form method="post" action="/campanias/${k.id}/prueba" class="d-flex gap-1"><input type="email" class="form-control form-control-sm" name="correo" value="${esc(usuario.correo)}" required style="max-width:260px"><button class="btn btn-sm btn-outline-secondary"${smtpOk ? '' : ' disabled'}>Enviarme una prueba</button></form>
      </div>
      <hr>
      <form method="post" action="/campanias/${k.id}/programar" class="row g-2 align-items-end">
        <div class="col-md-6"><label class="form-label small mb-1">Programar el envío (hora de Colombia)</label><input type="datetime-local" class="form-control form-control-sm" name="programada_en" value="${esc(aLocal(k.programada_en))}" required></div>
        <div class="col-md-6 d-flex gap-2"><button class="btn btn-sm btn-outline-primary"${['enviando'].includes(k.estado) ? ' disabled' : ''}>Programar</button>${k.estado === 'programada' ? `<button class="btn btn-sm btn-outline-dark" formaction="/campanias/${k.id}/cancelar">Cancelar la programación</button>` : ''}</div>
      </form>
    </div></div>
    <div class="card mb-4"><div class="card-header">Destinatarios</div>
      <div class="card-body p-0"><div class="table-responsive" style="max-height:480px"><table class="table table-sm table-hover align-middle mb-0"><thead class="table-light"><tr><th>#</th><th>Correo</th><th>Estado</th><th>Enviado</th><th>Respondió</th><th>Enlace personal</th><th></th></tr></thead><tbody>${filas || '<tr><td colspan="7" class="text-muted p-3">Sin destinatarios. Agregue correos abajo.</td></tr>'}</tbody></table></div></div>
      <div class="card-body border-top"><form method="post" action="/campanias/${k.id}/destinatarios"><label class="form-label small">Agregar destinatarios (correo; nombre; entidad, uno por línea)</label><textarea class="form-control font-monospace form-control-sm" id="lista-destinatarios" name="destinatarios" rows="4" required></textarea><div class="d-flex justify-content-between align-items-center mt-2"><span class="small text-muted" id="contador-destinatarios"></span><button class="btn btn-sm btn-outline-primary">Agregar</button></div></form></div></div>
  </div>
  <div class="col-lg-5">
    <div class="card mb-4"><div class="card-header">Mensaje</div><div class="card-body"><form method="post" action="/campanias/${k.id}/editar">
      <div class="row g-2"><div class="col-8 mb-2"><label class="form-label small mb-1">Nombre de la campaña</label><input class="form-control form-control-sm" name="nombre" value="${esc(k.nombre)}" required></div><div class="col-4 mb-2"><label class="form-label small mb-1">Periodo (corte)</label><input class="form-control form-control-sm" name="periodo" value="${esc(k.periodo || '')}" required maxlength="40"></div></div>
      <div class="mb-2"><label class="form-label small mb-1">Asunto</label><input class="form-control form-control-sm" name="asunto" value="${esc(k.asunto)}" required></div>
      <div class="mb-2"><label class="form-label small mb-1">Cuerpo</label><textarea class="form-control form-control-sm" name="cuerpo" rows="10" required>${esc(k.cuerpo)}</textarea><div class="form-text">Variables por persona: <code>{{nombre}}</code>, <code>{{entidad}}</code>, <code>{{enlace}}</code>.</div></div>
      <button class="btn btn-sm btn-primary">Guardar mensaje</button>
    </form></div></div>
    <div class="card mb-4"><div class="card-header">Así se verá el correo</div><div class="card-body"><div class="small text-muted mb-2">Asunto: <strong>${esc(previa.asunto)}</strong></div><div class="previa-correo">${cuerpoPrevia}</div></div></div>
    <form method="post" action="/campanias/${k.id}/eliminar" data-confirmar="Se eliminará la campaña y su lista de destinatarios. Las respuestas ya recibidas se conservan. ¿Continuar?"><button class="btn btn-sm btn-outline-danger">Eliminar campaña</button></form>
  </div>
</div>
<script src="/static/js/cuestionarios-admin.js"></script>` });
}
