# K21-39: Failure Recovery Specification

This document details database recovery, backup checkpoints, and crash-safe transaction rollbacks.

---

## 1. Crash Safety & WAL Journaling

To prevent database corruption in the event of unexpected system halts (e.g. process termination, power loss):
- **WAL Journaling**: SQLite connections enable Write-Ahead Logging (`PRAGMA journal_mode=WAL;`). Updates are appended to a WAL file before being committed to the main database file.
- **Synchronous Commits**: DB writes are executed with `PRAGMA synchronous=NORMAL;` ensuring atomic transactions on disk.

---

## 2. Checkpoints & Rollbacks

- **Automated Checkpoints**: The `WorldModelCoordinator` triggers database snapshot checkpoints every 1,000 transactions or on schedule.
- **Rollback Log**: In case of transition failure:
  - If a transaction is aborted, SQLite executes an atomic `ROLLBACK`.
  - To revert a merged branch, the coordinator reads inverse events from the `Event Log` and applies inverse deltas, restoring state to 100% of its previous values.
- **Validation**: Replay tests verify snapshot restore fidelity.
