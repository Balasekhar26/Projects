class CapabilityRegistry:
    def __init__(self):
        self.supported_capabilities = {
            "file_read",
            "file_write",
            "mouse_click",
            "text_typing",
            "git_commands",
            "command_run"
        }

    def is_command_supported(self, command: str) -> bool:
        """Checks if the command parameters map to a supported system capability boundary."""
        cmd_clean = command.lower().strip()
        
        # Simple capability matcher
        if "rm" in cmd_clean or "format" in cmd_clean:
            return False
            
        if "git" in cmd_clean:
            return "git_commands" in self.supported_capabilities
        elif "echo" in cmd_clean or "ls" in cmd_clean:
            return "command_run" in self.supported_capabilities
            
        return True
