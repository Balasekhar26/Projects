import unittest
from pathlib import Path

from modules.tiny_gpu_lab import TinyGpuLab


UPSTREAM = r"C:\Users\balu\Projects\external-projects\tiny-gpu"


class TinyGpuLabTest(unittest.TestCase):
    def test_discovers_systemverilog_modules(self):
        if not Path(UPSTREAM).exists():
            self.skipTest(f"External tiny-gpu checkout not found: {UPSTREAM}")
        modules = TinyGpuLab(UPSTREAM).discover_verilog_modules()
        names = {module.name for module in modules}

        self.assertIn("gpu", names)
        self.assertIn("core", names)
        self.assertIn("alu", names)

    def test_builds_simulation_commands(self):
        lab = TinyGpuLab(UPSTREAM)

        self.assertIn("test_matadd.py", lab.simulation_command("matadd")[3])
        self.assertIn("test_matmul.py", lab.simulation_command("matmul")[3])


if __name__ == "__main__":
    unittest.main()
