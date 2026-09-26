# La API pública del host expone el mismo runner que conserva la ruta CLI existente.
from ada.web.application.generic.__main__ import run_operational_application

__all__ = ['run_operational_application']
