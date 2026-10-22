"""门禁：`Isaac.GetSoundIdByName`（批次 265，2026-10-02）。

## 这条为什么能做成真实现

工作清单把它归在 `glue_compose`（"PC 在 exe 的 Lua 绑定层实现"）。它的语义是**按名字查引擎的
音效表**，而引擎里确实存着这张表（三条独立指令证据写在 `runtime_constants.hpp` 的批次 265 段）：

* `vector<SoundEffect>` 在 `SoundEffects + 0x00 / +0x08`（`SoundEffects::Play @ 0x4A2FD0` 开头
  `ldp x24, x8, [x19]`）；
* 元素步长 `0x1F0`（同一函数里"除以 496"的乘常数 `0xBDEF7BDF` + `lsr #4`，以及 `LoadConfig`
  里两处 `sub …, …, #0x1f0`）；
* 名字是元素 `+0x1D8` 的 libc++ `std::string`（`LoadConfig @ 0x4A220C`：`strcmp(属性名,"name")`
  → `bl std::string::assign`，目标 `x0 = x25 = 元素 + 0x1D8`）。

★ **"编号 == 元素下标"是引擎自己给的判据**：`SoundEffects::Play` 算完 `count` 之后紧跟着
`cmp w8, w22`（w22 = 第 1 个形参 `eSoundEffect`）—— 引擎**把 id 当下标**去索引这张表。
所以命中后返回**下标**与引擎一致（与 `Isaac.GetMusicIdByName` 同一条路）。

## 本文件钉什么、不钉什么

钉**接线与降级**：目录行 / 绑定行 / 契约页:行 / 参数个数 / 拿不到 `Manager` 时返回 `-1`（不报错、
不是 nil）/ **形状保险（条数上限）** / 以及"复用共享的 Manager 解析"这条。

★ **不钉值**：宿主没有引擎 ⇒ 证明不了"某个音效名真的换出了那个编号"。那要真机
（见存档 README 的 V10，用模组自带的音效名反查）。
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

#: `(名字, 域内序号, 契约页:行)`
API = ("GetSoundIdByName", 0x008D, "Isaac.md:424")

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

void PublishZeroedModule() {
    // 盖住 `kGameOwnerGlobalSlotOffset` 与 `kGameManagerGlobalSlotOffset` 两个槽（两者都在
    // 0xAAC6xx 附近）：槽里全 0 ⇒ 拿不到 Manager ⇒ 必须走"返回 -1"那条路。
    const std::size_t size = kGameOwnerGlobalSlotOffset > kGameManagerGlobalSlotOffset
                                 ? kGameOwnerGlobalSlotOffset + 16
                                 : kGameManagerGlobalSlotOffset + 16;
    g_ModuleBytes.assign(size, 0);
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
    PublishZeroedModule();
    LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "degrade") == 0) {
        script =
            "local ok, value = pcall(function() return Isaac.GetSoundIdByName('BitsAppear') end)"
            " print('SND ok='..tostring(ok)..' value='..tostring(value)..' type='..type(value))"
            " local empty, v2 = pcall(function() return Isaac.GetSoundIdByName('') end)"
            " print('SND empty ok='..tostring(empty)..' value='..tostring(v2))"
            " local num, v3 = pcall(function() return Isaac.GetSoundIdByName(42) end)"
            " print('SND number ok='..tostring(num)..' value='..tostring(v3))";
    } else if (std::strcmp(scenario, "arity") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local a = ok(function() return Isaac.GetSoundIdByName() end)"
            " local b = ok(function() return Isaac.GetSoundIdByName({}) end)"
            " print('SND arity='..a..','..b)";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@soundid.lua");
    static_cast<void>(result);
    return 0;
}
'''


class IsaacSoundIdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-soundid-")
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

    def test_missing_manager_returns_minus_one_without_erroring(self):
        """拿不到 `Manager` ⇒ **返回整数 `-1`**（契约里"找不到"的那一支），**不报错、不是 nil**。

        为什么必须是 `-1` 而不是 nil：PC 的返回类型是 `SoundEffect`（整数），契约正文逐字写了
        "Returns `-1` if no sound with that name could be found"；模组拿它当编号直接喂给
        `SFXManager:Play(id)`，nil 会让它们抛错、把整条回调摘掉。
        """
        out = self.run_scenario("degrade")
        self.assertIn("SND ok=true value=-1 type=number", out)

    def test_empty_name_and_number_arguments_follow_lua_conventions(self):
        """空串直接 `-1`（引擎侧不会有无名音效）；数字按 `luaL_checklstring` 转成串（与 PC 同口径）。"""
        out = self.run_scenario("degrade")
        self.assertIn("SND empty ok=true value=-1", out)
        self.assertIn("SND number ok=true value=-1", out)

    def test_argument_gates(self):
        """参数个数不对、或给了表，都必须报错（模组写错了就该报错）。"""
        out = self.run_scenario("arity")
        self.assertIn("SND arity=false,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_row_and_binding_row_exist(self):
        name, index, _page = API
        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "Isaac", "{name}"',
            CATALOG.read_text(encoding="utf-8"),
            f"catalog 里没有 Isaac:{name}（域内序号 0x{index:04x}）")
        self.assertRegex(
            ISAAC_API.read_text(encoding="utf-8"),
            rf"\{{\s*(?i:0x{0x0E010000 + index:08x}),\s*&Isaac{name}\s*\}}",
            f"Isaac 绑定表里没有 0x{0x0E010000 + index:08X} → Isaac{name}")

    def test_contract_page_and_line_are_quoted_in_the_implementation(self):
        self.assertIn(API[2], ISAAC_API.read_text(encoding="utf-8"),
                      f"{API[0]} 的实现处没有引用契约 {API[2]}")

    def test_shape_constants_carry_the_evidence(self):
        """四个形状常量必须在，且值就是反汇编读出来的那几个（写错就是查错表）。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        for needle in (
            "kSoundEffectVectorBeginOffset = 0x00",
            "kSoundEffectVectorEndOffset = 0x08",
            "kSoundEffectSize = 0x1F0",
            "kSoundEffectNameStringOffset = 0x1D8",
            "kSoundEffectMaximumCount = 4096",
        ):
            with self.subTest(needle):
                self.assertIn(needle, constants, f"缺常量：{needle}")
        # 取证里必须留下"引擎自己把 id 当下标"这条（它是"返回下标"的**唯一**依据）。
        self.assertIn("cmp w8, w22", constants,
                      "取证里必须留下 `SoundEffects::Play` 那句 `cmp w8, w22`（id 当下标用的证据）")
        # 0x1F0 是"除以 496"的乘常数：mov w9,#0x7bdf + movk w9,#0xbdef,lsl#16 合成 0xbdef7bdf。
        self.assertIn("mov w9,#0x7bdf", constants, "取证里必须留下乘常数的低半字（除 496 的写法）")
        self.assertIn("movk w9,#0xbdef,lsl#16", constants, "取证里必须留下乘常数的高半字")

    def test_reuses_the_shared_manager_resolution_and_the_music_traversal_shape(self):
        """★ 复用共享的 `ResolveManagerAddress()`，并与曲目那条**同一条遍历形状**。

        两处各写一份"基址 → g_Manager 槽 → Manager*"必然漂 —— 这是批次 148 把
        `ResolveManagerAddress` 抽出来时写下的理由。
        """
        isaac = ISAAC_API.read_text(encoding="utf-8")
        handler = isaac[isaac.index("\nint IsaacGetSoundIdByName(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("ResolveManagerAddress()", handler, "必须复用共享的 Manager 解析")
        self.assertIn("kManagerSoundEffectsOffset", handler, "子对象偏移必须是音效表那一个")
        # 形状保险与逐字节比较：与曲目那条同一套写法（没有第二份"怎么比串"的实现）。
        self.assertIn("kSoundEffectMaximumCount", handler, "必须有条数上限的形状保险")
        self.assertIn("ResolveLibcxxString", handler, "必须复用 libc++ 串解析（不要自己读 std::string）")
        self.assertIn("std::memcmp", handler, "比较必须是逐字节相等")

    def test_isaac_members_are_called_with_a_dot(self):
        """`Isaac` 是全局表 ⇒ 按 `.` 调 ⇒ 栈上不含 `self`，第 1 个实参就是这个字符串。"""
        isaac = ISAAC_API.read_text(encoding="utf-8")
        handler = isaac[isaac.index("\nint IsaacGetSoundIdByName(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("luaL_checklstring(state, 1, &length)", handler,
                      "第 1 个实参就是名字（不含 self）")


if __name__ == "__main__":
    unittest.main()
