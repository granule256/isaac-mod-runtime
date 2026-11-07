#pragma once

// **本文件由 `tools/build_layout_table.py` 从 `tools/layout_tables/game.json` 生成，请勿手改。**
//
// 每个常量都对应表里的一行，那一行带可复现证据（函数符号 + 指令地址）。
// 复核命令：`python3 tools/build_layout_table.py --table tools/layout_tables/game.json --verify`
//
// 口径（与表的 `confidence` 一致）：
//   confirmed  —— 语义有独立锚点 ⇒ **可以**用于对外 API；
//   candidate  —— 偏移确定、名字只有间接依据 ⇒ 只作登记，不进 API；
//   structural —— 只说明结构，不声称字段名。

#include <cstdint>

namespace isaac::runtime::layout {

inline constexpr std::uint8_t kGameBuildId[20] = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31, 0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7, 0x23, 0x88, 0xB2, 0xAB
};

// 玩家上一个待过的房间在房间列表里的索引（PC 侧 `Level:GetPreviousRoomIndex()` 读的就是这一格；PC 在 `Level+0x18198`，Switch 换成了 0x2155C）。`Level` 内嵌在 `Game` 起始处（同一地址）⇒ 本表（`struct: Game`）里的这一行同时就是 `Level` 的字段；`runtime_constants.hpp` 里叫 `kLevelPreviousRoomIndexOffset`（与既有的 `kLevelCurrentRoomIndexOffset` 同名同族）。这一格与紧邻的 `+0x21564` 构成一对：`Level::GetLastRoomDesc()` 把 `[+0x2155C]` 当第一个实参、`[+0x8]`（即 `+0x21564`）当第二个实参，尾调 `Level::GetRoomByIdx(int roomListIndex, int dimension)` —— 与已知的「当前房间」那一对（`0x21558` 索引 / `0x21560` 维度）逐字同形。（confirmed）
//   证据：0x003dc69c —— **低半字**：`mov w8, #0x155c`（下一条 0x3DC6A0 `movk w8, #0x2, lsl #16` 补高半字 ⇒ 合成 **0x2155C**）
//   证据：0x003dc6a0 —— **高半字**：`movk w8, #0x2, lsl #16` —— 与上一条合成 0x2155C；随后 0x3DC6A4 `add x8, x0, x8` 取这一对的**地址**，0x3DC6A8 `ldr w1,[x8]` 与 0x3DC6AC `ldr w2,[x8,#0x8]` 两个实参尾调 `Level::GetRoomByIdx(int, int)` ⇒ 这一格是**索引**（不是维度、不是描述符）
//   证据：0x00465ab4 —— **独立读者一（低半字）**：`Room::TrySpawnDevilRoomDoor(bool, bool)` 里 `mov w9, #0x155c` + 0x465AB8 `movk w9, #0x2, lsl #16` + 0x465ABC `add x9, x8, x9` ⇒ 同一格
//   证据：0x00466c48 —— **独立读者二**：`Room::TrySpawnBossRushDoor(bool, bool)` 也取这一格 —— 函数名即语义（Boss Rush 门只在「刚从 Boss 房出来」时才开）
//   证据：0x00472130 —— **独立读者三**：`Room::TrySpawnBlueWombDoor(bool, bool, bool)`（蓝子宫门，同样要看上一个房间）
inline constexpr std::uintptr_t kGamePreviousRoomIndexOffset = 0x2155C;
inline constexpr std::uintptr_t kGamePreviousRoomIndexWidth = 4;

