from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import replace
from functools import partial
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

from ada.contracts.tools.sources import (
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
)
from ada.web.alarms.baseline_projection import AlarmBaselineProjection
from ada.web.alarms.management_summary import AlarmManagementSummaryState
from ada.web.alarms.status import AlarmStatusState
from ada.web.application.generic.composition import (
    AdaApplicationComposition,
    create_local_operational_composition,
)
from ada.web.application.generic.descriptor import (
    GENERIC_APPLICATION_DESCRIPTOR,
    AdaApplicationDescriptor,
)
from ada.web.application.generic.operational_render import (
    validate_operational_render_application_binding,
)
from ada.web.branding import BrandingConfiguration
from ada.web.branding.web import BrandingAssetSet, OperationalBrandState, resolve_branding_assets
from ada.web.content_state import ContentState, ContentStateDependency
from ada.web.operational_render_binding import OperationalRenderBinding
from ada.web.operational_state import resolve_ada_operational_state
from ada.web.shell.navigation import AdaNavigationView
from ada.web.time_status.runtime import (
    TimeStatusRuntimeBinding,
    create_time_status_runtime_module,
)
from ada.web.ui.content_state import ContentStatePresentationMode
from ada.web.ui.global_indicator import GlobalIndicatorCollection
from ada.web.ui.time_status import TimeStatusDetailState
from atlanticus.web.assets import AssetLayer
from atlanticus.web.errors import WebDefinitionError
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.pwa import WebFavicon, WebPwaDefinition, WebPwaIcon, create_web_pwa_module

_LOGGER = logging.getLogger(__name__)
_PWA_ICON_LAYER = AssetLayer(
    name='ada_application_pwa',
    load_order=205,
    package='ada.web.application.generic',
    resource_directory='resources/pwa',
)


def _pwa_icons() -> tuple[WebPwaIcon, ...]:
    root = f'/assets/{_PWA_ICON_LAYER.target_name}/img'
    return (
        WebPwaIcon(src=f'{root}/ada-pwa-icon-192.png', sizes='192x192'),
        WebPwaIcon(src=f'{root}/ada-pwa-icon-512.png', sizes='512x512'),
        WebPwaIcon(
            src=f'{root}/ada-pwa-maskable-512.png',
            sizes='512x512',
            purpose=('maskable',),
        ),
    )


def _resolve_browser_favicon(layer: AssetLayer | None) -> WebFavicon | None:
    if layer is None:
        return None
    try:
        resource = files(layer.package).joinpath(layer.resource_directory, 'img', 'favicon.png')
    except (ModuleNotFoundError, TypeError) as error:
        raise WebDefinitionError('Application favicon package could not be resolved') from error
    if not resource.is_file():
        raise WebDefinitionError('Application favicon resource img/favicon.png does not exist')
    content = resource.read_bytes()
    if (
        len(content) < 33
        or int.from_bytes(content[8:12], 'big') != 13
        or content[:8] != b'\x89PNG\r\n\x1a\n'
        or content[12:16] != b'IHDR'
        or int.from_bytes(content[16:20], 'big') != 32
        or int.from_bytes(content[20:24], 'big') != 32
    ):
        raise WebDefinitionError('Application favicon must be a 32x32 PNG image')
    revision = hashlib.sha256(content).hexdigest()[:12]
    return WebFavicon(src=f'/assets/{layer.target_name}/img/favicon.png?v={revision}')


def _resolve_publications_root(descriptor: AdaApplicationDescriptor) -> Path:
    configured = os.getenv('APPLICATION_PUBLICATIONS_ROOT')
    if configured is None or not configured.strip():
        return descriptor.default_publications_root
    return Path(configured).expanduser().resolve()


