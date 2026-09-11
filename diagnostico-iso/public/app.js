/* Diagnóstico ISO 9001 · ProyectoIA — aplicación de una sola página, sin dependencias. */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const app = $('#app');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = n => (n === null || n === undefined) ? '—' : Number(n).toLocaleString('es-CO', { maximumFractionDigits: 1 });
  const fecha = s => s ? new Date(s.length === 10 ? s + 'T12:00:00' : s.replace(' ', 'T') + 'Z').toLocaleDateString('es-CO', { year: 'numeric', month: 'short', day: 'numeric' }) : '—';

  const ICONO = { cumple: '✔', cumple_parcial: '½', no_cumple: '✖', sin_evidencia: '?', sin_valorar: '·' };
  const COLOR = { cumple: 'var(--cumple)', cumple_parcial: 'var(--parcial)', no_cumple: 'var(--nocumple)', sin_evidencia: 'var(--sinevid)', sin_valorar: '#cfd3da' };
  const ETIQ = { cumple: 'Cumple', cumple_parcial: 'Cumplimiento parcial', no_cumple: 'No cumple', sin_evidencia: 'Sin evidencia', sin_valorar: 'Sin valorar' };
  const CLAVES = ['cumple', 'cumple_parcial', 'no_cumple', 'sin_evidencia'];

  const estado = { usuario: null, config: null };

  // ---------- red ----------
  async function api(path, opts = {}) {
    const r = await fetch(path, { headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, credentials: 'same-origin', ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
    let data = {};
    try { data = await r.json(); } catch { }
    if (r.status === 401 && !path.includes('/auth/')) { estado.usuario = null; location.hash = '#/login?next=' + encodeURIComponent(location.hash.slice(1)); }
    if (!r.ok) { const e = new Error(data.error || 'Error ' + r.status); e.status = r.status; e.data = data; throw e; }
    return data;
  }
  let toastT;
  function toast(msg, err = false) {
    const t = $('#toast'); t.textContent = msg; t.className = 'toast' + (err ? ' err' : ''); t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, err ? 5000 : 2500);
  }

  // ---------- modal ----------
  function modal(html, onMount) {
    const bg = document.createElement('div'); bg.className = 'modal-bg';
    bg.innerHTML = `<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
    bg.addEventListener('click', e => { if (e.target === bg) cerrar(); });
    const cerrar = () => bg.remove();
    document.body.appendChild(bg);
    $$('[data-cerrar]', bg).forEach(b => b.addEventListener('click', cerrar));
    if (onMount) onMount(bg, cerrar);
    return cerrar;
  }
  function confirmar(msg, textoBtn = 'Confirmar') {
    return new Promise(res => modal(`<h2>Confirmación</h2><p>${esc(msg)}</p><div class="acciones"><button class="btn sec" data-cerrar>Cancelar</button><button class="btn peligro" id="m-ok">${esc(textoBtn)}</button></div>`,
      (bg, cerrar) => { $('#m-ok', bg).onclick = () => { cerrar(); res(true); }; bg.addEventListener('click', e => { if (e.target === bg) res(false); }); $$('[data-cerrar]', bg).forEach(b => b.addEventListener('click', () => res(false))); }));
  }

  // ---------- gráficos SVG ----------
  function barrasCapitulo(caps, { onClick } = {}) {
    // Barras horizontales de cumplimiento por capítulo (una serie; hue secuencial azul).
    return `<div class="filas-cap">${caps.map(c => `
      <div class="fila-cap" data-cap="${c.capitulo}" role="button" tabindex="0" title="${esc(c.nombre)}: ${fmt(c.cumplimiento)} % (${c.total} preguntas)">
        <span class="num">${c.capitulo}</span>
        <div><span class="nom">${esc(c.nombre)}</span><div class="barra"><span style="width:${c.cumplimiento}%"></span></div></div>
        <span class="pct num">${fmt(c.cumplimiento)} %</span>
      </div>`).join('')}</div>`;
  }
  function distribucion(conteo, total) {
    const claves = [...CLAVES, 'sin_valorar'];
    return `<div class="dist">${claves.filter(k => conteo[k] > 0).map(k => `<span class="c-${k}" style="width:${100 * conteo[k] / total}%" title="${ETIQ[k]}: ${conteo[k]}"></span>`).join('')}</div>
      <div class="leyenda">${claves.filter(k => conteo[k] > 0 || k !== 'sin_valorar').map(k => `<span><i class="c-${k}"></i>${ICONO[k]} ${ETIQ[k]}: <strong>${conteo[k]}</strong> (${fmt(100 * conteo[k] / total)} %)</span>`).join('')}</div>`;
  }
  function lineaHistorico(serie) {
    // Evolución del cumplimiento por versión (una serie). Etiquetas directas por punto: la serie es corta.
    if (!serie.length) return '<p class="vacio">Sin versiones registradas.</p>';
    const W = 640, H = 220, ml = 40, mr = 16, mt = 20, mb = 40;
    const iw = W - ml - mr, ih = H - mt - mb;
    const x = i => ml + (serie.length === 1 ? iw / 2 : i * iw / (serie.length - 1));
    const y = v => mt + ih - v * ih / 100;
    const pts = serie.map((s, i) => [x(i), y(s.cumplimiento)]);
    const grid = [0, 25, 50, 75, 100].map(v => `<line x1="${ml}" x2="${W - mr}" y1="${y(v)}" y2="${y(v)}" stroke="#e3e6eb"/><text x="${ml - 6}" y="${y(v) + 4}" text-anchor="end" font-size="10" fill="#7a7d84">${v}</text>`).join('');
    const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
    const marks = serie.map((s, i) => `<g class="pt" data-i="${i}"><circle cx="${pts[i][0]}" cy="${pts[i][1]}" r="9" fill="#fff" opacity="0"/><circle cx="${pts[i][0]}" cy="${pts[i][1]}" r="5" fill="#2a78d6" stroke="#fff" stroke-width="2"/>
      <text x="${pts[i][0]}" y="${pts[i][1] - 12}" text-anchor="middle" font-size="11" font-weight="600" fill="#17202b">${fmt(s.cumplimiento)} %</text>
      <text x="${pts[i][0]}" y="${H - mb + 16}" text-anchor="middle" font-size="10" fill="#52514e">v${s.version_numero}</text>
      <text x="${pts[i][0]}" y="${H - mb + 28}" text-anchor="middle" font-size="9" fill="#7a7d84">${esc(fecha(s.fecha))}</text></g>`).join('');
    return `<svg class="svg-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Evolución del cumplimiento por versión">${grid}<path d="${path}" fill="none" stroke="#2a78d6" stroke-width="2"/>${marks}</svg>`;
  }
  function barrasComparacion(caps) {
    // Dos series (antes/después) por capítulo: barras agrupadas, leyenda obligatoria.
    return `<div class="leyenda" style="margin-bottom:.5rem"><span><i style="background:#9cc4ee"></i>Versión base</span><span><i style="background:#2a78d6"></i>Versión actual</span></div>
      <div class="filas-cap">${caps.map(c => `<div class="fila-cap" style="cursor:default">
        <span class="num">${c.capitulo}</span>
        <div><span class="nom">${esc(c.nombre)}</span>
          <div class="barra fina" style="margin-bottom:2px"><span style="width:${c.antes ?? 0}%;background:#9cc4ee"></span></div>
          <div class="barra fina"><span style="width:${c.despues}%"></span></div></div>
        <span class="pct num" style="color:${c.delta > 0 ? '#0a6a0a' : c.delta < 0 ? '#9a2323' : 'inherit'}">${c.delta === null ? '—' : (c.delta > 0 ? '+' : '') + fmt(c.delta)}</span></div>`).join('')}</div>`;
  }

  // ---------- enrutador ----------
  const rutas = [];
  function ruta(patron, fn, { publica = false } = {}) {
    const keys = []; const re = new RegExp('^' + patron.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/?]+)'; }) + '$');
    rutas.push({ re, keys, fn, publica });
  }
  async function navegar() {
    const hash = location.hash.slice(1) || '/';
    const [path, qs] = hash.split('?');
    const query = Object.fromEntries(new URLSearchParams(qs || ''));
    for (const r of rutas) {
      const m = r.re.exec(path);
      if (!m) continue;
      const params = {}; r.keys.forEach((k, i) => params[k] = decodeURIComponent(m[i + 1]));
      if (!r.publica && !estado.usuario) { location.hash = '#/login?next=' + encodeURIComponent(hash); return; }
      $('#btn-back').hidden = path === '/' || path === '/login';
      $('#btn-menu').hidden = !estado.usuario;
      document.body.classList.toggle('con-barra', false);
      app.innerHTML = '<div class="loading">Cargando…</div>';
      window.scrollTo(0, 0);
      try { await r.fn(params, query); } catch (e) { console.error(e); app.innerHTML = `<div class="tarjeta"><h2>No fue posible cargar la vista</h2><p>${esc(e.message)}</p><a class="btn sec" href="#/">Ir al inicio</a></div>`; }
      return;
    }
    app.innerHTML = '<div class="tarjeta"><h2>Página no encontrada</h2><a class="btn sec" href="#/">Ir al inicio</a></div>';
  }

  // ---------- vistas ----------
  ruta('/login', async (_, q) => {
    const a = estado.config.auth;
    app.innerHTML = `<div class="login">
      <div class="logo"><img src="/icono.svg" width="64" height="64" alt=""><h1>Diagnóstico ISO 9001</h1><p class="hint">Instrumento de diagnóstico de implementación ISO 9001:2015 + Enmienda 1:2024</p></div>
      ${a.gestor ? `<a class="btn bloque" href="/auth/gestor/login${q.next ? '?next=' + encodeURIComponent('/#' + q.next) : ''}">Ingresar con ${esc(a.gestor_nombre)}</a>` : ''}
      ${a.gestor && a.local ? '<div class="sep">o con correo y contraseña</div>' : ''}
      ${a.local ? `<form id="f-login" class="tarjeta">
        ${a.credenciales_gestor ? `<p class="hint" style="margin-top:0">Use el mismo correo y contraseña de ${esc(a.gestor_nombre)}.</p>` : ''}
        <label>Correo electrónico o usuario</label><input name="email" type="text" autocomplete="username" required inputmode="email" autocapitalize="none" spellcheck="false">
        <label>Contraseña</label><input name="password" type="password" autocomplete="current-password" required>
        <div class="acciones"><button class="btn bloque" type="submit">Ingresar</button></div></form>` : ''}
      ${!a.gestor && !a.local ? '<div class="alerta">No hay ningún método de acceso habilitado. Revise la configuración del servidor.</div>' : ''}
      <p class="hint" style="text-align:center"><a href="#/imprimir-blanco">Imprimir el formato en blanco</a> no requiere sesión.</p>
    </div>`;
    const f = $('#f-login');
    if (f) f.onsubmit = async e => {
      e.preventDefault();
      const b = $('button', f); b.disabled = true;
      try {
        const d = await api('/api/auth/local/login', { method: 'POST', body: { email: f.email.value, password: f.password.value } });
        estado.usuario = d.usuario; pintarUsuario();
        location.hash = q.next ? '#' + decodeURIComponent(q.next) : '#/';
      } catch (err) { toast(err.message, true); } finally { b.disabled = false; }
    };
  }, { publica: true });

  ruta('/', async () => {
    const { organizaciones } = await api('/api/organizaciones');
    const puedeCrear = ['admin', 'consultor'].includes(estado.usuario.rol);
    app.innerHTML = `
      <div class="fila entre"><h1>Organizaciones</h1>${puedeCrear ? '<button class="btn peq" id="b-nueva">+ Nueva organización</button>' : ''}</div>
      ${organizaciones.length ? organizaciones.map(o => {
        const d = o.ultimo_diagnostico;
        return `<div class="tarjeta enlace" data-href="#/org/${o.id}">
          <div class="fila entre"><h2 style="margin:0">${esc(o.nombre)}</h2>${o.sigla ? `<span class="chip">${esc(o.sigla)}</span>` : ''}</div>
          <p class="hint">${[o.sector, o.ciudad].filter(Boolean).map(esc).join(' · ')}</p>
          ${d ? `<div class="progreso"><span>v${d.version_numero} · ${d.estado === 'cerrado' ? 'cerrada' : 'en diligenciamiento'}</span><div class="barra"><span style="width:${d.cumplimiento}%"></span></div><strong class="num">${fmt(d.cumplimiento)} %</strong></div>
                 <p class="hint" style="margin:.4rem 0 0">Nivel: ${esc(d.nivel)} · Brecha: ${fmt(d.brecha_total)} % · ${o.total_versiones} versión(es)</p>`
             : '<p class="hint">Sin diagnósticos todavía.</p>'}
        </div>`; }).join('') : `<div class="tarjeta vacio">No tiene organizaciones asignadas.${puedeCrear ? ' Cree la primera con el botón superior.' : ' Solicite al administrador que lo asigne a una organización.'}</div>`}`;
    $$('[data-href]').forEach(el => el.onclick = () => location.hash = el.dataset.href);
    const bn = $('#b-nueva'); if (bn) bn.onclick = () => formOrganizacion();
  });

  function formOrganizacion(o = null) {
    modal(`<h2>${o ? 'Editar' : 'Nueva'} organización</h2><form id="f-org">
      <label>Nombre *</label><input name="nombre" required value="${esc(o?.nombre)}">
      <div class="grid-2"><div><label>Sigla</label><input name="sigla" value="${esc(o?.sigla)}"></div><div><label>NIT</label><input name="nit" value="${esc(o?.nit)}"></div></div>
      <div class="grid-2"><div><label>Sector</label><input name="sector" value="${esc(o?.sector)}" list="sectores"><datalist id="sectores"><option>Salud</option><option>Educación</option><option>Manufactura</option><option>Servicios</option><option>Sector público</option><option>Comercio</option></datalist></div><div><label>Ciudad</label><input name="ciudad" value="${esc(o?.ciudad)}"></div></div>
      <div class="grid-2"><div><label>Contacto</label><input name="contacto_nombre" value="${esc(o?.contacto_nombre)}"></div><div><label>Correo de contacto</label><input name="contacto_email" type="email" value="${esc(o?.contacto_email)}"></div></div>
      <label>Descripción</label><textarea name="descripcion">${esc(o?.descripcion)}</textarea>
      <div class="acciones"><button class="btn sec" type="button" data-cerrar>Cancelar</button><button class="btn" type="submit">Guardar</button></div></form>`,
      (bg, cerrar) => {
        $('#f-org', bg).onsubmit = async e => {
          e.preventDefault();
          const body = Object.fromEntries(new FormData(e.target));
          try {
            if (o) { await api('/api/organizaciones/' + o.id, { method: 'PUT', body }); toast('Organización actualizada'); cerrar(); navegar(); }
            else { const r = await api('/api/organizaciones', { method: 'POST', body }); toast('Organización creada'); cerrar(); location.hash = '#/org/' + r.id; }
          } catch (err) { toast(err.message, true); }
        };
      });
  }

  ruta('/org/:id', async ({ id }) => {
    const [{ organizacion: o, mi_rol, diagnosticos, miembros }, { historico }] = await Promise.all([api('/api/organizaciones/' + id), api(`/api/organizaciones/${id}/historico`)]);
    const gestor = ['admin', 'consultor'].includes(estado.usuario.rol);
    const abierto = diagnosticos.find(d => d.estado === 'en_diligenciamiento');
    app.innerHTML = `
      <div class="fila entre"><div><h1>${esc(o.nombre)}</h1><p class="hint">${[o.sigla, o.sector, o.ciudad, o.nit ? 'NIT ' + o.nit : null].filter(Boolean).map(esc).join(' · ')}</p></div>
        ${gestor ? '<button class="btn peq sec" id="b-editar">Editar</button>' : ''}</div>
      ${o.descripcion ? `<p>${esc(o.descripcion)}</p>` : ''}
      <div class="acciones">
        ${mi_rol === 'editor' ? `<button class="btn" id="b-nueva-v">+ Nueva versión del diagnóstico</button>` : ''}
        <a class="btn sec" href="#/imprimir/${o.id}">Imprimir diligenciado</a>
        <a class="btn sec" href="#/imprimir-blanco?org=${encodeURIComponent(o.nombre)}">Imprimir en blanco</a>
      </div>
      <h2 style="margin-top:1.25rem">Versiones del diagnóstico</h2>
      ${diagnosticos.length ? diagnosticos.map(d => `<div class="tarjeta">
        <div class="fila entre"><h3 style="margin:0">Versión ${d.version_numero} · ${esc(d.titulo)}</h3><span class="chip ${d.estado === 'cerrado' ? 'cerrado' : 'abierto'}">${d.estado === 'cerrado' ? 'Cerrada' : 'En diligenciamiento'}</span></div>
        <p class="hint">Fecha ${fecha(d.fecha)} · ${d.estado === 'cerrado' ? 'cerrada el ' + fecha(d.cerrado_en) : 'avance ' + fmt(d.avance_diligenciamiento) + ' %'}${d.base_version_id ? ' · derivada de una versión anterior' : ''}</p>
        <div class="progreso"><div class="barra"><span style="width:${d.cumplimiento}%"></span></div><strong class="num">${fmt(d.cumplimiento)} %</strong></div>
        <p class="hint" style="margin:.4rem 0 0">Nivel ${esc(d.nivel)} · brecha ${fmt(d.brecha_total)} % · ${ICONO.cumple} ${d.conteo.cumple} · ${ICONO.cumple_parcial} ${d.conteo.cumple_parcial} · ${ICONO.no_cumple} ${d.conteo.no_cumple} · ${ICONO.sin_evidencia} ${d.conteo.sin_evidencia}${d.conteo.sin_valorar ? ' · sin valorar ' + d.conteo.sin_valorar : ''}</p>
        <div class="acciones">
          <a class="btn ${d.estado === 'cerrado' || mi_rol !== 'editor' ? 'sec' : ''}" href="#/diag/${d.id}/llenar">${d.estado === 'cerrado' || mi_rol !== 'editor' ? 'Ver respuestas' : 'Diligenciar'}</a>
          <a class="btn sec" href="#/diag/${d.id}">Indicadores</a>
          <a class="btn sec" href="#/imprimir/${o.id}?v=${d.id}">Imprimir</a>
        </div></div>`).join('') : '<div class="tarjeta vacio">Aún no hay versiones. Cree la primera versión para aplicar el cuestionario.</div>'}
      <div class="tarjeta"><h2>Histórico de cumplimiento</h2>${lineaHistorico(historico)}
        ${historico.length > 1 ? `<div class="tabla-scroll"><table><thead><tr><th>Versión</th><th>Fecha</th><th class="der">Cumplimiento</th><th class="der">Brecha</th><th>Nivel</th>${historico[0].por_capitulo.map(c => `<th class="der">Cap. ${c.capitulo}</th>`).join('')}</tr></thead>
          <tbody>${historico.map(h => `<tr><td>v${h.version_numero}</td><td>${fecha(h.fecha)}</td><td class="der num">${fmt(h.cumplimiento)} %</td><td class="der num">${fmt(h.brecha_total)} %</td><td>${esc(h.nivel)}</td>${h.por_capitulo.map(c => `<td class="der num">${fmt(c.cumplimiento)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : ''}
        ${historico.length > 1 ? `<div class="acciones"><a class="btn sec" href="#/diag/${historico[historico.length - 1].id}/comparar/${historico[historico.length - 2].id}">Comparar últimas dos versiones</a></div>` : ''}
      </div>
      ${gestor ? `<div class="tarjeta"><div class="fila entre"><h2 style="margin:0">Usuarios asignados</h2><button class="btn peq" id="b-miembro">+ Asignar usuario</button></div>
        <p class="hint">Los usuarios asignados pueden diligenciar (editor) o consultar (lector) los diagnósticos de esta organización. Los administradores y consultores tienen acceso a todas las organizaciones.</p>
        ${miembros.length ? `<table><thead><tr><th>Usuario</th><th>Rol</th><th></th></tr></thead><tbody>${miembros.map(m => `<tr><td>${esc(m.nombre)}<br><span class="hint">${esc(m.email)} · ${m.origen === 'gestor' ? esc(estado.config.auth.gestor_nombre) : 'local'}</span></td><td>${m.rol}</td><td class="der"><button class="btn peq peligro" data-quitar="${m.id}">Quitar</button></td></tr>`).join('')}</tbody></table>` : '<p class="hint">Ningún usuario asignado.</p>'}
      </div>` : ''}`;
    const be = $('#b-editar'); if (be) be.onclick = () => formOrganizacion(o);
    const bv = $('#b-nueva-v'); if (bv) bv.onclick = () => {
      if (abierto) { toast(`La versión ${abierto.version_numero} sigue en diligenciamiento. Ciérrela desde sus indicadores antes de crear otra.`, true); location.hash = `#/diag/${abierto.id}/llenar`; return; }
      modal(`<h2>Nueva versión del diagnóstico</h2><form id="f-v">
        <label>Título</label><input name="titulo" value="Diagnóstico ISO 9001 – versión ${diagnosticos.length + 1}">
        <label>Fecha</label><input name="fecha" type="date" value="${new Date().toISOString().slice(0, 10)}">
        <label>Partir de una versión anterior</label><select name="desde_version_id"><option value="">Formato en blanco</option>${diagnosticos.map(d => `<option value="${d.id}">Versión ${d.version_numero} · ${esc(d.titulo)} (${fmt(d.cumplimiento)} %)</option>`).join('')}</select>
        <label>Qué copiar de la versión base</label><select name="modo_copia"><option value="completa">Valoraciones, evidencias, observaciones y responsables</option><option value="solo_textos">Solo evidencias, observaciones y responsables (valorar de nuevo)</option></select>
        <label>Notas</label><textarea name="notas" placeholder="Alcance, fuentes de información, equipo evaluador…"></textarea>
        <div class="acciones"><button class="btn sec" type="button" data-cerrar>Cancelar</button><button class="btn" type="submit">Crear versión</button></div></form>`,
        (bg, cerrar) => { $('#f-v', bg).onsubmit = async e => { e.preventDefault(); try { const r = await api(`/api/organizaciones/${o.id}/diagnosticos`, { method: 'POST', body: Object.fromEntries(new FormData(e.target)) }); cerrar(); toast('Versión ' + r.version_numero + ' creada'); location.hash = `#/diag/${r.id}/llenar`; } catch (err) { toast(err.message, true); } }; });
    };
    const bm = $('#b-miembro'); if (bm) bm.onclick = () => modal(`<h2>Asignar usuario</h2><form id="f-m">
        <label>Correo electrónico *</label><input name="email" type="email" required inputmode="email">
        <label>Nombre (si el usuario aún no existe)</label><input name="nombre">
        ${estado.config.auth.local ? '<label>Contraseña inicial (solo para crear usuario local; mínimo 8 caracteres)</label><input name="password" type="text" autocomplete="off"><p class="hint">Si el usuario ingresará por ' + esc(estado.config.auth.gestor_nombre) + ', deje la contraseña vacía.</p>' : ''}
        <label>Rol en la organización</label><select name="rol"><option value="editor">Editor (diligencia el cuestionario)</option><option value="lector">Lector (solo consulta)</option></select>
        <input type="hidden" name="crear" value="1">
        <div class="acciones"><button class="btn sec" type="button" data-cerrar>Cancelar</button><button class="btn" type="submit">Asignar</button></div></form>`,
      (bg, cerrar) => { $('#f-m', bg).onsubmit = async e => { e.preventDefault(); try { await api(`/api/organizaciones/${o.id}/miembros`, { method: 'POST', body: Object.fromEntries(new FormData(e.target)) }); cerrar(); toast('Usuario asignado'); navegar(); } catch (err) { toast(err.message, true); } }; });
    $$('[data-quitar]').forEach(b => b.onclick = async () => { if (await confirmar('¿Retirar este usuario de la organización?', 'Retirar')) { await api(`/api/organizaciones/${o.id}/miembros/${b.dataset.quitar}`, { method: 'DELETE' }); navegar(); } });
  });

  // ---------- diligenciamiento ----------
  ruta('/diag/:id/llenar', async ({ id }, q) => {
    const data = await api('/api/diagnosticos/' + id);
    const { diagnostico: d, organizacion: o, items, editable } = data;
    const caps = [...new Map(items.map(i => [i.capitulo, i.capitulo_nombre])).entries()].map(([n, nombre]) => ({ n, nombre }));
    let capActual = Number(q.cap) || caps[0].n;
    let soloPendientes = q.pendientes === '1';
    const resumen = { cumplimiento: d.cumplimiento, brecha_total: d.brecha_total, avance_diligenciamiento: d.avance_diligenciamiento, conteo: d.conteo };

    function pintar() {
      const lista = items.filter(i => i.capitulo === capActual && (!soloPendientes || !i.respuesta?.valoracion));
      const idx = caps.findIndex(c => c.n === capActual);
      app.innerHTML = `
        <div class="fila entre"><div><h1 style="font-size:1.2rem">${esc(o.nombre)}</h1><p class="hint">Versión ${d.version_numero} · ${esc(d.titulo)} · ${editable ? 'en diligenciamiento' : 'solo lectura'}</p></div>
          <a class="btn peq sec" href="#/diag/${d.id}">Indicadores</a></div>
        ${!editable ? '<div class="alerta info">Esta versión está cerrada o usted tiene acceso de solo lectura. Las respuestas se muestran sin posibilidad de edición.</div>' : ''}
        <div class="sticky-sub">
          <div class="caps">${caps.map(c => { const tot = items.filter(i => i.capitulo === c.n); const val = tot.filter(i => i.respuesta?.valoracion).length; return `<button class="cap-btn ${c.n === capActual ? 'activo' : ''}" data-cap="${c.n}">Cap. ${c.n}<small>${val}/${tot.length}</small></button>`; }).join('')}</div>
          <div class="fila entre"><h2 style="margin:0;font-size:1rem">${capActual}. ${esc(caps[idx].nombre)}</h2><label style="margin:0;display:flex;align-items:center;gap:.3rem;font-weight:500"><input type="checkbox" id="chk-pend" style="width:auto" ${soloPendientes ? 'checked' : ''}> Solo pendientes</label></div>
        </div>
        ${lista.length ? lista.map(tarjetaPregunta).join('') : '<div class="tarjeta vacio">No hay preguntas pendientes en este capítulo.</div>'}
        <div class="nav-caps">${idx > 0 ? `<button class="btn sec" data-ir="${caps[idx - 1].n}">‹ Capítulo ${caps[idx - 1].n}</button>` : ''}${idx < caps.length - 1 ? `<button class="btn" data-ir="${caps[idx + 1].n}">Capítulo ${caps[idx + 1].n} ›</button>` : `<a class="btn" href="#/diag/${d.id}">Ver indicadores ›</a>`}</div>
        <div class="barra-inferior no-print"><div class="progreso"><span id="p-txt">${fmt(resumen.avance_diligenciamiento)} % diligenciado</span><div class="barra fina"><span id="p-bar" style="width:${resumen.avance_diligenciamiento}%"></span></div><strong id="p-cum" class="num">${fmt(resumen.cumplimiento)} %</strong></div></div>`;
      $$('[data-cap]').forEach(b => b.onclick = () => { capActual = Number(b.dataset.cap); pintar(); window.scrollTo(0, 0); });
      $$('[data-ir]').forEach(b => b.onclick = () => { capActual = Number(b.dataset.ir); pintar(); window.scrollTo(0, 0); });
      $('#chk-pend').onchange = e => { soloPendientes = e.target.checked; pintar(); };
      $$('.pregunta').forEach(enlazarPregunta);
    }
    function tarjetaPregunta(it) {
      const r = it.respuesta || {};
      return `<article class="pregunta v-${r.valoracion || 'null'}" data-item="${it.id}">
        <div class="meta"><span class="chip">${esc(it.codigo)}</span><span>Numeral ${esc(it.numeral)}</span>${r.estado_origen ? `<span class="chip v-${r.valoracion}" title="Valoración registrada en el instrumento original">Origen: ${esc(r.estado_origen)}</span>` : ''}</div>
        <div class="texto">${esc(it.pregunta)}</div>
        <div class="valoraciones">${CLAVES.map(k => `<button class="val-btn ${r.valoracion === k ? 'activo' : ''}" data-v="${k}" ${editable ? '' : 'disabled'} aria-pressed="${r.valoracion === k}"><span class="ic">${ICONO[k]}</span>${ETIQ[k]}</button>`).join('')}</div>
        <details class="detalles" ${(r.evidencia || r.observaciones) && !editable ? 'open' : ''}><summary>Evidencia, observaciones y responsable</summary>
          <label>Evidencia encontrada</label><textarea name="evidencia" ${editable ? '' : 'readonly'} placeholder="Documentos, registros o prácticas verificadas">${esc(r.evidencia)}</textarea>
          <label>Observaciones y acciones sugeridas</label><textarea name="observaciones" ${editable ? '' : 'readonly'} placeholder="REVISAR: … INCLUIR: …">${esc(r.observaciones)}</textarea>
          <label>Responsable de la evidencia</label><input name="responsable" ${editable ? '' : 'readonly'} value="${esc(r.responsable ?? it.responsable_sugerido ?? '')}" placeholder="${esc(it.responsable_sugerido || 'Área o cargo responsable')}">
        </details>
        <div class="guardado" aria-live="polite"></div></article>`;
    }
    function enlazarPregunta(el) {
      if (!editable) return;
      const itemId = el.dataset.item;
      const it = items.find(i => i.id === itemId);
      const g = $('.guardado', el);
      let timer;
      async function guardar(body) {
        g.textContent = 'Guardando…'; g.className = 'guardado';
        try {
          const r = await api(`/api/diagnosticos/${d.id}/respuestas/${itemId}`, { method: 'PUT', body });
          it.respuesta = { ...(it.respuesta || {}), ...r.respuesta };
          Object.assign(resumen, r.resumen);
          g.textContent = 'Guardado'; g.className = 'guardado ok';
          el.className = 'pregunta v-' + (it.respuesta.valoracion || 'null');
          $('#p-txt').textContent = fmt(resumen.avance_diligenciamiento) + ' % diligenciado';
          $('#p-bar').style.width = resumen.avance_diligenciamiento + '%';
          $('#p-cum').textContent = fmt(resumen.cumplimiento) + ' %';
          const cb = $(`.cap-btn[data-cap="${it.capitulo}"] small`); if (cb) { const tot = items.filter(i => i.capitulo === it.capitulo); cb.textContent = tot.filter(i => i.respuesta?.valoracion).length + '/' + tot.length; }
        } catch (err) { g.textContent = 'Error al guardar: ' + err.message; g.className = 'guardado err'; }
      }
      $$('.val-btn', el).forEach(b => b.onclick = () => {
        const nuevo = b.classList.contains('activo') ? null : b.dataset.v;
        $$('.val-btn', el).forEach(x => { x.classList.toggle('activo', x.dataset.v === nuevo); x.setAttribute('aria-pressed', x.dataset.v === nuevo); });
        guardar({ valoracion: nuevo });
      });
      $$('textarea, input', el).forEach(inp => {
        inp.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => guardar({ [inp.name]: inp.value }), 900); });
        inp.addEventListener('blur', () => { clearTimeout(timer); if ((it.respuesta?.[inp.name] ?? '') !== inp.value) guardar({ [inp.name]: inp.value }); });
      });
    }
    pintar();
  });

  // ---------- indicadores ----------
  ruta('/diag/:id', async ({ id }) => {
    const { diagnostico: d, organizacion: o, indicadores: ind } = await api(`/api/diagnosticos/${id}/indicadores`);
    const { diagnosticos, mi_rol } = await api('/api/organizaciones/' + o.id);
    const gestor = ['admin', 'consultor'].includes(estado.usuario.rol);
    const anterior = diagnosticos.filter(x => x.version_numero < d.version_numero).sort((a, b) => b.version_numero - a.version_numero)[0];
    let filtroCap = ''; let filtroPri = ''; let limite = 15;
    app.innerHTML = `
      <div class="fila entre"><div><h1 style="font-size:1.2rem">${esc(o.nombre)}</h1><p class="hint">Versión ${d.version_numero} · ${esc(d.titulo)} · ${fecha(d.fecha)} · <span class="chip ${d.estado === 'cerrado' ? 'cerrado' : 'abierto'}">${d.estado === 'cerrado' ? 'Cerrada' : 'En diligenciamiento'}</span></p></div></div>
      ${ind.conteo.sin_valorar ? `<div class="alerta">Hay ${ind.conteo.sin_valorar} pregunta(s) sin valorar. Los indicadores las cuentan como no cumplidas hasta que se valoren.</div>` : ''}
      <div class="hero">
        <div class="stat principal"><div class="lab">Cumplimiento global ISO 9001</div><div class="val">${fmt(ind.cumplimiento)} %</div><div class="sub">Nivel de madurez: <strong>${esc(ind.nivel.nombre)}</strong>. ${esc(ind.nivel.descripcion)}</div></div>
        <div class="stat"><div class="lab">Brecha para alcanzar ISO 9001</div><div class="val" style="color:var(--nocumple)">${fmt(ind.brecha_total)} %</div><div class="sub">${ind.items_para_cumplir} de ${ind.total_items} preguntas por cerrar</div></div>
        <div class="stat"><div class="lab">Capítulo más crítico</div><div class="val">${ind.capitulo_critico ? 'Cap. ' + ind.capitulo_critico.capitulo : '—'}</div><div class="sub">${ind.capitulo_critico ? esc(ind.capitulo_critico.nombre) + ' · ' + fmt(ind.capitulo_critico.cumplimiento) + ' %' : ''}</div></div>
        <div class="stat"><div class="lab">Avance del diligenciamiento</div><div class="val">${fmt(ind.avance_diligenciamiento)} %</div><div class="sub">${ind.items_valorados} de ${ind.total_items} valoradas</div></div>
      </div>
      <div class="acciones">
        <a class="btn" href="#/diag/${d.id}/llenar">${d.estado === 'cerrado' ? 'Ver respuestas' : 'Diligenciar'}</a>
        <a class="btn sec" href="#/imprimir/${o.id}?v=${d.id}">Imprimir</a>
        <a class="btn sec" href="/api/diagnosticos/${d.id}/export.csv">Exportar CSV</a>
        ${anterior ? `<a class="btn sec" href="#/diag/${d.id}/comparar/${anterior.id}">Comparar con v${anterior.version_numero}</a>` : ''}
        ${d.estado !== 'cerrado' && mi_rol === 'editor' ? `<button class="btn suave" id="b-cerrar">Cerrar versión</button>` : ''}
        ${d.estado === 'cerrado' && gestor ? `<button class="btn suave" id="b-reabrir">Reabrir versión</button>` : ''}
        ${estado.usuario.rol === 'admin' ? `<button class="btn peligro" id="b-eliminar">Eliminar versión</button>` : ''}
      </div>
      <div class="tarjeta"><h2>Distribución de valoraciones</h2>${distribucion(ind.conteo, ind.total_items)}</div>
      <div class="tarjeta"><h2>Cumplimiento por capítulo de la norma</h2><p class="hint">Toque un capítulo para ver sus preguntas pendientes.</p>${barrasCapitulo(ind.por_capitulo)}</div>
      <div class="tarjeta"><details class="detalles"><summary style="font-size:1.15rem;color:inherit">Cumplimiento por numeral</summary><div class="tabla-scroll"><table><thead><tr><th>Numeral</th><th class="der">Preg.</th><th class="der">${ICONO.cumple}</th><th class="der">${ICONO.cumple_parcial}</th><th class="der">${ICONO.no_cumple}</th><th class="der">${ICONO.sin_evidencia}</th><th style="min-width:120px">Cumplimiento</th></tr></thead>
        <tbody>${ind.por_numeral.map(n => `<tr><td>${esc(n.numeral)}</td><td class="der">${n.total}</td><td class="der">${n.cumple}</td><td class="der">${n.cumple_parcial}</td><td class="der">${n.no_cumple}</td><td class="der">${n.sin_evidencia}</td><td><div class="progreso"><div class="barra fina"><span style="width:${n.cumplimiento}%"></span></div><span class="num">${fmt(n.cumplimiento)} %</span></div></td></tr>`).join('')}</tbody></table></div></details></div>
      <div class="tarjeta"><h2>Brecha: requisitos por cerrar</h2>
        <div class="fila"><select id="f-cap" style="width:auto;flex:1"><option value="">Todos los capítulos</option>${ind.por_capitulo.map(c => `<option value="${c.capitulo}">Cap. ${c.capitulo} · ${esc(c.nombre)}</option>`).join('')}</select>
          <select id="f-pri" style="width:auto;flex:1"><option value="">Toda prioridad</option><option value="alta">Prioridad alta</option><option value="media">Prioridad media</option></select></div>
        <p class="hint" style="margin-top:.5rem">Prioridad alta: no cumple, sin evidencia o sin valorar. Prioridad media: cumplimiento parcial.</p>
        <div id="lista-brecha"></div></div>
      <div class="tarjeta"><h2>Carga por responsable</h2><div class="tabla-scroll"><table><thead><tr><th>Responsable</th><th class="der">Preguntas</th><th class="der">Pendientes</th><th class="der">Cumpl.</th></tr></thead><tbody>${ind.por_responsable.map(r => `<tr><td>${esc(r.responsable)}</td><td class="der">${r.total}</td><td class="der">${r.pendientes}</td><td class="der num">${fmt(r.cumplimiento)} %</td></tr>`).join('')}</tbody></table></div></div>
      ${d.notas ? `<div class="tarjeta"><h2>Notas de la versión</h2><p>${esc(d.notas)}</p></div>` : ''}`;
    function pintarBrecha() {
      const todos = ind.brecha.filter(b => (!filtroCap || String(b.capitulo) === filtroCap) && (!filtroPri || b.prioridad === filtroPri));
      const l = todos.slice(0, limite);
      $('#lista-brecha').innerHTML = todos.length ? `<div class="tabla-scroll"><table><thead><tr><th>ID</th><th>Numeral</th><th>Pregunta</th><th>Valoración</th><th>Prioridad</th><th>Responsable</th><th>Acción sugerida</th></tr></thead>
        <tbody>${l.map(b => `<tr><td>${esc(b.codigo)}</td><td>${esc(b.numeral)}</td><td>${esc(b.pregunta)}</td><td><span class="chip v-${b.valoracion}">${ICONO[b.valoracion ?? 'sin_valorar']} ${esc(b.etiqueta)}</span></td><td>${b.prioridad === 'alta' ? '<strong>Alta</strong>' : 'Media'}</td><td>${esc(b.responsable)}</td><td>${esc(b.observaciones)}</td></tr>`).join('')}</tbody></table></div><p class="hint">Se muestran ${l.length} de ${todos.length} requisito(s).</p>${todos.length > l.length ? '<button class="btn sec bloque" id="b-mas">Mostrar todos</button>' : ''}` : '<p class="vacio">Sin requisitos pendientes con los filtros aplicados.</p>';
      const bm = $('#b-mas'); if (bm) bm.onclick = () => { limite = Infinity; pintarBrecha(); };
    }
    pintarBrecha();
    $('#f-cap').onchange = e => { filtroCap = e.target.value; limite = 15; pintarBrecha(); };
    $('#f-pri').onchange = e => { filtroPri = e.target.value; limite = 15; pintarBrecha(); };
    $$('.fila-cap').forEach(f => f.onclick = () => location.hash = `#/diag/${d.id}/llenar?cap=${f.dataset.cap}&pendientes=1`);
    const bc = $('#b-cerrar'); if (bc) bc.onclick = async () => { if (await confirmar('Al cerrar la versión se congelan las respuestas y se conserva como registro histórico. Los cambios posteriores requerirán una nueva versión.', 'Cerrar versión')) { try { await api(`/api/diagnosticos/${d.id}/cerrar`, { method: 'POST' }); toast('Versión cerrada'); navegar(); } catch (e) { toast(e.message, true); } } };
    const br = $('#b-reabrir'); if (br) br.onclick = async () => { if (await confirmar('¿Reabrir esta versión para edición?', 'Reabrir')) { try { await api(`/api/diagnosticos/${d.id}/reabrir`, { method: 'POST' }); navegar(); } catch (e) { toast(e.message, true); } } };
    const be = $('#b-eliminar'); if (be) be.onclick = async () => { if (await confirmar('Esta acción elimina la versión y todas sus respuestas de forma definitiva.', 'Eliminar')) { try { await api(`/api/diagnosticos/${d.id}`, { method: 'DELETE' }); location.hash = '#/org/' + o.id; } catch (e) { toast(e.message, true); } } };
  });

  ruta('/diag/:id/comparar/:otroId', async ({ id, otroId }) => {
    const { base, actual, comparacion: c, cambios } = await api(`/api/diagnosticos/${id}/comparar/${otroId}`);
    const { organizacion: o, diagnosticos } = await api('/api/organizaciones/' + actual.organizacion_id);
    app.innerHTML = `<h1 style="font-size:1.2rem">${esc(o.nombre)}</h1><p class="hint">Comparación de versiones</p>
      <div class="tarjeta"><div class="grid-2"><div><label>Versión base</label><select id="s-base">${diagnosticos.map(x => `<option value="${x.id}" ${x.id === base.id ? 'selected' : ''}>v${x.version_numero} · ${esc(x.titulo)} (${fmt(x.cumplimiento)} %)</option>`).join('')}</select></div>
        <div><label>Versión actual</label><select id="s-act">${diagnosticos.map(x => `<option value="${x.id}" ${x.id === actual.id ? 'selected' : ''}>v${x.version_numero} · ${esc(x.titulo)} (${fmt(x.cumplimiento)} %)</option>`).join('')}</select></div></div></div>
      <div class="hero"><div class="stat"><div class="lab">v${base.version_numero} · ${fecha(base.fecha)}</div><div class="val">${fmt(c.cumplimiento.antes)} %</div></div>
        <div class="stat"><div class="lab">v${actual.version_numero} · ${fecha(actual.fecha)}</div><div class="val">${fmt(c.cumplimiento.despues)} %</div></div>
        <div class="stat"><div class="lab">Variación</div><div class="val" style="color:${c.cumplimiento.delta > 0 ? '#0a6a0a' : c.cumplimiento.delta < 0 ? '#9a2323' : 'inherit'}">${c.cumplimiento.delta > 0 ? '+' : ''}${fmt(c.cumplimiento.delta)} pp</div></div></div>
      <div class="tarjeta"><h2>Cumplimiento por capítulo</h2>${barrasComparacion(c.por_capitulo)}</div>
      <div class="tarjeta"><h2>Cambios en el conteo de valoraciones</h2><table><thead><tr><th>Valoración</th><th class="der">Base</th><th class="der">Actual</th><th class="der">Δ</th></tr></thead><tbody>${c.conteo.map(x => `<tr><td>${ICONO[x.clave]} ${ETIQ[x.clave]}</td><td class="der">${x.antes}</td><td class="der">${x.despues}</td><td class="der">${x.delta > 0 ? '+' : ''}${x.delta}</td></tr>`).join('')}</tbody></table></div>
      <div class="tarjeta"><h2>Preguntas con cambio de valoración (${cambios.length})</h2>${cambios.length ? `<div class="tabla-scroll"><table><thead><tr><th>ID</th><th>Numeral</th><th>Pregunta</th><th>Antes</th><th>Después</th></tr></thead><tbody>${cambios.map(x => `<tr><td>${esc(x.codigo)}</td><td>${esc(x.numeral)}</td><td>${esc(x.pregunta)}</td><td><span class="chip v-${x.antes}">${ETIQ[x.antes ?? 'sin_valorar']}</span></td><td><span class="chip v-${x.despues}">${ETIQ[x.despues ?? 'sin_valorar']}</span></td></tr>`).join('')}</tbody></table></div>` : '<p class="vacio">Sin cambios entre las dos versiones.</p>'}</div>`;
    const ir = () => location.hash = `#/diag/${$('#s-act').value}/comparar/${$('#s-base').value}`;
    $('#s-base').onchange = ir; $('#s-act').onchange = ir;
  });

  // ---------- impresión ----------
  function encabezadoImpresion(titulo, o, d) {
    return `<div class="encabezado"><h1>${esc(titulo)}</h1><p class="hint">Referencia: ISO 9001:2015 y Enmienda 1:2024. Preguntas propias de aplicación. No es un instrumento oficial de ISO.</p></div>
      <div class="datos"><div><strong>Organización:</strong> ${esc(o?.nombre) || '&nbsp;'}</div><div><strong>Versión:</strong> ${d ? 'v' + d.version_numero + ' · ' + esc(d.titulo) : '&nbsp;'}</div><div><strong>Fecha:</strong> ${d ? fecha(d.fecha) : '&nbsp;'}</div><div><strong>Evaluador(es):</strong> &nbsp;</div><div><strong>Estado:</strong> ${d ? (d.estado === 'cerrado' ? 'Cerrada' : 'En diligenciamiento') : '&nbsp;'}</div><div><strong>Impreso:</strong> ${new Date().toLocaleString('es-CO')}</div></div>
      <div class="escala"><strong>Escala de valoración:</strong> ${ICONO.cumple} Cumple (100 %) · ${ICONO.cumple_parcial} Cumplimiento parcial (50 %) · ${ICONO.no_cumple} No cumple (0 %) · ${ICONO.sin_evidencia} Sin evidencia (0 %). El cumplimiento global es el promedio ponderado de las preguntas.</div>`;
  }
  function tablaImpresion(items, respMap, blanco) {
    let cap = null, html = '';
    for (const it of items) {
      if (it.capitulo !== cap) { cap = it.capitulo; html += `<tr class="cap-titulo"><td colspan="${blanco ? 6 : 7}">Capítulo ${cap}. ${esc(it.capitulo_nombre)}</td></tr>`; }
      const r = respMap ? (respMap.get(it.id) || {}) : {};
      html += `<tr><td>${esc(it.codigo)}</td><td>${esc(it.numeral)}</td><td>${esc(it.pregunta)}</td>
        <td class="casillas">${CLAVES.map(k => `<span class="${r.valoracion === k ? 'marcado' : ''}">${ETIQ[k]}</span>`).join('<br>')}</td>
        <td>${blanco ? '&nbsp;' : esc(r.evidencia)}</td><td>${blanco ? '&nbsp;' : esc(r.observaciones)}</td>${blanco ? '' : `<td>${esc(r.responsable ?? it.responsable_sugerido)}</td>`}</tr>`;
    }
    return `<table><thead><tr><th style="width:5%">ID</th><th style="width:5%">Numeral</th><th style="width:${blanco ? 34 : 26}%">Pregunta de diagnóstico</th><th style="width:12%">Valoración</th><th>Evidencia</th><th>Observaciones</th>${blanco ? '' : '<th style="width:10%">Responsable</th>'}</tr></thead><tbody>${html}</tbody></table>
      <div class="firma"><div>Elaboró / evaluador</div><div>Revisó / responsable de calidad</div></div>`;
  }

  ruta('/imprimir-blanco', async (_, q) => {
    const { instrumento, items } = await api('/api/instrumentos/iso9001-2015-amd1-2024/items');
    app.innerHTML = `<div class="no-print tarjeta"><div class="fila entre"><div><h2 style="margin:0">Formato en blanco</h2><p class="hint">${esc(instrumento.nombre)} · ${items.length} preguntas</p></div><div class="fila"><input id="i-org" placeholder="Nombre de la organización" value="${esc(q.org)}" style="width:auto"><button class="btn" id="b-print">Imprimir</button></div></div></div>
      <div class="tarjeta impresion" id="hoja"></div>`;
    const pintar = () => { $('#hoja').innerHTML = encabezadoImpresion('Instrumento de diagnóstico ISO 9001 (formato para diligenciar)', { nombre: $('#i-org').value }, null) + tablaImpresion(items, null, true); };
    pintar(); $('#i-org').oninput = pintar; $('#b-print').onclick = () => window.print();
  }, { publica: true });

  ruta('/imprimir/:orgId', async ({ orgId }, q) => {
    const { organizacion: o, diagnosticos } = await api('/api/organizaciones/' + orgId);
    if (!diagnosticos.length) { app.innerHTML = '<div class="tarjeta vacio">Esta organización no tiene versiones para imprimir.</div>'; return; }
    const sel = diagnosticos.find(d => d.id === q.v) || diagnosticos[0];
    const data = await api('/api/diagnosticos/' + sel.id);
    const { indicadores: ind } = await api(`/api/diagnosticos/${sel.id}/indicadores`);
    const respMap = new Map(data.items.filter(i => i.respuesta).map(i => [i.id, i.respuesta]));
    app.innerHTML = `<div class="no-print tarjeta"><div class="fila entre"><div><h2 style="margin:0">Imprimir diagnóstico diligenciado</h2><p class="hint">${esc(o.nombre)}</p></div>
        <div class="fila" style="width:100%"><select id="s-ver" style="max-width:100%">${diagnosticos.map(d => `<option value="${d.id}" ${d.id === sel.id ? 'selected' : ''}>Versión ${d.version_numero} · ${esc(d.titulo)} · ${fecha(d.fecha)}</option>`).join('')}</select>
        <label style="margin:0;display:flex;align-items:center;gap:.3rem;font-weight:500"><input type="checkbox" id="chk-ind" checked style="width:auto"> Incluir indicadores</label><button class="btn" id="b-print">Imprimir</button></div></div></div>
      <div class="tarjeta impresion" id="hoja"></div>`;
    const pintar = () => {
      const incluir = $('#chk-ind').checked;
      $('#hoja').innerHTML = encabezadoImpresion('Diagnóstico de implementación ISO 9001', o, data.diagnostico) +
        (incluir ? `<div class="resumen-imp"><div><strong>${fmt(ind.cumplimiento)} %</strong>Cumplimiento global</div><div><strong>${fmt(ind.brecha_total)} %</strong>Brecha ISO 9001</div><div><strong>${esc(ind.nivel.nombre)}</strong>Nivel de madurez</div>${ind.por_capitulo.map(c => `<div><strong>${fmt(c.cumplimiento)} %</strong>Cap. ${c.capitulo}</div>`).join('')}</div>
          <p style="font-size:.85rem">${ICONO.cumple} Cumple: ${ind.conteo.cumple} · ${ICONO.cumple_parcial} Parcial: ${ind.conteo.cumple_parcial} · ${ICONO.no_cumple} No cumple: ${ind.conteo.no_cumple} · ${ICONO.sin_evidencia} Sin evidencia: ${ind.conteo.sin_evidencia}${ind.conteo.sin_valorar ? ' · Sin valorar: ' + ind.conteo.sin_valorar : ''}</p>` : '') +
        tablaImpresion(data.items, respMap, false);
    };
    pintar();
    $('#chk-ind').onchange = pintar;
    $('#s-ver').onchange = e => location.hash = `#/imprimir/${orgId}?v=${e.target.value}`;
    $('#b-print').onclick = () => window.print();
  });

  // ---------- usuarios y perfil ----------
  ruta('/usuarios', async () => {
    if (!['admin', 'consultor'].includes(estado.usuario.rol)) { app.innerHTML = '<div class="tarjeta vacio">Solo administradores.</div>'; return; }
    const { usuarios } = await api('/api/usuarios');
    const admin = estado.usuario.rol === 'admin';
    app.innerHTML = `<div class="fila entre"><h1>Usuarios</h1>${admin && estado.config.auth.local ? '<button class="btn peq" id="b-nuevo">+ Usuario local</button>' : ''}</div>
      <p class="hint">Los usuarios que ingresan por ${esc(estado.config.auth.gestor_nombre)} se crean automáticamente en su primer acceso y sincronizan su nombre y rol desde el gestor.</p>
      <div class="tarjeta"><input id="buscar-u" placeholder="Buscar por nombre o correo" inputmode="search"></div>
      <div id="lista-usuarios"></div>`;
    function pintarUsuarios() {
      const q = ($('#buscar-u').value || '').toLowerCase();
      const l = usuarios.filter(u => !q || u.nombre.toLowerCase().includes(q) || u.email.toLowerCase().includes(q));
      $('#lista-usuarios').innerHTML = l.length ? l.map(u => `<div class="tarjeta" style="${u.activo ? '' : 'opacity:.55'}">
        <div class="fila entre"><div><strong>${esc(u.nombre)}</strong><br><span class="hint">${esc(u.email)} · ${u.rol} · ${u.origen === 'gestor' ? esc(estado.config.auth.gestor_nombre) : 'local'}${u.activo ? '' : ' · inactivo'}</span></div></div>
        <p class="hint" style="margin:.4rem 0 0">${['admin', 'consultor'].includes(u.rol) ? 'Acceso a todas las organizaciones por su rol global.' : (u.total_organizaciones ? `${u.total_organizaciones} organización(es): ${esc(u.organizaciones)}` : 'Sin organizaciones asignadas.')}</p>
        <div class="acciones"><button class="btn peq suave" data-orgs="${u.id}">Organizaciones</button>${admin ? `<button class="btn peq sec" data-edit="${u.id}">Editar</button>` : ''}</div></div>`).join('') : '<div class="tarjeta vacio">Sin resultados.</div>';
      $$('[data-edit]').forEach(b => b.onclick = () => form(usuarios.find(u => u.id === b.dataset.edit)));
      $$('[data-orgs]').forEach(b => b.onclick = () => asignarOrganizaciones(usuarios.find(u => u.id === b.dataset.orgs)));
    }
    $('#buscar-u').oninput = pintarUsuarios;
    const form = (u) => modal(`<h2>${u ? 'Editar' : 'Nuevo'} usuario</h2><form id="f-u">
      <label>Nombre *</label><input name="nombre" required value="${esc(u?.nombre)}">
      <label>Correo *</label><input name="email" type="email" required value="${esc(u?.email)}" ${u ? 'readonly' : ''}>
      <label>Rol global</label><select name="rol"><option value="usuario" ${u?.rol === 'usuario' ? 'selected' : ''}>Usuario (solo organizaciones asignadas)</option><option value="consultor" ${u?.rol === 'consultor' ? 'selected' : ''}>Consultor (todas las organizaciones)</option><option value="admin" ${u?.rol === 'admin' ? 'selected' : ''}>Administrador</option></select>
      ${u ? `<label>Activo</label><select name="activo"><option value="1" ${u.activo ? 'selected' : ''}>Sí</option><option value="0" ${!u.activo ? 'selected' : ''}>No</option></select>` : ''}
      ${!u || u.origen === 'local' ? `<label>${u ? 'Nueva contraseña (opcional)' : 'Contraseña *'}</label><input name="password" type="text" autocomplete="off" ${u ? '' : 'required'} minlength="8">` : ''}
      <div class="acciones"><button class="btn sec" type="button" data-cerrar>Cancelar</button><button class="btn" type="submit">Guardar</button></div></form>`,
      (bg, cerrar) => { $('#f-u', bg).onsubmit = async e => { e.preventDefault(); const body = Object.fromEntries(new FormData(e.target)); if (body.activo !== undefined) body.activo = body.activo === '1'; if (!body.password) delete body.password; try { await api(u ? '/api/usuarios/' + u.id : '/api/usuarios', { method: u ? 'PUT' : 'POST', body }); cerrar(); toast('Guardado'); navegar(); } catch (err) { toast(err.message, true); } }; });
    const bn = $('#b-nuevo'); if (bn) bn.onclick = () => form(null);
    pintarUsuarios();
  });

  // Asignación de una o varias organizaciones a un usuario (selección múltiple con rol por organización).
  async function asignarOrganizaciones(u) {
    const { organizaciones } = await api(`/api/usuarios/${u.id}/organizaciones`);
    const global = ['admin', 'consultor'].includes(u.rol);
    modal(`<h2>Organizaciones de ${esc(u.nombre)}</h2>
      <p class="hint">Marque las organizaciones que este usuario podrá diligenciar o consultar. ${global ? 'Este usuario tiene acceso a todas por su rol global; la asignación solo aplicaría si cambia a rol usuario.' : ''}</p>
      ${organizaciones.length ? `<input id="buscar-o" placeholder="Filtrar organizaciones" inputmode="search" style="margin-bottom:.5rem">
      <div class="fila entre" style="margin-bottom:.4rem"><button type="button" class="btn peq sec" id="o-todas">Seleccionar todas</button><button type="button" class="btn peq sec" id="o-ninguna">Quitar todas</button><span class="hint" id="o-cuenta"></span></div>
      <form id="f-orgs"><div id="lista-orgs">${organizaciones.map(o => `<label class="sel-org" data-texto="${esc((o.nombre + ' ' + (o.sigla || '') + ' ' + (o.sector || '') + ' ' + (o.ciudad || '')).toLowerCase())}">
          <input type="checkbox" name="org" value="${o.id}" ${o.asignada ? 'checked' : ''}>
          <span class="sel-org-nombre"><strong>${esc(o.nombre)}</strong><span class="hint">${[o.sigla, o.sector, o.ciudad].filter(Boolean).map(esc).join(' · ')}</span></span>
          <select name="rol-${o.id}" aria-label="Rol"><option value="editor" ${o.rol_asignado !== 'lector' ? 'selected' : ''}>Editor</option><option value="lector" ${o.rol_asignado === 'lector' ? 'selected' : ''}>Lector</option></select>
        </label>`).join('')}</div>
        <div class="acciones"><button class="btn sec" type="button" data-cerrar>Cancelar</button><button class="btn" type="submit">Guardar asignación</button></div></form>` : '<p class="vacio">Todavía no hay organizaciones creadas.</p><div class="acciones"><button class="btn sec" type="button" data-cerrar>Cerrar</button></div>'}`,
      (bg, cerrar) => {
        const f = $('#f-orgs', bg); if (!f) return;
        const cuenta = () => { $('#o-cuenta', bg).textContent = $$('input[name=org]:checked', bg).length + ' de ' + organizaciones.length + ' seleccionadas'; };
        cuenta();
        f.addEventListener('change', cuenta);
        $('#buscar-o', bg).oninput = e => { const q = e.target.value.toLowerCase(); $$('.sel-org', bg).forEach(l => l.hidden = q && !l.dataset.texto.includes(q)); };
        $('#o-todas', bg).onclick = () => { $$('.sel-org:not([hidden]) input[name=org]', bg).forEach(c => c.checked = true); cuenta(); };
        $('#o-ninguna', bg).onclick = () => { $$('.sel-org:not([hidden]) input[name=org]', bg).forEach(c => c.checked = false); cuenta(); };
        f.onsubmit = async e => {
          e.preventDefault();
          const sel = $$('input[name=org]:checked', bg).map(c => ({ id: c.value, rol: f[`rol-${c.value}`].value }));
          try { const r = await api(`/api/usuarios/${u.id}/organizaciones`, { method: 'PUT', body: { organizaciones: sel } }); cerrar(); toast(`${r.asignadas} organización(es) asignada(s)`); navegar(); } catch (err) { toast(err.message, true); }
        };
      });
  }

  ruta('/perfil', async () => {
    const u = estado.usuario;
    app.innerHTML = `<h1>Mi perfil</h1><div class="tarjeta"><p><strong>${esc(u.nombre)}</strong><br>${esc(u.email)}<br>Rol: ${u.rol} · Origen: ${u.origen === 'gestor' ? esc(estado.config.auth.gestor_nombre) : 'usuario local'}</p></div>
      ${u.origen === 'local' ? `<div class="tarjeta"><h2>Cambiar contraseña</h2><form id="f-pw"><label>Contraseña actual</label><input name="actual" type="password" required autocomplete="current-password"><label>Nueva contraseña (mínimo 8 caracteres)</label><input name="nueva" type="password" required minlength="8" autocomplete="new-password"><div class="acciones"><button class="btn" type="submit">Actualizar</button></div></form></div>`
        : `<div class="alerta info">Su cuenta se administra en <a href="${esc(estado.config.auth.gestor_url)}" target="_blank" rel="noopener">${esc(estado.config.auth.gestor_nombre)}</a>.</div>`}`;
    const f = $('#f-pw'); if (f) f.onsubmit = async e => { e.preventDefault(); try { await api('/api/auth/cambiar-password', { method: 'POST', body: Object.fromEntries(new FormData(f)) }); toast('Contraseña actualizada'); f.reset(); } catch (err) { toast(err.message, true); } };
  });

  // ---------- arranque ----------
  function pintarUsuario() {
    const u = estado.usuario;
    $('#drawer-user').innerHTML = u ? `<strong>${esc(u.nombre)}</strong><span>${esc(u.email)} · ${u.rol}</span>` : '';
    $$('[data-admin]').forEach(a => a.hidden = !u || !['admin', 'consultor'].includes(u.rol));
    $('#btn-menu').hidden = !u;
  }
  function abrirMenu(abrir) { $('#drawer').hidden = !abrir; }
  $('#btn-menu').onclick = () => abrirMenu(true);
  $('#drawer-backdrop').onclick = () => abrirMenu(false);
  $$('.drawer-link').forEach(a => a.addEventListener('click', () => abrirMenu(false)));
  $('#btn-back').onclick = () => { if (history.length > 1) history.back(); else location.hash = '#/'; };
  $('#btn-logout').onclick = async () => { await api('/api/auth/logout', { method: 'POST' }); estado.usuario = null; pintarUsuario(); location.hash = '#/login'; };
  window.addEventListener('hashchange', navegar);

  (async () => {
    // Token del gestor entregado por app.proyectoia.org como parámetro (?token=…): se canjea por una sesión propia.
    const p = new URLSearchParams(location.search);
    if (p.get('token')) {
      try { await api('/api/auth/gestor/token', { method: 'POST', body: { token: p.get('token') } }); } catch (e) { toast(e.message, true); }
      history.replaceState(null, '', location.pathname + location.hash);
    }
    const [cfg, me] = await Promise.all([api('/api/config'), api('/api/me').catch(() => ({ usuario: null }))]);
    estado.config = cfg; estado.usuario = me.usuario;
    $('#link-app-proyectoia').href = cfg.auth.app_url;
    pintarUsuario();
    navegar();
  })();
})();
