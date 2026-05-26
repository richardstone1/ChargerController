# Witness MCU — ATtiny1616

Compact **witness** for dumb LXT packs: **full Makita OBI 1-Wire** (same command set as `obi.py` / `STM32OBI`) plus **local 5S cell** and **dual NTC** ADC. **EEPROM-backed pack profiles** let each board report a stable UUID and correct OBI identity/cell template for different pack types.

**Upstream OBI:** [Open Battery Information](https://github.com/mnh-jansson/open-battery-information) (Martin Jansson, MIT) — see repo [CREDITS.md](../../CREDITS.md).

## Scope

| Layer | How to update |
|-------|----------------|
| Witness **flash** (application code) | **UPDI** only (initial bring-up and firmware changes) |
| Witness **EEPROM profile** (UUID, ROM, model, mode, presets) | Pack **1-Wire** via `0x57` + `configure_witness.py --bus` |

Full firmware over 1-Wire is out of scope for now.

## Features (v0.3)

| Block | Status |
|-------|--------|
| OBI serial host (`0x01` framing @ 9600) | Optional debug UART |
| **1-Wire bus slave** (pack enable active) | Implemented |
| **1-Wire maintenance** (`0x57` + subcmd) | No UART required |
| OBI emulate on pack bus (`0x33` / `0xCC`) | Emulate mode |
| Makita 1-Wire timings (OneWire2/OBI) | Implemented |
| **Passthrough** (real BMS on 1-Wire) | Default |
| **Emulate** (stored ROM/model/msg + live ADC) | Implemented |
| EEPROM pack profile + CRC | 99 bytes @ address 0 |
| Host config subcmds `0xF0`–`0xF6` | UART or 1-Wire |
| `configure_witness.py --bus` | Via OBI reader → pack |
| 5× cell voltage dividers | ADC |
| 2× NTC | Beta equation, 10k bias |
| Status LED | In-range cells → ON |
| I2C telemetry to Pico/STM32 | Planned |

## Operating modes

| Mode | Value | Behaviour |
|------|-------|-----------|
| Passthrough | 0 | Forwards OBI to the pack 1-Wire bus (smart BMS packs). |
| Emulate | 1 | Answers `0x33` / `0xCC` from EEPROM profile; overlays **live cell + NTC ADC** on READ_DATA. Use for dumb cell-only packs. |

Built-in presets (from OBI captures):

| Preset | ID | Model |
|--------|----|-------|
| Blank | 0 | `WITNESS` — passthrough, UUID from chip serial |
| BL1850B | 1 | 5.0 Ah OEM reference |
| BL1830 | 2 | 3.0 Ah placeholder frame |

UUID bytes 0–2 are `WIT`; byte 3 distinguishes preset; bytes 4–15 come from the ATtiny **SIGROW** serial on factory reset / preset load.

## Build / flash

1. Install **PlatformIO** + **megaTinyCore** (via `atmelmegaavr` platform).
2. Flash **jtag2updi** to an **Arduino Mega** — [../jtag2updi/SETUP-ARDUINO-MEGA.md](../jtag2updi/SETUP-ARDUINO-MEGA.md).
3. Set `upload_port` in `platformio.ini` to the Mega COM port.
4. Wire **UPDI** (4.7k) to the 1616.
5. `pio run -t upload` from this directory.

## Host access

**Production (sealed pack):** use an OBI reader on the pack terminals (enable + 1-Wire). The witness listens as a **1-Wire slave** when enable is high. No UART breakout required.

**Bench debug:** optional UART on PA1/PA2 @ 9600 (same config subcmds `0xF0`–`0xF6`).

Use upstream `read_battery.py` on an OBI reader in emulate mode; it reports the programmed model/ROM with live voltages from the witness ADC.

### Program a profile over the pack bus (recommended)

Connect **STM32OBI** (or Arduino OBI) to the pack clips. Flash firmware that includes OBI cmd **`0x57`** (included in this repo’s `STM32OBI`).

```powershell
# Status over pack 1-Wire (charger/OBI reader enables the pack)
python configure_witness.py COM9 --bus --status

# Load BL1850B preset, emulate mode, save to EEPROM — no witness UART
python configure_witness.py COM9 --bus --preset bl1850b --mode emulate --save

# Import OEM capture JSON
python configure_witness.py COM9 --bus --import-json oem_20250519_reference.json --mode emulate --save
```

### Program via witness UART (bench only)

```powershell
python configure_witness.py COM8 --status
python configure_witness.py COM8 --preset bl1850b --mode emulate --save
```

### 1-Wire maintenance protocol

After a normal 1-Wire **reset** (with pack **enable** active):

| Byte | Meaning |
|------|---------|
| `0x57` | Witness maintenance primary opcode (`OW_WITNESS_CMD`) |
| `0xF0`–`0xF6` | Subcommand (same as table below) |
| `tx_len` | Payload length |
| `tx…` | Payload |
| ← `rsp…` | Fixed length per subcmd |

OBI USB tunnel (STM32 → pack): `01 <len> <rsp_len> 57 <subcmd> <tx_len> <tx…>`

In **emulate** mode the witness also answers normal Makita **`0x33`** / **`0xCC`** on the pack bus so `read_battery.py` works without UART.

### Config subcommands (`0xF0`–`0xF6`)

| Cmd | Name | Payload | Response |
|-----|------|---------|----------|
| `0xF0` | GET_STATUS | — | mode, preset, uuid[16] |
| `0xF1` | READ_PROFILE | — | 99-byte `PackProfile` |
| `0xF2` | WRITE_PROFILE | 99 bytes | status (0=ok) |
| `0xF3` | RESET_PROFILE | preset id | status |
| `0xF4` | SET_MODE | mode | mode |
| `0xF5` | SAVE_EEPROM | — | status |
| `0xF6` | LOAD_PRESET | preset id | preset |

## Pin map (VQFN-20)

| Signal | Pin | Notes |
|--------|-----|--------|
| UART TX / RX | PA1 / PA2 | OBI host |
| Enable | PA3 | Input — external OBI reader drives pack enable |
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
