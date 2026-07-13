from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple
from backend.core.cos.kernel import KERNEL


def get_system_hmac_secret() -> bytes:
    """Retrieves or generates a persistent machine-local 32-byte secret key."""
    from backend.core.config import runtime_data_root
    secret_file = runtime_data_root() / "backend" / "data" / "governance" / ".hmac_secret"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    if secret_file.exists():
        return secret_file.read_bytes()
    import secrets
    new_secret = secrets.token_bytes(32)
    secret_file.write_bytes(new_secret)
    return new_secret


def serialize_canonical_token(token: Dict[str, Any]) -> bytes:
    """Serializes the core fields of a token in a sorted, canonical format for signing."""
    payload = {
        "token_id":        token["token_id"],
        "capabilities":    token["capabilities"],
        "trace_id":        token["trace_id"],
        "expires_at":      token["expires_at"],
        "max_invocations":  token["max_invocations"],
        "allowed_paths":    token["allowed_paths"],
        "allowed_domains":  token["allowed_domains"],
        "issued_by":        token["issued_by"],
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def mint_delegation_token(
    trace_id: str,
    capabilities: List[str],
    expires_in_minutes: int,
    max_invocations: int,
    allowed_paths: List[str],
    allowed_domains: List[str],
    issued_by: str = "user",
    private_key_hex: str | None = None,
) -> Dict[str, Any]:
    """Mints a cryptographically signed delegation token and persists it."""
    import warnings
    from backend.core.governance.identity_registry import IdentityRegistry

    if hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
        registry = IdentityRegistry(KERNEL.ledger)
        principal = registry.get(issued_by)
        if principal is None:
            principal = registry.resolve(issued_by)
        
        if principal is None:
            warnings.warn(f"Unknown issuer principal ID or name '{issued_by}'", UserWarning, stacklevel=2)
        elif not principal.is_effectively_active:
            raise PermissionError(f"Issuer principal '{issued_by}' is deactivated, suspended, revoked, or expired.")

    token_id = f"DTK-{str(uuid.uuid4())[:8].upper()}"
    expires_at = time.time() + (expires_in_minutes * 60)
    
    # Canonicalize paths
    canon_paths = []
    for p in allowed_paths:
        try:
            canon_paths.append(str(Path(p).expanduser().resolve()))
        except Exception:
            canon_paths.append(p)

    token = {
        "token_id": token_id,
        "capabilities": [c.upper().strip() for c in capabilities],
        "trace_id": trace_id,
        "expires_at": expires_at,
        "max_invocations": max_invocations,
        "current_invocations": 0,
        "allowed_paths": canon_paths,
        "allowed_domains": [d.lower().strip() for d in allowed_domains],
        "issued_by": issued_by,
        "status": "ACTIVE",
    }

    # Hashing payload
    payload_bytes = serialize_canonical_token(token)

    # Cryptographic signing
    if private_key_hex:
        # Asymmetric Ed25519
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            priv = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
            sig = priv.sign(payload_bytes)
            token["signature"] = sig.hex()
            token["signature_mode"] = "ed25519"
        except ImportError:
            raise RuntimeError("Ed25519 signing requested but cryptography library is not installed.")
    else:
        # Symmetric HMAC
        secret = get_system_hmac_secret()
        sig = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
        token["signature"] = sig
        token["signature_mode"] = "hmac"

    if hasattr(KERNEL, "ledger") and KERNEL.ledger is not None:
        KERNEL.ledger.create_delegation_token(token)

    return token


def validate_token_capability(
    token_id: str,
    capability: str,
    target: str | None = None,
) -> Tuple[bool, str]:
    """Validates delegation token cryptographic signatures, bounds, and path constraints."""
    if not hasattr(KERNEL, "ledger") or KERNEL.ledger is None:
        return False, "Ledger database is not initialized."

    token = KERNEL.ledger.get_delegation_token(token_id)
    if not token:
        return False, "Token not found."

    status = token["status"]
    if status != "ACTIVE":
        return False, f"Token status is {status}."

    # Validate issuer principal active status/expiry
    issued_by = token.get("issued_by")
    principal = None
    if issued_by:
        from backend.core.governance.identity_registry import IdentityRegistry
        registry = IdentityRegistry(KERNEL.ledger)
        principal = registry.get(issued_by)
        if principal is None:
            principal = registry.resolve(issued_by)
        if principal is not None:
            if not principal.is_effectively_active:
                return False, f"Issuer principal '{issued_by}' is deactivated, suspended, revoked, or expired."

    # Cryptographic Signature Verification
    signature = token.get("signature")
    if not signature:
        return False, "Token is missing a cryptographic signature."

    payload_bytes = serialize_canonical_token(token)
    sig_mode = token.get("signature_mode", "hmac")

    if sig_mode == "ed25519":
        # Verify Ed25519 signature using issuer public key
        if not principal or not principal.public_key:
            return False, f"Issuer '{issued_by}' does not have a registered public key for Ed25519 verification."
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            from cryptography.exceptions import InvalidSignature
            pub = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(principal.public_key))
            pub.verify(bytes.fromhex(signature), payload_bytes)
        except ImportError:
            return False, "Ed25519 signature verification is unavailable (cryptography module missing)."
        except InvalidSignature:
            return False, "Invalid cryptographic Ed25519 signature (token has been tampered with or is forged)."
        except Exception as e:
            return False, f"Error validating Ed25519 signature: {str(e)}"
    else:
        # Verify HMAC-SHA256 signature
        secret = get_system_hmac_secret()
        expected = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False, "Invalid cryptographic HMAC signature (token has been tampered with or is forged)."

    # Check expiration
    now = time.time()
    if now > token["expires_at"]:
        KERNEL.ledger.update_token_usage(token_id, token["current_invocations"], "EXPIRED")
        return False, "Token has expired."

    # Check invocation limits
    current_invocations = token["current_invocations"]
    max_invocations = token["max_invocations"]
    if current_invocations >= max_invocations:
        KERNEL.ledger.update_token_usage(token_id, current_invocations, "EXHAUSTED")
        return False, "Token invocation limit reached (exhausted)."

    # Check capability allowance
    cap_upper = capability.upper().strip()
    if cap_upper not in token["capabilities"]:
        return False, f"Capability {capability} is not allowed by this token."

    # Check target constraints if supplied
    if target:
        # If it's a file path capability, validate against allowed_paths
        if cap_upper in (
            "CAP_FILE_READ",
            "CAP_FILE_WRITE",
            "CAP_FILE_CREATE",
            "CAP_FILE_DELETE",
        ):
            try:
                target_path = Path(target).expanduser().resolve()
            except Exception:
                target_path = Path(target).absolute()
                
            allowed = False
            for allowed_p_str in token["allowed_paths"]:
                try:
                    allowed_path = Path(allowed_p_str).resolve()
                except Exception:
                    allowed_path = Path(allowed_p_str).absolute()
                
                # Check target is a subpath of or matches allowed_path
                if target_path == allowed_path or allowed_path in target_path.parents:
                    allowed = True
                    break
            if not allowed:
                return False, f"Path {target} resides outside allowed path constraints: {token['allowed_paths']}."

        # If it's a network request, validate against allowed_domains
        elif cap_upper in ("CAP_WEB_SEARCH", "CAP_WEB_DOWNLOAD", "CAP_TERMINAL_EXECUTE"):
            # Check domains
            target_lower = target.lower().strip()
            allowed = False
            for domain in token["allowed_domains"]:
                # Matches exact domain or subdomain (e.g. docs.python.org matching python.org)
                if target_lower == domain or target_lower.endswith("." + domain):
                    allowed = True
                    break
            if not allowed:
                return False, f"Target {target} is not in allowed domain constraints: {token['allowed_domains']}."

    # Valid token! Increment usage and check if exhausted
    new_invocations = current_invocations + 1
    new_status = "ACTIVE"
    if new_invocations >= max_invocations:
        new_status = "EXHAUSTED"

    KERNEL.ledger.update_token_usage(token_id, new_invocations, new_status)
    return True, "AUTHORIZED"

