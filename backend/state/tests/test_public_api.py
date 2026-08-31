import atlanticus.state as state


def test_public_api_exposes_state_0_2_contract() -> None:
    assert state.__version__ == '1.0.0'
    assert state.DEFAULT_MAX_DOCUMENT_BYTES == 1024 * 1024
    assert state.AtomicJsonStore.__name__ == 'AtomicJsonStore'
    assert state.AtomicStateStore.__name__ == 'AtomicStateStore'
