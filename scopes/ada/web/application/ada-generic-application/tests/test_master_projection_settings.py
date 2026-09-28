from __future__ import annotations

import pytest
from pydantic import ValidationError

from ada.web.application.generic.settings import AdaGenericSettings


def _values(tmp_path, *, master_path: str | None = None):
    values = {
        'ATLANTICUS_ENVIRONMENT': 'local',
        'ADA_APPLICATION_NAMESPACE': 'app',
        'ADA_TOOL_NAMESPACE': 'tool',
        'ADA_TOOL_SOURCE_PROVIDER': 'local',
        'ADA_TOOL_PROJECTION_PROVIDER': 'local',
        'ADA_TOOL_LOCAL_BASE_ROOT': str(tmp_path),
    }
    if master_path is not None:
        values['ADA_MASTER_PROJECTION_MATERIAL_PATH'] = master_path
    return values


def test_absent_or_blank_master_material_path_is_allowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert AdaGenericSettings.from_mapping(_values(tmp_path)).master_projection_material_path == ''
    assert AdaGenericSettings.from_mapping(
        _values(tmp_path, master_path='')
    ).master_projection_material_path == ''


def test_master_material_path_requires_absolute_location(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    absolute = str(tmp_path / 'master-projection.zip')
    settings = AdaGenericSettings.from_mapping(_values(tmp_path, master_path=absolute))
    assert settings.master_projection_material_path == absolute
    with pytest.raises(ValidationError, match='absolute'):
        AdaGenericSettings.from_mapping(_values(tmp_path, master_path='relative.zip'))
