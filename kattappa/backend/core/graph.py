from __future__ import annotations

import json
import logging
import re
from langgraph.graph import END, StateGraph

from backend.agents.browser import browser_node
from backend.agents.builder import builder_node
from backend.agents.coder import coder_node
from backend.agents.desktop import desktop_node
from backend.agents.evaluator import evaluator_node
from backend.agents.file_agent import file_node
from backend.agents.finance import finance_node
from backend.agents.planner import planner_node
from backend.agents.researcher import researcher_node
from backend.agents.self_improver import self_improver_node
from backend.agents.terminal import terminal_node
from backend.agents.vision import vision_node
from backend.agents.voice import voice_node
from backend.agents.monitoring import monitoring_node
from backend.agents.executive import executive_node
from backend.core.logger import log_event
from backend.core.state import AgentState

from backend.core.observer import Observer
from backend.core.attention import Attention
from backend.core.memory_recall import MemoryRecall
from backend.core.council_debate import CouncilDebate
from backend.core.safety_review import SafetyReview
from backend.core.metacognition import MetacognitiveGate
from backend.core.world_model import WorldModel
from backend.core.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

# Module-level KG singleton (lazily initialized)
_kg_instance: KnowledgeGraph | None = None

# ── Routing Logic ─────────────────────────────────────────────────────────────

def route_executive(state: AgentState) -> str:
    if state.get("result"):
        return "evaluator"
    return "observation"


def route_attention(state: AgentState) -> str:
    attn = state.get("attention_frame")
    if attn and attn.get("early_exit"):
        return "metacognition"
    return "memory"


def route_metacognition(state: AgentState) -> str:
    action = state.get("metacognitive_action", "ANSWER")
    re_retrieve_count = state.get("re_retrieve_count", 0)

    if action == "RE_RETRIEVE" and re_retrieve_count < 2:
        return "memory"

    if action in ("ANSWER", "ASK_CLARIFICATION", "ABSTAIN"):
        return "safety"

    return "council_debate"


def route_council(state: AgentState) -> str:
    res = state.get("council_debate_result")
    if res and (res.get("status") == "rejected" or res.get("requires_human_approval")):
        return "evaluator"
    return "planner"


def route_agent(state: AgentState) -> str:
    if state.get("approval_required") and state.get("result"):
        return "evaluator"
    selected = state.get("selected_agent") or "evaluator"
    return (
        selected
        if selected
        in {
            "coder",
            "builder",
            "browser",
            "desktop",
            "researcher",
            "vision",
            "voice",
            "file",
            "terminal",
            "finance",
            "self_improver",
            "monitoring",
        }
        else "evaluator"
    )


def route_evaluator(state: AgentState) -> str:
    if state.get("selected_agent") and state.get("result") is None:
        return "safety"
    return "end"


def route_reasoning(state: AgentState) -> str:
    gaps = state.get("reasoning_gaps")
    depth = state.get("reasoning_recursion_depth", 0)
    if gaps and depth < 3:
        return "memory"
    return "metacognition"



# ── Knowledge Graph Helpers ────────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "and", "or", "if", "while", "about", "up",
    "that", "this", "these", "those", "it", "its", "i", "me", "my", "we",
    "our", "you", "your", "he", "him", "his", "she", "her", "they", "them",
    "their", "what", "which", "who", "whom", "please", "want", "like",
    "get", "got", "make", "go", "going", "help", "also", "new", "use",
})


def _get_kg() -> KnowledgeGraph | None:
    """Return a lazily-initialized KnowledgeGraph singleton, or None on failure."""
    global _kg_instance
    if _kg_instance is not None:
        return _kg_instance
    try:
        from backend.core.config import runtime_data_root
        data_dir = str(runtime_data_root() / "knowledge_graph")
        _kg_instance = KnowledgeGraph(data_dir)
        return _kg_instance
    except Exception as exc:
        logger.warning("knowledge_graph_node: failed to initialize KG: %s", exc)
        return None


