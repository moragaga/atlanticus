# Espejo pedagógico: explica la evaluación KPI pura, sin incorporar loading ni clientes de infraestructura.
class KpiEvaluationError(RuntimeError):
    pass


class KpiEvaluationContractError(KpiEvaluationError):
    pass
