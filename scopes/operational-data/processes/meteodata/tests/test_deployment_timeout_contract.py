from __future__ import annotations

import json
from pathlib import Path

from atlanticus.operational_data.processes.meteodata.composition import (
    METEODATA_JOB_DEFINITION,
)


def test_replica_timeout_preserves_runtime_shutdown_budget() -> None:
    deployment_file = Path(__file__).resolve().parents[1] / 'config.detail.json'
    deployment = json.loads(deployment_file.read_text(encoding='utf-8'))
    replica_timeout = deployment['configuration']['replicaTimeout']

    assert isinstance(replica_timeout, int) and not isinstance(replica_timeout, bool)
    assert replica_timeout >= (
        METEODATA_JOB_DEFINITION.execution_timeout_seconds
        + METEODATA_JOB_DEFINITION.shutdown_grace_seconds
    )
