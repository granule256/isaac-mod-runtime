"""门禁：`put-tree` **必须把"你给的那个远端根目录本身"建出来**，且失败**绝不当成成功**。

## 为什么有这条门禁（2026-09-23 批次 075 的真机教训）

要给卡上五个**新语言根**铺覆盖层文件（`…/romfs/rp_patch/resources.de` 等，卡上还不存在），
`put-tree` 报了 `553 No such file or directory`。根因：老实现只建**树里出现**的那几级目录
（`gfx`、`gfx/ui`…），**从不建你指定的那个远端根** ⇒ 远端根不存在时，树里最浅那一级的
`mkdir` 必然 `553`（因为它的父目录还不存在）。那次只能手工逐级 `mkdir` 再逐个 `put` 绕过去。

**同一份交接里还写着"退出码仍是 0（假成功）"** —— 这一条**与代码对不上**：`with_retry`
两次都失败会抛 `SystemExit`（退出码 1）、读回不一致 `cmd_put_tree` 返回 1。最可能是当时命令
接了 `| tail`，管道把退出码换成了 `tail` 的（同一份交接自己就记过这个坑）。
⇒ 本门禁把"非零退出"这件事**钉死**，两种形态都测（建目录失败、读回不一致），
以后再有人改出"假成功"就会红。

## 判据（离线跑，不碰设备、不发一条网络命令）

1. 远端根不存在时：**先把它逐级建出来**（父一定先于子），再建树里的子目录，最后才传文件；
2. 远端根**已存在**时：只发一次 `mkdir` 就够了（这台设备对连续连接敏感，不许无谓地逐级重试）；
3. 远端根写成 `/`（SD 根）时**不建任何东西**；
4. 某一级建不出来（`553`）⇒ **抛 `SystemExit`**、**一个文件都不许传**；
5. 读回不一致 ⇒ 返回 **1**（不是 0），且**后面的文件不传**；
6. `550`（已存在）不算失败；`553` 与其它 5xx 含义不同，不许混。
"""

import ftplib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import device_ftp  # noqa: E402


class FakeFtp:
    """一台"讲道理"的假 FTP 服务器：父目录不存在就回 `553`，已存在回 `550`。

    每次 `connect()` 都新建一个实例（真机上每个动作本来就是一条新连接），
    但 `server` 状态在所有实例之间共享，模拟"同一个设备"。
    """

    def __init__(self, server):
        self.server = server

    # --- 目录 -------------------------------------------------------------
    def mkd(self, path):
        self.server.log.append(('mkd', path))
        if path in self.server.refuse_mkd:
            raise ftplib.error_perm('553 No such file or directory.')
        if path in self.server.existing:
            raise ftplib.error_perm('550 Directory already exists.')
        parent = path.rsplit('/', 1)[0]
        if parent not in ('', '/') and parent not in self.server.existing:
            raise ftplib.error_perm('553 No such file or directory.')
        self.server.existing.add(path)

    # --- 文件 -------------------------------------------------------------
    def storbinary(self, command, fp):
        assert command.startswith('STOR ')
        path = command[len('STOR '):]
        self.server.log.append(('stor', path))
        data = fp.read()
        self.server.files[path] = data
        self.server.uploaded.append(path)

    def retrbinary(self, command, callback):
        assert command.startswith('RETR ')
        path = command[len('RETR '):]
        self.server.log.append(('retr', path))
        data = self.server.files.get(path, b'')
        if self.server.truncate_readback:
            data = data[:max(0, len(data) - 1)]
        callback(data)

    def quit(self):
        pass

    def close(self):
        pass


class FakeServer:
    def __init__(self):
        self.log = []
        self.existing = set()
        self.files = {}
        self.uploaded = []
        self.refuse_mkd = set()
        self.truncate_readback = False


class PutTreeTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree = Path(self.tmp.name) / 'tree'
        (self.tree / 'gfx' / 'ui' / 'main menu').mkdir(parents=True)
        (self.tree / 'gfx' / 'ui' / 'main menu' / 'gamemenu.anm2').write_bytes(b'<AnimatedSprite/>')
        (self.tree / 'gfx' / 'ui' / 'main menu' / 'gamemenu.pcx').write_bytes(b'PCX')

        patches = [
            mock.patch.object(device_ftp, 'connect', lambda args: FakeFtp(self.server)),
            mock.patch.object(device_ftp, 'assert_game_stopped', lambda args: True),
            mock.patch.object(device_ftp.time, 'sleep', lambda seconds: None),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    # --- 小工具 -----------------------------------------------------------
    def args(self, path):
        return device_ftp.argparse.Namespace(
            local=str(self.tree), path=path, force_write=True,
            host='127.0.0.1', port=0, user='u', password='p')

    def mkdirs(self):
        return [entry[1] for entry in self.server.log if entry[0] == 'mkd']

    def first_index(self, predicate):
        for index, entry in enumerate(self.server.log):
            if predicate(entry):
                return index
        return None

    # --- 判据 1：远端根本身要建出来，且父一定先于子 -------------------------
    def test_remote_root_itself_is_created_before_its_children(self):
        root = '/atmosphere/contents/010021C000B6A000/romfs/rp_patch/resources.de'
        self.assertEqual(device_ftp.cmd_put_tree(self.args(root)), 0)

        mkdirs = self.mkdirs()
        for level in ('/atmosphere', '/atmosphere/contents',
                      '/atmosphere/contents/010021C000B6A000',
                      '/atmosphere/contents/010021C000B6A000/romfs',
                      '/atmosphere/contents/010021C000B6A000/romfs/rp_patch',
                      root):
            self.assertIn(level, mkdirs, f'远端根这一级没被建出来：{level}')

        root_index = self.server.log.index(('mkd', root))
        child_index = self.server.log.index(('mkd', f'{root}/gfx'))
        self.assertLess(root_index, child_index, '远端根必须**先于**它下面的子目录建出来')

        # 树里的目录也要逐级建（父先于子），最后才是文件。
        self.assertLess(self.server.log.index(('mkd', f'{root}/gfx')),
                        self.server.log.index(('mkd', f'{root}/gfx/ui')))
        self.assertLess(self.server.log.index(('mkd', f'{root}/gfx/ui/main menu')),
                        self.first_index(lambda e: e[0] == 'stor'))

    def test_every_file_is_uploaded_under_the_remote_root(self):
        root = '/atmosphere/contents/010021C000B6A000/romfs/rp_patch/resources.de'
        self.assertEqual(device_ftp.cmd_put_tree(self.args(root)), 0)
        self.assertEqual(
            sorted(self.server.uploaded),
            [f'{root}/gfx/ui/main menu/gamemenu.anm2',
             f'{root}/gfx/ui/main menu/gamemenu.pcx'])

    # --- 判据 2：远端根已存在 ⇒ 一次 mkdir 就够 ------------------------------
    def test_existing_remote_root_costs_a_single_mkdir(self):
        root = '/atmosphere/contents/010021C000B6A000/exefs'
        self.server.existing.add(root)
        self.assertEqual(device_ftp.cmd_put_tree(self.args(root)), 0)
        self.assertEqual(self.mkdirs().count(root), 1,
                         '远端根已存在时只该发一次 mkdir（这台设备对连续连接敏感）')

    # --- 判据 3：远端根 = SD 根 ⇒ 不建任何东西 -------------------------------
    def test_slash_root_creates_nothing_above_the_tree(self):
        self.assertEqual(device_ftp.cmd_put_tree(self.args('/')), 0)
        self.assertNotIn('', self.mkdirs())
        self.assertNotIn('/', self.mkdirs())
        self.assertNotIn('//', self.mkdirs())
        self.assertIn('/gfx', self.mkdirs(), '树里的目录仍要建（挂到 SD 根下）')

    # --- 判据 4：建不出来 ⇒ 抛 SystemExit、一个文件都不许传 -------------------
    def test_a_level_that_cannot_be_created_aborts_without_uploading(self):
        root = '/atmosphere/contents/010021C000B6A000/romfs/rp_patch/resources.de'
        self.server.refuse_mkd = {root, f'{root}/gfx'}
        with self.assertRaises(SystemExit) as caught:
            device_ftp.cmd_put_tree(self.args(root))
        self.assertIn('553', str(caught.exception))
        self.assertEqual(self.server.uploaded, [], '建目录失败时**一个文件都不许传**')

    def test_other_permission_errors_are_not_swallowed(self):
        """`553` 之外的 5xx（权限等）必须原样失败，不许被当成"已存在"放过。"""
        with mock.patch.object(device_ftp, 'with_retry',
                               side_effect=SystemExit('boom')):
            with self.assertRaises(SystemExit):
                device_ftp.mkdir_once(self.args('/x'), '/x')

    # --- 判据 5：读回不一致 ⇒ 返回 1，后面的文件不传 -------------------------
    def test_readback_mismatch_returns_nonzero_and_stops(self):
        self.server.truncate_readback = True
        root = '/atmosphere/contents/010021C000B6A000/romfs/rp_patch/resources.de'
        self.assertEqual(device_ftp.cmd_put_tree(self.args(root)), 1,
                         '读回不一致必须返回非零（"假成功"是这个工具的已知事故形态）')
        self.assertEqual(len(self.server.uploaded), 1, '第一个文件读回不一致后就该停下')

    # --- 判据 6：550 与 553 不许混 -------------------------------------------
    def test_mkdir_once_tells_exists_apart_from_missing_parent(self):
        self.server.existing.add('/there')
        self.assertEqual(device_ftp.mkdir_once(self.args('/there'), '/there'), 'exists')
        self.assertEqual(device_ftp.mkdir_once(self.args('/nope/sub'), '/nope/sub'),
                         'missing_parent')
        self.assertEqual(device_ftp.mkdir_once(self.args('/new'), '/new'), 'created')

    def test_remote_join_does_not_double_the_slash(self):
        self.assertEqual(device_ftp.remote_join('/', 'gfx/ui'), '/gfx/ui')
        self.assertEqual(device_ftp.remote_join('/a/b', 'gfx'), '/a/b/gfx')


if __name__ == '__main__':
    unittest.main()
