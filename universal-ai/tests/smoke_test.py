from ai_system.core.config import load_settings
from ai_system.core.llm import LocalLLM
from ai_system.memory.store import MemoryStore


def test_config_and_memory() -> None:
    settings = load_settings()
    memory = MemoryStore(settings)
    memory_id = memory.remember("smoke test memory", kind="test", source="smoke")
    assert memory_id
    assert memory.count() >= 1


def test_ollama_health_shape() -> None:
    settings = load_settings()
    ok, message = LocalLLM(settings).health()
    assert isinstance(ok, bool)
    assert message
