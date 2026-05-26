#ifndef PACK_PROFILE_H
#define PACK_PROFILE_H

#include <Arduino.h>

/** EEPROM-backed witness identity + OBI static/live templates. */
#define PACK_PROFILE_MAGIC 0x5749u /* 'WI' */
#define PACK_PROFILE_SIZE  99u
#define WITNESS_UUID_LEN     16u
#define WITNESS_ROM_LEN       8u
#define WITNESS_MSG_LEN      32u
#define WITNESS_MODEL_LEN     8u
#define WITNESS_READ_DATA_LEN 29u

enum WitnessMode : uint8_t {
    WITNESS_MODE_PASSTHROUGH = 0,
    WITNESS_MODE_EMULATE = 1,
};

enum WitnessPreset : uint8_t {
    WITNESS_PRESET_BLANK = 0,
    WITNESS_PRESET_BL1850B = 1,
    WITNESS_PRESET_BL1830 = 2,
    WITNESS_PRESET_CUSTOM = 255,
};

#pragma pack(push, 1)
struct PackProfile {
    uint16_t magic;
    uint16_t crc;
    uint8_t uuid[WITNESS_UUID_LEN];
    uint8_t mode;
    uint8_t preset_id;
    uint8_t rom_id[WITNESS_ROM_LEN];
    uint8_t msg_frame[WITNESS_MSG_LEN];
    char model[WITNESS_MODEL_LEN];
    uint8_t read_data_tpl[WITNESS_READ_DATA_LEN];
};
#pragma pack(pop)

static_assert(sizeof(PackProfile) == PACK_PROFILE_SIZE, "PackProfile EEPROM layout");

class PackProfileStore {
public:
    void begin();
    bool load();
    bool save();
    void factoryReset(WitnessPreset preset = WITNESS_PRESET_BLANK);
    void applyPreset(WitnessPreset preset);

    PackProfile &profile() { return active_; }
    const PackProfile &profile() const { return active_; }

    bool isEmulate() const { return active_.mode == WITNESS_MODE_EMULATE; }

private:
    uint16_t crc16(const uint8_t *data, size_t len) const;
    void refreshCrc();

    PackProfile active_;
    bool loaded_ = false;
};

#endif
