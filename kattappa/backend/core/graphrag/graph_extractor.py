import re
import uuid

class GraphExtractor:
    PREDICATES = {
        "communicates with": "communicates_with",
        "sends data to": "sends_data_to",
        "receives data from": "receives_data_from",
        "depends on": "depends_on",
        "requires": "requires",
        "needs": "requires",
        "controls": "controls",
        "manages": "controls",
        "operates": "controls",
        "contains": "contains",
        "owns": "contains",
        "includes": "contains",
        "consists of": "contains",
        "causes": "causes",
        "results in": "causes",
        "leads to": "causes",
        "is a": "is_a",
        "is an": "is_a",
        "belongs to": "is_a",
        "supersedes": "supersedes",
        "replaces": "supersedes",
        "upgrades": "supersedes"
    }

    CATEGORIES = {
        "communicates_with": "Communication",
        "sends_data_to": "Communication",
        "receives_data_from": "Communication",
        "depends_on": "Dependency",
        "requires": "Dependency",
        "controls": "Control",
        "contains": "Structural",
        "causes": "Causal",
        "is_a": "Hierarchy",
        "supersedes": "Versioning"
    }

    @classmethod
    def extract_relations(cls, text: str, chunk_id: str) -> list[dict]:
        """Parses sentences within chunk text and extracts entity relationships using regex matching templates."""
        sentences = re.split(r'\.|\?|\!', text)
        extracted = []

        pred_pattern = "|".join(re.escape(k) for k in cls.PREDICATES.keys())
        pattern = re.compile(
            r'^\s*(?P<source>[\w\s\-\.\_]+?)\s+(?P<predicate>' + pred_pattern + r')\s+(?P<target>[\w\s\-\.\_]+?)\s*$',
            re.IGNORECASE
        )

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            match = pattern.match(sentence)
            if match:
                source_raw = match.group("source").strip()
                predicate_raw = match.group("predicate").strip().lower()
                target_raw = match.group("target").strip()

                def clean_id(name):
                    return re.sub(r'\s+', '_', name.lower())

                source_id = clean_id(source_raw)
                target_id = clean_id(target_raw)
                
                if not source_id or not target_id:
                    continue

                predicate = cls.PREDICATES.get(predicate_raw, predicate_raw)
                category = cls.CATEGORIES.get(predicate, "Unknown")
                
                extracted.append({
                    "relationship_id": f"rel_{source_id}_{target_id}_{predicate}",
                    "source_id": source_id,
                    "source_name": source_raw,
                    "target_id": target_id,
                    "target_name": target_raw,
                    "predicate": predicate,
                    "confidence": 0.80,
                    "source_chunk_id": chunk_id,
                    "extraction_method": "regex_rule",
                    "metadata": {
                        "category": category,
                        "directionality": "directional"
                    }
                })
        return extracted
