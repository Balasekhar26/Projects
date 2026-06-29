"""Belief Management Component 11: Bayesian Belief Coordinator (Program 5C).

Bridges the exact Bayesian Network inference engine with the persistent SQLite belief store.
Automatically maps belief dependency chains to conditional probability tables.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.core.beliefs.belief import Belief, BeliefDependency
from backend.core.beliefs.belief_store import BeliefStore
from backend.core.beliefs.bayesian_engine import BayesianBeliefEngine, BayesianNode

logger = logging.getLogger(__name__)


class BayesianBeliefCoordinator:
    """Coordinates Bayesian network generation and posterior updates for stored beliefs."""

    def __init__(self, store: BeliefStore) -> None:
        self._store = store
        self._engine = BayesianBeliefEngine()

    @property
    def engine(self) -> BayesianBeliefEngine:
        return self._engine

    def build_network_from_store(self) -> None:
        """Loads all active beliefs and dependencies from the SQLite store to construct the Bayesian Network."""
        self._engine = BayesianBeliefEngine()  # Reset
        beliefs = self._store.list_beliefs()
        
        # Sort beliefs topologically using dependencies to ensure parent nodes are added first
        added_nodes: List[str] = []
        pending_beliefs = list(beliefs)

        # Loop until all nodes that can be resolved are added to the network
        iterations = 0
        max_iterations = len(beliefs) * 2
        while pending_beliefs and iterations < max_iterations:
            iterations += 1
            b = pending_beliefs.pop(0)
            
            # Retrieve parent dependencies
            parent_deps = self._store.get_parent_dependencies(b.belief_id)
            parent_ids = [p.parent_belief_id for p in parent_deps]
            dep_types = [p.dependency_type for p in parent_deps]

            # Check if all parents have already been added to the network
            if all(pid in added_nodes for pid in parent_ids):
                # Parents resolved: build node
                # Base CPT
                if not parent_ids:
                    # Prior probability from base confidence
                    cpt = {(): b.confidence}
                else:
                    cpt = self._engine.generate_default_cpt(parent_ids, dep_types)

                node = BayesianNode(
                    node_id=b.belief_id,
                    parents=parent_ids,
                    cpt=cpt,
                )
                self._engine.network.add_node(node)
                added_nodes.append(b.belief_id)

                # Set evidence state if it's highly believed or refuted/retracted
                if b.confidence >= 0.90:
                    self._engine.set_evidence(b.belief_id, True)
                elif b.confidence <= 0.10:
                    self._engine.set_evidence(b.belief_id, False)
            else:
                # Parents not yet added: requeue this belief
                pending_beliefs.append(b)

    def calculate_posterior(self, belief_id: str) -> float:
        """Computes the posterior probability of a belief given current evidence states."""
        # Ensure network is built
        self.build_network_from_store()
        
        if belief_id not in self._engine.network.nodes:
            logger.warning("Belief '%s' not mapped in the Bayesian Network.", belief_id)
            # Return prior confidence fallback
            b = self._store.get_belief(belief_id)
            return b.confidence if b else 0.5

        return self._engine.network.query(belief_id, self._engine.evidence)

    def propagate_posteriors(self) -> Dict[str, float]:
        """Calculates and returns posterior probabilities for all registered beliefs."""
        self.build_network_from_store()
        posteriors = {}
        for belief_id in self._engine.network.nodes:
            posteriors[belief_id] = self._engine.network.query(belief_id, self._engine.evidence)
        return posteriors
