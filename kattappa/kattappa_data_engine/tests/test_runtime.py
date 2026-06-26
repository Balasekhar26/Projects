import os
import sys
import pytest

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from kattappa_runtime.loader import ModelLoader, Mode
from kattappa_runtime.prompt_builder import PromptBuilder
from kattappa_runtime.conversation import ConversationState
from kattappa_runtime.memory import DummyMemoryProvider
from kattappa_runtime.router import ToolRouter

def test_conversation_state_pruning():
    conv = ConversationState(max_tokens=100)
    
    # Add multiple messages to trigger pruning limit
    for i in range(20):
        conv.add_message("user", f"Here is turn number {i} with some additional padding words to increase size.")
        conv.add_message("assistant", f"Acknowledging turn {i}.")
        
    conv.prune_history()
    
    # Assert history was pruned and fits limits
    assert len(conv.messages) < 40
    assert conv.estimate_tokens() <= 100

def test_prompt_builder():
    builder = PromptBuilder()
    prompt = builder.build_prompt(
        system_rules="System Test.",
        memory_context="Stored name is Balu.",
        conversation_history=[{"role": "user", "content": "hello"}],
        user_message="help me"
    )
    
    # Verify exact Qwen tags
    assert "<|im_start|>system" in prompt
    assert "System Test." in prompt
    assert "[Persistent Memory Context]" in prompt
    assert "Stored name is Balu." in prompt
    assert "<|im_start|>user\nhello<|im_end|>" in prompt
    assert "<|im_start|>user\nhelp me<|im_end|>" in prompt
    assert "<|im_start|>assistant" in prompt

def test_tool_router_extraction_and_execution():
    router = ToolRouter()
    
    # Test valid JSON extraction from markdown
    output = "Thinking: Let's run a calculation.\n\n```json\n{\n  \"tool\": \"calculator\",\n  \"arguments\": {\n    \"expression\": \"25 * 4\"\n  }\n}\n```"
    result = router.parse_and_execute(output)
    
    assert result is not None
    assert result["tool"] == "calculator"
    assert result["result"] == {"result": "100"}

def test_clock_tool():
    router = ToolRouter()
    output = "{\n  \"tool\": \"clock\",\n  \"arguments\": {}\n}"
    result = router.parse_and_execute(output)
    
    assert result is not None
    assert result["tool"] == "clock"
    assert "current_time" in result["result"]
    assert "timestamp" in result["result"]

def test_search_mock_tool():
    router = ToolRouter()
    output = "{\n  \"tool\": \"search_mock\",\n  \"arguments\": {\n    \"query\": \"creator of kattappa\"\n  }\n}"
    result = router.parse_and_execute(output)
    
    assert result is not None
    assert result["tool"] == "search_mock"
    assert any("Balu" in r for r in result["result"]["results"])

def test_memory_provider():
    test_cache = "/tmp/test_runtime_memory.json"
    if os.path.exists(test_cache):
        os.remove(test_cache)
        
    prov = DummyMemoryProvider(cache_file=test_cache)
    prov.store({"user_pet": "Dog"})
    
    # Retrieve test
    res = prov.retrieve("pet query")
    assert "user_pet: Dog" in res
    
    # Forget test
    prov.forget("user_pet")
    res = prov.retrieve("pet query")
    assert "No relevant memories found" in res
    
    if os.path.exists(test_cache):
        os.remove(test_cache)
