# STM32C031C6 双轴云台方案选型更新（2026-03-10）

## 1. 背景与本轮结论

本轮选型不再把 `MKS GC6609 StepStick` 作为默认落地方案。

原因很直接：

- 当前测试电机为 `42BYGH34-401A`。
- 实测绕组分组为：
  - 黑 + 红：约 `3.3 ohm`
  - 绿 + 蓝：约 `3.3 ohm`
  - 其余任意组合：接近开路
- `EN / DIR / STEP` 已通过 GUI 引脚测试验证，MCU 侧输出链路正常。
- 同一颗电机换到其它驱动器后可以正常连续转动，`12V` 侧输入电流约 `1.2A`。
- 在当前项目中，`MKS GC6609` 模块则表现为堵转、异常电流和多次损坏。

这说明当前问题的主矛盾已经不是：

- `STM32C031C6` 的 STEP/DIR 代码逻辑；
- 或 GUI 串口命令下发链路；

而是：

- `MKS GC6609` 小模块对这颗电机和当前负载组合的工程余量不足。

因此新的选型策略应拆成两条线：

1. `快速可演示`：优先换成已验证可带动该电机的更高余量 `STEP/DIR` 驱动器。
2. `后续可集成/可诊断`：再转向 `TMC2209 + UART 诊断 + 电流监测` 的体系。

## 2. 当前代码可复用性判断

现有代码库已经足够通用，不必因为换驱动器而整体推倒重来。

### 固件层

- 当前底层抽象是标准 `STEP / DIR / EN / ZERO`，不是写死 `GC6609` 专有寄存器。
- 电机状态机、速度斜坡、固件点动、引脚测试都在 [ptz_motor.h](/Users/michael/Documents/AI%20Codex/PTZ/Core/Inc/ptz_motor.h) 和 [ptz_motor.c](/Users/michael/Documents/AI%20Codex/PTZ/Core/Src/ptz_motor.c)。
- 默认引脚映射在 [main.h](/Users/michael/Documents/AI%20Codex/PTZ/Core/Inc/main.h)。
- 若新驱动器仍是 `STEP/DIR/EN` 接口，通常只需要：
  - 保留现有串口协议；
  - 保留现有 GUI；
  - 视驱动器输入极性，调整 `PTZ_MOTOR_EN_ACTIVE_LEVEL` 和方向宏；
  - 如驱动器是光耦 `5V` 输入，再补一级电平转换或晶体管驱动。

### GUI 层

- 现有 GUI 已按双轴自定义串口协议重构，支持：
  - 双电机独立控制
  - 连续 / 点动 / 连续点动
  - 速度、加速度调节
  - 状态帧、故障帧显示
  - `DIR / EN / STEP` 引脚测试
- 代码在 [ptz_gui.py](/Users/michael/Documents/AI%20Codex/PTZ/tools/ptz_gui.py)。

因此，本轮选型的核心是 `驱动器与保护链路`，不是 `MCU/GUI 重做`。

## 3. 选型原则

本轮按下面四条排序：

1. 先解决 `电机能稳定转`。
2. 尽量复用现有 `STM32C031C6 + VCP + GUI + 串口协议`。
3. 再补 `保护/诊断`，不要把“能转”和“全诊断”绑死。
4. 避免继续押注已经在实测中反复失效的 `GC6609` 小模块。

## 4. 方案对比

| 方案 | 硬件组成 | 代码复用 | 诊断/保护能力 | 工作量 | 风险 | 结论 |
|---|---|---:|---|---|---|---|
| A. 外置高余量 `STEP/DIR` 驱动器 | `STM32C031C6 + 外置步进驱动器 + 12V/24V` | 高 | 中 | 低 | 体积较大；若为光耦输入需做电平适配 | `首选`，最快形成稳定 demo |
| B. `TMC2209 + UART` 诊断方案 | `STM32C031C6 + TMC2209 + PDN_UART + 可选 INA219` | 中高 | 高 | 中高 | 单线 UART、散热和模块连续电流余量要认真设计 | `中期主线`，适合下一版集成板 |
| C. `RS485` 智能步进控制器 | `PC/MCU + RS485 控制器 + 电机` | 中低 | 中 | 中 | 会改变现有“USB 直连 MCU”的体系 | 可作基准平台，不建议作为当前主线 |
| D. 继续使用 `MKS GC6609` 小模块 | `STM32C031C6 + MKS GC6609` | 高 | 低 | 低 | 已在实测中多次失败 | `不建议` |

