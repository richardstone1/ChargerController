#include <Arduino.h>
#include "obi_config.h"
#include "OneWire2.h"

/** Major version number (X.x.x) */
#define OBI_VERSION_MAJOR 0
/** Minor version number (x.X.x) */
#define OBI_VERSION_MINOR 3
/** Patch version number (x.x.X) */
#define OBI_VERSION_PATCH 0

/** Witness pack maintenance on 1-Wire (see tools/attiny1616-witness/include/witness_onewire_cmds.h). */
#define OW_WITNESS_CMD 0x57

OneWire makita(ONEWIRE_PIN);

void cmd_and_read_33(byte *cmd, uint8_t cmd_len, byte *rsp, uint8_t rsp_len) {
	int i;
	makita.reset();
	delayMicroseconds(400);
	makita.write(0x33,0);

	for (i=0; i < 8; i++) {
		delayMicroseconds(90);
		rsp[i] = makita.read();
	}

	for (i=0; i < cmd_len; i++) {
		delayMicroseconds(90);
		makita.write(cmd[i],0);
	}

	for (i=8; i < rsp_len + 8; i++) {
		delayMicroseconds(90);
		rsp[i] = makita.read();
	}
}

void cmd_and_read_cc(byte *cmd, uint8_t cmd_len, byte *rsp, uint8_t rsp_len) {
	int i;
	makita.reset();
	delayMicroseconds(400);
	makita.write(0xcc,0);

	for (i=0; i < cmd_len; i++) {
		delayMicroseconds(90);
		makita.write(cmd[i],0);
	}

	for (i=0; i < rsp_len; i++) {
		delayMicroseconds(90);
		rsp[i] = makita.read();
	}
}

void witness_bus_transact(uint8_t subcmd, byte *tx, uint8_t tx_len, byte *rsp, uint8_t rsp_len) {
	int i;
	makita.reset();
	delayMicroseconds(400);
	makita.write(OW_WITNESS_CMD, 0);
	delayMicroseconds(90);
	makita.write(subcmd, 0);
	delayMicroseconds(90);
	makita.write(tx_len, 0);
	for (i = 0; i < tx_len; i++) {
		delayMicroseconds(90);
		makita.write(tx[i], 0);
	}
	for (i = 0; i < rsp_len; i++) {
		delayMicroseconds(90);
		rsp[i] = makita.read();
	}
}

void setup() {
	Serial.begin(9600);
#ifdef USBCON
	/* Wait for USB CDC enumerate / host to open the port (e.g. read_battery.py). */
	unsigned long usb_wait = millis();
	while (!Serial && (millis() - usb_wait) < 5000) {
		delay(10);
	}
#endif
	pinMode(ENABLE_PIN, OUTPUT);
	digitalWrite(ENABLE_PIN, LOW);
}

void send_usb(byte *rsp, byte rsp_len) {
    for (int i=0; i < rsp_len; i++) {
        Serial.write(rsp[i]);
    }
}

void read_usb() {
    if (Serial.available() >= 4) {
        byte start = Serial.read();
        byte cmd;
        byte len;
        byte data[255];
        byte rsp[255];
        byte rsp_len;

        if (start == 0x01) {
            len = Serial.read();
            rsp_len = Serial.read();
            cmd = Serial.read();
            if (len > 0){
                for (int i = 0; i < len; i++) {
                    while (Serial.available() < 1);
                    data[i] = Serial.read();
                }
            }
        }
        else {
            return;
        }
    	digitalWrite(ENABLE_PIN, HIGH);
	    delay(400);

        switch(cmd) {
            case 0x01:
                rsp[0] = 0x01;
                rsp[2] = OBI_VERSION_MAJOR;
                rsp[3] = OBI_VERSION_MINOR;
                rsp[4] = OBI_VERSION_PATCH;
                break;
            case 0x31:
                makita.reset();
                delayMicroseconds(400);
                makita.write(0xcc,0);
                delayMicroseconds(90);
                makita.write(0x99,0);
                delay(400);
                makita.reset();
                delayMicroseconds(400);
                makita.write(0x31,0);
                delayMicroseconds(90);
                rsp[3] = makita.read();
                delayMicroseconds(90);
                rsp[2] = makita.read();
                delayMicroseconds(90);
                break;
            case 0x32:
                makita.reset();
                delayMicroseconds(400);
                makita.write(0xcc,0);
                delayMicroseconds(90);
                makita.write(0x99,0);
                delay(400);
                makita.reset();
                delayMicroseconds(400);
                makita.write(0x32,0);
                delayMicroseconds(90);
                rsp[3] = makita.read();
                delayMicroseconds(90);
                rsp[2] = makita.read();
                delayMicroseconds(90);
                break;
            case 0x33:
                cmd_and_read_33(data, len, &rsp[2], rsp_len);
                break;
            case 0xCC:
                cmd_and_read_cc(data, len, &rsp[2], rsp_len);
                break;
            case OW_WITNESS_CMD:
                if (len >= 2) {
                    witness_bus_transact(data[0], &data[2], data[1], &rsp[2], rsp_len);
                } else {
                    rsp_len = 0;
                }
                break;
            default:
                rsp_len = 0;
                break;
        }
        rsp[0] = cmd;
        rsp[1] = rsp_len;
        send_usb(rsp, rsp_len + 2);

        digitalWrite(ENABLE_PIN, LOW);
    }
}

void loop() {
    read_usb();
}
