"""读数工具的"偏移表自动同步"门禁（**不需要设备**）。

为什么值得单独立测试：这套工具的偏移以前是**手抄**的，而改任何一个编译单元都会让
`bss`/`data` 整体挪位 —— 项目已经因此误读过两次（读数"看起来有值"、其实是别人的变量）。
现在改成"读数前直接问本地 ELF 的符号表"，那么就要钉住三件事：

1. ELF 解析本身对不对（用一个**自己拼出来的最小 ELF** 验，不依赖构建产物）；
2. 解析不到的符号必须**从表里删掉**，绝不允许沿用过期的偏移；
3. 提示表（键 → 符号名）本身不许写空、写重，也不许指向已经不存在的键。
"""

import importlib.util
import re
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GDB_TOOL = ROOT / "tools" / "read_device_state_via_gdb.py"
ELF_TOOL = ROOT / "tools" / "elf_syms.py"
ERROR_PROBE = ROOT / "tools" / "probe_lua_error_channel.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_minimal_elf(symbols: dict, payload: bytes = b"\x11" * 32, text_vaddr: int = 0x1000,
                      text_offset: int = 0x200) -> bytes:
    """拼一个"够解析"的 ELF64：一个 PT_LOAD + .text/.symtab/.strtab/.shstrtab。

    自己拼而不是用真构建产物：门禁要在**没有构建过**的机器上也能跑（`runtime.elf` 是被
    gitignore 的产物）。
    """
    shstr = b"\0.text\0.symtab\0.strtab\0.shstrtab\0"
    names = {".text": shstr.index(b".text"), ".symtab": shstr.index(b".symtab"),
             ".strtab": shstr.index(b".strtab"), ".shstrtab": shstr.index(b".shstrtab")}

    strtab = bytearray(b"\0")
    entries = []
    for name, (value, size) in symbols.items():
        off = len(strtab)
        strtab += name.encode() + b"\0"
        entries.append((off, value, size))

    symtab = bytearray(24)                      # 第一项是空符号（ELF 规定）
    for off, value, size in entries:
        symtab += struct.pack("<IBBHQQ", off, 0x10, 0, 1, value, size)

    payload_offset = text_offset
    symtab_offset = payload_offset + len(payload)
    strtab_offset = symtab_offset + len(symtab)
    shstr_offset = strtab_offset + len(strtab)
    shoff = (shstr_offset + len(shstr) + 7) & ~7
    shnum = 5                                   # null + .text/.symtab/.strtab/.shstrtab
    total = shoff + shnum * 64

    blob = bytearray(total)
    blob[0:16] = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    struct.pack_into("<HHIQQQIHHHHHH", blob, 0x10,
                     1, 0xB7, 1, text_vaddr, 64, shoff, 0, 64, 56, 1, 64, shnum, 4)
    struct.pack_into("<IIQQQQQQ", blob, 64, 1, 5, text_offset, text_vaddr, 0,
                     len(payload), len(payload), 8)

    def section(index: int, name_off: int, kind: int, addr: int, offset: int, size: int,
                link: int, align: int, entsize: int) -> None:
        struct.pack_into("<IIQQQQIIQQ", blob, shoff + index * 64,
                         name_off, kind, 0, addr, offset, size, link, 0, align, entsize)

    section(1, names[".text"], 1, text_vaddr, payload_offset, len(payload), 0, 4, 0)
    section(2, names[".symtab"], 2, 0, symtab_offset, len(symtab), 3, 8, 24)
    section(3, names[".strtab"], 3, 0, strtab_offset, len(strtab), 0, 1, 0)
    section(4, names[".shstrtab"], 3, 0, shstr_offset, len(shstr), 0, 1, 0)
    blob[payload_offset:payload_offset + len(payload)] = payload
    blob[symtab_offset:symtab_offset + len(symtab)] = symtab
    blob[strtab_offset:strtab_offset + len(strtab)] = strtab
    blob[shstr_offset:shstr_offset + len(shstr)] = shstr
    return bytes(blob)


class ElfSymTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.elf_syms = load_module("elf_syms", ELF_TOOL)

    def test_load_symbols_reads_names_and_addresses(self):
        blob = build_minimal_elf({"IsaacModRuntime_GetRuntimeIdentity": (0x28bd8, 68),
                                  "g_LastLuaErrorText": (0x336ca8, 256)})
        symbols = self.elf_syms.load_symbols(blob)
        self.assertEqual(symbols["IsaacModRuntime_GetRuntimeIdentity"], (0x28bd8, 68))
        self.assertEqual(symbols["g_LastLuaErrorText"], (0x336ca8, 256))

    def test_read_vaddr_translates_through_program_headers(self):
        """`read_vaddr` 要把"模块内偏移"换成文件偏移（自校验指纹就是这么取的）。"""
        payload = bytes(range(32))
        blob = build_minimal_elf({}, payload=payload, text_vaddr=0x1000, text_offset=0x200)
        self.assertEqual(self.elf_syms.read_vaddr(blob, 0x1000, 8), bytes(range(8)))
        self.assertEqual(self.elf_syms.read_vaddr(blob, 0x1008, 4), payload[8:12])
        self.assertIsNone(self.elf_syms.read_vaddr(blob, 0x999999, 4))

    def test_stripped_elf_reports_no_symbols_instead_of_guessing(self):
        blob = bytearray(build_minimal_elf({"x": (0x10, 4)}))
        # 把 `.symtab` 这个节**改名**（名字置空），模拟没有符号表的产物：
        # 解析器按节名找 `.symtab`，于是应当老实返回"没有符号"而不是瞎猜。
        shoff, = struct.unpack_from("<Q", blob, 0x28)
        struct.pack_into("<I", blob, shoff + 2 * 64, 0)
        self.assertEqual(self.elf_syms.load_symbols(bytes(blob)), {})


class SymSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_module("read_device_state_via_gdb", GDB_TOOL)

    def setUp(self):
        self.original = dict(self.tool.SYMS)

    def tearDown(self):
        self.tool.SYMS.clear()
        self.tool.SYMS.update(self.original)

    def test_sync_takes_offsets_from_the_elf(self):
        key = "identity"
        name = self.tool.SYM_ELF_NAMES[key]
        with self._elf({name: (0x1234, 68)}) as path:
            self.tool.sync_syms_from_elf(path)
        self.assertEqual(self.tool.SYMS[key], 0x1234)

    def test_callback_registry_count_layout_follows_elf_size(self):
        name = self.tool.SYM_ELF_NAMES['g_CallbackRegistry']
        for size, offset in ((0x2008, 0x2000), (0x2508, 0x2500), (0x2d08, 0x2d00)):
            with self.subTest(size=size), self._elf({name: (0x8000, size)}) as path:
                self.tool.sync_syms_from_elf(path)
                self.assertEqual(self.tool.CALLBACK_REGISTRY_COUNT_OFFSET, offset)
                requests, _ = self.tool.build_requests(0x10000000, 0, 0)
                request = next(row for row in requests if row[0] == 'callback_count')
                self.assertEqual(request[1], 0x10008000 + offset)

    def test_unknown_registry_layout_does_not_request_a_guessed_count(self):
        name = self.tool.SYM_ELF_NAMES['g_CallbackRegistry']
        with self._elf({name: (0x8000, 0x2608)}) as path:
            self.tool.sync_syms_from_elf(path)
            requests, skipped = self.tool.build_requests(0x10000000, 0, 0)
            self.assertNotIn('callback_count', [row[0] for row in requests])
            self.assertIn('callback_count_layout', skipped)

    def test_diagnostic_snapshot_reads_and_labels_optional_u32(self):
        import contextlib
        import io
        fields = ('g_CallbackDiagnosticViewIncomplete', 'g_CallbackDiagnosticViewOverflow')
        names = self.tool.SYM_ELF_NAMES_OPTIONAL
        with self._elf({names[key]: (0x8000 + index * 4, 4) for index, key in enumerate(fields)}) as path:
            self.tool.sync_syms_from_elf(path)
            requests, _ = self.tool.build_requests(0x10000000, 0, 0)
            self.assertTrue(all(key in [row[0] for row in requests] for key in fields))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertTrue(self.tool.print_callback_diagnostic_view({fields[0]: [0x100000001]}))
        self.assertIn('诊断快照', output.getvalue())
        self.assertIn('标记 = 1', output.getvalue())
        self.assertIn('条目 = 未读', output.getvalue())
        self.assertFalse(self.tool.print_callback_diagnostic_view({}))

    def test_missing_symbol_is_dropped_not_kept_stale(self):
        """核心断言：解析不到就**删键**。留着过期偏移等于把别人的变量当成我们的。"""
        kept, gone = "identity", "g_DefaultEntry"
        with self._elf({self.tool.SYM_ELF_NAMES[kept]: (0x1234, 68)}) as path:
            missing = self.tool.sync_syms_from_elf(path)
        self.assertIn(gone, missing)
        self.assertNotIn(gone, self.tool.SYMS)
        self.assertEqual(self.tool.SYMS[kept], 0x1234)

    def test_no_elf_keeps_the_table_and_says_so(self):
        with self._elf({}) as path:
            path.unlink()
            missing = self.tool.sync_syms_from_elf(path)
        self.assertTrue(missing)
        self.assertEqual(self.tool.SYMS, self.original)

    def _elf(self, symbols):
        import tempfile

        class _Fixture:
            def __enter__(self_inner):
                self_inner._dir = tempfile.TemporaryDirectory()
                target = Path(self_inner._dir.name) / "runtime.elf"
                target.write_bytes(build_minimal_elf(symbols))
                return target

            def __exit__(self_inner, *_exc):
                self_inner._dir.cleanup()
                return False

        return _Fixture()