def _extract_entities(text: str, max_entities: int = 5) -> list[str]:
    """Extract candidate entity names from free text.

    Strategy: pull capitalised multi-word phrases and significant single words
    (length >= 3, not stop words).  De-duplicates while preserving order.
    """
    if not text or not text.strip():
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    # 1. Capitalised phrases (likely proper nouns / entity names)
    for match in re.finditer(r"[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*", text):
        phrase = match.group().strip()
        key = phrase.lower()
        if key not in seen and len(phrase) >= 2:
            candidates.append(phrase)
            seen.add(key)

    # 2. Significant individual words (fallback for lowercase queries)
    for word in re.findall(r"[a-zA-Z]{3,}", text):
        low = word.lower()
        if low not in _STOP_WORDS and low not in seen:
            candidates.append(word)
            seen.add(low)

    return candidates[:max_entities]


# ── Cognitive Pipeline Node Functions ──────────────────────────────────────────

def observation_node(state: AgentState) -> AgentState:
    frame = Observer.observe(
        state["user_input"],
        state.get("chat_session_id") or "kattappa-main-chat",
        current_message_id=state.get("current_chat_message_id")
    )
    state["observation_frame"] = frame
    state["logs"].append("cognitive: observation gathered")
    return state


def attention_node(state: AgentState) -> AgentState:
    frame = Attention.process(state["observation_frame"])
    state["attention_frame"] = frame

    if frame.get("early_exit"):
        exit_type = frame["early_exit"]["type"]
        payload = frame["early_exit"]["payload"]
        state["result"] = payload.get("result") or payload.get("response")
        state["selected_agent"] = payload.get("selected_agent") or payload.get("agent")
        if "logs" in payload:
            state["logs"].extend(payload["logs"])
        state["logs"].append(f"cognitive: early exit via {exit_type}")
    else:
        state["logs"].append("cognitive: attention focused")
    return state


