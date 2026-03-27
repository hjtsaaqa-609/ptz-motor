#ifndef TMC2209_UART_H
#define TMC2209_UART_H

#include "main.h"
#include "ptz_motor.h"

#ifdef __cplusplus
extern "C" {
#endif

#define TMC2209_UART_SYNC 0x05U

#define TMC2209_REG_GCONF 0x00U
#define TMC2209_REG_GSTAT 0x01U
#define TMC2209_REG_IFCNT 0x02U
#define TMC2209_REG_IOIN 0x06U
#define TMC2209_REG_IHOLD_IRUN 0x10U
#define TMC2209_REG_TPOWERDOWN 0x11U
#define TMC2209_REG_TPWMTHRS 0x13U
#define TMC2209_REG_CHOPCONF 0x6CU
#define TMC2209_REG_DRV_STATUS 0x6FU
#define TMC2209_REG_PWMCONF 0x70U

typedef enum {
  TMC2209_UART_OK = 0,
  TMC2209_UART_ERR_PARAM,
  TMC2209_UART_ERR_NOT_INIT,
  TMC2209_UART_ERR_TX,
  TMC2209_UART_ERR_RX,
  TMC2209_UART_ERR_TIMEOUT,
  TMC2209_UART_ERR_CRC,
  TMC2209_UART_ERR_FRAME
} TMC2209_UartResult_t;

typedef struct {
  uint32_t gconf;
  uint32_t ihold_irun;
  uint32_t chopconf;
  uint32_t pwmconf;
  uint32_t drv_status;
  uint32_t ioin;
  uint32_t tpwmthrs;
} TMC2209_RegSnapshot_t;

void TMC2209_UART_Init(UART_HandleTypeDef *huart);
TMC2209_UartResult_t TMC2209_UART_ReadRegister(uint8_t addr, uint8_t reg, uint32_t *value);
TMC2209_UartResult_t TMC2209_UART_WriteRegister(uint8_t addr, uint8_t reg, uint32_t value);
TMC2209_UartResult_t TMC2209_UART_ReadSnapshot(const PTZ_Motor_t *motor, TMC2209_RegSnapshot_t *snapshot);
uint8_t TMC2209_UART_CRC(const uint8_t *data, uint8_t len);
uint8_t TMC2209_MicrostepToMres(uint32_t microstep, uint8_t *mres);
uint32_t TMC2209_MresToMicrostep(uint8_t mres);
uint32_t TMC2209_CalcCurrentRmsMa(uint8_t irun, uint8_t vsense, uint16_t rsense_mohm);
const char *TMC2209_UartResultString(TMC2209_UartResult_t result);

#ifdef __cplusplus
}
#endif

#endif /* TMC2209_UART_H */
