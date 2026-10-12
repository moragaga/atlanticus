from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.master_projection.composition import (
    compose_master_projection_backend,
)


def test_backend_composes_six_source_domains(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
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
