# Error específico del boundary Source de ADA Access.
class AdaAccessConfigurationSourceError(RuntimeError):
    pass


# Error específico de materialización de ADA Access contra una Projection exacta de Profiles.
class AdaAccessConfigurationProjectionError(RuntimeError):
    pass
