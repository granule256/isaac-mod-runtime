"""门禁：`Room:SetFloorColor(Color)` / `Room:SetWallColor(Color)`（批次 302，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧字段 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Room:SetFloorColor(Color)` | `Room.md:783` | `Room + 0x7968` 的 **44 字节 `ColorMod`** | 字段行 `ColorModWrite` / 返回 0 值 | 9 |
| `Room:SetWallColor(Color)` | `Room.md:834` | `Room + 0x7994` 的 **44 字节 `ColorMod`** | 同上 | 9 |

两条都是「把 `Color` 句柄转成 44 字节 `ColorMod`、整块写进 `Room` 上一个成员」——
PC 的绑定本体各只有 12 条指令（`add ecx,0x7188` / `add ecx,0x71b4` 之后一串
`movups/movq/mov`，`ret 0x2c`），**没有任何别的副作用** ⇒ 走**字段数据行**（0 字节代码）。

## 这两格凭什么就是地板 / 墙（三条独立证据，详见 `runtime_constants.hpp` 的批次 302 段）

1. **构造函数把它当 `ColorMod` 初始化**：`Room::Room() @ 0x44E75C` 用引擎自己的
   `ColorMod::Reset()` 作用在 `Room+0x7968`，紧接着 `0x44E768` 对 `Room+0x7994` 做同一件事
   ⇒ 两格同类型、**相距 `0x2C` = 一个 `ColorMod`**（与 PC 的 `0x7188`/`0x71B4` 间距一致）；
2. **具名读者 = 真的把它画出去的那条链**：`Room::Render` 把 `Room+0x7968` 的 44 字节**原样**
   喂给 `Backdrop::RenderFloor(Vector2 const&, ColorMod)`、把 `Room+0x7994` 的喂给
   `Backdrop::RenderWalls(Vector2 const&, ColorMod)` ⇒ 「地板」「墙」这两个名字来自**引擎自己的渲染调用**；
3. **引擎自己的「房间变金」** `Room::TurnGold` 写的是 `Room+0x7994` ⇒ 变金染的是**墙**。

★ 与 PC 的对应：PC `SetFloorColor` = `+0x7188`、`SetWallColor` = `+0x71B4`（也是相距 `0x2C`、
地板在前）⇒ **相对关系互相印证**；**绝对数值不许平移**。

## 宿主验到了什么、没验到什么

* **验到**（字段行没有入口指纹 ⇒ 伪造内存里的字节真被写）：
  - ★★ **写进去的就是「传进来的那份颜色」**：读回那 44 字节 —— tint = rgba、shift 前三格 = ro/go/bo、
    shift 第 4 格与三个保留格 = 0（★ 专抓「只写 tint 忘了 shift」「漏写保留格」）；
  - ★★ **两块互不串扰**：只写地板之后墙那一格 44 字节**一个字节都不变**（★ 专抓「偏移写成相邻那一格」——
    两格只差 `0x2C`，这是本批最可能的错法）；
  - ★ **两次调用按顺序生效**（整块覆盖写，不是叠加）；
  - **拿不到当前房间 ⇒ 什么都不写、不抛错、返回 0 个值**；
  - **参数闸门**：少给/多给都报错；传非 `Color` 也报错；点号显式 self 放行；
  - 布局表两行 `confirmed` + `--verify` 重新反汇编核对。
* **没验**：真机上这两格是不是就是地板/墙色（宿主里「偏移对不对」是同一张表的两处引用同一个常量，
  自己证不了自己）以及真机上的观感 ⇒ 真机项 = 作业单 **V52**。
"""

import json
import re
import struct
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
REMAINING = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
ISAAC = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
LAYOUT_ROOM = ROOT / "tools" / "layout_tables" / "room.json"
LAYOUT_TOOL = ROOT / "tools" / "build_layout_table.py"

#: 本批两条 API 的目录序号 / 偏移常量 / 偏移值 / 布局表行名。
APIS = (
    ("SetFloorColor", 0x0031, "kRoomFloorColorModOffset", 0x7968, "FloorColorMod"),
    ("SetWallColor", 0x0032, "kRoomWallColorModOffset", 0x7994, "WallColorMod"),
)

