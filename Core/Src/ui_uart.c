#include "ui_uart.h"
#include "build_info.h"

#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define UI_LINE_BUF_LEN 96U
#define UI_TX_BUF_LEN 512U

#ifndef PTZ_FW_NAME
#define PTZ_FW_NAME "ptz_demo_c031c6"
#endif

#ifndef PTZ_BUILD_TIME
#define PTZ_BUILD_TIME __DATE__ " " __TIME__
#endif

static UART_HandleTypeDef *s_huart = NULL;
static PTZ_Motor_t *s_m1 = NULL;
static PTZ_Motor_t *s_m2 = NULL;

static uint8_t s_rx_char = 0U;
static volatile uint8_t s_line_ready = 0U;
static volatile uint8_t s_line_len = 0U;
static volatile uint8_t s_overflow = 0U;
static uint8_t s_telemetry_enabled = 1U;
static char s_line_buf[UI_LINE_BUF_LEN];
static const char s_fw_name[] = PTZ_FW_NAME;
static const char s_build_time[] = PTZ_BUILD_TIME;

static void ui_printf(const char *fmt, ...) {
  char tx[UI_TX_BUF_LEN];
  va_list ap;
  int n;

  if (s_huart == NULL) {
    return;
  }

  va_start(ap, fmt);
  n = vsnprintf(tx, sizeof(tx), fmt, ap);
  va_end(ap);

  if (n <= 0) {
    return;
  }
  if (n >= (int)sizeof(tx)) {
    n = (int)sizeof(tx) - 1;
  }
  HAL_UART_Transmit(s_huart, (uint8_t *)tx, (uint16_t)n, 100U);
}

static void ui_ok(const char *fmt, ...) {
  char msg[UI_TX_BUF_LEN - 8U];
  va_list ap;
  int n;

  va_start(ap, fmt);
  n = vsnprintf(msg, sizeof(msg), fmt, ap);
  va_end(ap);
  if (n < 0) {
    return;
  }
  ui_printf("OK %s\r\n", msg);
}

static void ui_err(const char *code, const char *detail) {
  ui_printf("ERR code=%s detail=%s\r\n", code, detail);
}

static void to_lower_inplace(char *s) {
  while (*s != '\0') {
    *s = (char)tolower((unsigned char)*s);
    s++;
  }
}

static uint8_t split_args(char *line, char *argv[], uint8_t max_args) {
  uint8_t argc = 0U;
  char *tok = strtok(line, " \t");
  while (tok != NULL && argc < max_args) {
    argv[argc++] = tok;
    tok = strtok(NULL, " \t");
  }
  return argc;
}

static uint8_t parse_u32(const char *text, uint32_t *value) {
  char *endptr = NULL;
  unsigned long raw;

  if (text == NULL || value == NULL) {
    return 0U;
  }

  raw = strtoul(text, &endptr, 10);
  if (endptr == text || *endptr != '\0') {
    return 0U;
  }

  *value = (uint32_t)raw;
  return 1U;
}

static uint8_t parse_microstep(const char *text, uint32_t *microstep) {
  uint32_t raw = 0U;

  if (!parse_u32(text, &raw) || microstep == NULL) {
    return 0U;
  }

  if (raw == 1U || raw == 2U || raw == 4U || raw == 8U || raw == 16U) {
    *microstep = raw;
    return 1U;
  }

  return 0U;
}

static PTZ_Motor_t *motor_from_axis(const char *axis_name) {
  if (strcmp(axis_name, "m1") == 0) {
    return s_m1;
  }
  if (strcmp(axis_name, "m2") == 0) {
    return s_m2;
  }
  return NULL;
}

static uint8_t parse_driver(const char *text, PTZ_MotorDriver_t *driver) {
  if (text == NULL || driver == NULL) {
    return 0U;
  }
  if (strcmp(text, "gc6609") == 0) {
    *driver = PTZ_DRIVER_GC6609;
    return 1U;
  }
  if (strcmp(text, "dm556") == 0) {
    *driver = PTZ_DRIVER_DM556;
    return 1U;
  }
  if (strcmp(text, "a4988") == 0) {
    *driver = PTZ_DRIVER_A4988;
    return 1U;
  }
  return 0U;
}

