from __future__ import annotations


def build_kpi_inspection_surface_fragment() -> str:
    return """<div id="ada-kpi-inspection-surface" class="ada-kpi-inspection-surface" data-open="false" data-state="idle" data-busy="false" aria-hidden="true" inert>
    <section class="ada-kpi-inspection-surface__panel" role="dialog" aria-modal="false" aria-busy="false" aria-labelledby="ada-kpi-inspection-title" aria-describedby="ada-kpi-inspection-status">
        <header class="ada-kpi-inspection-surface__header">
            <div class="ada-kpi-inspection-surface__heading">
                <p class="ada-kpi-inspection-surface__eyebrow">KPI</p>
                <h2 id="ada-kpi-inspection-title" class="ada-kpi-inspection-surface__title">Información del indicador</h2>
                <p id="ada-kpi-inspection-key" class="ada-kpi-inspection-surface__key"></p>
            </div>
            <button type="button" class="ada-kpi-inspection-surface__close" aria-label="Cerrar inspector KPI" data-kpi-inspection-close>×</button>
        </header>
        <div id="ada-kpi-inspection-status" class="ada-kpi-inspection-surface__body" aria-live="polite">
            <div class="ada-kpi-inspection-surface__view" data-kpi-inspection-view="loading" hidden>
                <span class="ada-kpi-inspection-surface__spinner" aria-hidden="true"></span>
                <p>Cargando información…</p>
            </div>
            <div class="ada-kpi-inspection-surface__view" data-kpi-inspection-view="unavailable" hidden>
                <p>No hay información descriptiva disponible para este KPI.</p>
            </div>
            <div class="ada-kpi-inspection-surface__view" data-kpi-inspection-view="error" hidden>
                <p>Unable to load KPI information.</p>
            </div>
            <div class="ada-kpi-inspection-surface__view" data-kpi-inspection-view="ready" hidden>
                <p class="ada-kpi-inspection-surface__empty" data-kpi-inspection-empty hidden>La definición existe y todavía no contiene información descriptiva.</p>
                <dl class="ada-kpi-inspection-surface__fields" data-kpi-inspection-fields></dl>
            </div>
        </div>
    </section>
</div>"""
