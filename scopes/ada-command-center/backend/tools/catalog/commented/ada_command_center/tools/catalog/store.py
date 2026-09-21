# Frontera de persistencia del catálogo.
# El consolidator depende de este contrato y no conoce Azure ni Blob Storage.
# Esto permite probar la consolidación sin infraestructura externa.

from __future__ import annotations

from abc import ABC, abstractmethod

from ada_command_center.tools.catalog.models import ToolCatalogSnapshot


class ToolCatalogStore(ABC):
    @abstractmethod
    def get_current(self) -> ToolCatalogSnapshot | None:
        raise NotImplementedError

    @abstractmethod
    def replace_current(self, snapshot: ToolCatalogSnapshot) -> ToolCatalogSnapshot:
        raise NotImplementedError
