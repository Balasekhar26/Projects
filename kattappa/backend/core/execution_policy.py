"""Execution Policy Engine (Phase 3.5).

The final, deterministic guardrail between thinking and acting. No agent — and
no Execution Engine — may run an action until the policy engine answers:

    "Can this action legally execute right now?"

Every action type maps to one of three outcomes:

* ``AUTO_EXECUTE``   - safe, read-only-ish actions may run without a human
* ``REQUIRE_HUMAN``  - the action needs explicit human approval first
* ``BLOCKED``        - never permitted automatically

Two safety invariants:

* **Deny by default** - an unknown action requires human approval, never auto.
* **Consensus gate** - even an AUTO_EXECUTE action only runs if Consensus v2
  approved it and did not itself demand human approval; this carries forward the
  "no automatic code changes" guarantee.

The engine decides; it never executes. There is intentionally no
apply/run/execute method here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class PolicyOutcome(str, Enum):
    AUTO_EXECUTE = "auto_execute"
    REQUIRE_HUMAN = "require_human"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionPolicy:
    action: str
    auto_execute: bool = False
    require_human: bool = True
    blocked: bool = False
    description: str = ""

    @property
    def outcome(self) -> PolicyOutcome:
        if self.blocked:
            return PolicyOutcome.BLOCKED
        if self.auto_execute and not self.require_human:
            return PolicyOutcome.AUTO_EXECUTE
        return PolicyOutcome.REQUIRE_HUMAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "auto_execute": self.auto_execute,
            "require_human": self.require_human,
            "blocked": self.blocked,
            "outcome": self.outcome.value,
            "description": self.description,
        }


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    outcome: PolicyOutcome
    matched: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "outcome": self.outcome.value,
            "matched": self.matched,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ExecutionGate:
    action: str
    outcome: PolicyOutcome
    consensus_approved: bool
    requires_human: bool
    blocked: bool
    reason: str

    @property
    def can_auto_execute(self) -> bool:
        return (
            self.outcome is PolicyOutcome.AUTO_EXECUTE
            and self.consensus_approved
            and not self.requires_human
            and not self.blocked
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "outcome": self.outcome.value,
            "consensus_approved": self.consensus_approved,
            "requires_human": self.requires_human,
            "blocked": self.blocked,
            "can_auto_execute": self.can_auto_execute,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Default policy table
# ---------------------------------------------------------------------------

def _auto(action: str, desc: str = "") -> ActionPolicy:
    return ActionPolicy(action, auto_execute=True, require_human=False, description=desc)


def _human(action: str, desc: str = "") -> ActionPolicy:
    return ActionPolicy(action, auto_execute=False, require_human=True, description=desc)


def _blocked(action: str, desc: str = "") -> ActionPolicy:
    return ActionPolicy(action, blocked=True, require_human=True, description=desc)


_DEFAULT_LIST = [
    # Safe, read-only-ish.
    _auto("READ_FILE", "Read a file"),
    _auto("LIST_DIR", "List a directory"),
    _auto("SEARCH_MEMORY", "Search memory"),
    _auto("RECALL_MEMORY", "Recall a memory"),
    _auto("GET_STATUS", "Read system status"),
    # Mutating -> human approval (preserves 'no automatic code changes').
    _human("CREATE_FILE", "Create a new file"),
    _human("WRITE_FILE", "Write/overwrite a file"),
    _human("EDIT_FILE", "Edit a file"),
    _human("DELETE_FILE", "Delete a file"),
    _human("MOVE_FILE", "Move/rename a file"),
    _human("GIT_COMMIT", "Commit to git"),
    _human("GIT_PUSH", "Push to a remote"),
    _human("RUN_SHELL", "Run a shell command"),
    _human("DEPLOY", "Deploy to an environment"),
    _human("INSTALL_PACKAGE", "Install a dependency"),
    _human("NETWORK_REQUEST", "Make an outbound network request"),
    _human("SEND_EMAIL", "Send an email"),
    _human("DESKTOP_CONTROL", "Control mouse/keyboard"),
    _human("COMMIT_MEMORY_DELTA", "Commit a memory delta to long-term memory"),
    # Desktop policies (V3 Hardened)
    _auto("DESKTOP_READ_SCREEN", "Read screen text or elements"),
    _auto("DESKTOP_SCREENSHOT", "Take a screenshot"),
    _auto("DESKTOP_OPEN_APP", "Open approved desktop application"),
    _auto("DESKTOP_MOUSE_MOVE", "Move cursor"),
    _auto("DESKTOP_MOUSE_CLICK", "Click validated UI targets"),
    _auto("DESKTOP_KEYBOARD_TYPING", "Type text or shortcuts"),
    _auto("DESKTOP_CLOSE_APP", "Close active application"),
    _auto("DESKTOP_KILL_PROCESS", "Kill process"),
    _human("DESKTOP_DELETE_FILE", "Delete a file via desktop"),
    _human("DESKTOP_SHUTDOWN", "Shutdown system"),
    _human("DESKTOP_SETTINGS", "Modify system settings"),
    # Code policies
    _auto("RUN_TESTS", "Run tests"),
    _auto("RUN_BENCHMARKS", "Run benchmarks"),
    _auto("ANALYZE_CODE", "Analyze code"),
    _auto("GENERATE_CODE", "Generate code"),
    _human("PATCH_CODE", "Patch code"),
    _auto("CREATE_PROPOSAL", "Create proposal"),
    _auto("ANALYZE_REPO", "Analyze repo codebase"),
    # Voice policies (Auto Approved)
    _auto("VOICE_MICROPHONE_READ", "Capture audio stream from local microphone"),
    _auto("VOICE_SPEAKER_OUTPUT", "Play synthesized speech audio output"),
    _auto("VOICE_STT", "Transcribe raw speech audio into text"),
    _auto("VOICE_TTS", "Synthesize text into speech audio"),
    _auto("VOICE_WAKE_WORD_DETECTION", "Locally detect wake words"),
    # Never automatic.
    _blocked("FORMAT_DRIVE", "Format a disk"),
    _blocked("DISABLE_SECURITY", "Disable security controls"),
    _blocked("TRANSFER_MONEY", "Transfer money / make a payment"),
    _blocked("EXFILTRATE_DATA", "Send private data off-device"),
]

DEFAULT_POLICIES: dict[str, ActionPolicy] = {p.action: p for p in _DEFAULT_LIST}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """Deterministic action-policy gate. Decides; never executes."""

    def __init__(self, policies: Mapping[str, ActionPolicy] | None = None) -> None:
        self._policies: dict[str, ActionPolicy] = dict(policies or DEFAULT_POLICIES)

    @staticmethod
    def _key(action: str) -> str:
        return action.strip().upper()

    def register(self, policy: ActionPolicy) -> None:
        self._policies[self._key(policy.action)] = policy

    def get(self, action: str) -> ActionPolicy | None:
        return self._policies.get(self._key(action))

    def policies(self) -> list[ActionPolicy]:
        return sorted(self._policies.values(), key=lambda p: p.action)

    def evaluate(self, action: str, agent_name: str | None = None) -> PolicyDecision:
        policy = self.get(action)
        if policy is None:
            # Deny by default: unknown actions need a human.
            return PolicyDecision(
                self._key(action), PolicyOutcome.REQUIRE_HUMAN, matched=False,
                reason="unknown action -> human approval required (deny by default)",
            )
            
        # If agent_name is provided, check capability registry
        if agent_name:
            from backend.core.capability_registry import ACTION_CAPABILITY_MAP, CapabilityRegistry
            required_cap = ACTION_CAPABILITY_MAP.get(action.upper())
            if required_cap:
                if not CapabilityRegistry.is_capability_allowed(agent_name, required_cap):
                    return PolicyDecision(
                        self._key(action), PolicyOutcome.BLOCKED, matched=True,
                        reason=f"agent '{agent_name}' lacks required capability '{required_cap}' for action '{action}'",
                    )
            
        reason = {
            PolicyOutcome.AUTO_EXECUTE: "policy permits automatic execution",
            PolicyOutcome.REQUIRE_HUMAN: "policy requires human approval",
            PolicyOutcome.BLOCKED: "policy blocks this action",
        }[policy.outcome]
        return PolicyDecision(self._key(action), policy.outcome, matched=True, reason=reason)

    def gate(
        self,
        action: str,
        *,
        consensus_approved: bool = True,
        consensus_requires_human: bool = False,
    ) -> ExecutionGate:
        """Combine the action policy with the consensus outcome."""
        decision = self.evaluate(action)
        blocked = decision.outcome is PolicyOutcome.BLOCKED
        reasons = [decision.reason]

        if blocked:
            requires_human = False  # blocked entirely; a human cannot wave it through here
        elif (
            decision.outcome is PolicyOutcome.AUTO_EXECUTE
            and consensus_approved
            and not consensus_requires_human
        ):
            requires_human = False
        else:
            requires_human = True
            if not consensus_approved:
                reasons.append("consensus did not approve")
            elif consensus_requires_human:
                reasons.append("consensus requires human approval")

        return ExecutionGate(
            action=self._key(action),
            outcome=decision.outcome,
            consensus_approved=consensus_approved,
            requires_human=requires_human,
            blocked=blocked,
            reason="; ".join(reasons),
        )

    def gate_with_consensus(self, action: str, consensus_decision: Any) -> ExecutionGate:
        """Convenience: derive the consensus flags from a ConsensusDecision."""
        from backend.core.consensus_engine import ConsensusStatus

        approved = getattr(consensus_decision, "status", None) is ConsensusStatus.APPROVED
        human = bool(getattr(consensus_decision, "requires_human_approval", True))
        return self.gate(action, consensus_approved=approved, consensus_requires_human=human)

    def to_dict(self) -> dict[str, Any]:
        return {"policies": [p.to_dict() for p in self.policies()]}


def load_policies(raw: Mapping[str, Mapping[str, Any]]) -> PolicyEngine:
    """Build an engine from a plain mapping (e.g. parsed YAML)."""
    policies: dict[str, ActionPolicy] = dict(DEFAULT_POLICIES)
    for action, spec in raw.items():
        key = action.strip().upper()
        policies[key] = ActionPolicy(
            action=key,
            auto_execute=bool(spec.get("auto_execute", False)),
            require_human=bool(spec.get("require_human", not spec.get("auto_execute", False))),
            blocked=bool(spec.get("blocked", False)),
            description=str(spec.get("description", "")),
        )
    return PolicyEngine(policies)


# Module-level shared engine over the default policy table.
DEFAULT_POLICY_ENGINE = PolicyEngine()
