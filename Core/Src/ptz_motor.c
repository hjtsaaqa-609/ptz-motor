#include "ptz_motor.h"

static void config_step_pin_af(PTZ_Motor_t *motor) {
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  if (motor == NULL || motor->step_port == NULL) {
    return;
  }

  GPIO_InitStruct.Pin = motor->step_pin;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = motor->step_af;
  HAL_GPIO_Init(motor->step_port, &GPIO_InitStruct);
}

static void config_step_pin_gpio(PTZ_Motor_t *motor) {
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  if (motor == NULL || motor->step_port == NULL) {
    return;
  }

  GPIO_InitStruct.Pin = motor->step_pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(motor->step_port, &GPIO_InitStruct);
}

static GPIO_PinState motor_en_inactive_level(const PTZ_Motor_t *motor) {
  return (motor->en_active_level == GPIO_PIN_SET) ? GPIO_PIN_RESET : GPIO_PIN_SET;
}

static uint32_t clamp_speed(uint32_t speed_hz) {
  if (speed_hz < PTZ_MOTOR_MIN_SPEED_HZ) {
    return PTZ_MOTOR_MIN_SPEED_HZ;
  }
  if (speed_hz > PTZ_MOTOR_MAX_SPEED_HZ) {
    return PTZ_MOTOR_MAX_SPEED_HZ;
  }
  return speed_hz;
}

static uint32_t clamp_accel(uint32_t accel_hzps) {
  if (accel_hzps < PTZ_MOTOR_MIN_ACCEL_HZPS) {
    return PTZ_MOTOR_MIN_ACCEL_HZPS;
  }
  if (accel_hzps > PTZ_MOTOR_MAX_ACCEL_HZPS) {
    return PTZ_MOTOR_MAX_ACCEL_HZPS;
  }
  return accel_hzps;
}

static uint32_t clamp_steps_per_rev(uint32_t steps_per_rev) {
  if (steps_per_rev < PTZ_MOTOR_MIN_STEPS_PER_REV) {
    return PTZ_MOTOR_MIN_STEPS_PER_REV;
  }
  if (steps_per_rev > PTZ_MOTOR_MAX_STEPS_PER_REV) {
    return PTZ_MOTOR_MAX_STEPS_PER_REV;
  }
  return steps_per_rev;
}

static uint32_t clamp_wakeup_delay_us(uint32_t wakeup_delay_us) {
  if (wakeup_delay_us > PTZ_MOTOR_MAX_WAKEUP_DELAY_US) {
    return PTZ_MOTOR_MAX_WAKEUP_DELAY_US;
  }
  return wakeup_delay_us;
}

static uint32_t speed_to_interval_ticks(uint32_t timer_tick_hz, uint32_t speed_hz) {
  uint32_t interval;

  if (speed_hz == 0U) {
    return 0U;
  }

  interval = timer_tick_hz / (speed_hz * 2U);
  if (interval == 0U) {
    interval = 1U;
  }
  if (interval > 0xFFFFU) {
    interval = 0xFFFFU;
  }
  return interval;
}

static uint32_t interval_ticks_to_speed(uint32_t timer_tick_hz, uint32_t interval) {
  if (interval == 0U) {
    return 0U;
  }
  return timer_tick_hz / (interval * 2U);
}

static void driver_setup_delay(const PTZ_Motor_t *motor) {
  for (volatile uint32_t i = 0; i < motor->setup_delay_loops; ++i) {
    __NOP();
  }
}

static void driver_wakeup_delay_us(uint32_t wakeup_delay_us) {
  uint32_t ms;
  uint32_t rem_us;
  uint32_t loops_per_us;
  volatile uint32_t loops;

  if (wakeup_delay_us == 0U) {
    return;
  }

  ms = wakeup_delay_us / 1000U;
  rem_us = wakeup_delay_us % 1000U;

  if (ms > 0U) {
    HAL_Delay(ms);
  }
  if (rem_us == 0U) {
    return;
  }

  loops_per_us = SystemCoreClock / 3000000U;
  if (loops_per_us == 0U) {
    loops_per_us = 1U;
  }

  loops = rem_us * loops_per_us;
  while (loops-- > 0U) {
    __NOP();
  }
}

