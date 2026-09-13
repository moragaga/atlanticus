from atlanticus.web.users.configuration.web import build_users_history_preview
from atlanticus.web.users.identity import build_user_key


def _text(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, (str, int, float)):
        return str(value)
    children = getattr(value, 'children', None)
    if isinstance(children, (list, tuple)):
        return ' '.join(_text(item) for item in children)
    return _text(children)


def test_users_history_preview_shows_profiles_and_assignments_without_access_semantics() -> None:
    preview = build_users_history_preview(
        {
            'administrator_background_color': '#26425A',
            'administrator_text_color': '#FFFFFF',
            'guest_background_color': '#D6DADE',
            'guest_text_color': '#0D1B2A',
            'profiles': [
                {
                    'key': 'operator',
                    'label': 'Operador',
                    'background_color': '#C9A24B',
                    'text_color': '#0D1B2A',
                }
            ],
            'users': [
                {
                    'user_id': build_user_key(
                        issuer='entra',
                        subject_id='jane-subject',
                    ),
                    'display_name': 'Jane Doe',
                    'email': 'jane@example.com',
                    'profile_key': 'operator',
                    'enabled': True,
                    'issuer': 'entra',
                    'subject_id': 'jane-subject',
                }
            ],
        }
    )

    text = _text(preview)

    assert 'Perfiles 4' in text
    assert 'Perfiles personalizados 1' in text
    assert 'Operador operator' in text
    assert 'Fondo #C9A24B' in text
    assert 'Texto #0D1B2A' in text
    assert 'Acceso total' not in text
    assert 'Acceso restringido' not in text
    expected_user_id = build_user_key(
        issuer='entra',
        subject_id='jane-subject',
    )
    assert f'Jane Doe {expected_user_id}' in text
    assert 'jane@example.com' in text
    assert 'Perfil: operator' in text
    assert 'Activo' in text
