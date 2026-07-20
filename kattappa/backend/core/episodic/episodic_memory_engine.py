from backend.core.episodic.episode_store import EpisodeStore
from backend.core.episodic.event_segmenter import EventSegmenter
from backend.core.episodic.lesson_extractor import LessonExtractor

class EpisodicMemoryEngine:
    def __init__(self):
        self.store = EpisodeStore()
        self.segmenter = EventSegmenter()
        self.lesson_extractor = LessonExtractor()

    def record_episode(self, goal: str, result: str, failure_reason: str = "") -> None:
        """Saves a task run to episodic store database."""
        self.store.save_episode(goal, result, failure_reason)

    def get_segmented_sessions(self, threshold_sec: float = 300.0) -> list[list[dict]]:
        """Segments history logs items list into epoch sessions groups."""
        episodes = self.store.get_all_episodes()
        return self.segmenter.segment_events(episodes, threshold_sec)

    def extract_guidelines(self, threshold_count: int = 2) -> list[str]:
        """Analyzes historical outcomes to extract operational policies guidelines."""
        episodes = self.store.get_all_episodes()
        return self.lesson_extractor.extract_lessons(episodes, threshold_count)
