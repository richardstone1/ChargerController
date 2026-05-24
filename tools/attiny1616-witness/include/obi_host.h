#ifndef OBI_HOST_H
#define OBI_HOST_H

#include <Arduino.h>
#include "makita_onewire.h"

/** ArduinoOBI-compatible serial command handler (9600 8N1). */
class ObiHost {
public:
    ObiHost(MakitaOneWire &ow, MakitaEnable &en);

    void begin(uint32_t baud);
    void poll();

private:
    void cmdAndRead33(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen);
    void cmdAndReadCc(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen);
    void handleFrame(uint8_t cmd, uint8_t len, const uint8_t *data, uint8_t rspLen);
    void sendUsb(const uint8_t *rsp, uint8_t rspLen);

    MakitaOneWire &ow_;
    MakitaEnable &en_;
};

#endif
