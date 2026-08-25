class WebError(Exception):
    pass


class WebConfigurationError(WebError):
    pass


class WebDefinitionError(WebError):
    pass


class WebCompositionError(WebError):
    pass


class WebAssetError(WebError):
    pass


class ServiceRegistryError(WebCompositionError):
    pass
