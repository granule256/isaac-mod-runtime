// ============================================================================
// 钩子隔离（L4）· 甲案：记录 C++ 异常的抛出位置（2026-09-29，）
// ============================================================================
//
// 用户 2026-09-29 在"甲 / 乙 / 丙"三案中选了**甲**：只做"在 `__cxa_throw` 上记录抛出位置"，
// **不接管 `abort()`**（乙案）—— 因为导出 `abort` 这个同名符号有"改变游戏侧符号解析"的介入风险。
//
// ## 要回答什么问题
//
// `docs/问题记录-画面卡死-20260924.md` 把"画面卡死、音乐还在、连崩溃报告都没有"的三类嫌疑
// （Lua 无保护抛错 / 未捕获 C++ 异常 / 断言）分开的办法只有一个：**把发生的位置记下来**。
// 的 `fatal_forensics.hpp` 已经解决"未捕获异常 ⇒ 留下报告"，但它只报出
// **`std::terminate` 被调的那一刻**（`kKindCxxTerminate`），报不出**异常是从哪里抛出来的**。
// 本设施补这一半：每次 C++ 异常抛出时记下**抛出点**（`__builtin_return_address(0)`）。
//
// ## 为什么用 `--wrap=__cxa_throw`
//
// `__cxa_throw` 是 libstdc++ 的实现符号、**不是**我们可以"挂入口中继"的游戏函数；
// 而本模块是 `-nostartfiles` 的模块，链接器提供了 `-Wl,--wrap=<符号>` 这种**纯链接期**的重定向：
//   * 所有对本模块内 `__cxa_throw` 的调用改调到 `__wrap___cxa_throw`；
//   * 我们要调真实现时用 `__real___cxa_throw`。
// ⇒ **不导出任何全局同名符号、不改游戏侧任何东西**（这正是"甲案介入面小"的兑现方式）。
// 已在 devkitA64 上实测：`aarch64-none-elf-g++ -Wl,--wrap=__cxa_throw` 编译 + 链接均通过。
//
// ## 只记"最近一次"，不刷屏
//
// 环形会带来"异常风暴时冲掉别的证据"的副作用；这里**只保留最近一次**（8 个字段），
// 且**每条只写一次**——异常路径本身必须是最小动作（它已经在异常里了，不能在这里分配内存、
// 不能调可能抛的函数、不能加锁）。因此本文件：无动态分配、无锁、无 `try`。
//
// ## 读数怎么用
//
// 读数工具读 `g_ThrowForensics` 那几个符号（固定布局），真机上看到
// `throwCount > 0` 就说明"这一局抛过 C++ 异常"，`lastThrowFrom` 就是**模块内抛出点的偏移**
// （拿 `runtime.elf` 的符号表反查即得函数名）。
//
// ## 只在目标（AArch64）构建里生效
//
// 宿主门禁夹具不会链 `--wrap`（它们的链接命令各自手写），也不该被本设施改变行为 ⇒ 整份实现
// 用 `__aarch64__` 守卫（宿主构建得到空 TU）。

#if defined(__aarch64__)

#include <cstdint>

namespace isaac::runtime::forensics {

// 固定布局的"最近一次抛出"记录（读数工具按这个布局解，字段只许往后加）。
struct ThrowForensics {
    std::uint32_t throwCount;   // 本会话抛出次数（>0 即"抛过 C++ 异常"）
    std::uint32_t reserved0;    // 对齐保留
    std::uint64_t lastThrowFrom; // 最近一次的抛出点（`__builtin_return_address(0)`）
    std::uint64_t lastThrowType; // 最近一次的 `std::type_info*`（`__cxa_throw` 第 2 参）
    std::uint64_t firstThrowFrom; // 第一次的抛出点（风暴时仍留一条"最早"）
};
ThrowForensics g_ThrowForensics{};

}  // namespace isaac::runtime::forensics

extern "C" {

// libstdc++ 的真实现（由 libstdc++ 提供；我们只是把调用重定向到自己这里）。
void __real___cxa_throw(void* thrown, void* type, void (*destructor)(void*));

// `--wrap=__cxa_throw` 的落点：只记一笔再原样转发。
// 这里刻意不做任何可能再抛的事（不分配、不打日志、不加锁）——
// 它运行在"已经要抛异常"的路径上。
[[noreturn]] void __wrap___cxa_throw(void* thrown, void* type, void (*destructor)(void*)) {
    using isaac::runtime::forensics::g_ThrowForensics;
    const auto from = reinterpret_cast<std::uint64_t>(__builtin_return_address(0));
    if (g_ThrowForensics.throwCount == 0) {
        g_ThrowForensics.firstThrowFrom = from;
    }
    ++g_ThrowForensics.throwCount;
    g_ThrowForensics.lastThrowFrom = from;
    g_ThrowForensics.lastThrowType = reinterpret_cast<std::uint64_t>(type);
    __real___cxa_throw(thrown, type, destructor);
    __builtin_unreachable();
}

}  // extern "C"

#endif  // __aarch64__