static void apply_driver_profile(PTZ_Motor_t *motor, PTZ_MotorDriver_t driver) {
  motor->driver = driver;
  switch (driver) {
    case PTZ_DRIVER_TMC2209:
      motor->steps_per_rev = PTZ_MOTOR_TMC2209_STEPS_PER_REV;
      motor->wakeup_delay_us = PTZ_MOTOR_TMC2209_WAKEUP_DELAY_US;
      motor->en_active_level = GPIO_PIN_RESET;
      motor->dir_fwd_level = GPIO_PIN_SET;
      motor->dir_rev_level = GPIO_PIN_RESET;
      motor->setup_delay_loops = 1200U;
      break;
    case PTZ_DRIVER_A4988:
      motor->steps_per_rev = PTZ_MOTOR_A4988_STEPS_PER_REV;
      motor->wakeup_delay_us = PTZ_MOTOR_A4988_WAKEUP_DELAY_US;
      motor->en_active_level = GPIO_PIN_RESET;
      motor->dir_fwd_level = GPIO_PIN_SET;
      motor->dir_rev_level = GPIO_PIN_RESET;
      motor->setup_delay_loops = 1200U;
      break;
    case PTZ_DRIVER_DM556:
      motor->steps_per_rev = PTZ_MOTOR_DM556_STEPS_PER_REV;
      motor->wakeup_delay_us = PTZ_MOTOR_DM556_WAKEUP_DELAY_US;
      motor->en_active_level = GPIO_PIN_RESET;
      motor->dir_fwd_level = GPIO_PIN_SET;
      motor->dir_rev_level = GPIO_PIN_RESET;
      motor->setup_delay_loops = 4000U;
      break;
    case PTZ_DRIVER_GC6609:
    default:
      motor->steps_per_rev = PTZ_MOTOR_GC6609_STEPS_PER_REV;
      motor->wakeup_delay_us = PTZ_MOTOR_GC6609_WAKEUP_DELAY_US;
      motor->en_active_level = GPIO_PIN_RESET;
      motor->dir_fwd_level = GPIO_PIN_SET;
      motor->dir_rev_level = GPIO_PIN_RESET;
      motor->setup_delay_loops = 2000U;
      break;
  }
}

static void stop_step_output(PTZ_Motor_t *motor) {
  HAL_TIM_OC_Stop_IT(motor->htim, motor->channel);
  config_step_pin_gpio(motor);
  HAL_GPIO_WritePin(motor->step_port, motor->step_pin, GPIO_PIN_RESET);
}

static void update_output(PTZ_Motor_t *motor, PTZ_MotorDir_t dir, uint32_t speed_hz) {
  uint32_t interval;
  uint32_t compare_base;

  if (motor == NULL) {
    return;
  }

  if (speed_hz == 0U || dir == PTZ_MOTOR_STOP) {
    stop_step_output(motor);
    HAL_GPIO_WritePin(motor->en_port, motor->en_pin, motor_en_inactive_level(motor));
    motor->pulse_interval_ticks = 0U;
    motor->actual_speed_hz = 0U;
    motor->running = 0U;
    if (motor->state != PTZ_MOTOR_STATE_PIN_TEST && motor->state != PTZ_MOTOR_STATE_FAULT) {
      motor->state = PTZ_MOTOR_STATE_IDLE;
    }
    return;
  }

  interval = speed_to_interval_ticks(motor->timer_tick_hz, speed_hz);
  if (interval == 0U) {
    PTZ_MotorEmergencyStop(motor, PTZ_MOTOR_FAULT_PARAM);
    return;
  }

  HAL_GPIO_WritePin(motor->dir_port, motor->dir_pin,
                    (dir == PTZ_MOTOR_FORWARD) ? motor->dir_fwd_level : motor->dir_rev_level);
  HAL_GPIO_WritePin(motor->en_port, motor->en_pin, motor->en_active_level);
  driver_setup_delay(motor);

  motor->pulse_interval_ticks = interval;
  if (!motor->running) {
    driver_wakeup_delay_us(motor->wakeup_delay_us);
    compare_base = __HAL_TIM_GET_COUNTER(motor->htim) + interval;
    stop_step_output(motor);
    config_step_pin_af(motor);
    __HAL_TIM_SET_COMPARE(motor->htim, motor->channel, compare_base);
    if (HAL_TIM_OC_Start_IT(motor->htim, motor->channel) != HAL_OK) {
      PTZ_MotorEmergencyStop(motor, PTZ_MOTOR_FAULT_HAL);
      return;
    }
  }

  motor->dir = dir;
  motor->actual_speed_hz = interval_ticks_to_speed(motor->timer_tick_hz, interval);
  motor->running = 1U;
}

