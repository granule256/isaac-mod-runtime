"""Vanilla PC ReplaceSpritesheet reads its two arguments and ignores trailing values."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .test_lua_sprite import HARNESS, SCRIPT, SOURCE
from .test_support import build_lua_harness
from . import test_support


class SpriteExtraArgumentsTests(unittest.TestCase):
    def test_replace_spritesheet_accepts_mod_compatibility_arguments(self):
        script = SCRIPT.replace(
            "sprite:ReplaceSpritesheet(4, 'gfx/replaced.png')",
            "assert(select('#',sprite:ReplaceSpritesheet(4, 'gfx/replaced.png', true))==0)",
        ).replace("sprite:ReplaceSpritesheet(1, '')",
                  "sprite:ReplaceSpritesheet(1, '', false, 'ignored')")
        with tempfile.TemporaryDirectory(prefix="isaac-sprite-extra-") as temporary:
            flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS
                          if not flag.startswith("-DEXL_DIAGNOSTIC_STAGE="))
            with patch.object(test_support, "HARNESS_COMPILE_FLAGS", flags):
                binary = build_lua_harness(source_root=SOURCE, workdir=Path(temporary),
                                           harness_source=HARNESS.replace("@SCRIPT@", script))
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
