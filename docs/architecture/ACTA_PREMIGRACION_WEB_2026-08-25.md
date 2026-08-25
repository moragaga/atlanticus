# Acta de Premigración Web — Atlanticus

**Fecha:** 25 de agosto de 2026  
**Estado:** Baseline arquitectónico evolutivo — semiestablecido, no definitivo  
**Alcance inicial:** Web Atlanticus + Web ADA  
**Repositorios fuente:** `atlanticus-multi-stage` y, posteriormente, `atlanticus-stage`  
**Objetivo:** iniciar una nueva línea canónica limpia, promoviendo sólo capacidades vigentes y permitiendo avanzar funcionalmente mientras `atlanticus-stage` continúa desarrollando el backend y el motor de alarmas.

---

## 1. Contexto y decisión de premigración

`atlanticus-stage` y `atlanticus-multi-stage` no se fusionarán directamente.

`atlanticus-stage` continúa siendo la línea activa para backend, materialización, KPI y el motor de alarmas actualmente en desarrollo. Su árbol ya contiene capacidades Atlanticus transversales (`backend`, `connectivity`, `integrations`) y dominio bajo `scopes/ada`, incluyendo Alarms, Data, KPIs, Operational Calendar y Processes.

`atlanticus-multi-stage` se considera desde este punto una **fuente de capacidades Web y experiencia acumulada**, no una estructura que deba copiarse completa al nuevo repositorio. Contiene capacidades valiosas, pero también generaciones anteriores, artifacts, adapters, tests y contratos que deben revisarse antes de ser promovidos.

La nueva línea canónica se construirá en un repositorio limpio, con fronteras explícitas desde el inicio.

Principio de migración:

> **No se migran repositorios completos; se promueven capacidades aprobadas.**

---

## 2. Frontera arquitectónica provisional

La estructura siguiente es una guía de ownership. No está escrita en piedra y puede evolucionar cuando una integración real demuestre una mejor frontera.

```text
atlanticus/
├── backend/
│   └── capacidades transversales Atlanticus
│
├── connectivity/
│   └── Cosmos, SQL, Storage, Service Bus, Redis, Key Vault, HTTP, etc.
│
├── integrations/
│   └── contratos e integración con sistemas externos reutilizables
│       └── pi/
│
├── web/
│   └── capacidades Web transversales Atlanticus
│       ├── core/
│       ├── identity/
│       ├── users/
│       ├── navigation/
│       ├── manager/
│       ├── activity/
│       └── shell/
│
├── scopes/
│   ├── ada/
│   │   ├── backend/
│   │   │   ├── kpis/
│   │   │   ├── processes/
│   │   │   └── ...
│   │   │
│   │   └── web/
│   │       ├── application/
│   │       │   └── ada-generic-application/
│   │       │
│   │       ├── ui/
│   │       │   ├── components/
│   │       │   └── shell/
│   │       │
│   │       ├── surfaces/
│   │       │   ├── integrated-operations/
│   │       │   ├── process/
│   │       │   └── strategic/
│   │       │
│   │       ├── alarms/
│   │       │   ├── management-summary/
│   │       │   ├── status/
│   │       │   ├── surface/
│   │       │   ├── detail/
│   │       │   └── management-action/
│   │       │
│   │       ├── kpis/
│   │       └── configuration/
│   │           ├── tools/
│   │           └── kpis/
│   │
│   └── command-center/
│       ├── contracts/
│       │   └── alarms/
│       ├── backend/
│       │   └── alarms/
│       └── web/
│           ├── application/
│           ├── configuration/
│           ├── dashboard/
│           └── trends/
│
├── deployment/
├── scripts/
├── artifacts/       # generado / temporal
├── distribution/    # generado / temporal
└── .runtime/        # generado / helper local
```

### Regla principal de frontera

```text
Atlanticus
backend / connectivity / integrations / web
        ↓
capacidades transversales
        ↓
scopes/*
ADA / Command Center / futuras soluciones
```

Atlanticus no debe conocer ADA ni Command Center.

Los scopes pueden consumir capacidades Atlanticus y componerlas según su producto.

---

## 3. Significado de `web/`

La raíz `web/` pertenece a Atlanticus y sólo debe contener capacidades reutilizables por más de una solución.

