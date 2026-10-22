"""门禁：`Room:GetAliveBossesCount()`（批次 310，2026-10-03）。

## 这一条是什么

| API | 契约 | 引擎侧 | 语料调用点 |
| --- | --- | --- | --- |
| `Room:GetAliveBossesCount()` | `Room.md:86/88`（`#### int GetAliveBossesCount ( )`） | `max(0, *(i32*)(Room+0x1A60) + *(i32*)(Room+0x1A64))` | 2 |

★ 谁在调：`BOIStageAPI15` 判"这一波 Boss 打完没"（`GetAliveBossesCount() < 1 or Room:IsClear()`）、
`BossRushWaveCounter` 数"这波还剩几个 Boss"（`aliveBossesCount > 0`，并与上一帧比较）。
**返回 `nil` 会让那两处的比较直接抛错、把整条回调摘掉。**

★★★ **批次 311 的更正（接在本文件上）**：本用例原先钉的是 `Room + 0x1A58`/`+0x1A5C`
—— **那是「敌人」那一对**，不是 Boss。原因：PC 上这两条 API 是**紧邻的孪生函数**，
读的是**相邻的两对格子**、尾巴一模一样，只有偏移不同：

| PC 绑定 | 读的两格 |
| --- | --- |
| `Room:GetAliveEnemiesCount @ 0x448000` | `+0x12C0` / `+0x12C4` |
| `Room:GetAliveBossesCount @ 0x448020` | `+0x12C8` / `+0x12CC` |

而 Switch 侧 `Room + 0x1A58`/`+0x1A5C` 的归属由**具名函数**钉死：
`Entity_NPC::get_alive_enemy_count() @ 0x122768`（函数名自己写着 **enemy**）读的就是它。
⇒ 本用例现在钉 **Boss 对**（`kRoomAliveBossesCountOffset = 0x1A60`）；
**敌人对**（`0x1A58`）归批次 311 的 `test_lua_batch311_alive_enemies.py`。
★ 教训：**两条 API 名字相近时，必须逐个核各自的绑定 VA**（这次两条只差 `0x20`，一眼扫过就张冠李戴）。

## 凭什么说这两格、这个算式（**两边逐句同义**）

★★ **PC 的绑定本体就是一个算式**（`Room:GetAliveBossesCount @ 0x448020`）：
`mov edx,[ecx+0x12CC]`（第 2 格）+ `mov ecx,[ecx+0x12C8]`（第 1 格）→ `add ecx,edx` →
`test ecx,ecx` → **`cmovg eax,ecx`** ⇒ **有符号求和、负数清成 0**
（与孪生函数 `GetAliveEnemiesCount @ 0x448000` **逐句相同**，只有偏移不同）。

★★★ **Switch 侧同一段模板在 `0x1447C4` 处与敌人那条并列出现**（这是归属的分水岭）：
`ldr w9,[x8,#0x1a5c]` + `ldr w10,[x8,#0x1a58]` → `add` → **`bic w9,w9,w9,asr#31`**（敌人，夹下限）；
`ldr w10,[x8,#0x1a64]` + `ldr w8,[x8,#0x1a60]` → `add` → **`bic w8,w8,w8,asr#31`**（Boss，夹下限）；
最后 `sub w20, w9, w8`（**敌人 − Boss**）⇒ 两对**各是一个独立计数**，且**用的是同一个夹下限口径**。

★ 佐证（不是主证据）：PC 两对相距 `8`（`0x12C0`→`0x12C8`），Switch 两对也相距 `8`
（`0x1A58`→`0x1A60`）⇒ **相对顺序一致**；另有多处成对读 `+0x1A60`/`+0x1A64` 再 `cmp … #0` 的代码。

⇒ Switch 的两格是 `Room + 0x1A60`/`+0x1A64`（PC `+0x12C8`/`+0x12CC`，**数值不许平移**），
而**算法语义两边一致** —— 这是本条最硬的判据。

## 宿主验到了什么、没验到什么

* **验到**：
  - **两组正常读数**：`(3, 4) ⇒ 7`、`(0, 0) ⇒ 0`；
  - ★★ **判别组 `(-5, 2) ⇒ 0`**：这是"有符号求和 + 负数清 0"与"无符号相加"**唯一分得开**的那种输入
    —— 无符号相加会答 `4294967293`（既有 `FieldKind::Sum2U32` 就是那个语义 ⇒ 本条**没**复用它）；
  - **参数闸门**（多给实参报错、消息里现拼 `Room:GetAliveBossesCount`）与**接收者闸门**；
  - ★ **拿不到当前房间 ⇒ 答 `0`、不报错**（不是 `nil`：语料拿它做 `< 1` 比较）。
* **没验**：真机上那两格就是"活着的 Boss 数"（宿主里夹具与实现引用同一个常量）
  ⇒ 真机项 = 作业单 **V60**（最强判据 = 清空一间 Boss 房前后读数变化）。
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parent.parent / "source"
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
REMAINING = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

API_INDEX = 0x0034
BINDING_ID = 0x04010034
OFFSET_NAME = "kRoomAliveBossesCountOffset"
CONTRACT = "Room.md:86/88"

#: 夹具里那两格的读数（**判别组**是第三组：有符号求和 vs 无符号相加在这里分道扬镳）。
CASES = (
    ("sum", 3, 4, 7),
    ("zero", 0, 0, 0),
    ("negative", -5, 2, 0),
)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存：只需要两块 int32（`Room + 0x1A58` / `+0x1A5C`），房间本身走
// `ReadCurrentGameRoom` 的桩（与 `Room:GetGridIndex` 那一族用的同一条链）。
namespace {

std::vector<unsigned char> g_RoomBytes;
bool g_RoomAvailable = true;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

void PublishFakeRoom(std::int32_t first, std::int32_t second) {
    g_RoomBytes.assign(kRoomAliveBossesCountOffset + 2 * sizeof(std::int32_t) + 8, 0);
    WriteAt<std::int32_t>(g_RoomBytes, kRoomAliveBossesCountOffset, first);
    WriteAt<std::int32_t>(g_RoomBytes, kRoomAliveBossesCountOffset + sizeof(std::int32_t), second);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    if (!g_RoomAvailable) {
        *room = nullptr;
        return GameRoomObservation::RoomUnreadable;
    }
    *room = reinterpret_cast<void*>(g_RoomBytes.data());
    return GameRoomObservation::Success;
}

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
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    std::int32_t first = 0;
    std::int32_t second = 0;
    if (std::strcmp(scenario, "sum") == 0) {
        first = 3; second = 4;
    } else if (std::strcmp(scenario, "zero") == 0) {
        first = 0; second = 0;
    } else if (std::strcmp(scenario, "negative") == 0) {
        first = -5; second = 2;          // ★ 和是 -3 ⇒ 必须清成 0
    } else if (std::strcmp(scenario, "args") == 0 || std::strcmp(scenario, "badrecv") == 0) {
        first = 3; second = 4;
    } else if (std::strcmp(scenario, "noroom") == 0) {
        g_RoomAvailable = false;
    } else {
        return 91;
    }
    PublishFakeRoom(first, second);

    static const char* kRead =
        "local room = Game():GetRoom()"
        " print('B310 kind=' .. type(room) .. ',' .. type(room.GetAliveBossesCount))"
        " local value = room:GetAliveBossesCount()"
        " print('B310 value=' .. tostring(value) .. ' t=' .. type(value))";
    static const char* kArgs =
        "local room = Game():GetRoom()"
        " local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function msg(f) return tostring(select(2, pcall(f))) end"
        " print('B310 extra=' .. ok(function() return room:GetAliveBossesCount(1) end))"
        " print('B310 extramsg=' .. msg(function() return room:GetAliveBossesCount(1) end))"
        " print('B310 oknone=' .. ok(function() return room:GetAliveBossesCount() end))";
    static const char* kBadRecv =
        "local room = Game():GetRoom()"
        " local f = room.GetAliveBossesCount"
        " print('B310 badrecv=' .. tostring(select(1, pcall(function() return f({}) end))))";
    static const char* kNoRoom =
        "local ok, room = pcall(function() return Game():GetRoom() end)"
        " print('B310 noget=' .. tostring(ok) .. ' kind=' .. type(room))"
        " local okv, value = pcall(function() return room:GetAliveBossesCount() end)"
        " print('B310 nook=' .. tostring(okv) .. ' value=' .. tostring(value) .. ' t=' .. type(value))";

    const char* script = nullptr;
    if (std::strcmp(scenario, "args") == 0) {
        script = kArgs;
    } else if (std::strcmp(scenario, "noroom") == 0) {
        script = kNoRoom;
    } else if (std::strcmp(scenario, "badrecv") == 0) {
        script = kBadRecv;      // 走不到（场景名不在上面那一串里，留着给将来用）
    } else {
        script = kRead;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b310.lua");
    static_cast<void>(result);
    return 0;
}
'''
HARNESS = HARNESS.replace("FAKE_FIRST", "0").replace("FAKE_SECOND", "0")


class RoomAliveBossesBatch310Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b310-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    @staticmethod
    def value(out, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return match.group(1)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_two_adjacent_cells_are_summed(self):
        """正常读数：`(3, 4) ⇒ 7`、`(0, 0) ⇒ 0`；返回类型必须是 `number`。"""
        out = self.run_scenario("sum")
        self.assertIn("B310 kind=userdata,function", out)
        self.assertIn("B310 value=7 t=number", out)
        out = self.run_scenario("zero")
        self.assertIn("B310 value=0 t=number", out)

    def test_a_negative_sum_is_clamped_to_zero(self):
        """★★ **判别组**：`(-5, 2) ⇒ 0`（不是 `-3`、更不是 `4294967293`）。

        PC 的绑定本体是 `add` + `test` + **`cmovg`**（有符号求和、负数清成 0）；
        Switch 侧同一个算式是 `add` + **`bic w19,w8,w8,asr#31`**（同样清成 0）。
        ★ 把这里写成"无符号相加"（既有 `FieldKind::Sum2U32` 的语义）就会答 `4294967293` ⇒ 红。
        """
        out = self.run_scenario("negative")
        self.assertIn("B310 value=0 t=number", out)
        self.assertNotIn("4294967293", out)
        self.assertNotIn("B310 value=-3", out)

    def test_argument_gate_and_bad_receiver(self):
        """参数闸门：只收接收者；接收者不是 `Room` ⇒ 报错。"""
        out = self.run_scenario("args")
        self.assertIn("B310 extra=false", out)
        self.assertIn("Room:GetAliveBossesCount accepts no arguments", out)
        self.assertIn("B310 oknone=true", out)

        out = self.run_scenario("badrecv")
        self.assertIn("B310 badrecv=false", out)

    def test_missing_room_answers_zero_without_erroring(self):
        """★ 拿不到当前房间 ⇒ 答 **`0`**（不是 `nil`）、不报错。

        ★ 为什么必须是整数：语料拿它做 `GetAliveBossesCount() < 1 or Room:IsClear()` 这种比较，
        `nil` 会让比较直接抛错、把整条回调摘掉。
        """
        out = self.run_scenario("noroom")
        self.assertIn("B310 noget=true", out)
        self.assertIn("B310 nook=true value=0 t=number", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 契约引用 / 偏移常量字面值 + 两边的算式证据 / 复用房间解析。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Room, 1, 0x{API_INDEX:04X}), ApiDomain::Room, "Room", '
            f'"GetAliveBossesCount"',
            catalog, "目录里没有 Room:GetAliveBossesCount")
        self.assertIn(CONTRACT, catalog, f"目录行的注释里没有引用契约 {CONTRACT}")
        self.assertIn(f"{{0x{BINDING_ID:08X}, &RoomGetAliveBossesCount}}", remaining,
                      f"绑定表里没有 0x{BINDING_ID:08X} → RoomGetAliveBossesCount")

        block = remaining[remaining.index("int RoomGetAliveBossesCount(lua_State* state) {"):]
        block = block[:block.index("\n}\n")]
        self.assertIn(OFFSET_NAME, block)
        #: ★★ 批次 311：两条孪生 API **共用** `PushRoomAliveCount`（只有偏移不同）⇒
        #:    「房间解析 / 两格紧邻 / 夹下限」那几步落在**共用实现**里，改去那里核。
        self.assertIn("PushRoomAliveCount", block)

        shared = remaining[
            remaining.index("int PushRoomAliveCount(lua_State* state, std::uintptr_t pairOffset) {"):]
        shared = shared[:shared.index("\n}\n")]
        #: ★ 房间解析复用既有的那一条链（不许自己再走一遍 Game → Room）。
        self.assertIn("CurrentRoomAddress()", shared)
        self.assertIn("pairOffset", shared, "两格都用调用方给的偏移算，不许写死")
        self.assertIn("sizeof(std::int32_t)", shared, "第二格必须紧邻（+4）")
        #: ★ 下限：`total > 0 ? … : 0`（负数清成 0）。
        self.assertRegex(shared, r"total\s*>\s*0\s*\?", "必须按 PC 的 `cmovg` 语义夹下限")
        #: ★ 反回归：不许改成无符号相加（那会在负值上答出巨大的数）。
        self.assertNotIn("Sum2U32", shared)

        #: 偏移常量写死 + 两边的算式证据留在常量段里。
        #: ★★ 批次 311 更正：本条读的是 **Boss 对**（`0x1A60`），敌人对是 `0x1A58`
        #:    —— 两个常量都在常量段里，且**相距 8**（PC 的 `0x12C0`→`0x12C8` 同样是 8）。
        self.assertRegex(constants, rf"inline constexpr uintptr_t {OFFSET_NAME}\s*=\s*0x1A60;")
        self.assertRegex(constants,
                         r"inline constexpr uintptr_t kRoomAliveEnemiesCountOffset\s*=\s*0x1A58;",
                         "敌人那一对的常量必须在常量段里（批次 311 立的）")
        self.assertIn("0x448000", constants, "取证里必须留下**敌人**那条 PC 绑定的 VA")
        self.assertIn("cmovg", constants, "取证里必须留下 PC 的 `cmovg`")
        self.assertIn("0x122768", constants, "取证里必须留下 Switch 具名消费者的地址")
        self.assertIn("bic", constants, "取证里必须留下 Switch 的 `bic wN,wN,wN,asr#31`")
        self.assertIn("0x21550", constants, "取证里必须留下基址链（Game → Room*）")
        self.assertIn("0x1447C4", constants, "取证里必须留下「两条公式并列」那一处（归属的分水岭）")
        #: ★★ 反回归：**不许再退回 0x1A58** —— 那正是批次 310 搞反的那一对。
        self.assertNotRegex(constants,
                            rf"inline constexpr uintptr_t {OFFSET_NAME}\s*=\s*0x1A58;")


if __name__ == "__main__":
    unittest.main()
