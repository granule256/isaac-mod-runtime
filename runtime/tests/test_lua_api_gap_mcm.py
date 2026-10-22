"""批次 207（2026-09-29）为 MCM 补齐的那一批 API 的宿主行为测试。

## 这一批为什么存在

MCM（Mod Config Menu）要在破解 Switch 上跑起来，缺的**不是**配置界面那一层，而是它能调到的
底层接口。这一批逐条对着 MCM 的调用点补齐（括号里是 MCM 的调用处）：

| API | MCM 在哪用 | 返回值从哪来 |
| --- | --- | --- |
| `Isaac.GetScreenWidth()` / `GetScreenHeight()` | `screenhelper.lua:55/56` 按屏幕摆界面 | 模块 GOT 槽 `0xAAC650`/`0xAAC658` |
| `Isaac.GetEntityTypeByName(name)` | `modconfig.lua:260` 查 `"Potato Dummy"` | 本体 `entities2.xml` 的**静态名字快照** |
| `Isaac.GetEntityVariantByName(name)` | `modconfig.lua:261`（同上） | 同上 |
| `Room:IsClear()` | `modconfig.lua:231` 判"这屋能不能开菜单" | `Room+0x8`（描述符）`+0x50` 的 bit0 |
| `Entity:HasEntityFlags(Flags)` | `modconfig.lua:207` 排除友方 | `Entity+0x1B8` 的 64 位标志字 |
| `Entity:IsActiveEnemy([includeDead])` | `modconfig.lua:206` 判"屋里有没有活敌人" | 引擎自己的方法（数据行） |
| `Entity:ToProjectile()` | `modconfig.lua:220` 把子弹换成投射物视图 | `Type == 9` **且** vptr 精确等于投射物 vtable |

（`Game:GetHUD()` / `HUD:IsVisible()` / `HUD:SetVisible()` 三条在
`test_lua_hud_visibility.py` 里，那份要伪造一整块 `Game` 直到 HUD 那一格，单独放。）

## 这里钉的是"我们这一侧"的行为

偏移本身的出处是反汇编（记在 `runtime_constants.hpp` 的批次 207 段）。本用例用**伪造的引擎
内存**证明我们读得对、过滤得对、参数校验对、降级得对：

1. **屏宽/屏高**：槽里放 1280/720 ⇒ Lua 侧必须原样拿到；没装 Hook（`SetEngineModuleBase`
   未被调用）⇒ 返回 `0` 而**不报错**（报错会把整条模组回调摘掉，0 只是让界面贴在左上角）；
2. **实体名查表**：这是**纯查表**、与引擎内存无关，所以能在宿主上验到"返回值真的对"：
   `Monstro → (20, 0)`、`Lokii → (69, 1)`（同 Type 不同 Variant 这一维也进了表）、
   `???'s Only Friend → (3, 77)`（名字里那三个问号是"三字符组"那个坑的现场）；
   ★ 并且钉住**写明的偏离**：`"Potato Dummy"` 查不到 ⇒ `0` / `-1`（与"没装那个模组的 PC"一致）；
   ★★ 这段断言**第一次跑就抓到一个真功能缺陷**：名字块的下标按 `len + 2` 算，而相邻字符串
   字面量在 C++ 里是**先拼接**（隐式 `\0` 只有整串末尾一个）⇒ 第 i 条偏 i 字节 ⇒
   `GetEntityTypeByName("Monstro")` 恒返回 `0`。生成器自己的门禁当时是绿的 ——
   因为它把同一个错误模型抄了一遍。这就是"纯查表也要有真行为测试"的理由。
3. **`Room:IsClear()`**：描述符 `+0x50` 的 bit0 就是判据（1 ⇒ true，0 ⇒ false）；
   ★ 2026-10-01（批次 250）：**描述符读不到时回退 `false`、不再报错**。本用例初建（批次 207）
   时的口径是"报错而不是答 false"，理由是"编 false 会让模组按'这屋没清'行事，是拿假数据影响
   判断"。批次 250 权衡后**推翻**它：一次 Lua 错误会摘掉**整条模组回调**（2026-10-01 的
   GoodTrip 真机事故：`scripts/floor.lua:12` 抛错 ⇒ 功能全无、设置页也不注册），代价是一整个
   模组而不是一个值；而 PC 上这一步根本不失败（绑定层直接读有效对象的字段，没有"解析"这一步）。
   实现 = `runtime/src/interfaces/lua/remaining_api.cpp` 的 `RoomIsClear`：三处 `luaL_error`
   都换成 `PushNativeFallbackBoolean(state, kFbRoomIsClear, false)`。
   证据 = `dist/change-archive-20261001/250-native-state-fallback/change.patch` 的 `RoomIsClear`
   段、`README.md` 第五节（同步反转了 5 条同类门禁）、`native_state_fallback.hpp` 的三句话口径。
   ⇒ 门禁**同步反转**为"必须不报错、且答布尔 `false`"（still fail-able：报错或答非 false 都会红）；
   ★ 夹具断的是**第二段**链（`Room + 0x8` = 0）。第一段链（整个 Room 读不到）在 Lua 侧够不着 ——
   `Game():GetRoom()` 会先报错；真机上只有"上一帧留下的旧句柄"才碰得到，所以不在这里造；
4. **`Entity:HasEntityFlags`**：PC 的语义是 "has **all** named EntityFlags set"
   （`Entity.md:427`）⇒ `(字段 & 实参) == 实参`，**不是**"任意一位"。
   这就是它值得单独断言的地方：写反了不报错，只会让 MCM 把"友方 + 别的位"的实体也当成危险；
5. **`Entity:IsActiveEnemy`**：尾部参数可省略（形状 `BoolOpt1`，省略 = `false` = PC 缺省），
   多给参数必须报错；宿主上没有引擎入口 ⇒ **安静返回 `false`**（模组不会被打断）；
6. **`Entity:ToProjectile`**：非投射物 ⇒ `nil`（PC 契约 `Entity.md:653` 的 `data-altreturn='nil'`）；
   是投射物 ⇒ 返回投射物视图；**已经是投射物视图再调一次 ⇒ 返回同一个对象**（身份相等，
   PC 的 `ToPickup`/`ToPlayer` 一族都是这个口径）。
   ★ 拿"非玩家句柄"的办法：夹具把玩家的 `Entity.Parent` 指针（`+0x390`）指到**另一张实体**，
   脚本用 `player.Parent` 取它。之所以绕这一下 —— `Isaac.GetPlayer(i)` 要求 vptr **精确**
   等于 `Entity_Player`（`ResolveEntityPlayer` 的判据），塞不进一张投射物；而房间实体容器
   （`Isaac.GetRoomEntities`）要先过"容器指纹"校验，夹具造不出来。
   `Parent` 是无类型门槛的指针字段（读到什么就按 `Entity` 视图给出去），正好够用。
   ★★ 这一段也抓到一个**真缺陷**：`entity:ToProjectile()` 拿到的投射物视图上，
   `:ToProjectile()`（以及**所有**走统一句柄校验的 `Entity` 方法，共 20 余处）会报
   `expected an Entity, EntityPlayer or EntityPickup` —— 校验口少认了 `EntityProjectile`
   元表，导致 `EntityToProjectile()` 里的"返回自己"分支是死代码。已修
   （`runtime/src/interfaces/lua/isaac_api.cpp` 的 `CheckEntityHandle`）。
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

#: 伪造 GOT 槽里的屏幕尺寸（必须能被 float 精确表示，脚本用 `==` 比对）。
SCREEN_WIDTH = 1280.0
SCREEN_HEIGHT = 720.0
#: 伪造的实体标志字：`EntityFlag.FLAG_NO_STATUS_EFFECTS`(1<<0) | `FLAG_FRIENDLY`(1<<29)。
#: 用**两个真实枚举位**（脚本通过全局 `EntityFlag` 取名字，两边不会写歪）。
ENTITY_FLAGS = (1 << 0) | (1 << 29)
#: 房间描述符 `+0x50` 的 bit0（`kRoomDescriptorClearOffset` / `kRoomClearFlagBit`）。
ROOM_FLAGS_CLEAR = 0x1


def host_compilers() -> tuple[str, str] | None:
    """(C 编译器, C++ 编译器)；缺任何一个就整体 skip，不伪装成通过。"""
    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None


def render_harness() -> str:
    """把 Python 侧的读数与 Lua 脚本注入 harness（`@NAME@` 占位，避免误替换同名标识符）。"""
    literals = (
        ("SCREEN_WIDTH", repr(float(SCREEN_WIDTH))),
        ("SCREEN_HEIGHT", repr(float(SCREEN_HEIGHT))),
        ("ENTITY_FLAGS", f"{ENTITY_FLAGS}ULL"),
        ("ROOM_FLAGS_CLEAR", f"{ROOM_FLAGS_CLEAR}U"),
    )
    text = HARNESS
    for name, value in literals:
        text = text.replace(f"@{name}@", value)
    return text.replace("@SCRIPT@", SCRIPT).lstrip()


class LuaApiGapMcmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        cc, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-mcm-api-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "mcm_api_harness.cpp"
        harness.write_text(render_harness(), encoding="utf-8")
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        objects = []
        for source in sorted(lua_root.glob("*.c")):
            if source.name in excluded:
                continue
            output = temporary / f"{source.stem}.o"
            build = subprocess.run(
                [cc, "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root),
                 "-c", str(source), "-o", str(output)], text=True, capture_output=True)
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            objects.append(output)
        cls.binary = temporary / "mcm_api_harness"
        build = subprocess.run(
            [cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *(str(path) for path in objects), "-o", str(cls.binary)],
            text=True, capture_output=True)
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_harness(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_screen_size_and_entity_names(self):
        """屏宽/屏高取自 GOT 槽；实体名是纯查表 ⇒ 宿主上能验到"返回值真的对"。"""
        result = self.run_harness("baseline")
        self.assertIn("MCM_API_OK scenario=baseline", result.stdout)

    def test_room_is_clear_follows_the_descriptor_bit(self):
        """描述符 `+0x50` 的 bit0 = 1 ⇒ true；= 0 ⇒ false；描述符读不到 ⇒ 回退 false 且不报错（批次 250）。"""
        self.run_harness("room_not_clear")
        self.run_harness("room_descriptor_missing")

    def test_to_projectile_positive_negative_and_identity(self):
        """非投射物 ⇒ nil；是投射物 ⇒ 投射物视图；再调一次 ⇒ 身份相等。"""
        self.run_harness("projectile")

    def test_without_an_engine_base_the_batch_degrades_silently(self):
        """没装 Hook 时：屏宽给 0、查名字照常工作、一条都不报错。"""
        result = self.run_harness("no_base")
        self.assertIn("MCM_API_OK scenario=no_base", result.stdout)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"
#include "room_descriptor_layout.hpp"
#include "runtime_constants.hpp"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 别的家族的观察面：本用例不碰它们。`ReadCurrentGameRoom` 是本用例真正要用的一条，
// 所以下面**强定义**覆盖共享弱默认桩（`runtime/tests/shared_lua_stubs.cpp`）。
GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::OwnerUnreadable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {
    return TextReadResult::OpenFailed;
}
}

namespace {

const char* kScriptTemplate = R"lua(@SCRIPT@)lua";

//: 给 Lua 侧的同名常量（`verifyScreenSize` 要拿它跟 `Isaac.GetScreenWidth()` 比）。
//: ★ 必须在 Lua 里也定义一遍 —— 只放在 C++ 侧的话 Lua 读到的是 `nil`，
//:   `1280.0 == nil` 恒为假，报出来的错误还是"got 1280.0"，看起来像读数错了。
const char* kLuaPrologue = "SCREEN_WIDTH = @SCREEN_WIDTH@\nSCREEN_HEIGHT = @SCREEN_HEIGHT@\n";

// 伪造 GOT 槽里的屏幕尺寸（与 Python 侧同一批字面量）。
constexpr float kScreenWidth = @SCREEN_WIDTH@;
constexpr float kScreenHeight = @SCREEN_HEIGHT@;

// --- 伪造的引擎内存 ---------------------------------------------------------
//
//   模块块[base + kGameOwnerGlobalSlotOffset]   = &g_Game 变量（槽里是变量地址，不是对象）
//   模块块[base + kIsaacScreenWidthSlotOffset]  = &g_ScreenWidth（**指向 float**的指针）
//   模块块[base + kIsaacScreenHeightSlotOffset] = &g_ScreenHeight
//   g_Game 变量                                 = Game*
//   Game + kGameRoomPointerOffset               = Room*
//   Game + kGamePlayerArrayBegin/EndOffset      = vector<Entity_Player*>
//   Room + kRoomDescriptorPointerOffset         = RoomDescriptor*
//   RoomDescriptor + kRoomDescriptorFlagsOffset = u32 玩法标志（bit0 = 已清）
//   Entity_Player 首字                          = base + kEntityPlayerVtableOffset
//   Entity_Player + kEntityParentOffset         = &g_OtherEntity（拿非玩家句柄的出口）
//   Entity_Projectile 首字                      = base + kEntityProjectileVtableOffset
constexpr std::size_t kGameBlockSize =
    kGamePlayerArrayCapacityOffset + sizeof(std::uint64_t);

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_DescriptorBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_OtherBytes;
std::vector<unsigned char> g_ScreenWidthBytes;
std::vector<unsigned char> g_ScreenHeightBytes;

std::uintptr_t g_EngineBase = 0;
//: 房间描述符指针是否给得出来。`false` = 房间拿得到的是一张"没有描述符"的 Room
//: （`Room:IsClear()` 的**第二段**链断在这里 ⇒ 批次 250 起**回退 `false`、不报错**）。
//: ★ 第一段链（整个 Room 读不到）**不是**用这个开关造的：那条路会让 `Game():GetRoom()`
//:   先报错，Lua 侧根本走不到 `IsClear()`；真机上只有"上一帧拿到的旧句柄"才碰得到。
bool g_DescriptorPresent = true;

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
    std::size_t moduleSize = kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t);
    moduleSize = moduleSize > kIsaacScreenWidthSlotOffset + sizeof(std::uint64_t)
                     ? moduleSize
                     : kIsaacScreenWidthSlotOffset + sizeof(std::uint64_t);
    moduleSize = moduleSize > kIsaacScreenHeightSlotOffset + sizeof(std::uint64_t)
                     ? moduleSize
                     : kIsaacScreenHeightSlotOffset + sizeof(std::uint64_t);
    g_ModuleBytes.assign(moduleSize, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGameBlockSize, 0);
    g_RoomBytes.assign(kRoomDescriptorPointerOffset + sizeof(std::uint64_t), 0);
    g_DescriptorBytes.assign(isaac::runtime::layout::kRoomDescriptorFlagsOffset + sizeof(std::uint32_t), 0);
    // 实体块要盖住标志字（`+kEntityFlagsOffset`）；按 `Entity_Player` 的大小分配，
    // 免得将来有人加一个"按对象大小校验"的守卫时这里先红。
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    // "另一张实体"要盖住 `Type`（`+0x38`）与 `ProjectileFlags`（`+0x428`）两处。
    g_OtherBytes.assign(kEntityProjectileFlagsOffset + sizeof(std::int32_t), 0);
    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    g_ScreenWidthBytes.assign(sizeof(float), 0);
    g_ScreenHeightBytes.assign(sizeof(float), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
}

// 玩家实体：vptr 精确等于 `Entity_Player`（`Isaac.GetPlayer` 就认这一条）+ 标志字 +
// 一个指向"另一张实体"的 `Parent` 指针（脚本靠它拿到非玩家句柄）。
void PublishPlayer(std::uint64_t flags) {
    WriteWord(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityFlagsOffset, flags);
    WriteWord(g_PlayerBytes, kEntityParentOffset, AddressOf(g_OtherBytes));
}

// `Entity:ToProjectile()` 的判据是"Type == 9 **且** 首字精确等于投射物 vtable"，
// 所以投射物场景就是把这两处改掉 —— 不需要真的构造一颗子弹。
// 非投射物场景给它 `Entity_Player` 的 vtable + Type 1，既过通用 `Entity` 校验、
// 又必然让 `ToProjectile` 答 nil。
void PublishOther(bool projectile) {
    WriteWord(g_OtherBytes, 0, g_EngineBase + (projectile ? kEntityProjectileVtableOffset
                                                          : kEntityPlayerVtableOffset));
    WriteAt<std::uint32_t>(g_OtherBytes, kEntityTypeOffset,
                           projectile ? kEntityTypeProjectile : kEntityTypePlayer);
    WriteAt<std::int32_t>(g_OtherBytes, kEntityProjectileFlagsOffset,
                          projectile ? 0x40000000 : 0);
}

void PublishBaseline(std::uint32_t roomFlags) {
    WriteWord(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteWord(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    WriteWord(g_ModuleBytes, kIsaacScreenWidthSlotOffset, AddressOf(g_ScreenWidthBytes));
    WriteWord(g_ModuleBytes, kIsaacScreenHeightSlotOffset, AddressOf(g_ScreenHeightBytes));
    WriteAt<float>(g_ScreenWidthBytes, 0, kScreenWidth);
    WriteAt<float>(g_ScreenHeightBytes, 0, kScreenHeight);

    WriteWord(g_GameBytes, kGameRoomPointerOffset, AddressOf(g_RoomBytes));
    WriteWord(g_RoomBytes, kRoomDescriptorPointerOffset,
              g_DescriptorPresent ? AddressOf(g_DescriptorBytes) : 0);
    WriteAt<std::uint32_t>(g_DescriptorBytes, isaac::runtime::layout::kRoomDescriptorFlagsOffset, roomFlags);

    WriteWord(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteWord(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteWord(g_GameBytes, kGamePlayerArrayEndOffset, AddressOf(g_PlayerArrayBytes) +
                                                          sizeof(std::uint64_t));
}

bool ExpectGlobal(const char* name, double expected) {
    double value = 0.0;
    if (!LuaRuntime::ReadLuaGlobalNumber(name, &value)) {
        std::printf("MCM_API_FAIL: global %s was never written\n", name);
        return false;
    }
    if (value != expected) {
        std::printf("MCM_API_FAIL: %s expected %.0f, got %.0f\n", name, expected, value);
        return false;
    }
    return true;
}

} // namespace

// 强定义覆盖共享弱默认桩：拿当前房间的那条（真机实现是**两级解引用**：
// `ownerSlot`（= `模块基址 + kGameOwnerGlobalSlotOffset`）→ 槽里的"指针变量地址" → `Game*`，
// 再从 `Game + kLevelCurrentRoomOffset` 取 Room；见 `runtime/source/game_observer.cpp` 的
// `ReadCurrentGameRoom`。★ 写成一级解引用就会让 `Game:GetRoom()` 恒报错 —— 这一版第一次
// 就是这个错）。
GameRoomObservation ReadCurrentGameRoom(uintptr_t ownerSlot, void** room) {
    if (ownerSlot == 0 || room == nullptr) return GameRoomObservation::OwnerUnreadable;
    std::uintptr_t owner = 0;
    std::uintptr_t game = 0;
    std::memcpy(&owner, reinterpret_cast<const void*>(ownerSlot), sizeof(owner));
    if (owner == 0) return GameRoomObservation::OwnerNull;
    std::memcpy(&game, reinterpret_cast<const void*>(owner), sizeof(game));
    if (game == 0) return GameRoomObservation::GameNull;
    std::uintptr_t current = 0;
    std::memcpy(&current, reinterpret_cast<const void*>(game + kGameRoomPointerOffset),
                sizeof(current));
    if (current == 0) return GameRoomObservation::RoomUnreadable;
    *room = reinterpret_cast<void*>(current);
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const std::string scenario = argv[1];
    if (scenario != "baseline" && scenario != "projectile" && scenario != "room_not_clear" &&
        scenario != "room_descriptor_missing" && scenario != "no_base") {
        return 91;
    }
    const bool withEngine = scenario != "no_base";

    CreateBlocks();
    if (withEngine) {
        LuaRuntime::SetEngineModuleBase(g_EngineBase);
        // `GameOwnerSlot()` 的发布点（真机在 Hook 安装期调用一次，参数是
        // `模块基址 + kGameOwnerGlobalSlotOffset`）：`Game:GetRoom()` /
        // `Room:IsClear()` 那一族读的是这个值，不是 `EngineModuleBase()`。
        LuaRuntime::SetGameBindings(g_EngineBase + kGameOwnerGlobalSlotOffset, 0);
        PublishPlayer(@ENTITY_FLAGS@);
        PublishOther(scenario == "projectile");
        g_DescriptorPresent = scenario != "room_descriptor_missing";
        PublishBaseline(scenario == "room_not_clear" ? 0U : @ROOM_FLAGS_CLEAR@);
    }

    const std::string script =
        "SCENARIO = '" + scenario + "'\n" + kLuaPrologue + kScriptTemplate;
    const auto result =
        LuaRuntime::InitializeFromBuffer(script.c_str(), script.size(), "@mcm_api.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        std::printf("MCM_API_FAIL: the Lua state did not initialize\n");
        return 2;
    }

    LuaRuntime::DispatchPostUpdate();
    if (LuaRuntime::TakeCallbackError()) {
        std::printf("MCM_API_FAIL: the Lua callback raised an error\n");
        return 1;
    }
    if (!ExpectGlobal("MCM_API_OK", 1.0)) return 1;
    std::printf("MCM_API_OK scenario=%s\n", scenario.c_str());
    return 0;
}
'''

SCRIPT = r'''
local mod = RegisterMod('MCM api gap probe', 1)

local function check(condition, message)
  if not condition then error(message, 2) end
end

local function describe(value)
  if value == nil then return 'nil' end
  return type(value) .. ':' .. tostring(value)
end

--: 错误文本里必须点出 API 名字（MCM 调这些的地方都没有 pcall，出错时唯一的线索就是这句）。
local function rejects(call, apiName, what)
  local ok, failure = pcall(call)
  check(not ok, what .. ' must raise, but it succeeded')
  check(string.find(tostring(failure), apiName, 1, true) ~= nil,
        what .. ' must name the API in its error, got ' .. tostring(failure))
end

-- ---------------------------------------------------------------------------
-- 屏幕尺寸（`Isaac.GetScreenWidth/GetScreenHeight`）
-- ---------------------------------------------------------------------------
local function verifyScreenSize(withEngine)
  if withEngine then
    check(Isaac.GetScreenWidth() == SCREEN_WIDTH,
          'GetScreenWidth must read the GOT slot, got ' .. describe(Isaac.GetScreenWidth()))
    check(Isaac.GetScreenHeight() == SCREEN_HEIGHT,
          'GetScreenHeight must read the GOT slot, got ' .. describe(Isaac.GetScreenHeight()))
  else
    -- 没装 Hook（`SetEngineModuleBase` 没被调用）⇒ 必须是 0 且**不报错**：
    -- 报错会把整条回调摘掉，0 只是让界面贴在左上角。
    check(Isaac.GetScreenWidth() == 0,
          'GetScreenWidth must degrade to 0 without an engine base, got '
          .. describe(Isaac.GetScreenWidth()))
    check(Isaac.GetScreenHeight() == 0,
          'GetScreenHeight must degrade to 0 without an engine base, got '
          .. describe(Isaac.GetScreenHeight()))
  end
  rejects(function() return Isaac.GetScreenWidth(1) end, 'GetScreenWidth',
          'Isaac.GetScreenWidth with an argument')
  rejects(function() return Isaac.GetScreenHeight(1) end, 'GetScreenHeight',
          'Isaac.GetScreenHeight with an argument')
end

-- ---------------------------------------------------------------------------
-- 实体名查表（`Isaac.GetEntityTypeByName` / `GetEntityVariantByName`）
-- ---------------------------------------------------------------------------
local function verifyEntityNames()
  -- 已知名字：值与生成表（`tools/entity_name_source.txt`）逐条对应。
  check(Isaac.GetEntityTypeByName('Monstro') == 20,
        'Monstro type, got ' .. describe(Isaac.GetEntityTypeByName('Monstro')))
  check(Isaac.GetEntityVariantByName('Monstro') == 0,
        'Monstro variant, got ' .. describe(Isaac.GetEntityVariantByName('Monstro')))
  -- 同 Type 不同 Variant ⇒ 说明 Variant 这一维真的进了表（不是恒 0）。
  check(Isaac.GetEntityTypeByName('Lokii') == 69,
        'Lokii type, got ' .. describe(Isaac.GetEntityTypeByName('Lokii')))
  check(Isaac.GetEntityVariantByName('Lokii') == 1,
        'Lokii variant, got ' .. describe(Isaac.GetEntityVariantByName('Lokii')))
  -- 名字里带三个问号：这是 C++ 历史三字符组那个坑的现场（生成器要把它写成 `\?`）。
  check(Isaac.GetEntityTypeByName("???'s Only Friend") == 3,
        "the trigraph name must be in the table, got "
        .. describe(Isaac.GetEntityTypeByName("???'s Only Friend")))
  check(Isaac.GetEntityVariantByName("???'s Only Friend") == 77,
        "the trigraph name's variant, got "
        .. describe(Isaac.GetEntityVariantByName("???'s Only Friend")))

  -- ★ 写明的偏离：模组自己加的实体名看不见 ⇒ 与"没装那个模组的 PC"一致（0 / -1）。
  --   这正是 MCM 那个 `if potatoType and potatoVariant > 0` 要防的情况。
  check(Isaac.GetEntityTypeByName('Potato Dummy') == 0,
        'a mod-only name must answer 0, got '
        .. describe(Isaac.GetEntityTypeByName('Potato Dummy')))
  check(Isaac.GetEntityVariantByName('Potato Dummy') == -1,
        'a mod-only name must answer -1, got '
        .. describe(Isaac.GetEntityVariantByName('Potato Dummy')))

  -- 参数不是字符串（含 nil）⇒ 按"查不到"处理（0 / -1），**不报错**。
  check(Isaac.GetEntityTypeByName(nil) == 0, 'a nil name must answer 0, not raise')
  check(Isaac.GetEntityTypeByName(42) == 0, 'a numeric name must answer 0, not raise')
  check(Isaac.GetEntityVariantByName(nil) == -1, 'a nil name must answer -1, not raise')

  -- 参数个数错才报错（0 个、2 个都要报，且点出 API 名字）。
  rejects(function() return Isaac.GetEntityTypeByName() end, 'GetEntityTypeByName',
          'GetEntityTypeByName without a name')
  rejects(function() return Isaac.GetEntityTypeByName('a', 'b') end, 'GetEntityTypeByName',
          'GetEntityTypeByName with two names')
  rejects(function() return Isaac.GetEntityVariantByName() end, 'GetEntityVariantByName',
          'GetEntityVariantByName without a name')
end

-- ---------------------------------------------------------------------------
-- `Room:IsClear()`
-- ---------------------------------------------------------------------------
local function verifyRoomIsClear(expected)
  local room = Game():GetRoom()
  check(room ~= nil, 'Game():GetRoom() must return a room handle')
  check(room:IsClear() == expected,
        'IsClear must follow descriptor +0x50 bit0 (expected ' .. tostring(expected) .. '), got '
        .. describe(room:IsClear()))
  rejects(function() return room:IsClear(1) end, 'IsClear', 'Room:IsClear with an argument')
end

local function verifyUnreadableRoom()
  -- ★ 2026-10-01（批次 250）：口径已**反转** —— 描述符读不到时**回退 `false`、不再报错**。
  --   旧口径（本用例初建的批次 207）要求"报错而不是答 false"，理由是"编 false 会让模组按
  --   '这屋没清'行事"。批次 250 推翻它：一次 Lua 错误会摘掉**整条模组回调**（2026-10-01 的
  --   GoodTrip 真机事故），代价是一整个模组而不是一个值；PC 上这一步根本不会失败（直接读字段、
  --   没有"解析"这一步）。实现见 `remaining_api.cpp` 的 `RoomIsClear` 三处
  --   `PushNativeFallbackBoolean(state, kFbRoomIsClear, false)`；政策见 `native_state_fallback.hpp`，
  --   证据见 `dist/change-archive-20261001/250-native-state-fallback/change.patch` 的 `RoomIsClear` 段。
  --   ★ 保护价值保留（可失败）：必须**不抛错**、且必须给**布尔 `false`**（不是 nil / 不是 true）。
  local room = Game():GetRoom()
  check(room ~= nil, 'Game():GetRoom() must return a room handle')
  local ok, value = pcall(function() return room:IsClear() end)
  check(ok, 'IsClear must not raise when the room descriptor cannot be read')
  check(value == false,
        'IsClear must fall back to false when the room descriptor cannot be read, got '
        .. describe(value))
end

-- ---------------------------------------------------------------------------
-- `Entity:HasEntityFlags` / `IsActiveEnemy` / `ToProjectile`
-- ---------------------------------------------------------------------------
local function verifyEntityFlags()
  local player = Isaac.GetPlayer(0)
  check(player ~= nil, 'Isaac.GetPlayer(0) must return a handle')

  local friendly = EntityFlag.FLAG_FRIENDLY            -- 1 << 29（伪造内存里置着）
  local noStatus = EntityFlag.FLAG_NO_STATUS_EFFECTS   -- 1 << 0 （伪造内存里置着）
  local absent = EntityFlag.FLAG_NO_QUERY              -- 1 << 46（伪造内存里**没**置）

  check(player:HasEntityFlags(friendly) == true, 'a set flag must answer true')
  check(player:HasEntityFlags(noStatus) == true, 'the other set flag must answer true')
  check(player:HasEntityFlags(friendly | noStatus) == true,
        'both set flags together must answer true')
  -- ★ 关键语义（PC 契约 `Entity.md:427` 的 "has **all** named EntityFlags set"）：
  --   掩码里混进一个**没置**的位就必须答 false —— 写成"任意一位"会静默答 true。
  check(player:HasEntityFlags(friendly | absent) == false,
        'a mask with one missing bit must answer false (has ALL, not ANY)')
  check(player:HasEntityFlags(absent) == false, 'a missing flag must answer false')

  -- 掩码必须是整数；参数个数必须是 1（`FieldApiHandler` 的 `U64FlagsAllSet` 分支）。
  rejects(function() return player:HasEntityFlags() end, 'HasEntityFlags',
          'HasEntityFlags without a mask')
  rejects(function() return player:HasEntityFlags(true) end, 'HasEntityFlags',
          'HasEntityFlags with a boolean mask')
  rejects(function() return player:HasEntityFlags(1, 1) end, 'HasEntityFlags',
          'HasEntityFlags with two masks')
end

local function verifyIsActiveEnemy()
  local player = Isaac.GetPlayer(0)
  -- ★ 尾部参数**可省略**（形状 `BoolOpt1`；省略时寄存器保持 0 = `includeDead == false`
  --   = PC 的缺省值）。MCM 的 `RoomIsSafe()` 正是不传参地调它。
  local omitted = pcall(function() return player:IsActiveEnemy() end)
  check(omitted, 'IsActiveEnemy() must accept the omitted trailing argument')
  local provided = pcall(function() return player:IsActiveEnemy(false) end)
  check(provided, 'IsActiveEnemy(false) must be accepted')
  local providedTrue = pcall(function() return player:IsActiveEnemy(true) end)
  check(providedTrue, 'IsActiveEnemy(true) must be accepted')
  -- 宿主上没有引擎入口 ⇒ 安静给 false（不报错：报错会把 MCM 的回调整条摘掉）。
  check(player:IsActiveEnemy() == false,
        'IsActiveEnemy must answer false when the engine entry is unavailable, got '
        .. describe(player:IsActiveEnemy()))
  rejects(function() return player:IsActiveEnemy(false, false) end, 'IsActiveEnemy',
          'IsActiveEnemy with two arguments')
end

local function verifyToProjectile(expectedProjectile)
  local player = Isaac.GetPlayer(0)
  check(player ~= nil, 'Isaac.GetPlayer(0) must return a handle')
  -- ★ 非玩家句柄从 `Parent` 指针字段来（夹具把玩家的 `Parent` 指到另一张实体）：
  --   `Isaac.GetPlayer` 只认精确的 `Entity_Player` vptr，塞不进投射物；
  --   房间实体容器要先过指纹校验，宿主夹具造不出来。
  local other = player.Parent
  check(other ~= nil, 'the fixture must expose a second entity through Entity.Parent')
  local converted = other:ToProjectile()
  if not expectedProjectile then
    -- 非投射物 ⇒ nil（PC 契约 `Entity.md:653` 的 `data-altreturn='nil'`），不报错。
    check(converted == nil,
          'ToProjectile on a non-projectile must answer nil, got ' .. describe(converted))
    check(pcall(function() return other:ToProjectile() end),
          'ToProjectile on a non-projectile must not raise')
  else
    check(converted ~= nil, 'ToProjectile on a projectile must answer a handle')
    -- ★ 身份相等：底层已经是投射物 ⇒ PC 返回自己。`lua_pushvalue` 让"再调一次"拿到
    --   同一个 userdata（不是两个内容相同的新对象）。
    local again = converted:ToProjectile()
    check(again == converted,
          'ToProjectile on a projectile view must return the same object')
  end
  rejects(function() return other:ToProjectile(1) end, 'ToProjectile',
          'ToProjectile with an argument')
end

-- ---------------------------------------------------------------------------
local function run()
  check(SCENARIO ~= nil, 'the scenario must be set')
  verifyScreenSize(SCENARIO ~= 'no_base')
  verifyEntityNames()

  if SCENARIO == 'no_base' then
    MCM_API_OK = 1
    return
  end

  verifyEntityFlags()
  verifyIsActiveEnemy()
  verifyToProjectile(SCENARIO == 'projectile')

  if SCENARIO == 'room_descriptor_missing' then
    verifyUnreadableRoom()
  else
    verifyRoomIsClear(SCENARIO ~= 'room_not_clear')
  end

  MCM_API_OK = 1
end

mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
  -- 先把失败原因打出来再往上抛：运行时的 `TakeCallbackError()` 只给一个布尔，
  -- 看不到"到底哪一条断言红了"（脚本正文是一大段，没有这行就只能二分）。
  local ok, failure = pcall(run)
  if not ok then
    print('SCRIPT_FAIL: ' .. tostring(failure))
    error(failure, 0)
  end
end)
'''
