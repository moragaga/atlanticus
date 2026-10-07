from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256

from ada.contracts.alarms import AlarmConfigurationProjection


@dataclass(frozen=True, slots=True)
class AlarmMaterializationCandidate:
    _serialized_projection: bytes = field(repr=False)

    @classmethod
    def capture(
        cls,
        projection: AlarmConfigurationProjection,
    ) -> AlarmMaterializationCandidate:
        if not isinstance(projection, AlarmConfigurationProjection):
            raise TypeError('projection must be an AlarmConfigurationProjection')
        serialized = json.dumps(
            projection.to_document(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return cls(_serialized_projection=serialized)

    @property
    def projection(self) -> AlarmConfigurationProjection:
        return AlarmConfigurationProjection.from_document(json.loads(self._serialized_projection))

    @property
    def source_key(self) -> str:
        return self.projection.source_key

    @property
    def source_release_id(self) -> str:
        return self.projection.source_release_id

    @property
    def alarm_configuration_revision(self) -> str:
        return self.source_release_id

    @property
    def confirmed_tool_catalog_revision(self) -> str:
        return self.projection.confirmed_tool_catalog_revision

    @property
    def fingerprint(self) -> str:
        return sha256(self._serialized_projection).hexdigest()
