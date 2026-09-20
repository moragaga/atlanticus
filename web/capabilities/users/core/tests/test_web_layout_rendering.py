from types import SimpleNamespace

import pytest

pytest.importorskip('dash')
pytest.importorskip('dash_bootstrap_components')

from atlanticus.web.users.web import build_users_admin_configuration


class _UnavailableAdministration:
    def discover(self):
        raise RuntimeError('unavailable')


def test_users_admin_layout_renders_when_management_is_denied() -> None:
    context = SimpleNamespace(
        administration=_UnavailableAdministration(),
        can_manage=lambda: False,
    )

    rendered = build_users_admin_configuration(context)

    assert rendered is not None