Ejemplos esperados:

- runtime/base Web;
- identidad;
- Users;
- Navigation;
- Manager;
- actividad de usuario;
- shell y contratos de presentación verdaderamente transversales.

Manager, Users y Navigation deben ser consumibles tanto por ADA como por Command Center.

Las capacidades específicas de ADA no deben vivir en `web/ada`; deben vivir bajo:

```text
scopes/ada/web/
```

Del mismo modo, las capacidades específicas de Command Center viven bajo:

```text
scopes/command-center/web/
```

---

## 4. ADA Generic Application

La aplicación ADA genérica se construirá desde temprano en:

```text
scopes/ada/web/application/ada-generic-application/
```

No será una demo, reference app ni showcase. Será la aplicación real y visible sobre la cual se integrarán progresivamente las capacidades promovidas.

Objetivo operativo:

```bash
uv run ada-generic-application
```

Debe poder levantarse localmente sin exigir Cosmos, SharePoint, Service Bus, Key Vault ni otras dependencias externas obligatorias.

La aplicación irá creciendo de forma incremental:

```text
ADA Generic Application
├── Header / Shell
├── Operational content slot
├── Manager
└── capabilities ADA montadas progresivamente
```

Cada capability migrada debe poder observarse en esta aplicación lo antes posible.

---

## 5. Manager

Manager sigue siendo una capability transversal de Atlanticus Web.

La solución ADA tendrá una ruta propia de Manager, previsiblemente `/manager`, en vez de exponer todas las opciones administrativas directamente en el menú global de ADA.

La Home de Manager será deliberadamente simple:

```text
Centro de Operaciones Integrado

Administración y configuración centralizada.
Utilice la navegación para acceder a las capacidades disponibles.
```

No se crearán dashboards, métricas ni tarjetas sólo para llenar espacio.

Se conservará el Header/contexto administrativo ya existente —incluyendo el botón/acción contextual de la derecha que ha demostrado simplificar la navegación— y se revisará durante la promoción de Manager qué elementos actuales son canónicos.

---

## 6. Baseline funcional de alarmas en ADA

Las capacidades de alarmas ADA son **presentaciones/acciones consumidoras** del dominio de alarmas cuya autoridad futura será Command Center.

Deben poder funcionar de forma independiente y también coexistir en una misma herramienta.

### 6.1 Alarm Management / Management Summary

Nombre actual: `Alarm Management`; nombre técnico revisable para reducir ambigüedad.

Responsabilidad:

- capability visual del Header;
- muestra estado/porcentaje de gestiones;
- en Integrated Operations presenta agregación general por Mina y Planta;
- en otras herramientas debe poder recibir contexto/scope y mostrar sólo los grupos que correspondan;
- no ejecuta gestión, lifecycle ni comandos sobre las alarmas.

### 6.2 Alarm Status

Capability del Header que hoy presenta los conteos `Activas` y `Gestionadas`.

Se debe revisar posteriormente su presentación visual porque los dos controles actuales se sienten como piezas separadas y poco integradas.

**Activas:**

- cantidad de alarmas actualmente activas;
- modal/resumen de las alarmas activas;
- incluye alarmas que permanecen activas aunque ya hayan sido gestionadas;
- complementa al Alarm Surface, donde físicamente no caben todas las alarmas activas.

**Gestionadas:**

- cantidad/resumen de alarmas gestionadas en un período;
- modal de gestionadas;
- tendencias;
- selección/agrupación y capacidades analíticas asociadas.

Una misma alarma puede estar simultáneamente activa y haber sido gestionada; ambos conceptos no son excluyentes.

### 6.3 Alarm Surface

Responsabilidad:

- mostrar las alarmas visibles dentro de la superficie operacional ADA;
- decidir/recibir qué alarmas se presentan en el espacio disponible;
- no ser dueño del detalle ni del comando de gestión.

### 6.4 Alarm Detail

Responsabilidad:

- mostrar información enriquecida de una alarma seleccionada;
- texto;
- imágenes;
- enlaces;
- definiciones y otros recursos configurados desde Command Center.

Debe poder reutilizarse independientemente del Surface.

### 6.5 Management Action

Responsabilidad:

