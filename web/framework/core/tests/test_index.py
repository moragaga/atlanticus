from atlanticus.web.index import IndexContribution, IndexPageDefinition, render_index_string


def test_index_composes_application_and_module_contributions() -> None:
    rendered = render_index_string(
        application_id='test-app',
        display_name='Test App',
        version='0.1.0',
        definition=IndexPageDefinition(
            head_fragments=('<meta name="application" content="test">',),
            runtime_config={'safe': '<value>'},
        ),
        module_contributions=(
            (
                'module-a',
                IndexContribution(
                    body_end_fragments=('<div id="module-a"></div>',),
                    runtime_config={'enabled': True},
                ),
            ),
        ),
    )

    assert '<meta name="application" content="test">' in rendered
    assert '<div id="module-a"></div>' in rendered
    assert '"module-a":{"enabled":true}' in rendered
    assert '\\u003cvalue\\u003e' in rendered
