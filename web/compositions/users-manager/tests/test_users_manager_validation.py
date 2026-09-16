from atlanticus.web.compositions.users_manager import UsersManagerDraftValidationWorkflow
from atlanticus.web.manager import DraftValidationWorkflow, build_workspace_revision
from atlanticus.web.users.configuration.admin_composition import (
    build_users_profiles_admin_revision,
    default_users_profiles_configuration,
)


def test_manager_workspace_revision_matches_users_domain_draft_revision() -> None:
    configuration = default_users_profiles_configuration()
    payload = configuration.to_document()

    assert build_workspace_revision(payload) == build_users_profiles_admin_revision(configuration)


def test_users_validator_implements_generic_validation_contract() -> None:
    workflow = UsersManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'Admin',
    )

    assert isinstance(workflow, DraftValidationWorkflow)


def test_users_validator_accepts_canonical_users_profiles_payload() -> None:
    workflow = UsersManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'Admin',
    )
    payload = default_users_profiles_configuration().to_document()

    result = workflow.validate_draft(payload)

    assert result.valid is True
    assert result.draft_revision == build_workspace_revision(payload)
    assert result.issues == ()
    assert tuple(item.label for item in result.summary) == (
        'Usuarios',
        'Usuarios activos',
        'Perfiles funcionales',
    )


def test_users_validator_reports_invalid_canonical_contract() -> None:
    workflow = UsersManagerDraftValidationWorkflow(
        audit_actor_provider=lambda: 'Admin',
    )
    payload = {'users': [], 'profiles': []}

    result = workflow.validate_draft(payload)

    assert result.valid is False
    assert result.draft_revision == build_workspace_revision(payload)
    assert len(result.issues) == 1
    assert result.issues[0].code == 'users.configuration.invalid'
