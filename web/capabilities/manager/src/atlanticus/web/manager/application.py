from dash import Input, Output, State, html, no_update, page_container

from atlanticus.web.application import create_web_application
from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.errors import ManagerDefinitionError
from atlanticus.web.manager.models import ManagerApplicationDefinition
from atlanticus.web.manager.surface import ManagerSurface
from atlanticus.web.manager.web.ids import REFRESH_BUTTON_ID, REFRESH_SIGNAL_ID
from atlanticus.web.manager.web.layout import build_manager_header
from atlanticus.web.models import WebApplicationDefinition, WebApplicationRuntime
from atlanticus.web.modules import WebModule


def build_manager_web_definition(
    definition: ManagerApplicationDefinition,
    *,
    authorization: ManagerAuthorizationPolicy | None = None,
) -> WebApplicationDefinition:
    if not definition.subtitle.strip():
        raise ManagerDefinitionError('Manager application subtitle must not be empty')
    if definition.surface.route_prefix:
        raise ManagerDefinitionError('Standalone manager route prefix must be empty')
    surface = ManagerSurface(definition.surface, authorization=authorization)

    def register_host_callbacks(app: object, _services: object) -> None:
        @app.callback(
            Output(REFRESH_SIGNAL_ID, 'data'),
            Input(REFRESH_BUTTON_ID, 'n_clicks'),
            State(REFRESH_SIGNAL_ID, 'data'),
            prevent_initial_call=True,
        )
        def request_refresh(clicks: int | None, current: int | None):
            if not isinstance(clicks, int) or isinstance(clicks, bool) or clicks <= 0:
                return no_update
            return int(current or 0) + 1

    host_module = WebModule(
        name='manager-standalone-host',
        page_packages=('atlanticus.web.manager.pages',),
        register_callbacks=register_host_callbacks,
    )

    def layout(services):
        return html.Div(
            [
                build_manager_header(definition=definition, services=services),
                *surface.layout(services).children,
                definition.shell_overlays(services)
                if definition.shell_overlays is not None
                else None,
                html.Div(page_container, hidden=True),
            ],
            className='atlanticus-manager atlanticus-manager--standalone',
        )

    return WebApplicationDefinition(
        import_name=definition.import_name,
        metadata=definition.metadata,
        publications_root=definition.publications_root,
        layout=layout,
        modules=definition.web_modules + surface.web_modules + (host_module,),
        index=definition.index,
        dash=definition.dash,
        flask_config=definition.flask_config,
    )


def create_manager_application(
    definition: ManagerApplicationDefinition,
    *,
    authorization: ManagerAuthorizationPolicy | None = None,
) -> WebApplicationRuntime:
    return create_web_application(
        build_manager_web_definition(definition, authorization=authorization)
    )
