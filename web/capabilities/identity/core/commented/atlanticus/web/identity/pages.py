from __future__ import annotations

from flask import Response

from atlanticus.web.status_pages import StatusPageAction, status_page_response


# Falla de autenticación: conserva 401 y ofrece volver a intentar la carga.
def invalid_identity_response() -> Response:
    return status_page_response(
        status_code=401,
        title='No fue posible iniciar sesión',
        message='No fue posible validar tu ingreso. Intenta recargar la página.',
        action=StatusPageAction(label='Reintentar', href=''),
    )


# Un usuario desactivado queda bloqueado completamente para la aplicación.
def user_disabled_response() -> Response:
    return status_page_response(
        status_code=403,
        title='Usuario desactivado',
        message='Tu usuario está desactivado y no tiene acceso a esta aplicación.',
    )


# Indisponibilidad de identidad: conserva 503 y no se presenta como credencial inválida.
def identity_unavailable_response() -> Response:
    return status_page_response(
        status_code=503,
        title='No fue posible iniciar sesión',
        message='El servicio de identidad no está disponible. Intenta recargar la página.',
        action=StatusPageAction(label='Reintentar', href=''),
    )
