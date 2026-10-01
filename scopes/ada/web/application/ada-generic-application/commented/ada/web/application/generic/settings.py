from __future__ import annotations

# Espejo pedagógico: mismo comportamiento productivo con contexto explicativo en español.

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from ada.web.kpis.collector import CosmosKpiDeliveryReaderSettings
from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.persistence import (
    ToolPersistenceSettings,
    ToolProjectionProvider,
    ToolSourceProvider,
)
from ada.web.tools.projection.cosmos import TOOL_PROJECTION_STORAGE_RESOURCE
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
    StorageSasCredential,
    StorageSettings,
)
from atlanticus.web.configuration import WebSettings

APPLICATION_NAMESPACE_VARIABLE = 'ADA_APPLICATION_NAMESPACE'
PERSISTENCE_MODE_VARIABLE = 'ADA_PERSISTENCE_MODE'
TOOL_NAMESPACE_VARIABLE = 'ADA_TOOL_NAMESPACE'
TOOL_LOCAL_BASE_ROOT_VARIABLE = 'ADA_TOOL_LOCAL_BASE_ROOT'
TOOL_SOURCE_BLOB_CONTAINER_VARIABLE = 'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME'
TOOL_SOURCE_BLOB_CONNECTION_STRING_VARIABLE = 'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING'
TOOL_SOURCE_BLOB_ACCOUNT_URL_VARIABLE = 'ADA_TOOL_SOURCE_BLOB_ACCOUNT_URL'
TOOL_SOURCE_BLOB_SAS_TOKEN_VARIABLE = 'ADA_TOOL_SOURCE_BLOB_SAS_TOKEN'
TOOL_PROJECTION_COSMOS_ENDPOINT_VARIABLE = 'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT'
TOOL_PROJECTION_COSMOS_KEY_VARIABLE = 'ADA_TOOL_PROJECTION_COSMOS_KEY'
TOOL_PROJECTION_COSMOS_DATABASE_VARIABLE = 'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME'
KPI_DELIVERY_COSMOS_ENDPOINT_VARIABLE = 'COSMOS_CONSUMPTION_ENDPOINT'
KPI_DELIVERY_COSMOS_KEY_VARIABLE = 'COSMOS_CONSUMPTION_KEY'
KPI_DELIVERY_COSMOS_DATABASE_VARIABLE = 'COSMOS_CONSUMPTION_DATABASE_NAME'
MASTER_PROJECTION_RELATIVE_PATH = 'master-projection/material.zip'


class AdaPersistenceMode(StrEnum):
    LOCAL = 'local'
    DURABLE = 'durable'


