from __future__ import annotations

import tomllib
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_CATALOG = _REPOSITORY_ROOT / "tooling/distribution/web/products.toml"


def _products() -> dict[str, dict[str, object]]:
    payload = tomllib.loads(_CATALOG.read_text(encoding="utf-8"))
    products = payload.get("products")
    assert isinstance(products, dict)
    return products


def test_catalog_preserves_current_web_products() -> None:
    products = _products()
    assert tuple(products) == ("generic", "ada")
    assert products["generic"]["distribution_strategy"] == "wheelhouse"
    assert products["generic"]["qualification_strategy"] == "runtime"
    assert products["ada"]["distribution_strategy"] == "ada"
    assert products["ada"]["qualification_strategy"] == "ada-precheck"


def test_catalog_root_packages_match_current_projects() -> None:
    for product in _products().values():
        root = _REPOSITORY_ROOT / str(product["root_project"]) / "pyproject.toml"
        metadata = tomllib.loads(root.read_text(encoding="utf-8"))["project"]
        assert metadata["name"] == product["root_package"]
        assert metadata["requires-python"] == "==3.14.2"


def test_catalog_starter_inputs_exist() -> None:
    starter_root = _REPOSITORY_ROOT / "tooling/distribution/web/starter"
    for product in _products().values():
        overlay = product.get("starter_overlay")
        if overlay:
            assert (starter_root / str(overlay)).is_dir()
        contract = product.get("environment_contract")
        if contract:
            assert (_REPOSITORY_ROOT / str(contract)).is_file()
        for relative in product["base_excluded_roots"]:
            assert isinstance(relative, str) and relative


def test_catalog_strategies_are_supported_by_current_tooling() -> None:
    products = _products().values()
    assert {product["distribution_strategy"] for product in products} <= {
        "wheelhouse",
        "ada",
    }
    assert {product["qualification_strategy"] for product in products} <= {
        "runtime",
        "ada-precheck",
    }
    assert {product["probe_strategy"] for product in products} <= {"generic", "ada"}
