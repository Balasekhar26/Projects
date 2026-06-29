# K21-48: Performance Benchmarks & Budgets

This document specifies the execution latency limits, throughput requirements, and memory constraints for the World Model.

---

## 1. Latency & Throughput Targets

To support real-time planning, World Model operations must satisfy the following bounds under a standard load (up to 1,000 active entities):

| Operation | Target Latency | Maximum Allowable | Metric Type |
| :--- | :--- | :--- | :--- |
| **Branch Creation** | $\le 5\text{ms}$ | $10\text{ms}$ | p95 latency |
| **Branch Query** | $\le 2\text{ms}$ | $5\text{ms}$ | p99 latency |
| **Transition Evaluation** | $\le 15\text{ms}$ | $30\text{ms}$ | p95 latency |
| **Event Append** | $\le 10\text{ms}$ | $20\text{ms}$ | p95 latency |
| **Branch Merge** | $\le 20\text{ms}$ | $50\text{ms}$ | p95 latency |

---

## 2. Resource Budgets

- **Peak RAM Overhead**: The World Model's in-memory footprint (caches and active branch deltas) must remain $\le 50\text{MB}$ under normal execution.
- **Disk Footprint**: Database size growth must not exceed `100KB` per 1,000 processed events, enforced via event pruning and transaction packaging.
