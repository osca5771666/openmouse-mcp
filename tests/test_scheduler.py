from __future__ import annotations

import threading
import time

import pytest

from mouse_mcp.errors import ActionCancelled
from mouse_mcp.scheduler import ActionRunner


def test_emergency_stop_cancels_current_and_drains_pending_jobs() -> None:
    runner = ActionRunner()
    started = threading.Event()
    current_error: list[BaseException] = []
    pending_error: list[BaseException] = []

    def current(cancel: threading.Event) -> str:
        started.set()
        cancel.wait(3)
        return "not-cancelled"

    def pending(_cancel: threading.Event) -> str:
        return "should-not-run"

    def run_current() -> None:
        try:
            runner.submit(current)
        except BaseException as exc:
            current_error.append(exc)

    def run_pending() -> None:
        try:
            runner.submit(pending)
        except BaseException as exc:
            pending_error.append(exc)

    first = threading.Thread(target=run_current)
    second = threading.Thread(target=run_pending)
    first.start()
    assert started.wait(1)
    second.start()
    time.sleep(0.05)
    runner.emergency_stop("test")

    first.join(2)
    second.join(2)
    runner.close()

    assert current_error and isinstance(current_error[0], ActionCancelled)
    assert pending_error and isinstance(pending_error[0], ActionCancelled)


def test_submit_after_emergency_stop_can_run_again() -> None:
    runner = ActionRunner()
    runner.emergency_stop("test")

    result = runner.submit(lambda _cancel: "ok")
    runner.close()

    assert result == "ok"


def test_closed_runner_rejects_new_work() -> None:
    runner = ActionRunner()
    runner.close()

    with pytest.raises(ActionCancelled):
        runner.submit(lambda _cancel: "never")
