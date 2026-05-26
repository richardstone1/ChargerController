#ifndef WITNESS_ONEWIRE_CMDS_H
#define WITNESS_ONEWIRE_CMDS_H

/**
 * Witness maintenance over the Makita pack 1-Wire bus (no UART required).
 *
 * After a normal 1-Wire reset, the host sends primary command 0x57 ('W').
 * Subcommands mirror witness_config_cmds.h (0xF0–0xF6).
 *
 * Transaction (host = OBI reader / charger, slave = witness):
 *   RESET
 *   host → 0x57
 *   host → subcmd (0xF0..0xF6)
 *   host → tx_len
 *   host → tx[tx_len]
 *   host ← rsp[rsp_len]     (rsp_len is fixed per subcmd, same as UART OBI config)
 *
 * OBI serial tunnel (STM32OBI / witness UART debug): USB frame cmd 0x57
 *   01 <len> <rsp_len> 57 <subcmd> <tx_len> <tx...>
 *   response: 57 <rsp_len> <rsp...>
 *
 * Emulate-mode OBI reads (0x33 / 0xCC) are also served on the bus when the
 * witness is in emulate mode and the host uses the normal Makita sequence.
 */

#include <stdint.h>

/** Primary 1-Wire opcode (post-reset); not used by Makita BMS. */
#define OW_WITNESS_CMD 0x57u

/** OBI host serial tunnel for the same 1-Wire maintenance transaction. */
#define OBI_WITNESS_BUS_CMD 0x57u

/** Expected response payload sizes (bytes after OBI cmd/len header). */
#define WCMD_RSP_GET_STATUS   18u
#define WCMD_RSP_READ_PROFILE 99u
#define WCMD_RSP_STATUS_BYTE   1u

static inline uint8_t witnessConfigRspLen(uint8_t subcmd) {
    switch (subcmd) {
    case 0xF0:
        return WCMD_RSP_GET_STATUS;
    case 0xF1:
        return WCMD_RSP_READ_PROFILE;
    case 0xF2:
    case 0xF3:
    case 0xF4:
    case 0xF5:
    case 0xF6:
        return WCMD_RSP_STATUS_BYTE;
    default:
        return 0;
    }
}

#endif
