from __future__ import annotations

from pathlib import Path
import unittest


SKETCH = (
    Path(__file__).resolve().parents[2]
    / "Frank_Herz"
    / "arduino"
    / "Frank_Herz_DAQ"
    / "Frank_Herz_DAQ.ino"
)


class SharedFirmwareTests(unittest.TestCase):
    def test_canonical_sketch_supports_both_differential_pairs_and_averaging(self) -> None:
        source = SKETCH.read_text(encoding="utf-8")
        for marker in (
            '#protocol,modern-lab-dual-channel,4',
            'ads.readADC_Differential_0_1()',
            'ads.readADC_Differential_2_3()',
            'for (uint8_t sampleIndex = 0; sampleIndex < averageCount; ++sampleIndex)',
            'sumA += rawA;',
            'sumB += rawB;',
            'strcmp(name, "avg") == 0',
            'const uint8_t MAX_AVERAGE_COUNT = 64;',
            'rangeSettlingDiscardPairs = RANGE_SETTLING_DISCARD_PAIRS;',
        ):
            self.assertIn(marker, source)
        self.assertNotIn('readADC_SingleEnded', source)


if __name__ == "__main__":
    unittest.main()
