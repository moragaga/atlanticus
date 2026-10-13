# Espejo pedagógico: adoption.py. Misma lógica ejecutable que src, con explicaciones en español.
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Any, Protocol

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOGGER = logging.getLogger(__name__)
ADOPTION_MODE_VARIABLE = 'ADA_TOOL_ADOPTION_MODE'


# Define los dos modos admitidos; startup mantiene el comportamiento vigente y on_page_load es optativo.
class ToolAdoptionMode(StrEnum):
    STARTUP = 'startup'
    ON_PAGE_LOAD = 'on_page_load'


# Lee la variable también desde .env y la valida antes de crear el runtime.
class ToolAdoptionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        frozen=True,
    )
    mode: ToolAdoptionMode = Field(
        default=ToolAdoptionMode.STARTUP,
        validation_alias=ADOPTION_MODE_VARIABLE,
    )


@dataclass(frozen=True, slots=True)
# Representa la revisión activa y si la proyección puede adoptarse con seguridad.
class ToolRevision:
    eligible: bool
    release_id: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.eligible, bool):
            raise TypeError('eligible must be bool')
        if self.release_id is not None and (
            not isinstance(self.release_id, str) or not self.release_id
        ):
            raise ValueError('release_id must be non-empty text or None')
        if not self.eligible and self.release_id is not None:
            raise ValueError('ineligible Tool revision cannot contain a release_id')


# Describe la superficie mínima de un worker sin acoplarse a Flask o a Dash.
class WorkerRuntime(Protocol):
    application: Any
    server: Any

    # La operación es idempotente y preserva el cierre del iterable WSGI original.
    def close(self) -> None: ...


@dataclass(slots=True)
# Agrupa un worker, la aplicación WSGI y el número de peticiones en curso.
class _Generation:
    worker: WorkerRuntime
    wsgi: Callable[..., Iterable[bytes]]
    revision: ToolRevision
    in_flight: int = 0
    retired: bool = False


# Retrasa la liberación de recursos hasta que el servidor termina de consumir la respuesta.
class _ManagedResponse(Iterator[bytes]):
    def __init__(self, iterable: Iterable[bytes], release: Callable[[], None]) -> None:
        self._iterable = iterable
        self._iterator = iter(iterable)
        self._release = release
        self._closed = False

    def __iter__(self) -> _ManagedResponse:
        return self

    # La respuesta libera sus recursos incluso si la iteración termina por excepción.
    def __next__(self) -> bytes:
        if self._closed:
            raise StopIteration
        try:
            return next(self._iterator)
        except BaseException:
            self.close()
            raise

    # La operación es idempotente y preserva el cierre del iterable WSGI original.
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            close = getattr(self._iterable, 'close', None)
            if callable(close):
                close()
        finally:
            self._release()


