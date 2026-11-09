# 硬件事实清单（Xiaomi Pad 8 Pro / piano / SM8750 "sun"）

全部数值**直接在本机读取**，来源见每行末列。未从任何其他机型（dada / sheng）复制。

## SoC

| 项 | 值 | 来源 |
| --- | --- | --- |
| 根 compatible | `qcom,sun-mtp` / `qcom,sun` / `qcom,sunp-mtp` / `qcom,sunp` | `/proc/device-tree/compatible` |
| CPU | 8× `arm,armv8`（Oryon）；MPIDR `0x000..0x500` + `0x10000`、`0x10100` | `/proc/device-tree/cpus/` |
| GIC distributor | `0x16000000` + `0x10000` | `soc/interrupt-controller@16000000` |
| GIC redistributor | `0x16080000` + `0x200000`，stride `0x40000` | 同上 |
| GIC ITS | `0x16040000` + `0x20000` | `msi-controller@0x16040000` |
| UFS PHY | `0x1d80000` + `0x2000`，`qcom,ufs-phy-qmp-v4-sun` | `soc/ufsphy_mem@1d80000` |
| UFS 控制器 | `0x1d84000` + `0x3000`（另有 `0x1d88000`/`0x1da5000`/`0x1da4000`） | `soc/ufshc@1d84000` |
| GPU | Adreno 830，`qcom,adreno-gpu-gen8-0-1`，基址 `0x3d00000` | `soc/qcom,kgsl-3d0@3d00000` |
| GPU SMMU | `0x3da0000` + `0x40000` | `soc/kgsl-smmu@3da0000` |
| APPS SMMU | `0x15000000` + `0x100000` | `soc/apps-smmu@15000000` |

## 显示

| 项 | 值 | 来源 |
| --- | --- | --- |
| MDSS / MDP | **`0xae00000`** | `soc/qcom,mdss_mdp@ae00000` |
| DSI controller 0 / 1 | `0xae94000` / `0xae96000` | `soc/qcom,mdss_dsi_ctrl{0,1}@ae9{4,6}000` |
| DSI PHY 0 / 1 | `0xae95500` / `0xae97500` | `soc/qcom,mdss_dsi_phy{0,1}@ae9{5,7}500` |
| 面板代号 | **P81**（`P81_PANEL_PA` / `P81_PANEL_PB`） | `msm_drm.ko` 字符串 |
| 面板类型 | **LCD**，支持 CABC / HBM / APL dimming / local-HBM | `msm_drm.ko`：`[LCD]`、`lcd panel cabc`、`apl_dimming`、`lhbm` |
| 分辨率 | **3200 × 2136** | `/sys/class/drm/card0-DSI-1/modes` |
| 刷新率 | 144 / 120 / 90 / 60 / 50 Hz | 同上 |
| 动态刷新描述 | `120,90,60,50:100,60,5` | `ro.vendor.display.dynamic_refresh_rate` |
| 默认帧率 | 60 | `ro.vendor.display.default_fps` |
| 背光设备 | `panel0-backlight`，**max 4095（12-bit）** | `/sys/class/backlight/panel0-backlight/max_brightness` |
| TE 引脚 | **GPIO 86**（`<39 86 0>`，tlmm phandle 39） | `qcom,dsi-display-primary/qcom,platform-te-gpio` |
| 显示电源轨 | `tvdd` / `vci` / `vdd` / `vddil12b` / `vddio` / `vsn` / `vsp` | `qcom,dsi-display-primary/*-supply` |
| 面板电源节点 | `dsi_panel_pwr_supply`、`_P81`、`_avdd`、`_sim` | `soc/` |
| GPIO 稳压 | `display_gpio_regulator@1`、`_vsn`、`_vsp` | `soc/` |
| Demura ID | `0x0122e700` / `0x00000471` | `qcom,demura-panel-id` |
| Framebuffer / dump | `0xFC800000` | `soc/disp_rdump_region@FC800000` |

### 面板时序：待确认

h/v porch、DSI lane 数、DSC 参数属于面板驱动的**内部时序表**，不在设备树、不在 `/vendor/etc/display`
（那里的 `nt37801_amoled_*` 是 AMOLED 机型配置，`1440x3200` 与本机 3200×2136 不符）。
获取途径：内核源码 `dsi_panel_*` 表，或开机早期 dmesg。

## 触摸

| 项 | 值 | 来源 |
| --- | --- | --- |
| 控制器 | **Novatek NT36672A / NT36532** | `/proc/kallsyms`：`NT36672A_memory_map [nt36532_touch]` |
| 总线 | **SPI0** | `/sys/bus/spi/devices/spi0.0/modalias` = `spi:NVT-ts-spi` |
| input 设备 | `NVTCapacitiveTouchScreen`（input11） | `/sys/class/input/input11/name` |
| 触控笔 | `NVTCapacitivePenM80p`（input12）、`NVTCapacitivePenP81c`（input13） | 同上 |
| DT 封装节点 | `xiaomi-touch`（仅 compatible/status） | `soc/xiaomi_touch` |
| 触摸供电 | `touch_avdd_vreg` | `soc/touch_avdd_vreg` |
| I2C 旁路 | `4-004c` 名 "803"，**非主触控路径** | `/sys/bus/i2c/devices/4-004c` |

## 指纹（侧边，非屏下）

| 项 | 值 | 来源 |
| --- | --- | --- |
| 厂商 | **Goodix** | `persist.vendor.sys.fp.vendor=goodix` |
| 总线 | **SPI** | dmesg：`xiaomi-fp fp_ioctl: FP_IOC_ENABLE_SPI_CLK` |
| 中断 | GPIO（`xiaomi,gpio_irq`） | `soc/xiaomi_fingerprint/xiaomi,gpio_irq` |
| 供电 | `fp_3v3_vreg-supply`（3.3V） | 同上 |
| pinctrl | `reset_high` / `reset_low` / `irq_default` | `soc/xiaomi_fingerprint/pinctrl-names` |
| 设备节点 | `/dev/xiaomi-fp`(481,0)、`/dev/mifp_id`(481,1) | `ls -l /dev` |
| 形态 | **侧边电容式**（电源键集成） | 用户实机确认 |
| 无关节点 | `fingerprint-screen`（仅 name/panel/phandle）、`mca_*_fod_data` | 屏下机型模板残留，与本机无关 |

## 其他外设

| 器件 | 地址 | 名称 |
| --- | --- | --- |
| SPI1 | `spi1.0` | `spi:ir-spi` |
| 音频功放 | I2C `0-0034`..`0-0037` | `fs16xx` |
| PMIC | I2C `11-0068`、`11-0069` | `i2c-pmic` |
| 电量计 | I2C `3-0055`、`8-0055` | `bq27z561` master/slave |
| 充电 | I2C `3-006a` | `sc8541_master` |
| 无线充 | I2C `9-0038` | `sc96231-wireless-ch` |
| USB Type-C | I2C `2-0042` | `fsa4480-i2c` |
