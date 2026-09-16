from pathlib import Path

import pytest

from atlanticus.web.users.authority import (
    BASIC_AUTHORITY_KEY,
    GUEST_AUTHORITY_KEY,
    LOCAL_AUTHORITY_KEY,
    ROOT_AUTHORITY_KEY,
    has_full_access,
    is_assignable_authority,
    normalize_authority_key,
)
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.local import LOCAL_JANE, LOCAL_JOHN, select_local_user


def test_base_authorities_keep_system_semantics() -> None:
    assert is_assignable_authority(GUEST_AUTHORITY_KEY) is False
    assert is_assignable_authority(LOCAL_AUTHORITY_KEY) is False
    assert is_assignable_authority(BASIC_AUTHORITY_KEY) is True
    assert is_assignable_authority(ROOT_AUTHORITY_KEY) is True
    assert has_full_access(GUEST_AUTHORITY_KEY) is False
    assert has_full_access(BASIC_AUTHORITY_KEY) is False
    assert has_full_access(ROOT_AUTHORITY_KEY) is True
    assert has_full_access(LOCAL_AUTHORITY_KEY) is True


def test_functional_authority_keys_remain_assignable_without_users_owning_profiles() -> None:
    assert is_assignable_authority('operator') is True
    assert normalize_authority_key(' Operator ') == 'operator'


def test_authority_key_rejects_empty_or_spaced_values() -> None:
    with pytest.raises(UsersDefinitionError):
        normalize_authority_key(' ')
    with pytest.raises(UsersDefinitionError):
        normalize_authority_key('read only')


def test_local_selector_preserves_jane_and_john_contracts() -> None:
    jane = select_local_user(selector=lambda users: users[0])
    john = select_local_user(selector=lambda users: users[1])

    assert jane.display_name == 'Jane Doe'
    assert jane.subject_id == LOCAL_JANE.subject_id
    assert jane.authority_key == LOCAL_AUTHORITY_KEY
    assert jane.avatar_background_color == '#C85D91'
    assert jane.avatar_text_color == '#FFFFFF'
    assert jane.is_local is True
    assert jane.has_full_access is True

    assert john.display_name == 'John Doe'
    assert john.subject_id == LOCAL_JOHN.subject_id
    assert john.authority_key == LOCAL_AUTHORITY_KEY
    assert john.avatar_background_color == '#3778C2'
    assert john.avatar_text_color == '#FFFFFF'
    assert john.is_local is True
    assert john.has_full_access is True


def test_users_core_has_no_profiles_dependency() -> None:
    package_root = Path(__file__).resolve().parents[1]
    pyproject = (package_root / 'pyproject.toml').read_text(encoding='utf-8')
    sources = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in sorted((package_root / 'src').rglob('*.py'))
    )

    assert 'atlanticus-web-profiles' not in pyproject
    assert 'atlanticus.web.profiles' not in sources