class SymbolHintTests(unittest.TestCase):
    """提示表本身的完整性：写错了会让整张偏移表静默错位。"""

    @classmethod
    def setUpClass(cls):
        cls.tool = load_module("read_device_state_via_gdb_hints", GDB_TOOL)
        cls.probe = load_module("probe_lua_error_channel", ERROR_PROBE)

    def test_every_hint_key_is_readable_after_sync(self):
        """同步之后，提示表里的每个键都必须真的在 `SYMS` 里 —— 否则读数会 KeyError 或读错位置。

        注意：错误通道那几个键（`g_CallbackError` 等）**只在提示表里**，值一律由 ELF 提供；
        这正是我们要的：它们的字面值没有任何理由手抄一份。
        """
        elf = ROOT / self.tool.DEFAULT_ELF
        if not elf.exists():
            self.skipTest(f"没有本地构建产物 {self.tool.DEFAULT_ELF}")
        self.tool.sync_syms_from_elf(elf)
        absent = [key for key in self.tool.SYM_ELF_NAMES if key not in self.tool.SYMS]
        self.assertEqual(absent, [], f"同步后仍缺失：{absent}")

    def test_hints_are_unique_and_non_empty(self):
        names = list(self.tool.SYM_ELF_NAMES.values())
        self.assertTrue(all(names))
        self.assertEqual(len(names), len(set(names)), "同一个符号名被挂到两个键上")

    def test_probe_only_hints_stay_out_of_the_main_table(self):
        """探针专用符号必须**留在自己的表里**，且符号名必须落在探针的命名空间里。

        为什么单开一张表（批次 019）：上面两条断言要求"主表每一项都能在当前**生产** ELF 里
        解析到"，而探针符号按定义在生产构建里不存在（`PROBE_BREAK=0` 时整个 TU 被编译掉）。
        把探针符号混进主表只剩两条路：要么放宽那两条断言，要么每次跑门禁都得先出一份探针
        构建 —— 两条都不能要。所以这里反过来钉住"它不许混进来"，顺便钉住命名空间前缀，
        免得将来有人把普通变量也塞进这张"门禁不查"的表里。
        """
        probe_only = getattr(self.tool, "SYM_ELF_NAMES_PROBE_ONLY", None)
        self.assertIsNotNone(probe_only, "探针专用符号表不见了")
        overlap = set(probe_only) & set(self.tool.SYM_ELF_NAMES)
        self.assertEqual(overlap, set(), f"这些键同时出现在主表与探针表里：{sorted(overlap)}")
        for key, name in probe_only.items():
            self.assertTrue(name.startswith("_ZN5isaac7runtime5probe"),
                            f"{key} 的符号名不在探针命名空间里：{name}")

    def test_probe_build_only_hints_are_accounted_for(self):
        """**正式包按设计缺席**的那批探针量：要么解析到，要么如实记账，不许静默消失。

        为什么再分一张表（批次 232，2026-09-30 用户指令"将探针都撤去"）：正式包现在把探针的
        采集动作整个编译掉了（`runtime/source/probe_gate.hpp`），而正式包是带 section GC 链接的
        ⇒ **没人写的全局量会被链接器丢掉** ⇒ 那 77 个符号在生产 ELF 里根本不存在。
        主表那两条断言是"偏移表不许过期"的守门人，不该为探针放宽（与上一张表同一个理由）。

        三条断言：
        ① 三张符号表**互不重叠**（否则同一个键两边抢着写 `SYMS`）；
        ② 这张表里的键看起来必须是"我们自己的诊断全局量"（键 `g_` 打头，或符号名落在
           `isaac::runtime` 里）—— 防止有人把别的东西塞进这张"允许缺席"的表来糊弄门禁；
        ③ 同步之后每一项要么进 `SYMS`、要么进 `SYM_MISSING` + 本构建无探针名单，
           **不许两边都不在**（那才是"静默消失"，读数会 KeyError）。
        """
        table = getattr(self.tool, "SYM_ELF_NAMES_PROBE_BUILD_ONLY", None)
        self.assertIsNotNone(table, "探针包专用符号表不见了")
        self.assertTrue(table, "这张表空了 ⇒ 有人把键挪回了主表（那会让上面两条断言红）")
        for other_name, other in (("主表", self.tool.SYM_ELF_NAMES),
                                  ("探针 TU 表", self.tool.SYM_ELF_NAMES_PROBE_ONLY)):
            overlap = set(table) & set(other)
            self.assertEqual(overlap, set(),
                             f"这些键同时出现在探针包表与{other_name}里：{sorted(overlap)}")
        for key, name in table.items():
            self.assertTrue(key.startswith("g_") or "5isaac7runtime" in name,
                            f"{key} / {name} 看着不像我们自己的诊断全局量")
        elf = ROOT / self.tool.DEFAULT_ELF
        if not elf.exists():
            self.skipTest(f"没有本地构建产物 {self.tool.DEFAULT_ELF}")
        self.tool.sync_syms_from_elf(elf)
        for key in table:
            self.assertTrue(key in self.tool.SYMS or key in self.tool.SYM_MISSING,
                            f"{key} 既没解析到、也没记进 SYM_MISSING（静默消失了）")
        # 反向自证：**解析得到**的键不许被记成"本构建没有" —— 两个名单不许互相污染。
        contaminated = [k for k in self.tool.SYMS
                        if k in table and k in self.tool.SYM_PROBE_BUILD_ABSENT]
        self.assertEqual(contaminated, [],
                         f"这些键既解析到了、又被记成「本构建无探针」：{sorted(contaminated)}")

    def test_error_probe_keys_are_all_auto_synced(self):
        """错误通道探针读的每个键都必须能被自动同步。

        否则它会用**手抄的过期偏移**去读 —— 这正是这个探针以前读不出东西的原因之一
        （旧版还在调用早已不存在的接口）。
        """
        for key in self.probe.WANTED:
            self.assertIn(key, self.tool.SYM_ELF_NAMES,
                          f"{key} 没进提示表 ⇒ 探针会读到过期偏移")

    def test_error_probe_decodes_module_name_heads(self):
        word = int.from_bytes(b"main.lua", "big")
        self.assertEqual(self.probe.ascii_of(word), "main.lua")

    def test_current_build_elf_resolves_every_hint(self):
        """有构建产物时顺带核对一次：整张提示表都要能在**当前这份 ELF** 里解析到。

        这条是"偏移表不许过期"的守门人：重建之后若某个符号改了名/没了，这里会红。
        """
        elf = ROOT / self.tool.DEFAULT_ELF
        if not elf.exists():
            self.skipTest(f"没有本地构建产物 {self.tool.DEFAULT_ELF}")
        elf_syms = load_module("elf_syms_for_gate", ELF_TOOL)
        table = elf_syms.load_symbols(elf.read_bytes())
        unresolved = {key: name for key, name in self.tool.SYM_ELF_NAMES.items()
                      if name not in table}
        self.assertEqual(unresolved, {}, f"这些符号在本构建的 ELF 里找不到：{unresolved}")


