from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ada.configuration.tools import ToolConfiguration
from ada.web.application.configuration_manager import (
    NavigationManagerWorkflowAdapter,
    ToolConfigurationManagerWorkflowAdapter,
    UsersManagerWorkflowAdapter,
)
from atlanticus.web.manager import (
    ConfigurationLifecycleWorkflow,
    RevisionHistoryWorkflow,
)
from atlanticus.web.navigation.configuration import NavigationConfigurationCatalog
from atlanticus.web.users.configuration import UsersConfigurationCatalog

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


class AdministrationFake:
    def __init__(self, revision_value) -> None:
        self.revision_value = revision_value
        self.validated = None
        self.published = None
        self.expected_revision = None
        self.requested_revision = None
        self.requested_limit = None
        self.history = (
            SimpleNamespace(
                revision='source',
                saved_by='source-user',
                saved_at_utc=NOW,
            ),
            SimpleNamespace(
                revision='previous',
                saved_by='previous-user',
                saved_at_utc=NOW,
            ),
        )

    def validate_configuration(self, value):
        self.validated = value
        return _validation_result()

    def validate_catalog(self, value):
        self.validated = value
        return _validation_result()

    def publish_configuration(self, value, *, expected_source_revision):
        self.published = value
        self.expected_revision = expected_source_revision
        return _publication_result()

    def publish_catalog(self, value, *, expected_source_revision):
        self.published = value
        self.expected_revision = expected_source_revision
        return _publication_result()

    def list_history(self, *, limit=20):
        self.requested_limit = limit
        return self.history[:limit]

    def load_revision_configuration(self, revision):
        self.requested_revision = revision
        return self.revision_value

    def load_revision_catalog(self, revision):
        self.requested_revision = revision
        return self.revision_value


class WorkflowFake:
    def __init__(self) -> None:
        self.projected_revision = None

    def get_status(self):
        return SimpleNamespace(
            source_revision='source',
            source_audit=_audit('source-user'),
            active_revision='active',
            active_source_revision='source',
            projection_audit=_audit('projector'),
        )

    def project(self, expected_source_revision):
        self.projected_revision = expected_source_revision
        return SimpleNamespace(
            source_revision='source',
            projection_revision='active',
            projected=True,
            audit=_audit('projector'),
            issues=(
                SimpleNamespace(
                    code='warning.code',
                    message='Warning',
                    level='warning',
                    path='field',
                ),
            ),
            summary=(SimpleNamespace(label='Items', value='1'),),
        )


def _audit(actor):
    return SimpleNamespace(actor=actor, occurred_at_utc=NOW)


def _validation_result():
    return SimpleNamespace(
        draft_revision='draft',
        valid=True,
        audit=_audit('validator'),
        issues=(
            SimpleNamespace(
                code='warning.code',
                message='Warning',
                level='warning',
                path='field',
            ),
        ),
        summary=(SimpleNamespace(label='Items', value='1'),),
    )


def _publication_result():
    return SimpleNamespace(
        source_revision='published',
        published=True,
        audit=_audit('publisher'),
        summary=(SimpleNamespace(label='Items', value='1'),),
    )


def _tool_payload() -> dict[str, object]:
    return {
        'tool_key': 'process',
        'display_name': 'Process',
        'kind': 'process',
        'source_consumption': {
            'tool_key': 'process',
            'source_keys': ['pi'],
        },
        'source_operational_participation': {
            'tool_key': 'process',
            'control_sources': [
                {
                    'source_key': 'pi',
                    'pre_degrading_after_seconds': 200,
                    'degrading_after_seconds': 300,
                }
            ],
            'additional_observation_source_keys': [],
        },
        'structure': None,
    }


def _cases():
    tool = ToolConfiguration.from_document(_tool_payload())
    navigation = NavigationConfigurationCatalog()
    users = UsersConfigurationCatalog()
    return (
        (
            ToolConfigurationManagerWorkflowAdapter,
            tool.to_document(),
            tool,
        ),
        (
            NavigationManagerWorkflowAdapter,
            navigation.to_document(),
            navigation,
        ),
        (
            UsersManagerWorkflowAdapter,
            users.to_document(),
            users,
        ),
    )


@pytest.mark.parametrize('adapter_type,payload,revision_value', _cases())
def test_adapters_satisfy_manager_contracts_and_translate_domain_results(
    adapter_type,
    payload,
    revision_value,
) -> None:
    administration = AdministrationFake(revision_value)
    workflow = WorkflowFake()
    adapter = adapter_type(
        SimpleNamespace(
            administration=administration,
            projection_workflow=workflow,
        )
    )

    assert isinstance(adapter, ConfigurationLifecycleWorkflow)
    assert isinstance(adapter, RevisionHistoryWorkflow)

    status = adapter.get_status()
    assert status.source_revision == 'source'
    assert status.source_audit is not None
    assert status.source_audit.actor == 'source-user'
    assert status.active_revision == 'active'
    assert status.active_source_revision == 'source'

    validation = adapter.validate_draft(payload)
    assert validation.draft_revision == 'draft'
    assert validation.valid is True
    assert validation.audit.actor == 'validator'
    assert validation.issues[0].level == 'warning'
    assert validation.summary[0].value == '1'
    assert administration.validated.to_document() == payload

    publication = adapter.publish_draft(payload, 'source')
    assert publication.source_revision == 'published'
    assert publication.published is True
    assert publication.audit.actor == 'publisher'
    assert administration.published.to_document() == payload
    assert administration.expected_revision == 'source'

    projection = adapter.project('source')
    assert projection.source_revision == 'source'
    assert projection.projection_revision == 'active'
    assert projection.projected is True
    assert projection.audit.actor == 'projector'
    assert workflow.projected_revision == 'source'

    history = adapter.list_history(limit=1)
    assert len(history) == 1
    assert history[0].revision == 'source'
    assert history[0].current is True
    assert history[0].active is True
    assert administration.requested_limit == 1

    recovered = adapter.load_revision('previous')
    assert recovered == revision_value.to_document()
    assert administration.requested_revision == 'previous'
