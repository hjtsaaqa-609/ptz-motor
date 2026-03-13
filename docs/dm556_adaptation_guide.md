# STM32C031C6 对接 DM556 外置驱动器调整说明

## 1. 结论先行

这类 `DM556` 外置驱动器可以直接复用当前项目的运动控制框架，因为它本质上仍是：

- `PUL` = `STEP`
- `DIR` = `DIR`
- `ENA` = `ENABLE`

所以：

- `GUI` 不需要改协议；
- `固件` 不需要改步进状态机；
- 主要调整点在 `接线方式`、`电源电压`、`输入接口电平` 和 `ENA` 是否接入。

## 接线图

![STM32C031C6-ULN2803A-DM556-Wiring](/Users/michael/Documents/AI%20Codex/PTZ/docs/stm32c031c6_uln2803a_dm556_wiring.png)

可直接打开的图片文件：

- [PNG 接线图](/Users/michael/Documents/AI%20Codex/PTZ/docs/stm32c031c6_uln2803a_dm556_wiring.png)
- [JPG 接线图](/Users/michael/Documents/AI%20Codex/PTZ/docs/stm32c031c6_uln2803a_dm556_wiring.jpg)

## 2. 必须先确认的硬件边界

按你给的驱动器铭牌和 Leadshine `DM556/DM556E` 官方资料，这类驱动器有几个关键约束：

1. 主电源不是 `12V`
   - 你图上的外壳已经写了 `VDC:+20V~+50V`
   - 官方资料也写的是 `18~50VDC` 或 `20~50VDC`，推荐 `24~48VDC`
   - 所以后续测试电源要改成 `24V` 起步，不要继续用 `12V`

2. 控制输入是光耦隔离输入
   - `PUL+ / PUL-`
   - `DIR+ / DIR-`
   - `ENA+ / ENA-`
   - 官方资料给出的逻辑信号电流大约 `7~16mA`

3. `3.3V GPIO` 不建议直接硬连驱动输入
   - NUCLEO 的 `PA8/PA0/PA1` 只是普通 `3.3V` GPIO
   - `DM556` 这类输入通常更适合 `5V` 逻辑或开集电极灌电流方式
   - 最稳妥做法是加一个中间驱动级

## 3. 推荐接线方式

### 方案 A：首轮 bring-up 推荐接法

这是我推荐你先做的接法，目标是：

- 最快跑通
- 最少代码改动
- 避免先在 `ENA` 极性上浪费时间

#### 控制信号

使用 `ULN2003 / ULN2803 / 3 路 NPN 开集电极` 做中间驱动。

其中你提到的这类 `ULN2803A` 成品模块是可以用的，而且比 `PC817` 模块更适合当前场景。

原因：

- `ULN2803A` 本质上是 8 路开集电极达林顿阵列，正适合去灌电流驱动 `DM556` 的 `PUL- / DIR- / ENA-`
- `DM556` 自己已经是光耦输入，不需要再串一层低速 `PC817`
- `ULN2803A` 一块板有 8 路，足够同时带两路电机：
  - `M1_STEP / M1_DIR / M1_EN`
  - `M2_STEP / M2_DIR / M2_EN`

前提：

- 你买的是“纯 ULN2803A 阵列输出模块”，不是带继电器/额外光耦的复合板
- 模块输入侧能接受 `3.3V` 高电平
- 模块输出侧是标准开集电极 `OUTx`

连接方式：

| STM32C031 | 中间驱动 | DM556 |
|---|---|---|
| `PA8` (`M1_STEP`) | 输入1 | 输出1 -> `PUL-` |
| `PA0` (`M1_DIR`) | 输入2 | 输出2 -> `DIR-` |
| `PA1` (`M1_EN`) | 先不接 | `ENA-` 先留空 |
| `5V` | - | `PUL+`、`DIR+` 共接 `+5V` |
| - | - | `ENA+` 先留空 |
| `GND` | 中间驱动 GND | `5V` 逻辑地共地 |

说明：

