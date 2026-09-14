import pytest

from atlanticus.web.identity.access import AccessDecision, AccessResolver, AccessStatus
from atlanticus.web.identity.bootstrap_root import (
    BootstrapRootAccessResolver,
    BootstrapRootPolicy,
)
from atlanticus.web.identity.errors import IdentityDefinitionError
from atlanticus.web.identity.models import AuthenticatedIdentity


class RecordingResolver(AccessResolver):
    def __init__(self) -> None:
        self.calls: list[tuple[AuthenticatedIdentity, str]] = []

    def resolve(self, identity: AuthenticatedIdentity, *, load_id: str) -> AccessDecision:
        self.calls.append((identity, load_id))
        return AccessDecision(status=AccessStatus.READY, user_id='user-normal')


def _identity(
    *,
    provider_key: str = 'entra',
    issuer: str = 'https://issuer.example',
    subject_id: str = 'subject-root',
) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key=provider_key,
        issuer=issuer,
        subject_id=subject_id,
    )


def test_bootstrap_root_policy_normalizes_identity_parts() -> None:
    policy = BootstrapRootPolicy(
        issuer='  https://issuer.example  ',
        subject_id='  subject-root  ',
        enabled=True,
    )

    assert policy.issuer == 'https://issuer.example'
    assert policy.subject_id == 'subject-root'


@pytest.mark.parametrize(
    ('field', 'value', 'message'),
    [
        ('issuer', '   ', 'issuer must not be empty'),
        ('subject_id', '   ', 'subject id must not be empty'),
    ],
)
def test_bootstrap_root_policy_requires_identity_parts(
    field: str,
    value: str,
    message: str,
) -> None:
    values = {
        'issuer': 'https://issuer.example',
        'subject_id': 'subject-root',
        'enabled': True,
    }
    values[field] = value

    with pytest.raises(IdentityDefinitionError, match=message):
        BootstrapRootPolicy(**values)


def test_bootstrap_root_policy_requires_boolean_enabled_flag() -> None:
    with pytest.raises(IdentityDefinitionError, match='must be boolean'):
        BootstrapRootPolicy(
            issuer='https://issuer.example',
            subject_id='subject-root',
            enabled=1,
        )


def test_matching_enabled_root_bypasses_fallback() -> None:
    fallback = RecordingResolver()
    resolver = BootstrapRootAccessResolver(
        policy=BootstrapRootPolicy(
            issuer='https://issuer.example',
            subject_id='subject-root',
            enabled=True,
        ),
        fallback=fallback,
    )

    decision = resolver.resolve(
        _identity(provider_key='any-provider'),
        load_id='load-root',
    )

    assert decision.status is AccessStatus.READY
    assert decision.user_id is None
    assert decision.bootstrap_root is True
    assert fallback.calls == []


@pytest.mark.parametrize(
    'identity',
    [
        _identity(issuer='https://other.example'),
        _identity(subject_id='other-subject'),
        _identity(issuer='https://ISSUER.example'),
        _identity(subject_id='SUBJECT-ROOT'),
    ],
)
def test_non_matching_root_falls_back_exactly(
    identity: AuthenticatedIdentity,
) -> None:
    fallback = RecordingResolver()
    resolver = BootstrapRootAccessResolver(
        policy=BootstrapRootPolicy(
            issuer='https://issuer.example',
            subject_id='subject-root',
            enabled=True,
        ),
        fallback=fallback,
    )

    decision = resolver.resolve(identity, load_id='load-normal')

    assert decision.user_id == 'user-normal'
    assert decision.bootstrap_root is False
    assert fallback.calls == [(identity, 'load-normal')]


def test_disabled_root_policy_falls_back_to_normal_access() -> None:
    identity = _identity()
    fallback = RecordingResolver()
    resolver = BootstrapRootAccessResolver(
        policy=BootstrapRootPolicy(
            issuer='https://issuer.example',
            subject_id='subject-root',
            enabled=False,
        ),
        fallback=fallback,
    )

    decision = resolver.resolve(identity, load_id='load-normal')

    assert decision.user_id == 'user-normal'
    assert decision.bootstrap_root is False
    assert fallback.calls == [(identity, 'load-normal')]
