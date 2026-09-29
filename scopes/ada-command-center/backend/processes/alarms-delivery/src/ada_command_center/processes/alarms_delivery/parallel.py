from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings


class _CosmosWriter(Protocol):
    def __enter__(self) -> _CosmosWriter: ...

    def __exit__(self, *_: object) -> None: ...

    def upsert_item(self, *, container_name: str, item: Mapping[str, object]) -> object: ...


@dataclass(frozen=True, slots=True)
class CosmosDispatchTask:
    tool_key: str
    connection_ref: str
    container_name: str
    documents: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        for field in ('tool_key', 'connection_ref', 'container_name'):
            value = getattr(self, field)
            if not isinstance(value, str) or not value or value.strip() != value:
                raise ValueError(f'{field} must be non-empty text')
        if not isinstance(self.documents, tuple) or not self.documents:
            raise ValueError('documents must be a non-empty tuple')
        documents: list[dict[str, object]] = []
        for item in self.documents:
            if (
                not isinstance(item, Mapping)
                or not isinstance(item.get('id'), str)
                or not item['id']
            ):
                raise ValueError('Every Cosmos document must have an id')
            documents.append(deepcopy(dict(item)))
        object.__setattr__(self, 'documents', tuple(documents))


@dataclass(frozen=True, slots=True)
class CosmosDispatchResult:
    tool_key: str
    connection_ref: str
    published_documents: int
    error_type: str | None

    @property
    def successful(self) -> bool:
        return self.error_type is None


class ParallelCosmosPublisher:
    def __init__(
        self,
        *,
        connections: Mapping[str, CosmosSettings],
        max_workers: int,
        client_factory: Callable[[CosmosSettings], _CosmosWriter] | None = None,
    ) -> None:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
            raise ValueError('max_workers must be a positive integer')
        self._connections = dict(connections)
        self._factory = (
            client_factory
            if client_factory is not None
            else lambda settings: CosmosClient(settings=settings)
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix='alarm-cosmos'
        )
        self._closed = False

    def __enter__(self) -> ParallelCosmosPublisher:
        if self._closed:
            raise RuntimeError('Cosmos publisher is closed')
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=True)

    def publish(
        self,
        tasks: tuple[CosmosDispatchTask, ...],
        *,
        assert_authority: Callable[[], None],
    ) -> tuple[CosmosDispatchResult, ...]:
        if self._closed:
            raise RuntimeError('Cosmos publisher is closed')
        if not isinstance(tasks, tuple) or any(
            not isinstance(task, CosmosDispatchTask) for task in tasks
        ):
            raise TypeError('tasks must contain CosmosDispatchTask values')
        if len({task.tool_key for task in tasks}) != len(tasks):
            raise ValueError('Only one dispatch task per tool is allowed in a batch')
        if len({task.connection_ref for task in tasks}) != len(tasks):
            raise ValueError('A dispatch batch cannot share a Cosmos connection')
        if any(task.connection_ref not in self._connections for task in tasks):
            raise ValueError('Dispatch task refers to an unknown Cosmos connection')
        if not callable(assert_authority):
            raise TypeError('assert_authority must be callable')
        if not tasks:
            return ()
        assert_authority()
        future_to_task = {self._executor.submit(self._publish_one, task): task for task in tasks}
        results = []
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                published = future.result()
                results.append(
                    CosmosDispatchResult(task.tool_key, task.connection_ref, published, None)
                )
            except Exception as error:
                results.append(
                    CosmosDispatchResult(
                        task.tool_key, task.connection_ref, 0, type(error).__name__
                    )
                )
        assert_authority()
        return tuple(sorted(results, key=lambda result: result.tool_key))

    def _publish_one(self, task: CosmosDispatchTask) -> int:
        settings = self._connections[task.connection_ref]
        with self._factory(settings) as client:
            published = 0
            for document in task.documents:
                client.upsert_item(container_name=task.container_name, item=document)
                published += 1
        return published