- `PUL+` 和 `DIR+` 共接 `+5V`
- `PUL-` 和 `DIR-` 由 `ULN2003` 这类灌电流输出下拉
- `ENA` 第一轮先不接，驱动保持默认使能
- 如果你的 `ULN2803A` 模块带 `VCC/GND` 端子，那通常是给板上指示灯或输入参考使用，建议接 `5V/GND`
- `ULN2803A` 的 `COM` 端只用于感性负载续流钳位，这里不要接到 `DM556` 的 `24V` 电源上

这样做的好处：

- `STEP/DIR` 足够先完成正反转验证
- 不需要先确认 `ENA` 的具体有效极性
- 当前固件几乎不用动

### 方案 B：完整接法

如果后面要让 `ENA` 也受 GUI 和固件控制，再接：

| STM32C031 | 中间驱动 | DM556 |
|---|---|---|
| `PA1` (`M1_EN`) | 输入3 | 输出3 -> `ENA-` |
| `+5V` | - | `ENA+` |

但是这一步接入前，需要先按第 6 节调整代码里的 `EN` 有效电平，或者先用 GUI 的引脚测试确认极性。

### 方案 C：双轴复用一块 ULN2803A 模块

若你是一块 `ULN2803A` 模块同时带两路 `DM556`，建议通道分配如下：

| ULN2803A 通道 | 连接 |
|---|---|
| `IN1/OUT1` | `M1_STEP -> DM556#1 PUL-` |
| `IN2/OUT2` | `M1_DIR -> DM556#1 DIR-` |
| `IN3/OUT3` | `M1_EN -> DM556#1 ENA-` |
| `IN4/OUT4` | `M2_STEP -> DM556#2 PUL-` |
| `IN5/OUT5` | `M2_DIR -> DM556#2 DIR-` |
| `IN6/OUT6` | `M2_EN -> DM556#2 ENA-` |

共阳极统一接法：

- `DM556#1 PUL+ / DIR+ / ENA+ -> +5V`
- `DM556#2 PUL+ / DIR+ / ENA+ -> +5V`

这样一块 8 路模块就足够双轴使用，还剩 2 路余量。

## 4. 电机和电源接线

### 电机相线

你前面已经实测确认当前这颗 `42BYGH34-401A` 的绕组分组为：

- 黑 + 红：一组
- 绿 + 蓝：一组

所以接到 `DM556` 时建议先按下面接：

| DM556 端子 | 电机线 |
|---|---|
| `A+` | 黑 |
| `A-` | 红 |
| `B+` | 绿 |
| `B-` | 蓝 |

如果方向相反：

- 优先改 `DIR` 逻辑
- 或只交换同一相内两根线，例如 `黑/红` 对调

不要跨相乱换。

### 主电源

| DM556 端子 | 连接 |
|---|---|
| `+V` | `24VDC` 电源正极 |
| `GND` | `24VDC` 电源负极 |

注意：

- 不要用 `12V`
- 多个驱动共电源时，电源线应分别回到电源端，不要串接级联

## 5. 首轮拨码建议

### 细分

为了让当前固件和 GUI 的 `rpm` 换算不改，建议先把细分设成 `1600 pulse/rev`。

按你图上的拨码表，对应：

- `SW5 = OFF`
- `SW6 = OFF`
- `SW7 = ON`
- `SW8 = ON`

这样就和当前代码里的：

- [ptz_motor.h](/Users/michael/Documents/AI%20Codex/PTZ/Core/Inc/ptz_motor.h) `PTZ_MOTOR_STEPS_PER_REV = 1600`
- [ptz_gui.py](/Users/michael/Documents/AI%20Codex/PTZ/tools/ptz_gui.py) `STEPS_PER_REV = 1600`

保持一致。

### 电流

这颗电机铭牌是 `1.7A`，第一轮不要把电流拨得太激进。

建议先从较保守值开始：

- `SW1/SW2/SW3` 先设到接近 `2.1A peak / 1.5A RMS`

