import pytest
import time
from backend.core.world_state.sensors.base_sensor import BaseSensor
from backend.core.world_state.sensors.system_sensor import SystemSensor
from backend.core.world_state.sensors.hardware_sensor import HardwareSensor
from backend.core.world_state.sensors.storage_sensor import StorageSensor
from backend.core.world_state.sensors.python_sensor import PythonSensor
from backend.core.world_state.sensors.network_sensor import NetworkSensor
from backend.core.world_state.sensors.capability_sensor import CapabilitySensor
from backend.core.world_state.sensors.process_sensor import ProcessSensor
from backend.core.world_state.sensors.runtime_sensor import RuntimeSensor
from backend.core.world_state.world_state_manager import WorldStateManager

def test_individual_sensors() -> None:
    # Test system sensor
    sys_data = SystemSensor().collect()
    assert "system" in sys_data
    assert "os_name" in sys_data["system"]
    assert "hostname" in sys_data["system"]

    # Test hardware sensor
    hw_data = HardwareSensor().collect()
    assert "hardware" in hw_data
    assert "cpu_cores" in hw_data["hardware"]
    assert "ram_total" in hw_data["hardware"]

    # Test storage sensor
    store_data = StorageSensor().collect()
    assert "storage" in store_data
    assert "free_space" in store_data["storage"]

    # Test python sensor
    py_data = PythonSensor().collect()
    assert "python" in py_data
    assert "python_version" in py_data["python"]

    # Test network sensor
    net_data = NetworkSensor().collect()
    assert "network" in net_data
    assert "connected" in net_data["network"]

    # Test capability sensor
    cap_data = CapabilitySensor().collect()
    assert "capabilities" in cap_data
    assert "git" in cap_data["capabilities"]

    # Test process sensor
    proc_data = ProcessSensor().collect()
    assert "processes" in proc_data
    assert "running" in proc_data["processes"]

    # Test runtime sensor
    run_data = RuntimeSensor().collect()
    assert "runtime" in run_data
    assert "user_context" in run_data

def test_world_state_manager_aggregation() -> None:
    manager = WorldStateManager()
    snapshot = manager.get_snapshot()
    
    assert "system" in snapshot
    assert "hardware" in snapshot
    assert "storage" in snapshot
    assert "python" in snapshot
    assert "network" in snapshot
    assert "capabilities" in snapshot
    assert "processes" in snapshot
    assert "runtime" in snapshot
    assert "user_context" in snapshot

def test_world_state_caching_ttl() -> None:
    class MockSensor(BaseSensor):
        def __init__(self):
            self.calls = 0
        def collect(self) -> dict:
            self.calls += 1
            return {"mock": {"val": self.calls}}

    manager = WorldStateManager()
    sensor = MockSensor()
    
    manager._sensors = {
        "mock_sensor": (sensor, 1.0)
    }
    
    snap1 = manager.get_snapshot()
    assert snap1["mock"]["val"] == 1
    
    snap2 = manager.get_snapshot()
    assert snap2["mock"]["val"] == 1
    assert sensor.calls == 1
    
    time.sleep(1.1)
    snap3 = manager.get_snapshot()
    assert snap3["mock"]["val"] == 2
    assert sensor.calls == 2
