# K21-12: Domain Interfaces & Contracts

This document formalizes the public interfaces and communication signatures for the World Model components.

---

## 1. WorldModelCoordinator Interface

The Coordinator is the sole manager of domain worlds. It exposes the following public API signatures:

```python
class WorldModelCoordinator:
    """Central interface routing operations and managing simulation branches."""

    @classmethod
    def get_entity(cls, domain: str, entity_id: str, branch_id: Optional[str] = None) -> Optional[Entity]:
        """Retrieve an entity by ID from a specific domain and branch."""
        pass

    @classmethod
    def publish_observation(cls, domain: str, observation: Dict[str, Any]) -> str:
        """Publish a raw observation, generating a change event and updating belief states."""
        pass

    @classmethod
    def create_branch(cls, parent_branch_id: Optional[str] = None) -> str:
        """Create a new delta-based simulation branch and return its UUID."""
        pass

    @classmethod
    def simulate_step(cls, branch_id: str, action: Dict[str, Any]) -> TransitionResult:
        """Execute a forward step inside a simulation branch, returning predicted outcomes."""
        pass

    @classmethod
    def merge_branch(cls, branch_id: str) -> bool:
        """Merge simulation delta adjustments back into the Main World state."""
        pass
```

---

## 2. Cognitive Domain Interface

Each of the 6 domains (Physical, Digital, Human, Self, Temporal, Economic) implements this common interface contract:

```python
class CognitiveDomain(ABC):
    """Abstract base class representing a localized domain world."""

    @abstractmethod
    def retrieve_entity(self, entity_id: str, deltas: Dict[str, Any]) -> Optional[Entity]:
        """Resolves property value inheritance using parent states and deltas."""
        pass

    @abstractmethod
    def evaluate_transition(self, entity: Entity, event: Event) -> Dict[str, Any]:
        """Applies causal laws to evaluate state transitions."""
        pass
```
- **Interface Version**: `v1.0.0`
- **Ownership**: `Program C: World Models`
- **Verification Rule**: Changing these signatures requires updating `adr_index.md` and running all regression tests.
