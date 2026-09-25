#!/usr/bin/env python3
"""设备 FTP 读写小工具（一次连接只做一件事）。

为什么要单独写它：这台主机上的 FTP 服务**对连续快速连接敏感**（会返回 `451` 或直接 reset），
而项目纪律明确要求「**一个连接只做一件事、随用随关、动作之间留 1~3 秒**」。
把这条纪律写进工具里，比每次手写 `ftplib` 更不容易违反（也避免并发）。

纪律（照 `AGENTS.md`「设备取证纪律」）：
* **不要常驻**：要用时临时前台开，**用完关掉再进游戏**（常驻的 FTP 会与 `fs.mitm` 抢 SD，
  导致游戏在装载阶段崩）。
* **写卡必须在游戏未运行时做**（先用调试桩确认 `Application` 进程不在，或人工确认已退出）。
* 撞上 `451`/reset 时**等几秒再单次重试**，不要猛重试。

用法：
    python3 tools/device_ftp.py ls  /atmosphere/contents/010021C000B6A000/exefs
    python3 tools/device_ftp.py cat /atmosphere/config/system_settings.ini
    python3 tools/device_ftp.py get /path/on/device  /path/local
    python3 tools/device_ftp.py put /path/local  /path/on/device
    python3 tools/device_ftp.py put-tree /path/local/dir  /path/on/device   # 整棵目录**顺序**上传 + 逐文件核验
    python3 tools/device_ftp.py sha /path/on/device            # 读回并算 sha256（写后核验用）

★ `put-tree` 的纪律（2026-09-23 批次 071 新增，理由是这台设备的服务端行为）：
  这台设备上的 FTP 服务**对连续快速连接非常敏感**（会返回 `451` 或直接 reset）。所以整棵目录
  上传时**不许并发、不许猛重试**：
    * **你给的那个远端根目录本身**先建出来（`ensure_remote_directory`：先试一次整条路径，
      服务端说"父目录不存在"（`553`）才从最浅一级往下逐级建）——
      2026-09-23 批次 075 的教训：老实现只建**树里出现**的那几级，远端根不存在时必 `553`；
    * 树里每一级目录再 `mkdir` **逐级**创建（父目录不存在就先建父目录）；
    * 文件**一个接一个**传，每个文件传完**立刻读回 sha256 核对**，对不上就**当场停下**并报告；
    * 文件之间**睡 1~3 秒**（每个动作本身也是一次新连接，`with_retry` 还会在动作后再等 1.5 秒）；
    * 写卡前先做一次"游戏在不在跑"的检查（与 `put` 同一套逻辑；**判断不了会如实说明**，
      不把它当成"安全"）。
    * **任一步失败都是非零退出**（`with_retry` 抛 `SystemExit`、读回不一致返回 1）——
      但**别把命令接 `| tail`**：管道会把退出码换成 `tail` 的，看起来像"成功了"。

选项：`--host`（默认 192.168.124.11）、`--port`（默认 5000）、`--user/--password`（账号密码见 tools/device_access.py 的说明）
"""

from __future__ import annotations

import argparse
import ftplib
import hashlib
import io
import sys
import time
from pathlib import Path

DEFAULT_HOST = '192.168.124.11'
DEFAULT_PORT = 5000
import pathlib as _pathlib
import sys as _sys
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))
from tools.device_access import resolve_device as _resolve_device
_H, _P, _U, _W = _resolve_device(required=False)
DEFAULT_USER = _U
DEFAULT_PASSWORD = _W
SETTLE_SECONDS = 1.5
RETRY_WAIT_SECONDS = 5.0
#: `put-tree` 每个动作之间额外等待的秒数（项目纪律：连续快速连接会被服务端 `451`/reset）。
#: 要求是"文件之间睡 1~3 秒"；取 2.0 秒，加上 `with_retry` 自带的 1.5 秒结算，稳在区间内。
PUT_TREE_GAP_SECONDS = 2.0


def connect(args) -> ftplib.FTP:
    ftp = ftplib.FTP()
    ftp.connect(args.host, args.port, timeout=30)
    ftp.login(args.user, args.password)
    ftp.set_pasv(True)
    return ftp


