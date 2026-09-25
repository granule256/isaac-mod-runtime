#pragma once

#include <cstdint>
#include <cstdlib>
#include <exception>

// 生产可用的「死前留证」（2026-09-24 批次 099）。
//
// ## 由来
// `docs/问题记录-画面卡死-20260924.md`：游戏**画面卡死、音乐还在、连崩溃报告都没有**。
// 那份记录（§2）把现场钉死为「主线程停在 newlib `_exit` 的原地自旋」，也就是有人调了
// 标准 `abort()`。同一天的离线分析（该文档 §10）把 `runtime.elf` 里所有能到 `abort` 的
// 路都列了出来，结论是三类嫌疑分不开：
//   ① **Lua 在"没有 pcall 保护"的上下文里抛错** —— `luaD_throw`（`0x442d0`）里就是 `bl abort`；
//   ② **未捕获的 C++ 异常** —— `std::terminate` 的默认行为就是 `abort`；
//   ③ 断言 / 堆检查（本次可排除：无 `__assert_func` 调用点、无 `__cxa_guard_*`）。
// 分不开的原因是**它们一个都不留痕迹**：`abort → _exit` 自旋，崩溃报告目录里什么都没有。
//
// ## 这个设施做什么
// 只做一件事：在"真的死掉"之前，把「我是谁」装进寄存器并 `svcBreak(BreakReason_User)`
// ⇒ 卡死变成一份**可读的崩溃报告**（模块基址、停下的 PC 偏移、x0..x3 寄存器快照）。
// ★★ 它**不改任何游戏逻辑**：不改判据、不改返回值、不拦调用 —— 只把"静默"变成"可查"。
//
// ## 崩溃报告怎么读
// 报告里模块名 + 偏移必须与本地部署产物的符号表对上；`x1` 应当是 `ISAACAB1`，
// `x2` 告诉你**是哪条路**：`1` = 未捕获的 C++ 异常、`2` = Lua 无保护抛错。
//
// ## 为什么整个设施是**头文件里的 inline**（而不是一个 `.cpp`）
// 两条硬约束（2026-09-24 实测踩出来的）：
//   1. 宿主门禁夹具**各自单独列源文件**编译运行时的一部分；做成独立 `.cpp` 时，
//      凡是编译 `lua_runtime.cpp` 的夹具都会在链接期报"未定义符号"。
//      放成 inline 定义 ⇒ **任何编译单元都自带定义**，夹具不用改。
//   2. `svc 0x7f` 在宿主机（x86_64）上**不是合法指令** ⇒ 必须用 `__aarch64__` 守卫，
//      宿主退化成普通 `std::abort()`（夹具不会真的触发它）。
namespace isaac::runtime::forensics {

//: `x1` 的魔数：ASCII `"ISAACAB1"`（Abort forensics 1）—— 报告里认这三个才是我装的兜底。
inline constexpr std::uint64_t kAbortMagic = 0x3142414341415349ULL;

//: `x2` 的分类码（见文件头"崩溃报告怎么读"）。
inline constexpr std::uint64_t kKindCxxTerminate = 1;  // 未捕获的 C++ 异常
inline constexpr std::uint64_t kKindLuaPanic = 2;      // Lua 无保护抛错

//: 把 `(magic, kind, detail)` 装进 `x1..x3` 再执行 `svc 0x7f`（`x0 = 2` = `BreakReason_User`）。
//: 写法照抄项目里真机验证过的那一处（`saltynx_runtime_bridge.cpp` 的 `IsaacModRuntime_ProbeFsSteps`）：
//: 寄存器用 `register ... __asm__("xN")` 钉住，`svc 0x7f` 后面接 `__builtin_unreachable()`。
//: ★ `svcBreak` 之后**不会返回**（会话在那一刻结束），所以标 `[[noreturn]]`。
[[noreturn]] inline void Break(std::uint64_t kind, std::uint64_t detail) noexcept {
#if defined(__aarch64__)
    register std::uint64_t x0 __asm__("x0") = 2;  // BreakReason_User
    register std::uint64_t x1 __asm__("x1") = kAbortMagic;
    register std::uint64_t x2 __asm__("x2") = kind;
    register std::uint64_t x3 __asm__("x3") = detail;
    __asm__ volatile("svc 0x7f"
                     :
                     : "r"(x0), "r"(x1), "r"(x2), "r"(x3)
                     : "memory");
    __builtin_unreachable();
#else
    // 宿主机（x86_64）门禁夹具会编译这一份：`svc 0x7f` 在 x86 上不是合法指令 ⇒ 退化。
    // 夹具不会真的走到这里（它们不制造 panic / 未捕获异常），这里只是让编译与链接都成立。
    static_cast<void>(kind);
    static_cast<void>(detail);
    std::abort();
#endif
}

namespace detail {

//: 一次性守卫：terminate 处理器自己再出问题（递归 terminate）时**不再 break**，
//: 直接落到 `abort()` —— 否则会在 break 那条路上套娃。
//: 函数内 static（而不是命名空间级变量）：inline 函数里的局部 static 在所有编译单元里
//: 是同一个对象，不需要 C++17 的 `inline` 变量。
inline std::uint32_t& TerminateForensicsTaken() noexcept {
    static std::uint32_t taken = 0;
    return taken;
}

//: 未捕获的 C++ 异常 ⇒ 这里。先留证再走原来的死法（`abort`），保证行为与之前一致
//: （只是多了一份报告），避免"改了死法"引入新的不确定性。
[[noreturn]] inline void TerminateForensics() noexcept {
    std::uint32_t& taken = TerminateForensicsTaken();
    if (taken == 0) {
        taken = 1;
        Break(kKindCxxTerminate, 0);
    }
    std::abort();
}

}  // namespace detail

//: 装「未捕获 C++ 异常」的兜底（`std::set_terminate`）。在模块初始化线程上尽早调一次；
//: 重复调用是幂等的（只是把处理器再设一遍）。
inline void InstallAbortForensics() noexcept { std::set_terminate(&detail::TerminateForensics); }

}  // namespace isaac::runtime::forensics