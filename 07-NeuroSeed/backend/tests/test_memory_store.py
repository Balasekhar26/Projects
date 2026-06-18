from __future__ import annotations

from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_store import NeuroSeedMemoryStore


class FakeChromaCollection:
    def __init__(self) -> None:
        self.documents: dict[str, str] = {}

    def upsert(self, ids, documents, metadatas) -> None:
        for memory_id, document in zip(ids, documents):
            self.documents[memory_id] = document

    def delete(self, ids) -> None:
        for memory_id in ids:
            self.documents.pop(memory_id, None)


class NeuroSeedMemoryStoreTest(unittest.TestCase):
    def test_preserves_consent_boundary(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            store = NeuroSeedMemoryStore(sqlite_path=Path(temp_dir) / "neuroseed.db")
            fake_collection = FakeChromaCollection()
            store._collection = fake_collection

            blocked = {
                "dataModel": {"version": "pilot-consent-v1"},
                "seeds": [
                    {
                        "id": "seed-blocked",
                        "title": "Blocked",
                        "text": "Unapproved content",
                        "keywords": ["blocked"],
                        "cue": {"type": "audio", "label": "A-01", "tones": [220], "pattern": [80]},
                        "approved": False,
                        "consent": {"status": "pending", "model": "pilot-consent-v1", "approvedAt": None},
                        "createdAt": "2026-06-14T10:00:00",
                    }
                ],
                "sessions": [
                    {
                        "id": "session-blocked",
                        "startedAt": "2026-06-14T10:05:00",
                        "status": "completed",
                        "approvedSeedIds": ["seed-blocked"],
                        "cueEvents": [
                            {
                                "seedId": "seed-blocked",
                                "seedTitle": "Blocked",
                                "cueLabel": "A-01",
                                "stage": "N2",
                                "cuedAt": "2026-06-14T10:06:00",
                            }
                        ],
                        "settings": {"maxCues": 1, "volume": 8, "haptic": 0, "allowedStages": ["N2", "N3"]},
                        "safetyBoundary": {"version": "pilot-consent-v1"},
                    }
                ],
                "recallResults": [],
            }
            with self.assertRaises(ValueError):
                store.upsert_state(blocked)
            self.assertEqual(fake_collection.documents, {})

            state = store.upsert_state(
                {
                    "dataModel": {"version": "pilot-consent-v1"},
                    "seeds": [
                        {
                            "id": "seed-approved",
                            "title": "Hippocampus cue",
                            "text": "Hippocampus binds episodic memories before cortical integration.",
                            "keywords": ["hippocampus", "episodic", "cortical"],
                            "cue": {"type": "audio", "label": "A-02", "tones": [261, 330], "pattern": [80, 40, 120]},
                            "approved": True,
                            "consent": {
                                "status": "awake-approved",
                                "model": "pilot-consent-v1",
                                "approvedAt": "2026-06-14T10:00:00",
                            },
                            "createdAt": "2026-06-14T09:55:00",
                        }
                    ],
                    "sessions": [
                        {
                            "id": "session-approved",
                            "startedAt": "2026-06-14T10:05:00",
                            "endedAt": "2026-06-14T10:10:00",
                            "status": "completed",
                            "approvedSeedIds": ["seed-approved"],
                            "cueEvents": [
                                {
                                    "seedId": "seed-approved",
                                    "seedTitle": "Hippocampus cue",
                                    "cueLabel": "A-02",
                                    "stage": "N2",
                                    "cuedAt": "2026-06-14T10:06:00",
                                }
                            ],
                            "settings": {"maxCues": 1, "volume": 8, "haptic": 0, "allowedStages": ["N2", "N3"]},
                            "safetyBoundary": {"version": "pilot-consent-v1"},
                        }
                    ],
                    "recallResults": [
                        {
                            "id": "recall-approved",
                            "sessionId": "session-approved",
                            "seedId": "seed-approved",
                            "seedTitle": "Hippocampus cue",
                            "condition": "uncued",
                            "answer": "hippocampus episodic",
                            "score": 0.5,
                            "checkedAt": "2026-06-14T11:00:00",
                            "consentModel": "pilot-consent-v1",
                        }
                    ],
                }
            )

            self.assertEqual(state["summary"]["approvedCount"], 1)
            self.assertEqual(state["recallResults"][0]["condition"], "cued")
            self.assertEqual(state["consentLogs"][0]["consentStatus"], "awake-approved")
            self.assertIn("neuroseed:seed-approved", fake_collection.documents)

            state = store.upsert_state({
                "dataModel": {"version": "pilot-consent-v1"},
                "seeds": [],
                "sessions": [],
                "recallResults": [],
            })
            self.assertEqual(state["summary"]["seedCount"], 0)
            self.assertEqual(fake_collection.documents, {})


if __name__ == "__main__":
    unittest.main()
