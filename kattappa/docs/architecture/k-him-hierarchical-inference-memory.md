# K-HIM: Kattappa Hierarchical Inference Memory Engine

## 1. Architectural Purpose & Scope

**K-HIM (Kattappa Hierarchical Inference Memory Engine)** is Kattappa's native SSD-streamed inference runtime designed to execute compatible models larger than physical system RAM while keeping all Kattappa-owned processes strictly under a configurable **8.0 GB total process-tree RAM ceiling** (defined as `KATTAPPA_MAX_PROCESS_TREE_MEMORY_BYTES = 8_000_000_000` bytes, approximately 7.45 GiB).

Rather than acting merely as an adapter to external inference engines, Kattappa owns model admission, tensor placement, SSD storage layout, expert cache policies, prefetch scheduling, KV-cache budgeting, process supervision, RAM enforcement, live telemetry, and fallback behavior.

---

## 2. Four-Tier Memory Hierarchy

```text
+-------------------------------------------------------------+
| GPU VRAM                                                    |
| Hot tensors and active expert execution buffers            |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
| System RAM (Hard Kattappa limit: 8.0 GB total process-tree) |
| Resident model core, quantized KV cache, active workspace   |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
| 2 TB SSD                                                    |
| Interface and measured bandwidth: TBD during K-HIM-0        |
| Cold experts, model weight shards, inactive tensor store   |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
| 500 GB HDD                                                  |
| Long-term backups, archived models, historical datasets     |
+-------------------------------------------------------------+
```

---

## 3. Mode-Specific RAM Budgets

The 8.0 GB limit applies to the complete Kattappa-owned process tree (control plane, sidecars, resident models, caches, and tools).

### 3.1 Interactive Mode

| Domain | Maximum Budget | Description |
| :--- | :---: | :--- |
| **Control plane, policy, and memory** | **1.30 GB** | Core orchestrator, state engines, security governors |
| **Voice, UI, and automation** | **0.70 GB** | Playwright, TTS/STT helpers, desktop sidecars |
| **Fast resident model** | **2.30 GB** | Low-latency interactive chat and tool-routing model, subject to measured hardware performance |
| **Working memory and telemetry** | **0.70 GB** | Context buffers, telemetry trackers, live stats |
| **I/O and temporary buffers** | **0.40 GB** | Temporary execution workspace |
| **Safety reserve** | **0.80 GB** | Host safety margin |
| **Target Peak** | **6.20 GB** | **Interactive Mode Target** |

### 3.2 Deep Reasoning Mode

| Domain | Maximum Budget | Description |
| :--- | :---: | :--- |
| **Control plane, policy, and memory** | **1.30 GB** | Core orchestrator, state engines, security governors |
| **Minimal voice/UI/tool bridge** | **0.30 GB** | Scaled-down automation bridge |
| **Resident model core and hot experts** | **4.50 GB** | MoE core parameters and active expert cache |
| **KV cache and I/O buffers** | **1.00 GB** | Quantized KV cache pages and async read buffers |
| **Telemetry and supervisor** | **0.20 GB** | Governor daemon, telemetry loggers |
| **Emergency reserve** | **0.70 GB** | Host safety margin |
| **Hard Peak Ceiling** | **8.00 GB** | **Deep Reasoning Hard Ceiling** |

*Note: The fast resident model must be fully unloaded, suspended, or reduced before the deep inference runtime receives its full cache allocation.*

---

## 4. Two-Mind System Architecture

```text
User Request
    |
    v
+-------------------------------------------------------------+
| Complexity & Permission Router                              |
+-------------------------------------------------------------+
    |                                           |
    v                                           v
[Fast Interactive Task]                     [Deep Reasoning Task]
Small model fully resident                  Large SSD-streamed MoE model
Voice, desktop, browser, chat               Architecture, science, research
                                            (Produces plans; permission
                                             system retains control)
```

