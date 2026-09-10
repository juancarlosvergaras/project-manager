// Pequeñas ayudas de las páginas de administración de cuestionarios: confirmaciones, copiar enlaces y desplegar detalles.
(function () {
  'use strict';
  document.addEventListener('submit', function (e) {
    var f = e.target.closest('form[data-confirmar]');
    if (f && !confirm(f.dataset.confirmar)) e.preventDefault();
  });
  document.addEventListener('click', function (e) {
    var copiar = e.target.closest('[data-copiar]');
    if (copiar) {
      e.preventDefault();
      var texto = copiar.dataset.copiar;
      var listo = function () { var t = copiar.textContent; copiar.textContent = 'Copiado'; setTimeout(function () { copiar.textContent = t; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(texto).then(listo); else { window.prompt('Copie el enlace:', texto); }
      return;
    }
    var det = e.target.closest('[data-detalles]');
    if (det) {
      e.preventDefault();
      var fila = document.getElementById(det.dataset.detalles);
      if (fila) { fila.hidden = !fila.hidden; det.textContent = fila.hidden ? 'Ver' : 'Ocultar'; }
    }
  });
  var lista = document.getElementById('lista-destinatarios');
  var contador = document.getElementById('contador-destinatarios');
  if (lista && contador) {
    var contar = function () {
      var n = lista.value.split('\n').filter(function (l) { return /@/.test(l); }).length;
      contador.textContent = n ? n + ' destinatario' + (n === 1 ? '' : 's') + ' detectado' + (n === 1 ? '' : 's') : '';
    };
    lista.addEventListener('input', contar); contar();
  }
})();
