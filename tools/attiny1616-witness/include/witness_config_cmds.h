#ifndef WITNESS_CONFIG_CMDS_H
#define WITNESS_CONFIG_CMDS_H

/** Witness maintenance commands — UART (0xF0–0xF6) or 1-Wire subcmd after OW_WITNESS_CMD (0x57). */
enum WitnessConfigCmd : uint8_t {
    WCMD_GET_STATUS = 0xF0,   /* rsp: mode, preset, uuid[16] */
    WCMD_READ_PROFILE = 0xF1, /* rsp: raw PackProfile bytes */
    WCMD_WRITE_PROFILE = 0xF2,/* payload: raw PackProfile bytes */
    WCMD_RESET_PROFILE = 0xF3,/* payload[0]=preset id (optional) */
    WCMD_SET_MODE = 0xF4,     /* payload[0]=WitnessMode */
    WCMD_SAVE_EEPROM = 0xF5,
    WCMD_LOAD_PRESET = 0xF6,   /* payload[0]=WitnessPreset */
};

#endif
