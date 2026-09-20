#!/usr/bin/env python3
"""用 **EID 自己的寻路器**在宿主上回答"`Room:GetGridPath` 该返回什么"。

## 为什么需要它（问题与解决记录 098）

真机上"地上药丸、卡片走到旁边只显示一个问号"，根因是运行时里
`Room:GetGridPath` 是个恒返回 `1000` 的占位实现（批次 7 留下），而 EID 的判据是
`collision <= 900 = 可走`（`features/eid_api.lua:3362`）⇒ `EID:HasPathToPosition` 恒 false
⇒ `attemptPathfind` 恒 false ⇒ EID 走"够不到就不给看"的隐瞒分支，只画问号。

要改就得先定**下标口径**：EID 的 `EvaluateLocation` 把 `(gx,gy)` 算成 `gx*W + gy`，
而引擎 `Room::GetGridPath(int,int) @ 0x484120` 内部是 `array[W*y + x]` —— 看着差一次转置。
真相在 EID 自己的代码里：`features/pathfinder/luafinding.lua` 的 `Initialize` 写的是
`FindVector(start.Y, start.X)`，**寻路器把 X/Y 换了一次**，所以 `gx*W+gy` 恰好等于引擎的
`W*gx... ` 口径（推导见 `docs/改动日志-20260920.md` 098）。⇒ `GetGridPath(index)` 必须
**按引擎那张表的下标直读**，不做任何转置。

本工具把这条推导放到"可执行证据"上：它**在运行时从仓库里的 EID 副本里抽出
`EID:EvaluateLocation` 与 `EID:HasPathToPosition` 两个函数的原文**（不抄一遍，避免与上游漂移），
喂给合成的 13×7 房间网格，分别用"旧口径（恒 1000）"与"新口径（真实数组）"跑一遍：

* 旧口径下**每一个场景都判"没路"** ⇒ 宿主上复现出用户的症状；
* 新口径下"全可走 / 高代价但可走"判有路，"被围死 / 被墙隔开"判没路 ⇒ 与 PC 判据一致。

## 用法

    python3 tools/room_grid_reachability_probe.py            # 跑全部场景，打印对照表
    python3 tools/room_grid_reachability_probe.py --json     # 同上，输出 JSON（给门禁消费）

宿主 Lua 解释器用**仓库自带的 vendored Lua 5.3.3**（`runtime/source/third_party/lua-5.3.3`）
编出来，落在 `runtime/.host-lua-build/`（已被 `.gitignore` 的 `runtime/.*-build/` 覆盖，
不会进 git）。没有 C 编译器时明确报错，不伪装成通过。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LUA_SRC = ROOT / "runtime" / "source" / "third_party" / "lua-5.3.3" / "src"
LUA_BUILD_DIR = ROOT / "runtime" / ".host-lua-build"
LUA_BIN = LUA_BUILD_DIR / "lua533"

#: 仓库里那份 EID（与卡上逐字节相同的那一份的上游原样）。
EID_ROOT = (ROOT / "dist" / "isaac-eid-release-20260914" / "atmosphere" / "contents"
            / "010021C000B6A000" / "romfs" / "isaac_mods" / "mods"
            / "external item descriptions_836319872")
EID_API = EID_ROOT / "features" / "eid_api.lua"

#: 要抽出来的两个函数（名字必须一字不差 —— 上游改名时这里应当红，而不是静默测别的东西）。
WANTED_FUNCTIONS = ("EvaluateLocation", "HasPathToPosition")

#: 合成房间：标准房间的网格是 **13 宽 × 7 高**（引擎 `GetGridIndex` 的 y 偏移 −120 = −3 格
#: 正是"房间在 13×13 网格里偏下 3 格"的来处），下标口径 `index = W*gy + gx`。
GRID_WIDTH = 13
GRID_HEIGHT = 7

#: EID 的"可走"阈值：`collision <= 900` 才算可走（`eid_api.lua:3362`）。
WALKABLE = 0
HEAVY_BUT_WALKABLE = 900
BLOCKED = 1000


def ensure_lua() -> Path:
    """编译（或复用）vendored Lua 5.3.3 解释器；缺编译器时抛 RuntimeError。"""
    cc = shutil.which("cc")
    if cc is None:
        raise RuntimeError("需要宿主 C 编译器（cc）来编译 vendored Lua 5.3.3")
    sources = [p for p in sorted(LUA_SRC.glob("*.c")) if p.name != "luac.c"]
    if not sources:
        raise RuntimeError(f"找不到 vendored Lua 源码：{LUA_SRC}")
    newest = max(p.stat().st_mtime for p in sources)
    if LUA_BIN.exists() and LUA_BIN.stat().st_mtime >= newest:
        return LUA_BIN
    LUA_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    command = [cc, "-O2", "-std=gnu99", f"-I{LUA_SRC}", "-o", str(LUA_BIN),
               *[str(p) for p in sources], "-lm"]
    # 刻意**不加** `LUA_USE_MACOSX`：那个宏会拉进 readline，本机没有时链接直接失败，
    # 而我们要的只是"能跑脚本"的解释器。
    subprocess.run(command, check=True, capture_output=True)
    return LUA_BIN


def function_source(name: str) -> str:
    """从 EID 的 `eid_api.lua` 里抽出 `function EID:<name>(...) ... end` 的原文。

    抽的是**上游原文**（不是抄写版）：只要上游改了这两个函数，本工具跟门禁就跟着变，
    不会出现"测的是一份和上线代码不一样的东西"。
    """
    text = EID_API.read_text(encoding="utf-8")
    anchor = f"function EID:{name}("
    # 上游的写法是"函数体结束那一行顶格的 `end`"，这两个函数内部都没有嵌套函数，
    # 所以取"顶格 end 行"为止是最省事又不会误伤的口径；上游改形状时这里会抛错（而不是静默测别的）。
    match = re.search(rf"^function EID:{re.escape(name)}\(.*?^end$", text, re.S | re.M)
    if match is None:
        raise RuntimeError(f"{EID_API} 里找不到以顶格 end 收尾的 {anchor}")
    return match.group(0)


def _scenarios() -> list[dict]:
    """四个场景：网格下标口径一律 `index = W*gy + gx`。"""
    def blank() -> list[int]:
        return [WALKABLE] * (GRID_WIDTH * GRID_HEIGHT)

    def at(cells: list[int], gx: int, gy: int) -> int:
        return gy * GRID_WIDTH + gx

    # ① 全可走：玩家在 (2,3)，目标在 (10,3)
    open_room = blank()

    # ② 目标被一圈不可走围死：目标 (10,3) 的上下左右
    sealed = blank()
    for gx, gy in ((9, 3), (11, 3), (10, 2), (10, 4)):
        sealed[at(sealed, gx, gy)] = BLOCKED

    # ③ 竖墙把房间分成两半（第 6 列全不可走）：玩家在左、目标在右
    walled = blank()
    for gy in range(GRID_HEIGHT):
        walled[at(walled, 6, gy)] = BLOCKED

    # ④ 高代价但**仍可走**（判据是 `<= 900`）：整行 (·,4) 设成 900
    heavy = blank()
    for gx in range(GRID_WIDTH):
        heavy[at(heavy, gx, 4)] = HEAVY_BUT_WALKABLE

    return [
        {"name": "全可走（期望：有路）", "costs": open_room, "expect_path": True},
        {"name": "目标被围死（期望：没路）", "costs": sealed, "expect_path": False},
        {"name": "竖墙隔开（期望：没路）", "costs": walled, "expect_path": False},
        {"name": f"高代价但可走（{HEAVY_BUT_WALKABLE}，期望：有路）", "costs": heavy,
         "expect_path": True},
    ]


def _driver_lua(conventions: list[str]) -> str:
    """生成驱动脚本：mock 房间 + 抽出来的两个 EID 函数 + 逐场景跑。"""
    pieces = [f"""
