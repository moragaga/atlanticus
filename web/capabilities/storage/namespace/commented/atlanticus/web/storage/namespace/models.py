# Modela una jerarquía lógica reutilizable de aplicación + scope.
# No conoce SourceStore, Blob, Cosmos ni el significado de negocio del segundo segmento.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True, slots=True)
class StorageNamespace:
    application_namespace: str
    scope_namespace: str

    def __post_init__(self) -> None:
        # Ambos nombres son segmentos lógicos y se validan antes de derivar rutas o prefijos.
        object.__setattr__(
            self,
            'application_namespace',
            _require_namespace_segment(
                self.application_namespace,
                'application_namespace',
            ),
        )
        object.__setattr__(
            self,
            'scope_namespace',
            _require_namespace_segment(
                self.scope_namespace,
                'scope_namespace',
            ),
        )

    @property
    def application_prefix(self) -> str:
        # Nivel compartido por recursos cuyo ownership corresponde a toda la aplicación.
        return self.application_namespace

    @property
    def scope_prefix(self) -> str:
        # Nivel subordinado reutilizable; cada producto decide si representa Tool u otro scope.
        return f'{self.application_namespace}/{self.scope_namespace}'

    def local_application_root(self, base_root: str | Path) -> Path:
        # Deriva el root local de aplicación desde un root físico absoluto provisto por composición.
        return _require_absolute_root(base_root) / self.application_namespace

    def local_scope_root(self, base_root: str | Path) -> Path:
        # Agrega el scope lógico sin imponer semántica de producto sobre ese segundo nivel.
        return self.local_application_root(base_root) / self.scope_namespace

    def local_projection_root(self, base_root: str | Path) -> Path:
        # Las projections locales conservan la frontera física projections/ existente.
        return self.local_scope_root(base_root) / 'projections'

    def application_blob_name(self, relative_path: str) -> str:
        # Deriva nombres Blob application-scoped sin conocer containers ni credenciales.
        return _join_prefix(self.application_prefix, relative_path)

    def scope_blob_name(self, relative_path: str) -> str:
        # Deriva nombres Blob scope-scoped preservando la misma identidad lógica local/durable.
        return _join_prefix(self.scope_prefix, relative_path)


def _require_namespace_segment(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    normalized = value.strip()
    if not normalized:
        raise ValueError(f'{field_name} must not be empty')
    if normalized != value:
        raise ValueError(f'{field_name} must not contain surrounding whitespace')
    if normalized in {'.', '..'}:
        raise ValueError(f'{field_name} must be a logical namespace segment')
    if '/' in normalized or '\\' in normalized or '\x00' in normalized:
        raise ValueError(f'{field_name} must not contain path separators')
    return normalized


def _require_absolute_root(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('base_root must be an absolute path')
    return path


def _join_prefix(prefix: str, relative_path: str) -> str:
    path = _require_relative_posix_path(relative_path)
    return f'{prefix}/{path}'


def _require_relative_posix_path(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError('relative_path must be text')
    normalized = value.strip().replace('\\', '/')
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith('/')
        or path.is_absolute()
        or any(part in {'', '.', '..'} for part in path.parts)
        or '\x00' in normalized
    ):
        raise ValueError('relative_path must be a safe relative path')
    return path.as_posix()
