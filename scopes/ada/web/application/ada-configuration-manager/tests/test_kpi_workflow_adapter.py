from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from ada.web.application.configuration_manager import KpiConfigurationManagerWorkflowAdapter
from ada.web.kpis.configuration import KpiConfiguration


def _audit():
    return SimpleNamespace(
        actor='local',
        occurred_at_utc=datetime(2026, 9, 9, tzinfo=UTC),
    )


class Administration:
    def validate_configuration(self, configuration):
        assert isinstance(configuration, KpiConfiguration)
        return SimpleNamespace(
            draft_revision='draft-r1',
            valid=True,
            audit=_audit(),
            issues=(),
            summary=(),
        )

    def publish_configuration(self, configuration, *, expected_source_revision):
        assert isinstance(configuration, KpiConfiguration)
        assert expected_source_revision == 'source-r0'
        return SimpleNamespace(
            source_revision='source-r1',
            published=True,
            audit=_audit(),
            summary=(),
        )

    def load_revision_configuration(self, revision):
        assert revision == 'source-r1'
        return KpiConfiguration()

    def list_history(self, *, limit=20):
        assert limit == 20
        return ()


class ProjectionWorkflow:
    def get_status(self):
        return SimpleNamespace(
            source_revision='source-r1',
            source_audit=_audit(),
            active_revision='projection-r1',
            active_source_revision='source-r1',
            projection_audit=_audit(),
        )

    def project(self, expected_source_revision):
        assert expected_source_revision == 'source-r1'
        return SimpleNamespace(
            source_revision='source-r1',
            projection_revision='projection-r2',
            projected=True,
            audit=_audit(),
            issues=(),
            summary=(),
        )


def adapter():
    return KpiConfigurationManagerWorkflowAdapter(
        SimpleNamespace(
            administration=Administration(),
            projection_workflow=ProjectionWorkflow(),
        )
    )


def test_kpi_workflow_adapter_reuses_manager_contract() -> None:
    workflow = adapter()

    assert workflow.validate_draft({'bindings': []}).valid is True
    assert workflow.publish_draft({'bindings': []}, 'source-r0').published is True
    assert workflow.project('source-r1').projected is True
    assert workflow.load_revision('source-r1') == {'bindings': []}
    assert workflow.list_history() == ()
