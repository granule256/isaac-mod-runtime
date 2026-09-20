/* 通用引擎调用跳板（声明与设计说明见 `engine_call_trampoline.hpp`）。
 *
 * 为什么是**独立汇编文件**而不是 C++ 里的 `__attribute__((naked))`：设备工具链是 devkitA64 的
 * GCC，它对这个属性只回一句 `'naked' attribute directive ignored`（并被 `-Werror` 变成构建失败）。
 * 跳板本身只有二十来条指令，写成 `.s` 反而更清楚 —— 而且 devkitPro 的规则用
 * `-x assembler-with-cpp` 汇编 `.s`，所以这里的 `#if` 是有效的。
 *
 * 为什么用汇编而不是"再写几个 C++ 签名分支"：分支写法把"支持的签名"钉死在**编译期**，
 * 每加一种参数组合都要重新写代码 —— 那正是"加 API 又要花代码段"的老毛病。
 * 这里用一条固定的跳板把"装参数"变成运行期动作，于是往后的签名组合只花数据。
 *
 * 实现要点（AAPCS64）：
 *   * 整数/指针参数进 `x0..x7`，浮点参数进 `d0..d7`（两套寄存器**各自独立计数**）；
 *   * 返回值：整数/指针在 `x0`，浮点在 `d0`；
 *   * 两个回填指针放在**栈上**，不放在寄存器里跨过 `blr`：`x9..x15` 是 caller-saved（被调函数
 *     可以随便踩），而用 `x19/x20` 之类 callee-saved 寄存器则要依赖"被调函数守规矩"这个前提。
 *     放栈上就是零前提。
 *   * `blr` 会把返回地址写进 `x30`，把调用方给我们的返回地址顶掉 ⇒ 不保存 `x30` 就会
 *     `ret` 回跳板自己的 `str`，**变成死循环**（2026-09-19 实测踩到，逐条单步才看出来）。
 *     所以这里保存 `x29/x30`，栈保持 16 字节对齐。
 *
 * 声明与头文件里一致（参数只能通过固定的入参寄存器访问），寄存器约定：
 *   x0 = function、x1 = integerArguments、x2 = floatArguments、
 *   x3 = integerResult、x4 = floatResult。
 */

#if defined(__APPLE__)
/* 宿主（macOS）上的 C 符号带下划线前缀；设备（ELF）上没有。 */
#define ISAAC_ENGINE_CALL_TRAMPOLINE _EngineCallTrampoline
#else
#define ISAAC_ENGINE_CALL_TRAMPOLINE EngineCallTrampoline
#endif

.text
.globl ISAAC_ENGINE_CALL_TRAMPOLINE
#if !defined(__APPLE__)
.type ISAAC_ENGINE_CALL_TRAMPOLINE, %function
#endif
ISAAC_ENGINE_CALL_TRAMPOLINE:
    /* 一帧 32 字节：高 16 字节放调用方的 x29/x30，低 16 字节放两个回填指针。 */
    stp x29, x30, [sp, #-32]!
    str x3, [sp, #16]
    str x4, [sp, #24]
    /* 目标函数与两个参数数组搬进 caller-saved 的临时寄存器（只在下一条 blr 之前用）。 */
    mov x9, x0
    mov x10, x1
    mov x11, x2
    /* 装 8 个整数/指针参数（数组一定是 8 格，见头文件里的契约）。 */
    ldp x0, x1, [x10]
    ldp x2, x3, [x10, #16]
    ldp x4, x5, [x10, #32]
    ldp x6, x7, [x10, #48]
    /* 装 8 个浮点参数。 */
    ldp d0, d1, [x11]
    ldp d2, d3, [x11, #16]
    ldp d4, d5, [x11, #32]
    ldp d6, d7, [x11, #48]
    blr x9
    /* 回填两个返回值格子（返回 void 时这两个值无意义，但指针仍然合法）。
       两个指针**从栈上重新取**：被调函数踩掉了哪些寄存器与我们无关。 */
    ldr x9, [sp, #16]
    ldr x10, [sp, #24]
    str x0, [x9]
    str d0, [x10]
    ldp x29, x30, [sp], #32
    ret
#if !defined(__APPLE__)
.size ISAAC_ENGINE_CALL_TRAMPOLINE, . - ISAAC_ENGINE_CALL_TRAMPOLINE
#endif
