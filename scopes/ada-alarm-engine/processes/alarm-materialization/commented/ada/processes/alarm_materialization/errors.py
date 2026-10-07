# Errores propios del boundary de acquisition; separan espera normal de fallas operacionales o contractuales.
class AlarmMaterializationAcquisitionError(RuntimeError):
    pass


# La configuración todavía no fue publicada: el proceso puede hacer skip sin degradar el último READY.
class AlarmMaterializationConfigurationPending(AlarmMaterializationAcquisitionError):
    pass


# El recurso existe, pero su documento no cumple la identidad o contrato compartido esperado.
class AlarmMaterializationContractError(AlarmMaterializationAcquisitionError):
    pass
