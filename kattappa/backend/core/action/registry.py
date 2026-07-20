"""Executor registry used to decouple planning from action implementations."""

from __future__ import annotations

from threading import RLock

from backend.core.action.interfaces import ActionExecutorProtocol


class ExecutorRegistryError(LookupError):
    """Base error for invalid executor registry operations."""


class ExecutorAlreadyRegisteredError(ExecutorRegistryError):
    """Raised when a name is registered twice without explicit replacement."""


class ExecutorNotFoundError(ExecutorRegistryError):
    """Raised when an action references an unknown executor."""


class ExecutorRegistry:
    """Thread-safe, instance-scoped map of names to injected executors."""

    def __init__(self) -> None:
        self._executors: dict[str, ActionExecutorProtocol] = {}
        self._lock = RLock()

    def register(
        self,
        name: str,
        executor: ActionExecutorProtocol,
        *,
        replace: bool = False,
    ) -> None:
        """Register an executor, rejecting accidental duplicate names."""

        normalized_name = self._normalize_name(name)
        if not callable(getattr(executor, "execute", None)):
            raise TypeError("executor must provide an execute(action) method")

        with self._lock:
            if normalized_name in self._executors and not replace:
                raise ExecutorAlreadyRegisteredError(
                    f"executor '{normalized_name}' is already registered"
                )
            self._executors[normalized_name] = executor

    def resolve(self, name: str) -> ActionExecutorProtocol:
        """Resolve an executor by normalized name or raise a typed error."""

        normalized_name = self._normalize_name(name)
        with self._lock:
            try:
                return self._executors[normalized_name]
            except KeyError as exc:
                raise ExecutorNotFoundError(
                    f"executor '{normalized_name}' is not registered"
                ) from exc

    def unregister(self, name: str) -> None:
        """Remove a registered executor or raise when it is absent."""

        normalized_name = self._normalize_name(name)
        with self._lock:
            if normalized_name not in self._executors:
                raise ExecutorNotFoundError(
                    f"executor '{normalized_name}' is not registered"
                )
            del self._executors[normalized_name]

    def registered_names(self) -> tuple[str, ...]:
        """Return a stable snapshot of registered executor names."""

        with self._lock:
            return tuple(sorted(self._executors))

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized_name = name.strip().casefold()
        if not normalized_name:
            raise ValueError("executor name must not be empty")
        return normalized_name
