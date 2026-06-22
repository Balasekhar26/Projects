"""Proposal Governance Layer (Layer 10/11 - Step 6.4.1).

Enforces safety boundaries, controls proposal volume, manages expiration,
tracks performance execution, and computes semantic similarity checks.
"""

from __future__ import annotations

import json
import math
import time
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED_GATE_1 = "approved_gate_1"
    LAB_TESTING = "lab_testing"
    BENCHMARKING = "benchmarking"
    APPROVED_GATE_2 = "approved_gate_2"
    CANARY = "canary"
    DEPLOYED = "deployed"
    EXPIRED = "expired"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    NEEDS_REVISION = "needs_revision"
    SANDBOX_APPROVED = "sandbox_approved"


def _track_records_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "track_records.json"


def _budget_config_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "budget_config.json"


# -- 1. Immutable Protected Core Registry ------------------------------------
class ProtectedCoreRegistry:
    # IMMUTABLE: Hardcoded in the source code. Cannot be modified by proposals.
    PROTECTED_MODULES = {
        "validators",
        "policy_engine",
        "consensus_engine",
        "value_engine",
        "benchmark_arena",
        "reliability_monitor",
        "proposal_governance",
        "approval_gates",
        "deployment_controls",
        "deployment_controller",
        "reliability",
        "execution_policy",
        "main",
        "main.py",
    }

    _cached_graph = None

    @classmethod
    def is_protected(cls, module_name: str) -> bool:
        """Returns True if the module name belongs to the protected core."""
        name_clean = module_name.strip().lower()
        if name_clean.endswith(".py"):
            name_clean = name_clean[:-3]
        return name_clean in cls.PROTECTED_MODULES

    @classmethod
    def build_dependency_graph(cls) -> dict[str, set[str]]:
        """Scans all python files in backend/core and returns a dict mapping
        module_name -> set of imported module names from backend.core.* or local.
        """
        if cls._cached_graph is not None:
            return cls._cached_graph

        import ast
        from pathlib import Path
        
        core_dir = Path(__file__).parent
        graph = {}
        if not core_dir.exists():
            return {}

        for py_path in core_dir.glob("*.py"):
            mod_name = py_path.stem
            graph[mod_name] = set()
            try:
                content = py_path.read_text(encoding="utf-8")
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            base_imported = cls._clean_import_name(alias.name)
                            if base_imported:
                                graph[mod_name].add(base_imported)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            base_imported = cls._clean_import_name(node.module)
                            if base_imported:
                                graph[mod_name].add(base_imported)
            except Exception:
                pass
        cls._cached_graph = graph
        return graph

    @classmethod
    def _clean_import_name(cls, name: str) -> str | None:
        parts = name.split(".")
        if "backend" in parts:
            idx = parts.index("backend")
            if idx + 2 < len(parts) and parts[idx + 1] == "core":
                return parts[idx + 2]
        if "core" in parts:
            idx = parts.index("core")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        if len(parts) == 1:
            return parts[0]
        return None

    @classmethod
    def is_transitively_protected(cls, target_module: str) -> bool:
        """Returns True if the target module is transitively imported by any protected module."""
        target_clean = target_module.strip().lower()
        if target_clean.endswith(".py"):
            target_clean = target_clean[:-3]

        if cls.is_protected(target_clean):
            return True

        graph = cls.build_dependency_graph()
        
        visited = set()
        queue = [mod for mod in cls.PROTECTED_MODULES if mod in graph]
        
        while queue:
            curr = queue.pop(0)
            if curr == target_clean:
                return True
            if curr not in visited:
                visited.add(curr)
                for imp in graph.get(curr, set()):
                    if imp not in visited:
                        queue.append(imp)
        return False

    @classmethod
    def check_affected_modules(cls, affected_modules: list[str]) -> bool:
        """Returns True if any listed affected module is transitively in the protected core."""
        return any(cls.is_transitively_protected(m) for m in affected_modules)


