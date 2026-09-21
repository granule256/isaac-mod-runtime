"""门禁：每条 API 的**完成定义（Definition of Done）**必须交代清楚 —— 契约依据 / 边界判据 / 成熟度。

## 为什么要有它（2026-09-21，用户提出的问题）

"每条 API 到底和 PC 语义一致不一致"这件事，此前**没有"实现时就必须交代"的强制机制**：

* `api_catalog.cpp` 只说"这条 API 存在"；
* `api_deviation.cpp` 只记"**已经知道**与 PC 不同的那几条"（2026-09-21 批次 017 起为 **24** 条）；
* 成熟度台账只要求"**宣称真机验证过**的必须有依据"。

中间的空白是最大的那块：**新加一条 API 时，"它凭什么说自己是 PC 的那个语义"
（在 `tools/pc_contract_docs/` 的哪一页哪一行）与"边界/异常输入是什么口径、谁钉住"
两件事，没有任何地方逼着人写**。写成注释没人读，不写也没人问 ——
这正是 107→109→110 三批返工（凭推断断言 PC 语义）与 098 那次
（`Room:GetGridPath` 恒返常量、后果写错）的共同根因。

所以本门禁钉住，**基线之外**的每一个 catalog id 必须在
`tools/api_definition_of_done.json` 里有条目，且三件事齐备：

1. **契约依据**：页在仓库里、行号在范围内、`quote` **逐字落在那一行上**；
2. **边界判据**：写明输入形状（受控词表）+ 一个**真实存在**的测试文件，
   **且那个文件里真的提到这条 API**（否则"判据"是随手指的一个文件）；
3. **成熟度**：与 `api_catalog.cpp` 逐字一致，且新 API 要在
   `tools/api_maturity_evidence.json` 里登记（四态之一）。

## 基线 grandfather（不能一次全红）

台账里的 `baseline.ids` 是**门禁建立当时**那 252 条的快照，它们豁免（补了的照样逐条校验）。
基线**只读**：本测试把它的**条数与摘要**写死，防止两件事 ——
① 有人偷偷删 API（基线 ⊆ catalog 那条也会红）；② 把新 API 塞进基线来躲门禁
（`test_baseline_digest_pin_catches_an_api_planted_into_the_baseline` 专门讲这件事）。

## 口径只有一份

判据、解析与错误文案都在 `tools/api_definition_of_done.py`（门禁不重写一套正则）。
本测试另外核对两处**口径漂移**：域名表 vs `api_descriptor.hpp` 的枚举、
catalog 解析 vs `test_api_maturity_ledger` 的解析。

## 合成回归（"门禁真的会红"）

下面用一份**最小合成仓库**（自造 catalog + 自造台账 + 自造契约页 + 自造测试文件）
把每种缺项各跑一遍：三个负面对照（缺三件事 / 抄错行 / 判据文件不对）
加一个**正面对照**（三件事齐备时不许红 —— 否则门禁是不可用的）。
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.api_definition_of_done import (
    BOUNDARY_KINDS,
    DOMAIN_VALUES,
    baseline_digest,
    check,
    load_catalog,
    load_ledger,
)

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
DESCRIPTOR = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_descriptor.hpp"
LEDGER = ROOT / "tools" / "api_definition_of_done.json"

#: ★ 账本数字（改动时必须同步并在这上面补一行说明，见 CONTRIBUTING.md 第二节）。
#:
#: 基线条数：2026-09-21 建立本门禁时冻结 **252** 条（当时 `api_catalog.cpp` 的全部目录行）。
#: 这个数字**只该保持不变** —— 基线是"历史快照"，新 API 不许塞进来（要塞就是躲门禁）。
BASELINE_COUNT = 252

#: 基线集合的摘要（`baseline_digest()` = 排序后逐行拼接的 sha256 前 16 位）。
#: 光看条数挡不住"删一条老的、加一条新的"那种同数量替换 ⇒ 用摘要钉死内容。
BASELINE_DIGEST = "b7f97f652bd6e631"

#: 台账里已有条目的数量：2026-09-21 建账时 **4** 条（都是"够格当模板"的老 API：
#: `Room:GetGridPath` / `Isaac:GetTime` / `Input:IsActionTriggered` / `EntityPlayer:GetPill`）。
#: 这个数字**只增不减**：删条目要么是 API 被删（那要一起改基线），要么是有人想躲门禁。
EXPECTED_ROWS = 4


def _entry(sequence: str, name: str, maturity: str = "Experimental", domain: str = "Room",
           owner: str | None = None) -> str:
    """合成 catalog 里的一行（形状与真实 `api_catalog.cpp` 一致）。"""
    return (f'    {{MakeId(ApiDomain::{domain}, 1, {sequence}), ApiDomain::{domain}, '
            f'"{owner or domain}", "{name}", kV1, 0,\n'
            f'     ThreadAffinity::MainUpdate, ApiMaturity::{maturity}}},\n')


#: 合成契约页（行号是真数出来的：第 5 行就是新 API 那一行）。
SYNTHETIC_PAGE_LINES = [
    "# Room",
    "",
    "#### int GetGridPath ( int Index )",
    "",
    "#### int NewProbe ( int Index )",
]

#: 合成测试文件：必须**提到那条 API**（门禁按接口名/id 找）。
SYNTHETIC_TEST = "def test_new_probe_out_of_range():\n    # Room:NewProbe / 0x04010002 越界下标\n    pass\n"


def _synthetic_ledger(baseline_ids, rows) -> dict:
    return {
        "schema": 1,
        "note": ["合成台账（只给门禁自证用）"],
        "baseline": {"note": "合成", "count": len(baseline_ids), "ids": list(baseline_ids)},
        "rows": rows,
    }


class SyntheticRepoMixin:
    """搭一份最小合成仓库，供"门禁真的会红"的对照用（不依赖真实 catalog）。"""

    def synthetic_repo(self, *, rows=None, baseline_ids=None, maturity_rows=None,
                       test_files=None, extra_entries=None, page_lines=None) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="dod-synthetic-"))
        self.addCleanup(shutil.rmtree, directory, True)

        (directory / "runtime" / "src" / "interfaces" / "lua").mkdir(parents=True)
        (directory / "runtime" / "tests").mkdir(parents=True)
        (directory / "tools" / "pc_contract_docs").mkdir(parents=True)

        entries = [_entry("0x0001", "GetGridPath", "HostVerified")]
        entries.extend(extra_entries if extra_entries is not None else [_entry("0x0002", "NewProbe")])
        (directory / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp").write_text(
            "constexpr LuaApiDescriptor kDefaultApis[] = {\n" + "".join(entries) + "};\n",
            encoding="utf-8")

        (directory / "tools" / "pc_contract_docs" / "Room.md").write_text(
            "\n".join(page_lines if page_lines is not None else SYNTHETIC_PAGE_LINES) + "\n",
            encoding="utf-8")

        files = test_files if test_files is not None else {
            "runtime/tests/test_synthetic_probe.py": SYNTHETIC_TEST}
        for relative, content in files.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        (directory / "tools" / "api_maturity_evidence.json").write_text(
            json.dumps({"schema": 1, "rows": maturity_rows if maturity_rows is not None
                        else {"Room:NewProbe": {"maturity": "Experimental", "evidence": []}}},
                       ensure_ascii=False), encoding="utf-8")

        (directory / "tools" / "api_definition_of_done.json").write_text(
            json.dumps(_synthetic_ledger(
                baseline_ids if baseline_ids is not None else ["Room:GetGridPath"],
                rows if rows is not None else {"Room:NewProbe": complete_row()}),
                ensure_ascii=False), encoding="utf-8")
        return directory


def complete_row() -> dict:
    """一份**合格**的台账条（正面对照的基准）。"""
    return {
        "contract": {"page": "tools/pc_contract_docs/Room.md", "line": 5,
                     "quote": "#### int NewProbe ( int Index )"},
        "boundary": {"kind": "越界下标", "judgement": "runtime/tests/test_synthetic_probe.py",
                     "detail": "Index 越界（负数 / >= W*H）一律返回 0，不读越界内存"},
        "maturity": "Experimental",
    }


class ApiDefinitionOfDoneTests(SyntheticRepoMixin, unittest.TestCase):
    # ------------------------------------------------------------------ 现仓库

    def test_ledger_is_shaped(self):
        self.assertTrue(LEDGER.is_file(), "缺少 tools/api_definition_of_done.json")
        ledger = load_ledger()
        self.assertEqual(ledger["schema"], 1)
        self.assertIn("baseline", ledger)
        self.assertIn("rows", ledger)

    def test_repository_passes_every_criterion(self):
        """★ 主判据：当前仓库必须整体通过（红就是有人加了 API 没交代）。"""
        report = check()
        self.assertEqual(report.errors, [], "完成定义门禁未通过：\n  - " + "\n  - ".join(report.errors))
        self.assertGreater(report.catalog_size, 200, "catalog 解析结果太少，门禁失去意义")

    def test_baseline_is_frozen(self):
        """基线**只读**：条数与摘要都被钉死。"""
        ledger = load_ledger()
        ids = ledger["baseline"]["ids"]
        self.assertEqual(len(ids), BASELINE_COUNT,
                         "基线条数变了。基线是历史快照，**不许增删** —— "
                         "新增 API 请填 completion rows，不要往 baseline 里塞。")
        self.assertEqual(ledger["baseline"]["count"], BASELINE_COUNT,
                         "baseline.count 与 BASELINE_COUNT 不一致")
        self.assertEqual(baseline_digest(ids), BASELINE_DIGEST,
                         "基线内容变了（同数量替换也算）。确认是「真的删了 API」再同步摘要并写清原因。")

    def test_every_baseline_api_still_exists(self):
        """不许偷偷删接口：基线里的每一条都还在 catalog 里。"""
        catalog = load_catalog()
        missing = sorted(set(load_ledger()["baseline"]["ids"]) - set(catalog))
        self.assertEqual(missing, [], f"基线里这些 API 从 catalog 消失了：{missing}")

    def test_registered_rows_are_really_checked(self):
        """台账里已有的条目**逐条真的被校验过**（否则这张台账就是装饰）。"""
        report = check()
        self.assertEqual(report.rows_checked, EXPECTED_ROWS,
                         "已登记条数变了（只增不减；减少说明有人删了条目）。")

    def test_new_apis_are_exactly_those_outside_the_baseline(self):
        report = check()
        baseline = set(load_ledger()["baseline"]["ids"])
        self.assertEqual(set(report.new_apis), set(load_catalog()) - baseline)

    # ------------------------------------------------------- 口径漂移的两处互证

    def test_domain_table_matches_the_cpp_enum(self):
        """工具里的域名表必须与 `api_descriptor.hpp` 的 `ApiDomain` 枚举一致（口径只有一份）。"""
        text = DESCRIPTOR.read_text(encoding="utf-8")
        block = re.search(r"enum class ApiDomain[^{]*\{(.*?)\};", text, re.S)
        self.assertIsNotNone(block, "api_descriptor.hpp 里没找到 ApiDomain 枚举")
        enum_values = {name: int(value) for name, value in
                       re.findall(r"(\w+)\s*=\s*(\d+)", block.group(1))}
        self.assertTrue(enum_values, "枚举解析结果为空 —— 解析口径过期了")
        self.assertEqual(DOMAIN_VALUES, enum_values,
                         "本工具的 DOMAIN_VALUES 与 C++ 枚举漂移了（新加域名要同步两处）")

    def test_catalog_parser_agrees_with_the_maturity_ledger_gate(self):
        """本工具解析 catalog 的结果，必须与成熟度门禁那套解析**逐条一致**。"""
        from runtime.tests.test_api_maturity_ledger import catalog_maturity

        mine = {key: entry.maturity for key, entry in load_catalog().items()}
        theirs = catalog_maturity()
        self.assertEqual(mine, theirs, "两套 catalog 解析口径漂移了（有一边正则过期）")

    # -------------------------------------------------------------- 合成负面对照

    def test_a_new_api_without_any_of_the_three_turns_red(self):
        """★ 主反面：新 API 什么也没交代 ⇒ 三件事逐条点名。"""
        directory = self.synthetic_repo(rows={})
        report = check(root=directory)
        joined = "\n".join(report.errors)
        self.assertFalse(report.ok, "新 API 什么都没交代，门禁却绿了")
        self.assertIn("[新接口] Room:NewProbe", joined)
        for piece in ("契约依据", "边界判据", "成熟度"):
            self.assertIn(piece, joined, f"缺项里没有点名「{piece}」：\n{joined}")

    def test_a_complete_row_passes(self):
        """★ 正面对照：三件事齐备时**不许红** —— 否则这条门禁是不可用的。"""
        directory = self.synthetic_repo()
        report = check(root=directory)
        self.assertEqual(report.errors, [], "合格条目被误判：\n  - " + "\n  - ".join(report.errors))
        self.assertEqual(report.new_apis, ["Room:NewProbe"])

    def test_a_wrong_contract_line_turns_red(self):
        """抄错行 / 凭记忆写一句：引文必须逐字落在那一行上。"""
        row = complete_row()
        row["contract"]["quote"] = "#### int NewProbe ( int Index, int Extra )"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        report = check(root=directory)
        joined = "\n".join(report.errors)
        self.assertIn("[契约依据] Room:NewProbe", joined)
        self.assertIn("引用与文档对不上", joined)

    def test_a_contract_line_out_of_range_turns_red(self):
        row = complete_row()
        row["contract"]["line"] = 999
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        self.assertIn("没有第 999 行", "\n".join(check(root=directory).errors))

    def test_a_citation_of_another_api_turns_red(self):
        """★ 抄**另一条 API**的那一行也过不去：引文里必须出现这条 API 的名字。

        为什么要有这一半：只核对"片段真的在那一行里"，随手抄邻居 API 的规格行也能过 ——
        那也是假通过（与 099 那次"关键词恰好出现"同一族）。
        """
        row = complete_row()
        row["contract"]["line"] = 3                     # 那是 `Room:GetGridPath` 的规格行
        row["contract"]["quote"] = "#### int GetGridPath ( int Index )"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("引文里没有出现这条 API 的名字", joined)

    def test_a_contract_page_outside_the_repo_turns_red(self):
        """契约源必须在仓库里 —— 指到 `analysis/`（gitignore）就是"对别人不可做"。"""
        row = complete_row()
        row["contract"]["page"] = "analysis/isaacdocs-snapshot/docs/Room.md"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("不在", joined)
        self.assertIn("analysis/", joined)

    def test_a_missing_judgement_file_turns_red(self):
        row = complete_row()
        row["boundary"]["judgement"] = "runtime/tests/test_does_not_exist.py"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        self.assertIn("判据指向不存在的测试文件",
                      "\n".join(check(root=directory).errors))

    def test_a_judgement_file_that_never_mentions_the_api_turns_red(self):
        """★ 反"随手指一个存在的测试文件"：那个文件里必须真的提到这条 API。"""
        row = complete_row()
        directory = self.synthetic_repo(
            rows={"Room:NewProbe": row},
            test_files={"runtime/tests/test_synthetic_probe.py": "def test_something_else():\n    pass\n"})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("找不到这条 API 的名字", joined)

    def test_an_unregistered_maturity_turns_red(self):
        directory = self.synthetic_repo(rows={"Room:NewProbe": complete_row()},
                                        maturity_rows={})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("api_maturity_evidence.json 里没有 Room:NewProbe 的条目", joined)

    def test_a_maturity_disagreeing_with_the_catalog_turns_red(self):
        row = complete_row()
        row["maturity"] = "HardwareVerified"      # catalog 里是 Experimental
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("[成熟度] Room:NewProbe", joined)
        self.assertIn("两边必须一起改", joined)

    def test_a_placeholder_boundary_turns_red(self):
        """占位式写法（`暂无`/`TODO`）等于没写。"""
        row = complete_row()
        row["boundary"]["detail"] = "暂无"
        row["boundary"]["kind"] = "随便写的形状"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("不在受控词表里", joined)
        self.assertIn("不许占位", joined)
        self.assertTrue(BOUNDARY_KINDS, "受控词表不能是空的")

    def test_a_ledger_row_for_an_unknown_api_turns_red(self):
        """死账：台账里的 key 必须在 catalog 里真实存在。"""
        directory = self.synthetic_repo(rows={"Room:NewProbe": complete_row(),
                                              "Room:TypoName": complete_row()})
        self.assertIn("[死账]", "\n".join(check(root=directory).errors))

    def test_a_deleted_baseline_api_turns_red(self):
        directory = self.synthetic_repo(baseline_ids=["Room:GetGridPath", "Room:Vanished"])
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("[基线]", joined)
        self.assertIn("Room:Vanished", joined)

    def test_baseline_digest_pin_catches_an_api_planted_into_the_baseline(self):
        """★ 反规避：把新 API 塞进基线，`check()` 确实会变绿 —— 所以基线被摘要钉死。

        这是这套设计里**唯一**的规避路径（不放宽基线就绕不过去），因此要显式证明它被堵住：
        合成的仓库里把 `Room:NewProbe` 放进 baseline，`check()` 不再报缺项；
        而真实台账的基线摘要与本测试里写死的 `BASELINE_DIGEST` 一比就对不上 ⇒ 门禁红。
        """
        directory = self.synthetic_repo(rows={}, baseline_ids=["Room:GetGridPath", "Room:NewProbe"])
        self.assertEqual(check(root=directory).errors, [],
                         "（预期）塞进基线后 check() 不再报缺项 —— 这正是要防的规避路径")

        planted = load_ledger()["baseline"]["ids"] + ["Room:NewProbe"]
        self.assertNotEqual(baseline_digest(planted), BASELINE_DIGEST,
                            "基线被塞进了新 API，摘要却没变 —— 摘要失去意义")
        self.assertEqual(baseline_digest(load_ledger()["baseline"]["ids"]), BASELINE_DIGEST)

    # ------------------------------------------------------------------- 进度

    def test_progress_is_reported(self):
        """只报进度、不判红：缺口数字一眼可见（回填的时候要用它）。"""
        report = check()
        by_owner: dict[str, int] = {}
        for key in report.gaps:
            owner = key.partition(":")[0]
            by_owner[owner] = by_owner.get(owner, 0) + 1
        print(f"\n[进度] catalog {report.catalog_size} 条 = 基线 {report.baseline_size} 条（豁免）"
              f" + 新接口 {len(report.new_apis)} 条；已交代 {report.rows_checked} 条；"
              f"**基线里还没交代的是 {len(report.gaps)} 条**"
              f"（{', '.join(f'{k} {v}' for k, v in sorted(by_owner.items(), key=lambda i: -i[1])[:6])} …）")
        self.assertEqual(len(report.gaps), report.baseline_size - report.rows_checked)


if __name__ == "__main__":
    unittest.main()
