import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_FILES = ('application.py', 'modules.py', 'pages.py')


@pytest.mark.parametrize('filename', _FILES)
def test_productive_and_commented_sources_have_identical_ast(filename: str) -> None:
    productive = _ROOT / 'src' / 'atlanticus' / 'web' / filename
    commented = _ROOT / 'commented' / 'atlanticus' / 'web' / filename

    productive_tree = ast.dump(ast.parse(productive.read_text(encoding='utf-8')))
    commented_tree = ast.dump(ast.parse(commented.read_text(encoding='utf-8')))

    assert commented_tree == productive_tree
