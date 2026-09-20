#!/usr/bin/env python3
"""兼容壳：缺口报告工具已改名为 `tools/mod_api_gap_report.py`（它对**任意模组**都适用）。

保留这个文件名是因为历史引用很多（门禁、台账、`docs/` 与若干存档 README 里都写着旧名），
删掉会让那些引用指向不存在的文件。**新代码请用新名字**，行为完全一致。

为什么这里不写 `from mod_api_gap_report import main`：门禁用
`importlib.util.spec_from_file_location(...)` 按**路径**加载本文件，那种加载方式不会把
`tools/` 放进 `sys.path` ⇒ 直接 import 会 ModuleNotFoundError（2026-09-19 实测踩到）。
所以这里按**文件路径**加载同目录的那个模块。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_TARGET = pathlib.Path(__file__).resolve().parent / 'mod_api_gap_report.py'
_spec = importlib.util.spec_from_file_location('mod_api_gap_report', _TARGET)
if _spec is None or _spec.loader is None:  # pragma: no cover - 文件被删才会发生
    raise SystemExit(f'找不到 {_TARGET}（缺口报告工具是不是被改名/删掉了？）')
_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault('mod_api_gap_report', _module)
_spec.loader.exec_module(_module)

main = _module.main

if __name__ == '__main__':
    sys.exit(main())
