#!/usr/bin/env python3
"""把 Switch 相册里**最新的一批截图**取到本机（给 AI 直接用眼睛读）。

为什么要有它（2026-10-04）：
  真机上的读数一直是"我出命令 → 用户打字/截图 → 用户口述"这条慢回路。用户现在改为
  **自己截图**（NS 的截图键），那截图就落在 SD 卡的相册目录里，而我们的 FTP 正好能读 SD
  ⇒ 我可以直接 `Read` 那些图片，不用再麻烦用户复述屏幕上的字。
  同一条回路以后能反复用（探针、菜单、报错框……只要有截屏就能读）。

★ 纪律（与 `tools/device_ftp.py` 同一套，别绕过）：
  * **一次连接只做一件事**，动作之间睡 1~3 秒 —— 这台设备的 FTP 服务对连续快速连接敏感
    （会 `451` 或直接 reset）；
  * **本工具只读**（LIST + RETR），不写卡 ⇒ 不需要"游戏已退出"那条前置检查；
  * 相册目录在 **SD 卡**上（`/Nintendo/Album/<年>/<月>/<日>/`），与游戏运行无关。

用法：
    python3 tools/fetch_device_screenshots.py                 # 等 FTP（最多 8 分钟）→ 取最新 12 张
    python3 tools/fetch_device_screenshots.py --wait 0        # 不等，一次性试
    python3 tools/fetch_device_screenshots.py --limit 20 --out dist/xxx
    python3 tools/fetch_device_screenshots.py --days 2        # 连前一天的一起看
"""

from __future__ import annotations

import argparse
import pathlib
import socket
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import device_ftp  # noqa: E402  （复用连接/重试纪律，不另写一份）

#: 相册根目录（相对 SD 卡根）。ftpd 一般把 SD 根挂在 `/`。
#: ★★ **这台设备上 `sdmc:/Nintendo/Album` 是空的** —— 因为开了 emuMMC，内部存储的
#: `Nintendo` 被重定向到了 SD 上（`/emuMMC/emummc.ini` 的 `nintendo_path=emuMMC/SD00/Nintendo`）
#: ⇒ **真正的相册在 `/emuMMC/SD00/Nintendo/Album`**。所以这里给一串候选，按顺序找第一个
#: 含"数字年份目录"的那个；`emummc.ini` 能读到就用它推出来的那条优先。
ALBUM_ROOT_CANDIDATES = (
    '/Nintendo/Album',
    '/emuMMC/SD00/Nintendo/Album',
)
#: `emummc.ini` 的位置（用来推 nintendo_path）。
EMUMMC_INI = '/emuMMC/emummc.ini'
#: 认得的图片后缀（NS 截图是 `.jpg`；有些版本也会给 `.png`）。
IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png')
#: 两个动作之间的间隔（项目纪律：1~3 秒）。
GAP_SECONDS = 1.5
#: 等 FTP 时每隔多久探一次。
PROBE_SECONDS = 10.0


