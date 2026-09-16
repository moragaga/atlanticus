import gzip
import json

import pytest

from atlanticus.web.users.configuration import (
    decode_users_profiles_configuration_import,
    default_users_profiles_configuration,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError


def _payload(document: dict[str, object]) -> bytes:
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return gzip.compress(encoded, mtime=0)


def test_import_decodes_canonical_users_profiles_document() -> None:
    configuration = default_users_profiles_configuration()

    decoded = decode_users_profiles_configuration_import(
        _payload(configuration.to_document())
    )

    assert decoded == configuration


def test_import_rejects_noncanonical_envelope() -> None:
    with pytest.raises(
        UsersConfigurationValidationError,
        match='Users/profiles configuration contract is invalid',
    ):
        decode_users_profiles_configuration_import(
            _payload({'document_type': 'unsupported', 'schema_version': 1})
        )


def test_import_requires_gzip_payload() -> None:
    with pytest.raises(UsersConfigurationValidationError, match='must be gzip encoded'):
        decode_users_profiles_configuration_import(b'{}')
