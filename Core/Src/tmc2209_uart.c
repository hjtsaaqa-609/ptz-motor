#include "tmc2209_uart.h"

#include <string.h>

#define TMC2209_UART_WRITE_FLAG 0x80U
#define TMC2209_UART_READ_REQ_LEN 4U
#define TMC2209_UART_WRITE_REQ_LEN 8U
#define TMC2209_UART_RESP_LEN 8U
#define TMC2209_UART_RX_BUF_LEN 32U
#define TMC2209_UART_TIMEOUT_MS 30U

static UART_HandleTypeDef *s_tmc_huart = NULL;

static void tmc2209_uart_flush_rx(void) {
  if (s_tmc_huart == NULL) {
    return;
  }

  while (__HAL_UART_GET_FLAG(s_tmc_huart, UART_FLAG_RXNE) != RESET) {
    (void)s_tmc_huart->Instance->RDR;
  }

  __HAL_UART_CLEAR_OREFLAG(s_tmc_huart);
  __HAL_UART_CLEAR_NEFLAG(s_tmc_huart);
  __HAL_UART_CLEAR_FEFLAG(s_tmc_huart);
}

static void encode_u32_be(uint8_t *dst, uint32_t value) {
  dst[0] = (uint8_t)((value >> 24) & 0xFFU);
  dst[1] = (uint8_t)((value >> 16) & 0xFFU);
  dst[2] = (uint8_t)((value >> 8) & 0xFFU);
  dst[3] = (uint8_t)(value & 0xFFU);
}

static uint32_t decode_u32_be(const uint8_t *src) {
  return ((uint32_t)src[0] << 24) |
         ((uint32_t)src[1] << 16) |
         ((uint32_t)src[2] << 8) |
         (uint32_t)src[3];
}

static TMC2209_UartResult_t read_frame(uint8_t reg, uint32_t *value) {
  uint8_t rxbuf[TMC2209_UART_RX_BUF_LEN];
  uint8_t byte = 0U;
  uint32_t start = HAL_GetTick();
  uint32_t count = 0U;

  if (s_tmc_huart == NULL || value == NULL) {
    return TMC2209_UART_ERR_PARAM;
  }

  memset(rxbuf, 0, sizeof(rxbuf));

  while ((HAL_GetTick() - start) < TMC2209_UART_TIMEOUT_MS && count < sizeof(rxbuf)) {
    if (HAL_UART_Receive(s_tmc_huart, &byte, 1U, 2U) == HAL_OK) {
      rxbuf[count++] = byte;
      if (count >= TMC2209_UART_RESP_LEN) {
        uint32_t i;
        for (i = 0U; i + TMC2209_UART_RESP_LEN <= count; ++i) {
          uint8_t *frame = &rxbuf[i];
          if (frame[0] != TMC2209_UART_SYNC) {
            continue;
          }
          if (frame[1] != 0xFFU) {
            continue;
          }
          if ((frame[2] & 0x7FU) != (reg & 0x7FU)) {
            continue;
          }
          if (TMC2209_UART_CRC(frame, TMC2209_UART_RESP_LEN - 1U) != frame[TMC2209_UART_RESP_LEN - 1U]) {
            return TMC2209_UART_ERR_CRC;
          }
          *value = decode_u32_be(&frame[3]);
          return TMC2209_UART_OK;
        }
      }
    }
  }

  return (count == 0U) ? TMC2209_UART_ERR_TIMEOUT : TMC2209_UART_ERR_FRAME;
}

void TMC2209_UART_Init(UART_HandleTypeDef *huart) {
  s_tmc_huart = huart;
}

uint8_t TMC2209_UART_CRC(const uint8_t *data, uint8_t len) {
  uint8_t crc = 0U;
  uint8_t i;
  uint8_t j;

  if (data == NULL) {
    return 0U;
  }

  for (i = 0U; i < len; ++i) {
    uint8_t current = data[i];
    for (j = 0U; j < 8U; ++j) {
      if (((crc >> 7) ^ (current & 0x01U)) != 0U) {
        crc = (uint8_t)((crc << 1) ^ 0x07U);
      } else {
        crc = (uint8_t)(crc << 1);
      }
      current >>= 1;
    }
  }

  return crc;
}

TMC2209_UartResult_t TMC2209_UART_WriteRegister(uint8_t addr, uint8_t reg, uint32_t value) {
  uint8_t frame[TMC2209_UART_WRITE_REQ_LEN];

  if (s_tmc_huart == NULL) {
    return TMC2209_UART_ERR_NOT_INIT;
  }

  frame[0] = TMC2209_UART_SYNC;
  frame[1] = addr & 0x03U;
  frame[2] = reg | TMC2209_UART_WRITE_FLAG;
  encode_u32_be(&frame[3], value);
  frame[7] = TMC2209_UART_CRC(frame, 7U);

  tmc2209_uart_flush_rx();
  if (HAL_UART_Transmit(s_tmc_huart, frame, sizeof(frame), TMC2209_UART_TIMEOUT_MS) != HAL_OK) {
    return TMC2209_UART_ERR_TX;
  }
  HAL_Delay(1U);
  tmc2209_uart_flush_rx();
  return TMC2209_UART_OK;
}

