# El layout describe la composición lógica, no nombres de archivos ni un formato físico.
"""Layouts neutrales para una unidad lógica de publicación."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from atlanticus.datasets.core.errors import DatasetDefinitionError
from atlanticus.datasets.core.validation import (
    validate_dimension_name,
    validate_identity_segment,
)


@dataclass(frozen=True, slots=True)
class SingleArtifactLayout:
    """La publicación confirmada se representa mediante un único artefacto."""

    # El nombre es lógico; cada adapter físico decide su extensión.
    artifact_name: str = 'data'
    # El default conserva el contrato previo: una entrada vacía se omite.
    allow_empty: bool = False

    def __post_init__(self) -> None:
        validate_identity_segment(
            self.artifact_name,
            field='artifact_name',
            error_type=DatasetDefinitionError,
        )
        if not isinstance(self.allow_empty, bool):
            raise DatasetDefinitionError('allow_empty must be a boolean')


@dataclass(frozen=True, slots=True)
class FileSetLayout:
    """La publicación confirmada contiene partes identificadas por una dimensión."""

    # La dimensión es semántica; el adaptador puede conservar nombres físicos opacos.
    part_dimension: str

    def __post_init__(self) -> None:
        validate_dimension_name(
            self.part_dimension,
            field='part_dimension',
            error_type=DatasetDefinitionError,
        )


DatasetLayout: TypeAlias = SingleArtifactLayout | FileSetLayout
