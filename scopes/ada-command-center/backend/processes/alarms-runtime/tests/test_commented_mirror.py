import io
import tokenize
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_PRODUCTION_ROOT = _ROOT / 'src' / 'ada_command_center' / 'processes' / 'alarms_runtime'
_COMMENTED_ROOT = _ROOT / 'commented' / 'ada_command_center' / 'processes' / 'alarms_runtime'
_IGNORED = {
    tokenize.COMMENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.NEWLINE,
    tokenize.NL,
}


def test_commented_mirror_matches_productive_tokens() -> None:
    production = sorted(path.name for path in _PRODUCTION_ROOT.glob('*.py'))
    commented = sorted(path.name for path in _COMMENTED_ROOT.glob('*.py'))
    assert commented == production
    for name in production:
        assert _tokens(_COMMENTED_ROOT / name) == _tokens(_PRODUCTION_ROOT / name)


def _tokens(path: Path) -> list[tuple[int, str]]:
    source = path.read_bytes()
    return [
        (token.type, token.string)
        for token in tokenize.tokenize(io.BytesIO(source).readline)
        if token.type not in _IGNORED
    ]
