# Este error conserva el comportamiento observable de validación del contrato publicado.
# La lógica se mantiene equivalente al archivo productivo; sólo se agregan comentarios pedagógicos.

class AlarmConfigurationValidationError(ValueError):
    pass
