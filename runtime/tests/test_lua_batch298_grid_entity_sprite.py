"""门禁：`GridEntity:GetSprite()`（批次 298，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 走法 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `GridEntity:GetSprite()` | `GridEntity.md:53` | `GridEntity + 0x48` 那个**内嵌 ANM2** | **手写处理器**（要交回 `Sprite` 句柄） | 14 |

清单里另有一条 `GridEntityRock:GetSprite`（同样记 14 处、同一个模组 BOIStageAPI15），但它
**没有契约页、也没有接收者证据** ⇒ 它是同一批调用点的**派生行**：语料里那 14 处的接收者全是
`grid:GetSprite()` / `self.GridEntity:GetSprite()`（**基类句柄**），而 `ToRock()` 在我们这边
压的本来就是基类 `GridEntity` 视图 ⇒ 走同一段代码就对了（`mod_api_gap_report.py` 会沿 owner
继承链把那条派生行自动划掉，实测见生成器里那段注释）。

## 为什么 `+0x48` 就是网格实体的 sprite（与 `Entity+0x50` 同一手法）

**PC 侧的标尺**：`GridEntity:GetSprite @ 0x427440` = `lea eax,[ecx+0x3C]`、
`GridEntityRock:GetSprite @ 0x427680` = `lea eax,[ecx+0x40]`（两个类**偏移不同**）。

**Switch 侧只有一格**，证据是"引擎自己把它当 ANM2 用"：

* `GridEntity_Rock::InitSubclass @ 0x392E98`：`add x21, x19, #0x48` → `bl ANM2::Load`
  （加载的是 `gfx/grid/grid_rock.anm2`）；
* 同一个类的 `Render @ 0x392B1C` → `ANM2::Render`、`update_anim_frame @ 0x38FD88` → `ANM2::SetFrame`；
* **另有 10 个子类的 `ANM2::Load` 写同一格**（Decoration / Door / Fire / Gravity / Lock / Poop /
  PressurePlate / Spikes / Stairs / TrapDoor）⇒ 基类与子类**同格**。
* ★ 免费交叉印证：同一次扫全镜像里 `+0x50` 拿到 **48 处**命中 —— 那正是既有的
  `kEntitySpriteOffset`（`Entity` 的 sprite）。

## 宿主验到了什么、没验到什么

* **验到**：
  - ★★ **句柄真的指在 `gridEntity + 0x48`**：夹具把那块内嵌 ANM2 的 `+0x149`（"图形已加载"
    标志，`kSpriteLoadedFlagOffset`）写成 1 ⇒ `sprite:IsLoaded()` 必须答 **true**
    （`IsLoaded` 是**纯读那一格**、没有引擎调用 ⇒ 宿主里能读到真值）。这一条同时钉住
    "偏移对"与"解析链对"。
  - **接收者失效（网格实体没了）⇒ `GetSprite()` 给 `nil`、不报错**；
  - ★ **借出的句柄会重新校验**：把网格实体的 vptr 改坏之后再对**旧句柄**调
    `sprite:IsLoaded()` ⇒ **报错**且消息里写明是"网格实体不在了"（与"我们自己释放了 sprite"分开）；
  - 参数闸门：0 参方法多给实参报错。
* **没验**：真机上这一格是不是网格实体在用的那个 ANM2（宿主里"偏移对不对"是常量与夹具两处
  写同一个数，自己证不了自己）。⇒ 真机项 = 作业单 **V49**（最强判据 = 对一块石头
  `rs:GetSprite():SetFrame("rock", 0)` 之后**屏幕上的石头真的变了**帧）。
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
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
SPRITE_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "sprite_api.cpp"
SPRITE_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "sprite_api.hpp"
HANDLES = ROOT / "runtime" / "source" / "lua_object_handles.hpp"
ISAAC_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
WORKLIST_TOOL = ROOT / "tools" / "build_api_restore_worklist.py"

#: Isaac 域里这一条的序号（域内下一个空号 = 0xD0）。
API_INDEX = 0x00D0
#: 夹具里用的网格下标（写进 `GridEntity + 0x28`，`Room:GetGridEntity(i)` 按它查表）。
GRID_INDEX = 20


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 假模块槽 / 假房间 / 假网格实体（形状抄 `test_lua_grid_entity_cast_batch276.py`）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = "Game"（本夹具里同时当 Level/Room 解析的锚点）
//   Room + kRoomGridEntityTableOffset        = 按网格下标索引的 `GridEntity*` 表
//   网格实体首字                              = base + kGridEntityVtableOffset（存活判据要它）
//   网格实体 + kGridEntitySpriteOffset (0x48) = **内嵌 ANM2**；把它的 `+0x149`（已加载标志）写成 1
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_GridBytes;

//: `ReadCurrentGameRoom` 被调了几次（`Room:GetGridEntity` 每次都会问一次）。
int g_RoomReads = 0;
//: `dead` 那一场：第 2 次问房间时把网格实体的 vptr 改坏（模拟"石头炸掉了"）。
bool g_CorruptOnSecondRead = false;

static_assert(kGridEntitySpriteOffset + kSpriteLoadedFlagOffset < kGridEntitySpriteOffset + 0x158,
              "sprite 的已加载标志必须落在内嵌 ANM2 的 0x158 字节之内");

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
    // 网格实体：0x48 的内嵌 ANM2（0x158 字节）+ 一点余量。
    g_GridBytes.assign(kGridEntitySpriteOffset + 0x158 + 0x20, 0);
    WriteAt<std::uintptr_t>(g_GridBytes, 0,
                            AddressOf(g_ModuleBytes) + kGridEntityVtableOffset);
    WriteAt<std::uint32_t>(g_GridBytes, kGridEntityTypeOffset, 6);
    WriteAt<std::uint32_t>(g_GridBytes, kGridEntityGridIndexOffset, GRID_INDEX);
    // ★★ 内嵌 ANM2 的"图形已加载"标志 = 1 ⇒ `sprite:IsLoaded()` 必须答 true。
    WriteAt<std::uint8_t>(g_GridBytes, kGridEntitySpriteOffset + kSpriteLoadedFlagOffset, 1);

    const std::size_t tableOffset = kRoomGridEntityTableOffset + GRID_INDEX * sizeof(std::uintptr_t);
    g_RoomBytes.assign(tableOffset + sizeof(std::uintptr_t) + 8, 0);
    WriteAt<std::uintptr_t>(g_RoomBytes, tableOffset, AddressOf(g_GridBytes));
    WriteAt<std::uintptr_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uintptr_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    ++g_RoomReads;
    // ★ 每次 `Game():GetRoom():GetGridEntity(i)` 会读**两次**（`GetRoom()` 一次 +
    //   `GetGridEntity` 一次）⇒ 阈值 3 = **第二条链**的 `GetRoom()` 那一步，
    //   于是"第一条链拿到的句柄"仍然指着这个实体、而"第二条链拿到的句柄"已经失效
    //   —— 正好把"新调用给 nil"与"旧句柄重新校验"两件事分开验。
    if (g_CorruptOnSecondRead && g_RoomReads >= 3) {
        // "石头被炸掉了"：vptr 改成一块**不在 `GridEntity` 家族区间**里的值
        // （用模块块自己的地址 —— 那里放的是数据，不是 vtable）。
        WriteAt<std::uintptr_t>(g_GridBytes, 0, AddressOf(g_RoomBytes));
    }
    *room = reinterpret_cast<void*>(AddressOf(g_RoomBytes));
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "sprite") == 0) {
        // 默认。
    } else if (std::strcmp(scenario, "dead") == 0) {
        g_CorruptOnSecondRead = true;
    } else {
        return 91;
    }
    PublishFakeRoom();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "sprite") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) return tostring(select(2, pcall(f))) end"
            " local grid = Game():GetRoom():GetGridEntity(GRID_INDEX)"
            " local sprite = grid:GetSprite()"
            " print('B298 kind=' .. type(grid) .. ',' .. type(sprite))"
            // ★★ 内嵌 ANM2 的 +0x149 = 1 ⇒ 纯读那一格的方法必须答 true
            " print('B298 loaded=' .. tostring(sprite:IsLoaded()))"
            " print('B298 loadedkind=' .. type(sprite:IsLoaded()))"
            " print('B298 arity=' .. ok(function() return grid:GetSprite(1) end))"
            " print('B298 arityerr=' .. err(function() return grid:GetSprite(1) end))";
    } else {
        script =
            "local function err(f) return tostring(select(2, pcall(f))) end"
            " local grid = Game():GetRoom():GetGridEntity(GRID_INDEX)"
            " local sprite = grid:GetSprite()"
            " print('B298 alive=' .. tostring(sprite:IsLoaded()))"
            // 再问一次房间 ⇒ 桩在这一刻把网格实体的 vptr 改坏
            " local grid2 = Game():GetRoom():GetGridEntity(GRID_INDEX)"
            " print('B298 deadnil=' .. tostring(grid2:GetSprite() == nil))"
            " print('B298 deadkind=' .. type(grid2:GetSprite()))"
            // ★ 旧句柄要**重新校验**：网格实体没了 ⇒ 报错，且消息指明是网格实体
            " print('B298 deadmsg=' .. err(function() return sprite:IsLoaded() end))";
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b298.lua");
    static_cast<void>(result);
    return 0;
}'''
HARNESS = HARNESS.replace("GRID_INDEX", str(GRID_INDEX))


class GridEntitySpriteBatch298Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b298-")
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
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_the_handle_points_at_the_embedded_anm2(self):
        """★★ 句柄必须指在 `gridEntity + 0x48`：夹具把那一格内嵌 ANM2 的 `+0x149`
        （"图形已加载"标志）写成 1 ⇒ `sprite:IsLoaded()`（**纯读那一格**、无引擎调用）
        必须答 `true`。★ 这一条同时钉住"偏移对"与"解析链对"（走的是新来源那条分支）。
        """
        out = self.run_scenario("sprite")
        self.assertIn(f"B298 kind=userdata,userdata", out)
        self.assertIn("B298 loaded=true", out)
        self.assertIn("B298 loadedkind=boolean", out)

    def test_argument_gate_is_exactly_zero(self):
        """0 参方法多给实参必须报错。"""
        out = self.run_scenario("sprite")
        self.assertIn("B298 arity=false", out)
        self.assertIn("GridEntity:GetSprite accepts no arguments", out)

    def test_dead_grid_entity_yields_nil_and_the_old_handle_revalidates(self):
        """★★ 网格实体没了（vptr 被改坏）之后：

        * **新调用** `grid:GetSprite()` ⇒ **nil**（不报错，让 `if sprite then` 走另一条路）；
        * ★ **旧句柄**再访问 ⇒ **报错**，且消息里写明是**网格实体**不在了
          （与"我们自己释放了这个 Sprite"分开报 —— 否则真机日志会误读）。
        """
        out = self.run_scenario("dead")
        self.assertIn("B298 alive=true", out)
        self.assertIn("B298 deadnil=true", out)
        self.assertIn("B298 deadkind=nil", out)
        self.assertIn("the engine grid entity this Sprite belongs to is no longer alive", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 三个常量 / 新来源 / 存活判据 / 生成器里那句注释。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        sprite = SPRITE_API.read_text(encoding="utf-8")
        sprite_header = SPRITE_HEADER.read_text(encoding="utf-8")
        handles = HANDLES.read_text(encoding="utf-8")
        isaac_header = ISAAC_HEADER.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        #: 目录行 + 手写绑定行（这条 API 交回句柄 ⇒ 数据行产出不了句柄）。
        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{API_INDEX:04X}), ApiDomain::Isaac, "GridEntity", '
            f'"GetSprite"', catalog)
        self.assertRegex(remaining, rf"\{{\s*(?i:0x0E01{API_INDEX:04x}),\s*&GridEntityGetSprite\}}")
        self.assertIn("int GridEntityGetSprite(lua_State* state);", remaining)
        self.assertIn("int GridEntityGetSprite(lua_State* state) {", remaining)
        #: ★ 反回归：不许被塞进字段行表 —— 它要交回句柄。
        self.assertNotRegex(remaining, rf"0x0E01{API_INDEX:04x}[^\n]*FieldKind::")

        #: 常量与偏移。
        self.assertRegex(constants, r"inline constexpr uintptr_t kGridEntitySpriteOffset\s*=\s*0x48;")
        self.assertRegex(constants, r"inline constexpr uintptr_t "
                                    r"kGridEntityVtableRangeBeginOffset\s*=\s*0xA37890;")
        self.assertRegex(constants, r"inline constexpr uintptr_t "
                                    r"kGridEntityVtableRangeEndOffset\s*=\s*0xA382A8;")

        #: 新的 Sprite 来源（句柄的**所有权**标记 + 三处分支）。
        self.assertIn("kSpriteSourceEngineGridEntity = 2", handles)
        self.assertIn("PushEngineGridEntitySpriteHandle", sprite_header)
        self.assertIn("int PushEngineGridEntitySpriteHandle(lua_State* state, void* gridEntity)",
                      sprite)
        #: 三处按来源分支的地方都要认它（漏任一处都是真事故：__gc 会去 free 引擎内存）。
        #: 四处**代码**位置各断言一次（不数总次数 —— 注释里也会出现这个名字）。
        self.assertIn("using LuaRuntime::kSpriteSourceEngineGridEntity;", sprite)
        self.assertIn("if (handle->source == kSpriteSourceEngineGridEntity) {\n"
                      "        const std::uintptr_t owner = engine_memory::AddressOf(handle->owner);\n"
                      "        if (!IsLiveGridEntityPointer(owner)) {", sprite)
        self.assertIn("handle->source = kSpriteSourceEngineGridEntity;", sprite)
        # 核非拥有分支本身，允许同一早退条件加入新增的额外网格Sprite来源。
        gc = sprite.split("int DestroySpriteHandle(", 1)[1].split("std::size_t AttachSpriteMethods", 1)[0]
        nonowning = re.search(r"if\s*\(([^{}]*source[^{}]*)\)\s*\{\s*return 0;\s*\}", gc)
        self.assertIsNotNone(nonowning)
        for source in ("kSpriteSourceEngineEntity", "kSpriteSourceEngineGridEntity", "kSpriteSourceEngineGridExtra"):
            self.assertIn(source, nonowning.group(1))
        #: 网格实体存活判据的导出声明与实现。
        self.assertIn("bool IsLiveGridEntityPointer(std::uintptr_t candidate) noexcept;",
                      isaac_header)
        self.assertIn("bool IsLiveGridEntityPointer(std::uintptr_t candidate) noexcept {",
                      ISAAC_HEADER.parent.joinpath("isaac_api.cpp").read_text(encoding="utf-8"))

        #: ★ 常量段要写下取证依赖的地址（PC 两个绑定 + Rock 的三处 + 那个"基址 0x48"的锚点）。
        written = {int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", constants)}
        for va in (0x427440, 0x427680,            # PC 两条绑定
                   0x392E98, 0x392ED8,            # Rock::InitSubclass 的 add + ANM2::Load
                   0x392B1C, 0x38FD88):           # Rock::Render / update_anim_frame
            self.assertIn(va, written, f"证据地址 {va:#x} 没有写进常量段")
        self.assertIn(0x48, written, "偏移 0x48 没有写进常量段")

        #: 派生 owner 那条的处置要写明（生成器里那段注释）。
        tool = WORKLIST_TOOL.read_text(encoding="utf-8")
        self.assertIn("派生 owner 的方法会自动消失", tool)


if __name__ == "__main__":
    unittest.main()
