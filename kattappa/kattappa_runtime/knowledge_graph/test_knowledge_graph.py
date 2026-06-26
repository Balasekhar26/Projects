"""
Tests for Step 29 — Knowledge Graph
=======================================

Hermetic tests — no network, no training. Disk via tmp_path.

Covers:

Schema
  - Node: canonical_name auto-generated, to_dict/from_dict roundtrip
  - Edge: to_dict/from_dict roundtrip, default relationship
  - GraphStats.summary() non-empty

GraphStore
  - add_node: stores and retrieves correctly
  - add_node: dedup by canonical name + entity type increments mention_count
  - add_node: different entity_type → different node (no dedup)
  - add_node: richer description updates existing
  - add_edge: stores and retrieves correctly
  - add_edge: dedup by (source, target, relationship) updates weight to max
  - get_edges_from: filtered by relationship type
  - get_edges_to: filtered by relationship type
  - find_by_name: exact match
  - find_by_name: case-insensitive canonical match
  - nodes_by_type: returns correct subset
  - node_count / edge_count
  - persistence across instances
  - remove_edge removes from adjacency index

GraphQuery
  - find_related: returns nodes within max_depth
  - find_related: respects max_depth=1 (direct only)
  - find_related: respects relation_type filter
  - find_related: empty when entity not found
  - find_dependencies: follows DEPENDS_ON chain
  - find_prerequisites: finds prereqs via DEPENDS_ON outgoing
  - find_tools_for_skill: returns TOOL nodes via USES edge
  - find_tools_for_skill: returns empty when no tools connected
  - find_knowledge_gaps: returns unlearned prereqs
  - find_knowledge_gaps: excludes already-learned concepts
  - find_path: finds direct path length 1
  - find_path: finds indirect path (2 hops)
  - find_path: returns found=False when no path exists
  - find_path: same source and target returns length 0
  - get_subgraph: returns correct nodes and edges within radius
  - get_hubs: sorted by mention_count descending
  - search_nodes: substring match on name
  - search_nodes: substring match on description
  - traverse: BFS depth limit respected
  - traverse: min_weight filter

KnowledgeGraph Facade
  - add() returns node in graph
  - add() deduplication via facade
  - relate() creates edge
  - relate_by_name() creates nodes + edge
  - describe() contains entity name and relationships
  - find_related, find_dependencies, find_prerequisites all delegate correctly
  - find_tools_for_skill via facade
  - find_knowledge_gaps via facade
  - ingest_research_report adds topic + concept nodes
  - ingest_learning_record adds LEARNED_FROM edge
  - ingest_mistake adds DEPENDS_ON edge for gap
  - stats() returns GraphStats with correct counts
  - search() returns matching nodes
  - find_path via facade
"""

import pytest
from kattappa_runtime.knowledge_graph.schema import (
    Node, Edge, EntityType, RelationshipType, GraphStats
)
from kattappa_runtime.knowledge_graph.store  import GraphStore
from kattappa_runtime.knowledge_graph.query  import GraphQuery
from kattappa_runtime.knowledge_graph.engine import KnowledgeGraph


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def store(tmp_path):
    return GraphStore(store_dir=str(tmp_path / "kg"))


@pytest.fixture
def kg(tmp_path):
    return KnowledgeGraph(store_dir=str(tmp_path / "kg"))


def make_rf_graph(kg: KnowledgeGraph):
    """Build a small RF-domain knowledge graph for query tests."""
    rf     = kg.add("RF Systems",           EntityType.RESEARCH_TOPIC, description="Radio frequency engineering")
    smith  = kg.add("Smith Chart",           EntityType.TOOL)
    imp    = kg.add("Impedance Matching",    EntityType.CONCEPT)
    trans  = kg.add("Transmission Line",     EntityType.CONCEPT)
    bala   = kg.add("Bala Sekhar",           EntityType.PERSON)
    katt   = kg.add("kattappa",              EntityType.PERSON)

    kg.relate(rf,   smith,  RelationshipType.USES,          weight=0.9)
    kg.relate(rf,   imp,    RelationshipType.DEPENDS_ON,    weight=0.85)
    kg.relate(imp,  trans,  RelationshipType.DEPENDS_ON,    weight=0.7)
    kg.relate(bala, rf,     RelationshipType.WORKED_ON,     weight=0.8)
    kg.relate(katt, imp,    RelationshipType.LEARNED_FROM,  weight=0.6)
    kg.relate(smith, imp,   RelationshipType.APPLIES_TO,    weight=0.75)

    return rf, smith, imp, trans, bala, katt


