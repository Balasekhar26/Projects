# K21-35: World Update Scheduler

This document details the update loop scheduler, event-sourced transaction queue, and synchronization ticking mechanisms.

---

## 1. The Transaction Queue

To prevent race conditions, write observations are staged inside a thread-safe **Transaction Queue**:

```
[Observation Event] ──> [Transaction Queue (FIFO)] ──> [Scheduler Tick] ──> [Commit Domain DB]
```

- **Thread safety**: Evaluator writes append events to the queue using a lock-free queue or mutex.
- **Batched Commits**: Commits run in batches during the scheduler tick (e.g. every `100ms` or when the queue size reaches 20 events), minimizing disk I/O overhead.

---

## 2. Event Execution Scheduler API

```python
class WorldUpdateScheduler:
    """Manages update ticks, background consolidation, and queue processing."""
    
    _queue = queue.Queue()
    _active = False

    @classmethod
    def queue_event(cls, event: Event) -> None:
        cls._queue.put(event)
        
    @classmethod
    def run_tick(cls) -> None:
        """Processes and commits queued events within a single database transaction."""
        with KERNEL.write_lock:
            # 1. Fetch batched events
            # 2. Run validations
            # 3. Apply state updates
            # 4. Commit transaction
            pass
```
- During `run_tick`, the scheduler locks access to the target world instance, preventing inconsistent reads.
