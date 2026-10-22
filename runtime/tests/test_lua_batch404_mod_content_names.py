"""门禁：`Isaac.GetItemIdByName` / `GetTrinketIdByName` / `GetCardIdByName` 的**模组追加层**
（批次 404，2026-10-07）。

## 这一批是什么

真机读数（批次 402）里 `Trinity/main.lua:67` 的
`EntityPlayer:AddCollectible type is outside uint32 range`，根因是
`Isaac.GetItemIdByName("Mirror of Hearts")` 查的是**本体契约快照**（`isaac_name_tables.cpp`），
模组自加的道具一律返回 `-1` ⇒ `AddCollectible(-1, 5)` 抛错 ⇒ **整条 `MC_POST_PLAYER_INIT`
回调被摘掉** ⇒ Peter 拿不到那件道具（只剩引擎按 `players.xml` 的 `items="493"` 发的 Adrenaline）。

修法（与批次 401 的 `GetPlayerTypeByName` 同构）：在装载期把每个模组的
`content/items.xml`（`<passive>/<active>/<familiar>` → 收藏品；`<trinket>` → 饰品）与
`content/pocketitems.xml`（`<card>/<rune>` → 卡牌）里声明的名字，按**引擎喂入顺序**追加进
运行时可变的层（`runtime/source/program/mod_content_names.*`）。

id 规则（批次 404 逐条取证，见 `mod_content_names.hpp` 表头 / 存档 README）：
**id = 本体该类条数 + 该条目在本模组该 xml 里的同类出现顺序（0 基），跨模组按喂入顺序累加。**
本体条数：收藏品 **733**、饰品 **190**、卡牌 **98**（逐条来自引擎反汇编的 resize 立即数）。

## 这条门禁钉六件事（与作业单逐条对应）

1. **本体各表逐值不变** —— 静态表（`collectibles.txt` / `cards.txt` / `player_types.txt`）不许被本批改；
   端到端里 `GetItemIdByName("Brimstone") == 118`、`GetTrinketIdByName("Lucky Toe") == 42` 逐值钉住。
2. **追加顺序 = 喂入顺序** —— 宿主按"逐模组喂入"断言 id 是 733/734/735、190/191；静态侧钉住
   喂入循环里的调用点（`mod_menu_native.cpp` 的 `LoadEngineModContent`）。
3. **幂等** —— 同一个 `(modKey, 文件)` 喂两次只算一次。
4. **坏 XML 不抛错、不挤错位置** —— 截断的 items.xml 跳过该模组，**下一个**模组仍从 733 起；
   无名条目仍占 id、显式负 id 的卡牌不占 id（各钉一条）。
5. **端到端** —— 真 Lua 下 `Isaac.GetItemIdByName("Mirror of Hearts")` 返回**该模组实际分配的
   那个 id**（用夹具模拟引擎的 id 分配，**不**写死真机上某个具体数字）；本体名字逐值不变。
6. **本体优先（值层面）与 `AddCollectible` 越界不再抛错** —— 模组卡牌与本体重名时返回本体 id；
   `AddCollectible(-1, ...)` 变"No-op + `false`"（与批次 398 的 `HasCollectible` 同形）。

## 宿主验到了什么、没验到什么

* **验到**：追加层的解析 / 分族 / 顺序 / 幂等 / 坏 XML 处置、静态表与追加层的优先级、
  三条 `Isaac.Get*ByName` 的**真 Lua 路径**返回值。
* **没验**：真机上"引擎把 items.xml 喂进 `ItemConfig` 之后 id 确实等于我们推的那个值"
  —— 宿主没有引擎（只有我们自己的静态表 + 追加层）。这一条只能真机：选 Peter 进局，
  看 `Trinity/main.lua:67` 的 `AddCollectible` 是否不再抛错、Peter 是否拿到 "Mirror of Hearts"。
"""

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
GEN_IMPL = SOURCE / "program" / "isaac_name_tables.cpp"
NEW_HEADER = SOURCE / "program" / "mod_content_names.hpp"
NEW_IMPL = SOURCE / "program" / "mod_content_names.cpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
MOD_MENU_NATIVE = SOURCE / "mod_menu_native.cpp"
SUPPORT = ROOT / "runtime" / "tests" / "test_support.py"
GEN = ROOT / "tools" / "generate_isaac_name_tables.py"
COLLECTIBLES_SRC = ROOT / "tools" / "isaac_name_source" / "collectibles.txt"
TRINKETS_SRC = ROOT / "tools" / "isaac_name_source" / "trinkets.txt"

