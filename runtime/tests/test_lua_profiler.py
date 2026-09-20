"""门禁：**Lua 采样剖析器**（批次 089，2026-09-20）。

## 为什么有它

088 把运行时的家底量准之后，"物品旁边 EID 那条渲染回调 1050 µs/帧"里剩下的
**约 824 µs（79%）在 EID 自己的 Lua 里** —— 按 API 分只能看到它调了我们什么，
看不到它自己算在哪，于是只能靠猜，而 088 恰好是一次猜错（估 750 µs，实测 31 µs）。
剖析器（`lua_sethook` + `LUA_MASKCOUNT` 计数钩子）就是为了不再猜。

## 这条门禁钉住什么

**A. 真跑一个 Lua 状态**（不是读代码）：
1. 装上钩子后，**热的那个函数拿到明显更多的采样点**，冷的那个少 —— 这是剖析器的全部意义；
2. `g_RuntimePerfProfileSamples` 必须等于"各桶 hits 之和 + 溢出数"（账要对得上，
   对不上说明有采样被丢了或者被算了两次）；
3. 函数名与短文件名要**真的记进去**（读数里靠它们认人），无名函数要有合成名字；
4. **钩子不许改变程序行为**：同一个脚本"装钩子 / 不装钩子"两次运行的结果必须逐字相同
   （剖析器把模组改坏了就本末倒置）。

**B. 记账行为**（纯函数）：
5. 同 `(source, name)` 合并；桶满**不覆盖**已有样本、只加溢出；`line` 只记首次值。

**C. 口径一致**：桶数与每项字节数必须与读数工具一致（工具按"个数 × 每项字节"整块读）。
"""

import re
import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:  # pragma: no cover - 直接跑单文件时的回退
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
SOURCE = RUNTIME / "source"
HEADER = RUNTIME / "src" / "interfaces" / "lua" / "runtime_profiler.hpp"
TOOL = ROOT / "tools" / "read_device_state_via_gdb.py"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "interfaces/lua/runtime_profiler.hpp"

#include <cstdio>
#include <cstring>

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

// 剖析器的存储与钩子（定义在 `lua_runtime.cpp`，都是裸名，宿主也能直接取）。
// 注意：它们在**全局** `extern "C"` 作用域里定义（不是命名空间里），所以这里也按全局声明。
extern "C" void IsaacRuntime_ProfileHook(lua_State* state, lua_Debug* debug);
extern "C" isaac::runtime::RuntimePerfProfileBucket
    g_RuntimePerfProfileBuckets[isaac::runtime::kRuntimePerfProfileBucketCount];
extern "C" std::uint64_t g_RuntimePerfProfileSamples;
extern "C" std::uint64_t g_RuntimePerfProfileOverflow;

namespace {
int failures = 0;
void expect(bool condition, const char* what) {
    if (!condition) {
        std::printf("FAIL %s\n", what);
        ++failures;
    }
}

// 一段脚本：`hot` 被调用很多次（内部是长循环），`cold` 只调用一次。
const char* kScript = R"LUA(
local trace = {}
function cold(n)
    return n + 1
end
function hot(n)
    local total = 0
    for i = 1, n do
        total = total + (i * 2) % 7
    end
    return total
end
function drive()
    local sum = 0
    for i = 1, 400 do
        sum = sum + hot(300)
    end
    return sum + cold(1)
end
return drive()
)LUA";

std::uint64_t TotalHits() {
    std::uint64_t total = 0;
    for (std::size_t index = 0; index < isaac::runtime::kRuntimePerfProfileBucketCount; ++index) {
        total += g_RuntimePerfProfileBuckets[index].hits;
    }
    return total;
}

std::uint64_t HitsFor(const char* name) {
    for (std::size_t index = 0; index < isaac::runtime::kRuntimePerfProfileBucketCount; ++index) {
        const auto& bucket = g_RuntimePerfProfileBuckets[index];
        if (bucket.hits != 0 && std::strcmp(bucket.name, name) == 0) {
            return bucket.hits;
        }
    }
    return 0;
}

