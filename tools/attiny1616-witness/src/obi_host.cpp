#include "obi_host.h"
#include "witness_config.h"
#include "witness_config_cmds.h"
#include "witness_onewire_cmds.h"
#include "witness_profile_cmds.h"
#include "obi_synth.h"

ObiHost::ObiHost(MakitaOneWire &ow, MakitaEnable &en, PackProfileStore &profiles, WitnessAnalog *live)
    : ow_(ow), en_(en), profiles_(profiles), live_(live) {}

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

void ObiHost::witnessBusTransact(uint8_t subcmd, const uint8_t *tx, uint8_t txLen, uint8_t *rsp, uint8_t rspLen) {
    ow_.reset();
    delayMicroseconds(400);
    ow_.write(OW_WITNESS_CMD);
    obiGap();
    ow_.write(subcmd);
    obiGap();
    ow_.write(txLen);
    for (uint8_t i = 0; i < txLen; i++) {
        obiGap();
        ow_.write(tx[i]);
    }
    for (uint8_t i = 0; i < rspLen; i++) {
        obiGap();
        rsp[i] = ow_.read();
    }
}

void ObiHost::emulateRead33(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen) {
    (void)cmd;
    (void)cmdLen;
    const PackProfile &p = profiles_.profile();
    memcpy(rsp, p.rom_id, WITNESS_ROM_LEN);
    const uint8_t msgLen = rspLen > WITNESS_ROM_LEN ? (uint8_t)(rspLen - WITNESS_ROM_LEN) : 0;
    if (msgLen > 0) {
        memcpy(rsp + WITNESS_ROM_LEN, p.msg_frame, msgLen > WITNESS_MSG_LEN ? WITNESS_MSG_LEN : msgLen);
    }
}

void ObiHost::emulateReadCc(const uint8_t *cmd, uint8_t cmdLen, uint8_t *rsp, uint8_t rspLen) {
    const PackProfile &p = profiles_.profile();

    if (cmdLen >= 2 && cmd[0] == 0xDC && cmd[1] == 0x0C) {
        memset(rsp, 0, rspLen);
        memcpy(rsp, p.model, rspLen < WITNESS_MODEL_LEN ? rspLen : WITNESS_MODEL_LEN);
        return;
    }

    if (cmdLen >= 1 && cmd[0] == 0xD7 && live_ != nullptr) {
        obiSynthReadData(p, *live_, rsp);
        if (rspLen > WITNESS_READ_DATA_LEN) {
            memset(rsp + WITNESS_READ_DATA_LEN, 0, rspLen - WITNESS_READ_DATA_LEN);
        }
        return;
    }

    memset(rsp, 0, rspLen);
}

void ObiHost::sendUsb(const uint8_t *rsp, uint8_t rspLen) {
    for (uint8_t i = 0; i < rspLen; i++) {
        Serial.write(rsp[i]);
    }
}

bool ObiHost::handleConfigCmd(uint8_t cmd, uint8_t len, const uint8_t *data, uint8_t rspLen) {
    if (cmd == OBI_WITNESS_BUS_CMD) {
        if (len < 2) {
            return true;
        }
        const uint8_t subcmd = data[0];
        const uint8_t txLen = data[1];
        if ((uint16_t)2 + txLen > len) {
            return true;
        }
        uint8_t rsp[255];
        en_.set(true);
        delay(400);
        witnessBusTransact(subcmd, &data[2], txLen, rsp, rspLen);
        en_.set(false);
        uint8_t out[255];
        out[0] = cmd;
        out[1] = rspLen;
        memcpy(&out[2], rsp, rspLen);
        sendUsb(out, rspLen + 2);
        return true;
    }

    if (cmd < WCMD_GET_STATUS) {
        return false;
    }

    uint8_t rsp[255];
    uint8_t got = 0;
    if (!witnessRunProfileCmd(profiles_, live_, cmd, data, len, rsp, sizeof(rsp), &got)) {
        return false;
    }

    uint8_t out[255];
    out[0] = cmd;
    out[1] = got;
    memcpy(&out[2], rsp, got);
    sendUsb(out, got + 2);
    return true;
}

void ObiHost::handleObiCmd(uint8_t cmd, uint8_t len, const uint8_t *data, uint8_t rspLen) {
    uint8_t rsp[255];
    const bool emulate = profiles_.isEmulate();

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
        if (emulate) {
            rsp[0] = cmd;
            rsp[1] = rspLen;
            rsp[2] = 0;
            rsp[3] = 0;
            sendUsb(rsp, rspLen + 2);
        } else {
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
        }
        break;
    case 0x32:
        if (emulate) {
            rsp[0] = cmd;
            rsp[1] = rspLen;
            rsp[2] = 0;
            rsp[3] = 0;
            sendUsb(rsp, rspLen + 2);
        } else {
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
        }
        break;
    case 0x33:
        rsp[0] = cmd;
        rsp[1] = rspLen;
        if (emulate) {
            emulateRead33(data, len, &rsp[2], rspLen);
        } else {
            cmdAndRead33(data, len, &rsp[2], rspLen);
        }
        sendUsb(rsp, rspLen + 2);
        break;
    case 0xCC:
        rsp[0] = cmd;
        rsp[1] = rspLen;
        if (emulate) {
            emulateReadCc(data, len, &rsp[2], rspLen);
        } else {
            cmdAndReadCc(data, len, &rsp[2], rspLen);
        }
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

    if (handleConfigCmd(cmd, len, data, rspLen)) {
        return;
    }
    handleObiCmd(cmd, len, data, rspLen);
}
