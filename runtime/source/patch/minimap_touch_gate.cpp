#include "patch/minimap_touch_gate.hpp"

#include <array>

// 引擎内存访问层（L1）："读哪个地址的值"与"这段地址可读吗"都收在它里面。
// 用它而不是自己写 `svcQueryMemory` + `memcpy(reinterpret_cast<...>)`：那条纪律来自
// `runtime/tests/test_no_new_raw_engine_access.py`（存量冻结、新功能走框架接口），
// 同时省掉本文件再抄第四份"这一页是不是模块代码段"的判定。
#include "infrastructure/memory/engine_field_access.hpp"
#include "relay/entry_relay.hpp"

// 真机侧实现：设计与三处补丁的语义全部写在 `patch/minimap_touch_gate.hpp` 的注释里。
// 本文件只做三件事：
//   1. 核对"这三处现在长得是不是我们预期的那三条指令"（**这一步之后才允许第一次写入**）；
//   2. 三处都相符才逐处改写，改写走入口中继那套 4 字节原语
//      （`relay::TryRewriteCodeWord`：RwPages 可写别名 + Flush + 只读读回）；
//   3. 把结果记进四个 `g_MinimapTouchGate*` 诊断量。

namespace isaac::runtime {
namespace {

// 读一个指令字：可读性判据用 L1 层那份**唯一一份**实现（地址非法/不可读 ⇒ false）。
// 它只是"这一页像代码"的第二道旁证 —— **主判据是内容守卫**（下面逐字比对期望原值）：
// 地址算错、映射不是游戏代码、版本不符，内容都不会正好等于期望的那条指令。
bool ReadWord(uintptr_t address, std::uint32_t* out) {
    return engine_memory::ReadAt(address, out, &engine_memory::EngineMemoryReadable);
}

void Publish(std::uint32_t applied, std::uint32_t guardMismatch, std::uint32_t failureCode,
             MinimapTouchGateState state) {
    g_MinimapTouchGateApplied.store(applied, std::memory_order_release);
    g_MinimapTouchGateGuardMismatch.store(guardMismatch, std::memory_order_release);
    g_MinimapTouchGateFailureCode.store(failureCode, std::memory_order_release);
    g_MinimapTouchGateState.store(static_cast<std::uint32_t>(state), std::memory_order_release);
}

}  // namespace

bool InstallMinimapTouchGate(std::uintptr_t moduleBase, std::size_t moduleTextSize) {
    constexpr std::size_t kWordBytes = sizeof(std::uint32_t);
    // 真正写下结论之前先归零：本函数进程内只会被调用一次，但"重跑也自洽"更省事，
    // 读数里也不会留下上一次的残值。
    Publish(0, 0, 0, MinimapTouchGateState::kNotTried);

    if (moduleBase == 0 || moduleTextSize < kWordBytes) {
        Publish(0, 0, MakeMinimapTouchGateFailureCode(MinimapTouchGateFailureKind::kModuleInvalid),
                MinimapTouchGateState::kFailed);
        return false;
    }

    // ---- 1) 先把三处现场读出来核对（**这一段之后才允许发生第一次写入**）----
    std::array<std::uint32_t, kMinimapTouchGatePatchCount> current{};
    std::array<std::uint32_t, kMinimapTouchGatePatchCount> patched{};
    for (std::size_t index = 0; index < kMinimapTouchGatePatches.size(); ++index) {
        const MinimapTouchGatePatch& patch = kMinimapTouchGatePatches[index];
        const std::uint32_t ordinal = static_cast<std::uint32_t>(index) + 1u;
        if (patch.offset % 4u != 0 || patch.offset > moduleTextSize - kWordBytes) {
            Publish(0, 0,
                    MakeMinimapTouchGateFailureCode(MinimapTouchGateFailureKind::kModuleInvalid,
                                                    ordinal),
                    MinimapTouchGateState::kFailed);
            return false;
        }
        const uintptr_t address = moduleBase + patch.offset;
        if (address < moduleBase || !ReadWord(address, &current[index])) {
            // 读不到（地址不在任何可读映射里 / 参数非法）⇒ 按"模块/地址非法"记账，**一处都不写**。
            Publish(0, 0,
                    MakeMinimapTouchGateFailureCode(MinimapTouchGateFailureKind::kModuleInvalid,
                                                    ordinal),
                    MinimapTouchGateState::kFailed);
            return false;
        }
        patched[index] = patch.patched;
    }

    // ---- 2) 三处**都已经**是我们写过的值 ⇒ 幂等：一个字节都不写，直接报"装上" ----
    // 加这一段只为不让"重复安装"变成一个吓人的失败读数：那样读出来会像"守卫不符"，
    // 而事实上补丁早就在位了。
    bool alreadyPatched = true;
    for (std::size_t index = 0; index < current.size(); ++index) {
        if (current[index] != patched[index]) {
            alreadyPatched = false;
            break;
        }
    }
    if (alreadyPatched) {
        Publish(static_cast<std::uint32_t>(kMinimapTouchGatePatchCount), 0, 0,
                MinimapTouchGateState::kInstalled);
        return true;
    }

    // ---- 3) 逐处核对**期望原值**：任何一处不符 ⇒ 一处都不写，游戏保持原样 ----
    // （全有或全无的口径与理由写在头文件里：半套补丁会把行为改得比不改更糟。）
    const std::uint32_t firstMismatch = FirstMinimapTouchGateGuardMismatch(current);
    if (firstMismatch != 0) {
        Publish(0, CountMinimapTouchGateGuardMismatches(current),
                MakeMinimapTouchGateFailureCode(MinimapTouchGateFailureKind::kGuardMismatch,
                                                firstMismatch),
                MinimapTouchGateState::kFailed);
        return false;
    }

    // ---- 4) 三处都相符 ⇒ 逐处改写（复用入口中继那套 4 字节改写原语）----
    std::uint32_t applied = 0;
    std::uint32_t guardMismatch = 0;
    std::uint32_t failureCode = 0;
    for (std::size_t index = 0; index < kMinimapTouchGatePatches.size(); ++index) {
        const MinimapTouchGatePatch& patch = kMinimapTouchGatePatches[index];
        const std::uint32_t ordinal = static_cast<std::uint32_t>(index) + 1u;
        const relay::CodeWordPatchFailure result = relay::TryRewriteCodeWord(
            moduleBase + patch.offset, patch.expected, patch.patched);
        if (result == relay::CodeWordPatchFailure::None) {
            ++applied;
            continue;
        }
        // 走到这里说明"判定的那一刻"与"写入的那一刻"之间现场变了（理论上不会：本安装跑在
        // 模块初始化线程上，游戏主循环尚未开始）。照实记账，不掩盖。
        if (result == relay::CodeWordPatchFailure::GuardMismatch) {
            ++guardMismatch;
            if (failureCode == 0) {
                failureCode = MakeMinimapTouchGateFailureCode(
                    MinimapTouchGateFailureKind::kGuardMismatch, ordinal);
            }
        } else if (result == relay::CodeWordPatchFailure::WriteVerifyFailed) {
            if (failureCode == 0) {
                failureCode = MakeMinimapTouchGateFailureCode(
                    MinimapTouchGateFailureKind::kWriteFailed, ordinal);
            }
        } else if (failureCode == 0) {
            failureCode = MakeMinimapTouchGateFailureCode(
                MinimapTouchGateFailureKind::kModuleInvalid, ordinal);
        }
    }

    const bool installed = applied == kMinimapTouchGatePatchCount;
    Publish(applied, guardMismatch, failureCode,
            installed ? MinimapTouchGateState::kInstalled : MinimapTouchGateState::kFailed);
    return installed;
}

}  // namespace isaac::runtime