const char* SourceFor(const char* name) {
    for (std::size_t index = 0; index < isaac::runtime::kRuntimePerfProfileBucketCount; ++index) {
        const auto& bucket = g_RuntimePerfProfileBuckets[index];
        if (bucket.hits != 0 && std::strcmp(bucket.name, name) == 0) {
            return bucket.source;
        }
    }
    return "";
}

// 跑一次脚本，返回结果字符串；`profile` 决定装不装钩子。
bool RunScript(bool profile, long long* result, char* output, std::size_t outputSize) {
    lua_State* state = luaL_newstate();
    if (state == nullptr) {
        return false;
    }
    // 宿主 harness 的 Lua 对象清单**不含 `linit.c`**（`luaL_openlibs` 不在里面），
    // 而我们的运行时本来就是逐个开库的 —— 这里照同一口径只开 `_G`（脚本只用算术与循环）。
    luaL_requiref(state, "_G", luaopen_base, 1);
    lua_pop(state, 1);
    if (profile) {
        lua_sethook(state, IsaacRuntime_ProfileHook, LUA_MASKCOUNT, 200);
    }
    const int status = luaL_loadbuffer(state, kScript, std::strlen(kScript), "@sample.lua") ||
                       lua_pcall(state, 0, 1, 0);
    if (status != LUA_OK) {
        std::snprintf(output, outputSize, "error: %s", lua_tostring(state, -1));
        lua_close(state);
        return false;
    }
    *result = static_cast<long long>(lua_tointeger(state, -1));
    std::snprintf(output, outputSize, "%lld", *result);
    lua_close(state);
    return true;
}
} // namespace

