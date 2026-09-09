from __future__ import annotations

from dash import Input, Output, State

from ada.configuration.tools import (
    BrandingVariant,
    ToolConfiguration,
    ToolConfigurationKind,
)
from ada.web.configuration.tool_editor.ids import (
    BRANDING_ID,
    CONFIGURATION_STORE_ID,
    COVERAGE_ID,
    DISPATCH_DEGRADATION_ID,
    DISPATCH_DEGRADATION_WRAPPER_ID,
    DISPATCH_ENABLED_ID,
    DISPATCH_PREVENTIVE_ID,
    DISPLAY_NAME_ID,
    DRAFT_STORE_ID,
    KIND_ID,
    PI_DEGRADATION_ID,
    PI_PREVENTIVE_ID,
    PROCESS_COVERAGE_STORE_ID,
    TOOL_KEY_STORE_ID,
    VALIDATION_MESSAGE_ID,
    VALIDITY_STORE_ID,
)
from ada.web.configuration.tool_editor.models import (
    ToolSourceEditorValues,
    build_configuration_from_source_editor,
    generate_tool_key,
    source_editor_values_from_configuration,
)
from ada.web.configuration.tool_editor.structure import (
    structure_editor_coverage_from_configuration,
)

_COVERAGE_MINE = 'mine'
_COVERAGE_PLANT = 'plant'
_COVERAGE_MINE_PLANT = 'mine_plant'


