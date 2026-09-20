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

namespace isaac::runtime {
namespace {

// 非空 TU：避免"空翻译单元"这类与行为无关的告警把门禁吵红。
[[maybe_unused]] constexpr int kEngineCallTrampolineHostStub = 1;

}  // namespace
}  // namespace isaac::runtime

void EngineCallTrampoline(std::uintptr_t, const std::uint64_t*, const double*,
                          std::uint64_t* integerResult, double* floatResult) noexcept {
    if (integerResult != nullptr) {
        *integerResult = 0;
    }
    if (floatResult != nullptr) {
        *floatResult = 0.0;
    }
}

#endif
