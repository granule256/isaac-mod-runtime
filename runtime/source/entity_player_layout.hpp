#pragma once

// **本文件由 `tools/build_layout_table.py` 从 `tools/layout_tables/entity_player.json` 生成，请勿手改。**
//
// 每个常量都对应表里的一行，那一行带可复现证据（函数符号 + 指令地址）。
// 复核命令：`python3 tools/build_layout_table.py --table tools/layout_tables/entity_player.json --verify`
//
// 口径（与表的 `confidence` 一致）：
//   confirmed  —— 语义有独立锚点 ⇒ **可以**用于对外 API；
//   candidate  —— 偏移确定、名字只有间接依据 ⇒ 只作登记，不进 API；
//   structural —— 只说明结构，不声称字段名。

#include <cstdint>

namespace isaac::runtime::layout {

inline constexpr std::uint8_t kEntity_PlayerBuildId[20] = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31, 0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7, 0x23, 0x88, 0xB2, 0xAB
};

// 玩家能不能操作（PC 的 `EntityPlayer.ControlsEnabled`，**1 字节** bool）。模组会**写**它：MCM 打开设置菜单时 `player.ControlsEnabled = false` 冻住玩家（`modconfig.lua:1632`）。⚠️ 与 `+0x404` 的 `ControlsCooldown` 相邻（bool 在前、int32 在后）（confirmed）
//   证据：0x004422d4 —— ★ 语义锚点：引擎自己的『设置玩家能否操作』就是写这一格 —— `and w9, w1, #0x1`（参数是 bool）之后 `strb w9, [x10, #0x400]`（**按字节写** ⇒ 宽度 1），外层是遍历 `PlayerManager` 全部玩家的循环（`ldp x8, x9, [x0, #0x10]` → `ldr x10, [x8], #0x8` → `cmp`/`b.ne`）
//   证据：0x004422cc —— 同一函数里的 `and w9, w1, #0x1`：参数被夹成 0/1 才落进内存 ⇒ 内存里只会是 0 或 1（与 `kind=bool`、`width=1` 互相印证）
inline constexpr std::uintptr_t kEntity_PlayerControlsEnabledOffset = 0x400;
inline constexpr std::uintptr_t kEntity_PlayerControlsEnabledWidth = 1;

// 按键冷却（PC 的 `EntityPlayer.ControlsCooldown`，**有符号 int32**；EID 会**写**它来抑制按键连发）。取值锚点：麻痹药丸分支把它设成 240 或 120 帧。⚠️ `+0x408` 是**另一个**字段（`SetShootingCooldown`，取 max），不是本行（confirmed）
//   证据：0x002b265c —— `ldr w10, [x19, #0x404]` + `cmp #0` + `b.le` ⇒ 值 > 0 时不让射击（这就是『控制冷却』的用法）
//   证据：0x002e1c3c —— 麻痹药丸分支 `str w8, [x20, #0x404]`：写入的是上面 `csel` 出来的帧数
//   证据：0x002e1c2c —— `mov w8, #0xf0`(240) 与紧随的 0x2E1C30 `mov w9, #0x78`(120) 经 0x2E1C34 `csel` 二选一写进本字段 ⇒ 冷却按 240/120 **帧**计，是个帧计数
inline constexpr std::uintptr_t kEntity_PlayerControlsCooldownOffset = 0x404;
inline constexpr std::uintptr_t kEntity_PlayerControlsCooldownWidth = 4;

// 罐中生命，PC读取12A4；NS AddJarHearts读写并执行8上限与HUD刷新。（confirmed）
//   证据：0x00280030 —— 罐中生命，PC读取12A4；NS AddJarHearts读写并执行8上限与HUD刷新。 原始取证在dist/callback-rplus-20261013/player-api/evidence。
inline constexpr std::uintptr_t kEntity_PlayerJarHeartsOffset = 0x16CC;
inline constexpr std::uintptr_t kEntity_PlayerJarHeartsWidth = 4;

