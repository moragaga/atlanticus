from __future__ import annotations

import argparse
import json
import sys
import tomllib
from importlib import metadata
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent
_PRODUCTS = tomllib.loads((WEB_ROOT / "products.toml").read_text(encoding="utf-8"))[
    "products"
]
_PROFILES = tuple(_PRODUCTS)
_STARTER_PACKAGES = frozenset(
    str(product["starter_package"]) for product in _PRODUCTS.values()
)


def _verify_dependencies(portable: bool) -> list[str]:
    errors: list[str] = []
    for distribution in metadata.distributions():
        name = (distribution.metadata.get("Name") or "").lower().replace("_", "-")
        if not name.startswith(("atlanticus-", "ada-")):
            continue
        direct_url = distribution.read_text("direct_url.json")
        if direct_url is None:
            continue
        try:
            record = json.loads(direct_url)
        except ValueError:
            errors.append(f"Invalid installation metadata for {name}")
            continue
        if (
            portable
            and name not in _STARTER_PACKAGES
            and (record.get("dir_info", {}).get("editable") is True)
        ):
            errors.append(f"Editable internal dependency is not portable: {name}")
    return errors


# Los productos con composition root propio se validan como artefactos.
def _probe_artifact(*, product: dict[str, object], portable: bool) -> dict[str, object]:
    starter_package = str(product["starter_package"])
    root_package = str(product["root_package"])
    metadata.version(starter_package)
    metadata.version(root_package)
    matches = tuple(
        entry
        for entry in metadata.entry_points(group="console_scripts")
        if entry.name == starter_package
    )
    if len(matches) != 1:
        raise AssertionError("Starter console entrypoint is missing or ambiguous")
    entrypoint = matches[0].load()
    if not callable(entrypoint):
        raise AssertionError("Starter console entrypoint is not callable")
    checks = ["starter.metadata", "root.metadata", "starter.entrypoint"]
    errors = _verify_dependencies(portable)
    if errors:
        return {"status": "FAIL", "checks": checks, "errors": errors}
    checks.append("dependencies.portable")
    return {"status": "PASS", "checks": checks, "python": sys.version.split()[0]}


def _check_response(client: object, path: str, *, status: int = 200) -> object:
    response = client.get(path)
    if response.status_code != status:
        raise AssertionError(
            f"Unexpected HTTP status for {path}: {response.status_code}"
        )
    return response


# Sólo el Starter genérico se compone dentro del probe compartido.
def _probe_generic(*, portable: bool) -> dict[str, object]:
    metadata.version("application-starter")
    from application.composition import create_application_definition
    from atlanticus.web.application import create_web_application

    runtime = create_web_application(create_application_definition())
    checks: list[str] = []
    client = runtime.server.test_client()
    live = _check_response(client, "/health/live").get_json()
    if live.get("status") != "alive":
        raise AssertionError("Health liveness response is invalid")
    checks.append("health.live")
    ready = client.get("/health/ready")
    if ready.status_code not in (200, 503) or ready.get_json().get("status") not in (
        "ready",
        "not_ready",
    ):
        raise AssertionError("Health readiness response is invalid")
    checks.append("health.ready.diagnostic")
    _check_response(client, "/")
    checks.append("home.http")
    layout = _check_response(client, "/_dash-layout").get_json()
    if "application-content" not in json.dumps(layout):
        raise AssertionError("Dash application layout is missing the expected root")
    checks.append("dash.layout")
    errors = _verify_dependencies(portable)
    if errors:
        return {"status": "FAIL", "checks": checks, "errors": errors}
    return {
        "status": "PASS",
        "checks": checks,
        "python": sys.version.split()[0],
        "readiness": ready.get_json()["status"],
    }


def probe(*, profile: str, application: Path, portable: bool) -> dict[str, object]:
    del application
    product = _PRODUCTS[profile]
    strategy = product["probe_strategy"]
    if strategy == "artifact":
        return _probe_artifact(product=product, portable=portable)
    if strategy == "generic":
        return _probe_generic(portable=portable)
    raise ValueError("Unsupported Web Starter probe strategy")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=_PROFILES, required=True)
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    try:
        outcome = probe(
            profile=args.profile, application=args.application, portable=args.portable
        )
    except Exception as error:
        outcome = {
            "status": "FAIL",
            "error_type": type(error).__name__,
            "error": str(error),
        }
    print("STARTER_QUALIFICATION_RESULT:" + json.dumps(outcome, ensure_ascii=False))
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
