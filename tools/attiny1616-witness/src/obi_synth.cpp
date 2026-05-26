#include "obi_synth.h"

static void writeLe16(uint8_t *dst, uint16_t mv) {
    dst[0] = (uint8_t)(mv & 0xFF);
    dst[1] = (uint8_t)(mv >> 8);
}

void obiSynthReadData(const PackProfile &profile, const WitnessAnalog &live, uint8_t *out29) {
    memcpy(out29, profile.read_data_tpl, WITNESS_READ_DATA_LEN);

    float packV = 0.0f;
    for (uint8_t i = 0; i < 5; i++) {
        if (!isnan(live.cells_v[i])) {
            packV += live.cells_v[i];
        }
    }
    if (packV < 0.5f) {
        packV = 0.0f;
    }

    writeLe16(out29 + 0, (uint16_t)(packV * 1000.0f + 0.5f));
    for (uint8_t i = 0; i < 5; i++) {
        const float cv = isnan(live.cells_v[i]) ? 0.0f : live.cells_v[i];
        writeLe16(out29 + 2 + (i * 2), (uint16_t)(cv * 1000.0f + 0.5f));
    }

    const float t1 = isnan(live.ntc1_c) ? 25.0f : live.ntc1_c;
    const float t2 = isnan(live.ntc2_c) ? t1 : live.ntc2_c;
    writeLe16(out29 + 16, (uint16_t)(t1 * 100.0f + 0.5f));
    writeLe16(out29 + 18, (uint16_t)(t2 * 100.0f + 0.5f));
}

void obiPatchMsgFrame(PackProfile &profile) {
    (void)profile;
}
