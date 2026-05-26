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

    /** Non-blocking reset detect (master pulled low ≥480 µs). */
    bool detectReset();
    /** Slave: presence ack after master reset. */
    void presenceAck();
    uint8_t readByteSlave();
    void writeByteSlave(uint8_t v);

private:
    void writeBit(uint8_t v);
    uint8_t readBit();
    uint8_t readBitSlave();
    void writeBitSlave(uint8_t v);

    pin_t pin_;
};

class MakitaEnable {
public:
    explicit MakitaEnable(pin_t pin);
    /** High-Z input; external host drives pack enable. */
    void beginPassive();
    void set(bool on);

private:
    pin_t pin_;
    bool passive_ = true;
};

void obiGap();

#endif
