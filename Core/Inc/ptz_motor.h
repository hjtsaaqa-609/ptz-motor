#ifndef PTZ_MOTOR_H
#define PTZ_MOTOR_H

#include "main.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PTZ_MOTOR_MIN_SPEED_HZ 10U
#define PTZ_MOTOR_MAX_SPEED_HZ 50000U
#define PTZ_MOTOR_DEFAULT_ACCEL_HZPS 1600U
#define PTZ_MOTOR_MIN_ACCEL_HZPS 100U
#define PTZ_MOTOR_MAX_ACCEL_HZPS 50000U

#define PTZ_MOTOR_ZERO_ACTIVE_LEVEL GPIO_PIN_RESET

#define PTZ_MOTOR_GC6609_STEPS_PER_REV 1600U
#define PTZ_MOTOR_DM556_STEPS_PER_REV 1600U

typedef enum {
  PTZ_MOTOR_STOP = 0,
  PTZ_MOTOR_FORWARD,
  PTZ_MOTOR_REVERSE
} PTZ_MotorDir_t;

typedef enum {
  PTZ_MOTOR_STATE_IDLE = 0,
  PTZ_MOTOR_STATE_RAMP_UP,
  PTZ_MOTOR_STATE_RUN,
  PTZ_MOTOR_STATE_RAMP_DOWN,
  PTZ_MOTOR_STATE_PIN_TEST,
  PTZ_MOTOR_STATE_FAULT
} PTZ_MotorState_t;

typedef enum {
  PTZ_MOTOR_FAULT_NONE = 0,
  PTZ_MOTOR_FAULT_PARAM,
  PTZ_MOTOR_FAULT_SPEED_RANGE,
  PTZ_MOTOR_FAULT_ACCEL_RANGE,
  PTZ_MOTOR_FAULT_HAL
} PTZ_MotorFault_t;

typedef enum {
  PTZ_MOTOR_OK = 0,
  PTZ_MOTOR_ERR_PARAM,
  PTZ_MOTOR_ERR_SPEED_RANGE,
  PTZ_MOTOR_ERR_ACCEL_RANGE,
  PTZ_MOTOR_ERR_BUSY
} PTZ_MotorResult_t;

typedef enum {
  PTZ_MOTOR_PIN_DIR = 0,
  PTZ_MOTOR_PIN_EN,
  PTZ_MOTOR_PIN_STEP
} PTZ_MotorPin_t;

typedef enum {
  PTZ_DRIVER_GC6609 = 0,
  PTZ_DRIVER_DM556
} PTZ_MotorDriver_t;

typedef struct {
  TIM_HandleTypeDef *htim;
  uint32_t channel;

  GPIO_TypeDef *step_port;
  uint16_t step_pin;
  uint32_t step_af;

  GPIO_TypeDef *dir_port;
  uint16_t dir_pin;

  GPIO_TypeDef *en_port;
  uint16_t en_pin;

  GPIO_TypeDef *zero_port;
  uint16_t zero_pin;

  uint32_t timer_tick_hz;
  volatile PTZ_MotorDriver_t driver;
  volatile PTZ_MotorDir_t dir;
  volatile PTZ_MotorDir_t target_dir;
  volatile PTZ_MotorState_t state;
  volatile PTZ_MotorFault_t fault;
  volatile uint32_t cmd_speed_hz;
  volatile uint32_t actual_speed_hz;
  volatile uint32_t accel_hzps;
  volatile uint32_t pulse_interval_ticks;
  volatile uint32_t steps_per_rev;
  volatile uint32_t jog_until_ms;
  volatile uint32_t zero_edges;
  volatile uint32_t last_zero_tick_ms;
  volatile uint16_t setup_delay_loops;
  volatile uint8_t running;
  volatile uint8_t zero_active;
  volatile uint8_t pin_override_active;
  volatile GPIO_PinState en_active_level;
  volatile GPIO_PinState dir_fwd_level;
  volatile GPIO_PinState dir_rev_level;
} PTZ_Motor_t;

void PTZ_MotorInit(PTZ_Motor_t *motor,
                   TIM_HandleTypeDef *htim,
                   uint32_t channel,
                   GPIO_TypeDef *step_port, uint16_t step_pin, uint32_t step_af,
                   GPIO_TypeDef *dir_port, uint16_t dir_pin,
                   GPIO_TypeDef *en_port, uint16_t en_pin,
                   GPIO_TypeDef *zero_port, uint16_t zero_pin,
                   uint32_t timer_tick_hz);

PTZ_MotorResult_t PTZ_MotorCommand(PTZ_Motor_t *motor, PTZ_MotorDir_t dir, uint32_t speed_hz);
PTZ_MotorResult_t PTZ_MotorJog(PTZ_Motor_t *motor, PTZ_MotorDir_t dir, uint32_t speed_hz, uint32_t duration_ms);
PTZ_MotorResult_t PTZ_MotorSetAccel(PTZ_Motor_t *motor, uint32_t accel_hzps);
PTZ_MotorResult_t PTZ_MotorSetDriver(PTZ_Motor_t *motor, PTZ_MotorDriver_t driver);
void PTZ_MotorStop(PTZ_Motor_t *motor);
void PTZ_MotorEmergencyStop(PTZ_Motor_t *motor, PTZ_MotorFault_t fault);
void PTZ_MotorClearFault(PTZ_Motor_t *motor);
void PTZ_MotorService(PTZ_Motor_t *motor, uint32_t now_ms, uint32_t dt_ms);
void PTZ_MotorOnTimerCompare(PTZ_Motor_t *motor);
void PTZ_MotorPinWrite(PTZ_Motor_t *motor, PTZ_MotorPin_t pin, GPIO_PinState state);
void PTZ_MotorPinRestore(PTZ_Motor_t *motor);
void PTZ_MotorZeroUpdate(PTZ_Motor_t *motor);
const char *PTZ_MotorDriverString(PTZ_MotorDriver_t driver);
const char *PTZ_MotorDirString(PTZ_MotorDir_t dir);
const char *PTZ_MotorStateString(PTZ_MotorState_t state);
const char *PTZ_MotorFaultString(PTZ_MotorFault_t fault);
uint32_t PTZ_MotorHzToRpm(const PTZ_Motor_t *motor, uint32_t step_hz);
uint32_t PTZ_MotorRpmToHz(const PTZ_Motor_t *motor, uint32_t rpm);

#ifdef __cplusplus
}
#endif

#endif /* PTZ_MOTOR_H */
