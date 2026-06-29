# ADR-36: Plugin SDK Specification

*   **Status**: `ACCEPTED`
*   **Date**: 2026-06-29
*   **Evidence Level**: **E4** (Approved Blueprint)

### Context & Problem
Third-party developers need to extend Kattappa with new tools, reasoning strategies, planners, and normalizers. Integrating these by modifying core system directories creates merge conflicts, compromises security, and breaks backwards compatibility.

### Decision
Define a robust **Plugin SDK** that allows safe, sandboxed, and versioned third-party extensions.

---

### Core Specifications

#### 1. Plugin Manifest (`plugin.json`)
Every plugin must declare a manifest defining its identity and capabilities:
```json
{
  "plugin_id": "com.example.coder",
  "version": "1.0.0",
  "entry_point": "plugin.py:init",
  "declared_capabilities": ["tool", "reasoner"],
  "requested_permissions": ["filesystem.read"],
  "dependencies": ["numpy>=1.20"]
}
```

#### 2. Lifecycle States
- Plugins transit through a managed state machine: `LOADED -> VALIDATED -> ENABLED -> RUNNING -> SHUTDOWN`.
- Unloaded or disabled plugins cannot register listeners on the system event bus.

#### 3. Sandboxing & Isolation
- Plugins are loaded into isolated namespaces or subprocess boundaries.
- Attempting file access outside declared paths or executing unregistered imports throws a security exception, terminating the plugin.