// 本层最后一个 Boss 房在房间列表里的索引（PC 侧 `Level:GetLastBossRoomListIndex()` 读的就是这一格；PC 在 `Level+0x181A4`）。判据来自引擎自己的具名读者：`Room::IsCurrentRoomLastBoss()` 把当前房间描述符的 `+0x8`（房间自己的列表索引）与这一格比较 ⇒ 这一格装的必然是「另一个房间的列表索引」，而那个函数问的正是「当前房间是不是最后一个 Boss 房」。另有 `Level::ShowBossRoom` / `Level::CanSpawnDevilRoom` / `Room::TriggerBossDeath` / `StageTransition::Update` / `Level::RestoreGameState` / `Level::GetLocalStageType` 在读它。（confirmed）
//   证据：0x00464460 —— 低半字：`mov w10, #0x1568`（下一条 0x464464 `movk w10, #0x2, lsl #16` 补高半字 ⇒ 合成 0x21568）。同一函数先读 `[Game+0x21558]`（当前房间索引）与 `w2 = -1` 调 `Level::GetRoomByIdx` 拿到当前描述符，再 `ldr w8,[x0,#0x8]` 与这一格比较 ⇒ 结构即语义：比的是两个「房间列表索引」
//   证据：0x00464464 —— **高半字**：`movk w10, #0x2, lsl #16` —— 与上一条合成 0x21568
//   证据：0x003e7a14 —— **独立读者一（低半字）**：`Level::CanSpawnDevilRoom()` 里 `mov w8, #0x1568` + 0x3E7A18 `movk w8, #0x2, lsl #16` + 0x3E7A1C `ldrsw x8, [x19, x8]` ⇒ 恶魔房只在「打完最后一个 Boss 房」之后才可能出现
//   证据：0x003e7128 —— **独立读者二**：`Level::ShowBossRoom()`（把 Boss 房在地图上标出来）读同一格
inline constexpr std::uintptr_t kGameLastBossRoomListIndexOffset = 0x21568;
inline constexpr std::uintptr_t kGameLastBossRoomListIndexWidth = 4;

// 玩家数组（`std::vector<Entity_Player*>`）的 **begin**：`Game+0x25C50`；`end` 在 +0x25C58（本表下一行）、`capacity` 在 +0x25C60。这一对就是 PC 侧 `Game():GetPlayer(i)` / `Isaac.GetPlayer(i)` 的真值来源（本镜像**没有** `PlayerManager::GetPlayer(int)`，必须自己索引）。命名与 `runtime_constants.hpp` 的 `kGamePlayerArrayBeginOffset` 是同一个字段（那一份是运行时的取名，这里是布局表的登记）（confirmed）
//   证据：0x0035a0ec —— 低半字：`mov w8, #0x5c50`（下一条 0x35A0F0 `movk w8, #0x2, lsl #16` 补高半字 ⇒ 0x25C50）
//   证据：0x0035a0f0 —— 高半字：`movk w8, #0x2, lsl #16` —— 与上一条合成 0x25C50
//   证据：0x00351b84 —— `add x21, x8, x9`，其中 x9 = 前两条（0x351B7C `mov w9, #0x5c50` + 0x351B80 `movk w9, #0x2, lsl #16`）合成的 0x25C50 ⇒ x21 指向本行这一格；紧随 0x351B88 `ldp x8, x9, [x21]` 一次读出 begin/end。证据里的 offset 写的是指令里那个立即数 0x5C50（0x25C50 的高半字在前一条 movk 上），与本表 `TimeCounter` 那行的写法一致
//   证据：0x00351b90 —— 取值锚点：`lsr x9, x9, #3`，x9 = end − begin（0x351B8C `sub x9, x9, x8`）⇒ 元素 8 字节（指针），正是 `std::vector<Entity_Player*>` 的形状；`Game::GetRandomPlayer` 0x35A114 的 `asr x23, x21, #3` 是同一形态的第二处
inline constexpr std::uintptr_t kGamePlayerArrayBeginOffset = 0x25C50;
inline constexpr std::uintptr_t kGamePlayerArrayBeginWidth = 8;

// 玩家数组（`std::vector<Entity_Player*>`）的 **end**：`Game+0x25C58` = begin(0x25C50) + 8。与上一行成对使用（`end − begin` 再 `>>3` 就是玩家数）；命名与 `runtime_constants.hpp` 的 `kGamePlayerArrayEndOffset` 是同一个字段（confirmed）
//   证据：0x0035a100 —— `ldp x22, x9, [x8]`：x8 = `Game+0x25C50`（0x35A0EC/0x35A0F0 合成）⇒ 这一对装载就是 begin(0x25C50) 与 end(本行 0x25C58)；紧随 0x35A10C `subs x21, x9, x22` 取字节差。大偏移在访存指令里只剩寄存器，所以这条证据的 offset 只能是 0（一次 16 字节装载），本行的绝对偏移由上一行的合成 + 这里的 +8 决定
//   证据：0x0035a114 —— 取值锚点：`asr x23, x21, #3`（x21 = 0x35A10C 算出的 end − begin）⇒ 元素 8 字节 ⇒ 这一对是 `std::vector<Entity_Player*>` 的 begin/end
//   证据：0x0035a2ac —— 第二处独立站点：0x35A294/0x35A298 同样合成 0x25C50、0x35A2A0 `ldp x8, x9, [x22]` 同一对、0x35A2A4 `sub x9, x9, x8`、本条 `lsr x9, x9, #3` ⇒ 与上一行互为印证
inline constexpr std::uintptr_t kGamePlayerArrayEndOffset = 0x25C58;
inline constexpr std::uintptr_t kGamePlayerArrayEndWidth = 8;

