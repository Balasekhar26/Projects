# K-HIM: Kattappa Hierarchical Inference Memory Engine

## 1. Architectural Purpose & Requirements

**K-HIM (Kattappa Hierarchical Inference Memory Engine)** is Kattappa's native SSD-streamed inference system designed to execute models larger than physical system RAM while enforcing a strict **8 GB total Kattappa process-tree RAM governor**.

Rather than connecting to external third-party inference backends, Kattappa native inference streams cold tensors and expert parameters dynamically from high-speed SSD storage into a bounded RAM cache, streaming only the specific active experts required per token.

---

## 2. Four-Tier Memory Hierarchy

```text
+-------------------------------------------------------------+
| GPU VRAM                                                    |
| Hot tensors and active expert execution buffers            |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
| System RAM (Hard Kattappa limit: 8 GB)                      |
| Resident model core, quantized KV cache, active workspace   |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
| 2 TB NVMe SSD                                               |
| Cold experts, model weight shards, inactive tensor store   |
+-------------------------------------------------------------+
                            |
+-------------------------------------------------------------+
| 500 GB HDD                                                  |
| Long-term backups, archived models, historical datasets     |
+-------------------------------------------------------------+
```

---

## 3. Two-Mind System Architecture

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

1. **Fast Interactive Mind**: A small, fully resident model (< 2-3 GB RAM) dedicated to sub-second interactive chat, desktop control, voice, and browser automation.
2. **Deep Reasoning Mind**: A large, SSD-streamed MoE model invoked for complex planning, research, code synthesis, and architectural verification. The reasoning model produces structured plans and recommendations but does NOT bypass Kattappa's security and permission boundaries.

---

## 4. Key Subsystems & Technical Components

1. **SSD Tensor & Expert Store**: Memory-mapped binary layout optimizing sequential and random block reads for model weights on NVMe storage.
2. **Bounded Hot-Expert RAM Cache**: LRU/LFU cache keeping frequently activated experts resident within allocated System RAM budgets.
3. **Asynchronous Prefetcher**: Predictive pipeline that fetches next-token candidate experts before layer computation begins.
4. **Expert Routing & Predictor**: Lightweight predictor neural net or heuristic layer estimating expert activation paths.
5. **Quantized KV Cache Manager**: 4-bit/8-bit quantized Key-Value cache manager with sliding window and paged memory allocation.
6. **Model Admission Controller**: Verifies RAM, VRAM, and SSD bandwidth availability before loading candidate models.
7. **Strict 8 GB RAM Governor**: Hard process-tree monitor enforcing memory caps across all sidecars and parent processes.
8. **Inference Sidecar Crash Isolation**: Runs inference engine in an isolated subprocess; process crashes do NOT collapse the main Kattappa control plane.
9. **Automatic Fallback Model**: Instantly routes requests to a smaller resident model if SSD streaming stalls or crashes.
10. **Telemetry & Diagnostics**: Live measurement of RAM, VRAM, SSD read bandwidth, latency, prefetch hit rate, and thermals.

---

## 5. K-HIM-0 Research & Measurement Targets

Prior to prototyping code implementation in K-HIM-1, the following baseline parameters must be measured on the workstation:

- **Storage Bandwidth**: Sustained sequential and 4K random read MB/s on NVMe target.
- **RAM Footprint**: Baseline Windows host RAM consumption and available Kattappa ceiling.
- **Candidate Quantizations**: FP16 vs INT8 vs INT4 activation and weight memory trade-offs.
- **Resident Core Bytes**: Minimum non-swappable core parameters for target MoE architectures.
- **Active Expert Bytes**: Parameter size per token activation.
- **KV Cache Growth Rate**: Memory per 1,000 context tokens under 4-bit quantization.
- **SSD Thermal & Wear**: Impact of continuous token streaming on NVMe thermals and endurance.
- **I/O Mechanism Performance**: Benchmark `mmap` vs Direct I/O (`O_DIRECT`) vs `io_uring` / `FILE_FLAG_NO_BUFFERING`.

---

## 6. Authoritative Roadmap Milestones

```text
K-R0.5 (ACTIVE)
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
Feasibility research, hardware benchmarks and technical specification
        |
        v
K-HIM-1 (FUTURE)
Native SSD-streamed MoE prototype with small sparse model
        |
        v
K-HIM-2 (FUTURE)
Hard 8 GB total process-tree RAM governor integration
        |
        v
K-HIM-3 (FUTURE)
Production hardening, large model support, and real-world validation
```

> [!IMPORTANT]
> **No production code for K-HIM will be introduced until K-R0.5, K-SB-1, and K-CAP-1 are formally validated and closed.**
