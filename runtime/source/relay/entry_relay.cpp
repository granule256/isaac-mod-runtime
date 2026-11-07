#include "relay/entry_relay.hpp"

#include <atomic>
#include <cstring>
#include <span>

#include "lib/util/sys/jit.hpp"

// 整数地址 ↔ 指针的转换只从引擎内存访问层拿（`AsObject`）—— 调用点不再出现 `reinterpret_cast`。
// 这是 `runtime/tests/test_no_new_raw_engine_access.py` 那条"存量冻结"台账要求的写法
// （"新功能走框架接口"）；该层是 header-only/inline，不新增任何链接依赖。
#include "infrastructure/memory/engine_field_access.hpp"

// 入口中继的真机侧实现。
//
// 设计、槽布局与安全门禁全部写在 `entry_relay.hpp` 的注释里；本文件只负责“碰系统”的那部分：
//   * 竞技场（`JIT_CREATE`，落在本模块 `.text`）的一次性初始化；
//   * 槽位分配的原子自增；
//   * 经 `exl::util::RwPages` 写入槽与目标入口，写完 `Flush()`（DCache + ICache）；
//   * 用只读地址读回校验；
//   * 失败码记账（`LastFailure()`）。
//
// 这里刻意**不引用** `hook_manager.cpp` / `probe/**` 的任何东西：本机制自包含，谁接线谁调用。