这样先验证转动、温升和堵转情况，再决定是否往上调。

### 静止电流

建议：

- `SW4 = OFF`

理由：

- 这通常代表静止电流降低
- 可以明显减小发热
- 更适合第一轮联调

## 6. 代码需要怎么改

### 6.1 最小改动版本

如果你按第 3 节的推荐接法：

- 只接 `PUL`
- 只接 `DIR`
- `ENA` 不接
- 细分设 `1600`

那么代码可以先不改。

原因：

- 当前固件输出的 `STEP` 脉冲和 `DIR` 逻辑已经满足这类驱动的时序要求
- 当前定时器 tick 是 `1MHz`
- 现有最大速度 `50kHz` 下，单个高/低电平宽度也在 `10us` 量级，明显大于 `DM556` 手册要求的 `2.5us`
- 代码里已经在切方向后插入了建立时间，再开始发脉冲

### 6.2 如果你接入 ENA

当前项目默认定义是：

- [ptz_motor.h](/Users/michael/Documents/AI%20Codex/PTZ/Core/Inc/ptz_motor.h): `PTZ_MOTOR_EN_ACTIVE_LEVEL GPIO_PIN_RESET`

这是针对前面 `GC6609` 低有效使能写的。

如果 `DM556` 采用“共阳极 + 开集电极灌电流”接法，则大概率要改为：

```c
#define PTZ_MOTOR_EN_ACTIVE_LEVEL GPIO_PIN_SET
```

理由：

- 在这种接法下，`MCU=1` -> 开集电极导通 -> `ENA-` 被拉低 -> 驱动输入被激活

但这里我不建议你现在就直接硬改并烧录，最稳妥的顺序是：

1. 第一轮先不接 `ENA`
2. 先验证 `PUL/DIR` 正常转动
3. 第二轮再把 `ENA` 接入
4. 用 GUI 的 `Pin Test` 做高低电平试验，再最终确定 `EN` 极性

### 6.3 如果以后改了细分

如果后面不是 `1600 pulse/rev`，则需要同步改两个地方：

1. 固件：
   - [ptz_motor.h](/Users/michael/Documents/AI%20Codex/PTZ/Core/Inc/ptz_motor.h) 的 `PTZ_MOTOR_STEPS_PER_REV`
2. GUI：
   - [ptz_gui.py](/Users/michael/Documents/AI%20Codex/PTZ/tools/ptz_gui.py) 的 `STEPS_PER_REV`

否则：

- GUI 显示的 `rpm`
- 固件换算出来的 `rpm`

都会和实际机械转速不一致。

## 7. 推荐的首轮测试步骤

1. 把驱动电源改成 `24V`
2. 细分拨到 `1600 pulse/rev`
3. 电流先拨保守值
4. 只接 `PUL` 和 `DIR`，`ENA` 先不接
5. 用 `ULN2003 / NPN` 做控制接口，不要直接拿 `3.3V GPIO` 硬推
6. GUI 里先用：
   - `Continuous`
   - `10 rpm`
   - `低加速度`
7. 如果能稳定转，再接入 `ENA`

## 8. 后续建议

这款 `DM556` 的好处是：

- 对当前电机余量更大
- 更适合先把 demo 稳定下来

它的缺点是：

- 体积更大
- 当前这张图的版本看起来没有可直接接入 MCU 的故障输出

所以它适合：

- 当前阶段的演示/联调

不适合直接替代后续想做的：

- 驱动诊断
- 电流监测闭环
- 轻量集成板方案

## 9. 参考资料

- [Leadshine DM556E User Manual](https://www.leadshine.com/upfiles/downloads/d19dd5aeb9ceb378d9a7882ab9551217_1651053026312.pdf)
- [Leadshine DM556 User Manual](https://www.leadshine.com/upfiles/downloads/2c28eb55103c7f769867f3338c14808f_1660188467317.pdf)
- [Leadshine EM1-556 产品页](https://www.leadshine.com/product-detail/EM1-556.html)
