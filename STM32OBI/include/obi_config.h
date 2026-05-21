#ifndef OBI_CONFIG_H
#define OBI_CONFIG_H

/**
 * Pin mapping for STM32 Blue Pill (bluepill_f103c8 / variant_PILL_F103Cx).
 *
 * Arduino Uno OBI (ArduinoOBI): ONEWIRE = D6 (ATmega PD6), ENABLE = D8 (ATmega PB0).
 *
 * On Blue Pill, abstract pin numbers 6 and 8 are PB3 and PA12 (USB D+) — avoid
 * using 8 for ENABLE. Defaults below mirror Uno intent:
 *   - ENABLE → PB0 (same port bit name as Uno D8)
 *   - ONEWIRE → PA6 (common breakout pin; rewire from Uno D6)
 *
 * Override with -DONEWIRE_PIN=… / -DENABLE_PIN=… in platformio.ini if needed.
 */

#ifndef ONEWIRE_PIN
#define ONEWIRE_PIN 26   /* PA6 — silkscreen A6 on many boards */
#endif

#ifndef ENABLE_PIN
#define ENABLE_PIN 28    /* PB0 — matches Uno D8 → ATmega PB0 */
#endif

#endif
