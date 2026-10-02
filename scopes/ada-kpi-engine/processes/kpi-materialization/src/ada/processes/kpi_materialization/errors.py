class KpiMaterializationAcquisitionError(RuntimeError):
    pass


class KpiMaterializationRegistryPending(KpiMaterializationAcquisitionError):
    pass


class KpiMaterializationIterationError(RuntimeError):
    pass


class KpiMaterializationSettingsError(ValueError):
    pass
