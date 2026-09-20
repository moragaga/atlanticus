from __future__ import annotations

# Estos modelos describen exclusivamente datos requeridos por la presentación administrativa.
# LocalIdentityBadge deriva las iniciales visibles desde el nombre sin alterar la identidad del usuario.

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.profiles.models import normalize_profile_color

ProfilesWorkspacePayloadReader = Callable[
    [dict[str, object] | None],
    dict[str, object] | None,
]
ProfilesWorkspacePayloadWriter = Callable[
    [dict[str, object] | None, dict[str, object]],
    dict[str, object],
]


@dataclass(frozen=True, slots=True)
class LocalIdentityBadge:
    display_name: str
    background_color: str
    text_color: str

    def __post_init__(self) -> None:
        display_name = self.display_name.strip()
        if not display_name:
            raise ValueError('Local identity display name must not be empty')
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(
            self,
            'background_color',
            normalize_profile_color(self.background_color),
        )
        object.__setattr__(
            self,
            'text_color',
            normalize_profile_color(self.text_color),
        )

    @property
    def avatar_text(self) -> str:
        words = tuple(part for part in self.display_name.split() if part)
        if len(words) == 1:
            return words[0][:2].upper()
        return f'{words[0][0]}{words[-1][0]}'.upper()


def build_profile_avatar_text(label: str) -> str:
    normalized = label.strip()
    if not normalized:
        raise ValueError('Profile label must not be empty')
    return normalized[0].upper()


LocalIdentityBadgeProvider = Callable[[], tuple[LocalIdentityBadge, ...]]


@dataclass(frozen=True, slots=True)
class ProfilesAdminWebContext:
    workspace_payload_reader: ProfilesWorkspacePayloadReader
    workspace_payload_writer: ProfilesWorkspacePayloadWriter
    local_identity_badges_provider: LocalIdentityBadgeProvider
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    editor_revision_store_id: object
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'Profiles Source'
    projection_name: str = 'Profiles Projection'