-- 本脚本由 tools/room_grid_reachability_probe.py 生成，不要手改。
local GRID_WIDTH, GRID_HEIGHT = {GRID_WIDTH}, {GRID_HEIGHT}
local EID_ROOT = [[{EID_ROOT}]]
package.path = EID_ROOT .. "/?.lua;" .. package.path

-- Isaac 的 Vector：EID 传给寻路器的是它的 .X/.Y。
local function Vector(x, y) return {{ X = x, Y = y }} end
_G.Vector = Vector

-- mock 房间：宽高 + 一张 int32 通行代价表（引擎 `Room + 0xE98` 的那张，下标 = W*gy + gx）
local room = {{}}
room.GetGridWidth = function() return GRID_WIDTH end
room.GetGridHeight = function() return GRID_HEIGHT end
room.GetGridPath = function(_, index)
    if CONVENTION == "engine-array" then
        if index < 0 or index >= GRID_WIDTH * GRID_HEIGHT then return 0 end  -- 引擎越界给 0
        return room.costs[index + 1]
    end
    return 1000  -- 旧口径：运行时里的占位（恒"不可走"）
end
-- 引擎 `Room::GetGridIndex(Vector) @ 0x459e3c`：gx = trunc((x-40)/40+0.5)、gy = trunc((y-120)/40+0.5)
room.GetGridIndex = function(_, pos)
    local gx = math.floor((pos.X - 40) / 40 + 0.5)
    local gy = math.floor((pos.Y - 120) / 40 + 0.5)
    if gx < 0 or gy < 0 or gx >= GRID_WIDTH or gy >= GRID_HEIGHT then return -1 end
    return GRID_WIDTH * gy + gx
end
_G.game = {{ GetRoom = function() return room end }}

-- EID 侧：只放抽出原文需要的两个字段
EID = {{}}
EID.Pathfinder = require("features.pathfinder.luafinding")
"""]

    for name in WANTED_FUNCTIONS:
        pieces.append(f"-- ↓↓↓ 以下函数原文抽自 {EID_API.name}（上游原样，不抄写）\n")
        pieces.append(function_source(name))
        pieces.append("\n")

    pieces.append("""
