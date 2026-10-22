"""批次 365（2026-10-05）：**引擎绑定的守卫校验必须早于任何"入口改写"。**

被测的不变量（一句话）：`PublishManagerEngineBindings()`（逐入口核对原版序言 + 发布引擎绑定）
必须在 `InstallProductionHooks()`（入口中继在这里把目标函数头 16 字节改成跳转桩）**之前**执行。

为什么这条不变量值得一条门禁（真机定案，2026-10-05 01:24 的读数）：
  批次 363 给 `ANM2::Load` 装了入口中继，靶点是 `kSpriteLoadOffset = 0xC970` ——
  而**同一个地址**是 Lua 侧 `Sprite:Load` 的引擎绑定，`VerifyBindingTable` 是**从活内存里
  读那 16 字节**与期望序言逐字节比的。挂点安装在前、绑定校验在后 ⇒ 校验读到我们自己的跳转桩
  ⇒ 那一格绑定静默留 0 ⇒ **每个模组的 `Sprite:Load` 都抛 "native binding is unavailable"**
  （真机后果：5 个模组同一条错、回调登记数 81 → 16、`ManifestInstallReturned` detail 0 → 21）。
  ⇒ 这类"挂点靶点"与"绑定守卫"撞在同一个地址上的情形，**只能靠顺序**保证正确。

这个门禁是**静态核对**（宿主即可判定）：
  1. `TryInstallDefaultManifestMod` 里，`PublishManagerEngineBindings(module)` 必须出现在
     `InstallProductionHooks(` **之前**；
  2. **非空洞自证**：必须真的存在"既是入口中继靶点、又出现在某张绑定守卫表里"的偏移 ——
     否则本次门禁什么也没保护到（将来把中继挪走/改名时，它会报红提醒重看这一条）；
  3. 那个交集里必须包含本批的已知案例 `kSpriteLoadOffset`（挡住"交集成空还装作通过"）；
  4. 批次 363 定义了却**没有任何调用点**的 `NoteAnm2LoadRelayInstalled` 必须真的被接上
     （它会写读数里"中继装上没有"那一格；没有调用点 ⇒ 那一格恒写"未试"，是**会撒谎的判据**）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK_MANAGER = ROOT / "runtime" / "source" / "hook_manager.cpp"
ADAPTER = ROOT / "runtime" / "src" / "infrastructure" / "relay" / "entry_relay_hook_adapter.cpp"

#: 入口中继适配器里"靶点"用的偏移常量（`BindingOf` 的每个 `case` 都在这里取一个 `k*Offset`）。
#: 用它做集合运算而不是去解析 C++ —— 多收几个名字只会让交集更大，不会让门禁变空。
OFFSET_NAME = re.compile(r"\b(k[A-Za-z0-9_]*Offset)\b")
#: 绑定守卫表的一行：`{kXxxOffset, offsetof(...), &kXxxExpectedBytes}`。
GUARD_ROW = re.compile(r"\{\s*(k[A-Za-z0-9_]*Offset)\s*,\s*offsetof\(")
#: 函数体切片：从函数头到下一个 `^\}`（本文件里这几个函数都是顶格写的）。
FUNCTION_HEAD = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_:<>\s\*&]*\bTryInstallDefaultManifestMod\(", re.M
)


def function_body(text, head_pattern):
    """切出一个顶格函数（从函数头那一行到下一个顶格 `}`），找不到就报错。"""
    match = head_pattern.search(text)
    assert match, "找不到函数头"
    start = match.start()
    end = text.find("\n}", start)
    assert end > start, "找不到函数体的结束"
    return text[start : end + 2]


class BindingGuardOrderingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook_manager = HOOK_MANAGER.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")

    # ---- 1. 顺序：绑定校验/发布 必须早于 入口改写 ---------------------------
    def test_engine_bindings_are_published_before_entry_hooks_install(self):
        body = function_body(self.hook_manager, FUNCTION_HEAD)
        publish = body.find("PublishManagerEngineBindings(module)")
        install = body.find("InstallProductionHooks(")
        self.assertNotEqual(publish, -1, "TryInstallDefaultManifestMod 里没有发布引擎绑定")
        self.assertNotEqual(install, -1, "TryInstallDefaultManifestMod 里没有安装挂点")
        self.assertLess(
            publish,
            install,
            "引擎绑定的‘校验 + 发布’必须早于 `InstallProductionHooks` —— 否则入口中继"
            "改过的头 16 字节会被绑定守卫判成‘序言不符’，那一格绑定静默留 0"
            "（2026-10-05 真机：Sprite:Load 对全部模组失效）。",
        )

    # ---- 2. 非空洞自证：真的存在"中继靶点 ∩ 绑定守卫" ----------------------
    def _relay_targets(self):
        return set(OFFSET_NAME.findall(self.adapter))

    def _guard_offsets(self):
        return set(GUARD_ROW.findall(self.hook_manager))

    def test_the_intersection_is_not_empty(self):
        intersection = self._relay_targets() & self._guard_offsets()
        self.assertTrue(
            intersection,
            "没有任何‘入口中继靶点’同时出现在绑定守卫表里 ⇒ 这条门禁现在是**空洞**的"
            "（它保护的那个不变量不存在了/被改名了）。请重新确认：要么靶点换了地址，"
            "要么守卫表换了口径 —— 确认后更新本条门禁，别让它空转。",
        )
        self.assertIn(
            "kSpriteLoadOffset",
            intersection,
            "批次 363/365 的已知案例（`kSpriteLoadOffset` = `ANM2::Load` 入口 = Lua 的 "
            "`Sprite:Load` 绑定）不在交集里 ⇒ 说明靶点或守卫表变过了，必须重看顺序那一条。",
        )

    # ---- 3. 会撒谎的判据必须接上：Anm2Load 的安装结果要留痕 ----------------
    def test_anm2_install_result_is_recorded(self):
        self.assertIn(
            "NoteAnm2LoadRelayInstalled",
            self.adapter,
            "`NoteAnm2LoadRelayInstalled` 没有任何调用点 ⇒ 读数里‘中继装上没有’恒写‘未试’，"
            "**即使入口早已是补丁**（批次 363 就是这样，2026-10-05 真机读数当场抓到）。",
        )
        # 它必须在中继桩真正安装/早退的每一条路上都被调到，而不是只在某一条分支里。
        note = re.search(
            r"const auto \w+ = \[id\]\(bool installed, unsigned failure\) \{(.*?)\n    \};",
            self.adapter,
            re.S,
        )
        self.assertIsNotNone(note, "适配器里没有安装结果留痕的 lambda")
        body = note.group(1)
        self.assertIn("NoteAnm2LoadRelayInstalled", body, "留痕 lambda 里没接 Anm2Load")
        self.assertIn(
            "NoteRebuildMountPointsEntryRelay", body, "留痕 lambda 里丢了 RebuildMountPoints"
        )


if __name__ == "__main__":
    unittest.main()
