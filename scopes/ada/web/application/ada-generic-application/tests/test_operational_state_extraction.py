from __future__ import annotations

import inspect

from ada.web.application.generic import application
from ada.web.application.generic.application import create_application_definition
from ada.web.operational_state import resolve_ada_operational_state


def test_application_delegates_operational_policy_to_extracted_package() -> None:
    source = inspect.getsource(application)

    assert 'resolve_ada_operational_state' in source
    assert '_validate_source_configuration' not in source
    assert '_validate_ada_operational_participation' not in source
    assert '_resolve_time_status_summary' not in source
    assert '_resolve_source_freshness' not in source
    assert '_validate_content_state_dependencies' not in source
    assert '_SUPPORTED_ADA_CONTROL_SOURCE_KEYS' not in source
    assert callable(resolve_ada_operational_state)


def test_application_definition_preserves_empty_operational_contract() -> None:
    definition = create_application_definition()

    assert definition.layout.keywords['tool_key'] is None
    assert definition.layout.keywords['time_status_summary'] is None
    assert definition.layout.keywords['global_indicators_source_keys'] == ()