def memory_recall_node(state: AgentState) -> AgentState:
    payload = MemoryRecall.recall(
        state["attention_frame"],
        state.get("chat_session_id") or "kattappa-main-chat",
        query=state.get("memory_query")
    )
    state["memory_payload"] = payload
    
    # Propagate memory confidence level
    conf_level = payload.get("memory_confidence_level", "HIGH")
    state["memory_confidence_level"] = conf_level

    # Initialize Blackboard System Workspace (only if not already initialized)
    from backend.core.blackboard import Blackboard, SharedContext
    if not state.get("blackboard"):
        session_id = state.get("chat_session_id") or "kattappa-main-chat"
        user_intent = state["user_input"]
        
        context = SharedContext(
            session_id=session_id,
            user_intent=user_intent,
            working_memory=payload,
        )
        board = Blackboard(context)
        state["blackboard"] = board
    else:
        board = state["blackboard"]

    if conf_level == "LOW":
        board.add_constraint("memory_recall", "Memory confidence is LOW (timeout or database failure)")

    # Build and format memory_context for planning/reasoning layers with Physical Reality Separation
    facts_parts = []
    executed_actions_parts = []
    simulation_memory_parts = []
    belief_user_profile_parts = []

    # 1. Recent session thread history (chronological) -> FACTS
    hist = payload.get("episodic_history") or []
    for m in hist:
        role_name = m.get("role") or "unknown"
        facts_parts.append(f"- {role_name}: {m.get('content')} [source: READ, confidence: 1.0]")

    # 2. Stored semantic memories -> FACTS
    sem = payload.get("semantic_context") or []
    for s in sem:
        if isinstance(s, dict):
            conf = s.get("confidence", 0.85)
            src = s.get("source_type", "READ")
            facts_parts.append(f"- {s.get('role', 'User')}: {s.get('content')} [source: {src}, confidence: {conf:.2f}]")
        else:
            facts_parts.append(f"- {s} [source: READ, confidence: 0.85]")

    # 3. Autobiographical lessons -> Distributed by source_type (DID, READ, SIMULATED, INFERRED)
    cog = payload.get("cognitive_episodes") or []
    for c in cog:
        if isinstance(c, dict):
            src = c.get("source_type", "INFERRED")
            conf = c.get("composite_score", c.get("confidence", 0.90))
            entry = (
                f"- Event: {c.get('event_summary') or c.get('gist_summary') or c.get('content') or 'None'}, "
                f"Outcome: {c.get('outcome_status') or c.get('outcome') or 'None'}, "
                f"Lesson: {c.get('derived_lesson') or 'None'} [source: {src}, confidence: {conf:.2f}]"
            )
            if src == "DID":
                executed_actions_parts.append(entry)
            elif src == "READ":
                facts_parts.append(entry)
            elif src == "SIMULATED":
                simulation_memory_parts.append(entry)
            elif src == "INFERRED":
                belief_user_profile_parts.append(entry)
            else:
                facts_parts.append(entry)

    # 4. User Relationship Profile -> BELIEF & USER PROFILE
    rel = payload.get("relationship_notes") or {}
    if rel:
        ident = rel.get("identity")
        if isinstance(ident, dict):
            belief_user_profile_parts.append(f"- Identity: {ident.get('name', 'Bala')} [source: INFERRED, confidence: 0.90]")
        trust_m = rel.get("trust_metrics")
        if isinstance(trust_m, dict):
            belief_user_profile_parts.append(f"- Trust Score: {trust_m.get('trust_score', 0.0)} [source: INFERRED, confidence: 0.95]")

    # Assemble context block with explicit headers
    ctx_blocks = []
    
    ctx_blocks.append("### FACTS (Conversation History & Verified Facts)")
    if facts_parts:
        ctx_blocks.extend(facts_parts)
    else:
        ctx_blocks.append("None")
        
    ctx_blocks.append("\n### EXECUTED ACTIONS (Actual System Executions)")
    if executed_actions_parts:
        ctx_blocks.extend(executed_actions_parts)
    else:
        ctx_blocks.append("None")
        
    ctx_blocks.append("\n### SIMULATION MEMORY (Predictions & Hypothetical Scenarios)")
    if simulation_memory_parts:
        ctx_blocks.extend(simulation_memory_parts)
    else:
        ctx_blocks.append("None")
        
    ctx_blocks.append("\n### BELIEF & USER PROFILE (Inferences & Preferences)")
    if belief_user_profile_parts:
        ctx_blocks.extend(belief_user_profile_parts)
    else:
        ctx_blocks.append("None")

    new_ctx = "\n".join(ctx_blocks)
    
    # Cumulative Memory Context accumulation
    depth = state.get("reasoning_recursion_depth", 0)
    if state.get("memory_context") and depth > 0:
        state["memory_context"] = (
            state["memory_context"] + 
            f"\n\n=== RECURSIVE RECALL RESULT (Depth {depth}) ===\n" + 
            new_ctx
        )
    else:
        state["memory_context"] = new_ctx

    if depth > 0 and state.get("blackboard"):
        state["blackboard"].add_fact("recursive_recall", f"Depth {depth} new context retrieved: {new_ctx}")
        
    state["logs"].append("cognitive: memory recall complete")
    return state


