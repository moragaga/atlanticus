from __future__ import annotations

import inspect
import json
from importlib.metadata import version as distribution_version

import pytest

from ada.contracts.tools.sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
)
from ada.web.alarms.baseline_surface import ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER
from ada.web.alarms.management_summary import (
    ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER,
    AlarmManagementSummaryArea,
    AlarmManagementSummarySegmentState,
    AlarmManagementSummaryState,
    AlarmManagementSummaryTone,
)
from ada.web.alarms.status import ADA_ALARM_STATUS_ASSET_LAYER, AlarmStatusState
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.runtime import create_application_runtime
from ada.web.branding.web import (
    ADA_BRANDING_ASSET_LAYER,
    DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
    DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC,
    DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
)
from ada.web.content_state import ContentState, ContentStateDependency
from ada.web.shell.header import ADA_OPERATIONAL_HEADER_ASSET_LAYER
from ada.web.shell.navigation import ADA_NAVIGATION_ASSET_LAYER, AdaNavigationView
from ada.web.time_status.runtime import (
    TIME_STATUS_RUNTIME_HOST_TYPE,
    TimeStatusRuntimeBinding,
)
from ada.web.ui.content_state import (
    ADA_CONTENT_STATE_ASSET_LAYER,
    ContentStatePresentationMode,
)
from ada.web.ui.core import ADA_UI_ASSET_LAYER
from ada.web.ui.display_status import ADA_DISPLAY_STATUS_ASSET_LAYER
from ada.web.ui.global_indicator import (
    ADA_GLOBAL_INDICATOR_ASSET_LAYER,
    GlobalIndicatorCollection,
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
)
from ada.web.ui.time_status import (
    ADA_TIME_STATUS_ASSET_LAYER,
    TimeStatusDetailSourceState,
    TimeStatusDetailState,
)
from atlanticus.web.bootstrap import BOOTSTRAP_FOUNDATION_ASSET_LAYER
from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY
from atlanticus.web.navigation.api import (
    NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
    NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY,
    NavigationDefinitionProvider,
)


def test_definition_composes_current_ada_web_capabilities() -> None:
    definition = create_application_definition()

    assert definition.metadata.application_id == 'ada-generic-application'
    assert definition.metadata.display_name == 'ADA'
    assert definition.metadata.version == distribution_version('ada-generic-application')
    assert tuple(module.name for module in definition.modules) == (
        'bootstrap-foundation',
        'ada-ui',
        'ada-display-status',
        'ada-global-indicator',
        'ada-alarm-baseline-surface',
        'ada-alarm-management-summary',
        'ada-alarm-status',
        'ada-branding',
        'navigation',
        'navigation-authorization',
        'ada-navigation',
        'ada-operational-header',
        'ada-session',
        'ada-wake-lock',
        'ada-page-readiness',
    )
    assert definition.page_packages == ('ada.web.application.generic.pages',)


