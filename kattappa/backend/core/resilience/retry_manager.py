import time

class RetryManager:
    @classmethod
    def execute_with_retry(cls, func, max_attempts: int = 3, initial_delay_sec: float = 0.1, backoff_factor: float = 2.0):
        """Executes a function with exponential backoff retry cycles."""
        attempt = 0
        delay = initial_delay_sec
        
        while attempt < max_attempts:
            try:
                return func()
            except Exception as e:
                attempt += 1
                if attempt >= max_attempts:
                    raise e
                time.sleep(delay)
                delay *= backoff_factor
