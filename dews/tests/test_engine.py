import unittest

from dews_safe_sim.engine import SafetySimulation
from dews_safe_sim.models import Reading


class SafetySimulationTest(unittest.TestCase):
    def test_flags_current_temperature_and_rf_noise(self):
        readings = [
            Reading(timestamp_ms=0, voltage_v=12.0, current_a=2.5, temperature_c=72.0, rf_noise_dbm=-18.0)
        ]
        findings = SafetySimulation().analyze(readings)
        self.assertEqual({finding.metric for finding in findings}, {"current_a", "temperature_c", "rf_noise_dbm"})

    def test_flags_safe_visual_and_thermal_hazards_without_engagement(self):
        readings = [
            Reading(
                timestamp_ms=0,
                voltage_v=12.0,
                current_a=0.5,
                temperature_c=32.0,
                rf_noise_dbm=-50.0,
                visual_hazard_confidence=0.91,
                thermal_hotspot_c=92.0,
                line_of_sight_m=300.0,
            )
        ]
        findings = SafetySimulation().analyze(readings)
        actions = {finding.protective_action for finding in findings}
        self.assertEqual({finding.metric for finding in findings}, {"visual_hazard_confidence", "thermal_hotspot_c"})
        self.assertIn("alert_and_evidence", actions)
        self.assertIn("evacuate_and_monitor", actions)
        for finding in findings:
            self.assertNotIn("heat", finding.recommendation.lower())
            self.assertNotIn("damage", finding.recommendation.lower())


if __name__ == "__main__":
    unittest.main()
