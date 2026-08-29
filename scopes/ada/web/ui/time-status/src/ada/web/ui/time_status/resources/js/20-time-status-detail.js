(() => {
  'use strict';

  const CONTAINER_SELECTOR = "[data-ada-time-status-container='true']";
  const TRIGGER_SELECTOR = "[data-ada-time-status-detail-trigger='true']";
  const SURFACE_SELECTOR = "[data-ada-time-status-detail-surface='true']";
  const OPEN_SELECTOR = "[data-ada-time-status-detail-open='true']";

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

  function setOpen(parts, isOpen) {
    parts.container.setAttribute('data-ada-time-status-detail-open', isOpen ? 'true' : 'false');
    parts.trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    parts.surface.hidden = !isOpen;
    parts.surface.setAttribute('aria-hidden', isOpen ? 'false' : 'true');
  }

  function closeContainer(container) {
    const trigger = container.querySelector(TRIGGER_SELECTOR);
    const surface = container.querySelector(SURFACE_SELECTOR);
    if (!trigger || !surface) {
      return;
    }
    setOpen({ container, trigger, surface }, false);
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
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
