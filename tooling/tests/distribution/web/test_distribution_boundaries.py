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


def test_master_projection_runtime_belongs_to_ada_generic_application() -> None:
    package = (
        _ROOT / "scopes/ada/web/application/ada-generic-application/src/"
        "ada/web/application/generic/master_projection"
    )
    for name in ("material.py", "reader.py", "provision.py"):
        assert (package / name).is_file()
    starter = _ROOT / "scopes/ada/tooling/distribution/web/starter/src/application"
    assert not (starter / "master_projection").exists()
    assert not (starter / "local_resources.py").exists()
