"""门禁：批次 337（2026-10-04 凌晨）—— `EntityPlayer:FireTear(...)`（**4 处 / 3 个模组**）。

## 这一批是什么

交接第八份 §3「批 C」里**处数最大**的一条（4 处），也是"引擎真身在、但要手写转发"那类：
契约 **7 个形参**、Switch 真身只收 **5 格**。

| 契约 | 引擎 |
| --- | --- |
| `FireTear(Vector Position, Vector Velocity, boolean CanBeEye = true, boolean NoTractorBeam = false, boolean CanTriggerStreakEnd = true, Entity Source = nil, float DamageMultiplier = 1)` → `EntityTear` | `Entity_Player::FireTear(Vector2 const& /*x1*/, Vector2 /*按值 → s0,s1*/, u32 /*w2*/, Entity* /*x3*/, float /*s2*/)` @ `0x2A991C` |

★ 三个布尔被引擎**打包成一个 `u32` 位掩码**（mangled 里的 `j`），而 `Velocity` 是**按值**的 HFA
（PC 调用点连推 8 字节、Switch 入口第一条就是 `stp s0,s1,[x29,#-0x8]`）。
⇒ 数据行那条路缺两种表达能力 ⇒ **手写**（与 328/332/334 同一笔账）。

## 判据

* **参数闸门**：2..7 个实参；`Position`/`Velocity` 必须是 Vector；`Source` 非 nil 时必须是实体句柄；
  `DamageMultiplier` 必须是数值。
* **降级**：入口首 4 字节对不上 ⇒ **不调引擎、不报错**，压 `nil` 回去（契约返回 `EntityTear`）。
* **接线**：两个常量、绑定行 `0x0E0100EA`、目录行、`EngineCallShape` 表**零增长**。

## ★★ 宿主验不到什么（要写清楚）

宿主**没有引擎**，而这条走的是 `AsFunction`（**直接按编译期签名调**，不走跳板 —— 见下）
⇒ 只要入口指纹对得上就会**跳进伪造块**。所以宿主用例**故意不种入口字**，
只跑"降级 + 参数闸门"这两条路。
**真值**（射出来的眼泪带不带那个速度、三个布尔对不对）只能在**真机**上验 ⇒ 挂作业单第九节。

## ★ 顺便记一条与跳板有关的观察（本批发现，未在本批处理）

`EngineCallTrampoline` 的浮点入参是按 **`double`** 装的（`.s` 里 `ldp d0, d1, [x11]`），
而共享处理器写进去的是 `static_cast<double>(value)` —— 引擎若把那一格当 **`float`** 读
（读 `d0` 的**低 32 位**），拿到的是 0。★ 本批**没有**走跳板（`AsFunction` 由编译器按签名装寄存器）
⇒ 这条 API 不受影响；但**走数据行的浮点参数**是否受影响值得单独查一批，已记进交接。
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
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
SHAPES = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_method_api.hpp"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

extern "C" {
extern std::uint32_t g_HostEngineCallTrampolineCalls;
}

// 伪造的引擎内存：只要一个"当前玩家"（`FireTear` 的接收者从栈上取）。
// ★ **故意不种 `kEntityPlayerFireTearEntryWord`** —— 本批走 `AsFunction`（直接按签名调），
//   种了入口字就会跳进这块伪造内存 ⇒ 用例只跑"降级 + 参数闸门"。
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

void PublishFakeWorld() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
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
    const bool known = std::strcmp(scenario, "degrade") == 0 ||
                       std::strcmp(scenario, "noargs") == 0 ||
                       std::strcmp(scenario, "onevec") == 0 ||
                       std::strcmp(scenario, "badvec") == 0 ||
                       std::strcmp(scenario, "toomany") == 0 ||
                       std::strcmp(scenario, "badsource") == 0 ||
                       std::strcmp(scenario, "baddamage") == 0;
    if (!known) return 91;
    PublishFakeWorld();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    std::string script =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local p = Isaac.GetPlayer(0)\n"
        "print('B337 p=' .. type(p) .. ' fn=' .. type(p and p.FireTear))\n";
    if (std::strcmp(scenario, "degrade") == 0) {
        // ★ 语料写法（`events.lua:900`）：5 个实参。
        script +=
            "local good, value = pcall(function() return p:FireTear(Vector(1,2), Vector(3,4), "
            "false, false, false) end)\n"
            "print('B337 ok=' .. tostring(good))\n"
            "print('B337 value=' .. tostring(value))\n";
    } else if (std::strcmp(scenario, "noargs") == 0) {
        script +=
            "print('B337 ok=' .. ok(function() return p:FireTear() end))\n"
            "print('B337 msg=' .. err(function() return p:FireTear() end))\n";
    } else if (std::strcmp(scenario, "onevec") == 0) {
        script +=
            "print('B337 ok=' .. ok(function() return p:FireTear(Vector(1,2)) end))\n"
            "print('B337 msg=' .. err(function() return p:FireTear(Vector(1,2)) end))\n";
    } else if (std::strcmp(scenario, "badvec") == 0) {
        script +=
            "print('B337 ok=' .. ok(function() return p:FireTear(1, 2) end))\n"
            "print('B337 msg=' .. err(function() return p:FireTear(1, 2) end))\n";
    } else if (std::strcmp(scenario, "toomany") == 0) {
        script +=
            "print('B337 ok=' .. ok(function() return p:FireTear(Vector(1,2), Vector(3,4), false, "
            "false, false, nil, 1, 9) end))\n"
            "print('B337 msg=' .. err(function() return p:FireTear(Vector(1,2), Vector(3,4), false, "
            "false, false, nil, 1, 9) end))\n";
    } else if (std::strcmp(scenario, "badsource") == 0) {
        script +=
            "print('B337 ok=' .. ok(function() return p:FireTear(Vector(1,2), Vector(3,4), false, "
            "false, false, 7) end))\n"
            "print('B337 msg=' .. err(function() return p:FireTear(Vector(1,2), Vector(3,4), false, "
            "false, false, 7) end))\n";
    } else {
        script +=
            "print('B337 ok=' .. ok(function() return p:FireTear(Vector(1,2), Vector(3,4), false, "
            "false, false, nil, 'x') end))\n"
            "print('B337 msg=' .. err(function() return p:FireTear(Vector(1,2), Vector(3,4), false, "
            "false, false, nil, 'x') end))\n";
    }

    const char* text = script.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(text, std::strlen(text), "@b337.lua");
    static_cast<void>(result);
    std::printf("B337 calls=%u\n", g_HostEngineCallTrampolineCalls);
    return 0;
}
'''


class FireTearBatch337Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b337-")
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
        return result.stdout + result.stderr

    @staticmethod
    def value(out, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return match.group(1)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_corpus_call_shape_degrades_without_erroring(self):
        """★ 语料那 5 参写法：入口字对不上 ⇒ **不调引擎、不报错**，返回值是 `nil`。"""
        out = self.run_scenario("degrade")
        self.assertIn("B337 p=userdata fn=function", out)
        self.assertIn("B337 ok=true", out)
        self.assertEqual(self.value(out, "B337 value"), "nil", out)
        self.assertEqual(self.value(out, "B337 calls"), "0", out)

    def test_argument_count_gates(self):
        """实参 2..7 个：0 个 / 1 个 / 8 个都报错。"""
        noargs = self.run_scenario("noargs")
        self.assertIn("B337 ok=false", noargs)
        self.assertIn("EntityPlayer:FireTear expects a position", noargs)
        one = self.run_scenario("onevec")
        self.assertIn("B337 ok=false", one)
        self.assertIn("EntityPlayer:FireTear expects a position", one)
        many = self.run_scenario("toomany")
        self.assertIn("B337 ok=false", many)
        self.assertIn("EntityPlayer:FireTear expects a position", many)

    def test_argument_type_gates(self):
        """两个 Vector 必需；`Source` 给了就必须是实体；`DamageMultiplier` 必须是数值。"""
        badvec = self.run_scenario("badvec")
        self.assertIn("B337 ok=false", badvec)
        self.assertIn("EntityPlayer:FireTear expects a position vector", badvec)
        badsource = self.run_scenario("badsource")
        self.assertIn("B337 ok=false", badsource)
        src = self.run_scenario("badsource")
        self.assertIn("B337 msg=", src)
        baddamage = self.run_scenario("baddamage")
        self.assertIn("B337 ok=false", baddamage)
        self.assertIn("damage multiplier", baddamage)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """两个常量 + 手写处理器 + 绑定行 + 目录行 + ★ 形状表**零增长**。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        source = ISAAC_API.read_text(encoding="utf-8")
        catalog = CATALOG.read_text(encoding="utf-8")
        shapes = SHAPES.read_text(encoding="utf-8")

        self.assertIn("kEntityPlayerFireTearOffset = 0x2A991C", constants)
        self.assertIn("kEntityPlayerFireTearEntryWord = 0xD10383FFu", constants)
        self.assertIn("int EntityPlayerFireTear(lua_State* state)", source)
        self.assertIn("std::uintptr_t EntityPlayerFireTearMethod() noexcept", source)
        self.assertRegex(source, r"\{0x0E0100EA, &EntityPlayerFireTear\},")
        self.assertRegex(catalog,
                         r"MakeId\(ApiDomain::Isaac, 1, 0x00EA\).*\"EntityPlayer\", \"FireTear\"")
        #: ★ 本批**不加形状**（手写）：形状枚举里不该出现以 `FireTear` 命名的**新形状**
        #: （文件注释里提到这条 API 是允许的 —— 所以只断言"没有这样的枚举成员"）。
        self.assertIsNone(re.search(r"\b\w*FireTear\w*\s*=\s*\d+", shapes))


if __name__ == "__main__":
    unittest.main()
