from __future__ import annotations

from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from ada.web.kpis.collector import (
    DEFAULT_KPI_LATEST_DELIVERY_CONTAINER,
    DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER,
    CosmosKpiDeliveryReaderSettings,
)
from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.persistence import (
    ToolPersistenceSettings,
    ToolProjectionProvider,
    ToolSourceProvider,
)
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
    StorageSasCredential,
    StorageSettings,
)
from atlanticus.web.configuration import WebSettings

# Tool persistence conserva nombres propios porque Source y Projection pueden usar conexiones distintas.
APPLICATION_NAMESPACE_VARIABLE = 'ADA_APPLICATION_NAMESPACE'
TOOL_NAMESPACE_VARIABLE = 'ADA_TOOL_NAMESPACE'
TOOL_SOURCE_PROVIDER_VARIABLE = 'ADA_TOOL_SOURCE_PROVIDER'
TOOL_PROJECTION_PROVIDER_VARIABLE = 'ADA_TOOL_PROJECTION_PROVIDER'
TOOL_LOCAL_BASE_ROOT_VARIABLE = 'ADA_TOOL_LOCAL_BASE_ROOT'
TOOL_SOURCE_BLOB_CONTAINER_VARIABLE = 'ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME'
TOOL_SOURCE_BLOB_CONNECTION_STRING_VARIABLE = 'ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING'
TOOL_SOURCE_BLOB_ACCOUNT_URL_VARIABLE = 'ADA_TOOL_SOURCE_BLOB_ACCOUNT_URL'
TOOL_SOURCE_BLOB_SAS_TOKEN_VARIABLE = 'ADA_TOOL_SOURCE_BLOB_SAS_TOKEN'
TOOL_PROJECTION_COSMOS_ENDPOINT_VARIABLE = 'ADA_TOOL_PROJECTION_COSMOS_ENDPOINT'
TOOL_PROJECTION_COSMOS_KEY_VARIABLE = 'ADA_TOOL_PROJECTION_COSMOS_KEY'
TOOL_PROJECTION_COSMOS_DATABASE_VARIABLE = 'ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME'
TOOL_PROJECTION_COSMOS_CONTAINER_VARIABLE = 'ADA_TOOL_PROJECTION_COSMOS_CONTAINER_NAME'

# KPI Delivery consume la conexión Cosmos de consumo ya usada por los procesos productores.
KPI_DELIVERY_COSMOS_ENDPOINT_VARIABLE = 'COSMOS_CONSUMPTION_ENDPOINT'
KPI_DELIVERY_COSMOS_KEY_VARIABLE = 'COSMOS_CONSUMPTION_KEY'
KPI_DELIVERY_COSMOS_DATABASE_VARIABLE = 'COSMOS_CONSUMPTION_DATABASE_NAME'
KPI_LATEST_DELIVERY_CONTAINER_VARIABLE = 'KPI_LATEST_DELIVERY_CONTAINER'
KPI_TIMESERIES_DELIVERY_CONTAINER_VARIABLE = 'KPI_TIMESERIES_DELIVERY_CONTAINER'


