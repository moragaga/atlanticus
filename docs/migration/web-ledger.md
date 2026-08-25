# Ledger de premigración Web

Este ledger registra qué se promueve desde `atlanticus-multi-stage`. La regla es promover capacidades aprobadas, no copiar el repositorio completo.

| Capability | Origen multi-stage | Destino nuevo | Estado | Decisión |
|---|---|---|---|---|
| Web Observability | `web/framework/observability` | `web/framework/observability` | PROMOTED | Base mínima, sin dependencia ADA |
| Web Core | `web/framework/core` | `web/framework/core` | PROMOTED | Base Flask/Dash transversal; corregido `except` inválido en `application.py` |
| Identity Core | `web/capabilities/identity/core` | por revisar | PENDING | Revisar siguiente |
| Identity Local | `web/capabilities/identity/local` | por revisar | PENDING | Necesaria para ejecución local |
| Identity App Service | `web/capabilities/identity/app-service` | por revisar | PENDING | No necesaria para primer arranque local |
| Navigation Core | `web/capabilities/navigation/core` | por revisar | PENDING | Revisar con shell/navegación |
| Users Core | `web/capabilities/users/core` | por revisar | PENDING | Revisar tras Identity |
| Manager | `web/capabilities/manager` | por revisar | PENDING | Recuperar capability transversal, no la composición ADA antigua |
| Reference App | `web/applications/reference` | — | DO NOT PROMOTE | Sólo referencia histórica |
| Runtime Infrastructure | `web/compositions/runtime-infrastructure` | por revisar más adelante | HOLD | No debe bloquear app local con Cosmos |
| SharePoint HTTP composition | `web/compositions/sharepoint-http` | por revisar | HOLD | Migrar sólo cuando exista consumidor real |

## Siguiente slice

`Identity Core + Identity Local`, seguido de `Navigation Core`, con smoke dentro de la futura `scopes/ada/web/application/ada-generic-application` tan pronto exista el mínimo para levantarla.
