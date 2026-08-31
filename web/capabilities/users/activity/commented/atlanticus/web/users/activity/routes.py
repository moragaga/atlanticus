# Traduce HTTP al contrato del servicio.
# Identity sigue siendo la autoridad del principal efectivo.
from __future__ import annotations

from flask import Flask, jsonify, request

from atlanticus.web.identity.access import ACCESS_RUNTIME_SERVICE_KEY, AccessRuntime
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.activity.errors import UserActivityError
from atlanticus.web.users.activity.models import UserActivityEvent
from atlanticus.web.users.activity.services import UserActivityService

USER_ACTIVITY_SERVICE_KEY = 'atlanticus.web.users.activity'
USER_ACTIVITY_BOOTSTRAP_PATH = '/_atlanticus/activity/bootstrap'
USER_ACTIVITY_EVENT_PATH = '/_atlanticus/activity/events'


def register_user_activity_routes(server: Flask, services: ServiceRegistry) -> None:
    activity = services.require(USER_ACTIVITY_SERVICE_KEY, UserActivityService)
    access = services.require(ACCESS_RUNTIME_SERVICE_KEY, AccessRuntime)

    @server.get(USER_ACTIVITY_BOOTSTRAP_PATH)
    def atlanticus_user_activity_bootstrap():
        snapshot = access.current_or_none()
        return jsonify({'enabled': True, 'track': activity.should_track(snapshot)})

    @server.post(USER_ACTIVITY_EVENT_PATH)
    def atlanticus_user_activity_event():
        snapshot = access.current_or_none()
        if snapshot is None:
            return jsonify({'error': 'Access snapshot is not available'}), 401
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({'error': 'User activity payload must be a JSON object'}), 400
        try:
            event = UserActivityEvent.from_payload(payload)
            result = activity.capture(snapshot=snapshot, event=event)
        except UserActivityError as error:
            return jsonify({'error': str(error)}), 400
        return jsonify(result), 202
