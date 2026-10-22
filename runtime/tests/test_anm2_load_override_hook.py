"""批次 363：`ANM2::Load` 入口中继 —— 让"模组覆盖本体资源"真正生效。

被测对象：
  * `runtime/source/anm2_load_override_hook.{hpp,cpp}`（回调体、只读遍历、作废原语）；
  * `runtime/source/runtime_constants.hpp` 里本批新增的偏移与 16 字节守卫；
  * `runtime/src/domain/runtime/hook_catalog.hpp` 里的新挂点；
  * `tools/read_device_state_via_gdb.py` 的读数面（符号名 / 挂点名 / 报告段）。

这个��禁**只做宿主机能做的判定**（纯静态核对 + 用游戏镜像复核偏移与守卫），
真机行为由探针与读数验收。它要挡住的是"看起来接上了、实际指错地方"的那类错误：

  1. 16 字节守卫必须与 `Repentance.nro` 里 `0xC970` 处的现场**逐字节相同**
     —— 抄错一个字节就等于中继永远装不上（而那是静默失败）；
  2. 作废原语的两个偏移必须是**真函数入口**（序言逐字节相同），且**不是** `Load2` 之类的近邻；
  3. 挂点必须登记成 `EntryRelay` + `required = false`（装不上不许拖垮模组加载）；
  4. 回调必须**先问解析器、答模组层才动手**（不许无条件作废）；
  5. 计数为 0 时**绝不调用** `RemoveReference`（引擎那个函数会先打日志再减 ⇒ 下溢）；
  6. 读数工具三张表（`HOOK_NAMES` / `RELAY_BY_HOOK` / `SYM_ELF_NAMES`）与新挂点同步。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
HOOK_HEADER = SOURCE / "anm2_load_override_hook.hpp"
HOOK_IMPL = SOURCE / "anm2_load_override_hook.cpp"
CONSTANTS = SOURCE / "runtime_constants.hpp"
CATALOG = ROOT / "runtime" / "src" / "domain" / "runtime" / "hook_catalog.hpp"
ADAPTER = ROOT / "runtime" / "src" / "infrastructure" / "relay" / "entry_relay_hook_adapter.cpp"
EXLAUNCH_ADAPTER = (
    ROOT / "runtime" / "src" / "infrastructure" / "exlaunch" / "exlaunch_hook_adapter.cpp"
)
READER = ROOT / "tools" / "read_device_state_via_gdb.py"
MAKEFILE = ROOT / "runtime" / "misc" / "mk" / "common.mk"
NRO = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0"
    / "1"
    / ".nro"
    / "Repentance.nro"
)


def expected_bytes(text, name):
    """读出 `inline constexpr std::array<u8, 16> kName = { ... };` 的 16 个字节。"""
    match = re.search(
        rf"inline constexpr std::array<u8, 16> {name} = \{{(.*?)\}};", text, re.S
    )
    assert match, f"{name} 没找到"
    values = [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{2})", match.group(1))]
    assert len(values) == 16, f"{name} 不是 16 字节（拿到 {len(values)}）"
    return bytes(values)


def offset_of(text, name):
    match = re.search(rf"inline constexpr uintptr_t {name} = (0x[0-9A-Fa-f]+);", text)
    assert match, f"{name} 没找到"
    return int(match.group(1), 16)


class Anm2LoadOverrideHookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.constants = CONSTANTS.read_text(encoding="utf-8")
        cls.impl = HOOK_IMPL.read_text(encoding="utf-8")
        cls.header = HOOK_HEADER.read_text(encoding="utf-8")
        cls.catalog = CATALOG.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.exlaunch = EXLAUNCH_ADAPTER.read_text(encoding="utf-8")
        cls.reader = READER.read_text(encoding="utf-8")
        cls.nro = NRO.read_bytes()

    # ---- 1. 守卫必须与游戏镜像现场逐字节相同 -------------------------------
    def test_guards_match_the_game_image(self):
        cases = [
            # ★ 靶点复用既有的 `kSpriteLoad*` —— 那个函数的 mangled 名就是 `ANM2::Load`
            #   （与 Lua 侧 `Sprite:Load` 同一个地址）；本批**不**另立常量。
            ("kSpriteLoadOffset", "kSpriteLoadExpectedBytes", "ANM2::Load"),
            (
                "kAnmCacheRemoveReferenceOffset",
                "kAnmCacheRemoveReferenceExpectedBytes",
                "AnmCache::RemoveReference",
            ),
            (
                "kAnmCacheFreeUnreferencedEntriesOffset",
                "kAnmCacheFreeUnreferencedEntriesExpectedBytes",
                "AnmCache::FreeUnreferencedEntries",
            ),
            # ★★ 批次 366（2026-10-05）：挂载点表的**元素类型**守卫 —— 引擎是
            #   `add x19, x19, #0x8`（步长 8）+ `ldr x2, [x19]`（元素当 C 串指针）。
            #   我们曾按 24 字节 `std::string` 读这张表 ⇒ 中继整整一轮静默失效。
            (
                "kAnmCacheMountLoopOffset",
                "kAnmCacheMountLoopExpectedBytes",
                "AnmCache::Load2 的挂载点遍历（步长 8 / 元素是 char*）",
            ),
            # ★★ 批次 367：缓存节点布局（计数 +0x88 / 右孩子 +0x08）。
            (
                "kAnmCacheNodeLayoutOffset",
                "kAnmCacheNodeLayoutExpectedBytes",
                "AnmCache 缓存节点布局（FreeUnreferencedEntries 里那 16 字节）",
            ),
        ]
        for offset_name, bytes_name, label in cases:
            offset = offset_of(self.constants, offset_name)
            expected = expected_bytes(self.constants, bytes_name)
            actual = self.nro[offset : offset + 16]
            self.assertEqual(
                actual,
                expected,
                f"{label}（{offset_name} = {offset:#x}）的 16 字节守卫与镜像不符："
                f"现场 {actual.hex()} vs 登记 {expected.hex()}",
            )

    # ---- 2. 三个偏移互不相同（挡住"顺手抄了邻居的偏移"）--------------------
    def test_offsets_are_distinct(self):
        offsets = [
            offset_of(self.constants, "kSpriteLoadOffset"),
            offset_of(self.constants, "kAnmCacheRemoveReferenceOffset"),
            offset_of(self.constants, "kAnmCacheFreeUnreferencedEntriesOffset"),
        ]
        self.assertEqual(len(set(offsets)), 3, f"三个偏移有重复：{[hex(o) for o in offsets]}")
        # ★ 一个地址只留一个名字：不许为同一个函数再立一套 `kAnm2Load*` 常量
        #   （`0xC970` 的 mangled 名就是 `ANM2::Load`，与既有的 `kSpriteLoadOffset` 同一个地址）。
        for duplicate in ("kAnm2LoadFileOffset", "kAnm2LoadExpectedBytes"):
            self.assertNotIn(
                duplicate, self.constants,
                f"{duplicate} 是重复常量 —— 靶点请复用既有的 kSpriteLoad*（一个地址一个名字）",
            )

    # ---- 3. 挂点登记：EntryRelay + required = false -------------------------
    def test_hook_is_registered_as_optional_entry_relay(self):
        self.assertIn("Anm2Load,", self.catalog, "HookId 里没有 Anm2Load")
        self.assertRegex(
            self.catalog,
            r"\{HookId::Anm2Load,\s*\"Anm2Load\",\s*HookBackend::EntryRelay,\s*false\}",
            "Anm2Load 必须登记成 EntryRelay + required = false",
        )

    def test_relay_adapter_binds_the_target_and_callback(self):
        self.assertIn("kSpriteLoadOffset", self.adapter, "适配器没有绑定 ANM2::Load 的靶点")
        self.assertIn("kSpriteLoadExpectedBytes", self.adapter, "适配器没有用 16 字节守卫")
        self.assertIn(
            "EntryRelayAnm2LoadCallback", self.adapter, "适配器没有把回调接进 g_hookCallbacks"
        )

    def test_legacy_backend_rejects_the_new_hook(self):
        # 旧 IPS 后端不支持它 ⇒ 必须显式给出"不支持"的答复（否则 -Wswitch 报错，或更糟：
        # 静默落进 default 分支）。这里钉住那条 case。
        self.assertRegex(
            self.exlaunch,
            r"case HookId::ModManagerLoadConfigs:\s*\n\s*//[^\n]*\n\s*case HookId::Anm2Load:",
            "旧后端没有显式拒绝 Anm2Load",
        )

    # ---- 4. 只在"解析器答模组层"时才动手 -----------------------------------
    def test_scan_happens_before_asking_the_resolver(self):
        # 顺序不变式：**先只读地看缓存**，只有"确实有压住模组的那一份"才去问解析器。
        # 这样真正的未命中（缓存里一份都没有）完全不问解析器 —— 那正是绝大多数情况，
        # 而且引擎自己马上会问，我们不必替它问一遍。
        scan = self.impl.index("ScanCandidateEntries(path, length, nullptr, &sawModPrefix)")
        ask = self.impl.index("NoteAnm2LoadResolverAsked();")
        self.assertLess(scan, ask, "必须先只读看缓存，再问解析器")
        # 而且中间要有那道"缓存里一份都没有就直接放行"的提前返回。
        between = self.impl[scan:ask]
        self.assertIn("if (!scan.anyEntry)", between,
                      "看缓存之后必须能直接放行，不能无条件去问解析器")

    def test_eviction_only_happens_for_mod_layer_paths(self):
        # 顺序不变式：问解析器 → 判模组层 → 反推 owner 前缀 →（只有都成立）才作废。
        ask = self.impl.index("NoteAnm2LoadResolverAsked();")
        owner = self.impl.index("FindOwnerPrefix(mounted, ownerPrefix")
        free_mounted = self.impl.index("bindings.freePath(mounted)")
        mod_check = self.impl.index("if (!modLayer)")
        evict = self.impl.index("ScanCandidateEntries(path, length, ownerPrefix)")
        self.assertLess(ask, owner, "必须先问解析器，拿到挂载路径，才谈得上反推 owner")
        # 反推必须**在释放那条挂载路径之前**（拿到的是引擎 `new[]` 出来的缓冲，释放后就是野指针）。
        self.assertLess(owner, free_mounted, "反推 owner 前缀必须在释放挂载路径之前")
        # 而"不是模组层就一份都不动"这道闸必须在**作废之前**。
        self.assertLess(mod_check, evict, "「不是模组层 ⇒ 一份都不动」必须拦在作废之前")
        self.assertLess(owner, evict, "必须先反推 owner 前缀，才轮到你作废")
        # 判模组层的依据是解析器给出的挂载路径里含 `isaac_mods`。
        self.assertIn("isaac_mods", self.impl, "判模组层没有用 isaac_mods")

    def test_owner_entries_are_never_evicted(self):
        # ★ 这条是本设计的关键：**只作废"不是 owner 前缀下"的那一份**。
        # 少了它，每次加载都会连模组自己那份一起作废 ⇒ 下一次变成"不命中 ⇒ 重新开文件"，
        # 等于每次都用文件读换掉一次缓存命中（缓存白设了）。
        #
        # ★ 批次 366：作废动作从"只读扫描里"搬回了回调（因为引擎的 `RemoveReference`
        #   自己会拼挂载点前缀、而且要的是 libc++ 的串对象）；判据也跟着换成新的形状：
        #   ① 扫描只**标记**"有非 owner 条目"；② 回调在看到"只剩 owner 一份"时**提前返回**，
        #   作废那一句必须在那个早退**之后**。
        self.assertIn("bool anyNonOwnerEntry", self.impl, "没有'压住模组的条目'这个判据")
        self.assertIn("if (!underOwner)", self.impl, "没有'属于 owner 前缀的不算数'这道分支")
        block = self.impl[self.impl.index("if (!underOwner)"):]
        self.assertIn(
            "result.anyNonOwnerEntry = true;", block[:200],
            "'不属于 owner 前缀'必须被记进 anyNonOwnerEntry（而不是在那里就动手）",
        )
        tail = self.impl[self.impl.index("if (!stale.anyNonOwnerEntry)"):]
        self.assertLess(
            tail.index("original(anm2, name, loadGraphics);"),
            tail.index("freeUnreferencedEntries(g_Bindings.anmCache)"),
            "只剩 owner 自己那一份时必须提前返回，回收那一句只能在它之后",
        )

    def test_unknown_owner_prefix_is_conservative(self):
        # 反推不出 owner 前缀时**什么都不能动**（宁可这次不修，也不冒误伤的风险）。
        self.assertIn("if (!haveOwner)", self.impl, "没有'反推不出 owner 就不动手'这道分支")
        block = self.impl[self.impl.index("if (!haveOwner)"):]
        # 该分支必须在作废之前返回。
        self.assertLess(block.index("original(anm2, name, loadGraphics);"),
                        block.index("freeUnreferencedEntries(g_Bindings.anmCache)"),
                        "反推不出 owner 时必须提前返回，不得走到回收")

    def test_owner_prefix_is_the_longest_match(self):
        # 取**最长**的匹配前缀：短前缀可能只是长前缀的一部分，取短了会把模组自己那份误判成别人的。
        self.assertIn("prefixLength > best", self.impl, "owner 前缀没有取最长匹配")

    def test_non_gfx_paths_are_ignored(self):
        # 只处理 `gfx/` 开头的内容相对路径（绝对路径与别的资源一律原样放行）。
        self.assertIn('std::memcmp(path, "gfx/", 4)', self.impl)

    # ---- 6. 候选键只按挂载点算，不遍历缓存里的字符串 -----------------------
    def test_candidate_keys_are_computed_from_mount_points(self):
        self.assertIn("ReadMountPoints", self.impl, "没有读挂载点表")
        self.assertIn("HashDjb2", self.impl, "没有用引擎同一个哈希算法算候选键")
        # 引擎在查找前会把 `.png` 改写成 `.pcx`，候选键必须照做（否则算出来的键根本不存在）。
        self.assertIn('std::memcpy(png, ".pcx", 4)', self.impl, "候选键没有做 .png → .pcx 改写")
        # 只读遍历：**扫描函数体内部**不许出现任何写缓存的调用（手工插节点 / 增删引用）。
        # ★ 批次 366：判据从"整份文件里不许出现这些词"收紧成"**函数体里不许出现这些调用**" ——
        #   因为注释里要引用引擎的函数名（`AddReference` 等）来写清根因，整份文件级别的字符串
        #   匹配会把注释也算进去（那是**假阳性**，不是真的写了缓存）。
        start = self.impl.index("ScanResult ScanCandidateEntries(")
        end = self.impl.index("\n}\n", start)
        body = self.impl[start:end]
        for forbidden in ("removeReference(", "freeUnreferencedEntries(", "insert(", "__tree_balance"):
            self.assertNotIn(forbidden, body, f"只读遍历里出现了写缓存的调用：{forbidden}")

    def test_hash_matches_the_engine_algorithm(self):
        # djb2 变体：h = h * 33 + c，初值 5381（`KAGE::Filesys::FileManager::HashDJB2`）。
        self.assertIn("5381", self.impl, "哈希初值不是 5381")
        self.assertRegex(self.impl, r"hash \* 33u \+", "哈希不是 `h * 33 + c` 形状")

    # ---- 7. 回调形状与"没有回退入口就不动" ---------------------------------
    def test_callback_signature_matches_the_target_abi(self):
        self.assertRegex(
            self.impl,
            r'extern "C" void EntryRelayAnm2LoadCallback\(void\* anm2, const void\* name,\s*\n\s*'
            r"std::uint32_t loadGraphics\)",
            "回调形状必须与 `ANM2::Load(std::string const&, bool)` 的 ABI 一致",
        )

    def test_callback_runs_the_original_when_unprepared(self):
        # 没有回退入口 ⇒ 直接返回（绝不假装跑过原��数）；绑定不齐 ⇒ 直接跑原函数。
        self.assertIn("if (original == nullptr)", self.impl)
        self.assertIn("original(anm2, name, loadGraphics);", self.impl)

    # ---- 8. 绑定不齐时"绝不半套使用" ---------------------------------------
    def test_incomplete_bindings_are_cleared(self):
        self.assertRegex(
            self.impl,
            r"if \(!ok\) \{[\s\S]{0,200}g_Bindings = Bindings\{\};",
            "绑定不齐时必须清空绑定（绝不半套使用）",
        )

    # ---- 9. 新 TU 必须显式登记（source/ 根目录不被 wildcard 收）------------
    def test_translation_unit_is_registered(self):
        self.assertIn(
            "CPPFILES += anm2_load_override_hook.cpp",
            MAKEFILE.read_text(encoding="utf-8"),
            "`source/` 根目录下的 TU 必须显式登记进 CPPFILES",
        )

    # ---- 10. 读数面三张表同步 ----------------------------------------------
    def test_reader_tables_are_in_sync(self):
        # ★ 2026-10-07（批次 390）：批次 390 在 `Anm2Load` 后面又加了三条
        # （`ManagerIsAction*`）⇒ 原来断言的字面量 `'Anm2Load',]`（它当时是尾巴）不再成立。
        # 判据改成"`Anm2Load` 这一项在表里"—— 想钉的还是同一件事。
        self.assertIn("'Anm2Load',", self.reader, "HOOK_NAMES 没有加 Anm2Load")
        self.assertIn(
            "'Anm2Load': 'entry_relay_anm2_load'", self.reader, "RELAY_BY_HOOK 没有加 Anm2Load"
        )
        self.assertIn(
            "'entry_relay_anm2_load': 'EntryRelayAnm2LoadCallback'",
            self.reader,
            "SYM_ELF_NAMES 没有把回调符号接上",
        )
        self.assertIn(
            "'g_Anm2LoadOverrideState': "
            "'_ZN5isaac7runtime6bridge23g_Anm2LoadOverrideStateE'",
            self.reader,
            "状态面必须按 mangled 名登记（C++ 命名空间里的变量在 ELF 里就是 mangled 名）",
        )
        self.assertIn("模组覆盖本体资源", self.reader, "读数里没有这一段报告")

    # ---- 11. 状态面字段顺序与结构体一致 ------------------------------------
    def test_state_struct_field_order_is_documented(self):
        # 读数工具按"8 个 u32 连续"读它 ⇒ 结构体必须是 8 个 u32、顺序与注释一致。
        fields = re.search(
            r"struct Anm2LoadOverrideState \{(.*?)\};", self.header, re.S
        )
        self.assertIsNotNone(fields, "头文件里没有 Anm2LoadOverrideState")
        body = fields.group(1)
        names = re.findall(r"std::uint32_t (\w+);", body)
        self.assertEqual(
            names,
            [
                "relayState",
                "relayFailure",
                "callbackCount",
                "resolverAsked",
                "staleFound",
                "evicted",
                "lastPathHash",
                "mountListFlags",
                # ★ 批次 384（2026-10-06）：末尾追加两格 —— `[8]` = **本条中继"第一次被调用"的时刻**
                #   （判据：与 `g_EarlyMountState` 里 `Game::Init` 的时刻比大小 ⇒ 回答"引擎最初那次读
                #    有没有走我们的中继"），`[9]` = 对齐保留。
                #   ★ **只许往后加**（字段顺序即内存顺序，读数工具按下标解码）。
                "callbackFirstTicks",
                "reservedAlign",
            ],
            "状态面字段顺序变了 —— 读数工具的判读表必须同步改",
        )
        # 外部链接（读数工具按符号名读）—— 定义必须在匿名命名空间之外。
        self.assertRegex(
            self.impl,
            r"namespace isaac::runtime::bridge \{\s*\n\s*//[^\n]*\n(?:\s*//[^\n]*\n)*"
            r"Anm2LoadOverrideState g_Anm2LoadOverrideState\{\};",
            "状态面定义必须在匿名命名空间之外（否则没有外部符号，读数读不到）",
        )

    # ---- 12. ★★ 批次 366：挂载点表必须按 8 字节的 `const char*` 读 --------------
    def test_mount_point_table_is_read_as_char_pointers(self):
        self.assertIn(
            "constexpr std::size_t kMountPointEntrySize = 8;",
            self.impl,
            "挂载点表的元素是 8 字节的 `const char*`（见 kAnmCacheMountLoopExpectedBytes 那条守卫）—— "
            "按 24 字节的 `std::string` 读会让整条中继**静默失效**（2026-10-05 真机实测）。",
        )
        self.assertNotIn(
            "kNativeStringSize",
            self.impl,
            "不许再用 24 字节的串对象口径遍历挂载点表 —— 那是上一版的根因。",
        )
        # 遍历必须走 `kMountPointEntrySize`，且必须**先解引用再读 C 串**（`ReadMountPointAt`）。
        self.assertIn("item += kMountPointEntrySize", self.impl, "遍历步长必须是 8")
        self.assertIn("ReadMountPointAt(item", self.impl, "必须从元素里取出 char* 再读 C 串")
        self.assertIn(
            "const std::size_t count = (end - begin) / kMountPointEntrySize;",
            self.impl,
            "条目数必须按 8 字节算",
        )

    # ---- 12b. ★★ 批次 367：树查找必须从 `[map+0x08]`（已经是根）开始，只解一层 ----
    def test_cache_lookup_starts_at_the_root_without_extra_dereference(self):
        start = self.impl.index("bool FindEntryRefCount(")
        end = self.impl.index("\n}\n", start)
        body = self.impl[start:end]
        # 根 = 直接读 `[map + 0x08]`（那个值就是根节点指针）。
        self.assertIn(
            "const std::uintptr_t endNode = map + kAnmCacheMapRootSentinelOffset;",
            body,
            "结束哨兵是**地址** map+0x08（引擎自己 `cmp x26, x27` 比的就是这个地址）",
        )
        self.assertRegex(
            body,
            r"ReadAt\(endNode, &node,",
            "必须**直接**把 `[map+0x08]` 读成根节点 —— 它已经是根，不许再解一层",
        )
        # 旧写法（多解一层：把 [map+8] 当哨兵、再读它的左孩子当根）不许回来。
        self.assertNotIn(
            "&sentinel", body,
            "旧的 `sentinel` 口径就是那个 bug：把已经是根的 [map+8] 又当成哨兵去取左孩子，"
            "导致从根的左孩子开始查、永不比较根自己（真机：中继被调 178 次、问解析器 0 次）。",
        )

    # ---- 12c. ★★ 批次 368：空前缀不能跳过（引擎"最后一次迭代"的键 = 裸路径键）----
    def test_empty_mount_prefix_is_not_skipped(self):
        start = self.impl.index("ScanResult ScanCandidateEntries(")
        end = self.impl.index("\n}\n", start)
        body = self.impl[start:end]
        self.assertNotIn(
            "prefixLength == 0 ||", body,
            "空前缀**不能跳过**：引擎那张表的最后一项就是空串，`Load2` 最后一次迭代算出来的键"
            "就是裸路径 `HashDJB2(<路径>)`，而 `Preload2` 建条目用的正是那个键 —— "
            "跳过它 ⇒ 探到的旧条目永远是 0（真机：中继被调 178 次、问解析器 0 次）。",
        )
        self.assertIn(
            'std::strstr(prefix, "isaac_mods")', body,
            "扫描时要记下这张表里到底有没有模组层（读数用）",
        )

    # ---- 12d. ★★ 批次 368：表里没有模组前缀时不许放弃作废 -----------------------
    def test_missing_owner_prefix_does_not_block_eviction(self):
        block = self.impl[self.impl.index("if (!haveOwner)"):]
        head = block[:600]
        self.assertNotIn(
            "return;", head,
            "反推不出 owner 前缀时**不能**直接返回：引擎那张挂载点表是开机快照、"
            "一条 `isaac_mods` 都没有（设备实测）⇒ 放弃就等于永远不修。",
        )
        self.assertIn("ownerPrefix[0] = '\\0';", head, "应把 owner 前缀置空 ⇒ 每个键都算压着模组的")
        # 空转保护必须在作废之前。
        self.assertIn("AlreadyEvictedThisSession", self.impl, "缺少'同一路径每会话最多作废一次'的保护")

    # ---- 13. ★★ 批次 366：作废那一步必须是"引擎的形状" -------------------------
    def test_live_references_are_never_decremented(self):
        # ★★ 批次 369（真机崩溃定案）：**一律不许调用 `RemoveReference`** —— 它会把活引用减掉，
        #    而引擎自己的小地图 ANM2 手里仍指着那条条目的 `LayerData`（`Load2` 建的是指向它的
        #    LayerState）⇒ 释放后使用 ⇒ `AnimationLayer::RenderFrame` 里 Data Abort。
        #    只允许"回收计数为 0 的条目"（引擎自己的原语，按定义不动活条目）。
        self.assertNotIn(
            "removeReference(",
            self.impl[self.impl.index('extern "C" void EntryRelayAnm2LoadCallback'):],
            "回调里不许再出现 `RemoveReference` 调用（批次 368 的真机崩溃就是它）。",
        )
        self.assertIn(
            "freeUnreferencedEntries(g_Bindings.anmCache)", self.impl,
            "只允许回收计数为 0 的条目。",
        )
        self.assertIn(
            "stale.anyZeroCount", self.impl,
            "回收必须只在「存在计数为 0 的候选项」时发生。",
        )
        self.assertIn(
            "dist/crash-20261005-1259/crash.log", self.impl,
            "崩溃证据（报告路径）必须留在代码注释里 —— 免得后来者又把减引用加回来。",
        )
        # `.pcx` 改写要跟引擎一样**截断**（引擎在 +4 处写 NUL）。
        self.assertIn('png[4] = \'\\0\';', self.impl, "`.png`→`.pcx` 改写必须补上截断（引擎就是这么做的）")


if __name__ == "__main__":
    unittest.main()
