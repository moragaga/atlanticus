from __future__ import annotations

from flask import Response

from atlanticus.web.status_pages import StatusPageAction, status_page_response


def invalid_identity_response() -> Response:
    return status_page_response(
        status_code=401,
        title='No fue posible iniciar sesión',
        message='No fue posible validar tu ingreso. Intenta recargar la página.',
        action=StatusPageAction(label='Reintentar', href=''),
    )


def user_not_promoted_response() -> Response:
    return status_page_response(
        status_code=403,
        title='Usuario no habilitado',
        message='Tu identidad todavía no ha sido promovida como usuario de la plataforma.',
    )


def user_disabled_response() -> Response:
    return status_page_response(
        status_code=403,
        title='Usuario desactivado',
        message='Tu usuario está desactivado y no tiene acceso a esta aplicación.',
    )


def identity_unavailable_response() -> Response:
    return status_page_response(
        status_code=503,
        title='No fue posible iniciar sesión',
        message='El servicio de identidad no está disponible. Intenta recargar la página.',
        action=StatusPageAction(label='Reintentar', href=''),
    )
