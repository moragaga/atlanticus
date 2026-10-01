from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Variables públicas que forman el contrato tipado del environment del runtime Web.
ATLANTICUS_ENVIRONMENT_VARIABLE = 'ATLANTICUS_ENVIRONMENT'
APPLICATION_INSIGHTS_CONNECTION_STRING_VARIABLE = 'APPLICATION_INSIGHTS_CONNECTION_STRING'
# Contexto por ejecución que permite aislar una composición explícita de fuentes externas.
_MAPPING_ONLY = ContextVar('atlanticus_web_settings_mapping_only', default=False)


class WebEnvironment(StrEnum):
    # La capa Web mantiene sólo los ambientes actualmente validados por el framework.
    LOCAL = 'local'
    PRODUCTION = 'production'

    @property
    def is_local(self) -> bool:
        return self is WebEnvironment.LOCAL

    @property
    def is_production(self) -> bool:
        return self is WebEnvironment.PRODUCTION


class WebSettings(BaseSettings):
    # El contrato Web lee exclusivamente environment y no carga archivos .env por sí mismo.
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        env_prefix='',
        extra='ignore',
        frozen=True,
        validate_default=True,
    )

    # Environment gobierna decisiones propias del runtime Web, no configuración backend.
    environment: WebEnvironment = Field(
        default=WebEnvironment.LOCAL,
        validation_alias=ATLANTICUS_ENVIRONMENT_VARIABLE,
    )
    # La connection string queda disponible para la integración Web de Application Insights.
    application_insights_connection_string: str | None = Field(
        default=None,
        validation_alias=APPLICATION_INSIGHTS_CONNECTION_STRING_VARIABLE,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # from_mapping debe consumir únicamente los valores recibidos y no el proceso o dotenv.
        if _MAPPING_ONLY.get():
            return (init_settings,)
        # La construcción normal conserva la resolución estándar definida por cada subclase.
        return init_settings, env_settings, dotenv_settings, file_secret_settings

    @field_validator('environment', mode='before')
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        # Se normalizan espacios y mayúsculas sin ampliar el conjunto de ambientes válidos.
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator('application_insights_connection_string', mode='before')
    @classmethod
    def normalize_application_insights_connection_string(cls, value: object) -> object:
        # Una variable vacía equivale a telemetría Web no configurada.
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> Self:
        # Esta entrada permite pruebas y composición deterministas sin mutar os.environ.
        if not isinstance(values, Mapping):
            raise TypeError('values must be a mapping')
        copied: dict[str, str] = {}
        for name, value in values.items():
            if not isinstance(name, str):
                raise TypeError('Environment variable names must be text')
            if not isinstance(value, str):
                raise TypeError(f"Environment variable '{name}' must contain text")
            copied[name] = value
        # ContextVar evita interferencia entre ejecuciones concurrentes y anidadas.
        token = _MAPPING_ONLY.set(True)
        try:
            # Se usa el constructor normal para conservar validadores y aliases de subclases.
            return cls(**copied)
        finally:
            # Siempre se restaura el contexto, incluso cuando la validación falla.
            _MAPPING_ONLY.reset(token)
