"""批次 100（2026-09-24）：「不许再裸碰引擎」的**冻结增量**门禁。

## 这条门禁在防什么

真机卡死的定位过程（见 `docs/架构诊断-框架为什么失效-20260924.md`）得到一个结构性结论：
框架只建成了"挂点安装 + 回调派发"，而**"和引擎打交道"从来没被框架接管** ——
于是每个功能各自伸手（读内存、调引擎、管资源），全仓累积 **945 处 `reinterpret_cast`**。
一处写错 ⇒ 内存被写坏 ⇒ 之后抛 C++ 异常时栈已坏 ⇒ libgcc 展开失败直接 `abort` ⇒ **静默卡死**。

**修框架是长期工程**（引擎内存访问层 / 引擎调用层 / 资源层 / 钩子隔离，见诊断文档第七节）。
但"出血"必须**立刻**止住：**存量冻结、只许减不许增**。

## 判据（4 条）

1. **逐文件只许减不许增**：某个文件的计数 > 台账里的数字 ⇒ 判红（报出文件与差值）。
2. **新文件必须显式登记**：出现台账里没有的文件（计数 > 0）⇒ 判红 ——
   想新增就得改台账并写明理由，**不许悄悄多一处**。
3. **总数只许减不许增**（挡住"拆成两个文件各写一半"这种绕过）。
4. **台账自证**：`schema` / `why` / `criteria` / `how_to_change` 四个字段必须在 ——
   台账不能变成一堆没人知道为什么在那的数字。

## 口径的诚实说明

口径是"每个 `.cpp`/`.hpp` 里 `reinterpret_cast` 的出现次数（去行注释、排除 `third_party`）"。
它**是代理指标、不是精确判定**：不区分"正当的 `void*` 转换"与"裸读引擎内存"。
之所以够用，是因为它的目的**不是精确度量**，而是**让新增必须显式登记**（改台账 + 写理由）。
真正"功能代码只能通过框架接口碰引擎"要靠**引擎内存访问层**（诊断文档第七节阶段 1）落地，
那时本台账的数字应当一批批降下来。

## 怎么改（不是"把数字改大"）

确实需要新增引擎交互时，先看 `docs/加一个功能模块的做法.md`：新功能应走框架接口。
确实要临时绕过 ⇒ 在 `tools/raw_engine_access_baseline.json` 里把该文件数字 +1，
并在提交信息里写明**理由 + 回退计划**；迁移走框架后把数字减回去（本门禁不拦"降"）。
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tools" / "raw_engine_access_baseline.json"
ROOTS = (ROOT / "runtime" / "source", ROOT / "runtime" / "src")
#: 排除第三方源码（Lua 5.3.3 在 `source/third_party/` 下）。
SKIP_PARTS = ("third_party",)
FINGERPRINT = re.compile(r"reinterpret_cast")


def count_occurrences(path: Path) -> int:
    """按台账口径数一个文件里的 `reinterpret_cast`（先去掉行注释）。"""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return len(FINGERPRINT.findall(re.sub(r"//[^\n]*", "", text)))


def measure() -> dict[str, int]:
    """当前工作区的计数（相对仓库根的路径 ⇒ 次数）。"""
    counts: dict[str, int] = {}
    for root in ROOTS:
        for path in sorted(root.rglob("*")):
            if path.suffix not in (".cpp", ".hpp"):
                continue
            if any(part in path.parts for part in SKIP_PARTS):
                continue
            number = count_occurrences(path)
            if number:
                counts[str(path.relative_to(ROOT))] = number
    return counts


class RawEngineAccessFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cls.expected: dict[str, int] = cls.baseline["files"]
        cls.current = measure()

    def test_ledger_explains_itself(self):
        """台账必须能自证：四个说明字段都在（别让它变成一堆没有出处的数字）。"""
        for field in ("schema", "why", "criteria", "how_to_change"):
            self.assertIn(field, self.baseline, f"台账缺 `{field}` —— 得写清这条数字是什么口径")
        self.assertEqual(self.baseline["schema"], "isaac-raw-engine-access-baseline/1")

    def test_no_file_may_increase(self):
        """★ 主判据：逐文件只许减不许增。"""
        increased = {
            name: (self.expected[name], self.current.get(name, 0))
            for name in self.expected
            if self.current.get(name, 0) > self.expected[name]
        }
        self.assertEqual(
            increased, {},
            "这些文件的「裸碰引擎」变多了（台账数字 ⇒ 现在）：\n"
            + "\n".join(f"  {name}: {old} ⇒ {now}" for name, (old, now) in sorted(increased.items()))
            + "\n\n新功能请走框架接口（见 docs/加一个功能模块的做法.md）；"
              "确实要临时绕过就改 tools/raw_engine_access_baseline.json 并写明理由。")

    def test_new_files_must_be_registered(self):
        """新文件必须显式登记 —— 不许"换个文件、悄悄多一处"。"""
        unregistered = sorted(name for name in self.current if name not in self.expected)
        self.assertEqual(
            unregistered, [],
            "这些文件里有「裸碰引擎」但台账里没有它们：\n  " + "\n  ".join(unregistered)
            + "\n\n要么走框架接口把这一处去掉，要么在台账里登记它（带理由）。")

    def test_total_may_not_increase(self):
        """总数也只许减不许增（挡住"拆成两个文件各写一半"）。"""
        total = sum(self.current.values())
        self.assertLessEqual(
            total, self.baseline["total"],
            f"总数从 {self.baseline['total']} 涨到了 {total} —— 存量只能减不能增。")

    def test_reductions_are_reported(self):
        """降下来的条目要在门禁输出里点名（好让迁移有可见的进展，而不是悄悄降）。"""
        reduced = {
            name: (self.expected[name], now)
            for name in self.expected
            if (now := self.current.get(name, 0)) < self.expected[name]
        }
        if reduced:
            # 不判红：迁移过程中数字下降是好事 —— 但要把"可以把台账数字改小"这件事说出来。
            print("\n[进展] 这些文件的「裸碰引擎」比台账少了（可以把台账数字改小）：")
            for name, (old, now) in sorted(reduced.items()):
                print(f"  {name}: {old} ⇒ {now}")
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()