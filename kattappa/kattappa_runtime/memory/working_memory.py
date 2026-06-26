class WorkingMemory:
    def __init__(self):
        self.state = {
            "active_project": "Kattappa",
            "current_phase": "KM-6",
            "last_topic": "memory architecture",
            "open_tasks": []
        }

    def get(self, key: str, default=None):
        return self.state.get(key, default)

    def set(self, key: str, value):
        self.state[key] = value

    def add_task(self, task: str):
        if task not in self.state["open_tasks"]:
            self.state["open_tasks"].append(task)

    def remove_task(self, task: str):
        if task in self.state["open_tasks"]:
            self.state["open_tasks"].remove(task)

    def reset(self):
        self.state = {
            "active_project": None,
            "current_phase": None,
            "last_topic": None,
            "open_tasks": []
        }
