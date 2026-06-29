# K21-24: Interface Contracts (Final Freeze)

This document formalizes the public APIs, versioning strategies, and extension points for the World Model.

---

## 1. Frozen API Signatures

### 1.1. WorldModelCoordinator API (`v1.0.0`)
```python
class WorldModelCoordinator:

    @classmethod
    def get_entity(cls, domain: str, entity_id: str, branch_id: Optional[str] = None) -> Optional[Entity]:
        """Retrieve Entity from specified domain/branch. Thread-safe."""
        pass

    @classmethod
    def create_branch(cls, parent_branch_id: Optional[str] = None) -> str:
        """Create new delta-based branch. Returns branch UUID."""
        pass

    @classmethod
    def simulate_action(cls, branch_id: str, action: Dict[str, Any]) -> TransitionResult:
        """Run simulated transition step on branch. Returns TransitionResult."""
        pass

    @classmethod
    def propose_merge(cls, branch_id: str) -> List[str]:
        """Generate candidate events from branch deltas. Returns proposed event IDs."""
        pass
```

---

## 2. Versioning & Backward Compatibility

- **Semantic Versioning**: API contracts utilize `MAJOR.MINOR.PATCH`. Major versions require an approved ADR.
- **Delta Compatibility**: Delta log keys must remain backward compatible with properties schemas. If a schema property is deprecated, it is marked `deprecated=True` rather than deleted, avoiding deserialization errors on historical snapshots.
