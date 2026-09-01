class KpiEvaluationError(RuntimeError):
    pass


class KpiEvaluationContractError(KpiEvaluationError):
    pass


class KpiDependencyError(KpiEvaluationError):
    pass


class KpiDependencyNotRequestedError(KpiEvaluationError, KeyError):
    pass
