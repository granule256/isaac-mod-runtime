"""`Isaac.GetPlayer(i)` 与 `Entity`/`EntityPlayer` 只读视图的宿主行为测试。

批次 2 的这两件事都建立在"已真机交叉验证过的引擎偏移"上（见 `runtime_constants.hpp` 的常量表与
探针魔数 `ISAACGP1`），所以设备侧不需要新的证据；需要被证明的是**我们这一侧的指针链、校验与
Lua 视图**对不对。那些正好可以完全在宿主上验证：

1. 用 `malloc` 出来的块**伪造一份引擎内存**（模块块里的 `g_Game` 槽 → 指针变量 → `Game` →
   `players` 向量 → `Entity_Player`），并通过 `SetEngineModuleBase()` 把它当成引擎模块基址发布；
2. 用真实 Lua 脚本断言 `Isaac.GetPlayer(0)` 的字段值（真机实测值：`Type == 1`、`Variant == 0`、
   `SubType == 0`、`PlayerType == 0`、下标 0、位置 `(80.0, 280.0)`）、`Position` 的"新对象"语义、
   `ToPlayer`、`GetPlayerType`、`GetData`、`HasCollectible`；
3. 逐场景断言"拿不到就返回 nil / false"：越界、空指针、vptr 不匹配、槽为空、基址未发布。

`HasCollectible` 的设备实现是一条 `bl base + 0x27D3F4`，宿主上既没有引擎映像也不可能把 C++
函数放进去，所以宿主通过 `SetEntityPlayerHasCollectibleHostImplementation()` 注入那一条调用
（设备构建里不存在这个入口，见 `isaac_api.hpp`）。注入点记录它收到的参数，因此下面这几件事仍然
是**被验证的**，而不是假设的：

  * 传给引擎的第一个参数就是 `players[0]` 的地址（`x0 = this`）；
  * 收藏品 id 原样到达、返回值原样变成 Lua 布尔；
  * **vptr 校验先于调用** —— 引擎内存被改坏之后，那个句柄的 `HasCollectible` 不再产生调用。

最后一条用"两帧"实现：第一帧拿到句柄并正常调用；harness 在派发之间把伪造的 vptr 改坏；第二帧
用同一个句柄访问字段/方法，必须既返回安全值、又不产生新的引擎调用。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"


HARNESS = r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/api_call_stats.hpp"   // 批次 141：兜底挡下的次数与最后一次编号

#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 批次 141（2026-09-26）：宿主跳板（`engine_call_trampoline_host_stub.cpp`）记的"真的调进引擎几次"。
// 设备上由汇编跳板完成调用；宿主上没有引擎，跳板什么都不做 ⇒ 想知道"这一行到底有没有被调进去"
// 只能看这个计数（`null_costume_guard` 场景用它区分"有效编号照常调"与"无效编号被挡下"）。
extern "C" std::uint32_t g_HostEngineCallTrampolineCalls;

// Observation seams owned by other families: the Lua runtime links them, so the harness answers
// "unavailable" exactly like the other Lua runtime tests do.
GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::ThunkUnavailable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {
    return GameRoomObservation::RoomUnreadable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {
    return TextReadResult::OpenFailed;
}
}

namespace {

const char* kScriptTemplate = R"lua(@SCRIPT@)lua";

//: 批次 212：`ControlsEnabled`(+0x400，1 字节 bool) 两侧的**诱饵**字节 ——
//: 按 4 字节写会踩坏邻居（症状比"没写进去"难查得多），所以这里两侧都下诱饵。
constexpr std::uint8_t kEnabledNeighbourBefore = 0x5Au;
constexpr std::uint8_t kEnabledNeighbourAfter = 0xA5u;

// --- 伪造的引擎内存 --------------------------------------------------------
//
// 与真机完全同形：模块块（`base + kGameOwnerGlobalSlotOffset` 是 `g_Game` 的**槽**，槽里存的是
// 指向 .bss 变量的指针）→ 变量里才是 `Game*` → `Game` 里的 `std::vector<Entity_Player*>`
// → 元素指向 `Entity_Player` 对象，对象首字是 vtable 指针。
std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
// 收藏品容器（`EntityPlayer:GetCollectibleCount()` 读 `+0x1AB8`/`+0x1AC0` 那一对指针）。
std::vector<unsigned char> g_CollectibleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
// --- 批次 141：null 服装容器（`ItemConfig` **内嵌**在 `Manager` 里）-------------------
//
// 链与真机逐级同形（批次 139 的反汇编定案）：模块块[base + 0xAAC648] = &g_ManagerSlot
// （槽里是**变量地址**，不是对象）→ 变量里是 `Manager*` → `Manager + 0x36538` = `ItemConfig`
// （**内嵌**，所以是加法）→ `IC + 0x30/+0x38` = null 服装向量（元素是条目指针）。
std::vector<unsigned char> g_ManagerSlotBytes;
std::vector<unsigned char> g_ManagerBytes;
std::vector<std::vector<unsigned char>> g_CostumeItemBlocks;
std::vector<unsigned char> g_CostumeElementBytes;

std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

void WriteWord(std::vector<unsigned char>& block, std::size_t offset, std::uint64_t value) {
    WriteAt(block, offset, value);
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

// `Isaac.GetPlayer` 用到的偏移都要落在这块里：全局槽在 `0xAAC698`，vptr 期望值在 `0xA37110`。
void CreateBlocks() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    // 批次 137（2026-09-26）：`EntityPlayer:AddNullCostume` 走**引擎方法数据行**，它的入口判据是
    // "模块基址 + 偏移 + 入口 4 字节指纹"。宿主上要让它真的走到 `callable` 分支（进而调那个**占位**
    // 跳板，而不是判成"入口指纹不符"），就得在那块伪造模块内存的对应偏移上摆上真正的首 4 字节。
    // 偏移与字都取自 `runtime_constants.hpp`（`kEntityPlayerAddNullCostumeOffset` 在伪造块范围内：
    // `0x291BBC < 0xAAC698`）。
    WriteAt<std::uint32_t>(g_ModuleBytes, kEntityPlayerAddNullCostumeOffset,
                           kEntityPlayerAddNullCostumeEntryWord);
    WriteAt<std::uint32_t>(g_ModuleBytes, kEntityPlayerTryRemoveNullCostumeOffset,
                           kEntityPlayerTryRemoveNullCostumeEntryWord);
    // 批次 195（2026-09-29）：`EntityPlayer:HasTrinket` 改成**一次引擎调用**
    // （`Entity_Player::HasTrinket @ 0x28D3B8`），它按"模块基址 + 偏移 + 入口 4 字节指纹"
    // 解析入口。宿主上摆上真正的首 4 字节，那个 handler 才会走到"调跳板"这一步
    // （否则它会像 `RNG:SetSeed` 那样报 "native bindings are unavailable" —— 那是**设计行为**：
    // 偏移/指纹对不上时不编一个假 false）。`0x28D3B8 < 0xAAC698` ⇒ 落在伪造块范围内。
    WriteAt<std::uint32_t>(g_ModuleBytes, kEntityPlayerHasTrinketOffset,
                           kEntityPlayerHasTrinketEntryWord);
}

// 发布两级链的**第一级**：模块块里的槽 → .bss 变量。
void PublishOwnerSlot(std::uint64_t variableAddress) {
    WriteWord(g_ModuleBytes, kGameOwnerGlobalSlotOffset, variableAddress);
}

// `players` 数组（元素是 `Entity_Player*`）与 `Game` 里的 begin/end。
void PublishPlayers(const std::vector<std::uint64_t>& players) {
    g_PlayerArrayBytes.assign(players.size() * sizeof(std::uint64_t) + sizeof(std::uint64_t), 0);
    for (std::size_t index = 0; index < players.size(); ++index) {
        WriteWord(g_PlayerArrayBytes, index * sizeof(std::uint64_t), players[index]);
    }
    WriteWord(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteWord(g_GameBytes, kGamePlayerArrayEndOffset,
              AddressOf(g_PlayerArrayBytes) + players.size() * sizeof(std::uint64_t));
}

// 真机实测值：Type == 1、Variant == 0、SubType == 0、PlayerType == 0、下标 0、位置 (80, 280)。
void FillPlayer(bool validVtable) {
    WriteWord(g_PlayerBytes, 0,
              validVtable ? g_EngineBase + kEntityPlayerVtableOffset : 0x5A5A5A5AULL);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, 1);
    WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,1);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityVariantOffset, 0);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntitySubTypeOffset, 0);
    WriteAt<float>(g_PlayerBytes, kEntityPositionOffset, 80.0F);
    WriteAt<float>(g_PlayerBytes, kEntityPositionOffset + sizeof(float), 280.0F);
    WriteAt<float>(g_PlayerBytes, kEntitySizeOffset, 12.5F);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, 0);
    // 字段读取型 API（**数据行**机制，见 `field_api.hpp`）要读的三个偏移。
    // 值刻意取非零/非默认，用来证明"真的读了内存"，而不是像以前的桩那样返回硬编码 0：
    //   * 红心容器 = 6（半心单位）⇒ `GetMaxHearts()` 必须回 6；
    //   * 魂心 = 4（半心单位）⇒ `GetSoulHearts()` 必须回 4；
    //   * 婴儿皮肤 = -1（**有符号**，非婴儿）⇒ `GetBabySkin()` 必须回 -1 而不是 4294967295。
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerRedHeartContainersOffset, 6);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerSoulHeartsOffset, 4);
    WriteAt<std::int32_t>(g_PlayerBytes, kEntityPlayerBabySkinOffset, -1);
    // 2026-09-16 新增字段（**故意写死字面偏移**，不跟实现侧常量走 —— 夹具跟着常量走会两边一起错、
    // 断言永远绿；见 `docs/错误复盘.md` 2026-09-16 第一条）：
    //   * 四个 float 属性：Damage=4.25 / MoveSpeed=1.5 / MaxFireDelay=7.5 / TearRange=300.0
    //     （取非整数，能证明是按 float 读而不是按整数读）；
    //   * ★ 批次 405：补 `ShotSpeed`(+0x1838) = 2.5f —— 它是 `MaxFireDelay` 的高 4 字节，
    //     同一族属性，读/写都要按 float 钉住（前后偏移由其它字段天然隔离，误读会拿到 7.5 或 0）。
    //   * `CanFly` = 1（+0x1954，**1 字节**；前后各一个单字节诱饵，按 4 字节读会读到诱饵）；
    //   * `ControlsCooldown` = -3（+0x404，有符号：无符号读会给出 4294967293）。
    WriteAt<float>(g_PlayerBytes, 0x1844, 4.25F);
    WriteAt<float>(g_PlayerBytes, 0x194C, 1.5F);
    WriteAt<float>(g_PlayerBytes, 0x1834, 7.5F);
    WriteAt<float>(g_PlayerBytes, 0x1854, 300.0F);
    // 批次 405：`ShotSpeed`(+0x1838) 紧挨 `MaxFireDelay`(+0x1834) 的高 4 字节。
    WriteAt<float>(g_PlayerBytes, 0x1838, 2.5F);
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x1953, 0x7Fu);   // 诱饵：CanFly 前一字节
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x1954, 1u);
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x1955, 0x7Eu);   // 诱饵：CanFly 后一字节
    WriteAt<std::int32_t>(g_PlayerBytes, 0x404, -3);
    // ★ 2026-10-01（批次 257）：`player.Luck` 的偏移从 `0x1920`(int32) 更正为 `0x1950`(**float**)。
    //   * `+0x1950` 写 `-3.25f` —— **负数 + 小数**：按整数读、或读成别的偏移都会失败；
    //   * `+0x1920`（**旧偏移**）故意写 int32 `7`：实现若再退回旧偏移，断言会拿到 `7` 而不是 -3.25
    //     ⇒ 这一格就是"改回去也没人发现"的克星；
    //   * 这 4 个字节（0x1950..0x1953）会**覆盖**上面那个 `+0x1953` 的"CanFly 前一字节"诱饵
    //     ⇒ 那个诱饵位现在由本 float 的最高字节（`-3.25f` 的 `0xC0`）担当，它同样 ≠ 1，
    //       "CanFly 读成前一格"这类 off-by-one 照样会被抓到（所以上面那行仍保留、不删）。
    WriteAt<std::int32_t>(g_PlayerBytes, 0x1920, 7);
    WriteAt<float>(g_PlayerBytes, 0x1950, -3.25F);
    // 批次 212：`ControlsEnabled`(+0x400) 是**1 字节** bool，夹具把它置 1（= 能操作），
    // 前后各放一个诱饵字节 —— 按 4 字节写会踩坏邻居，那种 bug 比"没写进去"更难查。
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x3FF, kEnabledNeighbourBefore);
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x400, 1u);
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x401, kEnabledNeighbourAfter);
    // 批次 133（2026-09-25）：**饰品槽**（`GetTrinket` / `GetTrinketMultiplier` 读的都是它）。
    // 槽 0 = 30、槽 1 = 0（空）。偏移同样写字面值（+0x1AB0，两槽步长 4）。
    WriteAt<std::uint32_t>(g_PlayerBytes, 0x1AB0, 30);
    WriteAt<std::uint32_t>(g_PlayerBytes, 0x1AB4, 0);
    // 批次 195（2026-09-29）：`EntityPlayer:HasGoldenBomb()` 现在是**字段数据行**，读
    // `Entity_Player + 0x16D9` 那一个字节 ⇒ 夹具写 1（前后各一个字节诱饵：按 4 字节读会读到诱饵）。
    // 偏移写字面值，不跟实现侧常量走（跟着常量走会两边一起错、断言永远绿）。
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x16D8, 0x7Fu);
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x16D9, 1u);
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x16DA, 0x7Eu);
    // ★★ 批次 195（2026-09-29）：`EntityPlayer` 组 A 的五条字段（**全部写字面偏移 + 诱饵**，
    // 理由同上面那条：夹具跟着实现侧常量走会两边一起错、断言永远绿）。
    //   * `GetHearts` → `+0x16BC`（半心）。`+0x16B8` 已是"容器 6"（`GetMaxHearts` 读它）、
    //     `+0x16C0` 放诱饵 ⇒ 读错一格就会读到 6 或诱饵，断言必然失败。
    //   * `GetPoopMana` → `+0x269C`；前后各一个 4 字节诱饵。
    //   * `GetPoopSpell` → `+0x26A0` 起 6 个**互不相同**的字节（1..6），`+0x26A6` 放诱饵
    //     ⇒ 既能验"第 i 格读得对"，也能验"越界不许读到 +0x26A6"。
    //   * `GetModelingClayEffect` → `+0x2730`（写 166 = 一个可辨认的收藏品 id）。
    //   * `GetPlayerFormCounter` → `+0x1C54 + form*4` 的 15 格 int32（只写 0/1/14 三格，
    //     其余留 0 —— 与"引擎里是个计数器数组"同形），`+0x1C90` 放诱饵（越界会读到它）。
    WriteAt<std::uint32_t>(g_PlayerBytes, 0x16B8, 6);
    WriteAt<std::uint32_t>(g_PlayerBytes, 0x16BC, 7);
    WriteAt<std::uint32_t>(g_PlayerBytes, 0x16C0, 0x7F7F7F7Fu);
    WriteAt<std::uint32_t>(g_PlayerBytes, 0x2698, 0x7F7F7F7Fu);
    WriteAt<std::uint32_t>(g_PlayerBytes, 0x269C, 7);
    WriteAt<std::uint32_t>(g_PlayerBytes, 0x26A0, 0x7F7F7F7Fu);
    for (std::uint32_t slot = 0; slot < 6; ++slot) {
        WriteAt<std::uint8_t>(g_PlayerBytes, 0x26A0 + slot, static_cast<std::uint8_t>(1 + slot));
    }
    WriteAt<std::uint8_t>(g_PlayerBytes, 0x26A6, 0x55u);
    WriteAt<std::int32_t>(g_PlayerBytes, 0x2730, 166);
    WriteAt<std::int32_t>(g_PlayerBytes, 0x1C54 + 0 * 4, 3);
    WriteAt<std::int32_t>(g_PlayerBytes, 0x1C54 + 1 * 4, 0);
    WriteAt<std::int32_t>(g_PlayerBytes, 0x1C54 + 14 * 4, 7);
    WriteAt<std::int32_t>(g_PlayerBytes, 0x1C90, 0x7F7F7F7F);
    // 收藏品容器：**按 id 的计数数组**（每格 4 字节 = "该收藏品有几件"）。
    // 写 `{1, 0, 2}` ⇒ `GetCollectibleCount()`（求和）必须回 **3**，而不是 2（非零格子数）
    // 或 3（格子数本身也恰好是 3 —— 所以这里刻意让"求和"与"格子数"不同：见下面 6 格那组）。
    g_CollectibleBytes.assign(6 * sizeof(std::uint32_t), 0);
    WriteAt<std::uint32_t>(g_CollectibleBytes, 0 * sizeof(std::uint32_t), 1);
    WriteAt<std::uint32_t>(g_CollectibleBytes, 4 * sizeof(std::uint32_t), 2);
    WriteWord(g_PlayerBytes, kEntityPlayerCollectibleBeginOffset,
              AddressOf(g_CollectibleBytes));
    WriteWord(g_PlayerBytes, kEntityPlayerCollectibleEndOffset,
              AddressOf(g_CollectibleBytes) + 6 * sizeof(std::uint32_t));
    // `Entity.Index` 是**房间实体表序号**（`Entity+0x30`，批次 4 定位），与"玩家在 `players`
    // 向量里的下标"（`+0x19F0`）不是同一个量；两个偏移刻意写不同的值，用来钉住读的是哪个。
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityIndexOffset, 7);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerIndexOffset, 0);
}

void CorruptVtable() {
    WriteWord(g_PlayerBytes, 0, 0xDEADBEEFULL);
}

// --- 批次 141：把 null 服装容器摆出来（`null_costume_guard` 场景专用）---------------
//
// 三条槽位：0 = 有条目、1 = 有条目、2 = **空槽**（引擎的向量里本来就有空槽这种形态，
// `GetNullItem(2)` 会拿到空指针 —— 真机上那就是崩的那一步）。条目的 `ID`（`+0x04`）写非零值，
// 只是让"读到的确实是这一条"更容易看；`AddNullCostume` 那条路只看**下标**（`GetNullItem(id)`
// 是纯下标取值），不看 `ID` 字段。
void PublishNullCostumes() {
    // `ItemConfig` 内嵌在 `Manager` 里 ⇒ 这一块要盖到 `0x36538 + 0x40`。
    g_ManagerBytes.assign(kManagerItemConfigOffset + 0x40, 0);
    g_CostumeItemBlocks.assign(2, std::vector<unsigned char>(0xB0, 0));
    WriteAt<std::uint32_t>(g_CostumeItemBlocks[0], kItemConfigItemIdOffset, 5);
    WriteAt<std::uint32_t>(g_CostumeItemBlocks[1], kItemConfigItemIdOffset, 7);
    const std::uint64_t elements[3] = {
        reinterpret_cast<std::uint64_t>(g_CostumeItemBlocks[0].data()),
        reinterpret_cast<std::uint64_t>(g_CostumeItemBlocks[1].data()),
        0,
    };
    g_CostumeElementBytes.assign(sizeof(elements), 0);
    std::memcpy(g_CostumeElementBytes.data(), elements, sizeof(elements));
    WriteWord(g_ManagerBytes, kManagerItemConfigOffset + kItemConfigNullItemBeginOffset,
              AddressOf(g_CostumeElementBytes));
    WriteWord(g_ManagerBytes, kManagerItemConfigOffset + kItemConfigNullItemEndOffset,
              AddressOf(g_CostumeElementBytes) + sizeof(elements));
    // 两级链：模块块里的槽 → .bss 变量；变量 → `Manager`。
    g_ManagerSlotBytes.assign(sizeof(std::uint64_t), 0);
    WriteWord(g_ManagerSlotBytes, 0, AddressOf(g_ManagerBytes));
    WriteWord(g_ModuleBytes, kGameManagerGlobalSlotOffset, AddressOf(g_ManagerSlotBytes));
}

// --- 注入的"引擎方法" ------------------------------------------------------

std::uintptr_t g_CallEntity = 0;
std::uint32_t g_CallId = 0;
int g_CallCount = 0;
//: 引擎侧看到的第二个参数（`ignoreModifiers`）—— 必须**原样往返**（2026-09-17 补的字段）。
bool g_LastIgnoreModifiers = false;
int g_IgnoreModifiersTrueCount = 0;

bool HarnessHasCollectible(void* entity, std::uint32_t collectibleId, bool ignoreModifiers) {
    g_CallEntity = reinterpret_cast<std::uintptr_t>(entity);
    g_CallId = collectibleId;
    g_LastIgnoreModifiers = ignoreModifiers;
    if (ignoreModifiers) {
        ++g_IgnoreModifiersTrueCount;
    }
    ++g_CallCount;
    // 只对 1 号收藏品回答 true：返回值必须原样往返（恒真/恒假都算实现错了）。
    return collectibleId == 1;
}

bool ExpectNumber(const char* name, double expected) {
    double value = 0.0;
    if (!LuaRuntime::ReadLuaGlobalNumber(name, &value)) {
        std::printf("ISAAC_FAIL: global %s was never written\n", name);
        return false;
    }
    if (value != expected) {
        std::printf("ISAAC_FAIL: %s expected %.0f, got %.0f\n", name, expected, value);
        return false;
    }
    return true;
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const std::string scenario = argv[1];
    if (scenario != "valid" && scenario != "empty" && scenario != "zero_element" &&
        scenario != "bad_vptr" && scenario != "no_game" && scenario != "no_base" &&
        scenario != "take_damage" && scenario != "null_costume_guard") {
        return 91;
    }

    const bool publishBase = scenario != "no_base";
    CreateBlocks();
    if (publishBase) {
        LuaRuntime::SetEngineModuleBase(g_EngineBase);
    }

    if (scenario == "valid" || scenario == "take_damage" || scenario == "null_costume_guard") {
        FillPlayer(true);
        PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));
        WriteWord(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
        PublishPlayers({AddressOf(g_PlayerBytes)});
        if (scenario == "null_costume_guard") {
            PublishNullCostumes();
        }
    } else if (scenario == "empty") {
        PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));
        WriteWord(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
        PublishPlayers({});
    } else if (scenario == "zero_element") {
        PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));
        WriteWord(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
        PublishPlayers({0});
    } else if (scenario == "bad_vptr") {
        FillPlayer(false);
        PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));
        WriteWord(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
        PublishPlayers({AddressOf(g_PlayerBytes)});
    } else if (scenario == "no_game") {
        // 槽可读但变量里是 0：第二级解引用拿到空指针。
        PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));
        WriteWord(g_OwnerSlotBytes, 0, 0);
        PublishPlayers({AddressOf(g_PlayerBytes)});
    }

    isaac::runtime::SetEntityPlayerHasCollectibleHostImplementation(&HarnessHasCollectible);

    // 批次 141：派发之前记下宿主跳板的调用次数 ⇒ 下面用差值断言"这一场景里只有有效编号
    // 真的调进了引擎"（宿主跳板是占位实现，它被调到与否就是"我们有没有把这次调用放行"）。
    const std::uint32_t trampolineBefore = g_HostEngineCallTrampolineCalls;

    const std::string script = "SCENARIO = '" + scenario + "'\n" + kScriptTemplate;
    const auto result =
        LuaRuntime::InitializeFromBuffer(script.c_str(), script.size(), "@entity_player.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("ISAAC_FAIL: the Lua state did not initialize\n");
        return 2;
    }

    LuaRuntime::DispatchPostUpdate();
    if (LuaRuntime::TakeCallbackError()) {
        std::printf("ISAAC_FAIL: the Lua callback raised an error\n");
        return 1;
    }
    if (scenario == "valid") {
        // 第二帧之前把伪造的 vptr 改坏：句柄必须自证失效，而且不许再调用引擎方法。
        CorruptVtable();
        LuaRuntime::DispatchPostUpdate();
        if (LuaRuntime::TakeCallbackError()) {
            std::printf("ISAAC_FAIL: the second frame raised a Lua error\n");
            return 1;
        }
    }

    if (!ExpectNumber("SCENARIO_OK", 1.0)) return 1;
    if (scenario == "take_damage") {
        if (!ExpectNumber("TAKE_DAMAGE_OK", 1.0)) return 1;
        std::printf("TAKE_DAMAGE_OK\n");
        return 0;
    }
    if (scenario == "valid") {
        if (!ExpectNumber("PHASE1_OK", 1.0)) return 1;
        if (!ExpectNumber("PHASE2_OK", 1.0)) return 1;
        // 现在有 5 次调用：2 次老用例 + 3 次带可选参数的新用例
        if (g_CallCount != 5) {
            std::printf("ISAAC_FAIL: HasCollectible must reach the engine exactly 5 times, got %d\n",
                        g_CallCount);
            return 1;
        }
        if (g_IgnoreModifiersTrueCount != 1) {
            std::printf("ISAAC_FAIL: ignoreModifiers=true must reach the engine exactly once, got %d\n",
                        g_IgnoreModifiersTrueCount);
            return 1;
        }
        if (g_CallEntity != AddressOf(g_PlayerBytes)) {
            std::printf("ISAAC_FAIL: x0 must be the Entity_Player address (got %llx, want %llx)\n",
                        static_cast<unsigned long long>(g_CallEntity),
                        static_cast<unsigned long long>(AddressOf(g_PlayerBytes)));
            return 1;
        }
        if (g_CallId != 2) {
            std::printf("ISAAC_FAIL: the last collectible id must be 2, got %u\n", g_CallId);
            return 1;
        }
        // 2026-09-16 写通道：Lua 侧 `player.ControlsCooldown = 2` 必须**真的落进引擎内存**。
        // 这里**故意写死字面偏移 0x404**，不跟实现侧的 `kEntityPlayerControlsCooldownOffset` 走
        // —— 夹具跟着常量走会两边一起错、断言永远绿（见 `docs/错误复盘.md` 2026-09-16 第一条）。
        // 第二帧 Lua 又写了一次 5（句柄已失效）⇒ 必须**没有**写进去，值仍是 2。
        std::int32_t cooldown = 0;
        std::memcpy(&cooldown, g_PlayerBytes.data() + 0x404, sizeof(cooldown));
        if (cooldown != 2) {
            std::printf("ISAAC_FAIL: ControlsCooldown at +0x404 must be 2 after the write "
                        "(stale-handle write must be ignored), got %d\n", cooldown);
            return 1;
        }
        // 批次 212：`Velocity`(+0x334) / `Position`(+0x310) 是 Vector2（两个 float），
        // `ControlsEnabled`(+0x400) 是 **1 字节** bool。偏移同样**写字面值**（夹具不许跟实现侧的
        // 常量走，否则两边一起错、断言永远绿）。
        float velocity[2] = {0.0F, 0.0F};
        float position[2] = {0.0F, 0.0F};
        std::memcpy(velocity, g_PlayerBytes.data() + 0x334, sizeof(velocity));
        std::memcpy(position, g_PlayerBytes.data() + 0x310, sizeof(position));
        if (velocity[0] != 1.5F || velocity[1] != -2.5F) {
            std::printf("ISAAC_FAIL: Velocity at +0x334 must be (1.5, -2.5), got (%f, %f)\n",
                        static_cast<double>(velocity[0]), static_cast<double>(velocity[1]));
            return 1;
        }
        if (position[0] != 80.0F || position[1] != 280.0F) {
            std::printf("ISAAC_FAIL: Position at +0x310 must be (80, 280), got (%f, %f)\n",
                        static_cast<double>(position[0]), static_cast<double>(position[1]));
            return 1;
        }
        // `ControlsEnabled` 只占 1 字节：夹具在它前后各放一个诱饵字节（按 4 字节写会踩到它们）。
        const std::uint8_t controlsEnabled = g_PlayerBytes[0x400];
        const std::uint8_t beforeEnabled = g_PlayerBytes[0x3FF];
        const std::uint8_t afterEnabled = g_PlayerBytes[0x401];
        if (controlsEnabled != 0u || beforeEnabled != kEnabledNeighbourBefore ||
            afterEnabled != kEnabledNeighbourAfter) {
            std::printf("ISAAC_FAIL: ControlsEnabled at +0x400 must be a single 0 byte with its "
                        "neighbours untouched, got %u / %u / %u\n",
                        static_cast<unsigned>(beforeEnabled), static_cast<unsigned>(controlsEnabled),
                        static_cast<unsigned>(afterEnabled));
            return 1;
        }
        // ★ 批次 405：六个战斗属性必须**真的落进引擎内存**（偏移写字面值，不跟实现侧常量走）。
        // Lua 侧第一帧写的是 Damage=12.5 / MoveSpeed=2.25 / MaxFireDelay=5.5 / ShotSpeed=1.75 /
        // Luck=8.5 / TearRange=123.5；第二帧（句柄失效）不碰它们 ⇒ 这里读到的就是那些值。
        struct StatCheck { const char* name; std::uintptr_t offset; float want; };
        const StatCheck stats[] = {
            {"MaxFireDelay", 0x1834, 5.5F},
            {"ShotSpeed", 0x1838, 1.75F},
            {"Damage", 0x1844, 12.5F},
            {"MoveSpeed", 0x194C, 2.25F},
            {"Luck", 0x1950, 8.5F},
            {"TearRange", 0x1854, 123.5F},
        };
        for (const StatCheck& stat : stats) {
            float got = 0.0F;
            std::memcpy(&got, g_PlayerBytes.data() + stat.offset, sizeof(got));
            if (got != stat.want) {
                std::printf("ISAAC_FAIL: %s at +0x%llX must be %.2f after the write, got %.3f\n",
                            stat.name, static_cast<unsigned long long>(stat.offset),
                            static_cast<double>(stat.want), static_cast<double>(got));
                return 1;
            }
        }
    } else if (g_CallCount != 0) {
        std::printf("ISAAC_FAIL: no engine call is allowed without a validated player, got %d\n",
                    g_CallCount);
        return 1;
    }

    std::printf("ENTITY_PLAYER_OK scenario=%s engine_calls=%d\n", scenario.c_str(), g_CallCount);
    if (scenario == "null_costume_guard") {
        // 批次 141：把"兜底挡了几次 / 最后一次收到的编号 / 判定不了几次 / 真调进引擎几次"打给
        // Python 侧。**这是本场景唯一的硬证据** —— 宿主上引擎不存在，Lua 侧只能断言"不报错"，
        // 而"有没有被挡下"只有这几格说得清（设备上读的是同一批全局量）。
        const isaac::runtime::ApiRowStats stats = isaac::runtime::ApiRowStatsSnapshot();
        std::printf("COSTUME_GUARD rejects=%u reason=%u last=%d unknown=%u trampoline=%u\n",
                    stats.rejectGuard, stats.lastRejectReason,
                    static_cast<int>(stats.nullCostumeLastRequestedId),
                    stats.nullCostumeGuardUnknown,
                    g_HostEngineCallTrampolineCalls - trampolineBefore);
    }
    if (scenario == "valid") {
        // 两帧的 Lua 侧结论都已经由 `ExpectNumber` 核对过，这里只是把标记打出来给 Python 侧看。
        std::printf("PHASE1_OK PHASE2_OK\n");
    }
    return 0;
}
'''

SCRIPT = r'''
local mod = RegisterMod('EntityPlayer view', 1)

local function check(condition, message)
  if not condition then error(message, 2) end
end

-- 引擎基址发布到 Lua 侧（宿主测试专用入口；设备构建里不存在）。
local savedPlayer = nil
local frame = 0

local function describe(value)
  if value == nil then return 'nil' end
  return type(value) .. ':' .. tostring(value)
end

-- 拿不到玩家的场景：任何下标都必须安静地返回 nil。
-- `Game:GetNumPlayers()` 报出的每一个下标都必须是**能拿到的**玩家；报 0 就必须承认没有玩家。
-- 两种可接受口径：①如实报引擎的元素个数（读成功，含 0）；②读失败时降级报 1，
-- 但那时 EID 走的是"单人快路径"（`main.lua:1065` 判 `numPlayers == 1`），不会进循环。
-- **不可接受**的是"报 1 且 `Isaac.GetPlayer(0)` 为 nil 且向量其实读得到且为空"。
local function verifyPlayerCountCoherence()
  local ok, count = pcall(function() return Game():GetNumPlayers() end)
  check(ok, 'Game:GetNumPlayers must not raise a Lua error')
  check(type(count) == 'number', 'Game:GetNumPlayers must return a number, got ' .. describe(count))
  local reachable = 0
  for index = 0, math.max(count, 1) - 1 do
    if Isaac.GetPlayer(index) ~= nil then reachable = reachable + 1 end
  end
  if count == 0 then
    check(reachable == 0, 'a zero player count must mean no reachable player')
  elseif count == 1 then
    check(reachable == 1,
          'a reported player count must never point at an unreachable player, got ' ..
          reachable .. ' of ' .. count)
  else
    check(reachable == count,
          'the reported player count must match the reachable players, got ' ..
          reachable .. ' of ' .. count)
  end
  PLAYER_COUNT = count
  PLAYER_REACHABLE = reachable
end

local function verifyUnavailable()
  for _, index in ipairs({ 0, 1, 99 }) do
    local ok, value = pcall(function() return Isaac.GetPlayer(index) end)
    check(ok, 'Isaac.GetPlayer must not raise a Lua error for index ' .. index)
    check(value == nil, 'Isaac.GetPlayer(' .. index .. ') must be nil, got ' .. describe(value))
  end
  local negativeOk, negative = pcall(function() return Isaac.GetPlayer(-1) end)
  check(negativeOk, 'Isaac.GetPlayer(-1) must not raise a Lua error')
  check(negative == nil, 'Isaac.GetPlayer(-1) must be nil, got ' .. describe(negative))
  local typeOk, typed = pcall(function() return Isaac.GetPlayer('nope') end)
  check(typeOk, 'Isaac.GetPlayer must not raise for a non-integer index')
  check(typed == nil, 'Isaac.GetPlayer must be nil for a non-integer index')
  -- 参数缺省时按 0 处理，拿不到玩家同样是 nil。
  local noneOk, none = pcall(function() return Isaac.GetPlayer() end)
  check(noneOk, 'Isaac.GetPlayer() must not raise a Lua error')
  check(none == nil, 'Isaac.GetPlayer() must be nil without a player')
  -- 批次 140：`Game:GetPlayer(index)` 在没有玩家时同样必须给 nil（PC 正文：任何玩家初始化之前
  -- 调用可以返回 nil）—— 这一档**不**许"夹到最后一个"，因为压根没有"最后一个"。
  do
    local gameOk, gamePlayer = pcall(function() return Game():GetPlayer(0) end)
    check(gameOk, 'Game:GetPlayer(0) must not raise a Lua error without a player')
    check(gamePlayer == nil, 'Game:GetPlayer(0) must be nil without a player, got '
          .. describe(gamePlayer))
  end
  -- **口径一致性（真机 01789207110 的根因）**：`Game:GetNumPlayers()` 与
  -- `Isaac.GetPlayer(i)` 对同一个引擎事实必须给出同一个答案。EID 的
  -- `features/eid_api.lua:2620` 就是 `for i = 0, game:GetNumPlayers() - 1 do local player = Isaac.GetPlayer(i)`
  -- 之后立刻索引 `player.QueuedItem`：只要 `GetNumPlayers()` 报了一个"读不到的玩家"，
  -- 那一帧就会抛错、回调被派发器静默摘除，屏幕全空而游戏不崩。
  verifyPlayerCountCoherence()
end

local function verifyFields(player)
  check(player.Type == 1, 'Type must be ENTITY_PLAYER (1), got ' .. describe(player.Type))
  check(player.Variant == 0, 'Variant must be 0, got ' .. describe(player.Variant))
  check(player.SubType == 0, 'SubType must be 0, got ' .. describe(player.SubType))
  -- 批次 4 起 `Entity.Index` 读 `Entity+0x30`（`Room::AddEntity` 的 `str w8,[x1,#0x30]`），
  -- 不再是"玩家在 players 向量里的下标"（`+0x19F0`，已不再作为 Lua 字段暴露）。
  check(player.Index == 7, 'Index must be the room list index (7), got ' .. describe(player.Index))
  check(player.PlayerType == 0, 'PlayerType must be 0 (Isaac), got ' .. describe(player.PlayerType))
  check(player:GetPlayerType() == player.PlayerType,
        'GetPlayerType must read the same field as PlayerType')
  check(type(player.Size) == 'number' and math.abs(player.Size - 12.5) < 0.001,
        'Size must be the entity radius, got ' .. describe(player.Size))
  local position = player.Position
  check(type(position) == 'userdata', 'Position must be a Vector, got ' .. describe(position))
  check(math.abs(position.X - 80.0) < 0.001 and math.abs(position.Y - 280.0) < 0.001,
        'Position must be (80, 280), got (' .. position.X .. ', ' .. position.Y .. ')')
  -- 必须是**新的** Vector：改它不能影响下一次读取（别名会让 Mod 改到别人的值）。
  position.X = -1
  position.Y = -1
  local again = player.Position
  check(math.abs(again.X - 80.0) < 0.001 and math.abs(again.Y - 280.0) < 0.001,
        'Position must return a fresh Vector on every read')
  -- 未知字段仍然是 nil（`__index` 不能凭空造值）。
  check(player.NotAThing == nil, 'an unknown field must be nil')
  -- 2026-09-16 新增字段（偏移证据见 `runtime_constants.hpp` 的同名常量注释）：
  --   * 四个战斗属性是 **float**（夹具给 4.25 / 1.5 / 7.5 / 300.0 这种非整数 ⇒ 按整数读会失败）；
  --   * `CanFly` 是 **1 字节布尔**（夹具在前后各放了一个单字节诱饵 ⇒ 按 4 字节读会读到诱饵）；
  --   * `ControlsCooldown` 是**有符号** int32（夹具 -3 ⇒ 无符号读会给出 4294967293）。
  --   * 收藏品没有 `MimicCharge`（那是卡/胶囊的字段）⇒ 必须是 nil。
  check(player.Damage == 4.25, 'Damage must come from +0x1844, got ' .. describe(player.Damage))
  check(player.MoveSpeed == 1.5,
        'MoveSpeed must come from +0x194C, got ' .. describe(player.MoveSpeed))
  check(player.MaxFireDelay == 7.5,
        'MaxFireDelay must come from +0x1834 (float, not int), got '
        .. describe(player.MaxFireDelay))
  check(player.TearRange == 300.0,
        'TearRange must come from +0x1854, got ' .. describe(player.TearRange))
  -- ★ 批次 405：`ShotSpeed`(+0x1838) 是 `MaxFireDelay`(+0x1834) 的高 4 字节，同族 float。
  check(player.ShotSpeed == 2.5,
        'ShotSpeed must come from +0x1838 (float), got ' .. describe(player.ShotSpeed))
  -- ★ 2026-10-01（批次 257）：`Luck` 是 **float**，偏移 `+0x1950`（夹具给 -3.25，且旧偏移
  --   `+0x1920` 特意写了 int32 `7` 当诱饵）⇒ 读错偏移 / 按整数读都必然失败。
  check(player.Luck == -3.25,
        'Luck must be the **float** at +0x1950 (NOT the int32 at +0x1920), got '
        .. describe(player.Luck))
  check(player.CanFly == true,
        'CanFly must be the byte at +0x1954 (1 = true), got ' .. describe(player.CanFly))
  check(type(player.CanFly) == 'boolean', 'CanFly must be a boolean, got ' .. describe(player.CanFly))
  check(player.ControlsCooldown == -3,
        'ControlsCooldown must be a **signed** int32 at +0x404, got '
        .. describe(player.ControlsCooldown))
  check(player.MimicCharge == nil,
        'a collectible must not expose MimicCharge, got ' .. describe(player.MimicCharge))

  -- ---------------------------------------------------------------------------
  -- 写通道（2026-09-16）：`EntityPlayer.ControlsCooldown` 是**可写**成员
  -- ---------------------------------------------------------------------------
  -- EID 的用法是 `player.ControlsCooldown = 2`（`features/eid_bagofcrafting.lua:877`、
  -- `features/eid_holdmapdesc.lua:669`：背包 / 按住地图时"吃掉"随后的按键）。
  -- 此前元表没有 `__newindex` ⇒ 这两句会抛 "attempt to index a userdata value"，
  -- 整条回调被派发器摘除（画面正常但功能消失）。
  check(player.ControlsCooldown == -3,
        'before the write the field must still be the fixture value (-3), got '
        .. describe(player.ControlsCooldown))
  local writeOk, writeError = pcall(function() player.ControlsCooldown = 2 end)
  check(writeOk, 'player.ControlsCooldown = 2 must not raise: ' .. tostring(writeError))
  check(player.ControlsCooldown == 2,
        'the write must be visible to the next read, got ' .. describe(player.ControlsCooldown))
  -- 引擎内存里的那个字必须真的变了（harness 在派发结束后核对 +0x404 的四字节）。
  CONTROLS_WRITE_OK = 1

  -- ---------------------------------------------------------------------------
  -- 批次 212（2026-09-30）：`Velocity` / `Position` / `ControlsEnabled` 也必须可写
  -- ---------------------------------------------------------------------------
  -- MCM 打开菜单时冻住玩家：`modconfig.lua:1625 player.Velocity = vecZero`、
  -- `:1630 player.Position = …`、`:1632 player.ControlsEnabled = false`。
  -- 我们原来只认 `ControlsCooldown` ⇒ 第 1625 行就抛错 ⇒ **渲染回调每帧中断** ⇒
  -- 菜单永远画不出来（真机症状："按右摇杆 UI 不见了、菜单一片空白、也没声音"）。
  local velOk, velError = pcall(function() player.Velocity = Vector(1.5, -2.5) end)
  check(velOk, 'player.Velocity = Vector(...) must not raise: ' .. tostring(velError))
  local posOk, posError = pcall(function() player.Position = Vector(80, 280) end)
  check(posOk, 'player.Position = Vector(...) must not raise: ' .. tostring(posError))
  local ctlOk, ctlError = pcall(function() player.ControlsEnabled = false end)
  check(ctlOk, 'player.ControlsEnabled = false must not raise: ' .. tostring(ctlError))
  -- 写完要**读得回来**（模组会写完再读；只写不读就不是 PC 语义）：
  check(player.Velocity.X == 1.5 and player.Velocity.Y == -2.5,
        'the Velocity write must be visible to the next read, got '
        .. describe(player.Velocity.X) .. '/' .. describe(player.Velocity.Y))
  check(player.Position.X == 80 and player.Position.Y == 280,
        'the Position write must be visible to the next read, got '
        .. describe(player.Position.X) .. '/' .. describe(player.Position.Y))
  check(player.ControlsEnabled == false,
        'the ControlsEnabled write must be visible to the next read, got '
        .. describe(player.ControlsEnabled))
  -- 引擎内存里的那几格必须真的变了（harness 按**字面偏移**核对：+0x334/+0x338、+0x310/+0x314、+0x400）。
  FIELDS_WRITE_OK = 1

  -- ---------------------------------------------------------------------------
  -- 批次 405（2026-10-07）：六个战斗属性也必须可写
  -- ---------------------------------------------------------------------------
  -- Trinity 在 `MC_EVALUATE_CACHE` 处理器里写 `player.Damage`（`main.lua:85`）与
  -- `player.MoveSpeed` / `player.Luck` / `player.MaxFireDelay`（`:116`）。
  -- 我们原来拒写 ⇒ 每次属性重算都抛错 ⇒ 那条回调被派发器摘掉 ⇒ 自定义角色的属性调整整块失效。
  -- PC 契约对这几格反复写 "Player stat - Only change this in MC_EVALUATE_CACHE" ⇒ 都是可写成员。
  -- ★ 写法与模组一致：`player[名字] = 数值`；写完立刻读回来（只写不读就不是 PC 语义）。
  -- ★ 值取**非整数**（.5/.25）：按整数写会丢小数，这里会当场抓到。
  local statWrites = {
    { 'Damage', 12.5 }, { 'MoveSpeed', 2.25 }, { 'MaxFireDelay', 5.5 },
    { 'ShotSpeed', 1.75 }, { 'Luck', 8.5 }, { 'TearRange', 123.5 },
  }
  for _, entry in ipairs(statWrites) do
    local name, value = entry[1], entry[2]
    local ok, err = pcall(function() player[name] = value end)
    check(ok, 'player.' .. name .. ' = ' .. value .. ' must not raise: ' .. tostring(err))
    check(math.abs(player[name] - value) < 0.001,
          'the ' .. name .. ' write must be visible to the next read, got ' .. describe(player[name]))
  end
  -- 引擎内存里那六格必须真的变了（harness 按**字面偏移** 0x1834/0x1838/0x1844/0x194C/0x1950/0x1854 核对）。
  STATS_WRITE_OK = 1

  -- 不认识的字段名**仍然报错**（故意的：防拼错被静默吞掉）—— 但要能被读数看见（探针计数）。
  local badNameOk, badNameError = pcall(function() player.NotAThingEither = 1 end)
  check(not badNameOk, 'an unknown EntityPlayer field must still raise on write')

  -- 只有放行的那几个字段可写：别的字段名必须报错（不许静默吞掉笔误）。
  local unknownOk, unknownError = pcall(function() player.NotAThing = 1 end)
  check(not unknownOk, 'writing an unknown EntityPlayer field must raise')
  check(string.find(tostring(unknownError), 'read-only', 1, true) ~= nil,
        'the error must say the remaining fields are read-only, got ' .. tostring(unknownError))
  -- ★ 批次 405：拒写文案必须把新放行的字段名列出来（否则读者会以为它们不可写）。
  for _, allowed in ipairs({ 'Damage', 'MoveSpeed', 'MaxFireDelay', 'ShotSpeed', 'Luck', 'TearRange' }) do
    check(string.find(tostring(unknownError), allowed, 1, true) ~= nil,
          'the read-only message must list the newly allowed field ' .. allowed
          .. ', got ' .. tostring(unknownError))
  end
  -- 类型不对也不许写进去（`luaL_checknumber` 会抛）。
  local typeOk, typeError = pcall(function() player.ControlsCooldown = 'two' end)
  check(not typeOk, 'a non-integer ControlsCooldown must raise, got ' .. tostring(typeError))
  local statTypeOk = pcall(function() player.Damage = 'lots' end)
  check(not statTypeOk, 'a non-number Damage must raise (luaL_checknumber)')

  -- 批次 6（2026-09-12）：EID 逐帧调用的一批成员。缺任何一个都是 "attempt to call a nil value"，
  -- 而派发器会**静默摘除**整条回调（真机报告 `01789210946` 的 `player:GetPill(0)` 就是这样）。
  -- 这一段先钉"名字在、不抛错、返回类型对"；其中**返回恒定值**的那些（引擎里还没定位到字段的桩）
  -- 由紧接着的 `constant...` 段**逐条钉住那个常量本身** —— 类型对不等于语义对（098 的教训：
  -- `Room:GetGridPath` 类型一直是数字，值一直是错的）。
  -- 无参成员：返回数字。
  local zeroNoArg = { 'GetNumKeys', 'GetNumBombs', 'GetNumCoins', 'GetHearts', 'GetMaxHearts',
                      'GetSoulCharge', 'GetBloodCharge', 'GetPoopMana', 'GetPoopSpell',
                      'GetZodiacEffect', 'GetModelingClayEffect' }
  -- ★ 批次 184（2026-09-28）：`GetGlyphOfBalanceDrop` **从本集合移出** —— 它现在是
  --   "收 2 个整数、返回一张表"（见下面的单测），既不是无参、也不再是恒 0。
  for _, name in ipairs(zeroNoArg) do
    local ok, value = pcall(function() return player[name](player) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(type(value) == 'number', name .. ' must return a number, got ' .. describe(value))
  end
  -- ★ 批次 128：上面这一族的**没有字段可读**的成员返回的是恒定值（恒 0），它们都登记在
  -- `api_deviation.cpp`（0x0E01003A/0x0E01003E/0x0E01003F/0x0E010040/0x0E010041）。
  -- 这里把"恒"这件事本身钉住：只钉类型的话，"一直是 0 却被模组当真值用"这种静默失效没有任何
  -- 东西拦得住（模组拿 0 做算术**不报错、不崩**，只是结论错）。改实现拿到真值时必须同步改这条断言
  -- 与那条偏离登记 —— 这正是"两条台账互相咬住"的意思。
  -- ★ 批次 184（2026-09-28）：原来这条清单里的第 6 条（`0x0E010042` = `GetGlyphOfBalanceDrop`）
  --   **已经还掉了** ⇒ 它从本集合移出，改由下面那段"返回表"的断言单独钉住。
  -- ★★ 批次 195（2026-09-29）：这一族**空了** —— 原来在册的四条（`GetHearts` / `GetPoopMana` /
  --   `GetPoopSpell` / `GetModelingClayEffect`）都拿到了字段偏移，改成**真读数**（见下面那组
  --   "字段直读"断言）。留这个空表是为了让下一个人知道"这里原来钉的是什么、为什么现在没有了"。
  local constantZeroNoArg = {}
  for _, name in ipairs(constantZeroNoArg) do
    local ok, value = pcall(function() return player[name](player) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(value == 0,
          name .. ' is a registered constant placeholder (api_deviation.cpp): it must answer exactly 0, got '
          .. describe(value))
  end
  -- ★★ 批次 195：组 A 五条改成**真读数**之后的判据（夹具里的字面值见 C++ 侧 `FillPlayer`）。
  --   每条都同时钉住"读的是那一格"与"越界不许读到邻格"：
  check(player:GetHearts() == 7,
        'GetHearts must read +0x16BC (fixture 7, half-hearts), got ' .. describe(player:GetHearts()))
  check(player:GetPoopMana() == 7,
        'GetPoopMana must read +0x269C (fixture 7), got ' .. describe(player:GetPoopMana()))
  check(player:GetPoopSpell(0) == 1 and player:GetPoopSpell(5) == 6,
        'GetPoopSpell must index +0x26A0..+0x26A5 (fixtures 1..6), got '
        .. describe(player:GetPoopSpell(0)) .. '/' .. describe(player:GetPoopSpell(5)))
  check(player:GetPoopSpell(6) == 0 and player:GetPoopSpell(-1) == 0
        and player:GetPoopSpell(100) == 0,
        'GetPoopSpell out of range must answer 0 (never read +0x26A6 or beyond), got '
        .. describe(player:GetPoopSpell(6)) .. '/' .. describe(player:GetPoopSpell(-1)) .. '/'
        .. describe(player:GetPoopSpell(100)))
  check(player:GetModelingClayEffect() == 166,
        'GetModelingClayEffect must read +0x2730 (fixture 166), got '
        .. describe(player:GetModelingClayEffect()))
  check(player:GetPlayerFormCounter(0) == 3 and player:GetPlayerFormCounter(1) == 0
        and player:GetPlayerFormCounter(14) == 7,
        'GetPlayerFormCounter must index +0x1C54 + form*4 (fixtures 3/0/7), got '
        .. describe(player:GetPlayerFormCounter(0)) .. '/' .. describe(player:GetPlayerFormCounter(1))
        .. '/' .. describe(player:GetPlayerFormCounter(14)))
  check(player:GetPlayerFormCounter(15) == 0 and player:GetPlayerFormCounter(-1) == 0
        and player:GetPlayerFormCounter(100) == 0,
        'GetPlayerFormCounter out of range must answer 0 (never read +0x1C90), got '
        .. describe(player:GetPlayerFormCounter(15)) .. '/'
        .. describe(player:GetPlayerFormCounter(-1)) .. '/'
        .. describe(player:GetPlayerFormCounter(100)))
  -- ★ 批次 184（2026-09-28）：`GetGlyphOfBalanceDrop(variant, subtype)` **不再恒 0** ——
  --   它现在走 `EngineCallShape::Ref2U32Pair` 数据行（批次 184 新增的形状）：收 2 个整数、
  --   真调引擎 `0x2FE574`、返回**一张两元表** `{[1]=variant, [2]=subtype}`。
  --   这条 API 的**形状口径没有 PC 文档可对齐**（它是 Repentogon 才有的，`tools/pc_contract_docs/`
  --   里查不到）⇒ 口径取它**唯一的消费者 EID**：`features/eid_repentogon.lua:265` 里
  --   `local t = player:GetGlyphOfBalanceDrop(Variant, SubType)` 之后读 `t[1]`（与 `-1` 比）
  --   与 `t[2]`。
  --   ★ 宿主上的语义要说清楚：引擎调用被跳板清零（`engine_call_trampoline_host_stub.cpp`）
  --     ⇒ 引擎**不会改写**我们造的那两个"出参槽" ⇒ 表里就是**入参原样**。所以这里传 `(7, 9)`
  --     断言拿回 `{[1]=7, [2]=9}`：它证明的是"**参数进得去、表出得来、两个字段都是整数**"。
  --     **值对不对（引擎算出来的掉落物）宿主证明不了，只能真机验** —— 汇报时不许把这条说成"值已验真"。
  do
    local ok, dropTable = pcall(function() return player:GetGlyphOfBalanceDrop(7, 9) end)
    check(ok, 'GetGlyphOfBalanceDrop(7, 9) must not raise: ' .. tostring(dropTable))
    check(type(dropTable) == 'table',
          'GetGlyphOfBalanceDrop must return a table (EID reads t[1]/t[2]), got '
          .. describe(dropTable))
    check(dropTable[1] == 7 and dropTable[2] == 9,
          'GetGlyphOfBalanceDrop must pass both arguments through the engine out-slots, got [1]='
          .. describe(dropTable[1]) .. ' [2]=' .. describe(dropTable[2]))
  end
  -- 字段读取型 API（**数据行**机制，见 `field_api.hpp`）：值必须来自伪造内存里那几个偏移，
  -- 而不是像以前的桩那样返回硬编码 0；`GetBabySkin` 还要证明是**有符号**读。
  check(player:GetMaxHearts() == 6,
        'GetMaxHearts must read the heart-container field (+0x16B8), got '
        .. describe(player:GetMaxHearts()))
  check(player:GetSoulHearts() == 4,
        'GetSoulHearts must read the soul-heart field (+0x16C4), got '
        .. describe(player:GetSoulHearts()))
  check(player:GetBabySkin() == -1,
        'GetBabySkin must be a signed read (non-baby = -1), got ' .. describe(player:GetBabySkin()))
  -- 求和口径：容器是"按 id 的计数"（`{1,0,0,0,2,0}`）⇒ 总数 = 3。
  -- 这条断言同时排除三种错口径：格子数（6）、非零格子数（2）、以及恒为 0 的桩。
  check(player:GetCollectibleCount() == 3,
        'GetCollectibleCount must sum the per-id counts, got '
        .. describe(player:GetCollectibleCount()))
  -- 参数个数不对：共享处理器要按 catalog 里的 `owner:name` 现拼消息（与手写时代逐字一致）。
  local okArity, arityError = pcall(function() return player:GetMaxHearts(1) end)
  check(not okArity and string.find(tostring(arityError),
        'EntityPlayer:GetMaxHearts accepts no arguments', 1, true) ~= nil,
        'wrong arity must name the method, got ' .. tostring(arityError))
  -- 带槽位参数的成员：同样返回数字（药丸/卡片/饰品/表单计数都是"没有就是 0"）。
  local zeroSlotted = { 'GetPill', 'GetCard', 'GetCollectibleNum', 'GetTrinketMultiplier' }
  for _, name in ipairs(zeroSlotted) do
    local ok, value = pcall(function() return player[name](player, 0) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(type(value) == 'number', name .. ' must return a number, got ' .. describe(value))
  end
  -- ★ 批次 177（2026-09-28）：`GetPill` / `GetCard` / `GetZodiacEffect` / `HasPlayerForm` /
  -- `CanPickRedHearts` 这五条**已经不再返回硬编码的恒定假值** —— 它们改走引擎方法数据行
  -- （`kEntityPlayerEngineRows`，值来自 `Entity_Player::GetPill(int)` 那一族；逐条证据见
  -- `runtime_constants.hpp`）。所以它们从下面这几条"恒定值"名单里移除了。
  -- ★ 注意宿主上的表现**看不出来**：这个 harness 里没有引擎，跳板的宿主占位把返回值格子清零
  -- （`engine_call_trampoline_host_stub.cpp`）⇒ `GetPill(0)` 照样是 0、`CanPickRedHearts()` 照样
  -- 是 false。真正"值来自引擎"的验收只能在真机上做（读数面判据见 177 的改动日志）。
  -- 「这五条确实接上了引擎、且旧假桩真的删了」由 `runtime/tests/test_id_argument_policy.py` 钉。
  -- ★ 批次 128：下面这些是**登记在案的恒定值**（`api_deviation.cpp`），这里钉住那个常量本身
  -- （只钉类型的话，"一直是 0 却被模组当真值用"这种静默失效没有任何东西拦得住；
  -- 模组拿 0 做算术**不报错、不崩**，只是结论错）。改实现拿到真值时必须同步改这条断言
  -- 与那条偏离登记 —— 这正是"两条台账互相咬住"的意思。
  -- ★ 批次 195：`GetPlayerFormCounter` **从本集合移出**（它现在读 `+0x1C54` 的真值，见上面那组断言）。
  local constantZeroSlotted = {}
  for _, name in ipairs(constantZeroSlotted) do
    local ok, value = pcall(function() return player[name](player, 0) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(value == 0,
          name .. ' is a registered constant placeholder (api_deviation.cpp): it must answer exactly 0, got '
          .. describe(value))
  end
  -- 可能为 nil 的对象/id：PC 上"没有就是这个结果"，比编一个假对象安全。
  -- ★ 批次 132（2026-09-25）更正：`GetMainTwin` **不在这一组**。它当初被写进"恒 nil"里，
  -- 而 PC 文档 `EntityPlayer.md:1057` 明写 "When called on any other character, returns that
  -- character" ⇒ 普通角色返回**自己**。这条错误在真机上咬过一次（见下面消费者视角那段）。
  local nilNoArg = {}  -- GetName现返回原生字符串，专用真实实体名字回归覆盖。
  for _, name in ipairs(nilNoArg) do
    local ok, value = pcall(function() return player[name](player) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(value == nil, name .. ' must be nil by default, got ' .. describe(value))
  end
  -- ★ 批次 132（2026-09-25，真机实测教训）：**消费者视角**判据。EID 拼"长子名分"描述时写的是
  -- `player:GetMainTwin():GetPlayerType()`（`features/eid_modifiers.lua:420`）。旧实现让它恒 nil
  -- ⇒ 这一句在真机上抛 "attempt to index a nil value" ⇒ 派发器把**整条 MC_POST_RENDER 回调摘掉**
  -- （用户看到的正是"站在长子名分旁边 EID 不显示信息"）。
  -- ⇒ 只钉"返回值等于 nil 还是自己"是不够的（批次 128 就是这么钉的，结果把错误行为钉住了）：
  -- 必须**照模组那样链下去**。PC 契约 `EntityPlayer.md:1050-1057`：普通角色返回自己
  -- ⇒ `GetMainTwin() == player`，链出来的类型也就等于自己的类型（EID 那个 `== playerID` 因此成立）。
  local mainTwin = player:GetMainTwin()
  check(mainTwin ~= nil,
        'GetMainTwin must not be nil for an ordinary character (PC: returns that character)')
  check(mainTwin == player, 'GetMainTwin must return the player itself, got ' .. describe(mainTwin))
  local chainOk, chained = pcall(function() return player:GetMainTwin():GetPlayerType() end)
  check(chainOk, 'eid_modifiers.lua:420 chains GetMainTwin():GetPlayerType() - it must not raise: '
        .. tostring(chained))
  check(chained == player:GetPlayerType(),
        'the chained player type must equal the player own type, got ' .. describe(chained))
  -- ★ 批次 195（2026-09-29）：这四条 `Get*RNG` **不再恒 nil** —— 它们真读
  -- `Entity_Player + 0x1BB0/0x1BC8/0x1BE0/0x1BF8` 四张 `vector<RNG>`（索引即枚举 id）。
  -- 本夹具**没有**在玩家块上发布那四对 begin/end（`begin == 0`）⇒ 这里只能钉"读不到就给 nil、
  -- 且不抛错"这一档；**取值那一档**（换 id 读到另一格、四个偏移各自指对、快照语义、越界口径）
  -- 在 `runtime/tests/test_lua_entity_rng_and_fields.py` 里有专门的夹具与消费者视角断言。
  local nilSlotted = { 'GetCollectibleRNG', 'GetCardRNG', 'GetPillRNG' }
  for _, name in ipairs(nilSlotted) do
    local ok, value = pcall(function() return player[name](player, 0) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(value == nil, name .. ' must be nil when the vector is unreadable, got ' .. describe(value))
  end
  local okTrinketRng, trinketRng = pcall(function() return player:GetTrinketRNG(0) end)
  check(okTrinketRng, 'GetTrinketRNG must not raise: ' .. tostring(trinketRng))
  check(trinketRng == nil, 'GetTrinketRNG must be nil when the vector is unreadable')
  -- 布尔成员：`IsSubPlayer` 恒 false（登记在 `api_deviation.cpp` 的 0x0E01004D）。
  -- ★ 批次 177：`CanPickRedHearts` 与 `HasPlayerForm` 已从这份名单移出（改走引擎数据行）。
  -- ★ 批次 195：`HasGoldenBomb` 也移出（改成字段数据行，读 `+0x16D9`；见下面那两条断言）。
  -- 钉 `== false` 而不是"是个布尔"：模组的写法是 `if player:HasPlayerForm(x) then`，
  -- "恒 false"与"某天开始返回真值"都必须是这条断言能分辨的两件事。
  local booleanNoArg = { 'IsSubPlayer' }
  for _, name in ipairs(booleanNoArg) do
    local ok, value = pcall(function() return player[name](player) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(value == false,
          name .. ' is a registered constant placeholder (api_deviation.cpp): it must answer exactly false, got '
          .. describe(value))
  end
  -- ★ 批次 195：`HasGoldenBomb` 读的是夹具写进去的 `+0x16D9 = 1`（取值锚点见
  -- `runtime_constants.hpp` 的 `kEntityPlayerGoldenBombFlagOffset`）。
  check(player:HasGoldenBomb() == true,
        'HasGoldenBomb must read Entity_Player+0x16D9, got ' .. describe(player:HasGoldenBomb()))
  for _, name in ipairs({ 'HasTrinket' }) do
    local ok, value = pcall(function() return player[name](player, 0) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(value == false,
          'TRINKET_NONE must answer exactly false, got ' .. describe(value))
  end
  -- ★ 批次 133（2026-09-25）修掉"恒 false"；★ **批次 195（2026-09-29）起改成一次引擎调用**
  -- （`Entity_Player::HasTrinket @ 0x28D3B8`）—— 引擎自己就实现了 PC 文档的两种口径
  -- （`IgnoreModifiers=false` 走 `GetTrinketMultiplier`、`true` 扫两个饰品槽，比较前 `and #0x7fff`
  -- ⇒ 金色饰品不再答 false）。逐条理由见 `isaac_api.cpp` 那个 handler 的注释。
  --
  -- ⚠️ **宿主上拿不到返回值**：通用跳板的宿主占位把结果清零（`engine_call_trampoline_host_stub.cpp`）
  -- ⇒ 这里只能钉"不报错 + 返回布尔"；**参数形状与"无效 id 不调引擎"那一半**在
  -- `runtime/tests/test_lua_entity_rng_and_fields.py` 里逐帧核对跳板的 `x0/x1/x2`，
  -- **取值那一半要真机**（判据写在 `analysis/api-restore-entityplayer-b/spec.json` 的
  -- device_criteria 里）。
  for _, flag in ipairs({ false, true }) do
    local ok, value = pcall(function() return player:HasTrinket(30, flag) end)
    check(ok, 'HasTrinket(30, ' .. tostring(flag) .. ') must not raise: ' .. tostring(value))
    check(type(value) == 'boolean',
          'HasTrinket must return a boolean, got ' .. describe(value))
  end
  -- 一个参数也不传：PC 的 `IgnoreModifiers` 可省（等价于 false），同样不许报错。
  local okDefault, defaultValue = pcall(function() return player:HasTrinket(30) end)
  check(okDefault, 'HasTrinket(30) must not raise: ' .. tostring(defaultValue))
  -- `id = 0`（TRINKET_NONE）恒 false，且**不调引擎**（负/0/超 uint32 在被调方挡下）。
  check(player:HasTrinket(0) == false, 'TRINKET_NONE must answer false')
  check(player:HasTrinket(0, true) == false, 'TRINKET_NONE must answer false with IgnoreModifiers')
  -- `GetPoopSpell(int Position)`：PC 的签名带位置参数 ⇒ 带参数调用必须被接受。
  -- ★ 批次 195：值**不再是恒 0**（队列在 `+0x26A0` 的 6 格里，夹具写 1..6）—— 这里只钉
  -- "带参数调用不报错 + 读到的是那一格"，越界口径那两条在上面那组断言里。
  local okPoopSpell, poopSpell = pcall(function() return player:GetPoopSpell(0) end)
  check(okPoopSpell, 'GetPoopSpell(0) must not raise: ' .. tostring(poopSpell))
  check(poopSpell == 1, 'GetPoopSpell(0) must read the queue head (+0x26A0, fixture 1), got '
        .. describe(poopSpell))
  -- ★ 批次 133（2026-09-25，真机实测教训）：`HasTrinket` **不许再恒 false** —— EID 的"套装进度"
  -- 里饰品类靠它：`features/eid_api.lua:2574` 是
  --   `elseif 变体 == 饰品 and player:HasTrinket(id) then progress = progress + player:GetTrinketMultiplier(id)`
  -- 恒 false ⇒ 这一支**永不执行** ⇒ 含饰品的套装（Guppy 那类）永远少算。
  -- ★ 批次 195（2026-09-29）**口径变更**：`HasTrinket` 不再自己扫饰品槽，改成**一次引擎调用**
  -- （`Entity_Player::HasTrinket @ 0x28D3B8`；引擎自己就实现了 PC 的两种口径、并在比较前
  -- `and #0x7fff` ⇒ 旧实现"金色饰品答 false"随之消失）。
  -- ⇒ 宿主上**它的值取决于跳板**（占位实现把结果清零）⇒ 这里只能钉"夹具的饰品槽可读"与
  -- "调用不报错、返回布尔"；**取值那一半（握着答 true、金色饰品答 true）要真机**，
  -- 参数形状那一半由 `runtime/tests/test_lua_entity_rng_and_fields.py` 逐帧核对。
  -- 批次 133 那条"消费者视角"断言（握着 1 件必须累加到 1）因此**移到了真机判据**里
  -- （`analysis/api-restore-entityplayer-b/spec.json` 的 device_criteria），不再在宿主上假装成立。
  check(player:GetTrinket(0) == 30,
        'fixture: trinket slot 0 must read 30, got ' .. describe(player:GetTrinket(0)))
  -- 消费者视角这一半仍然可钉：拿返回值当闸门做算术**不许抛错**（空表/nil 会抛）。
  local trinketProgress = 0
  if player:HasTrinket(30) then
    trinketProgress = trinketProgress + player:GetTrinketMultiplier(30)
  end
  check(type(trinketProgress) == 'number',
        'the EID trinket-progress gate must keep working, got ' .. describe(trinketProgress))
  -- ★ 批次 137（2026-09-26）：`EntityPlayer:AddNullCostume(int)` —— The Specialist for Good Items
  -- 的舞蹈段落要用它（给玩家换上一套临时服装）。它走**引擎方法数据行**（`Void1`），宿主上的
  -- 通用跳板是**占位实现**（不真的跳），所以这里钉的是**消费者视角的边界**：
  --   ① 合法句柄 + 一个整数参数 ⇒ 不许报错（否则整条 `MC_POST_PICKUP` 类回调会被摘掉，
  --      用户看到的就是"捡到四级物品什么也没发生"）；
  --   ② 参数不是整数 ⇒ 按 PC 口径报错，且消息里要现拼出 `EntityPlayer:AddNullCostume`；
  --   ③ 少给参数 ⇒ 同样报错（"把判据放宽成永远通过"也要能被这条挡住）。
  local addOk, addError = pcall(function() return player:AddNullCostume(5) end)
  check(addOk, 'player:AddNullCostume(5) must not raise: ' .. tostring(addError))
  local addTypeOk, addTypeError = pcall(function() return player:AddNullCostume('x') end)
  check(not addTypeOk, 'a non-integer AddNullCostume argument must raise')
  check(string.find(tostring(addTypeError), 'EntityPlayer:AddNullCostume expects 1 argument(s)',
                    1, true) ~= nil,
        'the arity error must name EntityPlayer:AddNullCostume, got ' .. tostring(addTypeError))
  local addMissingOk = pcall(function() return player:AddNullCostume() end)
  check(not addMissingOk, 'AddNullCostume without an argument must raise')
  -- 同一批：`TryRemoveNullCostume(int)`（跳舞结束/物品丢掉时摘掉临时服装）—— 边界与上面逐条同形。
  local removeOk, removeError = pcall(function() return player:TryRemoveNullCostume(5) end)
  check(removeOk, 'player:TryRemoveNullCostume(5) must not raise: ' .. tostring(removeError))
  local removeTypeOk, removeTypeError = pcall(function() return player:TryRemoveNullCostume('x') end)
  check(not removeTypeOk, 'a non-integer TryRemoveNullCostume argument must raise')
  check(string.find(tostring(removeTypeError),
                    'EntityPlayer:TryRemoveNullCostume expects 1 argument(s)', 1, true) ~= nil,
        'the arity error must name EntityPlayer:TryRemoveNullCostume, got '
        .. tostring(removeTypeError))
  -- 此旧玩家夹具的真实熔炼向量是合法0/0/0，故返回空表；非空与失效行为由专用真实内存夹具验证。
  -- ★ 批次 388（2026-10-07）：`GetEffects` 已从这里**移出** —— 它现在返回带 17 个方法的
  --   `TemporaryEffects` 对象（"恒返回空表"那条偏离已还清），断言见本节后面。
  for _, name in ipairs({ 'GetSmeltedTrinkets' }) do
    local ok, value = pcall(function() return player[name](player) end)
    check(ok, name .. ' must not raise: ' .. tostring(value))
    check(type(value) == 'table' and next(value) == nil,
          name .. ' must reflect this fixture\'s actual empty native vector, got '
          .. describe(value))
  end
  -- ★ 批次 388（2026-10-07）：`player:GetEffects()` 必须返回一个**带方法**的对象，且链式调用不抛错
  --   —— 这正是原来坏掉的那条：旧实现返回空表 ⇒ `GetEffects():HasCollectibleEffect(id)` 抛
  --   `attempt to call a nil value` ⇒ 整条模组回调被派发器静默摘掉（minimapi 的小地图就是这么没的）。
  local effects = player:GetEffects()
  check(effects ~= nil, 'player:GetEffects() must answer an object, got ' .. describe(effects))
  check(type(effects) == 'userdata' or type(effects) == 'table',
        'player:GetEffects() must answer an object, got ' .. describe(effects))
  for _, name in ipairs({ 'HasCollectibleEffect', 'HasTrinketEffect', 'HasNullEffect',
                          'GetCollectibleEffectNum', 'GetTrinketEffectNum', 'GetNullEffectNum',
                          'AddCollectibleEffect', 'AddTrinketEffect', 'AddNullEffect',
                          'RemoveCollectibleEffect', 'RemoveTrinketEffect', 'RemoveNullEffect',
                          'ClearEffects', 'GetCollectibleEffect', 'GetNullEffect',
                          'GetTrinketEffect', 'GetEffectsList' }) do
    check(type(effects[name]) == 'function',
          'TemporaryEffects:' .. name .. ' must be a method, got ' .. describe(effects[name]))
  end
  -- 真实现的两条（走引擎方法数据行）：宿主跳板恒返回 0、且伪造模块里没有引擎代码
  -- （入口指纹对不上 ⇒ 共享处理器**静默降级**）⇒ 这里只要求"不抛错 + 返回 PC 同类型的值"。
  -- ★ 那 6 条 `Add*`/`Remove*` 是**手写**的、入口指纹对不上时**按设计报错**（同 `HasTrinket`），
  --   所以宿主上**不调用它们**（调用必抛）—— 只断言方法在不在（上面那一圈）。
  local hasOk, hasValue = pcall(function() return effects:HasCollectibleEffect(1) end)
  check(hasOk, 'GetEffects():HasCollectibleEffect(1) must not raise: ' .. tostring(hasValue))
  check(type(hasValue) == 'boolean',
        'HasCollectibleEffect must answer a boolean, got ' .. describe(hasValue))
  local numOk, numValue = pcall(function() return effects:GetCollectibleEffectNum(1) end)
  check(numOk, 'GetEffects():GetCollectibleEffectNum(1) must not raise: ' .. tostring(numValue))
  check(type(numValue) == 'number',
        'GetCollectibleEffectNum must answer a number, got ' .. describe(numValue))
  -- 夹具没有临时效果：查询nil，实时列表大小为0。
  local effectOk, effectValue = pcall(function() return effects:GetCollectibleEffect(1) end)
  check(effectOk, 'GetEffects():GetCollectibleEffect(1) must not raise: ' .. tostring(effectValue))
  check(effectValue == nil, 'No collectible effect exists in this fixture')
  local listOk, listValue = pcall(function() return effects:GetEffectsList() end)
  check(listOk, 'GetEffects():GetEffectsList() must not raise: ' .. tostring(listValue))
  check(type(listValue) == 'userdata' and listValue.Size == 0 and #listValue == 0,
        'Empty EffectList must expose Size 0, got ' .. describe(listValue))
  -- `player.QueuedItem` 是 EID 逐帧读 14 次的字段；PC 上它**永远是一张表**（`EntityPlayer.md:2016`）。
  -- ★ 批次 195（2026-09-29）：改成真读 `QueueItemData`（**内嵌**在 `+0x1C38`）——
  -- 夹具没写那四个字段（全 0，等于"没举着东西"）⇒ `Item` 是 nil，但 `Charge` **必须是数字**、
  -- `Touched` **必须是布尔**。旧实现返回空表 ⇒ `player.QueuedItem.Charge > 0` 会抛
  -- `attempt to compare nil with number`（EID 的逐帧回调会被派发器整条摘掉）。
  -- 取值那一档（举着东西时 `Item` 是句柄、`Charge`/`Touched` 是夹具里的值）在
  -- `runtime/tests/test_lua_entity_rng_and_fields.py` 里。
  local queued = player.QueuedItem
  check(type(queued) == 'table', 'player.QueuedItem must be a table, got ' .. describe(queued))
  check(queued.Item == nil, 'an empty queued item must have no Item')
  check(type(queued.Charge) == 'number',
        'QueuedItem.Charge must be a number even with nothing queued, got ' .. describe(queued.Charge))
  check(queued.Charge == 0, 'QueuedItem.Charge must be 0 here, got ' .. describe(queued.Charge))
  check(type(queued.Touched) == 'boolean',
        'QueuedItem.Touched must be a boolean, got ' .. describe(queued.Touched))
  check(queued.Touched == false, 'QueuedItem.Touched must be false here')
  check((queued.Charge > 0) == false, 'the EID comparison `QueuedItem.Charge > 0` must work')
end

local function verifyValid()
  local player = Isaac.GetPlayer(0)
  check(player ~= nil, 'Isaac.GetPlayer(0) must return an EntityPlayer')
  check(type(player) == 'userdata', 'GetPlayer must return a userdata, got ' .. describe(player))
  verifyFields(player)

  -- 方法：引擎侧的返回值必须原样往返（注入实现对 id == 1 回答 true）。
  check(player:HasCollectible(1) == true, 'HasCollectible(1) must be true')
  check(player:HasCollectible(2) == false, 'HasCollectible(2) must be false')
  -- PC 的第二个参数 `ignoreModifiers` 是可选的布尔（EID 会传 true，见 eid_api.lua:3004）
  check(player:HasCollectible(1, true) == true, 'HasCollectible(1, true) must be true')
  check(player:HasCollectible(2, false) == false, 'HasCollectible(2, false) must be false')
  check(player:HasCollectible(2, nil) == false, 'HasCollectible(2, nil) 按缺省处理')
  -- 批次 404（2026-10-07）：`AddCollectible` 越界 = **安全 no-op**（压 false、不抛错）。
  -- 模组里的常见写法是 `Isaac.GetItemIdByName("自定义道具")` —— 快照表 + 追加层都查不到时给 **-1**，
  -- 紧接着就喂给 `AddCollectible`。真机上我们一抛错就被派发器**静默摘掉整条回调**
  -- （`Trinity/main.lua:67`，报 `EntityPlayer:AddCollectible type is outside uint32 range` ——
  -- 本批 404 的起因）。契约（`EntityPlayer.md:137-139`）只写
  -- `void AddCollectible(CollectibleType Type, ...)`，**没有"越界报错"这一说** ⇒ 与批次 398 的
  -- `HasCollectible` 同形，改成"安全 no-op + false"。
  local oobOk, oobError = pcall(function() return player:AddCollectible(-1, 5) end)
  check(oobOk, 'AddCollectible(-1, 5) must not raise a Lua error: ' .. tostring(oobError))
  check(player:AddCollectible(-1, 5) == false,
        'AddCollectible(-1, 5) must answer false (safe no-op)')
  check(player:AddCollectible(-1) == false,
        'AddCollectible(-1) (type only) must answer false too')
  check(player:AddCollectible(-1, 5, true, 0, 0) == false,
        'AddCollectible(-1) with five args must answer false too')
  local same = player:ToPlayer()
  check(same == player, 'EntityPlayer:ToPlayer must return the player itself')
  -- 批次 4 起 `GetData` 返回 Runtime 自管的稳定表（EID 真的往里面写，见
  -- `features/eid_api.lua:2229`），同一个实体每次都必须是**同一张**表。
  local data = player:GetData()
  check(type(data) == 'table', 'GetData must return a table, got ' .. describe(data))
  check(data == player:GetData(), 'GetData must keep the same table for the same entity')
  data.MARK = 'entity-player'
  check(player:GetData().MARK == 'entity-player', 'a write must be visible through GetData')

  -- 只有一个玩家：越界必须返回 nil。
  check(Isaac.GetPlayer(1):GetPlayerType() == player:GetPlayerType(), 'invalid index returns the first player (fixed PC exe)')
  -- 同上：数量与可达玩家必须一致（本场景只有一个玩家）。
  verifyPlayerCountCoherence()
  check(PLAYER_COUNT == 1, 'the valid scenario has exactly one player, got ' .. PLAYER_COUNT)
  check(PLAYER_REACHABLE == 1, 'that one player must be reachable')
  check(Isaac.GetPlayer(99):GetPlayerType() == player:GetPlayerType(), 'invalid index returns the first player (fixed PC exe)')

  -- 批次 140：`Game:GetPlayer(index)` —— The Specialist for Good Items 的 `main.lua:446` 是 **1 基**循环
  -- （`for playerNum = 1, game:GetNumPlayers() do ... game:GetPlayer(playerNum)`），单人局第一句就是
  -- `GetPlayer(1)`。按 PC 契约 `Game.md:338` 的正文（徽章 `.alldlc`），下标"没被用上"（越界/负数）
  -- ⇒ **夹到最后一个玩家**；若按 `Isaac.GetPlayer` 那样给 nil，模组会在 `:450` 的
  -- `player:GetPlayerType()` 上抛错、整条 `MC_POST_NEW_ROOM` 回调被摘 —— 那正是本轮在修的现象。
  -- 断言一律比**字段值**（`Type`），不比 userdata 身份：两次调用各自压一个新句柄，
  -- 是否相等取决于元表有没有 `__eq`，那不在这条 API 的判据范围内。
  check(Game():GetPlayer(0).Type == player.Type, 'Game:GetPlayer(0) must reach the only player')
  check(Game():GetPlayer(1).Type == player.Type, 'Game:GetPlayer(1) must clamp to the only player')
  check(Game():GetPlayer(99).Type == player.Type, 'Game:GetPlayer(99) must clamp to the last player')
  check(Game():GetPlayer(-1).Type == player.Type,
        'Game:GetPlayer(-1) must clamp to the last player (PC text: the index was not used)')
  -- ★ 模组会在返回的句柄上**立刻链下去**（`player:GetPlayerType()`）⇒ 这里照它的样子链一次。
  check(Game():GetPlayer(1):GetPlayerType() ~= nil,
        'a clipped player must answer methods (the mod chains on it right away)')
  do
    local badOk, badValue = pcall(function() return Game():GetPlayer('x') end)
    check(badOk, 'Game:GetPlayer(string) must not raise a Lua error: ' .. tostring(badValue))
    check(badValue == nil, 'Game:GetPlayer(string) must be nil, got ' .. describe(badValue))
    local missingOk, missingValue = pcall(function() return Game():GetPlayer() end)
    check(missingOk, 'Game:GetPlayer() must not raise a Lua error: ' .. tostring(missingValue))
    check(missingValue == nil, 'Game:GetPlayer() must be nil, got ' .. describe(missingValue))
  end
  savedPlayer = player
  PHASE1_OK = 1
end

-- 第二帧：harness 已经把伪造的 vptr 改坏，句柄必须自证失效。
local function verifyInvalidatedHandle()
  check(savedPlayer ~= nil, 'the first frame must have produced a handle')
  check(Isaac.GetPlayer(0) == nil, 'GetPlayer must be nil once the vptr no longer matches')
  check(savedPlayer.Type == nil, 'an invalidated handle must not answer fields')
  check(savedPlayer.Position == nil, 'an invalidated handle must not answer Position')
  check(savedPlayer:GetPlayerType() == nil, 'GetPlayerType must be nil on an invalidated handle')
  -- 句柄失效时，字段读取型 API（数据行）也必须按各自**约定好的**降级值返回：
  -- 计数器回 0、婴儿皮肤回 -1（PC 的"非婴儿"就是 -1，回 0 会让 Mod 以为这是婴儿）。
  check(savedPlayer:GetMaxHearts() == 0,
        'GetMaxHearts on an invalidated handle must degrade to 0, got '
        .. describe(savedPlayer:GetMaxHearts()))
  check(savedPlayer:GetBabySkin() == -1,
        'GetBabySkin on an invalidated handle must degrade to -1, got '
        .. describe(savedPlayer:GetBabySkin()))
  -- 这一句在 harness 侧被核对：它不许再到达引擎（调用计数必须停在 2）。
  check(savedPlayer:HasCollectible(1) == false,
        'HasCollectible on an invalidated handle must degrade to false')
  -- 批次 137：`AddNullCostume` 是**数据行**（共享处理器）⇒ 句柄失效时按设计**静默降级**
  -- （接收者拿不到 ⇒ 不做引擎调用、不报错），与手写的 `HasCollectible` 同口径。
  local staleAddOk, staleAddError = pcall(function() return savedPlayer:AddNullCostume(5) end)
  check(staleAddOk, 'AddNullCostume on an invalidated handle must not raise: '
        .. tostring(staleAddError))
  local staleRemoveOk, staleRemoveError = pcall(function() return savedPlayer:TryRemoveNullCostume(5) end)
  check(staleRemoveOk, 'TryRemoveNullCostume on an invalidated handle must not raise: '
        .. tostring(staleRemoveError))
  -- 写通道也一样：句柄失效时**不许**往那个地址写（那可能是别人的内存）。
  -- harness 会在派发结束后核对 +0x404 仍是第一帧写的 2（没被这一句改成 5）。
  local staleOk, staleError = pcall(function() savedPlayer.ControlsCooldown = 5 end)
  check(staleOk, 'writing through an invalidated handle must not raise: ' .. tostring(staleError))
  PHASE2_OK = 1
end

-- 批次 071：`Entity:TakeDamage` 的**参数个数**判据（真机事故的回归守卫）。
--
-- 真机形态：GoodTrip `trip.lua:70` 写 `player:TakeDamage(n, flags, EntityRef(player), 0)`
-- —— **冒号调用会把 `self` 压进栈**，所以栈上是 5 个值。批次 065 的判据写成"栈深度必须是 4"，
-- 于是真机上**每一次调用都报错**（错误会把整条 MC_POST_RENDER 回调摘掉），
-- 而当时没有任何用例调用过这条 API，所以一路带到了卡上。
-- 这里把三种形态都钉住：PC 的 4 实参、省略 countdown 的 3 实参、以及**真少参数时必须报错**
-- （否则"把判据改宽成永远通过"也会绿）。
local function verifyTakeDamageArity(player)
  local ref = EntityRef(player)
  check(ref ~= nil, 'EntityRef(player) must not be nil')
  local okFull, errFull = pcall(function()
    return player:TakeDamage(1, 3, ref, 0)
  end)
  check(okFull, 'player:TakeDamage(damage, flags, ref, countdown) must not raise: '
        .. tostring(errFull))
  local okShort, errShort = pcall(function()
    return player:TakeDamage(1, 3, ref)
  end)
  check(okShort, 'player:TakeDamage(damage, flags, ref) must not raise: ' .. tostring(errShort))
  local okBad = pcall(function()
    return player:TakeDamage(1, 3)
  end)
  check(not okBad, 'player:TakeDamage(damage, flags) must be rejected (missing the EntityRef)')
  TAKE_DAMAGE_OK = 1
end

-- 批次 141（2026-09-26）：`AddNullCostume` / `TryRemoveNullCostume` 的**参数校验**（兜底）。
--
-- 真机事故：The Specialist for Good Items 在跳舞时把 `Isaac.GetCostumeIdByPath(...)` 的结果
-- **直接**喂进来，而查不到时那个值是 `-1` ⇒ 引擎 `GetNullItem(-1)` 拿到空 ⇒
-- `AddCostume(nullptr)` 解引用空指针（`Data Abort`，崩溃地址为零）。夹具把 null 服装容器摆成
-- "两个真条目 + 一个空槽"，这一帧断言的是**消费者视角**：
--   ① 有效下标（0 / 1）⇒ 不报错，而且**照常调进引擎**（宿主跳板计数核对）；
--   ② 无效下标（空槽 2 / 越界 99 / 负数 -1）⇒ **不报错、不崩**，而且**不往引擎里调**
--      （核对"被挡下的次数"与"最后一次收到的编号"）；
--   ③ 参数**形状**的判据不许被这道校验放宽（非整数 / 缺参数仍然要报错）——
--      否则"把判据改宽成永远通过"也会绿。
local function verifyNullCostumeGuard(player)
  local okFirst, firstError = pcall(function() return player:AddNullCostume(0) end)
  check(okFirst, 'a valid null-costume slot must not raise: ' .. tostring(firstError))
  local okSecond, secondError = pcall(function() return player:AddNullCostume(1) end)
  check(okSecond, 'the second valid slot must not raise: ' .. tostring(secondError))
  for _, slot in ipairs({ 2, 99, -1 }) do
    local ok, err = pcall(function() return player:AddNullCostume(slot) end)
    check(ok, 'AddNullCostume(' .. slot .. ') must be blocked quietly, got: ' .. tostring(err))
  end
  local removeOk, removeError = pcall(function() return player:TryRemoveNullCostume(-1) end)
  check(removeOk, 'TryRemoveNullCostume(-1) must be blocked quietly, got: ' .. tostring(removeError))
  local typeOk = pcall(function() return player:AddNullCostume('x') end)
  check(not typeOk, 'a non-integer argument must still raise')
  local missingOk = pcall(function() return player:AddNullCostume() end)
  check(not missingOk, 'a missing argument must still raise')
end

local function run()
  frame = frame + 1
  if SCENARIO == 'take_damage' then
    local player = Isaac.GetPlayer(0)
    check(player ~= nil, 'the fake engine must expose one player')
    verifyTakeDamageArity(player)
    SCENARIO_OK = 1
    return
  end
  if SCENARIO == 'null_costume_guard' then
    local player = Isaac.GetPlayer(0)
    check(player ~= nil, 'the fake engine must expose one player')
    verifyNullCostumeGuard(player)
    SCENARIO_OK = 1
    return
  end
  if SCENARIO == 'valid' then
    if frame == 1 then
      verifyValid()
    elseif frame == 2 then
      verifyInvalidatedHandle()
    end
    SCENARIO_OK = 1
    return
  end
  verifyUnavailable()
  SCENARIO_OK = 1
end

mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  local ok, err = pcall(run)
  if not ok then
    SCENARIO_OK = 0
    print('ISAAC_ERROR: ' .. tostring(err))
  end
end)
'''


def host_compilers() -> tuple[str, str] | None:
    """(C 编译器, C++ 编译器)；缺任何一个就整体 skip，不伪装成通过。"""
    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None


class LuaEntityPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        cc, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-entity-player-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "entity_player_harness.cpp"
        harness.write_text(HARNESS.replace("@SCRIPT@", SCRIPT).lstrip())
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            output = temporary / f"{lua_source.stem}.o"
            build = subprocess.run(
                [cc, "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root), "-c",
                 str(lua_source), "-o", str(output)], text=True, capture_output=True,
            )
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            lua_objects.append(output)
        cls.harness = temporary / "entity_player_harness"
        build = subprocess.run(
            [cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             # ★ 批次 252 补：`null_costume_guard` 场景读的是 `ApiRowStatsSnapshot()` 里的
             # `rejectGuard`，而那个计数器被**批次 232 的探针总开关**（`EXL_DIAGNOSTIC_PROBES`）
             # 包住了（`api_call_stats.hpp` 的 `RecordEngineRowReject`）。宿主 harness 原来**没有**
             # 定义这个宏 ⇒ 计数器恒 0 ⇒ 那条断言（`rejects=4`）**必然失败**。
             # 这是 232 引入的回归（真机上读诊断包时是好的，只有宿主 harness 会踩到）。
             "-DEXL_DIAGNOSTIC_PROBES=1",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *map(str, lua_objects), "-o", str(cls.harness)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> subprocess.CompletedProcess:
        result = subprocess.run([str(self.harness), scenario], text=True, capture_output=True)
        self.assertEqual(
            result.returncode, 0,
            f"scenario {scenario} exited with {result.returncode}\n{result.stdout}{result.stderr}",
        )
        self.assertNotIn("ISAAC_ERROR", result.stdout + result.stderr)
        self.assertNotIn("ISAAC_FAIL", result.stdout + result.stderr)
        return result

    def test_player_fields_and_methods_match_the_hardware_verified_values(self):
        """真机实测值逐条核对 + `Position` 的"新对象"语义 + 方法返回值往返。

        伪造的引擎内存按真机探针 `ISAACGP1` 的读数摆好（`Type == 1`、`Variant == 0`、
        `SubType == 0`、`PlayerType == 0`、下标 0、位置 `(80, 280)`），Lua 侧逐字段断言；
        harness 另外核对注入的"引擎方法"收到的 `x0`（必须是 `Entity_Player` 地址）与 id。
        """
        result = self.run_scenario("valid")
        self.assertIn("ENTITY_PLAYER_OK scenario=valid engine_calls=5", result.stdout)

    def test_take_damage_accepts_the_pc_call_shape(self):
        """★ 批次 071：`player:TakeDamage(damage, flags, EntityRef(player), countdown)` 必须被接受。

        真机事故：批次 065 的判据写成"栈深度必须是 4"，而**冒号调用**（PC 模组一律这么写）
        栈上是 5 个值 ⇒ GoodTrip `trip.lua:70` 的诅咒房过路费**每一次调用都报错**，
        错误还把整条 `MC_POST_RENDER` 回调摘掉；当时没有任何用例调用过这条 API，
        所以缺陷一路带到了卡上（用户复测时才暴露）。

        同时钉住反方向：**真少参数时必须报错** —— 否则"把判据改宽成永远通过"也会绿。
        """
        result = self.run_scenario("take_damage")
        self.assertIn("TAKE_DAMAGE_OK", result.stdout)

    def test_a_null_costume_id_is_validated_before_the_engine_is_called(self):
        """★ 批次 141：编号无效时**不往引擎里调**（真机崩在 `AddCostume(nullptr)` 的回归守卫）。

        真机事故：The Specialist for Good Items 跳舞时把 `Isaac.GetCostumeIdByPath(...)` 的结果
        **直接**喂给 `player:AddNullCostume(id)`；查不到时那个值是 `-1` ⇒ 引擎 `GetNullItem(-1)`
        拿到空 ⇒ `AddCostume(nullptr)` 解引用空指针（`Data Abort`、崩溃地址为零）。

        夹具把 null 服装容器摆成"两个真条目 + 一个空槽"，断言的是**两半**：

        * 有效下标（0 / 1）⇒ 照常调进引擎（宿主跳板被调到 **2** 次）；
        * 无效下标（空槽 2 / 越界 99 / 负数 -1）与 `TryRemoveNullCostume(-1)` ⇒ 一次都没调进去，
          共挡下 **4** 次、最后一次收到的编号是 **-1**、且没有"判定不了而放行"（`unknown == 0`）；
        * 参数**形状**判据没被这道校验放宽（非整数 / 缺参数仍然报错 —— 由 Lua 侧断言）。

        这一行就是"这一批到底有没有生效"的硬证据：宿主上引擎不存在，Lua 侧只能断言"不报错"，
        而"有没有被挡下"只有这几格说得清（设备上读的是同一批全局量）。
        """
        result = self.run_scenario("null_costume_guard")
        self.assertIn(
            "COSTUME_GUARD rejects=4 reason=4 last=-1 unknown=0 trampoline=2", result.stdout
        )

    def test_get_player_returns_nil_when_the_player_cannot_be_validated(self):
        """四种"拿不到玩家"的形态都必须返回 nil，而且**一次引擎调用都不许发生**。

        * `empty`：玩家向量为空（`begin == end`）；
        * `zero_element`：向量里有一个空元素；
        * `bad_vptr`：元素非空但首字不是 `base + 0xA37110`；
        * `no_game`：`g_Game` 槽可读、但变量里是空指针；
        * `no_base`：引擎模块基址根本没发布（宿主/真机早期）。
        """
        for scenario in ("empty", "zero_element", "bad_vptr", "no_game", "no_base"):
            with self.subTest(scenario=scenario):
                result = self.run_scenario(scenario)
                self.assertIn(f"ENTITY_PLAYER_OK scenario={scenario} engine_calls=0", result.stdout)

    def test_invalidated_handle_degrades_without_reaching_the_engine(self):
        """vptr 校验必须发生在**每一次**访问上，尤其是引擎调用之前。

        `valid` 场景的第二帧里，伪造的 vptr 已经被改坏：字段返回 nil、`HasCollectible` 返回
        false，而 harness 记录的引擎调用次数仍然停在 2（第一帧那两次），说明
        `Entity_Player::HasCollectible` 没有被调用。
        """
        result = self.run_scenario("valid")
        self.assertIn("PHASE1_OK", result.stdout)
        self.assertIn("PHASE2_OK", result.stdout)
        # harness 的核对（调用次数、x0、id）通过才会打印这一行。
        self.assertIn("engine_calls=5", result.stdout)


if __name__ == "__main__":
    unittest.main()