class U32ReadMaskingTests(unittest.TestCase):
    """**4 字节的全局必须掩码**：读数工具按 8 字节取字，一个字里往往装着两个 `uint32`。

    ## 为什么要有这条（2026-09-28 批次 192 的现场发现）

    同一个坑已经咬过两次，而两次都是"读数看起来有值、其实是错的"：

    * 2026-09-26：`mod_engine_stage`（真值 2）被印成 `4294967298`（= 2 | 1<<32，高 32 位是隔壁
      `mod_engine_attempts` 的 1）—— 于是"调了 4 次"与"一次都没调"这种**相反结论**都可能得出；
    * 2026-09-28（本批）：我新加的 10 个触摸诊断量全是 `uint32`，地址实测 4 字节一格
      （`0x83c0818…0x83c083c`，正好两两共用一个 8 字节字）⇒ 若用 `first(...)`，
      **每一个印出来的数都掺了隔壁的值**。加上这条门禁时它还顺带扫出了一处**存量**问题
      （`g_sequence`，启动状态机那一段）—— 见本类最后一个用例。

    修法是既有的两种之一：`first_u32(...)`，或 `first(...) & 0xFFFFFFFF`。
    **判据不是"必须写成哪一种"，而是"有没有掩码"** —— 存量里两种写法都有（79 处 4 字节读），
    一刀切要求某一种会误报一片。

    这条门禁**不需要设备**，但需要本构建的 `runtime.elf`（符号大小从 ELF 的 `.symtab` 读，
    **不写死名单** —— 写死名单就等于又抄了一张会过期的表）。
    """

    @classmethod
    def setUpClass(cls):
        cls.tool = load_module("gdb_tool_for_u32_gate", GDB_TOOL)
        cls.elf_syms = load_module("elf_syms_for_u32_gate", ELF_TOOL)

    def _violations(self, source: str) -> list[str]:
        """按同一套判据扫一段源码，返回违规行（**判据只有这一份**，自证用例复用它）。"""
        elf = ROOT / self.tool.DEFAULT_ELF
        if not elf.exists():
            self.skipTest(f"没有本地构建产物 {self.tool.DEFAULT_ELF}")
        table = self.elf_syms.load_symbols(elf.read_bytes())
        found = []
        for lineno, line in enumerate(source.splitlines(), 1):
            for key in re.findall(r"first\(\s*values\s*,\s*'([A-Za-z0-9_]+)'", line):
                name = self.tool.SYM_ELF_NAMES.get(key)
                if not name or name not in table:
                    continue                      # 非字面键 / 不在表里 ⇒ 不判
                if table[name][1] != 4:
                    continue                      # 只判 4 字节的（指针、u64 整字读是对的）
                if "0xFFFFFFFF" not in line:
                    found.append(f"行 {lineno}：{key}（{name}，size=4）—— {line.strip()[:80]}")
        return found

    def test_every_four_byte_global_is_masked(self):
        violations = self._violations(GDB_TOOL.read_text(encoding="utf-8"))
        self.assertEqual(
            violations, [],
            "这些 4 字节全局用 `first(...)` 读却**没掩码**（会把隔壁全局取进高 32 位）：\n  "
            + "\n  ".join(violations)
            + "\n\n改成 `first_u32(values, '键')`，或补 `& 0xFFFFFFFF`。")

    def test_the_rule_actually_fires(self):
        """**破坏证伪**：门禁必须真的抓得到这一形状，否则它只是个装饰。

        造一行"4 字节符号 + 无掩码"的假源码，走**同一个** `_violations`，必须报出来。
        （本项目纪律：新增/优化过的门禁必须能抓到它声称能抓的东西。）
        """
        elf = ROOT / self.tool.DEFAULT_ELF
        if not elf.exists():
            self.skipTest(f"没有本地构建产物 {self.tool.DEFAULT_ELF}")
        table = self.elf_syms.load_symbols(elf.read_bytes())
        key = next((k for k, n in self.tool.SYM_ELF_NAMES.items()
                    if n in table and table[n][1] == 4), None)
        self.assertIsNotNone(key, "符号表里找不到任何 4 字节符号，这条自证用例本身失效了")
        fake = f"    value = first(values, '{key}')\n"
        self.assertNotIn("0xFFFFFFFF", fake, "构造的假源码本身必须是不带掩码的")
        hits = self._violations(fake)
        self.assertEqual(len(hits), 1, f"判据没抓到构造出来的违规 —— 门禁是假的：{hits}")
        self.assertIn(key, hits[0])

    def test_the_rule_accepts_both_legal_spellings(self):
        """反向自证：两种合法写法都**不许**被判红（否则门禁会逼着大家改存量）。"""
        elf = ROOT / self.tool.DEFAULT_ELF
        if not elf.exists():
            self.skipTest(f"没有本地构建产物 {self.tool.DEFAULT_ELF}")
        table = self.elf_syms.load_symbols(elf.read_bytes())
        key = next((k for k, n in self.tool.SYM_ELF_NAMES.items()
                    if n in table and table[n][1] == 4), None)
        self.assertIsNotNone(key)
        for legal in (f"    v = first_u32(values, '{key}')\n",
                      f"    v = first(values, '{key}') & 0xFFFFFFFF\n"):
            self.assertEqual(self._violations(legal), [], f"合法写法被判红：{legal!r}")


