from atlanticus.web.navigation.configuration import NAVIGATION_COSMOS_REQUIREMENTS


def test_navigation_declares_cosmos_container_requirement() -> None:
    assert [
        (item.container_name, item.partition_key, item.ttl_seconds)
        for item in NAVIGATION_COSMOS_REQUIREMENTS
    ] == [('configuration', '/partition_key', None)]
