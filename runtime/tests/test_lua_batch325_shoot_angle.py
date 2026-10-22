"""门禁：批次 325 —— `EntityLaser.ShootAngle(...)`（**第二条静态调用**，8 处 / 1 个模组）。

## 这一批是什么

| 面 | 内容 |
| --- | --- |
| API | `EntityLaser.ShootAngle(int Variant, Vector SourcePos, float AngleDegrees, int Timeout, Vector PosOffset, Entity Source)`（契约 `tools/pc_contract_docs/EntityLaser.md:146`，逐字 `static EntityLaser`）|
| 能力 | 沿用批次 324 立的两样：**静态调用**（形状行 `reserved[0]`）+ **句柄返回**（新加 `EngineReturnKind::EntityLaser`）⇒ 本批只多一个枚举值 |
| 新形状 | 31 `StaticIntVector2RefFloatIntVector2RefHandleBool`（**7 个参数**，`optionalArgumentCount = 1`）|
| 挂载点 | 全局 `EntityLaser` 表（把批 324 的函数抽成通用的 `AttachStaticOwnerTable` 复用）|

## ★★ 本批推翻了批 282 的一条排除理由

批 282 把这条**排除**掉了，注释写的是「引擎符号 7 参 vs 契约 6 参 ⇒ 按『参数个数对齐』规则排除」。
本批去读了 **PC 那条绑定**（`tools/pc_exe_binding.py ShootAngle` ⇒ `0x8C7550`）：

```
8c755f  movzx ecx, byte ptr [ebp + 0x20]   ← ★ 第 7 格参数（0x8/0xc/0x10/0x14/0x18/0x1c/0x20 七格）
8c7566  push  ecx                          ← ★ 原样转发给 Game::Spawn 的第 8 个参数
8c757e  call  0x6d0ca0                     ←   Game::Spawn(7 /*ENTITY_LASER*/, …)
```

⇒ **PC 与 Switch 签名一致**，差的第 7 格只是 C++ 头里的**缺省值**（契约文档不写它）。
⇒ 按「尾部 1 个可省」处理（省略时保持 0），与 `Room:SetGridPath(int,int,int)` 同一档。
★ 教训：**「契约少写一个」不等于「引擎真的少一个」** —— 要去 PC 看那条绑定收几个参数。

## 判据

★★★ 静态调用最容易错的是"实参落哪个寄存器"。AAPCS64 下没有 `this`：

| 形参 | 寄存器 |
| --- | --- |
| `int Variant` | `x0` |
| `Vector SourcePos` | `x1`（**指针**）|
| `float AngleDegrees` | **`s0`**（浮点独立一路）|
| `int Timeout` | `x2` |
| `Vector PosOffset` | `x3`（**指针**）|
| `Entity Source` | `x4`（nil ⇒ 0）|
| 第 7 个 `bool`（契约没写） | `w5`（省略 ⇒ 0）|

夹具逐格断言（含把 `x1`/`x3` 当 `Vector2*` 读回来核对内容）。
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

VARIANT = 5
SOURCE_POS = (1.0, 2.0)
ANGLE = 90.0
TIMEOUT = 15
POS_OFFSET = (3.0, 4.0)

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

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::uintptr_t g_EngineBase = 0;
constexpr std::uintptr_t kGuardBytes = kEntityLaserShootAngleOffset;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

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
        WriteEntryWord(kEntityLaserShootAngleEntryWord);
    }
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "call") != 0 && std::strcmp(scenario, "noentry") != 0 &&
        std::strcmp(scenario, "shortarg") != 0 && std::strcmp(scenario, "extraarg") != 0 &&
        std::strcmp(scenario, "method") != 0) {
        return 91;
    }
    PublishFakeWorld(std::strcmp(scenario, "noentry") != 0);

    std::string script_text =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "print('B325 kind=' .. type(EntityLaser))\n"
        "print('B325 fn=' .. type(EntityLaser.ShootAngle))\n"
        "print('B325 inst=' .. tostring(EntityLaser.SetActiveRotation))\n"
        "local p = Isaac.GetPlayer(0)\n"
        "print('B325 method=' .. tostring(p and p.ShootAngle))\n";
    if (std::strcmp(scenario, "call") == 0 || std::strcmp(scenario, "noentry") == 0) {
        script_text +=
            "local ok1, result = pcall(function()\n"
            "  return EntityLaser.ShootAngle(5, Vector(1, 2), 90, 15, Vector(3, 4), nil)\n"
            "end)\n"
            "print('B325 ok=' .. tostring(ok1))\n"
            "print('B325 result=' .. tostring(result))\n";
    } else if (std::strcmp(scenario, "shortarg") == 0) {
        script_text +=
            "print('B325 ok=' .. ok(function() return EntityLaser.ShootAngle(5, Vector(1, 2), 90, 15, Vector(3, 4)) end))\n"
            "print('B325 msg=' .. err(function() return EntityLaser.ShootAngle(5, Vector(1, 2), 90, 15, Vector(3, 4)) end))\n";
    } else if (std::strcmp(scenario, "extraarg") == 0) {
        script_text +=
            "print('B325 ok=' .. ok(function() return EntityLaser.ShootAngle("
            "5, Vector(1, 2), 90, 15, Vector(3, 4), nil, false, 9) end))\n"
            "print('B325 msg=' .. err(function() return EntityLaser.ShootAngle("
            "5, Vector(1, 2), 90, 15, Vector(3, 4), nil, false, 9) end))\n";
    } else {
        script_text +=
            "local laser = p and p:ToLaser()\n"
            "print('B325 laser=' .. tostring(laser))\n"
            "print('B325 lasermethod=' .. tostring(laser and laser.ShootAngle))\n";
    }

    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b325.lua");
    static_cast<void>(result);
    std::printf("B325 base=0x%llX\n", static_cast<unsigned long long>(g_EngineBase));
    std::printf("B325 calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("B325 target=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget));
    std::printf("B325 x0=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[0]));
    std::printf("B325 x1=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[1]));
    std::printf("B325 x2=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[2]));
    std::printf("B325 x3=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[3]));
    std::printf("B325 x4=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[4]));
    std::printf("B325 w5=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[5]));
    std::printf("B325 s0=%.4f\n", static_cast<double>(g_HostEngineCallTrampolineLastFloat32[0]));
    const int registers[2] = {1, 3};
    for (int index = 0; index < 2; ++index) {
        const std::uintptr_t pointer =
            g_HostEngineCallTrampolineLastIntegers[registers[index]];
        float x = 0.0f;
        float y = 0.0f;
        if (pointer != 0) {
            std::memcpy(&x, reinterpret_cast<const void*>(pointer), sizeof(float));
            std::memcpy(&y, reinterpret_cast<const void*>(pointer + 4), sizeof(float));
        }
        std::printf("B325 vec%d=%.4f,%.4f\n", index, static_cast<double>(x),
                    static_cast<double>(y));
    }
    return 0;
}
'''


class EntityLaserShootAngleBatch325Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b325-")
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
        """★★★ 核心：**没有 `this`** ⇒ 七个形参自己排 `x0/x1/s0/x2/x3/x4/w5`，逐格断言。"""
        out = self.run_scenario("call")
        self.assertIn("B325 kind=table", out)
        self.assertIn("B325 fn=function", out)
        base = int(self.value(out, "B325 base"), 16)
        self.assertEqual(int(self.value(out, "B325 target"), 16), base + 0xF743C, out)
        self.assertEqual(self.value(out, "B325 calls"), "1", out)
        self.assertEqual(int(self.value(out, "B325 x0"), 16), VARIANT, out)
        #: `x1` = SourcePos 的槽（内容逐字是脚本里那个 Vector）。
        self.assertNotEqual(self.value(out, "B325 x1"), "0x0", out)
        self.assertEqual(self.value(out, "B325 vec0"), "1.0000,2.0000", out)
        #: `s0` = AngleDegrees（**浮点独立一路**，不被前面的整数挤走）。
        self.assertEqual(self.value(out, "B325 s0"), "90.0000", out)
        #: `x2` = Timeout。
        self.assertEqual(int(self.value(out, "B325 x2"), 16), 15, out)
        #: `x3` = PosOffset 的槽。
        self.assertNotEqual(self.value(out, "B325 x3"), "0x0", out)
        self.assertEqual(self.value(out, "B325 vec1"), "3.0000,4.0000", out)
        #: `x4` = Source（脚本传 nil ⇒ 0；语料里真有一处这么写）。
        self.assertEqual(self.value(out, "B325 x4"), "0x0", out)
        #: `w5` = 契约没写的那第 7 格（省略 ⇒ 0，"尾部可省"那一档）。
        self.assertEqual(int(self.value(out, "B325 w5"), 16), 0, out)

    def test_missing_entry_word_never_calls_the_engine(self):
        """入口指纹对不上 ⇒ 不调引擎、不报错，返回 `nil`。"""
        out = self.run_scenario("noentry")
        self.assertEqual(self.value(out, "B325 calls"), "0", out)
        self.assertIn("B325 ok=true", out)
        self.assertIn("B325 result=nil", out)

    def test_argument_count_gates(self):
        """参数个数：**最少 6**（尾部 1 个可省）、**最多 7**。"""
        short = self.run_scenario("shortarg")
        self.assertIn("B325 ok=false", short)
        self.assertIn("EntityLaser:ShootAngle expects at most 7 argument(s)", short)
        extra = self.run_scenario("extraarg")
        self.assertIn("B325 ok=false", extra)
        self.assertIn("EntityLaser:ShootAngle expects at most 7 argument(s)", extra)
        self.assertEqual(self.value(extra, "B325 calls"), "0", extra)

    def test_it_is_static_only(self):
        """★ 静态方法只挂全局表：`EntityLaser.SetActiveRotation`（实例方法）不在全局表上。"""
        out = self.run_scenario("method")
        self.assertIn("B325 inst=nil", out)
        self.assertNotIn("B325 lasermethod=function", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """形状 31（静态、返回 EntityLaser、尾部 1 个可省）与常量、行、全局表。"""
        shapes = SHAPES.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        rows = ISAAC_API.read_text(encoding="utf-8")
        self.assertRegex(shapes, r"StaticIntVector2RefFloatIntVector2RefHandleBool\s*=\s*31,")
        self.assertRegex(shapes, r"EntityLaser\s*=\s*6,")
        #: 形状行：7 个参数、返回 EntityLaser、尾部 1 个可省、静态标记 `{1, 0, 0}`。
        self.assertRegex(
            rows,
            r"\{7, \{EngineArgKind::Int, EngineArgKind::Vector2Ref, EngineArgKind::Float, "
            r"EngineArgKind::Int,\s*\n[^}]*\},\s*\n"
            r"\s*EngineReturnKind::EntityLaser, FieldReceipt::Entity, IntArgumentGuard::None, 1, "
            r"\{1, 0, 0\}\}")
        self.assertIn("kEntityLaserShootAngleOffset = 0xF743C", constants)
        self.assertIn("kEntityLaserShootAngleEntryWord = 0xD101C3FFU", constants)
        self.assertIn("kEntityLaserStaticRows", rows)
        self.assertRegex(rows, r"AttachStaticOwnerTable\(state, \"EntityLaser\",")


if __name__ == "__main__":
    unittest.main()
