#!/usr/bin/env python3
"""每条 API 的**完成定义（Definition of Done）**台账：契约依据 / 边界判据 / 成熟度。

## 为什么要有它（2026-09-21，用户提出的问题）

这个项目的验收基准一直是三维：① 存在、② 语义、③ 派发时机。前两维此前**各有各的账**：

* "存在" ⇒ `runtime/src/interfaces/lua/api_catalog.cpp`（目录行就是真值源）；
* "语义" ⇒ `api_deviation.cpp` 那张**偏离**台账（只有"与 PC 不同"的地方才登记）。

问题出在**中间那一大片**：一条新 API 加进来时，"它凭什么说自己是 PC 的那个语义"、
"边界/异常输入是什么口径"这两件事**没有任何地方强制交代** —— 想写就写在实现处的注释里，
不写也没人问。注释不会被门禁读、不会被读数带出来、更不会拦住下一个人。

⇒ 所以把"实现一条 API 时**必须交代**的三件事"做成一份台账 + 一条**会红的**门禁：

1. **契约依据**：这条 API 在 `tools/pc_contract_docs/<页>.md` 的哪一行（行号 + 那一行的原文片段）；
2. **边界判据**：至少一条"边界/异常输入"的判据 —— 写明**输入形状**（越界下标 / nil 参数 / 空表 /
   同帧重复调用 …）**并**点名一个仓库里真实存在的测试文件；
3. **成熟度**：四态之一（`HardwareVerified` / `HostVerified` / `Experimental` / `Disabled`），
   并且要在 `tools/api_maturity_evidence.json` 里**有登记**（"凭什么这么说"写在那份台账里）。

## 为什么是**新开一份**台账，而不是扩展 `api_maturity_evidence.json`

* **口径不同**：成熟度台账的口径是"**宣称真机验证过的**必须有依据"（所以它只有 30 条、`Experimental`
  的反而不进去）；而本台账的口径是"**每条新 API 都必须交代**"（默认全量）。两者的行集故意不一样，
  混在一起之后"台账多少条"会同时表示两件事，这正是项目里被咬过两次的那种口径混淆。
* **生命周期不同**：成熟度会**升降格**（`Level:IsAscent` 就降过），契约依据与边界口径则是
  **实现时一次定死**、之后只在真的变了才改。混在一起会让人不敢动成熟度（怕碰坏契约那栏）。
* **不变式不同**：成熟度台账要求"台账 ⊆ catalog"；本台账还要求"**catalog 里的新条目 ⊆ 台账**"
  （反方向的那一半），这是本门禁存在的全部意义。

## 判据（改宽改窄都会红）

* **基线冻结**：`baseline.ids` 是**本门禁建立之前**就已经存在的那批 API 的**快照**，
  它们 grandfather 掉（不要求补三件事，补了的按下面的规则一并校验）。基线**只读**：
  门禁核对"基线 ⊆ 当前 catalog"（不许偷偷删 API）、"基线条数/摘要不变"（不许把新 API 塞进基线来躲门禁）。
* **基线之外的每一个 catalog id** 都必须在本台账 `rows` 里有条目，且三件事齐备 —— 缺哪件报哪件（`[新接口]`）。
* `rows` 里出现的每一个 key 都必须**真实存在于 catalog**（打错名字 = 死账，`[死账]`）。
* `contract`：页必须在 `tools/pc_contract_docs/` 或 `tools/pc_enum_docs/` 下**且真的存在**
  （契约源必须在仓库里 —— 批次 111 的教训：`analysis/` 是 gitignore 的，指向那里等于对别人不可做）、
  行号在范围内、`quote` 必须**逐字出现在那一行里**、并且**引文里要出现这条 API 的名字**
  （抄错行、凭记忆写一句、随手抄另一条 API 的那一行，都过不去）。
  文档里确实没有这一条时写 `"missing": "文档里没有 <说明>"` —— 明确写出来也算数，但不许留空。
* `boundary`：`kind` 必须取自受控词表；`judgement` 必须是**真实存在**的 `runtime/tests/**.py`，
  **并且那个文件里必须真的提到这条 API**（按接口名或 id 十六进制找）—— 否则"判据"是随便指的一个文件；
  `detail` 必须写清钉住了什么输入形状（不许 `暂无`/`TODO` 占位）。
* `maturity`：本台账里写的必须与 `api_catalog.cpp` 里的**逐字一致**（真值源仍是 catalog），
  且**基线之外**的 API 必须在 `api_maturity_evidence.json` 里有条目、成熟度也一致（三处一致）。

## 用法

    python3 tools/api_definition_of_done.py                 # 现状：台账条数、覆盖、缺口（不判红）
    python3 tools/api_definition_of_done.py --check         # 跑判据；有问题则退出码 1（门禁用）
    python3 tools/api_definition_of_done.py --gaps          # 列出基线里还没台账条的 API（按 owner 分组）
    python3 tools/api_definition_of_done.py --template "Room:GetDoor"   # 打印一份可粘贴的条骨架

新加一条 API 时的动作顺序（三件事都做完，门禁才会绿）：

    1. 在 catalog 里加目录行；
    2. `--template "<Owner:Name>"` 拿骨架 → 填 `contract`/`boundary` → 粘进 `tools/api_definition_of_done.json` 的 `rows`；
    3. 在 `tools/api_maturity_evidence.json` 的 `rows` 里加同名条目（成熟度与 catalog 一致）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
LEDGER = ROOT / "tools" / "api_definition_of_done.json"
MATURITY_LEDGER = ROOT / "tools" / "api_maturity_evidence.json"

#: 域名 → 数值（用于把 `MakeId(...)` 还原成完整 id）。
#:
#: ★ 这张表与 `runtime/src/interfaces/api_descriptor.hpp` 的 `enum class ApiDomain` 必须一致 ——
#: 门禁 `test_api_definition_of_done.py::test_domain_table_matches_the_cpp_enum` 会直接解析那个
#: 头文件来比对，加了新域名却忘了同步这里会当场红（**口径只有一份，漂移要被抓住**）。
#: （`runtime/tests/contract/test_api_deviation.py` 里也有一张同形的表，但它少了 `ModMenu`，
#: 那份属于那个门禁自己的事，本工具不改别人的解析口径。）
DOMAIN_VALUES = {
    "Global": 0, "Mod": 1, "Game": 2, "Level": 3, "Room": 4, "ItemPool": 5,
    "Music": 6, "Rng": 7, "Persistence": 8, "Input": 9, "Diagnostic": 10,
    "Font": 11, "Vector": 12, "Sprite": 13, "Isaac": 14, "Seed": 15, "ModMenu": 16,
}

#: 成熟度四态（与 C++ 侧 `ApiMaturity` 一致）。
MATURITIES = ("HardwareVerified", "HostVerified", "Experimental", "Disabled")

#: 契约页允许待的目录（**必须在仓库里**；`analysis/` 是 gitignore 的，指过去等于白指）。
CONTRACT_DOC_DIRS = ("tools/pc_contract_docs/", "tools/pc_enum_docs/")

#: "文档里没有这一条"的写法前缀。
CONTRACT_ABSENT_PREFIX = "文档里没有"

#: 边界输入形状的受控词表。不在表里的形状写 `其他`，并在 `detail` 里写清是什么。
BOUNDARY_KINDS = (
    "越界下标", "越界数值", "nil 参数", "类型错误参数", "空表", "缺少参数", "多余参数",
    "同帧重复调用", "回调外调用", "失效句柄", "其他",
)

#: 判据文件的形态：必须是仓库里的测试模块。
JUDGEMENT_RE = re.compile(r"^(?:runtime/)?tests/[A-Za-z0-9_./-]+\.py$")

#: 占位式写法（出现即判红 —— "写了等于没写"）。
PLACEHOLDER_WORDS = ("暂无", "TODO", "TBD", "待补", "n/a", "N/A", "???", "待定")

#: catalog 的一条目录行。形状与 `test_api_maturity_ledger.py` 里的正则一致
#: （那个门禁也要用的字段，多出一份解析口径就会漂移 —— 本模块的 `--check` 会与它交叉核对）。
CATALOG_ENTRY_RE = re.compile(
    r"\{MakeId\(ApiDomain::(\w+),\s*(\d+),\s*(0x[0-9A-Fa-f]+)\)\s*,\s*ApiDomain::\w+,\s*"
    r'"([^"]+)",\s*"([^"]+)",\s*kV1,\s*\d+,\s*ThreadAffinity::\w+,\s*ApiMaturity::(\w+)\}'
)


@dataclass(frozen=True)
class CatalogEntry:
    """catalog 里的一条 API。`key` 就是台账的键（`Owner:Name`，与成熟度台账同一形状）。"""

    identifier: int
    owner: str
    name: str
    maturity: str

    @property
    def key(self) -> str:
        return f"{self.owner}:{self.name}"

    @property
    def hex_id(self) -> str:
        return f"0x{self.identifier:08X}"


def load_catalog(path: Path | None = None) -> dict[str, CatalogEntry]:
    """解析 `api_catalog.cpp` 的目录行 → `{Owner:Name: CatalogEntry}`。"""
    text = (path or CATALOG).read_text(encoding="utf-8")
    entries: dict[str, CatalogEntry] = {}
    for domain, group, sequence, owner, name, maturity in CATALOG_ENTRY_RE.findall(text):
        value = DOMAIN_VALUES.get(domain)
        if value is None:  # 新增了域名但没同步这张表 —— 让门禁自己去红，不要静默跳过
            raise ValueError(f"未知的 ApiDomain::{domain}（本工具的 DOMAIN_VALUES 需要同步）")
        entry = CatalogEntry(
            identifier=(value << 24) | (int(group) << 16) | int(sequence, 16),
            owner=owner,
            name=name,
            maturity=maturity,
        )
        entries[entry.key] = entry
    return entries


def load_ledger(path: Path | None = None) -> dict:
    return json.loads((path or LEDGER).read_text(encoding="utf-8"))


def load_maturity_rows(path: Path | None = None) -> dict:
    """成熟度台账的 `rows`（"凭什么说它到了这一档"写在那里）。"""
    return json.loads((path or MATURITY_LEDGER).read_text(encoding="utf-8"))["rows"]


def baseline_digest(keys) -> str:
    """基线集合的稳定摘要 —— 用来把基线**钉死**（不许往基线里塞新 API 躲门禁）。"""
    material = "\n".join(sorted(keys)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def _is_placeholder(text: str) -> bool:
    return any(word in text for word in PLACEHOLDER_WORDS)


def identifier_forms(entry: CatalogEntry) -> tuple[str, ...]:
    """"这个测试文件真的在讲这条 API 吗"要认的几种写法。"""
    return (
        entry.name,
        f"0x{entry.identifier:08X}",
        f"0x{entry.identifier:08x}",
        f"0x{entry.identifier:X}",
        f"0x{entry.identifier:x}",
    )


def contract_problems(entry: CatalogEntry, contract, root: Path) -> list[str]:
    """契约依据这一栏的问题列表（空 = 合格）。"""
    tag = f"[契约依据] {entry.key}"
    if not isinstance(contract, dict):
        return [f"{tag}：没有 `contract` 一栏（要么写页:行号 + 原文，要么写 'missing'）"]

    # 形态二：文档里确实没有这一条 —— 必须写明是什么，不许留空。
    if "missing" in contract:
        reason = contract.get("missing")
        if not isinstance(reason, str) or not reason.startswith(CONTRACT_ABSENT_PREFIX):
            return [f"{tag}：`contract.missing` 必须以「{CONTRACT_ABSENT_PREFIX}」开头并写明是什么"]
        if len(reason) <= len(CONTRACT_ABSENT_PREFIX) + 4 or _is_placeholder(reason):
            return [f"{tag}：'文档里没有 …' 后面没写清是什么（等于没写）"]
        return []

    page_text = contract.get("page")
    line_text = contract.get("line")
    quote = contract.get("quote")
    problems: list[str] = []
    if not isinstance(page_text, str) or not page_text:
        return [f"{tag}：缺少 `contract.page`（形如 tools/pc_contract_docs/Room.md）"]
    if not page_text.startswith(CONTRACT_DOC_DIRS):
        problems.append(
            f"{tag}：契约页 {page_text} 不在 {' / '.join(CONTRACT_DOC_DIRS)} 下 —— "
            "契约源必须在仓库里（analysis/ 是 gitignore 的，指过去对别人不可做）"
        )
        return problems
    page = root / page_text
    if not page.is_file():
        return [f"{tag}：契约页不存在：{page_text}（用到别的页时要把那页照 README 复制进仓库）"]
    if not isinstance(line_text, int) or line_text <= 0:
        return [f"{tag}：`contract.line` 必须是正整数（现在 {line_text!r}）"]
    lines = page.read_text(encoding="utf-8", errors="replace").splitlines()
    if line_text > len(lines):
        return [f"{tag}：{page_text} 只有 {len(lines)} 行，没有第 {line_text} 行"]
    if not isinstance(quote, str) or len(quote) < 4:
        return [f"{tag}：`contract.quote` 太短（要把那一行里逐字出现的片段抄进来）"]
    if _is_placeholder(quote):
        return [f"{tag}：`contract.quote` 是占位写法（{quote!r}）—— 必须抄真实原文"]
    if quote not in lines[line_text - 1]:
        return [
            f"{tag}：{page_text}:{line_text} 那一行里没有「{quote}」—— 引用与文档对不上。\n"
            f"        那一行实际是：{lines[line_text - 1][:160]!r}"
        ]
    # ★ 反向的那一半：引文里必须出现**这条 API 的名字**。
    #   为什么：只核对"片段真的在那一行里"挡不住"随手抄另一条 API 的那一行" —— 那也是假通过
    #   （与 099 那次"关键词恰好出现"是同一族）。PC 文档里每条 API 都有自己的规格行
    #   （形如 `#### int GetGridPath ( int Index )`），所以这条在实践中总能满足；
    #   真遇到只能引散文段落的合理情形，改这条规则时要**同步补一个反例**（口径不许悄悄放宽）。
    if entry.name not in quote:
        problems.append(
            f"{tag}：引文里没有出现这条 API 的名字（{entry.name}）—— 契约引用的意义是点名"
            "**这条 API 的规格在哪一行**，抄别的 API 的那一行过不了"
        )
    return problems


def boundary_problems(entry: CatalogEntry, boundary, root: Path) -> list[str]:
    """边界判据这一栏的问题列表（空 = 合格）。"""
    tag = f"[边界判据] {entry.key}"
    if not isinstance(boundary, dict):
        return [f"{tag}：没有 `boundary` 一栏（要写清哪种异常输入、由哪个测试钉住）"]
    problems: list[str] = []

    kind = boundary.get("kind")
    if kind not in BOUNDARY_KINDS:
        problems.append(f"{tag}：`boundary.kind` = {kind!r} 不在受控词表里：{list(BOUNDARY_KINDS)}")

    detail = boundary.get("detail")
    if not isinstance(detail, str) or len(detail) < 8 or _is_placeholder(detail):
        problems.append(f"{tag}：`boundary.detail` 要写清钉住了什么输入形状（≥8 字，不许占位）")

    judgement = boundary.get("judgement")
    if not isinstance(judgement, str) or not JUDGEMENT_RE.match(judgement):
        problems.append(
            f"{tag}：`boundary.judgement` = {judgement!r} 不是仓库里的测试模块"
            "（形如 runtime/tests/test_lua_room_grid.py）"
        )
        return problems
    path = root / judgement
    if not path.is_file():
        problems.append(f"{tag}：判据指向不存在的测试文件：{judgement}")
        return problems

    # ★ 反"随手指一个测试文件"：那个文件里必须真的提到这条 API（按接口名或 id 找）。
    content = path.read_text(encoding="utf-8", errors="replace")
    if not any(form in content for form in identifier_forms(entry)):
        problems.append(
            f"{tag}：判据文件 {judgement} 里找不到这条 API 的名字（{entry.name}）或 id（{entry.hex_id}）"
            " —— 那多半不是钉这条 API 的测试"
        )
    return problems


def maturity_problems(entry: CatalogEntry, declared, maturity_rows: dict,
                      require_registration: bool) -> list[str]:
    """成熟度这一栏的问题列表（空 = 合格）。

    `require_registration=True`（基线之外的新 API）：还必须在成熟度台账里有条目 ——
    "凭什么说它到了这一档"要有地方写，这条就是本门禁与 `test_api_maturity_ledger` 的接口。
    """
    tag = f"[成熟度] {entry.key}"
    problems: list[str] = []
    if declared not in MATURITIES:
        problems.append(f"{tag}：台账里的成熟度 {declared!r} 不是四态之一：{list(MATURITIES)}")
    elif declared != entry.maturity:
        problems.append(
            f"{tag}：台账写 {declared}、catalog 写 {entry.maturity} —— 真值源是 catalog，"
            "两边必须一起改"
        )
    row = maturity_rows.get(entry.key)
    if require_registration and row is None:
        problems.append(
            f"{tag}：tools/api_maturity_evidence.json 里没有 {entry.key} 的条目"
            "（新 API 必须在成熟度台账里登记四态之一）"
        )
    elif row is not None and row.get("maturity") != entry.maturity:
        problems.append(
            f"{tag}：成熟度台账写 {row.get('maturity')}、catalog 写 {entry.maturity} —— 三处必须一致"
        )
    return problems


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    new_apis: list[str] = field(default_factory=list)
    rows_checked: int = 0
    baseline_size: int = 0
    gaps: list[str] = field(default_factory=list)
    catalog_size: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def check(root: Path | None = None, catalog_path: Path | None = None,
          ledger_path: Path | None = None, maturity_path: Path | None = None) -> Report:
    """跑完整套判据。`root` 可指向别处（合成仓库），供门禁自证"能红"。"""
    root = Path(root) if root is not None else ROOT
    catalog_path = Path(catalog_path) if catalog_path else root / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
    ledger_path = Path(ledger_path) if ledger_path else root / "tools" / "api_definition_of_done.json"
    maturity_path = Path(maturity_path) if maturity_path else root / "tools" / "api_maturity_evidence.json"

    report = Report()
    try:
        catalog = load_catalog(catalog_path)
    except (OSError, ValueError) as error:
        report.errors.append(f"[catalog] 读不了 {catalog_path}：{error}")
        return report
    report.catalog_size = len(catalog)
    if not catalog:
        report.errors.append(f"[catalog] 没解析到任何目录行（{catalog_path} 形状变了？）")
        return report

    try:
        ledger = load_ledger(ledger_path)
    except (OSError, ValueError) as error:
        report.errors.append(f"[台账] 读不了 {ledger_path}：{error}")
        return report
    try:
        maturity_rows = load_maturity_rows(maturity_path)
    except (OSError, ValueError) as error:
        report.errors.append(f"[成熟度台账] 读不了 {maturity_path}：{error}")
        return report

    if ledger.get("schema") != 1:
        report.errors.append("[台账] schema 必须是 1")
    baseline = ledger.get("baseline")
    if not isinstance(baseline, dict) or not isinstance(baseline.get("ids"), list):
        report.errors.append("[台账] 缺少 baseline.ids（基线快照）")
        return report
    baseline_ids = baseline["ids"]
    report.baseline_size = len(baseline_ids)
    duplicates = sorted({key for key in baseline_ids if baseline_ids.count(key) > 1})
    if duplicates:
        report.errors.append(f"[基线] 基线里有重复项：{duplicates}")
    missing_from_catalog = sorted(set(baseline_ids) - set(catalog))
    if missing_from_catalog:
        report.errors.append(
            f"[基线] 基线里这些 API 在当前 catalog 里**不见了**（不许偷偷删接口）：{missing_from_catalog}"
        )

    rows = ledger.get("rows")
    if not isinstance(rows, dict):
        report.errors.append("[台账] 缺少 rows")
        return report

    # ① 死账：台账里的 key 必须在 catalog 里真的存在。
    unknown = sorted(set(rows) - set(catalog))
    if unknown:
        report.errors.append(f"[死账] 台账里的这些 key 在 catalog 里不存在（名字写错了？）：{unknown}")

    # ② 逐条校验已登记的条目（基线内的也校验 —— 登记了就得合格）。
    for key, row in sorted(rows.items()):
        entry = catalog.get(key)
        if entry is None or not isinstance(row, dict):
            continue
        report.rows_checked += 1
        report.errors.extend(contract_problems(entry, row.get("contract"), root))
        report.errors.extend(boundary_problems(entry, row.get("boundary"), root))
        report.errors.extend(maturity_problems(entry, row.get("maturity"), maturity_rows,
                                               require_registration=key not in set(baseline_ids)))

    # ③ 门禁的正题：**基线之外**的每个 catalog id 都必须三件事齐备。
    for key, entry in sorted(catalog.items()):
        if key in set(baseline_ids):
            continue
        report.new_apis.append(key)
        row = rows.get(key) if isinstance(rows.get(key), dict) else {}
        missing: list[str] = []
        if contract_problems(entry, row.get("contract"), root):
            missing.append("契约依据")
        if boundary_problems(entry, row.get("boundary"), root):
            missing.append("边界判据")
        if maturity_problems(entry, row.get("maturity") if row else None, maturity_rows,
                            require_registration=True):
            missing.append("成熟度")
        if missing:
            report.errors.append(
                f"[新接口] {key}（{entry.hex_id}）没有完成定义，缺：{'、'.join(missing)}"
                "（见 tools/api_definition_of_done.py 文件头的判据与 --template）"
            )

    report.gaps = sorted(key for key in baseline_ids if key not in rows)
    return report


def template(key: str, catalog: dict[str, CatalogEntry]) -> str:
    """给一条 API 打印可粘贴的骨架（新加 API 时用）。"""
    entry = catalog.get(key)
    maturity = entry.maturity if entry else "<四态之一>"
    skeleton = {
        key: {
            "contract": {
                "page": "tools/pc_contract_docs/<页>.md",
                "line": 0,
                "quote": "<那一行里逐字出现的原文片段>",
            },
            "boundary": {
                "kind": "<受控词表里的形状>",
                "judgement": "runtime/tests/<测试模块>.py",
                "detail": "<说清钉住了哪种异常输入、期望是什么>",
            },
            "maturity": maturity,
        }
    }
    return json.dumps(skeleton, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="跑判据；有问题则退出码 1")
    parser.add_argument("--gaps", action="store_true", help="列出基线里还没有台账条的 API")
    parser.add_argument("--template", default="", help="打印某条 API 的台账骨架（Owner:Name）")
    args = parser.parse_args(argv)

    try:
        catalog = load_catalog()
    except (OSError, ValueError) as error:
        # 解析不了就直说（例如新加了域名却没同步 DOMAIN_VALUES）—— 不要甩一整段 traceback。
        print(f"[catalog] 读不了 {CATALOG}：{error}", file=sys.stderr)
        return 2
    if args.template:
        if args.template not in catalog:
            print(f"catalog 里没有 {args.template}（先加目录行再来拿骨架）", file=sys.stderr)
            return 2
        print(template(args.template, catalog))
        return 0
    report = check()
    if args.gaps:
        by_owner: dict[str, list[str]] = {}
        for key in report.gaps:
            owner, _, name = key.partition(":")
            by_owner.setdefault(owner, []).append(name)
        print(f"基线 {report.baseline_size} 条里，还没有完成定义台账条的：{len(report.gaps)} 条")
        for owner in sorted(by_owner):
            print(f"  {owner}（{len(by_owner[owner])}）：" + "、".join(sorted(by_owner[owner])))
        return 0

    print(f"catalog {report.catalog_size} 条；基线 {report.baseline_size} 条；"
          f"已登记台账条 {report.rows_checked} 条；基线之外的新接口 {len(report.new_apis)} 条")
    print(f"缺口（基线里还没交代的）：{len(report.gaps)} 条 —— 用 --gaps 看名单")
    if report.errors:
        print(f"\n★ 判据未通过，共 {len(report.errors)} 项：", file=sys.stderr)
        for problem in report.errors:
            print(f"  - {problem}", file=sys.stderr)
    if args.check:
        return 0 if report.ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
