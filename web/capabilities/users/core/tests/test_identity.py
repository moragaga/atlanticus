import pytest

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key


def test_user_key_is_stable_for_the_same_authenticated_identity() -> None:
    expected = build_user_key(issuer='entra', subject_id='oid-1')

    assert build_user_key(issuer=' entra ', subject_id=' oid-1 ') == expected
    assert expected.startswith('user:')


def test_user_key_preserves_exact_issuer_identity() -> None:
    assert build_user_key(
        issuer='entra',
        subject_id='oid-1',
    ) != build_user_key(
        issuer='ENTRA',
        subject_id='oid-1',
    )


@pytest.mark.parametrize(
    ('issuer', 'subject_id'),
    [(None, 'oid-1'), ('entra', None), ('', 'oid-1'), ('entra', ' ')],
)
def test_user_key_rejects_incomplete_authenticated_identity(
    issuer: str | None,
    subject_id: str | None,
) -> None:
    with pytest.raises(UsersDefinitionError, match='must not be empty'):
        build_user_key(issuer=issuer, subject_id=subject_id)
