from __future__ import annotations

import tokenize
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE / 'src' / 'atlanticus/data_producers/meteodata'
COMMENTED = PACKAGE / 'commented' / 'atlanticus/data_producers/meteodata'
IGNORED = {tokenize.COMMENT, tokenize.ENCODING, tokenize.NL}


def meaningful_tokens(path: Path):
    with path.open('rb') as source:
        return [(item.type, item.string) for item in tokenize.tokenize(source.readline) if item.type not in IGNORED]


def test_pedagogical_mirror_has_same_python_behavior():
    for source in sorted(SOURCE.glob('*.py')):
        assert meaningful_tokens(source) == meaningful_tokens(COMMENTED / source.name)