## 5. 推荐落地路线

### 方案 A：首选演示方案

**推荐组合**

- 主控：`STM32C031C6T6 / NUCLEO-C031C6`
- 驱动：`外置 STEP/DIR 步进驱动器`，连续电流能力建议至少高于当前电机实测工作点
- 电机：`42BYGH34-401A`
- 上位机：继续使用当前 `USB VCP + 自定义 GUI`

**为什么这是首选**

- 你已经用“其它驱动器”验证过这颗电机可以正常工作。
- 当前固件就是标准 `STEP/DIR/EN` 控制模型，迁移成本最低。
- 这条路线的目标是先把 demo 做稳，而不是继续证明 `GC6609` 是否还能救。

**建议的硬件边界**

- 选 `STEP/DIR/ENA` 输入型驱动器；
- 连续相电流能力至少覆盖这颗 `42BYGH34-401A` 的稳定工作点；
- 若驱动器输入侧为 `5V` 光耦，MCU 侧增加：
  - NPN/MOS 管下拉驱动，或
  - 专用电平转换/光耦驱动。

**对现有代码的改动**

- 基本不改协议和 GUI；
- 只需要根据新驱动器实际极性，检查：
  - [ptz_motor.h](/Users/michael/Documents/AI%20Codex/PTZ/Core/Inc/ptz_motor.h) 里的 `PTZ_MOTOR_EN_ACTIVE_LEVEL`
  - `PTZ_MOTOR_DIR_FWD_LEVEL`
  - `PTZ_MOTOR_DIR_REV_LEVEL`
- 如引脚要重映射，再改 [main.h](/Users/michael/Documents/AI%20Codex/PTZ/Core/Inc/main.h)。

**保护建议**

- 先加最小保护：
  - 电源保险
  - 驱动器散热
  - 急停 / 总停
- 第二步再加：
  - `INA219` 电流监测
  - 驱动器 `FAULT/ALM` 到 MCU `EXTI`
  - 过流后 `EN` 关断和 GUI 告警

### 方案 B：中期集成方案

**推荐组合**

- 主控：`STM32C031C6`
- 驱动：`TMC2209`
- 运动控制：保留当前 `TIM OC + STEP/DIR` 架构
- 诊断链路：`PDN_UART` 读回驱动诊断 + 可选 `INA219` + `IWDG`

**为什么它适合中期，而不是立即切换**

- 公开资料和本地调研都更偏向 `TMC2209` 这一类“可诊断”的驱动；
- 但它不是“换模块就完事”，还需要处理：
  - 单线 UART + CRC
  - 回声/重试/超时
  - 驱动参数初始化
  - 故障轮询与状态机
  - 模块连续电流和热设计

**当前推荐的软件组合**

- `TMC2209` 寄存器访问层：`veysiadn/TMC2209_STM32`
- 脉冲层：`asansil/STM32-Pulse-Generator` 的 `TIM OC + CCR 更新` 范式
- MCU 底座：`STM32CubeC0`

**适用前提**

- 你接受这是一条 `下一版板卡/下一轮固件` 路线；
- 你愿意为诊断能力增加硬件和软件复杂度；
- 你不会再把“小 StepStick 模块 + 1.7A 电机 + 无充分散热”当作理所当然的稳定组合。

**当前判断**

- 这条路适合“后续集成板”和“产品化前的可诊断架构”；
- 不适合拿来替代当前必须尽快稳定的演示需求。

### 方案 C：RS485 控制器方案

**适用场景**

- 用作对照平台；
- 用来快速验证机械、电机和负载本体是否正常；
- 或者在完全放弃本地 MCU 运动控制时使用。

**为什么不作为当前主线**

- 它会改变现有 `PC -> USB -> STM32 -> Driver` 的架构；
- 你的当前 GUI、固件协议和调试链路价值会被削弱；
- 更像“成熟控制器替代方案”，而不是本项目的自然演进。

### 方案 D：继续使用 MKS GC6609

不建议继续投入。

理由：