static uint32_t calc_ramp_step(uint32_t accel_hzps, uint32_t dt_ms) {
  uint32_t step;

  if (dt_ms == 0U) {
    return 0U;
  }

  step = (accel_hzps * dt_ms) / 1000U;
  if (step == 0U) {
    step = 1U;
  }
  return step;
}

void PTZ_MotorInit(PTZ_Motor_t *motor,
                   TIM_HandleTypeDef *htim,
                   uint32_t channel,
                   GPIO_TypeDef *step_port, uint16_t step_pin, uint32_t step_af,
                   GPIO_TypeDef *dir_port, uint16_t dir_pin,
                   GPIO_TypeDef *en_port, uint16_t en_pin,
                   GPIO_TypeDef *zero_port, uint16_t zero_pin,
                   uint32_t timer_tick_hz) {
  if (motor == NULL || htim == NULL || timer_tick_hz == 0U) {
    return;
  }

  motor->htim = htim;
  motor->channel = channel;
  motor->step_port = step_port;
  motor->step_pin = step_pin;
  motor->step_af = step_af;
  motor->dir_port = dir_port;
  motor->dir_pin = dir_pin;
  motor->en_port = en_port;
  motor->en_pin = en_pin;
  motor->zero_port = zero_port;
  motor->zero_pin = zero_pin;
  motor->timer_tick_hz = timer_tick_hz;
  apply_driver_profile(motor, PTZ_DRIVER_A4988);
  motor->dir = PTZ_MOTOR_STOP;
  motor->target_dir = PTZ_MOTOR_STOP;
  motor->state = PTZ_MOTOR_STATE_IDLE;
  motor->fault = PTZ_MOTOR_FAULT_NONE;
  motor->cmd_speed_hz = 0U;
  motor->actual_speed_hz = 0U;
  motor->accel_hzps = PTZ_MOTOR_DEFAULT_ACCEL_HZPS;
  motor->pulse_interval_ticks = 0U;
  motor->jog_until_ms = 0U;
  motor->zero_edges = 0U;
  motor->last_zero_tick_ms = 0U;
  motor->running = 0U;
  motor->zero_active = 0U;
  motor->pin_override_active = 0U;

  config_step_pin_af(motor);
  HAL_GPIO_WritePin(motor->en_port, motor->en_pin, motor_en_inactive_level(motor));
  HAL_GPIO_WritePin(motor->dir_port, motor->dir_pin, motor->dir_fwd_level);
  PTZ_MotorZeroUpdate(motor);
}

PTZ_MotorResult_t PTZ_MotorCommand(PTZ_Motor_t *motor, PTZ_MotorDir_t dir, uint32_t speed_hz) {
  if (motor == NULL || dir == PTZ_MOTOR_STOP) {
    return PTZ_MOTOR_ERR_PARAM;
  }
  if (motor->pin_override_active) {
    return PTZ_MOTOR_ERR_BUSY;
  }
  if (speed_hz < PTZ_MOTOR_MIN_SPEED_HZ || speed_hz > PTZ_MOTOR_MAX_SPEED_HZ) {
    return PTZ_MOTOR_ERR_SPEED_RANGE;
  }

  PTZ_MotorZeroUpdate(motor);
  motor->fault = PTZ_MOTOR_FAULT_NONE;
  motor->target_dir = dir;
  motor->cmd_speed_hz = clamp_speed(speed_hz);
  motor->jog_until_ms = 0U;

  if (motor->actual_speed_hz == 0U) {
    motor->state = PTZ_MOTOR_STATE_RAMP_UP;
  }
  return PTZ_MOTOR_OK;
}

PTZ_MotorResult_t PTZ_MotorJog(PTZ_Motor_t *motor, PTZ_MotorDir_t dir, uint32_t speed_hz, uint32_t duration_ms) {
  PTZ_MotorResult_t ret;

  if (duration_ms == 0U) {
    return PTZ_MOTOR_ERR_PARAM;
  }

  ret = PTZ_MotorCommand(motor, dir, speed_hz);
  if (ret != PTZ_MOTOR_OK) {
    return ret;
  }

  motor->jog_until_ms = HAL_GetTick() + duration_ms;
  return PTZ_MOTOR_OK;
}