// 金炸弹标志（PC 的 `EntityPlayer:HasGoldenBomb()`，catalog `0x0E01004A`）—— `Entity_Player + 0x16D9` 那**一个字节**。取值锚点 = 引擎自己的一对同名函数（`AddGoldenBomb()` 置 1 / `RemoveGoldenBomb()` 清 0）；旁证：紧邻的 `0x16D8` 是「金**钥匙**」标志（`AddGoldenKey`/`RemoveGoldenKey` 写法逐字同形），两个相邻字节 = 两个「金色 X」标志（confirmed）
//   证据：0x002fc3f4 —— `add x8, x0, x8`（x8 = 上一条 0x2FC3F0 `mov w8, #0x16d9`）⇒ 目标 = `this + 0x16D9`；下一条 0x2FC3FC `strb w9, [x8]` 把 1 写进去
//   证据：0x002fc3f8 —— ★ 取值锚点（置 1）：`mov w9, #0x1` 之后 `strb w9, [x8]` —— 这一格是**布尔语义**，不是「某处有个字节」
//   证据：0x002fc490 —— 第二处独立锚点（清 0）：同一个 `mov w8, #0x16d9` + `strb wzr, [x8]` —— 一置一清两条构成完整的取值锚点
//   证据：0x00280588 —— 互证：紧邻的 0x16D8 是「金钥匙」标志（`mov w8, #0x16d8` + `strb`），写法与金炸弹逐字同形 ⇒ 0x16D8/0x16D9 是两个独立的「金色 X」状态位
inline constexpr std::uintptr_t kEntity_PlayerGoldenBombFlagOffset = 0x16D9;
inline constexpr std::uintptr_t kEntity_PlayerGoldenBombFlagWidth = 1;

// **「额外动画正在播放」标志**（u8，0/1）。PC 契约 `tools/pc_contract_docs/EntityPlayer.md:1760` 的 `void StopExtraAnimation ( )` 把**本格与下一格（相隔 2）一起清 0**；PC 上这两格是 `Entity_Player + 0x12E8` / `+0x12EA`（中间的 `0x12E9` PC **明确跳过**） ⇒ Switch 的 `+0x1710` / `+0x1712` **逐字同构**。★ 为什么能定案：① 消费者 `Entity_Player::IsExtraAnimationFinished @ 0x2B78C4` 第一句就 `mov w8,#0x1710` + `add x8,x0,x8` + `ldrb w9,[x8]` + `cbz`（**正在播放 ⇒ 直接返回 false**）；② 写入者 `Entity_Player::PlayExtraAnimation @ 0x2B0904` 在开始播放时 `strb w20(1),[x22]`（本格=1）并 `strb wzr,[x22,#0x2]`（邻格=0）；③ `tools/nro_find_offset_access.py 0x1710` 命中 40 处，全在 `Entity_Player` 的方法里、写法一律 `add x8,x0/x19,#0x1710` 之后 `ldrb/strb [x8]` 与 `[x8,#2]`。（confirmed）
//   证据：0x002b78c4 —— **具名消费者（函数名即语义）**：`mov w8, #0x1710` —— `IsExtraAnimationFinished` 的第一句就把 本格偏移装进寄存器（随后 `add x8,x0,x8` + `ldrb w9,[x8]` + `cbz` ⇒ 正在播放就返回 false）。★ 这里记的是**寄存器合成形态**的锚点（偏移整值就在这条 `mov` 上）。
//   证据：0x002b0914 —— **具名写入者**：`mov w8, #0x1710` + `add x22, x0, x8` —— `PlayExtraAnimation` 把本格地址留在 `x22`，随后 `0x2B0958 strb w20(=1), [x22]` 置 1。
//   证据：0x002b0950 —— **取值锚点**：`mov w20, #0x1` —— 紧接着 `strb w20, [x22]` 把本格写成 **1**（同函数 `0x2B0924` 先把邻格清 0）⇒「开始播放 ⇒ 正在播放=1、已结束=0」这一对由 这两条 `strb` 钉住。
inline constexpr std::uintptr_t kEntity_PlayerExtraAnimationPlayingOffset = 0x1710;
inline constexpr std::uintptr_t kEntity_PlayerExtraAnimationPlayingWidth = 1;