def with_retry(args, action, label: str):
    """一次连接只做一件事；失败等几秒单次重试（`451` 是服务端限流，不代表卡坏了）。"""
    last = None
    for attempt in (1, 2):
        try:
            ftp = connect(args)
            try:
                return action(ftp)
            finally:
                try:
                    ftp.quit()
                except Exception:
                    try:
                        ftp.close()
                    except Exception:
                        pass
        except Exception as exc:  # noqa: BLE001 - 打印原文更有用
            last = exc
            print(f'[{label}] 第 {attempt} 次失败：{type(exc).__name__}: {exc}', file=sys.stderr)
            if attempt == 1:
                time.sleep(RETRY_WAIT_SECONDS)
        finally:
            time.sleep(SETTLE_SECONDS)
    raise SystemExit(f'[{label}] 两次都没成功：{last}')


def fetch_bytes(args, remote: str) -> bytes:
    def action(ftp: ftplib.FTP) -> bytes:
        buf = io.BytesIO()
        ftp.retrbinary(f'RETR {remote}', buf.write)
        return buf.getvalue()

    return with_retry(args, action, f'get {remote}')


def cmd_ls(args) -> int:
    lines: list[str] = []

    def action(ftp: ftplib.FTP):
        ftp.retrlines(f'LIST {args.path}', lines.append)

    with_retry(args, action, f'ls {args.path}')
    for line in lines:
        print(line)
    return 0


def cmd_cat(args) -> int:
    data = fetch_bytes(args, args.path)
    sys.stdout.write(data.decode('utf-8', 'replace'))
    print()
    return 0


def cmd_get(args) -> int:
    data = fetch_bytes(args, args.path)
    Path(args.local).write_bytes(data)
    print(f'{args.path} -> {args.local}: {len(data)} 字节  sha256={hashlib.sha256(data).hexdigest()[:16]}')
    return 0


def cmd_sha(args) -> int:
    data = fetch_bytes(args, args.path)
    print(f'{len(data)}\t{hashlib.sha256(data).hexdigest()}\t{args.path}')
    return 0


def assert_game_stopped(args) -> bool:
    """写卡前确认游戏没在跑（项目纪律：游戏运行时写卡会与 `fs.mitm` 抢 SD 卡）。

    ⚠️ 判据**不是**"进程表里有没有 Application" —— FTP 自己（`hbl.elf` + `ftpd.elf`）
    也是一个 Application 进程。要看模块清单里有没有以撒本体（`Repentance.nrs.elf`）。
    2026-09-15 就吃过这个亏：用户在"游戏已彻底关闭、只开着 FTP"的状态下，
    只看进程表的检查反复判成"游戏还在跑"。

    判断不了（调试桩连不上）时不硬闯也不装死：明确印出"判断不了"并**继续** ——
    这条检查是"把纪律自动化"，不是权限墙。
    """
    if getattr(args, 'force_write', False):
        print('⚠ 指定了 --force-write：跳过"游戏是否已退出"的检查（请自行确认过）')
        return True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import read_device_state_via_gdb as gdb_tool
    except Exception as exc:                 # 工具链不在/导入失败：退化成人工确认
        print(f'⚠ 无法加载调试桩工具（{type(exc).__name__}）⇒ 判断不了游戏是否在跑')
        return True
    try:
        running, detail = gdb_tool.game_is_running(args.host)
        # `monitor get info` 会**抖**（返回空 ⇒ 拿不到模块清单 ⇒ "判断不了"）。
        # 2026-09-16 实测：有时第一次就答对、有时连着两次都空、第三次才对
        # （同一天见了三次"判断不了"）⇒ 判断不了就**多补几次、中间留间隔**。
        # 这一步是"把纪律自动化"的第一道门，让它因为桩抖动而默认放行，等于门形同虚设。
        attempt = 1
        while running is None and attempt < 3:
            attempt += 1
            print(f'写卡前检查（第 {attempt} 次）：{detail} —— 隔 2 秒再问一次（桩抖动是已知现象）')
            time.sleep(2)
            running, detail = gdb_tool.game_is_running(args.host)
    except Exception as exc:
        print(f'⚠ 调试桩检查失败（{type(exc).__name__}: {exc}）⇒ 判断不了游戏是否在跑')
        return True
    print(f'写卡前检查：{detail}')
    if running is True:
        print('✗ 游戏正在运行 —— 现在写卡会与 fs.mitm 抢 SD 卡（下一次启动可能崩在装载界面）。')
        print('  请先彻底退出游戏（Home → 该游戏 → X → Close）再重试；')
        print('  确实要强行写就加 --force-write（不推荐）。')
        return False
    if running is None:
        print(f'⚠ 连问 {attempt} 次仍判断不了 ⇒ **请自己确认游戏已退出**再继续'
              f'（检查已放行，但不代表安全）。')
    return True


