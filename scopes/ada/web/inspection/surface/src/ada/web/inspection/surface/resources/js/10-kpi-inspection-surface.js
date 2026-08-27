(() => {
  'use strict';

  const ROOT_ID = 'ada-kpi-inspection-surface';
  const KEY_ID = 'ada-kpi-inspection-key';
  const TRIGGER_SELECTOR = '[data-kpi-inspection-key]';
  const CLOSE_SELECTOR = '[data-kpi-inspection-close]';
  const VIEW_SELECTOR = '[data-kpi-inspection-view]';
  const MODULE_NAME = 'kpi-inspection-surface';
  const DEFAULT_API_BASE_PATH = '/api/inspection/kpis';
  const NATIVE_INTERACTIVE = new Set(['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA']);

  const controller = {
    root: null,
    keyNode: null,
    fieldsNode: null,
    emptyNode: null,
    closeButton: null,
    previousFocus: null,
    request: null,
    requestSequence: 0,
    apiBasePath: DEFAULT_API_BASE_PATH,
  };

  function runtimeConfig() {
    const node = document.getElementById('atlanticus-runtime-config');
    if (!node) {
      return {};
    }
    try {
      return JSON.parse(node.textContent || '{}');
    } catch (_error) {
      return {};
    }
  }

  function resolveApiBasePath() {
    const config = runtimeConfig();
    const value = config?.modules?.[MODULE_NAME]?.api_base_path;
    if (typeof value !== 'string') {
      return DEFAULT_API_BASE_PATH;
    }
    const normalized = value.trim().replace(/\/+$/, '');
    return normalized.startsWith('/') && normalized !== '' ? normalized : DEFAULT_API_BASE_PATH;
  }

  function setState(state) {
    controller.root.dataset.state = state;
    controller.root.querySelectorAll(VIEW_SELECTOR).forEach((view) => {
      view.hidden = view.dataset.kpiInspectionView !== state;
    });
  }

  function openSurface(kpiKey, trigger) {
    controller.previousFocus = trigger || document.activeElement;
    controller.root.inert = false;
    controller.root.setAttribute('aria-hidden', 'false');
    controller.root.dataset.open = 'true';
    document.documentElement.classList.add('ada-kpi-inspection-open');
    document.body.classList.add('ada-kpi-inspection-open');
    controller.keyNode.textContent = kpiKey;
    controller.fieldsNode.replaceChildren();
    controller.emptyNode.hidden = true;
    setState('loading');
    controller.closeButton.focus({ preventScroll: true });
  }

  function closeSurface() {
    if (controller.request) {
      controller.request.abort();
      controller.request = null;
    }
    controller.requestSequence += 1;
    controller.root.dataset.open = 'false';
    controller.root.setAttribute('aria-hidden', 'true');
    controller.root.inert = true;
    document.documentElement.classList.remove('ada-kpi-inspection-open');
    document.body.classList.remove('ada-kpi-inspection-open');
    const focusTarget = controller.previousFocus;
    controller.previousFocus = null;
    if (focusTarget && focusTarget.isConnected && typeof focusTarget.focus === 'function') {
      focusTarget.focus({ preventScroll: true });
    }
  }

  function humanizeFieldName(name) {
    return String(name)
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/^./, (character) => character.toUpperCase());
  }

  function renderDefinition(definition) {
    controller.fieldsNode.replaceChildren();
    const entries = Object.entries(definition);
    controller.emptyNode.hidden = entries.length !== 0;
    for (const [name, value] of entries) {
      const term = document.createElement('dt');
      term.className = 'ada-kpi-inspection-surface__field-name';
      term.textContent = humanizeFieldName(name);
      const description = document.createElement('dd');
      description.className = 'ada-kpi-inspection-surface__field-value';
      description.textContent = value === null ? '—' : String(value);
      controller.fieldsNode.append(term, description);
    }
  }

  function validatePayload(payload, requestedKey) {
    if (!payload || typeof payload !== 'object' || payload.kpi_key !== requestedKey) {
      throw new Error('Inspection response is invalid');
    }
    if (payload.available === false && payload.definition === null) {
      return payload;
    }
    if (
      payload.available !== true ||
      !payload.definition ||
      typeof payload.definition !== 'object' ||
      Array.isArray(payload.definition)
    ) {
      throw new Error('Inspection response is invalid');
    }
    return payload;
  }

  async function loadDefinition(kpiKey) {
    if (controller.request) {
      controller.request.abort();
    }
    const request = new AbortController();
    controller.request = request;
    const sequence = ++controller.requestSequence;
    try {
      const response = await fetch(
        `${controller.apiBasePath}/${encodeURIComponent(kpiKey)}`,
        {
          method: 'GET',
          headers: { Accept: 'application/json' },
          cache: 'no-store',
          signal: request.signal,
        },
      );
      if (!response.ok) {
        throw new Error(`Inspection request failed with status ${response.status}`);
      }
      const payload = validatePayload(await response.json(), kpiKey);
      if (sequence !== controller.requestSequence || controller.root.dataset.open !== 'true') {
        return;
      }
      if (!payload.available) {
        setState('unavailable');
        return;
      }
      renderDefinition(payload.definition);
      setState('ready');
    } catch (error) {
      if (error?.name === 'AbortError' || sequence !== controller.requestSequence) {
        return;
      }
      setState('error');
    } finally {
      if (sequence === controller.requestSequence) {
        controller.request = null;
      }
    }
  }

  function inspectTrigger(trigger) {
    const kpiKey = String(trigger.getAttribute('data-kpi-inspection-key') || '').trim();
    if (!kpiKey) {
      return;
    }
    openSurface(kpiKey, trigger);
    void loadDefinition(kpiKey);
  }

  function handleClick(event) {
    const closeTarget = event.target.closest?.(CLOSE_SELECTOR);
    if (closeTarget && controller.root.contains(closeTarget)) {
      event.preventDefault();
      closeSurface();
      return;
    }
    const trigger = event.target.closest?.(TRIGGER_SELECTOR);
    if (!trigger) {
      return;
    }
    event.preventDefault();
    inspectTrigger(trigger);
  }

  function handleKeydown(event) {
    if (event.key === 'Escape' && controller.root.dataset.open === 'true') {
      event.preventDefault();
      closeSurface();
      return;
    }
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    const trigger = event.target.closest?.(TRIGGER_SELECTOR);
    if (!trigger || NATIVE_INTERACTIVE.has(trigger.tagName)) {
      return;
    }
    event.preventDefault();
    inspectTrigger(trigger);
  }

  function initialize() {
    controller.root = document.getElementById(ROOT_ID);
    if (!controller.root || controller.root.dataset.initialized === 'true') {
      return;
    }
    controller.keyNode = document.getElementById(KEY_ID);
    controller.fieldsNode = controller.root.querySelector('[data-kpi-inspection-fields]');
    controller.emptyNode = controller.root.querySelector('[data-kpi-inspection-empty]');
    controller.closeButton = controller.root.querySelector('.ada-kpi-inspection-surface__close');
    if (!controller.keyNode || !controller.fieldsNode || !controller.emptyNode || !controller.closeButton) {
      return;
    }
    controller.apiBasePath = resolveApiBasePath();
    controller.root.dataset.initialized = 'true';
    document.addEventListener('click', handleClick);
    document.addEventListener('keydown', handleKeydown);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
  } else {
    initialize();
  }
})();
