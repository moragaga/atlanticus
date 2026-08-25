# Resuelve un principal local estable sin acoplar el provider a personas de prueba concretas.
from __future__ import annotations

import getpass
import os

from flask import Request

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.provider import IdentityProvider

_LOCAL_SUBJECT_ENVIRONMENT_VARIABLE = 'ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID'


class LocalIdentityProvider(IdentityProvider):
    def __init__(self, *, subject_id: str | None = None) -> None:
        # Un subject explícito facilita pruebas y composiciones locales deterministas.
        resolved_subject_id = _resolve_subject_id(subject_id)
        # Reutilizamos la validación neutral del contrato de identidad al construir el provider.
        identity = AuthenticatedIdentity(
            provider_key='local',
            issuer='atlanticus-local',
            subject_id=resolved_subject_id,
        )
        self._subject_id = identity.subject_id

    @property
    def key(self) -> str:
        return 'local'

    @property
    def production_ready(self) -> bool:
        # Este provider existe sólo para desarrollo y nunca es válido en producción.
        return False

    def validate_configuration(self) -> None:
        return None

    def resolve(self, request: Request) -> AuthenticatedIdentity:
        del request
        # La identidad permanece estable durante toda la vida del provider.
        return AuthenticatedIdentity(
            provider_key='local',
            issuer='atlanticus-local',
            subject_id=self._subject_id,
        )


def _resolve_subject_id(explicit_subject_id: str | None) -> str:
    if explicit_subject_id is not None:
        return explicit_subject_id

    # La variable permite fijar el mismo principal entre máquinas o escenarios locales.
    configured_subject_id = os.environ.get(_LOCAL_SUBJECT_ENVIRONMENT_VARIABLE)
    if configured_subject_id is not None:
        return configured_subject_id

    # Sin configuración, el usuario del sistema entrega un principal local estable por desarrollador.
    return f'local:{getpass.getuser()}'
