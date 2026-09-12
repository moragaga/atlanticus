from __future__ import annotations

from abc import ABC, abstractmethod

from atlanticus.web.source.models import (
    HistoryPage,
    HistoryQuery,
    IntegrityResult,
    PublishRequest,
    PublishResult,
    SourceKey,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceResource,
    SourceSnapshot,
)


class SourceStore(ABC):
    @abstractmethod
    def get_current(self, source_key: SourceKey) -> SourceSnapshot:
        raise NotImplementedError

    @abstractmethod
    def read_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> tuple[SourceReleaseMetadata, tuple[SourceResource, ...]]:
        raise NotImplementedError

    @abstractmethod
    def publish(self, request: PublishRequest) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    def query_history(self, query: HistoryQuery) -> HistoryPage:
        raise NotImplementedError

    @abstractmethod
    def verify_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> IntegrityResult:
        raise NotImplementedError
