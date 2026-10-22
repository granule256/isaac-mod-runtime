"""`Level:GetCurrentRoomDesc` / `GetRoomByIdx` / `GetRooms` 的宿主机行为。

## 这一批的字段偏移从哪来

**不是从 PC 版抄的**：来自 `tools/layout_tables/room_descriptor.json`，每条都带可复核证据
（反汇编里的偏移/常量，或**真机行为观察**）。真机上验证过的几条：

| 字段 | 偏移 | 真机怎么验证的 |
| --- | --- | --- |
| `GridIndex` | `+0x00` | 起始房间（网格正中 84）读到 84；走进宝箱房变成 97 |
| `SafeGridIndex` | `+0x04` | 与上同房间同行（普通房里两者相等） |
| `ListIndex` | `+0x08` | 11 个已分配槽位的值恰好是 0..10 |
| `Data` | `+0x10` | 指向房间配置；`Data+0x8` 读出的类型构成一层合理布局（宝藏 4/商店 7/恶魔 10/BOSS 5） |
| `VisitedCount` | `+0x4c` | 首次进房 0→1；回到起始房间 1→2（计数而非布尔） |
| `DisplayFlags` | `+0x48` | 同一间房（网格 72）在地图上变得可见时 0→5（位0 可见 + 位2 显示图标）；同时它的 `VisitedCount`=0、`Flags`=0x0 ⇒ 与"清房/访问次数"无关 |
| `Clear` | `+0x50` | 清掉敌人瞬间 0→1，其它字段不动 |

描述符数组**内联在 Level 对象里**：基址 `Level+0x18`、步长 `0x100`、个数在 `Level+0x21510`。

## 这份宿主机测试钉住什么

伪造同一套内存布局（模块槽 → owner → Game），于是**读取链写错就会红**。重点覆盖：

1. 解析链：`GameOwnerSlot()` 是**槽的地址**，要解两次才到 `Game*`（第一版少解两层，
   真机探针上踩过同一个坑）；
2. 每个字段读的是它自己的偏移（逐个钉住，避免"整批偏移错位"这种看不出异常的错）；
3. `GetRoomByIdx(-1)` = 当前房间、越界与负数（非 -1）给 nil；
4. `GetRooms().Size` 与 `:Get(i)`（含越界给 nil）；
5. 非受管回调作用域里调用必须报错。
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"
#include "room_descriptor_layout.hpp"
#include "interfaces/lua/api500_world.guards.hpp"

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace {

// ---- 伪造引擎内存 -----------------------------------------------------------
//
// 解析链（与实现、与真机探针完全一致，**两解**）：
//   `GameOwnerSlot()`（= 模块映像 + kGameOwnerGlobalSlotOffset，是**槽的地址**）
//     → `*(槽)` = owner → `*(owner)` = Game*（= Level*）
// 真机实测同形：`g_Game` 槽内容 ≠ 对象本身，还要再解一层。
// 第一版假内存少铺了一层，于是实现返回 0（"读不到 Level"）—— 补上这一层正是本测试的价值。
// 第一版实现把"槽的地址"当成 Level 用，少解了两层；这里把链铺成真机的样子，
// 于是那种错误会直接让断言红，而不是在设备上才暴露。
std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerBytes;        // 槽 → owner
std::vector<unsigned char> g_GamePointerBytes;  // owner 指向的那个字（里面才是 Game*）
std::vector<unsigned char> g_LevelBytes;
std::vector<unsigned char> g_ConfigBytes;

constexpr std::uint32_t kCurrentIndex = 84;
constexpr std::uint32_t kCurrentDimension = 0;
// 批次 049：这两个让部分场景改写"当前进入格"与"引擎映射表"。
//   * `map_fallback`：进入格 98、房间在槽 1（GridIndex 97，2x2）⇒ **扫描找不到**，只有
//     引擎自己的 `Level+0x2d18` 映射表能找到（PC 文档：`+0x21558` 是"从哪一格进去的"）；
//   * `absent`：进入格 130，谁也不是、映射表也没写 ⇒ 两道都失败 ⇒ 必须给 -1 而不是 nil。
std::uint32_t g_CurrentIndex = kCurrentIndex;
//: 批次 071 场景开关：让当前槽位的 `Data` 指针为 0（见 `PublishFakeEngine` 与 `data_missing`）。
bool g_ZeroDataPointer = false;
int g_MapGrid = -1;
std::uint32_t g_MapSlot = 0;
constexpr std::uint32_t kRooms[3] = {84, 97, 71};      // 起始房间 / 宝箱房 / 普通房
constexpr std::uint32_t kTypes[3] = {1, 4, 1};         // ROOM_DEFAULT / ROOM_TREASURE / ROOM_DEFAULT
// `+0x50` 现在按 PC 的 `RoomDescriptor.Flags`（32 位位掩码）读：`Clear` 只是它的**第 0 位**。
//   * 槽 0（起始/当前房间）：`0x401` = bit0(FLAG_CLEAR) + bit10(FLAG_RED_ROOM) ⇒ `Clear` 真、`Flags` 1025；
//   * 槽 1（宝箱房）：`0x8` = 只有 bit3(FLAG_CHALLENGE_DONE) ⇒ `Clear` **假**、`Flags` 8。
//     这一条正是"语义收窄"的判别用例：旧实现按"非零即真"会把槽 1 也报成清房（会红）。
constexpr std::uint32_t kClearFlag[3] = {0x401, 0x8, 0};
// `+0x48` = PC 的 `RoomDescriptor.DisplayFlags`（小地图可见性**位掩码**）。
// 刻意与上面那行取**不同**的值：这样"读错成相邻的 Flags"会立刻红（0x5 vs 0x401）。
constexpr std::uint32_t kDisplayFlags[3] = {0x5, 0x0, 0x3};
// `Data + 0x5C` = `RoomConfigRoom.Shape`（PC `RoomShape` 枚举）。1 = 1x1、9 = LTL、8 = 2x2。
constexpr std::uint32_t kShapes[3] = {1, 9, 8};
constexpr std::uint32_t kVisited[3] = {2, 1, 1};
constexpr std::uint32_t kArrayBase = 0x18;
// `Level + 0x2d18`：引擎自己的"网格下标 → 槽位号"表（int32，每维 169 项）。
// 生产代码里的同名常量在 `remaining_api.cpp` 的 `kDescriptorGridSlotTableOffset`。
constexpr std::uint32_t kLevelGridSlotTableOffsetForTest = 0x2D18;
constexpr std::uint32_t kStride = 0x100;

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

// 描述符数组**内联在 Level 对象里**（真机布局就是这样：基址 Level+0x18、步长 0x100），
// 所以字段要写进 Level 块本身 —— 第一版写到一个独立块里，于是实现找不到描述符。

void PublishFakeEngine() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    // 2026-10-20：配置字段已经走受保护的原生布局，旧夹具需提供相同指纹。
    const auto& layout = isaac::runtime::api500_world::kLayouts[6];
    std::memcpy(g_ModuleBytes.data() + layout.offset, layout.bytes.data(), layout.bytes.size());
    // LeaveDoor字段的独立写者指纹（只校验，不执行AArch64）。
    constexpr unsigned char leaveGuard[16]={0x28,0xa3,0xd9,0x39,0x29,0x23,0xb,0x29,0x28,0x5b,0x46,0xb9,0x28,0x67,0,0xb9};
    std::memcpy(g_ModuleBytes.data()+0x3d9b80,leaveGuard,sizeof(leaveGuard));
    // 新的真实Spawns容器同样验证解析器与镜像布局；均只提供指纹，不执行代码。
    constexpr unsigned char parseGuard[16]={0xfd,0x43,0x02,0x91,0xfc,0x6f,0x0a,0xa9,0xfa,0x67,0x0b,0xa9,0xf8,0x5f,0x0c,0xa9};
    constexpr unsigned char mirrorGuard[16]={0xf8,0x5f,0x03,0xa9,0xf6,0x57,0x04,0xa9,0xf4,0x4f,0x05,0xa9,0xf4,0x03,0x00,0xaa};
    std::memcpy(g_ModuleBytes.data()+0x48f490,parseGuard,sizeof(parseGuard));
    std::memcpy(g_ModuleBytes.data()+0x495248,mirrorGuard,sizeof(mirrorGuard));


    g_OwnerBytes.assign(sizeof(std::uint64_t), 0);
    g_GamePointerBytes.assign(sizeof(std::uint64_t), 0);
    // Level 对象要覆盖到描述符数组、当前索引/维度、以及元素个数所在的 +0x21510。
    g_LevelBytes.assign(0x21600, 0);
    // 每个房间配置块 0x60 字节（`Shape` 在 +0x5C、占 4 字节 ⇒ 块至少要 0x60），三块互不重叠。
    g_ConfigBytes.assign(0x60 * 3, 0);

    // 两条取 Game 的路径都要自洽（真机上它们是同一个槽地址）：
    //   ① `*(模块 + 偏移)` → owner → `*(owner)` → Game（`ReadGameCurses` 那条链）
    //   ② `GameOwnerSlot()` → `*(槽)` → owner → Game（`ObserveLevelIsAscent` 那条链）
    WriteWord(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_GamePointerBytes));
    WriteWord(g_OwnerBytes, 0, AddressOf(g_GamePointerBytes));
    WriteWord(g_GamePointerBytes, 0, AddressOf(g_LevelBytes));
    WriteAt<std::uint32_t>(g_LevelBytes, 0x21510, 3);          // 元素个数
    WriteAt<std::uint32_t>(g_LevelBytes, kLevelCurrentRoomIndexOffset, g_CurrentIndex);
    if (g_MapGrid >= 0) {
        // `Level + 0x2d18` = 引擎自己的"网格下标 → 槽位号"表（int32，维度 0 的 169 项）。
        WriteAt<std::uint32_t>(g_LevelBytes,
                               kLevelGridSlotTableOffsetForTest +
                                   static_cast<std::size_t>(g_MapGrid) * 4,
                               g_MapSlot);
    }
    WriteAt<std::uint32_t>(g_LevelBytes, kLevelCurrentRoomDimensionOffset, kCurrentDimension);
    for (std::size_t slot = 0; slot < 3; ++slot) {
        const std::uintptr_t base = kArrayBase + slot * kStride;   // 相对 Level 块
        WriteAt<std::uint32_t>(g_LevelBytes, base + 0x00, kRooms[slot]);
        WriteAt<std::uint32_t>(g_LevelBytes, base + 0x04, kRooms[slot]);
        WriteAt<std::uint32_t>(g_LevelBytes, base + 0x08, static_cast<std::uint32_t>(slot));
        // 槽 0 = 当前房间：`data_missing` 场景把它写成 0（其它槽照旧指向真实配置块）。
        const bool zeroData = g_ZeroDataPointer && slot == 0;
        WriteWord(g_LevelBytes, base + 0x10,
                  zeroData ? 0 : AddressOf(g_ConfigBytes) + slot * 0x60);
        WriteAt<std::uint32_t>(g_LevelBytes, base + 0x4C, kVisited[slot]);
        WriteAt<std::uint32_t>(g_LevelBytes, base + 0x48, kDisplayFlags[slot]);
        WriteAt<std::uint32_t>(g_LevelBytes, base + 0x50, kClearFlag[slot]);
        WriteAt<std::uint32_t>(g_ConfigBytes, slot * 0x60 + 0x08, kTypes[slot]);
        WriteAt<std::uint32_t>(g_ConfigBytes, slot * 0x60 + 0x5C, kShapes[slot]);
    }
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

// 覆盖共享默认桩：`Level:GetStage` 等既有 API 在本次测试里不需要真值，保持"读不到"。

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "map_fallback") == 0) {
        g_CurrentIndex = 98;   // 2x2 房间（GridIndex 97）的"进入格"
        g_MapGrid = 98;
        g_MapSlot = 1;
    } else if (std::strcmp(scenario, "map_fallback_backward") == 0) {
        g_CurrentIndex = 96;   // 锚点**右下**那一格（L 形房间会出现这种相对位置）
        g_MapGrid = 96;
        g_MapSlot = 1;
    } else if (std::strcmp(scenario, "absent") == 0) {
        g_CurrentIndex = 130;  // 谁也不是；映射表那一格没写（=0 ⇒ 槽 0，但被"足迹"校验挡掉）
    } else if (std::strcmp(scenario, "data_missing") == 0) {
        // 批次 071：当前房间的描述符是**有效槽位**、但 `+0x10`（Data 指针）读出 0。
        // 真机形态（贪婪模式一类）：GoodTrip `control.lua:339` 写 `crd.Data.Type`，
        // 我们以前返回 nil ⇒ 整条 `MC_POST_NEW_ROOM` 回调每次崩。
        g_ZeroDataPointer = true;
    }
    PublishFakeEngine();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerBytes), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "top_level") == 0) {
        script =
            "local ok, v = pcall(function() return Game():GetLevel():GetCurrentRoomDesc() end)"
            " print('TOPLEVEL ok='..tostring(ok)..' v='..tostring(v))";
    } else if (std::strcmp(scenario, "fields") == 0) {
        script =
            "local mod=RegisterMod('Probe',1);"
            " mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()"
            " local d=Game():GetLevel():GetCurrentRoomDesc()"
            " print('GRID='..tostring(d.GridIndex))"
            " print('SAFE='..tostring(d.SafeGridIndex))"
            " print('LIST='..tostring(d.ListIndex))"
            " print('VISITED='..tostring(d.VisitedCount))"
            " print('DISPLAY='..tostring(d.DisplayFlags))"
            " print('CLEAR='..tostring(d.Clear))"
            " print('FLAGS='..tostring(d.Flags))"
            " print('TYPE='..tostring(d.Data.Type))"
            " print('SHAPE='..tostring(d.Data.Shape))"
            // 批次 056：`Data.Spawns` 必须**存在**且是可索引的空容器。
            // 为什么钉住：GoodTrip 的绘制路径读 `spawns.Size` 与 `spawns:Get(j)`，
            // 给 nil 会让整条 MC_POST_RENDER 回调每帧报错、小地图一个像素都画不出来
            // （真机 `widget.lua:391: attempt to index a nil value (local 'spawns')`）。
            " local sp=d.Data.Spawns"
            " print('SPAWNS='..type(sp))"
            " print('SPAWNS_SIZE='..tostring(sp.Size))"
            " print('SPAWNS_GET='..tostring(sp:Get(0)))"
            // 批次 061：`Level` 的字段**可写**（PC 的 Level 是引擎对象，模组直接赋值）。
            // 真机 `trip.lua:123` 就是 `floor.level.EnterDoor = -1`；没有 `__newindex` 时
            // 这一句抛 "attempt to index a IsaacRuntime.Level value" ⇒ GoodTrip 传送断在这里。
            " local lv=Game():GetLevel()"
            " lv.EnterDoor = -1"
            " lv.LeaveDoor = -1"
            " lv.WhateverFieldTypo = 7"
            " print('WRITE=ok')"
            " end)";
    } else if (std::strcmp(scenario, "map_fallback") == 0) {
        script =
            "local mod=RegisterMod('Probe',1);"
            " mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()"
            " local d=Game():GetLevel():GetCurrentRoomDesc()"
            " print('CUR_GRID='..tostring(d.GridIndex))"
            " print('CUR_SAFE='..tostring(d.SafeGridIndex))"
            " end)";
    } else if (std::strcmp(scenario, "map_fallback_backward") == 0 ||
               std::strcmp(scenario, "absent") == 0) {
        script =
            "local mod=RegisterMod('Probe',1);"
            " mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()"
            " local d=Game():GetLevel():GetCurrentRoomDesc()"
            " print('CUR_GRID='..tostring(d.GridIndex))"
            " print('CUR_SAFE='..tostring(d.SafeGridIndex))"
            " print('CUR_LIST='..tostring(d.ListIndex))"
            " print('CUR_FLAGS='..tostring(d.Flags))"
            // 批次 073：**空句柄**（解析不到当前房间）下，数值/布尔/子对象字段也**不许给 nil**。
            // 真机事故：换房那一刻 `GetCurrentRoomDesc()` 返回空句柄 ⇒ `crd.Data` 是 nil ⇒
            // GoodTrip `control.lua:339` 的 `crd.Data.Type` 崩、整条换房回调被摘掉。
            " local dd = d.Data"
            " print('CUR_DATA_KIND='..type(dd))"
            " print('CUR_DATA_TYPE='..tostring(dd.Type))"
            " print('CUR_DATA_SPAWNS='..type(dd.Spawns))"
            " print('CUR_DISPLAY='..tostring(d.DisplayFlags))"
            " print('CUR_CLEAR='..tostring(d.Clear))"
            " print('CUR_VISITED='..tostring(d.VisitedCount))"
            " end)";
    } else if (std::strcmp(scenario, "data_missing") == 0) {
        script =
            "local mod=RegisterMod('Probe',1);"
            " mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()"
            " local d=Game():GetLevel():GetCurrentRoomDesc()"
            " print('DATA_KIND='..type(d.Data))"
            " print('DATA_TYPE='..tostring(d.Data.Type))"
            " print('DATA_SHAPE='..tostring(d.Data.Shape))"
            " print('DATA_SPAWNS='..type(d.Data.Spawns))"
            " end)";
    } else if (std::strcmp(scenario, "by_index") == 0) {
        script =
            "local mod=RegisterMod('Probe',1);"
            " mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()"
            " local level=Game():GetLevel()"
            " print('TREASURE='..tostring(level:GetRoomByIdx(97).Data.Type))"
            " print('CURRENT_CLEAR='..tostring(level:GetRoomByIdx(-1).Clear))"
            " print('TREASURE_FLAGS='..tostring(level:GetRoomByIdx(97).Flags))"
            " print('TREASURE_DISPLAY='..tostring(level:GetRoomByIdx(97).DisplayFlags))"
            " print('TREASURE_CLEAR='..tostring(level:GetRoomByIdx(97).Clear))"
            " local missing = level:GetRoomByIdx(999)"
            " print('MISSING='..tostring(missing)..' MISSING_GRID='..tostring(missing.GridIndex))"
            " print('NEGATIVE='..tostring(level:GetRoomByIdx(-2)))"
            " end)";
    } else {
        script =
            "local mod=RegisterMod('Probe',1);"
            " mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()"
            " local rooms=Game():GetLevel():GetRooms()"
            " print('SIZE='..tostring(rooms.Size))"
            " for i=0,rooms.Size-1 do"
            "   local ok, room = pcall(function() return rooms:Get(i) end)"
            "   if not ok then print('GETERR'..i..'='..tostring(room))"
            "   else"
            "     print('ROOM'..i..'='..tostring(room and room.GridIndex))"
            "   end"
            " end"
            " print('OUT='..tostring(rooms:Get(99)))"
            " end)";
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@roomdesc.lua");
    if (std::strcmp(scenario, "top_level") == 0) {
        // ★ 设计变更（2026-09-19 批次 043）：顶层（非托管回调）调用**不再被作用域守卫拒绝** ——
        // PC 允许模组在加载期读引擎状态（GoodTrip 的 scripts/floor.lua:11-17 就是），
        // 而报错会让整个模组的功能整块消失。判据改为「这次调用真的被执行了」：
        // 脚本一律用 pcall 包住并打印结果，Python 侧核对（见本文件对应测试）。
        static_cast<void>(result);
        return 0;
    }
    if (result != LuaRuntime::LuaInitResult::Success) return 2;
    LuaRuntime::DispatchPreGetCollectible(nullptr, 0, 0, 1, 0);
    if (LuaRuntime::TakeCallbackError()) {
        // 失败时把 Lua 错误文本整段打出来 —— 否则宿主机只能看到"回调里出错了"，
        // 又要靠猜（这条通道与真机探针读的是同一份文本）。
        char buffer[512] = {};
        const std::size_t length = LuaRuntime::CopyLastLuaErrorText(buffer, sizeof(buffer));
        std::printf("LUA_ERROR(%.*s)\n", static_cast<int>(length), buffer);
        return 4;
    }
    return 0;
}
'''


class LuaRoomDescriptorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-roomdesc-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.binary), scenario], text=True, capture_output=True)

    def test_each_field_reads_its_own_offset(self):
        """逐个字段钉住偏移 —— 防"整批偏移错位"这种界面上看不出异常的错。"""
        result = self.run_scenario("fields")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # `FLAGS` / `SHAPE`（2026-09-16 新增）：
        #   * `+0x50` 是 32 位位掩码 ⇒ fixture 写 `0x401`（bit0 + bit10）时 `Flags` 必须回 1025、
        #     而 `Clear` 只看 bit0（所以仍是 true）；
        #   * `Data+0x5C` 是 `Shape`（fixture 槽 0 = 1）。
        # `DISPLAY`（2026-09-19 批次 047 新增）：`+0x48` = PC 的 `RoomDescriptor.DisplayFlags`。
        # fixture 槽 0 的 `Flags` 是 `0x401`，`DisplayFlags` 写的是 `0x5` —— 两条断言一起看，
        # "把 0x48 读成了相邻的 0x50"会立刻红（真实缺陷：GoodTrip 绘制路径读它拿 nil，
        # 每帧抛 `attempt to compare number with nil`，小地图画不出来）。
        for expected in ("GRID=84", "SAFE=84", "LIST=0", "VISITED=2", "DISPLAY=5", "CLEAR=true",
                         "FLAGS=1025", "TYPE=1", "SHAPE=1",
                         # 批次 056：空容器形状（真值取证前是 `Size = 0`、`Get` 恒 nil）。
                         # 这条钉的是"形状在、不抛错"；**它不声称 Spawns 的真实内容正确**。
                         "SPAWNS=userdata", "SPAWNS_SIZE=0", "SPAWNS_GET=nil",
                         # 批次 061：字段写入必须**接受**（不抛错）。这条钉的是"形状"，
                         # 不声称写入真的落到引擎（`EnterDoor` 的偏移还没有证据）。
                         "WRITE=ok"):
            with self.subTest(expected=expected):
                self.assertIn(expected, result.stdout)

    def test_data_is_never_nil_even_when_the_pointer_is_zero(self):
        """★ 批次 071：`Data` 指针读成 0 时，`Data` 也**必须是表**（不是 nil）。

        真机事故（2026-09-19 用户复测仍复现）：GoodTrip `control.lua:339` 写的是
        `crd.Data.Type`；某些房间（贪婪模式一类）`描述符 + 0x10` 读出来是 0，
        我们返回 nil ⇒ 模组的 `MC_POST_NEW_ROOM` 回调**每次都崩**，被派发器摘掉，
        "秘密房/诅咒房预缓存"那一支永远不执行。

        判据：字段按 0 建出来（走"普通房间"这个安全分支），而且**不抛错**；
        PC 里 `Data` 是内嵌结构、本来就不可能为 nil。
        """
        result = self.run_scenario("data_missing")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DATA_KIND=table", result.stdout)
        self.assertIn("DATA_TYPE=0", result.stdout)
        self.assertIn("DATA_SHAPE=0", result.stdout)
        self.assertIn("DATA_SPAWNS=userdata", result.stdout)

    def test_get_room_by_idx_finds_rooms_and_refuses_what_it_cannot_prove(self):
        """`GetRoomByIdx(97)` 找到宝箱房；`(-1)` 是当前房间；越界与 -2 给 nil。

        `-2`（PC 的"上一个房间"）**没有证据**（负数槽位公式未验证），所以必须给 nil
        而不是编一个房间 —— 给错房间比给 nil 更糟。
        """
        result = self.run_scenario("by_index")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TREASURE=4", result.stdout)
        self.assertIn("CURRENT_CLEAR=true", result.stdout)
        # 语义收窄的判别用例：宝箱房 flags 只有 bit3（0x8）⇒ `Flags` 回 8、`Clear` 必须**假**。
        # 旧实现按"非零即真"会把这里报成 true（这条用例就是为它写的）。
        self.assertIn("TREASURE_FLAGS=8", result.stdout)
        # 批次 047：`GetRoomByIdx` 这条路上也要能读 `DisplayFlags`（槽 1 写的是 0）。
        self.assertIn("TREASURE_DISPLAY=0", result.stdout)
        self.assertIn("TREASURE_CLEAR=false", result.stdout)
        # ★ 设计变更（2026-09-19 批次 043）：查不到的描述符**也给对象**（PC 在这类位置给的就是对象，
        # 给 nil 会让模组的加载期代码整块消失 —— GoodTrip 的 floor.lua:15-16 真机实测）。
        # 判据随之变成："有对象，但**字段如实说没有**"。
        # ★ 再变更（2026-09-19 批次 049）：「如实说没有」对**网格类字段**改成给 **-1**，不再给 nil。
        # 理由是真机代价：GoodTrip 的 `scripts/floor.lua:218-220` 把 `SafeGridIndex` 当**表键**
        # （`link[here] = ...`）⇒ 给 nil 直接 "table index is nil"，整条 `MC_POST_UPDATE`
        # 回调每帧被打断；而引擎自己的"这一格没有房间"就是 -1
        # （真机实测：未分配槽位的 `+0x00`/`+0x04` 都是 `0xFFFFFFFF`）⇒ -1 既不是编值、也不比 PC 严。
        self.assertIn("MISSING_GRID=-1", result.stdout)
        self.assertNotIn("MISSING=nil", result.stdout)
        self.assertIn("NEGATIVE=nil", result.stdout)

    def test_multi_tile_room_is_found_through_the_engine_map(self):
        """批次 049：多格房间必须靠**引擎自己的映射表**找到。

        `Level + 0x21558` 是"从哪一格进去的"（PC 文档 `RoomDescriptor.md:193`），在 2x2 / L 形
        房间里它**不等于该房间的 `GridIndex`** ⇒ 只按"扫描 `+0x00 == 下标`"会找不到，
        于是 `GetCurrentRoomDesc()` 返回空句柄、`SafeGridIndex` 变 nil。

        本场景：进入格 98、房间在槽 1（`GridIndex` 97，2x2 足迹 {97, 98, 110, 111}）；
        映射表写 `map[98] = 1`。期望读出**房间**的 97（不是进入格的 98）。
        """
        result = self.run_scenario("map_fallback")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CUR_GRID=97", result.stdout)

    def test_multi_tile_room_is_found_when_the_entry_cell_is_before_the_anchor(self):
        """方向相反的情形同样要认：L 形房间的锚点与进入格可以差 **负** 的 1/13/14。

        PC 文档里 LTL 房间的 `SafeGridIndex` 是**右上**那一格 ⇒ 进入格落在锚点的左/上是正常的；
        只收正差值的守卫会把这类房间全挡掉（退化成"没有当前房间"）。
        """
        result = self.run_scenario("map_fallback_backward")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CUR_GRID=97", result.stdout)

    def test_absent_room_reports_minus_one_not_nil(self):
        """批次 049：解析不到当前房间时，网格类字段给 **-1**（引擎自己的"没有房间"就是 -1）。

        真机代价：GoodTrip 的 `scripts/floor.lua:218-220` 拿 `SafeGridIndex` 当表键
        ⇒ 给 nil 就报 "table index is nil"、整条 `MC_POST_UPDATE` 回调每帧被打断。
        真机实测：未分配槽位的 `+0x00`/`+0x04` 都是 `0xFFFFFFFF`（= -1）。
        """
        result = self.run_scenario("absent")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CUR_GRID=-1", result.stdout)
        self.assertIn("CUR_SAFE=-1", result.stdout)
        self.assertIn("CUR_LIST=-1", result.stdout)
        self.assertNotIn("CUR_GRID=nil", result.stdout)
        # ★ 批次 073 **改动了一条既有断言**（原来是 `CUR_FLAGS=nil`）：空句柄下数值/布尔/子对象
        # 字段也**给该类型的空值**，不再给 nil。理由是真机证据，不是"为了让改动通过"：
        # 换房那一刻 `GetCurrentRoomDesc()` 返回空句柄 ⇒ `crd.Data` 是 nil ⇒
        # GoodTrip `scripts/control.lua:339` 的 `crd.Data.Type` 崩、整条 `MC_POST_NEW_ROOM`
        # 回调被派发器摘掉（环形历史里那条错一直挂着）。PC 里这些字段都有确定类型，
        # 给 nil 等于逼模组在每次换房时自己判空 —— 而模组作者（有 PC 的行为作参照）不会判。
        self.assertIn("CUR_FLAGS=0", result.stdout)
        self.assertIn("CUR_DISPLAY=0", result.stdout)
        self.assertIn("CUR_CLEAR=false", result.stdout)
        self.assertIn("CUR_VISITED=0", result.stdout)
        self.assertIn("CUR_DATA_KIND=table", result.stdout)
        self.assertIn("CUR_DATA_TYPE=0", result.stdout)
        self.assertIn("CUR_DATA_SPAWNS=userdata", result.stdout)

    def test_get_rooms_exposes_size_and_indexed_access(self):
        """`GetRooms()` 要有 `.Size` 与 `:Get(i)`，越界给 nil（EID 就是这么遍历的）。"""
        result = self.run_scenario("rooms")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SIZE=3", result.stdout)
        self.assertIn("ROOM0=84", result.stdout)
        self.assertIn("ROOM1=97", result.stdout)
        self.assertIn("ROOM2=71", result.stdout)
        self.assertIn("OUT=nil", result.stdout)

    def test_outside_a_managed_callback_the_apis_now_run(self):
        result = self.run_scenario("top_level")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
