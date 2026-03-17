# STM32C031C6 对接 TMC2209 模块调整说明

## 当前支持范围

当前仓库对 `TMC2209` 的支持范围是：

- `STEP / DIR / ENN` 独立模式
- 每轴运行时切换 `driver=tmc2209`
- `steps_per_rev` 运行时换算
- `microstep` 逻辑配置：`8 / 16 / 32 / 64`
- `wakeup_us` 起转前等待参数

当前 **不包含**：

- `PDN_UART` 单线 UART 寄存器配置
- `IHOLD / IRUN / TCOOLTHRS / SGTHRS` 等 Trinamic 寄存器调参
- `DIAG` 故障脚接入与 StallGuard 联动

也就是说，这一版把 `TMC2209` 当作一颗可直接复用现有 `STEP/DIR/EN` 框架的驱动器 profile，而不是完整 UART 版集成方案。

## 默认 profile

当前固件和 GUI 中，`TMC2209` profile 默认使用：

- `steps_per_rev = 1600`
- `wakeup_us = 0`
- `EN` 低有效
- `DIR` 高=Forward，低=Reverse

这个默认值对应常见 `standalone` 配置下的 `1/8` 逻辑细分。

> 注意：`TMC2209` 常见模块内部会做 `MicroPlyer` 插值到 `256`，但对 MCU 来说，`STEP` 口看到的仍然是当前 `MS1/MS2` 或寄存器配置决定的外部逻辑步细分。

## 运行时配置

串口示例：

```text
m1 cfg driver tmc2209
m1 cfg microstep 16
m1 cfg steps 3200
m1 cfg wakeup 0
```

说明：

- `cfg microstep 8|16|32|64`
  - 当前只修改软件侧的逻辑换算
  - 前提是你的模块硬件 `MS1/MS2` 或 UART 配置已经与之匹配
- `cfg steps <steps_rev>`
  - 直接修改逻辑换算参数
  - 当硬件细分不是默认值时，可用它修正 GUI 的 `rpm` 显示和指令换算
- `cfg wakeup <us>`
  - 给某些模块在 `EN` 释放后预留一个保守等待时间

## 建议接线

基础控制信号仍按现有双轴接口：

- `M1 STEP = PA8`
- `M1 DIR = PA0`
- `M1 EN = PA1`
- `M2 STEP = PB4`
- `M2 DIR = PB0`
- `M2 EN = PB1`

建议模块侧：

- `VIO / VDD` -> `3V3`
- `GND` -> `MCU GND`
- `STEP` -> MCU `STEP`
- `DIR` -> MCU `DIR`
- `ENN` -> MCU `EN`
- `VM` -> 电机电源
- `GND` -> 电机电源地

如果后续要启用 UART：

- 再单独把 `PDN_UART` 接到 MCU UART / 单线半双工接口
- 再补寄存器初始化和诊断逻辑

## 这次实现的边界

这次加入 `TMC2209`，主要目的是：

- 让现有 GUI 可以直接切换到 `TMC2209`
- 让 `rpm` / `accel` / `steps/rev` 换算和 profile 匹配
- 保持与 `GC6609` / `DM556` / `A4988` 一致的操作路径

如果后面要做真正的 `TMC2209 UART` 版：

1. 增加 `PDN_UART` 硬件接线说明
2. 补 `UART` 驱动层
3. 加 GUI 的 `IRUN / IHOLD / SpreadCycle / StealthChop` 配置
4. 接 `DIAG` 进 MCU 做故障/堵转联动
