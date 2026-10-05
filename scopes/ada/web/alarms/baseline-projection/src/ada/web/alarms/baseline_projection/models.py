from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.alarms.baseline_projection.errors import AlarmBaselineProjectionError


class AlarmBaselineAnchorKind(StrEnum):
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
    main_points: tuple[AlarmBaselinePoint, ...]
    bottom_point: AlarmBaselinePoint | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_key, str) or not self.tool_key.strip():
            raise AlarmBaselineProjectionError('Alarm baseline tool key is required')
        if not isinstance(self.kind, ToolConfigurationKind):
            raise AlarmBaselineProjectionError('Alarm baseline Tool kind is invalid')

        main_points = tuple(self.main_points)
        if not main_points:
            raise AlarmBaselineProjectionError('Alarm baseline requires main points')
        if any(not isinstance(point, AlarmBaselinePoint) for point in main_points):
            raise AlarmBaselineProjectionError(
                'Alarm baseline main points must contain AlarmBaselinePoint values'
            )
        if self.bottom_point is not None:
            if not isinstance(self.bottom_point, AlarmBaselinePoint):
                raise AlarmBaselineProjectionError(
                    'Alarm baseline bottom point must be an AlarmBaselinePoint value'
                )
            if self.kind is not ToolConfigurationKind.PROCESS:
                raise AlarmBaselineProjectionError(
                    'Alarm baseline bottom point is only supported for Process'
                )

        points = (
            main_points
            if self.bottom_point is None
            else (*main_points, self.bottom_point)
        )
        anchors = tuple((point.anchor_kind, point.anchor_key) for point in points)
        if len(anchors) != len(set(anchors)):
            raise AlarmBaselineProjectionError('Alarm baseline contains duplicate anchors')
        component_keys = tuple(point.component_key for point in points)
        if len(component_keys) != len(set(component_keys)):
            raise AlarmBaselineProjectionError('Alarm baseline contains duplicate component keys')

        object.__setattr__(self, 'tool_key', self.tool_key.strip())
        object.__setattr__(self, 'main_points', main_points)

    @property
    def points(self) -> tuple[AlarmBaselinePoint, ...]:
        if self.bottom_point is None:
            return self.main_points
        return (*self.main_points, self.bottom_point)

    @property
    def main_component_keys(self) -> tuple[str, ...]:
        return tuple(point.component_key for point in self.main_points)

    @property
    def bottom_component_key(self) -> str | None:
        return None if self.bottom_point is None else self.bottom_point.component_key

    @property
    def component_keys(self) -> tuple[str, ...]:
        return tuple(point.component_key for point in self.points)

    def to_document(self) -> dict[str, object]:
        return {
            'tool_key': self.tool_key,
            'kind': self.kind.value,
            'main_points': [point.to_document() for point in self.main_points],
            'bottom_point': (
                None if self.bottom_point is None else self.bottom_point.to_document()
            ),
        }
