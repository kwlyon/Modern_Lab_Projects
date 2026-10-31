# SerialPlotter

SerialPlotter is a Python/Tkinter real-time serial plotting tool for the Modern Lab data acquisition hardware. The current application connects to an Arduino-based shield over a serial port, waits for the `Modern Lab Data Acquisition Shield` handshake banner, and plots incoming measurements live with Matplotlib.

This repository contains the Python plotting application, PyInstaller build specifications, Eagle CAD files for the Arduino shield, CAM/manufacturing outputs, and Arduino Uno sketches used with the shield.

## Current Contents

- `recorder4.py` - current StreamPlot application entry point.
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

As the project settles, this section can be expanded with notes about board revisions, firmware versions, expected serial output format, and lab setup details.
