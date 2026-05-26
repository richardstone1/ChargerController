#ifndef WITNESS_BUS_SLAVE_H
#define WITNESS_BUS_SLAVE_H

#include "makita_onewire.h"
#include "pack_profile.h"
#include "adc_sense.h"

/** 1-Wire slave: OBI emulate + witness maintenance when pack enable is active. */
class WitnessBusSlave {
public:
    WitnessBusSlave(MakitaOneWire &ow, PackProfileStore &profiles, WitnessAnalog *live);

    /** Non-blocking: handle one bus session if reset detected while enable active. */
    void poll(bool enableActive);

private:
    uint8_t readByteFromMaster();
    void writeByteToMaster(uint8_t v);
    void writeBlockToMaster(const uint8_t *data, uint8_t len);
    bool handleWitnessMaint(uint8_t subcmd, uint8_t txLen);
    bool handleObi33();
    bool handleObiCc();

    MakitaOneWire &ow_;
    PackProfileStore &profiles_;
    WitnessAnalog *live_;
    uint8_t rsp_[255];
};

#endif
