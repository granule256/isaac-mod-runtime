#!/usr/bin/env python3
"""批次预检：在**跑全量门禁之前**，用几秒钟把"最容易红、且原因最单一"的那几条门禁跑掉。

## 为什么要有它

这个仓库的全量门禁约 145 秒，而它红的时候**经常是"一个根因让 30 多个模块同时红"**
（2026-09-18 三次都是这样：命名空间限定符、宿主 harness 少一行弱默认桩、存档目录缺 README）。
那时人容易顺着第一屏错误去查，而真正该看的是那一条。

所以这里把"每次改完几乎必然要过的六件事"抽出来单独跑（合计约半秒）：

| 门禁 | 它抓什么 | 踩过的坑 |
| --- | --- | --- |
| `test_change_archive_completeness` | 留痕完整性（日志↔存档双向、README、change.patch、`.gitattributes`） | 09-17 一天漏 4 个目录；`change.patch` 必须在 `git add` **之前**生成，否则嵌套套件看不到它 |
| `test_lua_api_stub_ledger` | 接口"安全桩"台账（条数只能降、每条要写理由、修好的不许回退） | "有目录行"曾被当成"已实现" |
| `test_callback_surface` | 回调面台账（74 条不许丢、`unknown` 只降不升） | 覆盖率一度多算一条 |
| `test_callback_dispatch_counters` | 派发计数这条读数通道两头不许漂（表长/符号名/真的请求了） | 偏移过期会让真机读数骗人 |
| `test_lua_callback_dispatch_sites` | `HasDispatchSite` 名单 == 代码里真实的派发调用 | **注释里抄了派发调用的字面写法** ⇒ 名单凭空多一条 |
| `test_elf_syms` | 读数工具默认符号 ELF 里能解析到当前符号 | 构建产物放错目录（`.gdbsym-artifacts/` 才是正式落点） |

`--all` 再加上 `test_engine_offset_signatures`（约 34 秒，它抓"新偏移常量没登记进
`tools/engine_symbol_signatures.json`"，修法是跑 `tools/gen_engine_symbol_signatures.py`）。

## 用法

    python3 tools/preflight_batch.py           # 快档（约 0.5 秒）
    python3 tools/preflight_batch.py --all     # 加上偏移常量台账那条
    python3 tools/preflight_batch.py --json    # 给脚本用的结果

退出码：全部通过 = 0；有红 = 1。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 快档：合计约 0.5 秒。顺序按"最常先红"排。
FAST_MODULES = (
    "runtime.tests.test_change_archive_completeness",
    "runtime.tests.test_lua_api_stub_ledger",
    "runtime.tests.test_callback_surface",
    "runtime.tests.test_callback_dispatch_counters",
    "runtime.tests.test_lua_callback_dispatch_sites",
    "runtime.tests.test_elf_syms",
)

#: 慢档（约 34 秒）：新偏移常量没登记时它会红，并**连带**让嵌套套件那条一起红。
SLOW_MODULES = ("runtime.tests.test_engine_offset_signatures",)

#: 每条门禁红了之后"下一步该去哪"——把这一个月踩过的坑直接摆在这里，省一次翻文档。
HINTS = {
    "test_change_archive_completeness": (
        "留痕缺项：当天日志引用的存档子目录要存在、磁盘上的子目录要被日志引用；"
        "每个目录要有 README.md，且要有 change.patch（或在 README 里写明「无代码改动」）；"
        "含逐字节产物的目录根要有 .gitattributes（`* -text`）。"
        "⚠️ change.patch 必须在 `git add` 之前生成 —— 嵌套套件按 `git ls-files` 复制工作区。"
        "脚手架：`python3 tools/new_change_batch.py <NNN-主题>`。"
    ),
    "test_lua_api_stub_ledger": (
        "接口台账：源码里认出的桩集合必须与 tools/lua_api_stub_ledger.json 双向一致；"
        "条数只能降（降了要同步改 STUB_BUDGET）；修好的要加进 FIXED_AND_MUST_STAY_FIXED。"
        "看现状：`python3 tools/lua_api_stub_report.py`。"
    ),
    "test_callback_surface": (
        "回调面台账：74 条不许丢、每条要有 status 与 note、`unknown` 只能降。"
        "看现状：`python3 tools/callback_surface.py`（改完台账用 --write）。"
    ),
    "test_callback_dispatch_counters": (
        "派发计数这条读数通道：表长 / 三个符号名 / 读数工具真的请求了它们，"
        "三者必须一致；累加点必须在派发器的两个入口各一处。"
    ),
    "test_lua_callback_dispatch_sites": (
        "派发点一致性：`HasDispatchSite` 名单 == 代码里真实的派发调用。"
        "★ 最常见原因：**注释或字符串里抄了那种调用的字面写法**（这条门禁是纯文本匹配、"
        "连注释一起扫）—— 改注释即可，别去改名单。"
    ),
    "test_elf_syms": (
        "读数工具默认符号 ELF：正式构建必须落在 runtime/.gdbsym-artifacts/"
        "（放别处会让门禁按设计判红、真机读数用过偏移）。"
    ),
    "test_engine_offset_signatures": (
        "新偏移常量没登记 ⇒ 跑 `python3 tools/gen_engine_symbol_signatures.py`。"
        "它还会**连带**让嵌套套件（test_game_file_reader_stage10）一起红 —— 先修这条根因。"
    ),
}


def run(module: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", module],
        cwd=ROOT, text=True, capture_output=True,
    )
    return {
        "module": module,
        "ok": result.returncode == 0,
        "detail": (result.stdout + result.stderr).strip(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批次预检（全量门禁之前先跑这一小撮）")
    parser.add_argument("--all", action="store_true", help="连 34 秒那条偏移常量台账一起跑")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    modules = list(FAST_MODULES) + (list(SLOW_MODULES) if args.all else [])
    results = [run(module) for module in modules]
    failures = [item for item in results if not item["ok"]]

    if args.json:
        print(json.dumps({"results": results, "failures": [f["module"] for f in failures]},
                         ensure_ascii=False, indent=2))
        return 1 if failures else 0

    for item in results:
        mark = "✓" if item["ok"] else "✗"
        print(f"  {mark} {item['module'].removeprefix('runtime.tests.')}"
              + ("" if item["ok"] else "    ← 先修这条"))
    if failures:
        print()
        for item in failures:
            print(f"== {item['module']} ==")
            hint = HINTS.get(item["module"].rsplit(".", 1)[-1])
            if hint:
                print(f"   提示：{hint}")
            tail = item["detail"].splitlines()[-12:]
            print("   " + "\n   ".join(tail))
            print()
        print(f"预检没过（{len(failures)} 条）。修完再跑 `python3 tools/run_tests.py`。")
        return 1
    print()
    print("预检全过 ⇒ 可以跑全量门禁 `python3 tools/run_tests.py`。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
