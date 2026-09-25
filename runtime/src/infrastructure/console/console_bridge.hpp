#pragma once

// 游戏控制台 `IsaacRepentance::Console` 的**引擎桥**：把"我们自己的一个 Console 实例"接起来。
//
// ## 为什么需要它
//
// Switch 版把控制台"拆线"了：`Manager::IsDebuggingConsoleEnabled` 是 `mov w0,wzr; ret` 桩，
// `Console` 的构造/`Init`/`Update`/`Render`/`Show`/`ProcessInput`/`ShowKeyboard` **入边全是 0**
// ⇒ 引擎自己既不建这个对象、也不驱动它。**但类与全部命令实现都在镜像里**（`Console::RunCommand`
// 一个函数就 0x6070 字节，含 PC 全量命令）⇒ 我们自己在运行时里建一个实例、把命令喂进去，
// 就等于把 PC 控制台接回来。取证与证据见 `docs/问题与解决记录.md` 续四十 与 `runtime_constants.hpp`
// 里那一段常量注释（含"必须按 GOT+PLT 桩扫，直接扫 BL 必然全零"这条口径）。
//
// ## 三条跨模块纪律（都不是风格问题）
//
// 1. **对象存储属于我们，且不销毁**：Console 内部那两个 `deque` 的缓冲由**游戏**分配、由游戏释放
//    （`Clear`/析构里），而对象本身在我们手里。我们只构造、**从不调析构**（模块不卸载，走得掉）。
//    存放用**静态 POD 缓冲**（不是 `operator new`）——顺带避开"在钩子里手工配对 new/delete"那条红线。
// 2. **绝不把 `std::string` 交给对方再自己释放**：本模块**自带一份 libc++**（导入表里没有任何
//    分配器符号），游戏模块则从进程导入 `_Znwm`/`_ZdlPv` ⇒ 跨模块 free 会崩。所以：
//      * **命令串**：按游戏那份 libc++ 的**经典短串布局**手工拼 24 字节（首字节 = 长度<<1、
//        数据从 +1 开始；长度上限 22 ⇒ 永远落在内联存储里，**根本不涉及分配器**）；
//      * **输出串**：给引擎一块**全零的 24 字节缓冲**（在老布局里就是"空短串"），引擎自己 append
//        （短串就地、长串换成它自己的堆），**我们只按那一套布局读、从不 clear/析构**。
//      ⇒ 这条比"用我们自己的 std::string"安全得多：**不必假设两边的 libc++ 版本一致**。
//        实测（2026-09-25）：宿主/新版 libc++ 的短串是"数据从 +0 开始、标志在末字节"，
//        与游戏那份**不同**——照直写就错了。
// 3. **每次调引擎前先核对 16 字节入口守卫**（走 `engine_call::ResolveFunction`）；对不上就**不调**，
//    把失败写进状态面，而不是"盲跳一个地址"。
//
// ## 状态面
//
// 控制台**自报一份**（`g_ConsoleState`，读数工具按裸名取）。为什么不像模组菜单那样挤进
// `g_ModMenuState` 的编号清单：那一份的下标是**读数工具的契约**，插一格就让后面全挪位
// （2026-09-23 已犯过三次）；而控制台这几个量语义自成一块。读数工具本来就支持按名字读多份状态。

#include "domain/console/console_switch.hpp"
#include "domain/console/console_text.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "ports/save_file_port.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime::console {

//: 一次执行的结论码（进状态面 `[4]`，真机上据此判断走到哪一步 ⇒ 不必靠猜）。
enum class ExecStatus : std::uint32_t {
    kOk = 0,             // 引擎真的跑完了这条命令
    kEmptyCommand = 1,   // 空命令（不调引擎）
    kEntriesMissing = 2, // 入口没解析出来（守卫不符 / 基址没发布）
    kNoPlayer = 3,       // 没有玩家 ⇒ **不调**（见下面"玩家"那段：传 null 时引擎会读空指针）
    kTooLong = 4,        // 命令超过内联串上限
    kFenceBroken = 5,    // 发现对象缓冲越界写 ⇒ 停用（不再调引擎）
    kOutputFenced = 6,   // 输出串超过上限 ⇒ 拒绝新命令（不 free、不 clear）
    kDisabledBySwitch = 7,  // 总开关关着 ⇒ **一律拒绝**（这是 PC 的 `EnableDebugConsole=0` 语义）
};

//: 命令串的**内联**上限：老布局里短串数据在 `+1`，最后一个字节要留给 `\0` ⇒ 22。
//: （游戏自己也这么判：`Console::VirtualKeyboardFinished` 里 `cmp x0,#0x17` ⇒ ≥23 就走堆串。）
inline constexpr std::size_t kCommandInlineCapacity = 22;
//: 命令串的**总长度**上限（超出的走长布局，数据放我们自己的静态缓冲；缓冲要留一个结尾 `\0`）。
inline constexpr std::size_t kCommandBufferCapacity = 128;
//: 一条命令最多多少字节（= 缓冲容量 − 结尾 `\0`）。
inline constexpr std::size_t kCommandLengthLimit = kCommandBufferCapacity - 1;
//: 输出累计字节上限。超了就**拒绝新命令**（既不 free 也不 clear —— 那块内存是游戏分配的）。
inline constexpr std::size_t kOutputByteLimit = 64 * 1024;
//: 对象缓冲尾部的哨兵宽度：`Console` 写出界要能被发现，而不是踩到相邻静态变量。
inline constexpr std::size_t kObjectFenceBytes = 16;
//: 哨兵填充值。
inline constexpr unsigned char kObjectFenceValue = 0xA5;

