"""门禁：批次 324 —— `EntityNPC.ThrowSpider(...)`（**本项目第一条静态调用**，3 处 / 2 个模组）。

## 这一批加了什么

| 面 | 内容 |
| --- | --- |
| API | `EntityNPC.ThrowSpider(Vector Position, Entity Spawner, Vector TargetPos, boolean Big, float YOffset)`（契约 `tools/pc_contract_docs/EntityNPC.md:165`）|
| ★★★ 新能力 1 | **静态调用**：PC 的写法是 `EntityNPC.ThrowSpider(...)` —— **点号直呼在类名上**，没有 `this`。形状行的 `reserved[0]` 置 1（`EngineCallShapeRow::staticCall()`），处理器据此不从栈上取接收者、`integers[0]` 让给第一个实参 |
| ★★ 新能力 2 | **句柄返回**：`EngineReturnKind::EntityNpc`（`PushEntityHandle`；空指针压 `nil`）|
| 挂载点 | **全局 `EntityNPC` 表**（照 `ItemConfig`/`Isaac` 的 `lua_setglobal`）—— ★ **只挂静态行**，`npc:ThrowSpider(...)` 这种 PC 上不存在的写法我们**故意不提供** |
| 代价 | 形状那行是 16 字节数据；另两样是枚举值 + 返回那个 `switch` 里三行 ⇒ 没有新的"机制" |

## 宿主怎么验（判据核心）

★★★ **静态调用最容易错的地方是"实参落哪个寄存器"**（AAPCS64 下没有 `this` 占 `x0`）：

| 形参 | 寄存器 |
| --- | --- |
| `Vector Position` | `x0`（**指针**，指向处理器自己栈上的 `Vector2` 槽）|
| `Entity Spawner` | `x1`（nil ⇒ 0）|
| `Vector TargetPos` | `x2`（**指针**）|
| `boolean Big` | `w3` |
| `float YOffset` | `s0` |

夹具逐格断言：跳板桩记下的 `target` 必须是 `模块基址 + 0x1116EC`（**入口指纹也对上了** ——
假模块块里必须真的摆上守卫 `FF C3 01 D1`，否则这一行会被判降级、`calls` 会是 0），
`integers[0]/[2]` 指向的两块内存里必须真的躺着传进去的两个 `Vector`，`integers[1] == 0`、
`integers[3] == 1`、`floats[0] == 12.5`。★ 桩把返回的 `x0` 写成 0 ⇒ 正好顺带验到"拿不到就压 `nil`"。
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
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
SHAPES = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_method_api.hpp"

#: 夹具里那次调用用的实参（脚本里逐字写死，断言里也逐字比对）。
POSITION = (3.5, -4.25)
TARGET = (7.0, 8.0)
BIG = True
Y_OFFSET = 12.5

HARNESS = r'''
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/engine_method_api.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

extern "C" {
extern std::uint32_t g_HostEngineCallTrampolineCalls;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
extern double g_HostEngineCallTrampolineLastFloats[8];
//: ★★ 批次 338（2026-10-04）：浮点槽按 **f32** 解释的读数（引擎在 `sN` 里读到的就是它）。
//: 以前这里读的是 `LastFloats[0]` 那个 double —— 那是**错误的中间表示**，
//: 掩盖了「跳板把 float 当 double 装」这个 bug。
extern float g_HostEngineCallTrampolineLastFloat32[8];
}

// 伪造的引擎内存：只放**模块块**，里面摆上 `EntityNPC::ThrowSpider` 的入口守卫
// （前 4 字节 `FF C3 01 D1` = `kEntityNpcThrowSpiderEntryWord`，小端）——
// 入口指纹是这一行"能不能调"的第一道闸门，摆不上就根本不会走跳板（`calls` 会是 0）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::uintptr_t g_EngineBase = 0;

constexpr std::uintptr_t kGuardBytes = kEntityNpcThrowSpiderOffset;

static_assert((kEntityNpcThrowSpiderEntryWord & 0xFFU) == 0xFFU,
              "守卫第 1 字节应当是 0xFF（先看 runtime_constants.hpp 里怎么从 guard16 取的）");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

//: 小端写入入口指纹的 4 个字节。
void WriteEntryWord(std::uint32_t word) {
    for (int index = 0; index < 4; ++index) {
        g_ModuleBytes[kGuardBytes + static_cast<std::size_t>(index)] =
            static_cast<unsigned char>((word >> (8 * index)) & 0xFFU);
    }
}

void PublishFakeWorld(bool plantEntryWord) {
    g_ModuleBytes.assign(kGuardBytes + 0x40, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    if (plantEntryWord) {
        WriteEntryWord(kEntityNpcThrowSpiderEntryWord);
    }
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "call") != 0 && std::strcmp(scenario, "noentry") != 0 &&
        std::strcmp(scenario, "missingarg") != 0 && std::strcmp(scenario, "extraarg") != 0 &&
        std::strcmp(scenario, "method") != 0) {
        return 91;
    }
    PublishFakeWorld(std::strcmp(scenario, "noentry") != 0);

    std::string script_text =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "print('B324 kind=' .. type(EntityNPC))\n"
        "print('B324 fn=' .. type(EntityNPC.ThrowSpider))\n"
        "print('B324 inst=' .. tostring(EntityNPC.Morph))\n"
        "local p = Isaac.GetPlayer(0)\n"
        "print('B324 npcmethod=' .. tostring(p and p.ThrowSpider))\n";
    if (std::strcmp(scenario, "call") == 0 || std::strcmp(scenario, "noentry") == 0) {
        script_text +=
            "local ok1, result = pcall(function()\n"
            "  return EntityNPC.ThrowSpider(Vector(3.5, -4.25), nil, Vector(7, 8), true, 12.5)\n"
            "end)\n"
            "print('B324 ok=' .. tostring(ok1))\n"
            "print('B324 result=' .. tostring(result))\n";
    } else if (std::strcmp(scenario, "missingarg") == 0) {
        script_text +=
            "print('B324 ok=' .. ok(function() return EntityNPC.ThrowSpider(Vector(1, 1)) end))\n"
            "print('B324 msg=' .. err(function() return EntityNPC.ThrowSpider(Vector(1, 1)) end))\n";
    } else if (std::strcmp(scenario, "extraarg") == 0) {
        script_text +=
            "print('B324 ok=' .. ok(function() return EntityNPC.ThrowSpider("
            "Vector(1, 1), nil, Vector(1, 1), false, 0, 9) end))\n"
            "print('B324 msg=' .. err(function() return EntityNPC.ThrowSpider("
            "Vector(1, 1), nil, Vector(1, 1), false, 0, 9) end))\n";
    } else {
        // `method`：`npc:ThrowSpider(...)` —— ★ PC 上**不存在**这种写法（它是静态方法），
        // 我们**故意**不提供 ⇒ 应当是 `nil`（不是"能跑"）。
        script_text +=
            "local npc = p and p:ToNPC()\n"
            "print('B324 npc=' .. tostring(npc))\n"
            "print('B324 npcmethod2=' .. tostring(npc and npc.ThrowSpider))\n";
    }

    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b324.lua");
    static_cast<void>(result);
    std::printf("B324 base=0x%llX\n", static_cast<unsigned long long>(g_EngineBase));
    std::printf("B324 calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("B324 target=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget));
    std::printf("B324 x0=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[0]));
    std::printf("B324 x1=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[1]));
    std::printf("B324 x2=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[2]));
    std::printf("B324 w3=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[3]));
    std::printf("B324 s0=%.4f\n", static_cast<double>(g_HostEngineCallTrampolineLastFloat32[0]));
    // 把 `x0`/`x2` 当成 `Vector2*` 读回来 —— 这是"实参真的落到了那个寄存器"的最硬证据。
    for (int index = 0; index < 2; ++index) {
        const std::uintptr_t pointer = g_HostEngineCallTrampolineLastIntegers[
            index == 0 ? 0 : 2];
        float x = 0.0f;
        float y = 0.0f;
        if (pointer != 0) {
            std::memcpy(&x, reinterpret_cast<const void*>(pointer), sizeof(float));
            std::memcpy(&y, reinterpret_cast<const void*>(pointer + 4), sizeof(float));
        }
        std::printf("B324 vec%d=%.4f,%.4f\n", index, static_cast<double>(x),
                    static_cast<double>(y));
    }
    return 0;
}
'''

HARNESS = (HARNESS
           .replace("kEntityNpcThrowSpiderOffset", "kEntityNpcThrowSpiderOffset")
           .replace("kEntityNpcThrowSpiderEntryWord", "kEntityNpcThrowSpiderEntryWord"))


class EntityNpcThrowSpiderBatch324Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b324-")
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

    def test_static_call_lands_every_argument_in_the_right_register(self):
        """★★★ 核心判据：**没有 `this`** ⇒ 五个实参自己排 `x0/x1/x2/w3` 与 `s0`，逐格断言。"""
        out = self.run_scenario("call")
        self.assertIn("B324 kind=table", out)
        self.assertIn("B324 fn=function", out)
        #: 引擎入口 = 模块基址 + 偏移（**而且入口指纹对上了**，否则 `calls` 会是 0）。
        base = int(self.value(out, "B324 base"), 16)
        self.assertEqual(int(self.value(out, "B324 target"), 16), base + 0x1116EC, out)
        self.assertEqual(self.value(out, "B324 calls"), "1", out)
        #: ① `x0` = Position 的 `Vector2` 槽（指针）—— 内容必须逐字是脚本里传的那个 Vector。
        self.assertNotEqual(self.value(out, "B324 x0"), "0x0", out)
        self.assertEqual(self.value(out, "B324 vec0"), "3.5000,-4.2500", out)
        #: ② `x1` = Spawner（脚本传 `nil` ⇒ 0 —— 语料里真有一处这么写）。
        self.assertEqual(self.value(out, "B324 x1"), "0x0", out)
        #: ③ `x2` = TargetPos 的槽。
        self.assertNotEqual(self.value(out, "B324 x2"), "0x0", out)
        self.assertEqual(self.value(out, "B324 vec1"), "7.0000,8.0000", out)
        #: ④ `w3` = Big（true ⇒ 1）。
        self.assertEqual(int(self.value(out, "B324 w3"), 16), 1, out)
        #: ⑤ `s0` = YOffset（浮点**独立一路**，不被前四个整数挤走 —— 这正是最容易写错的地方）。
        self.assertEqual(self.value(out, "B324 s0"), "12.5000", out)

    def test_missing_entry_word_never_calls_the_engine(self):
        """入口指纹对不上 ⇒ **不调引擎**（`calls` 为 0），也不报错（静默降级）。"""
        out = self.run_scenario("noentry")
        self.assertEqual(self.value(out, "B324 calls"), "0", out)
        self.assertIn("B324 ok=true", out)
        #: 拿不到 ⇒ 压 `nil`（桩把返回的 `x0` 写成 0；这一格与"引擎返回空指针"同一条路径）。
        self.assertIn("B324 result=nil", out)

    def test_argument_count_gates(self):
        """参数个数闸门：少给/多给都报错，文案是 `EntityNPC:ThrowSpider expects 5 argument(s)`。

        ★ 这一条**不是** `expects at most N argument(s)` —— "at most" 那种文案只在形状声明了
        `optionalArgumentCount != 0`（尾部可省）时才出现（见 `EngineMethodHandler` 里那个 `if`）；
        本形状 5 个参数**全部必填**，所以两种错都报同一条。★ 别照抄别的族的断言。
        """
        missing = self.run_scenario("missingarg")
        self.assertIn("B324 ok=false", missing)
        self.assertIn("EntityNPC:ThrowSpider expects 5 argument(s)", missing)
        extra = self.run_scenario("extraarg")
        self.assertIn("B324 ok=false", extra)
        self.assertIn("EntityNPC:ThrowSpider expects 5 argument(s)", extra)
        #: ★ 两种错都不许把引擎调起来（闸门在调用之前）。
        self.assertEqual(self.value(extra, "B324 calls"), "0", extra)

    def test_it_is_static_only(self):
        """★ 静态方法只挂在全局表上：`npc:ThrowSpider` 必须**取不到**（PC 也没这种写法）。"""
        out = self.run_scenario("method")
        self.assertNotIn("B324 npcmethod2=function", out)
        self.assertIn("B324 inst=nil", out)  # 实例方法 `Morph` 也不在全局表上（它在元表上）

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """形状行必须是**静态**（`reserved[0] = 1`）、返回 `EntityNpc`，且行挂在静态表里。"""
        shapes = SHAPES.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        rows = ISAAC_API.read_text(encoding="utf-8")
        self.assertRegex(shapes, r"StaticVoidVector2RefHandleVector2RefBoolFloat\s*=\s*30,")
        self.assertRegex(shapes, r"EntityNpc\s*=\s*5,")
        self.assertIn("bool staticCall() const noexcept", shapes)
        #: 形状行：5 个参数、返回 EntityNpc、最后一格 `{1, 0, 0}`（= 静态调用标记）。
        self.assertRegex(
            rows,
            r"\{5, \{EngineArgKind::Vector2Ref, EngineArgKind::Handle, EngineArgKind::Vector2Ref,\s*\n"
            r"\s*EngineArgKind::Bool, EngineArgKind::Float,[^}]*\},\s*\n"
            r"\s*EngineReturnKind::EntityNpc, FieldReceipt::Entity, IntArgumentGuard::None, 0, "
            r"\{1, 0, 0\}\}")
        #: 常量与数据行。
        self.assertIn("kEntityNpcThrowSpiderOffset = 0x1116EC", constants)
        self.assertIn("kEntityNpcThrowSpiderEntryWord = 0xD101C3FFU", constants)
        self.assertIn("kEntityNPCStaticRows", rows)
        #: ★ 批次 325 把这段抽成了通用助手（`AttachStaticOwnerTable`）⇒ 断言跟着改；
        #:   这一条**必须**留着：它是"静态方法挂全局类表、不走 AttachOwnerMethods"的判据。
        self.assertRegex(rows, r"AttachStaticOwnerTable\(state, \"EntityNPC\",")


if __name__ == "__main__":
    unittest.main()
