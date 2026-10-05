from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AdaApplicationDescriptor:
    import_name: str
    application_id: str
    display_name: str
    distribution_name: str
    application_root: Path

    def __post_init__(self) -> None:
        for field_name in (
            'import_name',
            'application_id',
            'display_name',
            'distribution_name',
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f'{field_name} must be non-empty trimmed text')
        if not isinstance(self.application_root, Path):
            raise TypeError('application_root must be pathlib.Path')
        object.__setattr__(self, 'application_root', self.application_root.expanduser().resolve())

    @property
    def default_publications_root(self) -> Path:
        return self.application_root / '.runtime' / 'publications'


GENERIC_APPLICATION_DESCRIPTOR = AdaApplicationDescriptor(
    import_name='ada.web.application.generic',
    application_id='ada-generic-application',
    display_name='ADA',
    distribution_name='ada-generic-application',
    application_root=Path(__file__).resolve().parents[5],
)
