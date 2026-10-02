from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.kpis.delivery import KpiLatestSnapshot
from ada.processes.kpi_delivery.errors import KpiDeliveryRepositoryError
from ada.processes.kpi_delivery.models import (
    KpiLatestPublication,
    KpiLatestPublicationStatus,
)
from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosConflictError,
    CosmosPatchOperation,
    CosmosPreconditionFailedError,
)


@dataclass(slots=True)
class KpiLatestSnapshotRepository:
    client: CosmosClient
    container_name: str

    def publish(self, snapshot: KpiLatestSnapshot) -> KpiLatestPublication:
        if not isinstance(snapshot, KpiLatestSnapshot):
            raise TypeError('snapshot must be KpiLatestSnapshot')
        payload = snapshot.to_payload()
        item_id = _required_text(payload.get('id'), 'snapshot id')
        partition_key = _required_text(payload.get('partition_id'), 'snapshot partition_id')
        desired_revision = snapshot.manifest.revision
        current = self.client.find_item(
            container_name=self.container_name,
            item_id=item_id,
            partition_key=partition_key,
            include_metadata=True,
        )
        if current is None:
            return self._create_or_resolve_conflict(
                payload=payload,
                item_id=item_id,
                partition_key=partition_key,
                desired_revision=desired_revision,
            )
        current_revision, etag = _current_identity(
            current,
            item_id=item_id,
            partition_key=partition_key,
        )
        if current_revision == desired_revision:
            return KpiLatestPublication(
                status=KpiLatestPublicationStatus.UNCHANGED,
                revision=desired_revision,
            )
        try:
            self.client.patch_item(
                container_name=self.container_name,
                item_id=item_id,
                partition_key=partition_key,
                operations=(
                    CosmosPatchOperation('replace', '/manifest', payload['manifest']),
                    CosmosPatchOperation('replace', '/destinations', payload['destinations']),
                ),
                if_match_etag=etag,
            )
        except CosmosPreconditionFailedError:
            return self._resolve_concurrent_write(
                item_id=item_id,
                partition_key=partition_key,
                desired_revision=desired_revision,
            )
        return KpiLatestPublication(
            status=KpiLatestPublicationStatus.PUBLISHED,
            revision=desired_revision,
        )

    def _create_or_resolve_conflict(
        self,
        *,
        payload: Mapping[str, Any],
        item_id: str,
        partition_key: str,
        desired_revision: str,
    ) -> KpiLatestPublication:
        try:
            self.client.create_item(container_name=self.container_name, item=payload)
        except CosmosConflictError:
            return self._resolve_concurrent_write(
                item_id=item_id,
                partition_key=partition_key,
                desired_revision=desired_revision,
            )
        return KpiLatestPublication(
            status=KpiLatestPublicationStatus.PUBLISHED,
            revision=desired_revision,
        )

    def _resolve_concurrent_write(
        self,
        *,
        item_id: str,
        partition_key: str,
        desired_revision: str,
    ) -> KpiLatestPublication:
        current = self.client.find_item(
            container_name=self.container_name,
            item_id=item_id,
            partition_key=partition_key,
            include_metadata=True,
        )
        if current is None:
            raise KpiDeliveryRepositoryError(
                'KPI latest snapshot disappeared during concurrent publication'
            )
        current_revision, _ = _current_identity(
            current,
            item_id=item_id,
            partition_key=partition_key,
        )
        if current_revision == desired_revision:
            return KpiLatestPublication(
                status=KpiLatestPublicationStatus.UNCHANGED,
                revision=desired_revision,
            )
        raise KpiDeliveryRepositoryError('KPI latest snapshot changed concurrently')


def _current_identity(
    document: Mapping[str, Any],
    *,
    item_id: str,
    partition_key: str,
) -> tuple[str, str]:
    if document.get('id') != item_id:
        raise KpiDeliveryRepositoryError('existing KPI latest snapshot id is invalid')
    if document.get('partition_id') != partition_key:
        raise KpiDeliveryRepositoryError('existing KPI latest snapshot partition_id is invalid')
    if document.get('document_type') != 'ada_kpi_latest_delivery':
        raise KpiDeliveryRepositoryError('existing KPI latest snapshot document_type is invalid')
    destinations = document.get('destinations')
    if not isinstance(destinations, Mapping):
        raise KpiDeliveryRepositoryError('existing KPI latest snapshot destinations are invalid')
    manifest = document.get('manifest')
    if not isinstance(manifest, Mapping):
        raise KpiDeliveryRepositoryError('existing KPI latest snapshot manifest is invalid')
    revision = manifest.get('revision')
    if not isinstance(revision, str) or not revision or revision != revision.strip():
        raise KpiDeliveryRepositoryError('existing KPI latest snapshot revision is invalid')
    etag = document.get('_etag')
    if not isinstance(etag, str) or not etag:
        raise KpiDeliveryRepositoryError('existing KPI latest snapshot ETag is missing')
    return revision, etag


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise KpiDeliveryRepositoryError(f'{field_name} must be a non-empty string')
    if value != value.strip():
        raise KpiDeliveryRepositoryError(f'{field_name} must not contain surrounding whitespace')
    return value
