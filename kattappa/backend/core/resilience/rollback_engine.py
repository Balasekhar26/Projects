class RollbackEngine:
    @classmethod
    def rollback_state(cls, checkpoint_state: dict) -> dict:
        """Reverts active state changes back to a secure saved checkpoint."""
        return dict(checkpoint_state)
