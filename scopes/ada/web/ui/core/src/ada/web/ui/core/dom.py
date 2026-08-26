from __future__ import annotations

import re

_DOM_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


def component_identity_attributes(component_key: str) -> dict[str, str]:
    return {'data-ada-component-key': _normalize_dom_key(component_key, label='component key')}


def subcomponent_identity_attributes(subcomponent_key: str) -> dict[str, str]:
    return {
        'data-ada-subcomponent-key': _normalize_dom_key(
            subcomponent_key,
            label='subcomponent key',
        )
    }


def slot_identity_attributes(slot_key: str) -> dict[str, str]:
    return {'data-ada-slot-key': _normalize_dom_key(slot_key, label='slot key')}


def _normalize_dom_key(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _DOM_KEY_PATTERN.fullmatch(value):
        raise ValueError(f'Invalid ADA DOM {label}: {value!r}')
    return value
