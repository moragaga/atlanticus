import io
import tokenize
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_PRODUCTIVE = _ROOT / 'src' / 'ada_command_center' / 'processes' / 'alarms_materialization'
_COMMENTED = _ROOT / 'commented' / 'ada_command_center' / 'processes' / 'alarms_materialization'
_IGNORED = {
    tokenize.COMMENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.NEWLINE,
    tokenize.NL,
}


def _tokens(path):
    return [
        (token.type, token.string)
        for token in tokenize.tokenize(io.BytesIO(path.read_bytes()).readline)
        if token.type not in _IGNORED
    ]


def test_commented_mirror_has_same_executable_tokens():
    productive = sorted(path.name for path in _PRODUCTIVE.glob('*.py'))
    commented = sorted(path.name for path in _COMMENTED.glob('*.py'))
    assert commented == productive
    for name in productive:
        assert _tokens(_COMMENTED / name) == _tokens(_PRODUCTIVE / name)
