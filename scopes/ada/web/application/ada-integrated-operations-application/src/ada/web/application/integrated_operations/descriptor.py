from pathlib import Path

from ada.web.application.generic import AdaApplicationDescriptor
from atlanticus.web.assets import AssetLayer


def _resolve_favicon_asset_layer(package_root: Path) -> AssetLayer | None:
    favicon = package_root / 'resources' / 'favicon' / 'img' / 'favicon.ico'
    if not favicon.is_file():
        return None
    return AssetLayer(
        name='ada_integrated_operations_favicon',
        load_order=206,
        package='ada.web.application.integrated_operations',
        resource_directory='resources/favicon',
    )


INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR = AdaApplicationDescriptor(
    import_name='ada.web.application.integrated_operations',
    application_id='ada-integrated-operations-application',
    display_name='ADA Operaciones Integradas',
    pwa_short_name='ADA Operaciones',
    distribution_name='ada-integrated-operations-application',
    application_root=Path(__file__).resolve().parents[5],
    favicon_asset_layer=_resolve_favicon_asset_layer(Path(__file__).resolve().parent),
)