//: 状态面（读数工具按裸名 `g_ConsoleState` 取；**字段只能往后追加**）。
struct BridgeState {
    std::uint32_t armed;            // [0]  1 = 这一整块编进来了
    std::uint32_t entriesResolved;  // [1]  入口解析结果位图：bit0 构造 / bit1 Init / bit2 RunCommand
                                    //      / bit3 参数块构造 / bit4 开键盘（0b11111 = 全齐）
    std::uint32_t objectCreated;    // [2]  1 = 那个 Console 实例已构造 + `Init` 过
    std::uint32_t commandsRun;      // [3]  引擎**真的被调**的次数
    std::uint32_t lastStatus;       // [4]  最近一次结论码（见 `ExecStatus`）
    std::uint32_t lastCommandLength;// [5]  最近一条命令的字节数
    std::uint32_t outputBytes;      // [6]  输出串累计长度（引擎侧增长）
    std::uint32_t lastOutputBytes;  // [7]  最近一次新增的输出字节数
    std::uint32_t keyboardRequests; // [8]  请求弹系统软键盘的次数
    std::uint32_t keyboardResults;  // [9]  软键盘回调交回文本的次数
    std::uint32_t lastAction;       // [10] 最近观察到"按住"的动作号（0xFFFFFFFF = 还没学到）
                                    //      ★ 真机上用它把"哪个键 = 哪个动作号"定下来
    std::uint32_t frames;           // [11] 每帧点跑过多少帧（证明这块代码真在跑）
    std::uint32_t outputIsLong;     // [12] 1 = 输出串已经换成引擎的堆缓冲（只读、永不释放）
    std::uint32_t fenceBroken;      // [13] 1 = 抓到过一次对象缓冲越界写（**必须恒 0**）
    std::uint32_t layoutChecks;     // [14] 字符串布局自检跑过几次（0 次 = 还没走到执行路径）
    std::uint32_t layoutOk;         // [15] 1 = 自检通过（首字节低 1 位 = 是否堆串那一套）
    std::uint32_t overlayFrames;    // [16] 输出还要在屏幕上留多少帧（0 = 没在显示）
    std::uint32_t triggerHeld;      // [17] 1 = 组合键当前按住（呼出用的长按判据）
    std::uint32_t actionsSeen;      // [18] 本会话里"被按住过"的动作号**累计位图**（bit N = 动作 N）
                                    //      ★ 诊断用：一次读数就能拿到整张"按键 ↔ 动作号"映射
                                    //      （[10] 只留最后一个，连打时会被顶掉）
    // ---- 批次 124：总开关（对应 PC 的 `EnableDebugConsole`，开关本体在模组页那一行）----
    std::uint32_t switchEnabled;    // [19] 1 = 控制台可用（默认；文件里 `enabled=0` 或用户在
                                    //      模组页上拨到关 ⇒ 0）。★ 0 时连 `Isaac.ExecuteCommand` 也拒
    std::uint32_t switchRefusals;   // [20] 因为开关关着而**被拒**的命令次数（含模组调 API 的那些）
    std::uint32_t switchFileFailures;  // [21] 开关状态文件读/写失败次数（端口没接上也算）
                                       //      ★ 读失败**不改开关值**（回默认"开"），只计数
};

// ★★ 符号形状踩过两次，两条都记下：
//   ① `extern "C" inline BridgeState g_ConsoleState = {};` ⇒ gcc 报
//      `'g_ConsoleState' initialized and declared 'extern'`（本构建 `-Werror` ⇒ 构建失败；
//      `mod_menu_native.cpp` 的 `g_ModMenuState` 也记过同一条）。
//   ② 把初始化列表去掉 ⇒ **两个编译器都不认**：那只是声明、不是定义
//      （clang：`inline variable ... is not defined`；gcc：`odr-used inline variable ... is not defined`）。
//   ⇒ 定案：**不加 `extern "C"`**，用命名空间内的 `inline` 变量（两边都接受、也不必写初始化列表之外的
//   额外东西）。代价是符号名成了**改编名** `_ZN5isaac7runtime7console14g_ConsoleStateE` ——
//   读数工具的 `SYM_ELF_NAMES` 就按这个名字取（`g_CallbackDispatchCounts` 那几个也是改编名，先例在）。
inline BridgeState g_ConsoleState{};
//: 起个短名字给本文件的实现用（读数工具仍按裸名取，名字不变）。
inline BridgeState& State() noexcept {
    return g_ConsoleState;
}