- representar la acción `Gestionar` iniciada por el usuario;
- comunicar al motor de alarmas que alguien tomó conocimiento y está realizando una acción asociada a detener/atender la alarma.

El contrato exacto y el nombre de dominio definitivo **no se fijarán todavía**. Se alinearán posteriormente con el contrato real del motor de alarmas desarrollado en `atlanticus-stage`.

### Composición esperada

```text
Alarm contracts/provider
       │
       ├── Management Summary
       ├── Alarm Status
       ├── Alarm Surface
       ├── Alarm Detail
       └── Management Action
```

Ninguna de estas capacidades debe necesitar que las otras existan para construirse o ejecutarse.

---

## 7. Command Center y relación con ADA

Command Center será la futura autoridad del dominio de alarmas.

Conceptualmente será dueño de:

```text
Alarm Core
Alarm Persistence
Alarm Runtime
Alarm Delivery
Alarm Management semantics
Backup
Analytics / Trends
Alarm Configuration
```

ADA consume contratos/proyecciones/providers de Command Center, pero no importa directamente implementaciones internas del motor.

Regla:

```text
Command Center internals
        ↓
public alarm contracts/providers
        ↓
ADA alarm capabilities
```

El motor de alarmas no debe depender de `ada.web.*`.

---

## 8. Política de promoción desde `atlanticus-multi-stage`

`atlanticus-multi-stage` será tratado como cantera.

Para cada capability Web:

1. localizar implementación vigente;
2. determinar si sigue representando el comportamiento deseado;
3. revisar dependencias;
4. identificar legacy evidente;
5. promover únicamente source vigente;
6. promover espejo comentado equivalente;
7. conservar sólo tests que protejan contrato/comportamiento vigente;
8. montar la capability en `ada-generic-application` cuando aplique;
9. ejecutar un gate mínimo;
10. registrar la decisión en el ledger de migración.

No se trasladarán automáticamente adapters históricos, reference apps, artifacts, wheels, scripts correctivos ni tests de generaciones anteriores.

---

## 9. Orden inicial de migración Web

Orden propuesto, sujeto a ajustes por dependencias reales:

### Etapa W0 — Skeleton del repositorio

- crear estructura raíz;
- configuración Python 3.14.2 + UV;
- reglas básicas de exclusión de archivos generados;
- documentos de arquitectura y ledger.

### Etapa W1 — Atlanticus Web Foundation

Revisar/promover capacidades transversales mínimas:

- Web Core;
- Identity;
- Users;
- Navigation;
- Manager;
- Shell/base compartida.

No es obligatorio terminar todas antes de comenzar la aplicación ADA.

### Etapa W2 — ADA Generic Application

En cuanto exista el runtime Web mínimo:

- crear `ada-generic-application`;
- levantar `/`;
- crear content slot operacional;
- integrar `/manager`;
- mantener ejecución local sin infraestructura externa obligatoria.

### Etapa W3 — Header y capacidades base ADA

Promover y montar progresivamente:

- Branding;
- Header;
- Time Status;
- Global Indicator;
- wrappers/container/card necesarios.

Cada cambio debe verse en la aplicación real antes de continuar.

### Etapa W4 — Alarm capabilities ADA

Orden inicial:

1. Management Summary;
2. Alarm Status y modales;
3. Alarm Surface;
4. Alarm Detail;
5. Management Action.

Las primeras cuatro pueden trabajar con providers estáticos/locales mientras `atlanticus-stage` continúa evolucionando.

### Etapa W5 — Configuration

Tools/KPI Configuration no se copiarán de forma masiva.

Se revisarán incrementalmente al tener consumidores reales montados en la aplicación.

Separar cuando corresponda:

- semántica/contratos;
- edición Web;
- Source/Projection;
- adapters físicos;
- callbacks/UI.

### Etapa W6 — Integración futura con `atlanticus-stage`

Cuando las capacidades backend estén maduras se promoverán hacia sus fronteras definitivas.

Ejemplos previstos:

```text
Stage Alarm Engine
→ scopes/command-center/backend/alarms/

Stage KPI domain/processes
→ scopes/ada/backend/kpis/ y procesos correspondientes
```

No se realizará un merge ciego de árboles.

---

## 10. Gates durante la premigración

