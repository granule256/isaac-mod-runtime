"""交付目录的**逐字节副本**门禁 —— "`.gitattributes` 写了但没生效"这类静默失效。

**为什么需要它**：项目有一条硬纪律（AGENTS.md / CONTRIBUTING）：交给设备的逐字节副本
**不许让 git 做行尾规范化**，否则"回退件"就不再等于我们验过的那个文件
（2026-09-15 实测：`main.lua` 87328 字节被 CRLF→LF 变成 85297，哈希全变）。
做法是在放副本的目录里写 `.gitattributes`。

**2026-09-16 又栽了一次，而且是新的形态**：写了一个只有 `-text`（**没有匹配模式**）的
`.gitattributes` —— 这种行是**非法行、git 直接忽略**，于是保护等于没写：
`git check-attr` 什么都不报，提交时三个 `main.lua` 副本被规范化，
仓库里的对象与磁盘不一致（磁盘 `e7bb9466…` / 仓库 `cb10b902…`）。
危险的地方在于**没有任何报错**：`git add` 只给一句 "CRLF will be replaced by LF" 的警告，
很容易被当成噪音划过去。

所以这里把三件事都钉住（每条都对应上面那次失败的一个环节）：

1. 目录里的 `.gitattributes` 必须**有生效的行**（模式 + `-text`），不能只有裸 `-text`；
2. `git check-attr text <文件>` 必须回 `unset`（证明这条规则真的落到文件上了）；
3. 已跟踪文件的**仓库对象必须与工作区文件逐字节相同**（证明提交时没被规范化）。
"""

import fnmatch
import functools
import hashlib
import pathlib
import subprocess
import threading
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


# ---------------------------------------------------------------------------
# 批量 git 调用（2026-09-28 批次 182）
#
# **为什么**：交付目录里共 2495 个文件、865 MB 内容，而原来的写法是**逐文件起一个 git 子进程**：
# 一次 `git show :<path>` 读一个对象、一次 `git check-attr` 查一个属性。
# 实测这条门禁要跑 119 秒（本文件是快档门禁里最慢的一个），其中光 2495 次 `git show`
# 就占 28 秒、`check-attr` 那 2000+ 次再占掉剩下的绝大部分 —— **都是进程启动与管道开销**。
# 下面四个 helper 把"每个文件一次调用"换成"整批一次调用"。
#
# ★ **判据一个字节都没有变**（这是这次改动唯一的红线）：
#   还是"索引对象内容的 sha256 == 工作区文件字节的 sha256"、"`git check-attr text` 必须回 unset"。
#   变的只是"用几次子进程去问 git"，不是"问什么、跟什么比"。
#   已按下面的方式证伪过（见 `runtime/tests/test_byte_exact_delivery_dirs.py` 的提交说明）：
#   故意改一个交付目录里被跟踪文件的字节 ⇒ 仍然红；故意写一个裸 `-text` 的 `.gitattributes`
#   ⇒ 仍然红。**优化过的门禁必须能抓到它原来能抓的东西**，否则就是把门禁改成了假的。
# ---------------------------------------------------------------------------


def git_ls_files(paths) -> list[str]:
    """一次拿到这些路径下所有**被跟踪**的文件名（相对仓库根）。

    原先每个交付目录各调一次 `git ls-files`（44 次），这里合并成一次。
    `-z`：文件名按 NUL 切分 —— 路径里有空格或中文时，按空白切会切错。
    """
    paths = [str(path) for path in paths]
    if not paths:
        return []
    out = git("ls-files", "-z", "--", *paths).stdout
    return [name.decode("utf-8", "surrogateescape") for name in out.split(b"\0") if name]


def git_index_entries(paths) -> dict[str, str]:
    """一次拿到 {相对路径: 索引里的 blob oid}（一次 `git ls-files -s`）。

    等价于原先"逐文件 `git show :<path>` 成功即代表它在索引里"：
    **只有在索引里**的文件才会出现在 `ls-files -s` 的输出里。
    """
    paths = [str(path) for path in paths]
    if not paths:
        return {}
    out = git("ls-files", "-s", "-z", "--", *paths).stdout
    entries: dict[str, str] = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _, name = record.partition(b"\t")
        fields = meta.split()
        if len(fields) < 3:      # `<mode> <oid> <stage>`；认不出来就跳过（不改判据）
            continue
        entries[name.decode("utf-8", "surrogateescape")] = fields[1].decode()
    return entries