// --- 引擎入口类型（放一处；第一项是显式 `this`）------------------------------------
using ConsoleCtorFn = void (*)(void*);
using ConsoleInitFn = void (*)(void*);
//: `RunCommand(std::string const&, std::string*, Entity_Player*)` —— 三个参数我们都按裸指针传
//: （命令串与输出串是**手工拼的老布局缓冲**，见本文件头部第 2 条纪律）。
using ConsoleRunCommandFn = void (*)(void*, const void*, void*, void*);
using VirtualKeyboardParamsCtorFn = void (*)(void*);
//: `OpenVirtualKeyboard(VirtualKeyboardParams const&, unsigned int)`，`this` = `&KAGE::System::g_Manager`。
//: ★ `this` 写成 `std::uintptr_t` 而不是 `void*`：调用点拿到的就是整数地址，
//:   写成 `void*` 会在调用点逼出一个 `reinterpret_cast`（而**冻结台账按每个文件的
//:   `reinterpret_cast` 计数判、只许减不许增**，见 `tools/raw_engine_access_baseline.json`）。
//:   ABI 上完全一样（整数与指针都走 `x0`）。
using OpenVirtualKeyboardFn = void (*)(std::uintptr_t, const void*, std::uint32_t);
//: 软键盘回调签名：`void(wchar_t const*, void*)`（本平台 `wchar_t` = 4 字节）。
using VirtualKeyboardFinishedFn = void (*)(const std::uint32_t*, void*);

struct EngineEntries {
    ConsoleCtorFn consoleCtor{nullptr};
    ConsoleInitFn consoleInit{nullptr};
    ConsoleRunCommandFn runCommand{nullptr};
    VirtualKeyboardParamsCtorFn paramsCtor{nullptr};
    OpenVirtualKeyboardFn openKeyboard{nullptr};
};

//: 系统软键盘参数块。**布局来自 `Console::ShowKeyboard` 的反汇编**（引擎自己那份配方），
//: 由 `static_assert` 钉在 0x30 字节（改错就对不上，编译期就红）。
struct VirtualKeyboardParams {
    std::uint32_t flags;        // +0x00 构造时清零
    std::uint32_t padding;      // +0x04 对齐填充（构造只写 4 字节的 0，这里显式留着）
    std::uint32_t* text;        // +0x08 宽字符缓冲（**4 字节/字符**，见 `console_text.hpp` 的查证）
    std::uint32_t limit;        // +0x10 上限（引擎自己传 64）
    std::uint32_t reserved;     // +0x14
    //: 文本变化回调（+0x18）与完成回调（+0x20）：**直接写成函数指针类型**，
    //: 这样赋我们的回调时不需要任何转换（写 `void*` 会在调用点逼出一个 `reinterpret_cast`）。
    VirtualKeyboardFinishedFn textChanged;  // +0x18（不用，留空）
    VirtualKeyboardFinishedFn finished;     // +0x20
    void* userData;             // +0x28 回传给完成回调
};
static_assert(sizeof(VirtualKeyboardParams) == 0x30,
              "VirtualKeyboardParams 必须与引擎那份逐字节同形（0x30 字节）");

// ============================================================================
// 游戏那份 libc++ 的字符串布局（**经典**布局）—— 手工拼 / 只读解码
// ============================================================================
//
// 证据（都是游戏自己代码里的访问形状，不是猜的）：
//   * 判"是不是长串" = **首字节的低 1 位**：`ldrb w8,[s]` + `tst w8,#1`；
//   * 短串：长度 = **首字节 >> 1**（`lsr x9,x8,#1`），数据从 **+1** 开始（`add x1,s,#1`）；
//   * 长串：长度 = **+8 的 u64**，数据指针 = **+0x10 的 u64**
//     （`ldp x10,x8,[s,#0x8]` → `csel x2,x9,x10,eq` 取长度、`csinc x1,x8,s,ne` 取数据指针）。
// 出处：`Console::Print @ 0x3BFB4` 的前 16 条指令（读入参那个 `std::string const&`）。
//
// ★ 与宿主/新版 libc++ 的差别（2026-09-25 实测）：新版把短串数据放在 **+0**、标志放到末字节
//   ⇒ **两边布局不同**。所以这里手工拼字节，绝不把本模块的 `std::string` 交出去。
inline constexpr std::size_t kEngineStringBytes = 24;

