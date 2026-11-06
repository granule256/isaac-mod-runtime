#pragma once


#include <array>
#include <cstddef>
#include <cstdint>

// 2026-10-09 离线取证：Entity_Player::InitPlayerSkin @0x27AAAC 的 0x27AAE4..0x27AAF0
// 以 Manager+0x36758 取得 EntityConfig。EntityConfig::GetPlayer @0x700CC 的
// 0x700D0 从 +0x18/+0x20 读 vector begin/end；0x700F0..0x700F4 按编号乘 0x178。
// LoadPlayers @0x6DC54 写 name 到 Player+0x08（既有皮肤链分析 §3.1）。
inline constexpr uintptr_t kEntityConfigPlayerArrayBeginOffset = 0x18;
inline constexpr uintptr_t kEntityConfigPlayerArrayEndOffset = 0x20;
inline constexpr uintptr_t kEntityConfigPlayerStride = 0x178;
inline constexpr uintptr_t kEntityConfigPlayerNameOffset = 0x08;


using u8 = std::uint8_t;

// 2026-10-09：实体碰撞与NPC渲染。碰撞bool返回值由Entity::handle_collisions
// @0x632b8/0x632d4合并，1跳过collide_capsules物理分离，0保留物理碰撞。
inline constexpr uintptr_t kEntityFamiliarHandleCollisionOffset = 0xD1C94;
inline constexpr std::array<u8, 16> kEntityFamiliarHandleCollisionExpectedBytes = {
    0xEA, 0x0F, 0x19, 0xFC, 0xE9, 0xA3, 0x00, 0x6D, 0xFC, 0x17, 0x00, 0xF9, 0xFD, 0xFB, 0x01, 0xA9
};
inline constexpr uintptr_t kEntityNpcHandleCollisionOffset = 0x11C234;
inline constexpr std::array<u8, 16> kEntityNpcHandleCollisionExpectedBytes = {
    0xFF, 0x43, 0x07, 0xD1, 0xE9, 0x23, 0x16, 0x6D, 0xFD, 0x7B, 0x17, 0xA9, 0xFD, 0xC3, 0x05, 0x91
};
inline constexpr uintptr_t kEntityPlayerHandleCollisionOffset = 0x2DB4A8;
inline constexpr std::array<u8, 16> kEntityPlayerHandleCollisionExpectedBytes = {
    0xFF, 0xC3, 0x03, 0xD1, 0xE9, 0x23, 0x09, 0x6D, 0xFD, 0x7B, 0x0A, 0xA9, 0xFD, 0x83, 0x02, 0x91
};
inline constexpr uintptr_t kEntityTearHandleCollisionOffset = 0x33D920;
inline constexpr std::array<u8, 16> kEntityTearHandleCollisionExpectedBytes = {
    0xFF, 0xC3, 0x06, 0xD1, 0xED, 0x93, 0x00, 0xFD, 0xEB, 0x2B, 0x13, 0x6D, 0xE9, 0x23, 0x14, 0x6D
};
inline constexpr uintptr_t kEntityProjectileHandleCollisionOffset = 0x327B04;
inline constexpr std::array<u8, 16> kEntityProjectileHandleCollisionExpectedBytes = {
    0xFF, 0x43, 0x03, 0xD1, 0xE9, 0x23, 0x06, 0x6D, 0xFD, 0x7B, 0x07, 0xA9, 0xFD, 0xC3, 0x01, 0x91
};
inline constexpr uintptr_t kEntityKnifeHandleCollisionOffset = 0xF2748;
inline constexpr std::array<u8, 16> kEntityKnifeHandleCollisionExpectedBytes = {
    0xFF, 0x03, 0x04, 0xD1, 0xFD, 0x7B, 0x0B, 0xA9, 0xFD, 0xC3, 0x02, 0x91, 0xF9, 0x63, 0x00, 0xF9
};
inline constexpr uintptr_t kEntityBombHandleCollisionOffset = 0x7EEDC;
inline constexpr std::array<u8, 16> kEntityBombHandleCollisionExpectedBytes = {
    0xFF, 0x03, 0x03, 0xD1, 0xE9, 0x23, 0x07, 0x6D, 0xFD, 0x7B, 0x08, 0xA9, 0xFD, 0x03, 0x02, 0x91
};
inline constexpr uintptr_t kEntityNpcRenderOffset = 0x120F50;
inline constexpr std::array<u8, 16> kEntityNpcRenderExpectedBytes = {
    0xFF, 0x83, 0x06, 0xD1, 0xEF, 0x3B, 0x10, 0x6D, 0xED, 0x33, 0x11, 0x6D, 0xEB, 0x2B, 0x12, 0x6D
};



using u64 = std::uint64_t;

inline constexpr u64 kTargetTitleId = 0x010021C000B6A000ULL;
inline constexpr uintptr_t kGameOwnerGlobalSlotOffset = 0xAAC698;
// 446：PC控制台rewind恢复快照后请求重载，Switch同名引擎入口均存在。
inline constexpr uintptr_t kGameRestoreGlowingHourGlassStateOffset = 0x35C41C;
inline constexpr std::array<u8, 16> kGameRestoreGlowingHourGlassStateExpectedBytes = {
    0xFF, 0xC3, 0x02, 0xD1, 0xFD, 0x7B, 0x05, 0xA9,
    0xFD, 0x43, 0x01, 0x91, 0xFC, 0x6F, 0x06, 0xA9};
inline constexpr uintptr_t kManagerConsoleRestartGameOffset = 0x3FA458;
inline constexpr std::array<u8, 16> kManagerConsoleRestartGameExpectedBytes = {
    0xFF, 0xC3, 0x02, 0xD1, 0xFD, 0x7B, 0x07, 0xA9,
    0xFD, 0xC3, 0x01, 0x91, 0xF7, 0x43, 0x00, 0xF9};
inline constexpr uintptr_t kConsoleSeedsAssignOffset = 0x49CD0C;
inline constexpr std::array<u8, 16> kConsoleSeedsAssignExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA};
// Manager::RestartGame @3FA4B4构造种子目标地址；execute_start_game
// @3F9248读+1并调用StartFromSavedState，@3F91B4读+1A8作为Exit(bool)参数。
inline constexpr uintptr_t kManagerConsoleRestartSeedsOffset = 0x1D7318;
inline constexpr uintptr_t kManagerConsoleLoadSavedOffset = 0x1D7309;
inline constexpr uintptr_t kManagerConsoleSaveOnRestartOffset = 0x1D74B0;
// PC rewind最后一次性跳过淡入等待。Fadein和Update均消费该u8，后者自行清零。
// 证据：docs/rewind与goto恢复研究-20261019.md；不是旧候选0x2F005C。
inline constexpr uintptr_t kGameInstantFadeOffset = 0x2F0058;
inline constexpr uintptr_t kGameInstantFadeUpdateLayoutOffset = 0x351F44;
inline constexpr std::array<u8,16> kGameInstantFadeUpdateLayoutExpectedBytes = {
    0x56,0xF3,0x40,0x39,0x96,0x01,0x00,0x35,
    0x05,0x7A,0x0C,0x94,0xC8,0x3A,0x00,0xF0};

// --- 玩家 / ItemConfig 的引擎偏移（2026-09-12 反汇编定位，真机探针待验证）------------
//
// 背景：这个 NRO 里**没有 Lua VM、也没有 `Isaac.*` 的绑定函数**（全镜像搜 `luaL_newstate`/
// `lua_State`/`main.lua`/`isaac_mods` 等全部 0 命中），所以 Runtime 必须自己封装引擎原语。
// 下面每一项都是"已交叉验证的静态结论"，但**尚未上真机**：按项目探针纪律，实现前要用一次
// `svcBreak` 把指针与字段打出来确认（配方见 `docs/问题与解决记录.md` 的批次 2 条目）。
//
// 玩家链路：`Game* = *(u64*)(base + kGameOwnerGlobalSlotOffset)`（是**指针变量**，不是对象），
// 玩家数组是 `Game + kGamePlayerArrayOffset` 处的 `std::vector<Entity_Player*>`（步长 8），
// `players[0]` 即主玩家；引擎里**没有** `PlayerManager::GetPlayer(int)`，必须自己索引 + 越界检查。
inline constexpr uintptr_t kGameManagerGlobalSlotOffset = 0xAAC648;       // g_Manager 的 GOT 槽
// 2026-10-13真实保存槽：Manager::SetSaveSlot 0x3FAA28，输入w1既用于
// %srep_gamedata%d.dat（0x3FAA74..88），也在0x3FAADC写到Manager+0x10；
// Menu_Save::refresh_slot 0x413DE0从相同字段读旧槽，再调用SetSaveSlot恢复。
inline constexpr uintptr_t kManagerSaveSlotFieldOffset = 0x10;
inline constexpr uintptr_t kManagerSetSaveSlotOffset = 0x3FAA28;
inline constexpr std::array<u8, 16> kManagerSetSaveSlotExpectedBytes = {
    0xFD,0x7B,0xBD,0xA9,0xFC,0x57,0x01,0xA9,0xFD,0x03,0x00,0x91,0xF4,0x4F,0x02,0xA9};
inline constexpr uintptr_t kManagerSetSaveSlotStoreOffset = 0x3FAADC;
inline constexpr std::array<u8, 4> kManagerSetSaveSlotStoreExpectedBytes = {0x93,0x12,0x00,0xB9};
inline constexpr uintptr_t kGamePlayerManagerOffset = 0x25C40;            // Game::PlayerManager 内嵌对象
inline constexpr uintptr_t kGamePlayerArrayBeginOffset = 0x25C50;         // vector<Entity_Player*> begin
inline constexpr uintptr_t kGamePlayerArrayEndOffset = 0x25C58;           //   … end
inline constexpr uintptr_t kGamePlayerArrayCapacityOffset = 0x25C60;      //   … capacity
// 玩家数量上限：只用于"偏移猜错时不要把一整段垃圾当成向量"这层保险；真正的判据是读者的
// vptr 校验（`Isaac.GetPlayer`）或这条向量自身的形状（`Game:GetNumPlayers`）。
inline constexpr std::size_t kEnginePlayerMaximumCount = 32;
inline constexpr uintptr_t kGameRoomPointerOffset = 0x21550;              // Game → Room*
// `Level` 就是 `Game`（同一地址），"当前房间"是同一段里的两个 u32：
// 证据是固定 NRO 里 `Level::GetCurrentRoomDesc @ 0x3DC684` 的反汇编 —— 它把
// `Level + 0x21558` 读进 `w1`、`Level + 0x21560` 读进 `w2`，随后尾跳到唯一的
// `Level::GetRoomByIdx(int, int)` PLT thunk，即这两个字段就是"当前 descriptor 的解析参数对"。
// 见 `docs/PC-Mod-兼容矩阵.md`（Stage104 条目）与 `docs/会话交接-2026-08-26.md`。
inline constexpr uintptr_t kLevelCurrentRoomIndexOffset = 0x21558;        // 当前房间在描述符表里的索引
// 445：原版Level::ChangeRoom @0x3D9E9C存get_target_slot的返回值；
// Entity_Player::GetEnterPosition @0x2F3D78读同格，-1表示没有进入门，
// @0x2F3DDC把它交给GetDoorSlotPosition。门动画@0x384248也读同格。
// Level::load_room @0x3D7F6C的原生日志明确称它为“door from where to enter”。
inline constexpr uintptr_t kLevelEnterDoorOffset = 0x21570;  // i32，实际进入的DoorSlot
// `Level + 0x00` = 关卡（`eLevelStage`）、`Level + 0x04` = **关卡类型**（`eStageType`）。
// 证据（2026-09-16，`Level::SetStage(eLevelStage, eStageType) @ 0x3E420C` 的收尾两条）：
//   `stp w21, w20, [x19]` —— 把第 1 个参数（关卡）与第 2 个参数（类型）**连着**写进 `this+0x00`/`+0x04`；
// 另有两条交叉验证：
//   * `Level::GetAbsoluteStage @ 0x3E7F3C` 只读 `*(u32*)this`（就是关卡，贪婪模式再做一次映射）；
//   * 同函数里对 `+0x04` 做 `and w8, w8, #0xfffffffe; cmp w8, #0x4` —— 清掉 bit0 后与 4 比较，
//     正好把 `STAGETYPE_REPENTANCE(4)` 与 `STAGETYPE_REPENTANCE_B(5)` 归成一类
//     ⇒ 该字里存的就是**枚举原值**（4/5 互为"忏悔时代关卡"）。
inline constexpr uintptr_t kLevelStageOffset = 0x00;
inline constexpr uintptr_t kLevelStageTypeOffset = 0x04;
//: `StageType.STAGETYPE_ORIGINAL`（PC 枚举 0）：`Level:IsAltStage()` 的判据是"类型不是它"。
inline constexpr std::uint32_t kStageTypeOriginal = 0;
//: `TruppeStageType`：`STAGETYPE_REPENTANCE(4)` / `STAGETYPE_REPENTANCE_B(5)` 清掉 bit0 都是 4。
inline constexpr std::uint32_t kStageTypeRepentanceEraMasked = 0x4;
//: 幕府/革赫那第二层（`STAGE4_3 == 9`）—— PC 文档说 `IsPreAscent()` 指的是"通往升华的那一层"。
inline constexpr std::uint32_t kLevelStagePreAscent = 9;
inline constexpr uintptr_t kLevelCurrentRoomDimensionOffset = 0x21560;    //   … 对应的维度参数

//: 引擎自己的 `Level::GetRoomByIdx(int, int) const`（**描述符解析的唯一权威**）。
//:
//: 为什么改成直接调它（批次 077）：我们手写的那套"扫描 `+0x00 == 下标` + 引擎映射表 + 足迹校验"
//: 在真机上解析率很低（一次会话 8844 次解析里 5162 次给了空句柄），而且**从某些房间走进两格房时
//: 解析出来的不是那个房间** —— 于是 GoodTrip 的地图条件 `grid_room[crd.SafeGridIndex] ~= nil`
//: 为假、整张地图不画（`rules.lua` 的 `check_teleble`），而错误历史干干净净（条件为假，不是异常）。
//: 用户实测的判据非常干净：**从银色道具房 / 贪婪最下方那间走进两格房必现，传送进去则不现**
//: —— 两者唯一的差别就是"进房间时踩在哪一格"（`Level + 0x21558`）。
//:
//: 引擎这条函数就是 PC 的 Lua 绑定走的同一条路（`Level::GetCurrentRoomDesc @ 0x3DC684` 内部
//: 就是读 `+0x21558`/`+0x21560` 后转调它），所以它的答案**按定义**就是"PC 会得到的答案"；
//: 无效格子它返回自己的静态空描述符（**对象，不是 nil**），这也正是 PC 的语义。
//:
//: **入口**（固定 NRO，`python3 tools/nro_disasm.py 0x3dc3b0 0xd0`）：
//:   `d10103ff sub sp, sp, #0x40`（**真正的函数开头**；0x3DC5B0 是它的中段，不能当入口调 ——
//:    那一段用 `w10` 当维度，而 `w10` 是**函数前半段**才赋值的）
//:   `5282a209 mov w9,#0x1510 ; movk w9,#0x2` → `x11 = Level + 0x21510`（描述符区基址）
//:   `36f80042 tbz w2,#31` + `b9405162 ldr w2,[x11,#0x50]` ⇒ **维度传 -1 = 用当前维度**
//:    `7100085f cmp w2,#0x2 ; b.hi` ⇒ 维度 > 2 直接给空描述符
//:   `3101943f cmn w1,#0x65` / `3101903f cmn w1,#0x64` ⇒ 索引 **-101 / -100** 两个特殊值
//:   `52803f49 mov w9,#0x1fa(506) ; 4b010129 sub w9,w9,w1` ⇒ **负数索引**映射到"尾部槽位"
//:    （`槽号 = 506 - 索引`）—— 也就是说 PC 的 `-1`/`-2` 语义就在这条函数里，我们不必再猜
//:   `1b090549 madd w9, w10, w9(169), w1` + `b8aa6929 ldrsw x9,[x9,#0x2d18]` ⇒ 映射表取**有符号**槽号
//:   `9a88b000 csel x0, x0, x8, lt` ⇒ 槽号 < 0 时返回**静态空描述符**（`0xabc000+0xa10`，是对象不是 nil）
//:   `d65f03c0 ret`（函数尾在 0x3DC680，紧挨着 `Level::GetCurrentRoomDesc @ 0x3DC684` ⇒ 长度自洽）
inline constexpr uintptr_t kLevelGetRoomByIdxOffset = 0x3DC3B0;
//: 入口 4 字节指纹（同一份 NRO 的第一条指令 `sub sp, sp, #0x40`）。
inline constexpr std::uint32_t kLevelGetRoomByIdxEntryWord = 0xD10103FFu;
// `Room:IsMirrorWorld()` 的判据：**当前房间的维度 == 1**。
//
// 证据（两条独立）：
//   ① `Level + 0x21560` 就是"当前 descriptor 的维度参数" —— `Level::GetCurrentRoomDesc @ 0x3DC684`
//      把它当 `Level::GetRoomByIdx(index, dimension)` 的**第 2 个实参**（见本文件
//      `kLevelCurrentRoomIndexOffset` 那一段的反汇编记录，那条偏移本来就是为此取的）；
//   ② PC 文档快照 `RoomDescriptor.md` 写明维度枚举的含义：
//      `0 = main dimension`、**`1 = secondary dimension, used by downpour mirror dimension
//      and mines escape sequence`**、`2 = death certificate dimension`。
//      而 PC 对 `Room:IsMirrorWorld()` 的说明是"Returns true if the player is inside the
//      mirror dimension"（`Room.md`）⇒ 两者合起来就是"当前维度 == 1"。
//
// ⚠️ **已知过宽（写在这里免得以后当 bug 查）**：文档同上写着维度 1 也被**矿坑逃脱序列**用
// ⇒ 那一幕这条 API 也会答 true。PC 的说明只到"玩家在镜像维度里"这一层，无法再细分；
// 要细分得另找引擎判据（层号/关卡类型），目前没有证据。
inline constexpr std::uint32_t kMirrorWorldDimension = 1;
inline constexpr uintptr_t kGameHudOffset = 0xE8468;                      // Game → HUD

// `Manager::GetLanguageCode() const`：读取 `Manager + 0x36CC0` 的 StringTable 当前语言索引，
// 再映射为两字符语言代码。反汇编见 `tools/nro_disasm.py 0x3F8AFC`。
inline constexpr uintptr_t kManagerGetLanguageCodeOffset = 0x3F8AFC;
inline constexpr std::array<u8, 16> kManagerGetLanguageCodeExpectedBytes = {
    0xFD, 0x7B, 0xBF, 0xA9, 0xFD, 0x03, 0x00, 0x91,
    0x08, 0x98, 0x8D, 0x52, 0x68, 0x00, 0xA0, 0x72,
};

// `Game + 0x24F99C`：**本局的游戏帧计数（u32）**，即 PC 的 `Game:GetFrameCount()`。
// 证据（同一个 build `91C73FDD…`，`tools/nro_disasm.py`）：
//   * **每帧 +1**：`Game::Update`（`0x351884`）在 `0x3518B0` 先把 `0x24F998` 装进 `x24`
//     （`mov w8,#0xf998; movk w8,#0x24,lsl#16; add x24,x0,x8`），随后 `0x352114`–`0x352120`
//     `ldp w8,w9,[x24,#0x4]; add w8,w8,#1; add w9,w9,#1; stp w8,w9,[x24,#0x4]`
//     —— 一次更新把 `+0x24F99C` 与 `+0x24F9A0` 两个计数器各加一（后者是同一步里的第二个计数）。
//   * **构造时清零**：`Game::init_vars`（`0x34DA80`）`0x34DAC4`–`0x34DAC8`
//     `add x9,x0,x9`（x9 = `0x24F998`）后 `stur xzr,[x9,#0x4]` → `+0x24F99C` 归零。
//   * **引擎自己就是这么用的**：`Entity::GetFrameCount()`（`0x5A210`）与 `Room::GetFrameCount()`
//     （`0x470B0C`）都是 `ldr w8,[Game+0x24F99C]; sub w0,w8,[this+各自的起始帧]`；
//     全镜像共 155 处引用该偏移，`Game::SaveState`（`0x3505A4`）也把它抄进 `GameState`。
// 语义提示：计数器在 `Game::Update` 里前进，所以**暂停期间不增长**，与 PC 文档
// （"Returns the number of frames the gameplay is actively running. Pauses are therefore not
// included!"）一致；但**它是否随"新开一局"归零未验证**（唯一找到的写入点只有 `init_vars`），
// 所以 EID 的 `game:GetFrameCount() < 10*30`（开局警告）不保证能命中。
inline constexpr uintptr_t kGameFrameCountOffset = 0x24F99C;

// --- `Game` 的四个 Lua 字段（2026-09-16 静态取证；NRO 文件偏移 = 运行时模块偏移）------------
//
// 四个都落在已知簇里：`Game+0x24F998` 起是一组计数器/计时器（`FrameCount` 在 0x24F99C），
// `Game+0x26FA88` 起是挑战状态，`Game+0x2F0028` 是难度。每条都有**两处不同函数**的指令证据。

// `game.Challenge`：`eChallenge` 枚举原值（int32，4 字节）。
//   * `Game::Start(ePlayerType, eChallenge, Seeds, eDifficulty) @ 0x34E570`：`str w2,[x21]`，
//     其中 x21 = this+0x26FA88（`0x34E548 mov w8,#0xfa88` / `movk w8,#0x26,lsl#16` / `add x21,x0,x8`），
//     w2 就是第 2 个参数 eChallenge；
//   * `Game::GetChallengeParams() const @ 0x34EA9C`：`ldr w1,[x8]`（x8 = this+0x26FA88）后尾跳到
//     `Manager::GetChallengeParams(eChallenge)`；
//   * 旁证：`Game::Init @ 0x34DD7C` 归零、`Game::SaveState @ 0x350678` / `RestoreState @ 0x34F10C`
//     在 GameState+0x00 来回抄。
inline constexpr uintptr_t kGameChallengeOffset = 0x26FA88;

// --- `Game:GetVictoryLap()` / `Game:GetSeeds()` / `Seeds:GetStartSeed()` / `Seeds:IsCustomRun()`
//     （批次 195，2026-09-29；证据规格 `analysis/api-restore-game/spec.json`，本条全部是**确证**）----
//
// ★ 三个偏移都来自"写它的就是同名函数"这条最强形态，另有 3~5 个**独立读者**：
//
// `kGameVictoryLapOffset`（int32）—— PC 的 `Game:GetVictoryLap()`（契约页只有签名：
// `tools/pc_contract_docs/Game.md:389`；语义由配对的 `Game.md:429 NextVictoryLap()` 与消费者
// EID `features/eid_api.lua:2360` 的 `game:GetVictoryLap() > 0` 定死）。主锚点
// `Game::NextVictoryLap() @ 0x34FE00`：`0x34FE58 mov w8,#0xfd50` / `0x34FE5C movk w8,#0x26,lsl#16`
// / `0x34FE60 ldr w9,[x19,x8]` / `0x34FE64 add w10,w9,#1` / `0x34FE68 str w10,[x19,x8]` ⇒ 这一格 +1；
// 首次进圈（原值 0）顺带把难度（`Game+0x2F0028`）置 1(HARD)。五个独立读者都在 `cmp` 小整数域里：
//   `Entity_Player::TriggerPreVictoryLap(int) @ 0x2FC528`（`0x2FC564 ldr w8,[x9,x8]` → `cmp w8,#2`）、
//   `Level::Init @ 0x3E0688`（`0x3E0D20` → `cmp w9,#3`）、
//   `HUD::Render @ 0x3AD730`（`0x3AD748` → `cmp w8,#1` → `b.lt`，≥1 才画跑圈标记）、
//   `Level::place_rooms @ 0x3D14B0`（`0x3D1AB4` → `cmp w8,#2` → `b.gt` 跳过成就解锁）、
//   `Room::SpawnClearAward @ 0x455810` / `Entity_Player::TakeDamage`（`cmp #1` / `cmp #0`）。
// ⚠️ `Game+0x26FD58` 起是内嵌的 `GenericPrompt`（`Game::ShowVictoryLapPrompt @ 0x34D55C` 做
//    `add x0,x0,#0x26FD58` 再调 `GenericPrompt::Show`）——**不是**计数器的一部分。
inline constexpr uintptr_t kGameVictoryLapOffset = 0x26FD50;

// `kGameSeedsObjectOffset` = `Seeds` 对象**内嵌**在 `Game` 里的基址（不是指针，取地址相加）。
// 五处独立站点都用同一个 `add xN, xGame, #0x25D40`：
//   * `Game::Start @ 0x34E5DC`（`add x22, x20, #0x25D40` → `Seeds::operator=`）；
//   * `Game::SaveState @ 0x350630`（→ `Seeds::Seeds(const&)` → `GameState+0x28840`）；
//   * `Game::RestoreState @ 0x34F0E8`（→ `Seeds::operator=`）；
//   * `Game::StartDailyChallenge @ 0x34EB6C`（→ `Seeds::Reset`）；
//   * `Console::RunCommand @ 0x40EF8 / 0x4203C`（控制台 `seed <串>`）。
inline constexpr uintptr_t kGameSeedsObjectOffset = 0x25D40;

// `kSeedsStartSeedOffset`：`Seeds + 0x4`（**相对 Seeds 对象**，所以对外读的是 `Game+0x25D44`）。
// 唯一写它的是 `Seeds::SetStartSeed(unsigned) @ 0x4A1114`：`0x4A1124 str w1,[x0,#0x4]`（w1 = 形参），
// 且 `0x4A1128 cbnz w1` 为 0 时取 `RandomU32() ?: 1`（与 PC 文档 `Seeds.md:79` 的
// "1 与 2^32-1 之间"逐字吻合）。第二处独立读到它：`Seeds::Restart(eChallenge) @ 0x4A120C`
// （`0x4A1220 ldr w1,[x0,#0x4]`，带自定义种子时重开沿用同一颗）；第三处：`Game::NextVictoryLap`
// （`0x34FEF0 ldr w1,[x24,#0xf4]`，x24 = `Game+0x25C50` ⇒ 0x25D44）把它喂给 `SetStartSeed`。
// Lua 返回值保留完整 uint32 值域（1..2^32-1）；不能把最高位当符号位。
inline constexpr uintptr_t kSeedsStartSeedOffset = 0x4;

// `kSeedsCustomRunFlagOffset`：`Seeds + 0x0` 那**一个字节** = "本局用的是玩家自选种子"。
// 三处写：`Console::RunCommand`（`seed <串>`：`0x42040 mov w8,#1` → `0x42044 strb w8,[x1]`，x1 就是
// `Game+0x25D40`，随后 `Manager::RestartGame`）、`Menu_Character::ProcessSeedEntry @ 0x4053E0`
// （`0x40569C strb w8,[x9,#0x600]`，菜单挂起的那份 Seeds）、`Game::StartDebug @ 0x34FAC4`
// （`0x34FB58 strb w10,[x23]`）；三处读：`Seeds::AchievementUnlocksDisallowed() @ 0x49ED6C`
// （`ldrb w8,[x0]` 非 0 ⇒ 直接 return 1"本局禁成就"）、`Seeds::Restart`（非 0 ⇒ 沿用原种子）、
// 以及本项目的 `Seeds:IsCustomRun()`。清零：`Seeds::Seeds()` / `Seeds::Reset()` 的 `strb wzr`。
// ★ **只读这一个字节**：PC 文档 `Seeds.md:112` 写的是"挑战局**或**带种子的局"，
//   而"挑战局会不会也写这一字节"静态上查不到（写它的只有上面三处）⇒ 规格里 OR 上
//   `Game+0x26FA88`（eChallenge）的那一半是**推断**，**本轮不实现**（等真机三点读数钉死/推翻，
//   判据写在 `analysis/api-restore-game/README.md` §三.2）。
inline constexpr uintptr_t kSeedsCustomRunFlagOffset = 0x00;

// --- 批次 306（2026-10-03）：`Seeds` 的**两个成员**（`GetNextSeed` / `GetStageSeed`）-----------
//
// ★★★ **先看 `Seeds::Seeds()`（构造函数）@ `0x49CBD4`，它把布局钉死了**：
//     0049cbe0  stp  x20, x19, [sp, #0x20]
//     0049cbe8  add  x0, x0, #0x8            ; ★ this + 0x8
//     0049cbec  bl   …RNG…C1Ev               ; ★ `RNG::RNG()` —— `Seeds + 0x8` 是**一个内嵌的 RNG**
//     0049cbf8  str  xzr, [x19, #0x68]       ; set<eSeedEffect> 的 size
//     0049cc00  str  x21, [x20, #0x58]!      ; （x21 = this）set 的 end 结点指回自己
//     0049cc0c  str  wzr, [x19, #0x4]        ; 起始种子 = 0（既有 `kSeedsStartSeedOffset`）
//     0049cc10  strb wzr, [x19]              ; 自选种子标志（既有 `kSeedsCustomRunFlagOffset`）
//   ⇒ 布局：`+0x00` u8、`+0x04` u32、**`+0x08` 内嵌 `RNG`（16 字节，`kRngObjectSize`）**、
//     **`+0x18` 起是关卡种子数组**、`+0x58` 起是 `std::set<eSeedEffect>`（`__tree`：end/root/size）。
//
// ★★★ **第二条独立证据（也是"数组在哪"的直接证据）：`Seeds::ForgetStageLevel(eLevelStage) @ 0x4A1228`**
//     004a1238  add  x19, x0, w1, uxtw #2    ; x19 = this + 4*stage
//     004a123c  ldr  w1, [x19, #0x18]        ; ★ 读 this + 0x18 + 4*stage（那就是这个 stage 的种子）
//     004a1240  mov  w2, #0x27               ; 39 = RNG 的移位参数
//     004a1248  bl   …RNG…C1Ejj              ; 在本函数栈上构造 RNG(种子, 39)
//     004a1250  bl   …RNG…4NextEv            ; 取下一个
//     004a1254  str  w0, [x19, #0x18]        ; ★ 写回同一格（"忘掉"= 重新摇一个）
//   ⇒ 数组基址 `Seeds + 0x18`、步长 **4 字节**，与构造函数的 RNG 终点（`0x8+0x10 = 0x18`）**吻合**。
//
// ★★★ **PC 侧同偏移、同步长（免费交叉印证，但数值仍不许平移）**：
//     `Seeds:GetStageSeed @ 0x705F30` = `mov eax, [esi + 4*eax + 0x18]`（`esi` = this，`eax` = stage 实参）
//     —— 基址与步长**逐字相同**；数组之前同样是 `+0x4`（本函数开头 `cmp dword ptr [esi+0x4], 0` 是
//     "本局已开始"的断言）与 `+0x8`（`GetNextSeed` 的状态字）。
//
// ★ **槽位数 16 是"夹"出来的、不是猜的**：`+0x18` 到 `+0x58`（`__tree` 的 end 结点）之间是
//   `0x40 = 64` 字节 = **16 个 u32**。★ PC 那条绑定**没有边界检查**（`stage` 越界就是读飞）⇒
//   我们按 16 个槽降级（**刻意偏离**，与 `BoolBitArrayOfArg` 的越界降级同一口径）。
inline constexpr uintptr_t kSeedsStageSeedArrayOffset = 0x18;
inline constexpr std::size_t kSeedsStageSeedStride = 4;
inline constexpr std::uint32_t kSeedsStageSeedSlotCount = 16;

// `Seeds + 0x8` = **内嵌的 `RNG` 对象**（证据见上：构造函数 `add x0,x0,#8` + `bl RNG::RNG()`）。
// `Seeds:GetNextSeed()` 就是**对它调 `RNG::Next()`**、返回新值。
//
// ★★★ **PC 侧那条绑定把这个调用内联了，指令级逐句对上**（`Seeds:GetNextSeed @ 0x6C4560`）：
//     6c4563  cmp  dword ptr [esi+0x4], 0x0   ; 断言"本局已开始"
//     6c4578  mov  edx, dword ptr [esi+0x8]   ; ★ 状态字 = RNG + 0x0
//     6c4596  mov  ecx, dword ptr [esi+0xc]   ; ★ 移位量 = RNG + 0x4
//     6c459b  shr  eax, cl ; 6c45a0 xor eax, edx
//     6c459d  mov  ecx, dword ptr [esi+0x10]  ; ★ RNG + 0x8
//     6c45a4  shl  edx, cl ; 6c45a9 xor edx, eax
//     6c45a6  mov  ecx, dword ptr [esi+0x14]  ; ★ RNG + 0xc
//     6c45ad  shr  eax, cl ; 6c45af xor eax, edx
//     6c45b1  mov  dword ptr [esi+0x8], eax   ; ★ 写回状态字，并在 eax 里返回
//   而 Switch 侧 `RNG::Next() @ 0x44E464` 是**同一个 xorshift**（只是没内联）：
//     0044e490  ldp  w9, w10, [x19, #0x4] / 0044e4a4  ldr  w9, [x19, #0xc]
//     0044e4b0  str  w0, [x19]                ; 原地写回
//     0044e4bc  ret                           ; 返回值在 w0
//   ⇒ 我们**调引擎自己的 `RNG::Next()`**（`kRngNextOffset`，已有 16 字节指纹 + `RngNextThunk()`
//     那一套），`this` 传 `Seeds + 0x8`。**不自己抄一份 xorshift** —— 两份实现迟早漂。
inline constexpr uintptr_t kSeedsRngOffset = 0x08;

// `game.Difficulty`：`eDifficulty`（0=NORMAL/1=HARD/2=GREED/3=GREEDIER，int32）。
//   * `Game::Start @ 0x34E56C`：`str w4,[x10]`（x10 = this+0x2F0028，w4 = 第 4 个参数 eDifficulty）；
//   * `Game::IsHardMode() const @ 0x3501EC`：`ldr w8,[x0,#0x2F0028]` + `and w8,w8,#0xfffffffd`
//     + `cmp w8,#0x1` + `cset w0,eq`；同址的 `Game::IsGreedMode() @ 0x350208`（**正是本项目已在打补丁
//     的那条函数**）用 `and #0xfffffffe; cmp #2` —— 两条 `and`/`cmp` 与 PC 枚举逐值吻合，互为印证。
inline constexpr uintptr_t kGameDifficultyOffset = 0x2F0028;

// `game.TimeCounter`：**有符号** int32，30 fps 帧钟（PC 文档："same as FrameCounter but can be
// modified, mostly used for timed events"）。
//   * `Game::Update @ 0x352114-0x352120`：`ldp w8,w9,[x24,#0x4]` / `add …,#1` / `add …,#1` /
//     `stp w8,w9,[x24,#0x4]`（x24 = Game+0x24F998）⇒ 每帧与 `FrameCount`(0x24F99C) **一起** +1；
//   * 控制台 `time` 命令 @0x3EF48：`ldrsw x8,[x8,x9]`（x9 = 0x24F9A0）后除以 30 输出秒 ⇒ 有符号；
//   * 旁证：`ScoreSheet::Calculate @ 0x49C504`（`scvtf` + `/30`）、`Minimap::Render @ 0x41E00C`
//     （SPEED 挑战倒计时 `28800 - 它`）、`Room::TrySpawnBossRushDoor @ 0x466B1C`（日志 "Mom clear time"）。
inline constexpr uintptr_t kGameTimeCounterOffset = 0x24F9A0;

// `game.ScreenShakeOffset`：`Vector`（两个 float，8 字节）——**与既有 `kGameToScreenAdjustOffset`
// 是同一个字段**（那条是结构名、这是 PC 名），这里只加别名，**不要**新增第二个偏移。
// 语义证据（2026-09-16 补）：
//   * `Game::Update @ 0x3518EC-0x35191C`：震动帧数 `Game+0x24F9AC` 递减到**恰好 0** 的那一帧，
//     用 `Vector2::operator=` 把它设成 `KAGE::Math::Vector2::Zero`；
//   * `Camera::update_drag2 @ 0x34164` / `update_ultrasmooth @ 0x33C78`：震动分支（读 0x24F9AC 与
//     0x24F99C 生成 `RandomUnitVector`）之后把结果写进它；
//   * `Room::Render @ 0x47FD60`、`FXLayers::render @ 0x348DAC`、`HUD::Render @ 0x3AC814` 把它
//     加进/读进渲染坐标；
//   * 模组侧佐证：EID 的 `eid_api.lua:2207`
//     `room:WorldToScreenPosition(Vector(0,0)) - room:GetRenderScrollOffset() - game.ScreenShakeOffset`
//     —— 减掉的两项正好是本仓库已取证的那两项（Room 的 0x1938 与 Game 的 0x24F9B0）。
inline constexpr uintptr_t kGameScreenShakeOffsetOffset = 0x24F9B0;
// 顺带取证（同一簇，供后续用）：屏幕震动的剩余帧数 —— `Game::ShakeScreen(int) @ 0x355BD0`
// `str w1,[x0,#0x24F9AC]`，`Game::Update @ 0x3518EC` 每帧 -1。
inline constexpr uintptr_t kGameShakeTimerOffset = 0x24F9AC;

// Entity 基类（顺序与 `Entity::Init` 的 `stp w1,w2,[x0,#0x38]; str w3,[x0,#0x40]` 一致）。
// 陷阱：`Entity + 0x3E8` 是**生成种子**而不是 `Index`（236 处引用多为 `ldr w1,[x,#0x3e8]; bl RNG::RNG`）。
inline constexpr uintptr_t kEntityTypeOffset = 0x38;                      // u32，ENTITY_PLAYER == 1
inline constexpr uintptr_t kEntityVariantOffset = 0x3C;                   // u32
inline constexpr uintptr_t kEntitySubTypeOffset = 0x40;                   // u32（玩家时即 PlayerType）
inline constexpr uintptr_t kEntityPositionOffset = 0x310;                 // Vector2（两个 float）
inline constexpr uintptr_t kEntityVelocityOffset = 0x334;                 // Vector2
inline constexpr uintptr_t kEntitySizeOffset = 0x344;                     // float 半径
// `Entity.Parent`（`Entity*`，8 字节，可为 0）—— 多段实体的主段、跟班挂主人、分段子段回指：
//   * 写：`Entity::SetParent @ 0x59164`：`0x5917C add x21,x0,#0x390` + `0x59234 str x19,[x21]`
//     （x19 = 形参 x1；同函数还维护"父+0x3B8 的 std::set<Entity*>"子集合）；
//   * 读：`Entity::GetLastParent @ 0x58BE8`：`ldr x0,[x0,#0x390]` + `cbnz`（沿本字段上溯到顶）；
//   * 读：`Entity::HasCommonParentWithEntity @ 0x58F40/0x58F54`（两条父链各自上溯后比较）；
//   * 空判：`Entity::ClearReferences @ 0x5D410/0x5D418`（`ldr` 后直接 `cbz`）⇒ 合法取值为 0。
inline constexpr uintptr_t kEntityParentOffset = 0x390;
// `Entity.PositionOffset`（`Vector2`，两个 float）—— 引擎把它叠加在 `Position(0x310)` 上算绘制位置：
//   * `Entity::Render @ 0x624FC`：`0x62534 add x0,x19,#0x310` / `0x62538 add x1,x19,#0x320` /
//     `bl Vector2::operator+`；
//   * `Entity_Player::render_player_sprite @ 0x2D9398`：`0x2D9520 ldr x8,[x19,#0x320]`（存栈）→
//     临时置零 → 渲染时用 `Position + 它` → 还原；
//   * 出生清零：`Entity::Init @ 0x598A8`（`add x0,x19,#0x320` + `Vector2::operator=`）。
//   ⚠️ 命名辨析：PC 另有 `SpriteOffset`（也是 Vector）。0x320 与 Position(0x310)、插值旧位置(0x318)
//   连续构造、并被引擎当"位置偏移"用 ⇒ 判为 `PositionOffset`；**不要**拿它当 `SpriteOffset`。
inline constexpr uintptr_t kEntityPositionOffsetOffset = 0x320;          // Vector2（两个 float）
// `Entity.DropSeed` / `Entity:GetDropRNG()` 读的**同一个 16 字节 `RNG` 对象**（`kRngObjectSize`）——
// 本常量就是它的**起始地址**（构造与出生两处具名证据把地址钉死；RNG 的种子 = 对象头 4 字节）：
//   * 实体基类**只有这一个 RNG 成员**，构造函数 `Entity::Entity @ 0x58978` 就在这一格上
//     `add x0,x19,#0x3d8` + `bl RNG::RNG()`（析构 `0x589FC` 同址 `bl RNG::~RNG()`）；
//   * 出生 `Entity::Init @ 0x597E8`：`add x21,x0,#0x3d8` → `0x5980C bl RNG::SetSeed(uint,uint)`
//     （`0x597FC mov w2,#0x1e` = 用途常量 **30**）⇒ 这一格就是那个 RNG 的起点；
//   * `RNG::SetSeed @ 0x44E3C0`：`str w1,[x0]` ⇒ 种子就是该 RNG 对象头 4 字节；
//   * `Room::save_entity @ 0x4550FC`：`ldr w8,[x20,#0x3d8]` → 按 **32 位整数**存进存档
//     （同函数 0x4550F4 存的是 `0x3E8`=InitSeed，与既有常量互证）；
//   * `Room::restore_entity @ 0x4556AC`：`add x0,x19,#0x3d8` + `bl RNG::SetSeed` 回灌。
// ★★ **两条 API 同址、不是两个字段**（批次 316 把命名从"推断"升级成"两平台对上"）：
//   PC 侧 `Entity.DropSeed @ 0x59FD60` = `mov eax,[ecx+0x334]; ret` 与
//   `Entity:GetDropRNG @ 0x412390` = `lea eax,[ecx+0x334]; ret` —— 两条**指着同一格**；
//   Switch 侧同理（构造/出生两处具名函数都拿 `this+0x3d8` 当 `RNG*` 用）。
//   ⇒ 布局表 `tools/layout_tables/entity.json` 的 `DropSeed` 行已由 candidate 升 `confirmed`
//     （补的正是上面 `Entity::Init` 那两条证据，`--verify` 5 条全过）。★ 本批为它新开
//     `FieldKind::RngSnapshot`（读整段 16 字节、压 `kRngMetatable` 句柄）落地 `Entity:GetDropRNG()`。
//   ★ PC `0x334` / Switch `0x3D8`，**数值不许平移**。
//   ⚠️ 这是"种子/状态字"：`RNG::Next @ 0x44E4B0` 会把新状态写回同一个字 ⇒ 取随机数会变。
inline constexpr uintptr_t kEntityDropSeedOffset = 0x3D8;                // uint32（RNG 的种子/状态字）

// `EntityFamiliar.Player`（`Entity_Player*`，8 字节）：
//   * 写：`Entity_Familiar::SetPlayer @ 0xD8C10`：`0xD8C98/0xD8CE8 str x20,[x19,#0x400]`；
//   * 读：`Entity_Familiar::player_can_fire @ 0xC0104`：`ldr x0,[x0,#0x400]` 直接喂
//     `Entity_Player::IsExtraAnimationFinished()`；
//   * 读：`Entity_Familiar::Render @ 0xD1174`：`ldr x0,[x0,#0x400]` → `ldr w8,[x0,#0x1738]`
//     （0x1738 正是已知的 `Entity_Player.PlayerType` ⇒ 证明这一格存的是玩家实体）。
//   ⚠️ 引擎这几处读点都不判空，我们自己读之前必须先判 0。
inline constexpr uintptr_t kEntityFamiliarPlayerOffset = 0x400;          // Entity_Player*
inline constexpr uintptr_t kEntityPlayerIndexOffset = 0x19F0;             // Entity_Player 在 players 里的下标
inline constexpr uintptr_t kEntityPlayerTypeOffset = 0x1738;              // PlayerType（没有 GetPlayerType 方法）
// 玩家当前名字（24 字节 libc++ 字符串），不是 PlayerType 对应的配置名。
// PC GetName@0x7A7FA0 返回实体 +0x1310；Switch InitPreLevelInitStats@0x27B1F8、
// InitPlayerSkin@0x27ADA4 与 RestoreGameState@0x2C4018 均写实体 +0x1740。
inline constexpr uintptr_t kEntityPlayerNameOffset = 0x1740;
inline constexpr uintptr_t kEntityPlayerCollectibleBeginOffset = 0x1AB8;  // 每收藏品计数数组（步长 4）
inline constexpr uintptr_t kEntityPlayerCollectibleEndOffset = 0x1AC0;
inline constexpr uintptr_t kEntityPlayerSize = 0x2FA0;                    // sizeof(Entity_Player)
// `Entity_Player` 的 vtable 指针（`_ZTVN…Entity_PlayerE + 0x10`）：判断"这个指针真是一张
// Entity_Player"的最强判据，用 `*(u64*)candidate == base + 该偏移`。
inline constexpr uintptr_t kEntityPlayerVtableOffset = 0xA37110;
inline constexpr uintptr_t kEntityPlayerHasCollectibleOffset = 0x27D3F4;  // HasCollectible(id, bool)
// `Entity_Player::AddCollectible(eCollectibleType, int, bool, int, int)`（`0x292A74`，
// 符号 `_ZN15IsaacRepentance13Entity_Player14AddCollectibleENS_16eCollectibleTypeEibii`）。
// 清单里属 `missing_easy`（有底座、由我们自己接）。接法与 `HasCollectible` 同一种：
// **模块基址 + 偏移**，外加 4 字节入口指纹（`sub sp, sp, #0x110`）——偏移写错会落到别的函数上，
// 调用它的后果不可预期，所以这一层指认比"只查可读"更严。
inline constexpr uintptr_t kEntityPlayerAddCollectibleOffset = 0x292A74;
// 首 4 字节按**小端整字**存（`FF 43 04 D1` → `0xD10443FF`）：调用点用一次 `ReadEngine<u32>`
// 就能核对，不必逐字节读。
inline constexpr std::uint32_t kEntityPlayerAddCollectibleEntryWord = 0xD10443FFU;

// `Entity_Player::AddCoins(int Amount)`（`0x280068`，符号
// `_ZN15IsaacRepentance13Entity_Player8AddCoinsEi`）。清单里同样是 `missing_easy`（有底座、
// 由我们自己接）。接法与 `AddCollectible` 逐字相同：模块基址 + 偏移 + 4 字节入口指纹 ——
// 它会**改玩家状态**，偏移写错就会去调别的函数，那一层指认不是可选项。
inline constexpr uintptr_t kEntityPlayerAddCoinsOffset = 0x280068;
// 首 4 字节按小端整字存（`FD 7B BD A9` → `0xA9BD7BFD`，即 `stp x29,x30,[sp,#-0x30]!`）。
inline constexpr std::uint32_t kEntityPlayerAddCoinsEntryWord = 0xA9BD7BFDU;

// --- 批次 050（2026-09-19）：GoodTrip 真机上接下来会撞到的一批"引擎方法" -------------------
//
// 来源：`tools/mod_api_gap_report.py` 对 goodtripfixed 的高置信缺口清单（每条都带真机调用次数），
// 以及 GoodTrip 源码里的实际调用点。偏移取自固定 NRO 的动态符号表（`file_offset` 就是运行时模块
// 里的偏移，见 `runtime/tests/test_lua_level_batch8.py` 的说明），入口 4 字节指纹由
// `nro_symbols.parse_dynamic_symbols` + 读文件前 4 字节得出。
//
// `Entity_Player::SetShootingCooldown(int)`（`0x2FB994`）。GoodTrip 在**打开地图后按方向键**时
// 会调它（`scripts/control.lua:100` 的 `M.player_shoot_cooldown()`，`widget.lua:560` 也调）——
// 而在它**之后**的 `widget.draw_minimap_ui()` 才是真正画小地图的地方 ⇒
// 缺它是"按住地图键 + 方向键，屏幕什么都不画"的直接原因。
inline constexpr uintptr_t kEntityPlayerSetShootingCooldownOffset = 0x2FB994;
inline constexpr std::uint32_t kEntityPlayerSetShootingCooldownEntryWord = 0xB9440808U;

// `Entity_Player::AnimateHappy()`（`0x2F6CA8`）/ `AnimateSad()`（`0x2F6D2C`）。
// GoodTrip 传送成功/失败时各播一个动画（`scripts/control.lua:226`/`234`）。
// 两者开头都是 `stp x29,x30,[sp,#-0x30]!` ⇒ **指纹相同**，靠偏移区分。
// （批次 051 起它们走"引擎方法数据行"，每个 API 只花 16 字节只读数据 ⇒ 不再受预算限制。）
inline constexpr uintptr_t kEntityPlayerAnimateHappyOffset = 0x2F6CA8;
inline constexpr std::uint32_t kEntityPlayerAnimateHappyEntryWord = 0xA9BD7BFDU;
inline constexpr std::uintptr_t kEntityPlayerAnimateSadOffset = 0x2F6D2C;
inline constexpr std::uint32_t kEntityPlayerAnimateSadEntryWord = 0xA9BD7BFDU;

// `Entity_Player::GetNumBlackHearts()`（const，`0x27FF84`）。
// ★ PC 的 Lua 名字是 `EntityPlayer:GetBlackHearts()`，而**引擎里的符号叫 `GetNumBlackHearts`**
// （同族 `GetNumCoins`/`GetNumKeys` 都是这个名字形状）。GoodTrip 在传送前的体力判断里连调两次
// （`scripts/trip.lua:111`/`116`）⇒ 缺它同样是"方法不存在"，整条回调被打断。
inline constexpr uintptr_t kEntityPlayerGetNumBlackHeartsOffset = 0x27FF84;
inline constexpr std::uint32_t kEntityPlayerGetNumBlackHeartsEntryWord = 0xB956C40AU;

// `Game::ChangeRoom(int, int)`（`0x353FE0`）。GoodTrip 的传送主路径（`scripts/trip.lua:150` 起
// 共 6 处）就是 `Game():ChangeRoom(目标格, -1)`；第二参 `-1` 表示"按当前维度"。
inline constexpr uintptr_t kGameChangeRoomOffset = 0x353FE0;
inline constexpr std::uint32_t kGameChangeRoomEntryWord = 0xA9BC7BFDU;

// 批次 055：`Game::StartRoomTransition(int RoomIndex, eDirection, eAnimation,
// Entity_Player* Player, int Dimension)`（`0x353CBC`，入口 `0xD10343FF`）。
//
// 为什么必需：GoodTrip 的传送**默认路径**就是它（`scripts/trip.lua:207`，而
// `cfg.FastTransition` 默认 false ⇒ 走的就是这一条）。缺它时模组报
// "attempt to call a nil value (method 'StartRoomTransition')"，传送这一步整条断掉。
// 5 个参数、其中第 4 个是**玩家实体指针** ⇒ 这是"通用跳板 + 签名描述符"第一个真实消费者
// （见 `engine_call_trampoline.hpp` 与 `EngineCallShape::VoidIntIntIntHandleInt`）。
inline constexpr uintptr_t kGameStartRoomTransitionOffset = 0x353CBC;
inline constexpr std::uint32_t kGameStartRoomTransitionEntryWord = 0xD10343FFU;
// 2026-10-26：固定NRO 0x353CBC读取，供首层贪婪沙漏错误房原生入口认证。
inline constexpr std::array<u8, 16> kGameStartRoomTransitionExpectedBytes = {
    0xff,0x43,0x03,0xd1,0xea,0x2b,0x00,0xfd,0xe9,0x23,0x06,0x6d,0xfd,0x7b,0x07,0xa9
};

// 批次 063：`Entity::IsFlying() const`（`0x5C744`，入口 `0xB941E008`）。
//
// 为什么必须有：GoodTrip 的诅咒房判定（`scripts/trip.lua:90`）问的是
// `floor.player:IsFlying()`（飞着进诅咒房不掉血），没有它就报
// "attempt to call a nil value (method 'IsFlying')" ⇒ **刺房（type 10）整条传送路径断掉**。
// PC 里它在基类 `Entity` 上（`Entity.md`），而 `EntityPlayer` 会继承基类方法
// （`IndexEntity()` 查完自己的表会回落到 `kEntityMetatable`），所以这一行挂在 `Entity` 族。
// 签名：无参（只有隐式 this）、返回 bool ⇒ 用 `EngineCallShape::Bool0`（批次 055 的返回种类里已有 Bool）。
inline constexpr uintptr_t kEntityIsFlyingOffset = 0x5C744;
inline constexpr std::uint32_t kEntityIsFlyingEntryWord = 0xB941E008U;

// 批次 207（2026-09-29）：`Entity::IsActiveEnemy(bool includeDead) const`（`0x5F028`，
// 符号 `_ZNK15IsaacRepentance6Entity13IsActiveEnemyEb`，入口 `0xB9403809`）。
//
// 为什么必须有：MCM（Mod Config Menu）决定"现在能不能开菜单"要问
// `entity:IsActiveEnemy()`（`analysis/mod-corpus/isaac-mod-config-menu/scripts/modconfig.lua:206`，
// 在 `RoomIsSafe()` 里）；PC 契约 `tools/pc_contract_docs/Entity.md:454/456`
// （`#### boolean IsActiveEnemy ( boolean includeDead )`，正文 "return true for non background NPCs
// (ex: every enemy except fire and shopkeepers)"）。缺它就是 "attempt to call a nil value"，
// 整条回调被摘 ⇒ 用户看到"装了 MCM 但菜单打不开"。
//
// ★ **`includeDead` 的缺省值 = 0**（反汇编原文，`0x5F028`..`0x5F0B8`）：
//     0x5F0A4  ldrb   w8, [x0, #0x1C3]   ; 再调一次这个字节就换个问题
//     0x5F0AC  cset   w8, eq             ; w8 = (那个字节 == 0) = "还活着"
//     0x5F0B0  orr    w8, w8, w1         ; w8 |= includeDead（x1 = w1 = 形参，**不写缺省**）
//     0x5F0B4  and    w0, w8, #0x1
//   `w1` 只在最后被 `orr` 并入结果、函数体里从不给它赋默认值 ⇒ Lua 侧不传时**寄存器必须已经是 0**。
//   这正是形状 `EngineCallShape::BoolOpt1`（"尾部参数可省略"）存在的理由。
// ★ 顺带定下 `Entity + 0x1C3` 是"死亡/已被移除"字节（同一字节被 `Entity_Pickup::CanReroll`
//   与 `Entity_Projectile::CanShutDoors` 的邻居读到，写法一致）。
inline constexpr uintptr_t kEntityIsActiveEnemyOffset = 0x5F028;
inline constexpr std::uint32_t kEntityIsActiveEnemyEntryWord = 0xB9403809U;

// 批次 207（2026-09-29）：`Entity_Projectile` 的 vtable 指针（`0xA37410`）与
// `EntityProjectile.ProjectileFlags`（`+0x428`，u32）。
//
// **vtable 偏移的算法**：`_ZTVN15IsaacRepentance17Entity_ProjectileE` 符号落在 `0xA37400`，
// 加 `0x10` 跳过 vtable 表头（offset-to-top + typeinfo）⇒ `0xA37410`。这条 `+0x10` 规则由
// 既有三个常量交叉验证：`Entity_Player` 符号 `0xA37100` ↔ 本文件 `0xA37110`；
// `Entity_Pickup` `0xA36E18` ↔ `0xA36E28`；`Entity_Familiar` `0xA35718` ↔ `0xA35728`（都差 0x10）。
//
// **`ProjectileFlags` 的偏移证据**（逐条指令）：`Entity_Projectile::CanShutDoors()` @ `0x31F450`：
//     0x31F450  ldr  w8, [x0, #0x3c]     ; Variant（`0xB` = 门）
//     0x31F45C  ldr  w8, [x0, #0x428]    ; ★ `ProjectileFlags`
//     0x31F460  mvn  w8, w8              ; 取反
//     0x31F464  lsr  w0, w8, #31         ; 取出 bit31 当返回值
//   ⇒ bit31 就是 `ProjectileFlags.CANT_HIT_PLAYER`（`.data` 里
//   `Entity_Projectile::CANT_HIT_PLAYER = 0x80000000`，与 `analysis/isaacdocs-snapshot/docs/enums/
//   ProjectileFlags.md` 的逐位表吻合）—— MCM 判"这发子弹会不会打到玩家"用的正是这一位
//   （`modconfig.lua:220`：`entity:ToProjectile().ProjectileFlags & ProjectileFlags.CANT_HIT_PLAYER`）。
//   同族还有 `0x31F478 str xzr,[x0,#0x428]`（整体清零，8 字节写覆盖 `+0x428`/`+0x42C`）——
//   字段本身按 PC 契约 `EntityProjectile.md` 是 `int`（32 位）。
inline constexpr uintptr_t kEntityProjectileVtableOffset = 0xA37410;
inline constexpr uintptr_t kEntityProjectileFlagsOffset = 0x428;
// `Type` 判据用的是**既有**的 `kEntityTypeProjectile`（本文件"实体分区"那一段，
// `EntityType.ENTITY_PROJECTILE == 9`）—— 这里不再写第二份，避免同名常量两处定义。

// 批次 207（2026-09-29）：`Game` 里**内嵌**的 `HUD` 子对象（`Game + 0xE8468`），
// 以及 `HUD` 自己的"可见"字节（`HUD + 0xC53FA`）。
//
// **为什么是"内嵌"而不是指针**：`Game::Game()` @ `0x34B3F8`..`0x34B404` 逐条为证 ——
//     0x34B3F8  mov  w8, #0x8468
//     0x34B3FC  movk w8, #0xe, lsl #16      ; w8 = 0xE8468
//     0x34B400  add  x0, x20, x8            ; x20 = this（Game*）
//     0x34B404  bl   0x679AA0 <import _ZN15IsaacRepentance3HUDC2Ev>   ; HUD::HUD()
//   ⇒ `HUD* = Game* + 0xE8468`（加法，引擎里**不存在**指向它的指针）。同一函数里紧邻的
//   `GameOver`(`+0x27630`)、`Leaderboard`(`+0x47BF8`) 写法逐字同形。
//   `HUD::HUD()` 内部再按 `+0x908` 步长构造 8 个 `PlayerHUD`（`0x34B690` 起）。
// **可见字节的证据**：`HUD::Render()` @ `0x3AC71C` 的**前四条有效指令**就是它 ——
//     0x3AC74C  mov  w8, #0x53fa
//     0x3AC750  movk w8, #0xc, lsl #16      ; w8 = 0xC53FA
//     0x3AC754  ldrb w8, [x0, x8]
//     0x3AC758  cbz  w8, 0x3AE3B4           ; == 0 ⇒ 直接跳到函数收尾（`add sp,sp,#0x260` … `ret`）
//   ⇒ 这个字节为 0 时整个 HUD 渲染被跳过，正是 `HUD:IsVisible()/SetVisible()` 要的语义。
//   ★ 这是本批**唯一一处我们会去写的引擎内存**（`SetVisible`），所以先只做读、写留待真机确认。
inline constexpr uintptr_t kGameHudObjectOffset = 0xE8468;
inline constexpr uintptr_t kHudVisibleFlagOffset = 0xC53FA;

// 批次 207（2026-09-29）：`Room:IsClear()` 的判据位 —— `[Room + 0x8] + 0x50` 的 **bit0**。
//
// `Room` 的前 8 字节之后紧跟一个 `RoomDescriptor*`（既有常量 `kRoomDescriptorClearOffset` /
// `kRoomDescriptorFlagsOffset` 都是 `0x50`），而 `Room::TriggerClear(bool)` @ `0x470B58` 的
// 前五条有效指令就是"把这个位置 1"：
//     0x470B68  ldr  x8, [x0, #0x8]     ; x8 = RoomDescriptor*
//     0x470B74  ldr  w9, [x8, #0x50]
//     0x470B78  orr  w9, w9, #0x1       ; ★ bit0
//     0x470B7C  str  w9, [x8, #0x50]    ; 写回
//   ⇒ bit0 = "这个房间已清"。函数名（`TriggerClear` = "触发清房"）与操作数一起把语义钉死了，
//   不是"某处有个字节"。
// PC 契约 `tools/pc_contract_docs/Room.md:642/644`：`#### boolean IsClear ( )`，
// 消费者 `modconfig.lua:231`：`if room:IsClear() and not roomHasDanger then return true end`。
inline constexpr unsigned kRoomClearFlagBit = 0;

// 批次 137（2026-09-26）：`Entity_Player::AddNullCostume(ItemConfig::eNullItemID)`（`0x291BBC`，
// 符号 `_ZN15IsaacRepentance13Entity_Player14AddNullCostumeENS_10ItemConfig11eNullItemIDE`）。
//
// 为什么必须有：The Specialist for Good Items（"捡到四级物品跳 Specialist 舞 + 放歌"）在跳舞时
// 用 `player:AddNullCostume(Isaac.GetCostumeIdByPath(...))` 给玩家换上一套临时服装
// （`main.lua` 的舞蹈段落）。缺它就是 "attempt to call a nil value (method 'AddNullCostume')"，
// 而那几句落在 `MC_POST_PICKUP` 那类条件回调里 ⇒ 报错会把**整条回调摘掉**，用户看到的就是
// "捡到四级物品什么也没发生"（不崩、不报错）。
// 签名：一个 `int`（`eNullItemID` 枚举按值传，与 `AddCoins` 同一个 ABI 形状）⇒ `Void1` 数据行。
// 入口 4 字节 `FD 7B BE A9` → `0xA9BE7BFD`（`stp x29,x30,[sp,#-0x30]!`）。
inline constexpr uintptr_t kEntityPlayerAddNullCostumeOffset = 0x291BBC;
inline constexpr std::uint32_t kEntityPlayerAddNullCostumeEntryWord = 0xA9BE7BFDU;

// 批次 137（2026-09-26）：`Entity_Player::TryRemoveNullCostume(ItemConfig::eNullItemID)`（`0x2F2170`，
// 符号 `_ZN15IsaacRepentance13Entity_Player16TryRemoveCostumeENS_10ItemConfig11eNullItemIDE`）。
//
// 这是 The Specialist for Good Items 的**另一半**：跳舞结束/物品丢掉时要 `player:TryRemoveNullCostume(id)`
// 把临时服装摘掉（`main.lua:504/508/513`）。**坐实过程**：`analysis/lua-api-inventory/inventory.json`
// 里 `Entity_Player` 类下有三条 `TryRemoveCostume` 重载（`eNullItemID` / `eTrinketType` /
// `(eCollectibleType,bool)`）—— PC 的 `TryRemoveNullCostume(NullId)` 对应的就是**第一条**
// （`eNullItemID` 那个），签名逐条对上，不是猜的。
// 入口 4 字节 `FD 7B BE A9` → `0xA9BE7BFD`（与 `AddNullCostume` 同为 `stp x29,x30,[sp,#-0x30]!`，
// 靠偏移区分）。
inline constexpr uintptr_t kEntityPlayerTryRemoveNullCostumeOffset = 0x2F2170;
inline constexpr std::uint32_t kEntityPlayerTryRemoveNullCostumeEntryWord = 0xA9BE7BFDU;

// --- 批次 177（2026-09-28）：审查第 3 遍查出的"引擎里有同名成员、我们却恒返回假值"的桩 --------
//
// 来源 = `tools/lua_api_engine_reuse_scan.py`（第 3 遍的只读对账器）输出的 `stub+engine` 档：
// 该档的每一行都满足"① 我们的处理器恒返回假值 ② 引擎动态符号表里有同名成员函数
// ③ 签名能从 mangled name 直接读出来"。这一批把其中**接收者就是 `Entity_Player`** 的 5 条
// 从"手写假桩"改成"引擎方法数据行"（每个 API 只花 16 字节只读数据、0 字节代码）。
//
// ★ 偏移 = 固定 NRO（build `91C73FDD575061318D68886316AFEAC72388B2AB`）的动态符号表 `file_offset`
//   （`file_offset` 就是运行时模块里的偏移，与 `kManagerUpdateFileOffset` 那批同一条口径）；
//   入口 4 字节指纹 = 读该文件偏移处的前 4 字节、按小端整字存（`nro_disasm.py` 可复核）。
//
// `Entity_Player::GetPill(int) const` @ `0x2E8D80`
//   符号 `_ZNK15IsaacRepentance13Entity_Player7GetPillEi`。EID 逐帧问
//   （`features/eid_api.lua:2606` 的 `player:GetPill(0)`）⇒ 恒 0 就是"口袋描述永远缺一条"。
//   签名 `(this, i32) -> i32` ⇒ `EngineCallShape::Int1`。
//   入口 4 字节 `08 CC 21 8B` → `0x8B21CC08`（`add x8, x0, w1, sxtw #3`）。
//   ★ 与下面 `GetCard` **同指纹**（同族、同形状的前几条指令）⇒ 靠偏移区分，与
//   `AnimateHappy`/`AnimateSad` 那条注释同一个道理。
inline constexpr uintptr_t kEntityPlayerGetPillOffset = 0x2E8D80;
inline constexpr std::uint32_t kEntityPlayerGetPillEntryWord = 0x8B21CC08U;

// `Entity_Player::GetCard(int) const` @ `0x2E8D58`（符号 `_ZNK15IsaacRepentance13Entity_Player7GetCardEi`）。
// 与 `GetPill` 成对使用（EID 的 `eid_data.lua:91-116` 两处都按 `id ~= 0` 判）⇒ `Int1`。
// 入口 4 字节 `08 CC 21 8B` → `0x8B21CC08`（同 `GetPill`，靠偏移区分）。
inline constexpr uintptr_t kEntityPlayerGetCardOffset = 0x2E8D58;
inline constexpr std::uint32_t kEntityPlayerGetCardEntryWord = 0x8B21CC08U;

// `Entity_Player::GetZodiacEffect() const` @ `0x29A938`
//   （符号 `_ZNK15IsaacRepentance13Entity_Player15GetZodiacEffectEv`）。
// PC 契约 `tools/pc_contract_docs/EntityPlayer.md:1341`：返回「星座道具当前的派生效果值」（整型）。
// 签名 `(this) -> i32` ⇒ 复用已有的 `EngineCallShape::Int0`（批次 051 就有，不新增形状）。
// 入口 4 字节 `FF C3 00 D1` → `0xD100C3FF`（`sub sp, sp, #0x30`）。
inline constexpr uintptr_t kEntityPlayerGetZodiacEffectOffset = 0x29A938;
inline constexpr std::uint32_t kEntityPlayerGetZodiacEffectEntryWord = 0xD100C3FFU;

// `Entity_Player::HasPlayerForm(ePlayerForm) const` @ `0x298510`
//   （符号 `_ZNK15IsaacRepentance13Entity_Player13HasPlayerFormENS_11ePlayerFormE`）。
// PC 契约 `tools/pc_contract_docs/EntityPlayer.md:1382`：「当前是不是某个形态」⇒ 返回 bool。
// 签名 `(this, i32) -> bool` ⇒ `EngineCallShape::Bool1`（本批新增）。
// 入口 4 字节 `08 FC 84 52` → `0x5284FC08`（`mov w8, #0x27E0`）。
inline constexpr uintptr_t kEntityPlayerHasPlayerFormOffset = 0x298510;
inline constexpr std::uint32_t kEntityPlayerHasPlayerFormEntryWord = 0x5284FC08U;

// `Entity_Player::GetGlyphOfBalanceDrop(unsigned int&, unsigned int&)` @ `0x2FE574`
//   （符号 `_ZN15IsaacRepentance13Entity_Player21GetGlyphOfBalanceDropERjS1_`，批次 177 扫出）。
// ★ PC 契约文档里**查不到这一条**（`tools/pc_contract_docs/EntityPlayer.md` 里没有）——
//   它是 **Repentogon 才有的 API** ⇒ Lua 侧形状没有官方口径可对齐。口径取它**唯一的消费者 EID**：
//   `local t = player:GetGlyphOfBalanceDrop(Variant, SubType)`，之后读 `t[1]`（与 `-1` 比，判"有没有掉落"）
//   与 `t[2]`（子类型，0 = 不带）。原文见仓库里的副本
//   `The Binding of Isaac Rebirth/mods/external item descriptions_836319872/features/eid_repentogon.lua:265`。
// 签名 `void(this, u32&, u32&)`：两个参数**既是入参又是出参** —— 引擎只往 `x1`/`x2` 指向的槽里写、
//   唯一一个 `ret` 之前从不写 `w0`（批次 177 的反汇编取证，完整推导在
//   `tools/lua_api_stub_ledger.json` 的那条 note 里）。
// ⇒ 走批次 184 新增的 `EngineCallShape::Ref2U32Pair`（返回种类 `U32PairTable`：两个槽读回来压成一张两元表）。
// 入口 4 字节 `FF C3 01 D1` → `0xD101C3FF`（`sub sp, sp, #0x70`；本批用
//   `python3 tools/nro_disasm.py 0x2fe574 24` 复核过）。
inline constexpr uintptr_t kEntityPlayerGetGlyphOfBalanceDropOffset = 0x2FE574;
inline constexpr std::uint32_t kEntityPlayerGetGlyphOfBalanceDropEntryWord = 0xD101C3FFU;

// `Entity_Player::CanPickRedHearts()` @ `0x2FB6A4`
//   （符号 `_ZN15IsaacRepentance13Entity_Player16CanPickRedHeartsEv`，**注意它不是 const 成员**
//   —— mangled name 里没有 `NK`；ABI 上无差别，`this` 仍在 `x0`）。
// PC 契约 `tools/pc_contract_docs/EntityPlayer.md:550`：「现在能不能捡红心」（满血时为 false）。
// ★ 真实调用点：EID 的 `features/eid_itemprediction.lua:366` 的
//   `elseif ... and player:CanPickRedHearts() and player:GetHearts() <= 1 ...` ——
//   恒 false 会让"满红心"那一支预测永远不成立。
// 签名 `(this) -> bool` ⇒ 复用 `EngineCallShape::Bool0`。
// 入口 4 字节 `0A 38 57 B9` → `0xB957380A`（`ldr w10, [x0, #0x1738]`，读 PlayerType）。
inline constexpr uintptr_t kEntityPlayerCanPickRedHeartsOffset = 0x2FB6A4;
inline constexpr std::uint32_t kEntityPlayerCanPickRedHeartsEntryWord = 0xB957380AU;

// 批次 065：`Entity::TakeDamage(float, EntityRef const&, int)` @ `0x5DCA4`（入口 `0xD10343FF`）
// 与玩家的重载 `Entity_Player::TakeDamage(...)` @ `0x2A34D0`（入口 `0xD107C3FF`）。
//
// 为什么两条都要：GoodTrip 的诅咒房过路费（`scripts/trip.lua:70`）打的是**玩家**，而玩家的重载
// 才有玩家专属逻辑（无敌帧、血量、动画）。PC 那边 `TakeDamage` 是**虚函数**
// （各子类各有实现、模块内只走虚表），我们这里按"接收者是不是玩家"二选一：
// 玩家走 `0x2A34D0`，其余走基类 `0x5DCA4`。**已知偏离**：非玩家子类自己的重载不会被执行
// （例如 `Entity_NPC::TakeDamage` 的额外处理），写在实现处的注释里。
inline constexpr uintptr_t kEntityTakeDamageOffset = 0x5DCA4;
inline constexpr std::uint32_t kEntityTakeDamageEntryWord = 0xD10343FFU;
inline constexpr uintptr_t kEntityPlayerTakeDamageOffset = 0x2A34D0;
inline constexpr std::uint32_t kEntityPlayerTakeDamageEntryWord = 0xD107C3FFU;

// ---- 批次 271（2026-10-02）：`needs_new_receiver` 桶头部三条（都是"引擎里有同名方法"）------
//
// 这一批的做法与 `TakeDamage` 同一形态：**解析入口 → 校验 16 字节原文 → 直接调**。
// 三条的符号都逐字在 dynsym 里（`tools/nro_symbols.py`），并且**都只有基类/本类一份实现**
// （用嵌套名解析器扫过全符号表：`SetColor` 只在 `Entity`、`AddCharmed` 只在 `Entity`、
//  `UseActiveItem` 只在 `Entity_Player` —— 没有子类重写 ⇒ 不存在"该调哪个重载"的问题）。
//
//   * `Entity::SetColor(ColorMod const&, int, int, bool, bool)` @ `0x63B84`，51 处调用（全清单单条最高）。
//     反汇编首四句给出寄存器形状：`mov w21,w5` / `mov w23,w4` / `mov w19,w3` / `mov w20,w2`
//     ⇒ `x1`=&ColorMod、`w2`=Duration、`w3`=Priority、`w4`=Fadeout、`w5`=Share，
//     与 mangled 名 `…SetColorERKNS_8ColorModEiibb` 逐字对应。
//     ★ 第一个参数用的 `EngineColorMod` 与批次 267 的 `Game:SpawnParticles` **是同一个结构**
//     （批次 271 把它抽到 `interfaces/lua/engine_color_mod.hpp`，映射只留一份）。
//   * `Entity::AddCharmed(EntityRef const&, int)` @ `0x5EBE8`。
//   * `Entity_Player::UseActiveItem(eCollectibleType, unsigned, int, int)` @ `0x30653C`
//     —— 这条**早就有常量**（见下面 `kEntityPlayerUseActiveItemOffset`），本批只是把处理器接上。
inline constexpr uintptr_t kEntitySetColorOffset = 0x63B84;
inline constexpr std::array<u8, 16> kEntitySetColorExpectedBytes = {
    0xFF, 0x03, 0x02, 0xD1, 0xFD, 0x7B, 0x04, 0xA9,
    0xFD, 0x03, 0x01, 0x91, 0xF8, 0x5F, 0x05, 0xA9,
};
inline constexpr uintptr_t kEntityAddCharmedOffset = 0x5EBE8;

// ---- 批次 273（2026-10-02）：`needs_new_receiver` 桶里"参数全是标量/Vector/EntityRef"的 8 条 ------
//
// 选批口径（同批 271/272）：用嵌套名解析器扫全符号表，**只收"同名方法只有一个类有"的条目**
// （`SetColor` 那种）—— 那意味着**没有子类重写**，不需要像 `Entity:TakeDamage` 那样挑重载。
// 本批 8 条全部满足；`GridEntity:Door::Open/Close` 那种"同名类数 > 1"的（虚函数重写）**不收**。
//
// 8 条的 mangled 名都在 dynsym 里逐字可查，arity 与 PC 契约页一一对应：
//   Entity 族（挂在 `kEntityHandlers`）：`AddFreeze(EntityRef const&, int)` @ `0x5E358`、
//                                        `AddPoison(EntityRef const&, int, float)` @ `0x5E5F8`；
//   EntityPlayer 族（挂在 `kEntityPlayerHandlers`）：`AddBlueSpider(Vector2 const&)` @ `0x2FB40C`
//     （**返回 Entity**）、`AddGoldenHearts(int)` @ `0x2FC924`、`AddMinisaac(Vector2 const&, bool)`
//     @ `0x2AC1F4`（**返回 EntityFamiliar**）、`AddPill(ePillColor)` @ `0x2B0B80`、
//     `AnimateAppear()` @ `0x2E8184`、`DropTrinket(Vector2 const&, bool)` @ `0x2A20D4`。
//   ★ `AddGoldenHearts` 与 `AnimateAppear` 的**入口 16 字节完全相同**（同一个编译器prologue）——
//     这正说明"守卫只能用来确认'这个地址上确实是我们要的那串指令'，不能用来**区分**两个函数"；
//     区分靠的是**偏移**。写在这里免得以后有人拿守卫当唯一判据。
inline constexpr uintptr_t kEntityAddFreezeOffset = 0x5E358;
inline constexpr std::array<u8, 16> kEntityAddFreezeExpectedBytes = {
    0xFF, 0xC3, 0x01, 0xD1, 0xFD, 0x7B, 0x03, 0xA9,
    0xFD, 0xC3, 0x00, 0x91, 0xF7, 0x23, 0x00, 0xF9,
};
inline constexpr uintptr_t kEntityAddPoisonOffset = 0x5E5F8;
inline constexpr std::array<u8, 16> kEntityAddPoisonExpectedBytes = {
    0xFF, 0x03, 0x02, 0xD1, 0xE9, 0x23, 0x03, 0x6D,
    0xF7, 0x2B, 0x00, 0xF9, 0xFD, 0x7B, 0x04, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerAddBlueSpiderOffset = 0x2FB40C;
inline constexpr std::array<u8, 16> kEntityPlayerAddBlueSpiderExpectedBytes = {
    0xFF, 0x03, 0x01, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF5, 0x13, 0x00, 0xF9,
};
inline constexpr uintptr_t kEntityPlayerAddGoldenHeartsOffset = 0x2FC924;
inline constexpr std::array<u8, 16> kEntityPlayerAddGoldenHeartsExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerAddMinisaacOffset = 0x2AC1F4;
inline constexpr std::array<u8, 16> kEntityPlayerAddMinisaacExpectedBytes = {
    0xFF, 0xC3, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF9, 0x1B, 0x00, 0xF9,
};
inline constexpr uintptr_t kEntityPlayerAddPillOffset = 0x2B0B80;
inline constexpr std::array<u8, 16> kEntityPlayerAddPillExpectedBytes = {
    0xE2, 0x03, 0x1F, 0x2A, 0x4F, 0x1E, 0x0F, 0x14,
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerAnimateAppearOffset = 0x2E8184;
inline constexpr std::array<u8, 16> kEntityPlayerAnimateAppearExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerDropTrinketOffset = 0x2A20D4;
inline constexpr std::array<u8, 16> kEntityPlayerDropTrinketExpectedBytes = {
    0xFF, 0x43, 0x01, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF7, 0x13, 0x00, 0xF9,
};

// ---- 批次 274（2026-10-02）：清桶批（12 条）-----------------------------------------------------
//
// 选批口径**与批次 273 相同**（引擎里有同名方法 **且该同名方法只有一个类有** ⇒ 无子类重写），
// 只是把"参数最简单"那一档收到极致：**arity 0..2、参数只有标量 / `Vector` / `EntityRef`**。
// 十二条的 mangled 名都在 dynsym 里逐字可查；★ **这份守卫字节是用脚本从镜像现场读出来的**
// （不是照抄清单里的守卫串 —— 批次 269 就栽在抄错一个字节上）；`test_runtime_constants_against_nro`
// 每轮还会再对一次。
//
//   体积提示：这一批里 `AddPrettyFly` / `AnimateTrapdoor` / `CanPickSoulHearts` 三条的入口 16 字节
//   **相同**（同一套编译器 prologue，与批次 273 的 `AddGoldenHearts`/`AnimateAppear` 同一现象）
//   ⇒ 再强调一次：**守卫不能当身份判据，区分靠偏移**。
//
//   `kSeedsForgetStageSeedOffset` 是 `Seeds` 族的：`this` 不是句柄存的地址，而是
//   `Game + kGameSeedsObjectOffset` 现算（与 `Seeds:GetStartSeed()` 同一条思路）。
inline constexpr uintptr_t kEntityAddFearOffset = 0x5F660;
inline constexpr std::array<u8, 16> kEntityAddFearExpectedBytes = {
    0xFF, 0xC3, 0x01, 0xD1, 0xFD, 0x7B, 0x03, 0xA9,
    0xFD, 0xC3, 0x00, 0x91, 0xF7, 0x23, 0x00, 0xF9,
};
inline constexpr uintptr_t kEntityAddHealthOffset = 0x5A248;
inline constexpr std::array<u8, 16> kEntityAddHealthExpectedBytes = {
    0xFF, 0x43, 0x00, 0xD1, 0x01, 0x54, 0x43, 0xBD,
    0x20, 0x28, 0x20, 0x1E, 0xE0, 0x0F, 0x00, 0xBD,
};
inline constexpr uintptr_t kEntityRemoveStatusEffectsOffset = 0x5FEB8;
inline constexpr std::array<u8, 16> kEntityRemoveStatusEffectsExpectedBytes = {
    0xE8, 0x0F, 0x1E, 0xFC, 0xFD, 0xFB, 0x00, 0xA9,
    0xFD, 0x23, 0x00, 0x91, 0xF3, 0x0F, 0x00, 0xF9,
};
inline constexpr uintptr_t kEntityPlayerAddBoneHeartsOffset = 0x27E380;
inline constexpr std::array<u8, 16> kEntityPlayerAddBoneHeartsExpectedBytes = {
    0xFF, 0x83, 0x01, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF9, 0x13, 0x00, 0xF9,
};
inline constexpr uintptr_t kEntityPlayerAddFriendlyDipOffset = 0x2F62DC;
inline constexpr std::array<u8, 16> kEntityPlayerAddFriendlyDipExpectedBytes = {
    0xE8, 0x03, 0x00, 0xAA, 0xE0, 0x03, 0x01, 0x2A,
    0xE1, 0x03, 0x02, 0xAA, 0xE2, 0x03, 0x08, 0xAA,
};
inline constexpr uintptr_t kEntityPlayerAddPrettyFlyOffset = 0x2F6DB0;
inline constexpr std::array<u8, 16> kEntityPlayerAddPrettyFlyExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerAnimateTrapdoorOffset = 0x2F69F8;
inline constexpr std::array<u8, 16> kEntityPlayerAnimateTrapdoorExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerCanPickSoulHeartsOffset = 0x2FB7C4;
inline constexpr std::array<u8, 16> kEntityPlayerCanPickSoulHeartsExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerDonateLuckOffset = 0x2F9978;
inline constexpr std::array<u8, 16> kEntityPlayerDonateLuckExpectedBytes = {
    0x08, 0x20, 0x59, 0xB9, 0x08, 0x01, 0x01, 0x0B,
    0x09, 0x58, 0x59, 0xB9, 0x08, 0x20, 0x19, 0xB9,
};
inline constexpr uintptr_t kEntityPlayerRemoveGoldenBombOffset = 0x2FC490;
inline constexpr std::array<u8, 16> kEntityPlayerRemoveGoldenBombExpectedBytes = {
    0x28, 0xDB, 0x82, 0x52, 0x08, 0x00, 0x08, 0x8B,
    0x1F, 0x01, 0x00, 0x39, 0x89, 0x3D, 0x00, 0x90,
};
inline constexpr uintptr_t kEntityPlayerRemoveGoldenKeyOffset = 0x280628;
inline constexpr std::array<u8, 16> kEntityPlayerRemoveGoldenKeyExpectedBytes = {
    0x08, 0xDB, 0x82, 0x52, 0x08, 0x00, 0x08, 0x8B,
    0x1F, 0x01, 0x00, 0x39, 0x69, 0x41, 0x00, 0x90,
};
inline constexpr uintptr_t kSeedsForgetStageSeedOffset = 0x4A1228;
inline constexpr std::array<u8, 16> kSeedsForgetStageSeedExpectedBytes = {
    0xFF, 0xC3, 0x00, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF3, 0x13, 0x00, 0xF9,
};

// ---- 批次 278（2026-10-02）：`EntityPlayer` 族的 5 条（参数个数与引擎符号**完全对齐**）------------
//
// 选批口径（在 273/274 之上再加一条硬要求）：**引擎符号的参数个数与 PC 契约页完全一致**
//   —— 因为有几条引擎版比 PC 版**多一个尾参**（例如 `ChangePlayerType(ePlayerType, bool)`，
//      PC 契约里只有一个参数）。多出来的那一个我们**不知道怎么给**（给 0/给 false 都是猜），
//      ⇒ 本批**不收**那些；只收个数对得上的：
//        `Entity_Player::ThrowHeldEntity(Vector2 const&)` @ 0x27C648（arity 1 ✓）
//        `Entity_Player::AddSwarmFlyOrbital(Vector2 const&)` @ 0x28D510（arity 1 ✓）
//        `Entity_Player::AddItemWisp(int, Vector2 const&, bool)` @ 0x31DF50（arity 3 ✓）
//        `Entity_Player::UsePill(ePillEffect, ePillColor, unsigned)` @ 0x2DFC04（arity 3 ✓）
//        ★ 这一条的偏移**仓库里早就有**（批次更早的清单登记过）—— 本批只是接上处理器，
//          所以下面**没有**它的常量（重复定义会编译红，本批真踩过一次）。
//        `Entity_Player::AddBlueFlies(int, Vector2 const&, Entity*)` @ 0x27FC18（arity 3 ✓）
//   五条都是**同名方法只有一个类有**（无子类重写），入口 16 字节**用脚本从镜像现场读出来**。
inline constexpr uintptr_t kEntityPlayerThrowHeldEntityOffset = 0x27C648;
inline constexpr std::array<u8, 16> kEntityPlayerThrowHeldEntityExpectedBytes = {
    0xFF, 0x83, 0x07, 0xD1, 0xE8, 0xCB, 0x00, 0xFD,
    0xFC, 0xD7, 0x00, 0xF9, 0xFD, 0xFB, 0x19, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerAddSwarmFlyOrbitalOffset = 0x28D510;
inline constexpr std::array<u8, 16> kEntityPlayerAddSwarmFlyOrbitalExpectedBytes = {
    0xFF, 0x03, 0x02, 0xD1, 0xFD, 0x7B, 0x04, 0xA9,
    0xFD, 0x03, 0x01, 0x91, 0xF8, 0x5F, 0x05, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerAddItemWispOffset = 0x31DF50;
inline constexpr std::array<u8, 16> kEntityPlayerAddItemWispExpectedBytes = {
    0xFF, 0x83, 0x02, 0xD1, 0xFD, 0x7B, 0x04, 0xA9,
    0xFD, 0x03, 0x01, 0x91, 0xFC, 0x6F, 0x05, 0xA9,
};
inline constexpr uintptr_t kEntityPlayerAddBlueFliesOffset = 0x27FC18;
inline constexpr std::array<u8, 16> kEntityPlayerAddBlueFliesExpectedBytes = {
    0xFF, 0x83, 0x01, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};

inline constexpr std::array<u8, 16> kEntityAddCharmedExpectedBytes = {
    0xFF, 0x83, 0x01, 0xD1, 0xFD, 0x7B, 0x03, 0xA9,
    0xFD, 0xC3, 0x00, 0x91, 0xF6, 0x57, 0x04, 0xA9,
};

// `Room::PlayMusic()`（`0x451834`）与 `Level::AddCurse(eLevelCurse,bool)`（`0x3E7E08`）/
// `Level::RemoveCurses(uint)`（`0x3D8EC4`）—— 传送路径上"补音乐 / 临时加撤迷宫诅咒"用的
// （`scripts/trip.lua:202`/`26`/`126`）。批次 051 起它们走"引擎方法数据行"（每个 16 字节只读）。
inline constexpr uintptr_t kRoomPlayMusicOffset = 0x451834;
inline constexpr std::uint32_t kRoomPlayMusicEntryWord = 0xD101C3FFU;
inline constexpr uintptr_t kLevelAddCurseOffset = 0x3E7E08;
inline constexpr std::uint32_t kLevelAddCurseEntryWord = 0xD10143FFU;
inline constexpr uintptr_t kLevelRemoveCursesOffset = 0x3D8EC4;
inline constexpr std::uint32_t kLevelRemoveCursesEntryWord = 0xD10143FFU;

// `Entity_Player + 0x16E0` = **金币数**（u32）。证据（2026-09-18，`tools/nro_disasm.py 0x280068`）：
// `Entity_Player::AddCoins` 的"取-加-夹-存"四条指令连着写同一个字段 ——
//   0x280100 `ldr w9,[x19,#0x16e0]` → 0x280104 `add w9,w9,w20`（w20 = 入参 Amount）
//   → 0x28010C `csel w8,w9,w8,lt` 夹到上限 → 0x28011C `str w8,[x19,#0x16e0]`，
// 之后 0x280120 调 `Entity_Player::consumable_count_changed(1)`、0x280144 尾调到
// `HUD::SetSecondScreenRefresh(HudRefreshType, 1)` —— 这两条是"消耗品数量变了要刷 HUD"的引擎侧效应。
// 上限来自同函数 0x2800F4 的 `csel w8, 99, 999`（999 = 拥有 INDEX 416 那件收藏品时）⇒ 即 PC 的
// `GetMaxCoins()` 语义，**独立说明这就是"加钱"而不是别的计数器**。
// 还有一条独立印证：0x280088 读 `[x19,#0x1738]`（= `kEntityPlayerTypeOffset`，PlayerType）
// 与 0x21/0x0E 比较后转去 `AddHearts` —— 那正是 Keeper（14）"金币当血加"的引擎分支。
inline constexpr uintptr_t kEntityPlayerCoinsOffset = 0x16E0;

// `Entity_Player` 的另外四个"计数类"字段（2026-09-18 取证）。四个都出自**同一个配方**：
// 引擎自己的 `Add<X>(int)` 就是"取-加-夹-存"**同一个**字段（并夹到 99），所以字段偏移能从它读出来。
// 取证命令：`python3 tools/nro_disasm.py <Add 函数偏移> 0x40`。
//   * **钥匙** `+0x16D4`：`AddKeys @ 0x2804E8` ——
//     `ldr w8,[x0,#0x16d4]` → `add w8,w8,w1` → `cmp w8,#0x63`+`csel` 夹到 99 → `str w10,[x0,#0x16d4]`;
//   * **炸弹** `+0x16DC`：⚠️ **2026-09-18 夜更正**（原写 `+0x16E4`，是错的；下面"更正证据"三条）;
//   * **魂充能** `+0x2478`：`AddSoulCharge @ 0x27FD98` —— 同形 + 尾调
//     `Entity_Player::update_soul_charges(int)`（这条引擎调用是语义锚点）;
//   * **血充能** `+0x247C`：`AddBloodCharge @ 0x27F5B0` —— 同形 + 尾调 `update_blood_charges(int)`。
// ★ **2026-09-18 夜更正（`+0x16E4` → `+0x16DC`）**，三条独立证据（都出自引擎自己的"消耗品"路径）：
//   ① `Entity_Player::store_consumable_data`（`0x28D300`）把消耗品存进 `ConsumableData` 的**顺序**是
//      `+0x16E0`→结构 `+0x00`、`+0x16D4`→`+0x04`、**`+0x16DC`→`+0x08`**（金币/钥匙/炸弹），
//      而 `+0x16E4` **压根不在这个集合里**；
//   ② `Entity_Player::sync_consumable_counts`（`0x2806C0`）联机同步按位分支：bit0 金币(`0x16E0`)、
//      bit1 钥匙(`0x16D4`)、**bit2 炸弹(`0x16DC`)**，并且比较 `+0x24A4` 作上限；
//   ③ `AddBombs` 的**常规路径**就是 `+0x16DC`（`ldr w8,[x19,#0x16dc]` → `add` → `cmp #0x63` →
//      `csel` 夹到 99 → `str`），并把值镜像给同伴；`+0x16E4` 只出现在
//      `PlayerType == 0x19`（`PLAYER_BLUEBABY_B`）那条**特殊分支**上（还伴随"立即生成炸弹实体"）。
//   原证据为什么错：它抄的是那条特殊分支的指令，而"访问次数"与"是不是消耗品"都不能替代
//   **"引擎自己在哪里把它当消耗品存取"** 这一条真值源（这次的判据工具 `tools/engine_field_recipe.py`
//   就是按"读出来的值被加上入参"排序，并在校验既有常数时把这条差异暴露出来的）。
// 交叉印证：三个"消耗品计数"连在一起（`0x16D4` 钥匙 / `0x16E0` 金币 / `0x16DC` 炸弹），
// 两个"充能"连在一起（`0x2478` 魂 / `0x247C` 血）—— 两条独立线索都指向同一簇，不是巧合。
// `AddKeys` 里还读了 `[x0,#0x19f0]`（玩家在 players 向量里的下标）⇒ 这些字段是**每个玩家各自**的，
// 所以读法是"玩家实体 + 偏移"，不是全局量。
inline constexpr uintptr_t kEntityPlayerKeysOffset = 0x16D4;
inline constexpr uintptr_t kEntityPlayerBombsOffset = 0x16DC;
inline constexpr uintptr_t kEntityPlayerSoulChargeOffset = 0x2478;
inline constexpr uintptr_t kEntityPlayerBloodChargeOffset = 0x247C;

// --- Entity_Player 的字段（2026-09-14 反汇编定位）--------------------------------------
//
// `ControllerIndex`（`+0x19EC`，u32）：`Entity_Player::SetControllerIndex(unsigned, bool)`
// （`0x29B6FC`）的**第一条指令**就是 `str w1, [x0, #0x19ec]`，随后把同一个值传播给子玩家
// （`[x0+0x2460]`/`[x0+0x2588]`/`[x0+0x2580]` 三个"分身/附属"指针各自的 `+0x19EC`）——
// 这就是 PC 的 `EntityPlayer.ControllerIndex`。它与 `kEntityPlayerIndexOffset`（`+0x19F0`）
// 相邻，但**不是**同一个量：`+0x19F0` 是"玩家在 `players` 向量里的下标"。
//
// 血量（PC 的 `GetEffectiveMaxHearts`/`GetSoulHearts`/`GetBrokenHearts`）：
//   * `+0x16B8`（u32）：**红心容器数**。`Entity_Player::GetEffectiveMaxHearts()`（`0x27E8AC`）
//     在"非骨心角色"分支上返回 `[x0+0x16b8] + [x0+0x2450]*2`（`0x27E8DC`–`0x27E8E4`），
//     骨心角色分支只返回 `[x0+0x16b8]`（`0x27E8D4`）。
//   * `+0x2450`（u32）：**骨心数**（上面那个 `lsl #1` 就是它）。
//   * `+0x16C4`（u32）：**魂心数**（半心为单位，含黑心）。证据：
//     `Entity_Player::IsBlackHeart(int)`（`0x27FE70`）先 `ldr w8,[x0,#0x16c4]`，
//     `ccmp w8, w1, #8, ge` —— 即"下标 i 必须 ≤ 魂心总数"；`GetNumBlackHearts()`（`0x27FF84`）
//     同样先取 `[x0+0x16c4]` 再 `[x0+0x16c8]`（黑心位图）。
//   * `+0x2470`（u32）：**碎心数**。`Entity_Player::AddBrokenHearts(int)`（`0x29A550`）
//     `ldr w9,[x19,#0x2470]` → 加参数 → 夹到 `GetHeartLimit(true)/2` → `str w8,[x19,#0x2470]`。
// 骨心角色的判据（`GetEffectiveMaxHearts` 里的掩码）：`PlayerType <= 0x28` 且
// `(1 << PlayerType) & 0x11883021410` 命中的角色**不计**骨心，即 PlayerType ∈
// {4, 10, 12, 17, 24, 25, 31, 35, 36, 40}（???、The Lost、Black Judas、The Soul、
// T.Judas、T.???、T.Lost、T.Forgotten、T.Bethany、T.Soul）。
inline constexpr uintptr_t kEntityPlayerControllerIndexOffset = 0x19EC;    // u32
inline constexpr uintptr_t kEntityPlayerRedHeartContainersOffset = 0x16B8;  // u32（半心单位）
inline constexpr uintptr_t kEntityPlayerSoulHeartsOffset = 0x16C4;          // u32（半心单位）
inline constexpr uintptr_t kEntityPlayerBoneHeartsOffset = 0x2450;          // u32
inline constexpr uintptr_t kEntityPlayerBrokenHeartsOffset = 0x2470;        // u32
inline constexpr std::uint64_t kEntityPlayerBoneHeartlessTypeMask = 0x11883021410ULL;
inline constexpr std::uint32_t kEntityPlayerMaximumTypeForBoneHearts = 0x28;

// --- 房间实体容器（批次 4，2026-09-12 反汇编静态定位）----------------------------------
//
// `Room + 0x1950` 是**内嵌**的 `IsaacRepentance::EntityList` 对象（既不是指针也不是
// `std::vector`）。铁证 `Room::AddEntity` @ `0x468a7c`：
//   `ldr w8,[x0,#0x1948]`（索引计数器）→ `add x0,x0,#0x1950`（取 `&EntityList`）
//   → `str w8,[x1,#0x30]`（**顺带证明 `Entity+0x30` == `Entity.Index`**）→ `b EntityList::Add`。
// `Room::RemoveEntity` / `Room::reset` 同形态。子偏移表（`EL` = `Room + 0x1950`）：
//
//   | 偏移 | 含义 |
//   |---|---|
//   | `EL+0x48` / cap `+0x50`=0x4000 / count `+0x54` | 一般实体表 |
//   | `EL+0x60` / cap `+0x68`=0x100 / count `+0x6c` | 持久实体表（PLAYER/FAMILIAR/KNIFE） |
//   | **`EL+0x78` / cap `+0x80`=0x800 / count `+0x84`** | **房间内活动实体全集（枚举用它）** |
//   | `EL+0x90` / `+0x98` / `+0x9c` | 渲染排序表 |
//   | `EL+0xA8` / cap `+0xB0`=0x4000 / count `+0xB4` | EFFECT 实体表 |
//   | `EL+0xC0` / `+0xD8`(cap 0x8000) / `+0xE4` | 查询结果暂存 + **单调 arena** |
//
// **容量是固定常量、从不重分配**（`Add` 溢出只打日志），所以三个容量值可以当**容器指纹**用。
inline constexpr uintptr_t kRoomEntityListOffset = 0x1950;      // Room → 内嵌 EntityList
// `Room + 0x8` = 指向本房间的 `RoomDescriptor*`（批次 207，2026-09-29 补记）。
//
// 证据（三条互相独立、都是函数名即语义的那种）：
//   1. `Room::TriggerClear(bool)` @ `0x470B58`：`0x470B68 ldr x8,[x0,#0x8]` →
//      `0x470B74 ldr w9,[x8,#0x50]` → `orr w9,w9,#0x1` → `str w9,[x8,#0x50]`
//      ⇒ 解出来的那个对象里 `+0x50` 就是布局表已确认的 `RoomDescriptor.Flags`
//      （`room_descriptor_layout.hpp:73`，bit0 = `FLAG_CLEAR`）。
//   2. `Room::IsBeastRoom()`：`ldr x8,[x0,#0x8]` 之后按 `[x8,#0x10]` 走
//      （`RoomDescriptor.Data`，布局表 `:43`）。
//   3. `Room::GetFrameCount` / `Room` 内嵌 `EntityList`（`+0x1950`）等既有字段都在这 8 字节之后
//      ⇒ 头 8 字节是一个指针成员，不是内嵌对象。
// ★ 注意 `Room + 0x8` 与 `Room + 0x30`（网格实体表）、`Room + 0x1950`（EntityList）**不是**同族：
//   这一格是"回指描述符"，所以 `Room:IsClear()` 要**两级**解引用（先 Room → 描述符，再描述符 → 标志）。
inline constexpr uintptr_t kRoomDescriptorPointerOffset = 0x8;
// ============================================================================
// 批次 290（2026-10-02）：`Room:GetRoomShape()` —— 形状住在**房间配置对象**里
// ============================================================================
//
// **为什么不能像批次 289 那样"一跳直读"**：形状不在 `Room` 上，而在
// `Room` → `RoomDescriptor` → `RoomConfig::Room` 这条**两跳指针链**的末端。
// PC 的 `Room:GetRoomShape @ 0x444C30` 本体就是这条链（`tools/pc_exe_binding.py GetRoomShape --disasm`）：
//     444c30  mov  eax, [ecx + 0x4]   ; ① 描述符（PC 在 `Room+0x4`；Switch 在 `Room+0x8`）
//     444c33  test eax, eax
//     444c35  je   0x444c42
//     444c37  mov  eax, [eax + 0x10]  ; ② 配置对象（`RoomDescriptor.Data`）
//     444c3a  test eax, eax
//     444c3c  je   0x444c42
//     444c3e  mov  eax, [eax + 0x48]  ; ③ 形状（PC 在 `Data+0x48`；**Switch 在 `Data+0x5C`**）
//     444c41  ret
//     444c42  mov  eax, 0x1           ; ★ 两跳任一为空 ⇒ 答 1（= `ROOMSHAPE_1x1`）
//
// **Switch 侧有三条独立读者**（函数名即语义，都是"逐字同形"的两跳 + 同一个形状区间）：
//   1. `Room::IsLShapedRoom() const @ 0x48453C` —— 整个函数只有 28 字节：
//        `ldr x8,[x0,#0x8]` → `ldr x8,[x8,#0x10]` → `ldr w8,[x8,#0x5c]` → `sub w8,w8,#0x9`
//        → `cmp w8,#0x4` → `cset w0,lo` → `ret`  ⇒ 真值当且仅当形状 ∈ **9..12**。
//      而 9..12 正好是 `RoomShape` 的四个 L 形（`ROOMSHAPE_LTL/LTR/LBL/LBR`；本项目自己的
//      枚举表 `runtime/source/program/doc_lua_enum_data.cpp` 逐值如此）⇒ 这两跳 + 这一格就是形状。
//   2. `Room::GetLRoomAreaDesc() const @ 0x484558` —— 同一条两跳（0x484590 读同一格），
//      取到后 `sub w9,w8,#0x9 / cmp w9,#0x3 / b.hi`（越界直接走非 L 形分支），命中则用
//      `add x10, x9, x8, lsl #5`（32 字节一项）索引一张静态表算 L 形房间的分区描述。
//   3. `Room::Init(RoomConfig::Room const*, RoomDescriptor*) @ 0x45F974` —— 同一条两跳之后
//      `ldr w8,[x8,#0x5c]` + `sub w8,w8,#0x9 / cmp w8,#0x3 / b.hi` 特判 L 形房间。
// 三条都写进布局表 `tools/layout_tables/room_descriptor.json` 的 `Data.Shape` 行，
// `python3 tools/build_layout_table.py --table tools/layout_tables/room_descriptor.json --verify`
// 会重新反汇编逐条核对（本批实测：15 行 / 38 条证据全部通过）。
//
// **★ 为什么不搬 PC 的偏移**：PC 用 `Data+0x48`、Switch 用 `Data+0x5C`；PC 的描述符在
// `Room+0x4`、Switch 在 `Room+0x8`。理由与批次 269/289 同一条 —— 32 位与 64 位构建的成员
// 布局不同（指针 4 vs 8 字节），**只能取 Switch 自己那群读者的偏移**。
//
// **★ 为什么这个常量从 `remaining_api.cpp` 挪到这里**：它原先只是那个文件里文件级的
// `constexpr`（供 `RoomDescriptor.Data.Shape` 的字段表用）。现在它同时是**对外 API 的字段偏移**，
// 而 `runtime/tests/test_field_api_rows.py` 只承认 `runtime_constants.hpp` 里的具名常量
// （同一个值在两处各写一遍迟早漂移）。语义、证据与偏移三者不变，只是换了住处。
inline constexpr uintptr_t kRoomConfigShapeOffset = 0x5C;
// ============================================================================
// 批次 327（2026-10-03）：`Room:IsDoorSlotAllowed(DoorSlot)` —— `RoomConfig::Room.Doors`
// ============================================================================
//
// PC 契约 `tools/pc_contract_docs/Room.md:655`（原文逐字）：
//   `#### boolean IsDoorSlotAllowed ( [DoorSlot](enums/DoorSlot.md) Slot )`
//   "Returns whether or not the supplied door slot is valid for the current room. This is
//    contingent on the room definition in the STB/XML file. (Basement Renovator displays
//    valid doors as brown and invalid doors as white.) The value returned by this method is
//    **independent of whether or not a door currently exists** at the given slot."
// ⇒ 语义 = **房间定义（XML）里这一个门位合不合法**，与"门此刻在不在"无关。
//
// PC 绑定函数本体（`tools/pc_exe_binding.py IsDoorSlotAllowed --disasm`，VA `0x58BFD0`，逐字）：
//     mov  edx, ecx                 ; edx = this(Room)
//     mov  ecx, [ebp+0x8]           ; ecx = Slot
//     lea  eax, [ecx+1] ; cmp eax,8 ; ja 0x58c002   ; ★ 只接受 Slot ∈ -1..7，其余答 false
//     mov  eax, [edx+0x4]           ; Room + 0x4 = 描述符（PC 的 RoomDescriptor* 偏移）
//     and  ecx, 0x1f ; shr esi, 5
//     mov  edx, [eax+0x10]          ; 描述符 + 0x10 = Data（RoomConfig::Room*）
//     mov  eax, 1 ; shl eax, cl
//     test dword ptr [edx + 4*esi + 0x38], eax  ; ★ 测位数组的第 Slot 位
//     setne al ; ret 0x4
// ⇒ PC 读的是 **`RoomConfig::Room` 里那一格**（PC 在 `Data+0x38`）。
// 那一格的正式名字与语义在 PC 文档快照里写得很直白 ——
// `analysis/isaacdocs-snapshot/docs/RoomConfig_Room.md:29`：
//   `#### const int Doors` —— "Returns a bit mask of the positions of valid door positions in
//    this room. It is a combination of bit flags of the DoorSlotFlag enum:
//    LEFT0 = 1 << DoorSlot.LEFT0, UP0 = 1 << DoorSlot.UP0, RIGHT0 = 1 << DoorSlot.RIGHT0,
//    DOWN0 = 1 << DoorSlot.DOWN0, LEFT1 = 1 << DoorSlot.LEFT1, UP1 = 1 << DoorSlot.UP1,
//    RIGHT1 = 1 << DoorSlot.RIGHT1, DOWN1 = 1 << DoorSlot.DOWN1}"
// ⇒ **第 Slot 位 = 这一个门位是否合法**，与 `IsDoorSlotAllowed` 逐字对上（位号 0..7）。
// ★ 别与 `RoomDescriptor.AllowedDoors`（PC 文档 `RoomDescriptor.md:21`，类型 `DoorSet`，
//   注文 "Contains data swapped just on load (in cases like minibosses, or other such events)"）
//   混为一谈 —— 那是**运行时**那一份（Switch 在描述符 `+0x20`，由 `Level::precalc_allowed_doors`
//   现算），与契约里"与门此刻在不在无关"这句正好相反。
//
// Switch 侧：这一格在 **`Data + 0x40`**（PC 是 `+0x38` —— 同一结构体两平台的偏移不同，
// 与同表的 `Data.Shape`（PC `+0x48` / Switch `+0x5C`）处境一样，**不许平移 PC 的偏移**）。
// 四条独立证据（扫描器 `analysis/api-restore-room-doorslot/scan_twohop.py` 按
// "两跳指针链 + 立即数"扫出来，逐条经 `tools/nro_disasm.py` 复核）：
//   1. `Level::precalc_allowed_doors(RoomDescriptor&) @ 0x3D6660`：`0x3D6A08 ldr x9,[x20,#0x10]`
//      （`x20` = 描述符 ⇒ `x9` = `Data`）→ `0x3D6A14 ldr x9,[x9,#0x40]` → `0x3D6A18 tst x9,x8`
//      （`x8 = 1 << 门位`，门位在 `0x3D6A0C lsl x8,x12,x24` 里由 `x24`(0..7) 生成）
//      ⇒ 引擎自己就是"拿房间配置的门位掩码按门位逐位测"，**与 PC 的读法逐字同形**。
//   2. `Level::get_room_neighbor_pos(int, eDoorSlot) @ 0x3D8228`：`0x3D824C ldr x9,[x0,#0x10]`
//      （`x0` = 描述符，`Level::GetRoomByIdx` 的返回值）→ `0x3D8254 ldr x8,[x9,#0x40]` →
//      `0x3D8258 lsr x8,x8,x19`（`x19` = 门位）→ `0x3D825C tbz w8,#0x0` ⇒ **函数名即语义**
//      （"按门位取邻居位置"）：掩码第 门位 位没置 ⇒ 这间房的配置里那个方向没有门。
//      `x9` 真的是 `Data` 有旁证：同函数 `0x3D8288 ldr w11,[x9,#0x5c]` 读的正是本表已确认的 `Data.Shape`。
//   3. `Room::TrySpawnSecretExitEbb(bool,bool)`（函数体在 `0x464D00` 一带）：`0x464D30 ldr x8,[x20,#0x8]`
//      （描述符）→ `0x464D40 ldr x9,[x8,#0x10]`（`Data`）→ `0x464D44 ldr x9,[x9,#0x40]` →
//      `0x464D48 tst x9,x10`（`x10 = 1 << 门位`，门位是 `0x464D28 mov w1,#0x8` 之后
//      `RNG::Random(8)` 抽的）；**通过之后**才在 `0x464D60 ldr x11,[x8,#0x20]`（描述符 `+0x20`
//      = 运行时 `AllowedDoors`）再测同一门位。⇒ 这一步把两格的**先后关系**写死了：
//      `Data+0x40` = "配置允许"，`描述符+0x20` = "运行时允许"。契约那句 "contingent on the room
//      definition ... independent of whether a door exists" 指的就是前者。
//   4. `Level::get_target_slot(int, eDirection, bool)` / `Level::MakeRedRoomDoor(int, eDoorSlot)` /
//      `Room::TrySpawnDevilRoomDoorEbb` / `Room::TrySpawnBossRushDoorEbb` / `Room::TrySpawnBlueWombDoorEbb` /
//      `Room::check_player_enter_door()` 等十余处门逻辑，用的都是同一条两跳 + `1 << 门位` 的读法
//      （扫描输出见 `analysis/api-restore-room-doorslot/`）。
// ★ `Data+0x40` 在引擎里是**按 64 位读**的（`ldr x`，不是 `ldr w`）⇒ 字段行 `offset2`（元素宽度）取 **8**；
//   位号就是 `DoorSlot` 本身（0..7 落在低 8 位里）。
// ★ 布局表 `tools/layout_tables/room_descriptor.json` 的 `Data.Doors` 行（本批新加，`confirmed`）
//   记的就是这条证据链；生成物是 `runtime/source/room_descriptor_layout.hpp` 里的
//   `layout::kRoomDescriptorDataDoorsOffset`。
// ★ 越界口径（与 PC 的差异，字段行那一行的注释里也写了）：PC 的护栏是
//   `(unsigned)(Slot+1) > 8 ⇒ false`（即 -1..7 放行）；我们沿用 `FieldKind::BoolBitArrayOfArg`
//   既有的"负位号 → 降级"口径 ⇒ 契约域 0..7 内与 PC 逐位一致。
inline constexpr uintptr_t kRoomConfigDoorsOffset = 0x40;
// ============================================================================
// 批次 291（2026-10-02）：`Room` 的四个只读状态量
// （`GetBossID` / `IsFirstVisit` / `IsAmbushDone` / `HasWaterPits`）
// ============================================================================
//
// **这一批的共同点**：四条在引擎里都**没有同名访问器**（Switch 构建里连符号都没有）
// ⇒ 走字段读取型数据行（`remaining_api.cpp` 的 `kRoomFieldApis`），0 字节代码。
// 语义靠"**谁消费了这个值**"锚定：每条都给两条以上互相独立的**具名消费者**
// （函数名即语义），不是"某处有个字节"。
//
// ── ① `Room:GetBossID()` —— `Room + 0x1FC0` ──────────────────────────────
//
// PC 契约 `tools/pc_contract_docs/Room.md:109`：
//   `#### int GetBossID ( )`
//   "Returns the boss ID of the **first boss** in the room. Returns 0 otherwise."
//   "A boss ID is **NOT** equal to the entity Type, but is defined as a separate value
//    in the entities2.xml file inside the 'bossID' attribute."
// PC 绑定函数本体（`tools/pc_exe_binding.py GetBossID --disasm`，VA `0x430D60`）：
//     `mov eax, dword ptr [ecx + 0x1d1c]; ret`  ⇒ 一跳直读 `Room + 0x1D1C`。
//
// Switch 侧三条独立互证（偏移是 **0x1FC0**，不是 PC 那个 —— 32/64 位布局不同，**不能搬**）：
//   1. `Room::Init(RoomConfig::Room const*, RoomDescriptor*)` @ `0x45C6A0`..`0x45C6C4`：
//      对房间里每个生成实体取它的 `EntityConfig`（`EntityConfig::GetEntity(type,variant,subtype)`），
//      读 `EntityConfig::Entity + 0x34`（= entities2.xml 的 `bossID` 属性）；
//      **第一个非零**的写进 `Room + 0x1FC0`（`0x45C6C4 str w8,[x19,#0x1fc0]`），
//      **第二个不同的**写进 `+0x1FC4`（`0x45C6BC str w8,[x19,#0x1fc4]`）
//      ⇒ 与契约"the **first** boss in the room"逐字吻合。
//   2. `RoomTransition::change_room()` @ `0x499674`：`ldr w1,[x0,#0x1fc0]` 当作
//      `RoomTransition::StartBossIntro(eBossId, eBossId)` 的**第 1 个实参**
//      （第 2 个实参来自 `+0x1FC4`，`0x499690`）—— 契约里"这个值用来决定进房时显示的
//      Boss 头像"说的就是它。
//   3. `Room::PlayMusic()` @ `0x451948`：`ldr w8,[x19,#0x1fc0]` → `sub w8,w8,#0x6` →
//      `cmp w8,#0x52` → `b.hi`（**取值区间 6..0x58 = 6..88**）→ 索引一张静态表挑 Boss 曲子。
//      这个区间与语料里模组比对的那几个 Boss id 逐条落在里面
//      （`boss_id == 6 / 8 / 24 / 55 / 62 / 63 / 88`，见 `MusicModCallback`、
//       `MinimapAPI`、`Enhanced-Boss-Bars` 的调用点）。
// ⇒ 语义（first boss id）、来源（entities2.xml 的 bossID）、消费者（Boss 入场与音乐）三头对上。
// ★ 引擎里**没有**同名方法，也没有 `get_boss_id` 这类改名版本
// （全符号表子串扫描 + `tools/mangled_impl_count.py` 都是 0 命中）⇒ 只能直读字段。
inline constexpr uintptr_t kRoomBossIdOffset = 0x1FC0;

// ── ② `Room:IsFirstVisit()` —— `Room + 0x1` 的**一个字节** ──────────────────
//
// PC 绑定函数本体（`tools/pc_exe_binding.py IsFirstVisit --disasm`，VA `0x638F90`）：
//     `mov al, byte ptr [ecx + 0x1]; ret`  ⇒ 一跳直读 `Room + 0x1` 的**字节**。
// PC 契约 `tools/pc_contract_docs/Room.md:670` 只有签名、没有散文 ⇒ 语义由 Switch 侧的
// **三条具名读者**定（都落在 `Room` 自己的函数里，`x19`/`x0` 就是 `Room*`）：
//   1. `Room::Init(RoomConfig::Room const*, RoomDescriptor*)` @ `0x45CCBC`..`0x45CCD8`：
//        `ldr w8,[x20,#0x4c]`（= 描述符的 `VisitedCount`）→ `cbz w8` → `mov w8,#1` →
//        `strb w8,[x19,#0x1]` ⇒ **"访问次数还是 0" 才把这个字节置 1** = "第一次进这间房"。
//   2. `Room::RespawnEnemies()` @ `0x488B00`..`0x488B28`：先把描述符 `+0x4C`（`VisitedCount`）
//        **加一**（`add w9,w9,#1` / `str w9,[x8,#0x4c]`），紧接着 `strb wzr,[x19,#0x1]` 把它**清零**
//        ⇒ 再次进房时它不再为真，与 `VisitedCount` 是同一条时间线。
//   3. `Room::PlayMusic()` @ `0x451E9C`：`ldrb w8,[x19,#0x1]` → 只有非零时才 `Random(4)` 抽曲子
//        ⇒ 引擎自己按"是不是首次"分支。
// ★ 与 `RoomDescriptor.VisitedCount`（描述符 `+0x4C`，布局表 confirmed）**不是同一格**：
//   这一格在 `Room` 对象上、是**字节**；那一格在描述符上、是 4 字节**计数**。
//   拿 `VisitedCount != 0` 去模拟会答错（PC 读的就是这一格）。
// ★ 为什么 `Room + 0x1` 在 64 位构建里位置不变：`Room` 头 8 字节之后才是描述符指针
//   （`kRoomDescriptorPointerOffset`），PC 是 `+0x4`、Switch 是 `+0x8`（多出来的 4 字节是对齐），
//   而 `+0x00..+0x03` 两版一致 ⇒ 前 4 字节里的这个字节两版同一个位置。
//   （交叉核对：PC 的 `TopLeft` 在 `Room+0x14`、Switch 在 `+0x1C`，差值正好是"两个指针各宽 4 字节"。）
inline constexpr uintptr_t kRoomFirstVisitOffset = 0x1;

// ── ③④ `Room:IsAmbushDone()` / `Room:HasWaterPits()` —— 描述符 `Flags` 的 bit3 / bit5 ──
//
// 契约：`tools/pc_contract_docs/Room.md:639`（`#### boolean IsAmbushDone ( )`）与
// `Room.md:622`（`#### boolean HasWaterPits ( )`）—— 两页都只有签名、没有散文，
// 所以语义同样靠"谁消费了这一位"定。
//
// 这两个位**已经**登记在布局表 `tools/layout_tables/room_descriptor.json` 的 `Flags` 行里。
// 那一行的语义表来自 PC 文档快照 `RoomDescriptor.md:101`：低六位依次是
// `FLAG_CLEAR`=bit0 / `PRESSURE_PLATES_TRIGGERED`=bit1 / `SACRIFICE_DONE`=bit2 /
// `CHALLENGE_DONE`=bit3 / `SURPRISE_MINIBOSS`=bit4 / `HAS_WATER`=bit5。
//
// PC 侧**三条绑定函数本体**把这三个位逐个钉死（`tools/pc_exe_binding.py <名字> --disasm`）：
//   * `Room:IsClear      @ 0x427700`：`mov eax,[ecx+0x4]`（描述符）→ `mov al,[eax+0x44]`
//     → `and al,1`      ⇒ **bit0**（与批次 207 已落地的判据一致）。
//   * `Room:IsAmbushDone @ 0x6DCE00`：同一条链 → `mov eax,[eax+0x44]` → `shr eax,3`
//     → `and al,1`      ⇒ **bit3**。
//   * `Room:HasWaterPits @ 0x4F3EC0`：同一条链 → `shr eax,5` → `and al,1` ⇒ **bit5**。
//   （PC 上这个位掩码在描述符 `+0x44`，Switch 上在 `+0x50` —— 又是一个"同名不同偏移"。）
//
// Switch 侧四条独立具名读者（偏移 `+0x50`；前两条锚 bit3，后两条锚 bit5）：
//   * `Ambush::StartChallenge()` @ `0x406C`..`0x408C`：
//       `g_Game` → `Game` → `[Game+0x21550]`（`Room*`）→ `[Room+0x8]`（描述符）→
//       `ldrb w8,[x8,#0x50]` → `tbnz w8,#0x3` → **置着就直接 `ret`**（不再开始这场伏击）
//       ⇒ bit3 = "这间房的伏击/挑战已经做过了" = `IsAmbushDone()`。
//   * `Level::CanOpenChallengeRoom(int) const` @ `0x3E6C48`..`0x3E6C50`：同一条链 →
//       `ldrb w9,[x0,#0x50]` → `tbnz w9,#0x3` ⇒ bit3 = `CHALLENGE_DONE`（挑战房是否已开过）。
//   * `Room::pre_render_pits()` @ `0x47F03C`..`0x47F048`：`ldr x8,[x0,#0x8]`（描述符）→
//       `ldrb w8,[x8,#0x50]` → `tbz w8,#0x5` → 位没置就**不渲染水坑**。
//   * `Room::pre_render_water()` @ `0x47F6C0`..`0x47F6C8`：逐字同形（同一个 bit5 判据）。
//   另有 `Room::Update` / `Room::Render` / `Room::ComputeColorModifier` / `Room::update_ambient_sounds`
//   各自单独测 bit5（复现工具：`tools/nro_find_bit_readers.py 0x50`）。
//   ★ **别拿 `Room::HasWater()`（`0x487FA0`）当锚点**：那条读的是 `Room + 0x7894` 的
//     **水位浮点数**（`fcmp s0,#0.0` / `cset w0,gt`），与"这间房的坑里有没有水"不是一回事
//     （一个是画面水位、一个是房间标志位）。
//
// ★ **为什么这个常量要写进本头文件**：数据行的 `offset` **只认**本文件里的具名常量
//   （`runtime/tests/test_field_api_rows.py::test_offsets_are_named_constants_not_magic_numbers`），
//   而布局表那一份在**生成物** `room_descriptor_layout.hpp` 的 `layout::` 命名空间里
//   （`layout::kRoomDescriptorFlagsOffset` / `layout::kRoomDescriptorClearOffset`）。
//   两者同名同值，`remaining_api.cpp` 里有一条 `static_assert` 钉住它们不许漂移。
inline constexpr uintptr_t kRoomDescriptorFlagsOffset = 0x50;

// ============================================================================
// 批次 292（2026-10-02）：`Room` 的**背景类型**（`Room:GetBackdropType()`）
// ============================================================================
//
// 契约 `tools/pc_contract_docs/Room.md:103`：
//   `#### [BackdropType](enums/BackdropType.md) GetBackdropType ( )`
//   "Returns the BackdropType of the current room."
// PC 绑定函数本体（`tools/pc_exe_binding.py GetBackdropType --disasm`，VA `0x4BAEA0`）：
//     `mov eax, dword ptr [ecx + 0x1e84]; ret`   ⇒ 一跳直读成员、原样返回。
//
// ★★★ **Switch 侧的偏移为什么是 `Room+0x21B0`（而不是 PC 那个 `0x1E84`）**——
// 这一格其实是**内嵌的 `Backdrop` 子对象里的字段**，两条独立证据把它钉死：
//   1. **内嵌关系**（`Room::LoadBackdropGraphics @ 0x45ABF8`）：
//        `mov w9, #0x1fe0` → `add x21, x20, x9`  ⇒ `Backdrop` 子对象 = **`Room + 0x1FE0`**；
//      紧接着 0x45AC14 拿 `x21` 当 `this` 调 `Backdrop::Init`。
//   2. **写入方**（`Backdrop::Init(Backdrop::eBackdrop, bool) @ 0x26E80`）：
//        `0x26E9C  cmp  w1, #0x3c      ; 60 = DARK_CLOSET（最后一个真背景）`
//        `0x26EA4  csinc w8, w1, wzr, ls  ; > 60 一律夹成 0（= BACKDROP_NULL）`
//        `0x26EA8  str  w8, [x0, #0x1d0]  ; ★ eBackdrop ∈ Backdrop+0x1D0`
//      ⇒ `0x1FE0 + 0x1D0 = 0x21B0`（两个偏移都在上面逐条给出，**不是位移推的**）。
//
// **Switch 侧具名读者**（`--fn Room` 过滤后 48 处命中，分布在 14 个 `Room` 成员函数里；
// 下面四个的函数名本身就说明了这一格是什么）：
//   * `Room::LoadBackdropGraphics()` @ `0x45AE1C`（装载背景图）；
//   * `Room::HasLava() const` @ `0x461F90`（整个函数就是"读这一格 + 比若干值"，函数名即语义）；
//   * `Room::init_rain()` @ `0x4646A8`（按背景决定起不起雨）；
//   * `Room::pre_render_pits()` @ `0x47F030`（先比这一格是不是矿层，再看 `Flags` bit5 画不画水坑）。
//
// **取值锚点（两条，都落在 `BackdropType` 的合法域 0..60 内）**：
//   * `Room::pre_render_pits @ 0x47F034` 的 `cmp w8, #0x20` ⇒ 0x20 = 32 = `BackdropType.MINES`；
//   * `Room::Init @ 0x45CC90` 的 `cmp w8, #0x10` ⇒ 0x10 = 16 = `BackdropType.DARKROOM`
//     （紧邻还比了一个 `0x23` = 35 = `PLANETARIUM`）。
//   ★ 这两个数与 PC 文档枚举页 `tools/pc_enum_docs/BackdropType.md` **同值** —— 那张表本批
//     已经生成进运行时（`DocLuaEnumData`），所以模组拿返回值能与 `BackdropType.*` 直接比
//     （这正是本批"同一件事的两半"，与批次 269 的 `RenderMode` + `Room:GetRenderMode()` 同形）。
//
// ★ 与 `Music+0x1D0`（`Music::Crossfade` / `EnableLayer` 读写的那一格）**同偏移、不同基对象**
//   —— 引用这一格时**必须带基对象说清**（本项目里"同名偏移落在不同基对象上"的先例：
//   `Room+0x50` vs 描述符 `+0x50`、`Room+0x1D1C` vs `Entity_Player+0x1D1C`）。
//   本批读的是 `Room` 上那一格，与 `Music` 无关。
inline constexpr uintptr_t kRoomBackdropTypeOffset = 0x21B0;

// ============================================================================
// 批次 302（2026-10-03）：`Room:SetFloorColor` / `SetWallColor`（各 9 处 = 18 处）
//   —— `Room` 上**两个相邻的 `ColorMod`**（各 44 字节，相距 `0x2C`）
// ============================================================================
//
// ★★★ **PC 侧的标尺**（`tools/pc_exe_binding.py SetFloorColor --disasm`，绑定本体各只有 12 条指令，
//   两条**逐字同形**、只有那个立即数不同）：
//
//     00427800？不是 —— 实际 VA：
//     SetFloorColor @ 0x7A7ED0：`add ecx, 0x7188`  → 把 **44 字节**（`ret 0x2c`）的实参整块拷进去
//       7a7ed3  add  ecx, 0x7188
//       7a7ee0  movups xmm0, [ebp+0x8]   / 7a7ee7 movups [ecx], xmm0
//       7a7eea  movups xmm0, [ebp+0x18]  / 7a7eee movups [ecx+0x10], xmm0
//       7a7ef2  movq   xmm0, [ebp+0x28]  / 7a7ef7 movq   [ecx+0x20], xmm0
//       7a7efc  mov    [ecx+0x28], eax   （`eax = [ebp+0x30]`）
//     SetWallColor  @ 0x7A7F10：**同一段代码**，只是 `add ecx, 0x71b4`
//   ⇒ PC 的 `_floorColorMod` 在 **`+0x7188`**、`_wallColorMod` 在 **`+0x71B4`**，
//     **相距 `0x2C` = 一个 `ColorMod`**，顺序是**地板在前、墙在后**。
//     ★ 那个 44 字节的实参就是 `ColorMod`（见下面 `kColorModSize` 的取证）。
//
// ★★★ **Switch 侧：三份互相独立的证据指向同一对格（顺序与间距都与 PC 一致）**
//
//   ① **具名写入方（构造函数就把它当 `ColorMod` 初始化）** —— `Room::Room() @ 0x44E740`：
//        0044e75c  mov  w8, #0x7968          ; ← 地板那一格
//        0044e760  add  x0, x19, x8
//        0044e764  bl   ColorMod::Reset      ; ★ 用引擎自己的 `ColorMod::Reset()` 初始化它
//        0044e768  mov  w8, #0x7994          ; ← 墙那一格
//        0044e76c  add  x0, x19, x8
//        0044e770  bl   ColorMod::Reset      ; ★ 同一条 `Reset`
//      ⇒ 这两格**就是 `ColorMod` 成员**（不然不会拿 `ColorMod::Reset` 来初始化）；
//        `0x7994 - 0x7968 = 0x2C` = 一个 `ColorMod` ⇒ 与 PC 的**间距和顺序都一致**。
//        同一段还给 `Room+0x7918/0x7928/0x7938/0x7948`（各 0x10 的 `Color`）调了 `Color` 的构造函数
//        —— 那五个是**水/光**语义（读者只有 `Room::FadeWaterColor`，批次 295/300 已排除），与本批无关。
//
//   ② **具名读者 = 真的把颜色画出去的那条链**（这正是"最强判据"要求的那条调用链）：
//        `Room::Render @ 0x48035C..0x48039C`：把 `Room+0x7968` 起 **44 字节**逐段搬到一个栈上临时量
//          （`ldr x8,[x19,#0x7968]` / `ldr x9,[x19,#0x7970]` → `stp [x29,#-0x88]`；
//           `+0x7978`/`+0x7980` → `[x29,#-0x78]`；`+0x7988` → `[x29,#-0x68]`；`+0x7990` → `[x29,#-0x60]`）
//          然后 `bl Backdrop::RenderFloor(Vector2 const&, ColorMod)`（桩 `0x67EDA0`）
//        `Room::Render @ 0x480564..0x480598`：同一形态，源是 **`Room+0x7994`**，目标是
//          `bl Backdrop::RenderWalls(Vector2 const&, ColorMod)`（桩 `0x67EDC0`）
//      ⇒ **地板那一格喂给 `RenderFloor`、墙那一格喂给 `RenderWalls`**，一一对应、没有第三种解释。
//        （两条读者都只是**原样搬 44 字节**，不掺任何计算 ⇒ 写进去什么，画出来就是什么。）
//
//   ③ **引擎自己的"改墙色"入口**：`Room::TurnGold @ 0x464AB0` 往 **`Room+0x7994`** 写一整份
//      `ColorMod`（`add x10, x19, x10(=0x7994)` + 两条 `stp`）—— 房间变金是把**墙**染金的，
//      与"`0x7994` = 墙色"独立吻合。
//
// ★ **取值锚点**（布局表 `confirmed` 需要的那一条）：`ColorMod::Reset @ 0x37830` 本体
//     00037830  mov x8, #0x3f8000003f800000   ; 两个 1.0f
//     00037834  stp x8,  x8,  [x0]            ; tint = (1,1,1,1) ← `+0x00`
//     00037840  stp xzr, xzr, [x0, #0x10]     ; shift = (0,0,0,0) ← `+0x10`
//     00037838  str xzr, [x0, #0x20]          ; ← `+0x20`
//     0003783c  str wzr, [x0, #0x28]          ; ← `+0x28`（共 44 字节）
//   ⇒ 布局 = 4 个 float 的 tint（乘）+ 4 个 float 的 shift（加）+ 3 格保留，
//     与我们的 `EngineColorMod`（`engine_color_mod.hpp`，`sizeof == kColorModSize`）**逐格一致**。
//
// ★ **不许平移**：PC `0x7188`/`0x71B4`、Switch `0x7968`/`0x7994` —— 数值完全不同（布局差异），
//   只有"相距 0x2C + 地板在前"这一对**相对关系**可以互相印证。
// ★ **接收者**：语料 18 处全是 `Game():GetRoom():SetFloorColor(...)` 形态
//   （逐个调用点核过 `room` 的来源，**全是当前房间**）⇒ 用既有的 `FieldReceipt::Room`
//   （解析"当前房间"，不从栈上取）—— 与批次 289/290/291/295 的 `Room` 族同一口径。
// ★ 取证命令：`python3 tools/nro_disasm.py 0x44E740 0x40`（构造）/ `0x48035C 0x60`（地板读者）
//             `0x480564 0x40`（墙读者）/ `0x37830 0x18`（`ColorMod::Reset`）
//             `python3 tools/pc_exe_binding.py SetFloorColor --disasm`
inline constexpr uintptr_t kRoomFloorColorModOffset = 0x7968;  // ColorMod（44 字节）
inline constexpr uintptr_t kRoomWallColorModOffset = 0x7994;   // ColorMod（44 字节）

// ============================================================================
// 批次 303（2026-10-03）：**虚函数的 vtable 槽号**（"按槽号调用"那套机制的数据面）
// ============================================================================
//
// 背景：`Entity:CanShutDoors()` / `EntityNPC:CanShutDoors()` / `GridEntity:Destroy(bool)` /
// `GridEntity:PostInit()` 这几条**不是普通引擎方法** —— 它们是**虚函数**：
// PC 的绑定本体不调某一个具体函数，而是 `mov eax,[ecx]; jmp [eax+偏移]`。
// PC 镜像里有一整张这样的跳板表（**`0x8604E0` 起**，每条 3~5 字节）：
//
//     8604ee  mov eax,[ecx] / 8604f0 jmp [eax+0x30]     ; 槽 12
//     86050c  mov eax,[ecx] / 86050e jmp [eax+0x18]     ; 槽 6   ← GridEntity::Destroy 那一档
//     86051b  mov eax,[ecx] / 86051d jmp [eax+0x48]     ; 槽 18  ← CanShutDoors 那一档
//   （同表附近的名字表里出现 `CanShutDoors` / `IsBoss` / `IsInvincible` / `IsVisible` / `IsDead`
//     —— 全是实体上的判定方法；`IsBoss` 也是虚的，与下面对得上。）
//
// ★★★ **槽号怎么从 Switch 镜像读出来（取证手法，值得复用）**：
//   1. `_ZTV<类>`（vtable）在**文件里全是 0**，靠 RELA **在加载时才填**；
//      但槽位**不是** `R_AARCH64_RELATIVE`，而是 **`R_AARCH64_ABS64`(257) + 符号索引**！
//      （实测：`Entity` vtable `0xA34F48` 附近 18 条重定位全是 type 257、带 sym。）
//      ⇒ 读法：对该 vtable 的每一格 `vtable + 0x10 + i*8`，去 RELA 表里找那条 type=257 的记录，
//      用它的**符号索引**查 dynsym 拿名字（`fromelf`/`objdump` 看不到这一层）。
//      ★ 别被 `R_AARCH64_RELATIVE` 带偏：`nro_symbols.parse_dynamic_relocations()` 按导入符号名
//      分组、**把 sym==0 的 RELATIVE 全跳过**，而 vtable 用的是带符号的那种。
//   2. **Itanium ABI 布局**：`vtable[0] = offset-to-top`、`vtable[1] = typeinfo`（`_ZTI<类>`，
//      实测它在 `+0x08`）。★★★ **"槽 0"相对 `_ZTV<类>` 这个符号是 `+0x10`，但对象首字存的
//      就是 `_ZTV + 0x10`（= 槽 0 自己的地址）⇒ 运行时按"对象首字 + 槽号*8"读，不再加 0x10。**
//      三条独立证据：`_ZTVEntity`(`0xA34F48`)+0x10 = `kEntityVtableRangeBeginOffset`(`0xA34F58`)；
//      `_ZTVEntity_NPC`(`0xA35DA8`)+0x10 = `kEntityNpcVtableOffset`(`0xA35DB8`)；
//      `_ZTVGridEntity`(`0xA37880`)+0x10 = `kGridEntityVtableOffset`(`0xA37890`)。
//      ★ 另有代码侧印证：`IsEntityPlayer()` 判的是 `*(u64*)candidate == base + kEntityPlayerVtableOffset`
//        —— 拿**对象首字**与那个常量**直接相等**比较。
//      ★★ 批次 303 的第一版在运行时多加了 `0x10`（读成"槽号 + 2"），**批次 304 修正**；
//        当时宿主用例没发现，因为夹具引用了机制自己的那个常量、两边一起漂。
//   3. 校验办法：同一个虚函数在**基类与派生类里占同一个槽号**（实测：`Entity::CanShutDoors`
//      在 `_ZTVEntity` 的槽 18、`Entity_NPC::CanShutDoors` 在 `_ZTVEntity_NPC` 的**同一个槽 18**）
//      ⇒ 槽号稳定，按槽调用就等价于虚派发。
//
// ★★★ **不许照抄 PC 的槽号**：两边的 vtable 布局**差一个析构槽** ——
//   Itanium（Switch）在开头放**两个**析构变体（实测 `Entity` 槽 0 = `D2`、槽 1 = `D0`），
//   MSVC（PC）只放**一个** `scalar deleting destructor` ⇒ **PC 的槽号通常比 Switch 小 1**。
//   实测：`CanShutDoors` PC 是第 17 条（`jmp [eax+0x44]`）、Switch 是第 **18** 条（`+0x90`）。
//   ⇒ 槽号只能从 **Switch 的 `_ZTV`** 读，PC 那边只用来判"它是不是虚函数"。
//
// ★ 取证命令（本机，无需上卡）：
//     python3 tools/nro_disasm.py 0x48035C 0x60        # 读某处代码（示例）
//     python3 analysis/api-restore-302/dump_vtable.py  # 本批新写的 vtable dumper（见该脚本头部）
//
// 本批用到的槽号（**已实现**的只有第 1 条；其余两条的槽号一并记下来，等有 `GridEntity` 接收者
// 的批次直接用 —— 它们**没有** Consumers 之外的不确定性）：
//   * `Entity` / `Entity_NPC` 的 `CanShutDoors()`（const bool）  → **槽 18**（`_ZTVEntity` @ `0xA34F48`）
//   * `GridEntity` 的 `PostInit()`（void）                      → **槽 2**（`_ZTVGridEntity` @ `0xA37880`）
//   * `GridEntity` 的 `Destroy(bool)`（bool）                   → **槽 6**（同上）
//     （`GridEntity` 的槽 3/4 是 `__cxa_pure_virtual` —— 纯虚，派生类必须覆盖。）
inline constexpr std::uint32_t kEntityVtableCanShutDoorsSlot = 18;

// --- 批次 304（2026-10-03）：`GridEntity` 的两个槽号（本批实现的两条虚函数）----------------
// 与上面同一套读法（`_ZTVGridEntity` @ `0xA37880`，对象首字 = `+0x10` = `0xA37890`）：
//   * `GridEntity::PostInit()`（void）        → 槽 **2**（`0xA37890 + 2*8 = 0xA378A0`）
//   * `GridEntity::Destroy(bool)`（bool）     → 槽 **6**（`0xA37890 + 6*8 = 0xA378C0`）
// 自证：`GridEntity` 的槽 3/4 是 `__cxa_pure_virtual`（纯虚，派生类必须覆盖），
//      而槽 2/6 在派生类里被逐类覆盖（`GridEntity_Door`/`_Rock`/`_Statue`/`_TNT`/`_Web` 各有自己的
//      `Destroy`）⇒ 这两个槽号在整棵树上一致（虚函数的定义）。
// ★★ **不许照抄 PC 的槽号**：PC 侧 `Destroy` 是第 **5** 条（`jmp [eax+0x18]` 那张表里
//   `0x86050c`）、`PostInit` 更靠前 —— 与 Switch 差一个析构槽（Itanium 两个析构变体 / MSVC 一个）。
inline constexpr std::uint32_t kGridEntityVtablePostInitSlot = 2;

// --- 批次 319（2026-10-03）：**修正批 238 四条 `Entity` API 的调用方式**（直调 → 虚调用）------
//
// ★★★ 本批发现的是一类**此前没人查过的错**：批 238 把 28 条 API 一次性落成"引擎方法数据行"，
//   分层依据只有"形状与接收者都现成"，**没有核过"PC 那条绑定是不是虚调用"**。而其中四条是虚的：
//
//   | API | PC 绑定 | 跳板表里的偏移 | PC 序号 | **Switch 槽号** |
//   | --- | --- | --- | --- | --- |
//   | `Entity:Update()`  | `0x860520` | `jmp [eax+0xc]`  | 3  | **4** |
//   | `Entity:Kill()`    | `0x8604FD` | `jmp [eax+0x24]` | 9  | **10** |
//   | `Entity:Remove()`  | `0x860511` | `jmp [eax+0x28]` | 10 | **11** |
//   | `Entity:IsBoss()`  | `0x86051B` | `jmp [eax+0x48]` | 18 | **19** |
//
//   判据（本项目自己的"判法四档"第 ③ 档）：**PC 绑定落在 `0x8604E0` 起那张
//   `mov eax,[ecx]; jmp [eax+偏移]` 跳板表里 ⇒ 它是虚函数**。四条都落在那张表里，
//   而同批的 `Entity:IsEnemy`（`0x684620`）不在 ⇒ 直调是对的。**同批只有这四条要改。**
//
//   ★ 换算关系（与批 303 的实测一致）：**PC 序号 = Switch 槽号 − 1**（Itanium 放两个析构变体、
//     MSVC 放一个）。四条逐条核对：第 3/9/10/18 条 ↔ 槽 4/10/11/19，**全部吻合**。
//   ★ 复核命令（本机、离线）：
//       python3 tools/nro_vtable_slot.py Entity --find Update   # → slot 4
//       python3 tools/nro_vtable_slot.py --find-all Kill       # → 整棵树都在 slot 10
//
// ★★ **为什么必须改**：直调基类会**跳过子类的实现** ——
//   `Update` 在**每一个** `Entity` 派生类里都被覆盖（`Entity_Player`/`Entity_NPC`/`Entity_Tear`…），
//   `Kill` 有 `Entity_Familiar::Kill` 与 `Entity_NPC::Kill` 两份覆盖、
//   `Remove` 有 `Entity_Familiar::Remove` / `Entity_Pickup::Remove`、
//   `IsBoss` 有 `Entity_NPC::IsBoss`。
//   ⇒ 改之前 `player:Update()` 跑的是**基类**的更新（真机上"手动更新实体"会做一半的事）。
//   这与批 304 修 `GridEntity:Destroy` 是同一个道理，只是那批修的是"新写的行"、本批修的是"已上线的行"。
//
// ★ 槽号的读法见上面批 303/304 两段（vtable 在文件里全是 0，靠 `R_AARCH64_ABS64`(257) + 符号索引填）。
//   ★ 本批起有工具：`tools/nro_vtable_slot.py`（批 318 固化，`--find` / `--find-all` / `--list`）。
inline constexpr std::uint32_t kEntityVtableUpdateSlot = 4;
inline constexpr std::uint32_t kEntityVtableKillSlot = 10;
inline constexpr std::uint32_t kEntityVtableRemoveSlot = 11;
inline constexpr std::uint32_t kEntityVtableIsBossSlot = 19;

// --- 批次 305（2026-10-03）：`Music` 的"启用"字节（`MusicManager:Disable/Enable/IsEnabled`）------
// `Music` 对象 = `Manager + kManagerMusicOffset`（**内嵌**，批次 239 已取证）—— 本批这一格
// 相对 **`Music`** 算。
//
// ★★★ **PC 侧的三个绑定紧挨着、语义毫无歧义**（`tools/pc_exe_binding.py <名字> --disasm`）：
//     7fac20  mov byte ptr [ecx + 0x328], 0x1   ; ★ `MusicManager:Enable()`
//     7fac30  mov byte ptr [ecx + 0x328], 0x0   ; ★ `MusicManager:Disable()`
//     7fac40  mov al, byte ptr [ecx + 0x328]    ; ★ `MusicManager:IsEnabled()`
//   ⇒ PC 上是 `Music + 0x328` 的**一个字节**：1 = 启用、0 = 停用（PC `0x328` **不许平移**）。
//
// ★★★ **Switch 侧两条独立证据指向同一格、且语义同向**：
//   ① **具名写入方 = 构造函数**（`Music::Music() @ 0x423FBC`）：
//        0042400c  mov  w8, #0x1
//        00424018  strb w8, [x19, #0x3f0]      ; ★ 默认 **1 = 启用**（与 PC 一致）
//        00424024  strb wzr, [x19, #0x428]     ; 旁边另一格清 0（不是本格）
//      ⇒ 它是 `Music` 的成员，且初值与 PC 的"默认启用"一致。
//   ② **具名消费者 = `Music::Update() @ 0x426C58` 的闸**：
//        00426c7c  ldrb w8, [x0, #0x3f0]       ; x0 = this = Music
//        00426c88  cbnz w8, 0x426c9c            ; ★ 非 0（启用）⇒ 去更新音乐；为 0 ⇒ 再看 Game 状态
//      ⇒ "非 0 才更新"与 PC 的 `Enable ⇒ 1` 同向。
//   ★ 取证命令：`python3 tools/nro_disasm.py 0x423FBC 0xC8`（构造）与 `0x426C58 0x70`（Update）。
//   ★ 顺带提醒：全镜像扫 `ldrb [xN, #0x3F0]` 会命中 18 处，**绝大多数是 `Entity_Player + 0x3F0`**
//     （另一棵树上的同偏移）⇒ 按偏移扫必须**按最近符号归属**再人工判基对象（本项目既有盲点）。
inline constexpr uintptr_t kMusicEnabledOffset = 0x3F0;   // u8：1 = 启用、0 = 停用

inline constexpr std::uint32_t kGridEntityVtableDestroySlot = 6;

// --- 批次 321（2026-10-03）：`GridEntity:Update()`（1 处）的槽号 -------------------------------
// 与上面批 304 同一套读法（`_ZTVGridEntity` @ `0xA37880`，对象首字 = `+0x10`）：
//   * `GridEntity::Update()`（void）  → 槽 **3**
// ★★★ **自证（这一条比 304 那两条还硬）**：**基类 `_ZTVGridEntity` 的槽 3 就是
//   `__cxa_pure_virtual`（纯虚）**，而 `GridEntity_Door`/`_Rock`/`_Statue`/`_TNT`/`_Web`/`_Pit`/
//   `_Fire`/`_Lock`/`_Poop`/`_Wall`/`_Spikes`/`_Stairs`/`_Gravity`/`_TrapDoor`/`_Decoration`/
//   `_Teleporter`/`_PressurePlate` … 这些派生类**每一个**都在槽 3 放自己的 `Update`
//   ⇒ 「基类纯虚 + 派生类逐类覆盖」正是虚函数的定义，而且**不存在**"某个派生类忘了覆盖 ⇒
//   落到基类"的情形（基类那份根本不可调用）。★ 复核：`nro_vtable_slot.py GridEntity --find Update`
//   + `--find-all Update`（能看到几十个派生类都在槽 3）。
// ★ PC 侧同一条规律：名表里 `Update` 有多个登记项，其中一条指向跳板表 **`0x860507`** =
//   `mov eax,[ecx]; jmp [eax+0x8]` ⇒ PC 序号 **2** ⇒ Switch 槽 **3**（PC 序号 = Switch 槽号 − 1）。
//   （另一条指向 `0x860520` = 序号 3 = `Entity::Update` 的槽 4 —— 两条互不影响，别混。）
// ★ 接收者沿用批 304 的 `FieldReceipt::GridEntity`（栈上那个句柄），形状沿用 `Void0`
//   ⇒ **没有新接收者、没有新形状、0 字节代码**。
inline constexpr std::uint32_t kGridEntityVtableUpdateSlot = 3;

// ============================================================================
// 批次 293（2026-10-03）：`Entity` 的**三个相邻状态字节**
//   （`IsVisible` / `Exists` / `IsDead` —— 共 32 处调用点）
// ============================================================================
//
// ★★★ **PC 侧的标尺：三个字节也是相邻的**（`tools/pc_exe_binding.py <名字> --disasm`）：
//     `Entity:IsVisible @ 0x412360` = `mov al, byte ptr [ecx + 0x169]; ret`
//     `Entity:Exists    @ 0x412340` = `mov al, byte ptr [ecx + 0x16A]; ret`
//     `Entity:IsDead    @ 0x412350` = `mov al, byte ptr [ecx + 0x16B]; ret`
//   ⇒ PC 上是 `visible / exists / dead` 连着三个字节（顺序本身就是一条交叉证据）。
//
// **Switch 侧的三格**（`Entity + 0x1C1 / 0x1C2 / 0x1C3`，**顺序与 PC 一致**）——
// 三格各自都有**具名消费者**，不是靠"照 PC 平移"：
//
// ① `Entity + 0x1C1` = `IsVisible`
//      * `Entity::Render` @ `0x062514`：`ldrb w8,[x0,#0x1c1]` + 0x6251C `cbz w8, →函数尾`
//        ⇒ 为 0 时**整个实体不画**；
//      * `EntityList::RenderShadows` @ `0x078210`（不可见的连影子都不画）；
//      * `Camera::get_enemy_target` @ `0x032BBC`（摄像机不锁定看不见的敌人）；
//      * **写入方** `Entity_Effect::Init` @ `0x0800A4`：`strb wzr,[x19,#0x1c1]`（新建 Effect 初始不可见）。
//
// ② `Entity + 0x1C2` = `Exists`
//      * `EntityList::Update` @ `0x076848`：`ldrb w8,[x22,#0x1c2]` + `cbnz w8, →继续处理`
//        （为 0 就跳过）⇒ 这一位就是"还算不算实体表的一员"；
//      * **写入方** `Entity::Remove()` @ `0x05D3E4`：`strb wzr,[x0,#0x1c2]`；
//      * 构造函数 `Entity::Entity()` @ `0x0588E8` 把它清零（新实体还没进表）；
//      * 析构 `Entity::~Entity` @ `0x0589DC` 也读它（0x0589EC 再清零）。
//    ★ 契约散文（`Entity.md:322`）逐字对上：
//      "Checks whether the entity is still spawned in the current room."
//
// ③ `Entity + 0x1C3` = `IsDead`
//      ★★ **决定性**：`Entity::Kill()` @ `0x05C8E8`..`0x05C934` 的函数体是
//         `ldrb w8,[x0,#0x1c3]` → `cbnz`（**已经置着就直接返回**，幂等）
//         → `mov w8,#1`（0x5C8F4）→ `strb w8,[x0,#0x1c3]`（0x5C8F8）
//         → 取虚表槽 `[x8,#0x98]` 调用 → 类型不是 3 就**尾调用 `Entity::BloodExplode()`**（0x5C934）。
//      而契约散文（`Entity.md:502`）写着 `Kills the entity and makes a blood splat or gibs.`
//      ⇒ "置 1 = 标记已死"这条对应关系由**函数体 + 契约散文两头对上**，不是猜的。
//      * 第二处独立读者：`Entity::IsVulnerableEnemy` @ `0x05C650`（死掉的实体不再是可伤害的敌人）；
//      * `Entity::BloodExplode` @ `0x05D380`；`Entity::Remove` @ `0x05D3E0` 读它、
//        并在"还没死"时置 1（0x05D3F4）—— 与 ② 那一格构成一对
//        （**"实体离开实体表时，如果它还没死就把它标记成死了"**，同一段代码在析构函数里逐字重复）。
//      * ★★★ **写侧（批次 315 补的）**：`Entity:Die()` 就是"把这一格写成 1" ——
//        PC 侧两条绑定**逐字对上**：`IsDead @ 0x412350` = `movb 0x16b(%ecx),%al; ret`（读）、
//        `Die @ 0x436B60` = `movb $0x1, 0x16b(%ecx); ret`（**写同一格**）⇒ PC 上这两条 API
//        是"同一格的两侧"、各自只有两条指令 ⇒ `Die` 是**纯字段写**（不需要引擎函数）。
//        ★★ 又一条交叉印证：PC 的 `IsVisible @ 0x412360` 读 `+0x169`，与 `+0x16B` **相隔 2**；
//        Switch 的 `+0x1C1`(可见) 与 `+0x1C3`(已死) **同样相隔 2**（中间是 `+0x1C2` = `Exists`）。
//        ★ **口径**：只写这一格（PC `Die` 逐字照做）；Switch 的 `Entity::Kill()` 额外立刻
//        调虚表槽并可能 `BloodExplode`，**不复刻那一步**（PC 也没做）。
//        ⇒ 也正因为这条，**"dynsym 里 0 个实现"不等于"做不了"**：0 实现只说明 Switch 侧
//        没有同名函数（内联进去了），**字段本身一直在**（这条教训记在交接与技能里）。
//
// ★★★ **为什么这三条能直接走字段行**：它们的接收者是 Lua 栈上的**实体句柄**
//   （`FieldReceipt::Entity`，批次 002 起就有），**不需要新接收者、不需要新 kind**
//   —— 三条各 16 字节只读、0 字节代码。
// ★ **降级档一律 `False`**（看不见 / 不在表里 / 没死）：三者都按"读到 0 的口径"答，
//   与 PC 上"读到 0"同值；而"句柄无效"时答 false 也不会让模组对幽灵句柄动手
//   （模组侧的典型写法是 `if not e:Exists() then return end` 或 `if e:IsDead() then ...`）。
inline constexpr uintptr_t kEntityVisibleOffset = 0x1C1;
inline constexpr uintptr_t kEntityExistsOffset = 0x1C2;
inline constexpr uintptr_t kEntityIsDeadOffset = 0x1C3;

// ============================================================================
// 批次 294（2026-10-03）：`Level` 的**两个房间列表索引**
//   （`Level:GetPreviousRoomIndex()` 2 处 + `Level:GetLastBossRoomListIndex()` 1 处）
// ============================================================================
//
// ★★★ **`Level` 的房间索引在引擎里成"对"存放**，两个对都已经被 Named 读者钉住：
//
//   * `Level + 0x21558` = **当前**房间索引（本项目早已有 `kLevelCurrentRoomIndexOffset`）
//     配 `Level + 0x21560` = 该索引对应的**维度**（`kLevelCurrentRoomDimensionOffset`）；
//   * `Level + 0x2155C` = **上一个**房间索引（**本批**），配 `Level + 0x21564` = 它的维度。
//     ★ 证据是 `Level::GetLastRoomDesc()` 的整个函数体（`0x3DC69C`..`0x3DC6B0`）：
//         `mov  w8, #0x155c` + `movk w8, #0x2, lsl #16` + `add x8, x0, x8`
//         → `ldr w1, [x8]`      ← **第一个实参 = 索引**
//         → `ldr w2, [x8, #0x8]` ← 第二个实参 = 维度（= `+0x21564`）
//         → `b Level::GetRoomByIdx(int, int)`
//       与"当前房间"那一对（`Level::GetCurrentRoomDesc` 读 `+0x21558` / `+0x21560`）**逐字同形**。
//     另有三个 `Room::TrySpawn*Door` 在读它（函数名即语义）：
//       `TrySpawnDevilRoomDoor @ 0x465AB4`、`TrySpawnBossRushDoor @ 0x466C48`、
//       `TrySpawnBlueWombDoor @ 0x472130`
//       —— 恶魔房 / Boss Rush 门 / 蓝子宫门都只在「刚从 Boss 房出来」时才可能开。
//
//   * `Level + 0x21568` = **本层最后一个 Boss 房**的房间列表索引（**本批**）。
//     ★★ 最硬的证据是 `Room::IsCurrentRoomLastBoss()`（`0x464430`..`0x464470`）：
//         `ldr w1, [Game+0x21558]`（**当前**房间索引）+ `w2 = -1` → `Level::GetRoomByIdx`
//         拿到当前房间描述符 → `ldr w8, [x0, #0x8]`（描述符自己的**列表索引**）
//         → 与 `Level+0x21568`（`mov w10,#0x1568` + `movk w10,#0x2`）比较
//       ⇒ 这一格装的必然是「另一个房间的列表索引」，而这个函数问的正是
//         「当前房间是不是最后一个 Boss 房」 ⇒ 语义与 PC 的 `GetLastBossRoomListIndex` 对上。
//     ★ 另有六个具名读者：`Level::ShowBossRoom @ 0x3E7128`（在地图上标出 Boss 房）、
//       `Level::CanSpawnDevilRoom @ 0x3E7A14`（恶魔房只在打完最后一个 Boss 房后才可能出现）、
//       `Room::TriggerBossDeath @ 0x46A1CC`、`StageTransition::Update @ 0x4A614C`、
//       `Level::RestoreGameState @ 0x3E51EC`、`Level::GetLocalStageType @ 0x3D0588`。
//
// ★ **PC 侧的标尺**（`tools/pc_exe_binding.py <名字> --disasm`）：
//     `Level:GetPreviousRoomIndex @ 0x59FEC0`     = `mov eax, [ecx + 0x18198]; ret`
//     `Level:GetLastBossRoomListIndex @ 0x4C0530` = `mov eax, [ecx + 0x181A4]; ret`
//   —— 两条都是"一跳直读成员"，而且 PC 那边**也是相邻的一簇**
//   （`0x18198` / `0x181A4`，间隔 `0xC`；Switch 侧 `0x2155C` / `0x21568` 同样间隔 `0xC`）。
//   ★ 偏移两边不同（PC 32 位、Switch 64 位），**不许平移** —— 本批的偏移全部由 Switch 侧读者定。
//
// ★ 语义位置说明：`Level` 内嵌在 `Game` **起始处**（同一地址）⇒ 这两格同时是 `Game` 的字段，
//   布局表里登记在 `game.json`（`struct: Game`）的 `PreviousRoomIndex` / `LastBossRoomListIndex`
//   两行（`--verify` 会重新反汇编逐条核对）；生成常量名带 `Game` 前缀，与本文件这两个名字
//   由 `remaining_api.cpp` 里的 `static_assert` 钉在一起。
inline constexpr uintptr_t kLevelPreviousRoomIndexOffset = 0x2155C;
inline constexpr uintptr_t kLevelLastBossRoomListIndexOffset = 0x21568;

// ============================================================================
// 批次 295（2026-10-03）：房间的**两个种子**
//   （`Room:GetDecorationSeed()` 8 处 + `Room:GetSpawnSeed()` 8 处）
// ============================================================================
//
// ★★ **PC 侧的标尺**（`tools/pc_exe_binding.py <名字> --disasm`）—— 两条都读描述符，
//    而且都**先查空指针**：
//     `Room:GetDecorationSeed @ 0x4977F0`：
//        `mov eax,[ecx+0x4]`（描述符）→ `test eax,eax` → **`jne` 才继续**（为空直接 `ret`，eax 还是 0）
//        → `mov eax,[eax+0x58]` ⇒ **PC 在 `descriptor+0x58`**
//     `Room:GetSpawnSeed @ 0x4276D0`：同样的形状 → `mov eax,[eax+0x5C]` ⇒ **PC 在 `descriptor+0x5C`**
//   ★ 两句一起给出**降级值 0**（描述符为空时 PC 就是返回 0）—— 本批因此用 `FieldMissing::Zero`，
//     不是"我们选的保守值"，而是**照 PC 抄的**。
//   ★ PC 那边两格是相邻的（0x58 / 0x5C），**装饰在前、出怪在后**。
//
// **Switch 侧的两格**（`descriptor + 0x64` / `+0x68`）—— 同样相邻、同样"装饰在前"：
//
// ① `descriptor + 0x64` = `DecorationSeed`
//    ★★★ 最硬的证据：`Room::LoadBackdropGraphics`（`0x45ABEC` / `0x45ABF4` / `0x45AC04` 三条）：
//        0x45ABEC  `ldr  x8, [x20, #0x8]`    ; x8 = Room 的**描述符**
//        0x45ABF4  `ldr  w1, [x8, #0x64]`    ; ★ 这一格
//        0x45ABF8  `add  x21, x20, #0x1FE0`  ; Backdrop 子对象
//        0x45AC04  `bl   Backdrop::SetSeed`  ; ★★ 把它当**背景对象**的种子
//      ⇒ 基址在同一段里就定死了（不是"某个 0x64"），而"喂给 Backdrop 的种子"就是装饰种子的定义。
//    * 第二/三处读者：`Room::Init @ 0x45CCDC`（`RNG(seed, 35)`）与 `@ 0x45CBD4`（`RNG(seed, 6)`）
//      —— 同一函数里还读 `[x20,#0x50]`/`[x20,#0x51]` = 描述符的 `Flags` ⇒ x20 就是描述符。
//    * `GameState::write_Room @ 0x3689A0` 把它**序列化**进存档 ⇒ 它必须持久。
//
// ② `descriptor + 0x68` = `SpawnSeed`
//    * `Room::Init @ 0x45CFB0`：`ldr w1,[x8,#0x68]` + `mov w2,#0x11`（用途 17）建 RNG，紧接着
//      `bl Game::IsHardMode()`，**按硬核与否决定抽 1 次还是 2 次**，再 `RNG::Next` +
//      `Room::GetRandomTileIndex` 挑一个房间内随机下标存进房间字段（`+0xE90`）
//      ⇒ 「硬核模式影响抽签次数」本身就是**出怪侧**的语义证据（硬核改变出怪）。
//    * 同一函数 `@ 0x45D280` 又一次拿它当种子（用途 61）。
//    * `GameState::write_Room @ 0x3689D4` 也在**会存档的字段表**里（与装饰种子相邻的两条 `ldr`）。
//
// ★ **为什么 Switch 换到了 0x64/0x68（而不是 PC 的 0x58/0x5C）**：Switch 描述符的布局不同。
//   旁证：`GameState::write_Room` 序列化的 u32 偏移是
//   `0x0 / 0x4 / 0x8 / 0xC / 0x48 / 0x4C / 0x50 / 0x58 / 0x60 / 0x64 / 0x68 / 0x6C / 0x70`
//   —— **`0x5C` 不在里面**（PC 的 SpawnSeed 在 0x5C，若 Switch 也照搬，读档后出怪就会变），
//   而 `0x64`/`0x68` 都在 ⇒ 两个种子都能持久 ✓。**偏移绝不许从 PC 平移。**
//
// ★ 两条数据行的接收者是既有的 `FieldReceipt::RoomDescriptor`（当前房间 → `Room+0x8` 一跳），
//   种类 `I32`（PC 的绑定是 `mov eax,…` + 契约写 `int` ⇒ 与 PC 的有符号口径一致）、
//   降级 `Zero`（照 PC 的"描述符为空返回 0"）。
inline constexpr uintptr_t kRoomDescriptorDecorationSeedOffset = 0x64;
inline constexpr uintptr_t kRoomDescriptorSpawnSeedOffset = 0x68;
// `Room + 0x30` = **网格实体表**（按网格下标索引，每项 8 字节的 `GridEntity*`）。
// 证据（2026-09-16）：`Room::SpawnGridEntity(int index, eGridEntityType type, u32, u32, int) @ 0x452528`
// 里 `add x8, x0, w1, uxtw #3; ldr x8, [x8, #0x30]` —— 就是用网格下标取这一族的指针；
// 同处还看到 `ldr w0, [x8, #0x40]`（`GridEntity + 0x40` 参与碰撞判定）。
inline constexpr uintptr_t kRoomGridEntityTableOffset = 0x30;

// --- 批次 310 做、**批次 311 修正归属**：房间里两个「活着的数量」计数对 ---------------------
//
// ★★★ **先看 PC 上「谁是谁」**：这两条 API 在 `isaac-ng.exe` 里是**紧邻的孪生函数**，
//   读的是**相邻的两对格子**、尾巴一模一样（`add` + `test` + **`cmovg`** + `ret`）：
//
//      Room:GetAliveEnemiesCount @ 0x448000 :  mov edx,[ecx+0x12C4] / mov ecx,[ecx+0x12C0]
//      Room:GetAliveBossesCount  @ 0x448020 :  mov edx,[ecx+0x12CC] / mov ecx,[ecx+0x12C8]
//
//   ⇒ **敌人对 = `0x12C0`/`0x12C4`；Boss 对 = `0x12C8`/`0x12CC`**（`+0x20` 之差、同一个模板）。
//   ★★ **批次 310 把这两条的归属搞反了**（只看了 `0x448020` 那一段、没核 `0x448000`）：
//      它把「敌人对」当成 Boss ⇒ 模组调 `GetAliveBossesCount()` 会拿到**敌人**数。
//      批次 311 修正常量指向、并补上 `GetAliveEnemiesCount()`。
//      ★ 教训：**两条 API 名字相近时，必须逐个核各自的绑定 VA**（这次只差 `0x20`，一眼扫过就张冠李戴）。
//
// ★★★ **Switch 侧对应哪一对**（三处独立证据，互相印证）：
//
//   ① **具名函数**（最硬的一条）：`Entity_NPC::get_alive_enemy_count() @ 0x122768`
//      （`_ZNK15IsaacRepentance10Entity_NPC21get_alive_enemy_countEv` 是镜像里**唯一**一个
//      `alive_*` 符号）读的就是 **`Room + 0x1A58`/`+0x1A5C`**：
//        00122778  adrp x8, 0xaac000 ; ldr x8, [x8, #0x698]   ; g_Game
//        00122780  ldr  x8, [x8]
//        00122784  mov  w9, #0x1550 ; movk w9, #0x2, lsl #16  ; ★ 0x21550
//        0012278c  ldr  x20, [x8, x9]                          ; ★ x20 = *(Game+0x21550) = **Room***
//        00122798  ldr  w8,  [x20, #0x1a5c]                    ; ★ 第 2 格
//        0012279c  ldr  w9,  [x20, #0x1a58]                    ; ★ 第 1 格
//        001227a0  add  w8, w9, w8
//        001227a4  bic  w19, w8, w8, asr #31                   ; ★ `w8 & ~(w8>>31)` = **负数清成 0**
//      ⇒ **函数名自己说的**：`+0x1A58` 那一对是**敌人**（与 PC 的敌人对 `0x12C0` 同在「第一对」）。
//
//   ② ★★★ **两条公式并列出现**（`0x1447C4` 起，某处 AI/判定代码）—— **这是归属的分水岭**：
//        ldr w9, [x8, #0x1a5c] / ldr w10, [x8, #0x1a58] → add → **bic w9,w9,w9,asr#31**  ; 敌人（夹下限）
//        ldr w10,[x8, #0x1a64] / ldr w8,  [x8, #0x1a60] → add → **bic w8,w8,w8,asr#31**  ; Boss（夹下限）
//        sub  w20, w9, w8                                                              ; ★ 敌人 − Boss
//      ⇒ **`+0x1A60` 那一对是 Boss**；而且**两条用的是同一个夹下限口径**（与 PC 逐句同义）。
//
//   ③ **顺序与间距**（印证，不是主证据）：Switch 两对相距 `8`（`0x1A58`→`0x1A60`），
//      PC 两对也相距 `8`（`0x12C0`→`0x12C8`）⇒ 相对顺序一致。
//
//   ④ 另有多处**成对读 `0x1A60`/`0x1A64` 再 `cmp … #0` / `b.gt`** 的代码（如 `0x117364`，
//      以及 `Ambush::Update` 的 `0x4FFC`：**先判敌人对、再判 Boss 对**）—— 与「两个独立计数」一致。
//
// ★ 每对只登记**第一格**：第二格永远紧邻在 `+4`（PC 同样是 `0x12C0`/`0x12C4` 这种相邻对，
//   与 `Level` 那几个房间索引的"成对存放"同一形态）—— 相邻本身就是一条证据。
inline constexpr uintptr_t kRoomAliveEnemiesCountOffset = 0x1A58;
inline constexpr uintptr_t kRoomAliveBossesCountOffset = 0x1A60;
// ============================================================================
// 门族（批次 078，2026-09-19）：`Room:GetDoor(slot)` 及其字段
// ============================================================================
//
// 为什么现在做：`Room:GetDoor` 长期是"恒返回 nil"的降级（批次 046），而 GoodTrip 的
// **连通图完全建立在它之上**（`floor.sweep_doors()` → `floor.linked()` → `rules.check_teleble()`）。
// 它返回 nil 时我们只能靠临时钉子 `AllowAnyRoom = true` 让传送能用 —— 那个钉子的副作用就是
// **能传送到没去过的房间**（用户实测反馈）。把门族做实，钉子才能撤掉。
//
// 取门路线（证据：`Room::GetDoorSlotPosition(eDoorSlot) const @ 0x464B8C` 的前 20 条指令）：
//   `11000428 add w8, w1, #1 ; cmp w8, #9 ; b.lo`  ⇒ 槽位合法范围 **-1..7**
//   `8b21c808 add x8, x0, w1, sxtw #2 ; b94e7108 ldr w8, [x8, #0xe70]`
//     ⇒ **每个槽位的门在"网格下标"就存在 `Room + 0xE70 + slot*4`**（有符号）
//   `b9401409 ldr w9, [x0, #0x14]`（= 房间网格宽度）后 `sdiv/msub` 把线性的网格下标拆成 行/列
//   ⇒ 再用 `Room + 0x30` 的网格实体表取 `GridEntity_Door*`（那条表是老证据）
//: 门槽位 → 网格下标的数组基址（`Room::GetDoorSlotPosition` 用的就是它）。
inline constexpr uintptr_t kRoomDoorGridIndexTableOffset = 0xE70;
//: **门槽位 → `GridEntity_Door*`**（0..7 直接索引）—— `Room:GetDoor(slot)` 走这一张，
//: 比"先取网格下标、再查网格实体表"短一步。证据：`Room::make_door(eDoorSlot) @ 0x454EE4`
//: `add x22,x0,w1,sxtw #3; ldr x8,[x22,#0xe30]`（判重）与末尾 `str x20,[x22]`（存门）；
//: `Room::TriggerRedRoomDoorCreated` 用 `0xE30/0xE38/0xE40` 对应 `make_door(0/1/2)`，
//: `TrySpawnTheVoidDoor` 用 `make_door(5)` 即 `0xE58` ✓。
inline constexpr uintptr_t kRoomDoorObjectTableOffset = 0xE30;
//: 门自己也记着自己的槽位（`Room::make_door` 的 `0x454FF4 str w19,[x20,#0x1a0]`）。
inline constexpr uintptr_t kGridEntityDoorSlotOffset = 0x1A0;
//: `GridEntity_Door + 0x30C` = **`TargetRoomIndex`**（门通向哪个房间，按 `Level` 描述符下标）。
//: 证据（四条独立）：`InitSubclass @ 0x385F98` 初始化成 -1；
//: `Update @ 0x38175C` 读它后 `bl Level::GetRoomByIdx(int,int)`；`SetRoomTypes @ 0x385A78` 同形；
//: 写入方 `Room::TriggerRedRoomDoorCreated @ 0x48BE74` 把描述符的 `+0x04`（该房下标）`str` 进门的 `+0x30C`。
//: 也与 GoodTrip `floor.lua:225` 的 `GetRoomByIdx(door.TargetRoomIndex, -1)` 逐字同形。
inline constexpr uintptr_t kGridEntityDoorTargetRoomIndexOffset = 0x30C;
//: 槽位的合法范围（`GetDoorSlotPosition` 里 `w1 + 1 < 9` ⇒ -1..7）。
inline constexpr std::int32_t kRoomDoorSlotMinimum = -1;
inline constexpr std::int32_t kRoomDoorSlotMaximum = 7;
//: `Room + 0x14` = 房间**网格宽度**（`GetDoorSlotPosition` 用它把线性下标拆成行/列）。
//: **2026-09-20（批次 098）第二条独立证据**：`Room::GetGridPath(int,int) @ 0x484120` 与
//: `Room::GetGridIndex(int,int) @ 0x45a264` 的第一件事都是 `ldr w9,[x0,#0x14]` → `cmp w9,w1`
//: （第一个参数的上限），随后 `madd w9, w9, w2, w1` 即 `index = W*y + x` —— 同一格既当宽度用
//: 又当线性下标里的步长用，两处互相印证。
inline constexpr uintptr_t kRoomGridWidthOffset = 0x14;
//: `Room + 0x18` = 房间**网格高度**（int32）。以前记的是"未定位"，批次 098 由上面那两条
//: 函数的第二条边界 `ldr w10,[x0,#0x18]` → `cmp w10,w2` 定位（第二个参数的上限）。
//: 标准房间是 13 宽 × 7 高（引擎 `GetGridIndex(Vector)` 的 y 偏移 −120 = −3 格，
//: 正是"房间在 13×13 网格里偏下 3 格"的来处），**具体数字以真机读数为准，代码里不写死**。
inline constexpr uintptr_t kRoomGridHeightOffset = 0x18;
//: `Room + 0xE98` = 网格的**通行代价数组**（每个格子 int32，共 `W*H` 格，下标 `W*y + x`）。
//: 证据：`Room::GetGridPath(int,int) @ 0x484120` 的尾部
//: `add x8, x8, w9, uxtw #2` → `ldr w0, [x8, #0xe98]`（`x8` 是 `this`），
//: 越界（参数为负、或 `>= W/H`、或算出的下标为负）时该函数一律返回 **0**。
//: 语义（PC 文档 `Room.md` 的 `GetGridPath`）：0 = 最可走，数值越大越不优先，
//: **> 900 = 不可走**（900 是敌人走过留下的降优先值，950 是火，石头/坑更高）。
inline constexpr uintptr_t kRoomGridPathArrayOffset = 0xE98;
//: 世界坐标 → 格坐标的换算常量，取自 `Room::GetGridIndex(Vector2 const&) @ 0x459e3c`：
//:   `gx = (int)((pos.x − 40.0f) / 40.0f + 0.5f)`、`gy = (int)((pos.y − 120.0f) / 40.0f + 0.5f)`
//: 然后 `gx ∈ [0,W)`、`gy ∈ [0,H)` 才算合法，返回 **`W*gy + gx`**；越界返回 **−1**。
//: `(int)` 是 AArch64 `fcvtzs`（**向零截断**，所以 `pos=(0,0)` 得 `gx=0`、`gy=-2` ⇒ 越界）。
//: −40/−120 不是随手写的：−120 = 3 格，与"房间在 13×13 网格里偏下 3 格"这条已知事实吻合；
//: 于是格 k 的横向跨度是 `[40k+20, 40k+60)`、格心在 `40k+40`（标准房间左下格心即 (40,120)）。
//: ⚠️ 这两个常量是**先减后除**里的被减数（`pos − 常量`），别把符号写反 —— 写反时
//: `pos=(120,240)` 会算成格 (4,9)、直接越界成 −1，宿主门禁 `test_lua_room_grid` 会当场抓到。
inline constexpr float kRoomGridCellSize = 40.0F;
inline constexpr float kRoomGridWorldOffsetX = 40.0F;
inline constexpr float kRoomGridWorldOffsetY = 120.0F;
// ============================================================================
// 房间边界（批次 289，2026-10-02）：`Room:GetTopLeftPos()` / `GetBottomRightPos()`
// ============================================================================
//
// `Room + 0x1C` = 矩形**左上角**、`Room + 0x24` = 矩形**右下角**（各一个 `Vector2` =
// 两个 float，世界像素坐标；`0x20` 是左上的 Y、`0x28` 是右下的 Y）。
//
// 对外就是 PC 的 `Room:GetTopLeftPos()` / `GetBottomRightPos()`：PC 侧这两个方法本体就是
// **原样返回成员**（`0x432630 mov edx,[ecx+0x14]` / `0x432650 mov edx,[ecx+0x1c]`），
// 而 Switch 构建里**没有同名访问器**（`4Room` 的符号里搜不到 `TopLeft`/`BottomRight`/
// `GetBounds` 一类）⇒ 只能直读字段（走字段读取型数据行，见 `remaining_api.cpp` 的
// `kRoomFieldApis`）。
//
// ★ 为什么 PC 的偏移（`0x14/0x18` 与 `0x1C/0x20`）与这里**不能互相搬**：PC 是 **32 位**构建、
//   Switch 是 64 位 —— 指针成员宽度不同（PC 的描述符指针在 `Room+0x4`，Switch 在 `Room+0x8`），
//   且 Switch 在 `0x14/0x18` 放的是**网格宽高**（见上面的 `kRoomGridWidthOffset`）⇒
//   两侧偏移必须各自取证。
//
// 判据（四条独立互证，全部落在 Switch 侧；每条都能在布局表里重新反汇编核对）：
//   1. **写入方是具名函数** `Room::RecomputeRoomBounds(bool) @ 0x45B88C`（符号名即"重算房间边界"）：
//      `0x45B9EC add x21, x19, #0x1c` → `0x45B9FC Vector2::operator=` **先**写 `0x1C`；
//      随后 `0x45BA00 ldp w8, w9, [x19, #0x14]` 取网格宽高、`0x45BA04 sub w8, w8, #0x2` 得墙内跨度，
//      `0x45BA28 Vector2::operator+`（**被加数是 `&Room+0x1C`**）、`0x45BA30 add x20, x19, #0x24`
//      取第二格地址、`0x45BA40 Vector2::operator=` 把结果写进它
//      ⇒ **`0x24` = `0x1C` + 正的跨度** ⇒ `0x1C` 是左上、`0x24` 是右下。
//   2. `Room::Init @ 0x45EF08`（摆随机位置）用 `0x1C/0x20` 当**基点**、`0x24/0x28` 减 `0x1C/0x20`
//      得**正**跨度（`rand × 跨度 + 基点`）—— 同一结论，且证明这两格在进房间时**真的有值**。
//   3. `Room::IsPositionInRoom @ 0x464560`（矩形判定从 `0x4645BC` 起）：`0x1C/0x20` 是**加** Margin 的**下界**、
//      `0x24/0x28` 是**减** Margin 的**上界**；`Room::GetClampedPosition @ 0x48437C` 同样把
//      `0x1C/0x20` 当 `Vector2::Clamped` 的 min、`0x24/0x28` 当 max。
//   4. `Room::GetCenterPos @ 0x456250`（函数名即"房间中心"，PC 契约 `Room.md:139`；`Room::Update`
//      在 `0x46F5EC` 起**内联**了同一段）取这两格相减（被减数是 `&Room+0x24`）再乘 `0.5f`
//      加回 `0x1C` ⇒ 两格是**对角**、连线中点是房间中心。★ 与 PC 对齐的关键：PC 侧同名判定函数
//      `Room::IsPositionInRoom @ 0x7CF0A0` 对 `0x14/0x18`（= `GetTopLeftPos` 读的那一对）做
//      **加** Margin、对 `0x1C/0x20`（= `GetBottomRightPos` 读的那一对）做**减** Margin ——
//      与 Switch 侧 `0x1C` 加 / `0x24` 减 的**符号模式逐条相同**。
//
// 布局表：`tools/layout_tables/room.json` 的 `TopLeft` / `BottomRight` 两行（`confirmed`，
// 共 19 条证据，`python3 tools/build_layout_table.py --table tools/layout_tables/room.json
// --verify` 可整表复核）。常量名带 `Pos` 是为了与布局表的 `layout::kRoomTopLeftOffset`
// 区分（两处同值，布局表那份才是被 `--verify` 逐条核对的）。
inline constexpr uintptr_t kRoomTopLeftPosOffset = 0x1C;
inline constexpr uintptr_t kRoomBottomRightPosOffset = 0x24;
//: `Room::GetDoorSlotPosition(eDoorSlot) const`（返回 `XY`：两个 float 走 `s0`/`s1`；
//: 槽位非法时返回 `Vector2::Zero`）。用它取门的**世界坐标**（GoodTrip 的 `door.Position` 用得到）。
//: 入口首字 `d10083ff`（`sub sp, sp, #0x20`）。
inline constexpr uintptr_t kRoomGetDoorSlotPositionOffset = 0x464B8C;
inline constexpr std::uint32_t kRoomGetDoorSlotPositionEntryWord = 0xD10083FFu;
//: `GridEntity_Door` 的字段（证据：`GridEntity_Door::InitSubclass @ 0x385F98` 的存值序列
//: `str wzr,[x0,#0x1a4]` / `str x8,[x0,#0x1a8]`（x8 = -0x100000000 ⇒ 0x1A8=0、0x1AC=-1）/
//: `str wzr,[x0,#0x318]`；以及 `SetRoomTypes @ 0x385A78` 写 0x1A4/0x1A8、`SetDirection @ 0x385F7C`
//: 写 0x1AC、`IsTargetRoomArcade @ 0x386038` 读 0x1A8）。
inline constexpr uintptr_t kGridEntityDoorCurrentRoomTypeOffset = 0x1A4;
inline constexpr uintptr_t kGridEntityDoorTargetRoomTypeOffset = 0x1A8;
inline constexpr uintptr_t kGridEntityDoorDirectionOffset = 0x1AC;
//: 门自己的标志字（`Open()`/`CanEnter()` 读它的 bit4/bit5）。
inline constexpr uintptr_t kGridEntityDoorFlagsOffset = 0x318;
//: `GridEntity_Door::CanEnter() const`（`0x384FC8`）—— **"这扇门现在能不能过"的引擎判据**。
//:
//: 为什么用它实现 PC 的 `GridEntityDoor:IsOpen()`：PC 文档（`GridEntityDoor.md:56`）只给了
//: `boolean IsOpen()` 这一个签名、**没有语义说明**；而 GoodTrip 的用途是
//: `rules.lua` 的 `check_room_open()`（"这个房间还有没有能走的门"，用来判小 BOSS/挑战房是否算开），
//: 那正是"能不能过"这个语义。引擎自己这条函数就是它内部问同一个问题的判据，所以直接调它。
//:
//: 反汇编（`python3 tools/nro_disasm.py 0x384fc8 0x50`，共 6 条指令、叶函数）：
//:   `b9401009 ldr w9,[x0,#0x10]`（门对象的 variant）
//:   `7100093f cmp w9,#0x2` + `1a9f17e9 cset w9,eq`
//:   `394c6008 ldrb w8,[x0,#0x318]` + `121c0108 and w8,w8,#0x10`（标志字 bit4）
//:   `4a481120 eor w0, w9, w8, lsr #4` ⇒ **`CanEnter = (variant == 2) XOR bit4`**
//: 入口首字 = `b9401009`。
inline constexpr uintptr_t kGridEntityDoorCanEnterOffset = 0x384FC8;
inline constexpr std::uint32_t kGridEntityDoorCanEnterEntryWord = 0xB9401009u;
//: `Rect`（`XY` 的小表）用于把 `Room::GetDoorSlotPosition` 的返回值读回来。
struct RoomDoorPosition {
    float x;
    float y;
};
// `GridEntity + 0x08` = 类型（`eGridEntityType`）。
//
// ★ 2026-09-19 修正（批次 078，独立取证）：**旧结论 `+0x18` 是错的**。
//   * `Room::CreateGridEntity(eGridEntityType, unsigned gridIndex) @ 0x37FC50`：
//     `0x380084 str w20(类型实参),[x21,#0x8]` —— 类型直接落在 `+0x08`；
//   * `GridEntity::IsRock() @ 0x37FBEC` 读 `+0x08` 后 `sub w8,w8,#2; cmp #0x19` 查位集
//     `0x03D0001F`，解出来正好 {2,3,4,5,6,22,24,25,26,27}，与 PC `GridEntityType.md` 的岩石族逐项吻合；
//   * `+0x18` 是 `GridEntity::Init(unsigned)` 写的槽，而所有创建路径都给它 `RandomU32()`
//     （`make_door` 0x454FC4、`make_wall` 0x454E2C、`SpawnGridEntity` 第 4 实参）⇒ 它是**生成种子**。
//   * 结构对照：`GridEntity::Init(const Desc&)` 把 `Desc[0x00..0x1F]` 拷到对象 `+0x08..+0x27`
//     ⇒ 对象 `+0x08` = `Desc+0x00` = Type、`+0x10` = `Desc+0x08` = Variant、`+0x1C` = `Desc+0x14` = VarData。
inline constexpr uintptr_t kGridEntityTypeOffset = 0x08;
//: `GridEntity + 0x1C` = **`VarData`**（PC 的 `GridEntity.VarData`）。
//: 证据：`Room::SpawnGridEntity(int, eGridEntityType, unsigned, unsigned, int) @ 0x452528` 把第 5 个实参
//: 写进 `+0x1C`（`0x452634 str w20,[x24,#0x1c]`），而"活板门 `VarData = 1` ⇒ 虚空传送门"这条 PC 语义
//: 在引擎里对得上（`GridEntity_TrapDoor::InitSubclass @ 0x395F1C` 读 `+0x1C` 判 1 后换 `VoidTrapdoor.anm2`）。
//: 门的诅咒房标记也走它（`GridEntity_Door::Update` 在 `CURSE_OF_THE_CURSED` 分支读 `+0x1C`）。
inline constexpr uintptr_t kGridEntityVarDataOffset = 0x1C;
//: `GridEntity + 0x28` = **网格下标**（位置由引擎按格子算，不存 float）：
//: `GridEntity::GetPosition() @ 0x37E498` 读它后转调 `Room::GetGridPosition(int)`。
inline constexpr uintptr_t kGridEntityGridIndexOffset = 0x28;

// ---- 批次 276（2026-10-02）：`GridEntity` 子类的 vtable 偏移（7 条转换要用）----------------------
//
// 算法与 `Entity` 族**逐字相同**（那条是批次 242 定的）：vtable 指针 = `_ZTV` 符号地址 **+ 0x10**
// （Itanium ABI：`_ZTV` 头两个机器字是 offset-to-top 与 typeinfo，虚函数表从 +0x10 开始）。
// 这一条**用既有常量验证过**：`kEntityPlayerVtableOffset = 0xA37110` 而 `_ZTV…Entity_PlayerE`
// 文件偏移是 `0xA37100`；`Entity_Familiar`（0xA35718→0xA35728）、`Entity_Tear`（0xA37628→0xA37638）
// 两个也一样 ⇒ 本批 7 个子类照同一式子算，`_ZTV` 符号全在 dynsym 里逐字可查。
// ★ `Entity:ToPlayer()` 一族用的判据就是「对象首字 == base + 该常量」，本批的 `GridEntity:To*()`
//   复用同一条（`GridEntity::Init` 里那句 `ldr x8,[x0]` 也印证首字是 vptr）。
inline constexpr uintptr_t kGridEntityVtableOffset = 0xA37890;
inline constexpr uintptr_t kGridEntity_PitVtableOffset = 0xA37BE8;
inline constexpr uintptr_t kGridEntity_RockVtableOffset = 0xA37D98;
inline constexpr uintptr_t kGridEntity_DoorVtableOffset = 0xA37998;
inline constexpr uintptr_t kGridEntity_TNTVtableOffset = 0xA38098;
inline constexpr uintptr_t kGridEntity_PoopVtableOffset = 0xA37C70;
inline constexpr uintptr_t kGridEntity_PressurePlateVtableOffset = 0xA37CF8;
inline constexpr uintptr_t kGridEntity_SpikesVtableOffset = 0xA37E08;


// ---- 批次 276（2026-10-02）：`GridEntity` 子类的 vtable 偏移（7 条转换要用）----------------------
//
// 算法与 `Entity` 族**逐字相同**（那条是批次 242 定的）：vtable 指针 = `_ZTV` 符号地址 **+ 0x10**
// （Itanium ABI：`_ZTV` 头两个机器字是 offset-to-top 与 typeinfo，虚函数表从 +0x10 开始）。
// 这一条**用既有常量验证过**：`kEntityPlayerVtableOffset = 0xA37110` 而 `_ZTV…Entity_PlayerE`
// 的文件偏移是 `0xA37100`；`Entity_Familiar`（0xA35718→0xA35728）、`Entity_Tear`(0xA37628→0xA37638)
// 两个也一样 ⇒ 本批 7 个子类照同一个式子算，`_ZTV` 符号全在 dynsym 里逐字可查。
// ★ `Entity:ToPlayer()` 一族用的判据就是"对象首字 == base + 该常量"，本批的 `GridEntity:To*()`
//   复用同一条（`GridEntity::Init` 里那句 `ldr x8,[x0]` 也印证首字是 vptr）。


//: `GridEntity::GetPosition() const @ 0x37E498` —— PC Lua 的 `GridEntity.Position`（`const Vector`）。
//:
//: 为什么必须补（2026-09-21，用户报"EID 在献祭房不显示房间信息"）：EID 给 Lua 的网格实体挑"离玩家最近的那个"
//: 时逐个取 `gridEntity.Position`（`main.lua:1491`），而我们过去**没给非门的网格实体**这个字段
//: ⇒ 取到 `nil` 再 `:__sub` ⇒ 该帧描述整段不画（不崩、无提示）。EID 只给 `GRID_SPIKES` 注册了描述
//: （`eid_grid_descriptions.lua:115/133`）⇒ 症状**只在献祭房/带刺房间出现**，与用户描述一致。
//:
//: 证据（`tools/nro_disasm.py 0x37E498`，符号表 `_ZNK15IsaacRepentance10GridEntity11GetPositionEv`）：
//: ```
//: 0037e498  adrp x8, 0xaac000 ; ldr x8, [x8, #0x698]   ; x8 = &g_Game
//: 0037e4a0  ldr  x8, [x8]                              ; x8 = g_Game
//: 0037e4a4  mov  w9, #0x1550 ; movk w9, #0x2, lsl #16  ; 0x21550 = Game::Level
//: 0037e4ac  ldr  w1, [x0, #0x28]                       ; 网格下标
//: 0037e4b0  ldr  x8, [x8, x9]                          ; x8 = Level（`Room::GetGridPosition` 的 this）
//: 0037e4b4  mov  x0, x8
//: 0037e4b8  b    0x66fef0 ; Room::GetGridPosition(int) const   ← 尾调用，返回值原样透传
//: ```
//: **ABI**（`Room::GetGridPosition(int) const @ 0x454d38` 的收尾 `ldp s0, s1, [sp, #0x8]`）：
//: 返回 `Vector2`（两个 float）在 **s0/s1**；入参 `x0` = Level/Room 指针、`w1` = 网格下标。
//: 也就是说我们只要按 `x0 = 网格实体指针` 调它，返回值直接就是 PC 的 `Position`。
//: 位置公式（同一条函数）：`x = (idx % W + 1) * 40`、`y = (idx / W) * 40 + 120`。
inline constexpr uintptr_t kGridEntityGetPositionOffset = 0x37E498;
//: `GridEntity::GetPosition() const` 的入口 16 字节（`tools/nro_disasm.py` 逐字节核过）。
inline constexpr std::array<u8, 16> kGridEntityGetPositionExpectedBytes = {
    0x68, 0x39, 0x00, 0xd0, 0x08, 0x4d, 0x43, 0xf9,
    0x08, 0x01, 0x40, 0xf9, 0x09, 0xaa, 0x82, 0x52,
};
// `GridEntity + 0x10` = **variant**。证据（2026-09-16，行为锚点）：
// `GridEntity_Poop::InitSubclass` / `GridEntity_Poop::Update` 反复读 `+0x10` 并与 **1000 (0x3E8)**
// 比较 —— Isaac 里便便的 variant 正是 1000 起（1000=普通便便、1001=玉米…），共 4 处独立比较。
// 另有结构证据：`GridEntity::Init(const Desc&) @ 0x37E4BC` 把 `Desc+0x00..0x1C` 整段拷到
// 对象 `+0x08..0x24`，其中对象 `+0x18` ← `Desc+0x10`（与上面那条"类型在 +0x18"一致 ✓）。
// ★ 2026-10-16更正：原10实为State；旧推断原文保留于上方。
// Door::InitSubclass385fb0把10存PreviousState310、385fb8把0c存PreviousVariant314；
// Rock::GetBigRockFrame39349c读取0c按variant>=1000解码，PC705cd0/430d00同义。
inline constexpr uintptr_t kGridEntityVariantOffset = 0x0C;
// `GridEntity + 0x30` = **该网格实体自己的 RNG**（PC Lua 的 `GridEntity:GetRNG()`）。
// 两条互相独立的证据（2026-09-16 反汇编，`add x0, xThis, #0x30` 形态 —— 不是 `ldr`，是把字段
// **地址**当 `this` 交给 `RNG` 的方法，所以看起来像"取地址传参"）：
//   * `GridEntity::hurt_func(Entity*, float, int, unsigned, bool) @ 0x37E57C`：
//     序言 `mov x19, x0`（0x37E5B8）说明 x19 就是 `this`；函数体 0x37E928 处
//     `add x0, x19, #0x30; bl RNG::Next`，紧接着把这个返回值当种子构造临时 RNG
//     （`RNG::RNG(seed, 2)`）—— 这正是引擎里"从本实体的 RNG 派生一个新 RNG"的标准写法；
//   * `GridEntity_Spikes::InitSubclass() @ 0x393B34`：0x393CB8 处
//     `add x0, x19, #0x30; RNG::SetSeed([x19+0x24], 35)` —— 尖刺在初始化时把自己的 RNG
//     按 shift=35（Isaac 内部最常用的档位）重新播种，与 IsaacDocs `GridEntity.md:38` 那句
//     "这个 RNG 在全关卡的所有网格实体上用同一个种子初始化"完全对上。
// `RNG` 自身布局来自 `RNG::SetSeed(uint, uint) @ 0x44E3C0`：`[this+0x0] = seed`、
// `[this+0x4..0xB] = s_Shifts[idx]`、`[this+0xC] = s_Shifts[idx].second` ⇒ 共 16 字节、
// **种子就是头 4 字节**（PC 的 `RNG:GetSeed()` 读它、`Next()` 原地更新它）。
inline constexpr uintptr_t kGridEntityRngOffset = 0x30;
inline constexpr std::size_t kRngObjectSize = 16;

// `Room:WorldToScreenPosition(Vector)`（批次 10，2026-09-15）：引擎里它就是
// `GetRenderPosition(世界坐标, true) + Room.RenderScrollOffset + Game.ToScreenAdjust`。
// 三处证据都来自 `Room::WorldToScreenPosition @ 0x489354` 这一条函数的反汇编：
//   * `bl 0x670fa0`（PLT 桩，指向 `_ZN15IsaacRepentance17GetRenderPositionERKN4KAGE4Math7Vector2Eb`）；
//   * `mov w8,#0x1938` + `add x1,x19,x8` → `Vector2::operator+` ⇒ 房间的滚动偏移；
//   * `g_Game` → `*(g_Game)` + `0x24F9B0` → `Vector2::operator+` ⇒ Game 那一份调整量。
inline constexpr uintptr_t kGetRenderPositionStubOffset = 0x670FA0;
inline constexpr std::array<u8, 16> kGetRenderPositionStubExpectedBytes = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0x9E, 0x43, 0xF9,
    0x10, 0xE2, 0x1C, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
// Game 那一份"世界→屏幕"调整量的偏移。**名字只是结构性的**（该字段的语义没有单独定位），
// 证据 = 同一条函数把它加进结果里；所以它只用于这条 API 的换算，不对外暴露字段。
inline constexpr uintptr_t kGameToScreenAdjustOffset = 0x24F9B0;
inline constexpr uintptr_t kEntityListLiveBeginOffset = 0x78;   // Entity**（步长 8）
inline constexpr uintptr_t kEntityListLiveCapacityOffset = 0x80;  // u32，恒 0x800
inline constexpr uintptr_t kEntityListLiveCountOffset = 0x84;     // u32
inline constexpr std::uint32_t kEntityListLiveCapacity = 0x800;
// 一般实体表的 begin/count（`+0x48`/`+0x54`）：批次 4 的注释表里早就写了这一对与 `+0x50`
// 的容量，但只给容量具了名。2026-09-13 的 `ISAACEL1` 探针要把三张表的 begin/count 都报出来，
// 所以在这里补齐（纯新增，不改动既有常量）。
inline constexpr uintptr_t kEntityListGeneralBeginOffset = 0x48;      // Entity**（步长 8）
inline constexpr uintptr_t kEntityListGeneralCapacityOffset = 0x50;  // u32，恒 0x4000
inline constexpr uintptr_t kEntityListGeneralCountOffset = 0x54;     // u32
inline constexpr std::uint32_t kEntityListGeneralCapacity = 0x4000;
inline constexpr uintptr_t kEntityListEffectBeginOffset = 0xA8;      // Entity**（步长 8）
inline constexpr uintptr_t kEntityListEffectCapacityOffset = 0xB0;   // u32，恒 0x4000
inline constexpr uintptr_t kEntityListEffectCountOffset = 0xB4;      // u32
inline constexpr uintptr_t kEntityListArenaCapacityOffset = 0xE0;    // u32，恒 0x8000
inline constexpr std::uint32_t kEntityListArenaCapacity = 0x8000;

// ---- 批次 268（2026-10-02）：`Isaac.CountEntities` 与 `Entity.SpawnerEntity` 的偏移 ---------
//
// `Isaac.CountEntities(spawner, type, variant, subtype)`（PC 契约 `tools/pc_contract_docs/Isaac.md:72`，
// 正文 `:74-78`）在 PC 侧落到引擎的一个成员函数上：`tools/pc_exe_binding.py CountEntities`
// 给出名字表项在文件 `0x409B12`（VA `0x80A712`）⇒ 绑定函数 VA `0x80D0D0`；把 4 个实参读全之后
// 它是 `mov eax,[0xbfd65c]`（全局游戏对象）+ `mov ecx,[eax+0x18190]` + `add ecx,0x1218`
// + `call 0x416640` ⇒ 成员调用的形状 = `this = *(g_Game+0x18190)+0x1218`、实参 `(spawner,type,variant,subtype)`。
//
// Switch 侧同一个函数 = `EntityList::CountSpawned(Entity*, eEntityType, int, int)` @ **`0x7A1CC`**
// （dynsym 里逐字有这个名字）。`python3 tools/nro_disasm.py 0x7a1cc 200` 给出三件本批依赖的事：
//   ① 寄存器形状：`x0 = this`(EntityList) / `x1 = spawner` / `w2 = type` / `w3 = variant` / `w4 = subtype`；
//   ② 逐实体比 `[+0x38]`(Type) / `[+0x3c]`(Variant) / `[+0x40]`(SubType)，再比 **`[+0x3A8]`**（生成者）
//      与 `x1` —— 见下面的 `kEntitySpawnerEntityOffset`；
//   ③ 通配语义**引擎自己就实现了**（所以这条 API 一行都不用自己写）：
//      `cbz x1` ⇒ 不看生成者；`cbz w2` ⇒ 不看 Type；`tbnz w3,#0x1f` / `tbnz w4,#0x1f`
//      ⇒ variant / subtype 为负时跳过那一格。正好对上 PC 文档那句
//      "Type … can be `EntityType.ENTITY_NULL`" 与两个 `-1` 缺省值。
//
// ★ 入口 4 字节指纹 `0xAA0003E8`（`mov x8, x0`）**很泛**，它本身不构成判据强度；
//   本条的硬证据是"偏移来自 dynsym 里那个符号地址 + 反汇编逐条对上了语义"，指纹只是防呆。
inline constexpr uintptr_t kEntityListCountSpawnedOffset = 0x7A1CC;
inline constexpr std::uint32_t kEntityListCountSpawnedEntryWord = 0xAA0003E8;

// `Entity.SpawnerEntity`（PC 契约 `tools/pc_contract_docs/Entity.md:822/824`：返回 `Entity`、
// `data-altreturn='nil'`）= **`Entity + 0x3A8`，一个裸的 `Entity*`**（不是 `EntityRef`）。
// **两条独立入口互证**：① `EntityList::CountSpawned` 的 `ldr x10,[x10,#0x3a8]` + `cmp x10,x1`
// （上面那条）；② `Entity::GetLastSpawner` @ `0x58C10` 整个函数体就是
// `ldr x0,[x0,#0x3a8]` + `cbnz x0,<回到开头>`（沿这一格往上走到没有生成者为止）——
// 函数名与这一格的语义逐字吻合。
// ★ 本批**只把偏移记下来当证据，不对外开 `Entity.SpawnerEntity`**：它的同族两个字段
//   （`SpawnerType` / `SpawnerVariant`）还没取证到，只开一个会让模组拿到半个对象。
inline constexpr uintptr_t kEntitySpawnerEntityOffset = 0x3A8;

// ---- 批次 399（2026-10-07）：`Entity.SpawnerEntity` 对外开，并补齐同族两个字段 ---------
//
// ★ 上面那个"不对外开"的决定被本批**推翻了一半**：`SpawnerEntity` 单独开出来是有价值的 ——
//   语料模组 `Trinity` 的 `main.lua:129`（Peter 的"红眼泪"效果）就写
//   `local player = tear.SpawnerEntity:ToPlayer()`；我们没开这一格 ⇒ Lua 拿到 `nil`
//   ⇒ 链式取值抛 `attempt to index a nil value (field 'SpawnerEntity')` ⇒ 派发器静默摘掉
//   整条 `MC_POST_FIRE_TEAR` 登记（真机错误环逐字见 `dist/gdb-read-20261007-2045-char-error.txt`）。
//   批次 268 当初"只开一个会让模组拿到半个对象"的顾虑，在本批拿到同族两个字段的证据后不再成立。
//
// `Entity.SpawnerEntity`（PC 契约 `tools/pc_contract_docs/Entity.md:824`，小节标题在 `Entity.md:822`：
//   返回 `Entity`、`data-altreturn='nil'`）= `Entity + 0x3A8`，**裸 `Entity*`**（不是 `EntityRef`）。
//   * 读：`Entity::GetLastSpawner @ 0x58C10` = `ldr x0,[x0,#0x3a8]` + `cbnz x0,<回到开头>`
//     （沿"生成者链"上溯到没有生成者为止 —— 函数名与这一格语义逐字吻合）；
//   * 读：`EntityList::CountSpawned @ 0x7A1CC` 的 `ldr x10,[x10,#0x3a8]` + `cmp x10,x1`；
//   * 写：`Entity::SetSpawnerEntity @ 0x59638` 的 `str x19,[x21]`（`x21 = x0 + 0x3A8`）；
//   * 空判：同函数 `cbz x19,<跳过>` ⇒ **合法取值为 0** ⇒ 指针为 0 时必须推 `nil`（PC 亦然）。
//
// `Entity.SpawnerType` / `Entity.SpawnerVariant`（PC 契约 `Entity.md:829` / `Entity.md:834`）
//   = **`+0x44` / `+0x48`**，两个 u32，**两条独立入口互证**：
//   ① `Entity_NPC::query_npcs_spawnertype @ 0x11FE60`（函数名即语义，按"生成者类型"过滤 NPC）：
//      `0x11FEEC ldr w8,[x24,#0x44]` + `cmp w8,w20`（`w20` = 形参 `SpawnerType`）
//      —— 第一个比较用的就是这一格。
//   ② `Game::Spawn @ 0x3540D0`（生成实体时记录"谁生的"）：
//      `0x35417C ldr w8,[x24,#0x38]`（spawner 的 `Type`）→ `0x354180 str w8,[x22,#0x44]`；
//      `0x354184 ldr w8,[x24,#0x3c]`（spawner 的 `Variant`）→ `0x35419C str w8,[x22,#0x48]`；
//      `x24` = 生成者、`x22` = 新实体；无生成者时 `0x354190 str wzr,[x22,#0x44]`（连同后者写 0）
//      —— 即这两格 = **生成瞬间从生成者抄下来的 `Type` / `Variant`**。
//   ★ 与 PC 的排布同构：PC 的 own `Type`/`Variant` 在 `0x28`/`0x2C`、spawner 的对在 `0x34`/`0x38`
//     （`tools/pc_exe_binding.py SpawnerType/SpawnerVariant` 各给一条
//     `mov eax,[ecx+0x34]; ret` / `mov eax,[ecx+0x38]; ret`）；Switch 上 own 在 `0x38`/`0x3C`、
//     spawner 的对顺延到 `0x44`/`0x48` —— 间距都是 +4、顺序一致（一层免费交叉印证）。
inline constexpr uintptr_t kEntitySpawnerTypeOffset = 0x44;      // u32，生成者的 Type
inline constexpr uintptr_t kEntitySpawnerVariantOffset = 0x48;   // u32，生成者的 Variant

// Entity 基类里本批次新用到的字段（出处：`EntityList::Add`/`Room::AddEntity` 的存值形态与
// `Entity::GetFrameCount` 的减法形态，见 `docs/问题与解决记录.md` 批次 4）。
inline constexpr uintptr_t kEntityIndexOffset = 0x30;         // u32，`Entity.Index`（房间实体表序号）
inline constexpr uintptr_t kEntitySpawnFrameOffset = 0x2F4;   // u32，生成帧（FrameCount 的减数）
// `Entity.InitSeed`（u32）= `+0x3E8`。**这一条在本仓库里早就被记为"陷阱"**：
// "`Entity + 0x3E8` 是**生成种子**而不是 `Index`（236 处引用多为 `ldr w1,[x,#0x3e8]; bl RNG::RNG`）"
// —— 32 位装载后直接当 `RNG::RNG(seed)` 的入参，就是 PC 的 `Entity.InitSeed`。
// EID 把它当**表键**用（`main.lua:206`/`210`/`264`、`features/eid_api.lua:3095`），
// 所以它必须是非 nil 的数字：`table[nil] = x` 在 Lua 里是硬错误 `table index is nil`
// （与批次 3 的 `EID.controllerIndexes[p.ControllerIndex]` 完全同类）。
inline constexpr uintptr_t kEntityInitSeedOffset = 0x3E8;
// 64 位实体标志。bit46 == `EntityFlag.FLAG_NO_QUERY`（`enums.lua:1034`：`1<<46` "Hide from
// query results"）→ `QueryRadius`/`FindByType` 都跳过；bit3 置位的实体**不在活表**里。
inline constexpr uintptr_t kEntityFlagsOffset = 0x1B8;
inline constexpr unsigned kEntityFlagNoQueryBit = 46;
// `Entity` 家族 vtable 区间（`_ZTV` 段），用于"这个指针像不像一张 Entity"的通用判据。
// `Entity_Pickup` 的 vtable 落在其中，是 `ToPickup()` 的唯一判据。
inline constexpr uintptr_t kEntityVtableRangeBeginOffset = 0xA34F58;
inline constexpr uintptr_t kEntityVtableRangeEndOffset = 0xA38230;
inline constexpr uintptr_t kEntityPickupVtableOffset = 0xA36E28;
// `Entity_Familiar` 的 vtable 指针（`_ZTVN15IsaacRepentance15Entity_FamiliarE` @ `0xA35718`，
// 加 `0x10` 跳过 "offset-to-top + typeinfo" 两个表头字 ⇒ `0xA35728`）。
// 这条 `+0x10` 规则由既有两个常量交叉验证：`Entity_Player` 符号 `0xA37100` ↔ 本文件
// `0xA37110`；`Entity_Pickup` 符号 `0xA36E18` ↔ `0xA36E28`（都差 `0x10`，一致）。
// 用途：`Entity:ToFamiliar()` 的判据（`Type == ENTITY_FAMILIAR` 且 vptr 精确相等）。
inline constexpr uintptr_t kEntityFamiliarVtableOffset = 0xA35728;
inline constexpr std::uint32_t kEntityTypePlayer = 1;
inline constexpr std::uint32_t kEntityTypePickup = 5;
// 实体族回调（2026-09-18 批次 010）要按 `EntityType` 把实体分派给对应的回调。下面这几个值
// 取自 PC 的 `EntityType` 枚举（`analysis/isaacdocs-snapshot/docs/enums/EntityType.md`），
// 已与本仓库既有的分区代码交叉核对：`2` 眼泪、`4` 炸弹、`7` 激光、`8` 刀、`9` 弹射物
// （`ClassifyEntity` 里的 `type == 2`/`== 8`/`== 9`/`== 4` 四条与枚举一致）。
// 判据说明：这几类**没有各自的 vtable 常量**（没取证过），所以只能用 `Type` 判；
// 玩家/掉落物/跟班那三类有 vtable 常量，判据必须是"Type + vptr 精确相等"（见 `isaac_api.cpp`）。
inline constexpr std::uint32_t kEntityTypeTear = 2;
inline constexpr std::uint32_t kEntityTypeBomb = 4;
inline constexpr std::uint32_t kEntityTypeLaser = 7;
inline constexpr std::uint32_t kEntityTypeKnife = 8;
inline constexpr std::uint32_t kEntityTypeProjectile = 9;
// `EntityType.ENTITY_FAMILIAR == 3`（PC 枚举；本项目既有的实体分区代码里也用 `type == 3`
// 判"跟班"，且 `variant == 0xEF` 的特例归到敌人那一类）。
inline constexpr std::uint32_t kEntityTypeFamiliar = 3;
inline constexpr std::uint32_t kEntityTypeEffect = 0x3E8;
// `IsEnemy = (u32)(Type - 10) < 0x3DE`（引擎 `EntityList::collide()` 里的同一条比较）。
inline constexpr std::uint32_t kEntityEnemyTypeBase = 10;
inline constexpr std::uint32_t kEntityEnemyTypeSpan = 0x3DE;
// `Entity + 0xCC9`：**boss 标记字节**（`Isaac.CountBosses` 的判据；2026-09-18 批次 026 取证）。
//
// 证据（三条互证）：
//   ① `Entity_NPC::IsBoss()`（符号 `_ZNK15IsaacRepentance10Entity_NPC6IsBossEv` @ `0x124B20`）
//      的**整个函数体**就是 `ldrb w0, [x0, #0xcc9]` + `ret` ⇒ 这条 PC 访问器读的就是这个字节；
//   ② 基类 `Entity::IsBoss()` @ `0x67580` 是 `mov w0, wzr; ret`（恒 false）⇒ 这个字段只对
//      NPC 有意义，别的类里读它是无意义数据（下面的 `IsBossEntity` 因此先要求"这是敌人"）；
//   ③ 全镜像扫"对 `[x?, #0xcc9]` 的字节访问"共 **15 处**（4 写 11 读，含①那一处）：
//      写入处 `0x108A10` 把 NPC 配置结构（`[实体+0x300]`）里 `+0x30` 的字节**拷进**实体
//      `+0xCC9`（同一段里还有 `+0x5C→+0xCC8`、`+0x120→+0xCCC`、`+0x124→+0xCD0`），
//      读取处 `0x106374` 在 NPC 寻路重置（`NPCAI_Pathfinder::Reset`）之后按它分支 ⇒
//      这是一个由 NPC 配置驱动、被 AI 代码真正使用的字段。
inline constexpr uintptr_t kEntityBossFlagOffset = 0xCC9;

// EntityNPC.CanShutDoors 是可写 bool 属性，与基类的虚方法不同。
// NPC::Init @108A04/108A08 把 config+5C 拷到 +CC8；
// NPC::CanShutDoors @124B00 先读本字节，再排除友军标记。
inline constexpr uintptr_t kEntityNpcCanShutDoorsOffset = 0xCC8;
inline constexpr uintptr_t kEntityNpcCanShutDoorsMethodOffset = 0x124B00;
inline constexpr std::array<u8,16> kEntityNpcCanShutDoorsExpectedBytes = {
    0x08,0x20,0x73,0x39,0xa8,0x00,0x00,0x34,0x08,0xec,0x46,0x39,0x1f,0x01,0x1b,0x72
};

// 扫描一个实体需要的字段区间：最远的字段是 `Size`（`+0x344`，4 字节），所以一次可读性检查
// 覆盖 `[entity, entity + 0x348)` 就够，之后的逐字段读取只是 `memcpy`（真机上 `svcQueryMemory`
// 是系统调用，逐字段检查会让一次全房间扫描变成上千次调用）。
inline constexpr std::size_t kEntitySnapshotSpan = 0x348;

// `Entity_Pickup` 字段（`Touched` **未定案**，`+0x560` 只是候选，见注释）。
inline constexpr uintptr_t kEntityPickupOptionsIndexOffset = 0x55C;
inline constexpr uintptr_t kEntityPickupTouchedOffset = 0x560;   // 猜测：u8/bool
inline constexpr uintptr_t kEntityPickupForceBlindOffset = 0x562;  // u8
inline constexpr uintptr_t kEntityPickupPriceOffset = 0x564;       // u32
inline constexpr uintptr_t kEntityPickupShopItemIdOffset = 0x56C;  // u32

// `EntityPlayer.Luck` 的字段偏移（`0x1950`，**float**）。
//
// ★★★ 2026-10-01 更正：这里原先写的是 `0x1920`（**int32**）—— **那是错的**，用户报的
//     「EID 显示的幸运与游戏自带的（暂停菜单属性页）不一致」就是它造成的。四处证据都指向 `0x1950`：
//   * ★ 语义锚点 1（**游戏自己怎么显示它**）：`PauseScreen::Show @ 0x43274C` 连读六个玩家属性做
//     暂停菜单属性显示，前五个是 0x194C 速度 / 0x1834 射速 / 0x1844 伤害 / 0x1854 射程 / 0x1838 弹速，
//     第六个就是 `0x432930 ldr s0, [x20, #0x1950]` → `0x432934 bl PlayerUtils::GetLuckRating(float)`
//     （`_ZN15IsaacRepentance11PlayerUtils13GetLuckRatingEf`，符号表在 `0x4438A0`）。
//     ⇒ **暂停菜单那一栏幸运读的就是这一格，而且按 float 读**。
//   * ★ 语义锚点 2（**引擎自己往它里面加幸运加成**）：`Entity_Player::EvaluateItems @ 0x280804` 里
//     `0x28AF88 ldr s1, [x19, #0x1950]` → `fadd s0, s1, s0` → `0x28AF90 str s0, [x19, #0x1950]`
//     （`fadd` 前面的 `scvtf` 把"饰品倍率×10"这类整数加成转成浮点再累加）⇒ 它是被浮点累加的**属性**。
//   * ★ 频度旁证：全镜像扫「`ldr s?, [x?, #0x1950]`」共 **82 处**（属性级高频，散在
//     `EvaluateItems` / `GetTearHitParams` / 各类道具效果里）；而同族属性 0x194C 速度 / 0x1844 伤害
//     也都是 float ⇒ **`Luck` 没有理由是个 int32**。
//   * ★ `0x1920` 到底是什么：`Entity_Player::DonateLuck(int) @ 0x2F9978` 里
//     `ldr w8, [x0, #0x1920]` / `add w8, w8, w1`（**整数加法**）/ `str w8, [x0, #0x1920]`，
//     并且同一段还给 `+0x1958` 置脏标记位 `0x400`；`Entity_Player::StoreGameState @ 0x2F85C0` /
//     `Entity_Player::RestoreGameState @ 0x2C48AC` 把 `0x1914/0x1918/0x191C/0x1920/0x1924` 这五格
//     **按 int32 整块存档** ⇒ 它是「捐赠运气」那类**计数器**，**不是** PC 契约里那个
//     「等于幸运属性（the Luck Stat）」的 `Luck`。全镜像它只有 2 读 2 写。
//
// PC 契约（`tools/pc_contract_docs/EntityPlayer.md:1966-1969`）：
//     #### float Luck
//     Player stat - Only change this in a callback to MC_EVALUATE_CACHE.
//     **This is equal to the Luck Stat.**
//   ⇒ 类型是 **float**，与上面两条镜像锚点一致；所以我们按 `float → Lua number` 交付。
//
// 取证命令（本机就有游戏镜像，不必猜、也不必上网找）：
//     python3 tools/nro_disasm.py 0x4328F0 0x70       # 暂停菜单读第六个属性
//     python3 tools/nro_disasm.py 0x28AF70 0x60       # EvaluateItems 里浮点累加 Luck
//     python3 tools/nro_disasm.py 0x2F9940 0x60       # DonateLuck 操作的其实是 +0x1920 计数器
//
// 为什么必须实现（不实现会出什么）：EID 在**逐帧渲染路径**上对"幸运值相关道具"调用
// `EID.LuckFormulas[...](player.Luck)`（`features/eid_data.lua` 里 48 条公式）。字段缺失时
// Lua 侧拿到 `nil` ⇒ 算术抛错 ⇒ 那一条渲染回调**当场中断** ⇒ 该帧那片道具的描述全部不画
// （连带同帧后面要画的一起丢）。真机症状：死亡证明房间里"部分底座道具既没文字也没问号"，
// 错误文本为 `eid_data.lua:1215: attempt to perform arithmetic on a nil value (local 'luck')`。
// ★★ 教训（这次踩的）：它当年只是"给个数字让 EID 不抛 nil 错"就记成做完了 ⇒「不抛错」≠「值对」。
//    有真实语义的字段必须用 **PC 契约原文 + 镜像/真机对照** 定案，而不是"能跑就行"。
// （旧写法 = 读 `+0x1920` 的 int32，已作废；改动与判读见
//   `docs/调查-EID幸运显示与游戏不一致-20261001.md` 与 `docs/改动日志-20261001.md` 批次 257。）
inline constexpr uintptr_t kEntityPlayerLuckOffset = 0x1950;  // float

// --- `Entity_Player` 的战斗属性与两个状态字段（2026-09-16 静态取证）------------------------
//
// 这四个属性都只以 `ldr s0/str s0`（float）出现；命名链是引擎自己的
// `PlayerUtils::Get{Speed,TearDelay,Damage,Range}Rating(float)`：`PauseScreen::Show @ 0x43274C`
// 连续读这五个偏移做暂停菜单的属性显示（0x194C→速度、0x1834→射速、0x1844→伤害、0x1854→射程、
// 0x1838→弹速），`Entity_Player::AddCollectible @ 0x292A74` 里同一组。默认值也自证：
// `Entity_Player::Init @ 0x278D94` 写 `+0x194C = 1.0f`、`+0x1854 = 260.0f`（= 6.5×40），
// `EvaluateItems @ 0x280804` 里 `+0x1834` 用 10.0f、`+0x1844` 用 3.5f —— 正好是 Isaac 的
// 基础速度/射程/射速/伤害。
// ★ 2026-10-01：那一串其实是**六个** —— 第六个 `0x432930 ldr s0,[x20,#0x1950]` →
//   `PlayerUtils::GetLuckRating(float)` 就是幸运（见上面 `kEntityPlayerLuckOffset` 一节）。
//
// `Damage`（float）：
//   * `Entity_Player::GetTearHitParams @ 0x2AD63C`：`0x2AD6D4 ldr s0,[x20,#0x1844]` → 乘倍率后
//     写进 `TearParams::Damage`（`0x2AD6DC str s0,[x26,#0x48]!`）；
//   * `EvaluateItems` 的 CACHE_DAMAGE 分支：先 `str wzr,[x19,#0x1844]` 清零再累加，
//     收尾 `fmov s10,#3.5`（`0x2830FC str s0,[x19,#0x1844]`）。
inline constexpr uintptr_t kEntityPlayerDamageOffset = 0x1844;          // float
// `MoveSpeed`（float）：
//   * `Entity_Player::Init`：`0x279698 mov w8,#0x194c` + `0x27969C mov w9,#0x3f800000`(1.0f)
//     + `0x2796A0 str x9,[x19,x8]`（默认 1.0）；
//   * `Entity_Player::control_movement @ 0x2B14B4`：`0x2B1748 ldr s0,[x19,#0x194c]` → `fmul`/`fadd`。
inline constexpr uintptr_t kEntityPlayerMoveSpeedOffset = 0x194C;        // float
// `MaxFireDelay`（float；**Switch 侧是 float，PC AB+ 文档写 int —— 按 float 读**）：
//   * `EvaluateItems`：`0x28BB0C bl PlayerUtils::GetTearDelayFromRating` → `0x28BB10 str s0,[x19,#0x1834]`；
//   * `Entity_Player::control_shooting @ 0x2B260C`：`0x2B4150 ldr w9,[x19,#0x1834]` → 抄进每个武器
//     （`0x2B4154 str w9,[x8,#0x1c]`，同一段重复 5 次，对应 +0x1758/1760/1768/1770/1778 五个武器槽）。
inline constexpr uintptr_t kEntityPlayerMaxFireDelayOffset = 0x1834;     // float
// `ShotSpeed`（float，批次 405 补常量；**紧挨 `MaxFireDelay` 的高 4 字节**）：
//   取证出处与上面 `MaxFireDelay`/`Damage` **同一族**（本批不新增独立取证，证据就是同一条写点）：
//   * `Entity_Player::Init @ 0x278D94`：`0x27964C mov w8,#0x1834` + `0x279638 movk x9,#0x3f80,lsl#48`
//     + `0x279660 str x9,[x19,x8]` —— 这是**一次存 8 字节**：低 4 字节 `+0x1834=1.0f`（MaxFireDelay）、
//     高 4 字节 `+0x1838=1.0f`（ShotSpeed）⇒ 引擎初始化一口气给两格写默认 1.0。
//   * `PauseScreen::Show @ 0x43274C` 连读六个属性做暂停菜单显示：`0x1838` 就是其中的**弹速**
//     （见上面 `kEntityPlayerLuckOffset` 一节第 2018/2062 行）。
// Windows：全镜像里 `+0x1838` 只以 `ldr s0`/`str s0`（float）出现，与 `MaxFireDelay` 同形。
// PC 契约（`EntityPlayer.md`）：`float ShotSpeed` — "Player stat - Only change this in a callback to
//   MC_EVALUATE_CACHE." ⇒ 与其余五个战斗属性同口径（只在 `MC_EVALUATE_CACHE` 里改）。
inline constexpr uintptr_t kEntityPlayerShotSpeedOffset = 0x1838;        // float
// `TearRange`（float，原始射程单位，默认 260 = 6.5×40）：
//   * `Entity_Player::Init`：`0x2796B8 mov w8,#0x43820000`(260.0f) → `0x2796BC str w8,[x19,#0x1854]`；
//   * `Entity_Player::FireDelayedBrimstone @ 0x2FB24C`：`0x2FB3C8 ldr s0,[x19,#0x1854]` → 算激光长度；
//   * `Entity_Player::FireTear @ 0x2A991C`：`0x2A9BA8 ldr w8,[x19,#0x1854]` → 写进新子弹的射程字段。
inline constexpr uintptr_t kEntityPlayerTearRangeOffset = 0x1854;        // float
// `CanFly`（**1 字节** bool，0/1）：
//   * `Entity_Player::GetFlyingOffset @ 0x2BB9F0`：`0x2BBA20 mov w8,#0x1954` + `0x2BBA24 ldrb w8,[x19,x8]`
//     + `cbz`（置位时返回 `Vector2(0,-4)` 的飞行视觉偏移）；
//   * `Entity_Player::AddMinisaac @ 0x2AC1F4`：读同一个字节，按"能否飞"给小以撒定运动层 5/3；
//   * `PlayerManager::ReplacePlayer @ 0x4428DC` 把它从旧玩家拷到新玩家。
//   ⚠️ **只改这一格不会立刻改变碰撞层**：决定"能否飞过石头/坑"的是 `+0x1E0`
//   （`Entity::IsFlying @ 0x5C744` = `[+0x1E0] < 4`），它由引擎在缓存重算时按本字段同步
//   —— PC 侧同样要求"只在 `MC_EVALUATE_CACHE` 里改"，行为一致。
inline constexpr uintptr_t kEntityPlayerCanFlyOffset = 0x1954;           // bool(1 byte)
inline constexpr uintptr_t kEntityFlyingLayerOffset = 0x1E0;             // int32（派生量，非 Lua 字段）
// `ControlsCooldown`（**有符号 int32**；EID 会**写**它来抑制按键连发）：
//   * `Entity_Player::UsePill @ 0x2DFC04` 的麻痹药丸分支：`0x2E1C2C mov w8,#0xf0`(240) /
//     `0x2E1C30 mov w9,#0x78`(120) / `csel` / `0x2E1C3C str w8,[x20,#0x404]`；
//   * `Entity_Player::Update @ 0x2BBCDC` 每帧递减到 0（`ldr w8,[x19,#0x404]` / `subs #1` / `b.lt` / `str`）；
//   * `control_shooting @ 0x2B265C`：`ldr w10,[x19,#0x404]` + `cmp #0` + `b.le`（>0 就不让射击）。
//   ⚠️ `+0x408` 是**另一个**字段（`SetShootingCooldown @ 0x2FB994`，取 max），不是本字段。
inline constexpr uintptr_t kEntityPlayerControlsCooldownOffset = 0x404;  // int32

//: `EntityPlayer.ControlsEnabled`（**bool，1 字节**）—— 批次 212（2026-09-30）取证。
//:
//: 锚点 = **引擎自己**的 `IsaacRepentance::PlayerManager::SetControlsEnabled(bool) @ 0x4422C0`：
//:   ```asm
//:   004422c0  ldp x8, x9, [x0, #0x10]     ; PlayerManager: 玩家向量 begin/end（+0x10 / +0x18）
//:   004422cc  and w9, w1, #0x1            ; 参数 bool → 0/1
//:   004422d0  ldr x10, [x8], #0x8         ; 下一个玩家指针
//:   004422d4  strb w9, [x10, #0x400]      ; ★★ 写 `Entity_Player + 0x400`（按字节 ⇒ bool）
//:   004422e0  b.ne 0x4422d0               ; 循环所有玩家
//:   ```
//: ⇒ 语义锚点（引擎自己的"设开关"就是写这一格）+ **与 `+0x404`（`ControlsCooldown` int32）
//:   正好相邻**（bool 在 int32 前面）⇒ 两条互证。
//: 为什么需要它：MCM 打开菜单时会 `player.ControlsEnabled = false`（冻住玩家），
//: 我们**拒写**就抛错、**整条渲染回调每帧中断** ⇒ 菜单永远画不出来（2026-09-30 真机实测）。
inline constexpr uintptr_t kEntityPlayerControlsEnabledOffset = 0x400;  // bool（1 字节）

// --- `Entity_Player._cacheFlags`（**u32 缓存标志字**，批次 301，2026-10-03 取证）-------------
//
// 它是什么：玩家身上那个「哪些属性需要重算」的位掩码（PC 叫 `EntityPlayer._cacheFlags`）。
// `EntityPlayer:AddCacheFlags(CacheFlag)` 就是 `_cacheFlags |= 参数`；引擎在下一帧
// `EvaluateItems()` 里逐位测试、按位重算对应属性，然后清位。
//
// ★★★ 两侧的定位与互相印证（三条独立证据，缺一条都只剩"某处有个 u32"）：
//
//   ① **PC 侧本体**（`tools/pc_exe_binding.py AddCacheFlags --disasm`）：
//        `00427800  push ebp` … `00427806  09 81 b8 14 00 00  or dword ptr [ecx+0x14b8], eax`
//      ⇒ PC 的 `_cacheFlags` 在 `EntityPlayer + 0x14B8`（PC 偏移，**不许平移**）。
//      PC 侧同一格还有一批常量 OR（全文件搜立即数 `0x14b8`）：
//        `00427d51  or dword ptr [eax+0x14b8], 0x400`、`005f38bb` 同款、
//        `005ab18d` / `005abf58` = `…, 0x41f`、`005ab718` = `…, 0x201`、`005b45bf` = `…, 0xffff`
//      ⇒ 这一格是"各种位掩码往里面 OR"的那个字，不是计数器。
//
//   ② **Switch 侧「具名写入方」把语义钉死**（最硬的一条）：
//        `Entity_Player::AddCollectible @ 0x29367c`（mangled
//        `_ZN15IsaacRepentance13Entity_Player14AddCollectibleENS_16eCollectibleTypeEibii`）：
//          0029367c  ldr  w8, [x22, #0x54]    ; ← **道具配置自己的 CacheFlags**
//          00293680  ldr  w9, [x20, #0x1958]  ; ← 玩家这一格
//          00293684  orr  w8, w9, w8          ; ★ 玩家._cacheFlags |= 道具.CacheFlags
//          00293688  str  w8, [x20, #0x1958]
//      ★ `[x22,#0x54]` 正是**我们早就确认过的** `kItemConfigItemCacheFlagsOffset`（`0x54`，
//        "`cache=` 属性 OR 累积，`<familiar>` 自动 `|= 0x200`"）⇒ **"把道具声明的缓存标志
//        并进玩家这一格"这件事被逐条写了出来**，`+0x1958` 的身份不可能再是别的。
//        （PC 的 `AddCollectible` 做同一件事，两侧同形。）
//
//   ③ **Switch 侧「读者 / 派发器」位号与 `CacheFlag` 枚举逐位吻合**：
//        `Entity_Player::EvaluateItems @ 0x280804`
//          `0x280ec8  str  xzr, [sp, #0x68]`
//          `0x280ecc  mov  w8, #0x1958` / `0x280ed0  add  x21, x19, x8`  ; x21 = 玩家 + 0x1958
//          `0x280ed4  ldr  w8, [x19, #0x1958]` / `0x280ee4  tbz  w8, #0x8, …`   ; bit8 = CACHE_WEAPON
//        …同一函数后段 `0x28bb54  ldr  w8, [x21]`（**就是同一格**，经 x21 间接读）
//          `0x28bb58  tbnz w8, #0x0, …`  ; bit0  = CACHE_DAMAGE
//          `0x28bb5c  tbnz w8, #0x1, …`  ; bit1  = CACHE_FIREDELAY
//          `0x28bb60  tbnz w8, #0x3, …`  ; bit3  = CACHE_RANGE
//          `0x28bb64  tbnz w8, #0x4, …`  ; bit4  = CACHE_SPEED
//          `0x28bb68  tbnz w8, #0xa, …`  ; bit10 = CACHE_LUCK
//          `0x28bb6c  tbz  w8, #0x2, …`  ; bit2  = CACHE_SHOTSPEED
//        ⇒ 位号与 `CacheFlag`（`1<<0` 伤害 / `1<<1` 射速 / `1<<2` 弹速 / `1<<3` 射程 /
//          `1<<4` 速度 / `1<<7` 飞行 / `1<<8` 武器 / `1<<10` 幸运…）逐位对上。
//        ★★ **这一条同时纠正了批次 300 的一个负结果**：那批说"`+0x1958` 只有一个位测试
//          （`tbz w8,#0x8`）、不够格当缓存字" —— 那是**工具的盲点**：
//          `EvaluateItems` 先把地址算进 `x21`（`mov w8,#0x1958` + `add x21,x19,x8`），
//          之后用 `ldr w8,[x21]` 读，位测试**不落在"`[x19,#0x1958]` 立即数形态"上** ⇒
//          只扫立即数寻址的扫描器（`tools/nro_find_bit_readers.py 0x1958`）**看不见它们**。
//          "0/1 处命中" ≠ "没有位测试"（与 `nro_find_offset_access.py` 那条同一类盲点）。
//
//   ④ **取值锚点（`semantic` 证据用）**：`Entity_Player::DonateLuck @ 0x2f9978`（mangled
//      `_ZN15IsaacRepentance13Entity_Player10DonateLuckEi`）——"捐款加运气"这个入口**同时**
//      加计数器、**并给这一格 OR 进 `CACHE_LUCK`**：
//        002f9980  ldr  w9, [x0, #0x1958]
//        002f9988  orr  w8, w9, #0x400     ; ★ 0x400 = bit10 = `CACHE_LUCK`
//        002f998c  str  w8, [x0, #0x1958]
//        002f9990  b    Entity_Player::EvaluateItems
//      ★ 与 PC 侧**同一个位**：PC 的 `DonateLuck` 也写 `or [this+0x14b8], 0x400`
//        （`0x427d51` / `0x5f38bb` 两处）⇒ 两侧"这位 = 幸运缓存"完全一致，
//        偏移数值不同（PC `0x14B8` / Switch `0x1958`）是布局差异，**不许互相平移**。
//
//   ⑤ **频度旁证**：全镜像扫"同一偏移的读-改-写"（`ldr wD,[xN,#imm]` … `orr wD,wD,..` …
//      `str wD,[xN,#imm]`）得 `+0x1958` **103 处**（第二名只有 42 处），且访问者是
//      `UsePill`(30) / `update_babies`(24) / `Update`(22) / `UseActiveItem`(21) /
//      `AddCollectible`(14) / `TakeDamage`(14) / `update_effects`(14) / `EvaluateItems`(12) /
//      `RemoveCollectible`(10) … —— 全是"道具/药丸/受击之后要让属性重算"的那一族。
//
// 类型：**u32**（两侧全按 32 位 `ldr/str w?` / `or dword` 访问；`DonateLuck` 的 `#0x400`
//   也只落在低 32 位里）。PC 文档 `EntityPlayer.md:108/109`（`void AddCacheFlags(CacheFlag)`，
//   正文 "Will reevaluate the cache flags provided in the next cache reevaluation."）。
//
// 为什么必须实现（不实现会出什么）：`AddCacheFlags` 在语料里 **4 个模组 / 34 处**，全是
//   "改了属性之后让引擎重算"的收尾动作（`Trinity`、`RepentancePlus`、`IsaacOnTwitchReloaded`、
//   `BOIStageAPI15`）。缺它 ⇒ `p:AddCacheFlags(...)` 调 nil ⇒ **整条回调当场中断**，
//   于是"改了的伤害/速度根本没生效"、而且**屏幕上什么都看不到**（用户只看到"这个道具没效果"）。
//   ★ 更隐蔽的一层：`CacheFlag` 是个**全局枚举表**（模组写 `CacheFlag.CACHE_DAMAGE`），
//     表没发的话 `CacheFlag.CACHE_DAMAGE` 本身就是 nil ⇒ 就算方法在也仍然抛错
//     （"API + 枚举表常常是同一件事的两半"，批 269/292/297 的先例）⇒ 本批**两半一起做**。
//   取证命令：`python3 tools/nro_disasm.py 0x293660 0x40`（AddCollectible 的 OR）
//             `python3 tools/nro_disasm.py 0x28bb4c 0x28`（EvaluateItems 的位测试）
//             `python3 tools/nro_disasm.py 0x2f9978 0x20`（DonateLuck 的 0x400）
//             `python3 tools/pc_exe_binding.py AddCacheFlags --disasm`（PC 的 `or [ecx+0x14b8]`）
//   布局表：`tools/layout_tables/entity_player.json` 的 `CacheFlags` 行（`confirmed`）。
inline constexpr uintptr_t kEntityPlayerCacheFlagsOffset = 0x1958;      // u32 缓存标志位掩码

// `Entity_Player` 的主动道具/饰品/婴儿皮肤（"批次 4 顺带确认的小偏移"）。
inline constexpr uintptr_t kEntityPlayerActiveItemOffset = 0x1964;      // 每槽步长 0x1C
inline constexpr uintptr_t kEntityPlayerActiveItemStride = 0x1C;
inline constexpr uintptr_t kEntityPlayerActiveItemChargeOffset = 0x1968;        // slot 基址 +4
inline constexpr uintptr_t kEntityPlayerActiveItemSecondChargeOffset = 0x196C;  // slot 基址 +8
inline constexpr uintptr_t kEntityPlayerActiveItemMaxChargeOffset = 0x197C;     // slot 基址 +0x18
inline constexpr uintptr_t kEntityPlayerTrinketOffset = 0x1AB0;         // 每槽步长 4，共 2 槽
inline constexpr std::size_t kEntityPlayerTrinketSlotCount = 2;
inline constexpr uintptr_t kEntityPlayerBabySkinOffset = 0x20E8;       // signed，非婴儿 = -1

// ============================================================================
// 批次 195（2026-09-29）：`Entity_Player` 上本批新定位的四组字段
// （证据规格：`analysis/api-restore-entityplayer-b/spec.json`、`analysis/api-restore-rng/spec.json`）
// ============================================================================

// `EntityPlayer:HasGoldenBomb()`（catalog `0x0E01004A`）= `Entity_Player + 0x16D9` 那**一个字节**。
// **取值锚点**是引擎自己的一对同名函数（所以这一格不是"某处有个字节"，而是 1/0 都见过）：
//   * `Entity_Player::AddGoldenBomb() @ 0x2FC3F0`：`0x2FC3F0 mov w8,#0x16d9` /
//     `0x2FC3F4 add x8,x0,x8` / `0x2FC3F8 mov w9,#1` / `0x2FC3FC strb w9,[x8]` ⇒ 置 1；
//   * `Entity_Player::RemoveGoldenBomb() @ 0x2FC490`：同一组 `mov/add` + `strb wzr,[x8]` ⇒ 清 0。
// 互证：紧挨着的 `0x16D8` 是"金**钥匙**"标志（`AddGoldenKey @ 0x280588` / `RemoveGoldenKey @ 0x280628`
// 写法逐字同形，PC 同样有一对 `HasGoldenKey`/`AddGoldenKey`）⇒ 两个相邻字节 = 两个"金色 X"标志。
// 旁证：这两个函数还会把同一个字节**复制给同局每个玩家**（遍历 `Game+0x25C50` 的玩家向量）⇒
// 它是"每玩家一份"的状态位，读**当前接收者**的那一份即可。
inline constexpr uintptr_t kEntityPlayerGoldenBombFlagOffset = 0x16D9;  // u8，非 0 即真

// 四张 `std::vector<RNG>`（每格 16 字节 = `kRngObjectSize`；begin/end/cap 各 8 字节）。
// 它们就是 PC 四条 `Get*RNG` 的数据源（镜像里**没有**这四个名字，见规格的
// `engine_absent_check`），**索引就是枚举 id 本身**：
//   * `PlayerManager::FirstCollectibleOwner(eCollectibleType, RNG**, bool) @ 0x4417AC`：
//     `0x441860 ldr x9,[x22,#0x1bb8]`（end）/ `0x441864 ldr x8,[x22,#0x1bb0]`（begin）/
//     `lsr x9,x9,#4`（元素 16 字节）/ `0x44188C add x8,x8,w20,UXTW #4`（`&_collectibleRNGs[id]`），
//     越界文案 `0x8A4B78 "Collectible ID out of bounds!"`；
//   * `PlayerManager::FirstTrinketOwner(eTrinketType, RNG**, bool) @ 0x441A68`：同形，`0x1BC8`/`0x1BD0`，
//     越界文案 `0x8B2559`；
//   * `Entity_Player::UsePill(ePillEffect, ePillColor, uint) @ 0x2DFC04`：`0x2E0010/0x2E0014` 读
//     `0x1BE8`/`0x1BE0`，越界文案 `0x8933F3`；`0x2DFCFC-0x2DFD08` 是 `_pillRNGs[id].Random(50)`
//     （**索引就是 PillEffect 本身**）；
//   * `Entity_Player::UseCard(eCard, uint) @ 0x2E9040`：`0x2E912C/0x2E9130` 读 `0x1C00`/`0x1BF8`，
//     越界文案 `0x891503`；`0x2E909C-0x2E90A8` 是 `_cardRNGs[id].Random(97)`。
// 独立旁证：`Entity_Player::Init @ 0x278D94` 对这四张表各跑一个 `push_back` 循环
// （`0x278E18/0x278EB8/0x278F50/0x278FF0` 的 `mov w8,#0x1BB0/0x1BC8/0x1BE0/0x1BF8` +
// `bl 0x27A530`（`std::vector<RNG>::push_back`，容量检查用 `>>4`、写入用 `#0x10` 步长））；
// `StoreGameState` 存盘时按 begin/end 整表拷走。
// ★ **元素个数不写死**：`Init` 按一个全局对象里的源列表长度建表 ⇒ 运行时按 `(end-begin)/16` 算
//   （已知下界：card 表 > 45，见 `Room::update_card_against_humanity @ 0x468AA4` 的 `cmp w9,#0x2d`）。
inline constexpr uintptr_t kEntityPlayerCollectibleRngVectorOffset = 0x1BB0;  // std::vector<RNG>
inline constexpr uintptr_t kEntityPlayerTrinketRngVectorOffset = 0x1BC8;
inline constexpr uintptr_t kEntityPlayerPillRngVectorOffset = 0x1BE0;
inline constexpr uintptr_t kEntityPlayerCardRngVectorOffset = 0x1BF8;
//: `std::vector<RNG>` 的元素步长（= `kRngObjectSize`）。四处 `lsr x9,x9,#0x4` 共同证明。
inline constexpr std::size_t kEntityPlayerRngVectorStride = 16;

// `EntityPlayer.QueuedItem`（**属性**，不是方法；catalog 里没有它 ⇒ 走 `PushEntityPlayerField`
// 的名字分派）：`QueueItemData` **内嵌**在 `Entity_Player + 0x1C38`，四个字段 / 步长 0x18。
// 三个独立函数给出同一组偏移（写 / 读 / 清）：
//   * 写 `Entity_Player::QueueItem(ItemConfig::Item const*, int, u8, int) @ 0x2924A4`：
//     `0x2924D8 str x20,[x19,#0x1c38]`（Item*）/ `0x2924DC str w23,[x19,#0x1c40]`（Charge）/
//     `0x2924E0 strb w22,[x8,#0xc]`（Touched，x8 = x19+0x1C38）/ `0x2924E4 str w21,[x19,#0x1c48]`（VarData）；
//   * 读 `Entity_Player::FlushQueueItem() @ 0x2926D4`：同一组偏移（并把 `Touched` 当布尔用）；
//   * 清 `Entity_Player::DestroyQueueItem() @ 0x292918`：四条 `str/strb` 清同一个结构。
// ★ PC 的 `QueueItemData` 只有 `Item`/`Charge`/`Touched` 三个字段（`QueueItemData.md`）；
//   `VarData`（`+0x10`）引擎里有、文档里没有 ⇒ **不对外暴露**（常量仍登记，便于将来核对）。
inline constexpr uintptr_t kEntityPlayerQueuedItemOffset = 0x1C38;
inline constexpr uintptr_t kQueuedItemDataItemOffset = 0x00;     // ItemConfig::Item*（8 字节）
inline constexpr uintptr_t kQueuedItemDataChargeOffset = 0x08;   // int32
inline constexpr uintptr_t kQueuedItemDataTouchedOffset = 0x0C;  // u8（布尔）
inline constexpr uintptr_t kQueuedItemDataVarDataOffset = 0x10;  // int32（PC 文档未列，不对外）

// ============================================================================
// 批次 195（2026-09-29）：`EntityPlayer` 组 A 的五条字段（证据规格
// `analysis/api-restore-entityplayer-a/spec.json`，全部**确证**）
// ============================================================================

// `EntityPlayer:GetHearts()`（catalog `0x0E01003A`）= `Entity_Player + 0x16BC`（u32，**半心为单位**）。
// 三条独立的"引擎自用路径"指向同一格：
//   * `Entity_Player::update_red_hearts() @ 0x27ECDC`：`0x27ECF4 ldr w8,[x0,#0x16bc]` →
//     `0x27ED0C asr w9,w9,#1`（半心→整心，夹出血心阈值 `+0x2474`）→ `0x27ED2C str w8,[x0,#0x16bc]`
//     —— 函数名就是"更新红心"，`asr #1` 定死了单位是**半心**；
//   * `Entity_Player::AddHearts(int, bool) @ 0x27F29C`：`0x27F3DC ldr w8,[x20,#0x16b8]`（容器）+
//     `0x27F3E0 ldr w9,[x20,#0x2450]`（骨心）+ `add w8,w8,w9,LSL #1`（上限 = 容器 + 2×骨心，
//     与 PC 正文 "heart containers and bone hearts" 逐字对上）→ 取-加-夹-存 `+0x16BC`；
//   * `Entity_Player::SetFullHearts() @ 0x2B0B88`：`mov w8,#0x16bc` + 把容器数写进去 ⇒ 满血 = 本字段。
// 200 条字面访问全部落在血量路径上（`check_death` 的 `str w31` 清零、`TakeDamage`、`AddSoulHearts`…）。
// ⚠️ **别接成 `+0x16B8`**（那是容器/上限，已实现的 `GetMaxHearts` 读它）。
inline constexpr uintptr_t kEntityPlayerHeartsOffset = 0x16BC;

// `EntityPlayer:GetPoopMana()`（`0x0E01003E`）= `Entity_Player + 0x269C`（u32）。
// 引擎自己的 `AddPoopMana(int) @ 0x2BAF44`（取-加-夹-存，上限 9、Tainted ??? 带 Birthright(619) 时 29，
// 并把同一个值镜像给 `players` 向量里每个玩家）与同级 `GetMaxPoopMana() @ 0x3004A4`（同一组分支）
// 双双指向这一格；40 条访问全在消耗品路径上（`store/restore_consumable_data`、`sync_consumable_counts`、
// `RenderSpellQueue` 用它决定法术队列画几格）。
inline constexpr uintptr_t kEntityPlayerPoopManaOffset = 0x269C;

// `EntityPlayer:GetPoopSpell(int Position)`（`0x0E01003F`）：队列 = `Entity_Player + 0x26A0`，**6 格 u8**。
//   * `Entity_Player::UsePoopSpell() @ 0x2BAEF8`：`mov w8,#0x26a0 / add x20,x0,x8` 取队首 `ldrb w1,[x20]`
//     → 调 `UsePoopSpell(ePoopSpellType)` → 整体左移一格（`ldurh/strh` + `ldrb/strb`）→ 末格 `strb wzr,[x20,#0x5]`
//     ⇒ 恰好 6 格、`Position 0` = 下一个要用的；
//   * `Entity_Player::CheckPoopSpellQueue() @ 0x2FA590`：`cmp x26,#0x6` 循环上界 6、`add x9,x8,#0x26a0`；
//   * 初始化 `Init @ 0x278D94` 的 `str x31,[x19,#0x26a0]`（8 字节清零，前 6 字节是队列）；
//   * HUD 消费者 `RenderSpellQueue @ 0x3A8668` 直接取 `+0x26A5`（第 6 格）去画。
// ★ **必须自己夹 [0,5]**：引擎三处访问全是编译期常量下标、运行时从不检查；`Position = 6` 会读到
//   `+0x26A6`（同一次清零的邻接字节），更大就读到无关字段。PC 没给越界口径 ⇒ 我们给 0（= SPELL_NONE）。
inline constexpr uintptr_t kEntityPlayerPoopSpellQueueOffset = 0x26A0;   // u8[6]
inline constexpr std::uint32_t kEntityPlayerPoopSpellQueueSlots = 6;

// `EntityPlayer:GetModelingClayEffect()`（`0x0E010041`）= `Entity_Player + 0x2730`（int32，CollectibleType）。
// ★ 决定性证据是**存档字段与玩家字段是同一个值的存取两端**：
//   * `Entity_Player::StoreGameState(GameStatePlayer&) @ 0x2F8224`：`0x2F8C58 ldr w8,[x20,#0x2730]` →
//     `0x2F8C5C str w8,[x19,#0x608]`（x19 = GameStatePlayer）；`RestoreGameState @ 0x2C3ED4` 反向照抄；
//   * 而 `GameStatePlayer::Read @ 0x373E84` 在 `0x377E78 ldr w8,[x20,#0x608]` 之后校验
//     `0x377EB4 bl ItemConfig::GetCollectible(int)`，不合法就打到**唯一一处**引用的字符串
//     `"[warn] Invalid modeling clay effect %d\n"`（@0x89157F）—— 字符串自己说明了这一格叫什么。
// 另 14 处访问全在橡皮泥语义上（`HasCollectible`/`NumCollectibleHeld` 读它、每房间重抽的
// `TriggerNewRoom_TemporaryEffects` 先清后写、失去饰品 166 时清掉）。没模仿时引擎写 0。
inline constexpr uintptr_t kEntityPlayerModelingClayEffectOffset = 0x2730;

// ============================================================================
// TemporaryEffects（批次 388，2026-10-07）—— `EntityPlayer:GetEffects()` 的返回值
// ============================================================================
//
// 背景：PC 的 `EntityPlayer:GetEffects()` 返回 `TemporaryEffects` 对象（`EntityPlayer.md:951`），
// 它挂着 17 个方法（逐字节契约副本 = `analysis/isaacdocs-snapshot/docs/TemporaryEffects.md`）。
// 我们此前**恒返回空表** ⇒ 模组写 `player:GetEffects():HasCollectibleEffect(id)` 是在空表上取
// 方法 ⇒ 抛 `attempt to call a nil value` ⇒ **整条回调被派发器静默摘掉**（minimapi 的小地图
// 画不出来就是这么来的；EID `features/eid_itemprediction.lua:540` 是同一个写法）。
//
// --- 容器：**内嵌**在 Entity_Player 里，偏移 0x18D8 ---
// 三处独立函数都用 `add x?, x?, #0x18D8` 算同一个 this：
//   * `Entity_Player::ClearTemporaryEffects() @ 0x2DCCD4`：`0x2DCCEC mov w8,#0x18d8` /
//     `add x0,x19,x8` → 传进 `TemporaryEffects::ClearEffects`；
//   * `Entity_Player::Init @ 0x279160-0x279170`：`add x0,x19,#0x18D8` / `mov w1,#1` /
//     `bl TemporaryEffects::ClearEffects`（本批实测反汇编逐条确认）；
//   * `Entity_Player::TriggerNewRoom_TemporaryEffects() @ 0x2F476C`：`0x2F47DC mov w8,#0x18d8`。
// ⇒ `&player->TemporaryEffects == player + 0x18D8`（**内嵌、不是指针**，所以取地址相加即可）。
// 布局（构造 `TemporaryEffects::TemporaryEffects(Entity_Player*) @ 0x4A6748` / 析构 `@ 0x4A6760`）：
//   +0x00 u32；+0x08/+0x10 = `std::vector<TemporaryEffect>` 的 begin/end；+0x20 两字节
//   （+0x21 = 冻结标志，Update/GetEffectNum 第一句都读它）；+0x28 = 反指 `Entity_Player*`。
//   `sizeof(TemporaryEffects) = 0x30`；元素步长 0x10（`ItemConfig::Item* @+0x00`、
//   `u32 count @+0x08`、`u32 remaining @+0x0C`）。容器偏移证据见
//   `analysis/api-restore-entityplayer-b/spec.json`（"GetEffects" 那一项）。
inline constexpr uintptr_t kEntityPlayerTemporaryEffectsOffset = 0x18D8;
inline constexpr uintptr_t kTemporaryEffectsEffectListBeginOffset = 0x08;
inline constexpr uintptr_t kTemporaryEffectsEffectListEndOffset = 0x10;
inline constexpr uintptr_t kTemporaryEffectsPlayerBackrefOffset = 0x28;
inline constexpr uintptr_t kTemporaryEffectsElementStride = 0x10;

// --- 引擎方法：全部取自 `Repentance.nro` 的**动态符号表**（不是猜的）---
// 取法（2026-10-07 本批实测）：`tools/nro_symbols.py` 的 `parse_dynamic_symbols()` 列出全部
// 34 条含 `TemporaryEffects` 的符号并给 file_offset；入口 4 字节指纹按**小端整字**取
// （与 `runtime_constants.hpp` 既有常量同一口径）。
// ★★ 本族指纹**很弱**：`HasEffect`×3 与 `GetEffectNum`×3 的首 4 字节**全是** `0x39408408`
//    （= `ldrb w8,[x0,#0x21]`），`AddEffect`×3 全是 `0xD10103FF`，`RemoveEffect`×3 全是
//    `0xD100C3FF` ⇒ 指纹只能证明"模块基址对"，**证明不了偏移没写错**。
//    ⇒ 这族必须靠偏移本身 + 宿主/真机读数兜底（与 `PathFinder` 那条同一声明）。
// ★★ **更正**：`docs/会话交接-20261005-十六-…` 第六节那张 "TemporaryEffects 真身" 表**整体是错的**
//    （它写 `HasEffect(eCollectibleType) = 0x4A6A20`、`GetEffectNum = 0x4A6D78` …，真值分别是
//    `0x4A6D60` / `0x4A7228`，差 0x340 上下）。本段的值以动态符号表为准 —— 那张表按它自己的
//    标注"入口 16 字节守卫还没核对"，本批核对时发现偏移也不对。
// 引擎符号 → 常量（括号内是 mangled 名的类型后缀，用来区分同名重载）：
//   `HasEffect(eCollectibleType) const`  → kTemporaryEffectsHasCollectibleEffectOffset
//   `HasEffect(eTrinketType) const`      → kTemporaryEffectsHasTrinketEffectOffset
//   `HasEffect(eNullItemID) const`       → kTemporaryEffectsHasNullEffectOffset
//   `GetEffectNum(eCollectibleType) const` → kTemporaryEffectsGetCollectibleEffectNumOffset
//   `GetEffectNum(eTrinketType) const`     → kTemporaryEffectsGetTrinketEffectNumOffset
//   `GetEffectNum(eNullItemID) const`      → kTemporaryEffectsGetNullEffectNumOffset
//   `AddEffect(eCollectibleType,bool,unsigned int)` → kTemporaryEffectsAddCollectibleEffectOffset
//   `AddEffect(eTrinketType,bool,unsigned int)`     → kTemporaryEffectsAddTrinketEffectOffset
//   `AddEffect(eNullItemID,bool,unsigned int)`      → kTemporaryEffectsAddNullEffectOffset
//   `RemoveEffect(eCollectibleType,unsigned int)`   → kTemporaryEffectsRemoveCollectibleEffectOffset
//   `RemoveEffect(eTrinketType,unsigned int)`       → kTemporaryEffectsRemoveTrinketEffectOffset
//   `RemoveEffect(eNullItemID,unsigned int)`        → kTemporaryEffectsRemoveNullEffectOffset
// 2026-10-09：PC const视图的字段名是Cooldown（不是旧台账的TimeLeft）。
inline constexpr uintptr_t kTemporaryEffectsFrozenOffset = 0x21;
inline constexpr uintptr_t kTemporaryEffectCountOffset = 0x08;
inline constexpr uintptr_t kTemporaryEffectCooldownOffset = 0x0C;
inline constexpr uintptr_t kTemporaryEffectsClearEffectsOffset = 0x4A6E60;
inline constexpr std::array<std::uint8_t, 16> kTemporaryEffectsClearEffectsEntryBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFB, 0x0B, 0x00, 0xF9, 0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9};

inline constexpr uintptr_t kTemporaryEffectsHasCollectibleEffectOffset = 0x4A6D60;
inline constexpr std::uint32_t kTemporaryEffectsHasCollectibleEffectEntryWord = 0x39408408U;
inline constexpr uintptr_t kTemporaryEffectsHasTrinketEffectOffset = 0x4A6DC4;
inline constexpr std::uint32_t kTemporaryEffectsHasTrinketEffectEntryWord = 0x39408408U;
inline constexpr uintptr_t kTemporaryEffectsHasNullEffectOffset = 0x4A6E14;
inline constexpr std::uint32_t kTemporaryEffectsHasNullEffectEntryWord = 0x39408408U;
inline constexpr uintptr_t kTemporaryEffectsGetCollectibleEffectNumOffset = 0x4A7228;
inline constexpr std::uint32_t kTemporaryEffectsGetCollectibleEffectNumEntryWord = 0x39408408U;
inline constexpr uintptr_t kTemporaryEffectsGetTrinketEffectNumOffset = 0x4A7290;
inline constexpr std::uint32_t kTemporaryEffectsGetTrinketEffectNumEntryWord = 0x39408408U;
inline constexpr uintptr_t kTemporaryEffectsGetNullEffectNumOffset = 0x4A72E4;
inline constexpr std::uint32_t kTemporaryEffectsGetNullEffectNumEntryWord = 0x39408408U;
inline constexpr uintptr_t kTemporaryEffectsAddCollectibleEffectOffset = 0x4A6924;
inline constexpr std::uint32_t kTemporaryEffectsAddCollectibleEffectEntryWord = 0xD10103FFU;
inline constexpr uintptr_t kTemporaryEffectsAddTrinketEffectOffset = 0x4A6994;
inline constexpr std::uint32_t kTemporaryEffectsAddTrinketEffectEntryWord = 0xD10103FFU;
inline constexpr uintptr_t kTemporaryEffectsAddNullEffectOffset = 0x4A6A04;
inline constexpr std::uint32_t kTemporaryEffectsAddNullEffectEntryWord = 0xD10103FFU;
inline constexpr uintptr_t kTemporaryEffectsRemoveCollectibleEffectOffset = 0x4A6BA0;
inline constexpr std::uint32_t kTemporaryEffectsRemoveCollectibleEffectEntryWord = 0xD100C3FFU;
inline constexpr uintptr_t kTemporaryEffectsRemoveTrinketEffectOffset = 0x4A6C00;
inline constexpr std::uint32_t kTemporaryEffectsRemoveTrinketEffectEntryWord = 0xD100C3FFU;
inline constexpr uintptr_t kTemporaryEffectsRemoveNullEffectOffset = 0x4A6C60;
inline constexpr std::uint32_t kTemporaryEffectsRemoveNullEffectEntryWord = 0xD100C3FFU;

// `EntityPlayer:GetPlayerFormCounter(ePlayerForm)`（`0x0E010045`）：
// 计数器数组 = `Entity_Player + 0x1C54`，**15 个 int32**（= `NUM_PLAYER_FORMS`，form 0..14）。
//   * `Entity_Player::increment_player_form_counter(ePlayerForm, int) @ 0x29813C`：
//     `0x298160 add x9,x0,w1,UXTW #0x2`（步长 4，按 form 索引）→ `ldr w11,[x9,#0x1c54]` →
//     `+ delta` → `bic`（夹 ≥ 0）→ `str w11,[x9,#0x1c54]`；
//   * `Entity_Player::HasPlayerForm(ePlayerForm) @ 0x298510`：读同一格 + `cmp w8,#0x2` + `cset gt`
//     ⇒ **"有没有这个形态" = 计数器 > 2**（第 3 件才算成套），语义确证；
//   * 数组长度由 `RestoreGameState` 的**存档连续复制证明**：`0x2C41F8–0x2C426C` 恰好 15 组
//     `ldr w8,[x20,#0x10C+4i] / str w8,[x19,#0x1C54+4i]`（i = 0..14），紧接着 `+0x1C90` 是另一个
//     8 字节字段 ⇒ 不多不少 15 格。
// ★ **必须自己夹 [0,14]**：三个引擎函数全是直接索引、没有任何边界检查；`form = 15` 会读到
//   `+0x1C90`（8 字节指针的低半）。PC 没给越界口径 ⇒ 我们给 0。
// ⚠️ PC 官方文档里**没有**这条（它是 Repentogon 扩展）⇒ 形状取自签名
//   （`analysis/lua-api-inventory/inventory.json` 的 `int GetPlayerFormCounter(PlayerForm)`）+ 引擎语义。
inline constexpr uintptr_t kEntityPlayerFormCountersOffset = 0x1C54;   // int32[15]
inline constexpr std::uint32_t kEntityPlayerFormCounterCount = 15;

// `EntityPlayer:HasTrinket(TrinketType, bool)` 的引擎入口
// （`IsaacRepentance::Entity_Player::HasTrinket(eTrinketType, bool) const`，mangled
// `_ZNK15IsaacRepentance13Entity_Player10HasTrinketENS_12eTrinketTypeEb`）。
// 引擎自己就实现了 PC 文档的两种口径 —— `IgnoreModifiers == true` 时扫两个饰品槽
// （`0x28D428 ldr w9,[x20,#0x1ab0]` / `and w9,w9,#0x7fff` / `cmp w9,w19`；槽 1 在 `+0x1ab4`，
// **低位 15 位才是 id、高位是金色标志**），`false` 时改问
// `Entity_Player::GetTrinketMultiplier(eTrinketType)`（`0x28D400-0x28D420`，返回"倍率 > 0"）。
// ⇒ 直接调它比自己扫槽便宜且对（旧实现逐位相等 ⇒ **金色饰品答 false**，而且读不到
//   "由其它道具赋予的饰品效果"那一族）。
inline constexpr uintptr_t kEntityPlayerHasTrinketOffset = 0x28D3B8;
//: `0x28D3B8` 的入口首 4 字节（小端整字）：`stp x29,x30,[sp,#-0x20]!`。
inline constexpr std::uint32_t kEntityPlayerHasTrinketEntryWord = 0xA9BE7BFD;

// Entity_Player::GetTrinketMultiplier(eTrinketType) const includes held/golden,
// swallowed and simulated trinkets, plus Mom's Box. HasTrinket(false) calls it.
inline constexpr uintptr_t kEntityPlayerGetTrinketMultiplierOffset = 0x29B030;
inline constexpr std::array<u8, 16> kEntityPlayerGetTrinketMultiplierExpectedBytes = {
    0xFF, 0x43, 0x01, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9,
};

// `Level` **内嵌在 `Game` 起始处**（见 `docs/问题与解决记录.md` 批次 4 的"更正旧记录"：
// `Level+0x21550` 与 `Game+0x21550` 是同一个地址），所以 `Level* == Game*`，
// `Level:GetCurses()` 读的就是 `Game + 0x0C`（u32 位掩码）。
inline constexpr uintptr_t kLevelCursesOffset = 0x0C;

// `ItemPool`：PC Lua 的 `GetLastPool()` 在 Switch NRO 里没有同名 C++ 访问器，属于字段直读。
// `ItemPool::GetCollectible` 在 `0x3C64C0`、`0x3C66E8` 都把最终选用的池类型写入
// `[ItemPool + 0x8C0]`；`get_chaos_pool()` 返回该池后立即写回，证明这里保存的就是最近一次
// `GetCollectible` 实际使用的池。
inline constexpr uintptr_t kItemPoolLastPoolOffset = 0x8C0;

// 药丸的两张并行小表（批次 13，2026-09-16）：PC Lua 的 `ItemPool:IsPillIdentified(PillColor)`
// 就是读第二张表的第 color 个字节。三条互相独立的指令作证：
//   * 读表一：`ItemPool::GetPillEffect(ePillColor, Entity_Player*) @ 0x3C857C` 里
//     `and w8, w1, #0x7ff` → `add x8, x0, w8, uxtw #2` → `ldr w20, [x8, #0xa2c]`
//     —— 按颜色取药丸效果，颜色先被 **0x7ff** 掩码（IsaacDocs 的 `PILL_COLOR_MASK`）；
//   * 表二的语义锚点：`HUD::PlayerHUD::RenderPocketItems @ 0x3A6094` 在 0x3A6608 处
//     `ldrb w9, [Game + 0x24D28 + color]`，非 0 就显示药丸真名，为 0 就显示字符串表里的
//     `#QUESTION_MARKS_NAME`（"???"）—— `Game + 0x242C0` 正是 `ItemPool`
//     （见 `game_observer.cpp` 的 `kGameItemPoolOffset`），所以那个字节就是"这个颜色认不认得"；
//   * 表二的写入：`ItemPool::RestoreGameState @ 0x3CA1A0` 把存档里的 15 组
//     `[state+0x3b0+4i] → [this+0xa2c+4i]`（药丸效果）与 `[state+0x3ec+i] → [this+0xa68+i]`
//     （识别位）逐条展开写回；`ItemPool::RerollPillEffect(ePillColor, uint, bool) @ 0x3CAA7C`
//     也在重掷时写 `[this+0xa68+color] = 第三个参数 & 1`。
// 数量 15 = IsaacDocs `enums/PillColor.md` 的 `NUM_PILLS`（普通药丸 0..13 + 金色药丸 14），
// 与"0xa2c 起 15×4 字节后正好是 0xa68"这条算术完全吻合。
inline constexpr uintptr_t kItemPoolPillEffectOffset = 0xA2C;
inline constexpr uintptr_t kItemPoolPillIdentifiedOffset = 0xA68;
inline constexpr std::uint32_t kPillColorCount = 15;
inline constexpr std::uint32_t kPillColorMask = 0x7FF;

// ItemPool::ResetTrinkets @0x3C78FC..0x3C7980 reads begin/end and divides
// their difference by 8. RemoveTrinket @0x3C7B34 indexes this vector unchecked.
inline constexpr uintptr_t kItemPoolTrinketBeginOffset = 0xA10;
inline constexpr uintptr_t kItemPoolTrinketEndOffset = 0xA18;
inline constexpr std::size_t kItemPoolTrinketEntryBytes = 8;

// --- ItemConfig（2026-09-12 反汇编 + 真机现象逐位互证）--------------------------------
//
// 陷阱（上一轮探针失败的根因）：`ItemConfig` **内嵌**在 `Manager` 里，**不存在指向它的指针**。
// 正确链路是"取地址"，不是"取值"：
//
//   mslot = *(u64*)(base + kGameManagerGlobalSlotOffset)   // 槽内容 = base + 0xABCCE0
//   M     = *(u64*)mslot                                   // Manager*（两级解引用）
//   IC    = M + kManagerItemConfigOffset                   // ★加法：内嵌对象
//
// 反汇编硬证据（`tools/nro_disasm.py`，build `91C73FDD…`）：
//   * `ItemConfig::IsValidCollectible(eCollectibleType)`（`0x3C0D64`）自己就是
//     `ldr x8,[x8,#0x648]`（`g_Manager`）→ `ldr x8,[x8]` → `add x8, x8, #0x36538`，
//     即同一枚"加法"形态；`mov w9,#0x6538; movk w9,#0x3,lsl #16` 就是 0x36538。
//   * `Manager::Manager`（`0x3F3B00`）在 `0x3F3C58` 处
//     `mov w8,#0x6538; movk w8,#0x3,lsl #16; add x0,x19,x8; bl ItemConfig::ItemConfig()`
//     —— `x19` 就是 `Manager` 自身，**加法**组成地址；紧随其后 `0x3F3C68` 的
//     `mov w8,#0x6740 …`（下一个成员）证明 `ItemConfig` 占 `[0x36538, 0x36740)`，
//     即 `sizeof(ItemConfig) == 0x208`（`EntityConfig` 的构造在 `+0x36758`）。
//   * 把 `*(M + 0x36538)` 当指针用会读到 `collectibles.begin()`（真机观测 `0x3954852000`），
//     随后 `items[0]==0` 时的 `*(u64*)8` 又被可读性检查拦掉 —— 与旧报告"第 6 位不亮"逐位吻合。
inline constexpr uintptr_t kManagerItemConfigOffset = 0x36538;

// 并列向量（同一个 `IC` 上，全部是 `std::vector<ItemConfig::Item*>`：begin/end 相邻两个 u64，
// 步长 8）。偏移逐个来自各自 getter 的第一条 `ldp`（符号名即 getter 名）：
//   * `0x3C0C50 ItemConfig::GetCollectible(int) const`   → `ldp x8,x9,[x0]`      → +0x00/+0x08
//   * `0x3C0C9C ItemConfig::GetTrinket(int) const`       → `ldp x9,x10,[x0,#0x18]`→ +0x18/+0x20
//   * `0x3C0CC4 ItemConfig::GetNullItem(int) const`      → `ldp x8,x9,[x0,#0x30]` → +0x30/+0x38
//   * `0x3C0CEC ItemConfig::GetPillEffect(ePillEffect)`  → `ldp x8,x9,[x0,#0x60]` → +0x60/+0x68
//   * `0x3C0D14 ItemConfig::GetCard(int) const`          → `ldp x8,x9,[x0,#0x48]` → +0x48/+0x50
//   * `0x3C0D3C ItemConfig::GetPlayerForm(ePlayerForm)`  → `ldp x8,x9,[x0,#0x90]` → +0x90/+0x98
// 每个 getter 的其余三条指令都是同一形态：`sub end,begin` / `lsr #3` / `cmp` + `b.le` →
// 越界返回空指针，然后 `ldr x0,[begin, w1, uxtw #3]`。所以"条目就是向量元素"是被反汇编证实的。
//
// 数量硬判据：`ItemConfig::Init`（`0x3B4138`）先 `cmp x10, #0x2dc; b.hi`，否则
// `mov w8, #0x2dd`（733）后 `vector::__append(733 - n)`；另一支 `mov w10, #0x16e8`（5864）
// 直接比较字节长度。**733 × 8 == 0x16E8** 就是收藏品向量的长度硬判据（真机探针用它）。
// 顺带：`Init` 里 Trinket 向量（`IC+0x18`）预分配 0xBE == 190 项（0x5F0 字节）。
inline constexpr uintptr_t kItemConfigGetCollectibleOffset = 0x3C0C50;
inline constexpr uintptr_t kItemConfigCollectibleCount = 733;
inline constexpr uintptr_t kItemConfigCollectibleVectorBytes = 0x16E8;  // 733 × 8
inline constexpr uintptr_t kItemConfigTrinketCount = 190;               // 0xBE，`Init` 预分配
inline constexpr uintptr_t kItemConfigCollectibleBeginOffset = 0x00;
inline constexpr uintptr_t kItemConfigCollectibleEndOffset = 0x08;
inline constexpr uintptr_t kItemConfigTrinketBeginOffset = 0x18;
inline constexpr uintptr_t kItemConfigTrinketEndOffset = 0x20;
inline constexpr uintptr_t kItemConfigNullItemBeginOffset = 0x30;
inline constexpr uintptr_t kItemConfigNullItemEndOffset = 0x38;
inline constexpr uintptr_t kItemConfigCardBeginOffset = 0x48;
inline constexpr uintptr_t kItemConfigCardEndOffset = 0x50;
inline constexpr uintptr_t kItemConfigPillEffectBeginOffset = 0x60;
inline constexpr uintptr_t kItemConfigPillEffectEndOffset = 0x68;
inline constexpr uintptr_t kItemConfigPlayerFormBeginOffset = 0x90;
inline constexpr uintptr_t kItemConfigPlayerFormEndOffset = 0x98;

// `ItemConfig::Item`：**`Type`（`eItemType`）**、id、以及 libc++ `std::string` 形态的名字与
// 描述——**不是 `const char*`**，读取要按 SSO 规则（byte0 的 bit0 是 is_long）。
//
// ★ 2026-09-14 重新定案：`+0x00` 是 PC 的 `ItemConfig_Item.Type`（`eItemType`），
//   **不是**"向量类别"。三条独立证据（都在本文件提到的 build `91C73FDD…` 上）：
//   1. `items.xml` 解析器（`ItemConfig::Load`，`0x3B50E0`）把 `type` 属性**原样**写进 `+0x00`：
//      `"passive"`→`str w8(=1),[x27]`（`0x3B57B8`）、`"trinket"`→2（`0x3B57DC`）、
//      `"active"`→3（`0x3B57F8`）、`"familiar"`→4（`0x3B581C`）、`"null"`→0（`0x3B5840`）。
//      这 5 个值恰好是冻结文档 `enums/ItemType.md` 的 `ITEM_NULL/PASSIVE/TRINKET/ACTIVE/FAMILIAR`。
//   2. `ItemConfig::Item::GetSoulChargeType()`（`0x3C19C0`）先 `ldr w9,[x0]` 再 `cmp w9,#0x3`
//      —— 只有"主动道具"（`ITEM_ACTIVE == 3`）才继续算充能类型。
//   3. `ItemConfig::Item::TemporaryEffectsAreInstances()`（`0x3C1804`）用 `1 << [x0]` 与
//      `0x1A`（bit 1/3/4）取交集，即该字段只取 {1,3,4} 这类小枚举值。
//   `id` 仍是 `+0x04`（同一解析器写 `"id"`，且 `0x3C19D0` 用它比 `0x146`/`0x28F` 两个收藏品 id）。
//   历史遗留：本常量曾叫 `kItemConfigItemKindOffset` 并被当成"1=COLLECTIBLE"，
//   于是 `ItemConfig:IsCollectible(id)` 曾要求 `Type == ITEM_PASSIVE`（见 `isaac_api.cpp`）。
//   偏移来源：`ItemConfig::Item::GetDisplayName(eLanguage)`（`0x3B9334`）的
//   `ldrb w8, [x21, #0x8]!`（前索引寻址直接落在 `+0x08`）与 `lsr x9, x8, #1`（短串 size = byte0>>1）；
//   `ItemConfig::Item::GetDisplayDescription(eLanguage)`（`0x3C0F08`）的
//   `ldrb w8, [x21, #0x20]!` → 描述在 `+0x20`。
inline constexpr uintptr_t kItemConfigItemTypeOffset = 0x00;
inline constexpr uintptr_t kItemConfigItemIdOffset = 0x04;
inline constexpr uintptr_t kItemConfigItemNameOffset = 0x08;
inline constexpr uintptr_t kItemConfigItemDescriptionOffset = 0x20;
// `GfxFileName`（PC 文档 `ItemConfig::Item::GfxFileName`，LuaDocs 里是 `string` 字段）在 `+0x38`。
// 偏移来源是 `items.xml` 解析器（`ItemConfig::Load`，`0x3B50E0`）自己的 `gfx` 属性分支：
//   * `0x3B58B4` 用 `strcmp(name, "gfx")` 命中后 `cbz` 跳到 `0x3B5B20`；
//   * 该分支先按 `Type` 选前缀 —— `Type == 2` 走 `"trinkets/"`（`0x3B5C50`），否则走
//     `"collectibles/"`（`0x3B5C9C`）—— 再把 XML 里的值 `append` 上去拼成完整路径；
//   * 两条路在 `0x3B5CE0..0x3B5D10` 汇合，把结果**整体写进 `[x27, #0x38]`**：
//     byte0 → `+0x38`、byte1 → `+0x39`、byte2..9 → `[sp,#0x60]`（= `x27+0x3A`，见 `0x3B5854`）、
//     长串数据指针 → `+0x48`，旧的堆块按 byte0 的 bit0 释放（`0x3B5CE4`/`0x3B5CEC`）。
// 同一段里 `description` → `+0x20`（`0x3B585C` 的 `add x8, x27, #0x20`）、`name` → `+0x08`
// （`0x3B5860` 的 `add x21, x27, #0x8`），与上面两条常量互为交叉验证。
// 形态与 `Name`/`Description` 相同：24 字节 libc++ 串占 `+0x38`..`+0x4F`，数据指针在 `+0x48`。
inline constexpr uintptr_t kItemConfigItemGfxFileNameOffset = 0x38;
// --- 批次 139（2026-09-26）：**null 服装**条目上的 anm2 路径与 id（`ItemConfig_Item +0x88` / `+0x80`）
//
// 为什么要它们：`Isaac:GetCostumeIdByPath(path)`（The Specialist for Good Items 的舞蹈服装要靠它反查 id）
// 必须"遍历 null 道具向量、比路径、返回 id" —— 而路径**不在** `+0x08 Name` / `+0x38 GfxFileName` 上
// （那两个是道具自己的名字与图集名），它在 `+0x88`。定案过程与本条的两条互证指令见
// `dist/specialist-costume-field-static.md`（2026-09-26，纯静态、只读仓库内镜像）：
//   * **写入侧** `ItemConfig::LoadCostumes(char const*, ModEntry*) @ 0x3B9448`
//     （前 16 字节 `fd7bbaa9fc6f01a9fd030091fa6702a9`）：`0x3B97C4` 用 `strcmp` 匹配 xml 键 `"anm2path"`，
//     命中后 `0x3B99A0`（`memcpy` anm2root 的值）+ `0x3B99C0`（`std::string::append` 接上 anm2path 的值）
//     拼成整串（例如 `the/specialist_isaac.anm2`），再 `0x3BA064 add x0,x19,#0x88` +
//     `0x3BA070 std::string::operator=` 写进 **条目 +0x88**；同一条路径上还写 `+0x80 = id`。
//   * **读取侧** `Entity_Player::AddCostume(ItemConfig::Item const*, bool) @ 0x290C38` 的
//     `0x290D7C ldrb w8,[x23,#0x88]!` —— 另一个函数按**同一个偏移**当"服装路径"判长短串，
//     且 SSO 口径（首字节 bit0 / 长串长度在串 `+0x8`）与运行时的 `PushLibcxxString` 完全一致。
//   * id 在 `+0x04`（`0x3B9FFC str w8,[x9,#0x4]`），而 `ItemConfig::GetNullItem(int) @ 0x3C0CC4`
//     是**纯下标取值**（`ldr x0,[x8, w1, uxtw #3]`，不看条目任何字段）⇒ **条目 `+0x04` ≡ 它在 null
//     向量里的下标**（`LoadCostumes` 拿"当前元素个数"当 id 存）。
//   ★ 与 `+0x38 GfxFileName` 的区别：那个由 `items.xml` 的 `gfx` 属性写，是**道具**的图集；
//     null 服装条目**不写**它（也不写 `+0x08 Name`）⇒ 真机上读到空串与"路径在 +0x88"并不矛盾。
inline constexpr uintptr_t kItemConfigItemNullCostumePathOffset = 0x88;
// 注：同一条路径上引擎还把 id 又写了一遍到 `+0x80`（`0x3BA06C str w8,[x19,#0x80]`），与 `+0x04` **恒等**
// ⇒ 实现里直接用既有的 `kItemConfigItemIdOffset`（`+0x04`，PC 的 `ItemConfig_Item.ID` 就是它），
// 不为 `+0x80` 再造一个常量（没有消费者，多一个常量就多一处要与镜像对账的东西）。
// `Quality`（PC 文档 `ItemConfig_Item.Quality`，LuaDocs 里是 `int` 字段）在 `+0xC8`；
// `CraftingQuality`（同族，`ItemConfig_Item.CraftingQuality`）在 `+0xCC`。
//
// 问什么要这两个：EID 拿 `EID.itemConfig:GetCollectible(id).Quality` 算道具品质
// （`features/eid_api.lua:2702`），`main.lua:663` 用它拼 `{{QualityN}}` 图标；读不到 nil 时
// 被 `and desc.Quality` 短路 ⇒ **品质图标静默不显示**（不报错、无日志）。这正是
// "缺口只统计过方法、字段从没被枚举过"的典型案例，见 `docs/错误复盘.md` 2026-09-16。
//
// 偏移来源与 `gfx` 同一条链 —— `items.xml` 解析器 `ItemConfig::Load`（`0x3B50E0`）的属性分派：
//   * `0x3B5A64` `adrp x1, 0x891000` + `0x3B5A68` `add x1, x1, #0x642`（=> `0x891642` = `"quality"`）
//     `strcmp` 命中后 `0x3B5A70` 的 `cbz w0` 跳到 `0x3B623C`；该分支 `bl atoi`（`0x3B6248`）之后
//     就是 **`str w0, [x27, #0xc8]`（`0x3B624C`）** ⇒ `Quality` = 32 位整数，落在 `+0xC8`；
//   * `0x3B5A78` `adrp x1, 0x8AA000` + `0x3B5A7C` `add x1, x1, #0x1a9`（=> `0x8AA1A9` = `"craftquality"`）
//     命中后跳到 `0x3B62A0`，同样是 `atoi` 之后 **`str w0, [x27, #0xcc]`（`0x3B62B0`）**
//     ⇒ `CraftingQuality` = `+0xCC`。
//   * **互证**：同一函数的收尾段 `0x3B6308..0x3B631C` 先 `ldr w8,[x27,#0xcc]` 与哨兵
//     `0x8FFFFFFF`（`mov w9, #-0x70000001`）比较，相等就把 `ldr w8,[x27,#0xc8]` 写回 `+0xcc`
//     ⇒ **`items.xml` 没写 `craftquality` 时默认等于 `quality`**，与 PC 文档语义一致，
//     两个偏移互相印证（这一条也说明实现里不该自己编"缺省值"）。
//   * 与既有常量同源：同一分派链里 `id → +0x04`（`0x3B5AE8` 的 `str w0, [x27, #0x4]`），
//     布尔类属性走 `string2bool` 后写**单字节**（`0x3B6234` 的 `strb w8, [x27, #0xb7]`）
//     —— 两个 32 位整数落在 `+0xC8`/`+0xCC` 这一段，与它们都不冲突。
inline constexpr uintptr_t kItemConfigItemQualityOffset = 0xC8;
inline constexpr uintptr_t kItemConfigItemCraftingQualityOffset = 0xCC;
// `CraftingQuality` 在 `items.xml` 未指定时的哨兵值（见上面 `0x3B630C` 的 `mov w9, #-0x70000001`）。
inline constexpr std::uint32_t kItemConfigItemCraftingQualityUnset = 0x8FFFFFFFu;

// 同一张 `items.xml` 属性分派表里的另外四个字段（2026-09-16 批次：字段缺口台账的 planned 项）。
//
// 取证方法与 `quality` 完全一样 —— 从 `ItemConfig::Load`（`0x3B50E0`）的 `strcmp` 链往下看
// 每个属性分支落点的那条 `str`：
//   * `achievement`：`0x3B58C4` 的 `strcmp` 命中 → `0x3B5B78`；`bl atoi`（`0x3B5B84`）之后
//     **`str w0, [x27, #0x50]`（`0x3B5B88`）** ⇒ `AchievementID` = `+0x50`；
//   * `tags`：`0x3B5A90` 的 `strcmp` 命中 → `0x3B5D48`；`bl atoi`（`0x3B5D54`）之后
//     **`str w0, [x27, #0x58]`（`0x3B5D58`）** ⇒ `Tags` = `+0x58`；
//   * `maxcharges`：`0x3B5978` 的 `strcmp` 命中 → `0x3B5E50`；`bl atoi`（`0x3B5E5C`）之后
//     **`str w0, [x27, #0x74]`（`0x3B5E60`）** ⇒ `MaxCharges` = `+0x74`；
//   * `chargetype`：`0x3B59F0` 的 `strcmp` 命中 → `0x3B5F60`，该分支**先按字符串取枚举**：
//     `"normal"` → `0x3B6038` 的 **`str wzr, [x27, #0xb0]`**（=0）、`"timed"` → `0x3B60C8`
//     （=1）、`"special"` → `0x3B615C` 的 `mov w8,#2; str w8,[x27, #0xb0]`（=2）
//     ⇒ `ChargeType` = `+0xB0`，且三个取值**正好等于** PC 的
//     `ItemConfig.CHARGE_NORMAL(0) / CHARGE_TIMED(1) / CHARGE_SPECIAL(2)`
//     （`analysis/isaacdocs-snapshot/docs/enums/ItemConfig.md:22-24`）—— 三值互证，不是按顺序猜的。
//
// 类型按 PC 文档定（`analysis/isaacdocs-snapshot/docs/ItemConfig_Item.md`）：
//   * `AchievementID` 是 **int** 且"默认可解锁时返回 -1" ⇒ 必须**有符号**读，否则 -1 会变成 4294967295，
//     EID 的 `item.AchievementID == -1`（`features/eid_api.lua:2003`）就永远不成立；
//   * `MaxCharges` / `ChargeType` 也是 int ⇒ 有符号读；
//   * `Tags` 文档写 int，但语义是**位掩码**（EID 用 `item.Tags & ItemConfig.TAG_QUEST`）⇒ 按
//     **无符号 64 位**读（零扩展），这样第 31 位不会被符号扩展污染、**第 32 位（TAG_NO_EDEN）也不会被截掉**。
//     ★★ 2026-09-29（批次 195）**更正偏移**：原来的 `0x58` 是**错的** ——
//     `ItemConfig::Item` 的 tags 位掩码在 **`+0xC0`**、宽 **8 字节**（有效 bit0..bit32 共 33 位）。
//     证据（`analysis/api-restore-itemconfig/spec.json` 的 `item_config_item_tags_field`）：
//       * 写点唯一：`ItemConfig::LoadMetadata @ 0x3BA2F4` 在 `0x3BA88C` `str x21,[x8,#0xc0]`
//         （x21 = `0x3BA638 bl 0x3B7650` 的返回值，而那个函数就是"空格切词 → 逐词查位表 → OR 累积"），
//         紧随其后 `0x3BA890 stp w27,w9,[x8,#0xc8]` 写已确证的 Quality(+0xC8)/CraftingQuality(+0xCC)；
//       * 三个**读者**同口径：`ItemConfig::IsTaggedCollectible @ 0x3C0E58`（`ldr x8,[x0,#0xc0]` +
//         `tst x8,x19` + `cset w0,ne`）、`IsTaggedTrinket @ 0x3C0EF0`、`GetTaggedItems @ 0x3C1F2C/0x3C2014`
//         （`tst x9,x23` + `b.eq <跳过>`）；
//       * 清零形态：`ItemConfig::Load` 用 `str xzr,[x20,#0xc0]!` —— **8 字节**整体清零。
//     ⚠️ 而 `0x58` 是 items.xml 的 `maxhearts=`（PC 的 `AddMaxHearts`）：
//     `0x3B58EC` 比较串 `maxhearts`（@0x8AB355）→ `0x3B5D54 bl atoi` → `0x3B5D58 str w0,[x27,#0x58]`
//     （**4 字节**存）。⇒ 旧实现在读 `item.Tags` 时读到的其实是"加多少心"。
//
// 宽度：TAG_NO_EDEN = `1<<32` 需要第 33 位 ⇒ 必须 u64（引擎注册它时用的就是 `mov x8,#0x100000000`）。
inline constexpr uintptr_t kItemConfigItemAchievementIdOffset = 0x50;
inline constexpr uintptr_t kItemConfigItemTagsOffset = 0xC0;   // u64，bit0..bit32
//: `+0x54` 的 `CacheFlags`（u32；`cache=` 属性 OR 累积，`<familiar>` 自动 `|= 0x200`）。
//: 我们**没有**实现它，这里只登记（证据见规格的 `offset_0x54_is_cacheflags`），供后续判断优先级。
inline constexpr uintptr_t kItemConfigItemCacheFlagsOffset = 0x54;
//: `+0x58` 的 items.xml `maxhearts=`（4 字节）。登记它是为了**防止再有人把它当成 tags**：
//: 这条注释的由来就是旧实现把 `Tags` 接到了这一格上（见上）。
inline constexpr uintptr_t kItemConfigItemMaxHeartsOffset = 0x58;
inline constexpr uintptr_t kItemConfigItemMaxChargesOffset = 0x74;
inline constexpr uintptr_t kItemConfigItemChargeTypeOffset = 0xB0;
// `Hidden`（2026-09-16，字段缺口台账 planned 里证据最足的一条）：
//   * `bool`，**1 字节**（`ldrb`，不是 4 字节整数）；
//   * 证据：`ItemConfig::Item::IsAvailable`（`0x3C101C`，见下面那组常量）的**第一条指令**就是
//     `ldrb w8, [x0, #0xb7]`，随后非零直接返回 false —— 与 PC 文档
//     （`ItemConfig_Item.md`：`boolean Hidden`；"HIDDEN 的道具不会出现在死亡证明房间"）吻合；
//   * EID 用法：`features/eid_api.lua:2008` 的 `if item.Hidden then`（隐藏道具不出描述）与
//     `eid_api.lua:1927` Spindown Dice 预测里的 `not item.Hidden`（缺它这一半恒真）。
inline constexpr uintptr_t kItemConfigItemHiddenOffset = 0xB7;
// `MimicCharge`（卡牌 / 胶囊各一个，2026-09-16 取证）。EID 用它给"模仿胶囊/卡牌"补一句说明
// （`features/eid_modifiers.lua:731`）。两个结构都由 `ItemConfig::LoadPocketItems @ 0x3BE42C`
// 从 cards.xml / pills.xml 建出来，"XML 属性名 → 结构体偏移"在指令层面直接可读：
//   * `"mimiccharge"` 这一支在 `0x3BE96C-0x3BE978`（`add x1,x1,#0xf16` + `strcmp` + `cbz`），
//     处理体 `0x3BED08 bl atoi` → `0x3BED0C str w0,[sp,#0x68]`（该栈槽整函数只有这一处属性写入）；
//   * 卡：`0x3BEE88 str w8,[x23,#0x64]`（x23 = `operator new(0x78)` 出来的 Card）；
//   * 胶囊：`0x3BEF5C stp w9,w8,[x23,#0x44]`（x23 = `operator new(0x58)`；STP 先写低地址 ⇒
//     w9→+0x44 announcerdelay、**w8→+0x48 mimiccharge**）。
// 消费侧（第二处独立证据）：`Entity_Player::UseActiveItem @ 0x30653C` 在
//   * `0x3106E8 ldr w9,[x0,#0x64]` → `0x3106EC str w9,[x8,#0x197C]`（卡；前置 `cmp #0x107` = CLEAR_RUNE、
//     且卡类型 `[card+0x58]==2` = rune）；
//   * `0x312A4C ldr w9,[x0,#0x48]` → `0x312A50 str w9,[x8,#0x197C]`（胶囊；前置 `cmp #0x15c` = PLACEBO）。
// 类型：写入来自 `atoi`、读出用 `ldr w` ⇒ 4 字节 int。
inline constexpr uintptr_t kItemConfigCardMimicChargeOffset = 0x64;        // ItemConfig::Card
//: ★ 批次 242（2026-09-30）：`ItemConfig::Card` 的**卡类型**（`+0x58`，4 字节 int）——
//: 实现 `ItemConfig_Item:IsRune()` 用的就是它（PC 的类名是 `ItemConfig_Card`，见下）。
//: 为什么现在补：EID 在 `eid_bagofcrafting.lua:102` / `eid_itemprediction.lua:327` /
//: `eid_modifiers.lua:1277` **三处无保护地调 `GetCard(id):IsRune()`** ⇒ 我们缺它时**每帧一个 Lua 错误**
//: （真机读数：EID 的 `MC_POST_RENDER` 占全部托管回调时间的 90%、Lua 分配 1.59 亿次）。
//: 证据 = **引擎自己的判据**：上面 `MimicCharge` 那一段记录过 —— `Entity_Player::UseActiveItem`
//: 处理 `CLEAR_RUNE(0x107)` 时读 `[card+0x58]` 并与 `2` 比较（"卡类型 == 2 ⇒ rune"）。
//: PC 契约：IsaacDocs `ItemConfig_Card.md:29` `#### boolean IsRune ( )`（带 `.reporplus` 徽章
//: = REPENTOGON 一侧）；语义就是"这张卡是不是符文"。
inline constexpr uintptr_t kItemConfigCardTypeOffset = 0x58;               // ItemConfig::Card
inline constexpr std::int32_t kItemConfigCardTypeRune = 2;                 // CardType == 2 ⇒ rune
inline constexpr uintptr_t kItemConfigPillEffectMimicChargeOffset = 0x48;  // ItemConfig::PillEffect
// `eChargeType`（同一份 enums 文档）：`0x3B6038`/`0x3B60C8`/`0x3B615C` 三个落点分别写 0/1/2。
inline constexpr std::int32_t kItemChargeTypeNormal = 0;
inline constexpr std::int32_t kItemChargeTypeTimed = 1;
inline constexpr std::int32_t kItemChargeTypeSpecial = 2;

// --- `IsAvailable` 一族（2026-09-16，取证见 `docs/问题与解决记录.md` 续十二）------------------
//
// **地址以动态符号表为准**：交接文档早先记的 `0x3C0F9C` / `0x3C1B5C` / `0x3C1C48` 是错的
// （各偏低 0x80 / 0x140 / 0x100），实测如下三条：
//   * `ItemConfig::Item::IsAvailable(long, uint)` const  @ `0x3C101C`
//   * `ItemConfig::Card::IsAvailable()` const            @ `0x3C1C9C`
//   * `ItemConfig::PillEffect::IsAvailable()` const      @ `0x3C1D48`
inline constexpr uintptr_t kItemConfigItemIsAvailableOffset = 0x3C101C;
inline constexpr uintptr_t kItemConfigCardIsAvailableOffset = 0x3C1C9C;
inline constexpr uintptr_t kItemConfigPillEffectIsAvailableOffset = 0x3C1D48;
// 入口 4 字节按小端整字存（与 `kEntityPlayerAddCollectibleEntryWord` 同口径），调用前核对一次。
// ⚠️ Card 与 PillEffect 两条**序言同构**（都是 `stp x29,x30,[sp,#-0x20]!`）⇒ 指纹只能证明
// "这里是一条符合预期的序言"；**区分谁是谁靠句柄里的 `beginOffset`**，不靠指纹。
inline constexpr std::uint32_t kItemConfigItemIsAvailableEntryWord = 0xD10143FFU;
inline constexpr std::uint32_t kItemConfigCardIsAvailableEntryWord = 0xA9BE7BFDU;
inline constexpr std::uint32_t kItemConfigPillEffectIsAvailableEntryWord = 0xA9BE7BFDU;
// `Item::IsAvailable` 的 flags 取值 —— **这是我们的兼容层定义**（三个函数在镜像里没有任何调用点，
// 参数无法从游戏自己的用法学到）。依据两条：
//   ① PC 文档 `analysis/isaacdocs-snapshot/docs/ItemConfig_Item.md:35-38`：
//      "true = 已解锁；false = 没解锁 **或被 tags 挡掉**"；
//   ② `0x3C101C` 反汇编读出的位语义：bit1 = 成就解锁（读 `+0x50` 的 `AchievementID`，-1 直接 true）、
//      bit2 = tags/当前局阻挡、bit3 = 模组提供的物品、bit0 = 按 `Type` 分流。
// 已按此在 `api_deviation.cpp` 登记偏离（含未覆盖的 PC 语义）。
inline constexpr std::int64_t kItemIsAvailableFlags = 0x2 | 0x4 | 0x8;

// `eItemType`（冻结文档 `analysis/isaacdocs-snapshot/docs/enums/ItemType.md`）。
inline constexpr std::uint32_t kItemTypeNull = 0;
inline constexpr std::uint32_t kItemTypePassive = 1;
inline constexpr std::uint32_t kItemTypeTrinket = 2;
inline constexpr std::uint32_t kItemTypeActive = 3;
inline constexpr std::uint32_t kItemTypeFamiliar = 4;
inline constexpr uintptr_t kGameIsPausedThunkOffset = 0x671100;
inline constexpr std::array<u8, 16> kGameIsPausedThunkExpectedBytes = {
    0x70, 0x21, 0x00, 0xB0, 0x11, 0xF6, 0x43, 0xF9,
    0x10, 0xA2, 0x1F, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
// Manager input-action trampolines. Each loads the Manager singleton itself and zeroes the
// trailing `Entity*` argument, so the Runtime can call them with the two arguments the PC
// Lua API takes. Offsets and guards come from the game's own dynamic symbol table (the NRO
// offset equals the loaded module offset, verified against previously recorded guards), and
// the guard bytes are what the Hook installation checks before publishing the binding.
inline constexpr uintptr_t kManagerIsActionPressedOffset = 0x3F9B6C;
inline constexpr std::array<u8, 16> kManagerIsActionPressedExpectedBytes = {
    0x80, 0x35, 0x00, 0xF0, 0x00, 0xB4, 0x43, 0xF9,
    0xE3, 0x03, 0x1F, 0xAA, 0x86, 0xFB, 0x09, 0x14,
};
inline constexpr uintptr_t kManagerIsActionTriggeredOffset = 0x3F9B7C;
inline constexpr std::array<u8, 16> kManagerIsActionTriggeredExpectedBytes = {
    0x80, 0x35, 0x00, 0xF0, 0x00, 0xB4, 0x43, 0xF9,
    0xE3, 0x03, 0x1F, 0xAA, 0x62, 0xDE, 0x09, 0x14,
};
inline constexpr uintptr_t kManagerGetActionValueOffset = 0x3F9B8C;
inline constexpr std::array<u8, 16> kManagerGetActionValueExpectedBytes = {
    0x80, 0x35, 0x00, 0xF0, 0x00, 0xB4, 0x43, 0xF9,
    0xE3, 0x03, 0x1F, 0xAA, 0xFA, 0x0B, 0x0A, 0x14,
};

// --- ★★★ 批次 390（2026-10-07）：`KAGE::Input::ManagerBase` 那三处查询入口 --------------------
//
// ★★ 上面那三条与下面这三条的关系（**批次 392 更正**，真机回归 + 反汇编定案 —— 别再按旧说法理解）：
//   * 上面 `kManager*Offset = 0x3F9B**` = `IsaacRepentance::Manager::IsAction*`：自己装 Manager 单例、
//     把末尾 `Entity*` 清 0，然后**尾跳**进下面这三条（`nro_disasm 0x3F9B6C` 能看见 `b 0x678990`，
//     那个桩指向符号 `_ZN4KAGE5Input11ManagerBase15IsActionPressedEjjPj`）；
//   * **它不是"只有 Lua 才走"的胶水**：`tools/nro_callers.py 0x3F9B6C` 给出 **35 个**调用点，含
//     `Entity_Player::get_movement_input` / `control_shooting` / 各 `Menu_*::ProcessInput`
//     ⇒ Lua与引擎都会经过此入口；部分检查传nil，移动/射击等传真实Entity*。
//   * ⇒ 只挂下面这三条**并不能**自动满足"覆盖不影响 Lua 读取"：它会把 Lua 的读取一起覆盖
//     （MCM 菜单可见时 `return false` 冻住自己光标，就是这么来的）。批次 392 的处置 =
//     我们这侧读输入时套 `LuaRuntime::RawEngineInputQueryScope`，中继见标记就跳过派发
//     （见 `hook_manager.cpp` 的输入中继及 `lua_runtime.cpp` 的直读壳）。
//   * 2026-10-25：钩子已移到高层，精确重定位这16字节，先取得Entity*再原样执行清x3/尾跳；
//     下面底层常量保留作ABI/绑定依据，不再作为MC_INPUT_ACTION入口。
//
// 取证（**全部来自 `Repentance.nro` 的动态符号表**，可重跑；build `91C73FDD575061318D68886316AFEAC72388B2AB`）：
//   `KAGE::Input::ManagerBase::IsActionPressed / IsActionTriggered / GetActionValue`
//   形参 `(动作号, controllerIndex, 出参指针)`；`GetActionValue` 返回 float。
// ⚠️ `IsActionPressed` 与 `IsActionTriggered` 的 16 字节守卫**逐字节相同**（序言一模一样）
//   ⇒ 守卫挡得住"偏移写错"，**挡不住"这两条互换了"**（要靠行为读数发现）。
inline constexpr uintptr_t kKageManagerIsActionPressedOffset = 0x4F9920;
inline constexpr std::array<u8, 16> kKageManagerIsActionPressedExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9, 0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
inline constexpr uintptr_t kKageManagerIsActionTriggeredOffset = 0x4F9A64;
inline constexpr std::array<u8, 16> kKageManagerIsActionTriggeredExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9, 0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
inline constexpr uintptr_t kKageManagerGetActionValueOffset = 0x4F9BCC;
inline constexpr std::array<u8, 16> kKageManagerGetActionValueExpectedBytes = {
    0xE8, 0x0F, 0x1B, 0xFC, 0xFD, 0x7B, 0x01, 0xA9, 0xFD, 0x43, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9,
};
//: `InputHook` 的三个取值（`enums/InputHook.md`：`IS_ACTION_PRESSED=0` / `IS_ACTION_TRIGGERED=1` /
//: `GET_ACTION_VALUE=2`）—— 与 `lua_runtime.cpp` 暴露给 Lua 的 `InputHook` 常量表同一份口径。
inline constexpr std::int32_t kInputHookIsActionPressed = 0;
inline constexpr std::int32_t kInputHookIsActionTriggered = 1;
inline constexpr std::int32_t kInputHookGetActionValue = 2;


// --- `Input.IsButtonPressed/IsButtonTriggered/GetButtonValue`（批次 195，2026-09-29）---------
//
// ★ 与上面三条**动作**查询不是同一个东西：这三条按**按键号**问，入口在
// `KAGE::Input::ManagerBase`（不是 `IsaacRepentance::Manager` 的跳板）⇒ 必须自己取
// `KAGE::Input::g_Manager`。证据规格 `analysis/api-restore-input-keys/spec.json`
// （`engine_facts.manager_entry_points` / `device_button_state` / `plt_stub_only_two`）。
//
// `kKageInputManagerSlotOffset`：`KAGE::Input::g_Manager` 的 **GOT 槽**（槽里是那个指针）。
// 出处：三条入口的序言自己就是 `adrp/ldr` 取它，且游戏自己的调用点（`Game::ProcessInput` 的
// L+R+StickL+StickR 组合键、`Menu_Title::Update`、`Console::check_key_autorepeat`）全走这条链。
inline constexpr uintptr_t kKageInputManagerSlotOffset = 0xAAC768;

// `KAGE::Input::ManagerBase::IsButtonPressed(unsigned button, unsigned deviceId, unsigned* out)`
// （mangled `_ZN4KAGE5Input11ManagerBase15IsButtonPressedEjjPj`）：`x0` = ManagerBase*、
// w1 = button、w2 = deviceId（`0xFFFFFFFF` = 任意设备）、x3 = 可空的 out 指针。
// 真机意义：**游戏自己在用**（`Game::ProcessInput+0x88/0xa4/0xc0/0xdc` 问按键 8/11/10/13 的
// L+R+StickL+StickR 组合键）⇒ 它不是死代码。
inline constexpr uintptr_t kKageIsButtonPressedOffset = 0x4F9504;
inline constexpr std::array<u8, 16> kKageIsButtonPressedExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
//: ★★ 序言**区分不了**这三条，也区分不了同族的动作查询 —— 四条入口的**头 32 字节完全相同**
//:（`FD7BBCA9F85F01A9FD030091F65702A9F44F03A914800191F503012AF60300AA`）⇒ 16 字节（甚至
//: 32 字节）指纹**认不出谁是谁**，偏移写串了会被静默放过（换成另一条按钮查询 = 给出错语义）。
//: 区分点在**各自动用的虚表槽**那条指令上（偏移 `entry+0xE0`）：
//: `IsButtonPressed` 是 `ldr x8,[x8,#0x30]`（**指令字 `0xF9401908`，内存里是 `08 19 40 F9`**）、
//: `IsButtonTriggered` 是 `ldr x8,[x8,#0x38]`（字 `0xF9401D08`，内存 `08 1D 40 F9`）、
//: `IsActionPressed` 是 `+0x48`、`IsActionTriggered` 是 `+0x50`。
//: ⇒ 本批新加的两条入口**除序言外再比这 4 字节**（见 `hook_manager.cpp` 的
//: `VerifyInputButtonEntry`）。这与「Card/PillEffect 序言同构、靠句柄 beginOffset 区分」是同一类坑。
//:
//: ★★★ 2026-09-29（批次 210）**这里曾经写错、真机哑了一整轮**：上面这 4 字节原本写成
//: `{0xF9, 0x40, 0x19, 0x08}` —— 那是**反汇编里指令字的十六进制字面顺序**，不是**内存字节序**。
//: AArch64 是小端：`ldr x8,[x8,#0x30]` 的字节在内存里是 `08 19 40 F9`。守卫是拿
//: `memcmp` 逐字节比的（`engine_call_access.hpp` 的 `VerifyEntryBytes`）⇒ 写反了**永远不比中**，
//: 而代价是**静默的**：`VerifyInputButtonBindings` 留下 0 ⇒ 发布槽是 0 ⇒
//: `Input.IsButtonPressed` / `IsButtonTriggered` 在真机上**恒答 false**（不报错、不崩、也不置探针位），
//: MCM 的"按右摇杆开菜单"于是永远没反应（详见 `dist/change-archive-20260929/210-…`）。
//: ⇒ 写这类常量一律按**内存字节序**（与 `kKageIsButtonPressedExpectedBytes` 同一种写法），
//:   别照抄反汇编里的 `F9 40 19 08`。现在有门禁钉住：
//:   `runtime/tests/test_engine_offset_signatures.py` 的
//:   `test_guard_bytes_match_the_game_image_when_available` 会拿本地镜像逐字节比一遍。
inline constexpr uintptr_t kKageInputButtonDiscriminatorOffset = 0xE0;
inline constexpr std::array<u8, 4> kKageIsButtonPressedDiscriminator = {0x08, 0x19, 0x40, 0xF9};

// ⚠️ **引擎的 `ManagerBase::IsButtonTriggered @ 0x4F9648` 刻意不登记、不绑定**：
//   与 `IsButtonPressed` 逐条同构（唯一区别是设备虚表槽 `+0x38`，`0x4F9728 ldr x8,[x8,#0x38]`），
//   但它的语义**不是** PC 文档的上升沿，而是「上一帧也按着」
//   （`InputDeviceBase::Poll @ 0x4F70B0` 把 `+0x30` 复制进 `+0x38`）⇒ 我们**不用它**：
//   `Input.IsButtonTriggered` 的边沿由 `LuaRuntime::InputFrameEdges` 自己算
//   （与 `IsActionTriggered` 同一处口径，见 `input_api.cpp`）。
//   ★ 更正（批次 381，2026-10-06）：类型由 `ActionEdgeTracker` 改名为 `InputFrameEdges`，
//     且改成"每帧在引擎帧边界采一次、判定纯读"（口径见 `runtime/source/input_edge.hpp` 第五节）。
//   ★ 为什么不"登记但不调用"：门禁 `test_engine_offset_signatures` 要求**每个绑定入口都有一个
//     带声明类型的调用点**（"单方法绑定链"），没有消费者的入口会被判成"从没被比过"、
//     需要进分诊台账 —— 那样登记它就只剩噪音。偏移写串的后果在这里不会静默：
//     `IsButtonPressed` 那条的 4 字节判别式（`entry+0xE0`，内存字节 `08 19 40 F9`
//     = 指令字 `0xF9401908`）就是专门防这个的。

// `KAGE::Input::ManagerBase::GetButtonValue(unsigned button, unsigned deviceId, unsigned* out)`
// —— 返回值走 **s0**（浮点）。这条**没有 PLT 桩**（全模块没有外部调用点）⇒ 只能直接调真入口。
// ⚠️ 它在 Switch 上只可能给 0.0/1.0：有名字的按键号（0..17）全落在"走 IsButtonPressed 给 0/1"
//   那一档；模拟量那一档的按键号在引擎里对不上任何名字（见规格的 `reachability_problem`）。
//   轴强度请用 `Input.GetActionValue`。
inline constexpr uintptr_t kKageGetButtonValueOffset = 0x4F97B0;
inline constexpr std::array<u8, 16> kKageGetButtonValueExpectedBytes = {
    0xE8, 0x0F, 0x1B, 0xFC, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9,
};

//: 手柄按键号的上界（含）：`DeviceNX::GetButtonName` 的名字表给出 0..17
//: （0..3 方向 / 4..7 A/B/X/Y / 8..9 L/ZL / 10 摇杆按 / 11..12 R/ZR / 13 摇杆按 /
//:  14..15 +/- / 16..17 SL/SR），且**与 PC 的 `Controller` 枚举 0..15 逐项相同**
//: （`analysis/mod-corpus/isaac-mod-config-menu/scripts/inputhelper.lua:40-55`）。
//: ★ 16/17（SL/SR）引擎里没有任何写点位图的路径 ⇒ 恒 false（登记在偏离台账里）。
inline constexpr std::uint32_t kKageControllerButtonMaximum = 17;

// --- 引擎的**输入设备表**（批次 211，2026-09-30）---------------------------------------------
//
// 为什么要读它：PC 模组里的"第几个手柄"用的是 PC 的编号（`0` = 键盘、`1..4` = 第 1..4 台手柄），
// 而 Switch 引擎的设备号是**另一张表**（`0` = 触摸屏、`1..8`/`33` = 手柄）。
// 模组传 `1` ⇒ 引擎按 `GetId()` 找不到那台手柄 ⇒ **恒答 false**（同一个坑踩了三次：
// 嵌入式模组菜单、主菜单自绘入口、MCM 的"按右摇杆开菜单"）。
// 映射口径在 `runtime/source/pc_ns_input_device_map.hpp`；这三个偏移只负责把设备表读出来。
//
// 出处是 `KAGE::Input::ManagerBase::IsButtonPressed @ 0x4F9504` 自己的指令：
//   004f9540  ldp x24,x8,[x22,#0x8]        ; x22 = this ⇒ `[this+0x8]` = 设备向量 begin
//   004f9560  ldr x8,[x22,#0x10]           ; `[this+0x10]` = 设备向量 end（遍历到它为止）
//   004f954c  ldr x0,[x24] ; bl 0x681b90   ; 每个条目 = 设备指针；`GetId()` 拿设备号
//   004f9554  cmp w0,w23 ; b.eq …           ; ★ 与调用方给的 deviceId **精确**比较
//   （`0xFFFFFFFF` 那条路走 0x4F957C，另外遍历所有设备——游戏本体自己的调用点都用它）
// 条目步长 8 字节（`f8777900 ldr x0,[x8,x23,lsl #3]`）；真机实测表里是 `[0, 33]`
// （`dist/gdb-read-20260930-0030-device-table.txt`）。
inline constexpr uintptr_t kKageInputDeviceVectorBeginOffset = 0x8;
inline constexpr uintptr_t kKageInputDeviceVectorEndOffset = 0x10;
//: 设备对象里的设备号（`InputDeviceBase::GetId()` 读的就是它；
//: `DeviceNX::Initialize @ 0x4FC5AC` 是 `ldr w8,[x1]; str w8,[x0,#0x8]`）。
inline constexpr uintptr_t kKageInputDeviceIdOffset = 0x8;
//: 设备对象里的"**动作数**"。出处 = `InputDeviceBase::IsActionPressed @ 0x4F76A8` 的序言：
//: `ldr w8,[x0,#0x1c] ; cmp w8,w1 ; b.ls ⇒ 直接答 false`（越界的动作号不问设备）。
inline constexpr uintptr_t kKageInputDeviceActionCountOffset = 0x1c;
//: 设备对象里的"**每动作绑定的按钮码数组**"指针表。出处 = 同一条函数的循环体：
//: `ldr x8,[x19,#0x20]`（表基址）→ `ldr x8,[x8,x20,lsl #3]`（第 action 个数组的指针）
//: → `ldr w1,[x8,x22,lsl #2]`（该数组里第 i 个按钮码）→ 再拿按钮码调虚槽 `+0x30`。
//:
//: ★ 批次 223：这张表就是"+17 错位"的嫌疑对象 —— 真机上"推左/右/下"时引擎**同时**答
//: `action` 与 `action+17` 为真（左⇒0&17、右⇒1&18、下⇒3&20，四个数据点全对上）
//: ⇒ 若"第 i 项与第 i+17 项绑的是同一个输入"，那答案就在这里。dump 探针见 `input_api.cpp`。
inline constexpr uintptr_t kKageInputDeviceActionTableOffset = 0x20;

// --- 设备对象的**内部输入状态**（批次 224；全部来自 `InputDeviceBase::Poll @0x4F70B0`
//     与 `InputDeviceBase::IsActionPressed @0x4F76A8` 的反汇编）--------------------------------
//
// 为什么要 dump 这些"原始格子"：真机上"推摇杆下"时引擎**同时**答 `ACTION_DOWN(3)` 与
// `ACTION_MENULEFT(20)` 为真（推左 ⇒ 0 与 17、推右 ⇒ 1 与 18，四个点全对上），
// 而批次 223 的表 dump 已经证明"**动作 12..23 没有任何按钮绑定**"（指针全 0）
// ⇒ 多报只能来自 `IsActionPressed` 的第二条判定「`analog[action] > 死区`」
// ⇒ 必须直接看 `+0xd0` 那 24 格的原始值，**不能再经过任何 API 转述**
//   （批次 222/223 已经踩过一次：`GetActionValue` 给的数与 `IsActionPressed` 内部读的对不上）。
//: 设备启用字节（`Poll` 序言 `ldrb w8,[x0,#0xd]`；0 ⇒ 整个设备答 false）。
inline constexpr uintptr_t kKageInputDeviceEnabledOffset = 0xD;
//: 本帧 / 上一帧的**按键位图**（`Poll` 开头 `ldr x8,[x0,#0x30] ; str x8,[x0,#0x38]`）。
inline constexpr uintptr_t kKageInputDeviceKeysCurrentOffset = 0x30;
inline constexpr uintptr_t kKageInputDeviceKeysPreviousOffset = 0x38;
//: ★★ 批次 403（2026-10-07）：**`+0x30` 这一格不是引擎用的按键位图，别拿它算边沿。**
//:   真机读数（`dist/gdb-read-20261007-1732-after-fire-stick.txt`，8523 帧、用户正在玩）：
//:   按键 0/1/2/3（十字）与 4（A）、14（减号）的 `lastEdgeFrame` 是活的
//:   （5711/5687/5735/5758、1239、117），而 **5..13 与 15..17**（B/X/Y/L/ZL/两摇杆按下/R/ZR/+）
//:   **从未答过按住**、按键侧的"刚按下"累计（`g_InputButtonEdgeCounts`）**一次都没报过**。
//:   ★ 这是**按位位置的规律**（0..4 与 14 活、5..13 与 15+ 死），**不是"用户按过哪些键"的规律**
//:   —— 一个 8523 帧、用户全程在玩的会话里，B/X/Y/L/R/ZL/ZR/摇杆按下必然被按过。
//:   ⇒ 采样器（`input_api.cpp` 的 `SampleInputFrame`）按键侧**改用"对 0..17 逐个问引擎"**
//:   （`ManagerBase::IsButtonPressed`，批次 403）。本格只保留给别处（动作侧 / 批次 224 的设备状态 dump）。
//: 本帧 / 上一帧的**摇杆方向位图**（`Poll` 里用 `orr` 往 `+0x40` 置位，随后 `str` 到 `+0x48`）。
inline constexpr uintptr_t kKageInputDeviceStickCurrentOffset = 0x40;
inline constexpr uintptr_t kKageInputDeviceStickPreviousOffset = 0x48;
//: 8 个轴幅值（`+0x50 + 4*i`；`Poll` 里把两根摇杆各拆成 x-/x+/y-/y+ 四个非负幅值）。
inline constexpr uintptr_t kKageInputDeviceAxesOffset = 0x50;
//: **每动作的模拟量数组**（`IsActionPressed`：`ldr x8,[x19,#0xd0] ; ldr s0,[x8,x20,lsl #2]`）。
inline constexpr uintptr_t kKageInputDeviceActionValueOffset = 0xD0;
//: 动作判定用的**死区**（`IsActionPressed`：`ldr s1,[x19,#0xe4] ; fcmp s0,s1 ; b.le ⇒ false`）。
inline constexpr uintptr_t kKageInputDeviceDeadzoneOffset = 0xE4;
//: 摇杆长度重映射那一处用的另一个死区（`Poll` 里 `ldr s1,[x19,#0xe0]`）。
inline constexpr uintptr_t kKageInputDeviceDeadzoneAltOffset = 0xE0;

// --- Switch 引擎的**内部动作表**（批次 230，2026-09-30；"推下被答成按左"的定案证据）------------
//
// ★ 结论：**模组看到的 `ButtonAction` 与 Switch 引擎内部的动作号不是同一张表**，所以三条 Lua
//   入口（`Input.IsActionPressed` / `IsActionTriggered` / `GetActionValue`）必须翻译。
//   翻译表与逐行证据在 `runtime/src/interfaces/lua/input_action_map.hpp`（**唯一真值源**），
//   这里只留"为什么它是对的"的浓缩版：
//
//   * `InputDeviceBase::IsActionPressed @0x4F76A8`：动作号**直接当数组下标**（绑定表 `+0x20`、
//     模拟量 `+0xd0`、死区 `+0xe4`），`ManagerBase::IsActionPressed @0x4F9920` 也不翻译；
//   * 引擎自己的菜单用 **17..20** 当方向：`Menu_Game::Update @0x40D770` 里 19 ⇒ 选中行 -1（上）、
//     20 ⇒ +1（下）；`PauseScreen` / `Menu_Bestiary` / `Menu_KeyConfig` 同一组；
//   * 默认按键表 `IsaacRepentance::s_ButtonMap @0xa38300`（24 条 = 24 个内部动作；
//     `s_JoyConLeftButtonMap @0xa38420` / `s_JoyConRightButtonMap @0xa384e0` 各一份）：
//     17..20 ← 十字键四向 + 左摇杆；21 ← L、22 ← R、23 ← X、16 ← `+`；
//   * 内部 16 = `ACTION_JOINMULTIPLAYER`：`PlayerManager::ProcessInput @0x43E700` 在
//     「16 被触发 + 按住 8(炸弹) + 按住 10(药丸)」时调 `PlayerManager::SpawnCoPlayer`；
//   * 真机读数（批次 222）：推左 ⇒ 0 与 17、推右 ⇒ 1 与 18、推下 ⇒ 3 与 20。
//
//   ⇒ Switch 内部动作表（24 个，正好用满 0..23）：
//     `0..15` 与 PC 同号；`16 JOINMULTIPLAYER`；`17..20 MENU L/R/U/D`；
//     `21 MENULB`、`22 MENURB`、`23 MENUTAB`。
//     PC 才有的 `FULLSCREEN/MUTE/RESTART/MENULT/MENURT/MENUEX/EMOTES/CONSOLE` 在这里**不存在**。
//
// ★ 与下面那段的区别（批次 224 当时的推断已被本批取代）：当时以为"多报只能来自 `analog[action]`"，
//   其实两件事同时成立 —— 判定确实读 `analog[action]`（这部分对），而**号本身**在两张表里不是
//   同一个语义（这才是"多报 +17"的来历：PC 的 17..20 正好落在 Switch 的"菜单四向"上）。

// `KAGE::Graphics::Font` -- PC Lua's `Font` type (Stage148 audit:
// `analysis/stage148-font-abi/91C73FDD575061318D68886316AFEAC72388B2AB.json`). Every entry
// point below is a module-local definition resolved from the game's own dynamic symbol table,
// and the guard bytes are what the Hook installation checks before publishing the binding.
//
// Unlike Game/Level/Room, the Runtime allocates Font instances itself: `~Font()` only releases
// the Font's internal buffers (it never deletes `this` and never unregisters a global), so the
// destructor is a tail-jump to `Unload()` and the object's storage belongs to us. `Font` has no
// vptr (`+0x00` is the `IsLoaded` flag) and must never be copied by value.
inline constexpr std::size_t kFontObjectSize = 0x20050;
inline constexpr uintptr_t kFontCtorOffset = 0x4CDE20;
inline constexpr std::array<u8, 16> kFontCtorExpectedBytes = {
    0xC8, 0x09, 0x80, 0x52, 0x48, 0x00, 0xA0, 0x72,
    0x1F, 0x00, 0x00, 0x39, 0x1F, 0x40, 0x00, 0xB9,
};
// The destructor's guard window deliberately spans into `Unload()`, because `~Font()` is a
// single `b Unload` tail-jump followed by Unload's prologue.
inline constexpr uintptr_t kFontLoadOffset = 0x4CDEB8;
inline constexpr std::array<u8, 16> kFontLoadExpectedBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFC, 0x6F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};
inline constexpr uintptr_t kFontUnloadOffset = 0x4CE768;
inline constexpr std::array<u8, 16> kFontUnloadExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
inline constexpr uintptr_t kFontIsLoadedOffset = 0x4CE898;
inline constexpr std::array<u8, 16> kFontIsLoadedExpectedBytes = {
    0x00, 0x00, 0x40, 0x39, 0xC0, 0x03, 0x5F, 0xD6,
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
};
inline constexpr uintptr_t kFontGetStringWidthOffset = 0x4CE9BC;
inline constexpr std::array<u8, 16> kFontGetStringWidthExpectedBytes = {
    0x2C, 0x00, 0x40, 0x39, 0xCC, 0x08, 0x00, 0x34,
    0xC9, 0x09, 0x80, 0x52, 0x49, 0x00, 0xA0, 0x72,
};
inline constexpr uintptr_t kFontGetLineHeightOffset = 0x4CEEE0;
inline constexpr std::array<u8, 16> kFontGetLineHeightExpectedBytes = {
    0x00, 0x28, 0x40, 0x79, 0xC0, 0x03, 0x5F, 0xD6,
    0x00, 0x2C, 0x40, 0x79, 0xC0, 0x03, 0x5F, 0xD6,
};

// `Font::DrawString(text, x, y, Color const&, boxWidth, center)`: a thin wrapper that copies
// the colour and calls `DrawStringScaled(text, x, y, 1.0f, 1.0f, &copy, boxWidth, center)`.
// The `Color` argument travels as a pointer (the class has a user-defined copy constructor,
// so it is passed by invisible reference), which is what lets the Lua layer hand it a 16-byte
// RGBA block of its own. No explicit batch handling exists here: KAGE's graphics manager owns
// the batching, so the open question for hardware is whether drawing from the Runtime's render
// callback lands inside a live batch.
// 三个绘制变体（同一类，紧邻 `DrawString`）：坐标走 s0/s1，缩放的
// `ScaleX`/`ScaleY` 走 s2/s3，颜色仍走整数寄存器 x2（不可见引用），w3 = boxWidth、w4 = center。
// 已逐条反汇编核对：`DrawStringScaledUTF8` 先 `mov v8..v11` 收下 v0..v3、`mov w20/w19` 收下 w3/w4、
// `mov x21, x2` 收下颜色指针，与 `DrawString` 的形态完全一致（EID 用的就是 ScaledUTF8）。
inline constexpr uintptr_t kFontDrawStringScaledUTF8Offset = 0x4CFAB8;
inline constexpr std::array<u8, 16> kFontDrawStringScaledUTF8ExpectedBytes = {
    0xFF, 0xC3, 0x01, 0xD1, 0xEB, 0x2B, 0x01, 0x6D,
    0xE9, 0x23, 0x02, 0x6D, 0xFD, 0x7B, 0x03, 0xA9,
};

// `IsaacRepentance::ANM2` 的对象尺寸 = **0x158（344 字节）**，两种独立方法互证
// （工具 `tools/stage155_anm2_size_audit.py`，报告 `analysis/stage155-anm2-size/stride.json`）：
//   1. 游戏自己在 `AnmCache::CreateGlobalAnim()` 里就是 `mov w0,#0x158` → `bl operator new`
//      → `bl ANM2::ANM2()`（`0x1793C/0x17940/0x17948`）；
//   2. 同一父对象里连续构造的三个 ANM2 成员位移是 `0x5028`/`0x5180`/`0x52D8`，步长正好 0x158
//      （`0x1B570`–`0x1B590`）。
// 我们按 16 字节对齐自己分配这块内存（尺寸由上面的证据定案），构造用游戏的 ctor、析构用
// `kSpriteDestructorOffset`（D1 不释放内存，游戏自己在 `0xEC38 → 0xEC40` 里紧跟 `operator delete`）。
inline constexpr std::size_t kSpriteObjectSize = 0x158;
inline constexpr std::size_t kSpriteObjectAlignment = 16;
// `ANM2+0x149` 是"图形是否加载完成"的标志；为 0 时 `Render`/`Update` 是安全空操作（stage150 审计）。
inline constexpr std::size_t kSpriteLoadedFlagOffset = 0x149;

// 批次 065：`EntityRef`（`Entity::EntityRef`）的**替身缓冲区**大小。引擎按引用读它，
// 已知被读到的最大偏移是 `+0x28`（源实体指针，8 字节）⇒ 需要 ≥ `0x30`；这里给 `0x40` 留余量。
// 布局证据（哪几个格子、各自凭什么）写在 `interfaces/lua/entity_ref_api.hpp`。
inline constexpr std::size_t kEntityRefStorageSize = 0x40;

// `Entity+0x50` = 内嵌的 `ANM2`（PC Lua 的 `Entity:GetSprite()`）。两条独立指令序列互证
// （都在 `Repentance.nro` 的 `.dynsym` 里，用 `tools/nro_disasm.py` 复现）：
//   1. **构造函数** `Entity::Entity()`（`0x588ac`）：
//        `900052a8 adrp x8, 0xaac000 ; _ZTVN15IsaacRepentance6EntityE`
//        `a8857c08 stp  x8, xzr, [x0], #0x50`  ← **后索引写**：vptr → `this+0`、0 → `this+8`，
//                                                 然后把 x0 前移 0x50
//        `94185c8b bl   0x66fb00 ; import _ZN15IsaacRepentance4ANM2C1Ev`  ← 用 `this+0x50` 当 this
//      内嵌成员没有"指针字段"，构造出来的对象就在 `this+0x50` 上。
//   2. **渲染** `Entity::Render(Vector2 const&)`（`0x624fc`）：
//        `91014260 add x0, x19, #0x50` → `bl 0x6721d0 ; import ANM2::BeginBatches()`
//        `91014260 add x0, x19, #0x50` → `bl 0x66fcf0 ; import ANM2::Render(Vector2 const&, …)`
//   3. **派生类的贴图装载** `Entity_Pickup::ReloadGraphics(bool)`（`0x26a97c`）：给收藏品底座换
//      spritesheet 的那几处全是 `add x0/x20, x19, #0x50` → `ANM2::ReplaceSpritesheet(int,
//      std::string const&)`（例如 `gfx/Items/Pick Ups/...`）。也就是说 `Entity_Pickup` 的
//      **主** sprite 就是基类那个内嵌对象，而不是它自己的另一个 ANM2 成员。
// 单继承下基类子对象在偏移 0，所以**所有** `Entity_*`（含 `Entity_Player`/`Entity_Pickup`）的
// sprite 都在同一个偏移。
//
// ★ 已知偏差（必须写明）：派生类可以**额外**持有别的 ANM2 成员（`Entity_Tear::Render`
// （`0x341794`）渲染的是 `this+0x4d8`/`this+0x630`，`Entity_Pickup::Render`（`0x270c34`）还会
// `RenderLayer` 渲染 `this+0x620` 的从属 sprite）。本轮只把"基类主 sprite"接出来 ——
// 与 PC 的 `Entity:GetSprite()` 对应；对"渲染时主要画从属 sprite"的少数实体，返回值可能不是
// 屏幕上最显眼的那个对象。要么接受这条偏差，要么逐个派生化。
inline constexpr uintptr_t kEntitySpriteOffset = 0x50;

// `ANM2+0x38`：指向**当前动画名**的 libc++ `std::string`（24 字节 SSO 对象；没有动画时为 0）。
// 证据 = 引擎自己的 `ANM2::IsPlaying(char const*)`（`private:kSpriteIsPlayingOffset`）就是这么读的：
//   `f9401c08 ldr x8, [x0, #0x38]`（为 0 → 返回 false）
//   `39415009 ldrb w9, [x0, #0x54]`（在播标志，为 0 → false）
//   `39400109 ldrb w9, [x8]` → `37000129 tbnz w9, #0x1, …`
//     长串（bit0=1）：`f9400900 ldr x0, [x8, #0x10]`（数据指针）
//     短串：`91000500 add x0, x8, #0x1`（内联数据从 +1 开始）
//   → `bl strcmp(x0, 传入的动画名)`
// 这与 `lua_object_handles.hpp`/`sprite_api.cpp` 里 `kLibcxxStringDataOffset = 16` 的长串布局一致，
// 也就是说 `Sprite:GetAnimation()` 可以只用"引擎自己证明过的读法"实现，不需要猜偏移。
inline constexpr uintptr_t kSpriteAnimationNameOffset = 0x38;
// `ANM2+0x60`：`AnimationState*`。证据来自引擎自己的 `ANM2::GetTexel`（`0xC074`）——
// 它第一件事就是 `add x0, x0, #0x60`（`0xC098`）再 tail-call
// `AnimationState::GetTexel`（`0xC0B8`）；`ANM2::Render` 也把同一个 `[this+0x60]` 当参数传下去。
// 用途：调引擎 `GetTexel` 前判"有没有当前动画状态"，指针为空就退回落值，避免空指针解引用。
inline constexpr uintptr_t kSpriteAnimationStateOffset = 0x60;

// `Sprite + 0x08`：**这个 Sprite 加载的文件名**（libc++ `std::string`，24 字节 SSO 对象）。
// 契约 `Sprite.md:70`（`#### string GetFilename ( )`），正文的例子逐字给出：
//   `print(sprite:GetFilename()) -- this prints "gfx/001.000_Player.anm2"`
// ★★★ **两处具名证据**（都在同一棵 Sprite 上）：
//   ① **写入口** = `Sprite::LoadAnimationsFile(char const*, char const*) @ 0x4A48B4`：
//        004a48c4  add  x0, x0, #0x8            ; ★ this + 0x8
//        004a48c8  bl   std::string::assign(char const*)   ; ★ 把传进来的文件名赋给这一格
//        004a48d0  strb w8(1), [x19, #0x48]     ; 另有一个"已加载"字节（不是本格）
//        004a48d8  mov  w0, #1 / ret            ; 返回 true
//      ⇒ **驱动器里的路径字符串就存在 `Sprite + 0x8`**，而且是"整串 assign"（不是指针）。
//   ② **构造函数** `Sprite::Sprite() @ 0x4A4658`：
//        004a466c  ldr  x8, [x8, #0x390]        ; _ZTVSprite
//        004a4670  add  x8, x8, #0x10
//        004a4680  stp  x8, xzr, [x0]           ; ★ [this+0]=vptr、**[this+8]=0** ⇒ 空串
//      ⇒ 这一格在构造时被清成**空**（与"没加载过的 Sprite，`GetFilename()` 答 `""`"一致 ——
//        语料里 `customgrids.lua:547` 正是拿 `== ""` 判"还没加载"）。
// ★ 读法与 `kSpriteAnimationNameOffset` 那一族**同一套**（libc++ SSO 口径：
//   `kLibcxxStringLongFlag` / `kLibcxxStringDataOffset` / `kLibcxxStringShortDataOffset`），
//   实现复用 `sprite_api.cpp` 里那份唯一的 `ReadLibcxxStringAt`。
// ★ PC 侧的绑定 `GetFilename` 在 `isaac-ng.exe` 的名字表里**没有被引用**（`push 引用 0 处`）
//   ⇒ PC 侧的偏移（若有）读不到；本条的判定**完全靠 Switch 侧这两处具名函数**。
// ★ 2026-10-23更正：上方Sprite类证据不适用于Lua Sprite（实际ANM2）。
// ANM2::Load@0xC9C4把this直接作为string赋值目标；原生文件名位于+0。
// 真机长串+0/+8/+0x10依次是cap/len/data，旧+8读法会把长度当SSO头。
inline constexpr uintptr_t kSpriteFilenameOffset = 0x00;
// `ANM2+0x54`：在播标志（同一个 `IsPlaying` 读到的第二个条件）。
inline constexpr uintptr_t kSpritePlayingFlagOffset = 0x54;

// ---------------------------------------------------------------------------
// `Sprite` 的三个**可写**属性在 `ANM2` 里的落点（2026-09-16）
// ---------------------------------------------------------------------------
// 这三条是"引擎写通道"的第一批落点：PC 的 `Sprite.Scale` / `Sprite.Color` / `Sprite.FlipX`
// 在 PC 上就是写 `ANM2` 的成员，之前我们只把值缓存进句柄（渲染时读不到差别），现在按下面
// 两条互不相同的证据写进原生对象。
//
// **证据一：`ANM2::Reset`（`0x65B8`）—— 构造/复位时写的默认值，本身就把语义钉住了**
//   * `0x670C add x0,x19,#0xdc` → `bl Vector2::operator=(Vector2 const&)`，右操作数是
//     `KAGE::Math::Vector2::One`（`0x6708 ldr x1,[…] ; _ZN4KAGE4Math7Vector23OneE`）
//     ⇒ `ANM2+0xDC` 是**缩放向量**，默认 `(1,1)`；
//   * `0x6704/0x6708` 前一条同类指令是 `0x66E4 add x0,x19,#0xd4` → 同一个 `operator=`
//     但右操作数是 `Vector2::Zero`（`_ZN4KAGE4Math7Vector24ZeroE`）⇒ `+0xD4` 是另一个
//     向量（渲染里加在位置上的那个，本轮不用，仅登记）；
//   * `0x6714 add x0,x19,#0xe8` → `bl ColorMod::Reset()` ⇒ `ANM2+0xE8` 是一个 `ColorMod`
//     （精灵自身的颜色），`0x6720 add x20,x19,#0x114` → 又一次 `ColorMod::Reset()` ⇒ 第二个
//     `ColorMod` 落在 `0x114` ⇒ **第一个 `ColorMod` 占 `0xE8..0x114`，共 0x2C 字节**；
//   * `0x6754 strh wzr,[x19,#0x140]` ⇒ `0x140`/`0x141` 是**两个相邻的字节标志**，默认 0。
//
// **证据二：`ANM2::AnimationLayer::GetDestQuad`（`0x9790`）—— 渲染时怎么用这三格**
//   （该函数第 6 个参数 `x6` 就是 `ANM2 const*`，函数符号自带 `…, ANM2 const*)`）
//   * `0x9824 ldr x8,[x26,#0xdc]!`（`x26` = `ANM2`）一次性读 **8 字节** = 缩放向量的
//     `X@0xDC`/`Y@0xE0`，随后与图层缩放一起进 `Vector2::operator*`（`0x9834`）；
//   * `0x97DC ldrb w23,[x6,#0x140]` 与 `0x97C4 ldrb w8,[x6,#0x141]` 读那两个字节，
//     用于决定四边形是否镜像 ⇒ 就是 PC 的 `FlipX`/`FlipY`；
//   * `0x97D0 ldr w11,[x3,#0x90]`＋`0x97F8 orr w24,w11,w10`（`w10=[ANM2+0x150]`）是把
//     图层标志与 `ANM2+0x150` 合起来判混合模式，与颜色无关（旁证：`0x150` 不是颜色）。
//
// **`ColorMod` 自己的布局（写颜色要知道哪 4 个 float 是 tint）**
//   * `ColorMod::Reset`（`0x37830`）：`0x37834 stp x8,x8,[x0]`（`x8` = `0x3f8000003f800000`
//     = 两个 `1.0f`）+ `0x37838 str xzr,[x0,#0x20]` + `0x3783C str wzr,[x0,#0x28]` +
//     `0x37840 stp xzr,xzr,[x0,#0x10]` ⇒ 头 8 字节 = 两个 1.0f（tint），`0x10..0x1C` 清零（偏移量）；
//   * `ColorMod::SetTint`（`0x37848`）：`str s0,[x0]` / `str s1,[x0,#0x4]` / `str s2,[x0,#0x8]` /
//     `str s3,[x0,#0xc]` ⇒ **tint 的 R/G/B/A 就在 `+0x00/+0x04/+0x08/+0x0C`**；紧随其后的
//     `0x3785C` 起同样四条 `str` 打在 `+0x10/+0x14/+0x18/+0x1C`（偏移量四元组）；
//   * `ColorMod::operator*=`（`0x37BEC`）：`+0x00..+0x0C` 走 `fmul`（相乘），`+0x10..+0x1C`
//     走 `fadd`/平均（叠加）⇒ 与 PC `Color` 的"RGB 乘、Offset 加"一致。
inline constexpr uintptr_t kSpriteScaleOffset = 0xDC;    // Vector2（缩放 X@+0xDC、Y@+0xE0）
inline constexpr uintptr_t kSpriteColorOffset = 0xE8;    // ColorMod：tint 在 +0x00..+0x0C
// PC PlaybackSpeed getter447CB0读取ANM2+104；NS ctor6748初始化+144=1.0，
// NS Update86F4/8748通过AnimationState.owner读取同一+144，参与实际帧推进。
// 原件反汇编：dist/callback-rplus-20261013/{pc-playback-speed,ns-anm2-ctor,ns-anm2-update}.txt。
inline constexpr uintptr_t kSpritePlaybackSpeedOffset = 0x144; // float，逐对象共享原生值
inline constexpr uintptr_t kSpriteFlipXOffset = 0x140;   // u8
// Reset @0x6754 clears both bytes; GetDestQuad @0x97C4 reads +0x141,
// then @0x98BC/0x98D4 uses it for the Y component (X uses +0x140).
inline constexpr uintptr_t kSpriteFlipYOffset = 0x141;   // u8
// `ColorMod` 内部偏移：tint 的 R/G/B/A 与"偏移量"四元组的起点。
inline constexpr uintptr_t kColorModTintOffset = 0x00;
// 2026-10-10 更正：旧注释把 SetColorize 当作 SetOffset，原始记录保存在本批 before。
// NS SetColorize@0x3785C 写+10..1C，SetOffset(float)@0x37870 写+20/+24/+28；
// PC SetOffset@0x65AEE0 同写+20/+24/+28，FillVertices@0x378F4 真正消费这些格子。
inline constexpr uintptr_t kColorModColorizeOffset = 0x10;
inline constexpr uintptr_t kColorModShiftOffset = 0x20;
inline constexpr std::size_t kColorModSize = 0x2C;
// PC `Color` 的第 5/6/7 个分量（`RO/GO/BO`）在我们的 `KColor` 句柄里也有对应字段
// （`lua_object_handles.hpp` 的 `ColorHandle::offsetRed/Green/Blue`），所以一并写进去。

// `Sprite`（引擎侧 `IsaacRepentance::ANM2`）第一步用到的入口：全部是 `char const*`/数值参数，
// 不涉及 `std::string`，因此没有 ABI 风险。对象尺寸见 `kSpriteObjectSize` 的注释。
// 构造函数 `ANM2::ANM2()`
inline constexpr uintptr_t kSpriteCtorOffset = 0x6540;
inline constexpr std::array<u8, 16> kSpriteCtorExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
// 完整对象析构 `ANM2::~ANM2()`（D1：**不释放内存**，内存由我们自己 free）
inline constexpr uintptr_t kSpriteDestructorOffset = 0x71A4;
inline constexpr std::array<u8, 16> kSpriteDestructorExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
// `void Play(char const*, bool)`
// `bool SetAnimation(char const*, bool)`
// `void SetFrame(char const*, int)`
inline constexpr uintptr_t kSpriteSetFrameNamedOffset = 0xA65C;
inline constexpr std::array<u8, 16> kSpriteSetFrameNamedExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
// `void SetFrame(int)`
// `int GetFrame() const`
// `void SetLayerFrame(int, int)`
// `int GetLayerFrame(int)`
// `KColor GetTexel(Vector2, Vector2, float, int) const` —— **EID 用来判"这个底座是不是
// 赎罪线红问号底座"的唯一依据**（`main.lua:230-232` 逐点比色）。旧实现是"恒返回不透明白色"
// 的占位，导致两个 sprite 处处相等 → 每个底座都被判成问号底座 → EID 只画问号、不写描述。
//
// 偏移与 ABI 出处：`analysis/stage150-sprite-abi/<build>.json` 的
// `records.sprite_get_texel`（`confidence = verified`）——
//   * `.dynsym` 符号 `_ZNK15IsaacRepentance4ANM28GetTexelEN4KAGE4Math7Vector2ES3_fi`
//     → file_offset `0xC074`（下面这 16 字节是**从 NRO 抄录**并与镜像逐字节核对过的）；
//   * 前两个 `KAGE::Math::Vector2` **按值传**（HFA → s0..s3），`s4` = alphaThreshold，
//     `w1` = layerId；返回值是 16 字节 `KColor`，走 **x8 间接结果寄存器**
//     （函数体里 `mov x20,x8` 把它存下来，`0xC0B4`）。
// --- 批次 214（2026-09-30）：中文版 MCM 要用的三条 Sprite 方法 -------------------------------
//
// 为什么补：中文版 `!!Mod Config Menu Chinese`（工坊 2494192799）新增的 `scripts/filepathhelper.lua`
// 用 `anm2Tester:GetDefaultAnimationName() ~= "" or anm2Tester:GetLayerCount() > 0` 判"这条路径是不是
// 一个真 anm2"（它靠这个给自己的中文字体找路径），并且紧接着 `anm2Tester:Reset()`——
// **那三行不在 `pcall` 里**（只有 `Load` 被包着）⇒ 缺任何一条都会抛错、把调用方整条回调打断。
inline constexpr uintptr_t kSpriteResetOffset = 0x65B8;
// 2026-10-23更正：Lua Sprite使用ANM2，4A4724是另一个Sprite类，不能混用。
inline constexpr std::array<u8, 16> kSpriteResetExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
}; // ANM2::Reset @0x65B8，与原NRO动态符号及入口16B独立核同。

//: `Sprite` 里的 **ANM2 指针**：`Sprite+0x30`（`ANM2::GetLayerFrame @private:kSpriteGetLayerFrameOffset` 就是 `ldr x9,[x19,#0x30]`
//: 之后 `ldr w9,[x9,#0xb0]`）。★ 别与 `Sprite+0x38` 混 —— 那个是当前动画名的 `std::string`。
inline constexpr uintptr_t kSpriteAnm2Offset = 0x30;
// 2026-10-15订正：ANM2+0x18存原XML DefaultAnimation的libc++字符串。
// Preload2@0x10FD8..11020解析属性到缓存+0x70；Load2@0xF8F0..F8FC复制到this+0x18；
// Reset@0x6630..6658清空该串。+0x30是AnimationState的owner/self，构造@0x6554写this。
inline constexpr uintptr_t kSpriteDefaultAnimationNameOffset = 0x18;
//: ANM2 里的**层数**（`ANM2+0xB0`，`ANM2::GetLayerFrame` 用它做 layer 越界判定）。
inline constexpr uintptr_t kAnim2LayerCountOffset = 0xB0;
//: ANM2 里的**动画表**：数组基址 `+0x98`、个数 `+0xA0`、每项步长 `0x150`
//: （`ANM2::SetAnimation @private:kSpriteSetAnimationOffset`：`ldr w23,[x0,#0xa0]` / `ldr x21,[x0,#0x98]` / `add x21,x21,#0x150`）。
inline constexpr uintptr_t kAnim2AnimationArrayOffset = 0x98;
inline constexpr uintptr_t kAnim2AnimationCountOffset = 0xA0;
inline constexpr std::size_t kAnim2AnimationStride = 0x150;
// ★ 读引擎字符串**复用既有那套常量**（`kLibcxxStringDataOffset` / `kLibcxxStringShortDataOffset` /
//   `kLibcxxStringLongFlag`，见本文件后面 `Sprite:GetAnimation` 那一族用的同一套）——
//   同一件事只留一个真值源。这里的取证只是给那套常量补一条**独立的**证据：
//   `ANM2::SetAnimation @private:kSpriteSetAnimationOffset` 里 `ldrb w8,[x21] ; tbnz w8,#0x0 → 用 [x21+0x10] 当数据指针 ; 否则用 x21+1`。

// --- 批次 214：`Seeds`（`Game:GetSeeds()`）----------------------------------------------------
//
// ★ 对象布局（`Seeds::Seeds @0x49CBD4` 构造 + `Seeds::Reset @0x49CC34` 都是这个形状）：
//   `+0x00` u8（标志）、`+0x04` u32、`+0x08` 一个 `RNG`、`+0x58` 起是 `std::set<eSeedEffect>`
//   （libc++ `__tree`：`+0x58` end 结点、`+0x60` 根、`+0x68` 元素个数）。
// ⇒ **生效中的种子效果存在那棵 set 里**（不是位图）⇒ `HasSeedEffect` 只能走树查找。
inline constexpr uintptr_t kSeedsEffectTreeOffset = 0x58;
//: libc++ `__tree_node` 的字段：左孩子 `+0x00`、右孩子 `+0x08`、**键** `+0x1c`
//: （证据：`Seeds::SeedEffectBlocksAchievements @0x49ED14` 的查找循环 `ldr w11,[x10,#0x1c]` /
//: `ldr x10,[x10,w11,uxtw #3]`）。
inline constexpr uintptr_t kLibcxxTreeNodeLeftOffset = 0x00;
inline constexpr uintptr_t kLibcxxTreeNodeRightOffset = 0x08;
inline constexpr uintptr_t kLibcxxTreeNodeKeyOffset = 0x1C;
// ★ `Seeds::Reset()`（`0x49CC34`，16 字节序言 = `FD 7B BE A9 F4 4F 01 A9 FD 03 00 91 F3 03 00 AA`）
//   的**取证已完成但这一批不登记常量**：Seeds 一族还没有任何已发布的绑定，要用它得先建整套
//   "Seeds 绑定表 + 发布 + 校验 + 取址助手"；而两个 MCM 变体只用 `Has/Add/Remove`。
//   常量保持不登记（否则 ABI 门禁会要求一个不存在的调用点）—— 取证记在存档与当日记忆里，下一批直接落。

inline constexpr uintptr_t kSpriteGetTexelOffset = 0xC074;
inline constexpr std::array<u8, 16> kSpriteGetTexelExpectedBytes = {
    0xFF, 0x83, 0x01, 0xD1, 0xEC, 0x0B, 0x00, 0xFD,
    0xF5, 0x27, 0x00, 0xF9, 0xEB, 0xAB, 0x01, 0x6D,
};

// --- `Level::GetCurses()` 的完整语义所需的两个 `Game` 方法（2026-09-12）-------------
//
// 反汇编 `Level::GetCurses`（`0x3D57CC`，`docs/问题与解决记录.md` 批次 4 记过它读
// `this+0xC`）得到 PC 的完整三步：
//
//     ldr w19,[x0,#0xc]            ; ① Level 自己的诅咒位（我们**已经**在做的一步）
//     ldr x20,[x20,#0x698]         ; 全局 Game 槽
//     ldr x0,[x20]                 ; → Game*
//     bl  GetSpecialSeedPermanentCurses()   ; ② 特殊种子"永久诅咒" —— 调用点 `0x3D57E8`
//     orr w0, w19, w0              ;    合成：curses | permanent（`0x3D57EC`）
//     ldr x0,[x20]
//     bl  GetSpecialSeedBannedCurses()      ; ③ 特殊种子"禁用诅咒" —— `0x3D57F4`
//     and w0, w0, w19              ;    合成：... & banned（`0x3D57F8`）
//
// GOT 槽 `0xAA3E20`/`0xAA3E28` 的重定位表把这两个 PLT 桩解析成
// `_ZNK15IsaacRepentance4Game29GetSpecialSeedPermanentCursesEv` 与
// `_ZNK15IsaacRepentance4Game26GetSpecialSeedBannedCursesEv`（`.dynsym` 里查得到，
// 地址即下面的偏移）。旧实现只做了 ① —— 于是特殊种子（Victory Lap / 挑战 / 种子局）的
// 永久诅咒读不到、"禁用诅咒"也屏蔽不掉，`EID:hasCurseBlind()` 可能因此误判。
inline constexpr uintptr_t kGameSpecialSeedPermanentCursesOffset = 0x35097C;
inline constexpr std::array<u8, 16> kGameSpecialSeedPermanentCursesExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0xB4, 0x8B, 0x52,
};
inline constexpr uintptr_t kGameSpecialSeedBannedCursesOffset = 0x350B98;
inline constexpr std::array<u8, 16> kGameSpecialSeedBannedCursesExpectedBytes = {
    0x08, 0xB4, 0x8B, 0x52, 0x48, 0x00, 0xA0, 0x72,
    0x08, 0x00, 0x08, 0x8B, 0x09, 0x01, 0x40, 0xF9,
};
// `Pickup.Touched` 的字段偏移仍是 `kEntityPickupTouchedOffset`；那个偏移本身是"待真机确认"
// 的猜测，本轮探针就是去确认它。
// `void Update()`
inline constexpr uintptr_t kSpriteUpdateOffset = 0x86BC;
inline constexpr std::array<u8, 16> kSpriteUpdateExpectedBytes = {
    0xE8, 0x0F, 0x1E, 0xFC, 0xFD, 0xFB, 0x00, 0xA9,
    0xFD, 0x23, 0x00, 0x91, 0xF3, 0x0F, 0x00, 0xF9,
};
// `bool IsPlaying(char const*) const`
// `bool IsFinished(char const*) const`
// `void Render(Vector2 const&, Vector2 const&, Vector2 const&)`
inline constexpr uintptr_t kSpriteRenderOffset = 0x9BD4;
inline constexpr std::array<u8, 16> kSpriteRenderExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
// `void RenderLayer(int, Vector2 const&, Vector2 const&, Vector2 const&)`
// `void PlayRandom(unsigned int)`

// 第二步：`Load`/`ReplaceSpritesheet` 需要 libc++ 的 `std::string`（24 字节 SSO），本模块编的是
// libstdc++（32 字节），所以不能直接传自己的 string。做法是借游戏自己导入的
// `basic_string::assign(char const*)` 往一块 24 字节缓冲里填值 —— 全零的 24 字节在 libc++ 里
// 本来就是合法的空短串（long 标志位为 0、size 为 0），这是最弱的一个假设。
// `void Load(std::string const&, bool)`
// ★ 2026-10-04（批次 363）：这一个函数的 mangled 名是 `IsaacRepentance::ANM2::Load(...)`
//   —— Lua 侧的 `Sprite:Load` 与引擎侧的 `ANM2::Load` **是同一个地址**（符号表复核，见
//   本文件末尾"模组覆盖本体资源"那一段的说明）。批次 363 的入口中继挂的就是它，
//   所以**没有**另立 `kAnm2Load*` 常量：一个地址只留一个名字与一份守卫。
inline constexpr uintptr_t kSpriteLoadOffset = 0xC970;
inline constexpr std::array<u8, 16> kSpriteLoadExpectedBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFB, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};
// `LoadGraphics()`（thunk：`mov w1,wzr; b load_graphics(false)`）
// `void ReplaceSpritesheet(int, std::string const&)`
// 游戏导入的 libc++ `basic_string::assign(char const*)` PLT 桩（字符串桥用）
inline constexpr uintptr_t kLibcxxStringAssignOffset = 0x66FB80;
inline constexpr std::array<u8, 16> kLibcxxStringAssignExpectedBytes = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0x96, 0x46, 0xF9,
    0x10, 0xA2, 0x34, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
// `IContentManager::GetMountedFilePath(char const*)`：内容路径 → 真实文件路径（找不到返回 null）。
// 引擎自己的 `ImageManager::LoadImage` 就是这么解析贴图文件的，所以我们用同一条路径判断"在不在"。
// 注意：返回的是**引擎分配**的字符串（调用方按需释放；我们只做存在性判断，沿用引擎自身"不释放"的做法）。
inline constexpr uintptr_t kContentGetMountedFilePathOffset = 0x4C2340;
inline constexpr std::array<u8, 16> kContentGetMountedFilePathExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};

// 游戏导入的 `operator delete(void*)`（`_ZdlPv`）PLT 桩。
// **为什么需要它**：字符串桥借游戏的 `basic_string::assign(char const*)` 建出来的是 libc++ 的
// 24 字节 `std::string`；路径超过 SSO 容量时，缓冲是**游戏模块的分配器**分配的。本模块（`subsdk9`）
// 有自己的 newlib 堆，用本模块的 `free` 去释放会踩坏堆 —— 必须走游戏自己的 `operator delete`。
inline constexpr uintptr_t kGameOperatorDeleteOffset = 0x66FB10;
inline constexpr std::array<u8, 16> kGameOperatorDeleteExpectedBytes = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0x7A, 0x46, 0xF9,
    0x10, 0xC2, 0x33, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
// libc++ `std::string` 的 `__long` 布局实测（2026-09-13 真机探针，掩码位 17/18）：
// 数据指针在对象**偏移 16**；首字的**最低位为 1 表示 long**（短串则内联，位 14 实测）。
inline constexpr std::size_t kLibcxxStringDataOffset = 16;
// 短串（SSO）的内联数据从对象**偏移 1** 开始 —— 首字节存 `size << 1`（最低位是 long 标志）。
// 证据同样是引擎自己的代码：`ANM2::IsPlaying`（`private:kSpriteIsPlayingOffset`）的 `91000500 add x0, x8, #0x1` 之后
// 直接 `strcmp`，也就是把 `对象+1` 当 C 串首地址用（与 libc++ 的 `__short::__data_` 一致）。
inline constexpr std::size_t kLibcxxStringShortDataOffset = 1;
// 长串标志位（首字最低位）。
inline constexpr std::uint8_t kLibcxxStringLongFlag = 0x01;

inline constexpr uintptr_t kGameIsGreedModeOffset = 0x350200;
// Guard transcribed from `Repentance.nro` @0x350200 and cross-checked against the project's own
// `analysis/starterr-native-evidence/universal-getter-inventory-*.json`
// (`anchors.game_is_greed_mode.entry_guard`). Byte 10 used to read 0xB8 instead of 0x68; because
// `VerifyGameIsGreedMode` compares all 16 bytes with `memcmp`, that single wrong byte disabled the
// whole `Game:IsGreedMode` binding on hardware (fixed 2026-09-13, see docs/问题与解决记录.md).
inline constexpr std::array<u8, 16> kGameIsGreedModeExpectedBytes = {
    0x08, 0x05, 0x80, 0x52, 0xE8, 0x05, 0xA0, 0x72,
    0x08, 0x68, 0x68, 0xB8, 0x08, 0x79, 0x1F, 0x12,
};
inline constexpr uintptr_t kLevelIsAscentOffset = 0x3E1D98;
inline constexpr std::array<u8, 16> kLevelIsAscentExpectedBytes = {
    0x08, 0x00, 0x40, 0xB9, 0x08, 0x05, 0x00, 0x51,
    0x1F, 0x15, 0x00, 0x71, 0x28, 0x01, 0x00, 0x54,
};
// 批次 8（2026-09-15）：EID 在**描述构建**路径上无条件调用、而我们此前没有的两个 `Level` 成员。
// 两个偏移与守卫都取自 `docs/PC-Lua-API-对照清单.md` 的 `missing_easy` 表（该表的
// `file_offset` 已由两个上机验证过的守卫证明"等于运行时模块偏移"，见文档 §3.3）；
// 守卫就是该偏移处的 16 字节原文，安装期逐字节比对。
//
//   * `Level:GetAbsoluteStage()` —— `features/eid_modifiers.lua:197`（潘多拉魔盒条目）与
//     `eid_conditionals_funcs.lua:363/369`、`eid_grid_descriptions.lua:108`、`eid_modifiers.lua:1164`；
//   * `Level:IsNextStageAvailable()` —— `features/eid_holdmapdesc.lua:174`。
//
// 两者都是 `const` 成员函数，返回 `int` / `bool`，参数只有 `this`（`Level*`）一个 —— 与
// `Level::IsAscent` 同一形状，所以 handler 走同一条"解析指针链 → 直接调用"的路。
inline constexpr uintptr_t kLevelGetAbsoluteStageOffset = 0x3E7F3C;
inline constexpr std::array<u8, 16> kLevelGetAbsoluteStageExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x28, 0x36, 0x00, 0xB0,
};
inline constexpr uintptr_t kLevelIsNextStageAvailableOffset = 0x3DBDBC;
inline constexpr std::array<u8, 16> kLevelIsNextStageAvailableExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
// 批次 270（2026-10-02）：`Level:QueryRoomTypeIndex(RoomType, Visited, RNG, IgnoreGroup)` ——
// 作业单第二节 `needs_new_shape` 桶的**最后一条**（1 处 / RepentancePlus）。
//
// PC 契约 `tools/pc_contract_docs/Level.md:328`：
// `#### int QueryRoomTypeIndex ( [RoomType](enums/RoomType.md) RoomType, boolean Visited,
// [RNG](RNG.md) rng, boolean IgnoreGroup = false )`（正文 `:329`：`IgnoreGroup` 置真时把
// "分组 ID 不同的房间"也算进来，**当前未使用**）。
//
// Switch 侧符号 = `Level::QueryRoomTypeIndex(eRoomType, bool, RNG&, bool)` @ **`0x3E605C`**
// （dynsym 里逐字有这个名字；mangled `_ZN15IsaacRepentance5Level18QueryRoomTypeIndexENS_9eRoomTypeEbRNS_3RNGEb`）。
// `python3 tools/nro_disasm.py 0x3e605c 0x200` 给出两件本批依赖的事：
//   ① 寄存器形状：`w1` = RoomType（`and w8,w1,#0xfffffffe` + `cmp w8,#0xe` 是 `RoomType` 的分支）、
//      `w23 = w1`（后续 `cmp w23,#3` / `cmp w23,#0x16`）、`x3` **存进 x20**（`mov x20, x3`
//      @ `0x3E60D4`）⇒ 第三个参数是个**指针**，与 mangled 名里的 `RNG&` 一致；
//   ② "没有这种房间"时它自己返回 **`-1`**（`mov w19, #-0x1` @ `0x3E6094`）——
//      这正是我们降级时要给的值（见 handler 处的注释）。
//
// ★ **不需要新形状**：工作单把它判进 `needs_new_shape` 是因为数据行机制只认标量参数，而这里
//   第 3 个参数是 `RNG&`。但**手写处理器本来就什么形状都能写**（`Isaac:CountEntities` 那条
//   4 参 + 指针同样是手写），所以本批手写、**不动 `EngineCallShape` 表**
//   —— 加形状要"三处同步"（表尾 + 枚举 + ABI 工具），能不动就不动。
//   ★ `RNG` 句柄本身就**是**引擎对象：`RngHandle` 是 `std::array<u8, kRngObjectSize>` 的裸存储，
//   `RNG:SetSeed`/`Next`/`RandomInt` 全都把 `storage.data()` 当 `this` 传给引擎方法
//   （`rng_api.cpp:78/94/158`）⇒ 把它的地址当 `RNG&` 交出去是**同一件东西**，不是替身。
inline constexpr uintptr_t kLevelQueryRoomTypeIndexOffset = 0x3E605C;
inline constexpr std::array<u8, 16> kLevelQueryRoomTypeIndexExpectedBytes = {
    0xFF, 0x43, 0x02, 0xD1, 0xFD, 0x7B, 0x03, 0xA9,
    0xFD, 0xC3, 0x00, 0x91, 0xFC, 0x6F, 0x04, 0xA9,
};
// `Room::GetFrameCount()`（2026-09-16 补，PC：`Room:GetFrameCount()` ——
// "Returns the amount of frames the room has been active for. Resets to 0 when the player leaves
// the room or the run is exited."）。
//
//   * 符号：`_ZN15IsaacRepentance4Room13GetFrameCountEv`，文件偏移 **`0x470B0C`**，arity 0（只有 `this`）；
//     来源 `analysis/lua-api-inventory/inventory.json`（`match_kind: exact_class`、
//     `match_confidence: high`、`thunk_readiness: ready`），16 字节守卫也取自同一条目。
//   * 语义证据（我们自己的指令级记录，见本文件 `kGameFrameCountOffset` 的注释）：
//     引擎里 `Room::GetFrameCount` 与 `Entity::GetFrameCount` 同形 ——
//     `ldr w8,[Game+0x24F99C]; sub w0,w8,[this+进入房间时的帧号]`
//     ⇒ "本局帧计数 − 进房间那一刻的帧号"，所以离开房间会归零。
//   * EID 用法：`features/eid_bagofcrafting.lua:967` 的 `game:GetRoom():GetFrameCount() < 2`
//     （刚进房间前两帧不显示合成结果）、`eid_bagofcrafting_search.lua:166`、`eid_debugging.lua:202`。
//     **缺它时**：背包合成那条渲染路径**每帧抛错**（`attempt to call a nil value (method
//     'GetFrameCount')`），EID 的描述渲染整段被打断 —— 这是 2026-09-16 真机上暴露出来的。
inline constexpr uintptr_t kRoomGetFrameCountOffset = 0x470B0C;
inline constexpr std::array<u8, 16> kRoomGetFrameCountExpectedBytes = {
    0x08, 0x00, 0x40, 0x39, 0x48, 0x01, 0x00, 0x34,
    0xE8, 0x31, 0x00, 0x90, 0x08, 0x4D, 0x43, 0xF9,
};
inline constexpr uintptr_t kManagerMusicOffset = 0x36068;

// ---- 批次 185（2026-09-28）：音效（`SFXManager`）的"从哪里拿"与 `IsPlaying` --------
//
// **`Manager` 里 `SoundEffects` 子对象的偏移 = `0x364A8`。**
// 取证（本批做出来的 —— 批次 177 把 `SFXManager:IsPlaying` 留到下一批，缺的就是这个数）：
// `IsaacRepentance::Manager::PlaySound(eSoundEffect, float, int, float, float)` @ `0x3F9B9C`
// 里这么算（复核命令 `python3 tools/nro_disasm.py 0x3f9bd0 40`）：
//     `mov w8, #0x64a8` ＋ `movk w8, #0x3, lsl #16`   ⇒ `w8 = 0x364A8`
//     `add x0, x21, x8`                               ⇒ `x0 = this(Manager) + 0x364A8`
//     `b 0x672870`（import 桩 `SoundEffects::Play(eSoundEffect, float, int, float, float)`）
//   ⇒ 那个 `this + 0x364A8` 就是被当成 `SoundEffects` 传进 `Play` 的 ✓
//   ★ 旁证：与已在用的 `kManagerMusicOffset = 0x36068` 只差 `0x440`，同区间。
//   ★ 顺带解释了"全镜像搜 `bl SoundEffects::*` 是 0 处"（本批真搜过：`IsPlaying`/`Play`/`Update`
//     各 0 处）：引擎走的是 **import 桩**（`0x672870` 那类），不是直接 `bl` 到 `0x4A2xxx`。
inline constexpr uintptr_t kManagerSoundEffectsOffset = 0x364A8;

// `SoundEffects::IsPlaying(eSoundEffect) const` @ `0x4A38AC`
//   （符号 `_ZN15IsaacRepentance12SoundEffects9IsPlayingENS_12eSoundEffectE`）。
// PC 契约 `tools/pc_contract_docs/SFXManager.md:48`：「boolean IsPlaying ( SoundEffect ID )」。
// ⇒ 收 1 个整数、返回布尔；接收者从 `Manager + kManagerSoundEffectsOffset` 解析（不是从 Lua 栈）。
// 入口 4 字节 `FD 7B BC A9` → `0xA9BC7BFD`（`stp x29, x30, [sp, #-0x40]!`）。

// 2026-10-09：其余七个 SFX 接口，偏移与完整参数均来自该 NRO 动态符号。
// _ZN15IsaacRepentance12SoundEffects11AdjustPitchENS_12eSoundEffectEf
inline constexpr uintptr_t kSoundEffectsAdjustPitchOffset = 0x4A33FC;
inline constexpr std::array<u8, 16> kSoundEffectsAdjustPitchExpectedBytes = {
    0xE8, 0x0F, 0x1D, 0xFC, 0xFD, 0xFB, 0x00, 0xA9, 0xFD, 0x23, 0x00, 0x91, 0xF5, 0x0F, 0x00, 0xF9
};
// _ZN15IsaacRepentance12SoundEffects12AdjustVolumeENS_12eSoundEffectEf
inline constexpr uintptr_t kSoundEffectsAdjustVolumeOffset = 0x4A32CC;
inline constexpr std::array<u8, 16> kSoundEffectsAdjustVolumeExpectedBytes = {
    0xEA, 0x0F, 0x1A, 0xFC, 0xE9, 0x23, 0x01, 0x6D, 0xFD, 0x7B, 0x02, 0xA9, 0xFD, 0x83, 0x00, 0x91
};
// _ZN15IsaacRepentance12SoundEffects21GetAmbientSoundVolumeENS_12eSoundEffectE
inline constexpr uintptr_t kSoundEffectsGetAmbientSoundVolumeOffset = 0x4A3C9C;
inline constexpr std::array<u8, 16> kSoundEffectsGetAmbientSoundVolumeExpectedBytes = {
    0xE8, 0x0F, 0x1B, 0xFC, 0xFD, 0x7B, 0x01, 0xA9, 0xFD, 0x43, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9
};
// _ZN15IsaacRepentance12SoundEffects7PreloadENS_12eSoundEffectE
inline constexpr uintptr_t kSoundEffectsPreloadOffset = 0x4A202C;
inline constexpr std::array<u8, 16> kSoundEffectsPreloadExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF6, 0x57, 0x01, 0xA9, 0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9
};
// _ZN15IsaacRepentance12SoundEffects15SetAmbientSoundENS_12eSoundEffectEff
inline constexpr uintptr_t kSoundEffectsSetAmbientSoundOffset = 0x4A3964;
inline constexpr std::array<u8, 16> kSoundEffectsSetAmbientSoundExpectedBytes = {
    0xEB, 0x2B, 0xB8, 0x6D, 0xE9, 0x23, 0x01, 0x6D, 0xFB, 0x1B, 0x00, 0xF9, 0xFD, 0x7B, 0x02, 0xA9
};
// _ZN15IsaacRepentance12SoundEffects4StopENS_12eSoundEffectE
inline constexpr uintptr_t kSoundEffectsStopOffset = 0x4A35BC;
inline constexpr std::array<u8, 16> kSoundEffectsStopExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9, 0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9
};
// _ZN15IsaacRepentance12SoundEffects17StopLoopingSoundsEv
inline constexpr uintptr_t kSoundEffectsStopLoopingSoundsOffset = 0x4A36A0;
inline constexpr std::array<u8, 16> kSoundEffectsStopLoopingSoundsExpectedBytes = {
    0xFD, 0x7B, 0xBB, 0xA9, 0xF9, 0x0B, 0x00, 0xF9, 0xFD, 0x03, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9
};

inline constexpr uintptr_t kSoundEffectsIsPlayingOffset = 0x4A38AC;
inline constexpr std::array<u8, 16> kSoundEffectsIsPlayingExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};

// ---- 批次 408（2026-10-08）：`SFXManager:Play` 的真入口（本批把"空实现"接上引擎）-------
//
// `IsaacRepentance::SoundEffects::Play(eSoundEffect, float, int, bool, float, float)` @ `0x4A2FD0`
//   （符号 `_ZN15IsaacRepentance12SoundEffects4PlayENS_12eSoundEffectEfibff`）。
// PC 契约 `tools/pc_contract_docs/SFXManager.md:53`：
//   `void Play ( SoundEffect ID, float Volume = 1, int FrameDelay = 2, boolean Loop = false,
//                float Pitch = 1, float Pan = 0 )`
//   ⚠️ 契约里的 `FrameDelay` 是 **`int`、缺省 `2`**（不是 `float`、不是 `0`）—— 本文件按契约原文，
//      不按别处转述的版本；`?frame?` 那个"缺省 2"在真机上就是"同一音效至少隔 2 帧才允许再播"。
// ⇒ 六个形参按 AArch64 ABI 落：`x0 = this`、`w1 = ID(int)`、`s0 = Volume(float)`、
//   `w2 = FrameDelay(int)`、`w3 = Loop(bool)`、`s1 = Pitch(float)`、`s2 = Pan(float)`。
//
// ★★ 三条**互相独立**的证据（指到反汇编行；复核命令写在每条里）：
//   ① **动态符号表**（`tools/nro_symbols.py` 的 `parse_dynamic_symbols` 读出）：一条
//      `_ZN15IsaacRepentance12SoundEffects4PlayENS_12eSoundEffectEfibff` @ `0x4A2FD0`。
//      Itanium 名字末尾 `E fibff` 逐字 = `(eSoundEffect, float, int, bool, float, float)` ——
//      与 PC 契约的参数**个数、顺序、类型逐一对上**（`f`=Volume、`i`=FrameDelay、`b`=Loop、
//      `f f`=Pitch/Pan）。
//   ② **引擎自己的调用点实参**：`IsaacRepentance::Manager::PlaySound(eSoundEffect, float, int,
//      float, float)` @ `0x3F9B9C` 的尾部（`python3 tools/nro_disasm.py 0x3f9b9c 0x70`）：
//        `mov w8,#0x64a8` + `movk w8,#0x3, lsl #16`  ⇒ x8 = `0x364A8`（= 本文件
//                                                        `kManagerSoundEffectsOffset`）
//        `add x0, x21, x8`                             ⇒ x0 = `Manager + 0x364A8`（音效子对象）
//        `ldr w1, [x29,#0x1c]`                         ⇒ w1 = ID
//        `mov v0.16b, v9.16b` / `mov v1.16b, v8.16b`   ⇒ s0 = Volume、s1 = Pitch
//        `mov w2, w20` / `and w3, w19, #0x1`           ⇒ w2 = FrameDelay、w3 = Loop
//        `fmov s2, wzr`                                ⇒ s2 = Pan = 0
//        `b 0x672870`（import 桩；反汇编器把目标标成
//          `import _ZN15IsaacRepentance12SoundEffects4PlayENS_12eSoundEffectEfibff`）
//      ⇒ **引擎自己就是这么调这个函数**：接收者 = `Manager + 0x364A8`（与批次 185 的 `IsPlaying`
//        同一个子对象），实参顺序与 ① 的 ABI 推导逐条一致。
//   ③ **函数体自证**（`python3 tools/nro_disasm.py 0x4a2fd0 0x180`）：入口把
//        `mov x19,x0`（this）/`mov w22,w1`（ID）/`mov v9.16b,v0.16b`（Volume）/`mov w21,w2`（FrameDelay）/
//        `mov w20,w3`（Loop）/`mov v10.16b,v1.16b`（Pitch）/`mov v8.16b,v2.16b`（Pan）逐个收进寄存器；
//        紧接着 `umaddl x23, w22, #0x1f0, x24`（`0x4A3048`）拿 **ID 当音效表下标**（步长 `0x1F0`，
//        与本文件 `kSoundEffectSize` 同一个数）、`str s9, [x26, #0x1cc]`（`0x4A30CC`）把 **Volume 按
//        浮点存进条目**、`add w8, w8, w21`（`0x4A30D4`）把 **FrameDelay 当整数帧数**累加
//        ⇒ "w1=ID / s0=Volume / w2=FrameDelay / w3=Loop / s1=Pitch / s2=Pan" 三处互证。
//
// ★ 为什么**不**用同族另一条 `Play` 重载
//   `_ZN15IsaacRepentance12SoundEffects4PlayENS_12eSoundEffectERKN4KAGE4Math7Vector2Efibf`
//   @ `0x4A32BC`：它多收一个 `KAGE::Math::Vector2 const&`（位置）⇒ 与 PC 的 `SFXManager:Play`
//   **参数形状不符**（那是世界坐标音效用的）。两条入口的序言也完全不同：本入口
//   `sub sp,sp,#0x80`（`0x4A2FD0`），那条是 4 条指令的转发 thunk（直接 `b 0x672870`）。
//
// 入口 16 字节（**文件原始字节序**，与 `kSoundEffectsIsPlayingExpectedBytes` 同一口径）：
//   `FF 03 02 D1 EA 0B 00 FD E9 23 02 6D FD 7B 03 A9`
//   = `sub sp,sp,#0x80` / `str d10,[sp,#0x10]` / `stp d9,d8,[sp,#0x20]` / `stp x29,x30,[sp,#0x30]`。
inline constexpr uintptr_t kSoundEffectsPlayOffset = 0x4A2FD0;
inline constexpr std::array<u8, 16> kSoundEffectsPlayExpectedBytes = {
    0xFF, 0x03, 0x02, 0xD1, 0xEA, 0x0B, 0x00, 0xFD,
    0xE9, 0x23, 0x02, 0x6D, 0xFD, 0x7B, 0x03, 0xA9,
};

// ---- 批次 142（2026-09-26）：引擎侧"模组内容有没有被加载"的两个观测点 ----------------
//
// 依据（反汇编 + 真机读数，见 `docs/改动日志-20260926.md` §023/§024）：
//   * `Music::LoadConfig(char const*, bool)` 的真实入口是镜像 `0x425218`（**不是**台账
//     `inventory.json` 记的 `0x424FD8` —— 那个偏了 `0x240`），它把曲目表定在
//     `Music + 0x3D8`（`std::vector<Music::Entry>` 的 begin/end），内置场景 `resize(119)`；
//   * 真机实测 `end - begin = 13328`，且 `13328 / 119 = 112` ⇒ `sizeof(Music::Entry) = 0x70`；
//   * `ModManager` 的模组表是 `vector<ModEntry*>`，在 `ModManager + 0x00/+0x08`（`LoadConfigs`
//     开头 `ldp x21, x8, [x0]` 逐条遍历、步长 8）；`ModManager = Manager + 0x36800`；
//   * `ModEntry + 0x139` 是**引擎自己的"这个模组已启用"标志** —— `ModManager::IsActive()`
//     （镜像 `0x42277C`）就是"遍历看有没有一条非 0"；`LoadConfigs` 对每条先看这一字节，
//     为 0 就整段跳过（连 `LoadCustomResources()` 都不调）。
inline constexpr uintptr_t kManagerSelfAddressOffset = 0xABCCE0;  // 槽内容应等于 base + 它
inline constexpr uintptr_t kMusicEntryVectorBeginOffset = 0x3D8;  // vector<Music::Entry>.begin
inline constexpr uintptr_t kMusicEntryVectorEndOffset = 0x3E0;    //   …end
inline constexpr std::size_t kMusicEntrySize = 0x70;              // 13328 / 119 = 112（实测）
//: 曲目条目里的**编号**（`int32`），条目第一个字段。
//:
//: ★ 批次 149c（2026-09-27）：这条是**真机把上一版的推断否掉之后**补上的。
//: 上一版（148）把"名字在条目起点"当结论，依据是**排除法**（两条读路径都不碰 `+0x00..+0x1F`）。
//: 真机读数 `dist/gdb-read-20260927-0020.txt` 直接否掉了它：曲目表从 119 涨到 **121**
//: （模组的 `music.xml` 真进去了），而"最后一条的名字"读出来是 `'x'` ——
//: **`0x78` = 120 = 最后一条的下标**，也就是说 `+0x00` 存的是这条自己的编号，不是名字。
//:
//: 依据（写侧的属性分派，逐条可复核 —— `Music::LoadConfig @ 0x425218` 尾部那一段）：
//:   1. `0x425588` 把 `"id"` 这个属性名取进 `x27`；`0x425610` `strcmp(属性名, "id")`；
//:   2. `0x425614` 命中就跳到 `0x4256FC`：`bl atoi` → `0x42570C str w0, [sp, #0xf8]`
//:      —— `sp+0xf8` 是**模板条目**的起点 ⇒ **`id` 落在条目 `+0x00`**（4 字节）。
//: 与真机读到的 `0x78`（= 第 120 条）完全对上 ⇒ 这条是**证据最硬**的一行。
inline constexpr std::uintptr_t kMusicEntryIdOffset = 0x00;
//: 曲目条目里的**名字**：一段 24 字节的 libc++ `std::string`，从条目 `+0x08` 起。
//:
//: 依据（写侧属性分派，与上面 `kMusicEntryIdOffset` 同一条链）：
//:   1. `0x425620` 取 `"name"`、`0x425624 strcmp` ⇒ 命中跳 `0x425714`；
//:   2. `0x425714`：`[sp,#0x70]` 装的正是**条目 `+0x08`**（`0x425538 add x9, x8, #0x8`
//:      把 `模板+0x08` 存进 `[sp,#0x70]`，`0x42553C str x9, [sp, #0x70]`），
//:      随后 `0x425724 bl std::string::assign(char const*)` ⇒ **`name` 落在条目 `+0x08`**。
//:
//: ⚠️ 上一版把本偏移写成 `0x00`（排除法推断），真机否掉了它 —— 这与布局表里那句
//: "名字若与 `music.xml` 里的 track 名对不上，就说明这条推断错了"完全一致。
//: **教训**：排除法给的"唯一自洽位置"也可能是别的东西（这里 `+0x00` 恰好是编号）；
//: 写侧**属性分派**那种直接证据（`strcmp(属性名)` → 目标槽）才是一锤定音的。
inline constexpr std::uintptr_t kMusicEntryNameStringOffset = 0x08;
//: 曲目表的形状保险（超过就当自己读错了，绝不硬走）：内置 119 条 + 模组追加的若干条，
//: 4096 是"不可能撞到、又不会把野指针当表"的量级。
inline constexpr std::size_t kMusicEntryMaximumCount = 4096;

// ---- 批次 265（2026-10-02）：音效表（`Isaac.GetSoundIdByName` 要遍历的那张表）------------------
//
// 与上面曲目表**同形**（同一个 `Manager`、同一种 `std::vector<T>`），只是子对象偏移、元素步长与
// 名字字段的位置不同。三条独立证据：
//
// ① **向量在 `SoundEffects + 0x00 / +0x08`**：`SoundEffects::Play(eSoundEffect, int, float, int,
//    float, float) @ 0x4A2FD0` 开头 `ldp x24, x8, [x19]`（x19 = this）⇒ begin/end 就在子对象
//    起点；`LoadConfig` 里也见 `str xzr, [x19, #0x10]`（capacity）。
// ② **元素步长 `0x1F0`**：① 的同一个函数紧跟着
//    `sub x8, x8, x24` / `lsr x8, x8, #4` / `mov w9,#0x7bdf` + `movk w9,#0xbdef,lsl#16` /
//    `mul w8, w8, w9` —— 那是"除以 496"的乘常数写法（`(x>>4) * 0xbdef7bdf >> 32` = `x / 0x1F0`）；
//    `LoadConfig` 里也有两处 `sub …, …, #0x1f0`（析构旧元素时回退一格）。
// ③ **名字在元素 `+0x1D8`**：`SoundEffects::LoadConfig @ 0x4A220C` 的属性分派
//    （`strcmp(属性名, "name")` → `bl std::string::assign(char const*)`，目标寄存器
//    `x0 = x25`，而 `0x4A2648 add x25, x26, #0x1d8`，x26 = 元素基址）⇒ 那是一个 libc++ `std::string`。
//    同一段里 `strcmp(属性名, "id")` → `atoi`，配对的槽是元素 `+0x1D4`（`0x4A2694 stp x25, x8` 就是
//    把 `+0x1D8`/`+0x1D4` 成对登记进属性表）。
//
// ★★ **"编号 == 元素下标"是引擎自己给的判据**（不是从 PC 文档推的）：② 那段算完 `count` 之后
//    紧跟着 `cmp w8, w22`（w22 就是第 1 个形参 `eSoundEffect`）—— 引擎**把 id 当下标用**去索引这张表。
//    ⇒ `GetSoundIdByName` 命中后返回**下标**与引擎一致。
//    （曲目表那边更硬的一条旁证可以对照：真机上表从 119 涨到 121 时，最后一条的 `+0x00` 读出来
//     正好等于它的下标 —— 见上面 `kMusicEntryIdOffset` 的注释。音效表的 `+0x1D4` 是同一种字段，
//     真机可用它交叉核对，见作业单第九节的 V10。）
inline constexpr uintptr_t kSoundEffectVectorBeginOffset = 0x00;  // vector<SoundEffect>.begin
inline constexpr uintptr_t kSoundEffectVectorEndOffset = 0x08;    //   …end
inline constexpr std::size_t kSoundEffectSize = 0x1F0;
inline constexpr std::uintptr_t kSoundEffectIdOffset = 0x1D4;         // int32（sounds.xml 没写 id ⇒ 由引擎填）
inline constexpr std::uintptr_t kSoundEffectNameStringOffset = 0x1D8;  // libc++ std::string
//: 形状保险（与 `kMusicEntryMaximumCount` 同一个理由）：内置音效几百条 + 模组追加的若干条，
//: 4096 是"不可能撞到、又不会把野指针当表"的量级。
inline constexpr std::size_t kSoundEffectMaximumCount = 4096;
inline constexpr std::uintptr_t kModManagerModListBeginOffset = 0x00;  // vector<ModEntry*>.begin
inline constexpr std::uintptr_t kModManagerModListEndOffset = 0x08;    //   …end
inline constexpr std::uintptr_t kModEntryEnabledFlagOffset = 0x139;    // ★ 引擎的模组启用位
//: ★ 紧挨着加载位的那一格（`ModEntry + 0x138`）= **引擎自己的"用户开着这个模组"开关**
//: （就是引擎自带模组页里那个复选框）。
//:
//: 三条互相印证的依据：
//: 1. `ListMods` 写这两格的分支（镜像 `0x420318`-`0x420340`）：
//:    ```
//:      <目录>/disable.it 存在 ⇒ +0x139 ← 0、+0x138 ← 0   （用户关了）
//:      不存在                ⇒ +0x139 ← *(Manager+0x36519)、+0x138 ← 1（用户开着）
//:    ```
//:    ⇒ `+0x139` = "本轮加载不加载" = `+0x138` 与**总闸**（`Manager+0x36519`）的合取。
//: 2. 引擎自带模组页 `Menu_Mods::Update` 按确认键翻的就是**这一格**：
//:    `*(unsigned char*)(条目 + 0x138) ^= 1`（本项目 2026-09-22 的反汇编记录，
//:    见 `mod_page_nav.hpp` 的 `ModPageToggleEnabled`）。
//: 3. `Menu_Mods::Render` 按这一格给行上色（为 0 走另一条颜色分支）——
//:    这正是"用户开关"该有的表现。
//:
//: 排队顺序上还有一个与批次 147 有关的含义：另一处 `strh wzr,[entry,#0x138]`
//: （`0x420434`）把两格一起清 0，那条路走的是"这个目录不算一个模组"。
//:
//: ⇒ 批次 147 的处置：**这一格为 0 就别去动 `+0x139`**（要么是用户关了、要么根本不是模组），
//: 与运行时 Lua 侧 `ModToggleService::ApplyToBatch` 认 `<目录>/disable.it` 的口径一致 ——
//: 否则会出现"内容进了引擎、脚本没加载"这种更难查的半截状态。
inline constexpr std::uintptr_t kModEntryUserEnabledFlagOffset = 0x138;
//: ★★ 引擎自己的"启用模组"**总开关**（`Manager` 上的一个字节；PC 的 ModsEnabled）。
//:
//: 依据（反汇编 `ModManager::ListMods`，镜像 `0x41FB0C`，批次 142）：
//: ```
//:   拼出 "<模组目录>/disable.it" → FileManager::Exists(...)
//:   存在      ⇒ ModEntry+0x139 = 0、+0x138 = 0
//:   不存在    ⇒ ModEntry+0x139 = *(Manager + 0x36519)、+0x138 = 1   ← 就是这一格
//: ```
//: 也就是说：**每条模组的启用位 = 跑 `ListMods` 那一刻这个字节的值**。项目里早就登记过它
//: （`mod_page_nav.hpp` 的 `kModsEnabledGateOn`、`mod_menu_native.cpp` 的
//: `kManagerModsEnabledOffset`，都写同一个 0x36519；`批次 058` 的真机读数就发现它是 0），
//: 我们的运行时也会把它置 1 —— 但那是**模组页/每帧**那条路，晚于引擎扫目录。
inline constexpr std::uintptr_t kManagerModsEnabledOffset = 0x36519;
inline constexpr std::size_t kEngineModListMaximumCount = 64;  // 形状保险：超过就当读错了

// ---- 批次 148（2026-09-26）：**我们自己把引擎那条"扫模组目录 + 加载 content"喊一次** --------
//
// 为什么非要我们喊：`ModManager::Reset` / `ListMods` / `LoadConfigs` 在 Switch 这版镜像里
// **零引用**（全镜像扫 `bl`/`b`/取地址三种形态，一条都没有 —— 批次 147/148 各扫过一次），
// 而 147 的入口中继真机证明"引擎从不调 `LoadConfigs`"（`g_ModLoadConfigsCalls = 0`）
// ⇒ 模组的 `content/*.xml`（皮肤 / 音乐）永远不会进引擎，跳舞模组的
// `Isaac.GetCostumeIdByPath` 必然查不到（真机：43 次查表 0 命中）。
//
// 参考实现（同 build-id 的 `repentance-plus-switch` 移植）的做法一致：**直接调这两个函数**，
// 不自造 id 表。它的 `g_ModdingDataPath` 写 `"mods/"`；我们的模组树在
// `rom:/isaac_mods/mods/`（标题覆盖层）⇒ 写 `"isaac_mods/mods/"`，拼出来的
// `<路径><目录>/content/` 正是我们磁盘上的布局。
inline constexpr uintptr_t kModManagerListModsFileOffset = 0x41FB0C;
inline constexpr std::array<u8, 16> kModManagerListModsExpectedBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFC, 0x6F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};
//: `IsaacRepentance::g_ModdingDataPath` —— `char[0x400]`（**不是指针**），文件偏移 `0xABBC04`。
//:
//: 依据（反汇编 `ListMods @ 0x41FB0C` + 同 build-id 的参考实现互证）：
//: ```
//: 0x41FBE0  adrp x0, 0xAAD000
//: 0x41FBE4  ldr  x0, [x0, #0x198]   ← GOT 槽 0xAAD198，装的是**数组地址**
//: 0x41FBE8  bl   strlen              ← 所以它被当 C 串用
//: ```
//: GOT 槽里放地址（而不是 `adrp`+`add` 直接算数组）说明数组**定义在别的编译单元**。
//: 同一函数里还把它第二遍当 `GetDirectoryEntries(cm, "", g_ModdingDataPath, &count)` 的第 3 个实参
//: ⇒ 它就是"模组目录根"，且**带结尾斜杠**时拼出来的路径才与磁盘一致。
//: 参考实现把它整段清零后写 `"mods/"`，并靠这一步让引擎真的列出模组 ⇒ 这里照做。
inline constexpr uintptr_t kModdingDataPathFileOffset = 0xABBC04;
inline constexpr std::size_t kModdingPathCapacity = 0x400;
//: 我们磁盘上的模组树（标题覆盖层 `rom:/isaac_mods/mods/`）在**应用根相对**口径下的写法。
//: 为什么不是 `rom:/...`：引擎的内容挂载解析只认"相对应用根"的输入 —— 这条项目自己实测过两次
//: （批次 085 的模组页名字、`test_font_resource_path_normalization.py` 的文件头）。
inline constexpr char kModdingDataPathValue[] = "isaac_mods/mods/";

// ---- 批次 148b（2026-09-26 深夜）：**绕开 `ListMods`，直接调两个 content 加载器** ------------
//
// 为什么放弃"调引擎的 `ListMods` + `LoadConfigs`"：真机崩溃报告
// （`dist/crash-148-20260926.log`，`Result 0x2F6202` / `Type: User Break`）给出
//   `ContentManager::get_directory_entries + 0x30` ← `IContentManager::GetDirectoryEntries`
//   ← `ModManager::ListMods + 0x50` ← `runtime` ← `run_repentance`
// 反汇编 `get_directory_entries`（`0x4CC928`）第 5 条指令就把它交给
// `nn::fs::OpenDirectory(&handle, <path>, 3)`、**返回码非 0 立即 abort**；而 `<path>` 是
// `CreateCleanPath(g_ModdingDataPath, "")` 的结果。这版镜像里 `g_ModdingDataPath`
// **永远是空串**（全镜像搜 `isaac_mods` / `mods/` / `romfs` 都是 0 命中 ⇒ 引擎自己从不初始化它）
// ⇒ **`ListMods` 在本版本里必然 abort**，与"什么时候调"无关（批次 143 那次也是它，
// 当时归因成"第一帧太早"是误判）。
//
// 改成直接调 `ModManager::LoadConfigs` 里用的那两个加载器 —— 它们**只开一个文件**、
// 用的是引擎自己的 `KAGE::Filesys::FileManager`（认"相对应用根"的路径，批次 085 验证过）：
//   * `ItemConfig::LoadCostumes(char const* file, ModEntry*)` @ `0x3B9448`
//     （`_ZN15IsaacRepentance10ItemConfig12LoadCostumesEPKcPNS_8ModEntryE`）：
//     `x1` 直接交给 `FileManager::OpenRead`；`OpenRead` 失败只走普通分支（`cbz x0`）**不 abort**；
//     入口 `cmp x2,#0` + `csel` ⇒ **`ModEntry` 传 `nullptr` 是它自己处理过的**。
//   * `Music::LoadConfig(char const* file, bool)` @ `0x425218`
//     （`_ZN15IsaacRepentance5Music10LoadConfigEPKcb`）：`LoadConfigs` 对模组传的第二个参数是
//     **`1`**（调用点 `mov w2, #0x1`）；`OpenRead` 失败同样走普通分支。
inline constexpr uintptr_t kItemConfigLoadCostumesFileOffset = 0x3B9448;
inline constexpr std::array<u8, 16> kItemConfigLoadCostumesExpectedBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFC, 0x6F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};
inline constexpr uintptr_t kMusicLoadConfigFileOffset = 0x425218;
inline constexpr std::array<u8, 16> kMusicLoadConfigExpectedBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFC, 0x6F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};
//: 模组 content 目录下、我们要喂给引擎的文件名。与 `ModManager::LoadConfigs` 里的字面量**逐字相同**
//: （反汇编 `0x41E388` 的调用点读到 `"costumes2.xml"` 与 `"music.xml"`）。
//: ★★ 开头那个 `/` **不能少**：模组根目录的写法是 `isaac_mods/mods/<目录>`（`kModdingDataPathValue`
//: 的结尾斜杠被目录名吃掉了）⇒ 少了它拼出来是 `...<目录>content/costumes2.xml`（目录名与 `content`
//: 粘在一起）。2026-09-26 真机就是这个错：挂载解析 8 条全失败（`path_misses = 8`）、
//: 两个加载器一次都没调、容器 132/119 一条没涨。引擎自己的写法是"content 路径（`<目录>/content/`，
//: 带结尾斜杠）+ 文件名"，我们这里等价地写成"模组根 + `/content/<文件名>`"。
inline constexpr char kModContentCostumesFile[] = "/content/costumes2.xml";
inline constexpr char kModContentMusicFile[] = "/content/music.xml";

// ---- 批次 152（2026-09-27 上午）：`LoadCostumes` 的第二个参数**不能传 `nullptr`** ----------
//
// 上一批（149b）真机读数：`LoadCostumes` 被调了 2 次、`null` 服装容器却 **132 → 132**（一条没涨）。
// 本轮把 `ItemConfig::LoadCostumes @ 0x3B9448` **全文读完**（962 行反汇编，`tools/nro_disasm.py`），
// 得到的结论如下 —— 每一句都能照地址复核：
//
// ## 1) 第二个参数（`x2` = `ModEntry*`）**只被用作"是不是空指针"**
//   * `0x3B9474 str x2,[sp,#0x48]` 把它存进栈；此后**只有三处**读它，且**全是 `cbz`**：
//     `0x3B9DA0`（trinket 分支）/ `0x3B9DF0`（passive·active·familiar 分支）/ `0x3B9E40`（none 分支）；
//   * 另外算出一个 `ctx = (x2 != 0) ? x2 + <本常量> : 0`（入口 `0x3B946C add x8,x2,#…` +
//     `0x3B9478 csel x8,xzr,x8,eq`），`ctx` **只在 trinket / passive·active·familiar 两条分支里**
//     被读（`0x3B9F64` / `0x3BA0F4`；另有 `0x3B9738` 只是把它拆成 `ctx+0x8` / `ctx+0x20` 两个
//     槽位、不访问内存）⇒ **`type="none"` 那条分支一次都不碰 `ctx`**。
//   * `ctx` 里其实是**两个 libc++ `std::map<int,int>` 的空树头部**（各 `0x18` 字节：
//     `+0x00 __begin_node_` / `+0x08 __end_node_.__left_` / `+0x10 size_`；第二个从 `ctx+0x18` 起）。
//     判据：`0x3BA010 ldr x0,[x9,#0x8]` 取的就是 `__end_node_.__left_`（libc++ 的 `__root()`），
//     紧接着 `bl __tree_balance_after_insert`，再 `ldr x8,[x19,#0x10]` + `add #1` 就是 `size_`。
//
// ## 2) 两条路的**语义差别**（这才是"没涨"的原因）
//   * 引擎自己的调用点有两处，`bl` 到同一个 PLT 桩（全镜像扫描：只有 `0x3F6010` 与 `0x41E694`）：
//     ① `0x3F5FFC-0x3F6010`（`Manager::LoadConfigs`，加载**本体**的 `resources/costumes2.xml`）
//        —— `mov x2, xzr`：**本体传的就是 `nullptr`**；
//     ② `0x41E694`（`ModManager::LoadConfigs @ 0x41E388`，加载**模组**的 content）
//        —— `ldr x2,[x21]`：传的是模组列表里那个**真 `ModEntry*`**。
//   * `nullptr`（本体那条路）：`[sp+0x88]` 保持 XML 里的 `id` 属性 ⇒ 把 `anm2root+anm2path`
//     写进**已经存在**的那一条（本体条目先由 `items.xml` / 内置表建好），容器**不涨**。
//   * 非空（模组那条路）：`type="none"` 时 `0x3B9E58 str w8,[sp,#0x88]` 把 `id` **覆盖成
//     "容器当前条数"**，`0x3B9E5C bl _Znwm` 造一条新条目、`0x3B9EE0 str x26,[x19],#0x8` +
//     `0x3B9EE4 str x19,[x27,#0x38]` 压进容器、`0x3B9FFC str w8,[x9,#0x4]` 写编号、
//     `0x3BA070 string::assign(item+0x88, anm2root+anm2path)` 写路径 ⇒ **容器涨**。
//     （`v27` 在这里 = `ItemConfig*`（函数入口 `mov x27,x0`），`+0x30/+0x38/+0x40` 就是
//      `NullItemBegin/End/Cap` —— 与 `kItemConfigNullItemBeginOffset` 同一个容器。）
//   * ⇒ 我们要的就是后一条：**传一个非空的指针**。
//
// ## 3) 为什么不做"造一个够用的 `ModEntry`"这件事的完整版
//   * `type="none"` 只用到"非空"这一个性质 ⇒ 传一块**只初始化了两个空 map**的替身就够；
//   * trinket / passive·active·familiar 那三条分支会读 `ctx` 的两个 map（`0x3B9F64` / `0x3BA0F4`），
//     所以替身的两个 map 必须**是合法的空树**（`__begin_node_ == &__end_node_`、`__left_ = 0`、
//     `size_ = 0`）—— 零填充**不行**：`0x3B9F78 ldr x8,[x8]` 会解引用 `__begin_node_`，
//     全 0 时就是解引用空指针。
//   * 引擎自己那条路传的是真 `ModEntry`（它那两张 map 是 `ModEntry` 自己的成员，`ModEntry` 构造时
//     默认构造 ⇒ 一开始也是空树）⇒ **替身与引擎的行为在这三条分支上一致**（都是空 map）。
//     未解的一点：那两张 map 会不会被别处（例如 `ModEntry::LoadCustomResources`）填成
//     非平凡映射 —— 本文只主张"本轮 `LoadCostumes` 里没有任何写非零值的地方"
//     （插入处 `0x3B9F60 stp w8,wzr,[x0,#0x1c]` = `{key=id, value=0}`）。
//
// ## 4) 「路径口径」与「本参数」是**两个独立的原因**，别混
//   * 149b 已定案：路径**必须去掉 `rom:/`**（真机：只有那样曲目表才 119 → 121）；
//   * 本批定案：参数**必须非空**（否则 `type="none"` 一条都不加）。
//
// 常量：替身里 `ctx` 相对 `ModEntry*` 的偏移（入口 `add x8,x2,#0x108`）。
inline constexpr uintptr_t kModEntryCostumeContextOffset = 0x108;
//: `ctx` 里两个 `std::map` 头部的总长（各 `0x18`：`__begin_node_` / `__end_node_.__left_` / `size_`）。
inline constexpr std::size_t kModEntryCostumeContextBytes = 0x30;
//: 替身整体要多大：`ctx` 结束（`+0x138`）就够 —— 引擎在这条路上**没有**读更大的偏移。
//: 留到 `+0x140` 只为了对齐好看，**不是**引擎的要求。
inline constexpr std::size_t kModEntrySubstituteBytes = 0x140;

// ---- 批次 378（2026-10-05）：把"逐模组喂 content"从 **2 项**补齐到引擎的 **16 项** ------------
//
// 由来：Switch 版引擎自己那条路（`ModManager::LoadConfigs @ 0x41E388`）在本版镜像里
// **从不执行**（批次 147/148 已定案：全镜像零引用；147 的入口中继真机读到 `LoadConfigs` 调用数 0）
// ⇒ "把每个模组的 `content/*.xml` 交给各加载器"这件事只能我们自己做。本批之前只喂 2 个
// （`costumes2.xml` / `music.xml`，批次 148~156 真机定案的那条路）；本批按引擎**逐条**补齐到 16 项
// （14 个文件 + `ModEntry::LoadCustomResources` + `EntityConfig::PostLoadMods`）。
//
// ## 依据（本批把 `ModManager::LoadConfigs` 全文重读了一遍：`python3 tools/nro_disasm.py 0x41e388 0x9b0`）
//
// 循环体（`x21` 在 `ModManager` 的 `vector<ModEntry*>` 上走，步长 8；`ModManager = Manager + 0x36800`）：
//   * `0x41E408 ldr x0,[x21]` → `0x41E40C ldrb w8,[x0,#0x139]` + `cbz`：**引擎自己的启用位**
//     为 0 就整段跳过（连 `LoadCustomResources` 都不调）⇒ 我们只喂 `ModMenuDiscoveredEnabled` 为真的；
//   * `0x41E414 bl ModEntry::LoadCustomResources` —— ★ **它排在 `entities2.xml` 之前**
//     （不是"最后一件事"）。本批照引擎把它放在每个模组的第一位；表里它是第 15 行，
//     行的编号按"读数位掩码"排（见下），**不等于调用顺序**；
//   * 之后 14 个文件，每个都是 `FileManager::Exists(路径)` → 存在才 `bl <加载器>`；
//     ★ 那条 `Exists` **闸我们不做**（加载器对"打不开"有自己的普通分支：`OpenRead` 返回空即返回、
//       `cbz` 不 abort）—— 本批的调用点因此会比引擎多几次"文件不存在"的空调用，代价是几次
//       文件系统查询，换掉的是"再解析一个引擎入口"；
//   * 循环**外**（`0x41ED24`-`0x41ED34`）：`x0 = Manager + 0x36758` → `EntityConfig::PostLoadMods()`
//     ⇒ **所有模组都喂完之后调一次**（不是每个模组一次）。
//
// ## Manager 的三个子对象偏移（接收者 `x0`）—— 逐条都是从上面的调用点读出来的立即数
//
//   * `0x41E480 mov w9,#0x6758` + `0x41E484 movk w9,#0x3,lsl#16` + `add x0,x8,x9`
//     → `EntityConfig::Load`；`0x41EAE8`/`0x41EAEC` 同一对立即数 → `EntityConfig::LoadPlayers`
//     ⇒ **`Manager + 0x36758`**（与"`ModManager` 在 `+0x36800`"只差 `0xA8`，同区间、互为旁证）；
//   * `0x41EA58 ldr x0,[x22]`（`x22` = `g_Manager` 槽的地址 ⇒ `x0 = *槽` = **Manager 本体**，
//     **不加任何偏移**）→ `Manager::LoadChallenges`。★ 这一条最容易写错成"某个子对象"；
//   * `0x41EB94` 的 `#0x64a8` + `#0x3,lsl#16` ⇒ `Manager + 0x364A8` → `SoundEffects::LoadConfig`
//     （同一个数本文件批次 185 已登记为 `kManagerSoundEffectsOffset`，这里**不重复定义**）；
//   * `0x41EC40` 的 `#0x6068` + `#0x3,lsl#16` ⇒ `Manager + 0x36068` → `Music::LoadConfig`
//     （= 已有的 `kManagerMusicOffset`）；
//   * `0x41ECF0 mov w9,#0xcbb8` + `0x41ECF4 movk w9,#0x2,lsl#16` ⇒ `Manager + 0x2CBB8`
//     → `NightmareScene::LoadConfig`（这一条**只有两个参数**：`x0`/`x1`，没有 `w2`）。
inline constexpr uintptr_t kManagerEntityConfigOffset = 0x36758;
inline constexpr uintptr_t kManagerNightmareSceneOffset = 0x2CBB8;

//: 14 个内容加载器的**共同 16 字节序言** —— 本批逐条比对过：这 14 条入口的这 16 字节**完全相同**
//: （`FD 7B BA A9 FC 6F 01 A9 FD 03 00 91 FA 67 02 A9`，全部按**内存字节序**写）。
//: ★★ 因此序言守卫**认不出谁是谁**：`ItemConfig::Load` 与 `LoadCostumes` 连 `sub sp,sp,#0x160`
//:   都一样（那是第 5 条指令、在 16 字节之外）⇒ 偏移写串了会被**静默放过**（换成另一个加载器
//:   = 喂错容器、不报错不崩）。所以每个加载器都必须在下面登记自己的**判别式**（4 字节 + 偏移），
//:   两道理一起过才算解析成功。这与"按钮查询靠 `entry+0xE0` 的虚表槽区分"（批次 210）是同一类坑。
inline constexpr std::array<u8, 16> kModContentLoaderExpectedBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFC, 0x6F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};
//: `ModEntry::LoadCustomResources()` 的序言（表里第 15 行；与本文件重载无关的那个 `ModEntry` 同名）。
//: 16 字节里第 8 个字节（`04` vs `05`）就与 `PostLoadMods` 分得开，但**仍然**按 16 字节比满。
inline constexpr std::array<u8, 16> kModEntryLoadCustomResourcesExpectedBytes = {
    0xFF, 0x83, 0x02, 0xD1, 0xFD, 0x7B, 0x04, 0xA9,
    0xFD, 0x03, 0x01, 0x91, 0xFC, 0x6F, 0x05, 0xA9,
};
//: `EntityConfig::PostLoadMods()` 的序言（表里第 16 行）。★ 这 16 字节本身就唯一，不需要判别式。
inline constexpr std::array<u8, 16> kEntityConfigPostLoadModsExpectedBytes = {
    0xFF, 0x83, 0x02, 0xD1, 0xFD, 0x7B, 0x05, 0xA9,
    0xFD, 0x43, 0x01, 0x91, 0xF9, 0x33, 0x00, 0xF9,
};

//: "喂进来的这一项"的接收者（`x0` 从哪来）。取值就是 `.cpp` 里那个 `switch` 的分支号。
enum class ModContentFeedReceiver : std::uint32_t {
    ItemConfig = 0,      //: `Manager + kManagerItemConfigOffset`
    EntityConfig = 1,    //: `Manager + kManagerEntityConfigOffset`
    ManagerItself = 2,   //: **`Manager` 本体**（不加偏移 —— `Manager::LoadChallenges`）
    SoundEffects = 3,    //: `Manager + kManagerSoundEffectsOffset`
    Music = 4,           //: `Manager + kManagerMusicOffset`
    NightmareScene = 5,  //: `Manager + kManagerNightmareSceneOffset`
    ModEntryItself = 6,  //: `x0` = 这个模组的 `ModEntry*` 自己（`LoadCustomResources`）
};

//: 第三个参数（`x2` / `w2`）的形状 —— 引擎对模组传的值逐条照抄，不自己推。
enum class ModContentFeedArgument : std::uint32_t {
    ModEntry = 0,  //: `x2 = ModEntry*`（`ItemConfig::Load` / `LoadCostumes` / `EntityConfig::Load` …）
    BoolTrue = 1,  //: `w2 = 1`（`LoadChallenges` / `SoundEffects::LoadConfig` / `Music::LoadConfig` …）
    None = 2,      //: 没有第三个参数（`NightmareScene::LoadConfig` 只收路径）
};

//: 一条"喂给引擎"的登记项。**字段顺序即初始化顺序**（本文件其他地方的常量都给守卫单独立名，
//: 这里把 16 条收进一张表，是因为它们**必须保持引擎的调用次序**、且每条都要带判别式 ——
//: 拆成 16 组散装常量反而更容易把行序与判别式对错）。
//:
//: `expected` / `expectedSize`：入口 16 字节守卫（14 条相同，另两条各自不同，见上面三个常量）。
//: `discriminatorOffset` / `discriminator`：第二道守卫（4 字节按内存字节序）；两者任一为空
//: 表示"本条的序言已唯一、不需要第二道"。
//: `fileName`：`content/` 下的文件名；`nullptr` = 这一条不是"content 下的文件"（整批项）。
//: ★ 表里 `costumes2.xml`/`music.xml` 两行**参与入口解析与位掩码**，但**喂的动作**由
//:   `.cpp` 里那条批次 148~156 定案的专用路负责（它要"两种路径口径 + 容器涨没涨"的取证）——
//:   否则同一条 `costumes2.xml` 会被喂两遍（引擎只喂一遍，重复会把 23 条服装加两遍）。
struct ModContentFeedSpec {
    std::uintptr_t functionOffset;
    const u8* expected;
    std::size_t expectedSize;
    std::uintptr_t discriminatorOffset;
    std::array<u8, 4> discriminator;
    const char* fileName;
    ModContentFeedReceiver receiver;
    ModContentFeedArgument argument;
};

//: 判别式的长度（4 字节；与本文件 `kKageIsButtonPressedDiscriminator` 同一口径）。
inline constexpr std::size_t kModContentFeedDiscriminatorBytes = 4;

//: **引擎 `LoadConfigs` 循环体的 16 项**，行号 = `modEngineLoadersResolved` 的位号。
//: 判别式逐字节取自镜像（本批用 `nro_disasm.py` 复核过；写成内存字节序，别照抄反汇编里的
//: `mov`/指令字顺序 —— 批次 210 在按钮那边就是因为写反了而真机哑了一整轮）。
//: 行序 = 界面表里的行序（14 个文件按引擎调用次序，然后 `LoadCustomResources`、`PostLoadMods`）；
//: ★ **调用顺序**与行序有一处不同：`LoadCustomResources` 引擎是每个模组**第一个**调的。
inline constexpr std::array<ModContentFeedSpec, 16> kModContentFeedSpecs = {{
    // 0 entities2.xml —— `EntityConfig::Load(char const*, ModEntry*)` @ 0x68860
    {0x68860, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0xC3, 0x0D, 0xD1}, "entities2.xml", ModContentFeedReceiver::EntityConfig,
     ModContentFeedArgument::ModEntry},
    // 1 items.xml —— `ItemConfig::Load` @ 0x3B50E0（判别式必须取 +0x2C：+0x20 与 `LoadCostumes` 相同）
    {0x3B50E0, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x2C,
     {0xE2, 0x2F, 0x00, 0xF9}, "items.xml", ModContentFeedReceiver::ItemConfig,
     ModContentFeedArgument::ModEntry},
    // 2 pocketitems.xml —— `ItemConfig::LoadPocketItems` @ 0x3BE42C
    {0x3BE42C, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x03, 0x06, 0xD1}, "pocketitems.xml", ModContentFeedReceiver::ItemConfig,
     ModContentFeedArgument::ModEntry},
    // 3 costumes2.xml —— `ItemConfig::LoadCostumes` @ 0x3B9448（喂的动作在专用路上，见结构体注释）
    {0x3B9448, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x2C,
     {0xE2, 0x27, 0x00, 0xF9}, "costumes2.xml", ModContentFeedReceiver::ItemConfig,
     ModContentFeedArgument::ModEntry},
    // 4 items_metadata.xml —— `ItemConfig::LoadMetadata` @ 0x3BA2F4（判据取 +0x24：+0x20 与 recipes 相同）
    {0x3BA2F4, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x24,
     {0xF8, 0x03, 0x00, 0xAA}, "items_metadata.xml", ModContentFeedReceiver::ItemConfig,
     ModContentFeedArgument::ModEntry},
    // 5 wisps.xml —— `ItemConfig::LoadWispConfig` @ 0x3BA984
    {0x3BA984, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x03, 0x0B, 0xD1}, "wisps.xml", ModContentFeedReceiver::ItemConfig,
     ModContentFeedArgument::ModEntry},
    // 6 locusts.xml —— `ItemConfig::LoadLocustConfig` @ 0x3BC43C
    {0x3BC43C, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x03, 0x0A, 0xD1}, "locusts.xml", ModContentFeedReceiver::ItemConfig,
     ModContentFeedArgument::ModEntry},
    // 7 recipes.xml —— `ItemConfig::LoadCraftingRecipes` @ 0x3BDB68
    {0x3BDB68, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x24,
     {0xE8, 0x37, 0x00, 0xF0}, "recipes.xml", ModContentFeedReceiver::ItemConfig,
     ModContentFeedArgument::ModEntry},
    // 8 bombcostumes.xml —— `ItemConfig::LoadBombCostumeRules(char const*, bool)` @ 0x3BF790
    //    ★ 这一条**没有 ModEntry**（第三个参数是 `bool`，引擎调用点传 1）。
    {0x3BF790, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x43, 0x09, 0xD1}, "bombcostumes.xml", ModContentFeedReceiver::ItemConfig,
     ModContentFeedArgument::BoolTrue},
    // 9 challenges.xml —— `Manager::LoadChallenges(char const*, bool)` @ 0x3F6C90
    //    ★ 接收者是 **Manager 本体**（`0x41EA58 ldr x0,[x22]`，不加偏移）。
    {0x3F6C90, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x83, 0x08, 0xD1}, "challenges.xml", ModContentFeedReceiver::ManagerItself,
     ModContentFeedArgument::BoolTrue},
    // 10 players.xml —— `EntityConfig::LoadPlayers` @ 0x6DC54
    {0x6DC54, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x03, 0x0E, 0xD1}, "players.xml", ModContentFeedReceiver::EntityConfig,
     ModContentFeedArgument::ModEntry},
    // 11 sounds.xml —— `SoundEffects::LoadConfig(char const*, bool)` @ 0x4A220C
    {0x4A220C, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x03, 0x17, 0xD1}, "sounds.xml", ModContentFeedReceiver::SoundEffects,
     ModContentFeedArgument::BoolTrue},
    // 12 music.xml —— `Music::LoadConfig(char const*, bool)` @ 0x425218（与上面同一条专用路）
    {0x425218, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x43, 0x08, 0xD1}, "music.xml", ModContentFeedReceiver::Music,
     ModContentFeedArgument::BoolTrue},
    // 13 nightmares.xml —— `NightmareScene::LoadConfig(char const*)` @ 0x427ECC（**没有第三个参数**）
    {0x427ECC, kModContentLoaderExpectedBytes.data(), kModContentLoaderExpectedBytes.size(), 0x20,
     {0xFF, 0x83, 0x04, 0xD1}, "nightmares.xml", ModContentFeedReceiver::NightmareScene,
     ModContentFeedArgument::None},
    // 14 `ModEntry::LoadCustomResources()` @ 0x41EDB0 —— `void()`（this 在 x0），每个模组**第一个**调
    {0x41EDB0, kModEntryLoadCustomResourcesExpectedBytes.data(),
     kModEntryLoadCustomResourcesExpectedBytes.size(), 0x20, {0xE8, 0x43, 0x00, 0x91}, nullptr,
     ModContentFeedReceiver::ModEntryItself, ModContentFeedArgument::None},
    // 15 `EntityConfig::PostLoadMods()` @ 0x71914 —— `void()`（this 在 x0），**所有模组喂完之后调一次**
    {0x71914, kEntityConfigPostLoadModsExpectedBytes.data(),
     kEntityConfigPostLoadModsExpectedBytes.size(), 0, {0x00, 0x00, 0x00, 0x00}, nullptr,
     ModContentFeedReceiver::EntityConfig, ModContentFeedArgument::None},
}};

//: 表里那两行的行号（`.cpp` 用它们把"喂的动作"路由到专用路 / 得到 `PostLoadMods` 的地址）。
inline constexpr std::size_t kModFeedRowCostumes = 3;
inline constexpr std::size_t kModFeedRowMusic = 12;
inline constexpr std::size_t kModFeedRowCustomResources = 14;
inline constexpr std::size_t kModFeedRowPostLoadMods = 15;
//: 14 个"content 下的文件"就排在表的前 14 行。
inline constexpr std::size_t kModFeedContentRows = 14;
//: `Manager` 子对象之间的路径段（拼路径用；与已有的 `kModContentCostumesFile` 同一形状）。
inline constexpr char kModContentDirectoryPrefix[] = "/content/";

// ---- 批次 378：**真 `ModEntry`**（`LoadCustomResources` 会往它里面写 ANM2） -------------------
//
// ★★★ 为什么必须用引擎自己的构造器造真条目（本批最关键的一条）：
//   `ModEntry::LoadCustomResources()` 会写 `ModEntry + 0x140` 起的 **13 个内嵌 `ANM2`**
//   （步长 `0x158`：`+0x140`、`+0x298` … 最后一个在 `+0x1160`），而 `sizeof(ModEntry) = 0x12B8`
//   （判据见下面 `kModEntryCtorFileOffset` 的注释）。本批之前那个替身
//   （`SubstituteModEntry`，只有 `0x140` 字节）一旦被喂进 `LoadCustomResources` 就是**越界写**
//   —— 它会一路写穿到别的 bss 变量上。所以本批改成"引擎构造器造真条目"，替身只留给
//   批次 152 定案的那条 `LoadCostumes` 专用路（那条路只用"非空"这一个性质）。
//
//   `ModEntry::ctor @ 0x420D18`（本批逐条读过，`nro_disasm.py 0x420d18 0x100`）：
//     * 入口 16 字节：`FD 7B BE A9 F3 0B 00 F9 FD 03 00 91 08 C0 03 91`；
//     * `0x420D54 stp x8, xzr, [x0, #0xf8]`（x8 = `this+0xf0`）→ `+0xf8 = this+0xf0`、`+0x100 = 0`；
//     * `0x420D58 add x8, x0, #0x110` + `0x420D5C stp x8, xzr, [x0, #0x108]`
//       → **`+0x108` = `this+0x110`**、`+0x110 = 0`；
//     * `0x420D60 add x8, x0, #0x128` + `0x420D64 stp xzr, x8, [x0, #0x118]`
//       → `+0x118 = 0`、**`+0x120` = `this+0x128`**；
//     * `0x420D7C stp xzr, xzr, [x0, #0x128]` → `+0x128 = 0`、`+0x130 = 0`。
//     ⇒ 这就是 libc++ `std::map`（`__tree`）的**空树头部**：`__begin_node_`（指向 `&__end_node_`）
//       / `__end_node_.__left_`（0）/ `size_`（0），两张 map 各 `0x18` 字节，分别在 `+0x108` /
//       `+0x120` —— 与批次 152 里 `LoadCostumes` 的 `ctx = ModEntry + 0x108` 完全对上。
//       **结论：构造器确实把这两张 map 初始化好了，构造之后不需要我们再补
//       `MakeEmptyCostumeTree`**（本批核对的就是这一条）。
//     * `0x420D80` 起对 `+0x140` 起的 13 个 `ANM2` 逐个 `bl ANM2::ANM2()`（那条 import 桩
//       `0x66FB00`）⇒ 步长 `0x158`、末尾 `+0x1160`，所以 `sizeof(ModEntry) = 0x1160 + 0x158 = 0x12B8`。
//     * `0x420D68 mov w8,#0x101` + `0x420D6C strh w8,[x0,#0x138]` ⇒ `+0x138 = 1`、`+0x139 = 1`
//       （引擎那两格"用户开关 / 本轮启用位"）。**与我们无关**：这些条目**不进**引擎的模组表，
//       只当 `ModEntry*` 参数用。
inline constexpr std::uintptr_t kModEntryCtorFileOffset = 0x420D18;
inline constexpr std::array<u8, 16> kModEntryCtorExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0xC0, 0x03, 0x91,
};
//: `sizeof(ModEntry)` —— 由构造器最后那个 `ANM2` 的偏移与步长算出来（`0x1160 + 0x158`）。
inline constexpr std::size_t kModEntryBytes = 0x12B8;
//: 竞技场里每个条目占的**步长**。`0x12B8` 不是 16 的倍数（`0x12B8 % 16 == 8`），而引擎自己
//: 是用 `new` 拿的条目（aarch64 上 16 字节对齐）⇒ 步长取 `0x12C0`，保证**每个下标都 16 字节对齐**
//: （里面的 `ANM2` 有 8 字节成员，按 8 对齐其实也够，但没必要赌）。
inline constexpr std::size_t kRealModEntryStride = 0x12C0;
//: 竞技场容量 = 引擎允许的模组上限（`ModManifest::kMaximumSelectedMods = 32`，
//: `runtime/source/mod_manifest.hpp:25`）。32 × 0x12C0 = 153,600 字节 ≈ 150 KiB —— 本模块的
//: bss 有 130 MB 级余量（`HeapSize` 已是 128 MiB），不差这点；而**取小了**的后果是
//: "第 N 个之后的模组的 content 永远喂不进去"（静默、只在读数里看得出），不能取小。
inline constexpr std::size_t kMaximumRealModEntries = 256;

// ---- 批次 378：真 `ModEntry` 的**内容目录成员**（`LoadCustomResources` 靠它才找得到文件）-----
//
// ★★ 本批最关键的一条静态发现（它决定 `LoadCustomResources` 到底有没有用）：
//   `ModEntry::GetContentPath @ 0x41EF10`（`LoadCustomResources` 每加载一个 ANM2 都要调它一次）
//   读的是 **`ModEntry + 0x48`** 那个 `std::string`：
//     * `0x41EF3C ldrb w8,[x23,#0x48]!`（`x23` = this ⇒ 串头在 `+0x48`）；
//     * `0x41EF54 sub x3,x8,#1`（砍掉最后一个字符）+ `0x41EF70` 取字面量 `0x891854 = "-dlc3/"`
//       + `0x41EF78 bl assign` ⇒ 先试 `<base>-dlc3/<名>`，`0x41F088 bl FileManager::Exists`；
//     * 不存在时**回落**：`0x41F0B8` 重新按 `+0x48` 取串 ⇒ `<base><名>`，再 `Exists`（`0x41F41C`）。
//   ⇒ `+0x48` 必须是我们已经拼好的 **`isaac_mods/mods/<目录>/content/`**（**带结尾 `/`**：
//     函数第一件事就是把最后一个字符砍掉再接 `-dlc3/`）。
//   **不填它 = 等于没喂**：空串会变成 `-dlc3/<名>` 与 `<名>`，两个 `Exists` 都假 ⇒
//   `LoadCustomResources` 逐个 ANM2 直接跳过 —— 不报错、不崩，只是"模组自己的资源永远不进引擎"。
//
// ★★ 另一个成员 `+0x60` **也一起填**（同一条串），理由是本版镜像里"写"和"读"用的不是同一个成员：
//   `ModManager::ListMods` 建条目时（`0x41FCF8` 起）把
//   `g_ModdingSaveDataPath + <目录> + "/content/"`（`0x88E18C` 那个字面量 `/content/`）存进的是
//   **`+0x60`**：`0x41FFA8`-`0x420018` 先 `operator+(char const*, string const&)`、再
//   `append("/content/")`，最后把整串搬进 `[x23,#0x60]`（搬之前还按 `ldrb w8,[x23,#0x60]`
//   释放旧串 ⇒ 确认 `+0x60` 就是个 `std::string`）。
//   ⇒ 本版引擎自己那条 `LoadConfigs` 因此**读不到内容**（写 `+0x60`、读 `+0x48`）——
//     这是"PC 能、Switch 不能"的一条具体机制，也是本批必须自己填的原因。
//   两个都填成同一个串：谁读都对；而且我们的条目**不进**引擎的模组表（`Manager+0x36800`），
//   不会影响别的代码。
inline constexpr uintptr_t kModEntryContentPathOffset = 0x48;
inline constexpr uintptr_t kModEntryContentDirectoryOffset = 0x60;

//: `std::string::assign(const char*)` 的 **PLT 桩**（`0x66FB80`）—— 把上面那两个成员填成
//: `isaac_mods/mods/<目录>/content/` 用它。
//:
//: 为什么**不自己写**那 24 字节：libc++ 的 `std::string` 有 SSO / 长串两套布局，长串还要用
//: 它自己的分配器分配（之后引擎释放时用的是**同一个** `_ZdlPv`）。自己写布局 = 把 libc++
//: 的内部约定抄一份，抄错就是堆破坏（最难查的一类）。让 libc++ 自己 `assign` 就没有这个问题。
//:
//: ★ 这个符号**不在本模块里**：`python3 tools/nro_callers.py --list-stubs assignEPKc --substring`
//:   报 `stub=0x66fb80 slot=0xa9dd28 target=0x0`（`target=0` = 动态链接进来的，本模块没有它的实现）
//:   ⇒ 不能像别的入口那样核对"函数序言"。改核对**桩本身**：这 16 字节里编码了
//:   `adrp x16,0xa9d000` + `ldr x17,[x16,#0xd28]`，合起来正是 `0xA9DD28` 那个
//:   `R_AARCH64_JUMP_SLOT` —— 也就是 `assign` 的槽。逐字节相等 ⇒ 这条桩确实通往 `assign`。
//:   引擎自己就是这么调的（`0x41FEB4`、`0x42007C`、`0x41FF2C`、`0x4208CC` 四处 `bl 0x66fb80`）。
inline constexpr uintptr_t kModEntryStringAssignFileOffset = 0x66FB80;
inline constexpr std::array<u8, 16> kModEntryStringAssignExpectedBytes = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0x96, 0x46, 0xF9,
    0x10, 0xA2, 0x34, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
//: `ModEntry::ctor` 解析失败占的位（`modEngineLoaderFailures` 的 bit16 —— 它不在那 16 行表里）。
inline constexpr std::uint32_t kModFeedConstructorFailureBit = 1U << 16;
//: `std::string::assign` 桩解析失败占的位（同上的 bit17 —— 它也不在那 16 行表里）。
inline constexpr std::uint32_t kModFeedStringAssignFailureBit = 1U << 17;

inline constexpr uintptr_t kMusicGetCurrentMusicIdOffset = 0x426C38;
inline constexpr std::array<u8, 16> kMusicGetCurrentMusicIdExpectedBytes = {
    0x00, 0xC8, 0x43, 0xB9, 0xC0, 0x03, 0x5F, 0xD6,
    0xE8, 0x03, 0x00, 0xAA, 0x00, 0xCC, 0x43, 0xB9,
};
inline constexpr uintptr_t kMusicPauseOffset = 0x42764C;
inline constexpr std::array<u8, 16> kMusicPauseExpectedBytes = {
    0x08, 0x00, 0x80, 0xB9, 0x09, 0x3C, 0x80, 0x52,
    0x08, 0x01, 0x09, 0x9B, 0x00, 0x21, 0x00, 0x91,
};
inline constexpr uintptr_t kMusicResumeOffset = 0x427660;
inline constexpr std::array<u8, 16> kMusicResumeExpectedBytes = {
    0x08, 0x00, 0x80, 0xB9, 0x09, 0x3C, 0x80, 0x52,
    0x08, 0x01, 0x09, 0x9B, 0x00, 0x21, 0x00, 0x91,
};
// 批次 137（2026-09-26）：`MusicManager:UpdateVolume()` —— `Music::UpdateVolume()` @ `0x427908`
// （符号 `_ZN15IsaacRepentance5Music12UpdateVolumeEv`）。The Specialist for Good Items 的
// "捡到四级物品放歌"那条路在一次 `PlayMusic`/音量调整之后会调它（把音量重新同步到选项菜单的设置）。
// 缺它就是 "attempt to call a nil value (method 'UpdateVolume')"。
// 入口 16 字节守卫（取自固定 NRO 的 `nro_symbols` 偏移 + 文件首字节）：`283400b0082543f90b0080b90c3c8052`。
inline constexpr uintptr_t kMusicUpdateVolumeOffset = 0x427908;
inline constexpr std::array<u8, 16> kMusicUpdateVolumeExpectedBytes = {
    0x28, 0x34, 0x00, 0xB0, 0x08, 0x25, 0x43, 0xF9,
    0x0B, 0x00, 0x80, 0xB9, 0x0C, 0x3C, 0x80, 0x52,
};
// 批次 138（2026-09-26）：`MusicManager:Play(eMusic ID, float Volume = 1)` —— The Specialist
// for Good Items 的"捡到四级物品放歌"**主路径**（`main.lua:483/489/494` 写的是
// `MusicManager():Play(id, 1)`）。缺它就是 "attempt to call a nil value (method 'Play')"，
// 而那几句在 `MC_POST_UPDATE` 回调里 ⇒ 整条回调被摘掉（用户看到的就是"捡到四级物品什么也没发生"）。
//
// 底座 `IsaacRepentance::Music::Play(IsaacRepentance::eMusic, float)` @ `0x427238`
// （符号/偏移/入口指纹 16 字节都取自 `analysis/lua-api-inventory/inventory.json` 的同名条目）。
// ★ 与**同址的** `kStage48MusicPlayOffset` 是**同一个函数** —— 那条是阶段 48 诊断包的转发靶点，
// 本常量是给**对外 API 自己**的：阶段清理那一轮删诊断常量时，不会连带把这条 API 的出处删掉。
// 参数形状（`this` + `eMusic` + `float`）与 PC 文档 `tools/pc_contract_docs/MusicManager.md:102`
// 的 `void Play ( Music ID, float Volume = 1 )` 逐字对应；第二个参数省缺时我们传 `1.0f`（PC 的默认值）。
inline constexpr uintptr_t kMusicPlayOffset = 0x427238;
inline constexpr std::array<u8, 16> kMusicPlayExpectedBytes = {
    0xE8, 0x0F, 0x1C, 0xFC, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
inline constexpr uintptr_t kRngSetSeedOffset = 0x44E3C0;
inline constexpr std::array<u8, 16> kRngSetSeedExpectedBytes = {
    0x01, 0x00, 0x00, 0xB9, 0xE8, 0x32, 0x00, 0xF0,
    0x08, 0x65, 0x41, 0xF9, 0x89, 0x01, 0x80, 0x52,
};
inline constexpr uintptr_t kRngNextOffset = 0x44E464;
inline constexpr std::array<u8, 16> kRngNextExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x00, 0x40, 0xB9,
};
// 批次 195（2026-09-29）：`RNG:RandomInt(Max)` / `RNG:RandomFloat()` 的引擎入口
// （来源：`analysis/api-restore-rng/README.md` 的 PLT 桩表 —— `RNG::Random(uint)` 桩 `0x66FE30`、
// `RNG::Random()` 桩 `0x66FEA0`；这里登记的是**真入口**，与既有的 `kRngSetSeedOffset`/`kRngNextOffset`
// 同一口径）。
//   * `RNG::Random(unsigned Max)` —— 引擎自己在 `Entity_Player::UsePill` 里
//     `0x2DFD04 mov w1,#0x32` + `0x2DFD08 bl 0x66FE30`（= `_pillRNGs[id].Random(50)`）、
//     在 `UseCard` 里 `mov w1,#0x61` + `bl 0x66FE30`（= `.Random(97)`）⇒ 它返回 `uint`，且**会推进**
//     这颗 RNG（`RNG.md:124-127` 的 "Since this mutates the RNG object"）；
//   * `RNG::Random()` —— 返回 `float`（`RNG.md:101-104` 同句）。
// ⚠️ 两条入口的前 16 字节与 `kRngNextOffset` 的**第 4..7 字节不同**，所以 16 字节指纹分得开
//    `Random(uint)` 与 `Next()`；但 `Random()` 与 `Next()` 的前 16 字节**逐字节相同**
//    （`FD 7B BE A9 F3 0B 00 F9 FD 03 00 91 08 00 40 B9`）⇒ 指纹只能证明"模块基址对"，
//    分不出这两条；偏移本身由上面的 PLT 桩表独立核对（桩→GOT 槽→真入口）。
inline constexpr uintptr_t kRngRandomUintOffset = 0x44E3E8;
inline constexpr std::array<u8, 16> kRngRandomUintExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x00, 0x40, 0xB9,
};
inline constexpr uintptr_t kRngRandomOffset = 0x44E4C0;
inline constexpr std::array<u8, 16> kRngRandomExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x00, 0x40, 0xB9,
};
inline constexpr uintptr_t kStage48MusicPlayOffset = 0x427238;
inline constexpr std::array<u8, 16> kStage48MusicPlayExpectedBytes = {
    0xE8, 0x0F, 0x1C, 0xFC, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
inline constexpr uintptr_t kStage48SoundActorPlayOffset = 0x517CF4;
inline constexpr std::array<u8, 16> kStage48SoundActorPlayExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
inline constexpr uintptr_t kStage48SoundActorPauseOffset = 0x517D2C;
inline constexpr std::array<u8, 16> kStage48SoundActorPauseExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
inline constexpr uintptr_t kStage48MusicPlayRelayCodeOffset = 0x68CD40;
inline constexpr uintptr_t kStage48MusicPlayRelaySlotOffset = 0x68CD78;
inline constexpr uintptr_t kStage48SoundActorPlayRelayCodeOffset = 0x68CD80;
inline constexpr uintptr_t kStage48SoundActorPlayRelaySlotOffset = 0x68CDB0;
inline constexpr uintptr_t kStage48SoundActorPauseRelayCodeOffset = 0x68CDC0;
inline constexpr uintptr_t kStage48SoundActorPauseRelaySlotOffset = 0x68CDF0;
inline constexpr std::array<u8, 4> kStage48MusicPlayRelayExpectedEntry = {
    0xC2, 0x96, 0x09, 0x14,
};
inline constexpr std::array<u8, 4> kStage48SoundActorPlayRelayExpectedEntry = {
    0x23, 0xD4, 0x05, 0x14,
};
inline constexpr std::array<u8, 4> kStage48SoundActorPauseRelayExpectedEntry = {
    0x25, 0xD4, 0x05, 0x14,
};
inline constexpr std::array<u8, 64> kStage48MusicPlayRelayExpectedBytes = {
    0xE8,0x0F,0x1C,0xFC,0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,
    0xFE,0x0B,0x00,0xF9,0xE0,0x1B,0x00,0xBD,0x31,0x01,0x00,0x10,
    0x30,0xFE,0xDF,0xC8,0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,
    0xE0,0x07,0x40,0xA9,0xFE,0x0B,0x40,0xF9,0xE0,0x1B,0x40,0xBD,
    0xFF,0x83,0x00,0x91,0x32,0x69,0xF6,0x17,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,
};
inline constexpr std::array<u8, 48> kStage48SoundActorPlayRelayExpectedBytes = {
    0xFD,0x7B,0xBE,0xA9,0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,
    0x31,0x01,0x00,0x10,0x30,0xFE,0xDF,0xC8,0x50,0x00,0x00,0xB4,
    0x00,0x02,0x3F,0xD6,0xE0,0x07,0x40,0xA9,0xFF,0x83,0x00,0x91,
    0xD5,0x2B,0xFA,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr std::array<u8, 48> kStage48SoundActorPauseRelayExpectedBytes = {
    0xFD,0x7B,0xBE,0xA9,0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,
    0x31,0x01,0x00,0x10,0x30,0xFE,0xDF,0xC8,0x50,0x00,0x00,0xB4,
    0x00,0x02,0x3F,0xD6,0xE0,0x07,0x40,0xA9,0xFF,0x83,0x00,0x91,
    0xD3,0x2B,0xFA,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr uintptr_t kPreGetCollectibleRelayOffset = 0x3C6350;
inline constexpr std::array<u8, 16> kPreGetCollectibleRelayExpectedOriginal = {
    0xFF, 0x03, 0x04, 0xD1, 0xE8, 0x4B, 0x00, 0xFD,
    0xFD, 0x7B, 0x0A, 0xA9, 0xFD, 0x83, 0x02, 0x91,
};
inline constexpr uintptr_t kPreGetCollectibleRelayCodeOffset = 0x68CE00;
inline constexpr uintptr_t kPreGetCollectibleRelaySlotOffset = 0x68CE58;
inline constexpr std::array<u8, 4> kPreGetCollectibleRelayExpectedEntry = {
    0xAC, 0x1A, 0x0B, 0x14,
};
inline constexpr std::array<u8, 96> kPreGetCollectibleRelayExpectedBytes = {
    0xFF,0x03,0x04,0xD1,0xFF,0x03,0x01,0xD1,0xE0,0x07,0x00,0xA9,
    0xE2,0x0F,0x01,0xA9,0xE4,0x13,0x00,0xF9,0xFE,0x17,0x00,0xF9,
    0x11,0x02,0x00,0x10,0x30,0xFE,0xDF,0xC8,0x10,0x01,0x00,0xB4,
    0x00,0x02,0x3F,0xD6,0x11,0xFC,0x60,0xD3,0xB1,0x00,0x00,0xB4,
    0xFE,0x17,0x40,0xF9,0xFF,0x03,0x01,0x91,0xFF,0x03,0x04,0x91,
    0xC0,0x03,0x5F,0xD6,0xE0,0x07,0x40,0xA9,0xE2,0x0F,0x41,0xA9,
    0xE4,0x13,0x40,0xF9,0xFE,0x17,0x40,0xF9,0xFF,0x03,0x01,0x91,
    0x40,0xE5,0xF4,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr uintptr_t kGameChangeRoomCallFileOffset = 0x354050;
inline constexpr std::array<u8, 4> kGameChangeRoomCallExpectedOriginal = {
    0xFC, 0x99, 0x0C, 0x94,
};
inline constexpr uintptr_t kGameChangeRoomRelayCodeOffset = 0x68CE60;
inline constexpr uintptr_t kGameChangeRoomRelaySlotOffset = 0x68CE90;
inline constexpr std::array<u8, 4> kGameChangeRoomRelayExpectedEntry = {
    0x84, 0xE3, 0x0C, 0x14,
};
inline constexpr std::array<u8, 64> kGameChangeRoomRelayExpectedBytes = {
    0xFF,0x43,0x00,0xD1,0xFE,0x07,0x00,0xF9,0x76,0xB6,0xFF,0x97,0xE0,0x03,0x13,0xAA,
    0x11,0x01,0x00,0x10,0x30,0xFE,0xDF,0xC8,0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,
    0xFE,0x07,0x40,0xF9,0xFF,0x43,0x00,0x91,0x73,0x1C,0xF3,0x17,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr uintptr_t kGameStartSavedCallFileOffset = 0x3F92A4;
inline constexpr uintptr_t kGameStartNewCallFileOffset = 0x3F93F8;
inline constexpr uintptr_t kGameStartSavedRelayCodeOffset = 0x68CC20;
inline constexpr uintptr_t kGameStartNewRelayCodeOffset = 0x68CC70;
inline constexpr uintptr_t kGameStartRelaySlotOffset = 0x68CCC0;
// ★ 这两条是"打完补丁后调用点上应有的分支指令"，编码里**含中继代码的地址** ——
// 换代码洞时必须与下面两段 80 字节的护栏**一起重算**，否则校验不过、挂点装不上
// （2026-09-14 就漏改过一次：只重算了 80 字节那段，结果设备上槽一直是 0）。
inline constexpr std::array<u8, 4> kGameStartSavedRelayExpectedEntry = {
    0x5F, 0x4E, 0x0A, 0x14,
};
inline constexpr std::array<u8, 4> kGameStartNewRelayExpectedEntry = {
    0x1E, 0x4E, 0x0A, 0x14,
};
inline constexpr std::array<u8, 80> kGameStartSavedRelayExpectedBytes = {
    0xFF, 0x83, 0x00, 0xD1, 0xE0, 0x07, 0x00, 0xA9,
    0xFE, 0x0B, 0x00, 0xF9, 0x91, 0xBF, 0xFF, 0x97,
    0xE0, 0x03, 0x40, 0xF9, 0x21, 0x00, 0x80, 0x52,
    0x51, 0x04, 0x00, 0x10, 0x30, 0xFE, 0xDF, 0xC8,
    0x50, 0x00, 0x00, 0xB4, 0x00, 0x02, 0x3F, 0xD6,
    0xE0, 0x07, 0x40, 0xA9, 0xFE, 0x0B, 0x40, 0xF9,
    0xFF, 0x83, 0x00, 0x91, 0x95, 0xB1, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
inline constexpr std::array<u8, 80> kGameStartNewRelayExpectedBytes = {
    0xFF, 0x83, 0x00, 0xD1, 0xE0, 0x07, 0x00, 0xA9,
    0xFE, 0x0B, 0x00, 0xF9, 0x8D, 0xBF, 0xFF, 0x97,
    0xE0, 0x03, 0x40, 0xF9, 0x41, 0x00, 0x80, 0x52,
    0xD1, 0x01, 0x00, 0x10, 0x30, 0xFE, 0xDF, 0xC8,
    0x50, 0x00, 0x00, 0xB4, 0x00, 0x02, 0x3F, 0xD6,
    0xE0, 0x07, 0x40, 0xA9, 0xFE, 0x0B, 0x40, 0xF9,
    0xFF, 0x83, 0x00, 0x91, 0xD6, 0xB1, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
inline constexpr std::array<uintptr_t, 3> kGameRestartCallFileOffsets = {
    0x351C50, 0x351D20, 0x351ECC,
};
inline constexpr std::array<uintptr_t, 3> kGameRestartRelayCodeOffsets = {
    0x68CEA0, 0x68CEF0, 0x68CF40,
};
inline constexpr uintptr_t kGameRestartRelaySlotOffset = 0x68CF90;
inline constexpr std::array<u8, 4> kGameRestartRelay0ExpectedEntry = {
    0x94, 0xEC, 0x0C, 0x14,
};
inline constexpr std::array<u8, 4> kGameRestartRelay1ExpectedEntry = {
    0x74, 0xEC, 0x0C, 0x14,
};
inline constexpr std::array<u8, 4> kGameRestartRelay2ExpectedEntry = {
    0x1D, 0xEC, 0x0C, 0x14,
};
inline constexpr std::array<u8, 80> kGameRestartRelay0ExpectedBytes = {
    0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,0xFE,0x0B,0x00,0xF9,0x45,0x92,0xFF,0x97,
    0xE0,0x03,0x40,0xF9,0x21,0x00,0x80,0x52,0xD1,0x06,0x00,0x10,0x30,0xFE,0xDF,0xC8,
    0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,0xE0,0x07,0x40,0xA9,0xFE,0x0B,0x40,0xF9,
    0xFF,0x83,0x00,0x91,0x60,0x13,0xF3,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr std::array<u8, 80> kGameRestartRelay1ExpectedBytes = {
    0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,0xFE,0x0B,0x00,0xF9,0x31,0x92,0xFF,0x97,
    0xE0,0x03,0x40,0xF9,0x41,0x00,0x80,0x52,0x51,0x04,0x00,0x10,0x30,0xFE,0xDF,0xC8,
    0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,0xE0,0x07,0x40,0xA9,0xFE,0x0B,0x40,0xF9,
    0xFF,0x83,0x00,0x91,0x80,0x13,0xF3,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr std::array<u8, 80> kGameRestartRelay2ExpectedBytes = {
    0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,0xFE,0x0B,0x00,0xF9,0x1D,0x92,0xFF,0x97,
    0xE0,0x03,0x40,0xF9,0x61,0x00,0x80,0x52,0xD1,0x01,0x00,0x10,0x30,0xFE,0xDF,0xC8,
    0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,0xE0,0x07,0x40,0xA9,0xFE,0x0B,0x40,0xF9,
    0xFF,0x83,0x00,0x91,0xD7,0x13,0xF3,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr uintptr_t kSaveLoadRelaySaveCallFileOffset = 0x3FA7B4;
inline constexpr uintptr_t kSaveLoadRelayLoadCallFileOffset = 0x3FAB60;
inline constexpr uintptr_t kSaveLoadRelaySaveCodeOffset = 0x68CEA0;
inline constexpr uintptr_t kSaveLoadRelayLoadCodeOffset = 0x68CEF0;
inline constexpr uintptr_t kSaveLoadRelaySlotOffset = 0x68CF90;
inline constexpr std::array<u8, 4> kSaveLoadRelaySaveExpectedEntry = {0xBB,0x49,0x0A,0x14};
inline constexpr std::array<u8, 4> kSaveLoadRelayLoadExpectedEntry = {0xE4,0x48,0x0A,0x14};
inline constexpr std::array<u8, 80> kSaveLoadRelaySaveExpectedBytes = {
    0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,0xFE,0x0B,0x00,0xF9,0x79,0xBF,0xFF,0x97,
    0xE0,0x03,0x13,0xAA,0x21,0x00,0x80,0x52,0xD1,0x06,0x00,0x10,0x30,0xFE,0xDF,0xC8,
    0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,0xE0,0x07,0x40,0xA9,0xFE,0x0B,0x40,0xF9,
    0xFF,0x83,0x00,0x91,0x39,0xB6,0xF5,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr std::array<u8, 80> kSaveLoadRelayLoadExpectedBytes = {
    0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,0xFE,0x0B,0x00,0xF9,0x81,0xBF,0xFF,0x97,
    0xE0,0x1F,0x00,0xB9,0xE0,0x03,0x14,0xAA,0x41,0x00,0x80,0x52,0x31,0x04,0x00,0x10,
    0x30,0xFE,0xDF,0xC8,0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,0xE0,0x07,0x40,0xA9,
    0xFE,0x0B,0x40,0xF9,0xE0,0x1F,0x40,0xB9,0xFF,0x83,0x00,0x91,0x0E,0xB7,0xF5,0x17,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr uintptr_t kStage128SaveDataManagerRelaySaveCallFileOffset = 0x36F474;
inline constexpr uintptr_t kStage128SaveDataManagerRelayLoadCallFileOffset = 0x379294;
inline constexpr uintptr_t kStage128SaveDataManagerRelaySaveCodeOffset = 0x68CEA0;
inline constexpr uintptr_t kStage128SaveDataManagerRelayLoadCodeOffset = 0x68CEF0;
inline constexpr uintptr_t kStage128SaveDataManagerRelaySlotOffset = 0x68CF90;
inline constexpr std::array<u8, 4> kStage128SaveDataManagerRelaySaveExpectedEntry = {0x8B,0x76,0x0C,0x14};
inline constexpr std::array<u8, 4> kStage128SaveDataManagerRelayLoadExpectedEntry = {0x17,0x4F,0x0C,0x14};
inline constexpr std::array<u8, 80> kStage128SaveDataManagerRelaySaveExpectedBytes = {
    0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,0xFE,0x0B,0x00,0xF9,0x21,0x00,0x80,0x52,
    0x11,0x07,0x00,0x10,0x30,0xFE,0xDF,0xC8,0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,
    0xE0,0x07,0x40,0xA9,0xFE,0x0B,0x40,0xF9,0xFF,0x83,0x00,0x91,0x0D,0x93,0xFF,0x97,
    0x6A,0x89,0xF3,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr std::array<u8, 80> kStage128SaveDataManagerRelayLoadExpectedBytes = {
    0xFF,0x83,0x00,0xD1,0xE0,0x07,0x00,0xA9,0xFE,0x0B,0x00,0xF9,0x41,0x00,0x80,0x52,
    0x91,0x04,0x00,0x10,0x30,0xFE,0xDF,0xC8,0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,
    0xE0,0x07,0x40,0xA9,0xFE,0x0B,0x40,0xF9,0xFF,0x83,0x00,0x91,0xE9,0x92,0xFF,0x97,
    0xDE,0xB0,0xF3,0x17,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr std::uint32_t kTargetModuleScanAttemptLimit = 300;
inline constexpr std::int64_t kTargetModuleScanIntervalNanoseconds = 100'000'000;
// 批次 370（2026-10-05）：`ModuleWorker` **在现有 5 秒等待之前**那一段有界前置步骤的上限。
//
// 那一段要抢在引擎第一次读共享路径（`Game::Init → Minimap::Init → ANM2::Load("gfx/ui/minimap1.anm2")`）
// 之前把模组挂载点挂上（取证见 `docs/分析-模组覆盖本体资源那一环该补在哪一刻-20261005.md`），
// 而那一刻**没有可等的东西** —— 只能小步问、问不到就走人。两条上限都是 **2 秒**（400 × 5 ms），
// 与"认不出来就原样继续（后续逻辑一字不改）"那条纪律配套：超时不是失败，只说明我们比引擎晚。
//
// ⚠️ 它们**不改变** `kWorkerStartupDelayNanoseconds` 的语义：5 秒等待仍在重活之前，
// 这段前置步骤只是"我们自己的线程在做等待"的一部分（它自己的耗时 =
// 状态面里的 `delayStartTicks - workerEnteredTicks`，见 `early_mod_mount_state.hpp`）。
inline constexpr std::uint32_t kEarlyMountModuleScanAttemptLimit = 400;
// ⚠️ 批次 371（2026-10-05）：这一条**不再被使用** —— 370 那版在 worker 线程里"有界轮询内容管理器
// 那个 GOT 槽、等到非 0 再挂"；371 把挂载挪进 `Game::Init` 的入口中继回调（游戏线程），那一刻
// 引擎自己正在跑、内容管理器必然在位，不需要轮询。**常量保留**（不删）：它是 370 的留痕，
// 也免得后来者以为"从来没量过这件事"。
inline constexpr std::uint32_t kEarlyMountContentManagerAttemptLimit = 400;
inline constexpr std::int64_t kEarlyMountPollNanoseconds = 5'000'000;

// 批次 371（2026-10-05）：**`Game::Init` 的入口** —— 零占洞入口中继的靶点。
//
// 为什么是它（取证见 `docs/分析-模组覆盖本体资源那一环该补在哪一刻-20261005.md`）：
//   全 NRO 里引用 `"gfx/ui/minimap1.anm2"` / `"minimap2.anm2"` 的地方**只有 `Minimap::Init`**，
//   而 `Minimap::Init` 的唯一调用者是 `Game::Init + 0x340`（`python3 tools/nro_callers.py 0x41C63C`）。
//   ⇒ 在 `Game::Init` **入口**挂中继 = 我们的回调一定排在"引擎第一次读那两个 anm2"**之前**
//   （入口中继契约：回调跑在目标函数体之前；回调自己决定几时调回退入口跑原函数）。
//   ⇒ 让模组那一层在引擎第一次读共享路径之前就存在（= PC 的形态），缓存里从头到尾不会出现
//   本体那份，**不需要任何"事后作废"**（那条路已被 368 的真机崩溃证伪）。
//
// 入口 16 字节（**不含任何 PC 相对指令** ⇒ 满足入口中继的安全门禁；已用
// `python3 tools/nro_disasm.py 0x34DD50 0x40` 逐字节复核）：
//   0x34DD50:  d101c3ff  sub  sp, sp, #0x70        → FF C3 01 D1
//   0x34DD54:  a9037bfd  stp  x29, x30, [sp, #0x30] → FD 7B 03 A9
//   0x34DD58:  9100c3fd  add  x29, sp, #0x30        → FD C3 00 91
//   0x34DD5C:  a9045ff8  stp  x24, x23, [sp, #0x40] → F8 5F 04 A9
//   （第 5 条 `bl Game::init_vars` 在 16 字节之外，不参与。）
// 注意：本文件 138 行附近另有一句旧注释写 `Game::Init @ 0x34DD7C`（那是 `Game::init_vars` 之后的
// 某个内部符号点，不是入口），**入口就是这里的 `0x34DD50`**，与 `tools/stage14_game_provenance.py`
// 的 `game_init` 登记逐字节一致。
inline constexpr uintptr_t kGameInitEntryFileOffset = 0x34DD50;
inline constexpr std::array<u8, 16> kGameInitEntryExpectedBytes = {
    0xFF, 0xC3, 0x01, 0xD1, 0xFD, 0x7B, 0x03, 0xA9,
    0xFD, 0xC3, 0x00, 0x91, 0xF8, 0x5F, 0x04, 0xA9,
};
// `ModuleWorker` 一进来就等多久（秒），由构建开关 `WORKER_STARTUP_DELAY_SECONDS` 决定。
//
// **默认 0 = 生产形状**：worker 建好就开始干活（2026-08-23 起就是这样，门禁
// `test_worker_does_not_depend_on_fixed_sdk_initialization_delay` 也钉着这条）。
// 真机实验包用 `WORKER_STARTUP_DELAY_SECONDS=5` 打开：把"我们自己的启动期动作"
// （扫内存找游戏模块、装挂点、自校验、读模组文件）挪到"系统装载游戏本体模块"那个窗口之后。
//
// 为什么不在 `exl_main` 里等：入口是被游戏**同步等待**的（记录续十六 §二：不做延迟不到 1 秒就崩、
// 延迟 8 秒版就"约 8 秒"崩、栈一模一样），在入口等等于直接给开机加秒数。
// 背景、实测数字与取舍见 `docs/问题与解决记录.md` 2026-09-16 续十六 与 `docs/改动日志-20260916.md`。
#if !defined(EXL_WORKER_STARTUP_DELAY_SECONDS)
#define EXL_WORKER_STARTUP_DELAY_SECONDS 0
#endif
inline constexpr std::int64_t kWorkerStartupDelayNanoseconds =
    static_cast<std::int64_t>(EXL_WORKER_STARTUP_DELAY_SECONDS) * 1'000'000'000LL;
inline constexpr std::array<u8, 0x20> kTargetBuildId = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31,
    0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7,
    0x23, 0x88, 0xB2, 0xAB, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
inline constexpr uintptr_t kManagerUpdateFileOffset = 0x3F8DB8;
// Build ID 91C73FDD575061318D68886316AFEAC72388B2AB (Repentance.nro).
// File offset 0x3F8DB8, Ghidra symbol _ZN15IsaacRepentance7Manager6UpdateEv:
// sub sp, #0x50; stp x29, x30, [sp, #0x10]; add x29, sp, #0x10; str x23, [sp, #0x20].
inline constexpr std::array<u8, 16> kManagerUpdateExpectedBytes = {
    0xFF, 0x43, 0x01, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF7, 0x13, 0x00, 0xF9,
};
inline constexpr uintptr_t kManagerRelayCodeOffset = 0x68CBE0;
inline constexpr uintptr_t kManagerRelayFallbackOffset = 0x68CBF0;
inline constexpr uintptr_t kManagerRelaySlotOffset = 0x68CBF8;
inline constexpr std::array<u8, 4> kManagerRelayExpectedEntry = {
    0x8A, 0x4F, 0x0A, 0x14,
};
inline constexpr std::array<u8, 32> kManagerRelayExpectedBytes = {
    0xD1, 0x00, 0x00, 0x10, 0x30, 0xFE, 0xDF, 0xC8,
    0x50, 0x00, 0x00, 0xB4, 0x00, 0x02, 0x1F, 0xD6,
    0xFF, 0x43, 0x01, 0xD1, 0x72, 0xB0, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
// 零占洞入口改写的前两条指令（`ldr x16, #8` + `br x16`，literal 就在紧随其后的 +8）。
// 用途：识别"这个函数入口已经被**入口中继**接管"——旧 IPS 形态与这种形态都要认的地方
// （例如 `ValidateItemPoolGetCollectibleMethod`）靠它区分。
// 数值必须与 `source/relay/entry_relay.hpp` 的编码器一致，由
// `src/infrastructure/relay/entry_relay_hook_adapter.cpp` 里的 static_assert 钉住。
inline constexpr std::uint32_t kEntryRelayEntryStubWord0 = 0x58000050;
inline constexpr std::uint32_t kEntryRelayEntryStubWord1 = 0xD61F0200;

inline constexpr uintptr_t kManagerRenderFileOffset = 0x3F9684;
// Manager::Render @3F97B8读+8，8BF819跳表仅场景2进入Game::Render；场景1是菜单。
inline constexpr uintptr_t kManagerRenderSceneOffset = 0x8;
inline constexpr std::uint32_t kManagerGameplayScene = 2;
inline constexpr std::array<u8, 16> kManagerRenderExpectedBytes = {
    0xFF, 0xC3, 0x02, 0xD1, 0xE8, 0x3B, 0x00, 0xFD,
    0xFD, 0x7B, 0x08, 0xA9, 0xFD, 0x03, 0x02, 0x91,
};
// `Manager::Render` 体内最后一次 `Present` 调用的位置（不是函数入口！）。
// 这 16 字节以 `bl`（PC 相对）开头，入口中继**无法回放**，因此它不能走 entry_relay；
// 迁移时改为改写该调用所用 PLT 桩对应的 GOT 槽（见设计文档 §4.5）。
// 登记它的唯一目的是把"不可入口挂"这个事实钉进测试。
//
// 偏移**复用**既有的 `kManagerPresentCallFileOffset`（见本文件 Present 调用点那一段），
// 不要再为它新造偏移常量 —— 同一地址只能有一个真值源。同一处的两个数组都配到这一个偏移常量：
// `kManagerPresentCallExpectedEntry` 描述**打补丁后**的 4 字节（入口已被改成跳向代码洞的 `b`），
// 本数组登记的是**原始镜像**的 16 字节。
//
// 命名与配对规则（**不要靠后缀推断**，本文件这里已经踩过坑）：
// `tools/verify_runtime_constants_against_nro.py` 的 `pair_guards()` 两侧剥的尾巴不一样 ——
// 偏移侧按 `OFFSET_SUFFIXES = ("FileOffset", "CallFileOffset", "Offset")` **整段剥掉**后缀
// （`FileOffset` 先命中），所以 `kManagerPresentCallFileOffset` 的基名是 `kManagerPresentCall`；
// 数组侧只剥 `ExpectedBytes`。因此本数组必须叫 `kManagerPresentCallExpectedBytes` 才配得上，
// 叫 `...CallFileExpectedBytes` 会因两侧基名不等而落进 `unpaired_arrays`。
// **不要**为了消掉 `unpaired_arrays` 再给这个地址补一个偏移常量 —— 那会把刚刚消除掉的
// "同一地址两个名字"重新引进来。
//
// 名字还必须以 `ExpectedBytes` 结尾，否则 `ARRAY_PATTERN` 根本不解析它。
// 另外要清楚校验器对它的作用很有限：`0x3F9B40` 是 `tools/build_patches.py` 的写入目标，
// 会被归为 `patched-image` 而跳过比对。换言之：**对着原始 NRO 逐字节核对这 16 字节的只有
// `runtime/tests/test_entry_relay_ledger.py`**，不要指望校验器兜底。
inline constexpr std::array<u8, 16> kManagerPresentCallExpectedBytes = {
    0xC0, 0xDB, 0x09, 0x94, 0xE8, 0x3B, 0x40, 0xFD,
    0xF4, 0x4F, 0x4A, 0xA9, 0xF6, 0x57, 0x49, 0xA9,
};
inline constexpr uintptr_t kManagerRenderRelayCodeOffset = 0x68CC00;
inline constexpr uintptr_t kManagerRenderRelayFallbackOffset = 0x68CC10;
inline constexpr uintptr_t kManagerRenderRelaySlotOffset = 0x68CC18;
inline constexpr std::array<u8, 4> kManagerRenderRelayExpectedEntry = {
    0x5F, 0x4D, 0x0A, 0x14,
};
inline constexpr std::array<u8, 32> kManagerRenderRelayExpectedBytes = {
    0xD1, 0x00, 0x00, 0x10, 0x30, 0xFE, 0xDF, 0xC8,
    0x50, 0x00, 0x00, 0xB4, 0x00, 0x02, 0x1F, 0xD6,
    0xFF, 0xC3, 0x02, 0xD1, 0x9D, 0xB2, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
// `MC_POST_RENDER` 的真实派发点：`Manager::Render` 体内最后一次 `Present` 调用。
//
// 入口中继（上面那组 `kManagerRenderRelay*`）把原函数整体当子调用跑完才回来派发，所以它派发时
// 本帧已经上屏、帧图像队列已经清空。2026-09-13 的真机照片（`analysis/stage149-photo/`）证明
// 后果有两条：回调里画的东西进的是**下一帧**队列，而且在那一帧里排在游戏自己的图像之前，于是
// 画在实体（以撒）与 HUD **之下**、只压在房间地面上。把派发插到 `Present` **之前**，图像就在
// 本帧入队、本帧 apply，并排在最后一个被画 —— 这才是 PC 的 `MC_POST_RENDER` 覆盖层语义。
//
// 调用点上下文：`x0` 已经是 `Present` 的实参（`KAGE::Graphics::g_Manager`），其后到 `ret`
// 之间只用 `d8` 与调用者保存之外寄存器，所以中继桩只需额外保存/恢复 `x0`。
inline constexpr uintptr_t kManagerPresentCallFileOffset = 0x3F9B40;
inline constexpr std::array<u8, 4> kManagerPresentCallExpectedEntry = {
    0xF0, 0x4C, 0x0A, 0x14,
};
inline constexpr uintptr_t kManagerPresentRelayCodeOffset = 0x68CF00;
inline constexpr uintptr_t kManagerPresentRelaySlotOffset = 0x68CF30;
// 覆盖代码洞 0x00..0x37：桩（含保存/恢复 x0 与 `blr`）＋补回的 `bl Present` ＋跳回 `调用点+4`；
// 末尾 8 字节正是 callback 槽（发布前为零），校验时按既有写法排除掉。
inline constexpr std::array<u8, 56> kManagerPresentRelayExpectedBytes = {
    0xFF, 0x43, 0x00, 0xD1, 0xF3, 0x03, 0x00, 0xF9,
    0xF3, 0x03, 0x00, 0xAA, 0x31, 0x01, 0x00, 0x10,
    0x30, 0xFE, 0xDF, 0xC8, 0x50, 0x00, 0x00, 0xB4,
    0x00, 0x02, 0x3F, 0xD6, 0xE0, 0x03, 0x13, 0xAA,
    0xF3, 0x03, 0x40, 0xF9, 0xFF, 0x43, 0x00, 0x91,
    0xC6, 0x8E, 0xFF, 0x97, 0x06, 0xB3, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
// ---- M2b：`render-present` 的"零代码字节"方案（改 GOT 槽，不改游戏指令）----
//
// `Manager::Render` 体内那次 `bl` 的目标是一个 PLT 桩（偏移 `0x670A40`）：
//     adrp x16, 0xA9E000 ; ldr x17, [x16, #0x488] ; add x16, x16, #0x488 ; br x17
// 桩读的那个槽在**模块内偏移 `0xA9E488`**（由 `_ZN4KAGE8Graphics7Manager7PresentEv` 的重定位表
// 独立印证）。槽里存的是加载器解析出来的 `Present` 地址，运行时**必须先读后存**，绝不能拿文件初值
// （`0x66FAA0`，那是懒绑定的解析桩）当准。
// 解码提醒：`ldr` 的 imm12 要按访问宽度缩放 —— 0x91 × 8 = 0x488，别当成 0x091。
//
// `Present` 本体（`_ZN4KAGE8Graphics7Manager7PresentEv`）就定义在本游戏模块内，偏移 `0x4F3014`。
//
// **关键事实（本方案成立的依据）**：指向这个桩的调用点**有 43 处**（`Game::Render` 6、
// `Room::Render` 5、`Manager::Render` 3、`EntityList::Update` 2、`HUD`/菜单/背景/过场…），
// 而 IPS 方案只拦截其中**一处**（`kManagerPresentCallFileOffset` = 0x3F9B40）。因此改槽之后，
// 拦截函数**必须按调用方过滤**：只有返回地址等于 `kManagerPresentCallFileOffset + 4` 的那一次调用
// 才派发 `MC_POST_RENDER`，其余 42 处原样转发给真正的 `Present` —— 行为与 IPS 方案逐字等价。
inline constexpr uintptr_t kManagerPresentStubOffset = 0x670A40;
inline constexpr std::array<u8, 16> kManagerPresentStubExpectedBytes = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0x46, 0x42, 0xF9,
    0x10, 0x22, 0x12, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kManagerPresentGotSlotOffset = 0xA9E488;
inline constexpr uintptr_t kManagerPresentTargetOffset = 0x4F3014;
inline constexpr std::array<u8, 16> kManagerPresentTargetExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x00, 0x40, 0xF9,
};
inline constexpr uintptr_t kGameInitCallFileOffset = 0x3F5A44;
inline constexpr std::array<u8, 8> kGameInitContextExpectedBytes = {
    0xE0, 0x03, 0x14, 0xAA, 0x14, 0x01, 0x00, 0xF9,
};
inline constexpr uintptr_t kGameObserverRelayCodeOffset = 0x68CC40;
inline constexpr uintptr_t kGameObserverRelaySlotOffset = 0x68CC70;
inline constexpr std::array<u8, 4> kGameObserverRelayExpectedEntry = {
    0x7F, 0x5C, 0x0A, 0x14,
};
inline constexpr std::array<u8, 64> kGameObserverRelayExpectedBytes = {
    0xFF, 0x43, 0x00, 0xD1, 0xF3, 0x03, 0x00, 0xF9,
    0xF3, 0x03, 0x00, 0xAA, 0x31, 0x01, 0x00, 0x10,
    0x30, 0xFE, 0xDF, 0xC8, 0x50, 0x00, 0x00, 0xB4,
    0x00, 0x02, 0x3F, 0xD6, 0xE0, 0x03, 0x13, 0xAA,
    0xF3, 0x03, 0x40, 0xF9, 0xFF, 0x43, 0x00, 0x91,
    0x92, 0xBE, 0xFF, 0x97, 0x77, 0xA3, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
inline constexpr uintptr_t kGameUpdateCallFileOffset = 0x3F905C;
inline constexpr std::array<u8, 4> kGameUpdateContextExpectedBytes = {
    0xC0, 0x02, 0x40, 0xF9,
};
inline constexpr uintptr_t kGameUpdateObserverRelayCodeOffset = 0x68CC80;
inline constexpr uintptr_t kGameUpdateObserverRelaySlotOffset = 0x68CCB0;
inline constexpr std::array<u8, 4> kGameUpdateObserverRelayExpectedEntry = {
    0x09, 0x4F, 0x0A, 0x14,
};
inline constexpr std::array<u8, 64> kGameUpdateObserverRelayExpectedBytes = {
    0xFF, 0x43, 0x00, 0xD1, 0xF3, 0x03, 0x00, 0xF9,
    0xF3, 0x03, 0x00, 0xAA, 0x31, 0x01, 0x00, 0x10,
    0x30, 0xFE, 0xDF, 0xC8, 0x50, 0x00, 0x00, 0xB4,
    0x00, 0x02, 0x3F, 0xD6, 0xE0, 0x03, 0x13, 0xAA,
    0xF3, 0x03, 0x40, 0xF9, 0xFF, 0x43, 0x00, 0x91,
    0x4E, 0xBF, 0xFF, 0x97, 0xED, 0xB0, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
inline constexpr uintptr_t kGameState2CallFileOffset = 0x3F903C;
inline constexpr std::array<u8, 4> kGameState2ContextExpectedBytes = {
    0xC0, 0x02, 0x40, 0xF9,
};
inline constexpr uintptr_t kGameState2ObserverRelayCodeOffset = 0x68CCC0;
inline constexpr uintptr_t kGameState2ObserverRelaySlotOffset = 0x68CCF0;
inline constexpr std::array<u8, 4> kGameState2ObserverRelayExpectedEntry = {
    0x21, 0x4F, 0x0A, 0x14,
};
inline constexpr std::array<u8, 64> kGameState2ObserverRelayExpectedBytes = {
    0xFF, 0x43, 0x00, 0xD1, 0xF3, 0x03, 0x00, 0xF9,
    0xF3, 0x03, 0x00, 0xAA, 0x31, 0x01, 0x00, 0x10,
    0x30, 0xFE, 0xDF, 0xC8, 0x50, 0x00, 0x00, 0xB4,
    0x00, 0x02, 0x3F, 0xD6, 0xE0, 0x03, 0x13, 0xAA,
    0xF3, 0x03, 0x40, 0xF9, 0xFF, 0x43, 0x00, 0x91,
    0x36, 0xBF, 0xFF, 0x97, 0xD5, 0xB0, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
// ---- 批次 147（2026-09-26）：`ModManager::LoadConfigs` —— 引擎那条"模组 content 加载"路的闸门 ----
//
// 与上面的 `kManagerLoadConfigsFileOffset`（`Manager::LoadConfigs @ 0x3F5C38`，加载**本体**配置）
// **不是同一个函数**：这一个在 `ModManager` 上，按每条模组的启用位决定读不读它的 `content/*.xml`。
//
// 依据（反汇编 `ModManager::Reset @ 0x422440` 与 `ModManager::LoadConfigs @ 0x41E388`）：
// ```
// Reset: UnloadMods → ListMods（此时把 +0x139 定死）→ Manager::ReloadConfigs → ModManager::LoadConfigs
// LoadConfigs: ldp x21, x8, [x0]        ; x0 = ModManager*，表 = [x0](begin)/[x0+8](end)
//              循环：ldr x0,[x21]; ldrb w8,[x0,#0x139]; cbz w8 → 跳过这一条
//              …… 通过则 LoadCustomResources + GetContentPath + ItemConfig::LoadCostumes / Music::LoadConfig …
// ```
// 我们在它的**入口**挂零占洞入口中继（`runtime/source/relay/entry_relay.hpp`）：那一刻列表已建好、
// 还没读过任何一条，正好按我们的开关把 `+0x139` 写成该启用/该禁用，然后放行原函数。
//
// 挂钩前提：入口 16 字节里**不得含 PC 相对指令**（入口中继会把这 16 字节拷到槽里回放）。
// 这四条是 `sub sp` / `stp` / `add x29,sp` / `stp`，都不含地址计算 ⇒ 可以挂。
inline constexpr uintptr_t kModManagerLoadConfigsFileOffset = 0x41E388;
inline constexpr std::array<u8, 16> kModManagerLoadConfigsExpectedBytes = {
    0xFF, 0xC3, 0x02, 0xD1, 0xFD, 0x7B, 0x05, 0xA9,
    0xFD, 0x43, 0x01, 0x91, 0xFC, 0x6F, 0x06, 0xA9,
};
// `ModEntry + 0x48` 是一个 libc++ `std::string`，内容是 `ListMods` 写进去的
// **"<模组目录>/content/"**（构造点在 `ListMods` 的 `0x4201F0`-`0x420248`：`<目录>` + `"/content/"`）。
// `ModEntry::GetContentPath @ 0x41EF10` 就是按短/长模式从这一格取 size/data 的 ——
// 我们照同一套 libc++ 规则读，用来把"存档里记着关掉的那个目录名"对到具体条目上。
inline constexpr uintptr_t kModEntryContentPathStringOffset = 0x48;
//: libc++ `std::string` 的长模式判据与字段位置：首字节最低位 = 1 表示"长模式"，
//: 此时 **`+0x8` = size、`+0x10` = data**（`__long` 的顺序是 cap / size / data）。
//: 短模式：`size = 首字节 >> 1`、`data` 紧随首字节（`+0x1`）之后。
//: ★ 依据取自引擎自己两处：`ModEntry::GetContentPath @ 0x41EF10` 取 `size` 读的是 `this+0x50`
//: （= 字符串起点 `+0x48` 再加 `0x8`）；`ListMods` 写新串是 `str x8,[entry+0x48]` +
//: `stp x9,x10,[entry+0x50]`（⇒ `+0x50` = size、`+0x58` = data）。**两格写反会拿长度当地址、当场崩。**
inline constexpr std::uint8_t kLibcxxStringLongModeBit = 0x1;
inline constexpr uintptr_t kManagerLoadConfigsFileOffset = 0x3F5C38;
inline constexpr uintptr_t kGameIsPausedRenderCallFileOffset = 0x3429A4;
inline constexpr std::array<u8, 12> kGameIsPausedRenderContextExpectedBytes = {
    0x48, 0x3B, 0x00, 0xD0, 0x08, 0x4D, 0x43, 0xF9, 0x00, 0x01, 0x40, 0xF9,
};
inline constexpr uintptr_t kGameIsPausedRenderObserverRelayCodeOffset = 0x68CD00;
inline constexpr uintptr_t kGameIsPausedRenderObserverRelaySlotOffset = 0x68CD30;
inline constexpr std::array<u8, 4> kGameIsPausedRenderObserverRelayExpectedEntry = {0xD7, 0x28, 0x0D, 0x14};
inline constexpr std::array<u8, 64> kGameIsPausedRenderObserverRelayExpectedBytes = {
    0xFF,0x43,0x00,0xD1,0xF3,0x03,0x00,0xF9,0xF3,0x03,0x00,0xAA,0x31,0x01,0x00,0x10,
    0x30,0xFE,0xDF,0xC8,0x50,0x00,0x00,0xB4,0x00,0x02,0x3F,0xD6,0xE0,0x03,0x13,0xAA,
    0xF3,0x03,0x40,0xF9,0xFF,0x43,0x00,0x91,0xF6,0x90,0xFF,0x97,0x1F,0xD7,0xF2,0x17,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
};
inline constexpr uintptr_t kManagerToModManagerOffset = 0x36800;

// ---- 批次 409（2026-10-08）：`ModManager::LoadConfigs` 的**收尾那一步** ----------------------
//
// 一句话：引擎在"逐模组喂完 content"之后还要把 `gfx/ui/mod_defaults.anm2` 载进
// `ModManager + 0x368` 那个 `ANM2`；这一步我们（批次 378 重放这个函数时）**漏了**
// ⇒ 那个 ANM2 永远是默认构造（层数组为空）⇒ 在**暂停屏上画模组道具**时崩。
//
// ## 依据：`ModManager::LoadConfigs @ 0x41E388` 循环体**之后**的尾部（逐条反汇编）
//
//   * `0x41E3B4 mov x19, x0` —— 入口把 `this`（`ModManager*`）存进 `x19`；
//   * `0x41ED24 ldr x8,[x22]`（`x22` = `g_Manager` 槽）+ `0x41ED28 mov w9,#0x6758` +
//     `0x41ED2C movk w9,#0x3,lsl#16` + `0x41ED30 add x0,x8,x9` ⇒ `x0 = Manager + 0x36758`
//     ⇒ `0x41ED34 bl EntityConfig::PostLoadMods()`（**= 本仓 `kModContentFeedSpecs` 第 15 行，已实现**）；
//   * `0x41ED3C add x19, x19, #0x368` ⇒ `x19 = ModManager + 0x368`；
//   * `0x41ED54 add x10, x10, #0x790` ⇒ 字面量 **`"gfx/ui/mod_defaults.anm2"`**；
//   * `0x41ED70 mov w2, #0x1` + `0x41ED78 mov x0, x19` + `0x41ED7C bl ANM2::Load(string const&, bool)`
//     ⇒ **`ANM2::Load("gfx/ui/mod_defaults.anm2", true)`，`this = ModManager + 0x368`**。
//
// ## 为什么漏了它就会崩（真机 2026-10-08 13:45 实测崩过一次，报告
//    `dist/crash-20261008-1345/01791438320_010021c000b6a000.log`）
//
//   * 暂停屏 `PauseScreen::Render` 遍历玩家道具；**道具 id ≥ `0x2DD`（= 733，本体收集品上限之后）**
//     的那一条走 `ModManager::RenderCustomCollectionItem(id, …)`（调用点 `0x4332DC`，
//     `cmp w23, #0x2dd` + `b.lt` 在 `0x433254/0x433258`）；
//   * 该函数里道具没有自定义图时走"默认"分支（`0x422AC0`）：`x24 = ModManager + 0x368`，
//     `ANM2::SetFrame("Default", 0)`，然后 `0x422B18 mov w1, wzr` + `0x422B1C bl ANM2::GetLayer`
//     + `0x422B20 add x0, x0, #0x80` + `bl KAGE::Graphics::BlendMode::operator=`；
//   * ★★ `ANM2::GetLayer(int)`（`0xA034`）**不做"越界返回空"**：越界只打一条日志，
//     然后照样算 `x0 = [ANM2 + 0xA8](层数组基址) + i * 0xB0`（`0xA080`-`0xA088`）
//     ⇒ 基址为空时 `x0 = 0` ⇒ 紧跟的 `add x0,x0,#0x80` 让**写落到 `0x80`** ⇒ `Data Abort`；
//   * 真机报告逐字对上：`PC = BlendMode::operator= + 0x4`、`X[00] = 0x80`、
//     `LR = ModManager::RenderCustomCollectionItem + 0x198`、
//     `ReturnAddress[00] = PauseScreen::Render + 0x560`。
//
// ## 为什么"引擎不调"这条前提是硬的（不是推断）
//
//   * `ModManager::LoadConfigs` 全镜像只有 **2 个调用者**，且都在 `ModManager` 自己里：
//     `ModManager::Reset + 0x30`（`0x422470`）与 `ModManager::PostLanguageSwitch + 0x24`（`0x422768`）；
//   * 而 **`ModManager::Reset` / `ModManager::PostLanguageSwitch` / `ModManager::PreLanguageSwitch`
//     三者全镜像的调用点数都是 0** ⇒ `LoadConfigs` 在这版镜像里**从不执行**（与批次 147/148 的
//     定案一致），所以这个 ANM2 必须由我们载 —— 见 `mod_menu_native.cpp` 的
//     `LoadModManagerDefaultAnm2Once`。
//   * 复核命令：`python3 tools/nro_disasm.py 0x41ed10 0x100`；调用点扫描见本批改动日志。
inline constexpr uintptr_t kModManagerDefaultAnm2Offset = 0x368;
//: ★★ 要调的那个函数 **不自造新常量**：它就是上面 `kSpriteLoadOffset`（`0xC970`）那个函数 ——
//: 2026-10-04/05 符号表已复核 `0xC970` 的 mangled 名就是
//: `_ZN15IsaacRepentance4ANM24LoadERKNSt3__112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEEb`
//: （Lua 侧 `Sprite:Load` 与引擎侧 `ANM2::Load` **是同一个地址**）。一个地址只留一个名字、一份守卫。
//:
//: ★ 为什么这里**不**像别的入口那样在运行时核对序言：批次 363 的 `ANM2::Load` **入口中继**会把
//: 该函数头 16 字节改写成跳转桩（见 `hook_manager.cpp` 批次 365 那段注释），所以运行期那 16 字节
//: 可能已经**不是**原版序言 —— 拿原版序言去核对会**必然失败**、把这一步静默跳过（那正是本次要修的
//: 形态）。地址直接取 `模块基址 + kSpriteLoadOffset`：中继装上了就**走中继**（语义正确：
//: 模组若自带 `resources/gfx/ui/mod_defaults.anm2` 时该由模组那份赢），没装上就是原函数。
//: 那 16 字节守卫仍由 `test_anm2_load_override_hook.py` / `test_binding_guard_ordering.py` /
//: `--only engine_offset_signatures` 在离线门禁里钉住。
//: 形参口径（反汇编自证）：`x0 = this(ANM2*)`、`x1 = const std::string*`、`w2 = bool` ——
//: 入口 `0xC990 mov w20, w2` / `0xC994 mov x21, x1` / `0xC998 mov x19, x0`。
//: 那一步要载的文件（与 `0x41ED54` 处字面量逐字节相同）。
inline constexpr char kModManagerDefaultAnm2Path[] = "gfx/ui/mod_defaults.anm2";
//: `ANM2::Load` 入口拿不到（模块基址为 0）时占的位（`modEngineLoaderFailures` 的 bit18 —— 它同样
//: 不在那 16 行表里）。
inline constexpr std::uint32_t kModFeedAnm2LoadFailureBit = 1U << 18;

inline constexpr uintptr_t kModManagerResetFileOffset = 0x422440;
inline constexpr std::array<u8, 16> kModManagerResetExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
inline constexpr std::array<u8, 16> kManagerLoadConfigsExpectedBytes = {
    0xFF, 0x43, 0x02, 0xD1, 0xFD, 0x7B, 0x03, 0xA9,
    0xFD, 0xC3, 0x00, 0x91, 0xFC, 0x6F, 0x04, 0xA9,
};
inline constexpr uintptr_t kManagerLoadConfigsRelayCodeOffset = 0x68CC20;
inline constexpr uintptr_t kManagerLoadConfigsRelayFallbackOffset = 0x68CC30;
inline constexpr uintptr_t kManagerLoadConfigsRelaySlotOffset = 0x68CC38;
inline constexpr std::array<u8, 4> kManagerLoadConfigsRelayExpectedEntry = {
    0xFA, 0x5B, 0x0A, 0x14,
};
inline constexpr std::array<u8, 32> kManagerLoadConfigsRelayExpectedBytes = {
    0xD1, 0x00, 0x00, 0x10, 0x30, 0xFE, 0xDF, 0xC8,
    0x50, 0x00, 0x00, 0xB4, 0x00, 0x02, 0x1F, 0xD6,
    0xFF, 0x43, 0x02, 0xD1, 0x02, 0xA4, 0xF5, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
inline constexpr std::size_t kGameFileObjectSize = 0x60;
inline constexpr uintptr_t kGameFileConstructorFileOffset = 0x4CCBC0;
inline constexpr uintptr_t kGameFileOpenReadFileOffset = 0x4CCD58;
inline constexpr uintptr_t kGameFileOpenWriteFileOffset = 0x4CCE38;
inline constexpr uintptr_t kGameFileGetLengthFileOffset = 0x4CD104;
inline constexpr uintptr_t kGameFileReadFileOffset = 0x4CD184;
inline constexpr uintptr_t kGameFileWriteFileOffset = 0x4CD190;
inline constexpr uintptr_t kGameFileCloseFileOffset = 0x4CD00C;
inline constexpr uintptr_t kGameFileDestructorFileOffset = 0x4CCBFC;
inline constexpr std::array<u8, 16> kGameFileConstructorExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
inline constexpr std::array<u8, 16> kGameFileOpenReadExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x02, 0x1F, 0x00, 0xD0,
};
inline constexpr std::array<u8, 16> kGameFileOpenWriteExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x03, 0x00, 0xAA,
};
inline constexpr std::array<u8, 16> kGameFileGetLengthExpectedBytes = {
    0xFF, 0x83, 0x00, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xFF, 0x07, 0x00, 0xF9,
};
inline constexpr std::array<u8, 16> kGameFileReadExpectedBytes = {
    0x5B, 0xCB, 0x06, 0x14, 0x00, 0xE0, 0x00, 0xD1,
    0x59, 0xCB, 0x06, 0x14, 0x5C, 0xCB, 0x06, 0x14,
};
inline constexpr std::array<u8, 12> kGameFileWriteExpectedBytes = {
    0x5C, 0xCB, 0x06, 0x14, 0x00, 0xE0, 0x00, 0xD1,
    0x5A, 0xCB, 0x06, 0x14,
};
inline constexpr std::array<u8, 16> kGameFileCloseExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
inline constexpr std::array<u8, 16> kGameFileDestructorExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x2F, 0x00, 0xB0,
};
inline constexpr char kRomfsSentinelPath[] = "rom:/isaac_mod_probe.lua";
inline constexpr char kRomfsSentinelContents[] = "ISAAC_ROMFS_PROBE\n";
inline constexpr std::size_t kRomfsSentinelLength = 18;
inline constexpr char kRomfsLuaProbePath[] = "rom:/runtime_probe.lua";
inline constexpr std::size_t kRomfsLuaProbeMaximumLength = 4096;
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
inline constexpr char kRomfsModManifestPath[] = "rom:/isaac_mods/manifest.json";
// 必须与 `runtime/src/application/mod/manifest_service.hpp` 的同名常量一致：`hook_manager.cpp`
// 同时包含两者，这里未限定的名字解析到全局作用域这一个（`g_DefaultManifest` 的缓冲区），
// 而服务用自己命名空间里的那一个做读取上限判定。
// 2026-09-14：131072 -> 524288。真实贴图 Mod（qualityonsprites）的清单是 **309 KB**（712 个
// 源文件 + 711 个生成的 `.pcx`，每条记录带 path+sha256），而 `GameFileReader::ReadTextFile`
// 对超过缓冲区的文件返回 `LengthOutOfRange` —— "清单过大"等于直接 `ManifestRead` 失败。
// 512 KiB 按实测每条约 200 字节可容纳约 2600 个文件，代价只是 .bss（磁盘映像不变）。
inline constexpr std::size_t kRomfsModManifestMaximumLength = 524288;
// 2026-09-12：16384 -> 1048576。真机报告 `01789200504` 的根因就是它太小：EID 的 `main.lua`
// 是 **87,328 字节**、`require` 的语言文件最大 **243,740 字节**，而 `ReadTextFile` 对超长文件
// 返回 `LengthOutOfRange` → `EntryRead` 失败（诊断字 `[11] = 4`）→ **EID 的 Lua 一行都没跑**，
// 表现为"加载不报错、回调注册表为空、屏幕上什么都没有"。1 MiB 是最大 Lua 文件的 4 倍，
// 只花 .bss。同名常量在 `manifest_service.hpp` 里也有一份，两者必须相等（见 `hook_manager.cpp`
// 的 `static_assert`）。
// 2026-10-29：作者WOL固定提交cffda577原样IsaacScript构建入口为2,698,817B，
// 1MiB会直接EntryRead失败。上调至3MiB；生产入口与require各复用一份缓冲，
// 合计BSS增加4MiB，不随模组数增加，也没有新增每帧工作/分配/IO。
inline constexpr std::size_t kRomfsModScriptMaximumLength = 3145728;
#endif

// KAGE content mount points: how a Mod's own `resources/` directory reaches the
// engine's resource lookup. `ContentMountPointPath(char const*)` joins the string
// with `ContentManager::ApplicationMountPoint()`, `AddMountPoint(path const&)`
// builds a `ContentMountPoint` whose `FileMap::build` **enumerates the directory
// recursively** (through `nn::fs`, so the Atmosphere SD overlay is included) and
// files stay addressable by their path relative to the mount point. A Mod mount
// point therefore needs no `kage_mount_points.dat` entry.
//
// Hardware evidence for the whole chain (7 guards matching on the device plus the
// four-step resolution result) is in
// `analysis/stage146-content-mount-point/device-evidence-20260913.json`, crash
// report `01789131431`.
inline constexpr uintptr_t kContentManagerSlotOffset = 0xAAC748;
inline constexpr uintptr_t kContentMountPointPathCtorOffset = 0x4C0D84;
inline constexpr std::array<u8, 16> kContentMountPointPathCtorExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x00, 0x80, 0x12,
};
inline constexpr uintptr_t kContentMountPointPathDtorOffset = 0x4C0F60;
inline constexpr std::array<u8, 16> kContentMountPointPathDtorExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
inline constexpr uintptr_t kContentAddMountPointOffset = 0x4C1700;
inline constexpr std::array<u8, 16> kContentAddMountPointExpectedBytes = {
    0xFD, 0x7B, 0xBB, 0xA9, 0xFA, 0x67, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9,
};

// ---------------------------------------------------------------------------
// 目录枚举与文件写入：**引擎自己**的文件层（2026-09-16 取证，当前无调用方）
// ---------------------------------------------------------------------------
//
// ★ 下面这组常量**现在没有调用方** —— 它们是"方案 A（运行时自己发现模组、清单降级成可选）"
//   的取证结果。2026-09-16 用户裁定"先不做"，所以探针代码已删除，**证据留在这里**：
//   下一轮要做的时候不必再从头 argv 一遍（而且门禁会继续用 NRO 逐字节核对这些守卫字节）。
//   完整经过与真机读数见 `docs/问题与解决记录.md` 续三十/续三十一。
//
// 背景：我们模块自己起 `sm`/`fs` 会话是**死的**（`svcConnectToNamedPort("sm:")` 在内核层返回
// `0x10801` OutOfResource，`fsInitialize` 因此 `0xE401`，12 秒后重试不变；见
// `docs/SaltyNX文件服务与自建方案研究.md`）。但引擎自己那套 `KAGE::Filesys` 用的是**游戏进程
// 已经建好的 fs 会话**（游戏靠它写存档、读 romfs，我们的模组挂载点也是靠它生效的）。
//
// 真机结论（`dist/gdb-read-20260916-171017.txt`）：
//   * `isaac_mods/mods` 列得出来，`count = 2`，两个条目就是卡上的两个模组目录，
//     名字读回来分别是 "external item de…" 与 "multimod-probe" ⇒ **覆盖层里的目录看得见**；
//   * 返回的指针是**第一个条目**的地址（条目数走出参给），条目 0x10 字节：
//     `+0x00` 标志字节、`+0x08` 名字指针；标志 `0x06` = 目录 + 自己拥有名字串；
//   * ⚠️ **只对 `isaac_mods/mods` 这种路径安全**：对子目录（`…/multimod-probe`）再调一次会
//     触发**引擎内部断言**（崩溃报告 `01789549162`）。
//
// 下面这些偏移的守卫字节仍由门禁逐字节核对（`*ExpectedBytes` 的既有机制）。

// `KAGE::Filesys::IContentManager::GetDirectoryEntries(char const* path, unsigned& count)`
//   * 符号：`.dynsym` 里函数体在 `0x4C23C4`（名字见 `tools/nro_symbols.py` 的查询结果）；
//   * 行为（反汇编逐条读出）：`x1` = 路径（相对**应用根**，与 `AddMountPoint` 同一口径，
//     内部会先过 `KAGE::Util::Path::CreateCleanPath`），`x2` = 出参 `unsigned& count`；
//     返回一个 `new[]` 出来的块：`[0]` 是条目数（8 字节），条目紧跟其后、**每项 0x10 字节**；
//   * 释放：那块内存是引擎的 `operator new[]`（`_Znam`）分配的 ⇒ 必须用引擎的
//     `operator delete[]`（`_ZdaPv`，GOT 槽见下）释放，用我们的 `free` 会踩坏游戏堆。
inline constexpr uintptr_t kContentGetDirectoryEntriesOffset = 0x4C23C4;
inline constexpr std::array<u8, 16> kContentGetDirectoryEntriesExpectedBytes = {
    0xFF, 0x83, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF7, 0x1B, 0x00, 0xF9,
};
// `KAGE::Filesys::DirectoryEntry`（0x10 字节一项）：
//   * `+0x00` 标志字节：bit0 = 是文件、bit1 = 是目录。证据 = 引擎自己的两个内联访问器
//     `DirectoryEntry::IsFile()`（`0x4C2730`：`ldrb w8,[x0]` + `and w0,w8,#0x1`）与
//     `DirectoryEntry::IsDirectory()`（`0x4C273C`：`ldrb w8,[x0]` + `ubfx w0,w8,#1,#1`）；
//   * `+0x08` `char const* Name`。证据 = `DirectoryEntry::GetName()`（`0x4C2748`：`ldr x0,[x0,#0x8]`）；
//   * 每项 0x10：`GetDirectoryEntries` 里那条 `asr x8, x8, #4`（按 16 字节算条目数）与拷贝循环
//     里的 `add x21, x21, #0x10`。
inline constexpr std::size_t kDirectoryEntrySize = 0x10;
inline constexpr std::size_t kDirectoryEntryNameOffset = 0x08;
// ⚠️ **返回值不是分配起点**：`GetDirectoryEntries` 返回的是**条目数组的首地址**，条目数组前面还压着
// 一个 8 字节的"条目数"头，真正的 `new[]` 指针在返回值的**前 8 字节**（`返回值 - 8`）。
// 反汇编（2026-09-17 逐条读出 `0x4C23C4`）：
//   * `0x4C2480 orr x8, x22, #0x8` + `0x4C2488 bl _Znam` ⇒ 申请的是 `条目区字节数 + 8`；
//   * `0x4C2490 str x21, [x20], #0x8` ⇒ 把条目数写进块首 8 字节，并把指针推到 +8；
//   * 之后的构造/拷贝循环都以 `x20`（= 块首 + 8）为条目基址（`add x21, x21, #0x10`）；
//   * `0x4C2534 mov x0, x20` + `ret` ⇒ **返回的就是"块首 + 8"**。
// ⇒ 释放必须用 `返回值 - kDirectoryEntryCountHeaderSize`。用返回值直接 `delete[]` 等于释放一个
//   偏移指针（不是块首）⇒ 踩坏游戏线程本地堆的空闲链表 ⇒ **几层调用之后**在一次毫不相干的
//   分配里炸掉（真机现象见 `docs/问题与解决记录.md` 续三十七）。
inline constexpr std::size_t kDirectoryEntryCountHeaderSize = 0x08;
inline constexpr unsigned kDirectoryEntryFileBit = 0;
inline constexpr unsigned kDirectoryEntryDirectoryBit = 1;

// 引擎的 `operator delete[]`（`_ZdaPv`）**GOT 槽**：NRO 的重定位表里 `_ZdaPv` 只有一条
// `R_AARCH64_JUMP_SLOT`（`0xA9DD30`），运行期槽内就是真正要调用的地址。取槽里的值再调用，
// 既不必自己解析 PLT，也不会用到我们模块的 `free`。证据 = `tools/nro_symbols.py` 的
// `parse_dynamic_relocations()` 输出（`_ZdaPv: slots=['0xa9dd30'] type=[1026]`）。
inline constexpr uintptr_t kEngineArrayDeleteGotOffset = 0xA9DD30;

// `KAGE::Filesys::File`（引擎自己的文件类）—— 写文件用：
//   * 构造 `File::File()`（`0x4CCBC0`）：内部调 `BufferedFileStream` 的构造、写 vtable 到
//     `+0x00`/`+0x38`、清 `+0x50` 起两个 8 字节 ⇒ 对象至少 0x58 字节（调用方留 0x80 更稳）；
//   * `bool File::OpenWrite(char const* name)`（`0x4CCE38`）：路径会拼在
//     `g_SaveDataManager.GetMountPoint()` 后面（`0x4CCE48` 取全局 `g_SaveDataManager` 槽、
//     `0x4CCE54` 调 `SaveDataManager::GetMountPoint`），也就是**写进游戏的存档目录**，
//     不是任意 `sdmc:` 路径 —— 想要"模组的开关状态"这类持久化，这里正好是合适的位置；
//   * `File::Write(char const* data, int count, int elementSize)`（`0x4CD190`，尾调到
//     `BufferedStreamBase::WriteToBuffer`），底层是 `nn::fs::WriteFile`；
//   * `bool File::Close()`（`0x4CD00C`）。
inline constexpr uintptr_t kFilesysFileCtorOffset = 0x4CCBC0;
inline constexpr std::array<u8, 16> kFilesysFileCtorExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
inline constexpr uintptr_t kFilesysFileOpenWriteOffset = 0x4CCE38;
inline constexpr std::array<u8, 16> kFilesysFileOpenWriteExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x03, 0x00, 0xAA,
};
// `File::Write`（`0x4CD190`）是**虚函数覆盖**，尾调到 `BufferedStreamBase::WriteToBuffer`
// —— 写进的是缓冲，真机实测"打开成功但写入失败"（缓冲没 `Create` 过）。真正直连
// `nn::fs::WriteFile` 的是 `File::write_stream_data`（`0x4CD220`，2026-09-16 第二轮改用）：
// `0x4CD230` 先查 `[x0+0x40] == 1`（打开模式必须是"写"）、`0x4CD24C` 取 `[x0+0x50]` 的句柄，
// `0x4CD26C` 调 `nn::fs::WriteFile(handle, offset, data, size, option)`。
// `bool File::open_write(char const* name, char const* mount)`（`0x4CCEB0`）：**带自定义挂载点**的
// 打开写入口。⚠️ 2026-09-16 第二轮更正：**自定义挂载点并不等于"能写到任意位置"** —— 挂载点只是
// 拼在名字前面的前缀，最终仍由 `nn::fs::OpenFile` 在**游戏进程已挂载的那张表**里解析。游戏只挂了
// `rom`（`0x4CC6C8` 传字面量 `"rom"`）与存档（`"sdmc"`，见下文 `GetMountPoint`），**没有挂真 SD 卡**
// （它连 `nn::fs::MountSdCard` 都没导入）⇒ 传 `"sdmc:/SaltySD/…"` 只会落进存档分区。第一轮三个探针
// 文件因此全部"打开失败"（真机读数 + 上面的静态证据两条对得上）。
//
// 反汇编（逐条读出）：`w3 = 6`（`nn::fs` 的 `Write|AllowAppend`）；`x0 = this`、`x1 = name`、
// `x2 = mount` 原样传给 `File::open_file_handle`；成功后再尾调
// `BufferedFileStream::OpenWrite(name)`（建立缓冲层，也会把 `[this+0x40]` 置成"写"状态 ——
// `write_stream_data` 的前置检查就是它）。**注意**：这个返回值是"两步都对"才为真，
// 所以第一轮读数里的"打开失败"也可能来自第二步（缓冲层）。
inline constexpr uintptr_t kFilesysFileOpenWriteWithMountOffset = 0x4CCEB0;
inline constexpr std::array<u8, 16> kFilesysFileOpenWriteWithMountExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xC3, 0x00, 0x80, 0x52,
};
// `bool File::open_file_handle(char const* name, char const* mount, int mode)`（`0x4CD2D4`）：
//   * `x1` = 文件名、`x2` = 挂载点前缀、`w3` = `nn::fs::OpenMode`；
//   * 长度上限 `w23 = (mode & 2) ? 0x104 : 0x40`（写路径 260 字节）；
//   * `0x4CD358 bl KAGE::Util::Path::CreateCleanPath(name, mount, false, false)` ⇒ **拼路径**；
//   * `0x4CD374 bl nn::fs::OpenFile(&handle@this+0x50, 拼好的路径, mode)` ⇒ 用的是**游戏自己的
//     fs 会话**（这就是"我们模块自己起不了 sm/fs、但引擎能写"的原因）。
inline constexpr uintptr_t kFilesysFileOpenFileHandleOffset = 0x4CD2D4;
inline constexpr std::array<u8, 16> kFilesysFileOpenFileHandleExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
// `File` 对象尺寸 = **0x60 字节**：证据 = `SaveDataManagerBase::OpenSaveFileForWriting`（`0x4CC278`）
// 里 `mov w0, #0x60; bl _Znwm; bl File::File()`（`0x4CC2C8`/`0x4CC2D0`/`0x4CC2D4`），
// 之后 `ldr x8,[x20]; ldr x8,[x8,#0x60]; blr x8` 就是引擎自己的"创建/打开写"虚调用。
inline constexpr std::size_t kFilesysFileObjectSize = 0x60;
// `File::Write`（`0x4CD190`）是**虚函数覆盖**，尾调到 `BufferedStreamBase::WriteToBuffer`
// —— 写进的是缓冲（真机第一轮"打开成功但写入失败"就是它）。本探针把两条路都试一遍，
// 所以这个入口也要有守卫。
inline constexpr uintptr_t kFilesysFileWriteOffset = 0x4CD190;
inline constexpr std::array<u8, 16> kFilesysFileWriteExpectedBytes = {
    0x5C, 0xCB, 0x06, 0x14, 0x00, 0xE0, 0x00, 0xD1,
    0x5A, 0xCB, 0x06, 0x14, 0x20, 0x00, 0xA0, 0x52,
};
inline constexpr uintptr_t kFilesysFileWriteStreamDataOffset = 0x4CD220;
inline constexpr std::array<u8, 16> kFilesysFileWriteStreamDataExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
inline constexpr uintptr_t kFilesysFileCloseOffset = 0x4CD00C;
inline constexpr std::array<u8, 16> kFilesysFileCloseExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
// 探针写完就删：`g_SaveDataManager` 的全局槽（`File::OpenWrite` 用的就是它）+
// `SaveDataManager::DeleteSaveFile(char const*)`（`0x4CDD18`）。
inline constexpr uintptr_t kSaveDataManagerGlobalSlotOffset = 0xAAC940;
inline constexpr uintptr_t kSaveDataDeleteFileOffset = 0x4CDD18;
inline constexpr std::array<u8, 16> kSaveDataDeleteFileExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};

// ---- 读回来的那半条通道 + "存档分区叫什么名字"（2026-09-16 第二轮探针新增）----
//
// `bool File::OpenRead(char const* path)`（`0x4CCD58`）：与 `OpenWrite` **不对称** ——
// `0x4CCD64` 把挂载点写成空串字面量（`0x8AED62`，编目里就是某个字符串的结尾那个 NUL，
// 链接器合并出来的空串），于是 `CreateCleanPath` 只返回原样路径 ⇒ **这里要传完整路径**
// （`"sdmc:/<名字>"`），不能像 `OpenWrite` 那样只传相对名字。之后同样尾调
// `BufferedFileStream::OpenRead`。
inline constexpr uintptr_t kFilesysFileOpenReadOffset = 0x4CCD58;
inline constexpr std::array<u8, 16> kFilesysFileOpenReadExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x02, 0x1F, 0x00, 0xD0,
};
// `bool File::Exists(char const* path)`（`0x4CCCE8`）—— **引擎自己的存在性判定**，
// 也是"绝不盲开"的现成实现（2026-09-22 批次 043 反汇编逐条读出来的）：
//
//     004cccf8  mov  x1, x0               ; path
//     004cccfc  adrp x0, 0xaac000
//     004ccd00  ldr  x0, [x0, #0x748]     ; g_ContentManager（**一次取值**就是对象指针）
//     004ccd04  bl   IContentManager::GetMountedFilePath
//     004ccd08  cbz  x0, 0x4ccd40         ; 解析不到 ⇒ w20 = 0 ⇒ **直接返回 false，不炸**
//     004ccd18  bl   nn::fs::OpenFile(…, mounted, 1)   ; 解析得到才真去开
//
// ⚠️ 2026-09-22 起**没有消费者**（批次 044 的探针曾用它做"读文件前的存在性检查"，
// 后来发现真正的错不在这里、而在于**把没解析过的路径交给读函数** ⇒ 进标题界面即崩，
// 见 `docs/问题与解决记录.md` 续七十；修法是改用 `kContentManagerGetMountedFilePathOffset`
// 拿"引擎自己能打开的绝对路径"再读）。**保留这个常量与这段证据**，因为它是引擎自己的存在性
// 判定：判"在不在"时用它**不会**因路径形状不对而炸（它内部会先解析），以后要用直接拿。
//
// 参数一个（path），返回 `bool`（w0）。**它是静态函数**（没有 `this`），所以调用点不需要
// 任何单例指针。
inline constexpr uintptr_t kFilesysFileExistsOffset = 0x4CCCE8;
inline constexpr std::array<u8, 16> kFilesysFileExistsExpectedBytes = {
    0xFF, 0xC3, 0x00, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
// `int File::read_stream_data(char* dest, int count, int elementSize)`（`0x4CD1B0`）：
//   * `0x4CD1BC ldr w9,[x0,#0x40]; cbz` ⇒ 打开模式必须是"读"（`0x4CD1C4` 返回 0 = 失败）；
//   * `0x4CD1D4 mul w9, w3, w2` ⇒ 字节数 = `count * elementSize`（与写侧同形）；
//   * `0x4CD1EC ldp x1,x2,[x0,#0x50]` 取句柄与偏移、`0x4CD1FC bl nn::fs::ReadFile`；
//   * `0x4CD204 ldr x0,[x29,#0x18]` ⇒ **返回值就是读到的字节数**（0 = 失败）。
inline constexpr uintptr_t kFilesysFileReadStreamDataOffset = 0x4CD1B0;
inline constexpr std::array<u8, 16> kFilesysFileReadStreamDataExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x09, 0x40, 0x40, 0xB9,
};
// `int File::GetLength() const`（`0x4CD104`）：取 `[x0+0x50]` 的句柄问长度。
inline constexpr uintptr_t kFilesysFileGetLengthOffset = 0x4CD104;
inline constexpr std::array<u8, 16> kFilesysFileGetLengthExpectedBytes = {
    0xFF, 0x83, 0x00, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xFF, 0x07, 0x00, 0xF9,
};
// `char const* SaveDataManager::GetMountPoint() const`（`0x4CDD9C`）—— **游戏存档分区的真实挂载点**。
// 这个名字来自它的函数体（两条独立证人）：
//   ① `0x4CDD9C adrp x0, 0x892000; 0x4CDDA0 add x0, x0, #0x7E3` ⇒ 返回字面量 `0x8927E3`，
//      `Repentance.nro` 该处逐字节为 `"sdmc:/"`；
//   ② `SaveDataManager::Initialize`（`0x4CD95C`）把同一个虚函数槽（`ldr x8,[x19]; ldr x8,[x8,#0x30]`
//      ⇒ `R_AARCH64_JUMP_SLOT` 指向本函数）取回来的字符串用 `strstr(…, ":/")` 截断成 `"sdmc"`，
//      再 `0x4CDA54/0x4CDA74 bl nn::fs::MountSaveData(截断后的名字, uid)`。
// **由此可知**：游戏嘴里的 `sdmc:` **不是真 SD 卡**，而是它自己的存档分区 —— 我们第一轮探针把
// `"sdmc:/SaltySD/plugins/<title>/"` 当挂载点传进去，路径实际落在了存档里，所以三个用例全"打开失败"。
// 顺带解释了更早那次 `nn::fs::OpenFile` 上的 `nn::diag::Abort`（结果码 `0x2EE802`）：
// 那是 `fs::ResultInvalidCharacter`（6004，非法路径字符）——把一个带 `:` 的完整路径当相对名字传了。
inline constexpr uintptr_t kSaveDataManagerGetMountPointOffset = 0x4CDD9C;
inline constexpr std::array<u8, 16> kSaveDataManagerGetMountPointExpectedBytes = {
    0x20, 0x1E, 0x00, 0xB0, 0x00, 0x8C, 0x1F, 0x91,
    0xC0, 0x03, 0x5F, 0xD6, 0xFD, 0x7B, 0xBF, 0xA9,
};
// 两个 `nn::fs` 的 **导入跳板**（我们没有 `nn::fs` 的符号表，只有游戏自己的 `.got` 槽与跳板）：
//   * `0x680200` = `bool nn::fs::IsMounted(char const* mountName)`（槽 `0xAA6068`）；
//   * `0x680220` = `Result nn::fs::CommitSaveData(char const* mountName)`（槽 `0xAA6078`）。
// 证据：`tools/nro_symbols.py` 的 `parse_dynamic_relocations()` 给出这两个槽的
// `R_AARCH64_JUMP_SLOT` 记录（符号名即上面两条），跳板本身是
// `adrp x16, …; ldr x17, [x16, #imm]; add x16, x16, #imm; br x17`（16 字节，见下面的守卫字节）。
// `CommitSaveData` 这一步不是可选的：Switch 的存档是"提交式"的，写完不提交，重启后可能什么都看不到
// （游戏自己的 `SaveDataManager::commit_save_data()`（`0x4CDD94`）就是 `ldr x0,[x0,#0x10]`（挂载名）
// 之后 `b 0x680220`）。
inline constexpr uintptr_t kFilesysIsMountedThunkOffset = 0x680200;
inline constexpr std::array<u8, 16> kFilesysIsMountedThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xD0, 0x11, 0x36, 0x40, 0xF9,
    0x10, 0xA2, 0x01, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysCommitSaveDataThunkOffset = 0x680220;
inline constexpr std::array<u8, 16> kFilesysCommitSaveDataThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xD0, 0x11, 0x3E, 0x40, 0xF9,
    0x10, 0xE2, 0x01, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};

// ---- 直连 `nn::fs` 的整组导入跳板（2026-09-16 第三轮探针新增）----
//
// 为什么直连：走引擎 `File` 类要跟它的缓冲/流模式语义打交道（第二轮 `Close()` 的返回类型其实是
// `void`，我们把它的垃圾返回值当 bool 读，才得出假的"关闭失败"）；直连 `nn::fs` 每一步都有
// `Result` 码（0 = 成功），没有缓冲层，也没有对象状态。
//
// 每个函数的名字与签名都由**引擎自己的调用点**反推（不是猜的）：
//   * `OpenFile(FileHandle* out, char const* path, int mode)`（`0x4CD374`，`0x4CCD78`：读传 1、写传 6）；
//   * `CreateFile(char const* path, s64 size)`（`0x4CD384`：`x0 = 拼好的路径`、`x1 = 1`）；
//   * `WriteFile(FileHandle, s64 offset, void const* data, size_t size, WriteOption const& option)`
//     （`0x4CD26C`：`x4 = 栈上清零的 4 字节 option`）；
//   * `SetFileSize(FileHandle, s64)`（`0x4CD2AC`：写完把位置当新长度设回去，所以第二轮
//     `GetLength()` 才等于 27）；
//   * `ReadFile(u64* outSize, FileHandle, s64 offset, void* buffer, size_t size)`（`0x4CD1FC`）；
//   * `GetFileSize(s64* outSize, FileHandle)`、`FlushFile(FileHandle)`、`CloseFile(FileHandle)`
//     （`File::Exists` 用过 `CloseFile`：`0x4CCD30`）。
// 槽地址与跳板地址的对应关系来自 `tools/nro_symbols.py` 的 `parse_dynamic_relocations()`。
// Directory imports use the game's existing filesystem session. Unlike the
// content-manager wrapper, these return an error when a directory is absent.
inline constexpr uintptr_t kFilesysOpenDirectoryThunkOffset = 0x67FFB0;
inline constexpr std::array<u8, 16> kFilesysOpenDirectoryThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xD0, 0x11, 0xA2, 0x47, 0xF9,
    0x10, 0x02, 0x3D, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysReadDirectoryThunkOffset = 0x67FFD0;
inline constexpr std::array<u8, 16> kFilesysReadDirectoryThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xD0, 0x11, 0xAA, 0x47, 0xF9,
    0x10, 0x42, 0x3D, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysCloseDirectoryThunkOffset = 0x67FFE0;
inline constexpr std::array<u8, 16> kFilesysCloseDirectoryThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xD0, 0x11, 0xAE, 0x47, 0xF9,
    0x10, 0x62, 0x3D, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysOpenFileThunkOffset = 0x680060;
inline constexpr std::array<u8, 16> kFilesysOpenFileThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xB0, 0x11, 0xCE, 0x47, 0xF9,
    0x10, 0x62, 0x3E, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysCreateFileThunkOffset = 0x680110;
inline constexpr std::array<u8, 16> kFilesysCreateFileThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xB0, 0x11, 0xFA, 0x47, 0xF9,
    0x10, 0xC2, 0x3F, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysWriteFileThunkOffset = 0x6800F0;
inline constexpr std::array<u8, 16> kFilesysWriteFileThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xB0, 0x11, 0xF2, 0x47, 0xF9,
    0x10, 0x82, 0x3F, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysReadFileThunkOffset = 0x6800E0;
inline constexpr std::array<u8, 16> kFilesysReadFileThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xB0, 0x11, 0xEE, 0x47, 0xF9,
    0x10, 0x62, 0x3F, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysSetFileSizeThunkOffset = 0x680100;
inline constexpr std::array<u8, 16> kFilesysSetFileSizeThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xB0, 0x11, 0xF6, 0x47, 0xF9,
    0x10, 0xA2, 0x3F, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysFlushFileThunkOffset = 0x6800C0;
inline constexpr std::array<u8, 16> kFilesysFlushFileThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xB0, 0x11, 0xE6, 0x47, 0xF9,
    0x10, 0x22, 0x3F, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysGetFileSizeThunkOffset = 0x6800D0;
inline constexpr std::array<u8, 16> kFilesysGetFileSizeThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xB0, 0x11, 0xEA, 0x47, 0xF9,
    0x10, 0x42, 0x3F, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
inline constexpr uintptr_t kFilesysCloseFileThunkOffset = 0x680070;
inline constexpr std::array<u8, 16> kFilesysCloseFileThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xB0, 0x11, 0xD2, 0x47, 0xF9,
    0x10, 0x82, 0x3E, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
// `nn::fs::DeleteFile(char const* path)`（跳板 `0x680210`，槽 `0xAA6070`）：
// 删掉存档里的一个文件。游戏自己不用它（它用 `SaveDataManager::DeleteSaveFile`），
// 但我们清理探针/过期状态文件时需要"按完整路径删"这一个入口。
inline constexpr uintptr_t kFilesysDeleteFileThunkOffset = 0x680210;
inline constexpr std::array<u8, 16> kFilesysDeleteFileThunkExpectedBytes = {
    0x30, 0x21, 0x00, 0xD0, 0x11, 0x3A, 0x40, 0xF9,
    0x10, 0xC2, 0x01, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
// `nn::fs::OpenMode`：读 = 1、写 = 6（`Write|AllowAppend`，引擎两个打开点用的就是这两个值）。
inline constexpr int kVfsOpenModeRead = 1;
inline constexpr int kVfsOpenModeWrite = 6;
// `File` 里那个 `FileStream` 子对象的**流模式**字段：`FileStream` 子对象从 `File+0x38` 开始，
// 它的 `+0x08` 就是模式 ⇒ 在 `File` 里的偏移 = `0x38 + 0x08` = `0x40`。
// 取值：`OpenRead` 写 0、`OpenWrite` 写 1、`Close` 写 2（证据：`FileStream::OpenRead 0x4CD47C`
// 的 `str wzr,[x0,#0x8]`、`FileStream::OpenWrite 0x4CD4B4` 的 `mov w8,#0x1; str w8,[x0,#0x8]`、
// `FileStream::Close 0x4CD500` 的 `mov w8,#0x2; str w8,[x0,#0x8]`）。
// `write_stream_data`/`read_stream_data` 的前置检查（`0x4CD230 cmp w9,#0x1`、`0x4CD1C0 cbz w9`）
// 正好按这个字段判方向 —— 所以"写完再读"必须换一个**新构造**的 `File`。
inline constexpr std::size_t kFilesysFileStreamModeOffset = 0x40;

// The engine clears and rebuilds the whole table on content reload, so a Mod mount
// point has to be re-registered every time this function returns.
inline constexpr uintptr_t kRebuildContentMountPointsOffset = 0x3B3510;
inline constexpr std::array<u8, 16> kRebuildContentMountPointsExpectedBytes = {
    0xFF, 0x43, 0x02, 0xD1, 0xFD, 0x7B, 0x06, 0xA9,
    0xFD, 0x83, 0x01, 0x91, 0xF5, 0x3B, 0x00, 0xF9,
};
// The Mod root prefix the Runtime addresses (`rom:/isaac_mods/mods/`); the content
// mount adapter strips the application prefix before handing a path to the engine,
// whose own path constructor adds it back.
inline constexpr char kModAddressRootPrefix[] = "rom:/isaac_mods/mods/";

// ============================================================================
// 批次 363（2026-10-04）：模组覆盖本体资源的最后一环 —— `ANM2::Load` 入口中继
// ============================================================================
//
// **问题**：引擎开机时自己就把 `gfx/ui/minimap1.anm2` 这类**共享路径**按"本体层"
// （`rp_patch/resources` 前缀）读进了动画缓存；我们的模组挂载点是约 5 秒后才追加的。
// `AnmCache::Load2`（`0xF570`）的查找是"挂载点前缀 + 路径哈希、**第一个命中的键胜出**"
// ⇒ 之后每一次 `Load`（包括 minimapi 自己那次）都命中那份本体旧条目、**连路径解析器都不问**
// ⇒ 模组自带的那份永远赢不了。真机读数：共享路径末帧 11（本体 13 帧）、模组独有路径末帧 12
// （模组 14 帧）、`minimap1.anm2` 的解析次数 0。
//
// **修法**：在 `ANM2::Load` 入口加一层中继 —— 先问解析器这条路径现在归谁；答模组层且缓存里
// 确实还有旧条目时，用引擎自己的原语把它作废（`RemoveReference` 按读到的计数减到 0 ⇒
// `FreeUnreferencedEntries`），再原样跑原函数 ⇒ 不命中 ⇒ `Preload2` 开文件 ⇒ 解析器给模组那份。
//
// ★ 靶点入口**不自造新常量**：它就是上面 `kSpriteLoadOffset`（`0xC970`）那一个函数 ——
//   `kSpriteLoadExpectedBytes` 与本批需要的 16 字节**逐字节相同**。
//   2026-10-04 用符号表复核确认：`0xC970` 的 mangled 名是
//   `_ZN15IsaacRepentance4ANM24LoadERKNSt3__112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEEb`
//   ⇒ `IsaacRepentance::ANM2::Load(std::__1::string const&, bool)`。
//   也就是说仓库里一直叫的 `Sprite:Load`（Lua 侧 `Sprite:Load` 就是它）**本体就是 `ANM2::Load`** ——
//   同一个地址、同一个函数，只是从哪一侧看而已。一个地址只留一个名字，避免两份守卫将来各改各的。
//   （`python3 tools/gen_engine_symbol_signatures.py` 会把这条 mangled 名记进签名表，可复核。）
//
// ABI 形状（挂钩时必须逐字对上）：
//   * x0 = `this`（ANM2 对象，0x158 字节）；
//   * x1 = **libc++ 的 24 字节 `std::string`**（本模块编的是 libstdc++ 的 32 字节，不能直接互传）；
//   * w2 = `loadGraphics`。

// `AnmCache::RemoveReference(std::string const&)`（`0x14CC4`）：按路径把**每个存在的挂载点键**
// 的引用计数减 1。★ 计数为 0 时它**先打日志再减**（`0x14E3C`–`0x14E5C`）⇒ 会下溢成 0xFFFFFFFF，
// 所以调用方**必须先自己读计数**，只在 > 0 时按读到的数减。
inline constexpr uintptr_t kAnmCacheRemoveReferenceOffset = 0x14CC4;
inline constexpr std::array<u8, 16> kAnmCacheRemoveReferenceExpectedBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFC, 0x6F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};

// `AnmCache::FreeUnreferencedEntries()`（`0x14F64`）：把引用计数为 0 的条目
// `Entry2::FreeMemory()` 之后从 map 里 `__tree_remove` 删掉（`0x14FCC`–`0x1508C`）。
// 引擎自己在换语言（`PerformLanguageSwitch` `0x3B3A28`）、选项菜单、`ModManager::Reset`、
// 控制台命令四处调用它 —— 这条路径是引擎自己走熟了的。
inline constexpr uintptr_t kAnmCacheFreeUnreferencedEntriesOffset = 0x14F64;
inline constexpr std::array<u8, 16> kAnmCacheFreeUnreferencedEntriesExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};

// `g_AnmCache`（`0xAAC6A0`）：`std::__1::map<uint32_t, Entry2>`（libc++ 红黑树）。
// ★★ 2026-10-05（批次 367）**更正**：以前这里写的是"`+0x00` 左哨兵、`+0x08` 根哨兵"，
//   而按那个口径写的查找**多解引用了一层**（把已经是根的东西又当成哨兵去取左孩子）
//   ⇒ 从根的左孩子开始查、永不比较根自己 ⇒ 大多数键查不到（真机：中继被调 178 次、
//   问解析器 0 次）。正确的布局是：
//   * map 对象：`+0x00` = `__begin_node_`（最左节点）；**`+0x08` 就是"结束哨兵"本身**，
//     它的 `__left_`（= 直接读 `[map+0x08]` 得到的那个值）**就是根节点指针**；空树时指向自己。
//   * 节点：`+0x00` 左、`+0x08` 右、`+0x10` 父、`+0x20` 键（u32 哈希）、`+0x88` 引用计数（u32）。
//   出处：`Load2` `0xF6D0`（`ldr x8,[x27]`，`x27 = this+8`）、
//         `AddReference` `0x14C34`（同形；命中时 `0x14C74` `ldr w9,[x8,#0x88]` + `add #1` + `str`）、
//         `FreeUnreferencedEntries` `0x14FAC`（`ldr w8,[x21,#0x88]` 判 0；中序走 `+8`/`+0x10`）。
inline constexpr uintptr_t kAnmCacheGotSlotOffset = 0xAAC6A0;
inline constexpr std::size_t kAnmCacheMapRootSentinelOffset = 0x08;
inline constexpr std::size_t kAnmCacheNodeLeftOffset = 0x00;
inline constexpr std::size_t kAnmCacheNodeRightOffset = 0x08;
inline constexpr std::size_t kAnmCacheNodeKeyOffset = 0x20;
inline constexpr std::size_t kAnmCacheNodeRefCountOffset = 0x88;

// ★★ 节点布局的**形状守卫**（批次 367）：`FreeUnreferencedEntries` 里那 16 字节 ——
//   `ldr w8,[x21,#0x88]`（引用计数在 +0x88）+ `cbz` + `ldr x8,[x21,#0x8]`（右孩子在 +0x08）+ `cbz`。
// 配合上面 `kAnmCacheMountLoopExpectedBytes`（挂载点表元素 8 字节）一起，把"我们读引擎缓存
// 时依赖的那几个偏移"钉成**从镜像里读字节**的门禁：引擎换了形状就在宿主机上报红。
inline constexpr uintptr_t kAnmCacheNodeLayoutOffset = 0x14FAC;
inline constexpr std::array<u8, 16> kAnmCacheNodeLayoutExpectedBytes = {
    0xA8, 0x8A, 0x40, 0xB9, 0xE8, 0x00, 0x00, 0x34,
    0xA8, 0x06, 0x40, 0xF9, 0x28, 0x02, 0x00, 0xB4,
};

// `g_ContentMountPoints`（`0xAAC740`）：挂载点前缀表。★ **元素是 `const char*`（8 字节指针）**，
// 不是 libc++ 的 `std::string`（24 字节）—— 这一条 2026-10-05 才定案，代价是 `ANM2::Load` 中继
// 整整一轮静默失效（详见 `docs/分析-ANM2覆盖链静默失效根因-挂载点表元素类型与两处ABI-20261005.md`）。
// 三处反汇编互证（`Repentance.nro`）：
//   * `AnmCache::Load2`           `0xF638` `add x19, x19, #0x8` + `0xF644` `ldr x2, [x19]`
//   * `AnmCache::AddReference`    `0x14BA0` 同形
//   * `AnmCache::RemoveReference` `0x14D68` 同形
// 元素取出来**直接**喂 `strncpy_s(buf, 256, 元素, 256)`（`0xF654`）⇒ 元素就是一条 C 串的首地址。
// 另外：三个函数都在**列表为空**时才现问 `IContentManager::GetMountPoints` 填一次
// ⇒ 这份缓存是**长期缓存**的（开机那一版），调用方必须自己兜底。
inline constexpr uintptr_t kContentMountPointsGotSlotOffset = 0xAAC740;

// ★★ 形状守卫（2026-10-05，批次 366）：`AnmCache::Load2` 里"遍历挂载点表"那 16 字节 ——
//   `add x19, x19, #0x8`（**步长 8**）+ `cmp x19, x8` + `b.eq` + `ldr x2, [x19]`（**元素当指针用**）。
// 它钉住的是一件结构性的事：引擎的挂载点表元素是 8 字节指针，不是 24 字节的串对象。
// 哪天引擎换了形状（或我们又读错），`runtime/tests/test_anm2_load_override_hook.py` 会在这里报红。
inline constexpr uintptr_t kAnmCacheMountLoopOffset = 0xF638;
inline constexpr std::array<u8, 16> kAnmCacheMountLoopExpectedBytes = {
    0x73, 0x22, 0x00, 0x91, 0x7F, 0x02, 0x08, 0xEB,
    0x80, 0x06, 0x00, 0x54, 0x62, 0x02, 0x40, 0xF9,
};

// Rebuild relay: `RebuildContentMountPoints()` starts with `ClearMountPoints(false)`
// and rebuilds the whole mount point table (base content, add-on content, Rep+ patch),
// so a Mod mount point disappears with every content reload. The relay patches the
// function's **only** `ret` (`0x3B36F4`, verified: one `ret` in the body and every early
// exit funnels into it) with a branch to a stub in the last .text zero page; the stub
// calls a callback published through its own slot and then executes the original `ret`.
// Patching the single return covers all four call sites, one of which is a tail call.
inline constexpr uintptr_t kRebuildMountPointsRelayOffset = 0x3B36F4;
inline constexpr std::array<u8, 16> kRebuildMountPointsRelayExpectedOriginal = {
    0xC0, 0x03, 0x5F, 0xD6, 0xE0, 0x23, 0x40, 0xF9,
    0x05, 0xF1, 0x0A, 0x94, 0xE8, 0x03, 0x40, 0x39,
};
inline constexpr uintptr_t kRebuildMountPointsRelayCodeOffset = 0x68CFA0;
inline constexpr uintptr_t kRebuildMountPointsRelaySlotOffset = 0x68CFC8;
inline constexpr std::array<u8, 4> kRebuildMountPointsRelayExpectedEntry = {
    0x2B, 0x66, 0x0B, 0x14,
};
inline constexpr std::array<u8, 0x30> kRebuildMountPointsRelayExpectedBytes = {
    0xFF, 0x83, 0x00, 0xD1, 0xE0, 0x7B, 0x00, 0xA9,
    0x11, 0x01, 0x00, 0x10, 0x30, 0xFE, 0xDF, 0xC8,
    0x50, 0x00, 0x00, 0xB4, 0x00, 0x02, 0x3F, 0xD6,
    0xE0, 0x7B, 0x40, 0xA9, 0xFF, 0x83, 0x00, 0x91,
    0xC0, 0x03, 0x5F, 0xD6, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};
inline constexpr char kLogDirectory[] = "/atmosphere/logs";
inline constexpr char kLogPath[] = "/atmosphere/logs/isaac-runtime-probe.log";

// --- 接口面补缺一批（2026-09-18 夜，批次 028）------------------------------------------
//
// 这一批接的是**EID 真的在调、而我们没有**的四个成员（判据来自真机报错与 EID 源码引用）。
// 入口地址与 4 字节入口指纹都取自游戏镜像：
// `python3 tools/nro_disasm.py <地址> 0x20`（指纹 = 入口那条指令的整字）。
// 调用方式与 `EntityPlayer:AddCollectible`/`AddCoins` 一族相同：模块基址 + 偏移 + **调用前核对指纹**
// （这些都会真的进引擎，偏移写错就会去调别的函数 ⇒ 指纹不是可选项）。

// `ItemPool::GetPillEffect(ePillColor, Entity_Player*)`（符号
// `_ZN15IsaacRepentance8ItemPool13GetPillEffectENS_10ePillColorEPNS_13Entity_PlayerE`）。
// PC 文档 `ItemPool.md:65`：`PillEffect GetPillEffect(PillColor, EntityPlayer = nil)`。
// ★ 为什么这条最急：EID 在 `features/eid_api.lua:881` 调 `pool:GetPillEffect(SubType, player) + 1`，
// 真机报 `attempt to call a nil value (method 'GetPillEffect')` ⇒ **那颗药的描述整条消失**。
inline constexpr uintptr_t kItemPoolGetPillEffectOffset = 0x3C857C;
inline constexpr std::uint32_t kItemPoolGetPillEffectEntryWord = 0xA9BD7BFDU;

// `ItemPool::GetPoolForRoom(eRoomType, unsigned)`（符号
// `_ZNK15IsaacRepentance8ItemPool14GetPoolForRoomENS_9eRoomTypeEj`；`const` 成员）。
// PC 文档 `ItemPool.md:74`：`ItemPoolType GetPoolForRoom(RoomType, int Seed)`。
// EID 在"这个房间的池子是什么"那条路径上调用它（`features/eid_api.lua` 的链式调用）。
inline constexpr uintptr_t kItemPoolGetPoolForRoomOffset = 0x3C5C7C;
inline constexpr std::uint32_t kItemPoolGetPoolForRoomEntryWord = 0xD10103FFU;

// `Level::GetLastRoomDesc()`（符号 `_ZN15IsaacRepentance5Level15GetLastRoomDescEv`）。
// PC 文档 `Level.md:172`：`const RoomDescriptor GetLastRoomDesc()`。
// 函数体只有 6 条指令，且**尾调用** `Level::GetRoomByIdx(int, int)`：
//   `add x8, x0, #0x2155C` → `ldr w1, [x8]`、`ldr w2, [x8, #0x8]` → `b GetRoomByIdx`
// ⇒ 它读的是"上一个房间"的（索引 `+0x2155C`、维度 `+0x21564`）——正好紧挨着我们早就用着的
// "当前房间"那一对（`+0x21558`/`+0x21560`），互相印证。返回值是 `RoomDescriptor*`，
// 我们用现成的 `PushRoomDescriptor` 把它交给 Lua。
inline constexpr uintptr_t kLevelGetLastRoomDescOffset = 0x3DC69C;
inline constexpr std::uint32_t kLevelGetLastRoomDescEntryWord = 0x5282AB88U;

// `Entity_Pickup::CanReroll()`（符号 `_ZNK15IsaacRepentance13Entity_Pickup9CanRerollEv`）。
// PC 文档 `EntityPickup.md:25`：`boolean CanReroll()`。EID 用它判断"这个掉落物能不能被重掷"。
// ⚠️ 同名的 `Entity_NPC::CanReroll`（`0x11FAF4`）**本批不做**：我们还没有 `EntityNPC` 视图
// （模组拿到的 NPC 是基类 `Entity` 视图）⇒ 加了也调不到，属于"先要有视图"的欠账。
inline constexpr uintptr_t kEntityPickupCanRerollOffset = 0x26AFA8;
inline constexpr std::uint32_t kEntityPickupCanRerollEntryWord = 0x39470C09U;

// --- 回调面补齐（2026-09-20 批次 102）：第 1 期的四个**入口中继**靶点 -------------
//
// 这四条都是"引擎在事件发生的那一刻调用"的函数，我们用入口中继（零占洞：只改目标函数入口
// 的 16 字节、跳到本模块自己竞技场里的槽）挂它们。16 字节必须是**目标函数真实序言的前
// 16 字节**（`entry_relay` 会把它们原样搬进槽里回放），且不许含 PC 相对指令 ——
// 由 `runtime/tests/test_entry_relay_ledger.py` 对着 NRO 逐字节核对。
//
// 四个靶点的选法与实参映射的依据（本地符号表 `dist/.tmp-demangle/symbols.json` +
// `analysis/isaacdocs-snapshot` 的 PC 文档 + `tools/nro_disasm.py` 反汇编）：
//   * `Entity_Player::UseActiveItem(eCollectibleType /*w1*/, unsigned /*w2*/, int /*w3*/,
//     int /*w4*/)` —— PC 的 Lua 签名是
//     `UseActiveItem(CollectibleType Item, UseFlags UseFlags = 0, ActiveSlot Slot = -1,
//     int CustomVarData = 0)`（`EntityPlayer.md:1853`）⇒ w2 = UseFlags、
//     w3 = ActiveSlot、w4 = CustomVarData。反汇编印证：函数体开头就是
//     `and w20, w2, #0x1`（= `UseFlags & USE_NOANIM`，`UseFlag.md`：`USE_NOANIM = 1 << 0`）。
//   * `Entity_Player::UseCard(eCard /*w1*/, unsigned /*w2*/)` —— PC：
//     `UseCard(Card ID, UseFlags UseFlags = 0)`（`EntityPlayer.md:1865`）⇒ w2 = UseFlags。
//   * `Entity_Player::UsePill(ePillEffect /*w1*/, ePillColor /*w2*/, unsigned /*w3*/)` ——
//     PC 的 `MC_USE_PILL` 只给 `(PillEffect, EntityPlayer, UseFlags)`，所以 w3 = UseFlags；
//     反汇编印证：w2 进 `and w9, w21, #0x7ff`（药丸颜色掩码）、w3 另有去处。
//   * `Game::Exit(bool)` —— PC 的 `MC_PRE_GAME_EXIT` 只有 `(ShouldSave [bool])` 一个实参。
inline constexpr uintptr_t kEntityPlayerUseActiveItemOffset = 0x30653C;
inline constexpr std::array<u8, 16> kEntityPlayerUseActiveItemExpectedBytes = {
    0xEF, 0x3B, 0xB6, 0x6D, 0xED, 0x33, 0x01, 0x6D,
    0xEB, 0x2B, 0x02, 0x6D, 0xE9, 0x23, 0x03, 0x6D,
};
inline constexpr uintptr_t kEntityPlayerUseCardOffset = 0x2E9040;
inline constexpr std::array<u8, 16> kEntityPlayerUseCardExpectedBytes = {
    0xEE, 0x0F, 0x16, 0xFC, 0xED, 0x33, 0x01, 0x6D,
    0xEB, 0x2B, 0x02, 0x6D, 0xE9, 0x23, 0x03, 0x6D,
};
inline constexpr uintptr_t kEntityPlayerUsePillOffset = 0x2DFC04;
inline constexpr std::array<u8, 16> kEntityPlayerUsePillExpectedBytes = {
    0xEC, 0x0F, 0x17, 0xFC, 0xEB, 0x2B, 0x01, 0x6D,
    0xE9, 0x23, 0x02, 0x6D, 0xFD, 0x7B, 0x03, 0xA9,
};
inline constexpr uintptr_t kGameExitOffset = 0x3512F4;
inline constexpr std::array<u8, 16> kGameExitExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF8, 0x5F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};

// `Entity_Pickup::handle_collision(Entity*, bool)`（符号
// `_ZN15IsaacRepentance13Entity_Pickup16handle_collisionEPNS_6EntityEb`）——批次 103 的
// `MC_PRE_PICKUP_COLLISION` 靶点。反汇编（`tools/nro_disasm.py 0x271F2C 0x80`）确认实参：
// `x0` = 掉落物自身、`x1` = 碰它的那个实体（EID 的处理器读 `collider.Type`）、`w2` = `low`
// （PC 文档：`true` 表示"掉落物先撞上对方"，`false` 表示"对方先撞上掉落物"）。
//
// PC 的返回值是三态（`ModCallbacks.md`）：`true` = 忽略这次碰撞、`false` = 算碰撞但**不执行**
// 内部代码、`nil` = 照常执行内部代码 ⇒ 我们只区分"非 nil ⇒ 不跑原函数"（第三态照跑）。
inline constexpr uintptr_t kEntityPickupHandleCollisionOffset = 0x271F2C;
inline constexpr std::array<u8, 16> kEntityPickupHandleCollisionExpectedBytes = {
    0xFF, 0x83, 0x07, 0xD1, 0xEA, 0xB3, 0x00, 0xFD,
    0xE9, 0x23, 0x17, 0x6D, 0xFD, 0x7B, 0x18, 0xA9,
};

// `Room::spawn_entity(unsigned GridIndex, RoomConfig::Entry const&, unsigned Seed,
// Entity**, bool)`（符号 `_ZN15IsaacRepentance4Room12spawn_entityEjRKNS_10RoomConfig5EntryEjPPNS_6EntityEb`）
// —— 批次 104 的 `MC_PRE_ROOM_ENTITY_SPAWN`(71) 靶点。
//
// ★ 实参映射是**逐项坐实**的（不是猜；反汇编 + 重定位表，2026-09-20）：
//
//  1. **这个函数没有直接调用者** —— Repentance.nro 里既没有 `bl`、也没有取地址。原因是这些
//     NRO 是 **PIC 共享对象**：模块内部调用**导出**符号也要走 PLT。顺着
//     `R_AARCH64_JUMP_SLOT`（jmprel 里 `spawn_entity` 的 GOT 槽 `0xA9EB18`）找到 PLT 桩
//     `0x671760`，再扫 `bl` 到该桩 ⇒ **5 个调用点**：`0x401A8`、`0x35BB18`、`0x45D034`、
//     `0x46C7EC`、`0x488C00`（后三个是"遍历房间生成表、逐条生成"的循环体）。
//  2. `0x45D034` / `0x46C7EC` 两处的调用序列一致：`w1` = 循环下标、`x2` = 一个 12 字节条目
//     的指针、`w3` = 调用者自己的一个 4 字节局部、`x4 = nullptr`、`w5 = 0`。
//  3. `w1` = **GridIndex**：函数体内 `udiv w21, w19, w8` + `msub w19, w21, w8, w19`
//     （= 拿 w1 按房间宽度拆成行/列），并且它被原样传给 `Room::FixSpawnEntry`。
//  4. `w3` = **Seed**：函数入口用它构造 `RNG(seed, 35)`（PLT 调用解析出来是
//     `_ZN15IsaacRepentance3RNGC1Ejj`），并且和 `w1` 一起传给 `FixSpawnEntry`。
//  5. `x2` = `RoomConfig::Entry const&`：函数先把它的**前 12 字节**拷到栈上，再以
//     "可写引用"传给 `Room::FixSpawnEntry(Entry&, unsigned, unsigned)`（所以必须先拷贝）。
//     ⇒ 我们在**函数入口**派发，拿到的正是"引擎自然替换**之前**"的 Type/Variant/SubType
//     —— 与 PC 文档一致（"Returning such a table will override any replacements that might
//     naturally occur" ⇒ 回调本来就发生在替换之前）。
//  6. `x4` = `Entity**` 出参、`w5` = bool：本轮用不到（我们只派发，不接管生成）。
//
// ⚠️ 一个与 PC 文档**不一致**的地方（记在明处）：PC 的 `RoomConfig::Entry` 是
// `{int Subtype; int Type; int Variant; float Weight}`（16 字节、三个都是 `int`），
// 而这个构建里**不是**那个形状 —— `Room::FixSpawnEntry` 与 `RoomConfig::Spawn::PickEntry`
// 两处独立证据都显示：`Type` 是 32 位、`Variant`/`SubType` 是 **16 位**：
//   * `FixSpawnEntry`：`ldr w8,[x19]` 后 `cmp w8,#5`（`EntityType.PICKUP`）/`#6`（`SLOT`）
//     ⇒ `[+0]` 是 `Type`；随后 `ldrh w8,[x19,#4]`、`cmp w8,#0x12d`、`strh #0x12c,[x19,#4]`
//     ⇒ `[+4]` 是 16 位的**变体**（能改写成另一个变体）；另有 `strh w0,[x19,#6]` ⇒ `[+6]` 是 16 位。
//   * `Spawn::PickEntry`：`ldr w2,[x8]`（32 位）+ `ldrh w3,[x8,#4]` + `ldrh w4,[x8,#6]`
//     —— 同一组三连读，宽度也一致。
inline constexpr uintptr_t kRoomSpawnEntityOffset = 0x453918;
inline constexpr std::array<u8, 16> kRoomSpawnEntityExpectedBytes = {
    0xFF, 0x83, 0x03, 0xD1, 0xEB, 0x2B, 0x07, 0x6D,
    0xE9, 0x23, 0x08, 0x6D, 0xFD, 0x7B, 0x09, 0xA9,
};
// `RoomConfig::Entry` 的前三个字段（证据见上面那段：两条独立的三连读）。
inline constexpr uintptr_t kRoomConfigEntryTypeOffset = 0x00;     // i32：`EntityType`
inline constexpr uintptr_t kRoomConfigEntryVariantOffset = 0x04;  // i16（**不是** i32！）
inline constexpr uintptr_t kRoomConfigEntrySubTypeOffset = 0x06;  // i16（**不是** i32！）

// ---------------------------------------------------------------------------
// 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG`(11) 的四条入口中继挂点
// ---------------------------------------------------------------------------
// 契约（`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md:313-325`）：
// 「Called before new damage is applied.」实参 `(Entity, Amount[float], DamageFlags[int],
// Source[EntityRef], CountdownFrames[int])`，可选实参（过滤器）= `EntityType`；
// ★ 返回值口径：**返回 `false` 才取消这次伤害**（`true`/`nil` 都照常受伤）——
//   所以派发侧不能只判"真值"，要判"返回过非 nil 且不真"（见 `DispatchEntityTakeDamage`）。
//
// **为什么要挂四条、而不是只挂作业单写的 `Entity::TakeDamage` 一处**
// （2026-10-07 用 `tools/nro_disasm.py` 逐段反汇编定案）：
//   * 引擎里只有基类 `Entity::TakeDamage` 一份"通用受伤"实现；
//   * 子类**不一定回跳基类**：
//       - `Entity_NPC::TakeDamage`(0x122224) 入口第二条就 `bl` 基类（0x122254）✓；
//       - `Entity_Familiar::TakeDamage`(0xD8550) 在 0xD8960 调基类 ✓；
//       - `Entity_Player::TakeDamage`(0x2A34D0) / `Entity_Pickup::TakeDamage`(0x2767B8) /
//         `Entity_Slot::TakeDamage`(0x32FFB0) 全长扫 0x4000 字节**一次都没调基类**。
//   ⇒ 只挂基类会**漏掉玩家/掉落物/槽位受伤**。语料 6 个模组里 Trinity 的五个处理器全带
//     `EntityType.ENTITY_PLAYER` 过滤器 ⇒ 漏玩家等于这条回调整体没接上。
//   ⇒ 精确覆盖 = **4 条**：基类（覆盖 NPC/跟班/一切不覆写 TakeDamage 的实体）
//     + 玩家 + 掉落物 + 槽位。**不重复**：NPC/跟班不在子类入口挂，只在基类收一次。
//
// 实参映射（按目标 ABI 逐字对，反汇编核对）：
//   `TakeDamage(float Amount, unsigned long DamageFlags, EntityRef const& Source, int Countdown)`
//   ⇒ x0 = this（实体）、s0 = Amount、x1 = DamageFlags、x2 = &Source、w3 = CountdownFrames。
// 16 字节守卫都是纯 `sub`/`stp`/`str`/`mov`，**无 PC 相对指令**（入口中继要求可整体搬走回放）。
// 偏移不在这里重复定义 —— 用上面「批次 065」那一段已有的 `kEntityTakeDamageOffset`
// （同一个值 `0x5DCA4`，那边还有它的入口字与"为什么两条都要"的说明）。
inline constexpr std::array<u8, 16> kEntityTakeDamageExpectedBytes = {
    0xFF, 0x43, 0x03, 0xD1, 0xE8, 0x43, 0x00, 0xFD,
    0xF9, 0x4F, 0x00, 0xF9, 0xFD, 0xFB, 0x08, 0xA9,
};
// 偏移同样用「批次 065」已有的 `kEntityPlayerTakeDamageOffset`（`0x2A34D0`）。
inline constexpr std::array<u8, 16> kEntityPlayerTakeDamageExpectedBytes = {
    0xFF, 0xC3, 0x07, 0xD1, 0xED, 0x33, 0x16, 0x6D,
    0xEB, 0x2B, 0x17, 0x6D, 0xE9, 0x23, 0x18, 0x6D,
};
inline constexpr uintptr_t kEntityPickupTakeDamageOffset = 0x2767B8;
inline constexpr std::array<u8, 16> kEntityPickupTakeDamageExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x20, 0x20, 0x1E,
};
inline constexpr uintptr_t kEntitySlotTakeDamageOffset = 0x32FFB0;
inline constexpr std::array<u8, 16> kEntitySlotTakeDamageExpectedBytes = {
    0xFF, 0xC3, 0x02, 0xD1, 0xEC, 0x13, 0x00, 0xFD,
    0xEB, 0x2B, 0x03, 0x6D, 0xE9, 0x23, 0x04, 0x6D,
};

// ---------------------------------------------------------------------------
// 批次 396（2026-10-07）：`MC_EVALUATE_CACHE`(8) 的入口中继挂点
// ---------------------------------------------------------------------------
// 契约（`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md`）：玩家属性（缓存）重算时
// 触发，实参 `(EntityPlayer, CacheFlag)`、返回 void，可选实参（过滤器）= `CacheFlag`。
//
// 靶点 = `Entity_Player::EvaluateItems()` @ `0x280804`（符号
// `_ZN15IsaacRepentance13Entity_Player13EvaluateItemsEv`）——本版引擎"属性重算"的**唯一总闸**：
// 它一次读出 `Entity_Player + 0x1958` 那张 CacheFlag 掩码（`kEntityPlayerCacheFlagsOffset`），
// 再用一串 `tbnz/tbz` 逐位内联重算。旁证：`Entity_Player::DonateLuck` 就是"置 `+0x1958` bit10
// 后 `b EvaluateItems`"。
//
// ⚠️ 与 PC 的一个落差（记在明处，偏离台账同步登记）：**入口不带 CacheFlag 实参** ——
// 本版把每 bit 的重算内联进了 `EvaluateItems`，没有可单独挂的 `EvaluateCache(CacheFlag)`。
// 所以中继自己快照 `[x0+0x1958]`、枚举置位、每个 bit 派发一次（过滤值 = 该 bit）。
// ★ 重入（批次 405 更正 396 的旧措辞）：`EvaluateItems` 会为同屏第二个玩家递归调用自己
//   （`0x28bc0c bl EvaluateItems`，走 PLT ⇒ 也进我们这条中继）。这是**刻意的、不加防重入**：
//   内层那次是**另一个玩家**，本来就该各派发一次 —— 若加个布尔守卫，第二个玩家的回调会被静默吞掉。
//   详见 `hook_manager.cpp` 的 `EntryRelayEvaluateItemsCallback`。
// 16 字节守卫 = 4 条 `stp`，无 PC 相对指令。
// 偏移不重复定义 —— 用上面「批次 238」那一段已有的 `kEntityPlayerEvaluateItemsOffset`
// （同一个值 `0x280804`，那边还有它的入口字与 Lua API 行）。
inline constexpr std::array<u8, 16> kEntityPlayerEvaluateItemsExpectedBytes = {
    0xEF, 0x3B, 0xB6, 0x6D, 0xED, 0x33, 0x01, 0x6D,
    0xEB, 0x2B, 0x02, 0x6D, 0xE9, 0x23, 0x03, 0x6D,
};

// ---------------------------------------------------------------------------
// 批次 397（2026-10-07）：补全回调（第 2 批）—— 三条 `hookable` 的新入口中继
// ---------------------------------------------------------------------------
// 三条的 PC 契约原文（`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md`）：
//   * `MC_POST_ENTITY_KILL`(68)：「Called **right before a death animation is triggered**
//     for an Entity.」PC Entity::Kill @0x6848B0 先置死亡标记、执行血花，再在
//     @0x6848E3 调用回调68包装 @0x802C50。中继必须在原函数完成后派发，允许复活。
//   * `MC_POST_NPC_DEATH`(29)：「Gets called **after the Death animation is played**.」
//     ⇒ `Entity_NPC::trigger_death_remove()` 是"死亡动画播完之后"的那个汇合点。
//   * `MC_POST_GAME_END`(16)：「called when the game over screen appears, or when an ending
//     starts playing. The boolean value is **true when you died and got a game over**,
//     false when you won and got an ending.」⇒ 挂 `Game::End(eEnding)`，`IsGameOver` 由 `eEnding` 推。
//
// **`MC_POST_ENTITY_KILL` 为什么只挂基类一条**（2026-10-07 反汇编定案，与批次 396 的
// `TakeDamage` 相反）：全符号表里覆写 `Kill` 的只有两个类，而**两个都回跳基类** ——
//   * `Entity_NPC::Kill`(0x10B36C) 做完自己的 `DamageEntry` 赋值后在 0x10B3AC **尾调用**
//     `Entity::Kill`（`b 0x6733A0`，PLT 桩）；
//   * `Entity_Familiar::Kill`(0xAD85C) 同样调基类。
//   其余实体类没有自己的 `Kill`，走基类 vtable 槽 ⇒ **挂基类即全覆盖、且不重复**。
//   （旁证：批次 319 把 Lua 侧 `Entity:Kill()` 改成走虚调用 `kEntityVtableKillSlot`，理由同一条。）
//
// **`Game::End` 的 `IsGameOver` = `(eEnding == 1)`，两项独立证据**：
//   ① `0x350E4C cmp w19,#1; b.ne …` → `0x350EB0 b Manager::RecordLoss` —— 只有 `eEnding==1`
//      这一条路通向"记一次失败"；
//   ② `PlayerManager::NotifyDead` 在 `0x440544 mov w1,#1` 之后 `0x440558 b Game::End`
//      —— 玩家死亡这条链传的就是 `1`。
//   与契约原文「true when you died」一致。★ 这一条**是本批唯一跨函数推断出来的取值**，
//   上卡时要用只读探针确认（打一局死一次，看回调收到的 bool 是不是 true）。
//
// 三条的返回都是 **void**（尾部 `ret`，没有写 `w0`；`trigger_death_remove` 的尾部是
// `0x11A3CC ret`、`Game::End` 的尾部是 `0x351060 ret`）。16 字节守卫全是 `sub`/`stp`/`str`/`mov`，
// **无 PC 相对指令**（入口中继要求可整体搬走回放）。
inline constexpr std::array<u8, 16> kEntityKillExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x0C, 0x47, 0x39,
};
// 偏移不重复定义 —— 用上面「批次 319」那一段已有的 `kEntityKillOffset`（`0x5C8E0`）。
inline constexpr uintptr_t kEntityNpcTriggerDeathRemoveOffset = 0x1199D8;
inline constexpr std::array<u8, 16> kEntityNpcTriggerDeathRemoveExpectedBytes = {
    0xFF, 0x03, 0x04, 0xD1, 0xEB, 0x2B, 0x08, 0x6D,
    0xFB, 0x5B, 0x00, 0xF9, 0xE9, 0x23, 0x09, 0x6D,
};
inline constexpr uintptr_t kGameEndOffset = 0x350DE4;
inline constexpr std::array<u8, 16> kGameEndExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};

// `MC_POST_FIRE_TEAR`(61)：靶点 = `Entity_Player::FireTear(...)` @ `0x2A991C`（偏移常量与
// **整套 ABI 取证**在上面「批次 337」那一大段里 —— 那边是给 Lua API `EntityPlayer:FireTear`
// 手写转发用的，结论一字不差：`(Vector2 const& Position /*x1*/, Vector2 Velocity /*HFA s0,s1*/,
// u32 flags /*w2*/, Entity* Source /*x3*/, float DamageMultiplier /*s2*/)`，返回 `Entity_Tear*`）。
// 契约原文：「Called when the player fires a tear. … In Repentance, it works for tears fired
// with Incubus.」—— 引擎里 Incubus 那条路（`Weapon::FireTear` 取 `[familiar+0x400]` 当 owner）
// **也汇入同一个函数** ⇒ 与契约一致（本批用 4 个调用点 + 被调函数内部用法逐条核过形状）。
// ★ 返回值是泪弹指针 ⇒ 派发点必须在**原函数返回之后**（先跑原函数、拿 x0，再派发）。
// 16 字节守卫 = `sub`/`str`/`stp`/`add`，无 PC 相对指令。
inline constexpr std::array<u8, 16> kEntityPlayerFireTearExpectedBytes = {
    0xFF, 0x83, 0x03, 0xD1, 0xE8, 0x4B, 0x00, 0xFD,
    0xFD, 0x7B, 0x0A, 0xA9, 0xFD, 0x83, 0x02, 0x91,
};

//: `KAGE::Math::Vector2` 在**按值**传参时的 ABI 形状（两个 float ⇒ HFA，走 `s0`/`s1`）。
//: ★ 与 `isaac_api.cpp` 里批次 337 的 `EngineVector2Abi` 是**同一形状**（那边是手写转发用的
//: 局部结构体）；两处必须逐字一致 —— 都用来把 `FireTear` 的 `Velocity` 按值送进 `s0:s1`。
struct RelayVector2Hfa {
    float x;
    float y;
};
static_assert(sizeof(RelayVector2Hfa) == 8 && alignof(RelayVector2Hfa) == 4,
              "Vector2 按值必须正好是两个 float（否则 HFA 规则不成立、不会走 s0/s1）");

// ---------------------------------------------------------------------------
// 贴图桥：`KAGE::Graphics::ImagePcx::Load(char const*)` 入口中继挂点
// ---------------------------------------------------------------------------
// 拦截引擎加载 `.pcx` 贴图的最后一站。回调里先让原函数跑（`.pcx` 在则正常返回）；
// 当它因「文件不存在」失败、但同名 `.png` 存在时，在内存里把 PNG 转成 PCX 字节
// 喂给内存版 `Load`（见下 `kImagePcxLoadInMemoryFileOffset`）。
//
// 靶：`_ZN4KAGE8Graphics8ImagePcx4LoadEPKc`（单参 const char*）。
// 守卫字节由 `tools/nro_disasm.py 0x4d40a8 16` 抽查（2026-09-21，小端文件字节序）：
//   stp x29,x30,[sp,#-0x40]! / str x23,[sp,#0x10] / mov x29,sp / stp x22,x21,[sp,#0x20]
//   显示 a9bc7bfd f9000bf7 910003fd a90257f6 → 文件实际字节（见下数组）每 4 字节反序。
inline constexpr uintptr_t kImagePcxLoadFileOffset = 0x4d40a8;
inline constexpr std::array<u8, 16> kImagePcxLoadExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
// 内存版 `Load(const uint8_t* data, uint32_t size, const char* path)`：
// `_ZN4KAGE8Graphics8ImagePcx4LoadEPKhjPKc`。回调把转好的 PCX 字节喂它。
// 守卫字节由 `tools/nro_disasm.py 0x4d4160 16` 抽查（2026-09-21，小端文件字节序）：
//   sub sp,sp,#0x40 / stp x29,x30,[sp,#0x10] / add x29,sp,#0x10 / stp x22,x21,[sp,#0x20]
inline constexpr uintptr_t kImagePcxLoadInMemoryFileOffset = 0x4d4160;
inline constexpr std::array<u8, 16> kImagePcxLoadInMemoryExpectedBytes = {
    0xFF, 0x03, 0x01, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
// 转码器需要的三个 zlib 符号（C 符号，非引擎命名空间）。`PngToPcx` 通过注入的
// `InflateFn` 调用解压，不直接链 zlib 的符号；这里只存地址供 `GameFileReader` 在
// 设备安装时按偏移核对并发布。全部用「调用侧守卫」：只比入口前 16 字节，不比内部。
//   inflateInit2_ ：`tools/nro_disasm.py 0x4e1f90 16`（stp;stp;mov;cbz x2）
inline constexpr uintptr_t kZlibInflateInit2FileOffset = 0x4e1f90;
inline constexpr std::array<u8, 16> kZlibInflateInit2ExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xA2, 0x07, 0x00, 0xB4,
};
//   inflate       ：`tools/nro_disasm.py 0x4e21a0 16`（stp;stp;mov;stp）
inline constexpr uintptr_t kZlibInflateFileOffset = 0x4e21a0;
inline constexpr std::array<u8, 16> kZlibInflateExpectedBytes = {
    0xFD, 0x7B, 0xBA, 0xA9, 0xFC, 0x6F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xFA, 0x67, 0x02, 0xA9,
};
//   inflateEnd    ：`tools/nro_disasm.py 0x4e1f20 16`（stp;str x19;mov;cbz x0）
inline constexpr uintptr_t kZlibInflateEndFileOffset = 0x4e1f20;
inline constexpr std::array<u8, 16> kZlibInflateEndExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x60, 0x02, 0x00, 0xB4,
};

// ---------------------------------------------------------------------------
// 贴图桥 v2（2026-09-21 下午）：`ImageManager::LoadImage` 文件版 + 五参内存版
// ---------------------------------------------------------------------------
// 真机 14:10 验证 v1 拦截点（ImagePcx::Load @0x4d40a8）对"文件不存在"**永远等不到调用**：
// 文件版在创建贴图对象**之前**就先问挂载管理器 `GetMountedFilePath`，返回空（文件不在任何
// 挂载点）即从入口附近 `stp xzr,xzr,[x19]` 清零返回槽后**直接收尾**（0x4d2378 起就是纯
// epilogue）。所以拦截点必须上移到这里；兜底改为"原函数失败 → 读同名 .png → 转 PCX 字节
// → 调五参内存版（按扩展名建 ImagePcx、喂内存 Load、写缓存）→ 原样交出返回值"。
// 靶：`_ZN4KAGE8Graphics12ImageManager9LoadImageEPKcPNS0_25VertexAttributeDescriptorEb`。
// 守卫字节由 `tools/nro_disasm.py 0x4d1fe4 16` 抽查（2026-09-21，小端文件序）：
//   sub sp,sp,#0x80 / stp x29,x30,[sp,#0x20] / add x29,sp,#0x10+0x10 / str x27,[sp,#0x30]
inline constexpr uintptr_t kImageManagerLoadFileOffset = 0x4d1fe4;
inline constexpr std::array<u8, 16> kImageManagerLoadFileExpectedBytes = {
    0xFF, 0x03, 0x02, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xFB, 0x1B, 0x00, 0xF9,
};
// 靶：`_ZN4KAGE8Graphics12ImageManager9LoadImageEPKhjPKcS5_PNS0_25VertexAttributeDescriptorE`
// （五参内存版：按路径扩展名建对象 → 虚表 +0xe0 喂字节 → 写缓存）。**只调用、不挂钩**。
// 守卫字节由 `tools/nro_disasm.py 0x4d2654 16` 抽查（2026-09-21，小端文件序）。
inline constexpr uintptr_t kImageManagerLoadMemoryOffset = 0x4d2654;
inline constexpr std::array<u8, 16> kImageManagerLoadMemoryExpectedBytes = {
    0xFF, 0x03, 0x02, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xFC, 0x6F, 0x03, 0xA9,
};

// ---------------------------------------------------------------------------
// 贴图桥 v3（2026-09-21 15:1x）：兜底不许"盲开"文件
// ---------------------------------------------------------------------------
// 真机 crash_reports 01789974615（Type: User Break，`nn::diag::Abort`）坐实：兜底里用
// 引擎 `KAGE::Filesys::File::OpenRead` 直接开 `.png` 时，引擎的 `File::open_file_handle`
// 对"打开失败"**直接 Abort** —— 清单/脚本读取从来只开确定存在的文件，这条 Abort 路以前
// 从没被踩过。而挂载解析发生在我们上游（`GetMountedFilePath`），原始请求的路径形状
// 原样传给 `File::OpenRead` 它认不了 ⇒ 必然失败 ⇒ 必然 Abort。
// 修法：兜底先用引擎自己的 `IContentManager::GetMountedFilePath` 解析（文件不在任何
// 挂载点 ⇒ 返回空、**不炸** —— `FileManager::Exists` 内部正是这么用它做存在性判断的），
// 拿到挂载绝对路径再交给 GameFileReader 读；用完用游戏的 `operator delete[]` 还债。
// `g_ContentManager` 的 GOT 槽：游戏自己取它就是 `adrp 0xaac000; ldr [x0,#0x748]`。
inline constexpr uintptr_t kContentManagerGotSlotOffset = 0xAAC748;
// `IContentManager::GetMountedFilePath(char const*)`（成员：x0=内容管理器，x1=路径；
// 返回堆上挂载绝对路径，调用方须用游戏 `operator delete[]` 释放；不在任何挂载点返回空）。
// 守卫字节由 `tools/nro_disasm.py 0x4c2340 16` 抽查（2026-09-21，小端文件序）：
//   stp x29,x30,[sp,#-0x30]! / str x21,[sp,#0x10] / mov x29,sp / stp x20,x19,[sp,#0x20]
inline constexpr uintptr_t kContentManagerGetMountedFilePathOffset = 0x4C2340;
inline constexpr std::array<u8, 16> kContentManagerGetMountedFilePathExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};
// 游戏导入的 `operator delete[](void*)`（`_ZdaPv`）PLT 桩（释放 GetMountedFilePath 的返回值；
// 与 kGameOperatorDeleteOffset 同一形态：游戏分配的内存必须用游戏的 delete 还）。
// 守卫字节由 `tools/nro_disasm.py 0x66fb90 16` 抽查（2026-09-21，小端文件序）。
inline constexpr uintptr_t kGameOperatorDeleteArrayOffset = 0x66FB90;
inline constexpr std::array<u8, 16> kGameOperatorDeleteArrayExpectedBytes = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0x9A, 0x46, 0xF9,
    0x10, 0xC2, 0x34, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};

// ---------------------------------------------------------------------------
// 贴图桥 v4（2026-09-21 晚）：在"文件层"递字节，**不碰贴图管理器**
// ---------------------------------------------------------------------------
// 教训（16:22 真机卡死）：内存转码不能在贴图管理器内部再回调它自己（插入路径要拿
// `ImageManager+0x8` 的互斥锁 ⇒ 自己锁死自己）。v4 改成：
//   ① 挂 `IContentManager::GetMountedFilePath`：`.pcx` 不在任何挂载点、但同名 `.png` 在时，
//      返回一条**合成的 `.pcx` 挂载路径**（=`.png` 的挂载路径换扩展名）⇒ 引擎自己的文件版
//      会按"扩展名 pcx"建 `ImagePcx` 并走到对象的文件版 `Load`；
//   ② 我们已有的 `ImagePcx::Load` 钩子这时就能被调到（v1 当年等不到的就是这个前提！）：
//      原函数打不开合成路径 → 解析同名 `.png` → 读 → 转 PCX → 调**对象自己的**内存版
//      `Load`（`0x4d4160`，纯对象级、无锁）→ 返回 bool；
//   ③ 之后引擎自己完成缓存/登记（它自己的锁、它自己的层级）—— 全程无重入。
//
// 合成路径由引擎的调用方用 `_ZdaPv`（delete[]）释放 ⇒ 我们必须用**游戏自己的**
// `operator new[]`（`_Znam` 的 PLT 桩）分配，保证同一套堆。
// 守卫字节由 `tools/nro_disasm.py 0x66fb60 16` 抽查（2026-09-21，小端文件序）。
inline constexpr uintptr_t kGameOperatorNewArrayOffset = 0x66FB60;
inline constexpr std::array<u8, 16> kGameOperatorNewArrayExpectedBytes = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0x8E, 0x46, 0xF9,
    0x10, 0x62, 0x34, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};

// ---------------------------------------------------------------------------
// 模组页搬生产（2026-09-23）：三个**入口中继**靶点
// ---------------------------------------------------------------------------
// 由来：`docs/设计-模组页搬生产-20260923.md`（用户定案"整块搬"：选择界面那一列多一格「模组」
// + 模组页 + 中文字体接线）。行为真值源是探针 `runtime/source/probe/native_mods_menu_probe.cpp`
// —— 那三个入口在探针里已经逐字节核过、真机跑过，这里**逐字节照搬**它的常量（一个字节都不改）。
//
// 三个靶点各挂一次入口中继（零占洞：改写目标函数入口 16 字节，见 `relay/entry_relay.hpp`）：
//   * `Menu_Game::Render`    —— 那一列里多一格「模组」要**挪行 + 挪光标**（我们改图层偏移，
//                               画完再还原；引擎自己那份动画有第六层时由引擎画，我们不画）；
//   * `Menu_Title::Render`   —— 模组页（引擎状态 16）**唯一**的画手：`MenuManager::Render`
//                               每帧调的 15 个页面里没有模组页，所以借标题页那一趟的渲染上下文；
//   * `MenuManager::SetState`—— 保险：引擎按它自己的行号想替我们那一格跳统计/选项时挡下来。
//
// ⚠️ 三个靶点与探针**是同一批入口** ⇒ 探针构建里必须跳过这三个挂点的安装
// （`hook_manager.cpp` 的 `SkipOptionalHooksPredicate` 里那条 `EXL_PROBE_BREAK_NATIVE_MODS_MENU`
//  分支）：入口中继是"改写入口 16 字节"，同一入口装第二次必然 `EntryMismatch`。
//
// `Menu_Game::Render`（`tools/nro_disasm.py 0x40E73C 16` 抽查，小端文件序）：
//   sub sp,sp,#0x150 / str d8,[sp,#0x10] / str x28,[sp,#0x10] / stp x29,x30,[sp,#0x10]!
inline constexpr uintptr_t kMenuGameRenderOffset = 0x40E73C;
inline constexpr std::array<u8, 16> kMenuGameRenderExpectedBytes = {
    0xFF, 0x43, 0x05, 0xD1, 0xE8, 0x7B, 0x00, 0xFD,
    0xFC, 0x87, 0x00, 0xF9, 0xFD, 0xFB, 0x0F, 0xA9,
};
// `Menu_Title::Render`（`tools/nro_disasm.py 0x41A574 16`）：
//   sub sp,sp,#0x50 / ldp x9,x8,[sp,#0x40] / str x21,[sp,#0x10] / stp x29,x30,[sp,#0x20]
// ★ 为什么挂**函数入口**而不是改那个调用点：整份模块里 `bl Menu_Title::Render`
//   （文件偏移 `0x3FE8AC`，目标是 PLT 桩 `0x67D500`）是**唯一**引用它的一处
//   （扫全部 `bl/b`：直接跳 `0x41A574` 的 0 处、重定位表里指向它的 0 处）⇒ 两者语义相同，
//   而入口中继零占用游戏字节（游戏映像的代码洞只剩 0x30 字节、零余量）。
inline constexpr uintptr_t kMenuTitleRenderOffset = 0x41A574;
inline constexpr std::array<u8, 16> kMenuTitleRenderExpectedBytes = {
    0xFF, 0x43, 0x01, 0xD1, 0xE9, 0x23, 0x01, 0x6D,
    0xF5, 0x1B, 0x00, 0xF9, 0xFD, 0x7B, 0x02, 0xA9,
};
// `MenuManager::SetState(eState)`（`tools/nro_disasm.py 0x3FE4DC 16`）：
//   stp x29,x30,[sp,#-0x30]! / str x21,[sp,#0x10] / mov x29,sp / stp x20,x19,[sp,#0x20]
//: `PersistentGameData::SetReadOnly(bool)`（`0x439460`）—— **唯一写"只读位"（`PGD+0x1`）的地方**
//: （全镜像 24 个调用点，全部在开局路径上：`Game::Start` / `StartDailyChallenge` / `RestoreState` /
//: `StartFromRerunState`，没有任何"中途重新允许成就"的调用点）。
//: 函数体（`tools/nro_disasm.py 0x439460 0x40`）：
//:   `ands w20,w1,#1` … `strb w20,[x19,#1]` ⇒ 它就是"本局给不给成就"的开关本身。
//:
//: ★★ 为什么闸门挂在这里，而不是像 092~097 那样拦 `TryUnlock`（2026-09-24 批次 098 改，用户裁定
//:    "照 PC 语义来"）：PC 的模型是**查询式**—— `ModManager::AchievementsLocked()`（带符号的
//:    `AfterbirthPlus.nro` 里 `0x250CB8` 逐条反汇编：遍历模组列表，任一启用 ⇒ 读
//:    `PersistentGameData::Unlocked(4)` 取反 ⇒ 「有模组开着 且 妈腿成就未解锁」= 锁），
//:    **在开局那一刻问一次**，结果落到只读位；之后 `TryUnlock` 自己查这个字节。
//:    Switch 移植版把那条查询链删干净了（`check_game_data_modified` 是死代码、
//:    `Manager::AchievementUnlocksDisallowed` 是空实现），残留的禁成就判据只有"特殊种子"与
//:    "挑战局"两条 —— 所以我们在这道**唯一写只读位的关卡**上按 PC 的规则补上那一步，
//:    其余（禁与不禁、什么时候清 0）全部交回引擎自己。
//:    ★ 反面教训：`Manager+0x36D4D` 曾被当成"本局禁成就"的输入写了六个批次（084~089），真机上
//:    完全无效 —— `Game::Start` 只是把它抄进 `Game+0x2F0030`（紧挨难度字段 `+0x2F0028`），
//:    它**不参与** `SetReadOnly` 的判据。
inline constexpr uintptr_t kPersistentGameDataSetReadOnlyOffset = 0x439460;
inline constexpr std::array<u8, 16> kPersistentGameDataSetReadOnlyExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x34, 0x00, 0x00, 0x72,
};
inline constexpr uintptr_t kMenuManagerSetStateOffset = 0x3FE4DC;
inline constexpr std::array<u8, 16> kMenuManagerSetStateExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};

// --- 游戏控制台 `IsaacRepentance::Console` 与系统软键盘（2026-09-25，批次 121）---------------
//
// **为什么需要这一段**：Switch 版把控制台"拆线"了，但**类与全部命令实现都在镜像里**。
//
//   * `Manager::IsDebuggingConsoleEnabled`（`0x3F9B64`）是两条指令的桩（`mov w0, wzr; ret`），
//     全镜像**零引用** ⇒ 引擎自己那条"要不要跑控制台"的开关根本不存在；
//   * `Console` 的构造/`Init`/`Update`/`Render`/`Show`/`ProcessInput`/`ShowKeyboard`
//     入边**全是 0**（`Console::RunCommand` 有 72 条入边，但**全部来自 `Console` 自己**：
//     `submit_input` 与它自身）⇒ 这个类从没被实例化、也没接进游戏循环；
//   * 但 `Console::RunCommand` 一个函数就 **0x6070 字节**，内含 PC 全量命令（`giveitem`/`spawn`/
//     `stage`/...）的实现 ⇒ **让命令生效的正路是"我们自己建一个实例、把命令喂给它"**，
//     不必自己重写命令集。
//
// **取证口径（这条比结论更值钱）**：本镜像里**连自己导出的函数也走 PLT 桩**（`bl 0x67xxxx`
// → GOT → 真身），所以"全镜像扫 `BL` 到目标偏移"必然得到**全零**（连角色命名界面调
// `OpenVirtualKeyboard` 也扫不到）。正确做法是先把 `JUMP_SLOT`→`GOT`→`PLT 桩`映射建起来
// （`tools/nro_disasm.py` 的 `_relocation_maps` / `_plt_import`）。2026-08-29 的复盘记过这个坑，
// 2026-09-25 我自己又踩了一次（详见本批记录）。`docs/问题与解决记录.md` 续四十 是"能不能做"的调研。
//
// **对象大小**：构造只做 `memset(this+0x20, 0, 0x130)` 并把 `+0x00`/`+0x08`/`+0x158` 清零；
// `Init` 写到 `+0x160` ⇒ 留 `0x180` 并放哨兵（超界要能被发现，而不是踩到相邻静态变量）。
inline constexpr std::size_t kConsoleObjectSize = 0x180;
inline constexpr uintptr_t kConsoleCtorOffset = 0x3BC34;
inline constexpr std::array<u8, 16> kConsoleCtorExpectedBytes = {
    0xFD, 0x7B, 0xBF, 0xA9, 0xFD, 0x03, 0x00, 0x91,
    0x08, 0x80, 0x00, 0x91, 0x1F, 0x00, 0x00, 0xB9,
};
inline constexpr uintptr_t kConsoleInitOffset = 0x3BDE8;
inline constexpr std::array<u8, 16> kConsoleInitExpectedBytes = {
    0xFF, 0x03, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF3, 0x1B, 0x00, 0xF9,
};
//: `Console::RunCommand(std::string const&, std::string*, Entity_Player*)`（**成员函数**：`x0` = this）。
//: 两条对着反汇编逐条确认的语义（决定了我们的调用形状）：
//:   ① 第 2 个参数（输出串）**可为 null** —— `Console::Print` 里是
//:      `ldr x0,[x0,#0x150]` + `cbz x0, 跳过` + `std::string::append(out, text)`，
//:      即"追加"而非覆写、且不接输出时整段跳过；
//:   ② 第 3 个参数（玩家）**可为 null**，但**为 null 时它会去读 `Game + 0x25C50` 玩家向量的第一个
//:      元素且不判空**（`ldp x8,x9,[x19]` → `cbnz w9` → `ldr x26,[x8]`）⇒ 玩家列表为空时那是
//:      **读空指针**。所以我们只在**确实取到玩家**时才把 null 交给引擎（见 `console_bridge.hpp`）。
inline constexpr uintptr_t kConsoleRunCommandOffset = 0x3D740;
inline constexpr std::array<u8, 16> kConsoleRunCommandExpectedBytes = {
    0xE8, 0x0F, 0x19, 0xFC, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xFC, 0x6F, 0x02, 0xA9,
};
//: `KAGE::System::g_Manager` 的 GOT 槽：**槽里就是那个全局对象本身的地址**
//: （`ldr x0,[x0,#0x8c0]` 之后直接把 `x0` 当 `this` 传进成员函数，中间没有第二次解引用）
//: ⇒ 与 `kGameOwnerGlobalSlotOffset`（槽里是指针变量、要解一次）**形状不同**，别照抄。
inline constexpr uintptr_t kKageSystemManagerSlotOffset = 0xAAC8C0;
//: `KAGE::System::Manager::OpenVirtualKeyboard(VirtualKeyboardParams const&, unsigned int)`
//: —— 系统软键盘（swkbd）的引擎入口。**它在真机上是活的**：三个调用者 =
//: `Menu_Character::ProcessInput`（角色命名用的就是它）、`Console::ProcessInput`、`Console::ShowKeyboard`。
//: ⇒ 我们不必自己开 applet 会话，用引擎这一个（`this` = `&KAGE::System::g_Manager`）即可。
inline constexpr uintptr_t kKageOpenVirtualKeyboardOffset = 0x520180;
inline constexpr std::array<u8, 16> kKageOpenVirtualKeyboardExpectedBytes = {
    0xFD, 0x7B, 0xBB, 0xA9, 0xFC, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9,
};
//: `KAGE::System::VirtualKeyboardParams::VirtualKeyboardParams()` —— 就地构造这个 **0x30 字节**的
//: 参数块（`+0x00` 标志、`+0x08` 宽字符缓冲、`+0x10` 上限 64、`+0x18` 文本变化回调、
//: `+0x20` 完成回调、`+0x28` userData）。`Console::ShowKeyboard` 就是一份可照抄的完整配方。
inline constexpr uintptr_t kKageVirtualKeyboardParamsCtorOffset = 0x51A478;
inline constexpr std::array<u8, 16> kKageVirtualKeyboardParamsCtorExpectedBytes = {
    0x08, 0x1D, 0x00, 0x90, 0x08, 0x01, 0x15, 0x91,
    0x1F, 0x00, 0x00, 0xB9, 0x09, 0x08, 0x80, 0x52,
};
//: `VirtualKeyboardParams` 的宽字符缓冲长度上限（引擎自己那两份配方都传 64）。
inline constexpr std::size_t kVirtualKeyboardTextCapacity = 64;
//: 给"按偏移解析游戏入口"用的**范围上限**（`engine_call::ResolveFunction` 的 `moduleSize`）：
//: 取 `Repentance.nro` 的**文件大小** 11,210,752 字节 = `0xAB1000`（NRO 在内存里的映像就是这份
//: 文件，`.bss` 另算）⇒ 用它当上限**偏保守**，而我们要解析的偏移都远小于它（最大 `0x520180`）。
inline constexpr std::size_t kGameModuleRangeCheckSize = 0xAB1000;
//: `IsaacRepentance::WIDTH`（屏幕宽，float）的 **GOT 槽**：槽里放的是**指向 float 的指针**
//: ⇒ 读法是"槽 → 指针 → 那个 float"（两步）。出处：`Menu_Manager::get_target_offset` 里
//: `adrp x8,0xaac000; ldr x8,[x8,#0x650]; ldr s0,[x8]`。`mod_menu_native.cpp` 里有一份**同值**的
//: 文件内常量（`kWidthSlotOffset = 0xAAC650`，那里注释更全：它是用来算"菜单纸该摆在哪"的）。
//: 为什么控制台也要它：输出要贴**右上角**，必须知道屏幕有多宽才能算左端 x（不能猜）。
inline constexpr uintptr_t kIsaacScreenWidthSlotOffset = 0xAAC650;
//: `IsaacRepentance::HEIGHT`（屏幕高，float）的 GOT 槽 —— 读法与上面那条逐字相同
//: （槽 → 指向 float 的指针 → 那个 float）。出处：`Menu_Manager::get_target_offset` 的
//: `ldr x8,[x8,#0x658]; ldr s0,[x8]`；`mod_menu_native.cpp:447` 有一份**同值**的本地常量。
//: ★ 掌机上实测值是 **240**（不是 270，也不是 720）—— 见 `mod_menu_native.cpp:709` 那段
//:   "按 (screenHeight − 270)/2 推出来的目标与画布实际停的位置差 120"的读数。
inline constexpr uintptr_t kIsaacScreenHeightSlotOffset = 0xAAC658;
//: `IsaacRepentance::POINTSCALE`（渲染平面 → 窗口像素的比例，float）的 GOT 槽。
//: 出处：`GetRenderPosition @ 0x35B60` 里 `adrp x8,0xaac000; ldr x8,[x8,#0x7b0]; ldr s1,[x8]`
//: （x9 那条取的是 `DPP`，槽 `0xAAC7B8`；量化因子 K = POINTSCALE × DPP）。
//: 静态初值 2.0f（符号 `_ZN15IsaacRepentance10POINTSCALEE @ 0xa34370`），`ResizeWindow` 运行期会改。
inline constexpr uintptr_t kIsaacPointScaleSlotOffset = 0xAAC7B0;

// --- `Isaac.ScreenToWorld` 的算术常量（批次 195，2026-09-29）---------------------------
//
// 这些**不是**我们发明的口径：它们逐条来自 PC 的 `Isaac.ScreenToWorld` 处理函数
// （`isaac-ng.exe @ 0x80c760`，注册处文件偏移 0x409aaf）与引擎自己的 `GetRenderPosition`
// （`Repentance.nro @ 0x35B60`）。Switch 引擎里**没有** screen→world 的入口（穷举见
// `analysis/api-restore-transforms/spec.json` 的 `no_engine_screen_to_world`），PC 自己也是
// 就地把算式做完 —— 所以我们照抄算式，**不硬编码任何系数**：
//   wx = (p.x / POINTSCALE - room[0x1938].x - (WIDTH  - 338.0) * 0.5) / 0.65 + 60.0
//   wy = (p.y / POINTSCALE - room[0x1938].y - (HEIGHT - 182.0) * 0.5) / 0.65 + 140.0
// WIDTH / HEIGHT / POINTSCALE **运行期从上面三个 GOT 槽读**（`ResizeWindow` 会改它们 ⇒
// 不许写成 480/270/2.0 这种常量，那正是"掌机上算错"的来源）。
//: 0.65 = 26/40（世界单位 → 渲染平面点的比例；PC 字面量 @0xb6a4dc）。
inline constexpr float kWorldToRenderScale = 0.65F;
//: 13*26 / 7*26：房间在渲染平面上的宽/高（PC 字面量 @0xb6ac30 / @0xb6ab8c）。
inline constexpr float kRenderPlaneRoomWidth = 338.0F;
inline constexpr float kRenderPlaneRoomHeight = 182.0F;
//: 房间世界原点（PC 字面量 @0xb6aa8c / @0xb6ab44）—— 普通 13×7 房间 x∈[60,580]、y∈[140,420]。
inline constexpr float kRoomWorldOriginX = 60.0F;
inline constexpr float kRoomWorldOriginY = 140.0F;
//: `IsaacRepentance::g_Manager` 里那份**引擎自己的中等字体**（`Menu_Mods::Render` 画每一行用的
//: 就是它：`add x25, x8, #0x117120`），是纯 ASCII 的 `TeamMeatFont12`。
//: ★ 与 `mod_menu_native.cpp` 的本地常量 `kManagerFontOffset` 同值 —— 那一处被门禁按**原文**钉住
//: （`test_mod_menu_native_production.py`），所以这里重新登记一次而不是去改它；引用任一处都行，
//: 但**都只读**（077 往里面写过扩展字体，真机把中文显示搞坏了，078 撤回 ⇒ 不许再写）。
inline constexpr uintptr_t kIsaacManagerFontObjectOffset = 0x117120;
//: 引擎动作表里的"控制台"动作（`ButtonAction.ACTION_CONSOLE`，与 `lua_runtime.cpp` 的常量表一致）。
inline constexpr std::uint32_t kButtonActionConsole = 28;
//: 控制台呼出组合键：**同时按住**这两个动作（`ACTION_MENUCONFIRM` = A / `ACTION_MENUBACK` = B，
//: 与 `mod_menu_native.cpp` 里那三个动作号同一来源：`ACTION_MENUCONFIRM = 14` / `ACTION_MENUBACK = 15`）。
//: 为什么用"两个一起按"而不是单键：局内几乎每个单键都有本职（A/B 是射击面键），组合能避免误触。
//: ★ 批次 122 起判据是"**连续按住约 0.8 秒**"（`kConsoleTriggerHoldFrames`，在
//:   `console_session.hpp`）：光"同时按住"仍然会被连打射击误触（两键会在同一帧里被按下）。
//: ★ 组合是否可达以真机读数为准（控制台状态面 `g_ConsoleState[10]` 是"最近按下的动作号"、
//:   `[18]` 是"按过的动作号累计位图"）—— 若实测这两个组合不可达，改这两个数即可。
inline constexpr std::uint32_t kConsoleTriggerActionA = 14;
inline constexpr std::uint32_t kConsoleTriggerActionB = 15;

// ============================================================================
// 批次 238（2026-09-30）：**语料模组适配**（第一波 28 条引擎方法）
// ============================================================================
//
// 由来：用户要求把 `analysis/mod-corpus/` 里那 17 个语料模组全部接上。逐模组的
// `tools/mod_api_gap_report.py` 说明"运行时里找不到"的 API 去重后共 152 条，
// 其中 **71 条**在 Switch 动态符号表里有精确的方法入口（清单里 category = `missing_easy`），
// 本波先做"形状与接收者都现成"的 28 条。
//
// **证据来源（每条都是同一个口径）**：`analysis/lua-api-inventory/inventory.json` 的
// `switch` 一节 —— 它由 `tools/build_lua_api_inventory.py` 从**本仓库里那份 NRO**
// （`The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]/
// Program #0/1/.nro/Repentance.nro`）的动态符号表读出：`mangled` = 符号名、
// `offset` = 函数相对模块基址的偏移、`guard16` = 入口前 16 字节（这里取前 4 字节按
// **小端**拼成 `EntryWord`，调用前逐字节核对 —— 偏移错了就**不调**，不会静默调错函数）。
// 每条下面的注释里逐条给出 `mangled`，可复核。
//
// 形状的取法：**按符号签名（mangled 里编码的参数表），不按 PC 文档的参数个数** ——
// 文档写的是"调用者视角"（默认参数省略），而 ABI 上默认参数**照样占寄存器**。
// 例：`EntityPlayer:AddHearts(int)` 文档 1 个参数，符号是 `AddHearts(int, bool)`
// ⇒ ABI 是两个整数 ⇒ 用 `Void2`。用 `Void1` 会让第二个寄存器留下垃圾值。

// `Entity::IsBoss` @ `0x67580`，入口 `e0031f2a`（Mod 判「是不是 Boss」）。
// 符号：`_ZNK15IsaacRepentance6Entity6IsBossEv`
// ★★ 批次 319：**对外 API 已改走虚调用**（`kEntityVtableIsBossSlot`，见批次 319 段）——
//    这两个常量只作"基类实现"的登记证据保留，**派发不再用它们**。
inline constexpr uintptr_t kEntityIsBossOffset = 0x67580;
inline constexpr std::uint32_t kEntityIsBossEntryWord = 0x2A1F03E0U;

// `Entity::IsEnemy` @ `0x59130`，入口 `083840b9`（Mod 挑敌人）。
// 符号：`_ZNK15IsaacRepentance6Entity7IsEnemyEv`
inline constexpr uintptr_t kEntityIsEnemyOffset = 0x59130;
inline constexpr std::uint32_t kEntityIsEnemyEntryWord = 0xB9403808U;

// `Entity::Kill` @ `0x5C8E0`，入口 `fd7bbea9`（Mod 杀实体）。
// 符号：`_ZN15IsaacRepentance6Entity4KillEv`
// ★★ 批次 319：**对外 API 已改走虚调用**（`kEntityVtableKillSlot`）—— 这两个常量只作基类实现的
//    登记证据保留，**派发不再用它们**（`Entity_Familiar::Kill` / `Entity_NPC::Kill` 有覆盖）。
inline constexpr uintptr_t kEntityKillOffset = 0x5C8E0;
inline constexpr std::uint32_t kEntityKillEntryWord = 0xA9BE7BFDU;

// `Entity::Remove` @ `0x5D3E0`，入口 `080c4739`（6 个语料模组都在调（最高频的一条））。
// 符号：`_ZN15IsaacRepentance6Entity6RemoveEv`
// ★★ 批次 319：**对外 API 已改走虚调用**（`kEntityVtableRemoveSlot`）—— 这两个常量只作基类实现的
//    登记证据保留，**派发不再用它们**（`Entity_Familiar::Remove` / `Entity_Pickup::Remove` 有覆盖）。
inline constexpr uintptr_t kEntityRemoveOffset = 0x5D3E0;
inline constexpr std::uint32_t kEntityRemoveEntryWord = 0x39470C08U;

// `Entity::Update` @ `0x60040`，入口 `ff8305d1`（Mod 手动更新实体）。
// 符号：`_ZN15IsaacRepentance6Entity6UpdateEv`
// ★★★ 批次 319：**对外 API 已改走虚调用**（`kEntityVtableUpdateSlot`）—— 这两个常量只作基类实现的
//     登记证据保留，**派发不再用它们**。★ 这一条影响最大：`Update` 在**每个** `Entity` 派生类里
//     都被覆盖 ⇒ 直调基类时 `player:Update()` 只做了一半的事。
inline constexpr uintptr_t kEntityUpdateOffset = 0x60040;
inline constexpr std::uint32_t kEntityUpdateEntryWord = 0xD10583FFU;

// `EntityPlayer::AddBrokenHearts` @ `0x29A550`，入口 `fd7bbea9`（Mod 加碎心）。
// 符号：`_ZN15IsaacRepentance13Entity_Player15AddBrokenHeartsEi`
inline constexpr uintptr_t kEntityPlayerAddBrokenHeartsOffset = 0x29A550;
inline constexpr std::uint32_t kEntityPlayerAddBrokenHeartsEntryWord = 0xA9BE7BFDU;

// `EntityPlayer::AddCard` @ `0x2B0B78`，入口 `22008052`（Mod 塞卡牌）。
// 符号：`_ZN15IsaacRepentance13Entity_Player7AddCardENS_5eCardE`
inline constexpr uintptr_t kEntityPlayerAddCardOffset = 0x2B0B78;
inline constexpr std::uint32_t kEntityPlayerAddCardEntryWord = 0x52800022U;

// `EntityPlayer::AddEternalHearts` @ `0x27F6FC`，入口 `fd7bbea9`（Mod 加永恒心）。
// 符号：`_ZN15IsaacRepentance13Entity_Player16AddEternalHeartsEi`
inline constexpr uintptr_t kEntityPlayerAddEternalHeartsOffset = 0x27F6FC;
inline constexpr std::uint32_t kEntityPlayerAddEternalHeartsEntryWord = 0xA9BE7BFDU;

// `EntityPlayer::AddHearts` @ `0x27F29C`，入口 `fd7bbca9`（Mod 加心（第二参 = 是否来自拾取））。
// 符号：`_ZN15IsaacRepentance13Entity_Player9AddHeartsEib`
inline constexpr uintptr_t kEntityPlayerAddHeartsOffset = 0x27F29C;
inline constexpr std::uint32_t kEntityPlayerAddHeartsEntryWord = 0xA9BC7BFDU;

// `EntityPlayer::AddTrinket` @ `0x297A50`，入口 `ff0302d1`（Mod 加饰品）。
// 符号：`_ZN15IsaacRepentance13Entity_Player10AddTrinketENS_12eTrinketTypeEb`
inline constexpr uintptr_t kEntityPlayerAddTrinketOffset = 0x297A50;
inline constexpr std::uint32_t kEntityPlayerAddTrinketEntryWord = 0xD10203FFU;

// `EntityPlayer::EvaluateItems` @ `0x280804`，入口 `ef3bb66d`（Mod 改道具后重算属性）。
// 符号：`_ZN15IsaacRepentance13Entity_Player13EvaluateItemsEv`
inline constexpr uintptr_t kEntityPlayerEvaluateItemsOffset = 0x280804;
inline constexpr std::uint32_t kEntityPlayerEvaluateItemsEntryWord = 0x6DB63BEFU;

// `EntityPlayer::GetExtraLives` @ `0x2FB4A0`，入口 `085c4df9`（Mod 读额外生命数）。
// 符号：`_ZNK15IsaacRepentance13Entity_Player13GetExtraLivesEv`
inline constexpr uintptr_t kEntityPlayerGetExtraLivesOffset = 0x2FB4A0;
inline constexpr std::uint32_t kEntityPlayerGetExtraLivesEntryWord = 0xF94D5C08U;

// `EntityPlayer::NeedsCharge` @ `0x2FBA7C`，入口 `fd7bbda9`（Mod 问主动道具要不要充能）。
// 符号：`_ZNK15IsaacRepentance13Entity_Player11NeedsChargeEi`
inline constexpr uintptr_t kEntityPlayerNeedsChargeOffset = 0x2FBA7C;
inline constexpr std::uint32_t kEntityPlayerNeedsChargeEntryWord = 0xA9BD7BFDU;

// `EntityPlayer::Revive` @ `0x2E6600`，入口 `ff0301d1`（Mod 复活玩家）。
// 符号：`_ZN15IsaacRepentance13Entity_Player6ReviveEv`
inline constexpr uintptr_t kEntityPlayerReviveOffset = 0x2E6600;
inline constexpr std::uint32_t kEntityPlayerReviveEntryWord = 0xD10103FFU;

// `EntityPlayer::SetActiveCharge` @ `0x27F984`，入口 `fd7bbaa9`（Mod 设主动道具充能）。
// 符号：`_ZN15IsaacRepentance13Entity_Player15SetActiveChargeEii`
inline constexpr uintptr_t kEntityPlayerSetActiveChargeOffset = 0x27F984;
inline constexpr std::uint32_t kEntityPlayerSetActiveChargeEntryWord = 0xA9BA7BFDU;

// `EntityPlayer::SetCard` @ `0x2E8DA4`，入口 `3f0c0071`（Mod 设卡牌槽）。
// 符号：`_ZN15IsaacRepentance13Entity_Player7SetCardEiNS_5eCardE`
inline constexpr uintptr_t kEntityPlayerSetCardOffset = 0x2E8DA4;
inline constexpr std::uint32_t kEntityPlayerSetCardEntryWord = 0x71000C3FU;

// `EntityPlayer::TryRemoveTrinket` @ `0x2A27F0`，入口 `ff0302d1`（Mod 摘饰品）。
// 符号：`_ZN15IsaacRepentance13Entity_Player16TryRemoveTrinketENS_12eTrinketTypeE`
inline constexpr uintptr_t kEntityPlayerTryRemoveTrinketOffset = 0x2A27F0;
inline constexpr std::uint32_t kEntityPlayerTryRemoveTrinketEntryWord = 0xD10203FFU;

// `EntityPlayer::UseCard` @ `0x2E9040`，入口 `ee0f16fc`（Mod 让玩家用卡）。
// 符号：`_ZN15IsaacRepentance13Entity_Player7UseCardENS_5eCardEj`
// ★ 偏移**复用上面那条既有常量**（`Entity_Player::UseCard` 早就是批次 102 的中继靶点，
//   声明在文件上部）—— 这里只补入口指纹，别再声明一遍（会重复定义）。
inline constexpr std::uint32_t kEntityPlayerUseCardEntryWord = 0xFC160FEEU;

// `Game::AddDevilRoomDeal` @ `0x35AF10`，入口 `084e9f52`（Mod 记一次恶魔房交易）。
// 符号：`_ZN15IsaacRepentance4Game16AddDevilRoomDealEv`
inline constexpr uintptr_t kGameAddDevilRoomDealOffset = 0x35AF10;
inline constexpr std::uint32_t kGameAddDevilRoomDealEntryWord = 0x529F4E08U;

// `Game::Update` @ `0x351884`，入口 `ffc307d1`（Mod 手动推进一帧）。
// 符号：`_ZN15IsaacRepentance4Game6UpdateEv`
inline constexpr uintptr_t kGameUpdateOffset = 0x351884;
inline constexpr std::uint32_t kGameUpdateEntryWord = 0xD107C3FFU;

// `Level::Update` @ `0x3D08A4`，入口 `08aa8252`（Mod 手动推进一帧）。
// 符号：`_ZN15IsaacRepentance5Level6UpdateEv`
inline constexpr uintptr_t kLevelUpdateOffset = 0x3D08A4;
inline constexpr std::uint32_t kLevelUpdateEntryWord = 0x5282AA08U;

// `Level::UpdateVisibility` @ `0x3D9638`，入口 `fd7bbba9`（改了房间可见性后要调它生效）。
// 符号：`_ZN15IsaacRepentance5Level16UpdateVisibilityEv`
inline constexpr uintptr_t kLevelUpdateVisibilityOffset = 0x3D9638;
inline constexpr std::uint32_t kLevelUpdateVisibilityEntryWord = 0xA9BB7BFDU;

// `Room::GetRoomConfigStage` @ `0x455024`，入口 `fd7bbfa9`（Mod 读房间配置阶段）。
// 符号：`_ZNK15IsaacRepentance4Room18GetRoomConfigStageEv`
inline constexpr uintptr_t kRoomGetRoomConfigStageOffset = 0x455024;
inline constexpr std::uint32_t kRoomGetRoomConfigStageEntryWord = 0xA9BF7BFDU;

// `Room::HasCurseMist` @ `0x48C69C`，入口 `080440f9`（Mod 判诅咒雾）。
// 符号：`_ZNK15IsaacRepentance4Room12HasCurseMistEv`
inline constexpr uintptr_t kRoomHasCurseMistOffset = 0x48C69C;
inline constexpr std::uint32_t kRoomHasCurseMistEntryWord = 0xF9400408U;

// `Room::IsAmbushActive` @ `0x46AC8C`，入口 `083200d0`（Mod 判伏击进行中）。
// 符号：`_ZNK15IsaacRepentance4Room14IsAmbushActiveEv`
inline constexpr uintptr_t kRoomIsAmbushActiveOffset = 0x46AC8C;
inline constexpr std::uint32_t kRoomIsAmbushActiveEntryWord = 0xD0003208U;

// `Room::IsCurrentRoomLastBoss` @ `0x464430`，入口 `fd7bbea9`（Mod 判 Boss 房）。
// 符号：`_ZNK15IsaacRepentance4Room21IsCurrentRoomLastBossEv`
inline constexpr uintptr_t kRoomIsCurrentRoomLastBossOffset = 0x464430;
inline constexpr std::uint32_t kRoomIsCurrentRoomLastBossEntryWord = 0xA9BE7BFDU;

// `Room::RemoveDoor` @ `0x464484`，入口 `fd7bbda9`（Mod 拆门）。
// 符号：`_ZN15IsaacRepentance4Room10RemoveDoorENS_9eDoorSlotE`
inline constexpr uintptr_t kRoomRemoveDoorOffset = 0x464484;
inline constexpr std::uint32_t kRoomRemoveDoorEntryWord = 0xA9BD7BFDU;

// `Room::Update` @ `0x46D788`，入口 `ed33b76d`（Mod 手动更新房间）。
// 符号：`_ZN15IsaacRepentance4Room6UpdateEv`
inline constexpr uintptr_t kRoomUpdateOffset = 0x46D788;
inline constexpr std::uint32_t kRoomUpdateEntryWord = 0x6DB733EDU;

// ===========================================================================
// 批次 239（2026-09-30）：**语料模组适配第二波 A 批**（18 条，全部落成引擎方法数据行）
//
// 统一口径（本段所有条目都适用）：
//   * 偏移取 `analysis/lua-api-inventory/inventory.json` 的 `switch.offset`，
//     **逐条用本仓库那份 `Repentance.nro` 复核过**（符号 `file_offset` == 该偏移）；
//   * 入口字 = 该函数首 4 字节按小端读成 `u32`（本段每条都实测得到）；
//   * PC 契约原文见每条注释里的 `tools/pc_contract_docs/<页>.md:<行号>`（G2 闸门）；
//   * 「形状按符号签名取、不按文档参数个数」：文档参数个数与符号不一致的三条
//     （`Room:SetGridPath` / `Room:DestroyGrid` / `EntityPlayer:AddHearts` 一类）在各自注释里点名。
// ===========================================================================

// `Room::RemoveGridEntity(int, int, bool)` @ `0x46755C`，入口 `fd7bbda9`。
// 符号：`_ZN15IsaacRepentance4Room16RemoveGridEntityEiib`（3 个参数：int / int / **bool**）
// PC 契约：`tools/pc_contract_docs/Room.md:725`「void RemoveGridEntity ( int GridIndex, int PathTrail, boolean KeepDecoration )」
// 调用点：`BOIStageAPI15/.../roomHandler.lua`（`shared.Room:RemoveGridEntity(i, 0, false)`）、
// `IsaacOnTwitchReloaded/scripts/mechanics.lua`、`RepentancePlus/.../main.lua`。
// 第 3 个参数在语料里是 Lua **布尔** ⇒ 形状里该位置必须是 `Bool`（`Int` 会拒收布尔）。
inline constexpr uintptr_t kRoomRemoveGridEntityOffset = 0x46755C;
inline constexpr std::uint32_t kRoomRemoveGridEntityEntryWord = 0xA9BD7BFDU;

// `Room::GetGridCollision(int)` @ `0x452654`，入口 `080440f9`（`const` 成员，读一个数组格）。
// 符号：`_ZNK15IsaacRepentance4Room16GetGridCollisionEi`
// PC 契约：`tools/pc_contract_docs/Room.md:335`「GridCollisionClass GetGridCollision ( int GridIndex )」
// 调用点：`BOIStageAPI15/scripts/stageapi/grid/roomEditorFeatures.lua`（多处 `shared.Room:GetGridCollision(index)`）。
// 枚举返回按整数压回 ⇒ 形状 `Int1`。
inline constexpr uintptr_t kRoomGetGridCollisionOffset = 0x452654;
inline constexpr std::uint32_t kRoomGetGridCollisionEntryWord = 0xF9400408U;

// `Room::SetGridPath(int, int, int)` @ `0x4841EC`，入口 `0102f837`。
// 符号：`_ZN15IsaacRepentance4Room11SetGridPathEiii`（**3 个 int**）
// PC 契约：`tools/pc_contract_docs/Room.md:795`「boolean SetGridPath ( int Index, int Value )」—— **文档 2 个、符号 3 个**
//   ⇒ 按符号取 3 格（G3 闸门：默认参数在 ABI 上照样占寄存器），第 3 格由形状声明为"可省"。
// 调用点：`BOIStageAPI15/.../customgrids.lua` 与 `roomHandler.lua`（`shared.Room:SetGridPath(i, 0)`，**只传 2 个**）。
inline constexpr uintptr_t kRoomSetGridPathOffset = 0x4841EC;
inline constexpr std::uint32_t kRoomSetGridPathEntryWord = 0x37F80201U;

// `Room::SpawnClearAward()` @ `0x456810`，入口 `ff8304d1`（无参、返回 void）。
// 符号：`_ZN15IsaacRepentance4Room15SpawnClearAwardEv`
// PC 契约：`tools/pc_contract_docs/Room.md:862`「void SpawnClearAward ( )」
// 调用点：`IsaacOnTwitchReloaded/scripts/events.lua`（`room:SpawnClearAward()`）。
inline constexpr uintptr_t kRoomSpawnClearAwardOffset = 0x456810;
inline constexpr std::uint32_t kRoomSpawnClearAwardEntryWord = 0xD10483FFU;

// `Room::DestroyGrid(int, bool, bool)` @ `0x454CF4`，入口 `3ffc0671`。
// 符号：`_ZN15IsaacRepentance4Room11DestroyGridEibb`（**3 个参数**：int / bool / bool）
// PC 契约：`tools/pc_contract_docs/Room.md:63`「boolean DestroyGrid ( int Index, boolean Immediate )」—— 文档 2 个、符号 3 个
//   ⇒ 按符号取 3 格，尾部 2 格由形状声明为"可省"。
// 调用点：`IsaacOnTwitchReloaded/scripts/events.lua`（`room:DestroyGrid(ind)`，**只传 1 个**）。
inline constexpr uintptr_t kRoomDestroyGridOffset = 0x454CF4;
inline constexpr std::uint32_t kRoomDestroyGridEntryWord = 0x7106FC3FU;

// `Room::TurnGold()` @ `0x4649F8`，入口 `ff8303d1`（无参、返回 void）。
// 符号：`_ZN15IsaacRepentance4Room8TurnGoldEv`
// PC 契约：`tools/pc_contract_docs/Room.md:952`「void TurnGold ( )」
// 调用点：`IsaacOnTwitchReloaded/scripts/events.lua`（`room:TurnGold()`）、`scripts/passiveItems.lua`。
inline constexpr uintptr_t kRoomTurnGoldOffset = 0x4649F8;
inline constexpr std::uint32_t kRoomTurnGoldEntryWord = 0xD10383FFU;

// `Level::SetStage(eLevelStage, eStageType)` @ `0x3E420C`，入口 `fd7bbda9`。
// 符号：`_ZN15IsaacRepentance5Level8SetStageENS_11eLevelStageENS_10eStageTypeE`（两个枚举 ⇒ 两个整数寄存器）
// PC 契约：`tools/pc_contract_docs/Level.md:369`「void SetStage ( int StageOffset, int StageTypeOffset )」
// 调用点：`ChallengeAPI/.../stage_transition.lua`（`Game():GetLevel():SetStage(LevelStage.STAGE3_1, StageType.STAGETYPE_REPENTANCE)`）、
// `BOIStageAPI15/.../customstage.lua` 与 `extrarooms.lua`。
inline constexpr uintptr_t kLevelSetStageOffset = 0x3E420C;
inline constexpr std::uint32_t kLevelSetStageEntryWord = 0xA9BD7BFDU;

// `Level::SetNextStage()` @ `0x3E42F4`，入口 `fd7bbca9`（无参、返回 void）。
// 符号：`_ZN15IsaacRepentance5Level12SetNextStageEv`
// PC 契约：`tools/pc_contract_docs/Level.md:359`「void SetNextStage ( )」
inline constexpr uintptr_t kLevelSetNextStageOffset = 0x3E42F4;
inline constexpr std::uint32_t kLevelSetNextStageEntryWord = 0xA9BC7BFDU;

// `Level::GetPlanetariumChance()` @ `0x3D58BC`，入口 `ff4301d1`（无参、**返回 float 走 `d0`**）。
// 符号：`_ZN15IsaacRepentance5Level20GetPlanetariumChanceEv`
// PC 契约：`tools/pc_contract_docs/Level.md:187`「float GetPlanetariumChance ( )」
// 调用点：`isaac-planetarium-chance/main.lua`（`level:GetPlanetariumChance()`）。
// ★ 这条是本批**唯一**需要"无参 + 浮点返回"形状的（`Int0` 取 `x0`、它要取 `d0`）。
inline constexpr uintptr_t kLevelGetPlanetariumChanceOffset = 0x3D58BC;
inline constexpr std::uint32_t kLevelGetPlanetariumChanceEntryWord = 0xD10143FFU;

// `Level::GetRandomRoomIndex(bool, int)` @ `0x3DBA84`，入口 `ff4302d1`（`const` 成员）。
// 符号：`_ZNK15IsaacRepentance5Level18GetRandomRoomIndexEbj`（bool / int）
// PC 契约：`tools/pc_contract_docs/Level.md:198`「int GetRandomRoomIndex ( boolean IAmErrorRoom, int Seed )」
// 调用点：`MinimapAPI/scripts/minimapapi/main.lua`（`level:GetRandomRoomIndex(false, cache.RoomDescriptor.DecorationSeed)`）
// —— 第 1 个实参是 Lua **布尔** ⇒ 该位置必须 `Bool`。
inline constexpr uintptr_t kLevelGetRandomRoomIndexOffset = 0x3DBA84;
inline constexpr std::uint32_t kLevelGetRandomRoomIndexEntryWord = 0xD10243FFU;

// `Game::GetGreedBossWaveNum()` @ `0x359E18`，入口 `08058052`（`const` 成员、无参、返回 int）。
// 符号：`_ZNK15IsaacRepentance4Game19GetGreedBossWaveNumEv`
// PC 契约：`tools/pc_contract_docs/Game.md:269`「int GetGreedBossWaveNum ( )」
// 调用点：`BOIStageAPI15/.../customstage.lua`（`shared.Game:GetGreedBossWaveNum()`）。
// 接收者用 `FieldReceipt::Level` —— 与同族既有的 `Game:ChangeRoom`/`Game:Update` 同一条链
// （引擎里 `Level` 内嵌在 `Game` 起始处，见该 receipt 的注释）。
inline constexpr uintptr_t kGameGetGreedBossWaveNumOffset = 0x359E18;
inline constexpr std::uint32_t kGameGetGreedBossWaveNumEntryWord = 0x52800508U;

// ---- `Music` 一族（7 条）----------------------------------------------------
//
// ★ 接收者全是 `FieldReceipt::Music`（**不从 Lua 栈上取**）：`MusicManager()` 在 Lua 里是
// 占位句柄，引擎的 `Music` 是 `Manager + kManagerMusicOffset` 处的内嵌子对象。
// 这 7 条与既有的 `MusicManager:Pause`/`Resume`/`Play`/`UpdateVolume`（**手写**处理器）
// 是同一个对象、同一份偏移，区别只是那 4 条写在数据行机制之前。

// `Music::DisableLayer(int)` @ `0x4277DC`，入口 `080080b9`。
// 符号：`_ZN15IsaacRepentance5Music12DisableLayerEi`
// PC 契约：`tools/pc_contract_docs/MusicManager.md:47`「void DisableLayer ( int LayerId = 0 )」—— **参数有缺省值**
// 调用点：`BOIStageAPI15/.../callbacks.lua` 与 `MusicModCallback/.../repentance.lua`，**一个参数都不传**。
inline constexpr uintptr_t kMusicDisableLayerOffset = 0x4277DC;
inline constexpr std::uint32_t kMusicDisableLayerEntryWord = 0xB9800008U;

// `Music::IsLayerEnabled(int)` @ `0x427800`，入口 `080080b9`。
// 符号：`_ZNK15IsaacRepentance5Music14IsLayerEnabledEi`（`const` 成员、返回 bool）
// PC 契约：`tools/pc_contract_docs/MusicManager.md:87`「boolean IsLayerEnabled ( int LayerId = 0 )」
// 调用点：`BOIStageAPI15/.../callbacks.lua`（`shared.Music:IsLayerEnabled()`，不传参数）。
inline constexpr uintptr_t kMusicIsLayerEnabledOffset = 0x427800;
inline constexpr std::uint32_t kMusicIsLayerEnabledEntryWord = 0xB9800008U;

// `Music::EnableLayer(int, bool)` @ `0x427674`，入口 `090080b9`。
// 符号：`_ZN15IsaacRepentance5Music11EnableLayerEib`（int / bool）
// PC 契约：`tools/pc_contract_docs/MusicManager.md:57`「void EnableLayer ( int LayerId = 0, boolean Instant = false )」
// 调用点：`shared.Music:EnableLayer()`（不传参数，两个缺省值都是 0）。
inline constexpr uintptr_t kMusicEnableLayerOffset = 0x427674;
inline constexpr std::uint32_t kMusicEnableLayerEntryWord = 0xB9800009U;

// `Music::VolumeSlide(float, float)` @ `0x4278A0`，入口 `283400b0`（两个浮点走 `d0`/`d1`）。
// 符号：`_ZN15IsaacRepentance5Music11VolumeSlideEff`
// PC 契约：`tools/pc_contract_docs/MusicManager.md:130`「void VolumeSlide ( float TargetVolume, float FadeRate = 0.08 )」
// 调用点：`MusicModCallback/.../repentance.lua`（`musicmgr:VolumeSlide(0.1, 0.05)`）。
inline constexpr uintptr_t kMusicVolumeSlideOffset = 0x4278A0;
inline constexpr std::uint32_t kMusicVolumeSlideEntryWord = 0xB0003428U;

// `Music::GetQueuedMusicID()` @ `0x426C40`，入口 `e80300aa`（`const` 成员、无参、返回 eMusic）。
// 符号：`_ZNK15IsaacRepentance5Music16GetQueuedMusicIDEv`
// PC 契约：`tools/pc_contract_docs/MusicManager.md:77`「Music GetQueuedMusicID ( )」
// 调用点：`BOIStageAPI15/.../callbacks.lua`（`shared.Music:GetQueuedMusicID()`）。
inline constexpr uintptr_t kMusicGetQueuedMusicIdOffset = 0x426C40;
inline constexpr std::uint32_t kMusicGetQueuedMusicIdEntryWord = 0xAA0003E8U;

// `Music::PitchSlide(float)` @ `0x42785C`，入口 `00d403bd`。
// 符号：`_ZN15IsaacRepentance5Music10PitchSlideEf`
// PC 契约：`tools/pc_contract_docs/MusicManager.md:97`「void PitchSlide ( float TargetPitch )」—— **无缺省值** ⇒ 复用 `VoidFloat1`
// 调用点：`MusicModCallback/.../repentance.lua`（转发 `musicmgr:PitchSlide(...)`）。
inline constexpr uintptr_t kMusicPitchSlideOffset = 0x42785C;
inline constexpr std::uint32_t kMusicPitchSlideEntryWord = 0xBD03D400U;

// `Music::ResetPitch()` @ `0x427864`，入口 `e81b09b2`（无参、返回 void）。
// 符号：`_ZN15IsaacRepentance5Music10ResetPitchEv`
// PC 契约：`tools/pc_contract_docs/MusicManager.md:114`「void ResetPitch ( )」
inline constexpr uintptr_t kMusicResetPitchOffset = 0x427864;
inline constexpr std::uint32_t kMusicResetPitchEntryWord = 0xB2091BE8U;

// ===========================================================================
// 批次 252（2026-10-01）：混音 / 房间 / 玩家的 5 条引擎方法（**全部走数据行**）
//
// 偏移与入口指纹一律从**动态符号表**直接取（`tools/nro_symbols.py` 的
// `parse_dynamic_symbols`），再用 NRO 里那 4 个入口字节核对 —— 与批次 239 同一套口径。
// ===========================================================================

// `Music::Queue(eMusic ID)` @ `0x427854`，入口 `01cc03b9`。
// 符号：`_ZN15IsaacRepentance5Music5QueueENS_6eMusicE`
// PC 契约：`tools/pc_contract_docs/MusicManager.md:109`「void Queue ( Music ID )」——**无缺省值**
// ⇒ 形状 `Void1`（现成）、`argumentCount` = 1。
// 语料实参 1 个：`BOIStageAPI15/scripts/stageapi/core/callbacks.lua:545` 的
// `shared.Music:Queue(shouldQueue)`；`MusicModCallback/scripts/mmc/repentance.lua:775/879/889` 同。
inline constexpr uintptr_t kMusicQueueOffset = 0x427854;
inline constexpr std::uint32_t kMusicQueueEntryWord = 0xB903CC01U;

// `Music::Crossfade(eMusic ID, float FadeRate)` @ `0x4273C0`，入口 `e80f1cfc`。
// 符号：`_ZN15IsaacRepentance5Music9CrossfadeENS_6eMusicEf`
// PC 契约：`MusicManager.md:35`「void Crossfade ( Music ID, float FadeRate = 0.08 )」
// ⇒ 尾部 1 个可省。语料传 2 个（`MusicModCallback/.../repentance.lua:771/789`）。
// 形状 `VoidIntFloatOpt1`（本批新增）：整数与浮点**各自独立计数**（i32 走 `x1`、float 走 `d0`）。
inline constexpr uintptr_t kMusicCrossfadeOffset = 0x4273C0;
inline constexpr std::uint32_t kMusicCrossfadeEntryWord = 0xFC1C0FE8U;

// `Game::ShowHallucination(int FrameCount, eBackdrop Backdrop)` @ `0x35BE54`，入口 `fd7bbda9`。
// 符号：`_ZN15IsaacRepentance4Game17ShowHallucinationEiNS_8Backdrop9eBackdropE`
// PC 契约：`Game.md:484`「void ShowHallucination ( int FrameCount,
//   BackdropType Backdrop = BackdropType.NUM_BACKDROPS )」。
// ★ **那个缺省值不是 0**（`NUM_BACKDROPS` 是枚举的末值）⇒ **不能**用"尾部可省"那一格：
//   省略时寄存器保持 0，而 0 不等于那个缺省 ⇒ 想要"省略"就只能自己填对值。
//   ⇒ 用现成的 `Void2`（2 个参数全必填）；语料也传满 2 个
//   （`BOIStageAPI15/.../roomgfx.lua:160` 的 `shared.Game:ShowHallucination(0, backdrop)`）。
inline constexpr uintptr_t kGameShowHallucinationOffset = 0x35BE54;
inline constexpr std::uint32_t kGameShowHallucinationEntryWord = 0xA9BD7BFDU;

// `Room::SpawnGridEntity(int, eGridEntityType, uint Variant, uint Seed, int VarData)` @ `0x452528`。
// 符号：`_ZN15IsaacRepentance4Room15SpawnGridEntityEiNS_15eGridEntityTypeEjji`
// PC 契约：`Room.md:867`「boolean SpawnGridEntity ( int GridIndex, GridEntityType Type,
//   int Variant, int Seed, int VarData )」。
// ★ 契约写返回 `boolean`，但符号 `…Ejji` **没有返回值特征**（`void`）⇒ 本批按**符号**取形状
//   （G3 口径：形状按 mangled 签名取、不按文档），用 `VoidIntIntIntIntInt`。
//   ★ 语料那处也**不接返回值**（`BOIStageAPI15/.../roomHandler.lua:59`）⇒ 先这么做；
//   日后若发现模组拿返回值判断，再单独核实（**不猜**）。
// ★ 2026-10-23更正：非模板函数mangled名称通常不包含返回类型，不能由其缺失断言void。
// NRO0x4525CC/0x45263C明确返回0/1，PC0x7AAA5C返回true；本入口保留原生bool。
inline constexpr uintptr_t kRoomSpawnGridEntityOffset = 0x452528;
inline constexpr std::uint32_t kRoomSpawnGridEntityEntryWord = 0xA9BC7BFDU;

// `Entity_Player::RemoveCollectible(eCollectibleType, bool IgnoreModifiers, int ActiveSlot,
//  bool RemoveFromPlayerForm)` @ `0x299B50`，入口 `ff4302d1`。
// 符号：`_ZN15IsaacRepentance13Entity_Player17RemoveCollectibleENS_16eCollectibleTypeEbib`
// PC 契约：`EntityPlayer.md:1588`「void RemoveCollectible ( CollectibleType Type,
//   boolean IgnoreModifiers = false, ActiveSlot = ActiveSlot.SLOT_PRIMARY,
//   boolean RemoveFromPlayerForm = true )」⇒ 尾部 3 个可省（省略时保持 0，
//   而第 3 格的缺省 `SLOT_PRIMARY` 恰好是 0）。
// 语料只传 1 个（`IsaacOnTwitchReloaded/scripts/activeItems.lua` 的 8 处 `p:RemoveCollectible(id)`）。
// ★★ **清单把它记成 `ItemPool:RemoveCollectible`**（同名、另一个 owner）—— 语料里的接收者
//   是 **EntityPlayer**（`p`），按 owner 认才不会做错（批次 250 的"按 owner 区分"纪律）。
inline constexpr uintptr_t kEntityPlayerRemoveCollectibleOffset = 0x299B50;
inline constexpr std::uint32_t kEntityPlayerRemoveCollectibleEntryWord = 0xD10243FFU;

// ===========================================================================
// 批次 253（2026-10-01）：**带 `Vector2 const&` 参数**的两条
//
// ★★ 这一批的价值在于**不用扩跳板**：引擎收的是 `Vector2 const&`
//   （mangled 名里的 `RKN4KAGE4Math7Vector2E`）⇒ ABI 上就是一个**指针参数**（走 `x` 寄存器），
//   而"指针"本来就在跳板的支持范围内。做法与 `Ref2U32Pair` 同一思路：
//   把 Lua 的 Vector 拷进**我们自己栈上的 8 字节槽**，再把**槽的地址**当参数传。
//   （开工单原来预估这几条要"扩跳板"，实际不需要 —— 参数是引用，不是按值。）
// ===========================================================================

// `Room::IsPositionInRoom(Vector2 const& Pos, float Margin)` @ `0x464560`，入口 `fd7bbea9`。
// 符号：`_ZNK15IsaacRepentance4Room16IsPositionInRoomERKN4KAGE4Math7Vector2Ef`
// PC 契约：`tools/pc_contract_docs/Room.md:691`「boolean IsPositionInRoom ( Vector Pos, float Margin )」
// ⇒ 无缺省值，两个参数都必填。
// 语料实参（`BOIStageAPI15/.../roomHandler.lua` 与 `RepentancePlus`）：`room:IsPositionInRoom(pos, 0)`。
// 形状 `BoolVector2RefFloat`（本批新增）：`bool(this, Vector2&, float)`。
inline constexpr uintptr_t kRoomIsPositionInRoomOffset = 0x464560;
inline constexpr std::uint32_t kRoomIsPositionInRoomEntryWord = 0xA9BE7BFDU;

// `Game::CharmFart(Vector2 const& Position, float Radius, Entity* Source)` @ `0x35AB34`，
// 入口 `ffc302d1`。
// 符号：`_ZN15IsaacRepentance4Game9CharmFartERKN4KAGE4Math7Vector2EfPNS_6EntityE`
// PC 契约：`Game.md:102`「void CharmFart ( Vector Position, float Radius, Entity Source )」
// ⇒ 3 个参数、无缺省值；第 3 个是**实体指针**（`PNS_6EntityE` ⇒ 走 `x` 寄存器）。
// 形状 `VoidVector2RefFloatHandle`（本批新增）。
inline constexpr uintptr_t kGameCharmFartOffset = 0x35AB34;
inline constexpr std::uint32_t kGameCharmFartEntryWord = 0xD102C3FFU;

// `Game::SpawnParticles(Vector2 const& Pos, Entity_Effect::eVariant ParticleType, int NumParticles,
//                       float Speed, ColorMod const& Color, float Height, unsigned int SubType)`
// @ `0x3598F8`，入口 `d102c3ff`。
// 符号：`_ZN15IsaacRepentance4Game14SpawnParticlesERKN4KAGE4Math7Vector2ENS_13Entity_Effect8eVariantEifRKNS_8ColorModEfj`
// PC 契约：`tools/pc_contract_docs/Game.md:546`「void SpawnParticles ( Vector Pos,
//   EffectVariant ParticleType, int NumParticles, float Speed, Color Color = Color.Default,
//   float Height = 100000, int SubType = 0 )」—— 返回 `void`，后三个参数有缺省值。
// 语料：`IsaacOnTwitchReloaded` 14 处，一律 `Game():SpawnParticles(pos, EffectVariant.X, n, speed,
//   Color(...), h)` ⇒ **真实体调用**（`self` 在栈上），颜色**总是显式给**。
//
// ★ **ABI 从反汇编读出**（`python3 tools/nro_disasm.py 0x3598F8 0xB0`）：
//   `(this=x0, pos=x1, variant=w2, count=w3, speed=s0, colorMod=x4, height=s1, subtype=w5)`。
//   两处易错点都有指令为证：
//     * `00359938 mov v8.16b, v1.16b` / `0035994c fcmp s1, s0` ⇒ **第 6 个参数 `Height` 走 `s1`**
//       （`s0` 是 `Speed`），而且引擎拿它跟 `100000.0f`（`0x47c35000`，`0035992c/00359930`
//       两条 `mov/movk` 拼出来）**比一次**决定走哪条路 ⇒ 缺省值必须按契约原文传 `100000`，
//       **不能图省事传 0**（传 0 会走到另一条分支上去）。
//     * `0035993c mov x20, x4` ⇒ `ColorMod const&` 是一个**指针**（引用），不是按值；
//       它在循环里被原样交给 `Entity_Effect` 的虚函数（`00359a28/00359b34 mov x1, x20`）。
//     * 返回 `void`（没有任何往 `w0` 写的收尾）⇒ Lua 侧**不返回值**。
//
// ★ 为什么不写成数据行：那个 `ColorMod const&` **要先从 Lua 的 `Color` 句柄构造出一个 44 字节的
//   引擎对象**（`kColorModSize = 0x2C`、tint@+0x00、shift@+0x10 —— 见 `kSpriteColorOffset` 段），
//   而形状机制（`EngineCallShape`）只能表达"按某种标量宽度把 Lua 值搬进寄存器"，表达不了"构造"
//   ⇒ 这一条**必须手写处理器**（与 `Room` 那几条返回 `Vector2` 的同理，只是难点不同）。
inline constexpr uintptr_t kGameSpawnParticlesOffset = 0x3598F8;
inline constexpr std::uint32_t kGameSpawnParticlesEntryWord = 0xD102C3FFU;
//: ⚠️ 上面这个 4 字节入口指纹与 `kGameCharmFartEntryWord` **是同一个值**（两条函数的前 4 字节
//:   都是 `sub sp, sp, #0xb0`）—— 这是 4 字节指纹的固有弱点，本项目的口径是"偏移常量为主、
//:   指纹只当**冗余保险**"。真要把两者分开就得上 16 字节指纹（`kRngNextExpectedBytes` 那种），
//:   而手写处理器这一族目前一律用 4 字节 ⇒ 保持与同族一致，不为这一条单独开机制。

// ===========================================================================
// 批次 254（2026-10-01）：ItemPool 接收者 + 5 条引擎方法（**全部走数据行**）
//
// 偏移与入口指纹一律从**动态符号表**直接取（`tools/nro_symbols.py` 的
// `parse_dynamic_symbols`），再用 NRO 里那 4 个入口字节核对 —— 与批次 239/252 同一套口径。
// ===========================================================================

// `Game::MoveToRandomRoom(bool IAmErrorRoom, int Seed, Entity_Player* Player)` @ `0x35406C`，
// 入口 `fd7bbda9`。
// 符号：`_ZN15IsaacRepentance4Game16MoveToRandomRoomEbjPNS_13Entity_PlayerE`
// PC 契约：`tools/pc_contract_docs/Game.md:424`「void MoveToRandomRoom ( boolean IAmErrorRoom,
//   int Seed, EntityPlayer Player )」—— 3 个参数、无缺省值。
// ★ 反汇编 `0x35406C`：`and w1,w1,#1`（布尔）→ `Level::GetRandomRoomIndex(w1,w2)` 取目标格 →
//   尾跳到 `Game::StartRoomTransition(格, -1, 3, player, -1)` ⇒ 参数就是 `(bool, int, 指针)`，
//   返回 void。第 3 个是**裸实体指针**（`PNS_13Entity_PlayerE`）⇒ 用 `Handle` 种类、
//   `nil` = 空指针。
// 语料实参 3 个：`BOIStageAPI15/scripts/stageapi/core/callbacks.lua:142` 的
// `shared.Game:MoveToRandomRoom(false, shared.Room:GetSpawnSeed(), player)`。
// 形状 `VoidBoolIntHandle`（本批新增）。
inline constexpr uintptr_t kGameMoveToRandomRoomOffset = 0x35406C;
inline constexpr std::uint32_t kGameMoveToRandomRoomEntryWord = 0xA9BD7BFDU;

// `ItemPool::RemoveCollectible(eCollectibleType Collectible, bool, bool)` @ `0x3C61F0`，
// 入口 `fd7bbda9`。
// 符号：`_ZN15IsaacRepentance8ItemPool17RemoveCollectibleENS_16eCollectibleTypeEbb`
// PC 契约：`tools/pc_contract_docs/ItemPool.md:96`「boolean RemoveCollectible (
//   CollectibleType Collectible )」+ 正文「Removes a collectible from the itempool.
//   Returns true if given item did exist in the pool before.」。
// ★ PC 只写 1 个参数、引擎符号是 **3 格** ⇒ 按符号取形状（G3 口径）。
// ★ 反汇编 `0x3C61F0`（`<=0x108`）证实两个额外 `bool` 的含义：
//   * 第 2 个 `bool`（`w2`，位 0）置位时才去 `ItemConfig::GetCollectible` + `Item::IsAvailable`
//     做有效性判定；不置位直接进"查/删"那一段。
//   * 第 3 个 `bool`（`w3`，位 0）置位时**只查不删**（`tbnz w19,#0` 直接返回、不 OR 那一位）。
//   * 返回值 `bool`：`tst x10,x11; cset w0, eq` = "这一位原本没置位 ⇒ 该收藏品本来在池里"，
//     与 PC 正文那句逐字一致。
//   ⇒ 省略两个 `bool`（保持 0）恰好就是 PC 文档描述的行为（查 + 删）。
// 语料实参 1 个：`RepentancePlus/RepentancePlus/main.lua:474` 的
// `isUnlocked = itemPool:RemoveCollectible(collectibleType)`（还在用返回值）。
// 形状 `BoolIntBoolBoolOpt2`（本批新增；尾部 2 个可省）。
inline constexpr uintptr_t kItemPoolRemoveCollectibleOffset = 0x3C61F0;
inline constexpr std::uint32_t kItemPoolRemoveCollectibleEntryWord = 0xA9BD7BFDU;

// `Entity_Player::AddKeys(int Amount)` @ `0x2804E8`，入口 `08d456b9`。
// 符号：`_ZN15IsaacRepentance13Entity_Player7AddKeysEi`
// PC 契约：`tools/pc_contract_docs/EntityPlayer.md:295`「void AddKeys ( int Amount )」
//   + 正文「Adds keys to the player. Remove them with negative numbers.」。
// ⇒ ABI 就是 `void(this, i32)`、**1 个整数参数**（负数表示移除）⇒ 复用现成的 `Void1`。
// 语料实参：负数/正数都出现过（`IsaacOnTwitchReloaded/main.lua:569` 的 `p:AddKeys(req.value)`
//   与 `RepentancePlus/main.lua:1321` 的 `Player:AddKeys(-Player:GetNumKeys())`）。
inline constexpr uintptr_t kEntityPlayerAddKeysOffset = 0x2804E8;
inline constexpr std::uint32_t kEntityPlayerAddKeysEntryWord = 0xB956D408U;

// `Entity_Player::AddGoldenKey()` @ `0x280588`，入口 `08db8252`。
// 符号：`_ZN15IsaacRepentance13Entity_Player12AddGoldenKeyEv`
// PC 契约：`tools/pc_contract_docs/EntityPlayer.md:262`「void AddGoldenKey ( )」
// ⇒ 无参、返回 void ⇒ 复用现成的 `Void0`。
// 语料实参 0 个：`IsaacOnTwitchReloaded/main.lua:567` 的 `p:AddGoldenKey()`。
inline constexpr uintptr_t kEntityPlayerAddGoldenKeyOffset = 0x280588;
inline constexpr std::uint32_t kEntityPlayerAddGoldenKeyEntryWord = 0x5282DB08U;

// `Entity_Player::AddGoldenBomb()` @ `0x2FC3F0`，入口 `28db8252`。
// 符号：`_ZN15IsaacRepentance13Entity_Player13AddGoldenBombEv`
// PC 契约：`tools/pc_contract_docs/EntityPlayer.md:244`「void AddGoldenBomb ( )」
// ⇒ 无参、返回 void ⇒ 复用现成的 `Void0`。
// 语料实参 0 个：`IsaacOnTwitchReloaded/main.lua:572` 的 `p:AddGoldenBomb()`。
inline constexpr uintptr_t kEntityPlayerAddGoldenBombOffset = 0x2FC3F0;
inline constexpr std::uint32_t kEntityPlayerAddGoldenBombEntryWord = 0x5282DB28U;

// ===========================================================================
// 批次 242（2026-09-30）：**下转族**（`Entity:ToNPC`/`ToTear`/`ToLaser`/`ToEffect`/`ToKnife`）
//
// 口径与既有的 `ToPlayer`/`ToPickup`/`ToFamiliar`/`ToProjectile` **逐字相同**：
// `vptr` **精确等于** `base + <类>VtableOffset`（引擎里这几类都不是"每种子类一个 vtable"的风格）。
//
// ★ 常量 = **vtable 符号的 `file_offset` + 0x10**（对象里的 `vptr` 指向 vtable 的"函数表"起点，
//   前面 16 字节是 offset-to-top 与 typeinfo）。这条关系用已有的 4 条**逐条复核**过：
//   `Entity_Pickup` 符号 `0xa36e18` ↔ 常量 `0xA36E28`、`Entity_Player` `0xa37100` ↔ `0xA37110`、
//   `Entity_Projectile` `0xa37400` ↔ `0xA37410`、`Entity_Familiar` `0xa35718` ↔ `0xA35728`
//   —— 四条**全部**差 `0x10`。
//
// ★★ 批次 242 曾在这里断言"精确 vptr 对 `Entity_NPC` 也成立"，依据是"动态符号表里 71 个
//   `_ZTV` 没有敌人子类"。**那个断言已被批次 243 证伪**：`_ZTV` 只是**导出**的那一部分；
//   按"长度前缀"正确解析嵌套名之后，`Entity_NPC` 有 **49 个子类**
//   （`_Beast`/`_Chimera`/`_Dogma`/`_Mother`/`_UltraWar`/`_VisageMask` …）。
//   ⇒ 只有 `Entity_Effect`/`Tear`/`Laser`/`Knife` 这 4 条能用精确 vptr（它们**各 0 个子类**，已核）；
//     `Entity_NPC` **不能**，它的判据在 `EntityToNpc` 里改成"区间 − 13 个非 NPC 直接子类"。
//   ★ 教训：**"某个符号没出现"不等于"那个东西不存在"** —— 动态符号表是导出的子集，
//     判"某类有没有子类"必须按 mangled 名正确解析，不能靠"扫 `_ZTV` 没扫到"。
// ===========================================================================

// `_ZTVN15IsaacRepentance10Entity_NPCE` @ `0xA35DA8`（+0x10 = 常量）。
inline constexpr uintptr_t kEntityNpcVtableOffset = 0xA35DB8;
// `_ZTVN15IsaacRepentance11Entity_TearE` @ `0xA37628`。
inline constexpr uintptr_t kEntityTearVtableOffset = 0xA37638;
// `_ZTVN15IsaacRepentance12Entity_LaserE` @ `0xA35CB0`。
inline constexpr uintptr_t kEntityLaserVtableOffset = 0xA35CC0;
// `_ZTVN15IsaacRepentance13Entity_EffectE` @ `0xA35228`。
inline constexpr uintptr_t kEntityEffectVtableOffset = 0xA35238;
// `_ZTVN15IsaacRepentance12Entity_KnifeE` @ `0xA35B38`。
inline constexpr uintptr_t kEntityKnifeVtableOffset = 0xA35B48;

// ---- 批次 243（2026-09-30）：`ToNPC` 判据修正所需的"非 NPC 直接子类"vtable -------------------
//
// ★★ 为什么需要它们（**批次 242 的缺陷**）：242 把 `ToNPC` 写成"vptr 精确等于 `Entity_NPC` 的
// vtable"，依据是"符号表里 71 个 `_ZTV` 里没有敌人子类"。**那个依据是错的** ——
// `_ZTV` 只是**导出的**那些；按"长度前缀"正确解析嵌套名之后，`Entity_NPC` 有 **49 个子类**
// （`Entity_NPC_Beast`/`_Chimera`/`_Dogma`/`_Mother`/`_UltraWar`/`_VisageMask` …，全是有独立
// `UpdateAI` 的 BOSS/精英），它们的 vtable **不在动态符号表里** ⇒ 精确比对待遇它们**全部返回 nil**。
//
// ⇒ 正确的判据是**"`Entity` 家族区间内、且不属于那 13 个已知非 NPC 类"**：
//   按长度前缀解析后，**`Entity` 的直接子类恰好是 13 个**，除 `Entity_NPC` 之外全部列在下面。
//   `Entity` 家族区间（既有 `kEntityVtableRangeBeginOffset`/`EndOffset`）覆盖全部子类，
//   所以"区间内"这一条能容纳那 49 个没导出的 vtable，而"排除 13 个"把兄弟类挡掉。
//
// ★ 交叉验证：本段的 `kEntityBaseVtableOffset` = `0xA34F58` **正好等于**既有的
//   `kEntityVtableRangeBeginOffset` —— 区间起点就是 `Entity` 自己的 vtable，两处独立得到同一个数。
inline constexpr uintptr_t kEntityBaseVtableOffset = 0xA34F58;  // `Entity` 本体（区间起点）
inline constexpr uintptr_t kEntityBombVtableOffset = 0xA35048;
inline constexpr uintptr_t kEntityDummyVtableOffset = 0xA35140;
inline constexpr uintptr_t kEntitySlotVtableOffset = 0xA37508;
inline constexpr uintptr_t kEntityTextVtableOffset = 0xA37730;

// ---- 批次 245（2026-10-01）：`Entity.HitPoints` / `MaxHitPoints` / 伤害缓冲 -------------------
//
// ★ PC 契约 `tools/pc_contract_docs/Entity.md:750`：「**float** HitPoints」；`:774` 同样是
//   「**float** MaxHitPoints」；`:754` 还写明「HitPoints 不是挨打就立刻减，**要到下一帧才更新**」。
//   ⇒ 这两个是**浮点**字段（不是整数），而且减血**不在 `TakeDamage` 里**。
//
// ★★ 两条互证的取证（这是本批能定案的关键）：
//
//   ① `Entity::HasMortalDamage() @ 0x5E260`（**只有 20 字节**，一条判据）：
//        ```
//        ldr  s0, [x0, #0x20]      ; 伤害缓冲
//        ldr  s1, [x0, #0x354]     ; HitPoints
//        fcmp s0, s1
//        cset w0, ge               ; return 缓冲 >= 血量
//        ```
//      与契约 `Entity.md:451` 逐字吻合：「The game adds taken damage to a **damage buffer**,
//      which gets applied in the next frame. HasMortalDamage() returns true if the **buffered
//      damage is enough to kill** the entity.」
//
//   ② `Entity::AddHealth(float) @ 0x5A248`（**只有 52 字节**）—— 逐条就是 PC 的 `AddHealth`：
//        ```
//        ldr  s1, [x0, #0x354]     ; s1 = HitPoints
//        fadd s0, s1, s0           ; s0 = HitPoints + 入参
//        str  s0, [sp, #0xc]
//        ldr  s1, [x0, #0x358]     ; s1 = MaxHitPoints
//        fcmp s0, s1
//        add  x8, x0, #0x358       ; MaxHitPoints 的地址
//        add  x9, sp, #0xc
//        csel x8, x9, x8, mi       ; 取「(HP+入参)」还是「MaxHitPoints」，取决于谁更小
//        ldr  w8, [x8]
//        str  w8, [x0, #0x354]     ; 写回 HitPoints = min(HP+入参, MaxHitPoints)
//        ```
//      ⇒ `+0x354` 就是被读-改-写的那一格（HitPoints），`+0x358` 是它的上限（MaxHitPoints）。
//
// ★ 为什么它们属于 **`Entity` 基类**（因此对任何实体都成立、**写入不需要判类型**）：
//   `AddHealth`/`HasMortalDamage` 都是 `IsaacRepentance::**Entity**::` 的方法（符号名里没有子类前缀），
//   而 PC 也把这两个字段挂在 `Entity` 页上（`Entity.md:750/774`），不是 `EntityNPC` 页。
//
// ★ 上游为什么一直没找到它们：`TakeDamage` 里**没有任何减血**（契约 `:754` 解释了：下一帧才更新）
//   ⇒ 在 `TakeDamage` 里翻偏移是**翻不到的**；正确入口是 `AddHealth`（读-改-写同一格）与
//   `HasMortalDamage`（把两格放在同一条 `fcmp` 里）。
inline constexpr uintptr_t kEntityHitPointsOffset = 0x354;     // float
inline constexpr uintptr_t kEntityMaxHitPointsOffset = 0x358;  // float
// `Entity + 0x20` = **伤害缓冲**（float）。它不是 PC 的 Lua 字段（PC 没暴露），
// 但它是 `HasMortalDamage` 的另一个操作数，登记在这里是为了让那条判据可复核。
inline constexpr uintptr_t kEntityDamageBufferOffset = 0x20;

// ---- 批次 246（2026-10-01）：`EntityNPC.Scale` ---------------------------------------------
//
// PC 契约 `tools/pc_contract_docs/EntityNPC.md:223/225`：「### Scale … #### **float** Scale」
// （**挂在 `EntityNPC` 页上**，不是 `Entity` 页 ⇒ 这个字段只对 NPC 家族成立）。
//
// ★ 取证（两条互证，都是"这个类的 setter 自己写的格"）：
//   ① `Entity_NPC::SetScale(float) @ 0x10FCD8`：`str s0, [x0, #0xcc4]` —— 把**入参原样**写进本格；
//   ② `Entity_NPC::update_sprite_scale() @ 0x11B2B4`（名字就是"把 scale 应用到 sprite"）：
//        `ldr s0, [x0, #0xcc4]`（本格）× `ldr s1, [x0, #0x388]` → `fmul` → 缩放进来的尺寸
//        交给 `Vector2::operator*` → `Vector2::operator=` 写 `Entity + 0x12C`（Size）。
//      ⇒ 本格是"NPC 自己的缩放系数"，乘上 `+0x388`（另一个基数）得到实际尺寸。
//
// ★ 全镜像里 **17 个函数**访问本格（`SetScale`/`update_sprite_scale`/`MakeChampion`/`TrySplit`/
//   `Update` …），全都属于 `Entity_NPC`（或它的子类）⇒ 与"这是 NPC 字段"一致。
//   `+0x388` 是什么（另一个基数）**未取证**，本批不碰。
//
// ★ 为什么写它不需要"顺手改 Size"：引擎自己的 `Entity_NPC::Update` 每帧会调
//   `update_sprite_scale()`，把本格乘进 Size ⇒ **写本格就等于改缩放**，与 PC 的语义一致
//   （PC 那一边写 `Scale` 也是下一帧生效）。
//
// ★ 只对 NPC 家族成立 ⇒ 读/写都要先过"是不是 NPC 家族"这道判据（见 `IsNpcFamilyEntity`），
//   否则会把别的实体的某个无关 float 当成 Scale 读/写。
inline constexpr uintptr_t kEntityNpcScaleOffset = 0xCC4;

// ---- 批次 249（2026-10-01）：`Room` 三个**返回 Vector** 的方法 --------------------------------
//
// `Room:GetCenterPos()` / `GetGridPosition(int)` / `GetRandomPosition(float)`。
// 它们落在工作清单的 `needs_struct_return`（"跳板只支持标量返回 ⇒ 必须手写"）里。
//
// ★★ 但**清单里那条"16 字节值类型、走 x8 间接结果寄存器"的说法对这三条是错的**：
//   反汇编 `Room::GetGridPosition(int) @ 0x454D38`（`_ZNK15IsaacRepentance4Room15GetGridPositionEi`）看到
//   ```
//   add  x0, sp, #0x8          ; 在栈上构造临时 Vector2
//   bl   KAGE::Math::Vector2::Vector2(float, float)
//   ldp  s0, s1, [sp, #0x8]    ; 把它读进 s0 / s1
//   ret                        ; ⇒ 用**两个 SIMD 寄存器**返回，不是 x8、也不是 16 字节
//   ```
//   ⇒ `Vector2` 是 **8 字节**（两个 float，与 Lua 的 `Vector` 同布局），按 AAPCS64 走 `s0`/`s1`。
//   ★ 于是**手写时可以直接声明一个"两个 float 的结构体"按值返回**，不必扩跳板 ——
//     仓库里已有同形的先例：`RoomDoorPosition` + `RoomGetDoorSlotPosition()`
//     （`remaining_api.cpp`，`Room::GetDoorSlotPosition` 也是这么返回的。
//
// ★ `GetCenterPos` 的 `br x11` 那段是按**房间形状**分派的跳表（`w9 - 9 <= 3` ⇒ 只对
//   某几种形状走特殊分支），但每条分支的返回也是同一对 `s0`/`s1`。
inline constexpr uintptr_t kRoomGetCenterPosOffset = 0x456250;
inline constexpr std::uint32_t kRoomGetCenterPosEntryWord = 0xD100C3FFU;
inline constexpr uintptr_t kRoomGetGridPositionOffset = 0x454D38;
inline constexpr std::uint32_t kRoomGetGridPositionEntryWord = 0xD10083FFU;
inline constexpr uintptr_t kRoomGetRandomPositionOffset = 0x456110;
inline constexpr std::uint32_t kRoomGetRandomPositionEntryWord = 0xD10183FFU;

// ---- 批次 259（2026-10-01）：`Room` 四条**位置类**方法（同样返回 `Vector2`，同样手写）-------
//
// `Room:FindFreePickupSpawnPosition(Vector,…)` / `GetClampedPosition(Vector,float)` /
// `FindFreeTilePosition(Vector,float)` / `GetDoorSlotPosition(DoorSlot)`。
// 它们的 PC 契约在 `tools/pc_contract_docs/Room.md` 的 **78 / 152 / 83 / 291** 行。
//
// ★ 工作清单把它们归在 `needs_new_shape`（"参数里有向量/枚举 ⇒ 先扩一种形状能力"）。
//   逐条核对 **mangled 签名**之后结论与批次 253 相同：**不需要扩任何能力** ——
//   `Vector` 参数在 ABI 上是 **`Vector2 const&`（引用 ⇒ 指针，走 `x` 寄存器）**：
//   ```
//   _ZNK15IsaacRepentance4Room27FindFreePickupSpawnPositionERKN4KAGE4Math7Vector2Efbb
//                                                          ^^^^ const 引用
//   _ZNK15IsaacRepentance4Room18GetClampedPositionERKN4KAGE4Math7Vector2Effff
//   _ZNK15IsaacRepentance4Room20FindFreeTilePositionERKN4KAGE4Math7Vector2Ef
//   _ZNK15IsaacRepentance4Room19GetDoorSlotPositionENS_9eDoorSlotE      (无数值参数，只有枚举)
//   ```
//   ⇒ 四条都走**手写处理器**（与批次 249 的三条同一条路），理由同前：**跳板只支持标量返回**，
//     而这四条返回 `Vector2`。
//
// ★★ 四条都实机离线核过"返回值走 `s0`/`s1`"（`python3 tools/nro_disasm.py <偏移> <长度>`）：
//   * `GetDoorSlotPosition @ 0x464B8C`（132 字节，叶函数）：越界分支
//     `ldp s0, s1, [x8]`（读 `KAGE::Math::Vector2::Zero`）、命中分支末尾
//     `ldp s0, s1, [sp, #0x8]` + `ret`；
//   * `FindFreePickupSpawnPosition @ 0x455BFC` 末尾 `mov v0.16b, v8.16b` /
//     `mov v1.16b, v9.16b` + `ret`（**同时**证明第 2 个参数 `x1` 是 `Vector2` 指针：
//     开头 `ldp s0, s1, [x1]` 把它按两个 float 读出来）；
//   * `FindFreeTilePosition @ 0x488050` 末尾 `ldp s0, s1, [sp, #0x10]` + `ret`
//     （开头同样是 `ldp s0, s1, [x1]`）；
//   * `GetClampedPosition @ 0x4842A0` 末尾 `mov v0.16b, v8.16b` + `ldr s1, [sp, #0x2c]` + `ret`。
//   ⇒ "声明一个两个 float 的结构体、按值返回"就对得上（`RoomDoorPosition` 已是这个形状）。
//
// ★ `GetClampedPosition` 的**符号有 5 个参数、PC 文档只写 2 个**（`Pos, Margin`）：多出来的
//   三个 float 是文档没写的缺省值。**PC 的绑定层把 `Margin` 复制给全部四个 float**
//   （`isaac-ng.exe` 的绑定函数 `VA 0x427710`：`movss xmm3,[ebp+0x10]` 之后连续三次
//   `movss [esp+0x8]/[esp+0x4]/[esp]`，然后在 `call Room::GetClampedPosition`）——
//   与函数体一致（`minX += f0` / `minY += f1` / `maxX -= f2` / `maxY -= f3`
//   ⇒ 四个都等于 `Margin` 时正是"四面各留 Margin"），所以我们也传四个 `Margin`。
inline constexpr uintptr_t kRoomFindFreePickupSpawnPositionOffset = 0x455BFC;
inline constexpr std::uint32_t kRoomFindFreePickupSpawnPositionEntryWord = 0xD10303FFU;
inline constexpr uintptr_t kRoomGetClampedPositionOffset = 0x4842A0;
inline constexpr std::uint32_t kRoomGetClampedPositionEntryWord = 0xD10243FFU;
inline constexpr uintptr_t kRoomFindFreeTilePositionOffset = 0x488050;
inline constexpr std::uint32_t kRoomFindFreeTilePositionEntryWord = 0xD10203FFU;

// ---- 批次 262（2026-10-01）：`Isaac.GridSpawn` 的随机源 -----------------------------------------
//
// `IsaacRepentance::RandomU32()`（无参、返回 `unsigned`）。**这是引擎自己给网格实体打种子的那个函数**
// —— `runtime_constants.hpp` 的 `kGridEntityTypeOffset` 段早就记过：`+0x18` 是
// `GridEntity::Init(unsigned)` 写的槽，而**所有创建路径都给它 `RandomU32()`**
// （`make_door @ 0x454FC4` / `make_wall @ 0x454E2C` / `Room::SpawnGridEntity` 的第 4 实参）。
//
// 取证：`python3 tools/nro_disasm.py 0x35830 0x14` —— 20 字节的叶函数，正文就三句：
//   `stp x29, x30, [sp, #-0x10]!` / `mov x29, sp` / `bl genrand_int32` / `ldp …; ret`
// ⇒ 返回值在 `w0`、**无参数**。入口首字 = `0xA9BF7BFD`（`stp x29,x30,[sp,#-0x10]!`）。
// 符号名出自动态符号表 `_ZN15IsaacRepentance9RandomU32Ev`。
inline constexpr uintptr_t kRandomU32Offset = 0x35830;
inline constexpr std::uint32_t kRandomU32EntryWord = 0xA9BF7BFDU;

// 批次 272（2026-10-02）：`GridEntity:Init(int Seed)` @ `0x37E438`
// （`_ZN15IsaacRepentance10GridEntity4InitEj`，arity 1，PC 契约 `GridEntity.md` 的
// `void Init ( int Seed )`），语料 15 处。
//
// 反汇编前六句（`python3 tools/nro_disasm.py 0x37e438 0x20`）给出三件事：
//   `str wzr,[x0,#0x40]` / **`str w1,[x0,#0x18]`** / `ldr x8,[x0]` + `ldr x8,[x8,#0x58]`
//   ① **`w1` 就是 `Seed`**（AAPCS64 下"`this` + 一个 int"的标准位置；契约也只有一个参数）；
//   ② 它把种子写进 **`GridEntity + 0x18`` —— 与上面 `kRandomU32Offset` 那段里**早就记过**的一句
//      「`+0x18` 是 `GridEntity::Init(unsigned)` 写的槽，而所有创建路径都给它 `RandomU32()`」
//      **互证**（那条记录是批次 262 为 `Isaac.GridSpawn` 的随机源做的）⇒ 两条独立记录指向同一件事；
//   ③ 随后那句 `ldr x8,[x8,#0x58]` 是**虚表调用**：引擎自己在 `Init` 内部再分派到各子类的
//      `InitSubclass()` ⇒ 我们调基类这一条**正是** PC 走的那条路径，不存在"绕过子类逻辑"的问题
//      （对比 `Entity:TakeDamage` 那种"基类与子类各有一份实现、必须挑一个"的情形）。
//   ★ 同地址附近还有 `GridEntity::Init(Desc const&)` @ `0x37E4BC` —— **不同重载**，别混。
inline constexpr uintptr_t kGridEntityInitOffset = 0x37E438;
inline constexpr std::array<u8, 16> kGridEntityInitExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x00, 0x40, 0xF9,
};

// ---- 批次 279（2026-10-02）：`Sprite`（引擎 `ANM2`）的 overlay 三条 --------------------------
// 符号都在 `ANM2` 上（以撒引擎里 Lua 的 `Sprite` 就是 `ANM2` —— 本仓库既有的 `kSprite*Offset`
// 全落在 ANM2 的地址区间里）。这三条**只需要 `char const*`**（`PlayOverlay` 与
// `SetOverlayFrame` 各有 `std::string const&` 重载，我们选 `char const*` 的那个，
// 避开 libc++ `std::string` 的 ABI 桥 —— 与 `Sprite` 绑定表「第一步只收 char const*」同一条策略）。
inline constexpr uintptr_t kSpriteSetOverlayFrameOffset = 0xAEF8;
inline constexpr std::array<u8, 16> kSpriteSetOverlayFrameExpectedBytes = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};

// ---- 批次 283（2026-10-02）：`Sprite` 的四条「按名字查询」------------------------------------
// 引擎侧签名统一是 `bool ANM2::Xxx(std::string const&) const`（mangled 全是
// `_ZNK15IsaacRepentance4ANM2…ERKNSt3__112basic_string…`）⇒ 参数是 **libc++ 的
// `std::string const&`**，与 `Load` / `ReplaceSpritesheet` 同一个 ABI 关口。
// ★ 所以这四条**不能**走 overlay 那三条「只收 `char const*`」的路子，必须借既有的
//   `BuildNativeString` 桥（`sprite_api.cpp`）—— 那一步已经实测过 libc++ 的 24 字节 SSO 布局。
//
// ★★ 为什么必须给这四条各配一段"孪生函数"的说明：**光看前 16 字节守卫分不出它们是两个函数**。
//   * `IsOverlayPlaying`@`private:kSpriteIsOverlayPlayingOffset` 与 `IsOverlayFinished`@`private:kSpriteIsOverlayFinishedOffset`：**前 0x1C 字节逐字节相同**。
//     首个不同的指令落在"动画名为空"那一步的**取反**上（A 侧 `cbz w9` / B 侧 `cbnz w9`）
//     ⇒ 语义互补（在播 / 已播完）正是这一对的定义 ⇒ 这条**可以当互证**。
//   * `IsEventTriggered`@`private:kSpriteIsEventTriggeredOffset` 与 `WasEventTriggered`@`private:kSpriteWasEventTriggeredOffset`：**前 0x54 字节逐字节相同**。
//     首个不同字节是那个 `bl` 的**位移**（A 侧 `0x94199138` / B 侧 `0x941990E3`），
//     而两者算出来的**目标地址是同一个**（`0x6FFBA0`）⇒ 那只是"调用点地址不同"，
//     **不是语义差异**。★ 实质差异在更后面（各自查自己的事件表）⇒ 所以这一对
//     **不能**靠"前段字节相同"去判断"是不是同一个函数"，定案依据只能是 **dynsym 的 mangled 名字**
//     （两者各有独立符号，逐字在名字表里）。

// ---- 批次 281（2026-10-02）：`EntityTear:ChangeVariant`（视图化的第一条方法）--------------
// `Entity_Tear::ChangeVariant(int)` @ `0x3412D8`（arity **1** = 契约 `ChangeVariant(TearVariant)`
// 的一个参数 ✓；**同名方法只有一个类有**）。
inline constexpr uintptr_t kEntityTearChangeVariantOffset = 0x3412D8;
inline constexpr std::array<u8, 16> kEntityTearChangeVariantExpectedBytes = {
    0xFF, 0x83, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF7, 0x1B, 0x00, 0xF9,
};

// ---- 批次 282（2026-10-02）：`EntityLaser:SetActiveRotation`（视图化的第二条）--------------
// `Entity_Laser::SetActiveRotation(unsigned, float, float, bool)` @ `0xF7540`
// （arity **4** = 契约 `SetActiveRotation(int Delay, float AngleDegrees, float RotationSpd,
// boolean TimeoutComplete)` 的四个参数 ✓；**同名方法只有一个类有**）。
// ★ 同族的 `ShootAngle` **不收** —— 它的引擎符号是 **7 参**（PC 契约只写 6 ⇒ 多一个尾参 `bool`），
//   按批次 278 立的「参数个数必须与契约页对齐」规则排除。
inline constexpr uintptr_t kEntityLaserSetActiveRotationOffset = 0xF7540;
inline constexpr std::array<u8, 16> kEntityLaserSetActiveRotationExpectedBytes = {
    0x28, 0x00, 0x80, 0x52, 0x08, 0xA0, 0x13, 0x39,
    0x01, 0xEC, 0x04, 0xB9, 0x00, 0xF0, 0x04, 0xBD,
};

// ---- 批次 284（2026-10-02）：`EntityPlayer` 两条查询 + `GridEntityDoor` 三条 -------------------
//
// 先说**这一批怎么筛的**，因为本批更正了批次 273 留下的一句话：
//
// ★★★ 「同名方法只能有一个类有」这条规则的正确做法 = **扫全镜像里的 mangled 名字**，
//   不是"在 dynsym 里没看见别的就算没有"（dynsym 只是导出子集），更不是"名字眼熟就当有重写"。
//   做法：把 `Repentance.nro` 整个读进来，正则找 `_ZN15IsaacRepentance\w*<方法名>E\w*`，
//   把命中的 mangled 名字列全 —— 命中几条就是几个实现。
//
// ★★ **更正**：批次 273 在目录里写过「`GridEntityDoor:Open/Close` 那种**有重写**的不收」。
//   本次实测（同一把尺子）：`GridEntity_Door::Open()` 与 `GridEntity_Door::Close(bool)`
//   在整个镜像里**各只有一条** mangled 名字 ⇒ **没有子类重写**。
//   当初那句话多半是把 `Entity_NPC_HornfelDoor::Open(int)` / `Close()` 看成了重写 ——
//   那是**另一个类**（NPC，不是 `GridEntity_Door` 的子类），只是方法名撞了。
//   ⇒ 这两条本批**收下**。★ 273 那句老话已在 `api_catalog.cpp` 原地更正。
//
// ★ 用同一把尺子筛掉的（都**不收**，写在这里免得下次再查一遍）：
//   * `Entity:CanShutDoors()` —— 4 个实现（`Entity` / `Entity_NPC` / `Entity_Familiar` /
//     `Entity_Projectile`）⇒ 有重写。★ 另外它报告里那个偏移 `0x67578` 落在**导入跳板区**，
//     守卫是 `mov x0, xzr; ret` 两条 —— **那根本不是函数体**，是"返回空"的桩。
//   * `GridEntity:PostInit()` —— 8 个实现（`GridEntity` + Pit/Poop/Rock/Wall/Statue/Gravity）
//     ⇒ 有重写。★ 报告给的 `GridEntity::PostInit` @`0x380C34` 本身只有一条 `ret`（空函数）
//     ⇒ 就算调它也拿不到子类那份实现。
//   * `GridEntity:Destroy(bool)` —— `GridEntity` / `GridEntity_TNT` / `GridEntity_Web` /
//     `GridEntity_Door` 都有 ⇒ 有重写。★ 且 `0x380C40` 那条是**虚分派转发**
//     （`ldr x8,[x0]; mov w1,#4; ldr x2,[x8,#0x28]; br x2`）—— 它把调用者传进来的
//     `Immediate` **丢掉、改成常量 4** ⇒ 直调它连参数语义都不对。
//   * `Entity:IsVulnerableEnemy()` —— 只有一条实现，但引擎签名是
//     `Entity::IsVulnerableEnemy(Entity*) const`（PC 契约是 **0 参**）。那第二个实参是
//     **"来源实体"**：`0x5C67C` 上 `cbz x1, …` 空指针直接短路，非空时还会顺着
//     `[x1 + 0x3A8]` 追一条链（`0x5C690` 起的循环）⇒ **传什么进去会改变返回值**，
//     而 PC 那个无参重载到底传了什么**无从确定** ⇒ 按纪律**不猜**。
//     ★ 这是目前单条调用点最多的未做项（**22 处**），值得单独一批去 PC 侧取证
//     （按 `docs/会话交接-20261001-二-语料API恢复与字段取证.md` 的配方找绑定点、反汇编看它传什么）。
//
// 下面五条都是"只有一个实现 + 参数个数与契约页相等"：
//   * `Entity_Player::IsHoldingItem() const` @ `0x2929D0`（arity 0 ✓）
//   * `Entity_Player::IsExtraAnimationFinished() const` @ `0x2B78C4`（arity 0 ✓；
//     ★ 它的起点是**裸代码**（`mov w8,#0x1710; add x8,x0,x8; ldrb w9,[x8]…`）——
//     前一条指令是别的函数的 `bl`，所以 0x2B78C4 确实是函数头，不是中段）
//   * `GridEntity_Door::Open()` @ `0x385894`（arity 0 ✓）
//   * `GridEntity_Door::Close(bool)` @ `0x3820F4`（arity 1 ✓；★ 反汇编确认 `w1` **真被用**：
//     `0x382110: tbnz w1, #0, 0x382120` —— variant==1 且"不强制"时直接返回，其余才真去关）
//   * `GridEntity_Door::IsTargetRoomArcade() const` @ `0x386038`（arity 0 ✓）
inline constexpr uintptr_t kEntityPlayerIsHoldingItemOffset = 0x2929D0;
inline constexpr std::array<u8, 16> kEntityPlayerIsHoldingItemExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x24, 0x42, 0xF9,
};
inline constexpr uintptr_t kEntityPlayerIsExtraAnimationFinishedOffset = 0x2B78C4;
inline constexpr std::array<u8, 16> kEntityPlayerIsExtraAnimationFinishedExpectedBytes = {
    0x08, 0xE2, 0x82, 0x52, 0x08, 0x00, 0x08, 0x8B,
    0x09, 0x01, 0x40, 0x39, 0x69, 0x00, 0x00, 0x34,
};
inline constexpr uintptr_t kGridEntityDoorOpenOffset = 0x385894;
inline constexpr std::array<u8, 16> kGridEntityDoorOpenExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF4, 0x4F, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x18, 0x43, 0xB9,
};
inline constexpr uintptr_t kGridEntityDoorCloseOffset = 0x3820F4;
inline constexpr std::array<u8, 16> kGridEntityDoorCloseExpectedBytes = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0x08, 0x10, 0x40, 0xB9,
};
inline constexpr uintptr_t kGridEntityDoorIsTargetRoomArcadeOffset = 0x386038;
inline constexpr std::array<u8, 16> kGridEntityDoorIsTargetRoomArcadeExpectedBytes = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};

// ============================================================================
// 批次 285（2026-10-02）：`Morph` 家族两条（`EntityNPC` 视图 + 两条引擎方法数据行）
// ============================================================================
//
// 三条硬门槛都过（判据 = 扫**全镜像**的 mangled 名，见 `AGENTS.md` 与批次 284）：
//   * 引擎符号存在（两条 mangle 名逐字在 `Repentance.nro` 里）；
//   * **同名方法只有一个类有实现** —— `Morph` 在整份镜像里只有 `Entity_NPC::Morph` 与
//     `Entity_Pickup::Morph` 两条命中；它们是**兄弟类**（都是 `Entity` 的直接子类），
//     不是重写关系 ⇒ 两条都能直调基类地址（不涉及虚分派）。
//   * 参数个数与 PC 契约相等（4 = 4、6 = 6，见下）。
//
// `Entity_NPC::Morph(eEntityType, u32 Variant, u32 SubType, int ChampionColorIdx)`
//   符号 `_ZN15IsaacRepentance10Entity_NPC5MorphENS_11eEntityTypeEjji`（arity **4** ✓）。
//   PC 契约 `tools/pc_contract_docs/EntityNPC.md:117` 逐字：
//     `boolean Morph ( EntityType type, int Variant, int SubType, int ChampionColorIdx )`；
//   正文 `:119` 说 `ChampionColorIdx` 传 `-1` 表示"不加冠军颜色"（`:::lua -1`）。
//   反汇编（`0x10FAF4`，长度上界 `0x1E4` —— 下一个符号是 `Entity_NPC::SetScale` @ `0x10FCD8`）：
//     `ldr w8,[x0,#0x38]` 后 `cmp w8,w1` —— 当前 `Type`（`+0x38`）与入参 `w1` 比；
//     接着 `[x0,#0x3C]` 对 `w2`（Variant）、`[x0,#0x40]` 对 `w3`（SubType），
//     `tbnz w4,#0x1F`（`w4` 第 31 位 = 负数）—— 与契约那句"用 -1 表示不加冠军颜色"逐条吻合；
//     整个函数唯一一条 `ret`（`0x10FCC8`）之前是 `mov w0, w20`（`0x10FCB4`）
//     ⇒ **返回布尔**（w20 = 1 已变形 / 0 与当前形态相同、空操作）。
//
// `Entity_Pickup::Morph(eEntityType, u32, u32, bool KeepPrice, bool KeepSeed, bool IgnoreModifiers)`
//   符号 `_ZN15IsaacRepentance13Entity_Pickup5MorphENS_11eEntityTypeEjjbbb`（arity **6** ✓）。
//   PC 契约 `tools/pc_contract_docs/EntityPickup.md:40` 逐字：
//     `void Morph ( EntityType Type, int Variant, int SubType, boolean KeepPrice = false,`
//     `boolean KeepSeed = false, boolean IgnoreModifiers = false )`
//   ⇒ **尾部 3 个布尔带缺省值**，语料里两种写法都有（⇒ 形状必须声明"尾部 3 个可省"）：
//     * 3 参（走缺省）：`ChallengeAPI/scripts/challengeapi/goals/hooks/polaroid_negative.lua:33`
//       `entity:Morph(EntityType.ENTITY_PICKUP, PickupVariant.PICKUP_COLLECTIBLE, CollectibleType.COLLECTIBLE_NEGATIVE)`；
//     * 6 参：`RepentancePlus/RepentancePlus/main.lua:1249`
//       `Pickup:Morph(5, PickupVariant.PICKUP_OLDCHEST, 0, true, true, false)`、
//       `CyclingItemsAPI/main.lua:392` `entityPickup:Morph(5, 100, next, true, false, true)`。
//   反汇编（`0x26BD14`，长度上界 `0x5D0`）：前 6 条指令 `mov w26,w6` / `mov w25,w4` /
//     `str w1,[sp,#0x14]` / `stp w3,w2,[x29,#-0x20]` / `tbnz w5,#0x0` —— 6 个参数各占一个
//     `x` 寄存器，与符号签名一致；整个函数唯一一条 `ret`（`0x26C2E0`）之前**从不写 `w0`**
//     ⇒ **返回 void**。
//
// 入口 4 字节小端 word（= 上面 16 字节守卫的前 4 字节）：
//   `Entity_NPC::Morph` → `ff 83 01 d1` → `0xD10183FF`；
//   `Entity_Pickup::Morph` → `ff 03 04 d1` → `0xD10403FF`。
inline constexpr uintptr_t kEntityNpcMorphOffset = 0x10FAF4;
inline constexpr std::uint32_t kEntityNpcMorphEntryWord = 0xD10183FFU;
inline constexpr uintptr_t kEntityPickupMorphOffset = 0x26BD14;
inline constexpr std::uint32_t kEntityPickupMorphEntryWord = 0xD10403FFU;

// --- 批次 324（2026-10-03）：`EntityNPC.ThrowSpider(...)`（**静态**调用，3 处 / 2 个模组）--------
// PC 契约 `tools/pc_contract_docs/EntityNPC.md:165`：
//   `#### static const EntityNPC ThrowSpider ( Vector Position, Entity Spawner, Vector TargetPos,
//    boolean Big, float YOffset )` —— ★ **`static`**，而且是 `EntityNPC.ThrowSpider(...)`
//   这种**点号直呼在类名上**的写法（语料三处都这么写）。
// 引擎符号 `_ZN15IsaacRepentance10Entity_NPC11ThrowSpiderERKN4KAGE4Math7Vector2EPNS_6EntityES3_bf`
//   ⇒ `ThrowSpider(Vector2 const&, Entity*, Vector2 const&, bool, float)`：**5 个形参、没有 `this`**
//   ⇒ 契约 5 参 vs 符号 5 参 **逐字对得上**（这一点比同族的 `FireTear` 干净：
//     `FireTear` 符号 5 参、PC 契约 7 参 ⇒ 那一条的 PC 胶水做了额外的事，别照符号直调）。
// ★★ **AAPCS64 且没有 `this`** ⇒ 五个实参自己排寄存器：
//   整数/指针一路 `Vector2 const& SourcePos`→`x0`、`Entity*`→`x1`、`Vector2 const&`→`x2`、`bool`→`w3`；
//   浮点独立一路 `float`→`s0`。
// 入口 4 字节小端 word（= 16 字节守卫 `ffc301d1e81b00fdf72700f9fdfb03a9` 的前 4 字节）：
//   `ff c3 01 d1` → **`0xD101C3FF`**。
inline constexpr uintptr_t kEntityNpcThrowSpiderOffset = 0x1116EC;
inline constexpr std::uint32_t kEntityNpcThrowSpiderEntryWord = 0xD101C3FFU;

// --- 批次 325（2026-10-03）：`EntityLaser.ShootAngle(...)`（**静态**，8 处 / 1 个模组）----------
// PC 契约 `tools/pc_contract_docs/EntityLaser.md:146`：
//   `#### static EntityLaser ShootAngle ( int Variant, Vector SourcePos, float AngleDegrees,
//    int Timeout, Vector PosOffset, Entity Source )` —— ★ **`static`**，写法是
//   `EntityLaser.ShootAngle(...)`（点号直呼在类名上，语料 8 处全这么写）。
// 引擎符号 `_ZN15IsaacRepentance12Entity_Laser10ShootAngleEjRKN4KAGE4Math7Vector2EfiS5_PNS_6EntityEb`
//   ⇒ `ShootAngle(u32, Vector2 const&, float, int, Vector2 const&, Entity*, bool)`：**7 个形参、没有 `this`**。
// ★★★ **契约 6 参 / 符号 7 参 —— 这第 7 格不是"引擎多一个"，PC 也有**：
//   批 282 当年就是拿"符号 7 参 vs 契约 6 参"把这条**排除**掉的（注释还留在 `isaac_api.cpp`）。
//   本批去读了 PC 那条绑定（`tools/pc_exe_binding.py ShootAngle` ⇒ `0x8C7550`）：
//     8c755f  movzx ecx, byte ptr [ebp + 0x20]   ; ★ 第 **7** 格参数（0x8/0xc/0x10/0x14/0x18/0x1c/0x20）
//     8c7566  push  ecx                          ; ★ 原样转发给 Game::Spawn 的第 8 个参数
//     8c757e  call  0x6d0ca0                     ;    Game::Spawn(7 /*ENTITY_LASER*/, …)
//   ⇒ **PC 与 Switch 的签名一致**，差的那一格只是 C++ 头里的**缺省值**（契约文档不写它）
//   ⇒ 按"**尾部 1 个可省**"处理（省略时保持 0），与 `Room:SetGridPath(int,int,int)` 同一档。
// ★ Switch 侧那个 bool 确实被用（`0xf7468 mov w20, w5` → `0xf7494 and w8, w20, #0x1` → 转发给
//   `Game::SpawnEx`），所以**必须**给它一个值 —— 语料 8 处全部只传 6 个 ⇒ 走缺省 0。
// ★ 函数体（`0xF743C`）与 PC 那条绑定的后半段逐句同形：`Game::Spawn(7, variant, pos, Vector2::Zero, …)`
//   → 写 `+0x408/+0x40C`（角度相关）与 `+0x448`（timeout）→ `Vector2::operator=` 写位置。
// ★★ 实参映射（AAPCS64、无 `this`）：整数/指针一路 `Variant`→`x0`、`SourcePos`→`x1`、`Timeout`→`x2`、
//   `PosOffset`→`x3`、`Source`→`x4`、第 7 个 `bool`→`w5`；浮点独立一路 `AngleDegrees`→`s0`。
// 入口 4 字节小端 word（= 16 字节守卫 `ffc301d1e81300fdf91f00f9fdfb02a9` 的前 4 字节）：
//   `ff c3 01 d1` → **`0xD101C3FF`**。★ 与 `kEntityNpcThrowSpiderEntryWord` **同值** ——
//   两个函数的前 4 字节恰好一样（都是 `sub sp, sp, #0x70` + `str d8, [sp, #0x20]`），
//   入口指纹只保证"偏移没写错"，不承担唯一性。
inline constexpr uintptr_t kEntityLaserShootAngleOffset = 0xF743C;
inline constexpr std::uint32_t kEntityLaserShootAngleEntryWord = 0xD101C3FFU;

// --- 批次 326（2026-10-03）：`EntityPlayer:FireTechLaser(...)`（1 处 / 1 个模组）----------------
// PC 契约 `tools/pc_contract_docs/EntityPlayer.md:728`：
//   `#### EntityLaser FireTechLaser ( Vector Position, LaserOffset OffsetID, Vector Direction,
//    boolean LeftEye, boolean OneHit 的缺省是 false, Entity Source 的缺省是 nil,
//    float DamageMultiplier 的缺省是 1 )`
// 引擎符号 `_ZN15IsaacRepentance13Entity_Player13FireTechLaserERKN4KAGE4Math7Vector2E
//   NS0_12eLaserOffsetES5_bbPNS_6EntityEf` ⇒ `FireTechLaser(Vector2 const&, eLaserOffset,
//   Vector2 const&, bool, bool, Entity*, float)`：**7 个形参 + `this`**
//   ⇒ **契约 7 参 = 符号 7 参**（没有"契约少写"的问题，与 `ShootAngle` 那类不同）。
// ★★ 本批为它补的是**一种参数种类** `EngineArgKind::FloatDefaultOne`（省略时填 `1.0`）：
//   最后那一格 `DamageMultiplier` 的**缺省不是 0**，而 `optionalArgumentCount` 那一档的语义
//   是"省略的寄存器保持 0" ⇒ 直接用它会把伤害倍率填成 `0.0`（激光没伤害），那是真差异。
//   语料那 1 处（`IsaacOnTwitchReloaded/scripts/events.lua:1828`）传 5 个实参
//   （`p:FireTechLaser(pos, LASER_TECH5_OFFSET, dir, false, true)`）⇒ `Source` 与
//   `DamageMultiplier` 两条缺省都要生效。
// ★ 实参映射（实例方法 ⇒ `this` 占 `x0`）：`Position`→`x1`、`OffsetID`→`x2`、`Direction`→`x3`、
//   `LeftEye`→`w4`、`OneHit`→`w5`、`Source`→`x6`；★ **浮点只有一路**：`DamageMultiplier`→`s0`
//   （`Direction` 是 `Vector2 const&`，走指针 `x3`、不占浮点寄存器）。
// 入口 4 字节小端 word（= 16 字节守卫 `ffc303d1ec3b00fdeb2b086de923096d` 的前 4 字节）：
//   `ff c3 03 d1` → **`0xD103C3FF`**。
inline constexpr uintptr_t kEntityPlayerFireTechLaserOffset = 0x2B9020;
inline constexpr std::uint32_t kEntityPlayerFireTechLaserEntryWord = 0xD103C3FFU;

// ============================================================================
// 批次 286（2026-10-02）：`Entity:IsVulnerableEnemy()`（★ 一次 PC 侧取证专项）
// ============================================================================
//
// **为什么值得单开一批**：它是本项目里**单条调用点最多**的未做项（**22 处**、4 个模组：
// Custom-Bossbar / Enhanced-Boss-Bars / IsaacOnTwitchReloaded / RepentancePlus），
// 而且是"引擎签名比 PC 契约**多一个参数**"的那一类 —— 按纪律这种**不许猜**，
// 必须先把"PC 那个无参重载到底往那格传了什么"查清（批次 284 就是这么把它挡下来的）。
// 本批把那次取证做完了，结论是**传空指针**，证据链见下面第三节。
//
// ---- 1. 引擎侧（本机 `Repentance.nro`） -----------------------------------
//
//   `Entity::IsVulnerableEnemy(Entity*) const` @ `0x5C62C`
//   符号 `_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_`
//   （`EPS0_` = 一个 `Entity*` 形参；`K` = const 方法 —— **注意 mangled 前缀是 `_ZNK`**）。
//   函数长度上界 `0x90`（紧邻的下一个符号是 `Entity::IsObstacle` @ `0x5C6BC`）。
//   入口 16 字节：`08 38 40 B9  09 29 00 51  3F 75 0F 71  08 01 00 54` ⇒ 入口字 `0xB9403808`。
//   ★ 这个入口字与 `Entity::IsEnemy`（`0x59130`）**逐字节相同**（两条都以
//     `ldr w8,[x0,#0x38]` 开头）—— 入口字只是"这个地方是不是那条指令"的哨兵，不是唯一键，
//     唯一性由**偏移**保证。别因为"撞了入口字"就以为挂错了。
//
//   ★ **同名方法只有一个类有实现**（用「扫全镜像 mangled 名」核实，见第三节）：
//     整份 `Repentance.nro` 里 `IsVulnerableEnemy` 只有上面这一条命中 ✓
//
//   反汇编全文（`python3 tools/nro_disasm.py 0x5C62C 0x90`）：
//
//     0x5C62C  ldr   w8, [x0, #0x38]        ; w8 = this->Type
//     0x5C630  sub   w9, w8, #0xA
//     0x5C634  cmp   w9, #0x3DD
//     0x5C638  b.hi  0x5C658                ; Type ∉ [10, 10+0x3DD] ⇒ 返回 false
//     0x5C63C  ldr   w9, [x0, #0x1E4]
//     0x5C640  cmp   w9, #0x2
//     0x5C644  b.lo  0x5C658                ; [0x1E4] < 2 ⇒ false
//     0x5C648  ldrb  w9, [x0, #0x384]
//     0x5C64C  cbnz  w9, 0x5C658            ; 该字节非 0 ⇒ false
//     0x5C650  ldrb  w9, [x0, #0x1C3]
//     0x5C654  cbz   w9, 0x5C660            ; 该字节 == 0 ⇒ 继续（否则 false）
//     0x5C658  mov   w0, wzr ; ret          ; = 返回 false
//     0x5C660  ldr   x9, [x0, #0x1B8]       ; x9 = EntityFlags（64 位）
//     0x5C664  tst   x9, #0x10
//     0x5C668  and   w8, w8, #0xFFFFFFBF    ; Type 清掉 bit6
//     0x5C66C  cset  w10, eq                ; w10 = ((flags & 0x10) == 0)
//     0x5C670  cmp   w8, #0x322
//     0x5C674  cset  w8, eq                 ; w8  = (Type&~0x40 == 0x322)
//     0x5C678  orr   w0, w8, w10            ; w0  = 上面两个的"或" —— **这就是无来源时的返回值**
//     0x5C67C  cbz   x1, 0x5C6B8            ; ★ 来源为空 ⇒ 直接返回 w0（不碰 x1、无副作用）
//     0x5C680  cbz   w0, 0x5C6B8            ; 已判 false ⇒ 返回 false
//     0x5C684  tbnz  w9, #0x1D, 0x5C690     ; flags bit29 置位才去追链
//     0x5C688  mov   w0, #1 ; ret           ; 否则返回 true
//     0x5C690  …（顺 [x1+0x3A8] 走到链尾，再看链尾那个实体的两个字节/Type）
//
//   ⇒ **`x1`（那个"来源实体"）只在 `x1 != 0` 时才会被解引用**；`x1 == 0` 时这条路
//     是**纯读 + 立即返回**，不可能崩、也不可能有副作用。这是本批敢做的**前提**。
//
// ---- 2. PC 侧（`The Binding of Isaac Rebirth/isaac-ng.exe`）----------------
//
//   PC 的引擎实现 `0x684630`（`ret 4` ⇒ 同样收 **1 个** 形参），逻辑与上面**逐条对应**
//   （只是两版的内存布局不同：PC 的 Type 在 `+0x28`、flags 在 `+0x160`、那两个字节在
//   `+0x308`/`+0x16B`；Switch 在 `+0x38`/`+0x1B8`/`+0x384`/`+0x1C3`）：
//
//     68463A  mov edi, [esi+0x28]        ; Type
//     684640  cmp eax(=edi-0xA), 0x3DD ; ja ⇒ false
//     68464B  mov eax, [esi+0x180]      ; 与 Switch 的 [0x1E4] 同位：必须 >= 2
//     68465A  cmp byte [esi+0x308], 0   ; ↔ Switch [0x384]
//     684663  cmp byte [esi+0x16B], 0   ; ↔ Switch [0x1C3]
//     68466C  push 0 / push 0x10 / call 0x4122F0     ; = Entity::HasEntityFlags(0x10)
//     684679  cmp edi, 0x322 / 0x362                 ; ↔ "Type&~0x40 == 0x322"
//     684689  mov ecx, [ebp+8]          ; ★★ 第二个形参（来源实体）
//     68468E  test ecx, ecx ; je 0x6846D2           ; ★ 来源为空 ⇒ 直接返回 dl=1
//     684692  …（非空时还要看 [esi+0x160] & 0x20000000，再调 0x681340 追一层）
//
//   ★★★ **关键一步：PC 那个无参 Lua 重载到底传什么**。用
//   `python3 tools/pc_exe_binding.py IsVulnerableEnemy` 找到名字表项
//   （`"IsVulnerableEnemy"` 字符串 @ `0xB51A24`，表项在 `0x805450`），
//   它成对的那个指针是 `0x7FAE70`；全镜像里 `0x7FAE70` **只出现两次**（表项一次、
//   注册现场 `0x80E9D6` 的 `mov [eax], 0x7FAE70` 一次）⇒ 它是**为这一条方法专门写的**
//   包装（正因为引擎签名多一个参数，走不了通用转发），不是被多条共用的模板。
//   反汇编 `0x7FAE70`（尾部 `movzx eax,al` / `push eax` / `push L` / `call lua_pushboolean`
//   / `ret 4`，确认是 Lua 绑定）：
//
//     7FAE7F  push 2 / push L / call lua_pushvalue     ; 取 Lua 栈**第 2 格**
//     7FAE96  call luaL_ref                            ; 先把它挂起来
//     7FAEB7  call lua_type(L, -1)             → esi
//     7FAECB  test esi, esi ; je 0x7FAEDA              ; ★ 是 nil ⇒ eax = 0
//     7FAED3  call 0x80EE80                            ; 否则从那个对象里取出实体指针
//     7FAEE1  call 0x684630                            ; = IsVulnerableEnemy(this, eax)
//
//   而 PC 契约 `tools/pc_contract_docs/Entity.md:496` 逐字是
//     `#### boolean IsVulnerableEnemy ( ) {: .copyable aria-label='Functions' }`
//   （正文 `:497`："return true for enemies that can be damaged"；
//     `analysis/isaacdocs-snapshot/docs/tutorials/DebugConsole.md:315` 的官方示例也是
//     `v:IsVulnerableEnemy()`）—— **文档口径 0 参** ⇒ 第 2 格不存在 ⇒
//   `lua_pushvalue` 压的是 nil ⇒ **PC 传下去的就是空指针**。
//   （旁证：语料里 22 处调用**没有一处**给第二个实参。）
//
// ---- 3. 两版"来源为空"时**返回值等价**（这是敢照 PC 做的最后一块）----------
//
//   PC（684689 起）：走到这里说明前面那道闸门**已经通过**（`dl = 1` 是在闸门之后才设的；
//   闸门不通过在上面就 `jmp 0x6846D0` 把 `dl` 清 0 了）⇒ `来源 == 空` ⇒ **返回 true**。
//   等价说法：返回 `(Type&~0x40 == 0x322) || ((flags & 0x10) == 0)` —— 与 Switch 的 `w0`
//   是**同一个式子**（`0x362 == 0x322|0x40`）。
//   Switch（5C67C）：`cbz x1, → 返回 w0`，`w0` 就是那个式子。
//   ⇒ **`x1 = 0` 时两边给的是同一个答案。** 这就是本批"与 PC 一致"的判据。
//
// ---- 4. 我们怎么把 `x1` 变成 0 -------------------------------------------
//
//   用既有的**形状 `EngineCallShape::Bool0`**（`bool(this)`、0 个参数）即可 ——
//   `EngineMethodHandler`（`isaac_api.cpp:6871`）把整数参数数组**整块零初始化**、
//   只搬"实际给出"的那几个（同文件 `:6888` 的注释），而通用跳板无条件读满 8 个 `x`
//   ⇒ 省略的 `x1` **保持 0**，正好就是 PC 的缺省。⇒ **不需要新形状、0 字节代码。**
//
//   ★ ABI 体检会因此报 `under`（"我们声明 1 个含 this < 引擎 1 + 1"）—— 这是**预期**，
//     按纪律写进 `tools/engine_abi_triage.json`（那里对这种情况的标准说法就是
//     "引擎那个参数可以传 0（例如 `Entity*` 允许空指针），而我们的跳板会把对应寄存器清零"）。
//     只登记、不改代码：`x1 = 0` 正是我们要的语义。
inline constexpr uintptr_t kEntityIsVulnerableEnemyOffset = 0x5C62C;
inline constexpr std::uint32_t kEntityIsVulnerableEnemyEntryWord = 0xB9403808U;

// ============================================================================
// 批次 287（2026-10-02）：`EntityPlayer` 的"心数 / 金色钥匙"三个 `field_row`
// ============================================================================
//
// 这一批做三条**只读字段**（合 13 处调用点、3 个模组）：
//
//   | API | 契约 | 语义 | 字段 | 调用点 |
//   | --- | --- | --- | --- | --- |
//   | `EntityPlayer:GetBoneHearts()` | 0 参 → int | 骨心数（**不翻倍**） | `+0x2450`（**常量早已存在**） | 8（IsaacOnTwitchReloaded） |
//   | `EntityPlayer:GetEternalHearts()` | 0 参 → int | 永恒心数 | `+0x16C0` | 1（Trinity） |
//   | `EntityPlayer:HasGoldenKey()` | 0 参 → boolean | 有没有金色钥匙 | `+0x16D8`（u8） | 4（BOIStageAPI15 / RepentancePlus） |
//
// ---- 1. 契约原文（`tools/pc_contract_docs/EntityPlayer.md`）------------------
//
//   `:866` `#### int GetBoneHearts ( ) {: .copyable aria-label='Functions' }`
//        正文 `:867`「Returns the amount of bone hearts that the player has. This is not doubled like
//        the `EntityPlayer.GetMaxHearts` method is, so if e.g. the player has 3 bone hearts, this
//        will return 3.」⇒ ★ 那句「**not doubled**」正是本批选 `FieldKind::U32`（原样读、不乘 2）
//        的依据；`+0x2450` 在 `GetEffectiveMaxHearts` 里是被**乘 2** 之后才用的（见上文的
//        `kEntityPlayerBoneHeartsOffset` 注释），所以那一处乘 2 是**那个 API 的事**，不是这一格的事。
//   `:956` `#### int GetEternalHearts ( ) {: .copyable aria-label='Functions' }`
//        正文 `:957`「Returns the amount of eternal hearts the player has.」
//   `:1372` `#### boolean HasGoldenKey ( ) {: .copyable aria-label='Functions' }`（正文为空）
//
// ---- 2. 跨版本链条（每一条都是「PC 读点 + PC 写点 + Switch 写点」三方对应）----
//
//   取证口径：PC 侧 `python3 tools/pc_exe_binding.py <名字>` 拿绑定 VA 后 objdump；Switch 侧
//   `python3 tools/nro_disasm.py <偏移> <长度>`。
//
//   **① 骨心 `+0x2450`**（★ 常量已存在，本批只补消费方）——
//     * PC `EntityPlayer:GetBoneHearts` 的绑定 @ `0x5EF420`，**整个函数就一条指令**：
//       `mov eax, dword ptr [ecx + 0x1ca8]` / `ret`；
//     * PC `Entity_Player::AddBoneHearts` @ `0x78C870` 在同一格上"取-改-存"
//       （`78c8ee mov ecx,[esi+0x1ca8]` / `78c8ff mov [esi+0x1ca8],eax` …）；
//     * Switch 侧 `AddBoneHearts @ 0x27E380` 的强命中字段同样是 **`+0x2450`**
//       （`python3 tools/engine_field_recipe.py 0x27E380` 输出
//       `0x27e4c0 ldr [x19,#0x2450]` / `0x27e520 ldr [x19,#0x2450]` / `0x27e550 str [x19,#0x2450]`）。
//     ⇒ PC `+0x1ca8` ≡ Switch `+0x2450`。
//
//   **② 永恒心 `+0x16C0`** ——
//     * PC `EntityPlayer:GetEternalHearts` 的绑定 @ `0x6B1BF0` 读 `[ecx + 0x1298]`
//       （与上面那张"PC 取值表"一致）；
//     * PC `Entity_Player::AddEternalHearts` @ `0x7250A0`：
//       `7250bf add eax,[esi+0x1298]` → `test eax,eax` → `cmovg ecx,eax`（夹到 ≥0）
//       → `7250ca mov [esi+0x1298],ecx` —— **与读点是同一格**；
//     * Switch `AddEternalHearts @ 0x27F6FC`：`0x27F73C ldr w9,[x0,#0x16c0]`
//       → `0x27F740 add w9,w9,w1` → `0x27F744 bic w9,w9,w9,asr#31`（夹到 ≥0）
//       → `0x27F750 str w9,[x0,#0x16c0]` —— **与 PC 那支逐条同形**（连夹取方式都一样）。
//     ⇒ PC `+0x1298` ≡ Switch `+0x16C0`。
//     ★ 第二组独立锚点（不是同一个函数）：`Entity_Player::StoreGameState` /
//       `RestoreGameState(GameStatePlayer&)` **在这两版里都读写这一格**
//       （Switch 例 `0x2f81ec`（存）/ `0x2c45a4`（取回）；PC 侧同一对函数也在 `+0x1298` 上），
//       外加 `update_red_hearts`（Switch `0x27ed64`）在"更新红心"时也读它。
//       —— 一个"心数"字段同时出现在**存档对**与**红心更新**里，语义没有歧义。
//
//   **③ 金钥匙标志 `+0x16D8`**（u8）——
//     * PC `EntityPlayer:HasGoldenKey` 的绑定 @ `0x6B1C00` 读 `al = [ecx + 0x12b0]`；
//     * PC `Entity_Player::AddGoldenKey` @ `0x725930` 的**第一条指令**就是
//       `mov byte ptr [ecx + 0x12b0], 0x1`（紧接着 `0x725970` 是同一形态的清 0 —— `RemoveGoldenKey`）——
//       ★ 注意它**没有**用 `mov byte ptr [ecx+0x12b0]` 之外的花样，就是个标志字节；
//     * Switch `AddGoldenKey @ 0x280588`：`mov w8,#0x16d8` / `add x8,x0,x8` / `mov w9,#1` /
//       `strb w9,[x8]`；`RemoveGoldenKey @ 0x280628` 同形、`strb wzr,[x8]` 清 0
//       （★ 这两个函数都把同一个字节**复制给同局每个玩家** —— 遍历的正是 `g_Game + 0x25C50`，
//       与 `kGamePlayerArrayBeginOffset` 相符 ⇒ "每玩家一份"的状态位，读当前接收者那一份即可）。
//     ⇒ PC `+0x12b0` ≡ Switch `+0x16D8`。
//     ★★ **位移扫描对这个字段无效**（本批实测）：这一格在 Switch 上是
//       `mov w8,#0x16d8` + `add x8,x0,x8` + `strb w9,[x8]`（**寄存器里算地址**），
//       所以按"立即数偏移"扫 `strb w?,[x0,#0x16d8]` 得 **0 处** —— 0 处**不等于**"没有读写点"。
//       邻格 `+0x16D9` 是"金**炸弹**"标志（批次 195，写法逐字同形，`kEntityPlayerGoldenBombFlagOffset`）
//       ⇒ 两个相邻字节 = 两个"金色 X"标志，这一簇本身也是一条旁证。
//
// ---- 2b. 结构级互证：PC 侧那四个取值器是**相邻的单指令访问器**，PC↔Switch 恒定差 `0x428` ----
//
//   `tools/pc_exe_binding.py <名字>` 给出的绑定 VA 处，**整个函数就一条 `mov` + `ret`**
//   （`objdump` 逐条核过；取证口径与命令见 §2 开头那段）。四处并排：
//
//     | PC 绑定 VA | 指令 | PC 偏移 | Switch 偏移 | 差 |
//     | --- | --- | --- | --- | --- |
//     | `0x6B1BE0` `GetMaxHearts`     | `mov eax,[ecx+0x1290]` | `0x1290` | `0x16B8` | `0x428` |
//     | `0x6B1BF0` `GetEternalHearts` | `mov eax,[ecx+0x1298]` | `0x1298` | `0x16C0` | `0x428` |
//     | `0x5EF450` `GetSoulHearts`    | `mov eax,[ecx+0x129C]` | `0x129C` | `0x16C4` | `0x428` |
//     | `0x6B1C00` `HasGoldenKey`     | `mov al,[ecx+0x12B0]`  | `0x12B0` | `0x16D8` | `0x428` |
//
//   ★ 这条互证有三层加强，**彼此独立**：
//     ① 前三条绑定 VA **彼此只差 `0x10`**（`0x6B1BE0` / `0x6B1BF0` / `0x6B1C00`）—— 它们是
//        同一张"取值器表"里**连续的三个槽**，说明这一簇在 PC 上本来就是同一个字段族；
//     ② PC 侧偏移也连续（`0x1290`/`0x1298`/`0x129C`；`0x12B0` 稍远但同属那个子块）；
//     ③ PC↔Switch 的差在**四处完全相同（`0x428`）** ⇒ 这不是"碰巧读到一个整数"，
//        而是**同一块子结构整体平移**（前两条互证已经在批次 195 那条金炸弹上用过，本批扩到四条）。
//   ★ 骨心**不**在这簇里（PC `0x1CA8` vs Switch `0x2450`，差 `0x7A8`）：它在结构上属于另一段
//     （PC `0x1290 + 0x818`、Switch `0x16B8 + 0x798`）⇒ 骨心不靠这条互证，它靠**自己**那对锚点
//     （`AddBoneHearts @ 0x27E380` 的强命中读写 + `GetEffectiveMaxHearts` 的读点，批次 274 已取证）。
//
// ---- 3. 为什么走 `field_row` 而不直调引擎 -----------------------------------
//
//   三条在 Switch 镜像里**都没有同名函数**（`python3 tools/mangled_impl_count.py GetBoneHearts
//   GetEternalHearts HasGoldenKey` 各得 **0 个实现** —— 已按 mangled 的**长度前缀**逐段解析，
//   不是老正则那种"恒 0 命中"的假阴性）⇒ PC 上是**内联/字段访问器**、Switch 上同样不生成函数，
//   所以只能"读字段"。★ 读法与既有的 `EntityPlayer:GetSoulHearts`/`GetBrokenHearts`/
//   `GetRedHeartContainers` 完全同族（都是 `FieldKind::U32` + `FieldMissing::Zero`），
//   `HasGoldenKey` 与 `HasGoldenBomb` 同族（`FieldKind::Bool` + `FieldMissing::False`）。
//   读不到时压 `0` / `false`（PC 上"没有"就是这个值），**不抛 Lua 错误**（批 250 定案）。
inline constexpr uintptr_t kEntityPlayerEternalHeartsOffset = 0x16C0;      // u32（整颗为单位）
inline constexpr uintptr_t kEntityPlayerGoldenKeyFlagOffset = 0x16D8;      // u8，非 0 即真

// ============ 批次 288（2026-10-02）：`EntityPlayer` 的"方向"三条 ============
//
// 三条一起做（合 **37 处** / 2 个模组）：
//   `EntityPlayer:GetFireDirection()`     PC `EntityPlayer.md:968`，13 处
//   `EntityPlayer:GetHeadDirection()`     PC `EntityPlayer.md:994`，12 处
//   `EntityPlayer:GetMovementDirection()` PC `EntityPlayer.md:1096`，12 处
// 前两条走**字段读取型数据行**（`FieldApiRow`，0 字节代码），第三条走**引擎方法数据行**
// （`EngineMethodRow`，同样 0 字节代码）。
//
// ---- 1. 契约原文 -----------------------------------------------------------
//
//   三条在 PC 契约里**都只有签名、正文为空**（`Direction GetFireDirection ( )` 之类）
//   ⇒ 语义只能靠枚举名 + 引擎侧取证。`Direction` 枚举我们自己有表
//   （`runtime/source/program/doc_lua_enum_data.cpp:32`）：
//     `NO_DIRECTION = -1`、`LEFT = 0`、`UP = 1`、`RIGHT = 2`、`DOWN = 3`。
//   ★★★ 三条能一起做的前提：引擎自己的 `eDirection` 与 PC 的 `Direction` **数值逐个相等**
//   （§2 的算法推导），所以数据行**原样返回整数**即可，不需要任何映射表。
//
// ---- 2. 三方对应（PC 读点 / Switch 写点 / 消费方） --------------------------
//
//   ★ 前两条（开火方向 / 头部朝向）在 PC 上是**相邻的取值器，每个只有一条 `mov`+`ret`**：
//     | PC 绑定 VA | 指令 | PC 偏移 | Switch 偏移 | 差 |
//     | `0x422D80` `GetFireDirection` | `mov eax,[ecx+0x1560]` | `0x1560` | `0x1A00` | `0x4A0` |
//     | `0x427810` `GetHeadDirection` | `mov eax,[ecx+0x155C]` | `0x155C` | `0x19FC` | `0x4A0` |
//     | `0x422D90`（同族，`lea`） | `lea eax,[ecx+0x1564]` | `0x1564` | `0x1A04` | `0x4A0` |
//   三处 PC↔Switch 的差**完全相同（`0x4A0`）**，且两边偏移都**连续**
//   （`0x155C`/`0x1560`/`0x1564` ↔ `0x19FC`/`0x1A00`/`0x1A04`）
//   ⇒ **同一块子结构整体平移**（与批次 287 的 `0x428` 那簇同一个手法）。
//   ★ 第三行那个 `lea` 返回的是**地址**不是值 ⇒ 它是 `Vector2` 的取地址器，对应的正是
//     Switch 侧 `+0x1A04`（`SetAimDirection` 里 `Vector2::operator=` 的目标）。
//
//   ★★ Switch 侧的**独立**锚点（只看函数名就能定案，与 PC 无关）：
//     `Weapon::SetHeadDirection(eDirection)` @ `0x4A9A24`
//       `004a9a4c  str w1, [x8, #0x19fc]` —— `x8 = weapon->[0x8]` 是**武器持有者（玩家）**；
//       同一函数接着按同一个 `w1` 取出方向名、赋给 `+0x1698`（头动画字符串）
//       ⇒ `Entity_Player + 0x19FC` = **头部朝向**；且 `0x4A9A48 cmn w1, #0x1` 表明**允许 `-1`**。
//     `Entity_Player::SetAimDirection(const Vector2&)` @ `0x2A1CDC`
//       `002a1d14 str w0,[x20,#0x1a00]` + `002a1d20 str w0,[x20,#0x19fc]` —— 同一个方向值写**两格**；
//       且**零向量时 `w0 = -1`**（`0x2A1D04 mov w0, #-0x1`）⇒ 与 PC 的 `NO_DIRECTION = -1` 对上；
//       向量本身存 `+0x1A04`（`Vector2::operator=`）。
//     ⇒ 两格中 `0x19FC` 被"设头方向"直接写、`0x1A00` 只被瞄准/射击控制写
//       ⇒ 前者 = 头朝向、后者 = 开火方向；再加上 PC 侧"Head 排在 Fire 前 4 字节"的顺序**同向**，
//       四条独立证据一致（★ "一个 setter 写两个相邻格"那个坑，这里用到了第二、第三个锚点才敢定）。
//
//   ★ 第三条（运动方向）在 Switch 上是**真函数**：
//     `_ZNK15IsaacRepentance6Entity22get_movement_directionEv` @ `0x5C8AC`
//       005c8ac  ldr  s0, [x0, #0x334]   ; 自身"运动向量"的 x 分量
//       005c8b4  ldr  s1, [x0, #0x338]   ; 自身的 y 分量
//       …（与**带 `const Vector2&` 的重载** @ `0x5C87C` **逐条相同**的算法）…
//       005c8dc  ret                     ; 返回 w0 = eDirection（int）
//     带参重载开头 `ldp s0,s1,[x0]` 读的是传入向量的两个 float，之后指令序列完全一样
//     ⇒ 这段算法就是"把 (x,y) 向量化成方向"。它推出的四个值：
//       |x|>|y| ⇒ x≥0 给 **2**（RIGHT）、x<0 给 **0**（LEFT）；
//       否则    ⇒ y≥0 给 **3**（DOWN）、 y<0 给 **1**（UP）。
//     —— 与 PC 的 `Direction` 表**逐个相等**（§1）⇒ 直接返回引擎整数即可。
//     ★ `Entity + 0x334`/`+0x338` 是 `Entity` 级的运动向量（不是玩家专有），
//       但 PC 只把这条挂在 `EntityPlayer` 上 ⇒ 接收者仍取 `EntityPlayer`。
//
// ---- 3. 参数个数与"同名方法只有一个类有实现" --------------------------------
//
//   * 前两条在镜像里**没有同名函数**（`python3 tools/mangled_impl_count.py GetFireDirection
//     GetHeadDirection` 各得 **0 个实现**）⇒ 字段型 API 的第一条硬门槛**不适用**（同批次 287）。
//   * 第三条的符号名是**小写加下划线**的 `get_movement_direction`（不是 `GetMovementDirection`）
//     —— ★ 这又一次说明"按名字精确匹配会漏"。它的两个实现都是 `IsaacRepentance::Entity`
//     的**重载**（`() const` 与 `(const Vector2&)`），**不是两个类各实现一个** ⇒ 取 0 参那个
//     （契约也是 0 参）。
inline constexpr uintptr_t kEntityPlayerHeadDirectionOffset = 0x19FC;   // i32，eDirection（-1 = 无）
inline constexpr uintptr_t kEntityPlayerFireDirectionOffset = 0x1A00;   // i32，eDirection（-1 = 无）
inline constexpr uintptr_t kEntityGetMovementDirectionOffset = 0x5C8AC;
inline constexpr std::uint32_t kEntityGetMovementDirectionEntryWord = 0xBD433400U;

// ============================================================================
// 批次 296（2026-10-03）：`Entity_NPC` 的两个颜色索引 + `Entity_Player` 的主动道具充能
// （三条在 Switch 上都没有同名访问器 ⇒ 只能直读字段；PC 侧三条绑定本体的形状见下面那张表）
// ============================================================================
//
// 契约只给"返回一个 int / 枚举"，PC 侧三条绑定本体的形状就是标尺（`tools/pc_exe_binding.py`）：
//
//   | API | PC 绑定 VA | 指令 | PC 偏移 | Switch 偏移 |
//   | --- | --- | --- | --- | --- |
//   | `EntityNPC:GetChampionColorIdx` | `0x680DE0` | `mov eax,[ecx+0xBB4]` | `0xBB4` | `0xD10` |
//   | `EntityNPC:GetBossColorIdx`     | `0x7A7FD0` | `mov eax,[ecx+0xBC8]` | `0xBC8` | `0xD24` |
//   | `EntityPlayer:GetActiveCharge`  | `0x4F3F30` | `mov eax,[ecx+4*eax+0x14C8]`（`eax = 7*槽位`） | `0x14C8 + 0x1C*槽位` | `0x1968 + 0x1C*槽位` |
//
//   ★ PC 那两个索引**相距 `0x14`**（`0xBB4` → `0xBC8`），Switch 那两个**也正好相距 `0x14`**
//     （`0xD10` → `0xD24`）—— 顺序与间距一致是一层**免费的交叉印证**，
//     但两边的偏移数值**完全不同** ⇒ 这正是"PC/Switch 布局不同、偏移绝不许平移"的又一个实例。
//
// ---------------------------------------------------------------------------
// 1) `Entity_NPC + 0xD10` = **冠军色号**（`ChampionColorIdx`，i32；`-1` = 没有冠军色）
// ---------------------------------------------------------------------------
//   ★ 写入方（都是具名函数，三个）：
//     * `Entity_NPC::Init(eEntityType,unsigned,unsigned,unsigned)` @ `0x105F00`
//       `0x105F10 mov w25, #-0x1` → `0x105F14 str x25, [x0, #0xd10]`
//       —— **默认值 `-1`**（8 字节存，一并把相邻的 `0xD14` 也写成 -1 的高半部）；
//       紧接着 `0x105F34 strb wzr, [x0, #0xd0f]` 把**冠军标志字节**清零 ⇒ 两个量同批初始化。
//     * `Entity_NPC::MakeChampion(unsigned,int,bool)` @ `0x108F60`
//       `0x00108fdc  strb w8(1), [x19, #0xd0f]` + `0x00108fe0  str w21, [x19, #0xd10]`
//       —— 第二个实参（`w21` = `int ChampionColorIdx`，契约 `EntityNPC.md:103`）直接落这一格。
//     * `Entity_NPC::Morph(eEntityType,unsigned,unsigned,int)` @ `0x10FB48`
//       `0x0010fb58  str w4, [x19, #0xd10]`（第四个实参）+ `0x0010fb5c  strb w8(1), [x19, #0xd0f]`；
//       另一支 `0x0010fb88  mov w8, #-0x1` / `0x0010fb8c  str w8, [x19, #0xd10]` /
//       `0x0010fb90  strb wzr, [x19, #0xd0f]`（实体配置说"不冠军" ⇒ 写回 -1 并清标志）。
//       ⇒ 契约 `EntityNPC.md:119` 的散文（`Morph` 的 `ChampionColorIdx`，"用 -1 表示不加冠军色"）
//         与这一支**逐字对上**。
//   ★ 具名读者：`Entity_NPC::fix_champion_color()` @ `0x107090`（读它 → `cmp w8,#0x6` / `cmp w8,#0xc`
//     → 命中就写 `0x11`）、`Entity_NPC::load_graphics` / `translate_gfx_path` / 多个 `ai_*`。
//   ★ 取值锚点：`fix_champion_color` 的 `0x00107094  cmp w8, #0x6` 与 `0x001070d0  mov w8, #0x11`
//     —— 该字段被拿来与**冠军色枚举值**比较/赋值，不是"某处有个整数"。
//   ★ 降级档 = `FieldMissing::MinusOne`：`Init` 把"没有冠军色"就写成 `-1`（与 "0 是合法色号" 无关，
//     `-1` 是引擎自己的"无"口径），读不到时答 -1 与"读到 init 默认值"同值。
//
// ---------------------------------------------------------------------------
// 2) `Entity_NPC + 0xD24` = **Boss 色号**（`BossColorIdx`，i32；`-1` = 没有 Boss 色）
// ---------------------------------------------------------------------------
//   ★ 写入方：`Entity_NPC::Init` @ `0x105F40`（同一条 `mov w25,#-0x1` 写它 ⇒ 默认 `-1`）、
//     `Entity_NPC::SetBossColorIdx(int,bool)` @ `0x11FDA0`（`0x0011fdb0  str w1, [x19, #0xd24]`
//     写**第一个实参**；`0x0011fda0  ldr w8, [x0, #0xd24]` 先读它做"值没变就不做事"的守卫，
//     且值没变时**直接跳过** `load_graphics`/`ANM2::SetFrame` 那一段 ⇒ 这一格就是"Boss 配色"的开关）、
//     `Entity_NPC::load_entity_config` @ `0x108E44` / `0x108EA0`。
//   ★ 具名读者：`Entity_NPC::translate_gfx_path` @ `0x107AA8`
//       `0x00107aa8  ldr w8, [x0, #0xd24]` → `0x00107ab0  tbnz w8, #0x1f, →跳过`
//       → `0x00107ac8  add x8, x10, x8, lsl #7`（按 **0x80 步长**到 `EntityConfig::BossColor` 容器里取第 idx 项）
//       —— "换 gfx 路径"要查 Boss 配色，语义即"Boss 色号"；
//     `Entity_NPC::reset_color` @ `0x10FE00`（同一形态：`ldr w8,[x19,#0xd24]` + `tbnz w8,#0x1f`）；
//     另有多个 `ai_*` 与 `Room::TriggerBossDeath` @ `0x4697B8`。
//   ★ 语义锚点：`0x00107ab0  tbnz w8, #0x1f` —— 该字段按**有符号**看待、负值走"没有配色"分支
//     （与 `Init` 写的 `-1` 一致）。
//   ★ 降级档 = `FieldMissing::MinusOne`，理由同上（`Init` 的默认值就是 -1）。
//
// ★ `EntityNPC:IsChampion()` **本批没做**（负结果，别再重查）：PC 的绑定本体 @ `0x68F550` 是
//   `cmp byte [ecx+0xB8C], 0` + `mov eax,[ecx+0x160]; and eax,0x20000000` —— 即
//   「冠军标志字节非 0 **且** 某个实体标志位没置」，是**两个条件**。Switch 侧"冠军标志字节"
//   已经定位（`+0xD0F`，`Init` 清零 / `MakeChampion`/`Morph` 置 1），但那个**实体标志位**在
//   Switch 侧还没定到（`Entity` 的 64 位标志字在 `+0x1B8`，PC 读的却是 32 位的 `+0x160`，
//   两边不是同一个量）⇒ 少一半证据，宁缺勿错。
inline constexpr uintptr_t kEntityNpcChampionColorIdxOffset = 0xD10;    // i32，-1 = 没有冠军色
inline constexpr uintptr_t kEntityNpcBossColorIdxOffset = 0xD24;        // i32，-1 = 没有 Boss 色

// ---------------------------------------------------------------------------
// 3) `Entity_Player + 0x1968 + 0x1C*槽位` = **主动道具充能**（`GetActiveCharge(ActiveSlot)`，i32）
// ---------------------------------------------------------------------------
//   ★★ **没有新增偏移** —— 两个常量都是既有的：同一槽位数组的槽 0 元素基址是
//     `kEntityPlayerActiveItemOffset`（`0x1964`，服务 `GetActiveItem`），步长是
//     `kEntityPlayerActiveItemStride`（`0x1C`），而这一格是**同一元素的 `+4`**：
//     `kEntityPlayerActiveItemChargeOffset`（`0x1968`）；`+8` 那格（`0x196C`）是溢出充能。
//   ★ 元素的三个格由**引擎自己的具名函数**钉住（`Entity_Player::SetActiveCharge(int,int)
//     @ 0x27F984`）：
//       `0x27F9AC mov w9, #0x1C` + `0x27F9B0 umaddl x9, w2, w9, x19`（`x9 = this + 0x1C*槽位`）
//       → `0x27FA54 add x27, x9, x10`（`x10 = 0x1968`）→ `0x27FAEC str w8, [x27]` 写**主充能**
//       （值 = `min(实参, GetActiveMaxCharge(槽位))`：`0x27FAE0 subs` + `0x27FAE8 csel`）
//       → `0x27FA58 add x26, x9, x12`（`x12 = 0x196C`）→ `0x27FAF8 str w9, [x26]` 写溢出充能。
//   ★ 具名读者 `Entity_Player::GetTotalActiveCharge(int) @ 0x29B43C`：
//       `0x29B454 smaddl x8, w1, w8, x0`（`w8 = 0x1C`）
//       → `0x29B458 ldr w10, [x8, #0x1968]` + `0x29B45C ldr w8, [x8, #0x196C]` 然后**相加**
//       ⇒ 两格合起来才是"总充能"，本批的 `GetActiveCharge` 取**第一格**（与 PC 一致）。
//   ★ 同一元素的 `+0` 格（`0x1964`）**早就有消费方**：`0x27FA70 ldr w1, [x8, #0x1964]` 把它
//     喂给 `ItemConfig::GetCollectible`（`GetActiveItem` 那条链）⇒「充能 = 同一元素 `+4`」
//     有**同一数组的既有消费方**做交叉印证。
//   ★ 为什么取 `0x1968` 而不是 `0x196C`：PC 的 `GetActiveCharge` 读的是元素 `+4`
//     （`0x4F3F30`：`mov edx,[ebp+8]` → `add edx,0xBE` → `lea eax,[8*edx]; sub eax,edx`
//     → `mov eax,[ecx+4*eax]`，即 `this + 0x1C*(槽位+190)`，`0x1C*190 = 0x14C8`）
//     ⇒ PC 元素 `{道具指针 @+0, 充能 @+4}`、Switch 元素 `{收藏品 id @+0, 充能 @+4}`：
//     **元素内相对位置与步长都相同，基址数值不同**（`0x14C4` vs `0x1964`）
//     ⇒ 这才是"相对顺序可印证、偏移绝不许平移"的正确用法。

// ============================================================================
// 批次 297（2026-10-03）：状态标志（`Game:GetStateFlag` / `Level:GetStateFlag`）
// ============================================================================
//
// PC 侧两条绑定的形状（`tools/pc_exe_binding.py` 的 VA + `objdump`）：
//
//   `Game:GetStateFlag(int Flag)` @ `0x4E61D0`
//       mov edx,[ebp+8] → and ecx,0x1f → shr edx,0x5 → eax = 1 << (Flag&31)
//       → test dword [esi + 4*(Flag>>5) + 0x1822C], eax → setne
//     ⇒ PC 是**32 位字**的位数组、基址 `Game + 0x1822C`、**没有任何边界检查**
//       （负数会右移出巨大下标，PC 自己也读飞）。
//
//   `Level:GetStateFlag(int Flag)` @ `0x41C430`
//       在 edi:edx 里拼出 64 位掩码 → and edi,[ecx + 8*(Flag>>6) + 0x1C3168]
//                                      → and edx,[ecx + 8*(Flag>>6) + 0x1C316C] → or
//     ⇒ PC 是**64 位字**的位数组、基址 `Level + 0x1C3168`（`ecx` 就是接收者 `Level`）
//       —— 与 `Game` 那条**字宽不同**（32 vs 64），这是 PC 自己的事。
//
// ★★ Switch 侧两条**分别**定死了基址，用的是"具名函数里拿具名标志位"这条最硬的判据
//    （枚举值来自 PC 文档 `analysis/isaacdocs-snapshot/docs/enums/`）：
//
// 1) **`GameStateFlag` = `Game + 0x26FA50` 的位数组，每字节 8 个标志**（`n>>3` 字节、`n&7` 位）。
//    两处**互相独立**的位点位：
//      * `STATE_BACKWARDS_PATH = 48`（升华中）—— `Level::IsBackwardsPath() const @ 0x3E1D98`：
//        `0x3E1DB4 mov w9,#0xfa56` + `0x3E1DB8 movk w9,#0x26,lsl #16`
//        → `0x3E1DBC ldrb w8,[x8,x9]`（`x8` = `g_Game` 解引用）→ `0x3E1DC0 and w0,w8,#0x1`
//        ⇒ 地址 `0x26FA56`、**bit 0**；48 = 6*8 + 0 ⇒ 基址 `0x26FA50`、字节 6、位 0 ✓
//      * `STATE_BACKWARDS_PATH_INIT = 47`（相片门 / Dad's Note）——
//        `Level::CanSpawnDevilRoom() const @ 0x3E7998`：`mov w9,#0xfa55` + `movk w9,#0x26,lsl #16`
//        → `0x3E79A0 ldrb w8,[x8,x9]` → `0x3E79A4 tbnz w8,#0x7`
//        ⇒ 地址 `0x26FA55`、**bit 7**；47 = 5*8 + 7 ⇒ 字节 5、位 7 ✓（**换了一个字节、也换了一位**）
//    另有三处只读同一格（同一个 48 号标志）：`Level::CanSpawnTrapDoor @ 0x3D5C20`、
//      `Level::SetNextStage @ 0x3E432C`、`Level::Init @ 0x3E0F5C`（`add x10,x8,#0x26FA50`
//      → `ldrb w11,[x10,#0x6]` + `tbnz w11,#0x0` —— **这条把"基址 0x26FA50 + 字节 6"直接写出来了**）。
//    ★★ 交接文档里"用 PC 相邻字段间距推的 `Game+0x215F0` / `Game+0x26FA70` 两个候选**都没被证实**"
//      —— 其中 `0x26FA70` 就在这一片的下一页里（见下），而 `0x215F0` 的**真身是 `Level` 的**
//      （见第 2 条）⇒ 那次负结果的根因是**基址对象认错了**（把 Level 的当成 Game 的）。
//
// 2) **`LevelStateFlag` = `Level + 0x215F0` 的 `u64`**（`n>>6` 字、`n&63` 位；24 个标志一个 64 位字就够）。
//    两处**互相独立**的位点位：
//      * `STATE_REDHEART_DAMAGED = 2` —— `Level::SetRedHeartDamage() @ 0x3E7F00`：
//        `0x3E7F00 mov w8,#0x15c8` + `0x3E7F04 movk w8,#0x2,lsl #16` → `0x3E7F08 add x8,x0,x8`
//        （`x0` = this = Level ⇒ `Level+0x215C8`）→ `0x3E7F0C ldr x9,[x8,#0x28]`（**`Level+0x215F0`**）
//        → `0x3E7F10 orr x9,x9,#0x4` → `0x3E7F14 str x9,[x8,#0x28]` ⇒ **bit 2** ✓
//      * `STATE_COMPASS_EFFECT = 7` —— `Level::ApplyCompassEffect(bool) @ 0x3E6F54`：
//        `0x3E6F6C mov w8,#0x1510` + `movk w8,#0x2,lsl #16` → `0x3E6F74 add x22,x0,x8`（`Level+0x21510`）
//        …… → `0x3E7024 ldr x8,[x22,#0xe0]`（**`Level+0x215F0`**）→ `0x3E7028 orr x8,x8,#0x80`
//        → `0x3E702C str x8,[x22,#0xe0]` ⇒ **bit 7** ✓
//    ★ 与 PC **同形**（都是 64 位字），只是基址不同（PC `0x1C3168` / Switch `0x215F0`）。
//
// ★ 两格的**形状不同**（Game 是"每字节 8 位"、Level 是"每 64 位字 64 位"）⇒ 新种类
//   `FieldKind::BoolBitArrayOfArg` 把"元素宽度"放在 `offset2`（1 / 4 / 8 字节）里，
//   一条机制同时服务这两种排布（PC 侧那两条也正好是 32 位字 / 64 位字两种）。
inline constexpr uintptr_t kGameStateFlagsOffset = 0x26FA50;   // 位数组，每字节 8 个标志
inline constexpr uintptr_t kLevelStateFlagsOffset = 0x215F0;   // u64（24 个标志只用一个字）

// ============================================================================
// 批次 298（2026-10-03）：`GridEntity + 0x48` = 内嵌 ANM2（网格实体的 sprite）
// ============================================================================
//
// 契约：`GridEntity:GetSprite()`（`GridEntity.md:53`）与 `GridEntityRock:GetSprite()` 都返回
// 「这个网格实体自己的 sprite」。PC 侧两个绑定本体是**一跳直读成员**、而且**两个类的偏移不同**：
//
//   GridEntity:GetSprite      @ `0x427440`: `lea eax, [ecx + 0x3C]; ret`
//   GridEntityRock:GetSprite  @ `0x427680`: `lea eax, [ecx + 0x40]; ret`
//
// ★★ Switch 侧我们**只找到一格**，而且证据是"引擎自己把它当 ANM2 用"（与 `Entity+0x50` 同一手法）：
//
//   1) **`GridEntity_Rock::InitSubclass @ 0x392E40`**（最长的一条）：
//        `0x392E98  add  x21, x19, #0x48`        ; ★ x19 = this ⇒ x21 = this + 0x48
//        （中间构造 "gfx/grid/grid_rock.anm2" 这个 std::string）
//        `0x392ED4  mov  x0, x21`
//        `0x392ED8  bl   ANM2::Load(std::string const&, bool)`   ; ★★ 引擎把 this+0x48 当 ANM2
//   2) **`GridEntity_Rock::Render @ 0x392AA0`**：`0x392B1C add x20, x19, #0x48` → `0x392BA4 bl ANM2::Render`
//      同一函数里还有 `add x8, x19, #0x130` / `#0x140` / `#0x150`（ANM2 **内部**的层状态）
//      ⇒ `+0x48` 确实是一个**完整的 ANM2**（0x158 字节），不是指针。
//   3) **`GridEntity_Rock::update_anim_frame @ 0x38FC14`**：`0x38FD88 add x0, x19, #0x48` → `bl ANM2::SetFrame`
//   4) ★ **另有 10 个子类的 `ANM2::Load` 也写同一格**（扫全镜像得到，每条都是"`add xN, this, #0x48`
//      紧跟 `bl ANM2::Load`"）：`GridEntity_Decoration::InitSubclass`（`0x381054`/`0x381100`/`0x381244`）、
//      `GridEntity_Door::load_animation_file`（17 处）、`GridEntity_Fire::InitSubclass`（`0x386328`）、
//      `GridEntity_Gravity::PostInit`（`0x387158`）、`GridEntity_Lock::InitSubclass`（`0x3874EC`）、
//      `GridEntity_Poop::InitSubclass`（`0x38A6B4`）、`GridEntity_PressurePlate::InitSubclass`（`0x38EF94`）、
//      `GridEntity_Spikes::InitSubclass`（`0x393BD4`）、`GridEntity_Stairs::InitSubclass`（`0x3945FC`）、
//      `GridEntity_TrapDoor::InitSubclass`（`0x395FE0`/`0x396190`/`0x3961F4`/`0x396364`）。
//   ⇒ **Switch 上"网格实体的 sprite"就是 `+0x48`**（基类与子类同一格），所以 `GridEntity:GetSprite()`
//     与 `GridEntityRock:GetSprite()` 在我们的实现里读的是**同一个偏移**（PC 那 4 字节差是 PC 自己的事）。
//   ★ 免费交叉印证：同一个扫描里 `+0x50` 拿到 **48 处**命中 —— 那正是 `Entity` 的 sprite
//     （既有 `kEntitySpriteOffset = 0x50`，`Entity::Render` / `Entity_Pickup::ReloadGraphics`）
//     ⇒ 手法本身是可信的。
//   ★ 我们**不做** `GridEntityRock` 的独立偏移：没有任何证据支持 Switch 上它有第二格 ANM2
//     （Rock 的 `Render`/`RenderTop`/`update_anim_frame` 三处全用 `+0x48`）。
inline constexpr uintptr_t kGridEntitySpriteOffset = 0x48;

// ---- 网格实体句柄的**存活判据**用的 vtable 区间 ----------------------------------
//
// `GridEntity:GetSprite()` 交出去的 `Sprite` 句柄指向**引擎网格实体内部**的内存（与
// `Entity:GetSprite()` 同一形态）⇒ 每次访问都要重新确认"这个网格实体还在"。判据与
// `Entity` 那条同形（vptr 落在家族的 vtable 区间内），区间由**全部 18 个具名 vtable**夹出：
//
//   `0xA37880` GridEntity（本体）→ `0xA37900` Decoration → `0xA37988` Door → `0xA37A40` Fire
//   → `0xA37AC8` Gravity → `0xA37B50` Lock → `0xA37BD8` Pit → `0xA37C60` Poop
//   → `0xA37CE8` PressurePlate → `0xA37D88` Rock → `0xA37DF8` Spikes → `0xA37E80` Stairs
//   → `0xA37F08` Statue → `0xA38000` Teleporter → `0xA38088` TNT → `0xA38110` TrapDoor
//   → `0xA38198` Wall → `0xA38220` Web（**末位**）
//
//   ★ 按 ABI，对象首字存的是 `_ZTV + 0x10`（既有 `kGridEntityVtableOffset = 0xA37890`
//     就是 `0xA37880 + 0x10`）⇒ 区间取 `[0xA37890, 0xA382A8)`（末位 `0xA38220 + 0x10 + 0x88`）。
//   ★ 前一族 vtable 是 `0xA37820`（`ReferenceCount<EntitySave...>`）、后一族是 `0xA3A8A8`
//     （`Sprite`）⇒ 这 18 个确实**连成一片**。
//   ★★ **已知局限**（真机项里核）：既有的 `kEntityVtableRangeEndOffset = 0xA38230` **盖住**了
//     本区间的头部 ⇒ 「已经销毁、且那块内存被复用成 `Entity`」这种极端情况会被判成"还活着"。
//     代价是**误判为活**时才可能踩内存，而"判死"只会让 `GetSprite()` 退回 nil（安全）。
inline constexpr uintptr_t kGridEntityVtableRangeBeginOffset = 0xA37890;
inline constexpr uintptr_t kGridEntityVtableRangeEndOffset = 0xA382A8;

// ============ 批次 312（2026-10-03）：`EntityPlayer:IsCoopGhost()` 的**合作幽灵标志字节** ============
//
// 契约（`tools/pc_contract_docs/EntityPlayer.md:1499-1501`）：
//   `#### boolean IsCoopGhost ( )` 正文「In a multiplayer game, if a player dies, they will return
//   as a tiny ghost. This method returns true if the player is a co-op ghost.」
//
// **PC 侧**（`python3 tools/pc_exe_binding.py IsCoopGhost --disasm`）：
//   名字表项（文件 `0x404FFA` / `0x404FFF`）是成对的
//   `push 0x6C4AF0`（函数，`.text`）+ `push 0xB52F0C`（字符串 `"IsCoopGhost"`，`.rdata`）
//   ⇒ 绑定函数 `0x6C4AF0`：
//       6c4af0  mov al, byte ptr [ecx + 0x1f88]     ; 读 **一个字节**、直接当返回值
//       6c4af6  ret
//   ⇒ **PC 偏移 `Entity_Player + 0x1F88`**（★ 数值不许平移）。
//   ★ 表项顺序是 `push <函数>; push <名字>` —— 本批特意逐字节核过（上一篇 `push 0x7980B0` +
//     `push 0xB52FDC "GetPoopMana"` 同形），不是靠工具自述。
//
// **Switch 侧偏移 `0x284C` 的取值锚点 = 引擎自己的三个具名写入方 + 一个具名消费者**
//   （★ 不是「某处有个字节」，四个函数语义完全吻合）：
//
//   ① `Entity_Player::morph_to_coop_ghost() @ 0x2E788C`（变成合作幽灵）**置 1**：
//        0x2E78B0  mov  w9, #0x27e0
//        0x2E78BC  add  x22, x0, x9          ; x22 = 玩家 + 0x27E0
//        0x2E7C14  mov  w21, #0x1
//        0x2E7C30  strb w21, [x22, #0x6c]    ; 玩家 + 0x27E0 + 0x6C = 玩家 + 0x284C ⇒ 1
//       （同一段里 0x2E7C40 `strb w21,[x19,#0x1c1]` 把"可见"也置 1 —— 与"变成一个小幽灵"一致）
//   ② `Entity_Player::init_coop_ghost() @ 0x2F7FF8`（初始化合作幽灵）**置 1**：
//        0x2F8018  mov  w8, #0x284c
//        0x2F801C  add  x22, x0, x8
//        0x2F8164  mov  w21, #0x1
//        0x2F817C  strb w21, [x22]           ; 玩家 + 0x284C ⇒ 1
//   ③ `Entity_Player::revive_coop_ghost() @ 0x2F7CDC`（复活、不再是幽灵）**清 0**：
//        0x2F7CF4  mov  w8, #0x284c
//        0x2F7CF8  strb wzr, [x0, x8]        ; 玩家 + 0x284C ⇒ 0
//   ④ `PlayerManager::GetNumCoopPlayersAlive() @ 0x4433B4`（**具名消费者**，统计"还活着的合作玩家"）：
//        0x4433D8  mov  w11, #0x284c
//        0x4433E0  ldrb w12, [x12, x11]      ; 读这一格
//        0x4433E4  eor  w12, w12, #0x1       ; 取反
//        0x4433E8  add  w0, w0, w12          ; 计数 += (标志 == 0)
//       ⇒ 它数的是**标志为 0** 的玩家，而函数名是 `GetNumCoopPlayersAlive`（活着的合作玩家）
//         ⇒ **置 1 = 已经不是"活着的玩家" = 是合作幽灵**。与 ①②③ 的置位方向逐字吻合。
//
//   ★ 同族 `PlayerManager::ReviveCoopPlayers()` 也引用 0x284C（批量清这一类玩家）—— 第五条旁证。
//   ★ 常见误认：`Entity + 0x384`（同样是 morph/init 置 1、revive 清 0 的字节）**不是**这一格 ——
//     它落在 `Entity` 基类区（紧邻 `+0x388` 的 Vector(1,1) 缩放与 `+0x390` 的 `Parent`），
//     且被 `Entity::TakeDamage` / `Entity::IsVulnerableEnemy` / `Entity_Player::EvaluateItems`
//     大量读取 ⇒ 是碰撞/受击类的标志，与 PC 的 `+0x1F88` 对不上。判别靠的是 ④ 那条消费者。
//
//   PC→Switch 的偏移差在这一带约 `0x8C4`（同族已定案对照：`PlayerType` PC `0x130C` ↔ Switch
//   `0x1738`、`_cacheFlags` PC `0x14B8` ↔ Switch `0x1958`，差值随深度单调增大）⇒ 推算落点约
//   `0x2700~0x2850`，与实测 `0x284C` 相符。
inline constexpr uintptr_t kEntityPlayerCoopGhostFlagOffset = 0x284C;   // 1 = 是合作幽灵（byte）

// ============ 批次 313（2026-10-03）：`Level` 头部两个**布尔标志字节** ============
//   `Level:HasBossChallenge()`（契约 `tools/pc_contract_docs/Level.md:271`）与
//   `Level:GetCanSeeEverything()`（同页 `:104`）。两条都是"读一个字节、非 0 即真"。
//
// ① PC 侧绑定本体（各自只有两条指令，`pc_exe_binding.py` 拿到 VA 后按地址区间取）：
//      HasBossChallenge   @ 0x7FA860: movb 0x8(%ecx), %al ; ret   ⇒ PC Level + 0x08
//      GetCanSeeEverything@ 0x7FA870: movb 0x11(%ecx), %al; ret   ⇒ PC Level + 0x11
//    ★ 两条在**同一张名字表簇**里（相邻 0x10），同簇还有 `SetCanSeeEverything`（写侧）、
//      `IsDevilRoomDisabled` / `IsPillIdentified` / `IsCustomRun` / `DungeonReturnPosition`
//      —— 也就是**同一批 Level 布尔**，读法都是"取一个字节当 bool"。
//
// ② ★★★ **Switch 的 `Level` 头部与 PC 逐格一致**（三条独立锚点，Switch 侧各自有具名函数）：
//      `Level + 0x00` = `eLevelStage`（`Level::SetStage` 用 `stp w21, w20, [x19]` 把两个参数
//                       连着写进 `+0x00`/`+0x04`；见 `kLevelStageOffset` 段）
//      `Level + 0x04` = `eStageType`（同上；另有 `Level:IsAltStage` 走 `+0x04 != 0`）
//      `Level + 0x0C` = 诅咒位掩码（`Level::IsNextStageAvailable @ 0x3DBF14` 读 `[x20,#0xc]`；
//                       PC 的 `Level::GetCurses` 也是 `orl 0xc(%ecx), %esi`）⇒ `kLevelCursesOffset`
//    ⇒ `+0x08` 夹在 `+0x04`（u32 结束处）与 `+0x0C`（u32 起始处）**之间** ⇒ 两平台同格。
//
// ③ ★★ Switch 侧这两格都是 `Level::StoreGameState` / `RestoreGameState` 存读的**四个字节标志**
//    之二（同一个 `GameState` 区块 `+0x1B8~+0x1BB`）：
//      StoreGameState   @ 0x3E5898: ldrb w9, [x0, #0x8]    ; Level + 0x08 → 存档
//      RestoreGameState @ 0x3E4E78: strb w8, [x19, #0x11]  ; 读档 → Level + 0x11
//                       @ 0x3E4E80: strb w8, [x19, #0x8]   ; 读档 → Level + 0x08
//      （另两格是 `+0x09` 与 `+0x10`；四个字节各自独立 ⇒ `+0x10` 与 `+0x11` 是两个 1 字节成员）
//    ★ `Level::Init @ 0x3E0978` 也写 `strb w8, [x19, #0x8]`（初始化这一格）。
//
// ④ ★★★ **`+0x11` 的具名消费者（语义自证）**：`Level::try_display_room
//    @ 0x3D90C4-0x3D90D8`（决定"这一间还没去过的房间要不要显示在地图上"）：
//        0x3D90CC  bl  PlayerManager::FirstCollectibleOwner   ; w1 = 0x4C = 76
//        0x3D90D0  cbnz x0, 显示                              ; 76 = COLLECTIBLE_XRAY_VISION（透视）
//        0x3D90D4  ldrb w8, [x20, #0x11]                     ; 否则读 Level + 0x11
//        0x3D90D8  cbz  w8, 跳过                              ; 这一格为 0 ⇒ 不显示
//      ⇒ 「有透视 **或** 这一格非 0 ⇒ 显示整张地图」= **`GetCanSeeEverything` 的语义逐字对应**。
//      （76 的枚举名核对过：`analysis/isaacdocs-snapshot/docs/enums/CollectibleType.md`
//        的 `|76 |COLLECTIBLE_XRAY_VISION`。）
//
//   ★ 已知局限：`+0x11` 的**写入方**没有具名函数（PC 那边是 `SetCanSeeEverything`）；本条只读，
//     不依赖写入方。★ 真机项 V63 用「透视前后 + 调试台命令」两次读数核它。
inline constexpr uintptr_t kLevelBossChallengeOffset = 0x08;      // 1 = 本层是 Boss 挑战（byte）
inline constexpr uintptr_t kLevelCanSeeEverythingOffset = 0x11;   // 1 = 能看到整张地图（byte）

// ---- 批次 314（2026-10-03）：`EntityNPC:IsChampion()` 的**冠军标志字节** = `Entity_NPC + 0xD0F` ----
// 契约 `tools/pc_contract_docs/EntityNPC.md:93`：`#### boolean IsChampion ( )`。
//   PC 侧绑定 `0x68F580`（名字表项 = `push 0x68F580` + `push 0xB53448 "IsChampion"`），
//   本体**只有两条指令**：
//       68f580  movb 0xbb3(%ecx), %al ; ret      ⇒ PC 偏移 `Entity_NPC + 0x0BB3`（**读一个字节**）
//   ★★★ **本批更正了批次 296 记下的一条负结果**：那一批写「PC 的绑定 @ `0x68F550` 是
//     `cmp byte [ecx+0xB8C],0` + `mov eax,[ecx+0x160]; and eax,0x20000000` —— 两个条件」
//     ⇒ 判成"少一半证据、宁缺勿错"。本批核了名字表：**`push 0x68F550` 在全镜像里出现 0 次**
//     （没有任何名字表项指向它）⇒ 那段代码**根本不是这条 API 的绑定**，是**读串了函数**
//     （与批次 311 的"孪生 API 张冠李戴"**同一类错的第二次实例**；判别办法同样是
//      "先把绑定 VA 从名字表里核出来，再去反汇编那一段"）。
//     ★ 顺带把同簇的真身一并还原（行序规则"func 在前、名字在后"，见批次 313 的验证）：
//       `IsChampion` → `0x68F580` ✓、`MakeChampion` → `0x6A6570`、`SetCanSeeEverything` → `0x59FED0`、
//       `ControlsEnabled` → `0x68F590`（那是 `movb 0x360(%ecx),%al`，与冠军无关）。
//   ★ Switch 侧那一格**批次 296 当时已经锚定**（只差"另一半"，而本批证明**根本不需要**另一半）：
//     * 具名写入方（三个）：`Entity_NPC::Init @ 0x105F34` **清 0**（`strb wzr, [x0, #0xd0f]`，
//       与 `0x105F14 str x25(-1), [x0, #0xd10]` 同批 ⇒ 建实体时"标志 0 + 色号 -1"）；
//       `Entity_NPC::MakeChampion @ 0x108FDC` **置 1**（`strb w8(1), [x19, #0xd0f]`，紧接着
//       `0x108FE0 str w21, [x19, #0xd10]` 把第二个实参写进冠军色号）；
//       `Entity_NPC::Morph @ 0x10FB5C` **置 1** / 另一支 `0x10FB90` **清 0**
//       （`strb wzr, [x19, #0xd0f]`，与 `0x10FB8C str w8(-1), [x19, #0xd10]` 同批）。
//     ⇒ **"标志"与"色号"永远同批写** = 「是不是冠军」这一件事在引擎里就是这两格一起翻。
//   ★★★ **免费的交叉印证（本批新增）**：PC 的冠军**标志**在 `0xBB3`（1 字节）、冠军**色号**在
//     `0xBB4`（i32）—— 两格**紧邻、间距 1**；Switch 侧是 `0xD0F`（1 字节）与 `0xD10`（i32）
//     —— **也是紧邻、间距 1**。相对顺序与间距两边一致（与批次 296 记的"两个色号相距 `0x14`、
//     两边也一致"同一类免费印证），而两边**绝对值完全不同** ⇒ 又一次"偏移不许平移"。
//   ★ 降级档 = `FieldMissing::False`：读不到时答"不是冠军"（与 PC 上读到 0 同值），**不抛 Lua 错误**。
inline constexpr uintptr_t kEntityNpcChampionFlagOffset = 0xD0F;    // 1 = 是冠军（byte）

// ============================================================================
// 批次 328（2026-10-03）：`EntityPlayer:GetShootingInput()` / `GetShootingJoystick()`
// —— 两条 API 在 PC 上**共用同一份实现** ⇒ 我们同样只接一个引擎函数
// ============================================================================
//
// **PC 侧**：两个名字的名字表项指向**同一个 VA `0x741B00`**（各跑一次
// `python3 tools/pc_exe_binding.py GetShootingInput` / `GetShootingJoystick` 即可复现）
// ⇒ PC 的 `GetShootingInput` 与 `GetShootingJoystick` 是**同一份胶水**、返回值逐值相同。
// 契约原文（`tools/pc_contract_docs/EntityPlayer.md`）：
//   * :1235 `#### [Vector](Vector.md) GetShootingInput ( )` —— "Returns a vector that corresponds
//     to the shooting inputs that this player is **pressing**."
//   * :1245 `#### [Vector](Vector.md) GetShootingJoystick ( )` —— "…that this player is
//     **holding**. See the image for the [GetShootingInput](#getshootinginput) method."
// ⇒ 两条的返回值语义在实现上是同一条（PC 正是这么做的）⇒ 我们也用同一个引擎函数。
//
// **PC 绑定本体是一段算法**（不是 `call 0x…`）⇒ 按"判法四档"的 **②档**：**去 Switch 侧找同名函数、调它**。
//   同名函数 = `_ZN15IsaacRepentance13Entity_Player18get_shooting_inputEv` @ **`0x2B0FFC`**
//   （入口首 4 字节 `0xD10143FF`；`python3 tools/nro_disasm.py 0x2b0ffc 0xc0` 可复核）。
// ★★★ **本批顺手发现的某类盲点**：工作清单按 **Lua 名**（`GetShootingInput`）去符号表查，
//   而引擎里是 **snake_case**（`get_shooting_input`）⇒ 清单报了 `no_symbol`、把它塞进
//   `needs_forensics`。同一次排查还捞出 `Entity_Familiar::follow_parent` /
//   `add_to_followers` / `follow_position` —— **按 snake_case 复查能翻出一批**。
//
// **函数体做了什么**（读完整个函数体，不是只看头几条）：
//   1. `0x2B1014` `add x0, x29, #0x18` + `bl KAGE::Math::Vector2::Vector2()` ⇒ 先建一个**零向量**当累加器；
//   2. `0x2B101C`..`0x2B10A8` 读全局 `g_Game`，在一棵树上按 `+0x1c` 与常量 `0x4a` / `0x4b` 比较查找；
//      命中某支时 `0x2B1078 bl Entity_Player::get_movement_input()` ⇒ **把"移动输入"当作射击输入的一份**；
//   3. `0x2B10B4` `mov w8, #-0x40800000`（= **-4.0f**）→ `Vector2::operator*(float const&)`
//      ⇒ 对输入做**缩放/取反**（这就是那个"方向图"里的角度换算）；
//   4. 另一支走 `g_Manager` 的 `Manager::GetActionValue(action, controllerIndex, player)`，
//      **action 取 4 / 5 / 6**（`0x2B10F0` / `0x2B110C` / `0x2B112C`），把每次的 `s0` 累加/相减进累加器。
//   ⇒ 语义 = "玩家当前**按下/保持**的射击输入向量"，与契约那两句对上。
//
// ★★ **返回走 `s0`/`s1`（不是 `x8`）**：`KAGE::Math::Vector2` 是两个 `float` 的 **HFA**
//   ⇒ AAPCS64 规定按 `s0`/`s1` 返回。旁证就在本函数体内：`0x2B10B0 bl get_movement_input`
//   之后紧接 `0x2B10BC stp s0, s1, [sp, #0x10]` —— 引擎自己就是这么接那个返回值的。
//   （同族先例：`Sprite:GetTexel` 那条偏离台账里写的 "HFA 传参与 `KColor` 走 `x8` 的 ABI" 是**两件事** ——
//    HFA **入参/返回**走 `s`/`d` 寄存器，而 `KColor`（两个 `Vector`）不是 HFA ⇒ 才走 `x8`。）
//
// ★★★ **为什么手写、而不是数据行**：通用跳板 `engine_call_trampoline.s` 只把 `x0` 与 `d0`
//   回填给调用方（`str x0, [x9]` / `str d0, [x10]`）⇒ **两个浮点的返回在机制内表达不了**。
//   照 `Room:GetCenterPos()` 的先例**手写处理器**（那条就是这么做的：用一个"返回两个 float 的结构体"
//   的函数指针类型，让编译器按 HFA 约定生成 `s0`/`s1`）。代价 ≈ 一条手写处理器（几百字节），
//   换来 **2 条 API / 16 处**（`GetShootingInput` 14 处 + `GetShootingJoystick` 2 处，是全清单最大的一块）。
inline constexpr uintptr_t kEntityPlayerGetShootingInputOffset = 0x2B0FFC;
inline constexpr std::uint32_t kEntityPlayerGetShootingInputEntryWord = 0xD10143FFu;

// ============================================================================
// 批次 330（2026-10-03）：`EntityFamiliar:FollowParent()` / `AddToFollowers()`
// —— ★ 本批的产出是**给 `EntityFamiliar` 建自己的视图**，这两条是它的第一批住户
// ============================================================================
//
// **为什么先建视图**：这两条方法挂在 `EntityFamiliar` 这个类上，而 `Entity:ToFamiliar()` 此前
// 压的是**基类 `Entity` 元表**（批次 9 起）⇒ `EntityFamiliar` 页上的方法**没有地方挂**，
// 语料里 `familiar:FollowParent()` 报 "attempt to call a nil value"（整条回调被摘）。
// 做法照**批次 285 给 `EntityNPC` 立的那一套**（`kEntityNPCMetatable` + `EntityView::Npc` +
// `CheckEntityHandle` 认它 + 注册处那一段）⇒ 本批新增 `kEntityFamiliarMetatable` 与
// `EntityView::Familiar`，并让 `ToFamiliar()` 压新元表；字段仍回落到 `Entity`。
//
// **PC 契约**（`tools/pc_contract_docs/EntityFamiliar.md`）：
//   * :47 `#### void AddToFollowers ( )`
//   * :65 `#### void FollowParent ( )`
// 两条都是**无参、返回 `void`** —— 是本清单里最便宜的形状（复用现成的 `EngineCallShape::Void0`，
// 所以本批**没有新形状**）。
//
// **PC 绑定本体**（`python3 tools/pc_exe_binding.py <名字> --disasm` 给 VA，再按区间自己取）：
//   * `AddToFollowers` → VA `0x60D000`：`mov eax,[edi+0xe20]` → `cmp [eax],0x1` →
//     `cmp [eax+4],0x295` → 相等就跳走；否则 `mov ecx,[edi+0x2c]` / `cmp ecx,0xeb` …
//   * `FollowParent`   → VA `0x447DE0`：`mov ecx,[ebx+0x314]` → `test ecx,ecx` → 非空时
//     `push &(this+0x314)` + `add ecx,0x324` + `call 0x4bc3c0`。
// ⇒ 两条的**本体都是算法**（不是"直接 `call` 到同名方法"）⇒ 按"判法四档"的 **②档**：
//   **去 Switch 侧找同名函数、调它**。同名函数逐字存在（**snake_case**）：
//   * `_ZN15IsaacRepentance15Entity_Familiar13follow_parentEv` @ **`0xAEC14`**（入口首 4 字节 `0xD10243FF`）
//   * `_ZN15IsaacRepentance15Entity_Familiar16add_to_followersEv` @ **`0xAC958`**（入口首 4 字节 `0xD10143FF`）
//
// ★★★ **名字对不上的风险核过了（这一步不能省）**：PC 的 `AddToFollowers` 里出现的
//   `[ptr]==1 && [ptr+4]==0x295` 那一对检查，**Switch 的 `follow_parent()` 里也有**
//   ⇒ 光看这一条会怀疑"是不是两个名字接反了"。**逐条对照函数体之后确认没接反**：
//     * Switch `add_to_followers()`（`0xAC95C`..）：`ldr x8,[x0,#0xf50]` → `cbz` →
//       `ldr w9,[x8]` / `cmp w9,#0x1` / `ldr w8,[x8,#0x4]` / `cmp w8,#0x295` →
//       然后 `ldr w20,[x19,#0x3c]` / `cmp w20,#0xeb`（**235**）/ … / `bl Entity::SetParent` /
//       读 `g_Game`；
//     * PC `AddToFollowers`（`0x60D000`..）：`mov eax,[edi+0xe20]` → `cmp [eax],1` /
//       `cmp [eax+4],0x295` → 然后 `mov ecx,[edi+0x2c]` / `cmp ecx,0xeb`（**235**）/ …
//     ⇒ **同样的三连（同一格的 1 / 0x295 检查，随后比 0xeb=235）** ⇒ 这就是同一套算法，
//       `add_to_followers ∷ AddToFollowers`、`follow_parent ∷ FollowParent` 逐字对应。
//   ★ 而两条 Switch 函数都以同一格 `[this+0xf50]` 开头（PC 侧对应 `+0x314`/`+0xe20` 那两个
//     成员），这也解释了"为什么前几条指令看着像"。
//
// ★★ **接收者为什么必须精确判**：`FieldReceipt::EntityFamiliar`（新收的第 10 档）要求
//   **精确**的 `base + kEntityFamiliarVtableOffset` 且 `Type == EntityType.ENTITY_FAMILIAR`。
//   理由不是洁癖：`follow_parent()` 的**第一条字段访问**就是 `ldr x8,[x0,#0xf50]`，紧跟 `cbz x8`
//   之后**解引用**它（`ldr w9,[x8]`）⇒ 拿一个别的实体当 `this` 交进去会**野读**。
//   （对照：`EntityNPC` 那两条是**读** `+0xD0F`/`+0xD10`，看错类型最多读到别人的值 —— 读与调的危险等级不同。）
//   ★ 判据与 `Entity:ToFamiliar()` 的那条**同一份实现**（`ValidatedEntityFamiliar`）。
inline constexpr uintptr_t kEntityFamiliarFollowParentOffset = 0xAEC14;
inline constexpr std::uint32_t kEntityFamiliarFollowParentEntryWord = 0xD10243FFu;
inline constexpr uintptr_t kEntityFamiliarAddToFollowersOffset = 0xAC958;
inline constexpr std::uint32_t kEntityFamiliarAddToFollowersEntryWord = 0xD10143FFu;

// ============================================================================
// 批次 332（2026-10-03）：`EntityPlayer:GetMovementJoystick()` —— 与 328 那对**同型**
// ============================================================================
//
// **PC 契约**（`tools/pc_contract_docs/EntityPlayer.md:1106`）：`#### [Vector](Vector.md) GetMovementJoystick ( )`
// —— 无参、返回一个 `Vector`（同页还有同族的 `GetMovementInput` :1100 与 `GetMovementVector` :1111）。
//
// ★★ **PC 侧 `GetMovementInput` 与 `GetMovementJoystick` 共用同一个绑定 VA `0x741880`**
//   （`python3 tools/pc_exe_binding.py <名字>` 各跑一次即可复现）⇒ 两条在 PC 上是同一份实现。
//   （同一先例：328 的 `GetShootingInput` / `GetShootingJoystick` 共用 `0x741B00`。）
//   ★ 本批**只接语料真正用到的那一条**（`GetMovementJoystick`，4 处）；
//     `GetMovementInput` 是同一段代码的另一张门面 —— 将来有模组用到时，加一行目录 + 一行绑定即可。
//
// **Switch 侧真身**：`_ZN15IsaacRepentance13Entity_Player18get_movement_inputEv` @ **`0x2B0D9C`**
//   （入口首 4 字节 `0xD10103FF`；`python3 tools/nro_disasm.py 0x2b0d9c 0x110` 可复核）。
//   ★ 又是 **snake_case**（Lua 名 `GetMovementJoystick` 在符号表里查不到 —— 329 的兜底也搜不到，
//     因为**名字本身不同**：`joystick` vs `input`）；PC 绑定本体是**算法** ⇒ 判法四档第 ② 档。
//
// ★★★ **"名字不同名"这一步必须靠函数体定案 —— 本批把 PC 与 Switch 的检查逐条对齐过**：
//
//   | 检查 | PC `GetMovementJoystick`（`0x741880`..） | Switch `get_movement_input`（`0x2B0D9C`..） |
//   | --- | --- | --- |
//   | 玩家类型 | `mov eax,[esi+0x130c]` / `cmp eax,0x14` | `ldr w8,[x0,#0x1738]` / `cmp w8,#0x14` |
//   | 父指针 | `mov ecx,[esi+0x314]` / `test` / `cmp [ecx+0x28],0x1` | `ldr x9,[x19,#0x390]` / `cbz` / `ldr w9,[x9,#0x38]` / `cmp w9,#0x1` |
//   | 另两个类型 | `cmp eax,0x1d` / `cmp eax,0x26` | `cmp w8,#0x26` / `cmp w8,#0x1d` |
//   | 双子比较 | `[ecx+0x1550]` vs `[esi+0x1550]` | `[x8+0x19f0]` vs `[x19+0x19f0]` + `csel` |
//   | 能不能操作 | `cmp byte [esi+0x360],0` | `ldrb w8,[x19,#0x400]`（= **`ControlsEnabled`**，批次 313 已定案） |
//   | 冷却 | `cmp dword [esi+0x364],0` / `jg` | `ldr w8,[x19,#0x404]`（= **`ControlsCooldown`**，批次 291 已定案）/ `cmp #0` / `b.gt` |
//   | ★ **动作号** | `push 0xb` → `call 0x8b10b0`（`IsActionPressed`）→ `test al,al` | `mov w1,#0xb` → `bl Manager::IsActionPressed` → `tbz w0,#0x0` |
//   | 按下时的返回 | 往返回缓冲写两个常量（`[0xc02fec]`/`[0xc02ff0]`） | `ldp s0, s1, [Vector2::Zero]` ← **同一件事**：置零 |
//   | 未按下的分支 | `push 0/1/2` → `call 0x8b1240` 三次，`subss`/`addss` 累加 | `Manager::GetActionValue(w1 = 0/1/2, controllerIndex=[x19+0x19ec], player)` 三次，`fsub`/`fadd` 累加 |
//
//   ⇒ **七条检查 + 动作号 `0x0b`(11) + 两条分支的做法全部一一对应** ⇒ 这就是同一个函数。
//   ★ 这条对得上尤其重要：`GetMovementJoystick`（我们）与 `get_movement_input`（引擎）**名字不一样**
//     （`joystick` vs `input`），**只看名字会判"查不到"**；328 那次是"同名的两种拼写"，
//     这一次是"**同义的两种命名**"——**判据永远只能是函数体**。
//   ★ 顺带一条结构旁证：328 那条 `get_shooting_input()` 内部就**调用**了本函数
//     （`0x2B1078 bl <get_movement_input 的 PLT>`）—— 射击输入里含移动输入那一份，与 PC 的
//     `GetShootingInput` 绑定（`0x741B00`）里同样含移动分量一致。
//
// ★★ **返回走 `s0`/`s1`（HFA）**：两条分支的返回分别是 `Vector2::Zero` 的 `ldp s0, s1, [x8]`
//   与累加器的 `s0`/`s1` ⇒ 与 328 一样，**通用跳板只回填 `x0`/`d0` ⇒ 机制内表达不了** ⇒ **手写**。
//   复用 328 已经立好的 `EngineVector2Abi`（"两个 `float` 的结构体"）与那套接法。
inline constexpr uintptr_t kEntityPlayerGetMovementJoystickOffset = 0x2B0D9C;
inline constexpr std::uint32_t kEntityPlayerGetMovementJoystickEntryWord = 0xD10103FFu;

// ============================================================================
// 批次 333（2026-10-03）：`Entity:MultiplyFriction(float Value)` —— `Entity` 的**摩擦**（一对格）
// ============================================================================
//
// **PC 契约** `tools/pc_contract_docs/Entity.md:510`：`#### void MultiplyFriction ( float Value )`
// —— 只有签名、没有散文 ⇒ **语义由绑定本体定**。
//
// **PC 绑定本体**（`0x5951D0`，逐字）：
//     movss xmm0, [ebp + 0x8]        ; Value
//     mulss xmm0, [ecx + 0x2c4]      ; × 实体那一格
//     movss [ecx + 0x2c4], xmm0      ; 写回
//     ret 4
// ⇒ 读改写一个 `float`（判法四档的 **①档**：字段写 ⇒ 走**数据行**）。
//
// **Switch 侧：那一格是 `Entity + 0x340`**。★ 旁边还有一格 `+0x33C`，两格构成
// **"原值 / 本帧值"** 一对 —— 选哪一格是这一批**唯一需要判**的事，四条证据如下：
//
//   ① **谁在用**：`Entity::Update` @ `0x6026C` 读 `+0x340` 喂给
//      `TimeScaledFriction(friction, dt)`（`0x672110`），紧接着把返回值**乘进速度向量**
//      （`0x6028C` 的 `Vector2::operator*=(x21 = this+0x334)`）⇒ **`+0x340` 才是"生效的那一格"**
//      （函数名 `TimeScaledFriction` 即语义 = 摩擦；这也是本行的**独立语义锚点**）。
//   ② **它是被衰减的**：同一函数 `0x60144`..`0x6015C`：
//      `mov w8,#0x3333` + `movk w8,#0x3f73,lsl#16`（= **0x3F733333 = 0.95f**）→ `fmov s1,w8` →
//      `ldr s0,[x19,#0x33c]` → `fmul s0,s0,s1` → `str s0,[x19,#0x340]`
//      ⇒ `+0x340 = +0x33C × 0.95f`：**教科书式的"摩擦衰减"**（且带了立即数锚点）。
//   ③ **`+0x33C` 是原值**：`Entity::Init(eEntityType,eVariant,eSubType,uSeed)` @ `0x59860` 与
//      `0x59898` 两处都是 `ldr w8,[x19,#0x33c]` → `str w8,[x19,#0x340]`（**把原值拷进本帧值**），
//      而 `Entity::Update` @ `0x602B8` 也做同一次拷贝（每帧先复位、再按分支衰减）。
//   ④ ★★ **语料用法把这一条钉死**：`IsaacOnTwitchReloaded/scripts/events.lua:850` 在
//      `events.EV_Slip` 的 **`onUpdate`（每帧）** 里调 `p:MultiplyFriction(1.2)`
//      ⇒ 乘**原值**会逐帧指数级累积（1.2 的帧数次方）、乘**本帧值**才是模组要的效果
//      （每帧在原值基础上放大 1.2 倍，且下一帧会被复位）⇒ **取 `+0x340`**。
//
// ★ 同族的旁证：PC 的 `FollowPosition` 绑定（`0x5F4EB0`）也把 `[ecx+0x2c4]` **乘一个常数**用
//   （与"被衰减的本帧值"同一角色），而 Switch 这边被 `TimeScaledFriction` 消费的正是 `+0x340`。
//
// ★ 顺带记两条**负结果**（省得后人重复查）：
//   * `Entity` 上没有 `multiply_friction` / `friction` 一类符号（全符号表子串扫描 0 命中），
//     `TimeScaledFriction` / `Entity_Tear::SetHomingFriction` 是**别的**函数（前者是公式、后者在眼泪上）；
//   * `EntityLaser:SetMaxDistance` 的 Switch 偏移**本批没找到**（PC 在 `EntityLaser+0x420`、
//     是"写一个 float"；Switch 侧既无具名访问器、也没有同形的消费点可比）⇒ **留待下一批**。
inline constexpr uintptr_t kEntityFrictionOffset = 0x340;

// ============================================================================
// 批次 334（2026-10-03）：`EntityPlayer:CheckFamiliar(...)` —— 一条**引擎方法行做不到**的调用
// ============================================================================
//
// **PC 契约** `tools/pc_contract_docs/EntityPlayer.md:591`，逐字：
//
//     void CheckFamiliar ( FamiliarVariant FamiliarVariant, int TargetCount, RNG rng,
//                          ItemConfigItem SourceItemConfigItem = nil, int FamiliarSubType = -1 )
//
// ⇒ **5 个形参、后两个带缺省值**（`nil` 与 `-1`）。散文另给了两条关键信息：
//   * 「Call this method to spawn the appropriate amount of familiars associated with a custom
//     collectible」——按 `TargetCount` 把该 `FamiliarVariant` 的随从**增到/减到**这个数；
//   * `rng`：「Can just be the RNG object from `EntityPlayer.GetCollectibleRNG`」
//     ⇒ 语料那三处正是这么写的（`player:GetCollectibleRNG(item.id)`）。
//
// **引擎符号（snake_case）逐字存在**：
//   `_ZN15IsaacRepentance13Entity_Player14check_familiarEjiRNS_3RNGEPKNS_10ItemConfig4ItemEi`
//   = `Entity_Player::check_familiar(unsigned int, int, RNG&, ItemConfig::Item const*, int)` → `void`
//   @ **`0x29AD94`**，入口首 4 字节 = **`0xD10243FF`**（= `sub sp, sp, #0x90`）。
//
// **反汇编（`python3 tools/nro_disasm.py 0x29ad94 0x140`）—— 三件事各自钉住一格**：
//
//   * 五个形参全走整数寄存器（`this` 之外）：`mov w21, w1`（TargetCount）、
//     `bic w25, w2, w2, asr #31`（FamiliarVariant，顺带 clamp 到 ≥ 0）、
//     `mov x20, x3`（RNG 引用）、`mov x19, x4`（SourceItem 指针）、`mov w24, w5`（FamiliarSubType）。
//     ⇒ 没有浮点、没有栈上传参 ⇒ 六个 `x` 寄存器装得下。
//   * ★★ **第 3 参是真 RNG、而且引擎会推进它**：`0x29AE60  mov x0, x20` →
//     `0x29AE64  bl 0x66FE90 <_ZN15IsaacRepentance3RNG4NextEv>`。⇒ 传进去的必须是**那颗真 RNG**，
//     不能是快照 —— 我们 Lua 侧的 `RngHandle::storage` 恰好就是 16 字节的**引擎 RNG 对象裸存储**
//     （`RNG:SetSeed`/`Next`/`RandomInt` 都把 `storage.data()` 当 `this` 交给引擎），
//     与 `Level:QueryRoomTypeIndex` 第 3 参**同一件东西** ⇒ 直接把地址交出去即可（不是替身）。
//   * ★★ **第 4 参（SourceItem）取 `nil` 是安全的、且它就是"存进随从的一个字段"**：
//     `0x29AEB0  str x19, [x26, #0xf50]`（把指针写进新建随从的 `+0xf50`）。传空指针 = 写 0，
//     与 PC 的缺省 `nil` 逐字一致（文档另说明它只影响 Sacrificial Altar 消不消耗那个收集品）。
//   * ★★★ **第 5 参（FamiliarSubType）取 `-1` 与取 `0` 行为不同**：
//     `0x29AE1C  tbnz w24, #0x1f, 0x29AEFC` —— 拿**符号位**分支。`-1` 走的就是那条特殊分支
//     （文档：`-1 matches any subtype`）⇒ **不能用"省略即 0"那一套**（那会变成"只匹配 subtype 0"，
//     与 PC 不一致）。
//
// **为什么手写处理器、而不是加一种 `EngineCallShape`**（这是本批唯一真需要算的账）：
//   数据行那条路缺**两种表达能力**：① "把 Lua 的 RNG 句柄当 `RNG&` 传"（现有 `Handle` 档走的是
//   `ResolveArgumentHandle` 那套句柄校验，RNG 不在其中）；② "省略时填 `-1` 的整数"（`optionalArgumentCount`
//   的语义写死了"省略的寄存器保持 0"，`FloatDefaultOne` 是它唯一一次破例）。
//   按 326 的校准，**新开一种 `EngineArgKind` ≈ `.text +0x480`** ⇒ 两种 ≈ +0x900；
//   而手写一条 ≈ 300 字节，且只有 3 处受益 ⇒ **手写更省**（与 328/332 同一笔账）。
//
// ★ 顺带记两条：这一条在清单里被归到 `needs_new_receiver`（"差接收者视图"），但我们**早就有**
//   `FieldReceipt::EntityPlayer` ⇒ 那条理由在这条上不成立（清单是按符号可用性粗分的）。
//   ★ 3 处语料调用**全是 3 参写法**（`IsaacOnTwitchReloaded/scripts/callbacks.lua:255`、
//   `RepentancePlus/RepentancePlus/main.lua:1742` 与 `:1743`）⇒ 后两个形参走的正是这两个缺省值。
// ★ PC 那一侧：绑定函数在 **`0x72EB50`**（`python3 tools/pc_exe_binding.py CheckFamiliar --disasm`），
//   本体是一段**真算法（带 SEH 帧、有循环、遍历 ItemConfig 取 `SourceItemConfigItem`）**
//   ⇒ 按判法四档的 **②档** 处理：「PC 本体是算法 ⇒ 去 Switch 找那个真身 / 或调它能调到的部分」，
//   而这条的真身在 Switch 上**逐字存在且可直接调**（就是上面 `check_familiar`），
//   于是 Lua 侧只要补两个形参（`nil` / `-1`）转发即可 —— 无需复现 PC 那段取 item 的算法。
inline constexpr uintptr_t kEntityPlayerCheckFamiliarOffset = 0x29AD94;
inline constexpr std::uint32_t kEntityPlayerCheckFamiliarEntryWord = 0xD10243FFu;

// ============================================================================
// 批次 335（2026-10-03）：三条"符号在 + 尾部多一格缺省参数"的引擎方法行
// ============================================================================
//
// 本批是交接第八份 §3「批 A」：三条**共用一个新形状** `VoidIntBoolOpt1`
// （`void(this, i32, bool)`，尾部 1 个可省）。下面逐条写清楚"为什么按符号取形状"、
// "省略那一格填 0 是不是与 PC 一致"。
//
// ---------------------------------------------------------------------------
// ① `Seeds:SetStartSeed(int)`（2 处；语料 `IsaacOnTwitchReloaded/scripts/events.lua:1433` 与 `:1465`）
// ---------------------------------------------------------------------------
//
// **PC 契约** `tools/pc_contract_docs/Seeds.md:170/172`，逐字：
//
//     #### void SetStartSeed ( string StartSeed )
//     Empty string means we will pick a new random seed.
//
// ★ 契约写的是 **`string`**，而语料传的是**数字**（`local seed = seeds:GetNextSeed()` 的返回值，
//   它是 `int`）⇒ **符号里到底有没有一个吃数字的重载，必须查符号表**，不能照契约想当然。
//
// **符号表逐字有这么两个重载**（`tools/nro_symbols.py` / `inventory.json` 都能查）：
//
//   * `_ZN15IsaacRepentance5Seeds12SetStartSeedENSt3__112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE`
//     = `Seeds::SetStartSeed(std::string const&)` @ **`0x4A10E8`**；
//   * `_ZN15IsaacRepentance5Seeds12SetStartSeedEj` = `Seeds::SetStartSeed(unsigned int)` @ **`0x4A1114`**。
//
// **反汇编把两者的关系钉死**（`python3 tools/nro_disasm.py 0x4a10e8 0x40`）：
//
//     004a10e8  stp x29, x30, [sp, #-0x20]!
//     004a10fc  bl 0x671de0  ; import Seeds::String2Seed(std::string const&)   ← 先把字符串解析成种子
//     004a1100  mov w1, w0
//     004a1104  mov x0, x19
//     004a1110  b 0x67a270   ; import Seeds::SetStartSeed(unsigned int)        ← **尾调数字版**
//
// ⇒ **字符串版只是"解析 + 转交"**，真身是数字版；语料给的就是数字 ⇒ **取数字版**（本行）。
// ★ 语料那两处传的是 `seeds:GetNextSeed()` 的返回值（`int`）—— 走数字重载是**逐字对应**的。
// ★ 遗留的不确定（已挂真机项，见作业单第九节）：PC 的 Lua 绑定是不是先把数字**强制转成
//   字符串**再走字符串版（`luaL_checkstring` 会把数字转成十进制串，而 `String2Seed` 只认
//   9 字符 "ABCD EFGH" 形态 ⇒ 那样会落到"空种子"⇒ 随机）。两种走法**都得到"换一个新种子"**
//   这同一个可观察结果，但**种子值不同** ⇒ 离线判不了，真机读一次 `GetStartSeed()` 即可定案。
//   ★ 数字版的函数体（0x4A1124 起）自带反向证据：`str w1,[x0,#4]`（存进 `Seeds + 4`）→
//     `cbnz w1`（非 0 就跳过）→ 为 0 时 `RandomU32()` 现取一个随机种子 ⇒ 文档那句
//     "Empty string means we will pick a new random seed" 说的就是这个分支。
//
// **接收者**：`Seeds` 在引擎里是**内嵌在 `Game` 里的子对象**（不是指针）⇒ 本批新开
// `FieldReceipt::Seeds` = `Game + kGameSeedsObjectOffset`（与 `Seeds:GetStartSeed()` 手写实现
// 里那条链**同一份常量、同一份判据**）。此前 `Seeds` 家族**没有** engine row 的那种接收者，
// 所以这是本批的"一种新能力"。
inline constexpr uintptr_t kSeedsSetStartSeedOffset = 0x4A1114;
inline constexpr std::uint32_t kSeedsSetStartSeedEntryWord = 0xA9BE7BFDu;  //: `stp x29,x30,[sp,#-0x20]!`

// ---------------------------------------------------------------------------
// ② `EntityPlayer:ChangePlayerType(PlayerType)`（1 处；`RepentancePlus/RepentancePlus/main.lua:1008`）
// ---------------------------------------------------------------------------
//
// **PC 契约** `tools/pc_contract_docs/EntityPlayer.md:581`，逐字：
//     `#### void ChangePlayerType ( [PlayerType](enums/PlayerType.md) PlayerType )`
//   散文（`:583`）：「Used to change one player into another player type. ...」——**只有 1 个形参**。
//
// **Switch 符号**（清单/inventory）：`_ZN15IsaacRepentance13Entity_Player16ChangePlayerTypeENS_11ePlayerTypeEb`
//   = `Entity_Player::ChangePlayerType(ePlayerType, bool)` @ **`0x2AACCC`** ⇒ **arity 2**。
//   ⇒ 按 **G3 口径"按符号取形状"**：默认参数在 ABI 上照样占寄存器 ⇒ 收 2 格、尾部 1 个可省。
//
// **PC 引擎函数的签名逐条核实**（`python3 tools/pc_exe_binding.py ChangePlayerType --disasm`，
//   工具给出的是 **PC 侧引擎函数本体** `0x78FF70`，不是 Lua 胶水）：
//
//     mov ebx, ecx                     ; this
//     cmp byte ptr [ebp + 0xc], 0x0    ; ← **第 2 个形参（bool）真的被读**
//     je  <公共路径>
//     mov eax, [ebp + 0x8]             ; 第 1 个形参 = PlayerType
//     cmp eax, 0x10                    ; PLAYER_THEFORGOTTEN
//     ...（与 Switch 侧 `tbz w2,#0x0` / `cmp w22,#0x11` / `cmp w22,#0x10` **逐条同形**）
//
// ⇒ **PC 与 Switch 的引擎签名一模一样**（都是 `(PlayerType, bool)`，bool 都在第 2 格）。
//
// ★★ **省略那一格填 0 是不是安全**：**这条可以证明"对这 2 处语料完全无影响"** ——
//   Switch 函数体前三条分支（`0x2AACFC`..`0x2AAD18`）的结构是：
//
//       tbz  w2, #0x0, <公共路径>      ; bool == 0 ⇒ 直接走公共路径
//       cmp  w22, #0x11 ; b.eq <特殊>  ; PlayerType == 17 (PLAYER_THESOUL)
//       cmp  w22, #0x10 ; b.ne <公共>  ; 不是 16 ⇒ 公共路径
//       ldr  w8,[x19,#0x1738] ; cmp w8,#0x11 ; b.eq <特殊>
//
//   ⇒ **`PlayerType ∉ {16, 17}` 时 bool 取什么都走同一条路**。语料那处传的是
//     `PlayerType.PLAYER_EVE`（= **5**，见 `analysis/isaacdocs-snapshot/docs/enums/PlayerType.md:14`）
//     ⇒ **bool 对这次调用是惰性的**（这不是"押注"，是分支表读出来的）。
//   ★ 那两条特殊分支是**游戏内部的"被遗忘者 ⇄ 灵魂"互换**：PC 侧内部调用点在 `0x771D65`
//     `push 0x1`（= 真传 `true`）—— 那是**游戏自己**在做互换，与模组调 `ChangePlayerType(角色)`
//     不是同一件事；Lua 契约只有 1 个形参（`ChangePlayerType.md:581`），
//     vanilla 文档里所有带缺省值的形参**缺省全是 0/false/nil** ⇒ 取 0。
inline constexpr uintptr_t kEntityPlayerChangePlayerTypeOffset = 0x2AACCC;
inline constexpr std::uint32_t kEntityPlayerChangePlayerTypeEntryWord = 0xD10243FFu;  //: `sub sp,sp,#0x90`

// ---------------------------------------------------------------------------
// ③ `EntityPlayer:DischargeActiveItem(ActiveSlot)`（1 处；`RepentancePlus/RepentancePlus/main.lua:2249`）
// ---------------------------------------------------------------------------
//
// **PC 契约** `tools/pc_contract_docs/EntityPlayer.md:642/644`，逐字：
//
//     #### void DischargeActiveItem ( [ActiveSlot](enums/ActiveSlot.md) ActiveSlot = ActiveSlot.SLOT_PRIMARY )
//     Sets the charge of your active item to 0 without triggering the active item effect.
//
//   ⇒ 语义 = **把主动道具的充能置 0、但不触发它的效果**；形参带缺省 `SLOT_PRIMARY`（= 0）。
//
// **Switch 符号**：`_ZN15IsaacRepentance13Entity_Player19DischargeActiveItemEib`
//   = `Entity_Player::DischargeActiveItem(int, bool)` @ **`0x2B9540`** ⇒ **arity 2**
//   （契约 1 格 vs 符号 2 格，与 ② 同形）⇒ 同一个新形状。
//
// **函数体头几行**（`python3 tools/nro_disasm.py 0x2b9540 0x60`）证实"第 1 格 = 主动道具槽索引"：
//
//     002b9564  mov w8, #0x1c
//     002b9568  smaddl x8, w1, w8, x0     ; x8 = this + slot*0x1C   ← 按槽索引进数组
//     002b956c  ldr w9, [x8, #0x1964]     ; 该槽的道具 id
//     002b9570  cbz w9, <返回>            ; 空槽 ⇒ 什么都不做
//     002b9590  mov w27, w2               ; ← **第 2 个形参（bool）被保存**
//
// ★ 与 ② 同一口径取 0：Lua 契约只暴露 1 个形参、且它带缺省；vanilla 的缺省值一律是 0。
//   ★ 诚实记一句：这条的 bool **确实参与分支**（`0x2B9C54` 有 `tbnz w27,#0x0`，
//     两条路的差别里有"要不要往 `RemoveCollectible` 走"），**不像 ② 那样能证明对语料惰性**
//     ⇒ 若真机上发现 PC 那一格不是 0，这一条的 bool 要单独改（见作业单第九节的真机项）。
inline constexpr uintptr_t kEntityPlayerDischargeActiveItemOffset = 0x2B9540;
inline constexpr std::uint32_t kEntityPlayerDischargeActiveItemEntryWord = 0xD103C3FFu;  //: `sub sp,sp,#0xf0`

// ============================================================================
// 批次 336（2026-10-03 深夜）：两条"纯读一格"的字段行（交接第八份 批 B/批 C）
// ============================================================================
//
// 本批是**纯取证批**：一次把 `field_row` 那 7 条（外加批 C 里那条"纯读 1 字节"）全查一遍，
// 只落地两条**证据链闭合**的。★ 两条都复用现成的 `FieldKind` + `FieldReceipt` ⇒ **0 字节代码**。
// 其余五条的**负结果**写在 `docs/改动日志-20261003.md` 第四十节（省得后人重复查）。

// ---------------------------------------------------------------------------
// ① `Room:GetTintedRockIdx()` —— `Room + 0xE90`（u32）→ `FieldKind::I32` + `FieldReceipt::Room`
// ---------------------------------------------------------------------------
//
// **PC 契约** `tools/pc_contract_docs/Room.md:559/561`：逐字 `#### int GetTintedRockIdx ( )`（只有签名）。
//
// **PC 绑定本体**（`python3 tools/pc_exe_binding.py GetTintedRockIdx --disasm` ⇒ `0x427750`）：
//
//     00427750  8b 81 64 07 00 00   mov eax, dword ptr [ecx + 0x764]
//     00427756  c3                  ret
//
//   ⇒ PC 上它**就是"读 `Room + 0x764` 这个 i32"**、**没有任何守卫**（对照：同族的
//     `GetDungeonRockIdx` 在 PC 上有一条"某个标志位 ⇒ 直接返回 -1"的前置判断）。
//
// **Switch 侧：那一格是 `Room + 0xE90`** —— 三条独立证据（两条镜像内 + 一条 PC 对照）：
//
//   ① **写入点（语义锚点）**：`Room::Init @ 0x45C020`，地址 `0x45CFF0`..`0x45D000`：
//        `bl RNG::Next()` → `mov w1, w0` → `mov x0, x19`（= this）→
//        `bl Room::GetRandomTileIndex(int)` → **`str w0, [x19, #0xe90]`**
//      ⇒ 房间初始化时**随机挑一个格子索引**存进这一格 —— 这正是"这一间房的染色石头在哪一格"。
//   ② **具名读者**：`Room::spawn_entity @ 0x453918`，三处（`+0x11c` / `+0x220` / `+0x10fc`）：
//        `ldr w9, [x20, #0xe90]` → `cmp w9, w19`（与**当前要生成的格子索引**比较）
//      ⇒ 生成网格实体时拿它判"这一格是不是被标记的那一格"。
//   ③ **PC 对照（顺序）**：PC 上 `GetTintedRockIdx` = `Room+0x764`、
//      `GetDungeonRockIdx` = `Room+0x768`（`0x7DBAA0` 处 `mov eax,[ecx+0x768]`）
//      —— **两格相邻、tinted 在低地址**；Switch 的 `Room::GetDungeonRockIdx()`（符号在，
//      `0x48920C` 处 `ldr w0, [x0, #0xe94]`）读 `0xE94` ⇒ **同序** ⇒ `0xE90` 就是 tinted。
//      ★ 注意：**数值不许平移**（PC 0x764 ≠ Switch 0xE90），这一条只用来定**顺序**。
//
// ★ 为什么不需要"真机判别实验"（`Entity:GetColor` 那条需要，见批 B 的负结果）：
//   这里的三条证据里有一条是**具名消费者**（`Room::spawn_entity` 拿它跟格子索引比），
//   语义不是"两个长得像的字段选一个"，而是"这个函数名 + 这个比较就是它的全部用法"。
inline constexpr uintptr_t kRoomTintedRockIdxOffset = 0xE90;

// ---------------------------------------------------------------------------
// ② `Entity:CollidesWithGrid()` —— `Entity + 0x1EC`（u8）→ `FieldKind::Bool` + `FieldReceipt::Entity`
// ---------------------------------------------------------------------------
//
// **PC 契约** `tools/pc_contract_docs/Entity.md` 的 `CollidesWithGrid` 行：`#### boolean CollidesWithGrid ( )`。
//
// **PC 绑定本体**（`python3 tools/pc_exe_binding.py CollidesWithGrid --disasm` ⇒ `0x641420`）：
//
//     00641420  8a 81 88 01 00 00   mov al, byte ptr [ecx + 0x188]
//     00641426  c3                  ret
//
//   ⇒ PC 上它**就是"读 `Entity + 0x188` 这一个字节"** ⇒ 判法四档 ①档（字段读）⇒ 数据行。
//
// **Switch 侧：那一格是 `Entity + 0x1EC`**（`python3 tools/nro_disasm.py 0x5a27c 0x90` + 全镜像扫字节访问）：
//
//   * **初始化**：`Entity::Init` 里 `strb wzr, [x19, #0x1ec]`（`0x598EC`）⇒ 出生时清零；
//   * ★★ **语义锚点（函数名即语义）**：`Entity::CollideWithGrid @ 0x5A27C` ——
//       开头 `tbnz w1,#0x0` 跳过、否则 `strb wzr, [x22, #0x1ec]`（**整趟碰撞开始前先清 0**），
//       随后在 7 个"确实碰上了"的分支里各写一次 1（`0x5A398` / `0x5A3F8` / `0x5A474` /
//       `0x5A488` / `0x5A6F8` / `0x5AB9C`）；`Entity::PlayerCollideWithGrid` 是**逐字同形**的一套
//       （`0x5B7F0` 清零 + `0x5B8D8`/`0x5B938`/`0x5B94C`/`0x5BDBC` 置位）。
//       ⇒ "本帧有没有撞到网格" = 这个字节。
//   * **读者**：`Entity::Update`（`0x600D8` / `0x60174`）与一批 `Entity_*::Update` /
//       `Entity_Familiar::ai_*`（撞墙后各自动作）—— 与 PC 的 `boolean CollidesWithGrid` 用法一一对应。
//
// ★ 一条**负结果**（顺手记下、省得后人再找）：`Entity:IsInvincible()` 的 PC 本体也是纯读一格
//   （`0x59FD50` = `mov al,[ecx+0x308]`），但 **Switch 侧找不到锚**：全符号表没有同名方法、
//   PC 的 `0x308` 不能平移（PC/Switch 的 `Entity` 布局**不同** —— 同一格摩擦 PC 在 `0x2C4`、
//   Switch 在 `0x340`）、PC 侧除绑定本体外**只有一个**读者（`0x6D3F52`）且那是个通用守卫
//   （`cmp byte [ecx+0x308],0` + `cmp byte [ecx+0x16b],0` 连着跳），不足以反推出 Switch 那一格。
inline constexpr uintptr_t kEntityCollidesWithGridOffset = 0x1EC;

// ============================================================================
// 批次 337（2026-10-04 凌晨）：`EntityPlayer:FireTear(...)` —— 一条"引擎真身在、但要手写转发"的
// ============================================================================
//
// **PC 契约** `tools/pc_contract_docs/EntityPlayer.md:720`，逐字：
//
//     EntityTear FireTear ( Vector Position, Vector Velocity, boolean CanBeEye = true,
//                           boolean NoTractorBeam = false, boolean CanTriggerStreakEnd = true,
//                           Entity Source = nil, float DamageMultiplier = 1 )
//     - `CanBeEye`: If the player has the Evil Eye item, passing true allows the tear to have a chance of being an eye.
//     - `NoTractorBeam`: If the player has the Tractor Beam item, passing true means that the tear will be exempt from the beam.
//     - `CanTriggerStreakEnd`: If the player has the Dead Eye item, passing false means that the tear will be exempt from ending the streak.
//
// ★★ **两个缺省值是 `true`**（`CanBeEye` / `CanTriggerStreakEnd`）⇒ 不能走"省略即 0"那条路。
//
// **Switch 真身**：`_ZN15IsaacRepentance13Entity_Player8FireTearERKN4KAGE4Math7Vector2ES3_jPNS_6EntityEf`
//   @ **`0x2A991C`**，入口首 4 字节 = **`0xD10383FF`**（= `sub sp, sp, #0xe0`）。
//
// **它到底收什么（两侧互证，★ 这是本条的取证重点）** —— 契约 7 个形参、引擎只有 5 个：
//   * **三个布尔被引擎打包成一个 `u32` 位掩码**（mangled 里的 `j`）；
//   * **`Velocity` 是"按值"传的**（不是 `const&`）：PC 调用点 `0x77F5BE` 连推**两个 dword**（8 字节）
//     给它；Switch 入口头一条就是 `stp s0, s1, [x29, #-0x8]`（把 8 字节 HFA 落栈）。
//   ⇒ **`FireTear(Vector2 const& Position /*x1*/, Vector2 Velocity /*HFA s0,s1*/,
//                u32 flags /*w2*/, Entity* Source /*x3*/, float DamageMultiplier /*s2*/)`**
//   （Switch 入口逐条对上：`mov x20, x1` / `stp s0,s1` / `mov w21, w2` / `mov x22, x3`，
//     且 `x22` 后面有 `cbz x22` ⇒ 它可空 = `Source` ✓）。
//
// ★★★ **位掩码的位序**（三个布尔各占一位）：
//   * **bit 1 = `NoTractorBeam`（已证）**：`0x2A9A28 tbz w21, #0x1` → 不设就跳；
//     设了则 `bic` 清掉 `Entity_Tear::TEAR_TRACTOR_BEAM` 那个标志（同段 `ldr x8,[x8,#0xa40]`
//     的符号就是 `_ZN15IsaacRepentance11Entity_Tear17TEAR_TRACTOR_BEAME`）
//     ⇒ **"设了就不吃牵引光束"** 与契约原文逐字对应；
//   * bit 0 / bit 2：`0x2A9D10 tbnz w21, #0x0`（跳过一段"射速/冷却"计算）与
//     `0x2A9BBC tbz w21, #0x2`（设了则清新眼泪上的一个字节）；**按契约的形参顺序**取
//     bit0 = `CanBeEye`、bit2 = `CanTriggerStreakEnd`（与 bit1 的位置一致 ⇒ 同一位序）。
//     ★ 旁证：引擎**自己**的调用点传 `flags = 3`（`0x77F5AD`，bit0|bit1）与 `0x47`（`0x795ADA`，
//     低三位全设 + 一个只有内圈才用的 bit6）⇒ **低三位就是那三个布尔**。
//   * ★ **语料 4 处全都是 `false, false, false`** ⇒ `flags = 0`，与位序无关（位序只影响
//     "传 true 时对不对"）⇒ 已挂真机项（见作业单第九节）。
//
// **为什么手写而不是数据行**：数据行那条路缺两种表达能力 ——
//   ① **按值的 HFA 形参**（现有 `EngineArgKind::Vector2Ref` 只表达 `const&` ⇒ 传指针）；
//   ② **两个缺省为 `true` 的布尔**（`optionalArgumentCount` 写死"省略即 0"，
//      唯一破例是 326 的 `FloatDefaultOne`）。
//   按 326 的校准每新开一种 ≈ `.text +0x480` ⇒ 两种 ≈ `+0x900`；手写 ≈ 300 字节
//   （与 328/332/334 同一笔账）⇒ **手写更省**，而且能逐条处理后两个可选形参。
inline constexpr uintptr_t kEntityPlayerFireTearOffset = 0x2A991C;
inline constexpr std::uint32_t kEntityPlayerFireTearEntryWord = 0xD10383FFu;  //: `sub sp,sp,#0xe0`

// ============================================================================
// 批次 339（2026-10-04）：`EntityFamiliar:FireProjectile(Vector Dir)` —— 一条"引擎真身在"的
// ============================================================================
//
// **PC 契约** `tools/pc_contract_docs/EntityFamiliar.md:57/59`，逐字：
//
//     EntityTear FireProjectile ( Vector Dir )
//     Shoots a projectile from the center of the familiar in the direction you defined.
//     If used on a familiar that shoots multiple projectiles (example: harlequin baby), this function
//     will only return the left most projectile based on the direction. If used on familiars with
//     special tears (example: Lil Brimstone,...), this will just shoot a regular tear.
//     **This function will not play the shoot animation of the familiar.**
//
// **Switch 真身**：`_ZN15IsaacRepentance15Entity_Familiar16fire_projectilesERKN4KAGE4Math7Vector2Eb`
//   @ **`0xB06FC`**，入口首 4 字节 = **`0xD10643FF`**（= `sub sp, sp, #0x190`）。
//   ★ 同族另有一个重载 `fire_projectiles(eDirection, bool)` @ `0xB06B8`（吃的是方向枚举）
//     —— **契约要的是 `Vector Dir` 那一个**，所以取 `0xB06FC`。
//
// **ABI 逐条核实**（`python3 tools/nro_disasm.py 0xb06fc 0x40`）：
//   `mov x8, x1` → `str x8, [sp, #0x10]` ⇒ **`x1` 是 `Vector2 const&`（指针）**；
//   `mov x19, x0` = `this`；bool 在 `w2`（mangled 末位的 `b`）。
//   ⇒ 我们这一侧要传：`x0` = 班尸指针、**`x1` = 我们自己栈上那个 Vector2 槽的地址**、
//     `w2` = 那个隐藏的 bool。
//
// ★★ **那第二个 `bool` 传什么**（契约里没有它，是引擎内部参数）：
//   ① **文档明文**："This function will not play the shoot animation of the familiar."
//      ⇒ Lua 那条路**不播动画**；
//   ② **引擎自己的调用点有明传 `0` 的**：`0x42E3B4` 处 `push 0x0` → `push &Vector2` → `call 0x618860`
//      （PC 侧 `Entity_Familiar::fire_projectiles` 的本体，`arg1` = `[ebp+8]`、`arg2` = `[ebp+0xc]`）
//      ⇒ 那一路就是 `bool = false`。
//   ⇒ 我们传 **`false`**。★ 与 335 的 `DischargeActiveItem` 一样：**这是"按契约与调用点推断"、
//     不是被证明的等式** ⇒ 已挂真机项（作业单第九节）。
inline constexpr uintptr_t kEntityFamiliarFireProjectileOffset = 0xB06FC;
inline constexpr std::uint32_t kEntityFamiliarFireProjectileEntryWord = 0xD10643FFu;

// ============================================================================
// 批次 340（2026-10-04）：`Game:Spawn(...)` 与 `Isaac.Spawn(...)` —— ★ **第一个"参数上栈"的例子**
// ============================================================================
//
// **PC 契约**（两条，逐字）：
//   * `tools/pc_contract_docs/Game.md:520`：
//     `Entity Spawn ( EntityType Type, int Variant, Vector Position, Vector Velocity, Entity Spawner,
//      int SubType, int Seed )`
//   * `tools/pc_contract_docs/Isaac.md:621`：
//     `Entity Spawn ( EntityType entityType, int entityVariant, int entitySubtype, Vector position,
//      Vector velocity, Entity Spawner )`
//   ★ 两条散文都写明：`Isaac.Spawn` 用**随机种子**、`Game():Spawn` 用**指定种子**；
//     并警告 **`Isaac.Spawn` 有概率产生种子 0 而崩游戏** ⇒ 我们要给它一个**非 0** 随机种子。
//
// **Switch 真身**：`_ZN15IsaacRepentance4Game7SpawnExENS_11eEntityTypeEjRKN4KAGE4Math7Vector2ES6_PNS_6EntityEjjj`
//   @ **`0x3540D0`**，入口首 4 字节 = **`0xD10283FF`**。
//   = `SpawnEx(eEntityType, u32, Vector2 const&, Vector2 const&, Entity*, u32, u32, u32)` ⇒ **8 个形参**。
//
// **ABI 逐条核实**（`python3 tools/nro_disasm.py 0x3540d0 0x90`）：
//   `w27 = w1`（type）、`w28 = w2`（variant）、`x20 = x3`（`&Position`）、`x24 = x5`（Spawner）、
//   `w26 = w6`、`w25 = w7`（后两个 u32）；
//   ★★★ 而**第 8 个形参在栈上**：入口第一条就是 `ldr w8, [x29, #0x60]`，随后 `and w2, w8, #0x1`
//   ⇒ 它被当**布尔**用（喂给 `EntityFactory::Create(type, bool)` 的第 2 个参数）。
//   ⇒ ★★★ **本项目第一个"第 8 个参数走栈"的引擎调用** —— 通用跳板只填 `x0..x7`/`d0..d7`、
//     **填不了栈参数** ⇒ 这条**不能用数据行**（栈上那格会是垃圾），**必须手写**
//     （`AsFunction<Fn>` 由编译器按编译期签名把第 9 个参数量放到栈上 ✓）。
//   ⇒ 我们传 `false`（0）—— 契约里没有这一格，它是引擎内部参数。
//
// **映射**：`SpawnEx` 的前 7 格与 `Game:Spawn` 的 7 个形参**逐格同序**：
//   `(type, variant, &pos, &vel, spawner, subType, seed)` ✓
//   ⇒ `Game:Spawn` 直接转发；`Isaac.Spawn` 要把 `subtype` 从第 3 位挪到第 6 位、并现取随机种子。
//   语料也印证：`Game():Spawn(type, variant, pos, vel, spawner, subtype, seed)`（7 个实参，如
//   `BOIStageAPI15/.../taintedkeepercoins.lua:63`、`TBOI_Better-Voiding/.../main.lua:154`）。
inline constexpr uintptr_t kGameSpawnExOffset = 0x3540D0;
inline constexpr std::uint32_t kGameSpawnExEntryWord = 0xD10283FFu;  //: `sub sp,sp,#0xa0`

// ============================================================================
// 批次 341（2026-10-04）：四条 API —— `Entity:IsInvincible` / `EntityLaser:SetMaxDistance`
//                        / `EntityPlayer:TryRemoveTrinketCostume` / `EntityFamiliar:FollowPosition`
// ============================================================================
//
// 本批四条的证据都来自只读取证（`docs/取证-C组-三条字段-20261004.md` 与
// `docs/取证-D组-杂项八条-20261004.md`），下面逐条摘录**决定性的那几条指令**。

// ---- 1) `Entity:IsInvincible()` → `Entity + 0x384`（u8）------------------------------
//
// **PC**：绑定 VA `0x59FD50` = `mov al, byte ptr [ecx+0x308]; ret` ⇒ 纯读 PC `Entity+0x308`。
//
// **PC→Switch 的偏移对位**（本区 PC `0x2C4`…`0x308` **增量恒为 `+0x7C`**）：
//   `Friction` PC `0x2C4` ↔ Switch `0x340`、`HitPoints` `0x2D8` ↔ `0x354`、
//   `MaxHitPoints` `0x2DC` ↔ `0x358`（三者都是本项目**已 confirmed** 的布局行）
//   ⇒ PC `0x308` 投到 Switch 只能是 **`0x384`**（`0x354→0x384` 与 `0x2D8→0x308` 的跨度同为 `0x30`）。
//
// **Switch 侧三条独立证据**：
//   * 具名写入方 `Entity_NPC_VisageMask::SetNoDamage(bool)` @ `0x25D640`：
//     `0x25D644 strb w8, [x0, #0x384]` —— 把 bool 形参直接写进本格（函数名即语义"设置免伤"）。
//   * 出生清零 `Entity::Init` @ `0x5999C`：`strb w31, [x19, #0x384]`（`wzr`）⇒ 新实体默认不免伤。
//   * 受击闸门 `Entity::TakeDamage` @ `0x5DD80`：`ldrb w9,[x19,#0x384]; cbnz w9, skip`
//     —— 紧接其后判 `+0x1C3`（本项目已 confirmed 的 `IsDead`），两边的**守卫顺序逐字同形**；
//     第二读者 `Entity::IsVulnerableEnemy` @ `0x5C648` 同样 `ldrb w9,[x0,#0x384]; cbnz` 直接返回 false。
//   ★ 与仓库既有记载互印：`runtime_constants.hpp` 批次 286 段（`Entity:IsVulnerableEnemy` 专项）
//     早已把 PC `+0x308` ↔ Switch `+0x384` 对上过。
inline constexpr uintptr_t kEntityIsInvincibleOffset = 0x384;

// ---- 2) `EntityLaser:SetMaxDistance(float)` → `Entity_Laser + 0x4F8`（float）---------
//
// **PC**：绑定 VA `0x4275B0` = `movss xmm0,[ebp+8]; movss [ecx+0x420],xmm0; ret 4`
// ⇒ 把实参**直接写进** PC `Entity_Laser+0x420`（★ 数值不平移：Switch 在 `0x4F8`）。
//
// **Switch 侧三条独立证据**（契约散文 `EntityLaser.md:126`："Used to trim brimstone for
//   Azazel (0 - off)"）：
//   * 具名消费者① `Entity_Laser::update_laser` @ `0xF9CB8`：
//     `ldr s0,[x19,#0x4f8]; fcmp s0,#0.0; b.le`（≤0 不裁剪）→ 与 `Vector2::DistanceSquared` 比 →
//     超过就用 `Vector2::Resized` 把端点夹到"起点 + 方向 × 本格"。
//   * 具名消费者② `Entity_Laser::init_laser` @ `0xF8718`：同款 `ldr s0,[x19,#0x4f8]` + `fcmp #0.0` 裁剪。
//   * 具名写入方（发激光那条路）@ `0x4B8718`：`bl Vector2::Length` 之后
//     `0x4B8724 str s0, [x28, #0x4f8]` —— 把"两控制点距离"写成最大射程。
inline constexpr uintptr_t kEntityLaserMaxDistanceOffset = 0x4F8;

// ---- 3) `EntityPlayer:TryRemoveTrinketCostume(TrinketType)` --------------------------
//
// **PC 契约** `tools/pc_contract_docs/EntityPlayer.md:1838`：`void TryRemoveTrinketCostume ( TrinketType Trinket )`。
//
// **Switch 真身 = 同族 `TryRemoveCostume` 的 trinket 重载**
//   `_ZN15IsaacRepentance13Entity_Player16TryRemoveCostumeENS_12eTrinketTypeE` @ **`0x2A25B0`**，
//   入口首 4 字节 = `0xA9BD7BFD`（= `stp x29, x30, [sp, #-0x30]!`）。符号表里**没有**
//   `TryRemoveTrinketCostume`（引擎侧按类型分派），但 `TryRemoveCostume` 的三个重载里
//   `(eTrinketType)` 那条与契约逐参对应（另两条是 `(ItemConfig::eNullItemID)` 与 `(eCollectibleType,bool)`）。
//   函数体：取条目 `ItemConfig::GetTrinket(id)` → 看 `[item+0xB6]` 标志 / `TemporaryEffects::HasEffect`
//   → 尾调 `Entity_Player::RemoveCostume(ItemConfig::Item const*)` ⇒ `void(this, i32)` 形状。
//   ★ 先例：`EntityPlayer:TryRemoveNullCostume(int)` 的底座就是同族 `(eNullItemID)` 那条
//     （`0x2F2170`，走 `VoidNullId1` 数据行）⇒ 本条照同一形态，但**不需要** null-id 校验（饰品编号
//     走 `GetTrinket`，与 `TryRemoveNullCostume` 的 `GetNullItem` 不是同一个容器）。
//   ★ 保留项：PC 的 Lua 胶水多调了一层容器方法 ⇒ "可观察效果是否逐字一致"已挂真机项。
inline constexpr uintptr_t kEntityPlayerTryRemoveTrinketCostumeOffset = 0x2A25B0;
inline constexpr std::uint32_t kEntityPlayerTryRemoveTrinketCostumeEntryWord = 0xA9BD7BFDu;

// ---- 4) `EntityFamiliar:FollowPosition(Vector2 const&)` ------------------------------
//
// **PC 契约** `tools/pc_contract_docs/EntityFamiliar.md:70`：`void FollowPosition ( Vector Pos )`。
//
// **Switch 真身** `_ZN15IsaacRepentance15Entity_Familiar15follow_positionERKN4KAGE4Math7Vector2E`
//   @ **`0xAFCC0`**，入口首 4 字节 = **`0xD100C3FF`**（= `sub sp, sp, #0x30`）。
//
// **★★ 本条推翻了批次 331 的负结果**：331 记的是"符号在、但函数体从不读实参 ⇒ 不能接"。
//   复核（`docs/取证-D组-杂项八条-20261004.md` §6）证明那次是**线性读**漏了分支：
//   函数有**两条路**，`0xAFCC0` 的守卫（`[this+0xF50]` 的三重判定）**成立**时走 `+0x34`、
//   把 `this+0xDA0` 拷进 `this+0x310`（那一支确实不用实参、早退）；
//   守卫**不成立**时三条 `b.ne/b` 直接跳到 **`+0x60`（`0xAFD20`，同一栈帧）**，那里
//   `0xAFD24 mov x0, x1` 用的就是**原始实参 `Vector2 const&`**：算 `实参 - this[0x310]`、
//   `× 0.1f`、写进 `this[0x334]`，并把 `this[0x340]`（工作摩擦）乘 `0.8f`。
//   ⇒ 与 PC 的 `FollowPosition`（绑定 VA `0x5F4EB0`）**两条路逐条同形**（PC 位置 `+0x294`/速度 `+0x2B8`/
//     摩擦 `+0x2C4`，Switch `+0x310`/`+0x334`/`+0x340`；`×0.1` 常数 PC `0xb6a2cc` / Switch `0x3DCCCCCD`）。
//   ⇒ **可接**。ABI：`this=x0`、`x1 = Vector2 const&`（**指针**）、返回 `void`；
//     形状用本批新开的 `VoidVector2Ref`（`EngineArgKind::Vector2Ref` 本来就存在 ⇒ 纯数据）。
inline constexpr uintptr_t kEntityFamiliarFollowPositionOffset = 0xAFCC0;
inline constexpr std::uint32_t kEntityFamiliarFollowPositionEntryWord = 0xD100C3FFu;

// ============================================================================
// 批次 342（2026-10-04）：`Game:Darken` / `EntityPlayer:StopExtraAnimation`
//                        / `GridEntity:GetSaveState`
// ============================================================================
//
// 前两条的落地规格来自 `docs/取证-F组-Explode与明暗与动画落地规格-20261004b.md`；
// 第三条来自 `docs/取证-G组-SaveState与列表落地规格-20261004b.md`。下面的指令都**自己反汇编核过**。

// ---- 1) `Game:Darken(float Darkness, int Timeout)` -----------------------------------
//
// **PC 契约** `tools/pc_contract_docs/Game.md:129`：`void Darken ( float Darkness, int Timeout )`，
// 正文「Darkens the room. This is the function that is called internally during The Lamb fight
// or when Dice Rooms are activated.」。PC 绑定 VA = **`0x432F60`**（`__thiscall`，两个标量形参）。
//
// **Switch 侧那两格**（`Game` 上的三个连续成员，本 API 只写其中两格）：
//   * `Game + 0x24F9B8`（**int**）= `Timeout`：`Game::Update` 每帧 **递减**它
//     （`_ZN15IsaacRepentance4Game6UpdateEv` 内的 `0x352168`：`ldr w8,[x24,#0x20]; subs w8,w8,#0x1`，
//      同函数紧随 `ldr s0,[x24,#0x24]` 读那个 float；★ 取证报告 F 组把这里记成 `ai_dark_one`，
//      实际所属符号是 `Game::Update @ 0x351884`（`ai_dark_one` 在 `0x1471F0`，是另一条路））。
//   * `Game + 0x24F9BC`（float）= 插值量（**本 API 不写**，故不引常量；两者之间**夹着它** ⇒
//     两格**不相邻**，绝不能用一条 `u64`/`u32` 掩盖）。
//   * `Game + 0x24F9C0`（**float**）= `TargetDarkness`：渲染侧读它
//     （`Room::GetLightingAlpha @ 0x477504` 那一路：`Modifier × TargetDarkness`）。
//
// **写入点（默认值锚点）** —— `Entity_NPC::ai_lamb`（兰姆战那一套）里的
// `_ZN15IsaacRepentance10Entity_NPC7ai_lambEv` 段 `0x169BC4`..`0x169BE0`
// （`python3 tools/nro_disasm.py 0x169bbc 0x30`；★ 落地时按符号表复核过：这一段所属符号是
//  `Entity_NPC::ai_lamb @ 0x16827C`，**不是** `Entity::Kill`）：
//   `0x169BC8 mov w9,#0xf9b8` + `0x169BCC movk w9,#0x24,lsl#16` ⇒ `w9 = 0x24F9B8`；
//   `0x169BD4 add x8,x8,x9` ⇒ `x8 = Game + 0x24F9B8`；
//   `0x169BDC str w10,[x8,#0x8]`（`w10 = 0x3F800000` = **`1.0f`**）⇒ `Game + 0x24F9C0 = 1.0f`；
//   `0x169BE0 str w9,[x8]`（`w9 = 0x258` = **600**）⇒ `Game + 0x24F9B8 = 600`。
//   ⇒ 「暗度目标 = 1.0f、持续 600 帧」这条默认值把两格的**语义与顺序**同时钉住。
inline constexpr uintptr_t kGameTargetDarknessOffset = 0x24F9C0;   //: float
inline constexpr uintptr_t kGameDarknessTimeoutOffset = 0x24F9B8;  //: int

// ---- 2) `EntityPlayer:StopExtraAnimation()` ------------------------------------------
//
// **PC 契约** `tools/pc_contract_docs/EntityPlayer.md:1760`：`void StopExtraAnimation ( )`。
// PC 绑定 VA = **`0x57B1D0`**；PC 那两格是 `Entity_Player + 0x12E8`（"正在播放"）与
// `+0x12EA`（"已结束"）—— **两字节、相隔 2**（中间 `0x12E9` PC 明确跳过）。
//
// **Switch 侧那两格**（逐字同构：`+0x1710` ↔ PC `0x12E8`、`+0x1712` ↔ PC `0x12EA`）：
//   * `Entity_Player + 0x1710`（**byte**）= "正在播放"；
//   * `Entity_Player + 0x1712`（**byte**）= "已结束"。
//
// **证据①（消费者，函数名即语义）** `Entity_Player::IsExtraAnimationFinished` @ `0x2B78C4`：
//   `mov w8,#0x1710` → `add x8,x0,x8` → `ldrb w9,[x8]` + `cbz`（**正在播放就返回 false**）
//   → `ldrb w8,[x8,#0x2]` + `cmp w8,#0` + `cset w0,eq` ⇒ 「没在播 且 已结束标志为 0」
//   ⇒ 两格分别是"正在播放 / 已结束"，且**相隔 2**。
//
// **证据②（写入者）** `Entity_Player::PlayExtraAnimation` @ `0x2B0914` 起：
//   `mov w8,#0x1710` + `add x22,x0,x8`；`0x2B0924 strb wzr,[x22,#0x2]`（已结束=0）；
//   `0x2B0958 strb w20(1),[x22]`（正在播放=1）+ `0x2B095C strb wzr,[x22,#0x2]`（已结束=0）。
//   ⇒ 「开始播放 ⇒ 正在播放=1、已结束=0」这一对与 PC 同形。
//
// **证据③** `tools/nro_find_offset_access.py 0x1710` 命中 40 处，全在 `Entity_Player` 的方法里，
//   写法一律 `add x8,x0/x19,#0x1710` 之后 `ldrb/strb [x8]` 与 `ldrb/strb [x8,#2]`
//   （`TakeDamage` / `try_end_astral_projection` / `IsFullSpriteRendering` / `update_effects` /
//   `AnimatePickup` …）。
//
// ★★ **必须逐字节写两格**：不能往 `+0x1710` 写一个 `u16 = 0` —— 那会**连带清掉 `+0x1711`**，
//   而 PC 明确跳过 `0x12E9`（`+0x1711` 的用途在本镜像里**未取证**）⇒ 与 PC 不一致。
inline constexpr uintptr_t kEntityPlayerExtraAnimationPlayingOffset = 0x1710;   //: byte
inline constexpr uintptr_t kEntityPlayerExtraAnimationFinishedOffset = 0x1712;  //: byte

// ---- 3) `GridEntity:GetSaveState()` ---------------------------------------------------
//
// **PC 契约** `tools/pc_contract_docs/GridEntity.md:46`：`GridEntityDesc GetSaveState ( )`；
// 正文（`:49`）逐字说明**它与 `Desc` 属性返回同一个 `GridEntityDesc` 对象**，
// 并建议用 `GetSaveState()` 而不是 `Desc`。
// PC 绑定 VA = **`0x71FF60`** = `lea eax,[ecx+0x4]; ret` ⇒ 返回 `&this->desc`（**指针 getter**，
// 不是把结构体按值返回）。Switch 侧 desc 内嵌在 `GridEntity + 0x08`
// （`GridEntity::Init(const Desc&)` 把 `Desc[0x00..0x1F]` 拷到对象 `+0x08..+0x27`）。
//
// ⇒ 本 API **不需要**任何新偏移、也不调引擎：它与 `GridEntity:Desc` 走**同一份**表构造
// （`PushGridEntityDescTable`，见 `remaining_api.cpp`）。这里把三格已在
// `kGridEntityTypeOffset` / `kGridEntityVariantOffset` / `kGridEntityVarDataOffset` 取证过的
// 偏移再点名一次，作为这条 API 的落点说明（**不重复定义常量**）。

// ============================================================================
// 批次 343（2026-10-04）：`Entity:GetColor` / `ItemConfig:GetCollectibles|GetTrinkets`
// ============================================================================
//
// `GetColor` 的偏移依据 = `docs/取证-K组-GetColor落地规格-20261004d.md`
// （它的上游是 `docs/取证-I组-GetColor离线定案尝试-20261004c.md` 的**离线定案**）。

// ---- 1) `Entity:GetColor()` → `Entity + 0x138`（值类型 `Color`，44 字节 `ColorMod`）--------
//
// **PC**：绑定 VA `0x4F3DE0` = `lea eax,[ecx+0xE4]; ret` ⇒ 返回**当前/生效色**那个 `ColorMod`
// （PC 在 `Entity + 0xE4`）。契约 `tools/pc_contract_docs/Entity.md:338` 逐字
// `#### const [Color](Color.md) GetColor ( )` —— **按值返回**，所以胶水层给 Lua 的是一个值拷贝。
//
// **Switch 侧那一格 = `Entity + 0x138`**。★★★ 本格**不靠"看起来像"**，而是靠
// **PC/Switch 的 `Entity::SetColor` 逐字同构**定案（I 组）：
//   * PC `Entity::SetColor @ 0x68A380` 与 Switch `Entity::SetColor @ 0x63B84` 是同一个函数的同一套分支：
//     `Duration > 0`（临时色）支写 **PC `+0xE4` ↔ Switch `+0x138`**；
//     `Duration <= 0`（永久色）支写 **PC `+0x1B0` ↔ Switch `+0x220`**；
//     连临时色那个 `vector` 的位置与步长（PC `+0x1A4` ↔ Switch `+0x208`，步长 `0x3C`）都一一对应。
//   * 交叉印证三条：`Entity::reset_color`（PC `0x723EF0` 写 `+0xE4` ↔ Switch `0x5C754` 写 `+0x138`）；
//     `Entity::Update` 每帧用 `ColorMod::Lerp` 重算这一格；`Entity_Player::Render @ 0x2DAD90` 读它去画。
//   * ★ PC 侧三格的间距也能对上：`+0xE4`（当前色）/`+0x1B0`（默认色）/`+0x1DC`（SplatColor）
//     两两相距 `0x2C`（一个 `ColorMod`）⇒ Switch 的 `+0x138`/`+0x220`/`+0x24C` 也是两两相距 `0x2C`。
//
// ★★ **本格极易与 `+0x220` 取错**（那是 Lua 的 `Entity.Color` **属性**那一格），
//   也与 `+0x24C`（`SplatColor`）不同 ⇒ 用例把三格摆成**互不相同**的值来钉住。
// ★ 语料 4 处（`Trinity/main.lua:717`、`Enhanced-Boss-Bars/main.lua:279`、
//   `IsaacOnTwitchReloaded/scripts/events.lua:2736` 与 `mechanics.lua:791`）都把它**按值**用
//   （取分量或直接喂回 `SetColor`）。
inline constexpr uintptr_t kEntityGetColorOffset = 0x138;

// ============================================================================
// 批次 344（2026-10-04）：`EntityPlayer:AnimateCollectible` / `PathFinder:HasPathToPos`
// ============================================================================
//
// 规格来源：`docs/取证-L组-两条手写处理器的可执行规格-20261004d.md` §B（AnimateCollectible，
// 独立复核见 `docs/取证-N组-独立复核Explode与AnimateCollectible-20261004e.md`）与
// `docs/取证-J组-两条缺前置的补齐方案-20261004c.md` §3.1（HasPathToPos）。

// ---- 1) `EntityPlayer:AnimateCollectible(CollectibleType, string, string)` ------------------
//
// **PC**：契约 `tools/pc_contract_docs/EntityPlayer.md:435` 逐字
//   `#### void AnimateCollectible ( CollectibleType Collectible, string AnimName = "Pickup",
//    string SpriteAnimName = "PlayerPickupSparkle" )`
// 绑定本体 VA `0x770300`（`python3 tools/pc_exe_binding.py AnimateCollectible --disasm`）——
// 它只是一层胶水：从 `[ebp+0xc]` / `[ebp+0x10]` 取两个**已解析好的** `char const*` 转给引擎。
//
// **Switch 真身 = `Entity_Player::AnimatePickup(eCollectibleType, char const*, char const*)
//  @ 0x2DD150`**（入口首 4 字节 `0xD10743FF` = `sub sp,sp,#0x1d0`），mangled:
//   `_ZN15IsaacRepentance13Entity_Player13AnimatePickupENS_16eCollectibleTypeEPKcS3_`
// ★★ **引擎里没有叫 `AnimateCollectible` 的符号** —— 这一条是**改名**：契约名与引擎名不同，
//   而同族有 **5 条** `AnimatePickup` 重载（`python3 -` 那条列出符号的脚本可复现）⇒
//   **选错不报错、只会播错动画**，所以要靠"哪条重载的第 1 格是 `eCollectibleType`"定案。
//   ★ L 组与 N 组两轮独立核对过：只有 `(eCollectibleType, …)` 那条重载的函数体把 `w1`
//     喂给 `ItemConfig::GetCollectible` ⇒ 就是它。
// ★★ **缺省字符串必须传字面串，不能传 `nullptr`**（L 组从引擎侧反推、N 组复核）：
//   两个指针随后分别喂 `ANM2::Play(char const*, bool) @ private:kSpritePlayOffset`，那里对名字做 `strcmp`
//   且**没有 null 检查**（`0xA224 mov x1, x20` → `bl strcmp`）⇒ 传 null 会读 NULL 段、当场崩。
//   ⇒ 缺省（或缺 `nil`）时必须传 `"Pickup"` / `"PlayerPickupSparkle"`（大小写敏感、逐字一致）。
//   ★ 负数 `CollectibleType` **不特殊处理**：引擎入口 `0x2DD1D0 tbnz w23,#0x1f` 就是 PC 那条
//     "程序化道具"分支的对应物，我们不加工（加工就与 PC 不一致）。
//
// 语料 2 处：`RepentancePlus/main.lua:1054`（1 参，走缺省）与
// `BOIStageAPI15/scripts/stageapi/core/callbacks.lua:144`（3 参）。
inline constexpr uintptr_t kEntityPlayerAnimateCollectibleOffset = 0x2DD150;
inline constexpr std::uint32_t kEntityPlayerAnimateCollectibleEntryWord = 0xD10743FFu;

// ---- 2) `PathFinder:HasPathToPos(Vector Pos, boolean IgnorePoop)` ---------------------------
//
// **PC**：契约 `analysis/isaacdocs-snapshot/docs/PathFinder.md:61-64`（本批已逐字节 vendor 进
//   `tools/pc_contract_docs/PathFinder.md`）逐字
//   `#### boolean HasPathToPos ( Vector Pos, boolean IgnorePoop )`，正文
//   "Used for safe check if any NPC is behind rocks/pits, doesn't disturb class members."
// 取用链（`tools/pc_contract_docs/EntityNPC.md:208-210`）：`EntityNPC` 上的 **`Pathfinder` 属性**
//   交出 `PathFinder` 对象，再调它的实例方法。
//
// **Switch 真身 = `NPCAI_Pathfinder::HasPathToPos(Vector2 const&, bool) const @ 0x42F6CC`**
// （入口首 4 字节 `0xA9BA7BFD` = `stp x29,x30,[sp,#-0x60]!`），mangled:
//   `_ZNK15IsaacRepentance16NPCAI_Pathfinder12HasPathToPosERKN4KAGE4Math7Vector2Eb`
// ★ 同族另有一条 **3 参**重载 `_ZN…HasPathToPosERK…Vector2ES5_b @ 0x42FAFC`（起点/终点内部版）
//   ⇒ 与契约逐参对应的是 **2 参**那条（`0x42F6CC`），**不要抄错重载**。
//
// **★ 接收者链：`NPCAI_Pathfinder` 内嵌在 `Entity_NPC + 0x408`**（J 组决定性证据 + 3 处旁证）：
//   * 构造点 `Entity_NPC::Entity_NPC() @ 0x105754`：
//     `0x105774 add x0, x19, #0x408` → `0x105780 bl NPCAI_Pathfinder::NPCAI_Pathfinder(Entity*)`
//     （`x1 = Entity_NPC*`，arity 与语义都对得上）；
//   * 旁证三处，都是同一偏移取址再调 `NPCAI_Pathfinder::` 的成员函数：
//     `Entity_NPC::ai_poky @ 0x1C8348`（`add x20,x19,#0x408` → `UpdateGridIndex`）、
//     `Entity_NPC::ai_stonehead @ 0x1C77C0`（同）、
//     `Entity_NPC::Init @ 0x106364`（`add x0,x19,#0x408` → `Reset`）。
//   ⇒ 共 4 条独立证据指向同一个数。★ 引擎里**没有**具名访问器（不存在 `Entity_NPC::Pathfinder()`）
//     ⇒ 真机若发现属性答出的对象不对，第一嫌疑就是这一格。
//   ★★ `Entity_Familiar` 也内嵌一份 `NPCAI_Pathfinder`，但偏移**不同**（`+0x5F8`），而且 PC 的
//     `EntityFamiliar` 页里**没有** `Pathfinder` 属性 ⇒ **本批只挂在 `EntityNPC` 上**
//     （多给一个 PC 没有的属性 = 与 PC 不一致）。
inline constexpr uintptr_t kEntityNpcPathfinderOffset = 0x408;
inline constexpr uintptr_t kPathFinderHasPathToPosOffset = 0x42F6CC;
inline constexpr std::uint32_t kPathFinderHasPathToPosEntryWord = 0xA9BA7BFDu;

// ============================================================================
// 批次 345（2026-10-04）：`Isaac:Explode(Vector pos, Entity source, float damage)`
// ============================================================================
//
// 规格来源：`docs/取证-L组-两条手写处理器的可执行规格-20261004d.md` **§A**（完整可执行规格），
// 上游 = F 组（`docs/取证-F组-Explode与明暗与动画落地规格-20261004b.md`）与
// H 组（`docs/取证-H组-时间缩放与爆炸实参-20261004c.md` 独立复核末尾 4 格，★ 更正 `p9` 的指令地址
// 应为 `0x80BB83`），落地前的独立复核 = N 组（`docs/取证-N组-独立复核Explode与AnimateCollectible-20261004e.md`）。

// ---- `Isaac:Explode` → `Game::BombExplosionEffects`（9 形参，第 9 格走栈）-------------------
//
// **PC**：契约 `tools/pc_contract_docs/Isaac.md:112` 逐字
//   `#### void Explode ( [Vector](Vector.md) pos, [Entity](Entity.md) source, float damage )`
//   + 正文 "Spawn an explosion on a specified location."
// 绑定本体 VA `0x80BB60`：把 **9 个形参**从右到左压栈后 `call 0x6D26E0`
// （= `Game::BombExplosionEffects`）。末尾 4 格是**绑定常量**：
//   `p6`(float f) = **1.0f** @ `0x80BB8A`、`p7`(bool b) = **true** @ `0x80BB87`、
//   `p8`(unsigned long ul) = **4** @ `0x80BB85`、`p9`(bool b2) = **false** @ `0x80BB83`。
// `p3`（`bitset128_t`）= **全 0（16 字节）**；`p4`（`ColorMod const&`）指向栈上 44 字节：
// 前 16 字节 = `(1,1,1,1)`、其余清零。返回 `void`。
// ★ 两个邻居都不匹配（阈值常量组 `175/140/105/90/75` 在 PC 与 Switch **逐字节同**）⇒ 靶点已互证。
//
// **Switch 真身 = `Game::BombExplosionEffects @ 0x355C68`**（入口首 4 字节 `0xD10443FF` =
// `sub sp,sp,#0x110`），mangled:
//   `_ZN15IsaacRepentance4Game20BombExplosionEffectsERKN4KAGE4Math7Vector2EfNS_11bitset128_tERKNS_8ColorModEPNS_6EntityEfbmb`
// ★★ **为什么必须手写**（而不是走数据行）：**9 个形参 ⇒ 第 9 格 `bool` 走栈**
//   （序言 `0x355CFC ldrb w21,[x29,#0x60]`），而通用跳板只填 `x0..x7`/`d0..d7`、**填不了栈**；
//   且 `bitset128_t` 是 16 字节**按值**聚合体（走 `x2:x3`，不是 HFA）。
//   ⇒ 用 `AsFunction<BombExplosionEffectsFn>` 让**编译器**按签名把第 9 格放栈
//   （与批次 340 的 `Game::SpawnEx` 同一条路）。
//
// **逐格 AAPCS64 落位**（全部由序言逐条读出；走栈偏移的算法 = 340 的 `SpawnEx` 同一套：
// `sub sp,sp,#0x110` ⇒ 令 S = 新 sp，`add x29,sp,#0xb0` ⇒ x29 = S+0xb0，
// 调用者的 sp = S+0x110 = **x29 + 0x60**）：
//   0 `this`  `Game*`            → `x0`   （`mov x27, x0`）
//   1 `pos`   `Vector2 const&`   → `x1`   （`mov x22, x1`）
//   2 `damage` `float`           → `s0`   （`mov v8.16b, v0.16b`）
//   3 `tearFlags` `bitset128_t`  → `x2`(低64) + `x3`(高64)（`str x2,[sp,#0x20]` / `mov x28, x3`）
//   4 `cm`    `ColorMod const&`  → `x4`   （`mov x23, x4`）
//   5 `source` `Entity*`         → `x5`   （`mov x19, x5`）
//   6 `f`     `float`            → `s1`   （`mov v9.16b, v1.16b`）
//   7 `b`     `bool`             → `w6`   （`mov w24, w6`）
//   8 `ul`    `unsigned long`    → `x7`   （`mov x20, x7`）
//   9 `b2`    `bool`             → **栈 `[x29,#0x60]`**（`ldrb w21,[x29,#0x60]`）
// ★ 两个 float 的**顺序由形参顺序决定**：`damage` 是第 3 个形参 ⇒ 第一个 float ⇒ `s0`；
//   `f` 是第 7 个 ⇒ 第二个 ⇒ `s1`。**不能把 `f` 挪前面**。
//
// **`tearFlags` 那一格为什么传全 0**：引擎把它当**掩码**与全局的眼泪标志集合相与
// （`0x355D08` 段：`ldp x8,x9,[x26]` → `and x9,x9,x28` → `ldr x10,[sp,#0x20]` → `and x8,x8,x10`
// → `orr`），再用 `Entity_Tear::TEAR_CROSS_BOMB` 去 `tst` —— 全 0 ⇒ 所有位都不命中
// ⇒ 走「无特殊标志」的路径，**与 PC 绑定逐字节同**（PC 给的就是全 0）。
// ★ 末尾 4 格确实被引擎消费（不是死参）：`0x355D74 str s0,[x25,#0x470]`（damage）、
//   `0x355D78 str x20,[x25,#0x420]`（`ul` = 4）、`0x355D7C tbz w24,#0x0`（`b` = true 命中）、
//   `0x355D98 tbz w21,#0x0`（`b2` = false **不**命中）。
//
// 语料 **5 处**（全是**点号**调用，栈上没有 `self`）：
//   `RepentancePlus/RepentancePlus/main.lua:2242`（`Isaac.Explode(Player.Position, Player, 110)`）与
//   `IsaacOnTwitchReloaded/scripts/passiveItems.lua:183/184/185/187`（各 `Isaac.Explode(entity.Position, entity, 60.0/30.0)`）。
inline constexpr uintptr_t kGameBombExplosionEffectsOffset = 0x355C68;
inline constexpr std::uint32_t kGameBombExplosionEffectsEntryWord = 0xD10443FFu;

// ============================================================================
// 批次 346（2026-10-04）：`Entity:AddVelocity(Vector[, boolean])` 用的时间缩放格
// ============================================================================
//
// 规格来源：`docs/取证-M组-AddVelocity可执行规格-20261004d.md` §3.2（偏移量级已由 H 组离线定案、
// O 组独立复核算式逐条正确）；上游 = E 组（`docs/取证-E组-AddVelocity落地规格-20261004b.md`）。

// ---- `Entity + 0x370` = 时间缩放系数（float，常态 1.0f）------------------------------------
//
// **PC 的同角色格 = `Entity + 0x2f4`**（PC 绑定 `0x422B60` 在 `IgnoreTimeScale == false` 时读它，
// 为真时用常量 `1.0f`）。Switch 侧那一格的证据：
//   * `Entity::Update @ 0x60040`：`0x60084 ldr s0,[x19,#0x370]` → `0x60090 str s1,[x19,#0x378]`
//     （`+0x378 += +0x370`，`+0x374` 记上一帧快照）⇒ 这是**每帧的时间值**；
//   * 同一格在 `0x60274` 被当 `ts` 喂 `TimeScaledFriction`、在 `0x60294..0x602b0` 当位移倍率。
// ★★ **量级定案 = 时间缩放系数（常态 1.0f），不是 1/60 的帧时长**（H 组六条证据，关键五条）：
//   ① `Entity::Init @ 0x5989C`：`mov x8,#0x3f800000`（= 1.0f）+ 两条 `movk` 合成 `0xB727C5AC`，
//      `0x598B4 str x8,[x19,#0x370]` ⇒ **出生即精确 1.0f**
//      （1/60 的位型是 `0x3C888889`，不是 `0x3F800000`）；
//   ② `Weapon::GetTimeScale @ 0x4A7950`：owner 为空时兜底 `fmov s0,#1.0` ⇒ 缺省即 1.0；
//   ③ `Room::GetTimeScale @ 0x450F30`：取值集合 {1.0（玩家）/ 0.8（有秒表）/ clamp[0.02,1.75] / +GFuel}
//      —— 全是「≈1 的倍率」，且「秒表 ⇒ 0.8」正对应契约 `Entity.md:288` 的 Stopwatch 减速；
//   ④ 四个写入方（`Entity_{Player,NPC,Projectile,Tear}::Update`）都从那些 getter 取数写进 `+0x370`；
//   ⑤ `Entity::IsTimeScaledFrame @ 0x5C7FC`：把「每帧 += `+0x370`」的累加器当「时间缩放帧」计数。
// ★ 结构对位（逐字段相差 `+0x7C`，加同一个魔法常量）：PC {`0x2B8`/`0x2BC` 速度 Vector2, `0x2C0` 摩擦基, `0x2C4` 摩擦,
//   `0x2F4` 时间缩放, `0x2F8` 快照, `0x2FC` 累加器} ↔ Switch {`0x334`, `0x33C`, `0x340`, `0x370`,
//   `0x374`, `0x378`}；两侧 `Entity::Init` 都写 `{1.0f, 0xB727C5AC, 0}` 到「时间缩放/快照/累加器」三格
//   （同一个非平凡常量当指纹）。
// ★ `kEntityVelocityOffset`（`0x334`）与 `kEntityFrictionOffset`（`0x340`）**早已存在、本批复用**。
//
// ★ 本批**不给布局表 `tools/layout_tables/entity.json` 加 `TimeScale` 行**：本条 `provenance` 是
//   `engine_call`（读三格，其中 `Velocity`/`TimeScale` 都没有 confirmed 布局行 ⇒ 不能冒充
//   `engine_field`），而工具口径明确写着「这类选 `engine_call`，**而不是去造一行布局表**」
//   （`tools/api_definition_of_done.py` 的 `provenance` 段）。M 组 §3.3 给了"若要加"的可过写法备查。
inline constexpr uintptr_t kEntityTimeScaleOffset = 0x370;

// ============================================================================
// 批次 347（2026-10-04）：`RoomConfigSpawn:PickEntry(float r)` 与它要的四件前置
// ============================================================================
//
// 规格来源：`docs/取证-P组-PickEntry可执行规格-20261004e.md`（**本批的完整可执行规格**；
// 它同时更正了 J 组三处 —— 见 `Spawns` 那几条注释）。

// ---- `RoomConfig::Room`（= `RoomDescriptor.Data`）里的 `Spawns` ------------------------------
//
// ★★★ **`Spawns` 不是 `std::vector`**，而是「**数组首地址 + `u16` 计数**」两条字段
//   ⇒ **没有 `end`/`cap`**（J 组写"查不到 end/cap"，P 组更正为"**根本不存在**"，因为不是 vector）。
//   写点 = `RoomConfig::parse_room_node @ 0x48F914/0x48F918`（`str x0,[x20,#0x50]` +
//   `strh w8,[x20,#0x58]`，数组由 `operator new[](0x18*N)` + `memcpy` 建出）；
//   读点 = `Room::Init`（两处）/ `Room::RespawnEnemies` / `Room::SpawnGreedModeWave`
//   —— 四处都是 `ldrh w8,[xN,#0x58]` + `ldr x8,[xN,#0x50]` 这一对。
inline constexpr uintptr_t kRoomConfigRoomSpawnsBeginOffset = 0x50;  // Data + 0x50：Spawn 数组首地址
inline constexpr uintptr_t kRoomConfigRoomSpawnCountOffset = 0x58;   // Data + 0x58：元素个数（**u16**）
inline constexpr std::size_t kRoomConfigSpawnStride = 0x18;          // sizeof(RoomConfig::Spawn)

// ---- `RoomConfig::Spawn` 的三格（元素布局，逐条见 P 组 §2.4）----------------------------------
//
// 零初始化指令逐条给出宽度（`parse_room_node`）：`str wzr,[x0]`（`+0x00` 4 字节 = X/Y 一起清）、
// `str xzr,[x0,#0x8]`（`+0x08` 8 字节指针）、`strb wzr,[x0,#0x10]`（`+0x10` 1 字节）、
// `str wzr,[x0,#0x14]`（`+0x14` 4 字节）；步进 `add x8,x8,#0x30`（两格 = 0x30 ⇒ 每格 **0x18**）。
inline constexpr uintptr_t kRoomConfigSpawnEntriesOffset = 0x08;     // Spawn + 0x08：Entry 数组首地址
inline constexpr uintptr_t kRoomConfigSpawnEntryCountOffset = 0x10;  // Spawn + 0x10：EntryCount（**u8**）
inline constexpr uintptr_t kRoomConfigSpawnSumWeightsOffset = 0x14;  // Spawn + 0x14：SumWeights（f32）
// ★ `Spawn + 0x00`/`+0x02` 是 `X`/`Y`（**i16**，两处消费者按 `(Y+1)*W + X + 1` 当网格坐标用：
//   `Room::Init+0x105c @ 0x45D060` 与 `Room::RespawnEnemies @ 0x488B88`，逐字同形）
//   —— 但**没有任何具名访问器**、也没有第二条独立消费路径把"它是 X"钉死
//   ⇒ 按本项目置信度口径只能记 **candidate（不可用于对外 API）** ⇒ **本批不做**这两个属性
//   （PC 有 ⇒ 已并入偏离登记：模组读 `spawn.X` 会得 `nil`）。

// ---- `RoomConfig::Entry`：12 字节（PC 是 16 字节）--------------------------------------------
//
// `PickEntry` 反汇编里的三连读：`ldr w2,[x8]`（`Type` i32 @ `+0x00`）、
// `ldrh w3,[x8,#0x4]`（`Variant` **u16** @ `+0x04`）、`ldrh w4,[x8,#0x6]`（`SubType` **u16** @ `+0x06`）、
// `ldr s2,[x0,#0x8]`（`Weight` f32 @ `+0x08`）。
//   ★ `kRoomConfigEntryTypeOffset/VariantOffset/SubTypeOffset` **已存在（批次 104）、本批复用**；
//   ★★ **`Variant`/`SubType` 必须按 i16 符号扩展读**（PC 的类型是 `int`；既有
//     `ReadRoomConfigEntryFields` 是**零扩展** ⇒ `0xFFFF` 会答成 `65535`，而 PC 答 `-1`）
//     ⇒ 本批的视图**不复用**那份零扩展实现，另按符号扩展读。
inline constexpr std::size_t kRoomConfigEntryStride = 0x0C;          // sizeof(RoomConfig::Entry)
inline constexpr uintptr_t kRoomConfigEntryWeightOffset = 0x08;      // Entry + 0x08：Weight（f32）

// ---- `RoomConfigSpawn:PickEntry(float r)` 的真身 --------------------------------------------
//
// `_ZNK15IsaacRepentance10RoomConfig5Spawn9PickEntryEf @ 0x494910`（入口首 4 字节 `0xA9BE7BFD` =
// `stp x29,x30,[sp,#-0x20]!`）⇒ `this = x0`、`s0 = float r`、返回 `x0 = RoomConfig::Entry const*`、
// `const` 成员函数。
// ★ **未命中路径不是 `nullptr`**：当 `r*SumWeights` 落在所有条目之后时，引擎会 `bl KAGE_LogMessage`
//   打一条日志，然后返回 `Entries.begin`（`0x494984 ldr x0,[x19,#0x8]`）。⇒ 我们的处理器
//   **只在引擎真返回 0 时压 `nil`**，不要"看到没命中就给 nil"（PC 也是返回一个引用）。
inline constexpr uintptr_t kRoomConfigSpawnPickEntryOffset = 0x494910;
inline constexpr std::uint32_t kRoomConfigSpawnPickEntryEntryWord = 0xA9BE7BFDu;

// 2026-10-09：药丸颜色/效果与实体退化的精确原生入口。
inline constexpr uintptr_t kItemPoolGetPillOffset = 0x3C84B8;
inline constexpr std::array<u8, 16> kItemPoolGetPillExpectedBytes = {0xFF, 0xC3, 0x00, 0xD1, 0xFD, 0x7B, 0x01, 0xA9, 0xFD, 0x43, 0x00, 0x91, 0xF3, 0x13, 0x00, 0xF9};
inline constexpr std::array<u8, 16> kItemPoolGetPillEffectExpectedBytes = {0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9, 0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9};
inline constexpr uintptr_t kGameDevolveEnemyOffset = 0x35B8E0;
inline constexpr std::array<u8, 16> kGameDevolveEnemyExpectedBytes = {0xFF, 0x83, 0x02, 0xD1, 0xE9, 0x23, 0x04, 0x6D, 0xFD, 0x7B, 0x05, 0xA9, 0xFD, 0x43, 0x01, 0x91};

// 2026-10-09：NPC内部AI的GOT槽，不搬运包含b.hi的入口指令。
// Update的五个调用点均汇入此PLT（包括特殊flags的第二次AI），其它更新照常执行。
inline constexpr uintptr_t kNpcUpdateAiOffset = 0x1118F8;
inline constexpr std::array<u8, 16> kNpcUpdateAiExpectedBytes = {0x08, 0x38, 0x40, 0xB9, 0x08, 0x29, 0x00, 0x51, 0x1F, 0xF5, 0x0E, 0x71, 0xA8, 0x06, 0x00, 0x54};
inline constexpr uintptr_t kNpcUpdateAiStubOffset = 0x675C10;
inline constexpr std::array<u8, 16> kNpcUpdateAiStubExpectedBytes = {0x50, 0x21, 0x00, 0xF0, 0x11, 0xBA, 0x46, 0xF9, 0x10, 0xC2, 0x35, 0x91, 0x20, 0x02, 0x1F, 0xD6};
inline constexpr uintptr_t kNpcUpdateAiGotSlotOffset = 0xAA0D70;

// 2026-10-15：Game::Render在0x3529B8调用HUD::Render()，后续才画暂停/过场等前景。
// 复用后文HUD Lua包装的kHudRenderOffset/ExpectedBytes；GOT由ADRP/LDR解码为0xAA3300。
// ABI由_ZN15IsaacRepentance3HUD6RenderEv及调用实参确认：void(this)。
inline constexpr uintptr_t kHudRenderStubOffset = 0x67A730;
inline constexpr std::array<u8, 16> kHudRenderStubExpectedBytes = {
    0x50, 0x21, 0x00, 0xB0, 0x11, 0x82, 0x41, 0xF9,
    0x10, 0x02, 0x0C, 0x91, 0x20, 0x02, 0x1F, 0xD6};
inline constexpr uintptr_t kHudRenderGotSlotOffset = 0xAA3300;
// HUD::Render asks Game::AchievementUnlocksDisallowed at this one callsite.
// Preserve that native query for all other callers (rewards, records, entities).
inline constexpr uintptr_t kHudAchievementQueryCallOffset = 0x3AD040;
inline constexpr std::array<u8,16> kHudAchievementQueryCallExpectedBytes = {0x28,0x14,0x0B,0x94,0xE8,0x03,0x00,0x2A,0x60,0x02,0x40,0xF9,0x09,0x05,0x80,0x52};
inline constexpr uintptr_t kGameAchievementQueryOffset = 0x34EAA8;
inline constexpr std::array<u8,16> kGameAchievementQueryExpectedBytes = {0xFD,0x7B,0xBE,0xA9,0xF3,0x0B,0x00,0xF9,0xFD,0x03,0x00,0x91,0x08,0xA8,0x8B,0x52};
inline constexpr uintptr_t kGameAchievementQueryStubOffset = 0x6720E0;
inline constexpr std::array<u8,16> kGameAchievementQueryStubExpectedBytes = {0x70,0x21,0x00,0x90,0x11,0xEE,0x47,0xF9,0x10,0x62,0x3F,0x91,0x20,0x02,0x1F,0xD6};
inline constexpr uintptr_t kGameAchievementQueryGotSlotOffset = 0xA9EFD8;
inline constexpr uintptr_t kPltResolverOffset = 0x66FAA0;

// 2026-10-09：生成回调在天然替换和实体工厂之前；保留栈上的forceSpawn。
inline constexpr std::array<u8, 16> kGameSpawnExExpectedBytes = {0xFF, 0x83, 0x02, 0xD1, 0xFD, 0x7B, 0x04, 0xA9, 0xFD, 0x03, 0x01, 0x91, 0xFC, 0x6F, 0x05, 0xA9};

// 2026-10-09 HUD偏移：Manager ctor0x3F3C48..54把OptionsConfig建在+0x364D0；
// OptionsConfig::Load0x4304E8..500以字符串HudOffset读float并写+0x44。
// HUD::Render0x3AC828..850读Manager+0x36514，计算(1-offset)*(-20,-12)。
// Menu_Options::Update0x4122E4..318步进0.1并夹到0..1后写同一格。
inline constexpr uintptr_t kManagerHudOffsetOffset = 0x36514;

// 2026-10-15 FoundHUD：Load @0x430530..558将FoundHUD布尔写OptionsConfig+0x3A。
// Manager内OptionsConfig位于+0x364D0；StatHUD::Render @0x3AF1D0..1DC读+0x3650A。
// Menu_Options::Update @0x412338/36C..378切换同一字节，Save @0x430A80保存FoundHUD=%d。
inline constexpr uintptr_t kManagerFoundHudOffset = 0x3650A;

// 2026-10-09 配对身体：init_twin @0x2FADA0在0x2FADE4..DF8把双方
// Entity_Player+0x2580的EHandle::SetRef互相指向；MergeTwins @0x2E83B8读取同格。
// PlayerManager::IsCoopPlay @0x44335C..368比较两者signed玩家index(+0x19F0)，
// 与PC GetMainTwin @0x412690的+0x1D80/+0x1550同一规则。
inline constexpr uintptr_t kEntityPlayerTwinOffset = 0x2580;
// PC IsSubPlayer @0x720270直接返回index bit31；NS InitPreLevelInitStats
// @0x27B308/0x27B30C同样用+0x19F0的bit31判断副玩家，无需按角色Type猜。

// 2026-10-09：Manager::SetSaveSlot0x3FAA3C把Manager+0x18传给PGD::Clear，
// 0x3FAA90..94用同地址Load；PGD是单例内嵌对象，切档读写它，不是另造存档。
inline constexpr uintptr_t kManagerPersistentGameDataObjectOffset = 0x18;
// _ZNK15IsaacRepentance18PersistentGameData8UnlockedENS_12eAchievementE
// @0x439654，完整函数还检查当前Game状态，不能仅复制+0x28成就字节。
inline constexpr uintptr_t kPersistentGameDataUnlockedOffset = 0x439654;
inline constexpr std::array<u8, 16> kPersistentGameDataUnlockedExpectedBytes = {
    0x3F, 0x08, 0x00, 0x31, 0x80, 0x00, 0x00, 0x54,
    0x41, 0x01, 0xF8, 0x37, 0x3F, 0xF4, 0x09, 0x71,
};

// 2026-10-09：PC player属性TearFlags注册805DA6为+0x13D0的16字节可写值。
// NS GetTearHitParams @0x2AD6E8/EC读取player+0x1858/+0x1860；
// Weapon::GetTearFlags @0x4A8640/44在Type1玩家分支读取同格。
inline constexpr uintptr_t kEntityPlayerTearFlagsOffset = 0x1858;
// PC tear getter412650拷贝+0x378，setter650280调用真实SetTearFlags；
// NS SetTearFlags @0x33BE38/44写入+0x418/+0x420，并有额外视觉/效果处理。
inline constexpr uintptr_t kEntityTearFlagsOffset = 0x418;
inline constexpr uintptr_t kEntityTearSetTearFlagsOffset = 0x33BAA0;
inline constexpr std::array<u8,16> kEntityTearSetTearFlagsExpectedBytes = {
    0xFF,0x43,0x02,0xD1,0xE8,0x1B,0x00,0xFD,
    0xFB,0x27,0x00,0xF9,0xFD,0xFB,0x03,0xA9,
};

// 2026-10-09：Player::Init 27951C..558依据真实ItemConfig.Trinkets槽数调整
// 此向量；RecomputeSmelterTrinkets 2F7F70..FF4明确4字节步长、bit15选择+0/+2。
// GetTrinketMultiplier 29B2E0/E4两格均LDRSH；REPENTOGON Global.zhl对应两个short。
inline constexpr uintptr_t kEntityPlayerSmeltedTrinketBeginOffset = 0x1B60;
inline constexpr uintptr_t kEntityPlayerSmeltedTrinketEndOffset = 0x1B68;
inline constexpr uintptr_t kEntityPlayerSmeltedTrinketCapacityOffset = 0x1B70;
inline constexpr std::size_t kSmeltedTrinketDescriptorBytes = 4;

// 2026-10-09：PC玩家可写泪弹属性，按真实消费者映射，不能按PC/NS字段次序猜。
// PC注册805DE2：TearHeight+13BC；GetTearHitParams@2AD6E0读NS+1848至params+50，
// FireTear@2A9AF0把同一格（sp+70）传给Entity_Tear::SetHeight。
inline constexpr uintptr_t kEntityPlayerTearHeightOffset = 0x1848;
// PC注册805DD6：TearFallingSpeed+13C0；FireTear@2A9B18/38读NS+184C，传SetFallingSpeed。
inline constexpr uintptr_t kEntityPlayerTearFallingSpeedOffset = 0x184C;
// PC注册805DCA：TearFallingAcceleration+13C4；FireTear@2A9B74读NS+1850，传SetFallingAcceleration。
inline constexpr uintptr_t kEntityPlayerTearFallingAccelerationOffset = 0x1850;
// PC注册805D9A：TearColor+13E0，writeable=1；NS GetTearHitParams@2AD6F4..72C
// 从player+1868逐字复制44字节至返回params+8，后由FireTear传原生SetColor。
inline constexpr uintptr_t kEntityPlayerTearColorOffset = 0x1868;

// 2026-10-10：REPENTOGON PGD图鉴查询；三个具名函数各0xB4字节，调用原生配置归一化和计数树。
inline constexpr uintptr_t kPersistentGameDataBestiaryKillOffset = 0x43B158;
inline constexpr std::array<u8, 16> kPersistentGameDataBestiaryKillExpectedBytes = {0xFD,0x7B,0xBE,0xA9,0xF3,0x0B,0x00,0xF9,0xFD,0x03,0x00,0x91,0x88,0x33,0x00,0xB0};
inline constexpr uintptr_t kPersistentGameDataBestiaryDeathOffset = 0x43B820;
inline constexpr std::array<u8, 16> kPersistentGameDataBestiaryDeathExpectedBytes = {0xFD,0x7B,0xBE,0xA9,0xF3,0x0B,0x00,0xF9,0xFD,0x03,0x00,0x91,0x88,0x33,0x00,0xB0};
inline constexpr uintptr_t kPersistentGameDataBestiaryEncounterOffset = 0x43B66C;
inline constexpr std::array<u8, 16> kPersistentGameDataBestiaryEncounterExpectedBytes = {0xFD,0x7B,0xBE,0xA9,0xF3,0x0B,0x00,0xF9,0xFD,0x03,0x00,0x91,0x88,0x33,0x00,0xB0};

// 2026-10-10：MC_GET_TRINKET(66) 黄金处理前两内部BL，完整指纹见trinket_internal_guards.hpp。
// x21仅bit0被原函数消费，携带自然对齐pool地址；不写被DontAdvance RNG占用的SP+0x20。
inline constexpr std::uintptr_t kTrinketGetFunctionOffset = 0x3C7600;
inline constexpr std::uintptr_t kTrinketFirstRandomHookOffset = 0x3C7668;
inline constexpr std::uintptr_t kTrinketSelectedHookOffset = 0x3C784C;
inline constexpr std::uintptr_t kTrinketFirstVeneerOffset = 0x68CFE0;
inline constexpr std::uintptr_t kTrinketSelectedVeneerOffset = 0x68CFF0;
inline constexpr std::uintptr_t kItemPoolTrinketRngOffset = 0x8D4;
inline constexpr std::uintptr_t kTrinketManagerGotSlotOffset = 0xAAC648;
inline constexpr std::uintptr_t kTrinketFirstResumeOffset = 0x3C766C;
inline constexpr std::uintptr_t kTrinketGoldenResumeOffset = 0x3C7850;
inline constexpr std::uintptr_t kTrinketCleanupResumeOffset = 0x3C78AC;
inline constexpr std::uint32_t kTrinketFirstRandomExpectedWord = 0x940AA1F2U;
inline constexpr std::uint32_t kTrinketSelectedExpectedWord = 0x940AA589U;

// 70：确定最终位置之后、奖励逻辑之前的VectorCtor BL；取消保析构，跳过seed写回。
inline constexpr uintptr_t kClearAwardHookOffset = 0x456988;
inline constexpr std::uint32_t kClearAwardHookExpectedWord = 0x940864D2U;
inline constexpr uintptr_t kClearAwardResumeOffset = 0x45698C;
inline constexpr uintptr_t kClearAwardCleanupOffset = 0x458170;
// 8B间隙，SoundActorPlay代码CD80..B0与槽CDB0..B8之后、Pause洞CDC0之前。
inline constexpr uintptr_t kClearAwardVeneerOffset = 0x68CDB8;

inline constexpr uintptr_t kRoomSpawnInternalVeneerOffset = 0x68CFD0;
inline constexpr std::size_t kRoomSpawnInternalVeneerBytes = 16;
inline constexpr std::size_t kTrinketFirstVeneerBytes = 16;
inline constexpr std::size_t kTrinketSelectedVeneerBytes = 16;
inline constexpr std::size_t kClearAwardVeneerBytes = 8;

// 2026-10-10：固定REPENTOGON PGD写入/查询；完整NS函数证据存dist/pgd-bestiary-write-static-20261010/。
inline constexpr uintptr_t kPersistentGameDataAddBestiaryKillOffset = 0x43AC5C;
inline constexpr std::array<u8,16> kPersistentGameDataAddBestiaryKillExpectedBytes = {
    0xFD,0x7B,0xBD,0xA9,0xF6,0x57,0x01,0xA9,0xFD,0x03,0x00,0x91,0xF4,0x4F,0x02,0xA9
};
inline constexpr uintptr_t kPersistentGameDataAddBossOffset = 0x439A40;
inline constexpr std::array<u8,16> kPersistentGameDataAddBossExpectedBytes = {
    0xFD,0x7B,0xBE,0xA9,0xF4,0x4F,0x01,0xA9,0xFD,0x03,0x00,0x91,0x3F,0x9C,0x01,0x71
};
// AddBoss 439A60以this+id寻址、439A74写byte 1；439A84/8C等读取id1/2同表。
inline constexpr uintptr_t kPersistentGameDataBossKilledOffset = 0xD87;

// 67基类D2：原内联Remove之后的RNG析构BL，完整控制流守卫见entity_remove_guards.hpp。
inline constexpr uintptr_t kEntityDestructorFunctionOffset = 0x589BC;
inline constexpr uintptr_t kEntityDestructorHookOffset = 0x58A00;
inline constexpr std::uint32_t kEntityDestructorHookExpectedWord = 0x94185D10U;
inline constexpr uintptr_t kEntityDestructorResumeOffset = 0x58A04;
inline constexpr uintptr_t kEntityDestructorVeneerOffset = 0x68CDA8;
inline constexpr std::size_t kEntityDestructorVeneerBytes = 8;
inline constexpr uintptr_t kEntityDestructorRngDestroyOffset = 0x44E3BC;
inline constexpr std::array<u8, 4> kEntityDestructorRngDestroyExpectedBytes = {0xC0,0x03,0x5F,0xD6};

// 2026-10-10：Agony AB+实际require链使用的Familiar orbit方法，完整PC/NS证据存dist/familiar-orbit-static-20261010/。
// GetOrbit返回s0/s1两float HFA，正常层尾支返回Pos；Recalculate bool见PC Lua thunk84BF60。
inline constexpr uintptr_t kEntityFamiliarGetOrbitPositionOffset = 0xAFD84;
// 三轨道字段：PC实际property getter/setter与NS Vector乘/速度乘帧/层读写交叉证明。
inline constexpr uintptr_t kEntityFamiliarOrbitDistanceOffset = 0xD78;
inline constexpr uintptr_t kEntityFamiliarOrbitSpeedOffset = 0xD80;
inline constexpr uintptr_t kEntityFamiliarOrbitLayerOffset = 0xD84;
inline constexpr std::array<u8,16> kEntityFamiliarGetOrbitPositionExpectedBytes = {
    0xFF,0x43,0x01,0xD1,0xE9,0x23,0x01,0x6D,0xF5,0x1B,0x00,0xF9,0xFD,0x7B,0x02,0xA9
};
inline constexpr uintptr_t kEntityFamiliarRecalculateOrbitOffsetOffset = 0xACEA0;
inline constexpr std::array<u8,16> kEntityFamiliarRecalculateOrbitOffsetExpectedBytes = {
    0xFF,0x83,0x02,0xD1,0xEA,0x13,0x00,0xFD,0xE9,0x23,0x03,0x6D,0xFD,0x7B,0x04,0xA9
};
inline constexpr uintptr_t kEntityFamiliarAddToOrbitOffset = 0xAE844;
inline constexpr std::array<u8,16> kEntityFamiliarAddToOrbitExpectedBytes = {
    0xFF,0xC3,0x00,0xD1,0xFD,0x7B,0x01,0xA9,0xFD,0x43,0x00,0x91,0xF4,0x4F,0x02,0xA9
};
inline constexpr uintptr_t kEntityFamiliarRemoveFromOrbitOffset = 0xAD648;
inline constexpr std::array<u8,16> kEntityFamiliarRemoveFromOrbitExpectedBytes = {
    0xFD,0x7B,0xBE,0xA9,0xF3,0x0B,0x00,0xF9,0xFD,0x03,0x00,0x91,0x01,0x84,0x4D,0xB9
};

// 2026-10-10 Agony实际加载模块三查询，完整具名NS原函数见独立dist。
inline constexpr uintptr_t kRoomGetGridCollisionAtPosOffset = 0x459D38;
inline constexpr std::array<u8, 16> kRoomGetGridCollisionAtPosExpectedBytes = {0x08,0x44,0xB8,0x52,0x02,0x01,0x27,0x1E,0x08,0x44,0xA8,0x52,0x02,0x28,0x22,0x1E};
inline constexpr uintptr_t kEntityNpcGetPlayerTargetOffset = 0x10B464;
inline constexpr std::array<u8, 16> kEntityNpcGetPlayerTargetExpectedBytes = {0xFF,0x83,0x02,0xD1,0xFD,0x7B,0x04,0xA9,0xFD,0x03,0x01,0x91,0xFC,0x6F,0x05,0xA9};
inline constexpr uintptr_t kSpriteGetOverlayFrameOffset = 0xAFE0;
inline constexpr std::array<u8, 16> kSpriteGetOverlayFrameExpectedBytes = {0x08,0x34,0x40,0xF9,0x88,0x00,0x00,0xB4,0x00,0x80,0x40,0xBD,0x00,0x00,0x38,0x1E};

// 静态实体方法（2026-10-10）：PC Lua注册/IAT及NS完整函数原件在
// dist/static-entity-methods-20261010/。SetSpriteFrame沿既有ANM2 SetFrame，this=Entity+0x50；
// PC强制Reset、设位置并停止播放与NS 0xA65C完整同形，不在桥中重新夹取frame。
inline constexpr uintptr_t kEntityTearResetSpriteScaleOffset = 0x33D010;
inline constexpr std::array<u8, 16> kEntityTearResetSpriteScaleExpectedBytes = {
    0xFF,0xC3,0x01,0xD1,0xFD,0x7B,0x03,0xA9,0xFD,0xC3,0x00,0x91,0xF7,0x23,0x00,0xF9};
inline constexpr uintptr_t kEntityNpcPlaySoundOffset = 0x119998;
inline constexpr std::array<u8, 16> kEntityNpcPlaySoundExpectedBytes = {
    0x02,0x10,0x2C,0x1E,0x09,0x10,0x4D,0xB9,0x3F,0x49,0x00,0x71,0x23,0x08,0x22,0x1E};
// 两字符串重载：x0 this,x1/x2 classic libc++ string const&,s0 threshold。
inline constexpr uintptr_t kEntityNpcAnimWalkFrameOffset = 0x1100B0;
inline constexpr std::array<u8, 16> kEntityNpcAnimWalkFrameExpectedBytes = {
    0xE8,0x0F,0x1C,0xFC,0xFD,0x7B,0x01,0xA9,0xFD,0x43,0x00,0x91,0xF6,0x57,0x02,0xA9};
// Bomb IsFetus：PC getter422D60/setter5EF220读写+398；NS Init7AF7C清0、
// FireBomb2E4520写1、Update7B7C8/7B834读取+438。按真实u8/Lua真假读写。
inline constexpr uintptr_t kEntityBombIsFetusOffset = 0x438;
// Tear Scale：PC getter544B60读+370，setter650250夹至0.01、写+370/+374再Reset。
// NS SetScale33BF7C是同形原方法，不能用直接字段写入替掉动画更新副作用。
inline constexpr uintptr_t kEntityTearScaleOffset = 0x410;
inline constexpr uintptr_t kEntityTearSetScaleOffset = 0x33BF7C;
inline constexpr std::array<u8, 16> kEntityTearSetScaleExpectedBytes = {
    0x48,0xE1,0x9A,0x52,0x68,0x84,0xA7,0x72,0x01,0x01,0x27,0x1E,0x09,0x00,0x26,0x1E};

// 2026-10-10加载前12/37：运行时只发布slot，首Random仍只安全替换BL。
inline constexpr uintptr_t kLevelCurseFunctionOffset = 0x3E0688;
inline constexpr uintptr_t kLevelCurseFirstRandomOffset = 0x3E0B34;
inline constexpr std::uint32_t kLevelCurseFirstRandomExpectedWord = 0x940A3CBF;
inline constexpr uintptr_t kLevelCurseFirstResumeOffset = 0x3E0B38;
inline constexpr uintptr_t kLevelCurseFirstVeneerOffset = 0x68CF98;
inline constexpr std::size_t kLevelCurseFirstVeneerBytes = 8;

// 2026-10-20：console长度中继[68CD40,68CD68)之后的24B零区。
// 当前console中继与旧Stage48MusicPlay互斥；三槽彼此独占，不能交给旧诊断中继。
inline constexpr uintptr_t kClearAwardPointerSlotOffset = 0x68CD68;
inline constexpr uintptr_t kLevelCurseFirstPointerSlotOffset = 0x68CD70;
inline constexpr uintptr_t kEntityDestructorPointerSlotOffset = 0x68CD78;
inline constexpr uintptr_t kLevelCurseEvalOffset = 0x3E0C88;
inline constexpr uintptr_t kLevelCurseStaticRelayCodeOffset = 0x68CDC0;
inline constexpr uintptr_t kLevelCurseStaticRelaySlotOffset = 0x68CDD8;
inline constexpr uintptr_t kPickupSelectionFunctionOffset = 0x269594;
inline constexpr uintptr_t kPickupSelectionHookOffset = 0x269D50;
inline constexpr uintptr_t kPickupSelectionStaticRelayCodeOffset = 0x68CDE0;
inline constexpr uintptr_t kPickupSelectionStaticRelaySlotOffset = 0x68CDF8;

// Variant110奖杯配置路径绕过普通CMP点，原LDUR后有自己的CMP/角色修正。
inline constexpr uintptr_t kPickupSelectionSpecialOffset = 0x269D08;
inline constexpr uintptr_t kPickupSelectionSpecialRelayCodeOffset = 0x68CD00;
inline constexpr uintptr_t kPickupSelectionSpecialRelaySlotOffset = 0x68CD18;

// 2026-10-13：Console未知命令的两条冷条件中继，仅生产包；与stage48音频诊断互斥。
inline constexpr uintptr_t kConsoleUnknownLengthRelayCodeOffset = 0x68CD40;
inline constexpr uintptr_t kConsoleUnknownLengthRelaySlotOffset = 0x68CD60;
inline constexpr uintptr_t kConsoleUnknownCompareRelayCodeOffset = 0x68CD80;
inline constexpr uintptr_t kConsoleUnknownCompareRelaySlotOffset = 0x68CDA0;

// CHAPI玩家字段：PC与NS独立写者/消费者及新增layout行见player-api/evidence。
inline constexpr uintptr_t kEntityPlayerDamageCooldownOffset = 0x1734;
inline constexpr uintptr_t kEntityPlayerJarHeartsOffset = 0x16CC;
inline constexpr uintptr_t kEntityPlayerSubPlayerOffset = 0x2460;
inline constexpr uintptr_t kEntityPlayerAddJarHeartsOffset = 0x280018;

// HUD Lua包装：PC7FAF10/7FB300；NS三个具名重载和Render的真实入口。
inline constexpr uintptr_t kHudRenderOffset = 0x3AC71C;
inline constexpr std::array<unsigned char,16> kHudRenderExpectedBytes = {0xEF,0x3B,0xB6,0x6D,0xED,0x33,0x01,0x6D,0xEB,0x2B,0x02,0x6D,0xE9,0x23,0x03,0x6D};
inline constexpr uintptr_t kHudShowItemTextOffset = 0x3AB318;
inline constexpr std::array<unsigned char,16> kHudShowItemTextExpectedBytes = {0xFF,0xC3,0x07,0xD1,0xFD,0x7B,0x1A,0xA9,0xFD,0x83,0x06,0x91,0xFC,0xDB,0x00,0xF9};
inline constexpr uintptr_t kHudShowItemObjectOffset = 0x3AB6D8;
inline constexpr std::array<unsigned char,16> kHudShowItemObjectExpectedBytes = {0xFD,0x7B,0xBB,0xA9,0xFC,0x67,0x01,0xA9,0xFD,0x03,0x00,0x91,0xF8,0x5F,0x02,0xA9};
inline constexpr uintptr_t kHudShowFortuneTextOffset = 0x3AC0B0;
inline constexpr std::array<unsigned char,16> kHudShowFortuneTextExpectedBytes = {0xFF,0x43,0x02,0xD1,0xEB,0x2B,0x02,0x6D,0xF9,0x2B,0x00,0xF9,0xE9,0x23,0x03,0x6D};

// CHAPI健康方法的权威字段/原生入口，独立PC/NS原件取证见health-api/report.md。
inline constexpr uintptr_t kEntityPlayerGoldenHeartsOffset = 0x1DC4;
inline constexpr uintptr_t kEntityPlayerRottenHeartsOffset = 0x2474;
inline constexpr uintptr_t kEntityPlayerAddBlackHeartsRPlusOffset = 0x27D9F4;
inline constexpr uintptr_t kEntityPlayerAddMaxHeartsRPlusOffset = 0x27CFBC;
inline constexpr uintptr_t kEntityPlayerAddRottenHeartsRPlusOffset = 0x2FEA98;
inline constexpr uintptr_t kEntityPlayerAddSoulHeartsRPlusOffset = 0x27DD54;
inline constexpr uintptr_t kEntityPlayerCanPickBlackHeartsRPlusOffset = 0x2FB900;
inline constexpr uintptr_t kEntityPlayerCanPickBoneHeartsRPlusOffset = 0x2FCA88;
inline constexpr uintptr_t kEntityPlayerCanPickGoldenHeartsRPlusOffset = 0x2FCA20;
inline constexpr uintptr_t kEntityPlayerCanPickRottenHeartsRPlusOffset = 0x2FEE98;
inline constexpr uintptr_t kEntityPlayerGetHeartLimitRPlusOffset = 0x27E6A4;
inline constexpr uintptr_t kEntityPlayerIsBlackHeartRPlusOffset = 0x27FE70;
inline constexpr uintptr_t kEntityPlayerIsBoneHeartRPlusOffset = 0x2AD618;
inline constexpr uintptr_t kEntityPlayerRemoveBlackHeartRPlusOffset = 0x27FEBC;
inline constexpr uintptr_t kEntityPlayerSetFullHeartsRPlusOffset = 0x2B0B88;

// RPlus武器/拾取字段：PC getters/setters与NS消费者原件见callback-rplus-20261013。
inline constexpr uintptr_t kEntityCollisionDamageOffset = 0x35C;
inline constexpr uintptr_t kEntitySetCollisionDamageVtableSlot = 0x80;
inline constexpr uintptr_t kEntitySetCollisionDamageOffset = 0x67570;
inline constexpr uintptr_t kEntityTearSetCollisionDamageOffset = 0x341670;
inline constexpr uintptr_t kEntityTearFallingSpeedOffset = 0x404;
inline constexpr uintptr_t kEntityTearFallingAccelerationOffset = 0x408;
inline constexpr uintptr_t kEntityKnifeTearFlagsOffset = 0x400;
inline constexpr uintptr_t kEntityLaserTearFlagsOffset = 0x418;
inline constexpr uintptr_t kEntityBombTearFlagsOffset = 0x428;
inline constexpr uintptr_t kEntityPickupAutoUpdatePriceOffset = 0x568;
inline constexpr uintptr_t kEntityBombSetTearFlagsOffset = 0x7EAB8;
inline constexpr std::array<u8,16> kEntityBombSetTearFlagsExpectedBytes = {0x28,0x00,0x80,0x52,0x01,0x14,0x02,0xF9,0x02,0x18,0x02,0xF9,0x08,0x5C,0x11,0x39};

// 2026-10-13：社区1.60方法固定NS入口，守卫及PC参数证据见methods-api/report.md。
inline constexpr uintptr_t kRPlusAddBurnOffset = 0x5F994;
inline constexpr uintptr_t kRPlusAddConfusionOffset = 0x5F0BC;
inline constexpr uintptr_t kRPlusAddMidasFreezeOffset = 0x5F3D0;
inline constexpr uintptr_t kRPlusAddShrinkOffset = 0x65370;
inline constexpr uintptr_t kRPlusAddSlowingOffset = 0x5E96C;
inline constexpr uintptr_t kRPlusHasMortalDamageOffset = 0x5E260;
inline constexpr uintptr_t kRPlusAddCostumeOffset = 0x290C38;
inline constexpr uintptr_t kRPlusAddWispOffset = 0x31BB2C;
inline constexpr uintptr_t kRPlusAnimateCardOffset = 0x2F67B4;
inline constexpr uintptr_t kRPlusAnimatePickupOffset = 0x2F6640;
inline constexpr uintptr_t kRPlusCanPickupItemOffset = 0x2DF948;
inline constexpr uintptr_t kRPlusFireBombOffset = 0x2E4210;
inline constexpr uintptr_t kRPlusFlushQueueItemOffset = 0x2926D4;
inline constexpr uintptr_t kRPlusFullChargeOffset = 0x299634;
inline constexpr uintptr_t kRPlusGetMaxTrinketsOffset = 0x2A1DE0;
inline constexpr uintptr_t kRPlusGetTearMovementInheritanceOffset = 0x2B8EB4;
inline constexpr uintptr_t kRPlusRemoveCostumeOffset = 0x2914E0;
inline constexpr uintptr_t kRPlusSetPillOffset = 0x2E8DDC;
inline constexpr uintptr_t kRPlusSetPocketActiveItemOffset = 0x29A6C4;
inline constexpr uintptr_t kRPlusThrowBlueSpiderOffset = 0x2ACB54;
inline constexpr uintptr_t kRPlusWillPlayerReviveOffset = 0x2D640C;
inline constexpr uintptr_t kRPlusFartOffset = 0x35A6B4;
inline constexpr uintptr_t kRPlusShakeScreenOffset = 0x355BAC;
inline constexpr uintptr_t kRPlusBarOffset = 0x385850;
inline constexpr uintptr_t kRPlusFindGridPathOffset = 0x42B9E4;
inline constexpr uintptr_t kRPlusAimWriterOffset = 0x2A1D18;
inline constexpr uintptr_t kRPlusBombCountdownWriterOffset = 0x7CC18;
inline constexpr uintptr_t kRPlusGridDescWriterOffset = 0x37E4BC;
inline constexpr uintptr_t kRPlusHeartStagesWriterOffset = 0x4A5FDC;
inline constexpr uintptr_t kRPlusAwardSeedReaderOffset = 0x456834;
inline constexpr uintptr_t kRPlusBombCountdownOffset = 0x400;
inline constexpr uintptr_t kRPlusAimDirectionOffset = 0x1A04;
inline constexpr uintptr_t kRPlusHeartStagesOffset = 0x26FA68;
inline constexpr uintptr_t kRPlusAwardSeedOffset = 0x6C;
inline constexpr uintptr_t kRPlusHeartsOffset = 0x16BC;
inline constexpr uintptr_t kRPlusSoulHeartsOffset = 0x16C4;
inline constexpr uintptr_t kRPlusMaxHeartsOffset = 0x16B8;

// 2026-10-14：100个新增Lua API；完整函数/PC包装见dist/apis100-20261014。
// 入口缓存按模块基址分代；Grid Hurt实际通过vtable+0x28选择覆盖方法。
// EntityPlayer:AddBombs — IsaacRepentance::Entity_Player::AddBombs(int)
inline constexpr uintptr_t kApi100EntityPlayerAddBombsOffset = 0x2802E8;
inline constexpr std::array<u8,16> kApi100EntityPlayerAddBombsExpectedBytes = {0xff,0x83,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf9,0x13,0x00,0xf9};
// EntityPlayer:AddGigaBombs — IsaacRepentance::Entity_Player::AddGigaBombs(int)
inline constexpr uintptr_t kApi100EntityPlayerAddGigaBombsOffset = 0x2BB030;
inline constexpr std::array<u8,16> kApi100EntityPlayerAddGigaBombsExpectedBytes = {0x08,0xa4,0x64,0xb9,0x08,0x01,0x01,0x0b,0x0a,0xdc,0x56,0xb9,0x1f,0x01,0x0a,0x6b};
// EntityPlayer:AddJarFlies — IsaacRepentance::Entity_Player::AddJarFlies(int)
inline constexpr uintptr_t kApi100EntityPlayerAddJarFliesOffset = 0x2FC8EC;
inline constexpr std::array<u8,16> kApi100EntityPlayerAddJarFliesExpectedBytes = {0x08,0xd0,0x56,0xb9,0x08,0x01,0x01,0x0b,0x21,0x00,0x80,0x52,0x1f,0x51,0x00,0x71};
// EntityPlayer:AddPoopMana — IsaacRepentance::Entity_Player::AddPoopMana(int)
inline constexpr uintptr_t kApi100EntityPlayerAddPoopManaOffset = 0x2BAF44;
inline constexpr std::array<u8,16> kApi100EntityPlayerAddPoopManaExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityPlayer:AddDeadEyeCharge — IsaacRepentance::Entity_Player::AddDeadEyeCharge()
inline constexpr uintptr_t kApi100EntityPlayerAddDeadEyeChargeOffset = 0x2FBF2C;
inline constexpr std::array<u8,16> kApi100EntityPlayerAddDeadEyeChargeExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x08,0x28,0x5d,0xb9};
// EntityPlayer:ClearDeadEyeCharge — IsaacRepentance::Entity_Player::ClearDeadEyeCharge()
inline constexpr uintptr_t kApi100EntityPlayerClearDeadEyeChargeOffset = 0x2FBF74;
inline constexpr std::array<u8,16> kApi100EntityPlayerClearDeadEyeChargeExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0x28,0x5d,0xb9};
// EntityPlayer:ClearCostumes — IsaacRepentance::Entity_Player::ClearCostumes()
inline constexpr uintptr_t kApi100EntityPlayerClearCostumesOffset = 0x27A99C;
inline constexpr std::array<u8,16> kApi100EntityPlayerClearCostumesExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityPlayer:ClearTemporaryEffects — IsaacRepentance::Entity_Player::ClearTemporaryEffects()
inline constexpr uintptr_t kApi100EntityPlayerClearTemporaryEffectsOffset = 0x2DCCD4;
inline constexpr std::array<u8,16> kApi100EntityPlayerClearTemporaryEffectsExpectedBytes = {0xfd,0x7b,0xbb,0xa9,0xfa,0x67,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
// EntityPlayer:GetEffectiveBloodCharge — IsaacRepentance::Entity_Player::GetEffectiveBloodCharge() const
inline constexpr uintptr_t kApi100EntityPlayerGetEffectiveBloodChargeOffset = 0x2DCF40;
inline constexpr std::array<u8,16> kApi100EntityPlayerGetEffectiveBloodChargeExpectedBytes = {0x08,0x38,0x57,0xb9,0x1f,0x91,0x00,0x71,0x61,0x00,0x00,0x54,0x00,0x7c,0x64,0xb9};
// EntityPlayer:GetEffectiveSoulCharge — IsaacRepentance::Entity_Player::GetEffectiveSoulCharge() const
inline constexpr uintptr_t kApi100EntityPlayerGetEffectiveSoulChargeOffset = 0x2DCF24;
inline constexpr std::array<u8,16> kApi100EntityPlayerGetEffectiveSoulChargeExpectedBytes = {0x08,0x38,0x57,0xb9,0x1f,0x49,0x00,0x71,0x61,0x00,0x00,0x54,0x00,0x78,0x64,0xb9};
// EntityPlayer:GetMaxPocketItems — IsaacRepentance::Entity_Player::GetMaxPocketItems() const
inline constexpr uintptr_t kApi100EntityPlayerGetMaxPocketItemsOffset = 0x2B0970;
inline constexpr std::array<u8,16> kApi100EntityPlayerGetMaxPocketItemsExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x61,0x1f,0x80,0x52};
// EntityPlayer:GetMaxPoopMana — IsaacRepentance::Entity_Player::GetMaxPoopMana() const
inline constexpr uintptr_t kApi100EntityPlayerGetMaxPoopManaOffset = 0x3004A4;
inline constexpr std::array<u8,16> kApi100EntityPlayerGetMaxPoopManaExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x08,0x38,0x57,0xb9};
// EntityPlayer:HasTimedItem — IsaacRepentance::Entity_Player::HasTimedItem()
inline constexpr uintptr_t kApi100EntityPlayerHasTimedItemOffset = 0x2DDC50;
inline constexpr std::array<u8,16> kApi100EntityPlayerHasTimedItemExpectedBytes = {0xfd,0x7b,0xbf,0xa9,0xfd,0x03,0x00,0x91,0x68,0x3e,0x00,0xf0,0x01,0x64,0x59,0xb9};
// EntityPlayer:IsHeldItemVisible — IsaacRepentance::Entity_Player::IsHeldItemVisible() const
inline constexpr uintptr_t kApi100EntityPlayerIsHeldItemVisibleOffset = 0x2D8DA4;
inline constexpr std::array<u8,16> kApi100EntityPlayerIsHeldItemVisibleExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0x24,0x42,0xf9};
// EntityPlayer:RemoveBlueFly — IsaacRepentance::Entity_Player::RemoveBlueFly()
inline constexpr uintptr_t kApi100EntityPlayerRemoveBlueFlyOffset = 0x28D45C;
inline constexpr std::array<u8,16> kApi100EntityPlayerRemoveBlueFlyExpectedBytes = {0x08,0xe4,0x56,0xb9,0x08,0x05,0x00,0x51,0x08,0xe4,0x16,0xb9,0xc0,0x03,0x5f,0xd6};
// EntityPlayer:RemoveBlueSpider — IsaacRepentance::Entity_Player::RemoveBlueSpider()
inline constexpr uintptr_t kApi100EntityPlayerRemoveBlueSpiderOffset = 0x2FB490;
inline constexpr std::array<u8,16> kApi100EntityPlayerRemoveBlueSpiderExpectedBytes = {0x08,0xe8,0x56,0xb9,0x08,0x05,0x00,0x51,0x08,0xe8,0x16,0xb9,0xc0,0x03,0x5f,0xd6};
// EntityPlayer:CanAddCollectible — IsaacRepentance::Entity_Player::CanAddCollectible(IsaacRepentance::eCollectibleType) const
inline constexpr uintptr_t kApi100EntityPlayerCanAddCollectibleOffset = 0x2F630C;
inline constexpr std::array<u8,16> kApi100EntityPlayerCanAddCollectibleExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf3,0x03,0x00,0xaa};
// EntityPlayer:AnimateLightTravel — IsaacRepentance::Entity_Player::AnimateLightTravel()
inline constexpr uintptr_t kApi100EntityPlayerAnimateLightTravelOffset = 0x2F6A64;
inline constexpr std::array<u8,16> kApi100EntityPlayerAnimateLightTravelExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityPlayer:TryUseKey — IsaacRepentance::Entity_Player::TryUseKey()
inline constexpr uintptr_t kApi100EntityPlayerTryUseKeyOffset = 0x28D7E8;
inline constexpr std::array<u8,16> kApi100EntityPlayerTryUseKeyExpectedBytes = {0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf5,0x13,0x00,0xf9};
// EntityPlayer:GetGreedDonationBreakChance — IsaacRepentance::Entity_Player::GetGreedDonationBreakChance() const
inline constexpr uintptr_t kApi100EntityPlayerGetGreedDonationBreakChanceOffset = 0x2FD1BC;
inline constexpr std::array<u8,16> kApi100EntityPlayerGetGreedDonationBreakChanceExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x01,0x38,0x57,0xb9};
// Entity:BloodExplode — IsaacRepentance::Entity::BloodExplode()
inline constexpr uintptr_t kApi100EntityBloodExplodeOffset = 0x5C938;
inline constexpr std::array<u8,16> kApi100EntityBloodExplodeExpectedBytes = {0xff,0x83,0x04,0xd1,0xef,0x3b,0x08,0x6d,0xed,0x33,0x09,0x6d,0xeb,0x2b,0x0a,0x6d};
// Entity:GetLastParent — IsaacRepentance::Entity::GetLastParent()
inline constexpr uintptr_t kApi100EntityGetLastParentOffset = 0x58BE8;
inline constexpr std::array<u8,16> kApi100EntityGetLastParentExpectedBytes = {0xe8,0x03,0x00,0xaa,0x00,0xc8,0x41,0xf9,0xc0,0xff,0xff,0xb5,0xe0,0x03,0x08,0xaa};
// Entity:GetLastChild — IsaacRepentance::Entity::GetLastChild()
inline constexpr uintptr_t kApi100EntityGetLastChildOffset = 0x58BFC;
inline constexpr std::array<u8,16> kApi100EntityGetLastChildExpectedBytes = {0xe8,0x03,0x00,0xaa,0x00,0xcc,0x41,0xf9,0xc0,0xff,0xff,0xb5,0xe0,0x03,0x08,0xaa};
// Entity:HasFullHealth — IsaacRepentance::Entity::HasFullHealth()
inline constexpr uintptr_t kApi100EntityHasFullHealthOffset = 0x5A234;
inline constexpr std::array<u8,16> kApi100EntityHasFullHealthExpectedBytes = {0x00,0x54,0x43,0xbd,0x01,0x58,0x43,0xbd,0x00,0x20,0x21,0x1e,0xe0,0xb7,0x9f,0x1a};
// Entity:IsFrame — IsaacRepentance::Entity::IsFrame(int, int) const
inline constexpr uintptr_t kApi100EntityIsFrameOffset = 0x5C780;
inline constexpr std::array<u8,16> kApi100EntityIsFrameExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityFamiliar:AddCoins — IsaacRepentance::Entity_Familiar::AddCoins(int)
inline constexpr uintptr_t kApi100EntityFamiliarAddCoinsOffset = 0xD62BC;
inline constexpr std::array<u8,16> kApi100EntityFamiliarAddCoinsExpectedBytes = {0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityFamiliar:AddHearts — IsaacRepentance::Entity_Familiar::AddHearts(int)
inline constexpr uintptr_t kApi100EntityFamiliarAddHeartsOffset = 0xD63FC;
inline constexpr std::array<u8,16> kApi100EntityFamiliarAddHeartsExpectedBytes = {0x08,0x90,0x4d,0xb9,0x08,0x01,0x01,0x0b,0x08,0x90,0x0d,0xb9,0xc0,0x03,0x5f,0xd6};
// EntityFamiliar:AddKeys — IsaacRepentance::Entity_Familiar::AddKeys(int)
inline constexpr uintptr_t kApi100EntityFamiliarAddKeysOffset = 0xD8DC0;
inline constexpr std::array<u8,16> kApi100EntityFamiliarAddKeysExpectedBytes = {0x08,0x94,0x4d,0xb9,0x08,0x01,0x01,0x0b,0x08,0x94,0x0d,0xb9,0xc0,0x03,0x5f,0xd6};
// EntityFamiliar:RemoveFromFollowers — IsaacRepentance::Entity_Familiar::remove_from_followers()
inline constexpr uintptr_t kApi100EntityFamiliarRemoveFromFollowersOffset = 0xAD67C;
inline constexpr std::array<u8,16> kApi100EntityFamiliarRemoveFromFollowersExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityFamiliar:RemoveFromDelayed — IsaacRepentance::Entity_Familiar::remove_from_delayed()
inline constexpr uintptr_t kApi100EntityFamiliarRemoveFromDelayedOffset = 0xAD7FC;
inline constexpr std::array<u8,16> kApi100EntityFamiliarRemoveFromDelayedExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x08,0x24,0x76,0x39};
// EntityFamiliar:AddToDelayed — IsaacRepentance::Entity_Familiar::add_to_delayed()
inline constexpr uintptr_t kApi100EntityFamiliarAddToDelayedOffset = 0xACCCC;
inline constexpr std::array<u8,16> kApi100EntityFamiliarAddToDelayedExpectedBytes = {0xff,0x83,0x01,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xf8,0x5f,0x03,0xa9};
// EntityFamiliar:MoveDelayed — IsaacRepentance::Entity_Familiar::move_delayed(int)
inline constexpr uintptr_t kApi100EntityFamiliarMoveDelayedOffset = 0xC1ACC;
inline constexpr std::array<u8,16> kApi100EntityFamiliarMoveDelayedExpectedBytes = {0xff,0x43,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf7,0x13,0x00,0xf9};
// EntityFamiliar:MoveDiagonally — IsaacRepentance::Entity_Familiar::move_diagonally(float)
inline constexpr uintptr_t kApi100EntityFamiliarMoveDiagonallyOffset = 0xBF35C;
inline constexpr std::array<u8,16> kApi100EntityFamiliarMoveDiagonallyExpectedBytes = {0xff,0x03,0x02,0xd1,0xea,0x13,0x00,0xfd,0xe9,0x23,0x03,0x6d,0xfd,0x7b,0x04,0xa9};
// EntityFamiliar:PlayChargeAnim — IsaacRepentance::Entity_Familiar::play_charge_anim(IsaacRepentance::eDirection)
inline constexpr uintptr_t kApi100EntityFamiliarPlayChargeAnimOffset = 0xB1A9C;
inline constexpr std::array<u8,16> kApi100EntityFamiliarPlayChargeAnimExpectedBytes = {0xff,0x83,0x02,0xd1,0xe9,0x23,0x03,0x6d,0xfb,0x2b,0x00,0xf9,0xfd,0x7b,0x04,0xa9};
// EntityFamiliar:PlayFloatAnim — IsaacRepentance::Entity_Familiar::play_float_anim(IsaacRepentance::eDirection)
inline constexpr uintptr_t kApi100EntityFamiliarPlayFloatAnimOffset = 0xB1880;
inline constexpr std::array<u8,16> kApi100EntityFamiliarPlayFloatAnimExpectedBytes = {0xff,0xc3,0x00,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf3,0x13,0x00,0xf9};
// EntityFamiliar:PlayShootAnim — IsaacRepentance::Entity_Familiar::play_shoot_anim(IsaacRepentance::eDirection)
inline constexpr uintptr_t kApi100EntityFamiliarPlayShootAnimOffset = 0xB1CD8;
inline constexpr std::array<u8,16> kApi100EntityFamiliarPlayShootAnimExpectedBytes = {0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf5,0x13,0x00,0xf9};
// EntityFamiliar:Shoot — IsaacRepentance::Entity_Familiar::shoot()
inline constexpr uintptr_t kApi100EntityFamiliarShootOffset = 0xB20F8;
inline constexpr std::array<u8,16> kApi100EntityFamiliarShootExpectedBytes = {0xff,0x83,0x01,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xf8,0x5f,0x03,0xa9};
// EntityPickup:PlayPickupSound — IsaacRepentance::Entity_Pickup::PlayPickupSound()
inline constexpr uintptr_t kApi100EntityPickupPlayPickupSoundOffset = 0x27104C;
inline constexpr std::array<u8,16> kApi100EntityPickupPlayPickupSoundExpectedBytes = {0xff,0x03,0x01,0xd1,0xe8,0x0b,0x00,0xfd,0xf5,0x17,0x00,0xf9,0xfd,0xfb,0x01,0xa9};
// EntityPickup:PlayDropSound — IsaacRepentance::Entity_Pickup::PlayDropSound()
inline constexpr uintptr_t kApi100EntityPickupPlayDropSoundOffset = 0x270808;
inline constexpr std::array<u8,16> kApi100EntityPickupPlayDropSoundExpectedBytes = {0x08,0x3c,0x40,0xb9,0x1f,0xad,0x04,0x71,0x6c,0x02,0x00,0x54,0x08,0x29,0x00,0x51};
// EntityPickup:AppearFast — IsaacRepentance::Entity_Pickup::AppearFast()
inline constexpr uintptr_t kApi100EntityPickupAppearFastOffset = 0x26C80C;
inline constexpr std::array<u8,16> kApi100EntityPickupAppearFastExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x08,0x3c,0x40,0xb9};
// EntityPickup:GetCoinValue — IsaacRepentance::Entity_Pickup::GetCoinValue() const
inline constexpr uintptr_t kApi100EntityPickupGetCoinValueOffset = 0x271680;
inline constexpr std::array<u8,16> kApi100EntityPickupGetCoinValueExpectedBytes = {0x08,0x3c,0x40,0xb9,0x1f,0x51,0x00,0x71,0xe1,0x00,0x00,0x54,0x08,0x40,0x40,0xb9};
// GridEntity:Hurt — IsaacRepentance::GridEntity::Hurt(int)
inline constexpr uintptr_t kApi100GridEntityHurtOffset = 0x380C38;
inline constexpr std::array<u8,16> kApi100GridEntityHurtExpectedBytes = {0xe0,0x03,0x1f,0x2a,0xc0,0x03,0x5f,0xd6,0x08,0x00,0x40,0xf9,0x81,0x00,0x80,0x52};
// GridEntityDoor:CanBlowOpen — IsaacRepentance::GridEntity_Door::CanBlowOpen()
inline constexpr uintptr_t kApi100GridEntityDoorCanBlowOpenOffset = 0x384DB0;
inline constexpr std::array<u8,16> kApi100GridEntityDoorCanBlowOpenExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x54,0x39,0x00,0x90};
// GridEntityDoor:SetLocked — IsaacRepentance::GridEntity_Door::SetLocked(bool)
inline constexpr uintptr_t kApi100GridEntityDoorSetLockedOffset = 0x386010;
inline constexpr std::array<u8,16> kApi100GridEntityDoorSetLockedExpectedBytes = {0x08,0x0c,0x40,0xb9,0x1f,0x11,0x00,0x71,0x61,0x00,0x00,0x54,0x41,0x00,0x00,0x37};
// GridEntityDoor:SetRoomTypes — IsaacRepentance::GridEntity_Door::SetRoomTypes(IsaacRepentance::eRoomType, IsaacRepentance::eRoomType)
inline constexpr uintptr_t kApi100GridEntityDoorSetRoomTypesOffset = 0x385A78;
inline constexpr std::array<u8,16> kApi100GridEntityDoorSetRoomTypesExpectedBytes = {0xfd,0x7b,0xbb,0xa9,0xf9,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
// GridEntityDoor:SpawnDust — IsaacRepentance::GridEntity_Door::SpawnDust()
inline constexpr uintptr_t kApi100GridEntityDoorSpawnDustOffset = 0x38229C;
inline constexpr std::array<u8,16> kApi100GridEntityDoorSpawnDustExpectedBytes = {0xff,0xc3,0x03,0xd1,0xed,0x33,0x07,0x6d,0xeb,0x2b,0x08,0x6d,0xe9,0x23,0x09,0x6d};
// GridEntityRock:GetBigRockFrame — IsaacRepentance::GridEntity_Rock::GetBigRockFrame() const
inline constexpr uintptr_t kApi100GridEntityRockGetBigRockFrameOffset = 0x39349C;
inline constexpr std::array<u8,16> kApi100GridEntityRockGetBigRockFrameExpectedBytes = {0x08,0x0c,0x40,0xb9,0x08,0xa1,0x0f,0x71,0x00,0x21,0x9f,0x5a,0xc0,0x03,0x5f,0xd6};
// GridEntityRock:SetBigRockFrame — IsaacRepentance::GridEntity_Rock::SetBigRockFrame(int)
inline constexpr uintptr_t kApi100GridEntityRockSetBigRockFrameOffset = 0x39388C;
inline constexpr std::array<u8,16> kApi100GridEntityRockSetBigRockFrameExpectedBytes = {0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf5,0x13,0x00,0xf9};
// GridEntityRock:UpdateAnimFrame — IsaacRepentance::GridEntity_Rock::update_anim_frame()
inline constexpr uintptr_t kApi100GridEntityRockUpdateAnimFrameOffset = 0x38FC14;
inline constexpr std::array<u8,16> kApi100GridEntityRockUpdateAnimFrameExpectedBytes = {0x08,0x0c,0x40,0xb9,0x09,0xa1,0x0f,0x71,0x29,0x21,0x9f,0x5a,0x3f,0x01,0x00,0x71};
// ItemPool:AddBibleUpgrade — IsaacRepentance::ItemPool::AddBibleUpgrade(int, IsaacRepentance::ItemPool::eItemPoolType)
inline constexpr uintptr_t kApi100ItemPoolAddBibleUpgradeOffset = 0x3CAF0C;
inline constexpr std::array<u8,16> kApi100ItemPoolAddBibleUpgradeExpectedBytes = {0x5f,0x7c,0x00,0x71,0xa1,0x0b,0x00,0x54,0x08,0x48,0x40,0xb9,0x08,0x01,0x01,0x0b};
// ItemPool:ForceAddPillEffect — IsaacRepentance::ItemPool::ForceAddPillEffect(IsaacRepentance::ePillEffect)
inline constexpr uintptr_t kApi100ItemPoolForceAddPillEffectOffset = 0x3CA8D0;
inline constexpr std::array<u8,16> kApi100ItemPoolForceAddPillEffectExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0x30,0x4a,0xb9};
// ItemPool:GetCard — IsaacRepentance::ItemPool::GetCard(unsigned int, bool, bool, bool) const
inline constexpr uintptr_t kApi100ItemPoolGetCardOffset = 0x3C8488;
inline constexpr std::array<u8,16> kApi100ItemPoolGetCardExpectedBytes = {0x7f,0x00,0x00,0x72,0x49,0x01,0x80,0x52,0x2a,0x11,0x9f,0x1a,0x9f,0x00,0x00,0x72};
// ItemPool:GetPill — IsaacRepentance::ItemPool::GetPill(unsigned int) const
inline constexpr uintptr_t kApi100ItemPoolGetPillOffset = 0x3C84B8;
inline constexpr std::array<u8,16> kApi100ItemPoolGetPillExpectedBytes = {0xff,0xc3,0x00,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf3,0x13,0x00,0xf9};
// ItemPool:GetTrinket — IsaacRepentance::ItemPool::GetTrinket(bool)
inline constexpr uintptr_t kApi100ItemPoolGetTrinketOffset = 0x3C7600;
inline constexpr std::array<u8,16> kApi100ItemPoolGetTrinketExpectedBytes = {0xff,0x43,0x02,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xfc,0x6f,0x04,0xa9};
// ItemPool:RemoveTrinket — IsaacRepentance::ItemPool::RemoveTrinket(IsaacRepentance::eTrinketType)
inline constexpr uintptr_t kApi100ItemPoolRemoveTrinketOffset = 0x3C7B34;
inline constexpr std::array<u8,16> kApi100ItemPoolRemoveTrinketExpectedBytes = {0x09,0x08,0x45,0xf9,0x28,0x4d,0x21,0x8b,0x0a,0x4d,0x40,0x38,0x6a,0x01,0x00,0x34};
// ItemPool:ResetRoomBlacklist — IsaacRepentance::ItemPool::ResetRoomBlacklist()
inline constexpr uintptr_t kApi100ItemPoolResetRoomBlacklistOffset = 0x3CAEC4;
inline constexpr std::array<u8,16> kApi100ItemPoolResetRoomBlacklistExpectedBytes = {0x08,0x88,0x44,0xf9,0x08,0x02,0x00,0xb4,0xe9,0x03,0x1f,0xaa,0x28,0x00,0x80,0x52};
// ItemPool:ResetTrinkets — IsaacRepentance::ItemPool::ResetTrinkets()
inline constexpr uintptr_t kApi100ItemPoolResetTrinketsOffset = 0x3C78E0;
inline constexpr std::array<u8,16> kApi100ItemPoolResetTrinketsExpectedBytes = {0xfd,0x7b,0xba,0xa9,0xfb,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xfa,0x67,0x02,0xa9};
// Level:ApplyBlueMapEffect — IsaacRepentance::Level::ApplyBlueMapEffect()
inline constexpr uintptr_t kApi100LevelApplyBlueMapEffectOffset = 0x3E6E7C;
inline constexpr std::array<u8,16> kApi100LevelApplyBlueMapEffectExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Level:ApplyCompassEffect — IsaacRepentance::Level::ApplyCompassEffect(bool)
inline constexpr uintptr_t kApi100LevelApplyCompassEffectOffset = 0x3E6F54;
inline constexpr std::array<u8,16> kApi100LevelApplyCompassEffectExpectedBytes = {0xfd,0x7b,0xbb,0xa9,0xf9,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
// Level:ApplyMapEffect — IsaacRepentance::Level::ApplyMapEffect()
inline constexpr uintptr_t kApi100LevelApplyMapEffectOffset = 0x3E6D98;
inline constexpr std::array<u8,16> kApi100LevelApplyMapEffectExpectedBytes = {0xfd,0x7b,0xbc,0xa9,0xf8,0x5f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// Level:CanOpenChallengeRoom — IsaacRepentance::Level::CanOpenChallengeRoom(int) const
inline constexpr uintptr_t kApi100LevelCanOpenChallengeRoomOffset = 0x3E6C1C;
inline constexpr std::array<u8,16> kApi100LevelCanOpenChallengeRoomExpectedBytes = {0xfd,0x7b,0xbb,0xa9,0xfa,0x67,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
// Level:CanSpawnDevilRoom — IsaacRepentance::Level::CanSpawnDevilRoom()
inline constexpr uintptr_t kApi100LevelCanSpawnDevilRoomOffset = 0x3E7894;
inline constexpr std::array<u8,16> kApi100LevelCanSpawnDevilRoomExpectedBytes = {0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// Level:CanStageHaveCurseOfLabyrinth — IsaacRepentance::Level::CanStageHaveCurseOfLabyrinth(IsaacRepentance::eLevelStage)
inline constexpr uintptr_t kApi100LevelCanStageHaveCurseOfLabyrinthOffset = 0x3D082C;
inline constexpr std::array<u8,16> kApi100LevelCanStageHaveCurseOfLabyrinthExpectedBytes = {0xfd,0x7b,0xbf,0xa9,0xfd,0x03,0x00,0x91,0xe9,0x36,0x00,0x90,0x29,0x4d,0x43,0xf9};
// Level:ChangeRoom — IsaacRepentance::Level::ChangeRoom(int, int)
inline constexpr uintptr_t kApi100LevelChangeRoomOffset = 0x3D9AAC;
inline constexpr std::array<u8,16> kApi100LevelChangeRoomExpectedBytes = {0xff,0x83,0x02,0xd1,0xfd,0x7b,0x04,0xa9,0xfd,0x03,0x01,0x91,0xfc,0x6f,0x05,0xa9};
// Level:GetCurseName — IsaacRepentance::Level::GetCurseName()
inline constexpr uintptr_t kApi100LevelGetCurseNameOffset = 0x3E3FA8;
inline constexpr std::array<u8,16> kApi100LevelGetCurseNameExpectedBytes = {0xff,0x03,0x02,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xfa,0x67,0x04,0xa9};
// Level:GetName — IsaacRepentance::Level::GetName()
inline constexpr uintptr_t kApi100LevelGetNameOffset = 0x3E3DC8;
inline constexpr std::array<u8,16> kApi100LevelGetNameExpectedBytes = {0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// Level:InitializeDevilAngelRoom — IsaacRepentance::Level::InitializeDevilAngelRoom(bool, bool)
inline constexpr uintptr_t kApi100LevelInitializeDevilAngelRoomOffset = 0x3E6654;
inline constexpr std::array<u8,16> kApi100LevelInitializeDevilAngelRoomExpectedBytes = {0xff,0xc3,0x02,0xd1,0xe9,0x23,0x04,0x6d,0xfd,0x7b,0x05,0xa9,0xfd,0x43,0x01,0x91};
// Level:MakeRedRoomDoor — IsaacRepentance::Level::MakeRedRoomDoor(int, IsaacRepentance::eDoorSlot)
inline constexpr uintptr_t kApi100LevelMakeRedRoomDoorOffset = 0x3D8554;
inline constexpr std::array<u8,16> kApi100LevelMakeRedRoomDoorExpectedBytes = {0xff,0x83,0x04,0xd1,0xfd,0x7b,0x0c,0xa9,0xfd,0x03,0x03,0x91,0xfc,0x6f,0x0d,0xa9};
// Level:RemoveCompassEffect — IsaacRepentance::Level::RemoveCompassEffect()
inline constexpr uintptr_t kApi100LevelRemoveCompassEffectOffset = 0x3E723C;
inline constexpr std::array<u8,16> kApi100LevelRemoveCompassEffectExpectedBytes = {0xfd,0x7b,0xba,0xa9,0xfb,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xfa,0x67,0x02,0xa9};
// Level:SetRedHeartDamage — IsaacRepentance::Level::SetRedHeartDamage()
inline constexpr uintptr_t kApi100LevelSetRedHeartDamageOffset = 0x3E7F00;
inline constexpr std::array<u8,16> kApi100LevelSetRedHeartDamageExpectedBytes = {0x08,0xb9,0x82,0x52,0x48,0x00,0xa0,0x72,0x08,0x00,0x08,0x8b,0x09,0x15,0x40,0xf9};
// Level:ShowMap — IsaacRepentance::Level::ShowMap()
inline constexpr uintptr_t kApi100LevelShowMapOffset = 0x3E7048;
inline constexpr std::array<u8,16> kApi100LevelShowMapExpectedBytes = {0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// Level:ShowName — IsaacRepentance::Level::ShowName(bool)
inline constexpr uintptr_t kApi100LevelShowNameOffset = 0x3E4148;
inline constexpr std::array<u8,16> kApi100LevelShowNameExpectedBytes = {0xff,0x83,0x01,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xf6,0x57,0x04,0xa9};
// Level:UncoverHiddenDoor — IsaacRepentance::Level::UncoverHiddenDoor(int, IsaacRepentance::eDoorSlot)
inline constexpr uintptr_t kApi100LevelUncoverHiddenDoorOffset = 0x3E7CAC;
inline constexpr std::array<u8,16> kApi100LevelUncoverHiddenDoorExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Room:DamageGrid — IsaacRepentance::Room::DamageGrid(int, int)
inline constexpr uintptr_t kApi100RoomDamageGridOffset = 0x484A3C;
inline constexpr std::array<u8,16> kApi100RoomDamageGridExpectedBytes = {0x3f,0xfc,0x06,0x71,0x08,0x01,0x00,0x54,0x08,0x4c,0x21,0x8b,0x00,0x19,0x40,0xf9};
// Room:GetBrokenWatchState — IsaacRepentance::Room::GetBrokenWatchState() const
inline constexpr uintptr_t kApi100RoomGetBrokenWatchStateOffset = 0x450F00;
inline constexpr std::array<u8,16> kApi100RoomGetBrokenWatchStateExpectedBytes = {0xe8,0x32,0x00,0x90,0x08,0x4d,0x43,0xf9,0x08,0x01,0x40,0xf9,0x09,0x51,0x9f,0x52};
// Room:GetDevilRoomChance — IsaacRepentance::Room::GetDevilRoomChance()
inline constexpr uintptr_t kApi100RoomGetDevilRoomChanceOffset = 0x4662F4;
inline constexpr std::array<u8,16> kApi100RoomGetDevilRoomChanceExpectedBytes = {0xe9,0x23,0xbc,0x6d,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf6,0x57,0x02,0xa9};
// Room:GetDungeonRockIdx — IsaacRepentance::Room::GetDungeonRockIdx() const
inline constexpr uintptr_t kApi100RoomGetDungeonRockIdxOffset = 0x4891F0;
inline constexpr std::array<u8,16> kApi100RoomGetDungeonRockIdxExpectedBytes = {0x08,0x31,0x00,0xf0,0x08,0x4d,0x43,0xf9,0x08,0x01,0x40,0xf9,0x29,0xbe,0x82,0x52};
// Room:GetLightingAlpha — IsaacRepentance::Room::GetLightingAlpha()
inline constexpr uintptr_t kApi100RoomGetLightingAlphaOffset = 0x477504;
inline constexpr std::array<u8,16> kApi100RoomGetLightingAlphaExpectedBytes = {0xff,0x43,0x01,0xd1,0xe9,0x23,0x01,0x6d,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91};
// Room:GetRandomTileIndex — IsaacRepentance::Room::GetRandomTileIndex(int)
inline constexpr uintptr_t kApi100RoomGetRandomTileIndexOffset = 0x461FB4;
inline constexpr std::array<u8,16> kApi100RoomGetRandomTileIndexExpectedBytes = {0xff,0x83,0x01,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xf7,0x1b,0x00,0xf9};
// Room:HasLava — IsaacRepentance::Room::HasLava() const
inline constexpr uintptr_t kApi100RoomHasLavaOffset = 0x461F90;
inline constexpr std::array<u8,16> kApi100RoomHasLavaExpectedBytes = {0x08,0xb0,0x61,0xb9,0x1f,0x81,0x00,0x71,0xa1,0x00,0x00,0x54,0x08,0x04,0x40,0xf9};
// Room:HasWater — IsaacRepentance::Room::HasWater()
inline constexpr uintptr_t kApi100RoomHasWaterOffset = 0x487FA0;
inline constexpr std::array<u8,16> kApi100RoomHasWaterExpectedBytes = {0x88,0x22,0x8f,0x52,0x00,0x68,0x68,0xbc,0x08,0x20,0x20,0x1e,0xe0,0xd7,0x9f,0x1a};
// Room:IsLShapedRoom — IsaacRepentance::Room::IsLShapedRoom() const
inline constexpr uintptr_t kApi100RoomIsLShapedRoomOffset = 0x48453C;
inline constexpr std::array<u8,16> kApi100RoomIsLShapedRoomExpectedBytes = {0x08,0x04,0x40,0xf9,0x08,0x09,0x40,0xf9,0x08,0x5d,0x40,0xb9,0x08,0x25,0x00,0x51};
// Room:RespawnEnemies — IsaacRepentance::Room::RespawnEnemies()
inline constexpr uintptr_t kApi100RoomRespawnEnemiesOffset = 0x488AA0;
inline constexpr std::array<u8,16> kApi100RoomRespawnEnemiesExpectedBytes = {0xff,0x03,0x03,0xd1,0xfd,0x7b,0x06,0xa9,0xfd,0x83,0x01,0x91,0xfc,0x6f,0x07,0xa9};
// Room:SetBrokenWatchState — IsaacRepentance::Room::SetBrokenWatchState(int)
inline constexpr uintptr_t kApi100RoomSetBrokenWatchStateOffset = 0x488664;
inline constexpr std::array<u8,16> kApi100RoomSetBrokenWatchStateExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x01,0x44,0x19,0xb9};
// Room:ShopReshuffle — IsaacRepentance::Room::ShopReshuffle(bool, bool)
inline constexpr uintptr_t kApi100RoomShopReshuffleOffset = 0x487490;
inline constexpr std::array<u8,16> kApi100RoomShopReshuffleExpectedBytes = {0xff,0x43,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf7,0x13,0x00,0xf9};
// Room:ShopRestockFull — IsaacRepentance::Room::ShopRestockFull()
inline constexpr uintptr_t kApi100RoomShopRestockFullOffset = 0x486EF0;
inline constexpr std::array<u8,16> kApi100RoomShopRestockFullExpectedBytes = {0xff,0xc3,0x03,0xd1,0xe8,0x43,0x00,0xfd,0xfd,0x7b,0x09,0xa9,0xfd,0x43,0x02,0x91};
// Room:ShopRestockPartial — IsaacRepentance::Room::ShopRestockPartial()
inline constexpr uintptr_t kApi100RoomShopRestockPartialOffset = 0x46CE64;
inline constexpr std::array<u8,16> kApi100RoomShopRestockPartialExpectedBytes = {0xff,0x03,0x02,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xfc,0x6f,0x03,0xa9};
// Room:TriggerClear — IsaacRepentance::Room::TriggerClear(bool)
inline constexpr uintptr_t kApi100RoomTriggerClearOffset = 0x470B58;
inline constexpr std::array<u8,16> kApi100RoomTriggerClearExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Room:TrySpawnBlueWombDoor — IsaacRepentance::Room::TrySpawnBlueWombDoor(bool, bool, bool)
inline constexpr uintptr_t kApi100RoomTrySpawnBlueWombDoorOffset = 0x471F7C;
inline constexpr std::array<u8,16> kApi100RoomTrySpawnBlueWombDoorExpectedBytes = {0xff,0x83,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xfa,0x67,0x02,0xa9};
// Room:TrySpawnBossRushDoor — IsaacRepentance::Room::TrySpawnBossRushDoor(bool, bool)
inline constexpr uintptr_t kApi100RoomTrySpawnBossRushDoorOffset = 0x4669F0;
inline constexpr std::array<u8,16> kApi100RoomTrySpawnBossRushDoorExpectedBytes = {0xff,0x83,0x01,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xf8,0x5f,0x03,0xa9};
// Room:TrySpawnMegaSatanRoomDoor — IsaacRepentance::Room::TrySpawnMegaSatanRoomDoor(bool)
inline constexpr uintptr_t kApi100RoomTrySpawnMegaSatanRoomDoorOffset = 0x4624AC;
inline constexpr std::array<u8,16> kApi100RoomTrySpawnMegaSatanRoomDoorExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Room:TrySpawnSecretExit — IsaacRepentance::Room::TrySpawnSecretExit(bool, bool)
inline constexpr uintptr_t kApi100RoomTrySpawnSecretExitOffset = 0x464C10;
inline constexpr std::array<u8,16> kApi100RoomTrySpawnSecretExitExpectedBytes = {0xff,0x43,0x04,0xd1,0xed,0x33,0x08,0x6d,0xfc,0x63,0x00,0xf9,0xeb,0x2b,0x09,0x6d};
// Room:TrySpawnTheVoidDoor — IsaacRepentance::Room::TrySpawnTheVoidDoor(bool)
inline constexpr uintptr_t kApi100RoomTrySpawnTheVoidDoorOffset = 0x4723E0;
inline constexpr std::array<u8,16> kApi100RoomTrySpawnTheVoidDoorExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Color:SetOffset — IsaacRepentance::ColorMod::SetOffset(float, float, float)
inline constexpr uintptr_t kApi100ColorSetOffsetOffset = 0x37870;
inline constexpr std::array<u8,16> kApi100ColorSetOffsetExpectedBytes = {0x00,0x20,0x00,0xbd,0x01,0x24,0x00,0xbd,0x02,0x28,0x00,0xbd,0xc0,0x03,0x5f,0xd6};
// Color:SetTint — IsaacRepentance::ColorMod::SetTint(float, float, float, float)
inline constexpr uintptr_t kApi100ColorSetTintOffset = 0x37848;
inline constexpr std::array<u8,16> kApi100ColorSetTintExpectedBytes = {0x00,0x00,0x00,0xbd,0x01,0x04,0x00,0xbd,0x02,0x08,0x00,0xbd,0x03,0x0c,0x00,0xbd};
// Color:Reset — IsaacRepentance::ColorMod::Reset()
inline constexpr uintptr_t kApi100ColorResetOffset = 0x37830;
inline constexpr std::array<u8,16> kApi100ColorResetExpectedBytes = {0xe8,0x1b,0x09,0xb2,0x08,0x20,0x00,0xa9,0x1f,0x10,0x00,0xf9,0x1f,0x28,0x00,0xb9};
// Sprite:Reload — IsaacRepentance::ANM2::Reload()
inline constexpr uintptr_t kApi100SpriteReloadOffset = 0xCB74;
inline constexpr std::array<u8,16> kApi100SpriteReloadExpectedBytes = {0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0x00,0x40,0x39};
// Sprite:RemoveOverlay — IsaacRepentance::ANM2::RemoveOverlay()
inline constexpr uintptr_t kApi100SpriteRemoveOverlayOffset = 0xAFFC;
inline constexpr std::array<u8,16> kApi100SpriteRemoveOverlayExpectedBytes = {0x00,0x80,0x01,0x91,0xe1,0x03,0x1f,0xaa,0x37,0x94,0x19,0x14,0xfd,0x7b,0xbe,0xa9};
// MusicManager:Fadein — IsaacRepentance::Music::Fadein(IsaacRepentance::eMusic, float, float)
inline constexpr uintptr_t kApi100MusicManagerFadeinOffset = 0x4275E4;
inline constexpr std::array<u8,16> kApi100MusicManagerFadeinExpectedBytes = {0xe9,0x23,0xbd,0x6d,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf3,0x13,0x00,0xf9};
// MusicManager:Fadeout — IsaacRepentance::Music::Fadeout(float)
inline constexpr uintptr_t kApi100MusicManagerFadeoutOffset = 0x427630;
inline constexpr std::array<u8,16> kApi100MusicManagerFadeoutExpectedBytes = {0x08,0x00,0x80,0xb9,0x09,0x3c,0x80,0x52,0x08,0x01,0x09,0x9b,0x1f,0xd9,0x01,0xb9};

// 2026-10-14第二批100：固定PC/NS完整证据见dist/apis200-20261014。
// Entity:HasCommonParentWithEntity — IsaacRepentance::Entity::HasCommonParentWithEntity(IsaacRepentance::Entity*)
inline constexpr uintptr_t kApi200EntityHasCommonParentWithEntityOffset=0x58F24;
inline constexpr std::array<u8,16> kApi200EntityHasCommonParentWithEntityExpectedBytes={0x41,0x01,0x00,0xb4,0x28,0x38,0x40,0xb9,0x1f,0x79,0x03,0x71,0x61,0x00,0x00,0x54};
// Entity:SetSize — IsaacRepentance::Entity::SetSize(float, KAGE::Math::Vector2, int)
inline constexpr uintptr_t kApi200EntitySetSizeOffset=0x59E54;
inline constexpr std::array<u8,16> kApi200EntitySetSizeExpectedBytes={0xff,0x83,0x02,0xd1,0xec,0x0b,0x00,0xfd,0xeb,0x2b,0x02,0x6d,0xe9,0x23,0x03,0x6d};
// EntityFamiliar:GetOrbitDistance — IsaacRepentance::Entity_Familiar::get_orbit_distance(int)
inline constexpr uintptr_t kApi200EntityFamiliarGetOrbitDistanceOffset=0xAD254;
inline constexpr std::array<u8,16> kApi200EntityFamiliarGetOrbitDistanceExpectedBytes={0x48,0x50,0x00,0xf0,0x08,0x61,0x01,0x91,0x89,0x02,0x80,0x52,0x08,0x20,0x29,0x9b};
// EntityFamiliar:PickEnemyTarget — IsaacRepentance::Entity_Familiar::pick_enemy_target(float, int, unsigned int, KAGE::Math::Vector2 const&, float)
inline constexpr uintptr_t kApi200EntityFamiliarPickEnemyTargetOffset=0xB2448;
inline constexpr std::array<u8,16> kApi200EntityFamiliarPickEnemyTargetExpectedBytes={0xff,0x03,0x03,0xd1,0xee,0x13,0x00,0xfd,0xed,0x33,0x03,0x6d,0xeb,0x2b,0x04,0x6d};
// EntityKnife:Reset — IsaacRepentance::Entity_Knife::Reset()
inline constexpr uintptr_t kApi200EntityKnifeResetOffset=0xF4F68;
inline constexpr std::array<u8,16> kApi200EntityKnifeResetExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xc1,0x4d,0x00,0x90};
// EntityKnife:Shoot — IsaacRepentance::Entity_Knife::Shoot(float, float)
inline constexpr uintptr_t kApi200EntityKnifeShootOffset=0xF4C58;
inline constexpr std::array<u8,16> kApi200EntityKnifeShootExpectedBytes={0xff,0xc3,0x00,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityPlayer:AddCurseMistEffect — IsaacRepentance::Entity_Player::AddCurseMistEffect()
inline constexpr uintptr_t kApi200EntityPlayerAddCurseMistEffectOffset=0x2C7280;
inline constexpr std::array<u8,16> kApi200EntityPlayerAddCurseMistEffectExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0xfc,0x84,0x52};
// EntityPlayer:AddDollarBillEffect — IsaacRepentance::Entity_Player::add_dollar_bill_effect()
inline constexpr uintptr_t kApi200EntityPlayerAddDollarBillEffectOffset=0x2DF808;
inline constexpr std::array<u8,16> kApi200EntityPlayerAddDollarBillEffectExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityPlayer:AddPlayerFormCostume — IsaacRepentance::Entity_Player::add_player_form_costume(IsaacRepentance::ePlayerForm)
inline constexpr uintptr_t kApi200EntityPlayerAddPlayerFormCostumeOffset=0x29854C;
inline constexpr std::array<u8,16> kApi200EntityPlayerAddPlayerFormCostumeExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xb4,0x40,0x00,0x90};
// EntityPlayer:AnimatePitfallIn — IsaacRepentance::Entity_Player::AnimatePitfallIn(bool)
inline constexpr uintptr_t kApi200EntityPlayerAnimatePitfallInOffset=0x2F6AD0;
inline constexpr std::array<u8,16> kApi200EntityPlayerAnimatePitfallInExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityPlayer:AnimatePitfallOut — IsaacRepentance::Entity_Player::AnimatePitfallOut()
inline constexpr uintptr_t kApi200EntityPlayerAnimatePitfallOutOffset=0x2F6B78;
inline constexpr std::array<u8,16> kApi200EntityPlayerAnimatePitfallOutExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityPlayer:AnimateTeleport — IsaacRepentance::Entity_Player::AnimateTeleport(bool)
inline constexpr uintptr_t kApi200EntityPlayerAnimateTeleportOffset=0x2F6BEC;
inline constexpr std::array<u8,16> kApi200EntityPlayerAnimateTeleportExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf8,0x5f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityPlayer:DoZitEffect — IsaacRepentance::Entity_Player::do_zit_effect(KAGE::Math::Vector2 const&)
inline constexpr uintptr_t kApi200EntityPlayerDoZitEffectOffset=0x2AD1C0;
inline constexpr std::array<u8,16> kApi200EntityPlayerDoZitEffectExpectedBytes={0xff,0x03,0x03,0xd1,0xe8,0x2b,0x00,0xfd,0xfd,0x7b,0x06,0xa9,0xfd,0x83,0x01,0x91};
// EntityPlayer:DropPocketItem — IsaacRepentance::Entity_Player::DropPocketItem(unsigned int, KAGE::Math::Vector2 const&)
inline constexpr uintptr_t kApi200EntityPlayerDropPocketItemOffset=0x2E8B9C;
inline constexpr std::array<u8,16> kApi200EntityPlayerDropPocketItemExpectedBytes={0xff,0x83,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf9,0x13,0x00,0xf9};
// EntityPlayer:FireBrimstone — IsaacRepentance::Entity_Player::FireBrimstone(KAGE::Math::Vector2 const&, IsaacRepentance::Entity*, float)
inline constexpr uintptr_t kApi200EntityPlayerFireBrimstoneOffset=0x2E4704;
inline constexpr std::array<u8,16> kApi200EntityPlayerFireBrimstoneExpectedBytes={0xff,0x43,0x01,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xf4,0x4f,0x04,0xa9};
// EntityPlayer:FireDelayedBrimstone — IsaacRepentance::Entity_Player::FireDelayedBrimstone(float, IsaacRepentance::Entity*)
inline constexpr uintptr_t kApi200EntityPlayerFireDelayedBrimstoneOffset=0x2FB24C;
inline constexpr std::array<u8,16> kApi200EntityPlayerFireDelayedBrimstoneExpectedBytes={0xff,0xc3,0x02,0xd1,0xe8,0x3b,0x00,0xfd,0xfd,0x7b,0x08,0xa9,0xfd,0x03,0x02,0x91};
// EntityPlayer:FireKnife — IsaacRepentance::Entity_Player::FireKnife(IsaacRepentance::Entity*, unsigned int, float, bool, unsigned int)
inline constexpr uintptr_t kApi200EntityPlayerFireKnifeOffset=0x2F7738;
inline constexpr std::array<u8,16> kApi200EntityPlayerFireKnifeExpectedBytes={0xff,0x83,0x01,0xd1,0xe8,0x0b,0x00,0xfd,0xf9,0x17,0x00,0xf9,0xfd,0xfb,0x01,0xa9};
// EntityPlayer:FireTechXLaser — IsaacRepentance::Entity_Player::FireTechXLaser(KAGE::Math::Vector2 const&, KAGE::Math::Vector2 const&, float, IsaacRepentance::Entity*, float)
inline constexpr uintptr_t kApi200EntityPlayerFireTechXLaserOffset=0x2FCEB4;
inline constexpr std::array<u8,16> kApi200EntityPlayerFireTechXLaserExpectedBytes={0xff,0x83,0x03,0xd1,0xeb,0x2b,0x07,0x6d,0xf9,0x53,0x00,0xf9,0xe9,0x23,0x08,0x6d};
// EntityPlayer:GetBombFlags — IsaacRepentance::Entity_Player::GetBombFlags(bool) const
inline constexpr uintptr_t kApi200EntityPlayerGetBombFlagsOffset=0x2B78EC;
inline constexpr std::array<u8,16> kApi200EntityPlayerGetBombFlagsExpectedBytes={0xff,0xc3,0x05,0xd1,0xfd,0x7b,0x11,0xa9,0xfd,0x43,0x04,0x91,0xfc,0x6f,0x12,0xa9};
// EntityPlayer:GetFlyingOffset — IsaacRepentance::Entity_Player::GetFlyingOffset() const
inline constexpr uintptr_t kApi200EntityPlayerGetFlyingOffsetOffset=0x2BB9F0;
inline constexpr std::array<u8,16> kApi200EntityPlayerGetFlyingOffsetExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x88,0x3f,0x00,0xb0};
// EntityPlayer:GetLaserOffset — IsaacRepentance::Entity_Player::get_laser_offset(IsaacRepentance::Entity_Player::eLaserOffset, KAGE::Math::Vector2 const&) const
inline constexpr uintptr_t kApi200EntityPlayerGetLaserOffsetOffset=0x2B86E8;
inline constexpr std::array<u8,16> kApi200EntityPlayerGetLaserOffsetExpectedBytes={0xff,0xc3,0x01,0xd1,0xfd,0x7b,0x04,0xa9,0xfd,0x03,0x01,0x91,0xf5,0x2b,0x00,0xf9};
// EntityPlayer:GetNPCTarget — IsaacRepentance::Entity_Player::GetNPCTarget()
inline constexpr uintptr_t kApi200EntityPlayerGetNPCTargetOffset=0x2A1CA8;
inline constexpr std::array<u8,16> kApi200EntityPlayerGetNPCTargetExpectedBytes={0x08,0x0c,0x4c,0xf9,0x68,0x00,0x00,0xb4,0xe0,0x03,0x08,0xaa,0xc0,0x03,0x5f,0xd6};
// EntityPlayer:HasInvincibility — IsaacRepentance::Entity_Player::HasInvincibility(unsigned long)
inline constexpr uintptr_t kApi200EntityPlayerHasInvincibilityOffset=0x2AA45C;
inline constexpr std::array<u8,16> kApi200EntityPlayerHasInvincibilityExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityPlayer:InitBabySkin — IsaacRepentance::Entity_Player::init_baby_skin()
inline constexpr uintptr_t kApi200EntityPlayerInitBabySkinOffset=0x27B048;
inline constexpr std::array<u8,16> kApi200EntityPlayerInitBabySkinExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityPlayer:IsFullSpriteRendering — IsaacRepentance::Entity_Player::IsFullSpriteRendering()
inline constexpr uintptr_t kApi200EntityPlayerIsFullSpriteRenderingOffset=0x2B8DD0;
inline constexpr std::array<u8,16> kApi200EntityPlayerIsFullSpriteRenderingExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0x1b,0x83,0x52};
// EntityPlayer:IsPosInSpotLight — IsaacRepentance::Entity_Player::IsPosInSpotLight(KAGE::Math::Vector2 const&)
inline constexpr uintptr_t kApi200EntityPlayerIsPosInSpotLightOffset=0x2DF8AC;
inline constexpr std::array<u8,16> kApi200EntityPlayerIsPosInSpotLightExpectedBytes={0xff,0x03,0x01,0xd1,0xe8,0x13,0x00,0xfd,0xf3,0x1f,0x00,0xf9,0xfd,0xfb,0x02,0xa9};
// EntityPlayer:PlayExtraAnimation — IsaacRepentance::Entity_Player::PlayExtraAnimation(char const*)
inline constexpr uintptr_t kApi200EntityPlayerPlayExtraAnimationOffset=0x2B0904;
inline constexpr std::array<u8,16> kApi200EntityPlayerPlayExtraAnimationExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityPlayer:QueueItem — IsaacRepentance::Entity_Player::QueueItem(IsaacRepentance::ItemConfig::Item const*, int, unsigned char, int)
inline constexpr uintptr_t kApi200EntityPlayerQueueItemOffset=0x2924A4;
inline constexpr std::array<u8,16> kApi200EntityPlayerQueueItemExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityPlayer:RemoveCurseMistEffect — IsaacRepentance::Entity_Player::RemoveCurseMistEffect()
inline constexpr uintptr_t kApi200EntityPlayerRemoveCurseMistEffectOffset=0x2C73C4;
inline constexpr std::array<u8,16> kApi200EntityPlayerRemoveCurseMistEffectExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityPlayer:RemoveSkinCostume — IsaacRepentance::Entity_Player::RemoveSkinCostume()
inline constexpr uintptr_t kApi200EntityPlayerRemoveSkinCostumeOffset=0x2E81F0;
inline constexpr std::array<u8,16> kApi200EntityPlayerRemoveSkinCostumeExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x34,0x3e,0x00,0x90};
// EntityPlayer:ResetItemState — IsaacRepentance::Entity_Player::ResetItemState()
inline constexpr uintptr_t kApi200EntityPlayerResetItemStateOffset=0x2992CC;
inline constexpr std::array<u8,16> kApi200EntityPlayerResetItemStateExpectedBytes={0xff,0xc3,0x06,0xd1,0xfd,0x7b,0x16,0xa9,0xfd,0x83,0x05,0x91,0xfc,0xbb,0x00,0xf9};
// EntityPlayer:RespawnFamiliars — IsaacRepentance::Entity_Player::RespawnFamiliars()
inline constexpr uintptr_t kApi200EntityPlayerRespawnFamiliarsOffset=0x2A1C98;
inline constexpr std::array<u8,16> kApi200EntityPlayerRespawnFamiliarsExpectedBytes={0x08,0x58,0x59,0xb9,0x08,0x01,0x17,0x32,0x08,0x58,0x19,0xb9,0xb3,0x3e,0x0f,0x14};
// EntityPlayer:ShootRedCandle — IsaacRepentance::Entity_Player::shoot_red_candle(KAGE::Math::Vector2 const&)
inline constexpr uintptr_t kApi200EntityPlayerShootRedCandleOffset=0x2F1EB8;
inline constexpr std::array<u8,16> kApi200EntityPlayerShootRedCandleExpectedBytes={0xff,0x43,0x03,0xd1,0xfd,0x7b,0x0a,0xa9,0xfd,0x83,0x02,0x91,0xf6,0x57,0x0b,0xa9};
// EntityPlayer:SpawnMawOfVoid — IsaacRepentance::Entity_Player::SpawnMawOfVoid(int)
inline constexpr uintptr_t kApi200EntityPlayerSpawnMawOfVoidOffset=0x2B8590;
inline constexpr std::array<u8,16> kApi200EntityPlayerSpawnMawOfVoidExpectedBytes={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityPlayer:ThrowFriendlyDip — IsaacRepentance::Entity_Player::ThrowFriendlyDip(int, KAGE::Math::Vector2 const&, KAGE::Math::Vector2 const&)
inline constexpr uintptr_t kApi200EntityPlayerThrowFriendlyDipOffset=0x2FEA84;
inline constexpr std::array<u8,16> kApi200EntityPlayerThrowFriendlyDipExpectedBytes={0xe8,0x03,0x00,0xaa,0xe0,0x03,0x01,0x2a,0xe1,0x03,0x02,0xaa,0xe2,0x03,0x08,0xaa};
// EntityPlayer:TriggerBookOfVirtues — IsaacRepentance::Entity_Player::TriggerBookOfVirtues(IsaacRepentance::eCollectibleType, int)
inline constexpr uintptr_t kApi200EntityPlayerTriggerBookOfVirtuesOffset=0x31BF84;
inline constexpr std::array<u8,16> kApi200EntityPlayerTriggerBookOfVirtuesExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// EntityPlayer:TryHoldEntity — IsaacRepentance::Entity_Player::TryHoldEntity(IsaacRepentance::Entity*)
inline constexpr uintptr_t kApi200EntityPlayerTryHoldEntityOffset=0x2DC2D0;
inline constexpr std::array<u8,16> kApi200EntityPlayerTryHoldEntityExpectedBytes={0xff,0x83,0x06,0xd1,0xfd,0x7b,0x16,0xa9,0xfd,0x83,0x05,0x91,0xfc,0xbb,0x00,0xf9};
// EntityPlayer:TryHoldTrinket — IsaacRepentance::Entity_Player::TryHoldTrinket(IsaacRepentance::eTrinketType)
inline constexpr uintptr_t kApi200EntityPlayerTryHoldTrinketOffset=0x2A1EE8;
inline constexpr std::array<u8,16> kApi200EntityPlayerTryHoldTrinketExpectedBytes={0xfd,0x7b,0xbb,0xa9,0xfa,0x67,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
// EntityPlayer:UpdateCanShoot — IsaacRepentance::Entity_Player::update_canshoot()
inline constexpr uintptr_t kApi200EntityPlayerUpdateCanShootOffset=0x27A8B0;
inline constexpr std::array<u8,16> kApi200EntityPlayerUpdateCanShootExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// EntityPlayer:UsePoopSpell — IsaacRepentance::Entity_Player::UsePoopSpell(IsaacRepentance::Entity_Player::ePoopSpellType)
inline constexpr uintptr_t kApi200EntityPlayerUsePoopSpellOffset=0x2B8140;
inline constexpr std::array<u8,16> kApi200EntityPlayerUsePoopSpellExpectedBytes={0xff,0x03,0x02,0xd1,0xe8,0x23,0x00,0xfd,0xf7,0x2f,0x00,0xf9,0xfd,0xfb,0x04,0xa9};
// EntityTear:SetDeadEyeIntensity — IsaacRepentance::Entity_Tear::SetDeadEyeIntensity(float)
inline constexpr uintptr_t kApi200EntityTearSetDeadEyeIntensityOffset=0x341524;
inline constexpr std::array<u8,16> kApi200EntityTearSetDeadEyeIntensityExpectedBytes={0xff,0x83,0x01,0xd1,0xe8,0x1b,0x00,0xfd,0xf5,0x27,0x00,0xf9,0xfd,0xfb,0x03,0xa9};
// Game:AddEncounteredBoss — IsaacRepentance::Game::AddEncounteredBoss(IsaacRepentance::eEntityType, unsigned int)
inline constexpr uintptr_t kApi200GameAddEncounteredBossOffset=0x359B98;
inline constexpr std::array<u8,16> kApi200GameAddEncounteredBossExpectedBytes={0xfd,0x7b,0xbb,0xa9,0xfa,0x67,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
// Game:ButterBeanFart — IsaacRepentance::Game::ButterBeanFart(KAGE::Math::Vector2 const&, float, IsaacRepentance::Entity*, bool, bool)
inline constexpr uintptr_t kApi200GameButterBeanFartOffset=0x3591DC;
inline constexpr std::array<u8,16> kApi200GameButterBeanFartExpectedBytes={0xff,0x03,0x05,0xd1,0xef,0x3b,0x0a,0x6d,0xed,0x33,0x0b,0x6d,0xeb,0x2b,0x0c,0x6d};
// Game:DonateAngel — IsaacRepentance::Game::DonateAngel(int)
inline constexpr uintptr_t kApi200GameDonateAngelOffset=0x35AFB4;
inline constexpr std::array<u8,16> kApi200GameDonateAngelExpectedBytes={0x08,0x4f,0x9f,0x52,0xc8,0x04,0xa0,0x72,0x09,0x68,0x68,0xb8,0x29,0x01,0x01,0x0b};
// Game:DonateGreed — IsaacRepentance::Game::DonateGreed(int)
inline constexpr uintptr_t kApi200GameDonateGreedOffset=0x35AF9C;
inline constexpr std::array<u8,16> kApi200GameDonateGreedExpectedBytes={0x88,0x4e,0x9f,0x52,0xc8,0x04,0xa0,0x72,0x09,0x68,0x68,0xb8,0x29,0x01,0x01,0x0b};
// Game:End — IsaacRepentance::Game::End(IsaacRepentance::eEnding)
inline constexpr uintptr_t kApi200GameEndOffset=0x350DE4;
inline constexpr std::array<u8,16> kApi200GameEndExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// Game:Fadein — IsaacRepentance::Game::Fadein(float)
inline constexpr uintptr_t kApi200GameFadeinOffset=0x34E490;
inline constexpr std::array<u8,16> kApi200GameFadeinExpectedBytes={0x08,0x0b,0x80,0x52,0xe8,0x05,0xa0,0x72,0x02,0x10,0x2e,0x1e,0x89,0xb5,0x98,0x52};
// Game:Fadeout — IsaacRepentance::Game::Fadeout(float, IsaacRepentance::Game::eFadeoutTarget)
inline constexpr uintptr_t kApi200GameFadeoutOffset=0x34E4DC;
inline constexpr std::array<u8,16> kApi200GameFadeoutExpectedBytes={0x88,0x52,0x9f,0x52,0xc8,0x04,0xa0,0x72,0x08,0x00,0x08,0x8b,0x01,0x01,0x40,0xbd};
// Game:FinishChallenge — IsaacRepentance::Game::FinishChallenge()
inline constexpr uintptr_t kApi200GameFinishChallengeOffset=0x35B360;
inline constexpr std::array<u8,16> kApi200GameFinishChallengeExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Game:GetGreedWavesNum — IsaacRepentance::Game::GetGreedWavesNum() const
inline constexpr uintptr_t kApi200GameGetGreedWavesNumOffset=0x359DFC;
inline constexpr std::array<u8,16> kApi200GameGetGreedWavesNumExpectedBytes={0x08,0x05,0x80,0x52,0xe8,0x05,0xa0,0x72,0x08,0x68,0x68,0xb8,0x1f,0x0d,0x00,0x71};
// Game:GetNearestPlayer — IsaacRepentance::Game::GetNearestPlayer(KAGE::Math::Vector2 const&)
inline constexpr uintptr_t kApi200GameGetNearestPlayerOffset=0x35A270;
inline constexpr std::array<u8,16> kApi200GameGetNearestPlayerExpectedBytes={0xff,0xc3,0x01,0xd1,0xe8,0x0b,0x00,0xfd,0xfb,0x17,0x00,0xf9,0xfd,0xfb,0x01,0xa9};
// Game:GetRandomPlayer — IsaacRepentance::Game::GetRandomPlayer(KAGE::Math::Vector2 const&, float)
inline constexpr uintptr_t kApi200GameGetRandomPlayerOffset=0x35A0CC;
inline constexpr std::array<u8,16> kApi200GameGetRandomPlayerExpectedBytes={0xff,0xc3,0x01,0xd1,0xe8,0x13,0x00,0xfd,0xf9,0x1f,0x00,0xf9,0xfd,0xfb,0x02,0xa9};
// Game:HasEncounteredBoss — IsaacRepentance::Game::HasEncounteredBoss(IsaacRepentance::eEntityType, unsigned int)
inline constexpr uintptr_t kApi200GameHasEncounteredBossOffset=0x359D1C;
inline constexpr std::array<u8,16> kApi200GameHasEncounteredBossExpectedBytes={0x08,0x07,0x80,0x52,0xe8,0x05,0xa0,0x72,0x08,0x00,0x08,0x8b,0x08,0x25,0x40,0xa9};
// Game:MakeShockwave — IsaacRepentance::Game::MakeShockwave(KAGE::Math::Vector2 const&, float, float, int)
inline constexpr uintptr_t kApi200GameMakeShockwaveOffset=0x359F90;
inline constexpr std::array<u8,16> kApi200GameMakeShockwaveExpectedBytes={0xff,0x83,0x01,0xd1,0xe9,0x23,0x02,0x6d,0xf5,0x23,0x00,0xf9,0xfd,0x7b,0x03,0xa9};
// Game:NextVictoryLap — IsaacRepentance::Game::NextVictoryLap()
inline constexpr uintptr_t kApi200GameNextVictoryLapOffset=0x34FE00;
inline constexpr std::array<u8,16> kApi200GameNextVictoryLapExpectedBytes={0xff,0x83,0x02,0xd1,0xfd,0x7b,0x04,0xa9,0xfd,0x03,0x01,0x91,0xfb,0x2b,0x00,0xf9};
// Game:RerollEnemy — IsaacRepentance::Game::RerollEnemy(IsaacRepentance::Entity*, bool)
inline constexpr uintptr_t kApi200GameRerollEnemyOffset=0x35B448;
inline constexpr std::array<u8,16> kApi200GameRerollEnemyExpectedBytes={0xff,0x83,0x03,0xd1,0xea,0x33,0x00,0xfd,0xe9,0x23,0x07,0x6d,0xfd,0x7b,0x08,0xa9};
// Game:RerollLevelCollectibles — IsaacRepentance::Game::RerollLevelCollectibles()
inline constexpr uintptr_t kApi200GameRerollLevelCollectiblesOffset=0x35AFCC;
inline constexpr std::array<u8,16> kApi200GameRerollLevelCollectiblesExpectedBytes={0xfd,0x7b,0xba,0xa9,0xfc,0x6f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xfa,0x67,0x02,0xa9};
// Game:RerollLevelPickups — IsaacRepentance::Game::RerollLevelPickups(unsigned int)
inline constexpr uintptr_t kApi200GameRerollLevelPickupsOffset=0x35B0E8;
inline constexpr std::array<u8,16> kApi200GameRerollLevelPickupsExpectedBytes={0xff,0x43,0x02,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xfc,0x6f,0x04,0xa9};
// Game:StartStageTransition — IsaacRepentance::Game::StartStageTransition(bool, IsaacRepentance::StageTransition::eAnimation, IsaacRepentance::Entity_Player*)
inline constexpr uintptr_t kApi200GameStartStageTransitionOffset=0x352200;
inline constexpr std::array<u8,16> kApi200GameStartStageTransitionExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};
// GridEntityDoor:TryBlowOpen — IsaacRepentance::GridEntity_Door::TryBlowOpen(bool, IsaacRepentance::Entity*)
inline constexpr uintptr_t kApi200GridEntityDoorTryBlowOpenOffset=0x384700;
inline constexpr std::array<u8,16> kApi200GridEntityDoorTryBlowOpenExpectedBytes={0xff,0x43,0x02,0xd1,0xe9,0x23,0x04,0x6d,0xf7,0x33,0x00,0xf9,0xfd,0x7b,0x05,0xa9};
// GridEntityDoor:TryUnlock — IsaacRepentance::GridEntity_Door::TryUnlock(IsaacRepentance::Entity_Player*, bool)
inline constexpr uintptr_t kApi200GridEntityDoorTryUnlockOffset=0x384FE4;
inline constexpr std::array<u8,16> kApi200GridEntityDoorTryUnlockExpectedBytes={0xff,0x83,0x03,0xd1,0xeb,0x2b,0x06,0x6d,0xe9,0x23,0x07,0x6d,0xfd,0x7b,0x08,0xa9};
// GridEntityPit:MakeBridge — IsaacRepentance::GridEntity_Pit::MakeBridge(IsaacRepentance::GridEntity*)
inline constexpr uintptr_t kApi200GridEntityPitMakeBridgeOffset=0x38824C;
inline constexpr std::array<u8,16> kApi200GridEntityPitMakeBridgeExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0x10,0x40,0xb9};
// GridEntityPit:SetLadder — IsaacRepentance::GridEntity_Pit::SetLadder(bool)
inline constexpr uintptr_t kApi200GridEntityPitSetLadderOffset=0x38966C;
inline constexpr std::array<u8,16> kApi200GridEntityPitSetLadderExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x28,0x00,0x00,0x12};
// GridEntityPit:UpdateCollision — IsaacRepentance::GridEntity_Pit::UpdateCollision()
inline constexpr uintptr_t kApi200GridEntityPitUpdateCollisionOffset=0x389548;
inline constexpr std::array<u8,16> kApi200GridEntityPitUpdateCollisionExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x14,0x39,0x00,0xf0};
// GridEntityPoop:RespawnRedPoop — IsaacRepentance::GridEntity_Poop::RespawnRedPoop()
inline constexpr uintptr_t kApi200GridEntityPoopRespawnRedPoopOffset=0x38CA58;
inline constexpr std::array<u8,16> kApi200GridEntityPoopRespawnRedPoopExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x08,0x0c,0x40,0xb9};
// GridEntityPressurePlate:Reward — IsaacRepentance::GridEntity_PressurePlate::reward()
inline constexpr uintptr_t kApi200GridEntityPressurePlateRewardOffset=0x38D3A0;
inline constexpr std::array<u8,16> kApi200GridEntityPressurePlateRewardExpectedBytes={0xff,0xc3,0x03,0xd1,0xe9,0x23,0x08,0x6d,0xfd,0x7b,0x09,0xa9,0xfd,0x43,0x02,0x91};
// HUD:AssignPlayerHUDs — IsaacRepentance::HUD::AssignPlayerHUDs()
inline constexpr uintptr_t kApi200HUDAssignPlayerHUDsOffset=0x3AFC98;
inline constexpr std::array<u8,16> kApi200HUDAssignPlayerHUDsExpectedBytes={0xfd,0x7b,0xba,0xa9,0xfc,0x6f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xfa,0x67,0x02,0xa9};
// HUD:FlashChargeBar — IsaacRepentance::HUD::FlashChargeBar(IsaacRepentance::Entity_Player*, int)
inline constexpr uintptr_t kApi200HUDFlashChargeBarOffset=0x3AA960;
inline constexpr std::array<u8,16> kApi200HUDFlashChargeBarExpectedBytes={0x08,0x00,0x40,0xf9,0x1f,0x01,0x01,0xeb,0x80,0x04,0x00,0x54,0x08,0x84,0x44,0xf9};
// HUD:InvalidateActiveItem — IsaacRepentance::HUD::InvalidateActiveItem(IsaacRepentance::Entity_Player*, int)
inline constexpr uintptr_t kApi200HUDInvalidateActiveItemOffset=0x3AAABC;
inline constexpr std::array<u8,16> kApi200HUDInvalidateActiveItemExpectedBytes={0x08,0x00,0x40,0xf9,0x1f,0x01,0x01,0xeb,0x60,0x03,0x00,0x54,0x08,0x84,0x44,0xf9};
// HUD:InvalidateCraftingItem — IsaacRepentance::HUD::InvalidateCraftingItem(IsaacRepentance::Entity_Player*)
inline constexpr uintptr_t kApi200HUDInvalidateCraftingItemOffset=0x3AABA8;
inline constexpr std::array<u8,16> kApi200HUDInvalidateCraftingItemExpectedBytes={0x0a,0x00,0x40,0xf9,0x41,0x03,0x00,0xb4,0x5f,0x01,0x01,0xeb,0x80,0x09,0x00,0x54};
// HUD:PostUpdate — IsaacRepentance::HUD::PostUpdate()
inline constexpr uintptr_t kApi200HUDPostUpdateOffset=0x3AA4CC;
inline constexpr std::array<u8,16> kApi200HUDPostUpdateExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// HUD:Update — IsaacRepentance::HUD::Update()
inline constexpr uintptr_t kApi200HUDUpdateOffset=0x3AA378;
inline constexpr std::array<u8,16> kApi200HUDUpdateExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0x09,0x80,0x8a,0x52};
// ItemConfig:GetNullItem — IsaacRepentance::ItemConfig::GetNullItem(int) const
inline constexpr uintptr_t kApi200ItemConfigGetNullItemOffset=0x3C0CC4;
inline constexpr std::array<u8,16> kApi200ItemConfigGetNullItemExpectedBytes={0x01,0x01,0xf8,0x37,0x08,0x24,0x43,0xa9,0x29,0x01,0x08,0xcb,0x29,0xfd,0x43,0xd3};
// Level:ForceHorsemanBoss — IsaacRepentance::Level::ForceHorsemanBoss(unsigned int)
inline constexpr uintptr_t kApi200LevelForceHorsemanBossOffset=0x3E5D78;
inline constexpr std::array<u8,16> kApi200LevelForceHorsemanBossExpectedBytes={0xff,0x43,0x02,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xfc,0x6f,0x04,0xa9};
// Level:GetEnterPosition — IsaacRepentance::Level::GetEnterPosition() const
inline constexpr uintptr_t kApi200LevelGetEnterPositionOffset=0x3E56F4;
inline constexpr std::array<u8,16> kApi200LevelGetEnterPositionExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x08,0xab,0x82,0x52};
// Level:GetNonCompleteRoomIndex — IsaacRepentance::Level::GetNonCompleteRoomIndex() const
inline constexpr uintptr_t kApi200LevelGetNonCompleteRoomIndexOffset=0x3DBF98;
inline constexpr std::array<u8,16> kApi200LevelGetNonCompleteRoomIndexExpectedBytes={0xff,0x03,0x02,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xfc,0x6f,0x03,0xa9};
// PathFinder:EvadeTarget — IsaacRepentance::NPCAI_Pathfinder::EvadeTarget(KAGE::Math::Vector2 const&, bool)
inline constexpr uintptr_t kApi200PathFinderEvadeTargetOffset=0x42D840;
inline constexpr std::array<u8,16> kApi200PathFinderEvadeTargetExpectedBytes={0xff,0xc3,0x03,0xd1,0xef,0x3b,0x05,0x6d,0xed,0x33,0x06,0x6d,0xeb,0x2b,0x07,0x6d};
// PathFinder:GetGridIndex — IsaacRepentance::NPCAI_Pathfinder::GetGridIndex() const
inline constexpr uintptr_t kApi200PathFinderGetGridIndexOffset=0x42F6C4;
inline constexpr std::array<u8,16> kApi200PathFinderGetGridIndexExpectedBytes={0x00,0x24,0x40,0xb9,0xc0,0x03,0x5f,0xd6,0xfd,0x7b,0xba,0xa9,0xfc,0x6f,0x01,0xa9};
// PathFinder:MoveRandomly — IsaacRepentance::NPCAI_Pathfinder::MoveRandomly(bool)
inline constexpr uintptr_t kApi200PathFinderMoveRandomlyOffset=0x42D218;
inline constexpr std::array<u8,16> kApi200PathFinderMoveRandomlyExpectedBytes={0xff,0x83,0x01,0xd1,0xe8,0x1b,0x00,0xfd,0xfd,0x7b,0x04,0xa9,0xfd,0x03,0x01,0x91};
// PathFinder:MoveRandomlyAxisAligned — IsaacRepentance::NPCAI_Pathfinder::MoveRandomlyAxisAligned(float, bool)
inline constexpr uintptr_t kApi200PathFinderMoveRandomlyAxisAlignedOffset=0x42E044;
inline constexpr std::array<u8,16> kApi200PathFinderMoveRandomlyAxisAlignedExpectedBytes={0xff,0x43,0x04,0xd1,0xea,0x4b,0x00,0xfd,0xe9,0x23,0x0a,0x6d,0xfd,0x7b,0x0b,0xa9};
// PathFinder:MoveRandomlyBoss — IsaacRepentance::NPCAI_Pathfinder::MoveRandomlyBoss(bool)
inline constexpr uintptr_t kApi200PathFinderMoveRandomlyBossOffset=0x42EEE0;
inline constexpr std::array<u8,16> kApi200PathFinderMoveRandomlyBossExpectedBytes={0xff,0x03,0x02,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xfa,0x67,0x04,0xa9};
// PathFinder:Reset — IsaacRepentance::NPCAI_Pathfinder::Reset()
inline constexpr uintptr_t kApi200PathFinderResetOffset=0x42B8A8;
inline constexpr std::array<u8,16> kApi200PathFinderResetExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// PathFinder:ResetMovementTarget — IsaacRepentance::NPCAI_Pathfinder::ResetMovementTarget()
inline constexpr uintptr_t kApi200PathFinderResetMovementTargetOffset=0x42F63C;
inline constexpr std::array<u8,16> kApi200PathFinderResetMovementTargetExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x33,0x00,0xb0};
// PathFinder:UpdateGridIndex — IsaacRepentance::NPCAI_Pathfinder::UpdateGridIndex()
inline constexpr uintptr_t kApi200PathFinderUpdateGridIndexOffset=0x42F674;
inline constexpr std::array<u8,16> kApi200PathFinderUpdateGridIndexExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xe8,0x33,0x00,0xb0};
// Room:CheckLine — IsaacRepentance::Room::CheckLine(KAGE::Math::Vector2 const&, KAGE::Math::Vector2 const&, IsaacRepentance::Room::eLinecheckMode, int, bool, bool, KAGE::Math::Vector2*) const
inline constexpr uintptr_t kApi200RoomCheckLineOffset=0x45A32C;
inline constexpr std::array<u8,16> kApi200RoomCheckLineExpectedBytes={0xff,0x43,0x04,0xd1,0xec,0x43,0x00,0xfd,0xeb,0x2b,0x09,0x6d,0xe9,0x23,0x0a,0x6d};
// Room:GetClampedGridIndex — IsaacRepentance::Room::GetClampedGridIndex(KAGE::Math::Vector2 const&) const
inline constexpr uintptr_t kApi200RoomGetClampedGridIndexOffset=0x484234;
inline constexpr std::array<u8,16> kApi200RoomGetClampedGridIndexExpectedBytes={0x08,0x44,0xb8,0x52,0x00,0x01,0x27,0x1e,0x08,0x44,0xa8,0x52,0x21,0x08,0x40,0x2d};
// Room:GetLaserTarget — IsaacRepentance::Room::GetLaserTarget(KAGE::Math::Vector2 const&, KAGE::Math::Vector2 const&) const
inline constexpr uintptr_t kApi200RoomGetLaserTargetOffset=0x45A2A0;
inline constexpr std::array<u8,16> kApi200RoomGetLaserTargetExpectedBytes={0xff,0x43,0x01,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xf5,0x1b,0x00,0xf9};
// Room:GetSeededCollectible — IsaacRepentance::Room::GetSeededCollectible(unsigned int, bool)
inline constexpr uintptr_t kApi200RoomGetSeededCollectibleOffset=0x4527EC;
inline constexpr std::array<u8,16> kApi200RoomGetSeededCollectibleExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Room:MamaMegaExplosion — IsaacRepentance::Room::MamaMegaExplosion(KAGE::Math::Vector2 const&)
inline constexpr uintptr_t kApi200RoomMamaMegaExplosionOffset=0x471AD4;
inline constexpr std::array<u8,16> kApi200RoomMamaMegaExplosionExpectedBytes={0xff,0xc3,0x01,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xf8,0x5f,0x04,0xa9};
// Room:TryMakeBridge — IsaacRepentance::Room::TryMakeBridge(IsaacRepentance::GridEntity*, IsaacRepentance::GridEntity*)
inline constexpr uintptr_t kApi200RoomTryMakeBridgeOffset=0x467214;
inline constexpr std::array<u8,16> kApi200RoomTryMakeBridgeExpectedBytes={0xff,0x83,0x01,0xd1,0xe9,0x23,0x01,0x6d,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91};
// Room:TrySpawnDevilRoomDoor — IsaacRepentance::Room::TrySpawnDevilRoomDoor(bool, bool)
inline constexpr uintptr_t kApi200RoomTrySpawnDevilRoomDoorOffset=0x465510;
inline constexpr std::array<u8,16> kApi200RoomTrySpawnDevilRoomDoorExpectedBytes={0xff,0x03,0x05,0xd1,0xed,0x33,0x0b,0x6d,0xeb,0x2b,0x0c,0x6d,0xe9,0x23,0x0d,0x6d};
// Room:TrySpawnSecretShop — IsaacRepentance::Room::TrySpawnSecretShop(bool)
inline constexpr uintptr_t kApi200RoomTrySpawnSecretShopOffset=0x465384;
inline constexpr std::array<u8,16> kApi200RoomTrySpawnSecretShopExpectedBytes={0xff,0xc3,0x00,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Room:TrySpawnSpecialQuestDoor — IsaacRepentance::Room::TrySpawnSpecialQuestDoor()
inline constexpr uintptr_t kApi200RoomTrySpawnSpecialQuestDoorOffset=0x4625DC;
inline constexpr std::array<u8,16> kApi200RoomTrySpawnSpecialQuestDoorExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
// Seeds:CanAddSeedEffect — IsaacRepentance::Seeds::CanAddSeedEffect(IsaacRepentance::eSeedEffect)
inline constexpr uintptr_t kApi200SeedsCanAddSeedEffectOffset=0x49EE8C;
inline constexpr std::array<u8,16> kApi200SeedsCanAddSeedEffectExpectedBytes={0xff,0x43,0x01,0xd1,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91,0xf5,0x1b,0x00,0xf9};
// Seeds:CountUnlockedSeedEffects — IsaacRepentance::Seeds::CountUnlockedSeedEffects()
inline constexpr uintptr_t kApi200SeedsCountUnlockedSeedEffectsOffset=0x49EBC4;
inline constexpr std::array<u8,16> kApi200SeedsCountUnlockedSeedEffectsExpectedBytes={0x69,0x30,0x00,0xd0,0x29,0x25,0x43,0xf9,0x29,0x01,0x40,0xf9,0xe8,0x03,0x1f,0xaa};
// Seeds:InitSeedInfo — IsaacRepentance::Seeds::InitSeedInfo()
inline constexpr uintptr_t kApi200SeedsInitSeedInfoOffset=0x49CDB4;
inline constexpr std::array<u8,16> kApi200SeedsInitSeedInfoExpectedBytes={0xff,0x03,0x03,0xd1,0xfd,0x7b,0x06,0xa9,0xfd,0x83,0x01,0x91,0xfc,0x6f,0x07,0xa9};
// Seeds:RemoveBlockingSeedEffects — IsaacRepentance::Seeds::RemoveBlockingSeedEffects(IsaacRepentance::eSeedEffect)
inline constexpr uintptr_t kApi200SeedsRemoveBlockingSeedEffectsOffset=0x4A0C84;
inline constexpr std::array<u8,16> kApi200SeedsRemoveBlockingSeedEffectsExpectedBytes={0xfd,0x7b,0xbb,0xa9,0xf9,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
// Seeds:Reset — IsaacRepentance::Seeds::Reset()
inline constexpr uintptr_t kApi200SeedsResetOffset=0x49CC34;
inline constexpr std::array<u8,16> kApi200SeedsResetExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf3,0x03,0x00,0xaa};
// Seeds:Restart — IsaacRepentance::Seeds::Restart(IsaacRepentance::eChallenge)
inline constexpr uintptr_t kApi200SeedsRestartOffset=0x4A120C;
inline constexpr std::array<u8,16> kApi200SeedsRestartExpectedBytes={0xe8,0x03,0x01,0x2a,0xe1,0x03,0x1f,0x2a,0x88,0x00,0x00,0x35,0x08,0x00,0x40,0x39};
// Sprite:SetOverlayAnimation — IsaacRepentance::ANM2::SetOverlayAnimation(char const*, bool)
inline constexpr uintptr_t kApi200SpriteSetOverlayAnimationOffset=0xAAF0;
inline constexpr std::array<u8,16> kApi200SpriteSetOverlayAnimationExpectedBytes={0xfd,0x7b,0xbc,0xa9,0xf8,0x5f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf6,0x57,0x02,0xa9};

// 第三批100：字段/原函数按完整PC包装、NS状态写者与公开bootstrap核定；全部Experimental。
inline constexpr std::uintptr_t kApi300EntityPlayerCanShootFieldOffset=0x1c9d;
inline constexpr std::uintptr_t kApi300EntityPlayerCanTurnHeadOffset=0x2bbc98;
inline constexpr std::array<u8,16> kApi300EntityPlayerCanTurnHeadExpectedBytes={0x08,0xb4,0x56,0xb9,0x00,0x7d,0x1f,0x53,0xc0,0x03,0x5f,0xd6,0x08,0xac,0x4b,0xf9};
inline constexpr std::uintptr_t kApi300EntityPlayerRenderBodyOffset=0x2da2e0;
inline constexpr std::array<u8,16> kApi300EntityPlayerRenderBodyExpectedBytes={0xff,0x83,0x01,0xd1,0xe8,0x0b,0x00,0xfd,0xfd,0x7b,0x02,0xa9,0xfd,0x83,0x00,0x91};
inline constexpr std::uintptr_t kApi300EntityPlayerGetActiveWeaponEntityOffset=0x2bbc74;
inline constexpr std::array<u8,16> kApi300EntityPlayerGetActiveWeaponEntityExpectedBytes={0xe8,0x03,0x00,0xaa,0x00,0xac,0x4b,0xf9,0x60,0x00,0x00,0xb5,0x00,0xb1,0x4b,0xf9};
inline constexpr std::uintptr_t kApi300EntityPlayerGetBatteryChargeFieldOffset=0x196c;
inline constexpr std::uintptr_t kApi300EntityPlayerGetBodyColorFieldOffset=0x1d10;
inline constexpr std::uintptr_t kApi300EntityPlayerGetHeadColorFieldOffset=0x1d0c;
inline constexpr std::uintptr_t kApi300EntityPlayerGetItemStateFieldOffset=0x19d4;
inline constexpr std::uintptr_t kApi300EntityPlayerGetJarFliesFieldOffset=0x16d0;
inline constexpr std::uintptr_t kApi300EntityPlayerGetLastActionTriggersFieldOffset=0x16f0;
inline constexpr std::uintptr_t kApi300EntityPlayerGetLastDamageFlagsFieldOffset=0x1aa0;
inline constexpr std::uintptr_t kApi300EntityPlayerGetLastDirectionFieldOffset=0x1a10;
inline constexpr std::uintptr_t kApi300EntityPlayerGetMovementVectorFieldOffset=0x1a18;
inline constexpr std::uintptr_t kApi300EntityPlayerGetNumBlueFliesFieldOffset=0x16e4;
inline constexpr std::uintptr_t kApi300EntityPlayerGetNumBlueSpidersFieldOffset=0x16e8;
inline constexpr std::uintptr_t kApi300EntityPlayerGetNumGigaBombsFieldOffset=0x24a4;
inline constexpr std::uintptr_t kApi300EntityPlayerGetRecentMovementVectorFieldOffset=0x1a28;
inline constexpr std::uintptr_t kApi300EntityPlayerGetSmoothBodyRotationFieldOffset=0x20e0;
inline constexpr std::uintptr_t kApi300EntityPlayerGetTearPoisonDamageFieldOffset=0x1960;
inline constexpr std::uintptr_t kApi300EntityPlayerGetTearRangeModifierFieldOffset=0x1914;
inline constexpr std::uintptr_t kApi300EntityPlayerGetTotalDamageTakenFieldOffset=0x1aac;
inline constexpr std::uintptr_t kApi300EntityPlayerGetTractorBeamFieldOffset=0x17c8;
inline constexpr std::uintptr_t kApi300EntityPlayerGetVelocityBeforeUpdateFieldOffset=0x1a34;
inline constexpr std::uintptr_t kApi300EntityPlayerHasCurseMistEffectFieldOffset=0x27e0;
inline constexpr std::uintptr_t kApi300EntityPlayerIsItemQueueEmptyFieldOffset=0x1c38;
inline constexpr std::uintptr_t kApi300EntityPlayerIsP2AppearingFieldOffset=0x1734;
inline constexpr std::uintptr_t kApi300EntityPlayerSetBloodChargeFieldOffset=0x247c;
inline constexpr std::uintptr_t kApi300EntityPlayerSetSoulChargeFieldOffset=0x2478;
inline constexpr std::uintptr_t kApi300EntityPlayerRenderHeadOffset=0x2da690;
inline constexpr std::array<u8,16> kApi300EntityPlayerRenderHeadExpectedBytes={0xfd,0x7b,0xbb,0xa9,0xf9,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf8,0x5f,0x02,0xa9};
inline constexpr std::uintptr_t kApi300EntityPlayerAddControlsCooldownFieldOffset=0x404;
inline constexpr std::uintptr_t kApi300EntityPlayerAreControlsEnabledFieldOffset=0x400;
inline constexpr std::uintptr_t kApi300GameAddPixelationFieldOffset=0x2f0050;
inline constexpr std::uintptr_t kApi300GameAddStageWithoutDamageFieldOffset=0x26fa6c;
inline constexpr std::uintptr_t kApi300GameAddStageWithoutHeartsPickedFieldOffset=0x26fa68;
inline constexpr std::uintptr_t kApi300GameAddTreasureRoomsVisitedFieldOffset=0x26fa60;
inline constexpr std::uintptr_t kApi300GameClearDonationModAngelFieldOffset=0x26fa78;
inline constexpr std::uintptr_t kApi300GameClearDonationModGreedFieldOffset=0x26fa74;
inline constexpr std::uintptr_t kApi300GameClearStagesWithoutDamageFieldOffset=0x26fa6c;
inline constexpr std::uintptr_t kApi300GameGetDarknessModifierFieldOffset=0x24f9bc;
inline constexpr std::uintptr_t kApi300GameGetDevilRoomDealsFieldOffset=0x26fa70;
inline constexpr std::uintptr_t kApi300GameGetDonationModAngelFieldOffset=0x26fa78;
inline constexpr std::uintptr_t kApi300GameGetDonationModGreedFieldOffset=0x26fa74;
inline constexpr std::uintptr_t kApi300EntityKnifeGetRenderZOffset=0xf26fc;
inline constexpr std::array<u8,16> kApi300EntityKnifeGetRenderZExpectedBytes={0x00,0x14,0x43,0xbd,0x08,0x59,0xa8,0x52,0x01,0x24,0x44,0xbd,0x00,0x28,0x21,0x1e};
inline constexpr std::uintptr_t kApi300EntityLaserGetRenderZOffset=0xf5f4c;
inline constexpr std::array<u8,16> kApi300EntityLaserGetRenderZExpectedBytes={0x00,0x14,0x43,0xbd,0x08,0x59,0xa8,0x52,0x01,0x2c,0x43,0xbd,0x00,0x28,0x21,0x1e};
inline constexpr std::uintptr_t kApi300EntityNPCGetAliveEnemyCountOffset=0x122768;
inline constexpr std::array<u8,16> kApi300EntityNPCGetAliveEnemyCountExpectedBytes={0xfd,0x7b,0xbd,0xa9,0xf5,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
inline constexpr std::uintptr_t kApi300GameGetNumEncounteredBossesFieldOffset=0x2f0038;
inline constexpr std::uintptr_t kApi300GameGetStagesWithoutDamageFieldOffset=0x26fa6c;
inline constexpr std::uintptr_t kApi300GameGetStagesWithoutHeartsPickedFieldOffset=0x26fa68;
inline constexpr std::uintptr_t kApi300GameGetTargetDarknessFieldOffset=0x24f9c0;
inline constexpr std::uintptr_t kApi300GameGetTreasureRoomVisitCountFieldOffset=0x26fa60;
inline constexpr std::uintptr_t kApi300GameHasHallucinationFieldOffset=0x26fa38;
inline constexpr std::uintptr_t kApi300GameSetLastDevilRoomStageFieldOffset=0x26fa5c;
inline constexpr std::uintptr_t kApi300GameSetLastLevelWithDamageFieldOffset=0x2f002c;
inline constexpr std::uintptr_t kApi300GameSetLastLevelWithoutHalfHpFieldOffset=0x2f0020;
inline constexpr std::uintptr_t kApi300GameGetScreenShakeCountdownFieldOffset=0x24f9ac;
inline constexpr std::uintptr_t kApi300EntityTearClearTearFlagsFieldOffset=0x418;
inline constexpr std::uintptr_t kApi300EntityTearHasTearFlagsFieldOffset=0x418;
inline constexpr std::uintptr_t kApi300RoomGetGridPathFromPosFieldOffset=0xe98;
inline constexpr std::uintptr_t kApi300EntityBombClearTearFlagsFieldOffset=0x428;
inline constexpr std::uintptr_t kApi300RoomGetRedHeartDamageFieldOffset=0x1940;
inline constexpr std::uintptr_t kApi300RoomGetSecondBossIDFieldOffset=0x1fc4;
inline constexpr std::uintptr_t kApi300EntityBombHasTearFlagsFieldOffset=0x428;
inline constexpr std::uintptr_t kApi300RoomGetWaterCurrentFieldOffset=0x7c78;
inline constexpr std::uintptr_t kApi300EntityKnifeClearTearFlagsFieldOffset=0x400;
inline constexpr std::uintptr_t kApi300RoomHasTriggerPressurePlatesFieldOffset=0x78ed;
inline constexpr std::uintptr_t kApi300EntityLaserClearTearFlagsFieldOffset=0x418;
inline constexpr std::uintptr_t kApi300RoomIsInitializedFieldOffset=0x0;
inline constexpr std::uintptr_t kApi300RoomIsSacrificeDoneFieldOffset=0x8;
inline constexpr std::uintptr_t kApi300RoomKeepDoorsClosedFieldOffset=0x1918;
inline constexpr std::uintptr_t kApi300RoomSetAmbushDoneFieldOffset=0x8;
inline constexpr std::uintptr_t kApi300RoomSetCardAgainstHumanityFieldOffset=0x1920;
inline constexpr std::uintptr_t kApi300EntityLaserHasTearFlagsFieldOffset=0x418;
inline constexpr std::uintptr_t kApi300RoomSetRedHeartDamageFieldOffset=0x1940;
inline constexpr std::uintptr_t kApi300RoomSetSacrificeDoneFieldOffset=0x8;
inline constexpr std::uintptr_t kApi300EntityKnifeHasTearFlagsFieldOffset=0x400;
inline constexpr std::uintptr_t kApi300RoomStopRainFieldOffset=0x7c74;
inline constexpr std::uintptr_t kApi300PathFinderGetEvadeMovementCountdownFieldOffset=0x740;
inline constexpr std::uintptr_t kApi300PathFinderHasDirectPathFieldOffset=0x730;
inline constexpr std::uintptr_t kApi300PathFinderSetCanCrushRocksFieldOffset=0x73c;
inline constexpr std::uintptr_t kApi300SeedsCountSeedEffectsFieldOffset=0x68;
inline constexpr std::uintptr_t kApi300SeedsClearSeedEffectsFieldOffset=0x58;
inline constexpr std::uintptr_t kApi300SeedsClearStartSeedFieldOffset=0x4;
inline constexpr std::uintptr_t kApi300SeedsGetPlayerInitSeedFieldOffset=0x50;
inline constexpr std::uintptr_t kApi300SeedsGetStartSeedStringFieldOffset=0x4a102c;
inline constexpr std::uintptr_t kApi300SeedsIsInitializedFieldOffset=0x4;
inline constexpr std::uintptr_t kApi300SeedsIsSeedComboBannedFieldOffset=0xabd828;
inline constexpr std::uintptr_t kApi300LevelAddAngelRoomChanceFieldOffset=0x21538;
inline constexpr std::uintptr_t kApi300LevelDisableDevilRoomFieldOffset=0x9;
inline constexpr std::uintptr_t kApi300LevelGetAngelRoomChanceFieldOffset=0x21538;
inline constexpr std::uintptr_t kApi300LevelGetDungeonPlacementSeedFieldOffset=0x21580;
inline constexpr std::uintptr_t kApi300LevelGetHeartPickedFieldOffset=0x10;
inline constexpr std::uintptr_t kApi300LevelGetRoomCountFieldOffset=0x21510;
inline constexpr std::uintptr_t kApi300LevelIsDevilRoomDisabledFieldOffset=0x9;
inline constexpr std::uintptr_t kApi300LevelSetCanSeeEverythingFieldOffset=0x11;
inline constexpr std::uintptr_t kApi300LevelSetHeartPickedFieldOffset=0x10;
inline constexpr std::uintptr_t kApi300EntityEffectIsPlayerCreepOffset=0xa5764;
inline constexpr std::array<u8,16> kApi300EntityEffectIsPlayerCreepExpectedBytes={0x08,0x80,0x00,0x51,0x1f,0xf5,0x00,0x71,0x08,0x01,0x00,0x54,0x29,0x04,0x8e,0xd2};
inline constexpr std::uintptr_t kApi300ItemConfigIsValidCollectibleOffset=0x3c0d64;
inline constexpr std::array<u8,16> kApi300ItemConfigIsValidCollectibleExpectedBytes={0xfd,0x7b,0xbf,0xa9,0xfd,0x03,0x00,0x91,0xe0,0x04,0x00,0x34,0x68,0x37,0x00,0x90};
inline constexpr std::uintptr_t kApi300EntityNPCCalcTargetPositionOffset=0x10b898;
inline constexpr std::array<u8,16> kApi300EntityNPCCalcTargetPositionExpectedBytes={0xff,0x03,0x02,0xd1,0xe8,0x23,0x00,0xfd,0xfd,0x7b,0x05,0xa9,0xfd,0x43,0x01,0x91};
inline constexpr std::uintptr_t kApi300EntityNPCCanBeDamagedFromVelocityOffset=0x11f810;
inline constexpr std::array<u8,16> kApi300EntityNPCCanBeDamagedFromVelocityExpectedBytes={0xff,0x83,0x01,0xd1,0xe8,0x1b,0x00,0xfd,0xfd,0x7b,0x04,0xa9,0xfd,0x03,0x01,0x91};
inline constexpr std::uintptr_t kApi300EntityNPCCanRerollOffset=0x11faf4;
inline constexpr std::array<u8,16> kApi300EntityNPCCanRerollExpectedBytes={0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9,0xfd,0x03,0x00,0x91,0x08,0x80,0x41,0xf9};

// 第四批100：39方法+61公共字段；构造器辅助不计，全部Experimental。
inline constexpr std::uintptr_t kApi400EntityPlayerRenderGlowEntryOffset=0x2da1f0;
inline constexpr std::uintptr_t kApi400EntityNPCKillUniqueEntryOffset=0x10b3b0;
inline constexpr std::uintptr_t kApi400EntityNPCMakeChampionEntryOffset=0x108f60;
inline constexpr std::uintptr_t kApi400EntityNPCMakeSplatEntryOffset=0x6588c;
inline constexpr std::uintptr_t kApi400EntityPickupTryOpenChestEntryOffset=0x26f80c;
inline constexpr std::uintptr_t kApi400EntityGetBossIDFieldOffset=0x300;
inline constexpr std::uintptr_t kApi400EntitySetSpriteOverlayFrameEntryOffset=0xaef8;
inline constexpr std::uintptr_t kApi400EntityEffectFollowParentEntryOffset=0x59164;
inline constexpr std::uintptr_t kApi400EntityEffectSetDamageSourceFieldOffset=0x468;
inline constexpr std::uintptr_t kApi400EntityEffectSetRadiiFieldOffset=0x44c;
inline constexpr std::uintptr_t kApi400EntityEffectSetTimeoutFieldOffset=0x454;
inline constexpr std::uintptr_t kApi400EntityKnifeGetKnifeDistanceFieldOffset=0x434;
inline constexpr std::uintptr_t kApi400EntityKnifeGetKnifeVelocityFieldOffset=0x438;
inline constexpr std::uintptr_t kApi400EntityKnifeSetPathFollowSpeedFieldOffset=0x4ec;
inline constexpr std::uintptr_t kApi400EntityLaserGetEndPointFieldOffset=0x500;
inline constexpr std::uintptr_t kApi400EntityLaserIsCircleLaserFieldOffset=0x40;
inline constexpr std::uintptr_t kApi400EntityLaserIsSampleLaserFieldOffset=0x44d;
inline constexpr std::uintptr_t kApi400EntityLaserSetBlackHpDropChanceFieldOffset=0x524;
inline constexpr std::uintptr_t kApi400EntityLaserSetHomingTypeFieldOffset=0x4fc;
inline constexpr std::uintptr_t kApi400EntityLaserSetMultidimensionalTouchedFieldOffset=0x538;
inline constexpr std::uintptr_t kApi400EntityLaserSetOneHitFieldOffset=0x561;
inline constexpr std::uintptr_t kApi400EntityLaserSetTimeoutFieldOffset=0x448;
inline constexpr std::uintptr_t kApi400EntityNPCResetPathFinderTargetEntryOffset=0x42f63c;
inline constexpr std::uintptr_t kApi400EntityPlayerRenderTopEntryOffset=0x2da7a8;
inline constexpr std::uintptr_t kApi400EntityRenderShadowLayerEntryOffset=0x62e7c;
inline constexpr std::uintptr_t kApi400EntityProjectileAddChangeFlagsFieldOffset=0x438;
inline constexpr std::uintptr_t kApi400EntityProjectileAddFallingAccelFieldOffset=0x408;
inline constexpr std::uintptr_t kApi400EntityProjectileAddFallingSpeedFieldOffset=0x404;
inline constexpr std::uintptr_t kApi400EntityProjectileAddHeightFieldOffset=0x400;
inline constexpr std::uintptr_t kApi400EntityProjectileAddProjectileFlagsFieldOffset=0x428;
inline constexpr std::uintptr_t kApi400EntityProjectileAddScaleFieldOffset=0x410;
inline constexpr std::uintptr_t kApi400EntityProjectileClearProjectileFlagsFieldOffset=0x428;
inline constexpr std::uintptr_t kApi400EntityTearSetKnockbackMultiplierFieldOffset=0x460;
inline constexpr std::uintptr_t kApi400EntityTearSetParentOffsetFieldOffset=0x8ec;
inline constexpr std::uintptr_t kApi400EntityTearSetWaitFramesFieldOffset=0x428;
inline constexpr std::uintptr_t kApi400EntityNPCFireProjectilesEntryOffset=0x10ce58;
inline constexpr std::uintptr_t kApi400EntityNPCFireBossProjectilesEntryOffset=0x11be5c;
inline constexpr std::uintptr_t kApi400SeedsSeed2StringEntryOffset=0x4a102c;
inline constexpr std::uintptr_t kApi400SeedsString2SeedEntryOffset=0x4a0e14;

// 第四批主审追加：NS直接调用原生种子校验，替换仅有清零、尚缺独立语义锚的CurveStrength候选。
inline constexpr std::uintptr_t kApi400SeedsIsStringValidSeedEntryOffset=0x4a0df8;

// 第六批静态API：入口或已核访问器字段；完整PC/NS依据与跳转语义见dist/apis600-20261016。
inline constexpr std::uintptr_t kApi600EntityPlayerGetTearHitParamsEntryOffset=0x2ad63c;
inline constexpr std::uintptr_t kApi600EntityPlayerGetActiveSubChargeFieldOffset=0x1970;
inline constexpr std::uintptr_t kApi600EntityPlayerGetBombVariantEntryOffset=0x2ba348;
inline constexpr std::uintptr_t kApi600EntityPlayerAreOpposingShootDirectionsPressedFieldOffset=0x1a0c;
inline constexpr std::uintptr_t kApi600EntityPlayerHasWeaponTypeFieldOffset=0x1780;
inline constexpr std::uintptr_t kApi600EntityPlayerGetMultiShotParamsEntryOffset=0x2bb0e4;
inline constexpr std::uintptr_t kApi600EntityPlayerGetMultiShotPositionVelocityEntryOffset=0x2bb744;
inline constexpr std::uintptr_t kApi600ItemConfigGetCardsFieldOffset=0x48;
inline constexpr std::uintptr_t kApi600ItemConfigGetPillEffectsFieldOffset=0x60;
inline constexpr std::uintptr_t kApi600ItemConfigGetNullItemsFieldOffset=0x30;
inline constexpr std::uintptr_t kApi600ItemConfigItemIsNullFieldOffset=0x0;
inline constexpr std::uintptr_t kApi600ItemConfigShouldAddCostumeOnPickupFieldOffset=0xb6;
inline constexpr std::uintptr_t kApi600CardConfigListGetFieldOffset=0x48;
inline constexpr std::uintptr_t kApi600CardConfigListlenFieldOffset=0x48;
inline constexpr std::uintptr_t kApi600PillConfigListGetFieldOffset=0x60;
inline constexpr std::uintptr_t kApi600PillConfigListlenFieldOffset=0x60;
inline constexpr std::uintptr_t kApi600GameBombDamageEntryOffset=0x354e04;
inline constexpr std::uintptr_t kApi600GameBombExplosionEffectsEntryOffset=0x355c68;
inline constexpr std::uintptr_t kApi600GameBombTearflagEffectsEntryOffset=0x35672c;
inline constexpr std::uintptr_t kApi600GameUpdateStrangeAttractorEntryOffset=0x35bf74;
inline constexpr std::uintptr_t kApi600GameRenderEntryOffset=0x35231c;
inline constexpr std::uintptr_t kApi600RoomRenderEntryOffset=0x47fb08;
inline constexpr std::uintptr_t kApi600GridEntityDoorIsBustedFieldOffset=0x309;
inline constexpr std::uintptr_t kApi600GridEntityDoorIsLockedFieldOffset=0xc;
inline constexpr std::uintptr_t kApi600GridEntityDoorIsKeyFamiliarTargetFieldOffset=0xc;
inline constexpr std::uintptr_t kApi600GridEntityDoorGetSpriteOffsetFieldOffset=0x11c;
inline constexpr std::uintptr_t kApi600GridEntityRockGetRubbleAnimFieldOffset=0x1b8;
inline constexpr std::uintptr_t kApi600GameGetLastDevilRoomStageFieldOffset=0x26fa5c;
inline constexpr std::uintptr_t kApi600GameGetLastLevelWithDamageFieldOffset=0x2f002c;
inline constexpr std::uintptr_t kApi600GameGetLastLevelWithoutHalfHpFieldOffset=0x2f0020;
inline constexpr std::uintptr_t kApi600RoomGetShopLevelFieldOffset=0x76c8;
inline constexpr std::uintptr_t kApi600RoomGetLavaIntensityFieldOffset=0x7fa0;
inline constexpr std::uintptr_t kApi600RoomHasSlowDownFieldOffset=0x78f0;
inline constexpr std::uintptr_t kApi600RoomSetSlowDownFieldOffset=0x78f0;
inline constexpr std::uintptr_t kApi600RoomIsFirstEnemyDeadFieldOffset=0x7964;
inline constexpr std::uintptr_t kApi600RoomSetFirstEnemyDeadFieldOffset=0x7964;
inline constexpr std::uintptr_t kApi600RoomInvalidatePickupVisionFieldOffset=0x8160;
inline constexpr std::uintptr_t kApi600RoomEmitBloodFromWallsFieldOffset=0x78d8;
inline constexpr std::uintptr_t kApi600SpriteGetOverlayAnimationFieldOffset=0x68;
inline constexpr std::uintptr_t kApi600SpriteSetOverlayRenderPriorityFieldOffset=0x90;
inline constexpr std::uintptr_t kApi600GlobalRandomVectorEntryOffset=0x35830;
inline constexpr std::uintptr_t kApi600RoomConfigEntriesGetFieldOffset=0x8;
inline constexpr std::uintptr_t kApi600RoomConfigEntrieslenFieldOffset=0x10;
inline constexpr std::uintptr_t kApi600RoomConfigSpawnslenFieldOffset=0x58;
inline constexpr std::uintptr_t kApi600RoomGetDeliriumDistanceFieldOffset=0xf4;

// 第六批EntityRef原生快照排布更正，PC登记与Game::BombDamage实参构造双证；旧记录见entity_ref_api.hpp历史注释。
inline constexpr std::uintptr_t kApi600EntityRefTypeOffset=0x0;
inline constexpr std::uintptr_t kApi600EntityRefVariantOffset=0x4;
inline constexpr std::uintptr_t kApi600EntityRefSpawnerTypeOffset=0x8;
inline constexpr std::uintptr_t kApi600EntityRefSpawnerVariantOffset=0xc;
inline constexpr std::uintptr_t kApi600EntityRefPositionOffset=0x10;
inline constexpr std::uintptr_t kApi600EntityRefNativeOffsetOffset=0x18;
inline constexpr std::uintptr_t kApi600EntityRefFlagsOffset=0x20;
inline constexpr std::uintptr_t kApi600EntityRefEntityOffset=0x28;

// 第七批固定PC版本恢复：原件与边界见dist/apis700-20261016，虚表行值为槽号。
inline constexpr std::uintptr_t kApi700EntityPlayerAnimatePillEntryOffset=0x2DFA98;
inline constexpr std::uintptr_t kApi700EntityPlayerAnimateTrinketEntryOffset=0x2E8260;
inline constexpr std::uintptr_t kApi700EntityPlayerSwapActiveItemsEntryOffset=0x2DC570;
inline constexpr std::uintptr_t kApi700EntityPlayerTryRemoveCollectibleCostumeEntryOffset=0x29ABAC;
inline constexpr std::uintptr_t kApi700EntityPlayerGetCostumeNullPosEntryOffset=0x28E8C4;
inline constexpr std::uintptr_t kApi700EntityPlayerReplaceCostumeSpriteEntryOffset=0x2FC000;
inline constexpr std::uintptr_t kApi700EntityPlayerQueueExtraAnimationFieldOffset=0x1718;
inline constexpr std::uintptr_t kApi700EntityPlayerGetLastDamageSourceFieldOffset=0x1A70;
inline constexpr std::uintptr_t kApi700EntityPlayerGetPocketItemFieldOffset=0x1C10;
inline constexpr std::uintptr_t kApi700RoomScreenWrapPositionEntryOffset=0x4848D0;
inline constexpr std::uintptr_t kApi700EntityLaserCalculateEndPointEntryOffset=0xF7BD8;
inline constexpr std::uintptr_t kApi700SeedsGetSeedEffectEntryOffset=0x49F098;
inline constexpr std::uintptr_t kApi700SeedsIsSpecialSeedEntryOffset=0x49F098;
inline constexpr std::uintptr_t kApi700IsaacAddPillEffectToPoolEntryOffset=0x3CA8D0;
inline constexpr std::uintptr_t kApi700RoomGetLRoomAreaDescEntryOffset=0x484558;
inline constexpr std::uintptr_t kApi700RoomGetLRoomTileDescEntryOffset=0x45BF90;
inline constexpr std::uintptr_t kApi700ItemPoolAddRoomBlacklistFieldOffset=0x908;
inline constexpr std::uintptr_t kApi700LevelGetDevilAngelRoomRNGFieldOffset=0x21528;
inline constexpr std::uintptr_t kApi700GameGetFontFieldOffset=0x24F9C8;
inline constexpr std::uintptr_t kApi700GameGetAmbushFieldOffset=0x26FAA8;
inline constexpr std::uintptr_t kApi700GameGetItemOverlayFieldOffset=0x25DB0;
inline constexpr std::uintptr_t kApi700GameShowFortuneEntryOffset=0x342FA4;
inline constexpr std::uintptr_t kApi700GameShowRuleEntryOffset=0x342FA4;
inline constexpr std::uintptr_t kApi700IsaacGetCurseIdByNameFieldOffset=0x2500;
inline constexpr std::uintptr_t kApi700IsaacGetScreenPointScaleFieldOffset=0xA34370;
inline constexpr std::uintptr_t kApi700EntityRenderVtableSlot=0x6;
inline constexpr std::uintptr_t kApi700EntityPostRenderVtableSlot=0x8;
inline constexpr std::uintptr_t kApi700GridEntityRenderVtableSlot=0x4;
inline constexpr std::uintptr_t kApi700EntityLaserGetSamplesFieldOffset=0x478;
inline constexpr std::uintptr_t kApi700EntityLaserGetNonOptimizedSamplesFieldOffset=0x490;
inline constexpr std::uintptr_t kApi700EntityNPCQueryNPCsTypeEntryOffset=0x10B868;
inline constexpr std::uintptr_t kApi700EntityNPCQueryNPCsSpawnerTypeEntryOffset=0x11FE60;
inline constexpr std::uintptr_t kApi700EntityNPCQueryNPCsGroupEntryOffset=0x120104;
inline constexpr std::uintptr_t kApi700RoomGetEntitiesFieldOffset=0x19C0;
inline constexpr std::uintptr_t kApi700EntityListGetFieldOffset=0x8;
inline constexpr std::uintptr_t kApi700EntityList__lenFieldOffset=0x8;
inline constexpr std::uintptr_t kApi700VectorListGetFieldOffset=0x0;
inline constexpr std::uintptr_t kApi700VectorList__lenFieldOffset=0x0;
inline constexpr std::uintptr_t kApi700GridEntityPoopReduceSpawnRateFieldOffset=0x1C;

// 第七批固定PC版本恢复：原件与边界见dist/apis700-20261016，虚表行值为槽号。
inline constexpr std::uintptr_t kApi700GameSpawnEntityDescEntryOffset=0x3546CC;

// 2026-10-20：压力板字符串寿命；writer正常16B入口，两个析构在RNG析构BL精确拦截，避免重放ADRP。
inline constexpr uintptr_t kPressurePlateAnimationWriterOffset = 0x38E524;
inline constexpr std::array<u8,16> kPressurePlateAnimationWriterExpectedBytes = {0xfd,0x7b,0xbd,0xa9,0xf5,0xb,0x0,0xf9,0xfd,0x3,0x0,0x91,0xf4,0x4f,0x2,0xa9};
inline constexpr uintptr_t kPressurePlateDtorVeneerOffset = 0x68CD20;
inline constexpr std::size_t kPressurePlateDtorVeneerBytes = 16;
inline constexpr uintptr_t kPressurePlateDeletingVeneerOffset = 0x68CD30;
inline constexpr std::size_t kPressurePlateDeletingVeneerBytes = 16;

// 2026-10-26：原生Entity_Player::Init结束时派MC_POST_PLAYER_INIT，
// 避免零初始血角色被延迟扫描到时已经死亡。固定NRO实际虚函数入口；
// ABI void(this, EntityType, variant, subType, initSeed)，原函数完整执行后派发。
// Entity::Init(eEntityType,u32,u32,u32), verified against the supported original.
// Its base initializer also runs for native pickup/NPC Morph operations.
inline constexpr uintptr_t kNativeEntityInitOffset = 0x597D4;
inline constexpr std::array<u8,16> kNativeEntityInitExpectedBytes = {
    0xFF,0x83,0x01,0xD1,0xFD,0x7B,0x03,0xA9,
    0xFD,0xC3,0x00,0x91,0xF5,0x23,0x00,0xF9,
};
// Init dispatch uses relocated data pointers, preserving function bodies for
// field/layout validators. The supported NRO has no derived Init PLT/GOT and
// no direct BL/B callers; its derived Init addresses occur only in these vtables.
inline constexpr uintptr_t kNativeEntityInitVtableSlotOffset = 0xA34F68;
inline constexpr uintptr_t kNativeEntityInitGotOffset = 0xA9F2E8;
inline constexpr uintptr_t kNativeEntityInitPltOffset = 0x672700;
inline constexpr std::array<u8,16> kNativeEntityInitPltExpectedBytes = {
    0x70,0x21,0x00,0xB0,0x11,0x76,0x41,0xF9,
    0x10,0xA2,0x0B,0x91,0x20,0x02,0x1F,0xD6,
};
inline constexpr uintptr_t kNativeTearInitOffset = 0x330E58;
inline constexpr uintptr_t kNativeTearInitVtableSlotOffset = 0xA37648;
inline constexpr std::array<u8,16> kNativeTearInitExpectedBytes = {
    0xFF,0x43,0x01,0xD1,0xFD,0x7B,0x02,0xA9,
    0xFD,0x83,0x00,0x91,0xF6,0x57,0x03,0xA9,
};
inline constexpr uintptr_t kNativeEffectInitOffset = 0x7FEF4;
inline constexpr uintptr_t kNativeEffectInitVtableSlotOffset = 0xA35248;
inline constexpr std::array<u8,16> kNativeEffectInitExpectedBytes = {
    0xFF,0x43,0x03,0xD1,0xEB,0x2B,0x05,0x6D,
    0xE9,0x23,0x06,0x6D,0xFD,0x7B,0x07,0xA9,
};
inline constexpr uintptr_t kNativePlayerInitOffset = 0x278D94;
inline constexpr std::array<u8, 16> kNativePlayerInitExpectedBytes = {
    0xFF,0x03,0x05,0xD1,0xEA,0x63,0x00,0xFD,
    0xE9,0x23,0x0D,0x6D,0xFD,0x7B,0x0E,0xA9,
};

// Room::Room() leaves +0x8 (RoomDescriptor*) untouched. Level::Reset @0x3D0284
// deletes the old room, allocates 0x8168 bytes, calls this constructor, then
// publishes it at +0x21550. PlayerManager::Init runs before Level::Init and Lua
// may read the descriptor during POST_PLAYER_INIT -> SetPocketActiveItem -> cache.
// Initialize only this member before native construction; the native bounds
// vectors (+0x1C/+0x24) and GetCenterPos implementation remain authoritative.
inline constexpr uintptr_t kNativeRoomConstructorOffset = 0x44E5DC;
inline constexpr std::array<u8, 16> kNativeRoomConstructorExpectedBytes = {
    0xFF,0x43,0x02,0xD1,0xE9,0x23,0x03,0x6D,
    0xF9,0x2B,0x00,0xF9,0xFD,0x7B,0x04,0xA9,
};
