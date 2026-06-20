import os
import re
from datetime import datetime
from pathlib import Path
from typing import List

class ObsidianMemory:
    def __init__(self) -> None:
        self.vault_path = Path(os.getenv(
            "SEKHAR_OBSIDIAN_VAULT", 
            "C:/Users/balu/ObsidianVault/SekharBrain"
        )).resolve()
        
        try:
            self.vault_path.mkdir(parents=True, exist_ok=True)
            (self.vault_path / "Daily Notes").mkdir(exist_ok=True)
            (self.vault_path / "Concepts").mkdir(exist_ok=True)
        except Exception:
            pass

    def _sanitize_filename(self, name: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "", name).strip()

    def write_daily_note(self, content: str, category: str = "general") -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        daily_note_path = self.vault_path / "Daily Notes" / f"{today}.md"
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"\n- **[{timestamp}]** ({category}) {content}\n"
        
        if not daily_note_path.exists():
            header = f"# Daily Log - {today}\n\n## Timeline\n"
            daily_note_path.write_text(header + log_entry, encoding="utf-8")
        else:
            with open(daily_note_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
        return daily_note_path

    def write_concept_page(self, title: str, content: str, tags: List[str] = None, connections: List[str] = None) -> Path:
        sanitized_title = self._sanitize_filename(title)
        concept_path = self.vault_path / "Concepts" / f"{sanitized_title}.md"
        
        frontmatter = "---\n"
        frontmatter += f"title: \"{title}\"\n"
        frontmatter += f"updated: {datetime.now().isoformat()}\n"
        if tags:
            frontmatter += "tags:\n" + "\n".join([f"  - {t}" for t in tags]) + "\n"
        frontmatter += "---\n\n"
        
        body = f"# {title}\n\n{content}\n\n"
        if connections:
            body += "## Related Links\n"
            body += "\n".join([f"- [[{conn}]]" for conn in connections]) + "\n"
            
        concept_path.write_text(frontmatter + body, encoding="utf-8")
        return concept_path
