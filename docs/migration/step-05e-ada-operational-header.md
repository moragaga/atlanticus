# Step 05E — ADA Operational Header

**Estado:** en ejecución
**Destino:** `scopes/ada/web/shell/header`
**Distribución:** `ada-web-shell-header==0.1.0`

## Objetivo

Promover el Header operacional ADA como un shell visual liviano y `slot-driven`. El Header no conoce `ToolManifest`, configuración de KPIs, semántica Mina/Planta ni presentaciones de alarmas. La composition root entrega componentes ya construidos.

```text
Operational Header
├── Brand slot
├── Global Indicators slot
├── Alarm Management slot
├── Alarm Status slot
└── Navigation anchors
```

En el bootstrap 05E sólo Brand y Navigation tienen contenido real. Los slots restantes existen como contrato DOM pero colapsan cuando están vacíos.

## Reparto inicial de espacio

El Header es una fila de bloques. El Brand conserva su caja estable y los slots operacionales usan prioridades relativas:

- Global Indicators: `2.40`;
- Alarm Management: `1.45`;
- Alarm Status: `1.25`.

Estos valores pertenecen al layout del Header y pueden ajustarse visualmente más adelante sin cambiar las capabilities internas.

## Frontera

`ada.web.shell.header` recibe `dash.Component` ya resueltos. No importa Branding, Navigation Presentation, Global Indicators ni Alarms. Sólo depende de ADA UI Core para identidad DOM y de Atlanticus Web para publicación de assets.

La composition root monta `build_operational_brand()` y los triggers existentes de Navigation en el Header. El offcanvas sigue siendo propiedad de Navigation.

## Autoridad visual de capabilities cerradas

Step 05E no modifica archivos de `ada.web.ui.branding` ni `ada.web.shell.navigation`. El CSS de Navigation validado manualmente al cierre de 05D es autoridad y no se sobrescribe.

## Gate

```bash
bash scripts/scopes/ada/check.sh header
bash scripts/scopes/ada/check.sh
```

Después:

```bash
cd scopes/ada/web/application/ada-generic-application
uv run ada-generic-application
```

El step se cierra sólo después de revisar la geometría real del Header en pantalla.