static void print_version(void) {
  ui_printf("BUILD fw=%s time=%s\r\n", s_fw_name, s_build_time);
}

static void print_help(void) {
  ui_printf("\r\n=== PTZ Console ===\r\n");
  ui_printf("status                     : print one structured status frame\r\n");
  ui_printf("version                    : print firmware build info\r\n");
  ui_printf("telemetry on/off           : enable or disable periodic STAT output\r\n");
  ui_printf("all stop                   : stop both motors\r\n");
  ui_printf("m1 f <hz>                  : run M1 forward\r\n");
  ui_printf("m1 r <hz>                  : run M1 reverse\r\n");
  ui_printf("m1 s                       : stop M1 with ramp-down\r\n");
  ui_printf("m1 jog f <hz> <ms>         : firmware-side jog\r\n");
  ui_printf("m1 cfg accel <hzps>        : set M1 acceleration\r\n");
  ui_printf("m1 cfg driver gc6609|dm556|a4988 : switch M1 driver profile\r\n");
  ui_printf("m1 cfg steps <steps_rev>   : set M1 logical steps per rev\r\n");
  ui_printf("m1 cfg microstep 1|2|4|8|16: set M1 A4988 logical microstep\r\n");
  ui_printf("m1 cfg wakeup <us>         : set M1 wakeup delay before first step\r\n");
  ui_printf("m1 diag                    : print M1 diagnostic line\r\n");
  ui_printf("m1 clear                   : clear M1 fault latch\r\n");
  ui_printf("m1 pin dir/en/step hi/lo   : force pin state for probing\r\n");
  ui_printf("m1 pin restore             : restore normal run mode\r\n");
  ui_printf("m2 ...                     : same commands for motor 2\r\n");
  ui_printf("speed_hz range=%lu..%lu accel_hzps range=%lu..%lu\r\n\r\n",
            (unsigned long)PTZ_MOTOR_MIN_SPEED_HZ,
            (unsigned long)PTZ_MOTOR_MAX_SPEED_HZ,
            (unsigned long)PTZ_MOTOR_MIN_ACCEL_HZPS,
            (unsigned long)PTZ_MOTOR_MAX_ACCEL_HZPS);
}

static void print_status_line(void) {
  ui_printf(
      "STAT tick=%lu telemetry=%u "
      "m1_drv=%s m1_steps_rev=%lu m1_wakeup_us=%lu m1_state=%s m1_dir=%s m1_target_hz=%lu m1_actual_hz=%lu m1_rpm=%lu m1_zero=%u m1_edges=%lu m1_accel_hzps=%lu m1_fault=%s m1_override=%u "
      "m2_drv=%s m2_steps_rev=%lu m2_wakeup_us=%lu m2_state=%s m2_dir=%s m2_target_hz=%lu m2_actual_hz=%lu m2_rpm=%lu m2_zero=%u m2_edges=%lu m2_accel_hzps=%lu m2_fault=%s m2_override=%u\r\n",
      (unsigned long)HAL_GetTick(),
      (unsigned)s_telemetry_enabled,
      PTZ_MotorDriverString((PTZ_MotorDriver_t)s_m1->driver),
      (unsigned long)s_m1->steps_per_rev,
      (unsigned long)s_m1->wakeup_delay_us,
      PTZ_MotorStateString((PTZ_MotorState_t)s_m1->state),
      PTZ_MotorDirString((PTZ_MotorDir_t)s_m1->dir),
      (unsigned long)s_m1->cmd_speed_hz,
      (unsigned long)s_m1->actual_speed_hz,
      (unsigned long)PTZ_MotorHzToRpm(s_m1, s_m1->actual_speed_hz),
      (unsigned)s_m1->zero_active,
      (unsigned long)s_m1->zero_edges,
      (unsigned long)s_m1->accel_hzps,
      PTZ_MotorFaultString((PTZ_MotorFault_t)s_m1->fault),
      (unsigned)s_m1->pin_override_active,
      PTZ_MotorDriverString((PTZ_MotorDriver_t)s_m2->driver),
      (unsigned long)s_m2->steps_per_rev,
      (unsigned long)s_m2->wakeup_delay_us,
      PTZ_MotorStateString((PTZ_MotorState_t)s_m2->state),
      PTZ_MotorDirString((PTZ_MotorDir_t)s_m2->dir),
      (unsigned long)s_m2->cmd_speed_hz,
      (unsigned long)s_m2->actual_speed_hz,
      (unsigned long)PTZ_MotorHzToRpm(s_m2, s_m2->actual_speed_hz),
      (unsigned)s_m2->zero_active,
      (unsigned long)s_m2->zero_edges,
      (unsigned long)s_m2->accel_hzps,
      PTZ_MotorFaultString((PTZ_MotorFault_t)s_m2->fault),
      (unsigned)s_m2->pin_override_active);
}