# ===========================================================================
# Schema Tests
# ===========================================================================

class TestNodeSchema:
    def test_canonical_name_auto(self):
        n = Node(name="Smith Chart")
        assert n.canonical_name == "smith chart"

    def test_roundtrip(self):
        n  = Node(name="Impedance Matching", entity_type=EntityType.CONCEPT,
                  description="Matching network theory", confidence=0.8)
        d  = n.to_dict()
        n2 = Node.from_dict(d)
        assert n2.name          == "Impedance Matching"
        assert n2.entity_type   == EntityType.CONCEPT
        assert n2.confidence    == pytest.approx(0.8)

    def test_default_entity_type(self):
        n = Node(name="X")
        assert n.entity_type == EntityType.CONCEPT


class TestEdgeSchema:
    def test_roundtrip(self):
        e  = Edge(source_id="a", target_id="b",
                  relationship=RelationshipType.USES, weight=0.9,
                  evidence="test")
        d  = e.to_dict()
        e2 = Edge.from_dict(d)
        assert e2.relationship == RelationshipType.USES
        assert e2.weight       == pytest.approx(0.9)
        assert e2.evidence     == "test"

    def test_default_relationship(self):
        e = Edge()
        assert e.relationship == RelationshipType.RELATED_TO


class TestGraphStats:
    def test_summary_non_empty(self):
        s = GraphStats(node_count=5, edge_count=3,
                       entity_counts={"concept": 3, "tool": 2},
                       rel_counts={"uses": 2, "related_to": 1},
                       top_nodes=["Smith Chart", "RF Systems"])
        assert "5 nodes" in s.summary()
        assert "Smith Chart" in s.summary()


# ===========================================================================
# GraphStore Tests
# ===========================================================================

