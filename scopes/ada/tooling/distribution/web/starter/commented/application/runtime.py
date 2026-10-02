from ada.web.application.generic.host import (
    create_worker_runtime as create_ada_worker_runtime,
)
from ada.web.application.generic.host import run_operational_application

from application.composition import create_composition
from application.production import create_identity_provider


# WSGI aporta únicamente extensiones al runtime de ADA Generic.
def create_worker_runtime():
    return create_ada_worker_runtime(
        composition_factory=create_composition,
        production_identity_provider_factory=create_identity_provider,
    )


# La ejecución local usa el mismo host reusable.
def run_application() -> None:
    run_operational_application(
        composition_factory=create_composition,
        production_identity_provider_factory=create_identity_provider,
    )
