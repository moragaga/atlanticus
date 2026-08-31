import io
import tokenize
from pathlib import Path

_PRODUCTION_ROOT = Path(__file__).parents[1] / 'src/atlanticus/web/pwa'
_COMMENTED_ROOT = Path(__file__).parents[1] / 'commented/atlanticus/web/pwa'


def _python_tokens(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding='utf-8')
    return [
        (token.type, token.string)
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type
        not in {
            tokenize.COMMENT,
            tokenize.NL,
            tokenize.ENCODING,
        }
        and not (token.type == tokenize.STRING and token.start[0] == 1)
    ]


def test_commented_mirror_only_adds_comments() -> None:
    for production_path in sorted(_PRODUCTION_ROOT.glob('*.py')):
        if production_path.name == 'py.typed':
            continue
        commented_path = _COMMENTED_ROOT / production_path.name
        assert commented_path.exists()
        assert _python_tokens(commented_path) == _python_tokens(production_path)


def test_commented_runtime_assets_only_add_comments() -> None:
    relative_paths = (
        Path('resources/service-worker.js'),
        Path('resources/assets/js/10_pwa_registration.js'),
        Path('resources/assets/js/js.list'),
    )
    for relative_path in relative_paths:
        production = (_PRODUCTION_ROOT / relative_path).read_text(encoding='utf-8').splitlines()
        commented = (_COMMENTED_ROOT / relative_path).read_text(encoding='utf-8').splitlines()
        executable = [
            line
            for line in commented
            if not line.lstrip().startswith('//') and not line.lstrip().startswith('#')
        ]
        assert executable == production
