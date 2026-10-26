"""BUG-014（2026-10-26）：`Game.TimeCounter` 的写入必须真落到引擎。

真机依据（`docs/TimeMachine原包真机测试结果-20261026.md` 的 BUG-014 段）：
TimeMachine 每次加速后做 `Game().TimeCounter = Game().TimeCounter + add`，
320000/PID151 上 144 / 113 逻辑帧两段样本的额外补偿 82 / 161 **全部丢失**
（原生 TimeCounter 只增加了引擎自己的 144 / 113），而同段里的
`BlueWombParTime` / `BossRushParTime` 真实减少了 82 / 161 —— 那两个走 api600 世界字段表。

本测试守三件事：
1. `Game().TimeCounter = n` 之后**读回就是 n**，引擎内存里也真的是 n；
2. 非数字（nil / 字符串 / 表）**不报错、不改变原生值**，落到"忽略计数"那条诊断线上；
3. 真写**不**进忽略计数 —— "写了"与"没写"必须能分开读（"没量到"≠"没发生"）。
"""
import unittest
from .test_api500_world import run_world

MAIN = r'''
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
extern "C" {
extern std::atomic<std::uint32_t> g_IsaacIgnoredFieldWriteCount;
extern char g_IsaacLastIgnoredFieldName[24];
extern std::atomic<std::uint32_t> g_IsaacGameTimeCounterWriteCount;
extern std::int32_t g_IsaacLastGameTimeCounterWrite;
}
// `run_world` 会把生产的 `ReadCurrentGameRoom` / `ReadCurrentGameItemPool` 换成这两个
// （本测试只关心 `Game` 那一段伪造内存，房间/道具池给最小可用值）。
void* Api500WorldRoom(){return g_RoomBytes.data();}
void* Api500WorldPool(){return nullptr;}
int main(){
    static_cast<void>(kScriptTemplate);
    static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);
    static_cast<void>(&ExpectNumber);
    CreateBlocks();
    // `Game` 在这个 harness 里只分配到玩家数组那一段（~0x25C60）；`TimeCounter` 在
    // `Game+0x24F9A0`，必须先把伪造块扩到覆盖它 —— 而且**必须在 `PublishGame()` 之前**
    // （那一步会把 `AddressOf(g_GameBytes)` 存进 owner slot，resize 之后再存就指到旧块上了）。
    g_GameBytes.resize(kGameTimeCounterOffset + 16, 0);
    FillEntities();
    PublishLists();
    PublishGame();
    PublishEntityList(g_RoomBytes, true);
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::SetGameBindings(g_EngineBase + kGameOwnerGlobalSlotOffset, 0x2222);
    WriteAt<std::int32_t>(g_GameBytes, kGameTimeCounterOffset, 5000);
    WriteAt<std::int32_t>(g_GameBytes, 0x24f9a4, 7);   // BossRushParTime
    WriteAt<std::int32_t>(g_GameBytes, 0x24f9a8, 7);   // BlueWombParTime
    const char* script = R"lua(
assert(Game().TimeCounter == 5000, "initial native read")
Game().TimeCounter = 5123
assert(Game().TimeCounter == 5123, "write must read back")
Game().TimeCounter = Game().TimeCounter + 100
assert(Game().TimeCounter == 5223, "read-modify-write (TimeMachine 的补偿写法)")
Game().TimeCounter = -7
assert(Game().TimeCounter == -7, "signed value")
local writes_before = 3
Game().TimeCounter = nil
assert(Game().TimeCounter == -7, "nil 不写、也不报错")
Game().TimeCounter = "abc"
assert(Game().TimeCounter == -7, "非数字字符串不写、也不报错")
Game().TimeCounter = {}
assert(Game().TimeCounter == -7, "表不写、也不报错")
-- `Level` 上没有这个字段（PC 契约里 `Level` 也没有）⇒ 同一个名字挂在 Level 句柄上必须
-- **不许**写进 `Game+0x24F9A0`（owner 判断不能只认字段名）。
Game():GetLevel().TimeCounter = 9999
assert(Game().TimeCounter == -7, "Level 上的同名赋值不许落到 Game 的偏移上")
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@bug-014-time-counter.lua")
        != LuaRuntime::LuaInitResult::Success) {
        LuaRuntime::LuaErrorHistoryEntryView errors[8]{};
        const auto count = LuaRuntime::CopyLuaErrorHistory(errors, 8);
        for (std::size_t i = 0; i < count; ++i) {
            std::fprintf(stderr, "%s\n", errors[i].text);
        }
        return 1;
    }
    std::int32_t native = 0;
    // 直接读伪造块（生产侧的 `ReadField` 已由 `Game().TimeCounter` 的读回覆盖；这里要的是
    // "引擎那块内存本身真的变了"，所以按字节取，避免再绕一层 API）。
    std::memcpy(&native, g_GameBytes.data() + kGameTimeCounterOffset, sizeof(native));
    assert(native == -7);                     // 引擎里真的是 -7（不是只有 getter 在编）
    assert(g_IsaacGameTimeCounterWriteCount.load() == 3);   // 5123 / 5223 / -7
    assert(g_IsaacLastGameTimeCounterWrite == -7);
    assert(g_IsaacIgnoredFieldWriteCount.load() == 4);      // nil / "abc" / {} / Level 上那次
    assert(std::strcmp(g_IsaacLastIgnoredFieldName, "TimeCounter") == 0);
    std::printf("time-counter ok native=%d writes=%u ignored=%u\n", native,
                g_IsaacGameTimeCounterWriteCount.load(), g_IsaacIgnoredFieldWriteCount.load());
    return 0;
}
'''


class GameTimeCounterWrite(unittest.TestCase):
    def test_write_lands_in_engine(self):
        result = run_world(main=MAIN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('time-counter ok', result.stdout + result.stderr)
