# Espejo pedagógico: mantiene el mismo AST que producción y documenta el contrato Manager en español.
import re

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.manager.models import (
    ManagerEntry,
    ManagerModule,
    ManagerModuleGroup,
    ManagerPrincipal,
)

ManagerRegisteredItem = ManagerModule | ManagerEntry

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
        entries: tuple[ManagerEntry, ...] = (),
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
        self._entries = self._validate_entries(entries)
        self._items = self._validate_combined_contract(self._modules, self._entries)
        self._by_key = {item.key: item for item in self._items}
        self._by_route = {item.route: item for item in self._items}

    @property
    def groups(self) -> tuple[ManagerModuleGroup, ...]:
        return self._groups

    @property
    def modules(self) -> tuple[ManagerModule, ...]:
        return self._modules

    @property
    def entries(self) -> tuple[ManagerEntry, ...]:
        return self._entries

    @property
    def items(self) -> tuple[ManagerRegisteredItem, ...]:
        return self._items

    def require(self, key: str) -> ManagerModule:
        normalized = key.strip()
        item = self._by_key.get(normalized)
        if not isinstance(item, ManagerModule):
            raise ManagerDefinitionError(f'Manager module is not registered: {normalized}')
        return item

    def require_entry(self, key: str) -> ManagerEntry:
        normalized = key.strip()
        item = self._by_key.get(normalized)
        if not isinstance(item, ManagerEntry):
            raise ManagerDefinitionError(f'Manager entry is not registered: {normalized}')
        return item

    @property
    def route_prefix(self) -> str:
        return self._route_prefix

    @property
    def root_route(self) -> str:
        return self._route_prefix or '/'

    def route_for(self, item: ManagerRegisteredItem) -> str:
        if self._route_prefix:
            return f'{self._route_prefix}{item.route}'
        return item.route

    def find_by_route(self, route: str) -> ManagerRegisteredItem | None:
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

    def visible_entries(
        self,
        principal: ManagerPrincipal,
        policy: ManagerAuthorizationPolicy,
    ) -> tuple[ManagerEntry, ...]:
        return tuple(entry for entry in self._entries if policy.can_view(principal, entry))

    def visible_items(
        self,
        principal: ManagerPrincipal,
        policy: ManagerAuthorizationPolicy,
    ) -> tuple[ManagerRegisteredItem, ...]:
        return tuple(item for item in self._items if policy.can_view(principal, item))

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
        source_signal_ids: set[str] = set()
        for module in modules:
            self._validate_common_item(module)
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
            service_keys = (
                module.source_service,
                module.source_reader_service,
                module.projection_service,
                module.draft_validation_service,
            )
            if any(not service_key.strip() for service_key in service_keys):
                raise ManagerDefinitionError('Manager module service keys must not be empty')
            if (
                module.source_history_service is not None
                and not module.source_history_service.strip()
            ):
                raise ManagerDefinitionError('Manager source history service key must not be empty')
            if module.source_signal_id is not None:
                source_signal_id = module.source_signal_id.strip()
                if not source_signal_id:
                    raise ManagerDefinitionError('Manager source signal id must not be empty')
                if source_signal_id in source_signal_ids:
                    raise ManagerDefinitionError(
                        f'Manager source signal id is duplicated: {source_signal_id}'
                    )
                source_signal_ids.add(source_signal_id)
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

    def _validate_entries(self, entries: tuple[ManagerEntry, ...]) -> tuple[ManagerEntry, ...]:
        for entry in entries:
            self._validate_common_item(entry)
        return tuple(
            sorted(
                entries,
                key=lambda entry: (
                    self._group_by_key[entry.group_key].order,
                    entry.order,
                    entry.key,
                ),
            )
        )

    def _validate_common_item(self, item: ManagerRegisteredItem) -> None:
        if not _MODULE_KEY_PATTERN.fullmatch(item.key):
            raise ManagerDefinitionError('Manager item key has an invalid format')
        if item.group_key not in self._group_by_key:
            raise ManagerDefinitionError(f'Manager item group is not registered: {item.group_key}')
        if not _ROUTE_PATTERN.fullmatch(item.route) or item.route.endswith('/'):
            raise ManagerDefinitionError('Manager item route has an invalid format')
        if not item.title.strip():
            raise ManagerDefinitionError('Manager item title must not be empty')
        if not callable(item.layout):
            raise ManagerDefinitionError('Manager item layout must be callable')
        self._validate_access(item)

    def _validate_combined_contract(
        self,
        modules: tuple[ManagerModule, ...],
        entries: tuple[ManagerEntry, ...],
    ) -> tuple[ManagerRegisteredItem, ...]:
        items: tuple[ManagerRegisteredItem, ...] = (*modules, *entries)
        if not items:
            raise ManagerDefinitionError('Manager must register at least one administrative item')
        keys: set[str] = set()
        routes: set[str] = set()
        for item in items:
            if item.key in keys:
                raise ManagerDefinitionError(f'Manager item key is duplicated: {item.key}')
            if item.route in routes:
                raise ManagerDefinitionError(f'Manager item route is duplicated: {item.route}')
            keys.add(item.key)
            routes.add(item.route)
        return tuple(
            sorted(
                items,
                key=lambda item: (
                    self._group_by_key[item.group_key].order,
                    item.order,
                    item.key,
                ),
            )
        )

    def _validate_access(self, item: ManagerRegisteredItem) -> None:
        access_key = item.access_key
        if access_key is not None and not _ACCESS_KEY_PATTERN.fullmatch(access_key):
            raise ManagerDefinitionError('Manager access key has an invalid format')
