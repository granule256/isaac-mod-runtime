"""门禁：`Entity:MultiplyFriction(float Value)`（批次 333，2026-10-03）。

## 这一条是什么

| API | 契约 | 引擎侧 | 形状 | 语料 |
| --- | --- | --- | --- | --- |
| `Entity:MultiplyFriction(float Value)` | `Entity.md:510` | **读改写** `Entity + 0x340` 那一格 `float` | 字段行 + **本批新开**的 `FieldKind::FloatMultiplyArg` | 1 处 |

**PC 绑定本体**（`0x5951D0`）：`movss xmm0,[ebp+8]` → `mulss xmm0,[ecx+0x2c4]` →
`movss [ecx+0x2c4],xmm0; ret 4` ⇒ 判法四档第 ① 档（字段写）⇒ 走**数据行**。

## ★★ 这一批唯一需要判的事：乘**哪一格**

`Entity + 0x340` 与 `+0x33C` 是一对（**原值 / 本帧值**）。四条证据选了 `+0x340`：
① `Entity::Update` 读它喂给 `TimeScaledFriction(friction, dt)`、再把结果乘进**速度向量**（它才是生效的）；
② 同一函数把它写成 `[+0x33C] × 0.95f`（**摩擦衰减**，立即数 `0x3F733333`）；
③ `Entity::Init` 把 `+0x33C` **拷进** `+0x340`（⇒ `+0x33C` 是原值）；
④ ★★ **语料是每帧调用**（`events.lua:850` 在 `onUpdate` 里）⇒ 乘原值会逐帧指数级累积。
（详见 `runtime_constants.hpp` 批次 333 段 / 布局表 `entity.json` 的 `Friction` 行。）

## 宿主验到了什么、没验到什么

* ★★ **验到了真值**（本批与 328/332 那两条**不一样**）：字段数据行**没有入口指纹、读的就是我们伪造的
  那块内存** ⇒ 夹具把 `Entity + 0x340` 摆成某个值、调 API、**读回来比**。
  三个互不相等的组合（`2.0×0.5=1.0` / `3.0×2=6.0` / `1.25×1.0=1.25`）把「整格覆盖写」「加法写」
  「写错格」三种错法都堵住。
* **验到**：返回值个数 = **0**（写侧 kind 的口径）；参数闸门（不给 / 字符串 / 多给都报错，
  消息里有名字）；★ **非整值浮点必须放行**（`1.2` —— 语料就是这么调的）。
* **没验**：真机上那一格到底是不是「本帧的工作摩擦」—— 那是**偏移**问题，
  由布局表那行（`--verify` 重新反汇编核对）+ 上面四条证据兜住。
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
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
LAYOUT = ROOT / "tools" / "layout_tables" / "entity.json"
LAYOUT_HEADER = ROOT / "runtime" / "source" / "entity_layout.hpp"

INDEX = 0x00E5

#: `(场景, 初值, 乘数, 期望值)`。
CASES = (
    ("a", 2.0, 0.5, 1.0),
    ("b", 3.0, 2.0, 6.0),
    ("c", 1.25, 1.0, 1.25),
    ("d", 0.5, 0.5, 0.25),
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存：只要一个"当前玩家"。★ 与 328/332 那两条**不同**：本批的字段行读的就是
// 我们这块内存（没有入口指纹）⇒ 调用前后都能真读，**这是真值判据**。
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

//: `Entity + kEntityFrictionOffset` 那一格（float）的读写 —— 夹具自己就能看到 API 的效果。
void WriteFriction(float value) {
    std::memcpy(g_PlayerBytes.data() + kEntityFrictionOffset, &value, sizeof(value));
}

float ReadFriction() {
    float value = 0.0F;
    std::memcpy(&value, g_PlayerBytes.data() + kEntityFrictionOffset, sizeof(value));
    return value;
}

void PublishFakeGame() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    //: ★ 块要盖住要读的那一格。
    static_assert(kEntityFrictionOffset + sizeof(float) <= kEntityPlayerSize,
                  "the fake player block must cover the friction cell");
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

    double initial = 0.0;
    double multiplier = 0.0;
    if (std::strcmp(scenario, "a") == 0) { initial = CASE_A; multiplier = MULT_A; }
    else if (std::strcmp(scenario, "b") == 0) { initial = CASE_B; multiplier = MULT_B; }
    else if (std::strcmp(scenario, "c") == 0) { initial = CASE_C; multiplier = MULT_C; }
    else if (std::strcmp(scenario, "d") == 0) { initial = CASE_D; multiplier = MULT_D; }
    else if (std::strcmp(scenario, "gate") != 0) { return 91; }

    PublishFakeGame();
    WriteFriction(static_cast<float>(initial));
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    //: ★ 调用**前**的值（"只乘、不覆盖"这条判据的基线）。
    std::printf("B333 before=%.6f\n", ReadFriction());

    char script[1024];
    if (std::strcmp(scenario, "gate") == 0) {
        std::snprintf(script, sizeof(script),
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) return tostring(select(2, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B333 fn=' .. type(p.MultiplyFriction))"
            " print('B333 noarg=' .. ok(function() return p:MultiplyFriction() end))"
            " print('B333 noargerr=' .. err(function() return p:MultiplyFriction() end))"
            " print('B333 strarg=' .. ok(function() return p:MultiplyFriction('x') end))"
            " print('B333 strargerr=' .. err(function() return p:MultiplyFriction('x') end))"
            " print('B333 twoargs=' .. ok(function() return p:MultiplyFriction(1, 2) end))"
            " print('B333 nilarg=' .. ok(function() return p:MultiplyFriction(nil) end))");
    } else {
        // ★ 只调**一次**（这是写侧 API，多调一次就多乘一次）。
        std::snprintf(script, sizeof(script),
            "local function count(...) return select('#', ...) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B333 fn=' .. type(p.MultiplyFriction))"
            " print('B333 n=' .. tostring(count(p:MultiplyFriction(%.9g))))",
            multiplier);
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b333.lua");
    static_cast<void>(result);
    //: ★ 调用**后**的值 —— 真值判据就是这一行。
    std::printf("B333 after=%.6f\n", ReadFriction());
    return 0;
}
'''


class MultiplyFrictionBatch333Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b333-")
        source = HARNESS
        for name, initial, mult, _expected in CASES:
            source = source.replace(f"CASE_{name.upper()}", repr(initial))
            source = source.replace(f"MULT_{name.upper()}", repr(mult))
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=source,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主 · 真值）

    def test_the_cell_is_multiplied_not_overwritten(self):
        """★★ **本批的核心判据**：`2.0 × 0.5 = 1.0`、`3.0 × 2 = 6.0`、`1.25 × 1 = 1.25`、`0.5 × 0.5 = 0.25`。

        字段数据行读的就是夹具那块内存 ⇒ **这是真值判据**（不是接线判据）。
        「整格覆盖写」（会得到乘数本身）、「加法写」（会得到和）、「写错格」（读回原值）三种错法
        都会让至少一场红。
        """
        for name, initial, _mult, expected in CASES:
            with self.subTest(scenario=name):
                out = self.run_scenario(name)
                self.assertIn(f"B333 before={initial:.6f}", out)
                self.assertIn(f"B333 after={expected:.6f}", out)

    def test_the_api_returns_no_values(self):
        """★ 写侧 kind：返回值个数必须是 **0**（PC 返回 `void`）。

        ★ 这条同时兜住「新增写侧 kind 忘了进 `RowReturnsNoValues`」那类错 —— 忘了就会多压一个值。
        """
        out = self.run_scenario("a")
        self.assertIn("B333 fn=function", out)
        self.assertIn("B333 n=0", out)

    def test_argument_gate_accepts_a_number_and_rejects_the_rest(self):
        """参数闸门：**恰好一个数值**。不给 / 字符串 / `nil` / 多给都报错，且消息里有名字。

        ★★ 与非整值浮点有关的那一条在这里定：`1.2` 必须被**放行**（`_VALUE` 那几场用的就是浮点乘数），
        而字符串要拒 —— 若误用了同族的 `IsIntegerArgument`，浮点那几场会**直接报错**、
        `after` 读数会停在 `before` 上。
        """
        out = self.run_scenario("gate")
        self.assertIn("B333 fn=function", out)
        self.assertIn("B333 noarg=false", out)
        self.assertIn("Entity:MultiplyFriction expects one number argument", out)
        self.assertIn("B333 strarg=false", out)
        self.assertIn("B333 twoargs=false", out)
        self.assertIn("B333 nilarg=false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 新 kind / 偏移常量 / 布局表 / 编译期对账 —— 台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        header = FIELD_HEADER.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{INDEX:04X}), ApiDomain::Isaac, '
            f'"Entity", "MultiplyFriction"', catalog, "目录行缺失")
        #: ★ 数据行：`Entity + 0x340`、`FloatMultiplyArg`、接收者基类 `Entity`。
        self.assertRegex(
            api,
            r"\{\s*0x0E0100E5,\s*kEntityFrictionOffset,\s*0,\s*"
            r"FieldKind::FloatMultiplyArg,\s*FieldMissing::Zero,\s*"
            r"FieldReceipt::Entity,\s*0xFF\}",
            "数据行缺失或形状/接收者不对")
        #: ★★ 反回归：这条是**字段**写、不是引擎调用；不许被塞进引擎方法行。
        self.assertNotRegex(api, rf"0x0E0100E5[^\n]*EngineCallShape")

        #: 新 kind 的定义与「返回 0 值」名单。
        self.assertIn("FloatMultiplyArg = 19,", header)
        self.assertRegex(api, r"RowReturnsNoValues[\s\S]{0,900}FieldKind::FloatMultiplyArg")
        #: 偏移常量 + 编译期对账（两处同名常量不许漂移）。
        self.assertIn("inline constexpr uintptr_t kEntityFrictionOffset = 0x340;", constants)
        self.assertIn("kEntityFrictionOffset == layout::kEntityFrictionOffset", api)
        self.assertIn("kEntityFrictionOffset", LAYOUT_HEADER.read_text(encoding="utf-8"))

    def test_the_layout_row_is_confirmed_with_a_semantic_anchor(self):
        """布局表 `Friction` 行必须是 `confirmed`，且**带立即数的语义锚点**（那个 `0.95f`）。

        没有这条锚点，`+0x340` 就只是"被 `Entity::Update` 读过的一个 float"；
        有了它才能说清这一格是**被衰减的摩擦**（`--verify` 会重新反汇编逐条核对）。
        """
        import json
        table = json.loads(LAYOUT.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in table["rows"]}
        self.assertIn("Friction", rows)
        row = rows["Friction"]
        self.assertEqual(row["confidence"], "confirmed")
        self.assertEqual(row["offset"], 832)
        self.assertEqual(row["width"], 4)
        kinds = [e["kind"] for e in row["evidence"]]
        self.assertIn("semantic", kinds)
        self.assertGreaterEqual(kinds.count("access"), 2)
        immediates = [e.get("immediate") for e in row["evidence"] if e["kind"] == "semantic"]
        self.assertIn(16243, immediates)  # 0x3F73 —— 与相邻的 `mov w8,#0x3333` 合成 0.95f


if __name__ == "__main__":
    unittest.main()