// **「额外动画已结束」标志**（u8，0/1）。与上一格**相隔 2**（中间的 `+0x1711` 本镜像里**未取证**、PC 也跳过它 ⇒ 我们的实现**必须逐字节只写这两格**）。★ 为什么能定案：消费者 `Entity_Player::IsExtraAnimationFinished @ 0x2B78C4` 在 `ldrb w9,[x8]`（`x8 = this + 0x1710`）为 0 之后，**同一条 `x8`** 上再 `ldrb w8,[x8,#0x2]`、 `cmp w8,#0` + `cset w0,eq` ⇒ 本格 =「基址 +2」= `+0x1712`，语义是「已结束」（函数名 `IsExtraAnimationFinished` 的返回值就是它）；★ `Entity_Player::PlayExtraAnimation @ 0x2B0924` 一进来就 `strb wzr,[x22,#0x2]`（开始播放 ⇒ 本格清 0）也印证这一对。（confirmed）
//   证据：0x002b78dc —— **寄存器合成形态的定位锚点**：`ldrb w8, [x8, #0x2]` —— `x8` 由同函数第一句 `mov w8,#0x1710` + `add x8,x0,x8` 定到 `this + 0x1710`，这里再 `+2` ⇒ 本格 = `this + 0x1712`。★ 立即数 `2` 就是这条指令里能核到的那一格。
//   证据：0x002b78e0 —— **取值锚点**：`cmp w8, #0x0` + 紧随的 `cset w0, eq` ——「本格为 0 ⇒ 返回 true（已结束）」 ⇒ 本格是布尔语义的『已结束』标志。
//   证据：0x002b0924 —— **具名写入者（清 0）**：`strb wzr, [x22, #0x2]` —— `x22 = this + 0x1710`（同函数 `mov w8,#0x1710` + `add x22,x0,x8`）⇒ 本格 = `this + 0x1712`，开始播放时被清 0。★ 立即数 `2` 是本条能核到的那一格；偏移整值由上面那条 `ldrb [x8,#0x2]` 钉住。
inline constexpr std::uintptr_t kEntity_PlayerExtraAnimationFinishedOffset = 0x1712;
inline constexpr std::uintptr_t kEntity_PlayerExtraAnimationFinishedWidth = 1;

// 受伤无敌冷却帧数，PC读取1308；NS伤害判定读取1734，Init置0，Twin同步有符号max。（confirmed）
//   证据：0x002a4908 —— 受伤无敌冷却帧数，PC读取1308；NS伤害判定读取1734，Init置0，Twin同步有符号max。 原始取证在dist/callback-rplus-20261013/player-api/evidence。
inline constexpr std::uintptr_t kEntity_PlayerDamageCooldownOffset = 0x1734;
inline constexpr std::uintptr_t kEntity_PlayerDamageCooldownWidth = 4;

// 射击延迟（PC 的 `EntityPlayer.MaxFireDelay`）。⚠️ **Switch 侧是 float**，PC AB+ 文档写 int —— 按 float 读。取值锚点：`Entity_Player::Init` 写默认 10.0f（confirmed）
//   证据：0x002b4150 —— `ldr w9, [x19, #0x1834]` → `str w9, [x8, #0x1c]` 抄进每个武器（同一段重复 5 次，对应 +0x1758/1760/1768/1770/1778 五个武器槽）⇒ 它是每帧被武器读取的射击延迟
//   证据：0x0027962c —— `mov x9, #0x41200000`(10.0f)（`movk x9, #0x3f80, lsl #48` 补的高 32 位 1.0f 是相邻的 `+0x1838`）→ 0x279660 `str x9, [x19, x8]`，x8 = 0x1834（见 0x27964c）⇒ 默认射击延迟 10.0
inline constexpr std::uintptr_t kEntity_PlayerMaxFireDelayOffset = 0x1834;
inline constexpr std::uintptr_t kEntity_PlayerMaxFireDelayWidth = 4;

// 眼泪伤害（PC 的 `EntityPlayer.Damage`，float）。取值锚点：`Entity_Player::Init` 把 `0x40600000`(3.5f，Isaac 的基础伤害) 写进这一格（confirmed）
//   证据：0x002ad6d4 —— `ldr s0, [x20, #0x1844]` → 乘倍率后写进 `TearParams::Damage`（0x2AD6DC `str s0, [x26, #0x48]!`）⇒ 这一格是『参与伤害计算的基数』
//   证据：0x00279664 —— `mov x9, #0x40600000`（低 32 位就是 3.5f；`movk x9, #0xc1be, lsl #48` 补的高 32 位是同批写的相邻字段）→ 0x279670 `str x9, [x19, x8]`，其中 x8 = 0x1844（见 0x279668 `mov w8, #0x1844`）⇒ 默认伤害 3.5
inline constexpr std::uintptr_t kEntity_PlayerDamageOffset = 0x1844;
inline constexpr std::uintptr_t kEntity_PlayerDamageWidth = 4;

