# Puerto abstracto de Source.
# Mantiene el contrato independiente de cualquier provider durable concreto.
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


# Puerto neutral que cualquier provider durable debe implementar con las mismas invariantes.
class SourceStore(ABC):
    @abstractmethod
    # Lee manifest de forma atómica: ausencia significa Source todavía no publicada.
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
    # Materializa primero; después compara el token bajo lock y solo entonces reemplaza manifest.
    def publish(self, request: PublishRequest) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    # Recorre únicamente previous_published_release; nunca lista carpetas para inventar History.
    def query_history(self, query: HistoryQuery) -> HistoryPage:
        raise NotImplementedError

    @abstractmethod
    # Verifica metadata, presencia, tamaño, digest y hash agregado sin cambiar Source.
    def verify_release(
        self,
        source_key: SourceKey,
        release_ref: SourceReleaseRef,
    ) -> IntegrityResult:
        raise NotImplementedError
