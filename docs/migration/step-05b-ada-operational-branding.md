# Step 05B — ADA Operational Branding

**Estado:** PROMOTED; ampliación institucional consumida por Navigation en 05D
**Destino:** `scopes/ada/web/ui/branding`
**Distribución:** `ada-web-ui-branding==0.1.1`

## Responsabilidad

Publicar identidad visual ADA como assets y componentes reutilizables, sin conocer Header, Navigation, Tool Manifest ni Manager.

## Assets públicos actuales

```text
ada.web.ui.branding
└── resources/img
    ├── ada-operational-primary.svg
    └── amsa-pelambres-primary.svg
```

Las URLs públicas son `DEFAULT_OPERATIONAL_BRAND_LOGO_SRC` y `DEFAULT_PELAMBRES_BRAND_LOGO_SRC`. Ambos recursos se sirven por `AssetLayer`, nunca como base64.

`OperationalBrandState` sigue siendo la presentación operacional de ADA y recibe `context_name` por inyección. La incorporación del logo de Minera Los Pelambres no cambia ese contrato: sólo amplía el catálogo público de assets para composiciones que lo necesitan.

Manager mantiene su composición visual separada.
