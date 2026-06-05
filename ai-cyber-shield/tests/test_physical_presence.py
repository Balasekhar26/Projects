import unittest

from asa.physical_presence import CyberEvent, PresenceEvent, correlate_presence


class PhysicalPresenceTest(unittest.TestCase):
    def test_unknown_presence_plus_usb_is_high_risk(self):
        result = correlate_presence(
            PresenceEvent("desk", 0.9, 10_000),
            [CyberEvent("usb_inserted", 11_000)],
        )

        self.assertEqual(result.risk_level, "high")
        self.assertEqual(result.recommended_action, "lock_screen_and_alert")

    def test_known_user_presence_stays_low(self):
        result = correlate_presence(
            PresenceEvent("desk", 0.9, 10_000, known_user_present=True),
            [CyberEvent("login_attempt", 11_000)],
        )

        self.assertEqual(result.risk_level, "low")


if __name__ == "__main__":
    unittest.main()

