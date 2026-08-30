from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from ada.configuration.tool_source_consumption import (
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
)
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
from ada.web.content_state.dependency_resolver import (
    ContentStateDependency,
    MissingSourceFreshnessError,
)
from ada.web.shell.header import ADA_OPERATIONAL_HEADER_ASSET_LAYER
from ada.web.shell.navigation import ADA_NAVIGATION_ASSET_LAYER, AdaNavigationView
from ada.web.ui.branding import (
    ADA_BRANDING_ASSET_LAYER,
    DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
    DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC,
    DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
)
from ada.web.ui.content_state import ADA_CONTENT_STATE_ASSET_LAYER, ContentState
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
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    TimeStatusSourceState,
    TimeStatusSummaryState,
)
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
    assert definition.metadata.version == '0.1.32'
    assert tuple(module.name for module in definition.modules) == (
        'ada-ui',
        'ada-display-status',
        'ada-global-indicator',
        'ada-alarm-management-summary',
        'ada-alarm-status',
        'ada-branding',
        'identity',
        'navigation',
        'ada-navigation',
        'ada-operational-header',
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
    assert 'ada-navigation__anchor-host' in payload
    assert 'Test User' in payload
    assert 'Asistente de Decisiones Ágiles' in payload
    assert DEFAULT_OPERATIONAL_BRAND_LOGO_SRC in payload
    assert DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC in payload
    assert DEFAULT_PELAMBRES_BRAND_LOGO_SRC in payload
    assert 'Versión 0.1.32' in payload
    assert runtime.services.contains(ACCESS_RUNTIME_SERVICE_KEY)
    assert runtime.services.contains(NAVIGATION_PRINCIPAL_PROVIDER_SERVICE_KEY)
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
    assert navigation.home_route_key == 'home'
    assert navigation.find_link('home').href == '/'

    with client.session_transaction() as session:
        snapshot = session['_atlanticus_access_snapshot']
    assert snapshot['identity']['subject_id'] == 'local:test-user'


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


def test_time_status_mounts_under_header_only_when_explicitly_injected(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    policy = TimeStatusFreshnessPolicy(warning_after_seconds=200, stale_after_seconds=300)
    pi = TimeStatusSourceState(
        key='pi',
        label='PI',
        policy=policy,
        condition=TimeStatusSourceCondition.FRESH,
        relative_age_text='hace menos de 10 segundos',
        timestamp_utc=datetime(2026, 8, 29, 22, 0, tzinfo=UTC),
    )
    summary = TimeStatusSummaryState(pi=pi, has_detail=True)
    detail = TimeStatusDetailState(
        sources=(TimeStatusDetailSourceState(key='blockgrade', label='BlockGrade', value='Error'),)
    )
    runtime = create_application_runtime(
        source_consumption=ToolSourceConsumption(
            tool_key='process',
            source_keys=('pi', 'blockgrade'),
        ),
        time_status_summary=summary,
        time_status_detail=detail,
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert 'time_status' in payload
    assert 'data-ada-time-status-tool-key' in payload
    assert 'process' in payload
    assert 'BlockGrade' in payload
    assert 'informational' in payload
    assert any(
        entry.startswith(f'{ADA_TIME_STATUS_ASSET_LAYER.target_name}/css/')
        for entry in runtime.assets.css_entries
    )
    assert any(
        entry.startswith(f'{ADA_TIME_STATUS_ASSET_LAYER.target_name}/js/')
        for entry in runtime.assets.js_entries
    )


def test_time_status_assets_are_not_loaded_without_time_status() -> None:
    definition = create_application_definition()

    assert 'ada-time-status' not in tuple(module.name for module in definition.modules)


def test_time_status_definition_adds_module_when_summary_is_injected() -> None:
    policy = TimeStatusFreshnessPolicy(warning_after_seconds=200, stale_after_seconds=300)
    summary = TimeStatusSummaryState(
        pi=TimeStatusSourceState(
            key='pi',
            label='PI',
            policy=policy,
            condition=TimeStatusSourceCondition.FRESH,
            relative_age_text='hace menos de 10 segundos',
            timestamp_utc=datetime(2026, 8, 29, 22, 0, tzinfo=UTC),
        )
    )

    definition = create_application_definition(
        source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
        time_status_summary=summary,
    )

    assert 'ada-time-status' in tuple(module.name for module in definition.modules)


def test_time_status_without_additional_sources_renders_explicit_empty_detail(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    policy = TimeStatusFreshnessPolicy(warning_after_seconds=200, stale_after_seconds=300)
    summary = TimeStatusSummaryState(
        pi=TimeStatusSourceState(
            key='pi',
            label='PI',
            policy=policy,
            condition=TimeStatusSourceCondition.FRESH,
            relative_age_text='hace menos de 10 segundos',
            timestamp_utc=datetime(2026, 8, 30, 13, 0, tzinfo=UTC),
        ),
        has_detail=True,
    )
    runtime = create_application_runtime(
        source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
        time_status_summary=summary,
        time_status_detail=None,
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert 'Sin fuentes adicionales' in payload
    assert 'Esta herramienta no consume fuentes de datos adicionales.' in payload


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


def _time_status_summary(
    *,
    pi_condition: TimeStatusSourceCondition,
    dispatch_condition: TimeStatusSourceCondition | None = None,
) -> TimeStatusSummaryState:
    policy = TimeStatusFreshnessPolicy(warning_after_seconds=200, stale_after_seconds=300)

    def source(key: str, condition: TimeStatusSourceCondition) -> TimeStatusSourceState:
        return TimeStatusSourceState(
            key=key,
            label=key.upper(),
            policy=policy,
            condition=condition,
            relative_age_text=(
                None if condition is TimeStatusSourceCondition.DATA_ERROR else 'hace 10 segundos'
            ),
            timestamp_utc=(
                None
                if condition is TimeStatusSourceCondition.DATA_ERROR
                else datetime(2026, 8, 30, 13, 0, tzinfo=UTC)
            ),
        )

    return TimeStatusSummaryState(
        pi=source('pi', pi_condition),
        dispatch=(None if dispatch_condition is None else source('dispatch', dispatch_condition)),
    )


def test_global_indicators_runtime_binding_resolves_initial_stale_and_preserves_kpi_dom(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime(
        global_indicators=_content_state_test_collection(),
        content_state_dependencies=(
            ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
        ),
        source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
        time_status_summary=_time_status_summary(
            pi_condition=TimeStatusSourceCondition.HARD_STALE,
        ),
    )
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert response.status_code == 200
    assert 'data-ada-content-state-runtime' in payload
    assert 'data-ada-content-state-tool-key' in payload
    assert 'data-ada-content-state-sources' in payload
    assert 'global_indicators' in payload
    assert 'process' in payload
    assert 'stale' in payload
    assert 'Información desactualizada' in payload
    assert 'runtime_shift_actual' in payload


def test_global_indicators_runtime_binding_resolves_source_error_per_own_dependencies() -> None:
    definition = create_application_definition(
        global_indicators=_content_state_test_collection(),
        content_state_dependencies=(
            ContentStateDependency(
                component_key='global_indicators',
                source_keys=('pi', 'dispatch'),
            ),
        ),
        source_consumption=ToolSourceConsumption(
            tool_key='integrated_operations',
            source_keys=('pi', 'dispatch'),
        ),
        time_status_summary=_time_status_summary(
            pi_condition=TimeStatusSourceCondition.HARD_STALE,
            dispatch_condition=TimeStatusSourceCondition.DATA_ERROR,
        ),
    )

    assert definition.metadata.version == '0.1.32'
    assert (
        definition.layout.keywords['global_indicators_runtime_state'] is ContentState.SOURCE_ERROR
    )
    assert definition.layout.keywords['global_indicators_source_keys'] == ('pi', 'dispatch')


def test_construction_precedence_is_preserved_over_runtime_source_error(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ATLANTICUS_ENVIRONMENT', raising=False)
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:test-user')

    runtime = create_application_runtime(
        global_indicators=_content_state_test_collection(),
        global_indicators_content_state=ContentState.CONSTRUCTION,
        content_state_dependencies=(
            ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
        ),
        source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
        time_status_summary=_time_status_summary(
            pi_condition=TimeStatusSourceCondition.DATA_ERROR,
        ),
    )
    payload = json.dumps(
        runtime.server.test_client().get('/_dash-layout').get_json(),
        ensure_ascii=False,
    )

    assert 'data-ada-content-state-declared' in payload
    assert 'construction' in payload
    assert 'En construcción' in payload
    assert 'runtime_shift_actual' in payload


def test_content_state_dependency_requires_required_time_status_source() -> None:
    with pytest.raises(MissingSourceFreshnessError, match='dispatch'):
        create_application_definition(
            global_indicators=_content_state_test_collection(),
            content_state_dependencies=(
                ContentStateDependency(
                    component_key='global_indicators',
                    source_keys=('pi', 'dispatch'),
                ),
            ),
            source_consumption=ToolSourceConsumption(
                tool_key='process',
                source_keys=('pi', 'dispatch'),
            ),
            time_status_summary=_time_status_summary(
                pi_condition=TimeStatusSourceCondition.FRESH,
            ),
        )


def test_content_state_dependency_rejects_component_not_adopted_by_generic_application() -> None:
    with pytest.raises(ValueError, match='Unsupported Generic Application Content State component'):
        create_application_definition(
            content_state_dependencies=(
                ContentStateDependency(component_key='other_component', source_keys=('pi',)),
            ),
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            time_status_summary=_time_status_summary(
                pi_condition=TimeStatusSourceCondition.FRESH,
            ),
        )


def test_source_driven_composition_requires_tool_source_consumption() -> None:
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match='requires ToolSourceConsumption',
    ):
        create_application_definition(
            time_status_summary=_time_status_summary(
                pi_condition=TimeStatusSourceCondition.FRESH,
            )
        )


def test_time_status_required_source_must_be_declared_by_tool_configuration() -> None:
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match="Source is not declared by Tool Configuration: 'pi'",
    ):
        create_application_definition(
            source_consumption=ToolSourceConsumption(
                tool_key='process',
                source_keys=('blockgrade',),
            ),
            time_status_summary=_time_status_summary(
                pi_condition=TimeStatusSourceCondition.FRESH,
            ),
        )


def test_time_status_detail_source_must_be_declared_by_tool_configuration() -> None:
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match="Source is not declared by Tool Configuration: 'blockgrade'",
    ):
        create_application_definition(
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            time_status_summary=_time_status_summary(
                pi_condition=TimeStatusSourceCondition.FRESH,
            ),
            time_status_detail=TimeStatusDetailState(
                sources=(
                    TimeStatusDetailSourceState(
                        key='blockgrade',
                        label='BlockGrade',
                        value='Fresh',
                    ),
                )
            ),
        )


def test_content_state_dependency_source_must_be_declared_by_tool_configuration() -> None:
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
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            time_status_summary=_time_status_summary(
                pi_condition=TimeStatusSourceCondition.FRESH,
                dispatch_condition=TimeStatusSourceCondition.FRESH,
            ),
        )
