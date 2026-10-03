from ada_command_center.domain.alarms.identity import (
    ALARM_CONFIGURATION_SOURCE_KEY as DOMAIN_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager import ALARM_CONFIGURATION_SOURCE_KEY


def test_web_host_adapts_domain_identity_to_source_model():
    assert ALARM_CONFIGURATION_SOURCE_KEY.value == DOMAIN_SOURCE_KEY
