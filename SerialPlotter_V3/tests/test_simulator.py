from __future__ import annotations

import queue
import time
import unittest

from serial_plotter_v3 import config
from serial_plotter_v3.core import AcquisitionController, parse_data_line
from serial_plotter_v3.transport import SimulatorTransport


class SimulatorTests(unittest.TestCase):
    def test_hardware_averaging_command_controls_streamed_records(self) -> None:
        lines: queue.Queue[bytes] = queue.Queue()
        simulator = SimulatorTransport(lines.put, lambda error: None)
        simulator.open()
        self.addCleanup(simulator.close)
        self.assertEqual(lines.get(timeout=1).decode(), config.HANDSHAKE_BANNER)
        self.assertEqual(lines.get(timeout=1).decode(), config.PROTOCOL_CAPABILITY)
        for _ in range(3):
            lines.get(timeout=1)

        simulator.write(b"avg,8\n")
        self.assertEqual(lines.get(timeout=1), b"OK,avg,8")
        simulator.write(b"avg,65\n")
        self.assertTrue(lines.get(timeout=1).startswith(b"ERR,INVALID_AVERAGE"))

        controller = AcquisitionController(simulator.write)
        controller.mark_device_ready()
        controller.set_average_count(8)
        controller.start()
        deadline = time.monotonic() + 2.0
        while len(controller.dataset) < 2 and time.monotonic() < deadline:
            line = lines.get(timeout=0.5)
            if line.startswith(b"DATA,"):
                controller.ingest(line)
        points = controller.dataset.snapshot()
        self.assertGreaterEqual(len(points), 2)
        self.assertTrue(all(point.average_count == 8 for point in points))
        self.assertLess(points[-1].channel_a_voltage_v, 0.0)

    def test_signed_counts_and_peak_magnitude_match_differential_mode(self) -> None:
        simulator = SimulatorTransport(lambda line: None, lambda error: None)
        simulator._averages = 16
        record = simulator._make_sample(0.0)
        raw = parse_data_line(record)
        self.assertLess(raw.channel_a_adc_counts, 0)
        self.assertLess(raw.channel_a_input_v, 0)
        self.assertGreaterEqual(
            simulator._last_magnitudes[0], abs(raw.channel_a_adc_counts)
        )
        self.assertEqual(int(raw.channel_a_adc_counts), raw.channel_a_adc_counts)


if __name__ == "__main__":
    unittest.main()