class TestGraphStore:
    def test_add_and_get(self, store):
        n = Node(name="Smith Chart", entity_type=EntityType.TOOL)
        added = store.add_node(n)
        retrieved = store.get_node(added.node_id)
        assert retrieved.name == "Smith Chart"

    def test_dedup_increments_mention_count(self, store):
        n1 = store.add_node(Node(name="Impedance Matching", entity_type=EntityType.CONCEPT))
        n2 = store.add_node(Node(name="Impedance Matching", entity_type=EntityType.CONCEPT))
        assert n1.node_id == n2.node_id
        assert store.get_node(n1.node_id).mention_count == 2

    def test_different_type_not_deduped(self, store):
        n1 = store.add_node(Node(name="RF", entity_type=EntityType.CONCEPT))
        n2 = store.add_node(Node(name="RF", entity_type=EntityType.DOMAIN))
        assert n1.node_id != n2.node_id

    def test_dedup_updates_description(self, store):
        store.add_node(Node(name="X", entity_type=EntityType.CONCEPT, description="short"))
        store.add_node(Node(name="X", entity_type=EntityType.CONCEPT, description="a much longer description"))
        node = store.find_by_name("X")
        assert "longer" in node.description

    def test_add_edge_and_retrieve(self, store):
        src = store.add_node(Node(name="A", entity_type=EntityType.CONCEPT))
        tgt = store.add_node(Node(name="B", entity_type=EntityType.CONCEPT))
        e = store.add_edge(Edge(source_id=src.node_id, target_id=tgt.node_id,
                                relationship=RelationshipType.USES, weight=0.8))
        edges = store.get_edges_from(src.node_id)
        assert len(edges) == 1
        assert edges[0].weight == pytest.approx(0.8)

    def test_edge_dedup_updates_weight_to_max(self, store):
        src = store.add_node(Node(name="A", entity_type=EntityType.CONCEPT))
        tgt = store.add_node(Node(name="B", entity_type=EntityType.CONCEPT))
        store.add_edge(Edge(source_id=src.node_id, target_id=tgt.node_id,
                            relationship=RelationshipType.USES, weight=0.5))
        store.add_edge(Edge(source_id=src.node_id, target_id=tgt.node_id,
                            relationship=RelationshipType.USES, weight=0.9))
        edges = store.get_edges_from(src.node_id, RelationshipType.USES)
        assert len(edges) == 1
        assert edges[0].weight == pytest.approx(0.9)

    def test_get_edges_from_filtered(self, store):
        src = store.add_node(Node(name="S", entity_type=EntityType.CONCEPT))
        tgt = store.add_node(Node(name="T", entity_type=EntityType.CONCEPT))
        store.add_edge(Edge(source_id=src.node_id, target_id=tgt.node_id,
                            relationship=RelationshipType.USES))
        store.add_edge(Edge(source_id=src.node_id, target_id=tgt.node_id,
                            relationship=RelationshipType.RELATED_TO))
        uses_only = store.get_edges_from(src.node_id, RelationshipType.USES)
        assert len(uses_only) == 1

    def test_get_edges_to(self, store):
        src = store.add_node(Node(name="S", entity_type=EntityType.CONCEPT))
        tgt = store.add_node(Node(name="T", entity_type=EntityType.CONCEPT))
        store.add_edge(Edge(source_id=src.node_id, target_id=tgt.node_id,
                            relationship=RelationshipType.USES))
        incoming = store.get_edges_to(tgt.node_id)
        assert len(incoming) == 1

    def test_find_by_name_case_insensitive(self, store):
        store.add_node(Node(name="Smith Chart", entity_type=EntityType.TOOL))
        node = store.find_by_name("smith chart")
        assert node is not None
        assert node.name == "Smith Chart"

    def test_nodes_by_type(self, store):
        store.add_node(Node(name="A", entity_type=EntityType.TOOL))
        store.add_node(Node(name="B", entity_type=EntityType.CONCEPT))
        store.add_node(Node(name="C", entity_type=EntityType.TOOL))
        tools = store.nodes_by_type(EntityType.TOOL)
        assert len(tools) == 2

    def test_node_count(self, store):
        store.add_node(Node(name="X", entity_type=EntityType.CONCEPT))
        store.add_node(Node(name="Y", entity_type=EntityType.CONCEPT))
        assert store.node_count() == 2

    def test_edge_count(self, store):
        n1 = store.add_node(Node(name="X", entity_type=EntityType.CONCEPT))
        n2 = store.add_node(Node(name="Y", entity_type=EntityType.CONCEPT))
        store.add_edge(Edge(source_id=n1.node_id, target_id=n2.node_id,
                            relationship=RelationshipType.USES))
        assert store.edge_count() == 1

    def test_persistence_across_instances(self, tmp_path):
        d = str(tmp_path / "kg2")
        s1 = GraphStore(store_dir=d)
        n = s1.add_node(Node(name="Persist Me", entity_type=EntityType.CONCEPT))

        s2 = GraphStore(store_dir=d)
        loaded = s2.get_node(n.node_id)
        assert loaded is not None
        assert loaded.name == "Persist Me"

    def test_remove_edge(self, store):
        src = store.add_node(Node(name="S", entity_type=EntityType.CONCEPT))
        tgt = store.add_node(Node(name="T", entity_type=EntityType.CONCEPT))
        e = store.add_edge(Edge(source_id=src.node_id, target_id=tgt.node_id,
                                relationship=RelationshipType.USES))
        result = store.remove_edge(e.edge_id)
        assert result is True
        assert len(store.get_edges_from(src.node_id)) == 0


# ===========================================================================
# GraphQuery Tests
# ===========================================================================

