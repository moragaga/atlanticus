from __future__ import annotations

from flask import Flask, Response, jsonify

from ada.web.inspection.core import KpiDefinitionSnapshotStore, KpiInspectionResult
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

# La ruta expresa una consulta de definición por identidad KPI, no un canal de measurements.
_ROUTE = '/api/inspection/kpis/<path:kpi_key>'
_ENDPOINT = 'ada_kpi_inspection'


def create_kpi_inspection_api_module(store: KpiDefinitionSnapshotStore) -> WebModule:
    # La dependencia se inyecta ya materializada para que esta frontera Flask nunca conozca providers.
    if not isinstance(store, KpiDefinitionSnapshotStore):
        raise TypeError('Store must be a KpiDefinitionSnapshotStore')

    def register_routes(server: Flask, services: ServiceRegistry) -> None:
        # WebModule exige el registry, pero KI-005 no necesita registrar ni resolver servicios adicionales.
        del services

        def inspect_kpi(kpi_key: str) -> Response:
            # El lookup termina en memoria. Un KPI ausente es un resultado normal y no activa refresh.
            try:
                result = KpiInspectionResult(kpi_key=kpi_key, definition=store.get(kpi_key))
            except ValueError as error:
                return _json_response({'error': str(error)}, status=400)
            return _json_response(_serialize_result(result))

        # La ruta se registra explícitamente para evitar estado global o Blueprints compartidos.
        server.add_url_rule(
            _ROUTE,
            endpoint=_ENDPOINT,
            view_func=inspect_kpi,
            methods=['GET'],
        )

    return WebModule(name='kpi-inspection-api', register_routes=register_routes)


def _serialize_result(result: KpiInspectionResult) -> dict[str, object]:
    # El payload conserva los campos textuales arbitrarios sin inventar el schema de KPI Configuration.
    definition = result.definition
    return {
        'kpi_key': result.kpi_key,
        'available': result.available,
        'definition': None if definition is None else dict(definition.fields),
    }


def _json_response(payload: dict[str, object], *, status: int = 200) -> Response:
    # Cada click debe observar el snapshot vigente del worker, no una respuesta vieja del browser/proxy.
    response = jsonify(payload)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response
