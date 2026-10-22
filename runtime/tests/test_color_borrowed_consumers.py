"""借用颜色经过现有字体、原生setter和通用ColorMod入口时必须解析到根值。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_api100_values as values_fixture
from . import test_lua_font_resources as font_fixture
from .test_support import build_lua_harness


class BorrowedColorConsumerTests(unittest.TestCase):
    def run_harness(self, source, argument):
        source = re.sub(r"namespace GameFileReader \{\n[\s\S]*?\n\}\n\}", "",
                        source, count=1)
        with tempfile.TemporaryDirectory(prefix="borrowed-color-consumer-") as work:
            binary = build_lua_harness(source_root=font_fixture.SOURCE,
                                       workdir=Path(work), harness_source=source)
            result = subprocess.run([str(binary), argument], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_font_draw_variants_read_the_borrowed_rgba_after_gc(self):
        draw = (
            "local function BorrowedColor(...) local a=Color(...);"
            "return a*Color(1,1,1,1) end\n"
            + font_fixture.DRAW_SCRIPT.replace("KColor(", "BorrowedColor(")
                .replace("  -- 默认参数路径", "  collectgarbage('collect')\n  -- 默认参数路径")
        )
        source = (font_fixture.HARNESS.replace("@RESOURCES_SCRIPT@", "")
                  .replace("@GC_SCRIPT@", "").replace("@CALLBACK_SCRIPT@", "")
                  .replace("@DRAW_SCRIPT@", draw))
        self.run_harness(source, "draw")

    def test_native_color_setters_modify_the_borrowed_root(self):
        main = values_fixture.MAIN.replace(
            "c:SetColorize(.1,.2,.3,.4)",
            "c:SetColorize(.1,.2,.3,.4);c=c:__mul(Color(1,1,1,1));same=c"
        )
        source = values_fixture.fixture.HARNESS.split("int main(", 1)[0] + main
        self.run_harness(source, "integration")
