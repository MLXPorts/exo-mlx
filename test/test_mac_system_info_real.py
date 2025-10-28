#!/usr/bin/env python3
import os
import sys
import platform
import types
import unittest


class TestMacSystemInfoReal(unittest.TestCase):
    @unittest.skipUnless(platform.system() == "Darwin", "macOS only test")
    def test_real_system_profiler_parsing(self):
        # Stub scapy to avoid dependency when importing helpers
        if 'scapy' not in sys.modules:
            scapy = types.ModuleType('scapy')
            scapy_all = types.ModuleType('scapy.all')
            def _dummy_addr(_iface):
                return '127.0.0.1'
            def _dummy_list():
                return ['lo0']
            scapy_all.get_if_addr = _dummy_addr
            scapy_all.get_if_list = _dummy_list
            scapy.all = scapy_all
            sys.modules['scapy'] = scapy
            sys.modules['scapy.all'] = scapy_all

        import asyncio
        from exo.helpers import get_mac_system_info

        model, chip, memory_mb = asyncio.run(get_mac_system_info())
        print(f"Detected model={model!r}, chip={chip!r}, memory_mb={memory_mb}")

        # Basic sanity assertions for real hardware
        self.assertNotEqual(model, "Unknown Model")
        self.assertTrue(chip.startswith("Apple ") or chip.startswith("Unknown") == False)
        self.assertGreater(memory_mb, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)