// 眼泪射程（PC 的 `EntityPlayer.TearRange`，float，原始射程单位）。取值锚点：`Entity_Player::Init` 写默认 260.0f（= 6.5 × 40）（confirmed）
//   证据：0x002a9ba8 —— `ldr w8, [x19, #0x1854]` → 写进新生成子弹的射程字段 ⇒ 它是『子弹能飞多远』的输入
//   证据：0x002796bc —— `str w8, [x19, #0x1854]` —— 访问指令里就带字面偏移
//   证据：0x002796b8 —— 上一条 `mov w8, #0x43820000` 就是 260.0f（Isaac 的基础射程）⇒ 默认射程 260
inline constexpr std::uintptr_t kEntity_PlayerTearRangeOffset = 0x1854;
inline constexpr std::uintptr_t kEntity_PlayerTearRangeWidth = 4;

// 移动速度（PC 的 `EntityPlayer.MoveSpeed`，float）。取值锚点：`Entity_Player::Init` 写默认 1.0f（confirmed）
//   证据：0x002b1748 —— `ldr s0, [x19, #0x194c]` → `fmul`/`fadd` 参与每帧位移（同函数内另有两处同址读取）
//   证据：0x0027969c —— `mov w9, #0x3f800000`(1.0f) → 0x2796a0 `str x9, [x19, x8]`，x8 = 0x194c（见 0x279698）⇒ 基础速度 1.0
inline constexpr std::uintptr_t kEntity_PlayerMoveSpeedOffset = 0x194C;
inline constexpr std::uintptr_t kEntity_PlayerMoveSpeedWidth = 4;

// 能否飞（PC 的 `EntityPlayer.CanFly`，**1 字节** bool）。⚠️ 只改这一格不会立刻改变碰撞层：决定能否飞过石头/坑的是 `Entity+0x1E0`（见 `entity.json` 的 `FlyingLayer`），它由引擎在缓存重算时按本字段同步 —— PC 侧同样要求只在 `MC_EVALUATE_CACHE` 里改（confirmed）
//   证据：0x002bba20 —— ★ 证据形态是『寄存器合成』：`mov w8, #0x1954` 把偏移装进寄存器，**真正的访存是紧随其后的 0x2BBA24 `ldrb w8, [x19, x8]`**（该指令里没有字面立即数，工具核不到它，所以这里引的是准备寄存器那一条）。判据随后是 `cbz`，置位时函数返回 `Vector2(0, -4)` 的飞行视觉偏移（0x2BBA30 `fmov s1, #-4.00000000`）
//   证据：0x002ac3e4 —— 同一形态的第二处：`mov w8, #0x1954` → 0x2AC3E8 `ldrb w8, [x19, x8]`
//   证据：0x002ac3f0 —— ★ 语义锚点：读到的字节 `cmp w8, #0x0` 之后 `csel` 出 `5`（或另一层号），**写进 `Entity+0x1E0`**（0x2AC3F8 `str w8, [x20, #0x1e0]`，即 `entity.json` 已证明的飞行层）⇒ 这一格就是『能否飞』
inline constexpr std::uintptr_t kEntity_PlayerCanFlyOffset = 0x1954;
inline constexpr std::uintptr_t kEntity_PlayerCanFlyWidth = 1;

