"""门禁：**PC 的资源层重定向**这条机制的核心不变量（批次 378，2026-10-05）。

## 为什么有这条

批次 371 的"整局没有音乐"定案是：引擎请求**裸名** `music.xml`，而我们把模组的 `content/` 叶子
挂进了内容挂载表 ⇒ 倒序遍历的挂载表命中了 `<模组>/content/music.xml`（没有 `id` 的 2 条表）
⇒ 119 格表全空 ⇒ "music ready" 闸门不开。修法不是"把 `content` 叶子挪个位置"，而是
**换成 PC 的机制**：`ModManager::GetModResourcePath @0x870460` 按模组清单顺序（跳过停用的）
逐个启用的模组问"先 `<模组>/resources-dlc3/<名>`、再 `<模组>/resources/<名>`"，
第一个命中赢，都不在就把原名回传。

落点：`IContentManager::GetMountedFilePath`（`0x4C2340`）—— 引擎 8 个文件入口的公共前置步。

## 判据（钉住"机制的形状"，不钉某一行代码）

1. **候选只有两个后缀**：`resources-dlc3/` 与 `resources/`，顺序即优先级；
   **永远不许出现 `content`** —— 那正是 371 的成因，出现即红。
2. **顺序是"模组外层、后缀内层"**（与 PC 的循环同形）：外层按清单顺序，内层两级。
3. **不自己分配**：命中时把探测（桥给的**原函数**入口）返回的路径原样交回；未命中返回空
   —— 所有权与释放口径都不越过引擎那一层。
4. **早退**：已是解析形态（`rom:/…` / `isaac_mods/…`）的请求不再重定向，且要计数。
5. **读数面**：`g_ModResourceRedirectState` 必须能被读数工具按 mangled 名同步到、按 57 个字读，
   并把 `hits`（★ 答了模组层的次数）单独打印出来 —— 它是"模组资源真的经这里进了引擎"的唯一直接证据。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HPP = ROOT / "runtime" / "source" / "mod_resource_redirect.hpp"
CPP = ROOT / "runtime" / "source" / "mod_resource_redirect.cpp"
SHIM = ROOT / "runtime" / "source" / "program" / "mod_resource_redirect.cpp"
BRIDGE = ROOT / "runtime" / "source" / "image_pcx_bridge_hook.cpp"
HOOK_MANAGER = ROOT / "runtime" / "source" / "hook_manager.cpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"

#: 状态结构里的字符数组容量（`.hpp` 里那两个常量）—— 这里按"名字"取，不写死数字。
QUERY_CAPACITY = 192
ANSWER_CAPACITY = 224
COUNTER_FIELDS = 10  # published / modCount / calls / hits / dlc3Hits / plainHits /
#                      lastHitMod / skippedResolved / skippedTooLong / publishCount


def code_only(text: str) -> str:
    """剥掉行注释与整行块注释里的说明 —— 本仓纪律：判据只看**代码**。"""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


class ModResourceRedirectTests(unittest.TestCase):
    def setUp(self):
        self.hpp = HPP.read_text(encoding="utf-8")
        self.cpp = CPP.read_text(encoding="utf-8")
        self.code = code_only(self.cpp)
        self.bridge = BRIDGE.read_text(encoding="utf-8")
        self.hooks = HOOK_MANAGER.read_text(encoding="utf-8")

    # ---- ① 候选后缀：只许 resources-dlc3 / resources，永远不许 content --------------
    def test_candidates_are_only_the_two_pc_suffixes(self):
        table = self.cpp[self.cpp.index("kCandidateSuffixes"):]
        table = table[:table.index("};")]
        self.assertIn('"resources-dlc3/"', table, "PC 的第一优先是 `resources-dlc3/`")
        self.assertIn('"resources/"', table, "PC 的第二优先是 `resources/`")
        self.assertLess(table.index('"resources-dlc3/"'), table.index('"resources/"'),
                        "顺序反了就不是 PC 的优先级")
        # ★★ 371 的成因就写在这条上：候选里一旦出现 `content`，那个抢占就回来了。
        self.assertNotIn("content", table,
                         "★ 候选后缀里不许出现 `content` —— 371 的整局没音乐就是它抢的")
        # 实现里也不许偷偷拼 content（例如某条兜底路径）。
        self.assertNotIn('"content', self.code, "实现里不许拼 `content` 候选")

    # ---- ② 循环形状：模组外层、后缀内层 ------------------------------------------
    def test_loop_shape_is_mod_outer_suffix_inner(self):
        body = self.code[self.code.index("char* TryRedirectModResource("):]
        mod_loop = body.index("for (std::size_t mod = 0;")
        suffix_loop = body.index("for (std::size_t suffixIndex = 0;")
        self.assertLess(mod_loop, suffix_loop,
                        "必须是「模组外层、后缀内层」（与 PC 的循环同形）")
        self.assertIn("probe(contentManager, candidate)", body,
                      "探测必须问引擎那个原函数入口")
        self.assertIn("if (resolved == nullptr)", body,
                      "探测答空 ⇒ 继续问下一个（PC 同）")
        self.assertIn("return resolved;", body,
                      "命中就把引擎解析出来的路径**原样**交回（不自己分配）")

    # ---- ③ 不自己分配 / 不递归 ---------------------------------------------------
    def test_no_allocation_and_no_recursion(self):
        body = self.code[self.code.index("char* TryRedirectModResource("):]
        for forbidden in ("new ", "new[", "malloc", "operatorNewArray", "delete", "_ZdaPv"):
            self.assertNotIn(forbidden, body,
                             f"重定向这一段不许自己分配/释放（{forbidden}）—— 所有权归引擎")
        self.assertNotIn("EntryRelayContentGetMountedFilePathCallback(", body,
                         "探测不许递归进我们自己的中继（必须走桥传进来的原函数）")

    # ---- ④ 早退与计数 ------------------------------------------------------------
    def test_already_resolved_requests_are_skipped_and_counted(self):
        self.assertIn("LooksAlreadyResolved(requestedPath)", self.code)
        self.assertIn("kModsRootPrefix", self.cpp, "要认出 `isaac_mods/` 前缀的请求")
        self.assertIn("++state.skippedResolved;", self.code, "跳过要计数")

    # ---- ⑤ 接线：桥里真的先问了一遍（含 `.png` 那条支路）--------------------------
    def test_bridge_asks_the_redirect_first(self):
        self.assertRegex(self.bridge, r"bridge::TryRedirectModResource\(\s*path, self, original,",
                      "主支路必须先把请求交给重定向")
        self.assertRegex(self.bridge, r"TryRedirectModResource\(\s*pngPath, self, original,",
                      "`.png` 那条支路也要走重定向（模组那份 `.png` 现在只能由它给出）")
        # 命中时交给下面既有逻辑的必须是"重定向给出的那条"，不是原函数那条。
        self.assertIn("redirected != nullptr ? redirected : original(self, path)", self.bridge,
                      "命中时要把它当成引擎的答案（否则等于白问一遍）")

    # ---- ⑥ 发布点：在跑模组脚本之前 ---------------------------------------------
    def test_publication_happens_before_the_scripts_step(self):
        publish = self.hooks.index("PublishModResourceRedirectList(")
        scripts = self.hooks.index("ManifestLoadStep::Scripts")
        self.assertLess(publish, scripts,
                        "清单必须在 `ManifestLoadStep::Scripts` 之前发布 —— "
                        "模组脚本在文件作用域就查死服装编号")

    # ---- ⑦ 读数面：符号、mangled 名、读长、以及 `hits` 必须单独打印 ----------------
    def test_reader_can_read_the_state_plane(self):
        reader = READER.read_text(encoding="utf-8")
        self.assertRegex(reader, r"'g_ModResourceRedirectState':\s*0x[0-9a-fA-F]+\s*,",
                         "读数工具必须登记该字段，允许整表同步后的真实偏移")
        self.assertIn("sync_syms_from_elf", reader)
        self.assertIn(
            "'g_ModResourceRedirectState': "
            "'_ZN5isaac7runtime6bridge26g_ModResourceRedirectStateE'",
            reader,
            "mangled 名要与 ELF 里的符号逐字一致（`nm` 可核对）")
        words = (COUNTER_FIELDS * 4 + QUERY_CAPACITY + ANSWER_CAPACITY + 7) // 8
        self.assertIn(f"('mod_redirect_state', base + SYMS['g_ModResourceRedirectState'], {words})",
                      reader,
                      f"读长必须覆盖 10 个 u32 + {QUERY_CAPACITY} + {ANSWER_CAPACITY} 字节 = {words} 个字")
        self.assertIn("redirect_hits = u32_at(values, 'mod_redirect_state', 3)", reader,
                      "第 4 格（下标 3）是 hits —— 必须单独取出来")
        self.assertIn("答了模组层", reader, "hits 要单独打印（这是机制生效的唯一直接证据）")
        # 结构体字段顺序即内存顺序：两边必须一致。
        fields = re.findall(r"std::uint32_t (\w+);", self.hpp)
        self.assertEqual(
            fields[:COUNTER_FIELDS],
            ["published", "modCount", "calls", "hits", "dlc3Hits", "plainHits",
             "lastHitMod", "skippedResolved", "skippedTooLong", "publishCount"],
            "状态面字段顺序变了 ⇒ 读数工具的下标全错位")

    # ---- ⑧ 构建：根下的 `.cpp` 要有一个进得了构建的包装 ----------------------------
    def test_the_translation_unit_is_actually_compiled(self):
        self.assertTrue(SHIM.exists(),
                        "构建只收 `source/` 的下一级子目录 ⇒ 根下这个 `.cpp` 必须有一个 "
                        "`source/program/` 里的包装（否则链接期'未定义符号门禁'报红）")
        shim = SHIM.read_text(encoding="utf-8")
        self.assertIn('#include "../mod_resource_redirect.cpp"', shim)


if __name__ == "__main__":
    unittest.main()
