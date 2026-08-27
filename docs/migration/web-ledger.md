# Ledger de premigración Web

Este ledger registra qué se promueve desde `atlanticus-multi-stage`. La regla es promover capacidades aprobadas, no copiar el repositorio completo.

| Capability | Origen multi-stage | Destino nuevo | Estado | Decisión |
|---|---|---|---|---|
| Web Observability | `web/framework/observability` | `web/framework/observability` | PROMOTED | Base mínima, sin dependencia ADA |
| Web Core | `web/framework/core` | `web/framework/core` | PROMOTED | Base Flask/Dash transversal |
| Identity Core | `web/capabilities/identity/core` | `web/capabilities/identity/core` | PROMOTED | Contrato transversal de principal, provider, sesión y acceso |
| Identity Local | `web/capabilities/identity/local` | `web/capabilities/identity/local` | PROMOTED | Provider local estable |
| Identity App Service | `web/capabilities/identity/app-service` | por revisar | HOLD | Evaluar con deployment/Entra |
| Navigation Core | `web/capabilities/navigation/core` | `web/capabilities/navigation/core` | PROMOTED | Contrato transversal; sin dependencia Users |
| Users Core | `web/capabilities/users/core` | por revisar | PENDING | Revisar tras Header/Manager |
| Manager | `web/capabilities/manager` | por revisar | PENDING | Recuperar capability transversal, no composición ADA antigua |
| ADA Web UI Core | `scopes/ada/ui/framework/core` | `scopes/ada/web/ui/core` | PROMOTED | Assets/tokens + DOM; status/readiness/ticker diferidos |
| ADA Operational Branding | `scopes/ada/ui/components/branding` | `scopes/ada/web/ui/branding` | PROMOTED | Brand operacional independiente; ADA SVG + Pelambres PNG por AssetLayer |
| ADA Navigation Presentation | `scopes/ada/ui/shell/navigation` | `scopes/ada/web/shell/navigation` | PROMOTED | Patrón visual aprobado cerrado; CSS manual es autoridad |
| ADA Operational Header | `scopes/ada/ui/shell/header` | `scopes/ada/web/shell/header` | PROMOTING | Shell slot-driven; Brand/Navigation se anclan sin ownership; slots operacionales externos |

## Siguiente slice

`ADA Operational Header`: validar 0.1.0 en `ada-generic-application`, ajustar sólo geometría/layout del Header y cerrar 05E antes de promover Global Indicators.
