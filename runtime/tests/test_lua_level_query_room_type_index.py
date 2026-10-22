"""门禁：`Level:QueryRoomTypeIndex`（批次 270，2026-10-02）。

## 这条为什么曾被判成 `needs_new_shape`

工作单的分桶工具把它判进 `needs_new_shape`，理由是"第 3 个参数是 `RNG&`，数据行机制只认标量"。
**但那只是数据行的限制**：手写处理器本来就什么形状都能写（同批的 `Isaac:CountEntities` 也是
4 个实参 + 一个裸指针），所以本批**手写、且不动 `EngineCallShape` 表** —— 加形状要"三处同步"
（表尾 + 枚举 + `engine_offset_abi_report.py`），能不动就不动。

★ 而 `RNG&` 这一格根本不是难题：Lua 侧的 `RNG` 句柄（`LuaRuntime::RngHandle`）**就是**
16 字节的引擎 `RNG` 对象裸存储（`std::array<u8, kRngObjectSize>`），`RNG:SetSeed`/`Next`/
`RandomInt`/`RandomFloat` 全部把 `storage.data()` 当 `this` 交给引擎方法
（`rng_api.cpp:78/94/158/174`）⇒ 把它的地址当 `RNG&` 传出去是**同一件东西**，不是替身。
本文件里 `test_the_rng_handle_is_the_engine_rng_object` 就是钉这一条的静态判据。

## 本文件钉什么、不钉什么

钉**接线、参数闸门与降级值**；★ **不钉值** —— 宿主没有引擎，`-1` 只证明"读不到时给的是引擎
自己的『没有这种房间』表示法"，证明不了真机上算出来的那个房间下标（那要真机读数，见作业单第九节）。
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
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
RNG_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "rng_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::uint64_t g_RoomStorage = 0;

void PublishEmptyModule() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + 64, 0);
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_ModuleBytes.data()));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = &g_RoomStorage;
    return GameRoomObservation::Success;
}

GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t* stage) {
    if (stage == nullptr) return GameLevelStageObservation::GameUnreadable;
    *stage = 1;
    return GameLevelStageObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    PublishEmptyModule();
    LuaRuntime::SetGameBindings(0x1111, 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "query") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local level = Game():GetLevel()"
            " print('B270 level=' .. type(level))"
            " local rng = RNG()"
            " print('B270 fallback=' .. tostring(level:QueryRoomTypeIndex(2, false, rng)))"
            " print('B270 default_arg='"
            "   .. tostring(level:QueryRoomTypeIndex(2, true, rng, false)))"
            " print('B270 gates=' .. ok(function()"
            "     return level:QueryRoomTypeIndex(2, false) end)"
            "   .. ',' .. ok(function() return level:QueryRoomTypeIndex(2, false, rng, false, 1) end)"
            "   .. ',' .. ok(function() return level:QueryRoomTypeIndex(2, false, 5) end)"
            "   .. ',' .. ok(function() return level:QueryRoomTypeIndex('x', false, rng) end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b270.lua");
    static_cast<void>(result);
    return 0;
}
'''


class LevelQueryRoomTypeIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b270-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> str:
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    # ---------------------------------------------------------------- 宿主行为

    def test_falls_back_to_minus_one(self):
        """宿主没有引擎 ⇒ `-1` 且**不报错**。

        `-1` 是**引擎自己**对"没有这种房间"的取值（`runtime_constants.hpp` 的批次 270 段里
        记着 `mov w19, #-0x1` @ `0x3E6094`）⇒ 与 PC 的"找不到"同形。**不能给 0**：
        模组会把 0 当成"第 0 号房间"。
        """
        out = self.run_scenario("query")
        self.assertIn("B270 level=userdata", out)
        self.assertIn("B270 fallback=-1", out)

    def test_optional_ignore_group_defaults_to_false(self):
        """`IgnoreGroup` 是**可省尾参**（PC 缺省 `false`）⇒ 4 个实参（含 `self`）必须能调。

        ★ 这条是"少给参数会被当成参数个数不符而报错"那一类缺陷的钉子：本题材的老坑
        （批次 249）就是"参数个数算错 ⇒ 模组每一次调用都抛错 ⇒ 整条回调被摘掉"。
        """
        out = self.run_scenario("query")
        self.assertIn("B270 default_arg=-1", out)

    def test_argument_gates(self):
        """四个闸门：缺 RNG / 多给一个参数 / 第 3 个不是 RNG / RoomType 不是整数 —— 全部报错。

        前三条是**形状**（模组写错了，PC 上也会报）；第四条同样：契约里 `RoomType` 是
        `eRoomType` 枚举，传字符串在 PC 上也是 `luaL_checkinteger` 失败。
        """
        out = self.run_scenario("query")
        self.assertIn("B270 gates=false,false,false,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = REMAINING_API.read_text(encoding="utf-8")
        self.assertIn('MakeId(ApiDomain::Level, 1, 0x0018), ApiDomain::Level, "Level", '
                      '"QueryRoomTypeIndex"', catalog)
        self.assertRegex(body, r"\{\s*0x03010018,\s*&\w*QueryRoomTypeIndex\s*\}")

    def test_contract_page_is_quoted_in_the_implementation(self):
        self.assertIn("Level.md:328", REMAINING_API.read_text(encoding="utf-8"))

    def test_the_rng_handle_is_the_engine_rng_object(self):
        """★ 静态判据：`RNG` 句柄传给引擎方法时用的**就是** `storage.data()`。

        这是"把句柄地址当 `RNG&` 交出去"成立的前提 —— 不是替身、不需要布局映射。
        做法：`RNG:SetSeed` / `RNG:Next` 的调用点都必须是 `…(rng->storage.data(), …)`。
        `rng_api.cpp` 里已有一条 `static_assert(sizeof(RngHandle::storage) == kRngObjectSize)`
        把"它有多大"钉在编译期，这一格把"它就是那个对象"钉住。
        """
        rng = RNG_API.read_text(encoding="utf-8")
        self.assertIn("static_assert(sizeof(LuaRuntime::RngHandle::storage) == kRngObjectSize", rng)
        self.assertEqual(rng.count("ResolveRngObject(state, rng,"), 5,
                         "每个 RNG 引擎调用点都必须把句柄的裸存储当地址交出去"
                         "（少一处说明有人加了第二种表示法）")

    def test_engine_offset_and_sixteen_byte_guard_are_recorded(self):
        """偏移与 16 字节入口原文都要在 `runtime_constants.hpp` 里（`G4` 的取证要求）。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("kLevelQueryRoomTypeIndexOffset = 0x3E605C", constants)
        # ★ 本批真栽过一次：入口 16 字节我手抄成了 `FD00C391`，而镜像是 `FDC30091` ——
        # `test_runtime_constants` 当场红。这一格把**逐字节**再说一遍，免得后来者只看偏移。
        self.assertIn("0xFF, 0x43, 0x02, 0xD1, 0xFD, 0x7B, 0x03, 0xA9,", constants)
        self.assertIn("kLevelQueryRoomTypeIndexExpectedBytes", constants)


if __name__ == "__main__":
    unittest.main()

# 2026-10-09更正：5种RNG操作统一走引用resolver，RNG()在该resolver内用自身storage。
