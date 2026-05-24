# Witness module PCB — 22 × 8 mm

Target: stick-on **witness** for dumb 5S LXT-style packs — **ATtiny1616** + dividers + NTC + optional power.

## Board outline

| Parameter | Value |
|-----------|--------|
| Size | **22 mm × 8 mm** (max) |
| Layers | 2 (Top + Bottom), **1.0 mm** FR4 suggested |
| MCU | **ATtiny1616-MNR** (VQFN-20, **3×3 mm**, 0.4 mm pitch) — **top** |

## Layer assignment

### Top (components)

```
     22 mm ──────────────────────────────────────►
  ┌──────────────────────────────────────────────┐  ▲
  │  [C1 100n]                    [LED1 0402]   │  │
  │       ┌─────────────┐                        │  8 mm
  │       │ ATtiny1616  │  [TP UPDI]             │  │
  │       │   VQFN-20   │                        │  │
  │  [C2 100n]          [Rpull 4k7 to VDD]       │  │
  └──────────────────────────────────────────────┘  ▼
     ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○ ○   ← edge contact pads (see below)
```

### Bottom (0402 passives)

- **10×** divider resistors: 5× **470k** (top) + 5× **100k** (bottom to GND) — place **directly under** each cell sense pad.
- **2×** NTC bias **10k** to VDD at divider junction.
- **100n** VDD decoupling at each corner of MCU (C1/C2).
- Optional **power** block (one of below).

## Edge contact pads (top or edge — 1.0 × 1.5 mm)

| Pad | Function |
|-----|----------|
| C1 | Cell 1 tap (via divider → PA5) |
| C2 | Cell 2 → PA6 |
| C3 | Cell 3 → PA7 |
| C4 | Cell 4 → PB0 |
| C5 | Cell 5 → PB1 |
| T1 | NTC1 (to PB2) |
| T2 | NTC2 (to PB3) |
| OW | 1-Wire to pack (PA4 + 4.7k to VDD) |
| EN | Enable out (PA3) |
| TX | Host serial TX (PA1) |
| RX | Host serial RX (PA2) |
| VIN | Power input (see power options) |
| GND | Common ground |

Place pads along the **long (22 mm) edge** for harness soldering or spring contacts.

## Cell divider (per cell)

```
Cell+ ── 470k (Rtop, bottom) ──┬── to MCU ADC pin
                               │
                              100k (Rbot, bottom) ── GND
```

At **V_cell = 4.35 V**, **V_adc ≈ 0.76 V** with VDD = 3.3 V ref — good margin.

Use **0402** resistors; keep **Kelvin** sense: ADC trace from **top resistor / bottom junction**, not from pad.

## NTC (10k @ 25°C, e.g. NCP15XH103)

```
VDD ── 10k ──┬── PB2 or PB3
             │
            NTC ── GND
```

## Power options (pick one — mutually exclusive BOM)

| Option | When | Parts (bottom unless noted) |
|--------|------|-----------------------------|
| **A — Host 3.3 V** | STM32/Pico provides regulated 3.3 V on **VIN** pad | None (100n only) |
| **B — LDO** | 5 V from charger board | **SOT-23-5** `MCP1700T-3302E/` or `AP2112K-3.3` + 1µ + 100n |
| **C — Buck** | 12–18 V pack / tool rail, no 3.3 V available | **SOT-563** `TPS562200` or `MP2359` + 2.2µH 0805 + feedback dividers |

**Option C** is tight in 22×8 mm — consider **Option A or B** first; buck may need **23×9 mm** or second rev.

If input can exceed **5.5 V**, **never** tie VIN to MCU VDD without LDO/buck.

## Programming

- **UPDI** on **PA0**: test pad **0.8 mm** + 4.7k to VDD (series as per Microchip).
- Program with [jtag2updi on Mega](../jtag2updi/SETUP-ARDUINO-MEGA.md).

## LEDs

| LED | Color | Pin | Meaning |
|-----|-------|-----|---------|
| LED1 | Green | PB4 | All cells 2.5–4.35 V |

Optional **LED2** (yellow, **DNP**): 1-Wire activity — add on rev B if space.

## Routing notes

1. **Star ground** at MCU GND pad; short return for dividers.
2. Keep **1-Wire (PA4)** away from switching buck noise; guard with GND if buck fitted.
3. **UPDI** away from cell pads (high voltage during pack connect).
4. Bottom resistors: stagger so rework iron fits; avoid overlapping MCU thermal pad if exposed pad used.

## KiCad next step

1. New project `witness-22x8.kicad_pro`.
2. Import **ATtiny1616-MNR** from **microchip-avrlibrary** or draw 20-VQFN 3×3.
3. Place MCU at **(11 mm, 4 mm)**; route on **0.15 mm** / **0.2 mm** tracks.
4. Generate **Gerber** with board outline **22×8** in `Edge.Cuts`.

## BOM summary (core, excl. power option)

| Qty | Value | Package | Notes |
|-----|-------|---------|--------|
| 1 | ATtiny1616-MNR | VQFN-20 3×3 | |
| 5 | 470k | 0402 | Divider top |
| 5 | 100k | 0402 | Divider bottom |
| 2 | 10k | 0402 | NTC bias |
| 1 | 4.7k | 0402 | 1-Wire pull-up |
| 2 | 100n | 0402 | VDD decouple |
| 1 | LED green | 0402 | + 1k limiter |
| 2 | 10k NTC | 0402 or wire | External on pack |

## Firmware pin match

Pins match `include/witness_config.h` in this directory.
