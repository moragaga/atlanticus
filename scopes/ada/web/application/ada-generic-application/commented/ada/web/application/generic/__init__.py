# Expone el composition root público sin hacer que el namespace superior sea un paquete concreto.
from ada.web.application.generic.runtime import create_application_runtime

__all__ = ['create_application_runtime']
