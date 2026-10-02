# Errores de evaluación. Los errores de dependencias no exponen detalles técnicos de resolvers ajenos.
class KpiEvaluationError(RuntimeError):
    pass


class KpiEvaluationContractError(KpiEvaluationError):
    pass


class KpiDependencyError(KpiEvaluationError):
    pass


class KpiDependencyNotRequestedError(KpiEvaluationError, KeyError):
    pass
