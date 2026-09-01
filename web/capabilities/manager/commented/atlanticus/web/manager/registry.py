# Valida que cualquier renderer histórico declarado por un módulo sea invocable.
# La validación falla temprano ante una definición de módulo inválida.

import re

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.manager.models import ManagerModule, ManagerModuleGroup, ManagerPrincipal

_MODULE_KEY_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
_ROUTE_PATTERN = re.compile(r'^/[a-z0-9][a-z0-9/_-]*$')
_ROUTE_PREFIX_PATTERN = re.compile(r'^/[a-z0-9][a-z0-9/_-]*$')
_ACCESS_KEY_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')


class ManagerModuleRegistry:
    def __init__(
        self,
        groups: tuple[ManagerModuleGroup, ...],
        modules: tuple[ManagerModule, ...],
        *,
        route_prefix: str = '',
    ) -> None:
        if route_prefix and (
            not _ROUTE_PREFIX_PATTERN.fullmatch(route_prefix) or route_prefix.endswith('/')
        ):
            raise ManagerDefinitionError('Manager route prefix has an invalid format')
        self._route_prefix = route_prefix
        self._groups = self._validate_groups(groups)
        self._group_by_key = {group.key: group for group in self._groups}
        self._modules = self._validate_modules(modules)
        self._by_key = {module.key: module for module in self._modules}
        self._by_route = {module.route: module for module in self._modules}

    @property
    def groups(self) -> tuple[ManagerModuleGroup, ...]:
        return self._groups

    @property
    def modules(self) -> tuple[ManagerModule, ...]:
        return self._modules

    def require(self, key: str) -> ManagerModule:
        normalized = key.strip()
        if normalized not in self._by_key:
            raise ManagerDefinitionError(f'Manager module is not registered: {normalized}')
        return self._by_key[normalized]

    @property
    def route_prefix(self) -> str:
        return self._route_prefix

    @property
    def root_route(self) -> str:
        return self._route_prefix or '/'

    def route_for(self, module: ManagerModule) -> str:
        if self._route_prefix:
            return f'{self._route_prefix}{module.route}'
        return module.route

    def find_by_route(self, route: str) -> ManagerModule | None:
        normalized = route
        if self._route_prefix:
            prefix = f'{self._route_prefix}/'
            if not normalized.startswith(prefix):
                return None
            normalized = normalized[len(self._route_prefix) :]
        return self._by_route.get(normalized)

    def visible_modules(
        self,
        principal: ManagerPrincipal,
        policy: ManagerAuthorizationPolicy,
    ) -> tuple[ManagerModule, ...]:
        return tuple(module for module in self._modules if policy.can_view(principal, module))

    def _validate_groups(
        self,
        groups: tuple[ManagerModuleGroup, ...],
    ) -> tuple[ManagerModuleGroup, ...]:
        if not groups:
            raise ManagerDefinitionError('Manager must register at least one module group')
        keys: set[str] = set()
        for group in groups:
            if not _MODULE_KEY_PATTERN.fullmatch(group.key):
                raise ManagerDefinitionError('Manager module group key has an invalid format')
            if group.key in keys:
                raise ManagerDefinitionError(f'Manager module group key is duplicated: {group.key}')
            if not group.title.strip():
                raise ManagerDefinitionError('Manager module group title must not be empty')
            keys.add(group.key)
        return tuple(sorted(groups, key=lambda group: (group.order, group.key)))

    def _validate_modules(self, modules: tuple[ManagerModule, ...]) -> tuple[ManagerModule, ...]:
        if not modules:
            raise ManagerDefinitionError('Manager must register at least one module')
        keys: set[str] = set()
        routes: set[str] = set()
        source_signal_ids: set[str] = set()
        for module in modules:
            if not _MODULE_KEY_PATTERN.fullmatch(module.key):
                raise ManagerDefinitionError('Manager module key has an invalid format')
            if module.key in keys:
                raise ManagerDefinitionError(f'Manager module key is duplicated: {module.key}')
            keys.add(module.key)
            if module.group_key not in self._group_by_key:
                raise ManagerDefinitionError(
                    f'Manager module group is not registered: {module.group_key}'
                )
            if not _ROUTE_PATTERN.fullmatch(module.route) or module.route.endswith('/'):
                raise ManagerDefinitionError('Manager module route has an invalid format')
            if module.route in routes:
                raise ManagerDefinitionError(f'Manager module route is duplicated: {module.route}')
            routes.add(module.route)
            if not module.title.strip():
                raise ManagerDefinitionError('Manager module title must not be empty')
            if not callable(module.layout):
                raise ManagerDefinitionError('Manager module layout must be callable')
            if module.preamble is not None and not callable(module.preamble):
                raise ManagerDefinitionError('Manager module preamble must be callable')
            if module.history_preview_renderer is not None and not callable(
                module.history_preview_renderer
            ):
                raise ManagerDefinitionError('Manager history preview renderer must be callable')
            if module.default_section not in {'workflow', 'content'}:
                raise ManagerDefinitionError('Manager module default section is invalid')
            if not module.workflow_section_title.strip():
                raise ManagerDefinitionError('Manager workflow section title must not be empty')
            if not module.content_section_title.strip():
                raise ManagerDefinitionError('Manager content section title must not be empty')
            if not module.workflow_service.strip():
                raise ManagerDefinitionError('Manager workflow service must not be empty')
            if module.source_signal_id is not None:
                source_signal_id = module.source_signal_id.strip()
                if not source_signal_id:
                    raise ManagerDefinitionError('Manager source signal id must not be empty')
                if source_signal_id in source_signal_ids:
                    raise ManagerDefinitionError(
                        f'Manager source signal id is duplicated: {source_signal_id}'
                    )
                source_signal_ids.add(source_signal_id)
            self._validate_access(module)
        return tuple(
            sorted(
                modules,
                key=lambda module: (
                    self._group_by_key[module.group_key].order,
                    module.order,
                    module.key,
                ),
            )
        )

    def _validate_access(self, module: ManagerModule) -> None:
        for access_key in (module.access.view, module.access.validate, module.access.project):
            if access_key is not None and not _ACCESS_KEY_PATTERN.fullmatch(access_key):
                raise ManagerDefinitionError('Manager access key has an invalid format')