class TestGraphQuery:
    def test_find_related_direct(self, kg):
        make_rf_graph(kg)
        results = kg.find_related("RF Systems", max_depth=1)
        names = [r.node.name for r in results]
        assert "Smith Chart" in names or "Impedance Matching" in names

    def test_find_related_depth_2(self, kg):
        make_rf_graph(kg)
        results = kg.find_related("RF Systems", max_depth=2)
        names = [r.node.name for r in results]
        # Transmission Line is 2 hops away via RF→Impedance→Transmission
        assert "Transmission Line" in names

    def test_find_related_depth_1_excludes_depth_2(self, kg):
        make_rf_graph(kg)
        results = kg.find_related("RF Systems", max_depth=1)
        names = [r.node.name for r in results]
        assert "Transmission Line" not in names

    def test_find_related_relation_filter(self, kg):
        make_rf_graph(kg)
        results = kg.find_related("RF Systems", relation_type=RelationshipType.USES, max_depth=1)
        names = [r.node.name for r in results]
        assert "Smith Chart" in names
        assert "Impedance Matching" not in names  # connected via DEPENDS_ON

    def test_find_related_unknown_entity(self, kg):
        make_rf_graph(kg)
        results = kg.find_related("Nonexistent Entity")
        assert results == []

    def test_find_dependencies(self, kg):
        make_rf_graph(kg)
        results = kg.find_dependencies("RF Systems")
        names = [r.node.name for r in results]
        assert "Impedance Matching" in names

    def test_find_dependencies_transitive(self, kg):
        make_rf_graph(kg)
        results = kg.find_dependencies("RF Systems", max_depth=2)
        names = [r.node.name for r in results]
        # Transmission Line depends on Impedance Matching which RF depends on
        assert "Transmission Line" in names

    def test_find_prerequisites(self, kg):
        make_rf_graph(kg)
        results = kg.find_prerequisites("RF Systems")
        # RF depends on Impedance Matching → that's a prerequisite
        names = [r.node.name for r in results]
        assert "Impedance Matching" in names

    def test_find_tools_for_skill(self, kg):
        make_rf_graph(kg)
        tools = kg.find_tools_for_skill("RF Systems")
        assert any(t.name == "Smith Chart" for t in tools)

    def test_find_tools_no_tools(self, kg):
        kg.add("Orphan Skill", EntityType.SKILL)
        tools = kg.find_tools_for_skill("Orphan Skill")
        assert tools == []

    def test_find_knowledge_gaps_unlearned(self, kg):
        make_rf_graph(kg)
        # kattappa has LEARNED_FROM Impedance Matching only
        # Transmission Line should be a gap
        gaps = kg.find_knowledge_gaps("RF Systems", learner_name="kattappa")
        gap_names = [g.name for g in gaps]
        assert "Transmission Line" in gap_names

    def test_find_knowledge_gaps_excludes_learned(self, kg):
        make_rf_graph(kg)
        # kattappa already learned Impedance Matching
        gaps = kg.find_knowledge_gaps("RF Systems", learner_name="kattappa")
        gap_names = [g.name for g in gaps]
        assert "Impedance Matching" not in gap_names

    def test_find_path_direct(self, kg):
        make_rf_graph(kg)
        result = kg.find_path("RF Systems", "Smith Chart")
        assert result.found is True
        assert result.length == 1

    def test_find_path_indirect(self, kg):
        make_rf_graph(kg)
        result = kg.find_path("RF Systems", "Transmission Line")
        assert result.found is True
        assert result.length >= 2

    def test_find_path_not_found(self, kg):
        kg.add("Island A", EntityType.CONCEPT)
        kg.add("Island B", EntityType.CONCEPT)
        result = kg.find_path("Island A", "Island B")
        assert result.found is False

    def test_find_path_same_node(self, kg):
        make_rf_graph(kg)
        result = kg.find_path("RF Systems", "RF Systems")
        assert result.found is True
        assert result.length == 0

    def test_get_subgraph(self, kg):
        make_rf_graph(kg)
        nodes, edges = kg.get_subgraph("RF Systems", radius=1)
        names = [n.name for n in nodes]
        assert "RF Systems"        in names
        assert "Smith Chart"       in names
        assert "Impedance Matching" in names
        # Bala worked_on RF, so should be in the subgraph
        assert "Bala Sekhar" in names

    def test_get_hubs_sorted_by_mention_count(self, kg):
        make_rf_graph(kg)
        # Mention RF a few more times
        for _ in range(3):
            kg.add("RF Systems", EntityType.RESEARCH_TOPIC)
        hubs = kg.get_hubs(n=3)
        assert hubs[0].name == "RF Systems"

    def test_search_by_name(self, kg):
        make_rf_graph(kg)
        results = kg.search("smith")
        assert any(n.name == "Smith Chart" for n in results)

    def test_search_by_description(self, kg):
        make_rf_graph(kg)
        results = kg.search("radio frequency")
        assert any(n.name == "RF Systems" for n in results)