static void print_diag_line(const char *axis_name, const PTZ_Motor_t *motor) {
  ui_printf(
      "DIAG motor=%s driver=%s steps_rev=%lu wakeup_us=%lu state=%s dir=%s target_hz=%lu actual_hz=%lu rpm=%lu accel_hzps=%lu zero=%u zero_edges=%lu last_zero_ms=%lu jog_until_ms=%lu fault=%s override=%u\r\n",
      axis_name,
      PTZ_MotorDriverString((PTZ_MotorDriver_t)motor->driver),
      (unsigned long)motor->steps_per_rev,
      (unsigned long)motor->wakeup_delay_us,
      PTZ_MotorStateString((PTZ_MotorState_t)motor->state),
      PTZ_MotorDirString((PTZ_MotorDir_t)motor->dir),
      (unsigned long)motor->cmd_speed_hz,
      (unsigned long)motor->actual_speed_hz,
      (unsigned long)PTZ_MotorHzToRpm(motor, motor->actual_speed_hz),
      (unsigned long)motor->accel_hzps,
      (unsigned)motor->zero_active,
      (unsigned long)motor->zero_edges,
      (unsigned long)motor->last_zero_tick_ms,
      (unsigned long)motor->jog_until_ms,
      PTZ_MotorFaultString((PTZ_MotorFault_t)motor->fault),
      (unsigned)motor->pin_override_active);
}

static void run_pin_cmd(PTZ_Motor_t *m, const char *axis_name, uint8_t argc, char *argv[]) {
  PTZ_MotorPin_t pin = PTZ_MOTOR_PIN_DIR;
  GPIO_PinState state = GPIO_PIN_RESET;
  const char *pin_name = NULL;
  const char *level_name = NULL;

  if (argc < 3U) {
    ui_err("PIN_ARGS", "missing_pin_test_args");
    return;
  }

  if (strcmp(argv[2], "restore") == 0 || strcmp(argv[2], "run") == 0) {
    PTZ_MotorPinRestore(m);
    ui_ok("motor=%s action=pin_restore", axis_name);
    return;
  }

  if (argc < 4U) {
    ui_err("PIN_LEVEL", "missing_pin_level");
    return;
  }

  if (strcmp(argv[2], "dir") == 0) {
    pin = PTZ_MOTOR_PIN_DIR;
    pin_name = "DIR";
  } else if (strcmp(argv[2], "en") == 0) {
    pin = PTZ_MOTOR_PIN_EN;
    pin_name = "EN";
  } else if (strcmp(argv[2], "step") == 0) {
    pin = PTZ_MOTOR_PIN_STEP;
    pin_name = "STEP";
  } else {
    ui_err("PIN_NAME", "unknown_pin");
    return;
  }

  if (strcmp(argv[3], "hi") == 0 || strcmp(argv[3], "high") == 0 || strcmp(argv[3], "1") == 0) {
    state = GPIO_PIN_SET;
    level_name = "HIGH";
  } else if (strcmp(argv[3], "lo") == 0 || strcmp(argv[3], "low") == 0 || strcmp(argv[3], "0") == 0) {
    state = GPIO_PIN_RESET;
    level_name = "LOW";
  } else if ((strcmp(argv[3], "af") == 0 || strcmp(argv[3], "restore") == 0) && pin == PTZ_MOTOR_PIN_STEP) {
    PTZ_MotorPinRestore(m);
    ui_ok("motor=%s action=pin_restore pin=STEP", axis_name);
    return;
  } else {
    ui_err("PIN_LEVEL", "invalid_pin_level");
    return;
  }

  PTZ_MotorPinWrite(m, pin, state);
  ui_ok("motor=%s action=pin pin=%s level=%s", axis_name, pin_name, level_name);
}

