from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import ada.processes.kpi_delivery.composition as composition_module
from ada.kpis.delivery import KpiDeliveryConfiguration
from ada.processes.kpi_delivery.composition import KpiDeliveryComposition, build_composition
from ada.processes.kpi_delivery.storage import (
    KPI_LATEST_DELIVERY_CONTAINER_SPEC,
    KPI_REGISTRY_CONTAINER_SPEC,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(tmp_path) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-delivery-local',
        'VOLUMEN_PATH': str(tmp_path),
        'KPI_RUNTIME_APPLICATION': 'ada-kpi-runtime-local',
        'COSMOS_CONSUMPTION_ENDPOINT': 'http://localhost:8081',
        'COSMOS_CONSUMPTION_KEY': 'local-key',
        'COSMOS_CONSUMPTION_DATABASE_NAME': 'ada',
        'KPI_DELIVERY_POLL_INTERVAL_SECONDS': '1',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


class ProvisionerStub:
    def __init__(self) -> None:
        self.validated = []
        self.ensured = []

    def validate_containers(self, specs) -> None:
        self.validated.append(tuple(specs))

    def ensure_containers(self, specs):
        normalized = tuple(specs)
        self.ensured.append(normalized)
        return tuple(spec.name for spec in normalized)


class RegistryStub:
    def __init__(self, configuration) -> None:
        self.configuration = configuration
        self.calls = 0

    def read(self):
        self.calls += 1
        return self.configuration


class ReaderStub:
    def read(self, *_args, **_kwargs):
        return None


class CheckpointStub(ReaderStub):
    def commit(self, value):
        return value


class PublisherStub:
    def publish(self, value):
        return value


def test_composition_separates_own_runtime_from_kpi_runtime_authority(tmp_path) -> None:
    composition = build_composition(configuration=_configuration(tmp_path))

    assert composition.definition.module_name == 'ada.processes.kpi_delivery'
    assert composition.definition.service_name == 'kpi-delivery'
    assert composition.definition.job_key == 'kpi-delivery'
    assert composition.definition.sleep_seconds == 1
    assert composition.evaluations.paths.application_root == tmp_path / 'ada-kpi-runtime-local'
    assert composition.runtime_configuration.application == 'ada-kpi-delivery-local'
    assert composition.snapshots.container_name == KPI_LATEST_DELIVERY_CONTAINER_SPEC.name


def test_execute_validates_registry_and_ensures_only_owned_output_before_job(monkeypatch) -> None:
    configuration = KpiDeliveryConfiguration(revision='r1', bindings=())
    provisioner = ProvisionerStub()
    registry = RegistryStub(configuration)
    result = object()
    monkeypatch.setattr(composition_module, 'execute_job', lambda **_kwargs: result)
    composition = KpiDeliveryComposition(
        configuration=SimpleNamespace(values={}),
        runtime_configuration=SimpleNamespace(values={}),
        settings=object(),
        registry_repository=registry,
        kpi_state=ReaderStub(),
        evaluations=ReaderStub(),
        checkpoint=CheckpointStub(),
        snapshots=PublisherStub(),
        definition=object(),
        cosmos_client=nullcontext(),
        cosmos_provisioner=provisioner,
    )

    assert composition.execute() is result
    assert provisioner.validated == [(KPI_REGISTRY_CONTAINER_SPEC,)]
    assert provisioner.ensured == [(KPI_LATEST_DELIVERY_CONTAINER_SPEC,)]
    assert registry.calls == 1
