from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.errors import WebCompositionError

HealthCallback = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    callback: HealthCallback


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    name: str
    healthy: bool
    error_type: str | None = None

    def as_dict(self) -> dict[str, str]:
        payload = {'status': 'healthy' if self.healthy else 'unhealthy'}
        if self.error_type is not None:
            payload['error_type'] = self.error_type
        return payload


@dataclass(frozen=True, slots=True)
class HealthReport:
    ready: bool
    checks: tuple[HealthCheckResult, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            'status': 'ready' if self.ready else 'not_ready',
            'checks': {check.name: check.as_dict() for check in self.checks},
        }


class HealthRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck] = {}

    def add(self, name: str, callback: HealthCallback) -> None:
        normalized = name.strip()
        if not normalized:
            raise WebCompositionError('Health check name must not be empty')
        if normalized in self._checks:
            raise WebCompositionError(f'Health check already registered: {normalized}')
        self._checks[normalized] = HealthCheck(name=normalized, callback=callback)

    def evaluate(self) -> HealthReport:
        results: list[HealthCheckResult] = []
        for check in self._checks.values():
            try:
                healthy = check.callback() is True
                results.append(HealthCheckResult(name=check.name, healthy=healthy))
            except Exception as error:
                results.append(
                    HealthCheckResult(
                        name=check.name,
                        healthy=False,
                        error_type=type(error).__name__,
                    )
                )
        return HealthReport(
            ready=all(result.healthy for result in results),
            checks=tuple(results),
        )

    def __len__(self) -> int:
        return len(self._checks)


def register_health_routes(
    server: object,
    *,
    application_id: str,
    version: str,
    environment: str,
    registry: HealthRegistry,
) -> None:
    @server.get('/health/live')
    def health_live() -> tuple[dict[str, str], int]:
        return {
            'status': 'alive',
            'application_id': application_id,
            'version': version,
            'environment': environment,
        }, 200

    @server.get('/health/ready')
    def health_ready() -> tuple[dict[str, object], int]:
        report = registry.evaluate()
        payload = report.as_dict()
        payload['application_id'] = application_id
        payload['version'] = version
        payload['environment'] = environment
        return payload, 200 if report.ready else 503
