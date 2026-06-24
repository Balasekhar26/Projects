"""Meta-Cognition Engine (Layer 10/11).

Supervises the thinking process itself rather than acting as another agent or planner.
It analyzes uncertainty, conflicts, capability gaps, reasoning traps, and selects
the cognitive mode (DIRECT, DEEP_ANALYSIS, HIGH_ASSURANCE).

As a governor rather than a ruler, it never alters decisions from consensus, validators,
or value engines. It only returns supervision recommendations: ALLOW, ESCALATE,
REQUEST_MORE_EVIDENCE, or CHANGE_REASONING_MODE.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from backend.core.capability_graph import CapabilityGraph
from backend.core.config import load_config


class CognitiveMode(str, Enum):
    DIRECT = "DIRECT"
    DEEP_ANALYSIS = "DEEP_ANALYSIS"
    HIGH_ASSURANCE = "HIGH_ASSURANCE"


class SupervisionAction(str, Enum):
    ALLOW = "ALLOW"
    ESCALATE = "ESCALATE"
    REQUEST_MORE_EVIDENCE = "REQUEST_MORE_EVIDENCE"
    CHANGE_REASONING_MODE = "CHANGE_REASONING_MODE"


class MetaCognitionEngine:
    """Monitors and guides Kattappa's cognitive pipeline to enforce safe reasoning."""

    # 1. Select Cognitive Mode
    @classmethod
    def select_cognitive_mode(
        cls, prompt: str, is_production: bool = False, is_code_change: bool = False
    ) -> dict[str, Any]:
        prompt_lower = prompt.lower().strip()
        words = prompt_lower.split()

        # DIRECT mode heuristics (simple calculations or greetings)
        is_simple = (
            (len(words) <= 8
            or prompt_lower in {"hi", "hello", "hey", "status", "ping"}
            or re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", prompt_lower))
            and not any(kw in prompt_lower for kw in {"design", "architect", "feasibility", "equation", "derivation", "physics", "system topology", "dews"})
            and not any(kw in prompt_lower for kw in {"deploy", "production", "prod", "credentials", "auth", "secret"})
        )

        # HIGH_ASSURANCE mode triggers (deployments, code changes, or production environment)
        is_high_assurance = (
            is_production
            or is_code_change
            or any(kw in prompt_lower for kw in {"deploy", "production", "prod", "credentials", "auth", "secret"})
        )

        # DEEP_ANALYSIS mode triggers (complex research, system designs, architecture)
        is_deep_analysis = (
            not is_simple
            and not is_high_assurance
            and (
                len(words) >= 15
                or any(kw in prompt_lower for kw in {"design", "architect", "feasibility", "equation", "derivation", "physics", "system topology", "dews"})
            )
        )

        if is_high_assurance:
            mode = CognitiveMode.HIGH_ASSURANCE
            invoked = ["Validators", "Consensus", "Value Engine", "Policy Engine"]
        elif is_deep_analysis:
            mode = CognitiveMode.DEEP_ANALYSIS
            invoked = ["Router", "Consensus", "Value Engine"]
        else:
            mode = CognitiveMode.DIRECT
            invoked = []

        return {
            "mode": mode.value,
            "invoked_subsystems": invoked,
            "reasons": [
                f"simple={is_simple}",
                f"high_assurance={is_high_assurance}",
                f"deep_analysis={is_deep_analysis}",
            ],
        }

    # 2. Detect Uncertainty
    @classmethod
    def detect_uncertainty(
        cls,
        prompt: str,
        routing_confidence: float,
        evidence_count: int,
        missing_validators: bool,
    ) -> dict[str, Any]:
        reasons = []
        is_low = False

        if routing_confidence < 0.5:
            is_low = True
            reasons.append(f"Low routing confidence: {routing_confidence:.2f}")

        if evidence_count == 0:
            is_low = True
            reasons.append("No supporting tool or simulation evidence registered")

        if missing_validators:
            is_low = True
            reasons.append("Required validators are missing from the routing plan")

        certainty = "LOW" if is_low else "HIGH"
        action = SupervisionAction.REQUEST_MORE_EVIDENCE if is_low else SupervisionAction.ALLOW

        return {
            "certainty": certainty,
            "reasons": reasons,
            "action": action.value,
        }

    # 3. Detect Conflicts
    @classmethod
    def detect_conflicts(
        cls,
        vetoes: Sequence[Any],
        blocking_findings: Sequence[Any],
        consensus_status: str,
        simulation_success_rate: float | None = None,
    ) -> dict[str, Any]:
        reasons = []
        high_conflict = False

        # Vetoes
        failed_vetoes = []
        for v in vetoes:
            # support dict or Veto object
            if isinstance(v, dict):
                if not v.get("passed", True):
                    failed_vetoes.append(v.get("source", "unknown"))
            elif hasattr(v, "passed") and not v.passed:
                failed_vetoes.append(getattr(v, "source", "unknown"))

        if failed_vetoes:
            high_conflict = True
            reasons.append(f"Veto failure detected from: {', '.join(failed_vetoes)}")

        # Blocking findings from Critic
        if blocking_findings:
            high_conflict = True
            reasons.append(f"{len(blocking_findings)} blocking Critic findings identified")

        # Consensus status is escalate or rejected
        if consensus_status in {"escalate", "rejected", "no_feasible_solution"}:
            high_conflict = True
            reasons.append(f"Consensus engine status: {consensus_status}")

        # Simulation failure
        if simulation_success_rate is not None and simulation_success_rate < 0.5:
            high_conflict = True
            reasons.append(f"Simulation success rate too low: {simulation_success_rate:.2%}")

        action = SupervisionAction.ESCALATE if high_conflict else SupervisionAction.ALLOW

        return {
            "high_conflict": high_conflict,
            "conflicts": reasons,
            "action": action.value,
        }

    # 4. Detect Missing Capabilities
    @classmethod
    def detect_missing_capabilities(
        cls, goal: str, required_caps: list[str] | None = None
    ) -> dict[str, Any]:
        if not required_caps:
            return {
                "cannot_execute": False,
                "missing": [],
                "bottlenecks": [],
                "action": SupervisionAction.ALLOW.value,
            }

        assessment = CapabilityGraph.assess(goal, required_caps)
        missing = assessment.get("missing", [])
        bottlenecks = assessment.get("bottlenecks", [])

        cannot_execute = len(missing) > 0
        action = SupervisionAction.ESCALATE if cannot_execute else SupervisionAction.ALLOW

        return {
            "cannot_execute": cannot_execute,
            "missing": missing,
            "bottlenecks": bottlenecks,
            "action": action.value,
        }

    # 5. Detect Reasoning Traps
    @classmethod
    def detect_reasoning_traps(
        cls, chat_history: list[dict[str, Any]] | None, failed_runs_count: int = 0
    ) -> dict[str, Any]:
        traps = []

        # Circular Reasoning (repeated user prompts in recent history)
        if chat_history and len(chat_history) >= 3:
            user_msgs = [m["content"].lower().strip() for m in chat_history if m.get("role") == "user"]
            if len(user_msgs) >= 2 and user_msgs[-1] == user_msgs[-2]:
                traps.append("Circular reasoning trap: prompt repeated consecutively")

        # Repeated failed plans
        if failed_runs_count >= 2:
            traps.append(f"Repeated execution failures: {failed_runs_count} consecutive runs failed")

        action = SupervisionAction.ESCALATE if traps else SupervisionAction.ALLOW

        return {
            "traps_detected": traps,
            "action": action.value,
        }

    # Unified Entry point
    @classmethod
    def supervise(
        cls,
        prompt: str,
        routing_confidence: float = 1.0,
        evidence_count: int = 1,
        missing_validators: bool = False,
        vetoes: Sequence[Any] = (),
        blocking_findings: Sequence[Any] = (),
        consensus_status: str = "approved",
        simulation_success_rate: float | None = None,
        goal: str | None = None,
        required_caps: list[str] | None = None,
        chat_history: list[dict[str, Any]] | None = None,
        failed_runs_count: int = 0,
        is_production: bool = False,
        is_code_change: bool = False,
    ) -> dict[str, Any]:
        """Runs the complete cognitive checks. Returns the recommendation action."""
        mode_res = cls.select_cognitive_mode(prompt, is_production, is_code_change)
        uncertainty_res = cls.detect_uncertainty(prompt, routing_confidence, evidence_count, missing_validators)
        conflict_res = cls.detect_conflicts(vetoes, blocking_findings, consensus_status, simulation_success_rate)
        capability_res = cls.detect_missing_capabilities(goal or prompt, required_caps)
        trap_res = cls.detect_reasoning_traps(chat_history, failed_runs_count)

        # Action precedence: ESCALATE > REQUEST_MORE_EVIDENCE > CHANGE_REASONING_MODE > ALLOW
        final_action = SupervisionAction.ALLOW

        actions = [
            SupervisionAction(uncertainty_res["action"]),
            SupervisionAction(conflict_res["action"]),
            SupervisionAction(capability_res["action"]),
            SupervisionAction(trap_res["action"]),
        ]

        if SupervisionAction.ESCALATE in actions:
            final_action = SupervisionAction.ESCALATE
        elif SupervisionAction.REQUEST_MORE_EVIDENCE in actions:
            final_action = SupervisionAction.REQUEST_MORE_EVIDENCE
        elif mode_res["mode"] == CognitiveMode.DIRECT.value and len(prompt.split()) > 15:
            # Prompt is too long for direct execution, recommend changing mode
            final_action = SupervisionAction.CHANGE_REASONING_MODE

        return {
            "mode": mode_res["mode"],
            "invoked_subsystems": mode_res["invoked_subsystems"],
            "uncertainty": uncertainty_res,
            "conflict": conflict_res,
            "capability": capability_res,
            "trap": trap_res,
            "action": final_action.value,
        }


class MRALAuditor:
    """Meta-Cognition & Reasoning Audit Layer (MRAL) Manager.
    
    Extracts assumptions, matches reasoning contradictions, computes
    confidence trees, and logs decision traces for replay.
    """

    _lock = threading.RLock()
    _schema_ensured = False

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "goal_memory.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mral_decision_traces (
                    decision_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    goal_id TEXT,
                    goal_title TEXT NOT NULL,
                    goal_description TEXT,
                    final_decision TEXT NOT NULL,
                    requires_human_approval INTEGER NOT NULL,
                    research_confidence REAL NOT NULL,
                    simulation_confidence REAL NOT NULL,
                    verification_confidence REAL NOT NULL,
                    consensus_confidence REAL NOT NULL,
                    consensus_for_mass REAL NOT NULL,
                    consensus_against_mass REAL NOT NULL,
                    role_teacher_pct REAL NOT NULL,
                    role_engineer_pct REAL NOT NULL,
                    role_scientist_pct REAL NOT NULL,
                    role_builder_pct REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mral_assumptions (
                    assumption_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_verified INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (decision_id) REFERENCES mral_decision_traces(decision_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS mral_contradictions (
                    contradiction_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source_module TEXT NOT NULL,
                    description TEXT NOT NULL,
                    is_resolved INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (decision_id) REFERENCES mral_decision_traces(decision_id) ON DELETE CASCADE
                );
                """
            )
            conn.commit()

    @classmethod
    def detect_assumptions(cls, goal_title: str, goal_description: str, plan_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        assumptions = []
        text_to_check = (goal_title + " " + (goal_description or "")).lower()
        for step in plan_steps:
            text_to_check += " " + str(step.get("action", "")).lower() + " " + str(step.get("description", "")).lower()

        # Rule 1: Drone / Travel / Physical systems
        if any(w in text_to_check for w in ["drone", "fly", "delivery", "travel", "quadcopter", "uav"]):
            assumptions.append({
                "statement": "GPS signal is available and active in target environment",
                "category": "REGULATIONS",
                "is_verified": 0
            })
            assumptions.append({
                "statement": "Airspace regulations permit drone operations in target flight coordinates",
                "category": "REGULATIONS",
                "is_verified": 0
            })
            assumptions.append({
                "statement": "Weather conditions are within safe operational limits for drone flight",
                "category": "ENVIRONMENT",
                "is_verified": 0
            })
            assumptions.append({
                "statement": "Drone battery charge/capacity is correctly calibrated and sufficient",
                "category": "HARDWARE",
                "is_verified": 0
            })

        # Rule 2: RF / Radio / Hardware testing
        if any(w in text_to_check for w in ["rf", "radio", "signal", "frequency", "testing", "chamber", "hardware"]):
            assumptions.append({
                "statement": "RF testing chamber or simulation tools are available and calibrated",
                "category": "HARDWARE",
                "is_verified": 0
            })
            assumptions.append({
                "statement": "Hardware signal transmission does not violate local RF interference policies",
                "category": "REGULATIONS",
                "is_verified": 0
            })

        # Rule 3: Cloud / Deployment / API connections
        if any(w in text_to_check for w in ["cloud", "deploy", "api", "database", "credentials", "server", "aws", "gcp"]):
            assumptions.append({
                "statement": "Target network has stable internet connectivity and allows external traffic",
                "category": "NETWORK",
                "is_verified": 0
            })
            assumptions.append({
                "statement": "Cloud environment API credentials and security keys are provisioned",
                "category": "DEPLOYMENT",
                "is_verified": 0
            })

        # Rule 4: Coding / Execution / Platform dependencies
        if any(w in text_to_check for w in ["code", "rust", "python", "javascript", "compile", "build", "run"]):
            assumptions.append({
                "statement": "Compatible compiler/interpreter version is installed on host platform",
                "category": "DEVELOPMENT",
                "is_verified": 0
            })
            assumptions.append({
                "statement": "Third-party package repositories are reachable for dependencies download",
                "category": "DEVELOPMENT",
                "is_verified": 0
            })

        # Rule 5: Default standard operations
        if not assumptions:
            assumptions.append({
                "statement": "Agent execution container has standard read/write permissions to workspace directory",
                "category": "OPERATIONS",
                "is_verified": 1
            })
            assumptions.append({
                "statement": "System libraries and essential utility binaries are available on host platform",
                "category": "OPERATIONS",
                "is_verified": 1
            })

        return assumptions

    @classmethod
    def detect_contradictions(
        cls,
        goal_title: str,
        goal_description: str,
        plan_steps: List[Dict[str, Any]],
        sandbox_report: Dict[str, Any],
        consensus_decision: Dict[str, Any],
        lis_alarms: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        contradictions = []
        text_to_check = (goal_title + " " + (goal_description or "")).lower()
        for step in plan_steps:
            text_to_check += " " + str(step.get("action", "")).lower() + " " + str(step.get("description", "")).lower()

        # Rule 1: Battery limit clashing
        battery_match = re.search(r"battery\s*(?:range|limit|max)?\s*(?:=|is|of)?\s*(\d+)\s*km", text_to_check)
        route_match = re.search(r"(?:route|distance|delivery)\s*(?:=|is|of)?\s*(\d+)\s*km", text_to_check)
        if battery_match and route_match:
            bat_range = int(battery_match.group(1))
            route_dist = int(route_match.group(1))
            if route_dist > bat_range:
                contradictions.append({
                    "severity": "BLOCKING",
                    "source_module": "RESEARCH_VS_ENGINEERING",
                    "description": f"Route distance ({route_dist} km) clashing with maximum battery range limit ({bat_range} km)."
                })

        # Rule 2: Memory / sandbox capacity limits clashing
        if sandbox_report:
            if sandbox_report.get("exhaustion_triggered") or sandbox_report.get("estimated_memory_kb", 0) > 16000000:
                contradictions.append({
                    "severity": "BLOCKING",
                    "source_module": "SANDBOX_PREDICTION",
                    "description": "Simulation predicts resource exhaustion: projected memory usage clashing with physical resource limits."
                })
            if sandbox_report.get("upstream_delays_detected"):
                contradictions.append({
                    "severity": "WARNING",
                    "source_module": "SANDBOX_PREDICTION",
                    "description": "Simulation warns of upstream delays clashing with target project schedule limits."
                })

        # Rule 3: Consensus vetoes clashing
        if consensus_decision:
            if consensus_decision.get("status") in ("rejected", "no_feasible_solution"):
                contradictions.append({
                    "severity": "BLOCKING",
                    "source_module": "CONSENSUS_ENGINE",
                    "description": f"Consensus engine rejected the recommendation: {consensus_decision.get('rejected_by')} veto clashing with target approval goal."
                })

        # Rule 4: LIS drift warnings clashing
        if lis_alarms:
            for alarm, status in lis_alarms.items():
                if status == "WARNING":
                    contradictions.append({
                        "severity": "WARNING",
                        "source_module": "LIS_IDENTITY",
                        "description": f"Long-Term Identity System reports active drift warning clashing with safe behavioral guidelines: {alarm} alarm active."
                    })

        return contradictions

    @classmethod
    def calculate_confidence_tree(
        cls,
        research_topics: List[Dict[str, Any]],
        sandbox_report: Dict[str, Any],
        verification_prediction: Dict[str, Any],
        consensus_decision: Dict[str, Any]
    ) -> Dict[str, float]:
        research_conf = 90.0
        if research_topics:
            total_contradictions = sum(t.get("contradictions", 0) for t in research_topics)
            total_questions = sum(t.get("questions", 0) for t in research_topics)
            research_conf = max(10.0, 90.0 - (total_contradictions * 5.0) - (total_questions * 2.0))

        sim_conf = 95.0
        if sandbox_report:
            sim_conf = sandbox_report.get("validation_score", 95.0)
            if sandbox_report.get("exhaustion_triggered"):
                sim_conf = max(10.0, sim_conf - 40.0)

        verif_conf = 92.0
        if verification_prediction:
            status = verification_prediction.get("status")
            if status in ("RECOMMEND_REVISE", "BLOCKED"):
                verif_conf = 55.0
            elif status == "WARNING":
                verif_conf = 75.0

        consensus_conf = 90.0
        if consensus_decision:
            approve_mass = consensus_decision.get("approve_mass", 0.0)
            reject_mass = consensus_decision.get("reject_mass", 0.0)
            total_mass = approve_mass + reject_mass
            if total_mass > 0:
                consensus_conf = round((approve_mass / total_mass) * 100.0, 1)

        return {
            "research": research_conf,
            "simulation": sim_conf,
            "verification": verif_conf,
            "consensus": consensus_conf
        }

    @classmethod
    def record_decision_trace(
        cls,
        goal_id: Optional[str],
        goal_title: str,
        goal_description: Optional[str],
        plan_steps: List[Dict[str, Any]],
        consensus_decision: Dict[str, Any],
        sandbox_report: Dict[str, Any],
        verification_prediction: Dict[str, Any],
        research_topics: List[Dict[str, Any]],
        lis_profile: Dict[str, Any],
        lis_alarms: Dict[str, str],
        role_weights: Dict[str, int]
    ) -> Dict[str, Any]:
        conn = cls._get_sqlite_conn()
        try:
            decision_id = f"dec_{uuid.uuid4().hex[:8]}"
            now = time.time()

            assumptions = cls.detect_assumptions(goal_title, goal_description or "", plan_steps)

            contradictions = cls.detect_contradictions(
                goal_title, goal_description or "", plan_steps, sandbox_report, consensus_decision, lis_alarms
            )

            conf_tree = cls.calculate_confidence_tree(
                research_topics, sandbox_report, verification_prediction, consensus_decision
            )

            conn.execute(
                """
                INSERT INTO mral_decision_traces (
                    decision_id, timestamp, goal_id, goal_title, goal_description,
                    final_decision, requires_human_approval,
                    research_confidence, simulation_confidence, verification_confidence, consensus_confidence,
                    consensus_for_mass, consensus_against_mass,
                    role_teacher_pct, role_engineer_pct, role_scientist_pct, role_builder_pct
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id, now, goal_id, goal_title, goal_description,
                    consensus_decision.get("status", "REJECTED"),
                    1 if consensus_decision.get("requires_human_approval", False) else 0,
                    conf_tree["research"], conf_tree["simulation"], conf_tree["verification"], conf_tree["consensus"],
                    consensus_decision.get("approve_mass", 0.0), consensus_decision.get("reject_mass", 0.0),
                    role_weights.get("TEACHER", 25.0), role_weights.get("ENGINEER", 25.0),
                    role_weights.get("SCIENTIST", 25.0), role_weights.get("BUILDER", 25.0)
                )
            )

            for a in assumptions:
                conn.execute(
                    """
                    INSERT INTO mral_assumptions (assumption_id, decision_id, statement, category, is_verified)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"asm_{uuid.uuid4().hex[:8]}", decision_id, a["statement"], a["category"], a["is_verified"])
                )

            for c in contradictions:
                conn.execute(
                    """
                    INSERT INTO mral_contradictions (contradiction_id, decision_id, severity, source_module, description, is_resolved)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (f"ctr_{uuid.uuid4().hex[:8]}", decision_id, c["severity"], c["source_module"], c["description"])
                )

            conn.commit()

            return {
                "decision_id": decision_id,
                "timestamp": now,
                "goal_title": goal_title,
                "final_decision": consensus_decision.get("status", "REJECTED"),
                "requires_human_approval": consensus_decision.get("requires_human_approval", False),
                "confidence_tree": conf_tree,
                "assumptions": assumptions,
                "contradictions": contradictions
            }
        finally:
            conn.close()

    @classmethod
    def get_decision_replay(cls, decision_id: str) -> Optional[Dict[str, Any]]:
        conn = cls._get_sqlite_conn()
        try:
            trace_row = conn.execute("SELECT * FROM mral_decision_traces WHERE decision_id = ?", (decision_id,)).fetchone()
            if not trace_row:
                return None

            asm_rows = conn.execute("SELECT * FROM mral_assumptions WHERE decision_id = ?", (decision_id,)).fetchall()
            ctr_rows = conn.execute("SELECT * FROM mral_contradictions WHERE decision_id = ?", (decision_id,)).fetchall()

            return {
                "decision_id": trace_row["decision_id"],
                "timestamp": trace_row["timestamp"],
                "goal_id": trace_row["goal_id"],
                "goal_title": trace_row["goal_title"],
                "goal_description": trace_row["goal_description"],
                "final_decision": trace_row["final_decision"],
                "requires_human_approval": bool(trace_row["requires_human_approval"]),
                "confidence_tree": {
                    "research": trace_row["research_confidence"],
                    "simulation": trace_row["simulation_confidence"],
                    "verification": trace_row["verification_confidence"],
                    "consensus": trace_row["consensus_confidence"]
                },
                "consensus_mass": {
                    "for": trace_row["consensus_for_mass"],
                    "against": trace_row["consensus_against_mass"]
                },
                "role_weights": {
                    "TEACHER": trace_row["role_teacher_pct"],
                    "ENGINEER": trace_row["role_engineer_pct"],
                    "SCIENTIST": trace_row["role_scientist_pct"],
                    "BUILDER": trace_row["role_builder_pct"]
                },
                "assumptions": [dict(r) for r in asm_rows],
                "contradictions": [dict(r) for r in ctr_rows]
            }
        finally:
            conn.close()

    @classmethod
    def get_all_traces(cls) -> List[Dict[str, Any]]:
        conn = cls._get_sqlite_conn()
        try:
            rows = conn.execute("SELECT * FROM mral_decision_traces ORDER BY timestamp DESC").fetchall()
            traces = []
            for r in rows:
                traces.append({
                    "decision_id": r["decision_id"],
                    "timestamp": r["timestamp"],
                    "goal_title": r["goal_title"],
                    "final_decision": r["final_decision"],
                    "requires_human_approval": bool(r["requires_human_approval"]),
                    "overall_confidence": round((r["research_confidence"] + r["simulation_confidence"] + r["verification_confidence"] + r["consensus_confidence"]) / 4.0, 1)
                })
            return traces
        finally:
            conn.close()
