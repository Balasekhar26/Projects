"""Tool Timeout Manager (Program 11).

Interupts callables execution when they run past timeout thresholds.
"""
from __future__ import annotations

import threading
from typing import Any, Callable


class TimeoutManager:
    """Invokes callables in separate thread workers, raising TimeoutError on duration overflow."""

    @staticmethod
    def run_with_timeout(func: Callable[..., Any], timeout_seconds: float, **kwargs: Any) -> Any:
        """Runs the target function inside a thread and joins it with timeout bounds."""
        res_container = []
        err_container = []

        def worker():
            try:
                val = func(**kwargs)
                res_container.append(val)
            except Exception as exc:
                err_container.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            # Thread is still running past timeout
            raise TimeoutError(f"Function execution timed out after {timeout_seconds}s")

        if err_container:
            raise err_container[0]

        return res_container[0] if res_container else None
