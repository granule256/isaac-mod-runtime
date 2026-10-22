"""门禁：`tools/chain_owner_triage.py`（把"同名方法多 owner"那一档按**接收者类型**分诊）。

## 这条门禁要拦住什么

批次 162 的由来：缺口报告里 ①b 那一档（"同名方法多 owner、无法凭名字定类型"）原先**只能报出来**，
没人能回答"那到底是不是缺口" —— 于是 `Update` / `Render` / `Get` 这类通用名字长期挂在缺口的
候选里，排期时既不敢做也不敢划掉。分诊器把这些行按**接收者类型**判成三种结论，
本条门禁钉五件事：

1. **不猜**：类型只能从"全局表 / 构造式全局调用 / `<已知类型的根> + 一串方法调用>`"这三种来源推；
   推不出来的一律是 `manual`，**绝不许**退化成"候选里挑一个"。
2. **结论必须有证据**：`gap` / `not_a_gap` 的每一条都要有点名到**文件:行号**的证据；
   没有证据的结论等于没分诊。
3. **数字写死**：三种结论的条数被钉住 —— 分诊面变大/变小都要人工过一遍
   （与 `test_api_catalog` 的接口账本、`test_api_deviation` 的形状条数是同一套记账方式）。
4. **三种赋值形状都要真的被扫到，而且一条都不许跨行**（批次 179 补）：
   `local x = …` / `表.字段 = …` / `X = …`。踩过的两个坑都钉在这里 ——
   ① `LOCAL_RE` 原来用 `.{0,300}` + `re.S`，**贪婪跨行**会把紧跟着的几条 `local` 一并吞掉，
   于是后面那几条定义被静默漏掉（实测 `local hudBBSprite = Sprite()` 就一直没被定型）；
   ② `FIELD_RE` 原来用 `\\s*` 做分隔符，`\\s` **含换行**，会把"上一行句末的 `.` + 下一行的 `X =`"
   拼成一次假的字段赋值（实测 `main.lua` 第 1 行以 `one.` 收尾、第 2 行是 `EID = RegisterMod(…)`）。
5. **第五种来源（LuaLS 注解）的区间与索引口径**（批次 186 补）—— 它是唯一**作用域敏感**的来源，
   踩过的坑都钉在这里：
   ① 注解必须**按"调用点落在哪个函数体内"取**，不许像前四种来源那样"按变量名全文件汇总"；
   ② 索引键必须是 `(接收者, 方法名)`，不是光接收者 —— 否则 `entity:GetSprite` 会把
   `eid_grid_descriptions.lua` 里**另一个函数**的 `@param entity GridEntity` 吃进来，
   定出 `Entity/GridEntity` 两个类型、凭 `GridEntity:GetSprite` 凭空报一条**假缺口**；
   ③ **联合类型不采用**：取第一个词会让真实缺口静默消失，取并集会把"可能"报成"就是"，
   两条路都是替模组做主（而选择直接决定结论）⇒ 一律退回待人工；
   ④ 块配不平的文件（`lua_function_spans` 第二个返回值非 0）**整份不产出结论**。
"""

import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "chain_owner_triage.py"

#: PC 契约签名（`#### ReturnType Name ( … )`）的条数下限 —— 返回类型表是分诊器的全部依据，
#: 它要是被解析坏了（正则改错、目录搬走），分诊会静默退化成"全是 manual"。
MINIMUM_SIGNATURES = 800

