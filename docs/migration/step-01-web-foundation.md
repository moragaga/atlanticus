# Step 01 — Atlanticus Web Foundation

## Estado

Correctivo 0.1.1 de la primera promoción Web transversal.

## Capacidades promovidas

- `web/framework/core`
- `web/framework/observability`

## Política de validación local

El gate local normaliza antes de validar:

1. sincroniza el lock existente con `uv sync --locked`;
2. aplica únicamente fixes seguros de Ruff sobre los paquetes completos;
3. formatea todos los Python del paquete, incluidos `src`, `tests` y `commented`;
4. confirma Ruff y formato limpios;
5. ejecuta los tests del slice;
6. verifica equivalencia AST de producción y espejo comentado.

El gate no ejecuta `uv lock`: un cambio de dependencias debe actualizar el lock como parte explícita del incremento que modifica `pyproject.toml`.

## Correctivo de aislamiento Dash

Los tests de `atlanticus.web.application` crean varias aplicaciones Dash dentro del mismo proceso. Dash mantiene su registro de páginas global al proceso, por lo que una página registrada por un test podía contaminar al siguiente y producir rutas duplicadas. `framework/core/tests/conftest.py` limpia el registro y los módulos de páginas entre tests. No se modifica el comportamiento productivo de `create_web_application`.
