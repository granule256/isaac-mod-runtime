"""批次 195（2026-09-29）的**消费者视角**宿主判据：四条 `Get*RNG` + `RNG:RandomInt/RandomFloat`
+ `HasGoldenBomb` / `QueuedItem` / `GetVictoryLap` / `Seeds:*` / `HasTrinket`。

## 这一批修的是什么（三条只读取证规格的落地）

| 证据规格 | 落地内容 |
| --- | --- |
| `analysis/api-restore-rng/spec.json` | 四条 `Get*RNG` 从**恒 nil** 改成真读 `Entity_Player + 0x1BB0/0x1BC8/0x1BE0/0x1BF8` 四张 `vector<RNG>`；并补上 `RNG:RandomInt`/`RandomFloat`（Trinity 写的是 `GetCollectibleRNG(BIRTHRIGHT):RandomFloat()`） |
| `analysis/api-restore-entityplayer-b/spec.json` | `HasGoldenBomb` → 字段数据行（`+0x16D9`）；`QueuedItem` → 真表（`+0x1C38`）；`HasTrinket` → 一次引擎调用（`0x28D3B8`） |
| `analysis/api-restore-game/spec.json` | `Game:GetVictoryLap`（`+0x26FD50`）、`Seeds:GetStartSeed`（`Game+0x25D44`）、`Seeds:IsCustomRun`（`Game+0x25D40` 那一字节；**挑战局那一半刻意没做**，理由见 `runtime_constants.hpp`） |

## 宿主机能测什么、不能测什么

宿主机**没有引擎**，所以"`+0x1BB0` 在真机上确实是那张表"这一层只能真机验收；这里钉的是
**我们这段实现自己的可判定性质**，而且一律取**消费者视角**（照模组那样把返回值用下去）：

1. **四条 RNG 各自指到自己的表**：四组种子的高半字刻意不同（`0x1111`/`0x2222`/`0x3333`/`0x4444`）
   ⇒ 任何一条读错表（例如四条都读 `+0x1BB0`）都会当场对不上；同一族里**换一个 id 必须读到另一格**
   （排除"读到常量"的假通过）。
2. **快照语义**（`api_deviation.cpp` 的 `0x0E010033`~`0x0E010036` 那四条 `design` 的可执行版本）：
   从返回对象上 `Next()`/`RandomInt()` 之后，伪造的引擎内存**一个字节都不许动**；
   同时用 `NEXT_CALLS` 证明那次调用**真的发生过**（不是"没调用所以没变"）。
3. **`RandomInt`/`RandomFloat` 的参数与"操作的是快照"**：宿主注入的实现记下 `this` 与 `Max`
   ⇒ 断言 `this` **不是**引擎里那一格的地址（PC 改的是实体里那颗 RNG）。
4. **越界与负数一律 `nil`**（负数、`>= count`、`begin == 0` 三种），且**不抛 Lua 错误**。
5. **形状**：`GetSeed`/`Next`/`SetSeed`/`RandomInt`/`RandomFloat` 五个方法都可取，
   链式 `player:GetCollectibleRNG(id):GetSeed()` 不抛错（Trinity 的写法）。
6. **字段真读**：`HasGoldenBomb`（`+0x16D9` 的 0/1）、`QueuedItem` 的 `Charge`/`Touched`/`Item`
   （含"没举着东西时 `.Item == nil` 但 `Charge`/`Touched` 仍是数字/布尔"——`nil > 0` 会抛错）、
   `GetVictoryLap`（0/1/3 三档取值）、`Seeds:GetStartSeed`（**int32 呈现**：`0xDEADBEEF` 必须是负数）、
   `Seeds:IsCustomRun`（那一字节的 0/1）。
7. **`HasTrinket` 的引擎调用形状**：宿主跳板拿不到返回值 ⇒ 退回钉**参数原样到达**
   （`x0` = 玩家地址、`x1` = 饰品 id、`x2` = `IgnoreModifiers`），以及"无效 id 不调引擎"。

**两个场景**（`first` / `second`）把所有字段与种子整体挪一个常量 ⇒ "读到常量"的假实现无法同时过两关。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "interfaces/lua/isaac_api.hpp"

#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 批次 141 起宿主上"这一行到底有没有调进引擎"的唯一观测点；批次 195 起它还会记下
// 最后一次调用的目标地址与两个参数数组（`engine_call_trampoline_host_stub.cpp`）。
extern "C" {
extern std::uint32_t g_HostEngineCallTrampolineCalls;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
}

namespace {

const char* kScriptTemplate = R"lua(@SCRIPT@)lua";

// --- 伪造的引擎内存 ---------------------------------------------------------
//
// 与真机同形：模块块[base + 0xAAC698] = &g_OwnerSlot 变量（槽里是**变量地址**）→ 变量里是
// `Game*` → `Game + 0x25C50/+0x25C58` 的玩家向量 → `Entity_Player`（首字是 vtable）。
// `Manager` 那条链同样摆出来（`EntityPlayer.QueuedItem.Item` 要经它拿 `ItemConfig`）。
std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_ManagerSlotBytes;
std::vector<unsigned char> g_ManagerBytes;
std::vector<unsigned char> g_CostumeItemBytes;
std::vector<unsigned char> g_NullCostumeElements;

// 四张 `vector<RNG>` 的**元素数组**（每格 16 字节）。
std::vector<unsigned char> g_CollectibleRngs;
std::vector<unsigned char> g_TrinketRngs;
std::vector<unsigned char> g_PillRngs;
std::vector<unsigned char> g_CardRngs;

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

std::uint32_t ReadWordAt(const std::vector<unsigned char>& block, std::size_t offset) {
    std::uint32_t value = 0;
    std::memcpy(&value, block.data() + offset, sizeof(value));
    return value;
}

// 两个场景的种子：**高半字按表区分**（读错表立刻可见），`second` 整体再挪 0x10000
// （"读到常量"的实现过不了两关）。
constexpr std::uint32_t kDelta = 0x10000;
constexpr std::uint32_t kCollectibleSeeds[4] = {0x11110001, 0x11110002, 0x11110003, 0x11110004};
constexpr std::uint32_t kTrinketSeeds[3] = {0x22220011, 0x22220022, 0x22220033};
constexpr std::uint32_t kPillSeeds[2] = {0x33330077, 0x33330088};
constexpr std::uint32_t kCardSeeds[5] = {0x444400A1, 0x444400A2, 0x444400A3, 0x444400A4,
                                         0x444400A5};

//: `Game:GetStartSeed` 的两个取值：`0x12345678`（正）与 `0xDEADBEEF`（**按 int32 是负数**）。
constexpr std::uint32_t kStartSeedFirst = 0x12345678;
constexpr std::uint32_t kStartSeedSecond = 0xDEADBEEF;
constexpr std::int32_t kStartSeedSecondSigned = static_cast<std::int32_t>(kStartSeedSecond);

void FillRngTable(std::vector<unsigned char>& block, const std::uint32_t* seeds,
                  std::size_t count, std::uint32_t delta) {
    block.assign(count * kEntityPlayerRngVectorStride, 0);
    for (std::size_t index = 0; index < count; ++index) {
        WriteAt<std::uint32_t>(block, index * kEntityPlayerRngVectorStride, seeds[index] + delta);
    }
}

void PublishFakeEngine(bool second) {
    const std::uint32_t delta = second ? kDelta : 0;
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    // `Game` 块要盖住胜利圈（0x26FD50）与 Seeds 对象（0x25D40 起 0x70 字节）。
    g_GameBytes.assign(kGameVictoryLapOffset + sizeof(std::uint32_t) + 16, 0);
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint8_t>(g_PlayerBytes, kEntityExistsOffset, 1);
    g_EngineBase = AddressOf(g_ModuleBytes);

    // --- 玩家 ----------------------------------------------------------------
    WriteWord(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, 1);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, 0);
    // `HasGoldenBomb` 那一格：`first` = 1、`second` = 0（前后各一个字节诱饵 —— 按 4 字节读会读到诱饵）。
    WriteAt<std::uint8_t>(g_PlayerBytes, kEntityPlayerGoldenBombFlagOffset - 1, 0x7Fu);
    WriteAt<std::uint8_t>(g_PlayerBytes, kEntityPlayerGoldenBombFlagOffset, second ? 0u : 1u);
    WriteAt<std::uint8_t>(g_PlayerBytes, kEntityPlayerGoldenBombFlagOffset + 1, 0x7Eu);
    // `QueuedItem`：`first` = 举着一件 null 服装条目（id 42）、Charge 3、Touched 1；
    // `second` = 什么都没举（四个字段全 0）。
    if (!second) {
        WriteWord(g_PlayerBytes, kEntityPlayerQueuedItemOffset + kQueuedItemDataItemOffset,
                  AddressOf(g_CostumeItemBytes));
        WriteAt<std::int32_t>(g_PlayerBytes,
                              kEntityPlayerQueuedItemOffset + kQueuedItemDataChargeOffset, 3);
        WriteAt<std::uint8_t>(g_PlayerBytes,
                              kEntityPlayerQueuedItemOffset + kQueuedItemDataTouchedOffset, 1u);
        WriteAt<std::int32_t>(g_PlayerBytes,
                              kEntityPlayerQueuedItemOffset + kQueuedItemDataVarDataOffset, 9);
    }
    // 四张 RNG 表（begin/end 都写在玩家身上，元素数组是独立块）。
    FillRngTable(g_CollectibleRngs, kCollectibleSeeds, 4, delta);
    FillRngTable(g_TrinketRngs, kTrinketSeeds, 3, delta);
    FillRngTable(g_PillRngs, kPillSeeds, 2, delta);
    FillRngTable(g_CardRngs, kCardSeeds, 5, delta);
    struct VectorSource {
        std::uintptr_t offset;
        const std::vector<unsigned char>* block;
    };
    const VectorSource vectors[4] = {
        {kEntityPlayerCollectibleRngVectorOffset, &g_CollectibleRngs},
        {kEntityPlayerTrinketRngVectorOffset, &g_TrinketRngs},
        {kEntityPlayerPillRngVectorOffset, &g_PillRngs},
        {kEntityPlayerCardRngVectorOffset, &g_CardRngs},
    };
    for (const VectorSource& source : vectors) {
        WriteWord(g_PlayerBytes, source.offset, AddressOf(*source.block));
        WriteWord(g_PlayerBytes, source.offset + sizeof(std::uint64_t),
                  AddressOf(*source.block) + source.block->size());
    }

    // --- `ItemConfig`（`Manager` 里**内嵌**）+ 一条 null 条目（id 42）------------
    g_ManagerBytes.assign(kManagerItemConfigOffset + 0x40, 0);
    g_ManagerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_CostumeItemBytes.assign(0xB0, 0);
    WriteAt<std::uint32_t>(g_CostumeItemBytes, kItemConfigItemTypeOffset, kItemTypeNull);
    WriteAt<std::uint32_t>(g_CostumeItemBytes, kItemConfigItemIdOffset, 42u);
    {
        const std::uint64_t elements[1] = {AddressOf(g_CostumeItemBytes)};
        g_NullCostumeElements.assign(sizeof(elements), 0);
        std::memcpy(g_NullCostumeElements.data(), elements, sizeof(elements));
    }
    WriteWord(g_ManagerBytes, kManagerItemConfigOffset + kItemConfigNullItemBeginOffset,
              AddressOf(g_NullCostumeElements));
    WriteWord(g_ManagerBytes, kManagerItemConfigOffset + kItemConfigNullItemEndOffset,
              AddressOf(g_NullCostumeElements) + sizeof(std::uint64_t));
    WriteWord(g_ManagerSlotBytes, 0, AddressOf(g_ManagerBytes));
    WriteWord(g_ModuleBytes, kGameManagerGlobalSlotOffset, AddressOf(g_ManagerSlotBytes));

    // --- `Game`：胜利圈、Seeds、玩家向量；以及 `HasTrinket` 的入口指纹 --------
    WriteAt<std::int32_t>(g_GameBytes, kGameVictoryLapOffset, second ? 3 : 1);
    WriteAt<std::uint8_t>(g_GameBytes, kGameSeedsObjectOffset + kSeedsCustomRunFlagOffset,
                          second ? 0u : 1u);
    WriteAt<std::uint32_t>(g_GameBytes, kGameSeedsObjectOffset + kSeedsStartSeedOffset,
                           second ? kStartSeedSecond : kStartSeedFirst);
    g_PlayerArrayBytes.assign(sizeof(std::uint64_t), 0);
    WriteWord(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteWord(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteWord(g_GameBytes, kGamePlayerArrayEndOffset,
              AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));
    // `HasTrinket` 走"模块基址 + 偏移 + 入口 4 字节指纹"（与引擎方法数据行同一条判据）。
    WriteAt<std::uint32_t>(g_ModuleBytes, kEntityPlayerHasTrinketOffset,
                           kEntityPlayerHasTrinketEntryWord);

    WriteWord(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteWord(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

// --- 宿主注入的引擎实现（RNG 一族）------------------------------------------
std::uint32_t g_NextCalls = 0;
std::uintptr_t g_LastNextThis = 0;
std::uint32_t g_RandomIntCalls = 0;
std::uintptr_t g_LastRandomIntThis = 0;
std::uint32_t g_LastRandomIntMax = 0;
std::uint32_t g_RandomFloatCalls = 0;
std::uintptr_t g_LastRandomFloatThis = 0;

void HostSetSeed(void* storage, std::uint32_t seed, std::uint32_t shift) {
    auto* bytes = static_cast<unsigned char*>(storage);
    std::memcpy(bytes, &seed, sizeof(seed));
    const std::uint32_t shifts[3] = {shift, shift + 1, shift + 2};
    std::memcpy(bytes + 4, shifts, sizeof(shifts));
}

void HostNext(void* storage) {
    auto* bytes = static_cast<unsigned char*>(storage);
    std::uint32_t seed = 0;
    std::memcpy(&seed, bytes, sizeof(seed));
    seed = seed * 7u + 1u;
    std::memcpy(bytes, &seed, sizeof(seed));
    ++g_NextCalls;
    g_LastNextThis = reinterpret_cast<std::uintptr_t>(storage);
}

std::uint32_t HostRandomUint(void* storage, std::uint32_t maximum) {
    ++g_RandomIntCalls;
    g_LastRandomIntThis = reinterpret_cast<std::uintptr_t>(storage);
    g_LastRandomIntMax = maximum;
    return 0xABCDu;
}

float HostRandom(void* storage) {
    ++g_RandomFloatCalls;
    g_LastRandomFloatThis = reinterpret_cast<std::uintptr_t>(storage);
    return 0.25F;
}

// `GameFileReader` / 各家族的观察缝由 `shared_lua_stubs.cpp` 的弱默认提供（本场景不需要改）。

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const std::string scenario = argv[1];
    if (scenario != "first" && scenario != "second") return 91;
    const bool second = scenario == "second";

    // `g_CostumeItemBytes` 必须在 `PublishFakeEngine` 之前分配好（里面有它的地址）。
    g_CostumeItemBytes.assign(0xB0, 0);
    PublishFakeEngine(second);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    LuaRuntime::SetRngBindings(reinterpret_cast<uintptr_t>(&HostSetSeed),
                              reinterpret_cast<uintptr_t>(&HostNext));
    LuaRuntime::SetRngRandomBindings(reinterpret_cast<uintptr_t>(&HostRandomUint),
                                     reinterpret_cast<uintptr_t>(&HostRandom));

    std::string script = "SCENARIO = '" + scenario + "'\n" + kScriptTemplate;
    const auto result = LuaRuntime::InitializeFromBuffer(script.c_str(), script.size(),
                                                         "@batch195.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("ISAAC_FAIL: the Lua state did not initialize\n");
        return 2;
    }
    const auto dispatch = [](int step) {
        LuaRuntime::DispatchPostUpdate();
        if (!LuaRuntime::TakeCallbackError()) {
            return true;
        }
        char text[512] = {0};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(text, sizeof(text)));
        std::printf("LUA_ERROR(step %d)=%s\n", step, text);
        return false;
    };
    // 第 1 帧：四条 RNG + 所有标量字段；第 2~5 帧：`HasTrinket` 的四种调用形状各一次
    // （**每帧只调一次** ⇒ C++ 能在帧与帧之间读出跳板的 `x0/x1/x2`）。
    if (!dispatch(1)) return 1;
    for (int step = 2; step <= 5; ++step) {
        const std::uint32_t before = g_HostEngineCallTrampolineCalls;
        if (!dispatch(step)) return 1;
        std::printf("TRINKET_STEP step=%d calls=%u delta=%u target=%llx x0=%llx x1=%llu x2=%llu\n",
                    step, g_HostEngineCallTrampolineCalls,
                    g_HostEngineCallTrampolineCalls - before,
                    static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget),
                    static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[0]),
                    static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[1]),
                    static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[2]));
    }

    // --- 快照语义：引擎那四块内存必须**一个字节都没动** ------------------------
    const std::uint32_t delta = second ? kDelta : 0;
    struct TableCheck {
        const std::vector<unsigned char>* block;
        const std::uint32_t* seeds;
        std::size_t count;
    };
    const TableCheck checks[4] = {
        {&g_CollectibleRngs, kCollectibleSeeds, 4},
        {&g_TrinketRngs, kTrinketSeeds, 3},
        {&g_PillRngs, kPillSeeds, 2},
        {&g_CardRngs, kCardSeeds, 5},
    };
    bool engineUntouched = true;
    for (const TableCheck& check : checks) {
        for (std::size_t index = 0; index < check.count; ++index) {
            std::uint32_t expected = check.seeds[index] + delta;
            if (check.block == &g_CollectibleRngs && index == 0) { expected = expected * 7U + 1U; }
            if (ReadWordAt(*check.block, index * kEntityPlayerRngVectorStride) != expected) {
                std::printf("ISAAC_FAIL: the engine RNG at index %zu must match %08x\n", index,
                            expected);
                engineUntouched = false;
            }
        }
    }

    const std::uintptr_t collectibleElement = AddressOf(g_CollectibleRngs);
    std::printf("SCENARIO=%s NEXT_CALLS=%u ENGINE_MATCHES=%d\n", scenario.c_str(), g_NextCalls,
                engineUntouched ? 1 : 0);
    std::printf("RANDOMINT calls=%u max=%u this_is_snapshot=%d\n", g_RandomIntCalls,
                g_LastRandomIntMax, g_LastRandomIntThis != collectibleElement ? 1 : 0);
    std::printf("RANDOMFLOAT calls=%u this_is_snapshot=%d\n", g_RandomFloatCalls,
                g_LastRandomFloatThis != collectibleElement ? 1 : 0);
    std::printf("PLAYER=%llx TRINKET_METHOD=%llx START_SEED_SIGNED=%d\n",
                static_cast<unsigned long long>(AddressOf(g_PlayerBytes)),
                static_cast<unsigned long long>(g_EngineBase + kEntityPlayerHasTrinketOffset),
                second ? static_cast<int>(kStartSeedSecondSigned) : static_cast<int>(kStartSeedFirst));
    return engineUntouched ? 0 : 5;
}
'''

SCRIPT = r'''
local mod = RegisterMod('Batch195 host', 1)

local function check(condition, message)
  if not condition then error(message, 2) end
end

local function describe(value)
  if value == nil then return 'nil' end
  return type(value) .. ':' .. tostring(value)
end

local DELTA = (SCENARIO == 'second') and 0x10000 or 0

local function verifyRngVectors()
  local player = Isaac.GetPlayer(0)
  check(player ~= nil, 'Isaac.GetPlayer(0) must return the player')

  -- 四条各自指到自己的表：四组种子的高半字不同（0x1111/0x2222/0x3333/0x4444）⇒ 读错表当场可见。
  local collectible = player:GetCollectibleRNG(0)
  check(collectible ~= nil, 'GetCollectibleRNG(0) must return an RNG, got ' .. describe(collectible))
  check(collectible:GetSeed() == 0x11110001 + DELTA,
        'GetCollectibleRNG(0):GetSeed() must read +0x1BB0 cell 0, got '
        .. describe(collectible:GetSeed()))
  check(player:GetCollectibleRNG(3):GetSeed() == 0x11110004 + DELTA,
        'another collectible id must read another cell, got '
        .. describe(player:GetCollectibleRNG(3):GetSeed()))
  check(player:GetTrinketRNG(0):GetSeed() == 0x22220011 + DELTA,
        'GetTrinketRNG(0) must read +0x1BC8 cell 0, got '
        .. describe(player:GetTrinketRNG(0):GetSeed()))
  check(player:GetTrinketRNG(2):GetSeed() == 0x22220033 + DELTA,
        'another trinket id must read another cell')
  check(player:GetPillRNG(0):GetSeed() == 0x33330077 + DELTA,
        'GetPillRNG(0) must read +0x1BE0 cell 0, got '
        .. describe(player:GetPillRNG(0):GetSeed()))
  check(player:GetPillRNG(1):GetSeed() == 0x33330088 + DELTA,
        'another pill id must read another cell')
  check(player:GetCardRNG(0):GetSeed() == 0x444400A1 + DELTA,
        'GetCardRNG(0) must read +0x1BF8 cell 0, got '
        .. describe(player:GetCardRNG(0):GetSeed()))
  check(player:GetCardRNG(4):GetSeed() == 0x444400A5 + DELTA,
        'another card id must read another cell')

  -- 形状：PC 的 RNG 面五个方法都要在（缺一个就是模组侧的 "attempt to call a nil value"）。
  for _, name in ipairs({ 'GetSeed', 'Next', 'SetSeed', 'RandomInt', 'RandomFloat' }) do
    check(type(collectible[name]) == 'function',
          'RNG:' .. name .. ' must be a function, got ' .. describe(collectible[name]))
  end
  -- 链式调用（Trinity 的 `GetCollectibleRNG(id):RandomFloat()` 同形）。
  local chainOk, chained = pcall(function() return player:GetCollectibleRNG(1):GetSeed() end)
  check(chainOk, 'the chained GetSeed must not raise: ' .. tostring(chained))
  check(chained == 0x11110002 + DELTA,
        'the chained GetSeed must read cell 1, got ' .. describe(chained))

  -- 越界与负数：一律 nil、**不抛错**（引擎自己对越界是"打一句然后照样越界读"）。
  check(player:GetCollectibleRNG(4) == nil, 'id == count must be nil')
  check(player:GetCollectibleRNG(-1) == nil, 'a negative id must be nil')
  check(player:GetTrinketRNG(3) == nil, 'trinket id == count must be nil')
  check(player:GetCardRNG(99) == nil, 'an out of range card id must be nil')
  check(player:GetPillRNG(-5) == nil, 'a negative pill id must be nil')
  -- 参数口径：不是整数要报错（PC 的 `luaL_checkinteger` 同口径）。
  local badIdOk = pcall(function() return player:GetCollectibleRNG('x') end)
  check(not badIdOk, 'a non-integer id must raise')

  -- 快照语义：`Next()` 推进的是**句柄自己**（引擎那块内存由 C++ 侧回读比对）。
  local advanced = collectible:Next()
  check(type(advanced) == 'number', 'Next must return a number, got ' .. describe(advanced))
  check(collectible:GetSeed() ~= 0x11110001 + DELTA,
        'the snapshot seed must change after Next')
  -- 宿主注入的 `RandomInt`/`RandomFloat`（真机上是引擎的 `RNG::Random`）。
  check(collectible:RandomInt(50) == 0xABCD, 'RandomInt must return the engine value')
  check(collectible:RandomFloat() == 0.25, 'RandomFloat must return the engine value')
  local noArgOk = pcall(function() return collectible:RandomInt() end)
  check(not noArgOk, 'RandomInt without a maximum must raise')
  local badMaxOk = pcall(function() return collectible:RandomInt('x') end)
  check(not badMaxOk, 'RandomInt with a non-integer maximum must raise')
  local floatArgOk = pcall(function() return collectible:RandomFloat(1) end)
  check(not floatArgOk, 'RandomFloat with an argument must raise')
  RNG_OK = 1
end

local function verifyScalarFields()
  local player = Isaac.GetPlayer(0)
  -- `HasGoldenBomb` = `Entity_Player + 0x16D9`（数据行；前后各一个字节诱饵）。
  check(player:HasGoldenBomb() == (SCENARIO ~= 'second'),
        'HasGoldenBomb must read +0x16D9, got ' .. describe(player:HasGoldenBomb()))

  -- `player.QueuedItem`：PC 上**永远是一张表**；没举着东西时 `.Item == nil`，但
  -- `.Charge` 必须是数字、`.Touched` 必须是布尔（`nil > 0` 会抛错并摘掉整条回调）。
  local queued = player.QueuedItem
  check(type(queued) == 'table', 'QueuedItem must be a table, got ' .. describe(queued))
  if SCENARIO == 'second' then
    check(queued.Charge == 0, 'Charge must be 0 when nothing is queued, got '
          .. describe(queued.Charge))
    check(queued.Touched == false, 'Touched must be false when nothing is queued, got '
          .. describe(queued.Touched))
    check(queued.Item == nil, 'Item must be nil when nothing is queued, got ' .. describe(queued.Item))
  else
    check(queued.Charge == 3, 'Charge must read +0x1C40, got ' .. describe(queued.Charge))
    check(queued.Touched == true, 'Touched must read +0x1C44, got ' .. describe(queued.Touched))
    check(queued.Item ~= nil, 'Item must be the ItemConfig_Item handle, got ' .. describe(queued.Item))
    check(queued.Item.ID == 42, 'the queued item id must be 42, got ' .. describe(queued.Item.ID))
    check(queued.Item.Type == 0, 'the queued item type must be 0, got ' .. describe(queued.Item.Type))
    -- 消费者视角：EID 写的是 `player.QueuedItem.Charge > 0`（空表时这一句会抛错）。
    check((queued.Charge > 0) == true, 'the EID comparison `QueuedItem.Charge > 0` must work')
  end

  -- `Game:GetVictoryLap()`（`+0x26FD50`，两个场景取值不同）。
  check(Game():GetVictoryLap() == (SCENARIO == 'second' and 3 or 1),
        'GetVictoryLap must read +0x26FD50, got ' .. describe(Game():GetVictoryLap()))

  -- `Game:GetSeeds()` 的两个方法（引擎真值）。
  local seeds = Game():GetSeeds()
  check(seeds ~= nil, 'GetSeeds must not be nil')
  local startSeed = seeds:GetStartSeed()
  check(type(startSeed) == 'number', 'GetStartSeed must return a number, got ' .. describe(startSeed))
  -- ★ PC 的返回类型是 int ⇒ `0xDEADBEEF` 必须是**负数**（直接推 u32 会得到 3735928559）。
  check(startSeed == (SCENARIO == 'second' and -559038737 or 305419896),
        'GetStartSeed must read +0x25D44 as a signed int, got ' .. describe(startSeed))
  check(seeds:IsCustomRun() == (SCENARIO ~= 'second'),
        'IsCustomRun must read the byte at Game+0x25D40, got ' .. describe(seeds:IsCustomRun()))
end

-- `HasTrinket`：改动之后它是**一次引擎调用**（`Entity_Player::HasTrinket @ 0x28D3B8`）。
-- 宿主跳板拿不到返回值（真值要真机）⇒ 这里只钉"参数形状"那一半：**每一帧只调一次**，
-- 由 C++ 侧逐帧快照跳板的 `x0/x1/x2`（读数行 `TRINKET_STEP`）。取值那一半的判据写在
-- `analysis/api-restore-entityplayer-b/spec.json` 的 device_criteria 里。
local function verifyHasTrinketStep()
  local player = Isaac.GetPlayer(0)
  if STEP == 2 then
    local ok, value = pcall(function() return player:HasTrinket(30, false) end)
    check(ok, 'HasTrinket(30, false) must not raise: ' .. tostring(value))
    check(type(value) == 'boolean', 'HasTrinket must return a boolean, got ' .. describe(value))
  elseif STEP == 3 then
    local ok, value = pcall(function() return player:HasTrinket(30, true) end)
    check(ok, 'HasTrinket(30, true) must not raise: ' .. tostring(value))
    check(type(value) == 'boolean', 'HasTrinket must return a boolean, got ' .. describe(value))
  elseif STEP == 4 then
    -- 一个参数也不传：PC 的 `IgnoreModifiers` 可省（等价于 false），同样必须到达引擎。
    local ok, value = pcall(function() return player:HasTrinket(30) end)
    check(ok, 'HasTrinket(30) must not raise: ' .. tostring(value))
    check(type(value) == 'boolean', 'HasTrinket must return a boolean, got ' .. describe(value))
  elseif STEP == 5 then
    -- `id = 0`（TRINKET_NONE）**不调引擎**（负/0/超 uint32 在被调方挡下）。
    check(player:HasTrinket(0) == false, 'TRINKET_NONE must answer false')
    check(player:HasTrinket(0, true) == false, 'TRINKET_NONE must answer false (two-argument form)')
    TRINKET_OK = 1
  end
end

mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  STEP = (STEP or 0) + 1
  local ok, err = pcall(function()
    if STEP == 1 then
      verifyRngVectors()
      verifyScalarFields()
      VECTORS_OK = 1
    else
      verifyHasTrinketStep()
    end
  end)
  if not ok then
    print('BATCH195_ERROR: ' .. tostring(err))
  end
end)
'''
#: 两个场景下 Lua 侧必须全部通过（脚本失败会以 `LUA_ERROR` 打印并把退出码置 1）。
SCENARIOS = ("first", "second")


class LuaEntityRngAndFieldsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-batch195-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS.replace("@SCRIPT@", SCRIPT),
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> subprocess.CompletedProcess:
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("BATCH195_ERROR", result.stdout, result.stdout + result.stderr)
        return result

    def test_four_rng_getters_read_their_own_vector(self):
        """四条各指到自己的表；同一族换 id 读到另一格（排除常量）。"""
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                result = self.run_scenario(scenario)
                self.assertIn(f"SCENARIO={scenario}", result.stdout)

    def test_the_returned_rng_references_the_engine_object(self):
        """2026-10-09更正：引用直接更新引擎状态。以下原快照说明保留：

        ★ 四条 `design` 偏离的可执行版本：`Next()` 之后引擎内存一个字节都没动。

        同时 `NEXT_CALLS=1` 证明那次调用**真的发生过**（不是"没调用所以没变"），
        `this_is_snapshot=0` 证明 `RandomInt`/`RandomFloat` 操作的是我们那份拷贝。
        """
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                result = self.run_scenario(scenario)
                self.assertIn("ENGINE_MATCHES=1", result.stdout)
                self.assertIn("NEXT_CALLS=1", result.stdout)
                self.assertIn("RANDOMINT calls=1 max=50 this_is_snapshot=0", result.stdout)
                self.assertIn("RANDOMFLOAT calls=1 this_is_snapshot=0", result.stdout)

    def test_has_trinket_reaches_the_engine_with_the_pc_signature(self):
        """`HasTrinket` 的引擎调用形状：`x0` = 玩家、`x1` = 饰品 id、`x2` = `IgnoreModifiers`。

        宿主跳板拿不到返回值（真值要真机）⇒ 这一条钉的是**最容易写错的那一半**：参数按 PC 的
        签名装进寄存器，而且"无效 id（0）不调引擎"。Lua 侧每帧只调一次，C++ 在第 2~5 帧之间
        各读一次跳板状态 ⇒ 四种调用形状逐一可核：

        * 第 2 帧 `HasTrinket(30, false)` → `delta=1`、`x2=0`
        * 第 3 帧 `HasTrinket(30, true)`  → `delta=1`、`x2=1`（PC 的 `IgnoreModifiers` 真的传到了）
        * 第 4 帧 `HasTrinket(30)`        → `delta=1`、`x2=0`（可省参数等价于 false）
        * 第 5 帧 `HasTrinket(0)` ×2      → `delta=0`（`TRINKET_NONE` 在被调方挡下，不调引擎）
        """
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                result = self.run_scenario(scenario)
                steps = {
                    int(line.split()[1].split("=")[1]): dict(
                        item.split("=") for item in line.split()[2:]
                    )
                    for line in result.stdout.splitlines()
                    if line.startswith("TRINKET_STEP ")
                }
                self.assertEqual(sorted(steps), [2, 3, 4, 5], result.stdout)
                players = next(
                    (text for text in result.stdout.splitlines() if text.startswith("PLAYER=")), ""
                )
                player_address = players.split()[0].split("=")[1]
                method_address = players.split()[1].split("=")[1]
                for step, expected_x2 in ((2, "0"), (3, "1"), (4, "0")):
                    with self.subTest(step=step):
                        fields = steps[step]
                        self.assertEqual(fields["delta"], "1", result.stdout)
                        self.assertEqual(fields["x0"], player_address, result.stdout)
                        self.assertEqual(fields["x1"], "30", result.stdout)
                        self.assertEqual(fields["x2"], expected_x2, result.stdout)
                        self.assertEqual(fields["target"], method_address, result.stdout)
                self.assertEqual(steps[5]["delta"], "0", result.stdout)

    def test_scalar_fields_are_read_from_the_engine(self):
        """`GetStartSeed` 按 int32 呈现、`HasGoldenBomb`/`QueuedItem`/`VictoryLap` 逐值可核。

        这些都写在 Lua 脚本里（`second` 场景的 `0xDEADBEEF` 必须是 `-559038737`），
        这里只把 C++ 侧的两个合计读数也钉住（防止"脚本没跑到"这种假通过）。
        """
        first = self.run_scenario("first")
        self.assertIn("START_SEED_SIGNED=305419896", first.stdout)
        second = self.run_scenario("second")
        self.assertIn("START_SEED_SIGNED=-559038737", second.stdout)

    def test_the_two_scenarios_disagree_on_every_seed(self):
        """两个场景的读数必须不同 —— 否则"读到常量"的实现也能过。"""
        first = self.run_scenario("first")
        second = self.run_scenario("second")
        self.assertNotEqual(first.stdout, second.stdout)
        self.assertIn("SCENARIO=first", first.stdout)
        self.assertIn("SCENARIO=second", second.stdout)


if __name__ == "__main__":
    unittest.main()

# 2026-10-09更正：旧快照判据已改为PC活引用；指针比较用uintptr_t，不能截成u32。
