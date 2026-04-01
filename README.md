# ChargerController

Open-source **MicroPython** firmware for a **Raspberry Pi Pico W**–based Makita-style pack charger: web UI, telemetry, fan control, safety limits, and optional **Open Battery Information (OBI)** 1-Wire BMS access.

**License:** [MIT](LICENSE) — collaborative use and modification are encouraged.  
**Upstream credit:** OBI-related code traces to [Martin Jansson](https://github.com/mnh-jansson)’s [Open Battery Information](https://github.com/mnh-jansson/open-battery-information) project — see [CREDITS.md](CREDITS.md).

## Contributing

We welcome contributions. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [CREDITS.md](CREDITS.md). Add yourself to [CONTRIBUTORS.md](CONTRIBUTORS.md) when you contribute.

## Contents

| File | Description |
|------|-------------|
| `main.py` | Main firmware: ADC, Wi‑Fi, HTTP API, charger logic, embedded control UI |
| `obi.py` | OBI / Makita LXT 1-Wire bridge (GP18 data, GP19 enable by default) |
| `control.html` | Standalone/offline UI copy (optional; live UI is embedded in `main.py`) |

## Hardware (typical)

- **Pico W** — Wi‑Fi, web UI on port 80 (or 8080 fallback)
- Pack voltage / current / NTC — ADC on GP26–GP28 (see constants in `main.py`)
- **OBI** — GP18 = 1-Wire data (open-drain + pull-up), GP19 = enable

## Flashing

Copy `main.py` and `obi.py` to the Pico (e.g. Thonny). **Wi‑Fi:** copy `secrets.py.example` to `secrets.py` on the device and set `WIFI_SSID` / `WIFI_PASS` (see `.gitignore` — never commit `secrets.py`). Adjust `STATIC_IP` / gateway in `main()` if needed.

## Publishing to GitHub

See [GITHUB.md](GITHUB.md) for creating the **ChargerController** repository and pushing.
