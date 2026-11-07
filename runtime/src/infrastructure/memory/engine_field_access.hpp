#pragma once

// 引擎内存访问层（L1）：**偏移算术、对齐检查、可读性调用、取值**只在这里出现一次。
//
// 为什么会有这个文件（背景与证据）：`docs/架构诊断-框架为什么失效-20260924.md` ——
// 框架过去只建成了"挂点安装 + 回调派发"，**"和引擎打交道"从来没被框架接管** ⇒ 每个功能
// 各自伸手做"指针 + 偏移"，全仓累积 945 处 `reinterpret_cast`。一处写错 ⇒ 内存被写坏 ⇒
// 之后抛 C++ 异常时栈已坏 ⇒ libgcc 展开失败直接 `abort` ⇒ 静默卡死（2026-09-24 真机两次）。
// 用法与红线见 `docs/加一个功能模块的做法.md` 第三节。
//
// ## 本层负责什么、不负责什么
//
// 负责：把"`base + offset` 处的这个字段读出来 / 写进去"这件事做对 —— 回绕检查、对齐检查、
// 按 `T` 取值或落值，全部收在这一个文件里。功能代码**只写"读/写哪个字段"，不再写指针算术**。
// 从这里起还提供唯一一份"这段地址可读吗"（`EngineMemoryReadable`，起）、
// **唯一一份**"这段地址可写吗"（`EngineMemoryWritable`）与写原语（`WriteField` / `WriteAt`，
// 起）—— 在此之前四个 Lua API 族各有一份逐字相同的读判定、两个可写 TU 各有一份
// 逐字相同的写判定与 `memcpy` 写。
//
// 可读 ≠ 可写：两份判定刻意分开、并排放（`Perm_R` 与 `Perm_W`、读缓存与写缓存）。
//   写路径拿读判定放行，会让 `Sprite.Scale = 2` 去写只读页（真机 = `Data Abort`）。
//
// **判定仍可由使用方注入更严的**：`game_observer.cpp` 用的是"可读**且不可执行**"那一份
// （要求 `Perm_R` 且**不带** `Perm_X`，作为"指针没跑进代码段"的廉价校验），它按原文门禁保留在
// 那个 TU 里，通过本层的 `ReadableCheck` 参数传进来。层只负责"什么时候问、问几遍、问完怎么取"。
//
// ## 调用点怎么写
//
//     // `check` 是使用方自己那份"这段内存可读吗"（game_observer.cpp 用的是
//     // `IsReadableNonExecutableMapping`：要求带 `Perm_R` 且**不带** `Perm_X`）。
//     std::uint32_t stage = 0;
//     if (!isaac::runtime::engine_memory::ReadField(game, kLevelStageOffset, &stage, &check)) {
//         return GameLevelStageObservation::GameUnreadable;
//     }
//
// ⇒ 调用点里不再有 `reinterpret_cast`，也不再自己写 `address > UINTPTR_MAX - offset`。
//
// ## 线程
//
// 全部是**无状态**的纯函数，可重入、线程无关；唯一的外部副作用是通过 `check` 去问内核，
// 那一层的缓存与线程安全由 `engine_memory_guard.hpp` 负责（它已是验证过的实现，不要重写）。

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <type_traits>

#include "infrastructure/memory/engine_memory_guard.hpp"

// 设备侧那句 `svcQueryMemory` 要用 libnx；**只在 `__SWITCH__` 下引它**。
// ⚠️ 由此带来一条使用约束：**本头文件不能与 devkitpro 的 `<switch.h>` 出现在同一个编译单元里**
// （vendored 与 devkitpro 的 `MemoryInfo` 字段顺序不同 ⇒ 冲突）。本仓库当前只有 2 个编译单元
// 包含 `<switch.h>`（宿主插件与 SaltyNX 桥），都不是本层的消费者。
#if defined(__SWITCH__)
#include "lib/nx/nx.h"
#endif

