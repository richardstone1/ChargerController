# Witness MCU — ATtiny1616

Compact **witness** for dumb LXT packs: **full Makita OBI 1-Wire** (same command set as `obi.py` / `STM32OBI`) plus **local 5S cell** and **dual NTC** ADC.

**Upstream OBI:** [Open Battery Information](https://github.com/mnh-jansson/open-battery-information) (Martin Jansson, MIT) — see repo [CREDITS.md](../../CREDITS.md).

## Features (v0.1)

| Block | Status |
|-------|--------|
| OBI serial host (`0x01` framing @ 9600) | Implemented (`obi_host.cpp`) |
| Makita 1-Wire timings (OneWire2/OBI) | Implemented (`makita_onewire.cpp`) |
| 5× cell voltage dividers | ADC + config constants |
| 2× NTC | Beta equation, 10k bias |
| Status LED | In-range cells → ON |
| I2C telemetry to Pico/STM32 | Planned (test pads on PCB) |

## Build / flash

1. Install **PlatformIO** + **megaTinyCore** (via `atmelmegaavr` platform).
2. Flash **jtag2updi** to an **Arduino Mega** — [../jtag2updi/SETUP-ARDUINO-MEGA.md](../jtag2updi/SETUP-ARDUINO-MEGA.md).
3. Set `upload_port` in `platformio.ini` to the Mega COM port.
4. Wire **UPDI** (4.7k) to the 1616; **BOOT0** not applicable on tiny.
5. `pio run -t upload` from this directory.

## Host serial (OBI)

Connect **PA1 (TX)** / **PA2 (RX)** @ **9600** to your host (STM32 CDC, USB-UART, etc.). Use upstream `read_battery.py` unchanged once wired.

## Pin map (VQFN-20)

| Signal | Pin | Notes |
|--------|-----|--------|
| UART TX / RX | PA1 / PA2 | OBI host |
| Enable | PA3 | Pack interface |
| 1-Wire | PA4 | 4.7k pull-up |
| Cell 1–5 | PA5–PA7, PB0–PB1 | Divider sense |
| NTC 1–2 | PB2–PB3 | |
| LED OK | PB4 | Active low |
| UPDI | PA0 | Program only |

## PCB

Mechanical and BOM: [pcb/DESIGN.md](pcb/DESIGN.md) — target **22×8 mm**, passives on bottom.

## Next steps

- [ ] I2C register map for local ADC (parallel to OBI)
- [ ] Sleep / watchdog between host polls
- [ ] KiCad layout from `pcb/DESIGN.md`
