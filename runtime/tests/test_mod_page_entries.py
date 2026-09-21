"""原生模组页的**条目布局**门禁（批次 024）。

`Menu_Mods::Render` 要什么结构是反汇编看出来的（见 `mod_page_entries.hpp` 顶部）：
`g_Manager+0x36800` 起是 `begin/end/cap`，元素 8 字节；条目 `+0x18` 是 libc++ `std::string`
（长串形态：字节 0 的 bit0 = 1、数据指针在 `+0x28`）、`+0x138` 启用位、`+0x13a` "旧版"位。

这条门禁把那些偏移**逐字节**钉住 —— 写错的后果是"页面画出来但名字乱码/整页空白/读野指针"，
真机上很难看出来是哪一处错，所以在这里判死。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "mod_page_entries.hpp"

#include <cstdio>
#include <cstring>
#include <cstdint>

using isaac::runtime::BuildModPageEntries;
using isaac::runtime::ModPageEntrySource;
using isaac::runtime::kModPageEntryEnabledOffset;
using isaac::runtime::kModPageEntryOldOffset;
using isaac::runtime::kModPageEntryStride;
using isaac::runtime::kModPageEntryStringDataOffset;
using isaac::runtime::kModPageEntryStringOffset;

namespace {

int failures = 0;

void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}

}  // namespace

int main() {
    // 布局常量本身（改一个就在读数里对不上，所以钉死）。
    static_assert(kModPageEntryStride == 0x140, "步长");
    static_assert(kModPageEntryStringOffset == 0x18, "std::string 偏移");
    static_assert(kModPageEntryStringDataOffset == 0x28, "长串数据指针偏移");
    static_assert(kModPageEntryEnabledOffset == 0x138, "启用位");
    static_assert(kModPageEntryOldOffset == 0x13a, "旧版位");

    alignas(16) std::uint8_t entries[3 * kModPageEntryStride]{};
    std::uintptr_t pointers[3]{};
    std::uintptr_t vector[3]{};
    char arena[128]{};
    // 第二条故意超过 libc++ 短串容量（22 字节）⇒ 证明我们走的是长串形态而不是碰巧能用。
    const ModPageEntrySource sources[3] = {
        {"Visible Tinted Rocks", true, false},
        {"External Item Descriptions 中文名也要行", false, false},
        {"GoodTrip", true, true},
    };
    std::size_t used = 0;
    const std::uint32_t written = BuildModPageEntries(entries, pointers, vector, 3, sources,
                                                      arena, sizeof(arena), &used);
    Check(written == 3, "三个条目都该写成功");
    Check(used == std::strlen(sources[0].displayName) + 1 +
                   std::strlen(sources[1].displayName) + 1 +
                   std::strlen(sources[2].displayName) + 1,
          "名字副本字节数");

    // 向量三个字：begin / end / cap，元素 8 字节。
    const std::uintptr_t begin = reinterpret_cast<std::uintptr_t>(&pointers[0]);
    Check(vector[0] == begin, "begin 指向指针数组首元素");
    Check(vector[1] == begin + 8 * 3, "end = begin + 3*8");
    Check(vector[2] == vector[1], "cap = end");

    for (std::uint32_t i = 0; i < 3; ++i) {
        const std::uint8_t* entry = entries + i * kModPageEntryStride;
        Check(pointers[i] == reinterpret_cast<std::uintptr_t>(entry), "指针数组指向对应条目");
        Check((entry[kModPageEntryStringOffset] & 0x01) == 0x01, "长串标记 bit0 = 1");
        std::uintptr_t data = 0;
        std::memcpy(&data, entry + kModPageEntryStringDataOffset, sizeof(data));
        const auto* name = reinterpret_cast<const char*>(data);
        Check(std::strcmp(name, sources[i].displayName) == 0, "数据指针指向名字副本");
        std::uint64_t capacity = 0;
        std::memcpy(&capacity, entry + kModPageEntryStringOffset + 0x08, sizeof(capacity));
        Check(capacity == std::strlen(sources[i].displayName), "长串的长度字段自洽");
        Check(entry[kModPageEntryEnabledOffset] == (sources[i].enabled ? 1 : 0), "启用位");
        Check(entry[kModPageEntryOldOffset] == (sources[i].outdated ? 1 : 0), "旧版位");
        // 名字副本必须在 arena 里（稳定内存），不能是调用方那个字面量的地址。
        Check(data >= reinterpret_cast<std::uintptr_t>(arena) &&
              data < reinterpret_cast<std::uintptr_t>(arena) + sizeof(arena),
              "名字副本落在调用方给的 arena 里");
    }

    // 名字区放不下 ⇒ **整体放弃**（返回 0、不许写半截）。
    {
        alignas(16) std::uint8_t small[3 * kModPageEntryStride]{};
        std::uintptr_t smallPointers[3]{};
        std::uintptr_t smallVector[3]{};
        char tiny[4]{};
        std::size_t used2 = 123;
        const std::uint32_t written2 = BuildModPageEntries(small, smallPointers, smallVector, 3,
                                                           sources, tiny, sizeof(tiny), &used2);
        Check(written2 == 0, "名字区放不下时必须整体放弃");
        Check(used2 == 0, "放弃时名字用量记 0");
    }
    // 空名字/空指针 ⇒ 拒绝（页面上会出现空行，不如让调用方退目录名）。
    {
        alignas(16) std::uint8_t buffer[kModPageEntryStride]{};
        std::uintptr_t one = 0;
        std::uintptr_t vec[3]{};
        char arena2[16]{};
        const ModPageEntrySource bad[1] = {{"", true, false}};
        Check(BuildModPageEntries(buffer, &one, vec, 1, bad, arena2, sizeof(arena2), nullptr) == 0,
              "空名字必须拒绝");
        const ModPageEntrySource nullName[1] = {{nullptr, true, false}};
        Check(BuildModPageEntries(buffer, &one, vec, 1, nullName, arena2, sizeof(arena2),
                                  nullptr) == 0, "空指针必须拒绝");
    }

    if (failures != 0) { std::printf("MOD_PAGE_ENTRIES_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("MOD_PAGE_ENTRIES_CHECKS_PASSED\n");
    return 0;
}
'''


class ModPageEntriesTests(unittest.TestCase):
    def test_layout_on_host(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-mod-page-") as directory:
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
            self.assertIn("MOD_PAGE_ENTRIES_CHECKS_PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
