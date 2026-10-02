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
ADA_ROOT = WEB_ROOT / "ada"
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


def _load_ada_builder():
    return _load_module(
        "atlanticus_ada_web_distribution", ADA_ROOT / "build_distribution.py"
    )


def _qualify_ada_distribution(*, application: Path, timeout: int) -> dict[str, object]:
    process = subprocess.run(
        [
            sys.executable,
            str(ADA_ROOT / "qualify_distribution.py"),
            "--application",
            str(application),
        ],
        cwd=ADA_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        result = json.loads(process.stdout)
    except ValueError as error:
        raise RuntimeError(
            "ADA distribution qualification returned invalid JSON"
        ) from error
    if not isinstance(result, dict) or not isinstance(result.get("status"), str):
        raise RuntimeError("ADA distribution qualification returned an invalid result")
    if process.returncode not in (0, 2):
        raise RuntimeError("ADA distribution qualification process failed unexpectedly")
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
        if product["distribution_strategy"] == "ada":
            builder = _load_ada_builder()
            distribution = builder.build_ada_distribution(
                application=application, uv=uv
            )
        elif product["distribution_strategy"] == "wheelhouse":
            distribution = build_wheelhouse(
                profile=profile, application=application, uv=uv
            )
        else:
            raise ValueError("Unsupported Web distribution strategy")
        stages["distribution"] = distribution
        stage = "qualification"
        if product["qualification_strategy"] == "ada-precheck":
            qualification = _qualify_ada_distribution(
                application=application, timeout=timeout
            )
        elif product["qualification_strategy"] == "runtime":
            qualification = qualify(
                application=application,
                profile=profile,
                python=python,
                timeout=timeout,
                portable=True,
                inspect_only=False,
            )
        elif product["qualification_strategy"] == "artifact-precheck":
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
