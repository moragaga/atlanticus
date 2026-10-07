# Errores del proceso: distinguen espera normal, contrato, qualification, supersession y configuración.
class AlarmMaterializationAcquisitionError(RuntimeError):
    pass


class AlarmMaterializationConfigurationPending(AlarmMaterializationAcquisitionError):
    pass


class AlarmMaterializationContractError(AlarmMaterializationAcquisitionError):
    pass


class AlarmMaterializationQualificationError(RuntimeError):
    pass


class AlarmMaterializationSupersededError(RuntimeError):
    pass


class AlarmMaterializationSettingsError(ValueError):
    pass
