from __future__ import annotations

from enum import Enum, IntEnum
from typing import Dict, Tuple


class TrustZone(Enum):
    ZONE_INTERNAL = "ZONE_INTERNAL"
    ZONE_LOCAL_MACHINE = "ZONE_LOCAL_MACHINE"
    ZONE_HOME_NETWORK = "ZONE_HOME_NETWORK"
    ZONE_CLOUD = "ZONE_CLOUD"
    ZONE_PUBLIC_INTERNET = "ZONE_PUBLIC_INTERNET"
    ZONE_PHYSICAL_WORLD = "ZONE_PHYSICAL_WORLD"


class AuthorizationLevel(IntEnum):
    L0 = 0  # Internal reasoning only
    L1 = 1  # Read-only actions
    L2 = 2  # Local modifications
    L3 = 3  # External communications
    L4 = 4  # Financial actions / Deletion
    L5 = 5  # Physical-world actions / Dangerous


# Declarative mapping of capability constants to TrustZone, AuthorizationLevel, and default ApprovalPolicy
# Policies: "auto" (immediate allow), "once" (requires approval once per trace/session), "session" (requires approval once per session), "always" (always prompts)
CAPABILITY_POLICIES: Dict[str, Tuple[TrustZone, AuthorizationLevel, str]] = {
    # File capabilities
    "CAP_FILE_READ": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_FILE_CREATE": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L2, "once"),
    "CAP_FILE_WRITE": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L2, "once"),
    "CAP_FILE_DELETE": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L4, "always"),
    
    # Internal reasoning / memory
    "CAP_SCREEN_READ": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L1, "auto"),
    "CAP_SCREENSHOT": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_MOUSE_MOVE": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_KEYBOARD_INPUT": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L2, "once"),
    
    # Memory capabilities
    "CAP_MEMORY_READ": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L1, "auto"),
    "CAP_MEMORY_WRITE": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L2, "auto"),
    "CAP_MEMORY_PIN": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L2, "auto"),
    "CAP_MEMORY_DELETE": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L4, "always"),
    "CAP_MEMORY_ROLLBACK": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L3, "once"),

    # Code / execution
    "CAP_TEST_EXECUTE": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L2, "auto"),
    "CAP_BENCHMARK_EXECUTE": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L2, "auto"),
    "CAP_CODE_ANALYZE": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L0, "auto"),
    "CAP_CODE_GENERATE": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L0, "auto"),
    "CAP_CODE_PATCH": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L2, "once"),
    "CAP_TERMINAL_EXECUTE": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L3, "always"),
    "CAP_PROPOSAL_CREATE": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L1, "auto"),

    # Network / Web
    "CAP_WEB_SEARCH": (TrustZone.ZONE_PUBLIC_INTERNET, AuthorizationLevel.L1, "session"),
    "CAP_WEB_DOWNLOAD": (TrustZone.ZONE_PUBLIC_INTERNET, AuthorizationLevel.L2, "always"),

    # Voice capabilities
    "CAP_MICROPHONE_READ": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "always"),
    "CAP_SPEAKER_OUTPUT": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_STT": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L1, "auto"),
    "CAP_TTS": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L1, "auto"),
    "CAP_WAKE_WORD_DETECTION": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L0, "auto"),

    # Monitoring capabilities
    "CAP_MONITOR_CPU": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_MONITOR_RAM": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_MONITOR_GPU": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_MONITOR_STORAGE": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_MONITOR_NETWORK": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),
    "CAP_MONITOR_TEMP": (TrustZone.ZONE_LOCAL_MACHINE, AuthorizationLevel.L1, "auto"),

    # Executive capabilities
    "CAP_GOAL_MANAGE": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L1, "auto"),
    "CAP_GOAL_SCHEDULE": (TrustZone.ZONE_INTERNAL, AuthorizationLevel.L2, "once"),
}


def get_capability_policy(capability: str) -> Tuple[TrustZone, AuthorizationLevel, str]:
    """Retrieves the TrustZone, AuthorizationLevel, and ApprovalPolicy for a given capability."""
    cap_upper = str(capability).upper().strip()
    return CAPABILITY_POLICIES.get(
        cap_upper,
        (TrustZone.ZONE_PHYSICAL_WORLD, AuthorizationLevel.L5, "always"),  # Strict fail-safe fallback
    )
