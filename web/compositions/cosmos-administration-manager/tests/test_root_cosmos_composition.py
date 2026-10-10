from __future__ import annotations

import pytest

from atlanticus.web.compositions.cosmos_administration_manager import (
    CosmosInventoryManagerEntryError,
    create_cosmos_root_manager_surface,
)
from atlanticus.web.compositions.deployment_access_manager import DeploymentRootSession
from atlanticus.web.cosmos_administration import CosmosAdministrationService
from atlanticus.web.deployment_access import DeploymentAccessService
from atlanticus.web.manager import ManagerPrincipal


class FakeAccess(DeploymentAccessService):
    def __init__(self):
        pass


class FakeAdministration(CosmosAdministrationService):
    def __init__(self):
        pass


class DenyAll:
    def can_view(self, _principal, _entry):
        return False


def _surface(*, authorization=None, max_items=200):
    return create_cosmos_root_manager_surface(
        root_session=DeploymentRootSession(access=FakeAccess()),
        administration=FakeAdministration(),
        fallback_principal=lambda: ManagerPrincipal(
            subject_id='anonymous', display_name='Anonymous'
        ),
        max_items=max_items,
        authorization=authorization,
    )


def test_one_manager_surface_exposes_both_distinct_entries():
    surface = _surface()
    registry = surface.registry
    assert registry.root_route == '/manager'
    assert {item.key for item in registry.entries} == {
        'deployment-access',
        'cosmos-administration',
    }
    assert registry.route_for(registry.require_entry('deployment-access')) == (
        '/manager/deployment-access'
    )
    assert registry.route_for(registry.require_entry('cosmos-administration')) == (
        '/manager/cosmos-administration'
    )
    assert {item.access_key for item in registry.entries} == {
        'deployment-access.manage',
        'cosmos-administration.manage',
    }


def test_manager_policy_applies_to_both_entries():
    surface = _surface(authorization=DenyAll())
    principal = ManagerPrincipal(
        subject_id='root', display_name='ROOT', administrative_override=True
    )
    assert surface.registry.visible_entries(principal, surface.authorization) == ()


def test_invalid_inventory_limit_fails_before_surface_is_created():
    with pytest.raises(CosmosInventoryManagerEntryError):
        _surface(max_items=201)
