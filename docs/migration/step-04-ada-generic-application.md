# Step 04 — ADA Generic Application Bootstrap

Estado esperado: bootstrap visible de la primera aplicación real bajo `scopes/ada/web`.

## Alcance

- Crea `scopes/ada/web/application/ada-generic-application`.
- Publica el paquete concreto `ada.web.application.generic` dentro de namespaces `ada`, `ada.web` y `ada.web.application`.
- Usa Atlanticus Web Core, Identity Local y Navigation Core ya promovidos.
- Arranca en local sin Cosmos, SharePoint, Entra ni Service Bus obligatorios.
- Crea un único content slot real y una página `/` mínima.
- No crea todavía Header, Manager, superficies operacionales ni contratos ADA adicionales.
- Agrega tooling semántico del scope mediante `scripts/scopes/ada/check.*`.

## Contrato operativo

```bash
bash scripts/scopes/ada/check.sh
bash scripts/scopes/ada/check.sh application
```

La ejecución visible se realiza con:

```bash
cd scopes/ada/web/application/ada-generic-application
uv run ada-generic-application
```

## Siguiente paso

Promover y montar el Header ADA real sobre esta aplicación antes de seguir acumulando capacidades Web aisladas.
