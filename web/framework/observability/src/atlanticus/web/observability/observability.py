from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from typing import Any

from flask import Flask, g, got_request_exception, request

from atlanticus.web.observability.models import WebErrorInfo, WebEvent, WebSeverity
from atlanticus.web.observability.sanitization import sanitize

_EXCEPTION_FLAG = '_atlanticus_web_exception_observed'


class WebObservability:
    def __init__(self, *, application: str, logger: logging.Logger, json_output: bool) -> None:
        self._application = application
        self._logger = logger
        self._json_output = json_output

    def warning(self, name: str, message: str, **context: Any) -> None:
        self._emit(WebSeverity.WARNING, name, message, context=context)

    def error(
        self,
        name: str,
        message: str,
        *,
        exception: BaseException | None = None,
        **context: Any,
    ) -> None:
        self._emit(
            WebSeverity.ERROR,
            name,
            message,
            context=context,
            exception=exception,
        )

    def critical(
        self,
        name: str,
        message: str,
        *,
        exception: BaseException | None = None,
        **context: Any,
    ) -> None:
        self._emit(
            WebSeverity.CRITICAL,
            name,
            message,
            context=context,
            exception=exception,
        )

    def attach_flask(self, app: Flask) -> None:
        def observe_exception(sender: Flask, exception: BaseException, **_: Any) -> None:
            g.__setattr__(_EXCEPTION_FLAG, True)
            self.error(
                'web.request.failed',
                'Unhandled web request exception',
                exception=exception,
                method=request.method,
                path=request.path,
                endpoint=request.endpoint,
            )

        got_request_exception.connect(observe_exception, sender=app, weak=False)

        @app.after_request
        def observe_failed_response(response):
            if response.status_code >= 500 and not getattr(g, _EXCEPTION_FLAG, False):
                self.error(
                    'web.request.failed',
                    'Web request returned a server error',
                    method=request.method,
                    path=request.path,
                    endpoint=request.endpoint,
                    status_code=response.status_code,
                )
            return response

    def _emit(
        self,
        severity: WebSeverity,
        name: str,
        message: str,
        *,
        context: dict[str, Any],
        exception: BaseException | None = None,
    ) -> None:
        error = None
        if exception is not None:
            error = WebErrorInfo(type=type(exception).__name__, message=str(exception))
        event = WebEvent(
            name=name,
            severity=severity,
            message=message,
            application=self._application,
            context=sanitize(context),
            error=error,
        )
        log_method = {
            WebSeverity.WARNING: self._logger.warning,
            WebSeverity.ERROR: self._logger.error,
            WebSeverity.CRITICAL: self._logger.critical,
        }[severity]
        log_method(self._render(event))

    def _render(self, event: WebEvent) -> str:
        if self._json_output:
            payload = asdict(event)
            payload['timestamp'] = event.timestamp.isoformat()
            payload['severity'] = event.severity.value
            return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        details = [
            f'event={event.name}',
            f'application={event.application}',
            f'message={event.message}',
        ]
        if event.context:
            details.append(
                'context=' + json.dumps(event.context, ensure_ascii=False, separators=(',', ':'))
            )
        if event.error is not None:
            details.append(f'error={event.error.type}: {event.error.message}')
        return ' | '.join(details)


def configure_web_observability(*, application: str, json_output: bool) -> WebObservability:
    logger = logging.getLogger(f'atlanticus.web.{application}')
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
    logger.addHandler(handler)
    return WebObservability(application=application, logger=logger, json_output=json_output)