Durante la construcción funcional se priorizará velocidad sin trabajar a ciegas.

Gate mínimo por capability:

- Ruff check;
- Ruff format check;
- import correcto;
- espejo comentado equivalente;
- tests mínimos del contrato que se esté tocando;
- arranque de `ada-generic-application` cuando corresponda;
- smoke funcional/visual de la capability integrada.

Se posterga para una fase de hardening:

- cobertura exhaustiva;
- duplicación completa de escenarios entre capas;
- boundaries muy finos todavía en evolución;
- performance tuning específico;
- campañas E2E amplias;
- refactor contractual no requerido por un consumidor actual.

La premigración no autoriza eliminar pruebas críticas existentes de los repositorios fuente; simplemente evita trasladar toda la historia de tests al nuevo repositorio.

---

## 11. Carpetas generadas

Se adopta provisionalmente:

```text
artifacts/
├── processes/
└── web/
```

para outputs intermedios testeables.

```text
distribution/
├── processes/
└── web/
```

para productos listos para distribución.

```text
.runtime/
```

para estado/helper local efímero.

Flujo esperado:

```text
Source
  ↓
Artifact
  ↓
Distribution
  ↓
Deployment
```

Artifacts y Distribution nunca serán autoridad de source.

---

## 12. Deployment y scripts

`deployment/` y `scripts/` deberán evolucionar desde su orientación actual a procesos backend hacia capacidades transversales que también soporten aplicaciones Web.

La estructura exacta se decidirá cuando la primera Web requiera empaquetado/deployment real.

No se ampliará anticipadamente sin un consumidor.

---

## 13. Ledger de migración

Se mantendrá un archivo, por ejemplo:

```text
docs/migration/web-ledger.md
```

con una tabla mínima:

| Capability | Origen | Destino provisional | Estado | Decisión |
|---|---|---|---|---|
| Web Core | multi-stage | `web/core` | Pending | Review |
| Identity | multi-stage | `web/identity` | Pending | Promote/Review |
| Users | multi-stage | `web/users` | Pending | Promote/Review |
| Navigation | multi-stage | `web/navigation` | Pending | Promote/Review |
| Manager | multi-stage | `web/manager` | Pending | Review |
| ADA Header | multi-stage | `scopes/ada/web/ui/...` | Pending | Review |
| Global Indicator | multi-stage | `scopes/ada/web/ui/...` | Pending | Promote/Review |
| Alarm Management Summary | multi-stage | `scopes/ada/web/alarms/management-summary` | Pending | Review |
| Alarm Status | multi-stage | `scopes/ada/web/alarms/status` | Pending | Review UI |
| Alarm Surface | multi-stage | `scopes/ada/web/alarms/surface` | Pending | Review |
| Alarm Detail | multi-stage | `scopes/ada/web/alarms/detail` | Pending | Review |
| Alarm engine/legacy Web core | multi-stage | — | Do not promote as authority | Wait for stage |

El destino puede cambiar antes de la promoción si el análisis de dependencias demuestra una frontera mejor.

---

## 14. Criterios para modificar esta estructura

Esta acta es un baseline, no una arquitectura congelada.

Una frontera puede modificarse cuando exista evidencia concreta de que:

- una capability es realmente transversal y no específica de un scope;
- dos módulos separados no tienen responsabilidad independiente;
- un contrato actual impide composición limpia;
- una dependencia cruza scopes de forma incorrecta;
- la aplicación real demuestra que la composición propuesta no es adecuada.

No se modificarán fronteras sólo por estética del árbol o por anticipar necesidades hipotéticas.

---

## 15. Próximo paso acordado

El siguiente trabajo debe comenzar por la **premigración de Atlanticus Web genérico**, inspeccionando `atlanticus-multi-stage` capability por capability.

La prioridad no es copiar archivos rápidamente, sino determinar qué piezas forman la Web transversal mínima que permita crear y levantar cuanto antes:

```text
scopes/ada/web/application/ada-generic-application
```

Desde ese punto, la migración y el diseño continuarán sobre la aplicación real visible, integrando una capability a la vez.

---

**Estado del acta:** APROBACIÓN PENDIENTE / BASE PARA INICIAR PREMIGRACIÓN WEB.
