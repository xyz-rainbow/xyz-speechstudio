"""CrispASR server must not outlive the orchestrator process."""

from __future__ import annotations

from backend.orchestrator import crispasr


def test_atexit_eject_helper_is_callable():
    assert callable(crispasr._atexit_eject_crispasr)
    crispasr._atexit_eject_crispasr()


def test_eject_is_idempotent():
    assert crispasr.server_manager.eject() in (True, False)
    assert crispasr.server_manager.eject() is False