// `Entity_Player._cacheFlags`（**u32 缓存标志位掩码**）—— 玩家身上那个「哪些属性需要在下一帧重算」的字（PC 的 `EntityPlayer._cacheFlags`，PC 偏移 `+0x14B8`）。`EntityPlayer:AddCacheFlags(CacheFlag)` 就是 `_cacheFlags |= 参数`（PC 契约 `tools/pc_contract_docs/EntityPlayer.md:108/109`）。★ 取值锚点：`Entity_Player::DonateLuck`（捐款加运气）在给计数器加完之后**同时给这一格 OR 进 `0x400`（bit10 = `CACHE_LUCK`）**再跳 `EvaluateItems`；PC 侧同一个入口也写 `or [this+0x14b8], 0x400`（`0x427d51`/`0x5f38bb`）⇒ 两侧同一个位。★ 身份由 `EvaluateItems` 的逐位派发再钉一遍（`ldr w8,[x21]` 之后 `tbnz w8,#0/1/3/4/0xa` 与 `tbz w8,#0x8` 正好是 `CacheFlag` 的伤害/射速/射程/速度/幸运/武器位）。★ 与 PC 偏移 `0x14B8` **数值不同是布局差异，不许平移**。（confirmed）
//   证据：0x002f9980 —— `ldr w9, [x0, #0x1958]` —— 紧接的 `0x2f9988 orr w8, w9, #0x400` / `0x2f998c str w8, [x0, #0x1958]` 是「读-或-写回同一格」，随后 `0x2f9990 b Entity_Player::EvaluateItems` ⇒ 这一格就是「置缓存位、交给重算」的那个字
//   证据：0x002f9988 —— ★ 取值锚点：`orr w8, w9, #0x400` —— `0x400 = 1<<10 = CacheFlag.CACHE_LUCK`（「捐款加运气」当然要重算幸运）。PC 侧同一入口写 `or dword ptr [eax+0x14b8], 0x400`（`0x427d51` / `0x5f38bb`）⇒ 两版的「这位是幸运缓存」一致
//   证据：0x00293680 —— ★ 具名写入方把语义钉死：`0x29367c ldr w8,[x22,#0x54]`（道具配置自己的 `CacheFlags`，即既有的 `kItemConfigItemCacheFlagsOffset`）→ 本行这条 `ldr w9,[x20,#0x1958]`（读玩家这一格）→ `0x293684 orr w8, w9, w8` → `0x293688 str w8,[x20,#0x1958]` ⇒ 「拾取道具 ⇒ 把道具声明的缓存标志并进玩家这一格」。这一小段里同时出现两个已知偏移（`0x54` 与 `0x1958`），是把两者身份互证的直接证据
inline constexpr std::uintptr_t kEntity_PlayerCacheFlagsOffset = 0x1958;
inline constexpr std::uintptr_t kEntity_PlayerCacheFlagsWidth = 4;

// `std::vector<RNG>` 的 **begin**（PC 的四条 `Get*RNG` 用的就是这张表）：`Entity_Player + 0x1bb0`，元素 16 字节（`RNG` 对象），**索引就是枚举 id 本身**。end 在 +8（cap 在 +16）。元素个数**不写死**（`Entity_Player::Init` 按一个全局源列表的长度建表）⇒ 运行时按 `(end − begin) / 16` 算（confirmed）
//   证据：0x00441864 —— 该函数按 id 取这一格：`ldr x8, [x22, #0x1bb0]`（紧接着 `sub`/`lsr #4` 算出元素个数、`add x8, x8, w20, uxtw #4` 取第 id 格）
//   证据：0x0044186c —— ★ 取值锚点：`lsr x9, x9, #0x4`（end − begin 右移 4）⇒ **元素 16 字节**，与 `runtime_constants.hpp` 的 `kEntityObjectSize`/`kRngObjectSize = 16` 一致
//   证据：0x00278e18 —— 第二处独立站点（建表）：`mov w8, #0x1bb0` + `add x20, x19, x8`，随后循环里 `bl std::vector<RNG>::push_back`（0x27A530：容量检查 `>>4`、写入步长 `#0x10`）⇒ 这张表是逐格 push 出来的 `vector<RNG>`
inline constexpr std::uintptr_t kEntity_PlayerCollectibleRngVectorOffset = 0x1BB0;
inline constexpr std::uintptr_t kEntity_PlayerCollectibleRngVectorWidth = 8;