def port_open(host: str, port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(3.0)
        try:
            probe.connect((host, port))
            return True
        except OSError:
            return False


def wait_for_ftp(host: str, port: int, seconds: float) -> bool:
    """等 FTP 开（有上限）。**不轮询主线程**：这个函数只在本工具自己进程里跑。"""
    if port_open(host, port):
        print(f'FTP 已开：{host}:{port}')
        return True
    if seconds <= 0:
        print(f'FTP 没开（{host}:{port}），且没有给等待时间')
        return False
    print(f'FTP 还没开（{host}:{port}），最多等 {seconds:.0f} 秒 …', flush=True)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(PROBE_SECONDS)
        if port_open(host, port):
            print(f'FTP 开了：{host}:{port}')
            return True
    print(f'等满 {seconds:.0f} 秒，FTP 仍然没开')
    return False


def list_dir(args, path: str) -> list[str]:
    lines: list[str] = []

    def action(ftp):
        ftp.retrlines(f'LIST {path}', lines.append)

    try:
        device_ftp.with_retry(args, action, f'ls {path}')
    except SystemExit as exc:
        print(f'（列不了 {path}：{exc}）', file=sys.stderr)
        return []
    time.sleep(GAP_SECONDS)
    return lines


def names_in(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        parts = line.split(maxsplit=8)
        if len(parts) >= 9:
            names.append(parts[8])
        elif len(parts) >= 1 and not line.startswith('total'):
            names.append(parts[-1])
    return [name for name in names if name not in ('.', '..')]


def album_roots(args) -> list[str]:
    """按"最可能是真的那个"排序的相册根候选。

    ★ 为什么不写死一条：这台设备开了 emuMMC 且把内部 `Nintendo` 重定向到了 SD
    （`emummc.ini` 的 `nintendo_path=emuMMC/SD00/Nintendo`）⇒ `sdmc:/Nintendo/Album`
    **是空的**，截图其实在重定向之后那一侧。所以先读 `emummc.ini` 把它推出来，
    再兜底试几个常见位置。
    """
    roots: list[str] = []
    ini = ''
    try:
        ini = device_ftp.fetch_bytes(args, EMUMMC_INI).decode('utf-8', 'replace')
    except SystemExit:
        ini = ''
    for line in ini.splitlines():
        if line.strip().startswith('nintendo_path='):
            value = line.split('=', 1)[1].strip().strip('"')
            if value:
                roots.append('/' + value.lstrip('/') + '/Album')
    roots.extend(ALBUM_ROOT_CANDIDATES)
    #: 去重且保序 —— 顺序就是优先级。
    seen: set[str] = set()
    ordered: list[str] = []
    for root in roots:
        if root not in seen:
            seen.add(root)
            ordered.append(root)
    return ordered


def pick_album_root(args, roots: list[str]) -> str | None:
    """取第一个真的含"数字年份目录"的相册根。"""
    for root in roots:
        years = [n for n in names_in(list_dir(args, root)) if n.isdigit()]
        if years:
            print(f'相册根：{root}（{len(years)} 个年份目录）')
            return root
        print(f'（{root} 里没有年份目录，跳过）')
    return None


def newest_first(names: list[str]) -> list[str]:
    #: 相册目录名是 `2026` / `10` / `04`，文件名是 `HHMMSS...` ⇒ 字典序即为时间序。
    return sorted(names, reverse=True)


def gather_images(args, album_root: str, days: int, limit: int) -> list[tuple[str, str]]:
    """返回 [(远端路径, 文件名)]，最新的在前。"""
    found: list[tuple[str, str]] = []
    years = newest_first([n for n in names_in(list_dir(args, album_root)) if n.isdigit()])
    for year in years:
        months = newest_first(
            [n for n in names_in(list_dir(args, f'{album_root}/{year}')) if n.isdigit()])
        for month in months:
            day_names = newest_first(
                [n for n in names_in(list_dir(args, f'{album_root}/{year}/{month}'))
                 if n.isdigit()])
            for day_index, day in enumerate(day_names):
                if day_index >= days:
                    break
                remote_dir = f'{album_root}/{year}/{month}/{day}'
                files = [n for n in names_in(list_dir(args, remote_dir))
                         if n.lower().endswith(IMAGE_SUFFIXES)]
                for name in newest_first(files):
                    found.append((f'{remote_dir}/{name}', name))
                if len(found) >= limit:
                    return found[:limit]
            if found:
                return found[:limit]
    return found[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description='取设备相册里最新的截图（只读）')
    parser.add_argument('--host', default=device_ftp.DEFAULT_HOST)
    parser.add_argument('--port', type=int, default=device_ftp.DEFAULT_PORT)
    parser.add_argument('--user', default=device_ftp.DEFAULT_USER)
    parser.add_argument('--password', default=device_ftp.DEFAULT_PASSWORD)
    parser.add_argument('--out', default='dist/device-screenshots-20261004')
    parser.add_argument('--limit', type=int, default=12, help='最多取几张（最新优先）')
    parser.add_argument('--days', type=int, default=1, help='看最近几个日期目录')
    parser.add_argument('--wait', type=float, default=480.0, help='等 FTP 开最多几秒（0 = 不等）')
    args = parser.parse_args()

    if not wait_for_ftp(args.host, args.port, args.wait):
        return 2

    roots = album_roots(args)
    album_root = pick_album_root(args, roots)
    if album_root is None:
        print('没找到相册目录（试过：' + '、'.join(roots) + '）—— 检查截图是不是真的存下来了。')
        return 1

    images = gather_images(args, album_root, days=max(1, args.days), limit=max(1, args.limit))
    if not images:
        print(f'{album_root} 下没找到任何图片文件。')
        return 1

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f'取 {len(images)} 张 → {out_dir}/')
    written = 0
    for remote, name in images:
        try:
            data = device_ftp.fetch_bytes(args, remote)
        except SystemExit as exc:
            print(f'  ✗ {name}：{exc}', file=sys.stderr)
            break
        target = out_dir / name
        target.write_bytes(data)
        written += 1
        print(f'  ✓ {name}  {len(data)} 字节')
        time.sleep(GAP_SECONDS)
    print(f'完成：{written} 张，落在 {out_dir}/')
    return 0 if written else 1


if __name__ == '__main__':
    sys.exit(main())