class AdaGenericSettings(WebSettings):
    # .env sigue siendo una entrada local; las variables de proceso mantienen precedencia.
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
    tool_namespace: str = Field(validation_alias=TOOL_NAMESPACE_VARIABLE)
    tool_source_provider: ToolSourceProvider = Field(validation_alias=TOOL_SOURCE_PROVIDER_VARIABLE)
    tool_projection_provider: ToolProjectionProvider = Field(
        validation_alias=TOOL_PROJECTION_PROVIDER_VARIABLE
    )
    tool_local_base_root: Path | None = Field(
        default=None,
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
    tool_projection_cosmos_container_name: str | None = Field(
        default=None,
        validation_alias=TOOL_PROJECTION_COSMOS_CONTAINER_VARIABLE,
    )
    # La conexión KPI es opcional como capability completa: ausente no impide levantar la Web.
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
    # Los nombres de containers heredan los defaults congelados por el Collector.
    kpi_latest_delivery_container_name: str = Field(
        default=DEFAULT_KPI_LATEST_DELIVERY_CONTAINER,
        validation_alias=KPI_LATEST_DELIVERY_CONTAINER_VARIABLE,
    )
    kpi_timeseries_delivery_container_name: str = Field(
        default=DEFAULT_KPI_TIMESERIES_DELIVERY_CONTAINER,
        validation_alias=KPI_TIMESERIES_DELIVERY_CONTAINER_VARIABLE,
    )

    @model_validator(mode='after')
    def validate_provider_requirements(self) -> Self:
        if (
            self.tool_source_provider is ToolSourceProvider.LOCAL
            or self.tool_projection_provider is ToolProjectionProvider.LOCAL
        ):
            if self.tool_local_base_root is None:
                raise ValueError(f'{TOOL_LOCAL_BASE_ROOT_VARIABLE} is required by a local provider')
            if not self.tool_local_base_root.expanduser().is_absolute():
                raise ValueError(f'{TOOL_LOCAL_BASE_ROOT_VARIABLE} must be an absolute path')

        if self.tool_source_provider is ToolSourceProvider.BLOB:
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

        if self.tool_projection_provider is ToolProjectionProvider.COSMOS:
            required = (
                (TOOL_PROJECTION_COSMOS_ENDPOINT_VARIABLE, self.tool_projection_cosmos_endpoint),
                (TOOL_PROJECTION_COSMOS_KEY_VARIABLE, self.tool_projection_cosmos_key),
                (
                    TOOL_PROJECTION_COSMOS_DATABASE_VARIABLE,
                    self.tool_projection_cosmos_database_name,
                ),
                (
                    TOOL_PROJECTION_COSMOS_CONTAINER_VARIABLE,
                    self.tool_projection_cosmos_container_name,
                ),
            )
            missing = next((name for name, value in required if value is None), None)
            if missing is not None:
                raise ValueError(f'{missing} is required')

        # KPI Delivery se habilita sólo cuando la conexión está completa; una configuración parcial sí es inválida.
        kpi_connection = (
            (KPI_DELIVERY_COSMOS_ENDPOINT_VARIABLE, self.kpi_delivery_cosmos_endpoint),
            (KPI_DELIVERY_COSMOS_KEY_VARIABLE, self.kpi_delivery_cosmos_key),
            (KPI_DELIVERY_COSMOS_DATABASE_VARIABLE, self.kpi_delivery_cosmos_database_name),
        )
        if any(value is not None for _, value in kpi_connection):
            missing = next((name for name, value in kpi_connection if value is None), None)
            if missing is not None:
                raise ValueError(
                    f'{missing} is required when KPI delivery Cosmos is configured'
                )

        return self

    def tool_persistence_settings(self) -> ToolPersistenceSettings:
        return ToolPersistenceSettings(
            namespace=AdaStorageNamespace(
                application_namespace=self.application_namespace,
                tool_namespace=self.tool_namespace,
            ),
            source_provider=self.tool_source_provider,
            projection_provider=self.tool_projection_provider,
            local_base_root=(
                self.tool_local_base_root.expanduser()
                if self.tool_local_base_root is not None
                else None
            ),
            blob_container_name=self.tool_source_blob_container_name,
            cosmos_container_name=self.tool_projection_cosmos_container_name,
        )

    def storage_settings(self) -> StorageSettings | None:
        if self.tool_source_provider is not ToolSourceProvider.BLOB:
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
        # Este cliente existe sólo para resolver Tool Projection y el bootstrap lo cierra después de esa lectura.
        if self.tool_projection_provider is not ToolProjectionProvider.COSMOS:
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
        # Ausencia total significa capability Collector no configurada, no fallo global de Web.
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
        # Los containers Latest y Timeseries siguen siendo configurables sin cambiar el contrato de documentos.
        return CosmosKpiDeliveryReaderSettings(
            latest_container_name=self.kpi_latest_delivery_container_name,
            timeseries_container_name=self.kpi_timeseries_delivery_container_name,
        )
