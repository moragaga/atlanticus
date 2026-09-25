import ast
from pathlib import Path

_SOURCE_ROOT = Path(__file__).parents[1] / 'src' / 'ada_command_center' / 'domain' / 'tools'


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or '')
    return tuple(names)


def test_domain_tools_does_not_depend_on_command_center_web_backend_or_atlanticus() -> None:
    forbidden = (
        'ada_command_center.web',
        'ada_command_center.alarms',
        'ada_command_center.processes',
        'ada_command_center.tools',
        'atlanticus',
        'azure',
    )
    for path in sorted(_SOURCE_ROOT.glob('*.py')):
        for name in _imports(path):
            assert not any(name.startswith(prefix) for prefix in forbidden)


def test_production_code_has_no_comments() -> None:
    for path in sorted(_SOURCE_ROOT.glob('*.py')):
        for line in path.read_text(encoding='utf-8').splitlines():
            assert not line.lstrip().startswith('#')
