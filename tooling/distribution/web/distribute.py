from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = WEB_ROOT.parents[2]
_PRODUCTS = tomllib.loads((WEB_ROOT / "products.toml").read_text(encoding="utf-8"))[
    "products"
]
_PROFILES = tuple(_PRODUCTS)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Web distribution module is unavailable: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _repository_path(value: object) -> Path:
    relative = Path(str(value))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Web product path must be repository-relative")
    return REPOSITORY_ROOT / relative


_wheels = _load_module(
    "atlanticus_web_build_wheelhouse", WEB_ROOT / "build_wheelhouse.py"
)
_generator = _load_module(
    "atlanticus_web_generate_starter", WEB_ROOT / "generate_starter.py"
)
_qualifier = _load_module(
    "atlanticus_web_qualify_starter", WEB_ROOT / "qualify_starter.py"
)
WheelhouseBuildError = _wheels.WheelhouseBuildError
build_wheelhouse = _wheels.build_wheelhouse
generate_starter = _generator.generate_starter
qualify = _qualifier.qualify


def _load_distribution_handler(profile: str, product: dict[str, object]):
    path = _repository_path(product["distribution_handler"])
    module = _load_module(
        f"atlanticus_web_distribution_{profile.replace('-', '_')}",
        path,
    )
    name = str(product["distribution_callable"])
    handler = getattr(module, name, None)
    if not callable(handler):
        raise RuntimeError("Web product distribution handler is unavailable")
    return handler


def _run_qualification_handler(
    *,
    profile: str,
    product: dict[str, object],
    application: Path,
    timeout: int,
) -> dict[str, object]:
    path = _repository_path(product["qualification_handler"])
    process = subprocess.run(
        [sys.executable, str(path), "--application", str(application)],
        cwd=path.parent,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        result = json.loads(process.stdout)
    except ValueError as error:
        raise RuntimeError("Web product qualification returned invalid JSON") from error
    if not isinstance(result, dict) or not isinstance(result.get("status"), str):
        raise RuntimeError("Web product qualification returned an invalid result")
    if process.returncode not in (0, 2):
        raise RuntimeError("Web product qualification process failed unexpectedly")
    if result.get("profile") != profile:
        raise RuntimeError("Web product qualification returned a different profile")
    return result


def build_web_distribution(
    *,
    profile: str,
    destination: Path,
    uv: str,
    python: Path,
    timeout: int,
) -> dict[str, object]:
    if profile not in _PROFILES:
        raise ValueError("Unknown Web distribution profile")
    product = _PRODUCTS[profile]
    destination = destination.expanduser().resolve()
    stages: dict[str, object] = {}
    stage = "starter"
    try:
        application = generate_starter(profile=profile, destination=destination)
        stages["starter"] = {"status": "PASS", "application": str(application)}
        stage = "distribution"
        strategy = product["distribution_strategy"]
        if strategy == "wheelhouse":
            distribution = build_wheelhouse(
                profile=profile, application=application, uv=uv
            )
        elif strategy == "handler":
            handler = _load_distribution_handler(profile, product)
            distribution = handler(application=application, uv=uv)
        else:
            raise ValueError("Unsupported Web distribution strategy")
        stages["distribution"] = distribution
        stage = "qualification"
        strategy = product["qualification_strategy"]
        if strategy == "runtime":
            qualification = qualify(
                application=application,
                profile=profile,
                python=python,
                timeout=timeout,
                portable=True,
                inspect_only=False,
            )
        elif strategy == "artifact-precheck":
            qualification = qualify(
                application=application,
                profile=profile,
                python=python,
                timeout=timeout,
                portable=True,
                inspect_only=False,
            )
            if qualification.get("status") == "PASS":
                qualification = {
                    **qualification,
                    "status": "PRECHECK_PASS",
                    "runtime": "UNVERIFIED",
                }
        elif strategy == "handler":
            qualification = _run_qualification_handler(
                profile=profile,
                product=product,
                application=application,
                timeout=timeout,
            )
        else:
            raise ValueError("Unsupported Web qualification strategy")
        stages["qualification"] = qualification
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        ValueError,
        WheelhouseBuildError,
    ) as error:
        return {
            "status": "BLOCKED",
            "profile": profile,
            "application": str(destination),
            "failed_stage": stage,
            "error": str(error),
            "stages": stages,
        }
    expected = product["qualification_expected_status"]
    status = qualification.get("status")
    if status != expected:
        return {
            "status": status if status in ("BLOCKED", "FAIL") else "BLOCKED",
            "profile": profile,
            "application": str(destination),
            "failed_stage": "qualification",
            "stages": stages,
        }
    return {
        "status": status,
        "profile": profile,
        "application": str(destination),
        "stages": stages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and qualify an Atlanticus Web distribution"
    )
    parser.add_argument("--profile", choices=_PROFILES, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    destination = args.destination or (
        REPOSITORY_ROOT / "distribution" / f"{args.profile}-web-starter"
    )
    uv = shutil.which("uv")
    if uv is None:
        result = {
            "status": "BLOCKED",
            "profile": args.profile,
            "application": str(destination.expanduser().resolve()),
            "failed_stage": "preflight",
            "error": "uv executable is required",
            "stages": {},
        }
    else:
        result = build_web_distribution(
            profile=args.profile,
            destination=destination,
            uv=uv,
            python=args.python,
            timeout=args.timeout,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    raise SystemExit(0 if result["status"] in ("PASS", "PRECHECK_PASS") else 2)


if __name__ == "__main__":
    main()
