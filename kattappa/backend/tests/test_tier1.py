from __future__ import annotations

import pytest

from backend.core.capability_graph import CapabilityGraph, CapabilityKind
from backend.core.skill_library import SkillLibrary
from backend.core.trust_evidence import (
    ConfidenceTier,
    EvidenceItem,
    EvidenceLevel,
    TrustEngine,
    assess_from_dicts,
)


@pytest.fixture(autouse=True)
def _clean():
    CapabilityGraph.reset()
    SkillLibrary.reset()
    yield
    CapabilityGraph.reset()
    SkillLibrary.reset()


# ===========================================================================
# Capability Graph
# ===========================================================================

def test_capability_assessment_finds_missing():
    CapabilityGraph.register("Backend", CapabilityKind.SKILL, available=True)
    CapabilityGraph.register("Testing", CapabilityKind.SKILL, available=True)
    CapabilityGraph.register("UI Design", CapabilityKind.SKILL, available=False)

    result = CapabilityGraph.assess("Build Android App", ["Backend", "Testing", "UI Design"])
    assert set(result["satisfied"]) == {"Backend", "Testing"}
    assert result["missing"] == ["UI Design"]
    assert result["can_proceed"] is False
    assert result["coverage"] == pytest.approx(2 / 3, abs=1e-3)


def test_unregistered_capability_is_missing():
    CapabilityGraph.register("Firmware", available=True)
    result = CapabilityGraph.assess("Build DEWS", ["Firmware", "RF Design"])
    assert "RF Design" in result["missing"]


def test_dependency_closure_and_bottlenecks():
    CapabilityGraph.register("Firmware", available=True)
    CapabilityGraph.register("RF Testing", available=True, depends_on=["Firmware", "RF Design"])
    CapabilityGraph.register("RF Design", available=False)
    result = CapabilityGraph.assess("DEWS RF", ["RF Testing"])
    # Closure pulls in the dependencies.
    assert "Firmware" in result["required"] and "RF Design" in result["required"]
    # RF Design is missing AND something depends on it -> bottleneck.
    assert "RF Design" in result["missing"]
    assert "RF Design" in result["bottlenecks"]


def test_alternative_satisfies_capability():
    CapabilityGraph.register("PostgreSQL", available=False, alternatives=["SQLite"])
    CapabilityGraph.register("SQLite", available=True)
    result = CapabilityGraph.assess("Store data", ["PostgreSQL"])
    assert result["missing"] == []
    assert result["can_proceed"] is True


# ===========================================================================
# Trust & Evidence System
# ===========================================================================

def test_higher_evidence_dominates():
    report = TrustEngine.assess("RF link closes", [
        EvidenceItem("Poet", EvidenceLevel.OPINION, supports=True),
        EvidenceItem("PhysicsValidator", EvidenceLevel.REAL_WORLD, supports=True),
    ])
    assert report.top_level == "real_world"
    assert report.confidence is ConfidenceTier.HIGH
    assert report.evidence_score >= 0.9


def test_opinion_only_is_low_trust():
    report = TrustEngine.assess("It will work", [
        EvidenceItem("Engineer", EvidenceLevel.OPINION, supports=True),
    ])
    assert report.confidence is ConfidenceTier.LOW


def test_refuting_stronger_evidence_flags_conflict():
    report = TrustEngine.assess("The build is fine", [
        EvidenceItem("Engineer", EvidenceLevel.LLM_REASONING, supports=True),
        EvidenceItem("CompilerValidator", EvidenceLevel.VALIDATOR, supports=False),
    ])
    assert report.conflict is True
    assert report.confidence is ConfidenceTier.LOW


def test_corroboration_boosts_score():
    one = TrustEngine.assess("X", [EvidenceItem("a", EvidenceLevel.TEST_RESULT)])
    many = TrustEngine.assess("X", [
        EvidenceItem("a", EvidenceLevel.TEST_RESULT),
        EvidenceItem("b", EvidenceLevel.TEST_RESULT),
        EvidenceItem("c", EvidenceLevel.TEST_RESULT),
    ])
    assert many.evidence_score > one.evidence_score


def test_no_evidence_is_zero():
    report = TrustEngine.assess("nothing", [])
    assert report.evidence_score == 0.0
    assert report.top_level == "none"


def test_assess_from_dicts_and_provenance():
    report = assess_from_dicts("claim", [
        {"source": "sim", "level": "test_result", "supports": True},
        {"source": "val", "level": "validator", "supports": True},
    ])
    assert report.provenance[0]["level_value"] >= report.provenance[-1]["level_value"]
    import json
    json.dumps(report.to_dict())


# ===========================================================================
# Skill Library
# ===========================================================================

def test_add_and_search_skill():
    SkillLibrary.add_skill("RF Design", "Design an RF link budget",
                           inputs=["frequency", "range", "power"], outputs=["design package"],
                           tags=["rf", "hardware"])
    assert SkillLibrary.get("RF Design")["inputs"] == ["frequency", "range", "power"]
    results = SkillLibrary.search("rf link")
    assert any(s["name"] == "RF Design" for s in results)


def test_duplicate_skill_rejected():
    SkillLibrary.add_skill("Build APK")
    with pytest.raises(ValueError):
        SkillLibrary.add_skill("build apk")  # case-insensitive name clash


def test_skill_promoted_to_trusted_after_successes():
    SkillLibrary.add_skill("Write Unit Tests")
    for _ in range(3):
        skill = SkillLibrary.record_result("Write Unit Tests", True)
    assert skill["trust"] == "trusted"
    assert skill["success_rate"] == 1.0


def test_skill_stays_draft_with_failures():
    SkillLibrary.add_skill("Flaky Skill")
    SkillLibrary.record_result("Flaky Skill", True)
    SkillLibrary.record_result("Flaky Skill", False)
    skill = SkillLibrary.record_result("Flaky Skill", True)
    assert skill["trust"] == "draft"  # rate below promotion threshold


def test_find_for_tags():
    SkillLibrary.add_skill("PCB Layout", tags=["hardware", "pcb"])
    SkillLibrary.add_skill("Documentation", tags=["writing"])
    hits = {s["name"] for s in SkillLibrary.find_for_tags(["hardware"])}
    assert hits == {"PCB Layout"}


def test_library_is_template_store_not_executor():
    for forbidden in ("execute", "run", "apply", "invoke"):
        assert not hasattr(SkillLibrary, forbidden)
