# Step 05D — ADA Navigation Presentation

**Estado:** en ejecución; gate técnico verde en 0.1.3/0.1.4 y ajuste visual 0.1.5 preparado
**Destino:** `scopes/ada/web/shell/navigation`
**Distribución:** `ada-web-shell-navigation==0.1.2`

## Objetivo

Mantener la presentación ADA de navegación como capability visual independiente que consume `atlanticus.web.navigation`, preservando el patrón aprobado de multi-stage y permitiendo ajustes UI explícitos sin reintroducir acoplamientos de Header, Tool Manifest, ServiceRegistry o datos de proyecto.

## Ajuste 0.1.5

El canvas conserva trigger, offcanvas, user card, acción opcional, links, grupos, active state y responsive previamente restaurados. Se agregan solamente dos zonas institucionales acordadas:

```text
Navigation Offcanvas
├── Header
│   ├── logo ADA
│   └── Asistente de Decisiones Ágiles
├── Main (scrollable)
│   ├── user card
│   ├── optional action
│   └── navigation nodes
└── Footer
    ├── Minera Los Pelambres
    └── Versión <app>
```

El Header usa `var(--dark-color)`. El botón de cierre se adapta al fondo oscuro. El área central es la única zona con scroll; el footer permanece al final del canvas.

## Datos inyectables

`AdaNavigationView` conserva datos de presentación únicamente:

- título/subtítulo;
- `brand_logo_src` / alt;
- `footer_logo_src` / alt;
- `application_version`;
- acción opcional.

Navigation no importa Branding ni conoce la aplicación concreta. `ada-generic-application` inyecta los assets públicos de `ada.web.ui.branding` y su versión instalada.

## Branding institucional

`ada-web-ui-branding==0.1.1` publica dos recursos por `AssetLayer`:

- `ada-operational-primary.svg`;
- `amsa-pelambres-primary.svg`.

Navigation recibe las URLs; no duplica ni posee estos assets.

## Versión de aplicación

La composition root usa `importlib.metadata.version('ada-generic-application')` como fuente única para `ApplicationMetadata.version` y para el footer de Navigation. Navigation no hardcodea versiones.

## Frontera preservada

```text
Identity + Navigation Core + Branding
              |
              | datos ya resueltos
              v
       Composition Root
              |
              | NavigationMenu + view
              v
   ada.web.shell.navigation
```

Sin `ToolManifest`, resolución de `ServiceRegistry`, `ADA N1`, `pelambres.cl` ni URLs de proyecto hardcodeadas.

## Gate

```bash
bash scripts/scopes/ada/check.sh branding
bash scripts/scopes/ada/check.sh navigation
bash scripts/scopes/ada/check.sh
```

Después:

```bash
cd scopes/ada/web/application/ada-generic-application
uv run ada-generic-application
```

05D continúa abierto hasta revisar visualmente 0.1.5 y aplicar los ajustes UI adicionales acordados.