- 同一电机和机械条件下，已有更高余量驱动器可正常转动；
- 当前项目中，`GC6609` 模块已经出现重复性失效；
- 继续投入时间主要是在为一条已证明余量不足的路线兜底。

## 6. GUI 方案取舍

本轮不建议切换到 `CNCjs / UGS / Candle2` 这类通用 G-code GUI。

原因：

- 当前项目协议是轻量自定义串口协议，不是 `GRBL/G-code`。
- 现有 GUI 已经覆盖当前需求，且已适配本机老 `Tk` 环境的显示问题。
- 对当前 demo 来说，继续复用 [ptz_gui.py](/Users/michael/Documents/AI%20Codex/PTZ/tools/ptz_gui.py) 的收益明显高于引入大型通用上位机。

如果后续要做：

- 轨迹规划
- 多轴联动
- 脚本任务
- 远程 Web 面板

再考虑在现有协议之上重做 Web GUI，而不是现在切到 G-code 生态。

## 7. 最终建议

### 当前推荐

**主推荐方案**

- `STM32C031C6 + 外置高余量 STEP/DIR 驱动器 + 当前固件 + 当前 GUI`

**后续迭代方案**

- `STM32C031C6 + TMC2209(UART 诊断) + INA219 + IWDG + 当前协议/GUI`

**不再建议**

- `STM32C031C6 + MKS GC6609 StepStick + 42BYGH34-401A`

## 8. 建议的执行顺序

1. 先用已验证能带动该电机的外置驱动器，把双轴 demo 跑通。
2. 在当前代码上补：
   - `FAULT/ALM` 输入
   - 可选 `INA219`
   - 故障停机与 GUI 提示
3. 等机械、电机和运动参数稳定后，再决定是否切换到 `TMC2209` 集成方案。

## 9. 参考资料

### 本地调研与资料

- [基于 STM32C031C6 + GC6609（步进驱动）双轴云台开环控制的 GitHub 公开项目深度调研报告.pdf](/Users/michael/Documents/AI%20Codex/PTZ/%E5%9F%BA%E4%BA%8E%20STM32C031C6%20%2B%20GC6609%EF%BC%88%E6%AD%A5%E8%BF%9B%E9%A9%B1%E5%8A%A8%EF%BC%89%E5%8F%8C%E8%BD%B4%E4%BA%91%E5%8F%B0%E5%BC%80%E7%8E%AF%E6%8E%A7%E5%88%B6%E7%9A%84%20GitHub%20%E5%85%AC%E5%BC%80%E9%A1%B9%E7%9B%AE%E6%B7%B1%E5%BA%A6%E8%B0%83%E7%A0%94%E6%8A%A5%E5%91%8A.pdf)
- [GitHub 公开项目调研报告：STM32C031C6_STM32C0 上的 TMC2209 双轴步进控制与防护.pdf](/Users/michael/Documents/AI%20Codex/PTZ/GitHub%20%E5%85%AC%E5%BC%80%E9%A1%B9%E7%9B%AE%E8%B0%83%E7%A0%94%E6%8A%A5%E5%91%8A%EF%BC%9ASTM32C031C6_STM32C0%20%E4%B8%8A%E7%9A%84%20TMC2209%20%E5%8F%8C%E8%BD%B4%E6%AD%A5%E8%BF%9B%E6%8E%A7%E5%88%B6%E4%B8%8E%E9%98%B2%E6%8A%A4.pdf)
- [双轴步进电机驱动器 GUI 项目调研与分析.pdf](/Users/michael/Documents/AI%20Codex/PTZ/%E5%8F%8C%E8%BD%B4%E6%AD%A5%E8%BF%9B%E7%94%B5%E6%9C%BA%E9%A9%B1%E5%8A%A8%E5%99%A8%20GUI%20%E9%A1%B9%E7%9B%AE%E8%B0%83%E7%A0%94%E4%B8%8E%E5%88%86%E6%9E%90.pdf)

### 本轮核对的公开仓库与官方资料

- [veysiadn/TMC2209_STM32](https://github.com/veysiadn/TMC2209_STM32)
- [asansil/STM32-Pulse-Generator](https://github.com/asansil/STM32-Pulse-Generator)
- [STMicroelectronics/STM32CubeC0](https://github.com/STMicroelectronics/STM32CubeC0)
- [ADI/Trinamic TMC2209 Datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.09.pdf)
