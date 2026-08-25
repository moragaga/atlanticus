# Descubre Pages por paquetes Python explícitos; el orden de importación es determinista y se omiten módulos privados.
from __future__ import annotations

import pkgutil
import re
from importlib import import_module

from atlanticus.web.errors import WebCompositionError, WebDefinitionError

_PACKAGE_PATTERN = re.compile(r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$')


def validate_page_packages(packages: tuple[str, ...]) -> None:
    seen: set[str] = set()
    for package_name in packages:
        if not _PACKAGE_PATTERN.fullmatch(package_name):
            raise WebDefinitionError('Page package has an invalid module path')
        if package_name in seen:
            raise WebDefinitionError(f'Page package is duplicated: {package_name}')
        seen.add(package_name)


# La importación recursiva permite que cada módulo mantenga sus Pages dentro de su propio paquete.
def import_page_packages(packages: tuple[str, ...]) -> tuple[str, ...]:
    validate_page_packages(packages)
    imported: list[str] = []
    seen_modules: set[str] = set()

    for package_name in packages:
        try:
            package = import_module(package_name)
        except Exception as error:
            raise WebCompositionError(f'Failed to import page package: {package_name}') from error

        package_path = getattr(package, '__path__', None)
        if package_path is None:
            raise WebCompositionError(f'Page package is not a package: {package_name}')

        module_names = sorted(
            module.name
            for module in pkgutil.walk_packages(
                package_path,
                prefix=f'{package_name}.',
            )
            if not _is_private_module(module.name, package_name)
        )
        for module_name in module_names:
            if module_name in seen_modules:
                continue
            try:
                page_module = import_module(module_name)
                _bind_registered_page_layout(module_name, page_module)
            except WebCompositionError:
                raise
            except Exception as error:
                raise WebCompositionError(f'Failed to import page module: {module_name}') from error
            seen_modules.add(module_name)
            imported.append(module_name)

    return tuple(imported)


def _is_private_module(module_name: str, package_name: str) -> bool:
    relative = module_name.removeprefix(f'{package_name}.')
    return any(part.startswith('_') for part in relative.split('.'))


# Al importar Pages fuera del cargador automático de Dash, completamos el layout registrado igual que hace Pages.
def _bind_registered_page_layout(module_name: str, page_module: object) -> None:
    from dash import page_registry

    page = page_registry.get(module_name)
    if page is None or page.get('layout') is not None:
        return

    layout = getattr(page_module, 'layout', None)
    if layout is None:
        raise WebCompositionError(f'Page module has no layout: {module_name}')

    page['layout'] = layout
