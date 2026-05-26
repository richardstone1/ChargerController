#ifndef WITNESS_PROFILE_CMDS_H
#define WITNESS_PROFILE_CMDS_H

#include <stdint.h>
#include "pack_profile.h"
#include "adc_sense.h"

/** Run profile maintenance subcmd (0xF0–0xF6). Returns false if unknown. */
bool witnessRunProfileCmd(PackProfileStore &store, WitnessAnalog *live, uint8_t subcmd, const uint8_t *tx,
                          uint8_t txLen, uint8_t *rsp, uint8_t rspMax, uint8_t *rspLenOut);

#endif
