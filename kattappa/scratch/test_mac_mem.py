import subprocess
import re
import os
import psutil

def get_mac_memory_details():
    try:
        page_size = os.sysconf("SC_PAGESIZE")
    except Exception:
        page_size = 4096
    
    # vm_stat
    vm_stat_out = subprocess.check_output(["vm_stat"]).decode("utf-8")
    stored_pages = 0
    occupied_pages = 0
    for line in vm_stat_out.splitlines():
        if "Pages stored in compressor:" in line:
            stored_pages = int(re.search(r"\d+", line).group())
        elif "Pages occupied by compressor:" in line:
            occupied_pages = int(re.search(r"\d+", line).group())
            
    compressed_bytes = stored_pages * page_size
    compressed_gb = compressed_bytes / (1024**3)
    
    # swap usage
    swap_used_gb = 0.0
    try:
        swap_out = subprocess.check_output(["sysctl", "vm.swapusage"]).decode("utf-8")
        match = re.search(r"used\s*=\s*(\d+\.?\d*)([MGT])", swap_out)
        if match:
            val, unit = match.groups()
            val = float(val)
            if unit == "M":
                swap_used_gb = val / 1024.0
            elif unit == "G":
                swap_used_gb = val
            elif unit == "T":
                swap_used_gb = val * 1024.0
    except Exception:
        pass
        
    # memory pressure from sysctl
    memory_pressure_level = 0
    try:
        pressure_out = subprocess.check_output(["sysctl", "-n", "vm.memory_pressure"]).decode("utf-8").strip()
        memory_pressure_level = int(pressure_out)
    except Exception:
        pass
        
    # memory status level (free percentage)
    memorystatus_level = 100
    try:
        status_out = subprocess.check_output(["sysctl", "-n", "kern.memorystatus_level"]).decode("utf-8").strip()
        memorystatus_level = int(status_out)
    except Exception:
        pass
        
    return {
        "compressed_gb": compressed_gb,
        "swap_used_gb": swap_used_gb,
        "memory_pressure_level": memory_pressure_level,
        "memorystatus_level": memorystatus_level,
    }

print(get_mac_memory_details())