def knowledge_graph_node(state: AgentState) -> AgentState:
    """Enrich state context with relationship data from the Knowledge Graph.

    Runs after memory_recall_node and before reasoning_node.
    Lightweight pass-through when no KG data is available or on any error.
    """
    kg = _get_kg()
    if kg is None:
        state["kg_context"] = ""
        state["logs"].append("cognitive: KG unavailable — skipping knowledge graph enrichment")
        return state

    # Gather text sources for entity extraction
    text_sources: list[str] = []
    text_sources.append(state.get("user_input", ""))
    attn = state.get("attention_frame")
    if isinstance(attn, dict):
        text_sources.append(attn.get("clean_message", ""))
        text_sources.append(attn.get("detected_topic", ""))

    combined_text = " ".join(t for t in text_sources if t)
    entities = _extract_entities(combined_text)

    if not entities:
        state["kg_context"] = ""
        state["logs"].append("cognitive: KG — no candidate entities extracted")
        return state

    # Query the KG for each entity and collect results
    sections: list[str] = []
    total_related = 0

    for entity_name in entities:
        try:
            # find_related returns List[Tuple[KGNode, List[str]]]
            related = kg.find_related(entity_name, max_depth=2)
            # traverse returns List[Tuple[KGNode, int, List[str]]]
            traversed = kg.traverse(entity_name, max_depth=2)
        except Exception as exc:
            logger.warning("knowledge_graph_node: query failed for %r: %s", entity_name, exc)
            continue

        if not related and not traversed:
            continue

        total_related += len(related)

        lines: list[str] = [f"#### Entity: {entity_name}"]

        # Related entities via find_related
        if related:
            for kg_node, edge_path in related[:8]:
                path_str = " → ".join(edge_path) if edge_path else "direct"
                lines.append(
                    f"- {kg_node.name} [{kg_node.entity_type}] "
                    f"(confidence: {kg_node.confidence:.2f}, path: {path_str})"
                )

        # Deeper traversal context (depth info)
        if traversed:
            seen_names: set[str] = {r[0].name for r in related} if related else set()
            for kg_node, depth, path in traversed[:6]:
                if kg_node.name == entity_name or kg_node.name in seen_names:
                    continue
                seen_names.add(kg_node.name)
                path_str = " → ".join(path) if path else "direct"
                lines.append(
                    f"- {kg_node.name} [{kg_node.entity_type}] "
                    f"(depth: {depth}, confidence: {kg_node.confidence:.2f}, path: {path_str})"
                )

        if len(lines) > 1:  # header + at least one result
            sections.append("\n".join(lines))

    if not sections:
        state["kg_context"] = ""
        state["logs"].append(
            f"cognitive: KG queried {len(entities)} entities — no related knowledge found"
        )
        return state

    kg_block = (
        "### KNOWLEDGE GRAPH CONTEXT (Related Entities & Relationships)\n"
        + "\n\n".join(sections)
    )
    state["kg_context"] = kg_block

    # Also append to the cumulative memory_context so downstream nodes see it
    if state.get("memory_context"):
        state["memory_context"] = state["memory_context"] + "\n\n" + kg_block

    # Write to blackboard if available
    if state.get("blackboard"):
        state["blackboard"].add_fact(
            "knowledge_graph",
            f"KG enrichment: {len(entities)} entities queried, {total_related} related nodes found"
        )

    state["logs"].append(
        f"cognitive: knowledge graph enriched context with {total_related} related entries "
        f"from {len(entities)} entities"
    )
    return state


def reasoning_node(state: AgentState) -> AgentState:
    from backend.core.model_router import ask_model
    
    # Read query from blackboard if available, otherwise attention frame
    if state.get("blackboard"):
        clean_message = state["blackboard"].context.user_intent
    else:
        clean_message = state["attention_frame"]["clean_message"]
        
    mem_ctx = state["memory_context"] or ""

    prompt = (
        "You are the Kattappa reasoning subsystem. Analyze this user query and the retrieved memory context.\n\n"
        f"User Query: {clean_message}\n\n"
        f"Retrieved Memory Context:\n{mem_ctx}\n\n"
        "Identify if there is any critical missing information or context (e.g. details about a past project, preferences, previous decisions, or code locations) that you need to resolve this request safely and accurately.\n\n"
        "Output ONLY a JSON object in this format:\n"
        "{\n"
        '  "hypothesis": "Draft cognitive execution hypothesis (what actions, tools, and safety boundaries apply)",\n'
        '  "missing_knowledge_gap": "Description of critical missing info, or null if none",\n'
        '  "search_query_for_gap": "A memory search query to retrieve the missing info, or null if none"\n'
        "}"
    )
    
    try:
        raw_res = ask_model(prompt, role="fast")
        import json
        cleaned = raw_res.strip()
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1:
            parsed = json.loads(cleaned[start_idx : end_idx + 1])
        else:
            parsed = json.loads(cleaned)
            
        hypothesis = parsed.get("hypothesis", "")
        gap = parsed.get("missing_knowledge_gap")
        query_gap = parsed.get("search_query_for_gap")
    except Exception as exc:
        hypothesis = f"Standard execution reasoning: query={clean_message!r} (Error generating LLM reasoning: {exc})"
        gap = None
        query_gap = None

    state["reasoning_hypothesis"] = hypothesis.strip()
    
    # Process gaps for Bounded Recursion
    depth = state.get("reasoning_recursion_depth", 0)
    if gap and query_gap and depth < 3:
        state["reasoning_recursion_depth"] = depth + 1
        state["memory_query"] = query_gap
        state["reasoning_gaps"] = gap
        
        # Write gap to blackboard
        if state.get("blackboard"):
            state["blackboard"].add_assumption("reasoning", f"Missing info gap detected: {gap}")
            
        state["logs"].append(f"cognitive: reasoning detected knowledge gap: {gap!r}. Requesting recursive recall (depth={state['reasoning_recursion_depth']}).")
    else:
        state["reasoning_gaps"] = None
        
        # Write to blackboard
        if state.get("blackboard"):
            state["blackboard"].add_agent_output("reasoning", {"hypothesis": hypothesis.strip()})
            
        state["logs"].append("cognitive: reasoning hypothesis drafted")
        
    return state


