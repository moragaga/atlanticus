# Step 05B — ADA Operational Branding

**Estado:** preparado para gate autoritativo  
**Destino:** `scopes/ada/web/ui/branding`  
**Distribución:** `ada-web-ui-branding==0.1.0`

## Objetivo

Promover desde `atlanticus-multi-stage` sólo la identidad visual operacional que necesita ADA, sin trasladar el acoplamiento histórico entre Branding, Header, Tool Manifest y Manager.

## Revisión del source anterior

La implementación anterior contiene un resolver por calendario, manifest de variantes y `ATLANTICUS_BRAND_MANIFEST`. Las variantes de Fiestas Patrias, Halloween, Navidad y Año Nuevo no aportan assets distintos en el source vigente: terminan resolviendo el mismo recurso default. No existe evidencia actual para hacer de esa maquinaria una dependencia del Header nuevo.

El Header anterior también convierte el recurso de branding a data URI y construye dentro de su propia presentación el lockup con nombre de aplicación y Tool. Esa frontera obliga al Header a conocer demasiada configuración. Manager, por su parte, posee un lockup administrativo distinto con assets propios.

## Decisión

05B promueve una capability operacional independiente:

```text
ada.web.ui.branding
├── OperationalBrandState
├── build_operational_brand()
├── create_ada_branding_module()
└── resources/
    ├── css/
    └── img/ada-operational-primary.svg
```

El estado recibe únicamente datos de presentación. `context_name` es opcional y se inyecta desde la composición de la aplicación. Branding no consulta Tool Configuration, Tool Manifest ni providers.

El logo se publica mediante un `AssetLayer` de Atlanticus Web y se referencia por URL. No se incrusta como base64, permitiendo caching normal del navegador. El recurso operacional canónico se publica como `ada-operational-primary.svg`, conservando formato vectorial y caching normal del navegador.

El resolver calendario y los manifests históricos quedan diferidos. Si en el futuro existen variantes visuales reales, un resolver podrá seleccionar `logo_src` y entregar el resultado a `OperationalBrandState` sin cambiar el Header ni el componente.

## Integración real

`ada-generic-application` sube a `0.1.2`, registra `ada-branding` y monta el componente operacional directamente sobre el content slot. Este montaje es deliberadamente temporal: Step 05E moverá el mismo componente al slot de Branding del Header, sin reescribir su contrato.

El bootstrap local no inventa un nombre de Tool. Para smoke/configuración explícita puede inyectarse, por ejemplo, `Operaciones Integradas`.

## Fuera de alcance

- Header operacional;
- Global Indicators;
- Alarm Management;
- Alarm Status;
- Navigation presentation ADA;
- Manager Header/branding;
- Tool Configuration/Projection;
- variantes estacionales sin assets reales.

## Gate

```bash
bash scripts/scopes/ada/check.sh branding
bash scripts/scopes/ada/check.sh
```

Luego puede verificarse el boot local con:

```bash
cd scopes/ada/web/application/ada-generic-application
uv run ada-generic-application
```