//: 把一条命令写进"24 字节串头 + 数据缓冲"（返回 false = 超过总上限，不写）。
//:
//: 短命令（≤ 22）走**内联短串**：整条命令都在那 24 字节里，`+1` 起是数据。
//: 长命令走**长布局**，数据放调用方的静态缓冲（我们自己的内存），并把
//: `+0x00 = 容量|1`、`+0x08 = 长度`、`+0x10 = 数据指针`。
//: ★ 长布局这几条字段的出处是**游戏自己构造长串的代码**（`Console::VirtualKeyboardFinished`
//:   @ 0x3C65C）：`orr x8, x22, #0x1` → 写 `+0x00`（容量并上长串标志），随后
//:   `stp x20, x0, [sp,#0x10]` → 写 `+0x08` 长度、`+0x10` 数据指针。
//: ★ 安全性：引擎把命令当 `const&` 读（`split` 也是 `const&`）⇒ 它**不会**释放我们这块缓冲；
//:   我们也不用自己那份 libc++ 去析构它（那边布局都不一样，见本文件头部第 2 条纪律）。
[[nodiscard]] inline bool BuildCommandString(const char* command, std::size_t length,
                                             unsigned char* header, char* buffer,
                                             std::size_t bufferCapacity) noexcept {
    if (header == nullptr || command == nullptr || buffer == nullptr) {
        return false;
    }
    std::memset(header, 0, kEngineStringBytes);
    if (length <= kCommandInlineCapacity) {
        header[0] = static_cast<unsigned char>((length << 1) & 0xFFU);  // 短串：长度<<1，低 1 位 = 0
        std::memcpy(header + 1, command, length);
        return true;  // 结尾的 `\0` 由上面的 memset 提供（长度 ≤ 22 ⇒ 一定在缓冲内）
    }
    if (length + 1 > bufferCapacity) {
        return false;
    }
    std::memcpy(buffer, command, length);
    buffer[length] = '\0';
    const std::uint64_t capacity = static_cast<std::uint64_t>(bufferCapacity - 1) | 1ULL;
    const std::uint64_t size = static_cast<std::uint64_t>(length);
    const std::uintptr_t data = engine_memory::AddressOf(buffer);  // 走访问层的地址转换
    std::memcpy(header + 0x00, &capacity, sizeof(capacity));
    std::memcpy(header + 0x08, &size, sizeof(size));
    std::memcpy(header + 0x10, &data, sizeof(data));
    return true;
}



//: 输出串是不是已经换成引擎的堆缓冲（首字节低 1 位 = 1）。
[[nodiscard]] inline bool EngineStringIsLong(const unsigned char* string) noexcept {
    return string != nullptr && (string[0] & 0x01U) != 0U;
}

//: 输出串长度（按上面那套布局读）。
[[nodiscard]] inline std::size_t EngineStringSize(const unsigned char* string) noexcept {
    if (string == nullptr) {
        return 0;
    }
    if (!EngineStringIsLong(string)) {
        return static_cast<std::size_t>(string[0] >> 1);
    }
    std::uint64_t size = 0;
    std::memcpy(&size, string + 8, sizeof(size));
    return static_cast<std::size_t>(size);
}

//: 输出串数据指针（短串在缓冲内；长串是引擎堆上的地址 —— 用之前**必须**先判可读）。
[[nodiscard]] inline const char* EngineStringData(const unsigned char* string) noexcept {
    if (string == nullptr) {
        return nullptr;
    }
    if (!EngineStringIsLong(string)) {
        // 短串的数据就在我们自己的缓冲里（`+1` 起），按字节缓冲取指针即可。
        return static_cast<const char*>(static_cast<const void*>(string + 1));
    }
    std::uintptr_t data = 0;
    std::memcpy(&data, string + 0x10, sizeof(data));
    // 长串的数据在引擎堆上：地址 → 指针的转换走访问层那一处（调用点不做 `reinterpret_cast`）。
    return static_cast<const char*>(engine_memory::AsObject(data));
}

//: 布局自检：验证我们这套"读法"与本模块编译出来的 `sizeof` 观感一致。
//: 它**不是**在验证对方的 libc++（那验不了），而是把"缓冲够不够、判据读得对不对"钉住；
//: 真值还得靠真机（读数里 `outputBytes` 若明显不对，就是布局对不上）。
[[nodiscard]] inline bool StringLayoutSelfCheck() noexcept {
    unsigned char shortProbe[kEngineStringBytes]{};
    char shortBuffer[8]{};
    if (!BuildCommandString("ok", 2, shortProbe, shortBuffer, sizeof(shortBuffer))) {
        return false;
    }
    const bool shortOk = shortProbe[0] == 4 && shortProbe[1] == 'o' && shortProbe[2] == 'k' &&
                         shortProbe[3] == '\0' && !EngineStringIsLong(shortProbe) &&
                         EngineStringSize(shortProbe) == 2;
    // 长布局：首字节低 1 位必须是 1、`+8` 是长度、`+0x10` 是数据指针。
    unsigned char longProbe[kEngineStringBytes]{};
    char longBuffer[kCommandBufferCapacity]{};
    if (!BuildCommandString("giveitem c1 and a long tail", 28, longProbe, longBuffer,
                            sizeof(longBuffer))) {
        return false;
    }
    const char* longData = EngineStringData(longProbe);
    const bool longOk = EngineStringIsLong(longProbe) && EngineStringSize(longProbe) == 28 &&
                        longData == static_cast<const char*>(longBuffer) &&
                        longBuffer[28] == '\0';
    return shortOk && longOk;
}

// ============================================================================
// 静态存储（POD，无析构 ⇒ 不会注册 atexit 析构而误 free 引擎的内存）
// ============================================================================

