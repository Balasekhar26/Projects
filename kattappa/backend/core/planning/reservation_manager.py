"""Resource Reservation Management (Program 12.2).
"""
from __future__ import annotations

import time
import uuid
import threading
from dataclasses import dataclass
from typing import Dict


@dataclass
class ResourceReservation:
    """Represents a temporary block on multidimensional resources for execution safety."""
    reservation_id: str
    plan_id: str
    resource_vector: Dict[str, float]
    expires_at: float
    status: str  # RESERVED, ALLOCATED, RELEASED, EXPIRED


class ReservationManager:
    """Thread-safe resource pool allocating and sweeping transient worker reservations."""

    def __init__(self, capacity: Dict[str, float]) -> None:
        self.capacity = dict(capacity)
        self.available_resources = dict(capacity)
        self.reservations: Dict[str, ResourceReservation] = {}
        self._lock = threading.Lock()

    def reserve(self, plan_id: str, resource_vector: Dict[str, float], lease_duration: float = 60.0) -> str:
        """Reserves a resource vector if capacity allows. Sweeps expired reservations first."""
        with self._lock:
            self._expire_stale_reservations_under_lock()

            # Verify availability
            for resource, amount in resource_vector.items():
                available = self.available_resources.get(resource, 0.0)
                if available < amount:
                    raise ValueError(
                        f"Insufficient '{resource}' resource: requested {amount}, only {available} available."
                    )

            # Deduct allocation
            for resource, amount in resource_vector.items():
                self.available_resources[resource] -= amount

            res_id = f"res-{uuid.uuid4().hex[:8]}"
            expires_at = time.time() + lease_duration
            reservation = ResourceReservation(
                reservation_id=res_id,
                plan_id=plan_id,
                resource_vector=dict(resource_vector),
                expires_at=expires_at,
                status="RESERVED",
            )
            self.reservations[res_id] = reservation
            return res_id

    def allocate(self, reservation_id: str) -> None:
        """Transitions status of reservation from RESERVED to ALLOCATED."""
        with self._lock:
            res = self.reservations.get(reservation_id)
            if not res:
                raise KeyError(f"Reservation '{reservation_id}' not found.")
            if res.status != "RESERVED":
                raise ValueError(f"Cannot allocate reservation '{reservation_id}' with status '{res.status}'.")
            res.status = "ALLOCATED"

    def release(self, reservation_id: str) -> None:
        """Releases the locked resources back to the pool."""
        with self._lock:
            res = self.reservations.get(reservation_id)
            if not res:
                raise KeyError(f"Reservation '{reservation_id}' not found.")
            
            if res.status in {"RESERVED", "ALLOCATED"}:
                # Return resources to the pool
                for resource, amount in res.resource_vector.items():
                    self.available_resources[resource] = min(
                        self.capacity.get(resource, 0.0),
                        self.available_resources.get(resource, 0.0) + amount
                    )
            res.status = "RELEASED"

    def expire_stale_reservations(self) -> int:
        """Exposes public method to trigger sweep of expired reservation leases."""
        with self._lock:
            return self._expire_stale_reservations_under_lock()

    def _expire_stale_reservations_under_lock(self) -> int:
        """Private sweep routine executing inside critical lock sections."""
        now = time.time()
        expired_count = 0
        for res in self.reservations.values():
            if res.status == "RESERVED" and now >= res.expires_at:
                # Return resources to the pool
                for resource, amount in res.resource_vector.items():
                    self.available_resources[resource] = min(
                        self.capacity.get(resource, 0.0),
                        self.available_resources.get(resource, 0.0) + amount
                    )
                res.status = "EXPIRED"
                expired_count += 1
        return expired_count
