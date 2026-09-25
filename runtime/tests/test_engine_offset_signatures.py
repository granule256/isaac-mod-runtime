"""门禁：`runtime_constants.hpp` 的每个偏移常量都必须在"引擎符号签名表"里登记，且用对了。

## 为什么要有它

2026-09-17 暴露的是一整类风险：**我们按自己的假设去解释引擎的 ABI / 数据**，而这些假设**没有机器核对**。

* `EntityPlayer:HasCollectible` —— 引擎（与 PC）都是 `(eCollectibleType, bool)`，我们只收一个参数，
  EID 传第二个参数时**每次都报错**；
* 引擎返回的块"是不是分配起点" —— 我们假设是，直接 `delete[]`，踩坏游戏堆（续三十七）。

这两件事**都能静态查清**：游戏镜像里每个函数都自带参数表。本门禁把三件事钉住：

1. **登记完整**：`runtime_constants.hpp` 里出现的每个 `k…Offset` 常量，都必须在
   `tools/engine_symbol_signatures.json` 里有条目（新加偏移而不登记 ⇒ 判红）；
2. **证据一致**（仓库里有游戏镜像时）：表里记的 `mangled` 必须**就是那个偏移上的符号**，
   参数个数必须与 demangle 结果一致（偏移写错一位、或镜像换版本 ⇒ 判红）；
3. **用对了**（能自动识别出调用点的那些）：我们传的实参个数必须是"引擎参数个数"或"它 + 1
   （成员函数的隐式 `this`）"，其余 ⇒ 判红。这条正是能拦住 `HasCollectible` 那类错的那一条。

同时**报一个进度数**（不判红）：表里 193 个"结构体字段偏移"目前只有注释证据，
其中有多少条已经进了 `tools/layout_tables/`（二期"布局表铺开"的欠账）。
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
TABLE = ROOT / "tools" / "engine_symbol_signatures.json"
TOOL = ROOT / "tools" / "engine_offset_abi_report.py"
NRO = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0/1/.nro/Repentance.nro"
)
LAYOUT_DIR = ROOT / "tools" / "layout_tables"
CONST_RE = re.compile(r"^inline constexpr uintptr_t (k[A-Za-z0-9]+Offset) = (0x[0-9A-Fa-f]+);", re.M)


def load_table() -> list[dict]:
    return json.loads(TABLE.read_text(encoding="utf-8"))


class EngineOffsetSignatureTests(unittest.TestCase):
    def test_every_offset_constant_is_registered(self):
        constants = CONST_RE.findall(CONSTANTS.read_text(encoding="utf-8"))
        self.assertTrue(constants, "没解析到任何偏移常量（runtime_constants.hpp 格式变了？）")
        registered = {entry["constant"] for entry in load_table()}
        missing = sorted(name for name, _ in constants if name not in registered)
        self.assertFalse(
            missing,
            "这些偏移常量没有登记进 tools/engine_symbol_signatures.json（先跑 "
            "tools/gen_engine_symbol_signatures.py）：" + repr(missing[:12]),
        )

    def test_table_matches_the_game_image_when_available(self):
        if not NRO.exists():
            self.skipTest("仓库里没有游戏镜像（公开仓库不带游戏资源）")
        sys.path.insert(0, str(ROOT / "tools"))
        from nro_symbols import parse_dynamic_symbols  # noqa: PLC0415

        _soname, symbols = parse_dynamic_symbols(NRO.read_bytes())
        by_offset: dict[int, str] = {}
        for name, symbol in symbols.items():
            if symbol.file_offset is not None:
                by_offset.setdefault(symbol.file_offset, name)
        # 2026-09-17：生成器加了"假阳性过滤器" —— 动态表的 `st_value` 对不少条目是 0 或很小的值，
        # 于是**字段偏移会撞上跟我们毫无关系的符号**（实测 4 条：`rapidxml::…parse_cdata`、
        # `nndetailRoGetRoDataStart`、`nndetailRoGetRoDataEnd`、`_fini`）。拿它们去比参数表只会把
        # "ABI 体检"带偏，所以表里对这四个故意留空。判据相应改成：
        # **除这四个以外，表里记的 mangled 必须与镜像那个偏移上的符号逐字相同。**
        known_rejected = {
            "kEntityPlayerDamageOffset",
            "kEntityListLiveCapacityOffset",
            "kItemConfigPlayerFormBeginOffset",
            "kEntityFlyingLayerOffset",
            # 贴图桥（2026-09-21）：三个 zlib C 符号（inflateInit2_/inflate/inflateEnd）不是引擎
            # 命名空间符号，动态表按名字解析会落到 C 名而非 mangled，故意留空。
            "kZlibInflateInit2FileOffset",
            "kZlibInflateFileOffset",
            "kZlibInflateEndFileOffset",
        }
        rejected_seen = set()
        for entry in load_table():
            raw = by_offset.get(int(entry["offset"], 16))
            if entry["constant"] in known_rejected:
                rejected_seen.add(entry["constant"])
                self.assertIsNone(entry["mangled"],
                                  f"{entry['constant']} 应当被假阳性过滤器留空（镜像那个偏移上是 {raw}）")
                continue
            self.assertEqual(
                entry["mangled"], raw,
                f"{entry['constant']} @ {entry['offset']}：表里记的是 {entry['mangled']}，"
                f"镜像里那个偏移上是 {raw} —— 偏移或表都过期了",
            )
        self.assertEqual(rejected_seen, known_rejected,
                         "被过滤器拒掉的常量集合变了：要么是镜像换了版本，要么过滤器被改动了")

    def test_abi_report_coverage_does_not_regress(self):
        """体检必须真的在体检：覆盖率（能读出"我们声明的参数表"的函数偏移数）不许掉回去。

        2026-09-17 之前这份报告只覆盖 **3/92**，那句"参数个数不符 0"其实是"没比过"。
        2026-09-17 批次 1 改成按"我们声明的函数指针类型 vs 引擎签名"比，覆盖率 16/91；
        同一天后半段把 Font/Sprite 两族的绑定记录字段也改成声明类型（见
        `runtime/tests/test_binding_declared_types.py`），体检工具多了一条"绑定表行"的路
        —— 覆盖率 41/91（两族 36 条里 34 条在签名表里，另两条是 libc++ 的 PLT 桩、没有引擎符号）；
        再往后加了"单方法绑定那条链"（常量 → 校验助手 → 局部变量 → 发布函数 → 全局槽 → 取址助手
        → 调用点声明的类型，见 `single_binding_signature`），Input/Music/RNG 三族 8 条接上
        —— 覆盖率 49/91；再补上"地址交给另一个函数"那一跳（`declared_type_via_callee`）
        —— 覆盖率 51/91；再把 `GameFileReader::Bindings` 这一族的字段改成声明类型
        （形态 C′：`VerifyGameEntry(module, kXxxOffset, …, &verified.字段)`）—— 覆盖率 59/91；
        2026-09-17 第二批修掉形态 A 里"转型操作数切片少了闭括号"这个 bug（"局部变量"那条支路
        此前从未生效），并让局部变量的初始化表达式可以是"含常量的算式"、
        再新增形态 F（常量直接当实参交给助手 → 形参 → 派生地址变量 → 转型，见
        `declared_type_via_argument_helper`）—— 覆盖率 65/91；
        同一天再补形态 E（常量在取址助手体内、助手结果经调用点交给"按签名调"的那一层，
        见 `declared_type_via_address_helper`）并**在源码侧把 `ItemConfig` 的 `kind` 分派拆成
        三条互斥路径**（每个常量只对应一个签名）—— 覆盖率 **71/91**。
        这条钉住它不许回退，并同时要求**没有浮点/整数不匹配**（`Present` 转发桩那一类的形状）。
        """
        import importlib.util
        import tempfile
        spec = importlib.util.spec_from_file_location("abi_report", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        functions = [entry for entry in load_table() if entry["kind"] == "function"]
        resolved = [e for e in functions if module.declared_signature(e["constant"]) is not None]
        self.assertGreaterEqual(len(resolved), 71,
                                f"ABI 体检覆盖率掉了：{len(resolved)}/{len(functions)}")
        verdicts = [module.classify(entry, None if module.declared_signature(entry["constant"]) is None
                                    else module.declared_signature(entry["constant"])[1])
                    for entry in functions]
        floats = [row for row in verdicts if row["verdict"] == "float-mismatch"]
        self.assertEqual(floats, [], "有引擎调用把浮点参数当整数传（v 寄存器没准备）")

    def test_itemconfig_isavailable_has_one_signature_per_constant(self):
        """`ItemConfig` 的三个 `IsAvailable`：**每个偏移常量只对应一个签名**（不许再按 `kind` 选）。

        这三条原来挤在一个 `CallItemConfigIsAvailable(method, entry, kind)` 里、由运行时的 `kind`
        在两条签名之间选（`if (kind == 0)` 走带 flags 的三参数、否则走无参）——
        静态上分不出"哪个常量配哪个签名"，所以体检一直是"没比过"。
        源码侧拆成 `CallItemIsAvailable` / `CallCardIsAvailable` / `CallPillEffectIsAvailable`
        之后才读得到，这里逐条钉住（**谁再把它们合回去，这条就红**）。

        `Item` 那一条判"我们多给参数"是**有意的**：PC 契约是 `IsAvailable(long flags, uint)`，
        而镜像里这个偏移上的符号是 `Item::IsAvailableEx(unsigned int)`（一个 `uint`）——
        我们按 PC 契约传 `x1 = flags`（位置一致），多传的 `x2` 引擎不读（反汇编四个分支都没用到）。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("abi_report", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = {
            "kItemConfigItemIsAvailableOffset": 3,        # this + flags + 0
            "kItemConfigCardIsAvailableOffset": 1,        # 只有 this
            "kItemConfigPillEffectIsAvailableOffset": 1,  # 只有 this
        }
        for constant, count in expected.items():
            with self.subTest(constant=constant):
                signature = module.declared_signature(constant)
                self.assertIsNotNone(
                    signature,
                    f"{constant} 又读不出签名了：`ItemConfig` 的 kind 分派是不是被合回去了？")
                self.assertEqual(len(signature[1]), count, f"{constant} 的参数个数不对：{signature}")

    def test_helper_local_variable_chain_is_actually_checked(self):
        """`isaac_api.cpp` 一族（取址助手 + 局部变量 + 转型）必须**真的走上那条链**。

        2026-09-17 实测发现形态 A 里有个静默 bug：转型操作数的切片 `text[start:end]` **少了闭括号**，
        于是"操作数是某个局部变量"那条支路**从来没生效过**（覆盖率数字靠别的支路凑着，看不出来）。
        修好之后这批条目才有判决，所以这里逐条钉住 —— 链再断掉就直接红。

        同时钉住两条**类型不同**的函数（`HasCollectible` 是 `(eCollectibleType, bool)`、
        `AddCollectible` 是 5 个参数）：它们共用同一个局部变量名 `method`，
        证明"按所在函数体绑定局部变量"这一跳没有串味。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("abi_report", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = {
            # 常量 → 声明的参数个数（含 `this`）
            "kEntityPlayerHasCollectibleOffset": 3,
            "kEntityPlayerAddCollectibleOffset": 6,
            "kManagerGetLanguageCodeOffset": 1,
            "kItemConfigGetCollectibleOffset": 2,
        }
        for constant, count in expected.items():
            with self.subTest(constant=constant):
                signature = module.declared_signature(constant)
                self.assertIsNotNone(signature, f"{constant} 的「取址助手 + 局部变量」链断了")
                self.assertEqual(len(signature[1]), count,
                                 f"{constant} 读出来的参数个数不对：{signature}")

    def test_constant_as_argument_helper_chain_is_actually_checked(self):
        """`kGameSpecialSeed*Curses` 两条：常量**直接当实参**交给访问器助手（形态 F）。

        它们的写法是 `CallGameCurseAccessor(kGameSpecialSeedPermanentCursesOffset, …)` ——
        常量既不在任何转型的操作数里、也不在取址助手里，只有跟着
        "实参 → 形参 → `const uintptr_t target = base + offset;` → 转型"才读得到。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("abi_report", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for constant in ("kGameSpecialSeedPermanentCursesOffset",
                         "kGameSpecialSeedBannedCursesOffset"):
            with self.subTest(constant=constant):
                signature = module.declared_signature(constant)
                self.assertIsNotNone(signature, f"{constant} 的「常量当实参」链断了")
                self.assertEqual(len(signature[1]), 1,
                                 f"{constant} 应当声明成只带 this 的访问器：{signature}")

    def test_single_binding_chain_is_actually_checked(self):
        """没有绑定记录的那些入口（Input/Music/RNG）必须**真的走上那条链**，不许静默掉回"没比过"。

        它们没有 `LuaFontBindings` 那样的记录可读，声明的类型只能顺着
        "常量 → 校验助手 → 局部变量 → 发布函数 → 全局槽 → 取址助手 → 调用点"这条链找
        （`tools/engine_offset_abi_report.py` 的 `single_binding_signature`）。
        这条用例钉住这条链**接上了且判决一致**：链一断，覆盖率数字可能靠别的条目看不出来，
        但这里会直接红。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("abi_report", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # ★ 2026-09-20（批次 107）：`kManagerIsActionTriggeredOffset` **从这份名单里移出** ——
        # 那个引擎入口（`ManagerBase::IsActionTriggered`）在真机上**永远答假**（同一条控制器、
        # 同一个动作，`IsActionPressed` 通、它永远假），于是 `Input.IsActionTriggered` 改成
        # "问按住 + 自己算边沿"，**不再有调用点** ⇒ 这条链按设计断开，工具会判「没比过」。
        # 它不是被静默忽略：已在 `tools/engine_abi_backlog.json` 里分诊（B 类），
        # 理由与证据写在 `api_deviation.cpp` 的 0x09010004。
        for constant in (
            "kManagerIsActionPressedOffset",
            "kManagerGetActionValueOffset",
            "kMusicGetCurrentMusicIdOffset",
            "kMusicPauseOffset",
            "kMusicResumeOffset",
            "kRngSetSeedOffset",
            "kRngNextOffset",
        ):
            with self.subTest(constant=constant):
                signature = module.declared_signature(constant)
                self.assertIsNotNone(signature, f"{constant} 的单方法绑定链断了（读数变成「没比过」）")
                row = module.classify({"constant": constant, "parameters": ["a", "b", "c"][:0]},
                                      signature[1])
                self.assertNotEqual(row["verdict"], "unknown")

    def test_arity_verdict_counts_our_implicit_this(self):
        """★ 2026-09-19：`classify` 必须把「我们的声明含 `this`、引擎签名不含」算进判据。

        事故（真机 `Data Abort`，游戏被打崩）：`Entity:TakeDamage` 的真实签名是
        `TakeDamage(float, unsigned long, EntityRef const&, int)`（4 个显式参数），
        而我们当时只声明了 3 个 —— 于是引擎按引用解引用的 `x2` 拿到的是我们当 `countdown` 传的 0
        ⇒ 空指针解引用。**工具当时报的是"一致"**：旧判据允许 `our == engine` 也算通过
        （正确判据是 `our == engine + 1`），正好把"少给一个参数"这一整类放过去了。
        所以这里用合成用例把**四个方向**都钉死（只有"少给"那个方向以前是错的）。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("abi_report", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # `classify` 会先按常量去源码里读我们声明的形参表（这是它的设计），
        # 所以合成用例要把那一步替换掉 —— 只测"个数怎么判"这段算术。
        def verdict(engine_params, our_params):
            original = module.declared_signature
            module.declared_signature = lambda constant: ("synthetic.cpp", list(our_params),
                                                          "synthetic")
            try:
                entry = {"constant": "kSyntheticOffset", "parameters": list(engine_params)}
                return module.classify(entry, ["this"])["verdict"]
            finally:
                module.declared_signature = original

        take_damage_engine = ["float", "unsigned long", "EntityRef const&", "int"]
        cases = [
            # (引擎参数, 我们声明的参数表（**含 this**）, 期望判据)
            (["unsigned int"], ["this", "code"], "ok"),
            (["unsigned int"], ["this"], "under"),   # ← 旧版本在这里判成 ok（就是 TakeDamage 的形状）
            (take_damage_engine, ["this", "float", "flags", "ref", "countdown"], "ok"),
            (take_damage_engine, ["this", "float", "ref", "countdown"], "under"),
            ([], ["this"], "ok"),
            ([], ["this", "extra"], "over"),
            # 浮点不匹配优先于个数判据（引擎走 v 寄存器、我们走 x 寄存器 ⇒ 实参根本传不到）。
            (["float"], ["this", "int"], "float-mismatch"),
        ]
        for engine_params, our_params, expected in cases:
            with self.subTest(engine=engine_params, ours=our_params):
                self.assertEqual(verdict(engine_params, our_params), expected)

    def test_entity_take_damage_declaration_matches_the_engine_signature(self):
        """真机崩溃的那两个常量：声明必须是 5 个形参（this + float + flags + 引用 + countdown）。

        `flags` 那一位是**必须有**的：引擎签名 `...EfmRKNS0_9EntityRefEi` 里的 `m`
        就是 `unsigned long`（PC 的 `DamageFlags`）。批次 064 当时判成"引擎没有这个参数"，
        后果见 `docs/问题与解决记录.md` 续六十四。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("abi_report", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for constant in ("kEntityTakeDamageOffset", "kEntityPlayerTakeDamageOffset"):
            with self.subTest(constant=constant):
                signature = module.declared_signature(constant)
                self.assertIsNotNone(signature, f"{constant} 的声明读不出来（读数变成「没比过」）")
                row = module.classify(
                    {"constant": constant,
                     "parameters": ["float", "unsigned long", "EntityRef const&", "int"]},
                    signature[1])
                self.assertEqual(row["verdict"], "ok", row["detail"])
                self.assertEqual(len(signature[1]), 5, signature[1])

    def test_abi_triage_ledger_is_well_formed(self):
        """分诊台账：每条"我们故意少给参数"都必须带理由；浮点不匹配不许登记。"""
        triage = ROOT / "tools" / "engine_abi_triage.json"
        self.assertTrue(triage.is_file(), "缺少 ABI 分诊台账")
        data = json.loads(triage.read_text(encoding="utf-8"))
        constants = {entry["constant"] for entry in load_table()}
        for name, row in data["rows"].items():
            with self.subTest(constant=name):
                self.assertIn(name, constants, "台账里的常量不在签名表里")
                self.assertTrue(row.get("why"), "每条分诊都必须写明理由")
                self.assertTrue(row.get("evidence"), "每条分诊都必须给出依据")

    def test_unknown_entries_are_triaged_in_backlog(self):
        """工具**读不出声明**的每一条，都必须在欠账台账里写明"要不要补、为什么"。

        为什么要有这条（2026-09-17）：覆盖率是个诱人的数字 —— 光看 "读不到 23 个" 会以为还欠 23 条，
        而其中大部分（只当挂点/中继目标的、全仓库没有消费者的）**根本没有"调用签名"可错**。
        反过来，台账也不许留已经覆盖的条目（那会让"欠账"永远清不掉）。
        所以两边**互相钉住**：未覆盖集合 == 台账键集合。
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("abi_report", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        backlog = ROOT / "tools" / "engine_abi_backlog.json"
        self.assertTrue(backlog.is_file(), "缺少 ABI 欠账台账 tools/engine_abi_backlog.json")
        data = json.loads(backlog.read_text(encoding="utf-8"))
        rows = data["rows"]
        for name, row in rows.items():
            with self.subTest(constant=name):
                self.assertIn(row.get("class"), ("A", "B", "C"),
                              f"{name} 的类别必须是 A/B/C")
                self.assertTrue(row.get("why"), f"{name} 没写明为什么读不出来/要不要补")
                self.assertTrue(row.get("evidence"), f"{name} 没给出依据")
        functions = [entry for entry in load_table() if entry["kind"] == "function"]
        unknown = {e["constant"] for e in functions
                   if module.declared_signature(e["constant"]) is None}
        self.assertEqual(
            unknown - set(rows),
            set(),
            "这些常量工具读不出声明，却没在台账里分诊（要么补工具、要么写明为什么不必补）",
        )
        self.assertEqual(
            set(rows) - unknown,
            set(),
            "台账里这些条目**已经能读出来了**，请从台账里删掉（否则欠账永远挂着）",
        )

    def test_our_call_arity_is_legal(self):
        """能自动识别出调用点的那些：实参个数必须是 n（静态/自由）或 n+1（成员函数的 this）。"""
        result = subprocess.run(
            [sys.executable, str(TOOL), "--mismatch-only"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(
            result.returncode, 0,
            "引擎调用 ABI 体检发现参数个数不符：\n" + result.stdout + result.stderr,
        )
        self.assertIn("参数个数不符 **0**", result.stdout)

    def _evidence_covered(self) -> set[str]:
        covered: set[str] = set()
        for directory in (LAYOUT_DIR, LAYOUT_DIR / "drafts"):
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                covered.update(re.findall(r"k[A-Za-z0-9]+Offset", path.read_text(encoding="utf-8")))
        return covered

    def test_layout_table_progress_is_reported(self):
        """只报进度、不判红：字段偏移有多少条已经有布局表（或草稿）证据。"""
        table = load_table()
        fields = [entry for entry in table if entry["kind"] == "field"]
        covered = self._evidence_covered()
        with_evidence = [entry for entry in fields if entry["constant"] in covered]
        print(
            f"\n[进度] 偏移常量 {len(table)} 个：函数 {sum(1 for e in table if e['kind'] == 'function')}、"
            f"数据 {sum(1 for e in table if e['kind'] == 'data')}、字段 {len(fields)}；"
            f"字段里已有证据的 {len(with_evidence)} 个"
            f"（正式表 + 草稿；草稿见 tools/layout_tables/drafts/）"
        )

    def test_field_offset_drafts_are_verifiable(self):
        """草稿里的每条证据都必须能被重新反汇编证明（草稿也不许"只有人记得"）。

        草稿由 `tools/draft_layout_evidence.py` 生成，起草时已自带同样的复核；
        这里再独立跑一次生成器的 `--verify`，防止"草稿被手改坏"。
        """
        drafts = sorted((LAYOUT_DIR / "drafts").glob("*.json")) if (LAYOUT_DIR / "drafts").exists() else []
        if not drafts:
            self.skipTest("还没有草稿（跑 tools/draft_layout_evidence.py 生成）")
        if not NRO.exists():
            self.skipTest("仓库里没有游戏镜像（公开仓库不带游戏资源）")
        for path in drafts:
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "build_layout_table.py"),
                 "--table", str(path), "--verify"],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0,
                             f"{path.name} 的证据复核不通过：\n{result.stdout}{result.stderr}")
            table = json.loads(path.read_text(encoding="utf-8"))
            for row in table["rows"]:
                self.assertTrue(row.get("evidence"), f"{path.name} 的 {row['name']} 没有证据")
                self.assertEqual(row.get("confidence"), "candidate",
                                 f"{path.name} 的 {row['name']} 草稿不允许是 confirmed（语义未经人工确认）")


    # ------------------------------------------------------------------
    # 入口中继回调（引擎调我们）：参数**与返回值**都要对账
    # ------------------------------------------------------------------

    def _relay_rows(self):
        import importlib.util  # noqa: PLC0415

        spec = importlib.util.spec_from_file_location("abi_report_relay", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        image = NRO.read_bytes() if NRO.exists() else None
        rows = module.classify_relay(module.relay_declarations(), image)
        return module, rows

    def test_entry_relay_callbacks_declare_the_engines_return_value(self):
        """中继回调是**以目标函数的身份返回**的 ⇒ 目标函数在 `x0` 里返回什么，回调就得返回什么。

        ## 为什么要有它（2026-09-21 真机事故）

        入口中继把"本模块里的一个 `extern "C"` 回调"当目标函数来跑（`entry_relay.hpp`：槽里 `br`
        尾调用回调，回调的 `ret` 直接回到游戏的调用方）。前三种形态（我们主动调引擎）看不见这批回调，
        于是"返回值"这一项**从来没有被任何门禁比过**：

        * `Entity_Player::UseActiveItem`（本体 `0x30653C`）**有返回值** —— 唯一收尾点 `0x31A8C0` 是
          `mov x0, x22`（`x22 | (UseFlags & 1) << 8`），而我们的回调声明成 `void` ⇒ 游戏调用方读到的
          `x0` 是回调里最后一次调用的残留值 ⇒ **用后记账（扣充能 / 移除单次道具 / 服装动画）走错分支**，
          用户看到的是"所有主动道具用后不掉充能、部分道具被移除"；
        * 同一形状还有 `Entity_Pickup::handle_collision`（`0x2728C8` 的 `mov w0, #1`）与
          `Room::spawn_entity`（`0x453EA0` 的 `mov w0, w21`）——三个一起修。

        判据（纯静态，对着镜像）：从函数**自己的**收尾点往回扫，先撞上"写 `x0/w0`"⇒ 有返回值；
        先撞上 `bl/blr` ⇒ 收尾处的 `x0` 是调用残留 ⇒ void。两边不一致即判红。
        """
        module, rows = self._relay_rows()
        self.assertEqual(len(rows), len(module.RELAY_CALLBACK_TARGETS),
                         "中继回调表与登记条数不一致（`relay_declarations()` 解析不全？）")
        unresolved = [row["callback"] for row in rows if row["declared_parameters"] is None]
        self.assertEqual(unresolved, [],
                         "这些中继回调的 `extern \"C\"` 定义没被解析出来（改过写法就要同步工具）："
                         + repr(unresolved))
        bad = [row for row in rows if row["verdict"] == "relay-mismatch"]
        self.assertEqual(
            [(row["callback"], row["detail"]) for row in bad], [],
            "中继回调的声明与引擎不符（参数或返回值）")

    def test_entry_relay_return_values_are_actually_judged(self):
        """判据本身要真的在判：镜像在场时，"引擎有没有返回值"这一项**不许有判不出的条目**。

        这条防的是"门禁看起来在跑、其实一项都没比"（2026-09-17 那次覆盖率事故的同类形状）。
        """
        if not NRO.exists():
            self.skipTest("仓库里没有游戏镜像（公开仓库不带游戏资源）")
        _module, rows = self._relay_rows()
        unknown = [row["callback"] for row in rows if row["engine_returns"] is None]
        self.assertEqual(unknown, [], "返回值这一项没判出来（收尾点或往回扫的判据要修）：" + repr(unknown))
        returns = [row["callback"] for row in rows if row["engine_returns"]]
        self.assertEqual(
            len(returns), 4,
            "引擎里有返回值的入口中继靶点数变了（当前 4 个：ItemPool::GetCollectible、"
            "UseActiveItem、handle_collision、spawn_entity）。"
            "★ 批次 098（2026-09-24）这里从 5 **回到 4**：成就闸门按用户裁定从 "
            "`PersistentGameData::TryUnlock`（返回 bool）挪到 `PersistentGameData::SetReadOnly`"
            "（返回 void）—— 是设计变更，不是判据坏了。"
            "除了这类明确的设计变更，变了要么是镜像换了版本、"
            "要么是判据坏了 —— 两边都要先查清再改这个数字：" + repr(returns))

    def test_the_three_after_use_bookkeeping_callbacks_return_a_value(self):
        """三个"用后记账"回调**必须**声明非 void 返回值（钉住 2026-09-21 的修复，不许退回 void）。"""
        _module, rows = self._relay_rows()
        by_callback = {row["callback"]: row for row in rows}
        for callback in ("EntryRelayUseActiveItemCallback",
                         "EntryRelayPickupCollisionCallback",
                         "EntryRelayRoomEntitySpawnCallback"):
            row = by_callback[callback]
            self.assertIsNotNone(row["declared_return"], f"{callback} 没解析出来")
            self.assertNotEqual(
                row["declared_return"].replace(" ", ""), "void",
                f"{callback} 又变回 void 了：中继是**以目标函数的身份**返回的，"
                "引擎的返回值会被我们弄成垃圾（真机症状：主动道具用后不掉充能 / 道具被移除）")


if __name__ == "__main__":
    unittest.main()
