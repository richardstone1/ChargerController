#!/usr/bin/env python3
"""Configure ATtiny1616 witness pack profile (UART or pack 1-Wire via OBI reader)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    print("pip install pyserial", file=sys.stderr)
    raise

BAUD = 9600
PACK_PROFILE_SIZE = 99
WITNESS_UUID_LEN = 16

WCMD_GET_STATUS = 0xF0
WCMD_READ_PROFILE = 0xF1
WCMD_WRITE_PROFILE = 0xF2
WCMD_RESET_PROFILE = 0xF3
WCMD_SET_MODE = 0xF4
WCMD_SAVE_EEPROM = 0xF5
WCMD_LOAD_PRESET = 0xF6

OBI_WITNESS_BUS_CMD = 0x57

PRESETS = {
    "blank": 0,
    "bl1850b": 1,
    "bl1830": 2,
    "custom": 255,
}

MODES = {"passthrough": 0, "emulate": 1}

RSP_LEN = {
    WCMD_GET_STATUS: 18,
    WCMD_READ_PROFILE: 99,
    WCMD_WRITE_PROFILE: 1,
    WCMD_RESET_PROFILE: 1,
    WCMD_SET_MODE: 1,
    WCMD_SAVE_EEPROM: 1,
    WCMD_LOAD_PRESET: 1,
}


def hex_bytes(s: str) -> bytes:
    parts = s.replace(",", " ").split()
    return bytes(int(p, 16) for p in parts)


def request(ser: serial.Serial, payload_len: int, rsp_len: int, cmd: int, data: bytes = b"") -> bytes:
    frame = bytes([0x01, len(data), rsp_len, cmd]) + data
    expected = rsp_len + 2
    ser.reset_input_buffer()
    ser.write(frame)
    rsp = ser.read(expected)
    if len(rsp) != expected:
        raise RuntimeError(f"cmd 0x{cmd:02X}: expected {expected} bytes, got {len(rsp)}")
    if rsp[0] != cmd:
        raise RuntimeError(f"cmd 0x{cmd:02X}: response cmd mismatch 0x{rsp[0]:02X}")
    return rsp


def bus_request(ser: serial.Serial, subcmd: int, tx: bytes = b"") -> bytes:
    """Witness maintenance via OBI reader → pack 1-Wire (cmd 0x57 tunnel)."""
    rsp_len = RSP_LEN[subcmd]
    payload = bytes([subcmd, len(tx)]) + tx
    rsp = request(ser, len(payload), rsp_len, OBI_WITNESS_BUS_CMD, payload)
    return bytes(rsp[2:])


def wcmd(ser: serial.Serial, subcmd: int, tx: bytes = b"", *, over_bus: bool) -> bytes:
    if over_bus:
        return bus_request(ser, subcmd, tx)
    return bytes(request(ser, len(tx), RSP_LEN[subcmd], subcmd, tx)[2:])


def get_status(ser: serial.Serial, *, over_bus: bool) -> dict:
    body = wcmd(ser, WCMD_GET_STATUS, over_bus=over_bus)
    uuid = body[2 : 2 + WITNESS_UUID_LEN].hex()
    return {"mode": body[0], "preset": body[1], "uuid": uuid}


def load_preset(ser: serial.Serial, preset_id: int, *, over_bus: bool) -> None:
    wcmd(ser, WCMD_LOAD_PRESET, bytes([preset_id]), over_bus=over_bus)


def set_mode(ser: serial.Serial, mode: int, *, over_bus: bool) -> None:
    wcmd(ser, WCMD_SET_MODE, bytes([mode]), over_bus=over_bus)


def save_eeprom(ser: serial.Serial, *, over_bus: bool) -> None:
    if wcmd(ser, WCMD_SAVE_EEPROM, over_bus=over_bus)[0] != 0:
        raise RuntimeError("EEPROM save failed")


def factory_reset(ser: serial.Serial, preset_id: int = 0, *, over_bus: bool) -> None:
    wcmd(ser, WCMD_RESET_PROFILE, bytes([preset_id]), over_bus=over_bus)


def read_profile(ser: serial.Serial, *, over_bus: bool) -> bytes:
    return wcmd(ser, WCMD_READ_PROFILE, over_bus=over_bus)


def write_profile(ser: serial.Serial, blob: bytes, *, over_bus: bool) -> None:
    if len(blob) != PACK_PROFILE_SIZE:
        raise ValueError(f"profile must be {PACK_PROFILE_SIZE} bytes")
    if wcmd(ser, WCMD_WRITE_PROFILE, blob, over_bus=over_bus)[0] != 0:
        raise RuntimeError("profile write rejected")


def profile_from_capture(capture: dict, uuid: bytes | None = None) -> bytes:
    raw = capture["raw"]
    read_msg = hex_bytes(raw["read_msg"])
    if read_msg[0] != 0x33:
        raise ValueError("read_msg must start with 0x33")
    rom_id = read_msg[2:10]
    msg_frame = read_msg[10:42]

    model_rsp = hex_bytes(raw["model"])
    model = model_rsp[2:10].ljust(8, b"\x00")[:8]

    read_data = hex_bytes(raw["read_data"])
    if read_data[0] != 0xCC:
        raise ValueError("read_data must start with 0xCC")
    read_tpl = read_data[2 : 2 + 29]

    blob = bytearray(PACK_PROFILE_SIZE)
    blob[0:2] = (0x49, 0x57)
    blob[4:20] = uuid if uuid else b"WIT" + b"\xff" * 13
    blob[20] = MODES["emulate"]
    blob[21] = PRESETS["custom"]
    blob[22:30] = rom_id
    blob[30:62] = msg_frame
    blob[62:70] = model
    blob[70:99] = read_tpl
    return bytes(blob)


def main() -> None:
    ap = argparse.ArgumentParser(description="Program witness pack profile (OBI serial @ 9600)")
    ap.add_argument("port", nargs="?", default="COM8", help="OBI reader serial port (USB CDC)")
    ap.add_argument(
        "--bus",
        action="store_true",
        help="Use pack 1-Wire maintenance (OBI cmd 0x57) — no witness UART required",
    )
    ap.add_argument("--status", action="store_true", help="Print mode/preset/UUID")
    ap.add_argument("--preset", choices=sorted(PRESETS.keys()), help="Load built-in preset")
    ap.add_argument("--mode", choices=sorted(MODES.keys()), help="Set passthrough or emulate")
    ap.add_argument("--reset", action="store_true", help="Factory reset (blank preset)")
    ap.add_argument("--save", action="store_true", help="Persist profile to EEPROM")
    ap.add_argument("--import-json", type=Path, metavar="FILE", help="Import OBI capture JSON")
    ap.add_argument("--dump", type=Path, metavar="FILE", help="Dump raw profile blob")
    ap.add_argument("--uuid", help="16-byte UUID as hex (32 chars)")
    args = ap.parse_args()

    over_bus = args.bus

    with serial.Serial(args.port, BAUD, timeout=2) as ser:
        time.sleep(0.1)

        if args.status:
            st = get_status(ser, over_bus=over_bus)
            mode_name = next(k for k, v in MODES.items() if v == st["mode"])
            via = "1-Wire" if over_bus else "UART"
            print(f"[{via}] mode={mode_name} preset={st['preset']} uuid={st['uuid']}")

        if args.reset:
            factory_reset(ser, PRESETS["blank"], over_bus=over_bus)
            print("Factory reset (blank / passthrough)")

        if args.preset:
            load_preset(ser, PRESETS[args.preset], over_bus=over_bus)
            print(f"Loaded preset: {args.preset}")

        if args.import_json:
            cap = json.loads(args.import_json.read_text(encoding="utf-8"))
            uid = bytes.fromhex(args.uuid) if args.uuid else None
            if uid and len(uid) != WITNESS_UUID_LEN:
                raise SystemExit("--uuid must be 32 hex chars (16 bytes)")
            blob = profile_from_capture(cap, uid)
            write_profile(ser, blob, over_bus=over_bus)
            print(f"Imported profile from {args.import_json}")

        if args.mode:
            set_mode(ser, MODES[args.mode], over_bus=over_bus)
            print(f"Mode set to {args.mode}")

        if args.dump:
            blob = read_profile(ser, over_bus=over_bus)
            args.dump.write_bytes(blob)
            print(f"Wrote {len(blob)} bytes to {args.dump}")

        if args.save:
            save_eeprom(ser, over_bus=over_bus)
            print("Saved to EEPROM")

        if not any(
            [
                args.status,
                args.preset,
                args.mode,
                args.reset,
                args.import_json,
                args.dump,
                args.save,
            ]
        ):
            ap.print_help()


if __name__ == "__main__":
    main()
