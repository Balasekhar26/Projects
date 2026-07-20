from backend.core.distillation.pattern_miner import PatternMiner
from backend.core.distillation.skill_generalizer import SkillGeneralizer
from backend.core.distillation.skill_optimizer import SkillOptimizer
from backend.core.skills_runtime.skill_registry import Skill, SkillRegistry

class SkillDistillationEngine:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self.miner = PatternMiner()
        self.generalizer = SkillGeneralizer()
        self.optimizer = SkillOptimizer()

    def distill_repeated_workflow(
        self, 
        skill_name: str, 
        action_sequences: list[list[str]], 
        raw_steps: list[dict],
        success_rate: float = 0.95
    ) -> bool:
        """Runs sequence mining, variables templating, optimization, and registers distilled skills."""
        # 1. Mine patterns
        patterns = self.miner.mine_repeated_sequences(action_sequences)
        if not patterns:
            return False
            
        # 2. Generalize commands
        flat_cmds = [cmd for seq in action_sequences for cmd in seq]
        templated_cmd, variables = self.generalizer.generalize_commands(flat_cmds)
        
        # 3. Optimize execution steps
        optimized_steps = self.optimizer.optimize_steps(raw_steps)
        
        # Calculate skill confidence: 0.5 * success_rate + 0.2 * sample_size (scaled) + 0.3
        sample_size_factor = min(len(action_sequences) / 10.0, 1.0)
        confidence = (0.5 * success_rate) + (0.2 * sample_size_factor) + 0.3
        
        # Promote to trusted if confidence >= 0.90
        if confidence >= 0.90:
            distilled_skill = Skill(
                name=skill_name,
                prerequisites=[],
                steps=optimized_steps,
                post_conditions=["distilled_success"],
                description=f"Distilled template command: {templated_cmd}"
            )
            self.registry.register(distilled_skill)
            return True
            
        return False
