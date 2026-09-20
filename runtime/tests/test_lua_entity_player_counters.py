"""`EntityPlayer` 四个"计数类"成员的宿主行为测试（2026-09-18）。

## 为什么需要它

`GetNumKeys` / `GetNumBombs` / `GetSoulCharge` / `GetBloodCharge` 在此之前都是
**`PushZero` 的恒返回 0 假桩**（而 `analysis/lua-api-inventory` 把它们记成 `implemented`，
只因为它们命中目录行 ⇒ 台账在骗人，详见 `docs/改动日志-20260918.md` 的"账目失真"那一段）。
假读数不报错、不崩，模组拿它们做算术会得到错误结论（与"套装恒 `0/3`"同类）。

本用例钉住"**真的读了内存**"，并且**故意在夹具里写死字面偏移**（不跟实现侧常量走）——
夹具跟着实现常量走会两边一起错、断言永远绿（见 `docs/错误复盘.md` 2026-09-16 第一条）。
值也刻意取互不相同且非默认：只要实现读错字段或还在返回 0，就一定有一条断言红。

顺带钉住"降级口径"：实体拿不到时（vptr 不对）压 **0**，不压 nil —— PC 的返回类型是数字，
模组普遍直接参与算术，nil 会把整条回调摘掉。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

// 夹具里**写死字面偏移**（与实现侧的 `kEntityPlayer*Offset` 常量**故意不一致地解耦**）：
// 夹具跟着实现常量走，会让"实现把偏移写错 + 夹具抄同一个错"变成永远绿的假断言。
//
// ★ 2026-09-18 夜：`kFixtureBombsOffset` 由 `0x16E4` 改成 **`0x16DC`**。原来那个值抄自
// `AddBombs` 里 `PlayerType == PLAYER_BLUEBABY_B` 的**特殊分支**，而引擎自己的消耗品路径
// （`store_consumable_data` 把金币/钥匙/炸弹依次存成 `ConsumableData+0x00/+0x04/+0x08`、
// `sync_consumable_counts` 按 bit0/bit1/bit2 同步）都指向 `+0x16DC`。
// 也就是说：**这条夹具写错了值 ⇒ 它当时无法发现实现也跟着错**（这正是该夹具注释里担心的
// "实现与夹具抄同一个错"）。现在改的是夹具里的**证据值**，不是为了让某次改动变绿。
constexpr std::uintptr_t kFixtureKeysOffset = 0x16D4;
constexpr std::uintptr_t kFixtureCoinsOffset = 0x16E0;
constexpr std::uintptr_t kFixtureBombsOffset = 0x16DC;
constexpr std::uintptr_t kFixtureSoulChargeOffset = 0x2478;
constexpr std::uintptr_t kFixtureBloodChargeOffset = 0x247C;

// 期望值互不相同、且都不是 0/默认值 ⇒ 读错字段或还在返回 0 都会被抓到。
constexpr std::uint32_t kKeys = 7;
constexpr std::uint32_t kCoins = 42;
constexpr std::uint32_t kBombs = 3;
constexpr std::uint32_t kSoulCharge = 9;
constexpr std::uint32_t kBloodCharge = 5;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

void WriteWord(std::vector<unsigned char>& block, std::size_t offset, std::uint64_t value) {
    WriteAt(block, offset, value);
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void CreateBlocks() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
}

void PublishOwnerSlot(std::uint64_t variableAddress) {
    WriteWord(g_ModuleBytes, kGameOwnerGlobalSlotOffset, variableAddress);
}

void PublishPlayers(const std::vector<std::uint64_t>& players) {
    g_PlayerArrayBytes.assign(players.size() * sizeof(std::uint64_t) + sizeof(std::uint64_t), 0);
    for (std::size_t index = 0; index < players.size(); ++index) {
        WriteWord(g_PlayerArrayBytes, index * sizeof(std::uint64_t), players[index]);
    }
    WriteWord(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteWord(g_GameBytes, kGamePlayerArrayEndOffset,
              AddressOf(g_PlayerArrayBytes) + players.size() * sizeof(std::uint64_t));
}

void FillPlayer(unsigned int keys, unsigned int coins, unsigned int bombs,
                unsigned int soulCharge, unsigned int bloodCharge) {
    WriteWord(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, 1);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, 0);
    WriteAt<std::uint32_t>(g_PlayerBytes, kFixtureKeysOffset, keys);
    WriteAt<std::uint32_t>(g_PlayerBytes, kFixtureCoinsOffset, coins);
    WriteAt<std::uint32_t>(g_PlayerBytes, kFixtureBombsOffset, bombs);
    WriteAt<std::uint32_t>(g_PlayerBytes, kFixtureSoulChargeOffset, soulCharge);
    WriteAt<std::uint32_t>(g_PlayerBytes, kFixtureBloodChargeOffset, bloodCharge);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const std::string scenario = argv[1];
    if (scenario != "valid" && scenario != "only_keys") return 91;
    // `only_keys`：**只有一个字段非零**。它抓的是"某个 getter 读到了别的字段"——
    // 全非零的场景里，读串字段也可能恰好撞上另一个非零值而侥幸通过。
    const bool onlyKeys = (scenario == "only_keys");

    CreateBlocks();
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    FillPlayer(kKeys, onlyKeys ? 0 : kCoins, onlyKeys ? 0 : kBombs,
               onlyKeys ? 0 : kSoulCharge, onlyKeys ? 0 : kBloodCharge);
    PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));
    WriteWord(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    PublishPlayers({AddressOf(g_PlayerBytes)});

    // 断言写在脚本里：值 + **返回类型必须是数字**（PC 的签名是 `int GetX()`）。
    const std::string script =
        std::string("EXPECT = {") +
        "keys=" + std::to_string(kKeys) + "," +
        "coins=" + std::to_string(onlyKeys ? 0 : kCoins) + "," +
        "bombs=" + std::to_string(onlyKeys ? 0 : kBombs) + "," +
        "soul=" + std::to_string(onlyKeys ? 0 : kSoulCharge) + "," +
        "blood=" + std::to_string(onlyKeys ? 0 : kBloodCharge) + "}\n" +
        "local mod = RegisterMod('CounterProbe', 1)\n"
        "local function check(name, value, expected)\n"
        "  if type(value) ~= 'number' then\n"
        "    error(name .. ' must return a number, got ' .. type(value))\n"
        "  end\n"
        "  if value ~= expected then\n"
        "    error(name .. ' returned ' .. tostring(value) .. ', expected ' .. tostring(expected))\n"
        "  end\n"
        "end\n"
        "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE, function()\n"
        "  local p = Isaac.GetPlayer(0)\n"
        "  if p == nil then error('GetPlayer(0) returned nil') end\n"
        "  check('GetNumKeys', p:GetNumKeys(), EXPECT.keys)\n"
        "  check('GetNumCoins', p:GetNumCoins(), EXPECT.coins)\n"
        "  check('GetNumBombs', p:GetNumBombs(), EXPECT.bombs)\n"
        "  check('GetSoulCharge', p:GetSoulCharge(), EXPECT.soul)\n"
        "  check('GetBloodCharge', p:GetBloodCharge(), EXPECT.blood)\n"
        "  ASSERTED = 1\n"
        "end)";
    const auto result =
        LuaRuntime::InitializeFromBuffer(script.data(), script.size(), "@counters.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("COUNTERS_FAIL the Lua state did not initialize\n");
        return 2;
    }
    LuaRuntime::DispatchPreGetCollectible(nullptr, 0, 0, 1, 0);
    if (LuaRuntime::TakeCallbackError()) {
        std::printf("COUNTERS_FAIL the assertions inside the script failed\n");
        return 3;
    }
    double asserted = 0.0;
    if (!LuaRuntime::ReadLuaGlobalNumber("ASSERTED", &asserted) || asserted != 1.0) {
        std::printf("COUNTERS_FAIL the script never reached its assertions\n");
        return 4;
    }
    std::printf("COUNTERS_OK scenario=%s\n", scenario.c_str());
    return 0;
}
'''


def host_compilers() -> tuple[str, str] | None:
    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None


class EntityPlayerCounterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        cc, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-player-counters-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "counters_harness.cpp"
        harness.write_text(HARNESS.lstrip(), encoding="utf-8")
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        objects = []
        for source in sorted(lua_root.glob("*.c")):
            if source.name in excluded:
                continue
            output = temporary / f"{source.stem}.o"
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root),
                 "-c", str(source), "-o", str(output)], text=True, capture_output=True)
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            objects.append(output)
        cls.binary = temporary / "counters_harness"
        build = subprocess.run(
            [cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *map(str, objects), "-o", str(cls.binary)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> str:
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, f"{scenario}: {result.stdout}{result.stderr}")
        return result.stdout

    def test_the_four_counters_read_the_engine_fields(self):
        self.assertIn("COUNTERS_OK scenario=valid", self.run_scenario("valid"))

    def test_only_the_keys_field_set_means_the_others_read_their_own_zero(self):
        """★ 抓"读串字段"：只有钥匙非零 ⇒ 其余四个必须回 0。

        没有这条时，"实现把 `GetNumBombs` 也读成钥匙那个偏移"这种错误在
        "全部非零"的场景里会**侥幸通过**（两个字段都非零）。"""
        self.assertIn("COUNTERS_OK scenario=only_keys", self.run_scenario("only_keys"))


if __name__ == "__main__":
    unittest.main()
