// ============================================================================
// 把本模块的展开表（`.eh_frame`）登记给 libgcc 的展开器（2026-09-25，）
// ============================================================================
//
// **为什么必须有这个文件**：它是"真机画面卡死、音乐还在、连崩溃报告都没有"的根因所在。
// 完整证据链：`dist/freeze-20260925/`（现场 dump + 逐条复核命令）与
// `docs/问题记录-画面卡死-20260924.md` §11。要点：
//
//   1. 本模块是 `-nostartfiles` 链接的 ⇒ 没有 crtbegin/crtend ⇒ **没有人**调用
//      `__register_frame_info_bases`（这一步平时由 crtbegin 里的 `frame_dummy` 做），
//      而且那个入口在本模块里**根本没被链接进来**、也没有导出 ⇒ 外部（含系统加载器）
//      无从替我们登记。
//   2. libgcc 的 `_Unwind_Find_FDE` **只查"已登记对象"这张链表**（反汇编证据：模块内
//      `0x69FC0` 处 `pthread_mutex_lock(&object_mutex)` → `ldr x19,[x24,#0xe78]` →
//      `bl search_object`），**不查任何模块/phdr 表**；链表头是本模块 `.bss` 里的私有变量。
//   3. ⇒ 没登记 = 本模块里抛出的 C++ 异常连**第一帧**都查不到 ⇒ `uw_init_context_1`
//      直接 `abort()`（模块内 `0x67F88: bl uw_frame_state_for` 紧跟 `0x67F8C: cbnz w0, <abort>`）
//      ⇒ `abort` → `raise(6)` → newlib `_exit(1)`，而 `_exit` 在"退出钩子为空"时**原地自旋**
//      ⇒ 画面停、音乐继续、没有 `svcBreak`、没有崩溃报告、主机不重启。
//   4. 只补回了 `.eh_frame` / `.eh_frame_hdr` 这些表，
//      **没补"登记"** ⇒ 09-25 以同一签名再次卡死。
//
// **登记之后会怎样**：异常才"能展开" ⇒ 例如 `.pcx` 转码里 `std::vector::reserve` 抛出的
// `std::bad_alloc` 会走到 `std::terminate`（`PngToPcx` 是 `noexcept`）⇒ 099 批装的
// `std::set_terminate` 兜底才真正生效 ⇒ **留下崩溃报告**，而不是无声卡死。
//
// **为什么是构造项、且带优先级 101**：本模块里最早可能抛异常的代码是**别的构造项**
// （`_GLOBAL__sub_I_hook_manager.cpp` 等，默认优先级 65535），所以登记必须排在它们**之前**。
// 链接脚本用 `KEEP (*(SORT_BY_INIT_PRIORITY(.init_array.*)))` 收带优先级的构造项
// （见 `misc/link.ld`），exlaunch 的 `init.cpp:31-41` 会按顺序依次调用 ⇒ 101 一定早于 65535。
//
// **只在目标（AArch64）构建里生效**：`__eh_frame_start__`/`__eh_frame_end__` 由
// `misc/link.ld` 导出，宿主（x86_64）夹具里没有这两个符号，所以整份实现用 `__aarch64__` 守卫
// （宿主构建得到空 TU；本文件的代码不被任何其它 TU 调用，也不会给宿主夹具添未定义符号）。

#if defined(__aarch64__)

#include <cstdint>

extern "C" {
// libgcc 提供的登记入口（devkitA64 gcc 15.2.0 的 `libgcc.a` 里确实有：`__register_frame_info_bases`
// / `__register_frame` / `_Unwind_Find_FDE`；这里只用到第一个，链接时按需拉进来）。
void __register_frame_info_bases(const void* begin, void* object, void* tbase, void* dbase);

// 展开器查 FDE 的入口：**同一个**机制平时在异常展开里被调（`uw_frame_state_for` → 它）。
// 自检直接调它一次，就能证明"登记真的生效了"，不必等真的抛一次异常（那要复现一次卡死才能遇到）。
void* _Unwind_Find_FDE(void* pc, void* bases);

// 由 `misc/link.ld` 的 `.eh_frame` 输出段框出来的起止符号。
extern const char __eh_frame_start__[];
extern const char __eh_frame_end__[];
}

