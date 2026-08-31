from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.configuration.tools import ToolConfigurationKind, ToolScope
from ada.web.alarms.baseline_projection.errors import AlarmBaselineProjectionError


class AlarmBaselineAnchorKind(StrEnum):
    LAYOUT_ROLE = 'layout_role'
    COMPONENT = 'component'


@dataclass(frozen=True, slots=True)
class AlarmBaselinePoint:
    anchor_kind: AlarmBaselineAnchorKind
    anchor_key: str
    component_key: str
    display_name: str
    scope: ToolScope

    def __post_init__(self) -> None:
        if not isinstance(self.anchor_kind, AlarmBaselineAnchorKind):
            raise AlarmBaselineProjectionError('Alarm baseline anchor kind is invalid')
        if not isinstance(self.scope, ToolScope):
            raise AlarmBaselineProjectionError('Alarm baseline point scope is invalid')
        for label, value in (
            ('anchor key', self.anchor_key),
            ('component key', self.component_key),
            ('display name', self.display_name),
        ):
            if not isinstance(value, str) or not value.strip():
                raise AlarmBaselineProjectionError(f'Alarm baseline point {label} is required')
        object.__setattr__(self, 'anchor_key', self.anchor_key.strip())
        object.__setattr__(self, 'component_key', self.component_key.strip())
        object.__setattr__(self, 'display_name', self.display_name.strip())

    def to_document(self) -> dict[str, str]:
        return {
            'anchor_kind': self.anchor_kind.value,
            'anchor_key': self.anchor_key,
            'component_key': self.component_key,
            'display_name': self.display_name,
            'scope': self.scope.value,
        }


@dataclass(frozen=True, slots=True)
class AlarmBaselineProjection:
    tool_key: str
    kind: ToolConfigurationKind
    points: tuple[AlarmBaselinePoint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.tool_key, str) or not self.tool_key.strip():
            raise AlarmBaselineProjectionError('Alarm baseline tool key is required')
        if not isinstance(self.kind, ToolConfigurationKind):
            raise AlarmBaselineProjectionError('Alarm baseline Tool kind is invalid')
        points = tuple(self.points)
        if not points:
            raise AlarmBaselineProjectionError('Alarm baseline requires points')
        if any(not isinstance(point, AlarmBaselinePoint) for point in points):
            raise AlarmBaselineProjectionError(
                'Alarm baseline points must contain AlarmBaselinePoint values'
            )
        anchors = tuple((point.anchor_kind, point.anchor_key) for point in points)
        if len(anchors) != len(set(anchors)):
            raise AlarmBaselineProjectionError('Alarm baseline contains duplicate anchors')
        component_keys = tuple(point.component_key for point in points)
        if len(component_keys) != len(set(component_keys)):
            raise AlarmBaselineProjectionError('Alarm baseline contains duplicate component keys')
        object.__setattr__(self, 'tool_key', self.tool_key.strip())
        object.__setattr__(self, 'points', points)

    @property
    def component_keys(self) -> tuple[str, ...]:
        return tuple(point.component_key for point in self.points)

    def to_document(self) -> dict[str, object]:
        return {
            'tool_key': self.tool_key,
            'kind': self.kind.value,
            'points': [point.to_document() for point in self.points],
        }
