from __future__ import annotations

import unittest
from datetime import UTC

from atlanticus.kernel import OperationStatus, utc_now


class StatusAndTimeTests(unittest.TestCase):
    def test_status_values_are_stable_strings(self) -> None:
        self.assertEqual(str(OperationStatus.SUCCESS), 'success')
        self.assertEqual(str(OperationStatus.WARNING), 'warning')
        self.assertEqual(str(OperationStatus.ERROR), 'error')
        self.assertEqual(str(OperationStatus.SKIPPED), 'skipped')

    def test_utc_now_returns_timezone_aware_datetime(self) -> None:
        current = utc_now()

        self.assertIs(current.tzinfo, UTC)
        self.assertIsNotNone(current.utcoffset())


if __name__ == '__main__':
    unittest.main()
