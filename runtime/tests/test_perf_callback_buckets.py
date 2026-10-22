"""门禁：**按 (事件 id, 属主模组) 分开的回调耗时桶**（批次 086，2026-09-19）。

## 为什么有这条门禁

084/085 的常驻性能面只能回答"回调一共花了多久"。真机实测出来的是
"物品旁边占主线程 22.3%、走开 2.2%"——但**答不出是哪一个回调**：当时每帧约 11 次回调，
等于 11 个嫌疑人。批次 086 把每个样本再按 **(事件 id, 属主模组)** 记一个桶，
读数工具据此打印"最贵的回调"。

## 这条门禁钉住什么（两边都要，缺一条读数就会骗人）

**A. 记账行为（真编译、真跑，不是读代码）**：
1. 同键累加次数、累加 tick、`maxTicks` 取最大；
2. 不同键各占一个槽；
3. 表满时**不覆盖已有桶**，只把溢出次数加一，并返回 `false`；
4. 空槽只用一次（填过的槽不会被后来的键复用）。

**B. 打包与布局口径（读数工具按字节解，错一位就把名字标错回调）**：
5. `RuntimePerfCallbackKey`：低 32 位 = id、bit32..47 = `owner.index`、bit48..63 = `generation`；
6. 桶结构 = 4 个 u64，顺序 `key / count / ticks / maxTicks`，每项 32 字节；
7. 读数工具的 `PERF_BUCKET_COUNT` / `PERF_BUCKET_BYTES` 与头文件常量一致，
   且请求的字节数正好是"个数 × 每项字节"（少读会截断、多读会把别的变量当桶）。

**C. 设备侧形状**：数组由**定义它的那个 TU**持有、`extern "C"` + hidden（不碰数据 GOT、
`nm` 里是裸名），且 `lua_runtime.cpp` 的回调计时块里真的调了记账函数。
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
HEADER = RUNTIME / "src" / "interfaces" / "lua" / "runtime_perf.hpp"
LUA_RUNTIME = RUNTIME / "source" / "lua_runtime.cpp"
TOOL = ROOT / "tools" / "read_device_state_via_gdb.py"


def host_compilers() -> tuple[str, str] | None:
    """(C 编译器, C++ 编译器)；缺任何一个就整体 skip，不伪装成通过。"""
    import shutil

    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None

HARNESS = r'''
#include "interfaces/lua/runtime_perf.hpp"

#include <cstdio>

using isaac::runtime::RecordRuntimePerfCallbackSample;
using isaac::runtime::RuntimePerfCallbackBucket;
using isaac::runtime::RuntimePerfCallbackKey;
namespace perf = isaac::runtime;

int main() {
    int failures = 0;
    auto expect = [&failures](bool condition, const char* what) {
        if (!condition) {
            std::printf("FAIL %s\n", what);
            ++failures;
        }
    };

    // ---- 5/6. 打包口径与布局 -------------------------------------------------
    const std::uint64_t key = RuntimePerfCallbackKey(2, 0x1234, 0xABCD);
    expect((key & 0xFFFFFFFFULL) == 2ULL, "id 落在低 32 位");
    expect(((key >> 32) & 0xFFFFULL) == 0x1234ULL, "owner.index 落在 bit32..47");
    expect((key >> 48) == 0xABCDULL, "owner.generation 落在 bit48..63");
    expect(perf::kRuntimePerfBucketBytes == 48, "桶每项 48 字节（4 × u64 + 直方图 4 × u32）");
    expect(perf::kRuntimePerfBucketCount == 64, "桶个数 64");

    // 按键查桶（批次 095 起记账用**散列探测** ⇒ 不能再按槽位下标断言，必须按键找）。
    auto findBucket = [](const RuntimePerfCallbackBucket* table, std::size_t capacity,
                         std::uint64_t wanted) -> const RuntimePerfCallbackBucket* {
        for (std::size_t index = 0; index < capacity; ++index) {
            if (table[index].count != 0 && table[index].key == wanted) {
                return &table[index];
            }
        }
        return nullptr;
    };

    // ---- 1/2/3/4. 记账行为（按键断言：散列之后槽位下标不再稳定）----------------
    {
        RuntimePerfCallbackBucket buckets[8] = {};
        std::uint64_t overflow = 0;
        const std::uint64_t keyUpdate = RuntimePerfCallbackKey(1, 2, 1);
        const std::uint64_t keyRender = RuntimePerfCallbackKey(2, 3, 1);
        const std::uint64_t keyExtra = RuntimePerfCallbackKey(2, 4, 1);
        const std::uint64_t keyTooMany = RuntimePerfCallbackKey(35, 9, 1);

        expect(RecordRuntimePerfCallbackSample(buckets, 8, keyUpdate, 250, &overflow), "第一笔进桶");
        expect(RecordRuntimePerfCallbackSample(buckets, 8, keyRender, 300, &overflow), "第二笔进桶");
        // 同一键的**后一笔更小**：`maxTicks` 必须保住 250（写成"最后一次覆盖"就会红）。
        expect(RecordRuntimePerfCallbackSample(buckets, 8, keyUpdate, 100, &overflow), "重复键进桶");
        expect(RecordRuntimePerfCallbackSample(buckets, 8, keyExtra, 7, &overflow), "第三个键进桶");

        const RuntimePerfCallbackBucket* updateBucket = findBucket(buckets, 8, keyUpdate);
        const RuntimePerfCallbackBucket* renderBucket = findBucket(buckets, 8, keyRender);
        const RuntimePerfCallbackBucket* extraBucket = findBucket(buckets, 8, keyExtra);
        expect(updateBucket != nullptr, "按 key 必须能找到那一条");
        expect(updateBucket != nullptr && updateBucket->count == 2, "同键合并成一条（不是两条）");
        expect(updateBucket != nullptr && updateBucket->ticks == 350, "同键累加 tick");
        expect(updateBucket != nullptr && updateBucket->maxTicks == 250,
               "maxTicks 取最大而不是最后一次");
        expect(renderBucket != nullptr && renderBucket->count == 1 && renderBucket->ticks == 300 &&
               renderBucket->maxTicks == 300, "不同键各占一条");
        expect(extraBucket != nullptr && extraBucket->count == 1, "第三条也在表里");
        std::size_t occupied = 0;
        std::uint32_t binTotal = 0;
        for (const auto& bucket : buckets) {
            occupied += bucket.count != 0 ? 1 : 0;
            for (const auto& value : bucket.bins) {
                binTotal += value;
            }
        }
        expect(occupied == 3, "三个键必须正好占三条（散列不许把同一个键拆成两条）");
        expect(binTotal == 4, "直方图各档之和 == 总样本数");

        // 表满：不覆盖已有桶，只记溢出，并返回 false。
        RuntimePerfCallbackBucket two[2] = {};
        std::uint64_t smallOverflow = 0;
        RecordRuntimePerfCallbackSample(two, 2, keyUpdate, 7, &smallOverflow);
        RecordRuntimePerfCallbackSample(two, 2, keyRender, 9, &smallOverflow);
        expect(!RecordRuntimePerfCallbackSample(two, 2, keyTooMany, 999, &smallOverflow),
               "表满返回 false");
        expect(smallOverflow == 1, "表满只加溢出计数");
        expect(two[0].count + two[1].count == 2, "表满不许破坏已有样本");
        expect(!RecordRuntimePerfCallbackSample(nullptr, 0, keyUpdate, 1, nullptr), "空表不崩");
    }

    // tick 频率必须是常量（读 `cntfrq_el0` 会陷入，批次 081/082）。
    expect(perf::RuntimePerfTicksPerSecond() == 19200000ULL, "19.2 MHz 常量");

    // ★★ 批次 241：直方图三档上界**按 tick 核死**（19.2 tick = 1 µs ⇒ 1 ms = 19 200 tick）。
    // 这一条是补一个真机事故的判据：原来后两档写成 `1 * 19200000` / `5 * 19200000`
    // （= 1 秒 / 5 秒）⇒ 毫秒级样本全掉进第二档，"<5ms / >=5ms" 永远 0%，
    // 与同一个桶里的 `ticks`/`maxTicks` 自相矛盾。
    expect(perf::kRuntimePerfBinBounds[0] == 4800ULL, "第一档上界 = 250 µs = 4800 tick");
    expect(perf::kRuntimePerfBinBounds[1] == 19200ULL, "第二档上界 = 1 ms = 19200 tick");
    expect(perf::kRuntimePerfBinBounds[2] == 96000ULL, "第三档上界 = 5 ms = 96000 tick");
    {
        std::uint32_t bins[4] = {0, 0, 0, 0};
        perf::RecordRuntimePerfBin(bins, 100ULL * 19200ULL / 1000ULL);  // 100 µs ⇒ 第一档
        perf::RecordRuntimePerfBin(bins, 600ULL * 19200ULL / 1000ULL);  // 600 µs ⇒ 第二档
        perf::RecordRuntimePerfBin(bins, 2ULL * 19200ULL);              // 2 ms   ⇒ 第三档
        perf::RecordRuntimePerfBin(bins, 6ULL * 19200ULL);              // 6 ms   ⇒ 第四档
        expect(bins[0] == 1 && bins[1] == 1 && bins[2] == 1 && bins[3] == 1,
               "四个样本必须各落一档（6 ms 必须落在第四档）");
    }

    if (failures == 0) {
        std::printf("ALL OK\n");
    }
    return failures == 0 ? 0 : 1;
}
'''


def _compile_and_run():
    import subprocess
    import tempfile

    compilers = host_compilers()
    if compilers is None:
        raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
    _cc, cxx = compilers
    temporary = Path(tempfile.mkdtemp(prefix="perf-callback-buckets-"))
    compatibility = temporary / "compatibility"
    compatibility.mkdir()
    (compatibility / "stdfloat").write_text(
        "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n",
        encoding="utf-8")
    harness = temporary / "harness.cpp"
    harness.write_text(HARNESS, encoding="utf-8")
    binary = temporary / "harness"
    build = subprocess.run(
        [cxx, "-std=c++23", "-w", "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
         "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
         "-I", str(compatibility), "-I", str(RUNTIME / "source"), "-I", str(RUNTIME / "src"),
         str(harness), "-o", str(binary)],
        text=True, capture_output=True)
    if build.returncode != 0:
        raise AssertionError(f"compile failed:\n{build.stdout}\n{build.stderr}")
    finished = subprocess.run([str(binary)], capture_output=True, text=True)
    if finished.returncode != 0:
        raise AssertionError(f"harness 失败：\n{finished.stdout}{finished.stderr}")
    return finished.stdout


class PerfCallbackBuckets(unittest.TestCase):
    def test_recording_behaviour_matches_the_layout(self):
        output = _compile_and_run()
        self.assertIn("ALL OK", output, output)

    def test_tool_constants_match_the_header(self):
        header = HEADER.read_text(encoding="utf-8")
        tool = TOOL.read_text(encoding="utf-8")
        header_count = re.search(r"kRuntimePerfBucketCount\s*=\s*(\d+)", header)
        header_bytes = re.search(r"RuntimePerfCallbackBucket\b", header)
        self.assertIsNotNone(header_count, "头文件里找不到 kRuntimePerfBucketCount")
        self.assertIsNotNone(header_bytes, "头文件里找不到桶结构")
        tool_count = re.search(r"^PERF_BUCKET_COUNT\s*=\s*(\d+)", tool, re.M)
        tool_bytes = re.search(r"^PERF_BUCKET_BYTES\s*=\s*(\d+)", tool, re.M)
        self.assertIsNotNone(tool_count, "读数工具里找不到 PERF_BUCKET_COUNT")
        self.assertIsNotNone(tool_bytes, "读数工具里找不到 PERF_BUCKET_BYTES")
        self.assertEqual(
            header_count.group(1), tool_count.group(1),
            "头文件的 kRuntimePerfBucketCount 与读数工具的 PERF_BUCKET_COUNT 必须一致"
            "（工具按这个数整块读，不一致会把别的变量当桶）")
        # 桶 = 4 个 u64（key / count / ticks / maxTicks），工具按 '<QQQQ' 解。
        fields = re.search(
            r"struct RuntimePerfCallbackBucket\s*\{(.*?)\};", header, re.S).group(1)
        order = re.findall(r"std::uint64_t\s+(\w+);", fields)
        self.assertEqual(order, ["key", "count", "ticks", "maxTicks"],
                         "桶字段顺序变了，读数工具的 '<QQQQ' 解码会错位")
        self.assertEqual(tool_bytes.group(1), "48",
                         "每项 48 字节（4 × u64 + bins[4]；批次 092 加直方图后变了，两边必须同步）")
        self.assertIn("'<QQQQ'", tool, "工具的解码格式必须与字段顺序一致")
        self.assertIn("('perf_buckets',", tool, "工具里没有读桶数组的那一条请求")
        self.assertRegex(
            tool, r"'perf_buckets',\s*\n\s*base \+ SYMS\['g_RuntimePerfCallbackBuckets'\],\s*\n"
                  r"\s*\(PERF_BUCKET_COUNT \* PERF_BUCKET_BYTES \+ 7\) // 8",
            "桶数组必须按 '个数 × 每项字节' 整块读")
        # 批次 087：API 桶是**另一张表**，用的是同一套 32 字节记录 —— 个数同样要对齐。
        header_api_count = re.search(r"kRuntimePerfApiBucketCount\s*=\s*(\d+)", header)
        tool_api_count = re.search(r"^PERF_API_BUCKET_COUNT\s*=\s*(\d+)", tool, re.M)
        self.assertIsNotNone(header_api_count, "头文件里找不到 kRuntimePerfApiBucketCount")
        self.assertIsNotNone(tool_api_count, "读数工具里找不到 PERF_API_BUCKET_COUNT")
        self.assertEqual(header_api_count.group(1), tool_api_count.group(1),
                         "API 桶的个数必须两边一致（工具按这个数整块读）")
        self.assertRegex(
            tool, r"'perf_api_buckets',\s*\n\s*base \+ SYMS\['g_RuntimePerfApiBuckets'\],\s*\n"
                  r"\s*\(PERF_API_BUCKET_COUNT \* PERF_BUCKET_BYTES \+ 7\) // 8",
            "API 桶数组也必须按 '个数 × 每项字节' 整块读")
        self.assertIn("kRuntimePerfApiEngineTag", header, "头文件里缺少'引擎调用那一段'的标记位")
        self.assertTrue(
            re.search(r"^PERF_API_ENGINE_TAG\s*=\s*1 << 32", tool, re.M),
            "工具的标记位必须与头文件同位（`kRuntimePerfApiEngineTag`）")

    def test_api_ranking_is_descending(self):
        """"最贵的 API"必须**降序**，否则读数会把"最便宜的几个"当结论。

        这不是假想的错误：第一版就是升序取前 10，真凶被挤到第 8 名、最贵的几个根本没出现，
        而打印出来的名字、次数、平均**全都是对的** —— 只看输出发现不了。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("read_device_state", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        identifier_cheap, identifier_expensive = 0x0E010007, 0x0B01000D
        records = [
            (identifier_cheap, 1, 100, 100, (1, 0, 0, 0)),                    # 很便宜
            (identifier_expensive, 5, 900_000, 500_000, (0, 5, 0, 0)),        # 很贵
            (identifier_expensive | module.PERF_API_ENGINE_TAG, 5, 800_000, 400_000, (0, 5, 0, 0)),
        ]
        ranked = module.rank_perf_api_buckets(records)
        self.assertEqual([row[2] for row in ranked], [identifier_expensive, identifier_cheap],
                         "排序必须是合计耗时降序（贵在前）")
        self.assertEqual(ranked[0][0], 900_000, "返回的 ticks 必须是该接口的合计")
        self.assertEqual(ranked[0][3], 800_000, "引擎调用那一段要单独带出来（可算占比）")
        self.assertEqual(ranked[1][3], 0, "没有引擎段标记的接口，引擎段读数为 0")
        self.assertEqual(len(ranked), 2, "带引擎标记的同 id 记录不能算成第二个接口")

    def test_internal_ids_match_between_header_and_tool(self):
        """**内部运算/元表处理器**的保留 id：头文件与读数工具必须逐项一致。

        这些处理器不是 catalog 接口（没有 `owner:name`），所以没有"绑定表"可对；
        但它们**是热路径**（实体每次字段读、方法查找都要过 `Entity.__index`）。
        抄错一个序号，读数就会把 `Entity.__index` 的耗时标到 `Vector.__sub` 之类名下 ——
        名字、次数都对，只有结论是错的（这正是 087 那次"排序反向"的同类陷阱）。
        """
        header = HEADER.read_text(encoding="utf-8")
        tool = TOOL.read_text(encoding="utf-8")
        mapping = dict(re.findall(r"kPerfInternalId(\w+)\s*=\s*kPerfInternalIdBase \+ (\d+)U",
                                  header))
        self.assertGreaterEqual(len(mapping), 15, "头文件里的内部 id 少了（至少要覆盖元表与向量运算）")
        # 两边都转成"序号集合"再比：头文件写的是十进制偏移、工具写的是十六进制 id，必须换算。
        header_serials = sorted(int(value) for value in mapping.values())
        tool_serials = sorted(int(match.group(1), 16)
                              for match in re.finditer(r"0xFF0000([0-9A-F]{2}): '", tool))
        self.assertEqual(header_serials, tool_serials,
                         "头文件与读数工具的内部 id 序号集合必须一致")
        self.assertGreaterEqual(len(tool_serials), 12, "内部 id 至少覆盖元表与向量运算那些热路径")
        # 关键几项必须真的挂上了中央包装（否则读数里根本不会出现它们）
        source = (RUNTIME / "src" / "interfaces" / "lua" / "isaac_api.cpp").read_text(
            encoding="utf-8")
        for needle in ("kPerfInternalIdEntityIndex", "kPerfInternalIdEntityPlayerIndex",
                       "kPerfInternalIdEntityPickupIndex"):
            self.assertIn(needle, source, f"{needle} 没有挂上中央包装")
        self.assertIn("PushHandler(state, GlobalGetPtrHash, 0, 0x0001001FU)", source,
                      "`GlobalGetPtrHash` 要用真 catalog id 挂上中央包装")
        runtime_source = (RUNTIME / "source" / "lua_runtime.cpp").read_text(encoding="utf-8")
        for needle in ("kPerfInternalIdVectorSub", "kPerfInternalIdVectorIndex",
                       "kPerfInternalIdVectorCall"):
            self.assertIn(needle, runtime_source, f"{needle} 没有挂上中央包装")

    def test_global_handler_id_matches_the_catalog(self):
        """不走绑定表的全局处理器（`GetPtrHash`）也要核对 id —— 它没有 `{0x…, &Name}` 可对。

        这里用"catalog 里那一行必须逐字存在"来钉：`MakeId(ApiDomain::Global, 1, 0x1F)` ⇒
        `(0 << 24) | (1 << 16) | 0x1F = 0x0001001F`。catalog 一改，这条就红。
        """
        catalog = (RUNTIME / "src" / "interfaces" / "lua" / "api_catalog.cpp").read_text(encoding="utf-8")
        self.assertIn('MakeId(ApiDomain::Global, 1, 0x001F), ApiDomain::Global, "Global", "GetPtrHash"',
                      catalog, "catalog 里 `Global:GetPtrHash` 的 id 变了 ⇒ 插桩里的常量要跟着改")
        source = (RUNTIME / "src" / "interfaces" / "lua" / "isaac_api.cpp").read_text(encoding="utf-8")
        self.assertIn("PushHandler(state, GlobalGetPtrHash, 0, 0x0001001FU)", source,
                      "`GlobalGetPtrHash` 必须用真 catalog id 0x0001001F 挂上中央计时包装")

    def test_entity_data_fast_path_keeps_the_identity_rules(self):
        """`Entity:GetData()` 的快路径（批次 088）不许放宽"同一实体同一张表"的三个字段。

        快路径唯一的合法性来源是**指针 + 生成帧 + epoch 三者全等**；少比任何一个，
        地址被复用时就会把别人的表交出去（静默错数据，不报错）。
        """
        source = (RUNTIME / "src" / "interfaces" / "lua" / "isaac_api.cpp").read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r"cached\.slotPlusOne != 0 && cached\.entity == entity && cached\.epoch == epoch &&\s*\n"
            r"\s*cached\.spawnFrame == spawnFrame",
            "快路径必须同时比较 指针 / epoch / 生成帧 三个字段")
        self.assertIn("g_EntityDataSlotCache.fill(EntityDataSlotCache{});", source,
                      "换房间时必须把直映缓存整张作废（槽位索引不再可信）")
        self.assertIn("g_EntityDataRoomCache = EntityDataRoomCache{};", source,
                      "`ResetEntityDataStore()` 必须把房间缓存也复位")
        # 慢路径（权威）必须还在：快路径漏检时只能退回它，不能给出别的答案。
        self.assertRegex(
            source,
            r"for \(std::size_t index = 0; index < g_EntityDataEntries\.size\(\); \+\+index\) \{\s*\n"
            r"\s*EntityDataEntry& entry = g_EntityDataEntries\[index\];\s*\n"
            r"\s*if \(!entry\.occupied \|\| entry\.epoch != epoch \|\| entry\.entity != entity \|\|",
            "线性扫（权威路径）必须保留：快路径漏检时退回它")

    def test_device_storage_and_call_site(self):
        source = LUA_RUNTIME.read_text(encoding="utf-8")
        self.assertRegex(
            source, r'extern "C" \{\n(?:.*\n)*?__attribute__\(\(visibility\("hidden"\)\)\) '
                    r'isaac::runtime::RuntimePerfCallbackBucket\s*\n\s*'
                    r'g_RuntimePerfCallbackBuckets\[isaac::runtime::kRuntimePerfBucketCount\]',
            "桶数组必须 `extern \"C\"` + hidden + 固定个数（裸名供工具直读、不走数据 GOT）")
        # 记在 `lua_pcallk` 之后那一小段里（计时的地方），不要漂到别的路径上。
        timing = source.index("const std::uint64_t perfEnd = isaac::runtime::RuntimePerfTick();")
        # 从计时那一行**之后**找：文件里现在有两处记账调用（回调桶 + API 桶）。
        call = source.index("RecordRuntimePerfCallbackSample(", timing)
        region = source[max(0, call - len("static_cast<void>(isaac::runtime::")):source.index(");", call) + 2]
        for needle in ("static_cast<void>(isaac::runtime::RecordRuntimePerfCallbackSample(",
                       "g_RuntimePerfCallbackBuckets",
                       "isaac::runtime::kRuntimePerfBucketCount",
                       "isaac::runtime::RuntimePerfCallbackKey(",
                       "descriptor.id", "descriptor.owner.index", "descriptor.owner.generation"):
            self.assertIn(needle, region,
                          f"回调计时块里的记账调用少了 {needle} —— 只记总数就答不出"
                          f"\"贵的是哪一个回调\"")
        self.assertLess(call - timing, 2000, "记账调用应当紧跟在回调计时之后")


if __name__ == "__main__":
    unittest.main()
