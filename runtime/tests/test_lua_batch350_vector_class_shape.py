"""门禁：`getmetatable(Vector).__class` = 实例用的那个元表（批次 350，2026-10-04）。

## 这一批是什么

真机读数（`dist/gdb-report-20261004-185047.txt`）里，minimapi 的 Lua 错误是：

```
rom:/isaac_mods/mods/minimapi/scripts/minimapapi/main.lua:1211:
    bad argument #1 to 'GetRoomAtPosition', expected Vector
```

★ 这条错**不是我们运行时报的**，是 minimapi **自己的 `assert`** 抛的
（`MinimapAPI/main.lua:1210-1211`）：

```lua
function MinimapAPI:GetRoomAtPosition(position)
    assert(MinimapAPI:InstanceOf(position, Vector), "bad argument #1 ... expected Vector")
```

而 `InstanceOf`（`main.lua:629-638`）是这么判的：

```lua
local meta      = getmetatable(obj)
local metaclass = getmetatable(class)
if metaclass then return metaclass.__class == meta else return false end
```

我们的 `Vector` 全局有元表（`__call` / `__index`），**但那个元表上没有 `__class`**
⇒ `metaclass.__class` 是 `nil`、`meta` 是 `kVectorMetatable` ⇒ 恒 false。

批次 284 给 `Level` 补过**同一条 PC 形状**；本批给 `Vector` 补上。
（全语料里 `InstanceOf` 只在 minimapi 里出现，且它**只检查 `Vector`** ——
`main.lua:1181` 的 `RemoveRoom` 与 `:1211` 的 `GetRoomAtPosition` 两条 assert。）

## 判据（宿主 · 真 Lua）

1. `getmetatable(Vector).__class == getmetatable(Vector(1,2))`；
2. ★ **照 minimapi 的 `InstanceOf` 原样跑一遍**：`InstanceOf(v, Vector)` ⇒ `true`、
   `InstanceOf(1, Vector)` ⇒ `false`（后者证明它不是"恒 true"的假实现）。
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

HARNESS = r'''
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main() {
    g_ModuleBytes.assign(0x40000, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_ModuleBytes.data()));
    LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()), 0x2222);

    const char* script =
        "local v = Vector(1, 2)"
        " local meta = getmetatable(v)"
        " local metaclass = getmetatable(Vector)"
        " print('B350 metatype=' .. type(metaclass))"
        " print('B350 same=' .. tostring(metaclass ~= nil and metaclass.__class == meta))"
        // ★★ 照 minimapi `main.lua:629-638` 的 InstanceOf 原样跑一遍：
        " local function InstanceOf(obj, class)"
        "     local m = getmetatable(obj)"
        "     local mc = getmetatable(class)"
        "     if mc then return mc.__class == m else return false end"
        " end"
        " print('B350 instanceof=' .. tostring(InstanceOf(v, Vector)))"
        // 负例：不是 Vector 的值必须答 false（挡住"恒 true"的假实现）。
        " print('B350 notinstance=' .. tostring(InstanceOf(1, Vector)))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b350.lua");
    static_cast<void>(result);
    return 0;
}
'''


class Batch350VectorClassShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b350-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_harness(self):
        result = subprocess.run([str(self.binary)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_vector_class_metatable_exposes_class(self):
        """★ 本批核心：`getmetatable(Vector).__class` 就是实例用的那个元表。"""
        out = self.run_harness()
        self.assertIn("B350 metatype=table", out)
        self.assertIn("B350 same=true", out)

    def test_minimapi_instanceof_idiom_works_both_ways(self):
        """★★ 复刻 minimapi 的 `InstanceOf`：真的 Vector 答 true、别的值答 false。

        修之前（`__class` 缺失）两条都是 false ⇒ 真机上 minimapi 那条 `assert` 直接抛
        `bad argument #1 to 'GetRoomAtPosition', expected Vector`、整条回调被打断。
        """
        out = self.run_harness()
        self.assertIn("B350 instanceof=true", out)
        self.assertIn("B350 notinstance=false", out)
