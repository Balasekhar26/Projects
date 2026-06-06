# Kattappa AI OS Installation Agreement

Read this before installing Kattappa AI OS Assistant.

## Local-first and free-first

Kattappa AI OS is intended to run as a local-first assistant using fully free/open-source/local-first tools where practical. Paid, freemium, trial-limited, reward-network, closed, or privacy-risky tools must not be added to the seven-project core. When a paid or restricted tool is mentioned, Kattappa AI OS should search for a fully free alternative and add only the replacement if it improves a project.

## System access

Kattappa AI OS may inspect this machine's basic specifications, such as CPU count, RAM, operating system, and installed local capability status, so it can choose work that fits this system. Kattappa AI OS should run tasks within the capability of the current machine and delegate heavier work only to approved paired systems.

Kattappa AI OS must not perform destructive actions, installs, remote shell actions, remote desktop control, credential access, or sensitive file operations without approval.

## Multi-system cluster mode

Kattappa AI OS may support a multi-system mode where several trusted machines run together as one assistant. This mode is designed for owner-approved systems only.

By accepting this agreement, you acknowledge:

- This installation may include code paths for future local cluster mode.
- A machine may auto-connect to other Kattappa AI OS nodes only after explicit pairing/approval on the involved systems.
- After a system is installed, paired, and approved, Kattappa AI OS may automatically reconnect to that paired system when a task needs its capability, run approved non-sensitive worker processes, return results to the manager, and disconnect or idle the worker when the task is complete.
- Kattappa AI OS may connect to and use multiple already-paired systems at the same time when the manager has work that benefits from several workers and each worker stays within its capability limits.
- Approved self-improvement data should be published to the Kattappa AI OS Git repository as an improvement proposal, including approved/trusted skills, tool rules, free-tool replacements, capability profiles, sanitized reflection lessons, and test summaries.
- Every Kattappa AI OS system, paired or unpaired, may periodically check the Git repository for shared improvement proposals, with a default interval of 24 hours. When new improvement data is found, the system should verify it, check local compatibility and safety policy, then ask the local user or manager for approval before adopting it.
- Kattappa AI OS should not directly push improvement data to other systems. Systems receive shared improvements by Git clone/fetch/pull/install.
- Raw user chat history, private task context, private approval notes, credentials, secrets, and sensitive files should not auto-sync as improvement data.
- Kattappa AI OS must not silently join, monitor, control, or run workloads on systems where the owner/admin has not installed and approved it.
- Cluster traffic should stay on a trusted local network or user-controlled VPN.
- Each node should report its system capability, and the manager should route tasks only within each node's CPU/RAM/GPU/permission limits.
- Weak nodes should run only light tasks they can handle. Strong nodes may take heavier work, but no node is treated as unlimited; every assignment must stay inside the node's measured hardware and permission limits.
- This agreement covers ordinary cluster participation and task routing after installation and device pairing, so routine non-sensitive worker scheduling should not need a separate prompt each time.
- Chat history, task history, approval history, and long-term memory should be stored on the task-origin main/manager system, not on worker/sub systems.
- The only durable cross-system shared data should be approved, sanitized improvement data.
- Worker/sub systems should receive only the temporary task context needed to complete assigned work, return results to the manager, and delete task context after completion, failure, or cancellation.
- Paired systems may share approved sanitized improvement proposals through the Git repository and approved shared improvement registry. This shared workspace is not shared private data.
- Raw chat history, private task context, task payloads, approval notes, credentials, secrets, sensitive local files, and machine-private memory should not be treated as shared workspace data.
- Remote actions still require approval when they involve shell commands, file writes, installs, desktop control, credentials, destructive actions, or sensitive data.

## Acceptance

Continue installation only if you understand and accept these terms.
