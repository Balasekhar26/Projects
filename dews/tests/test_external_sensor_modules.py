import unittest

from modules.animal_audio import AnimalAudioDetection, animal_detection_to_finding
from modules.wifi_sensing import WifiCsiPrediction, build_csi_sense_zero_command, prediction_to_finding


class ExternalSensorModuleTest(unittest.TestCase):
    def test_wifi_fall_prediction_becomes_safe_alert(self):
        finding = prediction_to_finding(WifiCsiPrediction("fall", 0.88, zone="lab"))

        self.assertIsNotNone(finding)
        self.assertEqual(finding.metric, "wifi_csi_fall")
        self.assertEqual(finding.protective_action, "alert_and_check")

    def test_low_confidence_wifi_prediction_is_ignored(self):
        self.assertIsNone(prediction_to_finding(WifiCsiPrediction("walking", 0.2)))

    def test_csi_sense_zero_command_points_to_downloaded_runtime(self):
        command = build_csi_sense_zero_command(r"C:\Users\balu\Projects\external-projects\CSI-Sense-Zero")

        self.assertIn("main.py", command[1])
        self.assertIn("--host", command)

    def test_animal_distress_becomes_environmental_alert(self):
        finding = animal_detection_to_finding(
            AnimalAudioDetection("dog", "sharp_repeated_bark", 0.82, distress_score=0.74, zone="front")
        )

        self.assertIsNotNone(finding)
        self.assertEqual(finding.metric, "animal_audio_distress")
        self.assertEqual(finding.protective_action, "alert_and_evidence")


if __name__ == "__main__":
    unittest.main()