PTZ_MotorResult_t PTZ_MotorSetAccel(PTZ_Motor_t *motor, uint32_t accel_hzps) {
  if (motor == NULL) {
    return PTZ_MOTOR_ERR_PARAM;
  }
  if (accel_hzps < PTZ_MOTOR_MIN_ACCEL_HZPS || accel_hzps > PTZ_MOTOR_MAX_ACCEL_HZPS) {
    return PTZ_MOTOR_ERR_ACCEL_RANGE;
  }
  motor->accel_hzps = clamp_accel(accel_hzps);
  return PTZ_MOTOR_OK;
}

PTZ_MotorResult_t PTZ_MotorSetDriver(PTZ_Motor_t *motor, PTZ_MotorDriver_t driver) {
  if (motor == NULL) {
    return PTZ_MOTOR_ERR_PARAM;
  }
  if (motor->pin_override_active) {
    return PTZ_MOTOR_ERR_BUSY;
  }

  PTZ_MotorStop(motor);
  update_output(motor, PTZ_MOTOR_STOP, 0U);
  apply_driver_profile(motor, driver);
  HAL_GPIO_WritePin(motor->dir_port, motor->dir_pin, motor->dir_fwd_level);
  HAL_GPIO_WritePin(motor->en_port, motor->en_pin, motor_en_inactive_level(motor));
  return PTZ_MOTOR_OK;
}

PTZ_MotorResult_t PTZ_MotorSetStepsPerRev(PTZ_Motor_t *motor, uint32_t steps_per_rev) {
  if (motor == NULL) {
    return PTZ_MOTOR_ERR_PARAM;
  }
  if (motor->pin_override_active) {
    return PTZ_MOTOR_ERR_BUSY;
  }
  if (steps_per_rev < PTZ_MOTOR_MIN_STEPS_PER_REV || steps_per_rev > PTZ_MOTOR_MAX_STEPS_PER_REV) {
    return PTZ_MOTOR_ERR_STEPS_RANGE;
  }
  motor->steps_per_rev = clamp_steps_per_rev(steps_per_rev);
  return PTZ_MOTOR_OK;
}

PTZ_MotorResult_t PTZ_MotorSetWakeupDelayUs(PTZ_Motor_t *motor, uint32_t wakeup_delay_us) {
  if (motor == NULL) {
    return PTZ_MOTOR_ERR_PARAM;
  }
  if (motor->pin_override_active) {
    return PTZ_MOTOR_ERR_BUSY;
  }
  if (wakeup_delay_us > PTZ_MOTOR_MAX_WAKEUP_DELAY_US) {
    return PTZ_MOTOR_ERR_WAKEUP_RANGE;
  }
  motor->wakeup_delay_us = clamp_wakeup_delay_us(wakeup_delay_us);
  return PTZ_MOTOR_OK;
}

void PTZ_MotorStop(PTZ_Motor_t *motor) {
  if (motor == NULL) {
    return;
  }

  motor->target_dir = PTZ_MOTOR_STOP;
  motor->cmd_speed_hz = 0U;
  motor->jog_until_ms = 0U;
  if (motor->actual_speed_hz == 0U) {
    update_output(motor, PTZ_MOTOR_STOP, 0U);
  } else {
    motor->state = PTZ_MOTOR_STATE_RAMP_DOWN;
  }
}

void PTZ_MotorEmergencyStop(PTZ_Motor_t *motor, PTZ_MotorFault_t fault) {
  if (motor == NULL) {
    return;
  }

  stop_step_output(motor);
  config_step_pin_af(motor);
  HAL_GPIO_WritePin(motor->en_port, motor->en_pin, motor_en_inactive_level(motor));

  motor->dir = PTZ_MOTOR_STOP;
  motor->target_dir = PTZ_MOTOR_STOP;
  motor->cmd_speed_hz = 0U;
  motor->actual_speed_hz = 0U;
  motor->jog_until_ms = 0U;
  motor->running = 0U;
  motor->fault = fault;
  motor->state = PTZ_MOTOR_STATE_FAULT;
}

void PTZ_MotorClearFault(PTZ_Motor_t *motor) {
  if (motor == NULL) {
    return;
  }

  motor->fault = PTZ_MOTOR_FAULT_NONE;
  if (motor->pin_override_active) {
    motor->state = PTZ_MOTOR_STATE_PIN_TEST;
  } else if (motor->actual_speed_hz == 0U) {
    motor->state = PTZ_MOTOR_STATE_IDLE;
  }
}

