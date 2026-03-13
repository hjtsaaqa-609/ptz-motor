#ifndef UI_UART_H
#define UI_UART_H

#include "ptz_motor.h"

#ifdef __cplusplus
extern "C" {
#endif

void UI_Init(UART_HandleTypeDef *huart, PTZ_Motor_t *m1, PTZ_Motor_t *m2);
void UI_Process(void);
void UI_ReportRealtime(void);
uint8_t UI_TelemetryEnabled(void);
void UI_OnUartRxCplt(UART_HandleTypeDef *huart);

#ifdef __cplusplus
}
#endif

#endif /* UI_UART_H */
