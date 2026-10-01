import pytest

from ada_command_center.web.application.generic.surfaces import surface_visibility


def test_surface_visibility_selects_manager_for_manager_routes() -> None:
    assert surface_visibility('/', route_prefix='/manager') == (False, True)
    assert surface_visibility('/manager', route_prefix='/manager') == (True, False)
    assert surface_visibility('/manager/users', route_prefix='/manager') == (True, False)
    assert surface_visibility('/history', route_prefix='/manager') == (False, True)


def test_surface_visibility_rejects_invalid_route_prefix() -> None:
    with pytest.raises(ValueError, match='non-root absolute route'):
        surface_visibility('/', route_prefix='/')
