# Espejo pedagógico: Users Administration conserva identidad de origen y limita edición a profile y enabled.
from __future__ import annotations

from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.users.administration import UserCandidate, UsersAdministrationSnapshot
from atlanticus.web.users.models import DiscoveredUser, UserRecord


def snapshot_to_document(snapshot: UsersAdministrationSnapshot) -> dict[str, object]:
    return {
        'registry_version': snapshot.registry.version,
        'profiles': [_profile_to_document(profile) for profile in snapshot.profiles],
        'candidates': [_candidate_to_document(candidate) for candidate in snapshot.candidates],
    }


def preserve_profiles(
    fresh: dict[str, object],
    previous: dict[str, object] | None,
) -> dict[str, object]:
    if not isinstance(previous, dict):
        return fresh
    profiles = previous.get('profiles')
    if isinstance(profiles, list):
        fresh = dict(fresh)
        fresh['profiles'] = profiles
    return fresh


def _candidate_to_document(candidate: UserCandidate) -> dict[str, object]:
    return {
        'user_id': candidate.user_id,
        'state': candidate.state.value,
        'registry_user': _record_to_document(candidate.registry_user),
        'directory_user': _directory_to_document(candidate.directory_user),
        'promoted_user': _record_to_document(candidate.promoted_user),
        'issues': list(candidate.issues),
    }


def _record_to_document(user: UserRecord | None) -> dict[str, object] | None:
    return None if user is None else user.to_document()


def _directory_to_document(user: DiscoveredUser | None) -> dict[str, object] | None:
    if user is None:
        return None
    return {
        'user_id': user.user_id,
        'issuer': user.issuer,
        'subject_id': user.subject_id,
        'display_name': user.display_name,
        'email': user.email,
    }


def _profile_to_document(profile: ProfileDefinition) -> dict[str, object]:
    return {
        'key': profile.key,
        'label': profile.label,
        'background_color': profile.background_color,
        'text_color': profile.text_color,
    }
