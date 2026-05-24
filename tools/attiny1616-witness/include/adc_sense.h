#ifndef ADC_SENSE_H
#define ADC_SENSE_H

#include <Arduino.h>

struct WitnessAnalog {
    float cells_v[5];
    float ntc1_c;
    float ntc2_c;
};

class AdcSense {
public:
    void begin();
    WitnessAnalog sample();

private:
    float readCellVolts(pin_t pin);
    float readNtcC(pin_t pin);

    static constexpr float kNtcBeta = 3950.0f;
    static constexpr float kNtcR25 = 10000.0f;
};

#endif
