"""门禁：贴图桥转码缓存的**预算必须不小于"单张最大值"**。

## 为什么要有它（2026-10-10 真机踩出来的）

缓存容器的规则是"**单条超预算就不缓存**"
（`BudgetedLruCache::Insert` 第一句 `if (bytes > budget_bytes_) return false;`）。
所以预算有**两个互相独立的下界**：

1. 要能装下循环工作集（决定命中率）；
2. ★★★ **必须大于磁盘上任何一张转码后的贴图** —— 否则那一张**永远进不了缓存**，
   每次要用都重转。

批次 422 就是只按 ① 估的：把预算从 24 MiB 压到 **8 MiB**，看着"够装工作集"。
真机一验立刻露馅：`convertMicrosMax = 450.1 ms`、**单次兜底最大 607.8 ms**
（24 MiB 那版是 85.3 / 110.3 ms），最近兜底路径 = `mcm_cn_font/teammeatfont16bold_1.pcx`。
把 MCM 的 26 张字号 PNG 用 `tools/png_to_pcx.py` 全转一遍量尺寸，才看见
**单张最大 10.23 MiB**（26 张合计 59.2 MiB）⇒ 8 MiB 恰好把最大的那张结构性排除掉了。
423 改回 **16 MiB**。

★ 这条判据的作用：**把"②"变成机器判据**。以后谁再往下压预算，只要压到单张最大值以下，
门禁立刻红 —— 不用再靠"上卡跑一遍才发现菜单卡一下"。

★ 数据来源是**磁盘上真实的模组贴图**（不是硬编码数字）：
本仓库的发布目录里带着 `mod_config_menu_cn` 的字体目录，测试直接读它、真转一遍。
目录不在（浅克隆/裁剪过）时**跳过并说明**，不假装通过。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BRIDGE = ROOT / "runtime" / "source" / "image_pcx_bridge_hook.cpp"

#: 转码后最大的一张就出自这里（MCM 的中文字号）。
FONT_DIR_GLOBS = (
    "dist/*/atmosphere/contents/*/romfs/isaac_mods/mods/mod_config_menu_cn/resources/mcm_cn_font",
    "dist/*/*/atmosphere/contents/*/romfs/isaac_mods/mods/mod_config_menu_cn/resources/mcm_cn_font",
)


def budget_bytes() -> int:
    """从源码读预算（**不硬编码** —— 常量一调、判据就会开始骗人）。"""
    text = BRIDGE.read_text(encoding="utf-8")
    match = re.search(r"kImagePcxCacheBudgetBytes\s*=\s*(\d+)u\s*\*\s*1024u\s*\*\s*1024u", text)
    if not match:
        raise AssertionError(
            "在 image_pcx_bridge_hook.cpp 里找不到 `kImagePcxCacheBudgetBytes = Nu * 1024u * 1024u`；"
            "改了写法就要同步改这里（否则这条判据会静默失效）"
        )
    return int(match.group(1)) * 1024 * 1024


def font_dir() -> Path | None:
    for pattern in FONT_DIR_GLOBS:
        for candidate in sorted(ROOT.glob(pattern)):
            if candidate.is_dir():
                return candidate
    return None


def largest_png(folder: Path) -> Path:
    pngs = [p for p in folder.rglob("*.png") if p.is_file()]
    if not pngs:
        raise AssertionError(f"{folder} 里没有 .png")
    return max(pngs, key=lambda p: p.stat().st_size)


class ImagePcxCacheBudgetFloorTests(unittest.TestCase):
    def setUp(self):
        self.budget = budget_bytes()

    def test_budget_is_at_least_the_largest_single_transcode(self):
        folder = font_dir()
        if folder is None:
            self.skipTest(
                "仓库里没有 mod_config_menu_cn 的字体目录（裁剪过的检出）⇒ 无法量'单张最大值'。"
                "**这条判据在这里是没跑，不是通过**。"
            )
        sys.path.insert(0, str(ROOT / "tools"))
        from png_to_pcx import png_to_pcx  # noqa: PLC0415 - 只在需要时导入

        source = largest_png(folder)
        pcx = png_to_pcx(source.read_bytes())
        self.assertGreater(
            self.budget, len(pcx),
            f"转码缓存预算 {self.budget} 字节（{self.budget / 1048576:.2f} MiB）"
            f"**小于磁盘上最大的一张转码结果**：{source.name} → {len(pcx)} 字节"
            f"（{len(pcx) / 1048576:.2f} MiB）。\n"
            "⇒ 按 `BudgetedLruCache::Insert` 的'单条超预算不缓存'，这张图会**永远进不了缓存**，"
            "每次要用都重转（真机实测 450~600 ms/次）。\n"
            "⇒ 把 `kImagePcxCacheBudgetBytes` 加到大于它。",
        )

    def test_budget_is_a_sane_bound(self):
        # 上下界都卡一下：太小（< 一张大图）会踩上面那条；太大就失去"省内存"的意义。
        self.assertGreaterEqual(self.budget, 4 * 1024 * 1024, "预算小到不像话")
        self.assertLessEqual(self.budget, 24 * 1024 * 1024,
                             "预算超过 24 MiB ⇒ 又回到'实占 30 MB'那一版量级了（本批的目的就是省内存）")


if __name__ == "__main__":
    unittest.main()