#: 默认模组（EID）上的分诊结果 —— 改分诊口径、改契约页解析、或模组换了版本，这三个数字都会动。
#: 2026-09-27（批次 162）实测：25 条里 **6 条不是缺口、0 条真缺口、19 条待人工**。
#: 2026-09-28（批次 179）实测：**12 条不是缺口、0 条真缺口、13 条待人工** ——
#: 补上"构造式全局调用真的实现 + 第三条赋值形状 + `RegisterMod`"之后，6 条假缺口被剔掉
#: （`ArrowSprite:Update` / `CursorSprite:Render` / `hudBBSprite:Render` / `room:GetGridIndex` /
#: `EID:AddCallback` / `EID:RemoveCallback`）。
#: 2026-09-28（批次 186）实测：**15 条不是缺口、0 条真缺口、10 条待人工** ——
#: 加上第五种来源（LuaLS 注解）之后，3 条定案：`entity:GetSprite`（原来卡在"按变量名汇总"，
#: 反而被 `GridEntity:GetSprite` 带出一条假缺口）、`sprite:Render`、`spriteObj:Render`。
#: 2026-09-29（批次 197）实测：**18 条不是缺口、0 条真缺口、7 条待人工** —— 本批加了两档来源：
#: ① **第六种来源**：模组自己函数的 `---@return`（`mod_function_return_types()`）⇒
#:    `entityPlayer:GetName` 定案（来自 `local _, entityPlayer = EID:PlayersHaveCharacter(id, false)`，
#:    第 2 个返回值声明为 `EntityPlayer?`）。
#: ② **循环变量**：`for _, x in ipairs(<表达式>)` ⇒ 元素类型查**新加的"数组元素类型表"**
#:    （`load_contract_array_element_types()` —— 契约把数组写成 `X[]`，而原签名正则碰到 `[]` 匹配失败，
#:    所以 `Isaac.FindByType` 以前根本查不到返回类型）⇒ `crane:GetSprite`、`pickup:GetSprite` 定案。
#: ★ 同两条来源**没能**定案的：
#:    · `bagPlayer:GetSprite` —— `bagPlayer` 确实被定成 `EntityPlayer`，但它**不在 `GetSprite` 的候选 owner 里**
#:      （契约把 `GetSprite` 记在 `Entity` 名下 ⇒ 候选是 `Entity/GridEntity/GridEntityRock`）
#:      ⇒ 按"类型必须在该行的候选 owner 里"这条既有口径被挡回待人工。**刻意保守，不是漏做**。
#:    · `rooms:Get` / `lastRoomEntities:Get` —— 被遍历/被链的类型在契约里写成**容器名**
#:      （`RoomDescriptor List`），两张表都没有它 ⇒ 推不出。
#:    · `player:GetSprite` / `spriteObj:Update` —— 回调/匿名函数形参**作者没写注解**（没写的没法收）。
#: 2026-09-29（批次 202）实测：**18 条不是缺口、0 条真缺口、6 条待人工** —— 本批给"调用点扫描"
#: 加了 **Lua 注释剥离**（`gap.lua_source()`）⇒ 原来那条第 25 条 `EntityPlayer:GetName` **整条消失**：
#: 它唯一的"调用点"是 `eid_api.lua:1004` 的一句文档注释
#: （`---This is for modded characters, whose name is best found by doing EntityPlayer:GetName()`），
#: 不是代码。真调用（`entityPlayer:GetName` / `player:GetName`）本来就在，**结论一条都没变**。
#: ★ 注解那两路（`@param` / `@return`）**必须读原文、不许剥**（注解本身就是注释）——
#: 一起剥会把 `entityPlayer:GetName` / `sprite:Render` / `spriteObj:Render` 三条从"不是缺口"
#: 打回"待人工"（18/7 → 15/9）。这条踩过，见 `gap.lua_source_raw()` 的 docstring。
EXPECTED_NOT_A_GAP = 18
EXPECTED_GAP = 0
EXPECTED_MANUAL = 6


