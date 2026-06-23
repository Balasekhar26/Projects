import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.agent_society import AgentSociety
from backend.core.learning_dashboard import LearningDashboard


@pytest.fixture(autouse=True)
def clean_society_data(monkeypatch, tmp_path):
    # Direct reputations and debates to temp paths for clean testing
    monkeypatch.setattr("backend.core.agent_society._reputations_path", lambda: tmp_path / "agent_reputations.json")
    monkeypatch.setattr("backend.core.agent_society._debates_path", lambda: tmp_path / "agent_debates.json")


def test_reputation_seed_and_persistence():
    reps = AgentSociety.load_reputations()
    assert "Researcher" in reps
    assert reps["Researcher"]["reputation"] == 0.91
    assert reps["Auditor"]["reputation"] == 0.99
    
    # Check that it loaded seed and saved it
    reps["Researcher"]["reputation"] = 0.95
    AgentSociety.save_reputations(reps)
    
    loaded = AgentSociety.load_reputations()
    assert loaded["Researcher"]["reputation"] == 0.95


def test_debate_seed_and_persistence():
    debates = AgentSociety.load_debates()
    assert len(debates) >= 1
    assert debates[0]["id"] == "deb_001"
    assert debates[0]["consensus"] == "APPROVED"


def test_trigger_debate_approved():
    debate = AgentSociety.trigger_debate(
        title="Optimizing Node Lookup Cache",
        details="Increase cache size to 1024 nodes."
    )
    assert debate["consensus"] == "APPROVED"
    assert not debate["vetoed"]
    assert debate["votes"]["Reviewer"] == "APPROVE"
    assert debate["votes"]["Auditor"] == "APPROVE"


def test_trigger_debate_reviewer_reject():
    debate = AgentSociety.trigger_debate(
        title="Complex and Fail-Prone Lookup Cache",
        details="Failed system tests."
    )
    assert debate["consensus"] == "REJECTED"
    assert not debate["vetoed"]
    assert debate["votes"]["Reviewer"] == "REJECT"


def test_trigger_debate_auditor_veto_by_title():
    debate = AgentSociety.trigger_debate(
        title="Violate cache safety rules",
        details="Access memory directly."
    )
    assert debate["consensus"] == "REJECTED"
    assert debate["vetoed"]
    assert debate["votes"]["Auditor"] == "REJECT"


def test_trigger_debate_auditor_veto_by_protected_path():
    debate = AgentSociety.trigger_debate(
        title="Modify safety rules",
        details="Write to safety kernel registry.",
        target_file="backend/core/safety.py"
    )
    assert debate["consensus"] == "REJECTED"
    assert debate["vetoed"]
    assert debate["votes"]["Auditor"] == "REJECT"


def test_reputation_shifts():
    reps = AgentSociety.load_reputations()
    initial_eng_rep = reps["Engineer"]["reputation"]
    
    # Success updates reputation positively (caps at 1.0)
    AgentSociety.update_agent_reputation("Engineer", success=True)
    reps_after = AgentSociety.load_reputations()
    assert reps_after["Engineer"]["reputation"] > initial_eng_rep or reps_after["Engineer"]["reputation"] == 1.0
    
    # Failure degrades reputation
    curr_rep = reps_after["Engineer"]["reputation"]
    AgentSociety.update_agent_reputation("Engineer", success=False)
    reps_degraded = AgentSociety.load_reputations()
    assert reps_degraded["Engineer"]["reputation"] < curr_rep


def test_memory_curator_deduplication(monkeypatch, tmp_path):
    from backend.core.long_term_memory import LongTermMemory
    
    monkeypatch.setattr("backend.core.long_term_memory._memory_file_path", lambda: tmp_path / "long_term_memory.json")
    
    # Write duplicate entries into memory
    record = {"item": "duplicate_value"}
    LongTermMemory.add_record("ResearchMemory", record)
    LongTermMemory.add_record("ResearchMemory", record)
    
    partition = LongTermMemory.get_partition("ResearchMemory")
    assert len(partition) == 2
    
    # Run curator
    res = AgentSociety.curate_memory_partition("ResearchMemory")
    assert res["status"] == "success"
    assert res["removed_count"] == 1
    
    partition_cleaned = LongTermMemory.get_partition("ResearchMemory")
    assert len(partition_cleaned) == 1


def test_learning_dashboard_agent_society_stats():
    # Setup some test debates
    AgentSociety.trigger_debate("Reviewer should revise this complex thing", "details complex")
    AgentSociety.trigger_debate("Auditor vetoes: Violate rules", "details violating")
    
    stats = LearningDashboard.agent_society_stats()
    assert stats["total_debates"] >= 2
    assert "Researcher" in [r["agent"] for r in stats["reputations"]]
    assert stats["top_performing_agent"] is not None
    assert stats["most_accurate_reviewer"] is not None
    # Auditor is veto source, so Auditor should be failure source
    assert stats["most_common_failure_source"] in {"Auditor", "Reviewer"}


def test_fastapi_endpoints():
    client = TestClient(app)
    
    # Test reputation endpoint
    resp = client.get("/dashboard/agent-society/reputation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["data"]) >= 6
    
    # Test debates endpoint
    resp2 = client.get("/dashboard/agent-society/debates")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "ok"
    assert "top_performing_agent" in data2["data"]
    assert "debates" in data2["data"]
