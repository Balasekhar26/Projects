import pytest
import tempfile
import shutil
from pathlib import Path
from backend.core.preference_memory import PreferenceMemory
from backend.core.cognitive_memory_bus import MEMORY_BUS


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Sets a temporary folder for files and databases to isolate tests."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_pref_mgr_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    monkeypatch.setenv("KATTAPPA_DATA_DIR", temp_dir)

    PreferenceMemory._initialized = False
    PreferenceMemory.reset()

    yield Path(temp_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_preference_crud():
    # 1. Create a preference
    pref = PreferenceMemory.set_preference("editor_mode", "vim", confidence=0.8)
    assert pref["pref_key"] == "editor_mode"
    assert pref["pref_value"] == "vim"
    assert pref["confidence"] == 0.8
    assert pref["evidence_count"] == 1

    # 2. Retrieve preference
    retrieved = PreferenceMemory.get_preference("editor_mode")
    assert retrieved is not None
    assert retrieved["pref_value"] == "vim"

    # 3. Update preference (increments evidence_count)
    updated = PreferenceMemory.set_preference("editor_mode", "emacs", confidence=0.9)
    assert updated["pref_value"] == "emacs"
    assert updated["evidence_count"] == 2
    assert updated["confidence"] == 0.9

    # 4. List preferences
    all_prefs = PreferenceMemory.list_preferences()
    assert len(all_prefs) == 1
    assert all_prefs[0]["pref_key"] == "editor_mode"

    # 5. Delete preference
    PreferenceMemory.delete_preference("editor_mode")
    assert PreferenceMemory.get_preference("editor_mode") is None


def test_preference_reinforcement():
    # Setup preference
    PreferenceMemory.set_preference("theme", "dark", confidence=0.5)

    # Positive reinforcement -> increments confidence
    pref = PreferenceMemory.reinforce_preference("theme", positive=True)
    assert pref is not None
    assert pref["confidence"] == 0.6
    assert pref["evidence_count"] == 2

    # Negative reinforcement -> decays confidence (decays by 20%: 0.6 * 0.8 = 0.48)
    pref = PreferenceMemory.reinforce_preference("theme", positive=False)
    assert pref is not None
    assert round(pref["confidence"], 2) == 0.48

    # Multi-negative reinforcement -> triggers eviction below 0.2
    pref = PreferenceMemory.reinforce_preference("theme", positive=False) # 0.48 * 0.8 = 0.384
    assert pref is not None
    pref = PreferenceMemory.reinforce_preference("theme", positive=False) # 0.384 * 0.8 = 0.3072
    assert pref is not None
    pref = PreferenceMemory.reinforce_preference("theme", positive=False) # 0.3072 * 0.8 = 0.24576
    assert pref is not None
    
    # This one will decay to 0.24576 * 0.8 = 0.196608 (which is < 0.2)
    pref = PreferenceMemory.reinforce_preference("theme", positive=False)
    assert pref is None  # Evicted!

    # Verify deleted
    assert PreferenceMemory.get_preference("theme") is None


def test_memory_bus_routing():
    # Write preference through Memory Bus
    res = MEMORY_BUS.write("preference", {"key": "shell", "value": "zsh"}, confidence=0.7)
    assert res.success
    assert res.record_id == "shell"

    # Read preference through Memory Bus
    read_res = MEMORY_BUS.read("shell", memory_types=["preference"])
    assert len(read_res) == 1
    assert read_res[0].memory_type == "preference"
    assert len(read_res[0].records) == 1
    assert read_res[0].records[0]["pref_value"] == "zsh"
