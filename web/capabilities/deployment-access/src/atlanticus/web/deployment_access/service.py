from __future__ import annotations

import hashlib
from dataclasses import dataclass

from atlanticus.web.deployment_access.material import (
    DeploymentAccessIdentity,
    DeploymentAccessMaterialError,
    MaterialAvailability,
    generate_material,
    inspect_material,
    normalized_label,
    unlock_material,
)
from atlanticus.web.deployment_access.storage import (
    DeploymentAccessStorage,
    DeploymentAccessStorageError,
)


class DeploymentAccessVerificationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentAccessStatus:
    availability: MaterialAvailability
    fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class DeploymentAccessAuthentication:
    identity: DeploymentAccessIdentity
    fingerprint: str


class DeploymentAccessService:
    def __init__(
        self,
        *,
        storage: DeploymentAccessStorage,
        application_namespace: str,
        environment: str,
    ) -> None:
        if not isinstance(storage, DeploymentAccessStorage):
            raise TypeError('Deployment access requires material storage')
        self._storage = storage
        self._application_namespace = normalized_label(
            application_namespace, 'application_namespace'
        )
        self._environment = normalized_label(environment, 'environment')

    def inspect(self) -> DeploymentAccessStatus:
        try:
            content = self._storage.read()
        except DeploymentAccessStorageError:
            return DeploymentAccessStatus(MaterialAvailability.UNAVAILABLE)
        if content is None:
            return DeploymentAccessStatus(MaterialAvailability.ABSENT)
        availability = inspect_material(content)
        if availability is not MaterialAvailability.PRESENT:
            return DeploymentAccessStatus(availability)
        return DeploymentAccessStatus(availability, hashlib.sha256(content).hexdigest())

    def authenticate(self, *, service_user: str, password: str) -> DeploymentAccessAuthentication:
        content = self._storage.read()
        if content is None:
            raise DeploymentAccessMaterialError('Deployment access material is absent')
        identity = unlock_material(
            content,
            service_user=service_user,
            password=password,
            application_namespace=self._application_namespace,
            environment=self._environment,
        )
        return DeploymentAccessAuthentication(
            identity=identity, fingerprint=hashlib.sha256(content).hexdigest()
        )

    def create_or_replace(self, *, service_user: str, password: str) -> DeploymentAccessIdentity:
        return self._save(service_user=service_user, password=password, overwrite=True)

    def bootstrap_initial(self, *, service_user: str, password: str) -> DeploymentAccessIdentity:
        return self._save(service_user=service_user, password=password, overwrite=False)

    def delete(self) -> None:
        self._storage.delete()
        if self._storage.read() is not None:
            raise DeploymentAccessVerificationError('Deployment access deletion was not verified')

    def _save(
        self, *, service_user: str, password: str, overwrite: bool
    ) -> DeploymentAccessIdentity:
        content, identity = generate_material(
            service_user=service_user,
            password=password,
            application_namespace=self._application_namespace,
            environment=self._environment,
        )
        self._storage.write(content, overwrite=overwrite)
        stored = self._storage.read()
        if stored != content:
            raise DeploymentAccessVerificationError('Deployment access write was not verified')
        return identity
