from __future__ import annotations

import re
from dataclasses import dataclass

from ada_command_center.alarms.core import AlarmResolutionKey

_RESULT_PATTERN = re.compile(r'alarm-materialization-[0-9a-f]{64}')
_SHA256_PATTERN = re.compile(r'[0-9a-f]{64}')


@dataclass(frozen=True, slots=True)
class AlarmConfigurationArtifactRef:
    source_key: str
    result_id: str
    manifest_sha256: str
    resolution_key: AlarmResolutionKey

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_key, str)
            or not self.source_key
            or self.source_key.strip() != self.source_key
        ):
            raise ValueError('source_key must be non-empty text without surrounding whitespace')
        if not isinstance(self.result_id, str) or _RESULT_PATTERN.fullmatch(self.result_id) is None:
            raise ValueError('result_id must identify one materialization result')
        if (
            not isinstance(self.manifest_sha256, str)
            or _SHA256_PATTERN.fullmatch(self.manifest_sha256) is None
        ):
            raise ValueError('manifest_sha256 must be a lowercase SHA-256 digest')
        if not isinstance(self.resolution_key, AlarmResolutionKey):
            raise TypeError('resolution_key must be an AlarmResolutionKey')
