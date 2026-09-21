"""产物里**不许出现线程安全静态守卫**（`__cxa_guard_*`）—— 那个坑会让游戏黑屏冻死。

## 这条门禁为什么存在（2026-09-21 真机事故，续七十）

022 那批（模组上限 16→32）把 `LoadDefaultManifestModThroughService` 里的
`isaac::runtime::ManifestService manifestService{...}` 改成了 **函数内 `static`**，
理由写的是"解析器内部的值对象是几十 KiB 级，不能放游戏线程栈"——**对错了对象**：
真正大的是 `ResolveAll`/`ParseAll` 里的解析结果（`SelectedMods`：32 × 1.28 KiB，确实在栈上，
`ResolveAll` 的 `sub sp, sp, #0xc0b0` 就是它），而 `ManifestService` 自己只有
**一个引用 + 两个函数指针（约 24 字节）**。

函数内 `static` 带动态初始化 ⇒ 编译器生成**线程安全静态守卫**：

```
__cxa_guard_release:
    bl pthread_once        ; 本模块 -nostartfiles ⇒ 没有 pthread 运行时
    bl pthread_mutex_lock
    cbnz w0, <__gnu_cxx::__throw_concurrence_lock_error>   ; 锁失败就**抛异常**
```

真机现象（第一次上卡的容量-32 构建 = 每一批都只跑门禁、没上过真机）：

* 游戏**黑屏 + 有声音**（音频线程照跑）、**不崩**、没有崩溃报告；
* 启动状态机停在 `ManifestInstallEntered`（第 6 步），`LuaInitializeEntered`（第 8 步）从没到过；
* 主线程 PC 落在 newlib 的 `_exit`，而那一条指令是 **`b .`（自己跳自己）** ——
  也就是说 `abort()` 之后**永久自旋**，主线程再也不会返回；
* 栈上能看到 `__cxa_throw` → `_Unwind_RaiseException` → `abort` → `_exit` 这条链。

⇒ **规则：本模块里任何"函数内 `static` + 动态初始化"都是地雷。**
要静态存储就自己用一个 bool 做一次性初始化（或干脆放普通局部/文件作用域常量初始化）。

## 断言口径

1. **产物层面（真正的判据）**：`runtime/.gdbsym-artifacts/runtime.elf` 里
   **不许定义** `__cxa_guard_acquire()`/`__cxa_guard_release()`/`__cxa_guard_abort()` ——
   只要还有代码需要守卫机制，静态链接就会把这三个拉进来；一个都没有 ⇒ 全模块都没有这种静态。
   （产物不存在时跳过：`runtime.elf` 是 gitignore 的构建产物，门禁要在没构建过的机器上也能跑。）
2. **回归层面**：`hook_manager.cpp` 里那一行**不许再变回 `static`**（事故就是它引起的），
   并且要留着解释"为什么不能写成 static"的注释 —— 光删掉代码，下一个人还会再写一遍。

为什么**不做**通篇正则扫描"函数内 static"：`static std::atomic<...> x{0}`、
`static u32 calls = 0` 这类都是**常量初始化**（编译期完成，不生成守卫），扫进来只会刷假警报；
而真正的判据是"产物里有没有守卫符号"，那是机器可查的、且与写法无关。
"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ELF = ROOT / "runtime" / ".gdbsym-artifacts" / "runtime.elf"
HOOK_MANAGER = ROOT / "runtime" / "source" / "hook_manager.cpp"

#: 守卫机制的三个符号：产物里出现任何一个都说明还有代码走"函数内 static 动态初始化"。
GUARD_SYMBOLS = ("__cxa_guard_acquire", "__cxa_guard_release", "__cxa_guard_abort")

#: 事故那一行**不许再出现的写法**（变量名后面可以跟 `{` 或 `=`，两种都拦）。
FORBIDDEN_PATTERNS = (
    "static isaac::runtime::ManifestService manifestService{",
    "static isaac::runtime::ManifestService manifestService =",
)


class NoStaticGuardInitTests(unittest.TestCase):
    def test_changed_artifact_has_no_guard_symbols(self):
        """产物里不许有 `__cxa_guard_*`（这是"没有任何函数内 static 动态初始化"的机器判据）。"""
        if not ELF.exists():
            self.skipTest("没有构建产物 runtime.elf（门禁要在没构建过的机器上也能跑）")
        import sys

        sys.path.insert(0, str(ROOT / "tools"))
        from elf_syms import load_symbols

        symbols = load_symbols(ELF.read_bytes())
        present = [name for name in GUARD_SYMBOLS if name in symbols]
        self.assertEqual(
            present, [],
            "产物里出现了线程安全静态守卫：" + "、".join(present) +
            " ⇒ 某处又把函数内 `static` 写成了带动态初始化的形态；"
            "那会在真机上 abort 之后卡死在 newlib 的 `_exit` 自旋（黑屏 + 有声音），"
            "详见本文件头部与 docs/问题与解决记录.md 续七十。",
        )

    def test_manifest_service_is_not_a_function_local_static(self):
        """事故那一行不许再变回 `static`，并且要留着"为什么不能"的注释。"""
        text = HOOK_MANAGER.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            self.assertNotIn(
                pattern, text,
                "`ManifestService` 又被写成函数内 static 了 —— 会引出 `__cxa_guard_*`，"
                "真机上 pthread 锁失败 ⇒ 抛异常 ⇒ abort ⇒ `_exit` 自旋（黑屏 + 有声音）。"
                "它只有 24 字节，用普通局部即可。",
            )
        self.assertIn("__cxa_guard_acquire", text,
                      "那一行旁边的「为什么不能 static」注释被删了 —— 没有它，下一个人还会再写一遍。")



if __name__ == "__main__":
    unittest.main()
