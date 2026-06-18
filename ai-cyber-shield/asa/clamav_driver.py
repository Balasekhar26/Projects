from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Any

# Standard EICAR Antivirus Test Signature
EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"

class ClamAvScanner:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.clamscan_path = shutil.which("clamscan")

    def is_clamav_installed(self) -> bool:
        if not self.clamscan_path:
            return False
        try:
            res = subprocess.run([self.clamscan_path, "--version"], capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def scan_directory(self, target_dir: str | Path) -> dict[str, Any]:
        target_path = Path(target_dir).resolve()
        if not target_path.exists():
            raise ValueError(f"Target path does not exist: {target_dir}")

        if self.is_clamav_installed():
            return self._run_clamscan(target_path)
        else:
            return self._run_signature_fallback(target_path)

    def _run_clamscan(self, target_path: Path) -> dict[str, Any]:
        try:
            process = subprocess.run(
                [self.clamscan_path, "-r", str(target_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            output = process.stdout or ""
            findings = []
            
            for line in output.splitlines():
                if "FOUND" in line:
                    parts = line.split(":", 1)
                    file_path = parts[0].strip()
                    threat_name = parts[1].replace("FOUND", "").strip()
                    findings.append({
                        "file_path": file_path,
                        "threat_name": threat_name,
                        "severity": "critical",
                    })

            return {
                "engine": "ClamAV (Native)",
                "target": str(target_path),
                "findings": findings,
                "scan_status": "success" if process.returncode in (0, 1) else "error",
                "infected_count": len(findings),
            }
        except subprocess.TimeoutExpired:
            return {
                "engine": "ClamAV (Native)",
                "target": str(target_path),
                "findings": [],
                "scan_status": "timeout",
                "infected_count": 0,
            }
        except Exception as e:
            return {
                "engine": "ClamAV (Native)",
                "target": str(target_path),
                "findings": [],
                "scan_status": f"error: {str(e)}",
                "infected_count": 0,
            }

    def _run_signature_fallback(self, target_path: Path) -> dict[str, Any]:
        findings = []
        try:
            for path in target_path.rglob("*"):
                # Skip dependency, virtualenv, build, and pycache directories
                parts = path.parts
                if any(p.startswith(".") or p in {"node_modules", "venv", "env", "ai_system_env", "dist", "__pycache__"} for p in parts):
                    continue

                if not path.is_file():
                    continue
                
                # Prevent scanning very large files with signature scanning for performance
                try:
                    if path.stat().st_size > 10 * 1024 * 1024:  # 10MB limit
                        continue
                except Exception:
                    continue

                # Check for EICAR signature in binary read mode
                try:
                    content = path.read_bytes()
                    if EICAR_SIGNATURE in content:
                        findings.append({
                            "file_path": str(path),
                            "threat_name": "EICAR-Test-Signature",
                            "severity": "critical",
                        })
                        continue
                except OSError as e:
                    # Catch Windows Defender blocks (raises Errno 22 or 13)
                    if "eicar" in path.name.lower() or e.errno in (13, 22):
                        findings.append({
                            "file_path": str(path),
                            "threat_name": f"Blocked-File-Access (Potential Malware: {e.strerror or 'Antivirus block'})",
                            "severity": "critical",
                        })
                        continue
                except Exception:
                    pass

                # Check for suspicious double-extension file names or executables in non-binary folders
                try:
                    is_expected = path.name.lower() in {"setup.bat", "run.exe", "run.cmd", "run_cyber_shield.bat"}
                    is_in_expected_dir = any(d in str(path).lower() for d in ["/bin", "\\bin", "/scripts", "\\scripts", "/web-dashboard", "\\web-dashboard"])
                    if path.name.lower().endswith((".exe", ".bat", ".cmd", ".scr", ".vbs")) and "honeypot" not in str(path) and not is_expected and not is_in_expected_dir:
                        findings.append({
                            "file_path": str(path),
                            "threat_name": "Suspicious-Executable-Location",
                            "severity": "high",
                        })
                except Exception:
                    pass

            return {
                "engine": "Signature-Matching Fallback (ClamAV Sim)",
                "target": str(target_path),
                "findings": findings,
                "scan_status": "success",
                "infected_count": len(findings),
            }
        except Exception as e:
            return {
                "engine": "Signature-Matching Fallback (ClamAV Sim)",
                "target": str(target_path),
                "findings": [],
                "scan_status": f"error: {str(e)}",
                "infected_count": 0,
            }
