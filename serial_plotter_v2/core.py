"""Protocol parsing, voltage calibration, storage, and acquisition state."""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from typing import Callable, Iterable

from . import config


class ProtocolError(ValueError):
    """Raised when a line is not a valid dual-channel acquisition record."""


@dataclass(frozen=True, slots=True)
class Calibration:
    channel_a_scale: float = config.CHANNEL_A_SCALE
    channel_a_offset_v: float = config.CHANNEL_A_OFFSET_V
    channel_b_scale: float = config.CHANNEL_B_SCALE
    channel_b_offset_v: float = config.CHANNEL_B_OFFSET_V

    def __post_init__(self) -> None:
        values = (
            self.channel_a_scale,
            self.channel_a_offset_v,
            self.channel_b_scale,
            self.channel_b_offset_v,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Calibration values must be finite.")
        if self.channel_a_scale == 0 or self.channel_b_scale == 0:
            raise ValueError("Channel calibration scales must be nonzero.")


@dataclass(frozen=True, slots=True)
class RawSample:
    elapsed_ms: int
    channel_a_adc_counts: float
    channel_b_adc_counts: float
    channel_a_input_v: float
    channel_b_input_v: float


@dataclass(frozen=True, slots=True)
class DataPoint:
    elapsed_ms: int
    channel_a_voltage_v: float
    channel_b_voltage_v: float
    channel_a_adc_v: float
    channel_b_adc_v: float
    channel_a_adc_counts: float
    channel_b_adc_counts: float
    channel_a_adc_range_v: float
    channel_b_adc_range_v: float


def parse_data_line(line: bytes | str) -> RawSample:
    """Parse ``DATA,time_ms,a_raw,b_raw,a_input_v,b_input_v``."""

    if isinstance(line, bytes):
        text = line.decode("ascii", errors="strict").strip()
    else:
        text = line.strip()
    fields = [field.strip() for field in text.split(",")]
    if len(fields) != 6 or fields[0] != "DATA":
        raise ProtocolError("Expected a six-field DATA record.")
    try:
        elapsed_ms = int(fields[1])
        numeric = tuple(float(field) for field in fields[2:])
    except (TypeError, ValueError) as exc:
        raise ProtocolError("DATA record contains a non-numeric field.") from exc
    if elapsed_ms < 0 or not all(math.isfinite(value) for value in numeric):
        raise ProtocolError("DATA record contains an invalid numeric value.")

    a_counts, b_counts, a_input_v, b_input_v = numeric
    if not -32768.0 <= a_counts <= 32767.0:
        raise ProtocolError("Channel A ADC count is outside the ADS1115 range.")
    if not -32768.0 <= b_counts <= 32767.0:
        raise ProtocolError("Channel B ADC count is outside the ADS1115 range.")
    input_limit = max(config.ADC_RANGE_VOLTS) * config.MAX_DIVIDER_MULTIPLIER * 1.01
    if abs(a_input_v) > input_limit or abs(b_input_v) > input_limit:
        raise ProtocolError("Input voltage is outside the supported divider range.")
    return RawSample(elapsed_ms, a_counts, b_counts, a_input_v, b_input_v)


def validate_adc_range(range_v: float) -> float:
    if not math.isfinite(range_v):
        raise ValueError("ADC range must be finite.")
    for supported in config.ADC_RANGE_VOLTS:
        if math.isclose(range_v, supported, rel_tol=0.0, abs_tol=0.000_5):
            return supported
    raise ValueError(f"Unsupported ADS1115 range: {range_v!r} V")


def convert_sample(
    raw: RawSample,
    calibration: Calibration,
    channel_a_adc_range_v: float = config.DEFAULT_ADC_RANGE_VOLTS,
    channel_b_adc_range_v: float = config.DEFAULT_ADC_RANGE_VOLTS,
) -> DataPoint:
    """Apply optional desktop corrections without repeating divider scaling."""

    range_a = validate_adc_range(channel_a_adc_range_v)
    range_b = validate_adc_range(channel_b_adc_range_v)
    return DataPoint(
        elapsed_ms=raw.elapsed_ms,
        channel_a_voltage_v=(
            raw.channel_a_input_v * calibration.channel_a_scale
            + calibration.channel_a_offset_v
        ),
        channel_b_voltage_v=(
            raw.channel_b_input_v * calibration.channel_b_scale
            + calibration.channel_b_offset_v
        ),
        channel_a_adc_v=raw.channel_a_adc_counts * range_a / 32768.0,
        channel_b_adc_v=raw.channel_b_adc_counts * range_b / 32768.0,
        channel_a_adc_counts=raw.channel_a_adc_counts,
        channel_b_adc_counts=raw.channel_b_adc_counts,
        channel_a_adc_range_v=range_a,
        channel_b_adc_range_v=range_b,
    )


class Dataset:
    """Thread-safe append-only measurement storage until explicitly cleared."""

    def __init__(self, max_points: int = config.MAX_STORED_POINTS) -> None:
        if max_points < 1:
            raise ValueError("max_points must be positive")
        self._max_points = max_points
        self._points: list[DataPoint] = []
        self._lock = threading.Lock()

    def append(self, point: DataPoint) -> None:
        with self._lock:
            if len(self._points) >= self._max_points:
                raise OverflowError(
                    f"The safety limit of {self._max_points:,} stored points was reached."
                )
            self._points.append(point)

    def clear(self) -> None:
        with self._lock:
            self._points.clear()

    def snapshot(self) -> tuple[DataPoint, ...]:
        with self._lock:
            return tuple(self._points)

    def __len__(self) -> int:
        with self._lock:
            return len(self._points)


class AcquisitionController:
    """Acquisition state shared by the GUI and tests."""

    def __init__(
        self,
        sender: Callable[[bytes], None],
        calibration: Calibration | None = None,
        dataset: Dataset | None = None,
    ) -> None:
        self._sender = sender
        self.calibration = calibration or Calibration()
        self.dataset = dataset if dataset is not None else Dataset()
        self.device_ready = False
        self.running = False
        self.malformed_lines = 0
        self.storage_full = False
        self.channel_a_adc_range_v = config.DEFAULT_ADC_RANGE_VOLTS
        self.channel_b_adc_range_v = config.DEFAULT_ADC_RANGE_VOLTS

    def mark_device_ready(self) -> None:
        self.device_ready = True

    def disconnect(self) -> None:
        self.device_ready = False
        self.running = False

    def set_adc_ranges(self, channel_a_range_v: float, channel_b_range_v: float) -> None:
        self.channel_a_adc_range_v = validate_adc_range(channel_a_range_v)
        self.channel_b_adc_range_v = validate_adc_range(channel_b_range_v)

    def start(self) -> None:
        if not self.device_ready:
            raise RuntimeError("A compatible Arduino is not connected.")
        self._sender(config.START_COMMAND)
        self.running = True

    def stop(self) -> None:
        was_ready = self.device_ready
        self.running = False
        if was_ready:
            self._sender(config.STOP_COMMAND)

    def ingest(self, line: bytes | str) -> DataPoint | None:
        if not self.running:
            return None
        try:
            point = convert_sample(
                parse_data_line(line),
                self.calibration,
                self.channel_a_adc_range_v,
                self.channel_b_adc_range_v,
            )
            self.dataset.append(point)
            return point
        except (ProtocolError, UnicodeError):
            self.malformed_lines += 1
            return None
        except OverflowError:
            self.storage_full = True
            self.running = False
            return None

    def confirm_and_clear(self, confirm: Callable[[], bool]) -> bool:
        if len(self.dataset) and not confirm():
            return False
        self.dataset.clear()
        self.storage_full = False
        return True


def downsample_for_display(
    points: Iterable[DataPoint], maximum: int = config.MAX_DISPLAY_POINTS
) -> tuple[list[float], list[float], list[float]]:
    materialized = tuple(points)
    if not materialized:
        return [], [], []
    stride = max(1, math.ceil(len(materialized) / maximum))
    selected = materialized[::stride]
    if selected[-1] is not materialized[-1]:
        selected += (materialized[-1],)
    return (
        [point.elapsed_ms / 1000.0 for point in selected],
        [point.channel_a_voltage_v for point in selected],
        [point.channel_b_voltage_v for point in selected],
    )
