"""门禁：`RoomDescriptorList` 的 `__len` —— `#rooms`（批次 349，2026-10-04）。

## 这一批是什么

真机读数（`dist/gdb-report-20261004-183801.txt`）里，minimapi 的 Lua 错误是：

```
rom:/isaac_mods/mods/minimapi/scripts/minimapapi/main.lua:840:
    attempt to get length of a IsaacRuntime.RoomDescriptorList value (local 'rooms')
```

另有一条同形的 `main.lua:680`。那几行是：

```lua
local rooms = level:GetRooms()
for i = 0, #rooms - 1 do ... end          -- :680 / :840
MinimapAPI.CheckedRoomCount = #rooms      -- :734 / :886
```

⇒ 模组对**列表**用了 Lua 的长度运算符 `#`，而我们的 `RoomDescriptorList` 元表**只有 `__index`
（`Size`/`Get`），没有 `__len`** ⇒ 一取长度就报错、整条回调被打断。PC 的 `RoomDescriptorList`
是个列表、支持 `#` ⇒ 补 `__len` 才是"与 PC 一致"。

`__len` 与 `.Size` **同一个来源**（`DescriptorCount`，每次现读、不缓存）⇒ 两者永远一致。

## 判据（宿主 · 真 Lua）

1. `#rooms` 不报错，且 **等于 `.Size`**；
2. 三种描述符个数（0 / 3 / 7）**互不相同** ⇒ 证明 `__len` 读的是**活值**，不是写死的常量
   （"写死一个数"或"忘了现读"都会让至少一场红）。

★ 夹具照 `test_lua_room_descriptor.py`：`Level + 0x21510` 是描述符个数，
解析链是"模块 + `kGameOwnerGlobalSlotOffset` → 槽 → owner → Game(=Level)"（真机同形，两层）。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parent.parent / "source"

#: `(场景, `Level + 0x21510` 的初值)`
CASES = (("zero", 0), ("three", 3), ("seven", 7))

HARNESS = r'''
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerBytes;
std::vector<unsigned char> g_GamePointerBytes;
std::vector<unsigned char> g_LevelBytes;
std::uint32_t g_DescriptorCount = 3;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

// 批次 349 只需要 `Level + 0x21510`（描述符个数）这一格是真的；其余照
// `test_lua_room_descriptor.py` 铺成真机的两层链：槽 → owner → Game(=Level)。
void PublishFakeEngine() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerBytes.assign(sizeof(std::uint64_t), 0);
    g_GamePointerBytes.assign(sizeof(std::uint64_t), 0);
    g_LevelBytes.assign(0x21520, 0);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_GamePointerBytes));
    WriteAt<std::uint64_t>(g_OwnerBytes, 0, AddressOf(g_GamePointerBytes));
    WriteAt<std::uint64_t>(g_GamePointerBytes, 0, AddressOf(g_LevelBytes));
    WriteAt<std::uint32_t>(g_LevelBytes, 0x21510, g_DescriptorCount);
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "zero") == 0) { g_DescriptorCount = 0; }
    else if (std::strcmp(scenario, "three") == 0) { g_DescriptorCount = 3; }
    else if (std::strcmp(scenario, "seven") == 0) { g_DescriptorCount = 7; }
    else { return 91; }

    PublishFakeEngine();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerBytes), 0x2222);

    const char* script =
        "local rooms = Game():GetLevel():GetRooms()"
        " print('B349 kind=' .. type(rooms))"
        " local ok, err = pcall(function() return #rooms end)"
        " print('B349 ok=' .. tostring(ok))"
        " print('B349 err=' .. tostring(err))"
        " print('B349 len=' .. tostring(#rooms))"
        " print('B349 size=' .. tostring(rooms.Size))"
        " print('B349 eq=' .. tostring((#rooms) == rooms.Size))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b349.lua");
    static_cast<void>(result);
    return 0;
}
'''


class Batch349RoomDescriptorListLenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b349-")
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

    def test_length_operator_works_and_matches_size(self):
        """★★ **本批核心**：`#rooms` 不报错，且等于 `.Size` —— 三种个数都成立。

        修之前 `#rooms` 直接报 "attempt to get length of a IsaacRuntime.RoomDescriptorList
        value"，整条回调被打断（真机症状）。
        """
        for scenario, count in CASES:
            with self.subTest(scenario=scenario):
                out = self.run_scenario(scenario)
                self.assertIn("B349 kind=userdata", out)
                self.assertIn("B349 ok=true", out)
                self.assertNotIn("attempt to get length", out)
                self.assertIn(f"B349 len={count}", out)
                self.assertIn(f"B349 size={count}", out)
                self.assertIn("B349 eq=true", out)

    def test_length_is_read_live_not_baked_in(self):
        """★ `__len` 必须**每次现读**（与 `.Size` 同源），不能写死一个常量。

        三种场景的期望值互不相同（0 / 3 / 7）⇒ "写死常量"会让至少两场红。
        """
        observed = set()
        for scenario, _count in CASES:
            out = self.run_scenario(scenario)
            for line in out.splitlines():
                if line.startswith("B349 len="):
                    observed.add(line.split("=", 1)[1])
        self.assertEqual(observed, {"0", "3", "7"}, f"实测取值：{sorted(observed)}")
