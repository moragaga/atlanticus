from __future__ import annotations

from html import escape

from atlanticus.web.assets import AssetLayer
from atlanticus.web.index import IndexContribution
from atlanticus.web.modules import WebModule
from atlanticus.web.pwa.models import WebPwaDefinition
from atlanticus.web.pwa.routes import register_pwa_routes

PWA_ASSET_LAYER = AssetLayer(
    name='atlanticus_web_pwa',
    load_order=20,
    package='atlanticus.web.pwa',
    resource_directory='resources/assets',
)


def create_web_pwa_module(definition: WebPwaDefinition) -> WebModule:
    def register_routes(app, _services) -> None:
        register_pwa_routes(app, definition)

    # La identidad visual del navegador tiene prioridad sobre el fallback heredado de PWA.
    favicon = definition.browser_favicon
    if favicon is None and definition.icons:
        favicon = definition.icons[0]
    # Se construye un único enlace HTML para el navegador, escapando atributos.
    favicon_fragment = (
        ()
        if favicon is None
        else (
            '<link rel="icon" type="'
            + escape(favicon.mime_type, quote=True)
            + '" href="'
            + escape(favicon.src, quote=True)
            + '">',
        )
    )

    return WebModule(
        name='pwa',
        asset_layers=(PWA_ASSET_LAYER,),
        register_routes=register_routes,
        index=IndexContribution(
            head_fragments=(
                '<link rel="manifest" href="/manifest.webmanifest">',
                f'<meta name="theme-color" content="{definition.theme_color}">',
                *favicon_fragment,
            ),
            runtime_config={
                'service_worker_url': '/service-worker.js',
                'scope': definition.scope,
            },
        ),
    )
