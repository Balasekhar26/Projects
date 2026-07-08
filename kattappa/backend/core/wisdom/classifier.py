"""Decision Classifier — Phase K9 (multi-label upgrade).

Routes a question/context to one or more reasoning engines using weighted
multi-label classification.  A single input can produce multiple labels with
weights, enabling blended pipeline routing.

Label taxonomy (12 types)
──────────────────────────
  CODING        → code/debug/algorithm path
  ENGINEERING   → hardware/circuit/system design
  SCIENTIFIC    → research, papers, evidence, explanation
  CREATIVE      → writing, design, ideation
  TEACHING      → explain, tutorial, help understand
  ETHICAL       → moral, fairness, harm, responsibility
  EMOTIONAL     → feelings, stress, personal struggles
  STRATEGIC     → high-level planning, vision, roadmap
  RESEARCH      → find information, investigate
  PLANNING      → concrete next steps, task breakdown
  CONVERSATION  → social, informal, chat
  REFLECTION    → insights, lessons, self-evaluation

Routing contract
─────────────────
  If CODING, ENGINEERING, SCIENTIFIC, RESEARCH → ScienceEngine
  All others → WisdomEngine (for any label with weight >= 0.3)
  Labels can co-exist:  "Help me resign politely" → CONVERSATION(0.5) + EMOTIONAL(0.5) + PLANNING(0.3)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Label definitions ──────────────────────────────────────────────────────────

SCIENCE_LABELS = {"CODING", "ENGINEERING", "SCIENTIFIC", "RESEARCH"}
WISDOM_LABELS  = {"ETHICAL", "EMOTIONAL", "STRATEGIC", "PLANNING",
                  "CONVERSATION", "REFLECTION", "TEACHING", "CREATIVE"}


@dataclass
class LabelWeight:
    label: str
    weight: float   # 0.0–1.0 (relative confidence for this label)


@dataclass
class ClassificationResult:
    labels: list[LabelWeight]          # sorted descending by weight
    primary: str                       # highest-weight label
    use_wisdom_engine: bool
    use_science_engine: bool
    suggested_domains: list[str]       # wisdom domain tags from highest applicable labels
    reasoning: str

    # Convenience: backwards-compatible single-label access
    @property
    def question_type(self) -> str:
        return self.primary


# ── Signal tables (regex patterns, scored by weight) ──────────────────────────

_SIGNALS: dict[str, tuple[tuple[str, float], ...]] = {
    "CODING": (
        (r"\b(code|debug|function|class|method|variable|syntax|script|module|import)\b", 1.0),
        (r"\b(python|javascript|typescript|java|c\+\+|rust|go|swift|kotlin)\b", 1.0),
        (r"\b(algorithm|data structure|recursion|loop|iterator|lambda)\b", 0.8),
        (r"\b(sql|query|database|orm|migration|schema|index)\b", 0.9),
        (r"\b(api|endpoint|http|rest|graphql|websocket|request|response)\b", 0.8),
        (r"\b(compile|build|deploy|docker|kubernetes|ci/cd|pipeline)\b", 0.7),
    ),
    "ENGINEERING": (
        (r"\b(circuit|resistor|capacitor|transistor|voltage|current|ohm)\b", 1.0),
        (r"\b(radar|rf|fmcw|doppler|dsp|adc|dac|fpga|microcontroller|embedded)\b", 1.0),
        (r"\b(hardware|pcb|schematic|oscilloscope|multimeter|signal)\b", 0.9),
        (r"\b(amplifier|filter|antenna|frequency|bandwidth|spectrum)\b", 0.8),
        (r"\b(sensor|actuator|motor|servo|pwm|gpio|i2c|spi|uart)\b", 0.8),
    ),
    "SCIENTIFIC": (
        (r"\b(physics|chemistry|biology|mathematics|neuroscience|quantum)\b", 1.0),
        (r"\b(theorem|proof|formula|equation|constant|experiment|hypothesis)\b", 0.9),
        (r"\b(explain how|why does|what causes|mechanism|theory|model)\b", 0.7),
    ),
    "RESEARCH": (
        (r"\b(research|paper|study|journal|evidence|citation|literature)\b", 1.0),
        (r"\b(find information|investigate|look up|search for)\b", 0.8),
        (r"\b(data|statistics|survey|meta-analysis|systematic review)\b", 0.7),
    ),
    "CREATIVE": (
        (r"\b(write|creative|story|poem|design|brainstorm|generate|idea)\b", 0.9),
        (r"\b(imagine|invent|novel|original|unique|artistic)\b", 0.8),
    ),
    "TEACHING": (
        (r"\b(teach me|help me understand|explain|tutorial|beginner|introduction)\b", 1.0),
        (r"\b(how does .{1,30} work|what is .{1,30} used for)\b", 0.8),
        (r"\b(example|demonstration|walkthrough|step by step)\b", 0.6),
    ),
    "ETHICAL": (
        (r"\b(should i|is it right|is it wrong|ethical|moral|fair|honest)\b", 1.0),
        (r"\b(duty|responsibility|harm|safe|dangerous|allowed|forbidden|consent)\b", 0.9),
        (r"\b(bias|privacy|discrimination|rights|justice|equitable)\b", 0.8),
    ),
    "EMOTIONAL": (
        (r"\b(feel|feeling|stressed|anxious|overwhelmed|sad|frustrated|angry|lost)\b", 1.0),
        (r"\b(burnout|exhausted|motivated|inspired|passionate|excited)\b", 0.9),
        (r"\b(relationship|family|friend|colleague|manager|team)\b", 0.6),
        (r"\b(resign|quit|leave|move on|difficult decision)\b", 0.7),
    ),
    "STRATEGIC": (
        (r"\b(long.term|vision|mission|strategy|architecture|direction|roadmap)\b", 1.0),
        (r"\b(competitive|market|position|differentiate|advantage|opportunity)\b", 0.8),
        (r"\b(invest|priority|resource allocation|trade.?off|risk|impact)\b", 0.7),
    ),
    "PLANNING": (
        (r"\b(plan|milestone|next step|timeline|schedule|deadline|objective)\b", 1.0),
        (r"\b(how (do|can|should) i achieve|goal|target|deliverable)\b", 0.9),
        (r"\b(breakdown|decompose|action item|to.?do|checklist)\b", 0.8),
    ),
    "CONVERSATION": (
        (r"\b(hello|hi|hey|thanks|thank you|goodbye|bye|how are you)\b", 1.0),
        (r"\b(tell me|chat|talk|discuss|conversation|opinion)\b", 0.7),
        (r"\b(politely|professionally|diplomatically|tactfully)\b", 0.8),
        (r"\b(message|email|letter|respond to|reply to)\b", 0.6),
    ),
    "REFLECTION": (
        (r"\b(what (have|did) (i|we) learn|lessons?|insight|retrospect)\b", 1.0),
        (r"\b(reflect|review|evaluate|assess|look back|patterns?)\b", 0.9),
        (r"\b(improve|growth|progress|evolution|maturity)\b", 0.6),
    ),
}


class DecisionClassifier:
    """Multi-label decision classifier with weighted confidence per label."""

    @classmethod
    def classify(
        cls,
        question: str,
        context: dict | None = None,
    ) -> ClassificationResult:
        lower = question.lower()
        raw_scores: dict[str, float] = {}

        for label, patterns in _SIGNALS.items():
            score = 0.0
            for pattern, weight in patterns:
                if re.search(pattern, lower):
                    score = max(score, weight)
            if score > 0:
                raw_scores[label] = score

        if not raw_scores:
            raw_scores["CONVERSATION"] = 0.4   # fallback

        # Normalize to 0-1 range relative to the max score
        max_score = max(raw_scores.values())
        normalized = {k: v / max_score for k, v in raw_scores.items()}

        # Only keep labels with normalized weight >= 0.3 (meaningful signal)
        significant = {k: v for k, v in normalized.items() if v >= 0.3}
        if not significant:
            significant = {"CONVERSATION": 0.4}

        # Sort descending
        sorted_labels = sorted(significant.items(), key=lambda x: -x[1])
        label_weights = [LabelWeight(label=k, weight=v) for k, v in sorted_labels]
        primary = label_weights[0].label

        use_science = any(lw.label in SCIENCE_LABELS for lw in label_weights)
        use_wisdom  = any(lw.label in WISDOM_LABELS  for lw in label_weights)

        domains = cls._extract_domains(label_weights)
        reasoning = (
            f"Multi-label: {[(lw.label, round(lw.weight, 2)) for lw in label_weights]}. "
            f"Primary={primary}. science={use_science}, wisdom={use_wisdom}"
        )

        return ClassificationResult(
            labels=label_weights,
            primary=primary,
            use_wisdom_engine=use_wisdom,
            use_science_engine=use_science,
            suggested_domains=domains,
            reasoning=reasoning,
        )

    @staticmethod
    def _extract_domains(label_weights: list[LabelWeight]) -> list[str]:
        mapping: dict[str, list[str]] = {
            "ETHICAL":      ["ethics", "decision_making"],
            "EMOTIONAL":    ["discipline", "balance", "uncertainty"],
            "STRATEGIC":    ["long_term_planning", "priorities"],
            "PLANNING":     ["planning", "priorities"],
            "CONVERSATION": ["trust"],
            "REFLECTION":   ["self_improvement", "learning"],
            "CREATIVE":     ["planning"],
            "TEACHING":     ["knowledge_over_material"],
        }
        seen: set[str] = set()
        domains: list[str] = []
        for lw in label_weights:
            for d in mapping.get(lw.label, []):
                if d not in seen:
                    seen.add(d)
                    domains.append(d)
        return domains