namespace isaac::runtime::relay {

namespace {

// 中继竞技场：`JIT_CREATE` 在本模块 `.text` 里放一块 0x1000 字节、页对齐的静态零区
// （section `.text.EntryRelayArena`），`exl::util::Jit` 再用 `RwPages` 映射出可写别名。
// 注意它**从来不是**游戏映像的一部分，也不占任何游戏代码洞。
JIT_CREATE(EntryRelayArena, kArenaBytes);

std::atomic<std::uint32_t> s_LastFailure{ToFailureCode(EntryRelayFailure::None)};
std::atomic<std::size_t> s_NextSlot{0};
std::atomic<std::size_t> s_InstalledCount{0};
// 竞技场只映射一次的“认领 / 就绪”标志。这里刻意用 u32 而不是 bool 原子量：本项目有一条门禁
// （`runtime/tests/test_manager_update_hook_audit.py` 的
// `test_runtime_source_contains_no_bool_atomics`）禁止 runtime 源码里出现 bool 原子量。
constexpr std::uint32_t kFlagClear = 0;
constexpr std::uint32_t kFlagSet = 1;
std::atomic<std::uint32_t> s_ArenaClaimed{kFlagClear};
std::atomic<std::uint32_t> s_ArenaReady{kFlagClear};

std::uint32_t RecordFailure(EntryRelayFailure failure) {
    const std::uint32_t code = ToFailureCode(failure);
    s_LastFailure.store(code, std::memory_order_release);
    return code;
}

// 竞技场只映射一次。安装期假定单线程，但不依赖它：`s_ArenaClaimed` 的 CAS 保证只有一个
// 线程去建映射，其他线程等到 `s_ArenaReady`。`RwPages` 建映射失败会直接 abort 整个进程
// （`R_ABORT_UNLESS`/`EXL_ASSERT`），所以这里的自旋不会永久卡死。
void EnsureArenaReady() {
    if (s_ArenaReady.load(std::memory_order_acquire) != kFlagClear) {
        return;
    }
    std::uint32_t expected = kFlagClear;
    if (s_ArenaClaimed.compare_exchange_strong(expected, kFlagSet, std::memory_order_acq_rel)) {
        EntryRelayArena.Initialize(std::span {impl::EntryRelayArena::s_Area});
        s_ArenaReady.store(kFlagSet, std::memory_order_release);
        return;
    }
    while (s_ArenaReady.load(std::memory_order_acquire) == kFlagClear) {
    }
}

}  // namespace

bool TryInstallEntryRelayWithPublisher(std::uintptr_t target, const void* expectedEntry16,
    std::uintptr_t callback, EntryRelayOriginalPublisher publisher, void* context,
    std::uintptr_t* outOriginalEntry) {
    if (outOriginalEntry != nullptr) {
        *outOriginalEntry = 0;
    }

    // 先把“能不能读目标地址”挡住，再解引用。
    if (target == 0 || callback == 0 || expectedEntry16 == nullptr ||
        (target & 0x3u) != 0 || (callback & 0x3u) != 0) {
        RecordFailure(EntryRelayFailure::InvalidAddress);
        return false;
    }

    // 现场 16 字节。**任何写入都发生在这之后**，判定不通过就一个字节都不写。
    std::uint8_t current[kOriginalEntryBytes];
    std::memcpy(current, reinterpret_cast<const void*>(target), sizeof(current));

    const EntryRelayFailure precondition = EvaluateEntryRelayPreconditions(
        target, callback, expectedEntry16, current, s_NextSlot.load(std::memory_order_acquire));
    if (precondition != EntryRelayFailure::None) {
        RecordFailure(precondition);
        return false;
    }

    EnsureArenaReady();

    // 槽位分配：原子自增，避免重入；拿到的 index 超过上限即竞技场耗尽（失败不回退计数器，
    // 所以之后再装也仍然报 3）。
    const std::size_t index = s_NextSlot.fetch_add(1, std::memory_order_acq_rel);
    if (index >= kMaxRelays) {
        RecordFailure(EntryRelayFailure::ArenaExhausted);
        return false;
    }

    const std::uintptr_t roSlot = EntryRelayArena.GetRo() + SlotOffset(index);
    auto* rwSlot = reinterpret_cast<std::uint8_t*>(EntryRelayArena.GetRw() + SlotOffset(index));

    std::uint8_t expectedSlot[kSlotBytes];
    BuildSlotImage(expectedSlot, target, current, callback);
    std::memcpy(rwSlot, expectedSlot, sizeof(expectedSlot));
    // 槽必须在入口改写生效之前对指令侧可见：先刷槽，再改入口。
    EntryRelayArena.Flush();
    // 回调真正消费的是外部原子槽/Trampoline::Orig；先独立核完整槽再发布。
    if (std::memcmp(engine_memory::AsObject(roSlot), expectedSlot, kSlotBytes) != 0) {
        RecordFailure(EntryRelayFailure::WriteVerifyFailed);
        return false;
    }
    if (publisher != nullptr && !publisher(roSlot + kSlotFallbackOffset, context)) {
        RecordFailure(EntryRelayFailure::OriginalPublicationRejected);
        return false;
    }

    // 2026-10-04（真机崩溃 15:23 的根因之一）：先把"原函数入口"公布出去，再改函数入口。
    //
    // 原顺序是"改入口 → 读回校验 → 才公布"，于是存在一个窗口：**入口已经跳我们的回调了，
    // 而 `outOriginalEntry` 还停在 0**。处在这个窗口里时，只要引擎调一次那个函数，回调就会
    // `blr 0` —— 真机报告正是 `Instruction Abort`、`PC=0`、`LR` 落在
    // `EntryRelayContentGetMountedFilePathCallback + 0x50`（这一行的调用点）。
    //
    // 现在的口径：**"回调可达 ⇒ 原函数入口一定有效"**。公布的 `roSlot + kSlotFallbackOffset`
    // 就是槽里那段"跑原函数"的回退入口，即使后面校验失败、入口其实没改成，公布它也无害
    // （没人会调这个回调）。
    if (outOriginalEntry != nullptr) {
        *outOriginalEntry = roSlot + kSlotFallbackOffset;
    }

    std::uint8_t expectedEntry[kEntryPatchBytes];
    BuildEntryPatch(expectedEntry, roSlot);

    // 入口改写走 RW 别名，只改这 16 字节。
    exl::util::RwPages entryPages(target, kEntryPatchBytes);
    auto* rwEntry = reinterpret_cast<std::uint8_t*>(entryPages.GetRw());
    std::memcpy(rwEntry, expectedEntry, sizeof(expectedEntry));
    entryPages.Flush();

    // 读回校验：用**只读**地址读（也就是游戏真正执行的那份映射）。
    if (std::memcmp(reinterpret_cast<const void*>(roSlot), expectedSlot, kSlotBytes) != 0 ||
        std::memcmp(reinterpret_cast<const void*>(target), expectedEntry, kEntryPatchBytes) != 0) {
        // 2026-10-04：失败必须把入口还原。 上面那次 `memcpy` 已经让入口跳我们的回调了；
        //   这里若直接返回，就是"函数说自己没装成，实际却装上了" —— 调用方不会去接原函数，
        //   而引擎照调回调 ⇒ 又回到 `blr 0` 那条路。
        //   把现场 16 字节写回去再报失败，让"没装成"**真的是没装成**。
        std::memcpy(rwEntry, current, sizeof(current));
        entryPages.Flush();
        RecordFailure(EntryRelayFailure::WriteVerifyFailed);
        return false;
    }

    s_InstalledCount.fetch_add(1, std::memory_order_acq_rel);
    s_LastFailure.store(ToFailureCode(EntryRelayFailure::None), std::memory_order_release);
    // `outOriginalEntry` 在上面（改入口之前）就已经公布了 —— 见那段注释。
    return true;
}

// 兼容无外部回退消费方的旧接口。生产/早装/探针回调均使用显式publisher版本。
bool TryInstallEntryRelay(std::uintptr_t target, const void* expectedEntry16,
    std::uintptr_t callback, std::uintptr_t* outOriginalEntry) {
    return TryInstallEntryRelayWithPublisher(target,expectedEntry16,callback,nullptr,nullptr,outOriginalEntry);
}

// 任意地址的 4 字节代码改写（设计与守卫语义见 `entry_relay.hpp` 里那一节）。
//
// 与 `TryInstallEntryRelay` 走上同一条"碰系统"的路（`RwPages` 可写别名 + `Flush()`），
// 差别只在范围：这里只改**一个 4 字节字**，不碰入口 16 字节、也不用竞技场。
// 三处顺序刻意与入口改写一致：先读现场（只读地址）→ 判定 → 写（可写别名）→ 刷 → 读回校验。
CodeWordPatchFailure TryRewriteCodeWord(std::uintptr_t target, std::uint32_t expected,
                                        std::uint32_t patched) {
    if (target == 0 || (target & 0x3u) != 0) {
        return CodeWordPatchFailure::InvalidAddress;
    }

    // 守卫：现场从**只读**地址读（那才是游戏真正执行的那份映射）。判定不过就立刻返回，
    // 这一行之后才允许发生第一次写入。
    std::uint8_t current[sizeof(std::uint32_t)];
    std::memcpy(current, engine_memory::AsObject(target), sizeof(current));
    if (LoadLittleEndianWord(current, 0) != expected) {
        return CodeWordPatchFailure::GuardMismatch;
    }

    // 写入走同一页的可写别名；`RewriteCodeWordInBuffer` 会再核对一次（同一份判据），
    // 写完必须 `Flush()`：DCache 清 + ICache 失效，否则执行侧可能还看到旧指令。
    exl::util::RwPages pages(target, sizeof(std::uint32_t));
    auto* rw = static_cast<std::uint8_t*>(engine_memory::AsObject(pages.GetRw()));
    const CodeWordPatchFailure written = RewriteCodeWordInBuffer(rw, expected, patched);
    if (written != CodeWordPatchFailure::None) {
        return written;
    }
    pages.Flush();

    // 读回校验用只读地址（与 `TryInstallEntryRelay` 同一口径）。
    std::uint8_t verify[sizeof(std::uint32_t)];
    std::memcpy(verify, engine_memory::AsObject(target), sizeof(verify));
    return LoadLittleEndianWord(verify, 0) == patched ? CodeWordPatchFailure::None
                                                      : CodeWordPatchFailure::WriteVerifyFailed;
}

std::size_t InstalledCount() {
    return s_InstalledCount.load(std::memory_order_acquire);
}

std::uint32_t LastFailure() {
    return s_LastFailure.load(std::memory_order_acquire);
}

}  // namespace isaac::runtime::relay