def council_debate_node(state: AgentState) -> AgentState:
    reasoning_hyp = state.get("reasoning_hypothesis")
    # Read from blackboard if available
    if state.get("blackboard"):
        board = state["blackboard"]
        reasoning_entries = [e for e in board.entries() if e.source == "reasoning"]
        if reasoning_entries:
            reasoning_hyp = reasoning_entries[-1].content.get("hypothesis") or reasoning_hyp

    res = CouncilDebate.debate(
        state["attention_frame"],
        state["memory_payload"],
        reasoning_hyp
    )
    state["council_debate_result"] = res

    # Write to blackboard
    if state.get("blackboard"):
        if res.get("status") == "rejected":
            state["blackboard"].add_constraint("council_debate", {"status": "rejected", "reasons": res.get("reasons", [])})
        else:
            state["blackboard"].add_agent_output("council_debate", res)

    if res.get("status") == "rejected":
        brahma_rat = next((v.get("rationale") for v in res.get("votes", []) if v.get("perspective") == "Brahma"), "No rationale.")
        shiva_rat = next((v.get("rationale") for v in res.get("votes", []) if v.get("perspective") == "Shiva"), "No rationale.")
        rama_rat = next((v.get("rationale") for v in res.get("votes", []) if v.get("perspective") == "Rama"), "No rationale.")
        reasons = "\n".join(res.get("reasons", []))

        tradeoff_response = (
            "### Personality Council Deliberation\n\n"
            f"**Brahma (Engineering & Creation Lens):**\n"
            f"> {brahma_rat}\n\n"
            f"**Shiva (Risk & Destruction Lens):**\n"
            f"> {shiva_rat}\n\n"
            f"**Rama (Integrity & Stability Lens):**\n"
            f"> {rama_rat}\n\n"
            f"**Tradeoff & Decision Summary:**\n"
            f"The council deliberated on: \"{state['attention_frame']['clean_message']}\".\n"
            f"- **Decision / Reason:** {reasons if reasons else 'Rejected by Personality Council.'}"
        )
        state["result"] = tradeoff_response
        state["selected_agent"] = "personality_council"
        state["logs"].append("cognitive: rejected by Personality Council")
    elif res.get("requires_human_approval"):
        state["approval_required"] = True
        state["risk_level"] = "medium"
        state["logs"].append("cognitive: Personality Council requires human approval")
    else:
        state["logs"].append("cognitive: Personality Council approved hypothesis")
    return state