// `Seeds` 对象**内嵌**在 `Game` 里（PC 的 `Game:GetSeeds()` 返回值）：基址 = `Game + 0x25D40`（**加法**，不是解指针）。用途：`Game:GetSeeds()` 以及 `Seeds:GetStartSeed()`/`IsCustomRun()` 都在这条链上（本表下面两行）（confirmed）
//   证据：0x0034e5dc —— 访问形态：`add x22, x20, x8`，其中 x8 = 前两条（0x34E5D0 `mov w8, #0x5d40` + 0x34E5D4 `movk w8, #0x2, lsl #16`）合成的 0x25D40；随后 `mov x0, x22` 把它当 `Seeds::operator=` 的 `this`。本行的 offset 按项目既有惯例写低半字（0x5D40）—— 高半字在 `movk` 上，验证器比的是单条指令里的立即数
//   证据：0x0034e5d0 —— 低半字：`mov w8, #0x5d40`
//   证据：0x0034e5d4 —— 高半字：`movk w8, #0x2, lsl #16` —— 与上一条合成 0x25D40（`Seeds` 内嵌在 `Game` 里的基址）
inline constexpr std::uintptr_t kGameSeedsObjectOffset = 0x25D40;
inline constexpr std::uintptr_t kGameSeedsObjectWidth = 112;

// 「本局用的是玩家自选种子」标志（`Seeds + 0x00` 那一个字节，PC 的 `Seeds:IsCustomRun()` 的确证那一半）：三处写（控制台 `seed <串>` / 角色选择界面输入种子 / `Game::StartDebug`）、三处读（`AchievementUnlocksDisallowed` 的「非 0 ⇒ 本局禁成就」、`Restart` 的「非 0 ⇒ 沿用同一颗种子」、本项目的 `IsCustomRun`）。PC 文档把「挑战局」也算 `IsCustomRun`，而镜像里写这一字节的只有那三处 ⇒ OR 上 `Game+0x26FA88` 的那一半是推断，未实现（confirmed）
//   证据：0x0049ed6c —— 语义锚点（读）：`ldrb w8, [x0]` + `cbz` ⇒ 置位就直接 `return 1`（本局禁成就），与「自定义种子局禁成就」一致
//   证据：0x004a1218 —— 第二处独立读：`ldrb w8, [x0]` 非 0 才去 `ldr w1, [x0, #0x4]` 沿用原种子
//   证据：0x0034fb30 —— 第三处独立写路径：`add x23, x0, x8`（x8 = 0x34FB28 `mov w8, #0x5d40` + 0x34FB2C `movk w8, #0x2, lsl #16` = 0x25D40），随后 0x34FB58 `strb w10, [x23]` 把 1 写进这一格（同一条 `mov w10, #0x1` 还写了 `Game+0x26FA8E` 的调试标志）。offset 按惯例写低半字
//   证据：0x0034faf0 —— 取值锚点（写）：`mov w10, #0x1` —— 同一个寄存器在 0x34FB58 `strb w10, [x23]` 里写进本格
//   证据：0x0040554c —— 第四条独立写路径（角色选择界面输入种子）：`mov w8, #0x1` —— 同一个标志语义写进菜单挂起的那份 Seeds（`g_MenuManager + 0x600`，0x40569C `strb w8, [x9, #0x600]`；有效种子 = 1、无效串 = 0）⇒ 说明这一字节的语义不是「只有控制台才用」
inline constexpr std::uintptr_t kGameSeedsCustomRunFlagOffset = 0x25D40;
inline constexpr std::uintptr_t kGameSeedsCustomRunFlagWidth = 1;