#: 夹具里两次调用各自传的 `Color(r,g,b,a, ro,go,bo)`（互不相同 ⇒ 读错格/串扰都会红）。
FLOOR_RGBA = (0.25, 0.5, 0.75, 1.0)
FLOOR_OFFSET = (0.1, 0.2, 0.3)
WALL_RGBA = (1.0, 0.0, 0.0, 1.0)
WALL_OFFSET = (-0.1, -0.2, -0.3)
#: 第二次 `SetFloorColor` 用的另一份颜色（验「整块覆盖写」）。
FLOOR2_RGBA = (0.125, 0.25, 0.375, 0.5)
FLOOR2_OFFSET = (-0.4, -0.5, -0.6)


def f32(value: float) -> int:
    """`float32` 的位模式 —— 用例按**逐位**比对，避开浮点打印的歧义。"""
    return struct.unpack("<I", struct.pack("<f", value))[0]


def words_of(rgba, offset):
    """`Color(r,g,b,a, ro,go,bo)` 写进 `ColorMod` 之后的 11 个 `float32` 位模式：
    tint(4) + colorize(4，全 0) + offset(3)，2026-10-10 据具名 setter 更正。"""
    return tuple(f32(v) for v in (*rgba, 0.0, 0.0, 0.0, 0.0, *offset))


FLOOR_WORDS = words_of(FLOOR_RGBA, FLOOR_OFFSET)
WALL_WORDS = words_of(WALL_RGBA, WALL_OFFSET)
FLOOR2_WORDS = words_of(FLOOR2_RGBA, FLOOR2_OFFSET)
#: `ColorMod::Reset` 的默认（= 夹具里没被动过的那一格应当长这样）。
DEFAULT_WORDS = words_of((1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0))


def color_ctor(rgba, offset) -> str:
    return "Color({})".format(", ".join(repr(float(v)) for v in (*rgba, *offset)))


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 伪造的引擎内存（形状抄批次 292 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                          = &g_RoomBytes（"当前房间"）
//   g_RoomBytes[kRoomFloorColorModOffset]     = 44 字节的地板 ColorMod（本批写）
//   g_RoomBytes[kRoomWallColorModOffset]      = 44 字节的墙   ColorMod（本批写）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
bool g_RoomAvailable = true;

//: 房间块必须盖住两个 ColorMod 的末尾（`0x7994 + 44 = 0x79C0`）。
static_assert(kRoomWallColorModOffset + kColorModSize <= 0x79C0,
              "fake room block must hold both ColorMods");
//: ★ 两格必须**正好相邻一个 `ColorMod`** —— 这是本批"与 PC 的那对相对关系"的编译期版本。
static_assert(kRoomFloorColorModOffset + kColorModSize == kRoomWallColorModOffset,
              "两格应当正好相差一个 ColorMod（0x2C）");

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
    g_RoomBytes.assign(0x79C0, 0);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset,
                           AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
    // 两格按 `ColorMod::Reset` 的默认摆好（tint 全 1、其余 0）—— "没被动过"就有可断言的基线。
    const std::uint32_t one = 0x3F800000U;
    for (std::size_t i = 0; i < 4; ++i) {
        WriteAt<std::uint32_t>(g_RoomBytes, kRoomFloorColorModOffset + i * 4, one);
        WriteAt<std::uint32_t>(g_RoomBytes, kRoomWallColorModOffset + i * 4, one);
    }
}

//: 把某一格 44 字节按 11 个 `float32` 的**位模式**打出来（逐位比对，不受浮点打印影响）。
void DumpColorMod(const char* label, std::size_t offset) {
    std::printf("%s", label);
    for (std::size_t i = 0; i < kColorModSize / 4; ++i) {
        std::uint32_t word = 0;
        std::memcpy(&word, g_RoomBytes.data() + offset + i * 4, sizeof(word));
        std::printf(" %08X", word);
    }
    std::printf("\n");
}