class GameRunningCheckTests(unittest.TestCase):
    """"游戏在不在跑"的判据：**不能只看进程表里有没有 Application**。

    2026-09-15 实测教训：FTP 自己（`hbl.elf` + `ftpd.elf`）也是一个 Application 进程，
    于是"用户已彻底关掉游戏、只开着 FTP"时，只看进程表的检查一直报"游戏还在跑" ——
    既挡住了本来安全的写卡，又让人怀疑用户没关游戏。真正的判据是模块清单里有没有
    `Repentance.nrs.elf`。这几条把两个方向的误判都钉住。
    """

    @classmethod
    def setUpClass(cls):
        cls.tool = load_module("read_device_state_via_gdb_gamecheck", GDB_TOOL)

    FTP_INFO = """Process:     0x170 (Application)
Program Id:  0x052bd540ec804000
Application: 1
Hbl:         0
Modules:
  0x0062000000 - 0x0062005fff hbl.elf
  0x062be51000 - 0x062bf5efff ftpd.elf
"""

    GAME_INFO = """Process:     0x16f (Application)
Modules:
  0x0036b394f000 - 0x0036b3f40000 Repentance.nrs.elf
  0x007c28d81000 - 0x007c28d8f000 runtime.elf
"""

    def test_module_names_are_read_from_the_modules_section(self):
        self.assertEqual(self.tool.parse_module_names(self.FTP_INFO), ["hbl.elf", "ftpd.elf"])
        self.assertEqual(self.tool.parse_module_names(self.GAME_INFO),
                         ["Repentance.nrs.elf", "runtime.elf"])

    def test_ftp_application_is_not_the_game(self):
        """只看"有没有 Application"的写法会在这里判错 —— 这正是要防的那次事故。"""
        self.assertEqual(self.tool.parse_processes("368        Application \n"), 368)
        names = self.tool.parse_module_names(self.FTP_INFO)
        self.assertFalse(any(self.tool.GAME_MODULE_MARKER in name for name in names),
                         "FTP 进程被误判成游戏在跑")

    def test_game_application_is_recognized(self):
        names = self.tool.parse_module_names(self.GAME_INFO)
        self.assertTrue(any(self.tool.GAME_MODULE_MARKER in name for name in names))

    def test_empty_output_says_nothing_instead_of_guessing(self):
        """拿不到模块清单时不许猜 —— 返回空表（调用方据此报"判断不了"）。"""
        self.assertEqual(self.tool.parse_module_names("Modules:\n"), [])


if __name__ == "__main__":
    unittest.main()
