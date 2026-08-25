from __future__ import annotations

from collections.abc import Callable

from flask import g, has_request_context

from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.navigation.models import NavigationDefinition

NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY = 'atlanticus.web.navigation.definition-provider'
_REQUEST_CACHE_KEY = '_atlanticus_navigation_definition_cache'


class NavigationDefinitionProvider:
    def __init__(self, resolver: Callable[[], NavigationDefinition]) -> None:
        self._resolver = resolver
        self._request_key = f'provider-{id(self)}'

    def current(self) -> NavigationDefinition:
        cache = _request_cache()
        if cache is not None and self._request_key in cache:
            return cache[self._request_key]
        definition = self._resolver()
        if not isinstance(definition, NavigationDefinition):
            raise WebDefinitionError('Navigation definition provider returned an invalid value')
        if cache is not None:
            cache[self._request_key] = definition
        return definition


def _request_cache() -> dict[str, NavigationDefinition] | None:
    if not has_request_context():
        return None
    cache = getattr(g, _REQUEST_CACHE_KEY, None)
    if cache is None:
        cache = {}
        setattr(g, _REQUEST_CACHE_KEY, cache)
    return cache
