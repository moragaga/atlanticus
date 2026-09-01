from pathlib import Path

import pytest

from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment
from atlanticus.operational_data.processes.notpii.bootstrap import _require_absolute_volume_path
from atlanticus.operational_data.processes.notpii.errors import NotPiiProcessConfigurationError


def _configuration(volume_path: str) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-notpii',
        'VOLUMEN_PATH': volume_path,
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_volume_path_must_be_absolute(tmp_path: Path) -> None:
    with pytest.raises(NotPiiProcessConfigurationError, match='absolute'):
        _require_absolute_volume_path(_configuration('relative-volume'))
    assert _require_absolute_volume_path(_configuration(str(tmp_path))).require(
        'VOLUMEN_PATH'
    ) == str(tmp_path)
