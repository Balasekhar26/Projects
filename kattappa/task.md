# Proactive Safety Controller — Task List

- [x] **Component 1** — Update `schema.py` (SubsystemBudget MB limits, pageout/swapout rates, conservative thresholds, training budgets)
- [x] **Component 2** — Update `monitor.py` (parse pageouts/swapouts from vm_stat and calculate rates)
- [x] **Component 3** — Update `governor.py` (absolute budget checks in MB and CPU %)
- [x] **Component 4** — Update `safety_controller.py` (heavyweight lock, detailed memory estimation, early warning/pause checks)
- [x] **Component 5** — Refactor `trainer.py` (wrap context locks, step-based curriculum, proactive admission control loop)
- [x] Implement 1-second thread heartbeat logger in `trainer.py` and `monitor.py`
- [x] **Component 6** — Update `run_safe.sh` & `run_alpha.sh` (new thresholds)
- [/] **Verification** — Run unit tests + smoke test check
    - [x] Resumed pretraining from step 29,900 with context length capped at 1024 to prevent 2048 MPS OOM
