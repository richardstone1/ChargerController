#ifndef MAKITA_ONEWIRE_H
#define MAKITA_ONEWIRE_H

#include <Arduino.h>

/**
 * Makita LXT 1-Wire bit timing from OBI-modified OneWire2
 * (open-battery-information / ArduinoOBI).
 */
class MakitaOneWire {
public:
    explicit MakitaOneWire(pin_t pin);

    bool reset();
    void write(uint8_t v);
    uint8_t read();

private:
    void writeBit(uint8_t v);
    uint8_t readBit();

    pin_t pin_;
};

class MakitaEnable {
public:
    explicit MakitaEnable(pin_t pin);
    void set(bool on);

private:
    pin_t pin_;
};

void obiGap();

#endif
