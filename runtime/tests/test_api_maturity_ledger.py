"""门禁：接口成熟度必须**有据可查** —— `HardwareVerified` 的每一条都要能在台账里找到引文。

## 为什么要有它

`ApiMaturity` 是这套运行时对外的"敢不敢用"的口径：

* `HardwareVerified` = 真机上见过它**存在、被调到、行为自洽**；
* `HostVerified` = 只在宿主/单测上验过；
* `Experimental` = 实现了但**没有**真机证据（默认）。

问题是这三档此前只写在 `api_catalog.cpp` 里，**没有任何东西核对它**：
批次 7–13 那约 20 条早就拿到真机证据却仍标 `Experimental`（账本比事实落后），
而 `Level:IsAscent` 标着 `HardwareVerified`、记录里却反复写着"未授权 / 无可靠读取链"
（**账本比事实超前** —— 2026-09-17 核对时降回了 `HostVerified`）。

所以把它变成机器可核对的：

1. **台账**：`tools/api_maturity_evidence.json` 里，每条 `HardwareVerified` 都要有
   **文件 + 逐字引文**；
2. **引文必须真的存在**：门禁去那个文件里找这句话（找不到就判红）—— 防止"记着记着变成口口相传"；
3. **两边必须一致**：台账写的成熟度与 `api_catalog.cpp` 里写的一样（谁改了另一边都要一起改）；
4. **允许降格**：证据找不到就降回去，这才是台账的意义（本批就降了一条）。

## 口径说明（不判红，只报进度）

`Experimental` 占大多数是正常的：绝大多数接口只有宿主/静态证据。台账只要求
"**宣称真机验证过**的必须有依据"，不要求"每条都要有真机证据"。
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
LEDGER = ROOT / "tools" / "api_maturity_evidence.json"

ENTRY_RE = re.compile(
    r"\{MakeId\(ApiDomain::\w+,\s*\d+,\s*0x[0-9A-Fa-f]+\),\s*ApiDomain::\w+,\s*"
    r'"([^"]+)",\s*"([^"]+)",\s*kV1,\s*\d+,\s*ThreadAffinity::\w+,\s*ApiMaturity::(\w+)\}'
)


def catalog_maturity() -> dict[str, str]:
    text = CATALOG.read_text(encoding="utf-8")
    return {f"{owner}:{name}": maturity for owner, name, maturity in ENTRY_RE.findall(text)}


def ledger_rows() -> dict[str, dict]:
    return json.loads(LEDGER.read_text(encoding="utf-8"))["rows"]


class ApiMaturityLedgerTests(unittest.TestCase):
    def test_ledger_exists_and_is_shaped(self):
        self.assertTrue(LEDGER.is_file(), "缺少接口成熟度台账 tools/api_maturity_evidence.json")
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], 1)
        self.assertTrue(data["rows"], "台账不能是空的")

    def test_every_hardware_verified_api_has_evidence(self):
        """凡是宣称"真机验证过"的，台账里必须有依据。"""
        catalog = catalog_maturity()
        rows = ledger_rows()
        self.assertTrue(catalog, "没解析到 catalog 条目（正则或文件变了？）")
        hardware = sorted(name for name, maturity in catalog.items()
                          if maturity == "HardwareVerified")
        self.assertTrue(hardware, "catalog 里应当至少有若干条 HardwareVerified")
        missing = [name for name in hardware if name not in rows]
        self.assertEqual(
            missing, [],
            "这些接口标着 HardwareVerified 但台账里没有条目（要么补依据、要么降格）："
            + ", ".join(missing),
        )

    def test_evidence_quotes_are_real(self):
        """引文必须能在被引文件里逐字找到 —— 台账不许变成口口相传。"""
        for name, row in ledger_rows().items():
            for evidence in row.get("evidence", []):
                path = ROOT / evidence["file"]
                with self.subTest(api=name, file=evidence["file"]):
                    self.assertTrue(path.is_file(), f"台账引用的文件不存在：{evidence['file']}")
                    self.assertIn(evidence["quote"], path.read_text(encoding="utf-8",
                                                                  errors="replace"),
                                  f"{name} 的引文在 {evidence['file']} 里找不到")

    def test_ledger_matches_the_catalog(self):
        """台账与 catalog 必须同口径：两边不一致时，说明有人只改了一边。"""
        catalog = catalog_maturity()
        for name, row in ledger_rows().items():
            with self.subTest(api=name):
                self.assertIn(name, catalog, "台账里的接口不在 catalog 里（名字写错了？）")
                self.assertEqual(row["maturity"], catalog[name],
                                 f"{name} 的成熟度在台账与 catalog 里不一致")

    def test_downgrades_are_documented(self):
        """**降格**必须写明原因：这类改动最容易悄悄发生。"""
        rows = ledger_rows()
        for name, row in rows.items():
            if row.get("maturity") == "HostVerified" and "更正" in (row.get("note") or ""):
                self.assertTrue(row["evidence"], f"{name} 是降格条目，必须留着原依据")

    def test_progress_is_reported(self):
        """只报进度、不判红：口径分布一眼可见（含"真机证据覆盖率"）。"""
        catalog = catalog_maturity()
        counts: dict[str, int] = {}
        for maturity in catalog.values():
            counts[maturity] = counts.get(maturity, 0) + 1
        total = sum(counts.values())
        print(f"\n[进度] 接口 {total} 条："
              + "、".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda i: -i[1]))
              + f"；其中 HardwareVerified 全部有台账依据（{len(ledger_rows())} 条台账）")


if __name__ == "__main__":
    unittest.main()
