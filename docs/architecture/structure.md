# Atlanticus — estructura objetivo inicial

Estado: baseline evolutivo de premigración. No es una estructura congelada.

## Fronteras

```text
atlanticus/
├── backend/          capacidades backend transversales Atlanticus
├── connectivity/     conectividad transversal
├── integrations/     contratos/adaptadores de sistemas externos reutilizables
├── web/              capacidades Web transversales Atlanticus
├── scopes/
│   ├── ada/          solución/composición ADA
│   │   ├── backend/
│   │   └── web/
│   └── command-center/
│       ├── contracts/
│       ├── backend/
│       └── web/
├── deployment/       deployment transversal de procesos y Web
├── scripts/          tooling transversal
├── artifacts/        generado: artefactos testeables
├── distribution/     generado: productos distribuibles
└── .runtime/         generado/local: helper de ejecución
```

## Regla de ownership

`backend/`, `connectivity/`, `integrations/` y `web/` no conocen ADA ni Command Center.
Los productos bajo `scopes/*` consumen capacidades Atlanticus.

`scopes/ada/web` contiene presentación/composición específica de ADA.
`scopes/command-center` será autoridad del dominio de alarmas y podrá exponer contratos públicos consumibles por ADA u otras herramientas.

## Flujo de entrega

```text
Source -> Artifact -> Distribution -> Deployment
```

`artifacts/`, `distribution/` y `.runtime/` no son autoridad de desarrollo.

## Primera aplicación de scope

La primera composición Web ejecutable se incorpora bajo:

```text
scopes/ada/web/application/ada-generic-application
```

Publica `ada.web.application.generic`. Los niveles `ada`, `ada.web` y `ada.web.application` permanecen como namespaces compartidos; `generic` es el paquete concreto de la aplicación.