def register_tool_source_editor_callbacks(app: object) -> None:
    @app.callback(
        Output(DISPLAY_NAME_ID, 'value'),
        Output(KIND_ID, 'value'),
        Output(BRANDING_ID, 'value'),
        Output(PI_PREVENTIVE_ID, 'value'),
        Output(PI_DEGRADATION_ID, 'value'),
        Output(DISPATCH_ENABLED_ID, 'value'),
        Output(DISPATCH_PREVENTIVE_ID, 'value'),
        Output(DISPATCH_DEGRADATION_ID, 'value'),
        Input(CONFIGURATION_STORE_ID, 'data'),
    )
    def load_source_editor(
        configuration_document: dict[str, object] | None,
    ):
        if configuration_document is None:
            return (
                '',
                None,
                BrandingVariant.ORIGINAL.value,
                None,
                None,
                [],
                None,
                None,
            )
        configuration = ToolConfiguration.from_document(
            configuration_document
        )
        values = source_editor_values_from_configuration(configuration)
        return (
            values.display_name,
            values.kind.value,
            values.branding_variant.value,
            values.pi_preventive_after_seconds,
            values.pi_degradation_after_seconds,
            ['dispatch'] if values.dispatch_enabled else [],
            values.dispatch_preventive_after_seconds,
            values.dispatch_degradation_after_seconds,
        )

    @app.callback(
        Output(TOOL_KEY_STORE_ID, 'data'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        Input(DISPLAY_NAME_ID, 'value'),
        State(TOOL_KEY_STORE_ID, 'data'),
    )
    def sync_tool_key(
        configuration_document: dict[str, object] | None,
        display_name: str | None,
        current_tool_key: str | None,
    ) -> str | None:
        if configuration_document is not None:
            try:
                configuration = ToolConfiguration.from_document(
                    configuration_document
                )
            except ValueError:
                configuration = None
            if configuration is not None:
                return configuration.tool_key

        current = str(current_tool_key or '').strip()
        if current:
            return current

        name = str(display_name or '').strip()
        if not name:
            return None
        try:
            return generate_tool_key(name)
        except ValueError:
            return None

    @app.callback(
        Output(COVERAGE_ID, 'options'),
        Output(COVERAGE_ID, 'value'),
        Output(COVERAGE_ID, 'disabled'),
        Output(COVERAGE_ID, 'placeholder'),
        Output(PROCESS_COVERAGE_STORE_ID, 'data'),
        Input(CONFIGURATION_STORE_ID, 'data'),
        Input(KIND_ID, 'value'),
        State(COVERAGE_ID, 'value'),
        State(PROCESS_COVERAGE_STORE_ID, 'data'),
    )
    def sync_coverage(
        configuration_document: dict[str, object] | None,
        kind_value: str | None,
        current_coverage: str | None,
        process_coverage: str | None,
    ):
        remembered = (
            process_coverage
            if process_coverage in {_COVERAGE_MINE, _COVERAGE_PLANT}
            else None
        )
        options = _coverage_options(kind_value)
        if not options:
            return (
                [],
                None,
                True,
                'Selecciona primero el tipo',
                remembered,
            )
        if (
            kind_value
            == ToolConfigurationKind.INTEGRATED_OPERATIONS.value
        ):
            if current_coverage in {_COVERAGE_MINE, _COVERAGE_PLANT}:
                remembered = current_coverage
            return (
                options,
                _COVERAGE_MINE_PLANT,
                True,
                'Mina y Planta',
                remembered,
            )

        valid_values = {option['value'] for option in options}
        if configuration_document is not None:
            try:
                configuration = ToolConfiguration.from_document(
                    configuration_document
                )
            except ValueError:
                configuration = None
            if (
                configuration is not None
                and configuration.kind.value == kind_value
            ):
                configured = structure_editor_coverage_from_configuration(
                    configuration
                )
                if configured in valid_values:
                    return (
                        options,
                        configured,
                        False,
                        'Seleccionar cobertura',
                        configured,
                    )

        if current_coverage in valid_values:
            return (
                options,
                current_coverage,
                False,
                'Seleccionar cobertura',
                current_coverage,
            )
        if remembered in valid_values:
            return (
                options,
                remembered,
                False,
                'Seleccionar cobertura',
                remembered,
            )
        return (
            options,
            None,
            False,
            'Seleccionar cobertura',
            remembered,
        )

    @app.callback(
        Output(DISPATCH_DEGRADATION_WRAPPER_ID, 'hidden'),
        Input(DISPATCH_ENABLED_ID, 'value'),
    )
    def toggle_dispatch_threshold(
        dispatch_values: list[str] | None,
    ) -> bool:
        return 'dispatch' not in (dispatch_values or [])

    @app.callback(
        Output(DRAFT_STORE_ID, 'data'),
        Output(VALIDITY_STORE_ID, 'data'),
        Output(VALIDATION_MESSAGE_ID, 'children'),
        Input(DISPLAY_NAME_ID, 'value'),
        Input(TOOL_KEY_STORE_ID, 'data'),
        Input(KIND_ID, 'value'),
        Input(BRANDING_ID, 'value'),
        Input(PI_PREVENTIVE_ID, 'value'),
        Input(PI_DEGRADATION_ID, 'value'),
        Input(DISPATCH_ENABLED_ID, 'value'),
        Input(DISPATCH_PREVENTIVE_ID, 'value'),
        Input(DISPATCH_DEGRADATION_ID, 'value'),
        State(CONFIGURATION_STORE_ID, 'data'),
    )
    def build_source_draft(
        display_name: str | None,
        tool_key: str | None,
        kind_value: str | None,
        branding_value: str | None,
        pi_preventive: int | float | None,
        pi_degradation: int | float | None,
        dispatch_values: list[str] | None,
        dispatch_preventive: int | float | None,
        dispatch_degradation: int | float | None,
        configuration_document: dict[str, object] | None,
    ):
        dispatch_enabled = 'dispatch' in (dispatch_values or [])
        if (
            not str(display_name or '').strip()
            or not str(tool_key or '').strip()
            or not kind_value
            or not branding_value
            or pi_preventive is None
            or pi_degradation is None
            or (
                dispatch_enabled
                and (
                    dispatch_preventive is None
                    or dispatch_degradation is None
                )
            )
        ):
            return None, False, ''

        try:
            base_configuration = (
                ToolConfiguration.from_document(configuration_document)
                if configuration_document is not None
                else None
            )
            values = ToolSourceEditorValues(
                display_name=display_name or '',
                kind=ToolConfigurationKind(kind_value),
                branding_variant=BrandingVariant(branding_value),
                pi_preventive_after_seconds=pi_preventive,
                pi_degradation_after_seconds=pi_degradation,
                dispatch_enabled=dispatch_enabled,
                dispatch_preventive_after_seconds=dispatch_preventive,
                dispatch_degradation_after_seconds=dispatch_degradation,
            )
            updated = build_configuration_from_source_editor(
                base_configuration=base_configuration,
                tool_key=tool_key,
                values=values,
            )
        except ValueError as error:
            return None, False, str(error)

        return updated.to_document(), True, ''


def _coverage_options(
    kind_value: str | None,
) -> list[dict[str, str]]:
    if kind_value == ToolConfigurationKind.PROCESS.value:
        return [
            {'label': 'Mina', 'value': _COVERAGE_MINE},
            {'label': 'Planta', 'value': _COVERAGE_PLANT},
        ]
    if (
        kind_value
        == ToolConfigurationKind.INTEGRATED_OPERATIONS.value
    ):
        return [
            {
                'label': 'Mina y Planta',
                'value': _COVERAGE_MINE_PLANT,
            }
        ]
    return []
