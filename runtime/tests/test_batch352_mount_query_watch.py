"""批次 352（2026-10-04）：非 `.pcx` 挂载查询的**按路径取证** —— 判据与布局两条腿。

## 为什么要有这条门禁

批次 351 的诊断只记**全局计数**（"非 `.pcx` 查询 1342 次、其中 `.anm2` 78 次、
引擎答出模组目录 19 次"），真机读数当场证明它**判不了"某一条具体路径归谁"**：
模组独有的路径必然答模组、本体独有的路径必然答本体，两类都混在那个 19/78 里，
而我们要问的恰恰是第三类 —— **两边都有的共享路径**（minimapi 的
`mods/<dir>/resources/gfx/ui/minimap1.anm2` 与本体 `rom:/rp_patch/resources/gfx/ui/minimap1.anm2` 同名）。

批次 352 因此做两件事，本文件分别钉住：

1. **判据**：`runtime/source/image_mount_query_watch.hpp` 里的纯函数
   —— "这条路径属于哪个桶""该不该主动探测"。真机一轮很贵，这几条必须离线判死；
2. **布局**：`ImagePcxDiagnostics` 从 1196 字节长到 **2100** 字节（字段**只往尾部追加**，
   偏移一旦发布就不再动）。读数工具按**固定偏移**解析，所以"结构体布局"与"工具里的数字"
   必须对得上；这里**从源码逐字段重新累加一遍**（不抄实现里的常量），再拿结果去核工具里那些字面量
   —— 这样"有人在中间插了一个字段"会在这里红，而不是在真机上读出一堆看着像数据的垃圾。
"""

import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
BRIDGE = SOURCE / "image_pcx_bridge_hook.cpp"
WATCH_HEADER = SOURCE / "image_mount_query_watch.hpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"

# 352/353 那两段的字段 → 期望偏移（见 `_derive_struct_offsets`；这里是"被核对的一方"）。
EXPECTED_352_OFFSETS = {
    "mountOtherModWins": 1196,
    "mountOtherNotMod": 1200,
    "minimap1Calls": 1204,
    "minimap1ModWins": 1208,
    "minimap2Calls": 1212,
    "minimap2ModWins": 1216,
    "minimap1LastQuery": 1220,
    "minimap1LastAnswer": 1348,
    "minimap2LastQuery": 1508,
    "minimap2LastAnswer": 1636,
    "sharedProbeRuns": 1796,
    "sharedProbeModWin": 1800,
    "sharedProbeFirstModWin": 1804,
    "sharedProbeQuery": 1808,
    "sharedProbeAnswer": 1936,
    "reserved352": 2096,
    # ── 批次 353 ────────────────────────────────────────────────────────────────
    "modMountCount": 2100,
    "modMountDirectories": 2104,
    "otherRingCount": 2680,
    "otherRingPath": 2684,
    "otherRingAnswer": 3212,
    "sharedPathProbes": 3932,
    "reserved353": 4892,
    # ── 批次 354 ────────────────────────────────────────────────────────────────
    "modMountStatus": 4896,
    "modMountFailedLeaf": 4944,
    "reserved354": 4992,
    # ── 批次 356 ────────────────────────────────────────────────────────────────
    "mountOtherModWinsReal": 5000,
    "modMountTimeProbeRuns": 5004,
    "modMountTimeProbeModWin": 5008,
    "modMountTimeProbeAnswer": 5012,
    "reserved356": 5172,
    # ── 批次 357 ────────────────────────────────────────────────────────────────
    "mountVisibilityBitmap": 5176,
    "mountCheckpointRuns": 5180,
    "rebuildRelayInstalled": 5184,
    "remountAttempted": 5188,
    "remountStatus": 5192,
    "remountProbeModWin": 5196,
    "remountProbeAnswer": 5200,
    "reserved357": 5360,
    # ── 批次 358 ────────────────────────────────────────────────────────────────
    "rebuildRelayVerifyFailure": 5368,
    "rebuildRelayTargetBytes": 5372,
    "rebuildRelayStubBytes": 5388,
    "reserved358": 5404,
    # ── 批次 359 ────────────────────────────────────────────────────────────────
    "entryRelayRebuildInstalled": 5408,
    "entryRelayRebuildFailure": 5412,
    "entryRelayRebuildCalls": 5416,
    "reserved359": 5420,
    # ── 批次 360 ────────────────────────────────────────────────────────────────
    "remountWatchdogChecks": 5424,
    "remountHealCount": 5428,
    "reserved360": 5432,
    # ── 批次 361 ────────────────────────────────────────────────────────────────
    "probeSeq": 5440,
    "probeModCount": 5456,
    "lateTrialTick": 5472,
    "lateSharedBeforeModWin": 5476,
    "lateSharedAfterModWin": 5480,
    "lateModOnlyAfterModWin": 5484,
    "lateSharedBeforeAnswer": 5488,
    "lateSharedAfterAnswer": 5648,
    "reserved361": 5808,
}
EXPECTED_STRUCT_SIZE = 5816
# 嵌套的小结构体（读数工具按 +0/+4/+8/+12/+16/+80 解析它，每条 240 字节）。
EXPECTED_PROBE_RECORD_OFFSETS = {
    "runs": 0,
    "modWins": 4,
    "lastModWin": 8,
    "firstModWin": 12,
    "query": 16,
    "answer": 80,
}
EXPECTED_PROBE_RECORD_SIZE = 240

