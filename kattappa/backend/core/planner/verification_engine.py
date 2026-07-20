from __future__ import annotations

class VerificationEngine:
    @classmethod
    def get_verification_method(cls, action: str, params: dict) -> dict:
        """Determines the verification criteria needed to confirm task success."""
        act_upper = action.upper()
        if "WRITE" in act_upper:
            return {
                "type": "file_exists",
                "target": params.get("target") or params.get("path") or ""
            }
        if "INSTALL" in act_upper:
            return {
                "type": "package_importable",
                "target": params.get("package") or params.get("name") or ""
            }
        return {
            "type": "command_success",
            "check": "exit_code_zero"
        }
