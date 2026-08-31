from __future__ import annotations

import re
from pathlib import Path

# Este archivo es el espejo pedagógico del validador productivo de tokens CSS.
TOKEN_FILE = Path('scopes/ada/web/ui/core/src/ada/web/ui/core/resources/css/10-tokens.css')
COMMENTED_TOKEN_FILE = Path(
    'scopes/ada/web/ui/core/commented/ada/web/ui/core/resources/css/10-tokens.css'
)
LEGACY_TOKENS = (
    '--background',
    '--primary-background',
    '--secondary-background',
    '--tertiary-background',
    '--custom-text-color',
    '--primary-border-color',
    '--secondary-border-color',
    '--loader-color',
    '--loader-background',
    '--dark-color',
)
REQUIRED_TOKENS = (
    '--ada-color-surface-primary',
    '--ada-color-surface-secondary',
    '--ada-color-surface-tertiary',
    '--ada-color-surface-strong',
    '--ada-color-surface-active',
    '--ada-color-surface-inverse',
    '--ada-color-surface-emphasis',
    '--ada-color-text-primary',
    '--ada-color-text-secondary',
    '--ada-color-text-strong',
    '--ada-color-text-emphasis',
    '--ada-color-text-soft',
    '--ada-color-text-muted',
    '--ada-color-text-inverse',
    '--ada-color-border-primary',
    '--ada-color-border-secondary',
    '--ada-color-border-strong',
    '--ada-color-border-active',
)
SHARED_LITERALS = re.compile(
    r'#(?:EBEBEB|C7C7C7|E1E1E1|4D4D4D|BDBDBD|313131|FFFFFF|2E2E2E)\b',
    re.IGNORECASE,
)
CSS_MIRRORS = (
    (
        Path('scopes/ada/web/ui/core/src/ada/web/ui/core/resources/css/10-tokens.css'),
        COMMENTED_TOKEN_FILE,
    ),
    (
        Path(
            'scopes/ada/web/shell/navigation/src/ada/web/shell/navigation/resources/css/10-navigation.css'
        ),
        Path(
            'scopes/ada/web/shell/navigation/commented/ada/web/shell/navigation/resources/css/10-navigation.css'
        ),
    ),
    (
        Path(
            'scopes/ada/web/shell/header/src/ada/web/shell/header/resources/css/10-operational-header.css'
        ),
        Path(
            'scopes/ada/web/shell/header/commented/ada/web/shell/header/resources/css/10-operational-header.css'
        ),
    ),
    (
        Path(
            'scopes/ada/web/ui/global-indicator/src/ada/web/ui/global_indicator/resources/css/10-global-indicator.css'
        ),
        Path(
            'scopes/ada/web/ui/global-indicator/commented/ada/web/ui/global_indicator/resources/css/10-global-indicator.css'
        ),
    ),
    (
        Path(
            'scopes/ada/web/ui/time-status/src/ada/web/ui/time_status/resources/css/10-time-status.css'
        ),
        Path(
            'scopes/ada/web/ui/time-status/commented/ada/web/ui/time_status/resources/css/10-time-status.css'
        ),
    ),
    (
        Path(
            'scopes/ada/web/ui/content-state/src/ada/web/ui/content_state/resources/css/10-content-state.css'
        ),
        Path(
            'scopes/ada/web/ui/content-state/commented/ada/web/ui/content_state/resources/css/10-content-state.css'
        ),
    ),
    (
        Path(
            'scopes/ada/web/alarms/management-summary/src/ada/web/alarms/management_summary/resources/css/10-management-summary.css'
        ),
        Path(
            'scopes/ada/web/alarms/management-summary/commented/ada/web/alarms/management_summary/resources/css/10-management-summary.css'
        ),
    ),
    (
        Path(
            'scopes/ada/web/alarms/status/src/ada/web/alarms/status/resources/css/10-alarm-status.css'
        ),
        Path(
            'scopes/ada/web/alarms/status/commented/ada/web/alarms/status/resources/css/10-alarm-status.css'
        ),
    ),
    (
        Path(
            'scopes/ada/web/inspection/surface/src/ada/web/inspection/surface/resources/css/10-kpi-inspection-surface.css'
        ),
        Path(
            'scopes/ada/web/inspection/surface/commented/ada/web/inspection/surface/resources/css/10-kpi-inspection-surface.css'
        ),
    ),
    (
        Path(
            'scopes/ada/web/alarms/baseline-surface/src/ada/web/alarms/baseline_surface/resources/css/10-alarm-baseline-surface.css'
        ),
        Path(
            'scopes/ada/web/alarms/baseline-surface/commented/ada/web/alarms/baseline_surface/resources/css/10-alarm-baseline-surface.css'
        ),
    ),
)
EXCLUDED_PARTS = {
    '.runtime',
    '.venv',
    '.pytest_cache',
    '.ruff_cache',
    '__pycache__',
    'build',
    'dist',
    '__MACOSX',
}