def cmd_put(args) -> int:
    if not assert_game_stopped(args):
        return 1
    payload = Path(args.local).read_bytes()

    def action(ftp: ftplib.FTP):
        ftp.storbinary(f'STOR {args.path}', io.BytesIO(payload))

    with_retry(args, action, f'put {args.path}')
    print(f'{args.local} -> {args.path}: 发出 {len(payload)} 字节  sha256={hashlib.sha256(payload).hexdigest()[:16]}')
    print('（务必再用 `sha` 子命令读回核对）')
    return 0


def remote_join(remote_root: str, relative: str) -> str:
    """拼远端路径：远端根是 `/`（SD 根）时**不许拼出 `//gfx`** 这种双斜杠。

    老实现一律 `f'{remote_root}/{relative}'` ⇒ 远端根传 `/` 时每条路径都多一个斜杠。
    多数服务端会容忍，但这是没必要的形状差异（也让人怀疑"到底建到哪去了"）。
    """
    if remote_root in ('', '/'):
        return f'/{relative}'
    return f'{remote_root}/{relative}'


def mkdir_once(args, path: str) -> str:
    """建**一个**目录，返回三态字符串（用返回值区分"已存在"与"父目录不存在"，不靠抛异常）：

    * `created`        —— 建成功；
    * `exists`         —— 服务端回 `550`（已经存在，对"确保存在"这种用法不算失败）；
    * `missing_parent` —— 服务端回 `553`（**父目录不存在**，得先把父目录建出来）。

    其它失败（网络、`451` 限流、权限不足）照旧由 `with_retry` 抛 `SystemExit` ⇒ **退出码非零**。

    为什么要把 `553` 单独挑出来（2026-09-23 批次 075 的实测教训）：`put-tree` 原来只建
    **树里出现**的那几级目录、**从不建你给的那个远端根** ⇒ 远端根在卡上还不存在时，
    树里最浅那一级的 `mkdir` 必然 `553`（那次要给五个新语言根铺文件，全被这一条挡住，
    只能手工逐级 `mkdir` 绕过去）。这台设备上两种码的含义确实不同，别混成一个。
    """
    def action(ftp: ftplib.FTP) -> str:
        try:
            ftp.mkd(path)
            return 'created'
        except ftplib.error_perm as exc:
            text = str(exc)
            if text.startswith('550'):
                return 'exists'
            if text.startswith('553'):
                return 'missing_parent'
            raise

    return with_retry(args, action, f'mkdir {path}')


def ensure_remote_directory(args, remote: str) -> None:
    """确保设备上 `remote` **这个目录本身**存在（必要时逐级建父目录）。

    先试一次整条路径（这台设备对连续快速连接敏感，能一次解决就不发第二条命令）；
    只有服务端明确说"父目录不存在"（`553`）时才从最浅一级往下逐级建。
    远端根写成 `/`（SD 根）时什么都不做 —— 它本来就在。

    任一级建不出来就**抛 `SystemExit`**（非零退出），绝不返回"看起来成功"。
    """
    parts = [part for part in remote.split('/') if part]
    if not parts:
        print('远端根 = SD 根（/），无需创建')
        return
    verdict = mkdir_once(args, remote)
    time.sleep(PUT_TREE_GAP_SECONDS)
    if verdict != 'missing_parent':
        print(f'远端根 {remote}：{"已存在" if verdict == "exists" else "已创建"}')
        return
    print(f'远端根 {remote} 的父目录不存在（553）⇒ 从最浅一级开始逐级创建')
    prefix = ''
    created = 0
    for part in parts:
        prefix = f'{prefix}/{part}'
        verdict = mkdir_once(args, prefix)
        time.sleep(PUT_TREE_GAP_SECONDS)
        if verdict == 'created':
            created += 1
            print(f'mkdir {prefix} 完成')
        elif verdict == 'missing_parent':
            raise SystemExit(
                f'✗ mkdir {prefix} 仍报"父目录不存在"（553）—— 这一级在设备上建不出来。'
                f'已建成的层级：{created} 级。请查清原因（权限？路径过长？这一级其实是文件？）')
    print(f'远端根 {remote} 逐级创建完成（本次新建成 {created} 级）')


