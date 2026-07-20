"""Instance-scoped capability policy for the Action Runtime."""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping

from backend.core.action.models import Action


class Capability(str, Enum):
    """Capabilities currently enforced by canonical action executors."""

    FILE_WRITE = "file.write"
    SHELL_EXECUTE = "shell.execute"


DEFAULT_ACTION_CAPABILITIES: Mapping[tuple[str, str], Capability] = MappingProxyType(
    {
        ("file", "write"): Capability.FILE_WRITE,
        ("shell", "execute"): Capability.SHELL_EXECUTE,
    }
)


class CapabilityManager:
    """Authorize executor operations from an immutable injected grant set."""

    def __init__(
        self,
        granted: Iterable[Capability],
        action_capabilities: Mapping[tuple[str, str], Capability] | None = None,
    ) -> None:
        self._granted = frozenset(granted)
        self._action_capabilities = MappingProxyType(
            dict(action_capabilities or DEFAULT_ACTION_CAPABILITIES)
        )

    @classmethod
    def allowing(cls, *capabilities: Capability) -> CapabilityManager:
        """Build an explicit allow policy for a composition root."""

        return cls(capabilities)

    @classmethod
    def deny_all(cls) -> CapabilityManager:
        """Build a fail-closed policy with no grants."""

        return cls(())

    def required_capability(self, action: Action) -> Capability | None:
        """Return the declared capability for an action, if one exists."""

        return self._action_capabilities.get((action.executor, action.operation))

    def is_allowed(self, action: Action) -> bool:
        """Deny unknown operations and return whether the required grant exists."""

        required = self.required_capability(action)
        return required is not None and required in self._granted
