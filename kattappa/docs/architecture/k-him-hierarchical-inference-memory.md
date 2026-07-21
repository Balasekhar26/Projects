# K-HIM: Kattappa Hierarchical Inference Memory Engine

## 1. Architectural Purpose & Scope

**K-HIM (Kattappa Hierarchical Inference Memory Engine)** is Kattappa's native SSD-streamed inference runtime designed to execute compatible models larger than physical system RAM while keeping all Kattappa-owned processes strictly under a configurable **8 GiB total process-tree RAM ceiling**.

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
| System RAM (Hard Kattappa limit: 8 GiB total process-tree)  |
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

## 3. Dynamic 8 GiB Process-Tree RAM Budget

The 8 GiB RAM limit applies to the complete Kattappa-owned process tree (control plane, sidecars, resident models, caches, and tools).

| Domain | Initial Dynamic Ceiling | Description |
| :--- | :---: | :--- |
| **Control plane, policy, & memory coordination** | **1.5 GiB** | Core orchestrator, state engines, security governors |
| **Voice, UI, & automation bridges** | **0.5 GiB** | Playwright, TTS/STT helpers, desktop sidecars |
| **Fast resident model (when active)** | **2.0 GiB** | Sub-second interactive chat & tool routing model |
| **Deep inference resident core & expert cache** | **3.0 GiB** | Resident MoE core parameters and active expert cache |
| **KV cache & I/O buffers** | **0.5 GiB** | Quantized KV cache pages and async read buffers |
| **Emergency reserve** | **0.5 GiB** | Operating safety margin |
| **Total Process Tree Ceiling** | **8.0 GiB** | **Hard Kattappa Governor Limit** |

*Note: Kattappa dynamically unloads or suspends optional components (such as fast resident models or voice bridges) when transitioning into Deep Reasoning Mode.*

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

- **Fast Interactive Task**: Small resident model (< 2.0 GiB RAM) for instant interactive tasks.
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
| **Model with Unbounded KV Growth** | **Rejected** | Violates 8 GiB RAM limit guarantee |
| **Unsupported Tensor Layout** | **Rejected** | Inefficient or unsafe memory layout |

---

## 7. Formal Memory-Admission Equation

Before loading any model profile, the Kattappa Model Admission Controller evaluates:

$$\text{estimated\_peak\_kattappa\_ram} = \text{control\_plane\_peak} + \text{voice\_and\_tool\_peak} + \text{resident\_model\_core} + \text{max\_active\_expert\_cache} + \text{KV\_cache\_budget} + \text{workspace\_buffers} + \text{safety\_reserve}$$

### Admission Requirement:
$$\text{estimated\_peak\_kattappa\_ram} \le 8.0\text{ GiB}$$

If the estimate exceeds 8.0 GiB, Kattappa must:
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
Hard 8 GiB total Kattappa process-tree RAM governor integration
        |
        v
K-HIM-3 (FUTURE)
Production hardening, large model support, and real-world validation
```

> [!IMPORTANT]
> **No production code for K-HIM will be introduced until K-R0.5, K-SB-1, and K-CAP-1 are formally validated and closed.**