static void run_motor_cmd(PTZ_Motor_t *m, const char *axis_name, uint8_t argc, char *argv[]) {
  PTZ_MotorResult_t ret = PTZ_MOTOR_ERR_PARAM;
  uint32_t speed_hz = 0U;
  uint32_t duration_ms = 0U;
  uint32_t accel_hzps = 0U;
  uint32_t steps_per_rev = 0U;
  uint32_t wakeup_delay_us = 0U;
  uint32_t microstep = 0U;
  PTZ_MotorDriver_t driver = PTZ_DRIVER_GC6609;
  PTZ_MotorDir_t dir = PTZ_MOTOR_STOP;

  if (argc < 2U) {
    ui_err("ARGS", "missing_motor_args");
    return;
  }

  if (strcmp(argv[1], "s") == 0 || strcmp(argv[1], "stop") == 0) {
    PTZ_MotorStop(m);
    ui_ok("motor=%s action=stop", axis_name);
    return;
  }

  if (strcmp(argv[1], "clear") == 0) {
    PTZ_MotorClearFault(m);
    ui_ok("motor=%s action=clear_fault", axis_name);
    return;
  }

  if (strcmp(argv[1], "diag") == 0) {
    print_diag_line(axis_name, m);
    return;
  }

  if (strcmp(argv[1], "cfg") == 0) {
    if (argc < 4U) {
      ui_err("CFG_ARGS", "missing_cfg_args");
      return;
    }
    if (strcmp(argv[2], "accel") == 0) {
      if (!parse_u32(argv[3], &accel_hzps)) {
        ui_err("CFG_VALUE", "invalid_accel");
        return;
      }
      ret = PTZ_MotorSetAccel(m, accel_hzps);
      if (ret == PTZ_MOTOR_OK) {
        ui_ok("motor=%s action=set_accel accel_hzps=%lu", axis_name, (unsigned long)m->accel_hzps);
      } else {
        ui_err("ACCEL_RANGE", "accel_out_of_range");
      }
      return;
    }
    if (strcmp(argv[2], "driver") == 0) {
      if (!parse_driver(argv[3], &driver)) {
        ui_err("CFG_VALUE", "invalid_driver");
        return;
      }
      ret = PTZ_MotorSetDriver(m, driver);
      if (ret == PTZ_MOTOR_OK) {
        ui_ok("motor=%s action=set_driver driver=%s steps_rev=%lu", axis_name,
              PTZ_MotorDriverString((PTZ_MotorDriver_t)m->driver), (unsigned long)m->steps_per_rev);
      } else if (ret == PTZ_MOTOR_ERR_BUSY) {
        ui_err("BUSY", "pin_override_active");
      } else {
        ui_err("DRIVER", "driver_set_failed");
      }
      return;
    }
    if (strcmp(argv[2], "steps") == 0 || strcmp(argv[2], "steps_rev") == 0) {
      if (!parse_u32(argv[3], &steps_per_rev)) {
        ui_err("CFG_VALUE", "invalid_steps_rev");
        return;
      }
      ret = PTZ_MotorSetStepsPerRev(m, steps_per_rev);
      if (ret == PTZ_MOTOR_OK) {
        ui_ok("motor=%s action=set_steps_rev steps_rev=%lu", axis_name, (unsigned long)m->steps_per_rev);
      } else if (ret == PTZ_MOTOR_ERR_STEPS_RANGE) {
        ui_err("STEPS_RANGE", "steps_rev_out_of_range");
      } else if (ret == PTZ_MOTOR_ERR_BUSY) {
        ui_err("BUSY", "pin_override_active");
      } else {
        ui_err("STEPS", "steps_rev_set_failed");
      }
      return;
    }
    if (strcmp(argv[2], "microstep") == 0) {
      if (m->driver != PTZ_DRIVER_A4988) {
        ui_err("CFG_ITEM", "microstep_only_for_a4988");
        return;
      }
      if (!parse_microstep(argv[3], &microstep)) {
        ui_err("CFG_VALUE", "invalid_microstep");
        return;
      }
      ret = PTZ_MotorSetStepsPerRev(m, 200U * microstep);
      if (ret == PTZ_MOTOR_OK) {
        ui_ok("motor=%s action=set_microstep microstep=%lu steps_rev=%lu", axis_name, (unsigned long)microstep,
              (unsigned long)m->steps_per_rev);
      } else if (ret == PTZ_MOTOR_ERR_STEPS_RANGE) {
        ui_err("STEPS_RANGE", "steps_rev_out_of_range");
      } else if (ret == PTZ_MOTOR_ERR_BUSY) {
        ui_err("BUSY", "pin_override_active");
      } else {
        ui_err("MICROSTEP", "microstep_set_failed");
      }
      return;
    }
    if (strcmp(argv[2], "wakeup") == 0 || strcmp(argv[2], "wakeup_us") == 0) {
      if (!parse_u32(argv[3], &wakeup_delay_us)) {
        ui_err("CFG_VALUE", "invalid_wakeup_us");
        return;
      }
      ret = PTZ_MotorSetWakeupDelayUs(m, wakeup_delay_us);
      if (ret == PTZ_MOTOR_OK) {
        ui_ok("motor=%s action=set_wakeup wakeup_us=%lu", axis_name, (unsigned long)m->wakeup_delay_us);
      } else if (ret == PTZ_MOTOR_ERR_WAKEUP_RANGE) {
        ui_err("WAKEUP_RANGE", "wakeup_us_out_of_range");
      } else if (ret == PTZ_MOTOR_ERR_BUSY) {
        ui_err("BUSY", "pin_override_active");
      } else {
        ui_err("WAKEUP", "wakeup_set_failed");
      }
      return;
    }
    ui_err("CFG_ITEM", "unknown_cfg_item");
    return;
  }

  if (strcmp(argv[1], "pin") == 0) {
    run_pin_cmd(m, axis_name, argc, argv);
    return;
  }

  if (strcmp(argv[1], "jog") == 0) {
    if (argc < 5U) {
      ui_err("JOG_ARGS", "missing_jog_args");
      return;
    }
    if (strcmp(argv[2], "f") == 0 || strcmp(argv[2], "forward") == 0) {
      dir = PTZ_MOTOR_FORWARD;
    } else if (strcmp(argv[2], "r") == 0 || strcmp(argv[2], "reverse") == 0) {
      dir = PTZ_MOTOR_REVERSE;
    } else {
      ui_err("DIR", "invalid_jog_dir");
      return;
    }
    if (!parse_u32(argv[3], &speed_hz) || !parse_u32(argv[4], &duration_ms)) {
      ui_err("JOG_VALUE", "invalid_jog_value");
      return;
    }
    ret = PTZ_MotorJog(m, dir, speed_hz, duration_ms);
    if (ret == PTZ_MOTOR_OK) {
      ui_ok("motor=%s action=jog dir=%s target_hz=%lu duration_ms=%lu", axis_name, PTZ_MotorDirString(dir),
            (unsigned long)speed_hz, (unsigned long)duration_ms);
    } else if (ret == PTZ_MOTOR_ERR_SPEED_RANGE) {
      ui_err("SPEED_RANGE", "speed_out_of_range");
    } else if (ret == PTZ_MOTOR_ERR_BUSY) {
      ui_err("BUSY", "pin_override_active");
    } else {
      ui_err("JOG", "command_failed");
    }
    return;
  }

  if (argc < 3U) {
    ui_err("SPEED", "missing_speed");
    return;
  }

  if (strcmp(argv[1], "f") == 0 || strcmp(argv[1], "forward") == 0) {
    dir = PTZ_MOTOR_FORWARD;
  } else if (strcmp(argv[1], "r") == 0 || strcmp(argv[1], "reverse") == 0) {
    dir = PTZ_MOTOR_REVERSE;
  } else {
    ui_err("DIR", "unknown_direction");
    return;
  }

  if (!parse_u32(argv[2], &speed_hz)) {
    ui_err("SPEED", "invalid_speed");
    return;
  }

  ret = PTZ_MotorCommand(m, dir, speed_hz);
  if (ret == PTZ_MOTOR_OK) {
    ui_ok("motor=%s action=run dir=%s target_hz=%lu", axis_name, PTZ_MotorDirString(dir), (unsigned long)speed_hz);
  } else if (ret == PTZ_MOTOR_ERR_SPEED_RANGE) {
    ui_err("SPEED_RANGE", "speed_out_of_range");
  } else if (ret == PTZ_MOTOR_ERR_BUSY) {
    ui_err("BUSY", "pin_override_active");
  } else {
    ui_err("RUN", "command_failed");
  }
}

