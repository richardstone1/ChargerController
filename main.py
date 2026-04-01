import machine
from machine import ADC, Pin, PWM
import math
import time
import network
import uasyncio as asyncio
import array
import uctypes

try:
    import ujson as json
except ImportError:
    import json

try:
    from obi import MakitaOBI, READ_DATA_REQUEST, parse_read_data_response

    OBI_AVAILABLE = True
except ImportError:
    OBI_AVAILABLE = False

# Optional OTA support (if micropython_ota is present on device)
try:
    import micropython_ota  # type: ignore
except ImportError:
    micropython_ota = None


class ADCDMASampler:
    """
    RP2040 ADC DMA sampler using round-robin channels.
    Samples enabled mask bits (e.g. 0x07 = GP26..GP28, batt/current/temp only).
    """

    # ADC registers
    ADC_BASE = 0x4004C000
    ADC_CS = ADC_BASE + 0x00
    ADC_FCS = ADC_BASE + 0x08
    ADC_FIFO = ADC_BASE + 0x0C
    ADC_DIV = ADC_BASE + 0x10

    # DMA channel 0 registers
    DMA_BASE = 0x50000000
    DMA_CH0_READ_ADDR = DMA_BASE + 0x000
    DMA_CH0_WRITE_ADDR = DMA_BASE + 0x004
    DMA_CH0_TRANS_COUNT = DMA_BASE + 0x008
    DMA_CH0_CTRL_TRIG = DMA_BASE + 0x00C

    # Bit fields / constants
    ADC_CS_EN = 1 << 0
    ADC_CS_START_MANY = 1 << 3
    ADC_CS_RROBIN_SHIFT = 16
    ADC_FCS_EN = 1 << 0
    ADC_FCS_DREQ_EN = 1 << 3
    ADC_FCS_THRESH_SHIFT = 24
    ADC_FCS_OVER = 1 << 11
    ADC_FCS_UNDER = 1 << 10

    DREQ_ADC = 36
    DMA_CTRL_EN = 1 << 0
    DMA_CTRL_DATA_SIZE_16 = 1 << 2
    DMA_CTRL_INCR_WRITE = 1 << 5
    DMA_CTRL_TREQ_SHIFT = 15

    def __init__(self, channels_mask=0x0F, samples_per_channel=64):
        self.channels_mask = channels_mask & 0x0F
        self.channel_count = max(1, self._count_bits(self.channels_mask))
        self.samples_per_channel = max(8, int(samples_per_channel))
        self.total_samples = self.samples_per_channel * self.channel_count
        self.buf = array.array("H", [0] * self.total_samples)
        self.running = False

    @staticmethod
    def _count_bits(v):
        c = 0
        while v:
            c += v & 1
            v >>= 1
        return c

    def start(self):
        # Stop previous activity
        self.stop()

        mem32 = machine.mem32  # type: ignore[name-defined]
        fifo_addr = self.ADC_FIFO
        buf_addr = uctypes.addressof(self.buf)

        # Enable ADC and clear FIFO status.
        mem32[self.ADC_CS] = self.ADC_CS_EN | (self.channels_mask << self.ADC_CS_RROBIN_SHIFT)
        mem32[self.ADC_FCS] = self.ADC_FCS_EN | self.ADC_FCS_DREQ_EN | (1 << self.ADC_FCS_THRESH_SHIFT)
        mem32[self.ADC_DIV] = 0

        # Configure DMA CH0: ADC FIFO -> buffer (16-bit, increment write).
        ctrl = (
            self.DMA_CTRL_EN
            | self.DMA_CTRL_DATA_SIZE_16
            | self.DMA_CTRL_INCR_WRITE
            | (self.DREQ_ADC << self.DMA_CTRL_TREQ_SHIFT)
        )
        mem32[self.DMA_CH0_READ_ADDR] = fifo_addr
        mem32[self.DMA_CH0_WRITE_ADDR] = buf_addr
        mem32[self.DMA_CH0_TRANS_COUNT] = self.total_samples
        mem32[self.DMA_CH0_CTRL_TRIG] = ctrl

        # Start continuous conversions.
        mem32[self.ADC_CS] = (
            self.ADC_CS_EN
            | self.ADC_CS_START_MANY
            | (self.channels_mask << self.ADC_CS_RROBIN_SHIFT)
        )
        self.running = True

    def stop(self):
        mem32 = machine.mem32  # type: ignore[name-defined]
        mem32[self.DMA_CH0_CTRL_TRIG] = 0
        mem32[self.ADC_CS] = 0
        mem32[self.ADC_FCS] = 0
        self.running = False

    def read_averages_u16(self):
        # Restart DMA if one-shot transfer completed.
        mem32 = machine.mem32  # type: ignore[name-defined]
        if self.running and mem32[self.DMA_CH0_TRANS_COUNT] == 0:
            self.start()

        sums = [0, 0, 0, 0]
        counts = [0, 0, 0, 0]
        chan_list = []
        for ch in (0, 1, 2, 3):
            if self.channels_mask & (1 << ch):
                chan_list.append(ch)
        if not chan_list:
            return {0: 0, 1: 0, 2: 0, 3: 0}

        for idx, raw in enumerate(self.buf):
            ch = chan_list[idx % len(chan_list)]
            sums[ch] += raw & 0x0FFF
            counts[ch] += 1

        avg = {}
        for ch in (0, 1, 2, 3):
            if counts[ch] > 0:
                # scale 12-bit avg to MicroPython-style 16-bit ADC value
                avg[ch] = int((sums[ch] / counts[ch]) * 65535 / 4095)
            else:
                avg[ch] = 0
        return avg


