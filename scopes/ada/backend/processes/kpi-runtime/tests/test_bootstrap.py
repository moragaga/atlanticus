from __future__ import annotations

from ada.processes.kpi_runtime.bootstrap import load_configuration


def test_local_bootstrap_uses_process_root_dotenv(tmp_path) -> None:
    (tmp_path / '.env').write_text(
        '\n'.join(
            (
                'ENVIRONMENT=local',
                'APPLICATION=ada-kpi-runtime-local',
                f'VOLUMEN_PATH={tmp_path}',
                'PI_SOURCE=NOTPII',
                'PI_APPLICATION=operational-data-notpii-local',
                'KPI_POLL_INTERVAL_SECONDS=1',
                'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED=true',
                'ATLANTICUS_AZURE_OBSERVABILITY_MODE=off',
            )
        )
        + '\n',
        encoding='utf-8',
    )

    configuration = load_configuration(process_root=tmp_path, environ={})

    assert configuration.require('APPLICATION') == 'ada-kpi-runtime-local'
    assert configuration.require('PI_SOURCE') == 'NOTPII'