def git_blob_sha256(oids) -> dict[str, str]:
    """一次拿到 {oid: sha256(索引对象内容)} —— `git cat-file --batch`，**流式**读。

    为什么要流式：这批内容净大小 865 MB，`subprocess.run(capture_output=True)`
    会把它整个憋在内存里。这里逐条读 header + 内容、算完 sha256 立刻丢掉。

    ★ stdout 必须**边写 stdin 边读**，否则死锁：865 MB 的输出会灌满管道，
      主线程若还堵在写 stdin 上，双方就互等了。所以 stdin 交给单独一个线程写。
    """
    unique = sorted(set(oids))
    if not unique:
        return {}
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    payload = ("\n".join(unique) + "\n").encode()

    def feed() -> None:
        try:
            process.stdin.write(payload)
        finally:
            process.stdin.close()

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    digests: dict[str, str] = {}
    try:
        for oid in unique:
            header = process.stdout.readline().split()
            # 正常是 `<oid> <type> <size>`；对象不在库里时只回一行 `<输入> missing`
            if len(header) != 3 or header[1] != b"blob":
                raise AssertionError(
                    f"git cat-file --batch 认不出 {oid}：{b' '.join(header)!r}")
            body = process.stdout.read(int(header[2]))
            process.stdout.read(1)          # 每块内容后面跟一个换行
            digests[oid] = hashlib.sha256(body).hexdigest()
    finally:
        process.stdout.close()
        process.wait()
        writer.join(timeout=1)
    return digests


def git_check_attr_text(paths) -> dict[str, str]:
    """一次查一批路径的 `text` 属性 —— `git check-attr --stdin -z text`。

    原先每个文件一次 `git check-attr`（2000+ 次子进程）。
    `--stdin` + `-z`：输入按 NUL 分隔（`path\\0…`），输出也是 NUL 分隔的三元组
    （`path\\0attr\\0value\\0…`）。
    """
    paths = [str(path) for path in paths]
    if not paths:
        return {}
    process = subprocess.run(
        ["git", "check-attr", "--stdin", "-z", "text"], cwd=ROOT,
        input=b"\0".join(path.encode("utf-8", "surrogateescape") for path in paths) + b"\0",
        capture_output=True)
    fields = process.stdout.split(b"\0")
    values: dict[str, str] = {}
    for index in range(0, len(fields) - 2, 3):
        values[fields[index].decode("utf-8", "surrogateescape")] = \
            fields[index + 2].decode("utf-8", "surrogateescape")
    return values


@functools.lru_cache(maxsize=None)
def delivery_dirs() -> list[pathlib.Path]:
    """要按"逐字节副本"对待的交付目录。

    两类：① 自己带 `.gitattributes` 的目录（约定：这就是标记）；
    ② 被**顶层** `.gitattributes` 的规则罩住的目录（例如 `dist/isaac-eid-release-*`）。

    ★ 结果做了缓存：这个函数自己会为每个命中的目录各起一次 `git ls-files`，
    而本模块有 4 个用例都会调它 —— 每次重算都是白花的钱（目录清单在一次运行里不会变）。
    """
    if not DIST.is_dir():
        return []
    marked = {path for path in DIST.iterdir()
              if path.is_dir() and (path / ".gitattributes").is_file()}
    for pattern in top_level_patterns():
        # 只取模式**直接命名**的那一层（模式里的 `/**` 是递归通配，不能拿它的结果当目录）
        head = pattern.split("/", 1)[-1].split("/")[0]
        marked.update(path for path in DIST.glob(head) if path.is_dir())
    return sorted(marked)