def test_runtime_starts_locally_with_operational_header(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime()
    client = runtime.server.test_client()

    assert runtime.environment.value == 'local'
    assert client.get('/health/live').status_code == 200
    assert client.get('/health/ready').status_code == 200
    assert client.get('/').status_code == 200
    layout_response = client.get('/_dash-layout')
    assert layout_response.status_code == 200
    payload = json.dumps(layout_response.get_json(), ensure_ascii=False)
    assert 'operational_header' in payload
    assert 'global_indicators' in payload
    assert 'alarm_management' in payload
    assert 'alarm_status' in payload
    assert 'ada-navigation-desktop-toggle' in payload
    assert 'ada-navigation-mobile-toggle' in payload
    assert 'ada-navigation-offcanvas' in payload
    assert 'ada-operational-header__primary' in payload
    assert 'ada-navigation__anchor-host' not in payload
    assert 'Visitante' in payload
    assert 'Asistente de Decisiones Ágiles' in payload
    assert DEFAULT_OPERATIONAL_BRAND_LOGO_SRC in payload
    assert DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC in payload
    assert DEFAULT_PELAMBRES_BRAND_LOGO_SRC in payload
    assert f'Versión {distribution_version("ada-generic-application")}' in payload
    assert not runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    assert runtime.services.contains(NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY)
    assert any(
        entry.startswith(f'{BOOTSTRAP_FOUNDATION_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_UI_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_DISPLAY_STATUS_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_GLOBAL_INDICATOR_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_ALARM_STATUS_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_BRANDING_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_NAVIGATION_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_OPERATIONAL_HEADER_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )

    provider = runtime.services.require(
        NAVIGATION_DEFINITION_PROVIDER_SERVICE_KEY,
        NavigationDefinitionProvider,
    )
    navigation = provider.current()
    assert navigation.home_route_key is None
    assert navigation.links == ()


def test_global_indicators_mount_only_when_explicitly_injected(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    collection = GlobalIndicatorCollection(
        indicators=(
            GlobalIndicatorState(
                key='test_indicator',
                label='Indicador de prueba',
                unit='u',
                measurements=(
                    GlobalIndicatorMeasurementState(
                        key='turno',
                        label='Turno',
                        actual_value='10',
                        plan_value='12',
                        actual_kpi_key='test_kpi_shift_actual',
                        plan_kpi_key='test_kpi_shift_plan',
                    ),
                    GlobalIndicatorMeasurementState(
                        key='dia',
                        label='Día',
                        actual_value='20',
                        plan_value='24',
                        actual_kpi_key='test_kpi_day_actual',
                        plan_kpi_key='test_kpi_day_plan',
                    ),
                ),
                last_measurement=GlobalIndicatorLastMeasurementState(
                    '22', actual_kpi_key='test_kpi_latest'
                ),
            ),
        )
    )
    runtime = create_application_runtime(global_indicators=collection)
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert 'global-indicators' in payload
    assert 'test_indicator' in payload
    assert 'data-kpi-inspection-key' in payload
    assert 'test_kpi_shift_actual' in payload
    assert 'test_kpi_shift_plan' in payload
    assert 'test_kpi_latest' in payload
    assert 'Indicador de prueba' in payload
    assert 'Última medición' in payload
    assert '22' in payload
    assert 'data-slot-empty' in payload
    assert 'data-ada-component-key' in payload
    assert 'data-ada-content-state' in payload
    assert 'global_indicators' in payload
    assert any(
        entry.startswith(f'{ADA_CONTENT_STATE_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )


def test_content_state_assets_are_not_loaded_without_global_indicators() -> None:
    definition = create_application_definition()

    assert 'ada-content-state' not in tuple(module.name for module in definition.modules)


def test_global_indicators_construction_state_wraps_real_component_without_hiding_kpi_contract(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    collection = GlobalIndicatorCollection(
        indicators=(
            GlobalIndicatorState(
                key='construction_indicator',
                label='Indicador en construcción',
                unit='u',
                measurements=(
                    GlobalIndicatorMeasurementState(
                        key='turno',
                        label='Turno',
                        actual_value='10',
                        plan_value='12',
                        actual_kpi_key='construction_kpi_actual',
                        plan_kpi_key='construction_kpi_plan',
                    ),
                    GlobalIndicatorMeasurementState(
                        key='dia',
                        label='Día',
                        actual_value='20',
                        plan_value='24',
                        actual_kpi_key='construction_kpi_day_actual',
                        plan_kpi_key='construction_kpi_day_plan',
                    ),
                ),
            ),
        )
    )
    runtime = create_application_runtime(
        global_indicators=collection,
        global_indicators_content_state=ContentState.CONSTRUCTION,
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert 'data-ada-component-key' in payload
    assert 'global_indicators' in payload
    assert 'data-ada-content-state' in payload
    assert 'construction' in payload
    assert 'En construcción' in payload
    assert 'data-kpi-inspection-key' in payload
    assert 'construction_kpi_actual' in payload
    assert 'construction_kpi_plan' in payload
    assert 'construction_kpi_day_actual' in payload
    assert 'construction_kpi_day_plan' in payload
    assert 'Indicador en construcción' in payload
    assert 'ada-content-state__overlay' in payload
    assert any(
        entry.startswith(f'{ADA_CONTENT_STATE_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )


def test_alarm_management_summary_mounts_only_when_explicitly_injected(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    summary = AlarmManagementSummaryState(
        segments=(
            AlarmManagementSummarySegmentState(
                area=AlarmManagementSummaryArea.MINE,
                group=1,
                management_percentage=72,
                tone=AlarmManagementSummaryTone.ATTENTION,
            ),
            AlarmManagementSummarySegmentState(
                area=AlarmManagementSummaryArea.PLANT,
                group=3,
                management_percentage=88,
            ),
        )
    )
    runtime = create_application_runtime(alarm_management_summary=summary)
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert 'alarm_management' in payload
    assert 'ada-alarm-management-summary' in payload
    assert 'Grupo Mina' in payload
    assert 'Gestión Mina' in payload
    assert '72%' in payload
    assert 'Grupo Planta' in payload
    assert '88%' in payload
    assert 'attention' in payload


def test_alarm_status_mounts_only_when_explicitly_injected(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime(
        alarm_status=AlarmStatusState(active_count=12, managed_count=7)
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert 'alarm_status' in payload
    assert 'ada-alarm-status' in payload
    assert 'Activas' in payload
    assert 'Gestionadas' in payload
    assert '12' in payload
    assert '7' in payload
    assert 'data-alarm-status-action' in payload
    assert 'active' in payload
    assert 'managed' in payload


def test_tool_name_and_navigation_view_are_injected_without_shell_hardcoding(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime(
        tool_display_name='Operaciones Integradas',
        navigation_view=AdaNavigationView(
            title='ADA',
            subtitle='Navegación de la herramienta',
        ),
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert 'Operaciones Integradas' in payload
    assert 'Navegación de la herramienta' in payload


def test_public_package_exposes_runtime_factory() -> None:
    from ada.web.application.generic import create_application_runtime

    assert callable(create_application_runtime)


def _source_configuration(
    *,
    tool_key: str = 'process',
    with_dispatch: bool = False,
    additional_observation_source_keys: tuple[str, ...] = (),
    pi_pre_degrading_after_seconds: int = 200,
    pi_degrading_after_seconds: int = 300,
) -> tuple[ToolSourceConsumption, ToolSourceOperationalParticipation]:
    source_keys = ['pi']
    control_sources = [
        SourceControlPolicy(
            source_key='pi',
            pre_degrading_after_seconds=pi_pre_degrading_after_seconds,
            degrading_after_seconds=pi_degrading_after_seconds,
        )
    ]
    if with_dispatch:
        source_keys.append('dispatch')
        control_sources.append(
            SourceControlPolicy(
                source_key='dispatch',
                pre_degrading_after_seconds=400,
                degrading_after_seconds=600,
            )
        )
    source_keys.extend(additional_observation_source_keys)
    return (
        ToolSourceConsumption(tool_key=tool_key, source_keys=tuple(source_keys)),
        ToolSourceOperationalParticipation(
            tool_key=tool_key,
            control_sources=tuple(control_sources),
            additional_observation_source_keys=additional_observation_source_keys,
        ),
    )


def _time_status_detail() -> TimeStatusDetailState:
    return TimeStatusDetailState(
        sources=(
            TimeStatusDetailSourceState(
                key='blockgrade',
                label='BlockGrade',
                value='Error',
            ),
        )
    )


def test_time_status_mounts_runtime_host_from_tool_source_configuration(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')
    consumption, participation = _source_configuration(
        additional_observation_source_keys=('blockgrade',)
    )

    runtime = create_application_runtime(
        source_consumption=consumption,
        source_operational_participation=participation,
        time_status_detail=_time_status_detail(),
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert 'time_status' in payload
    assert TIME_STATUS_RUNTIME_HOST_TYPE in payload
    assert 'data-ada-time-status-runtime-host' in payload
    assert 'data-ada-time-status-tool-key' in payload
    assert 'process' in payload
    assert 'BlockGrade' in payload
    assert any(
        entry.startswith(f'{ADA_TIME_STATUS_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_TIME_STATUS_ASSET_LAYER.target_name}/js/')
        for entry in runtime.assets.js_entries
    )


def test_time_status_assets_are_not_loaded_without_operational_participation() -> None:
    definition = create_application_definition()

    module_names = tuple(module.name for module in definition.modules)
    assert 'ada-time-status' not in module_names
    assert 'ada-time-status-runtime' not in module_names


def test_time_status_definition_adds_ui_and_runtime_modules_from_control_sources() -> None:
    consumption, participation = _source_configuration()

    definition = create_application_definition(
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    module_names = tuple(module.name for module in definition.modules)

    assert 'ada-time-status' in module_names
    assert 'ada-time-status-runtime' in module_names


def test_time_status_without_additional_sources_preserves_explicit_empty_detail(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')
    consumption, participation = _source_configuration()

    runtime = create_application_runtime(
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert 'Sin fuentes adicionales' in payload
    assert 'Esta herramienta no consume fuentes de datos adicionales.' in payload


def test_generic_application_public_api_no_longer_accepts_legacy_time_status_snapshot() -> None:
    definition_signature = inspect.signature(create_application_definition)
    runtime_signature = inspect.signature(create_application_runtime)

    assert 'time_status_summary' not in definition_signature.parameters
    assert 'time_status_summary' not in runtime_signature.parameters
    assert 'time_status_snapshot' not in definition_signature.parameters
    assert 'time_status_snapshot' not in runtime_signature.parameters
    assert 'source_operational_participation' in definition_signature.parameters


def test_control_thresholds_are_owned_by_tool_operational_participation() -> None:
    consumption, participation = _source_configuration(
        pi_pre_degrading_after_seconds=200,
        pi_degrading_after_seconds=300,
    )

    definition = create_application_definition(
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    binding = definition.layout.keywords['time_status_binding']

    assert isinstance(binding, TimeStatusRuntimeBinding)
    pi_policy = binding.participation.control_policy('pi')
    assert pi_policy is not None
    assert pi_policy.pre_degrading_after_seconds == 200
    assert pi_policy.degrading_after_seconds == 300


def test_changing_tool_thresholds_changes_runtime_binding_without_other_policy_input() -> None:
    consumption, participation = _source_configuration(
        pi_pre_degrading_after_seconds=250,
        pi_degrading_after_seconds=350,
    )

    definition = create_application_definition(
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    binding = definition.layout.keywords['time_status_binding']
    pi_policy = binding.participation.control_policy('pi')

    assert pi_policy is not None
    assert pi_policy.pre_degrading_after_seconds == 250
    assert pi_policy.degrading_after_seconds == 350


def test_dispatch_is_absent_when_not_configured() -> None:
    consumption, participation = _source_configuration()

    definition = create_application_definition(
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    binding = definition.layout.keywords['time_status_binding']

    assert binding.participation.control_policy('dispatch') is None


def test_dispatch_uses_its_own_optional_control_thresholds_when_configured() -> None:
    consumption, participation = _source_configuration(with_dispatch=True)

    definition = create_application_definition(
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    binding = definition.layout.keywords['time_status_binding']
    dispatch = binding.participation.control_policy('dispatch')

    assert dispatch is not None
    assert dispatch.pre_degrading_after_seconds == 400
    assert dispatch.degrading_after_seconds == 600


def _content_state_test_collection() -> GlobalIndicatorCollection:
    return GlobalIndicatorCollection(
        indicators=(
            GlobalIndicatorState(
                key='runtime_indicator',
                label='Indicador runtime',
                unit='u',
                measurements=(
                    GlobalIndicatorMeasurementState(
                        key='turno',
                        label='Turno',
                        actual_value='10',
                        plan_value='12',
                        actual_kpi_key='runtime_shift_actual',
                        plan_kpi_key='runtime_shift_plan',
                    ),
                    GlobalIndicatorMeasurementState(
                        key='dia',
                        label='Día',
                        actual_value='20',
                        plan_value='24',
                        actual_kpi_key='runtime_day_actual',
                        plan_kpi_key='runtime_day_plan',
                    ),
                ),
            ),
        )
    )


def test_global_indicators_runtime_binding_is_client_driven_and_preserves_kpi_dom(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')
    consumption, participation = _source_configuration()

    runtime = create_application_runtime(
        global_indicators=_content_state_test_collection(),
        content_state_dependencies=(
            ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
        ),
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    definition = create_application_definition(
        global_indicators=_content_state_test_collection(),
        content_state_dependencies=(
            ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
        ),
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    payload = json.dumps(
        runtime.server.test_client().get('/_dash-layout').get_json(),
        ensure_ascii=False,
    )

    assert definition.layout.keywords['global_indicators_runtime_state'] is ContentState.READY
    assert definition.layout.keywords['global_indicators_source_keys'] == ('pi',)
    assert 'data-ada-content-state-runtime' in payload
    assert 'data-ada-content-state-tool-key' in payload
    assert 'data-ada-content-state-sources' in payload
    assert 'global_indicators' in payload
    assert 'process' in payload
    assert 'runtime_shift_actual' in payload


def test_global_indicators_runtime_binding_preserves_multiple_control_dependencies() -> None:
    consumption, participation = _source_configuration(
        tool_key='integrated_operations',
        with_dispatch=True,
    )
    definition = create_application_definition(
        global_indicators=_content_state_test_collection(),
        content_state_dependencies=(
            ContentStateDependency(
                component_key='global_indicators',
                source_keys=('pi', 'dispatch'),
            ),
        ),
        source_consumption=consumption,
        source_operational_participation=participation,
    )

    assert definition.layout.keywords['global_indicators_runtime_state'] is ContentState.READY
    assert definition.layout.keywords['global_indicators_source_keys'] == ('pi', 'dispatch')


def test_construction_precedence_is_preserved_for_client_driven_runtime(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')
    consumption, participation = _source_configuration()

    runtime = create_application_runtime(
        global_indicators=_content_state_test_collection(),
        global_indicators_content_state=ContentState.CONSTRUCTION,
        content_state_dependencies=(
            ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
        ),
        source_consumption=consumption,
        source_operational_participation=participation,
    )
    payload = json.dumps(
        runtime.server.test_client().get('/_dash-layout').get_json(),
        ensure_ascii=False,
    )

    assert 'data-ada-content-state-declared' in payload
    assert 'construction' in payload
    assert 'En construcción' in payload
    assert 'runtime_shift_actual' in payload


def test_content_state_dependency_rejects_additional_observation_as_degrading_source() -> None:
    consumption, participation = _source_configuration(
        additional_observation_source_keys=('blockgrade',)
    )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match="not declared as CONTROL: 'blockgrade'",
    ):
        create_application_definition(
            global_indicators=_content_state_test_collection(),
            content_state_dependencies=(
                ContentStateDependency(
                    component_key='global_indicators',
                    source_keys=('blockgrade',),
                ),
            ),
            source_consumption=consumption,
            source_operational_participation=participation,
        )


def test_content_state_dependency_rejects_component_not_adopted_by_generic_application() -> None:
    with pytest.raises(ValueError, match='Unsupported Generic Application Content State component'):
        create_application_definition(
            content_state_dependencies=(
                ContentStateDependency(component_key='other_component', source_keys=('pi',)),
            )
        )


def test_source_driven_composition_requires_tool_source_consumption() -> None:
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match='requires ToolSourceConsumption',
    ):
        create_application_definition(
            global_indicators=_content_state_test_collection(),
            content_state_dependencies=(
                ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
            ),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
        )


def test_source_driven_composition_requires_operational_participation() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='requires ToolSourceOperationalParticipation',
    ):
        create_application_definition(
            global_indicators=_content_state_test_collection(),
            content_state_dependencies=(
                ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
            ),
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
        )


def test_pi_must_be_explicitly_consumed_by_ada_time_status_runtime() -> None:
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match="Source is not declared by Tool Configuration: 'pi'",
    ):
        create_application_definition(
            source_consumption=ToolSourceConsumption(
                tool_key='process',
                source_keys=('blockgrade',),
            ),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                additional_observation_source_keys=('blockgrade',),
            ),
        )


def test_pi_must_participate_as_control_for_ada_time_status_runtime() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='requires PI as a CONTROL source',
    ):
        create_application_definition(
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
            ),
        )


def test_dispatch_when_consumed_must_participate_as_optional_control_source() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='Dispatch declared by Tool Source Consumption must participate as CONTROL',
    ):
        create_application_definition(
            source_consumption=ToolSourceConsumption(
                tool_key='process',
                source_keys=('pi', 'dispatch'),
            ),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
                additional_observation_source_keys=('dispatch',),
            ),
        )


def test_ada_time_status_runtime_rejects_other_control_source_keys() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match="supports only PI and Dispatch as CONTROL sources: 'blockgrade'",
    ):
        create_application_definition(
            source_consumption=ToolSourceConsumption(
                tool_key='process',
                source_keys=('pi', 'blockgrade'),
            ),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(
                    SourceControlPolicy('pi', 200, 300),
                    SourceControlPolicy('blockgrade', 400, 600),
                ),
            ),
        )


def test_time_status_detail_source_must_be_declared_by_tool_configuration() -> None:
    consumption, participation = _source_configuration()

    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match="Source is not declared by Tool Configuration: 'blockgrade'",
    ):
        create_application_definition(
            source_consumption=consumption,
            source_operational_participation=participation,
            time_status_detail=_time_status_detail(),
        )


def test_time_status_detail_source_must_be_additional_observation() -> None:
    consumption = ToolSourceConsumption(
        tool_key='process',
        source_keys=('pi', 'blockgrade'),
    )
    participation = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(SourceControlPolicy('pi', 200, 300),),
    )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match="not declared as ADDITIONAL OBSERVATION: 'blockgrade'",
    ):
        create_application_definition(
            source_consumption=consumption,
            source_operational_participation=participation,
            time_status_detail=_time_status_detail(),
        )


def test_time_status_detail_requires_operational_participation() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='Time Status detail requires ToolSourceOperationalParticipation',
    ):
        create_application_definition(time_status_detail=_time_status_detail())


def test_content_state_dependency_source_must_be_declared_by_tool_configuration() -> None:
    consumption, participation = _source_configuration()

    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match="Source is not declared by Tool Configuration: 'dispatch'",
    ):
        create_application_definition(
            global_indicators=_content_state_test_collection(),
            content_state_dependencies=(
                ContentStateDependency(
                    component_key='global_indicators',
                    source_keys=('pi', 'dispatch'),
                ),
            ),
            source_consumption=consumption,
            source_operational_participation=participation,
        )


def test_content_state_presentation_mode_defaults_to_normal() -> None:
    definition = create_application_definition()

    assert (
        definition.layout.keywords['content_state_presentation_mode']
        is ContentStatePresentationMode.NORMAL
    )


def test_authoring_mode_is_explicitly_threaded_and_logged(caplog) -> None:
    caplog.set_level('INFO', logger='ada.web.application.generic.application')
    definition = create_application_definition(
        content_state_presentation_mode=ContentStatePresentationMode.AUTHORING,
    )

    assert (
        definition.layout.keywords['content_state_presentation_mode']
        is ContentStatePresentationMode.AUTHORING
    )
    assert 'Content State presentation override is active: authoring' in caplog.messages


def test_generic_application_rejects_implicit_presentation_mode_string() -> None:
    with pytest.raises(TypeError, match='ContentStatePresentationMode'):
        create_application_definition(
            content_state_presentation_mode='authoring',  # type: ignore[arg-type]
        )


def test_runtime_factory_exposes_explicit_authoring_mode_contract() -> None:
    from ada.web.application.generic import ContentStatePresentationMode as ExportedPresentationMode

    signature = inspect.signature(create_application_runtime)

    assert ExportedPresentationMode is ContentStatePresentationMode
    assert signature.parameters['content_state_presentation_mode'].default is (
        ContentStatePresentationMode.NORMAL
    )
