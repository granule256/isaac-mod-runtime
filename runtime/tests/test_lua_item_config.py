"""`Isaac.GetItemConfig()` 与 `ItemConfig` / `ItemConfig_Item` 只读视图的宿主行为测试。

批次 2b 的这条链路（`Manager + 0x36538` 的**内嵌** `ItemConfig` → 并列向量 → 条目 → libc++ SSO
字符串）已经由反汇编定位（偏移与指令级证据记在 `runtime_constants.hpp` 的 ItemConfig 段），
需要被证明的是**我们这一侧的指针链、边界检查、字符串形态判定与 Lua 视图**对不对。那些正好
可以完全在宿主上验证：

1. 用 `malloc`/`std::vector` 出来的块**伪造一份引擎内存**：模块块里的 `g_Manager` 槽 → 槽里是
   `g_Manager` 变量的地址 → 变量里才是 `Manager*` → `Manager + kManagerItemConfigOffset` 处是
   **内嵌**的 `ItemConfig`（加法，不是解引用）→ 六条并列向量的前四条 → 条目对象（`+0x00` 类别、
   `+0x04` id、`+0x08` 名字 `std::string`、`+0x20` 描述 `std::string`）；
2. 用真实 Lua 脚本断言字段值（`GetCollectible(1).Name == "Sad Onion"`、描述非空）、
   并列向量（`GetTrinket`/`GetCard`/`GetPillEffect` 各自的下标空间）、越界/负数/非整数/缺参数
   一律 `nil`、`HasTags` 恒假；
3. **两条字符串路径都读对**：短串（≤22 字节，data 内联在 `+0x01`）与长串（>22 字节，data 指针
   在 `+0x10`、size 在 `+0x08`）各摆一条，逐字比对；
4. 逐场景断言"读不出来就降级"：基址未发布、`g_Manager` 槽为 0、槽里是空指针、向量为空、
   字节长度不是 8 的倍数、长度超过上限、条目指针为空、字符串 size 离谱、类别与向量不符。

最后一类用"两帧"实现：第一帧拿到句柄并正常读取；harness 在派发之间把收藏品向量**重新指向
另一块数组**（等价于换局后 `ItemConfig::Init` 重排向量）；第二帧用同一个句柄访问，必须既返回
`nil`、又在同一次派发里让**新句柄**立刻读到新数据 —— 这就是"每一次访问都重新校验"的判据。
"""

import shutil
import subprocess
import tempfile
import re
import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

# 长串条目（> 22 字节 → libc++ 的堆形态）：写进伪造内存与 Lua 期望值用的是同一个字面量。
LONG_NAME = "#THE_SAD_ONION_DESCRIPTION_LONG_STUB_TAIL"


HARNESS = r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/api_call_stats.hpp"   // 批次 141：`GetCostumeIdByPath` 的常驻埋点

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
const char* kLongName = "@LONG_NAME@";
// `GfxFileName`（`ItemConfig::Item` 的 `+0x38`）夹具值：短的一条走 libc++ 的 SSO，长的一条走堆形态。
const char* kShortGfx = "gfx/items/c1.png";
const char* kLongGfx = "gfx/items/collectibles/Collectibles_LongEntry.png";

// --- 伪造的引擎内存 --------------------------------------------------------
//
// 与真机同形（`ItemConfig` 是**内嵌**对象，所以 `IC` 是"算出来的地址"：
// `IC = Manager + kManagerItemConfigOffset`，正是上一轮探针多解引用一次的那个位置）：
//
//   模块块[base + 0xAAC648] = &g_Manager 变量        （槽里是**变量地址**，不是对象）
//   g_Manager 变量          = Manager*
//   Manager + 0x36538       = ItemConfig（内嵌，加法）
//   IC + 0x00/+0x08         = std::vector<ItemConfig::Item*>（收藏品，733 项）
//   IC + 0x18/+0x20 …       = 并列向量（Trinket / Card / PillEffect …）
//   条目 + 0x00/+0x04/+0x08/+0x20/+0x38 = Type / id / 名字 / 描述 / GfxFileName（都是 std::string）
std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_ManagerBytes;
std::vector<unsigned char> g_ManagerSlotBytes;
std::vector<std::vector<unsigned char>> g_ItemBlocks;
std::vector<std::vector<unsigned char>> g_VectorBlocks;
std::vector<std::vector<char>> g_LongStrings;

std::uintptr_t g_EngineBase = 0;

// 条目块的下标（`NewItemBlock()` 的顺序即身份）。
enum ItemSlot : std::size_t {
    kSadOnion = 0,      // 收藏品 1：短串名字
    kLongCollectible,   // 收藏品 2：长串名字（>22 字节）
    kTrinketItem,       // Trinket[1]
    kCardItem,          // Card[0]
    kPillItem,          // PillEffect[1]
    kBrimstone,         // 第二帧的新收藏品 1（换局后的向量）
    // 批次 139（2026-09-26）：null 服装向量里的三条 —— `Isaac.GetCostumeIdByPath` 的夹具。
    kCostumeLong,       // 长串路径（>22 字节 ⇒ 堆形态）：the/specialist_isaac.anm2
    kCostumeShort,      // 短串路径（内联形态）：the/items/binky.anm2
    kCostumeEmpty,      // 空串路径（字节 0 ⇒ 必须被跳过）
    kItemSlotCount,
};

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

