# Modela únicamente la jerarquía lógica ADA; no conoce SourceStore, Blob, Cosmos ni providers.
# La composición entrega el root/prefix derivado a cada capability según su ownership.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True, slots=True)
class AdaStorageNamespace:
    application_namespace: str
    tool_namespace: str

    def __post_init__(self) -> None:
        # Ambos nombres son segmentos lógicos, no rutas suministradas por el caller.
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
            'tool_namespace',
            _require_namespace_segment(
                self.tool_namespace,
                'tool_namespace',
            ),
        )

    @property
    def application_prefix(self) -> str:
        # Nivel global: users y cualquier capability con ownership de aplicación.
        return self.application_namespace

    @property
    def tool_prefix(self) -> str:
        # Nivel Tool: Source, Projection y otros estados propios de la Tool.
        return f'{self.application_namespace}/{self.tool_namespace}'

    def local_application_root(self, base_root: str | Path) -> Path:
        # Ejemplo: /data + conciencia_situacional.
        return _require_absolute_root(base_root) / self.application_namespace

    def local_tool_root(self, base_root: str | Path) -> Path:
        # Ejemplo: /data/conciencia_situacional/operaciones_integradas.
        # LocalSourceStore recibe este root y agrega internamente sources/<SourceKey>.
        return self.local_application_root(base_root) / self.tool_namespace

    def local_projection_root(self, base_root: str | Path) -> Path:
        # Las projections locales comparten la frontera explícita projections/.
        return self.local_tool_root(base_root) / 'projections'

    def application_blob_name(self, relative_path: str) -> str:
        # Permite ubicar recursos globales sin retroceder desde el namespace Tool.
        return _join_prefix(self.application_prefix, relative_path)

    def tool_blob_name(self, relative_path: str) -> str:
        # Permite ubicar recursos propios de Tool bajo el mismo namespace global.
        return _join_prefix(self.tool_prefix, relative_path)


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
