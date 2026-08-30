(() => {
  'use strict';

  // Eventos neutrales: uno entrega condiciones y el otro solicita el snapshot vigente.
  const SOURCE_FRESHNESS_EVENT = 'ada:source-freshness';
  const SOURCE_FRESHNESS_REQUEST_EVENT = 'ada:source-freshness-request';
  const WRAPPER_SELECTOR = "[data-ada-content-state-runtime='true']";
  const OVERLAY_SELECTOR = '.ada-content-state__overlay';
  const STATE_ATTRIBUTE = 'data-ada-content-state';
  const DECLARED_STATE_ATTRIBUTE = 'data-ada-content-state-declared';
  const TOOL_KEY_ATTRIBUTE = 'data-ada-content-state-tool-key';
  const SOURCE_KEYS_ATTRIBUTE = 'data-ada-content-state-sources';
  const STATE_PRIORITY = { ready: 0, stale: 1, source_error: 2, construction: 3 };
  const FRESHNESS_STATE = {
    fresh: 'ready',
    preventive: 'ready',
    hard_stale: 'stale',
    data_error: 'source_error',
  };

  // Snapshot por Tool+fuente para sobrevivir rerenders de Dash sin retener nodos antiguos.
  const sourceConditions = new Map();

  function snapshotKey(toolKey, sourceKey) {
    return `${toolKey}\u0000${sourceKey}`;
  }

  function sourceKeys(wrapper) {
    return String(wrapper.getAttribute(SOURCE_KEYS_ATTRIBUTE) || '')
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean);
  }

  function maxState(states) {
    return states.reduce(
      (current, candidate) =>
        STATE_PRIORITY[candidate] > STATE_PRIORITY[current] ? candidate : current,
      'ready',
    );
  }

  function runtimeState(wrapper) {
    const toolKey = String(wrapper.getAttribute(TOOL_KEY_ATTRIBUTE) || '').trim();
    const keys = sourceKeys(wrapper);
    if (!toolKey || !keys.length) {
      return null;
    }
    const states = [];
    for (const sourceKey of keys) {
      const condition = sourceConditions.get(snapshotKey(toolKey, sourceKey));
      if (!condition) {
        return null;
      }
      states.push(FRESHNESS_STATE[condition]);
    }
    return maxState(states);
  }

  function setEffectiveState(wrapper, state) {
    if (!(state in STATE_PRIORITY)) {
      return;
    }
    wrapper.setAttribute(STATE_ATTRIBUTE, state);
    const overlay = wrapper.querySelector(OVERLAY_SELECTOR);
    if (overlay) {
      overlay.setAttribute('aria-hidden', state === 'ready' ? 'true' : 'false');
    }
  }

  // Combina el estado declarativo con el runtime respetando la precedencia congelada.
  function syncWrapper(wrapper) {
    const dynamicState = runtimeState(wrapper);
    if (!dynamicState) {
      return;
    }
    const declaredState = String(
      wrapper.getAttribute(DECLARED_STATE_ATTRIBUTE) || 'ready',
    ).trim();
    if (!(declaredState in STATE_PRIORITY)) {
      return;
    }
    setEffectiveState(wrapper, maxState([declaredState, dynamicState]));
  }

  function wrapperUsesSource(wrapper, toolKey, sourceKey) {
    if (String(wrapper.getAttribute(TOOL_KEY_ATTRIBUTE) || '').trim() !== toolKey) {
      return false;
    }
    return sourceKeys(wrapper).includes(sourceKey);
  }

  function handleSourceFreshness(event) {
    const detail = event.detail || {};
    const toolKey = typeof detail.toolKey === 'string' ? detail.toolKey.trim() : '';
    const sourceKey = typeof detail.sourceKey === 'string' ? detail.sourceKey.trim() : '';
    const condition = typeof detail.condition === 'string' ? detail.condition.trim() : '';
    if (!toolKey || !sourceKey || !(condition in FRESHNESS_STATE)) {
      return;
    }

    sourceConditions.set(snapshotKey(toolKey, sourceKey), condition);
    document.querySelectorAll(WRAPPER_SELECTOR).forEach((wrapper) => {
      if (wrapperUsesSource(wrapper, toolKey, sourceKey)) {
        syncWrapper(wrapper);
      }
    });
  }

  function syncAddedElement(element) {
    if (element.matches(WRAPPER_SELECTOR)) {
      syncWrapper(element);
    }
    element.querySelectorAll(WRAPPER_SELECTOR).forEach(syncWrapper);
  }

  // Rehidrata wrappers reemplazados por Dash usando sólo el snapshot neutral.
  function handleMutations(mutations) {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node instanceof Element) {
          syncAddedElement(node);
        }
      });
    });
  }

  function start() {
    document.addEventListener(SOURCE_FRESHNESS_EVENT, handleSourceFreshness);
    document.querySelectorAll(WRAPPER_SELECTOR).forEach(syncWrapper);
    const observer = new MutationObserver(handleMutations);
    observer.observe(document.body, { childList: true, subtree: true });
    // Solicita el snapshot por si el productor cargó antes que este asset.
    document.dispatchEvent(new CustomEvent(SOURCE_FRESHNESS_REQUEST_EVENT));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
