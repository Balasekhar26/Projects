"""Reflection Engine (Layer 8 component).

Analyzes logs and execution traces, performs significance checks, and proposes reflections.
Also contains Phase 4 JSON-based reflection manager for backward compatibility and API endpoints.
"""

from __future__ import annotations

import json
import sqlite3
import re
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.model_router import ask_model
from backend.core.logger import log_event
from backend.core.reflection_memory import ReflectionMemory
from backend.core.config import load_config, runtime_data_root


def _path() -> Path:
    return runtime_data_root() / "backend" / "data" / "reflections.json"


_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class ReflectionCategory(str, Enum):
    RETRIEVAL = "retrieval"
    REASONING = "reasoning"
    TOOLING = "tooling"
    ALIGNMENT = "alignment"
    SAFETY = "safety"
    PERFORMANCE = "performance"
    SUCCESS = "success"

    @classmethod
    def coerce(cls, value: "ReflectionCategory | str") -> "ReflectionCategory":
        return value if isinstance(value, cls) else cls(str(value).strip().lower())


class ReflectionStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ReflectionEngine:
    """Reflection Engine (Layer 8 component).

    Responsible for analyzing logs and execution traces, performing significance checks,
    and invoking the model to safely generate improvement proposals under governance guidelines.
    Also handles Phase 4 JSON-backed persistent observations.
    """

    # --- Layer 8 Significance Evaluation and Proposals ---

    @classmethod
    def evaluate_significance(cls, logs_text: str) -> dict[str, Any]:
        """Performs a deterministic significance evaluation on raw log traces.
        
        Analyzes tool exit codes, exception counts, explicit error matches,
        recent tool benchmark rejections, and workflow run failures.
        """
        # Parse common failure indicators:
        # Non-zero exit codes: e.g. "exit_code=1" or similar
        exit_code_failures = len(re.findall(r"exit_code=[1-9]", logs_text))
        
        # Exception patterns
        exceptions = len(re.findall(r"(?i)\b(exception|failed|error|runtimeerror|valueerror|connectionerror)\b", logs_text))
        
        # Thumbs down / user rejection indicators
        thumbs_down = len(re.findall(r"(?i)\b(thumbs down|user rejected|thumbs-down|bad response)\b", logs_text))
        
        total_runs = len(re.findall(r"(?i)\b(run_task|session_start|execute_command)\b", logs_text)) or 1
        
        error_rate = (exit_code_failures + exceptions + thumbs_down) / total_runs
        
        # Read recent tool benchmark rejections/deprecations/rollbacks (Step 7.11 closed-loop)
        recent_rejections = 0
        rejected_tools = []
        try:
            from backend.core.benchmark_arena import BenchmarkArena
            tool_history = BenchmarkArena.load_tool_history()
            for r in tool_history[-10:]:
                if r.get("decision") in {"DEPRECATE", "ROLLBACK", "REJECT_VERSION"}:
                    recent_rejections += 1
                    rejected_tools.append(f"{r.get('tool')}:{r.get('candidate')} ({r.get('decision')})")
        except Exception:
            pass

        # Read recent workflow failures/rollbacks (Workflow Memory closed-loop)
        wf_failures = 0
        try:
            from backend.core.workflow_memory import WorkflowMemory
            recent_wf = WorkflowMemory.get_recent_workflow_runs(limit=10)
            wf_failures = sum(1 for w in recent_wf if not w.get("success"))
        except Exception:
            pass
            
        # Read goal calibration stats (Step 8.1 closed-loop)
        goal_block_rate = 0.0
        try:
            from backend.core.learning_dashboard import LearningDashboard
            goal_stats = LearningDashboard.goal_calibration_panel()
            goal_block_rate = goal_stats.get("goal_block_rate", 0.0)
        except Exception:
            pass

        actionable = (
            exit_code_failures > 0 
            or exceptions > 3 
            or thumbs_down > 0 
            or error_rate > 0.05 
            or recent_rejections > 0 
            or wf_failures > 0
            or goal_block_rate > 0.25
        )
        
        return {
            "exit_code_failures": exit_code_failures,
            "exceptions": exceptions,
            "thumbs_down": thumbs_down,
            "total_runs": total_runs,
            "error_rate": error_rate,
            "recent_tool_rejections": recent_rejections,
            "rejected_tools": rejected_tools,
            "recent_workflow_failures": wf_failures,
            "goal_block_rate": goal_block_rate,
            "actionable": actionable
        }

    @classmethod
    def analyze_and_propose(cls, logs_text: str, source_window_days: int = 7) -> str | None:
        """Parses interaction logs, runs significance checks, and proposes a reflection candidate.
        
        Returns the created reflection ID, or None if no actionable issue was found.
        """
        sig = cls.evaluate_significance(logs_text)
        
        # Trigger automated belief update
        try:
            from backend.core.human_memory import HumanMemory
            if sig["exit_code_failures"] > 0 or sig["exceptions"] > 3:
                HumanMemory.upsert_belief(
                    key="system_stability_status",
                    value="LOW_RELIABILITY_WARNING: Recent logs show multiple exceptions or non-zero exits.",
                    confidence=0.85
                )
            else:
                HumanMemory.upsert_belief(
                    key="system_stability_status",
                    value="HIGH_RELIABILITY: Systems are running clean without anomalous exceptions.",
                    confidence=0.95
                )
        except Exception as e:
            log_event(f"ReflectionEngine: failed to update active belief: {e}")
            
        # If no significant issues exist, do not generate proposals (avoids manufactured problems)
        if not sig["actionable"]:
            log_event("reflection_engine: no significant actionable issue detected in logs.")
            return None
            
        # Invoke model with a clean prompt requesting a structured JSON response
        prompt = (
            f"Analyze the following execution logs and identify the root cause of failures.\n"
            f"--- LOGS ---\n{logs_text[:4000]}\n------------\n\n"
            f"--- TELEMETRY CLOSED-LOOP CONTEXT ---\n"
            f"- Recent workflow failures: {sig['recent_workflow_failures']}\n"
            f"- Recent tool benchmark rejections: {sig['recent_tool_rejections']} ({', '.join(sig['rejected_tools'])})\n"
            f"-------------------------------------\n\n"
            f"Requirements:\n"
            f"1. Never propose self-modification of source code files.\n"
            f"2. Propose only behavior, retrieval, prompt, or tool parameter improvements.\n"
            f"3. Respond strictly with a JSON object containing these keys:\n"
            f"   - 'category': one of 'RETRIEVAL', 'REASONING', 'TOOLING', 'ALIGNMENT', 'SAFETY', 'PERFORMANCE', 'SUCCESS'\n"
            f"   - 'problem': clear explanation of the failure\n"
            f"   - 'cause': underlying root cause\n"
            f"   - 'improvement': proposed prompt or parameter change proposal (without modifying python files)\n"
            f"   - 'confidence': confidence score between 0.0 and 1.0\n"
            f"4. If nothing is actionable, return the category 'SUCCESS' and empty strings for other fields."
        )
        
        try:
            response = ask_model(prompt, role="coder")
            
            # Simple JSON extraction in case model returned extra markdown backticks
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                log_event("reflection_engine: failed to parse JSON from LLM response. Using deterministic fallback.")
                return cls._create_fallback_reflection(sig, source_window_days)
                
            data = json.loads(json_match.group(0))
            category = data.get("category", "PERFORMANCE").strip().upper()
            problem = data.get("problem", "Log errors detected").strip()
            cause = data.get("cause", "Exceptions / non-zero exits in logs").strip()
            improvement = data.get("improvement", "Improve search parameters or retry limits").strip()
            confidence = float(data.get("confidence", 0.7))
            
            if category == "SUCCESS" or not problem or problem.lower() == "none":
                return None
                
            # Submit to Reflection Memory (which handles deduplication)
            ref_id = ReflectionMemory.propose_reflection(
                category=category,
                problem=problem,
                cause=cause,
                improvement=improvement,
                confidence=confidence,
                source_window_days=source_window_days
            )
            return ref_id
            
        except Exception as exc:
            log_event(f"reflection_engine: LLM analysis failed: {exc}. Falling back to deterministic proposal.")
            return cls._create_fallback_reflection(sig, source_window_days)

            ref_id = ReflectionMemory.propose_reflection(
                category=category,
                problem=problem,
                cause=cause,
                improvement=improvement,
                confidence=confidence,
                source_window_days=source_window_days
            )
            return ref_id
            
        except Exception as exc:
            log_event(f"reflection_engine: LLM analysis failed: {exc}. Falling back to deterministic proposal.")
            return cls._create_fallback_reflection(sig, source_window_days)

    @classmethod
    def _create_fallback_reflection(cls, sig_data: dict, source_window_days: int) -> str:
        """Deterministic partial-capture fallback when LLM schema generation fails."""
        problem = f"Observed {sig_data['exceptions']} exceptions and {sig_data['exit_code_failures']} exit failures."
        cause = "System exit code mismatches or unhandled exceptions."
        improvement = "Increase retry delays or verify prerequisite environment settings."
        
        return ReflectionMemory.propose_reflection(
            category="PERFORMANCE",
            problem=problem,
            cause=cause,
            improvement=improvement,
            confidence=0.6,
            source_window_days=source_window_days
        )

    # =========================================================================
    # STEP 12: SELF-REFLECTION ANALYTICAL ENGINE
    # =========================================================================

    @staticmethod
    def calculate_wilson_score_interval(successes: int, total: int) -> tuple[float, float]:
        """RF1 Defense: Compute Wilson score interval bounds mathematically for 95% confidence level."""
        if total <= 0:
            return 0.0, 0.0
        z = 1.96  # 95% confidence level
        p_hat = successes / total
        denominator = 1 + (z**2 / total)
        center = p_hat + (z**2 / (2 * total))
        spread = z * ((p_hat * (1 - p_hat) / total) + (z**2 / (4 * total**2)))**0.5
        lower = (center - spread) / denominator
        upper = (center + spread) / denominator
        return max(0.0, lower), min(1.0, upper)

    @classmethod
    def filter_protected_core_violations(cls, domain: str, statement: str) -> bool:
        """RF5 Verification: Checks if a hypothesis touches security/authority domains."""
        # Check domain constraint explicitly
        _PROTECTED_DOMAINS = {
            "security", "authority", "approval", "permissions", 
            "capability_management", "risk_management", "identity_verification"
        }
        if domain in _PROTECTED_DOMAINS:
            return True
        # Regex safety backup
        _FORBIDDEN_PATTERNS = re.compile(
            r"(bypass|reduce|disable|auto-approve|lower|elevate|modify|override)\s+"
            r"(gate|security|approval|permission|policy|capability|broker|ledger|risk|auth)",
            re.IGNORECASE
        )
        if _FORBIDDEN_PATTERNS.search(statement):
            return True
        return False

    @classmethod
    def compile_daily_reflection(cls) -> dict[str, Any]:
        """Q1-Q4 Self-Reflection Loop. Aggregates data and creates report."""
        conn = ReflectionMemory._get_sqlite_conn()
        cursor = conn.cursor()
        today = time.strftime("%Y-%m-%d")
        
        try:
            # 1. Total opportunities vs observed counts (Selection Bias checks)
            cursor.execute("SELECT COUNT(*) FROM hm_reflection_observations WHERE outcome = 'UNKNOWN'")
            unknowns_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM hm_reflection_observations")
            total_logged = cursor.fetchone()[0]
            # Mock or check unobserved interactions
            unobserved_count = unknowns_count
            # If selection bias is high, mark warning flag
            bias_warning = (unobserved_count / max(1, total_logged)) > 0.30

            report_payload = {
                "period": "daily",
                "date": today,
                "evidence_window": {
                    "total_interactions_logged": total_logged,
                    "unobserved_interactions": unobserved_count,
                    "selection_bias_warning": bias_warning
                },
                "successes": [],
                "failures": [],
                "repeated_patterns": [],
                "improvement_hypotheses": [],
                "rejected_recommendations": [],
                "drift_alarms": []
            }

            # Q1 / Q2: Evaluate rates of successes vs failures
            # RF4 Echo Chamber check: ignore observations matching reflection_engine sources
            cursor.execute(
                """
                SELECT domain, action_type,
                       SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END),
                       COUNT(*)
                FROM hm_reflection_observations
                WHERE context_json NOT LIKE '%"source": "reflection_engine"%'
                  AND context_json NOT LIKE '%"provenance": "reflection_engine"%'
                GROUP BY domain, action_type
                """
            )
            for domain, action, successes, total in cursor.fetchall():
                lower, upper = cls.calculate_wilson_score_interval(successes, total)
                rate = successes / total
                entry = {
                    "domain": domain,
                    "action_type": action,
                    "success_rate": round(rate, 2),
                    "total_opportunities": total,
                    "confidence_interval": [round(lower, 2), round(upper, 2)]
                }
                if rate >= 0.75:
                    report_payload["successes"].append(entry)
                else:
                    report_payload["failures"].append(entry)

            # Q3: Extract Repeated friction patterns (independent-session count >= 2)
            cursor.execute(
                """
                SELECT pattern_signature, description, total_occurrences, success_rate, independent_sessions_count
                FROM hm_reflection_patterns
                WHERE total_occurrences >= 3
                """
            )
            for sig, desc, total, rate, sessions in cursor.fetchall():
                report_payload["repeated_patterns"].append({
                    "signature": sig,
                    "description": desc,
                    "occurrences": total,
                    "opportunities": total, # default matching opportunities
                    "independent_sessions": sessions
                })

            # Check sycophancy drift alarm: if total observed user corrections is 0 across 50+ interactions
            if total_logged >= 50:
                cursor.execute("SELECT COUNT(*) FROM hm_reflection_observations WHERE outcome = 'USER_CORRECTION'")
                corrections = cursor.fetchone()[0]
                if corrections == 0:
                    alarm_desc = "Sycophancy alert: 0 user corrections observed across 50+ sessions."
                    ReflectionMemory.raise_drift_alert("SYCOPHANCY_DRIFT", 0.8, alarm_desc)
                    report_payload["drift_alarms"].append(alarm_desc)

            # Q4: Improvement Hypotheses
            # Fetch unverified hypotheses
            cursor.execute(
                "SELECT id, domain, statement, predicted_metric_change, confidence_lower_bound, confidence_upper_bound "
                "FROM hm_reflection_hypotheses WHERE status = 'pending'"
            )
            for hyp_id, domain, statement, predicted, lower, upper in cursor.fetchall():
                # Enforce Protected-Core isolation
                if cls.filter_protected_core_violations(domain, statement):
                    report_payload["rejected_recommendations"].append({
                        "hypothesis_id": hyp_id,
                        "proposal": statement,
                        "reason": f"PROTECTED_CORE_VIOLATION: Proposal targets protected domain '{domain}' or attempts security bypass."
                    })
                    continue

                report_payload["improvement_hypotheses"].append({
                    "hypothesis_id": hyp_id,
                    "proposal": statement,
                    "prediction": predicted,
                    "confidence_interval": [round(lower, 2), round(upper, 2)],
                    "verification_required": True
                })

            # Write compiled report
            report_id = f"RPT-{uuid.uuid4().hex[:8].upper()}"
            cursor.execute(
                """
                INSERT INTO hm_reflection_reports
                    (id, execution_date, interactions_count, serialized_report_json, review_status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (report_id, today, total_logged, json.dumps(report_payload))
            )
            conn.commit()
            return report_payload
        finally:
            conn.close()

    # =========================================================================
    # STEP 12: DOUBLE-GATED PROMOTION GATE
    # =========================================================================

    @classmethod
    def verify_hypothesis(cls, hyp_id: str, success: bool) -> bool:
        """Independent Verification Gate: updates the verified status based on evidence."""
        conn = ReflectionMemory._get_sqlite_conn()
        cursor = conn.cursor()
        try:
            row = conn.execute("SELECT status FROM hm_reflection_hypotheses WHERE id = ?", (hyp_id,)).fetchone()
            if not row or row["status"] != "pending":
                return False
            status = "verified" if success else "rejected"
            cursor.execute(
                "UPDATE hm_reflection_hypotheses SET is_verified = ?, status = ? WHERE id = ?",
                (int(success), status, hyp_id)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @classmethod
    def verify_hypothesis_with_held_out_evidence(cls, hyp_id: str) -> tuple[bool, dict[str, Any]]:
        """Verification pipeline: evaluates hypothesis against held-out evidence (collected post-proposal)."""
        hyp = ReflectionMemory.get_hypothesis(hyp_id)
        if not hyp:
            return False, {"error": "Hypothesis not found"}
        if hyp["status"] != "pending":
            return False, {"error": f"Hypothesis status is {hyp['status']}, not pending"}

        cutoff = hyp.get("evidence_cutoff_timestamp")
        if cutoff is None:
            cutoff = hyp["created_at"]

        conn = ReflectionMemory._get_sqlite_conn()
        cursor = conn.cursor()
        try:
            # Query observations collected strictly AFTER cutoff timestamp
            # Filter out reflection-derived observations to prevent echo chambers
            cursor.execute(
                """
                SELECT outcome, COUNT(*) as cnt
                FROM hm_reflection_observations
                WHERE domain = ? 
                  AND timestamp > ?
                  AND context_json NOT LIKE '%"source": "reflection_engine"%'
                  AND context_json NOT LIKE '%"provenance": "reflection_engine"%'
                GROUP BY outcome
                """,
                (hyp["domain"], cutoff)
            )
            rows = cursor.fetchall()
            stats = {"SUCCESS": 0, "FAILURE": 0, "USER_CORRECTION": 0, "UNKNOWN": 0}
            for row in rows:
                stats[row["outcome"]] = row["cnt"]

            successes = stats["SUCCESS"]
            failures = stats["FAILURE"] + stats["USER_CORRECTION"]
            unknowns = stats["UNKNOWN"]
            total = successes + failures + unknowns

            if total < 3:
                return False, {
                    "status": "insufficient_evidence",
                    "total_trials": total,
                    "successes": successes,
                    "failures": failures,
                    "unknowns": unknowns
                }

            lower, upper = cls.calculate_wilson_score_interval(successes, total)
            rate = successes / total

            # Target: lower bound of Wilson score interval is >= 0.50 or success_rate is >= 0.70
            success = (lower >= 0.50) or (rate >= 0.70)
            cls.verify_hypothesis(hyp_id, success=success)

            return success, {
                "status": "verified" if success else "rejected",
                "total_trials": total,
                "successes": successes,
                "failures": failures,
                "unknowns": unknowns,
                "success_rate": round(rate, 2),
                "confidence_interval": [round(lower, 2), round(upper, 2)]
            }
        finally:
            conn.close()

    @classmethod
    def approve_hypothesis(cls, hyp_id: str, reviewer_id: str) -> bool:
        """Independent Approval Gate: human reviewer signs off on the hypothesis."""
        conn = ReflectionMemory._get_sqlite_conn()
        cursor = conn.cursor()
        try:
            row = conn.execute("SELECT status, is_verified, domain, statement FROM hm_reflection_hypotheses WHERE id = ?", (hyp_id,)).fetchone()
            if not row:
                return False
            
            # Transition to approved, but do not promote until is_verified is also 1
            cursor.execute("UPDATE hm_reflection_hypotheses SET is_approved = 1 WHERE id = ?", (hyp_id,))
            
            # Double-Gate promotion check
            if row["is_verified"] == 1:
                cls._promote_to_semantic_memory(cursor, hyp_id, row["statement"], reviewer_id)
                
            conn.commit()
            return True
        finally:
            conn.close()

    @classmethod
    def _promote_to_semantic_memory(cls, cursor: sqlite3.Cursor, hyp_id: str, statement: str, reviewer_id: str) -> None:
        """Promotes the verified + approved hypothesis into semantic memory."""
        cursor.execute("UPDATE hm_reflection_hypotheses SET status = 'promoted' WHERE id = ?", (hyp_id,))
        
        # Map lesson to semantic node
        from backend.core.semantic_memory import SemanticMemory
        node_id = str(uuid.uuid4())
        now = time.time()
        
        # Enforce RF4: node source is tagged 'reflection_engine' to prevent echo chambers
        cursor.execute(
            """
            INSERT INTO hm_semantic_nodes
                (id, concept, description, confidence, evidence_count, source_episode_ids, provenance, created_at, updated_at, status)
            VALUES (?, 'reflection_observation', ?, 0.85, 2, '[]', 'reflection_engine', ?, ?, 'verified')
            """,
            (node_id, statement, now, now)
        )
        
        # Provenance logged
        from backend.core.memory_governance import MemoryGovernance
        MemoryGovernance.log_provenance_direct(
            cursor=cursor,
            memory_id=node_id,
            memory_type="semantic",
            source="reflection_engine",
            created_by=reviewer_id,
            confidence=0.85,
            derived_from=[hyp_id],
            metadata_json=json.dumps({"origin": "reflection_engine", "promoted_hypothesis_id": hyp_id})
        )

    @classmethod
    def consolidate_episodic_memories(cls) -> list[str]:
        """Step 12: Reflection & Memory Consolidation Engine.
        
        Scans episodic events, groups them into clusters (by project or common keyword tokens),
        calculates success rates, applies the Wilson Score Interval gate, enforces safety and rate limits,
        and promotes qualifying patterns to Strategic Memory as draft INFERRED goals.
        """
        from backend.core.strategic_memory import StrategicMemory
        
        # 1. Fetch all episodic events
        conn = ReflectionMemory._get_sqlite_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_id, episode_id, title, gist_summary, verbatim_trace, outcome, lesson_learned, base_importance, source_type
                FROM episodic_events
                """
            )
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            # Handle case where tables are not initialized yet
            log_event(f"ConsolidationEngine: sqlite error fetching episodic events: {e}")
            return []
        finally:
            conn.close()

        if not rows:
            return []

        # 2. Cluster events by project_identifier and keyword tokens
        clusters = {}
        for row in rows:
            event = dict(row)
            project_id = None
            if event["episode_id"]:
                conn = ReflectionMemory._get_sqlite_conn()
                try:
                    p_row = conn.execute("SELECT project_identifier FROM episodic_episodes WHERE id = ?", (event["episode_id"],)).fetchone()
                    if p_row:
                        project_id = p_row["project_identifier"]
                finally:
                    conn.close()
            
            # Key 1: project-based clustering
            if project_id:
                clusters.setdefault(f"project:{project_id}", []).append(event)
            
            # Key 2: token/keyword based clustering
            text = (event["gist_summary"] or "") + " " + (event["title"] or "") + " " + (event["lesson_learned"] or "")
            tokens = _tokens(text)
            STOP_WORDS = {"the", "and", "for", "with", "this", "that", "from", "setup", "error", "failed", "system", "your", "were", "what", "then", "their", "when", "will"}
            for tok in tokens:
                if len(tok) >= 4 and tok not in STOP_WORDS:
                    clusters.setdefault(f"keyword:{tok}", []).append(event)

        # 3. Check current day's promotions limit
        one_day_ago = time.time() - 86400
        conn = ReflectionMemory._get_sqlite_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM hm_strategic_goals
                WHERE created_at > ?
                  AND status = 'draft'
                  AND trust_level = 'TRUST_UNVERIFIED'
                  AND approved_by_user = 0
                  AND goal LIKE '%[INFERRED]%'
                """,
                (one_day_ago,)
            )
            promotions_today = cursor.fetchone()[0]
        except Exception as e:
            log_event(f"Error checking promotions rate limit: {e}")
            promotions_today = 0
        finally:
            conn.close()

        promoted_goal_ids = []
        promoted_event_sets = []

        # 4. Evaluate each cluster
        sorted_clusters = sorted(clusters.items(), key=lambda item: len(item[1]), reverse=True)
        processed_statements = set()

        for cluster_name, cluster_events in sorted_clusters:
            # Enforce Minimum Evidence Count = 3
            if len(cluster_events) < 3:
                continue

            # Calculate successes vs failures
            successes = sum(1 for e in cluster_events if e["outcome"] in ("SUCCESS", "CORRECTED"))
            total = len(cluster_events)

            # Statistical Gate (Wilson Score Interval Lower Bound >= 0.50)
            lower, upper = cls.calculate_wilson_score_interval(successes, total)
            if lower < 0.50:
                continue

            # Rate limit check: max 5 promotions per day
            if promotions_today + len(promoted_goal_ids) >= 5:
                log_event("ConsolidationEngine: Promotion rate limit reached (max 5 per day). Skipping further promotions.")
                break

            # Prevent promoting redundant clusters containing similar/same evidence
            event_ids_set = set(e["event_id"] for e in cluster_events)
            is_redundant = False
            for promoted_set in promoted_event_sets:
                overlap = len(event_ids_set & promoted_set)
                if overlap / len(event_ids_set) >= 0.75:
                    is_redundant = True
                    break
            if is_redundant:
                continue

            # Formulate the principle statement
            lessons = [e["lesson_learned"] for e in cluster_events if e.get("lesson_learned")]
            titles = [e["title"] for e in cluster_events if e.get("title")]
            unique_lessons = []
            for l in lessons:
                if l and l not in unique_lessons:
                    unique_lessons.append(l)

            statement = ""
            if unique_lessons:
                prompt = (
                    f"Synthesize a clear, actionable strategic principle (a rule or guideline) from the following lessons learned:\n"
                    + "\n".join(f"- {l}" for l in unique_lessons) +
                    f"\n\nRespond with a single concise sentence summarizing the principle."
                )
                try:
                    statement = ask_model(prompt, role="coder").strip()
                    if statement.startswith("```"):
                        lines = statement.splitlines()
                        if len(lines) > 2:
                            statement = "\n".join(lines[1:-1]).strip()
                except Exception:
                    pass

            if not statement or len(statement) < 10:
                # Fallback deterministic formulation
                statement = f"Consolidated principle for {cluster_name}: " + "; ".join(unique_lessons[:3])

            # De-duplicate identical/similar statements within this run
            norm_statement = " ".join(statement.strip().lower().split())
            if norm_statement in processed_statements:
                continue
            processed_statements.add(norm_statement)

            # Safety Gate: check for protected core violations
            if cls.filter_protected_core_violations("planning", statement):
                log_event(f"ConsolidationEngine: Rejected candidate due to protected core violation: {statement}")
                continue

            # Promote to Strategic Memory as DRAFT INFERRED goal
            evidence_nodes = [e["event_id"] for e in cluster_events]
            goal_id = StrategicMemory.promote_strategic_principle(
                statement=statement,
                evidence_nodes=evidence_nodes,
                confidence=lower
            )
            promoted_goal_ids.append(goal_id)
            promoted_event_sets.append(event_ids_set)
            log_event(f"ConsolidationEngine: Successfully promoted principle '{statement}' to Goal {goal_id}")

        return promoted_goal_ids

    # =========================================================================
    # STEP 13: PLANNING & GOAL EXECUTION INTEGRATION
    # =========================================================================

    @classmethod
    def analyze_plan_performance_and_propose_adaptation(cls) -> list[str]:
        """Step 13: Analysis of plan blueprints in goal_memory.db to propose read-only goal adaptations."""
        config = load_config()
        # Connect to sibling database goal_memory.db
        db_path = config.sqlite_path.parent / "goal_memory.db"
        if not db_path.exists():
            return []

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        created_proposal_ids = []
        try:
            # Query blueprints with high replan counts or thrashing states
            rows = conn.execute(
                """
                SELECT blueprint_id, linked_goal_id, total_replans, blueprint_status
                FROM plan_blueprints
                WHERE total_replans > 2
                   OR blueprint_status IN ('INFEASIBLE', 'RESOURCE_UNAVAILABLE', 'VALUE_CONFLICT', 'STALE_ASSUMPTIONS')
                """
            ).fetchall()

            for r in rows:
                goal_id = r["linked_goal_id"]
                bp_id = r["blueprint_id"]
                replans = r["total_replans"]
                status = r["blueprint_status"]

                # Propose adaptation suggestions
                if replans > 2:
                    action = "PAUSE"
                    reason = f"Plan blueprint {bp_id} thrashed: replanned {replans} times."
                elif status == "VALUE_CONFLICT":
                    action = "ABANDON"
                    reason = f"Plan blueprint {bp_id} conflict detected: Value alignment checks failed."
                elif status == "RESOURCE_UNAVAILABLE":
                    action = "DELAY"
                    reason = f"Plan blueprint {bp_id} resource constraints: delay recommended."
                else:
                    action = "RE-ROUTE"
                    reason = f"Plan blueprint {bp_id} marked as {status}. Structural plan re-routing required."

                # Verify if a pending proposal for this goal already exists to prevent duplicate spamming
                prop_exists = False
                existing_props = ReflectionMemory.list_goal_adaptation_proposals(status="pending")
                for ep in existing_props:
                    if ep["goal_id"] == goal_id and ep["suggested_action"] == action:
                        prop_exists = True
                        break

                if not prop_exists:
                    # Look up hypothesis id if any
                    hyp_id = None
                    prop_id = ReflectionMemory.add_goal_adaptation_proposal(
                        hypothesis_id=hyp_id,
                        goal_id=goal_id,
                        suggested_action=action,
                        reason=reason
                    )
                    created_proposal_ids.append(prop_id)
        except Exception as e:
            log_event(f"reflection_engine: failed to analyze plan performance: {e}")
        finally:
            conn.close()

        return created_proposal_ids

    # --- Phase 4 JSON-Backed Observation Persistence and Management ---

    _lock = threading.RLock()

    MIN_EVIDENCE_COUNT = 3
    MIN_EVIDENCE_SOURCES = 2
    DEFAULT_WINDOW_DAYS = 30
    DEDUP_SIMILARITY = 0.6

    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"reflections": []}

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def reflect(
        cls,
        problem: str,
        cause: str,
        improvement: str,
        *,
        category: ReflectionCategory | str = ReflectionCategory.REASONING,
        evidence_source: str = "reasoning",
        confidence: int = 50,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> dict[str, Any]:
        """Record an observation. Dedups into an existing pending reflection."""
        problem = problem.strip()
        if not problem:
            raise ValueError("Reflection problem cannot be empty")
        category = ReflectionCategory.coerce(category)
        confidence = max(0, min(100, int(confidence)))
        ptokens = _tokens(problem)

        with cls._lock:
            data = cls._load()
            reflections = data.setdefault("reflections", [])

            # Dedup: fold into a similar PENDING reflection.
            for rec in reflections:
                if rec["status"] != ReflectionStatus.PENDING.value:
                    continue
                if _jaccard(ptokens, _tokens(rec["problem"])) >= cls.DEDUP_SIMILARITY:
                    sources = set(rec.get("evidence_sources", []))
                    sources.add(evidence_source)
                    rec["evidence_sources"] = sorted(sources)
                    rec["evidence_count"] = int(rec.get("evidence_count", 1)) + 1
                    rec["confidence"] = max(int(rec.get("confidence", 0)), confidence)
                    rec["updated_at"] = time.time()
                    cls._save(data)
                    return rec

            now = time.time()
            rec = {
                "id": uuid.uuid4().hex[:12],
                "category": category.value,
                "problem": problem,
                "cause": cause.strip(),
                "improvement": improvement.strip(),
                "confidence": confidence,
                "evidence_count": 1,
                "evidence_sources": [evidence_source],
                "status": ReflectionStatus.PENDING.value,
                "window_days": window_days,
                "created_at": now,
                "updated_at": now,
                "expires_at": now + window_days * 86400,
            }
            reflections.append(rec)
            cls._save(data)
            return rec

    @classmethod
    def is_actionable(cls, rec: dict[str, Any]) -> bool:
        return (
            int(rec.get("evidence_count", 0)) >= cls.MIN_EVIDENCE_COUNT
            and len(rec.get("evidence_sources", [])) >= cls.MIN_EVIDENCE_SOURCES
        )

    @classmethod
    def accept(cls, reflection_id: str) -> dict[str, Any]:
        """Governance acceptance. Returns the improvement to apply EXTERNALLY.

        Acceptance does NOT mutate any memory/weights/prompts itself.
        """
        with cls._lock:
            data = cls._load()
            rec = cls._find(data, reflection_id)
            if rec is None:
                raise KeyError(f"No reflection {reflection_id!r}")
            if not cls.is_actionable(rec):
                raise ValueError(
                    f"Reflection not actionable: needs >= {cls.MIN_EVIDENCE_COUNT} observations "
                    f"from >= {cls.MIN_EVIDENCE_SOURCES} sources"
                )
            rec["status"] = ReflectionStatus.ACCEPTED.value
            rec["updated_at"] = time.time()
            cls._save(data)
            return rec

    @classmethod
    def reject(cls, reflection_id: str) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            rec = cls._find(data, reflection_id)
            if rec is None:
                raise KeyError(f"No reflection {reflection_id!r}")
            rec["status"] = ReflectionStatus.REJECTED.value
            rec["updated_at"] = time.time()
            cls._save(data)
            return rec

    @classmethod
    def expire_old(cls, *, now: float | None = None) -> int:
        now = now or time.time()
        expired = 0
        with cls._lock:
            data = cls._load()
            for rec in data.get("reflections", []):
                if rec["status"] == ReflectionStatus.PENDING.value and now >= rec.get("expires_at", 0):
                    rec["status"] = ReflectionStatus.EXPIRED.value
                    rec["updated_at"] = now
                    expired += 1
            cls._save(data)
        return expired

    @staticmethod
    def _find(data: dict[str, Any], reflection_id: str) -> dict[str, Any] | None:
        return next((r for r in data.get("reflections", []) if r["id"] == reflection_id), None)

    @classmethod
    def get(cls, reflection_id: str) -> dict[str, Any] | None:
        return cls._find(cls._load(), reflection_id)

    @classmethod
    def list_reflections(cls, status: str | None = None) -> list[dict[str, Any]]:
        items = list(cls._load().get("reflections", []))
        if status:
            items = [r for r in items if r["status"] == status]
        return items

    @classmethod
    def actionable(cls) -> list[dict[str, Any]]:
        return [r for r in cls.list_reflections(ReflectionStatus.PENDING.value)
                if cls.is_actionable(r)]

    @classmethod
    def status(cls) -> dict[str, Any]:
        items = cls.list_reflections()
        by_status: dict[str, int] = {s.value: 0 for s in ReflectionStatus}
        by_category: dict[str, int] = {c.value: 0 for c in ReflectionCategory}
        for r in items:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            by_category[r["category"]] = by_category.get(r["category"], 0) + 1
        return {
            "total": len(items),
            "by_status": by_status,
            "by_category": by_category,
            "actionable": len(cls.actionable()),
        }

    @classmethod
    def reflect_and_consolidate(
        cls,
        session_id: str,
        user_query: str,
        response_text: str,
        state: dict[str, Any]
    ) -> None:
        """Asynchronously analyze outcome, record accuracy metrics, and store the episode."""
        from backend.core.episodic_memory import EpisodicMemory
        
        # 1. Determine execution outcome status
        success = True
        if state.get("selected_agent") == "safety" or "Safety Block" in response_text:
            success = False
            outcome = "FAILURE"
        elif state.get("selected_agent") == "personality_council" and state.get("council_debate_result", {}).get("status") == "rejected":
            success = False
            outcome = "ANOMALY"
        else:
            outcome = "SUCCESS"

        # 2. Derive a lesson learned based on outcome
        if outcome == "SUCCESS":
            lesson = f"User query: '{user_query}' processed successfully by {state.get('selected_agent', 'direct_model')}."
        else:
            lesson = f"User query: '{user_query}' triggered safety or council rejection: '{response_text[:100]}...'."

        # 3. Calculate importance score (normalized 0.0 to 1.0)
        risk_str = str(state.get("risk_level", "low")).lower()
        risk_val = 0.8 if "high" in risk_str else (0.5 if "medium" in risk_str else 0.2)
        importance = round(0.5 * risk_val + 0.5 * (1.0 if success else 0.2), 2)

        # 4. Create and store episode
        try:
            EpisodicMemory.create_episode(
                content=f"User: {user_query}\nAssistant: {response_text}",
                importance=importance,
                category="IMPLEMENTATION",
                session_id=session_id,
                outcome=outcome,
                lesson_learned=lesson,
            )
        except Exception:
            pass

        # 5. Record agent prediction success/failure outcome to update calibration
        selected_agent = state.get("selected_agent")
        if selected_agent and selected_agent not in ("unknown", "evaluator"):
            try:
                from backend.core.council_session import CouncilSession
                decision_id = (state.get("council_debate_result") or {}).get("decision_id")
                if decision_id:
                    CouncilSession.record_outcome(
                        decision_id=decision_id,
                        actual_success=1.0 if success else 0.0
                    )
            except Exception:
                pass

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({"reflections": []})

