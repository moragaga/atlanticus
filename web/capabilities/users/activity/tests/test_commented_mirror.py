import io
import tokenize
from pathlib import Path

_PRODUCTION = Path(__file__).parents[1] / 'src/atlanticus/web/users/activity'
_COMMENTED = Path(__file__).parents[1] / 'commented/atlanticus/web/users/activity'


def _tokens(path: Path):
    return [
        (token.type, token.string)
        for token in tokenize.generate_tokens(
            io.StringIO(path.read_text(encoding='utf-8')).readline
        )
        if token.type not in {tokenize.COMMENT, tokenize.NL, tokenize.ENCODING}
        and not (token.type == tokenize.STRING and token.start[0] == 1)
    ]


def test_python_mirrors_only_add_comments() -> None:
    for source in sorted(_PRODUCTION.rglob('*.py')):
        relative = source.relative_to(_PRODUCTION)
        mirror = _COMMENTED / relative
        assert mirror.exists()
        assert _tokens(mirror) == _tokens(source)


def test_javascript_and_list_mirrors_only_add_comments() -> None:
    for relative in (Path('resources/js/10_user_activity.js'), Path('resources/js/js.list')):
        production = (_PRODUCTION / relative).read_text(encoding='utf-8').splitlines()
        commented = (_COMMENTED / relative).read_text(encoding='utf-8').splitlines()
        executable = [
            line
            for line in commented
            if not line.lstrip().startswith('//') and not line.lstrip().startswith('#')
        ]
        assert executable == production
