from __future__ import annotations

import ast
import sys
from pathlib import Path


def _python_files(root: Path) -> dict[Path, Path]:
    return {path.relative_to(root): path for path in root.rglob('*.py')}


def _is_nonbehavioral_package_marker(path: Path) -> bool:
    if path.name != '__init__.py':
        return False

    tree = ast.parse(path.read_text(encoding='utf-8'))
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            body.pop(0)
    return not body


def _validate_pair(source_root: Path, commented_root: Path) -> None:
    source_files = _python_files(source_root)
    commented_files = _python_files(commented_root)

    missing = sorted(source_files.keys() - commented_files.keys())
    raw_extra = commented_files.keys() - source_files.keys()
    extra = sorted(
        relative
        for relative in raw_extra
        if not _is_nonbehavioral_package_marker(commented_files[relative])
    )

    if missing:
        joined = ', '.join(str(path) for path in missing)
        raise SystemExit(f'Missing commented mirrors: {joined}')
    if extra:
        joined = ', '.join(str(path) for path in extra)
        raise SystemExit(f'Unexpected behavioral commented mirrors: {joined}')

    for relative, source in sorted(source_files.items()):
        commented = commented_files[relative]
        source_ast = ast.dump(
            ast.parse(source.read_text(encoding='utf-8')),
            include_attributes=False,
        )
        commented_ast = ast.dump(
            ast.parse(commented.read_text(encoding='utf-8')),
            include_attributes=False,
        )
        if source_ast != commented_ast:
            raise SystemExit(f'Commented mirror mismatch: {source_root}/{relative}')


def main(arguments: list[str]) -> int:
    if not arguments or len(arguments) % 2:
        raise SystemExit(
            'Usage: validate_mirrors.py SOURCE_ROOT COMMENTED_ROOT [SOURCE_ROOT COMMENTED_ROOT ...]'
        )

    for index in range(0, len(arguments), 2):
        _validate_pair(Path(arguments[index]), Path(arguments[index + 1]))

    print('Commented mirrors validated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