// `std::vector<RNG>` 的 **begin**（PC 的四条 `Get*RNG` 用的就是这张表）：`Entity_Player + 0x1bc8`，元素 16 字节（`RNG` 对象），**索引就是枚举 id 本身**。end 在 +8（cap 在 +16）。元素个数**不写死**（`Entity_Player::Init` 按一个全局源列表的长度建表）⇒ 运行时按 `(end − begin) / 16` 算（confirmed）
//   证据：0x00441b20 —— 该函数按 id 取这一格：`ldr x8, [x22, #0x1bc8]`（紧接着 `sub`/`lsr #4` 算出元素个数、`add x8, x8, w20, uxtw #4` 取第 id 格）
//   证据：0x00441b28 —— ★ 取值锚点：`lsr x9, x9, #0x4`（end − begin 右移 4）⇒ **元素 16 字节**，与 `runtime_constants.hpp` 的 `kEntityObjectSize`/`kRngObjectSize = 16` 一致
inline constexpr std::uintptr_t kEntity_PlayerTrinketRngVectorOffset = 0x1BC8;
inline constexpr std::uintptr_t kEntity_PlayerTrinketRngVectorWidth = 8;

// `std::vector<RNG>` 的 **begin**（PC 的四条 `Get*RNG` 用的就是这张表）：`Entity_Player + 0x1be0`，元素 16 字节（`RNG` 对象），**索引就是枚举 id 本身**。end 在 +8（cap 在 +16）。元素个数**不写死**（`Entity_Player::Init` 按一个全局源列表的长度建表）⇒ 运行时按 `(end − begin) / 16` 算（confirmed）
//   证据：0x002e0014 —— 该函数按 id 取这一格：`ldr x8, [x20, #0x1be0]`（紧接着 `sub`/`lsr #4` 算出元素个数、`add x8, x8, w20, uxtw #4` 取第 id 格）
//   证据：0x002e001c —— ★ 取值锚点：`lsr x9, x9, #0x4`（end − begin 右移 4）⇒ **元素 16 字节**，与 `runtime_constants.hpp` 的 `kEntityObjectSize`/`kRngObjectSize = 16` 一致
inline constexpr std::uintptr_t kEntity_PlayerPillRngVectorOffset = 0x1BE0;
inline constexpr std::uintptr_t kEntity_PlayerPillRngVectorWidth = 8;

// `std::vector<RNG>` 的 **begin**（PC 的四条 `Get*RNG` 用的就是这张表）：`Entity_Player + 0x1bf8`，元素 16 字节（`RNG` 对象），**索引就是枚举 id 本身**。end 在 +8（cap 在 +16）。元素个数**不写死**（`Entity_Player::Init` 按一个全局源列表的长度建表）⇒ 运行时按 `(end − begin) / 16` 算（confirmed）
//   证据：0x002e9130 —— 该函数按 id 取这一格：`ldr x19, [x28, #0x1bf8]`（紧接着 `sub`/`lsr #4` 算出元素个数、`add x8, x8, w20, uxtw #4` 取第 id 格）
//   证据：0x002e9138 —— ★ 取值锚点：`lsr x9, x9, #0x4`（end − begin 右移 4）⇒ **元素 16 字节**，与 `runtime_constants.hpp` 的 `kEntityObjectSize`/`kRngObjectSize = 16` 一致
inline constexpr std::uintptr_t kEntity_PlayerCardRngVectorOffset = 0x1BF8;
inline constexpr std::uintptr_t kEntity_PlayerCardRngVectorWidth = 8;

// `QueueItemData`（PC 的 `EntityPlayer.QueuedItem`）：**内嵌**在 `Entity_Player + 0x1C38`，步长 0x18。字段 = `Item*`(+0x00) / `Charge i32`(+0x08) / `Touched u8`(+0x0C) / `VarData i32`(+0x10，PC 文档未列)。写（`QueueItem`）、读（`FlushQueueItem`）、清（`DestroyQueueItem`）三个独立函数给出同一组偏移（confirmed）
//   证据：0x002924d4 —— `add x8, x19, x8`（x8 = 0x2924D0 `mov w8, #0x1c38`）⇒ 结构基址；紧随 0x2924D8 `str x20, [x19, #0x1c38]` 写 `Item*`、0x2924DC `str w23, [x19, #0x1c40]` 写 Charge、0x2924E0 `strb w22, [x8, #0xc]` 写 Touched、0x2924E4 `str w21, [x19, #0x1c48]` 写 VarData
//   证据：0x00292710 —— 消费侧按同一组偏移读：`ldr x8, [x19, #0x1c38]`（非空才继续），随后 0x292714 `ldr w21, [x19, #0x1c40]`（Charge）、0x292718 `ldrb w24, [x9, #0xc]`（Touched，x9 = x19+0x1C38）
//   证据：0x002929b4 —— 清空侧：0x2929B4 `str xzr, [x19, #0x1c38]` + 0x2929B8 `str wzr, [x19, #0x1c40]` + 0x2929BC `strb wzr, [x8, #0xc]` + 0x2929C0 `str wzr, [x19, #0x1c48]` —— 四条清空再次覆盖同一个四字段结构
//   证据：0x002924d0 —— ★ 结构性锚点：`mov w8, #0x1c38` 合成出结构基址（低半字即可，0x1C38 < 0x10000）⇒ 后面四条 `str` 的相对偏移 +0x00/+0x08/+0x0C/+0x10 都落在这个 0x18 字节的结构里
inline constexpr std::uintptr_t kEntity_PlayerQueuedItemDataOffset = 0x1C38;
inline constexpr std::uintptr_t kEntity_PlayerQueuedItemDataWidth = 24;

