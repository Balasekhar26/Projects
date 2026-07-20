from collections import Counter

class LessonExtractor:
    @classmethod
    def extract_lessons(cls, episodes: list[dict], threshold_count: int = 2) -> list[str]:
        """Analyzes historical failures and extracts generalized operational policies."""
        failures = [ep["failure_reason"] for ep in episodes if ep["result"] == "failure" and ep["failure_reason"]]
        
        counts = Counter(failures)
        lessons = []
        
        for reason, count in counts.items():
            if count >= threshold_count:
                # Generate generalized guideline recommendation
                if "administrator" in reason.lower() or "permission" in reason.lower():
                    lessons.append("Ensure system execution runs under administrator elevation privileges.")
                elif "network" in reason.lower() or "connection" in reason.lower():
                    lessons.append("Verify active network socket interfaces before running script requests.")
                else:
                    lessons.append(f"Remediate frequent failure vector: {reason}")
                    
        return lessons