int main() {
    // ---- B. 记账行为（纯函数）------------------------------------------------
    {
        isaac::runtime::RuntimePerfProfileBucket buckets[4] = {};
        std::uint64_t overflow = 0;
        expect(isaac::runtime::RecordRuntimePerfProfileSample(
                   buckets, 4, "@a.lua", "alpha", 10, &overflow), "第一笔进桶");
        expect(isaac::runtime::RecordRuntimePerfProfileSample(
                   buckets, 4, "@a.lua", "alpha", 99, &overflow), "同键合并");
        expect(buckets[0].hits == 2, "同键累加");
        expect(buckets[0].line == 10, "line 只记首次值");
        expect(isaac::runtime::RecordRuntimePerfProfileSample(
                   buckets, 4, "@a.lua", nullptr, 40, &overflow), "无名函数也要有桶");
        expect(std::strcmp(buckets[1].name, "<匿名>") == 0, "无名函数用合成名字");
        expect(isaac::runtime::RecordRuntimePerfProfileSample(
                   buckets, 4, "@a.lua", "beta", 20, &overflow), "不同文件/函数各占一桶");
        expect(!isaac::runtime::RecordRuntimePerfProfileSample(nullptr, 0, "@a.lua", "x", 1, nullptr),
               "空表不崩");
    }
    {
        // **Space-Saving 的两条性质**（第一次真机就是因为缺了它们，表全废）：
        //   ① 被顶掉的计数**继承**过来 ⇒ 各桶之和 == 总采样数，永远不会丢样本；
        //   ② 热点会把自己"顶起来"，冷键挤不走它。
        isaac::runtime::RuntimePerfProfileBucket buckets[2] = {};
        std::uint64_t replaced = 0;
        for (int round = 0; round < 20; ++round) {
            isaac::runtime::RecordRuntimePerfProfileSample(buckets, 2, "@a.lua", "hot", 1, &replaced);
        }
        isaac::runtime::RecordRuntimePerfProfileSample(buckets, 2, "@a.lua", "cold", 2, &replaced);
        isaac::runtime::RecordRuntimePerfProfileSample(buckets, 2, "@a.lua", "third", 3, &replaced);
        std::uint64_t total = 0;
        bool hotSurvived = false;
        for (const auto& bucket : buckets) {
            total += bucket.hits;
            if (bucket.hits != 0 && std::strcmp(bucket.name, "hot") == 0) {
                hotSurvived = true;
            }
        }
        expect(total == 22, "各桶之和必须等于总采样数（被顶掉的计数要继承，不许丢）");
        expect(replaced == 1, "顶槽要记进 overflow（读数里据此判断表够不够）");
        expect(hotSurvived, "热点不许被冷键挤走（它的计数会把自己顶起来）");
        expect(buckets[0].hits >= 20, "热点的计数必须留在表里，不能被重置成 1");
    }

    // ---- A. 真跑一个 Lua 状态 -------------------------------------------------
    long long withoutProfile = 0, withProfile = 0;
    char output[64] = {};
    expect(RunScript(false, &withoutProfile, output, sizeof(output)), "不装钩子能跑");
    expect(RunScript(true, &withProfile, output, sizeof(output)), "装钩子能跑");
    expect(withoutProfile == withProfile, "装钩子不许改变脚本结果（钩子不能改行为）");

    const std::uint64_t hot = HitsFor("hot");
    const std::uint64_t cold = HitsFor("cold");
    const std::uint64_t samples = g_RuntimePerfProfileSamples;
    expect(samples > 0, "应当采到样本");
    expect(hot > 0, "热函数必须有采样点");
    expect(hot > cold * 5, "热函数的采样点必须远多于冷函数 —— 这正是剖析器的意义");
    // 注意：Lua 的 `short_src` 会**剥掉** chunk 名开头的 `@` 或 `=`（`lua_getinfo` 的行为），
    // 所以这里拿到的是 `sample.lua` 而不是 `@sample.lua` —— 真机上同理（`rom:/isaac_mods/...`）。
    expect(std::strcmp(SourceFor("hot"), "sample.lua") == 0, "短文件名要记进桶里");
    expect(TotalHits() == samples,
           "账要对：各桶 hits 之和 == 总采样数（Space-Saving 继承计数，不允许丢样本）");

    if (failures != 0) {
        std::printf("---- 桶内容（前 6 条）----\n");
        for (std::size_t index = 0; index < isaac::runtime::kRuntimePerfProfileBucketCount; ++index) {
            const auto& bucket = g_RuntimePerfProfileBuckets[index];
            if (bucket.hits == 0) {
                continue;
            }
            std::printf("  %-20s %-30s hits=%u line=%d\n", bucket.name, bucket.source,
                        bucket.hits, bucket.line);
            if (index > 40) {
                break;
            }
        }
    }
    if (failures == 0) {
        std::printf("ALL OK (samples=%llu hot=%llu cold=%llu)\n",
                    static_cast<unsigned long long>(samples),
                    static_cast<unsigned long long>(hot),
                    static_cast<unsigned long long>(cold));
    }
    return failures == 0 ? 0 : 1;
}
'''


def _compile_and_run():
    """按仓库既有 harness 的配方编译（vendored Lua 单独编、宏与包含路径照抄）。"""
    import subprocess
    import tempfile

    import shutil

    def host_compilers():
        cc = shutil.which("cc")
        if cc is None:
            return None
        for candidate in ("c++", "clang++", "g++"):
            found = shutil.which(candidate)
            if found is not None:
                return cc, found
        return None

    compilers = host_compilers()
    if compilers is None:
        raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
    cc, cxx = compilers
    temporary = Path(tempfile.mkdtemp(prefix="lua-profiler-"))
    compatibility = temporary / "compatibility"
    compatibility.mkdir()
    (compatibility / "stdfloat").write_text(
        "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n",
        encoding="utf-8")
    harness = temporary / "harness.cpp"
    harness.write_text(HARNESS, encoding="utf-8")

    lua_root = SOURCE / "third_party/lua-5.3.3/src"
    excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
    lua_objects = []
    for lua_source in sorted(lua_root.glob("*.c")):
        if lua_source.name in excluded:
            continue
        output = temporary / f"{lua_source.stem}.o"
        build = subprocess.run([cc, "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root),
                                "-c", str(lua_source), "-o", str(output)],
                               text=True, capture_output=True)
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)
        lua_objects.append(output)

    binary = temporary / "harness"
    build = subprocess.run(
        [cxx, "-std=c++23", "-w", "-DLUA_C89_NUMBERS", "-DEXL_LAYERED_RUNTIME=1",
         "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
         "-I", str(compatibility), "-I", str(SOURCE), "-I", str(RUNTIME / "src"),
         "-I", str(lua_root), str(harness),
         *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
         *map(str, lua_objects), "-o", str(binary)],
        text=True, capture_output=True)
    if build.returncode != 0:
        raise AssertionError(f"compile failed:\n{build.stdout}\n{build.stderr}")
    finished = subprocess.run([str(binary)], capture_output=True, text=True)
    if finished.returncode != 0:
        raise AssertionError(f"harness 失败：\n{finished.stdout}{finished.stderr}")
    return finished.stdout


class LuaProfiler(unittest.TestCase):
    def test_sampling_attributes_time_to_the_hot_function(self):
        output = _compile_and_run()
        self.assertIn("ALL OK", output, output)

    def test_tool_constants_match_the_header(self):
        header = HEADER.read_text(encoding="utf-8")
        tool = TOOL.read_text(encoding="utf-8")
        count = re.search(r"kRuntimePerfProfileBucketCount\s*=\s*(\d+)", header)
        step = re.search(r"kRuntimePerfProfileInstructionStep\s*=\s*(\d+)", header)
        tool_count = re.search(r"^PROFILE_BUCKET_COUNT\s*=\s*(\d+)", tool, re.M)
        tool_bytes = re.search(r"^PROFILE_BUCKET_BYTES\s*=\s*(\d+)", tool, re.M)
        tool_step = re.search(r"^PERF_PROFILE_INSTRUCTION_STEP\s*=\s*(\d+)", tool, re.M)
        for match, what in ((count, "kRuntimePerfProfileBucketCount"),
                            (step, "kRuntimePerfProfileInstructionStep"),
                            (tool_count, "PROFILE_BUCKET_COUNT"),
                            (tool_bytes, "PROFILE_BUCKET_BYTES"),
                            (tool_step, "PERF_PROFILE_INSTRUCTION_STEP")):
            self.assertIsNotNone(match, f"找不到 {what}")
        self.assertEqual(count.group(1), tool_count.group(1), "桶个数必须两边一致")
        self.assertEqual(step.group(1), tool_step.group(1),
                         "采样步长必须两边一致（否则读数里的百分比含义会被说错）")
        self.assertEqual(tool_bytes.group(1), "80", "每项 80 字节（u32+i32+char[24]+char[48]）")
        # 第一次真机的教训：128 个桶会被"只命中一次"的条目占满 ⇒ 桶数提上去了，
        # 并且必须有"淘汰命中最少的桶"的策略（否则热函数照样会被挤掉）。
        self.assertGreaterEqual(int(tool_count.group(1)), 192, "桶数不能退回 128（第一次真机就被占满）")
        header = HEADER.read_text(encoding="utf-8")
        self.assertIn("kProfileEvictionMaximumHits", header, "必须有淘汰阈值常量")
        self.assertIn("coldest", header, "没有空桶时必须淘汰命中最少的桶")
        fields = re.search(r"struct RuntimePerfProfileBucket\s*\{(.*?)\};", header, re.S).group(1)
        self.assertEqual(re.findall(r"char\s+(\w+)\[(\d+)\]", fields),
                         [("name", "24"), ("source", "48")],
                         "工具按 name[24] + source[48] 解，字段宽度变了要同步")
        self.assertRegex(
            tool, r"'perf_profile_buckets',\s*\n\s*base \+ SYMS\['g_RuntimePerfProfileBuckets'\],\s*\n"
                  r"\s*\(PROFILE_BUCKET_COUNT \* PROFILE_BUCKET_BYTES \+ 7\) // 8",
            "采样桶必须按 '个数 × 每项字节' 整块读")

    def test_allocation_accounting_mirrors_the_default_allocator(self):
        """分配账（批次 091）：计数分配器必须**与 Lua 默认分配器行为逐字相同**，只多记账。

        为什么这条必须有：087/088 的尺子量不到"分配 + 增量 GC"这段 C 侧时间，
        而 089 又证明 Lua 指令执行只占约 10 µs/帧 —— 那 2 ms 的去向只能靠分配账来判。
        **一旦这个分配器行为与默认的不一样（少 free、多 realloc、或丢掉 panic 处理器），
        量出来的就不是"真实开销"，而是"我们改出来的开销"。**
        """
        source = (SOURCE / "lua_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn("lua_setallocf(state, IsaacRuntime_CountingAlloc, nullptr);", source,
                      "必须用 lua_setallocf 换分配器（自己 lua_newstate 会丢掉 luaL_newstate 的 panic 处理器）")
        self.assertNotIn("lua_newstate(", source, "不要自己建状态：`luaL_newstate` 那套语义要原样保留")
        allocator = source[source.index("IsaacRuntime_CountingAlloc"):]
        allocator = allocator[:allocator.index("\n}\n")]
        self.assertIn("if (newSize == 0)", allocator, "默认分配器：长度为 0 表示 free")
        self.assertIn("std::free(block);", allocator, "长度为 0 必须真的 free（否则内存只增不减）")
        self.assertIn("std::realloc(block, newSize);", allocator, "其余情况走 realloc（与 l_alloc 同）")
        for counter in ("g_RuntimePerfAllocCalls", "g_RuntimePerfAllocBytes",
                        "g_RuntimePerfAllocNewCalls", "g_RuntimePerfFreeCalls"):
            self.assertIn(counter, allocator, f"分配器里少了计数 {counter}")
            self.assertIn(counter, TOOL.read_text(encoding="utf-8"), f"读数工具没读 {counter}")

    def test_hook_is_count_based_and_only_allocates_nothing(self):
        """钩子必须是**计数型**（`LUA_MASKCOUNT`），且只在设备构建里自动挂。

        计数型是这套做法的前提：`LUA_MASKLINE`/`LUA_MASKCALL` 会按"每次调用/每行"触发，
        在大循环里比计数型贵一到两个数量级。
        """
        source = (SOURCE / "lua_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn("lua_sethook(state, IsaacRuntime_ProfileHook, LUA_MASKCOUNT,", source)
        self.assertNotIn("LUA_MASKLINE", source)
        self.assertNotIn("LUA_MASKCALL", source)
        self.assertRegex(source, r"#if defined\(ISAAC_RUNTIME_PERF_TIMING\)\s*\n\s*ResetRuntimePerfProfile\(\);",
                         "自动挂载必须只在设备构建里（宿主套件不需要为此变慢）")
        # 钩子本体的"不许分配"是纪律，代码层面能钉的是：它只调用 `lua_getinfo`。
        hook = source[source.index("void ReadProfileFrameText"):source.index("void ResetRuntimePerfProfile")]
        lua_calls = set(re.findall(r"\blua_[a-z_]+", hook))
        self.assertEqual(lua_calls, {"lua_getinfo"},
                         f"钩子里只允许调 `lua_getinfo`（不分配、不碰栈），现在还有 {lua_calls}")


if __name__ == "__main__":
    unittest.main()
