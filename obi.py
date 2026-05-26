# SPDX-License-Identifier: MIT
#
# Open Battery Information (OBI) — Makita LXT 1-Wire bridge for MicroPython (Pico W).
#
# Protocol and transaction structure are derived from ArduinoOBI in the Open Battery
# Information project:
#   https://github.com/mnh-jansson/open-battery-information
#   Path: ArduinoOBI/src/main.cpp
#   Copyright (c) 2024 Martin Jansson — used under the MIT License (see CREDITS.md).
#
# This file is part of ChargerController; combined work is MIT-licensed; retain this
# notice in copies of substantial portions.
#
# Protocol: enable GPIO high, delay 400 ms, then Dallas 1-Wire with extra 90 µs between bytes.
# Pins: data = open-drain + external pull-up; enable = push-pull to battery interface.

import time
from machine import Pin

# --- Makita LXT command frames (same as OpenBatteryInformation/modules/makita_lxt.py) ---
READ_DATA_REQUEST = bytes([0x01, 0x04, 0x1D, 0xCC, 0xD7, 0x00, 0x00, 0xFF])
MODEL_CMD = bytes([0x01, 0x02, 0x10, 0xCC, 0xDC, 0x0C])
READ_MSG_CMD = bytes([0x01, 0x02, 0x28, 0x33, 0xAA, 0x00])

# Witness pack-bus maintenance (tools/attiny1616-witness/include/witness_onewire_cmds.h)
OBI_WITNESS_BUS_CMD = 0x57


class _BitBangOneWire:
    """Minimal Dallas 1-Wire master (RP2040 open-drain + pull-up)."""

    def __init__(self, pin_num):
        self.pin = Pin(pin_num, Pin.OPEN_DRAIN, Pin.PULL_UP)

    def reset(self):
        self.pin.value(0)
        time.sleep_us(480)
        self.pin.value(1)
        time.sleep_us(70)
        v = self.pin.value()
        time.sleep_us(410)
        return v == 0

    def write_bit(self, b):
        if b:
            self.pin.value(0)
            time.sleep_us(6)
            self.pin.value(1)
            time.sleep_us(64)
        else:
            self.pin.value(0)
            time.sleep_us(60)
            self.pin.value(1)
            time.sleep_us(10)

    def read_bit(self):
        self.pin.value(0)
        time.sleep_us(6)
        self.pin.value(1)
        time.sleep_us(9)
        v = self.pin.value()
        time.sleep_us(55)
        return v

    def write_byte(self, b):
        for i in range(8):
            self.write_bit(b & 1)
            b >>= 1

    def read_byte(self):
        v = 0
        for i in range(8):
            v |= (self.read_bit() & 1) << i
        return v


def _gap():
    time.sleep_us(90)


