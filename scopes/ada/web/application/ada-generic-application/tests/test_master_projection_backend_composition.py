from dataclasses import replace

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.master_projection.composition import (
    compose_master_projection_backend,
)


class Recovery:
    def __init__(self):
        self.calls = []

    def apply_snapshot(self, snapshot_id):
        self.calls.append(snapshot_id)
        return type('Result', (), {'differences': ()})()


def test_backend_composes_source_executor_and_users_replace(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    recovery = Recovery()
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    stores = replace(
        stores,
        users_recovery=lambda: recovery,
        users_snapshot_ids=lambda: ('snapshot-1',),
    )
    backend = compose_master_projection_backend(stores)
    report = backend.planner.inspect()
    assert {item.key.value for item in report.entries} == {
        'navigation',
        'profiles-configuration',
        'tools',
        'ada-access',
        'kpi-registry',
        'kpi-definitions',
    }
    result = backend.executor.apply_users(snapshot_id='snapshot-1')
    assert result.snapshot_id == 'snapshot-1'
    assert recovery.calls == ['snapshot-1']