namespace isaac::runtime::engine_memory {

// 「这段地址能读吗」—— 由使用方提供（见文件顶部说明：本层不引 libnx）。
//
// **刻意不是 `noexcept` 函数指针**：使用方现有的判定函数（例如 `IsReadableNonExecutableMapping`）
// 都没有写 `noexcept`，而 C++ 不允许把"非 noexcept 函数指针"隐式转成"noexcept 函数指针"
// ⇒ 写成 `noexcept` 会让所有现有判定函数都传不进来。
using ReadableCheck = bool (*)(std::uintptr_t address, std::size_t length);

// 一段区间能不能用：地址非零、长度非零、`address + length` 不回绕。
// 与 `engine_memory_guard.hpp` 的 `EngineGuardRangeUsable` 逐条同义（那里是宿主/设备都要过的第一道）。
[[nodiscard]] inline bool RangeUsable(std::uintptr_t address, std::size_t length) noexcept {
    return address != 0 && length != 0 && address <= UINTPTR_MAX - length;
}

// 一个**指针值**能不能当对象用：非零、8 字节对齐、它自己那 8 字节可读。
// 对应原实现里"读到 owner / Game* 之后先校一遍再往下跳"的那两行（跳指针链的每一跳都要）。
[[nodiscard]] inline bool PointerUsable(std::uintptr_t value, ReadableCheck readable) noexcept {
    return value != 0 && (value & (alignof(std::uintptr_t) - 1)) == 0 &&
           readable != nullptr && readable(value, sizeof(std::uintptr_t));
}

// ============================================================================
// 「这段地址可读吗」—— 唯一一份实现
// ============================================================================
//
// 语义**逐条照搬**此前四个 Lua API 族各写一份的那份（去掉注释后四份逐字相同，781 字符）：
//
//   ① 空地址 / 长度 0 / `address + length` 回绕 ⇒ 不可读；
//   ② 派发作用域内命中已登记的映射区间 ⇒ 直接答"可读"（**不进内核** —— 这是 2026-09-13
//      "物品信息显示卡顿"的修复核心）；
//   ③ 否则问一次内核：返回码失败 / 空映射 / 地址不在该映射内 / 不带 `Perm_R` ⇒ 不可读；
//   ④ 成功则把**整段**连续且权限一致的映射登记进缓存，之后的检查都命中缓存。
//
// 这里不看 `Perm_X`：可执行的代码段也算"可读"。要"可读且不可执行"的调用方自己注入
//   （`game_observer.cpp` 就是这么做的），不要改这一份 —— 改了会动到四个 API 族的既有语义。
[[nodiscard]] inline bool EngineMemoryReadable(std::uintptr_t address, std::size_t length) noexcept {
    if (!RangeUsable(address, length)) {
        return false;
    }
#if defined(__SWITCH__)
    if (EngineGuardLookupCached(address, length)) {
        return true;
    }
    const std::uint64_t syscallStart = EngineGuardSyscallBegin();
    MemoryInfo info{};
    u32 pageInfo = 0;
    // 显式写 `std::uint32_t`：有些 TU 的命名空间里有一个同名模板 `Result<T>` 会遮蔽 libnx 的
    // `Result`（u32）typedef，直接写 `Result` 会撞上模板推导。
    const std::uint32_t result = svcQueryMemory(&info, &pageInfo, address);
    EngineGuardSyscallEnd(syscallStart);
    if (R_FAILED(result) || info.size == 0 || info.addr > UINTPTR_MAX - info.size) {
        return false;
    }
    if (address < info.addr || address + length > info.addr + info.size ||
        (info.perm & Perm_R) == 0) {
        return false;
    }
    // 这次系统调用描述的是一整段连续且权限一致的映射，整段都可以复用这个结论。
    EngineGuardRememberReadable(info.addr, info.addr + info.size);
    return true;
#else
    // 宿主构建没有 `svcQueryMemory`；宿主测试的"引擎内存"是本进程 malloc 出来的伪造块，
    // 本来就一定可读。
    return true;
#endif
}

// ============================================================================
// 「这段地址可写吗」—— 唯一一份实现
// ============================================================================
//
// **刻意紧挨着上面那份读判定放**，因为这两件事最容易被搞混：
//
//   * 判定看的是 `Perm_W`（不是 `Perm_R`）—— 模块映像的代码段与只读数据段就是
//     "可读而不可写"，拿读判定给写路径放行 ⇒ `Sprite.Scale = 2` 去写只读页 ⇒ 真机 `Data Abort`；
//   * 命中的是**写**缓存（`EngineGuardLookupWritable` / `EngineGuardRememberWritable`），
//     与读缓存**分家**（`engine_memory_guard.hpp` 里两个实例本就分开，别合并）。
//
// 语义与读侧**逐条同形**：空 / 长度 0 / 回绕 ⇒ 不可写；命中写缓存 ⇒ 直接答"可写"（不进内核）；
// 否则问一次内核并按整段映射登记。此处这份**逐条照搬**此前 `sprite_api.cpp` 与 `isaac_api.cpp`
// 各写一份的那份实现（两份去掉注释后逐字相同），判决条件一条没改 —— 变的只是"实现在几处"：2 ⇒ 1。
[[nodiscard]] inline bool EngineMemoryWritable(std::uintptr_t address, std::size_t length) noexcept {
    if (!RangeUsable(address, length)) {
        return false;
    }
#if defined(__SWITCH__)
    if (EngineGuardLookupWritable(address, length)) {
        return true;
    }
    const std::uint64_t syscallStart = EngineGuardSyscallBegin();
    MemoryInfo info{};
    u32 pageInfo = 0;
    const std::uint32_t result = svcQueryMemory(&info, &pageInfo, address);
    EngineGuardSyscallEnd(syscallStart);
    if (R_FAILED(result) || info.size == 0 || info.addr > UINTPTR_MAX - info.size) {
        return false;
    }
    if (address < info.addr || address + length > info.addr + info.size ||
        (info.perm & Perm_W) == 0) {
        return false;
    }
    EngineGuardRememberWritable(info.addr, info.addr + info.size);
    return true;
#else
    // 宿主构建没有 `svcQueryMemory`；宿主测试里的"引擎内存"是本进程申请出来的伪造块，本来可写。
    return true;
#endif
}

// 读"某个**已经算好的地址**处的 `T`"，**不做对齐检查** —— 与各 TU 原来那份
// `ReadEngine(address, &value)` 逐字同义（它们也只做可读性检查）。
//
// 定义放在 `ReadField` **之后**：它要调 `ReadField`，而模板体内的非依赖名字在定义处就要找到。
// 为什么单列它：把那些调用点搬进层时，"偏移算术发生在别处（例如 `receiver + row->offset`
// 已经算好）"是最常见的形状；有这个名字就不用让调用点写 `ReadField(addr, 0, …)` 那个
// 看着像笔误的 `0`，也不必额外加一条原实现里没有的对齐判据。
// 出参写 `T* const&`（不是 `T*`）是与定义处同一条纪律：挡住"传裸 C 数组"时静默退化成
//   元素指针（真机事故见下面 `ReadField` 那一段）。两处必须一致 —— 只改一处会变成"两个不同的
//   重载并存" ⇒ 所有指针实参的调用都会判成 ambiguous（第一次构建就是这么红的）。
template <typename T>
[[nodiscard]] inline bool ReadAt(std::uintptr_t address, T* const& value,
                                 ReadableCheck readable) noexcept;

// 基址适配：对象指针 → 整数地址；整数地址 → 不透明指针。
// 存在的意义只有一个 —— **把 `reinterpret_cast` 收在本文件里**，调用点不再出现它。
[[nodiscard]] inline std::uintptr_t AddressOf(const void* object) noexcept {
    return reinterpret_cast<std::uintptr_t>(object);
}

[[nodiscard]] inline void* AsObject(std::uintptr_t address) noexcept {
    return reinterpret_cast<void*>(address);
}

// 从一个**槽**里取一个指针（槽本身按 `PointerUsable` 校一遍）。
//
// 返回 false = 槽不可用（空/未对齐/不可读）⇒ 调用方按"读不到"处理。
// 返回 true 时 `*value` 可能是 0 —— **空指针与读不到是两件事**，语义由调用方决定
// （`game_observer` 一族把它分成 `OwnerNull` / `GameNull` 与 `*Unreadable` 两档，
//  这个区分会进崩溃报告的状态码，所以不能在这里合并掉）。
[[nodiscard]] inline bool LoadPointer(std::uintptr_t slot, std::uintptr_t* value,
                                      ReadableCheck readable) noexcept {
    if (value == nullptr || !PointerUsable(slot, readable)) {
        return false;
    }
    std::memcpy(value, reinterpret_cast<const void*>(slot), sizeof(*value));
    return true;
}

// `base + offset` 处的字段地址（**只解出地址并确认那段可读，不取值**），失败返回 0。
//
// 为什么需要它：`ReadCurrentGameItemPool` 返回的是 ItemPool 那一段的**地址**而不是它的值，
// `requiredAlignment` 是 `base` 必须满足的对齐 —— 原实现里有些地方对 base 用了
// 8 字节（`alignof(uintptr_t)`）即使读的是 4 字节字段，那些地方显式传进来，语义逐条不变；
// **传 0 表示不做对齐检查**（原实现里也有一些读取点只查可读性、不查对齐）。
[[nodiscard]] inline std::uintptr_t FieldAddress(std::uintptr_t base, std::uintptr_t offset,
                                                 std::size_t width,
                                                 std::uintptr_t requiredAlignment,
                                                 ReadableCheck readable) noexcept {
    if (readable == nullptr || width == 0) {
        return 0;
    }
    if (requiredAlignment != 0 && (base & (requiredAlignment - 1)) != 0) {
        return 0;
    }
    if (offset > UINTPTR_MAX - base) {
        return 0;
    }
    const std::uintptr_t field = base + offset;
    if (!readable(field, width)) {
        return 0;
    }
    return field;
}

// 读"`base + offset` 处的那个指针字段"：回绕 + 对齐 + 可读性 + 取值。
// 取出来的**值本身不做校验**（原实现里也是下一跳才校 —— 槽可用与槽里的值可用是两件事）。
[[nodiscard]] inline bool LoadPointerAt(std::uintptr_t base, std::uintptr_t offset,
                                        std::uintptr_t requiredAlignment, std::uintptr_t* value,
                                        ReadableCheck readable) noexcept {
    if (value == nullptr) {
        return false;
    }
    const std::uintptr_t field =
        FieldAddress(base, offset, sizeof(std::uintptr_t), requiredAlignment, readable);
    if (field == 0) {
        return false;
    }
    std::memcpy(value, reinterpret_cast<const void*>(field), sizeof(*value));
    return true;
}

// 读一个字段：`base + offset` 处按 `T` 取出来。失败（不可读/未对齐/回绕/参数为空）返回 false，
// 此时**不写** `*value`（调用方保留自己的初值，与原来"先在栈上放 0 再判"的写法等价）。
//
// `requiredAlignment` 默认按 `T` 的对齐要求；原实现里有几处对 base 用 8 字节对齐检查，
// 那些调用点显式传 `alignof(std::uintptr_t)`，判定条件逐条不变。
template <typename T>
[[nodiscard]] inline bool ReadField(std::uintptr_t base, std::uintptr_t offset, T* const& value,
                                    ReadableCheck readable,
                                    std::uintptr_t requiredAlignment = alignof(T)) noexcept {
    static_assert(std::is_trivially_copyable<T>::value,
                  "引擎字段必须是可平凡复制的标量/小结构 —— 这里按字节拷贝，不做构造");
    if (value == nullptr) {
        return false;
    }
    const std::uintptr_t address =
        FieldAddress(base, offset, sizeof(T), requiredAlignment, readable);
    if (address == 0) {
        return false;
    }
    std::memcpy(value, reinterpret_cast<const void*>(address), sizeof(T));
    return true;
}

// 读一整段时不许传裸 C 数组（2026-09-24 ，真机事故换来的，别删）：
//
// 为什么出参写成上面那个 `T* const&`（**不是** `T*`）：
//   * 引用形参**不做"数组 → 指针"退化** ⇒ C 数组实参在**推导阶段就匹配不上** `T*`
//     （gcc 的原话：`could not match 'T *' against 'float[2]'`）；
//   * 于是"传裸数组"会命中下面那个 **`= delete`** 的重载 ⇒ **编译错误**。
//
// 为什么必须堵死这件事（事故本身）：出参若写成 `T*`，数组实参退化成元素指针 ⇒ 模板推出
// `T` = **元素类型** ⇒ `sizeof(T)` 只有**一个元素**：
//
//     float offset[2];
//     ReadField(manager, kCanvasOffset, offset, &check, 0);   // ✗ 只读 4 字节，编译得过！
//     ReadField(manager, kCanvasOffset, &offset, &check, 0);  // ✓ 整段 8 字节（T = float[2]）
//
// 坏的那一行**不报错、不崩、判定也只覆盖 4 字节**，第二个 float 原样留在初值 0 上。
// 上卡后就是这样翻的车：模组页那两个"画布偏移"float 只读到了 X ⇒ 页面位置的自证
// 修正拿 0 当 Y 去算 ⇒ **整页纵向偏出视野**；更糟的是**读数也跟着骗人**（同一个坏读让
// "实际画点"看起来仍是 (173, 72)），现场只留下 X 对、Y 成了 0 这一个指纹。
//
// ⇒ **要读一整段就写 `&数组`**；要读一个标量就写 `&标量`。谁想再犯都犯不了（编译期挡住）。
// 写侧不需要这一手：`WriteField` 的参数是 `const T&`，C 数组按引用绑定、长度本来就是对。
template <typename T, std::size_t N>
[[nodiscard]] inline bool ReadField(std::uintptr_t, std::uintptr_t, T (&)[N], ReadableCheck,
                                    std::uintptr_t = 0) = delete;

// `ReadAt` 的定义（声明见上 —— 它要调 `ReadField`，所以定义必须排在这里之后）。
template <typename T>
[[nodiscard]] inline bool ReadAt(std::uintptr_t address, T* const& value,
                                 ReadableCheck readable) noexcept {
    return ReadField(address, 0, value, readable, 0);
}

// `ReadAt` 的同一道保险（理由见上面 `ReadField` 那段）：裸 C 数组一律编译错误。
template <typename T, std::size_t N>
[[nodiscard]] inline bool ReadAt(std::uintptr_t, T (&)[N], ReadableCheck) = delete;

// 在**已经由 `FieldAddress` 确认过可读**的地址上取值（**不重复问内核**）。
//
// 这是每帧路径上"查一次、取多次"的关键：`ReadGameRenderOffset` 就是"一段 8 字节确认可读之后
// 连取两个 float"，重复调用 `ReadField` 会让每个 float 都各做一次 `svcQueryMemory`。
// **误用后果**：喂进一个没确认过的地址就是读没校验过的内存 ⇒ 只喂 `FieldAddress`/`ReadField`
// 刚返回的那个地址。
template <typename T>
[[nodiscard]] inline bool LoadVerifiedAt(std::uintptr_t address, std::size_t index,
                                         T* const& value) noexcept {
    if (address == 0 || value == nullptr) {
        return false;
    }
    const std::size_t offset = index * sizeof(T);
    if (offset > UINTPTR_MAX - address) {
        return false;
    }
    // 2026-09-26（的设备构建抓出来的）：这一句曾让设备构建编译不过 ——
    //   devkitA64 的 `-Werror=array-bounds` 在 `isaac_api.o` 上报
    //   `array subscript 0 is outside array bounds of 'const void [0]'`，指的就是这一行。
    //   **它不是真缺陷**（`address == 0` 在上面已经先返回假 ⇒ 这里永远不会真去读地址 0），
    //   而是编译器的一个误报：深度内联之后它把"由整数转来的 `void*`"当成一个**大小 0 的对象**
    //   （诊断里的 `const void [0]`），于是把 `memcpy` 访问的第 0 个字节算成"下标 0 越界"；
    //   报错处那句 `note: source object is likely at address zero` 说明它拿的是"**很可能**为 0"
    //   这种猜测，而不是证明。触发与否取决于"当次哪一段被内联" ⇒ 在别的编译单元改代码
    //   也可能把它翻出来（这次就是：改了 `isaac_api.cpp`，红的是一个既有的调用链
    //   `IsPickupEntity → ClassifyCallbackEntity → CaptureEntity → ReadEngineUnchecked`）。
    //   **修法只改形状、不改任何判据**：先用一句空 asm 把地址记进寄存器、让编译器**不知道**它的值
    //   （寄存器级、零运行时代价），它就没有"很可能为 0"可猜了。
    //   ⚠️ 纪律：**不许**用 `-Wno-array-bounds` 或降 `-Werror` 来绕 —— 那会把真正的越界一起放过去；
    //   上面那三道判据（地址非 0、出参非空、偏移不溢出）一条都不动。
    std::uintptr_t source = address + offset;
#if defined(__GNUC__) || defined(__clang__)
    __asm__ __volatile__("" : "+r"(source));
#endif
    std::memcpy(value, reinterpret_cast<const void*>(source), sizeof(T));
    return true;
}

// 取第 0 个（常见形态：`FieldAddress` 确认 8 字节、然后取两个 float 里的第一个）。
template <typename T>
[[nodiscard]] inline bool LoadVerified(std::uintptr_t address, T* const& value) noexcept {
    return LoadVerifiedAt(address, 0, value);
}

// 与 `ReadField` 同一道保险（理由见那一处）：裸 C 数组一律编译错误 —— 要整段就写 `&数组`。
template <typename T, std::size_t N>
[[nodiscard]] inline bool LoadVerifiedAt(std::uintptr_t, std::size_t, T (&)[N]) = delete;
template <typename T, std::size_t N>
[[nodiscard]] inline bool LoadVerified(std::uintptr_t, T (&)[N]) = delete;

// 一个"取对象指针、返回 bool"的引擎方法（`Game::IsGreedMode` / `Level::IsAscent` 这一类）的签名。
// 存在的意义：把 `reinterpret_cast<Fn>(thunk)` 与 `reinterpret_cast<const Object*>(address)`
// 这两处转换收进本层，调用点不再出现。
template <typename Signature>
struct UnaryMethod;

template <typename Result, typename Argument>
struct UnaryMethod<Result (*)(Argument)> {
    using ResultType = Result;
    using ArgumentType = Argument;
};

// 调一个一元"对象方法"：`thunk` 的地址已经由调用方验证过**是可执行的模块代码**
// （`IsMappedRxModuleCodeWindow` 那一道，属于调用方的职责 —— 本层不做代码段判定）。
template <typename Signature>
[[nodiscard]] inline typename UnaryMethod<Signature>::ResultType CallUnaryMethod(
    std::uintptr_t thunk, std::uintptr_t object) noexcept {
    using Argument = typename UnaryMethod<Signature>::ArgumentType;
    if (thunk == 0) {
        return typename UnaryMethod<Signature>::ResultType{};
    }
    const auto method = reinterpret_cast<Signature>(thunk);
    return method(reinterpret_cast<Argument>(object));
}

// ============================================================================
// 写侧：唯一一份"往引擎对象写字段"的实现
// ============================================================================
//
// 对称读侧的 `ReadField` / `ReadAt`；判定用上面那份 `EngineMemoryWritable`，由调用方以
// `WritableCheck` 传进来（理由与读侧相同 —— 层不引 libnx，只负责"什么时候问、问几遍"）。
//
// 为什么不能写成 `*reinterpret_cast<float*>(address) = value`：写与读**危险等级不同** ——
// 读错地址最坏读到垃圾，**写错地址是静默破坏别人的内存**（症状是随机崩溃 / 存档损坏，
// 而且事后无从归因）。所以这里只有一条纪律：**先确认可写，再写**。
//
// 用法（与读侧的 `ReadField` 逐字对称）：

//     if (!isaac::runtime::engine_memory::WriteField(
//             entity, kEntityPlayerControlsCooldownOffset, value, &IsEngineMemoryWritable)) {
//         return false;   // 拿不到可写权限 ⇒ 什么都不做
//     }

// 「这段地址可写吗」—— 与 `ReadableCheck` 是**同一个签名**（同构函数指针），单列一个名字
// 只为让调用点读得出"这里注入的是**写**判定"。两者的缓存与语义完全不同，**不能互换使用**。
using WritableCheck = bool (*)(std::uintptr_t address, std::size_t length);

// 写一个字段：`base + offset` 处按 `T` 落值。失败（不可写 / 未对齐 / 偏移回绕 / 判定为空）
// 返回 false，此时**一个字节都不落** —— 与读侧"失败时不写出参"逐条对称。
//
// 复用 `FieldAddress`：回绕与对齐两条判据与读侧是同一个函数，只是注进去的判定换成"可写"。
//   `requiredAlignment` 的语义同 `ReadField`：默认按 `T` 的对齐要求，**传 0 表示不查对齐**。
template <typename T>
[[nodiscard]] inline bool WriteField(std::uintptr_t base, std::uintptr_t offset, const T& value,
                                     WritableCheck writable,
                                     std::uintptr_t requiredAlignment = alignof(T)) noexcept {
    static_assert(std::is_trivially_copyable<T>::value,
                  "引擎字段必须是可平凡复制的标量/小结构 —— 这里按字节拷贝，不做构造");
    const std::uintptr_t address =
        FieldAddress(base, offset, sizeof(T), requiredAlignment, writable);
    if (address == 0) {
        return false;
    }
    // 复用 `AsObject`（层里"整数地址 → 不透明指针"的唯一一处转换）而不是在这里再写一次
    //   `reinterpret_cast`：冻结台账 `tools/raw_engine_access_baseline.json` 按"每个文件的
    //   `reinterpret_cast` 计数"判、**只许减不许增** ⇒ 本层自己不能再多一处。
    std::memcpy(AsObject(address), &value, sizeof(T));
    return true;
}

// 往"某个**已经算好的地址**"写 `T`，**不做对齐检查** —— 等价于 `WriteField(address, 0, …)`，
// 对称读侧的 `ReadAt`。`WriteEngine(address, value)` 那种"地址已在别处算好"的形态落在这里。
template <typename T>
[[nodiscard]] inline bool WriteAt(std::uintptr_t address, const T& value,
                                  WritableCheck writable) noexcept {
    return WriteField(address, 0, value, writable, 0);
}

} // namespace isaac::runtime::engine_memory