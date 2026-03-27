# 代码更新汇总（截至 2026-03-27）

本文档汇总 `origin/main` 上次提交 `ecca8f5 (Add TMC2209 driver support)` 之后，到当前工作区为止的主要改动。

## 1. TMC2209 单线 UART 功能正式落地

这次不是只保留 `STEP / DIR / ENN` 兼容 profile，而是把 `PDN_UART` 单线寄存器读写链路补齐到了可实际联调的状态。

### 底层固件新增

- 新增 `USART1` 用作 `TMC2209 PDN_UART`
  - `PA9 -> USART1_TX`
  - `PA10 -> USART1_RX`
- 新增独立驱动层：
  - `Core/Inc/tmc2209_uart.h`
  - `Core/Src/tmc2209_uart.c`
- 支持的寄存器访问范围：
  - `GCONF`
  - `IHOLD_IRUN`
  - `CHOPCONF`
  - `PWMCONF`
  - `DRV_STATUS`
  - `IOIN`
  - `TPWMTHRS`

### 新增串口命令

当前固件支持以下 `TMC2209 UART` 相关命令：

```text
m1 tmc cfg addr <0..3>
m1 tmc cfg rsense <mohm>
m1 tmc init
m1 tmc status
m1 tmc read gconf|ihold_irun|chopconf|pwmconf|drv_status|ioin|tpwmthrs
m1 tmc write irun|ihold|iholddelay|vsense|microstep|tpwmthrs|mode <value>
```

说明：

- `addr`：配置单线 UART 地址
- `rsense`：配置相电流估算所用采样电阻
- `init`：把 GUI/固件缓存参数批量写入 `TMC2209`
- `status`：一次性读取关键寄存器并输出汇总
- `write mode stealthchop|spreadcycle`：支持运行时切换斩波模式

## 2. GUI 增加 TMC2209 专属 UART 配置区

现有 GUI 在 `TMC2209` 驱动模式下会显示专属配置面板，支持直接调试寄存器相关参数。

### GUI 新增内容

- `TMC2209 UART` 面板
- 地址配置 `Addr`
- 采样电阻配置 `Rsense`
- 电流参数：
  - `IRUN`
  - `IHOLD`
  - `IHOLDDELAY`
- 模式切换：
  - `Stealth`
  - `Spread`
- `VSENSE` 开关
- 电流估算显示
- 在线状态显示 `online/offline`

### GUI 与固件联动

- `TMC2209` 模式下，`steps/rev` 与 `microstep` 会联动 `CHOPCONF.mres`
- GUI 里发起 `Read / Init / Apply Current / Mode` 等操作时，直接调用新增的 `tmc` 串口命令

## 3. TMC2209 起步策略继续保守化

为改善同步带或带载场景下的起步跳齿问题，`TMC2209` 的默认加速度和低速起步阶段做了额外限制：

- 默认加速度：`600 Hz/s`
- 当速度处于 `0..800 Hz` 区间时：
  - 有效加速度进一步压到 `300 Hz/s`

这层限制与 `UART` 功能无关，即使暂时不连 `PDN_UART` 也生效。

## 4. 文档与接线图更新

### 文档更新

- `README.md`
  - 增补 `TMC2209 UART` 功能说明
  - 更新 `USART1 PA9/PA10` 接线说明
  - 更新可用命令列表
- `docs/tmc2209_adaptation_guide.md`
  - 从“UART 仅预留”改为“UART 已支持”
  - 补充当前接线、寄存器能力和运行边界

### 新增接线图

- `docs/stm32c031c6_tmc2209_wiring.svg`
- `docs/stm32c031c6_tmc2209_wiring.png`
- `docs/stm32c031c6_tmc2209_wiring.jpg`

当前接线图已调整为 **单轴**，并明确：

- `PA8 -> STEP`
- `PA0 -> DIR`
- `PA1 -> ENN`
- `PA9 / USART1_TX -> 1k -> PDN_UART`
- `PA10 / USART1_RX -> PDN_UART`

## 5. 构建系统调整

这次增加 `TMC2209 UART` 后，固件体积继续上涨，因此构建参数做了一个必要调整：

- 编译优化从 `-Og` 调整为 `-Os`

目的很明确：

- 避免超出 `STM32C031C6T6` 的 `32KB Flash`
- 保持当前功能集仍可正常链接和烧录

## 6. 本轮改动涉及的核心文件

- `Core/Inc/main.h`
- `Core/Inc/ptz_motor.h`
- `Core/Inc/tmc2209_uart.h`
- `Core/Src/main.c`
- `Core/Src/ptz_motor.c`
- `Core/Src/tmc2209_uart.c`
- `Core/Src/ui_uart.c`
- `tools/ptz_gui.py`
- `README.md`
- `docs/tmc2209_adaptation_guide.md`

## 7. 当前结果

截至本次整理，代码已具备：

1. `GC6609 / DM556 / A4988 / TMC2209` 四类驱动运行时切换
2. `TMC2209` 单线 UART 配置读写
3. GUI 侧 `TMC2209 UART` 调试能力
4. 单轴 `TMC2209` 明确接线图

后续如果继续往前推进，优先级建议是：

1. 把 `DIAG` 接回 MCU
2. 增加 `DRV_STATUS` 异常联动
3. 再评估 `CoolStep / StallGuard` 配置路径
