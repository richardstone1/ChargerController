/**
 * ATtiny1616 witness MCU — Makita OBI bridge + local cell/NTC sense.
 *
 * OBI protocol derived from Open Battery Information (Martin Jansson, MIT).
 * See ../../CREDITS.md and ../jtag2updi for programming.
 */
#include <Arduino.h>
#include "witness_config.h"
#include "makita_onewire.h"
#include "obi_host.h"
#include "adc_sense.h"

MakitaOneWire gOw(PIN_ONEWIRE);
MakitaEnable gEn(PIN_ENABLE);
ObiHost gHost(gOw, gEn);
AdcSense gAdc;

static WitnessAnalog gLast;

static void ledsBegin() {
    pinMode(PIN_LED_OK, OUTPUT);
    digitalWrite(PIN_LED_OK, HIGH);
}

static void ledsUpdate(bool busActive) {
    (void)busActive;
    bool ok = true;
    for (uint8_t i = 0; i < 5; i++) {
        if (gLast.cells_v[i] < 2.5f || gLast.cells_v[i] > 4.35f) {
            ok = false;
        }
    }
    digitalWrite(PIN_LED_OK, ok ? LOW : HIGH);
}

void setup() {
    ledsBegin();
    gAdc.begin();
    gHost.begin(OBI_BAUD);
    gLast = gAdc.sample();
}

void loop() {
    gHost.poll();

    static uint32_t lastSample = 0;
    if (millis() - lastSample >= 250) {
        lastSample = millis();
        gLast = gAdc.sample();
        ledsUpdate(false);
    }
}
