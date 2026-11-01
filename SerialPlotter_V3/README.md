# Serial Plotter V3

Serial Plotter V3 is a general-purpose, two-channel voltage strip recorder for
the **current differential Modern Lab shield** used by the Franck–Hertz project.
It plots both signed input voltages over time, with independent display axes and
ADS1115 ranges. It does not apply Franck–Hertz current or X–Y calculations.

## Hardware and firmware

Use the **same Arduino Uno and shield, with the same firmware**, as the current
Franck–Hertz setup. The one maintained sketch is
[`../Frank_Herz/arduino/Frank_Herz_DAQ/Frank_Herz_DAQ.ino`](../Frank_Herz/arduino/Frank_Herz_DAQ/Frank_Herz_DAQ.ino).
V3 deliberately has no second sketch copy. Flash that file when setting up the
board; **do not flash V2's `Uno_Sketch.ino`**, which uses older single-ended
ADC readings. Both sketches announce protocol version 4, so the desktop app
cannot distinguish them from the handshake alone.

The current shield's [Eagle schematic and board](hardware/README.md) are kept
under `hardware/Eagle_Cad/`. Their top silkscreen has circled A and B labels;
the older files with the same Eagle names and a large trimmer remain archived
in `SerialPlotter/Arduino Shield for Aquisition/Eagle_Cad/`.

| Plotter input | Shield connector | ADS1115 measurement | Factory divider |
| --- | --- | --- | --- |
| Channel A | J1 | AIN0 − AIN1 | 909 kΩ high, 101 kΩ low |
| Channel B | J3 | AIN2 − AIN3 | 909 kΩ high, 101 kΩ low |

The ADS1115 is at I2C address `0x49`. It multiplexes the two pairs, so A and B
are sampled in sequence, not simultaneously. The firmware applies each
channel's EEPROM-backed resistor divider and independently autoranges the ADC.
Each ADC pin must remain between ground and the ADC supply voltage even when the
difference is negative. Use the shield's intended monitor inputs and suitable
dividers; do not connect a high-voltage source directly to an ADC pin. See the
[Franck–Hertz hardware notes](../Frank_Herz/README.md#hardware-architecture)
for the full electrical description.

## Arduino averaging

The **Averages / point** control selects 1–64 A/B conversion pairs for each
plotted row. Choose a number and select **Apply on Arduino**; the label changes
to *confirmed* when the Arduino replies `OK,avg,N`. The selection is also sent
automatically after every connection or Arduino reset. V3 initially selects 10;
the sketch itself defaults to 1 after power-up.

The Arduino averages the signed raw ADC counts for each channel **before** it
sends a row. V3 does not average the received rows again. The firmware uses the
largest absolute conversion in each group for autoranging, so an averaged value
cannot hide a near-clipping conversion. More conversions reduce random noise
but also reduce the maximum row rate. The confirmed pair count is stored with
each data point and exported in the workbook, even if you change it during a
recording.

The firmware uses 115200 baud and reports:

```text
Modern Lab Dual-Channel Data Acquisition
#protocol,modern-lab-dual-channel,4
DATA,time_ms,channel_a_raw,channel_b_raw,channel_a_input_v,channel_b_input_v
```

The last two fields are connector voltages after firmware divider correction.
Raw fields are averaged signed ADS1115 counts. V3 sends `avg,N` for averaging,
`delay,50` for the nominal record interval, and `run` / `stop` for acquisition.
Actual row timing can be longer than 50 ms when many conversion pairs are used.

## Run and use

From this folder, install Python 3 dependencies and run:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Choose the Arduino COM port, select **Connect**, then **Start Acquisition**.
You can instead choose **SIMULATOR (no hardware)** to explore the interface; it
generates signed signals and responds to the same averaging command. The
simulator is useful for software checks but does not verify the physical shield
or uploaded firmware.

Channel A and B checkboxes control display and Excel export; the Arduino still
measures both channels. When both are shown, A uses the left axis and B the
right. With one channel shown, that channel uses the left axis. **Auto-scale
live** changes only the plot view. **ADC Autorange** changes the converter's
electrical range; when disabled, you can select A and B ranges separately.
Stopping acquisition retains collected data until **Clear Data** is confirmed.

**Invert A** and **Invert B** independently reverse the displayed connector
voltage polarity. Both start unchecked. Excel exports use the polarity selected
at export time and record those selections in the Calibration sheet. Raw ADC
counts and ADC-node voltages remain unmodified.

Exports include signed connector voltages, raw counts, ADC-node voltages,
active ADC ranges, and the Arduino averaging count for every row. The optional
desktop scale/offset correction defaults to 1.0/0.0; the firmware has already
applied the shield's resistor-divider scaling.

## Checks and Windows build

```powershell
python -m unittest discover -s tests -v
python app.py --smoke-test
python app.py --gui-smoke-test
```

The shared Uno sketch can be compiled from the `Frank_Herz` folder with:

```powershell
arduino-cli compile --fqbn arduino:avr:uno arduino/Frank_Herz_DAQ
```

To package the desktop app, install `requirements-dev.txt` and run:

```powershell
python -m PyInstaller --noconfirm SerialPlotter_V3.spec
```

The distributable app is `dist/SerialPlotter_V3/SerialPlotter_V3.exe` together
with its `_internal` folder.
