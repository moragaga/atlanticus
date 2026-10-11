from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from ada.processes.alarm_delivery.contract import ToolDeliveryConfirmation
from atlanticus.state import AtomicJsonStore

_DOCUMENT_TYPE = 'ada_alarm_delivery_checkpoint'
_SCHEMA_VERSION = 1
_PATH = 'state/confirmations.json'


class AlarmDeliveryCheckpointError(ValueError):
    pass


class AlarmDeliveryCheckpointStore:
    def __init__(self, *, root: Path, modeler_application: str) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError('Delivery checkpoint root must be an absolute Path')
        if (
            not isinstance(modeler_application, str)
            or not modeler_application
            or modeler_application != modeler_application.strip()
        ):
            raise ValueError('Modeler application must be normalized text')
        self._modeler_application = modeler_application
        self._store = AtomicJsonStore(root_path=root, max_document_bytes=None)

    def read(self) -> dict[str, ToolDeliveryConfirmation]:
        document = self._store.read(_PATH)
        if document is None:
            return {}
        if not isinstance(document, dict) or set(document) != {
            'document_type',
            'schema_version',
            'modeler_application',
            'confirmations',
            'sha256',
        }:
            raise AlarmDeliveryCheckpointError('Delivery checkpoint shape is invalid')
        if (
            document['document_type'] != _DOCUMENT_TYPE
            or type(document['schema_version']) is not int
            or document['schema_version'] != _SCHEMA_VERSION
            or document['modeler_application'] != self._modeler_application
            or not isinstance(document['sha256'], str)
            or _digest({key: val for key, val in document.items() if key != 'sha256'})
            != document['sha256']
        ):
            raise AlarmDeliveryCheckpointError('Delivery checkpoint integrity is invalid')
        values = document['confirmations']
        if not isinstance(values, dict):
            raise AlarmDeliveryCheckpointError('Delivery confirmations inventory is invalid')
        result: dict[str, ToolDeliveryConfirmation] = {}
        for key, value in values.items():
            try:
                receipt = ToolDeliveryConfirmation.from_document(value)
            except (TypeError, ValueError) as error:
                raise AlarmDeliveryCheckpointError(
                    'Delivery checkpoint receipt is invalid'
                ) from error
            if key != receipt.tool_key:
                raise AlarmDeliveryCheckpointError('Delivery checkpoint Tool key differs')
            result[key] = receipt
        return result

    def confirm(self, receipt: ToolDeliveryConfirmation) -> None:
        if not isinstance(receipt, ToolDeliveryConfirmation):
            raise TypeError('Confirmation must be a ToolDeliveryConfirmation')
        current = self.read()
        previous = current.get(receipt.tool_key)
        if previous is not None:
            old = previous.source_journal_position
            new = receipt.source_journal_position
            old_key = (old['segment_id'], old['byte_offset'])
            new_key = (new['segment_id'], new['byte_offset'])
            if new_key < old_key or (new_key == old_key and old['commit_id'] != new['commit_id']):
                raise AlarmDeliveryCheckpointError('Delivery checkpoint cannot move backwards')
            if previous == receipt:
                return
        current[receipt.tool_key] = receipt
        body: dict[str, object] = {
            'document_type': _DOCUMENT_TYPE,
            'schema_version': _SCHEMA_VERSION,
            'modeler_application': self._modeler_application,
            'confirmations': {key: item.to_document() for key, item in sorted(current.items())},
        }
        self._store.replace(_PATH, {**body, 'sha256': _digest(body)})


def _digest(document: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False
        ).encode('utf-8')
    ).hexdigest()
