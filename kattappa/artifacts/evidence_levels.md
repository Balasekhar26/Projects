# Kattappa Evidence Levels (E0 - E5)

To prevent unverified assumptions from quietly becoming treated as architectural facts, Kattappa assigns an evidence level to every major design choice.

---

## The Evidence Hierarchy

| Level | Designation | Description / Verification Requirement |
| :--- | :--- | :--- |
| **E0** | **Intuition** | Initial concept, hypothesis, or design idea without empirical support. |
| **E1** | **Literature** | Design based on established scientific publications or models (e.g. GWT, SOAR). |
| **E2** | **Experiment** | Validated in a small-scale sandbox or single test case. |
| **E3** | **Internal Replicated** | Successfully replicated across multiple unit and integration test runs. |
| **E4** | **Benchmarked** | Continuously validated against standard benchmark metrics ($p < 0.05$). |
| **E5** | **Production Stable** | Running stably as a core, regression-free capability in the active system. |
