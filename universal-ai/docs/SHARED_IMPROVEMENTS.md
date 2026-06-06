# Shared Kattappa AI OS Improvements

This file is the Git-repo distribution point for approved, sanitized Kattappa AI OS improvement proposals.
Every Kattappa AI OS system, paired or unpaired, should use the Git repository as the canonical place to publish and discover shared improvement data.

## Rule

Approved improvement data may be shared through this repository so every Kattappa AI OS installation can discover it, whether or not that system is paired into a cluster.

Kattappa AI OS must not directly push improvement data to other systems. Systems receive shared improvements by cloning, fetching, pulling, or otherwise receiving this Git repository. A system that creates an approved improvement should sanitize it, write it here or to a future registry file, and then stage/commit/push to the configured Git remote when publication is enabled.

## What Can Be Shared

- approved or trusted skills
- tool rules and free-tool replacements
- cluster capability-policy updates
- sanitized reflection lessons
- test and validation summaries
- migration notes for local adapters

## What Must Not Be Shared Here

- raw user chat history
- private task context
- approval private notes
- credentials, tokens, keys, or secrets
- sensitive files or local-only data
- machine-specific private paths unless sanitized

## Receiving System Flow

1. Check for shared improvements on a schedule or when the user manually requests it. This applies to paired and unpaired systems.
2. Default check interval: once every 24 hours, with a small time jitter so multiple systems do not all check at the exact same moment.
3. Pull or clone the Git repository.
4. Read shared improvement proposals from this file or future registry files.
5. Verify free-tool policy, safety scope, and local compatibility.
6. Ask the local user or manager for approval when new improvement data is found.
7. If approval is not given, keep the item as a pending proposal only.
8. Adopt only after local approval.

## Current Shared Improvements

- Git repo hub policy: any system may publish approved, sanitized improvement proposals to the Git repo, and every system checks the repo for proposals before asking local approval to adopt them.
- Multi-system cluster policy: paired workers can run capability-checked tasks, while the task-origin manager keeps chat/task/approval memory.
- Paid-tool replacement policy: paid, freemium, trial-limited, reward-network, closed, or privacy-risky tools are blocked from the seven-project core unless replaced by fully free/open/local alternatives.
- Improvement sync policy: approved improvements can be shared automatically to paired nodes as proposals and distributed to unpaired systems through Git as sanitized proposals.
- Seven-project improvement-agent runtime: Kattappa AI OS exposes `POST /projects/improvement-agents/observe` to inspect all seven project readiness signals and create pending proposals, `POST /improvements/{improvement_id}` to approve or reject proposals, and `POST /projects/improvement-agents/check-shared` to import Git-shared improvements as pending local proposals. Nothing is auto-applied.

## Approved Improvement b44b22f0-b10b-4f06-a83a-fe3d4f6aadd7

<!-- improvement:b44b22f0-b10b-4f06-a83a-fe3d4f6aadd7 -->

- Published: 2026-06-06T20:44:35
- Title: Enable seven-project approval-gated improvement loop
- Risk: low
- Approval status: approved
- Motive: Verify every project has a Kattappa-managed improvement agent loop with approval, Git-backed publication, and local adoption approval.

Proposal:

The seven-project improvement agent observes setup/run/status signals, creates pending proposals, publishes approved sanitized information to the shared Git registry, and imports shared Git improvements only as pending proposals for local approval.

Receiving systems must verify policy, compatibility, tests, and rollback, then ask local approval before adopting.