TMC2209_UartResult_t TMC2209_UART_ReadRegister(uint8_t addr, uint8_t reg, uint32_t *value) {
  uint8_t frame[TMC2209_UART_READ_REQ_LEN];
  TMC2209_UartResult_t ret;

  if (s_tmc_huart == NULL) {
    return TMC2209_UART_ERR_NOT_INIT;
  }
  if (value == NULL) {
    return TMC2209_UART_ERR_PARAM;
  }

  frame[0] = TMC2209_UART_SYNC;
  frame[1] = addr & 0x03U;
  frame[2] = reg & 0x7FU;
  frame[3] = TMC2209_UART_CRC(frame, 3U);

  tmc2209_uart_flush_rx();
  if (HAL_UART_Transmit(s_tmc_huart, frame, sizeof(frame), TMC2209_UART_TIMEOUT_MS) != HAL_OK) {
    return TMC2209_UART_ERR_TX;
  }
  ret = read_frame(reg, value);
  tmc2209_uart_flush_rx();
  return ret;
}

TMC2209_UartResult_t TMC2209_UART_ReadSnapshot(const PTZ_Motor_t *motor, TMC2209_RegSnapshot_t *snapshot) {
  TMC2209_UartResult_t ret;
  uint8_t addr;

  if (motor == NULL || snapshot == NULL) {
    return TMC2209_UART_ERR_PARAM;
  }

  addr = motor->tmc_uart_addr & 0x03U;

  ret = TMC2209_UART_ReadRegister(addr, TMC2209_REG_GCONF, &snapshot->gconf);
  if (ret != TMC2209_UART_OK) {
    return ret;
  }
  ret = TMC2209_UART_ReadRegister(addr, TMC2209_REG_IHOLD_IRUN, &snapshot->ihold_irun);
  if (ret != TMC2209_UART_OK) {
    return ret;
  }
  ret = TMC2209_UART_ReadRegister(addr, TMC2209_REG_CHOPCONF, &snapshot->chopconf);
  if (ret != TMC2209_UART_OK) {
    return ret;
  }
  ret = TMC2209_UART_ReadRegister(addr, TMC2209_REG_PWMCONF, &snapshot->pwmconf);
  if (ret != TMC2209_UART_OK) {
    return ret;
  }
  ret = TMC2209_UART_ReadRegister(addr, TMC2209_REG_DRV_STATUS, &snapshot->drv_status);
  if (ret != TMC2209_UART_OK) {
    return ret;
  }
  ret = TMC2209_UART_ReadRegister(addr, TMC2209_REG_IOIN, &snapshot->ioin);
  if (ret != TMC2209_UART_OK) {
    return ret;
  }
  ret = TMC2209_UART_ReadRegister(addr, TMC2209_REG_TPWMTHRS, &snapshot->tpwmthrs);
  if (ret != TMC2209_UART_OK) {
    return ret;
  }
  return TMC2209_UART_OK;
}

uint8_t TMC2209_MicrostepToMres(uint32_t microstep, uint8_t *mres) {
  if (mres == NULL) {
    return 0U;
  }

  switch (microstep) {
    case 1U: *mres = 8U; return 1U;
    case 2U: *mres = 7U; return 1U;
    case 4U: *mres = 6U; return 1U;
    case 8U: *mres = 5U; return 1U;
    case 16U: *mres = 4U; return 1U;
    case 32U: *mres = 3U; return 1U;
    case 64U: *mres = 2U; return 1U;
    case 128U: *mres = 1U; return 1U;
    case 256U: *mres = 0U; return 1U;
    default: return 0U;
  }
}

uint32_t TMC2209_MresToMicrostep(uint8_t mres) {
  switch (mres & 0x0FU) {
    case 0U: return 256U;
    case 1U: return 128U;
    case 2U: return 64U;
    case 3U: return 32U;
    case 4U: return 16U;
    case 5U: return 8U;
    case 6U: return 4U;
    case 7U: return 2U;
    case 8U: return 1U;
    default: return 0U;
  }
}

uint32_t TMC2209_CalcCurrentRmsMa(uint8_t irun, uint8_t vsense, uint16_t rsense_mohm) {
  uint32_t vfs_mv;
  uint32_t rsense_total_mohm;
  uint32_t numerator;

  vfs_mv = vsense ? 180U : 325U;
  rsense_total_mohm = (uint32_t)rsense_mohm + 20U;
  if (rsense_total_mohm == 0U) {
    return 0U;
  }

  numerator = (uint32_t)(irun + 1U) * vfs_mv * 1000U;
  return numerator / (32U * rsense_total_mohm * 1414U / 1000U);
}

const char *TMC2209_UartResultString(TMC2209_UartResult_t result) {
  switch (result) {
    case TMC2209_UART_OK: return "OK";
    case TMC2209_UART_ERR_PARAM: return "PARAM";
    case TMC2209_UART_ERR_NOT_INIT: return "NOT_INIT";
    case TMC2209_UART_ERR_TX: return "TX";
    case TMC2209_UART_ERR_RX: return "RX";
    case TMC2209_UART_ERR_TIMEOUT: return "TIMEOUT";
    case TMC2209_UART_ERR_CRC: return "CRC";
    case TMC2209_UART_ERR_FRAME: return "FRAME";
    default: return "UNKNOWN";
  }
}
