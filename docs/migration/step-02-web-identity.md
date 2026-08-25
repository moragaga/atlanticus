# Step 02 — Atlanticus Web Identity Foundation

## Objetivo

Promover desde `atlanticus-multi-stage` únicamente la identidad transversal necesaria para ejecución Web local, sin incorporar todavía App Service/Entra, Users, Manager ni Navigation.

## Capabilities promovidas

```text
web/capabilities/identity/
├── core/
└── local/
```

El target semántico permanente es:

```bash
bash scripts/web/check.sh identity
```

`identity` agrupa ambos paquetes físicos. El mantenedor no necesita conocer sus rutas internas.

## Ajustes realizados durante la promoción

1. Se corrige en Identity Core la sintaxis inválida de múltiples excepciones en `module.py`.
2. El provider local deja de seleccionar aleatoriamente personas hardcodeadas.
3. El principal local se resuelve en este orden:
   - `subject_id` explícito al construir el provider;
   - `ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID`;
   - `local:<usuario-del-sistema>` como default de desarrollo.
4. `LocalIdentityProvider.production_ready` permanece `False`.
5. No se promueve `identity/app-service`; queda en HOLD hasta que exista un consumidor real de deployment/Entra.

## Frontera

Identity es Atlanticus Web transversal. No conoce ADA ni Command Center. Las aplicaciones consumen `IdentityProvider`/`AuthenticatedIdentity`; la selección del provider pertenece a la composición.

## Gate

Durante la instalación se actualiza el lock de `web/` por las nuevas dependencias de workspace y luego se ejecuta:

```bash
bash scripts/web/check.sh identity
bash scripts/web/check.sh
```

El primer comando aísla el slice nuevo; el segundo protege regresión de todas las capabilities Web promovidas.