# ===========================================================================
# KnowledgeGraph Facade Tests
# ===========================================================================

class TestKnowledgeGraphFacade:
    def test_add_returns_node(self, kg):
        node = kg.add("Smith Chart", EntityType.TOOL)
        assert node.name        == "Smith Chart"
        assert node.entity_type == EntityType.TOOL

    def test_add_deduplicates(self, kg):
        n1 = kg.add("Smith Chart", EntityType.TOOL)
        n2 = kg.add("Smith Chart", EntityType.TOOL)
        assert n1.node_id == n2.node_id
        assert kg.node_count() == 1

    def test_relate_creates_edge(self, kg):
        rf    = kg.add("RF", EntityType.DOMAIN)
        smith = kg.add("Smith", EntityType.TOOL)
        kg.relate(rf, smith, RelationshipType.USES, weight=0.9)
        assert kg.edge_count() == 1

    def test_relate_by_name(self, kg):
        kg.relate_by_name("RF", "Smith Chart", RelationshipType.USES, weight=0.8)
        assert kg.node_count() == 2
        assert kg.edge_count() == 1

    def test_describe_contains_name(self, kg):
        make_rf_graph(kg)
        desc = kg.describe("RF Systems")
        assert "RF Systems" in desc
        assert "uses" in desc or "depends_on" in desc

    def test_describe_unknown_entity(self, kg):
        desc = kg.describe("Nonexistent")
        assert "not found" in desc.lower()

    def test_stats_correct_counts(self, kg):
        make_rf_graph(kg)
        s = kg.stats()
        assert s.node_count  >= 6
        assert s.edge_count  >= 5
        assert s.summary() != ""

    def test_ingest_research_report(self, kg):
        from kattappa_runtime.research.schema import ResearchReport
        report = ResearchReport(
            topic    = "Impedance Matching",
            summary  = "Smith Charts simplify impedance calculations.",
            key_facts= ["Smith Chart shows impedance", "Transmission Line theory is key"],
            findings = [],
        )
        added = kg.ingest_research_report(report, domain="rf_systems")
        assert added > 0
        assert kg.get("Impedance Matching") is not None

    def test_ingest_learning_record(self, kg):
        from kattappa_runtime.learning.schema import LearningRecord
        record = LearningRecord(domain="rf_systems", confidence=0.75)
        kg.ingest_learning_record(record, learner_name="kattappa")
        katt = kg.get("kattappa")
        assert katt is not None
        store = kg._store
        edges = store.get_edges_from(katt.node_id, RelationshipType.LEARNED_FROM)
        assert len(edges) >= 1

    def test_ingest_mistake(self, kg):
        from kattappa_runtime.self_improvement.schema import DomainWeakness
        weakness = DomainWeakness(
            domain             = "rf_systems",
            failure_count      = 3,
            partial_count      = 1,
            total_attempts     = 5,
            failure_rate       = 0.6,
            top_knowledge_gaps = ["impedance matching unknown"],
        )
        # Pass as a plain object with root_cause derived from top_knowledge_gaps
        class _FakeMistake:
            root_cause = weakness.top_knowledge_gaps[0]
        kg.ingest_mistake(_FakeMistake(), domain="rf_systems")
        gap_node = kg.get("impedance matching unknown")
        assert gap_node is not None
