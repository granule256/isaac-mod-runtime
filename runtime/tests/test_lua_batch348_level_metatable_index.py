"""门禁：`Level` 元表的 `__index` **必须是函数**（批次 348，2026-10-04）。

## 这一批是什么

真机读数（`dist/gdb-report-20261004-181018.txt`）里，minimapi 的 Lua 错误是：

```
minimapi/scripts/minimapapi/apioverride.lua:25:
    attempt to call a table value (upvalue 'oldIndex')
```

`apioverride.lua:22-26` 这么写：

```lua
local oldIndex = class_mt.__index
rawset(class_mt, "__index", function(self, k)
    return classDat.New[k] or oldIndex(self, k)      -- ← 第 25 行
end)
```

它把 `getmetatable(Level).__class.__index` 取出来**当函数调用**。批次 284 把那个 `__index`
设成了"元表自己"（一张**表**）⇒ 一调就炸；而且 minimapi 那一下 `rawset` 装完之后，
**Level 实例的每一次属性查找**都走那条会报错的包装 ⇒ 同一条派发链上后面的模组跟着断
（GoodTrip 的画地图就在其中，真机症状 = "小地图没了"）。

PC 的类元表 `__index` 是**函数** —— 本仓 `Game`（`GameIndex`）/`RoomDescriptor`/`GridEntity`
族全都是函数。批次 348 起 `Level` 也是函数（`LevelIndex`，上值 1 = 类元表；
语义与表 `__index` **等价**：Lua 对表 `__index` 做的就是 `rawget`）。

## 判据（**在真 Lua 里验**，不是查源码文本）

1. `type(getmetatable(Level).__class.__index) == "function"` —— 本批的**核心**；
2. **照 minimapi 的写法调它**（`oldIndex(self, k)`）**不报错**，且能取到真方法；
3. 表 `__index` 的语义不变：认不出的键答 `nil`（不能为了"可调用"把语义改坏）；
4. `__class`（= 元表自己）与 `__type`（`"Level"`）两处形状还在 —— 批次 284 立的那两条
   不能被本批改坏。
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
LUA_RUNTIME = SOURCE / "lua_runtime.cpp"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 与批次 341 的用例同一副骨架：一个**全零**的假模块块当引擎基址
// （`LevelIndex` 只对类元表做 `rawget`，**不碰引擎内存** —— 给基址只是为了让注册那条路
//  不因为"没有引擎"而提前退场）。
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
        "local cls = getmetatable(Level).__class"
        // 1) 核心：必须是函数（批次 284 是一张表 ⇒ 真机报 "attempt to call a table value"）。
        " print('B348 cls=' .. type(cls))"
        " print('B348 idxkind=' .. type(cls.__index))"
        // 2) 真方法经它取得到（表 __index 的语义：对类元表 rawget）。
        " print('B348 getcurses=' .. type(cls.__index(nil, 'GetCurses')))"
        " print('B348 planetarium=' .. type(cls.__index(nil, 'GetPlanetariumChance')))"
        // 3) 认不出的键仍然答 nil（语义不能被改坏）。
        " print('B348 missing=' .. tostring(cls.__index(nil, 'DefinitelyNotAMethod')))"
        // 4) 284 立的另外两处形状还在。
        " print('B348 classself=' .. tostring(cls.__class == cls))"
        " print('B348 metatype=' .. tostring(cls.__type))"
        // 5) ★★ **照 minimapi 的 apioverride.lua:22-26 原样走一遍** —— 这一段就是真机的崩点。
        " local oldIndex = cls.__index"
        " local ra, rb = pcall(function()"
        "     rawset(cls, '__index', function(self, k) return nil or oldIndex(self, k) end)"
        "     return cls.__index(nil, 'GetCurses')"
        " end)"
        " print('B348 mminapi=' .. tostring(ra) .. '/' .. type(rb))"
        " print('B348 mminapierr=' .. tostring(rb))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b348.lua");
    static_cast<void>(result);
    return 0;
}
'''


class Batch348LevelIndexFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b348-")
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

    def test_level_class_table_exists_with_class_and_type(self):
        """批次 284 立的形状：`getmetatable(Level).__class` 就是实例用的那个元表，且带 `__type`。"""
        out = self.run_harness()
        self.assertIn("B348 cls=table", out)
        self.assertIn("B348 classself=true", out)
        self.assertIn("B348 metatype=Level", out)

    def test_index_is_a_function_not_a_table(self):
        """★★ **本批的核心判据**：`__index` 得是函数。

        批次 284 把它设成"元表自己"那张表 ⇒ `minimapi/apioverride.lua:25` 的
        `oldIndex(self, k)` 报 `attempt to call a table value`。查出 `table` 就是回到那个 bug。
        """
        out = self.run_harness()
        self.assertIn("B348 idxkind=function", out)
        self.assertNotIn("B348 idxkind=table", out)

    def test_index_keeps_table_lookup_semantics(self):
        """语义不能被"改坏"：真方法取得到、认不出的键答 `nil`（与表 `__index` 等价）。"""
        out = self.run_harness()
        self.assertIn("B348 getcurses=function", out)
        self.assertIn("B348 planetarium=function", out)
        self.assertIn("B348 missing=nil", out)

    def test_minimapi_override_idiom_no_longer_raises(self):
        """★★★ **真机崩点的复刻**：`oldIndex(self, k)` 那条路必须不报错。

        这一段与 `analysis/mod-corpus/MinimapAPI/scripts/minimapapi/apioverride.lua:22-26`
        逐字同形。它就是读数里那句错误的来源 ⇒ 这里红了就说明真机上还会报。
        """
        out = self.run_harness()
        self.assertIn("B348 mminapi=true/function", out)
        self.assertNotIn("attempt to call a table value", out)
