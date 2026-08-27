from __future__ import annotations

import json

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
from ada.web.shell.header import ADA_OPERATIONAL_HEADER_ASSET_LAYER
from ada.web.shell.navigation import ADA_NAVIGATION_ASSET_LAYER, AdaNavigationView
from ada.web.ui.branding import (
    ADA_BRANDING_ASSET_LAYER,
    DEFAULT_OPERATIONAL_BRAND_LOGO_SRC,
    DEFAULT_OPERATIONAL_BRAND_SECONDARY_LOGO_SRC,
    DEFAULT_PELAMBRES_BRAND_LOGO_SRC,
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
    assert definition.metadata.version == '0.1.22'
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
    assert 'Versión 0.1.22' in payload
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
                kpi_key='test_kpi',
                label='Indicador de prueba',
                unit='u',
                measurements=(
                    GlobalIndicatorMeasurementState(
                        key='turno',
                        label='Turno',
                        actual_value='10',
                        plan_value='12',
                    ),
                    GlobalIndicatorMeasurementState(
                        key='dia',
                        label='Día',
                        actual_value='20',
                        plan_value='24',
                    ),
                ),
                last_measurement=GlobalIndicatorLastMeasurementState('22'),
            ),
        )
    )
    runtime = create_application_runtime(global_indicators=collection)
    response = runtime.server.test_client().get('/_dash-layout')
    payload = json.dumps(response.get_json(), ensure_ascii=False)

    assert 'global-indicators' in payload
    assert 'test_indicator' in payload
    assert 'data-kpi-inspection-key' in payload
    assert 'test_kpi' in payload
    assert 'Indicador de prueba' in payload
    assert 'Última medición' in payload
    assert '22' in payload
    assert 'data-slot-empty' in payload


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
