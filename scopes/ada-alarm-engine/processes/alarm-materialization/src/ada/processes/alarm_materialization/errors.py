class AlarmMaterializationAcquisitionError(RuntimeError):
    pass


class AlarmMaterializationConfigurationPending(AlarmMaterializationAcquisitionError):
    pass


class AlarmMaterializationContractError(AlarmMaterializationAcquisitionError):
    pass


class AlarmMaterializationSupersededError(RuntimeError):
    pass


class AlarmMaterializationSettingsError(ValueError):
    pass
