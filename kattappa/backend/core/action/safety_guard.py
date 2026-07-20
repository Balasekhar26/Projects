class SafetyGuard:
    BLACKLIST_SUBSTRINGS = [
        "rm -rf", 
        "format c:", 
        "registry delete", 
        "del /f", 
        "drop table users"
    ]

    @classmethod
    def validate_action(cls, command: str) -> bool:
        """Inspects commands and parameters against safety blacklist templates."""
        cmd_clean = command.lower().strip()
        for pattern in cls.BLACKLIST_SUBSTRINGS:
            if pattern in cmd_clean:
                return False
        return True
