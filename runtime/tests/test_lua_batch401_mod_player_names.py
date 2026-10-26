"""门禁：`Isaac.GetPlayerTypeByName` 的**模组角色追加层**（批次 401，2026-10-07）。

## 这一批是什么

语料模组 `Trinity` 在 `content/players.xml` 里加了 3 个自定义角色（Mary / Peter / Isaiah），
它们能选、能进局（引擎侧成立），但模组的角色专属 Lua 逻辑**静默失效** ——
因为 `Isaac.GetPlayerTypeByName("Mary")` 查的是**本体契约快照**（`isaac_name_tables.cpp`），
返回 `-1` ⇒ `Trinity/main.lua:59` 起 `player:GetPlayerType() == <id>` 全部早退（不报错、不崩）。

修法（**路线 A**）：在装载期把每个模组的 `content/players.xml` 里声明的角色名，按**引擎喂入顺序**
追加进一张运行时可变的层（`runtime/source/program/mod_player_names.*`）。
id 规则（批次 399 已取证）：**41 + 该角色在本模组 `players.xml` 里的 `<player>` 出现顺序（0 基），
跨模组按喂入顺序继续累加。**

## 这条门禁钉五件事（与作业单逐条对应）

1. **本体 41 条逐值不变** —— `tools/isaac_name_source/player_types.txt` 与生成物都不许被本批改。
2. **追加顺序 = 喂入顺序** —— 宿主侧按"逐模组喂入"的调用顺序断言 id 是 41 → 42 → 43；
   静态侧钉住喂入循环里的调用点（`mod_menu_native.cpp` 的 `LoadEngineModContent`）。
3. **幂等** —— 同一个 modKey 喂两次只算一次。
4. **坏 XML 不抛错、不挤错位置** —— 截断的 players.xml 跳过该模组，**下一个**模组仍从 41 起；
   `name` 缺失/为空的条目被跳过且**不占 id**。
5. **端到端** —— 真 Lua 状态下 `Isaac.GetPlayerTypeByName("Mary") == 41`。

## 宿主验到了什么、没验到什么

* **验到**：追加层的解析 / 排序 / 幂等 / 坏 XML 处置、静态表与追加层的优先级、
  以及 `Isaac.GetPlayerTypeByName` 这条**真 Lua 路径**的返回值。
* **没验**：真机上"引擎把 players.xml 喂进 `EntityConfig` 之后 id 确实等于我们推的那个值"
  —— 宿主没有引擎。这一条只能真机（选 Peter 打一枪：`Trinity/main.lua:129` 的
  `tear.SpawnerEntity:ToPlayer()` 那条错误环应消失，且角色专属逻辑生效）。
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
GEN_SOURCE = ROOT / "tools" / "isaac_name_source" / "player_types.txt"
GEN_IMPL = SOURCE / "program" / "isaac_name_tables.cpp"
NEW_HEADER = SOURCE / "program" / "mod_player_names.hpp"
NEW_IMPL = SOURCE / "program" / "mod_player_names.cpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
MOD_MENU_NATIVE = SOURCE / "mod_menu_native.cpp"
SUPPORT = ROOT / "runtime" / "tests" / "test_support.py"

#: 本体角色表（`tools/isaac_name_source/player_types.txt`）的**逐值快照** —— 本批**不许动**它。
#: `(名字, id, 堕落 id[或 -1])`，按生成器写的顺序（名字升序）。
#: ★ 首行是**转义后的原始字节**：源文件按注释约定把 `?` 写成 `\?`（`\\?\\?\\?`），
#:   这是 PC 契约快照的**原文形态**，比的是源文件、不是运行期解转义后的名字。
BODY_PLAYER_TYPES = (
    ("\\?\\?\\?", 4, 25),
    ("Apollyon", 15, 34),
    ("Azazel", 7, 28),
    ("Bethany", 18, 36),
    ("Black Judas", 12, -1),
    ("Cain", 2, 23),
    ("Eden", 9, 30),
    ("Esau", 20, -1),
    ("Eve", 5, 26),
    ("Isaac", 0, 21),
    ("Jacob", 19, 37),
    ("Judas", 3, 24),
    ("Keeper", 14, 33),
    ("Lazarus", 8, 29),
    ("Lazarus II", 11, -1),
    ("Lilith", 13, 32),
    ("Magdalene", 1, 22),
    ("Samson", 6, 27),
    ("The Forgotten", 16, 35),
    ("The Lost", 10, 31),
    ("The Soul", 17, 40),
)

#: Trinity 风格的一份 players.xml（Mary/Peter/Isaiah 三条，与语料同形）。
TRINITY_XML = (
    '<players root="gfx/characters/costumes/">'
    '<player name="Mary" skin="character_mary.png" costume="7" />'
    '<player name="Peter" items="493" costumeSuffix="peter" costume="104" />'
    '<player name="Isaiah" hp="2" items="85, 251" costumeSuffix="isaiah" costume="7" />'
    "</players>"
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "program/mod_player_names.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

int Lookup(const char* name) {
    return static_cast<int>(isaac::runtime::LookupModPlayerTypeName(name, std::strlen(name)));
}

void Ingest(const char* key, const char* xml) {
    (void)isaac::runtime::IngestModPlayersXml(key, xml, std::strlen(xml));
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    isaac::runtime::ResetModPlayerNamesForTests();

    if (std::strcmp(scenario, "order") == 0) {
        // 两个模组、按喂入顺序逐条追加：ModA 先（41/42）、ModB 后（43）。
        Ingest("ModA", "<players><player name=\"A0\"/><player name=\"A1\"/></players>");
        Ingest("ModB", "<players><player name=\"B0\"/></players>");
        std::printf("B401 order=%d,%d,%d\n", Lookup("A0"), Lookup("A1"), Lookup("B0"));
        return 0;
    }
    if (std::strcmp(scenario, "idempotent") == 0) {
        Ingest("ModA", "<players><player name=\"A0\"/><player name=\"A1\"/></players>");
        Ingest("ModA", "<players><player name=\"A0\"/><player name=\"A1\"/></players>");  // 重复
        Ingest("ModB", "<players><player name=\"B0\"/></players>");
        const auto& stats = isaac::runtime::ModPlayerNameStatistics();
        std::printf("B401 idem=%d,%d,%d dup=%u\n", Lookup("A0"), Lookup("A1"), Lookup("B0"),
                    stats.duplicateMods);
        return 0;
    }
    if (std::strcmp(scenario, "malformed") == 0) {
        // 截断的 players.xml（没有闭合的 `>`）⇒ 该模组整份跳过；下一个模组仍从 41 起。
        Ingest("Bad", "<players><player name=\"Broken\"");
        Ingest("Good", "<players><player name=\"G0\"/><player name=\"G1\"/></players>");
        const auto& stats = isaac::runtime::ModPlayerNameStatistics();
        std::printf("B401 bad=%d,%d malformed=%u badLookup=%d\n", Lookup("G0"), Lookup("G1"),
                    stats.malformedMods, Lookup("Broken"));
        return 0;
    }
    if (std::strcmp(scenario, "noname") == 0) {
        // 4 条 `<player>`：第一条无 name、第三条空 name ⇒ 跳过且**不占 id**。
        Ingest("M", "<players><player hp=\"4\"/><player name=\"N0\"/>"
                    "<player name=\"\"/><player name=\"N1\"/></players>");
        const auto& stats = isaac::runtime::ModPlayerNameStatistics();
        std::printf("B401 noname=%d,%d skipped=%u\n", Lookup("N0"), Lookup("N1"),
                    stats.skippedEntries);
        return 0;
    }
    if (std::strcmp(scenario, "lua") == 0) {
        // 先把"Trinity 那份 players.xml"喂进追加层，再真跑 Lua 查名字。
        // ★ 用 `print` 回读（宿主真 Lua 路径），**不**依赖 `InitializeFromBuffer` 返回 `Success`
        //   —— 这段脚本没有登记回调，初始化会以 `MissingPostUpdateCallback` 收尾（状态被重置），
        //   但 `print` 早已落到 stdout，读数照样准（与批次 399 的夹具同法）。
        Ingest("Trinity", @TRINITY_XML@);
        const char* script =
            "print('B401 lua=' .. Isaac.GetPlayerTypeByName('Mary') .. ',' .. "
            "Isaac.GetPlayerTypeByName('Peter') .. ',' .. Isaac.GetPlayerTypeByName('Isaiah') .. ',' .. "
            "Isaac.GetPlayerTypeByName('Isaac') .. ',' .. Isaac.GetPlayerTypeByName('Magdalene') .. ',' .. "
            "Isaac.GetPlayerTypeByName('Isaac', true) .. ',' .. "
            "Isaac.GetPlayerTypeByName('Mary', true) .. ',' .. "
            "Isaac.GetPlayerTypeByName('NoSuchCharacter'))";
        const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b401.lua");
        static_cast<void>(result);
        return 0;
    }
    return 91;
}
'''


class ModPlayerNamesBatch401Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b401-")
        harness_source = HARNESS.replace("@TRINITY_XML@", '"' + TRINITY_XML.replace('"', '\\"') + '"')
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
        """② 追加顺序 = 喂入顺序：ModA 的两条先拿到 41/42、ModB 的拿到 43。

        ★ 顺序错了 id 就错，而且是**静默错**（按错角色判类型、不报错）—— 所以这里逐个钉死。
        """
        out = self.run_scenario("order")
        self.assertIn("B401 order=41,42,43", out)

    def test_same_mod_fed_twice_is_idempotent(self):
        """③ 幂等：同一个 modKey 喂两次，第二次整份忽略（id 不追加两次）。"""
        out = self.run_scenario("idempotent")
        self.assertIn("B401 idem=41,42,43 dup=1", out)

    def test_malformed_xml_is_skipped_and_does_not_shift_others(self):
        """④ 坏 XML 不抛错、不挤错位置：坏模组跳过，下一个模组仍从 41 起。"""
        out = self.run_scenario("malformed")
        # 好模组拿 41/42（坏模组**没有**挤掉它们的位置）；坏模组计数 ≥1；坏名字查不到。
        self.assertIn("B401 bad=41,42 malformed=1 badLookup=-1", out)

    def test_missing_name_is_skipped_without_consuming_an_id(self):
        """④ `name` 缺失/为空 ⇒ 跳过该条且**不占 id**（N0/N1 仍是 41/42，被跳过 2 条）。"""
        out = self.run_scenario("noname")
        self.assertIn("B401 noname=41,42 skipped=2", out)

    def test_end_to_end_lua_getplayer_type_by_name(self):
        """⑤ 端到端：真 Lua 下 `Isaac.GetPlayerTypeByName("Mary") == 41`。

        ★ 同时钉住"本体 41 条逐值不变"（Isaac=0 / Magdalene=1 / 堕落 Isaac=21），
        以及"模组角色没有堕落版本"（Mary + Tainted ⇒ -1）、"未知名字 ⇒ -1"。
        """
        out = self.run_scenario("lua")
        self.assertIn("B401 lua=41,42,43,0,1,21,-1,-1", out)

    # ---------------------------------------------------------------- 本体表不许被改

    def test_body_player_types_are_unchanged(self):
        """① 本体 41 条逐值不变 —— 直接读 `player_types.txt`，与冻结快照逐条比。

        ★ 本批的修法是"**另加**一层运行时可变的追加层"，**不是**改本体契约快照
        （`isaac_name_source/player_types.txt` 是 PC 契约的静态快照，改它等于动契约）。
        """
        rows = []
        for line in GEN_SOURCE.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            rows.append((fields[0], int(fields[1]), int(fields[2]) if len(fields) > 2 else -1))
        self.assertEqual(tuple(rows), BODY_PLAYER_TYPES,
                         "本体角色表被改动了 —— 追加层不该动这张快照")

    def test_body_ids_stay_inside_zero_to_forty(self):
        """① 本体的所有 id 都落在 `0..40`（追加层只许从 41 起，不许占本体槽）。

        ★ 不能断言"21 个名字把 0..40 铺满"：本体里 `38`/`39` 这两个编号**没有角色占用**
        （既不是某个角色本体 id，也不是任何角色的堕落 id），是空号 —— 这是契约事实，
        不是我们漏了。这里只钉"出现的 id ⊆ 0..40"且"本体 0..20 全在"。
        """
        ids = set()
        for _name, identifier, alternate in BODY_PLAYER_TYPES:
            ids.add(identifier)
            if alternate >= 0:
                ids.add(alternate)
        self.assertTrue(set(range(21)) <= ids, f"本体 id 0..20 应齐全，缺 {set(range(21)) - ids}")
        self.assertTrue(ids <= set(range(41)), f"本体 id 越过了 40：{sorted(i for i in ids if i > 40)}")

    # ---------------------------------------------------------------- 静态接线

    def test_lookup_consults_the_append_layer_only_as_a_fallback(self):
        """静态表**先查**（本体优先），只有未命中且非堕落查询时才落到追加层。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn("LookupModPlayerTypeName", body)
        # 先做静态查询、再做追加层查询（顺序不能反：否则本体 id 可能被模组同名角色盖掉）。
        static_at = body.index("LookupIsaacName(IsaacNameKind::PlayerType")
        dynamic_at = body.index("LookupModPlayerTypeName")
        self.assertLess(static_at, dynamic_at,
                        "静态表必须在追加层**之前**查（本体优先）")
        self.assertIn("id < 0 && !tainted", body, "只在静态未命中且非堕落时才查追加层")

    def test_append_layer_is_wired_into_the_feed_loop(self):
        """② 追加层挂在**喂入循环**上（`LoadEngineModContent`），不是在别处自己排序。

        判据：调用点在"发现模组 → 逐模组喂 content"的循环体内、`PostLoadMods` 收尾之前，
        且用**喂入用的那个目录名**当幂等键（不自己按名字重排）。
        """
        text = MOD_MENU_NATIVE.read_text(encoding="utf-8")
        self.assertIn("void FeedModPlayerTypeNames(", text)
        self.assertIn("isaac::runtime::IngestModPlayersXml(directory, text, textLength)", text)
        body_at = text.index("bool LoadEngineModContent(")
        loop_at = text.index("ModMenuDiscoveredCount()", body_at)
        call_at = text.index("FeedModPlayerTypeNames(directory,path,baseLength,sizeof(path))",
                             body_at)
        end_at = text.index("RunPostLoadModsOnceIfDue(manager", body_at)
        self.assertGreater(call_at, loop_at, "追加层调用必须在喂入循环里（发现结果之后）")
        self.assertLess(call_at, end_at, "追加层调用必须在 PostLoadMods 收尾之前")

    def test_new_source_unit_is_in_the_host_harness_list(self):
        """新 TU 必须进宿主夹具清单 —— 否则所有宿主用例在链接期报未定义符号。"""
        support = SUPPORT.read_text(encoding="utf-8")
        self.assertIn('"program" / "mod_player_names.cpp"', support)

    def test_files_exist(self):
        for path in (NEW_HEADER, NEW_IMPL):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file(), f"缺 {path}")


if __name__ == "__main__":
    unittest.main()
