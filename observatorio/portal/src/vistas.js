// Plantillas HTML del portal. Mismo diseño institucional que la Solución Automatizada (franja GOV.CO, cabezote
// MinTIC, barra de navegación gris con subrayado amarillo, pie con cinta tricolor y barra de accesibilidad).
import { F1, F10, NIVELES, nivelDe } from './indicadores.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n, d = 0) => Number(n || 0).toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d });

// ---------------------------------------------------------------- estructura común
function menuAplicativos(apps, ids, usuario, ruta) {
  const items = apps.map((a) => {
    const v = ids.find((i) => i.app === a.clave);
    const href = usuario ? `/abrir/${esc(a.clave)}` : `/ingresar?siguiente=${encodeURIComponent('/abrir/' + a.clave)}`;
    const estado = usuario ? (v ? '<span class="badge bg-success ms-2">Vinculada</span>' : '<span class="badge bg-secondary ms-2">Sin vincular</span>') : '';
    return `<li><a class="dropdown-item d-flex justify-content-between align-items-center" href="${href}">${esc(a.nombre)}${estado}</a></li>`;
  }).join('');
  const cuestionarios = `<li><a class="dropdown-item d-flex justify-content-between align-items-center" href="${usuario ? '/cuestionarios' : '/ingresar?siguiente=%2Fcuestionarios'}">Cuestionarios del Observatorio<span class="badge bg-primary ms-2">Del portal</span></a></li>`;
  return `<li class="nav-item dropdown">
    <a class="nav-link dropdown-toggle ${['aplicativos', 'cuestionarios'].includes(ruta) ? 'active' : ''}" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">Aplicativos</a>
    <ul class="dropdown-menu">${items}${cuestionarios}<li><hr class="dropdown-divider"></li><li><a class="dropdown-item" href="${usuario ? '/aplicativos' : '/ingresar?siguiente=%2Faplicativos'}">Ver todos los aplicativos</a></li></ul></li>`;
}