# Conserva un servidor Flask estable y cambia internamente la generación operacional activa.
class ToolAdoptingWorkerRuntime:
    def __init__(
        self,
        *,
        initial: WorkerRuntime,
        revision_reader: Callable[[], ToolRevision],
        worker_factory: Callable[[], WorkerRuntime],
    ) -> None:
        if not callable(revision_reader) or not callable(worker_factory):
            raise TypeError('Tool adoption requires callable revision reader and worker factory')
        self.application = initial.application
        self.server = initial.server
        self._revision_reader = revision_reader
        self._worker_factory = worker_factory
        self._state_lock = Lock()
        self._adoption_lock = Lock()
        self._closed = False
        self._active = _Generation(
            initial,
            self.server.wsgi_app,
            revision_reader(),
        )
        self._retired: list[_Generation] = []
        self.server.wsgi_app = self._dispatch

    @property
    def active_revision(self) -> ToolRevision:
        with self._state_lock:
            return self._active.revision

    # Solo la navegación HTML provoca una consulta de revisión; todas las demás peticiones se delegan directamente.
    def _dispatch(self, environ: Mapping[str, Any], start_response: Callable[..., Any]):
        if _is_document_navigation(environ):
            self._adopt_if_changed()
        with self._state_lock:
            if self._closed:
                raise RuntimeError('Tool adoption runtime is closed')
            generation = self._active
            generation.in_flight += 1
        try:
            response = generation.wsgi(environ, start_response)
            return _ManagedResponse(response, lambda: self._release(generation))
        except BaseException:
            self._release(generation)
            raise

    # Prepara la nueva aplicación completamente antes de sustituirla, sin modificar callbacks activos.
    def _adopt_if_changed(self) -> None:
        with self._adoption_lock:
            with self._state_lock:
                if self._closed:
                    return
                previous = self._active
            try:
                revision = self._revision_reader()
            except Exception as error:
                _LOGGER.warning('Tool adoption revision lookup failed (%s)', type(error).__name__)
                return
            if not revision.eligible:
                _LOGGER.warning('Tool adoption skipped: active projection is not ready')
                return
            if revision == previous.revision:
                return
            try:
                candidate = self._worker_factory()
            except Exception as error:
                _LOGGER.error('Tool adoption build failed (%s)', type(error).__name__)
                return
            try:
                confirmed = self._revision_reader()
            except Exception as error:
                _LOGGER.warning('Tool adoption confirmation failed (%s)', type(error).__name__)
                _close_worker(candidate)
                return
            if confirmed != revision:
                _LOGGER.warning('Tool adoption revision changed during preparation')
                _close_worker(candidate)
                return
            generation = _Generation(candidate, candidate.server.wsgi_app, revision)
            with self._state_lock:
                if self._closed:
                    retire_candidate = True
                    close_previous = False
                else:
                    retire_candidate = False
                    previous = self._active
                    previous.retired = True
                    self._active = generation
                    close_previous = previous.in_flight == 0
                    if not close_previous:
                        self._retired.append(previous)
            if retire_candidate:
                _close_worker(candidate)
                return
            if close_previous:
                _close_worker(previous.worker)
            _LOGGER.info('Tool adopted from projection revision: %s', revision.release_id)

    # Libera una generación retirada solo cuando no queden peticiones utilizándola.
    def _release(self, generation: _Generation) -> None:
        retired_worker = None
        with self._state_lock:
            generation.in_flight -= 1
            if generation.in_flight < 0:
                raise RuntimeError('Tool adoption in-flight request count is invalid')
            if generation.in_flight == 0 and generation.retired:
                if generation in self._retired:
                    self._retired.remove(generation)
                retired_worker = generation.worker
                generation.retired = False
        if retired_worker is not None:
            _close_worker(retired_worker)

    # La operación es idempotente y preserva el cierre del iterable WSGI original.
    def close(self) -> None:
        with self._adoption_lock:
            with self._state_lock:
                if self._closed:
                    return
                self._closed = True
                active = self._active
                active.retired = True
                if active.in_flight:
                    self._retired.append(active)
                    close_active = False
                else:
                    close_active = True
                retired = [generation for generation in self._retired if generation.in_flight == 0]
                self._retired = [generation for generation in self._retired if generation.in_flight]
            if close_active:
                _close_worker(active.worker)
            for generation in retired:
                _close_worker(generation.worker)


# Detiene los pollers de los collectors antes de cerrar las conexiones y demás recursos del worker.
def _close_worker(worker: WorkerRuntime) -> None:
    services = getattr(worker.application, 'services', None)
    if services is not None:
        for service_key in ('ada.kpi.collector.runtime', 'ada.alarm.collector.runtime'):
            if services.contains(service_key):
                try:
                    services.require(service_key).stop()
                except Exception as error:
                    _LOGGER.warning('Collector stop failed (%s)', type(error).__name__)
    try:
        worker.close()
    except Exception as error:
        _LOGGER.error('Tool adoption worker cleanup failed (%s)', type(error).__name__)


# Filtra assets, endpoints internos de Dash, health, API y peticiones no HTML.
def _is_document_navigation(environ: Mapping[str, Any]) -> bool:
    if environ.get('REQUEST_METHOD') != 'GET':
        return False
    accept = environ.get('HTTP_ACCEPT', '')
    if 'text/html' not in accept.lower():
        return False
    path = environ.get('PATH_INFO', '/')
    if not isinstance(path, str):
        return False
    excluded = ('/_dash-', '/assets/', '/health/', '/.auth/', '/favicon', '/logout')
    return not path.startswith(excluded) and not path.startswith('/api/')
