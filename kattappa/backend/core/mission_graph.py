from __future__ import annotations


class MissionGraph:
    @classmethod
    def get_prerequisites(cls, stages: list[str], target_stage: str) -> list[str]:
        """Returns stages preceding target_stage in the stages sequence."""
        if target_stage not in stages:
            return []
        idx = stages.index(target_stage)
        return stages[:idx]

    @classmethod
    def can_transition(cls, stages: list[str], completed_stages: list[str], target_stage: str) -> bool:
        """Checks if all prerequisite stages are present in completed_stages."""
        prereqs = cls.get_prerequisites(stages, target_stage)
        # Ensure every prerequisite stage has been marked completed
        return all(p in completed_stages for p in prereqs)

    @classmethod
    def validate_transition(cls, stages: list[str], completed_stages: list[str], target_stage: str) -> None:
        """Raises ValueError if any prerequisite stage is missing."""
        if not cls.can_transition(stages, completed_stages, target_stage):
            prereqs = cls.get_prerequisites(stages, target_stage)
            unmet = [p for p in prereqs if p not in completed_stages]
            raise ValueError(f"Cannot transition to stage '{target_stage}'. Prerequisite stages not completed: {', '.join(unmet)}")