struct Core {
    alignas(16) unsigned char consoleObject[kConsoleObjectSize]{};
    alignas(8) unsigned char commandString[kEngineStringBytes]{};  // 老布局，我方拼
    alignas(8) char commandBuffer[kCommandBufferCapacity]{};       // 长命令的数据（我方内存）
    alignas(8) unsigned char outputString[kEngineStringBytes]{};   // 老布局，引擎写、我方只读
    std::uint32_t keyboardText[kVirtualKeyboardTextCapacity]{};    // 软键盘的宽字符缓冲
    VirtualKeyboardParams keyboardParams{};
    ConsoleLog log{};
    //: 最近一次执行的**新增输出**（给 `Isaac.ExecuteCommand` 当返回值；超长截断）。
    char lastOutput[512]{};
    std::uint32_t lastOutputLength{0};
    //: 软键盘回调交回的命令（UTF-8），等**下一帧**再执行（回调里不调引擎）。
    char pendingCommand[kConsoleLogLineCapacity * 2]{};
    std::uint32_t pendingLength{0};
    bool pendingReady{false};
    bool objectReady{false};
    bool commandReady{false};
    bool outputReady{false};
    bool outputIsLong{false};
    //: 组合键**连续按住**了多少帧（松开清零）。呼出判据 = 这个计数到 `kConsoleTriggerHoldFrames`，
    //: 不是"按住的那一帧" —— A/B 是局内射击面键，连打时会在同一帧里同时按下（真机实测误触）。
    std::uint32_t comboHeldFrames{0};
    bool comboFired{false};  // 这一轮长按已经弹过键盘（一直按着不重复弹；松开才复位）
    // ---- 批次 124：总开关（值 + 两个"待办"；真正的 I/O 在每帧点里做，见 `ConsoleSwitchTick`）----
    bool switchEnabled{isaac::runtime::kConsoleSwitchDefaultEnabled};  // 缺文件 ⇒ 默认开
    bool switchReadPending{true};   // 开局第一帧读一次文件（那时已在游戏线程上）
    bool switchWritePending{false}; // 用户在模组页拨过开关 ⇒ 写一次
    bool switchWriteValue{false};
};

[[nodiscard]] inline Core& Storage() noexcept {
    static Core core{};
    return core;
}

// ============================================================================
// 总开关（批次 124）—— 对应 PC 的 `EnableDebugConsole`
// ============================================================================
//
// 三个入口分成两半，**故意不在一起**：
//   * 值：`ConsoleSwitchEnabled()`（每帧点与执行入口都问它，纯内存读，不做 I/O）；
//   * 拨动：`RequestConsoleSwitchWrite()`（模组页那一行调；**当场改内存**、只挂一个"待写"）；
//   * I/O：`ConsoleSwitchTick()`（**每帧点的最开头**调；只有挂了待办才真读/写文件）。
// 为什么 I/O 放在每帧点、而不是拨动的那一刻：拨动发生在菜单页的输入处理里（也在游戏线程，
// 但那一帧正在驱动引擎的菜单状态机）；按本项目一贯纪律"要动手就在每帧点做"，把文件 I/O
// 挪到每帧点开头最稳，且与污染标记那条路同一个位置口径。

//: 现在控制台可不可用。**每帧读它**（纯内存，不做 I/O）。
[[nodiscard]] inline bool ConsoleSwitchEnabled() noexcept {
    return Storage().switchEnabled;
}

//: 拨动开关（模组页那一行调）。**当场生效**（页面上的显示立刻变），只挂一个"待写"；
//: 真正落盘由 `ConsoleSwitchTick()` 在每帧点里做。写失败不回滚内存值（见 `.hpp` 的 fail-open 那段），
//: 但会记一次失败 ⇒ 读数里 `[21]` 会涨，不会静默。
inline void RequestConsoleSwitchWrite(bool enabled) noexcept {
    Core& core = Storage();
    core.switchEnabled = enabled;
    core.switchWriteValue = enabled;
    core.switchWritePending = true;
    State().switchEnabled = enabled ? 1U : 0U;
}

//: 每帧一次：把"开局读一次"与"拨动后写一次"做掉，并把 `[19]` 发布出去。
//: **只在游戏线程上调**（端口的实现自己也会拒绝别的线程）；没有待办时不碰文件系统。
inline void ConsoleSwitchTick() noexcept {
    Core& core = Storage();
    isaac::runtime::ISaveFilePort* storage = isaac::runtime::SessionSaveFilePort();
    if (core.switchReadPending) {
        core.switchReadPending = false;
        if (storage == nullptr) {
            ++State().switchFileFailures;  // 端口还没接上：如实记，不静默（开关停在默认值）
        } else {
            std::array<char, isaac::runtime::kConsoleSwitchMaximumBytes + 64> text{};
            std::size_t bytes = 0;
            const Status status = storage->Read(isaac::runtime::kConsoleSwitchFileName,
                                                text.data(), text.size(), &bytes);
            if (status.code() == StatusCode::NotFound) {
                // 第一次运行就是这样 ⇒ 默认值（开），**不算失败**。
                core.switchEnabled = isaac::runtime::kConsoleSwitchDefaultEnabled;
            } else if (!status.ok() || bytes > text.size()) {
                ++State().switchFileFailures;  // 读不动 ⇒ 停在默认值（开）
            } else {
                core.switchEnabled =
                    isaac::runtime::ParseConsoleSwitch(std::string_view(text.data(), bytes));
            }
        }
    }
    if (core.switchWritePending) {
        core.switchWritePending = false;
        if (storage == nullptr) {
            ++State().switchFileFailures;
        } else {
            std::array<char, isaac::runtime::kConsoleSwitchMaximumBytes> text{};
            const std::size_t length = isaac::runtime::SerializeConsoleSwitch(
                core.switchWriteValue, text.data(), text.size());
            if (length == 0) {
                ++State().switchFileFailures;  // 放不下 ⇒ 不写半截
            } else if (!storage->Write(isaac::runtime::kConsoleSwitchFileName,
                                       std::string_view(text.data(), length))
                            .ok()) {
                ++State().switchFileFailures;  // 写失败：内存值照旧生效，但跨重启不保 ⇒ 记账
            }
        }
    }
    State().switchEnabled = core.switchEnabled ? 1U : 0U;
}

