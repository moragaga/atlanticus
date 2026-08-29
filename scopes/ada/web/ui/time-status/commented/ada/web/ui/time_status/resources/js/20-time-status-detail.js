(() => {
  'use strict';

  // Cada interacción sigue resolviendo su propia frontera DOM. tool_key aporta identidad estable entre reemplazos de Dash.
  const CONTAINER_SELECTOR = "[data-ada-time-status-container='true']";
  const TRIGGER_SELECTOR = "[data-ada-time-status-detail-trigger='true']";
  const SURFACE_SELECTOR = "[data-ada-time-status-detail-surface='true']";
  const OPEN_SELECTOR = "[data-ada-time-status-detail-open='true']";
  const TOOL_KEY_ATTRIBUTE = 'data-ada-time-status-tool-key';

  // Este estado contiene sólo qué Tool tiene el detail abierto; timestamps y contenido continúan viviendo fuera del controller.
  let openToolKey = null;

  function resolveParts(trigger) {
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

  function resolveContainerParts(container) {
    // Tras un rerender siempre resolvemos los nodos nuevos; nunca retenemos referencias al Summary o Surface anteriores.
    const trigger = container.querySelector(TRIGGER_SELECTOR);
    const surface = container.querySelector(SURFACE_SELECTOR);
    if (!trigger || !surface) {
      return null;
    }
    return { container, trigger, surface };
  }

  function toolKey(container) {
    return String(container.getAttribute(TOOL_KEY_ATTRIBUTE) || '').trim();
  }

  function setOpen(parts, isOpen) {
    const key = toolKey(parts.container);
    parts.container.setAttribute('data-ada-time-status-detail-open', isOpen ? 'true' : 'false');
    parts.trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    parts.surface.hidden = !isOpen;
    parts.surface.setAttribute('aria-hidden', isOpen ? 'false' : 'true');

    // La memoria JS guarda sólo el open-state asociado al tool_key y se actualiza junto con el DOM visible.
    if (isOpen) {
      openToolKey = key || null;
    } else if (key && openToolKey === key) {
      openToolKey = null;
    }
  }

  function closeContainer(container) {
    const parts = resolveContainerParts(container);
    if (!parts) {
      return;
    }
    setOpen(parts, false);
  }

  function closeOpenOutside(targetContainer) {
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

  function restoreContainer(container) {
    // Sólo reabrimos el nuevo DOM cuando representa exactamente la Tool que estaba abierta antes del refresh.
    if (!openToolKey || toolKey(container) !== openToolKey) {
      return;
    }
    const parts = resolveContainerParts(container);
    if (!parts) {
      return;
    }
    closeOpenOutside(container);
    setOpen(parts, true);
  }

  function restoreAddedNode(node) {
    // El observer inspecciona únicamente nodos añadidos y subárboles que puedan contener Time Status.
    if (!(node instanceof Element)) {
      return;
    }
    if (node.matches(CONTAINER_SELECTOR)) {
      restoreContainer(node);
    }
    node.querySelectorAll(CONTAINER_SELECTOR).forEach(restoreContainer);
  }

  function handleMutations(mutations) {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach(restoreAddedNode);
    });
  }

  function handleClick(event) {
    const trigger = event.target.closest?.(TRIGGER_SELECTOR);
    if (trigger) {
      event.preventDefault();
      toggleTrigger(trigger);
      return;
    }

    document.querySelectorAll(OPEN_SELECTOR).forEach((container) => {
      if (!container.contains(event.target)) {
        closeContainer(container);
      }
    });
  }

  function handleKeydown(event) {
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
    event.preventDefault();
    toggleTrigger(trigger);
  }

  function start() {
    document.addEventListener('click', handleClick);
    document.addEventListener('keydown', handleKeydown);

    // MutationObserver es deliberado en TS-007: la Surface forma parte del subárbol que Dash puede reemplazar.
    const observer = new MutationObserver(handleMutations);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
