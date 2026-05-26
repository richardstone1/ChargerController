#include "witness_profile_cmds.h"
#include "witness_config_cmds.h"
#include "witness_onewire_cmds.h"
#include <string.h>

bool witnessRunProfileCmd(PackProfileStore &store, WitnessAnalog *live, uint8_t subcmd, const uint8_t *tx,
                          uint8_t txLen, uint8_t *rsp, uint8_t rspMax, uint8_t *rspLenOut) {
    (void)live;
    const uint8_t need = witnessConfigRspLen(subcmd);
    if (need == 0 || need > rspMax) {
        return false;
    }

    uint8_t status = 0;

    switch (subcmd) {
    case WCMD_GET_STATUS:
        rsp[0] = store.profile().mode;
        rsp[1] = store.profile().preset_id;
        memcpy(&rsp[2], store.profile().uuid, WITNESS_UUID_LEN);
        break;

    case WCMD_READ_PROFILE:
        memcpy(rsp, &store.profile(), PACK_PROFILE_SIZE);
        break;

    case WCMD_WRITE_PROFILE:
        if (txLen >= PACK_PROFILE_SIZE) {
            memcpy(&store.profile(), tx, PACK_PROFILE_SIZE);
            store.profile().magic = PACK_PROFILE_MAGIC;
        } else {
            status = 1;
        }
        rsp[0] = status;
        break;

    case WCMD_RESET_PROFILE: {
        WitnessPreset preset = WITNESS_PRESET_BLANK;
        if (txLen >= 1) {
            preset = static_cast<WitnessPreset>(tx[0]);
        }
        store.factoryReset(preset);
        rsp[0] = 0;
        break;
    }

    case WCMD_SET_MODE:
        if (txLen >= 1) {
            store.profile().mode = tx[0];
        }
        rsp[0] = store.profile().mode;
        break;

    case WCMD_SAVE_EEPROM:
        rsp[0] = store.save() ? 0 : 1;
        break;

    case WCMD_LOAD_PRESET:
        if (txLen >= 1) {
            store.applyPreset(static_cast<WitnessPreset>(tx[0]));
        }
        rsp[0] = store.profile().preset_id;
        break;

    default:
        return false;
    }

    *rspLenOut = need;
    return true;
}
