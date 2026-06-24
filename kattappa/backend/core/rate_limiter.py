import time
from collections import defaultdict
from typing import Dict, List

class RateLimiter:
    # Action name -> Maximum allowed execution per minute
    LIMITS: Dict[str, int] = None

    # Registry maps (session_id, action) -> list of execution timestamps
    _registry: Dict[tuple[str, str], List[float]] = defaultdict(list)

    @classmethod
    def check_rate_limit(cls, session_id: str, action: str) -> bool:
        """
        Tracks request timestamps and validates sliding window ceiling per action/minute.
        Returns True if within rate limits, False if rate-limited (blocked).
        """
        action_upper = action.upper()
        if cls.LIMITS is None:
            from backend.core.config import load_security_config
            sec_config = load_security_config()
            cls.LIMITS = sec_config.get("rate_limits") or {
                "DESKTOP_SCREENSHOT": 10,
                "DESKTOP_READ_SCREEN": 10,
                "BROWSER_READ": 20,
                "BROWSER_NAVIGATE": 20,
                "BROWSER_SEARCH": 20,
                "WRITE_FILE": 30,
                "FILE_WRITE": 30,
                "CREATE_FILE": 30,
                "RUN_SHELL": 10,
            }
            
        limit = cls.LIMITS.get(action_upper)
        if limit is None:
            return True  # No limit set by default for other tools

        now = time.time()
        key = (session_id, action_upper)
        history = cls._registry[key]

        # 1. Clean timestamps older than 60 seconds
        cutoff = now - 60.0
        cls._registry[key] = [t for t in history if t > cutoff]

        # 2. Check threshold
        if len(cls._registry[key]) >= limit:
            return False

        # 3. Record current request timestamp
        cls._registry[key].append(now)
        return True

    @classmethod
    def reset_limits(cls) -> None:
        """
        Reset rate limiter registry state. Useful for test isolation.
        """
        cls._registry.clear()
