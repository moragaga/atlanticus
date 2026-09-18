# Error propio del lifecycle Source de Profiles para no mezclar fallas de persistencia/publicación con invariantes del dominio core.
class ProfilesConfigurationSourceError(RuntimeError):
    pass
