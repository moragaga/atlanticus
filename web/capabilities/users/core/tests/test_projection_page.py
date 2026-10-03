from atlanticus.web.users.web.projection import (
    UsersProjectionWebContext,
    build_users_projection_configuration,
    create_users_projection_web_module,
)


class Workflow:
    def history_details(self):
        return ()

    def preview_capture(self):
        return {'digest': 'd', 'approved_ids': [], 'candidate_ids': []}


def test_projection_surface_builds_for_authorized_manager_without_restore_mode():
    context = UsersProjectionWebContext(workflow=Workflow(), can_manage=lambda: True)
    layout = build_users_projection_configuration(context)
    assert layout is not None
    assert create_users_projection_web_module(context).name == 'atlanticus-users-projection'
