# STM32C031C6 对接 TMC2209 模块调整说明

![STM32C031C6-TMC2209-Wiring](/Users/michael/Documents/AI%20Codex/PTZ/docs/stm32c031c6_tmc2209_wiring.png)

## 当前支持范围

当前仓库对 `TMC2209` 的支持范围是：

- `STEP / DIR / ENN` 独立模式
- `PDN_UART` 单线 UART 寄存器读写
- 每轴运行时切换 `driver=tmc2209`
- `steps_per_rev` 运行时换算
- `microstep` 逻辑配置：`8 / 16 / 32 / 64`
- `wakeup_us` 起转前等待参数
- `IHOLD / IRUN / IHOLDDELAY / VSENSE / TPWMTHRS` 读写
- `StealthChop / SpreadCycle` 运行时切换
- `DRV_STATUS / IOIN / GCONF / CHOPCONF / PWMCONF` 状态读取

当前 **仍不包含**：

- `DIAG` 故障脚接入与 StallGuard 联动
- `CoolStep`、`SGTHRS`、`TCOOLTHRS` 等更完整的闭环保护/诊断策略

也就是说，这一版已经从单纯的 `STEP/DIR/EN` profile，推进到可直接调 `TMC2209` 关键寄存器的 UART 集成方案。

## 默认 profile

当前固件和 GUI 中，`TMC2209` profile 默认使用：

- `steps_per_rev = 1600`
- `wakeup_us = 0`
- `default accel = 600 Hz/s`
- `EN` 低有效
- `DIR` 高=Forward，低=Reverse

这个默认值对应常见 `standalone / UART` 混合调试配置下的 `1/8` 逻辑细分。

另外，为改善同步带或外部负载起步时的跳齿，当前固件对 `TMC2209` 加了一层保守的起步加速度限制：

- 当目标速度和当前速度都处于 `0..800 Hz` 区间时
- 实际生效的加速度上限会被压到 `300 Hz/s`

这是一种纯 `STEP/DIR` 层的保守处理，即使暂时不走 UART 也生效。

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

当前接线图已收敛为单轴示例，只使用 `M1`：

- `M1 STEP = PA8`
- `M1 DIR = PA0`
- `M1 EN = PA1`

建议模块侧：

- `VIO / VDD` -> `3V3`
- `GND` -> `MCU GND`
- `STEP` -> MCU `STEP`
- `DIR` -> MCU `DIR`
- `ENN` -> MCU `EN`
- `VM` -> 电机电源
- `GND` -> 电机电源地

建议的单轴 UART 接法：

- `PA9 / USART1_TX` -> 串 `1k` 电阻 -> 模块 `PDN_UART`
- `PA10 / USART1_RX` -> 直接接到同一根 `PDN_UART` 线上
- 单轴地址绑法：`MS1 / AD0 = GND`，`MS2 / AD1 = GND`，地址 `0`

注意：

- 当前实现已经使用这条 `PDN_UART` 线做单线 UART 访问
- `MS1 / MS2` 在 UART 模式下优先承担地址绑定位，不适合继续固定成细分选择脚
- 细分建议通过 GUI 或串口命令写 `CHOPCONF.mres`，不要再依赖模块硬件绑脚
- 当前单轴图使用地址 `0`：`MS1/AD0=GND`、`MS2/AD1=GND`

## 当前可用 UART 命令

串口示例：

```text
m1 cfg driver tmc2209
m1 tmc cfg addr 0
m1 tmc cfg rsense 110
m1 tmc init
m1 tmc status
m1 tmc write irun 20
m1 tmc write ihold 8
m1 tmc write iholddelay 8
m1 tmc write vsense 1
m1 tmc write microstep 16
m1 tmc write mode spreadcycle
```

说明：

- `tmc cfg addr <0..3>`：设置单线 UART 地址
- `tmc cfg rsense <mohm>`：设置电流估算用的采样电阻值
- `tmc init`：把当前缓存参数写入 `GCONF / IHOLD_IRUN / CHOPCONF / TPWMTHRS`
- `tmc status`：读取关键寄存器并输出汇总
- `tmc write irun/ihold/iholddelay`：改运行/保持电流档位
- `tmc write vsense 0|1`：切 `CHOPCONF.vsense`
- `tmc write microstep 8|16|32|64`：改 `CHOPCONF.mres`
- `tmc write mode stealthchop|spreadcycle`：切 `GCONF.en_spreadCycle`

## 这次实现的边界

这次加入 `TMC2209`，主要目的是：

- 让现有 GUI 可以直接切换到 `TMC2209`
- 让 `rpm` / `accel` / `steps/rev` 换算和 profile 匹配
- 保持与 `GC6609` / `DM556` / `A4988` 一致的操作路径

如果后面要继续往前走，优先级应是：

1. 接 `DIAG` 进 MCU，补 `DRV_STATUS` 异常联动
2. 增加 `CoolStep / StallGuard` 相关寄存器配置
3. 把 `UART` 通道从单轴验证扩到双轴共享总线
