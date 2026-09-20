"""门禁：跨模块指针的"释放点"必须登记在 `tools/engine_pointer_ownership.json` 里。

## 为什么要有它

2026-09-17 的一次真机必崩：我们拿引擎 `GetDirectoryEntries` 的**返回值**直接 `delete[]`，
而它是"条目数组首址"、分配起点在它前面 8 字节 ⇒ 释放偏移指针 ⇒ 踩坏游戏堆 ⇒ 几层之后崩在别处。
复盘结论是"**跨模块指针的所有权没有台账**"（见 `docs/开发规范.md` 第 30 条）。

这条门禁把台账钉住：
1. 台账必须能解析、每条必须有出处（`evidence` 非空）与"指针是不是分配起点"的明确回答；
2. 代码里出现**引擎的释放函数**（`_ZdaPv` / `arrayDelete` 这类跨模块释放）的文件，
   必须在台账里登记 —— 新加一处不登记就判红；
3. 登记了"不是分配起点"的条目，代码里必须真的做那个调整（例如
   `- kDirectoryEntryCountHeaderSize`）—— 否则台账就会变成"写完就忘"的文档。
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "tools" / "engine_pointer_ownership.json"
SRC = ROOT / "runtime"

REQUIRED_FIELDS = (
    "id",
    "site_file",
    "site_symbol",
    "produced_by",
    "freed_by",
    "pointer_is_allocation_base",
    "adjustment",
    "evidence",
    "status",
)

#: 代码里"释放引擎内存"的写法（跨模块释放只允许这几种出现在登记过的文件里）。
ENGINE_RELEASE_PATTERNS = (r"\barrayDelete\s*\(", r"_ZdaPv")


def ledger_entries() -> list[dict]:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    return list(data["entries"])


class EnginePointerOwnershipTests(unittest.TestCase):
    def test_ledger_is_well_formed(self):
        entries = ledger_entries()
        self.assertTrue(entries, "台账是空的")
        for entry in entries:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, entry, f"{entry.get('id')} 缺字段 {field}")
            self.assertTrue(entry["evidence"], f"{entry['id']} 的 evidence 不能为空")
            self.assertIsInstance(entry["pointer_is_allocation_base"], bool)
            self.assertTrue(
                (ROOT / entry["site_file"]).exists(),
                f"{entry['id']} 指向的文件不存在：{entry['site_file']}",
            )

    def test_every_cross_module_release_site_is_registered(self):
        registered = {entry["site_file"] for entry in ledger_entries()}
        offenders = {}
        for path in SRC.rglob("*.cpp"):
            if "build" in path.parts or ".gdbsym" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in ENGINE_RELEASE_PATTERNS:
                if re.search(pattern, text):
                    rel = str(path.relative_to(ROOT))
                    offenders.setdefault(rel, set()).add(pattern)
        unregistered = {rel: pats for rel, pats in offenders.items() if rel not in registered}
        self.assertFalse(
            unregistered,
            "这些文件里出现了跨模块释放（arrayDelete/_ZdaPv），但没有登记进指针所有权台账："
            + repr(sorted(unregistered)),
        )

    def test_registered_adjustments_are_actually_applied(self):
        """台账里写"不是分配起点"的条目，代码里必须**真的做那个减法**。

        只查"名字出现过"是不够的 —— 名字在注释里也会出现（第一版就这么漏掉了：
        把实现改回旧写法后门禁照样绿）。
        """
        for entry in ledger_entries():
            if entry["pointer_is_allocation_base"]:
                continue
            text = (ROOT / entry["site_file"]).read_text(encoding="utf-8", errors="replace")
            tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{6,}", entry["adjustment"])
            self.assertTrue(tokens, f"{entry['id']} 的 adjustment 没有可核对的名字")
            for token in tokens:
                forms = (f"- {token}", f"-{token}")
                self.assertTrue(
                    any(form in text for form in forms),
                    f"{entry['id']} 说'返回值不是分配起点'，但 {entry['site_file']} 里找不到"
                    f"'减掉 {token}' 的写法 —— 台账与实现脱节了",
                )


if __name__ == "__main__":
    unittest.main()
