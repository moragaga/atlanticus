from atlanticus.web.status_pages import StatusPageAction, status_page_response


def test_status_page_renders_optional_action_and_disables_cache() -> None:
    response = status_page_response(
        status_code=403,
        title='Acceso denegado',
        message='No tienes acceso.',
        action=StatusPageAction(label='Volver al inicio', href='/'),
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 403
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'Acceso denegado' in body
    assert 'Volver al inicio' in body
    assert 'href="/"' in body


def test_status_page_escapes_dynamic_content() -> None:
    response = status_page_response(
        status_code=400,
        title='<Title>',
        message='<Message>',
        action=StatusPageAction(label='<Action>', href='/?x=<value>'),
    )

    body = response.get_data(as_text=True)
    assert '<Title>' not in body
    assert '<Message>' not in body
    assert '<Action>' not in body
    assert '&lt;Title&gt;' in body
    assert '&lt;Message&gt;' in body
    assert '&lt;Action&gt;' in body
    assert 'href="/?x=&lt;value&gt;"' in body
