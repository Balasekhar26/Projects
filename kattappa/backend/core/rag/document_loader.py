import os
import re

class DocumentLoader:
    @staticmethod
    def load_file(file_path: str) -> str:
        """Reads contents of text/markdown files and returns string contents."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Document file not found at: {file_path}")
            
        _, ext = os.path.splitext(file_path.lower())
        
        # Simple plain text / markdown reader
        if ext in [".txt", ".md", ".py", ".java", ".cpp", ".json", ".xml", ".html", ".css", ".js", ".ts", ".tsx"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
                
        # Basic fallback for other formats
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