export function pagina({ titulo, cuerpo, usuario = null, ruta = '', apps = [], ids = [] }) {
  const cuenta = usuario ? `<li class="nav-item dropdown">
        <a class="nav-link dropdown-toggle ${['cuenta', 'admin'].includes(ruta) ? 'active' : ''}" href="#" role="button" data-bs-toggle="dropdown">${esc((usuario.nombre || usuario.correo).split(' ')[0])}</a>
        <ul class="dropdown-menu dropdown-menu-end">
          <li><span class="dropdown-item-text small text-muted">${esc(usuario.nombre || '')}<br>${esc(usuario.correo)}</span></li>
          <li><hr class="dropdown-divider"></li>
          <li><a class="dropdown-item" href="/cuenta">Mi cuenta</a></li>
          ${usuario.rol === 'administrador' ? '<li><a class="dropdown-item" href="/admin">Administración</a></li>' : ''}
          <li><hr class="dropdown-divider"></li>
          <li><form method="post" action="/salir" class="m-0"><button class="dropdown-item" type="submit">Cerrar sesión</button></form></li>
        </ul></li>`
    : `<li class="nav-item"><a class="nav-link ${ruta === 'ingresar' ? 'active' : ''}" href="/ingresar">Ingresar</a></li>`;
  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Observatorio Nacional de Inteligencia Artificial. Proyecto IA para el Estado.">
<title>${esc(titulo)} &mdash; Observatorio Nacional de IA</title>
<link href="/static/vendor/bootstrap.min.css" rel="stylesheet">
<link href="/static/css/main.css" rel="stylesheet">
<link href="/static/css/portal.css" rel="stylesheet">
</head>
<body>
<div class="govco-ribbon"><div class="container govco-ribbon-inner">
  <a class="govco-ribbon-link" href="https://www.gov.co/" target="_blank" rel="noopener" aria-label="Ir a GOV.CO"><img src="/static/img/logo-govco.svg" alt="Logo GOV.CO" class="govco-ribbon-logo"></a>
</div></div>
<header class="mintic-masthead"><div class="container mintic-masthead-inner">
  <a class="mintic-lockup" href="/">
    <img src="/static/img/logo-mintic.png" alt="Logo MinTIC" class="mintic-lockup-logo">
    <div class="mintic-lockup-copy"><span class="mintic-kicker">Ministerio TIC</span><strong>Observatorio Nacional de Inteligencia Artificial</strong><small>Seguimiento a la adopción, la madurez y el uso responsable de la inteligencia artificial en el sector público colombiano.</small></div>
  </a>
  <div class="mintic-site-note"><span>Proyecto IA para el Estado</span><strong>Universidad de Cartagena</strong><small>${usuario ? 'Ingreso unificado a los aplicativos del proyecto y cuadro de mando del Observatorio.' : `Medición y acompañamiento de la adopción de IA en el sector público. <a href="/ingresar">Ingreso de administradores</a>`}</small></div>
</div></header>
${usuario ? `<nav class="navbar navbar-expand-lg navbar-mintic navbar-light"><div class="container">
  <a class="navbar-brand" href="/"><span class="navbar-brand-kicker">Observatorio IA</span><span class="navbar-brand-title">Portal del Observatorio</span></a>
  <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-label="Abrir navegación"><span class="navbar-toggler-icon"></span></button>
  <div class="collapse navbar-collapse" id="navbarNav">
    <ul class="navbar-nav me-auto">
      <li class="nav-item"><a class="nav-link ${ruta === 'inicio' ? 'active' : ''}" href="/">Inicio</a></li>
      <li class="nav-item"><a class="nav-link ${ruta === 'acerca' ? 'active' : ''}" href="/acerca">El Observatorio</a></li>
      <li class="nav-item"><a class="nav-link ${ruta === 'tablero' ? 'active' : ''}" href="${usuario ? '/tablero' : '/ingresar?siguiente=%2Ftablero'}">Cuadro de mando</a></li>
      ${menuAplicativos(apps, ids, usuario, ruta)}
    </ul>
    <ul class="navbar-nav">${cuenta}</ul>
  </div>
</div></nav>` : ''}
<main class="container page-shell mt-4 mb-5">
${cuerpo}
</main>
<footer class="footer-govco"><div class="footer-ribbon"></div><div class="container">
  <div class="footer-brand-panel">
    <div class="footer-brand-copy">
      <div class="footer-logo-stack"><img src="/static/img/logo-mintic.png" alt="Logo MinTIC" class="footer-logo footer-logo-mintic"><img src="/static/img/logo-govco.svg" alt="Logo GOV.CO" class="footer-logo footer-logo-govco"></div>
      <div><h5>Observatorio Nacional de Inteligencia Artificial</h5><p class="footer-note">Sistema de información del proyecto IA para el Estado para medir y acompañar la adopción de inteligencia artificial en las entidades públicas de Colombia.</p></div>
    </div>
    <div class="footer-highlight"><span>Universidad de Cartagena</span><strong>Ministerio de Tecnologías de la Información y las Comunicaciones</strong></div>
  </div>
  <div class="row g-4">
    <div class="col-md-4"><h6>Marco de medición</h6><ul><li>Diagnóstico de preparación institucional para IA</li><li>Sistema de indicadores por dimensión</li><li>Índice de Adopción de IA en el Sector Público</li><li>Modelo de seguimiento a la madurez institucional</li></ul></div>
    <div class="col-md-4"><h6>Aplicativos del proyecto</h6><ul>${apps.map((a) => `<li><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.nombre)}</a></li>`).join('')}<li><a href="https://app.proyectoia.org" target="_blank" rel="noopener">Portal del proyecto</a></li></ul></div>
    <div class="col-md-4"><h6>Portales oficiales</h6><ul><li><a href="https://www.mintic.gov.co/" target="_blank" rel="noopener">MinTIC Colombia</a></li><li><a href="https://www.gov.co/" target="_blank" rel="noopener">GOV.CO</a></li><li><a href="https://www.datos.gov.co/" target="_blank" rel="noopener">datos.gov.co</a></li><li><a href="https://www.unicartagena.edu.co/" target="_blank" rel="noopener">Universidad de Cartagena</a></li></ul></div>
  </div>
</div></footer>
<div class="footer-bottom"><div class="container"><span class="footer-bottom-brand">GOV.CO</span><span>Ministerio de Tecnologías de la Información y las Comunicaciones</span><span style="font-size:0.75rem">Observatorio Nacional de IA · versión 0.2</span></div></div>
<div class="accessibility-toolbar" id="a11y-toolbar">
  <button data-a11y="contraste" title="Contraste alto" aria-label="Alternar contraste alto"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none"/><path d="M12 2a10 10 0 0 1 0 20V2z" fill="currentColor"/></svg></button>
  <button data-a11y="mas" title="Aumentar texto" aria-label="Aumentar tamaño de texto"><svg viewBox="0 0 24 24"><text x="4" y="18" font-size="16" font-weight="bold" fill="currentColor">A</text><text x="16" y="12" font-size="10" font-weight="bold" fill="currentColor">+</text></svg></button>
  <button data-a11y="menos" title="Reducir texto" aria-label="Reducir tamaño de texto"><svg viewBox="0 0 24 24"><text x="4" y="18" font-size="16" font-weight="bold" fill="currentColor">A</text><text x="16" y="12" font-size="10" font-weight="bold" fill="currentColor">-</text></svg></button>
</div>
<script src="/static/vendor/bootstrap.bundle.min.js"></script>
<script src="/static/js/portal.js"></script>
</body>
</html>`;
}


// Recuadro público con las encuestas habilitadas, para invitar a las entidades a responderlas.
export function bloqueEncuestas(encuestas, { titulo = 'Encuestas habilitadas', compacto = false } = {}) {
  if (!encuestas || !encuestas.length) return '';
  const tarjetas = encuestas.map((e) => `<div class="col-md-6 col-xl-4"><div class="card h-100 encuesta-tarjeta"><div class="card-body d-flex flex-column">
      <h3 class="h6 text-primary mb-1">${esc(e.titulo)}</h3>
      <p class="small text-muted flex-grow-1 mb-2">${esc(e.subtitulo || '')}</p>
      <div class="small text-muted mb-2">${e.pasos} pasos · ${e.preguntas} preguntas${e.minutos ? ` · unos ${e.minutos} minutos` : ''}</div>
      <div class="d-flex align-items-center gap-3"><a class="btn btn-primary btn-sm" href="/c/${esc(e.clave)}" target="_blank" rel="noopener">Responder la encuesta</a><a href="/c/${esc(e.clave)}/qr.svg?descargar=1" title="Descargar el código QR"><img class="qr-mini" src="/c/${esc(e.clave)}/qr.svg?pie=0" alt="Código QR para responder ${esc(e.titulo)}"></a></div>
    </div></div></div>`).join('');
  return `<div class="card border-primary encuestas-habilitadas ${compacto ? 'mb-4' : 'mt-4 mb-4'}"><div class="card-header d-flex justify-content-between align-items-center"><span>${esc(titulo)}</span><span class="badge bg-primary">${encuestas.length} abiertas</span></div><div class="card-body">
  <p class="mb-3">El Observatorio invita a las entidades públicas a diligenciar los instrumentos que están abiertos. Cada respuesta alimenta el cuadro de mando nacional y orienta el acompañamiento técnico del proyecto IA para el Estado. No hace falta cuenta: cada encuesta se responde con el enlace de su botón y puede compartirse dentro de la entidad.</p>
  <div class="row g-3">${tarjetas}</div>
</div></div>`;
}

const nivelBadge = (n) => n ? `<span class="badge nivel-${n.n}">${esc(n.nombre)}</span>` : '<span class="badge bg-secondary">Sin medición</span>';

// ---------------------------------------------------------------- inicio (público)
export function vistaInicio({ usuario, apps, indicadores, ids, cuestionarios = [], encuestas = [] }) {
  const r = indicadores.r1519;
  const respuestas = cuestionarios.reduce((s, q) => s + (q.respuestas || 0), 0);
  return pagina({ usuario, apps, ids, ruta: 'inicio', titulo: 'Inicio', cuerpo: `
<div class="row"><div class="col-lg-8 mx-auto text-center">
  <h1 class="display-5 fw-bold mb-3">Observatorio Nacional de Inteligencia Artificial</h1>
  <p class="lead text-muted mb-3">Medición, seguimiento y acompañamiento de la adopción de inteligencia artificial en las entidades públicas de Colombia.</p>
</div></div>
<div class="row"><div class="col-lg-9 mx-auto">
  <div class="card border-primary mb-4"><div class="card-body">
    <h2 class="h5 text-primary mb-2">¿Qué es el Observatorio?</h2>
    <p class="mb-2" style="font-size:0.95rem">El Observatorio reúne en un solo lugar la información que producen los aplicativos del proyecto <strong>IA para el Estado</strong> y la convierte en indicadores comparables sobre la <strong>preparación, la adopción y la madurez</strong> de las entidades públicas en inteligencia artificial. Con una sola cuenta, las entidades acceden a sus aplicativos y el equipo del Observatorio consulta el cuadro de mando nacional.</p>
    <p class="mb-3" style="font-size:0.95rem">La medición se organiza en seis dimensiones, se agrega en el <strong>Índice de Adopción de IA en el Sector Público</strong> y clasifica a cada entidad en una escala de cinco niveles, de Inicial a Optimizado, que orienta el acompañamiento técnico.</p>
    <a class="btn btn-primary me-2" href="/acerca">Conocer el Observatorio</a>
    ${usuario ? '<a class="btn btn-outline-primary" href="/tablero">Ir al cuadro de mando</a>' : '<a class="btn btn-outline-primary" href="/ingresar">Ingresar</a>'}
  </div></div>
  ${bloqueEncuestas(encuestas, { titulo: 'Encuestas habilitadas para las entidades', compacto: true })}
</div></div>
<div class="row g-4 mt-1">
  <div class="col-md-3"><div class="card h-100 border-primary"><div class="card-body text-center"><h2 class="display-6 fw-bold text-primary">${apps.length}</h2><p class="text-muted mb-0">Aplicativos conectados</p></div></div></div>
  <div class="col-md-3"><div class="card h-100 border-success"><div class="card-body text-center"><h2 class="display-6 fw-bold text-success">${r ? fmt(r.entidades) : '--'}</h2><p class="text-muted mb-0">Entidades territoriales registradas</p></div></div></div>
  <div class="col-md-3"><div class="card h-100 border-info"><div class="card-body text-center"><h2 class="display-6 fw-bold text-info">${indicadores.fichas ? fmt(indicadores.fichas + indicadores.herramientas) : '--'}</h2><p class="text-muted mb-0">Fichas y herramientas de IA catalogadas</p></div></div></div>
  <div class="col-md-3"><div class="card h-100 border-warning"><div class="card-body text-center"><h2 class="display-6 fw-bold text-warning">${fmt(respuestas)}</h2><p class="text-muted mb-0">Respuestas a los cuestionarios del Observatorio</p></div></div></div>
</div>
<div class="row mt-5">
  <div class="col-md-6"><h3>Aplicativos del proyecto</h3>
    <ul class="list-group">${apps.map((a) => `<li class="list-group-item d-flex justify-content-between align-items-center"><a href="${usuario ? '/abrir/' + esc(a.clave) : '/ingresar?siguiente=' + encodeURIComponent('/abrir/' + a.clave)}">${esc(a.nombre)}</a><span class="badge bg-primary rounded-pill">Ingreso unificado</span></li>`).join('')}</ul></div>
  <div class="col-md-6"><h3>Accesos rápidos</h3>
    <ul class="list-group">
      <li class="list-group-item"><a href="${usuario ? '/tablero' : '/ingresar?siguiente=%2Ftablero'}">Cuadro de mando del Observatorio</a></li>
      <li class="list-group-item"><a href="/acerca">Dimensiones, índice y niveles de madurez</a></li>
      ${usuario && usuario.rol === 'administrador' ? '<li class="list-group-item"><a href="/cuestionarios">Cuestionarios y campañas de aplicación</a></li>' : ''}
      <li class="list-group-item"><a href="${usuario ? '/cuenta' : '/ingresar'}">${usuario ? 'Mi cuenta y aplicativos vinculados' : 'Ingresar con la cuenta de un aplicativo'}</a></li>
      <li class="list-group-item"><a href="https://app.proyectoia.org" target="_blank" rel="noopener">Portal del proyecto IA para el Estado</a></li>
    </ul></div>
</div>` });
}

// ---------------------------------------------------------------- el Observatorio (público)
export function vistaAcerca({ usuario, apps, ids, encuestas = [] }) {
  return pagina({ usuario, apps, ids, ruta: 'acerca', titulo: 'El Observatorio', cuerpo: `
<div class="mintic-page-intro mb-4">
  <div><h1>El Observatorio Nacional de Inteligencia Artificial</h1><p>Instancia del proyecto IA para el Estado, ejecutado por la Universidad de Cartagena con el Ministerio TIC, que mide de forma periódica y comparable cómo las entidades públicas colombianas se preparan, adoptan y gobiernan la inteligencia artificial.</p></div>
  <div class="mintic-page-intro-note"><strong>Tres objetos de medición</strong>Capacidad institucional, adopción de soluciones y resultados o riesgos observados. Un piloto no equivale a madurez, y una buena capacidad no garantiza valor público.</div>
</div>
<div class="row g-4">
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Propósito</div><div class="card-body">
    <p>El Observatorio produce evidencia comparable para orientar el acompañamiento técnico a las entidades, priorizar acciones de política pública y documentar avances con datos verificables. No ordena ni sanciona. Sus resultados alimentan la Escala de Acompañamiento Técnico en IA y la estrategia de fomento en entidades territoriales.</p>
    <p class="mb-0">El diseño privilegia la economía de trabajo para el Ministerio y para las entidades. Los instrumentos se diligencian una sola vez, las fuentes automáticas se aprovechan y las reglas de cálculo son reproducibles y versionadas.</p></div></div></div>
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Instrumentos y fuentes</div><div class="card-body">
    <p><strong>Encuesta Nacional de Adopción de IA en el Sector Público (ENAIASP).</strong> Incorpora el diagnóstico de preparación institucional y mide capacidades.</p>
    <p><strong>Registro Nacional de Sistemas de IA en el Sector Público (RNAIASP).</strong> Registra cada caso de uso o solución con identificador estable, etapa y nivel de riesgo.</p>
    <p class="mb-0"><strong>Fuentes automáticas.</strong> Los aplicativos del proyecto, entre ellos la Solución Automatizada de la Resolución 1519 y el Catálogo de IA, aportan evidencia complementaria que el portal recolecta cada hora.</p></div></div></div>
</div>
${bloqueEncuestas(encuestas)}
<h2 class="mt-5">Seis dimensiones de medición</h2>
<div class="table-responsive"><table class="table table-hover align-middle mintic-section-card"><thead><tr><th>Dimensión</th><th>Pregunta que responde</th><th>Unidad principal</th><th class="text-end">Indicadores</th></tr></thead><tbody>
${F10.dimensiones.map((d) => `<tr><td><strong>${esc(d.codigo)}. ${esc(d.nombre)}</strong></td><td>${esc(d.pregunta)}</td><td>${esc(d.unidad)}</td><td class="text-end">${d.indicadores.length}</td></tr>`).join('')}
</tbody></table></div>
<div class="row g-4 mt-2">
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Índice de Adopción de IA en el Sector Público</div><div class="card-body"><p>${esc(F10.indice)}</p><p class="mb-0">Los indicadores compuestos usan una escala de 0 a 100 y publican siempre el valor original junto al transformado. Una condición crítica no cumplida actúa como techo. Sin responsable, sin base de datos autorizada, sin control de acceso o sin supervisión para un sistema de alto impacto, la entidad no asciende de nivel aunque su promedio sea alto.</p></div></div></div>
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Escala unificada de madurez</div><div class="card-body">
    <table class="table table-sm mb-2"><thead><tr><th>Nivel</th><th>Rango</th><th>Ruta de acompañamiento</th></tr></thead><tbody>
    ${NIVELES.map((n) => `<tr><td>${nivelBadge(n)}</td><td>${n.desde.toFixed(2)} a ${n.hasta.toFixed(2)}</td><td>${esc(n.ruta)}</td></tr>`).join('')}
    </tbody></table><p class="small text-muted mb-0">Los mismos umbrales se aplican al promedio de cada ámbito del diagnóstico y al promedio institucional. Una entidad avanza cuando supera el punto de corte, cumple las condiciones críticas y mantiene el resultado durante dos observaciones.</p></div></div></div>
</div>
<h2 class="mt-5">Diagnóstico de preparación institucional</h2>
<p>El diagnóstico revisa 24 criterios agrupados en seis ámbitos, calificados de 1 a 5 con evidencia mínima documentada. El promedio de los ámbitos da el puntaje institucional y la diferencia entre el ámbito más alto y el más bajo mide el equilibrio del perfil.</p>
<div class="row g-3">${F1.ambitos.map((a) => `<div class="col-md-6 col-xl-4"><div class="card h-100"><div class="card-body"><h3 class="h6 text-primary mb-1">${esc(a.nombre)}</h3><p class="small text-muted mb-2">Eje habilitador. ${esc(a.eje)}</p><ul class="small mb-0 ps-3">${a.criterios.map(([c, t]) => `<li><strong>${c}</strong>. ${esc(t)}</li>`).join('')}</ul></div></div></div>`).join('')}</div>
<h2 class="mt-5">Modelo de seguimiento</h2>
<div class="row g-4">
  <div class="col-lg-4"><div class="card h-100"><div class="card-body"><h3 class="h6 text-primary">Ciclo anual</h3><p class="small mb-0">Preparación, recolección, validación, cálculo, contraste con la entidad, análisis, publicación y mejora. La medición institucional completa es anual y se sincroniza con el ciclo del FURAG. El registro de sistemas y los indicadores operativos se actualizan de forma trimestral o mensual.</p></div></div></div>
  <div class="col-lg-4"><div class="card h-100"><div class="card-body"><h3 class="h6 text-primary">Brechas y estancamiento</h3><p class="small mb-0">Una brecha persistente permanece dos mediciones sin acción activa. El estancamiento se identifica cuando no hay cambio y las acciones vencieron. En ambos casos el Observatorio informa la dimensión, la condición, el tiempo y la acción recomendada.</p></div></div></div>
  <div class="col-lg-4"><div class="card h-100"><div class="card-body"><h3 class="h6 text-primary">Alerta de desalineación</h3><p class="small mb-0">Se activa cuando una entidad opera o proyecta un sistema de impacto alto con nivel Inicial o Gestionado en gobernanza, datos, seguridad o supervisión. Exige revisión prioritaria y plan de tratamiento, no la suspensión automática.</p></div></div></div>
</div>
<h2 class="mt-5">Gobernanza y productos</h2>
<div class="row g-4">
  <div class="col-lg-6"><div class="card h-100"><div class="card-body"><p class="mb-0">El Observatorio opera con una estructura de cinco niveles. Comité Directivo, Secretaría Técnica, Comité Técnico Asesor, mesas sectoriales y territoriales, y una red de enlaces institucionales en las entidades. La Secretaría Técnica congela la versión metodológica de cada medición y publica los resultados.</p></div></div></div>
  <div class="col-lg-6"><div class="card h-100"><div class="card-body"><p class="mb-0">Los productos son un tablero periódico, un reporte ejecutivo, un informe metodológico, un conjunto de datos abiertos con diccionario y licencia, y alertas dirigidas. Cada recomendación vincula un hallazgo con una acción, una población objetivo y un responsable de política.</p></div></div></div>
</div>
<p class="small text-muted mt-4 mb-0">Marco de medición definido por la Universidad de Cartagena y el Ministerio TIC en el proyecto IA para el Estado, 2026, con referencia a la Política Nacional de Inteligencia Artificial (CONPES 4144), el Marco de Gestión de Riesgos de IA del NIST y la Recomendación de la UNESCO sobre la ética de la inteligencia artificial.</p>` });
}

// ---------------------------------------------------------------- ingreso
export function vistaIngreso({ error = '', apps, usuarioPrevio = '' }) {
  return pagina({ apps, ruta: 'ingresar', titulo: 'Ingresar', cuerpo: `
<div class="row"><div class="col-lg-5 mx-auto">
  <div class="card"><div class="card-header">Ingreso al portal</div><div class="card-body">
    <p class="text-muted" style="font-size:0.95rem">Use el usuario y la clave que ya tiene en ${apps.map((a) => `<strong>${esc(a.nombre)}</strong>`).join(' o en ')}. Con esa sesión accede a todos los aplicativos y al cuadro de mando.</p>
    <form method="post" action="/ingresar" data-working-text="Verificando...">
      <div class="mb-3"><label for="u" class="form-label">Usuario o correo</label><input id="u" name="usuario" class="form-control" autocomplete="username" required value="${esc(usuarioPrevio)}"></div>
      <div class="mb-3"><label for="p" class="form-label">Clave</label><input id="p" name="clave" type="password" class="form-control" autocomplete="current-password" required></div>
      ${error ? `<div class="alert alert-danger py-2">${esc(error)}</div>` : ''}
      <button class="btn btn-primary w-100">Ingresar</button>
    </form>
    <p class="small text-muted mt-3 mb-0">La clave se verifica en el aplicativo donde está registrada y no se guarda en el portal.</p>
  </div></div>
</div></div>` });
}

// ---------------------------------------------------------------- aplicativos (con sesión)
export function vistaAplicativos({ usuario, apps, ids, resumen, cuestionariosPublicados = 0 }) {
  const tarjetas = apps.map((a) => {
    const v = ids.find((i) => i.app === a.clave);
    const r = resumen.find((x) => x.app.clave === a.clave);
    const filas = r ? r.conjuntos.reduce((s, c) => s + c.filas, 0) : 0;
    return `<div class="col-md-6 col-xl-4"><div class="card h-100 ${v ? 'border-primary' : ''}"><div class="card-body d-flex flex-column">
      <h2 class="h5 text-primary">${esc(a.nombre)}</h2>
      <p class="small text-muted flex-grow-1">${v ? `Se abre con su sesión ya iniciada. Usuario ${esc(v.usuario_externo || v.id_externo)}.` : 'Aún no tiene una cuenta vinculada en este aplicativo. Se le pedirá su usuario y clave una sola vez.'}</p>
      <div class="d-flex justify-content-between align-items-center"><span class="small text-muted">${r && r.conjuntos.length ? `${fmt(filas)} registros recolectados` : 'Sin datos recolectados'}</span>${v ? '<span class="badge bg-success">Vinculada</span>' : '<span class="badge bg-secondary">Sin vincular</span>'}</div>
      <a class="btn ${v ? 'btn-primary' : 'btn-outline-primary'} mt-3" href="/abrir/${esc(a.clave)}">${v ? 'Abrir' : 'Vincular y abrir'}</a>
    </div></div></div>`;
  }).join('');
  return pagina({ usuario, apps, ids, ruta: 'aplicativos', titulo: 'Aplicativos', cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Aplicativos</h1><p>Aplicativos del proyecto IA para el Estado disponibles con su sesión del portal.</p></div>
<div class="mintic-page-intro-note"><strong>${ids.length} de ${apps.length} vinculados</strong>Cada aplicativo se vincula una sola vez con su usuario y clave propios.</div></div>
<div class="row g-4">${tarjetas}
<div class="col-md-6 col-xl-4"><div class="card h-100 border-primary"><div class="card-body d-flex flex-column"><h2 class="h5 text-primary">Cuestionarios del Observatorio</h2><p class="small text-muted flex-grow-1">Instrumentos del proyecto para diligenciar en línea${usuario.rol === 'administrador' ? ', con su editor, sus campañas de aplicación por correo y sus resultados' : ''}. Módulo propio del portal: se abre con esta misma sesión.</p><div class="d-flex justify-content-between align-items-center"><span class="small text-muted">${cuestionariosPublicados} publicados</span><span class="badge bg-primary">Del portal</span></div><a class="btn btn-primary mt-3" href="/cuestionarios">Abrir</a></div></div></div>
<div class="col-md-6 col-xl-4"><div class="card h-100"><div class="card-body d-flex flex-column"><h2 class="h5 text-primary">Cuadro de mando</h2><p class="small text-muted flex-grow-1">Indicadores del Observatorio construidos con los datos que reportan los aplicativos.</p><a class="btn btn-primary mt-3" href="/tablero">Abrir</a></div></div></div>
</div>` });
}

