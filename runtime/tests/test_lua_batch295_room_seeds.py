"""门禁：房间的**两个种子**（批次 295，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧字段 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Room:GetDecorationSeed()` | `Room.md:158` | `RoomDescriptor + 0x64`（`i32`） | `I32` / 降级 `Zero` | 8 |
| `Room:GetSpawnSeed()` | `Room.md:556` | `RoomDescriptor + 0x68`（`i32`） | `I32` / 降级 `Zero` | 8 |

两条都走**字段读取型数据行**、**零新机制**（接收者是既有的 `FieldReceipt::RoomDescriptor`，
批次 291 为"描述符上的字段"收的那条一跳链）。

## 为什么是 `0x64` / `0x68`

**PC 的标尺**（两条绑定本体都**先查空指针**）：

```
Room:GetDecorationSeed @ 0x4977F0:  mov eax,[ecx+4] → test eax,eax → 为零直接 ret → mov eax,[eax+0x58]
Room:GetSpawnSeed      @ 0x4276D0:  同上                                   → mov eax,[eax+0x5c]
```

⇒ PC 在描述符 `+0x58` / `+0x5C`（相邻，装饰在前），**而且降级值 0 是 PC 自己的行为**
（描述符为空就返回 0）⇒ 本批的 `FieldMissing::Zero` 是照抄的，不是我们挑的保守值。

**Switch 侧**（`+0x64` / `+0x68`，同样相邻、同样装饰在前）：

* `DecorationSeed` = `+0x64`：★★★ `Room::LoadBackdropGraphics` 里
  `ldr x8,[x20,#0x8]`（**描述符**）→ `ldr w1,[x8,#0x64]` → `add x21,x20,#0x1FE0`（Backdrop）
  → `bl Backdrop::SetSeed` —— **基址在同一段里就定死了**，而"喂给背景对象的种子"正是装饰种子的定义。
* `SpawnSeed` = `+0x68`：`Room::Init` 用它建 RNG（用途 17）后
  **按 `Game::IsHardMode()` 决定抽 1 次还是 2 次**，再挑一个房间内随机下标 ⇒ 出怪侧。
* 两格都在 `GameState::write_Room` 的**会存档字段表**里（`0x5C` 不在 ⇒ PC 那个位置在 Switch 上不是种子）。

## 宿主验到了什么、没验到什么

* **验到**（字段行**没有入口指纹** ⇒ 伪造内存里的值真会被读出来）：
  - ★★ **两个种子互相独立**：两格各摆**互不相同**的值（`0x12345678` / `7`），
    另有一场只让**出怪种子**非零（`0` / `0x0BADF00D`）⇒「读了同一格」与「读错格」都会红；
  - ★ **有符号读法**：`0xFFFFFFF6` 必须读回 **-10**（PC 的绑定是 `mov eax,…` + 契约写 `int`）；
  - **拿不到描述符**（`Room+0x8` 为 0）⇒ 两条都答 **0**、**不抛 Lua 错误**（照 PC 的行为）；
  - 参数闸门：多给一个参数报错。
* **没验**：真机上这两格是不是就是那两个种子（宿主里"偏移对不对"是同一张表的两处引用同一个常量，
  自己证不了自己）。⇒ 真机项 = 作业单 **V46**。
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
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
LAYOUT = ROOT / "tools" / "layout_tables" / "room_descriptor.json"

#: `(名字, 域内序号, 偏移常量)` —— 两条都是 `I32` + `FieldMissing::Zero` + `FieldReceipt::RoomDescriptor`。
SEED_APIS = (
    ("GetDecorationSeed", 0x002F, "kRoomDescriptorDecorationSeedOffset"),
    ("GetSpawnSeed", 0x0030, "kRoomDescriptorSpawnSeedOffset"),
)

#: 两个**互不相同**、且都非平凡的值（读错格 / 读同一格都会红）。
DECORATION = 0x12345678
SPAWN = 7
#: 只让出怪种子非零（`0` 与 `0x0BADF00D`）—— 专抓"两个都读了装饰种子"这类错法。
SPAWN_ONLY = 0x0BADF00D
#: `0xFFFFFFF6` = **-10**（有符号读法）。
NEGATIVE = -10


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状与批次 291/292 的用例一致）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                          = &g_RoomBytes（"当前房间"）
//   g_RoomBytes [kRoomDescriptorPointerOffset]= &g_DescriptorBytes（描述符；可为 0）
//   g_DescriptorBytes[0x64]                   = 装饰种子
//   g_DescriptorBytes[0x68]                   = 出怪种子
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_DescriptorBytes;
bool g_DescriptorAvailable = true;

static_assert(kRoomDescriptorDecorationSeedOffset + sizeof(std::int32_t) <= 0x80,
              "fake descriptor block must hold the decoration seed");
static_assert(kRoomDescriptorSpawnSeedOffset + sizeof(std::int32_t) <= 0x80,
              "fake descriptor block must hold the spawn seed");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeRoom() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_RoomBytes.assign(0x21B8, 0);
    g_DescriptorBytes.assign(0x80, 0);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset,
                           AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    if (g_DescriptorAvailable) {
        WriteAt<std::uint64_t>(g_RoomBytes, kRoomDescriptorPointerOffset,
                               AddressOf(g_DescriptorBytes));
    }
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = g_RoomBytes.data();
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    // 五个场景：
    //   values     —— 0x12345678 / 7（互不相同）
    //   spawnonly  —— 0 / 0x0BADF00D（只有出怪种子非零）
    //   negative   —— -10 / -3（看**有符号**读法）
    //   nodesc     —— 描述符指针为 0 ⇒ 两条都该答 0
    //   args       —— 参数闸门
    std::int32_t decoration = 0x12345678;
    std::int32_t spawn = 7;
    if (std::strcmp(scenario, "values") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "spawnonly") == 0) {
        decoration = 0;
        spawn = static_cast<std::int32_t>(0x0BADF00D);
    } else if (std::strcmp(scenario, "negative") == 0) {
        decoration = -10;
        spawn = -3;
    } else if (std::strcmp(scenario, "nodesc") == 0) {
        g_DescriptorAvailable = false;
    } else if (std::strcmp(scenario, "args") == 0) {
        // 默认值。
    } else {
        return 91;
    }

    PublishFakeRoom();
    WriteAt<std::int32_t>(g_DescriptorBytes, kRoomDescriptorDecorationSeedOffset, decoration);
    WriteAt<std::int32_t>(g_DescriptorBytes, kRoomDescriptorSpawnSeedOffset, spawn);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local room = Game():GetRoom()"
        " print('B295 roomkind=' .. type(room))"
        " print('B295 fn=' .. type(room.GetDecorationSeed) .. ',' .. type(room.GetSpawnSeed))"
        " local d = room:GetDecorationSeed()"
        " local s = room:GetSpawnSeed()"
        " print('B295 kind=' .. type(d) .. ',' .. type(s))"
        " print('B295 decoration=' .. tostring(d))"
        " print('B295 spawn=' .. tostring(s))"
        // 参数闸门：字段行**恰好收一个**（只有接收者）。
        " print('B295 argdec=' .. ok(function() return room:GetDecorationSeed(1) end))"
        " print('B295 argspawn=' .. ok(function() return room:GetSpawnSeed(1) end))"
        " print('B295 argerr=' .. tostring(select(2, pcall(function()"
        "   return room:GetSpawnSeed(1) end))))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b295.lua");
    static_cast<void>(result);
    return 0;
}
'''


class RoomSeedsBatch295Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b295-")
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

    # ---------------------------------------------------------------- 行为（宿主）

    def test_the_two_seeds_are_independent(self):
        """★★ 两格摆**互不相同**的值（`0x12345678` / `7`）⇒ 读错格 / 读同一格都会红。"""
        out = self.run_scenario("values")
        self.assertIn("B295 roomkind=userdata", out)
        self.assertIn("B295 fn=function,function", out)
        self.assertIn("B295 kind=number,number", out)
        self.assertIn(f"B295 decoration={DECORATION}", out)
        self.assertIn(f"B295 spawn={SPAWN}", out)
        #: 反向断言：两个值不许互换、不许相等。
        self.assertNotIn(f"B295 decoration={SPAWN}", out)
        self.assertNotIn(f"B295 spawn={DECORATION}", out)

    def test_only_spawn_non_zero(self):
        """★ 只让**出怪**种子非零（`0` / `0x0BADF00D`）⇒ 专抓"两个都读了装饰种子"。"""
        out = self.run_scenario("spawnonly")
        self.assertIn("B295 decoration=0", out)
        self.assertIn(f"B295 spawn={SPAWN_ONLY}", out)

    def test_seeds_read_back_signed(self):
        """★ `0xFFFFFFF6` 必须读回 **-10**（PC 的绑定是 `mov eax,…` + 契约写 `int`）。

        用 `FieldKind::U32` 读会得到 4294967286 ⇒ 那种实现在这里红。
        """
        out = self.run_scenario("negative")
        self.assertIn(f"B295 decoration={NEGATIVE}", out)
        self.assertIn("B295 spawn=-3", out)
        self.assertNotIn("4294967286", out)

    def test_missing_descriptor_degrades_to_zero(self):
        """★ 拿不到描述符（`Room+0x8` 为 0）⇒ 两条都答 **0**、**不抛错**。

        ★ 这个 0 是**照 PC 抄的**：PC 的两条绑定本体都是「描述符为空就直接返回 0」。
        """
        out = self.run_scenario("nodesc")
        self.assertIn("B295 decoration=0", out)
        self.assertIn("B295 spawn=0", out)
        self.assertIn("B295 kind=number,number", out)

    def test_argument_gate_is_exactly_one(self):
        """参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`），多给一个就报错。"""
        out = self.run_scenario("args")
        self.assertIn("B295 argdec=false", out)
        self.assertIn("B295 argspawn=false", out)
        self.assertIn("Room:GetSpawnSeed accepts no arguments", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 接收者 / 偏移常量。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, offset_name in SEED_APIS:
            with self.subTest(api=f"Room:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Room, 1, 0x{index:04X}), ApiDomain::Room, "Room", "{name}"',
                    catalog, f"目录里没有 Room:{name}")
                #: 两条都是 `I32` + `Zero` + `FieldReceipt::RoomDescriptor`（**既有**接收者）。
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0401{index:04x}),\s*{offset_name},\s*0,\s*"
                    rf"FieldKind::I32,\s*FieldMissing::Zero,\s*FieldReceipt::RoomDescriptor,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档/接收者不对：Room:{name}")
                #: ★ 反回归：不许塞进引擎方法行表（引擎里没有同名访问器）。
                self.assertNotRegex(remaining, rf"0x0401{index:04x}[^\n]*EngineCallShape")

        self.assertRegex(
            constants,
            r"inline constexpr uintptr_t kRoomDescriptorDecorationSeedOffset\s*=\s*0x64;")
        self.assertRegex(
            constants,
            r"inline constexpr uintptr_t kRoomDescriptorSpawnSeedOffset\s*=\s*0x68;")
        #: 与布局表生成物同名同值 ⇒ 两条 `static_assert` 钉住不许漂移。
        for name in ("DecorationSeed", "SpawnSeed"):
            self.assertRegex(
                remaining,
                rf"static_assert\(kRoomDescriptor{name}Offset\s*==\s*"
                rf"layout::kRoomDescriptor{name}Offset")

    def test_the_layout_rows_are_confirmed_with_named_evidence(self):
        """★ 布局表两行必须 `confirmed`，且证据里要有**那个能说明语义的具名读者**。"""
        import json

        table = json.loads(LAYOUT.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in table["rows"]}
        expected = {
            "DecorationSeed": (0x64, ["_ZN15IsaacRepentance4Room20LoadBackdropGraphicsEv"]),
            "SpawnSeed": (0x68,
                          ["_ZN15IsaacRepentance4Room4InitEPKNS_10RoomConfig4RoomEPNS_14RoomDescriptorE"]),
        }
        for name, (offset, functions) in expected.items():
            with self.subTest(row=name):
                self.assertIn(name, rows, f"布局表里没有 {name} 行")
                row = rows[name]
                self.assertEqual(row["confidence"], "confirmed")
                self.assertEqual(row["offset"], offset)
                self.assertEqual(row["width"], 4)
                kinds = [e["kind"] for e in row["evidence"]]
                self.assertIn("semantic", kinds)
                cited = [e["function"] for e in row["evidence"]]
                for function in functions:
                    self.assertIn(function, cited, f"{name} 行缺少 {function} 的证据")
                #: ★ 两行都要有 `GameState::write_Room` 的序列化证据（种子必须持久）。
                self.assertTrue(
                    any("write_Room" in e["function"] for e in row["evidence"]),
                    f"{name} 行缺少「会存档」的证据")

        #: 常量段要写下 PC 的标尺（两个绑定本体 + 两边的偏移）与关键具名读者。
        import re

        constants = CONSTANTS.read_text(encoding="utf-8")
        written = {int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", constants)}
        for va in (0x4977F0, 0x4276D0,          # PC 两个绑定本体
                   0x45ABF4, 0x45CCDC, 0x45CFB0, 0x45D280,   # Switch 侧的读者
                   0x3689A0, 0x3689D4):                      # 序列化
            self.assertIn(va, written, f"证据地址 {va:#x} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