def _repository_root() -> Path:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / 'scopes' / 'ada').is_dir() and (candidate / 'scripts').is_dir():
            return candidate
    raise SystemExit('Repository root not found')


def _productive_css(root: Path) -> tuple[Path, ...]:
    # Sólo auditamos CSS productivo de ADA; vendor, runtime y mirrors quedan fuera.
    result: list[Path] = []
    for base in (root / 'scopes' / 'ada',):
        for path in base.rglob('*.css'):
            relative = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in relative.parts):
                continue
            if 'commented' in relative.parts:
                continue
            if 'bootstrap' in path.name.lower():
                continue
            result.append(relative)
    return tuple(sorted(result))


def _normalize_css(text: str) -> str:
    # Los comentarios pedagógicos no cambian el contrato CSS.
    without_comments = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return re.sub(r'\s+', '', without_comments)


def _validate_authority(root: Path) -> None:
    # UI Core es la única autoridad de los colores compartidos ADA.
    token_path = root / TOKEN_FILE
    text = token_path.read_text(encoding='utf-8')
    missing = [token for token in REQUIRED_TOKENS if f'{token}:' not in text]
    if missing:
        raise SystemExit('Missing ADA root CSS tokens: ' + ', '.join(missing))
    if '._dash-loading {' not in text or 'display: none !important;' not in text:
        raise SystemExit('Dash native loading suppression is missing from ADA UI Core')


def _validate_consumers(root: Path) -> None:
    # Consumidores deben usar tokens; no aliases legacy ni literales compartidos.
    violations: list[str] = []
    for relative in _productive_css(root):
        text = (root / relative).read_text(encoding='utf-8')
        for legacy in LEGACY_TOKENS:
            if re.search(rf'{re.escape(legacy)}(?![A-Za-z0-9_-])', text):
                violations.append(f'{relative}: legacy token {legacy}')
        if relative != TOKEN_FILE:
            matches = sorted({match.group(0) for match in SHARED_LITERALS.finditer(text)})
            if matches:
                violations.append(f'{relative}: shared literals {", ".join(matches)}')
    if violations:
        raise SystemExit('CSS token contract violations:\n' + '\n'.join(violations))


def _validate_css_mirrors(root: Path) -> None:
    # Los CSS comentados deben conservar exactamente el mismo comportamiento.
    failures: list[str] = []
    for source, commented in CSS_MIRRORS:
        source_path = root / source
        commented_path = root / commented
        if not commented_path.is_file():
            failures.append(f'missing CSS commented mirror: {commented}')
            continue
        source_css = _normalize_css(source_path.read_text(encoding='utf-8'))
        commented_css = _normalize_css(commented_path.read_text(encoding='utf-8'))
        if source_css != commented_css:
            failures.append(f'CSS commented mirror mismatch: {source}')
    if failures:
        raise SystemExit('\n'.join(failures))


def main() -> int:
    # Ejecutamos todas las restricciones como una sola puerta semántica.
    root = _repository_root()
    _validate_authority(root)
    _validate_consumers(root)
    _validate_css_mirrors(root)
    print('ADA CSS token contract validated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
