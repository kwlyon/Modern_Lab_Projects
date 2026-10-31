# SerialPlotter

SerialPlotter is the original Python/Tkinter real-time serial plotting tool for earlier Modern Lab data acquisition hardware. Its `recorder4.py` application connects to an Arduino-based shield over a serial port, waits for the `Modern Lab Data Acquisition Shield` handshake banner, and plots incoming measurements live with Matplotlib. For the current differential shield and Frank–Herz Arduino sketch, use [Serial Plotter V3](../SerialPlotter_V3/README.md).

This repository contains the Python plotting application, PyInstaller build specifications, Eagle CAD files for the Arduino shield, CAM/manufacturing outputs, and Arduino Uno sketches used with the shield.

## Contents

- `recorder4.py` - latest StreamPlot entry point in this legacy folder.
- `StreamPlot.spec` - PyInstaller spec for building the StreamPlot executable.
- `recorder.py`, `recorder2.py`, `recorder3.py` - earlier development versions kept for reference.
- `recorder.spec` - earlier PyInstaller spec.
- `Arduino Shield for Aquisition/Eagle_Cad/` - Eagle board, schematic, library, and CAM output files for the shield.
- `Arduino Shield for Aquisition/Uno_Sketches/` - Arduino sketches for the shield firmware and test programs.

Generated build folders such as `build/` and `dist/` are intentionally ignored by git.

## Requirements

The Python application uses:

- Python 3
- NumPy
- PySerial
- Matplotlib
- Tkinter, included with most standard Python installs on Windows

Install the Python package dependencies with:

```powershell
python -m pip install numpy pyserial matplotlib
```

## Running From Source

Connect the Modern Lab data acquisition shield, then run:

```powershell
python recorder4.py
```

The app uses a fixed baud rate of `115200` and expects the shield to send the handshake banner:

```text
Modern Lab Data Acquisition Shield
```

After the handshake is received, the app applies its default gain and averaging settings.

## Building The Windows Executable

If PyInstaller is installed, build the StreamPlot executable with:

```powershell
python -m PyInstaller --noconfirm StreamPlot.spec
```

The generated executable will be written under `dist/`, which is ignored by git.

## Hardware Files

The shield design files currently live under:

```text
Arduino Shield for Aquisition/
  Eagle_Cad/
  Uno_Sketches/
```

These files document earlier shield revisions. For the current differential
AIN0−AIN1 and AIN2−AIN3 shield and its `Frank_Herz_DAQ.ino` firmware, follow the
Serial Plotter V3 hardware instructions.
