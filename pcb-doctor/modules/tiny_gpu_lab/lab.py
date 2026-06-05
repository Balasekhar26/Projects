from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TinyGpuModule:
    name: str
    path: Path
    size_bytes: int


class TinyGpuLab:
    def __init__(self, upstream_root: str | Path) -> None:
        self.upstream_root = Path(upstream_root)

    def discover_verilog_modules(self) -> tuple[TinyGpuModule, ...]:
        src_dir = self.upstream_root / "src"
        modules = []
        for path in sorted(src_dir.glob("*.sv")):
            modules.append(TinyGpuModule(path.stem, path, path.stat().st_size))
        return tuple(modules)

    def simulation_command(self, kernel: str = "matadd") -> list[str]:
        test_name = {
            "matadd": "test_matadd.py",
            "matmul": "test_matmul.py",
        }.get(kernel)
        if test_name is None:
            raise ValueError("kernel must be 'matadd' or 'matmul'")
        return ["python", "-m", "pytest", str(self.upstream_root / "test" / test_name), "-q"]

    def architecture_assets(self) -> dict[str, Path]:
        images = self.upstream_root / "docs" / "images"
        return {
            "gpu": images / "gpu.png",
            "core": images / "core.png",
            "isa": images / "isa.png",
            "thread": images / "thread.png",
            "trace": images / "trace.png",
        }

    def learning_summary(self) -> str:
        modules = ", ".join(module.name for module in self.discover_verilog_modules())
        return (
            "tiny-gpu is a learning-oriented SystemVerilog GPU. "
            f"Available modules: {modules}. "
            "Use the matrix-add and matrix-multiply tests to study execution traces."
        )

