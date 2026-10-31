from __future__ import annotations

import unittest

from serial_plotter_v2 import config
from serial_plotter_v2.core import (
    AcquisitionController,
    Calibration,
    DataPoint,
    ProtocolError,
    convert_sample,
    downsample_for_display,
    parse_data_line,
)


class ProtocolTests(unittest.TestCase):
    def test_external_voltages_and_optional_calibration(self) -> None:
        raw = parse_data_line("DATA,125,16000,8000,10.000000,5.000000")
        point = convert_sample(
            raw,
            Calibration(2.0, 0.5, 0.5, -0.25),
            4.096,
            0.512,
        )
        self.assertAlmostEqual(point.channel_a_voltage_v, 20.5)
        self.assertAlmostEqual(point.channel_b_voltage_v, 2.25)
        self.assertAlmostEqual(point.channel_a_adc_v, 2.0)
        self.assertAlmostEqual(point.channel_b_adc_v, 0.125)

    def test_identity_calibration_preserves_firmware_reported_voltages(self) -> None:
        point = convert_sample(
            parse_data_line("DATA,1,100,200,12.345000,6.789000"),
            Calibration(),
        )
        self.assertAlmostEqual(point.channel_a_voltage_v, 12.345)
        self.assertAlmostEqual(point.channel_b_voltage_v, 6.789)

    def test_malformed_records_are_rejected(self) -> None:
        for record in (
            "",
            "DATA,1,2",
            "DATA,time,1,2,3,4",
            "DATA,1,40000,2,3,4",
            "DATA,1,1,2,7000,4",
        ):
            with self.subTest(record=record), self.assertRaises(ProtocolError):
                parse_data_line(record)


class ControllerTests(unittest.TestCase):
    def test_pause_resume_retains_data_and_range_state_is_per_channel(self) -> None:
        sent: list[bytes] = []
        controller = AcquisitionController(sent.append)
        controller.mark_device_ready()
        controller.set_adc_ranges(4.096, 0.512)
        controller.start()
        point = controller.ingest("DATA,10,16000,16000,2.000000,0.250000")
        assert point is not None
        self.assertAlmostEqual(point.channel_a_adc_v, 2.0)
        self.assertAlmostEqual(point.channel_b_adc_v, 0.25)
        controller.stop()
        controller.ingest("DATA,20,1,2,3,4")
        self.assertEqual(len(controller.dataset), 1)
        controller.start()
        controller.ingest("DATA,30,1,2,3,4")
        self.assertEqual(len(controller.dataset), 2)
        self.assertEqual(
            sent,
            [config.START_COMMAND, config.STOP_COMMAND, config.START_COMMAND],
        )

    def test_malformed_line_is_counted_without_crashing(self) -> None:
        controller = AcquisitionController(lambda data: None)
        controller.mark_device_ready()
        controller.start()
        self.assertIsNone(controller.ingest("garbage"))
        self.assertEqual(controller.malformed_lines, 1)

    def test_downsampling_returns_both_voltage_channels(self) -> None:
        points = tuple(
            DataPoint(
                elapsed_ms=index * 100,
                channel_a_voltage_v=float(index),
                channel_b_voltage_v=float(index * 10),
                channel_a_adc_v=0.0,
                channel_b_adc_v=0.0,
                channel_a_adc_counts=0.0,
                channel_b_adc_counts=0.0,
                channel_a_adc_range_v=2.048,
                channel_b_adc_range_v=2.048,
            )
            for index in range(7)
        )
        times, channel_a, channel_b = downsample_for_display(points, maximum=3)
        self.assertEqual(times, [0.0, 0.3, 0.6])
        self.assertEqual(channel_a, [0.0, 3.0, 6.0])
        self.assertEqual(channel_b, [0.0, 30.0, 60.0])


if __name__ == "__main__":
    unittest.main()
