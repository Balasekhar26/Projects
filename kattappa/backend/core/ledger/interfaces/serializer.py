from abc import ABC, abstractmethod
from typing import Any, Type, TypeVar

T = TypeVar("T")


class EventSerializer(ABC):
    @abstractmethod
    def serialize(self, obj: Any) -> str:
        """Serializes an object into a string representation."""
        pass

    @abstractmethod
    def deserialize(self, data: str, cls: Type[T]) -> T:
        """Deserializes a string representation back into an instance of class T."""
        pass


class JSONSerializer(EventSerializer):
    import json

    def serialize(self, obj: Any) -> str:
        import json

        # Handled for custom serialization if needed, e.g. using to_dict() or default dataclass serialization
        if hasattr(obj, "to_dict"):
            return json.dumps(obj.to_dict())
        elif hasattr(obj, "__dict__"):
            return json.dumps(obj.__dict__)
        return json.dumps(obj)

    def deserialize(self, data: str, cls: Type[T]) -> T:
        import json

        parsed = json.loads(data)
        if hasattr(cls, "from_dict"):
            return getattr(cls, "from_dict")(parsed)
        return cls(**parsed)
