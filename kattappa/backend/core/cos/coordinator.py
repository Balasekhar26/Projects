"""World Model Coordinator — Phase K22.

Coordinates simulation branching, Proposal Event generation, and Bayesian updates
propagated back to the Main World.
"""
from __future__ import annotations

import copy
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.cos.belief_engine import BeliefEngine
from backend.core.cos.belief_revision import BeliefRevisionEngine
from backend.core.cos.entity_system import AliasRegistry, Entity, EventLog, Relation
from backend.core.cos.state_representation import BeliefState, BeliefStatus, ObservedState, PropertyValue
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class TransitionResult:
    """Represents predicted outcomes of a simulated transition action."""
    predicted_states: Dict[str, Any]
    success: bool
    effects: Dict[str, Any]


class WorldModelCoordinator:
    """Central gateway routing domain requests, managing branches, and proposel merges."""

    # branch_id -> Dict[domain_type, Dict[entity_id, Entity]]
    _branches: Dict[str, Dict[str, Dict[str, Entity]]] = {}
    _parent_map: Dict[str, str] = {}
    _belief_states: Dict[str, BeliefState] = {}
    _revision_engines: Dict[str, BeliefRevisionEngine] = {}
    _pkgs: Dict[str, Any] = {}

    _lock = uuid.uuid4()  # Dummy object for coordinate synchronization

    @classmethod
    def reset(cls) -> None:
        """Resets all branches and map states."""
        cls._branches.clear()
        cls._parent_map.clear()
        cls._belief_states.clear()
        cls._parent_map.clear()
        cls._revision_engines.clear()
        cls._pkgs.clear()

        # Initialize main branch
        cls._branches["main"] = {
            "physical": {},
            "digital": {},
            "human": {},
            "self": {},
            "economic": {},
            "temporal": {}
        }
        cls._belief_states["main"] = BeliefState(state_id="main_belief", branch_id="main", timestamp=time.time())
        cls._revision_engines["main"] = BeliefRevisionEngine(BeliefEngine(cls._belief_states["main"]))
        
        from backend.core.cos.pkg import ProbabilisticKnowledgeGraph
        cls._pkgs["main"] = ProbabilisticKnowledgeGraph()

    @classmethod
    def get_entity(cls, domain: str, entity_id: str, branch_id: Optional[str] = None) -> Optional[Entity]:
        """Retrieve Entity from specified domain/branch. Thread-safe."""
        branch = branch_id if branch_id is not None else "main"
        domain_lower = domain.lower()

        if branch not in cls._branches:
            return None

        resolved_id = AliasRegistry.resolve(entity_id)
        return cls._branches[branch].get(domain_lower, {}).get(resolved_id)

    @classmethod
    def register_entity(cls, domain: str, entity: Entity, branch_id: Optional[str] = None) -> None:
        """Register/insert an entity into a specific branch and domain."""
        branch = branch_id if branch_id is not None else "main"
        domain_lower = domain.lower()

        if branch not in cls._branches:
            cls._branches[branch] = {
                "physical": {},
                "digital": {},
                "human": {},
                "self": {},
                "economic": {},
                "temporal": {}
            }
        if branch not in cls._pkgs:
            from backend.core.cos.pkg import ProbabilisticKnowledgeGraph
            cls._pkgs[branch] = ProbabilisticKnowledgeGraph()

        # Resolve entity_id and alias
        AliasRegistry.register_alias(entity.canonical_id, entity.entity_id)
        cls._branches[branch].setdefault(domain_lower, {})[entity.entity_id] = entity
        
        # Sync immediately
        cls.sync_branch_to_pkg(branch)

    @classmethod
    def sync_branch_to_pkg(cls, branch_id: str) -> None:
        """Synchronizes branch entity states and relations into the PKG."""
        if branch_id not in cls._branches or branch_id not in cls._pkgs:
            return
        
        pkg = cls._pkgs[branch_id]
        # Re-register all nodes and edges
        for domain, entities in cls._branches[branch_id].items():
            for entity_id, entity in entities.items():
                pkg.register_node_confidence(entity_id, entity.confidence)
                for rel in entity.relations:
                    pkg.add_relation(rel)

    @classmethod
    def create_branch(cls, parent_branch_id: Optional[str] = None) -> str:
        """Create new delta-based branch. Returns branch UUID."""
        parent = parent_branch_id if parent_branch_id is not None else "main"
        if parent not in cls._branches:
            raise ValueError(f"Parent branch '{parent}' does not exist.")

        new_branch = f"branch_{uuid.uuid4().hex[:8]}"
        
        # Deep copy all entities from parent to child branch
        cls._branches[new_branch] = copy.deepcopy(cls._branches[parent])
        cls._parent_map[new_branch] = parent

        # Setup branch belief state
        cls._belief_states[new_branch] = copy.deepcopy(cls._belief_states[parent])
        cls._belief_states[new_branch].branch_id = new_branch
        cls._revision_engines[new_branch] = BeliefRevisionEngine(BeliefEngine(cls._belief_states[new_branch]))
        
        # Copy PKG
        cls._pkgs[new_branch] = copy.deepcopy(cls._pkgs[parent])

        log_event("branch_created", f"Created branch '{new_branch}' stemming from parent '{parent}'")
        return new_branch

    @classmethod
    def simulate_action(cls, branch_id: str, action: Dict[str, Any]) -> TransitionResult:
        """Run simulated transition step on branch. Returns TransitionResult."""
        if branch_id not in cls._branches:
            raise ValueError(f"Branch '{branch_id}' does not exist.")

        action_type = action.get("type", "unknown")
        success = True
        effects = {}
        predicted_states = {}

        # Mock action simulation logic
        if action_type == "degrade_cpu":
            # Simulate CPU load property change on SelfEntity
            for entity in cls._branches[branch_id].get("self", {}).values():
                entity.properties["cpu_load"] = 0.95
                predicted_states[f"{entity.entity_id}.cpu_load"] = 0.95
            effects["cpu"] = "degraded"
        elif action_type == "optimize_cost":
            for entity in cls._branches[branch_id].get("economic", {}).values():
                entity.properties["cost_per_query"] = 0.01
                predicted_states[f"{entity.entity_id}.cost_per_query"] = 0.01
            effects["cost"] = "optimized"
        else:
            success = False

        log_event("action_simulated", f"Simulated '{action_type}' on '{branch_id}' (success={success})")
        return TransitionResult(predicted_states=predicted_states, success=success, effects=effects)

    @classmethod
    def propose_merge(cls, branch_id: str) -> List[str]:
        """Generate candidate events from branch deltas. Returns proposed event IDs."""
        if branch_id not in cls._branches:
            raise ValueError(f"Branch '{branch_id}' does not exist.")

        parent = cls._parent_map.get(branch_id, "main")
        parent_branch = cls._branches[parent]
        current_branch = cls._branches[branch_id]

        proposed_event_ids = []

        # Find deltas by comparing entities
        for domain, entities in current_branch.items():
            for entity_id, entity in entities.items():
                parent_entity = parent_branch.get(domain, {}).get(entity_id)

                # Compute properties delta
                properties_delta = {}
                if parent_entity is None:
                    # Fresh entity added
                    properties_delta = copy.deepcopy(entity.properties)
                else:
                    for k, v in entity.properties.items():
                        if parent_entity.properties.get(k) != v:
                            properties_delta[k] = v

                if properties_delta:
                    event_id = f"event_{uuid.uuid4().hex[:8]}"
                    log = EventLog(
                        event_id=event_id,
                        timestamp=time.time(),
                        event_type="simulation_delta",
                        properties_delta=properties_delta,
                        source=branch_id
                    )
                    entity.history.append(log)
                    proposed_event_ids.append(event_id)

        log_event("merge_proposed", f"Branch '{branch_id}' proposed {len(proposed_event_ids)} candidate events.")
        return proposed_event_ids

    @classmethod
    def merge_branch(cls, branch_id: str) -> bool:
        """Merge simulation delta adjustments back into the Main World state via Bayesian belief updates."""
        if branch_id not in cls._branches:
            raise ValueError(f"Branch '{branch_id}' does not exist.")

        parent = cls._parent_map.get(branch_id, "main")
        parent_branch = cls._branches[parent]
        current_branch = cls._branches[branch_id]

        # Formulate ObservedState update from branch differences
        obs = ObservedState(state_id=f"merge_{branch_id}", branch_id=parent, timestamp=time.time())
        
        has_changes = False
        for domain, entities in current_branch.items():
            for entity_id, entity in entities.items():
                parent_entity = parent_branch.get(domain, {}).get(entity_id)

                for k, v in entity.properties.items():
                    if parent_entity is None or parent_entity.properties.get(k) != v:
                        # Construct a PropertyValue to submit as evidence
                        # We use source reliability = 0.85 since it comes from a simulation
                        from backend.core.cos.state_representation import EvidenceSource
                        src_sim = EvidenceSource(name=f"sim_{branch_id}", source_type="simulation", reliability=0.85)
                        
                        pv_incoming = PropertyValue(
                            value=v,
                            confidence=0.90,  # Simulation confidence
                            source=src_sim
                        )
                        obs.set_property(entity_id, k, pv_incoming)
                        has_changes = True

        if has_changes:
            # Process proposed simulation updates as evidence on the parent/main world belief engine!
            # Never directly overwrite beliefs; let the Bayesian fusion engine decide the new posteriors!
            rev_engine = cls._revision_engines.get(parent)
            if rev_engine:
                # Start transaction for safe atomic belief updates
                rev_engine.tms.begin(rev_engine.belief_engine.state)
                try:
                    rev_engine.belief_engine.process_observation(obs)
                    # Sync parent branch entities with updated belief states
                    for entity_id, props in obs.entity_states.items():
                        for k in props.keys():
                            updated_pv = rev_engine.belief_engine.state.get_property(entity_id, k)
                            if updated_pv:
                                # Find entity in parent branch and set property
                                for d in parent_branch.keys():
                                    if entity_id in parent_branch[d]:
                                        parent_branch[d][entity_id].properties[k] = updated_pv.value
                    
                    rev_engine.tms.commit()
                    # Sync to PKG
                    cls.sync_branch_to_pkg(parent)
                except Exception as e:
                    logger.error(f"Failed to merge branch: {e}")
                    rev_engine.tms.rollback(rev_engine.belief_engine.state)
                    return False

        log_event("branch_merged", f"Branch '{branch_id}' deltas successfully fused back into parent '{parent}' using Bayesian updates.")
        return True


# Initialize Coordinator Main Branch
WorldModelCoordinator.reset()
