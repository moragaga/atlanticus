from __future__ import annotations

from ada.web.application.generic.application import create_application_definition
from atlanticus.web.application import create_web_application
from atlanticus.web.models import WebApplicationRuntime


def create_application_runtime(
    *,
    tool_display_name: str | None = None,
) -> WebApplicationRuntime:
    # El bootstrap local puede omitir el nombre hasta que exista configuración real.
    return create_web_application(
        create_application_definition(tool_display_name=tool_display_name)
    )