std::uintptr_t AddressOf(const std::vector<char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

// libc++ `std::string` 的两种形态都写一遍：`forceLong` 用来把"短串"强行按堆形态摆放，
// 从而证明读取走的是 **byte0 的 bit0**，而不是"串短就一定是内联"这类巧合。
void WriteLibcxxString(std::vector<unsigned char>& block, std::size_t offset,
                       const std::string& text, bool forceLong) {
    if (!forceLong && text.size() <= 22) {
        const std::uint8_t header = static_cast<std::uint8_t>(text.size() << 1);
        std::memcpy(block.data() + offset, &header, 1);
        std::memcpy(block.data() + offset + 1, text.data(), text.size());
        return;
    }
    // 长串：byte0 = 1（bit0 是 is_long）、size 在 +0x08、data 指针在 +0x10。
    std::uint8_t header = 1;
    std::memcpy(block.data() + offset, &header, 1);
    g_LongStrings.emplace_back(text.begin(), text.end());
    g_LongStrings.back().push_back('\0');
    WriteWord(block, offset + 0x08, static_cast<std::uint64_t>(text.size()));
    WriteWord(block, offset + 0x10, static_cast<std::uint64_t>(AddressOf(g_LongStrings.back())));
}

void FillItem(std::size_t slot, std::uint32_t type, std::uint32_t id, const std::string& name,
              const std::string& description, const std::string& gfxFileName, bool nameIsLong) {
    auto& block = g_ItemBlocks[slot];
    WriteAt<std::uint32_t>(block, kItemConfigItemTypeOffset, type);
    WriteAt<std::uint32_t>(block, kItemConfigItemIdOffset, id);
    WriteLibcxxString(block, kItemConfigItemNameOffset, name, nameIsLong);
    WriteLibcxxString(block, kItemConfigItemDescriptionOffset, description, false);
    WriteLibcxxString(block, kItemConfigItemGfxFileNameOffset, gfxFileName, false);
}

std::uintptr_t ItemAddress(std::size_t slot) {
    return AddressOf(g_ItemBlocks[slot]);
}

// 批次 139（2026-09-26）：null 服装条目的**路径**（`+0x88`，24 字节 libc++ 串）与 **id**（`+0x04`）。
// ★ **写死字面偏移**（0x88），并在这 24 字节字段前后各放一个单字节诱饵（0x87 / 0xA0）：
//   夹具跟着实现侧的常量走会两边一起错、断言永远绿（理由见 `SetItemQuality` 的注释）。
//   `+0x04` 用既有的 `kItemConfigItemIdOffset`（PC 的 `ItemConfig_Item.ID`，实现返回的就是它）。
void WriteCostumePath(std::size_t slot, const std::string& path) {
    auto& block = g_ItemBlocks[slot];
    WriteAt<std::uint8_t>(block, 0x87, 0xA5u);   // 诱饵：字段前一字节
    WriteLibcxxString(block, 0x88, path, false);
    WriteAt<std::uint8_t>(block, 0xA0, 0x5Au);   // 诱饵：字段后一字节
}

void SetNullCostumePath(std::size_t slot, std::uint32_t id, const std::string& path) {
    WriteCostumePath(slot, path);
    WriteAt<std::uint32_t>(g_ItemBlocks[slot], kItemConfigItemIdOffset, id);
}

void CreateBlocks() {
    // 0xD8 而不是 0x40：`GfxFileName` 在 `+0x38`（24 字节的 libc++ 串占到 `+0x4F`），
    // 2026-09-16 起的 `Quality`(`+0xC8`) / `CraftingQuality`(`+0xCC`) 两个 32 位整数要占到 `+0xCF`，
    // 后面还要留出 `+0xD0` 那个诱饵。
    g_ItemBlocks.assign(kItemSlotCount, std::vector<unsigned char>(0xD8, 0));
    g_ManagerBytes.assign(kManagerItemConfigOffset + 0xA0, 0);
    g_ManagerSlotBytes.assign(sizeof(std::uint64_t), 0);
    // 模块块只需要覆盖 `g_Manager` 的槽（`Isaac.GetItemConfig` 用不到 `g_Game`，但玩家链在同一
    // 块里，测试保留同样的口径：越界的槽读不到就是"拿不到"）。
    g_ModuleBytes.assign(kGameManagerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    // `IsAvailable` 一族的三条引擎函数入口指纹：设备上由真实代码提供，夹具里手工摆上
    // —— 于是"入口核对通过 ⇒ 真的去调那一条"这条路上宿主也能验证；反例（指纹不对就不调）
    // 见 `test_is_available_refuses_to_call_when_the_entry_word_is_wrong`。
    WriteAt<std::uint32_t>(g_ModuleBytes, kItemConfigItemIsAvailableOffset,
                           kItemConfigItemIsAvailableEntryWord);
    WriteAt<std::uint32_t>(g_ModuleBytes, kItemConfigCardIsAvailableOffset,
                           kItemConfigCardIsAvailableEntryWord);
    WriteAt<std::uint32_t>(g_ModuleBytes, kItemConfigPillEffectIsAvailableOffset,
                           kItemConfigPillEffectIsAvailableEntryWord);
}

// `Quality`(`+0xC8`) / `CraftingQuality`(`+0xCC`) 的夹具写入。
//
// ★ 这里**故意写死字面偏移**（0xC8/0xCC），不用 `kItemConfigItemQualityOffset` 常量：
//   夹具和实现共用同一个常量时，常量写错两边会一起错 ⇒ 断言永远绿（实测过：把常量改成
//   诱饵位 0xC4，夹具跟着把值写到 0xC4，测试照样通过）。夹具的职责是**钉住 ABI 本身**。
// ★ 同时在 `+0xC4` / `+0xD0` 放诱饵：读错一格就会读到诱饵，断言必然失败。
void SetItemQuality(std::size_t slot, std::uint32_t quality, std::uint32_t craftingQuality) {
    auto& block = g_ItemBlocks[slot];
    WriteAt<std::uint32_t>(block, 0xC4, 0x7F7F7F7Fu);                 // 诱饵：Quality 前一格
    WriteAt<std::uint32_t>(block, 0xC8, quality);
    WriteAt<std::uint32_t>(block, 0xCC, craftingQuality);
    WriteAt<std::uint32_t>(block, 0xD0, 0x7E7E7E7Eu);                 // 诱饵：CraftingQuality 后一格
}

// `AchievementID`(`+0x50`) / `MaxCharges`(`+0x74`) / `ChargeType`(`+0xB0`)。
// ★ 同样**写死字面偏移 + 每个字段的后一格放诱饵**（理由见 `SetItemQuality` 的注释）：
//   夹具一旦跟着实现侧的常量走，两边就会一起错，断言永远绿。
// ★ 值故意挑"能把类型定死"的：`AchievementID` 给 **-1**（PC 的"默认可解锁"取值为 -1，
//   读成无符号就永远不等于 -1）、`MaxCharges` 也给 -1（同样钉有符号）。
//
// ★★ 2026-09-29（批次 195）：**`Tags` 从这里搬走了** —— 它的真偏移是 `+0xC0`（u64，33 位），
//   而 `+0x58` 是 items.xml 的 `maxhearts=`（见下）。搬走的同时**在 `+0x58` 放一个可辨认的诱饵**：
//   实现若还在读旧偏移，读到的就是 `0x5A5A5A5A` 而不是 `Tags` ⇒ 断言必然失败（这正是"钉 ABI 本身"）。
void SetItemExtras(std::size_t slot, std::int32_t achievementId,
                   std::int32_t maxCharges, std::int32_t chargeType) {
    auto& block = g_ItemBlocks[slot];
    WriteAt<std::int32_t>(block, 0x50, achievementId);
    WriteAt<std::uint32_t>(block, 0x54, 0x7F7F7F7Fu);
    // `+0x58` = `maxhearts`（**不是** tags）：放诱饵，旧实现读这里必红。
    WriteAt<std::uint32_t>(block, 0x58, 0x5A5A5A5Au);
    WriteAt<std::uint32_t>(block, 0x5C, 0x7F7F7F7Fu);
    WriteAt<std::int32_t>(block, 0x74, maxCharges);
    WriteAt<std::uint32_t>(block, 0x78, 0x7F7F7F7Fu);
    WriteAt<std::int32_t>(block, 0xB0, chargeType);
    WriteAt<std::uint32_t>(block, 0xB4, 0x7F7F7F7Fu);
}

// `Tags`（`+0xC0`，**8 字节无符号位掩码**，有效 bit0..bit32；2026-09-29 批次 195 更正偏移）。
//
// 证据：`ItemConfig::LoadMetadata @ 0x3BA88C` 的 `str x21,[x8,#0xc0]`（写点唯一）、
// `ItemConfig::IsTaggedCollectible @ 0x3C0E58` 的 `ldr x8,[x0,#0xc0]` + `tst x8,x19`
// （三个读者同口径）、`ItemConfig::Load` 的 `str xzr,[x20,#0xc0]!`（8 字节清零）。
//
// ★ 写死字面偏移 + **8 字节整体写**：这样"按 4 字节读"会丢掉高 32 位（`TAG_NO_EDEN = 1<<32`
//   永远读不到）⇒ 用 bit32 的那条断言会把宽度钉住。
// ★ 相邻的 `+0xC8`（Quality）/ `+0xCC`（CraftingQuality）由 `SetItemQuality` 写不同的值，
//   天然充当"后一格诱饵"；`+0xBC` 放一个 4 字节诱饵当"前一格"。
void SetItemTags(std::size_t slot, std::uint64_t tags) {
    auto& block = g_ItemBlocks[slot];
    WriteAt<std::uint32_t>(block, 0xBC, 0x7D7D7D7Du);   // 诱饵：tags 前一格
    WriteAt<std::uint64_t>(block, 0xC0, tags);
}

// `Hidden`（`+0xB7`，**1 字节**；2026-09-16 第三批）。
// ★ 写死字面偏移 + 前后各放一个**单字节**诱饵（`+0xB6` / `+0xB8`）：
//   读错一格（或按 4 字节整数读）都会读到诱饵 ⇒ 断言必然失败。
// ★ **必须在 `SetItemExtras` 之后调用**：那边给 `ChargeType`(+0xB0) 放的 4 字节诱饵
//   正好覆盖 `0xB4..0xB7`，会把 `+0xB7` 顶掉（夹具里的写入顺序是有意义的）。
// 证据：`ItemConfig::Item::IsAvailable`（`0x3C101C`）第一条指令 `ldrb w8,[x0,#0xb7]`，
// 非零直接返回 false —— 所以这里也顺便证明"我们按 1 字节读"。
void SetItemHidden(std::size_t slot, bool hidden) {
    auto& block = g_ItemBlocks[slot];
    WriteAt<std::uint8_t>(block, 0xB6, 0x7Fu);   // 诱饵：前一字节
    WriteAt<std::uint8_t>(block, 0xB7, hidden ? 1u : 0u);
    WriteAt<std::uint8_t>(block, 0xB8, 0x7Eu);   // 诱饵：后一字节
}

// `MimicCharge`（卡牌 `+0x64` / 胶囊 `+0x48`，2026-09-16）。**写死字面偏移 + 前后各一个 4 字节诱饵**：
// 读错一格就会读到诱饵。收藏品那条向量上没有这个字段（分别在 +0x64/+0x48 写值，收藏品的对应位置由
// 诱饵占住 ⇒ 万一实现对收藏品也返回了值，断言会失败）。
void SetMimicCharge(std::size_t cardSlot, std::int32_t cardValue, std::size_t pillSlot,
                    std::int32_t pillValue) {
    auto& card = g_ItemBlocks[cardSlot];
    WriteAt<std::uint32_t>(card, 0x60, 0x7F7F7F7Fu);   // 诱饵：前一格
    WriteAt<std::int32_t>(card, 0x64, cardValue);
    WriteAt<std::uint32_t>(card, 0x68, 0x7E7E7E7Eu);   // 诱饵：后一格
    auto& pill = g_ItemBlocks[pillSlot];
    WriteAt<std::uint32_t>(pill, 0x44, 0x7F7F7F7Fu);
    WriteAt<std::int32_t>(pill, 0x48, pillValue);
    WriteAt<std::uint32_t>(pill, 0x4C, 0x7E7E7E7Eu);
}

// 建一条 `std::vector<ItemConfig::Item*>` 并把 begin/end 写进 `IC` 的对应偏移。
void PublishVector(std::size_t beginOffset, const std::vector<std::uint64_t>& elements) {
    g_VectorBlocks.emplace_back(elements.size() * sizeof(std::uint64_t) + sizeof(std::uint64_t), 0);
    auto& block = g_VectorBlocks.back();
    for (std::size_t index = 0; index < elements.size(); ++index) {
        WriteWord(block, index * sizeof(std::uint64_t), elements[index]);
    }
    WriteWord(g_ManagerBytes, kManagerItemConfigOffset + beginOffset, AddressOf(block));
    WriteWord(g_ManagerBytes, kManagerItemConfigOffset + beginOffset + sizeof(std::uint64_t),
              AddressOf(block) + elements.size() * sizeof(std::uint64_t));
}

// 批次 148（2026-09-26）：曲目表 —— `Isaac.GetMusicIdByName` 的夹具。
//
// 形状与真机同源：曲目表是 `Manager + kManagerMusicOffset` 派生出的 Music 对象里那张
// `vector<Music::Entry>`（`+0x3D8/+0x3E0`，步长 `0x70`）；每条的**名字**是起点那 24 字节的
// libc++ 串（证据见 `runtime_constants.hpp` 的 `kMusicEntryNameStringOffset`）。
//
// ★ 每条的 `+0x20`（真机上那一格是 **path**）**故意摆一条不同的串当诱饵**：实现若读错字段，
//   拿到的就是 `decoy_*` 而不是曲目名 ⇒ 断言必然失败。`+0x38` 再摆一条，覆盖面一样。
std::vector<unsigned char> g_MusicTable;

void PublishMusicEntries(const std::vector<std::string>& names) {
    const std::size_t stride = kMusicEntrySize;
    // ★★ 是**连续**的元素数组（`vector<Music::Entry>`），**不是指针数组**：真机实测
    //    `end - begin = 13328`、`13328 / 119 = 112 = 0x70`，而 `Music::Play` 取条目是
    //    `begin + id * 0x70`（`umaddl x21, w19, w10(0x70), x8`）—— 两处都指着"连续、步长 0x70"。
    //    夹具若摆成指针数组（步长 8），实现那条 `(end - begin) % 0x70 == 0` 的形状判据会直接否掉
    //    ⇒ 这一次就是这么红的（第一版夹具写错了，实现是对的）。
    g_MusicTable.assign(names.size() * stride, 0);
    for (std::size_t index = 0; index < names.size(); ++index) {
        const std::size_t entry = index * stride;
        // ★ 2026-09-27（批次 149c）：条目布局**按真机更正过** —— `+0x00` 是这条自己的
        //   **编号**（`int32`，真机读数 `g_ModEngineMusicLastEntryId` = 120 = 最后一条的下标），
        //   名字串在 `+0x08`（`kMusicEntryNameStringOffset`）。第一版夹具把名字摆在 `+0x00`
        //   （那是 148 的排除法推断），真机否掉了它：`Music::LoadConfig` 的属性分派里
        //   `strcmp(属性名, "id")` → `str w0,[模板+0x00]`、`strcmp("name")` → `string::assign`
        //   到 `模板+0x08`（证据见 `tools/layout_tables/music_entry.json` 与
        //   `runtime_constants.hpp` 的两条常量注释）。
        WriteAt<std::int32_t>(g_MusicTable, entry + kMusicEntryIdOffset,
                              static_cast<std::int32_t>(index));
        WriteLibcxxString(g_MusicTable, entry + kMusicEntryNameStringOffset, names[index], false);
        // 诱饵：`+0x20`（真机上那一格是 **path**）与 `+0x38` 各摆一条**不同**的串 ——
        // 实现若读错字段，拿到的就是 `decoy_*`，断言必然失败。
        WriteLibcxxString(g_MusicTable, entry + 0x20,
                          "decoy_path_" + std::to_string(index) + ".ogg", false);
        WriteLibcxxString(g_MusicTable, entry + 0x38, "decoy_layer_" + std::to_string(index), false);
    }
    WriteWord(g_ManagerBytes, kManagerMusicOffset + kMusicEntryVectorBeginOffset,
              AddressOf(g_MusicTable));
    WriteWord(g_ManagerBytes, kManagerMusicOffset + kMusicEntryVectorEndOffset,
              AddressOf(g_MusicTable) + names.size() * stride);
}

std::vector<std::uint64_t> CollectibleElements() {
    // 733 项（真机硬判据 `E - B == 0x16E8`）：0 号是真机上的空槽（指针为 0）。
    std::vector<std::uint64_t> elements(kItemConfigCollectibleCount, 0);
    elements[1] = ItemAddress(kSadOnion);
    elements[2] = ItemAddress(kLongCollectible);
    return elements;
}

// `ItemConfig_Item:IsAvailable()` 的宿主接法：那一条 `bl` 在宿主上由测试注入的实现顶替。
// 它**记录分派结果**（`kind`：0 = `Item`（带 flags）/ 1 = `Card` / 2 = `PillEffect`）与 flags，
// 返回值刻意编码分派结果（只有"走 Item 分支且 flags 正确"才为 true）—— 这样 Lua 侧的断言
// 一次钉住两件事，而打印出来的 `ISAVAIL_CALLS` 由 Python 侧逐项核对顺序与取值。
struct IsAvailableCall {
    int kind = -1;
    std::int64_t flags = -1;
};
IsAvailableCall g_IsAvailableCalls[8];
int g_IsAvailableCallCount = 0;

bool HarnessIsAvailable(int kind, void* /*entry*/, std::int64_t flags) {
    if (g_IsAvailableCallCount < 8) {
        g_IsAvailableCalls[g_IsAvailableCallCount].kind = kind;
        g_IsAvailableCalls[g_IsAvailableCallCount].flags = flags;
    }
    ++g_IsAvailableCallCount;
    return kind == 0 && flags == kItemIsAvailableFlags;
}

// 批次 241：`ItemConfig_Item:IsRune()`（PC 类名 `ItemConfig_Card`）的宿主接法。
// 真机上它直读 `Card+0x58`（== 2 ⇒ 符文），宿主没有引擎映像 ⇒ 这里按**条目地址**回答：
// 只对夹具里那张卡条目为 true，别的（药丸/收藏品）为 false —— 这一条把"哪些句柄算符文"钉住。
int g_IsRuneCallCount = 0;

bool HarnessIsRune(void* card) {
    ++g_IsRuneCallCount;
    return reinterpret_cast<std::uintptr_t>(card) == ItemAddress(kCardItem);
}

// 条目数据。`+0x00` 是 PC 的 `ItemType`（批次 3 定案：`items.xml` 的 `type` 属性被解析器原样
// 写进这个字段，见 `runtime_constants.hpp` 的 `kItemConfigItemTypeOffset`）：1=PASSIVE、
// 2=TRINKET、3=ACTIVE、4=FAMILIAR。卡牌/药丸条目沿用 3/4 只是为了证明"`Type` 原样返回
// `+0x00` 的读数"，不声称卡牌/药丸在引擎里就是这两个类型。
void FillItems() {
    FillItem(kSadOnion, kItemTypePassive, 1, "Sad Onion", "Tears up + damage up", kShortGfx,
             false);
    FillItem(kLongCollectible, kItemTypePassive, 2, kLongName, "long name entry", kLongGfx, true);
    FillItem(kTrinketItem, kItemTypeTrinket, 1, "Swallowed Penny", "trinket stub",
             "gfx/items/t1.png", false);
    FillItem(kCardItem, 3, 0, "Card stub", "card stub", "gfx/items/card.png", false);
    FillItem(kPillItem, 4, 1, "Pill stub", "pill stub", "gfx/items/pill.png", false);
    FillItem(kBrimstone, kItemTypePassive, 1, "Brimstone", "blood laser barrage",
             "gfx/items/c118.png", false);
    // `Quality` / `CraftingQuality`（2026-09-16）：只给测试会断言的两条非零值，
    // 其余条目保持 0（字段在、值为 0 —— 与 PC 上"这段内存是整数"同形）。
    SetItemQuality(kSadOnion, /*quality=*/1, /*craftingQuality=*/3);
    SetItemQuality(kLongCollectible, /*quality=*/4, /*craftingQuality=*/4);
    // `items.xml` 属性分派表上的另外三个字段（2026-09-16 第二批；`Tags` 已在批次 195 搬走）。
    SetItemExtras(kSadOnion, /*achievementId=*/ -1, /*maxCharges=*/ 0,
                  /*chargeType=*/ 0);
    SetItemExtras(kLongCollectible, /*achievementId=*/ 5, /*maxCharges=*/ -1,
                  /*chargeType=*/ 2);
    // `Tags`（`+0xC0`，u64；2026-09-29 批次 195 更正偏移与宽度）。
    // ★ **必须在 `SetItemQuality` 之后**：那边给 `+0xC4` 放的 4 字节诱饵正好落在 tags 的高半部。
    // 值挑的是"能把两件事定死"的：
    //   * `kSadOnion` = `TAG_MUSHROOM(0x100) | TAG_OFFENSIVE(0x100000) | TAG_SUMMONABLE(0x1000000)`
    //     —— 就是 items_metadata.xml 给 1 号道具列的那三个标签；
    //   * `kLongCollectible` 带上 **bit32**（`TAG_NO_EDEN = 1<<32`）⇒ 按 4 字节读会丢掉它，
    //     断言必然失败（宽度被钉住）。
    SetItemTags(kSadOnion, 0x1100100ULL);
    SetItemTags(kLongCollectible, 0x100000108ULL);
    // `Hidden`（第三批）：一条假、一条真 ⇒ "读得到 + 读得对"两个方向都钉住。
    // 第二条同时覆盖"非 0 就是真"的口径（引擎里就是 `!= 0`）。
    SetItemHidden(kSadOnion, /*hidden=*/ false);
    SetItemHidden(kLongCollectible, /*hidden=*/ true);
    // `MimicCharge`（第三批）：卡与胶囊各给一个可辨认的值（卡 2、胶囊 3）。
    SetMimicCharge(kCardItem, 2, kPillItem, 3);
    // 批次 139：null 服装向量（`costumes2.xml` 里 `type=none` 的那些条目）。
    //   ① 长串路径（24 字节 ⇒ 堆形态）id 5；② 短串路径（19 字节 ⇒ 内联形态）id 7；
    //   ③ 空串（字节 0 ⇒ 必须被跳过）id 9。
    SetNullCostumePath(kCostumeLong, 5, "the/specialist_isaac.anm2");
    SetNullCostumePath(kCostumeShort, 7, "the/items/binky.anm2");
    SetNullCostumePath(kCostumeEmpty, 9, "");
    // ★ 反向判据的诱饵：**收藏品**条目上也挂一条同族的路径 ⇒ `GetCostumeIdByPath` 只允许搜 null 向量
    //   （那是已登记的偏离，见 `api_deviation.cpp` 的 0x0E01005D）。★ 只写路径、**不写 id**：
    //   收藏品条目的 `+0x04` 是它自己的 id（`valid` 场景要断言 `item.ID == 1`），不能被这条诱饵动过。
    WriteCostumePath(kSadOnion, "the/specialist_decoy.anm2");
}

// 换局：`ItemConfig::Init` 重排向量 —— 收藏品向量指到另一块数组、1 号条目换了一个对象。
// 旧的句柄缓存的是旧 begin，所以必须自证过期（而不是"地址还读得到就继续用"）。
void RepointCollectibleVector() {
    std::vector<std::uint64_t> elements(kItemConfigCollectibleCount, 0);
    elements[1] = ItemAddress(kBrimstone);
    elements[2] = ItemAddress(kLongCollectible);
    PublishVector(kItemConfigCollectibleBeginOffset, elements);
}

void PublishVectors() {
    PublishVector(kItemConfigCollectibleBeginOffset, CollectibleElements());
    // Trinket：{ 空槽, 条目, 空槽 } —— 下标空间与收藏品不同，越界判据必须按各自的向量算。
    PublishVector(kItemConfigTrinketBeginOffset,
                  {0, ItemAddress(kTrinketItem), 0});
    // Card：{ 条目, 空槽 }
    PublishVector(kItemConfigCardBeginOffset, {ItemAddress(kCardItem), 0});
    // PillEffect：{ 空槽, 条目 }
    PublishVector(kItemConfigPillEffectBeginOffset, {0, ItemAddress(kPillItem)});
    // 批次 139：null 服装向量 —— `Isaac.GetCostumeIdByPath` 搜的就是这一条（`IC+0x30/+0x38`）。
    PublishVector(kItemConfigNullItemBeginOffset,
                  {ItemAddress(kCostumeLong), ItemAddress(kCostumeShort),
                   ItemAddress(kCostumeEmpty)});
    // 批次 148：曲目表 —— `Isaac.GetMusicIdByName` 搜的就是这一条。
    // 下标 1 用**长串**（>22 字节 ⇒ 堆形态），把 libc++ 的两种串形态都走到（与服装那条同一口径）；
    // 下标 2 就是模组 `content/music.xml` 追加的那两条的等价物（真机上它们是 119/120）。
    PublishMusicEntries({"Title Screen", "Burning Basement (long-form track name)", "specialist"});
}

void PublishManager() {
    WriteWord(g_ModuleBytes, kGameManagerGlobalSlotOffset, AddressOf(g_ManagerSlotBytes));
    WriteWord(g_ManagerSlotBytes, 0, AddressOf(g_ManagerBytes));
    // `Manager + kManagerItemConfigOffset` 就是 `ItemConfig`；向量已经写在这块里了。
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
    const char* kScenarios[] = {"valid", "no_base", "slot_zero", "no_manager", "empty_vector",
                                "bad_length", "huge_length", "null_entry", "bad_string",
                                "wrong_kind", "bad_isavailable_entry", "costume_id_by_path",
                                "music_id_by_name"};
    bool known = false;
    for (const char* candidate : kScenarios) {
        if (scenario == candidate) known = true;
    }
    if (!known) return 91;

    CreateBlocks();
    FillItems();

    if (scenario != "no_base") {
        PublishVectors();
        PublishManager();
        if (scenario == "slot_zero") {
            // `g_Manager` 的**槽**本身是 0：第二级解引用必须变成"拿不到"，而不是读地址 0。
            WriteWord(g_ModuleBytes, kGameManagerGlobalSlotOffset, 0);
        } else if (scenario == "no_manager") {
            // 槽可读、变量里是空指针。
            WriteWord(g_ManagerSlotBytes, 0, 0);
        } else if (scenario == "empty_vector") {
            // begin == end：长度为 0。
            const std::uintptr_t begin = AddressOf(g_VectorBlocks.front());
            WriteWord(g_ManagerBytes, kManagerItemConfigOffset + kItemConfigCollectibleEndOffset,
                      begin);
        } else if (scenario == "bad_length") {
            // `E - B` 不是 8 的倍数（0x16E8 + 4）。
            const std::uintptr_t begin = AddressOf(g_VectorBlocks.front());
            WriteWord(g_ManagerBytes, kManagerItemConfigOffset + kItemConfigCollectibleEndOffset,
                      begin + kItemConfigCollectibleVectorBytes + 4);
        } else if (scenario == "huge_length") {
            // 长度超过合理上限（4097 项）：偏移猜错时"读到一段垃圾"必须变成"读不到"。
            const std::uintptr_t begin = AddressOf(g_VectorBlocks.front());
            WriteWord(g_ManagerBytes, kManagerItemConfigOffset + kItemConfigCollectibleEndOffset,
                      begin + 4097 * sizeof(std::uint64_t));
        } else if (scenario == "null_entry") {
            WriteWord(g_VectorBlocks.front(), 1 * sizeof(std::uint64_t), 0);
        } else if (scenario == "bad_string") {
            // `is_long` 置位（byte0 的 bit0）但 size 离谱（0x100000）：名字必须读成 nil，
            // 而不是拿这个长度去越界读。
            WriteAt<std::uint8_t>(g_ItemBlocks[kSadOnion], kItemConfigItemNameOffset, 1);
            WriteWord(g_ItemBlocks[kSadOnion], kItemConfigItemNameOffset + 0x08, 0x100000);
        } else if (scenario == "bad_isavailable_entry") {
            // `IsAvailable` 那条引擎函数的入口指纹对不上（偏移写错时的真实形态）：
            // **必须拒绝调用**（宁可返回 false，也不能去调另一个函数）。
            WriteAt<std::uint32_t>(g_ModuleBytes, kItemConfigItemIsAvailableOffset, 0);
        } else if (scenario == "wrong_kind") {
            // 收藏品向量里的条目却带着 TRINKET 的类别：`IsCollectible` 必须说 false。
            WriteAt<std::uint32_t>(g_ItemBlocks[kSadOnion], kItemConfigItemTypeOffset,
                                   kItemTypeTrinket);
        }
        LuaRuntime::SetEngineModuleBase(g_EngineBase);
    }

    // 只在 `valid` 场景装 `IsAvailable` 的宿主实现（其余场景跑同一份模板，但相关断言按 SCENARIO
    // 分支；不装那条通路就没人接 —— 与其它引擎方法的宿主接法同口径）。
    if (scenario == "valid" || scenario == "bad_isavailable_entry") {
        isaac::runtime::SetItemConfigIsAvailableHostImplementation(&HarnessIsAvailable);
    }
    // 批次 241：`IsRune` 的宿主实现（只在 valid 场景装）。
    if (scenario == "valid") {
        isaac::runtime::SetItemConfigCardIsRuneHostImplementation(&HarnessIsRune);
    }

    const std::string script = "SCENARIO = '" + scenario + "'\n" + kScriptTemplate;
    const auto result =
        LuaRuntime::InitializeFromBuffer(script.c_str(), script.size(), "@item_config.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("ISAAC_FAIL: the Lua state did not initialize\n");
        return 2;
    }

    const bool hasSecondFrame = scenario == "valid";
    LuaRuntime::DispatchPostUpdate();
    if (LuaRuntime::TakeCallbackError()) {
        std::printf("ISAAC_FAIL: the Lua callback raised an error\n");
        return 1;
    }
    if (hasSecondFrame) {
        // 第二帧之前把向量重新指向另一块数组：旧句柄必须自证过期。
        RepointCollectibleVector();
        LuaRuntime::DispatchPostUpdate();
        if (LuaRuntime::TakeCallbackError()) {
            std::printf("ISAAC_FAIL: the second frame raised a Lua error\n");
            return 1;
        }
    }

    if (!ExpectNumber("SCENARIO_OK", 1.0)) return 1;
    if (hasSecondFrame) {
        if (!ExpectNumber("PHASE1_OK", 1.0)) return 1;
        if (!ExpectNumber("PHASE2_OK", 1.0)) return 1;
    }
    std::printf("ITEM_CONFIG_OK scenario=%s\n", scenario.c_str());
    // 批次 141（2026-09-26）：把 `GetCostumeIdByPath` 的**常驻埋点**打出来给 Python 侧核对。
    // 这几格正是真机上"跳舞模组那 23 条到底查到了没有"的唯一直接证据（读数工具按符号直读同一批
    // 全局量）⇒ 门禁在这里钉住"查了几次 / 中几次 / 最后一次中的是几 / 容器里有几条"的语义，
    // 免得哪天埋点被挪了位置，或计数只加在"命中"那条返回路径上。
    if (scenario == "costume_id_by_path") {
        const isaac::runtime::ApiRowStats stats = isaac::runtime::ApiRowStatsSnapshot();
        std::printf("COSTUME_STATS calls=%u hits=%u misses=%u last=%u null=%u\n",
                    stats.costumePathCalls, stats.costumePathHits, stats.costumePathMisses,
                    stats.costumePathLastId, stats.costumePathNullCount);
    }
    // 批次 148（2026-09-26）：曲目名反查的常驻埋点（真机读数工具按同一批裸名直读）。
    // ★ `table` 那一格正是"模组的 `content/music.xml` 进引擎了没有"的直接读数 ——
    //   夹具里是 3 条，真机上基线 119、模组进去之后 121。
    if (scenario == "music_id_by_name") {
        const isaac::runtime::ApiRowStats stats = isaac::runtime::ApiRowStatsSnapshot();
        std::printf("MUSIC_STATS calls=%u hits=%u last=%d table=%u name=%s\n",
                    stats.musicIdCalls, stats.musicIdHits,
                    static_cast<int>(stats.musicIdLastResult), stats.musicIdTableCount,
                    g_IsaacMusicIdLastName);
    }
    if (hasSecondFrame) {
        // 两帧的 Lua 侧结论都已经由 `ExpectNumber` 核对过，这里只是把标记打出来给 Python 侧看。
        std::printf("PHASE1_OK PHASE2_OK\n");
    }
    // `IsAvailable` 的分派记录（顺序 = Lua 侧的调用顺序；Python 侧逐项核对）
    std::printf("ISAVAIL_CALLS %d", g_IsAvailableCallCount);
    for (int i = 0; i < g_IsAvailableCallCount && i < 8; ++i) {
        std::printf(" %d:%lld", g_IsAvailableCalls[i].kind,
                    static_cast<long long>(g_IsAvailableCalls[i].flags));
    }
    std::printf("\n");
    return 0;
}
'''


SCRIPT = r'''
local mod = RegisterMod('ItemConfig view', 1)

local function check(condition, message)
  if not condition then error(message, 2) end
end

local function describe(value)
  if value == nil then return 'nil' end
  return type(value) .. ':' .. tostring(value)
end

local LONG_NAME = '@LONG_NAME@'
local savedConfig = nil
local savedItem = nil
local frame = 0

-- 链路拿不到（基址未发布 / 槽为 0 / Manager 为空 / 向量非法 / 长度为 0）：只能是 nil，不报错。
local function verifyUnavailable()
  local ok, value = pcall(function() return Isaac.GetItemConfig() end)
  check(ok, 'Isaac.GetItemConfig must not raise a Lua error: ' .. tostring(value))
  check(value == nil, 'Isaac.GetItemConfig must be nil, got ' .. describe(value))
end

local function verifyValid()
  local config = Isaac.GetItemConfig()
  check(config ~= nil, 'Isaac.GetItemConfig() must return an ItemConfig')
  check(type(config) == 'userdata', 'GetItemConfig must return a userdata, got '
        .. describe(config))
  check(config.NotAThing == nil, 'an unknown ItemConfig field must be nil')
  check(type(config.GetCollectible) == 'function', 'GetCollectible must exist')

  local item = config:GetCollectible(1)
  check(type(item) == 'userdata', 'GetCollectible must return an ItemConfig_Item, got '
        .. describe(item))
  check(item.ID == 1, 'ID must be the item id (1), got ' .. describe(item.ID))
  -- `+0x00` 是 PC 的 `ItemType`（1 = ITEM_PASSIVE）：Sad Onion 是被动道具，所以读数是 1。
  check(item.Type == 1, 'Type must be the raw ItemType field (1 = ITEM_PASSIVE), got '
        .. describe(item.Type))
  check(item.Name == 'Sad Onion', 'Name must be "Sad Onion", got ' .. describe(item.Name))
  check(type(item.Description) == 'string' and #item.Description > 0,
        'Description must be a non-empty string, got ' .. describe(item.Description))
  -- `GfxFileName`（`ItemConfig::Item` 的 `+0x38`）：EID 在 `features/eid_api.lua:1278` 直接把它交给
  -- `Sprite:ReplaceSpritesheet`。缺这个字段正是真机上"一进道具范围就报错、描述全不显示"的根因
  -- （报告 `01789228056` 那条 126 字节的 Lua 错误唯一能落在 `eid_api.lua:1278`）。
  check(item.GfxFileName == 'gfx/items/c1.png',
        'GfxFileName must be the raw items.xml gfx path, got ' .. describe(item.GfxFileName))
  -- `Quality`(`+0xC8`) / `CraftingQuality`(`+0xCC`)，2026-09-16：EID 用前者显示品质
  -- （`features/eid_api.lua:2702` → `main.lua:663` 的 `{{QualityN}}`）、用两者做背包合成排序
  -- （`eid_bagofcrafting.lua:393/407` 的 `item.CraftingQuality or item.Quality`）。
  -- 缺这两个字段的症状是**静默的**（`and desc.Quality` 短路 ⇒ 品质不显示、不报错、无日志），
  -- 夹具在 `+0xC4`/`+0xD0` 放了诱饵 ⇒ 读错一格就会读到诱饵，断言必然失败。
  check(item.Quality == 1,
        'Quality must come from +0xC8 (fixture 1), got ' .. describe(item.Quality))
  check(item.CraftingQuality == 3,
        'CraftingQuality must come from +0xCC (fixture 3, not the Quality value), got '
        .. describe(item.CraftingQuality))
  -- `items.xml` 属性分派表上的另外三个字段（2026-09-16 第二批）：
  -- `AchievementID`(`+0x50`) / `MaxCharges`(`+0x74`) / `ChargeType`(`+0xB0`)。
  -- `Tags` 的偏移在批次 195 更正为 `+0xC0`（见下面那几条断言），不在这一组里。
  -- EID 的用法：`eid_api.lua:2003` 用 `item.AchievementID == -1` 与 `item.Tags & TAG_QUEST`
  -- 判断"是不是任务道具"，`eid_api.lua:785/786` 把 `ChargeType`/`MaxCharges` 填进描述对象。
  -- **-1 这条同时钉住"有符号读"**：无符号读会给出 4294967295，断言必然失败。
  check(item.AchievementID == -1,
        'AchievementID must be read **signed** (fixture -1), got ' .. describe(item.AchievementID))
  -- ★★ 2026-09-29（批次 195）：`Tags` 的真偏移是 **`+0xC0`（u64）**，`+0x58` 是 `maxhearts=`。
  -- 夹具在 `+0x58` 放了 `0x5A5A5A5A` 当诱饵、在 `+0xC0` 写 8 字节 ⇒ 这两条断言同时钉住
  -- "偏移对"与"宽度是 8 字节"（值 `0x1100100` 就是 items_metadata.xml 给 1 号道具的三个标签）。
  check(item.Tags == 0x1100100,
        'Tags must come from +0xC0 (fixture 0x1100100), got ' .. describe(item.Tags))
  check(item.Tags & 0x100 == 0x100,
        'Tags must work as a bitmask the way EID uses it, got ' .. describe(item.Tags))
  local longTagsItem = config:GetCollectible(2)
  check(longTagsItem.Tags == 0x100000108,
        'Tags must be read as a **u64**: bit32 (TAG_NO_EDEN = 1<<32) must survive, got '
        .. describe(longTagsItem.Tags))
  check(item.MaxCharges == 0,
        'MaxCharges must come from +0x74 (fixture 0), got ' .. describe(item.MaxCharges))
  check(item.ChargeType == 0,
        'ChargeType must come from +0xB0 (fixture 0 = CHARGE_NORMAL), got '
        .. describe(item.ChargeType))
  -- `Hidden`(`+0xB7`，**1 字节**；2026-09-16 第三批）：EID 用它做两件事 ——
  -- `eid_api.lua:2008` 的 `if item.Hidden then`（隐藏道具不出描述）与 `eid_api.lua:1927`
  -- Spindown Dice 预测里的 `not item.Hidden`（缺这个字段时那一半恒真）。
  -- 夹具在 `+0xB6`/`+0xB8` 放了单字节诱饵 ⇒ 读错一格或按 4 字节读都会读到诱饵。
  check(item.Hidden == false,
        'Hidden must be the byte at +0xB7 (fixture 0 = false), got ' .. describe(item.Hidden))
  local longItem = config:GetCollectible(2)
  check(type(longItem) == 'userdata', 'GetCollectible(2) must return an ItemConfig_Item')
  check(longItem.Hidden == true,
        'Hidden must be true when the byte is non-zero (fixture 1), got '
        .. describe(longItem.Hidden))
  -- `Hidden` 是布尔，不是数字：PC 文档写 `boolean`。
  check(type(longItem.Hidden) == 'boolean',
        'Hidden must be a boolean, got ' .. describe(longItem.Hidden))
  check(item.NotAThing == nil, 'an unknown item field must be nil')
  -- `ItemConfig_Item:IsAvailable()`（2026-09-16，"IsAvailable 一族"）：EID 在
  -- `eid_api.lua:1988`/`:2013`、`eid_bagofcrafting.lua:826` 上用它判断"这件道具解锁了没有"。
  -- 两件事一起钉住：
  --   ① EID 先做**字段式**探测（`if item.IsAvailable then ...`）⇒ `item.IsAvailable` 不能是 nil；
  --   ② 收藏品条目必须走 `Item::IsAvailable`，且 flags 是兼容层定义的 0xE
  --      （宿主 harness 只在"kind == 0 且 flags == 0xE"时返回 true）⇒ 拿到 true 就同时证明了这两点。
  check(item.IsAvailable ~= nil,
        'EID probes `item.IsAvailable` as a field first — it must not be nil')
  check(item:IsAvailable() == true,
        'the collectible entry must be routed to Item::IsAvailable with flags 0xE')
  -- `ItemConfig_Item:HasTags(tags)`（2026-09-29 批次 195：**从恒 false 改成真实现**）。
  -- PC 契约 `tools/pc_contract_docs/ItemConfig_Item.md:23`；口径 = 引擎自己三处同形的
  -- **任一命中**：`(Tags & mask) != 0`（`IsTaggedCollectible` / `IsTaggedTrinket` / `GetTaggedItems`）。
  -- 夹具给 1 号道具写的是 `0x1100100`（mushroom|offensive|summonable）⇒ 这两条同时钉住
  -- "参数真的被读了"与"任一命中"（老实现连参数都没读、恒 false）。
  check(item:HasTags(0x100) == true,
        'ItemConfig_Item:HasTags must read the mask argument (TAG_MUSHROOM) and answer true')
  check(item:HasTags(0x8000) == false,
        'ItemConfig_Item:HasTags must answer false when no bit matches (TAG_QUEST)')
  -- 批次 3：`ItemConfig_Item:IsCollectible()`（**无参**）是 EID 在描述构建里直接调用的成员
  -- （`main.lua:669`/`738`/`757`），判据是"句柄仍有效且 `Type != ITEM_NULL`"。
  check(item:IsCollectible() == true,
        'ItemConfig_Item:IsCollectible must be true for a validated collectible entry')
  -- 批次 7：`ItemConfig_Item:IsTrinket()`（同样是**数据行**实现，判据 `Type == ITEM_TRINKET`）。
  check(item:IsTrinket() == false,
        'ItemConfig_Item:IsTrinket must be false for a passive collectible')
  -- `ItemConfig:HasTags(id, tags)`（门面便捷形式，2026-09-29 批次 195：**从恒 false 改成真实现**）。
  -- id 走**收藏品向量**（与本文件里的 `IsCollectible` 同一条口径；PC 上没有这条方法 ⇒ 签名由我们定，
  -- 见 `isaac_api.cpp` 实现处的注释）。
  check(config:HasTags(1, 0x100) == true,
        'ItemConfig:HasTags(id, mask) must answer true when the bit is set')
  check(config:HasTags(1, 0x8000) == false,
        'ItemConfig:HasTags(id, mask) must answer false when no bit matches')
  check(config:HasTags(999, 0x100) == false,
        'ItemConfig:HasTags out of range must be false, not an error')

  -- 0 号是真机上的空槽（指针为 0）：必须 nil，既不是假对象也不能崩。
  check(config:GetCollectible(0) == nil, 'the null collectible slot must be nil')
  check(config:IsCollectible(1) == true, 'IsCollectible(1) must be true for Sad Onion')
  check(config:IsCollectible(0) == false, 'IsCollectible(0) must be false for the null slot')
  check(config:IsCollectible(999) == false, 'IsCollectible out of range must be false')

  -- 越界 / 负数 / 非整数 / 缺参数：一律 nil，且不抛 Lua 错误。
  for _, id in ipairs({ -1, 733, 999999 }) do
    local ok, value = pcall(function() return config:GetCollectible(id) end)
    check(ok, 'GetCollectible(' .. id .. ') must not raise: ' .. tostring(value))
    check(value == nil, 'GetCollectible(' .. id .. ') must be nil, got ' .. describe(value))
  end
  check(config:GetCollectible('nope') == nil, 'GetCollectible must be nil for a non-integer id')
  check(config:GetCollectible() == nil, 'GetCollectible must be nil without an id')
  check(config:IsCollectible('nope') == false, 'IsCollectible must be false for a non-integer id')
  -- id 的接受范围与 PC 的 `luaL_checkinteger` 一致：整值浮点收，带小数的浮点不收。
  local asFloat = config:GetCollectible(1.0)
  check(type(asFloat) == 'userdata' and asFloat.Name == 'Sad Onion',
        'an integral float id (1.0) must be accepted the way PC accepts it')
  check(config:GetCollectible(1.5) == nil, 'a fractional id must be nil')
  check(config:IsCollectible(1.0) == true, 'IsCollectible(1.0) must behave like IsCollectible(1)')

  -- 长串（> 22 字节）走 libc++ 的堆形态：必须逐字读对。
  local long = config:GetCollectible(2)
  check(long ~= nil, 'the long-name entry must exist')
  check(#LONG_NAME > 22, 'the fixture itself must be longer than the SSO buffer')
  check(long.Name == LONG_NAME,
        'a long std::string must be read from +0x10/+0x08, got ' .. describe(long.Name))
  check(long.ID == 2, 'the long-name entry must keep its own id, got ' .. describe(long.ID))
  check(type(long.Description) == 'string' and #long.Description > 0,
        'the long-name entry must still have a description')
  check(type(long.GfxFileName) == 'string' and #long.GfxFileName > 22,
        'a long gfx name must be read from the heap form, got ' .. describe(long.GfxFileName))
  check(string.sub(long.GfxFileName, 1, 4) == 'gfx/',
        'the long gfx name must be the fixture path, got ' .. describe(long.GfxFileName))
  check(long.Quality == 4, 'the long-name entry has its own Quality, got ' .. describe(long.Quality))
  check(long.CraftingQuality == 4,
        'the long-name entry has its own CraftingQuality, got ' .. describe(long.CraftingQuality))
  -- 每个条目读的是**自己那段内存**（不是共用一份夹具值），顺带把 `MaxCharges` 的有符号读也钉住。
  check(long.AchievementID == 5, 'AchievementID must be per-entry, got ' .. describe(long.AchievementID))
  -- ★ 批次 195：`Tags` 的偏移改成 `+0xC0`（u64）之后，这条"每个条目读的是自己那段内存"的断言
  -- 也要跟着换值 —— 而且它顺带把**宽度**钉住（`0x100000108` 带 bit32 = `TAG_NO_EDEN`）。
  check(long.Tags == 0x100000108, 'Tags must be per-entry, got ' .. describe(long.Tags))
  check(long.MaxCharges == -1,
        'MaxCharges must be read **signed** (fixture -1), got ' .. describe(long.MaxCharges))
  check(long.ChargeType == 2,
        'ChargeType must be per-entry (fixture 2 = CHARGE_SPECIAL), got ' .. describe(long.ChargeType))

  -- 并列向量：各自的下标空间与条目内容。
  local trinket = config:GetTrinket(1)
  check(trinket ~= nil, 'GetTrinket(1) must exist')
  check(trinket.Name == 'Swallowed Penny',
        'GetTrinket(1).Name must come from the trinket vector, got ' .. describe(trinket.Name))
  check(trinket.Type == 2, 'a trinket entry must report kind 2, got ' .. describe(trinket.Type))
  check(trinket:IsTrinket() == true, 'a kind-2 entry must answer IsTrinket true')
  check(trinket.ID == 1, 'the trinket id must come from its own entry')
  -- 非收藏品条目的这段内存是 0 ⇒ 必须读到**数字 0**（字段存在、值为 0），而不是 nil。
  -- EID 的 `item.CraftingQuality or item.Quality` 只在 nil 时才回退，读错成 nil 会改变行为。
  check(trinket.Quality == 0,
        'a non-collectible entry must still answer a numeric Quality (0), got '
        .. describe(trinket.Quality))
  check(config:GetTrinket(0) == nil, 'the null trinket slot must be nil')
  check(config:GetTrinket(2) == nil, 'the trinket vector has 3 slots: index 2 is the null slot')
  check(config:GetTrinket(3) == nil, 'GetTrinket(3) must be nil (out of range)')
  check(config:GetTrinket(733) == nil, 'the trinket vector is not the collectible vector')

  local card = config:GetCard(0)
  check(card ~= nil, 'GetCard(0) must exist')
  check(card.Name == 'Card stub', 'GetCard(0).Name must come from the card vector, got '
        .. describe(card.Name))
  check(card.Type == 3, 'Type must be the raw kind field of the card entry')
  check(config:GetCard(1) == nil, 'the card vector has 2 slots: index 1 is the null slot')
  check(config:GetCard(2) == nil, 'GetCard(2) must be nil (out of range)')

  -- `MimicCharge`（2026-09-16）：**卡牌与胶囊各有一个**（`+0x64` / `+0x48`），收藏品没有。
  -- EID 用它给"模仿胶囊/卡牌"补说明（`features/eid_modifiers.lua:731`）。
  check(card.MimicCharge == 2,
        'Card.MimicCharge must come from +0x64 (fixture 2), got ' .. describe(card.MimicCharge))
  check(trinket.MimicCharge == nil,
        'a trinket must not expose MimicCharge, got ' .. describe(trinket.MimicCharge))
  local pill = config:GetPillEffect(1)
  check(pill ~= nil, 'GetPillEffect(1) must exist')
  check(pill.MimicCharge == 3,
        'PillEffect.MimicCharge must come from +0x48 (fixture 3), got ' .. describe(pill.MimicCharge))
  check(pill.Name == 'Pill stub', 'GetPillEffect(1).Name must come from the pill vector, got '
        .. describe(pill.Name))
  check(config:GetPillEffect(0) == nil, 'the null pill slot must be nil')
  check(config:GetPillEffect(2) == nil, 'GetPillEffect(2) must be nil (out of range)')

  -- 卡牌/药丸条目走的是**另外两个引擎函数**（宿主 harness 对 kind != 0 一律返回 false）
  -- ⇒ 拿到 false 说明"没有误走 Item 那条"。具体分派（1 = Card、2 = PillEffect）由 C++ 侧
  -- 打印的 `ISAVAIL_CALLS` 在 Python 侧逐项核对 —— 布尔返回值区分不了 1 与 2，所以不能只看 Lua。
  check(card:IsAvailable() == false, 'a card entry must not be routed to Item::IsAvailable')
  check(pill:IsAvailable() == false, 'a pill entry must not be routed to Item::IsAvailable')

  -- 批次 241：`IsRune()`（PC 类名 `ItemConfig_Card`）。宿主实现按条目地址回答：
  -- 只有卡条目为 true；药丸/收藏品这些**没有"符文"概念**的向量一律 false（且不抛错）。
  check(card:IsRune() == true, 'IsRune must be true for the card entry (harness)')
  check(pill:IsRune() == false, 'IsRune must be false for a non-card entry')
  check(item:IsRune() == false, 'IsRune must be false for a collectible entry')
  local isRuneArgOk = pcall(function() return card:IsRune(1) end)
  check(not isRuneArgOk, 'IsRune must reject extra arguments')

  savedConfig = config
  savedItem = item
  PHASE1_OK = 1
end

-- 第二帧：向量已经被重新指向另一块数组（等价于换局后的 `ItemConfig::Init`）。
-- 旧句柄必须自证过期；同一帧里新取的句柄必须立刻读到新数据。
local function verifyExpired()
  check(savedConfig ~= nil and savedItem ~= nil, 'the first frame must have produced handles')
  check(savedConfig:GetCollectible(1) == nil,
        'a stale ItemConfig handle must not answer entries')
  check(savedConfig:IsCollectible(1) == false,
        'a stale ItemConfig handle must not answer IsCollectible')
  check(savedItem.ID == nil, 'a stale item handle must not answer ID')
  check(savedItem.Name == nil, 'a stale item handle must not answer Name')
  check(savedItem.Description == nil, 'a stale item handle must not answer Description')
  check(savedItem.GfxFileName == nil, 'a stale item handle must not answer GfxFileName')
  check(savedItem.Quality == nil, 'a stale item handle must not answer Quality')
  check(savedItem:HasTags(1) == false, 'HasTags stays false on a stale handle')

  local fresh = Isaac.GetItemConfig()
  check(fresh ~= nil, 'a new handle must be available right after the vector moved')
  local item = fresh:GetCollectible(1)
  check(item ~= nil, 'the new handle must answer entries')
  check(item.Name == 'Brimstone',
        'the new handle must read the new vector, got ' .. describe(item.Name))
  check(fresh:IsCollectible(1) == true, 'the new handle must answer IsCollectible')
  PHASE2_OK = 1
end

-- 条目指针为 0：单个下标拿不到，其余下标必须照常工作。
local function verifyNullEntry()
  local config = Isaac.GetItemConfig()
  check(config ~= nil, 'the config itself is still readable')
  check(config:GetCollectible(1) == nil, 'a null entry pointer must read as nil')
  check(config:IsCollectible(1) == false, 'a null entry pointer must read as false')
  check(config:GetCollectible(2) ~= nil, 'other indices must still work')
  check(config:GetCollectible(2).Name == LONG_NAME, 'the neighbouring entry must be intact')
end

-- 字符串 size 离谱：`Name` 降级成 nil，但同一对象的其他字段必须照常可读。
local function verifyBadString()
  local item = Isaac.GetItemConfig():GetCollectible(1)
  check(item ~= nil, 'the entry itself is still readable')
  check(item.ID == 1, 'ID must still be readable')
  check(item.Type == 1, 'Type must still be readable')
  check(item.Name == nil, 'an absurd std::string size must read as nil, got '
        .. describe(item.Name))
  check(type(item.Description) == 'string' and #item.Description > 0,
        'the description must be unaffected by the broken name')
  check(item.GfxFileName == 'gfx/items/c1.png',
        'GfxFileName must be unaffected by the broken name, got '
        .. describe(item.GfxFileName))
end

-- 收藏品向量里的条目带着 TRINKET 的类别：`IsCollectible` 必须按 `kind` 说 false。
local function verifyWrongKind()
  local config = Isaac.GetItemConfig()
  local item = config:GetCollectible(1)
  check(item ~= nil, 'the entry is still addressable')
  check(item.Type == 2, 'Type is the raw kind field, got ' .. describe(item.Type))
  check(config:IsCollectible(1) == false, 'IsCollectible rejects trinket type 2')
  check(item:IsCollectible() == false, 'item IsCollectible also rejects type 2')
  -- 同一条目、同一个 `Type` 字段：`IsTrinket` 必须与 `IsCollectible` 给出相反答案。
  check(item:IsTrinket() == true, 'IsTrinket requires kind == 2, got kind 2')
  check(config:IsCollectible(2) == true, 'the neighbouring collectible is untouched')
end

-- `IsAvailable` 的**反例**：引擎函数入口指纹对不上时，方法必须拒绝调用（返回 false），
-- 而不是"照调不误"（偏移写错就会去调别的函数，那比读错值危险得多）。
-- 判据两条：Lua 侧拿到 false；C++ 侧记录的调用数必须是 0。
local function verifyBadIsAvailableEntry()
  local config = Isaac.GetItemConfig()
  check(config ~= nil, 'Isaac.GetItemConfig() must return an ItemConfig')
  local item = config:GetCollectible(1)
  check(item ~= nil, 'GetCollectible(1) must exist even when the entry word is wrong')
  local ok, value = pcall(function() return item:IsAvailable() end)
  check(ok, 'IsAvailable must not raise a Lua error: ' .. tostring(value))
  check(value == false, 'a wrong entry word must degrade to false, got ' .. describe(value))
end

-- 批次 139（2026-09-26）：`Isaac.GetCostumeIdByPath(path)` 的**消费者视角**判据。
-- The Specialist for Good Items 在**文件作用域**就用它建两张服装表（`main.lua:26/29`）
-- ⇒ 这条 API 的判据必须照它的用法来：拿 `costumes2.xml` 里 `anm2root + anm2path` 拼出来的整串去问。
local function verifyCostumeIdByPath()
  -- ① 命中：长串形态（24 字节 ⇒ 堆）与短串形态（19 字节 ⇒ 内联）各一条。
  local long = Isaac.GetCostumeIdByPath('the/specialist_isaac.anm2')
  check(long == 5, 'the long-form path must map to its id (5), got ' .. describe(long))
  local short = Isaac.GetCostumeIdByPath('the/items/binky.anm2')
  check(short == 7, 'the short-form path must map to its id (7), got ' .. describe(short))
  -- ② **逐字**：大小写 / 前后缀 / 斜杠方向 / 截断 —— 任一不同都必须答 -1，而且**不抛错**
  --    （引擎写入侧只是 `memcpy(anm2root) + append(anm2path)`，没有任何改写）。
  local nearMisses = { 'THE/SPECIALIST_ISAAC.ANM2', 'the/specialist_isaac.anm2 ',
                       'gfx/the/specialist_isaac.anm2', 'the\\specialist_isaac.anm2',
                       'the/specialist_isaac', 'specialist_isaac.anm2', '' }
  for _, text in ipairs(nearMisses) do
    local ok, value = pcall(function() return Isaac.GetCostumeIdByPath(text) end)
    check(ok, 'a near-miss path must not raise a Lua error: ' .. tostring(value))
    check(value == -1, 'a near-miss path must answer -1, got ' .. describe(value))
  end
  -- ③ 空串条目（夹具里第 3 条，字节 0）必须被**跳过**：问它自己的"空路径"也仍是 -1 —
  --    上面那个 '' 已经覆盖；这里再确认"跳过它之后后面的条目仍然找得到"（顺序不敏感）。
  check(Isaac.GetCostumeIdByPath('the/items/binky.anm2') == 7,
        'an empty-path entry must not break the scan')
  -- ④ **只搜 null 向量**（已登记的偏离 0x0E01005D）：收藏品条目上也挂着同族路径 ⇒ 必须答 -1。
  local decoy = Isaac.GetCostumeIdByPath('the/specialist_decoy.anm2')
  check(decoy == -1, 'the collectible vector must NOT be searched, got ' .. describe(decoy))
  -- ⑤ 参数口径：PC 用 `luaL_checklstring`（数字会被转成串）⇒ 数字不许报错，只是查不到；
  --    缺参数则报错（PC 的 `bad argument #1`）。
  local numberOk, numberValue = pcall(function() return Isaac.GetCostumeIdByPath(123) end)
  check(numberOk, 'a number argument must not raise (PC coerces it): ' .. tostring(numberValue))
  check(numberValue == -1, 'a number argument maps to no costume, got ' .. describe(numberValue))
  local missingOk = pcall(function() return Isaac.GetCostumeIdByPath() end)
  check(not missingOk, 'calling it without an argument must raise')
end

-- 批次 148（2026-09-26）：`Isaac.GetMusicIdByName(name)` 的**消费者视角**判据。
-- The Specialist for Good Items 的"放歌"就是这条用法：`main.lua:477/478` 拿
-- `GetMusicIdByName("specialist")` 的编号、`:185/186` 拿 `s_<角色>` 那一族的编号，
-- 编号再喂给 `MusicManager():Play(id, 1)`（`main.lua:483/489/494`）。
local function verifyMusicIdByName()
  -- ① 两条内置曲目（夹具下标 0/1，第二条的名字是**长串**⇒ 堆形态）必须各自返回自己的下标。
  -- ★ 每条只查**一次**并存下来再断言：`check(..., 消息)` 的消息是**先求值**的，
  --   把调用写进消息里会让它被查两次 ⇒ 埋点的调用计数就与这里数出来的对不上。
  local title = Isaac.GetMusicIdByName('Title Screen')
  check(title == 0, 'the first track must map to index 0, got ' .. describe(title))
  local longName = Isaac.GetMusicIdByName('Burning Basement (long-form track name)')
  check(longName == 1, 'a long-form name must map to its index (1), got ' .. describe(longName))
  -- ② 模组追加的那条（下标 2）—— 这就是"放歌"真正要的那一下。
  local specialist = Isaac.GetMusicIdByName('specialist')
  check(specialist == 2, 'the modded track must map to its index (2), got ' .. describe(specialist))
  -- ③ 查不到 ⇒ **-1**（PC 契约同页 :292 明写），而且**不抛错**。
  local misses = { 'PAINCIALIST', 'specialist ', ' specialist', 'specialist.ogg', '',
                   'decoy_path_2.ogg', 'Title Screen X' }
  for _, text in ipairs(misses) do
    local ok, value = pcall(function() return Isaac.GetMusicIdByName(text) end)
    check(ok, 'a near-miss name must not raise a Lua error: ' .. tostring(value))
    check(value == -1, 'a near-miss name must answer -1, got ' .. describe(value))
  end
  -- ④ ★ **字段不能读错**：夹具每条的 `+0x20`（真机上那一格是 path）与 `+0x38` 都摆了诱饵串
  --    ⇒ 若实现读的是那两格，上面 ③ 里那两个诱饵名就会被"命中"（返回数字而不是 -1），断言会红。
  -- ⑤ 参数口径照 PC 的 `luaL_checklstring`：数字不许报错（转成串、查不到 ⇒ -1）；缺参数报错。
  local numberOk, numberValue = pcall(function() return Isaac.GetMusicIdByName(123) end)
  check(numberOk, 'a number argument must not raise (PC coerces it): ' .. tostring(numberValue))
  check(numberValue == -1, 'a number argument maps to no track, got ' .. describe(numberValue))
  local missingOk = pcall(function() return Isaac.GetMusicIdByName() end)
  check(not missingOk, 'calling it without an argument must raise')
end

local RUNNERS = {
  null_entry = verifyNullEntry,
  bad_string = verifyBadString,
  wrong_kind = verifyWrongKind,
  bad_isavailable_entry = verifyBadIsAvailableEntry,
  costume_id_by_path = verifyCostumeIdByPath,
  music_id_by_name = verifyMusicIdByName,
}

local function run()
  frame = frame + 1
  if SCENARIO == 'valid' then
    if frame == 1 then
      verifyValid()
    elseif frame == 2 then
      verifyExpired()
    end
    SCENARIO_OK = 1
    return
  end
  local runner = RUNNERS[SCENARIO] or verifyUnavailable
  runner()
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


class LuaItemConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        cc, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-item-config-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "item_config_harness.cpp"
        harness.write_text(
            HARNESS.replace("@SCRIPT@", SCRIPT).replace("@LONG_NAME@", LONG_NAME).lstrip()
        )
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
        cls.harness = temporary / "item_config_harness"
        build = subprocess.run(
            [cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             # ★ 批次 388 补（2026-10-07）：`costume_id_by_path` / `music_id_by_name` 两个场景读的是
             # `ApiRowStatsSnapshot()` 里的服装/曲目查表埋点，而那些计数被**批次 232 的探针总开关**
             # （`EXL_DIAGNOSTIC_PROBES`，见 `runtime/source/probe_gate.hpp`）包住了
             # （`api_call_stats.hpp` 的 `RecordCostumePathLookup` / `RecordMusicIdLookup`）。
             # 宿主 harness 原来**没有**定义这个宏 ⇒ 埋点体被编译掉 ⇒ 计数恒 0 ⇒ 那两条断言
             # （`COSTUME_STATS calls=12 …` / `MUSIC_STATS calls=11 …`）**必然失败**。
             # 这是 232 引入的回归：真机跑诊断包（`make DIAGNOSTIC_PROBES=1`）时是好的，只有宿主
             # harness 会踩到；同族的 `test_lua_entity_player.py` 已在批次 252 用同样方式补过。
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

    def test_collectible_fields_and_parallel_vectors(self):
        """`GetCollectible(1)` 的字段、并列向量、越界/负数/非整数一律 nil、`HasTags` 恒假。

        伪造内存按反汇编结论摆放（`IC = Manager + 0x36538` 的内嵌对象、收藏品向量 733 项、
        条目 `+0x00` 类别 / `+0x04` id / `+0x08` 名字 / `+0x20` 描述），Lua 侧逐条断言；
        短串与长串（> 22 字节）两条 libc++ `std::string` 路径都在这一帧里被读到。
        """
        result = self.run_scenario("valid")
        self.assertIn("ITEM_CONFIG_OK scenario=valid", result.stdout)
        # `IsAvailable` 的分派：顺序 = 收藏品（kind 0，flags 0xE = 14）、卡牌（kind 1，flags 0）、
        # 药丸（kind 2，flags 0）。Lua 侧的布尔返回值分不出 kind 1 与 2，所以这条是必要的第二重证据。
        self.assertIn("ISAVAIL_CALLS 3 0:14 1:0 2:0", result.stdout)
        self.assertIn("PHASE1_OK", result.stdout)

    def test_stale_handles_degrade_and_new_handles_re_read_the_engine(self):
        """每次访问都重新校验：向量被重排后，旧句柄一律 nil，新句柄立刻读到新数据。

        harness 在两帧之间把收藏品向量重新指向另一块数组（`ItemConfig::Init` 的等价形态）。
        旧 `ItemConfig` 句柄缓存的 begin 与现场不一致 → `GetCollectible` 返回 nil；
        旧条目句柄的"向量 begin + 下标"不再匹配 → 字段返回 nil；
        同一帧新取的句柄必须读到新向量里的 "Brimstone"。
        """
        result = self.run_scenario("valid")
        self.assertIn("PHASE1_OK", result.stdout)
        self.assertIn("PHASE2_OK", result.stdout)

    def test_costume_id_by_path_maps_the_exact_path_and_answers_minus_one_otherwise(self):
        """★ 批次 139：`Isaac:GetCostumeIdByPath(path)` 的**消费者视角**判据。

        The Specialist for Good Items 在**文件作用域**就用它建两张服装表（`main.lua:26/29`，缺它整个模组
        加载失败），所以判据照它的用法来：夹具在 **null 服装向量**里放三条 —— 长串路径（24 字节 ⇒ 堆形态）
        id 5、短串路径（19 字节 ⇒ 内联形态）id 7、空串 id 9 —— 然后断言：

        * 两条都能**命中并返回各自的 id**（两种 libc++ 串形态都走到）；
        * 大小写 / 前后缀（`gfx/`、尾空格）/ 反斜杠 / 截断 / 空串 ⇒ 一律 **-1 且不抛错**
          （"逐字比对"是引擎写入侧就只做 `memcpy + append` 决定的，比对口径错 ⇒ 模组拿 -1 去
          `AddNullCostume(-1)` ⇒ `GetNullItem(-1)` 是空 ⇒ `AddCostume` 解引用空指针）；
        * **只搜 null 向量**：收藏品条目上也挂着同族路径 ⇒ 必须答 -1（登记在 `api_deviation.cpp` 0x0E01005D）；
        * 参数口径照 PC 的 `luaL_checklstring`：数字不报错（转为串、查不到 ⇒ -1），**缺参数报错**。
        """
        result = self.run_scenario("costume_id_by_path")
        self.assertNotIn("ISAAC_ERROR", result.stdout + result.stderr)
        self.assertIn("ITEM_CONFIG_OK scenario=costume_id_by_path", result.stdout)
        # 批次 141：**常驻埋点**必须逐格对得上这次运行的调用序列（`verifyCostumeIdByPath` 里
        # 一共问了 12 次：3 次命中 —— long / short / binky —— 与 9 次没命中；最后一次命中是 binky
        # 的 id 7；最后一次查表是"数字参数 123"那次，容器里仍是夹具的 3 条）。
        # 这一行是"读数里那几格可信"的判据：埋点挪位置、只在命中路径上加计数、或把容器条目数
        # 记成别的东西，都会在这里红。
        self.assertIn("COSTUME_STATS calls=12 hits=3 misses=9 last=7 null=3", result.stdout)

    def test_music_id_by_name_maps_exact_names_and_answers_minus_one_otherwise(self):
        """★ 批次 148：`Isaac:GetMusicIdByName(name)` 的**消费者视角**判据。

        The Specialist for Good Items 的"放歌"就是这条用法（`main.lua:477/478` 拿 `specialist`、
        `:185/186` 拿 `s_<角色>` 那一族的编号），所以判据照它的用法来：夹具的曲目表放三条
        —— 下标 0 `Title Screen`（短串）、下标 1 一条**长串**名（> 22 字节 ⇒ 堆形态）、
        下标 2 `specialist`（= 模组 `content/music.xml` 追加那条的等价物）—— 然后断言：

        * 三条都能**命中并返回自己的下标**（两种 libc++ 串形态都走到）；
        * 大小写 / 尾空格 / 前缀 / `.ogg` 后缀 / 截断 / 空串 ⇒ 一律 **-1 且不抛错**
          （契约同页 :292 明写"找不到返回 -1"）；
        * ★ **字段读错必须被发现**：每条夹具的 `+0x20`（真机上是 path）与 `+0x38` 都摆了诱饵串，
          断言里专门去问那两个诱饵名 ⇒ 实现若读错字段就会"命中"，这里必红；
        * 参数口径照 PC 的 `luaL_checklstring`：数字不报错（转为串、查不到 ⇒ -1），缺参数报错；
        * **常驻埋点**逐格对账（`calls/hits/last/table`）—— `table` 那一格同时就是真机上
          "模组的 `content/music.xml` 进引擎了没有"的直接读数（真机基线 119、进去之后 121）。
        """
        result = self.run_scenario("music_id_by_name")
        self.assertNotIn("ISAAC_ERROR", result.stdout + result.stderr)
        self.assertIn("ITEM_CONFIG_OK scenario=music_id_by_name", result.stdout)
        # 调用序列（`verifyMusicIdByName` 一共 11 次，**都不带"消息里再查一次"**）：
        #   3 次命中（Title Screen / 长串 / specialist）+ 7 个近似名 + 数字参数 123 = 11 次；
        #   最后一次是数字 123 ⇒ 结果 -1、名字记成 "123"；查表时曲目表里 3 条。
        # 缺参数那一次不计：`luaL_checklstring` 在记录埋点**之前**就抛错了（与 PC 同一处报错）。
        self.assertIn("MUSIC_STATS calls=11 hits=3 last=-1 table=3 name=123", result.stdout)

    def test_is_available_refuses_to_call_when_the_entry_word_is_wrong(self):
        """入口指纹对不上 ⇒ **一次调用都不许发生**（宁可返回 false）。

        这条防的是"偏移写错就去调另一个函数"——本项目里比"读到一个错值"危险得多的那种失败。
        宿主上两条证据一起看：Lua 侧拿到 false，且注入的实现**没有被调用过**。
        """
        result = self.run_scenario("bad_isavailable_entry")
        self.assertNotIn("ISAAC_ERROR", result.stdout + result.stderr)
        self.assertIn("ISAVAIL_CALLS 0", result.stdout)

    def test_unreadable_links_return_nil_without_a_lua_error(self):
        """六种"整条链路拿不到"的形态都必须返回 nil，而且不抛 Lua 错误。

        * `no_base`：引擎模块基址根本没发布；
        * `slot_zero`：`g_Manager` 的槽本身是 0（第二级解引用不许读地址 0）；
        * `no_manager`：槽可读、但变量里是空指针；
        * `empty_vector`：`begin == end`（长度为 0）；
        * `bad_length`：`E - B` 不是 8 的倍数（0x16E8 + 4）；
        * `huge_length`：长度超过合理上限（4097 项）。
        """
        for scenario in ("no_base", "slot_zero", "no_manager", "empty_vector", "bad_length",
                         "huge_length"):
            with self.subTest(scenario=scenario):
                result = self.run_scenario(scenario)
                self.assertIn(f"ITEM_CONFIG_OK scenario={scenario}", result.stdout)

    def test_entry_and_string_level_failures_degrade_field_by_field(self):
        """条目级失败只影响那一条读数，不许把整个视图打断。

        * `null_entry`：条目指针为 0 → 该下标是 nil，相邻下标照常；
        * `bad_string`：`is_long` 置位但 size 离谱 → `Name` 是 nil，`ID`/`Type`/`Description`
          照常可读；
        * `wrong_kind`：收藏品向量里的条目带着 TRINKET 的类别 → `Type` 原样返回 2、
          `IsCollectible` 说 false。
        """
        for scenario in ("null_entry", "bad_string", "wrong_kind"):
            with self.subTest(scenario=scenario):
                result = self.run_scenario(scenario)
                self.assertIn(f"ITEM_CONFIG_OK scenario={scenario}", result.stdout)


if __name__ == "__main__":
    unittest.main()

class ItemConfigTagConstantTests(unittest.TestCase):
    """`ItemConfig.TAG_*` 常量必须与 PC 文档逐条一致。

    真机报告 `01789202729`：EID 的 `features/eid_data.lua:1025` 第一件事就是
    `ItemConfig.TAG_GUPPY`，而 Runtime 此前**没有全局 `ItemConfig` 表**（只有实例元表），
    于是整包加载在那一行断掉。这里拿 isaacdocs 快照逐条核对，防止手抄的位号出错。
    """

    def test_tag_constants_match_the_pc_docs(self):
        docs = (
            ROOT / "analysis" / "isaacdocs-snapshot" / "docs" / "enums" / "ItemConfig.md"
        )
        source = (ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp").read_text(
            encoding="utf-8"
        )
        if not docs.is_file():
            self.skipTest(f"缺少 PC 文档快照：{docs}")
        expected: dict[str, int] = {}
        for line in docs.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\|.*?\|\s*1\s*<<\s*(\d+)\s*\|\s*(TAG_[A-Z0-9_]+)\s*\{:", line)
            if match is not None:
                expected[match.group(2)] = int(match.group(1))
        self.assertGreater(len(expected), 30, "PC 文档里应当有 30 条以上的 TAG_* 常量")
        published = {
            name: int(bit)
            for name, bit in re.findall(
                r'ItemConfigConstant\{"(TAG_[A-Z0-9_]+)",\s*(\d+)\}', source
            )
        }
        self.assertEqual(published, expected, "ItemConfig.TAG_* 与 PC 文档不一致")
        # 全局表必须真的发布出去（EID 用的是全局名，不是实例上的字段）。
        self.assertIn('lua_setglobal(state, "ItemConfig")', source)