// ---------------------------------------------------------------------------
// 自检结果（**给真机读数用**，不必复现卡死就能判定登记有没有生效）
// ---------------------------------------------------------------------------
// bit0 = 展开器在我们自己的 PC 上找到了 FDE；其余位保留。
// 0 = 既没登记也没查到（病态，等于没修）；1 = 查到了（登记生效 ✓）；2 = 登记了但查不到（病态）。
// 读法（部署后不需要设备也能算出偏移，见 `dist/change-archive-20260925/134-eh-frame-registration/README.md`）：
// 绝对地址 = 运行时模块基址 + 本符号在 `runtime.elf` 里的偏移。
std::uint32_t g_EhFrameRegistrationSelfCheck = 0;
// 自检查到的 FDE 地址（0 = 没查到）。非零即证明"展开器能看到我们这一帧"。
std::uintptr_t g_EhFrameFdeForSelfCheck = 0;

namespace {

// libgcc 内部 `struct object`（`unwind-dw2-fde.h`）的**存储**：我们只提供内存、**不解释它的字段**。
// devkitA64 不装 libgcc 的内部头，所以这里按"宁大勿小"给一块 16 字节对齐的静态缓冲：
// 当前工具链里 `sizeof(struct object)` 是 0x28（3 个指针 + 一个联合 + 一个 `uaddr`），128 字节足够；
// 缓冲在 `.bss`（零初始化，没有动态初始化 ⇒ 不引入 magic-static 守卫），libgcc 会自己填。
alignas(16) std::uint8_t g_FrameObjectStorage[128]{};

// `struct dwarf_eh_bases { void *tbase; void *dbase; void *func; }` —— 只有自检用，值我们不读。
alignas(8) std::uint8_t g_SelfCheckBases[24]{};

// 幂等标志：登记只需要做一次（本模块只加载一次，这里再挡一道，避免将来被重复调用）。
bool g_FrameInfoRegistered = false;

}  // namespace

// 早期构造项（优先级 101）：把本模块的 `.eh_frame` 登记给展开器，并做一次自检。
// 空区间（`start == end`）时什么都不做 —— 那种情况下也确实没有可登记的 FDE。
extern "C" __attribute__((constructor(101))) void RegisterModuleEhFrameForUnwinding() {
    if (g_FrameInfoRegistered) {
        return;
    }
    const std::uintptr_t begin = reinterpret_cast<std::uintptr_t>(__eh_frame_start__);
    const std::uintptr_t end = reinterpret_cast<std::uintptr_t>(__eh_frame_end__);
    if (begin >= end) {
        return;
    }
    // `tbase`/`dbase` 传空：本模块的 FDE/CIE 指针编码全是 `pcrel`（`-fPIC` 下的常态），
    // 不依赖 text/data 基址；`.eh_frame_hdr` 那是另一套（我们不用表查找入口）。
    __register_frame_info_bases(reinterpret_cast<const void*>(begin), g_FrameObjectStorage, nullptr,
                                nullptr);
    g_FrameInfoRegistered = true;

    // 自检：拿本函数自己的地址去问展开器 —— 登记生效的话必然查得到（本函数就在 `.eh_frame` 里）。
    void* fde = _Unwind_Find_FDE(reinterpret_cast<void*>(&RegisterModuleEhFrameForUnwinding),
                                 g_SelfCheckBases);
    g_EhFrameFdeForSelfCheck = reinterpret_cast<std::uintptr_t>(fde);
    g_EhFrameRegistrationSelfCheck = (fde != nullptr) ? 1U : 2U;
}

#endif  // __aarch64__