"""门禁：**目录容量不许再是"手写的数字"**（2026-09-19 批次 052）。

## 为什么有这条

`ApiCatalog::kCapacity` 历史上是**手写的**：128 → 160 → 192 → 224 → 256，
**五次都是"快撞线才抬"**。2026-09-19 实测：目录已 248 条、只剩 8 个位置 —— 而越限的后果是
`ApiCatalog::Validate()` 把**整张目录**判为无效（真机上等于所有 API 全不挂）。

用户的判断是"以后陆续实现 api 不能再有架构问题束缚"。一个"每加几条 API 就得有人来改"的数字
就是这个束缚本身，所以它已经改成**结构性上限**：真正限制条数的是 id 的编码
（`MakeId(域, ownerGroup, 序号)`，序号是 `std::uint16_t` ⇒ 每域最多 65535 条，
而这一步由**编译器**保证）。本门禁钉住三件事：

1. 容量必须是那个结构性上限（不许再退回一个小数字）；
2. 当前条数与上限之间必须有**巨大**余量（否则说明又有人在"贴着线走"）；
3. 上限不能是"跟着当前条数走"的写法（例如 `= Count()`），那是自欺。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.hpp"
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"

#: 结构性上限：id 的序号是 16 位 ⇒ 每域 65535 条。
STRUCTURAL_CAPACITY = 0xFFFF
#: 余量下限：当前条数与上限的倍数（宽松，只用来发现"又在贴线"）。
MINIMUM_HEADROOM_FACTOR = 10


class ApiCatalogCapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = HEADER.read_text(encoding="utf-8")

    def capacity(self) -> int:
        match = re.search(r"static constexpr std::size_t kCapacity = ([^;]+);", self.header)
        self.assertIsNotNone(match, "找不到 kCapacity —— 写法变了，本门禁要跟着改")
        value = match.group(1).strip()
        self.assertTrue(re.fullmatch(r"0x[0-9A-Fa-f]+|\d+", value),
                        f"kCapacity 必须是**字面量**（结构性上限），实际是 {value!r} —— "
                        f"跟着条数走的写法是自欺")
        return int(value, 0)

    def test_capacity_is_the_structural_limit(self):
        self.assertEqual(self.capacity(), STRUCTURAL_CAPACITY,
                         "目录容量必须是 id 编码的结构性上限（16 位序号 ⇒ 65535）；"
                         "退回小手写数字 = 又把'以后加 API'锁死了")

    def test_headroom_is_wide(self):
        count = len(re.findall(r"MakeId\(", CATALOG.read_text(encoding="utf-8")))
        # `MakeId(` 还出现在函数定义里一次。
        count -= 1
        self.assertGreater(count, 0, "目录里一条都读不到 —— 写法变了")
        self.assertGreater(self.capacity(), count * MINIMUM_HEADROOM_FACTOR,
                           f"目录已有 {count} 条、上限 {self.capacity()} —— 余量不足 "
                           f"{MINIMUM_HEADROOM_FACTOR} 倍，说明又在贴着线走了")

    def test_the_capacity_comment_explains_why_it_is_structural(self):
        """上限旁边必须写清"为什么它不会再追上来"，否则下一个人又会去手改它。"""
        for phrase in ("16 位", "MakeId", "结构性"):
            self.assertIn(phrase, self.header,
                          f"kCapacity 的说明里应当解释结构性理由（缺 {phrase!r}）")


if __name__ == "__main__":
    unittest.main()