// 本局起始种子（`Seeds + 0x04`，PC 的 `Seeds:GetStartSeed()`，catalog `0x0F010002`）：取值 1..2^32−1、主菜单 0。唯一写它的是 `Seeds::SetStartSeed(unsigned)`（0 时取 `RandomU32() ?: 1`）；PC 返回类型是 `int` ⇒ 运行时按 int32 呈现（confirmed）
//   证据：0x004a1124 —— 写入侧：`str w1, [x0, #0x4]`（w1 = 第 1 个形参 seed）⇒ `Seeds + 0x04`
//   证据：0x004a1130 —— 取值锚点：`cmp w0, #0x1` + `csinc w1, w0, wzr, hi` ⇒ 为 0 时取 `RandomU32()` 且保证 ≥1，与 PC 文档 `Seeds.md:79` 的「1 与 2^32−1 之间」逐字吻合
//   证据：0x004a1220 —— 第二个独立读者：`ldr w1, [x0, #0x4]` —— 带自定义种子时重开沿用同一颗（0x4A1218 先读 `[x0]` 那个标志）
inline constexpr std::uintptr_t kGameSeedsStartSeedOffset = 0x25D44;
inline constexpr std::uintptr_t kGameSeedsStartSeedWidth = 4;

// 局内计时（PC 的 `game.TimeCounter`，**有符号** int32，30fps 帧钟：`Game::Update` 每帧与 `FrameCount` 一起 +1）（confirmed）
//   证据：0x003518b0 —— 低半字：`mov w8, #0xf998` + 0x3518B4 `movk w8, #0x24, lsl #16` = 0x24F998，`add x24, x0, x8` ⇒ x24 指向这一组计数器的基址（`FrameCount` 在 0x24F99C）
//   证据：0x003518b4 —— 高半字：`movk w8, #0x24, lsl #16` —— 与上一条合成 0x24F998
//   证据：0x00352114 —— `ldp w8, w9, [x24, #0x4]`：一次读两个相邻计数器 —— +4 是 0x24F99C（`FrameCount`），+8 就是**本行 0x24F9A0**（本字段）；随后 `add …,#1` 两次、0x352120 `stp w8, w9, [x24, #0x4]` 写回 ⇒ 两个计数器每帧一起 +1
//   证据：0x00352120 —— 同一对的写回（`stp w8, w9, [x24, #0x4]`，8 字节）；本行的 offset = 上面合成出来的基址 0x24F998 + 这个立即数 4 + 4（第二个字）
//   证据：0x0003ef3c —— 低半字：控制台 `time` 命令 `mov w9, #0xf9a0` + 0x3EF40 `movk w9, #0x24, lsl #16` = 0x24F9A0；0x3EF48 `ldrsw x8, [x8, x9]`（**有符号**读，`ldrsw`）后除以 30 输出秒
//   证据：0x0003ef40 —— 同上（高半字 `movk w9, #0x24, lsl #16`）
//   证据：0x0041e020 —— 取值锚点：SPEED 挑战倒计时算的是 `28800 − 本字段`（0x41E028 `sub w20, w9, w8`，其中 w8 = 0x41E00C 读出的本字段）。28800 帧 = 16 分钟 × 30 帧/秒 ⇒ 本字段是 30fps 帧钟；同一段 `ldrsw`/`mul` 序列也解释了『有符号』
inline constexpr std::uintptr_t kGameTimeCounterOffset = 0x24F9A0;
inline constexpr std::uintptr_t kGameTimeCounterWidth = 4;