class AdaGenericSettings(WebSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file='.env',
        env_file_encoding='utf-8',
        env_prefix='',
        extra='ignore',
        frozen=True,
        validate_default=True,
    )

    application_namespace: str = Field(
        default='conciencia_situacional',
        validation_alias=APPLICATION_NAMESPACE_VARIABLE,
    )
    persistence_mode: AdaPersistenceMode = Field(
        default=AdaPersistenceMode.LOCAL,
        validation_alias=PERSISTENCE_MODE_VARIABLE,
    )
    tool_namespace: str = Field(validation_alias=TOOL_NAMESPACE_VARIABLE)
    tool_local_base_root: Path = Field(
        default=Path('.runtime/ada'),
        validation_alias=TOOL_LOCAL_BASE_ROOT_VARIABLE,
    )
    tool_source_blob_container_name: str | None = Field(
        default=None,
        validation_alias=TOOL_SOURCE_BLOB_CONTAINER_VARIABLE,
    )
    tool_source_blob_connection_string: SecretStr | None = Field(
        default=None,
        validation_alias=TOOL_SOURCE_BLOB_CONNECTION_STRING_VARIABLE,
    )
    tool_source_blob_account_url: str | None = Field(
        default=None,
        validation_alias=TOOL_SOURCE_BLOB_ACCOUNT_URL_VARIABLE,
    )
    tool_source_blob_sas_token: SecretStr | None = Field(
        default=None,
        validation_alias=TOOL_SOURCE_BLOB_SAS_TOKEN_VARIABLE,
    )
    tool_projection_cosmos_endpoint: str | None = Field(
        default=None,
        validation_alias=TOOL_PROJECTION_COSMOS_ENDPOINT_VARIABLE,
    )
    tool_projection_cosmos_key: SecretStr | None = Field(
        default=None,
        validation_alias=TOOL_PROJECTION_COSMOS_KEY_VARIABLE,
    )
    tool_projection_cosmos_database_name: str | None = Field(
        default=None,
        validation_alias=TOOL_PROJECTION_COSMOS_DATABASE_VARIABLE,
    )
    kpi_delivery_cosmos_endpoint: str | None = Field(
        default=None,
        validation_alias=KPI_DELIVERY_COSMOS_ENDPOINT_VARIABLE,
    )
    kpi_delivery_cosmos_key: SecretStr | None = Field(
        default=None,
        validation_alias=KPI_DELIVERY_COSMOS_KEY_VARIABLE,
    )
    kpi_delivery_cosmos_database_name: str | None = Field(
        default=None,
        validation_alias=KPI_DELIVERY_COSMOS_DATABASE_VARIABLE,
    )

    @model_validator(mode='before')
    @classmethod
    def infer_durable_persistence(cls, values: object) -> object:
        if not isinstance(values, Mapping) or PERSISTENCE_MODE_VARIABLE in values:
            return values
        durable_names = (
            TOOL_SOURCE_BLOB_CONTAINER_VARIABLE,
            TOOL_SOURCE_BLOB_CONNECTION_STRING_VARIABLE,
            TOOL_SOURCE_BLOB_ACCOUNT_URL_VARIABLE,
            TOOL_SOURCE_BLOB_SAS_TOKEN_VARIABLE,
            TOOL_PROJECTION_COSMOS_ENDPOINT_VARIABLE,
            TOOL_PROJECTION_COSMOS_KEY_VARIABLE,
            TOOL_PROJECTION_COSMOS_DATABASE_VARIABLE,
        )
        if not any(values.get(name) not in (None, '') for name in durable_names):
            return values
        copied = dict(values)
        copied[PERSISTENCE_MODE_VARIABLE] = AdaPersistenceMode.DURABLE.value
        return copied

    @property
    def tool_source_provider(self) -> ToolSourceProvider:
        return (
            ToolSourceProvider.BLOB
            if self.persistence_mode is AdaPersistenceMode.DURABLE
            else ToolSourceProvider.LOCAL
        )

    @property
    def tool_projection_provider(self) -> ToolProjectionProvider:
        return (
            ToolProjectionProvider.COSMOS
            if self.persistence_mode is AdaPersistenceMode.DURABLE
            else ToolProjectionProvider.LOCAL
        )

    @model_validator(mode='after')
    def validate_provider_requirements(self) -> Self:
        if self.persistence_mode is AdaPersistenceMode.DURABLE:
            if self.tool_source_blob_container_name is None:
                raise ValueError(f'{TOOL_SOURCE_BLOB_CONTAINER_VARIABLE} is required')
            has_connection_string = self.tool_source_blob_connection_string is not None
            has_account_url = self.tool_source_blob_account_url is not None
            has_sas_token = self.tool_source_blob_sas_token is not None
            if has_connection_string and (has_account_url or has_sas_token):
                raise ValueError(
                    'Blob Source must use connection string or SAS credentials, not both'
                )
            if not has_connection_string and not (has_account_url and has_sas_token):
                raise ValueError(
                    'Blob Source requires connection string or account URL plus SAS token'
                )
            required = (
                (TOOL_PROJECTION_COSMOS_ENDPOINT_VARIABLE, self.tool_projection_cosmos_endpoint),
                (TOOL_PROJECTION_COSMOS_KEY_VARIABLE, self.tool_projection_cosmos_key),
                (
                    TOOL_PROJECTION_COSMOS_DATABASE_VARIABLE,
                    self.tool_projection_cosmos_database_name,
                ),
            )
            missing = next((name for name, value in required if value is None), None)
            if missing is not None:
                raise ValueError(f'{missing} is required')

        kpi_connection = (
            (KPI_DELIVERY_COSMOS_ENDPOINT_VARIABLE, self.kpi_delivery_cosmos_endpoint),
            (KPI_DELIVERY_COSMOS_KEY_VARIABLE, self.kpi_delivery_cosmos_key),
            (KPI_DELIVERY_COSMOS_DATABASE_VARIABLE, self.kpi_delivery_cosmos_database_name),
        )
        if any(value is not None for _, value in kpi_connection):
            missing = next((name for name, value in kpi_connection if value is None), None)
            if missing is not None:
                raise ValueError(f'{missing} is required when KPI delivery Cosmos is configured')

        return self

    def storage_namespace(self) -> AdaStorageNamespace:
        return AdaStorageNamespace(
            application_namespace=self.application_namespace,
            tool_namespace=self.tool_namespace,
        )

    def local_base_root(self) -> Path:
        return self.tool_local_base_root.expanduser().resolve()

    def master_projection_local_path(self) -> Path:
        return self.storage_namespace().local_application_root(
            self.local_base_root()
        ) / MASTER_PROJECTION_RELATIVE_PATH

    def master_projection_blob_name(self) -> str:
        return self.storage_namespace().application_blob_name(MASTER_PROJECTION_RELATIVE_PATH)

    def tool_persistence_settings(self) -> ToolPersistenceSettings:
        return ToolPersistenceSettings(
            namespace=self.storage_namespace(),
            source_provider=self.tool_source_provider,
            projection_provider=self.tool_projection_provider,
            local_base_root=(
                self.local_base_root()
                if self.persistence_mode is AdaPersistenceMode.LOCAL
                else None
            ),
            blob_container_name=(
                self.tool_source_blob_container_name
                if self.persistence_mode is AdaPersistenceMode.DURABLE
                else None
            ),
            cosmos_container_name=(
                TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name
                if self.persistence_mode is AdaPersistenceMode.DURABLE
                else None
            ),
        )

    def storage_settings(self) -> StorageSettings | None:
        if self.persistence_mode is not AdaPersistenceMode.DURABLE:
            return None
        connection_string = self.tool_source_blob_connection_string
        if connection_string is not None:
            credential = StorageConnectionStringCredential(connection_string.get_secret_value())
        else:
            account_url = self.tool_source_blob_account_url
            sas_token = self.tool_source_blob_sas_token
            if account_url is None or sas_token is None:
                raise RuntimeError('Blob Source credentials were not resolved')
            credential = StorageSasCredential(
                account_url=account_url,
                sas_token=sas_token.get_secret_value(),
                allow_insecure_http=self.environment.is_local,
            )
        return StorageSettings(credential=credential)

    def tool_projection_cosmos_settings(self) -> CosmosSettings | None:
        if self.persistence_mode is not AdaPersistenceMode.DURABLE:
            return None
        endpoint = self.tool_projection_cosmos_endpoint
        key = self.tool_projection_cosmos_key
        database_name = self.tool_projection_cosmos_database_name
        if endpoint is None or key is None or database_name is None:
            raise RuntimeError('Cosmos Projection settings were not resolved')
        return CosmosSettings(
            endpoint=endpoint,
            key=key.get_secret_value(),
            database_name=database_name,
            allow_insecure_http=self.environment.is_local,
        )

    def kpi_delivery_cosmos_settings(self) -> CosmosSettings | None:
        endpoint = self.kpi_delivery_cosmos_endpoint
        key = self.kpi_delivery_cosmos_key
        database_name = self.kpi_delivery_cosmos_database_name
        if endpoint is None and key is None and database_name is None:
            return None
        if endpoint is None or key is None or database_name is None:
            raise RuntimeError('KPI Delivery Cosmos settings were not resolved')
        return CosmosSettings(
            endpoint=endpoint,
            key=key.get_secret_value(),
            database_name=database_name,
            allow_insecure_http=self.environment.is_local,
        )

    def kpi_delivery_reader_settings(self) -> CosmosKpiDeliveryReaderSettings:
        return CosmosKpiDeliveryReaderSettings()