// ---------------------------------------------------------------- cuadro de mando
function barras(serie, etiqueta) {
  if (!serie || !serie.length) return '';
  const W = 560, H = 160, pl = 36, pb = 28, pt = 10, max = Math.max(...serie.map((s) => s.n), 1);
  const bw = Math.min(26, (W - pl - 10) / serie.length - 6);
  const sx = (i) => pl + (i + 0.5) * ((W - pl - 10) / serie.length), sy = (v) => pt + (1 - v / max) * (H - pb - pt);
  let out = `<svg viewBox="0 0 ${W} ${H}" class="grafico" role="img" aria-label="${esc(etiqueta)}">`;
  for (let t = 0; t <= 4; t++) { const v = Math.round((max * t) / 4); const y = sy(v); out += `<line x1="${pl}" x2="${W - 6}" y1="${y}" y2="${y}" class="g"/><text x="${pl - 6}" y="${y + 3}" text-anchor="end">${v}</text>`; }
  serie.forEach((s, i) => { const x = sx(i) - bw / 2, y = sy(s.n), h = sy(0) - y; out += `<path d="M${x},${sy(0)} v-${Math.max(h - 4, 0)} a4,4 0 0 1 4,-4 h${bw - 8} a4,4 0 0 1 4,4 v${Math.max(h - 4, 0)} z" class="barra"><title>${esc(s.mes)}: ${s.n}</title></path><text x="${sx(i)}" y="${H - 8}" text-anchor="middle">${esc(String(s.mes).slice(2).replace('-', '/'))}</text>`; });
  return out + '</svg>';
}

