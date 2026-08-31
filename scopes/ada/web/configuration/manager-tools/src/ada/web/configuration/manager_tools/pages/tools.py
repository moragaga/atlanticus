from dash import register_page

from ada.web.configuration.manager_tools.presentation import build_manager_tools_page

register_page(__name__, path='/manager/tools', name='Tools', order=0)

layout = build_manager_tools_page()