DRIVER = textwrap.dedent(
    r"""
    #include "image_mount_query_watch.hpp"

    #include <cstdio>
    #include <cstring>

    using isaac::runtime::bridge::ClassifyMountQueryPath;
    using isaac::runtime::bridge::LastPathSegmentEquals;
    using isaac::runtime::bridge::MountQueryWatch;
    using isaac::runtime::bridge::ShouldRunSharedPathProbe;

    int main() {
        int failures = 0;
        const auto check = [&failures](bool actual, bool expected, const char* what) {
            if (actual != expected) {
                std::printf("FAILED_CHECK %s\n", what);
                ++failures;
            }
        };

        // ── 1. 最后一段相等（按段，不按子串）───────────────────────────────────
        check(LastPathSegmentEquals("gfx/ui/minimap1.anm2", "minimap1.anm2"), true,
              "plain relative path");
        check(LastPathSegmentEquals("rom:/rp_patch/resources/gfx/ui/minimap1.anm2", "minimap1.anm2"),
              true, "engine answer path");
        check(LastPathSegmentEquals("minimap1.anm2", "minimap1.anm2"), true,
              "whole string is the segment");
        check(LastPathSegmentEquals("gfx/ui/foo_minimap1.anm2", "minimap1.anm2"), false,
              "must not match a longer file name (substring trap)");
        check(LastPathSegmentEquals("gfx/ui/minimap1.anm2.bak", "minimap1.anm2"), false,
              "trailing junk is a different file");
        check(LastPathSegmentEquals("gfx\\ui\\minimap1.anm2", "minimap1.anm2"), true,
              "backslash separator (PC mods write either)");
        check(LastPathSegmentEquals(nullptr, "minimap1.anm2"), false, "null path");
        check(LastPathSegmentEquals("gfx/ui/minimap1.anm2", nullptr), false, "null segment");
        check(LastPathSegmentEquals("gfx/ui/minimap1.anm2", ""), false, "empty segment");

        // ── 2. 分桶 ────────────────────────────────────────────────────────────
        check(ClassifyMountQueryPath("gfx/ui/minimap1.anm2") == MountQueryWatch::Minimap1, true,
              "bucket minimap1");
        check(ClassifyMountQueryPath("rom:/isaac_mods/mods/x/resources/gfx/ui/minimap1.anm2")
                  == MountQueryWatch::Minimap1, true, "bucket minimap1 from mod mount");
        check(ClassifyMountQueryPath("gfx/ui/minimap2.anm2") == MountQueryWatch::Minimap2, true,
              "bucket minimap2");
        check(ClassifyMountQueryPath("gfx/ui/minimap3.anm2") == MountQueryWatch::None, true,
              "minimap3 is not watched");
        check(ClassifyMountQueryPath("gfx/1000.007_Blood Splat.anm2") == MountQueryWatch::None,
              true, "unrelated anm2 stays in None");
        check(ClassifyMountQueryPath(nullptr) == MountQueryWatch::None, true, "null path -> None");
        check(ClassifyMountQueryPath("") == MountQueryWatch::None, true, "empty path -> None");

        // ── 3. 主动探测的时机 ──────────────────────────────────────────────────
        check(ShouldRunSharedPathProbe(0, 512), false, "never probe before the first query");
        check(ShouldRunSharedPathProbe(1, 512), true, "first query probes once");
        check(ShouldRunSharedPathProbe(2, 512), false, "second query does not probe");
        check(ShouldRunSharedPathProbe(512, 512), true, "periodic probe at the period");
        check(ShouldRunSharedPathProbe(1024, 512), true, "periodic probe repeats");
        check(ShouldRunSharedPathProbe(1, 0), true, "period 0 still probes the first query only");
        check(ShouldRunSharedPathProbe(512, 0), false, "period 0 disables the periodic probe");

        // ── 4. 探测路径表（353 的核心判据面：少一条就分不开甲'/乙'）────────────────
        check(isaac::runtime::bridge::kSharedPathProbeQueries.size() == 4, true,
              "probe table has exactly four entries");
        for (std::size_t i = 0; i < isaac::runtime::bridge::kSharedPathProbeQueries.size(); ++i) {
            const char* query = isaac::runtime::bridge::kSharedPathProbeQueries[i];
            check(query != nullptr && query[0] != '\0', true, "probe query is non-empty");
            for (std::size_t j = i + 1; j < isaac::runtime::bridge::kSharedPathProbeQueries.size(); ++j) {
                check(std::strcmp(query, isaac::runtime::bridge::kSharedPathProbeQueries[j]) != 0,
                      true, "probe queries are distinct");
            }
        }

        if (failures != 0) {
            std::printf("MOUNT_QUERY_WATCH_FAILURES %d\n", failures);
            return 1;
        }
        std::printf("MOUNT_QUERY_WATCH_CHECKS_PASSED\n");
        return 0;
    }
    """
)


