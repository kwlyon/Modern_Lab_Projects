# Modern Lab Projects

This repository collects four laboratory data-acquisition projects. The active
differential Arduino firmware is maintained in `Frank_Herz` and also used by
`SerialPlotter_V3`.

| Project | Contents |
| --- | --- |
| [Frank_Herz](Frank_Herz/README.md) | Franck–Hertz acquisition software and differential Arduino shield firmware |
| [SerialPlotter](SerialPlotter/README.md) | Original serial plotter and earlier shield designs |
| [SerialPlotter_V2](SerialPlotter_V2/README.md) | Two-channel recorder with the older single-ended Arduino sketch |
| [SerialPlotter_V3](SerialPlotter_V3/README.md) | General recorder for the current differential shield and Arduino averaging |

The three original projects were imported with unsquashed Git subtree merges.
Their commits remain in this repository's history. Frank_Herz release tags are retained
under `Frank_Herz/v...` names so they remain distinct from future tags for other
projects.

See each project's README for build, calibration, and hardware instructions.
For the current differential shield, use the
[Frank–Herz sketch](Frank_Herz/arduino/Frank_Herz_DAQ/Frank_Herz_DAQ.ino)
with either the Frank–Herz app or Serial Plotter V3.
Frank–Hertz Windows downloads and firmware attachments are available on the
[releases page](https://github.com/kwlyon/Modern_Lab_Projects/releases).
