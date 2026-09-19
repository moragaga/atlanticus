# Error propio del lifecycle Source de Profiles para no mezclar fallas de persistencia/publicación con invariantes del dominio core.
class ProfilesConfigurationSourceError(RuntimeError):
    pass


# Error propio de la materialización y persistencia de la Projection efectiva de Profiles.
class ProfilesConfigurationProjectionError(RuntimeError):
    pass
