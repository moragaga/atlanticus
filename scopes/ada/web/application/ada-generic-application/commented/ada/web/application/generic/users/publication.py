from __future__ import annotations

from dataclasses import replace

from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosConflictError,
    CosmosPatchOperation,
    CosmosPreconditionFailedError,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import RuntimeOperational, RuntimeUser
from atlanticus.web.users.store import UsersRuntimeStore


# Implementación local: las pruebas in-process son seriales.
class AdaLocalRuntimeUserWriter:
    def __init__(self, store: UsersRuntimeStore) -> None:
        self._store = store

    def upsert_base_user(self, user: RuntimeUser) -> RuntimeUser:
        current = self._store.resolve(_identity(user))
        if current is not None:
            if current.identity.issuer != user.issuer or current.subject_id != user.subject_id:
                raise ValueError('Runtime identity cannot change')
            user = replace(user, operational=current.operational, access_keys=current.access_keys)
        return self._store.upsert_user(user)

    # No reescribe identidad, estado, perfil ni claves de acceso.
    def upsert_operational(self, user_id: str, operational: RuntimeOperational) -> RuntimeUser:
        current = next((user for user in self._store.list_users() if user.user_id == user_id), None)
        if current is None:
            raise ValueError('Runtime user must exist before operational enrichment')
        return self._store.upsert_user(replace(current, operational=operational))


# El escritor de ADA utiliza CAS por ETag y modifica campos específicos del usuario.
class AdaCosmosRuntimeUserWriter:
    def __init__(
        self, *, client: CosmosClient, store: UsersRuntimeStore, container_name: str
    ) -> None:
        if client is None:
            raise TypeError('ADA runtime writer requires a Cosmos connection')
        if not isinstance(store, UsersRuntimeStore):
            raise TypeError('ADA runtime writer requires UsersRuntimeStore')
        if not isinstance(container_name, str) or not container_name.strip():
            raise ValueError('ADA runtime writer container must not be empty')
        self._client = client
        self._store = store
        self._container = container_name

    def upsert_base_user(self, user: RuntimeUser) -> RuntimeUser:
        if not isinstance(user, RuntimeUser):
            raise TypeError('ADA base writer requires RuntimeUser')
        for _attempt in range(4):
            document = self._read(user.user_id)
            if document is None:
                try:
                    return self._store.upsert_user(user)
                except (CosmosConflictError, CosmosPreconditionFailedError):
                    continue
            current = self._decode(document, user.user_id)
            if current.issuer != user.issuer or current.subject_id != user.subject_id:
                raise ValueError('Runtime identity cannot change')
            updated = replace(
                current,
                identity=user.identity,
                enabled=user.enabled,
                profile=user.profile,
            )
            if updated == current:
                return current
            try:
                self._patch(
                    user.user_id,
                    document,
                    (
                        CosmosPatchOperation('set', '/user/identity', user.identity.to_document()),
                        CosmosPatchOperation('set', '/user/enabled', user.enabled),
                        CosmosPatchOperation('set', '/user/profile', user.profile.to_document()),
                    ),
                )
                result = self._resolve(user)
                if (
                    result.identity != user.identity
                    or result.enabled != user.enabled
                    or result.profile != user.profile
                ):
                    raise RuntimeError('ADA base publication was overwritten concurrently')
                return result
            except (CosmosConflictError, CosmosPreconditionFailedError):
                continue
        raise RuntimeError('ADA base publication changed concurrently')

    # No reescribe identidad, estado, perfil ni claves de acceso.
    def upsert_operational(self, user_id: str, operational: RuntimeOperational) -> RuntimeUser:
        if not isinstance(operational, RuntimeOperational):
            raise TypeError('ADA operational writer requires RuntimeOperational')
        for _attempt in range(4):
            document = self._read(user_id)
            if document is None:
                raise ValueError('Runtime user must exist before operational enrichment')
            current = self._decode(document, user_id)
            if current.operational == operational:
                return current
            try:
                self._patch(
                    user_id,
                    document,
                    (CosmosPatchOperation('set', '/user/operational', operational.to_document()),),
                )
                result = self._resolve(current)
                if result.operational != operational:
                    raise RuntimeError('ADA operational publication was overwritten concurrently')
                return result
            except (CosmosConflictError, CosmosPreconditionFailedError):
                continue
        raise RuntimeError('ADA operational publication changed concurrently')

    def _read(self, user_id: str) -> dict | None:
        return self._client.find_item(
            container_name=self._container,
            item_id=user_id,
            partition_key=user_id,
            include_metadata=True,
        )

    @staticmethod
    def _decode(document: dict, user_id: str) -> RuntimeUser:
        if (
            document.get('id') != user_id
            or document.get('document_type') != 'atlanticus_tool_runtime_user'
            or document.get('schema_version') != 2
            or not isinstance(document.get('user'), dict)
        ):
            raise ValueError('ADA runtime document contract is invalid')
        user = RuntimeUser.from_document(document['user'])
        if user.user_id != user_id:
            raise ValueError('ADA runtime document identity is invalid')
        return user

    def _patch(
        self, user_id: str, document: dict, operations: tuple[CosmosPatchOperation, ...]
    ) -> None:
        etag = document.get('_etag')
        if not isinstance(etag, str) or not etag:
            raise ValueError('ADA runtime document ETag is required')
        self._client.patch_item(
            container_name=self._container,
            item_id=user_id,
            partition_key=user_id,
            operations=operations,
            if_match_etag=etag,
        )

    def _resolve(self, user: RuntimeUser) -> RuntimeUser:
        result = self._store.resolve(_identity(user))
        if result is None:
            raise RuntimeError('ADA published runtime user was not found')
        return result


def _identity(user: RuntimeUser) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(provider_key='ada-publication', issuer=user.issuer, subject_id=user.subject_id)
