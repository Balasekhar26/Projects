# Proactive Safety Controller — Task List

- [x] **Component 1** — Update `schema.py` (SubsystemBudget MB limits, pageout/swapout rates, conservative thresholds, training budgets)
- [x] **Component 2** — Update `monitor.py` (parse pageouts/swapouts from vm_stat and calculate rates)
- [x] Extend `ledger_store.py` interface for capability contracts
- [x] Extend `sqlite_store.py` schema (table + dynamic alter table migration) and CRUD methods
- [x] **Component 4** — Update `safety_controller.py` (heavyweight lock, detailed memory estimation, early warning/pause checks)
- [x] **Component 5** — Refactor `trainer.py` (wrap context locks, step-based curriculum, proactive admission control loop)
- [x] Implement 1-second thread heartbeat logger in `trainer.py` and `monitor.py`
- [x] **Component 6** — Update `run_safe.sh` & `run_alpha.sh` (new thresholds)
- [x] **Integration Checklist**
    - [x] TASK 1: Document live execution path in graph.py
    - [x] TASK 2: Insert planner outputs inside planner_node
    - [x] TASK 3: Implement Goal Extraction parsing rules
    - [x] TASK 4: Map steps directly to agent routing queue
    - [x] TASK 5: Update BeliefStore & Memories on finish
    - [x] TASK 6: Implement Failure Reflection (retry/replan/abort)
    - [x] TASK 7: Persist checkpoints across process restart
- [x] **Verification** — Run unit tests + smoke test check
    - [x] Resumed pretraining from step 29,900 with context length capped at 1024 to prevent 2048 MPS OOM