void PTZ_MotorService(PTZ_Motor_t *motor, uint32_t now_ms, uint32_t dt_ms) {
  uint32_t step_hz;
  uint32_t desired_hz;
  uint32_t current_hz;

  if (motor == NULL) {
    return;
  }

  PTZ_MotorZeroUpdate(motor);

  if (motor->pin_override_active) {
    motor->state = PTZ_MOTOR_STATE_PIN_TEST;
    return;
  }

  if (motor->fault != PTZ_MOTOR_FAULT_NONE) {
    motor->state = PTZ_MOTOR_STATE_FAULT;
    update_output(motor, PTZ_MOTOR_STOP, 0U);
    return;
  }

  if (motor->jog_until_ms != 0U && ((int32_t)(now_ms - motor->jog_until_ms) >= 0)) {
    motor->jog_until_ms = 0U;
    motor->target_dir = PTZ_MOTOR_STOP;
    motor->cmd_speed_hz = 0U;
  }

  step_hz = calc_ramp_step(motor->accel_hzps, dt_ms);
  desired_hz = motor->cmd_speed_hz;
  current_hz = motor->actual_speed_hz;

  if (motor->target_dir == PTZ_MOTOR_STOP || desired_hz == 0U) {
    if (current_hz <= step_hz) {
      update_output(motor, PTZ_MOTOR_STOP, 0U);
      motor->dir = PTZ_MOTOR_STOP;
    } else {
      current_hz -= step_hz;
      motor->state = PTZ_MOTOR_STATE_RAMP_DOWN;
      update_output(motor, motor->dir, current_hz);
    }
    return;
  }

  desired_hz = clamp_speed(desired_hz);

  if (current_hz == 0U) {
    motor->dir = motor->target_dir;
  } else if (motor->dir != motor->target_dir) {
    if (current_hz <= step_hz) {
      update_output(motor, PTZ_MOTOR_STOP, 0U);
      motor->dir = motor->target_dir;
    } else {
      motor->state = PTZ_MOTOR_STATE_RAMP_DOWN;
      update_output(motor, motor->dir, current_hz - step_hz);
      return;
    }
  }

  current_hz = motor->actual_speed_hz;
  if (current_hz < desired_hz) {
    current_hz += step_hz;
    if (current_hz > desired_hz) {
      current_hz = desired_hz;
    }
    motor->state = (current_hz == desired_hz) ? PTZ_MOTOR_STATE_RUN : PTZ_MOTOR_STATE_RAMP_UP;
  } else if (current_hz > desired_hz) {
    if ((current_hz - desired_hz) <= step_hz) {
      current_hz = desired_hz;
    } else {
      current_hz -= step_hz;
    }
    motor->state = (current_hz == desired_hz) ? PTZ_MOTOR_STATE_RUN : PTZ_MOTOR_STATE_RAMP_DOWN;
  } else {
    motor->state = PTZ_MOTOR_STATE_RUN;
  }

  update_output(motor, motor->target_dir, current_hz);
}

void PTZ_MotorOnTimerCompare(PTZ_Motor_t *motor) {
  uint32_t next_ccr;

  if (motor == NULL || !motor->running || motor->pulse_interval_ticks == 0U) {
    return;
  }

  next_ccr = __HAL_TIM_GET_COMPARE(motor->htim, motor->channel) + motor->pulse_interval_ticks;
  __HAL_TIM_SET_COMPARE(motor->htim, motor->channel, next_ccr);
}

void PTZ_MotorPinWrite(PTZ_Motor_t *motor, PTZ_MotorPin_t pin, GPIO_PinState state) {
  if (motor == NULL) {
    return;
  }

  stop_step_output(motor);
  motor->dir = PTZ_MOTOR_STOP;
  motor->target_dir = PTZ_MOTOR_STOP;
  motor->cmd_speed_hz = 0U;
  motor->actual_speed_hz = 0U;
  motor->pulse_interval_ticks = 0U;
  motor->jog_until_ms = 0U;
  motor->running = 0U;
  motor->pin_override_active = 1U;
  motor->state = PTZ_MOTOR_STATE_PIN_TEST;

  if (pin == PTZ_MOTOR_PIN_STEP) {
    config_step_pin_gpio(motor);
    HAL_GPIO_WritePin(motor->step_port, motor->step_pin, state);
    return;
  }

  config_step_pin_af(motor);
  if (pin == PTZ_MOTOR_PIN_DIR) {
    HAL_GPIO_WritePin(motor->dir_port, motor->dir_pin, state);
  } else if (pin == PTZ_MOTOR_PIN_EN) {
    HAL_GPIO_WritePin(motor->en_port, motor->en_pin, state);
  }
}

