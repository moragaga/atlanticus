from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey

PayloadT = TypeVar('PayloadT')


class ProjectionStore(ABC, Generic[PayloadT]):
    @abstractmethod
    def get_active(self, source_key: SourceKey) -> ProjectionRecord[PayloadT] | None:
        raise NotImplementedError

    @abstractmethod
    def replace_active(
        self,
        projection: ProjectionRecord[PayloadT],
    ) -> ProjectionRecord[PayloadT]:
        raise NotImplementedError
