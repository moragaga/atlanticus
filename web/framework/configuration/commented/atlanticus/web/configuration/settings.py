from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Variables públicas que forman el contrato tipado del environment del runtime Web.
ATLANTICUS_ENVIRONMENT_VARIABLE = 'ATLANTICUS_ENVIRONMENT'
# Puerto configurable para el servidor Flask local; sin variable, el valor es 8000.
ATLANTICUS_WEB_PORT_VARIABLE = 'ATLANTICUS_WEB_PORT'
# Activación opcional sólo para comparar assets optimizados en local.
ATLANTICUS_WEB_ASSETS_OPTIMIZED_VARIABLE = 'ATLANTICUS_WEB_ASSETS_OPTIMIZED'
# Umbral de lentitud del servidor configurable por destino, en milisegundos.
ATLANTICUS_WEB_SLOW_REQUEST_THRESHOLD_MS_VARIABLE = 'ATLANTICUS_WEB_SLOW_REQUEST_THRESHOLD_MS'
APPLICATION_INSIGHTS_CONNECTION_STRING_VARIABLE = 'APPLICATION_INSIGHTS_CONNECTION_STRING'
OBSERVABILITY_FILE_LOGS_ENABLED_VARIABLE = 'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED'
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
    observability_file_logs_enabled: bool = Field(
        default=False,
        validation_alias=OBSERVABILITY_FILE_LOGS_ENABLED_VARIABLE,
    )
    environment: WebEnvironment = Field(
        default=WebEnvironment.LOCAL,
        validation_alias=ATLANTICUS_ENVIRONMENT_VARIABLE,
    )
    # Pydantic convierte el valor textual del .env y rechaza puertos fuera del rango TCP.
    web_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        validation_alias=ATLANTICUS_WEB_PORT_VARIABLE,
    )
    # La producción fuerza optimización, aunque la variable sea false.
    assets_optimized: bool = Field(
        default=False,
        validation_alias=ATLANTICUS_WEB_ASSETS_OPTIMIZED_VARIABLE,
    )
    # La connection string queda disponible para la integración Web de Application Insights.
    # Umbral entero positivo; 2000 ms son 2 segundos.
    slow_request_threshold_ms: int = Field(
        default=2000,
        gt=0,
        validation_alias=ATLANTICUS_WEB_SLOW_REQUEST_THRESHOLD_MS_VARIABLE,
    )
    application_insights_connection_string: str | None = Field(
        default=None,
        repr=False,
        validation_alias=APPLICATION_INSIGHTS_CONNECTION_STRING_VARIABLE,
    )

    # La política efectiva no puede desactivar minificación en producción.
    @property
    def optimize_assets(self) -> bool:
        return self.environment.is_production or self.assets_optimized

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

    @field_validator('observability_file_logs_enabled')
    @classmethod
    def reject_web_file_logging(cls, value: bool) -> bool:
        if value:
            raise ValueError('Web file logs must remain disabled')
        return value

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