# -- 2. Proposal Integrity Scorer (PIS) ---------------------------------------
class ProposalIntegrityScorer:
    @classmethod
    def compute_pis(cls, title: str, proposal: str, affected_modules: list[str]) -> float:
        """Computes Proposal Integrity Score (PIS) [0, 100].

        Returns 0.0 if the proposal touches or attempts to modify evaluation,
        benchmarking, or governance paths.
        """
        text = f"{title} {proposal}".lower()
        
        # Immediate veto keywords
        veto_keywords = {
            "modify validator", "bypass validator", "disable validator",
            "modify policy", "bypass policy", "disable policy",
            "modify consensus", "bypass consensus", "disable consensus",
            "modify value engine", "bypass value engine", "disable value engine",
            "modify benchmark", "bypass benchmark", "disable benchmark",
            "modify approval", "bypass approval", "disable approval",
            "modify deployment", "bypass deployment", "disable deployment",
            "modify reliability", "bypass reliability", "disable reliability"
        }

        # Check affected modules list
        for mod in affected_modules:
            if ProtectedCoreRegistry.is_protected(mod):
                return 0.0

        # Check keyword scan
        for keyword in veto_keywords:
            if keyword in text:
                return 0.0

        return 100.0


# -- 3. Proposal Budget Manager --------------------------------------------
class ProposalBudgetManager:
    DEFAULT_DAILY_LIMIT = 5

    @classmethod
    def get_budget_limit(cls) -> int:
        """Determines daily proposal budget dynamically using historical PQS and ROI."""
        path = _budget_config_path()
        base_limit = cls.DEFAULT_DAILY_LIMIT
        if path.exists():
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
                base_limit = config.get("daily_limit", cls.DEFAULT_DAILY_LIMIT)
            except Exception:
                pass

        # 1. Pipeline ROI check (Throttles by 75% if ROI is negative and we have >= 5 runs)
        records = TrackRecordStore.get_track_records()
        total_runs = sum(1 for r in records if r.get("sandbox_result") or r.get("benchmark_result") or r.get("production_result"))
        roi = TrackRecordStore.get_pipeline_roi()
        if total_runs >= 5 and roi < 0.0:
            return max(1, int(base_limit * 0.25))  # Throttle pipeline by 75%

        # 2. PQS check
        pqs = TrackRecordStore.get_pqs()
        if pqs > 0.7:
            return int(base_limit * 1.20)  # +20%
        elif pqs < 0.3:
            return int(base_limit * 0.50)  # -50%

        return base_limit

    @classmethod
    def set_budget_override(cls, daily_limit: int) -> None:
        """Persists a manual override for the proposal budget limit."""
        path = _budget_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        config = {"daily_limit": max(1, daily_limit)}
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")


