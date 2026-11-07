// 通用引擎调用跳板的**宿主侧占位**（真实现是同目录的 `engine_call_trampoline.s`）。
//
// 文件名刻意与汇编那份**不同**：devkitPro 的构建按 basename 命名对象文件，同名的 `.s` 与 `.cpp`
// 会算出同一个 `.o`，结果汇编那份被静默丢掉（2026-09-19 实测：链接期报未定义符号）。
//
// 为什么要有这个文件：设备构建用 devkitA64 的 GCC 汇编 `.s`；而**宿主 harness** 是按一张
// `.cpp` 清单编译运行时的（`runtime/tests/test_support.layered_lua_runtime_sources`），
// 凡是链接 `isaac_api.cpp` 的 harness 都要有 `EngineCallTrampoline` 这个符号才链接得过。
// 宿主上没有引擎，引擎方法本来就不会被真的调到（handler 在校验不通过时直接降级），
// 所以这里给一个"不调用、两个返回值格子清零"的实现即可。
//
// **真实现的证据不在这里**：`runtime/tests/test_engine_call_trampoline.py` 直接汇编
// `engine_call_trampoline.s`（`-x assembler-with-cpp`），用一批签名各异的假引擎方法核对 ABI。
//
// 两个文件不会撞车：设备构建（`__SWITCH__`）里这个 TU 是空的，符号由 `.s` 提供。
#if !defined(__SWITCH__)

#include "interfaces/lua/engine_call_trampoline.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

// 宿主上"这一行到底有没有调进引擎"的唯一观测点。
// 设备上由真跳板完成调用，宿主上跳板什么都不做 ⇒ 想断言"有效编号照常调进引擎、无效编号被挡下
// 之后没调"就需要这个计数（`runtime/tests/test_lua_entity_player.py` 的 `null_costume_guard`
// 场景用它）。**只在测试里被读**，设备构建里这个 TU 是空的。
//
// 再加"最后一次调用的目标地址 + 两个参数数组"。
// 起因：本批有两条**手写**的引擎调用（`EntityPlayer:HasTrinket` 与 `RNG:RandomInt`/
// `RandomFloat`），宿主上拿不到返回值（跳板把结果清零），但"参数有没有按 PC 的签名装进
// `x0`/`x1`/`x2`"是**可判定的**，而且那正是最容易写错的地方（`x0` 必须是接收者、可选参数
// 必须原样往返）。没有这两格，那两条 API 在宿主上就只能验"不报错"，等于没验。
extern "C" {
std::uint32_t g_HostEngineCallTrampolineCalls = 0;
// 宿主测试可独立给原生返回值，默认仍0；本文件不进入Switch生产映像。
std::uint64_t g_HostEngineCallTrampolineIntegerResult = 0;
std::uintptr_t g_HostEngineCallTrampolineLastTarget = 0;
std::uint64_t g_HostEngineCallTrampolineLastIntegers[8] = {0, 0, 0, 0, 0, 0, 0, 0};
double g_HostEngineCallTrampolineLastFloats[8] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
// 同一个槽的"按 `f32` 解释"视图。
//
// 为什么需要它：跳板的浮点入参在 ABI 上是 `float`（引擎那些形参的 mangled 末位是 `f`），
// 而 AAPCS64 里 `float` 占 `sN` = `dN` 的低 32 位 ⇒ 槽里存的必须是 f32 位型
// （高 32 位填 0），不是"转成 `double` 的数值"。
// ⇒ 宿主用例要断言"引擎会读到什么"，就得把低 32 位按 `float` 解释；
// 直接把 `LastFloats[i]` 当 double 打印，看到的是位型拼出来的垃圾。
// 本批之前这里没有这一格，于是 324/325/326 三个用例都在断言一个错误的中间表示
// （数值上的 double 转换）—— 那正是这个 bug 能活这么久的原因。
extern float g_HostEngineCallTrampolineLastFloat32[8] = {0.0F, 0.0F, 0.0F, 0.0F,
                                                         0.0F, 0.0F, 0.0F, 0.0F};
}

namespace isaac::runtime {
namespace {

// 非空 TU：避免"空翻译单元"这类与行为无关的告警把门禁吵红。
[[maybe_unused]] constexpr int kEngineCallTrampolineHostStub = 1;

}  // namespace
}  // namespace isaac::runtime

void EngineCallTrampoline(std::uintptr_t function, const std::uint64_t* integerArguments,
                          const double* floatArguments, std::uint64_t* integerResult,
                          double* floatResult) noexcept {
    ++g_HostEngineCallTrampolineCalls;
    g_HostEngineCallTrampolineLastTarget = function;
    if (integerArguments != nullptr) {
        for (std::size_t index = 0; index < 8; ++index) {
            g_HostEngineCallTrampolineLastIntegers[index] = integerArguments[index];
        }
    }
    if (floatArguments != nullptr) {
        for (std::size_t index = 0; index < 8; ++index) {
            g_HostEngineCallTrampolineLastFloats[index] = floatArguments[index];
            // 低 32 位就是引擎会在 `sN` 里读到的那 32 位 ⇒ 按 `float` 解释
            // （这才是"引擎会读到什么"的读数；上面那一格保留原始 8 字节，便于排查）。
            std::uint64_t wide = 0;
            std::memcpy(&wide, &floatArguments[index], sizeof(wide));
            const std::uint32_t bits = static_cast<std::uint32_t>(wide);
            float value = 0.0F;
            std::memcpy(&value, &bits, sizeof(value));
            g_HostEngineCallTrampolineLastFloat32[index] = value;
        }
    }
    if (integerResult != nullptr) {
        *integerResult = g_HostEngineCallTrampolineIntegerResult;
    }
    if (floatResult != nullptr) {
        *floatResult = 0.0;
    }
}

#endif
