# ADR-23: Perception Architecture Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Cognitive operating systems ingest diverse, multi-modal signals (raw text, user speech, image frames, structured JSON settings, sensor readings). Parsing and processing these directly inside downstream reasoning modules creates tight coupling, parsing errors, and high latency.

### Decision
Define a decoupled, modular **Perception Architecture** that ingests multi-modal raw streams and normalizes them into canonical `Observation` objects before they enter the Executive loop.

---

### Perceptual Normalization & Fusion Channels

```
 [ Text ]    [ Speech ]   [ Vision ]   [ Files ]   [ Sensors ]
    │            │            │            │            │
    ▼            ▼            ▼            ▼            ▼
[     Multi-Modal Normalization & Alignment Pipeline     ]
                               │
                               ▼
                    [ Sensory Data Fusion ]
                               │
                               ▼
                    [ Grounded Observation ]
```

#### 1. Modality Normalizers:
- **Text Normalizer**: Standardizes encodings, filters escape sequences, and extracts metadata.
- **Speech-to-Text (STT)**: Transforms audio signals into text streams with word confidence scores.
- **Vision (Image/Video/OCR)**: Processes frames, extracts bounding boxes, and performs text character extraction.
- **Sensor/IoT Normalizer**: Ingests numerical telemetry streams (e.g. CPU load, memory usage, network latency).

#### 2. Sensory Data Fusion:
- Coordinates temporal alignment of inputs from different channels occurring within the same time window.
- Generates a single, integrated `ObservedState` containing unified property values (e.g. matching a user's verbal command with an active image/file on their editor screen).
- Registers the observation to the coordinator.
