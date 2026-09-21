"""模组**显示名**（`metadata.xml` 的 `<name>`）—— 模组页那张纸上的字就是它给的。

为什么单独一条门禁：这是"PC 一致"里唯一能离线验死的一环。写死字符串只能验"页面画得出来"，
验不了"名字取得对"。口径（大小写、属性、空白、实体、退回目录名）见 `mod_display_name.hpp`。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "mod_display_name.hpp"

#include <cstdio>
#include <cstring>
#include <string_view>

using isaac::runtime::ExtractModDisplayName;

namespace {
int failures = 0;

void Expect(std::string_view xml, const char* expected, const char* label) {
    char buffer[128]{};
    const bool ok = ExtractModDisplayName(xml, buffer, sizeof(buffer));
    if (expected == nullptr) {
        if (ok) { std::printf("FAIL %s（本不该取到，却得到 %s）\n", label, buffer); ++failures; }
        return;
    }
    if (!ok || std::strcmp(buffer, expected) != 0) {
        std::printf("FAIL %s（期望 %s，得到 %s）\n", label, expected, ok ? buffer : "<false>");
        ++failures;
        return;
    }
    std::printf("ok   %s -> %s\n", label, buffer);
}
}  // namespace

int main() {
    Expect("<mod><name>Visible Tinted Rocks</name></mod>", "Visible Tinted Rocks", "最简单形态");
    Expect("<mod>\n  <name>\n    External Item Descriptions\n  </name>\n</mod>",
           "External Item Descriptions", "跨行与首尾空白要 Trim");
    Expect("<name lang=\"en\">GoodTrip</name>", "GoodTrip", "开标签带属性（属性忽略）");
    Expect("<name>A &amp; B</name>", "A & B", "实体 &amp;");
    Expect("<name>x &lt; y &gt; z</name>", "x < y > z", "实体 &lt; &gt;");
    Expect("<name>First</name><name>Second</name>", "First", "只取第一个 <name>");
    Expect("<mod><name></name></mod>", nullptr, "空名字 ⇒ 交给调用方退目录名");
    Expect("<mod><name/></mod>", nullptr, "自闭合 ⇒ 没有文本");
    Expect("<mod><description>x</description></mod>", nullptr, "没有 <name>");
    Expect("<mod><NAME>Upper</NAME></mod>", nullptr, "XML 区分大小写：<NAME> 不算");
    Expect("<mod><names>Plural</names></mod>", nullptr, "<names> 不算（必须紧跟空白或 >）");
    Expect("", nullptr, "空输入");

    // 缓冲区太小 ⇒ 必须**如实失败**（而不是截断出一个假名字）。
    {
        char small[4]{};
        if (ExtractModDisplayName("<name>LongName</name>", small, sizeof(small))) {
            std::printf("FAIL 缓冲区太小却报成功：%s\n", small);
            ++failures;
        }
    }
    // 恰好放得下（含 NUL）⇒ 成功。
    {
        char exact[11]{};
        if (!ExtractModDisplayName("<name>0123456789</name>", exact, sizeof(exact)) ||
            std::strcmp(exact, "0123456789") != 0) {
            std::printf("FAIL 恰好放得下却失败\n");
            ++failures;
        }
    }

    if (failures != 0) {
        std::printf("MOD_DISPLAY_NAME_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("MOD_DISPLAY_NAME_CHECKS_PASSED\n");
    return 0;
}
'''


class ModDisplayNameTests(unittest.TestCase):
    def test_extraction_semantics_on_host(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-mod-display-name-") as directory:
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
            self.assertIn("MOD_DISPLAY_NAME_CHECKS_PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
