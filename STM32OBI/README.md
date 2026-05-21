# STM32OBI — Blue Pill port of Open Battery Information

Firmware for **STM32F103C8** (“Blue Pill”) that speaks the same host serial protocol as upstream **ArduinoOBI**.

**Upstream / attribution:** Derived from [Open Battery Information](https://github.com/mnh-jansson/open-battery-information) (`ArduinoOBI/src/main.cpp`, **Copyright (c) 2024 Martin Jansson**, MIT License). See [CREDITS.md](../CREDITS.md) in this repository.

Host tools such as `read_battery.py` live in the upstream repo’s `OpenBatteryInformation/` tree; use them unchanged at **9600 baud** over USB CDC.

## Hardware

Use the same interface circuit as Arduino OBI (see upstream project docs). **GPIO is 3.3 V** on the Blue Pill — tie pull-ups to **3.3 V**, not 5 V.

### Default pins

| Signal   | Arduino Uno | STM32OBI default | MCU pin | Notes |
|----------|-------------|------------------|---------|--------|
| One-Wire | D6 (PD6)    | Arduino pin **26** | **PA6** | Move wire from Uno D6 to PA6 (often labeled A6). |
| Enable   | D8 (PB0)    | Arduino pin **28** | **PB0** | Same GPIO port bit as Uno D8 on the ATmega. |

Do **not** use abstract pins 6/8 on Blue Pill without changing config: D6=**PB3**, D8=**PA12** (USB D+). Defaults in `include/obi_config.h` avoid that.

If your harness is already on other GPIOs, edit `obi_config.h` or add `-DONEWIRE_PIN=…` / `-DENABLE_PIN=…` in `platformio.ini`.

### Serial to the PC (default: USB CDC)

The default build (`bluepill`) routes **`Serial` over the micro USB connector** (STM32 USB device / CDC), similar to plugging an Arduino Uno into one USB port.

| Use | Connection |
|-----|------------|
| **Host tools** (`read_battery.py`, etc.) | **Micro USB** on the Blue Pill → COM port in Windows |
| **Flash / debug** | **ST-Link** (SWD) — separate from the CDC data path |

After flashing, plug **micro USB** (data, not power-only cable), wait a few seconds for enumeration, then run Python on the new COM port.

**ST-Link alone does not provide this COM port** on typical V2 dongles; it only programs the chip.

#### Optional: USART on A9/A10

If you prefer a USB–UART dongle instead of micro USB serial, build `bluepill_usart` and wire:

| Adapter | Blue Pill |
|---------|-----------|
| TX      | **A10** (MCU RX) |
| RX      | **A9** (MCU TX) |
| GND     | GND |

## Build

Requires [PlatformIO](https://platformio.org/) (CLI or VS Code extension).

```bash
cd STM32OBI
pio run
```

Default environment: **`bluepill`** (USB CDC).

USART-only variant:

```bash
pio run -e bluepill_usart
```

## Flash

### ST-Link (recommended)

```bash
pio run -t upload
```

Set `upload_port` in `platformio.ini` if needed.

### Serial bootloader (STM32 ROM UART)

1. Set BOOT0 high, reset, then `pio run -e bluepill_serial -t upload`
2. ROM UART is often **A9/A10** — not the USB CDC port.

## Test with Python

1. Flash firmware (`pio run -t upload` via ST-Link).
2. Connect **micro USB** to the PC (CDC). Confirm a new **USB Serial Device (COMx)** in Device Manager — not “Unknown USB Device”.
3. From upstream [open-battery-information](https://github.com/mnh-jansson/open-battery-information) `OpenBatteryInformation/`:

```bash
python read_battery.py COMx
python battery_capture.py --port COMx --label stm32-test
```

Version query should report firmware **0.3.0**. Command framing matches Arduino OBI:

| Byte 0 | Byte 1 | Byte 2     | Byte 3 | …        |
|--------|--------|------------|--------|----------|
| `0x01` | `len`  | `rsp_len`  | `cmd`  | payload  |

Response: `[cmd][rsp_len][payload…]`.

Battery commands may fail with no pack attached; the version line still proves the link works.

## Timing notes

- CPU runs at **72 MHz**; 1-Wire bit timing uses the same **microsecond delays** as Arduino OBI (modified OneWire2: longer reset/slot times for Makita packs).
- Critical sections disable interrupts during bit I/O (same as AVR). USB IRQ load is usually fine; if reads are flaky, shorten USB cables and avoid hub noise.

## Differences from ArduinoOBI

| Item        | ArduinoOBI | STM32OBI   |
|-------------|------------|------------|
| Version     | 0.2.1      | 0.3.0      |
| I/O voltage | 5 V        | 3.3 V      |
| Host link   | Uno 16U2 USB–serial | STM32 **USB CDC** (default) or USART1 (`bluepill_usart`) |
| OneWire lib | vendored   | same copy  |
| Protocol    | identical  | identical  |

## Project layout

```
STM32OBI/
  platformio.ini
  include/obi_config.h
  src/main.cpp
  lib/OneWire/          # OneWire2 (OBI-tuned timings)
```
