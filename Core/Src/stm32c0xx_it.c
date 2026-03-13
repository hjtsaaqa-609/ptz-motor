#include "main.h"
#include "stm32c0xx_it.h"

extern UART_HandleTypeDef huart2;
extern TIM_HandleTypeDef htim1;
extern TIM_HandleTypeDef htim3;

void NMI_Handler(void) {
  while (1) {
  }
}

void HardFault_Handler(void) {
  while (1) {
  }
}

void SVC_Handler(void) {
}

void PendSV_Handler(void) {
}

void SysTick_Handler(void) {
  HAL_IncTick();
}

void EXTI4_15_IRQHandler(void) {
  HAL_GPIO_EXTI_IRQHandler(M1_ZERO_Pin);
}

void EXTI2_3_IRQHandler(void) {
  HAL_GPIO_EXTI_IRQHandler(M2_ZERO_Pin);
}

void USART2_IRQHandler(void) {
  HAL_UART_IRQHandler(&huart2);
}

void TIM1_CC_IRQHandler(void) {
  HAL_TIM_IRQHandler(&htim1);
}

void TIM3_IRQHandler(void) {
  HAL_TIM_IRQHandler(&htim3);
}
