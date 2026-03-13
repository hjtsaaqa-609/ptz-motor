#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32c0xx_hal.h"

/* -------- Pin map (adjust to your board) -------- */
#define M1_DIR_Pin GPIO_PIN_0
#define M1_DIR_GPIO_Port GPIOA
#define M1_EN_Pin GPIO_PIN_1
#define M1_EN_GPIO_Port GPIOA
#define M1_ZERO_Pin GPIO_PIN_4
#define M1_ZERO_GPIO_Port GPIOA

#define M2_DIR_Pin GPIO_PIN_0
#define M2_DIR_GPIO_Port GPIOB
#define M2_EN_Pin GPIO_PIN_1
#define M2_EN_GPIO_Port GPIOB
#define M2_ZERO_Pin GPIO_PIN_2
#define M2_ZERO_GPIO_Port GPIOB

#define M1_STEP_Pin GPIO_PIN_8      /* TIM1_CH1 */
#define M1_STEP_GPIO_Port GPIOA
#define M2_STEP_Pin GPIO_PIN_4      /* TIM3_CH1 */
#define M2_STEP_GPIO_Port GPIOB

#define USART2_TX_Pin GPIO_PIN_2
#define USART2_TX_GPIO_Port GPIOA
#define USART2_RX_Pin GPIO_PIN_3
#define USART2_RX_GPIO_Port GPIOA

void Error_Handler(void);

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
