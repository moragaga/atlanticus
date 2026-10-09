from __future__ import annotations

from atlanticus.runtime.lease import ExecutionLease

from .test_output_current import _init, _publisher, _read


class _LeaseContext:
    def __init__(self, lease: ExecutionLease) -> None:
        self._lease = lease

    def assert_lease_current(self) -> None:
        self._lease.assert_current()

    def fenced_mutation(self):
        return self._lease.fenced_mutation()


def test_current_publication_does_not_reacquire_nonreentrant_lease_fence(tmp_path):
    persistence = _init(tmp_path)
    publisher = _publisher(tmp_path)
    with ExecutionLease(
        volume_path=tmp_path / 'lease-volume',
        application='alarm-runtime-test',
        service_name='alarm-runtime',
        module_name='ada.processes.alarm_runtime',
        run_id='current-publication-regression',
        lease_timeout_seconds=30,
        renewal_seconds=10,
        wait_seconds=0,
    ) as lease:
        context = _LeaseContext(lease)
        assert publisher.publish(context=context, persistence=persistence)
        assert publisher.publish(context=context, persistence=persistence) is False
    assert _read(tmp_path)['state']['groups'] == []