def safety_review_node(state: AgentState) -> AgentState:
    plan_data = {
        "steps": [
            {
                "tool": state.get("selected_agent"),
                "action": "execute",
                "args": {"input": state["user_input"]}
            }
        ]
    }
    if state.get("plan"):
        try:
            parsed = json.loads(state["plan"])
            if isinstance(parsed, dict) and "steps" in parsed:
                plan_data = parsed
        except Exception:
            pass

    # Read from blackboard if available to check existing constraints
    if state.get("blackboard"):
        board = state["blackboard"]
        # Can inspect constraints / decisions
        existing_constraints = [e for e in board.entries() if e.kind.value == "constraint"]

    res = SafetyReview.review(
        plan_data,
        state.get("chat_session_id") or "kattappa-main-chat",
        state.get("trust_tag", "SYSTEM_TRUST")
    )

    if not res.get("is_safe"):
        state["approval_required"] = True
        state["risk_level"] = "medium" if res.get("risk_level", 2) < 5 else "high"
        state["result"] = f"Safety Block: {res.get('rejection_reason')}"
        state["selected_agent"] = "safety"
        
        # Write constraint to blackboard
        if state.get("blackboard"):
            state["blackboard"].add_constraint("safety_review", {"is_safe": False, "rejection_reason": res.get("rejection_reason")})
            
        state["logs"].append(f"cognitive: safety review blocked - {res.get('rejection_reason')}")
    else:
        # Write fact to blackboard
        if state.get("blackboard"):
            state["blackboard"].add_fact("safety_review", {"is_safe": True})
            
        state["logs"].append("cognitive: safety review passed")
    return state


def metacognition_node(state: AgentState) -> AgentState:
    # Read from blackboard if available to check context/constraints
    if state.get("blackboard"):
        board = state["blackboard"]
        # Can check for any constraints that might force actions
        # e.g., low confidence or safety violations
        pass

    parsed = MetacognitiveGate.verify_grounding(state)
    state["metacognitive_action"] = parsed.get("recommended_action", "ANSWER")
    
    # Write to blackboard
    if state.get("blackboard"):
        state["blackboard"].add_agent_output("metacognition", parsed)
    
    # If action is RE_RETRIEVE, increment retrieve count
    if state["metacognitive_action"] == "RE_RETRIEVE":
        state["re_retrieve_count"] = state.get("re_retrieve_count", 0) + 1
        new_query = parsed.get("new_search_query")
        if new_query:
            state["memory_query"] = new_query
            state["logs"].append(f"cognitive: metacognitive gate requested re-retrieval with query: {new_query!r}")
        else:
            state["logs"].append("cognitive: metacognitive gate requested re-retrieval but no new query was provided")
    else:
        # Generate result if direct output action and no result exists yet
        if state["metacognitive_action"] == "ANSWER" and not state.get("result"):
            from backend.core.model_router import ask_model
            prompt = (
                "You are Kattappa. Answer the user request directly and concisely based on the retrieved memory context.\n\n"
                f"User Request: {state['user_input']}\n\n"
                f"Memory Context:\n{state.get('memory_context') or 'None'}\n"
            )
            try:
                state["result"] = ask_model(prompt, role="general")
            except Exception as e:
                state["result"] = f"Error generating answer: {e}"
        elif state["metacognitive_action"] == "ASK_CLARIFICATION" and not state.get("result"):
            from backend.core.model_router import ask_model
            prompt = (
                "You are Kattappa. Ask the user for clarification about their request.\n\n"
                f"User Request: {state['user_input']}\n"
            )
            try:
                state["result"] = ask_model(prompt, role="general")
            except Exception as e:
                state["result"] = f"Clarification request: {e}"
        elif state["metacognitive_action"] == "ABSTAIN" and not state.get("result"):
            from backend.core.model_router import ask_model
            prompt = (
                "You are Kattappa. Politely explain that you cannot perform or answer this request safely.\n\n"
                f"User Request: {state['user_input']}\n"
            )
            try:
                state["result"] = ask_model(prompt, role="general")
            except Exception as e:
                state["result"] = f"I cannot fulfill this request safely. Error: {e}"
                
        state["logs"].append(f"cognitive: metacognitive gate approved action: {state['metacognitive_action']}")
        
    return state


