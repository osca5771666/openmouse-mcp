from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable, TypeVar

from .errors import ActionCancelled


T = TypeVar("T")


@dataclass
class _Job:
    operation: Callable[[threading.Event], T]
    future: Future[T]
    generation: int


class ActionRunner:
    """Serial action queue with an emergency stop that drains pending work."""

    def __init__(self) -> None:
        self._queue: queue.Queue[_Job | None] = queue.Queue()
        self._lock = threading.Lock()
        self._generation = 0
        self._current_cancel: threading.Event | None = None
        self._closed = False
        self._thread = threading.Thread(
            target=self._worker,
            name="openmouse-action-runner",
            daemon=True,
        )
        self._thread.start()

    def submit(self, operation: Callable[[threading.Event], T]) -> T:
        with self._lock:
            if self._closed:
                raise ActionCancelled("Mouse action runner is closed.")
            generation = self._generation
        future: Future[T] = Future()
        self._queue.put(_Job(operation=operation, future=future, generation=generation))
        return future.result()

    def emergency_stop(self, reason: str = "emergency_stop") -> None:
        with self._lock:
            self._generation += 1
            if self._current_cancel is not None:
                self._current_cancel.set()
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            if job is None:
                continue
            if not job.future.done():
                job.future.set_exception(ActionCancelled(f"Mouse action cancelled: {reason}."))
            self._queue.task_done()

    def close(self) -> None:
        self.emergency_stop("runner_closed")
        with self._lock:
            self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=2)

    def _worker(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                self._queue.task_done()
                return
            try:
                with self._lock:
                    stale = job.generation != self._generation or self._closed
                    cancel = threading.Event()
                    if not stale:
                        self._current_cancel = cancel
                if stale:
                    raise ActionCancelled("Mouse action cancelled before execution.")
                result = job.operation(cancel)
                if cancel.is_set():
                    raise ActionCancelled("Mouse action cancelled.")
                if not job.future.done():
                    job.future.set_result(result)
            except BaseException as exc:  # The Future owns the tool-facing error.
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                with self._lock:
                    self._current_cancel = None
                self._queue.task_done()
