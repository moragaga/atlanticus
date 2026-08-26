# Step 05A — ADA Web UI Core

## Objetivo

Promover sólo la fundación visual mínima que debe ser compartida por las capacidades Web de ADA antes de reconstruir Branding, Navigation Presentation y Operational Header.

## Revisión del origen multi-stage

El antiguo `scopes/ada/ui/framework/core` mezclaba cuatro responsabilidades distintas dentro de una misma capa de assets:

- bootstrap/tokens y registro de assets;
- identidad DOM de componentes y slots;
- estados visuales (`DisplayStatus`/`DisplayValue` + iconos);
- readiness de página;
- un `AppTicker` global usado actualmente por Time Status.

La nueva línea no promueve esa mezcla completa.

## Capability promovida

```text
scopes/ada/web/ui/core
```

Publica:

```text
ada.web.ui.core
```

La capability contiene únicamente:

- registro de la capa base de assets ADA;
- Bootstrap vendorizado y tokens visuales compartidos;
- carga declarativa de Inter y Bootstrap Icons;
- atributos DOM estables para component/subcomponent/slot.

No contiene JavaScript, status visuals, readiness ni ticker.

## Decisiones de frontera

- El namespace viejo `ada.ui.framework.core` no se conserva. La capability pertenece explícitamente a `scopes/ada/web`, por lo que el namespace canónico es `ada.web.ui.core`.
- `status.py` y sus iconos se evaluarán cuando un consumidor real (Global Indicators/Runtime KPI) sea promovido.
- `ready.py`, `30-page-ready.css` y `10-page-ready.js` se evaluarán junto al shell/readiness que los necesite.
- `AppTicker` no se considera fundacional: hoy sólo tiene evidencia de consumo desde Time Status y se evaluará con esa capability.

## Montaje real

`ada-generic-application` incorpora `create_ada_ui_module()` a su composition root. Así la fundación promovida tiene un consumidor real desde este mismo step y sus assets se publican durante el boot local.

## Gate

```bash
bash scripts/scopes/ada/check.sh ui-core
bash scripts/scopes/ada/check.sh application
bash scripts/scopes/ada/check.sh
```

El cierre exige Ruff/format, tests, mirrors y boot local de la aplicación sin infraestructura externa.