static void parse_and_execute(char *line) {
  char *argv[8];
  uint8_t argc;
  PTZ_Motor_t *motor;

  to_lower_inplace(line);
  argc = split_args(line, argv, 8U);
  if (argc == 0U) {
    return;
  }

  if (strcmp(argv[0], "help") == 0) {
    print_help();
    return;
  }

  if (strcmp(argv[0], "status") == 0) {
    print_status_line();
    return;
  }

  if (strcmp(argv[0], "version") == 0 || strcmp(argv[0], "ver") == 0) {
    print_version();
    return;
  }

  if (strcmp(argv[0], "telemetry") == 0) {
    if (argc < 2U) {
      ui_err("TELEM", "missing_telemetry_value");
      return;
    }
    if (strcmp(argv[1], "on") == 0 || strcmp(argv[1], "1") == 0) {
      s_telemetry_enabled = 1U;
      ui_ok("action=telemetry value=on");
    } else if (strcmp(argv[1], "off") == 0 || strcmp(argv[1], "0") == 0) {
      s_telemetry_enabled = 0U;
      ui_ok("action=telemetry value=off");
    } else {
      ui_err("TELEM", "invalid_telemetry_value");
    }
    return;
  }

  if (strcmp(argv[0], "all") == 0 && argc >= 2U &&
      (strcmp(argv[1], "s") == 0 || strcmp(argv[1], "stop") == 0)) {
    PTZ_MotorStop(s_m1);
    PTZ_MotorStop(s_m2);
    ui_ok("action=stop_all");
    return;
  }

  motor = motor_from_axis(argv[0]);
  if (motor != NULL) {
    run_motor_cmd(motor, (strcmp(argv[0], "m1") == 0) ? "M1" : "M2", argc, argv);
    return;
  }

  ui_err("CMD", "unknown_command");
}