class ChargerController:
    # ---------- Fixed hardware spec ----------
    ADC_MAX = 65535.0
    VREF = 3.3  # nominal RP2040 ADC reference (3V3 rail); _adc_to_v uses this unless ratio≠1
    # Global raw ADC scale (temp/current). Battery uses VBATT linear cal below.
    ADC_VOLTAGE_CALIB_RATIO = 1.0

    # Pack voltage linear cal (DMM = A * V_firmware + B), least-squares on three uncorrected points:
    # (3.61→3.315), (5.12→4.971), (19.76→19.99). Single gain cannot fit all three; linear does.
    VBATT_CALIB_LINEAR_A = 1.0298424991024901
    VBATT_CALIB_LINEAR_B = -0.3547375998099831

    # Divider definitions are explicit as R_TOP (signal side) and R_BOTTOM (GND side).
    VDIV_BATT_R_TOP_OHM = 100000.0
    VDIV_BATT_R_BOTTOM_OHM = 10000.0
    # Pack short / true 0V: ADC+divider offset often ~0.3–0.5 V pack-equivalent; clamp below this to 0.
    VBATT_ZERO_CLAMP_V = 0.50
    # If divider tap (GP26 voltage before ×11) is below this, report 0 V (B+ shorted to GND / open noise).
    VBATT_ADC_NEAR_ZERO_V = 0.07

    # Current ADC divider (for ACS758 output): 10k/20k by your latest plan.
    # If wired as 10k top, 20k bottom then ratio = 20/(10+20)=0.666...
    VDIV_CURR_R_TOP_OHM = 10000.0
    VDIV_CURR_R_BOTTOM_OHM = 20000.0

    ACS758_ZERO_SENSOR_V = 2.5
    ACS758_SENS_SENSOR_V_PER_A = 0.040  # adjust if your ACS758 variant differs

    # Thermistor model
    THERM_PULLUP_OHM = 10000.0
    # 1MΩ pull-down on thermistor sense (GP28 / ADC2) to GND — NOT on ADC1 (GP27, current).
    # With pull-down: open leads → R ~1M (rejected); NTC present → R 400Ω–200k (detected).
    THERM_PULLDOWN_OHM = 1000000.0
    THERM_NOMINAL_OHM = 10000.0
    THERM_NOMINAL_C = 25.0
    THERM_BETA = 3950.0
    # Valid NTC resistance band: pull-up-only (open) + 1M pull-down → R ~ 1M; real 10k NTC spans ~1k–~130k.
    THERM_DETECT_R_MIN_OHM = 400.0
    THERM_DETECT_R_MAX_OHM = 200000.0

    # Hard safety limits
    MAX_VOLTAGE_V = 21.0
    MAX_CURRENT_A = 15.0
    MAX_OVERRANGE_FRAC = 0.10  # allow up to +10% as anomaly window
    # Clear configurable over_voltage fault only when pack V drops this far below cutoff (stops LED/console chatter).
    OVER_VOLTAGE_HYSTERESIS_V = 2.0

    # Fan profile tuning
    FAN_MIN_TEMP_C = 30.0
    FAN_MAX_TEMP_C = 55.0
    FAN_MAX_CURRENT_A = 12.0
    FAN_FORCE_MAX_TEMP_C = 40.0
    FAN_COLD_FORCE_ON_C = 8.0
    THERMAL_CHARGE_CUTOFF_C = 45.0
    COOLDOWN_MIN_FAN_PCT = 35.0
    FAN_EST_MAX_RPM = 5000.0
    FAN_TACH_PIN = None  # Optional: set GPIO number (e.g. 4) to enable fan tach input
    FAN_TACH_PULSES_PER_REV = 2
    # Default OFF: custom ADCDMASampler + machine.ADC together often hard-freezes evaluate()
    # (no V= lines, HTTP never starts). Direct read_u16() per channel is reliable on Pico W.
    USE_ADC_DMA = False
    DMA_SAMPLES_PER_CHANNEL = 64

    # Open Battery Information (Makita LXT 1-Wire): GP18 = data (open-drain + pull-up), GP19 = enable
    OBI_PIN_DATA = 18
    OBI_PIN_ENABLE = 19
    OBI_POLL_MS = 5000

    def __init__(self):
        # ADCs
        self.adc_v = ADC(26)   # GP26 ADC0
        self.adc_i = ADC(27)   # GP27 ADC1
        self.adc_t = ADC(28)   # GP28 ADC2
        self._adc_dma_ok = False
        self._adc_dma_latest = {0: 0, 1: 0, 2: 0, 3: 0}
        self._adc_dma_sampler = None
        if self.USE_ADC_DMA:
            try:
                self._adc_dma_sampler = ADCDMASampler(
                    channels_mask=0x07,  # ADC0..2 only (no GP29 / ADC3)
                    samples_per_channel=self.DMA_SAMPLES_PER_CHANNEL,
                )
                self._adc_dma_sampler.start()
                self._adc_dma_ok = True
            except Exception as ex:
                print("ADC DMA init failed, using direct ADC reads:", ex)
                self._adc_dma_sampler = None
                self._adc_dma_ok = False

        # Outputs
        self.charge_gate = Pin(2, Pin.OUT, value=0)  # GP2, active high enables gate drive
        self.fan_pwm = PWM(Pin(3))
        self.fan_pwm.freq(25000)  # quiet ultrasonic range
        self.fan_pwm.duty_u16(0)
        self.fan_last_pct = 0.0

        # External LEDs on GP13/14/15: GPIO HIGH = on. Wiring: GPIO → 330Ω → LED anode, LED cathode → GND
        # (common ground with Pico). ~4 mA at 3.3 V; fine for typical 20 mA LEDs.
        self.led_red = Pin(13, Pin.OUT, value=0)
        self.led_green = Pin(14, Pin.OUT, value=0)
        self.led_yellow = Pin(15, Pin.OUT, value=0)
        self._led_state = None  # must exist before first set_leds()
        self.set_leds(red=False, green=True, yellow=False)  # default: green on steady

        self.buzzer = PWM(Pin(16))
        self.buzzer.duty_u16(0)

        # State
        self.manual_charge_enable = False
        self.fault_latched = False
        self.last_fault = "none"
        self.fan_override_pct = None
        self.fan_enabled = True
        self.fan_auto_mode = True
        self.abort_latched = False
        self.fan_cold_assist_enabled = True
        self.fan_cold_force_on_c = self.FAN_COLD_FORCE_ON_C
        self.fan_cold_force_min_pct = 45.0

        # Runtime-configurable control limits
        self.cutoff_voltage_enabled = True
        self.min_current_enabled = True
        self.cutoff_temp_enabled = True
        self.cutoff_voltage_v = self.MAX_VOLTAGE_V
        self.min_charge_current_a = 0.25
        self.max_temp_limit_c = 55.0

        # External source stop detection (independent of hard cutoffs)
        self.source_stop_detect_enabled = True
        self.source_present_min_current_a = self.min_charge_current_a  # legacy alias
        self.source_stop_confirm_s = 4.0
        self._source_low_current_ms = 0.0
        self.source_stopped = False
        self.charge_hold_reason = "none"
        self.run_mode = "charge"  # charge|discharge
        self.manual_discharge_enable = False
        self.require_battery_present = True
        self.battery_presence_override = False
        self.thermistor_override = False

        # Discharge pulse/rest behavior for rebound compensation
        self.discharge_target_v = 15.0
        self.discharge_undershoot_v = 0.05
        self.discharge_rebound_tol_v = 0.02
        self.discharge_rest_s = 4.0
        self.discharge_state = "idle"  # idle|pull_down|rest|done
        self.discharge_last_cutoff_v = 0.0
        self.discharge_last_rebound_v = 0.0
        self._discharge_rest_ms = 0.0

        # Preset target profiles (editable)
        self.active_preset = "none"  # none|storagecharge|hotready|user1|user2
        self.preset_storagecharge_v = 18.4
        self.preset_hotready_v = 20.2
        self.preset_user1_v = 19.0
        self.preset_user2_v = 20.6
        # Post-charge cooldown behavior
        self.cooldown_enabled = True
        self.cooldown_active = False
        self.cooldown_temp_delta_c = 0.08
        self.cooldown_stable_s = 20.0
        self._cooldown_stable_ms = 0.0
        self._cooldown_last_temp_c = None

        # Persistent post-cooldown fan sampling:
        # if pack temp rises while fan is off and power is available, run fan again.
        self.fan_persist_enabled = True
        self.fan_persist_sample_s = 30.0
        self.fan_persist_rise_c = 0.10
        self.fan_persist_run_s = 20.0
        self.fan_persist_min_pct = 35.0
        self.thermistor_present_min_c = -20.0
        self.thermistor_present_max_c = 90.0
        self._fan_persist_ref_temp_c = None
        self._fan_persist_wait_ms = 0.0
        self._fan_persist_run_ms = 0.0

        # Optional tachometer capture
        self._tach_count = 0
        self._tach_last_ms = time.ticks_ms()
        self._fan_rpm = 0.0
        if self.FAN_TACH_PIN is not None:
            self.fan_tach = Pin(self.FAN_TACH_PIN, Pin.IN, Pin.PULL_UP)
            self.fan_tach.irq(trigger=Pin.IRQ_FALLING, handler=self._tach_irq)
        else:
            self.fan_tach = None

        # Running stats
        self.peak_temp_c = -273.15
        self.cumulative_ah = 0.0
        self.cumulative_wh = 0.0
        self._last_eval_ms = None
        self._warmup_until_ms = 0  # set on first evaluate; green shown instead of red during warmup
        self._cutoff_over_v_latch = False  # hysteresis for cutoff_voltage fault
        self.telemetry = {}

        self.obi = None
        self.obi_snapshot = None
        self._last_obi_tick = None
        if OBI_AVAILABLE:
            try:
                self.obi = MakitaOBI(self.OBI_PIN_DATA, self.OBI_PIN_ENABLE)
            except Exception as ex:
                print("OBI (GP18/19) init failed:", ex)

    def _poll_obi_if_due(self, now_ms):
        """Periodic read from pack BMS via OBI 1-Wire (~400 ms when run; keep rate low)."""
        if self.obi is None:
            return
        if self._last_obi_tick is not None and time.ticks_diff(now_ms, self._last_obi_tick) < self.OBI_POLL_MS:
            return
        self._last_obi_tick = now_ms
        try:
            r = self.obi.request(READ_DATA_REQUEST)
            self.obi_snapshot = parse_read_data_response(r)
        except Exception as ex:
            self.obi_snapshot = {"error": str(ex)}

    # ---------- IO helpers ----------
    def _adc_ref_volts(self):
        """Effective full-scale voltage for raw→V conversion (matches measured 3V3 if calibrated)."""
        return self.VREF * self.ADC_VOLTAGE_CALIB_RATIO

    def _adc_to_v(self, raw):
        return (raw / self.ADC_MAX) * self._adc_ref_volts()

    def _refresh_adc_dma(self):
        if not self._adc_dma_ok or self._adc_dma_sampler is None:
            return
        try:
            self._adc_dma_latest = self._adc_dma_sampler.read_averages_u16()
        except Exception as ex:
            print("ADC DMA read failed, fallback to direct ADC:", ex)
            self._adc_dma_ok = False

    def _read_adc_u16(self, channel):
        if self._adc_dma_ok:
            return int(self._adc_dma_latest.get(channel, 0))
        if channel == 0:
            return self.adc_v.read_u16()
        if channel == 1:
            return self.adc_i.read_u16()
        if channel == 2:
            return self.adc_t.read_u16()
        return 0

    @classmethod
    def _divider_ratio(cls, r_top, r_bottom):
        return r_bottom / (r_top + r_bottom)

    def _read_battery_adc_raw_u16(self):
        """Sample ADC0 (GP26) only — do not use DMA round-robin average for ch0.

        Round-robin DMA can assign FIFO samples to the wrong channel if the buffer
        phase doesn't align with ch0, which shows up as random multi-volt errors when
        B+ is actually at 0 V.

        Must pause DMA while calling read_u16(): concurrent DMA + single-shot ADC can
        hang the RP2040 ADC and freeze evaluate() (no telemetry, HTTP never binds).
        """
        dma_active = self._adc_dma_ok and self._adc_dma_sampler is not None
        if dma_active:
            self._adc_dma_sampler.stop()
        try:
            s = sorted((self.adc_v.read_u16(), self.adc_v.read_u16(), self.adc_v.read_u16()))
            return s[1]
        finally:
            if dma_active:
                self._adc_dma_sampler.start()

    def read_battery_voltage(self):
        v_adc = self._adc_to_v(self._read_battery_adc_raw_u16())
        # True 0 V at tap (B+ at GND): ignore tiny offset and linear-cal blow-up.
        if v_adc < self.VBATT_ADC_NEAR_ZERO_V:
            return 0.0
        ratio = self._divider_ratio(self.VDIV_BATT_R_TOP_OHM, self.VDIV_BATT_R_BOTTOM_OHM)
        v = v_adc / ratio
        if v < self.VBATT_ZERO_CLAMP_V:
            return 0.0
        v = v * self.VBATT_CALIB_LINEAR_A + self.VBATT_CALIB_LINEAR_B
        return v if v > 0.0 else 0.0

    def read_current_a(self):
        v_adc = self._adc_to_v(self._read_adc_u16(1))
        ratio = self._divider_ratio(self.VDIV_CURR_R_TOP_OHM, self.VDIV_CURR_R_BOTTOM_OHM)
        sensor_v = v_adc / ratio
        return (sensor_v - self.ACS758_ZERO_SENSOR_V) / self.ACS758_SENS_SENSOR_V_PER_A

    def _read_ntc_channel(self):
        """Read temp ADC (10k NTC + pull-up). Returns (t_c, r_ntc_ohm or None if saturated/open)."""
        raw = self._read_adc_u16(2)
        v = self._adc_to_v(raw)
        if v <= 0.001:
            return -273.15, None
        vref_eff = self._adc_ref_volts()
        if v >= vref_eff - 0.001:
            return 200.0, None
        r_ntc = self.THERM_PULLUP_OHM * (v / (vref_eff - v))
        t0_k = self.THERM_NOMINAL_C + 273.15
        inv_t = (1.0 / t0_k) + (1.0 / self.THERM_BETA) * math.log(r_ntc / self.THERM_NOMINAL_OHM)
        t_c = (1.0 / inv_t) - 273.15
        return t_c, r_ntc

    def read_temp_c(self):
        t_c, _ = self._read_ntc_channel()
        return t_c

    def _thermistor_10k_divider_ok(self, r_ntc):
        if r_ntc is None:
            return False
        return self.THERM_DETECT_R_MIN_OHM <= r_ntc <= self.THERM_DETECT_R_MAX_OHM

    def _battery_attached_therm(self, t_c, r_ntc):
        """True when temp ADC sees a plausible 10k-class NTC (pack connected); open leads fail here."""
        if not self._thermistor_10k_divider_ok(r_ntc):
            return False
        return self.thermistor_present_min_c <= t_c <= self.thermistor_present_max_c

    def read_battery_therm_detection(self):
        """Single sample: battery detected via NTC divider (use for API gating)."""
        t_c, r_ntc = self._read_ntc_channel()
        t_sensor_ok = -40.0 <= t_c <= 120.0
        return bool(self._battery_attached_therm(t_c, r_ntc) and t_sensor_ok)

    def set_charge(self, enabled):
        self.charge_gate.value(1 if enabled else 0)

    def set_fan_pct(self, pct):
        pct = max(0.0, min(100.0, float(pct)))
        self.fan_last_pct = pct
        self.fan_pwm.duty_u16(int(65535 * (pct / 100.0)))

    def _tach_irq(self, pin):
        self._tach_count += 1

    def _fan_rpm_value(self, now_ms):
        # Return measured RPM if tach is available, else estimated RPM from PWM duty.
        if self.fan_tach is not None:
            elapsed_ms = time.ticks_diff(now_ms, self._tach_last_ms)
            if elapsed_ms >= 1000:
                pulses = self._tach_count
                self._tach_count = 0
                self._tach_last_ms = now_ms
                rps = (pulses / float(self.FAN_TACH_PULSES_PER_REV)) / (elapsed_ms / 1000.0)
                self._fan_rpm = max(0.0, rps * 60.0)
            return self._fan_rpm, False
        est = (self.fan_last_pct / 100.0) * self.FAN_EST_MAX_RPM if self.fan_enabled else 0.0
        return est, True

    def set_leds(self, red=False, green=False, yellow=False):
        # Active high: 1 = LED on. Skip GPIO writes when unchanged (reduces flicker from noisy thresholds).
        state = (bool(red), bool(green), bool(yellow))
        if state == self._led_state:
            return
        self._led_state = state
        self.led_red.value(1 if red else 0)
        self.led_green.value(1 if green else 0)
        self.led_yellow.value(1 if yellow else 0)

    async def play_tone(self, hz, duration_ms, duty=24000):
        self.buzzer.freq(int(hz))
        self.buzzer.duty_u16(duty)
        await asyncio.sleep_ms(int(duration_ms))
        self.buzzer.duty_u16(0)

    async def play_start_beep(self):
        # Start Beep: A5 880Hz for 100ms
        await self.play_tone(880, 100)

    async def play_finish_melody(self):
        # Finish: C6, E6, G6
        for hz in (1047, 1318, 1567):
            await self.play_tone(hz, 130)
            await asyncio.sleep_ms(50)

    def _fan_profile(self, temp_c, current_a):
        if self.fan_override_pct is not None:
            return self.fan_override_pct

        # Blend temp and current driven fan requests, choose the higher
        temp_req = 0.0
        if temp_c > self.FAN_MIN_TEMP_C:
            span = self.FAN_MAX_TEMP_C - self.FAN_MIN_TEMP_C
            temp_req = 100.0 * min(1.0, (temp_c - self.FAN_MIN_TEMP_C) / span)

        current_req = 0.0
        if current_a > 0.5:
            current_req = 100.0 * min(1.0, current_a / self.FAN_MAX_CURRENT_A)

        return max(temp_req, current_req)

    def evaluate(self):
        preset_target_v = None
        if self.active_preset == "storagecharge":
            preset_target_v = self.preset_storagecharge_v
        elif self.active_preset == "hotready":
            preset_target_v = self.preset_hotready_v
        elif self.active_preset == "user1":
            preset_target_v = self.preset_user1_v
        elif self.active_preset == "user2":
            preset_target_v = self.preset_user2_v

        v_batt = self.read_battery_voltage()
        self._refresh_adc_dma()  # no-op when USE_ADC_DMA is False
        i_batt = self.read_current_a()
        t_batt, r_therm = self._read_ntc_channel()
        t_sensor_ok = -40.0 <= t_batt <= 120.0
        therm_override_active = self.thermistor_override
        # 10k NTC on temp ADC: open B+/B- → invalid divider (no detection). Override allows bench use.
        battery_attached_therm = self._battery_attached_therm(t_batt, r_therm) and t_sensor_ok
        battery_present = (
            battery_attached_therm or self.battery_presence_override or self.thermistor_override
        )
        thermistor_usable = battery_attached_therm and (not therm_override_active)
        # Peak only tracks valid NTC readings; no bogus peak when pack absent (override does not invent temp).
        if battery_attached_therm:
            if t_batt > self.peak_temp_c:
                self.peak_temp_c = t_batt
        else:
            self.peak_temp_c = -273.15

        now_ms = time.ticks_ms()
        if self._last_eval_ms is None:
            dt_h = 0.0
            dt_ms = 0.0
            self._warmup_until_ms = now_ms + 2500  # 2.5 s warmup: green by default, suppress spurious fault display
        else:
            dt_ms = float(time.ticks_diff(now_ms, self._last_eval_ms))
            dt_h = dt_ms / 3600000.0
        self._last_eval_ms = now_ms

        # Count only positive charge flow into the pack
        charge_i = i_batt if i_batt > 0.0 else 0.0
        self.cumulative_ah += charge_i * dt_h
        self.cumulative_wh += (v_batt * charge_i) * dt_h

        # Hard interlock
        fault = None
        abs_voltage_max = self.MAX_VOLTAGE_V * (1.0 + self.MAX_OVERRANGE_FRAC)
        abs_current_max = self.MAX_CURRENT_A * (1.0 + self.MAX_OVERRANGE_FRAC)

        # Absolute protection caps (beyond anomaly allowance)
        if v_batt > abs_voltage_max:
            fault = "over_voltage_abs"
        elif i_batt > abs_current_max:
            fault = "over_current_abs"

        # Configurable Pico supervisor cutoffs (hysteresis on V cutoff avoids red/green flicker on noisy ADC)
        if fault is None:
            if self.cutoff_voltage_enabled:
                if v_batt > self.cutoff_voltage_v:
                    self._cutoff_over_v_latch = True
                elif v_batt < (self.cutoff_voltage_v - self.OVER_VOLTAGE_HYSTERESIS_V):
                    self._cutoff_over_v_latch = False
                if self._cutoff_over_v_latch:
                    fault = "over_voltage"
            else:
                self._cutoff_over_v_latch = False
        if fault is None:
            if thermistor_usable and self.cutoff_temp_enabled and t_batt > self.max_temp_limit_c:
                fault = "over_temp"
            elif thermistor_usable and t_batt >= self.THERMAL_CHARGE_CUTOFF_C:
                fault = "thermal_cutoff"
            elif self.abort_latched:
                fault = "aborted"

        # Detect low-current end-of-charge only in charge mode.
        if (
            fault is None
            and self.run_mode == "charge"
            and (self.source_stop_detect_enabled or self.min_current_enabled)
            and self.manual_charge_enable
        ):
            min_i_th = self.min_charge_current_a
            if i_batt < min_i_th:
                self._source_low_current_ms += dt_ms
            else:
                self._source_low_current_ms = 0.0
                self.source_stopped = False
            if self._source_low_current_ms >= (self.source_stop_confirm_s * 1000.0):
                self.source_stopped = True
                # External source ended the cycle; stop requesting charge.
                self.manual_charge_enable = False
                self.charge_hold_reason = "min_current_reached"
        else:
            self._source_low_current_ms = 0.0
            if not self.manual_charge_enable:
                self.source_stopped = False

        # Preset target stop (independent of external source decision).
        if fault is None and self.run_mode == "charge" and self.manual_charge_enable and (preset_target_v is not None):
            if v_batt >= preset_target_v:
                self.manual_charge_enable = False
                self.charge_hold_reason = "preset_target_reached"

        # Presence gating for all active run modes unless override is set.
        if self.require_battery_present and (not battery_present):
            self.manual_charge_enable = False
            self.manual_discharge_enable = False
            self.source_stopped = False
            self.discharge_state = "idle"
            self.charge_hold_reason = "battery_absent"

        was_charge_enabled = bool(self.charge_gate.value())
        target_charge_enabled = False

        if fault is not None:
            self.fault_latched = True
            self.last_fault = fault
            self.charge_hold_reason = fault
            target_charge_enabled = False
            # During warmup, show green (default) instead of red to avoid spurious faults from settling ADC
            in_warmup = time.ticks_diff(self._warmup_until_ms, now_ms) > 0
            if in_warmup:
                self.set_leds(red=False, green=True, yellow=False)
            else:
                self.set_leds(red=True, green=False, yellow=False)
        else:
            self.fault_latched = False
            if self.run_mode == "charge":
                waiting_for_pack = self.require_battery_present and (not battery_present)
                if self.manual_charge_enable and not self.source_stopped:
                    target_charge_enabled = True
                    self.charge_hold_reason = "charging"
                    self.set_leds(red=False, green=False, yellow=True)
                elif waiting_for_pack:
                    target_charge_enabled = False
                    self.set_leds(red=False, green=True, yellow=False)
                else:
                    target_charge_enabled = False
                    if self.charge_hold_reason == "charging":
                        self.charge_hold_reason = "idle"
                    self.set_leds(red=False, green=True, yellow=False)
            else:
                # Discharge mode pulse/rest cycle to handle rebound.
                if not self.manual_discharge_enable:
                    self.discharge_state = "idle"
                    target_charge_enabled = False
                    self.charge_hold_reason = "discharge_idle"
                else:
                    if self.discharge_state in ("idle", "done"):
                        if v_batt > self.discharge_target_v:
                            self.discharge_state = "pull_down"
                        else:
                            self.discharge_state = "done"
                            self.manual_discharge_enable = False
                            self.charge_hold_reason = "discharge_target_met"

                    if self.discharge_state == "pull_down":
                        target_charge_enabled = True
                        self.charge_hold_reason = "discharge_pull_down"
                        if v_batt <= (self.discharge_target_v - self.discharge_undershoot_v):
                            target_charge_enabled = False
                            self.discharge_last_cutoff_v = v_batt
                            self.discharge_state = "rest"
                            self._discharge_rest_ms = 0.0
                            self.charge_hold_reason = "discharge_rest"
                    elif self.discharge_state == "rest":
                        target_charge_enabled = False
                        self._discharge_rest_ms += dt_ms
                        if self._discharge_rest_ms >= (self.discharge_rest_s * 1000.0):
                            rebound = max(0.0, v_batt - self.discharge_last_cutoff_v)
                            self.discharge_last_rebound_v = rebound
                            if (v_batt <= self.discharge_target_v) and (rebound <= self.discharge_rebound_tol_v):
                                self.discharge_state = "done"
                                self.manual_discharge_enable = False
                                self.charge_hold_reason = "discharge_complete"
                            else:
                                self.discharge_state = "pull_down"
                                self.charge_hold_reason = "discharge_pull_down"
                    else:
                        target_charge_enabled = False
                if target_charge_enabled:
                    self.set_leds(red=False, green=False, yellow=True)
                else:
                    self.set_leds(red=False, green=True, yellow=False)

        self.set_charge(target_charge_enabled)

        # Enter cooldown when charging transitions from ON to OFF.
        if self.cooldown_enabled and was_charge_enabled and not target_charge_enabled:
            self.cooldown_active = True
            self._cooldown_stable_ms = 0.0
            self._cooldown_last_temp_c = t_batt if battery_attached_therm else None
        elif target_charge_enabled:
            self.cooldown_active = False
            self._cooldown_stable_ms = 0.0
            self._cooldown_last_temp_c = t_batt if battery_attached_therm else None

        # Exit cooldown when temperature movement stays within threshold long enough.
        if self.cooldown_active and battery_attached_therm:
            if self._cooldown_last_temp_c is None:
                self._cooldown_last_temp_c = t_batt
            temp_move = abs(t_batt - self._cooldown_last_temp_c)
            if temp_move <= self.cooldown_temp_delta_c:
                self._cooldown_stable_ms += dt_ms
            else:
                self._cooldown_stable_ms = 0.0
            self._cooldown_last_temp_c = t_batt
            if self._cooldown_stable_ms >= (self.cooldown_stable_s * 1000.0):
                self.cooldown_active = False
                self._cooldown_stable_ms = 0.0

        # No valid NTC: cooldown cannot use temperature; clear (override does not provide a real T).
        if not battery_attached_therm:
            self.cooldown_active = False
            self._cooldown_stable_ms = 0.0
            self._cooldown_last_temp_c = None

        # Fan temp axis: use a low synthetic value when no NTC so temp-driven fan stays off; current path still works.
        t_fan = t_batt if battery_attached_therm else (self.FAN_MIN_TEMP_C - 25.0)

        # AC/DC is not sensed on Pico; assume rails present when unit is running.
        power_available = True
        if self.fan_enabled:
            fan_pct = self._fan_profile(t_fan, i_batt) if self.fan_auto_mode else (self.fan_override_pct or 0.0)
            if (
                self.fan_cold_assist_enabled
                and battery_present
                and battery_attached_therm
                and t_batt <= self.fan_cold_force_on_c
            ):
                fan_pct = max(fan_pct, self.fan_cold_force_min_pct)
            if battery_attached_therm and t_batt >= self.FAN_FORCE_MAX_TEMP_C:
                fan_pct = max(fan_pct, 100.0)
            # Keep fan running through cooldown in auto mode.
            if self.cooldown_active and self.fan_auto_mode:
                fan_pct = max(fan_pct, self.COOLDOWN_MIN_FAN_PCT)

            # Persistent sampling: if battery thermistor remains live and temperature keeps changing,
            # periodically pulse fan to help converge toward ambient.
            if (
                self.fan_persist_enabled
                and self.fan_auto_mode
                and (not self.cooldown_active)
                and power_available
                and battery_attached_therm
            ):
                if fan_pct <= 0.1:
                    if self._fan_persist_run_ms > 0.0:
                        self._fan_persist_run_ms = max(0.0, self._fan_persist_run_ms - dt_ms)
                        fan_pct = max(fan_pct, self.fan_persist_min_pct)
                        if self._fan_persist_run_ms <= 0.0:
                            self._fan_persist_ref_temp_c = t_batt
                            self._fan_persist_wait_ms = 0.0
                    else:
                        if self._fan_persist_ref_temp_c is None:
                            self._fan_persist_ref_temp_c = t_batt
                            self._fan_persist_wait_ms = 0.0
                        self._fan_persist_wait_ms += dt_ms
                        if self._fan_persist_wait_ms >= (self.fan_persist_sample_s * 1000.0):
                            temp_delta = abs(t_batt - self._fan_persist_ref_temp_c)
                            if temp_delta > self.fan_persist_rise_c:
                                self._fan_persist_run_ms = self.fan_persist_run_s * 1000.0
                                fan_pct = max(fan_pct, self.fan_persist_min_pct)
                            self._fan_persist_ref_temp_c = t_batt
                            self._fan_persist_wait_ms = 0.0
                else:
                    self._fan_persist_run_ms = 0.0
                    self._fan_persist_ref_temp_c = t_batt
                    self._fan_persist_wait_ms = 0.0
            else:
                self._fan_persist_run_ms = 0.0
                self._fan_persist_ref_temp_c = t_batt if battery_attached_therm else None
                self._fan_persist_wait_ms = 0.0
            self.set_fan_pct(fan_pct)
        else:
            fan_pct = 0.0
            self.set_fan_pct(0.0)
            self._fan_persist_run_ms = 0.0
            self._fan_persist_ref_temp_c = t_batt if battery_attached_therm else None
            self._fan_persist_wait_ms = 0.0

        fan_rpm, fan_rpm_estimated = self._fan_rpm_value(now_ms)
        v_sensor_ok = 0.0 <= v_batt <= 40.0
        i_sensor_ok = -30.0 <= i_batt <= 60.0
        voltage_anomaly = self.MAX_VOLTAGE_V < v_batt <= abs_voltage_max
        current_anomaly = self.MAX_CURRENT_A < i_batt <= abs_current_max

        if self.fault_latched:
            system_state = "FAULT_" + self.last_fault
        elif self.cooldown_active:
            system_state = "COOLDOWN"
        elif self.run_mode == "discharge" and self.manual_discharge_enable:
            system_state = "DISCHARGE_" + self.discharge_state.upper()
        elif self.source_stopped:
            system_state = "SOURCE_STOPPED"
        elif bool(self.charge_gate.value()):
            system_state = "CHARGING"
        else:
            system_state = "IDLE"

        self._poll_obi_if_due(now_ms)

        self.telemetry = {
            "system_state": system_state,
            "adc_dma_enabled": bool(self.USE_ADC_DMA),
            "adc_dma_active": bool(self._adc_dma_ok),
            "v_batt": round(v_batt, 3),
            "i_batt": round(i_batt, 3),
            "rated_voltage_v": round(self.MAX_VOLTAGE_V, 2),
            "rated_current_a": round(self.MAX_CURRENT_A, 2),
            "absolute_voltage_max_v": round(abs_voltage_max, 2),
            "absolute_current_max_a": round(abs_current_max, 2),
            "voltage_anomaly": bool(voltage_anomaly),
            "current_anomaly": bool(current_anomaly),
            "t_batt_c": (round(t_batt, 2) if battery_attached_therm else None),
            "t_batt_valid": bool(battery_attached_therm),
            "v_sensor_ok": bool(v_sensor_ok),
            "i_sensor_ok": bool(i_sensor_ok),
            "t_sensor_ok": bool(battery_attached_therm and t_sensor_ok),
            "thermistor_ohm": (
                (round(r_therm, 0) if r_therm is not None else None)
                if battery_attached_therm
                else None
            ),
            "battery_attached_therm": bool(battery_attached_therm),
            "battery_present": bool(battery_present),
            "require_battery_present": bool(self.require_battery_present),
            "battery_presence_override": bool(self.battery_presence_override),
            "thermistor_override": bool(self.thermistor_override),
            "thermistor_usable": bool(thermistor_usable),
            "peak_temp_c": (round(self.peak_temp_c, 2) if battery_attached_therm else None),
            "max_temp_limit_c": round(self.max_temp_limit_c, 1),
            "thermal_charge_cutoff_c": round(self.THERMAL_CHARGE_CUTOFF_C, 1),
            "fan_pct": round(fan_pct, 1),
            "fan_tach_enabled": bool(self.fan_tach is not None),
            "fan_rpm": int(fan_rpm),
            "fan_rpm_estimated": bool(fan_rpm_estimated),
            "fan_enabled": bool(self.fan_enabled),
            "fan_auto_mode": bool(self.fan_auto_mode),
            "fan_cold_assist_enabled": bool(self.fan_cold_assist_enabled),
            "fan_cold_force_on_c": round(self.fan_cold_force_on_c, 2),
            "fan_cold_force_min_pct": round(self.fan_cold_force_min_pct, 1),
            "fan_persist_enabled": bool(self.fan_persist_enabled),
            "fan_persist_sample_s": round(self.fan_persist_sample_s, 2),
            "fan_persist_rise_c": round(self.fan_persist_rise_c, 3),
            "fan_persist_run_s": round(self.fan_persist_run_s, 2),
            "fan_persist_min_pct": round(self.fan_persist_min_pct, 1),
            "fan_persist_active": bool(self._fan_persist_run_ms > 0.0),
            "fan_persist_wait_s": round(self._fan_persist_wait_ms / 1000.0, 2),
            "charge_enabled": bool(self.charge_gate.value()),
            "run_mode": self.run_mode,
            "manual_charge_enable": bool(self.manual_charge_enable),
            "manual_discharge_enable": bool(self.manual_discharge_enable),
            "discharge_target_v": round(self.discharge_target_v, 3),
            "discharge_undershoot_v": round(self.discharge_undershoot_v, 3),
            "discharge_rebound_tol_v": round(self.discharge_rebound_tol_v, 3),
            "discharge_rest_s": round(self.discharge_rest_s, 2),
            "discharge_state": self.discharge_state,
            "discharge_last_cutoff_v": round(self.discharge_last_cutoff_v, 3),
            "discharge_last_rebound_v": round(self.discharge_last_rebound_v, 3),
            "active_preset": self.active_preset,
            "preset_target_v": round(preset_target_v, 3) if preset_target_v is not None else None,
            "preset_storagecharge_v": round(self.preset_storagecharge_v, 3),
            "preset_hotready_v": round(self.preset_hotready_v, 3),
            "preset_user1_v": round(self.preset_user1_v, 3),
            "preset_user2_v": round(self.preset_user2_v, 3),
            "source_stop_detect_enabled": bool(self.source_stop_detect_enabled),
            "source_present_min_current_a": round(self.min_charge_current_a, 3),
            "source_stop_confirm_s": round(self.source_stop_confirm_s, 2),
            "source_stopped": bool(self.source_stopped),
            "charge_hold_reason": self.charge_hold_reason,
            "fault_latched": bool(self.fault_latched),
            "last_fault": self.last_fault,
            "cutoff_voltage_enabled": bool(self.cutoff_voltage_enabled),
            "min_current_enabled": bool(self.min_current_enabled),
            "cutoff_temp_enabled": bool(self.cutoff_temp_enabled),
            "cutoff_voltage_v": round(self.cutoff_voltage_v, 3),
            "min_charge_current_a": round(self.min_charge_current_a, 3),
            "abort_latched": bool(self.abort_latched),
            "cooldown_enabled": bool(self.cooldown_enabled),
            "cooldown_active": bool(self.cooldown_active),
            "cooldown_temp_delta_c": round(self.cooldown_temp_delta_c, 3),
            "cooldown_stable_s": round(self.cooldown_stable_s, 2),
            "cooldown_stable_progress_s": round(self._cooldown_stable_ms / 1000.0, 2),
            "cumulative_ah": round(self.cumulative_ah, 5),
            "cumulative_wh": round(self.cumulative_wh, 5),
            "uptime_s": time.ticks_ms() // 1000,
            "obi_enabled": bool(self.obi is not None),
            "obi_pins": "GP18=data, GP19=enable",
            "obi": self.obi_snapshot,
        }
        return self.telemetry


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Pico W Makita Charger</title>
  <style>
    body { font-family: sans-serif; margin: 20px; background: #0b0f14; color: #e5eef8; }
    .card { background: #121922; border: 1px solid #2b3441; border-radius: 10px; padding: 16px; margin-bottom: 12px; }
    button { margin-right: 8px; padding: 8px 12px; border-radius: 8px; border: none; cursor: pointer; }
    .on { background: #4caf50; color: #fff; }
    .off { background: #c62828; color: #fff; }
    input { width: 90px; margin-right: 8px; }
    code { color: #8bd5ff; }
    .row { margin-bottom: 10px; }
    canvas { width: 100%%; max-width: 900px; height: 220px; border: 1px solid #2b3441; border-radius: 8px; background: #0a0f16; }
  </style>
</head>
<body>
  <h2>Pico W Makita Clone Charger</h2>
  <div class="card">
    <div><b>System:</b> <code id="sys"></code></div>
    <div><b>Power:</b> <code>DC rails via isolators (not sensed on Pico)</code></div>
    <div><b>Battery (Therm):</b> <code id="batttherm"></code> — Therm R: <code id="thermr"></code></div>
    <div><b>Presence Gate:</b> <code id="battgate"></code></div>
    <div><b>Therm Override:</b> <code id="thovr"></code></div>
    <div><b>V Sensor:</b> <code id="vsok"></code> | <b>I Sensor:</b> <code id="isok"></code> | <b>T Sensor:</b> <code id="tsok"></code></div>
    <div><b>Anomaly:</b> <code id="anom"></code></div>
    <div><b>Fan:</b> <code id="fanstate"></code></div>
  </div>
  <div class="card">
    <div><b>Open Battery Information (OBI)</b> — <code id="obipins"></code></div>
    <div>Pack (BMS): <code id="obipack"></code> V | Cells: <code id="obicells"></code></div>
    <div>Temp: <code id="obitemp"></code> °C | <button type="button" class="on" onclick="readObi()">Read BMS now</button></div>
    <div><small id="obierr"></small></div>
  </div>
  <div class="card">
    <div>Voltage: <code id="v"></code> V</div>
    <div>Current: <code id="i"></code> A</div>
    <div>Temp: <code id="t"></code> C</div>
    <div>Peak Temp: <code id="tpeak"></code> C</div>
    <div>Temp Limit: <code id="tmax"></code> C</div>
    <div>Thermal Charge Cutoff: <code id="thard"></code> C</div>
    <div>Fan: <code id="f"></code> % | RPM: <code id="frpm"></code></div>
    <div>Cooldown: <code id="cool"></code> (<code id="coolp"></code> s)</div>
    <div>Source Detect: <code id="srcdet"></code> / Source Stopped: <code id="srcstop"></code></div>
    <div>Fault: <code id="fault"></code></div>
    <div>Charge Enabled: <code id="charge"></code></div>
    <div>Cumulative Ah: <code id="ah"></code></div>
    <div>Cumulative Wh: <code id="wh"></code></div>
  </div>
  <div class="card">
    <button onclick="setMode('charge')">Mode Charge</button>
    <button onclick="setMode('discharge')">Mode Discharge</button>
    <button class="on" onclick="setCharge(true)">Charge ON</button>
    <button class="off" onclick="setCharge(false)">Charge OFF</button>
    <button onclick="setDischarge(true)">Discharge ON</button>
    <button onclick="setDischarge(false)">Discharge OFF</button>
    <button class="off" onclick="abortNow()">ABORT</button>
    <button onclick="clearAbort()">Clear Abort</button>
    <button onclick="setPreset('storagecharge')">Preset Storage</button>
    <button onclick="setPreset('hotready')">Preset HotReady</button>
    <button onclick="setPreset('user1')">Preset User1</button>
    <button onclick="setPreset('user2')">Preset User2</button>
    <button onclick="setPreset('none')">Preset None</button>
    <button onclick="finishTone()">Finish Melody</button>
    <button onclick="startTone()">Start Beep</button>
  </div>
  <div class="card">
    <div class="row">
      <button onclick="setFanEnabled(true)">Fan Enable</button>
      <button onclick="setFanEnabled(false)">Fan Disable</button>
      <button onclick="setFanAuto(true)">Fan Auto</button>
      <button onclick="setFanAuto(false)">Fan Manual</button>
    </div>
    <div class="row">
      <label>Manual Fan %%:</label>
      <input id="fanpct" type="number" min="0" max="100" />
      <button onclick="setFanOverride()">Set Manual</button>
    </div>
  </div>
  <div class="card">
    <div class="row">
      <label>V cutoff:</label><input id="cutv" type="number" step="0.01" />
      <label>I minimum:</label><input id="cuti" type="number" step="0.01" />
      <label>Max Temp:</label><input id="maxt" type="number" step="0.1" />
    </div>
    <div class="row">
      <label>Cooldown dT:</label><input id="cooldt" type="number" step="0.01" />
      <label>Cooldown stable s:</label><input id="coolsec" type="number" step="1" />
    </div>
    <div class="row">
      <label>D target V:</label><input id="dtgt" type="number" step="0.01" />
      <label>D undershoot V:</label><input id="dund" type="number" step="0.01" />
      <label>D rebound tol V:</label><input id="drbt" type="number" step="0.01" />
      <label>D rest s:</label><input id="drst" type="number" step="0.1" />
    </div>
    <div class="row">
      <label>Fan sample s:</label><input id="fpsmp" type="number" step="1" />
      <label>Fan rise C:</label><input id="fprse" type="number" step="0.01" />
      <label>Fan run s:</label><input id="fprun" type="number" step="1" />
      <label>Cold-on C:</label><input id="fcold" type="number" step="0.1" />
      <button onclick="setFanPersist(true)">Fan Persist On</button>
      <button onclick="setFanPersist(false)">Fan Persist Off</button>
      <button onclick="setColdAssist(true)">Cold Assist On</button>
      <button onclick="setColdAssist(false)">Cold Assist Off</button>
      <button onclick="setBatteryGate(true)">Batt Gate On</button>
      <button onclick="setBatteryGate(false)">Batt Gate Off</button>
      <button onclick="setBatteryOverride(true)">Batt Override On</button>
      <button onclick="setBatteryOverride(false)">Batt Override Off</button>
      <button onclick="setThermOverride(true)">Therm Override On</button>
      <button onclick="setThermOverride(false)">Therm Override Off</button>
    </div>
    <div class="row">
      <label>Src min I A:</label><input id="srcmini" type="number" step="0.01" />
      <label>Src stop s:</label><input id="srcstops" type="number" step="0.5" />
    </div>
    <div class="row">
      <label>Storage V:</label><input id="pvstor" type="number" step="0.01" />
      <label>HotReady V:</label><input id="pvhot" type="number" step="0.01" />
      <label>User1 V:</label><input id="pv1" type="number" step="0.01" />
      <label>User2 V:</label><input id="pv2" type="number" step="0.01" />
    </div>
    <div class="row">
      <button onclick="setConfig()">Apply Limits</button>
      <button onclick="setCutoffEnable('v',true)">V Cutoff On</button>
      <button onclick="setCutoffEnable('v',false)">V Cutoff Off</button>
      <button onclick="setCutoffEnable('i',true)">I Min On</button>
      <button onclick="setCutoffEnable('i',false)">I Min Off</button>
      <button onclick="setCutoffEnable('t',true)">T Cutoff On</button>
      <button onclick="setCutoffEnable('t',false)">T Cutoff Off</button>
      <button onclick="setSourceDetect(true)">Src Detect On</button>
      <button onclick="setSourceDetect(false)">Src Detect Off</button>
      <button onclick="setCooldown(true)">Cooldown On</button>
      <button onclick="setCooldown(false)">Cooldown Off</button>
      <button onclick="resetEnergy()">Reset Ah/Wh</button>
    </div>
  </div>
  <div class="card">
    <div class="row">Voltage/Current</div>
    <canvas id="vi"></canvas>
  </div>
  <div class="card">
    <div class="row">Cumulative Ah/Wh</div>
    <canvas id="ew"></canvas>
  </div>
  <script>
    const hist = { t: [], v: [], i: [], ah: [], wh: [] };
    const MAX_POINTS = 240;

    async function api(path, body) {
      const r = await fetch(path, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body || {}) });
      return await r.json();
    }

    function pushHist(d) {
      const now = Date.now() / 1000;
      hist.t.push(now);
      hist.v.push(Number(d.v_batt));
      hist.i.push(Number(d.i_batt));
      hist.ah.push(Number(d.cumulative_ah));
      hist.wh.push(Number(d.cumulative_wh));
      while (hist.t.length > MAX_POINTS) {
        hist.t.shift(); hist.v.shift(); hist.i.shift(); hist.ah.shift(); hist.wh.shift();
      }
    }

    function drawSeries(canvasId, s1, s2, c1, c2) {
      const cv = document.getElementById(canvasId);
      const ctx = cv.getContext("2d");
      const w = cv.width = cv.clientWidth;
      const h = cv.height = cv.clientHeight;
      ctx.clearRect(0, 0, w, h);
      if (s1.length < 2) return;

      let mn = Math.min(...s1, ...s2);
      let mx = Math.max(...s1, ...s2);
      if (mx <= mn) { mx = mn + 1; }
      const pad = 10;
      const sx = (w - 2 * pad) / (s1.length - 1);
      const sy = (h - 2 * pad) / (mx - mn);
      function py(v) { return h - pad - (v - mn) * sy; }
      function draw(arr, color) {
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        for (let k = 0; k < arr.length; k++) {
          const x = pad + k * sx;
          const y = py(arr[k]);
          if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      draw(s1, c1);
      draw(s2, c2);
      ctx.fillStyle = "#aab7c8";
      ctx.fillText(`min ${mn.toFixed(2)}  max ${mx.toFixed(2)}`, 10, 14);
    }

    function redraw() {
      drawSeries("vi", hist.v, hist.i, "#6ee7ff", "#fda4af");
      drawSeries("ew", hist.ah, hist.wh, "#86efac", "#fcd34d");
    }

    async function poll() {
      const r = await fetch("/api/status");
      const d = await r.json();
      v.textContent = d.v_batt;
      i.textContent = d.i_batt;
      t.textContent = (d.t_batt_c != null && d.t_batt_c !== undefined) ? d.t_batt_c : "—";
      batttherm.textContent = d.battery_attached_therm ? "attached/live" : "not-detected";
      thermr.textContent = (d.thermistor_ohm != null && d.thermistor_ohm !== undefined) ? (d.thermistor_ohm >= 1000 ? (d.thermistor_ohm / 1000).toFixed(1) + "k" : d.thermistor_ohm) : "—";
      battgate.textContent = d.require_battery_present ? (d.battery_presence_override ? "required + force-present" : "required") : "not-required";
      thovr.textContent = d.thermistor_override ? "on (thermal + battery-detect bypass)" : (d.thermistor_usable ? "off (10k NTC detected)" : "off (awaiting pack / open leads)");
      vsok.textContent = d.v_sensor_ok ? "ok" : "check";
      isok.textContent = d.i_sensor_ok ? "ok" : "check";
      tsok.textContent = d.t_batt_valid ? (d.t_sensor_ok ? "ok" : "check") : "n/a";
      if (d.voltage_anomaly && d.current_anomaly) anom.textContent = "voltage+current over nominal";
      else if (d.voltage_anomaly) anom.textContent = "voltage over nominal";
      else if (d.current_anomaly) anom.textContent = "current over nominal";
      else anom.textContent = "none";
      const fanMode = d.fan_enabled ? (d.fan_auto_mode ? "enabled/auto" : "enabled/manual") : "disabled";
      const fanPersist = d.fan_persist_enabled ? (d.fan_persist_active ? "persist-active" : "persist-idle") : "persist-off";
      const coldAssist = d.fan_cold_assist_enabled ? `cold-assist<=${d.fan_cold_force_on_c}C` : "cold-assist-off";
      fanstate.textContent = d.fan_tach_enabled ? `${fanMode}, tach, ${fanPersist}, ${coldAssist}` : `${fanMode}, pwm-est, ${fanPersist}, ${coldAssist}`;
      obipins.textContent = d.obi_enabled ? (d.obi_pins || "GP18/GP19") : "disabled (missing obi.py)";
      const ob = d.obi;
      if (ob && !ob.error) {
        obipack.textContent = ob.pack_v != null ? ob.pack_v : "—";
        obicells.textContent = Array.isArray(ob.cells_v) ? ob.cells_v.map(x => x.toFixed(3)).join(", ") : "—";
        obitemp.textContent = ob.temp_c != null ? ob.temp_c : "—";
        obierr.textContent = "";
      } else if (ob && ob.error) {
        obipack.textContent = "—";
        obicells.textContent = "—";
        obitemp.textContent = "—";
        obierr.textContent = ob.error;
      } else {
        obipack.textContent = "—";
        obicells.textContent = "—";
        obitemp.textContent = "—";
        obierr.textContent = d.obi_enabled ? "waiting for first poll…" : "";
      }
      tpeak.textContent = (d.peak_temp_c != null && d.peak_temp_c !== undefined) ? d.peak_temp_c : "—";
      tmax.textContent = d.max_temp_limit_c;
      thard.textContent = d.thermal_charge_cutoff_c;
      f.textContent = d.fan_pct;
      frpm.textContent = d.fan_rpm_estimated ? `${d.fan_rpm} est` : d.fan_rpm;
      cool.textContent = d.cooldown_active ? "active" : "idle";
      coolp.textContent = d.cooldown_stable_progress_s;
      srcdet.textContent = d.source_stop_detect_enabled ? "on" : "off";
      srcstop.textContent = d.source_stopped ? "yes" : "no";
      fault.textContent = d.fault_latched ? d.last_fault : "none";
      charge.textContent = d.charge_enabled;
      ah.textContent = d.cumulative_ah;
      wh.textContent = d.cumulative_wh;
      if (!document.activeElement || document.activeElement.id !== "cutv") cutv.value = d.cutoff_voltage_v;
      if (!document.activeElement || document.activeElement.id !== "cuti") cuti.value = d.min_charge_current_a;
      if (!document.activeElement || document.activeElement.id !== "maxt") maxt.value = d.max_temp_limit_c;
      if (!document.activeElement || document.activeElement.id !== "cooldt") cooldt.value = d.cooldown_temp_delta_c;
      if (!document.activeElement || document.activeElement.id !== "coolsec") coolsec.value = d.cooldown_stable_s;
      if (!document.activeElement || document.activeElement.id !== "srcmini") srcmini.value = d.min_charge_current_a;
      if (!document.activeElement || document.activeElement.id !== "srcstops") srcstops.value = d.source_stop_confirm_s;
      if (!document.activeElement || document.activeElement.id !== "pvstor") pvstor.value = d.preset_storagecharge_v;
      if (!document.activeElement || document.activeElement.id !== "pvhot") pvhot.value = d.preset_hotready_v;
      if (!document.activeElement || document.activeElement.id !== "pv1") pv1.value = d.preset_user1_v;
      if (!document.activeElement || document.activeElement.id !== "pv2") pv2.value = d.preset_user2_v;
      if (!document.activeElement || document.activeElement.id !== "fpsmp") fpsmp.value = d.fan_persist_sample_s;
      if (!document.activeElement || document.activeElement.id !== "fprse") fprse.value = d.fan_persist_rise_c;
      if (!document.activeElement || document.activeElement.id !== "fprun") fprun.value = d.fan_persist_run_s;
      if (!document.activeElement || document.activeElement.id !== "fcold") fcold.value = d.fan_cold_force_on_c;
      if (d.run_mode === "discharge") {
        sys.textContent = `${d.system_state} (target ${d.discharge_target_v}V, rebound ${d.discharge_last_rebound_v}V, ${d.charge_hold_reason})`;
      } else if (d.active_preset && d.active_preset !== "none") {
        sys.textContent = `${d.system_state} (${d.active_preset} @ ${d.preset_target_v}V, ${d.charge_hold_reason})`;
      } else {
        sys.textContent = `${d.system_state} (${d.charge_hold_reason})`;
      }
      if (!document.activeElement || document.activeElement.id !== "dtgt") dtgt.value = d.discharge_target_v;
      if (!document.activeElement || document.activeElement.id !== "dund") dund.value = d.discharge_undershoot_v;
      if (!document.activeElement || document.activeElement.id !== "drbt") drbt.value = d.discharge_rebound_tol_v;
      if (!document.activeElement || document.activeElement.id !== "drst") drst.value = d.discharge_rest_s;
      pushHist(d);
      redraw();
    }
    async function setMode(mode) { await api("/api/mode", {mode}); }
    async function setCharge(on) { await api("/api/charge", {enabled:on}); }
    async function setDischarge(on) { await api("/api/discharge", {enabled:on}); }
    async function abortNow() { await api("/api/abort", {abort:true}); }
    async function clearAbort() { await api("/api/abort", {abort:false}); }
    async function setFanEnabled(on) { await api("/api/fan_enable", {enabled:on}); }
    async function setFanAuto(on) { await api("/api/fan_mode", {auto:on}); }
    async function setFanOverride() {
      const v = Number(document.getElementById("fanpct").value);
      await api("/api/fan_override", {fan_pct:v});
    }
    async function setConfig() {
      await api("/api/config", {
        cutoff_voltage_v: Number(cutv.value),
        min_charge_current_a: Number(cuti.value),
        max_temp_limit_c: Number(maxt.value),
        cooldown_temp_delta_c: Number(cooldt.value),
        cooldown_stable_s: Number(coolsec.value),
        source_present_min_current_a: Number(srcmini.value),
        source_stop_confirm_s: Number(srcstops.value),
        preset_storagecharge_v: Number(pvstor.value),
        preset_hotready_v: Number(pvhot.value),
        preset_user1_v: Number(pv1.value),
        preset_user2_v: Number(pv2.value),
        discharge_target_v: Number(dtgt.value),
        discharge_undershoot_v: Number(dund.value),
        discharge_rebound_tol_v: Number(drbt.value),
        discharge_rest_s: Number(drst.value),
        fan_persist_sample_s: Number(fpsmp.value),
        fan_persist_rise_c: Number(fprse.value),
        fan_persist_run_s: Number(fprun.value),
        fan_cold_force_on_c: Number(fcold.value)
      });
    }
    async function setCutoffEnable(which, on) {
      const body = {};
      if (which === "v") body.cutoff_voltage_enabled = on;
      if (which === "i") body.min_current_enabled = on;
      if (which === "t") body.cutoff_temp_enabled = on;
      await api("/api/config", body);
    }
    async function resetEnergy() { await api("/api/reset_energy", {}); }
    async function setSourceDetect(on) { await api("/api/config", {source_stop_detect_enabled:on}); }
    async function setCooldown(on) { await api("/api/config", {cooldown_enabled:on}); }
    async function setFanPersist(on) { await api("/api/config", {fan_persist_enabled:on}); }
    async function setColdAssist(on) { await api("/api/config", {fan_cold_assist_enabled:on}); }
    async function setBatteryGate(on) { await api("/api/config", {require_battery_present:on}); }
    async function setBatteryOverride(on) { await api("/api/config", {battery_presence_override:on}); }
    async function setThermOverride(on) { await api("/api/config", {thermistor_override:on}); }
    async function setPreset(name) { await api("/api/preset", {preset:name}); }
    async function finishTone() { await api("/api/tone", {name:"finish"}); }
    async function startTone() { await api("/api/tone", {name:"start"}); }
    async function readObi() {
      try {
        const r = await fetch("/api/obi/read", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
        const j = await r.json();
        if (j.ok) poll();
        else obierr.textContent = j.error || "read failed";
      } catch (e) { obierr.textContent = String(e); }
    }
    setInterval(poll, 1000);
    window.addEventListener("resize", redraw);
    poll();
  </script>
</body>
</html>
"""


def parse_http_request(raw):
    lines = raw.split("\r\n")
    first = lines[0].split(" ")
    method = first[0] if len(first) > 0 else ""
    path = first[1] if len(first) > 1 else "/"
    body = ""
    if "\r\n\r\n" in raw:
        body = raw.split("\r\n\r\n", 1)[1]
    return method, path, body


async def send_json(writer, obj, status="200 OK"):
    data = json.dumps(obj)
    writer.write(("HTTP/1.1 %s\r\n" % status).encode())
    writer.write(b"Content-Type: application/json\r\n")
    writer.write(("Content-Length: %d\r\n" % len(data)).encode())
    writer.write(b"Connection: close\r\n\r\n")
    writer.write(data.encode())
    await writer.drain()


async def send_html(writer, html):
    writer.write(b"HTTP/1.1 200 OK\r\n")
    writer.write(b"Content-Type: text/html\r\n")
    writer.write(("Content-Length: %d\r\n" % len(html)).encode())
    writer.write(b"Connection: close\r\n\r\n")
    writer.write(html.encode())
    await writer.drain()


async def handle_client(reader, writer, ctrl):
    try:
        raw = await reader.read(4096)
        if not raw:
            await writer.wait_closed()
            return
        # MicroPython bytes.decode() does not support errors= keyword (CPython does).
        try:
            req = raw.decode()
        except Exception:
            req = ""
        method, path, body = parse_http_request(req)

        if method == "GET" and path == "/":
            await send_html(writer, HTML)
        elif method == "GET" and path == "/api/status":
            await send_json(writer, ctrl.telemetry if ctrl.telemetry else ctrl.evaluate())
        elif method == "POST" and path == "/api/charge":
            payload = json.loads(body or "{}")
            enable = bool(payload.get("enabled", False))
            if enable and ctrl.require_battery_present and (not ctrl.battery_presence_override):
                if (not ctrl.thermistor_override) and (not ctrl.read_battery_therm_detection()):
                    await send_json(writer, {"ok": False, "error": "battery_not_present"}, status="400 Bad Request")
                    return
            ctrl.manual_charge_enable = enable
            if ctrl.manual_charge_enable:
                ctrl.run_mode = "charge"
            await send_json(writer, {"ok": True, "manual_charge_enable": ctrl.manual_charge_enable})
        elif method == "POST" and path == "/api/discharge":
            payload = json.loads(body or "{}")
            enable = bool(payload.get("enabled", False))
            if enable and ctrl.require_battery_present and (not ctrl.battery_presence_override):
                if (not ctrl.thermistor_override) and (not ctrl.read_battery_therm_detection()):
                    await send_json(writer, {"ok": False, "error": "battery_not_present"}, status="400 Bad Request")
                    return
            ctrl.manual_discharge_enable = enable
            if ctrl.manual_discharge_enable:
                ctrl.run_mode = "discharge"
                ctrl.manual_charge_enable = False
                ctrl.discharge_state = "idle"
            await send_json(writer, {"ok": True, "manual_discharge_enable": ctrl.manual_discharge_enable})
        elif method == "POST" and path == "/api/mode":
            payload = json.loads(body or "{}")
            mode = str(payload.get("mode", "charge"))
            if mode not in ("charge", "discharge"):
                await send_json(writer, {"ok": False, "error": "invalid_mode"}, status="400 Bad Request")
            else:
                ctrl.run_mode = mode
                if mode == "charge":
                    ctrl.manual_discharge_enable = False
                    ctrl.discharge_state = "idle"
                else:
                    ctrl.manual_charge_enable = False
                await send_json(writer, {"ok": True, "run_mode": ctrl.run_mode})
        elif method == "POST" and path == "/api/abort":
            payload = json.loads(body or "{}")
            ctrl.abort_latched = bool(payload.get("abort", True))
            if ctrl.abort_latched:
                ctrl.manual_charge_enable = False
                ctrl.manual_discharge_enable = False
                ctrl.set_charge(False)
            await send_json(writer, {"ok": True, "abort_latched": ctrl.abort_latched})
        elif method == "POST" and path == "/api/fan_enable":
            payload = json.loads(body or "{}")
            ctrl.fan_enabled = bool(payload.get("enabled", True))
            if not ctrl.fan_enabled:
                ctrl.set_fan_pct(0.0)
            await send_json(writer, {"ok": True, "fan_enabled": ctrl.fan_enabled})
        elif method == "POST" and path == "/api/fan_mode":
            payload = json.loads(body or "{}")
            ctrl.fan_auto_mode = bool(payload.get("auto", True))
            await send_json(writer, {"ok": True, "fan_auto_mode": ctrl.fan_auto_mode})
        elif method == "POST" and path == "/api/preset":
            payload = json.loads(body or "{}")
            preset = str(payload.get("preset", "none"))
            if preset not in ("none", "storagecharge", "hotready", "user1", "user2"):
                await send_json(writer, {"ok": False, "error": "invalid_preset"}, status="400 Bad Request")
            else:
                ctrl.active_preset = preset
                if preset == "none":
                    ctrl.charge_hold_reason = "preset_cleared"
                await send_json(writer, {"ok": True, "active_preset": ctrl.active_preset})
        elif method == "POST" and path == "/api/fan_override":
            payload = json.loads(body or "{}")
            val = payload.get("fan_pct", None)
            if val is None:
                ctrl.fan_override_pct = None
            else:
                ctrl.fan_override_pct = max(0.0, min(100.0, float(val)))
                ctrl.fan_auto_mode = False
            await send_json(writer, {"ok": True, "fan_override_pct": ctrl.fan_override_pct})
        elif method == "POST" and path == "/api/config":
            payload = json.loads(body or "{}")
            if "cutoff_voltage_v" in payload:
                ctrl.cutoff_voltage_v = max(1.0, float(payload["cutoff_voltage_v"]))
            # Backward-compatible key: cutoff_current_a now maps to minimum charge current.
            if "cutoff_current_a" in payload:
                ctrl.min_charge_current_a = max(0.01, min(20.0, float(payload["cutoff_current_a"])))
                ctrl.source_present_min_current_a = ctrl.min_charge_current_a
            if "min_charge_current_a" in payload:
                ctrl.min_charge_current_a = max(0.01, min(20.0, float(payload["min_charge_current_a"])))
                ctrl.source_present_min_current_a = ctrl.min_charge_current_a
            if "max_temp_limit_c" in payload:
                ctrl.max_temp_limit_c = max(-20.0, min(120.0, float(payload["max_temp_limit_c"])))
            if "cutoff_voltage_enabled" in payload:
                ctrl.cutoff_voltage_enabled = bool(payload["cutoff_voltage_enabled"])
            # Backward-compatible key: cutoff_current_enabled now maps to min-current supervision.
            if "cutoff_current_enabled" in payload:
                ctrl.min_current_enabled = bool(payload["cutoff_current_enabled"])
            if "min_current_enabled" in payload:
                ctrl.min_current_enabled = bool(payload["min_current_enabled"])
            if "cutoff_temp_enabled" in payload:
                ctrl.cutoff_temp_enabled = bool(payload["cutoff_temp_enabled"])
            if "cooldown_enabled" in payload:
                ctrl.cooldown_enabled = bool(payload["cooldown_enabled"])
                if not ctrl.cooldown_enabled:
                    ctrl.cooldown_active = False
                    ctrl._cooldown_stable_ms = 0.0
            if "cooldown_temp_delta_c" in payload:
                ctrl.cooldown_temp_delta_c = max(0.005, min(2.0, float(payload["cooldown_temp_delta_c"])))
            if "cooldown_stable_s" in payload:
                ctrl.cooldown_stable_s = max(1.0, min(600.0, float(payload["cooldown_stable_s"])))
            if "source_stop_detect_enabled" in payload:
                ctrl.source_stop_detect_enabled = bool(payload["source_stop_detect_enabled"])
            if "source_present_min_current_a" in payload:
                ctrl.source_present_min_current_a = max(0.01, min(20.0, float(payload["source_present_min_current_a"])))
                ctrl.min_charge_current_a = ctrl.source_present_min_current_a
            if "source_stop_confirm_s" in payload:
                ctrl.source_stop_confirm_s = max(0.5, min(120.0, float(payload["source_stop_confirm_s"])))
            if "preset_storagecharge_v" in payload:
                ctrl.preset_storagecharge_v = max(1.0, min(40.0, float(payload["preset_storagecharge_v"])))
            if "preset_hotready_v" in payload:
                ctrl.preset_hotready_v = max(1.0, min(40.0, float(payload["preset_hotready_v"])))
            if "preset_user1_v" in payload:
                ctrl.preset_user1_v = max(1.0, min(40.0, float(payload["preset_user1_v"])))
            if "preset_user2_v" in payload:
                ctrl.preset_user2_v = max(1.0, min(40.0, float(payload["preset_user2_v"])))
            if "discharge_target_v" in payload:
                ctrl.discharge_target_v = max(1.0, min(40.0, float(payload["discharge_target_v"])))
            if "discharge_undershoot_v" in payload:
                ctrl.discharge_undershoot_v = max(0.0, min(1.0, float(payload["discharge_undershoot_v"])))
            if "discharge_rebound_tol_v" in payload:
                ctrl.discharge_rebound_tol_v = max(0.001, min(1.0, float(payload["discharge_rebound_tol_v"])))
            if "discharge_rest_s" in payload:
                ctrl.discharge_rest_s = max(0.2, min(120.0, float(payload["discharge_rest_s"])))
            if "fan_persist_enabled" in payload:
                ctrl.fan_persist_enabled = bool(payload["fan_persist_enabled"])
            if "fan_persist_sample_s" in payload:
                ctrl.fan_persist_sample_s = max(5.0, min(1800.0, float(payload["fan_persist_sample_s"])))
            if "fan_persist_rise_c" in payload:
                ctrl.fan_persist_rise_c = max(0.01, min(5.0, float(payload["fan_persist_rise_c"])))
            if "fan_persist_run_s" in payload:
                ctrl.fan_persist_run_s = max(1.0, min(600.0, float(payload["fan_persist_run_s"])))
            if "fan_cold_assist_enabled" in payload:
                ctrl.fan_cold_assist_enabled = bool(payload["fan_cold_assist_enabled"])
            if "fan_cold_force_on_c" in payload:
                ctrl.fan_cold_force_on_c = max(-40.0, min(40.0, float(payload["fan_cold_force_on_c"])))
            if "require_battery_present" in payload:
                ctrl.require_battery_present = bool(payload["require_battery_present"])
            if "battery_presence_override" in payload:
                ctrl.battery_presence_override = bool(payload["battery_presence_override"])
            if "thermistor_override" in payload:
                ctrl.thermistor_override = bool(payload["thermistor_override"])
            await send_json(
                writer,
                {
                    "ok": True,
                    "cutoff_voltage_v": ctrl.cutoff_voltage_v,
                    "cutoff_current_a": ctrl.min_charge_current_a,
                    "min_charge_current_a": ctrl.min_charge_current_a,
                    "max_temp_limit_c": ctrl.max_temp_limit_c,
                    "cutoff_voltage_enabled": ctrl.cutoff_voltage_enabled,
                    "cutoff_current_enabled": ctrl.min_current_enabled,
                    "min_current_enabled": ctrl.min_current_enabled,
                    "cutoff_temp_enabled": ctrl.cutoff_temp_enabled,
                    "cooldown_enabled": ctrl.cooldown_enabled,
                    "cooldown_temp_delta_c": ctrl.cooldown_temp_delta_c,
                    "cooldown_stable_s": ctrl.cooldown_stable_s,
                    "source_stop_detect_enabled": ctrl.source_stop_detect_enabled,
                    "source_present_min_current_a": ctrl.min_charge_current_a,
                    "source_stop_confirm_s": ctrl.source_stop_confirm_s,
                    "active_preset": ctrl.active_preset,
                    "preset_storagecharge_v": ctrl.preset_storagecharge_v,
                    "preset_hotready_v": ctrl.preset_hotready_v,
                    "preset_user1_v": ctrl.preset_user1_v,
                    "preset_user2_v": ctrl.preset_user2_v,
                    "discharge_target_v": ctrl.discharge_target_v,
                    "discharge_undershoot_v": ctrl.discharge_undershoot_v,
                    "discharge_rebound_tol_v": ctrl.discharge_rebound_tol_v,
                    "discharge_rest_s": ctrl.discharge_rest_s,
                    "fan_persist_enabled": ctrl.fan_persist_enabled,
                    "fan_persist_sample_s": ctrl.fan_persist_sample_s,
                    "fan_persist_rise_c": ctrl.fan_persist_rise_c,
                    "fan_persist_run_s": ctrl.fan_persist_run_s,
                    "fan_cold_assist_enabled": ctrl.fan_cold_assist_enabled,
                    "fan_cold_force_on_c": ctrl.fan_cold_force_on_c,
                    "require_battery_present": ctrl.require_battery_present,
                    "battery_presence_override": ctrl.battery_presence_override,
                    "thermistor_override": ctrl.thermistor_override,
                },
            )
        elif method == "POST" and path == "/api/obi/read":
            if not OBI_AVAILABLE or ctrl.obi is None:
                await send_json(writer, {"ok": False, "error": "obi_not_configured"}, status="400 Bad Request")
            else:
                try:
                    r = ctrl.obi.request(READ_DATA_REQUEST)
                    snap = parse_read_data_response(r)
                    ctrl.obi_snapshot = snap
                    ctrl._last_obi_tick = time.ticks_ms()
                    await send_json(writer, {"ok": True, "obi": snap})
                except Exception as ex:
                    await send_json(writer, {"ok": False, "error": str(ex)}, status="400 Bad Request")
        elif method == "POST" and path == "/api/reset_energy":
            ctrl.cumulative_ah = 0.0
            ctrl.cumulative_wh = 0.0
            await send_json(writer, {"ok": True})
        elif method == "POST" and path == "/api/tone":
            payload = json.loads(body or "{}")
            tone = payload.get("name", "")
            if tone == "start":
                await ctrl.play_start_beep()
                await send_json(writer, {"ok": True})
            elif tone == "finish":
                await ctrl.play_finish_melody()
                await send_json(writer, {"ok": True})
            else:
                await send_json(writer, {"ok": False, "error": "unknown_tone"}, status="400 Bad Request")
        else:
            await send_json(writer, {"ok": False, "error": "not_found"}, status="404 Not Found")
    except Exception as ex:
        await send_json(writer, {"ok": False, "error": "server_error", "detail": str(ex)}, status="500 Internal Server Error")
    finally:
        try:
            await writer.drain()
        except Exception:
            pass
        await writer.wait_closed()


def connect_wifi(ssid, password, timeout_s=15, static_ifconfig=None):
    """Connect STA. Optional static_ifconfig: (ip, netmask, gateway, dns) strings after link up."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        start = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
                raise RuntimeError("Wi-Fi connect timeout")
            time.sleep_ms(200)
    if static_ifconfig is not None:
        try:
            wlan.ifconfig(static_ifconfig)
        except Exception as ex:
            # Bad subnet or firmware quirk — stay on DHCP so lwIP still works for HTTP.
            print("Static IP apply failed, using DHCP:", ex)
    return wlan


def maybe_start_ota():
    if micropython_ota is None:
        return False
    # Provide your own server/repo credentials if used.
    # This call is deliberately optional so firmware boots even when OTA config is absent.
    return True


async def control_loop(ctrl):
    print("control_loop: telemetry every 250 ms on USB serial")
    # Let the other task run start_server() before first (heavy) evaluate().
    await asyncio.sleep_ms(20)
    while True:
        try:
            data = ctrl.evaluate()
            t_disp = data["t_batt_c"]
            t_str = ("{:.1f}C".format(t_disp)) if t_disp is not None else "n/a"
            print(
                "V={:.2f}V I={:.2f}A T={} Fan={:.0f}% Charge={} Fault={}".format(
                    data["v_batt"],
                    data["i_batt"],
                    t_str,
                    data["fan_pct"],
                    data["charge_enabled"],
                    data["last_fault"] if data["fault_latched"] else "none",
                )
            )
        except Exception as ex:
            print("evaluate() error:", ex)
        await asyncio.sleep_ms(250)


async def web_server(ctrl, host="0.0.0.0", port=80):
    # Nested handler avoids lambda quirks on some MicroPython builds.
    async def client_cb(reader, writer):
        await handle_client(reader, writer, ctrl)

    last_ex = None
    for port_try in (port, 8080):
        try:
            server = await asyncio.start_server(client_cb, host, port_try)
            print("Web server listening on http://{}:{}".format(host, port_try))
            if port_try != port:
                print("Note: using port {} (primary port {} failed earlier)".format(port_try, port))
            await server.wait_closed()
            return
        except Exception as ex:
            last_ex = ex
            print("HTTP bind port {} failed: {}".format(port_try, ex))
    print("Web server failed on all ports (telemetry continues):", last_ex)
    while True:
        await asyncio.sleep_ms(60000)


async def main():
    # Wi‑Fi: copy secrets.py.example → secrets.py on the Pico (gitignored), or set below for local dev only.
    try:
        from secrets import WIFI_SSID, WIFI_PASS
    except ImportError:
        WIFI_SSID = ""
        WIFI_PASS = ""

    STATIC_IP = "192.168.0.60"
    NETMASK = "255.255.255.0"
    GATEWAY = "192.168.0.1"
    DNS = "192.168.0.1"

    ctrl = ChargerController()
    ctrl.set_leds(red=False, green=True, yellow=False)  # green on steady from power-on
    await ctrl.play_start_beep()

    try:
        wlan = connect_wifi(
            WIFI_SSID,
            WIFI_PASS,
            static_ifconfig=(STATIC_IP, NETMASK, GATEWAY, DNS),
        )
        print("Wi-Fi IP (static):", wlan.ifconfig()[0])
    except Exception as ex:
        print("Wi-Fi unavailable:", ex)
        print("Open http://192.168.0.60 only works after Wi-Fi connects; check SSID/password.")

    maybe_start_ota()

    ctrl.set_leds(red=False, green=True, yellow=False)

    # uasyncio: asyncio.gather() can return early on some MP builds and end the whole program
    # (no telemetry, no HTTP). Keep main() alive with a forever sleep and use create_task.
    print("Starting telemetry + HTTP tasks...")
    asyncio.create_task(web_server(ctrl))
    asyncio.create_task(control_loop(ctrl))
    while True:
        await asyncio.sleep_ms(60000)


try:
    asyncio.run(main())
finally:
    # Always fail safe on reboot/crash
    Pin(2, Pin.OUT, value=0)
    pwm = PWM(Pin(3))
    pwm.duty_u16(0)
    pwm.deinit()
