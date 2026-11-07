#!/usr/bin/env python3
"""按模块并行运行 unittest 测试。

每个模块在独立进程中运行，保留独立的临时工作目录和输出。
需要容器、Ghidra 或其他独占资源的模块单独调度，避免争用共享状态。
可按模块筛选；失败项及其输出汇总到最终报告。
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "runtime" / "tests"

#: 会**自己再跑一遍整套门禁**的用例（`test_game_file_reader_stage10` 的产物隔离检查）。
#: 快速模式跳过它；完整门禁必须跑。
NESTED_SUITE_MODULE = "runtime.tests.test_game_file_reader_stage10"

#: 需要**独占资源**、不能并行跑的模块：
#:   1. 要用 docker 容器的（并发会互相抢容器与磁盘）；
#:   2. 要跑 Ghidra 无头分析的（**所有 Ghidra 模块共用同一个 Ghidra 工程
#:      `analysis/ghidra/isaac-switch.gpr`**，并发跑会撞工程锁 —— 实测 22 个模块同时红）。
#: 判据是"代码里真的去用了那个资源"，**不是**"文件里出现过那个词"：
#: 按词匹配会两头出错 —— 把只在注释里提一句的模块误判成独占（白丢并行度），
#: 也会把"门禁测试自己引用的字面量"当成真调用（实测把 `test_host_object_cache` 自己误判）。
#: 所以按 **AST** 看真实调用与常量。
_CONTAINER_HELPERS = frozenset({"run_in_toolchain", "docker_image_available"})
_SUBPROCESS_CALLS = frozenset({"run", "Popen", "check_output", "check_call", "call"})
#: Ghidra 无头分析的可执行文件名（模块里通常写成 `GHIDRA = Path("…/analyzeHeadless")`）。
GHIDRA_MARKER = "analyzeHeadless"
#: 缓存包装器的文件名（2026-09-15 起模块都指向它）。**两个都要认**：
#: 只认前者的话，模块改用包装器之后会被判成"与 Ghidra 无关"⇒ 进并行批次 ⇒
#: 首次未命中时几十个进程一起打开同一个 Ghidra 工程，撞工程锁（实测过一次，22 个模块同时红）。
GHIDRA_WRAPPER_MARKER = "ghidra_cached.py"

#: 兜底用的关键字匹配（只在 AST 解析失败时使用）。
EXCLUSIVE_KEYWORDS = re.compile(
    r"""\[\s*['"]docker['"]|run_in_toolchain\s*\(|DOCKER_IMAGE|analyzeHeadless""")


def module_uses_container(source: str) -> bool:
    """这个测试模块会不会真的去启动容器（判据见上面那段说明）。"""
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return bool(EXCLUSIVE_KEYWORDS.search(source))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "DOCKER_IMAGE":
            return True
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name in _CONTAINER_HELPERS:
            return True
        if name in _SUBPROCESS_CALLS and node.args:
            first = node.args[0]
            if isinstance(first, (ast.List, ast.Tuple)):
                if any(isinstance(item, ast.Constant) and item.value == "docker"
                       for item in first.elts):
                    return True
    return False


def module_uses_ghidra(source: str) -> bool:
    """这个测试模块会不会去跑 Ghidra 无头分析（它们共用同一个工程，必须串行）。"""
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return GHIDRA_MARKER in source

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if GHIDRA_MARKER in node.value or GHIDRA_WRAPPER_MARKER in node.value:
                return True
    return False


def module_needs_exclusive_resource(source: str) -> bool:
    return module_uses_container(source) or module_uses_ghidra(source)


def _call_name(func) -> str:
    import ast

    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


class DiscoveryError(RuntimeError):
    """发现阶段就出错：有门禁模块**导不进来**（语法错 / import 出错）。见 `discover_modules`。"""


def discover_modules(tests_dir: Path = TESTS_DIR,
                     root: Path = ROOT) -> tuple[list[str], list[str]]:
    """返回（并行批次, 独占批次）的模块全名列表。

    **用 `unittest` 自己的发现机制**，而不是自己 `glob("test_*.py")`：
    门禁的模块分布在 `runtime/tests/` 顶层以及 `unit/`、`integration/`、`contract/`
    三个子包里；自己扫目录很容易漏掉子包（第一版就漏了 19 个模块），
    而"漏跑模块"正是并行脚本最危险的失败方式 —— 它仍然会打印绿色。

    ★ **导不进来的模块必须响亮失败**（2026-09-24 批次 109 补）：`unittest` 的发现器对
    "模块导入失败"是**吞掉**的 —— 它把一个语法错的 `test_x.py` 换成一个 `_FailedTest`
    （归到 `unittest.loader` 名下），真正的模块名从列表里消失。后果是**一条永远绿的假证据**：
    `--only 那个名字` 打印 "Ran 0 tests, OK"、整套门禁也照旧全绿（已实测：写一个 `def f(:`
    的坏文件 ⇒ `--only` 输出 `Ran 0 tests in 0.003s（0 个模块）OK`、退出码 0）。
    ⇒ 这里把 `_FailedTest` 挑出来**抛错**，而不是让它静默少跑一个门禁。
    （`_FailedTest` 只表示"失败"；导入期合法 `SkipTest` 走的是另一个类 `ModuleSkipped`，
     不会被误判。判据由 `runtime/tests/test_test_runner_discovery.py` 钉住。）

    参数可传入是为了让那条门禁能在**临时目录**里造一个坏模块来验，不要去污染 `runtime/tests/`。
    """
    suite = unittest.TestLoader().discover(str(tests_dir), top_level_dir=str(root))
    seen: dict[str, Path | None] = {}
    load_failures: list[str] = []
    for test in _flatten(suite):
        if type(test).__name__ == "_FailedTest":
            load_failures.append(str(getattr(test, "_exception", "导入失败（无异常信息）")))
            continue
        module_name = test.__class__.__module__
        if module_name in seen:
            continue
        module = sys.modules.get(module_name)
        seen[module_name] = Path(module.__file__) if getattr(module, "__file__", None) else None

    if load_failures:
        raise DiscoveryError(
            "有门禁模块**导不进来**（语法错 / import 出错）：\n"
            + "\n".join(f"  - {item}" for item in load_failures)
            + "\n\n★ 这必须是响亮失败，不能忽略：导入失败的模块**不会出现在模块列表里**"
              "（unittest 把它换成一个 `_FailedTest`），于是 `--only 它的名字` 会打印"
              "「Ran 0 tests, OK」、整套门禁也照旧打印绿色 —— **一个坏掉的门禁 = 一条永远绿的假证据**。"
              "\n先修好那个文件的语法/导入，再跑门禁。")

    parallel: list[str] = []
    exclusive: list[str] = []
    for module_name in sorted(seen):
        path = seen[module_name]
        text = path.read_text(encoding="utf-8", errors="replace") if path else ""
        (exclusive if module_needs_exclusive_resource(text) else parallel).append(module_name)
    return parallel, exclusive


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
_OK = re.compile(r"^OK(?: \(skipped=(\d+)\))?", re.M)
_FAILED = re.compile(r"^FAILED \(([^)]*)\)", re.M)


def run_module(module: str) -> dict:
    """跑一个模块，返回 {module, code, seconds, ran, skipped, failed, output}。"""
    started = time.time()
    process = subprocess.run(
        [sys.executable, "-m", "unittest", module],
        cwd=str(ROOT), text=True, capture_output=True,
    )
    seconds = time.time() - started
    text = (process.stderr or "") + (process.stdout or "")
    ran = int(_RAN.search(text).group(1)) if _RAN.search(text) else 0
    skipped = 0
    ok = _OK.search(text)
    failed = None
    if ok:
        skipped = int(ok.group(1) or 0)
    else:
        failed = _FAILED.search(text)
    return {
        "module": module,
        "code": process.returncode,
        "seconds": seconds,
        "ran": ran,
        "skipped": skipped,
        "failed": failed.group(1) if failed else None,
        "output": text,
    }


def run_serial_queue(modules: list[str], results: list[dict], report) -> None:
    """独占模块**彼此串行**地跑（它们抢同一个资源），但与并行批次同时进行。

    `results.append` 在 CPython 里是原子操作，且这里只有一个线程在追加独占模块的结果，
    所以不需要额外加锁（并行批次的追加来自主线程）。
    """
    for module in modules:
        result = run_module(module)
        results.append(result)
        report(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-j", "--jobs", type=int, default=0,
                        help="并发进程数（0 = min(8, CPU 核数)；1 = 串行）")
    parser.add_argument("--list", action="store_true", help="只列出模块与分组")
    parser.add_argument("--only", default="", help="只跑模块名里含这个子串的（排障用）")
    parser.add_argument("--fast", action="store_true",
                        help='快速模式：跳过独占批次（Ghidra/docker）与那条会跑整套门禁的嵌套用例；'
                         '只用于日常改动的内循环，不能当交付证据')
    parser.add_argument("--verbose-failures", action="store_true", default=True,
                        help="失败时打印该模块的完整输出（默认开）")
    args = parser.parse_args(argv)

    try:
        parallel, exclusive = discover_modules()
    except DiscoveryError as error:
        # 发现阶段就出错 ⇒ 退出码 2（见文件头"退出码"那段）。**不继续跑**：
        # 少了一个模块的全绿会让人以为"都跑过了"。
        print(str(error), file=sys.stderr)
        return 2
    if args.fast:
        # 快速模式跳过的两类：
        #   * 独占批次（Ghidra 无头分析 + docker 容器）—— 它们验的是"引擎里那些结论还成立吗"，
        #     与"我刚改的这几行有没有把别处弄坏"无关，而它们是整轮门禁的墙钟大头；
        #   * 嵌套用例 `test_game_file_reader_stage10` —— 它自己会再跑一遍整套门禁。
        # 跳过的模块名会**原样打印**，免得"绿了但没跑"被当成"全跑过"。
        skipped = sorted(exclusive + [NESTED_SUITE_MODULE]) if NESTED_SUITE_MODULE else sorted(exclusive)
        parallel = [module for module in parallel if module != NESTED_SUITE_MODULE]
        exclusive = []
        print(f"⚡ 快速模式：跳过 {len(skipped)} 个模块（独占批次 + 嵌套套件用例）——")
        for module in skipped:
            print(f"     - {module}")
        print("   ⚠ 这不是交付证据：发布前请跑不带 --fast 的完整门禁。", flush=True)
    if args.only:
        parallel = [m for m in parallel if args.only in m]
        exclusive = [m for m in exclusive if args.only in m]
    if args.list:
        print(f"并行批次 {len(parallel)} 个模块：")
        for module in parallel:
            print(f"  {module}")
        print(f"串行批次（独占 docker）{len(exclusive)} 个模块：")
        for module in exclusive:
            print(f"  {module}")
        return 0

    jobs = args.jobs or min(8, os.cpu_count() or 1)
    jobs = max(1, jobs)
    started = time.time()
    results: list[dict] = []

    if jobs == 1:
        for module in parallel + exclusive:
            result = run_module(module)
            results.append(result)
            print(f"  {result['seconds']:6.1f}s  {'ok ' if result['code'] == 0 else 'FAIL'}  {module}",
                  flush=True)
    else:
        # 并行批次用 jobs-1 个进程，**留一个进程专门跑独占模块**。
        # 为什么两路同时跑：独占模块（docker、Ghidra）加起来有 2 分钟以上，
        # 若放在并行批次之后串行跑，整轮时间就是"两段相加"；同时跑则取两者较大的那个。
        pool_jobs = max(1, jobs - 1)
        print(f"并行批次：{len(parallel)} 个模块，{pool_jobs} 并发；"
              f"独占批次：{len(exclusive)} 个模块，1 个专用进程（与并行批次同时跑）", flush=True)

        def report(result: dict) -> None:
            print(f"  {result['seconds']:6.1f}s  "
                  f"{'ok ' if result['code'] == 0 else 'FAIL'}  {result['module']}", flush=True)

        with futures.ThreadPoolExecutor(max_workers=pool_jobs + 1) as pool:
            exclusive_future = pool.submit(run_serial_queue, exclusive, results, report)
            pending = {pool.submit(run_module, module): module for module in parallel}
            for future in futures.as_completed(pending):
                result = future.result()
                results.append(result)
                report(result)
            exclusive_future.result()

    elapsed = time.time() - started
    total = sum(r["ran"] for r in results)
    skipped = sum(r["skipped"] for r in results)
    bad = [r for r in results if r["code"] != 0]

    print()
    slowest = sorted(results, key=lambda r: -r["seconds"])[:5]
    print(f"最慢的 5 个模块：")
    for result in slowest:
        print(f"  {result['seconds']:6.1f}s  {result['module']}")
    print()
    print(f"Ran {total} tests in {elapsed:.3f}s（{len(results)} 个模块，{jobs} 并发）")
    if bad:
        print(f"FAILED ({len(bad)} 个模块有问题)")
        for result in bad:
            print(f"  ✗ {result['module']}：{result['failed'] or '进程退出码 %d' % result['code']}")
            # 改一处、只想重跑这一条时用（整轮 1.5 分钟，单条几秒）：
            print(f"     重跑这一条：python3 tools/run_tests.py --only {result['module'].rsplit('.', 1)[-1]}")
            if args.verbose_failures:
                print("-" * 70)
                print(result["output"].strip()[:4000])
                print("-" * 70)
        return 1
    print(f"OK (skipped={skipped})" if skipped else "OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
