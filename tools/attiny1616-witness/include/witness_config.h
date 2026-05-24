#ifndef WITNESS_CONFIG_H
#define WITNESS_CONFIG_H

/**
 * ATtiny1616 witness — 20-pin VQFN 3×3 (22×8 mm PCB).
 * See pcb/DESIGN.md
 *
 * USART0 default: TX = PA1, RX = PA2 (OBI host serial @ 9600).
 */

#ifndef F_CPU
#define F_CPU 20000000UL
#endif

#define PIN_UART_TX   PIN_PA1
#define PIN_UART_RX   PIN_PA2

#define PIN_ENABLE    PIN_PA3
#define PIN_ONEWIRE   PIN_PA4

#define PIN_CELL1     PIN_PA5
#define PIN_CELL2     PIN_PA6
#define PIN_CELL3     PIN_PA7
#define PIN_CELL4     PIN_PB0
#define PIN_CELL5     PIN_PB1

#define PIN_NTC1      PIN_PB2
#define PIN_NTC2      PIN_PB3

#define PIN_LED_OK    PIN_PB4

#define ADC_VREF_MV       3300
#define CELL_DIV_RTOP_OHM 470000UL
#define CELL_DIV_RBOT_OHM 100000UL
#define NTC_SERIES_OHM    10000UL

#define OBI_BAUD          9600
#define OBI_VERSION_MAJOR 0
#define OBI_VERSION_MINOR 1
#define OBI_VERSION_PATCH 0

#endif