@functools.lru_cache(maxsize=None)
def top_level_patterns() -> tuple[str, ...]:
    """顶层 `.gitattributes` 里关掉行尾转换的模式（相对仓库根）。"""
    path = ROOT / ".gitattributes"
    if not path.is_file():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and any(part in ("-text", "!text", "binary") for part in parts[1:]):
            patterns.append(parts[0])
    return patterns


def declared_patterns(folder: pathlib.Path) -> list[str]:
    """该目录 `.gitattributes` 里声明的模式（相对该目录）；没有这个文件就返回空。"""
    attributes = folder / ".gitattributes"
    if not attributes.is_file():
        return []
    lines = attributes.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        parts = line.split()
        if parts and not parts[0].startswith("#") and len(parts) >= 2:
            if any(part in ("-text", "!text", "binary") for part in parts[1:]):
                out.append(parts[0])
    return out


def all_attribute_files() -> list[pathlib.Path]:
    """`dist/` 下**所有** `.gitattributes`（含 `change-archive/<日期>/<编号-主题>/` 里那 199 个）。

    ★ 2026-09-28 批次 182 补：原先"规则要有效"那条用例只遍历 `delivery_dirs()`
    （= `dist/` 的直接子目录 + 被顶层规则罩住的发布包），于是深度 4 的
    `dist/change-archive-<日期>/<编号-主题>/.gitattributes` **这一层没人检查**。
    它们的文件虽然会被 `git ls-files`（递归）纳入逐字节比对，但"这条规则本身有没有生效行"
    没人管 —— 而 2026-09-16 栽的那一跤正是**裸 `-text` 被 git 静默忽略**。
    实测补上这一层时，227 个文件全部合规（0 处违规）⇒ 这是**加固，不是修红**。
    """
    if not DIST.is_dir():
        return []
    return sorted(DIST.glob("**/.gitattributes"))


class ByteExactDeliveryDirTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inside = git("rev-parse", "--is-inside-work-tree")
        cls.has_git = inside.returncode == 0 and inside.stdout.strip() == b"true"

    def test_every_release_directory_is_covered_by_a_text_rule(self):
        """`dist/*release*` 的每个目录都必须被 `-text` 规则罩住。

        **为什么加**（2026-09-20 实测）：新整合包叫 `dist/isaac-switch-release-20260920/`，
        而顶层规则只写了 `dist/isaac-eid-release-*/**` ⇒ **罩不到**；同时本门禁只检查
        "自带 `.gitattributes` 的目录"与"被顶层规则罩住的目录"⇒ 这个包**根本没被检查**，
        提交时 80 个 EID 文件被 CRLF→LF 规范化（`main.lua` 仓库对象 `85ceec91…` / 磁盘 `46a391dd…`，
        正是 2026-09-15 那次同一个坑）。**只检查"被罩住的"永远发现不了"没被罩住的"**，
        所以这里改成按**命名约定**点名要求。
        """
        covered = delivery_dirs()
        suspects = sorted(path for path in DIST.glob("*release*") if path.is_dir())
        self.assertTrue(suspects, "dist/ 下应当至少有一个发布包目录；一个都没有说明约定变了，改这条门禁")
        uncovered = [path.name for path in suspects if path not in covered]
        self.assertFalse(uncovered, "这些发布包目录没被 -text 规则罩住（会被 git 规范化）："
                         + ", ".join(uncovered))

    def test_gitattributes_rules_have_a_pattern(self):
        """裸 `-text` 是非法行、会被 git 忽略 —— 这正是本次栽的那一跤。

        遍历 `dist/` 下**所有** `.gitattributes`（原先只查 `delivery_dirs()` 那一层，
        漏掉了 `change-archive/<日期>/<编号-主题>/` 这 199 个 —— 见 `all_attribute_files`）。
        """
        files = all_attribute_files()
        self.assertTrue(files, "dist/ 下一个 .gitattributes 都没有；约定变了，改这条门禁")
        for attributes in files:
            folder = attributes.parent
            with self.subTest(folder=str(folder.relative_to(ROOT))):
                lines = [line.strip() for line in
                         attributes.read_text(encoding="utf-8").splitlines()]
                effective = [line for line in lines if line and not line.startswith("#")]
                self.assertTrue(effective, f"{folder} 的 .gitattributes 没有生效行")
                for line in effective:
                    parts = line.split()
                    self.assertGreaterEqual(
                        len(parts), 2,
                        f"{folder}：`{line}` 缺匹配模式 ⇒ git 会整行忽略（保护等于没写）")
                    self.assertTrue(any(part in ("-text", "!text", "binary") for part in parts[1:]),
                                    f"{folder}：`{line}` 没有关掉行尾转换")

    def test_declared_patterns_match_real_files_and_take_effect(self):
        """声明的模式必须**真的盖住某个已跟踪文件**，并且那些文件的转换要真被关掉。

        只查"目录里有没有带 `-text` 的行"是不够的：老目录里写的是逐文件模式
        （`main.lua -text`），文件一改名（`main.lua.original`）保护就落空了 ——
        这条同时管住"模式打错/文件改名"和"规则没生效"。
        """
        if not self.has_git:
            self.skipTest("不在 git 工作区里（隔离副本）")
        for folder in delivery_dirs():
            patterns = declared_patterns(folder)
            relative_dir = folder.relative_to(ROOT)
            names = [pathlib.Path(name).name for name in git_ls_files([relative_dir])
                     if pathlib.Path(name).name != ".gitattributes"]
            if not names:
                continue
            matched_by_pattern = [(pattern,
                                   [name for name in names if fnmatch.fnmatch(name, pattern)])
                                  for pattern in patterns]
            # ★ 先一次性把要查的属性全查掉：原先这里是**每个文件一次** `git check-attr`，
            #   交付目录里有 2000+ 个文件 ⇒ 2000+ 次进程启动，是这条门禁的第二大开销。
            attributes = git_check_attr_text(
                str(relative_dir / name)
                for _pattern, matched in matched_by_pattern for name in matched)
            for pattern, matched in matched_by_pattern:
                with self.subTest(folder=folder.name, pattern=pattern):
                    self.assertTrue(matched, f"{folder.name}：模式 `{pattern}` 没盖住任何文件")
                    for name in matched:
                        relative = str(relative_dir / name)
                        value = attributes.get(relative, "")
                        self.assertEqual(
                            value, "unset",
                            f"{relative} 的行尾转换没被关掉"
                            f"（{f'text: {value}' if value else '没有任何属性'}）")

    def test_tracked_copies_are_byte_identical_to_the_worktree(self):
        """最终判据：仓库里存的对象 == 工作区文件（哈希能拿去和设备读数核对）。"""
        if not self.has_git:
            self.skipTest("不在 git 工作区里（隔离副本）")
        # ★ 一次 `git ls-files -s` 拿到全部索引对象 + 一次 `git cat-file --batch` 读内容
        #   （原先是每个文件一次 `git show`，2495 次进程 + 865 MB 内容）。
        entries = git_index_entries(folder.relative_to(ROOT) for folder in delivery_dirs())
        # 判"在不在索引里"不能看内容真值：**空文件是合法的**
        # （2026-09-20：发布包里 goodtripfixed 的 `changes.txt` 就是 0 字节，
        #  `assertTrue(blob)` 把它误报成"没进索引" ⇒ 门禁自己也会咬人）——
        # `ls-files -s` 天然只在索引里的才会出现，这个坑顺带就绕开了。
        wanted = {relative: oid for relative, oid in entries.items()
                  if (ROOT / relative).is_file()
                  and pathlib.Path(relative).name != ".gitattributes"}
        digests = git_blob_sha256(wanted.values())
        for relative, oid in sorted(wanted.items()):
            path = ROOT / relative
            with self.subTest(file=relative):
                self.assertEqual(
                    digests[oid],
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    f"{relative} 在仓库里与工作区不一致（被行尾规范化了）"
                    f" —— 修法：把该目录的 .gitattributes 写成 `* -text`，"
                    f"再 `git rm --cached` + `git add` 让对象重新入索引")


if __name__ == "__main__":
    unittest.main()
