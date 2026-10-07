class AlarmMaterializationAcquisitionError(RuntimeError):
    pass


class AlarmMaterializationConfigurationPending(AlarmMaterializationAcquisitionError):
    pass


class AlarmMaterializationContractError(AlarmMaterializationAcquisitionError):
    pass
