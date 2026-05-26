#include "makita_onewire.h"

MakitaOneWire::MakitaOneWire(pin_t pin) : pin_(pin) {
    pinMode(pin_, INPUT_PULLUP);
}

bool MakitaOneWire::reset() {
    pinMode(pin_, OUTPUT);
    digitalWrite(pin_, LOW);
    delayMicroseconds(750);
    noInterrupts();
    pinMode(pin_, INPUT_PULLUP);
    delayMicroseconds(70);
    bool presence = (digitalRead(pin_) == LOW);
    interrupts();
    delayMicroseconds(410);
    return presence;
}

void MakitaOneWire::writeBit(uint8_t v) {
    if (v & 1) {
        noInterrupts();
        pinMode(pin_, OUTPUT);
        digitalWrite(pin_, LOW);
        delayMicroseconds(12);
        pinMode(pin_, INPUT_PULLUP);
        interrupts();
        delayMicroseconds(120);
    } else {
        noInterrupts();
        pinMode(pin_, OUTPUT);
        digitalWrite(pin_, LOW);
        delayMicroseconds(100);
        pinMode(pin_, INPUT_PULLUP);
        interrupts();
        delayMicroseconds(30);
    }
}

uint8_t MakitaOneWire::readBit() {
    uint8_t r;
    noInterrupts();
    pinMode(pin_, OUTPUT);
    digitalWrite(pin_, LOW);
    delayMicroseconds(10);
    pinMode(pin_, INPUT_PULLUP);
    delayMicroseconds(10);
    r = digitalRead(pin_);
    interrupts();
    delayMicroseconds(53);
    return r & 1;
}

void MakitaOneWire::write(uint8_t v) {
    for (uint8_t mask = 0x01; mask; mask <<= 1) {
        writeBit((v & mask) ? 1 : 0);
    }
    pinMode(pin_, INPUT_PULLUP);
}

uint8_t MakitaOneWire::read() {
    uint8_t r = 0;
    for (uint8_t i = 0; i < 8; i++) {
        r |= (readBit() << i);
    }
    return r;
}

MakitaEnable::MakitaEnable(pin_t pin) : pin_(pin) {}

void MakitaEnable::beginPassive() {
    passive_ = true;
    pinMode(pin_, INPUT_PULLDOWN);
}

void MakitaEnable::set(bool on) {
    if (passive_) {
        pinMode(pin_, OUTPUT);
        passive_ = false;
    }
    digitalWrite(pin_, on ? HIGH : LOW);
    if (!on && !passive_) {
        pinMode(pin_, INPUT_PULLDOWN);
        passive_ = true;
    }
}

bool MakitaOneWire::detectReset() {
    if (digitalRead(pin_) != LOW) {
        return false;
    }
    uint32_t t0 = micros();
    while (digitalRead(pin_) == LOW) {
        if (micros() - t0 > 700) {
            while (digitalRead(pin_) == LOW) {
            }
            delayMicroseconds(420);
            return true;
        }
        if (micros() - t0 > 900) {
            return false;
        }
    }
    return false;
}

void MakitaOneWire::presenceAck() {
    delayMicroseconds(30);
    pinMode(pin_, OUTPUT);
    digitalWrite(pin_, LOW);
    delayMicroseconds(80);
    pinMode(pin_, INPUT_PULLUP);
    delayMicroseconds(400);
}

uint8_t MakitaOneWire::readBitSlave() {
    while (digitalRead(pin_) == HIGH) {
    }
    delayMicroseconds(15);
    const uint8_t bit = digitalRead(pin_) & 1u;
    delayMicroseconds(60);
    while (digitalRead(pin_) == LOW) {
    }
    delayMicroseconds(10);
    return bit;
}

void MakitaOneWire::writeBitSlave(uint8_t v) {
    while (digitalRead(pin_) == HIGH) {
    }
    if (v & 1u) {
        delayMicroseconds(12);
    } else {
        pinMode(pin_, OUTPUT);
        digitalWrite(pin_, LOW);
        delayMicroseconds(80);
        pinMode(pin_, INPUT_PULLUP);
    }
    while (digitalRead(pin_) == LOW) {
    }
    delayMicroseconds(10);
}

uint8_t MakitaOneWire::readByteSlave() {
    uint8_t r = 0;
    for (uint8_t i = 0; i < 8; i++) {
        r |= (uint8_t)(readBitSlave() << i);
    }
    return r;
}

void MakitaOneWire::writeByteSlave(uint8_t v) {
    for (uint8_t mask = 0x01; mask; mask <<= 1) {
        writeBitSlave((v & mask) ? 1u : 0u);
    }
    pinMode(pin_, INPUT_PULLUP);
}

void obiGap() {
    delayMicroseconds(90);
}
