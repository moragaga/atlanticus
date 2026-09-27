from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ada_command_center.alarms.materialization.local_reader import (
    LocalAlarmMaterializationReader,
    ReadyAlarmMaterialization,
    materialization_root,
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
