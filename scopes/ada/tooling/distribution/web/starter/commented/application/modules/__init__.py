from atlanticus.web.modules import WebModule


# Este hook concentra los módulos propios de la Tool. Para agregar callbacks, assets o páginas
# encapsuladas, se crea el módulo correspondiente y se devuelve desde esta tupla.
def create_application_modules() -> tuple[WebModule, ...]:
    return ()
