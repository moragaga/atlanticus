from __future__ import annotations

from dataclasses import dataclass

from atlanticus.web.identity.access import AccessDecision, AccessResolver, AccessStatus
from atlanticus.web.identity.errors import IdentityDefinitionError
from atlanticus.web.identity.models import AuthenticatedIdentity


@dataclass(frozen=True, slots=True)
class BootstrapRootPolicy:
    issuer: str
    subject_id: str
    enabled: bool

    def __post_init__(self) -> None:
        issuer = self.issuer.strip()
        subject_id = self.subject_id.strip()
        if not issuer:
            raise IdentityDefinitionError('Bootstrap root issuer must not be empty')
        if not subject_id:
            raise IdentityDefinitionError('Bootstrap root subject id must not be empty')
        if not isinstance(self.enabled, bool):
            raise IdentityDefinitionError('Bootstrap root enabled flag must be boolean')
        object.__setattr__(self, 'issuer', issuer)
        object.__setattr__(self, 'subject_id', subject_id)

    def matches(self, identity: AuthenticatedIdentity) -> bool:
        return (
            self.enabled
            and identity.issuer == self.issuer
            and identity.subject_id == self.subject_id
        )


class BootstrapRootAccessResolver(AccessResolver):
    def __init__(self, *, policy: BootstrapRootPolicy, fallback: AccessResolver) -> None:
        if not isinstance(policy, BootstrapRootPolicy):
            raise TypeError('policy must be BootstrapRootPolicy')
        if not isinstance(fallback, AccessResolver):
            raise TypeError('fallback must implement AccessResolver')
        self._policy = policy
        self._fallback = fallback

    def resolve(self, identity: AuthenticatedIdentity, *, load_id: str) -> AccessDecision:
        if self._policy.matches(identity):
            return AccessDecision(
                status=AccessStatus.READY,
                bootstrap_root=True,
            )
        return self._fallback.resolve(identity, load_id=load_id)
