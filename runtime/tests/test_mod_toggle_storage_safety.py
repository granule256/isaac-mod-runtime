"""门禁：**运行期绝不许写 SD 资源覆盖层**（`romfs/` 下的清单），开关状态只许进游戏存档分区。

## 为什么要有它

本项目最重的一条历史教训（`AGENTS.md`「设备取证纪律」）：往
`/atmosphere/contents/<title>/romfs/` 下写东西 ⇒ Atmosphere 下次启动重建 `romfs_metadata.bin`
⇒ **游戏在装载阶段崩**（时好时坏、极难归因）。而"模组清单" `manifest.json` 恰好在那个覆盖层里
（`rom:/isaac_mods/manifest.json`）。

模组开关要能"在游戏里关掉一个模组、重启生效"，就必须**落盘**；落盘位置选错就是踩雷。
运行时的既有做法是把它存进**游戏存档分区**（`isaac-switch-mods-state.txt`，经 `ISaveFilePort`），
本批（067）原生模组页复用同一套 —— 这条门禁把"哪条路是安全的"钉死：

1. **清单只读**：`kRomfsModManifestPath`（以及字面量 `rom:/isaac_mods/manifest.json`）在运行时代码里
   **只允许出现在读路径**（`Read*`）里，任何写/创建调用都不许沾它；
2. **开关状态不在覆盖层**：`kModToggleStateFileName` 既不是绝对路径也不含 `romfs`/`rom:/`，
   且开关服务只通过 `ISaveFilePort` 落盘；
3. **原生模组页不许自己写文件**：它只能调共用服务的写面
   （`ModMenuSetEnabled` / `ModMenuSaveToggles`），不出现任何直接的文件写调用
   —— 这样"写到哪里"永远只有一处口径。
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"
CONSTANTS = RUNTIME / "source" / "runtime_constants.hpp"
TOGGLE_STATE = RUNTIME / "src" / "domain" / "mod" / "mod_toggle_state.hpp"
TOGGLE_SERVICE = RUNTIME / "src" / "application" / "mod" / "mod_toggle_service.hpp"
MOD_MENU_API = RUNTIME / "src" / "interfaces" / "lua" / "mod_menu_api.cpp"
PROBE = RUNTIME / "source" / "probe" / "native_mods_menu_probe.cpp"

MANIFEST_SYMBOL = "kRomfsModManifestPath"
MANIFEST_LITERAL = "rom:/isaac_mods/manifest.json"
#: 写文件/创建文件的调用名（出现这些就等于"在写"）。读的那些不在此列。
WRITE_MARKERS = ("WriteTextFile", "WriteFile", "SaveFile", "ForWriting", "CreateFile", "OpenWrite")


def source_files() -> list[Path]:
    files = []
    for pattern in ("source/**/*.cpp", "source/**/*.hpp", "src/**/*.cpp", "src/**/*.hpp"):
        files.extend(RUNTIME.glob(pattern))
    return sorted(files)


class ModToggleStorageSafetyTests(unittest.TestCase):
    def test_manifest_is_only_ever_read(self):
        offenders = []
        for path in source_files():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for index, line in enumerate(lines):
                if MANIFEST_SYMBOL not in line and MANIFEST_LITERAL not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                if "constexpr char" in stripped or "inline constexpr" in stripped:
                    continue  # 常量定义本身
                window = "\n".join(lines[max(0, index - 4) : index + 5])
                if "Read" not in window:
                    offenders.append(f"{path.relative_to(ROOT)}:{index + 1}: {stripped}")
                if any(marker in window for marker in WRITE_MARKERS):
                    offenders.append(f"{path.relative_to(ROOT)}:{index + 1} 附近出现写调用: {stripped}")
        self.assertEqual(offenders, [],
                         "运行期**绝不许**写 SD 资源覆盖层里的清单 —— 见本文件头部说明")

    def test_toggle_state_lives_in_the_save_partition(self):
        text = TOGGLE_STATE.read_text(encoding="utf-8")
        match = re.search(r'kModToggleStateFileName\[\]\s*=\s*"([^"]+)"', text)
        self.assertIsNotNone(match, "开关状态文件名没找到（常量被改名了？）")
        name = match.group(1)
        for bad in ("romfs", "rom:/", "sdmc:/", "/atmosphere"):
            self.assertNotIn(bad, name,
                             f"开关状态不许落在卡上的覆盖层/绝对路径里：{name}")
        self.assertTrue(name.endswith(".txt") and "/" not in name,
                        f"开关状态应当只是存档分区里的一个文件名：{name}")
        service = TOGGLE_SERVICE.read_text(encoding="utf-8")
        self.assertIn("ISaveFilePort", service,
                      "开关服务必须经 `ISaveFilePort`（游戏存档分区）落盘，不许自己拼卡上的路径")

    def test_native_page_writes_only_through_the_shared_service(self):
        probe = PROBE.read_text(encoding="utf-8")
        # 只看**代码行**：注释里解释"为什么不能写覆盖层"是好事，不算违规。
        code = [line for line in probe.splitlines()
                if not line.strip().startswith("//") and not line.strip().startswith("*")]
        for marker in WRITE_MARKERS + ("romfs", "sdmc:/", "/atmosphere"):
            hits = [line.strip() for line in code if marker in line]
            self.assertEqual(hits, [],
                             f"原生模组页不许自己写文件/碰卡路径（代码里出现了 {marker}）：{hits}")
        self.assertIn("ModMenuSaveToggles", probe, "退出页面时的落盘必须走共用服务")
        self.assertIn("ModMenuSetEnabled", probe, "页内改开关必须走共用服务（只改内存）")

    def test_shared_service_exposes_a_write_side(self):
        header = (RUNTIME / "src" / "interfaces" / "lua" / "mod_menu_api.hpp").read_text(
            encoding="utf-8")
        self.assertIn("ModMenuSetEnabled", header)
        self.assertIn("ModMenuSaveToggles", header)
        cpp = MOD_MENU_API.read_text(encoding="utf-8")
        self.assertIn("ModMenuSetEnabled", cpp)
        self.assertIn("ModMenuSaveToggles", cpp)
        # 与 Lua 侧同一条纪律：未知目录一律拒绝（不许往状态里塞永远不生效的条目）。
        set_enabled = cpp.split("bool ModMenuSetEnabled", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("FindEntry", set_enabled,
                      "写面必须和 Lua 侧一样先判「这个目录是不是这一批扫描到的」")


if __name__ == "__main__":
    unittest.main()
