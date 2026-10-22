#!/usr/bin/env python3
"""环境面地基 · 回调（`ModCallbacks`）：PC 有什么 / 我们派发了哪些 / 还缺什么。

## 为什么先做这一面

用户的原话：「模组那么多，没有办法一个个测的……应该从兼容层入手」。这是对的：
**不能靠测模组，要靠测环境**。而在所有环境面里，**回调是模组接收一切事件的唯一通道**：

* 我们**没派发**的回调 ⇒ 注册了它的模组**静默不工作**（不报错、不崩，只是那个功能不生效）；
* 2026-09-17 的套装进度恒 `(0/3)` 就属于这一类（"事件没送到"）——只是那次的断点在**部署**
  （一份 IPS 补丁被改名禁用），不在实现里。

## 真值源

`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md` 的表格（PC 文档快照，随仓库走）。
**不要用 `grep -c '^|'` 数条数** —— 那会把表头与说明行算进去（2026-09-17 我就这么数出过一个
虚高的 "222"，实际是 74）。

## 产出

* `tools/callback_surface.json`：每条 = `{id, name, args, returns, status, where, note}`；
* 屏幕报告：覆盖率 + 按缺口列出的待补清单。

`status` 取值与含义：

| status | 含义 |
| --- | --- |
| `dispatched` | 运行时**已经**在派发（代码里有派发点） |
| `hookable` | 游戏里**已有对应挂点**可以转发，只差接线 |
| `needs_hook` | 需要新挂点（先要定位游戏里的触发点） |
| `platform` | PC 专属、Switch 侧没有对应机制（写明理由） |
| `unknown` | 还没查（默认值，门禁会盯着这个数不许涨） |

用法：

    python3 tools/callback_surface.py            # 报告
    python3 tools/callback_surface.py --write    # 重新生成 tools/callback_surface.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "analysis" / "isaacdocs-snapshot" / "docs" / "enums" / "ModCallbacks.md"
DESCRIPTOR = ROOT / "runtime" / "src" / "domain" / "callback" / "callback_descriptor.hpp"
MOD_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "mod_api.cpp"
SURFACE = ROOT / "tools" / "callback_surface.json"

STATUSES = {"dispatched", "hookable", "needs_hook", "platform", "pc_inactive", "unknown"}


def parse_dispatch_site_names() -> set[str]:
    """`HasDispatchSite()` 名单 → {常量名去掉 `kCallback` 前缀}。

    这是"到底有没有派发点"的**代码侧真值源**（设备侧那份常驻状态面报的就是它），
    所以台账的 `dispatched` 必须按它算，而不是按"有没有常量"算。
    """
    text = MOD_API.read_text(encoding="utf-8")
    start = text.index("bool HasDispatchSite(")
    body = text[start:text.index("}", start)]
    return set(re.findall(r"id\s*==\s*kCallback([A-Za-z0-9_]+)", body))


def parse_pc_table() -> list[dict]:
    """解析 PC 文档快照里的 `ModCallbacks` 表格。

    ⚠️ 真值源在 `.gitignore` 的 `analysis/` 下、**不进 git**（所以别的机器/副本里没有它）。
    文档不存在时退化成读台账里的**名单快照**（`pc_entries_snapshot`）—— 门禁走的就是快照那条路。
    """
    if not DOC.is_file():
        snapshot = load_surface().get("pc_entries_snapshot") or []
        print(f"（文档快照不在：{DOC.relative_to(ROOT)} ⇒ 用台账里的名单快照兜底，{len(snapshot)} 条）")
        return [{"id": e["id"], "name": e["name"], "args": "", "returns": ""} for e in snapshot]
    text = DOC.read_text(encoding="utf-8")
    entries: dict[int, dict] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 6 or not re.fullmatch(r"\d+", cells[1]):
            continue
        match = re.match(r"(MC_\w+)", cells[2])
        if match is None:
            continue
        entries[int(cells[1])] = {
            "id": int(cells[1]),
            "name": match.group(1),
            "args": cells[3],
            "returns": cells[5],
        }
    return [entries[key] for key in sorted(entries)]


def parse_dispatched() -> dict[int, str]:
    """我们**真的会派发**的那些回调。

    判据两条，缺一不可（2026-09-18 更正）：

    1. `callback_descriptor.hpp` 里有 id 常量（有常量才谈得上派发）；
    2. `mod_api.cpp` 的 `HasDispatchSite()` 名单里有它 —— 那份名单是"到底有没有派发点"的
       **代码侧真值源**，设备侧那份常驻状态面报的就是它。

    更正原因：原来只认第 1 条，于是 `MC_INPUT_ACTION`(13) 被算成"已派发"（常量在、
    **派发点没有** —— 历史上因为"从不触发"被刻意删掉了）。后果不是崩溃，而是**进度口径
    比真机事实多一条**，而这份台账正是"回调面覆盖了多少"的唯一进度来源。
    """
    text = DESCRIPTOR.read_text(encoding="utf-8")
    wired = parse_dispatch_site_names()
    out: dict[int, str] = {}
    for match in re.finditer(r"inline constexpr CallbackId (kCallback\w+) = (\d+);", text):
        name = match.group(1)
        if name == "kCallbackMaximumId":
            continue
        if name.removeprefix("kCallback") not in wired:
            continue
        out[int(match.group(2))] = name
    return out


def load_surface() -> dict:
    if SURFACE.is_file():
        return json.loads(SURFACE.read_text(encoding="utf-8"))
    return {"schema": "isaac-callback-surface/1", "rows": {}}


def main() -> int:
    parser = argparse.ArgumentParser(description="回调环境面报告")
    parser.add_argument("--write", action="store_true", help="重新生成 tools/callback_surface.json")
    args = parser.parse_args()

    pc = parse_pc_table()
    dispatched = parse_dispatched()
    surface = load_surface()
    rows: dict[str, dict] = surface.get("rows", {})

    # 已派发的：以代码为准（自动修正），并把 PC 侧的元数据补进去。
    for entry in pc:
        key = entry["name"]
        row = rows.setdefault(key, {})
        row.update({"id": entry["id"], "name": key, "args": entry["args"],
                    "returns": entry["returns"]})
        row.setdefault("status", "unknown")
        row.setdefault("where", "")
        row.setdefault("note", "")
        if entry["id"] in dispatched:
            row["status"] = "dispatched"
            row["where"] = row["where"] or f"callback_descriptor.hpp: {dispatched[entry['id']]}"

    # 反向修正：标着 `dispatched` 但代码里**没有派发点**的（常量在、名单不在）⇒ 退回 `hookable`。
    # 不这么修的话，历史上被误标的那几条会一直留着（`status` 只会被往上写）。
    for key, row in rows.items():
        if row.get("status") != "dispatched" or row.get("id") in dispatched:
            continue
        row["status"] = "hookable"
        row["where"] = ""
        note = row.get("note") or ""
        row["note"] = (note + " " if note else "") + (
            "⚠️ 2026-09-18 更正：台账原先按『有常量』算作已派发，但它没有派发点"
            "（`HasDispatchSite` 名单里刻意不含它）⇒ 退回 hookable。"
            "判据已改为与设备侧同一真值源（`HasDispatchSite`）。")

    surface["rows"] = rows
    surface["source_of_truth"] = str(DOC.relative_to(ROOT))
    if args.write:
        SURFACE.write_text(json.dumps(surface, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        print(f"已写入 {SURFACE.relative_to(ROOT)}（{len(rows)} 条）")

    counts: dict[str, int] = {}
    for row in rows.values():
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    total = len(rows)
    done = counts.get("dispatched", 0)
    print(f"\n回调环境面：PC {total} 条，已派发 **{done}**（{100 * done // max(1, total)}%）")
    for status in ("hookable", "needs_hook", "platform", "pc_inactive", "unknown"):
        if counts.get(status):
            print(f"  {status:11s} {counts[status]:3d}")
    print("\n未派发的（按 ID）：")
    for key in sorted(rows, key=lambda k: rows[k]["id"]):
        row = rows[key]
        if row["status"] == "dispatched":
            continue
        note = f"  ← {row['note'][:60]}" if row["note"] else ""
        print(f"  {row['id']:3d} {key:34s} {row['status']:10s}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
