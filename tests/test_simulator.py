from __future__ import annotations

import queue
import time
import unittest

from serial_plotter_v2 import config
from serial_plotter_v2.core import AcquisitionController
from serial_plotter_v2.transport import SimulatorTransport


class SimulatorTests(unittest.TestCase):
    def test_protocol_streams_two_calibrated_voltage_channels(self) -> None:
        lines: queue.Queue[bytes] = queue.Queue()
        simulator = SimulatorTransport(lines.put, lambda error: None)
        simulator.open()
        self.addCleanup(simulator.close)
        self.assertEqual(lines.get(timeout=1).decode(), config.HANDSHAKE_BANNER)
        self.assertEqual(lines.get(timeout=1).decode(), config.PROTOCOL_CAPABILITY)
        for _ in range(3):
            lines.get(timeout=1)

        controller = AcquisitionController(simulator.write)
        controller.mark_device_ready()
        simulator.write(b"delay,10\n")
        controller.start()
        deadline = time.monotonic() + 1.0
        while len(controller.dataset) < 3 and time.monotonic() < deadline:
            line = lines.get(timeout=0.5)
            if line.startswith(b"DATA,"):
                controller.ingest(line)
        self.assertGreaterEqual(len(controller.dataset), 3)
        point = controller.dataset.snapshot()[-1]
        self.assertGreaterEqual(point.channel_a_voltage_v, 0.0)
        self.assertGreaterEqual(point.channel_b_voltage_v, 0.0)

    def test_manual_ranges_are_independent(self) -> None:
        lines: queue.Queue[bytes] = queue.Queue()
        simulator = SimulatorTransport(lines.put, lambda error: None)
        simulator.open()
        self.addCleanup(simulator.close)
        for _ in range(5):
            lines.get(timeout=1)
        simulator.write(b"autorange,0\n")
        for _ in range(3):
            lines.get(timeout=1)
        simulator.write(b"range,A,1.024\n")
        lines.get(timeout=1)
        self.assertEqual(lines.get(timeout=1), b"#range,A=1.024,B=2.048")
        simulator.write(b"range,B,0.512\n")
        lines.get(timeout=1)
        self.assertEqual(lines.get(timeout=1), b"#range,A=1.024,B=0.512")
        self.assertEqual(simulator.active_ranges, (1.024, 0.512))

    def test_autorange_widens_and_narrows_with_persistence(self) -> None:
        simulator = SimulatorTransport(lambda line: None, lambda error: None)
        simulator._range_indices[:] = [3, 4]
        self.assertTrue(simulator._update_channel_autorange(0, 30_000.0))
        self.assertEqual(simulator.active_ranges, (2.048, 0.512))

        simulator._range_indices[1] = config.ADC_RANGE_VOLTS.index(2.048)
        simulator._range_cooldown[1] = 0
        for _ in range(config.AUTORANGE_NARROW_RECORDS - 1):
            self.assertFalse(simulator._update_channel_autorange(1, 3_200.0))
        self.assertTrue(simulator._update_channel_autorange(1, 3_200.0))
        self.assertEqual(simulator.active_ranges[1], 1.024)

    def test_voltage_report_is_independent_of_active_range(self) -> None:
        simulator = SimulatorTransport(lambda line: None, lambda error: None)
        elapsed = config.SIMULATOR_PERIOD_SECONDS / 6.0
        values: list[float] = []
        for range_v in (4.096, 2.048, 1.024):
            simulator._range_indices[0] = config.ADC_RANGE_VOLTS.index(range_v)
            fields = simulator._make_sample(elapsed).decode().split(",")
            values.append(float(fields[4]))
        for voltage in values:
            self.assertAlmostEqual(voltage, 10.0, delta=0.03)

    def test_obsolete_gain_commands_are_not_supported(self) -> None:
        lines: queue.Queue[bytes] = queue.Queue()
        simulator = SimulatorTransport(lines.put, lambda error: None)
        simulator.open()
        self.addCleanup(simulator.close)
        for _ in range(5):
            lines.get(timeout=1)
        for command in (b"1x\n", b"10x\n", b"mode,legacy\n"):
            simulator.write(command)
            self.assertEqual(lines.get(timeout=1), b"ERR,UNKNOWN_COMMAND")


if __name__ == "__main__":
    unittest.main()
