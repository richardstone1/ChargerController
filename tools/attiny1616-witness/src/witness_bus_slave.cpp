#include "witness_bus_slave.h"
#include "witness_onewire_cmds.h"
#include "witness_profile_cmds.h"
#include "witness_config_cmds.h"
#include "obi_synth.h"

WitnessBusSlave::WitnessBusSlave(MakitaOneWire &ow, PackProfileStore &profiles, WitnessAnalog *live)
    : ow_(ow), profiles_(profiles), live_(live) {}

void WitnessBusSlave::writeByteToMaster(uint8_t v) {
    ow_.writeByteSlave(v);
}

void WitnessBusSlave::writeBlockToMaster(const uint8_t *data, uint8_t len) {
    for (uint8_t i = 0; i < len; i++) {
        writeByteToMaster(data[i]);
    }
}

uint8_t WitnessBusSlave::readByteFromMaster() {
    return ow_.readByteSlave();
}

bool WitnessBusSlave::handleWitnessMaint(uint8_t subcmd, uint8_t txLen) {
    uint8_t tx[255];
    if (txLen > sizeof(tx)) {
        return false;
    }
    for (uint8_t i = 0; i < txLen; i++) {
        tx[i] = readByteFromMaster();
    }

    uint8_t rspLen = 0;
    if (!witnessRunProfileCmd(profiles_, live_, subcmd, tx, txLen, rsp_, sizeof(rsp_), &rspLen)) {
        return false;
    }
    writeBlockToMaster(rsp_, rspLen);
    return true;
}

bool WitnessBusSlave::handleObi33() {
    const PackProfile &p = profiles_.profile();
    writeBlockToMaster(p.rom_id, WITNESS_ROM_LEN);

    uint8_t cmd[2];
    cmd[0] = readByteFromMaster();
    cmd[1] = readByteFromMaster();

    uint8_t buf[WITNESS_ROM_LEN + WITNESS_MSG_LEN];
    memcpy(buf, p.rom_id, WITNESS_ROM_LEN);
    memcpy(buf + WITNESS_ROM_LEN, p.msg_frame, WITNESS_MSG_LEN);
    (void)cmd;
    writeBlockToMaster(buf + WITNESS_ROM_LEN, WITNESS_MSG_LEN);
    return true;
}

bool WitnessBusSlave::handleObiCc() {
    uint8_t sub[4];
    sub[0] = readByteFromMaster();
    sub[1] = readByteFromMaster();
    uint8_t subLen = 2;
    if (sub[0] == 0xD7) {
        sub[2] = readByteFromMaster();
        sub[3] = readByteFromMaster();
        subLen = 4;
    }

    const PackProfile &p = profiles_.profile();

    if (subLen >= 2 && sub[0] == 0xDC && sub[1] == 0x0C) {
        uint8_t model[WITNESS_MODEL_LEN];
        memset(model, 0, sizeof(model));
        memcpy(model, p.model, WITNESS_MODEL_LEN);
        writeBlockToMaster(model, WITNESS_MODEL_LEN);
        return true;
    }

    if (subLen >= 1 && sub[0] == 0xD7 && live_ != nullptr) {
        uint8_t rd[WITNESS_READ_DATA_LEN];
        obiSynthReadData(p, *live_, rd);
        writeBlockToMaster(rd, WITNESS_READ_DATA_LEN);
        return true;
    }

    return false;
}

void WitnessBusSlave::poll(bool enableActive) {
    if (!enableActive) {
        return;
    }
    if (!ow_.detectReset()) {
        return;
    }

    ow_.presenceAck();
    const uint8_t primary = readByteFromMaster();

    if (primary == OW_WITNESS_CMD) {
        const uint8_t subcmd = readByteFromMaster();
        const uint8_t txLen = readByteFromMaster();
        handleWitnessMaint(subcmd, txLen);
        return;
    }

    if (!profiles_.isEmulate()) {
        return;
    }

    if (primary == 0x33) {
        handleObi33();
        return;
    }

    if (primary == 0xCC) {
        handleObiCc();
    }
}
