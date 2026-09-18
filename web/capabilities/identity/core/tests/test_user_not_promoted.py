import pytest

from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.errors import IdentityDefinitionError
from atlanticus.web.identity.models import AuthenticatedIdentity


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key='entra',
        issuer='entra',
        subject_id='subject-1',
    )


def test_not_promoted_access_requires_user_id() -> None:
    with pytest.raises(IdentityDefinitionError, match='requires user_id'):
        AccessDecision(status=AccessStatus.USER_NOT_PROMOTED)


def test_not_promoted_snapshot_roundtrips() -> None:
    snapshot = AccessSnapshot.resolved(
        load_id='load-1',
        identity=_identity(),
        decision=AccessDecision(
            status=AccessStatus.USER_NOT_PROMOTED,
            user_id='user-1',
        ),
    )

    restored = AccessSnapshot.from_session(snapshot.to_session())

    assert restored.status is AccessStatus.USER_NOT_PROMOTED
    assert restored.user_id == 'user-1'


def test_not_promoted_status_page_is_forbidden() -> None:
    from atlanticus.web.identity.pages import user_not_promoted_response

    response = user_not_promoted_response()

    assert response.status_code == 403
    assert 'Usuario no habilitado' in response.get_data(as_text=True)
