def test_tools_namespace_composes_core_and_configuration_at_runtime() -> None:
    import ada.web.tools
    from ada.web.tools.errors import ToolConfigurationValidationError
    from ada.web.tools.structure import ToolStructure
    from ada.web.tools.configuration import ToolConfiguration, ToolLifecycleServices

    assert ada.web.tools.__spec__ is not None
    assert ada.web.tools.__spec__.submodule_search_locations is not None
    assert getattr(ada.web.tools, '__file__', None) is None
    assert ToolConfigurationValidationError is not None
    assert ToolStructure is not None
    assert ToolConfiguration is not None
    assert ToolLifecycleServices is not None