// `Darken` 的持续时间倒计时（int，单位 = 帧）。PC 侧 `Game:Darken(float Darkness, int Timeout)` 的第二个形参写的就是它（`__thiscall`，两个标量形参；绑定本体 `0x432F60`）。与 `+0x24F9C0`（TargetDarkness，float）相隔 8、中间夹着 `+0x24F9BC`（插值量，本表不登记） ⇒ 两格不相邻，绝不能用一条 `u64`/`u32` 掩盖（那会静默写坏中间那一格）。为什么能定案：`Entity_NPC::ai_lamb` 写成对默认值时把这一格写成 `600`（`mov w9,#0x258` + `str w9,[x8]`，`x8 = Game + 0x24F9B8`）、把邻格写成 `1.0f`；`Game::Update @ 0x352168` 每帧 `subs w8,w8,#0x1` 递减它 ⇒「600 帧的倒计时」由默认值 + 每帧递减两头对上。（confirmed）
//   证据：0x00169bc8 —— 偏移合成锚点（整格的地址就在这里）：`mov w9, #0xf9b8` + `movk w9, #0x24, lsl #16` ⇒ `w9 = 0x24F9B8`；随后 `add x8,x8,x9` 把 `Game*` 加成本格地址。这一对指令是本行偏移唯一的整值出处（本格的访问全是寄存器寻址）。
//   证据：0x00169bd8 —— **取值锚点**：`mov w9, #0x258`（= **600**）—— 紧跟一句 `str w9, [x8]` 把它写进本格；「600 帧的倒计时」这个量级正是默认时长。
//   证据：0x0035216c —— **具名消费者（每帧递减）**：`Game::Update` 里 `subs w8, w8, #0x1` —— 上一条 `ldr w8,[x24,#0x20]` 读的就是本格 ⇒ 它是**每帧减一的倒计时**，不是目标值（PC 的 `Timeout` 也是帧数）。
inline constexpr std::uintptr_t kGameDarknessTimeoutOffset = 0x24F9B8;
inline constexpr std::uintptr_t kGameDarknessTimeoutWidth = 4;

// `Darken` 的目标暗度（float）。PC 侧 `Game:Darken(float Darkness, int Timeout)` 写的就是这一格（PC 契约 `tools/pc_contract_docs/Game.md:129`；数值不许平移）。它旁边是 `+0x24F9B8`（Timeout，int）与 `+0x24F9BC`（插值量，本表不登记）—— 三格连续，本行只认那个 float。为什么能定案：① `Entity_NPC::ai_lamb`（兰姆战那一套）在 `0x169BC4..0x169BE0` 把 `Game + 0x24F9B8` 与 `Game + 0x24F9C0` 成对写成默认值 `600` 与 `1.0f`（地址由 `mov w9,#0xf9b8` + `movk w9,#0x24,lsl#16` 合成，再 `str w10(0x3F800000),[x8,#0x8]` / `str w9(0x258),[x8]`）⇒「暗度目标 = 1.0f、持续 600 帧」；② `Game::Update @ 0x352168` 每帧 `subs` 递减那一格 int、同函数紧随 `ldr s0,[x24,#0x24]` 读本格（递减的是倒计时、被读的是目标暗度）；③ 渲染侧 `Room::GetLightingAlpha @ 0x477504` 读本格算最终亮度。（confirmed）
//   证据：0x00169bdc —— 成对写入（默认值锚点）：`str w10, [x8, #0x8]` —— `w10 = 0x3F800000`（`1.0f`）、`x8 = Game + 0x24F9B8`（由紧邻的 `mov w9,#0xf9b8` + `movk w9,#0x24,lsl#16` + `add x8,x8,x9` 合成）⇒ 本格 = 基址 +8 = `Game + 0x24F9C0`，写的是 `1.0f`。紧接着的 `str w9(=600), [x8]` 把 Timeout 写成 600 ⇒ 两格的语义由这一对默认值同时钉住。本条记的是寄存器合成形态里能核到的那一格（立即数 `8`），偏移整值由 `mov w9,#0xf9b8` + `movk w9,#0x24,lsl#16` 两条合成（另见下一条）。
//   证据：0x00169bc8 —— **偏移合成锚点（低半字）**：`mov w9, #0xf9b8` —— 紧接 `movk w9, #0x24, lsl #16` 合成 `0x24F9B8`，随后 `add x8,x8,x9` 把它加进 `Game*` ⇒ 基址就是 `Game + 0x24F9B8`；本格（`+0x24F9C0`）就是由它 `+8` 得到的那一格。
//   证据：0x00352168 —— 具名消费者（函数名即语义）：`Game::Update` 里 `ldr w8, [x24, #0x20]` —— `x24 = Game + 0x24F998` 一类基址，`+0x20` 落到 `0x24F9B8`（Timeout，下一步 `subs` 递减它）；同函数紧随 `ldr s0, [x24, #0x24]` 读的就是本格（`+0x24` = `0x24F9C0`）。递减的是 `+0x24F9B8`（时长）、被读的是本格（目标暗度）—— 两个角色由这一对指令分开。
//   证据：0x00477504 —— 具名消费者（渲染侧）：`Room::GetLightingAlpha` 的入口（`sub sp, sp, #0x50`）——该函数把本格（`Modifier × TargetDarkness`）算进最终亮度。它对两格是寄存器寻址，所以这一条只证「本格被这个具名函数读」。
inline constexpr std::uintptr_t kGameTargetDarknessOffset = 0x24F9C0;
inline constexpr std::uintptr_t kGameTargetDarknessWidth = 4;

