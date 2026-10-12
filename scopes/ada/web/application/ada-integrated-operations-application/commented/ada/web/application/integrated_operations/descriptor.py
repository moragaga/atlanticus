from pathlib import Path

from ada.web.application.generic import AdaApplicationDescriptor
from atlanticus.web.assets import AssetLayer


# La aplicación especializada puede incluir su icono directamente en el código montado
# o copiado dentro de la imagen Docker. No requiere publicarse como wheel.
def _resolve_favicon_asset_layer(package_root: Path) -> AssetLayer | None:
    favicon = package_root / 'resources' / 'favicon' / 'img' / 'favicon.ico'
    # Mientras el recurso real no exista, el descriptor conserva el fallback ADA.
    if not favicon.is_file():
        return None
    # Atlanticus publica el recurso mediante el pipeline de assets ya existente.
    return AssetLayer(
        name='ada_integrated_operations_favicon',
        load_order=206,
        package='ada.web.application.integrated_operations',
        resource_directory='resources/favicon',
    )


# La identidad y los iconos PWA se heredan de la composición de ADA Generic.
INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR = AdaApplicationDescriptor(
    import_name='ada.web.application.integrated_operations',
    application_id='ada-integrated-operations-application',
    display_name='ADA Operaciones Integradas',
    pwa_short_name='ADA Operaciones',
    distribution_name='ada-integrated-operations-application',
    application_root=Path(__file__).resolve().parents[5],
    favicon_asset_layer=_resolve_favicon_asset_layer(Path(__file__).resolve().parent),
)