# -- 4. Proposal Expiration Manager ----------------------------------------
class ProposalExpirationManager:
    @classmethod
    def is_expired(cls, created_at: float, lifespan_days: int = 30) -> bool:
        """Returns True if a proposal age exceeds the maximum lifespan."""
        age_seconds = time.time() - created_at
        lifespan_seconds = lifespan_days * 24 * 3600
        return age_seconds > lifespan_seconds

    @classmethod
    def expire_stale_proposals(cls, proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Updates stale pending/draft proposals to 'expired' status."""
        modified = False
        for prop in proposals:
            status = prop.get("status")
            if status in ("pending", "draft") and cls.is_expired(prop.get("created_at", 0.0)):
                prop["status"] = ProposalStatus.EXPIRED.value
                prop["expired_at"] = time.time()
                modified = True
        return proposals


# -- 5. Track Record Store --------------------------------------------------
class TrackRecordStore:
    @classmethod
    def _load_records(cls) -> list[dict[str, Any]]:
        path = _track_records_path()
        if not path.exists():
            return []
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
            return records if isinstance(records, list) else []
        except Exception:
            return []

    @classmethod
    def _save_records(cls, records: list[dict[str, Any]]) -> None:
        path = _track_records_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    @classmethod
    def record_run(
        cls,
        proposal_id: str,
        stage: str,  # "sandbox", "benchmark", "production"
        success: bool,
        metrics: dict[str, Any] | None = None,
        research_cost: float = 10.0,
        predicted_gain: float | None = None,
        actual_sandbox_gain: float | None = None,
        actual_production_gain: float | None = None,
    ) -> dict[str, Any]:
        """Logs execution result for a proposal stage to track records database."""
        records = cls._load_records()

        # Find or create record
        record = None
        for r in records:
            if r.get("proposal_id") == proposal_id:
                record = r
                break

        if record is None:
            record = {
                "proposal_id": proposal_id,
                "sandbox_result": None,
                "benchmark_result": None,
                "production_result": None,
                "research_cost": research_cost,
                "predicted_gain": None,
                "actual_sandbox_gain": None,
                "actual_production_gain": None,
                "updated_at": time.time(),
            }
            records.append(record)

        stage_key = f"{stage}_result"
        record[stage_key] = {
            "success": success,
            "metrics": metrics or {},
            "timestamp": time.time(),
        }
        record["updated_at"] = time.time()

        # Update research cost if not set or default
        if record.get("research_cost", 0.0) == 10.0 and research_cost != 10.0:
            record["research_cost"] = research_cost

        # 1. Update predicted_gain
        if predicted_gain is not None:
            record["predicted_gain"] = predicted_gain
        elif record.get("predicted_gain") is None:
            try:
                from backend.core.proposal_engine import ProposalEngine
                proposals = ProposalEngine.list_proposals()
                for p in proposals:
                    if p.get("id") == proposal_id:
                        record["predicted_gain"] = p.get("expected_gain")
                        break
            except Exception:
                pass
            if record.get("predicted_gain") is None and metrics:
                record["predicted_gain"] = metrics.get("predicted_gain") or metrics.get("expected_gain")

        # 2. Update actual_sandbox_gain
        if actual_sandbox_gain is not None:
            record["actual_sandbox_gain"] = actual_sandbox_gain
        elif stage == "sandbox" and metrics:
            record["actual_sandbox_gain"] = metrics.get("actual_sandbox_gain") or metrics.get("gain") or metrics.get("actual_gain")

        # 3. Update actual_production_gain
        if actual_production_gain is not None:
            record["actual_production_gain"] = actual_production_gain
        elif stage == "production" and metrics:
            record["actual_production_gain"] = metrics.get("actual_production_gain") or metrics.get("gain") or metrics.get("actual_gain")

        # 4. Calculate individual PVS (Production Value Score)
        gain = record.get("actual_production_gain")
        cost = record.get("research_cost", 10.0)
        if gain is not None and cost > 0:
            record["pvs"] = round(float(gain) / float(cost), 4)

        cls._save_records(records)
        return record

    @classmethod
    def record_human_review(
        cls,
        proposal_id: str,
        gate: str,  # "gate_1", "gate_2"
        approved: bool,
        review_time_seconds: float,
    ) -> dict[str, Any]:
        """Logs human Gate 1 / Gate 2 reviews."""
        records = cls._load_records()

        record = None
        for r in records:
            if r.get("proposal_id") == proposal_id:
                record = r
                break

        if record is None:
            record = {
                "proposal_id": proposal_id,
                "sandbox_result": None,
                "benchmark_result": None,
                "production_result": None,
                "research_cost": 10.0,
                "predicted_gain": None,
                "actual_sandbox_gain": None,
                "actual_production_gain": None,
                "updated_at": time.time(),
            }
            records.append(record)

        review_key = f"{gate}_review"
        record[review_key] = {
            "approved": approved,
            "review_time_seconds": review_time_seconds,
            "timestamp": time.time(),
        }
        record["updated_at"] = time.time()

        cls._save_records(records)
        return record

    @classmethod
    def get_pqs(cls) -> float:
        """Calculates Proposal Quality Score (PQS) = successful / total proposals."""
        records = cls._load_records()
        if not records:
            return 0.5
        
        successful = 0
        total = 0
        for r in records:
            for stage in ("sandbox", "benchmark", "production"):
                res = r.get(f"{stage}_result")
                if res:
                    total += 1
                    if res.get("success"):
                        successful += 1
        return successful / total if total > 0 else 1.0

    @classmethod
    def get_pipeline_roi(cls) -> float:
        """Calculates Pipeline ROI = production benefits - research costs."""
        records = cls._load_records()
        total_benefit = 0.0
        total_cost = 0.0

        for r in records:
            # Add research cost
            total_cost += r.get("research_cost", 10.0)
            
            # Add production benefit (gain metric)
            prod = r.get("production_result")
            if prod and prod.get("success"):
                benefit = r.get("actual_production_gain")
                if benefit is None:
                    metrics = prod.get("metrics", {})
                    benefit = metrics.get("gain") or metrics.get("actual_gain") or metrics.get("actual_production_gain") or 0.0
                total_benefit += float(benefit)

        return total_benefit - total_cost

    @classmethod
    def get_gra_score(cls) -> float:
        """Calculates Gain Realization Accuracy (GRA).
        Computes RMSE between predicted_gain and actual_production_gain.
        Returns a score in [0.0, 1.0], where 1.0 is perfect prediction.
        """
        records = cls._load_records()
        valid_pairs = []
        for r in records:
            pred = r.get("predicted_gain")
            act = r.get("actual_production_gain")
            if pred is not None and act is not None:
                valid_pairs.append((float(pred), float(act)))
        
        if not valid_pairs:
            return 1.0
            
        mse = sum((pred - act) ** 2 for pred, act in valid_pairs) / len(valid_pairs)
        rmse = math.sqrt(mse)
        return round(1.0 / (1.0 + rmse), 4)

    @classmethod
    def get_pipeline_pvs(cls) -> float:
        """Calculates Pipeline Production Value Score (PVS) = total production gain / total research cost."""
        records = cls._load_records()
        total_gain = 0.0
        total_cost = 0.0

        for r in records:
            total_cost += r.get("research_cost", 10.0)
            gain = r.get("actual_production_gain")
            if gain is not None:
                total_gain += float(gain)
            else:
                prod = r.get("production_result")
                if prod and prod.get("success"):
                    metrics = prod.get("metrics", {})
                    gain = metrics.get("gain") or metrics.get("actual_gain") or metrics.get("actual_production_gain") or 0.0
                    total_gain += float(gain)

        return round(total_gain / total_cost, 4) if total_cost > 0 else 0.0

    @classmethod
    def get_improvement_yield(cls) -> float:
        """Calculates Improvement Yield (IY) = successful production deployments / approved proposals (Gate 1 approved)."""
        records = cls._load_records()
        if not records:
            return 1.0

        approved_count = 0
        production_success_count = 0

        for r in records:
            # Check if it was approved by Gate 1
            gate1 = r.get("gate_1_review")
            if gate1 and gate1.get("approved"):
                approved_count += 1
            
            # Check if production succeeded
            prod = r.get("production_result")
            if prod and prod.get("success"):
                production_success_count += 1

        if approved_count == 0:
            return 1.0
        return round(production_success_count / approved_count, 4)

    @classmethod
    def get_prr(cls) -> float:
        """Calculates Proposal Rejection Rate (PRR) = rejected proposals / total proposals."""
        try:
            from backend.core.proposal_engine import ProposalEngine
            proposals = ProposalEngine.list_proposals()
            if not proposals:
                return 0.0
            rejected = sum(1 for p in proposals if p.get("status") == ProposalStatus.REJECTED.value)
            return round(rejected / len(proposals), 4)
        except Exception:
            return 0.0

    @classmethod
    def get_nkhr(cls) -> float:
        """Calculates Negative Knowledge Hit Rate (NKHR) = blocked by negative knowledge / total proposals."""
        try:
            from backend.core.proposal_engine import ProposalEngine
            proposals = ProposalEngine.list_proposals()
            if not proposals:
                return 0.0
            blocked = sum(
                1 for p in proposals
                if p.get("status") == ProposalStatus.REJECTED.value
                and any("Negative-Knowledge" in r or "negative knowledge" in r.lower() for r in p.get("reasons", []))
            )
            return round(blocked / len(proposals), 4)
        except Exception:
            return 0.0

    @classmethod
    def get_rf(cls) -> float:
        """Calculates Rollback Frequency (RF) = rollbacks / total deployment attempts (deployed + rollbacks)."""
        from backend.core.config import runtime_data_root
        path = runtime_data_root() / "backend" / "data" / "canary_status.json"
        if not path.exists():
            return 0.0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rollbacks = sum(1 for s in data if s.get("current_step") == "ROLLBACK")
            records = cls._load_records()
            deployed = sum(1 for r in records if r.get("production_result") and r["production_result"].get("success"))
            attempts = deployed + rollbacks
            return round(rollbacks / attempts, 4) if attempts > 0 else 0.0
        except Exception:
            return 0.0

    @classmethod
    def get_track_records(cls) -> list[dict[str, Any]]:
        """Retrieves all track records."""
        return cls._load_records()

    @classmethod
    def get_human_burden_score(cls) -> dict[str, Any]:
        """Calculates human attention burden metrics."""
        records = cls._load_records()
        reviewed_count = 0
        rejected_count = 0
        total_time = 0.0

        for r in records:
            for gate in ("gate_1", "gate_2"):
                rev = r.get(f"{gate}_review")
                if rev:
                    reviewed_count += 1
                    total_time += rev.get("review_time_seconds", 0.0)
                    if not rev.get("approved"):
                        rejected_count += 1

        avg_time = total_time / reviewed_count if reviewed_count > 0 else 0.0
        # Burden Score scales higher if we have a lot of rejections relative to total reviews
        burden_score = (reviewed_count / max(1, reviewed_count - rejected_count)) * (avg_time / 60.0) if reviewed_count > 0 else 0.0

        return {
            "reviewed_count": reviewed_count,
            "rejected_count": rejected_count,
            "average_review_time_seconds": round(avg_time, 2),
            "human_burden_score": round(burden_score, 4),
        }


# -- 6. Semantic Negative-Knowledge Matcher ---------------------------------
class SemanticNegativeKnowledgeMatcher:
    @classmethod
    def check_semantic_duplicate(
        cls,
        candidate_text: str,
        negative_knowledge_entries: list[dict[str, Any]],
    ) -> tuple[str, float, str]:
        """Classifies similarity against historical failures into confidence bands:

        Returns:
            match_level: "block" (>= 0.90), "review" (0.80 - 0.90), "warning" (0.70 - 0.80), "ignore" (< 0.70)
            similarity: highest cosine similarity score
            reason: reason description
        """
        if not negative_knowledge_entries:
            return "ignore", 0.0, ""

        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            ef = DefaultEmbeddingFunction()
            candidate_vector = ef([candidate_text])[0]
        except Exception:
            return cls._jaccard_fallback(candidate_text, negative_knowledge_entries)

        best_score = 0.0
        best_reason = ""
        best_match_title = ""

        # Compute cosine similarities
        for entry in negative_knowledge_entries:
            title = entry.get("title", "")
            reason = entry.get("reason", "")
            
            # Compare both title-to-title and title-to-description for matching
            for target in (title, f"{title} {reason}"):
                try:
                    entry_vector = ef([target])[0]
                    similarity = cls._cosine_similarity(candidate_vector, entry_vector)
                    if similarity > best_score:
                        best_score = similarity
                        best_reason = reason
                        best_match_title = title
                except Exception:
                    continue

        return cls._map_score_to_band(best_score, best_match_title, best_reason)

    @classmethod
    def _cosine_similarity(cls, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    @classmethod
    def _map_score_to_band(cls, score: float, title: str, reason: str) -> tuple[str, float, str]:
        if score >= 0.90:
            return "block", score, f"Matches failure '{title}' (Reason: {reason})"
        elif score >= 0.80:
            return "review", score, f"Matches failure '{title}' (Reason: {reason})"
        elif score >= 0.70:
            return "warning", score, f"Matches failure '{title}' (Reason: {reason})"
        return "ignore", score, ""

    @classmethod
    def _jaccard_fallback(
        cls,
        candidate_text: str,
        negative_knowledge_entries: list[dict[str, Any]],
    ) -> tuple[str, float, str]:
        best_score = 0.0
        best_reason = ""
        best_match_title = ""

        cand_words = set(candidate_text.lower().split())

        for entry in negative_knowledge_entries:
            title = entry.get("title", "")
            reason = entry.get("reason", "")
            
            for target in (title, f"{title} {reason}"):
                comp_words = set(target.lower().split())
                intersection = cand_words.intersection(comp_words)
                union = cand_words.union(comp_words)
                jaccard = len(intersection) / len(union) if union else 0.0

                if jaccard > best_score:
                    best_score = jaccard
                    best_reason = reason
                    best_match_title = title

        # Map Jaccard score to bands
        if best_score >= 0.45:
            return "block", best_score, f"Matches failure '{best_match_title}' (Reason: {best_reason})"
        elif best_score >= 0.35:
            return "review", best_score, f"Matches failure '{best_match_title}' (Reason: {best_reason})"
        elif best_score >= 0.25:
            return "warning", best_score, f"Matches failure '{best_match_title}' (Reason: {best_reason})"
        return "ignore", best_score, ""


# -- 7. Improvement Registry --------------------------------------------------
def _improvement_registry_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "improvement_registry.json"


class ImprovementRegistry:
    import threading
    _lock = threading.RLock()

    @classmethod
    def _load_registry(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _improvement_registry_path()
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return cls.recover_corrupted_ledger()

    @classmethod
    def _save_registry(cls, data: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _improvement_registry_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def recover_corrupted_ledger(cls) -> list[dict[str, Any]]:
        """Recovers registry entries if JSON is corrupted, by backing up the file
        and rebuilding the entries from proposals and track records.
        """
        with cls._lock:
            path = _improvement_registry_path()
            if path.exists():
                backup_path = path.with_name(f"improvement_registry_corrupted_{int(time.time())}.json")
                try:
                    path.rename(backup_path)
                except Exception:
                    pass

            # Rebuild entries from scratch
            try:
                from backend.core.proposal_engine import ProposalEngine
                proposals = ProposalEngine.list_proposals()
                for prop in proposals:
                    prop_id = prop.get("id")
                    if prop_id:
                        cls.register_or_update(prop_id, proposal_dict=prop)
            except Exception:
                pass
            
            # Load the rebuilt list
            if not path.exists():
                return []
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    @classmethod
    def register_or_update(
        cls,
        proposal_id: str,
        final_outcome: str | None = None,
        proposal_dict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Appends a new state transition to the append-only Improvement Registry ledger."""
        with cls._lock:
            # Avoid circular imports
            from backend.core.proposal_engine import ProposalEngine
            from backend.core.proposal_governance import TrackRecordStore, ProposalStatus
            from backend.core.sandbox_lab import ArtifactStore
            from backend.core.deployment_advisor import CanaryReleaseCoordinator

            # 1. Resolve Proposal
            prop = proposal_dict
            if not prop:
                proposals = ProposalEngine.list_proposals()
                for p in proposals:
                    if p.get("id") == proposal_id:
                        prop = p
                        break
            
            # If still not found, check track records or create a mock template
            if not prop:
                records = TrackRecordStore.get_track_records()
                record = None
                for r in records:
                    if r.get("proposal_id") == proposal_id:
                        record = r
                        break
                
                prop = {
                    "id": proposal_id,
                    "title": f"Proposal {proposal_id}",
                    "problem": "Unknown problem",
                    "evidence": "No evidence logged",
                    "proposal": "No fix description logged",
                    "status": ProposalStatus.REJECTED.value if "rejected" in proposal_id else "pending",
                    "created_at": time.time(),
                    "confidence": 80,
                }
            
            # 2. Load Track Record
            records = TrackRecordStore.get_track_records()
            record = None
            for r in records:
                if r.get("proposal_id") == proposal_id:
                    record = r
                    break

            # 3. Load Sandbox PRS and experimental reports
            prs_score = None
            try:
                exps = ArtifactStore.load_experiments()
                for exp in exps:
                    if exp.get("package", {}).get("proposal_id") == proposal_id:
                        prs = exp.get("results", {}).get("prs_score")
                        if prs is not None:
                            prs_score = prs
                            break
            except Exception:
                pass

            # 4. Rollback status & Canary check
            rollback_status = "none"
            canary_result_val = None
            try:
                c_status = CanaryReleaseCoordinator.get_status(proposal_id)
                if c_status.get("current_step") == "ROLLBACK":
                    rollback_status = "rolled_back"
                    canary_result_val = {"success": False, "reason": c_status.get("anomaly", "Canary anomaly detected")}
                elif c_status.get("current_step") == "100%":
                    canary_result_val = {"success": True}
            except Exception:
                pass

            if final_outcome == "ROLLED_BACK":
                rollback_status = "rolled_back"
                if not canary_result_val:
                    canary_result_val = {"success": False, "reason": "Canary anomaly detected / Rolled back"}

            # 5. Resolve gains, GRA, and PVS
            predicted_gain = prop.get("expected_gain")
            sandbox_gain = None
            production_gain = None
            gra = None
            pvs_val = None
            research_cost = record.get("research_cost", 10.0) if record else 10.0

            if record:
                if record.get("predicted_gain") is not None:
                    predicted_gain = record.get("predicted_gain")
                sandbox_gain = record.get("actual_sandbox_gain")
                production_gain = record.get("actual_production_gain")
                
                # Compute GRA
                if predicted_gain is not None and production_gain is not None:
                    gra = round(1.0 / (1.0 + abs(float(predicted_gain) - float(production_gain))), 4)
                elif record.get("gra") is not None:
                    gra = record.get("gra")

            # 6. Resolve final_outcome if not passed
            prop_status = prop.get("status", "pending")
            if not final_outcome:
                if rollback_status == "rolled_back":
                    final_outcome = "ROLLED_BACK"
                elif prop_status == ProposalStatus.REJECTED.value:
                    if record and record.get("sandbox_result") and not record["sandbox_result"].get("success"):
                        final_outcome = "SANDBOX_FAILED"
                    elif record and record.get("benchmark_result") and not record["benchmark_result"].get("success"):
                        final_outcome = "BENCHMARK_FAILED"
                    elif rollback_status == "rolled_back" or (record and record.get("production_result") and not record["production_result"].get("success")):
                        final_outcome = "ROLLED_BACK"
                    else:
                        final_outcome = "REJECTED"
                elif prop_status == ProposalStatus.EXPIRED.value:
                    final_outcome = "EXPIRED"
                elif prop_status == ProposalStatus.DEPLOYED.value:
                    if record and record.get("production_result") and record["production_result"].get("success"):
                        final_outcome = "DEPLOYED_SUCCESSFUL"
                    else:
                        final_outcome = "DEPLOYED"
                elif prop_status == ProposalStatus.CANARY.value:
                    final_outcome = "DEPLOYED"
                else:
                    if record and record.get("sandbox_result") and not record["sandbox_result"].get("success"):
                        final_outcome = "SANDBOX_FAILED"
                    elif record and record.get("benchmark_result") and not record["benchmark_result"].get("success"):
                        final_outcome = "BENCHMARK_FAILED"
                    else:
                        final_outcome = "PROPOSED"

            # 7. Compute IQS
            iqs = None
            terminal_states = {
                "REJECTED": 0.0,
                "EXPIRED": 0.0,
                "SANDBOX_FAILED": 0.0,
                "BENCHMARK_FAILED": 0.0,
                "CANARY_FAILED": 0.0,
                "ROLLED_BACK": 0.0,
                "DEPLOYED_SUCCESSFUL": 1.0,
            }
            if final_outcome in terminal_states:
                confidence_prob = float(prop.get("confidence", 80)) / 100.0
                iqs = round(1.0 - (confidence_prob - terminal_states[final_outcome]) ** 2, 4)

            # 8. Compute individual entry PVS and IY
            if production_gain is not None and research_cost > 0.0:
                pvs_val = round(float(production_gain) / float(research_cost), 4)

            iy_val = None
            if final_outcome == "DEPLOYED_SUCCESSFUL":
                iy_val = 1.0
            elif final_outcome in terminal_states:
                iy_val = 0.0

            # 9. Negative Knowledge Hit check
            negative_knowledge_hit = False
            reasons = prop.get("reasons", [])
            if any("Negative-Knowledge" in r or "negative knowledge" in r.lower() for r in reasons):
                negative_knowledge_hit = True

            # 10. Build snapshot
            hypothesis = prop.get("hypothesis")
            if not hypothesis:
                hypothesis = f"Hypothesis: implementing the proposed fix will resolve the issue of '{prop.get('problem', '')}'."

            entry = {
                "improvement_id": f"imp_{proposal_id}",
                "proposal_id": proposal_id,
                "created_at": prop.get("created_at", time.time()),
                "problem": prop.get("problem", ""),
                "evidence": prop.get("evidence", ""),
                "hypothesis": hypothesis,
                "proposed_fix": prop.get("proposal", ""),
                "approval_status": prop_status,
                "sandbox_result": record.get("sandbox_result") if record else None,
                "benchmark_result": record.get("benchmark_result") if record else None,
                "canary_result": canary_result_val or (record.get("production_result") if record else None),
                "deployment_status": prop_status,
                "rollback_status": rollback_status,
                "negative_knowledge_hit": negative_knowledge_hit,
                "predicted_gain": predicted_gain,
                "sandbox_gain": sandbox_gain,
                "production_gain": production_gain,
                "IQS": iqs,
                "PRS": prs_score,
                "GRA": gra,
                "PVS": pvs_val,
                "IY": iy_val,
                "final_outcome": final_outcome,
                "timestamp": time.time(),
            }

            # Save to append-only registry
            registry = cls._load_registry()
            registry.append(entry)
            cls._save_registry(registry)

            return entry

    @classmethod
    def get_improvements(
        cls,
        status: str | None = None,
        from_time: float | None = None,
        to_time: float | None = None,
        proposal_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Returns consolidated latest states for unique improvements, applying filters."""
        with cls._lock:
            registry = cls._load_registry()
            
            # Group by improvement_id and keep the latest transition
            latest_map = {}
            for entry in registry:
                imp_id = entry["improvement_id"]
                latest_map[imp_id] = entry

            consolidated = list(latest_map.values())

            # Apply filters
            filtered = []
            for c in consolidated:
                if status and c.get("final_outcome") != status:
                    continue
                if proposal_id and c.get("proposal_id") != proposal_id:
                    continue
                if from_time and c.get("timestamp", 0.0) < from_time:
                    continue
                if to_time and c.get("timestamp", 0.0) > to_time:
                    continue
                filtered.append(c)

            # Sort by timestamp descending
            filtered.sort(key=lambda x: x.get("timestamp", 0.0), reverse=True)
            return filtered

    @classmethod
    def get_improvement_details(cls, improvement_id: str) -> list[dict[str, Any]]:
        """Returns the full sequence of transition events for the given improvement_id."""
        with cls._lock:
            registry = cls._load_registry()
            return [entry for entry in registry if entry["improvement_id"] == improvement_id]

    @classmethod
    def get_stats(cls) -> dict[str, Any]:
        """Computes summary statistics across all unique improvements."""
        with cls._lock:
            improvements = cls.get_improvements()
            total = len(improvements)
            
            successful = sum(1 for imp in improvements if imp.get("final_outcome") == "DEPLOYED_SUCCESSFUL")
            rejected = sum(1 for imp in improvements if imp.get("final_outcome") == "REJECTED")
            rolled_back = sum(1 for imp in improvements if imp.get("final_outcome") == "ROLLED_BACK")
            
            lab_or_deploy_states = {"SANDBOX_FAILED", "BENCHMARK_FAILED", "CANARY_FAILED", "ROLLED_BACK", "DEPLOYED", "DEPLOYED_SUCCESSFUL"}
            deployments_attempted = sum(1 for imp in improvements if imp.get("final_outcome") in lab_or_deploy_states)
            
            deployment_success_rate = 0.0
            if deployments_attempted > 0:
                deployment_success_rate = round(successful / deployments_attempted, 4)

            # prr
            prr = round(rejected / total, 4) if total > 0 else 0.0

            # nkhr
            nk_hits = sum(1 for imp in improvements if imp.get("negative_knowledge_hit"))
            nkhr = round(nk_hits / total, 4) if total > 0 else 0.0

            # rf
            rf = round(rolled_back / deployments_attempted, 4) if deployments_attempted > 0 else 0.0

            # iy
            iy = round(successful / total, 4) if total > 0 else 0.0

            gra_vals = [imp["GRA"] for imp in improvements if imp.get("GRA") is not None]
            avg_gra = round(sum(gra_vals) / len(gra_vals), 4) if gra_vals else 0.0

            iqs_vals = [imp["IQS"] for imp in improvements if imp.get("IQS") is not None]
            avg_iqs = round(sum(iqs_vals) / len(iqs_vals), 4) if iqs_vals else 0.0

            pvs_vals = [imp["PVS"] for imp in improvements if imp.get("PVS") is not None]
            avg_pvs = round(sum(pvs_vals) / len(pvs_vals), 4) if pvs_vals else 0.0

            prs_vals = [imp["PRS"] for imp in improvements if imp.get("PRS") is not None]
            avg_prs = round(sum(prs_vals) / len(prs_vals), 4) if prs_vals else 0.0

            return {
                "total": total,
                "successful": successful,
                "rejected": rejected,
                "rolled_back": rolled_back,
                "deployment_success_rate": deployment_success_rate,
                "avg_gra": avg_gra,
                "avg_iqs": avg_iqs,
                "avg_pvs": avg_pvs,
                "avg_prs": avg_prs,
                "pipeline_iy": iy,
                "pipeline_prr": prr,
                "pipeline_nkhr": nkhr,
                "pipeline_rf": rf,
            }

