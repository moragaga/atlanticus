from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass

from ada.processes.alarm_delivery.public_projection import (
    LIVE_PUBLIC_SCHEMA_VERSION,
    public_tool_projection,
)

SOURCE_DOCUMENT_TYPE = 'ada_alarm_modeler_live_projection'
SOURCE_SCHEMA_VERSION = 3
CONFIRMATION_DOCUMENT_TYPE = 'ada_alarm_delivery_confirmation'
CONFIRMATION_SCHEMA_VERSION = 1
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_SOURCE_FIELDS = frozenset(
    {
        'document_type',
        'schema_version',
        'artifact_ref',
        'source_journal_position',
        'source_as_of',
        'tools',
        'sha256',
    }
)
_TOOL_FIELDS = frozenset(
    {'tool_key', 'retired', 'alarms', 'operator_pool', 'operator_view', 'meta'}
)
_POSITION_FIELDS = frozenset({'segment_id', 'byte_offset', 'commit_id'})
_ARTIFACT_FIELDS = frozenset({'source_key', 'result_id', 'manifest_sha256', 'resolution_key'})
_RESOLUTION_FIELDS = frozenset({'alarm_configuration_revision', 'confirmed_tool_catalog_revision'})
_CONFIRMATION_FIELDS = frozenset(
    {
        'document_type',
        'schema_version',
        'tool_key',
        'destination_identity',
        'semantic_sha256',
        'source_sha256',
        'source_journal_position',
    }
)


class AlarmDeliveryContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ToolDeliveryConfirmation:
    tool_key: str
    destination_identity: str
    semantic_sha256: str
    source_sha256: str
    source_journal_position: dict[str, object]

    def __post_init__(self) -> None:
        _text(self.tool_key, 'confirmation tool_key')
        _text(self.destination_identity, 'destination identity')
        _digest_text(self.semantic_sha256, 'semantic_sha256')
        _digest_text(self.source_sha256, 'source_sha256')
        _position(self.source_journal_position)
        object.__setattr__(self, 'source_journal_position', deepcopy(self.source_journal_position))

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': CONFIRMATION_DOCUMENT_TYPE,
            'schema_version': CONFIRMATION_SCHEMA_VERSION,
            'tool_key': self.tool_key,
            'destination_identity': self.destination_identity,
            'semantic_sha256': self.semantic_sha256,
            'source_sha256': self.source_sha256,
            'source_journal_position': deepcopy(self.source_journal_position),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> ToolDeliveryConfirmation:
        item = _exact_mapping(document, _CONFIRMATION_FIELDS, 'Delivery confirmation')
        if (
            item['document_type'] != CONFIRMATION_DOCUMENT_TYPE
            or type(item['schema_version']) is not int
            or item['schema_version'] != CONFIRMATION_SCHEMA_VERSION
        ):
            raise AlarmDeliveryContractError('Delivery confirmation contract is invalid')
        return cls(
            tool_key=item['tool_key'],
            destination_identity=item['destination_identity'],
            semantic_sha256=item['semantic_sha256'],
            source_sha256=item['source_sha256'],
            source_journal_position=item['source_journal_position'],
        )


@dataclass(frozen=True, slots=True)
class ToolDeliveryCandidate:
    tool_key: str
    destination_identity: str
    tool: dict[str, object]
    artifact_ref: dict[str, object]
    source_sha256: str
    source_journal_position: dict[str, object]
    source_as_of: str
    semantic_sha256: str

    def confirmation(self) -> ToolDeliveryConfirmation:
        return ToolDeliveryConfirmation(
            tool_key=self.tool_key,
            destination_identity=self.destination_identity,
            semantic_sha256=self.semantic_sha256,
            source_sha256=self.source_sha256,
            source_journal_position=self.source_journal_position,
        )


@dataclass(frozen=True, slots=True)
class ToolDeliveryPlan:
    source_sha256: str
    pending: tuple[ToolDeliveryCandidate, ...]
    unchanged: tuple[str, ...]


