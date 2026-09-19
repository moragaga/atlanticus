# Superficie pública alineada con el contrato vigente, sin exports legacy.
from atlanticus.web.navigation.configuration.exchange import (
    build_navigation_configuration_digest,
    decode_navigation_configuration_import,
)
from atlanticus.web.navigation.configuration.models import (
    NavigationConfigurationCatalog,
    NavigationGroupConfiguration,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.configuration.profiles import NavigationProfileCatalogProvider
from atlanticus.web.navigation.configuration.projection_record import (
    NAVIGATION_PROJECTION_DOCUMENT_TYPE,
    NAVIGATION_PROJECTION_SCHEMA_VERSION,
    navigation_projection_from_document,
    navigation_projection_to_document,
)
from atlanticus.web.navigation.configuration.runtime import (
    create_projected_navigation_definition_provider,
    create_projected_navigation_module,
)
from atlanticus.web.navigation.configuration.source_projection import (
    NavigationProjectionBuilder,
    NavigationProjectionIssue,
    NavigationProjectionIssueLevel,
    NavigationProjectionValidator,
    create_navigation_profile_catalog_validator,
    create_navigation_projection_service,
)
from atlanticus.web.navigation.configuration.source_release import (
    NAVIGATION_SOURCE_DOCUMENT_TYPE,
    NAVIGATION_SOURCE_RESOURCE_PATH,
    NAVIGATION_SOURCE_SCHEMA_VERSION,
    NavigationSourceCodec,
    NavigationSourcePayload,
    NavigationSourceRelease,
    NavigationSourceService,
)

__all__ = [
    'NAVIGATION_PROJECTION_DOCUMENT_TYPE',
    'NAVIGATION_PROJECTION_SCHEMA_VERSION',
    'NAVIGATION_SOURCE_DOCUMENT_TYPE',
    'NAVIGATION_SOURCE_RESOURCE_PATH',
    'NAVIGATION_SOURCE_SCHEMA_VERSION',
    'NavigationConfigurationCatalog',
    'NavigationGroupConfiguration',
    'NavigationLinkConfiguration',
    'NavigationProfileCatalogProvider',
    'NavigationProjectionBuilder',
    'NavigationProjectionIssue',
    'NavigationProjectionIssueLevel',
    'NavigationProjectionValidator',
    'NavigationSourceCodec',
    'NavigationSourcePayload',
    'NavigationSourceRelease',
    'NavigationSourceService',
    'build_navigation_configuration_digest',
    'create_navigation_profile_catalog_validator',
    'create_navigation_projection_service',
    'create_projected_navigation_definition_provider',
    'create_projected_navigation_module',
    'decode_navigation_configuration_import',
    'navigation_projection_from_document',
    'navigation_projection_to_document',
]
