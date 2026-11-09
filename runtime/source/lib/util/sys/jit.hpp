#pragma once

#include "common.hpp"
#include "lib/util/typed_storage.hpp"
#include "rw_pages.hpp"

#include <span>

// 竞技场必须在 `--gc-sections` 下存活：它是**只被本 TU 引用**的静态数组，只要调用方那一侧
// 还没接线（或将来被临时摘掉），整个 TU 的 section 都会被当作不可达回收，竞技场就凭空消失
// （2026-09-12 实测：`runtime/source/relay/entry_relay.cpp` 的 `.text.EntryRelayArena`
// 在 ELF 里查不到，`nm` 里也没有任何 `EntryRelay*` 符号）。
// 因此给它打上 `SHF_GNU_RETAIN`：section 属性里的 `"axR"` 就是
// `alloc | exec | retain`（`R` 由 GNU as / ld 认，devkitA64 15.2.0 实测可用）。
// 注意不能用变量属性 `__attribute__((retain))`——GCC 对**已经显式指定 section** 的变量
// 会忽略它（报 `'retain' attribute ignored`，本项目 `-Werror` 直接失败）。
//
// ★ 竞技场会**在运行时被写**（先洞见做法：RwPages 映射可写别名 + icache 失效），所以它
// 绝不能落进公告代码封印（`link.ld` 的 `__notice_code_start__`..`__notice_code_end__`）：
// 一旦落进去，装钩子写桩就改写了受保护代码，紧接着的 `RecheckCode()` 会判
// `Failure::CodeIntegrity`，公告层直接封停兼容层（2026-11-09 真机 N10 就是这么来的）。
// 封印对象是按**编译单元**命中的（`*hook_manager.o(.text .text.*)` 等），而 `hook_manager.cpp`
// 用 `#include` 把 `repentogon_native_callbacks.cpp` 编进同一个 TU ⇒ 默认的 `.text.<name>`
// 会跟着被吸进封印区间。需要放进被封印 TU 的竞技场，用 `JIT_CREATE_IN_SECTION` 给一个
// **不以 `.text` 开头**的段名，由 `link.ld` 在 `__notice_code_end__` 之后显式放置。
#define JIT_CREATE_IN_SECTION(name, size, section_name)      \
    namespace impl::name {                                   \
        __attribute__((section(section_name ", \"axR\"")))    \
        alignas(PAGE_SIZE)                                   \
        static const std::array<const u8, size> s_Area {};   \
    }                                                        \
    constinit exl::util::Jit<size> name;

#define JIT_CREATE(name, size) \
    JIT_CREATE_IN_SECTION(name, size, ".text." #name)

namespace exl::util {

    template<size_t Size>
    class Jit {
        util::TypedStorage<RwPages> m_Pages;

        inline RwPages& GetPages() { return util::GetReference(m_Pages); }

        public:
        constexpr Jit() = default;
        inline void Initialize(std::span<const u8, Size> rx) {
            util::ConstructAt(m_Pages, reinterpret_cast<uintptr_t>(rx.data()), rx.size());
        }

        inline void Flush() {
            GetPages().Flush();
        }

        inline uintptr_t GetRo() { return GetPages().GetRo(); }
        inline uintptr_t GetRw() { return GetPages().GetRw(); }
        inline uintptr_t GetSize() { return GetPages().GetSize(); }
    };
}
