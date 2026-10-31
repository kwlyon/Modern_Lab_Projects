"""Excel export for selected Serial Plotter V3 channels."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .core import Calibration, DataPoint


def data_headers(include_channel_a: bool, include_channel_b: bool) -> tuple[str, ...]:
    if not include_channel_a and not include_channel_b:
        raise ValueError("At least one channel must be selected for export.")
    headers = ["Elapsed Time (ms)", "Arduino Averages (pairs/row)"]
    if include_channel_a:
        headers.extend(
            (
                "Channel A Voltage (V)",
                "Channel A ADC Voltage (V)",
                "Channel A Raw (counts)",
                "Channel A ADC Range (±V)",
            )
        )
    if include_channel_b:
        headers.extend(
            (
                "Channel B Voltage (V)",
                "Channel B ADC Voltage (V)",
                "Channel B Raw (counts)",
                "Channel B ADC Range (±V)",
            )
        )
    return tuple(headers)


def export_xlsx(
    path: str | Path,
    points: Iterable[DataPoint],
    calibration: Calibration,
    include_channel_a: bool = True,
    include_channel_b: bool = True,
) -> int:
    """Export the complete timebase and only the currently selected channels."""

    headers = data_headers(include_channel_a, include_channel_b)
    rows = tuple(points)
    destination = Path(path)
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Serial Data"
    sheet.append(headers)
    for point in rows:
        row: list[float | int] = [point.elapsed_ms, point.average_count]
        if include_channel_a:
            row.extend(
                (
                    point.channel_a_voltage_v,
                    point.channel_a_adc_v,
                    point.channel_a_adc_counts,
                    point.channel_a_adc_range_v,
                )
            )
        if include_channel_b:
            row.extend(
                (
                    point.channel_b_voltage_v,
                    point.channel_b_adc_v,
                    point.channel_b_adc_counts,
                    point.channel_b_adc_range_v,
                )
            )
        sheet.append(row)

    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
    sheet.freeze_panes = "A2"
    final_column = get_column_letter(len(headers))
    sheet.auto_filter.ref = f"A1:{final_column}{max(1, len(rows) + 1)}"
    for index, header in enumerate(headers, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = max(19, len(header) + 2)

    metadata = workbook.create_sheet("Calibration")
    metadata.append(("Setting", "Value", "Meaning"))
    for row in (
        ("Channel A scale", calibration.channel_a_scale, "V corrected per V reported"),
        ("Channel A offset", calibration.channel_a_offset_v, "V"),
        ("Channel B scale", calibration.channel_b_scale, "V corrected per V reported"),
        ("Channel B offset", calibration.channel_b_offset_v, "V"),
        ("Hardware scaling", "Applied by firmware", "EEPROM divider configuration"),
        ("Averaging", "Applied by firmware", "Pairs per row are recorded in Serial Data"),
    ):
        metadata.append(row)
    for cell in metadata[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
    metadata.freeze_panes = "A2"
    metadata.column_dimensions["A"].width = 25
    metadata.column_dimensions["B"].width = 20
    metadata.column_dimensions["C"].width = 32
    workbook.save(destination)
    return len(rows)
