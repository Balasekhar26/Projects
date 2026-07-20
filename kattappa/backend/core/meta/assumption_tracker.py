class AssumptionTracker:
    def __init__(self):
        self.assumptions = {}

    def register_assumption(self, plan_id: str, key: str, expected_state: str) -> None:
        """Registers a logical assumption baseline that must remain true during plan steps."""
        if plan_id not in self.assumptions:
            self.assumptions[plan_id] = {}
        self.assumptions[plan_id][key] = expected_state

    def verify_assumptions(self, plan_id: str, actual_system_states: dict) -> bool:
        """Asserts all registered plan assumptions against observed environment states."""
        plan_assumptions = self.assumptions.get(plan_id, {})
        for key, expected in plan_assumptions.items():
            actual = actual_system_states.get(key)
            if actual != expected:
                return False
        return True
