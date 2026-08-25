from __future__ import annotations

# Publica snapshots de assets manteniendo el orden declarado entre wheels y aplicación.

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any

from atlanticus.web.asset_optimization import optimize_staged_assets
from atlanticus.web.errors import WebAssetError, WebDefinitionError

_LAYER_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
_FILENAME_ORDER_PATTERN = re.compile(r'^\d{2,4}[-_][a-zA-Z0-9][a-zA-Z0-9._-]*$')
_LIST_FILES = {'css': 'css.list', 'js': 'js.list'}
_LOADABLE_KINDS = ('css', 'js')
_COPY_KINDS = ('img',)
_MANIFEST_NAME = 'manifest.json'
_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class AssetLayer:
    name: str
    load_order: int
    package: str | None = None
    resource_directory: str = 'resources'
    source_directory: Path | None = None
    # Solo las capas locales pueden ordenar por nomenclatura; los wheels conservan css.list/js.list.
    filename_ordered: bool = False

    def __post_init__(self) -> None:
        if not _LAYER_NAME_PATTERN.fullmatch(self.name):
            raise WebDefinitionError('Asset layer name has an invalid format')
        if self.load_order < 0 or self.load_order > 9999:
            raise WebDefinitionError('Asset layer load order must be between 0 and 9999')
        if bool(self.package) == bool(self.source_directory):
            raise WebDefinitionError(
                'Asset layer must define exactly one source: package or source_directory'
            )
        if self.package is not None and self.filename_ordered:
            raise WebDefinitionError('Packaged asset layer must use css.list/js.list ordering')
        _validate_relative_path(self.resource_directory, label='Asset resource directory')

    @property
    def target_name(self) -> str:
        safe_name = self.name.replace('-', '_').replace('.', '_')
        return f'{self.load_order:04d}_{safe_name}'


@dataclass(frozen=True, slots=True)
class AssetPublication:
    assets_root: Path
    revision: str
    manifest_path: Path
    css_entries: tuple[str, ...]
    js_entries: tuple[str, ...]


def publish_asset_layers(
    *,
    layers: tuple[AssetLayer, ...],
    publications_root: str | Path,
    optimize: bool = False,
) -> AssetPublication:
    ordered_layers = _validate_layers(layers)
    root = Path(publications_root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='.atlanticus-assets-', dir=root) as temporary:
        staging = Path(temporary)
        # Primero materializamos el orden real; recién después optimizamos el snapshot productivo.
        manifest = _stage_layers(ordered_layers, staging)
        if optimize:
            # CSS se concatena en el orden final y JS se minifica sin concatenarse.
            optimize_staged_assets(staging, manifest)
        manifest['optimized'] = optimize
        manifest['files'] = _hash_staged_files(staging)
        revision = _revision_for_manifest(manifest)
        manifest['schema_version'] = _SCHEMA_VERSION
        manifest['revision'] = revision
        manifest_path = staging / _MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )

        target = root / revision
        if target.exists():
            validate_asset_publication(target)
        else:
            try:
                os.replace(staging, target)
            except OSError:
                # Otro worker Gunicorn puede haber publicado la misma revisión en paralelo.
                if not target.exists():
                    raise
                validate_asset_publication(target)

    return validate_asset_publication(root / revision)


def validate_asset_publication(assets_root: str | Path) -> AssetPublication:
    root = Path(assets_root).resolve()
    manifest_path = root / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise WebAssetError('Asset publication manifest does not exist')

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != _SCHEMA_VERSION:
        raise WebAssetError('Asset publication manifest schema is invalid')

    revision = manifest.get('revision')
    if not isinstance(revision, str) or not revision:
        raise WebAssetError('Asset publication revision is invalid')

    expected_files = manifest.get('files')
    if not isinstance(expected_files, dict):
        raise WebAssetError('Asset publication file manifest is invalid')

    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob('*')
        if path.is_file() and path.name != _MANIFEST_NAME
    }
    if actual_files != set(expected_files):
        raise WebAssetError('Asset publication file set does not match the manifest')

    for relative_path, expected_hash in expected_files.items():
        if _sha256(root / relative_path) != expected_hash:
            raise WebAssetError(f'Asset integrity validation failed: {relative_path}')

    css_entries = _tuple_of_strings(manifest.get('css_entries'), label='CSS entries')
    js_entries = _tuple_of_strings(manifest.get('js_entries'), label='JavaScript entries')
    return AssetPublication(
        assets_root=root,
        revision=revision,
        manifest_path=manifest_path,
        css_entries=css_entries,
        js_entries=js_entries,
    )


