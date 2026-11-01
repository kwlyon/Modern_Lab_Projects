from __future__ import annotations

from pathlib import Path
import unittest

from openpyxl import load_workbook

from serial_plotter_v3.core import Calibration, convert_sample, parse_data_line
from serial_plotter_v3.export import data_headers, export_xlsx


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.point = convert_sample(
            parse_data_line("DATA,123,1600,3200,1.000000,2.000000"),
            Calibration(),
            average_count=12,
        )
        self.directory = Path(__file__).resolve().parents[1] / ".test_tmp"
        self.directory.mkdir(exist_ok=True)

    def _headers_from_export(self, include_a: bool, include_b: bool) -> tuple[str, ...]:
        path = self.directory / f"export-{include_a}-{include_b}.xlsx"
        try:
            export_xlsx(path, (self.point,), Calibration(), include_a, include_b)
            workbook = load_workbook(path, data_only=True)
            sheet = workbook["Serial Data"]
            headers = tuple(cell.value for cell in sheet[1])
            workbook.close()
            return headers
        finally:
            path.unlink(missing_ok=True)

    def test_channel_a_only_export_omits_channel_b(self) -> None:
        headers = self._headers_from_export(True, False)
        self.assertEqual(headers, data_headers(True, False))
        self.assertTrue(any("Channel A" in header for header in headers))
        self.assertFalse(any("Channel B" in header for header in headers))

    def test_channel_b_only_export_omits_channel_a(self) -> None:
        headers = self._headers_from_export(False, True)
        self.assertEqual(headers, data_headers(False, True))
        self.assertTrue(any("Channel B" in header for header in headers))
        self.assertFalse(any("Channel A" in header for header in headers))

    def test_both_channel_export_contains_both(self) -> None:
        headers = self._headers_from_export(True, True)
        self.assertTrue(any("Channel A" in header for header in headers))
        self.assertTrue(any("Channel B" in header for header in headers))

    def test_export_records_arduino_average_count(self) -> None:
        path = self.directory / "averaging.xlsx"
        try:
            export_xlsx(path, (self.point,), Calibration())
            workbook = load_workbook(path, data_only=True)
            sheet = workbook["Serial Data"]
            self.assertEqual(sheet.cell(1, 2).value, "Arduino Averages (pairs/row)")
            self.assertEqual(sheet.cell(2, 2).value, 12)
            workbook.close()
        finally:
            path.unlink(missing_ok=True)

    def test_inversion_changes_only_selected_connector_voltage(self) -> None:
        path = self.directory / "inverted.xlsx"
        try:
            export_xlsx(
                path, (self.point,), Calibration(),
                invert_channel_a=True, invert_channel_b=False,
            )
            workbook = load_workbook(path, data_only=True)
            sheet = workbook["Serial Data"]
            self.assertEqual(sheet.cell(2, 3).value, -1.0)
            self.assertEqual(sheet.cell(2, 4).value, self.point.channel_a_adc_v)
            self.assertEqual(sheet.cell(2, 7).value, 2.0)
            self.assertTrue(workbook["Calibration"].cell(6, 2).value)
            workbook.close()
        finally:
            path.unlink(missing_ok=True)

    def test_export_rejects_no_channels(self) -> None:
        with self.assertRaises(ValueError):
            data_headers(False, False)


if __name__ == "__main__":
    unittest.main()
