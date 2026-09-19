from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from secrets import choice

from atlanticus.web.profiles.models import LOCAL_PROFILE_KEY
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import EffectiveUser, build_avatar_text, normalize_user_color

# Las identidades y colores locales son propiedad de Users; sólo la key local pertenece a Profiles.
LOCAL_ISSUER = 'atlanticus-local'
LOCAL_JANE_BACKGROUND_COLOR = '#C85D91'
LOCAL_JANE_TEXT_COLOR = '#FFFFFF'
LOCAL_JOHN_BACKGROUND_COLOR = '#3778C2'
LOCAL_JOHN_TEXT_COLOR = '#FFFFFF'


@dataclass(frozen=True, slots=True)
class LocalUserDefinition:
    subject_id: str
    display_name: str
    avatar_background_color: str
    avatar_text_color: str

    def __post_init__(self) -> None:
        subject_id = self.subject_id.strip()
        display_name = self.display_name.strip()
        if not subject_id:
            raise UsersDefinitionError('Local user subject id must not be empty')
        if not display_name:
            raise UsersDefinitionError('Local user display name must not be empty')
        object.__setattr__(self, 'subject_id', subject_id)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(
            self,
            'avatar_background_color',
            normalize_user_color(self.avatar_background_color),
        )
        object.__setattr__(
            self,
            'avatar_text_color',
            normalize_user_color(self.avatar_text_color),
        )

    def to_effective_user(self) -> EffectiveUser:
        return EffectiveUser(
            user_id=build_user_key(issuer=LOCAL_ISSUER, subject_id=self.subject_id),
            subject_id=self.subject_id,
            display_name=self.display_name,
            email=None,
            enabled=True,
            avatar_text=build_avatar_text(self.display_name),
            profile_key=LOCAL_PROFILE_KEY,
            avatar_background_color=self.avatar_background_color,
            avatar_text_color=self.avatar_text_color,
            is_local=True,
        )


LOCAL_JANE = LocalUserDefinition(
    subject_id='local:jane-doe',
    display_name='Jane Doe',
    avatar_background_color=LOCAL_JANE_BACKGROUND_COLOR,
    avatar_text_color=LOCAL_JANE_TEXT_COLOR,
)
LOCAL_JOHN = LocalUserDefinition(
    subject_id='local:john-doe',
    display_name='John Doe',
    avatar_background_color=LOCAL_JOHN_BACKGROUND_COLOR,
    avatar_text_color=LOCAL_JOHN_TEXT_COLOR,
)
LOCAL_USERS = (LOCAL_JANE, LOCAL_JOHN)


def select_local_user(
    *,
    selector: Callable[[tuple[LocalUserDefinition, ...]], LocalUserDefinition] | None = None,
) -> EffectiveUser:
    selected = (selector or choice)(LOCAL_USERS)
    if selected not in LOCAL_USERS:
        raise UsersDefinitionError('Local user selector returned an unknown identity')
    return selected.to_effective_user()
