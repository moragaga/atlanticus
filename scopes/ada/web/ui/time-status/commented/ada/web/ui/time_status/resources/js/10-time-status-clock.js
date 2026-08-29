(() => {
  'use strict';

  // El marker se vuelve a resolver en cada tick; no retenemos un nodo que Dash pueda reemplazar.
  const CLOCK_SELECTOR = "[data-ada-time-status-clock='true']";
  const MODULE_NAME = 'ada-time-status';
  const DEFAULT_TIME_ZONE = 'America/Santiago';
  // Usamos formatToParts para producir YYYY-MM-DD HH:mm:ss sin depender del orden visual del locale.
  const FORMAT_LOCALE = 'en-CA';

  const controller = {
    timer: null,
    formatter: null,
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
      // Defensa de runtime: una configuración inválida no debe detener el reloj completo.
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

  function syncClock() {
    // Cada render consulta el reloj real; nunca sumamos segundos a un contador iniciado al cargar.
    const nowMs = Date.now();
    const text = formatTimestamp(nowMs);
    document.querySelectorAll(CLOCK_SELECTOR).forEach((node) => {
      node.textContent = text;
      node.title = text;
    });
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
    // Nos alineamos al siguiente segundo del reloj real y usamos setTimeout recursivo para corregir drift.
    const delayMs = Math.max(20, 1000 - (nowMs % 1000) + 5);
    controller.timer = window.setTimeout(scheduleNextTick, delayMs);
  }

  function resync() {
    scheduleNextTick();
  }

  function handleVisibilityChange() {
    // Al volver desde una pestaña suspendida recalculamos inmediatamente desde Date.now().
    if (!document.hidden) {
      resync();
    }
  }

  function start() {
    controller.formatter = createFormatter(resolveTimeZone());
    scheduleNextTick();
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