def world_model_node(state: AgentState) -> AgentState:
    from backend.core.model_router import ask_model
    import uuid

    selected_agent = state.get("selected_agent") or "unknown"
    user_input = state.get("user_input", "")
    plan = state.get("plan") or ""
    
    # Read from blackboard if available to check context
    if state.get("blackboard"):
        board = state["blackboard"]
        # E.g. Check constraints or reasoning outputs
        pass

    prompt = (
        "You are the Kattappa World Model Simulator. Simulate the execution of the planned action/agent.\n\n"
        f"Planned Agent/Action: {selected_agent}\n"
        f"User Input: {user_input}\n"
        f"Execution Plan: {plan}\n\n"
        "Predict the outcomes of this execution.\n"
        "Return ONLY a JSON object in this format:\n"
        "{\n"
        '  "predicted_success": <float 0.0-1.0>,\n'
        '  "predicted_cost": <float (estimated computational or execution cost, e.g. 0.0-10.0)>,\n'
        '  "predicted_time": "<string describing expected duration, e.g. \'100ms\', \'2s\'>",\n'
        '  "confidence_interval": [<float low>, <float high>],\n'
        '  "risk_score": <float 0.0-1.0>\n'
        "}"
    )

    prediction_id = state.get("current_chat_message_id") or f"wm-pred-{uuid.uuid4()}"
    
    try:
        raw_res = ask_model(prompt, role="fast")
        cleaned = raw_res.strip()
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1:
            parsed = json.loads(cleaned[start_idx : end_idx + 1])
        else:
            parsed = json.loads(cleaned)
            
        success = float(parsed.get("predicted_success", 0.9))
        cost = float(parsed.get("predicted_cost", 1.0))
        duration = str(parsed.get("predicted_time", "500ms"))
        interval = parsed.get("confidence_interval", [0.8, 1.0])
        if isinstance(interval, list) and len(interval) == 2:
            confidence_interval = (float(interval[0]), float(interval[1]))
        else:
            confidence_interval = (0.8, 1.0)
        risk = float(parsed.get("risk_score", 0.1))
        
    except Exception as e:
        success = 0.95
        cost = 1.0
        duration = "200ms"
        confidence_interval = (0.9, 1.0)
        risk = 0.05
        
    try:
        WorldModel.record_prediction(
            prediction_id=prediction_id,
            action=selected_agent,
            predicted_success=success,
            predicted_cost=cost,
            predicted_time=duration,
            confidence_interval=confidence_interval,
            risk_score=risk,
        )
        prediction_dict = {
            "prediction_id": prediction_id,
            "action": selected_agent,
            "predicted_success": success,
            "predicted_cost": cost,
            "predicted_time": duration,
            "confidence_interval": confidence_interval,
            "risk_score": risk,
        }
        state["world_model_prediction"] = prediction_dict
        
        # Write to blackboard
        if state.get("blackboard"):
            state["blackboard"].add_agent_output("world_model", prediction_dict)
            
        state["logs"].append(f"cognitive: pre-action world model simulation recorded for action {selected_agent!r} (success prediction={success:.2f})")
    except Exception as e:
        state["logs"].append(f"cognitive: failed to record world model prediction: {e}")

    return state