def plan_tool_deliveries(
    *,
    modeler_document: Mapping[str, object],
    destination_identities: Mapping[str, str],
    confirmations: Mapping[str, ToolDeliveryConfirmation],
) -> ToolDeliveryPlan:
    source = _source(modeler_document)
    if not isinstance(destination_identities, Mapping):
        raise AlarmDeliveryContractError('Destinations must be a mapping')
    if not isinstance(confirmations, Mapping):
        raise AlarmDeliveryContractError('Delivery confirmations must be a mapping')
    tools = source['tools']
    for tool_key, identity in destination_identities.items():
        _text(tool_key, 'destination tool_key')
        _text(identity, 'destination identity')
    if not set(tools).issubset(destination_identities):
        raise AlarmDeliveryContractError('A Modeler Tool has no delivery destination')
    if not set(confirmations).issubset(tools):
        raise AlarmDeliveryContractError('A previously delivered Tool lacks a retirement snapshot')
    for tool_key, confirmation in confirmations.items():
        if (
            not isinstance(confirmation, ToolDeliveryConfirmation)
            or confirmation.tool_key != tool_key
        ):
            raise AlarmDeliveryContractError('Delivery confirmation Tool identity is invalid')
    pending: list[ToolDeliveryCandidate] = []
    unchanged: list[str] = []
    for tool_key, tool in sorted(tools.items()):
        fingerprint = _hash(
            {
                'schema_version': LIVE_PUBLIC_SCHEMA_VERSION,
                'artifact_ref': source['artifact_ref'],
                'tool': public_tool_projection(tool),
            }
        )
        previous = confirmations.get(tool_key)
        if previous is not None:
            _monotonic(previous.source_journal_position, source['source_journal_position'])
        if (
            previous is not None
            and previous.destination_identity == destination_identities[tool_key]
            and previous.semantic_sha256 == fingerprint
        ):
            unchanged.append(tool_key)
            continue
        pending.append(
            ToolDeliveryCandidate(
                tool_key=tool_key,
                destination_identity=destination_identities[tool_key],
                tool=deepcopy(tool),
                artifact_ref=deepcopy(source['artifact_ref']),
                source_sha256=source['sha256'],
                source_journal_position=deepcopy(source['source_journal_position']),
                source_as_of=source['source_as_of'],
                semantic_sha256=fingerprint,
            )
        )
    return ToolDeliveryPlan(
        source_sha256=source['sha256'],
        pending=tuple(pending),
        unchanged=tuple(unchanged),
    )


def _source(value: Mapping[str, object]) -> dict[str, object]:
    document = _exact_mapping(value, _SOURCE_FIELDS, 'Modeler source')
    if (
        document['document_type'] != SOURCE_DOCUMENT_TYPE
        or type(document['schema_version']) is not int
        or document['schema_version'] != SOURCE_SCHEMA_VERSION
    ):
        raise AlarmDeliveryContractError('Modeler source contract is unsupported')
    _digest_text(document['sha256'], 'Modeler source sha256')
    if (
        _hash({key: item for key, item in document.items() if key != 'sha256'})
        != document['sha256']
    ):
        raise AlarmDeliveryContractError('Modeler source checksum mismatch')
    artifact = _exact_mapping(document['artifact_ref'], _ARTIFACT_FIELDS, 'Modeler artifact')
    for name in ('source_key', 'result_id'):
        _text(artifact[name], name)
    _digest_text(artifact['manifest_sha256'], 'manifest_sha256')
    resolution = _exact_mapping(artifact['resolution_key'], _RESOLUTION_FIELDS, 'Resolution key')
    for name in _RESOLUTION_FIELDS:
        _text(resolution[name], name)
    _position(document['source_journal_position'])
    _text(document['source_as_of'], 'source_as_of')
    tools = document['tools']
    if not isinstance(tools, Mapping):
        raise AlarmDeliveryContractError('Modeler Tools inventory is invalid')
    for tool_key, value in tools.items():
        _text(tool_key, 'tool_key')
        tool = _exact_mapping(value, _TOOL_FIELDS, 'Modeler Tool')
        if (
            tool['tool_key'] != tool_key
            or not isinstance(tool['retired'], bool)
            or not isinstance(tool['alarms'], dict)
            or not isinstance(tool['operator_pool'], list)
            or not isinstance(tool['operator_view'], list)
            or not isinstance(tool['meta'], dict)
        ):
            raise AlarmDeliveryContractError('Modeler Tool projection is invalid')
        if tool['retired'] and (tool['alarms'] or tool['operator_pool'] or tool['operator_view']):
            raise AlarmDeliveryContractError('Retired Tool must have an empty live state')
    return deepcopy(document)


def _monotonic(previous: Mapping[str, object], current: Mapping[str, object]) -> None:
    old_key = (previous['segment_id'], previous['byte_offset'])
    new_key = (current['segment_id'], current['byte_offset'])
    if old_key > new_key or (old_key == new_key and previous['commit_id'] != current['commit_id']):
        raise AlarmDeliveryContractError('Modeler source precedes a confirmed delivery')


def _exact_mapping(value: object, keys: frozenset[str], label: str) -> dict:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise AlarmDeliveryContractError(f'{label} fields are invalid')
    return dict(value)


def _text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise AlarmDeliveryContractError(f'{label} must be normalized text')


def _digest_text(value: object, label: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AlarmDeliveryContractError(f'{label} must be a lowercase SHA-256 digest')


def _position(value: object) -> None:
    document = _exact_mapping(value, _POSITION_FIELDS, 'Journal position')
    _text(document['segment_id'], 'segment_id')
    _text(document['commit_id'], 'commit_id')
    if type(document['byte_offset']) is not int or document['byte_offset'] <= 0:
        raise AlarmDeliveryContractError('Journal byte_offset must be positive')


def _hash(document: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')
    except (TypeError, ValueError, OverflowError) as error:
        raise AlarmDeliveryContractError('Delivery document must be canonical JSON') from error
    return hashlib.sha256(encoded).hexdigest()
