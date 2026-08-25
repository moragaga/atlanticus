// Señal mínima de que el runtime JS base fue cargado; no registra listeners de negocio.
(() => {
  document.documentElement.dataset.atlanticusWeb = 'ready';
})();
