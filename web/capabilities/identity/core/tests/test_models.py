import pytest

from atlanticus.web.identity.errors import IdentityDefinitionError
from atlanticus.web.identity.models import AuthenticatedIdentity


def test_authenticated_identity_keeps_received_optional_values_only() -> None:
    identity = AuthenticatedIdentity(
        provider_key='entra',
        issuer='issuer',
        subject_id='subject-1',
        display_name=' User One ',
        email=' user@example.com ',
    )

    assert identity.display_name == 'User One'
    assert identity.email == 'user@example.com'


def test_authenticated_identity_allows_missing_presentation_values() -> None:
    identity = AuthenticatedIdentity(
        provider_key='local',
        issuer='atlanticus-local',
        subject_id='local:john-doe',
    )

    assert identity.display_name is None
    assert identity.email is None


def test_authenticated_identity_rejects_empty_subject() -> None:
    with pytest.raises(IdentityDefinitionError, match='subject_id'):
        AuthenticatedIdentity(provider_key='local', issuer='local', subject_id=' ')
