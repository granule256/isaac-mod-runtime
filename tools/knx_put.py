#!/usr/bin/env python3
"""把本地文件写进 Switch 的**任意路径**（KELI-NX 平台，FTP 的替代品）。

## 为什么要有它

设备上跑着 KELI-NX（`docs/使用-KELI-NX远程控制平台-20261005.md`）：一个常驻 sysmodule，
把主机的文件能力暴露成端口 47800 上的方法。它的 `fs.write` 对**白名单以外**的路径也放行，
只要带口令 `I-KNOW-THIS-TOUCHES-OUTSIDE-ROOTS` —— 于是"往游戏 runtime 目录写 subsdk9"
**不再需要 ftpd**（而 ftpd 一启动游戏就没了）。

## 为什么不直接用 MCP 的 `knx_put`

MCP 服务器持有的是**它启动时那份** `pc/knx_mcp.py` 的代码，改了文件不会热生效；
而本仓库要的是"改完立刻可用"。所以这里直接从 `pc/knx_mcp.py` import（跑的是磁盘上的最新代码）。

★ 用法（必须**先关游戏** —— 目标文件正被加载时写入没意义）：

    python3 tools/knx_put.py <本地文件> <设备上的绝对路径>

例：

    python3 tools/knx_put.py runtime/.gdbsym-artifacts/deploy/atmosphere/contents/\\
010021C000B6A000/exefs/subsdk9 /atmosphere/contents/010021C000B6A000/exefs/subsdk9

退出码 0 = 写完且**读回逐字节校验通过**；非 0 = 打印详情（**校验不过就别重启**）。

★ 与 PC 侧 GDB（含 `tools/read_device_state_via_gdb.py` 的调试桩）互斥：两者抢设备上同一个
调试句柄，不能同时用。
"""

from __future__ import annotations

import sys
from pathlib import Path

PC_DIR = Path.home() / "code" / "github" / "KELI-NX" / "pc"
DEVICE = ("192.168.124.11", 47800)
OUTSIDE_TOKEN = "I-KNOW-THIS-TOUCHES-OUTSIDE-ROOTS"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    local, remote = argv[1], argv[2]
    if not Path(local).is_file():
        print(f"本地文件不存在：{local}")
        return 2

    sys.path.insert(0, str(PC_DIR))
    try:
        import knx_mcp  # type: ignore
    except ImportError as exc:
        print(f"import 不到 pc/knx_mcp.py（期望在 {PC_DIR}）：{exc}")
        return 2

    device = knx_mcp.Device(DEVICE[0], DEVICE[1], 180.0)
    try:
        out = knx_mcp.tool_put(device, {
            "local_path": local,
            "remote_path": remote,
            "confirm": OUTSIDE_TOKEN,
            "verify": True,
        })
    finally:
        device.close()

    ok = bool(out.get("verified")) and not out.get("size_mismatch")
    print(f"本地   : {out.get('local')}")
    print(f"远端   : {out.get('remote')}")
    print(f"字节   : 发出 {out.get('bytes')} / 读回 {out.get('readback_bytes')}"
          f" / 远端 stat {out.get('remote_size')}")
    print(f"sha256 : 本地 {out.get('sha256')}")
    print(f"         读回 {out.get('readback_sha256')}")
    print(f"分块   : {out.get('chunks')} 块 × {out.get('chunk_bytes')} 字节")
    if out.get("fallback"):
        print(f"回退   : {out['fallback']}")
    if out.get("size_mismatch"):
        print("★ 尺寸不符！")
    print("结果   : " + ("✅ 写入并读回校验通过" if ok else "❌ **校验未通过** —— 别重启，先查"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
