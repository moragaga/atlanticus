from application.composition import create_composition


def test_ada_starter_registers_external_example_module() -> None:
    composition = create_composition(None)
    assert sum(module.name == 'navigation' for module in composition.modules) == 1
    assert sum(module.name == 'starter-example' for module in composition.modules) == 1
    assert 'ada.web.application.generic.pages' in composition.page_packages
