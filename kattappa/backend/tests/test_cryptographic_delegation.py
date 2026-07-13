import pytest
import time
import hmac
import hashlib
import json
from unittest.mock import MagicMock, patch

from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
from backend.core.ledger.stores.memory_store import MemoryLedgerStore
from backend.core.governance.identity_registry import IdentityRegistry
from backend.core.governance.delegation_token_manager import (
    mint_delegation_token,
    validate_token_capability,
    get_system_hmac_secret,
)
from backend.core.cos.kernel import KERNEL

@pytest.fixture(params=["sqlite", "memory"])
def store(request):
    if request.param == "sqlite":
        return SQLiteLedgerStore(":memory:")
    return MemoryLedgerStore()


def test_hmac_token_verification_success(store):
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="issuer-agent", principal_type="AGENT")

        # Mint symmetric HMAC token
        token = mint_delegation_token(
            trace_id="t_hmac",
            capabilities=["CAP_FILE_READ"],
            expires_in_minutes=10,
            max_invocations=3,
            allowed_paths=["/tmp"],
            allowed_domains=["google.com"],
            issued_by=p.principal_id,
        )

        assert token["signature"] is not None
        assert token["signature_mode"] == "hmac"

        # Validate successfully
        valid, msg = validate_token_capability(token["token_id"], "CAP_FILE_READ", "/tmp/file.txt")
        assert valid is True
        assert msg == "AUTHORIZED"
    finally:
        KERNEL.ledger = old_ledger


def test_hmac_token_tampering(store):
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        registry = IdentityRegistry(store)
        p = registry.register(name="issuer-agent", principal_type="AGENT")

        # Mint symmetric HMAC token
        token = mint_delegation_token(
            trace_id="t_hmac",
            capabilities=["CAP_FILE_READ"],
            expires_in_minutes=10,
            max_invocations=3,
            allowed_paths=["/tmp"],
            allowed_domains=[],
            issued_by=p.principal_id,
        )

        # 1. Modify capabilities inside the DB directly to simulate tampering
        if isinstance(store, SQLiteLedgerStore):
            conn = store._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE delegation_tokens SET capabilities = '[\"CAP_FILE_READ\", \"CAP_TERMINAL_EXECUTE\"]' WHERE token_id = ?",
                (token["token_id"],),
            )
            conn.commit()
            store._close_connection(conn)
        else:
            # Modify memory store record directly in the list
            for t in store._tokens:
                if t["token_id"] == token["token_id"]:
                    t["capabilities"] = ["CAP_FILE_READ", "CAP_TERMINAL_EXECUTE"]
                    break

        # Validate should detect the tampering and fail
        valid, msg = validate_token_capability(token["token_id"], "CAP_TERMINAL_EXECUTE")
        assert valid is False
        assert "tampered with" in msg or "signature" in msg
    finally:
        KERNEL.ledger = old_ledger


def test_ed25519_token_verification_fallback_or_mock(store):
    """Verifies the Ed25519 validation flow works, dynamically mocking cryptography if missing."""
    old_ledger = KERNEL.ledger
    KERNEL.ledger = store
    try:
        # Register a principal with a public key
        registry = IdentityRegistry(store)
        dummy_pubkey = "a" * 64  # Hex representation of 32 bytes
        p = registry.register(
            name="issuer-asymmetric",
            principal_type="AGENT",
            public_key=dummy_pubkey,
        )

        # Since cryptography isn't installed, mint_delegation_token will raise RuntimeError
        # when private_key_hex is provided.
        with pytest.raises(RuntimeError, match="cryptography library is not installed"):
            mint_delegation_token(
                trace_id="t_ed",
                capabilities=["CAP_FILE_READ"],
                expires_in_minutes=10,
                max_invocations=3,
                allowed_paths=["/tmp"],
                allowed_domains=[],
                issued_by=p.principal_id,
                private_key_hex="b" * 64,  # Dummy private key
            )

        # Now let's mock cryptography package to test the validation pathway
        mock_crypto = MagicMock()
        mock_hazmat = MagicMock()
        mock_primitives = MagicMock()
        mock_asymmetric = MagicMock()
        mock_ed25519 = MagicMock()
        mock_exceptions = MagicMock()

        # Wire up nested imports
        mock_crypto.hazmat = mock_hazmat
        mock_hazmat.primitives = mock_primitives
        mock_primitives.asymmetric = mock_asymmetric
        mock_asymmetric.ed25519 = mock_ed25519
        mock_crypto.exceptions = mock_exceptions

        # Let's insert a mocked token with ed25519 signature mode manually into the store
        token = {
            "token_id": "DTK-ED25519",
            "capabilities": ["CAP_FILE_READ"],
            "trace_id": "t_ed",
            "expires_at": time.time() + 600,
            "max_invocations": 3,
            "current_invocations": 0,
            "allowed_paths": ["/tmp"],
            "allowed_domains": [],
            "issued_by": p.principal_id,
            "status": "ACTIVE",
            "signature": "c" * 128,  # Hex signature of 64 bytes
            "signature_mode": "ed25519",
        }
        store.create_delegation_token(token)

        mock_public_key = MagicMock()
        mock_ed25519.Ed25519PublicKey.from_public_bytes.return_value = mock_public_key

        # Patch the entire cryptography hierarchy in sys.modules to prevent circular loading issues
        with patch.dict("sys.modules", {
            "cryptography": mock_crypto,
            "cryptography.hazmat": mock_hazmat,
            "cryptography.hazmat.primitives": mock_primitives,
            "cryptography.hazmat.primitives.asymmetric": mock_asymmetric,
            "cryptography.hazmat.primitives.asymmetric.ed25519": mock_ed25519,
            "cryptography.exceptions": mock_exceptions,
        }):
            valid, msg = validate_token_capability(token["token_id"], "CAP_FILE_READ", "/tmp/file.txt")
            
            # verify method is called
            assert mock_ed25519.Ed25519PublicKey.from_public_bytes.called
            assert mock_public_key.verify.called
            assert valid is True

        # Assert validation fails if public_key.verify raises InvalidSignature
        class MockInvalidSignature(Exception):
            pass

        mock_public_key.verify.side_effect = MockInvalidSignature("Invalid signature")
        mock_exceptions.InvalidSignature = MockInvalidSignature

        with patch.dict("sys.modules", {
            "cryptography": mock_crypto,
            "cryptography.hazmat": mock_hazmat,
            "cryptography.hazmat.primitives": mock_primitives,
            "cryptography.hazmat.primitives.asymmetric": mock_asymmetric,
            "cryptography.hazmat.primitives.asymmetric.ed25519": mock_ed25519,
            "cryptography.exceptions": mock_exceptions,
        }):
            valid, msg = validate_token_capability(token["token_id"], "CAP_FILE_READ", "/tmp/file.txt")
            assert valid is False
            assert "tampered with" in msg or "Invalid signature" in msg

    finally:
        KERNEL.ledger = old_ledger