# ── State Graph Assembly ──────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)
    
    # Core Thinking Nodes
    graph.add_node("executive", executive_node)
    graph.add_node("observation", observation_node)
    graph.add_node("attention", attention_node)
    graph.add_node("memory", memory_recall_node)
    graph.add_node("knowledge_graph", knowledge_graph_node)
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("metacognition", metacognition_node)
    graph.add_node("council_debate", council_debate_node)
    graph.add_node("planner", planner_node)
    graph.add_node("world_model", world_model_node)
    graph.add_node("safety", safety_review_node)

    # Specialist Nodes
    graph.add_node("coder", coder_node)
    graph.add_node("builder", builder_node)
    graph.add_node("browser", browser_node)
    graph.add_node("desktop", desktop_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("vision", vision_node)
    graph.add_node("voice", voice_node)
    graph.add_node("file", file_node)
    graph.add_node("terminal", terminal_node)
    graph.add_node("finance", finance_node)
    graph.add_node("self_improver", self_improver_node)
    graph.add_node("monitoring", monitoring_node)
    graph.add_node("evaluator", evaluator_node)

    # entry & routing edges
    graph.set_entry_point("executive")
    graph.add_conditional_edges(
        "executive",
        route_executive,
        {
            "evaluator": "evaluator",
            "observation": "observation",
        }
    )
    graph.add_edge("observation", "attention")
    graph.add_conditional_edges(
        "attention",
        route_attention,
        {
            "metacognition": "metacognition",
            "memory": "memory",
        }
    )
    graph.add_edge("memory", "knowledge_graph")
    graph.add_edge("knowledge_graph", "reasoning")
    graph.add_conditional_edges(
        "reasoning",
        route_reasoning,
        {
            "memory": "memory",
            "metacognition": "metacognition",
        }
    )
    
    graph.add_conditional_edges(
        "metacognition",
        route_metacognition,
        {
            "memory": "memory",
            "safety": "safety",
            "council_debate": "council_debate",
        }
    )
    
    graph.add_conditional_edges(
        "council_debate",
        route_council,
        {
            "evaluator": "evaluator",
            "planner": "planner",
        }
    )
    graph.add_edge("planner", "world_model")
    graph.add_edge("world_model", "safety")
    graph.add_conditional_edges(
        "safety",
        route_agent,
        {
            "coder": "coder",
            "builder": "builder",
            "browser": "browser",
            "desktop": "desktop",
            "researcher": "researcher",
            "vision": "vision",
            "voice": "voice",
            "file": "file",
            "terminal": "terminal",
            "finance": "finance",
            "self_improver": "self_improver",
            "monitoring": "monitoring",
            "evaluator": "evaluator",
        },
    )

    for node in [
        "coder",
        "builder",
        "browser",
        "desktop",
        "researcher",
        "vision",
        "voice",
        "file",
        "terminal",
        "finance",
        "self_improver",
        "monitoring",
    ]:
        graph.add_edge(node, "evaluator")

    graph.add_conditional_edges(
        "evaluator",
        route_evaluator,
        {
            "safety": "safety",
            "end": END,
        },
    )
    return graph.compile()


compiled_graph = build_graph()


def run_graph(
    user_input: str,
    approved_approval_id: str | None = None,
    chat_session_id: str | None = None,
    current_chat_message_id: str | None = None,
    memory_query: str | None = None,
    ephemeral_worker: bool = False,
    trust_tag: str = "SYSTEM_TRUST",
) -> AgentState:
    state: AgentState = {
        "user_input": user_input,
        "memory_query": memory_query,
        "chat_session_id": chat_session_id,
        "current_chat_message_id": current_chat_message_id,
        "ephemeral_worker": ephemeral_worker,
        "plan": None,
        "selected_agent": None,
        "memory_context": None,
        "related_messages": [],
        "approval_id": None,
        "approved_approval_id": approved_approval_id,
        "approved": approved_approval_id is not None,
        "double_approved": False,
        "approval_required": False,
        "risk_level": "unknown",
        "result": None,
        "logs": [],
        "operator_plan": None,
        "trust_tag": trust_tag,
        # Cognitive fields
        "observation_frame": None,
        "attention_frame": None,
        "memory_payload": None,
        "council_debate_result": None,
        "reasoning_hypothesis": None,
        "stakes_level": "low",
        "reversibility": "reversible",
        "required_confidence": 0.50,
        "path_selected": "FAST",
        "metacognitive_action": "ANSWER",
        "world_model_prediction": None,
        "re_retrieve_count": 0,
        "blackboard": None,
        "memory_confidence_level": "HIGH",
        "reasoning_recursion_depth": 0,
        "reasoning_gaps": None,
        "kg_context": None,
    }

    result = compiled_graph.invoke(state)
    log_event(
        f"request={user_input!r} agent={result.get('selected_agent')} risk={result.get('risk_level')}"
    )
    return result
