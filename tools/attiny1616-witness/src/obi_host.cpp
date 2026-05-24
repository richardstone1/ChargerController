#include "obi_host.h"
#include "witness_config.h"

ObiHost::ObiHost(MakitaOneWire &ow, MakitaEnable &en) : ow_(ow), en_(en) {}

void ObiHost::begin(uint32_t baud) {
    Serial.begin(baud);
}

void ObiHost::cmdAndRead33(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen) {
    ow_.reset();
    delayMicroseconds(400);
    ow_.write(0x33);
    for (uint8_t i = 0; i < 8; i++) {
        obiGap();
        rsp[i] = ow_.read();
    }
    for (uint8_t i = 0; i < cmdLen; i++) {
        obiGap();
        ow_.write(cmd[i]);
    }
    for (uint8_t i = 8; i < rspLen + 8; i++) {
        obiGap();
        rsp[i] = ow_.read();
    }
}

void ObiHost::cmdAndReadCc(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen) {
    ow_.reset();
    delayMicroseconds(400);
    ow_.write(0xCC);
    for (uint8_t i = 0; i < cmdLen; i++) {
        obiGap();
        ow_.write(cmd[i]);
    }
    for (uint8_t i = 0; i < rspLen; i++) {
        obiGap();
        rsp[i] = ow_.read();
    }
}

void ObiHost::sendUsb(const uint8_t *rsp, uint8_t rspLen) {
    for (uint8_t i = 0; i < rspLen; i++) {
        Serial.write(rsp[i]);
    }
}

void ObiHost::handleFrame(uint8_t cmd, uint8_t len, const uint8_t *data, uint8_t rspLen) {
    uint8_t rsp[255];
    en_.set(true);
    delay(400);

    switch (cmd) {
    case 0x01:
        rsp[0] = 0x01;
        rsp[1] = rspLen;
        rsp[2] = OBI_VERSION_MAJOR;
        rsp[3] = OBI_VERSION_MINOR;
        rsp[4] = OBI_VERSION_PATCH;
        sendUsb(rsp, rspLen + 2);
        break;
    case 0x31:
        ow_.reset();
        delayMicroseconds(400);
        ow_.write(0xCC);
        obiGap();
        ow_.write(0x99);
        delay(400);
        ow_.reset();
        delayMicroseconds(400);
        ow_.write(0x31);
        obiGap();
        rsp[3] = ow_.read();
        obiGap();
        rsp[2] = ow_.read();
        obiGap();
        rsp[0] = cmd;
        rsp[1] = rspLen;
        sendUsb(rsp, rspLen + 2);
        break;
    case 0x32:
        ow_.reset();
        delayMicroseconds(400);
        ow_.write(0xCC);
        obiGap();
        ow_.write(0x99);
        delay(400);
        ow_.reset();
        delayMicroseconds(400);
        ow_.write(0x32);
        obiGap();
        rsp[3] = ow_.read();
        obiGap();
        rsp[2] = ow_.read();
        obiGap();
        rsp[0] = cmd;
        rsp[1] = rspLen;
        sendUsb(rsp, rspLen + 2);
        break;
    case 0x33:
        rsp[0] = cmd;
        rsp[1] = rspLen;
        cmdAndRead33(data, len, &rsp[2], rspLen);
        sendUsb(rsp, rspLen + 2);
        break;
    case 0xCC:
        rsp[0] = cmd;
        rsp[1] = rspLen;
        cmdAndReadCc(data, len, &rsp[2], rspLen);
        sendUsb(rsp, rspLen + 2);
        break;
    default:
        break;
    }

    en_.set(false);
}

void ObiHost::poll() {
    if (Serial.available() < 4) {
        return;
    }
    if (Serial.peek() != 0x01) {
        Serial.read();
        return;
    }
  Serial.read(); // 0x01
    uint8_t len = Serial.read();
    uint8_t rspLen = Serial.read();
    uint8_t cmd = Serial.read();
    uint8_t data[255];
    for (uint8_t i = 0; i < len; i++) {
        while (!Serial.available()) {
        }
        data[i] = Serial.read();
    }
    handleFrame(cmd, len, data, rspLen);
}
