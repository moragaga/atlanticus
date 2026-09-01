from __future__ import annotations

# Los callbacks conectan un documento ToolConfiguration de entrada con un draft válido de salida.
# Cuando la edición es incompleta o inválida se invalida el draft para evitar guardar estado anterior.
from dash import Input, Output, State

from ada.configuration.tools import ToolConfiguration
from ada.web.configuration.tool_editor.ids import (
    ADDITIONAL_OBSERVATION_ID,
    CONFIGURATION_STORE_ID,
    DISPATCH_DEGRADING_ID,
    DISPATCH_ENABLED_ID,
    DISPATCH_FIELDS_ID,
    DISPATCH_PRE_DEGRADING_ID,
    DRAFT_STORE_ID,
    PI_DEGRADING_ID,
    PI_PRE_DEGRADING_ID,
    VALIDATION_MESSAGE_ID,
    VALIDITY_STORE_ID,
)
from ada.web.configuration.tool_editor.models import (
    ToolSourceEditorValues,
    build_configuration_from_source_editor,
    parse_additional_observation_source_keys,
    source_editor_values_from_configuration,
)


def register_tool_source_editor_callbacks(app: object) -> None:
    @app.callback(
        Output(PI_PRE_DEGRADING_ID, 'value'),
        Output(PI_DEGRADING_ID, 'value'),
        Output(DISPATCH_ENABLED_ID, 'value'),
        Output(DISPATCH_PRE_DEGRADING_ID, 'value'),
        Output(DISPATCH_DEGRADING_ID, 'value'),
        Output(ADDITIONAL_OBSERVATION_ID, 'value'),
        Input(CONFIGURATION_STORE_ID, 'data'),
    )
    def load_source_editor(configuration_document: dict[str, object] | None):
        if configuration_document is None:
            return None, None, [], None, None, ''
        configuration = ToolConfiguration.from_document(configuration_document)
        values = source_editor_values_from_configuration(configuration)
        return (
            values.pi_pre_degrading_after_seconds,
            values.pi_degrading_after_seconds,
            ['dispatch'] if values.dispatch_enabled else [],
            values.dispatch_pre_degrading_after_seconds,
            values.dispatch_degrading_after_seconds,
            '\n'.join(values.additional_observation_source_keys),
        )

    @app.callback(
        Output(DISPATCH_FIELDS_ID, 'hidden'),
        Output(DISPATCH_PRE_DEGRADING_ID, 'disabled'),
        Output(DISPATCH_DEGRADING_ID, 'disabled'),
        Input(DISPATCH_ENABLED_ID, 'value'),
    )
    def toggle_dispatch_fields(dispatch_values: list[str] | None):
        enabled = 'dispatch' in (dispatch_values or [])
        return not enabled, not enabled, not enabled

    @app.callback(
        Output(DRAFT_STORE_ID, 'data'),
        Output(VALIDITY_STORE_ID, 'data'),
        Output(VALIDATION_MESSAGE_ID, 'children'),
        Input(PI_PRE_DEGRADING_ID, 'value'),
        Input(PI_DEGRADING_ID, 'value'),
        Input(DISPATCH_ENABLED_ID, 'value'),
        Input(DISPATCH_PRE_DEGRADING_ID, 'value'),
        Input(DISPATCH_DEGRADING_ID, 'value'),
        Input(ADDITIONAL_OBSERVATION_ID, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
    )
    def build_source_draft(
        pi_pre_degrading: int | float | None,
        pi_degrading: int | float | None,
        dispatch_values: list[str] | None,
        dispatch_pre_degrading: int | float | None,
        dispatch_degrading: int | float | None,
        additional_observation: str | None,
        configuration_document: dict[str, object] | None,
    ):
        if configuration_document is None:
            return None, False, ''
        try:
            base_configuration = ToolConfiguration.from_document(configuration_document)
            values = ToolSourceEditorValues(
                pi_pre_degrading_after_seconds=pi_pre_degrading,
                pi_degrading_after_seconds=pi_degrading,
                dispatch_enabled='dispatch' in (dispatch_values or []),
                dispatch_pre_degrading_after_seconds=dispatch_pre_degrading,
                dispatch_degrading_after_seconds=dispatch_degrading,
                additional_observation_source_keys=(
                    parse_additional_observation_source_keys(additional_observation)
                ),
            )
            updated = build_configuration_from_source_editor(
                base_configuration=base_configuration,
                values=values,
            )
        except ValueError as error:
            return None, False, str(error)
        return updated.to_document(), True, ''