def host_compiler():
    for candidate in ("clang++", "g++"):
        if shutil.which(candidate):
            return candidate
    return None


MEMBER = re.compile(r"^\s*([A-Za-z_]\w*(?:::\w+)*)\s+([A-Za-z_]\w*)\s*((?:\[\d+\])*)\s*;")


def _derive_members(struct_name, type_sizes):
    """从一个结构体定义里**逐字段累加**出偏移与总大小（不抄实现里的常量）。

    意义：如果有人把新字段插进结构体中间（或改了数组维度），累加出来的偏移会与工具里的字面量
    对不上 ⇒ 在门禁里红，而不是在真机上按旧偏移读出一堆看着像数据的垃圾。
    `type_sizes` 只认"元素的字节数"；不带下标的成员按元素大小算，带下标的再把各维相乘。
    """
    text = BRIDGE.read_text(encoding="utf-8")
    start = text.index(f"struct {struct_name} {{")
    end = text.index("\n};", start)
    offsets = {}
    offset = 0
    for line in text[start:end].splitlines():
        match = MEMBER.match(line)
        if match is None:
            continue
        type_name, name, dims_text = match.groups()
        dims = [int(d) for d in re.findall(r"\[(\d+)\]", dims_text)]
        count = 1
        for dim in dims:
            count *= dim
        offsets[name] = offset
        offset += type_sizes[type_name] * count
    return offsets, offset


def _derive_struct_offsets():
    record_offsets, record_size = _derive_members("SharedPathProbeRecord",
                                                 {"std::uint32_t": 4, "char": 1})
    assert record_offsets == EXPECTED_PROBE_RECORD_OFFSETS, record_offsets
    assert record_size == EXPECTED_PROBE_RECORD_SIZE, record_size
    return _derive_members("ImagePcxDiagnostics",
                           {"std::uint32_t": 4, "char": 1,
                            "SharedPathProbeRecord": record_size})


