from __future__ import annotations

from pathlib import Path
import unittest


GUI = Path(__file__).resolve().parents[1] / "serial_plotter_v2" / "gui.py"


class GuiArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = GUI.read_text(encoding="utf-8")

    def test_only_strip_recorder_ui_is_present(self) -> None:
        self.assertIn('self.axes.set_title("Two-Channel Strip Recorder")', self.source)
        self.assertNotIn("plot_mode_combo", self.source)
        self.assertNotIn("Measurement cursor", self.source)
        self.assertNotIn("Franck-Hertz Characteristic", self.source)

    def test_channel_axis_assignments_are_explicit(self) -> None:
        for marker in (
            "self.channel_a_line.set_visible(channel_a)",
            "self.channel_b_left_line.set_visible(channel_b and not channel_a)",
            "self.channel_b_right_line.set_visible(both)",
            "self.secondary_axes.set_visible(both)",
            'self.axes.set_ylabel("Channel A Voltage (V)"',
            'self.axes.set_ylabel("Channel B Voltage (V)"',
        ):
            self.assertIn(marker, self.source)

    def test_neither_channel_is_not_permitted(self) -> None:
        self.assertIn(
            "if not self.channel_a_enabled_var.get() and not self.channel_b_enabled_var.get()",
            self.source,
        )
        self.assertIn("At least one display channel must remain selected.", self.source)


if __name__ == "__main__":
    unittest.main()
