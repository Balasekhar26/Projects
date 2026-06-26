import time

class Clock:
    def execute(self):
        """Returns the current system timestamp and local time."""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime())
        return {
            "current_time": current_time,
            "timestamp": int(time.time())
        }
