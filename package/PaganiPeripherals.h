// SPDX-License-Identifier: BSD-2-Clause-Patent
//
// Piano (Xiaomi Pad 8 Pro, SM8750) board constants.
//
// Every value below was read from THIS device's live device tree
// (/sys/firmware/fdt, 1111735 B, md5 d491cf2eec5f644043601dfc0014be09,
//  model "Qualcomm Technologies, Inc. Piano based on SM8750").
// The OnePlus 13T (PKX110) values they replace are marked "(was: ...)".
//
// NOT confirmed from the piano device tree (still the 13T template):
//   TOUCH_SE / TOUCH_WRAPPER / TOUCH_SMMU* / TOUCH_VCC* / TOUCH_RSC /
//   TOUCH_HZ / TOUCH_CS_DELAY / TOUCH_WORD_DELAY / touch timing /
//   BRIGHTNESS_DEFAULT / PON_POWER / PON_VOLUME_UP / TOUCH_VDD_VRM.
//   These belong to the 13T's touch controller; piano uses a different part
//   (nanosic,803) and needs its own support code.
#pragma once

// ---- SoC level: identical on both boards ----
#define PAGANI_GCC_BASE 0x100000ULL
#define PAGANI_CMD_DB 0x81c60000ULL
#define PAGANI_CMD_DB_SIZE 0x20000
#define PAGANI_SPMI_CORE 0xc400000ULL
#define PAGANI_SPMI_CNFG 0xc42d000ULL
#define PAGANI_SPMI_OBS 0xc440000ULL
#define PAGANI_SPMI_EE 0

// ---- TLMM: piano pinctrl@f000000 (was: 0xf100000) ----
#define PAGANI_TLMM_GPIO(n) (0xf000000ULL+0x1000ULL*(n))

// ---- touch controller: piano = nanosic,803 on I2C 0x4c (GENI SE @0xa98000) ----
#define PAGANI_TOUCH_RESET 188          // was 161   (reset_pin = 39 188 0)
#define PAGANI_TOUCH_ATTN 97            // was 162   (irq_pin  = 39 97 8193)
#define PAGANI_TOUCH_PINS {48,49,50,51,PAGANI_TOUCH_RESET,PAGANI_TOUCH_ATTN}
#define PAGANI_TOUCH_DRIVES {2,1,2,1,3,3}
#define PAGANI_TOUCH_RESET_MS 10
#define PAGANI_TOUCH_STARTUP_MS 100
#define PAGANI_TOUCH_POWER_MS 200
#define PAGANI_TOUCH_EDGE_PIXELS 48
#define PAGANI_TOUCH_VDD "ldob14"       // was "ldob4"   (vdd-supply phandle 1017)
#define PAGANI_TOUCH_VDD_MV 3300        // was 1800      (3300000 uV, pm_humu_l14)
#define PAGANI_TOUCH_VCC "ldob16"
#define PAGANI_TOUCH_VCC_MV 3100
#define PAGANI_TOUCH_VDD_VRM 0x40800
#define PAGANI_TOUCH_VCC_VRM 0x41900

// ---- secure / smmu / rsc ----
#define PAGANI_TOUCH_SE 0xa90000ULL
#define PAGANI_TOUCH_WRAPPER 0xac0000ULL
#define PAGANI_TOUCH_SMMU 0x15000000ULL
#define PAGANI_TOUCH_SMMU_SIZE 0x100000
#define PAGANI_TOUCH_SMMU_SID 0xa3
#define PAGANI_TOUCH_RSC 0x16520000ULL
#define PAGANI_TOUCH_RSC_SIZE 0x10000
#define PAGANI_TOUCH_HZ 19000000
#define PAGANI_TOUCH_CS_DELAY 50
#define PAGANI_TOUCH_WORD_DELAY 0

// ---- PMIC: piano = pm8010 (was pm8550) ----
#define PAGANI_PON_PPID 0x00c          // was 0x013   (pm8010@c reg = 12 0)
#define PAGANI_GPIO_PPID 0x00d         // was 0x18d   (pm8010@d reg = 13 0)
#define PAGANI_PON_POWER 0x80
#define PAGANI_PON_VOLUME_UP 0x40
#define PAGANI_GPIO_VOLUME_DOWN 6       // was 1       (gpio_keys/vol_up gpios = 1671 6 1)

// ---- keys: the piano has no "+" key (13T: GPIO 97) ----
#define PAGANI_PLUS_KEY_GPIO 0
#define PAGANI_PLUS_KEY_DRIVE 2

// ---- display: MDSS base + NT37801 WQHD+ panel (was AA594_P_7_A0020) ----
#define PAGANI_DSI_BASE 0xae00000ULL   // was 0xae94000 (mdss_mdp@ae00000)
#define PAGANI_BRIGHTNESS_MAX 2047      // was 0xdbb    (mdss-brightness-max-level = 2047)
#define PAGANI_BRIGHTNESS_DEFAULT 0x599
