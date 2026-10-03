# Este módulo reúne errores de validación que forman parte del comportamiento observable de los contratos Tools.
# La lógica se mantiene equivalente al archivo productivo; sólo se agregan comentarios pedagógicos.

class ToolConfigurationValidationError(ValueError):
    pass


class ToolDependencyManifestValidationError(ValueError):
    pass
