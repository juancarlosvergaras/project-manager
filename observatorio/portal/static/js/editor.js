// Editor visual de cuestionarios. Trabaja sobre la definición JSON en memoria y la guarda por fetch.
// Los datos iniciales llegan en <script type="application/json" id="editor-datos">.
(function () {
  'use strict';
  var datos = JSON.parse(document.getElementById('editor-datos').textContent);
  var def = datos.definicion;
  var TIPOS = datos.tipos;
  var raiz = document.getElementById('editor');
  var pestana = 'contenido';
  var abiertos = {};
  var mensaje = null;

  // ---------------------------------------------------------------- utilidades de DOM
  function h(tag, attrs) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (k === 'class') el.className = v;
      else if (k === 'html') el.innerHTML = v;
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
      else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'hidden') { if (v) el[k] = true; }
      else if (v != null) el.setAttribute(k, v);
    });
    for (var i = 2; i < arguments.length; i++) agregar(el, arguments[i]);
    return el;
  }
  function agregar(el, hijo) {
    if (hijo == null || hijo === false) return;
    if (Array.isArray(hijo)) { hijo.forEach(function (x) { agregar(el, x); }); return; }
    el.appendChild(typeof hijo === 'string' ? document.createTextNode(hijo) : hijo);
  }
  function slug(t) { return String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40); }

  // Campo de edición enlazado a obj[clave]. tipo: text | textarea | number | check | select | lineas | opciones | pares
  function campo(obj, clave, etiqueta, tipo, extra) {
    extra = extra || {};
    var id = 'f' + Math.random().toString(36).slice(2, 8);
    var input;
    var valor = obj[clave];
    if (tipo === 'check') {
      input = h('input', { class: 'form-check-input', type: 'checkbox', id: id, checked: !!valor, onchange: function () { obj[clave] = input.checked; if (extra.alCambiar) extra.alCambiar(); } });
      return h('div', { class: 'form-check mb-2' }, input, h('label', { class: 'form-check-label', for: id }, etiqueta));
    }
    if (tipo === 'select') {
      input = h('select', { class: 'form-select form-select-sm', id: id, onchange: function () { obj[clave] = input.value; if (extra.alCambiar) extra.alCambiar(); } },
        (extra.opciones || []).map(function (o) { var v = typeof o === 'object' ? o.valor : o, t = typeof o === 'object' ? o.texto : o; return h('option', { value: v, selected: String(valor == null ? '' : valor) === String(v) }, t); }));
    } else if (tipo === 'textarea' || tipo === 'lineas' || tipo === 'opciones' || tipo === 'pares') {
      var texto = valor;
      if (tipo === 'lineas') texto = (valor || []).join('\n\n');
      if (tipo === 'opciones') texto = (valor || []).map(function (o) { return typeof o === 'object' ? o.valor + ' | ' + o.texto : o; }).join('\n');
      if (tipo === 'pares') texto = (valor || []).map(function (o) { return extra.claves.map(function (k) { return o[k] == null ? '' : o[k]; }).join(' | '); }).join('\n');
      input = h('textarea', { class: 'form-control form-control-sm', id: id, rows: extra.filas || (tipo === 'textarea' ? 3 : 5), oninput: function () {
        var t = input.value;
        if (tipo === 'textarea') obj[clave] = t;
        else if (tipo === 'lineas') obj[clave] = t.split(/\n\s*\n/).map(function (x) { return x.trim(); }).filter(Boolean);
        else if (tipo === 'opciones') obj[clave] = t.split('\n').map(function (x) { return x.trim(); }).filter(Boolean).map(function (x) { var p = x.split('|'); return p.length > 1 ? { valor: p[0].trim(), texto: p.slice(1).join('|').trim() } : x; });
        else if (tipo === 'pares') obj[clave] = t.split('\n').map(function (x) { return x.trim(); }).filter(Boolean).map(function (x) { var p = x.split('|').map(function (y) { return y.trim(); }); var o = {}; extra.claves.forEach(function (k, i) { o[k] = extra.numericas && extra.numericas.indexOf(k) >= 0 ? Number(p[i]) : (p[i] || ''); }); return o; });
        if (extra.alCambiar) extra.alCambiar();
      } });
      input.value = texto == null ? '' : texto;
    } else {
      input = h('input', { class: 'form-control form-control-sm', id: id, type: tipo === 'number' ? 'number' : 'text', placeholder: extra.placeholder || '', oninput: function () {
        if (tipo === 'number') obj[clave] = input.value === '' ? undefined : Number(input.value); else obj[clave] = input.value;
        if (extra.alCambiar) extra.alCambiar();
      }, onblur: extra.alSalir });
      input.value = valor == null ? '' : valor;
    }
    return h('div', { class: 'mb-2 ' + (extra.clase || '') }, h('label', { class: 'form-label small fw-semibold mb-1', for: id }, etiqueta), input, extra.ayuda ? h('div', { class: 'form-text' }, extra.ayuda) : null);
  }

  // ---------------------------------------------------------------- recorrido de la definición
  function todosLosCampos() {
    var out = [];
    function visitar(bloques) { (bloques || []).forEach(function (b) { if (TIPOS[b.tipo] && TIPOS[b.tipo].responde && b.nombre) out.push(b); if (b.tipo === 'condicional') visitar(b.bloques); }); }
    (def.pasos || []).forEach(function (p) { visitar(p.bloques); });
    return out;
  }
  function nombreUnico(base) {
    var usados = todosLosCampos().map(function (c) { return c.nombre; });
    var n = base || 'pregunta', i = 2;
    while (usados.indexOf(n) >= 0) n = (base || 'pregunta') + '_' + i++;
    return n;
  }
  function bloqueNuevo(tipo) {
    var b = { tipo: tipo };
    if (tipo === 'seccion') { b.numero = ''; b.titulo = 'Nueva sección'; }
    else if (tipo === 'texto') b.texto = 'Texto explicativo.';
    else if (tipo === 'leyenda') { b.titulo = 'Escala de evaluación'; b.descripcion = 'Cada pregunta se valora de 1 a 5.'; b.items = [1, 2, 3, 4, 5].map(function (n) { return { nivel: n, etiqueta: 'Nivel ' + n, texto: ['Inicial', 'Gestionado', 'Definido', 'Avanzado', 'Optimizado'][n - 1] }; }); }
    else if (tipo === 'condicional') { b.condicion = { campo: '', operador: '==', valor: '' }; b.bloques = []; }
    else {
      b.nombre = nombreUnico(tipo === 'texto_corto' ? 'campo' : tipo); b.etiqueta = 'Nueva pregunta'; b.requerido = true;
      if (tipo === 'seleccion' || tipo === 'unica' || tipo === 'multiple') b.opciones = ['Opción 1', 'Opción 2', 'Opción 3'];
      if (tipo === 'escala') { b.min = 1; b.max = 5; b.extremos = ['Totalmente en desacuerdo', 'Totalmente de acuerdo']; }
      if (tipo === 'rubrica') b.niveles = [1, 2, 3, 4, 5].map(function (n) { return { valor: String(n), texto: ['Inicial', 'Gestionado', 'Definido', 'Avanzado', 'Optimizado'][n - 1] }; });
      if (tipo === 'ranking') { b.items = [{ nombre: 'item_1', texto: 'Elemento 1' }, { nombre: 'item_2', texto: 'Elemento 2' }, { nombre: 'item_3', texto: 'Elemento 3' }]; b.min = 1; b.max = 3; }
      if (tipo === 'archivo') { b.requerido = false; b.max_mb = 10; b.acepta = '.pdf,.doc,.docx,.xls,.xlsx,.csv,image/*'; }
      if (tipo === 'municipio') b.depende_de = 'departamento';
      if (tipo === 'texto_corto') b.formato = 'text';
    }
    return b;
  }

  // ---------------------------------------------------------------- barra superior y pestañas
  function barra() {
    return h('div', { class: 'editor-barra' },
      h('div', { class: 'flex-grow-1' }, campo(def, 'titulo', 'Título del cuestionario', 'text', { clase: 'mb-0' })),
      h('div', { class: 'd-flex gap-2 align-items-end flex-wrap' },
        h('button', { class: 'btn btn-primary', type: 'button', onclick: function () { guardar(false); } }, 'Guardar'),
        h('button', { class: 'btn btn-outline-primary', type: 'button', onclick: function () { guardar(true); } }, 'Guardar y ver'),
        h('a', { class: 'btn btn-outline-secondary', href: datos.listaUrl }, 'Volver a la lista')),
      mensaje ? h('div', { class: 'w-100 mt-2 alert py-2 mb-0 ' + (mensaje.ok ? 'alert-success' : 'alert-danger'), html: mensaje.html }) : null);
  }
  function pestanas() {
    var lista = [['contenido', 'Pasos y preguntas'], ['presentacion', 'Presentación y políticas'], ['calculo', 'Identificación, cálculo y tablero'], ['json', 'JSON']];
    return h('ul', { class: 'nav nav-tabs mintic-tabs mb-3' }, lista.map(function (p) {
      return h('li', { class: 'nav-item' }, h('button', { class: 'nav-link' + (pestana === p[0] ? ' active' : ''), type: 'button', onclick: function () { pestana = p[0]; render(); } }, p[1]));
    }));
  }

  // ---------------------------------------------------------------- pestaña de contenido
  function resumenBloque(b) {
    if (b.tipo === 'seccion') return (b.numero ? b.numero + '. ' : '') + (b.titulo || '');
    if (b.tipo === 'texto') return (b.texto || '').slice(0, 90);
    if (b.tipo === 'leyenda') return b.titulo || 'Leyenda';
    if (b.tipo === 'condicional') return 'Se muestra si «' + (b.condicion && b.condicion.campo || '?') + '» ' + (b.condicion && b.condicion.operador || '==') + ' «' + (b.condicion && b.condicion.valor || '') + '»';
    return (b.numero != null && b.numero !== '' ? b.numero + '. ' : '') + (b.etiqueta || b.nombre || '');
  }
  function listaBloques(bloques, ruta) {
    var cont = h('div', { class: 'bloques' });
    bloques.forEach(function (b, j) {
      var clave = ruta + '/' + j;
      var abierto = !!abiertos[clave];
      var fila = h('div', { class: 'bloque' + (abierto ? ' abierto' : '') + (TIPOS[b.tipo] && TIPOS[b.tipo].responde ? '' : ' bloque-estructural') },
        h('div', { class: 'bloque-cab' },
          h('span', { class: 'badge bg-light text-primary border me-2' }, TIPOS[b.tipo] ? TIPOS[b.tipo].nombre : b.tipo),
          h('span', { class: 'bloque-resumen flex-grow-1', onclick: function () { abiertos[clave] = !abierto; render(); } }, resumenBloque(b) || '(sin texto)'),
          b.requerido ? h('span', { class: 'text-danger me-2', title: 'Obligatoria' }, '*') : null,
          b.dimension ? h('span', { class: 'badge bg-secondary me-2' }, b.dimension) : null,
          h('div', { class: 'btn-group btn-group-sm' },
            h('button', { class: 'btn btn-outline-secondary', type: 'button', title: 'Subir', disabled: j === 0, onclick: function () { mover(bloques, j, -1); } }, '↑'),
            h('button', { class: 'btn btn-outline-secondary', type: 'button', title: 'Bajar', disabled: j === bloques.length - 1, onclick: function () { mover(bloques, j, 1); } }, '↓'),
            h('button', { class: 'btn btn-outline-secondary', type: 'button', title: 'Duplicar', onclick: function () { var c = JSON.parse(JSON.stringify(b)); if (c.nombre) c.nombre = nombreUnico(c.nombre); bloques.splice(j + 1, 0, c); render(); } }, '⧉'),
            h('button', { class: 'btn btn-outline-primary', type: 'button', onclick: function () { abiertos[clave] = !abierto; render(); } }, abierto ? 'Cerrar' : 'Editar'),
            h('button', { class: 'btn btn-outline-danger', type: 'button', title: 'Quitar', onclick: function () { if (confirm('¿Quitar este bloque?')) { bloques.splice(j, 1); render(); } } }, '✕'))),
        abierto ? editorBloque(b, bloques, j, clave) : null);
      cont.appendChild(fila);
    });
    cont.appendChild(agregarBloque(bloques));
    return cont;
  }
  function mover(lista, i, delta) { var j = i + delta; if (j < 0 || j >= lista.length) return; var t = lista[i]; lista[i] = lista[j]; lista[j] = t; render(); }
  function agregarBloque(bloques) {
    var sel = h('select', { class: 'form-select form-select-sm', style: 'max-width:320px' }, Object.keys(TIPOS).map(function (k) { return h('option', { value: k }, TIPOS[k].nombre); }));
    sel.value = 'unica';
    return h('div', { class: 'd-flex gap-2 align-items-center mt-2 agregar-bloque' }, h('span', { class: 'small text-muted' }, 'Añadir:'), sel,
      h('button', { class: 'btn btn-sm btn-primary', type: 'button', onclick: function () { bloques.push(bloqueNuevo(sel.value)); render(); } }, '+ Añadir bloque'));
  }

  function editorBloque(b, bloques, j, clave) {
    var cuerpo = h('div', { class: 'bloque-cuerpo' });
    var camposDisponibles = todosLosCampos().map(function (c) { return { valor: c.nombre, texto: c.nombre + ' — ' + (c.etiqueta || '').slice(0, 50) }; });
    var tipoSel = campo(b, 'tipo', 'Tipo de bloque', 'select', { opciones: Object.keys(TIPOS).map(function (k) { return { valor: k, texto: TIPOS[k].nombre }; }), alCambiar: function () {
      var nuevo = bloqueNuevo(b.tipo);
      Object.keys(nuevo).forEach(function (k) { if (b[k] == null) b[k] = nuevo[k]; });
      if (TIPOS[b.tipo] && TIPOS[b.tipo].responde && !b.nombre) b.nombre = nombreUnico(slug(b.etiqueta));
      render();
    } });
    cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-4' }, tipoSel)));
    if (b.tipo === 'seccion') {
      cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-2' }, campo(b, 'numero', 'Número', 'text')), h('div', { class: 'col-md-2' }, campo(b, 'icono', 'Icono (emoji)', 'text')), h('div', { class: 'col-md-8' }, campo(b, 'titulo', 'Título de la sección', 'text'))));
    } else if (b.tipo === 'texto') {
      cuerpo.appendChild(campo(b, 'texto', 'Texto (admite **negritas**)', 'textarea'));
    } else if (b.tipo === 'leyenda') {
      cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-4' }, campo(b, 'titulo', 'Título', 'text')), h('div', { class: 'col-md-8' }, campo(b, 'descripcion', 'Descripción', 'text'))));
      cuerpo.appendChild(campo(b, 'items', 'Niveles, uno por línea: nivel | etiqueta | texto', 'pares', { claves: ['nivel', 'etiqueta', 'texto'], numericas: ['nivel'] }));
    } else if (b.tipo === 'condicional') {
      if (!b.condicion) b.condicion = {};
      cuerpo.appendChild(h('div', { class: 'row g-2' },
        h('div', { class: 'col-md-5' }, campo(b.condicion, 'campo', 'Se muestra según la pregunta', 'select', { opciones: [{ valor: '', texto: '(elija una pregunta)' }].concat(camposDisponibles) })),
        h('div', { class: 'col-md-3' }, campo(b.condicion, 'operador', 'Condición', 'select', { opciones: [{ valor: '==', texto: 'es igual a' }, { valor: '!=', texto: 'es distinto de' }, { valor: 'contiene', texto: 'contiene' }, { valor: 'no_vacio', texto: 'tiene respuesta' }, { valor: 'vacio', texto: 'está vacía' }] })),
        h('div', { class: 'col-md-4' }, campo(b.condicion, 'valor', 'Valor', 'text', { ayuda: 'Escriba el valor tal como aparece en las opciones.' }))));
      cuerpo.appendChild(h('div', { class: 'ps-3 border-start border-2 mt-2' }, h('div', { class: 'small fw-semibold mb-1' }, 'Bloques dentro de la condición'), listaBloques(b.bloques = b.bloques || [], clave)));
    } else {
      cuerpo.appendChild(h('div', { class: 'row g-2' },
        h('div', { class: 'col-md-1' }, campo(b, 'numero', 'N.º', 'text')),
        h('div', { class: 'col-md-7' }, campo(b, 'etiqueta', 'Pregunta o etiqueta', 'text', { alSalir: function () { if (!b.nombre || /^(pregunta|campo|unica|seleccion|multiple|escala|rubrica|si_no|parrafo|numero|fecha)(_\d+)?$/.test(b.nombre)) { b.nombre = nombreUnico(slug(b.etiqueta)); render(); } } })),
        h('div', { class: 'col-md-4' }, campo(b, 'nombre', 'Identificador (columna en los datos)', 'text', { ayuda: 'Letras, números y guion bajo.' }))));
      cuerpo.appendChild(h('div', { class: 'row g-2' },
        h('div', { class: 'col-md-8' }, campo(b, 'ayuda', 'Texto de ayuda (opcional)', 'text')),
        h('div', { class: 'col-md-2' }, campo(b, 'dimension', 'Dimensión (cálculo)', 'text', { placeholder: 'ej. DG' })),
        h('div', { class: 'col-md-2 pt-4' }, campo(b, 'requerido', 'Obligatoria', 'check'))));
      if (b.tipo === 'seleccion' || b.tipo === 'unica' || b.tipo === 'multiple') {
        if (!b.otro) b.otro = null;
        var otro = b.otro || { valor: 'Otros', etiqueta: 'Especifique' };
        var conOtro = { activo: !!b.otro };
        cuerpo.appendChild(h('div', { class: 'row g-2' },
          h('div', { class: 'col-md-6' }, campo(b, 'opciones', 'Opciones, una por línea (o "valor | texto")', 'opciones', { filas: 6 })),
          h('div', { class: 'col-md-6' },
            campo(conOtro, 'activo', 'Con campo «Otro, ¿cuál?»', 'check', { alCambiar: function () { b.otro = conOtro.activo ? otro : null; render(); } }),
            b.otro ? h('div', { class: 'row g-2' }, h('div', { class: 'col-6' }, campo(b.otro, 'valor', 'Se abre al elegir la opción', 'text')), h('div', { class: 'col-6' }, campo(b.otro, 'etiqueta', 'Texto del campo', 'text'))) : null,
            b.tipo === 'multiple' ? h('div', { class: 'row g-2' }, h('div', { class: 'col-6' }, campo(b, 'max', 'Máximo de opciones', 'number')), h('div', { class: 'col-6 pt-4' }, campo(b, 'en_linea', 'Opciones en línea', 'check'))) : null)));
      } else if (b.tipo === 'escala') {
        if (!b.extremos) b.extremos = ['', ''];
        cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-2' }, campo(b, 'min', 'Desde', 'number')), h('div', { class: 'col-md-2' }, campo(b, 'max', 'Hasta', 'number')), h('div', { class: 'col-md-4' }, campo(b.extremos, 0, 'Texto del extremo inferior', 'text')), h('div', { class: 'col-md-4' }, campo(b.extremos, 1, 'Texto del extremo superior', 'text'))));
      } else if (b.tipo === 'rubrica') {
        cuerpo.appendChild(campo(b, 'niveles', 'Niveles, uno por línea: valor | texto', 'pares', { claves: ['valor', 'texto'] }));
      } else if (b.tipo === 'ranking') {
        cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-8' }, campo(b, 'items', 'Elementos a ordenar, uno por línea: identificador | texto', 'pares', { claves: ['nombre', 'texto'] })), h('div', { class: 'col-md-2' }, campo(b, 'min', 'Valor mínimo', 'number')), h('div', { class: 'col-md-2' }, campo(b, 'max', 'Valor máximo', 'number'))));
      } else if (b.tipo === 'archivo') {
        cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-8' }, campo(b, 'acepta', 'Tipos aceptados (atributo accept)', 'text')), h('div', { class: 'col-md-4' }, campo(b, 'max_mb', 'Tamaño máximo (MB)', 'number'))));
      } else if (b.tipo === 'texto_corto') {
        cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-4' }, campo(b, 'formato', 'Formato', 'select', { opciones: [{ valor: 'text', texto: 'Texto' }, { valor: 'email', texto: 'Correo electrónico' }, { valor: 'url', texto: 'Dirección web' }, { valor: 'tel', texto: 'Teléfono' }] })), h('div', { class: 'col-md-8' }, campo(b, 'placeholder', 'Texto de ejemplo dentro del campo', 'text'))));
      } else if (b.tipo === 'parrafo') {
        cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-3' }, campo(b, 'filas', 'Líneas visibles', 'number')), h('div', { class: 'col-md-9' }, campo(b, 'placeholder', 'Texto de ejemplo dentro del campo', 'text'))));
      } else if (b.tipo === 'numero') {
        cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-3' }, campo(b, 'min', 'Mínimo', 'number')), h('div', { class: 'col-md-3' }, campo(b, 'max', 'Máximo', 'number')), h('div', { class: 'col-md-3' }, campo(b, 'peso', 'Peso en el cálculo', 'number'))));
      } else if (b.tipo === 'municipio') {
        cuerpo.appendChild(campo(b, 'depende_de', 'Identificador de la pregunta de departamento', 'text'));
      }
      if (TIPOS[b.tipo] && TIPOS[b.tipo].numerica && b.tipo !== 'numero') cuerpo.appendChild(h('div', { class: 'row g-2' }, h('div', { class: 'col-md-3' }, campo(b, 'peso', 'Peso en el cálculo (1 por defecto)', 'number'))));
    }
    return cuerpo;
  }

  function contenido() {
    var cont = h('div');
    def.pasos.forEach(function (p, i) {
      cont.appendChild(h('div', { class: 'card mb-3 paso' },
        h('div', { class: 'card-header d-flex align-items-center gap-2' },
          h('span', { class: 'badge bg-primary' }, 'Paso ' + (i + 1)),
          h('div', { class: 'flex-grow-1' }, campo(p, 'etiqueta', '', 'text', { clase: 'mb-0', placeholder: 'Etiqueta corta del paso' })),
          h('div', { class: 'btn-group btn-group-sm' },
            h('button', { class: 'btn btn-outline-secondary', type: 'button', disabled: i === 0, onclick: function () { mover(def.pasos, i, -1); } }, '↑'),
            h('button', { class: 'btn btn-outline-secondary', type: 'button', disabled: i === def.pasos.length - 1, onclick: function () { mover(def.pasos, i, 1); } }, '↓'),
            h('button', { class: 'btn btn-outline-danger', type: 'button', disabled: def.pasos.length === 1, onclick: function () { if (confirm('¿Quitar este paso con todas sus preguntas?')) { def.pasos.splice(i, 1); render(); } } }, 'Quitar paso'))),
        h('div', { class: 'card-body' }, listaBloques(p.bloques, 'p' + i))));
    });
    cont.appendChild(h('button', { class: 'btn btn-outline-primary', type: 'button', onclick: function () { def.pasos.push({ etiqueta: 'Paso ' + (def.pasos.length + 1), bloques: [{ tipo: 'seccion', numero: String(def.pasos.length + 1), titulo: 'Nueva sección' }] }); render(); } }, '+ Añadir paso'));
    return cont;
  }

  // ---------------------------------------------------------------- presentación y políticas
  function presentacion() {
    var p = def.politicas;
    return h('div', { class: 'row g-3' },
      h('div', { class: 'col-lg-6' }, h('div', { class: 'card h-100' }, h('div', { class: 'card-header' }, 'Encabezado y cierre'), h('div', { class: 'card-body' },
        campo(def, 'subtitulo', 'Subtítulo (bajo el título)', 'text'),
        campo(def, 'intro', 'Introducción. Separe los párrafos con una línea en blanco; admite **negritas**.', 'lineas', { filas: 10 }),
        campo(def.progreso, 'barra', 'Mostrar barra de progreso «Paso n de N»', 'check'),
        h('hr'),
        campo(def.cierre, 'boton', 'Texto del botón de envío', 'text'),
        campo(def.cierre, 'titulo', 'Título del mensaje de cierre', 'text'),
        campo(def.cierre, 'mensaje', 'Mensaje de cierre', 'textarea')))),
      h('div', { class: 'col-lg-6' }, h('div', { class: 'card h-100' }, h('div', { class: 'card-header' }, 'Políticas de privacidad y tratamiento de datos'), h('div', { class: 'card-body' },
        campo(p, 'mostrar', 'Mostrar las políticas y exigir su aceptación', 'check', { alCambiar: render }),
        p.mostrar ? [
          campo(p, 'posicion', 'Dónde aparecen', 'select', { opciones: [{ valor: 'inicio', texto: 'Al inicio: el formulario se abre al aceptarlas' }, { valor: 'final', texto: 'Al final: se aceptan antes de enviar' }] }),
          campo(p, 'titulo', 'Título', 'text'),
          campo(p, 'textos', 'Textos. Separe los párrafos con una línea en blanco.', 'lineas', { filas: 12 }),
          campo(p, 'etiqueta', 'Texto de la casilla de aceptación', 'text'),
          h('button', { class: 'btn btn-sm btn-outline-secondary', type: 'button', onclick: function () { p.textos = datos.politicasBase.slice(); render(); } }, 'Restaurar los textos institucionales (MinTIC y UdeC)')
        ] : h('p', { class: 'text-muted small mb-0' }, 'El cuestionario se mostrará directamente, sin bloque de políticas ni casilla de aceptación.')))));
  }

  // ---------------------------------------------------------------- identificación, cálculo y tablero
  function calculo() {
    var campos = todosLosCampos();
    var opcionesCampos = [{ valor: '', texto: '(ninguno)' }].concat(campos.map(function (c) { return { valor: c.nombre, texto: c.nombre + ' — ' + (c.etiqueta || '').slice(0, 45) }; }));
    var conOpciones = campos.filter(function (c) { return TIPOS[c.tipo] && (TIPOS[c.tipo].opciones || TIPOS[c.tipo].numerica) || c.tipo === 'departamento' || c.tipo === 'municipio'; });
    if (!def.identificacion) def.identificacion = {};
    if (!def.duplicados) def.duplicados = { campos: [], mensaje: '' };
    if (!def.calculo) def.calculo = { modo: 'promedio', niveles: false, dimensiones: [] };
    if (!def.tablero) def.tablero = { graficos: [], indicadores: [] };
    var dup = { texto: (def.duplicados.campos || []).join('\n') };
    var graf = { texto: (def.tablero.graficos || []).join('\n') };
    return h('div', { class: 'row g-3' },
      h('div', { class: 'col-lg-4' }, h('div', { class: 'card h-100' }, h('div', { class: 'card-header' }, 'Identificación de quien responde'), h('div', { class: 'card-body' },
        h('p', { class: 'small text-muted' }, 'Indique qué preguntas contienen estos datos. Se usan en la tabla de respuestas, en el cuadro de mando y para prellenar los enlaces de campaña.'),
        ['correo', 'nombre', 'entidad', 'documento', 'departamento', 'municipio'].map(function (k) { return campo(def.identificacion, k, k.charAt(0).toUpperCase() + k.slice(1), 'select', { opciones: opcionesCampos }); }),
        h('hr'),
        h('div', { class: 'small fw-semibold mb-1' }, 'Respuestas únicas'),
        h('p', { class: 'small text-muted' }, 'Preguntas cuyo valor no puede repetirse entre respuestas (por ejemplo la entidad o el correo). Una por línea.'),
        h('textarea', { class: 'form-control form-control-sm', rows: 3, oninput: function () { def.duplicados.campos = this.value.split('\n').map(function (x) { return x.trim(); }).filter(Boolean); } }, dup.texto),
        campo(def.duplicados, 'mensaje', 'Mensaje cuando ya existe', 'text')))),
      h('div', { class: 'col-lg-4' }, h('div', { class: 'card h-100' }, h('div', { class: 'card-header' }, 'Cálculo de puntajes'), h('div', { class: 'card-body' },
        h('p', { class: 'small text-muted' }, 'Las preguntas de escala, rúbrica, Sí/No y número con «dimensión» se agrupan y se calcula la suma o el promedio por dimensión y el total.'),
        campo(def.calculo, 'modo', 'Modo', 'select', { opciones: [{ valor: 'promedio', texto: 'Promedio por dimensión' }, { valor: 'suma', texto: 'Suma por dimensión' }] }),
        campo(def.calculo, 'niveles', 'Traducir el promedio a nivel de madurez (Inicial a Optimizado, escala 1 a 5)', 'check'),
        campo(def.calculo, 'dimensiones', 'Dimensiones, una por línea: clave | nombre | descripción', 'pares', { claves: ['clave', 'nombre', 'descripcion'], filas: 8 })))),
      h('div', { class: 'col-lg-4' }, h('div', { class: 'card h-100' }, h('div', { class: 'card-header' }, 'Cuadro de resultados'), h('div', { class: 'card-body' },
        h('div', { class: 'small fw-semibold mb-1' }, 'Gráficos de distribución'),
        h('p', { class: 'small text-muted' }, 'Identificadores de las preguntas cerradas que se grafican, uno por línea. Disponibles: ' + conOpciones.map(function (c) { return c.nombre; }).join(', ')),
        h('textarea', { class: 'form-control form-control-sm mb-2', rows: 4, oninput: function () { def.tablero.graficos = this.value.split('\n').map(function (x) { return x.trim(); }).filter(Boolean); } }, graf.texto),
        campo(def.tablero, 'indicadores', 'Indicadores de conteo, uno por línea: nombre | pregunta | valores a contar separados por coma', 'pares', { claves: ['nombre', 'campo', 'contar_texto'], filas: 5, alCambiar: function () { def.tablero.indicadores.forEach(function (i) { i.contar = String(i.contar_texto || '').split(',').map(function (x) { return x.trim(); }).filter(Boolean); }); } })))));
  }

  // ---------------------------------------------------------------- JSON
  function json() {
    var area = h('textarea', { class: 'form-control font-monospace', rows: 30 });
    area.value = JSON.stringify(def, null, 2);
    return h('div', null,
      h('p', { class: 'small text-muted' }, 'Definición completa del cuestionario. Puede copiarla, guardarla o pegar otra y aplicarla.'),
      area,
      h('div', { class: 'mt-2 d-flex gap-2' },
        h('button', { class: 'btn btn-outline-primary', type: 'button', onclick: function () { try { def = JSON.parse(area.value); datos.definicion = def; mensaje = { ok: true, html: 'JSON aplicado. Recuerde guardar.' }; render(); } catch (e) { mensaje = { ok: false, html: 'El JSON no es válido: ' + e.message }; render(); } } }, 'Aplicar JSON'),
        h('button', { class: 'btn btn-outline-secondary', type: 'button', onclick: function () { navigator.clipboard.writeText(area.value); } }, 'Copiar')));
  }

  // ---------------------------------------------------------------- guardar
  function guardar(verDespues) {
    // Las dimensiones de tablero.indicadores guardan también su forma de texto; se limpia antes de enviar.
    (def.tablero && def.tablero.indicadores || []).forEach(function (i) { if (i.contar_texto != null) { i.contar = String(i.contar_texto).split(',').map(function (x) { return x.trim(); }).filter(Boolean); delete i.contar_texto; } });
    fetch(datos.guardarUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ _csrf: datos.csrf, definicion: def }) })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        if (!r.ok) { mensaje = { ok: false, html: '<strong>No se guardó.</strong><br>' + (r.problemas || [r.mensaje || 'Error']).map(function (x) { return '• ' + x; }).join('<br>') }; render(); return; }
        mensaje = { ok: true, html: 'Guardado (versión ' + r.version + ').' };
        if (!datos.id) { window.location.href = r.editarUrl + (verDespues ? '?ver=1' : ''); return; }
        render();
        if (verDespues) window.open(datos.vistaPreviaUrl, '_blank');
      })
      .catch(function (e) { mensaje = { ok: false, html: 'No fue posible guardar: ' + e.message }; render(); });
  }

  function render() {
    var scroll = window.scrollY;
    raiz.innerHTML = '';
    raiz.appendChild(barra());
    raiz.appendChild(pestanas());
    raiz.appendChild(pestana === 'contenido' ? contenido() : pestana === 'presentacion' ? presentacion() : pestana === 'calculo' ? calculo() : json());
    window.scrollTo(0, scroll);
    mensaje = null;
  }
  // Los indicadores del tablero se editan como texto; se prepara esa forma al cargar.
  (def.tablero && def.tablero.indicadores || []).forEach(function (i) { i.contar_texto = (i.contar || []).join(', '); });
  render();
  if (/[?&]ver=1/.test(window.location.search)) window.open(datos.vistaPreviaUrl, '_blank');
  window.addEventListener('beforeunload', function () {});
})();
