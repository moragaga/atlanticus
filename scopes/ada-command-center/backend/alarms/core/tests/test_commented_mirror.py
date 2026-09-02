import io
import tokenize
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_PRODUCTION_ROOT = _PACKAGE_ROOT / 'src/ada_command_center/alarms/core'
_COMMENTED_ROOT = _PACKAGE_ROOT / 'commented/ada_command_center/alarms/core'


def _python_tokens(path: Path) -> list[tuple[int, str]]:
    tokens: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(
        io.StringIO(path.read_text(encoding='utf-8')).readline
    ):
        if token.type in {
            tokenize.COMMENT,
            tokenize.ENCODING,
            tokenize.ENDMARKER,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.NEWLINE,
            tokenize.NL,
        }:
            continue
        tokens.append((token.type, token.string))
    return tokens


def test_commented_mirror_only_adds_comments() -> None:
    production_paths = tuple(sorted(_PRODUCTION_ROOT.glob('*.py')))
    assert production_paths
    for production_path in production_paths:
        commented_path = _COMMENTED_ROOT / production_path.name
        assert commented_path.exists()
        assert _python_tokens(commented_path) == _python_tokens(production_path)
