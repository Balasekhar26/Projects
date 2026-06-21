import unittest
import time
from unittest.mock import patch
from backend.core.adaptive_runtime import HardwareProfiler, PerformanceProfile, AdaptiveContext, SelfLearningEngine

class TestAdaptiveRuntime(unittest.TestCase):

    def test_hardware_profiler(self):
        profile = HardwareProfiler.get_profile()
        self.assertIn("os", profile)
        self.assertIn("ram_total_gb", profile)
        self.assertIn("cpu_logical_cores", profile)
        self.assertIn("storage_type", profile)
        self.assertIn("on_ac_power", profile)
        self.assertGreater(profile["ram_total_gb"], 0.0)
        self.assertGreater(profile["cpu_logical_cores"], 0)

    def test_performance_profile_resolution(self):
        # ECO mode triggers: under 8GB RAM
        hw_eco = {
            "ram_total_gb": 4.0,
            "has_gpu_acceleration": False,
            "on_ac_power": True,
            "gpu_vram_gb": 0.0
        }
        self.assertEqual(PerformanceProfile.resolve_profile(hw_eco), "ECO")

        # ECO mode triggers: CPU-only & on battery power
        hw_eco_battery = {
            "ram_total_gb": 16.0,
            "has_gpu_acceleration": False,
            "on_ac_power": False,
            "gpu_vram_gb": 0.0
        }
        self.assertEqual(PerformanceProfile.resolve_profile(hw_eco_battery), "ECO")

        # BALANCED mode trigger: 8GB - 16GB RAM on AC
        hw_balanced = {
            "ram_total_gb": 12.0,
            "has_gpu_acceleration": True,
            "on_ac_power": True,
            "gpu_vram_gb": 4.0
        }
        self.assertEqual(PerformanceProfile.resolve_profile(hw_balanced), "BALANCED")

        # BEAST mode trigger: 32GB+ RAM & >= 8GB VRAM
        hw_beast = {
            "ram_total_gb": 64.0,
            "has_gpu_acceleration": True,
            "on_ac_power": True,
            "gpu_vram_gb": 16.0
        }
        self.assertEqual(PerformanceProfile.resolve_profile(hw_beast), "BEAST")

    def test_adaptive_context_limits(self):
        eco_limits = AdaptiveContext.get_limits("ECO")
        self.assertEqual(eco_limits["max_context_tokens"], 1500)
        self.assertTrue(eco_limits["compress_history"])
        self.assertFalse(eco_limits["disk_buffer_enabled"])

        beast_limits = AdaptiveContext.get_limits("BEAST")
        self.assertEqual(beast_limits["max_context_tokens"], 16000)
        self.assertFalse(beast_limits["compress_history"])
        self.assertTrue(beast_limits["disk_buffer_enabled"])

    def test_self_learning_engine(self):
        model = "test-model"
        
        # Initially healthy
        SelfLearningEngine.reset_failures(model)
        self.assertTrue(SelfLearningEngine.is_model_healthy(model))
        
        # Test latency logs
        SelfLearningEngine.log_response_time(model, 1.2)
        SelfLearningEngine.log_response_time(model, 2.5)
        self.assertTrue(SelfLearningEngine.is_model_healthy(model))
        
        # Trigger health failure by logging high average latency (>25s)
        import backend.core.adaptive_runtime as ar
        ar._metrics_log[model] = [30.0, 32.0]
        self.assertFalse(SelfLearningEngine.is_model_healthy(model))
        
        # Reset and check healthy again
        import backend.core.adaptive_runtime as ar
        ar._metrics_log[model] = [2.0] # override high average
        self.assertTrue(SelfLearningEngine.is_model_healthy(model))
        
        # Trigger failure count
        SelfLearningEngine.log_failure(model)
        SelfLearningEngine.log_failure(model)
        SelfLearningEngine.log_failure(model)
        self.assertFalse(SelfLearningEngine.is_model_healthy(model))
        
        # Reset and check healthy again
        SelfLearningEngine.reset_failures(model)
        self.assertTrue(SelfLearningEngine.is_model_healthy(model))

    @patch("httpx.post")
    def test_agent_hibernation(self, mock_post):
        from backend.core.adaptive_runtime import AgentHibernationEngine
        mock_post.return_value.status_code = 200
        
        AgentHibernationEngine.touch_model("test-model-warm")
        self.assertIn("test-model-warm", AgentHibernationEngine._last_used)
        
        success = AgentHibernationEngine.hibernate_model("test-model-warm", "http://127.0.0.1:11434")
        self.assertTrue(success)
        mock_post.assert_called_with(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model": "test-model-warm",
                "messages": [],
                "keep_alive": 0,
                "stream": False
            },
            timeout=5.0
        )

    def test_predictive_model_loading(self):
        from backend.core.adaptive_runtime import PredictiveModelLoader
        with patch("backend.core.adaptive_runtime.WarmupManager.warm_model_background") as mock_warm:
            PredictiveModelLoader.predict_and_warm("def my_func(a, b):")
            mock_warm.assert_called()

    def test_semantic_response_cache(self):
        from backend.core.adaptive_runtime import SemanticResponseCache
        query = "Explain git in one word."
        response = "Distributed."
        SemanticResponseCache.set(query, response, "general")
        
        cached_res, cached_agent = SemanticResponseCache.get(query)
        self.assertEqual(cached_res, response)
        self.assertEqual(cached_agent, "general")
        
        cached_res2, _ = SemanticResponseCache.get("Explain git in single word")
        self.assertEqual(cached_res2, response)

    def test_memory_prefetcher(self):
        from backend.core.adaptive_runtime import MemoryPrefetcher
        with patch("backend.core.memory.memory.search_chat_messages") as mock_search, \
             patch("backend.core.memory.build_memory_context") as mock_context:
            mock_search.return_value = [{"role": "user", "content": "hi"}]
            mock_context.return_value = "prefetched-context"
            
            MemoryPrefetcher.prefetch("msg-123", "hi", "session-123")
            time.sleep(0.5)
            
            result = MemoryPrefetcher.get_result("msg-123")
            self.assertIsNotNone(result)
            self.assertEqual(result["memory_context"], "prefetched-context")

    def test_gpu_task_scheduler(self):
        from backend.core.adaptive_runtime import GPUTaskScheduler
        model = GPUTaskScheduler.route_task("hi", "general")
        self.assertEqual(model, "qwen2.5:0.5b")

    def test_self_healing_runtime(self):
        from backend.core.adaptive_runtime import SelfHealingRuntime
        with patch("backend.core.model_router.health") as mock_health:
            mock_health.return_value = (True, "Ollama reachable")
            self.assertTrue(SelfHealingRuntime.heal_ollama())

    def test_memory_compression_engine(self):
        from backend.core.adaptive_runtime import MemoryCompressionEngine
        with patch("backend.core.memory.memory.list_chat_messages") as mock_list, \
             patch("backend.core.model_router.ask_model") as mock_ask, \
             patch("sqlite3.connect") as mock_conn:
            mock_list.return_value = [
                {"id": "1", "role": "user", "content": "hello", "created_at": "2026"},
                {"id": "2", "role": "assistant", "content": "hi", "created_at": "2026"},
                {"id": "3", "role": "user", "content": "how", "created_at": "2026"},
                {"id": "4", "role": "assistant", "content": "good", "created_at": "2026"},
                {"id": "5", "role": "user", "content": "are", "created_at": "2026"},
                {"id": "6", "role": "assistant", "content": "you", "created_at": "2026"},
                {"id": "7", "role": "user", "content": "today", "created_at": "2026"},
                {"id": "8", "role": "assistant", "content": "fine", "created_at": "2026"},
                {"id": "9", "role": "user", "content": "and", "created_at": "2026"},
                {"id": "10", "role": "assistant", "content": "you", "created_at": "2026"},
                {"id": "11", "role": "user", "content": "yes", "created_at": "2026"},
                {"id": "12", "role": "assistant", "content": "good", "created_at": "2026"},
            ]
            mock_ask.return_value = "compressed summary"
            MemoryCompressionEngine.compress_history("session-123", threshold=10)
            mock_ask.assert_called()

    @patch("httpx.get")
    @patch("httpx.post")
    def test_vram_occupancy_and_lru_eviction(self, mock_post, mock_get):
        from backend.core.adaptive_runtime import AgentHibernationEngine
        
        # Mock HardwareProfiler profile
        with patch("backend.core.adaptive_runtime.HardwareProfiler.get_profile") as mock_profile:
            mock_profile.return_value = {
                "gpu_vram_gb": 4.0,
                "has_gpu_acceleration": True
            }
            
            # Mock get response for /api/ps to show VRAM occupancy > 80% (3.5 GB used out of 4 GB)
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {
                "models": [
                    {"name": "old-model-1", "model": "old-model-1", "size_vram": 2 * 1024**3},
                    {"name": "old-model-2", "model": "old-model-2", "size_vram": 1.5 * 1024**3}
                ]
            }
            
            # Record last used times
            AgentHibernationEngine._last_used["old-model-1"] = 100.0
            AgentHibernationEngine._last_used["old-model-2"] = 200.0
            
            # Touching "incoming-model" should trigger eviction of "old-model-1" (oldest timestamp 100.0 < 200.0)
            AgentHibernationEngine.touch_model("incoming-model")
            
            # Verify hibernate was called on old-model-1
            mock_post.assert_any_call(
                "http://127.0.0.1:11434/api/chat",
                json={
                    "model": "old-model-1",
                    "messages": [],
                    "keep_alive": 0,
                    "stream": False
                },
                timeout=5.0
            )
