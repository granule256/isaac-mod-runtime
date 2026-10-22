"""门禁：批次 339（2026-10-04）—— `EntityFamiliar:FireProjectile(Vector Dir)`（1 处）。

## 这一批是什么

契约 `EntityFamiliar.md:57/59` 只有 **1 个形参**（`Vector Dir`），而引擎真身
`Entity_Familiar::fire_projectiles(Vector2 const&, bool)` @ `0xB06FC` **多一个隐藏 `bool`**；
真身逐字存在 ⇒ 手写转发（与 334 的 `CheckFamiliar`、337 的 `FireTear` 同一条路）。

★ 同族另有一个重载 `fire_projectiles(eDirection, bool)` @ `0xB06B8`（吃方向枚举）——
契约要的是 `Vector` 那一个，**两者的入口字不同**（`0xD10643FF` vs `0xD100C3FF`），
所以"取错重载"是**可判定的**（本文件直接断言这一点）。

## 判据

* **实参个数恰好 1**、**必须是 `Vector`**、**接收者必须是精确的 `EntityFamiliar`**；
* **入口首 4 字节对不上 ⇒ 不调引擎、不报错**，压 `nil`（契约返回 `EntityTear`）。
* ★ 造 familiar 句柄用的是批次 330 那一招：把假玩家的 `Parent` 指向一个
  "**精确 `Entity_Familiar` vptr + `Type = ENTITY_FAMILIAR`**" 的块 ⇒ `p.Parent:ToFamiliar()`。

★ 没验到的（真机项，作业单第九节）：真机上真的射出一颗眼泪、返回的句柄能用，
以及那个隐藏 `bool` 取 `false` 对不对（依据是契约散文 + 引擎自身调用点，**不是被证明的等式**）。
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

// 造 familiar 句柄（抄批次 330 那一招）：
//   假玩家（精确 Entity_Player vptr）→ `Isaac.GetPlayer(0)` 认它；
//   假玩家的 `Parent` 指向目标块 → `p.Parent` 交出"任意实体"句柄；
//   目标块 = **精确 `Entity_Familiar` vptr + Type = ENTITY_FAMILIAR** ⇒ `:ToFamiliar()` 认它。
// ★ **故意不种 `kEntityFamiliarFireProjectileEntryWord`** —— 本批走 `AsFunction`（直接按签名调），
//   种了入口字就会跳进伪造块 ⇒ 用例只跑"降级 + 参数闸门"。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_FamiliarBytes;
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

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    g_FamiliarBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_FamiliarBytes, 0, g_EngineBase + kEntityFamiliarVtableOffset);
    WriteAt<std::uint32_t>(g_FamiliarBytes, kEntityTypeOffset, kEntityTypeFamiliar);

    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_FamiliarBytes));

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
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    const bool known = std::strcmp(scenario, "degrade") == 0 ||
                       std::strcmp(scenario, "noargs") == 0 ||
                       std::strcmp(scenario, "twoargs") == 0 ||
                       std::strcmp(scenario, "badvec") == 0;
    if (!known) return 91;
    PublishFakeWorld();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    std::string script =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local p = Isaac.GetPlayer(0)\n"
        "local fam = p.Parent:ToFamiliar()\n"
        "print('B339 fam=' .. type(fam) .. ' fn=' .. type(fam and fam.FireProjectile))\n";
    if (std::strcmp(scenario, "degrade") == 0) {
        // ★ 语料写法（`RepentancePlus/main.lua:1931`）：只传方向。
        script +=
            "local good, value = pcall(function() return fam:FireProjectile(Vector(1, 2)) end)\n"
            "print('B339 ok=' .. tostring(good))\n"
            "print('B339 value=' .. tostring(value))\n";
    } else if (std::strcmp(scenario, "noargs") == 0) {
        script +=
            "print('B339 ok=' .. ok(function() return fam:FireProjectile() end))\n"
            "print('B339 msg=' .. err(function() return fam:FireProjectile() end))\n";
    } else if (std::strcmp(scenario, "twoargs") == 0) {
        script +=
            "print('B339 ok=' .. ok(function() return fam:FireProjectile(Vector(1,2), Vector(3,4)) end))\n"
            "print('B339 msg=' .. err(function() return fam:FireProjectile(Vector(1,2), Vector(3,4)) end))\n";
    } else {
        script +=
            "print('B339 ok=' .. ok(function() return fam:FireProjectile(7) end))\n"
            "print('B339 msg=' .. err(function() return fam:FireProjectile(7) end))\n";
    }

    const char* text = script.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(text, std::strlen(text), "@b339.lua");
    static_cast<void>(result);
    std::printf("B339 calls=%u\n", g_HostEngineCallTrampolineCalls);
    return 0;
}
'''


class FireProjectileBatch339Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b339-")
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
        """★ 语料那种 1 参写法：入口字对不上 ⇒ **不调引擎、不报错**，返回值是 `nil`。"""
        out = self.run_scenario("degrade")
        self.assertIn("B339 fam=userdata fn=function", out)
        self.assertIn("B339 ok=true", out)
        self.assertEqual(self.value(out, "B339 value"), "nil", out)
        self.assertEqual(self.value(out, "B339 calls"), "0", out)

    def test_argument_count_gates(self):
        """实参个数恰好 1：0 个 / 2 个都报错。"""
        for scenario in ("noargs", "twoargs"):
            out = self.run_scenario(scenario)
            self.assertIn("B339 ok=false", out)
            self.assertIn("EntityFamiliar:FireProjectile expects a direction vector", out)

    def test_argument_type_gate(self):
        """`Dir` 必须是 `Vector`。"""
        out = self.run_scenario("badvec")
        self.assertIn("B339 ok=false", out)
        self.assertIn("EntityFamiliar:FireProjectile expects a direction vector", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """两个常量 + 手写处理器 + 绑定行 + 目录 id + ★ **两个重载的入口字不同**。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        source = ISAAC_API.read_text(encoding="utf-8")
        catalog = CATALOG.read_text(encoding="utf-8")
        shapes = SHAPES.read_text(encoding="utf-8")

        self.assertIn("kEntityFamiliarFireProjectileOffset = 0xB06FC", constants)
        self.assertIn("kEntityFamiliarFireProjectileEntryWord = 0xD10643FFu", constants)
        #: ★ 取的是吃 `Vector2` 的那个重载（`0xB06FC`），不是吃 `eDirection` 的 `0xB06B8`
        #: —— 两个入口字不同，取错会被这一条抓住。
        self.assertNotIn("kEntityFamiliarFireProjectileOffset = 0xB06B8", constants)
        self.assertIn("0xB06B8", constants)  # 注释里记了另一个重载
        self.assertIn("int EntityFamiliarFireProjectile(lua_State* state)", source)
        self.assertIn("std::uintptr_t EntityFamiliarFireProjectileMethod() noexcept", source)
        self.assertIn("kEntityFamiliarHandlers", source)
        self.assertRegex(source, r"\{0x0E0100EB, &EntityFamiliarFireProjectile\},")
        self.assertRegex(catalog,
                         r"MakeId\(ApiDomain::Isaac, 1, 0x00EB\).*\"EntityFamiliar\", \"FireProjectile\"")
        #: ★ 本批**不加形状**（手写）。
        self.assertIsNone(re.search(r"\b\w*FireProjectile\w*\s*=\s*\d+", shapes))


if __name__ == "__main__":
    unittest.main()
