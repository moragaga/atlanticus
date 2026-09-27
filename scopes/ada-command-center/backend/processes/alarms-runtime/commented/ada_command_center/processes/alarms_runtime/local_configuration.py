# READY sigue siendo sólo una candidata; la lectura EFFECTIVE se fija al WAL validado.
# La selección devuelve una revisión junto con su Head para validar vigencia antes de ejecutar.
# El constructor puro enlaza la identidad exacta y el registry explícito para producir una revisión planificable.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ada_command_center.alarms.materialization.artifact_reference import (
    AlarmConfigurationArtifactRef,
)
from ada_command_center.alarms.materialization.local_reader import (
    LocalAlarmMaterializationReader,
    ReadyAlarmMaterialization,
    materialization_root,
)
from ada_command_center.alarms.persistence import (
    AlarmEffectiveConfigurationHead,
    AlarmPersistence,
)
from ada_command_center.processes.alarms_runtime.adoption import AlarmConfigurationRevision
from ada_command_center.processes.alarms_runtime.session import (
    AlarmEvaluatorRegistry,
    build_alarm_execution_session,
)


class RuntimeEffectiveConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeEffectiveConfiguration:
    effective_head: AlarmEffectiveConfigurationHead
    revision: AlarmConfigurationRevision

    def __post_init__(self) -> None:
        if not isinstance(self.effective_head, AlarmEffectiveConfigurationHead):
            raise TypeError('effective_head must be AlarmEffectiveConfigurationHead')
        if not isinstance(self.revision, AlarmConfigurationRevision):
            raise TypeError('revision must be an AlarmConfigurationRevision')
        expected = self.effective_head.target_artifact_ref
        actual = self.revision.artifact_ref
        if (
            actual.source_key != expected.source_key
            or actual.result_id != expected.result_id
            or actual.manifest_sha256 != expected.manifest_sha256
            or actual.resolution_key.alarm_configuration_revision
            != expected.alarm_configuration_revision
            or actual.resolution_key.confirmed_tool_catalog_revision
            != expected.confirmed_tool_catalog_revision
        ):
            raise RuntimeEffectiveConfigurationError(
                'Runtime revision does not match the exact EFFECTIVE artifact'
            )


@dataclass(frozen=True, slots=True)
class RuntimeLocalConfigurationReader:
    volume_path: Path
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.volume_path, Path) or not self.volume_path.is_absolute():
            raise ValueError('VOLUMEN_PATH must be an absolute Path')
        if (
            not isinstance(self.source_key, str)
            or not self.source_key
            or self.source_key.strip() != self.source_key
        ):
            raise ValueError('Alarm source key must be non-empty text')

    def load_ready_candidate(self) -> ReadyAlarmMaterialization | None:
        return LocalAlarmMaterializationReader(
            root=materialization_root(self.volume_path)
        ).read_published_ready(source_key=self.source_key)

    def load_exact_candidate(
        self, *, result_id: str, manifest_sha256: str
    ) -> ReadyAlarmMaterialization:
        return LocalAlarmMaterializationReader(
            root=materialization_root(self.volume_path)
        ).read_exact_ready(
            source_key=self.source_key,
            result_id=result_id,
            manifest_sha256=manifest_sha256,
        )

    def load_effective_revision(
        self,
        *,
        persistence: AlarmPersistence,
        evaluator_registry: AlarmEvaluatorRegistry,
    ) -> RuntimeEffectiveConfiguration | None:
        self._require_persistence(persistence)
        if not isinstance(evaluator_registry, AlarmEvaluatorRegistry):
            raise TypeError('evaluator_registry must be an AlarmEvaluatorRegistry')
        head = persistence.read_effective_head()
        if head is None:
            return None
        pin = head.target_artifact_ref
        if pin.source_key != self.source_key:
            raise RuntimeEffectiveConfigurationError(
                'EFFECTIVE source_key does not match Runtime configuration reader'
            )
        candidate = self.load_exact_candidate(
            result_id=pin.result_id,
            manifest_sha256=pin.manifest_sha256,
        )
        selected = RuntimeEffectiveConfiguration(
            effective_head=head,
            revision=build_alarm_configuration_revision(
                candidate=candidate,
                evaluator_registry=evaluator_registry,
            ),
        )
        self.assert_current_effective(persistence=persistence, selected=selected)
        return selected

    def assert_current_effective(
        self, *, persistence: AlarmPersistence, selected: RuntimeEffectiveConfiguration
    ) -> None:
        self._require_persistence(persistence)
        if not isinstance(selected, RuntimeEffectiveConfiguration):
            raise TypeError('selected must be RuntimeEffectiveConfiguration')
        if persistence.read_effective_head() != selected.effective_head:
            raise RuntimeEffectiveConfigurationError(
                'EFFECTIVE changed after Runtime selected its configuration'
            )

    def _require_persistence(self, persistence: AlarmPersistence) -> None:
        if not isinstance(persistence, AlarmPersistence):
            raise TypeError('persistence must be AlarmPersistence')
        if persistence.paths.shared_volume_path != self.volume_path:
            raise ValueError('Runtime reader and Persistence must use the same VOLUMEN_PATH')


# El registry se inyecta explícitamente: los callables de evaluadores no se serializan en el artefacto.
# B1 construye la revisión y sesión para planificar, pero no ejecuta la adopción.
def build_alarm_configuration_revision(
    *,
    candidate: ReadyAlarmMaterialization,
    evaluator_registry: AlarmEvaluatorRegistry,
) -> AlarmConfigurationRevision:
    if not isinstance(candidate, ReadyAlarmMaterialization):
        raise TypeError('candidate must be a ReadyAlarmMaterialization')
    if not isinstance(evaluator_registry, AlarmEvaluatorRegistry):
        raise TypeError('evaluator_registry must be an AlarmEvaluatorRegistry')
    runtime = candidate.runtime
    key = runtime.resolution_key
    if (
        candidate.delivery.resolution_key != key
        or candidate.manifest.get('status') != 'READY'
        or candidate.manifest.get('result_id') != candidate.result_id
        or candidate.manifest.get('resolution_key')
        != {
            'alarm_configuration_revision': key.alarm_configuration_revision,
            'confirmed_tool_catalog_revision': key.confirmed_tool_catalog_revision,
        }
    ):
        raise ValueError('candidate materialization identity or resolution key is inconsistent')
    artifact_ref = AlarmConfigurationArtifactRef(
        source_key=candidate.manifest.get('source_key'),
        result_id=candidate.result_id,
        manifest_sha256=candidate.manifest_sha256,
        resolution_key=key,
    )
    session = build_alarm_execution_session(
        alarm_configuration_revision=key.alarm_configuration_revision,
        tool_registry_revision=key.confirmed_tool_catalog_revision,
        planned_alarms=runtime.planned_alarms,
        parameters_by_alarm=runtime.parameters_by_alarm,
        evaluator_registry=evaluator_registry,
    )
    return AlarmConfigurationRevision(
        artifact_ref=artifact_ref,
        defined_alarm_identities=runtime.defined_alarm_identities,
        session=session,
    )
