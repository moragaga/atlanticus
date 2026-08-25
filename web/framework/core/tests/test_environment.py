import pytest

from atlanticus.web.environment import EnvironmentReader, WebEnvironment, resolve_environment
from atlanticus.web.errors import WebConfigurationError


def test_environment_reader_reads_required_and_optional_values_without_domain_semantics():
    reader = EnvironmentReader({'ENDPOINT': 'https://example.test', 'SECRET': 'value'})

    assert reader.require('ENDPOINT') == 'https://example.test'
    assert reader.optional('SECRET') == 'value'
    assert reader.optional('MISSING') is None


def test_environment_reader_snapshots_the_supplied_mapping():
    values = {'DATABASE': 'first'}
    reader = EnvironmentReader(values)

    values['DATABASE'] = 'second'

    assert reader.require('DATABASE') == 'first'


def test_environment_reader_rejects_missing_or_empty_required_values():
    reader = EnvironmentReader({'EMPTY': ''})

    with pytest.raises(WebConfigurationError, match="Required environment variable 'MISSING'"):
        reader.require('MISSING')
    with pytest.raises(WebConfigurationError, match="Required environment variable 'EMPTY'"):
        reader.require('EMPTY')


def test_environment_reader_rejects_invalid_variable_names():
    reader = EnvironmentReader({})

    with pytest.raises(TypeError, match='Environment variable name must be non-empty text'):
        reader.require('')
    with pytest.raises(ValueError, match='Environment variable name is invalid'):
        reader.optional(' INVALID ')


def test_environment_defaults_to_local():
    assert resolve_environment({}) is WebEnvironment.LOCAL


def test_environment_accepts_local_and_production():
    assert resolve_environment({'ATLANTICUS_ENVIRONMENT': 'local'}) is WebEnvironment.LOCAL
    assert (
        resolve_environment({'ATLANTICUS_ENVIRONMENT': 'production'}) is WebEnvironment.PRODUCTION
    )


def test_environment_rejects_unknown_value():
    with pytest.raises(WebConfigurationError, match='Invalid ATLANTICUS_ENVIRONMENT'):
        resolve_environment({'ATLANTICUS_ENVIRONMENT': 'dev'})