#: Trinity 风格的一份 items.xml（与语料 `analysis/mod-corpus/Trinity/content/items.xml` 同形：
#: 3 个被动 + 3 个主动 + 3 个饰品，`<trinket>` 就在 `<items>` 里 —— 本游戏没有 `trinkets.xml`）。
TRINITY_ITEMS_XML = (
    '<items gfxroot="gfx/items/" version="1">'
    '<passive id="0" name="D-Clover" />'
    '<passive id="1" name="Paper Knife" />'
    '<passive id="2" name="Worn Tire" />'
    '<active id="3" name="Mirror of Hearts" />'
    '<active id="4" name="Hacker Laptop" />'
    '<active id="5" name="Chessboard" />'
    '<trinket name="Old Credit Card" />'
    "<trinket name=\"Maggie's Drawing\" />"
    '<trinket name="Fire Killer" />'
    "</items>"
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "program/mod_content_names.hpp"
#include "program/isaac_name_tables.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

int Lookup(isaac::runtime::ModContentNameFamily family, const char* name) {
    return static_cast<int>(isaac::runtime::LookupModContentName(family, name, std::strlen(name)));
}

int Base(isaac::runtime::IsaacNameKind kind, const char* name) {
    return static_cast<int>(isaac::runtime::LookupIsaacName(kind, name, std::strlen(name)));
}

void IngestItems(const char* key, const char* xml) {
    (void)isaac::runtime::IngestModContentXml(isaac::runtime::ModContentFileKind::Items, key, xml,
                                              std::strlen(xml));
}

void IngestPocket(const char* key, const char* xml) {
    (void)isaac::runtime::IngestModContentXml(isaac::runtime::ModContentFileKind::PocketItems, key,
                                              xml, std::strlen(xml));
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    isaac::runtime::ResetModContentNamesForTests();
    using F = isaac::runtime::ModContentNameFamily;

    if (std::strcmp(scenario, "order") == 0) {
        // 两个模组、按喂入顺序：ModA（2 收藏品 + 1 饰品）、ModB（1 收藏品 + 1 饰品）。
        IngestItems("ModA", "<items><passive name=\"A0\"/><active name=\"A1\"/><trinket name=\"T0\"/></items>");
        IngestItems("ModB", "<items><familiar name=\"B0\"/><trinket name=\"T1\"/></items>");
        std::printf("B404 order=%d,%d,%d,%d,%d\n", Lookup(F::Collectible, "A0"),
                    Lookup(F::Collectible, "A1"), Lookup(F::Collectible, "B0"),
                    Lookup(F::Trinket, "T0"), Lookup(F::Trinket, "T1"));
        return 0;
    }
    if (std::strcmp(scenario, "idempotent") == 0) {
        IngestItems("ModA", "<items><passive name=\"A0\"/><trinket name=\"T0\"/></items>");
        IngestItems("ModA", "<items><passive name=\"A0\"/><trinket name=\"T0\"/></items>");  // 重复
        IngestItems("ModB", "<items><passive name=\"B0\"/></items>");
        const auto& stats = isaac::runtime::ModContentNameStatistics();
        std::printf("B404 idem=%d,%d,%d dup=%u\n", Lookup(F::Collectible, "A0"),
                    Lookup(F::Collectible, "B0"), Lookup(F::Trinket, "T0"),
                    stats.duplicateFiles);
        return 0;
    }
    if (std::strcmp(scenario, "malformed") == 0) {
        // 截断的 items.xml（标签没有闭合的 `>`）⇒ 该模组整份跳过；下一个模组仍从 733 起。
        IngestItems("Bad", "<items><passive name=\"Broken\"");
        IngestItems("Good", "<items><passive name=\"G0\"/><passive name=\"G1\"/></items>");
        const auto& stats = isaac::runtime::ModContentNameStatistics();
        std::printf("B404 bad=%d,%d malformed=%u broken=%d\n", Lookup(F::Collectible, "G0"),
                    Lookup(F::Collectible, "G1"), stats.malformedFiles,
                    Lookup(F::Collectible, "Broken"));
        return 0;
    }
    if (std::strcmp(scenario, "families") == 0) {
        // items.xml 里收藏品与饰品**交错**但各自独立推进；卡牌走 pocketitems.xml。
        IngestItems("M", "<items><passive name=\"C0\"/><trinket name=\"K0\"/>"
                         "<active name=\"C1\"/><trinket name=\"K1\"/></items>");
        IngestPocket("M", "<pocketitems><card name=\"D0\"/><rune name=\"R0\"/>"
                          "<card name=\"D1\"/></pocketitems>");
        std::printf("B404 fam=%d,%d,%d,%d,%d,%d,%d\n", Lookup(F::Collectible, "C0"),
                    Lookup(F::Collectible, "C1"), Lookup(F::Trinket, "K0"),
                    Lookup(F::Trinket, "K1"), Lookup(F::Card, "D0"), Lookup(F::Card, "R0"),
                    Lookup(F::Card, "D1"));
        return 0;
    }
    if (std::strcmp(scenario, "noname") == 0) {
        // 无名条目**仍占 id**（引擎照样 append）：N0=733、无名条目吃掉 734、N1=735。
        IngestItems("M", "<items><passive name=\"N0\"/><passive/><passive name=\"N1\"/></items>");
        const auto& stats = isaac::runtime::ModContentNameStatistics();
        std::printf("B404 noname=%d,%d unnamed=%u consumed=%u\n", Lookup(F::Collectible, "N0"),
                    Lookup(F::Collectible, "N1"), stats.unnamedEntries, stats.consumedIds);
        return 0;
    }
    if (std::strcmp(scenario, "cardneg") == 0) {
        // 显式负 id 的卡牌引擎整条跳过（`LoadPocketItems` 的 `tbnz w25,#0x1f`）⇒ 不占 id。
        IngestPocket("M", "<pocketitems><card id=\"-1\" name=\"Neg\"/>"
                          "<card name=\"P0\"/></pocketitems>");
        const auto& stats = isaac::runtime::ModContentNameStatistics();
        std::printf("B404 cardneg=%d neg=%d skipped=%u\n", Lookup(F::Card, "P0"),
                    Lookup(F::Card, "Neg"), stats.skippedEntries);
        return 0;
    }
    if (std::strcmp(scenario, "collide") == 0) {
        // ★ 模组卡牌**故意重名**本体卡牌（`Chaos Card` 本体 = 42）：引擎查名是从下标 0 起
        //   线性扫、命中第一个 ⇒ 本体那张先被找到，返回 **42**（不是追加层的 98）。
        //   这条钉死"本体优先"在**值层面**成立 —— 刚写这篇实现时正是栽在这一点上。
        IngestPocket("M", "<pocketitems><card name=\"Chaos Card\"/></pocketitems>");
        const char* script =
            "print('B404 collide=' .. Isaac.GetCardIdByName('Chaos Card'))";
        const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b404c.lua");
        static_cast<void>(result);
        std::printf("B404 collide_cpp=%d\n", Lookup(F::Card, "Chaos Card"));
        return 0;
    }
    if (std::strcmp(scenario, "lua") == 0) {
        // 夹具模拟引擎的 id 分配：把 Trinity 那份 items.xml / 一份 pocketitems.xml 喂进追加层，
        // 再真跑 Lua 查名字。★ 用 `print` 回读（宿主真 Lua 路径），**不**依赖
        // `InitializeFromBuffer` 返回 `Success`（这段脚本没有登记回调，会以
        // `MissingPostUpdateCallback` 收尾，但 `print` 早已落到 stdout）。
        IngestItems("Trinity", @TRINITY_ITEMS_XML@);
        IngestPocket("Trinity", "<pocketitems><card id=\"0\" name=\"Trinity Card\"/></pocketitems>");
        // 同时打印"我们追加层自己分配的那个 id"（C++ 侧直接查），供门禁比对 Lua 侧 ——
        // 这样**不必**在测试里写死真机上某个具体数字。
        const char* script =
            "print('B404 lua=' .. Isaac.GetItemIdByName('Mirror of Hearts') .. ',' .. "
            "Isaac.GetTrinketIdByName('Maggie\\'s Drawing') .. ',' .. "
            "Isaac.GetCardIdByName('Trinity Card') .. ',' .. "
            "Isaac.GetItemIdByName('Brimstone') .. ',' .. "
            "Isaac.GetTrinketIdByName('Lucky Toe') .. ',' .. "
            "Isaac.GetItemIdByName('NoSuchItemXYZ'))";
        const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b404.lua");
        static_cast<void>(result);
        std::printf("B404 cpp=%d,%d,%d,%d\n", Lookup(F::Collectible, "Mirror of Hearts"),
                    Lookup(F::Trinket, "Maggie's Drawing"), Lookup(F::Card, "Trinity Card"),
                    Base(isaac::runtime::IsaacNameKind::Collectible, "Brimstone"));
        return 0;
    }
    return 91;
}
'''


class ModContentNamesBatch404Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b404-")
        harness_source = HARNESS.replace(
            "@TRINITY_ITEMS_XML@", '"' + TRINITY_ITEMS_XML.replace('"', '\\"') + '"')
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=harness_source,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_append_order_is_the_feed_order(self):
        """② 追加顺序 = 喂入顺序：ModA 的收藏品先拿 733/734、ModB 的拿 735；饰品同理 190/191。

        ★ 顺序错了 id 就错，而且是**静默错**（拿到错道具、不报错）—— 所以逐个钉死。
        """
        out = self.run_scenario("order")
        self.assertIn("B404 order=733,734,735,190,191", out)

    def test_same_mod_file_fed_twice_is_idempotent(self):
        """③ 幂等：同一个 `(modKey, items.xml)` 喂两次，第二次整份忽略（id 不追加两次）。"""
        out = self.run_scenario("idempotent")
        self.assertIn("B404 idem=733,734,190 dup=1", out)

    def test_malformed_xml_is_skipped_and_does_not_shift_others(self):
        """④ 坏 XML 不抛错、不挤错位置：坏模组跳过，下一个模组仍从 733 起。"""
        out = self.run_scenario("malformed")
        self.assertIn("B404 bad=733,734 malformed=1 broken=-1", out)

    def test_families_advance_independently(self):
        """①③ 收藏品 / 饰品 / 卡牌三条计数器**各自独立**推进（同一 items.xml 交错也不串）。

        收藏品 733/734、饰品 190/191、卡牌 98/99/100（`<rune>` 与 `<card>` 同族）。
        """
        out = self.run_scenario("families")
        self.assertIn("B404 fam=733,734,190,191,98,99,100", out)

    def test_unnamed_entry_still_consumes_an_id(self):
        """④ 无名条目仍占 id（与引擎"往向量里追加一格"同语义）：N0=733、N1=735。"""
        out = self.run_scenario("noname")
        self.assertIn("B404 noname=733,735 unnamed=1 consumed=3", out)

    def test_negative_card_id_is_skipped_without_consuming_an_id(self):
        """④ 显式负 id 的卡牌整条跳过、不占 id（`LoadPocketItems` 的 `tbnz w25,#0x1f`）。"""
        out = self.run_scenario("cardneg")
        self.assertIn("B404 cardneg=98 neg=-1 skipped=1", out)

    def test_end_to_end_lua_get_by_name(self):
        """⑤ 端到端：真 Lua 下查模组道具 / 饰品 / 卡牌，返回**追加层分配的那个 id**。

        ★ 用 C++ 侧直接查同一个名字的结果当"期望值"（`B404 cpp=...`）⇒ **不写死真机数字**；
          再钉住本体名字逐值不变（`Brimstone` = 118，`Lucky Toe` = 42）、未知名字 = `-1`。
        """
        out = self.run_scenario("lua")
        lua_line = next(line for line in out.splitlines() if line.startswith("B404 lua="))
        cpp_line = next(line for line in out.splitlines() if line.startswith("B404 cpp="))
        lua_ids = [int(part) for part in lua_line.split("=", 1)[1].split(",")]
        cpp_ids = [int(part) for part in cpp_line.split("=", 1)[1].split(",")]
        self.assertEqual(len(lua_ids), 6)
        self.assertEqual(len(cpp_ids), 4)
        mirror_lua, maggie_lua, card_lua, brimstone, lucky_toe, unknown = lua_ids
        mirror_cpp, maggie_cpp, card_cpp, brimstone_cpp = cpp_ids
        # 模组条目：Lua 侧 == 追加层自己分配的 id（不写死真机数字）。
        self.assertEqual(mirror_lua, mirror_cpp, f"Lua 与追加层对 Mirror of Hearts 不一致：{out}")
        self.assertEqual(maggie_lua, maggie_cpp, f"Lua 与追加层对 Maggie's Drawing 不一致：{out}")
        self.assertEqual(card_lua, card_cpp, f"Lua 与追加层对 Chaos Card 不一致：{out}")
        # 模组条目必须落在本体基准**之后**（收藏品 733、饰品 190、卡牌 98）。
        self.assertGreaterEqual(mirror_lua, 733, f"收藏品 id 落在本体区间里：{out}")
        self.assertGreaterEqual(maggie_lua, 190, f"饰品 id 落在本体区间里：{out}")
        self.assertGreaterEqual(card_lua, 98, f"卡牌 id 落在本体区间里：{out}")
        # 本体名字逐值不变。
        self.assertEqual(brimstone, 118, f"本体收藏品表被改动：{out}")
        self.assertEqual(brimstone_cpp, 118, f"本体收藏品表被改动：{out}")
        self.assertEqual(lucky_toe, 42, f"本体饰品表不对（契约 Isaac.md:467）：{out}")
        self.assertEqual(unknown, -1, f"未知名字应返回 -1：{out}")

    def test_body_name_wins_over_a_same_named_mod_card(self):
        """① 本体优先（值层面）：模组卡牌与本体重名时，`GetCardIdByName` 返回**本体那个 id**。

        引擎查名从下标 0 起线性扫、命中第一个 ⇒ 本体 `Chaos Card` = 42 先被找到；
        追加层里**同样**存着这个名字（它的 id 是 98），但绝不该返回 98。
        """
        out = self.run_scenario("collide")
        self.assertIn("B404 collide=42", out, out)
        self.assertIn("B404 collide_cpp=98", out, out)

    def test_add_collectible_out_of_range_is_a_safe_noop(self):
        """⑥ `AddCollectible` 越界**不再抛错**（源码层口径）。

        行为层那条由 `runtime/tests/test_lua_entity_player.py` 的 `valid` 场景真跑（那里有能造出
        `Isaac.GetPlayer(0)` 的伪造引擎）；这里只钉"手写处理器**不再**用 `luaL_error` 抛这条"，
        免得有人把越界报错改回去。契约（`EntityPlayer.md:137-139`）没有"越界报错"这一说；
        项目口径（`test_id_argument_policy.py` 表头）是"参数是枚举 id 时不钉取值范围"。
        真机抛错 ⇒ 派发器静默摘掉整条回调 ⇒ Peter 拿不到道具（本批起因）。
        """
        body = ISAAC_API.read_text(encoding="utf-8")
        # 那行历史错误文本只能留在注释里（注释是本批的证据链），代码里不许再有 `luaL_error` 抛它。
        code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("//"))
        self.assertNotIn("AddCollectible type is outside uint32 range", code)
        # 越界分支必须走"安全 no-op"：handler 里出现 `AddCollectible` 的 `lua_pushboolean(state, 0)`。
        # ★ 必须带 ` {` 找**定义**：文件上方还有它的前向声明（`... state);`），
        #   `body.index` 会先命中那一处。
        handler_at = body.index("int EntityPlayerAddCollectible(lua_State* state) {")
        handler_end = body.index("\nint ", handler_at + 4)  # 下一个顶层函数定义
        handler = body[handler_at:handler_end]
        self.assertIn("lua_pushboolean(state, 0)", handler)

    # ---------------------------------------------------------------- 本体表不许被改

    def test_body_collectible_table_is_unchanged(self):
        """① 本体收藏品表逐值不变（钉两个契约里给过的例子）。"""
        rows = {}
        for line in COLLECTIBLES_SRC.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            rows[fields[0]] = int(fields[1])
        self.assertEqual(rows.get("The Sad Onion"), 1)
        self.assertEqual(rows.get("Brimstone"), 118)

    def test_trinket_table_matches_the_pc_contract_example(self):
        """① 新加的饰品静态表与契约例子逐值一致（`Isaac.md:467`：Lucky Toe → 42）。"""
        rows = {}
        for line in TRINKETS_SRC.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            rows[fields[0]] = int(fields[1])
        self.assertEqual(rows.get("Lucky Toe"), 42)
        self.assertTrue(rows, "trinkets.txt 为空 —— 生成器没跑或被清空")

    # ---------------------------------------------------------------- 静态接线

    def test_lookups_consult_the_append_layer_only_as_a_fallback(self):
        """静态表**先查**（本体优先），只有未命中时才落到追加层（三条各一处）。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        for kind, family in (("Collectible", "Collectible"), ("Card", "Card"), ("Trinket", "Trinket")):
            with self.subTest(kind):
                static_at = body.index(f"LookupIsaacName(IsaacNameKind::{kind}")
                dynamic_at = body.index(f"LookupModContentName(ModContentNameFamily::{family}")
                self.assertLess(static_at, dynamic_at,
                                f"{kind}：静态表必须在追加层**之前**查（本体优先）")
        self.assertNotIn("WarnStubOnce(state, Stub::GetTrinketIdByName", body,
                         "GetTrinketIdByName 已经不是桩了（本批补了本体静态表 + 追加层）")

    def test_append_layer_is_wired_into_the_feed_loop(self):
        """② 追加层挂在**喂入循环**上（`LoadEngineModContent`），不是在别处自己排序。"""
        text = MOD_MENU_NATIVE.read_text(encoding="utf-8")
        self.assertIn("void FeedModContentNames(", text)
        self.assertIn("isaac::runtime::IngestModContentXml(file, directory, text, textLength)", text)
        body_at = text.index("bool LoadEngineModContent(")
        loop_at = text.index("ModMenuDiscoveredCount()", body_at)
        call_at = text.index("FeedModContentNames(directory, path, baseLength, sizeof(path))", body_at)
        end_at = text.index("RunPostLoadModsOnceIfDue(manager", body_at)
        self.assertGreater(call_at, loop_at, "追加层调用必须在喂入循环里（发现结果之后）")
        self.assertLess(call_at, end_at, "追加层调用必须在 PostLoadMods 收尾之前")
        # 两个文件名必须与 `kModContentFeedSpecs` 的前两项逐字一致（items / pocketitems），
        # 且**不能**去喂不存在的 `trinkets.xml` / `cards.xml`（那会静默查不到）。
        self.assertIn('kModContentItemsFileName[] = "items.xml"',
                      NEW_HEADER.read_text(encoding="utf-8"))
        self.assertIn('kModContentPocketItemsFileName[] = "pocketitems.xml"',
                      NEW_HEADER.read_text(encoding="utf-8"))

    def test_new_source_unit_is_in_the_host_harness_list(self):
        """新 TU 必须进宿主夹具清单 —— 否则所有宿主用例在链接期报未定义符号。"""
        support = SUPPORT.read_text(encoding="utf-8")
        self.assertIn('"program" / "mod_content_names.cpp"', support)

    def test_trinket_kind_is_appended_to_the_generator_tables(self):
        """新增的 `trinket` 只在 `TABLES` **末尾**（`IsaacNameKind` 的下标不许错位）。"""
        text = GEN.read_text(encoding="utf-8")
        self.assertIn('"trinket"', text)
        self.assertIn('"trinket": "items.xml"', text)
        impl = GEN_IMPL.read_text(encoding="utf-8")
        self.assertIn("kTrinketNameEntries", impl)
        self.assertIn("Isaac.GetTrinketIdByName", impl)

    def test_files_exist(self):
        for path in (NEW_HEADER, NEW_IMPL):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"缺 {path}")


if __name__ == "__main__":
    unittest.main()
