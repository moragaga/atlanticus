from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.contracts.tools.errors import ToolConfigurationValidationError
from ada.contracts.tools.validation import require_key


@dataclass(frozen=True, slots=True)
class ToolRenderTopology:
    bottom_component_key: str | None = None

    def __post_init__(self) -> None:
        if self.bottom_component_key is None:
            return
        object.__setattr__(
            self,
            'bottom_component_key',
            require_key(
                self.bottom_component_key,
                label='Tool render bottom component key',
            ),
        )

    def to_document(self) -> dict[str, str]:
        if self.bottom_component_key is None:
            return {}
        return {'bottom_component_key': self.bottom_component_key}

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolRenderTopology:
        try:
            return cls(bottom_component_key=document.get('bottom_component_key'))
        except (TypeError, ValueError) as error:
            if isinstance(error, ToolConfigurationValidationError):
                raise
            raise ToolConfigurationValidationError(
                'Tool render topology contract is invalid'
            ) from error