// ============================================================================
// 解析入口（每次调用都重新核对 16 字节守卫；解析结果由调用方缓存）
// ============================================================================

[[nodiscard]] inline bool ResolveConsoleEntries(std::uintptr_t base, std::size_t moduleSize,
                                                EngineEntries* out) noexcept {
    if (out == nullptr || base == 0 || moduleSize == 0) {
        return false;
    }
    State().armed = 1;  // 走到这里就说明这一套编进来了（读数第 [0] 格的判据）
    out->consoleCtor = engine_call::ResolveFunction<ConsoleCtorFn>(
        base, moduleSize, kConsoleCtorOffset, kConsoleCtorExpectedBytes,
        &engine_memory::EngineMemoryReadable);
    out->consoleInit = engine_call::ResolveFunction<ConsoleInitFn>(
        base, moduleSize, kConsoleInitOffset, kConsoleInitExpectedBytes,
        &engine_memory::EngineMemoryReadable);
    out->runCommand = engine_call::ResolveFunction<ConsoleRunCommandFn>(
        base, moduleSize, kConsoleRunCommandOffset, kConsoleRunCommandExpectedBytes,
        &engine_memory::EngineMemoryReadable);
    out->paramsCtor = engine_call::ResolveFunction<VirtualKeyboardParamsCtorFn>(
        base, moduleSize, kKageVirtualKeyboardParamsCtorOffset,
        kKageVirtualKeyboardParamsCtorExpectedBytes, &engine_memory::EngineMemoryReadable);
    out->openKeyboard = engine_call::ResolveFunction<OpenVirtualKeyboardFn>(
        base, moduleSize, kKageOpenVirtualKeyboardOffset, kKageOpenVirtualKeyboardExpectedBytes,
        &engine_memory::EngineMemoryReadable);
    std::uint32_t resolved = 0;
    resolved |= out->consoleCtor != nullptr ? 1U : 0U;
    resolved |= out->consoleInit != nullptr ? 2U : 0U;
    resolved |= out->runCommand != nullptr ? 4U : 0U;
    resolved |= out->paramsCtor != nullptr ? 8U : 0U;
    resolved |= out->openKeyboard != nullptr ? 16U : 0U;
    State().entriesResolved = resolved;
    return out->consoleCtor != nullptr && out->consoleInit != nullptr &&
           out->runCommand != nullptr;
}

//: "读 `base + offset` 处的那个指针"（读不到返回 0）。走引擎内存访问层，功能代码里不写指针算术。
[[nodiscard]] inline std::uintptr_t LoadPointerField(std::uintptr_t base,
                                                    std::uintptr_t offset) noexcept {
    std::uintptr_t value = 0;
    if (!engine_memory::LoadPointerAt(base, offset, alignof(std::uintptr_t), &value,
                                      &engine_memory::EngineMemoryReadable)) {
        return 0;
    }
    return value;
}

//: `KAGE::System::g_Manager` 的**对象地址**（它的 GOT 槽里就是对象地址本身，不必再解一次）。
[[nodiscard]] inline std::uintptr_t KageSystemManager(std::uintptr_t base) noexcept {
    return LoadPointerField(base, kKageSystemManagerSlotOffset);
}

//: `Game*`：`g_Game` 是一个**指针变量**，所以槽 → 变量地址 → 再解一次才是 `Game*`。
[[nodiscard]] inline std::uintptr_t ResolveGame(std::uintptr_t base) noexcept {
    const std::uintptr_t variable = LoadPointerField(base, kGameOwnerGlobalSlotOffset);
    return variable != 0 ? LoadPointerField(variable, 0) : 0;
}

//: 玩家列表非空**且 `players[0]` 非 0**。两者缺一，引擎自己那条取玩家的路径就会读到空指针。
[[nodiscard]] inline bool HasUsableFirstPlayer(std::uintptr_t game) noexcept {
    if (game == 0) {
        return false;
    }
    const std::uintptr_t begin = LoadPointerField(game, kGamePlayerArrayBeginOffset);
    const std::uintptr_t end = LoadPointerField(game, kGamePlayerArrayEndOffset);
    if (begin == 0 || end <= begin) {
        return false;
    }
    return LoadPointerField(begin, 0) != 0;
}

