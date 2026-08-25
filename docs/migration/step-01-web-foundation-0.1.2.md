# Atlanticus Web Foundation — Step 01 corrective 0.1.2

Corrective limited to commented-mirror validation.

The Step 01 gate already validates formatting, Ruff and Web Foundation tests before mirror validation. The mirror validator now treats a mirror-only `__init__.py` as harmless only when it contains no executable behavior (comments and an optional module docstring are allowed).

All productive Python files still require a corresponding commented mirror with an equivalent AST. Missing mirrors, semantic differences and additional behavioral Python modules remain failures.
