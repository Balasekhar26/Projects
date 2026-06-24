import time
import uuid
from typing import Dict, Set
from dataclasses import dataclass

@dataclass
class CapabilityToken:
    token_id: str
    action: str
    session_id: str
    taint: str  # "SAFE", "UNTRUSTED", "PRIVATE"
    expires_at: float
    status: str = "ACTIVE"  # "ACTIVE", "REVOKED", "EXPIRED", "CONSUMED"

class CapabilityBroker:
    # Loaded dynamically from security_config.yaml
    EGRESS_ACTIONS: Set[str] = None

    _active_tokens: Dict[str, CapabilityToken] = {}

    @classmethod
    def get_session_taint_label(cls, db_conn, session_id: str) -> str:
        """
        Retrieves the session's taint status from the database.
        Taint levels >= 4 map to 'PRIVATE'.
        Taint levels == 3 map to 'UNTRUSTED'.
        """
        if not db_conn:
            return "SAFE"
        try:
            cursor = db_conn.cursor()
            cursor.execute("SELECT taint_level FROM security_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                taint_level = row[0]
                if taint_level >= 4:
                    return "PRIVATE"
                elif taint_level == 3:
                    return "UNTRUSTED"
            return "SAFE"
        except Exception:
            return "SAFE"

    @classmethod
    def mint_token(cls, session_id: str, action: str, taint: str, ttl_seconds: float = 60.0) -> CapabilityToken:
        """
        Mints a short-lived capability token carrying the session's taint.
        """
        token_id = f"CAP-{action.upper()}-{str(uuid.uuid4())[:8].upper()}"
        expires_at = time.time() + ttl_seconds
        token = CapabilityToken(
            token_id=token_id,
            action=action.upper(),
            session_id=session_id,
            taint=taint,
            expires_at=expires_at,
            status="ACTIVE"
        )
        cls._active_tokens[token_id] = token
        return token

    @classmethod
    def revoke_token(cls, token_id: str) -> None:
        """
        Revokes a specific capability token.
        """
        token = cls._active_tokens.get(token_id)
        if token:
            token.status = "REVOKED"

    @classmethod
    def revoke_all_tokens(cls) -> None:
        """
        Revokes all active capability tokens.
        """
        for token in cls._active_tokens.values():
            token.status = "REVOKED"

    @classmethod
    def validate_token(cls, token_id: str, action: str) -> bool:
        """
        Validates the capability token.
        Enforces that a token tainted with 'PRIVATE' cannot execute egress actions.
        """
        token = cls._active_tokens.get(token_id)
        if not token:
            return False

        if token.status != "ACTIVE":
            return False

        # Expiration Check
        if time.time() > token.expires_at:
            token.status = "EXPIRED"
            cls._active_tokens.pop(token_id, None)
            return False

        # Action Check
        if token.action != action.upper():
            return False

        # Taint Composition Rule
        if cls.EGRESS_ACTIONS is None:
            from backend.core.config import load_security_config
            sec_config = load_security_config()
            cls.EGRESS_ACTIONS = set(sec_config.get("egress_actions") or [
                "SEND_EMAIL", "NETWORK_REQUEST", "BROWSER_FILL_FORM",
                "BROWSER_CLICK_SUBMIT", "BROWSER_LOGIN", "GIT_PUSH", "DEPLOY"
            ])

        # If the token has a 'PRIVATE' taint, egress actions are strictly prohibited.
        if token.taint == "PRIVATE" and action.upper() in cls.EGRESS_ACTIONS:
            return False

        # Consume token (single-use)
        token.status = "CONSUMED"
        cls._active_tokens.pop(token_id, None)
        return True
