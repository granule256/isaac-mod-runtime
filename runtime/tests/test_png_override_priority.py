"""贴图桥的**优先级规则**：模组的 PNG 要能顶掉本体的 `.pcx`。

## 为什么要有这条门禁

用户装了 `visible tinted rocks`（X 石头显形）——整包放在 `resources-dlc3/` 里，一个像素都没变。
两个原因，这条门禁钉的是第二个：

1. 那个目录过去根本没被挂载（`resources-dlc3` 是 PC 的忏悔层，见
   `runtime/tests/integration/test_content_mount_service.py`）；
2. **桥只在"`.pcx` 不存在"时补位**：它先调 `original(path)`，只要答得出来（哪怕答的是**本体**
   那份 `.pcx`）就直接交回 ⇒ 模组的 PNG 永远轮不到。而贴图替换类模组要覆盖的目标，在本体
   （Switch 版）**正是已存在的 `.pcx`**。

所以新规则是：`.pcx` 的原函数结果**不是模组自己的文件**时，再问一次同名 `.png`，问到就用它。
判据 `IsModMountedPath`（路径形状 `rom:/isaac_mods/…`，依据 Stage147 真机读数
`docs/问题与解决记录.md:4872`）抽在头文件里，本测试直接测它，并在源码层面钉住调用次序。

## 断言口径

1. `rom:/isaac_mods/mods/<任意>/…` ⇒ true；本体路径（`rom:/resources/…`）⇒ false；
   `nullptr`/空串 ⇒ false（**不许**对空指针调 `strncmp`）；
2. 源码次序：`IsModMountedPath(mounted)` 那次早退必须**早于**构造 `.png` 探测（`pngPath`），
   否则就退化成"模组自带 `.pcx` 也会被 PNG 抢"；
3. 探测必须走 `original(self, pngPath)`（**原函数**）——自己拼路径那条路已经用三次真机
   Abort 换来过教训（引擎传下来的路径被它自己的 `CreateCleanPath` 清洗过）。
"""

import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
BRIDGE = SOURCE / "image_pcx_bridge_hook.cpp"

DRIVER = textwrap.dedent(
    r"""
    #include "image_pcx_bridge_hook.hpp"

    #include <cstdio>

    using isaac::runtime::bridge::IsModMountedPath;

    int main() {
        int failures = 0;
        const auto check = [&failures](bool actual, bool expected, const char* what) {
            if (actual != expected) {
                std::printf("FAILED_CHECK %s\n", what);
                ++failures;
            }
        };
        check(IsModMountedPath("rom:/isaac_mods/mods/visible tinted rocks_3002235272/resources-dlc3/gfx/grid/rocks_basement.pcx"),
              true, "mod resources-dlc3 path");
        check(IsModMountedPath("rom:/isaac_mods/mods/External Item Descriptions/resources/gfx/eid_inline_icons.pcx"),
              true, "mod resources path");
        check(IsModMountedPath("rom:/resources/gfx/grid/rocks_basement.pcx"), false,
              "base game path");
        check(IsModMountedPath("rom:/rp_patch/resources/gfx/grid/rocks_basement.pcx"), false,
              "repentance patch path");
        check(IsModMountedPath(nullptr), false, "null pointer");
        check(IsModMountedPath(""), false, "empty string");
        // 前缀必须是**整段**：`rom:/isaac_mods_backup/…` 不是模组目录。
        check(IsModMountedPath("rom:/isaac_mods_backup/x.pcx"), false, "prefix must match whole segment");
        if (failures != 0) {
            std::printf("PNG_OVERRIDE_FAILURES %d\n", failures);
            return 1;
        }
        std::printf("PNG_OVERRIDE_CHECKS_PASSED\n");
        return 0;
    }
    """
)


def host_compiler():
    for candidate in ("clang++", "g++"):
        if shutil.which(candidate):
            return candidate
    return None


class PngOverridePriorityTests(unittest.TestCase):
    def test_mod_path_predicate(self):
        """判据本身：只有模组目录下的挂载路径才让位、其它一律交回。"""
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("需要宿主 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="png-override-") as temporary:
            directory = Path(temporary)
            source = directory / "png_override.cpp"
            binary = directory / "png_override"
            source.write_text(DRIVER, encoding="utf-8")
            compile_result = subprocess.run(
                [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                 "-I", str(SOURCE), str(source), "-o", str(binary)],
                capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)

    def test_probe_order_and_original_function(self):
        """源码次序：先判"是不是模组文件"，再探测 `.png`；探测必须走 `original`。

        注意：同一个文件里**另一个**回调（`ImagePcx::Load` 的兜底）也会构造 `.png` 路径，
        所以断言必须锚在"路径解析回调"这一段里 —— 否则比的是两个不同函数里的位置。
        """
        text = BRIDGE.read_text(encoding="utf-8")
        callback = text.index("EntryRelayContentGetMountedFilePathCallback(void* self, const char* path) {")
        body = text[callback:]
        mod_gate = body.index("if (isaac::runtime::bridge::IsModMountedPath(mounted))")
        probe = body.index('std::memcpy(pngPath + pathLen - 4, ".png", 4)')
        self.assertLess(mod_gate, probe,
                        "模组自带的 .pcx 必须先原样交回，不能被 PNG 抢")
        self.assertIn("char* pngMounted = original(self, pngPath);", body)
        # `pngOverrideWins` 只在"原结果非空（= 本体那份让位了）"时加一。
        self.assertIn("++g_imagePcxDiag.pngOverrideWins;", body)

    def test_diagnostics_slot_is_named_for_the_new_counter(self):
        """诊断结构体那一格（老 `reserved`）已改名为 `pngOverrideWins`，读数工具按同一偏移解。"""
        text = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("std::uint32_t pngOverrideWins;", text)
        self.assertNotIn("std::uint32_t reserved;", text)
        reader = (ROOT / "tools" / "read_device_state_via_gdb.py").read_text(encoding="utf-8")
        self.assertIn("模组 PNG 顶掉本体 .pcx", reader)


if __name__ == "__main__":
    unittest.main()
