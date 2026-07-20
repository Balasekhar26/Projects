from __future__ import annotations
import time
import copy
from typing import Any

from backend.core.world_state.sensors.system_sensor import SystemSensor
from backend.core.world_state.sensors.hardware_sensor import HardwareSensor
from backend.core.world_state.sensors.storage_sensor import StorageSensor
from backend.core.world_state.sensors.python_sensor import PythonSensor
from backend.core.world_state.sensors.network_sensor import NetworkSensor
from backend.core.world_state.sensors.capability_sensor import CapabilitySensor
from backend.core.world_state.sensors.process_sensor import ProcessSensor
from backend.core.world_state.sensors.runtime_sensor import RuntimeSensor

class WorldStateManager:
    def __init__(self) -> None:
        self._sensors = {
            "system": (SystemSensor(), float("inf")),
            "hardware": (HardwareSensor(), float("inf")),
            "storage": (StorageSensor(), 60.0),
            "python": (PythonSensor(), 600.0),
            "network": (NetworkSensor(), 10.0),
            "capabilities": (CapabilitySensor(), 300.0),
            "processes": (ProcessSensor(), 5.0),
            "runtime": (RuntimeSensor(), 5.0)
        }
        
        self._cache: dict[str, Any] = {}
        self._last_refresh: dict[str, float] = {}

    def get_snapshot(self) -> dict[str, Any]:
        """Returns an aggregated deep-copied snapshot of all registered world state sensors."""
        now = time.time()
        aggregated: dict[str, Any] = {}
        
        for name, (sensor, ttl) in self._sensors.items():
            last_run = self._last_refresh.get(name, 0.0)
            if name not in self._cache or (now - last_run) > ttl:
                try:
                    res = sensor.collect()
                    self._cache[name] = res
                    self._last_refresh[name] = now
                except Exception:
                    # Keep old cache if collection fails
                    if name not in self._cache:
                        self._cache[name] = {}
            
            # Deep merge sensor dictionary keys
            for key, val in self._cache[name].items():
                if key in aggregated and isinstance(aggregated[key], dict) and isinstance(val, dict):
                    aggregated[key].update(val)
                else:
                    aggregated[key] = copy.deepcopy(val)
                    
        return aggregated

# Global Singleton Manager
WORLD_STATE_MANAGER = WorldStateManager()
