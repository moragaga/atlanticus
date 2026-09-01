# Espejo pedagógico: explica la evaluación KPI pura, sin incorporar loading ni clientes de infraestructura.
from ada.kpis.evaluation.errors import KpiEvaluationContractError, KpiEvaluationError
from ada.kpis.evaluation.evaluator import evaluate_kpi

__version__ = '1.0.0'

__all__ = [
    'KpiEvaluationContractError',
    'KpiEvaluationError',
    '__version__',
    'evaluate_kpi',
]
