#ifndef OBI_SYNTH_H
#define OBI_SYNTH_H

#include <Arduino.h>
#include "adc_sense.h"
#include "pack_profile.h"

/** Build OBI READ_DATA (0x1D) payload from profile template + live ADC. */
void obiSynthReadData(const PackProfile &profile, const WitnessAnalog &live, uint8_t *out29);

/** Patch charge-count bytes inside msg_frame if needed (optional). */
void obiPatchMsgFrame(PackProfile &profile);

#endif
