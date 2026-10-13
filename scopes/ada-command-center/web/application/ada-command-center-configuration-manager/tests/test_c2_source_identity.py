from ada.contracts.alarms import (
    ALARM_CONFIGURATION_SOURCE_KEY as CANONICAL_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager import ALARM_CONFIGURATION_SOURCE_KEY


def test_web_host_uses_canonical_alarm_source_identity():
    assert ALARM_CONFIGURATION_SOURCE_KEY.value == CANONICAL_SOURCE_KEY
