# Este módulo preserva el contrato público asociado al incremento de Materialization.
# Implementación del contrato AlarmMaterializationAcquisitionError.
class AlarmMaterializationAcquisitionError(RuntimeError):
    pass


# Implementación del contrato AlarmMaterializationConfigurationPending.
class AlarmMaterializationConfigurationPending(AlarmMaterializationAcquisitionError):
    pass


# Implementación del contrato AlarmMaterializationContractError.
class AlarmMaterializationContractError(AlarmMaterializationAcquisitionError):
    pass


# Implementación del contrato AlarmMaterializationSupersededError.
class AlarmMaterializationSupersededError(RuntimeError):
    pass


# Implementación del contrato AlarmMaterializationSettingsError.
class AlarmMaterializationSettingsError(ValueError):
    pass
