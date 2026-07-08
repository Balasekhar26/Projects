# K21-25: World Registry Specification

This document details the transition from a single-world model to a dynamic World Registry supporting multiple concurrent worlds.

---

## 1. Registry Architecture

The `WorldModelCoordinator` manages a **World Registry** allowing creation, deletion, and query routing across multiple distinct worlds:

```
                  WorldModelCoordinator (Registry Gateway)
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
   Main World (Active)     Robot Sandbox         User Mental Model
```

---

## 2. World Model Contexts

Supported World Types in the registry:
1. **Active Real World**: Maps current physical/digital operating state.
2. **Scientific Sandbox**: Isolated workspace for running hypothesis validations.
3. **User Mental Model**: The agent's estimate of the user's beliefs and constraints (Theory of Mind).
4. **Robot Simulator**: Simulated physical environment for navigation/locomotion.
5. **Dream World**: Asynchronous space used during offline memory consolidation.

---

## 3. Registry APIs
```python
class WorldRegistry:
    """Manages active worlds, routing, and lifecycle states."""
    
    @classmethod
    def register_world(cls, world_id: str, world_type: str) -> None:
        """Register a new world model into the registry."""
        pass
        
    @classmethod
    def get_world(cls, world_id: str) -> WorldInstance:
        """Retrieve a specific world instance."""
        pass
```
- A `WorldInstance` encapsulates its own 6 cognitive domains and active simulation branch trees.
