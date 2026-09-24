from ada_command_center.web.alarms.configuration.source_projection import (
    create_alarm_configuration_projection_service,
)
from ada_command_center.web.alarms.configuration.source_release import (
    AlarmConfigurationSourceService,
)
from ada_command_center.web.application.configuration_manager import (
    ALARM_CONFIGURATION_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_dependencies,
)
from atlanticus.web.projection.models import ProjectionAlignment


def _service(dependencies):
    return create_alarm_configuration_projection_service(
        source=dependencies.source_store,
        projection=dependencies.projection_store,
    )


def test_local_manager_projection_survives_recomposition(tmp_path) -> None:
    root = tmp_path / 'source'
    first = create_local_configuration_manager_dependencies(source_root=root)
    initial_projection = first.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
    assert initial_projection is not None

    restarted = create_local_configuration_manager_dependencies(source_root=root)
    restored = restarted.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
    assert restored == initial_projection
    assert _service(restarted).get_status(ALARM_CONFIGURATION_SOURCE_KEY).alignment is (
        ProjectionAlignment.CURRENT
    )


def test_local_manager_preserves_outdated_projection_until_explicit_project(tmp_path) -> None:
    root = tmp_path / 'source'
    first = create_local_configuration_manager_dependencies(source_root=root)
    active = first.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
    assert active is not None
    source = AlarmConfigurationSourceService(
        source=first.source_store,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )
    before = source.get_current()
    released = source.load_current()
    assert before.current is not None
    assert released is not None
    source.publish_snapshot(
        released.snapshot,
        published_by='local-test',
        expected_concurrency_token=before.concurrency_token,
        basis_release=before.current.release_ref,
    )

    restarted = create_local_configuration_manager_dependencies(source_root=root)
    projection = _service(restarted)
    assert restarted.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) == active
    assert projection.get_status(ALARM_CONFIGURATION_SOURCE_KEY).alignment is (
        ProjectionAlignment.OUTDATED
    )
    target = projection.select_current_target(ALARM_CONFIGURATION_SOURCE_KEY)
    assert target is not None
    result = projection.project(target)
    assert result.projection.target == target
    assert projection.get_status(ALARM_CONFIGURATION_SOURCE_KEY).alignment is (
        ProjectionAlignment.CURRENT
    )
    assert len(source.query_history(page_size=10).items) == 2


def test_local_manager_can_start_without_seed_and_preserve_existing_state(tmp_path) -> None:
    root = tmp_path / 'source'
    empty = create_local_configuration_manager_dependencies(
        source_root=root,
        seed_sample_configuration=False,
    )
    assert empty.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) is None
    first = create_local_configuration_manager_dependencies(source_root=root)
    active = first.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
    without_seed = create_local_configuration_manager_dependencies(
        source_root=root,
        seed_sample_configuration=False,
    )
    assert without_seed.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) == active
