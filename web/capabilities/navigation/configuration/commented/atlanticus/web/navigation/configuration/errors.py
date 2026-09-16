# Espejo pedagógico del archivo productivo; conserva exactamente su comportamiento.
# Los comentarios en español describen responsabilidades sin alterar el contrato ejecutable.
# Responsabilidad: NavigationConfigurationError encapsula una frontera explícita del contrato vigente.
class NavigationConfigurationError(RuntimeError):
    pass


# Responsabilidad: NavigationConfigurationValidationError encapsula una frontera explícita del contrato vigente.
class NavigationConfigurationValidationError(NavigationConfigurationError):
    pass


# Responsabilidad: NavigationConfigurationSourceError encapsula una frontera explícita del contrato vigente.
class NavigationConfigurationSourceError(NavigationConfigurationError):
    pass


# Responsabilidad: NavigationConfigurationProjectionError encapsula una frontera explícita del contrato vigente.
class NavigationConfigurationProjectionError(NavigationConfigurationError):
    pass
