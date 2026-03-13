#include "main.h"
#include "ptz_motor.h"
#include "ui_uart.h"

TIM_HandleTypeDef htim1;
TIM_HandleTypeDef htim3;
UART_HandleTypeDef huart2;

static PTZ_Motor_t g_motor1;
static PTZ_Motor_t g_motor2;

static void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM1_Init(void);
static void MX_TIM3_Init(void);
static void MX_USART2_UART_Init(void);

int main(void) {
  uint32_t last_report_tick = 0U;
  uint32_t last_service_tick = 0U;
  uint32_t timer1_tick_hz = 0U;
  uint32_t timer3_tick_hz = 0U;

  HAL_Init();
  SystemClock_Config();

  MX_GPIO_Init();
  MX_TIM1_Init();
  MX_TIM3_Init();
  MX_USART2_UART_Init();

  timer1_tick_hz = HAL_RCC_GetHCLKFreq() / (htim1.Init.Prescaler + 1U);
  timer3_tick_hz = HAL_RCC_GetHCLKFreq() / (htim3.Init.Prescaler + 1U);

  PTZ_MotorInit(&g_motor1, &htim1, TIM_CHANNEL_1,
                M1_STEP_GPIO_Port, M1_STEP_Pin, GPIO_AF2_TIM1,
                M1_DIR_GPIO_Port, M1_DIR_Pin,
                M1_EN_GPIO_Port, M1_EN_Pin,
                M1_ZERO_GPIO_Port, M1_ZERO_Pin,
                timer1_tick_hz);

  PTZ_MotorInit(&g_motor2, &htim3, TIM_CHANNEL_1,
                M2_STEP_GPIO_Port, M2_STEP_Pin, GPIO_AF1_TIM3,
                M2_DIR_GPIO_Port, M2_DIR_Pin,
                M2_EN_GPIO_Port, M2_EN_Pin,
                M2_ZERO_GPIO_Port, M2_ZERO_Pin,
                timer3_tick_hz);

  UI_Init(&huart2, &g_motor1, &g_motor2);
  last_service_tick = HAL_GetTick();

  while (1) {
    uint32_t now = HAL_GetTick();
    uint32_t dt_ms = now - last_service_tick;

    UI_Process();

    if (dt_ms >= 10U) {
      last_service_tick = now;
      PTZ_MotorService(&g_motor1, now, dt_ms);
      PTZ_MotorService(&g_motor2, now, dt_ms);
    }

    if ((now - last_report_tick) >= 250U) {
      last_report_tick = now;
      UI_ReportRealtime();
    }
  }
}

static void SystemClock_Config(void) {
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  __HAL_FLASH_SET_LATENCY(FLASH_LATENCY_1);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSIDiv = RCC_HSI_DIV1;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.SYSCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV1;
  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1) != HAL_OK) {
    Error_Handler();
  }
}

static void MX_TIM1_Init(void) {
  TIM_OC_InitTypeDef sConfigOC = {0};

  __HAL_RCC_TIM1_CLK_ENABLE();

  htim1.Instance = TIM1;
  htim1.Init.Prescaler = 47U; /* 48MHz / (47+1) => 1MHz */
  htim1.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim1.Init.Period = 0xFFFFU;
  htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim1.Init.RepetitionCounter = 0U;
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_OC_Init(&htim1) != HAL_OK) {
    Error_Handler();
  }

  sConfigOC.OCMode = TIM_OCMODE_TOGGLE;
  sConfigOC.Pulse = 100U;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_OC_ConfigChannel(&htim1, &sConfigOC, TIM_CHANNEL_1) != HAL_OK) {
    Error_Handler();
  }
}

static void MX_TIM3_Init(void) {
  TIM_OC_InitTypeDef sConfigOC = {0};

  __HAL_RCC_TIM3_CLK_ENABLE();

  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 47U; /* 48MHz / (47+1) => 1MHz */
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 0xFFFFU;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_OC_Init(&htim3) != HAL_OK) {
    Error_Handler();
  }

  sConfigOC.OCMode = TIM_OCMODE_TOGGLE;
  sConfigOC.Pulse = 100U;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_OC_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_1) != HAL_OK) {
    Error_Handler();
  }
}

static void MX_USART2_UART_Init(void) {
  __HAL_RCC_USART2_CLK_ENABLE();

  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  huart2.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart2.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&huart2) != HAL_OK) {
    Error_Handler();
  }
}

static void MX_GPIO_Init(void) {
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* DIR/EN output pins */
  GPIO_InitStruct.Pin = M1_DIR_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(M1_DIR_GPIO_Port, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = M1_EN_Pin;
  HAL_GPIO_Init(M1_EN_GPIO_Port, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = M2_DIR_Pin;
  HAL_GPIO_Init(M2_DIR_GPIO_Port, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = M2_EN_Pin;
  HAL_GPIO_Init(M2_EN_GPIO_Port, &GPIO_InitStruct);

  /* Zero-position input pins with EXTI */
  GPIO_InitStruct.Pin = M1_ZERO_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING_FALLING;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(M1_ZERO_GPIO_Port, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = M2_ZERO_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING_FALLING;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(M2_ZERO_GPIO_Port, &GPIO_InitStruct);

  /* STEP PWM pins */
  GPIO_InitStruct.Pin = M1_STEP_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF2_TIM1;
  HAL_GPIO_Init(M1_STEP_GPIO_Port, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = M2_STEP_Pin;
  GPIO_InitStruct.Alternate = GPIO_AF1_TIM3;
  HAL_GPIO_Init(M2_STEP_GPIO_Port, &GPIO_InitStruct);

  /* UART pins */
  GPIO_InitStruct.Pin = USART2_TX_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF1_USART2;
  HAL_GPIO_Init(USART2_TX_GPIO_Port, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = USART2_RX_Pin;
  HAL_GPIO_Init(USART2_RX_GPIO_Port, &GPIO_InitStruct);

  HAL_NVIC_SetPriority(EXTI4_15_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(EXTI4_15_IRQn);
  HAL_NVIC_SetPriority(EXTI2_3_IRQn, 1, 1);
  HAL_NVIC_EnableIRQ(EXTI2_3_IRQn);

  HAL_NVIC_SetPriority(USART2_IRQn, 2, 0);
  HAL_NVIC_EnableIRQ(USART2_IRQn);
  HAL_NVIC_SetPriority(TIM1_CC_IRQn, 1, 2);
  HAL_NVIC_EnableIRQ(TIM1_CC_IRQn);
  HAL_NVIC_SetPriority(TIM3_IRQn, 1, 3);
  HAL_NVIC_EnableIRQ(TIM3_IRQn);
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin) {
  if (GPIO_Pin == M1_ZERO_Pin) {
    PTZ_MotorZeroUpdate(&g_motor1);
  } else if (GPIO_Pin == M2_ZERO_Pin) {
    PTZ_MotorZeroUpdate(&g_motor2);
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
  UI_OnUartRxCplt(huart);
}

void HAL_TIM_OC_DelayElapsedCallback(TIM_HandleTypeDef *htim) {
  if (htim == g_motor1.htim) {
    PTZ_MotorOnTimerCompare(&g_motor1);
  } else if (htim == g_motor2.htim) {
    PTZ_MotorOnTimerCompare(&g_motor2);
  }
}

void Error_Handler(void) {
  __disable_irq();
  while (1) {
  }
}