// `QueueItemData.Charge`（`= 0x1C38 + 0x08`）：玩家举着的那件道具的**充能数**（PC 的 `QueueItemData.Charge`，int）。EID 写的是 `player.QueuedItem.Charge > 0` —— 读不到时给 nil 会让那一句抛 `attempt to compare nil with number`（confirmed）
//   证据：0x002924dc —— 写入侧：`str w23, [x19, #0x1c40]`（w23 = 第 2 个形参 `int`）
//   证据：0x00292714 —— 读取侧：`ldr w21, [x19, #0x1c40]` —— 随后被喂给 `AddCollectible(..., charge, ...)`（0x2927D0 一带）
//   证据：0x002924d0 —— 结构性锚点：结构基址由 `mov w8, #0x1c38` 合成，本行是它的 +0x08 那一格（两处独立读写都落在 `#0x1c40`）
inline constexpr std::uintptr_t kEntity_PlayerQueuedItemChargeOffset = 0x1C40;
inline constexpr std::uintptr_t kEntity_PlayerQueuedItemChargeWidth = 4;

// 金心数，PC720150读取186C；NS AddGoldenHearts读写1DC4并夹值。（confirmed）
//   证据：0x002fc990 —— 金心数，PC720150读取186C；NS AddGoldenHearts读写1DC4并夹值。 原件见player-api/evidence。
inline constexpr std::uintptr_t kEntity_PlayerGoldenHeartsOffset = 0x1DC4;
inline constexpr std::uintptr_t kEntity_PlayerGoldenHeartsWidth = 4;

// 被遗忘者副身体，NS update_forgotten_state创建0x2FA0真实玩家并写此字段，PC GetSubPlayer读1CB8。（confirmed）
//   证据：0x002e814c —— 被遗忘者副身体，NS update_forgotten_state创建0x2FA0真实玩家并写此字段，PC GetSubPlayer读1CB8。 原始取证在dist/callback-rplus-20261013/player-api/evidence。
inline constexpr std::uintptr_t kEntity_PlayerSubPlayerOffset = 0x2460;
inline constexpr std::uintptr_t kEntity_PlayerSubPlayerWidth = 8;

// 腐心数，PC7200D0读取1CC4；NS AddRottenHearts读写2474及生命同步。（confirmed）
//   证据：0x002fecec —— 腐心数，PC7200D0读取1CC4；NS AddRottenHearts读写2474及生命同步。 原件见player-api/evidence。
inline constexpr std::uintptr_t kEntity_PlayerRottenHeartsOffset = 0x2474;
inline constexpr std::uintptr_t kEntity_PlayerRottenHeartsWidth = 4;

// 对外 API 只允许读这些字段（`confidence == confirmed`）。
// 当前可用：Damage、MaxFireDelay、TearRange、MoveSpeed、CanFly、ControlsEnabled、ControlsCooldown、GoldenBombFlag、QueuedItemData、QueuedItemCharge、CollectibleRngVector、TrinketRngVector、PillRngVector、CardRngVector、CacheFlags、ExtraAnimationPlaying、ExtraAnimationFinished、DamageCooldown、JarHearts、SubPlayer、GoldenHearts、RottenHearts

} // namespace isaac::runtime::layout
