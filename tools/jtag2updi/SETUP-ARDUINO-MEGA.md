# jtag2updi on Arduino Mega (ATtiny1616 witness MCU)

Turn an **Arduino Mega 2560** into a **UPDI programmer** for modern AVRs (including **ATtiny1616**) using [ElTangas/jtag2updi](https://github.com/ElTangas/jtag2updi) (MIT license).

> **Note:** megaTinyCore now recommends **SerialUPDI** (USB-serial + resistor) over jtag2updi for speed and reliability. jtag2updi still works well if you already have a Mega on the bench.

## 1. Flash the programmer firmware (Mega)

### Arduino IDE

1. Install **Arduino IDE** (1.8.x or 2.x).
2. Open sketch folder: **`arduino-mega-sketch/jtag2updi/jtag2updi.ino`**
3. **Tools → Board → Arduino Mega or Mega 2560**
4. **Tools → Processor → ATmega2560** (if shown)
5. Select your Mega’s **COM port**.
6. **Sketch → Upload**.

After upload, **disable auto-reset** on the Mega so avrdude doesn’t reset the programmer mid-session:

- Put a **10 µF** cap between **RESET** and **GND**, or  
- See [DisablingAutoResetOnSerialConnection](https://playground.arduino.cc/Main/DisablingAutoResetOnSerialConnection)

Leave the Mega powered from USB; note the **COM port** (e.g. `COM5`).

### Pin used on Mega (default)

| Mega signal | Pin | Connect to target |
|-------------|-----|-------------------|
| **UPDI (PD3)** | **Digital 18** | via **4.7 kΩ** → **UPDI** on ATtiny1616 |
| **GND** | GND | GND |
| **VCC** | 5V or 3.3V | **Same voltage** as ATtiny1616 run/flash |

Do **not** reverse power: programmer and target should share ground; target VCC must be ≥ ~60% of programmer logic high level.

## 2. Wire ATtiny1616 (20-pin SOIC/DIP)

Typical **ATtiny1616** (check your package pinout):

| ATtiny1616 | Use |
|------------|-----|
| **PA0 / pin 12 (UPDI)** | UPDI data (through **4.7 kΩ** from Mega **D18**) |
| **VDD** | 3.3 V or 5 V (match Mega I/O rail) |
| **GND** | Common with Mega |

Optional: **0.1 µF** on VDD/GND at the tiny.

## 3. Target firmware tooling (ATtiny1616)

### Arduino IDE + megaTinyCore

1. **Boards Manager:** install **megaTinyCore** (Spence Konde).
2. **Tools → Board → ATtiny1616 (or 1616/1617 series)**
3. **Tools → Programmer → jtag2updi**
4. **Tools → Port →** Mega’s COM port (the programmer, not a separate USB-UART on the tiny).
5. **Sketch → Upload Using Programmer** (Ctrl+Shift+U).

### avrdude (command line)

Use a recent **avrdude** with **jtag2updi** support (Arduino 2.x / megaTinyCore install includes one). Example:

```powershell
avrdude -c jtag2updi -P COM5 -b 115200 -p t1616 -U flash:r:readback.hex:i
```

Read signature only:

```powershell
avrdude -c jtag2updi -P COM5 -b 115200 -p t1616
```

Part id for **ATtiny1616** is **`t1616`** (see `avrdude.conf` in this repo).

If the chip is **UPDI-locked**, you may need `-F` or a **chip erase** / **12 V UPDI** unlock flow (not covered here).

## 4. Witness MCU project (your next step)

Suggested layout for a dumb-pack telemetry node:

- **ATtiny1616** — ADC/GPIO for pack sense lines, I²C/UART to a host, low sleep current.
- Program/refresh via this **Mega + jtag2updi** setup until you move to **SerialUPDI** or a dedicated SNAP/ICE.

Keep OBI / Makita 1-Wire on your STM32/Pico witness path; use the **1616** for analog front-end or glue logic on simpler packs.

## Repo layout

| Path | Purpose |
|------|---------|
| `arduino-mega-sketch/jtag2updi/` | **Open this `.ino` in Arduino IDE** (Mega) |
| `source/` | Upstream source (same files) |
| `avrdude.conf` | Reference part defs (`t1616`, etc.) |
| `build/JTAG2UPDI.hex` | Prebuilt for **ATmega328P only** — **rebuild or use IDE for Mega** |

## Upstream / license

- **Firmware:** [ElTangas/jtag2updi](https://github.com/ElTangas/jtag2updi) (MIT)
- **megaTinyCore / SerialUPDI:** [SpenceKonde/megaTinyCore](https://github.com/SpenceKonde/megaTinyCore)

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `RSP_ILLEGAL_MCU_STATE` | UPDI locked; wiring; wrong part `-p` |
| No response | D18 ↔ UPDI, **4.7 kΩ**, common GND, same VCC |
| Port vanishes on connect | Mega **auto-reset** — add cap on RESET |
| `t1616` unknown | Use avrdude from megaTinyCore / Arduino 2.x |
