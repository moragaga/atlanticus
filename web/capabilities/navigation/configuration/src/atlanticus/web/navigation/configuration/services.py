from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from atlanticus.web.navigation.configuration.bundle import NavigationConfigurationBundle
from atlanticus.web.navigation.configuration.contracts import (
    NavigationAuditActorProvider,
    NavigationConfigurationPublisher,
    NavigationConfigurationSource,
    NavigationProjectionRepository,
)
from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationProjectionError,
    NavigationConfigurationSourceError,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.projection import (
    NavigationAuditRecord,
    NavigationConfigurationProjection,
    NavigationDraftValidationResult,
    NavigationProjectionExecutionResult,
    NavigationProjectionIssue,
    NavigationProjectionStatus,
    NavigationProjectionSummaryItem,
    NavigationSourcePublicationResult,
)

NavigationConfigurationValidator = Callable[
    [NavigationConfigurationCatalog],
    tuple[NavigationProjectionIssue, ...],
]


@dataclass(frozen=True, slots=True)
class NavigationConfigurationServices:
    administration: NavigationAdministrationService
    projection_workflow: NavigationProjectionWorkflow
    projection: NavigationProjectionRepository


class NavigationAdministrationService:
    def __init__(
        self,
        *,
        source: NavigationConfigurationSource,
        publisher: NavigationConfigurationPublisher,
        audit_actor_provider: NavigationAuditActorProvider,
        validators: tuple[NavigationConfigurationValidator, ...] = (),
    ) -> None:
        self._source = source
        self._publisher = publisher
        self._audit_actor_provider = audit_actor_provider
        self._validators = validators

    def load_source(self) -> NavigationConfigurationBundle | None:
        return self._source.fetch_bundle()

    def load_catalog(self) -> NavigationConfigurationCatalog | None:
        bundle = self.load_source()
        return bundle.catalog if bundle is not None else None

    def validate_catalog(
        self,
        catalog: NavigationConfigurationCatalog,
    ) -> NavigationDraftValidationResult:
        audit = NavigationAuditRecord(
            actor=self._audit_actor_provider(),
            occurred_at_utc=datetime.now(UTC),
        )
        issues = _validate_catalog(catalog, self._validators)
        return NavigationDraftValidationResult(
            draft_revision=_build_draft_revision(catalog),
            valid=not any(issue.level == 'error' for issue in issues),
            audit=audit,
            issues=issues,
            summary=_catalog_summary(catalog),
        )

    def publish_catalog(
        self,
        catalog: NavigationConfigurationCatalog,
        *,
        expected_source_revision: str | None,
    ) -> NavigationSourcePublicationResult:
        validation = self.validate_catalog(catalog)
        if not validation.valid:
            raise NavigationConfigurationSourceError(
                'Navigation draft is not valid for publication'
            )
        current = self._source.fetch_bundle()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_source_revision:
            raise NavigationConfigurationSourceError(
                'Navigation source revision changed before publication'
            )
        bundle = NavigationConfigurationBundle.create(
            catalog=catalog,
            saved_by=validation.audit.actor,
            now_utc=validation.audit.occurred_at_utc,
        )
        published = current_revision != bundle.revision
        self._publisher.publish_bundle(
            bundle,
            expected_source_revision=expected_source_revision,
        )
        return NavigationSourcePublicationResult(
            source_revision=bundle.revision,
            published=published,
            audit=validation.audit,
            summary=validation.summary,
        )

    def list_history(self, *, limit: int = 20) -> tuple[NavigationConfigurationBundle, ...]:
        return self._source.list_history(limit=limit)

    def load_revision_catalog(self, revision: str) -> NavigationConfigurationCatalog:
        bundle = self._source.fetch_revision(revision)
        if bundle is None:
            raise NavigationConfigurationSourceError(
                'Navigation configuration revision does not exist'
            )
        return bundle.catalog


