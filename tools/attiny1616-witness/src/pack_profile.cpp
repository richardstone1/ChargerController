#include "pack_profile.h"
#include <EEPROM.h>
#include <avr/io.h>
#include <stddef.h>
#include <string.h>

static const PackProfile kPresetBl1850b PROGMEM = {
    PACK_PROFILE_MAGIC,
    0,
    {0x57, 0x49, 0x54, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01},
    WITNESS_MODE_EMULATE,
    WITNESS_PRESET_BL1850B,
    {0x15, 0x04, 0x1B, 0x64, 0x07, 0x09, 0x01, 0x7C},
    {0xF1, 0x36, 0xB6, 0xC3, 0x18, 0x58, 0x00, 0x00, 0x84, 0x84, 0x40, 0x21, 0x01, 0x80, 0x02, 0x0D,
     0x43, 0xD0, 0x8E, 0x1B, 0xF0, 0x67, 0x00, 0x03, 0x02, 0x02, 0x0E, 0x50, 0x00, 0x40, 0x01, 0xC3},
    "BL1850B",
    {0x22, 0x48, 0x69, 0x0E, 0x6B, 0x0E, 0x69, 0x0E, 0x6C, 0x0E, 0x6B, 0x0E, 0x28, 0x05, 0x70, 0x0B,
     0x75, 0x0B, 0x00, 0x80, 0x40, 0x05, 0x2C, 0xC0, 0x12, 0x40, 0xDB, 0x5C, 0x00},
};

static const PackProfile kPresetBl1830 PROGMEM = {
    PACK_PROFILE_MAGIC,
    0,
    {0x57, 0x49, 0x54, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01},
    WITNESS_MODE_EMULATE,
    WITNESS_PRESET_BL1830,
    {0x15, 0x04, 0x1B, 0x64, 0x07, 0x09, 0x01, 0x7C},
    {0xF1, 0x36, 0xB6, 0xC3, 0x18, 0x58, 0x00, 0x00, 0x84, 0x84, 0x40, 0x21, 0x01, 0x80, 0x02, 0x0D,
     0x43, 0xD0, 0x8E, 0x1B, 0xF0, 0x65, 0x00, 0x03, 0x12, 0x02, 0x0E, 0x40, 0x00, 0x30, 0x00, 0xA3},
    "BL1830B",
    {0x22, 0x48, 0x69, 0x0E, 0x6B, 0x0E, 0x69, 0x0E, 0x6C, 0x0E, 0x6B, 0x0E, 0x28, 0x05, 0x70, 0x0B,
     0x75, 0x0B, 0x00, 0x80, 0x40, 0x05, 0x2C, 0xC0, 0x12, 0x40, 0xDB, 0x5C, 0x00},
};

static uint16_t crc16_ccitt_update(uint16_t crc, uint8_t data) {
    crc ^= (uint16_t)data << 8;
    for (uint8_t i = 0; i < 8; i++) {
        if (crc & 0x8000) {
            crc = (uint16_t)((crc << 1) ^ 0x1021);
        } else {
            crc <<= 1;
        }
    }
    return crc;
}

uint16_t PackProfileStore::crc16(const uint8_t *data, size_t len) const {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc = crc16_ccitt_update(crc, data[i]);
    }
    return crc;
}

void PackProfileStore::refreshCrc() {
    active_.magic = PACK_PROFILE_MAGIC;
    active_.crc = 0;
    active_.crc = crc16(reinterpret_cast<const uint8_t *>(&active_.uuid[0]),
                        PACK_PROFILE_SIZE - offsetof(PackProfile, uuid));
}

static void uuidFromSerial(PackProfile &p) {
    p.uuid[0] = 'W';
    p.uuid[1] = 'I';
    p.uuid[2] = 'T';
    p.uuid[3] = '0';
    p.uuid[4] = (uint8_t)(SIGROW.SERNUM0);
    p.uuid[5] = (uint8_t)(SIGROW.SERNUM0 >> 8);
    p.uuid[6] = (uint8_t)(SIGROW.SERNUM0 >> 16);
    p.uuid[7] = (uint8_t)(SIGROW.SERNUM0 >> 24);
    p.uuid[8] = (uint8_t)(SIGROW.SERNUM1);
    p.uuid[9] = (uint8_t)(SIGROW.SERNUM1 >> 8);
    p.uuid[10] = (uint8_t)(SIGROW.SERNUM1 >> 16);
    p.uuid[11] = (uint8_t)(SIGROW.SERNUM1 >> 24);
    p.uuid[12] = (uint8_t)(SIGROW.SERNUM2);
    p.uuid[13] = (uint8_t)(SIGROW.SERNUM2 >> 8);
    p.uuid[14] = (uint8_t)(SIGROW.SERNUM2 >> 16);
    p.uuid[15] = (uint8_t)(SIGROW.SERNUM2 >> 24);
}

void PackProfileStore::begin() {
    if (!load()) {
        factoryReset(WITNESS_PRESET_BLANK);
        save();
    }
    loaded_ = true;
}

bool PackProfileStore::load() {
    EEPROM.get(0, active_);
    if (active_.magic != PACK_PROFILE_MAGIC) {
        return false;
    }
    const uint16_t stored = active_.crc;
    active_.crc = 0;
    const uint16_t calc = crc16(reinterpret_cast<const uint8_t *>(&active_.uuid[0]),
                                PACK_PROFILE_SIZE - offsetof(PackProfile, uuid));
    active_.crc = stored;
    return calc == stored;
}

bool PackProfileStore::save() {
    refreshCrc();
    EEPROM.put(0, active_);
    return true;
}

void PackProfileStore::applyPreset(WitnessPreset preset) {
    switch (preset) {
    case WITNESS_PRESET_BL1850B:
        memcpy_P(&active_, &kPresetBl1850b, sizeof(PackProfile));
        uuidFromSerial(active_);
        active_.uuid[3] = 0x01;
        break;
    case WITNESS_PRESET_BL1830:
        memcpy_P(&active_, &kPresetBl1830, sizeof(PackProfile));
        uuidFromSerial(active_);
        active_.uuid[3] = 0x02;
        break;
    case WITNESS_PRESET_BLANK:
    default:
        memset(&active_, 0, sizeof(active_));
        active_.mode = WITNESS_MODE_PASSTHROUGH;
        active_.preset_id = WITNESS_PRESET_BLANK;
        memcpy(active_.model, "WITNESS", 7);
        uuidFromSerial(active_);
        break;
    }
    active_.preset_id = preset;
    refreshCrc();
}

void PackProfileStore::factoryReset(WitnessPreset preset) {
    applyPreset(preset);
}
