import pytest

from atlanticus.web.errors import ServiceRegistryError
from atlanticus.web.services import ServiceRegistry


def test_service_registry_registers_requires_and_freezes() -> None:
    services = ServiceRegistry()
    services.add('example', 'value')

    assert services.require('example', str) == 'value'
    assert services.snapshot() == {'example': 'value'}

    services.freeze()

    with pytest.raises(ServiceRegistryError, match='Service registry is frozen'):
        services.add('other', object())


def test_service_registry_rejects_missing_and_unexpected_type() -> None:
    services = ServiceRegistry()
    services.add('example', 10)

    with pytest.raises(ServiceRegistryError, match='Service is not registered'):
        services.require('missing')

    with pytest.raises(ServiceRegistryError, match='unexpected type'):
        services.require('example', str)
