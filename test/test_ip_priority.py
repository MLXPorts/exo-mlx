#!/usr/bin/env python
"""Test IP address prioritization"""

import unittest
from exo.helpers import _ip_address_priority


class TestIPPriority(unittest.TestCase):
    """Test IP address priority ordering"""

    def test_link_local_highest_priority(self):
        """Link-local (169.254.x.x) should have highest priority (0)"""
        self.assertEqual(_ip_address_priority("169.254.1.1"), 0)
        self.assertEqual(_ip_address_priority("169.254.10.20"), 0)
        self.assertEqual(_ip_address_priority("169.254.255.254"), 0)

    def test_private_networks_second_priority(self):
        """Private networks should have second priority (1)"""
        self.assertEqual(_ip_address_priority("10.0.0.1"), 1)
        self.assertEqual(_ip_address_priority("10.255.255.254"), 1)
        self.assertEqual(_ip_address_priority("192.168.1.1"), 1)
        self.assertEqual(_ip_address_priority("192.168.255.254"), 1)
        self.assertEqual(_ip_address_priority("172.16.0.1"), 1)
        self.assertEqual(_ip_address_priority("172.31.255.254"), 1)

    def test_public_ips_third_priority(self):
        """Public IPs should have third priority (2)"""
        self.assertEqual(_ip_address_priority("8.8.8.8"), 2)
        self.assertEqual(_ip_address_priority("1.1.1.1"), 2)
        self.assertEqual(_ip_address_priority("100.64.0.1"), 2)  # Carrier-grade NAT

    def test_localhost_lowest_priority(self):
        """Localhost should have lowest priority (3)"""
        self.assertEqual(_ip_address_priority("127.0.0.1"), 3)
        self.assertEqual(_ip_address_priority("127.0.1.1"), 3)
        self.assertEqual(_ip_address_priority("127.255.255.254"), 3)

    def test_priority_ordering(self):
        """Test that priorities are correctly ordered"""
        addresses = [
            "127.0.0.1",      # Localhost - priority 3
            "10.0.0.1",       # Private - priority 1
            "169.254.1.1",    # Link-local - priority 0
            "8.8.8.8",        # Public - priority 2
            "192.168.1.1",    # Private - priority 1
        ]

        sorted_addrs = sorted(addresses, key=_ip_address_priority)

        # Expected order: link-local, private, private, public, localhost
        self.assertEqual(sorted_addrs[0], "169.254.1.1")  # Link-local first
        self.assertIn(sorted_addrs[1], ["10.0.0.1", "192.168.1.1"])  # Private networks
        self.assertIn(sorted_addrs[2], ["10.0.0.1", "192.168.1.1"])
        self.assertEqual(sorted_addrs[3], "8.8.8.8")  # Public
        self.assertEqual(sorted_addrs[4], "127.0.0.1")  # Localhost last

    def test_link_local_range_boundaries(self):
        """Test boundary conditions for link-local range"""
        # Valid link-local
        self.assertEqual(_ip_address_priority("169.254.0.0"), 0)
        self.assertEqual(_ip_address_priority("169.254.255.255"), 0)

        # Not link-local (different class B)
        self.assertNotEqual(_ip_address_priority("169.253.255.255"), 0)
        self.assertNotEqual(_ip_address_priority("169.255.0.0"), 0)


if __name__ == "__main__":
    unittest.main()
