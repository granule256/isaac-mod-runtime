"""`api_deviation.cpp` 那张"与 PC 语义的偏离"表的契约门禁。

## 为什么要有这张表、这条门禁

验收基准是三维：① 存在、② 语义、③ 派发时机。其中"② 语义不满足"必须**被标记出来**。
在此之前偏离只写在实现处的注释里 —— 注释不会被任何报告、清单或设备读数带出来，
于是"实现正确"和"实现但有已知偏离"就分不清，批量补齐 API 时更没法逐条收口。

本文件守住四件事：

1. **每条偏离的 id 都必须在 `api_catalog.cpp` 里真实存在**（否则是打错 id 的死账）；
2. **文本必须同时说清"差在哪"和"后果"**（没有后果说明的条目无法用于判断"要不要现在修"）；
3. **条数写死在测试里**：新增/删除都必须人工过一遍（与 `test_api_catalog` 的绑定行数
   是同一套记账方式）；
4. 同一 id 不得重复登记。

（与项目其它源码门禁同一形态：只做受控文本提取，不做 C++ 解析。）
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
DEVIATIONS = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_deviation.cpp"

#: 当前表里的条数。新增或删除偏离条目时**必须**同步这个数字并在上面补一行说明。
#:
#: 首次建立（2026-09-15，地基一期）共 22 条，来源是代码注释里**明确承认**偏离的地方：
#:   `Options.HUDOffset`（1）；`Game:GetSeeds`/`GetVictoryLap` 与 `Seeds:IsCustomRun`/
#:   `GetStartSeed`（4）；`Level:GetCurses`（1）；`Room` 网格与寻路六条（6）；
#:   `Sprite:GetTexel`（1）；`Isaac.GetTime`（1）；`Entity`/`EntityPlayer:GetData`（2）；
#:   `ItemConfig`/`ItemConfig_Item:HasTags`（2）；`EntityPickup:IsShopItem`（1）；
#:   `EntityPlayer:GetPill`/`GetCard`（2）；`EntityPlayer:GetName`（1）。
#:
#: **22 → 21（2026-09-16）**：`Room:GetGridEntity()`（`0x04010007`）的偏离**已解除** ——
#: 网格实体表定位到 `Room + 0x30`（证据见 `runtime_constants.hpp` 的
#: `kRoomGridEntityTableOffset`），现在返回真实句柄；`GridEntity:GetVariant()`/`GetType()`
#: 同批落地。这是**第一条第 ④ 类偏离被消掉**（不是"改成不承认"，而是真的实现出来了）。
#:
#: **21 → 22（2026-09-16，批次 13）**：新增 `GridEntity:GetRNG()`（`0x0E010054`）一条
#: `Partial` —— PC 返回引擎 RNG 的**引用**，我们交回的是**取到那一刻的 16 字节快照**
#: （理由见 `api_deviation.cpp` 那一整段：网格实体随时销毁，而句柄只存实体地址、拿不到网格
#: 下标，做不到"每次访问重新解析并校验"）。同批的 `ItemPool:IsPillIdentified`（`0x05010003`）
#: 与 `RNG:GetSeed`（`0x07010003`）都是真读引擎字段/自身句柄，**不**记偏离。
#:
#: **23 → 19（2026-09-20，批次 098）**：`Room` 网格族的四条偏离**被真正的实现消掉** ——
#: `GetGridWidth`（`0x04010002`）、`GetGridHeight`（`0x04010003`）、`GetGridSize`（`0x04010004`）、
#: `GetGridIndex`（`0x04010005`）。起因是**用户可见**缺陷：`GetGridPath` 恒返 1000
#: （> EID 的 900 阈值）⇒ 地上每一颗药丸、每一张卡片都被判"够不到"、只画问号。
#: 网格尺寸字段（`Room + 0x14`/`+0x18`）、通行代价数组（`Room + 0xE98`）与格坐标换算
#: （`Room::GetGridIndex(Vector2) @ 0x459e3c`）本轮全部定位，证据见 `runtime_constants.hpp`；
#: `GetGridPath`（`0x04010006`）由 `Placeholder` 降为 `Partial`（只剩"越界给 0 而不是越界读"
#: 这一条口径差异）。判据：`runtime/tests/test_lua_room_grid.py`、
#: `tools/room_grid_reachability_probe.py`。
#:
#: **21 → 24（2026-09-21，批次 017）**：补进三条**平台降级** —— `Input.GetMousePosition`（`0x09010007`）、
#: `Input.IsMouseBtnPressed`（`0x09010008`）、`Isaac.ExecuteCommand`（`0x0E01002D`）。
#: 它们的事实此前只写在 `api_catalog.cpp` 的目录注释与实现注释里（原话就是"平台降级 / 平台限制"），
#: 符合本表"只收代码注释里已经明确承认的偏离"的收表口径，却一直没被收进来 —— 于是台账里
#: **一条"平台固有"都没有**，"这条差异还能不能还"这个问题在表里就没有答案。
#: 本批给每条加了"性质"字段（见下文 `EXPECTED_PLATFORM` / `EXPECTED_DEBT` / `EXPECTED_DESIGN`），
#: 三条平台条目是本批唯一的**新增**（其余 21 条只加字段、正文的语义结论与判据一字未改）。
#: 起因与口径见 `dist/change-archive-20260921/017-deviation-nature-split/README.md`。
EXPECTED_DEVIATIONS = 24

#: **按性质分组的条数**（2026-09-21，批次 017 建立；口径逐字写在 `api_deviation.cpp` 文件头）：
#:
#:   * `platform`（平台固有）= PC 上有对应物、Switch 平台侧**没有可用底座或语义无法映射**，
#:     且**已经取证过"没有"** ⇒ 继续做工作也消不掉；
#:   * `debt`（我们的欠账）= 底座**存在或可定位**，只是还没定位 / 没实现 / 实现得偏保守 ⇒ **能还**；
#:   * `design`（主动保留的口径差异）= 两侧都做得到，但我们**有意**选了别的口径、且台账写明不打算改
#:     （复刻 PC 等于复刻它的未定义行为；或照着做会把引擎内部指针交给模组）⇒ 不改。
#:
#: **这三个数字都只能降不能升**（消掉一条偏离就把它改小，并在上面补一行说明为什么 —— 与
#: `EXPECTED_DEVIATIONS`、`EXPECTED_JUDGEMENT_GAPS` 同一套记账方式）。新增偏离时**必须**同时
#: 想清楚它属于哪一类：想不清楚就说明这条偏离还没调查到能判断"能不能还"的程度，别急着登记。
#:
#: **platform 3 → 2、debt 19 → 20（2026-09-25，批次 121）**：`Isaac.ExecuteCommand`（`0x0E01002D`）
#: 那条"平台固有"的**前提被推翻了** —— 当时记为"Switch 没有控制台"，而事实是**控制台类与全部
#: 命令实现都在镜像里**（引擎只是从不实例化它：构造/`Init`/`Update`/`Render`/`ShowKeyboard`
#: 的调用边全是 0）。运行时现在自己建一个 `Console` 实例并调它的 `RunCommand`，返回值也照 PC 契约
#: 给字符串（`Isaac.md:106`）。⇒ 它从"平台固有"变成"**能还的欠账**"：残留的两条限制
#: （命令长度上限 127 字节、没有玩家时拒绝执行）都是我们实现侧的。
#: 总数 `EXPECTED_DEVIATIONS` 不变（只是改了性质），判据：`runtime/tests/test_console_bridge.py`
#: 与 `dist/change-archive-20260925/121-console-bridge/README.md`。
EXPECTED_PLATFORM = 2
EXPECTED_DEBT = 20
EXPECTED_DESIGN = 2

#: "判据：暂无（…）"的条数 —— **欠账**，只能降不能升。
#:
#: 2026-09-20（批次 099）建立这条记账方式时是 **0**：当天给 19 条全部补上了可执行判据
#: （每条点名一个仓库里真实存在的测试文件，并写明它钉住了什么、**哪一半没钉**）。
#: 以后新增偏离又一时给不出判据的，可以写"判据：暂无（理由…）"，但必须把这个数字 +1
#: 并在这段注释里说明 —— 让欠账有数字、有出处，而不是靠记性。
EXPECTED_JUDGEMENT_GAPS = 0

#: 允许的偏离种类（与 `ApiDeviationKind` 一致）。
KINDS = {"Partial", "Placeholder", "NotInEngine"}


def catalog_ids(text: str) -> set[int]:
    """`api_catalog.cpp` 里所有条目的完整 id。

    只算 `MakeId(...)` 调用 —— 目录里每条 API 都这么写（这是该文件的既有约定，
    `test_api_catalog` 的"家族绑定 id 必须与 Catalog 一致"那条也依赖同一形状）。
    """
    ids = set()
    domain_values = {
        "Global": 0, "Mod": 1, "Game": 2, "Level": 3, "Room": 4, "ItemPool": 5,
        "Music": 6, "Rng": 7, "Persistence": 8, "Input": 9, "Diagnostic": 10,
        "Font": 11, "Vector": 12, "Sprite": 13, "Isaac": 14, "Seed": 15,
    }
    for match in re.finditer(
        r"MakeId\(ApiDomain::(\w+),\s*(\d+),\s*(0x[0-9A-Fa-f]+)\)", text
    ):
        domain, group, sequence = match.groups()
        if domain not in domain_values:
            continue
        ids.add((domain_values[domain] << 24) | (int(group) << 16) | int(sequence, 16))
    return ids


def deviation_entries(text: str) -> list[tuple[int, str, str]]:
    """从 `api_deviation.cpp` 提取 `(id, kind, 文本)`。

    解析口径**只有一份**，在 `tools/api_deviation_ledger.py`（读数的"风险面"那一段也用它，
    两边不许各写一套正则）。这里保留这个函数名只是为了不动既有调用方。
    """
    from tools.api_deviation_ledger import load_entries

    return [(entry.identifier, entry.kind, entry.text) for entry in load_entries(DEVIATIONS)]


class ApiDeviationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CATALOG.read_text(encoding="utf-8")
        cls.deviations = DEVIATIONS.read_text(encoding="utf-8")

    def test_every_deviation_points_at_a_real_catalog_entry(self):
        """id 必须在 catalog 里真实存在 —— 打错 id 就等于这条偏离没有任何人会看到。"""
        known = catalog_ids(self.catalog)
        self.assertGreater(len(known), 150, "catalog id 解析结果太少，门禁失去意义")
        unknown = [
            hex(identifier)
            for identifier, _, _ in deviation_entries(self.deviations)
            if identifier not in known
        ]
        self.assertEqual(unknown, [], f"偏离表里出现了 catalog 中不存在的 id：{unknown}")

    def test_kinds_are_known_values(self):
        kinds = {kind for _, kind, _ in deviation_entries(self.deviations)}
        self.assertTrue(kinds, "一条偏离都没解析到 —— 门禁失去意义")
        self.assertTrue(kinds <= KINDS, f"出现了未知的偏离种类：{sorted(kinds - KINDS)}")

    def test_each_entry_states_the_consequence(self):
        """每条都必须有**明确写出来的**"偏离后果：…"。

        ★ 2026-09-20（批次 099）为什么加强：原来的判据是"文本里出现'后果'/'只'/'不'之一"，
        而 `EntityPlayer:GetName()` 那条一个字都没写后果，却因为正文里有"EID **只**做字符串拼接"
        而**通过了** —— 关键词是顺带出现的，判据等于没判。改成要求台账里那个**固定标记**
        （`api_deviation_ledger.CONSEQUENCE_MARKER`）。这类"关键词恰好出现"的假通过，
        与 047 那次"布局表里有这一行就算已实现"是同一族。
        """
        from tools.api_deviation_ledger import CONSEQUENCE_MARKER, load_entries

        entries = load_entries(DEVIATIONS)
        self.assertGreater(len(entries), 10, "一条偏离都没解析到 —— 门禁失去意义")
        missing = [hex(entry.identifier) for entry in entries if not entry.has_consequence]
        self.assertEqual(missing, [],
                         f"这些偏离没有写'{CONSEQUENCE_MARKER}'：{missing}。"
                         "后果必须写清'模组会看到什么'，否则没人能判断要不要现在修。")
        for entry in entries:
            with self.subTest(id=hex(entry.identifier)):
                self.assertGreater(len(entry.consequence), 8,
                                   f"{hex(entry.identifier)} 的'偏离后果'太短，等于没写")
                self.assertNotIn("暂无", entry.consequence,
                                 f"{hex(entry.identifier)} 的后果是'暂无'式占位 —— 那等于没写")

    def test_each_entry_names_an_existing_judgement(self):
        """★ 每条必须给出"判据：<仓库里的测试文件>"，且那个文件真的存在。

        为什么（098 事故的直接教训）：`Room:GetGridPath` 那条偏离**登记过**，但后果那一栏写的是
        "不画路径提示"，真相是"藏掉整条描述" —— 没有判据就没有人会发现写错了。
        所以从现在起，每条偏离都要能回答"**这条偏离靠什么被钉住**"：

        * 判据必须点名至少一个 `tests/**.py`，且该文件**在当前仓库里存在**（改名/删掉会红）；
        * 确实还没有可执行判据的，必须写成"判据：暂无（理由…）"—— 那是**欠账**，
          条数被 `EXPECTED_JUDGEMENT_GAPS` 钉住，**只能降不能升**（与安全桩台账同一套记账方式）。
        """
        from tools.api_deviation_ledger import JUDGEMENT_MARKER, load_entries

        entries = load_entries(DEVIATIONS)
        gaps: list[str] = []
        for entry in entries:
            with self.subTest(id=hex(entry.identifier)):
                if entry.judgement_missing:
                    gaps.append(hex(entry.identifier))
                    continue
                paths = entry.judgement_paths
                self.assertTrue(
                    paths,
                    f"{hex(entry.identifier)} 的'{JUDGEMENT_MARKER}'里没有点名任何 tests/*.py："
                    f"{entry.judgement!r}")
                for relative in paths:
                    self.assertTrue(
                        (ROOT / relative).is_file(),
                        f"{hex(entry.identifier)} 的判据指向不存在的文件：{relative}")
        self.assertEqual(
            len(gaps), EXPECTED_JUDGEMENT_GAPS,
            f"'暂无判据'的偏离条数变了（现在 {len(gaps)} 条：{gaps}）。"
            "要么补上可执行判据，要么在 EXPECTED_JUDGEMENT_GAPS 上面写清为什么又多欠一条。")

    def test_every_entry_states_a_valid_nature(self):
        """★ 每条必须写清**性质**：`platform`（平台固有）/ `debt`（我们的欠账）/ `design`（主动保留）。

        为什么加这条（2026-09-21，批次 017）：台账原来只有"偏离长什么样"（`kind`），读者分不清一条
        偏离是**这台机器上永远消不掉**的，还是**我们还没做到**的 —— 前者登记完就该停止投入，后者
        应当排进待办、还清后把条目删掉。没有这一栏时，两种情况都会办错。

        ★ 口径（逐字写在 `api_deviation.cpp` 文件头，这里只钉"写了没有、取值合不合法"）：
          * `platform` = PC 上有对应物、Switch 平台侧**没有可用底座或语义无法映射**（鼠标、控制台），
            且**已经取证过"没有"**；
          * `debt` = 底座**存在或可定位**，只是还没定位 / 没实现 / 实现得偏保守 ⇒ **能还**；
          * `design` = 两侧都做得到，但我们**有意**选了别的口径且写明不打算改（复刻 PC 的未定义行为、
            或把引擎内部指针交给模组）⇒ 不改。

        "不许有未归类的条目"也在这里判：缺标记（空串）与取值写错都会红。
        """
        from tools.api_deviation_ledger import NATURE_MARKER, NATURES, load_entries

        entries = load_entries(DEVIATIONS)
        self.assertGreater(len(entries), 10, "一条偏离都没解析到 —— 门禁失去意义")
        unclassified = [hex(entry.identifier) for entry in entries if not entry.is_classified]
        self.assertEqual(
            unclassified, [],
            f"这些偏离没有合法的'{NATURE_MARKER}'取值（只能是 {list(NATURES)}）：{unclassified}。"
            "口径见 api_deviation.cpp 文件头；想不清楚属于哪一类，说明这条偏离还没调查到能判断"
            "'能不能还'的程度。")
        # 取值必须与括号里那个中文名对得上（防止只改取值、把名字留在原文里）。
        for entry in entries:
            with self.subTest(id=hex(entry.identifier)):
                self.assertTrue(
                    entry.nature_label,
                    f"{hex(entry.identifier)} 的性质取值 {entry.nature!r} 不在 {list(NATURES)} 里")
                self.assertIn(
                    f"{NATURE_MARKER}{entry.nature}（{entry.nature_label}）", entry.text,
                    f"{hex(entry.identifier)} 的性质标记形状不对：应当是"
                    f"'{NATURE_MARKER}{entry.nature}（{entry.nature_label}）——理由：…'")

    def test_each_entry_states_the_nature_reason(self):
        """★ 每条的性质后面必须跟**一行理由**：读者不看别处就明白为什么这么归类。

        与"偏离后果"同一条纪律（098 的教训）：光有分类标签没有理由，下一个人无法复核 ——
        他只能重新做一遍调查，或者干脆相信这个标签。
        """
        from tools.api_deviation_ledger import NATURE_REASON_MARKER, load_entries

        entries = load_entries(DEVIATIONS)
        missing = [hex(entry.identifier) for entry in entries if not entry.nature_reason]
        self.assertEqual(
            missing, [],
            f"这些偏离没有写'{NATURE_REASON_MARKER}'后面那行理由：{missing}")
        for entry in entries:
            with self.subTest(id=hex(entry.identifier)):
                self.assertGreater(
                    len(entry.nature_reason), 8,
                    f"{hex(entry.identifier)} 的性质理由太短，等于没写：{entry.nature_reason!r}")
                self.assertNotIn(
                    "暂无", entry.nature_reason,
                    f"{hex(entry.identifier)} 的性质理由是'暂无'式占位 —— 那等于没写")

    def test_nature_counts_are_pinned(self):
        """★ 三个性质的**条数**写死 —— 只能降不能升（照 `EXPECTED_*` 那套记账方式）。

        为什么连条数也要钉：`platform` 与 `debt` 的比值就是"这台机器上还有多少是**能还**的"，
        是排期的依据。数字松了就会出现"悄悄把一条欠账标成平台固有、于是没人再管它"这种漂移。
        消掉一条偏离（真的实现出来了）⇒ 把数字改小并补一行说明；新增 ⇒ 说明它为何属于这一类。
        """
        from tools.api_deviation_ledger import load_entries

        entries = load_entries(DEVIATIONS)
        counts: dict[str, int] = {}
        for entry in entries:
            counts[entry.nature] = counts.get(entry.nature, 0) + 1
        expected = {
            "platform": EXPECTED_PLATFORM,
            "debt": EXPECTED_DEBT,
            "design": EXPECTED_DESIGN,
        }
        self.assertEqual(
            counts, expected,
            f"按性质分组的条数变了（现在 {counts}，门禁钉的是 {expected}）。"
            "消掉一条欠账/改判一条性质时，请同步上面三个 EXPECTED_* 并在注释里写清为什么。")
        self.assertEqual(
            sum(expected.values()), EXPECTED_DEVIATIONS,
            "三个性质的条数之和必须等于 EXPECTED_DEVIATIONS —— 有条目没被算进任何一组")

    def test_no_duplicate_ids(self):
        identifiers = [identifier for identifier, _, _ in deviation_entries(self.deviations)]
        duplicates = sorted({value for value in identifiers if identifiers.count(value) > 1})
        self.assertEqual(duplicates, [], f"同一 id 被登记了多次：{[hex(v) for v in duplicates]}")

    def test_the_ledger_count_is_up_to_date(self):
        """条数写死 —— 新增/删除偏离时强制人工过一遍（与绑定行数同一套记账方式）。"""
        self.assertEqual(
            len(deviation_entries(self.deviations)),
            EXPECTED_DEVIATIONS,
            "偏离表的条数变了。请确认每条都写清了'差在哪 + 为什么 + 后果'，"
            "再同步 EXPECTED_DEVIATIONS 并在上面补一行说明。",
        )


class PcContractCitationTests(unittest.TestCase):
    """★ 每条偏离都必须引用 **PC 文档的原文**（批次 111，用户的直接要求）。

    ## 为什么加这条门禁

    2026-09-20 的 107→109→110 三批都在改**同一个** API（`Input.IsActionTriggered`），
    根因是 107 那次**凭推断断言了 PC 的语义**（注释里写着"PC 是同一帧内问多少次都答 true"，
    但**没有任何出处**），而不是去读仓库里本来就有的 PC 文档快照。三批的返工就是这个的账单。

    "以后先读文档"不能靠记性 ⇒ 做成**能红的门禁**：每条偏离（我们与 PC 不同的地方，也就是
    最需要契约的地方）都必须写出

        PC 契约：tools/pc_contract_docs/<页>.md:<行号> 「<原文片段>」

    而这条门禁会**回头核对**：那一页存在、那一行存在、而且那个片段**确实出现在那一行里**
    ⇒ 抄错行、抄错页、凭记忆写一句、都过不去。

    文档里**确实没有**这一条时，写 `PC 契约：文档里没有 <说明>` —— 明确写出来也算数
    （不许留空，也不许用"大概是这样"糊过去）。

    ## 契约页**必须待在仓库里**（批次 111 的嵌套门禁抓出来的）

    第一版引用的是 `analysis/isaacdocs-snapshot/docs/` —— 而 `analysis/` 是 **gitignore 的**，
    于是"只复制已跟踪文件再跑一遍"的嵌套套件（`test_game_file_reader_stage10`）里，
    这些页**根本不存在** ⇒ 所有引用当场失效。这与批次 048 撞 `RoomShape` 时是同一个教训：
    **契约源不在仓库里 = 这一类工作对任何其他人都不可做**。
    所以那 13 页被**逐字节**复制进 `tools/pc_contract_docs/`（带 `.gitattributes` 的 `* -text`），
    引用也改指向副本 —— 下面是"字节被改过就红"的钉子（改了要先核对上游、再来改这里）。
    """

    #: 契约页的**字节数**（跨机器/行尾都不会变；`gitattributes` 标了 `-text`）。
    CONTRACT_PAGE_SIZES = {
        "Entity.md": 37788,
        "EntityPickup.md": 6651,
        "EntityPlayer.md": 92938,
        "Game.md": 28363,
        "GridEntity.md": 8270,
        "Input.md": 5525,
        "Isaac.md": 31975,
        "ItemConfig_Item.md": 9616,
        "Level.md": 21972,
        "Options.md": 5783,
        "Room.md": 48849,
        "Seeds.md": 7079,
        "Sprite.md": 19065,
    }

    def test_contract_pages_are_tracked_and_unchanged(self):
        for name, size in self.CONTRACT_PAGE_SIZES.items():
            with self.subTest(page=name):
                page = ROOT / "tools" / "pc_contract_docs" / name
                self.assertTrue(page.is_file(), f"缺契约页 {name}")
                self.assertEqual(page.stat().st_size, size,
                                 f"{name} 的字节数变了 —— 契约页被改动过，先核对上游再改这里")

    @classmethod
    def setUpClass(cls):
        cls.entries = deviation_entries(DEVIATIONS.read_text(encoding="utf-8"))

    def test_every_entry_states_the_pc_contract(self):
        marker = "PC 契约："
        missing = [f"0x{identifier:08X}" for identifier, _, text in self.entries
                   if marker not in text]
        self.assertEqual(missing, [],
                         f"这些偏离没有写'{marker}'：{missing}。\n"
                         "先读 `tools/pc_contract_docs/` 里那一页（PC 文档快照的逐字节副本），把原文与行号抄进来；\n"
                         "文档里确实没有这一条就写'PC 契约：文档里没有 …'（也要写明是什么）。")

    def test_citations_really_point_at_the_doc_text(self):
        """★ 关键：**回头核对**引用 —— 页要在、行要在、片段要真的在那一行里。"""
        pattern = re.compile(r'([^\s「」]+?):(\d+)(?:\s*「([^」]*)」)?')
        checked = 0
        for identifier, _, text in self.entries:
            match = re.search(r'PC 契约：(.*?)(?:"|$)', text, re.S)
            self.assertIsNotNone(match, f"0x{identifier:08X} 的'PC 契约：'后面是空的")
            body = match.group(1).strip()
            if body.startswith("文档里没有"):
                self.assertGreater(len(body), len("文档里没有"),
                                   f"0x{identifier:08X} 写了'文档里没有'但没说是什么")
                continue
            parsed = pattern.match(body)
            self.assertIsNotNone(parsed, f"0x{identifier:08X} 的契约引用格式不对：{body!r}")
            path_text, line_text, quote = parsed.groups()
            page = ROOT / path_text
            with self.subTest(entry=f"0x{identifier:08X}"):
                self.assertTrue(page.is_file(), f"{path_text} 不存在")
                lines = page.read_text(encoding="utf-8").splitlines()
                index = int(line_text)
                self.assertLessEqual(index, len(lines), f"{path_text} 没有第 {index} 行")
                line = lines[index - 1]
                if quote:
                    self.assertIn(quote, line,
                                  f"{path_text}:{index} 里没有「{quote}」—— 引用与文档对不上")
                checked += 1
        self.assertGreater(checked, 0, "一条带文档引用的契约都没有？先补起来")


if __name__ == "__main__":
    unittest.main()