def create_application_definition(
    *,
    application_descriptor: AdaApplicationDescriptor | None = None,
    composition: AdaApplicationComposition | None = None,
    operational_render_binding: OperationalRenderBinding | None = None,
    tool_display_name: str | None = None,
    branding_configuration: BrandingConfiguration | None = None,
    navigation_view: AdaNavigationView | None = None,
    global_indicators: GlobalIndicatorCollection | None = None,
    global_indicators_content_state: ContentState = ContentState.READY,
    content_state_presentation_mode: ContentStatePresentationMode = (
        ContentStatePresentationMode.NORMAL
    ),
    content_state_dependencies: tuple[ContentStateDependency, ...] = (),
    alarm_management_summary: AlarmManagementSummaryState | None = None,
    alarm_status: AlarmStatusState | None = None,
    alarm_baseline_projection: AlarmBaselineProjection | None = None,
    source_consumption: ToolSourceConsumption | None = None,
    source_operational_participation: ToolSourceOperationalParticipation | None = None,
    time_status_detail: TimeStatusDetailState | None = None,
) -> WebApplicationDefinition:
    _validate_content_state_presentation_mode(content_state_presentation_mode)
    if application_descriptor is not None and not isinstance(
        application_descriptor,
        AdaApplicationDescriptor,
    ):
        raise TypeError('application_descriptor must be AdaApplicationDescriptor')
    if alarm_baseline_projection is not None and not isinstance(
        alarm_baseline_projection,
        AlarmBaselineProjection,
    ):
        raise TypeError('Generic Application requires AlarmBaselineProjection value')
    if content_state_presentation_mode is ContentStatePresentationMode.AUTHORING:
        _LOGGER.info('Content State presentation override is active: authoring')
    resolved_descriptor = application_descriptor or GENERIC_APPLICATION_DESCRIPTOR
    application_version = version(resolved_descriptor.distribution_name)
    resolved_branding_configuration = branding_configuration or BrandingConfiguration()
    branding_assets = resolve_branding_assets(resolved_branding_configuration)
    operational_brand = OperationalBrandState(
        context_name=tool_display_name,
        logo_src=branding_assets.operational_logo_src,
    )
    resolved_global_indicators = global_indicators or GlobalIndicatorCollection(())
    time_status_binding = _resolve_time_status_binding(
        source_consumption=source_consumption,
        source_operational_participation=source_operational_participation,
        time_status_detail=time_status_detail,
    )
    operational_state = resolve_ada_operational_state(
        has_global_indicators=bool(len(resolved_global_indicators)),
        content_state_dependencies=content_state_dependencies,
        source_consumption=source_consumption,
        source_operational_participation=source_operational_participation,
    )
    resolved_composition = composition or create_local_operational_composition(
        include_content_state=bool(len(resolved_global_indicators)),
        include_time_status=time_status_binding is not None,
    )
    validate_operational_render_application_binding(
        binding=operational_render_binding,
        body_factory=resolved_composition.operational_body_factory,
    )
    runtime_modules = (
        ()
        if time_status_binding is None
        else (create_time_status_runtime_module(time_status_binding),)
    )
    metadata = ApplicationMetadata(
        application_id=resolved_descriptor.application_id,
        display_name=resolved_descriptor.display_name,
        version=application_version,
    )
    pwa = WebPwaDefinition.from_application(
        metadata,
        short_name=resolved_descriptor.pwa_short_name or metadata.display_name,
        theme_color='#5B5C64',
        background_color='#FFFFFF',
        icons=_pwa_icons(),
        start_url='/',
        scope='/',
        browser_favicon=_resolve_browser_favicon(resolved_descriptor.favicon_asset_layer),
    )
    favicon_layers = (
        ()
        if resolved_descriptor.favicon_asset_layer is None
        else (resolved_descriptor.favicon_asset_layer,)
    )
    return WebApplicationDefinition(
        import_name=resolved_descriptor.import_name,
        metadata=metadata,
        publications_root=_resolve_publications_root(resolved_descriptor),
        layout=partial(
            resolved_composition.layout,
            operational_brand=operational_brand,
            navigation_view=_resolve_navigation_view(
                navigation_view,
                application_version=application_version,
                branding_assets=branding_assets,
            ),
            global_indicators=resolved_global_indicators,
            global_indicators_content_state=global_indicators_content_state,
            content_state_presentation_mode=content_state_presentation_mode,
            global_indicators_runtime_state=(operational_state.global_indicators_runtime_state),
            global_indicators_source_keys=operational_state.global_indicators_source_keys,
            alarm_management_summary=alarm_management_summary,
            alarm_status=alarm_status,
            alarm_baseline_projection=alarm_baseline_projection,
            tool_key=operational_state.tool_key,
            time_status_binding=time_status_binding,
            operational_render_binding=operational_render_binding,
            operational_body_factory=resolved_composition.operational_body_factory,
        ),
        modules=(*resolved_composition.modules, *runtime_modules, create_web_pwa_module(pwa)),
        asset_layers=(_PWA_ICON_LAYER, *favicon_layers),
        page_packages=resolved_composition.page_packages,
    )


def _resolve_time_status_binding(
    *,
    source_consumption: ToolSourceConsumption | None,
    source_operational_participation: ToolSourceOperationalParticipation | None,
    time_status_detail: TimeStatusDetailState | None,
) -> TimeStatusRuntimeBinding | None:
    if source_operational_participation is None:
        if time_status_detail is not None:
            raise ToolSourceOperationalParticipationValidationError(
                'Time Status detail requires ToolSourceOperationalParticipation'
            )
        return None
    if source_consumption is None:
        raise ToolSourceConsumptionValidationError('Time Status runtime requires ToolSourceConsumption')
    return TimeStatusRuntimeBinding(
        consumption=source_consumption,
        participation=source_operational_participation,
        detail=time_status_detail,
    )


def _validate_content_state_presentation_mode(
    presentation_mode: ContentStatePresentationMode,
) -> None:
    if not isinstance(presentation_mode, ContentStatePresentationMode):
        raise TypeError('Generic Application requires ContentStatePresentationMode value')


def _resolve_navigation_view(
    view: AdaNavigationView | None,
    *,
    application_version: str,
    branding_assets: BrandingAssetSet,
) -> AdaNavigationView:
    resolved = view or AdaNavigationView()
    return replace(
        resolved,
        brand_logo_src=(resolved.brand_logo_src or branding_assets.navigation_logo_src),
        footer_logo_src=resolved.footer_logo_src or branding_assets.partner_logo_src,
        application_version=resolved.application_version or application_version,
    )
