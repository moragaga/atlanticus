# Step 05D — ADA Navigation Presentation

**Estado:** preparado para gate autoritativo
**Destino:** `scopes/ada/web/shell/navigation`
**Distribución:** `ada-web-shell-navigation==0.1.0`

## Objetivo

Promover la presentación ADA de navegación como una capability visual independiente que consume el contrato transversal `atlanticus.web.navigation` sin duplicar resolución, autorización ni configuración.

## Revisión del source anterior

La implementación multi-stage ya separaba parcialmente Navigation Core de su presentación, pero la capa ADA conservaba acoplamientos históricos:

- IDs y clases nombrados como `app-header-*` y `dashboard-*`;
- constantes `ADA N1`, `Navegación del proyecto` y `https://ada.pelambres.cl/` dentro del componente;
- un helper de presentación que resolvía servicios directamente;
- un `MutationObserver` global sobre `document.documentElement` para sincronizar estado visual;
- un asset `account-user.svg` declarado pero no consumido;
- CSS repetido por breakpoints y reglas específicas del Header.

## Decisión

La nueva frontera es:

```text
ada.web.shell.navigation
├── AdaNavigationView
├── AdaNavigationAction
├── build_ada_navigation_trigger()
├── build_ada_navigation_offcanvas()
└── create_ada_navigation_presentation_module()
```

La presentación recibe un `NavigationMenu` ya resuelto. No conoce `ServiceRegistry`, Users, Tool Manifest, Manager ni una aplicación concreta.

Título, subtítulo y acción superior son datos inyectables. No existe URL de Pelambres ni nombre `ADA N1` hardcodeado. La acción superior es opcional y no se muestra en el bootstrap.

Los IDs pertenecen a Navigation (`ada-navigation-*`) y el CSS usa sólo el namespace `.ada-navigation__*`. El componente no depende del Header para posicionarse.

La ruta activa se sincroniza mediante callbacks clientside de Dash y `dcc.Location`; se elimina el `MutationObserver` global y no se publica JavaScript adicional.

## Integración real

`ada-generic-application` sube a `0.1.3` y monta:

```text
ADA UI Core
+ Operational Branding
+ Identity Local
+ Navigation Core
+ ADA Navigation Presentation
```

La composition root resuelve el `NavigationMenu` desde los services y lo entrega a la presentación. Para el bootstrap local, Navigation Core recibe un `NavigationPrincipalProvider` derivado del snapshot de Identity; no se introduce Users todavía.

El Brand y el trigger se muestran en una franja temporal de bootstrap. Step 05E moverá esas mismas piezas al Header operacional real.

## Fuera de alcance

- Header operacional;
- Manager Navigation;
- Users;
- Navigation Configuration;
- autorización nueva;
- Global Indicators;
- Alarm Management;
- Alarm Status.

## Gate

```bash
bash scripts/scopes/ada/check.sh navigation
bash scripts/scopes/ada/check.sh
```

Luego validar visualmente:

```bash
cd scopes/ada/web/application/ada-generic-application
uv run ada-generic-application
```

05D permanece abierto hasta validar y ajustar la UI en la aplicación real.
