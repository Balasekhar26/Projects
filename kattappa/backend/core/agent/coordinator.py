import time
from backend.core.agent.observe import Observer
from backend.core.agent.reflector import Reflector
from backend.core.agent.learner import Learner
from backend.core.skills_runtime.skill_registry import Skill
from backend.core.skills_runtime.skills_runtime_engine import SkillsRuntimeEngine

class AgentLoopCoordinator:
    def __init__(self):
        self.observer = Observer()
        self.skills_engine = SkillsRuntimeEngine()
        self.learner = Learner(self.skills_engine)
        self.reflector = Reflector()

    def execute_goal_cycle(self, goal_id: str, objective: str, action_steps: list[dict]) -> str:
        """Coordinates the full Observe-Think-Act-Verify-Reflect-Learn cycle for target objectives."""
        start_time = time.time()
        
        # 1. Observe state
        self.observer.capture_world_state()
        
        # 2. Decompose and register steps as temporary execution skill
        temp_skill_name = f"temp_{goal_id}"
        temp_skill = Skill(
            name=temp_skill_name,
            prerequisites=[],
            steps=action_steps,
            post_conditions=[]
        )
        self.skills_engine.register_skill(temp_skill)
        
        # 3. Execute actions and verify
        result = self.skills_engine.execute(temp_skill_name, [])
        duration = time.time() - start_time
        
        # 4. Reflect and Learn outcomes
        if result == "SUCCESS":
            self.reflector.reflect_on_outcome(goal_id, True, duration)
            self.learner.learn_new_skill(objective, action_steps)
            return "SUCCESS"
        else:
            self.reflector.reflect_on_outcome(goal_id, False, duration)
            return f"FAILED_{result}"
            
        return result
