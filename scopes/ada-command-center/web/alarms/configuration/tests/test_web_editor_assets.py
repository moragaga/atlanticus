from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)
from ada_command_center.web.alarms.configuration.web.module import (
    create_alarm_configuration_admin_web_module,
)
from atlanticus.web.assets import publish_asset_layers


def test_editor_css_is_included_in_asset_publication(tmp_path) -> None:
    context = AlarmConfigurationAdminWebContext(
        workspace_payload_reader=lambda _document: None,
        workspace_payload_writer=lambda _document, payload: payload,
        draft_store_id='draft',
        saved_draft_store_id='saved',
        draft_save_action_id='save',
        editor_revision_store_id='revision',
    )
    module = create_alarm_configuration_admin_web_module(context)

    publication = publish_asset_layers(
        layers=module.asset_layers,
        publications_root=tmp_path,
    )

    assert len(publication.css_entries) == 1
    published_css = publication.assets_root / publication.css_entries[0]
    assert '.ada-command-center-alarm-editor' in published_css.read_text(encoding='utf-8')
