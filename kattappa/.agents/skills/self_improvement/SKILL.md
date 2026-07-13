---
name: self-improvement
description: Instruction set for executing self-improvement loops, trace analyses, and automated code corrections.
---

# Skill: Self-Improvement

Use this skill when analyzing trace logs of failed tasks and applying automated corrections.

## Guidelines
1. **Trace Inspection**: Parse execution logs, console logs, and database provenance records to pinpoint the exact failure node in the graph.
2. **Root Cause Identification**: Differentiate between:
   - Routing failures (incorrect model router choice)
   - Synthesis failures (broken planning output)
   - Safety blocks (false positives)
   - Exception aborts (bug in code)
3. **Automated Fix & Verification**: Apply the minimal correction to resolve the failure, run regression tests, and re-execute the target task to verify the fix.