-- 场景表由 Python 侧注入
local scenarios = SCENARIOS
local results = {}
for _, scenario in ipairs(scenarios) do
    room.costs = scenario.costs
    local startPos = Vector(scenario.start_x, scenario.start_y)
    local endPos = Vector(scenario.end_x, scenario.end_y)
    local hasPath = EID:HasPathToPosition(startPos, endPos)
    -- 顺带记下寻路器看到的起点/终点格坐标，便于核对口径
    local startGI = room:GetGridIndex(startPos)
    local endGI = room:GetGridIndex(endPos)
    results[#results + 1] = {
        name = scenario.name,
        has_path = hasPath and true or false,
        start_index = startGI,
        end_index = endGI,
    }
end

local out = {}
for _, row in ipairs(results) do
    out[#out + 1] = string.format("%s\\t%s\\t%d\\t%d", row.name,
        row.has_path and "有路" or "没路", row.start_index, row.end_index)
end
print(table.concat(out, "\\n"))
""")
    return "".join(pieces)


def lua_literal(value) -> str:
    """Python 值 → Lua 字面量（JSON 的 `{"key": ...}` 不是合法 Lua，必须自己拼）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        return "{" + ", ".join(lua_literal(item) for item in value) + "}"
    if isinstance(value, dict):
        fields = ", ".join(f"{key} = {lua_literal(item)}" for key, item in value.items())
        return "{" + fields + "}"
    raise TypeError(f"不能转成 Lua 字面量：{type(value)!r}")


def run(convention: str, scenarios: list[dict]) -> list[dict]:
    """按给定口径跑一遍全部场景，返回每行的 `{name, has_path, start_index, end_index}`。"""
    lua = ensure_lua()
    driver = _driver_lua([convention])
    # 场景坐标：格子中心 = (40 + 40*gx, 120 + 40*gy)（与引擎公式一致）
    payload = []
    for scenario in scenarios:
        payload.append({
            "name": scenario["name"],
            "costs": scenario["costs"],
            "start_x": 40 + 40 * 2,
            "start_y": 120 + 40 * 3,
            "end_x": 40 + 40 * 10,
            "end_y": 120 + 40 * 3,
        })
    header = (f'local CONVENTION = "{convention}"\n'
              f'local SCENARIOS = {lua_literal(payload)}\n')
    script = header + driver
    completed = subprocess.run([str(lua), "-"], input=script, text=True,
                               capture_output=True, cwd=str(ROOT))
    if completed.returncode != 0:
        raise RuntimeError(f"宿主 Lua 运行失败：{completed.stderr.strip()}"
                           f"\n{completed.stdout.strip()}")
    rows = []
    for line in completed.stdout.strip().splitlines():
        name, verdict, start_index, end_index = line.split("\t")
        rows.append({"name": name, "has_path": verdict == "有路",
                     "start_index": int(start_index), "end_index": int(end_index)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="用 EID 的寻路器验证 GetGridPath 的口径")
    parser.add_argument("--json", action="store_true", help="输出 JSON（门禁消费）")
    args = parser.parse_args()

    scenarios = _scenarios()
    report = {"scenarios": [], "conventions": {}}
    for convention in ("placeholder-const", "engine-array"):
        report["conventions"][convention] = run(convention, scenarios)
    for index, scenario in enumerate(scenarios):
        entry = {"name": scenario["name"], "expect_path": scenario["expect_path"]}
        for convention, rows in report["conventions"].items():
            entry[convention] = rows[index]["has_path"]
        entry["start_index"] = report["conventions"]["engine-array"][index]["start_index"]
        entry["end_index"] = report["conventions"]["engine-array"][index]["end_index"]
        report["scenarios"].append(entry)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("用 EID 自己的寻路器（luafinding.lua）跑同一批场景，两种 GetGridPath 口径对照：")
    print(f"  合成房间 {GRID_WIDTH}×{GRID_HEIGHT}（下标 = W*gy + gx）；"
          f"可走={WALKABLE}、高代价可走={HEAVY_BUT_WALKABLE}、不可走={BLOCKED}")
    print()
    print(f"  {'场景':34s} {'旧口径(恒1000)':>16s} {'新口径(引擎数组)':>18s} {'期望':>7s}")
    for entry in report["scenarios"]:
        old = "有路" if entry["placeholder-const"] else "没路"
        new = "有路" if entry["engine-array"] else "没路"
        expect = "有路" if entry["expect_path"] else "没路"
        mark = "✓" if (entry["engine-array"] == entry["expect_path"]) else "✗"
        print(f"  {entry['name']:34s} {old:>16s} {new:>18s} {expect:>7s} {mark}")
    print()
    print("  ⇒ 旧口径**四个场景全判没路**：这就是真机上「地上药丸/卡片只有问号」的宿主复现。")
    print("  ⇒ 新口径与 PC 判据一致（`<= 900` 才算可走）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
