# El reader sólo observa la publicación actual del Modeler; no interpreta ni reescribe el WAL.
from __future__ import annotations

from pathlib import Path

from atlanticus.state import AtomicJsonStore

_CURRENT = 'current/latest.json'


# Responsabilidad delimitada: ModelerCurrentReader
class ModelerCurrentReader:
    # Método del componente: __init__
    def __init__(self, *, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError('Modeler output root must be an absolute Path')
        self._store = AtomicJsonStore(root_path=root, max_document_bytes=None)

    # Método del componente: read
    def read(self) -> dict[str, object] | None:
        return self._store.read(_CURRENT)
