"""
Skill Memory — Step 23
=======================
Kattappa's self-model of what it knows and how well it knows it.

Each "skill" maps to a domain string (e.g. "translation", "reasoning",
"python", "rf_systems"). The SkillProfile for each domain tracks:

  - Confidence        → matches ConfidenceTracker values
  - Attempts          → total number of times this skill was exercised
  - Successes         → subset of attempts that succeeded
  - Success Rate      → successes / attempts (live computed)
  - Learning Velocity → rolling rate of confidence gain per 10 attempts
  - Last Used         → ISO-8601 UTC timestamp
  - Weaknesses        → list of identified knowledge gaps from LearningEngine
  - Notes             → free-form remarks

This lets Kattappa answer "what do I know?" and "how well do I know it?"
at any time — a prerequisite for realistic planning and self-improvement.

Persistence: JSON file (one dict per domain).

Public API
----------
    from kattappa_runtime.skill_memory import SkillMemory

    sm = SkillMemory()
    sm.record_attempt("translation", succeeded=True,  confidence_delta=+0.05)
    sm.record_attempt("rf_systems",  succeeded=False, confidence_delta=-0.10)
    sm.add_weakness("rf_systems", "impedance matching calculation failed")

    profile = sm.get("rf_systems")
    print(profile.success_rate)   # 0.0 (first attempt failed)
    print(profile.weaknesses)     # ["impedance matching calculation failed"]

    sm.summary_table()            # tabular view of all skills
"""

from kattappa_runtime.skill_memory.store import SkillMemory, SkillProfile

__all__ = ["SkillMemory", "SkillProfile"]
