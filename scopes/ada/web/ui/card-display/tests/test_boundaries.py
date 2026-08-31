from pathlib import Path


def test_card_display_implementation_has_no_tool_specific_or_legacy_card_type_semantics() -> None:
    package_root = Path(__file__).resolve().parents[1]
    implementation_text = '\n'.join(
        path.read_text(encoding='utf-8')
        for root in (package_root / 'src', package_root / 'commented')
        for path in root.rglob('*')
        if path.is_file() and path.suffix in {'.py', '.css'}
    ).lower()

    forbidden = (
        'integrated_operations',
        'integrated operations',
        'flotación',
        'flotacion',
        'molienda',
        'carguío',
        'carguio',
        'transporte',
        'puerto',
        'displaycardtype',
        'card_type',
        'en construcción',
        'en construccion',
        'datos desactualizados',
    )

    assert [token for token in forbidden if token in implementation_text] == []
