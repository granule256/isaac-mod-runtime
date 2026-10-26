"""运行时发现结果 → 原生模组页条目来源（目录顺序、开关逐条、装不下整体放弃）。

判据都在宿主上用**假来源**跑：目录表、开关、读文件三样都是假的 ⇒ "顺序对不对、开关有没有
逐条问对、装不下怎么办"全部离线判死；真机上只剩"那两条通道读不读得到"这一件事
（那是 `mod_menu_api` 与 `GameFileReader` 的既有面）。

为什么这几条值得单独钉住：模组页上"少一行 / 颜色不对"这种现象，**说不出**是"某些模组没发现到"
还是"我们把它标成关闭了"。所以每一条断言都对着一个具体的误判。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
SRC_ROOT = ROOT / "runtime" / "src"

HARNESS = r'''
#include "mod_page_runtime_sources.hpp"

#include <cstdio>
#include <cstring>

using isaac::runtime::CollectRuntimeModPageSources;
using isaac::runtime::DecideModPageSource;
using isaac::runtime::ModPageEntrySource;
using isaac::runtime::ModPageRuntimeStats;
using isaac::runtime::ModPageSourceDecision;
using isaac::runtime::ModPageTextReader;
using isaac::runtime::MountedReadResult;
using isaac::runtime::ResolveModPagePath;
using isaac::runtime::ResolveThenRead;
using isaac::runtime::kModPageMaximumMods;

namespace {

int failures = 0;

void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}

// ── 假的**挂载解析器**：认两条输入，各自的"解析结果"与输入**故意不同** ──
//
// 为什么结果要与输入不同：2026-09-22 真机事故就是"把输入当成要读的那条路径"（续七十）。
// 这份夹具让"读的时候到底用了哪条"变成一个**能在宿主上判死**的问题。
const char* const kResolvable[] = {
    "rom:/isaac_mods/mods/AlphaMod/metadata.xml",   // 原样形式就能解析
    "isaac_mods/mods/RelativeMod/metadata.xml",     // 只有去掉前缀才解析得出来
};
const char* const kResolved[] = {
    "rom:/mounted/AlphaMod/metadata.xml",           // ← 解析结果（与输入不同！）
    "rom:/mounted/RelativeMod/metadata.xml",
};
int resolveCalls = 0;
char resolveAsked[8][96]{};
char resolveWrote[8][96]{};

bool FakeResolve(void*, const char* path, char* out, std::size_t capacity) {
    if (resolveCalls < 8) { std::strncpy(resolveAsked[resolveCalls], path, 95); }
    for (int i = 0; i < 2; ++i) {
        if (std::strcmp(path, kResolvable[i]) == 0) {
            const std::size_t n = std::strlen(kResolved[i]);
            if (n + 1 > capacity) { ++resolveCalls; return false; }
            std::memcpy(out, kResolved[i], n + 1);
            if (resolveCalls < 8) { std::strncpy(resolveWrote[resolveCalls], kResolved[i], 95); }
            ++resolveCalls;
            return true;
        }
    }
    ++resolveCalls;
    return false;
}

// ── 三个假目录；开关按调用次数逐个记录（用来证明"每条都问了一次、问的是它自己那个名字"）──
const char* const kDirectories[3] = {"AlphaMod", "BetaMod", "GammaMod"};
int enabledCalls = 0;
char enabledAsked[3][64]{};

bool FakeEnabled(void*, const char* directory) {
    if (enabledCalls < 3) {
        std::strncpy(enabledAsked[enabledCalls], directory, 63);
    }
    ++enabledCalls;
    return std::strcmp(directory, "BetaMod") != 0;  // 只有 Beta 是"关着"
}

std::uint32_t FakeDirectories(void*, const char** out, std::uint32_t capacity) {
    if (capacity < 3) { return 3; }  // 装不下就如实报"三个"（不给半截）
    out[0] = kDirectories[0];
    out[1] = kDirectories[1];
    out[2] = kDirectories[2];
    return 3;
}

std::uint32_t NoDirectories(void*, const char**, std::uint32_t) { return 0; }

// 只认 Alpha 的 metadata.xml（有 <name>）；Beta 的 XML 里没有 <name>；Gamma 读不到文件。
bool FakeReader(void*, const char* path, char* buffer, std::size_t capacity,
                std::size_t* length) {
    const char* xml = nullptr;
    if (std::strstr(path, "/AlphaMod/") != nullptr) {
        xml = "<mod><name>Alpha \xe4\xb8\xad\xe6\x96\x87</name></mod>";
    } else if (std::strstr(path, "/BetaMod/") != nullptr) {
        xml = "<mod><description>no name</description></mod>";
    }
    if (xml == nullptr) { return false; }
    const std::size_t n = std::strlen(xml);
    if (n + 1 > capacity) { return false; }
    std::memcpy(buffer, xml, n + 1);
    if (length != nullptr) { *length = n; }
    return true;
}

}  // namespace

int main() {
        Check(kModPageMaximumMods == 256, "menu supports 256 mods");
    {
        const auto provider=[](void*,const char** out,std::uint32_t capacity)->std::uint32_t {
            if (capacity<256) return 256;
            for (unsigned i=0;i<256;++i) out[i]="AlphaMod";
            return 256;
        };
        ModPageEntrySource out[256]{};
        char names[256*256]{};
        char path[isaac::runtime::kModPageMetadataPathCapacity]{};
        char text[isaac::runtime::kModPageMetadataCapacity]{};
        ModPageRuntimeStats stats{};
        Check(CollectRuntimeModPageSources(out,256,provider,nullptr,nullptr,nullptr,
                  &FakeReader,nullptr,names,sizeof(names),path,text,&stats)==256,
              "all_256_menu_sources");
        std::uint8_t entries[257*isaac::runtime::kModPageEntryStride]{};
        std::uintptr_t pointers[257]{};
        ModPageEntrySource rows[257]{};
        rows[0]={"Console: ON",true,false};
        for(unsigned i=0;i<256;++i)rows[i+1]=out[i];
        std::uintptr_t vector[3]{};std::size_t used=0;
        char arena[256*256]{};
        Check(isaac::runtime::BuildModPageEntries(entries,pointers,vector,257,
              rows,arena,sizeof(arena),&used)==257,
              "console_plus_256_menu_entries");
    }
    // ---- DecideModPageSource：该等 / 该走 / 该退，三态的分界只有一处 ----
    {
        // 条目造好了 ⇒ 走（不管目录数、不管试了几次）
        Check(DecideModPageSource(true, 5, 1, 900) == ModPageSourceDecision::Ready,
              "真实条目造好了 ⇒ Ready");
        // 一个目录都没有、还没到上限 ⇒ **等**（发现结果在启动的模组扫描之后才填）
        Check(DecideModPageSource(false, 0, 1, 900) == ModPageSourceDecision::Wait,
              "还没等到任何目录 ⇒ Wait（这一条就是「主菜单比模组扫描先出现」那个坑）");
        Check(DecideModPageSource(false, 0, 899, 900) == ModPageSourceDecision::Wait,
              "上限之前都继续等");
        // 到上限 ⇒ 不再等（否则会一直等到玩家把游戏关掉）
        Check(DecideModPageSource(false, 0, 900, 900) == ModPageSourceDecision::Fallback,
              "到了尝试上限 ⇒ 退固定测试名，不许无限等");
        Check(DecideModPageSource(false, 0, 0, 0) == ModPageSourceDecision::Fallback,
              "上限为 0（不等待）⇒ 直接退");
        // 目录有、但条目没造出来 ⇒ 退（数据在，失败是真的，再等也不会变好）
        Check(DecideModPageSource(false, 3, 1, 900) == ModPageSourceDecision::Fallback,
              "目录有但条目没造出来 ⇒ 直接退，不要假装还在等");
        Check(DecideModPageSource(false, 1, 900, 900) == ModPageSourceDecision::Fallback,
              "同上，哪怕到了上限也一样是退");
    }

    // ---- ResolveModPagePath：两种输入形式都试，并把**解析出来的那条**交出去 ----
    {
        char out[128]{};
        std::uint32_t form = 0u;

        // ① 原样形式就解析得出来 ⇒ 位 0 置位，且交出去的是**解析结果**（不是输入！）
        resolveCalls = 0;
        Check(ResolveModPagePath(kResolvable[0], &FakeResolve, nullptr, out, sizeof(out), &form),
              "原样形式该解析成功");
        Check(std::strcmp(out, kResolved[0]) == 0,
              "交出去的必须是**解析器写出来的那条绝对路径**，不是传进来的那条"
              "（2026-09-22 的事故就是把输入当成了要读的路径）");
        Check(form == 1u, "原样就解析出来 ⇒ formMask 位 0");
        Check(resolveCalls == 1, "第一次就成功了 ⇒ 不该多问第二次");

        // ② 只有去掉前缀才解析得出来 ⇒ 位 1 置位，交出去的是那次的解析结果
        char prefixed[128]{};
        std::snprintf(prefixed, sizeof(prefixed), "rom:/%s", kResolvable[1]);
        resolveCalls = 0;
        Check(ResolveModPagePath(prefixed, &FakeResolve, nullptr, out, sizeof(out), &form),
              "原样答不出来、去前缀答得出来 ⇒ 也该成功");
        Check(std::strcmp(out, kResolved[1]) == 0,
              "去前缀那一次交出去的也必须是解析结果");
        Check(form == 2u, "去前缀才解析出来 ⇒ formMask 位 1");
        Check(resolveCalls == 2, "该问两次（原样一次、去前缀一次）");
        Check(std::strcmp(resolveAsked[1], kResolvable[1]) == 0,
              "第二次问的必须是跳过前缀之后的那条路径");

        // ③ 两种都不认 ⇒ 失败、formMask 清 0、输出缓冲不被碰、**解析器不再被多用**
        char untouched[64];
        std::memset(untouched, 0x5A, sizeof(untouched));
        std::memcpy(out, untouched, sizeof(untouched));
        resolveCalls = 0;
        Check(!ResolveModPagePath("rom:/isaac_mods/mods/GhostMod/metadata.xml", &FakeResolve, nullptr,
                                  out, sizeof(out), &form),
              "两种输入都不认 ⇒ 解析失败（这一条就是\"绝不盲开\"的闸）");
        Check(form == 0u, "失败时 formMask 必须是 0（不能留下上一轮的值）");
        Check(resolveCalls == 2, "失败也要问两次（原样、去前缀），不多问");
        Check(std::memcmp(out, untouched, sizeof(untouched)) == 0, "失败时不许碰输出缓冲");

        // ④ 不带前缀、又解析不出来 ⇒ 只问一次（不能凭空造出 `rom:/` 去问）
        resolveCalls = 0;
        Check(!ResolveModPagePath("isaac_mods/mods/GhostMod/metadata.xml", &FakeResolve, nullptr, out,
                                  sizeof(out), &form),
              "不带前缀且解析不出来 ⇒ 失败");
        Check(resolveCalls == 1, "不带前缀就只问一次（钉住\"前缀只跳过、不凭空加\"）");

        // ⑤ 空路径 / 只有前缀 / 输出放不下 ⇒ 都判失败，而不是读越界
        resolveCalls = 0;
        Check(!ResolveModPagePath(nullptr, &FakeResolve, nullptr, out, sizeof(out), &form),
              "空路径 ⇒ 失败");
        Check(resolveCalls == 0, "空路径不该触发任何一次解析查询");
        Check(!ResolveModPagePath("rom:/", &FakeResolve, nullptr, out, sizeof(out), &form),
              "只有前缀（前缀后面什么都没有）⇒ 失败");
        Check(resolveCalls == 1,
              "只有前缀时：按原样问过一次，**不许**再拿空路径去问第二次");
        char tiny[8]{};
        Check(!ResolveModPagePath(kResolvable[0], &FakeResolve, nullptr, tiny, sizeof(tiny), &form),
              "输出缓冲放不下 ⇒ 失败（绝不截断成一条错的路径）");

        // ⑥ formMask 允许为 nullptr（调用方只想知道"成不成"）
        Check(ResolveModPagePath(kResolvable[0], &FakeResolve, nullptr, out, sizeof(out), nullptr),
              "formMask 传空也要能用");
    }

    // ---- ResolveThenRead 的契约：**读的必须是解析出来的那条路径**（事故的正面判据）----
    {
        char resolved[128]{};
        char text[64]{};
        std::size_t length = 0;
        // 一个"顺带把收到的路径记下来"的 reader —— 这一格就是"我们到底读了哪条路径"的证据。
        struct Ctx { int calls; char saw[128]; };
        Ctx ctx{0, {}};
        auto recordingReader = +[](void* raw, const char* path, char*, std::size_t,
                                   std::size_t*) -> bool {
            auto* c = static_cast<Ctx*>(raw);
            ++c->calls;
            std::strncpy(c->saw, path, 127);
            return true;
        };
        const ModPageTextReader typedReader = recordingReader;
        Check(ResolveThenRead(kResolvable[0], &FakeResolve, nullptr, typedReader, &ctx, resolved,
                              sizeof(resolved), text, sizeof(text), &length) ==
                  MountedReadResult::Read,
              "解析 + 读都要成功");
        Check(ctx.calls == 1, "解析成功时读一次");
        Check(std::strcmp(ctx.saw, kResolved[0]) == 0,
              "★ reader 收到的必须是**解析出来的绝对路径**（事故的正面判据）");

        // 解析不出来 ⇒ **一次都不许读**（这就是"绝不盲开"）
        Ctx ctx2{0, {}};
        Check(ResolveThenRead("rom:/isaac_mods/mods/GhostMod/metadata.xml", &FakeResolve, nullptr,
                              typedReader, &ctx2, resolved, sizeof(resolved), text, sizeof(text),
                              &length) == MountedReadResult::NotMounted,
              "解析不出来 ⇒ NotMounted");
        Check(ctx2.calls == 0, "解析不出来时**一次都不许读**（盲开正是 2026-09-21 那次事故的形状）");
    }

    ModPageEntrySource sources[8]{};
    char arena[512]{};
    char path[isaac::runtime::kModPageMetadataPathCapacity]{};
    char text[isaac::runtime::kModPageMetadataCapacity]{};
    ModPageRuntimeStats stats{};

    const std::uint32_t count = CollectRuntimeModPageSources(
        sources, 8, &FakeDirectories, nullptr, &FakeEnabled, nullptr, &FakeReader, nullptr,
        arena, sizeof(arena), path, text, &stats);
    Check(count == 3, "三个目录该造出三条来源");
    Check(stats.directories == 3 && stats.entries == 3, "统计里的目录数与条数要对上");
    Check(stats.enabled == 2, "开关统计：三个里两个开着");
    Check(stats.overflowed == 0, "没超出容量就不该报 overflowed");
    Check(enabledCalls == 3, "开关要**逐条**问，不多不少三次");
    Check(std::strcmp(enabledAsked[0], "AlphaMod") == 0 &&
          std::strcmp(enabledAsked[1], "BetaMod") == 0 &&
          std::strcmp(enabledAsked[2], "GammaMod") == 0,
          "问开关时的名字必须是它自己那一条（顺序不能串）");
    Check(std::strcmp(sources[0].displayName, "Alpha \xe4\xb8\xad\xe6\x96\x87") == 0,
          "有名取 <name>（含中文）");
    Check(std::strcmp(sources[1].displayName, "BetaMod") == 0, "XML 里没有 <name> ⇒ 退目录名");
    Check(std::strcmp(sources[2].displayName, "GammaMod") == 0, "读不到文件 ⇒ 退目录名");
    Check(sources[0].enabled && !sources[1].enabled && sources[2].enabled,
          "开关状态要逐条落在对应那一行上");
    for (int i = 0; i < 3; ++i) {
        Check(!sources[i].outdated, "「旧版」位恒 false（没有可复核的来源，见头文件）");
        const auto address = reinterpret_cast<std::uintptr_t>(sources[i].displayName);
        Check(address >= reinterpret_cast<std::uintptr_t>(arena) &&
              address < reinterpret_cast<std::uintptr_t>(arena) + sizeof(arena),
              "名字必须落在 arena 里（稳定内存）");
    }

    // 开关来源缺席 ⇒ 一律当"开着"（与 `RuntimeMods.List()` 同口径），而不是当"关着"。
    {
        ModPageEntrySource out[8]{};
        char arena2[512]{};
        ModPageRuntimeStats s2{};
        Check(CollectRuntimeModPageSources(out, 8, &FakeDirectories, nullptr, nullptr, nullptr,
                                           &FakeReader, nullptr, arena2, sizeof(arena2), path, text,
                                           &s2) == 3,
              "没有开关来源时照样要造出条目");
        Check(s2.enabled == 3, "没有开关来源 ⇒ 全部当开着（不是当关着）");
        Check(out[0].enabled && out[1].enabled && out[2].enabled, "逐条也都要是开着");
    }

    // 一个目录都没有 ⇒ 0 条（页面上会是空表，调用方据此走"退回固定测试名"那条路）。
    {
        ModPageEntrySource out[8]{};
        char arena3[512]{};
        ModPageRuntimeStats s3{};
        Check(CollectRuntimeModPageSources(out, 8, &NoDirectories, nullptr, &FakeEnabled, nullptr,
                                           &FakeReader, nullptr, arena3, sizeof(arena3), path, text,
                                           &s3) == 0, "没有目录 ⇒ 0 条");
        Check(s3.directories == 0 && s3.entries == 0, "没有目录时统计也是 0");
    }

    // 装不下 ⇒ **整体放弃**（断言"不截断"：半截列表会被误判成"某些模组丢了"）。
    {
        ModPageEntrySource out[2]{};
        char arena4[512]{};
        ModPageRuntimeStats s4{};
        Check(CollectRuntimeModPageSources(out, 2, &FakeDirectories, nullptr, &FakeEnabled, nullptr,
                                           &FakeReader, nullptr, arena4, sizeof(arena4), path, text,
                                           &s4) == 0, "目录数超出容量 ⇒ 整体放弃，不许截断");
        Check(s4.overflowed == 1, "这种情况要单独记 overflowed（读数里一眼看出是这个原因）");
    }

    // 容量参数本身非法（0 / 超过上界）⇒ 拒绝，不去猜调用方想要什么。
    {
        ModPageEntrySource out[8]{};
        char arena5[512]{};
        Check(CollectRuntimeModPageSources(out, 0, &FakeDirectories, nullptr, &FakeEnabled, nullptr,
                                           &FakeReader, nullptr, arena5, sizeof(arena5), path, text,
                                           nullptr) == 0, "容量 0 ⇒ 拒绝");
        Check(CollectRuntimeModPageSources(out, kModPageMaximumMods + 1, &FakeDirectories, nullptr,
                                           &FakeEnabled, nullptr, &FakeReader, nullptr, arena5,
                                           sizeof(arena5), path, text, nullptr) == 0,
              "容量超过上界 ⇒ 拒绝（那说明调用方与这个单元对\"最多几个模组\"的理解不一致）");
    }

    // 空目录名 ⇒ 拒绝（否则会拼出 `mods//metadata.xml` 这种永远读不到的路径）。
    {
        auto emptyNameDirectories = +[](void*, const char** out, std::uint32_t) -> std::uint32_t {
            out[0] = "AlphaMod";
            out[1] = "";
            return 2;
        };
        ModPageEntrySource out[8]{};
        char arena6[512]{};
        Check(CollectRuntimeModPageSources(out, 8, emptyNameDirectories, nullptr, &FakeEnabled,
                                           nullptr, &FakeReader, nullptr, arena6, sizeof(arena6),
                                           path, text, nullptr) == 0, "空目录名 ⇒ 整体放弃");
    }

    // 名字区放不下 ⇒ 整体放弃（`CollectModPageSources` 的口径，这里确认它确实透传出来）。
    {
        ModPageEntrySource out[8]{};
        char tiny[4]{};
        Check(CollectRuntimeModPageSources(out, 8, &FakeDirectories, nullptr, &FakeEnabled, nullptr,
                                           &FakeReader, nullptr, tiny, sizeof(tiny), path, text,
                                           nullptr) == 0, "名字区放不下 ⇒ 整体放弃");
    }

    if (failures != 0) { std::printf("MOD_PAGE_RUNTIME_SOURCES_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("MOD_PAGE_RUNTIME_SOURCES_CHECKS_PASSED\n");
    return 0;
}
'''


class ModPageRuntimeSourcesTests(unittest.TestCase):
    def test_collection_on_host_with_fake_providers(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-mod-page-runtime-sources-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror",
                 "-I", str(SOURCE), "-I", str(SRC_ROOT), str(source), "-o", str(binary)],
                text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("MOD_PAGE_RUNTIME_SOURCES_CHECKS_PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