def cmd_put_tree(args) -> int:
    """把一整棵**本地目录**按同结构顺序传到设备上（`<本地目录> <设备目录>`）。

    为什么单独一个子命令、而不是让人循环调 `put`：整棵目录上传最容易出的错有四种，
    它们**都不会自己报错**，只会在真机上表现为"某个文件不见了 / 是旧的那份"：
      ① 父目录不存在 ⇒ 每个文件都失败，而人只看最后一行；
      ② 传了一半就撞上 `451`/reset ⇒ 后面几个文件静默没传；
      ③ 传上去了但内容不对（截断）；
      ④ **并发**上传 ⇒ 服务端直接 reset（这台设备的已知行为）。
    ⇒ 这里把四件事都做成流程：**远端根本身**先建出来（`ensure_remote_directory`），
      树里每一级目录再逐级 `mkdir`；文件**顺序**传；每个文件**传完读回 sha256**；
      任一步对不上就**当场停下**并说明停在哪个文件（绝不当成"大概没问题"继续往下传）。
    """
    root = Path(args.local)
    if not root.is_dir():
        print(f'✗ 本地不是一个目录：{root}', file=sys.stderr)
        return 2
    # 写卡前先确认游戏没在跑（与 `put` 完全同一套检查：判断不了会如实说明，不当成"安全"）。
    if not assert_game_stopped(args):
        return 1
    remote_root = args.path.rstrip('/') or '/'

    # ⓪ **远端根本身**要先存在（2026-09-23 批次 075：老实现只建树里那几级，远端根不存在就必 553）。
    ensure_remote_directory(args, remote_root)

    # ① 目录：把**每个文件的每一级祖先目录**都建出来（顺序 = 浅的在前，父一定先于子）。
    #    ★ 老实现只收 `path.parent`（= 文件所在的**最后一级**），中间层一个都不建 ⇒
    #    只要树的深度 ≥ 2、而中间层在卡上不存在，`mkdir` 就报 `553`。
    #    2026-09-23 批次 075 给五个新语言根铺文件时撞上的就是这个（当时只能手工逐级 `mkdir`）。
    directories = set()
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.parent.relative_to(root)
        for depth in range(1, len(relative.parts) + 1):
            directories.add(Path(*relative.parts[:depth]))
    for relative in sorted(directories, key=lambda path: len(path.parts)):
        remote_directory = remote_join(remote_root, relative.as_posix())
        verdict = mkdir_once(args, remote_directory)
        if verdict == 'missing_parent':
            raise SystemExit(
                f'✗ mkdir {remote_directory} 报"父目录不存在"（553）—— 它的上一级没建成。'
                f'这不该发生（远端根与每一级父目录都已先建过），请把整段输出发给维护者。')
        print(f'mkdir {remote_directory}：'
              f'{"已存在（550）" if verdict == "exists" else "已创建"}')
        time.sleep(PUT_TREE_GAP_SECONDS)

    # ② 文件：**顺序**传（不并发），每个文件传完立刻读回核对。
    files = sorted(path for path in root.rglob('*') if path.is_file())
    print(f'== 顺序上传 {len(files)} 个文件（每个传完读回 sha256 核对，之间等 '
          f'{PUT_TREE_GAP_SECONDS:.1f} 秒）==')
    for index, path in enumerate(files, start=1):
        relative = path.relative_to(root)
        remote = remote_join(remote_root, relative.as_posix())
        payload = path.read_bytes()
        expected = hashlib.sha256(payload).hexdigest()

        def upload(ftp: ftplib.FTP, target: str = remote, data: bytes = payload):
            ftp.storbinary(f'STOR {target}', io.BytesIO(data))

        with_retry(args, upload, f'put {remote}')
        time.sleep(PUT_TREE_GAP_SECONDS)

        # 读回核对：**新连接**读（复用连接可能拿到缓存的状态，项目纪律里写过这条）。
        actual_bytes = fetch_bytes(args, remote)
        actual = hashlib.sha256(actual_bytes).hexdigest()
        if actual != expected or len(actual_bytes) != len(payload):
            print(f'✗ [{index}/{len(files)}] {remote}：读回不一致 —— **停下**', file=sys.stderr)
            print(f'   本地 {len(payload)} 字节 / {expected[:16]}…', file=sys.stderr)
            print(f'   设备 {len(actual_bytes)} 字节 / {actual[:16]}…', file=sys.stderr)
            print(f'   ⇒ 剩下的 {len(files) - index} 个文件**没有传**。请查清原因'
                  f'（空间不足？名字过长？服务端限流？）再重跑本命令 ——'
                  f'重跑是幂等的（已一致的文件会再传一次，内容不变）。', file=sys.stderr)
            return 1
        print(f'✓ [{index}/{len(files)}] {remote}  {len(payload)} 字节  '
              f'sha256={actual[:16]}…（读回一致）')
        time.sleep(PUT_TREE_GAP_SECONDS)

    print(f'== 全部完成：{len(files)} 个文件、{len(directories)} 个目录；'
          f'每个文件都已读回核对 ==')
    print('（整棵目录的最终核对仍是 `python3 tools/verify_device_install.py`：'
          '它按部署清单逐文件比哈希，比"传的时候对过一次"更硬。）')
    return 0


