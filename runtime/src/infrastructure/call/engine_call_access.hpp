#pragma once

// 引擎调用层（L2，批次 108，2026-09-24）：**"把一个地址变成能调的引擎函数"这件事只在这里做一次**。
//
// 为什么会有这个文件：`docs/架构诊断-框架为什么失效-20260924.md` 第七节把框架缺的四层排了序。
// 第一层（引擎内存访问层 L1）已在批次 101~103 建成；**第二层"引擎调用"从来没人接** ——
// 于是"调一个引擎函数"在每个调用点各自写一遍：自己算 `模块基址 + 偏移`、自己逐字节核对、
// 再把地址 `reinterpret_cast<签名>` 成函数指针。光模组页（`runtime/source/mod_menu_native.cpp`）
// 一处就有 20 个这样的点，每个点都得自己记得"核对通过才允许调"。
//
// ★ 与 L1 的分工（别混）：
//   * L1（`infrastructure/memory/engine_field_access.hpp`）= 读写引擎**内存里的字段**；
//   * 本层 = 调引擎**映像里的函数**。
//   两者的守卫同源（都靠"这段地址可读吗"），但做的事不同：本层多一步"**逐字节核对入口序言**"
//   —— 偏移写错会调到别的函数上去改引擎状态，后果不可预期，所以"核对通过才把地址交出去"
//   不是可选项。这条纪律原来散在每个调用点，现在收在这里，调用点只调一个名字。
//
// ## 与既有两套机制的关系（不要重复造第三套）
//
//   * **Lua 侧**已有一套"数据驱动的引擎方法绑定"（批次 051/055）：`engine_method_api.hpp` 的
//     16 字节数据行 + `engine_call_trampoline.s` 的运行期参数编组。那套面向**从 Lua 栈取参**；
//     本层面向 **C++ 调用点** —— 后者的"参数编组"由**带签名的函数指针**在编译期完成，
//     所以本层**不需要**参数编组设施，只需要"解析 + 守卫 + 转换"这三件事。
//     ⇒ **从 Lua 调引擎方法走那套；从 C++ 调引擎函数走本层。** 两侧共用同一份可读判定。
//   * **钩子中继记下的原函数**（`isaac::runtime::Original<Fn>(HookId::...)`）不带"模块基址 + 偏移"，
//     没什么可核的，走 `AsFunction<Fn>()` 转换即可（它**不做**核对，理由写在那里的注释里）。
//
// ## 调用点怎么写
//
//     // 解析：核对 16 字节序言通过 ⇒ 得到可调用的函数指针；任一条不成立 ⇒ 得到 **nullptr**
//     // （即"绝不跳一个没核对过的地址"）。
//     g_Menu.modsCtor = engine_call::ResolveFunction<Context::CtorFn>(
//         module.base, module.size, kMenuModsCtorOffset, kMenuModsCtorExpected,
//         &engine_memory::EngineMemoryReadable);
//
//     // 调用点仍然自己判空：**"没解析出来"与"这次不该调"是两件事**，本层不替调用方决定。
//     if (g_Menu.modsCtor != nullptr) { g_Menu.modsCtor(object); }
//
// ## 线程
//
// 全部是**无状态**的纯函数，可重入、线程无关；唯一的外部副作用是通过 `readable` 去问内核，
// 那一层的缓存与线程安全由 `engine_memory_guard.hpp` 负责（与 L1 用的是同一份，不要另建）。

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <type_traits>

#include "infrastructure/memory/engine_field_access.hpp"

