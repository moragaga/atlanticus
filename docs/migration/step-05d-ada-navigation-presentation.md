# Step 05D — ADA Navigation Presentation

**Estado:** CERRADO / VERDE
**Destino:** `scopes/ada/web/shell/navigation`

Navigation Presentation conserva el patrón visual aprobado: trigger desktop lateral derecho con chevron, offcanvas derecho, header interno oscuro ADA, área central navegable, footer institucional y responsive.

El CSS final ajustado manualmente durante 05D es la autoridad visual canónica y no debe ser reemplazado por increments posteriores.

Branding es dueño de los assets institucionales:

- `ada-operational-primary.svg`;
- `amsa-pelambres-primary.png`.

Navigation recibe sus URLs por composición. La versión de la aplicación también se inyecta desde `ada-generic-application` mediante metadata; no se hardcodea dentro de Navigation.

Gate final validado: UI Core 8 tests, Branding 4 tests, Navigation 9 tests y Application 4 tests, además de Ruff/format y mirrors verdes.