// 本局挑战模式（PC 的 `game.Challenge`，`eChallenge` 枚举原值，int32）（confirmed）
//   证据：0x0034e548 —— 低半字：`mov w8, #0xfa88`（下一条 0x34E54C `movk w8, #0x26, lsl #16` 补高半字 ⇒ 0x26FA88）；0x34E550 `add x21, x0, x8` 之后 0x34E570 `str w2, [x21]` 写进去的是**第 2 个形参**，而 `Game::Start` 的签名里第 2 个参数就是 `eChallenge`
//   证据：0x0034e54c —— 高半字：`movk w8, #0x26, lsl #16` —— 与上一条 `mov w8, #0xfa88` 合成 0x26FA88
//   证据：0x0034ea90 —— 同形的第二处：读该字段作为第 1 个实参，尾跳到 `Manager::GetChallengeParams(eChallenge)`（0x34EAA4 → 0x671860）⇒ 这一格就是 `eChallenge`
//   证据：0x0034ea94 —— 同上（高半字 `movk w8, #0x26, lsl #16`）
//   证据：0x0041e010 —— 取值锚点：小地图渲染把该字段与 `0x16`(=22) 比较，命中时算 `28800 − TimeCounter`（0x41E020 `mov w9, #0x7080`；0x41E028 `sub w20, w9, w8`）—— 28800 帧 = 16 分钟 × 30fps 正是 SPEED 挑战的限时，而 IsaacDocs 快照里 `enums/Challenge.md` 写明 22 = `CHALLENGE_SPEED` ⇒ 该字段确实是 `eChallenge`
inline constexpr std::uintptr_t kGameChallengeOffset = 0x26FA88;
inline constexpr std::uintptr_t kGameChallengeWidth = 4;

// 胜利圈计数（PC 的 `Game:GetVictoryLap()`，catalog `0x02010009`）：普通局 0、跑圈 1..3。**写它的就是同名函数** `Game::NextVictoryLap()`（读一格 +1 写回，首次进圈顺带把难度改成 HARD）；另有五个独立读者都拿它与 1/2/3 比较（confirmed）
//   证据：0x0034fe58 —— 低半字：`mov w8, #0xfd50`（下一条 0x34FE5C `movk w8, #0x26, lsl #16` 补高半字 ⇒ 0x26FD50）
//   证据：0x0034fe5c —— 高半字：`movk w8, #0x26, lsl #16` —— 与上一条合成 0x26FD50；随后 0x34FE60 `ldr w9, [x19, x8]` / 0x34FE64 `add w10, w9, #1` / 0x34FE68 `str w10, [x19, x8]`（读一格 +1 写回）
//   证据：0x002fc558 —— 独立读者一（低半字，与读者自己的高半字 0x2FC55C 合成 0x26FD50）：这一格被读出来给参数判断用
//   证据：0x002fc56c —— 取值锚点：与 2 比较（落在 0..3 的跑圈取值域里）
//   证据：0x003ad740 —— 独立读者二（低半字，与 0x3AD744 的高半字合成 0x26FD50）
//   证据：0x003ad74c —— 取值锚点：`cmp w8, #0x1` 之后 `b.lt` ⇒ ≥1 才画跑圈标记，与「跑圈才有 HUD 标记」一致
inline constexpr std::uintptr_t kGameVictoryLapOffset = 0x26FD50;
inline constexpr std::uintptr_t kGameVictoryLapWidth = 4;

