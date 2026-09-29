from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ada_command_center.tools.catalog import (
    ToolCatalogConsolidator,
    ToolCatalogSnapshot,
    ToolCatalogStore,
)
from ada_command_center.tools.discovery_cosmos.connections import open_tool_catalog_discovery
from ada_command_center.tools.discovery_cosmos.discovery import (
    ToolCatalogDiscoveryError,
    ToolCatalogDiscoveryReport,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings

_REVISION = re.compile(r'[0-9a-f]{64}\Z')


class ToolCatalogManagerConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ToolCandidateSummary:
    connection_name: str
    tool_key: str
    display_name: str
    kind: str
    source_release_id: str


@dataclass(frozen=True, slots=True)
class ToolConnectionSummary:
    connection_name: str
    status: str
    issue: str | None
    tools: tuple[ToolCandidateSummary, ...]


@dataclass(frozen=True, slots=True)
class ToolCatalogReview:
    fingerprint: str
    current_revision: str | None
    can_confirm: bool
    issue: str | None
    connections: tuple[ToolConnectionSummary, ...]


@dataclass(frozen=True, slots=True)
class AdoptedToolCatalog:
    revision: str | None
    tools: tuple[ToolCandidateSummary, ...]


# Coordina inspecciones puntuales y la confirmación explícita del catálogo vigente.
class ToolCatalogManagerService:
    def __init__(
        self,
        *,
        catalog: ToolCatalogStore,
        connection_provider: Callable[[], Mapping[str, CosmosSettings]],
        client_factory: Callable[[CosmosSettings], CosmosClient] | None = None,
    ) -> None:
        if not isinstance(catalog, ToolCatalogStore):
            raise TypeError('catalog must be a ToolCatalogStore')
        if not callable(connection_provider):
            raise TypeError('connection_provider must be callable')
        self._catalog = catalog
        self._connection_provider = connection_provider
        self._client_factory = client_factory

    def _open_discovery(self):
        options = {'external_connections': self._connection_provider()}
        if self._client_factory is not None:
            options['client_factory'] = self._client_factory
        return open_tool_catalog_discovery(**options)

    # Una inspección abre y cierra clientes; no publica resultados.
    def inspect(self) -> ToolCatalogReview:
        with self._open_discovery() as discovery:
            report = discovery.inspect()
            current = self._catalog.get_current()
            return _review(report, current)

    # La confirmación repite el descubrimiento y comprueba el fingerprint recibido.
    def confirm(
        self,
        *,
        expected_fingerprint: str,
        expected_current_revision: str | None,
    ) -> AdoptedToolCatalog:
        if (
            not isinstance(expected_fingerprint, str)
            or _REVISION.fullmatch(expected_fingerprint) is None
        ):
            raise ToolCatalogManagerConflictError('Tool Catalog review is invalid')
        if expected_current_revision is not None and (
            not isinstance(expected_current_revision, str) or not expected_current_revision.strip()
        ):
            raise ToolCatalogManagerConflictError('Tool Catalog revision is invalid')
        with self._open_discovery() as discovery:
            report = discovery.inspect()
            current = self._catalog.get_current()
            review = _review(report, current)
            if (
                review.fingerprint != expected_fingerprint
                or review.current_revision != expected_current_revision
            ):
                raise ToolCatalogManagerConflictError(
                    'Tool Catalog candidates or current revision changed; inspect again'
                )
            if not review.can_confirm:
                raise ToolCatalogManagerConflictError(
                    'Tool Catalog review contains blocking issues'
                )
            inputs = report.consolidation_inputs(current=current)
            if _revision(self._catalog.get_current()) != expected_current_revision:
                raise ToolCatalogManagerConflictError('Current Tool Catalog changed; inspect again')
            confirmed = ToolCatalogConsolidator(
                inputs=inputs,
                store=self._catalog,
            ).refresh()
            return _adopted(confirmed)

    # Consulta exclusivamente la versión confirmada en el store existente.
    def adopted(self) -> AdoptedToolCatalog:
        return _adopted(self._catalog.get_current())


# Se calcula una huella del documento completo sin enviar ese documento al navegador.
def _review(
    report: ToolCatalogDiscoveryReport,
    current: ToolCatalogSnapshot | None,
) -> ToolCatalogReview:
    connections = tuple(
        ToolConnectionSummary(
            connection_name=item.connection_name,
            status=item.status.value,
            issue=item.issue.value if item.issue is not None else None,
            tools=tuple(
                ToolCandidateSummary(
                    connection_name=tool.connection_name,
                    tool_key=tool.tool_key,
                    display_name=tool.display_name,
                    kind=tool.kind,
                    source_release_id=tool.source_release_id.value,
                )
                for tool in item.tools
            ),
        )
        for item in report.connections
    )
    fingerprint_data = (
        (
            item.connection_name,
            item.status.value,
            item.issue.value if item.issue is not None else None,
            tuple(
                (
                    tool.namespace_key,
                    tool.tool_key,
                    tool.source_release_id.value,
                    tool.configuration.to_document(),
                )
                for tool in item.tools
            ),
        )
        for item in report.connections
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            (tuple(fingerprint_data), _revision(current)),
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
    ).hexdigest()
    try:
        report.consolidation_inputs(current=current)
    except ToolCatalogDiscoveryError:
        can_confirm = False
        issue = 'Discovery is incomplete, inconsistent, or requires reconciliation'
    else:
        can_confirm = True
        issue = None
    return ToolCatalogReview(
        fingerprint=fingerprint,
        current_revision=_revision(current),
        can_confirm=can_confirm,
        issue=issue,
        connections=connections,
    )


def _revision(current: ToolCatalogSnapshot | None) -> str | None:
    return None if current is None else current.revision


# El catálogo persistido no contiene la conexión de origen; no inventarla.
def _adopted(snapshot: ToolCatalogSnapshot | None) -> AdoptedToolCatalog:
    return AdoptedToolCatalog(
        revision=_revision(snapshot),
        tools=(
            ()
            if snapshot is None
            else tuple(
                ToolCandidateSummary(
                    connection_name='',
                    tool_key=tool.tool_key,
                    display_name=tool.display_name,
                    kind=tool.kind.value,
                    source_release_id=tool.source_release_id.value,
                )
                for tool in snapshot.tools
            )
        ),
    )
