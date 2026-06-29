# K21: Failure Analysis & Mitigation

---

## 1. Risks & Failure Modes

### F-01: Graph Explosion
- **Problem**: High frequency write logs create millions of transient nodes, consuming excess memory/storage.
- **Severity**: High.
- **Mitigation**: Implement automatic pruning and garbage collection (GC) matching the forgetting rules.

### F-02: Simulation Drift
- **Problem**: Long-horizon forecasts drift from reality due to accumulated approximation errors.
- **Severity**: Medium.
- **Mitigation**: Enforce maximum projection horizons (e.g. 5 steps) and degrade confidence exponentially at each step.

### F-03: Thread Lock Contention
- **Problem**: Concurrent sub-agent evaluations lock SQLite connection.
- **Severity**: High.
- **Mitigation**: Use connection pooling and write-ahead logging (WAL) mode for database writes.

---

## 2. Mitigation Policies

- **Emergency Rollback**: If database file corruption is detected, reload the latest checkpoint backups.
- **Event storm gating**: Throttle simulation frequency if the thought queue exceeds 50 steps.
