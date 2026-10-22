"""门禁：批次 326 —— `EntityPlayer:FireTechLaser(...)`（1 处 / 1 个模组）。

## 这一批补的是什么

不是"又一条 API"，而是一种**参数种类**：`EngineArgKind::FloatDefaultOne`。
原因：PC 契约里确实有**缺省不是 0** 的浮点参数 ——
`EntityPlayer:FireTechLaser(Vector Position, LaserOffset OffsetID, Vector Direction,
boolean LeftEye, boolean OneHit = false, Entity Source = nil, **float DamageMultiplier = 1**)`
（`tools/pc_contract_docs/EntityPlayer.md:728`）。而共享处理器原来表达"尾部可省"的方式是
`optionalArgumentCount`，它的语义是「**省略的寄存器保持 0**」（那一格的注释写着
「只有缺省值就是 0/false/空指针 的参数能用这一格」）⇒ 直接用它会把伤害倍率填成 `0.0`（激光没伤害）。

⇒ 本批加的那一种参数种类：**给出时**与 `Float` 完全一样；**省略时**填 `1.0`。

## 判据

★★★ 关键断言是**省略的那一格落到 `s0` 时是 `1.0` 而不是 `0.0`**（这正是这一批存在的理由），
以及**显式给值时原样透传**（证明它没有变成"永远 1.0"）。
其余按 AAPCS64 逐格断言（实例方法 ⇒ `this` 占 `x0`）：
`Position`→`x1`、`OffsetID`→`x2`、`Direction`→`x3`、`LeftEye`→`w4`、`OneHit`→`w5`、`Source`→`x6`、
`DamageMultiplier`→`s0`。
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

OFFSET_ID = 7
POSITION = (1.0, 2.0)
DIRECTION = (3.0, 4.0)
EXPLICIT_MULTIPLIER = 2.5

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
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

// 伪造的引擎内存（形状抄批次 319/321 的"假玩家"夹具）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes → Game*
//   Game 的玩家数组（begin/end）里放一个元素 → 玩家（首字 = base + Entity_Player 的 vptr）
//   ★ 模块块还要够大：这一行的入口守卫在 `kEntityPlayerFireTechLaserOffset`（≈ 2.8 MB）处。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::uintptr_t g_EngineBase = 0;
constexpr std::uintptr_t kGuardBytes = kEntityPlayerFireTechLaserOffset;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeWorld(bool plantEntryWord) {
    g_ModuleBytes.assign(kGuardBytes + 0x40, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    if (plantEntryWord) {
        for (int index = 0; index < 4; ++index) {
            g_ModuleBytes[kGuardBytes + static_cast<std::size_t>(index)] =
                static_cast<unsigned char>((kEntityPlayerFireTechLaserEntryWord >> (8 * index)) & 0xFFU);
        }
    }

    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uintptr_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "omitted") != 0 && std::strcmp(scenario, "explicit") != 0 &&
        std::strcmp(scenario, "noentry") != 0 && std::strcmp(scenario, "shortarg") != 0 &&
        std::strcmp(scenario, "extraarg") != 0) {
        return 91;
    }
    PublishFakeWorld(std::strcmp(scenario, "noentry") != 0);

    std::string script_text =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local p = Isaac.GetPlayer(0)\n"
        "print('B326 p=' .. type(p))\n"
        "print('B326 fn=' .. type(p and p.FireTechLaser))\n";
    if (std::strcmp(scenario, "omitted") == 0 || std::strcmp(scenario, "noentry") == 0) {
        // ★ 语料写法（events.lua:1828）：5 个实参 —— Source 与 DamageMultiplier 走缺省。
        script_text +=
            "local good, result = pcall(function()\n"
            "  return p:FireTechLaser(Vector(1, 2), 7, Vector(3, 4), false, true)\n"
            "end)\n"
            "print('B326 ok=' .. tostring(good))\n"
            "print('B326 result=' .. tostring(result))\n";
    } else if (std::strcmp(scenario, "explicit") == 0) {
        // 显式给全 7 个：`DamageMultiplier` 传 2.5，必须**原样透传**（不能被写成 1.0）。
        script_text +=
            "local good, result = pcall(function()\n"
            "  return p:FireTechLaser(Vector(1, 2), 7, Vector(3, 4), true, false, nil, 2.5)\n"
            "end)\n"
            "print('B326 ok=' .. tostring(good))\n"
            "print('B326 result=' .. tostring(result))\n";
    } else if (std::strcmp(scenario, "shortarg") == 0) {
        script_text +=
            "print('B326 ok=' .. ok(function() return p:FireTechLaser(Vector(1, 2), 7, Vector(3, 4)) end))\n"
            "print('B326 msg=' .. err(function() return p:FireTechLaser(Vector(1, 2), 7, Vector(3, 4)) end))\n";
    } else {
        script_text +=
            "local f = function() return p:FireTechLaser(Vector(1, 2), 7, Vector(3, 4), false, true, nil, 1, 9) end\n"
            "print('B326 ok=' .. ok(f))\n"
            "print('B326 msg=' .. err(f))\n";
    }

    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b326.lua");
    static_cast<void>(result);
    std::printf("B326 base=0x%llX\n", static_cast<unsigned long long>(g_EngineBase));
    std::printf("B326 calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("B326 target=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget));
    std::printf("B326 x1=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[1]));
    std::printf("B326 x2=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[2]));
    std::printf("B326 x3=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[3]));
    std::printf("B326 w4=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[4]));
    std::printf("B326 w5=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[5]));
    std::printf("B326 x6=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[6]));
    std::printf("B326 s0=%.4f\n", static_cast<double>(g_HostEngineCallTrampolineLastFloat32[0]));
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
        std::printf("B326 vec%d=%.4f,%.4f\n", index, static_cast<double>(x),
                    static_cast<double>(y));
    }
    return 0;
}
'''


class EntityPlayerFireTechLaserBatch326Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b326-")
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

    def test_omitted_tail_uses_the_contract_defaults(self):
        """★★★ 本批的核心：语料那种 5 参写法下，`Source` 缺省是 `nil`、
        **`DamageMultiplier` 的缺省是 `1`（不是 0）** —— 后者正是这一批存在的理由。"""
        out = self.run_scenario("omitted")
        self.assertIn("B326 p=userdata", out)
        self.assertIn("B326 fn=function", out)
        base = int(self.value(out, "B326 base"), 16)
        self.assertEqual(int(self.value(out, "B326 target"), 16), base + 0x2B9020, out)
        self.assertEqual(self.value(out, "B326 calls"), "1", out)
        #: `x1` = Position 的槽（内容逐字是脚本里那个 Vector）。
        self.assertEqual(self.value(out, "B326 vec0"), "1.0000,2.0000", out)
        #: `x2` = OffsetID。
        self.assertEqual(int(self.value(out, "B326 x2"), 16), OFFSET_ID, out)
        #: `x3` = Direction 的槽。
        self.assertEqual(self.value(out, "B326 vec1"), "3.0000,4.0000", out)
        #: `w4` = LeftEye(false ⇒ 0)、`w5` = OneHit(true ⇒ 1)。
        self.assertEqual(int(self.value(out, "B326 w4"), 16), 0, out)
        self.assertEqual(int(self.value(out, "B326 w5"), 16), 1, out)
        #: `x6` = Source（缺省 nil ⇒ 0）。
        self.assertEqual(self.value(out, "B326 x6"), "0x0", out)
        #: ★★★ `s0` = DamageMultiplier —— **缺省是 1.0，不是 0.0**。
        self.assertEqual(self.value(out, "B326 s0"), "1.0000", out)

    def test_explicit_value_passes_through(self):
        """显式给值时**原样透传**（证明 `FloatDefaultOne` 不是"永远 1.0"）。"""
        out = self.run_scenario("explicit")
        self.assertEqual(self.value(out, "B326 calls"), "1", out)
        self.assertEqual(self.value(out, "B326 s0"), "2.5000", out)
        #: 同一形状的其它格也照旧：`LeftEye` 这次传 true ⇒ `w4 == 1`。
        self.assertEqual(int(self.value(out, "B326 w4"), 16), 1, out)
        self.assertEqual(int(self.value(out, "B326 w5"), 16), 0, out)

    def test_missing_entry_word_never_calls_the_engine(self):
        """入口指纹对不上 ⇒ 不调引擎、不报错，返回 `nil`。"""
        out = self.run_scenario("noentry")
        self.assertEqual(self.value(out, "B326 calls"), "0", out)
        self.assertIn("B326 ok=true", out)
        self.assertIn("B326 result=nil", out)

    def test_argument_count_gates(self):
        """参数个数：**最少 4**（尾部 3 个可省）、**最多 7**。"""
        short = self.run_scenario("shortarg")
        self.assertIn("B326 ok=false", short)
        self.assertIn("EntityPlayer:FireTechLaser expects at most 7 argument(s)", short)
        extra = self.run_scenario("extraarg")
        self.assertIn("B326 ok=false", extra)
        self.assertIn("EntityPlayer:FireTechLaser expects at most 7 argument(s)", extra)
        self.assertEqual(self.value(extra, "B326 calls"), "0", extra)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """形状 32（尾部 3 个可省、最后一格 `FloatDefaultOne`）+ 常量 + 行 + 目录 id。"""
        shapes = SHAPES.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        rows = ISAAC_API.read_text(encoding="utf-8")
        self.assertRegex(shapes, r"FloatDefaultOne\s*=\s*5,")
        self.assertRegex(shapes, r"Vector2RefIntVector2RefBoolBoolHandleFloatOpt3\s*=\s*32,")
        self.assertRegex(
            rows,
            r"\{7, \{EngineArgKind::Vector2Ref, EngineArgKind::Int, EngineArgKind::Vector2Ref,\s*\n"
            r"[^}]*EngineArgKind::FloatDefaultOne,[^}]*\},\s*\n"
            r"\s*EngineReturnKind::EntityLaser, FieldReceipt::Entity, IntArgumentGuard::None, 3, "
            r"\{0, 0, 0\}\}")
        self.assertIn("kEntityPlayerFireTechLaserOffset = 0x2B9020", constants)
        self.assertIn("kEntityPlayerFireTechLaserEntryWord = 0xD103C3FFU", constants)
        self.assertRegex(rows, r"\{0x0E0100DF, kEntityPlayerFireTechLaserOffset,")
        #: ★ 反回归：`FloatDefaultOne` 只该出现在这一条新形状里（别把别的形状也改了）。
        self.assertEqual(shapes.count("FloatDefaultOne = 5,"), 1)


if __name__ == "__main__":
    unittest.main()
