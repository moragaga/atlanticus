from dash import Input, Output

from ada.web.alarms.collector import alarm_live_store_id
from ada.web.alarms.live_surface import ALARM_LIVE_BOARD_ID
from ada.web.branding.web import DEFAULT_OPERATIONAL_BRAND_LOGO_SRC
from atlanticus.web.index import IndexContribution

from .ids import DASHBOARD_ROOT_ID

STARTUP_LOADER_INDEX = IndexContribution(
    body_start_fragments=(
        (
            '<div id="ada-io-startup-loader" class="ada-io-startup-loader" '
            'role="status" aria-label="Cargando operaciones">'
            '<img class="ada-io-startup-loader__logo" '
            f'src="{DEFAULT_OPERATIONAL_BRAND_LOGO_SRC}" alt="ADA">'
            '<p class="ada-io-startup-loader__subtitle">Asistente de Decisiones Ágiles</p>'
            '<div class="ada-io-startup-loader__waves" aria-hidden="true">'
            '<div></div><div></div></div></div>'
        ),
        (
            '<script>'
            'if(location.pathname!=="/"){'
            'document.documentElement.dataset.adaIoLoaderSkip="true";'
            '}else{window.setTimeout(function(){'
            'var loader=document.getElementById("ada-io-startup-loader");'
            'if(loader){loader.classList.add("ada-io-startup-loader--exit");'
            'loader.setAttribute("aria-hidden","true");}'
            '},29500);}'
            '</script>'
        ),
    ),
)


def register_startup_alarm_readiness(dash_app, *, tool_key: str) -> None:
    dash_app.clientside_callback(
        """function(data, boardStyle) {
            const availability = data && data.availability;
            const resolved = ['ready', 'missing', 'invalid', 'unavailable', 'retired']
                .includes(availability);
            const rendered = boardStyle && boardStyle['--ada-alarm-live-slot-count'];
            const triggers = dash_clientside.callback_context.triggered || [];
            const boardUpdated = triggers.some((trigger) =>
                trigger.prop_id === 'ada-alarm-live-board.style');
            return resolved && rendered && boardUpdated ? 'true' : 'false';
        }""",
        Output(DASHBOARD_ROOT_ID, 'data-ada-io-alarm-ready'),
        Input(alarm_live_store_id(tool_key), 'data'),
        Input(ALARM_LIVE_BOARD_ID, 'style'),
    )
