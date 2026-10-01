from application.composition import create_composition


def test_ada_starter_uses_application_pages_and_keeps_ada_shell_modules() -> None:
    composition = create_composition(None)
    assert sum(module.name == 'navigation' for module in composition.modules) == 1
    assert sum(module.name == 'starter-example' for module in composition.modules) == 0
    assert composition.page_packages == ('application.pages',)
