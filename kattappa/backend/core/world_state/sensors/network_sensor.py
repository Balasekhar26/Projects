from __future__ import annotations
import socket
from backend.core.world_state.sensors.base_sensor import BaseSensor

class NetworkSensor(BaseSensor):
    def collect(self) -> dict:
        connected = False
        try:
            # Check external internet access by initiating connection to Cloudflare DNS
            socket.setdefaulttimeout(1.5)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(("1.1.1.1", 53))
            connected = True
        except Exception:
            pass
            
        return {
            "network": {
                "connected": connected,
                "interface_count": 1 if connected else 0,
                "internet_access": connected,
                "bandwidth_estimate": "100 Mbps" if connected else "0 Mbps"
            }
        }
