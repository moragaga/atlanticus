from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256

from ada.contracts.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.projection_record import (
    alarm_configuration_projection_from_document,
    alarm_configuration_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseRef


@dataclass(frozen=True, slots=True)
class AlarmMaterializationCandidate:
    _serialized_projection: bytes = field(repr=False)

    @classmethod
    def capture(
        cls,
        projection: ProjectionRecord[AlarmConfigurationSnapshot],
    ) -> AlarmMaterializationCandidate:
        document = alarm_configuration_projection_to_document(projection)
        serialized = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return cls(_serialized_projection=serialized)

    @property
    def projection(self) -> ProjectionRecord[AlarmConfigurationSnapshot]:
        return alarm_configuration_projection_from_document(json.loads(self._serialized_projection))

    @property
    def source_key(self) -> SourceKey:
        return self.projection.source_key

    @property
    def source_release(self) -> SourceReleaseRef:
        return self.projection.source_release

    @property
    def alarm_configuration_revision(self) -> str:
        return self.source_release.release_id.value

    @property
    def confirmed_tool_catalog_revision(self) -> str:
        return self.projection.payload.tool_dependencies.revision

    @property
    def fingerprint(self) -> str:
        return sha256(self._serialized_projection).hexdigest()
