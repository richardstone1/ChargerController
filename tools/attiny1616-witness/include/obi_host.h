#ifndef OBI_HOST_H
#define OBI_HOST_H

#include <Arduino.h>
#include "makita_onewire.h"
#include "pack_profile.h"
#include "adc_sense.h"

/** ArduinoOBI-compatible serial command handler (9600 8N1). */
class ObiHost {
public:
    ObiHost(MakitaOneWire &ow, MakitaEnable &en, PackProfileStore &profiles, WitnessAnalog *live);

    void begin(uint32_t baud);
    void poll();

private:
    bool handleConfigCmd(uint8_t cmd, uint8_t len, const uint8_t *data, uint8_t rspLen);
    void handleObiCmd(uint8_t cmd, uint8_t len, const uint8_t *data, uint8_t rspLen);
    void cmdAndRead33(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen);
    void cmdAndReadCc(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen);
    void emulateRead33(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen);
    void emulateReadCc(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen);
    void witnessBusTransact(uint8_t subcmd, const uint8_t *tx, uint8_t txLen, uint8_t *rsp, uint8_t rspLen);
    void sendUsb(const uint8_t *rsp, uint8_t rspLen);

    MakitaOneWire &ow_;
    MakitaEnable &en_;
    PackProfileStore &profiles_;
    WitnessAnalog *live_;
};

#endif
