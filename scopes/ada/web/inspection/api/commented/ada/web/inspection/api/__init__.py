# Expone únicamente la factory de integración Flask; no publica internals del endpoint.
from ada.web.inspection.api.module import create_kpi_inspection_api_module

__all__ = ['create_kpi_inspection_api_module']
