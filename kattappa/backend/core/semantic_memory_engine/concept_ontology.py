class ConceptOntology:
    def __init__(self):
        # In-memory graph structure for hierarchical taxonomy relationships
        self.isa_relations = {
            "python": "programming_language",
            "programming_language": "software_tool",
            "pytest": "testing_framework",
            "testing_framework": "software_tool",
            "vscode": "text_editor",
            "text_editor": "software_tool"
        }

    def get_ancestors(self, concept_id: str) -> list[str]:
        """Resolves recursive parent taxonomy paths for a concept (e.g. python -> software_tool)."""
        ancestors = []
        curr = concept_id.lower().strip()
        
        while curr in self.isa_relations:
            parent = self.isa_relations[curr]
            ancestors.append(parent)
            curr = parent
            
        return ancestors