def cmd_mkdir(args) -> int:
    """建目录（`nro_patches` 下每个中继一个目录，写入前必须先建）。"""
    def action(ftp: ftplib.FTP):
        try:
            ftp.mkd(args.path)
        except ftplib.error_perm as exc:
            # 550 = 已存在：对"确保存在"这种用法不算失败，但要如实说明。
            if not str(exc).startswith('550'):
                raise
            print(f'{args.path} 已存在（550），未做改动')

    with_retry(args, action, f'mkdir {args.path}')
    print(f'mkdir {args.path} 完成')
    return 0


def cmd_rm(args) -> int:
    """删一个文件（只用于删自己刚放上去的探针/临时件；目录用 `rmd` 另说）。"""
    def action(ftp: ftplib.FTP):
        ftp.delete(args.path)

    with_retry(args, action, f'rm {args.path}')
    print(f'rm {args.path} 完成')
    return 0


def cmd_mv(args) -> int:
    """改名/移动（`RNFR` + `RNTO`，一次连接只做这一件事）。

    为什么用它而不是"下载再上传"：搬位置不需要改内容，改名几毫秒就完成，
    既省流量也不会有"传一半损坏"的风险（2026-09-14 把 84 个错位的描述文件搬回正确位置就靠它）。
    """
    def action(ftp: ftplib.FTP):
        ftp.rename(args.src, args.dst)

    with_retry(args, action, f'mv {args.src} -> {args.dst}')
    print(f'mv 完成：{args.src} -> {args.dst}')
    return 0


def cmd_rmdir(args) -> int:
    """删一个空目录（搬空之后清理多余目录用）。"""
    def action(ftp: ftplib.FTP):
        ftp.rmd(args.path)

    with_retry(args, action, f'rmdir {args.path}')
    print(f'rmdir {args.path} 完成')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', default=DEFAULT_HOST)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--user', default=DEFAULT_USER)
    parser.add_argument('--password', default=DEFAULT_PASSWORD)
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('ls', help='列目录')
    p.add_argument('path')
    p.set_defaults(func=cmd_ls)

    p = sub.add_parser('cat', help='打印文本文件')
    p.add_argument('path')
    p.set_defaults(func=cmd_cat)

    p = sub.add_parser('get', help='下载到本地')
    p.add_argument('path')
    p.add_argument('local')
    p.set_defaults(func=cmd_get)

    p = sub.add_parser('put', help='上传覆盖（写卡前会自动确认游戏已退出）')
    p.add_argument('local')
    p.add_argument('path')
    p.add_argument('--force-write', action='store_true',
                   help='跳过"游戏是否已退出"的自动检查（自己确认过再用）')
    p.set_defaults(func=cmd_put)

    p = sub.add_parser('put-tree',
                       help='整棵目录顺序上传（远端根与各级目录逐级建、逐文件读回核对；写卡前会确认游戏已退出）')
    p.add_argument('local', help='本地目录')
    p.add_argument('path', help='设备上的目标目录（**它本身**与各级子目录都会逐级创建）')
    p.add_argument('--force-write', action='store_true',
                   help='跳过"游戏是否已退出"的自动检查（自己确认过再用）')
    p.set_defaults(func=cmd_put_tree)

    p = sub.add_parser('sha', help='读回并算大小+sha256')
    p.add_argument('path')
    p.set_defaults(func=cmd_sha)

    p = sub.add_parser('mkdir', help='建目录（已存在则如实说明）')
    p.add_argument('path')
    p.set_defaults(func=cmd_mkdir)

    p = sub.add_parser('rm', help='删一个文件（主要用来清掉自己放的探针）')
    p.add_argument('path')
    p.set_defaults(func=cmd_rm)

    p = sub.add_parser('mv', help='改名/移动（RNFR+RNTO，一次连接）')
    p.add_argument('src')
    p.add_argument('dst')
    p.set_defaults(func=cmd_mv)

    p = sub.add_parser('rmdir', help='删一个空目录')
    p.add_argument('path')
    p.set_defaults(func=cmd_rmdir)

    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
