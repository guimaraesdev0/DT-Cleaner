"""Cancellation and throttling helpers.

The scanner runs off the UI thread, so two things are needed: a way to stop it
promptly when the user presses ESC, and a way to stop it from flooding the UI
with thousands of updates per second.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class CancelToken:
    """A cooperative cancellation flag shared between UI and worker threads.

    Cooperative on purpose: killing a thread mid-delete could leave a tree half
    removed. Workers check `cancelled` at safe points instead.
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise ScanCancelled()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


class ScanCancelled(Exception):
    """Raised inside a worker when the user cancels. Always caught by the caller."""


class Throttle:
    """Rate-limits callbacks so the UI stays responsive during a fast scan.

    Without this, scanning a large drive would push tens of thousands of
    progress updates per second and the terminal would spend all its time
    repainting instead of scanning.
    """

    __slots__ = ("_interval", "_last", "_lock")

    def __init__(self, interval: float = 0.08) -> None:
        self._interval = interval
        self._last = 0.0
        self._lock = threading.Lock()

    def ready(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._last >= self._interval:
                self._last = now
                return True
        return False

    def call(self, fn: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> None:
        """Invoke `fn` only if the interval has elapsed. Never raises."""
        if fn is None or not self.ready():
            return
        try:
            fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - a broken callback must not kill the scan
            pass

    def force(self, fn: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> None:
        """Invoke `fn` regardless of the interval (for phase changes and finals)."""
        if fn is None:
            return
        with self._lock:
            self._last = time.monotonic()
        try:
            fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            pass
