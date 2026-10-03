from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from atlanticus.web.master_projection.apply import MasterApplyError, MasterProjectionExecutor
from atlanticus.web.master_projection.plan import UsersPlanState
from atlanticus.web.source.models import SourceKey


class Planner:
    def __init__(self, snapshot_ids=('snapshot-1',)):
        self.snapshot_ids = snapshot_ids

    def inspect(self):
        return SimpleNamespace(
            entries=(),
            users=SimpleNamespace(
                state=(
                    UsersPlanState.SNAPSHOT_SELECTION_REQUIRED
                    if self.snapshot_ids
                    else UsersPlanState.SNAPSHOT_MISSING
                ),
                snapshot_ids=self.snapshot_ids,
            ),
        )


def test_users_replace_executes_selected_snapshot_and_requires_current_catalog_selection():
    calls = []
    planner = Planner()
    executor = MasterProjectionExecutor(
        planner=planner,
        domains=(SimpleNamespace(key=SourceKey('dummy')),),
        users_replace=lambda snapshot_id: calls.append(snapshot_id) or SimpleNamespace(differences=()),
    )
    result = executor.apply_users(snapshot_id='snapshot-1')
    assert result.snapshot_id == 'snapshot-1'
    assert calls == ['snapshot-1']

    with pytest.raises(MasterApplyError, match='outdated'):
        executor.apply_users(snapshot_id='missing')