//: 对象的尾部哨兵还在不在（构造/Init/执行之后各查一次）。
[[nodiscard]] inline bool ObjectFenceIntact(const Core& core) noexcept {
    for (std::size_t index = kConsoleObjectSize - kObjectFenceBytes; index < kConsoleObjectSize;
         ++index) {
        if (core.consoleObject[index] != kObjectFenceValue) {
            return false;
        }
    }
    return true;
}

//: 就绪 = 入口齐 + 对象已构造 + 哨兵完好。不做任何引擎调用。
[[nodiscard]] inline bool EnsureConsoleObject(const EngineEntries& entries) noexcept {
    Core& core = Storage();
    if (core.objectReady) {
        return ObjectFenceIntact(core);
    }
    if (entries.consoleCtor == nullptr || entries.consoleInit == nullptr) {
        State().lastStatus = static_cast<std::uint32_t>(ExecStatus::kEntriesMissing);
        return false;
    }
    std::memset(core.consoleObject, 0, sizeof(core.consoleObject));
    for (std::size_t index = kConsoleObjectSize - kObjectFenceBytes; index < kConsoleObjectSize;
         ++index) {
        core.consoleObject[index] = kObjectFenceValue;
    }
    entries.consoleCtor(core.consoleObject);
    entries.consoleInit(core.consoleObject);
    if (!ObjectFenceIntact(core)) {
        // 越界写 ⇒ **立刻停用**：不再调引擎（宁可没有控制台，也不能踩坏相邻静态变量）。
        State().fenceBroken = 1;
        State().lastStatus = static_cast<std::uint32_t>(ExecStatus::kFenceBroken);
        return false;
    }
    core.objectReady = true;
    State().objectCreated = 1;
    return true;
}

// ============================================================================
// 执行一条命令
// ============================================================================

struct ExecutionOutcome {
    ExecStatus status{ExecStatus::kEntriesMissing};
    std::size_t produced{0};     // 本次新增的输出字节数
    std::size_t totalOutput{0};  // 引擎侧累计输出长度
};

//: 执行一条 UTF-8 命令。**不抛、不崩**：任何前置条件不成立都只回一个结论码。
//:
//: ★ 玩家参数恒传 **nullptr**，但**先自己确认玩家列表非空**：引擎在第三参数为 null 时会
//:   读 `Game + 0x25C50` 的 `vector<Entity_Player*>` 第一个元素（`ldp x8,x9,[x19]` → `cbnz w9`
//:   → `ldr x26,[x8]`）**且不判空** ⇒ 列表为空时那是读空指针。我们宁可"这一帧不执行"，
//:   也不把这种输入交给引擎（结论码 `kNoPlayer`）。
[[nodiscard]] inline ExecutionOutcome ExecuteCommand(const EngineEntries& entries,
                                                    std::uintptr_t base, const char* command,
                                                    std::size_t length) noexcept {
    ExecutionOutcome outcome{};
    Core& core = Storage();
    outcome.status = ExecStatus::kOk;

    if (command == nullptr || length == 0) {
        outcome.status = ExecStatus::kEmptyCommand;
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }
    // 总开关关着 ⇒ **一律拒绝**（连模组调 `Isaac.ExecuteCommand` 也拒）。放在"空命令"之后：
    // 空串不是一次"想执行"的尝试，不该被计成拒绝次数。**不调引擎**（这才是 PC 的开关语义）。
    if (!core.switchEnabled) {
        ++State().switchRefusals;
        outcome.status = ExecStatus::kDisabledBySwitch;
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }
    if (length > kCommandLengthLimit) {
        outcome.status = ExecStatus::kTooLong;
        State().lastCommandLength = static_cast<std::uint32_t>(length);
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }
    if (State().fenceBroken != 0 ||
        !EnsureConsoleObject(entries)) {
        outcome.status = ExecStatus::kFenceBroken;
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }
    if (entries.runCommand == nullptr) {
        outcome.status = ExecStatus::kEntriesMissing;
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }
    // 玩家可用（引擎自己要读 `players[0]`，我们替它先确认）。
    if (!HasUsableFirstPlayer(ResolveGame(base))) {
        outcome.status = ExecStatus::kNoPlayer;
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }
    if (State().outputBytes >= kOutputByteLimit) {
        outcome.status = ExecStatus::kOutputFenced;
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }
    ++State().layoutChecks;
    State().layoutOk = StringLayoutSelfCheck() ? 1U : 0U;
    if (State().layoutOk == 0) {
        // 自检不过说明我们给自己的缓冲尺寸/读法有问题 ⇒ 不把命令交出去。
        outcome.status = ExecStatus::kEntriesMissing;
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }

    if (!core.commandReady) {
        std::memset(core.commandString, 0, sizeof(core.commandString));
        core.commandReady = true;
    }
    if (!BuildCommandString(command, length, core.commandString, core.commandBuffer,
                            sizeof(core.commandBuffer))) {
        outcome.status = ExecStatus::kTooLong;
        State().lastStatus = static_cast<std::uint32_t>(outcome.status);
        return outcome;
    }
    if (!core.outputReady) {
        std::memset(core.outputString, 0, sizeof(core.outputString));  // 老布局里的"空短串"
        core.outputReady = true;
    }

    const std::size_t before = EngineStringSize(core.outputString);
    entries.runCommand(core.consoleObject, core.commandString, core.outputString, nullptr);
    const std::size_t after = EngineStringSize(core.outputString);

    const bool isLong = EngineStringIsLong(core.outputString);
    core.outputIsLong = isLong;
    State().outputIsLong = isLong ? 1U : 0U;
    core.lastOutputLength = 0;
    if (after > before) {
        const char* data = EngineStringData(core.outputString);
        const std::size_t available = after - before;
        // 数据指针必须**先判可读再解引用**（长串是引擎堆上的地址）。
        if (data != nullptr &&
            engine_memory::EngineMemoryReadable(engine_memory::AddressOf(data), available)) {
            core.log.Append(data + before, available);
            const std::size_t copied =
                available < sizeof(core.lastOutput) - 1 ? available : sizeof(core.lastOutput) - 1;
            std::memcpy(core.lastOutput, data + before, copied);  // 给 `Isaac.ExecuteCommand` 当返回值
            core.lastOutput[copied] = '\0';
            core.lastOutputLength = static_cast<std::uint32_t>(copied);
            outcome.produced = available;
        }
    }
    outcome.totalOutput = after;
    State().commandsRun += 1;
    State().lastCommandLength = static_cast<std::uint32_t>(length);
    State().outputBytes = static_cast<std::uint32_t>(after);
    State().lastOutputBytes = static_cast<std::uint32_t>(outcome.produced);
    State().lastStatus = static_cast<std::uint32_t>(outcome.status);
    if (!ObjectFenceIntact(core)) {
        State().fenceBroken = 1;
    }
    return outcome;
}

