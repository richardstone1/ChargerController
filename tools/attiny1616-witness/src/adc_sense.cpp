#include "adc_sense.h"
#include "witness_config.h"
#include <math.h>

void AdcSense::begin() {
    analogReference(VDD);
    analogReadResolution(12);
}

float AdcSense::readCellVolts(pin_t pin) {
    const uint16_t raw = analogRead(digitalPinToAnalogInput(pin));
    const float vAdc = (raw * (ADC_VREF_MV / 1000.0f)) / 4095.0f;
    const float scale = (float)(CELL_DIV_RTOP_OHM + CELL_DIV_RBOT_OHM) / (float)CELL_DIV_RBOT_OHM;
    return vAdc * scale;
}

float AdcSense::readNtcC(pin_t pin) {
    const uint16_t raw = analogRead(digitalPinToAnalogInput(pin));
    const float vAdc = (raw * (ADC_VREF_MV / 1000.0f)) / 4095.0f;
    if (vAdc <= 0.001f || vAdc >= (ADC_VREF_MV / 1000.0f) - 0.001f) {
        return NAN;
    }
    const float rNtc = (NTC_SERIES_OHM * vAdc) / ((ADC_VREF_MV / 1000.0f) - vAdc);
    const float invT = (1.0f / 298.15f) + (1.0f / kNtcBeta) * logf(rNtc / kNtcR25);
    return (1.0f / invT) - 273.15f;
}

WitnessAnalog AdcSense::sample() {
    WitnessAnalog w = {};
    w.cells_v[0] = readCellVolts(PIN_CELL1);
    w.cells_v[1] = readCellVolts(PIN_CELL2);
    w.cells_v[2] = readCellVolts(PIN_CELL3);
    w.cells_v[3] = readCellVolts(PIN_CELL4);
    w.cells_v[4] = readCellVolts(PIN_CELL5);
    w.ntc1_c = readNtcC(PIN_NTC1);
    w.ntc2_c = readNtcC(PIN_NTC2);
    return w;
}