void UI_Init(UART_HandleTypeDef *huart, PTZ_Motor_t *m1, PTZ_Motor_t *m2) {
  s_huart = huart;
  s_m1 = m1;
  s_m2 = m2;
  s_line_ready = 0U;
  s_line_len = 0U;
  s_overflow = 0U;
  s_telemetry_enabled = 1U;
  memset(s_line_buf, 0, sizeof(s_line_buf));

  HAL_UART_Receive_IT(s_huart, &s_rx_char, 1U);
  ui_printf("\r\nREADY fw=%s\r\n", s_fw_name);
  print_version();
  print_status_line();
}

void UI_Process(void) {
  char line_local[UI_LINE_BUF_LEN];

  if (s_overflow) {
    s_overflow = 0U;
    ui_err("LINE", "line_too_long");
  }

  if (!s_line_ready) {
    return;
  }

  __disable_irq();
  strncpy(line_local, s_line_buf, sizeof(line_local) - 1U);
  line_local[sizeof(line_local) - 1U] = '\0';
  s_line_ready = 0U;
  s_line_len = 0U;
  memset(s_line_buf, 0, sizeof(s_line_buf));
  __enable_irq();

  parse_and_execute(line_local);
}

void UI_ReportRealtime(void) {
  if (!s_telemetry_enabled) {
    return;
  }
  print_status_line();
}

uint8_t UI_TelemetryEnabled(void) {
  return s_telemetry_enabled;
}

void UI_OnUartRxCplt(UART_HandleTypeDef *huart) {
  if (huart != s_huart) {
    return;
  }

  if (!s_line_ready) {
    if (s_rx_char == '\r' || s_rx_char == '\n') {
      if (s_line_len > 0U) {
        s_line_buf[s_line_len] = '\0';
        s_line_ready = 1U;
      }
    } else if (s_line_len < (UI_LINE_BUF_LEN - 1U)) {
      s_line_buf[s_line_len++] = (char)s_rx_char;
    } else {
      s_line_len = 0U;
      memset(s_line_buf, 0, sizeof(s_line_buf));
      s_overflow = 1U;
    }
  }

  HAL_UART_Receive_IT(s_huart, &s_rx_char, 1U);
}
