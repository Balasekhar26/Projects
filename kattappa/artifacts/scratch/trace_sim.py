import os
os.environ["PYTEST_CURRENT_TEST"] = "1"
from pathlib import Path
import tempfile
import shutil

tmp_path = Path(tempfile.mkdtemp(prefix="kattappa_sim_trace_"))
os.environ["KATTAPPA_DATA_DIR"] = str(tmp_path)

import backend.core.config as config_module
from backend.core.config import load_config
from dataclasses import replace
cfg = load_config()
mock_config = replace(cfg, sqlite_path=tmp_path / "kattappa_test.db")
config_module.load_config = lambda: mock_config

import backend.core.action_memory as action_memory_module
import backend.core.simulation_engine as simulation_engine_module
import backend.core.simulation_calibration as simulation_calibration_module

action_memory_module.runtime_data_root = lambda: tmp_path
simulation_engine_module.runtime_data_root = lambda: tmp_path
simulation_calibration_module.runtime_data_root = lambda: tmp_path
simulation_calibration_module.SimulationCalibrator._cached_weights = {}

from backend.tests.test_simulation_engine_v1 import _seed_action_history
action_memory = action_memory_module.ActionMemory
_seed_action_history(action_memory, "RUN_TESTS", "coder", successes=9, failures=1)

# Check stats directly
stats = action_memory.get_action_type_statistics("RUN_TESTS")
print("STATS FOR RUN_TESTS:", stats)

# Run simulation plan
report = simulation_engine_module.SimulationEngine.simulate_plan(
    [{"step_id": "test", "agent": "coder", "action": "RUN_TESTS"}],
    goal="Run validation",
    workflow_id="wf_api"
)
print("REPORT SUCCESS PROBABILITY:", report.success_probability)
print("REPORT DICT:", report.to_dict())

shutil.rmtree(tmp_path, ignore_errors=True)
