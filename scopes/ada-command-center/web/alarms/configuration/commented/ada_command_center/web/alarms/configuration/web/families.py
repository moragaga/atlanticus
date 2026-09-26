# La familia se determina por su clave estable y por la pertenencia real de reglas y mensajes.
# Estructura y comportamiento idénticos al módulo productivo.

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ada_command_center.web.alarms.configuration.web.authoring import (
    add_message,
    add_rule,
    normalize_authoring_document,
)


@dataclass(frozen=True, slots=True)
class FamilySummary:
    key: str
    rule_indexes: tuple[int, ...]
    message_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FamilyCatalog:
    families: tuple[FamilySummary, ...]
    global_message_indexes: tuple[int, ...]

    def get(self, key: str) -> FamilySummary | None:
        return next((family for family in self.families if family.key == key), None)


def family_catalog(document: dict[str, object] | None) -> FamilyCatalog:
    value = document or {}
    groups: dict[str, tuple[list[int], list[int]]] = {}
    global_messages: list[int] = []
    rules = value.get('rules')
    messages = value.get('messages')
    for index, rule in enumerate(rules if isinstance(rules, list) else []):
        if not isinstance(rule, dict):
            continue
        identity = rule.get('identity')
        if not isinstance(identity, dict):
            continue
        key = identity.get('family_key')
        if isinstance(key, str) and key.strip():
            groups.setdefault(key, ([], []))[0].append(index)
    for index, message in enumerate(messages if isinstance(messages, list) else []):
        if not isinstance(message, dict):
            continue
        if message.get('scope') == 'GLOBAL':
            global_messages.append(index)
        elif message.get('scope') == 'FAMILY':
            key = message.get('family_key')
            if isinstance(key, str) and key.strip():
                groups.setdefault(key, ([], []))[1].append(index)
    return FamilyCatalog(
        families=tuple(
            FamilySummary(key, tuple(rules), tuple(messages))
            for key, (rules, messages) in sorted(
                groups.items(), key=lambda item: (item[0].casefold(), item[0])
            )
        ),
        global_message_indexes=tuple(global_messages),
    )


def require_new_family_key(
    document: dict[str, object] | None,
    raw_key: object,
    *,
    pending: tuple[str, ...] | list[str] = (),
) -> str:
    if not isinstance(raw_key, str) or not raw_key.strip():
        raise ValueError('Family key must not be empty')
    if raw_key != raw_key.strip():
        raise ValueError('Family key must not have leading or trailing whitespace')
    if family_catalog(document).get(raw_key) is not None or raw_key in pending:
        raise ValueError('Family key already exists')
    return raw_key


def add_rule_in_family(document: dict[str, object], key: str) -> dict[str, object]:
    if not isinstance(key, str) or not key.strip():
        raise ValueError('A valid family is required to create a rule')
    updated = add_rule(document)
    existing = {
        identity['alarm_key']
        for entry in updated['rules'][:-1]
        if isinstance(entry, dict)
        for identity in (entry.get('identity'),)
        if isinstance(identity, dict) and identity.get('family_key') == key
    }
    while True:
        alarm_key = f'alarm-{uuid4().hex[:12]}'
        if alarm_key not in existing:
            break
    rule = updated['rules'][-1]
    rule['identity']['family_key'] = key
    rule['identity']['alarm_key'] = alarm_key
    return updated


def add_message_in_family(document: dict[str, object], key: str | None) -> dict[str, object]:
    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise ValueError('A valid family is required to create a family message')
    updated = add_message(document)
    message = updated['messages'][-1]
    message['scope'] = 'GLOBAL' if key is None else 'FAMILY'
    message['family_key'] = key
    return updated


# El borrado de una familia comprueba referencias externas sin modificar la fuente.
def remove_family(document: dict[str, object], key: str) -> dict[str, object]:
    if not isinstance(document, dict) or not isinstance(key, str):
        raise ValueError('Invalid family deletion request')
    family = family_catalog(document).get(key)
    if family is None:
        raise ValueError('The selected family no longer exists')
    rules = document.get('rules')
    messages = document.get('messages')
    if not isinstance(rules, list) or not isinstance(messages, list):
        raise ValueError('Invalid configuration document')
    rule_indexes = set(family.rule_indexes)
    message_indexes = set(family.message_indexes)
    removed_identities = {
        (rules[index]['identity'].get('family_key'), rules[index]['identity'].get('alarm_key'))
        for index in rule_indexes
    }
    removed_message_keys = {messages[index].get('message_key') for index in message_indexes}
    for index, rule in enumerate(rules):
        if index in rule_indexes or not isinstance(rule, dict):
            continue
        reappearance = rule.get('reappearance')
        conditions = (
            reappearance.get('special_conditions') if isinstance(reappearance, dict) else None
        )
        for condition in conditions if isinstance(conditions, list) else []:
            if (
                isinstance(condition, dict)
                and (condition.get('family_key'), condition.get('alarm_key')) in removed_identities
            ):
                raise ValueError('Family rules are referenced by another family')
        associated = rule.get('message_keys')
        if isinstance(associated, list) and removed_message_keys.intersection(associated):
            raise ValueError('Family messages are referenced by another family')
    updated = normalize_authoring_document(document)
    updated['rules'] = [
        rule for index, rule in enumerate(updated['rules']) if index not in rule_indexes
    ]
    updated['messages'] = [
        message for index, message in enumerate(updated['messages']) if index not in message_indexes
    ]
    return updated


def initial_navigation() -> dict[str, object]:
    return {
        'page': 'families',
        'family_key': None,
        'tab': 'rules',
        'rule_index': None,
        'message_index': None,
        'section': 'general',
        'pending_families': [],
    }


def selected_family(navigation: object, document: dict[str, object] | None) -> str | None:
    if not isinstance(navigation, dict) or navigation.get('page') != 'family':
        return None
    key = navigation.get('family_key')
    if not isinstance(key, str):
        return None
    pending = navigation.get('pending_families')
    if family_catalog(document).get(key) is not None:
        return key
    return key if isinstance(pending, list) and key in pending else None


def merged_family_catalog(
    document: dict[str, object] | None, navigation: dict[str, object] | None
) -> FamilyCatalog:
    catalog = family_catalog(document)
    raw = navigation.get('pending_families') if isinstance(navigation, dict) else None
    pending = raw if isinstance(raw, list) else []
    groups = list(catalog.families)
    known = {item.key for item in groups}
    for key in pending:
        if isinstance(key, str) and key.strip() and key not in known:
            groups.append(FamilySummary(key=key, rule_indexes=(), message_indexes=()))
            known.add(key)
    groups.sort(key=lambda item: (item.key.casefold(), item.key))
    return FamilyCatalog(
        families=tuple(groups), global_message_indexes=catalog.global_message_indexes
    )
