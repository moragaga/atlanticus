# El lector devuelve READY verificado sin convertirlo en EFFECTIVE.
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
from ada_command_center.processes.alarms_runtime.adoption import AlarmConfigurationRevision
from ada_command_center.processes.alarms_runtime.session import (
    AlarmEvaluatorRegistry,
    build_alarm_execution_session,
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
