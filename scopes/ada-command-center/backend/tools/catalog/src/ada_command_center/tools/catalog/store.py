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
