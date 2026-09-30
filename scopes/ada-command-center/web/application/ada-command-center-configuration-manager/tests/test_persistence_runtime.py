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
    open_local_configuration_manager,
)
from atlanticus.web.projection.models import ProjectionAlignment

from .test_local_runtime import _manual_alarm_release, _principal, _reader, _storage


def _service(dependencies):
    return create_alarm_configuration_projection_service(
        source=dependencies.source_store,
        projection=dependencies.projection_store,
    )


def _publish_and_project(dependencies):
    snapshot = _manual_alarm_release(dependencies, 'confirmed-manual-test-revision')
    projection = _service(dependencies)
    target = projection.select_current_target(ALARM_CONFIGURATION_SOURCE_KEY)
    assert target is not None
    projection.project(target)
    return snapshot


def test_local_manager_projection_survives_recomposition(tmp_path, monkeypatch) -> None:
    _storage(monkeypatch)
    with open_local_configuration_manager(
        reader=_reader(tmp_path), principal_provider=_principal, base_root=tmp_path
    ) as first:
        snapshot = _publish_and_project(first)
        initial = first.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
        assert initial is not None
        assert initial.payload == snapshot
        projection_root = (
            tmp_path
            / 'conciencia_situacional'
            / 'command-center'
            / 'projections'
            / 'alarm-configuration'
        )
        assert projection_root.is_dir()
        assert tuple(projection_root.glob('alarm_configuration_projection_*.json'))

    with open_local_configuration_manager(
        reader=_reader(tmp_path), principal_provider=_principal, base_root=tmp_path
    ) as restarted:
        restored = restarted.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
        assert restored == initial
        assert _service(restarted).get_status(ALARM_CONFIGURATION_SOURCE_KEY).alignment is (
            ProjectionAlignment.CURRENT
        )


def test_local_manager_projection_changes_only_after_explicit_project(
    tmp_path, monkeypatch
) -> None:
    _storage(monkeypatch)
    with open_local_configuration_manager(
        reader=_reader(tmp_path), principal_provider=_principal, base_root=tmp_path
    ) as first:
        _publish_and_project(first)
        active = first.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY)
        source = AlarmConfigurationSourceService(
            source=first.source_store, source_key=ALARM_CONFIGURATION_SOURCE_KEY
        )
        current = source.get_current()
        assert current.current is not None
        _manual_alarm_release(first, 'confirmed-manual-test-revision')

    with open_local_configuration_manager(
        reader=_reader(tmp_path), principal_provider=_principal, base_root=tmp_path
    ) as restarted:
        projection = _service(restarted)
        assert restarted.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) == active
        assert projection.get_status(ALARM_CONFIGURATION_SOURCE_KEY).alignment is (
            ProjectionAlignment.OUTDATED
        )
        target = projection.select_current_target(ALARM_CONFIGURATION_SOURCE_KEY)
        assert target is not None
        projection.project(target)
        assert projection.get_status(ALARM_CONFIGURATION_SOURCE_KEY).alignment is (
            ProjectionAlignment.CURRENT
        )
        source = AlarmConfigurationSourceService(
            source=restarted.source_store, source_key=ALARM_CONFIGURATION_SOURCE_KEY
        )
        assert len(source.query_history(page_size=10).items) == 2


def test_local_manager_does_not_seed_state_between_restarts(tmp_path, monkeypatch) -> None:
    _storage(monkeypatch)
    with open_local_configuration_manager(
        reader=_reader(tmp_path), principal_provider=_principal, base_root=tmp_path
    ) as first:
        assert first.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) is None
        assert first.tool_reference_reader.load() is None
    with open_local_configuration_manager(
        reader=_reader(tmp_path), principal_provider=_principal, base_root=tmp_path
    ) as second:
        assert second.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) is None
        assert second.tool_reference_reader.load() is None