class MakitaOBI:
    """
    Battery BMS bridge: GP18 = 1-Wire data, GP19 = enable (active high during transaction).
    Call :meth:`request` with the same 8-byte USB frames the desktop app sends to ArduinoOBI.
    """

    def __init__(self, pin_data=18, pin_enable=19):
        self._ow = _BitBangOneWire(pin_data)
        self._en = Pin(pin_enable, Pin.OUT, value=0)
        self.last_error = None

    def enable(self, on):
        self._en.value(1 if on else 0)

    def _cmd_and_read_33(self, cmd, rsp_out):
        """Match Arduino cmd_and_read_33: rsp_out length = USB payload (ROM 8 bytes + remainder reads)."""
        ow = self._ow
        if len(rsp_out) < 8:
            raise ValueError("rsp_out too short")
        rest = len(rsp_out) - 8
        ow.reset()
        time.sleep_us(400)
        ow.write_byte(0x33)
        for i in range(8):
            _gap()
            rsp_out[i] = ow.read_byte()
        for i in range(len(cmd)):
            _gap()
            ow.write_byte(cmd[i])
        for j in range(rest):
            _gap()
            rsp_out[8 + j] = ow.read_byte()

    def _cmd_and_read_cc(self, cmd, rsp_out):
        ow = self._ow
        ow.reset()
        time.sleep_us(400)
        ow.write_byte(0xCC)
        for i in range(len(cmd)):
            _gap()
            ow.write_byte(cmd[i])
        for i in range(len(rsp_out)):
            _gap()
            rsp_out[i] = ow.read_byte()

    def _witness_bus_transact(self, subcmd, tx, rsp_out):
        """Tunnel witness EEPROM/profile cmds on pack 1-Wire (primary 0x57)."""
        ow = self._ow
        ow.reset()
        time.sleep_us(400)
        ow.write_byte(OBI_WITNESS_BUS_CMD)
        _gap()
        ow.write_byte(subcmd)
        _gap()
        ow.write_byte(len(tx))
        for b in tx:
            _gap()
            ow.write_byte(b)
        for i in range(len(rsp_out)):
            _gap()
            rsp_out[i] = ow.read_byte()

    def _cmd_and_read_raw(self, cmd, rsp_out):
        ow = self._ow
        ow.reset()
        time.sleep_us(400)
        for i in range(len(cmd)):
            _gap()
            ow.write_byte(cmd[i])
        for i in range(len(rsp_out)):
            _gap()
            rsp_out[i] = ow.read_byte()

    def _cmd_31(self):
        ow = self._ow
        ow.reset()
        time.sleep_us(400)
        ow.write_byte(0xCC)
        _gap()
        ow.write_byte(0x99)
        time.sleep_ms(400)
        ow.reset()
        time.sleep_us(400)
        ow.write_byte(0x31)
        _gap()
        b3 = ow.read_byte()
        _gap()
        b2 = ow.read_byte()
        _gap()
        return b2, b3

    def _cmd_32(self):
        ow = self._ow
        ow.reset()
        time.sleep_us(400)
        ow.write_byte(0xCC)
        _gap()
        ow.write_byte(0x99)
        time.sleep_ms(400)
        ow.reset()
        time.sleep_us(400)
        ow.write_byte(0x32)
        _gap()
        b3 = ow.read_byte()
        _gap()
        b2 = ow.read_byte()
        _gap()
        return b2, b3

    def request(self, frame):
        """
        USB frame: [0x01, len, rsp_len, cmd, ...data]
        Returns bytes: [cmd, rsp_len, payload...] (same as serial read from Arduino).
        """
        if len(frame) < 4 or frame[0] != 0x01:
            raise ValueError("bad OBI frame")
        ln = frame[1]
        rsp_len = frame[2]
        cmd = frame[3]
        data = frame[4 : 4 + ln]

        self.last_error = None
        self.enable(True)
        time.sleep_ms(400)
        try:
            out = bytearray(2 + rsp_len)
            out[0] = cmd
            out[1] = rsp_len

            if cmd == 0x01:
                out[2] = 0
                out[3] = 0
                out[4] = 1
            elif cmd == 0x31:
                b2, b3 = self._cmd_31()
                out[2] = 0
                out[3] = b2
                out[4] = b3
            elif cmd == 0x32:
                b2, b3 = self._cmd_32()
                out[2] = 0
                out[3] = b2
                out[4] = b3
            elif cmd == 0x33:
                buf = bytearray(rsp_len)
                self._cmd_and_read_33(data, buf)
                out[2 : 2 + rsp_len] = buf
            elif cmd == 0xCC:
                buf = bytearray(rsp_len)
                self._cmd_and_read_cc(data, buf)
                out[2 : 2 + rsp_len] = buf
            elif cmd == OBI_WITNESS_BUS_CMD:
                if len(data) < 2:
                    return bytes([cmd, 0])
                subcmd = data[0]
                tx_len = data[1]
                tx = data[2 : 2 + tx_len]
                buf = bytearray(rsp_len)
                self._witness_bus_transact(subcmd, tx, buf)
                out[2 : 2 + rsp_len] = buf
            else:
                raise ValueError("unsupported cmd 0x%02x" % cmd)

            return bytes(out)
        except Exception as ex:
            self.last_error = str(ex)
            raise
        finally:
            self.enable(False)


def parse_read_data_response(rsp):
    """Parse READ_DATA_REQUEST response payload (cmd 0xCC, rsp_len 0x1D)."""
    if rsp is None or len(rsp) < 2 + 0x1D:
        return None
    p = rsp[2:]
    v_pack = int.from_bytes(p[0:2], "little") / 1000.0
    cells = [
        int.from_bytes(p[2:4], "little") / 1000.0,
        int.from_bytes(p[4:6], "little") / 1000.0,
        int.from_bytes(p[6:8], "little") / 1000.0,
        int.from_bytes(p[8:10], "little") / 1000.0,
        int.from_bytes(p[10:12], "little") / 1000.0,
    ]
    t_cell = int.from_bytes(p[14:16], "little") / 100.0
    t_mos = int.from_bytes(p[16:18], "little") / 100.0
    return {
        "pack_v": round(v_pack, 3),
        "cells_v": [round(c, 3) for c in cells],
        "temp_c": round(t_cell, 2),
        "temp_mos_c": round(t_mos, 2),
    }