def load_tool():
    spec = importlib.util.spec_from_file_location("chain_owner_triage", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ChainOwnerTriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool()

    def _resolve(self, source: str) -> dict:
        """把一段 Lua 写进临时"模组"再定型 —— 复用被测代码自己的扫法。"""
        with tempfile.TemporaryDirectory(prefix="isaac-chain-triage-") as directory:
            mod = pathlib.Path(directory)
            (mod / "main.lua").write_text(source, encoding="utf-8")
            return self.tool.resolve_variable_types(mod)

    def test_contract_signatures_are_parsed(self):
        """契约页必须真的解析出返回类型表 —— 否则分诊器会静默退化。"""
        table = self.tool.load_contract_return_types()
        self.assertGreater(len(table), MINIMUM_SIGNATURES,
                           f"契约签名只解析出 {len(table)} 条（下限 {MINIMUM_SIGNATURES}）"
                           " —— 是不是 PC 契约页目录变了、或签名行格式变了？")
        self.assertEqual(table.get(("EntityPlayer", "GetPlayerType")), "PlayerType",
                         "抽查：`EntityPlayer:GetPlayerType()` 的返回类型应是 PlayerType（契约页签名行）")

    def test_receiver_types_come_from_locals_and_never_from_guessing(self):
        """正例：`local x = Isaac.GetPlayer(0)` 之后 `x:GetPlayerType()` ⇒ 接收者是 EntityPlayer。

        反例：根是陌生标识符（函数参数那种）⇒ 一律不算，**不许**退化成"候选里挑一个"。
        """
        resolved = self._resolve(
            "local player = Isaac.GetPlayer(0)\n"
            "local kind = player:GetPlayerType()\n"
            "local mystery = someCallbackArgument\n"
            "local other = mystery:GetPlayerType()\n")
        self.assertIn("EntityPlayer", resolved.get("player", {}),
                      "`local player = Isaac.GetPlayer(0)` 应当定出 EntityPlayer")
        self.assertNotIn("mystery", resolved,
                         "根是陌生标识符时**不许**定出类型（那就变成「猜」了）")

    def test_constructor_global_calls_are_typed(self):
        """规则②：`local s = Sprite()` ⇒ `s` 是 Sprite（**不是**"要跟一个方法调用"）。

        规则② 曾只写在文档里（`GLOBAL_CALL_TYPES` 是个从没被读过的死常量），批次 179 才实现。
        """
        resolved = self._resolve(
            "local s = Sprite()\n"
            "local g = Game()\n"
            "local eid = RegisterMod(\"x\", 1)\n")
        self.assertIn("Sprite", resolved.get("s", {}),
                      "`local s = Sprite()` 应当定出 Sprite（构造式全局调用：返回值类型就是函数名）")
        self.assertIn("Game", resolved.get("g", {}), "`local g = Game()` 应当定出 Game")
        self.assertIn("Mod", resolved.get("eid", {}),
                      "`RegisterMod(…)` 返回 Mod（PC 契约签名行），`EID:AddCallback` 靠它才是 Mod:AddCallback")

    def test_all_three_assignment_shapes_are_scanned(self):
        """三种赋值形状都要被扫到：`local x = …` / `表.字段 = …` / `X = …`。"""
        resolved = self._resolve(
            "local a = Sprite()\n"
            "EID = RegisterMod(\"x\", 1)\n"
            "EID.c = Sprite()\n")
        self.assertIn("Sprite", resolved.get("a", {}), "`local a = Sprite()` 要扫到")
        self.assertIn("Mod", resolved.get("EID", {}), "`EID = RegisterMod(…)`（裸全局赋值）要扫到")
        self.assertIn("Sprite", resolved.get("c", {}),
                      "`EID.c = Sprite()`（表字段）要扫到 —— 绑定口径 = 取最后一个字段名")

    def test_consecutive_local_assignments_are_never_swallowed(self):
        """★ 回归：`LOCAL_RE` 的窗口**不许跨行**，相邻的几条 `local` 一条都不许被吞掉。

        老写法 `.{0,300}` + `re.S` 是贪婪跨行的：第一条 `local` 的 300 字窗口会把后面几条
        （以及它们的定义）一起吃掉，而 `finditer` 从吞掉之后继续扫 ⇒ **静默漏定义**。
        """
        text = "local a = Sprite()\nlocal b = Sprite()\nlocal c = Sprite()\n"
        found = [match.group(1) for match in self.tool.LOCAL_RE.finditer(text)]
        self.assertEqual(["a", "b", "c"], found,
                         "相邻的 `local` 赋值必须各成一条 —— 窗口跨行就会把后面几条吞掉")
        resolved = self._resolve(text)
        for name in ("a", "b", "c"):
            with self.subTest(name=name):
                self.assertIn("Sprite", resolved.get(name, {}), f"`{name}` 被吞掉了（老 bug 复发）")

    def test_assignment_patterns_never_match_across_lines(self):
        """★ 回归：`字段 = <表达式>` 这一条**不许跨行匹配**（`\\s` 含换行会拼出假赋值）。"""
        text = "one.\nX = Sprite()\n"
        matches = [match.group(0) for match in self.tool.FIELD_RE.finditer(text)]
        self.assertEqual([], matches,
                         "`表.字段 =` 这一条跨行匹配了 —— `\\s*` 含换行，会把上一行句末的 `.` "
                         "和下一行的 `X =` 拼成一次假的字段赋值")
        bare = [(match.group(1), match.group(2))
                for match in self.tool.GLOBAL_ASSIGN_RE.finditer(text)]
        self.assertEqual([("X", "Sprite()")], bare, "裸全局赋值那一支应当认出行首的 `X = Sprite()`")

    def test_member_access_without_a_call_is_not_typed(self):
        """反例：`Isaac.PlayerType` 是**取常量**不是调方法 ⇒ 不许把根的类型当成变量的类型。"""
        resolved = self._resolve(
            "local kind = Isaac.PlayerType\n"
            "local t = someTable.field\n"
            "local u = mysteryFn()\n")
        self.assertNotIn("kind", resolved,
                         "`Isaac.PlayerType` 是常量访问 ⇒ 类型未知，不许写成 Isaac")
        self.assertNotIn("t", resolved, "`someTable.field` 的根不认识 ⇒ 不许定型")
        self.assertNotIn("u", resolved, "`mysteryFn()` 是陌生全局函数 ⇒ 不许定型")

    def test_lua_function_spans_pair_up_and_report_unbalanced_files(self):
        """第五种来源的地基：`function … end` 的块配对必须准，配不平时**必须报告**。

        为什么这件事要单独钉：注解是按"调用点落在哪个函数体内"取的，位置算错 = 证据指向别的函数。
        所以宁可用一个**逐字符状态机**（跳过注释/长字符串/普通字符串再数关键字），
        并且把"还剩几个结构词没配对"当返回值交出来 —— 调用方看到非 0 就**整份文件不产出结论**。
        """
        paired, unbalanced = self.tool.lua_function_spans(
            "function a()\n"
            "  if x then y() end\n"
            "end\n"
            "function b()\n"
            "  for i = 1, 2 do z() end\n"
            "end\n")
        self.assertEqual(0, unbalanced, "配平的文件不该报「没配平」")
        self.assertEqual([(1, 3), (4, 6)], paired, "两个函数的跨度应当是 (1,3) 与 (4,6)")

        # 字符串与注释里的 `end` / `function` 不许干扰计数（否则位置全错）
        paired, unbalanced = self.tool.lua_function_spans(
            'function a()\n'
            '  local s = "end function if do"\n'
            '  -- end\n'
            '  local t = [[ end ]]\n'
            'end\n')
        self.assertEqual(0, unbalanced, "字符串/注释里的结构词被算进去了")
        self.assertEqual([(1, 5)], paired, "字面量里的 `end` 不该参与配对")

        _, unbalanced = self.tool.lua_function_spans("function a()\n  if x then\n")
        self.assertNotEqual(0, unbalanced, "明显没配平的文件必须报出来（否则位置不可信的注解会被用）")

    def test_annotation_param_types_are_scoped_to_the_call_site(self):
        """★ 第五种来源的核心口径：注解**按调用点所在的函数**取，不按变量名全文件汇总。

        这里直接构造"同名变量在两个函数里是两种东西"的经典情形（EID 上真实存在）：
        同一个名字既做形参（有注解）又做局部变量（另有来历），后者**不许**借用前者的注解。
        """
        source = (
            "---@param item Entity\n"
            "function m:useAsParam(item)\n"
            "  return item:GetType()\n"
            "end\n"
            "\n"
            "function m:useAsLocal()\n"
            "  local item = m:makeSomething()\n"
            "  return item:GetType()\n"
            "end\n")
        with tempfile.TemporaryDirectory(prefix="isaac-anno-") as directory:
            mod = pathlib.Path(directory)
            (mod / "main.lua").write_text(source, encoding="utf-8")
            found = self.tool.resolve_annotation_types(mod)
        self.assertEqual({"Entity"}, set(found.get(("item", "GetType"), ({}, {}))[0]),
                         "形参那一处的 `@param item Entity` 应当被收下")
        # 关键反例：局部变量那一处**不许**被同一条注解覆盖 —— 若实现里按变量名汇总，这里就会误绑。
        # 判据是"证据里只出现形参那个函数的行号"。
        places = found[("item", "GetType")][0]["Entity"]
        self.assertEqual(1, len(places), f"只应有形参那一处被收下，实际 {places}")
        self.assertIn("main.lua:3", places[0], f"证据应指向形参所在函数的调用行，实际 {places[0]}")

    def test_annotation_is_indexed_by_receiver_and_method(self):
        """★ 索引键必须是 `(接收者, 方法名)`：同名接收者**在别的函数里**的注解不许搬过来。

        这是批次 186 实测踩到的那条捷径的回归：`entity` 在 A 函数上是 `Entity`，
        在 B 函数上是 `GridEntity`。若按变量名汇总，`entity:GetSprite` 会被定出
        `Entity/GridEntity` 两个类型 ⇒ 因为 `GridEntity:GetSprite` 我们没实现，
        **凭空报出一条假缺口**。
        """
        source = (
            "---@param entity Entity\n"
            "function m:describe(entity)\n"
            "  return entity:GetSprite()\n"
            "end\n"
            "\n"
            "---@param entity GridEntity\n"
            "function m:gridDescribe(entity)\n"
            "  return entity:GetType()\n"
            "end\n")
        with tempfile.TemporaryDirectory(prefix="isaac-anno-") as directory:
            mod = pathlib.Path(directory)
            (mod / "main.lua").write_text(source, encoding="utf-8")
            found = self.tool.resolve_annotation_types(mod)
        singles, _ = found.get(("entity", "GetSprite"), ({}, {}))
        self.assertEqual({"Entity"}, set(singles),
                         "`entity:GetSprite` 只该收下它自己那个函数的注解（Entity），"
                         "不许把另一个函数的 `GridEntity` 搬过来")
        singles, _ = found.get(("entity", "GetType"), ({}, {}))
        self.assertEqual({"GridEntity"}, set(singles),
                         "`entity:GetType` 反过来只该收下 GridEntity 那一处")

    def test_mod_function_return_types_are_used_positionally(self):
        """★ 第六种来源（批次 197）：模组自己函数的 `---@return` —— **必须按位置取**。

        由来：`local hasBag, bagPlayer = EID:PlayersHaveCollectible(710)` 的右边是**模组自己**的
        函数，不在 PC 契约页；作者写了 `---@return boolean, EntityPlayer?, integer?`
        ⇒ 第 2 个变量才是 `EntityPlayer`。若只收"类型集合"而不留位置，就会把 `boolean`
        当对象类型去用 —— 所以这条判据专门钉"位置"。
        """
        source = (
            "---@return boolean, EntityPlayer?, integer?\n"
            "function EID:PlayersHaveCollectible(id)\n"
            "  return true, player, i\n"
            "end\n"
            "\n"
            "local hasBag, bagPlayer = EID:PlayersHaveCollectible(710)\n"
            "bagPlayer:GetSprite()\n")
        with tempfile.TemporaryDirectory(prefix="isaac-ret-") as directory:
            mod = pathlib.Path(directory)
            (mod / "main.lua").write_text(source, encoding="utf-8")
            found = self.tool.resolve_variable_types(mod)
        self.assertIn("EntityPlayer", found.get("bagPlayer", {}),
                      "第 2 个变量该拿到第 2 个返回类型 `EntityPlayer`（`?` 要去掉）")
        self.assertNotIn("EntityPlayer", found.get("hasBag", {}),
                         "第 1 个变量是 `boolean`，不该被当成 `EntityPlayer`")

    def test_mod_function_return_types_skip_unbalanced_files(self):
        """块配不平的文件整份不下结论（与 `@param` 那条同一道闸）。"""
        source = (
            "---@return EntityPlayer?\n"
            "function EID:Foo()\n"
            "  do\n"                       # 多开一个块 ⇒ 配不平
            "  return player\n"
            "end\n"
            "\n"
            "local _, p = EID:Foo()\n")
        with tempfile.TemporaryDirectory(prefix="isaac-ret-unbal-") as directory:
            mod = pathlib.Path(directory)
            (mod / "main.lua").write_text(source, encoding="utf-8")
            found = self.tool.resolve_variable_types(mod)
        self.assertNotIn("EntityPlayer", found.get("p", {}),
                         "块配不平的文件不许用它里面的 `---@return` 下结论")

    def test_loop_variable_element_type_comes_from_the_array_table(self):
        """★ 循环变量（批次 197）：`for _, x in ipairs(Isaac.FindByType(…))` ⇒ `x` 是 `Entity`。

        为什么需要单开一张"数组元素类型表"：契约把数组返回类型写成
        `#### [Entity](Entity.md)[] FindByType ( … )` —— 类型与链接之间夹了个 `[]`，
        而 `SIGNATURE_RE` 要求类型后面紧跟空白 ⇒ **数组返回类型一直没被解析到**。
        不扩既有正则（免得动到那 4 种来源的口径），只给"循环变量"这一档读新表。
        """
        table = self.tool.load_contract_array_element_types()
        self.assertEqual("Entity", table.get(("Isaac", "FindByType")),
                         "`Isaac.FindByType` 的数组元素类型该是 `Entity`（契约：`[Entity](Entity.md)[]`）")
        source = (
            "for _, crane in ipairs(Isaac.FindByType(6, 16, -1, true, false)) do\n"
            "  crane:GetSprite()\n"
            "end\n")
        with tempfile.TemporaryDirectory(prefix="isaac-loop-") as directory:
            mod = pathlib.Path(directory)
            (mod / "main.lua").write_text(source, encoding="utf-8")
            found = self.tool.resolve_variable_types(mod)
        self.assertIn("Entity", found.get("crane", {}),
                      "循环变量 `crane` 该被定成元素类型 `Entity`")

    def test_loop_variable_with_a_container_name_stays_unresolved(self):
        """契约里写成**容器名**的（`RoomDescriptor List`）不猜 —— 留在待人工。"""
        source = (
            "local rooms = game:GetLevel():GetRooms()\n"
            "for _, room in ipairs(rooms) do\n"
            "  room:Get()\n"
            "end\n")
        with tempfile.TemporaryDirectory(prefix="isaac-loop-container-") as directory:
            mod = pathlib.Path(directory)
            (mod / "main.lua").write_text(source, encoding="utf-8")
            found = self.tool.resolve_variable_types(mod)
        self.assertNotIn("RoomDescriptor", found.get("room", {}),
                         "容器名（`RoomDescriptor List`）不是候选 owner ⇒ 不许当成元素类型")

    def test_union_annotations_are_declined(self):
        """★ **联合类型不采用**：取第一个词会让真实缺口静默消失，取并集会把"可能"报成"就是"。

        两条路都是替模组做主，而选择直接决定结论 ⇒ 一律退回待人工。
        """
        self.assertEqual(("", ["Entity", "GridEntity"]),
                         self.tool.annotation_types_of("Entity | GridEntity"),
                         "联合类型要拆成成员表（不产出单类型）")
        self.assertEqual(("Sprite", []), self.tool.annotation_types_of("Sprite"),
                         "普通单类型照常收下")
        self.assertEqual(("GridEntity", []),
                         self.tool.annotation_types_of(
                             "GridEntity: The grid entity to check for a description."),
                         "类型后面跟说明文字，只有首个词是类型 ⇒ 应当收成 GridEntity")
        self.assertEqual(("", []), self.tool.annotation_types_of("nil"), "`nil` 不是类型名")
        self.assertEqual(("", []), self.tool.annotation_types_of(""), "空注解不成类型")
        members = self.tool.annotation_types_of("fun(spriteObj: Sprite) | nil")[1]
        self.assertNotIn("Sprite", members,
                         "嵌套函数类型里的 `Sprite` 不是这个形参的类型，不许当成联合成员")

    def test_unbalanced_files_yield_no_annotations(self):
        """★ 块配不平的文件**整份不产出结论** —— 宁可少给一条，也不给一条位置算错的。"""
        with tempfile.TemporaryDirectory(prefix="isaac-anno-") as directory:
            mod = pathlib.Path(directory)
            (mod / "main.lua").write_text(
                "---@param entity Entity\n"
                "function m:describe(entity)\n"
                "  return entity:GetSprite()\n",      # 少了 `end` ⇒ 配不平
                encoding="utf-8")
            self.assertEqual([], self.tool.lua_function_param_types(mod / "main.lua"),
                             "配不平的文件必须返回空表（位置不可信的注解一条都不用）")
            self.assertEqual({}, self.tool.resolve_annotation_types(mod),
                             "配不平 ⇒ 这一份文件一条注解都不该进索引")

    def test_default_mod_triage_counts_are_pinned(self):
        """默认模组（EID）上的三种结论条数写死；模组不在时跳过（`dist/` 里的发布件不是人人都有）。"""
        mod = ROOT / self.tool.gap.DEFAULT_MOD
        if not mod.is_dir():
            self.skipTest(f"默认模组目录不在：{mod}")
        result = self.tool.triage(mod)
        counts = result["by_verdict"]
        self.assertEqual(counts.get("not_a_gap", 0), EXPECTED_NOT_A_GAP,
                         "「不是缺口」的条数变了 —— 请复核分诊结果并把 `EXPECTED_NOT_A_GAP` 同步")
        self.assertEqual(counts.get("gap", 0), EXPECTED_GAP,
                         "「真缺口」的条数变了 —— 请复核分诊结果并把 `EXPECTED_GAP` 同步")
        self.assertEqual(counts.get("manual", 0), EXPECTED_MANUAL,
                         "「待人工」的条数变了 —— 请复核分诊结果并把 `EXPECTED_MANUAL` 同步")
        self.assertEqual(result["rows"], sum(counts.values()),
                         "三种结论的条数必须正好等于这一档的行数（不许有行落在三种之外）")
        for row in result["triaged"]:
            with self.subTest(api=row["called_as"]):
                self.assertIn(row["verdict"], {"gap", "not_a_gap", "manual"})
                if row["verdict"] != "manual":
                    self.assertTrue(row["evidence"],
                                    f"{row['called_as']} 下了结论却没有证据 —— 结论必须能复核")
                    self.assertTrue(row["resolved_owners"],
                                    f"{row['called_as']} 下了结论却没有定出任何接收者")


if __name__ == "__main__":
    unittest.main()
