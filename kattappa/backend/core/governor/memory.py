import os
import re
import sys
import psutil
import subprocess
from typing import Dict, Any
from backend.core.governor.base import BaseGovernor, GovernorAction

class MemoryGovernor(BaseGovernor):
    """
    Monitors physical RAM, compressor occupancy, swap usage, and pageouts
    to prevent memory starvation and excessive SSD thrashing.
    """
    
    def __init__(self):
        self._last_pageouts = 0
        self._last_time = 0.0
        self._init_vm_stats()

    def _init_vm_stats(self):
        if sys.platform == "darwin":
            try:
                stats = self._get_macos_vm_stat()
                self._last_pageouts = stats.get("pageouts", 0)
                import time
                self._last_time = time.time()
            except Exception:
                pass

    def _get_macos_vm_stat(self) -> Dict[str, int]:
        stats = {"pageouts": 0, "compressed_pages": 0, "page_size": 4096}
        try:
            out = subprocess.check_output(["vm_stat"], text=True)
            m_page = re.search(r"page size of (\d+) bytes", out)
            if m_page:
                stats["page_size"] = int(m_page.group(1))

            m_comp = re.search(r"Pages occupied by compressor:\s*(\d+)", out)
            if m_comp:
                stats["compressed_pages"] = int(m_comp.group(1))

            m_pageouts = re.search(r"Pages pageout:\s*(\d+)", out)
            if not m_pageouts:
                m_pageouts = re.search(r"Pageouts:\s*(\d+)", out)
            if m_pageouts:
                stats["pageouts"] = int(m_pageouts.group(1))
        except Exception:
            pass
        return stats

    def _get_macos_swap(self) -> float:
        """Returns swap used in GB."""
        try:
            out = subprocess.check_output(["sysctl", "vm.swapusage"], text=True)
            m = re.search(r"used\s*=\s*([\d.]+)M", out)
            if m:
                return float(m.group(1)) / 1024.0
        except Exception:
            pass
        try:
            return psutil.swap_memory().used / (1024 ** 3)
        except Exception:
            return 0.0

    def get_metrics(self) -> Dict[str, Any]:
        vmem = psutil.virtual_memory()
        total_ram_gb = vmem.total / (1024 ** 3)
        available_ram_gb = vmem.available / (1024 ** 3)
        ram_percent = vmem.percent
        
        swap_used_gb = 0.0
        compressed_pct = 0.0
        pageouts_rate = 0.0

        if sys.platform == "darwin":
            import time
            swap_used_gb = self._get_macos_swap()
            vm_stats = self._get_macos_vm_stat()
            
            now = time.time()
            if self._last_time > 0:
                delta = max(now - self._last_time, 0.001)
                pageouts_diff = max(vm_stats["pageouts"] - self._last_pageouts, 0)
                pageouts_rate = pageouts_diff / delta
            
            self._last_pageouts = vm_stats["pageouts"]
            self._last_time = now
            
            total_ram_bytes = vmem.total
            if total_ram_bytes > 0:
                compressed_pct = (vm_stats["compressed_pages"] * vm_stats["page_size"] / total_ram_bytes) * 100.0
        else:
            try:
                swap_used_gb = psutil.swap_memory().used / (1024 ** 3)
            except Exception:
                pass

        return {
            "ram_percent": ram_percent,
            "total_ram_gb": total_ram_gb,
            "available_ram_gb": available_ram_gb,
            "swap_used_gb": swap_used_gb,
            "compressed_pct": compressed_pct,
            "pageouts_rate": pageouts_rate
        }

    def assess(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        ram_percent = metrics["ram_percent"]
        available_ram_gb = metrics["available_ram_gb"]
        swap_used_gb = metrics["swap_used_gb"]
        compressed_pct = metrics["compressed_pct"]
        pageouts_rate = metrics["pageouts_rate"]

        available_capacity = max(0.0, 100.0 - ram_percent)
        
        # Enforce OS / foreground application headroom policy (guarantee at least 50% RAM remains available)
        # 1. Critical conditions -> PAUSE
        if ram_percent > 90.0 or available_ram_gb < 1.0:
            action = GovernorAction.PAUSE
            risk_score = 0.98
            priority = 9
            reason = f"RAM usage is critical at {ram_percent}% (Only {available_ram_gb:.2f} GB free)."
        elif swap_used_gb > 8.0:
            action = GovernorAction.PAUSE
            risk_score = 0.90
            priority = 8
            reason = f"Swap usage is critical at {swap_used_gb:.2f} GB (Max safe is 8.0 GB)."
        elif pageouts_rate > 20.0:
            action = GovernorAction.PAUSE
            risk_score = 0.88
            priority = 8
            reason = f"Pageouts rate is critical at {pageouts_rate:.1f} pages/sec. High risk of disk thrashing."
        elif compressed_pct > 35.0:
            action = GovernorAction.PAUSE
            risk_score = 0.85
            priority = 7
            reason = f"Memory compressor occupancy is critical at {compressed_pct:.1f}% of physical memory."
            
        # 2. Elevated conditions -> ECO (Yielding resources)
        elif ram_percent > 50.0 or available_ram_gb < (metrics["total_ram_gb"] * 0.5):
            # Scale down when physical available RAM is less than 50%
            action = GovernorAction.ECO
            risk_score = 0.55
            priority = 5
            reason = f"RAM available is less than 50% ({available_ram_gb:.2f} GB left). Restricting to ECO mode."
        elif swap_used_gb > 2.0:
            action = GovernorAction.ECO
            risk_score = 0.50
            priority = 5
            reason = f"Swap usage is elevated at {swap_used_gb:.2f} GB."
        elif pageouts_rate > 5.0:
            action = GovernorAction.ECO
            risk_score = 0.45
            priority = 4
            reason = f"Pageouts rate is elevated at {pageouts_rate:.1f} pages/sec."
        elif compressed_pct > 15.0:
            action = GovernorAction.ECO
            risk_score = 0.40
            priority = 4
            reason = f"Memory compressor occupancy is elevated at {compressed_pct:.1f}%."
            
        # 3. Nominal conditions -> NONE
        else:
            action = GovernorAction.NONE
            risk_score = 0.10
            priority = 1
            reason = "System memory indicators are nominal."

        return {
            "available_capacity": available_capacity,
            "risk_score": risk_score,
            "priority": priority,
            "recommended_action": action,
            "reason": reason,
            "metrics": metrics
        }
