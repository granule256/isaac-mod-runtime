"""门禁：`Room:GetAliveEnemiesCount()`（批次 311，2026-10-03）。

## 这一条是什么

| API | 契约 | 引擎侧 | 语料调用点 |
| --- | --- | --- | --- |
| `Room:GetAliveEnemiesCount()` | `Room.md:93`（`#### int GetAliveEnemiesCount ( )`） | `max(0, *(i32*)(Room+0x1A58) + *(i32*)(Room+0x1A5C))` | 1 |

★ 谁在调：`BOIStageAPI15`（与 `Room:GetAliveBossesCount()` 同一段逻辑：判「这一波打完了没」）。
**返回 `nil` 会让那处比较直接抛错、把整条回调摘掉。**

## ★★★ 本批同时**修正了批次 310 的一处归属错误**

PC 上这两条 API 是**紧邻的孪生函数**，读的是**相邻的两对格子**、尾巴一模一样
（`add` + `test` + **`cmovg`** + `ret`），只有偏移不同：

| PC 绑定 | 读的两格 |
| --- | --- |
| `Room:GetAliveEnemiesCount @ 0x448000` | `+0x12C0` / `+0x12C4` |
| `Room:GetAliveBossesCount @ 0x448020` | `+0x12C8` / `+0x12CC` |

批次 310 只看了 `0x448020`、把「敌人对」当成了 Boss ⇒ 那一批的 `GetAliveBossesCount()`
会返回**敌人**数。本批把归属改对：

* **敌人** = `Room + 0x1A58`/`+0x1A5C`（`kRoomAliveEnemiesCountOffset`）；
* **Boss** = `Room + 0x1A60`/`+0x1A64`（`kRoomAliveBossesCountOffset`）。

### 凭什么说 `+0x1A58` 那一对是「敌人」

① **具名函数**（最硬）：`Entity_NPC::get_alive_enemy_count() @ 0x122768`
（`_ZNK15IsaacRepentance10Entity_NPC21get_alive_enemy_countEv` 是镜像里**唯一**一个 `alive_*`
符号）读的就是 `+0x1A58`/`+0x1A5C`：`x20 = *(g_Game → +0x21550)`（= `Room*`）→
`ldr w8,[x20,#0x1a5c]` + `ldr w9,[x20,#0x1a58]` + `add w8,w9,w8` +
**`bic w19,w8,w8,asr#31`**（负数清成 0）。**函数名自己说的就是 enemy。**

② ★★★ **两条公式并列出现**（`0x1447C4` 起）—— 归属的分水岭：
`ldr w9,[x8,#0x1a5c]` + `ldr w10,[x8,#0x1a58]` → `add` → `bic w9,w9,w9,asr#31`（**敌人**）；
`ldr w10,[x8,#0x1a64]` + `ldr w8,[x8,#0x1a60]` → `add` → `bic w8,w8,w8,asr#31`（**Boss**）；
`sub w20, w9, w8`（敌人 − Boss）⇒ 两对**各是一个独立计数**、**同一个夹下限口径**。

③ 顺序与间距（印证）：PC 两对相距 `8`（`0x12C0`→`0x12C8`），Switch 也相距 `8`
（`0x1A58`→`0x1A60`）⇒ 相对顺序一致。

## 宿主验到了什么、没验到什么

* **验到**：
  - ★★★ **交叉防互换**（本批最值钱的一条）：夹具把**两对**格子都摆出来、且**数值不同**
    （敌人 `(11, 13) ⇒ 24`、Boss `(-5, 2) ⇒ 0`），然后两条 API **各问一次**
    —— 敌人必须答 `24`、Boss 必须答 `0`。**只要两个常量被换回去，这一条立刻红**；
  - 正常读数与**判别组**（`(0, 0) ⇒ 0`、负数求和清 0 —— 与无符号相加在负值上分道扬镳）；
  - **参数闸门**与**接收者闸门**；**拿不到房间 ⇒ 答 `0`、不报错**；
  - **静态**：两个常量相差 `8`、两个 handler **各自引用自己的常量**（不许互相抄）。
* **没验**：真机上那两格就是「活着的敌人数」⇒ 真机项 = 作业单 **V61**
  （最强判据 = 有敌人的房间 `> 0`、清空后 `0`，且与 `GetAliveBossesCount()` **读数不同**）。
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

API_INDEX = 0x0035
BINDING_ID = 0x04010035
OFFSET_NAME = "kRoomAliveEnemiesCountOffset"
BOSS_OFFSET_NAME = "kRoomAliveBossesCountOffset"
CONTRACT = "Room.md:93"

#: 夹具里两对格子的读数。★ 两对**故意给不同的数**，好让「互换」立刻暴露。
CASES = (
    ("cross", (11, 13), (-5, 2)),      # ★★★ 敌人 24 / Boss 0 —— 互换必红
    ("zero", (0, 0), (0, 0)),
    ("sum", (3, 4), (100, 200)),
)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存：两对相邻的 int32（敌人 `+0x1A58`/`+0x1A5C`、Boss `+0x1A60`/`+0x1A64`）。
// 房间本身走 `ReadCurrentGameRoom` 的桩（与 `Room:GetGridIndex` 那一族用的同一条链）。
namespace {

std::vector<unsigned char> g_RoomBytes;
bool g_RoomAvailable = true;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

void PublishFakeRoom(std::int32_t enemyFirst, std::int32_t enemySecond,
                     std::int32_t bossFirst, std::int32_t bossSecond) {
    //: 块要盖住**两对**里更靠后的那一格（Boss 对在 `+0x1A60`）。
    g_RoomBytes.assign(kRoomAliveBossesCountOffset + 2 * sizeof(std::int32_t) + 8, 0);
    WriteAt<std::int32_t>(g_RoomBytes, kRoomAliveEnemiesCountOffset, enemyFirst);
    WriteAt<std::int32_t>(g_RoomBytes, kRoomAliveEnemiesCountOffset + sizeof(std::int32_t),
                          enemySecond);
    WriteAt<std::int32_t>(g_RoomBytes, kRoomAliveBossesCountOffset, bossFirst);
    WriteAt<std::int32_t>(g_RoomBytes, kRoomAliveBossesCountOffset + sizeof(std::int32_t),
                          bossSecond);
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

    std::int32_t e1 = 11, e2 = 13, b1 = -5, b2 = 2;   // ★ 默认 = 交叉那一档
    if (std::strcmp(scenario, "zero") == 0) {
        e1 = 0; e2 = 0; b1 = 0; b2 = 0;
    } else if (std::strcmp(scenario, "sum") == 0) {
        e1 = 3; e2 = 4; b1 = 100; b2 = 200;
    } else if (std::strcmp(scenario, "args") == 0 || std::strcmp(scenario, "badrecv") == 0) {
        e1 = 3; e2 = 4; b1 = 5; b2 = 6;
    } else if (std::strcmp(scenario, "noroom") == 0) {
        g_RoomAvailable = false;
    } else if (std::strcmp(scenario, "cross") != 0) {
        return 91;
    }
    PublishFakeRoom(e1, e2, b1, b2);

    static const char* kRead =
        "local room = Game():GetRoom()"
        " print('B311 kind=' .. type(room) .. ',' .. type(room.GetAliveEnemiesCount))"
        " local e = room:GetAliveEnemiesCount()"
        " local b = room:GetAliveBossesCount()"
        " print('B311 enemy=' .. tostring(e) .. ' t=' .. type(e))"
        " print('B311 boss=' .. tostring(b) .. ' t=' .. type(b))";
    static const char* kArgs =
        "local room = Game():GetRoom()"
        " local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function msg(f) return tostring(select(2, pcall(f))) end"
        " print('B311 extra=' .. ok(function() return room:GetAliveEnemiesCount(1) end))"
        " print('B311 extramsg=' .. msg(function() return room:GetAliveEnemiesCount(1) end))"
        " print('B311 oknone=' .. ok(function() return room:GetAliveEnemiesCount() end))";
    static const char* kBadRecv =
        "local room = Game():GetRoom()"
        " local f = room.GetAliveEnemiesCount"
        " print('B311 badrecv=' .. tostring(select(1, pcall(function() return f({}) end))))";
    static const char* kNoRoom =
        "local ok, room = pcall(function() return Game():GetRoom() end)"
        " print('B311 noget=' .. tostring(ok) .. ' kind=' .. type(room))"
        " local okv, value = pcall(function() return room:GetAliveEnemiesCount() end)"
        " print('B311 nook=' .. tostring(okv) .. ' value=' .. tostring(value) .. ' t=' .. type(value))";

    const char* script = nullptr;
    if (std::strcmp(scenario, "args") == 0) {
        script = kArgs;
    } else if (std::strcmp(scenario, "noroom") == 0) {
        script = kNoRoom;
    } else if (std::strcmp(scenario, "badrecv") == 0) {
        script = kBadRecv;
    } else {
        script = kRead;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b311.lua");
    static_cast<void>(result);
    return 0;
}
'''


class RoomAliveEnemiesBatch311Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b311-")
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

    def test_two_pairs_are_not_swapped(self):
        """★★★ **交叉防互换**（本批最值钱的一条）。

        夹具把**两对**格子都摆出来、且数值不同：敌人 `(11, 13) ⇒ 24`、Boss `(-5, 2) ⇒ 0`。
        ⇒ `GetAliveEnemiesCount()` 必须是 **`24`**、`GetAliveBossesCount()` 必须是 **`0`**。
        ★ 只要批次 310 那个「把敌人对当 Boss」的错误被退回去（两个常量换位），
        这一条立刻红（会答 `0` / `24`）。
        """
        out = self.run_scenario("cross")
        self.assertIn("B311 kind=userdata,function", out)
        self.assertIn("B311 enemy=24 t=number", out)
        self.assertIn("B311 boss=0 t=number", out)

    def test_normal_readings(self):
        """正常读数：`(0, 0)` 两对都答 `0`；`(3, 4) ⇒ 7` 而 Boss 那对 `(100, 200) ⇒ 300`。"""
        out = self.run_scenario("zero")
        self.assertIn("B311 enemy=0 t=number", out)
        self.assertIn("B311 boss=0 t=number", out)
        out = self.run_scenario("sum")
        self.assertIn("B311 enemy=7 t=number", out)
        self.assertIn("B311 boss=300 t=number", out)

    def test_a_negative_sum_is_clamped_to_zero(self):
        """★ **判别组**：Boss 那对 `(-5, 2) ⇒ 0`（不是 `-3`、更不是 `4294967293`）。

        PC 的绑定是 `add` + `test` + **`cmovg`**；Switch 侧是 `add` + **`bic wN,wN,wN,asr#31`**。
        ★ 写成「无符号相加」（既有 `FieldKind::Sum2U32` 的语义）会答 `4294967293` ⇒ 红。
        """
        out = self.run_scenario("cross")
        self.assertNotIn("4294967293", out)
        self.assertNotIn("B311 boss=-3", out)

    def test_argument_gate_and_bad_receiver(self):
        """参数闸门：只收接收者（消息里现拼 `Room:GetAliveEnemiesCount`）；接收者不是 `Room` ⇒ 报错。"""
        out = self.run_scenario("args")
        self.assertIn("B311 extra=false", out)
        self.assertIn("Room:GetAliveEnemiesCount accepts no arguments", out)
        self.assertIn("B311 oknone=true", out)

        out = self.run_scenario("badrecv")
        self.assertIn("B311 badrecv=false", out)

    def test_missing_room_answers_zero_without_erroring(self):
        """★ 拿不到当前房间 ⇒ 答 **`0`**（不是 `nil`）、不报错。"""
        out = self.run_scenario("noroom")
        self.assertIn("B311 noget=true", out)
        self.assertIn("B311 nook=true value=0 t=number", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 契约引用 / 偏移常量字面值 / **两个 handler 各用各的常量**。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Room, 1, 0x{API_INDEX:04X}), ApiDomain::Room, "Room", '
            f'"GetAliveEnemiesCount"',
            catalog, "目录里没有 Room:GetAliveEnemiesCount")
        self.assertIn(CONTRACT, catalog, f"目录行的注释里没有引用契约 {CONTRACT}")
        self.assertIn(f"{{0x{BINDING_ID:08X}, &RoomGetAliveEnemiesCount}}", remaining,
                      f"绑定表里没有 0x{BINDING_ID:08X} → RoomGetAliveEnemiesCount")

        #: ★★ 两个 handler **各自**引用自己的常量 —— 这是「不许互换」的静态那一半。
        enemies = remaining[remaining.index("int RoomGetAliveEnemiesCount(lua_State* state) {"):]
        enemies = enemies[:enemies.index("\n}\n")]
        self.assertIn(OFFSET_NAME, enemies)
        self.assertNotIn(BOSS_OFFSET_NAME, enemies, "敌人那条不许引用 Boss 的常量")

        bosses = remaining[remaining.index("int RoomGetAliveBossesCount(lua_State* state) {"):]
        bosses = bosses[:bosses.index("\n}\n")]
        self.assertIn(BOSS_OFFSET_NAME, bosses)
        self.assertNotIn(OFFSET_NAME, bosses, "Boss 那条不许引用敌人的常量")

        #: ★★ 两条共用同一份实现（只差偏移），不许各写一份。
        self.assertIn("PushRoomAliveCount", enemies)
        self.assertIn("PushRoomAliveCount", bosses)

        #: 常量字面值 + **相差 8**（PC 的 `0x12C0`→`0x12C8` 同样是 8）。
        self.assertRegex(constants, rf"inline constexpr uintptr_t {OFFSET_NAME}\s*=\s*0x1A58;")
        self.assertRegex(constants, rf"inline constexpr uintptr_t {BOSS_OFFSET_NAME}\s*=\s*0x1A60;")
        self.assertIn("0x448000", constants, "取证里必须留下**敌人**那条 PC 绑定的 VA")
        self.assertIn("0x448020", constants, "取证里必须留下 **Boss** 那条 PC 绑定的 VA")
        self.assertIn("0x1447C4", constants, "取证里必须留下「两条公式并列」那一处")
        self.assertIn("0x122768", constants, "取证里必须留下 Switch 具名函数（敌人）的地址")
        self.assertIn("0x21550", constants, "取证里必须留下基址链（Game → Room*）")


if __name__ == "__main__":
    unittest.main()
