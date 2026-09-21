from ada_command_center.web.alarms.configuration.manager import (
    ALARM_CONFIGURATION_MANAGER_PROJECTION_SERVICE,
    ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE,
    ALARM_CONFIGURATION_MANAGER_VALIDATION_SERVICE,
    compose_alarm_configuration_manager,
)
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore


class SourceStoreStub(SourceStore):
    def get_current(self, source_key):
        raise AssertionError(source_key)

    def read_release(self, source_key, release_ref):
        raise AssertionError((source_key, release_ref))

    def publish(self, request):
        raise AssertionError(request)

    def query_history(self, query):
        raise AssertionError(query)

    def verify_release(self, source_key, release_ref):
        raise AssertionError((source_key, release_ref))


class ProjectionStoreStub(ProjectionStore):
    def get_active(self, source_key):
        return None

    def replace_active(self, projection):
        return projection


def test_alarm_configuration_manager_composition_registers_real_workflows() -> None:
    source_key = SourceKey('alarm-configuration')
    principal = ManagerPrincipal(
        subject_id='manager-user',
        display_name='Manager User',
        access_keys=('alarms.manage',),
    )
    composition = compose_alarm_configuration_manager(
        source_store=SourceStoreStub(),
        projection_store=ProjectionStoreStub(),
        principal_provider=lambda: principal,
        source_key=source_key,
        group_key='configuration',
        access_key='alarms.manage',
    )

    module = composition.module
    services = ServiceRegistry()
    assert module.web_module is not None
    assert module.web_module.register_services is not None
    module.web_module.register_services(services)

    assert module.source_key == source_key
    assert module.source_service == ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE
    assert module.projection_service == ALARM_CONFIGURATION_MANAGER_PROJECTION_SERVICE
    assert module.draft_validation_service == ALARM_CONFIGURATION_MANAGER_VALIDATION_SERVICE
    assert (
        services.require(ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE) is composition.source_workflow
    )
    assert (
        services.require(ALARM_CONFIGURATION_MANAGER_PROJECTION_SERVICE)
        is composition.projection_service
    )
    assert (
        services.require(ALARM_CONFIGURATION_MANAGER_VALIDATION_SERVICE)
        is composition.validation_workflow
    )