namespace isaac::runtime::engine_call {

//: 可读判定与 L1 同一个类型 —— 刻意用别名而不是新类型：两端必须是**同一族**函数指针，
//: 免得调用点在两种"看起来一样"的指针之间转来转去。
using engine_memory::ReadableCheck;

//: 入口序言的宽度：16 字节，与项目里所有引擎入口常量（`kXxxExpectedBytes`）一致。
//:
//: 为什么固定宽度、不做"指针 + 长度"那么通用的样子：现在需要核对入口的 C++ 调用点**全部**是
//: 16 字节（`std::array<std::uint8_t, 16>`），而可变宽度要分成"读多长、比多长"两件事 ——
//: 多一个可能写错的参数。将来真出现 4 字节那种需求（Lua 侧的 `entryWord` 就是），
//: **在这里加**，不要在调用点自己写。
inline constexpr std::size_t kEntryPrologueBytes = 16;

//: "这个偏移确实落在模块映像里吗" —— 本层的第一道判据。
//:
//: 语义与各调用点原来那句
//: `module.size < expected.size() || offset > module.size - expected.size()` 逐条同义，
//: 后面那句 `candidate + size > base + size` 也在（写成不回绕的形状，结论一样）。
//: 收成一处的唯一理由：这是**同一个判据**，早该只有一份。
[[nodiscard]] inline bool EntryWithinImage(std::uintptr_t base, std::size_t moduleSize,
                                           std::uintptr_t offset,
                                           std::size_t expectedSize) noexcept {
    if (expectedSize == 0 || moduleSize < expectedSize || offset > moduleSize - expectedSize) {
        return false;
    }
    const std::uintptr_t candidate = base + offset;
    const std::uintptr_t imageEnd = base + moduleSize;  // base 是真映像基址，不会回绕
    if (candidate < base || candidate > imageEnd) {
        return false;
    }
    return expectedSize <= imageEnd - candidate;
}

//: 解析一个引擎入口的地址：**范围 + 可读 + 逐字节核对**三条全过才写 `*address`。
//:
//: 三条判据的来源与顺序：
//:   1. `EntryWithinImage` —— 偏移本身要落在映像里（拦"偏移写错了"的大多数情况）；
//:   2. `engine_memory::ReadAt` —— 那段地址真的可读（拦"这段映射压根不在"）；
//:   3. 读出来的 16 字节与常量里记的**逐字节相等** —— 拦"偏移落到别的函数头上"。
//:
//: ★ 读整段用**一次** `ReadAt`（读满 16 字节、问判定一次），与各调用点原来的写法一致 ——
//:   不要改成逐字节读：那会把可读判定的调用数乘 16（每帧路径上这是有代价的）。
//:
//: 返回 false 时**不写** `*address`（调用方拿到的仍是自己的初值，不会拿到半个结果）。
[[nodiscard]] inline bool ResolveEntryAddress(
    std::uintptr_t base, std::size_t moduleSize, std::uintptr_t offset,
    const std::array<std::uint8_t, kEntryPrologueBytes>& expected, std::uintptr_t* address,
    ReadableCheck readable) noexcept {
    if (address == nullptr || readable == nullptr) {
        return false;
    }
    if (!EntryWithinImage(base, moduleSize, offset, expected.size())) {
        return false;
    }
    const std::uintptr_t candidate = base + offset;
    std::array<std::uint8_t, kEntryPrologueBytes> actual{};
    if (!engine_memory::ReadAt(candidate, &actual, readable) || actual != expected) {
        return false;
    }
    *address = candidate;
    return true;
}

// ============================================================================
// 第二种形状：**地址已经算好了**，我只核对它上面的若干字节（批次 112）
// ============================================================================
//
// `ResolveEntryAddress` 的形状是"给我基址 + 偏移，我自己算地址"；但项目里还有一族调用点，
// 地址是从**别处**拿来的 —— Lua 侧传进来的方法地址、GOT 槽里记着的入口、钩子中继记下的原函数。
// 它们要回答的是"这段地址上确实是那个入口吗"。以前这件事同样在每个调用点各自写一遍：
// 自己 `svcQueryMemory`、自己 `memcmp(reinterpret_cast<const void*>(address), …)`。
// 现在也收在这里 —— **调用点不再出现 `reinterpret_cast`**（这正是本层存在的理由）。
//
// ★ **判定由调用方注入**（与 L1 同一个 `ReadableCheck`）：本层不做"这是不是代码段"的判断。
//   例如 `runtime/source/lua_runtime.cpp` 注入的是"必须落在 `MemType_ModuleCodeStatic` 且
//   `Perm_Rx` 的映射里"（比通用可读判定**严**：只认模块映像的代码段），
//   `game_observer.cpp` 那一族注入"可读且不可执行"。注入什么就是什么，本层不替它放宽。

//: 在**已经由调用方确认过**的一段地址上做逐字节比较（**不再问判定**）。
//:
//: **误用后果**：喂进一个没核对过的地址 = 读没校验过的内存 ⇒ 只喂刚被 `VerifyEntryBytes`
//: 或调用方自己的判定刚放行过的地址（与 L1 的 `LoadVerifiedAt` 是同一条纪律）。
//: 单独给这个名字，是因为"**一次核对、多次比较**"是既有形状：`lua_runtime.cpp` 的零占洞入口
//: 核对要在一个 16 字节窗口里比三段（入口 4 字节 / 原序言尾巴 12 字节 / stub 两个指令字），
//: 那个窗口**只问一次内核** —— 这个性质必须保留（逐段各问一次会把系统调用数乘上去）。
[[nodiscard]] inline bool BytesMatchAt(std::uintptr_t address, const std::uint8_t* expected,
                                       std::size_t expectedSize) noexcept {
    if (address == 0 || expected == nullptr || expectedSize == 0) {
        return false;
    }
    return std::memcmp(engine_memory::AsObject(address), expected, expectedSize) == 0;
}

//: 同上，但比的是**一个小值**（几个字节的常量字，例如入口 stub 的两条指令字）。
//: 存在的理由与 `BytesMatchAt` 一样，另外省掉调用点那处
//: `reinterpret_cast<const void*>(&常量)`。
template <typename T>
[[nodiscard]] inline bool ValueMatchesAt(std::uintptr_t address, const T& value) noexcept {
    static_assert(std::is_trivially_copyable<T>::value,
                  "这里按字节比较 —— 只接受可平凡复制的标量（几个字节的常量字）");
    if (address == 0) {
        return false;
    }
    return std::memcmp(engine_memory::AsObject(address), &value, sizeof(T)) == 0;
}

//: 核对"一个**已经在别处算好的地址**上的若干字节"：可读（注入判定）+ 逐字节相等。
//:
//: 两条判据的顺序与各调用点原来那句"先问内核、再 `memcmp`"逐条一致；问判定**只问一次**、
//: 覆盖整段（逐字节问会把 `svcQueryMemory` 的调用数乘上长度）。任一条不成立 ⇒ `false`
//: —— 调用方据此拒绝，**绝不跳一个没核对过的地址**。
[[nodiscard]] inline bool VerifyEntryBytes(std::uintptr_t address, const std::uint8_t* expected,
                                           std::size_t expectedSize,
                                           ReadableCheck readable) noexcept {
    if (address == 0 || expected == nullptr || expectedSize == 0 || readable == nullptr ||
        address > UINTPTR_MAX - expectedSize) {
        return false;
    }
    if (!readable(address, expectedSize)) {
        return false;
    }
    return BytesMatchAt(address, expected, expectedSize);
}

//: ★ 全仓**唯一一处**"整数地址 → 带签名的引擎函数指针"的转换。
//:
//: 为什么必须只有一处：这个转换**本身不可核对** —— 一旦转出来，它就是个"能调的地址"，
//: 后面谁顺手调一下都可能跳到别处去改引擎状态。把它收在这里，是为了让"哪些地方在调引擎函数"
//: 能靠**一个符号名**（`AsFunction` / `ResolveFunction`）搜出来，而不是逐处去读
//: `reinterpret_cast<...>`（那正是诊断文档里"全仓 945 处"的成因，也是真机卡死的源头面）。
//:
//: `address == 0` ⇒ 返回 `nullptr`：**绝不返回一个"看起来能调"的坏地址**。
//: 本函数**不做**可读 / 映像归属的核对 —— 交进来的地址必须是**已经核对过**的（要么来自
//: 上面的 `ResolveEntryAddress`，要么来自钩子中继记下的原函数，要么是引擎自己交回来的指针）。
template <typename Fn>
[[nodiscard]] inline Fn AsFunction(std::uintptr_t address) noexcept {
    static_assert(std::is_pointer_v<Fn>,
                  "Fn 必须是**函数指针**类型（例如 void (*)(void*)）—— 本层只做这个转换");
    return address == 0 ? nullptr : reinterpret_cast<Fn>(address);
}

//: 一步到位：解析（含全部守卫）⇒ 转换成带签名的函数指针；任一条不成立 ⇒ `nullptr`。
//:
//: 这是调用点最常用的那个名字 —— 上面两个函数是它的两半（想只要地址不要签名时用前者）。
template <typename Fn>
[[nodiscard]] inline Fn ResolveFunction(
    std::uintptr_t base, std::size_t moduleSize, std::uintptr_t offset,
    const std::array<std::uint8_t, kEntryPrologueBytes>& expected,
    ReadableCheck readable) noexcept {
    std::uintptr_t address = 0;
    if (!ResolveEntryAddress(base, moduleSize, offset, expected, &address, readable)) {
        return nullptr;
    }
    return AsFunction<Fn>(address);
}

}  // namespace isaac::runtime::engine_call