def _validate_layers(layers: tuple[AssetLayer, ...]) -> tuple[AssetLayer, ...]:
    seen_names: set[str] = set()
    seen_orders: set[int] = set()
    for layer in layers:
        if layer.name in seen_names:
            raise WebDefinitionError(f'Asset layer name is duplicated: {layer.name}')
        if layer.load_order in seen_orders:
            raise WebDefinitionError(f'Asset layer load order is duplicated: {layer.load_order}')
        seen_names.add(layer.name)
        seen_orders.add(layer.load_order)

    # Las capas locales de aplicación siempre quedan después de los assets empaquetados.
    packaged_orders = [layer.load_order for layer in layers if layer.package is not None]
    local_orders = [layer.load_order for layer in layers if layer.filename_ordered]
    if packaged_orders and local_orders and min(local_orders) <= max(packaged_orders):
        raise WebDefinitionError(
            'Filename-ordered application assets must load after packaged assets'
        )

    return tuple(sorted(layers, key=lambda item: item.load_order))


def _stage_layers(layers: tuple[AssetLayer, ...], staging: Path) -> dict[str, Any]:
    file_hashes: dict[str, str] = {}
    css_entries: list[str] = []
    js_entries: list[str] = []
    layer_manifest: list[dict[str, Any]] = []

    for layer in layers:
        source_root = _resolve_source_root(layer)
        target_root = staging / layer.target_name
        target_root.mkdir(parents=True, exist_ok=True)
        declared: dict[str, tuple[str, ...]] = {}

        for kind in _LOADABLE_KINDS:
            source_kind = _join_source(source_root, kind)
            entries = _resolve_declared_files(
                source_kind,
                kind=kind,
                filename_ordered=layer.filename_ordered,
            )
            declared[kind] = tuple(entry for entry, _ in entries)
            target_kind = target_root / kind
            target_kind.mkdir(parents=True, exist_ok=True)

            for index, (entry, resource) in enumerate(entries):
                target_name = f'{index:04d}__{Path(entry).name}'
                destination = target_kind / target_name
                destination.write_bytes(resource.read_bytes())
                relative = destination.relative_to(staging).as_posix()
                file_hashes[relative] = _sha256(destination)
                if kind == 'css':
                    css_entries.append(relative)
                else:
                    js_entries.append(relative)

            list_resource = _join_source(source_kind, _LIST_FILES[kind])
            if not layer.filename_ordered and _source_is_file(list_resource):
                list_destination = target_kind / _LIST_FILES[kind]
                list_destination.write_text(
                    '\n'.join(declared[kind]) + '\n',
                    encoding='utf-8',
                )
                relative = list_destination.relative_to(staging).as_posix()
                file_hashes[relative] = _sha256(list_destination)

        for kind in _COPY_KINDS:
            source_kind = _join_source(source_root, kind)
            if not _source_is_dir(source_kind):
                continue
            for relative_path, resource in _iter_source_files(source_kind):
                destination = target_root / kind / Path(*relative_path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(resource.read_bytes())
                relative = destination.relative_to(staging).as_posix()
                file_hashes[relative] = _sha256(destination)

        layer_manifest.append(
            {
                'name': layer.name,
                'load_order': layer.load_order,
                'target': layer.target_name,
                'css': declared['css'],
                'js': declared['js'],
            }
        )

    return {
        'layers': layer_manifest,
        'css_entries': css_entries,
        'js_entries': js_entries,
        'files': dict(sorted(file_hashes.items())),
    }


def _hash_staged_files(staging: Path) -> dict[str, str]:
    return {
        path.relative_to(staging).as_posix(): _sha256(path)
        for path in sorted(staging.rglob('*'))
        if path.is_file() and path.name != _MANIFEST_NAME
    }


def _resolve_source_root(layer: AssetLayer):
    if layer.package is not None:
        root = files(layer.package).joinpath(layer.resource_directory)
    else:
        root = layer.source_directory / layer.resource_directory

    if root is None or not _source_is_dir(root):
        raise WebAssetError(f'Asset layer source directory does not exist: {layer.name}')
    return root


def _resolve_declared_files(
    source: Any,
    *,
    kind: str,
    filename_ordered: bool,
) -> tuple[tuple[str, Any], ...]:
    if not _source_is_dir(source):
        return ()

    resources = {
        relative.as_posix(): resource
        for relative, resource in _iter_source_files(source)
        if relative.name != _LIST_FILES[kind]
    }
    if not resources:
        return ()

    list_resource = _join_source(source, _LIST_FILES[kind])
    if filename_ordered:
        # La aplicación final no necesita un .list: el prefijo numérico define un orden estable.
        if _source_is_file(list_resource):
            raise WebAssetError(f'Filename-ordered {kind} assets must not define a list file')
        # La aplicación final usa archivos planos con prefijo numérico para ordenar sin ambigüedad.
        entries = tuple(sorted(resources))
        for entry in entries:
            if (
                '/' in entry
                or not entry.endswith(f'.{kind}')
                or not _FILENAME_ORDER_PATTERN.fullmatch(Path(entry).name)
            ):
                raise WebAssetError(
                    f'Filename-ordered {kind} asset must be a root file with a numeric prefix: '
                    f'{entry}'
                )
        return tuple((entry, resources[entry]) for entry in entries)

    if not _source_is_file(list_resource):
        raise WebAssetError(f'Asset layer {kind} list does not exist')

    entries = _read_asset_list(list_resource.read_text(encoding='utf-8'), kind=kind)
    if set(entries) != set(resources):
        raise WebAssetError(
            f'Asset layer {kind} list must declare every packaged {kind} file exactly once'
        )
    return tuple((entry, resources[entry]) for entry in entries)


def _read_asset_list(content: str, *, kind: str) -> tuple[str, ...]:
    entries: list[str] = []
    seen: set[str] = set()
    expected_suffix = f'.{kind}'

    for raw_line in content.splitlines():
        entry = raw_line.strip()
        if not entry or entry.startswith('#'):
            continue
        normalized = _validate_relative_path(entry, label=f'{kind.upper()} asset path')
        if '/' in normalized:
            raise WebAssetError(f'Asset layer {kind} list only supports files at the layer root')
        if not normalized.endswith(expected_suffix):
            raise WebAssetError(f'Asset layer {kind} list contains an invalid file type')
        if normalized in seen:
            raise WebAssetError(f'Asset layer {kind} path is duplicated: {normalized}')
        entries.append(normalized)
        seen.add(normalized)

    if not entries:
        raise WebAssetError(f'Asset layer {kind} list must not be empty')
    return tuple(entries)


def _revision_for_manifest(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]


def _validate_relative_path(value: str, *, label: str) -> str:
    normalized = value.replace('\\', '/').strip('/')
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or '..' in path.parts:
        raise WebDefinitionError(f'{label} is invalid')
    return path.as_posix()


def _iter_source_files(root: Any, prefix: PurePosixPath | None = None):
    current = PurePosixPath() if prefix is None else prefix
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        relative = current / child.name
        if child.is_dir():
            yield from _iter_source_files(child, relative)
        elif child.is_file():
            yield relative, child


def _join_source(root: Any, child: str):
    return root.joinpath(child)


def _source_is_dir(value: Any) -> bool:
    return bool(value is not None and value.is_dir())


def _source_is_file(value: Any) -> bool:
    return bool(value is not None and value.is_file())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _tuple_of_strings(value: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise WebAssetError(f'Asset publication {label} are invalid')
    return tuple(value)
