import math

import pytest

from ada.kpis.delivery import KpiDeliveryValidationError, canonical_revision


def test_canonical_revision_is_order_independent_for_object_keys() -> None:
    assert canonical_revision({'b': 2, 'a': 1}) == canonical_revision({'a': 1, 'b': 2})


def test_canonical_revision_rejects_non_json_and_nan() -> None:
    with pytest.raises(KpiDeliveryValidationError, match='canonical JSON'):
        canonical_revision({'value': object()})
    with pytest.raises(KpiDeliveryValidationError, match='canonical JSON'):
        canonical_revision({'value': math.nan})
