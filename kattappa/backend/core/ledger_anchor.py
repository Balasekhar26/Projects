import os
from pathlib import Path

class LedgerAnchor:
    # Anchor file is stored in user home directory under a hidden filename
    ANCHOR_PATH = Path("~/.kattappa_ledger_head").expanduser().resolve()

    @classmethod
    def write_anchor(cls, ledger_hash: str) -> None:
        """
        Updates the external ledger head anchor with the latest ledger hash.
        """
        try:
            # Create directory if needed
            cls.ANCHOR_PATH.parent.mkdir(parents=True, exist_ok=True)
            cls.ANCHOR_PATH.write_text(ledger_hash.strip(), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def read_anchor(cls) -> str:
        """
        Reads the anchored ledger head hash.
        Returns 'GENESIS' if the anchor file does not exist yet.
        """
        try:
            if cls.ANCHOR_PATH.exists():
                return cls.ANCHOR_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return "GENESIS"