export function vistaTablero({ usuario, apps, ids, resumen, indicadores, cuestionarios = [], periodo = '', periodos = [] }) {
  const r = indicadores.r1519;
  // Promedio nacional por ámbito del diagnóstico de preparación, tomado del cuestionario con niveles cuyas dimensiones usan los códigos de los ámbitos.
  const f1Prom = {};
  for (const q of cuestionarios.filter((x) => x.niveles)) for (const [k, x] of Object.entries(q.dimensiones || {})) if (F1.ambitos.some((a) => a.codigo === k) && !f1Prom[k]) f1Prom[k] = { ...x, cuestionario: q };
  const f1Global = Object.values(f1Prom).length ? Object.values(f1Prom).reduce((s, x) => s + x.promedio, 0) / Object.values(f1Prom).length : null;
  const ultima = resumen.flatMap((x) => x.conjuntos.map((c) => c.fecha)).sort().pop();
  const conDatos = resumen.filter((x) => x.conjuntos.length).length;
  const tieneDatos = (clave) => (resumen.find((x) => x.app.clave === clave) || { conjuntos: [] }).conjuntos.length > 0;
  const evalSerie = (() => { const c = (resumen.find((x) => x.app.clave === 'solucion') || { conjuntos: [] }).conjuntos.find((k) => k.conjunto === 'evaluaciones'); return c ? c.series : null; })();
  const deptos = r ? Object.entries(r.porDepto).sort((a, b) => b[1].entidades - a[1].entidades).slice(0, 12) : [];
  const valorDe = (cod) => { const v = indicadores.valores[cod]; if (!v) return '<span class="badge bg-light text-secondary border">Pendiente de fuente</span>'; return `<strong>${fmt(v.valor, v.unidad === '%' ? 1 : 0)}</strong> ${esc(v.unidad)}<div class="small text-muted">${esc(v.fuente)}</div>`; };
  const pestanas = F10.dimensiones.map((d, i) => `<li class="nav-item" role="presentation"><button class="nav-link ${i === 0 ? 'active' : ''}" data-bs-toggle="tab" data-bs-target="#dim-${d.codigo}" type="button" role="tab">${d.codigo}. ${esc(d.nombre)} <span class="badge bg-light text-primary border ms-1">${d.indicadores.filter((x) => indicadores.valores[x.codigo]).length}/${d.indicadores.length}</span></button></li>`).join('');
  const paneles = F10.dimensiones.map((d, i) => `<div class="tab-pane fade ${i === 0 ? 'show active' : ''}" id="dim-${d.codigo}" role="tabpanel">
    <p class="text-muted mt-3 mb-2"><strong>${esc(d.pregunta)}</strong> Unidad principal de análisis. ${esc(d.unidad)}.</p>
    <div class="table-responsive"><table class="table table-hover align-middle"><thead class="table-dark"><tr><th>Código</th><th>Indicador</th><th>Fórmula</th><th>Fuente</th><th>Frecuencia</th><th>Desagregación</th><th>Valor actual</th></tr></thead><tbody>
    ${d.indicadores.map((x) => `<tr><td><code>${x.codigo}</code></td><td><strong>${esc(x.nombre)}</strong></td><td class="small">${esc(x.formula)}</td><td class="small">${esc(x.fuente)}</td><td class="small">${esc(x.frecuencia)}</td><td class="small">${esc(x.desagregacion)}</td><td>${valorDe(x.codigo)}</td></tr>`).join('')}
    </tbody></table></div>
    ${d.indicadores.filter((x) => indicadores.valores[x.codigo]).map((x) => { const v = indicadores.valores[x.codigo]; return `<div class="alert alert-light border small mb-2"><strong>${x.codigo}.</strong> ${esc(v.nota)} ${v.detalle ? Object.entries(v.detalle).map(([k, n]) => `<span class="badge bg-primary ms-1">${esc(k)}: ${fmt(n)}</span>`).join('') : ''}</div>`; }).join('')}
  </div>`).join('');
  return pagina({ usuario, apps, ids, ruta: 'tablero', titulo: 'Cuadro de mando', cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Cuadro de mando del Observatorio</h1><p>Indicadores de adopción y madurez en inteligencia artificial del sector público, construidos con los datos que reportan los aplicativos del proyecto.</p></div>
<div class="mintic-page-intro-note"><strong>Última actualización</strong>${ultima ? esc(ultima) + ' UTC' : 'Sin recolecciones'}${usuario.rol === 'administrador' ? '<form method="post" action="/admin/recolectar" class="mt-2"><button class="btn btn-sm btn-primary">Recolectar ahora</button></form>' : ''}</div></div>
<div class="row g-3 mb-4">
  <div class="col-md-3"><div class="card text-center border-primary"><div class="card-body py-3"><h3 class="mb-0 text-primary">${indicadores.conDatos} / ${indicadores.total}</h3><small class="text-muted">Indicadores con dato</small></div></div></div>
  <div class="col-md-3"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0">${conDatos} / ${apps.length}</h3><small class="text-muted">Aplicativos con datos</small></div></div></div>
  <div class="col-md-3"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0">${r ? fmt(r.entidades) : '--'}</h3><small class="text-muted">Entidades territoriales registradas</small></div></div></div>
  <div class="col-md-3"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0">${indicadores.fichas ? fmt(indicadores.fichas) : '--'}</h3><small class="text-muted">Fichas del Catálogo de IA</small></div></div></div>
</div>

<h2>Sistema de indicadores por dimensión</h2>
<p class="text-muted">Cada indicador tiene fórmula, fuente, frecuencia y desagregación. Los que ya cuentan con una fuente conectada muestran su valor actual. Los demás se activarán a medida que la encuesta nacional, el registro de sistemas y los expedientes de caso entren en operación.</p>
<ul class="nav nav-tabs mintic-tabs" role="tablist">${pestanas}</ul>
<div class="tab-content mintic-section-card p-3 mt-2">${paneles}</div>

<div class="row g-4 mt-4">
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Índice de Adopción de IA en el Sector Público</div><div class="card-body">
    <p class="small">${esc(F10.indice)}</p>
    <table class="table table-sm mb-0"><thead><tr><th>Nivel</th><th>Rango</th><th>Referencia MMCyTI</th></tr></thead><tbody>${NIVELES.map((n) => `<tr><td>${nivelBadge(n)}</td><td>${n.desde.toFixed(2)} a ${n.hasta.toFixed(2)}</td><td class="small">${esc(n.mmcyti)}</td></tr>`).join('')}</tbody></table>
    <p class="small text-muted mt-2 mb-0">El índice se publicará cuando la cobertura y la calidad de las fuentes superen los umbrales aprobados por la gobernanza del Observatorio.</p></div></div></div>
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Diagnóstico de preparación institucional</div><div class="card-body">
    <p class="small">${esc(F1.escala)}</p><p class="small">${esc(F1.calculo)}</p>
    <div class="table-responsive"><table class="table table-sm mb-0"><thead><tr><th>Ámbito</th><th>Criterios</th><th>Promedio nacional</th><th>Nivel</th></tr></thead><tbody>${F1.ambitos.map((a) => `<tr><td><strong>${esc(a.nombre)}</strong></td><td>${a.criterios.map(([c]) => c).join(', ')}</td>${f1Prom[a.codigo] ? `<td><strong>${fmt(f1Prom[a.codigo].promedio, 2)}</strong> <span class="small text-muted">(${fmt(f1Prom[a.codigo].n)} entidades)</span></td><td>${nivelBadge(nivelDe(f1Prom[a.codigo].promedio))}</td>` : `<td class="text-muted">Sin mediciones</td><td>${nivelBadge(null)}</td>`}</tr>`).join('')}${f1Global != null ? `<tr class="table-light"><td><strong>Promedio institucional nacional</strong></td><td></td><td><strong>${fmt(f1Global, 2)}</strong></td><td>${nivelBadge(nivelDe(f1Global))}</td></tr>` : ''}</tbody></table></div>
    <p class="small text-muted mt-2 mb-0">${f1Global != null ? `Promedios calculados con las respuestas al cuestionario «${esc(Object.values(f1Prom)[0].cuestionario.titulo)}» (${fmt(Object.values(f1Prom)[0].cuestionario.respuestas)} respuestas).` : 'Los promedios se llenan con las respuestas de las entidades al instrumento de autodiagnóstico aplicado desde el módulo de cuestionarios.'}</p></div></div></div>
</div>

<h2 class="mt-5">Evidencia complementaria de la Solución Automatizada (Resolución 1519 de 2020)</h2>
${r ? `<div class="row g-3 mb-3">
  <div class="col-md-3"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0 text-primary">${fmt(r.entidades)}</h3><small class="text-muted">Entidades registradas</small></div></div></div>
  <div class="col-md-3"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0">${fmt(r.evaluadas)}</h3><small class="text-muted">Entidades con evaluación</small></div></div></div>
  <div class="col-md-3"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0">${fmt(r.evaluaciones)}</h3><small class="text-muted">Evaluaciones realizadas</small></div></div></div>
  <div class="col-md-3"><div class="card text-center border-success"><div class="card-body py-3"><h3 class="mb-0 text-success">${r.promedio == null ? '--' : fmt(r.promedio, 1) + ' %'}</h3><small class="text-muted">Cumplimiento promedio</small></div></div></div>
</div>
<div class="row g-4">
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Evaluaciones por mes</div><div class="card-body">${evalSerie ? barras(evalSerie, 'Evaluaciones por mes') : '<p class="text-muted mb-0">Sin fechas en las evaluaciones recolectadas.</p>'}</div></div></div>
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Cobertura por departamento</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm table-hover mb-0"><thead><tr><th>Departamento</th><th class="text-end">Entidades</th><th class="text-end">Evaluadas</th><th style="width:38%">Cobertura</th></tr></thead><tbody>
  ${deptos.map(([d, v]) => `<tr><td>${esc(d)}</td><td class="text-end">${fmt(v.entidades)}</td><td class="text-end">${fmt(v.evaluadas)}</td><td><div class="progress" role="progressbar" aria-label="Cobertura"><div class="progress-bar" style="width:${v.entidades ? Math.round(v.evaluadas / v.entidades * 100) : 0}%">${v.entidades ? Math.round(v.evaluadas / v.entidades * 100) : 0} %</div></div></td></tr>`).join('')}
  </tbody></table></div></div></div></div>
</div>` : `<div class="alert alert-warning">${tieneDatos('solucion') ? 'Los conjuntos recibidos de la Solución Automatizada aún no incluyen entidades ni evaluaciones.' : 'Todavía no se han recolectado datos de la Solución Automatizada. Un administrador puede iniciar la recolección desde la página de administración.'}</div>`}

<h2 class="mt-5">Catálogo de IA</h2>
${indicadores.fichas || indicadores.herramientas ? `<div class="row g-3">
  <div class="col-md-4"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0 text-primary">${fmt(indicadores.fichas)}</h3><small class="text-muted">Fichas del Catálogo Único de Oferta IA</small></div></div></div>
  <div class="col-md-4"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0">${fmt(indicadores.herramientas)}</h3><small class="text-muted">Herramientas publicadas</small></div></div></div>
  <div class="col-md-4"><div class="card text-center"><div class="card-body py-3"><h3 class="mb-0">${fmt(indicadores.casos)}</h3><small class="text-muted">Casos de éxito documentados</small></div></div></div>
  ${Object.keys(indicadores.herramientasPorCategoria).length ? `<div class="col-12"><div class="card"><div class="card-header">Herramientas por categoría</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm table-hover mb-0"><thead><tr><th>Categoría</th><th class="text-end">Herramientas</th></tr></thead><tbody>${Object.entries(indicadores.herramientasPorCategoria).sort((a, b) => b[1] - a[1]).map(([c, n]) => `<tr><td>${esc(c)}</td><td class="text-end">${fmt(n)}</td></tr>`).join('')}</tbody></table></div></div></div></div>` : ''}
</div>` : `<div class="alert alert-warning">${tieneDatos('catalogo') ? 'Los conjuntos recibidos del Catálogo de IA aún no incluyen fichas ni herramientas.' : 'Todavía no se han recolectado datos del Catálogo de IA.'}</div>`}

<h2 class="mt-5">Cuestionarios del Observatorio</h2>
<div class="d-flex flex-wrap align-items-center gap-2 mb-3"><p class="text-muted mb-0 me-auto">Instrumentos aplicados desde el portal, con sus respuestas y los promedios por dimensión${periodo ? ` del periodo <strong>${esc(periodo)}</strong>` : ' de todos los periodos'}.</p>
<form method="get" action="/tablero" class="d-flex align-items-center gap-2"><label class="small mb-0" for="periodo">Periodo</label><select class="form-select form-select-sm" id="periodo" name="periodo"><option value="">Todos (integrado)</option>${periodos.map((p) => `<option value="${esc(p)}"${periodo === p ? ' selected' : ''}>${esc(p)}</option>`).join('')}</select><button class="btn btn-sm btn-outline-primary">Ver</button></form></div>
${cuestionarios.length ? `<div class="row g-3">${cuestionarios.map((q) => `<div class="col-md-6 col-xl-4"><div class="card h-100"><div class="card-body"><h3 class="h6 text-primary mb-1">${esc(q.titulo)}</h3><p class="small text-muted mb-2">${fmt(q.respuestas)} respuestas${q.entidades ? ` · ${fmt(q.entidades)} entidades` : ''}${q.campanias ? ` · ${fmt(q.campanias)} campañas` : ''}${q.ultima ? ` · última ${esc(String(q.ultima).slice(0, 16))} UTC` : ''}</p>${!periodo && Object.keys(q.porPeriodo || {}).length > 1 ? `<p class="small mb-2">${Object.entries(q.porPeriodo).map(([p, n]) => `<a class="badge bg-light text-primary border text-decoration-none me-1" href="/tablero?periodo=${encodeURIComponent(p)}">${esc(p)}: ${fmt(n)}</a>`).join('')}</p>` : ''}${Object.values(q.dimensiones || {}).map((x) => `<div class="d-flex justify-content-between small border-bottom py-1"><span>${esc(x.nombre)}</span><strong>${fmt(x.valor, 2)}${x.nivel ? ` · ${esc(x.nivel)}` : ''}</strong></div>`).join('')}${usuario.rol === 'administrador' ? `<a class="btn btn-sm btn-outline-primary mt-2" href="/cuestionarios/${q.id}">Ver resultados</a>` : ''}</div></div></div>`).join('')}</div>` : '<p class="text-muted">Todavía no hay cuestionarios con respuestas.</p>'}

<h2 class="mt-5">Datos recolectados</h2>
<div class="accordion" id="acordeonDatos">
${resumen.map((x, i) => `<div class="accordion-item"><h2 class="accordion-header"><button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#datos-${i}">${esc(x.app.nombre)} <span class="badge ${x.conjuntos.length ? 'bg-success' : 'bg-secondary'} ms-2">${x.conjuntos.length} conjuntos</span></button></h2>
  <div id="datos-${i}" class="accordion-collapse collapse" data-bs-parent="#acordeonDatos"><div class="accordion-body">
  ${x.conjuntos.length ? x.conjuntos.map((c) => `<div class="mb-3"><div class="d-flex justify-content-between"><strong>${esc(c.descripcion || c.conjunto)}</strong><span class="small text-muted">${fmt(c.filas)} filas · ${esc(c.fecha)} UTC</span></div>${c.muestra.length ? `<div class="table-responsive"><table class="table table-sm mt-2"><thead><tr>${c.columnas.slice(0, 6).map((k) => `<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${c.muestra.map((f) => `<tr>${c.columnas.slice(0, 6).map((k) => `<td>${esc(typeof f[k] === 'object' ? JSON.stringify(f[k]) : f[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : ''}</div>`).join('') : `<p class="text-muted mb-0">Sin datos recolectados.${x.ultimoError ? ' Último error. ' + esc(x.ultimoError.detalle) : ''}</p>`}
  </div></div></div>`).join('')}
</div>` });
}

// ---------------------------------------------------------------- cuenta
export function vistaCuenta({ usuario, ids, apps, sesiones }) {
  return pagina({ usuario, apps, ids, ruta: 'cuenta', titulo: 'Mi cuenta', cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Mi cuenta</h1><p>Sus datos, los aplicativos vinculados a su cuenta y las sesiones abiertas.</p></div></div>
<div class="row g-4">
  <div class="col-lg-5"><div class="card h-100"><div class="card-header">Datos</div><div class="card-body"><table class="table table-sm mb-0"><tr><th class="text-muted fw-normal">Nombre</th><td>${esc(usuario.nombre || '')}</td></tr><tr><th class="text-muted fw-normal">Correo</th><td>${esc(usuario.correo)}</td></tr><tr><th class="text-muted fw-normal">Rol en el portal</th><td>${esc(usuario.rol)}</td></tr></table></div></div></div>
  <div class="col-lg-7"><div class="card h-100"><div class="card-header">Aplicativos</div><div class="card-body"><table class="table align-middle mb-0">${apps.map((a) => { const v = ids.find((i) => i.app === a.clave); return `<tr><td><strong>${esc(a.nombre)}</strong><br><span class="small text-muted">${v ? `usuario ${esc(v.usuario_externo || v.id_externo)} · verificado ${esc(v.verificado_en)}` : 'sin vincular'}</span></td><td class="text-end">${v ? '<span class="badge bg-success">Vinculada</span>' : `<a class="btn btn-sm btn-outline-primary" href="/vincular/${esc(a.clave)}">Vincular</a>`}</td></tr>`; }).join('')}</table></div></div></div>
  <div class="col-12"><div class="card"><div class="card-header">Sesiones activas</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm mb-0"><thead><tr><th>Inicio</th><th>Expira</th><th>Dirección</th><th>Navegador</th></tr></thead><tbody>${sesiones.map((s) => `<tr><td>${esc(s.creada_en)}</td><td>${esc(s.expira_en.slice(0, 19).replace('T', ' '))}</td><td><code>${esc(s.ip || '')}</code></td><td class="small text-muted">${esc((s.agente || '').slice(0, 80))}</td></tr>`).join('')}</tbody></table></div></div></div></div>
</div>` });
}

export function vistaVincular({ usuario, app, apps = [], ids = [], error = '' }) {
  return pagina({ usuario, apps, ids, ruta: 'cuenta', titulo: 'Vincular', cuerpo: `
<div class="row"><div class="col-lg-5 mx-auto"><div class="card"><div class="card-header">Vincular ${esc(app.nombre)}</div><div class="card-body">
  <p class="text-muted" style="font-size:0.95rem">Escriba una sola vez el usuario y la clave que usa en ${esc(app.nombre)}. Desde entonces se abrirá con su sesión del portal.</p>
  <form method="post" action="/vincular/${esc(app.clave)}">
    <div class="mb-3"><label for="u" class="form-label">Usuario en ${esc(app.nombre)}</label><input id="u" name="usuario" class="form-control" required></div>
    <div class="mb-3"><label for="p" class="form-label">Clave en ${esc(app.nombre)}</label><input id="p" name="clave" type="password" class="form-control" required></div>
    ${error ? `<div class="alert alert-danger py-2">${esc(error)}</div>` : ''}
    <div class="d-flex gap-2"><button class="btn btn-primary">Vincular</button><a class="btn btn-outline-secondary" href="/cuenta">Cancelar</a></div>
  </form></div></div></div></div>` });
}

// ---------------------------------------------------------------- administración
export function vistaAdmin({ usuario, apps, ids = [], estados, auditoria, usuarios, mensaje = '' }) {
  return pagina({ usuario, apps, ids, ruta: 'admin', titulo: 'Administración', cuerpo: `
<div class="mintic-page-intro mb-4"><div><h1>Administración</h1><p>Estado de los conectores, recolección de datos, cuentas del portal (roles y administradores) y auditoría.</p></div>
<div class="mintic-page-intro-note"><strong>Recolección</strong><form method="post" action="/admin/recolectar"><button class="btn btn-sm btn-primary">Recolectar ahora</button></form></div></div>
${mensaje ? `<div class="alert alert-info">${esc(mensaje)}</div>` : ''}
<div class="card mb-4"><div class="card-header">Conectores</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead><tr><th>Aplicativo</th><th>Dirección interna</th><th>Estado</th><th>Conjuntos</th><th>Versión</th></tr></thead><tbody>
${estados.map((e) => `<tr><td><strong>${esc(e.app.nombre)}</strong></td><td><code>${esc(e.app.conector)}</code></td><td>${e.ok ? '<span class="badge bg-success">Activo</span>' : `<span class="badge bg-danger">Sin respuesta</span><div class="small text-muted">${esc(e.error)}</div>`}</td><td class="small">${e.ok ? esc((e.conjuntos || []).join(', ')) : ''}</td><td><code>${e.ok ? esc(e.version || '') : ''}</code></td></tr>`).join('')}
</tbody></table></div></div></div>
<div class="row g-4">
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Cuentas del portal</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm align-middle mb-0"><thead><tr><th>Correo</th><th>Rol</th><th>Último ingreso</th><th class="text-end">Vínculos</th><th></th></tr></thead><tbody>${usuarios.map((u) => `<tr><td>${esc(u.correo)}${u.id === usuario.id ? ' <span class="badge bg-light text-secondary border">usted</span>' : ''}<div class="small text-muted">${esc(u.nombre || '')}</div></td><td>${u.rol === 'administrador' ? '<span class="badge bg-primary">Administrador</span>' : '<span class="badge bg-secondary">Usuario</span>'}</td><td class="small">${esc(u.ultimo_ingreso || 'nunca')}</td><td class="text-end">${u.vinculos}</td><td class="text-end text-nowrap">${u.id === usuario.id ? '' : u.rol === 'administrador' ? `<form method="post" action="/admin/usuarios/${u.id}/rol" class="d-inline"><input type="hidden" name="rol" value="usuario"><button class="btn btn-sm btn-outline-secondary py-0">Quitar administrador</button></form>` : `<form method="post" action="/admin/usuarios/${u.id}/rol" class="d-inline"><input type="hidden" name="rol" value="administrador"><button class="btn btn-sm btn-outline-primary py-0">Hacer administrador</button></form>`}</td></tr>`).join('')}</tbody></table></div></div>
    <div class="card-body border-top"><form method="post" action="/admin/usuarios" class="row g-2 align-items-end">
      <div class="col-md-7"><label class="form-label small mb-1">Agregar una cuenta administradora por correo</label><input type="email" class="form-control form-control-sm" name="correo" required placeholder="persona@entidad.gov.co"></div>
      <div class="col-md-5"><button class="btn btn-sm btn-primary">Agregar administrador</button></div>

    </form></div></div></div>
  <div class="col-lg-6"><div class="card h-100"><div class="card-header">Auditoría reciente</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm mb-0"><thead><tr><th>Fecha</th><th>Evento</th><th>Aplicativo</th><th>Detalle</th></tr></thead><tbody>${auditoria.map((a) => `<tr><td class="small"><code>${esc(a.ocurrido_en)}</code></td><td>${esc(a.evento)}</td><td>${esc(a.app || '')}</td><td class="small text-muted">${esc(a.detalle || '')}</td></tr>`).join('')}</tbody></table></div></div></div></div>
</div>` });
}

export function vistaMensaje({ usuario, apps = [], titulo, texto, enlace = '/', textoEnlace = 'Volver al inicio' }) {
  return pagina({ usuario, apps, titulo, cuerpo: `<div class="row"><div class="col-lg-6 mx-auto"><div class="card"><div class="card-body"><h2 class="h4">${esc(titulo)}</h2><p class="text-muted">${esc(texto)}</p><a class="btn btn-primary" href="${esc(enlace)}">${esc(textoEnlace)}</a></div></div></div></div>` });
}