class NavigationProjectionWorkflow:
    def __init__(
        self,
        *,
        source: NavigationConfigurationSource,
        projection: NavigationProjectionRepository,
        audit_actor_provider: NavigationAuditActorProvider,
        validators: tuple[NavigationConfigurationValidator, ...] = (),
    ) -> None:
        self._source = source
        self._projection = projection
        self._audit_actor_provider = audit_actor_provider
        self._validators = validators

    def get_status(self) -> NavigationProjectionStatus:
        bundle = self._source.fetch_bundle()
        projection = self._projection.load()
        return NavigationProjectionStatus(
            source_revision=bundle.revision if bundle is not None else None,
            source_audit=(
                NavigationAuditRecord(
                    actor=bundle.saved_by,
                    occurred_at_utc=bundle.saved_at_utc,
                )
                if bundle is not None
                else None
            ),
            active_revision=projection.revision if projection is not None else None,
            active_source_revision=(projection.source_revision if projection is not None else None),
            projection_audit=(
                NavigationAuditRecord(
                    actor=projection.projected_by,
                    occurred_at_utc=projection.projected_at_utc,
                )
                if projection is not None
                else None
            ),
        )

    def project(self, expected_source_revision: str) -> NavigationProjectionExecutionResult:
        expected = expected_source_revision.strip()
        if not expected:
            raise NavigationConfigurationProjectionError(
                'Expected navigation source revision must not be empty'
            )
        bundle = self._require_source(expected)
        issues = _validate_catalog(bundle.catalog, self._validators)
        if any(issue.level == 'error' for issue in issues):
            raise NavigationConfigurationProjectionError(
                'Published navigation configuration is not valid for projection'
            )
        actor = self._audit_actor_provider()
        self._require_source(expected)
        projection = NavigationConfigurationProjection.create(
            source_revision=bundle.revision,
            projected_by=actor,
            catalog=bundle.catalog,
        )
        saved = self._projection.save(projection)
        self._require_source(expected)
        return NavigationProjectionExecutionResult(
            source_revision=bundle.revision,
            projection_revision=saved.revision,
            projected=True,
            audit=NavigationAuditRecord(
                actor=saved.projected_by,
                occurred_at_utc=saved.projected_at_utc,
            ),
            summary=_catalog_summary(bundle.catalog),
        )

    def _require_source(self, expected_revision: str) -> NavigationConfigurationBundle:
        bundle = self._source.fetch_bundle()
        if bundle is None:
            raise NavigationConfigurationSourceError(
                'Navigation configuration source does not exist'
            )
        if bundle.revision != expected_revision:
            raise NavigationConfigurationProjectionError(
                'Navigation source revision changed before projection'
            )
        return bundle


def compose_navigation_configuration_services(
    *,
    source: NavigationConfigurationSource,
    publisher: NavigationConfigurationPublisher,
    projection: NavigationProjectionRepository,
    audit_actor_provider: NavigationAuditActorProvider,
    validators: tuple[NavigationConfigurationValidator, ...] = (),
) -> NavigationConfigurationServices:
    return NavigationConfigurationServices(
        administration=NavigationAdministrationService(
            source=source,
            publisher=publisher,
            audit_actor_provider=audit_actor_provider,
            validators=validators,
        ),
        projection_workflow=NavigationProjectionWorkflow(
            source=source,
            projection=projection,
            audit_actor_provider=audit_actor_provider,
            validators=validators,
        ),
        projection=projection,
    )


def _validate_catalog(
    catalog: NavigationConfigurationCatalog,
    validators: tuple[NavigationConfigurationValidator, ...],
) -> tuple[NavigationProjectionIssue, ...]:
    issues = list(_intrinsic_issues(catalog))
    for validator in validators:
        issues.extend(validator(catalog))
    return tuple(issues)


def _intrinsic_issues(
    catalog: NavigationConfigurationCatalog,
) -> tuple[NavigationProjectionIssue, ...]:
    catalog.to_definition()
    return ()


def _catalog_summary(
    catalog: NavigationConfigurationCatalog,
) -> tuple[NavigationProjectionSummaryItem, ...]:
    links = (*catalog.links, *(link for group in catalog.groups for link in group.links))
    return (
        NavigationProjectionSummaryItem('Secciones', str(len(catalog.groups))),
        NavigationProjectionSummaryItem('Enlaces', str(len(links))),
        NavigationProjectionSummaryItem(
            'Perfiles configurados',
            str(len(catalog.configured_profiles())),
        ),
    )


def _build_draft_revision(catalog: NavigationConfigurationCatalog) -> str:
    canonical = json.dumps(
        catalog.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()
