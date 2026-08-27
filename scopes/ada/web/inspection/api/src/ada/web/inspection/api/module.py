from __future__ import annotations

from flask import Flask, Response, jsonify

from ada.web.inspection.core import KpiDefinitionSnapshotStore, KpiInspectionResult
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

_ROUTE = '/api/inspection/kpis/<path:kpi_key>'
_ENDPOINT = 'ada_kpi_inspection'


def create_kpi_inspection_api_module(store: KpiDefinitionSnapshotStore) -> WebModule:
    if not isinstance(store, KpiDefinitionSnapshotStore):
        raise TypeError('Store must be a KpiDefinitionSnapshotStore')

    def register_routes(server: Flask, services: ServiceRegistry) -> None:
        del services

        def inspect_kpi(kpi_key: str) -> Response:
            try:
                result = KpiInspectionResult(kpi_key=kpi_key, definition=store.get(kpi_key))
            except ValueError as error:
                return _json_response({'error': str(error)}, status=400)
            return _json_response(_serialize_result(result))

        server.add_url_rule(
            _ROUTE,
            endpoint=_ENDPOINT,
            view_func=inspect_kpi,
            methods=['GET'],
        )

    return WebModule(name='kpi-inspection-api', register_routes=register_routes)


def _serialize_result(result: KpiInspectionResult) -> dict[str, object]:
    definition = result.definition
    return {
        'kpi_key': result.kpi_key,
        'available': result.available,
        'definition': None if definition is None else dict(definition.fields),
    }


def _json_response(payload: dict[str, object], *, status: int = 200) -> Response:
    response = jsonify(payload)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response
