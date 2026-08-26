from __future__ import annotations

from pathlib import Path
import unittest


SKETCH = (
    Path(__file__).resolve().parents[1]
    / "Arduino Shield for Aquisition"
    / "Uno_Sketch"
    / "Uno_Sketch.ino"
)


class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SKETCH.read_text(encoding="utf-8")

    def test_current_dual_channel_protocol_and_adc_address_are_present(self) -> None:
        for marker in (
            "#protocol,modern-lab-dual-channel,4",
            "const uint8_t ADS1115_I2C_ADDRESS = 0x49;",
            "ads.begin(ADS1115_I2C_ADDRESS)",
            "const uint8_t CHANNEL_A_INPUT = 0;",
            "const uint8_t CHANNEL_B_INPUT = 2;",
        ):
            self.assertIn(marker, self.source)

    def test_autoranging_and_divider_calibration_are_retained(self) -> None:
        for marker in (
            "updateChannelAutorange(0, maximumA)",
            "updateChannelAutorange(1, maximumB)",
            "AUTORANGE_NARROW_RECORDS",
            "AUTORANGE_COOLDOWN_RECORDS",
            "externalVoltage(averagedA, sampledRangeA, RAhigh, RAlow)",
            "externalVoltage(averagedB, sampledRangeB, RBhigh, RBlow)",
            "dividerConfigChecksum",
            "EEPROM.put(CONFIG_EEPROM_ADDRESS, config);",
        ):
            self.assertIn(marker, self.source)

    def test_obsolete_gain_architecture_is_absent(self) -> None:
        for marker in (
            "SoftwareSerial",
            "LEGACY_MODE",
            '"1x"',
            '"10x"',
            "scaleFactor",
        ):
            self.assertNotIn(marker, self.source)


if __name__ == "__main__":
    unittest.main()
