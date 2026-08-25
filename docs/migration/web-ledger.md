# Ledger de premigración Web

Este ledger registra qué se promueve desde `atlanticus-multi-stage`. La regla es promover capacidades aprobadas, no copiar el repositorio completo.

| Capability | Origen multi-stage | Destino nuevo | Estado | Decisión |
|---|---|---|---|---|
| Web Observability | `web/framework/observability` | `web/framework/observability` | PROMOTED | Base mínima, sin dependencia ADA |
| Web Core | `web/framework/core` | `web/framework/core` | PROMOTED | Base Flask/Dash transversal; corregido `except` inválido en `application.py` |
| Identity Core | `web/capabilities/identity/core` | `web/capabilities/identity/core` | PROMOTED | Contrato transversal de principal, provider, sesión y acceso; corregido `except` inválido en `module.py` |
| Identity Local | `web/capabilities/identity/local` | `web/capabilities/identity/local` | PROMOTED | Provider local estable; elimina personas hardcodeadas y permite subject explícito/entorno/usuario del sistema |
| Identity App Service | `web/capabilities/identity/app-service` | por revisar | HOLD | No necesaria para primer arranque local; evaluar cuando integremos deployment/Entra |
| Navigation Core | `web/capabilities/navigation/core` | `web/capabilities/navigation/core` | PROMOTED | Contrato transversal de menú, definición, principal de navegación y autorización; sin dependencia Users |
| Users Core | `web/capabilities/users/core` | por revisar | PENDING | Revisar tras Navigation/Application bootstrap |
| Manager | `web/capabilities/manager` | por revisar | PENDING | Recuperar capability transversal, no la composición ADA antigua |
| Reference App | `web/applications/reference` | — | DO NOT PROMOTE | Sólo referencia histórica |
| Runtime Infrastructure | `web/compositions/runtime-infrastructure` | por revisar más adelante | HOLD | No debe bloquear app local con Cosmos |
| SharePoint HTTP composition | `web/compositions/sharepoint-http` | por revisar | HOLD | Migrar sólo cuando exista consumidor real |

## Siguiente slice

`ADA Generic Application Bootstrap`: crear temprano `scopes/ada/web/application/ada-generic-application` usando Core + Observability + Identity + Navigation, todavía sin Manager ni infraestructura externa obligatoria.
