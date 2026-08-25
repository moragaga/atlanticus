from __future__ import annotations

from ada.web.application.generic.application import create_application_definition
from atlanticus.web.application import create_web_application
from atlanticus.web.models import WebApplicationRuntime


def create_application_runtime() -> WebApplicationRuntime:
    # El runtime concreto queda deliberadamente delgado: definición ADA sobre Atlanticus Web.
    return create_web_application(create_application_definition())
