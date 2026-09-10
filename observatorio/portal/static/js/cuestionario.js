// Comportamiento de la página pública de un cuestionario: aceptación de políticas, pasos, validación, campos
// "otro", límites de selección, bloques condicionales, ranking sin repetidos, autocompletar de entidades,
// departamento y municipio, borrador local y envío por fetch. Todo es genérico: lo gobierna el HTML generado.
(function () {
  'use strict';
  const form = document.getElementById('cuestionario');
  if (!form) return;
  const TOTAL = Number(form.dataset.total) || 1;
  const presentacion = document.getElementById('presentacion');
  const terminos = document.getElementById('acepta_politicas');
  const terminosAlInicio = terminos && presentacion && presentacion.contains(terminos);
  const progressText = document.getElementById('steps-progress-text');
  const progressFill = document.getElementById('steps-progress-bar-fill');
  const aviso = document.getElementById('aviso');
  const DRAFT_KEY = form.dataset.borrador;
  const DUPLICADOS = JSON.parse(form.dataset.duplicados || '[]');
  let currentStep = 1;
  let restaurando = false;

  // ---------------------------------------------------------------- avisos
  function mostrarAviso(icono, titulo, texto, opciones) {
    opciones = opciones || {};
    aviso.querySelector('#aviso-icono').textContent = icono;
    aviso.querySelector('#aviso-titulo').textContent = titulo;
    aviso.querySelector('#aviso-texto').textContent = texto;
    aviso.querySelector('.aviso-caja').classList.toggle('aviso-cargando', !!opciones.cargando);
    aviso.querySelector('#aviso-cerrar').hidden = !!opciones.cargando;
    aviso.hidden = false;
  }
  function cerrarAviso() { aviso.hidden = true; }
  aviso.querySelector('#aviso-cerrar').addEventListener('click', cerrarAviso);

  // ---------------------------------------------------------------- políticas al inicio
  function actualizarVisibilidad() {
    if (!terminosAlInicio) return;
    form.classList.toggle('visible', terminos.checked);
  }
  if (terminosAlInicio) {
    terminos.addEventListener('change', function () {
      actualizarVisibilidad();
      if (terminos.checked) setTimeout(function () { form.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 50);
    });
    actualizarVisibilidad();
  }

  // ---------------------------------------------------------------- pasos
  function goToStep(n, opts) {
    opts = opts || {};
    document.querySelectorAll('.form-step').forEach(function (s) { s.classList.remove('active'); });
    document.querySelectorAll('.steps-progress .step-item').forEach(function (d, i) {
      d.classList.remove('active', 'done');
      if (i + 1 < n) d.classList.add('done'); else if (i + 1 === n) d.classList.add('active');
    });
    const target = document.querySelector('.form-step[data-step="' + n + '"]');
    if (target) target.classList.add('active');
    currentStep = n;
    if (progressText) progressText.textContent = 'Paso ' + n + ' de ' + TOTAL;
    if (progressFill) progressFill.style.width = Math.round((n / TOTAL) * 100) + '%';
    if (!opts.silent) window.scrollTo({ top: form.offsetTop - 20, behavior: 'smooth' });
  }
  function shake(el) {
    if (!el) return;
    el.classList.add('btn-shake');
    el.addEventListener('animationend', function () { el.classList.remove('btn-shake'); }, { once: true });
  }
  function oculto(el) { return !!el.closest('.conditional-block.is-hidden'); }

  function validarPaso(stepEl) {
    var invalido = null;
    stepEl.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (invalido || el.disabled || oculto(el)) return;
      if (el.type === 'checkbox' && el.closest('[data-checkbox-group]')) return;
      if (el.type === 'file') {
        var max = Number(el.dataset.maxMb || 10) * 1024 * 1024;
        if (el.files && el.files[0] && el.files[0].size > max) { el.setCustomValidity('El archivo supera ' + (el.dataset.maxMb || 10) + ' MB.'); invalido = el; return; }
        el.setCustomValidity('');
      }
      if (!el.checkValidity()) invalido = el;
    });
    return invalido;
  }
  function grupoInvalido(stepEl) {
    var grupos = stepEl.querySelectorAll('[data-checkbox-group]');
    for (var i = 0; i < grupos.length; i++) {
      var g = grupos[i];
      if (oculto(g)) continue;
      var marcados = g.querySelectorAll('input[type="checkbox"]:checked').length;
      var min = Number(g.dataset.min || 0), max = Number(g.dataset.max || 0);
      if (marcados < min || (max && marcados > max)) return g;
    }
    var rankings = stepEl.querySelectorAll('[data-ranking]');
    for (var j = 0; j < rankings.length; j++) {
      var r = rankings[j];
      if (oculto(r)) continue;
      var valores = Array.prototype.map.call(r.querySelectorAll('select'), function (s) { return s.value; }).filter(Boolean);
      if (new Set(valores).size !== valores.length) return r;
    }
    return null;
  }

  // Al avanzar de paso se pregunta al servidor si ya existe una respuesta con los campos marcados como únicos.
  async function revisarDuplicados(stepEl) {
    var url = form.dataset.existe;
    if (!url || !DUPLICADOS.length || form.action.indexOf('vista_previa=1') >= 0) return true;
    for (var i = 0; i < DUPLICADOS.length; i++) {
      var campo = stepEl.querySelector('[name="' + DUPLICADOS[i] + '"]');
      if (!campo || !campo.value.trim()) continue;
      try {
        var res = await fetch(url + '?campo=' + encodeURIComponent(DUPLICADOS[i]) + '&valor=' + encodeURIComponent(campo.value.trim()), { headers: { Accept: 'application/json' } });
        var datos = await res.json();
        if (datos.existe) { mostrarAviso('⛔', 'Respuesta ya registrada', datos.mensaje || 'Ya existe una respuesta registrada con estos datos.'); return false; }
      } catch (e) { /* si el servidor no contesta, no se bloquea el avance */ }
    }
    return true;
  }

  function prepararPaso(n) {
    var stepEl = document.querySelector('.form-step[data-step="' + n + '"]');
    if (!stepEl) return;
    var next = document.getElementById('btn-next-' + n);
    var prev = document.getElementById('btn-prev-' + n);
    function actualizar() { if (next) next.disabled = !!validarPaso(stepEl) || !!grupoInvalido(stepEl); }
    stepEl.querySelectorAll('input, select, textarea').forEach(function (el) { el.addEventListener('input', actualizar); el.addEventListener('change', actualizar); });
    stepEl.actualizarBoton = actualizar;
    actualizar();
    if (next) next.addEventListener('click', async function () {
      var inv = validarPaso(stepEl);
      if (inv) { shake(next); (inv.closest('.pregunta') || inv).scrollIntoView({ behavior: 'smooth', block: 'center' }); inv.reportValidity(); return; }
      var g = grupoInvalido(stepEl);
      if (g) { shake(next); shake(g); g.scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
      var original = next.innerHTML;
      next.disabled = true; next.textContent = 'Verificando...';
      var ok = await revisarDuplicados(stepEl);
      next.innerHTML = original; next.disabled = false;
      if (!ok) { shake(next); return; }
      goToStep(n + 1);
    });
    if (prev) prev.addEventListener('click', function () { goToStep(n - 1); });
  }
  for (var i = 1; i <= TOTAL; i++) prepararPaso(i);

  // ---------------------------------------------------------------- campos "otro"
  document.querySelectorAll('.otro-wrap').forEach(function (wrap) {
    var nombre = wrap.dataset.otroDe, valor = wrap.dataset.otroValor;
    var controles = form.querySelectorAll('[name="' + nombre + '"], [name="' + nombre + '[]"]');
    function sync() {
      var activo = false;
      controles.forEach(function (c) {
        if (c.type === 'checkbox' || c.type === 'radio') { if (c.checked && c.value === valor) activo = true; }
        else if (c.value === valor) activo = true;
      });
      wrap.hidden = !activo;
      if (!activo && !restaurando) wrap.querySelector('input').value = '';
    }
    controles.forEach(function (c) { c.addEventListener('change', sync); });
    sync();
  });

  // ---------------------------------------------------------------- límite de opciones
  document.querySelectorAll('[data-checkbox-group][data-max]').forEach(function (group) {
    var max = Number(group.dataset.max);
    group.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
      cb.addEventListener('change', function () {
        if (group.querySelectorAll('input[type="checkbox"]:checked').length > max) { this.checked = false; shake(group); }
      });
    });
  });

  // ---------------------------------------------------------------- bloques condicionales
  function valorDe(nombre) {
    var els = form.querySelectorAll('[name="' + nombre + '"], [name="' + nombre + '[]"]');
    var lista = [];
    els.forEach(function (el) {
      if (el.type === 'checkbox' || el.type === 'radio') { if (el.checked) lista.push(el.value); }
      else if (el.value !== '') lista.push(el.value);
    });
    return lista;
  }
  function cumple(cond) {
    if (!cond || !cond.campo) return true;
    var lista = valorDe(cond.campo), esperado = String(cond.valor == null ? '' : cond.valor);
    switch (cond.operador || '==') {
      case '==': return lista.indexOf(esperado) >= 0;
      case '!=': return lista.indexOf(esperado) < 0;
      case 'vacio': return lista.length === 0;
      case 'no_vacio': return lista.length > 0;
      case 'contiene': return lista.some(function (x) { return x.toLowerCase().indexOf(esperado.toLowerCase()) >= 0; });
      default: return true;
    }
  }
  var condicionales = Array.prototype.map.call(document.querySelectorAll('.conditional-block'), function (b) { return { el: b, cond: JSON.parse(b.dataset.condicion || '{}') }; });
  function evaluarCondicionales() {
    condicionales.forEach(function (c) {
      var visible = cumple(c.cond);
      c.el.classList.toggle('is-hidden', !visible);
      if (!visible && !restaurando) {
        c.el.querySelectorAll('input, select, textarea').forEach(function (el) {
          if (el.type === 'checkbox' || el.type === 'radio') el.checked = false; else if (el.type !== 'file') el.value = '';
        });
      }
    });
    document.querySelectorAll('.form-step').forEach(function (s) { if (s.actualizarBoton) s.actualizarBoton(); });
  }
  if (condicionales.length) { form.addEventListener('change', evaluarCondicionales); evaluarCondicionales(); }

  // ---------------------------------------------------------------- ranking sin valores repetidos
  document.querySelectorAll('[data-ranking]').forEach(function (r) {
    var selects = Array.prototype.slice.call(r.querySelectorAll('select'));
    function sync() {
      var usados = selects.map(function (s) { return s.value; }).filter(Boolean);
      selects.forEach(function (s) {
        Array.prototype.forEach.call(s.options, function (o) { if (o.value) o.hidden = usados.indexOf(o.value) >= 0 && o.value !== s.value; });
      });
    }
    selects.forEach(function (s) { s.addEventListener('change', sync); });
    sync();
  });

  // ---------------------------------------------------------------- Sí/No: pasa el foco a la siguiente pregunta
  document.querySelectorAll('[data-si-no] input[type="radio"]').forEach(function (radio) {
    radio.addEventListener('change', function () {
      if (restaurando || !radio.checked) return;
      var pregunta = radio.closest('.row'); if (!pregunta) return;
      var sig = pregunta.nextElementSibling;
      while (sig && !sig.matches('.row')) sig = sig.nextElementSibling;
      var destino = sig && sig.querySelector('input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled])');
      if (destino) setTimeout(function () { destino.focus({ preventScroll: false }); }, 150);
    });
  });

  // ---------------------------------------------------------------- entidades públicas
  var entidades = null;
  function cargarEntidades() {
    if (entidades) return Promise.resolve(entidades);
    return fetch('/static/datos/entidades.json').then(function (r) { return r.json(); }).then(function (d) { entidades = d; return d; }).catch(function () { return []; });
  }
  document.querySelectorAll('input[data-entidad]').forEach(function (input) {
    var caja = input.parentElement.querySelector('.entidad-sugerencias');
    input.addEventListener('focus', cargarEntidades);
    input.addEventListener('input', function () {
      var term = input.value.trim().toLowerCase();
      caja.innerHTML = '';
      if (term.length < 2) { caja.hidden = true; return; }
      cargarEntidades().then(function (lista) {
        var coincidencias = lista.filter(function (e) { return e[1].toLowerCase().indexOf(term) >= 0 || String(e[0]).indexOf(term) >= 0; }).slice(0, 40);
        if (!coincidencias.length) { caja.hidden = true; return; }
        coincidencias.forEach(function (e) {
          var b = document.createElement('button');
          b.type = 'button'; b.className = 'list-group-item list-group-item-action';
          b.textContent = e[1] + ' (' + e[0] + ')';
          b.addEventListener('mousedown', function (ev) { ev.preventDefault(); input.value = e[1]; caja.innerHTML = ''; caja.hidden = true; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })); });
          caja.appendChild(b);
        });
        caja.hidden = false;
      });
    });
    input.addEventListener('blur', function () { setTimeout(function () { caja.hidden = true; }, 150); });
  });

  // ---------------------------------------------------------------- departamento y municipio
  var deptos = document.querySelectorAll('select[data-departamento]');
  if (deptos.length) {
    fetch('/static/datos/colombia.json').then(function (r) { return r.json(); }).then(function (mapa) {
      deptos.forEach(function (sel) {
        Object.keys(mapa).forEach(function (d) { var o = document.createElement('option'); o.value = d; o.textContent = d; sel.appendChild(o); });
        var munis = form.querySelectorAll('select[data-municipio="' + sel.name + '"]');
        function llenar() {
          munis.forEach(function (m) {
            var actual = m.dataset.valor || m.value;
            m.innerHTML = '';
            if (sel.value && mapa[sel.value]) {
              m.disabled = false;
              m.appendChild(new Option('Seleccione...', ''));
              mapa[sel.value].forEach(function (x) { m.appendChild(new Option(x, x)); });
              if (actual) m.value = actual;
              m.dataset.valor = '';
            } else { m.disabled = true; m.appendChild(new Option('Seleccione primero un departamento...', '')); }
            m.dispatchEvent(new Event('change', { bubbles: true }));
          });
        }
        sel.addEventListener('change', llenar);
        if (sel.dataset.valor) { sel.value = sel.dataset.valor; sel.dataset.valor = ''; }
        llenar();
      });
    }).catch(function () {});
  }

  // ---------------------------------------------------------------- borrador local
  function serializar() {
    var campos = {};
    form.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (!el.name || el.type === 'file' || el.type === 'hidden') return;
      if (el.type === 'checkbox') {
        if (el.name.slice(-2) === '[]') { if (!campos[el.name]) campos[el.name] = []; if (el.checked) campos[el.name].push(el.value); }
        else campos[el.name] = el.checked;
      } else if (el.type === 'radio') { if (el.checked) campos[el.name] = el.value; }
      else campos[el.name] = el.value;
    });
    if (terminos) campos._terminos = terminos.checked;
    return campos;
  }
  function guardarBorrador() { try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ campos: serializar(), paso: currentStep, en: Date.now() })); } catch (e) {} }
  function borrarBorrador() { try { localStorage.removeItem(DRAFT_KEY); } catch (e) {} }
  function restaurarBorrador() {
    var carga;
    try { var crudo = localStorage.getItem(DRAFT_KEY); if (!crudo) return; carga = JSON.parse(crudo); } catch (e) { return; }
    if (!carga || !carga.campos) return;
    restaurando = true;
    var campos = carga.campos;
    if (campos._terminos && terminos) terminos.checked = true;
    Object.keys(campos).forEach(function (nombre) {
      if (nombre === '_terminos') return;
      var valor = campos[nombre];
      form.querySelectorAll('[name="' + nombre + '"]').forEach(function (el) {
        if (el.type === 'checkbox') el.checked = Array.isArray(valor) ? valor.indexOf(el.value) >= 0 : !!valor;
        else if (el.type === 'radio') el.checked = el.value === valor;
        else if (el.dataset.departamento != null || el.dataset.municipio != null) el.dataset.valor = valor;
        else el.value = valor;
      });
    });
    form.querySelectorAll('input, select, textarea').forEach(function (el) { el.dispatchEvent(new Event('change', { bubbles: true })); });
    restaurando = false;
    actualizarVisibilidad();
    if (carga.paso >= 1 && carga.paso <= TOTAL) goToStep(carga.paso, { silent: true });
  }
  form.addEventListener('input', guardarBorrador);
  form.addEventListener('change', guardarBorrador);
  if (terminos) terminos.addEventListener('change', guardarBorrador);
  restaurarBorrador();

  // ---------------------------------------------------------------- envío
  var btnSubmit = document.getElementById('btn-submit');
  var ultimoPaso = document.querySelector('.form-step[data-step="' + TOTAL + '"]');
  if (btnSubmit) btnSubmit.addEventListener('click', function (e) {
    var inv = validarPaso(ultimoPaso) || (terminos && !terminos.checkValidity() ? terminos : null);
    var g = !inv && grupoInvalido(ultimoPaso);
    if (inv || g) {
      e.preventDefault(); shake(btnSubmit);
      var el = inv || g;
      (el.closest('.pregunta') || el).scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (inv) inv.reportValidity(); else shake(g);
    }
  });
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    if (validarPaso(ultimoPaso) || grupoInvalido(ultimoPaso)) return;
    if (!(await revisarDuplicados(form))) return;
    btnSubmit.disabled = true;
    mostrarAviso('', 'Enviando respuestas...', 'Por favor espere mientras procesamos la información.', { cargando: true });
    try {
      var res = await fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } });
      var datos = null;
      try { datos = await res.json(); } catch (err) { datos = null; }
      if (res.ok && datos && datos.ok) {
        cerrarAviso(); borrarBorrador();
        form.hidden = true; if (presentacion) presentacion.hidden = true;
        var cierre = document.getElementById('cierre'); cierre.hidden = false;
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      var mensaje = datos && datos.errores ? datos.errores.map(function (x) { return '• ' + x.mensaje; }).join('\n') : (datos && datos.mensaje) || 'No fue posible registrar las respuestas. Intente de nuevo en unos minutos.';
      mostrarAviso('⚠️', datos && datos.titulo ? datos.titulo : 'Revise las respuestas', mensaje);
      if (datos && datos.errores && datos.errores.length) {
        var primero = form.querySelector('[data-pregunta="' + datos.errores[0].campo + '"]');
        if (primero) { var paso = primero.closest('.form-step'); if (paso) goToStep(Number(paso.dataset.step), { silent: true }); primero.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      }
    } catch (err) {
      mostrarAviso('⚠️', 'Sin conexión', 'No fue posible contactar el servidor. Sus respuestas siguen guardadas en este navegador; intente de nuevo.');
    } finally {
      btnSubmit.disabled = false;
    }
  });
})();
