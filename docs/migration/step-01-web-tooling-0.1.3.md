# Step 01 — Web Tooling Semántico 0.1.3

## Objetivo

Reemplazar el tooling histórico de migración `scripts/validation/check-web-foundation.*` por una interfaz permanente organizada por frontera.

## Estructura canónica

```text
scripts/
├── web/
│   ├── check.sh
│   ├── check.bat
│   └── check.py
├── repository/
│   └── validate_mirrors.py
└── commented/
    ├── web/
    └── repository/
```

## Interfaz

- `bash scripts/web/check.sh`: valida todas las capabilities Web registradas.
- `bash scripts/web/check.sh --all`: equivalente explícito.
- `bash scripts/web/check.sh core`: valida sólo Web Core.
- `bash scripts/web/check.sh observability`: valida sólo Web Observability.
- `bash scripts/web/check.sh core observability`: valida ambas explícitamente.
- `bash scripts/web/check.sh --list`: lista targets semánticos disponibles.

## Capabilities registradas inicialmente

| Target | Ruta actual |
|---|---|
| `core` | `web/framework/core` |
| `observability` | `web/framework/observability` |

La interfaz del mantenedor usa nombres semánticos. Las rutas físicas permanecen encapsuladas en `scripts/web/check.py` y pueden evolucionar sin cambiar los comandos públicos.

## Gate

El wrapper sincroniza `web/` usando exclusivamente el lock existente. El checker luego:

1. valida Python 3.14.2;
2. aplica fixes seguros Ruff;
3. formatea los targets seleccionados;
4. confirma Ruff + format limpio;
5. ejecuta los tests de los targets seleccionados;
6. valida espejos productivo/comentado.

El checker también normaliza y valida su propio tooling Python.

## Retiro

Se eliminan los archivos históricos:

- `scripts/validation/check-web-foundation.sh`
- `scripts/validation/check-web-foundation.bat`
- `scripts/validation/validate_commented_mirrors.py`

No se conserva adapter de compatibilidad porque el nuevo repositorio todavía está en premigración y la ruta anterior no constituye una API estable.
