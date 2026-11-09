# 外设清单与官方覆盖度（piano vs UniXNU 官方组件）

每个子系统都从本机实测，并对照 `UniXNU/UniXNU` 的 28 个官方组件与 sheng、dada 的配置，
标出**哪些能直接复用官方、哪些必须为 SM8750 自写**。

## 结论速览

| 功能 | 本机实测 | 官方是否有对应组件 | 结论 |
| --- | --- | --- | --- |
| CPU / GIC / 定时器 | Oryon 8 核，GIC `0x16000000` | `ArmCpu` | ✅ 可直接用（靠 dts） |
| 设备树平台 | `qcom,sun` | `ArmDTPlatform` | ✅ 可直接用 |
| 引导 / DarwinBoot | — | `DarwinBoot` | ✅ 可直接用 |
| Prelink | — | `XnuPrelink` | ✅ 可直接用 |
| RAM 盘 | — | `RamBlock` | ✅ 可直接用 |
| 虚拟块设备 | — | `VirtioMmioBlock` | ✅ 可直接用 |
| 加密 | — | `SoftwareAES` | ✅ 可直接用 |
| 钥匙串状态 | — | `AppleKeyStoreState` | ✅ 可直接用 |
| 根校验 | — | `VerifiedRoot` | ✅ 可直接用 |
| UFS | `qcom,ufshc` @ `0x1d84000`，`qcom,ufs-phy-qmp-v4-sun` | `ShengUfs`（sheng 版） | ⚠️ 可试，时钟表需换 SM8750 |
| 显示 | MDSS `0xae00000`，DSI `0xae94000`，P81 LCD 3200×2136 | `GopFramebuffer`（UEFI GOP） | ⚠️ 仅能出 GOP 帧；DSI 面板驱动需自写 |
| **WiFi** | **Qualcomm CNSS**（`cnss2` / `icnss2` / `cnss_utils`），EHT（WiFi 7） | `Ath12kWifi`（Atheros） | ❌ **完全不是同一硬件，官方组件用不了** |
| **蓝牙** | Qualcomm（`btfmcodec` / `btpower` / `bt_fm_swr`） | `QcaBluetooth` | ⚠️ 同为 QCA 系，可作起点 |
| **GNSS / GPS** | **不存在**（device-tree 与 403 个模块中均无 gnss/gps） | 无 | ✅ 无需支持；定位只能走 WiFi/网络 |
| **NFC** | NXP（`nqnfcinfo` 服务、`persist.nfc.secure_nfc=true`、`fm_ntag_i2c`） | 无 | ❌ 需自写 |
| **摄像头** | Qualcomm CCI（`cci0/1/2` @ `ac7b000/ac7c000/ac7d000`），传感器在 I2C-6 `0x10`，EEPROM `0x51` | 无 | ❌ 需自写 |
| **音频** | ADSP + `aw882xx` / `cs35l43` / `fs19xx` 功放，I2C-0 `0x34..0x37` 为 `fs16xx`×4 | 无 | ❌ 需自写 |
| **触觉（马达）** | Cirrus **CS40L26**（`cs40l26-core` / `cs40l26-i2c`） | 无 | ❌ 需自写 |
| USB | `dwc3-msm`，`ssusb@a600000`，Type-C 开关 `fsa4480` (I2C-2 `0x42`) | `QcomDwc3` | ⚠️ 官方有 DWC3 组件，可试 |
| 电池 / 充电 | `bq27z561` 电量计（I2C-3/8 `0x55`）、`sc8541` 充电（I2C-3 `0x6a`）、`hl7603` | 无 | ❌ 需自写 |
| 无线充电 | `sc96231-wireless-ch`（I2C-9 `0x38`） | 无 | ❌ 需自写 |
| 背光 | `ktz8866`（I2C-1/5 `0x11`）、`panel0-backlight` max 4095 | 无 | ❌ 需自写 |
| 闪光灯 / 手电 | `leds-qcom-flash`、`led:flash_0..3`、`led:torch_0..3` | 无 | ❌ 需自写 |
| 红外 | `ir-spi`（SPI1） | 无 | ❌ 需自写 |
| 霍尔（磁吸键盘/保护套） | `xiaomi_hall` | 无 | ❌ 需自写 |
| 按键 | `gpio-keys`、`pmic_pwrkey`、`pmic_resin` | 无 | ⚠️ 靠 dts 描述 |
| 调制解调器 | `modem0-qmi` / `modem2-qmi` / `remoteproc` 存在，但平板无 SIM 槽 | 无 | ✅ 可不做 |
| 传感器 DSP | `remoteproc-cdsp@32300000`、`remoteproc-adsp@03000000` | 无 | ❌ 需自写 |

## 与参考机型的差异（必须单独处理）

| 项 | piano（SM8750 / sun） | sheng（SM8550） | dada（SM8750 / sun） |
| --- | --- | --- | --- |
| GIC | `0x16000000` | `0x17100000` | `0x16000000` 同 |
| CPU | Oryon 8 核，MPIDR `0..0x500`+`0x10000/0x10100` | A510/A715/A710/X3 | 同 piano |
| GPU | Adreno 830 `gen8-0-1` | Adreno 740 | 同 piano |
| 显示 | MDSS `0xae00000`，P81 LCD **3200×2136** | 自有面板 | 手机 AMOLED 1200×2670 |
| 陀螺/加速度 | 走 CDSP | — | — |
| 形态 | 平板（无 GNSS、无 SIM） | 平板 | 手机（有 GNSS/调制解调器） |

> 注意：dada 是手机，它的 `WIFI_ATH11K=0`、GNSS、调制解调器配置**都不能照搬到 piano**；
> sheng 是平板但 SoC 不同，GIC/UFS 时钟/显示全不一样。

## 本机 I2C / SPI 总线实况

| 总线 | 地址 | 器件 |
| --- | --- | --- |
| I2C-0 | `0x34`..`0x37` | `fs16xx` 音频功放 ×4 |
| I2C-1 / 5 | `0x11` | `ktz8866`（显示电源/背光） |
| I2C-2 | `0x42` | `fsa4480`（USB Type-C 开关） |
| I2C-3 | `0x55` / `0x6a` | `bq27z561_master` / `sc8541_master` |
| I2C-4 | `0x4c` | `803`（非主触控路径） |
| I2C-6 | `0x10` / `0x51` | `cam-i2c-sensor` / `cam-i2c-eeprom` |
| I2C-8 / 3 | `0x55` | `bq27z561_slave` |
| I2C-9 | `0x38` | `sc96231-wireless-ch` |
| I2C-11 | `0x68` / `0x69` | `i2c-pmic` |
| **SPI-0** | — | **`NVT-ts-spi`（主触控 Novatek NT36532）** |
| SPI-1 | — | `ir-spi`（红外） |

## 对构建目标的建议顺序

1. **先不碰无线/摄像头/音频**。它们不影响 XNU 起内核 + 出画面。
2. 顺序：CPU/GIC（官方组件 + dts）→ UFS（读盘）→ 显示（GOP 先出帧）→ 触摸 → 再谈 WiFi/NFC/音频。
3. WiFi 是**唯一确定要写新驱动**的大件（CNSS 与官方 Ath12kWifi 完全不同），不要指望官方组件。
