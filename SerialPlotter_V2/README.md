# Serial Plotter V2

Serial Plotter V2 is a general-purpose two-channel voltage strip recorder for
an earlier Modern Lab Arduino acquisition shield setup. Its bundled protocol-v4
Uno sketch reads ADS1115 **single-ended AIN0 and AIN2** inputs, with EEPROM
resistor-divider calibration and independent ADC autoranging. It has no
experiment-specific X–Y plot or current calibration. For the current
**differential** Franck–Hertz shield and sketch, use
[Serial Plotter V3](../SerialPlotter_V3/README.md).

## Project layout

```text
SerialPlotter_V2/
├── Arduino Shield for Aquisition/
│   └── Uno_Sketch/
│       └── Uno_Sketch.ino
├── serial_plotter_v2/
├── tests/
├── app.py
├── SerialPlotter_V2.spec
└── README.md
```

The folder name `Arduino Shield for Aquisition` is retained from the original
project. `Uno_Sketch.ino` is the older single-ended firmware; it is **not** a
copy of the current differential `Frank_Herz_DAQ.ino`. Both announce protocol
version 4, so the handshake alone does not prove which input mode is uploaded.

## Running the application

```powershell
python -m pip install -r requirements.txt
python app.py
```

Choose the Arduino COM port or **SIMULATOR (no hardware)**, connect, and start
acquisition. Data is retained when acquisition is stopped and is removed only
after a confirmed Clear Data operation.

## Channel selection and axes

The **Channel A** and **Channel B** checkboxes change the live display and which
channels are included in an Excel export. The firmware continues sampling both
inputs so their independent electrical autoranging remains protected even when
one trace is hidden.

Axis assignment is always:

```text
Channel A only  → Channel A on the left axis
Channel B only  → Channel B on the left axis
Both channels   → Channel A left, Channel B right
```

The trace, label, tick color, and right-axis visibility update immediately when
the selection changes. The application prevents both channels from being
disabled simultaneously.

## Autoscale, autorange, and calibration

**Auto-scale live** changes only the plotted axes. Home restores live plot
fitting after Pan or Zoom.

**ADC Autorange** changes the ADS1115 electrical full-scale ranges. The Uno makes
the autoranging decisions independently for AIN0 and AIN2 and reports changes as
human-readable `#range,A=...,B=...` lines. With autoranging enabled, the two GUI
range selectors display the reported active settings and cannot be edited. With
it disabled, each range can be selected manually.

The Uno converts each row as:

```text
ADC counts → ADC-node voltage using that row's active range
           → connector voltage using the channel's EEPROM divider values
```

Serial Plotter V2 therefore receives actual calibrated connector voltages. Its
optional desktop scale/offset corrections default to 1.0 and 0.0, so it does not
repeat the hardware divider correction. Exports include the selected connector
voltages, ADC-node voltages, raw counts, active ranges, and correction metadata.

## Firmware commands

The copied firmware supports `run`, `stop`, `avg,N`, `delay,N`, `autorange?`,
`autorange,0|1`, `range?`, `range,A|B|both,V`, `dividers?`, the four resistor
configuration commands, and `defaults`. See comments in `Uno_Sketch.ino` and the
serial responses for validation details.

## Tests and build

```powershell
python -m unittest discover -s tests -v
python app.py --smoke-test
python app.py --gui-smoke-test
```

Compile the firmware for an Arduino Uno:

```powershell
arduino-cli compile --fqbn arduino:avr:uno "Arduino Shield for Aquisition/Uno_Sketch"
```

Build the Windows application:

```powershell
python -m PyInstaller --noconfirm SerialPlotter_V2.spec
```

The packaged executable and its required `_internal` directory are produced at:

```text
dist/SerialPlotter_V2/SerialPlotter_V2.exe
```

Launch the executable from the `dist` folder; the similarly named file under
`build` is an intermediate PyInstaller artifact and is not the distributable app.
