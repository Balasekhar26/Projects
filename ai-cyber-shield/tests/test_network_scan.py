import unittest

from asa.network_scan import _parse_nmap_text, _parse_ports, _safe_target


class LocalNetworkScanTest(unittest.TestCase):
    def test_safe_target_allows_private_and_loopback(self):
        self.assertEqual(_safe_target("localhost"), "127.0.0.1")
        self.assertEqual(_safe_target("192.168.1.20"), "192.168.1.20")
        self.assertEqual(_safe_target("10.0.0.0/24"), "10.0.0.0/24")

    def test_safe_target_blocks_public_or_large_scopes(self):
        with self.assertRaises(ValueError):
            _safe_target("8.8.8.8")
        with self.assertRaises(ValueError):
            _safe_target("10.0.0.0/16")

    def test_port_parser_limits_scope(self):
        self.assertEqual(_parse_ports("22,80,8000-8002"), [22, 80, 8000, 8001, 8002])
        with self.assertRaises(ValueError):
            _parse_ports("1-100")

    def test_parse_nmap_text_keeps_open_ports(self):
        output = """
Nmap scan report for 192.168.1.10
PORT     STATE SERVICE
22/tcp   open  ssh
80/tcp   closed http
8080/tcp open  http-proxy
"""
        observations = _parse_nmap_text("192.168.1.10", output)
        self.assertEqual([item.port for item in observations], [22, 8080])
        self.assertEqual(observations[0].service_hint, "ssh")


if __name__ == "__main__":
    unittest.main()
