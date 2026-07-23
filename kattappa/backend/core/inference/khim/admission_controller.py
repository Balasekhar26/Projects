"""
K-HIM Atomic Memory Reservation & Request Admission Controller.
Enforces request-scoped atomic reservations against the 8,000,000,000 decimal byte hard ceiling
with emergency reserve enforcement.
"""

from __future__ import annotations

import threading
from typing import Dict, Any, Optional

from backend.core.inference.khim.memory_supervisor import WindowsJobMemorySupervisor, HARD_CEILING_BYTES, EMERGENCY_RESERVE_BYTES


class KHIMAdmissionController:
    """Atomic request-scoped memory reservation controller."""

    def __init__(self, supervisor: Optional[WindowsJobMemorySupervisor] = None):
        self.supervisor = supervisor or WindowsJobMemorySupervisor()
        self._lock = threading.Lock()
        self._active_reservations: Dict[str, int] = {}

    def get_total_reserved_bytes(self) -> int:
        with self._lock:
            return sum(self._active_reservations.values())

    def evaluate_and_reserve(
        self,
        request_id: str,
        estimated_expert_resident_bytes: int,
        temporary_buffer_bytes: int = 50 * 1024 * 1024,
        voice_reserve_bytes: int = 100 * 1024 * 1024,
        tool_reserve_bytes: int = 100 * 1024 * 1024
    ) -> Dict[str, Any]:
        """Evaluates admission rule atomically. Returns reservation status."""
        mem_stats = self.supervisor.get_process_tree_memory()
        
        # FAIL CLOSED: If telemetry measurement is invalid, reject admission
        if not mem_stats.get("measurement_valid", True):
            return {
                "admitted": False,
                "reason": "MEASUREMENT_UNAVAILABLE_FAIL_CLOSED",
                "request_id": request_id,
                "fallback_recommended": True
            }

        current_rss = mem_stats.get("total_rss_bytes", 0)

        with self._lock:
            existing_reservations = sum(self._active_reservations.values())
            projected_peak = (
                current_rss +
                existing_reservations +
                estimated_expert_resident_bytes +
                temporary_buffer_bytes +
                voice_reserve_bytes +
                tool_reserve_bytes +
                EMERGENCY_RESERVE_BYTES
            )

            if projected_peak <= HARD_CEILING_BYTES:
                total_request_reservation = estimated_expert_resident_bytes + temporary_buffer_bytes
                self._active_reservations[request_id] = total_request_reservation
                return {
                    "admitted": True,
                    "request_id": request_id,
                    "reserved_bytes": total_request_reservation,
                    "projected_peak_bytes": projected_peak,
                    "hard_ceiling_bytes": HARD_CEILING_BYTES,
                    "fallback_recommended": False
                }
            else:
                return {
                    "admitted": False,
                    "reason": f"HARD_CEILING_EXCEEDED (Projected {projected_peak} > {HARD_CEILING_BYTES})",
                    "request_id": request_id,
                    "fallback_recommended": True
                }

    def release_reservation(self, request_id: str) -> bool:
        """Atomic release of request reservation on completion, error, or cancellation."""
        with self._lock:
            if request_id in self._active_reservations:
                del self._active_reservations[request_id]
                return True
            return False
