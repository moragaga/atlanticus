# Step 03 — Atlanticus Web Navigation Core

## Objetivo

Promover desde `atlanticus-multi-stage` únicamente el núcleo transversal de Navigation necesario para que las aplicaciones Atlanticus definan menú, principal de navegación y autorización de rutas sin depender de Users, ADA ni Command Center.

## Capability promovida

```text
web/capabilities/navigation/core/
```

El target semántico permanente es:

```bash
bash scripts/web/check.sh navigation
```

## Contrato preservado

Navigation Core mantiene responsabilidades pequeñas y explícitas:

- `NavigationDefinition` y modelos de links/grupos;
- `NavigationDefinitionProvider` para definición fija o dinámica;
- `NavigationPrincipalProvider` desacoplado de Users;
- resolución del menú visible según el principal efectivo;
- autorización de rutas internas y respuesta 403 consistente;
- integración con `ServiceRegistry` mediante `WebModule`.

No se promueven todavía:

- `web/capabilities/navigation/configuration`;
- composiciones Users/Navigation;
- Activity;
- UI específica ADA;
- Manager.

## Decisión de frontera

Navigation es una capability Web transversal de Atlanticus. No conoce ADA ni Command Center y tampoco depende de Users. Una composición futura puede adaptar Identity/Users hacia `NavigationPrincipal`, pero Navigation puede ejecutarse con un provider manual por sí sola.

## Gate

Durante la instalación se actualiza el lock del workspace Web y se ejecuta:

```bash
bash scripts/web/check.sh navigation
bash scripts/web/check.sh
```

El primer comando valida el slice nuevo de forma aislada. El segundo protege la regresión de Core, Observability, Identity y Navigation.

## Siguiente incremento

Crear temprano `scopes/ada/web/application/ada-generic-application` como composition root local y visible, sin Cosmos, SharePoint ni App Service obligatorios.
