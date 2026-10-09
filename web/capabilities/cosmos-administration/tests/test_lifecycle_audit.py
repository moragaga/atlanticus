from __future__ import annotations

import pytest

from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.cosmos_administration.audit import (
    BlobCosmosLifecycleAudit,
    CosmosLifecycleAuditError,
)


class FakeStorage(StorageClient):
    def __init__(self):
        self.items = {}

    def upload(self, *, container_name, blob_name, data, overwrite, content_type):
        assert overwrite is False
        assert content_type == 'application/json'
        key = (container_name, blob_name)
        if key in self.items:
            raise RuntimeError('Conflict')
        self.items[key] = data

    def download(self, *, container_name, blob_name):
        return self.items[(container_name, blob_name)]


def test_durable_audit_writes_immutable_verified_blob():
    storage = FakeStorage()
    audit = BlobCosmosLifecycleAudit(
        storage=storage, container_name='audit', blob_prefix='cosmos/lifecycle'
    )
    action_id = 'a' * 32
    audit.record(action_id=action_id, stage='intent', payload={'action': 'delete'})
    assert ('audit', f'cosmos/lifecycle/{action_id}/intent.json') in storage.items
    with pytest.raises(CosmosLifecycleAuditError):
        audit.record(action_id=action_id, stage='intent', payload={'action': 'delete'})


@pytest.mark.parametrize('stage', ['unknown', '../intent'])
def test_audit_rejects_untrusted_stage(stage):
    audit = BlobCosmosLifecycleAudit(
        storage=FakeStorage(), container_name='audit', blob_prefix='cosmos/lifecycle'
    )
    with pytest.raises(CosmosLifecycleAuditError):
        audit.record(action_id='a' * 32, stage=stage, payload={})
