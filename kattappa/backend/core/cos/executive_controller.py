"""ExecutiveController — Phase K23 coordinator loop.

Manages scheduler ticks, interrupts, budget allocations, and safety gates.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
from typing import Callable, Dict, List, Optional
from backend.core.logger import log_event
from backend.core.orchestrator.base import Task


class InterruptType(Enum):
    USER_INTERVENTION = "USER_INTERVENTION"
    SAFETY_VIOLATION = "SAFETY_VIOLATION"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass
class Interrupt:
    type: InterruptType
    priority: int  # Higher priority numbers trigger first
    message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Budget:
    max_latency_seconds: float
    max_tokens: int


class ExecutiveController:
    """Central OS runtime tick and interrupt coordinator singleton."""

    _instance: Optional[ExecutiveController] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._running = False
        self._tick_rate_ms = 100
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._active_interrupts: List[Interrupt] = []
        self._stage_handlers: Dict[str, List[Callable[[], None]]] = {
            "perceive": [],
            "retrieve": [],
            "reason": [],
            "plan": [],
            "act": [],
            "learn": [],
        }
        self._interrupt_handlers: Dict[
            InterruptType, List[Callable[[Interrupt], None]]
        ] = {}
        self._initialized = True

    def start(self, tick_rate_ms: int = 100) -> None:
        """Starts the background scheduler tick loop thread."""
        with self._lock:
            if self._running:
                return
            self._tick_rate_ms = tick_rate_ms
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
            log_event(
                "executive_controller_started",
                {"message": f"Loop started with tick_rate={tick_rate_ms}ms"},
            )

    def stop(self) -> None:
        """Stops the scheduler loop thread gracefully."""
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        log_event("executive_controller_stopped", {"message": "Loop stopped"})

    def trigger_interrupt(self, interrupt: Interrupt) -> None:
        """Registers a high-priority interrupt, sorting it for immediate handling."""
        with self._lock:
            self._active_interrupts.append(interrupt)
            # Sort by priority descending
            self._active_interrupts.sort(key=lambda x: x.priority, reverse=True)
            log_event(
                "executive_interrupt_triggered",
                {"message": f"Interrupt {interrupt.type.value} registered with priority {interrupt.priority}"},
            )

    def register_stage_handler(self, stage: str, handler: Callable[[], None]) -> None:
        """Registers a callback for a specific scheduler step."""
        with self._lock:
            if stage in self._stage_handlers:
                self._stage_handlers[stage].append(handler)

    def register_interrupt_handler(
        self, type: InterruptType, handler: Callable[[Interrupt], None]
    ) -> None:
        """Registers a callback for an interrupt class."""
        with self._lock:
            self._interrupt_handlers.setdefault(type, []).append(handler)

    def allocate_budget(self, task: Task) -> Budget:
        """Computes resource budgets based on task metadata."""
        complexity = task.params.get("complexity", "normal")
        if complexity == "high":
            return Budget(max_latency_seconds=10.0, max_tokens=4000)
        elif complexity == "low":
            return Budget(max_latency_seconds=2.0, max_tokens=1000)
        return Budget(max_latency_seconds=5.0, max_tokens=2000)

    def handle_interrupt(self, interrupt: Interrupt) -> None:
        """Invokes registered callbacks for the given interrupt type."""
        log_event(
            "executive_handling_interrupt", {"message": f"Handling interrupt {interrupt.type.value}"}
        )
        handlers = self._interrupt_handlers.get(interrupt.type, [])
        for handler in handlers:
            try:
                handler(interrupt)
            except Exception as e:
                log_event("executive_interrupt_handler_error", {"message": f"Handler error: {e}"})

    def process_tick(self) -> None:
        """Executes a single tick iteration, checking interrupts and processing stages."""
        with self._lock:
            # 1. Handle highest priority interrupt first if present
            if self._active_interrupts:
                highest_interrupt = self._active_interrupts.pop(0)
                self.handle_interrupt(highest_interrupt)
                return

            # 2. Sequential execution of OS stages
            for stage in ["perceive", "retrieve", "reason", "plan", "act", "learn"]:
                handlers = self._stage_handlers.get(stage, [])
                for handler in handlers:
                    try:
                        handler()
                    except Exception as e:
                        log_event("executive_stage_error", {"message": f"Stage {stage} error: {e}"})

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            start_time = time.time()
            try:
                self.process_tick()
            except Exception as e:
                log_event("executive_loop_tick_error", {"message": str(e)})

            elapsed = time.time() - start_time
            sleep_time = (self._tick_rate_ms / 1000.0) - elapsed
            if sleep_time > 0:
                self._stop_event.wait(timeout=sleep_time)


# Global ExecutiveController Singleton reference
CONTROLLER = ExecutiveController()