// 难度（PC 的 `game.Difficulty`，`eDifficulty`：0=NORMAL / 1=HARD / 2=GREED / 3=GREEDIER，int32）（confirmed）
//   证据：0x003501e4 —— 低半字：`mov w8, #0x28`（下一条 0x3501E8 `movk w8, #0x2f, lsl #16` 补高半字 ⇒ 0x2F0028），随后 0x3501EC `ldr w8, [x0, x8]` 读该字段
//   证据：0x003501e8 —— 高半字：`movk w8, #0x2f, lsl #16` —— 与上一条合成 0x2F0028
//   证据：0x003501f0 —— 取值锚点：`and w8, w8, #0xfffffffd`（清掉 bit1）+ 0x3501F4 `cmp w8, #0x1` + `cset w0, eq` ⇒ 『难度是 0 或 1 且等于 1 ⇒ 困难』，与 `eDifficulty` 的 NORMAL=0/HARD=1 逐值吻合；同一片区的 `Game::IsGreedMode` 用 `and #0xfffffffe; cmp #2`，两条互为印证
//   证据：0x0034e538 —— 第二处独立锚点（低半字）：`mov w8, #0x28` + 0x34E53C `movk w8, #0x2f, lsl #16` = 0x2F0028；0x34E544 `add x10, x0, x8` 之后 0x34E56C `str w4, [x10]` 写的是**第 4 个形参**，签名里第 4 个参数正是 `eDifficulty`
//   证据：0x0034e53c —— 同上（高半字 `movk w8, #0x2f, lsl #16`）
inline constexpr std::uintptr_t kGameDifficultyOffset = 0x2F0028;
inline constexpr std::uintptr_t kGameDifficultyWidth = 4;

// 屏幕震动的剩余帧数：`Game::ShakeScreen(int)` 把它设成传入的帧数，`Game::Update` 每帧 −1，减到 0 的那一帧把 `ScreenShakeOffset`（本表下一行）复位成零向量。candidate：命名靠引擎自己的符号名 `Game::ShakeScreen` 与这段行为，拿不出取值常量（candidate）
//   证据：0x00355bc0 —— 低半字：`mov w8, #0xf9ac` + 0x355BC4 `movk w8, #0x24, lsl #16` = 0x24F9AC；0x355BD0 `str w1, [x0, x8]` 把**第 1 个形参**（震动帧数）写进这一格
//   证据：0x00355bc4 —— 高半字：`movk w8, #0x24, lsl #16` —— 与上一条合成 0x24F9AC
//   证据：0x003518ec —— `ldr w8, [x24, #0x14]`，其中 x24 = `Game+0x24F998`（合成见 0x3518B0 那条）⇒ 0x24F998 + 0x14 = **0x24F9AC**；随后 0x3518F4 `subs w8, w8, #0x1`、0x3518FC `str w8, [x24, #0x14]` 每帧 −1
inline constexpr std::uintptr_t kGameShakeTimerOffset = 0x24F9AC;
inline constexpr std::uintptr_t kGameShakeTimerWidth = 4;

// 屏幕震动偏移（PC 的 `game.ScreenShakeOffset`，Vector2 两个 float；与既有结构名 `kGameToScreenAdjustOffset` 是**同一个**字段，不要再登记第二个偏移）。candidate：命名靠引擎自己的用法（世界坐标转屏幕坐标时加它、震动结束时复位成 `Vector2::Zero`），拿不出取值常量（candidate）
//   证据：0x0035190c —— 低半字：`mov w8, #0xf9b0` + 0x351910 `movk w8, #0x24, lsl #16` = 0x24F9B0；0x351914 `add x0, x19, x8` 后 0x351918 `bl 0x66ff80` = `KAGE::Math::Vector2::operator=`，第 2 个实参来自重定位槽 0xAAC660 = `_ZN4KAGE4Math7Vector24ZeroE` ⇒ 震动帧数归零那一帧把它设成零向量（分支条件见 0x351900 `b.ne`）
//   证据：0x00351910 —— 高半字：`movk w8, #0x24, lsl #16` —— 与上一条合成 0x24F9B0
//   证据：0x0048939c —— 第二处：同一合成形态（0x4893A0 `movk w9, #0x24, lsl #16`），0x4893A4 `add x1, x8, x9` 把 **`Game+0x24F9B0` 的地址**交给 `Vector2::operator+`（0x4893AC）—— 世界坐标转屏幕坐标时先加房间滚动偏移、再加它
//   证据：0x00348db8 —— 第三处：渲染层把该字段的地址交出去（0x348DC0 `add x0, x8, x9`）
//   证据：0x00033c7c —— 第四处：相机震动分支生成 `RandomUnitVector` 后写进它（0x33C84 `add x0, x8, x9` + 0x33C90 `bl` `Vector2::operator=`）
//   证据：0x00034168 —— 第五处：`update_drag2` 同样把结果写进它（0x34170 `add x0, x8, x9`）
inline constexpr std::uintptr_t kGameScreenShakeOffsetOffset = 0x24F9B0;
inline constexpr std::uintptr_t kGameScreenShakeOffsetWidth = 8;

