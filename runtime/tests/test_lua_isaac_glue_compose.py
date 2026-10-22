"""门禁：`glue_compose` 桶的三条（批次 261，2026-10-01）。

## 这一桶的口径

清单把这几条判成"PC 在 Lua 胶水层实现"（Switch 二进制的符号表里既没有同名自由函数、
`Game`/`Manager` 里也没有同名成员）⇒ 正确做法是**照 PC 文档的语义**用我们已有的原语拼，
而不是去接一个不存在的引擎符号。

本批落地三条：

| API | 怎么拼的 | 契约 |
| --- | --- | --- |
| `Isaac:GetChallenge()` | 直读 `Game + 0x26FA88`（`eChallenge` 原值，int32） | `Isaac.md:171` |
| `Isaac:ConsoleOutput(text)` | 转调 `EmitLine`（= 运行时自己的输出通道，与 `Isaac.DebugString` 同一条） | `Isaac.md:42` |
| `Isaac:HasModData(modRef)` | 转调 `Mod:HasData`（判定只有一份：`ModPersistence::HasModData`） | `Isaac.md:491` |

## 本文件钉什么、不钉什么

钉**接线与参数闸门**：目录行 / 绑定行 / 契约页:行 / 三条的参数个数与降级口径，以及
**`Isaac` 是全局表、按 `.` 调用 ⇒ 栈上不含 `self`** 这条与 `Room`/`Game` 相反的口径
（那正是批次 249 栽过的地方，见 `test_lua_room_position_fallback.py`）。

★ **不钉值**：宿主没有引擎 ⇒ `Isaac.GetChallenge()` 只能验"降级成 0 且不报错"，
**证明不了真机上返回的就是那一局挑战的 id**（那要真机读数）。
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
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
MOD_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "mod_api.cpp"
GENERATOR = ROOT / "tools" / "build_api_restore_worklist.py"

#: `(名字, 域内序号, 契约页:行)`
APIS = (
    ("GetChallenge", 0x0088, "Isaac.md:171"),
    ("ConsoleOutput", 0x0089, "Isaac.md:42"),
    ("HasModData", 0x008A, "Isaac.md:491"),
    # 批次 268（2026-10-02）：`glue_compose` 桶最后两条。
    # ★ `CountEntities` 与上面三条不同：它**有**引擎侧的实现可转调
    #   （`EntityList::CountSpawned` @ `0x7A1CC`，PC 侧绑定函数 VA `0x80D0D0` 读满实参后
    #   就是一次成员调用）—— 放在本文件是因为**清单把它判进同一桶**，
    #   而"值"那一半在宿主上验不了（见文件头"不钉值"）。
    # ★ `RunCallbackWithParam` 的契约行**本身不完整**（只写了 `callbackId`）；
    #   完整签名 `(callbackId, param, ...)` 与语义取自同源文档的另一次抓取，
    #   逐字引用写在 `isaac_api.cpp` 的实现处注释里。
    ("CountEntities", 0x008E, "Isaac.md:72"),
    ("RunCallbackWithParam", 0x008F, "Isaac.md:584"),
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;

void PublishEmptyModule() {
    // ★ 假模块必须**盖住 `kGameOwnerGlobalSlotOffset`**（0xAAC698）：`Isaac.GetChallenge()`
    //   会先 `EngineModuleBase() + 那个偏移` 去取 `g_Game` 的槽。铺得太小 ⇒ 那是一次**越界读**
    //   ⇒ 宿主上偶发 SIGSEGV（第一次就是这么挂的：手动跑绿、在 unittest 里红）。
    //   槽里全 0 ⇒ `ResolveGameAddress()` 拿到 0 就返回，不会再解引用第二层。
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + 16, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_ModuleBytes.data()));
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
    PublishEmptyModule();
    LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "degrade") == 0) {
        script =
            "local ok, value = pcall(function() return Isaac.GetChallenge() end)"
            " print('GLUE challenge ok='..tostring(ok)..' value='..tostring(value))"
            " local printed, err = pcall(function() return Isaac.ConsoleOutput('hello') end)"
            " print('GLUE console ok='..tostring(printed)..' results='..tostring(err))";
    } else if (std::strcmp(scenario, "arity") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " print('GLUE arity='..ok(function() return Isaac.GetChallenge(1) end)"
            "   ..','..ok(function() return Isaac.ConsoleOutput() end)"
            "   ..','..ok(function() return Isaac.ConsoleOutput({}) end)"
            "   ..','..ok(function() return Isaac.HasModData() end)"
            "   ..','..ok(function() return Isaac.HasModData(42) end))";
    } else if (std::strcmp(scenario, "coercion") == 0) {
        // ★ 数字→字符串的强制转换是 `luaL_checklstring` 的行为，**与 PC 的绑定层一致**
        //   （PC 的 `ConsoleOutput` 同样收下数字、打出它的文本形式）⇒ 这一格钉住"别把它当错误"。
        script =
            "local ok, results = pcall(function() return Isaac.ConsoleOutput(42) end)"
            " print('GLUE coercion ok='..tostring(ok)..' results='..tostring(results))";
    } else if (std::strcmp(scenario, "count_entities") == 0) {
        // 宿主没有引擎（`ResolveRoom()` 拿到 0）⇒ 唯一能验的是**参数闸门与降级值**：
        // 合法形状一律给 0 且不报错（第 11 条纪律：读不到原生状态不许抛 Lua 错误），
        // 形状不对才报错（那是模组写错了，PC 上也会报）。
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " print('B268 count=' .. tostring(Isaac.CountEntities(nil))"
            "   .. ',' .. tostring(Isaac.CountEntities(nil, 37, -1, -1))"
            "   .. ',' .. tostring(Isaac.CountEntities(nil, 0, 0, 0)))"
            " print('B268 count_arity=' .. ok(function() return Isaac.CountEntities() end)"
            "   .. ',' .. ok(function() return Isaac.CountEntities(nil, 0, 0, 0, 0) end)"
            "   .. ',' .. ok(function() return Isaac.CountEntities(nil, 'x') end)"
            "   .. ',' .. ok(function() return Isaac.CountEntities(nil, 0, 0, {}) end))";
    } else if (std::strcmp(scenario, "run_callback_with_param") == 0) {
        // `param` 是**注册时的过滤值**、**不传给回调**。三条登记：无过滤值 / 过滤值 7 / 无过滤值；
        // 中间那条一命中就 `return 'first'`（契约："breaking on the first return"）。
        // ⇒ 期望：`param = 7` 时前两条被调、第三条**不**被调（提前中断）；
        //        `param = 9` 时只有第一条与第三条被调；`param = nil` 等于"不做过滤"（全匹配）。
        //
        // ★ 用 `table.pack` 抓**结果个数**与第一个结果，而**不是**写 `tostring(f(…))`：
        //   在 Lua 里"多值表达式处于实参表最后一位"时**不做补齐** ⇒ 一个返回 0 个结果的调用
        //   会让 `tostring` 收到 0 个实参、报 `bad argument #1 to 'tostring' (value expected)`。
        //   那个报错**看起来像我们的 bug**，实际是脚本写法问题（契约是 `void`：没有回调返回值时
        //   就该返回 0 个结果）。这里把个数也一并钉住。
        script =
            "local mod = RegisterMod('batch 268', 1)"
            " local NAME = 'BATCH268_NAMED'"
            " local log = {}"
            " mod:AddCallback(NAME, function(self, a, b)"
            "   log[#log + 1] = 'plain:' .. tostring(self == mod) .. ':' .. tostring(a) .. ':' .. tostring(b)"
            " end)"
            " mod:AddCallback(NAME, function(self, a, b)"
            "   log[#log + 1] = 'f7:' .. tostring(a) .. '/' .. tostring(b)"
            "   return 'first'"
            " end, 7)"
            " mod:AddCallback(NAME, function(self, a, b) log[#log + 1] = 'plain2' end)"
            " local function fire(param)"
            "   log = {}"
            "   local packed = table.pack(Isaac.RunCallbackWithParam(NAME, param, 'A', 'B'))"
            "   return tostring(packed.n) .. ':' .. tostring(packed[1])"
            " end"
            " print('B268 p7=' .. fire(7) .. '|' .. table.concat(log, ','))"
            " print('B268 p9=' .. fire(9) .. '|' .. table.concat(log, ','))"
            " print('B268 pnil=' .. fire(nil) .. '|' .. table.concat(log, ','))"
            " local function ok(f) return tostring(select(1, pcall(f))) end"
            " print('B268 gates=' .. ok(function() return Isaac.RunCallbackWithParam(21, nil) end)"
            "   .. ',' .. ok(function() return Isaac.RunCallbackWithParam(-1) end)"
            "   .. ',' .. ok(function() return Isaac.RunCallbackWithParam() end))"
            " log = {}"
            " local compat = table.pack(Isaac.RunCallback(NAME, 'X', 'Y'))"
            " print('B268 compat=' .. tostring(compat.n) .. ':' .. tostring(compat[1])"
            "   .. '|' .. table.concat(log, ','))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@glue.lua");
    static_cast<void>(result);
    return 0;
}
'''


class IsaacGlueComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-glue-")
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

    def test_challenge_degrades_to_zero_and_console_output_never_errors(self):
        """拿不到 `Game` ⇒ `GetChallenge()` 压 `0`（= 契约里"没在挑战局"那个值）且不报错。

        `ConsoleOutput` 走 Lua 的 `print`，**没有返回值**（PC 契约是 `void`）⇒ `pcall` 的第二
        个返回值是 `nil`（不是 0 —— 0 意味着"返回了一个整数 0"）。文本本身会出现在输出里。
        """
        out = self.run_scenario("degrade")
        self.assertIn("GLUE challenge ok=true value=0", out)
        self.assertIn("GLUE console ok=true results=nil", out)
        self.assertIn("hello", out)

    def test_argument_gates(self):
        """参数个数/类型不对必须报错（模组写错了就该报错，而不是静默降级）。

        五格分别代表：不收参数的给了参数 / 收字符串的没给 / 收字符串的给了**表** /
        收 Mod 对象的没给 / 收 Mod 对象的给了数字。
        """
        out = self.run_scenario("arity")
        self.assertIn("GLUE arity=false,false,false,false,false", out)

    def test_number_coercion_matches_the_lua_string_convention(self):
        """数字会被当成字符串收下（`luaL_checklstring` 的强制转换）—— **不要**把它写成错误。

        理由：PC 的绑定层同样走 `luaL_checkstring` 一族，模组传数字时 PC 也会把它的文本形式
        打进控制台。我们单方面严格化反而会与 PC 不一致（那正是作业单里「判据 = 与 PC 一致」要防的）。
        """
        out = self.run_scenario("coercion")
        self.assertIn("GLUE coercion ok=true results=nil", out)
        self.assertIn("42", out)

    # ------------------------------------------- 批次 268（`glue_compose` 桶最后两条）

    def test_count_entities_degrades_to_zero_and_gates_its_arguments(self):
        """宿主无引擎 ⇒ 只钉两件事：合法形状给 `0` 且不报错；形状不对报错。

        ★ 为什么"给 0"是对的：这一条被模组写在回调体里，报错会把**整条回调摘掉**；
        而 `0` 的后果只是"数不到实体"（模组写的是 `> 0` / `< 35` 这类比较）。
        ★ 为什么"零参"也在报错那一侧：PC 的签名里 `Spawner` **没有缺省值**
        （缺省的是后面三个），所以 `CountEntities()` 在 PC 上同样是错的。
        """
        out = self.run_scenario("count_entities")
        self.assertIn("B268 count=0,0,0", out)
        self.assertIn("B268 count_arity=false,false,false,false", out)

    def test_run_callback_with_param_filters_and_breaks_on_the_first_return(self):
        """`param` 是**注册时的过滤值**、不传给回调；命中第一条有返回值的就中断。

        三条登记依次是：无过滤值（返回 nil）/ 过滤值 7（返回 `'first'`）/ 无过滤值；
        配合 `param = 7 / 9 / nil` 三种调用，一次把规约的三条都钉住：
        ① 任一侧没有过滤值 ⇒ 匹配；② 过滤值不等 ⇒ 跳过；③ 第一个非 nil 返回值 ⇒ 中断。
        ★ 同时验"过滤值不会变成回调的第一个额外实参"：回调签名是 `(self, a, b)`，
        收到的必须是 `'A','B'` —— 若把 `param` 也透传下去，第二个形参会收到数字、第三个收到 `'A'`。
        ★ 期望里的 `1:` / `0:` 前缀是**结果个数**（`table.pack(...).n`）：没有回调返回值时
        契约是 `void` ⇒ 返回 0 个结果，而不是"返回一个 nil"。
        """
        out = self.run_scenario("run_callback_with_param")
        self.assertIn("B268 p7=1:first|plain:true:A:B,f7:A/B", out)
        self.assertIn("B268 p9=0:nil|plain:true:A:B,plain2", out)
        self.assertIn("B268 pnil=1:first|plain:true:A:B,f7:A/B", out)
        self.assertIn("B268 gates=true,false,false", out)
        self.assertIn("B268 compat=1:first|plain:true:X:Y,f7:X/Y", out)

    def test_run_callback_with_param_reuses_the_single_named_callback_registry(self):
        """★ 不另写一份注册表：它必须走 `mod_api.cpp` 那套命名回调设施。

        判据 = 同一个字符串名下、同一次会话里 `Isaac.RunCallback` 与
        `Isaac.RunCallbackWithParam` 看到的是**同一张表**（上面 `compat` 那一格就是它：
        登记一次，两条派发都命中）。实现上靠 `RunNamedCallbacksWithFilter`
        （无过滤值的那条 `Isaac.RunCallback` 走同一条函数、只是过滤值传 0）。
        """
        mod = MOD_API.read_text(encoding="utf-8")
        self.assertIn(
            "int RunNamedCallbacks(lua_State* state, const char* name, int firstArgument) {\n"
            "    return RunNamedCallbacksWithFilter(state, name, 0, firstArgument);\n}",
            mod, "`Isaac.RunCallback` 必须转调带过滤值的那一份（不写第二份派发循环）")
        self.assertIn('lua_getfield(state, entryIndex, "OptionalArg")', mod,
                      "命名回调的过滤值字段名要与 PC 回调表一致（OptionalArg）")

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_rows_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        for name, index, _page in APIS:
            with self.subTest(name):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "Isaac", "{name}"',
                    catalog, f"catalog 里没有 Isaac:{name}（域内序号 0x{index:04x}）")
                self.assertRegex(
                    isaac, rf"\{{\s*(?i:0x{0x0E010000 + index:08x}),\s*&\w*{name}\s*\}}",
                    f"Isaac 绑定表里没有 0x{0x0E010000 + index:08X} → {name}")

    def test_contract_page_and_line_are_quoted_in_the_implementation(self):
        combined = (ISAAC_API.read_text(encoding="utf-8")
                    + (ROOT / "runtime" / "src" / "interfaces" / "lua" / "mod_api.hpp").read_text(
                        encoding="utf-8"))
        for name, _index, page in APIS:
            with self.subTest(name):
                self.assertIn(page, combined, f"{name} 的实现处没有引用契约 {page}")

    def test_isaac_members_are_called_with_a_dot_so_self_is_not_on_the_stack(self):
        """★ 口径：`Isaac` 是**全局表**，模组写 `Isaac.GetChallenge()`（`.`）⇒ 栈上**不含 `self`**。

        与 `Room`/`Game` 的方法调用（`room:GetCenterPos()` ⇒ 含 `self`）**相反**。
        这两套口径在同一个仓库里并存，混了就是"要么永远多算一个参数、要么永远少算一个"
        —— 批次 249 正是栽在这一格（见 `test_lua_room_position_fallback.py` 的 `convention` 场景）。
        """
        isaac = ISAAC_API.read_text(encoding="utf-8")
        # `.` 调用 ⇒ 0 参方法要求 `lua_gettop == 0`、1 参方法要求 `== 1`。
        self.assertIn('if (lua_gettop(state) != 0) {\n        return luaL_error(state, '
                      '"Isaac.GetChallenge accepts no arguments");', isaac)
        self.assertIn('if (lua_gettop(state) != 1) {\n        return luaL_error(state, '
                      '"Isaac.ConsoleOutput expects a string");', isaac)

    def test_has_mod_data_reuses_the_single_persistence_judgement(self):
        """★ `Isaac.HasModData` 必须与 `Mod:HasData` **共用同一份判定**，不许另写一份。

        作业单第三节第 7 条：判定只能有一份（`ModPersistence::HasModData`）。
        所以它在 `mod_api.cpp` 里是**转调**，而不是自己再查一遍磁盘。
        """
        mod = MOD_API.read_text(encoding="utf-8")
        self.assertIn("int IsaacHasModData(lua_State* state) {\n    return ModHasData(state);\n}",
                      mod, "Isaac.HasModData 必须是 ModHasData 的转调（不写第二份判定）")

    def test_worklist_generator_keeps_the_confirmed_pseudo_gaps_out(self):
        """G1 结案名单：`Vector:__sub` 与 `GridEntityDoor:IsOpen` 确认"早就能用"，已从清单划掉。

        ★ 为什么把它们钉在这里：这两条以前一直躺在待办清单里（缺口报告只读 catalog，
        看不见元表字段与 `__index` 名字分派这两类实现）⇒ 不做这一格，下一个接手的人会
        重新查一遍、甚至给 `Vector` 再加一个重复的减法实现。
        """
        generator = GENERATOR.read_text(encoding="utf-8")
        self.assertIn("CONFIRMED_PSEUDO_GAPS", generator)
        for api in ('"Vector:__sub"', '"GridEntityDoor:IsOpen"'):
            with self.subTest(api):
                self.assertIn(api, generator, f"结案名单里没有 {api}")
        self.assertIn("METATABLE_FIELD", generator,
                      "生成器必须扫元表字段（否则 Vector:__sub 这类伪缺口又会回到清单里）")


if __name__ == "__main__":
    unittest.main()
