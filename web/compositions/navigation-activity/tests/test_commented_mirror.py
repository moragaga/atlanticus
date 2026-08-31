import io
import tokenize
from pathlib import Path

_PRODUCTION = Path(__file__).parents[1] / 'src/atlanticus/web/compositions/navigation_activity'
_COMMENTED = Path(__file__).parents[1] / 'commented/atlanticus/web/compositions/navigation_activity'


def _tokens(path: Path):
    return [
        (token.type, token.string)
        for token in tokenize.generate_tokens(
            io.StringIO(path.read_text(encoding='utf-8')).readline
        )
        if token.type not in {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING}
        and not (token.type == tokenize.STRING and token.start[0] == 1)
    ]


def test_commented_mirror_only_adds_comments() -> None:
    for source in sorted(_PRODUCTION.glob('*.py')):
        mirror = _COMMENTED / source.name
        assert mirror.exists()
        assert _tokens(mirror) == _tokens(source)