void Substitute(std::string& text, const std::string& needle, const std::string& value) {
    for (std::size_t position = text.find(needle); position != std::string::npos;
         position = text.find(needle, position + value.size())) {
        text.replace(position, needle.size(), value);
    }
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    if (!g_RoomAvailable) {
        *room = nullptr;
        return GameRoomObservation::GameNull;
    }
    *room = g_RoomBytes.data();
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    if (std::strcmp(scenario, "noroom") == 0) {
        g_RoomAvailable = false;
    } else if (std::strcmp(scenario, "colors") != 0 && std::strcmp(scenario, "flooronly") != 0 &&
               std::strcmp(scenario, "twice") != 0 && std::strcmp(scenario, "args") != 0) {
        return 91;
    }

    PublishFakeRoom();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    std::string script_text =
        std::string("local scenario = '") + scenario + "'\n"
        // ★ 占位符用 `CLR`/`FLOORCLR`/`WALLCLR`/`FLOOR2CLR`（**刻意不含 `C`+`olor` 这种组合**，
        //   免得替换时误伤 `Color(` 本身）。
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local room = Game():GetRoom()\n"
        "print('B302 roomkind=' .. type(room))\n"
        "print('B302 fn=' .. type(room.SetFloorColor) .. ',' .. type(room.SetWallColor))\n"
        "if scenario == 'colors' or scenario == 'noroom' then\n"
        "  print('B302 retF=' .. select('#', room:SetFloorColor(FLOORCLR)))\n"
        "  print('B302 retW=' .. select('#', room:SetWallColor(WALLCLR)))\n"
        "elseif scenario == 'flooronly' then\n"
        "  print('B302 retF=' .. select('#', room:SetFloorColor(FLOORCLR)))\n"
        "elseif scenario == 'twice' then\n"
        "  room:SetFloorColor(FLOORCLR)\n"
        "  print('B302 ret2=' .. select('#', room:SetFloorColor(FLOOR2CLR)))\n"
        "elseif scenario == 'args' then\n"
        "  print('B302 noargs=' .. ok(function() return room:SetFloorColor() end))\n"
        "  print('B302 noargsmsg=' .. err(function() return room:SetFloorColor() end))\n"
        "  print('B302 twoargs=' .. ok(function() return room:SetFloorColor(CLR, CLR) end))\n"
        "  print('B302 numarg=' .. ok(function() return room:SetFloorColor(1) end))\n"
        "  print('B302 nilarg=' .. ok(function() return room:SetFloorColor(nil) end))\n"
        "  print('B302 tabarg=' .. ok(function() return room:SetWallColor({}) end))\n"
        "  print('B302 tabargmsg=' .. err(function() return room:SetWallColor({}) end))\n"
        "  print('B302 dotcall=' .. ok(function() return room.SetFloorColor(room, CLR) end))\n"
        "  print('B302 wallnoargs=' .. ok(function() return room:SetWallColor() end))\n"
        "end\n";
    // ★ 先换**更长的**占位符（`FLOOR2CLR`/`FLOORCLR`/`WALLCLR` 之后才是 `CLR`），
    //   否则 `CLR` 会把前三个也拆掉。
    Substitute(script_text, "FLOOR2CLR", FLOOR2_LITERAL);
    Substitute(script_text, "FLOORCLR", FLOOR_LITERAL);
    Substitute(script_text, "WALLCLR", WALL_LITERAL);
    Substitute(script_text, "CLR", FLOOR_LITERAL);

    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b302.lua");
    static_cast<void>(result);
    // ★ C++ 侧直接读伪造的房间块：这是"真的写进去了"的**独立**证据（不依赖 Lua 侧读数）。
    DumpColorMod("B302 floor=", kRoomFloorColorModOffset);
    DumpColorMod("B302 wall=", kRoomWallColorModOffset);
    return 0;
}
'''
# 夹具里那几份颜色由 Python 侧注进来（单一真值来源）。
HARNESS = (HARNESS
           .replace("FLOOR2_LITERAL", '"' + color_ctor(FLOOR2_RGBA, FLOOR2_OFFSET) + '"')
           .replace("FLOOR_LITERAL", '"' + color_ctor(FLOOR_RGBA, FLOOR_OFFSET) + '"')
           .replace("WALL_LITERAL", '"' + color_ctor(WALL_RGBA, WALL_OFFSET) + '"'))


class RoomColorsBatch302Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b302-")
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
    def words(out, label):
        match = re.search(rf"^{re.escape(label)}=((?: [0-9A-F]{{8}})+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return tuple(int(word, 16) for word in match.group(1).split())

    # ---------------------------------------------------------------- 行为（宿主）

    def test_writes_the_given_color_into_the_receiver_itself(self):
        """★★ 写进去的就是**传进来的那份颜色**（tint = rgba、shift 前三格 = ro/go/bo、其余 0）。

        ★ 专抓「只写 tint 忘了 shift」与「漏写保留格」两类错法：两份颜色在 shift 上完全不同，
        22 个位模式逐位比对。
        """
        out = self.run_scenario("colors")
        self.assertIn("B302 roomkind=userdata", out)
        self.assertIn("B302 fn=function,function", out)
        self.assertEqual(self.words(out, "B302 floor"), FLOOR_WORDS)
        self.assertEqual(self.words(out, "B302 wall"), WALL_WORDS)
        self.assertIn("B302 retF=0", out)
        self.assertIn("B302 retW=0", out)

    def test_the_two_color_mods_do_not_bleed_into_each_other(self):
        """★★ 只写地板 ⇒ 墙那一格 44 字节**一个字节都不许变**。

        ★ 两格只差 `0x2C` ⇒ 「偏移写成相邻那一格」是本批最可能的错法；这一条就是为它写的。
        """
        out = self.run_scenario("flooronly")
        self.assertEqual(self.words(out, "B302 floor"), FLOOR_WORDS)
        self.assertEqual(self.words(out, "B302 wall"), DEFAULT_WORDS,
                         "写地板串到了墙那一格（或墙那一格被顺带改写）")
        self.assertIn("B302 retF=0", out)

    def test_second_call_overwrites_instead_of_accumulating(self):
        """★ 两次 `SetFloorColor` ⇒ 读回的是**第二次**那份（PC 是整块覆盖写，不是叠加）。"""
        out = self.run_scenario("twice")
        self.assertEqual(self.words(out, "B302 floor"), FLOOR2_WORDS)
        self.assertEqual(self.words(out, "B302 wall"), DEFAULT_WORDS)
        self.assertIn("B302 ret2=0", out)

    def test_no_room_writes_nothing_and_returns_zero_values(self):
        """★ 拿不到当前房间 ⇒ 什么都不写、**不抛错**、返回 **0 个值**。"""
        out = self.run_scenario("noroom")
        self.assertEqual(self.words(out, "B302 floor"), DEFAULT_WORDS)
        self.assertEqual(self.words(out, "B302 wall"), DEFAULT_WORDS)
        self.assertIn("B302 retF=0", out)
        self.assertIn("B302 retW=0", out)

    def test_argument_gate(self):
        """参数闸门：**恰好两个**（接收者 + 一个 `Color`），非 `Color` 一律拒。"""
        out = self.run_scenario("args")
        self.assertIn("B302 noargs=false", out)
        self.assertIn("Room:SetFloorColor expects a Color", out)
        self.assertIn("B302 twoargs=false", out)
        self.assertIn("B302 numarg=false", out)
        self.assertIn("B302 nilarg=false", out)
        self.assertIn("B302 tabarg=false", out)
        self.assertIn("Room:SetWallColor expects a Color", out)
        self.assertIn("B302 wallnoargs=false", out)
        #: ★ 点号显式传 self 是合法写法（1 个接收者 + 1 个 `Color`），不许被拒。
        self.assertIn("B302 dotcall=true", out)
        #: 被拒的调用**一个字节都不许写**：这一场里唯一成功的调用是那句点号写法
        #: （`room.SetFloorColor(room, CLR)`）⇒ 地板 = 那份颜色、**墙仍是默认**。
        self.assertEqual(self.words(out, "B302 floor"), FLOOR_WORDS)
        self.assertEqual(self.words(out, "B302 wall"), DEFAULT_WORDS)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 种类 / 接收者 / 偏移常量 / 新 kind / 布局表生成物。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING.read_text(encoding="utf-8")
        isaac = ISAAC.read_text(encoding="utf-8")
        header = FIELD_HEADER.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, offset_name, offset, _row in APIS:
            with self.subTest(api=f"Room:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Room, 1, 0x{index:04X}), ApiDomain::Room, "Room", "{name}"',
                    catalog, f"目录里没有 Room:{name}")
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0401{index:04x}),\s*{offset_name},\s*(?:0x00|0),\s*"
                    rf"FieldKind::ColorModWrite,\s*FieldMissing::Zero,\s*FieldReceipt::Room,\s*0xFF\}}",
                    f"数据行缺失或形状/接收者不对：Room:{name}")
                self.assertRegex(constants,
                                 rf"inline constexpr uintptr_t {offset_name}\s*=\s*0x{offset:X};")
                #: ★ 反回归：不许被塞进引擎方法行表（引擎里没有同名访问器）。
                self.assertNotRegex(remaining, rf"0x0401{index:04x}[^\n]*EngineCallShape")
                #: 布局表生成物与本文件的常量必须同值（编译期钉住）。
                self.assertRegex(remaining, rf"static_assert\({offset_name} == layout::{offset_name},")

        #: 新 kind 必须在 `field_api.hpp` 里带说明地登记。
        self.assertRegex(header, r"ColorModWrite\s*=\s*15,")
        #: 共享处理器要认它：参数闸（`Color` 句柄）+ 那个 case + "返回 0 个值"的早退分支。
        self.assertIn("wantsColorModArgument", isaac)
        self.assertIn("case FieldKind::ColorModWrite", isaac)
        self.assertIn("FillEngineColorMod(state, 2, &value)", isaac)
        self.assertRegex(isaac, r"RowReturnsNoValues\(FieldKind kind\)[\s\S]{0,400}ColorModWrite")

    def test_layout_rows_are_confirmed_with_named_consumers(self):
        """★ 布局表两行必须 `confirmed`，且带**具名**写入方 / 读者与语义锚点。"""
        table = json.loads(LAYOUT_ROOM.read_text(encoding="utf-8"))
        self.assertEqual(table["struct"], "Room")
        rows = {row["name"]: row for row in table["rows"]}
        expected = {
            "FloorColorMod": (0x7968, [
                "_ZN15IsaacRepentance4RoomC2Ev",
                "_ZN15IsaacRepentance4Room4InitEPKNS_10RoomConfig4RoomEPNS_14RoomDescriptorE",
                "_ZN15IsaacRepentance4Room6RenderEv",
                "_ZN15IsaacRepentance8ColorMod5ResetEv"]),
            "WallColorMod": (0x7994, [
                "_ZN15IsaacRepentance4RoomC2Ev",
                "_ZN15IsaacRepentance4Room4InitEPKNS_10RoomConfig4RoomEPNS_14RoomDescriptorE",
                "_ZN15IsaacRepentance4Room6RenderEv",
                "_ZN15IsaacRepentance4Room8TurnGoldEv",
                "_ZN15IsaacRepentance8ColorMod5ResetEv"]),
        }
        for name, (offset, functions) in expected.items():
            with self.subTest(row=name):
                self.assertIn(name, rows, f"布局表里没有 {name} 行")
                row = rows[name]
                self.assertEqual(row["confidence"], "confirmed")
                self.assertEqual(row["offset"], offset)
                self.assertEqual(row["width"], 44)
                kinds = [entry["kind"] for entry in row["evidence"]]
                self.assertIn("semantic", kinds, f"{name} 行缺少取值锚点（semantic 证据）")
                cited = [entry["function"] for entry in row["evidence"]]
                for function in functions:
                    self.assertIn(function, cited, f"{name} 行缺少 {function} 的证据")

    def test_layout_evidence_reproduces_against_the_fixed_nro(self):
        """布局表的每条证据都要能重新反汇编核对（`--verify`）。"""
        nro = ROOT / (
            "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
            "/Program #0/1/.nro/Repentance.nro")
        if not nro.is_file():
            self.skipTest("仓库里没有游戏镜像（公开仓库不带游戏资源）")
        result = subprocess.run(
            ["python3", str(LAYOUT_TOOL), "--table", str(LAYOUT_ROOM), "--verify"],
            text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("通过", result.stdout)

    def test_the_two_offsets_are_one_color_mod_apart_like_on_pc(self):
        """★★ 「相距 `0x2C`、地板在前」是**与 PC 互相印证**的那一对关系（PC `0x7188`/`0x71B4`）。

        绝对数值在两边不同（布局差异、**不许平移**）⇒ 这条只钉相对关系 ——
        正是它让「这两格」在两个镜像之间对上号。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        floor = int(re.search(r"kRoomFloorColorModOffset\s*=\s*(0x[0-9A-Fa-f]+);",
                              constants).group(1), 16)
        wall = int(re.search(r"kRoomWallColorModOffset\s*=\s*(0x[0-9A-Fa-f]+);",
                             constants).group(1), 16)
        self.assertEqual(wall - floor, 0x2C, "两格应当正好相差一个 ColorMod")
        self.assertLess(floor, wall, "地板在墙前面（与 PC 的 0x7188 < 0x71B4 同序）")


if __name__ == "__main__":
    unittest.main()
