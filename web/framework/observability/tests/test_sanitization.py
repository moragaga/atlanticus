from atlanticus.web.observability import sanitize


def test_sanitize_redacts_secrets_without_redacting_definition_keys():
    value = sanitize(
        {
            'definition_key': 'movement_mine',
            'client_secret': 'hidden',
            'nested': {'access_token': 'hidden'},
        }
    )

    assert value == {
        'definition_key': 'movement_mine',
        'client_secret': '[REDACTED]',
        'nested': {'access_token': '[REDACTED]'},
    }