//: 最近一次执行的**新增输出**（给 `Isaac.ExecuteCommand` 当返回值；空返回 false）。
[[nodiscard]] inline bool TakeLastOutput(const char** text, std::uint32_t* length) noexcept {
    const Core& core = Storage();
    if (core.lastOutputLength == 0 || text == nullptr || length == nullptr) {
        return false;
    }
    *text = core.lastOutput;
    *length = core.lastOutputLength;
    return true;
}

// ============================================================================
// 系统软键盘
// ============================================================================

//: 软键盘回调：`void(wchar_t const*, void*)`（`wchar_t` = 4 字节，见 `console_text.hpp`）。
//: ★ 这里**只搬数据、不调引擎**：命令留给下一帧的会话点执行 —— 回调是引擎在它自己的
//:   applet 处理里进来的，那个位置上跑一整条命令没有依据。
inline void KeyboardFinishedCallback(const std::uint32_t* text, void* /*userData*/) noexcept {
    Core& core = Storage();
    core.pendingLength = 0;
    core.pendingReady = false;
    const std::size_t written =
        Utf32ToUtf8(text, kVirtualKeyboardTextCapacity, core.pendingCommand,
                    sizeof(core.pendingCommand));
    // 只有非空输入才算"交回了一条命令"（取消键盘时引擎会给空串）。
    if (written > 0) {
        core.pendingLength = static_cast<std::uint32_t>(written);
        core.pendingReady = true;
    }
    State().keyboardResults += 1;
}

//: 请求弹出系统软键盘。`this` 用引擎自己的 `KAGE::System::g_Manager` ⇒ 不必自己开 applet 会话。
[[nodiscard]] inline bool RequestKeyboard(const EngineEntries& entries,
                                         std::uintptr_t kageManager) noexcept {
    if (entries.openKeyboard == nullptr || entries.paramsCtor == nullptr || kageManager == 0) {
        return false;
    }
    Core& core = Storage();
    std::memset(&core.keyboardParams, 0, sizeof(core.keyboardParams));
    entries.paramsCtor(&core.keyboardParams);
    std::memset(core.keyboardText, 0, sizeof(core.keyboardText));
    core.keyboardParams.text = core.keyboardText;
    core.keyboardParams.limit = static_cast<std::uint32_t>(kVirtualKeyboardTextCapacity);
    core.keyboardParams.textChanged = nullptr;
    core.keyboardParams.finished = &KeyboardFinishedCallback;
    core.keyboardParams.userData = nullptr;
    core.pendingReady = false;
    core.pendingLength = 0;
    State().keyboardRequests += 1;
    entries.openKeyboard(kageManager, &core.keyboardParams, 0xFFFFFFFFU);
    return true;
}

//: 取走软键盘交回的命令（一次性）。返回 false = 没有待执行的命令。
[[nodiscard]] inline bool TakePendingCommand(const char** command, std::uint32_t* length) noexcept {
    Core& core = Storage();
    if (!core.pendingReady || command == nullptr || length == nullptr) {
        return false;
    }
    *command = core.pendingCommand;
    *length = core.pendingLength;
    core.pendingReady = false;
    return true;
}

}  // namespace isaac::runtime::console