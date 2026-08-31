from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ATLANTICUS_ENVIRONMENT_VARIABLE = 'ATLANTICUS_ENVIRONMENT'
APPLICATION_INSIGHTS_CONNECTION_STRING_VARIABLE = 'APPLICATION_INSIGHTS_CONNECTION_STRING'


class WebEnvironment(StrEnum):
    LOCAL = 'local'
    PRODUCTION = 'production'

    @property
    def is_local(self) -> bool:
        return self is WebEnvironment.LOCAL

    @property
    def is_production(self) -> bool:
        return self is WebEnvironment.PRODUCTION


class WebSettings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        env_prefix='',
        extra='ignore',
        frozen=True,
        validate_default=True,
    )

    environment: WebEnvironment = Field(
        default=WebEnvironment.LOCAL,
        validation_alias=ATLANTICUS_ENVIRONMENT_VARIABLE,
    )
    application_insights_connection_string: str | None = Field(
        default=None,
        validation_alias=APPLICATION_INSIGHTS_CONNECTION_STRING_VARIABLE,
    )

    @field_validator('environment', mode='before')
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator('application_insights_connection_string', mode='before')
    @classmethod
    def normalize_application_insights_connection_string(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> Self:
        if not isinstance(values, Mapping):
            raise TypeError('values must be a mapping')
        copied: dict[str, str] = {}
        for name, value in values.items():
            if not isinstance(name, str):
                raise TypeError('Environment variable names must be text')
            if not isinstance(value, str):
                raise TypeError(f"Environment variable '{name}' must contain text")
            copied[name] = value
        return cls.model_validate(copied)
