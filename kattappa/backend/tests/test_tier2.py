from __future__ import annotations

import pytest

from backend.core.knowledge_distillation import KnowledgeDistiller
from backend.core.simulation_engine import Scenario, SimulationEngine
from backend.core.world_model import EntityType, RelationType, WorldModel


@pytest.fixture(autouse=True)
def _clean():
    WorldModel.reset()
    yield
    WorldModel.reset()


# ===========================================================================
# World Model
# ===========================================================================

def test_impact_propagates_along_affects_chain():
    for name in ("RF Module", "Antenna", "Range", "Battery Life"):
        WorldModel.add_entity(name, EntityType.COMPONENT)
    WorldModel.add_relation("RF Module", "Antenna", RelationType.AFFECTS)
    WorldModel.add_relation("Antenna", "Range", RelationType.AFFECTS)
    WorldModel.add_relation("Range", "Battery Life", RelationType.AFFECTS)

    impact = WorldModel.impact_of("RF Module")
    assert impact["affected_names"] == ["Antenna", "Range", "Battery Life"]
    # Depth increases along the chain.
    depths = {a["entity"]: a["depth"] for a in impact["affected"]}
    assert depths["Antenna"] == 1 and depths["Battery Life"] == 3


def test_depends_on_propagates_impact():
    WorldModel.add_entity("STM32", EntityType.COMPONENT)
    WorldModel.add_entity("Firmware", EntityType.COMPONENT)
    # Firmware depends on STM32 -> changing STM32 affects Firmware.
    WorldModel.add_relation("Firmware", "STM32", RelationType.DEPENDS_ON)
    impact = WorldModel.impact_of("STM32")
    assert "Firmware" in impact["affected_names"]


def test_subtree_follows_contains():
    WorldModel.add_entity("DEWS", EntityType.PROJECT)
    WorldModel.add_entity("Hardware", EntityType.COMPONENT)
    WorldModel.add_entity("RF Module", EntityType.COMPONENT)
    WorldModel.add_relation("DEWS", "Hardware", RelationType.CONTAINS)
    WorldModel.add_relation("Hardware", "RF Module", RelationType.CONTAINS)
    tree = WorldModel.subtree("DEWS")
    assert tree["name"] == "DEWS"
    assert tree["children"][0]["name"] == "Hardware"
    assert tree["children"][0]["children"][0]["name"] == "RF Module"


def test_relation_requires_known_entities():
    WorldModel.add_entity("A")
    with pytest.raises(ValueError):
        WorldModel.add_relation("A", "Ghost", RelationType.AFFECTS)


def test_impact_handles_cycles():
    WorldModel.add_entity("X")
    WorldModel.add_entity("Y")
    WorldModel.add_relation("X", "Y", RelationType.AFFECTS)
    WorldModel.add_relation("Y", "X", RelationType.AFFECTS)
    impact = WorldModel.impact_of("X")
    assert "Y" in impact["affected_names"]  # terminates despite the cycle


def test_unknown_entity_impact_raises():
    with pytest.raises(KeyError):
        WorldModel.impact_of("Nope")


# ===========================================================================
# Simulation Engine
# ===========================================================================

def test_simulation_is_deterministic():
    sc = Scenario.from_dict({"name": "Memory Redesign", "base_success_prob": 1.0,
                             "risks": [{"name": "Fragmentation", "probability": 0.3, "impact": 0.5}]})
    a = SimulationEngine.simulate(sc, trials=500, seed=7).to_dict()
    b = SimulationEngine.simulate(sc, trials=500, seed=7).to_dict()
    assert a == b


def test_simulation_rates_sum_to_one():
    sc = Scenario.from_dict({"name": "X", "risks": [{"name": "R", "probability": 0.4, "impact": 0.4}]})
    rep = SimulationEngine.simulate(sc, trials=1000)
    assert rep.success_rate + rep.failure_rate == pytest.approx(1.0)


def test_dominant_risk_ranked_first():
    sc = Scenario.from_dict({"name": "Memory Redesign", "risks": [
        {"name": "Fragmentation", "probability": 0.6, "impact": 0.8},
        {"name": "Cache Thrash", "probability": 0.1, "impact": 0.2},
    ]})
    rep = SimulationEngine.simulate(sc, trials=2000)
    assert rep.top_risks[0]["risk"] == "Fragmentation"
    assert rep.failure_rate > 0


def test_no_risks_matches_base():
    sc = Scenario.from_dict({"name": "Safe", "base_success_prob": 1.0, "risks": []})
    rep = SimulationEngine.simulate(sc, trials=100)
    assert rep.success_rate == 1.0
    assert "proceed" in rep.recommendation


def test_high_failure_recommends_review():
    sc = Scenario.from_dict({"name": "Risky", "risks": [
        {"name": "Boom", "probability": 0.9, "impact": 0.9}]})
    rep = SimulationEngine.simulate(sc, trials=500)
    assert "review" in rep.recommendation


# ===========================================================================
# Knowledge Distillation
# ===========================================================================

def test_distill_clusters_similar_observations():
    obs = [
        "Users abandon plans that have too many steps",
        "Users abandon long plans with many steps",
        "Long plans with too many steps get abandoned by users",
        "RF test failed due to antenna mismatch",
    ]
    report = KnowledgeDistiller.distill(obs, min_cluster=3, similarity=0.34)
    assert len(report.patterns) == 1  # only the 'abandon long plans' cluster reaches 3
    pattern = report.patterns[0]
    assert pattern.count == 3
    assert "plans" in pattern.common_terms or "abandon" in pattern.common_terms
    assert pattern.principle  # a principle was synthesised


def test_distill_principle_hint():
    obs = ["plans over seven steps abandoned"] * 3
    report = KnowledgeDistiller.distill(
        obs, min_cluster=3, principle_hints={"plans": "Large plans need milestones every 3 steps"})
    assert report.patterns[0].principle == "Large plans need milestones every 3 steps"


def test_distill_below_threshold_yields_no_pattern():
    report = KnowledgeDistiller.distill(["one off thing", "totally different note"], min_cluster=3)
    assert report.patterns == []
    assert report.observations == 2
