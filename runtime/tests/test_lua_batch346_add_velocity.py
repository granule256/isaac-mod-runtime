"""门禁：批次 346（2026-10-04）—— `Entity:AddVelocity(Vector[, boolean IgnoreTimeScale])`（20 处）。

## 这一批是什么

| API | 处数 | 机制 | Switch 落点 |
| --- | --- | --- | --- |
| `Entity:AddVelocity(Velocity[, IgnoreTimeScale])` | **20** | **手写纯算法**（Switch 侧**没有可调真身**） | 直接读写 `Entity` 三格：速度 `+0x334/+0x338`、摩擦 `+0x340`、时间缩放 `+0x370`（本批新增常量） |

依据 = `docs/取证-M组-AddVelocity可执行规格-20261004d.md`（上游 = E 组，独立复核 = O 组
「算式逐条正确」）。★ 语料处数：清单按方法名聚合记 **15**，O 组 `grep` 实测 **20**（做计划按 20）。

## ★★ 本条**推翻**了一条旧负结果

批次 331 曾记「`Entity:AddVelocity` 两侧摩擦模型不同 ⇒ 不能做」。复核证明是**同一族**：
PC 绑定本体 `0x422B60` 的算式与 Switch 侧三格一一对应，按 PC 算式复刻即与 PC 一致。

## 本批的判据（宿主里**能验真值**：摆好 → 调 API → 读回来比）

纯算法 ⇒ 不像"引擎方法行"那样只能验接线。**五组互不相同**的
`(初速度, 实参, 摩擦, 时间缩放, IgnoreTimeScale) → 期望速度`：

| 场景 | 初速度 | 实参 | 摩擦 | 时间缩放 | flag | 期望 | 抓什么错法 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a | `(0,0)` | `(3,4)` | 2.0 | 1.0 | 缺省 | `(1.5, 2.0)` | 覆盖写 / 写错格 / 次序错 |
| b | `(1,-2)` | `(1,1)` | 0.5 | 1.0 | 缺省 | `(3.0, 0.0)` | 「加法 vs 乘法」/「除实参而非摩擦」 |
| c | `(0.5,0.5)` | `(2,2)` | 1.0 | 0.5 | 缺省 | `(1.5, 1.5)` | 漏了 `k` 的时间缩放支 |
| d | `(0.5,0.5)` | `(2,2)` | 1.0 | 0.5 | **true** | `(2.5, 2.5)` | `IgnoreTimeScale=true` 时**误读** ts |
| e | `(7,8)` | `(1,1)` | **0.0** | 1.0 | 缺省 | `(7,8)`（**不变**） | 漏了 `friction == 0` 零守卫 ⇒ 变 `inf` |

★ **零守卫只挡精确 `0.0f`**（MSVC 的 `ucomiss/test ah,0x44/jnp` 逐位推演），NaN 会**穿过**；
C++ 的 `friction == 0.0F` 对 NaN 同样为 false ⇒ 逐位一致 ⇒ **不额外加 NaN 特判**。

## 没验到的（真机项）

1. ★ **`+0x340`（本帧工作摩擦）在回调时点读到的是不是"本帧积分值"**：它是瞬态格
   （`Entity::Update` 帧末把 `+0x33C` 复位进 `+0x340`）⇒ 在 AI 回调里读到的可能是上一帧残留。
2. **`ts ≠ 1` 时与 PC 是否同结果**：PC 把 `ts` 乘进被加量，Switch 侧摩擦模型把 `ts` 放进倍率
   ⇒ 两侧只有在 `ts == 1` 时精确互逆，**不可代数互推**。
3. **引擎真的把它推动了**（位移是引擎积分的结果，宿主只验"内存被按 PC 算式改了"）。
4. **`EntityPickup`/`EntityFamiliar`/… 视图句柄调它被拒**：`EntityReceiverOrError` 只认 5 种元表，
   而 PC 允许对任意实体调 ⇒ 语料 20 处的接收者都在那 5 种内，本批**不改共享助手**，
   把这条记成已知偏差 + 真机项。
5. ★ **`+0x370` 的绝对语义**：H 组已离线定案（时间缩放、常态 `1.0f`，六条证据）⇒ 降级为可选复核。
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
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
SURFACE = ROOT / "runtime" / "tests" / "contract" / "test_engine_row_api_surface.py"
GAP_REPORT_TEST = ROOT / "runtime" / "tests" / "test_mod_api_gap_report.py"
CONTRACT_PAGE = ROOT / "tools" / "pc_contract_docs" / "Entity.md"

#: `(场景, 初速度 x, 初速度 y, 实参 x, 实参 y, 摩擦, 时间缩放, 期望 x, 期望 y)`
#: —— ★ 五组的期望**互不相同**，各自堵一种错法（见文件头那张表）。
CASES = (
    ("a", 0.0, 0.0, 3.0, 4.0, 2.0, 1.0, 1.5, 2.0),
    ("b", 1.0, -2.0, 1.0, 1.0, 0.5, 1.0, 3.0, 0.0),
    ("c", 0.5, 0.5, 2.0, 2.0, 1.0, 0.5, 1.5, 1.5),
    ("d", 0.5, 0.5, 2.0, 2.0, 1.0, 0.5, 2.5, 2.5),
    ("e", 7.0, 8.0, 1.0, 1.0, 0.0, 1.0, 7.0, 8.0),
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 333/341 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Game*
//   Game + 玩家数组 begin/end                 = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset / Type = PLAYER
//
// ★★ 本批**不调引擎**（纯算法）⇒ 引擎偏移根本用不到、模块块只要盖住 owner 槽；
//    真正的判据是"玩家块的三个格（速度/摩擦/时间缩放）被按 PC 算式改了" ⇒ **宿主里可验真值**。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void WriteVelocity(float x, float y) {
    std::memcpy(g_PlayerBytes.data() + kEntityVelocityOffset, &x, sizeof(x));
    std::memcpy(g_PlayerBytes.data() + kEntityVelocityOffset + sizeof(float), &y, sizeof(y));
}

void ReadVelocity(float* x, float* y) {
    std::memcpy(x, g_PlayerBytes.data() + kEntityVelocityOffset, sizeof(float));
    std::memcpy(y, g_PlayerBytes.data() + kEntityVelocityOffset + sizeof(float), sizeof(float));
}

void WriteFriction(float value) {
    std::memcpy(g_PlayerBytes.data() + kEntityFrictionOffset, &value, sizeof(value));
}

float ReadFriction() {
    float value = 0.0F;
    std::memcpy(&value, g_PlayerBytes.data() + kEntityFrictionOffset, sizeof(value));
    return value;
}

void WriteTimeScale(float value) {
    std::memcpy(g_PlayerBytes.data() + kEntityTimeScaleOffset, &value, sizeof(value));
}

float ReadTimeScale() {
    float value = 0.0F;
    std::memcpy(&value, g_PlayerBytes.data() + kEntityTimeScaleOffset, sizeof(value));
    return value;
}

void PublishFakeGame() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t) + 8, 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    static_assert(kEntityTimeScaleOffset + sizeof(float) <= kEntityPlayerSize,
                  "the fake player block must cover the time-value cell");
    static_assert(kEntityVelocityOffset + 2 * sizeof(float) <= kEntityPlayerSize,
                  "the fake player block must cover the velocity vector");

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
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

    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    std::printf("B346 base=%d\n", g_EngineBase != 0 ? 1 : 0);

    char script[4096];
    if (std::strcmp(scenario, "gate") == 0) {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) return tostring(select(2, pcall(f))) end"
            " local function count(...) return select('#', ...) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B346 gatefn=' .. type(p.AddVelocity))"
            // ★★ 1 参写法必须放行（语料 20 处**全是 1 参**）；2 参（布尔）也要放行。
            " print('B346 gate1=' .. ok(function() return p:AddVelocity(Vector(1, 0)) end))"
            " print('B346 gate1n=' .. tostring(count(p:AddVelocity(Vector(1, 0)))))"
            " print('B346 gate2=' .. ok(function() return p:AddVelocity(Vector(1, 0), true) end))"
            " print('B346 gate2n=' .. tostring(count(p:AddVelocity(Vector(1, 0), true))))"
            // --- 参数闸门（消息里必须带本 API 的名字）--------------------------------
            " print('B346 g0=' .. ok(function() return p:AddVelocity() end))"
            " print('B346 g0err=' .. err(function() return p:AddVelocity() end))"
            " print('B346 g3=' .. ok(function() return p:AddVelocity(Vector(1, 0), true, 1) end))"
            " print('B346 gnum=' .. ok(function() return p:AddVelocity(1) end))"
            " print('B346 gnumerr=' .. err(function() return p:AddVelocity(1) end))"
            " print('B346 gstr=' .. ok(function() return p:AddVelocity(Vector(1, 0), 'x') end))"
            " print('B346 gstrerr=' .. err(function() return p:AddVelocity(Vector(1, 0), 'x') end))"
            // --- 接收者不是实体 ⇒ 报错（把方法取出来、显式传一个表当 `self`）------------
            " local f = p.AddVelocity"
            " print('B346 grecv=' .. ok(function() return f(Isaac, Vector(1, 0)) end))"
            " print('B346 grecverr=' .. err(function() return f(Isaac, Vector(1, 0)) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else {
        //: 五个真值场景：摆好速度/摩擦/时间缩放，调一次，再读回来比。
        //: ★ 每个场景编译一份（模板里那组占位符由 Python 按场景替换好）⇒
        //:   这里不需要再按名字分派；`argv` 只用于把二进制与场景一一对应。
        const double velocityX = @@VX@@;
        const double velocityY = @@VY@@;
        const double argX = @@AX@@;
        const double argY = @@AY@@;
        const double friction = @@FR@@;
        const double timeScale = @@TS@@;
        const bool ignoreTimeScale = @@FLAG@@;
        static_cast<void>(argX);
        static_cast<void>(argY);
        static_cast<void>(ignoreTimeScale);

        WriteVelocity(static_cast<float>(velocityX), static_cast<float>(velocityY));
        WriteFriction(static_cast<float>(friction));
        WriteTimeScale(static_cast<float>(timeScale));
        float beforeX = 0.0F, beforeY = 0.0F, beforeFriction = 0.0F, beforeTimeScale = 0.0F;
        ReadVelocity(&beforeX, &beforeY);
        beforeFriction = ReadFriction();
        beforeTimeScale = ReadTimeScale();
        std::printf("B346 before=%g,%g fr=%g ts=%g\n", static_cast<double>(beforeX),
                    static_cast<double>(beforeY), static_cast<double>(beforeFriction),
                    static_cast<double>(beforeTimeScale));

        //: ★★ **只能调一次**：本 API 会真的改引擎内存（不像 344/345 那两条在宿主里必然降级），
        //:   所以"调两次分别取 ok 与返回个数"会把速度**加两遍**（本批第一版就是这么红的）。
        //:   做法：把调用包进一个函数，一次调用里同时拿到「没报错」与「返回几个值」。
        const char* s =
            "local p = Isaac.GetPlayer(0)"
            " local captured = nil"
            " local function go() captured = select('#', p.AddVelocity(p, Vector(@@LUA_AX@@, @@LUA_AY@@)@@LUA_FLAG@@)) end"
            " local ok, callerr = pcall(go)"
            " print('B346 callok=' .. tostring(ok))"
            " print('B346 callerr=' .. tostring(callerr))"
            " print('B346 n=' .. tostring(captured))";
        std::snprintf(script, sizeof(script), "%s", s);

        const auto result =
            LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b346.lua");
        static_cast<void>(result);
        float afterX = 0.0F, afterY = 0.0F;
        ReadVelocity(&afterX, &afterY);
        std::printf("B346 after=%g,%g\n", static_cast<double>(afterX), static_cast<double>(afterY));
        return 0;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b346.lua");
    static_cast<void>(result);
    return 0;
}
'''


def _fill(values):
    """把某个场景的数值填进 `@@…@@` 占位符（每个场景编译一份；`build_lua_harness` 按源码指纹缓存）。"""
    (name, velocity_x, velocity_y, arg_x, arg_y, friction, time_scale, _expect_x,
     _expect_y) = values
    source = HARNESS
    source = source.replace("@@VX@@", repr(velocity_x))
    source = source.replace("@@VY@@", repr(velocity_y))
    source = source.replace("@@AX@@", repr(arg_x))
    source = source.replace("@@AY@@", repr(arg_y))
    source = source.replace("@@FR@@", repr(friction))
    source = source.replace("@@TS@@", repr(time_scale))
    source = source.replace("@@FLAG@@", "true" if name == "d" else "false")
    #: Lua 侧用的实参（`Vector(x, y)`）与"传不传第 3 格"。
    source = source.replace("@@LUA_AX@@", repr(arg_x))
    source = source.replace("@@LUA_AY@@", repr(arg_y))
    source = source.replace("@@LUA_FLAG@@", ", true" if name == "d" else "")
    assert "@@" not in source, "还有没填上的占位符"
    return source


class Batch346AddVelocityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b346-")
        cls.binaries = {}
        for case in CASES:
            name = case[0]
            cls.binaries[name] = build_lua_harness(
                source_root=SOURCE,
                workdir=Path(cls.temporary.name) / f"harness-{name}",
                harness_source=_fill(case),
            )
        #: 闸门场景用同一份模板（随便填一组数；它不读那些编译期常量）。
        cls.gate = cls.binaries["a"]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        binary = self.gate if scenario == "gate" else self.binaries[scenario]
        result = subprocess.run([str(binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # ★ 批次 285 的教训：只回 stdout 时「Lua 报错」与「什么都没做」长得一样。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主 · 真值）

    def test_velocity_is_updated_by_the_pc_rule(self):
        """★★ **本批的核心判据**：五组 `(初速度, 实参, 摩擦, 时间缩放, flag)` ⇒ 读回来的速度。

        * a `(0,0)+(3,4)/2` ⇒ `(1.5, 2.0)`
        * b `(1,-2)+(1,1)/0.5` ⇒ `(3.0, 0.0)` —— ★ 「加法」而非「赋值」、「除摩擦」而非「除实参」
        * c `(0.5,0.5)+(0.5·(2,2))/1` ⇒ `(1.5, 1.5)` —— 拴住 `k` 的时间缩放支
        * d 同上但 `IgnoreTimeScale=true` ⇒ `(2.5, 2.5)` —— `k` 必须取 `1.0f`
        * e 摩擦 `0.0` ⇒ `(7, 8)` **不变**（零守卫；漏了会变 `inf`）
        """
        for name, vx, vy, _ax, _ay, friction, time_scale, expect_x, expect_y in CASES:
            with self.subTest(scenario=name):
                out = self.run_scenario(name)
                self.assertIn("B346 callok=true", out)
                self.assertIn("B346 n=0", out)
                self.assertIn(
                    f"B346 before={vx:g},{vy:g} fr={friction:g} ts={time_scale:g}", out)
                self.assertIn(f"B346 after={expect_x:g},{expect_y:g}", out)

    def test_zero_friction_is_a_silent_no_op(self):
        """★ **零守卫**单独再钉一次：摩擦为 `0.0` 时**速度一个字节都不许动**，也**不许报错**。

        （`test_velocity_is_updated_by_the_pc_rule` 的 e 组也会覆盖它，但这条把
        「不报错」也一起断言了 —— 漏掉守卫会得到 `inf`/`nan`，而**报错**会把整条回调摘掉。）
        """
        out = self.run_scenario("e")
        self.assertIn("B346 callok=true", out)
        self.assertIn("B346 before=7,8 fr=0 ts=1", out)
        self.assertIn("B346 after=7,8", out)
        self.assertNotIn("B346 after=inf", out)

    def test_argument_gates(self):
        """参数闸门：个数只接受 1 或 2、第 2 格必须是 `Vector`、第 3 格可省但必须是布尔。

        ★★ **1 参写法必须放行**（语料 20 处全是 1 参；收错个数会让模组每次调用都抛错、
        整条回调被摘 —— 批次 249 的形态）。★ 报错消息必须带本 API 的名字。
        """
        out = self.run_scenario("gate")
        self.assertIn("B346 base=1", out)
        self.assertIn("B346 gatefn=function", out)
        self.assertIn("B346 gate1=true", out)
        self.assertIn("B346 gate1n=0", out)
        self.assertIn("B346 gate2=true", out)
        self.assertIn("B346 gate2n=0", out)
        self.assertIn("B346 g0=false", out)
        self.assertIn("Entity:AddVelocity expects (Vector[, boolean]); got 0 argument(s)", out)
        self.assertIn("B346 g3=false", out)
        self.assertIn("B346 gnum=false", out)
        self.assertIn("Entity:AddVelocity expects a Vector", out)
        self.assertIn("B346 gstr=false", out)
        self.assertIn("Entity:AddVelocity expects a boolean IgnoreTimeScale", out)
        #: 接收者不是实体（`Isaac.AddVelocity(...)` 这种点号写法）⇒ 报"expects an entity"。
        self.assertIn("B346 grecv=false", out)
        self.assertIn("Entity:AddVelocity expects an entity", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 处理器 / 新常量 / 不是数据行 / 夹具已换。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        surface = SURFACE.read_text(encoding="utf-8")
        gap_report_test = GAP_REPORT_TEST.read_text(encoding="utf-8")

        self.assertIn('MakeId(ApiDomain::Isaac, 1, 0x00F9), ApiDomain::Isaac, "Entity", "AddVelocity"',
                      catalog)
        self.assertIn("{0x0E0100F9, &EntityAddVelocity},", api)
        self.assertRegex(api, r"int EntityAddVelocity\(lua_State\* state\)")
        #: ★★ 反回归：它是**手写纯算法**（Switch 侧没有可调真身），不许被塞进数据行表。
        self.assertNotRegex(api, r"0x0E0100F9[^\n]*EngineCallShape")
        self.assertNotRegex(api, r"0x0E0100F9[^\n]*FieldKind::")
        self.assertNotIn('"Entity:AddVelocity"', surface)

        #: ★ 算式必须逐条照 PC：先 `k*分量`、再 `/摩擦`、再 `+=`（括号钉死结合律），无钳制。
        self.assertIn("(k * velocity->x) / friction", api)
        self.assertIn("(k * velocity->y) / friction", api)
        self.assertIn("friction == 0.0F", api)
        #: ★★ **不许**调 `TimeScaledFriction`（PC 的 AddVelocity 根本没调它）。
        self.assertIn("不调 `TimeScaledFriction`", constants + api)

        self.assertIn("inline constexpr uintptr_t kEntityTimeScaleOffset = 0x370;", constants)

        #: ★★ 夹具必须已经换掉（否则本批实现完那条门禁会红）：链式夹具改成
        #: `Room:EmitBloodFromWalls`（B 组定案"做不到"⇒ 没有可落地的实现路径）。
        self.assertIn("Game():GetRoom():EmitBloodFromWalls(1, 1)", gap_report_test)
        self.assertIn('self.assertIn("EmitBloodFromWalls", names)', gap_report_test)
        #: ★ 只看**夹具正文**那一段（`COMMENT_ONLY_FIXTURE` 里那句 `AddVelocity` 是**纯注释**的
        #:   负对照，按 M 组 §4.3 第 7 条**故意保留**、永远不被当代码扫描）。
        fixture_block = gap_report_test.split("FIXTURE = \"\"\"", 1)[1].split('\"\"\"', 1)[0]
        self.assertNotIn("Game():GetRoom():AddVelocity(", fixture_block)

        #: 契约页必须在仓里（台账引的是 `Entity.md:282`）。
        self.assertTrue(CONTRACT_PAGE.is_file())

    def test_the_overturned_negative_result_is_recorded(self):
        """★★ 本批最重要的一条纪律：**推翻旧负结果要留痕、要写清错在哪**。

        批次 331 记「两侧摩擦模型不同 ⇒ 不能做」；复核证明是**同一族**（PC 绑定 `0x422B60` 的算式
        与 Switch 三格一一对应）⇒ 常量段与处理器注释里都要写明"推翻"。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        #: ★ 十六进制字面量在注释里有大小写两种写法 ⇒ 用小写比对（不然同一个数会假红）。
        haystack = constants.lower()
        for needle in ("0x422b60", "0x2c4", "0x2f4", "0x2b8", "0x2bc", "0x370", "0x340", "0x334",
                       "0x5989c", "0x3f800000", "0xb727c5ac", "timescaledfriction"):
            self.assertIn(needle, haystack, f"证据 {needle} 没有写进常量段")
        self.assertIn("推翻", api)
        self.assertIn("Entity.md", constants)


if __name__ == "__main__":
    unittest.main()
