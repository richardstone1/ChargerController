# Credits and upstream work

This project is **open source** and welcomes collaboration (see `CONTRIBUTING.md`).

## Open Battery Information (OBI) — `obi.py`

The Makita LXT **1-Wire** framing, enable timing, and USB-style command handling in `obi.py` are **derived from** the **ArduinoOBI** reference implementation in:

- **Open Battery Information**  
  - Repository: [github.com/mnh-jansson/open-battery-information](https://github.com/mnh-jansson/open-battery-information)  
  - Original Arduino firmware path: `ArduinoOBI/src/main.cpp`  
  - **Copyright (c) 2024 Martin Jansson** — used under the **MIT License** (see upstream `LICENSE.md` in that repository).

Please cite that project when publishing work based on the OBI protocol layer.

## Open Battery Information (OBI) — `STM32OBI/`

The **STM32F103 “Blue Pill”** firmware in `STM32OBI/` is a **PlatformIO port** of the same ArduinoOBI command set and Makita 1-Wire sequences:

- **Upstream:** [github.com/mnh-jansson/open-battery-information](https://github.com/mnh-jansson/open-battery-information) — `ArduinoOBI/src/main.cpp`, OneWire2 timings, host framing at 9600 baud  
- **Copyright (c) 2024 Martin Jansson** — MIT License (upstream `LICENSE.md`)  
- **This port:** Richard Stone — USB CDC on micro USB, default pins PA6 (1-Wire) / PB0 (enable), 3.3 V I/O  

Vendored `STM32OBI/lib/OneWire/` matches the OBI-modified OneWire2 library from that upstream tree.

## Open Battery Information (OBI) — `tools/attiny1616-witness/`

**ATtiny1616** witness firmware (Makita 1-Wire + local ADC) in `tools/attiny1616-witness/`:

- **Upstream:** same ArduinoOBI command sequences and OneWire2-style timings  
- **Copyright (c) 2024 Martin Jansson** — MIT License  
- **This port:** Richard Stone — witness MCU for dumb packs, 5S + dual NTC, 22×8 mm PCB spec in `tools/attiny1616-witness/pcb/DESIGN.md`

## MicroPython / Raspberry Pi

Firmware targets **MicroPython** on the **Raspberry Pi Pico W**. Thanks to the MicroPython and Raspberry Pi communities for documentation and tooling.

## How to add yourself

If you contribute meaningfully to this repository, add your name (or GitHub handle) to `CONTRIBUTORS.md` in a pull request, or ask a maintainer to add you.
