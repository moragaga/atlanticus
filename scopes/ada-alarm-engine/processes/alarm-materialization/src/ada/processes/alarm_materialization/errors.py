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
