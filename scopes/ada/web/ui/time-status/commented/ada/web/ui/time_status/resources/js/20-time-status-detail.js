(() => {
  'use strict';

  // Cada interacción resuelve su propia frontera DOM; no retenemos una Tool, un ID global ni un nodo compartido entre instancias.
  const CONTAINER_SELECTOR = "[data-ada-time-status-container='true']";
  const TRIGGER_SELECTOR = "[data-ada-time-status-detail-trigger='true']";
  const SURFACE_SELECTOR = "[data-ada-time-status-detail-surface='true']";
  const OPEN_SELECTOR = "[data-ada-time-status-detail-open='true']";

  function resolveParts(trigger) {
    // El trigger sólo puede controlar la Surface hermana dentro de su closest container.
    const container = trigger.closest(CONTAINER_SELECTOR);
    if (!container) {
      return null;
    }
    const surface = container.querySelector(SURFACE_SELECTOR);
    if (!surface) {
      return null;
    }
    return { container, trigger, surface };
  }

  function setOpen(parts, isOpen) {
    // DOM y atributos ARIA se actualizan juntos para mantener una sola representación del estado visible.
    parts.container.setAttribute('data-ada-time-status-detail-open', isOpen ? 'true' : 'false');
    parts.trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    parts.surface.hidden = !isOpen;
    parts.surface.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
  }

  function closeContainer(container) {
    // Re-resolvemos trigger y Surface en cada cierre; no dependemos de referencias retenidas.
    const trigger = container.querySelector(TRIGGER_SELECTOR);
    const surface = container.querySelector(SURFACE_SELECTOR);
    if (!trigger || !surface) {
      return;
    }
    setOpen({ container, trigger, surface }, false);
  }

  function closeOpenOutside(targetContainer) {
    // Al abrir otra instancia cerramos únicamente las demás superficies abiertas; el contenido nunca se comparte.
    document.querySelectorAll(OPEN_SELECTOR).forEach((container) => {
      if (container !== targetContainer) {
        closeContainer(container);
      }
    });
  }

  function toggleTrigger(trigger) {
    const parts = resolveParts(trigger);
    if (!parts) {
      return;
    }
    closeOpenOutside(parts.container);
    const isOpen = parts.container.getAttribute('data-ada-time-status-detail-open') === 'true';
    setOpen(parts, !isOpen);
  }

  function handleClick(event) {
    // La delegación permite que un trigger nuevo funcione sin registrar listeners por nodo.
    const trigger = event.target.closest?.(TRIGGER_SELECTOR);
    if (trigger) {
      event.preventDefault();
      toggleTrigger(trigger);
      return;
    }

    // Un click dentro de la Surface no la cierra; un click fuera de su container sí.
    document.querySelectorAll(OPEN_SELECTOR).forEach((container) => {
      if (!container.contains(event.target)) {
        closeContainer(container);
      }
    });
  }

  function handleKeydown(event) {
    // Escape cierra cualquier detail abierto sin introducir manejo global de foco.
    if (event.key === 'Escape') {
      document.querySelectorAll(OPEN_SELECTOR).forEach(closeContainer);
      return;
    }
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    const trigger = event.target.closest?.(TRIGGER_SELECTOR);
    if (!trigger) {
      return;
    }
    // Enter y Space implementan el comportamiento del role=button publicado por el Summary.
    event.preventDefault();
    toggleTrigger(trigger);
  }

  function start() {
    document.addEventListener('click', handleClick);
    document.addEventListener('keydown', handleKeydown);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
