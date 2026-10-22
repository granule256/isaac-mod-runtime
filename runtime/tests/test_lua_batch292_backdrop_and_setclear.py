"""门禁：`Room:GetBackdropType()` + `Room:SetClear(boolean)`（批次 292，2026-10-02）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 新增机制 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Room:GetBackdropType()` | `Room.md:103` | 直读 `Room + 0x21B0`（内嵌 `Backdrop` 的 `eBackdrop`） | — （`U32` 行） | 5 |
| `Room:SetClear(boolean)` | `Room.md:772` | 读改写描述符 `Flags`（`+0x50`）的 **bit0** | `FieldKind::BoolBitWrite`（第一条**不返回值、有副作用**的行） | 6 |

★ 与本批同时落地的 **`BackdropType` 枚举表**（`tools/pc_enum_docs/BackdropType.md` →
`tools/generate_doc_enum_tables.py` 的 `TABLES` → `DocLuaEnumData`）是**同一件事的另一半**：
模组拿 `GetBackdropType()` 的返回值**以枚举值为键**建表/比较（`MusicModCallback/.../repentance.lua:431`
起 `[BackdropType.BASEMENT] = Music.MUSIC_BASEMENT`），少了表那一半，返回的数值仍然用不上。
与批次 269 的 `RenderMode` + `Room:GetRenderMode()` 逐字同形。

## 为什么 `Room+0x21B0` 是 `eBackdrop`（两条独立证据）

1. **内嵌关系**：`Room::LoadBackdropGraphics @ 0x45ABF8` 的 `mov w9,#0x1fe0` +
   `add x21,x20,x9` ⇒ `Backdrop` 子对象 = `Room+0x1FE0`；紧接着 0x45AC14 拿它当 `this`
   调 `Backdrop::Init`。
2. **写入方**：`Backdrop::Init(Backdrop::eBackdrop, bool) @ 0x26E80` 的
   `cmp w1,#0x3c`（0x26E9C）+ `csinc w8,w1,wzr,ls`（0x26EA4）+ `str w8,[x0,#0x1d0]`（0x26EA8）
   ⇒ eBackdrop ∈ `Backdrop+0x1D0`，且 **> 60 一律夹成 0**；两跳相加 `0x1FE0+0x1D0 = 0x21B0`。

取值锚点：`Room::pre_render_pits @ 0x47F034` 的 `cmp w8,#0x20`（32 = `BackdropType.MINES`）、
`Room::Init @ 0x45CC90` 的 `cmp w8,#0x10`（16 = `BackdropType.DARKROOM`）。
另有 14 个 `Room` 成员函数在读它（`--fn Room` 过滤后 48 处命中）。

## 为什么 `SetClear` **不走**引擎自己的 `Room::TriggerClear(bool)`

`Room::TriggerClear(bool) @ 0x470B58` 的整个函数体做的是**另一件事**：`orr w9,w9,#1`
**无条件**置 bit0（不看实参）、把描述符 `+0x56` 加一、`bl ScoreSheet::AddClearedRoom(...)`、
再在 `Game+0x26FA88 == 0x1f` 时走一串结算 ⇒ 拿它接 `SetClear` 会**静默多做一堆事**
（多记一次清房、多打一次分）。PC 的绑定本体（`0x497800`）只是
「读 `Flags` → 按实参置/清 **bit0** → 写回」，所以本批**自己做读改写**。

## 宿主验到了什么、没验到什么

* **验到**（字段行**没有入口指纹** ⇒ 伪造块里的字节真会被读出来 / 写进去）：
  - 背景类型：写什么读回什么（32 / 0 / 60 各一格），且返回的是**整数**；
  - ★ **枚举表真的挂上了**：Lua 里 `BackdropType.MINES == 32`、`BackdropType.BACKDROP_NULL == 0`
    （少了这一半，模组比较会静默失配）；
  - `SetClear(true)` / `SetClear(false)` **两个方向都生效**，且**同字里的 bit3 原样保留**
    （用批次 291 的 `IsAmbushDone()` 与批次 207 的 `IsClear()` 两个 API 交叉验证 ——
    同一个 32 位字里的 bit0 与 bit3）；
  - ★ **`SetClear(0)` 是"置位"不是"清位"**：PC 的绑定按 Lua 真值语义取参（0 在 Lua 里为真）
    ⇒ 本批只有个数闸门、没有类型闸门；
  - 拿不到当前房间 ⇒ `GetBackdropType()` 答 0、`SetClear` 什么都不做，**都不抛 Lua 错误**；
  - 参数闸门：`SetClear()` / `SetClear(true,true)` 报错；`GetBackdropType(1)` 报错。
* **没验**：真机上 `Room+0x21B0` 是不是背景类型、写描述符 `+0x50` 的 bit0 会不会被引擎
  自己的逻辑覆盖 —— 只有真机能看。⇒ 真机项 = 作业单 **V43**。
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
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
FIELD_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
LAYOUT_ROOM = ROOT / "tools" / "layout_tables" / "room.json"
ENUM_TOOL = ROOT / "tools" / "generate_doc_enum_tables.py"
ENUM_GATE = ROOT / "runtime" / "tests" / "test_lua_doc_enum_tables.py"

#: `(名字, 域内序号, 偏移常量, offset2, FieldKind, FieldMissing, FieldReceipt)`。
FIELD_APIS = (
    ("GetBackdropType", 0x002D, "kRoomBackdropTypeOffset", "0x00", "U32", "Zero", "Room"),
    ("SetClear", 0x002E, "kRoomDescriptorFlagsOffset", "0", "BoolBitWrite", "Zero",
     "RoomDescriptor"),
)

#: `BackdropType` 的三个值（来自 `tools/pc_enum_docs/BackdropType.md`）。
#: ★ `MINES = 32` 与 Switch 侧 `pre_render_pits` 里的 `cmp w8,#0x20` **同值** —— 这是
#: "返回值能与枚举表直接比"的硬证据（两边错开就是"永远不相等"这种最隐蔽的失效）。
BACKDROP_MINES = 32
BACKDROP_NULL = 0
BACKDROP_DARK_CLOSET = 60
#: 描述符 `Flags` 的位（批次 291/207 的语义）：bit0 = 已清房，bit3 = `CHALLENGE_DONE`。
CLEAR_BIT_VALUE = 0x01
CHALLENGE_DONE_BIT_VALUE = 0x08


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 伪造的引擎内存：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                              = &g_RoomBytes（"当前房间"）
//   g_RoomBytes [kRoomDescriptorPointerOffset]    = &g_DescriptorBytes
//   g_RoomBytes [kRoomBackdropTypeOffset]         = 背景类型
//   g_DescriptorBytes[kRoomDescriptorFlagsOffset] = Flags 位掩码（bit0 清房 / bit3 挑战已完成）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_DescriptorBytes;
bool g_RoomAvailable = true;

//: 房间块必须盖住背景类型那一格（本批最远的偏移）。
static_assert(kRoomBackdropTypeOffset + sizeof(std::uint32_t) <= 0x21B8,
              "fake room block must hold the backdrop type");
static_assert(kRoomDescriptorPointerOffset + sizeof(std::uint64_t) <= 0x21B8,
              "fake room block must hold the descriptor pointer");
static_assert(kRoomDescriptorFlagsOffset + sizeof(std::uint32_t) <= 0x80,
              "fake descriptor block must hold the Flags word");

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
    WriteAt<std::uint64_t>(g_RoomBytes, kRoomDescriptorPointerOffset,
                           AddressOf(g_DescriptorBytes));
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
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

std::uint32_t ReadFlagsWord() {
    std::uint32_t value = 0;
    std::memcpy(&value, g_DescriptorBytes.data() + kRoomDescriptorFlagsOffset, sizeof(value));
    return value;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    std::uint32_t backdrop = 32;      // = BackdropType.MINES
    std::uint32_t flags = 0x08;       // 只有 bit3（挑战已完成），bit0 是清的
    if (std::strcmp(scenario, "mines") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "null") == 0) {
        backdrop = 0;                 // = BackdropType.BACKDROP_NULL
    } else if (std::strcmp(scenario, "closet") == 0) {
        backdrop = 60;                // = BackdropType.DARK_CLOSET（引擎允许的最大真背景）
    } else if (std::strcmp(scenario, "noroom") == 0) {
        g_RoomAvailable = false;
    } else if (std::strcmp(scenario, "settrue") == 0) {
        // flags 默认 0x08 ⇒ bit0 清着，SetClear(true) 之后应当是 0x09。
    } else if (std::strcmp(scenario, "setfalse") == 0) {
        flags = 0x09;                 // bit0 与 bit3 都置着，SetClear(false) 之后应当是 0x08
    } else if (std::strcmp(scenario, "toggle") == 0) {
        flags = 0x08;                 // bit3 置着 ⇒ 可以在"连着两次写"之后断言它没被动过
    } else if (std::strcmp(scenario, "truthy") == 0) {
        flags = 0x00;                 // 用 `SetClear(0)`（Lua 里 0 为真 ⇒ 应当置位）
    } else if (std::strcmp(scenario, "args") == 0) {
        flags = 0x00;
    } else {
        return 91;
    }

    PublishFakeRoom();
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomBackdropTypeOffset, backdrop);
    WriteAt<std::uint32_t>(g_DescriptorBytes, kRoomDescriptorFlagsOffset, flags);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    // 脚本按场景分支 —— 每个场景只做自己那几次写，这样 C++ 侧那次
    // `rawflags` 读数的预期才是**干净的**（不掺别的场景留下的位）。
    const std::string script_text =
        std::string("local scenario = '") + scenario + "'\n"
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local room = Game():GetRoom()\n"
        "print('B292 roomkind=' .. type(room))\n"
        "print('B292 fn=' .. type(room.GetBackdropType) .. ',' .. type(room.SetClear))\n"
        // 枚举表：与 `Room:GetBackdropType()` 配对的另一半，必须真的挂上。
        "print('B292 enumtype=' .. type(BackdropType))\n"
        "print('B292 enum_mines=' .. tostring(BackdropType.MINES))\n"
        "print('B292 enum_null=' .. tostring(BackdropType.BACKDROP_NULL))\n"
        "print('B292 enum_closet=' .. tostring(BackdropType.DARK_CLOSET))\n"
        // 背景类型
        "local b = room:GetBackdropType()\n"
        "print('B292 bkind=' .. type(b))\n"
        "print('B292 backdrop=' .. tostring(b))\n"
        "print('B292 ismines=' .. tostring(b == BackdropType.MINES))\n"
        "print('B292 isnull=' .. tostring(b == BackdropType.BACKDROP_NULL))\n"
        "print('B292 iscloset=' .. tostring(b == BackdropType.DARK_CLOSET))\n"
        // 清房标志的读写两侧（同字里的 bit0 与 bit3）
        "print('B292 clear0=' .. tostring(room:IsClear()))\n"
        "print('B292 ambush0=' .. tostring(room:IsAmbushDone()))\n"
        // ★ `select('#', f(...))` 才是"这次调用返回了几个值"（`pcall` 外面数会多一个 `true`）。
        "local retcount = -1\n"
        "if scenario == 'settrue' or scenario == 'noroom' then\n"
        "  retcount = select('#', room:SetClear(true))\n"
        "  print('B292 set1=' .. ok(function() return room:SetClear(true) end))\n"
        "  print('B292 clear1=' .. tostring(room:IsClear()))\n"
        "  print('B292 ambush1=' .. tostring(room:IsAmbushDone()))\n"
        "elseif scenario == 'setfalse' then\n"
        "  retcount = select('#', room:SetClear(false))\n"
        "  print('B292 clear1=' .. tostring(room:IsClear()))\n"
        "  print('B292 ambush1=' .. tostring(room:IsAmbushDone()))\n"
        "elseif scenario == 'toggle' then\n"
        "  retcount = select('#', room:SetClear(true))\n"
        "  print('B292 clear1=' .. tostring(room:IsClear()))\n"
        "  print('B292 ambush1=' .. tostring(room:IsAmbushDone()))\n"
        "  room:SetClear(false)\n"
        "  print('B292 clear2=' .. tostring(room:IsClear()))\n"
        "  print('B292 ambush2=' .. tostring(room:IsAmbushDone()))\n"
        "elseif scenario == 'truthy' then\n"
        // ★ `SetClear(0)` —— 0 在 Lua 里为**真** ⇒ PC 上这是"置位"（见用例文件头那段）。
        "  retcount = select('#', room:SetClear(0))\n"
        "  print('B292 clear1=' .. tostring(room:IsClear()))\n"
        "  print('B292 ambush1=' .. tostring(room:IsAmbushDone()))\n"
        "elseif scenario == 'args' then\n"
        "  print('B292 noargs=' .. err(function() return room:SetClear() end))\n"
        "  print('B292 twoargs=' .. err(function() return room:SetClear(true, true) end))\n"
        "  print('B292 bdargs=' .. err(function() return room:GetBackdropType(1) end))\n"
        "  print('B292 dotcall=' .. ok(function() return room.GetBackdropType(room) end))\n"
        "end\n"
        "print('B292 retcount=' .. tostring(retcount))";

    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b292.lua");
    static_cast<void>(result);
    // ★ C++ 侧直接读伪造的描述符块：这是"真的写进去了"的**独立**证据
    //   （不依赖 Lua 侧的读数，也不依赖 `IsClear()` 的实现）。
    std::printf("B292 rawflags=0x%02X\n", ReadFlagsWord());
    return 0;
}
'''


class BackdropAndSetClearBatch292Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b292-")
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

    def test_the_backdrop_type_is_read_from_the_room_object(self):
        """★ 写什么读回什么（32 / 0 / 60 各一格），且返回的是**整数**。"""
        out = self.run_scenario("mines")
        self.assertIn("B292 roomkind=userdata", out)
        self.assertIn("B292 fn=function,function", out)
        self.assertIn("B292 bkind=number", out)
        self.assertIn("B292 backdrop=32", out)
        self.assertIn("B292 ismines=true", out)
        self.assertIn("B292 isnull=false", out)

        out_null = self.run_scenario("null")
        self.assertIn("B292 backdrop=0", out_null)
        self.assertIn("B292 isnull=true", out_null)

        out_closet = self.run_scenario("closet")
        self.assertIn("B292 backdrop=60", out_closet)
        self.assertIn("B292 iscloset=true", out_closet)
        #: 60 是引擎允许的最大真背景（`Backdrop::Init` 把 >60 夹成 0）⇒ 它是合法读数而不是降级。
        self.assertIn("B292 ismines=false", out_closet)

    def test_the_enum_table_half_is_actually_registered(self):
        """★★ `BackdropType` 枚举表必须真的挂上 —— 少了它，返回值也用不上。

        模组是**以枚举值为键**用它的（`MusicModCallback/.../repentance.lua:431` 起
        `[BackdropType.BASEMENT] = Music.MUSIC_BASEMENT`、`:467` 正是本 API 的调用点）。
        ★ 这里同时钉住"两边同值"：`BackdropType.MINES` 必须是 32，
        因为 Switch 侧 `Room::pre_render_pits` 用的就是 `cmp w8,#0x20`。
        """
        out = self.run_scenario("mines")
        self.assertIn("B292 enumtype=table", out)
        self.assertIn("B292 enum_mines=32", out)
        self.assertIn("B292 enum_null=0", out)
        self.assertIn("B292 enum_closet=60", out)

    def test_set_clear_writes_the_clear_bit_in_both_directions(self):
        """★★ `SetClear(true)` 置位、`SetClear(false)` 清位；**同字里的 bit3 不许被碰**。

        初始位图 `0x08`（只有 bit3）：`SetClear(true)` 之后应当是 `0x09`、
        `SetClear(false)` 之后回到 `0x08`。bit3 用批次 291 的 `IsAmbushDone()` 交叉验证 ——
        它就是同一个 32 位字的 bit3；若实现写成"整字覆盖"（`value = arg and 1`），
        bit3 会在第一次写就丢掉，这一条立刻红。
        ★ `rawflags` 是 C++ 侧直接读伪造内存得到的（不经过 Lua、也不经过 `IsClear()`），
        所以它把"真的写进去了"与"读法自洽"分开了。
        """
        out = self.run_scenario("settrue")
        self.assertIn("B292 clear0=false", out)
        self.assertIn("B292 ambush0=true", out)
        self.assertIn("B292 set1=true", out)
        self.assertIn("B292 clear1=true", out)
        self.assertIn("B292 ambush1=true", out)
        #: ★ 本场景只写了 `true` 一次（同一格幂等）⇒ 位图从 `0x08` 变 `0x09`。
        self.assertIn("B292 rawflags=0x09", out)

    def test_set_clear_false_clears_an_already_set_bit(self):
        """★ 初始位图 `0x09`（bit0 已置）⇒ `SetClear(false)` 之后必须是 `0x08`。

        与上一场合起来才说明"两个方向都真的写了"：单看"写 false 之后是 false"这一场，
        分不出"真的清了位"与"本来就是清的"。
        """
        out = self.run_scenario("setfalse")
        self.assertIn("B292 clear0=true", out)
        self.assertIn("B292 clear1=false", out)
        self.assertIn("B292 ambush1=true", out)
        #: 从 `0x09` 清成 `0x08` ⇒ bit0 被清、bit3 原样（这一条就是"真的清了位"的证据）。
        self.assertIn("B292 rawflags=0x08", out)

    def test_set_clear_zero_is_truthy_like_pc(self):
        """★★ `SetClear(0)` 是**置位** —— PC 的绑定按 Lua 真值语义取参（0 在 Lua 里为真）。

        PC 的绑定本体（`0x497800`）做的是 `cmp byte ptr [ebp+0x8], 0; cmove`，
        那个字节由胶水层的布尔转换填进来；`lua_toboolean` 只把 `false` / `nil` 当假
        ⇒ `SetClear(0)` 置位、`SetClear(false)` / `SetClear(nil)` 清位。
        ★ 本批因此**只闸个数、不闸类型**（写成"必须 LUA_TBOOLEAN"会比 PC 更严，
        会拒掉 PC 上本来能用的写法）。
        """
        out = self.run_scenario("truthy")
        self.assertIn("B292 clear0=false", out)
        self.assertIn("B292 clear1=true", out)
        self.assertIn("B292 rawflags=0x01", out)

    def test_set_clear_returns_no_values(self):
        """★ `Room:SetClear` 返回 **0 个值**（PC 返回 `void`）—— 本机制第一条不返回值的行。

        `pcall` 的返回值个数 = 成功标志 + 被调函数的返回值 ⇒ `SetClear(true)` 应当是 **2**
        （`true` + 0 个）。返回 1 个值（例如压了个 `nil`）会让模组那边多出一个占位。
        """
        out = self.run_scenario("settrue")
        self.assertIn("B292 retcount=0", out)

    def test_toggling_works_on_the_same_word(self):
        """★ 同一格上"置位 → 清位"连着来：两次都生效（抓"只写一次就缓存住了"这类实现）。"""
        out = self.run_scenario("toggle")
        self.assertIn("B292 clear0=false", out)
        self.assertIn("B292 clear1=true", out)
        self.assertIn("B292 clear2=false", out)
        #: ★ 连着写两次之后 bit3（同一字的另一位）仍在 ⇒ "整字覆盖"式实现会在这里红。
        self.assertIn("B292 ambush1=true", out)
        self.assertIn("B292 ambush2=true", out)
        self.assertIn("B292 rawflags=0x08", out)   # 置位再清位 ⇒ 回到初始的 0x08

    def test_no_current_room_degrades_without_erroring(self):
        """★ 拿不到当前房间 ⇒ `GetBackdropType()` 答 0、`SetClear` 什么都不做、**都不抛错**。"""
        out = self.run_scenario("noroom")
        self.assertIn("B292 roomkind=userdata", out)
        self.assertIn("B292 backdrop=0", out)
        self.assertIn("B292 set1=true", out)
        self.assertIn("B292 clear1=false", out)
        #: 房间块里的位图**没被改动**（初始 0x08）—— 拿不到房间时一个字节都不落。
        self.assertIn("B292 rawflags=0x08", out)

    def test_argument_gates(self):
        """★ 参数闸门：`SetClear` **恰好两个值**（接收者 + 一个实参）；`GetBackdropType` 恰好一个。"""
        out = self.run_scenario("args")
        self.assertIn("Room:SetClear expects one argument", out)
        self.assertIn("Room:GetBackdropType accepts no arguments", out)
        #: 点号 + 显式 self 也是 1 个参数 ⇒ 放行（读侧）。
        self.assertIn("B292 dotcall=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 种类与降级档 / 接收者 / 偏移常量。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, offset_name, offset2, kind, missing, receipt in FIELD_APIS:
            with self.subTest(api=f"Room:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Room, 1, 0x{index:04X}), ApiDomain::Room, "Room", "{name}"',
                    catalog, f"目录里没有 Room:{name}")
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0401{index:04x}),\s*{offset_name},\s*{offset2},\s*"
                    rf"FieldKind::{kind},\s*FieldMissing::{missing},\s*"
                    rf"FieldReceipt::{receipt},\s*0xFF\}}",
                    f"数据行缺失或形状/降级档/接收者不对：Room:{name}")
                #: ★ 反回归：不许塞进引擎方法行表（`SetClear` 尤其容易被误当成
                #:   "调 `Room::TriggerClear(bool)` 就行"，见文件头那段理由）。
                self.assertNotRegex(remaining, rf"0x0401{index:04x}[^\n]*EngineCallShape")

        self.assertRegex(constants,
                         r"inline constexpr uintptr_t kRoomBackdropTypeOffset\s*=\s*0x21B0;")
        self.assertRegex(
            remaining,
            r"static_assert\(kRoomBackdropTypeOffset\s*==\s*layout::kRoomBackdropTypeOffset")

    def test_the_new_kind_exists_and_is_implemented(self):
        """★ 新种类 `BoolBitWrite` 必须**真的实现**：写那一位、**返回 0 个值**。"""
        field_api = FIELD_API.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")

        self.assertRegex(field_api, r"BoolBitWrite\s*=\s*11")
        self.assertRegex(isaac, r"case\s+FieldKind::BoolBitWrite\s*:")
        #: 真的按"那一位"置/清（`| mask` / `& ~mask`），不是整字覆盖。
        self.assertRegex(isaac, r"value\s*\|\s*mask")
        self.assertRegex(isaac, r"value\s*&\s*~mask")
        #: 写侧要走"先确认可写再写"那条原语（与 Game/Entity/Sprite 的写入口同一形态）。
        self.assertRegex(isaac, r"WriteField\(receiver,\s*row->offset,\s*updated")
        #: 位号越界 / 读不到 ⇒ 什么都不写、不抛错。
        self.assertRegex(isaac, r"row->offset2\s*>=\s*32")
        #: 参数口径：`BoolBitWrite` 只闸个数（`lua_toboolean` 语义），不与
        #: `U64FlagsAllSet` 的"必须是整数"混在一起。
        self.assertRegex(isaac, r"lua_toboolean\(state,\s*2\)")

    def test_the_layout_row_and_the_evidence_are_recorded(self):
        """★ 布局表 `BackdropType` 行必须 `confirmed` 且带语义锚点；常量段要写下证据链。"""
        import json

        table = json.loads(LAYOUT_ROOM.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in table["rows"]}
        self.assertIn("BackdropType", rows)
        row = rows["BackdropType"]
        self.assertEqual(row["confidence"], "confirmed")
        self.assertEqual(row["offset"], 0x21B0)
        self.assertEqual(row["width"], 4)
        kinds = [e["kind"] for e in row["evidence"]]
        self.assertIn("semantic", kinds)
        self.assertGreaterEqual(kinds.count("access"), 4)
        functions = [e["function"] for e in row["evidence"]]
        #: 内嵌关系那一跳（`Room + 0x1FE0`）与写入方（`Backdrop::Init`）都必须在表里。
        self.assertIn("_ZN15IsaacRepentance8Backdrop4InitENS0_9eBackdropEb", functions)
        self.assertIn("_ZN15IsaacRepentance4Room20LoadBackdropGraphicsEv", functions)
        self.assertIn("_ZNK15IsaacRepentance4Room7HasLavaEv", functions)

        constants = CONSTANTS.read_text(encoding="utf-8")
        folded = constants.lower()
        #: PC 侧的标尺 + 两条 Switch 侧锚点 + 那条"为什么不走 TriggerClear"的否定结论。
        for va in ("0x4baea0", "0x45abf8", "0x45ae1c", "0x26e80", "0x470b58"):
            self.assertIn(va, folded, f"证据地址 {va} 没有写进常量段")
        self.assertIn("0x1fe0", folded)
        self.assertIn("0x21b0", folded)

    def test_the_enum_table_half_is_wired_into_the_generator_and_the_gate(self):
        """★ 枚举表那一半的四处接线：文档页 / 生成器 `TABLES` / 重复键登记 / 门禁清单。

        与批次 269 的 `RenderMode` 同形 —— 「API + 枚举表」是**同一件事的两半**，
        只做一半等于没做（返回值拿不到可比的常量）。
        """
        tool = ENUM_TOOL.read_text(encoding="utf-8")
        page = ROOT / "tools" / "pc_enum_docs" / "BackdropType.md"
        self.assertTrue(page.is_file(), "契约快照里没有 BackdropType.md")
        self.assertIn('"BackdropType",', tool)
        #: ★ 这一页**有重复键** `NUM_BACKDROPS`（AB 档 61 / Rep+ 档 63）⇒ 必须按规程登记，
        #:   否则生成器会响亮失败（"没登记的重复键一律判错"是它的设计）。
        self.assertIn('"BackdropType.NUM_BACKDROPS"', tool)
        gate = ENUM_GATE.read_text(encoding="utf-8")
        self.assertIn('"BackdropType"', gate)
        self.assertIn('"BackdropType": 64', gate)
        self.assertIn('("BackdropType", "MINES"): 32', gate)


if __name__ == "__main__":
    unittest.main()
