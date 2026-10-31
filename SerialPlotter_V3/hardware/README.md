# Current differential Arduino shield

[`Eagle_Cad/AquisitionBoardV3.sch`](Eagle_Cad/AquisitionBoardV3.sch) and
[`Eagle_Cad/AquisitionBoardV3.brd`](Eagle_Cad/AquisitionBoardV3.brd) are the
schematic and board for the current Modern Lab shield. They were copied from
the Modern Lab **Atomic and Molecular / Arduino Shield for Aquisition** Eagle
project. Their original Eagle filenames are retained.

The board's top silkscreen has circled **A** and **B** labels. Unlike the older
files with the same names in
[`../../SerialPlotter/Arduino Shield for Aquisition/Eagle_Cad/`](../../SerialPlotter/Arduino%20Shield%20for%20Aquisition/Eagle_Cad/),
this board has no 15-turn Bourns 3006P trimmer. The older Eagle designs stay
there for reference. Eagle may retain unused library definitions in the files;
the placed board elements are the check for whether a part is fitted.

The schematic routes Channel A through J1 and the 909 kΩ / 101 kΩ divider to
ADS1115 AIN0−AIN1. Channel B uses J3 and the corresponding divider on
AIN2−AIN3. A 10 kΩ resistor pulls the ADC's ADDR pin to +5 V for I2C address
`0x49` when solder jumper SJ1 is open. This matches the maintained
[`Frank_Herz_DAQ.ino`](../../Frank_Herz/arduino/Frank_Herz_DAQ/Frank_Herz_DAQ.ino)
firmware used by both Franck–Hertz and Serial Plotter V3.

The files were checked for matching placed parts and schematic pin connections.
Physical electrical verification and an Eagle ERC/DRC run are still needed
before fabrication or hardware changes.
