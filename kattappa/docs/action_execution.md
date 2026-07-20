# Action Execution Foundation

Kattappa represents each atomic side effect as an immutable `Action`. The
planner selects an executor by name; it does not import or branch on concrete
executor implementations. An instance-scoped `ExecutorRegistry` supplies the
implementation through dependency injection.

```python
from backend.core.action import Action, ExecutorRegistry, FileExecutor

registry = ExecutorRegistry()
registry.register("file", FileExecutor("workspace"))

action = Action(
    executor="file",
    operation="write",
    parameters={"path": "hello.txt", "content": "Hello World"},
    requires_confirmation=False,  # the caller has completed the approval gate
)
result = registry.resolve(action.executor).execute(action)
```

The file executor confines resolved paths to its configured base directory,
writes through an atomic replacement, verifies exact bytes, and returns a
canonical `ActionResult`. It restores the prior file if verification fails.
Requests marked `requires_confirmation=True` are never executed; the caller
must complete the approval workflow and submit an explicitly approved action.

Every future executor must implement `execute(action) -> ActionResult`, measure
latency with a monotonic clock, and verify the resulting external state before
reporting success. Executor-specific failures belong in structured error codes,
not planner branches.

## Stabilization gates

`CapabilityManager` is injected into each executor and denies unknown operations
by default. `RecoveryPolicy` rejects retry budgets above three. `ShellExecutor`
accepts argument arrays rather than command strings, never invokes `shell=True`,
and applies both an executable allowlist and destructive-command deny rules.

Install the pinned engineering dependencies before running stabilization checks:

```bash
python -m pip install -r requirements-dev.txt
```

The performance gate uses warm-up executions followed by an odd number of timed
samples. It compares the sample median with recent results from the same OS,
architecture, and Python version:

```bash
python -m evaluation.action_runtime_benchmark \
  --output artifacts/execution-stabilization/benchmark.json \
  --history artifacts/action-benchmark-history.json \
  --record
```

Safety mutation testing is configured in `setup.cfg`. Mutmut 3 requires fork
support, so run it on Linux, macOS, or Windows through WSL:

```bash
mutmut run
mutmut export-cicd-stats
```

CI combines JUnit, coverage, mutation, and benchmark artifacts into JSON and a
compact Markdown dashboard using `python -m evaluation.ci_health_report`. A missing
artifact is a gate failure rather than an implied success.

Pytest markers separate deterministic unit, integration, safety, performance,
AI evaluation, and slow lanes. Counts must be derived from the current checkout;
they are not hard-coded into CI because benchmark generators and test modules
change independently.

Every test should eventually carry exactly one primary marker (`unit`,
`integration`, or `evaluation`) and may carry secondary traits such as `safety`,
`performance`, `slow`, `network`, `hardware`, or `mutation`. Strict marker
validation is enabled now; mandatory-primary enforcement remains an audit until
the legacy suite is classified.

Preserve exact collection evidence with the repository helper:

```bash
python -m scripts.collect_pytest_nodeids backend/tests \
  --output artifacts/execution-stabilization/backend-nodeids.txt
python -m scripts.collect_pytest_nodeids \
  --output artifacts/execution-stabilization/pytest-nodeids.txt
```