class Batch352MountQueryWatchTests(unittest.TestCase):
    def test_classifier_behaviour(self):
        """判据本身：按"最后一段"分桶、探测时机 —— 在宿主上真跑一遍。"""
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("需要宿主 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="mount-watch-") as temporary:
            directory = Path(temporary)
            source = directory / "mount_watch.cpp"
            binary = directory / "mount_watch"
            source.write_text(DRIVER, encoding="utf-8")
            compile_result = subprocess.run(
                [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                 "-I", str(SOURCE), str(source), "-o", str(binary)],
                capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)
            self.assertIn("MOUNT_QUERY_WATCH_CHECKS_PASSED", run_result.stdout)

    def test_struct_layout_matches_reader_offsets(self):
        """布局腿：源码累加出来的偏移 == 期望值 == 读数工具里用的字面量。"""
        offsets, total = _derive_struct_offsets()
        for name, expected in EXPECTED_352_OFFSETS.items():
            self.assertIn(name, offsets, f"结构体里找不到字段 {name}")
            self.assertEqual(offsets[name], expected,
                             f"{name} 的偏移变了（{offsets[name]} != {expected}）"
                             " —— 字段只能往尾部追加，且必须同步读数工具")
        self.assertEqual(total, EXPECTED_STRUCT_SIZE,
                         f"ImagePcxDiagnostics 大小变了：{total} != {EXPECTED_STRUCT_SIZE}")

        # 编译期那一条 static_assert 必须与这里算出来的一致（两处口径不许各说各话）。
        bridge = BRIDGE.read_text(encoding="utf-8")
        self.assertIn(f"sizeof(ImagePcxDiagnostics) == {EXPECTED_STRUCT_SIZE}", bridge)

        # 读数工具：读取长度必须**够**（字数 × 8 ≥ 结构体大小），且用到的偏移就是上面那些。
        reader = READER.read_text(encoding="utf-8")
        match = re.search(r"\('image_pcx_diag', base \+ SYMS\['image_pcx_diag'\], (\d+)\)", reader)
        self.assertIsNotNone(match, "读数工具里找不到 image_pcx_diag 的读取长度")
        words = int(match.group(1))
        self.assertGreaterEqual(words * 8, EXPECTED_STRUCT_SIZE,
                                f"读取长度 {words} 个字（{words * 8} 字节）读不全 {EXPECTED_STRUCT_SIZE} 字节")
        # 工具里**显式写死**的那些偏移，必须就是源码累加出来的偏移（逐个字段核对，不是看数量）。
        # 其余字段（`mountOtherNotMod` / `minimap1Calls` / … / `sharedProbeFirstModWin`）由
        # 上面两组 `unpack_from` 的**连续 u32** 覆盖 —— 组宽对不对由下一条断言保证。
        anchors = [
            (f"_struct.unpack_from('<6I', diag_raw, {offsets['mountOtherModWins']})",
             "352 前六个 u32 的起点（mountOtherModWins）"),
            (f"_diag_str({offsets['minimap1LastQuery']}, 128)", "minimap1LastQuery"),
            (f"_diag_str({offsets['minimap1LastAnswer']}, 160)", "minimap1LastAnswer"),
            (f"_diag_str({offsets['minimap2LastQuery']}, 128)", "minimap2LastQuery"),
            (f"_diag_str({offsets['minimap2LastAnswer']}, 160)", "minimap2LastAnswer"),
            (f"_struct.unpack_from('<3I', diag_raw, {offsets['sharedProbeRuns']})",
             "探测三格 u32 的起点（sharedProbeRuns）"),
            (f"_diag_str({offsets['sharedProbeQuery']}, 128)", "sharedProbeQuery"),
            (f"_diag_str({offsets['sharedProbeAnswer']}, 160)", "sharedProbeAnswer"),
            # ── 批次 353 ────────────────────────────────────────────────────────
            (f"_struct.unpack_from('<I', diag_raw, {offsets['modMountCount']})", "模组名单计数"),
            (f"{offsets['modMountDirectories']} + 48 * i", "模组目录名数组"),
            (f"_struct.unpack_from('<I', diag_raw, {offsets['otherRingCount']})", "环形历史计数"),
            (f"{offsets['otherRingPath']} + 88 * slot", "环形历史的路径"),
            (f"{offsets['otherRingAnswer']} + 120 * slot", "环形历史的回答"),
            (f"{offsets['sharedPathProbes']} + 240 * i", "四条探测路径的记录数组"),
            (f"off + {EXPECTED_PROBE_RECORD_OFFSETS['query']}", "探测记录里的 query 偏移"),
            (f"off + {EXPECTED_PROBE_RECORD_OFFSETS['answer']}", "探测记录里的 answer 偏移"),
            # ── 批次 354 ────────────────────────────────────────────────────────
            (f"_struct.unpack_from('<I', diag_raw, {offsets['modMountStatus']} + 4 * i)",
             "挂载状态码表"),
            (f"_struct.unpack_from('<I', diag_raw, {offsets['modMountFailedLeaf']} + 4 * i)",
             "失败叶子表"),
            # ── 批次 356 ────────────────────────────────────────────────────────
            (f"_struct.unpack_from('<3I', diag_raw, {offsets['mountOtherModWinsReal']})",
             "排除回声的计数 + 检查点两格"),
            (f"_diag_str356({offsets['modMountTimeProbeAnswer']}, 160)", "刚挂完检查点的回答"),
            # ── 批次 357 ────────────────────────────────────────────────────────
            (f"_struct.unpack_from('<6I', diag_raw, {offsets['mountVisibilityBitmap']})",
             "时间轴位图起头的六个 u32"),
            (f"_diag_str357({offsets['remountProbeAnswer']}, 160)", "重挂之后那次的回答"),
            # ── 批次 358 ────────────────────────────────────────────────────────
            (f"_struct.unpack_from('<I', diag_raw, {offsets['rebuildRelayVerifyFailure']})",
             "重建中继的失败码"),
            (f"diag_raw[{offsets['rebuildRelayTargetBytes']}:{offsets['rebuildRelayStubBytes']}].hex()",
             "目标处实际 16 字节"),
            (f"diag_raw[{offsets['rebuildRelayStubBytes']}:{offsets['reserved358']}].hex()",
             "代码洞桩处实际 16 字节"),
            # ── 批次 359 ────────────────────────────────────────────────────────
            (f"_struct.unpack_from('<3I', diag_raw, {offsets['entryRelayRebuildInstalled']})",
             "活路径上的三格（安装结果/失败码/包装调用数）"),
            # ── 批次 360 ────────────────────────────────────────────────────────
            (f"_struct.unpack_from('<2I', diag_raw, {offsets['remountWatchdogChecks']})",
             "自愈看门狗的两格（检查次数/补挂次数）"),
            # ── 批次 361 ────────────────────────────────────────────────────────
            (f"_struct.unpack_from('<4I', diag_raw, {offsets['probeSeq']})", "探测序号表"),
            (f"_struct.unpack_from('<4I', diag_raw, {offsets['probeModCount']})", "探测时的模组数表"),
            (f"_diag_str361({offsets['lateSharedBeforeAnswer']}, 160)", "重挂前共享路径的回答"),
            (f"_diag_str361({offsets['lateSharedAfterAnswer']}, 160)", "重挂后共享路径的回答"),
        ]
        for needle, what in anchors:
            self.assertIn(needle, reader, f"读数工具里没有按 {what} 的偏移解析：{needle!r}")
        # 组宽必须刚好够到下一条显式锚点（`<6I` 从 1196 起 = 24 字节，正好抵到 1220）。
        self.assertEqual(offsets["minimap1LastQuery"] - offsets["mountOtherModWins"], 6 * 4,
                         "352 前六个 u32 不再连续 —— 读数工具的 '<6I' 会读串位")
        self.assertEqual(offsets["sharedProbeQuery"] - offsets["sharedProbeRuns"], 3 * 4,
                         "探测三格 u32 不再连续 —— 读数工具的 '<3I' 会读串位")
        # 353：探测记录数组的**步长**必须就是嵌套结构体的大小（工具里按 240 跨步）。
        self.assertEqual(offsets["reserved353"] - offsets["sharedPathProbes"],
                         4 * EXPECTED_PROBE_RECORD_SIZE,
                         "sharedPathProbes 的步长变了 —— 读数工具的 '+ 240 * i' 会读串位")

    def test_reader_actually_prints_the_reading(self):
        """★ 技能 §3 那条：设施做了 ≠ 判据接上了 —— 读数工具必须**真的打印**这一段。"""
        reader = READER.read_text(encoding="utf-8")
        self.assertIn("352：按路径取证", reader, "读数工具没有 352 的打印段")
        for needle in ("主动探测", "minimap1.anm2", "minimap2.anm2"):
            self.assertIn(needle, reader, f"打印段里缺少 {needle!r}")
        # "缺就说缺"：本构建没有 / 这份读数没有，两种情形必须分开报。
        self.assertIn("本构建没有 352 的", reader)
        self.assertIn("这份读数里没有 352 的字段", reader)

    def test_relay_wires_the_watch_and_the_probe(self):
        """接线腿：中继里真的调了分桶与主动探测，且探测走**原函数**。"""
        bridge = BRIDGE.read_text(encoding="utf-8")
        callback = bridge.index("EntryRelayContentGetMountedFilePathCallback(void* self, const char* path) {")
        body = bridge[callback:]
        classify = body.index("bridge_ns::ClassifyMountQueryPath(path)")
        probe_gate = body.index("bridge_ns::ShouldRunSharedPathProbe(")
        probe_call = body.index("RunSharedPathProbes(self, original)")
        release = body.index("return static_cast<char*>(mountedOwner.Release());  // 只补 `.pcx` 这一类")
        self.assertLess(classify, release, "分桶必须发生在非 `.pcx` 分支里")
        self.assertLess(probe_gate, probe_call, "探测必须先过时机判定")
        self.assertLess(probe_call, release, "探测必须在返回之前跑")
        # ★ 探测必须走**原函数**（不是递归进我们自己的中继）—— 与 `.png` 探测同一条纪律。
        self.assertIn("original(self, query)", bridge, "探测必须用原函数入口")
        self.assertNotIn("EntryRelayContentGetMountedFilePathCallback(self", body)
        # ★★★ 批次 378（2026-10-05）：这一步（`ManifestLoadStep::Mounts`）以前是"登记内容挂载点
        #   并记下登记结果"。模组目录挂载这条机制已被 **PC 的资源层重定向**取代 ⇒ 这里改成钉住
        #   "**发布重定向清单**"，并且**不许**再出现任何挂载调用（判定意图不变：模组资源必须在
        #   模组脚本之前就对引擎可见）。取证见 `docs/分析-模组挂载机制与371没音乐定案-20261005.md`。
        hook_manager = (SOURCE / "hook_manager.cpp").read_text(encoding="utf-8")
        mount_step = hook_manager.index("case ManifestLoadStep::Mounts: {")
        publish = hook_manager.index(
            "isaac::runtime::bridge::PublishModResourceRedirectList(roots, rootCount)", mount_step)
        content_step = hook_manager.index("case ManifestLoadStep::Content: {", mount_step)
        self.assertLess(publish, content_step, "重定向清单必须在这一步发布（内容步之前）")
        # 撤除的那两处：登记与"失败在哪个叶子"的记账，都不许再出现在这条加载链上。
        self.assertNotIn("g_ContentMountService.RegisterMod(", hook_manager,
                         "挂载机制已撤除（376）：不许再登记内容挂载点")
        self.assertNotIn("bridge::RecordModMountResult(", hook_manager,
                         "挂载机制已撤除（376）：不许再有挂载结果记账")
        # 服务本身还在（它是纯逻辑、有单测），但**不再有生产调用点** —— 它的 accessor 照旧存在。
        service_hpp = (ROOT / "runtime" / "src" / "application" / "mod"
                       / "content_mount_service.hpp").read_text(encoding="utf-8")
        service_cpp = (ROOT / "runtime" / "src" / "application" / "mod"
                       / "content_mount_service.cpp").read_text(encoding="utf-8")
        self.assertIn("last_failed_leaf()", service_hpp)
        self.assertIn("lastFailedLeaf_ = ", service_cpp)
        # ★★ 354 的核心判据面：探测表里必须有"应用根相对"形式（换键形状，用来分开
        #   "挂载点不在表里"与"叶子相对这种键匹配不上"）。
        watch = WATCH_HEADER.read_text(encoding="utf-8")
        table = watch[watch.index("kSharedPathProbeQueries = {"):]
        table = table[:table.index("};")]
        # ★★ 356 的核心：**同一份文件、两种问法**（叶子相对 vs 应用根相对）。
        self.assertIn('"sprite/gt/gt_ui.anm2"', table, "缺少'叶子相对'的那一条")
        self.assertIn('"isaac_mods/mods/goodtripfixed/resources/sprite/gt/gt_ui.anm2"', table,
                      "缺少'同一份文件的应用根相对'那条 —— 没有它，'叶子相对答空'说明不了任何事")
        self.assertIn('"gfx/ui/minimap1.anm2"', table)
        self.assertIn('"isaac_mods/mods/', table,
                      "探测表里缺少'应用根相对'形式 —— 那就分不开'不可见'与'键形状不对'")
        # ★★★ 批次 378（2026-10-05）：下面四刀（356/357/360/361）原来钉的是"挂载收尾 / 内容步
        #   收尾 / 第一个 update 回调 / 自愈补挂 / 晚点重挂试验"这些**挂载机制专用**的探测调用点
        #   **必须接上**。模组目录挂载被 PC 的资源层重定向取代之后，加载链上**没有挂载点可探**了
        #   ⇒ 判据翻面：这些调用点不许再出现在加载链上（探针函数本身还在桥里，是纯记数）。
        #   取证与裁定见 `docs/分析-模组挂载机制与371没音乐定案-20261005.md`。
        #   ★ 判据只看**代码**：撤除说明本身就在 `hook_manager.cpp` 的注释里逐字提到这几个名字，
        #     不剥注释会先命中注释（本仓"判据只看代码"那条纪律）。
        hook_code = re.sub(r"//[^\n]*", "", hook_manager)
        for gone in ("bridge::ProbeMountVisibilityAfterMounting()",
                     "bridge::NoteMountVisibilityCheckpoint(1)",
                     "bridge::NoteMountVisibilityCheckpoint(2)",
                     "bridge::EnsureModMountsAlive()",
                     "bridge::RunLateRemountTrial()"):
            self.assertNotIn(gone, hook_code,
                             f"挂载机制已撤除（376）：加载链上不许再调 `{gone}`")
        #   中继那一段里用的是函数内的命名空间别名 `bridge_ns`（与同段其它调用一致）。
        self.assertIn("bridge_ns::NoteMountVisibilityCheckpoint(3)", bridge,
                      "第一次非 `.pcx` 查询那一刀没接上")
        # 360 起"补挂之后立刻复验"这一步挪进桥里（`EnsureModMountsAlive` 内部调用）。
        # ★ 376：桥里这段代码还在（纯记数），但**生产路径上已经没有调用点** —— 它是历史面。
        self.assertIn("ProbeMountVisibilityAfterRemount();", bridge,
                      "重挂之后没有立刻再问一次 —— 那就验证不了修法")
        self.assertIn("service->RemountAll()", bridge,
                      "自愈补挂没有真的调 RemountAll")
        self.assertIn("lateSharedBeforeModWin", bridge, "晚点试验没记'重挂前'那一半")
        self.assertIn("probeModCount", bridge, "探测没有记'当时的模组数' —— 那就还会把'还没挂'当成'丢了'")
        # ★★ 357：**"没跑"与"没装上"必须分开** —— 安装结果要留成一格。
        adapter = (ROOT / "runtime" / "src" / "infrastructure" / "exlaunch"
                   / "exlaunch_hook_adapter.cpp").read_text(encoding="utf-8")
        self.assertIn("NoteRebuildMountPointsRelayInstalled(ok)", adapter,
                      "重建挂载点中继的安装结果没有被记下来")
        # ★★ 358：光知道"没装上"不足以行动 —— **失败码与现场字节**也要接上。
        self.assertIn("bridge::NoteRebuildRelayVerifyDetail(", hook_manager,
                      "失败现场没有交给诊断 —— 那还是只知道'没装上'")
        self.assertIn("&failure)", hook_manager, "验证函数没有接收失败码")
        self.assertIn("kRelayVerifyTargetBytes", hook_manager, "失败码枚举没接上")
        # ★★ 359：**探针必须在活的路径上** —— 上一批记的是死代码（挂点目录把后端定成 EntryRelay）。
        entry_adapter = (ROOT / "runtime" / "src" / "infrastructure" / "relay"
                         / "entry_relay_hook_adapter.cpp").read_text(encoding="utf-8")
        self.assertIn("NoteRebuildMountPointsEntryRelay(", entry_adapter,
                      "活路径（入口中继适配器）上的安装结果没留痕")
        self.assertIn("bridge::NoteRebuildMountPointsEntryRelayCallbackFired()", hook_manager,
                      "包装被调用几次没记 —— 那就分不开'引擎没重建'与'我们没装上'")
        catalog = (ROOT / "runtime" / "src" / "domain" / "runtime"
                   / "hook_catalog.hpp").read_text(encoding="utf-8")
        self.assertIn('{HookId::RebuildMountPoints, "RebuildMountPoints", HookBackend::EntryRelay',
                      catalog, "挂点目录里的后端变了 —— 那死代码那条路可能又活了，探针位置要跟着改")
        for line in table.splitlines():
            match = re.search(r'"([^"]+)"', line)
            if match is not None:
                self.assertLess(len(match.group(1)), 64,
                                f"探测路径太长，会被记录里的 query[64] 截断：{match.group(1)!r}")


if __name__ == "__main__":
    unittest.main()
