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

MakitaEnable::MakitaEnable(pin_t pin) : pin_(pin) {
    pinMode(pin_, OUTPUT);
    digitalWrite(pin_, LOW);
}

void MakitaEnable::set(bool on) {
    digitalWrite(pin_, on ? HIGH : LOW);
}

void obiGap() {
    delayMicroseconds(90);
}