- **Fast Interactive Task**: Small resident model (< 2.0 GB RAM) for low-latency interactive tasks, subject to measured model, CPU and hardware performance.
- **Deep Reasoning Task**: SSD-streamed MoE model for complex reasoning. The deep reasoning model produces structured plans and analysis; Kattappa's security, permission, and execution systems maintain absolute control.

---

## 5. Expert Routing & Prefetch Architecture

```text
Native MoE Router Logits
        |
        v
Selected experts for current layer
        |
        v
Prefetch scheduler uses routing information
and recent expert-transition statistics
        |
        v
SSD reads issued before expert execution
```

1. **Authoritative Selector**: The model's **native MoE router or gating logits** determine which experts are required for each layer and token.
2. **Prefetch Scheduler**: Analyzes native routing logits and historical layer transition probabilities to issue async SSD read requests before execution reaches subsequent layers.

---

## 6. Model Compatibility Matrix

| Model Class | K-HIM Suitability | Architectural Rationale |
| :--- | :--- | :--- |
| **Sparse MoE** | **High** | Only selected experts activate per token; ideal for streaming |
| **Modular Specialist Model** | **High** | Specialized sub-networks can be loaded independently |
| **Quantized Layer-Streamed Model** | **Medium** | Supported, but requires high storage bandwidth |
| **Small Dense Model** | **High (as resident fallback)** | Entire model remains resident in RAM |
| **Very Large Dense Transformer** | **Low** | Requires all weights for every token; unsuited for streaming |
| **Model with Unbounded KV Growth** | **Rejected** | Violates 8.0 GB RAM limit guarantee |
| **Unsupported Tensor Layout** | **Rejected** | Inefficient or unsafe memory layout |

---

## 7. Formal Memory-Admission Equation

Before loading any model profile, the Kattappa Model Admission Controller evaluates:

$$\text{estimated\_peak\_kattappa\_ram} = \text{control\_plane\_peak} + \text{voice\_and\_tool\_peak} + \text{resident\_model\_core} + \text{max\_active\_expert\_cache} + \text{KV\_cache\_budget} + \text{workspace\_buffers} + \text{safety\_reserve}$$

### Admission Requirement:
$$\text{estimated\_peak\_kattappa\_ram} \le 8.0\text{ GB (8,000,000,000 bytes)}$$

If the estimate exceeds 8.0 GB, Kattappa must:
1. Reduce context length window.
2. Reduce expert cache allocation.
3. Apply higher quantization (e.g. 4-bit KV cache).
4. Suspend non-critical voice/UI sidecars.
5. Select a smaller compatible fallback model.
6. **Reject model loading.** (Never silently depend on OS page swapping).

---

## 8. SSD Storage & Capacity Policy

To prevent model streaming from exhausting host system disk space:

```text
Minimum Protected Free SSD Space = max(15% of SSD capacity, 250 GB)
```

K-HIM reserves protected space for Windows OS updates, virtual memory, temporary files, Kattappa databases, crash dumps, and expert-cache staging buffers. The 500 GB HDD serves strictly as archival storage, not as the active streaming tier.

---

## 9. Authoritative Roadmap Milestones

```text
K-R0.5 (ACTIVE: Release Validation Repair)
Complete immutable release Runs A, B and C
        |
        v
K-SB-1 (QUEUED)
Superbench outcome semantics and safety oracle
        |
        v
K-CAP-1 (QUEUED)
Unified capabilities, permissions and approvals
        |
        v
K-HIM-0 (QUEUED)
Scientific feasibility, hardware benchmarks (SSD bandwidth, CPU I/O mode), and spec
        |
        v
K-HIM-1 (FUTURE)
Native SSD-streamed MoE prototype with small sparse model
        |
        v
K-HIM-2 (FUTURE)
Hard 8 GB total Kattappa process-tree RAM governor integration
        |
        v
K-HIM-3 (FUTURE)
Production hardening, large model support, and real-world validation
```

> [!IMPORTANT]
> **No production code for K-HIM will be introduced until K-R0.5, K-SB-1, and K-CAP-1 are formally validated and closed.**