void PTZ_MotorPinRestore(PTZ_Motor_t *motor) {
  if (motor == NULL) {
    return;
  }

  stop_step_output(motor);
  config_step_pin_af(motor);
  HAL_GPIO_WritePin(motor->dir_port, motor->dir_pin, motor->dir_fwd_level);
  HAL_GPIO_WritePin(motor->en_port, motor->en_pin, motor_en_inactive_level(motor));

  motor->dir = PTZ_MOTOR_STOP;
  motor->target_dir = PTZ_MOTOR_STOP;
  motor->cmd_speed_hz = 0U;
  motor->actual_speed_hz = 0U;
  motor->pulse_interval_ticks = 0U;
  motor->jog_until_ms = 0U;
  motor->running = 0U;
  motor->pin_override_active = 0U;
  motor->state = (motor->fault == PTZ_MOTOR_FAULT_NONE) ? PTZ_MOTOR_STATE_IDLE : PTZ_MOTOR_STATE_FAULT;
}

void PTZ_MotorZeroUpdate(PTZ_Motor_t *motor) {
  GPIO_PinState state;
  uint8_t active;

  if (motor == NULL) {
    return;
  }

  state = HAL_GPIO_ReadPin(motor->zero_port, motor->zero_pin);
  active = (state == PTZ_MOTOR_ZERO_ACTIVE_LEVEL) ? 1U : 0U;
  if (active != motor->zero_active) {
    motor->zero_edges++;
    motor->last_zero_tick_ms = HAL_GetTick();
  }
  motor->zero_active = active;
}

const char *PTZ_MotorDriverString(PTZ_MotorDriver_t driver) {
  switch (driver) {
    case PTZ_DRIVER_TMC2209:
      return "TMC2209";
    case PTZ_DRIVER_A4988:
      return "A4988";
    case PTZ_DRIVER_DM556:
      return "DM556";
    case PTZ_DRIVER_GC6609:
    default:
      return "GC6609";
  }
}

const char *PTZ_MotorDirString(PTZ_MotorDir_t dir) {
  switch (dir) {
    case PTZ_MOTOR_FORWARD:
      return "FWD";
    case PTZ_MOTOR_REVERSE:
      return "REV";
    case PTZ_MOTOR_STOP:
    default:
      return "STOP";
  }
}

const char *PTZ_MotorStateString(PTZ_MotorState_t state) {
  switch (state) {
    case PTZ_MOTOR_STATE_RAMP_UP:
      return "RAMP_UP";
    case PTZ_MOTOR_STATE_RUN:
      return "RUN";
    case PTZ_MOTOR_STATE_RAMP_DOWN:
      return "RAMP_DOWN";
    case PTZ_MOTOR_STATE_PIN_TEST:
      return "PIN_TEST";
    case PTZ_MOTOR_STATE_FAULT:
      return "FAULT";
    case PTZ_MOTOR_STATE_IDLE:
    default:
      return "IDLE";
  }
}

const char *PTZ_MotorFaultString(PTZ_MotorFault_t fault) {
  switch (fault) {
    case PTZ_MOTOR_FAULT_PARAM:
      return "PARAM";
    case PTZ_MOTOR_FAULT_SPEED_RANGE:
      return "SPEED_RANGE";
    case PTZ_MOTOR_FAULT_ACCEL_RANGE:
      return "ACCEL_RANGE";
    case PTZ_MOTOR_FAULT_HAL:
      return "HAL";
    case PTZ_MOTOR_FAULT_NONE:
    default:
      return "NONE";
  }
}

uint32_t PTZ_MotorHzToRpm(const PTZ_Motor_t *motor, uint32_t step_hz) {
  if (motor == NULL || motor->steps_per_rev == 0U) {
    return 0U;
  }
  return (step_hz * 60U) / motor->steps_per_rev;
}

uint32_t PTZ_MotorRpmToHz(const PTZ_Motor_t *motor, uint32_t rpm) {
  if (motor == NULL || motor->steps_per_rev == 0U) {
    return PTZ_MOTOR_MIN_SPEED_HZ;
  }
  return clamp_speed((rpm * motor->steps_per_rev) / 60U);
}
