TARGET := ptz_demo_c031c6
BUILD_DIR := build
BUILD_TIME := $(shell date '+%Y-%m-%dT%H:%M:%S%z')
BUILD_INFO_HEADER := $(BUILD_DIR)/build_info.h

XPACK_GCC_BIN := $(HOME)/Library/xPacks/@xpack-dev-tools/arm-none-eabi-gcc/15.2.1-1.1.1/.content/bin
XPACK_OPENOCD := $(HOME)/Library/xPacks/@xpack-dev-tools/openocd/0.12.0-7.1/.content/bin/openocd
ifneq ($(wildcard $(XPACK_GCC_BIN)/arm-none-eabi-gcc),)
CROSS_COMPILE ?= $(XPACK_GCC_BIN)/arm-none-eabi-
else
CROSS_COMPILE ?= arm-none-eabi-
endif
ifneq ($(wildcard $(XPACK_OPENOCD)),)
OPENOCD ?= $(XPACK_OPENOCD)
else
OPENOCD ?= openocd
endif

CC := $(CROSS_COMPILE)gcc
AS := $(CROSS_COMPILE)gcc
OBJCOPY := $(CROSS_COMPILE)objcopy
SIZE := $(CROSS_COMPILE)size

CPUFLAGS := -mcpu=cortex-m0plus -mthumb
OPT := -Og
DEBUG := -g3

DEFS := -DSTM32C031xx -DUSE_HAL_DRIVER
INCLUDES := \
  -I$(BUILD_DIR) \
  -ICore/Inc \
  -I.stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Inc \
  -I.stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Inc/Legacy \
  -I.stm32cube_c0/Drivers/CMSIS/Device/ST/STM32C0xx/Include \
  -I.stm32cube_c0/Drivers/CMSIS/Include

CFLAGS := $(CPUFLAGS) $(OPT) $(DEBUG) $(DEFS) $(INCLUDES) \
  -std=gnu11 -Wall -Wextra -ffunction-sections -fdata-sections
DEPFLAGS := -MMD -MP
ASFLAGS := $(CPUFLAGS) $(DEBUG) -x assembler-with-cpp
LDFLAGS := $(CPUFLAGS) -Tlinker/STM32C031C6TX_FLASH.ld \
  -Wl,-Map=$(BUILD_DIR)/$(TARGET).map,--cref -Wl,--gc-sections \
  -specs=nano.specs -specs=nosys.specs

APP_SRCS := \
  Core/Src/main.c \
  Core/Src/ptz_motor.c \
  Core/Src/ui_uart.c \
  Core/Src/stm32c0xx_it.c \
  Core/Src/system_stm32c0xx.c

HAL_SRCS := \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_cortex.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_dma.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_exti.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_flash.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_flash_ex.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_gpio.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_pwr.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_pwr_ex.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_rcc.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_rcc_ex.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_tim.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_tim_ex.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_uart.c \
  .stm32cube_c0/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_uart_ex.c

STARTUP_SRCS := startup/startup_stm32c031c6tx.s

C_SRCS := $(APP_SRCS) $(HAL_SRCS)
S_SRCS := $(STARTUP_SRCS)
OBJS := $(addprefix $(BUILD_DIR)/,$(C_SRCS:.c=.o)) \
        $(addprefix $(BUILD_DIR)/,$(S_SRCS:.s=.o))
DEPS := $(OBJS:.o=.d)

.PHONY: all clean size flash FORCE

all: $(BUILD_DIR)/$(TARGET).bin $(BUILD_DIR)/$(TARGET).hex size

$(BUILD_INFO_HEADER): FORCE
	@mkdir -p $(dir $@)
	@printf '%s\n' \
	  '#ifndef PTZ_BUILD_INFO_H' \
	  '#define PTZ_BUILD_INFO_H' \
	  '#define PTZ_FW_NAME "$(TARGET)"' \
	  '#define PTZ_BUILD_TIME "$(BUILD_TIME)"' \
	  '#endif' > $@

$(BUILD_DIR)/$(TARGET).elf: $(OBJS)
	@mkdir -p $(dir $@)
	$(CC) $(OBJS) $(LDFLAGS) -o $@

$(BUILD_DIR)/$(TARGET).hex: $(BUILD_DIR)/$(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

$(BUILD_DIR)/$(TARGET).bin: $(BUILD_DIR)/$(TARGET).elf
	$(OBJCOPY) -O binary -S $< $@

$(BUILD_DIR)/%.o: %.c $(BUILD_INFO_HEADER)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(DEPFLAGS) -c $< -o $@

$(BUILD_DIR)/%.o: %.s
	@mkdir -p $(dir $@)
	$(AS) $(ASFLAGS) -c $< -o $@

size: $(BUILD_DIR)/$(TARGET).elf
	$(SIZE) $<

clean:
	rm -rf $(BUILD_DIR)

FORCE:

flash: $(BUILD_DIR)/$(TARGET).hex
	@if command -v STM32_Programmer_CLI >/dev/null 2>&1; then \
	  STM32_Programmer_CLI -c port=SWD mode=UR -w $< -v -rst; \
	elif command -v st-flash >/dev/null 2>&1; then \
	  st-flash --reset write $(BUILD_DIR)/$(TARGET).bin 0x08000000; \
	elif command -v $(OPENOCD) >/dev/null 2>&1; then \
	  $(OPENOCD) -f interface/stlink.cfg -f target/stm32c0x.cfg \
	    -c "program $(BUILD_DIR)/$(TARGET).elf verify reset exit"; \
	else \
	  echo "No ST-LINK flash tool found. Install STM32CubeProgrammer/stlink/openocd."; \
	  exit 1; \
	fi

-include $(DEPS)
