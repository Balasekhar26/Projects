import threading
import time
import unittest
from unittest.mock import patch

from backend.core.sensory_memory import SensoryMemory


class TestSensoryMemory(unittest.TestCase):

    def setUp(self):
        # Reset buffers before each test
        SensoryMemory.clear_all()

    def test_add_and_retrieve_observations(self):
        """Verify observations can be added, searched, and sorted chronologically."""
        # 1. Add user turn
        id1 = SensoryMemory.add_observation("USER_TURN", "Hi Kattappa")
        self.assertIsNotNone(id1)

        # 2. Add assistant turn
        id2 = SensoryMemory.add_observation("ASSISTANT_TURN", "Hello Bala!")
        self.assertIsNotNone(id2)

        # 3. Retrieve all
        obs = SensoryMemory.get_recent_observations()
        self.assertEqual(len(obs), 2)
        
        # Chronological sorting verification
        self.assertEqual(obs[0]["id"], id1)
        self.assertEqual(obs[1]["id"], id2)

        # 4. Filter by type
        user_obs = SensoryMemory.get_recent_observations(obs_type="USER_TURN")
        self.assertEqual(len(user_obs), 1)
        self.assertEqual(user_obs[0]["content"], "Hi Kattappa")

        # 5. Invalid type raises error
        with self.assertRaises(ValueError):
            SensoryMemory.add_observation("INVALID_TYPE", "data")

    def test_capacity_eviction_limit(self):
        """Verify queues cap at max capacity, evicting the oldest element in FIFO order."""
        # Add 12 items under cap of 10
        ids = []
        for i in range(12):
            ids.append(SensoryMemory.add_observation("TOOL_OBSERVATION", f"tool response {i}", max_capacity=10))

        obs = SensoryMemory.get_recent_observations(obs_type="TOOL_OBSERVATION")
        self.assertEqual(len(obs), 10)
        
        # Verify oldest elements (ids[0] and ids[1]) were evicted
        active_ids = [item["id"] for item in obs]
        self.assertNotIn(ids[0], active_ids)
        self.assertNotIn(ids[1], active_ids)
        self.assertEqual(obs[0]["id"], ids[2])
        self.assertEqual(obs[-1]["id"], ids[11])

    def test_ttl_expiration(self):
        """Verify observations decay and expire after their configured Time-To-Live."""
        now = time.time()
        with patch("time.time", return_value=now):
            # Observation expires in 5 seconds
            obs_id = SensoryMemory.add_observation("ENVIRONMENT_SIGNAL", "Low battery warning", ttl_seconds=5)

        # Check it is active initially
        with patch("time.time", return_value=now + 2):
            self.assertEqual(len(SensoryMemory.get_recent_observations()), 1)

        # Check it expires after 6 seconds
        with patch("time.time", return_value=now + 6):
            self.assertEqual(len(SensoryMemory.get_recent_observations()), 0)
            
            # Verify cleanup sweep prunes it
            pruned = SensoryMemory.run_cleanup_sweep()
            self.assertEqual(pruned, 1)

    def test_sensory_context_formatting(self):
        """Verify sensory context dictionary structure formats correctly for Working Memory."""
        SensoryMemory.add_observation("USER_TURN", "Turn prompt text")
        SensoryMemory.add_observation("EVENT_NOTIFICATION", "System notification event")

        context = SensoryMemory.get_sensory_context()
        self.assertIn("user_turn", context)
        self.assertIn("event_notification", context)
        self.assertIn("tool_observation", context)
        
        self.assertEqual(len(context["user_turn"]), 1)
        self.assertEqual(context["user_turn"][0]["content"], "Turn prompt text")
        self.assertEqual(len(context["event_notification"]), 1)
        self.assertEqual(context["event_notification"][0]["content"], "System notification event")
        self.assertEqual(len(context["tool_observation"]), 0)

    def test_multithreaded_concurrency_safety(self):
        """Verify thread locks prevent collisions during high-frequency multithreaded pushes."""
        threads = []
        
        def push_observations():
            for i in range(50):
                SensoryMemory.add_observation("USER_TURN", f"msg {i}", max_capacity=200)

        # Spawn 5 parallel threads pushing observations
        for _ in range(5):
            t = threading.Thread(target=push_observations)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        obs = SensoryMemory.get_recent_observations(obs_type="USER_TURN")
        self.assertEqual(len(obs), 200) # Capped at 200 capacity limit
