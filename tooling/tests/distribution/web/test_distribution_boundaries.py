import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_WEB = _ROOT / "tooling/distribution/web"


def test_shared_tree_has_no_product_specific_subtrees() -> None:
    assert not (_WEB / "ada").exists()
    assert not (_WEB / "starter/ada").exists()
    assert not (_WEB / "starter/command-center").exists()


def test_product_specific_distribution_surfaces_belong_to_scopes() -> None:
    assert (_ROOT / "scopes/ada/tooling/distribution/web/starter").is_dir()
    assert (
        _ROOT / "scopes/ada/tooling/distribution/web/build_distribution.py"
    ).is_file()
    assert (
        _ROOT
        / "scopes/ada-command-center/tooling/distribution/web/starter/pyproject.toml"
    ).is_file()


def test_master_projection_runtime_is_consumed_as_shared_capability() -> None:
    application = tomllib.loads(
        (
            _ROOT / "scopes/ada/web/application/ada-generic-application/pyproject.toml"
        ).read_text(encoding="utf-8")
    )
    starter = tomllib.loads(
        (
            _ROOT / "scopes/ada/tooling/distribution/web/starter/pyproject.toml"
        ).read_text(encoding="utf-8")
    )

    application_dependencies = set(application["project"]["dependencies"])
    starter_dependencies = set(starter["project"]["dependencies"])

    assert "atlanticus-web-master-projection==0.1.0" in application_dependencies
    assert any(
        dependency.startswith("ada-generic-application==")
        for dependency in starter_dependencies
    )
    assert not any(
        dependency.startswith("atlanticus-web-master-projection")
        for dependency in starter_dependencies
    )
