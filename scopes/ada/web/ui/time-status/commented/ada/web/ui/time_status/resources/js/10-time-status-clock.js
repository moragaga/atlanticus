(() => {
  'use strict';

  // El mismo controller mantiene reloj y freshness; TS-012A agrega hidratación inmediata tras rerender.
  const CLOCK_SELECTOR = "[data-ada-time-status-clock='true']";
  const SUMMARY_SELECTOR = "[data-component-key='time_status']";
  const SOURCE_SELECTOR = "[data-ada-time-status-source='true']";
  const SOURCE_VALUE_SELECTOR = "[data-ada-time-status-source-value='true']";
  const SOURCE_ICON_SELECTOR = "[data-ada-time-status-source-icon='true']";
  const MODULE_NAME = 'ada-time-status';
  const DEFAULT_TIME_ZONE = 'America/Santiago';
  const FORMAT_LOCALE = 'en-CA';

  const controller = {
    timer: null,
    formatter: null,
    observer: null,
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

  function resolveTimeZone() {
    const value = runtimeConfig()?.modules?.[MODULE_NAME]?.time_zone;
    return typeof value === 'string' && value.trim() ? value.trim() : DEFAULT_TIME_ZONE;
  }

  function createFormatter(timeZone) {
    const options = {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    };
    try {
      return new Intl.DateTimeFormat(FORMAT_LOCALE, options);
    } catch (_error) {
      return new Intl.DateTimeFormat(FORMAT_LOCALE, {
        ...options,
        timeZone: DEFAULT_TIME_ZONE,
      });
    }
  }

  function formatTimestamp(epochMs) {
    const values = {};
    for (const part of controller.formatter.formatToParts(new Date(epochMs))) {
      if (part.type !== 'literal') {
        values[part.type] = part.value;
      }
    }
    return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
  }

  function formatRelativeAge(ageSeconds) {
    if (ageSeconds < 10) {
      return 'hace menos de 10 segundos';
    }
    if (ageSeconds < 60) {
      const bucket = Math.floor(ageSeconds / 10) * 10;
      return `hace más de ${bucket} segundos`;
    }
    if (ageSeconds < 3600) {
      const minutes = Math.floor(ageSeconds / 60);
      return `hace más de ${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}`;
    }
    if (ageSeconds < 86400) {
      const hours = Math.floor(ageSeconds / 3600);
      return `hace más de ${hours} ${hours === 1 ? 'hora' : 'horas'}`;
    }
    const days = Math.floor(ageSeconds / 86400);
    return `hace más de ${days} ${days === 1 ? 'día' : 'días'}`;
  }

  function resolveCondition(ageSeconds, warningAfterSeconds, staleAfterSeconds) {
    if (ageSeconds >= staleAfterSeconds) {
      return 'hard_stale';
    }
    if (ageSeconds >= warningAfterSeconds) {
      return 'preventive';
    }
    return 'fresh';
  }

  function setSourceCondition(source, condition) {
    source.setAttribute('data-source-condition', condition);
    const content = source.querySelector("[data-ada-time-status-source-content='true']");
    if (content) {
      content.className = `ada-time-status__source-content ada-time-status__source-content--${condition}`;
    }
    const icon = source.querySelector(SOURCE_ICON_SELECTOR);
    if (icon) {
      const iconClass = condition === 'hard_stale' ? 'bi bi-cloud-slash' : 'bi bi-cloud-check';
      icon.className = `${iconClass} ada-time-status__item`;
    }
  }

  function updateSource(source, nowMs) {
    // DATA_ERROR pertenece a la resolución Python y no se reinterpreta con el reloj local.
    if (source.getAttribute('data-source-condition') === 'data_error') {
      return;
    }
    const timestampMs = Date.parse(source.getAttribute('data-source-timestamp-utc') || '');
    const warningAfterSeconds = Number(source.getAttribute('data-warning-after-seconds'));
    const staleAfterSeconds = Number(source.getAttribute('data-stale-after-seconds'));
    if (
      !Number.isFinite(timestampMs) ||
      !Number.isFinite(warningAfterSeconds) ||
      !Number.isFinite(staleAfterSeconds)
    ) {
      return;
    }

    const ageSeconds = Math.max(0, Math.floor((nowMs - timestampMs) / 1000));
    const condition = resolveCondition(ageSeconds, warningAfterSeconds, staleAfterSeconds);
    setSourceCondition(source, condition);
    const value = source.querySelector(SOURCE_VALUE_SELECTOR);
    if (value) {
      value.textContent = formatRelativeAge(ageSeconds);
    }
  }

  function updateSummary(summary, nowMs) {
    const sources = [...summary.querySelectorAll(SOURCE_SELECTOR)];
    sources.forEach((source) => updateSource(source, nowMs));
    if (!sources.length) {
      return;
    }
    const contentStale = sources.every(
      (source) => source.getAttribute('data-source-condition') === 'hard_stale',
    );
    const hasDataError = sources.some(
      (source) => source.getAttribute('data-source-condition') === 'data_error',
    );
    summary.setAttribute('data-content-stale', contentStale ? 'true' : 'false');
    summary.setAttribute('data-has-data-error', hasDataError ? 'true' : 'false');
  }

  function setClockNode(node, text) {
    node.textContent = text;
    node.title = text;
  }

  // Cuando Dash inserta un Summary nuevo se reemplaza el placeholder en la misma mutación, sin esperar al próximo segundo.
  function syncAddedElement(element, nowMs, text) {
    if (element.matches(CLOCK_SELECTOR)) {
      setClockNode(element, text);
    }
    element.querySelectorAll(CLOCK_SELECTOR).forEach((node) => setClockNode(node, text));
    if (element.matches(SUMMARY_SELECTOR)) {
      updateSummary(element, nowMs);
    }
    element.querySelectorAll(SUMMARY_SELECTOR).forEach((summary) => updateSummary(summary, nowMs));
  }

  function handleMutations(mutations) {
    // Se obtiene un único now para toda la ráfaga de nodos agregados y no se crea un segundo timer.
    const nowMs = Date.now();
    const text = formatTimestamp(nowMs);
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node instanceof Element) {
          syncAddedElement(node, nowMs, text);
        }
      });
    });
  }

  function syncClock() {
    const nowMs = Date.now();
    const text = formatTimestamp(nowMs);
    document.querySelectorAll(CLOCK_SELECTOR).forEach((node) => setClockNode(node, text));
    document.querySelectorAll(SUMMARY_SELECTOR).forEach((summary) => updateSummary(summary, nowMs));
    return nowMs;
  }

  function clearTimer() {
    if (controller.timer !== null) {
      window.clearTimeout(controller.timer);
      controller.timer = null;
    }
  }

  function scheduleNextTick() {
    clearTimer();
    const nowMs = syncClock();
    const delayMs = Math.max(20, 1000 - (nowMs % 1000) + 5);
    controller.timer = window.setTimeout(scheduleNextTick, delayMs);
  }

  function resync() {
    scheduleNextTick();
  }

  function handleVisibilityChange() {
    if (!document.hidden) {
      resync();
    }
  }

  function start() {
    controller.formatter = createFormatter(resolveTimeZone());
    scheduleNextTick();
    // El observer sólo rehidrata nodos nuevos; no vigila atributos ni hace polling.
    controller.observer = new MutationObserver(handleMutations);
    controller.observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', resync);
    window.addEventListener('pageshow', resync);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
