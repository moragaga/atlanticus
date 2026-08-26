# Step 05C — Component State evaluation

**Estado:** cerrado sin código

## Objetivo

Evaluar si el antiguo `state-wrapper` debía promoverse como capability independiente o si sólo era una capa histórica de composición.

## Hallazgo

Existe una necesidad transversal real en consumidores de Alarm Management, Notifications, Dashboard, Header y Operational Shell: representar estado visual del componente, cubrirlo temporalmente y aislar fallos opcionalmente.

El paquete anterior también contenía Page Readiness (`ready`, `ready_name`, `data-ready`). Esa semántica no pertenece al mismo contrato.

## Decisión

La capacidad futura se denomina conceptualmente `Component State` y, cuando exista un consumidor canónico, tendrá como destino tentativo:

```text
scopes/ada/web/ui/component-state
ada.web.ui.component_state
```

Conservará cover/overlay/wrapper/resilience. Page Readiness queda fuera.

No se promueve código en este step para evitar una capability huérfana. La promoción se hará junto con el primer consumidor real.
