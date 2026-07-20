class KnowledgeAsymmetry:
    @classmethod
    def detect_gaps(cls, system_facts: set[str], user_beliefs: set[str]) -> dict:
        """Compares system knowledge against user beliefs to find information asymmetries."""
        # Facts the system knows but the user may not
        system_only = system_facts - user_beliefs
        # Things the user believes but the system has no record of
        user_only = user_beliefs - system_facts
        # Shared knowledge
        shared = system_facts & user_beliefs

        return {
            "system_knows_user_doesnt": sorted(system_only),
            "user_believes_system_doesnt": sorted(user_only),
            "shared_knowledge": sorted(shared),
            "asymmetry_ratio": len(system_only) / max(len(system_facts), 1)
        }
