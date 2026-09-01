from __future__ import annotations

# Compone Sources y Structure como una única superficie de edición de ToolConfiguration.
from collections.abc import Mapping

from dash import html
from dash.development.base_component import Component

from ada.web.configuration.tool_editor.presentation import build_tool_source_editor
from ada.web.configuration.tool_editor.structure_ids import (
    TOOL_CONFIGURATION_EDITOR_ROOT_ID,
)
from ada.web.configuration.tool_editor.structure_presentation import (
    build_tool_structure_editor,
)


def build_tool_configuration_editor(
    *,
    configuration_document: Mapping[str, object] | None = None,
) -> Component:
    return html.Div(
        [
            build_tool_source_editor(
                configuration_document=configuration_document,
            ),
            build_tool_structure_editor(
                configuration_document=configuration_document,
            ),
        ],
        id=TOOL_CONFIGURATION_EDITOR_ROOT_ID,
        className='ada-tool-configuration-editor-complete',
    )
