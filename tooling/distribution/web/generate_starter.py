from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = WEB_ROOT.parents[2]
STARTER_ROOT = WEB_ROOT / 'starter'
_PROFILES = ('generic', 'ada')


def _copy_product_files(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob('*')):
        if (
            not path.is_file()
            or {'commented', 'tests', '__pycache__', '.pytest_cache'}
            & set(path.relative_to(source).parts)
            or path.suffix == '.pyc'
        ):
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def generate_starter(*, profile: str, destination: Path) -> Path:
    if profile not in _PROFILES:
        raise ValueError('Unknown Web Starter profile')
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError('Web Starter destination already exists')
    if profile == 'ada' and not (
        REPOSITORY_ROOT / 'scopes/ada/web/application/ada-generic-application/.env.detail'
    ).is_file():
        raise FileNotFoundError('ADA Generic environment contract is missing')
    destination.mkdir(parents=True)
    _copy_product_files(STARTER_ROOT / 'base', destination)
    if profile == 'ada':
        _copy_product_files(STARTER_ROOT / 'ada', destination)
        canonical_env_detail = (
            REPOSITORY_ROOT
            / 'scopes/ada/web/application/ada-generic-application/.env.detail'
        )
        shutil.copyfile(canonical_env_detail, destination / '.env.detail')
    hashes = {
        path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(destination.rglob('*'))
        if path.is_file()
    }
    (destination / 'manifest.json').write_text(
        json.dumps(
            {
                'artifact_kind': 'web-application-starter',
                'profile': profile,
                'qualification': 'UNVERIFIED',
                'wheelhouse_included': False,
                'files': hashes,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + '\n',
        encoding='utf-8',
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=_PROFILES, required=True)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    destination = args.destination or (
        REPOSITORY_ROOT / 'distribution' / f'{args.profile}-web-starter'
    )
    print(generate_starter(profile=args.profile, destination=destination))


if __name__ == '__main__':
    main()