// 模块里 `g_Manager` 的 GOT 槽（0xAAC648 = 页基址 0xAAC000 + 0x648）。同样要解两层：`Manager* = *(u64*)(*(u64*)(base + 0xAAC648))`；`ItemConfig` 等子系统是**内嵌**在 `Manager` 里的（取地址相加，不是解指针）。candidate：命名来自 NRO 重定位表（槽 ↦ `_ZN15IsaacRepentance9g_ManagerE`），页基址一半工具核不到（candidate）
//   证据：0x003c0d74 —— 本行的 offset = 0x3C0D70 `adrp x8, 0xaac000` + 这条 `ldr x8, [x8, #0x648]` 的立即数 0x648 ⇒ 0xAAC648；0x3C0D78 再解一次得 `Manager*`，随后 `add x8, x8, #0x36538`（0x3C0D7C/0x3C0D80 合成）就是内嵌的 `ItemConfig`。带注解反汇编里该槽显示为 `; _ZN15IsaacRepentance9g_ManagerE`
//   证据：0x0034e578 —— 第二处：`adrp x8, 0xaac000`（0x34E574）+ 本行这条装载 —— 开局时经 `g_Manager` 取管理器
//   证据：0x00355bd8 —— 第三处：`adrp x8, 0xaac000`（0x355BD4）+ 本行这条装载（随后按 `Manager` 的选项字节取音效设置）
inline constexpr std::uintptr_t kGameManagerGlobalSlotOffset = 0xAAC648;
inline constexpr std::uintptr_t kGameManagerGlobalSlotWidth = 8;

// 模块里 `g_Game` 的 GOT 槽（0xAAC698 = 页基址 0xAAC000 + 0x698）。⚠️ 槽里存的是**指针变量**：`Game* = *(u64*)(base + 0xAAC698)`，要解两层才到 `Game*`（`Game`/`Level` 是这个对象的起始处）。candidate：命名来自 NRO 自己的重定位表，但页基址那一半工具核不到（见表头 C 形态）（candidate）
//   证据：0x00470b18 —— 本行的 offset = 同函数上一条 0x470B14 `adrp x8, 0xaac000`（页基址）+ 这条 `ldr x8, [x8, #0x698]` 的立即数 0x698 ⇒ 0xAAC698；紧随 0x470B1C 再 `ldr x8, [x8]` 一次才拿到 `Game*` ⇒ 槽里是指针变量。带注解反汇编里该槽显示为 `; _ZN15IsaacRepentance6g_GameE`
//   证据：0x0003ef34 —— 第二处独立使用：`adrp x8, 0xaac000`（0x3EF30）+ 本行这条 `ldr x8, [x8, #0x698]` + `ldr x8, [x8]` —— 同一槽、同样的两级解引用
//   证据：0x00348db0 —— 第三处：渲染层同样经这个槽取 `Game*`（0x348DB4 再解一层），随后用它加上 Game 的屏幕震动偏移
inline constexpr std::uintptr_t kGameOwnerGlobalSlotOffset = 0xAAC698;
inline constexpr std::uintptr_t kGameOwnerGlobalSlotWidth = 8;

// 对外 API 只允许读这些字段（`confidence == confirmed`）。
// 当前可用：Challenge、Difficulty、TimeCounter、PlayerArrayBegin、PlayerArrayEnd、VictoryLap、SeedsObject、SeedsStartSeed、SeedsCustomRunFlag、PreviousRoomIndex、LastBossRoomListIndex、TargetDarkness、DarknessTimeout

} // namespace isaac::runtime::layout
