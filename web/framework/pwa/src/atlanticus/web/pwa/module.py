from __future__ import annotations

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

    return WebModule(
        name='pwa',
        asset_layers=(PWA_ASSET_LAYER,),
        register_routes=register_routes,
        index=IndexContribution(
            head_fragments=(
                '<link rel="manifest" href="/manifest.webmanifest">',
                f'<meta name="theme-color" content="{definition.theme_color}">',
            ),
            runtime_config={
                'service_worker_url': '/service-worker.js',
                'scope': definition.scope,
            },
        ),
    )
