from ada_command_center.domain.alarms import AlarmConfiguration
from ada_command_center.web.alarms.configuration.source_release import (
    AlarmConfigurationSourceService,
)
from ada_command_center.web.application.configuration_manager import (
    ALARM_CONFIGURATION_MANAGER_ACCESS_KEY,
    ALARM_CONFIGURATION_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_dependencies,
    create_local_tool_catalog_snapshot,
    create_sample_alarm_configuration,
)
from atlanticus.web.manager import ManagerWorkspace


def test_local_runtime_seeds_source_projection_and_tool_references(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)
    source = AlarmConfigurationSourceService(
        source=dependencies.source_store,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )

    release = source.load_current()
    projection = dependencies.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
    catalog = dependencies.tool_reference_reader.load()

    assert release is not None
    assert catalog is not None
    assert release.snapshot.configuration == create_sample_alarm_configuration()
    assert release.snapshot.confirmed_tool_catalog_revision == catalog.catalog_revision
    assert release.published_by == 'local-bootstrap'
    assert projection is not None
    assert projection.payload == release.snapshot
    assert tuple(tool.tool_key for tool in catalog.tools) == (
        'integrated_operations',
        'process_control',
    )
    visible = catalog.subcomponents('integrated_operations', 'mine_secondary')
    assert ('mine_primary', 'crusher') in tuple(
        (item.owner_component_key, item.subcomponent_key) for item in visible
    )


def test_local_runtime_does_not_reseed_existing_source(tmp_path) -> None:
    first = create_local_configuration_manager_dependencies(source_root=tmp_path)
    source = AlarmConfigurationSourceService(
        source=first.source_store,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )
    initial = source.get_current()

    second = create_local_configuration_manager_dependencies(source_root=tmp_path)
    repeated = AlarmConfigurationSourceService(
        source=second.source_store,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    ).get_current()

    assert repeated.current == initial.current


def test_local_runtime_can_start_without_sample_configuration(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(
        source_root=tmp_path,
        seed_sample_configuration=False,
    )
    source = AlarmConfigurationSourceService(
        source=dependencies.source_store,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )

    assert source.get_current().current is None
    assert dependencies.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) is None


def test_local_runtime_grants_only_alarm_configuration_capability(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)
    principal = dependencies.principal_provider()

    assert principal.is_local is True
    assert principal.profile_keys == ()
    assert principal.access_keys == (ALARM_CONFIGURATION_MANAGER_ACCESS_KEY,)


def test_sample_configuration_exercises_engine_facing_attributes() -> None:
    configuration = create_sample_alarm_configuration()
    primary = configuration.rules[1]

    assert primary.evaluator_key == 'local.threshold'
    assert primary.parameters == {
        'threshold_tph': 1200.0,
        'window': '15m',
        'quality_required': True,
    }
    assert primary.reappearance.after_minutes == 15
    assert primary.reappearance.special_conditions == (configuration.rules[0].identity,)
    assert primary.default_deactivation.enabled is True
    assert primary.default_deactivation.approval_required is True
    assert primary.escalation.origin_tool_key == 'integrated_operations'
    assert primary.escalation.steps[0].target_tool_key == 'process_control'
    assert primary.escalation.steps[0].wait_minutes_from_previous_step == 10
    assert tuple(target.tool_key for target in primary.visual_targets) == (
        'integrated_operations',
        'process_control',
    )


def test_local_tool_catalog_contains_integrated_and_process_topology() -> None:
    snapshot = create_local_tool_catalog_snapshot()

    integrated = snapshot.get('integrated_operations')
    process = snapshot.get('process_control')

    assert integrated is not None
    assert process is not None
    assert integrated.structure.alarm_baseline_component_keys == (
        'mine_primary',
        'mine_secondary',
    )
    assert process.structure.alarm_baseline_component_keys == ('plant_process',)


def test_sample_configuration_survives_browser_integral_number_workspace_round_trip(
    tmp_path,
) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)
    source = AlarmConfigurationSourceService(
        source=dependencies.source_store,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )
    release = source.load_current()

    assert release is not None
    workspace = ManagerWorkspace.create(
        owner_subject_id='local',
        payload=release.snapshot.configuration.to_document(),
        base=source.get_current(),
    )
    document = workspace.to_document()
    document['payload']['rules'][1]['parameters']['threshold_tph'] = 1200

    restored = ManagerWorkspace.from_document(document)
    configuration = AlarmConfiguration.from_document(restored.payload)

    threshold = configuration.rules[1].parameters['threshold_tph']
    assert threshold == 1200.0
    assert isinstance(threshold, float)
