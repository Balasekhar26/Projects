import os
from typing import Dict

class SecretBroker:
    _secrets: Dict[str, str] = {}

    @classmethod
    def register_secret(cls, key: str, value: str) -> None:
        """
        Registers a secret in the SecretBroker memory.
        """
        cls._secrets[key.upper()] = value

    @classmethod
    def get_secret(cls, key: str) -> str:
        """
        Retrieves a secret from the broker in privileged scopes.
        """
        return cls._secrets.get(key.upper(), "")

    @classmethod
    def scrub_env(cls, env: dict) -> dict:
        """
        Returns a scrubbed copy of the environment dictionary where all secret keys/credentials are removed.
        """
        clean_env = env.copy()
        
        # Pattern checks for keys containing secret indications
        patterns = ["KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL", "PASS"]
        
        for key in list(clean_env.keys()):
            key_upper = key.upper()
            if any(pat in key_upper for pat in patterns):
                # Whitelist specific safe environment keys
                if key_upper not in ["PATH", "KATTAPPA_ENV"]:
                    clean_env.pop(key, None)
                    
        return clean_env
