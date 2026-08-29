(() => {
  'use strict';

  // Cada interacción y medición sigue limitada al container local de Time Status.
  const CONTAINER_SELECTOR = "[data-ada-time-status-container='true']";
  const TRIGGER_SELECTOR = "[data-ada-time-status-detail-trigger='true']";
  const SURFACE_SELECTOR = "[data-ada-time-status-detail-surface='true']";
  const OPEN_SELECTOR = "[data-ada-time-status-detail-open='true']";
  const TOOL_KEY_ATTRIBUTE = 'data-ada-time-status-tool-key';
  const PLACEMENT_ATTRIBUTE = 'data-ada-time-status-detail-placement';
  const VIEWPORT_MARGIN_PX = 8;

  // openToolKey conserva sólo el estado visual entre rerenders; positionFrame limita mediciones a un frame.
  let openToolKey = null;
  let positionFrame = null;

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
    // Nunca retenemos referencias a nodos reemplazados por Dash; siempre resolvemos el DOM vigente.
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

  function viewportBounds() {
    // visualViewport mejora el cálculo en navegadores móviles cuando cambia el viewport visible.
    const viewport = window.visualViewport;
    if (viewport) {
      return {
        left: viewport.offsetLeft,
        top: viewport.offsetTop,
        right: viewport.offsetLeft + viewport.width,
        bottom: viewport.offsetTop + viewport.height,
        width: viewport.width,
      };
    }
    return {
      left: 0,
      top: 0,
      right: window.innerWidth,
      bottom: window.innerHeight,
      width: window.innerWidth,
    };
  }

  function detailGapPx() {
    // El gap visual es .25rem; convertirlo desde el font-size raíz evita asumir que 1rem siempre son 16 px.
    const rootSize = Number.parseFloat(window.getComputedStyle(document.documentElement).fontSize);
    return (Number.isFinite(rootSize) ? rootSize : 16) * 0.25;
  }

  function positionParts(parts) {
    if (parts.surface.hidden) {
      return;
    }

    const bounds = viewportBounds();
    const gap = detailGapPx();
    const triggerRect = parts.trigger.getBoundingClientRect();
    const usableWidth = Math.max(0, bounds.width - VIEWPORT_MARGIN_PX * 2);
    const availableBelow = Math.max(
      0,
      bounds.bottom - VIEWPORT_MARGIN_PX - triggerRect.bottom - gap,
    );
    const availableAbove = Math.max(
      0,
      triggerRect.top - (bounds.top + VIEWPORT_MARGIN_PX) - gap,
    );
    const desiredHeight = parts.surface.scrollHeight;

    // Preferimos abrir abajo. Sólo hacemos flip arriba cuando abajo no alcanza y arriba ofrece más espacio útil.
    const placement =
      desiredHeight <= availableBelow || availableBelow >= availableAbove ? 'bottom' : 'top';
    const availableHeight = placement === 'bottom' ? availableBelow : availableAbove;

    parts.surface.setAttribute(PLACEMENT_ATTRIBUTE, placement);
    parts.surface.style.setProperty(
      '--ada-time-status-detail-available-height',
      `${Math.floor(availableHeight)}px`,
    );
    parts.surface.style.setProperty(
      '--ada-time-status-detail-viewport-width',
      `${Math.floor(usableWidth)}px`,
    );

    // Primero medimos desde el anclaje natural; luego desplazamos sólo lo necesario para quedar dentro del viewport.
    parts.surface.style.setProperty('--ada-time-status-detail-shift-x', '0px');
    const surfaceRect = parts.surface.getBoundingClientRect();
    let shiftX = 0;
    const minimumLeft = bounds.left + VIEWPORT_MARGIN_PX;
    const maximumRight = bounds.right - VIEWPORT_MARGIN_PX;
    if (surfaceRect.left < minimumLeft) {
      shiftX += minimumLeft - surfaceRect.left;
    }
    if (surfaceRect.right + shiftX > maximumRight) {
      shiftX -= surfaceRect.right + shiftX - maximumRight;
    }
    parts.surface.style.setProperty(
      '--ada-time-status-detail-shift-x',
      `${Math.round(shiftX)}px`,
    );
  }

  function positionOpenContainers() {
    document.querySelectorAll(OPEN_SELECTOR).forEach((container) => {
      const parts = resolveContainerParts(container);
      if (parts) {
        positionParts(parts);
      }
    });
  }

  function schedulePositionOpen() {
    // resize/scroll/mutations pueden dispararse en ráfaga; requestAnimationFrame evita layouts repetidos en el mismo frame.
    if (positionFrame !== null) {
      return;
    }
    positionFrame = window.requestAnimationFrame(() => {
      positionFrame = null;
      positionOpenContainers();
    });
  }

  function setOpen(parts, isOpen) {
    const key = toolKey(parts.container);
    parts.container.setAttribute('data-ada-time-status-detail-open', isOpen ? 'true' : 'false');
    parts.trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    parts.surface.hidden = !isOpen;
    parts.surface.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
    if (isOpen) {
      openToolKey = key || null;

      // La Surface se mide después de quitar hidden y antes del siguiente paint del navegador.
      positionParts(parts);
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
    // Rerender mantiene open-state por tool_key y vuelve a calcular geometría sobre los nodos nuevos.
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

    // Si cambió contenido mientras el flyout estaba abierto, recalculamos su colisión en el siguiente frame.
    if (openToolKey) {
      schedulePositionOpen();
    }
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
    const observer = new MutationObserver(handleMutations);
    observer.observe(document.body, { childList: true, subtree: true });

    // Sólo la geometría abierta se recalcula ante cambios de viewport/scroll; no se crea polling ni timer adicional.
    window.addEventListener('resize', schedulePositionOpen);
    window.addEventListener('scroll', schedulePositionOpen, true);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', schedulePositionOpen);
      window.visualViewport.addEventListener('scroll', schedulePositionOpen);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
