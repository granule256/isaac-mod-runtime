"""清单目录 → 原生页条目来源（读 `metadata.xml` 的 `<name>`，取不到退目录名）。

判据都在宿主上用**假读文件**跑：路径怎么拼、读失败怎么办、名字落进 arena、装不下整体放弃。
真机上只剩"`ReadTextFile` 能不能读到"这一件事（那是既有面），不会把接线错误带到设备上。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "mod_page_sources.hpp"

#include <cstdio>
#include <cstring>

using isaac::runtime::CollectModPageSources;
using isaac::runtime::ModPageEntrySource;
using isaac::runtime::ModPageTextReader;
using isaac::runtime::MountedReadResult;
using isaac::runtime::ResolveThenRead;

namespace {

int failures = 0;
int reads = 0;
bool lastPathOk = false;

void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}

// 假读文件：只认两个路径，其余当"文件不存在"。
bool FakeReader(void*, const char* path, char* buffer, std::size_t capacity, std::size_t* length) {
    ++reads;
    lastPathOk = false;
    const char* xml = nullptr;
    if (std::strcmp(path, "rom:/isaac_mods/mods/AlphaMod/metadata.xml") == 0) {
        lastPathOk = true;
        xml = "<mod><name>Alpha \xe4\xb8\xad\xe6\x96\x87 &amp; Co</name></mod>";
    } else if (std::strcmp(path, "rom:/isaac_mods/mods/BetaMod/metadata.xml") == 0) {
        lastPathOk = true;
        xml = "<mod><description>no name here</description></mod>";
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
    const char* directories[3] = {"AlphaMod", "BetaMod", "GammaMod"};
    const bool enabled[3] = {true, false, true};
    const bool outdated[3] = {false, false, true};
    ModPageEntrySource sources[3]{};
    char arena[256]{};
    char path[isaac::runtime::kModPageMetadataPathCapacity]{};
    char text[isaac::runtime::kModPageMetadataCapacity]{};

    const std::uint32_t count = CollectModPageSources(sources, 3, directories, 3, enabled,
                                                      outdated, &FakeReader, nullptr, arena,
                                                      sizeof(arena), path, text);
    Check(count == 3, "三个目录都该收集到");
    Check(reads == 3, "每个目录都要读一次 metadata.xml");
    Check(std::strcmp(sources[0].displayName, "Alpha \xe4\xb8\xad\xe6\x96\x87 & Co") == 0,
          "有名取 <name>（含中文与实体解码）");
    Check(std::strcmp(sources[1].displayName, "BetaMod") == 0,
          "metadata.xml 里没有 <name> ⇒ 退目录名");
    Check(std::strcmp(sources[2].displayName, "GammaMod") == 0, "读不到文件 ⇒ 退目录名");
    Check(sources[0].enabled && !sources[1].enabled && sources[2].enabled, "启用标志透传");
    Check(!sources[0].outdated && sources[2].outdated, "旧版标志透传");
    for (int i = 0; i < 3; ++i) {
        const auto addr = reinterpret_cast<std::uintptr_t>(sources[i].displayName);
        Check(addr >= reinterpret_cast<std::uintptr_t>(arena) &&
              addr < reinterpret_cast<std::uintptr_t>(arena) + sizeof(arena),
              "名字必须落在 arena 里（稳定内存）");
    }

    // 装不下 ⇒ 整体放弃（半截列表比空列表更容易误判）。
    {
        ModPageEntrySource small[2]{};
        char arena2[256]{};
        Check(CollectModPageSources(small, 2, directories, 3, enabled, outdated, &FakeReader,
                                    nullptr, arena2, sizeof(arena2), path, text) == 0,
              "目录数超过容量 ⇒ 整体放弃");
    }
    // 名字区太小 ⇒ 整体放弃。
    {
        ModPageEntrySource out[3]{};
        char tiny[4]{};
        Check(CollectModPageSources(out, 3, directories, 3, enabled, outdated, &FakeReader,
                                    nullptr, tiny, sizeof(tiny), path, text) == 0,
              "名字区放不下 ⇒ 整体放弃");
    }
    // 目录名为空 ⇒ 拒绝（否则会拼出 mods//metadata.xml 这种路径）。
    {
        const char* bad[1] = {""};
        ModPageEntrySource out[1]{};
        char arena3[64]{};
        Check(CollectModPageSources(out, 1, bad, 1, nullptr, nullptr, &FakeReader, nullptr,
                                    arena3, sizeof(arena3), path, text) == 0, "空目录名必须拒绝");
    }

    // ---- ResolveThenRead：**绝不盲开**（解析不到挂载就不许调 reader）----
    {
        int readerCalls = 0;
        auto countingReader = +[](void* ctx, const char*, char*, std::size_t,
                                  std::size_t*) -> bool {
            ++*static_cast<int*>(ctx);
            return true;
        };
        auto missingResolver = +[](void*, const char*, char*, std::size_t) -> bool { return false; };
        auto presentResolver = +[](void*, const char*, char* out, std::size_t cap) -> bool {
            const char* resolved = "rom:/resolved.xml";
            const std::size_t n = std::strlen(resolved);
            if (n + 1 > cap) { return false; }
            std::memcpy(out, resolved, n + 1);
            return true;
        };
        auto failingReader = +[](void*, const char*, char*, std::size_t, std::size_t*) -> bool {
            return false;
        };
        char resolved[64]{};
        char text[64]{};
        std::size_t length = 0;
        Check(ResolveThenRead("rom:/x.xml", missingResolver, nullptr, countingReader, &readerCalls,
                              resolved, sizeof(resolved), text, sizeof(text), &length) ==
                  MountedReadResult::NotMounted,
              "没有挂载实体 ⇒ NotMounted");
        Check(readerCalls == 0, "没有挂载实体时**不许**去读（盲开会 Abort）");
        Check(ResolveThenRead("rom:/x.xml", presentResolver, nullptr, countingReader, &readerCalls,
                              resolved, sizeof(resolved), text, sizeof(text), &length) ==
                  MountedReadResult::Read,
              "有挂载实体且读成功 ⇒ Read");
        Check(readerCalls == 1, "有挂载实体时才读，且只读一次");
        Check(std::strcmp(resolved, "rom:/resolved.xml") == 0, "reader 收到的是**解析后**的路径");
        Check(ResolveThenRead("rom:/x.xml", presentResolver, nullptr, failingReader, nullptr,
                              resolved, sizeof(resolved), text, sizeof(text), &length) ==
                  MountedReadResult::ReadFailed,
              "有挂载但读失败 ⇒ ReadFailed（要和 NotMounted 分开）");
        Check(ResolveThenRead(nullptr, presentResolver, nullptr, countingReader, &readerCalls,
                              resolved, sizeof(resolved), text, sizeof(text), &length) ==
                  MountedReadResult::InvalidArgument,
              "空路径 ⇒ InvalidArgument");
    }

    if (failures != 0) { std::printf("MOD_PAGE_SOURCES_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("MOD_PAGE_SOURCES_CHECKS_PASSED\n");
    return 0;
}
'''


class ModPageSourcesTests(unittest.TestCase):
    def test_collection_on_host_with_fake_reader(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-mod-page-sources-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("MOD_PAGE_SOURCES_CHECKS_PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
