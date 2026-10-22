"""门禁：`needs_new_receiver` 桶里参数最简单的一批 8 条（批次 273，2026-10-02）。

## 这一批是什么

在批次 271/272 之后，剩下的 `needs_new_receiver` 里**参数形态只有标量 / `Vector` / `EntityRef`**
的 8 条。选批口径与 271 一样，而且更严：**该同名方法只有一个类有**（用嵌套名解析器扫全符号表）
⇒ 没有子类重写，不需要像 `Entity:TakeDamage` 那样在基类/子类之间挑一个。
（`GridEntityDoor:Open/Close`、`EntityNPC:Morph` 那种"同名类数 > 1"的**不收**。）

| API | 调用点 | 引擎入口 | 参数 |
| --- | --- | --- | --- |
| `Entity:AddFreeze(EntityRef, int)` | 2 | `Entity::AddFreeze @ 0x5E358` | EntityRef + 整数 |
| `Entity:AddPoison(EntityRef, int, float)` | 2 | `Entity::AddPoison @ 0x5E5F8` | EntityRef + 整数 + 浮点 |
| `EntityPlayer:AddBlueSpider(Vector)` | 4 | `Entity_Player::AddBlueSpider @ 0x2FB40C` | Vector（**返回 Entity**） |
| `EntityPlayer:AddGoldenHearts(int)` | 2 | `Entity_Player::AddGoldenHearts @ 0x2FC924` | 整数 |
| `EntityPlayer:AddMinisaac(Vector, bool=true)` | 2 | `Entity_Player::AddMinisaac @ 0x2AC1F4` | Vector（**返回 EntityFamiliar**） |
| `EntityPlayer:AddPill(PillColor)` | 2 | `Entity_Player::AddPill @ 0x2B0B80` | 枚举（整数） |
| `EntityPlayer:AnimateAppear()` | 2 | `Entity_Player::AnimateAppear @ 0x2E8184` | 无 |
| `EntityPlayer:DropTrinket(Vector, bool)` | 2 | `Entity_Player::DropTrinket @ 0x2A20D4` | Vector + 布尔 |

★ 两条返回实体的在**拿不到引擎时压 `nil`**（与 `Entity:ToPlayer()` 一族"转换/创建失败给 nil"同一口径）。
★ `AddGoldenHearts` 与 `AnimateAppear` 的入口 16 字节**完全相同**（同一编译器 prologue）——
区分靠偏移；本文件用静态判据把这件事钉住，免得以后有人拿守卫当唯一判据。

## 本文件钉什么、不钉什么

钉**接线、参数闸门、降级口径**；★ **不钉引擎那一步真的执行了**（宿主没有引擎）—— 那要真机，见 V24。
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

#: `(owner, 名字, 域内序号, 引擎常量前缀, C++ 处理器名)`
#:
#: ★ 最后一栏不是"owner + 名字"自动拼的：`Entity:AddFreeze` 对应的 C++ 名字是 `EntityAddFreeze`、
#:   `EntityPlayer:AddBlueSpider` 对应 `EntityPlayerAddBlueSpider` —— 拼法一致，但**不能靠拼**
#:   （写门禁时猜过一回，`int AddPill(...)` 根本不存在）。
APIS = (
    ("Entity", "AddFreeze", 0x0096, "kEntityAddFreeze", "EntityAddFreeze"),
    ("EntityPlayer", "AddBlueSpider", 0x0097, "kEntityPlayerAddBlueSpider",
     "EntityPlayerAddBlueSpider"),
    ("EntityPlayer", "AddGoldenHearts", 0x0098, "kEntityPlayerAddGoldenHearts",
     "EntityPlayerAddGoldenHearts"),
    ("EntityPlayer", "AddMinisaac", 0x0099, "kEntityPlayerAddMinisaac", "EntityPlayerAddMinisaac"),
    ("EntityPlayer", "AddPill", 0x009A, "kEntityPlayerAddPill", "EntityPlayerAddPill"),
    ("EntityPlayer", "AnimateAppear", 0x009B, "kEntityPlayerAnimateAppear",
     "EntityPlayerAnimateAppear"),
    ("EntityPlayer", "DropTrinket", 0x009C, "kEntityPlayerDropTrinket", "EntityPlayerDropTrinket"),
    ("Entity", "AddPoison", 0x009E, "kEntityAddPoison", "EntityAddPoison"),
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄 `test_lua_api_gap_batch3.py` 那套，只留本批要用的几格）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**，不是对象）
//   g_Game 变量            = Game*
//   Game + kGamePlayerArrayBegin/End = 只有一个元素的玩家指针数组
//   Entity_Player 首字      = base + kEntityPlayerVtableOffset（`ValidatedEntityPlayer` 要它）
// 有它才能真的走到"取接收者"那一步 —— 否则 `Isaac.GetPlayer(0)` 是 nil，参数闸门根本没被执行。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeGame() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    // 槽里放 `g_Game` **变量的地址**（与真实布局一致：槽指向变量，变量才指向对象）。
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    // 一个玩家：首字是 vtable，再填三个 `ValidatedEntityPlayer` 会看的字段。
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, 1);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, 0);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerIndexOffset, 0);
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
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "gates") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " local V = Vector(10, 20)"
            " print('B273 gh=' .. ok(function() return p:AddGoldenHearts(1) end)"
            "   .. ',' .. ok(function() return p:AddGoldenHearts() end)"
            "   .. ',' .. ok(function() return p:AddGoldenHearts('x') end))"
            " print('B273 pill=' .. ok(function() return p:AddPill(3) end)"
            "   .. ',' .. ok(function() return p:AddPill() end))"
            " print('B273 appear=' .. ok(function() return p:AnimateAppear() end)"
            "   .. ',' .. ok(function() return p:AnimateAppear(1) end))"
            " print('B273 drop=' .. ok(function() return p:DropTrinket(V, true) end)"
            "   .. ',' .. ok(function() return p:DropTrinket(true, true) end)"
            "   .. ',' .. ok(function() return p:DropTrinket(V) end))"
            " print('B273 spider=' .. ok(function() return p:AddBlueSpider(V) end)"
            "   .. ',' .. ok(function() return p:AddBlueSpider() end))"
            " print('B273 mini=' .. ok(function() return p:AddMinisaac(V) end)"
            "   .. ',' .. ok(function() return p:AddMinisaac(V, false) end)"
            "   .. ',' .. ok(function() return p:AddMinisaac(V, false, 1) end))"
            " print('B273 freeze=' .. ok(function() return p:AddFreeze(EntityRef(p), 60) end)"
            "   .. ',' .. ok(function() return p:AddFreeze(1, 60) end)"
            "   .. ',' .. ok(function() return p:AddFreeze(EntityRef(p)) end))"
            " print('B273 poison=' .. ok(function() return p:AddPoison(EntityRef(p), 60, 1.5) end)"
            "   .. ',' .. ok(function() return p:AddPoison(EntityRef(p), 60) end))"
            " print('B273 ret=' .. tostring(p:AddBlueSpider(V)) .. ',' .. tostring(p:AddMinisaac(V)))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b271.lua");
    static_cast<void>(result);
    return 0;
}

'''

class EntityMethodBatch273Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b273-")
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

    def test_all_eight_accept_their_documented_shapes(self):
        """八条的**合法形状都必须能调通**（宿主上引擎不可用 ⇒ 静默降级，不报错）。

        ★ 这一格是"参数个数/类型算错"那一类缺陷的钉子（批次 249 的形态：算错一次就每次抛错，
        错误还会把模组的整条回调摘掉）。
        """
        out = self.run_scenario("gates")
        self.assertIn("B273 gh=true,false,false", out)
        self.assertIn("B273 pill=true,false", out)
        self.assertIn("B273 appear=true,false", out)
        self.assertIn("B273 drop=true,false,false", out)
        self.assertIn("B273 spider=true,false", out)
        self.assertIn("B273 mini=true,true,false", out)
        self.assertIn("B273 freeze=true,false,false", out)
        self.assertIn("B273 poison=true,false", out)

    def test_entity_returning_two_give_nil_when_the_engine_is_unavailable(self):
        """★ 返回实体的两条在拿不到引擎时压 `nil`（不是空壳句柄、更不是报错）。

        与 `Entity:ToPlayer()` 一族同一口径：模组写 `if e then …` 照样成立。
        `AddMinisaac` 的 **`PlayAnim` 缺省值是 `true`**，写在契约签名里（本批唯一不靠推断的缺省值之一）。
        """
        out = self.run_scenario("gates")
        self.assertIn("B273 ret=nil,nil", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        body = ISAAC_API.read_text(encoding="utf-8")
        for owner, name, index, _prefix, _cpp in APIS:
            with self.subTest(name):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                    f'"{owner}", "{name}"',
                    catalog, f"catalog 里没有 {owner}:{name}")
                self.assertRegex(body, rf"\{{\s*(?i:0x0e01{index:04x}),\s*&\w*{name}\s*\}}",
                                 f"绑定表里没有 0x0E01{index:04X} → {name}")

    def test_each_api_has_an_offset_and_a_sixteen_byte_guard(self):
        constants = CONSTANTS.read_text(encoding="utf-8")
        for _owner, name, _index, prefix, cpp in APIS:
            with self.subTest(name):
                self.assertIn(f"{prefix}Offset = 0x", constants, f"{name} 缺偏移")
                self.assertIn(f"{prefix}ExpectedBytes", constants, f"{name} 缺 16 字节守卫")

    def test_guard_bytes_cannot_distinguish_two_functions(self):
        """★ `AddGoldenHearts` 与 `AnimateAppear` 的入口 16 字节**完全相同**。

        这不是笔误 —— 是同一套编译器 prologue。写这条判据的理由很直接：
        **守卫只能确认"这个地址上确实是我们要的那串指令"，不能用来区分两个函数**（区分靠偏移）。
        以后谁想把"守卫数组相同"当成重复或错误，会在这条门禁上看到原因。
        """
        path = Path(__file__).resolve().parent.parent / "source" / "runtime_constants.hpp"
        body = path.read_text(encoding="utf-8")
        assert "kEntityPlayerAddGoldenHeartsExpectedBytes" in body
        constants = CONSTANTS.read_text(encoding="utf-8")

        def guard(name: str) -> str:
            #: 只取 `= {` 之后的**字节部分** —— 名字当然不同（那正是不该比的）。
            start = constants.index(f"{name}ExpectedBytes = {{") + len(f"{name}ExpectedBytes = ")
            end = constants.index("};", start)
            return constants[start:end]

        self.assertEqual(guard("kEntityPlayerAddGoldenHearts"),
                         guard("kEntityPlayerAnimateAppear"),
                         "这两条本来就是同一段 prologue（若哪天不同了，说明注释要一起改）")
        #: 而偏移必须不同 —— 那才是真正的身份判据。
        self.assertIn("kEntityPlayerAddGoldenHeartsOffset = 0x2FC924", constants)
        self.assertIn("kEntityPlayerAnimateAppearOffset = 0x2E8184", constants)

    def test_all_eight_share_one_resolver_and_one_fallback_rule(self):
        """八条必须共用同一个取址助手与同一套降级口径（不各写一份）。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn("VectorHandle* VectorArgument(lua_State* state, int index)", body)
        self.assertIn("EntityRefBufferAt(state, 2)", body, "EntityRef 参数复用既有助手")
        for _owner, name, _index, prefix, cpp in APIS:
            with self.subTest(name):
                handler = body[body.index(f"int {cpp}(lua_State* state) {{"):]
                handler = handler[:handler.index("\n}\n")]
                self.assertIn(f"EntityMethodByExpectedBytes({prefix}Offset", handler,
                              f"{name} 没有走共用的 16 字节取址助手")


if __name__ == "__main__":
    unittest.main()
