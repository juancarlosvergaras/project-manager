// Barra de accesibilidad del portal (misma que la Solucion Automatizada): contraste alto y tamano de texto.
(function () {
  var nivel = 0, contraste = false;
  try { nivel = parseInt(localStorage.getItem('a11y-font') || '0', 10); contraste = localStorage.getItem('a11y-contrast') === '1'; } catch (e) {}
  function aplicar() {
    document.body.classList.remove('font-large', 'font-xlarge', 'high-contrast');
    if (nivel === 1) document.body.classList.add('font-large');
    if (nivel >= 2) document.body.classList.add('font-xlarge');
    if (contraste) document.body.classList.add('high-contrast');
  }
  function guardar() { try { localStorage.setItem('a11y-font', String(nivel)); localStorage.setItem('a11y-contrast', contraste ? '1' : '0'); } catch (e) {} }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-a11y]'); if (!b) return;
    var a = b.getAttribute('data-a11y');
    if (a === 'contraste') contraste = !contraste;
    if (a === 'mas') nivel = Math.min(2, nivel + 1);
    if (a === 'menos') nivel = Math.max(0, nivel - 1);
    guardar(); aplicar();
  });
  aplicar();
})();
