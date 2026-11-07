#pragma once

#include <cstddef>
#include <cstdint>

extern "C" {
#include <lua.h>
}

// Shared state and native bindings for the Lua API translation units.
// lua_runtime.cpp owns the Lua state, callback registry and metatable setup;
// API handlers access that state through the declarations in this header.
// Forward declarations keep host fixtures independent of registry definitions.
namespace isaac::runtime {
class CallbackRegistry;
struct ModHandle;
} // namespace isaac::runtime

namespace LuaRuntime {

// Called once at the top-level native Manager iteration. Does no Lua work.
void BeginGcFrame(std::uint64_t serial) noexcept;

// 仅在原生控制台同步命令的作用域内捕获，普通Lua print保持原stdout路径。
[[nodiscard]] bool ConsoleCommandOutputActive() noexcept;
[[nodiscard]] bool ConsoleConfigMenuVisible() noexcept;
[[nodiscard]] bool WriteActiveConsoleOutput(const char* text,std::size_t length) noexcept;


// --- Mod userdata ---------------------------------------------------------

inline constexpr char kModMetatable[] = "IsaacRuntime.Mod";

struct ModHandle {
    std::uint64_t persistenceNamespace;
    // 这个 Mod 的 **owner 句柄**，按 `(index, generation)` 打包成一个 32 位量
    // （低 16 位 index、高 16 位 generation）。回调登记用它做归属（多模组加载，2026-09-16）。
    //
    // 为什么不直接存 `isaac::runtime::ModHandle`：本头文件对它的依赖**刻意**保持在前向声明
    // （见上面的注释：宿主测试不该被迫编译回调登记表）。打包成 `std::uint32_t` 既维持了那条
    // 约束，又让"这个 Mod 对象属于哪一家"随身携带、不必再查全局表。
    std::uint32_t ownerPacked;
};

// Which persistence operation the current managed callback is running. The
// numeric values are a wire format for the trace/journal, so keep them stable.
enum class CallbackOperation : std::uint8_t {
    None = 0,
    SaveData,
    LoadData,
    HasData,
    RemoveData,
};

// Reports the current operation to the Runtime diagnostics. Defined in
// `lua_runtime.cpp`, which owns the diagnostic state.
void RecordCallbackOperation(CallbackOperation operation) noexcept;

// --- Callback registration census ------------------------------------------
//
// PC Mods register many `ModCallbacks` kinds during load; the Runtime only has
// dispatch sites for a few of them (see `HasDispatchSite` in `mod_api.cpp`).
// Registering the rest is allowed on purpose, so this census is how a hardware
// run can tell "registered but never fires" apart from "never registered".
// Defined in `interfaces/lua/mod_api.cpp`（唯一调用方，且一定被打包构建编译）。
void RecordCallbackRegistration(std::uint32_t callbackId, bool hasDispatchSite) noexcept;

// 回调里出过 Lua 错误（只读，不消费；消费入口仍是 `TakeCallbackError`）。诊断要能在
// 不改变既有“取走即清零”语义的前提下报告这个状态。
[[nodiscard]] bool CallbackErrorPending() noexcept;

// 最近一次 Lua 错误（或 Mod 加载失败）的信息：返回前 8 字节（不足补零），`length`
// 收到完整长度。真机上文件写入不可靠，所以错误信息用这种"装进诊断字"的方式留证。
[[nodiscard]] std::uint64_t LastLuaErrorHead(std::uint32_t* length) noexcept;
// `require` 失败的快照：第一次失败与最后一次失败的代码与模块名头 8 字节，以及失败总次数。
// 为什么要它：Mod 普遍用 `pcall(require, ...)` 并静默容忍失败（EID 就是这样），于是真机上
// 只能看到"后面某处索引到了 nil"，看不到**是哪一个 require 挂了、挂在哪一类**。
struct RequireFailureView {
    std::uint32_t firstCode;
    std::uint64_t firstNameHead;
    std::uint32_t lastCode;
    std::uint64_t lastNameHead;
    std::uint32_t total;
};
void RequireFailureSnapshot(RequireFailureView* view) noexcept;
// 模块假堆的已用字节数（`sbrk(0) - __fake_heap`）。整个模块的 malloc 都在这块 .bss 数组里，
// 所以它同时是"Lua + 其它一切"的峰值用量，用来判断 `exl::setting::HeapSize` 够不够。
[[nodiscard]] std::size_t HeapUsedBytes() noexcept;
// 整段错误文本（最多拷 `capacity` 字节，返回拷贝长度）。诊断用：8 字节的头往往只够认出
// "是哪一份脚本"（Lua 5.3.3 的 `luaO_chunkid` 会把长路径截成 "...+末 57 字符"），
// 真正要定位问题需要的是**行号 + 消息**，那在后面。
[[nodiscard]] std::size_t CopyLastLuaErrorText(char* output, std::size_t capacity) noexcept;
// 记录一次失败信息（`InitializeScript` 与回调派发的 Lua 错误路径调用）。
void RecordLuaErrorText(const char* text, std::size_t length) noexcept;

// Bit `id` is set when that `ModCallbacks` value was registered at least once.
// Low covers ids 0..63, high covers 64..127 (the PC table ends at 73).
[[nodiscard]] std::uint64_t RegisteredCallbackKindMaskLow() noexcept;
[[nodiscard]] std::uint64_t RegisteredCallbackKindMaskHigh() noexcept;
// Registrations whose kind has a dispatch site, and those that never fire.
[[nodiscard]] std::uint32_t DispatchableCallbackRegistrationCount() noexcept;
[[nodiscard]] std::uint32_t UnhookedCallbackRegistrationCount() noexcept;

// The Stage13 manifest/require diagnostic registers its POST_UPDATE phase under
// a Lua callback value of its own (the normal MC_POST_UPDATE is 1), so the
// mapping in the `Mod` family needs both the value and whether that diagnostic
// is running.
inline constexpr int kStage13CallbackValue = 1;

// True while the Runtime runs the Stage13 diagnostic. Defined in
// `lua_runtime.cpp`, which owns the Stage13 context.
[[nodiscard]] bool IsStage13CallbackMode() noexcept;

// --- Managed callback scope ----------------------------------------------

// True while the Runtime is invoking a Mod callback, i.e. while the game
// thread is in a state where native objects may be read. API families reject
// calls outside this scope instead of touching game memory from an unsafe
// point.
[[nodiscard]] bool InManagedCallbackScope() noexcept;

// --- Game binding slots ---------------------------------------------------

// Native addresses resolved by the Hook installation. Zero means "not
// available"; the handlers turn that into a Lua error instead of calling a
// null pointer.
[[nodiscard]] std::uintptr_t GameOwnerSlot() noexcept;
[[nodiscard]] std::uintptr_t GameIsPausedThunk() noexcept;
// 游戏本体 NRO（`Repentance.nro`）模块的加载基址。上面的槽/跳板地址都是模块内偏移，只有加上
// 基址才是绝对地址；`Isaac.GetPlayer` 的整条链路（全局槽 → Game* → players 向量 → Entity_Player）
// 与 `EntityPlayer` 的 vptr 判据都建立在基址上。
//
// 与 `GameOwnerSlot` 同一种模式：由 Hook 安装阶段在已经拿到 `TargetModule::base` 的地方发布，
// 0 表示"尚未发布"——handler 据此返回 nil（而不是去解引用一个 0 基址）。
[[nodiscard]] std::uintptr_t EngineModuleBase() noexcept;
// 发布基址（Hook 安装阶段调用一次，与 `SetGameBindings` 同一时机）。声明放在这里而不是
// `lua_runtime.hpp`：消费方是 `interfaces/lua` 的家族 TU，它们只依赖本头。
void SetEngineModuleBase(std::uintptr_t base) noexcept;
[[nodiscard]] std::uintptr_t GameIsGreedModeThunk() noexcept;
[[nodiscard]] std::uintptr_t LevelIsAscentThunk() noexcept;
// `Level` 家族另外两个方法入口。0 表示"没通过安装期守卫 ⇒ 不可用"。
[[nodiscard]] std::uintptr_t LevelGetAbsoluteStageThunk() noexcept;
// 2026-09-16：`Room:GetFrameCount()` 要调的引擎函数（`Room::GetFrameCount @ 0x470B0C`）。
// 0 表示"没通过安装期守卫 ⇒ 不可用"；handler 那时报"绑定不可用"，**不返回编造的帧数**
// （编个 0 会让 EID 以为"刚进房间"，把合成结果显示整段跳过）。
[[nodiscard]] std::uintptr_t RoomGetFrameCountThunk() noexcept;
// 2026-09-21：`GridEntity::GetPosition() const @ 0x37E498`（PC 的 `GridEntity.Position`）。
// 0 表示"没通过安装期守卫 ⇒ 不可用"；handler 那时报"绑定不可用"并让字段读取失败，
// **不编造坐标**（EID 靠它算"离玩家最近的刺"，编一个坐标会让它挑错实体）。
[[nodiscard]] std::uintptr_t GridEntityGetPositionThunk() noexcept;
#if !defined(__SWITCH__)
// 宿主注入钩子（与 `GetRenderPositionHostFunction` 同一形态，类型别名与 `lua_runtime.hpp` 逐字一致）。
using RoomFrameCountHostFunction = std::int32_t (*)(const void* room);
[[nodiscard]] RoomFrameCountHostFunction GetRoomGetFrameCountHostFunction() noexcept;
// 2026-09-21：`GridEntity.Position`（`GridEntity::GetPosition() const @ 0x37E498`）的宿主替身。
using GridEntityPositionHostFunction = void (*)(const void* entity, float* x, float* y);
[[nodiscard]] GridEntityPositionHostFunction GetGridEntityGetPositionHostFunction() noexcept;
#endif
// `Room:WorldToScreenPosition()` 要调的引擎函数（PLT 桩地址，
// 由 hook_manager 校验 16 字节入口后发布）。
[[nodiscard]] std::uintptr_t GetRenderPositionThunk() noexcept;
void SetGetRenderPositionBinding(std::uintptr_t method);
#if !defined(__SWITCH__)
// 宿主注入钩子（设备构建里不存在）：设备侧这条走"校验 16 字节入口 + 调用引擎函数"，
// 宿主上没有引擎映像，所以用注入的实现替代。类型别名与 `lua_runtime.hpp` 逐字一致。
using RenderPositionHostFunction = void (*)(const float* input, float* output, bool useCamera);
[[nodiscard]] RenderPositionHostFunction GetRenderPositionHostFunction() noexcept;
#endif
[[nodiscard]] std::uintptr_t LevelIsNextStageAvailableThunk() noexcept;
[[nodiscard]] std::uintptr_t ItemPoolGetCollectibleThunk() noexcept;
[[nodiscard]] std::uintptr_t MusicGetCurrentMusicIdThunk() noexcept;
[[nodiscard]] std::uintptr_t MusicPauseThunk() noexcept;
[[nodiscard]] std::uintptr_t MusicResumeThunk() noexcept;
// `MusicManager:UpdateVolume()` 的单方法绑定取址助手（形态与 `Music*Thunk` 相同）。
[[nodiscard]] std::uintptr_t MusicUpdateVolumeThunk() noexcept;
// `MusicManager:Play(ID, Volume)` 的取址助手（同上）。
[[nodiscard]] std::uintptr_t MusicPlayThunk() noexcept;
[[nodiscard]] std::uintptr_t RngSetSeedThunk() noexcept;
[[nodiscard]] std::uintptr_t RngNextThunk() noexcept;
// `RNG:RandomInt(Max)` / `RNG:RandomFloat()` 的取址助手
// （形态与上面两条相同：取到 0 = 没发布 ⇒ handler 报"绑定不可用"，不编一个随机数）。
[[nodiscard]] std::uintptr_t RngRandomUintThunk() noexcept;
[[nodiscard]] std::uintptr_t RngRandomThunk() noexcept;
// Input bindings (controller actions). Zero means "not available", which the handlers turn
// into a Lua error instead of answering a fabricated value.
[[nodiscard]] std::uintptr_t InputIsActionPressedThunk() noexcept;
// 已校验发布的引擎绑定；内部批量读取必须在RawEngineInputQueryScope内调用。
// 入口可能已是本运行时中继，消费者不能再次按原序言逐字拒绝。
[[nodiscard]] std::uintptr_t InputIsActionPressedBinding() noexcept;

// Lua 状态自己占了多少内存（字节）。
//
// 为什么加它：真机上本模块堆"已用 122.8 MB / 空闲 5.2 MB"（415 读数）把 `whatsmydps`
// 每帧要的 128 KiB 挡在门外，而"这 122 MB 是谁吃的"当时只能靠猜。这一格把
// Lua 侧（模组的表/字符串 —— EID 的语言包光源码就有 8 MB）与
// 其它（`malloc` 出来的：Font 块、贴图转码缓冲、挂载表、名字层…）分开：
// 其它 = 状态面 `heapUsedBytes`（[59]）− 本格。
// 口径 = `lua_gc` 的 `LUA_GCCOUNT` + `LUA_GCCOUNTB`；拿不到状态时返回 0。
// 只读、只记录：没有任何行为跟着它变。
// 声明放这个头（而不是 `lua_runtime.hpp`）的原因：消费方
// `mod_menu_native.cpp` 包含的是这一份；放错头会得到
// `'LuaStateMemoryBytes' is not a member of 'LuaRuntime'`（2026-10-08 本批实撞）。
[[nodiscard]] std::uint32_t LuaStateMemoryBytes() noexcept;
// 把"Lua 的 GC 看不见的那笔内存"补给 GC 看。
//
// 起因：`whatsmydps` 在 `MC_POST_RENDER` 里每帧 `Font()` 一个对象、用完即弃
// （真机实测 `MC_POST_RENDER` 派发次数 : Font 分配次数 = 1 : 1）。
// 后果：Font 存活块数一路锯到 507 块（× 128 KiB = 63 MB），
// 而它每约 250 帧才被 GC 收一次。
//
// 为什么 GC 不收它 —— 415 批留下的那句前提是错的：
// 那 128 KiB 的块走的是 `lua_getallocf` 拿到的裸 `frealloc`
// （`lapi.c:1169` 就是 `return G(L)->frealloc;`），而 Lua 只在
// `luaM_realloc_` 里更新 `g->GCdebt`（`lmem.c:97`）。
// ⇒ 直接调 `frealloc` 绕过了这笔账 ⇒ 这块内存不进 Lua 的用量统计
// ⇒ GC 的触发条件（`GCdebt` 对 `GCthreshold`）永远看不到它
// ⇒ 只能等别的分配顺手把 GC 触发起来，而那时已经攒了 500+ 块。
// （415 的原话是"它计入 Lua 的 GC 账 ⇒ GC 按需回收" —— 实测不成立，本批订正。）
//
// 修法：这笔内存我们自己看得见（`g_FontStorageLive`）⇒
// 由我们把它补报给 GC：存活块数超过软上限就催一次全量 GC。
//
// `frames` = 调用方的单调帧号（用来限速，不要传 0）；
// `liveFontBlocks` = `isaac::runtime::FontStorageLiveBlocks()` 的值。
// 为什么要调用方把块数传进来、而不是这里自己去读那个 `std::atomic`：
// 本文件在 `namespace LuaRuntime` 里写 `namespace isaac::runtime {…}` 会造出
// `LuaRuntime::isaac::runtime`，而这个名字会抢走本 TU 后面所有 `isaac::runtime::X`
// 的查找（2026-10-10 本批实撞：`lua_runtime.cpp` 一次性报了 15 个
// `'CallbackRegistry' in namespace 'LuaRuntime::isaac::runtime' does not name a type`）。
// ⇒ 不要在 `LuaRuntime` 里再开 `isaac`；要读那边的量就从参数进来。
// 返回 1 = 这一拍真的走了 GC 步进；0 = 没到阈值 / 没到起拍间隔 / 状态没建 /
// 上一轮没收掉东西（见实现里那条"自停"判据）。
// 调用点必须在不在 Lua 执行中的地方（本批放在 `ModMenuNativeUpdate()` 的每帧路径）——
// GC 会跑终结器，在 Lua 里乱插一脚是不安全的。
//
// 2026-10-10 当晚：从"全量 GC"改成"按时间预算切片的增量步进"。
// 425 用的是 `LUA_GCCOLLECT`（全量、stop-the-world），一秒左右一次
// ⇒ 用户当晚就报「掉一下回 60，然后再掉一下回 60，一直这样」——那是我上一批造的。
// 教训：425 只权衡了"一次收干净"，没权衡"单次最长停顿"；
// 改性能相关的选择，"单次最长耗时"必须是一等判据。
// 现在一拍之内反复走 `LUA_GCSTEP, 0`（单步、有界），
// 直到 ①一轮走完 或 ②花掉 1 ms 预算 或 ③撞步数上限 ⇒ 单次停顿有界、肉眼不可见；
// 同样的总工作量摊到 ~30 拍/秒上（≈3% CPU）。
// `LUA_GCSTEP` 的 `data` 必须传 0：`data != 0` 时它按"债"一路还完（≈全量，见
// `lapi.c:1066-1078` + `luaC_step` 的 `do…while (debt > -GCSTEPSIZE)`）——一样不可控。
[[nodiscard]] std::uint32_t NudgeLuaGcIfFontBlocksHigh(std::uint32_t frames,
                                                       std::uint32_t liveFontBlocks) noexcept;
[[nodiscard]] std::uintptr_t InputIsActionTriggeredThunk() noexcept;
[[nodiscard]] std::uintptr_t InputGetActionValueThunk() noexcept;
// 按键号那三条查询的入口（`KAGE::Input::ManagerBase`）。
// 与上面三条动作查询不是同一个东西（入口在 KAGE 的输入管理器上，不在
// `IsaacRepentance::Manager` 的跳板上）。取到 0 = 没发布（守卫不符）⇒ handler 报"绑定不可用"，
// 不编一个 false/0.0 把"偏移写串"伪装成"没按下"。
// 只有两条：`IsButtonTriggered` 不登记（引擎那条的语义不是 PC 的上升沿，我们不用它，
// 见 `runtime_constants.hpp` 里那段说明）。
[[nodiscard]] std::uintptr_t InputIsButtonPressedThunk() noexcept;
[[nodiscard]] std::uintptr_t InputGetButtonValueThunk() noexcept;
// --- 引擎入口的"声明类型"：唯一一份（2026-09-17）-----------------------------
//
// 这一段只干一件事：把这些游戏入口**声明成什么参数**写在一个地方。
//
// 为什么要有它：这些入口是"我们手写签名、直接跳进游戏模块"的地方，签名写错就是崩游戏。
// 而在这之前，同一份签名在仓库里有**两份互不相干的副本**——绑定记录（`LuaFontBindings` /
// `LuaSpriteBindings`）的字段类型是 `uintptr_t`（谁都看不出它期望什么参数），各个调用点
// 又各自写一份 `using PlayFn = void (*)(void*, const char*, bool);`。两份一旦漂移，
// 没有任何东西会发现，而漂移的后果是"按错的参数表跳进引擎"。
// 现在：绑定记录字段用这里的类型、取址助手（`XxxThunk`）返回这里的类型、调用点拿到指针
// 直接调用（`reinterpret_cast` 随之消失，参数由编译器核对）。偏移体检工具也从这里读出
// "我们声明的参数表"，与引擎符号反解出来的签名逐条比。
//
// 命名：`<族><成员>Fn`（例如 `SpritePlayFn`）。参数表第一项是**显式 this**，所以与引擎
// 符号（成员函数，`this` 不占参数位）相比会多一个参数，体检工具认得这条规则。
// 返回类型只写"我们实际怎么用它"：体检工具比的是参数个数与有没有浮点。
using FontCtorFn = void (*)(void*);
using FontDestructorFn = void (*)(void*);
using FontLoadFn = bool (*)(void*, const char*, const char*);
using FontUnloadFn = void (*)(void*);
using FontIsLoadedFn = bool (*)(const void*);
using FontGetStringWidthFn = int (*)(const void*, const char*);
using FontGetStringWidthUTF8Fn = int (*)(const void*, const char*);
using FontGetLineHeightFn = std::uint16_t (*)(const void*);
using FontGetBaselineHeightFn = std::uint16_t (*)(const void*);
using FontGetCharacterWidthFn = int (*)(const void*, char);
using FontSetMissingCharacterFn = void (*)(void*, std::uint16_t);
using FontDrawStringFn = void (*)(void*, const char*, float, float, const void*, int, bool);
using FontDrawStringScaledFn = void (*)(void*, const char*, float, float, float, float,
                                        const void*, int, bool);
using FontDrawStringUTF8Fn = void (*)(void*, const char*, float, float, const void*, int, bool);
using FontDrawStringScaledUTF8Fn = void (*)(void*, const char*, float, float, float, float,
                                            const void*, int, bool);

using SpriteCtorFn = void (*)(void*);
using SpriteDestructorFn = void (*)(void*);
using SpritePlayFn = void (*)(void*, const char*, bool);
using SpriteSetAnimationFn = bool (*)(void*, const char*, bool);
using SpriteSetFrameNamedFn = void (*)(void*, const char*, int);
using SpriteSetFrameFn = void (*)(void*, int);
using SpriteGetFrameFn = int (*)(const void*);
using SpriteSetLayerFrameFn = void (*)(void*, int, int);
using SpriteGetLayerFrameFn = int (*)(void*, int);
// AAPCS64: 两个平凡 Vector2 按 HFA 传 s0..s3，阈值 s4，层号 w1。
// Color 的非平凡析构强制 x8 间接返回；空析构优化后不产生运行成本。
struct SpriteTexelVector { float x; float y; };
struct SpriteTexelColor {
    float red; float green; float blue; float alpha;
    ~SpriteTexelColor() noexcept {}
};
static_assert(sizeof(SpriteTexelVector) == 8);
static_assert(sizeof(SpriteTexelColor) == 16);
using SpriteGetTexelFn = SpriteTexelColor (*)(void*, SpriteTexelVector, SpriteTexelVector, float, int);
using SpriteUpdateFn = void (*)(void*);
using SpriteIsPlayingFn = bool (*)(const void*, const char*);
using SpriteIsFinishedFn = bool (*)(const void*, const char*);
// overlay 三条。`PlayOverlay`/`SetOverlayFrame` 都选 `char const*` 重载
// （避开 libc++ `std::string` 桥）；`SetLastFrame()` 无参。
using SpritePlayOverlayFn = void (*)(void*, const char*, bool);
using SpriteSetLastFrameFn = void (*)(void*);
using SpriteSetOverlayFrameFn = void (*)(void*, const char*, int);
// `ANM2::Stop()`（0 参）。
using SpriteStopFn = void (*)(void*);
// 四条「按名字查询」—— 引擎侧统一 `bool ANM2::Xxx(std::string const&) const`。
// 第二个参数是 libc++ 的 24 字节 `std::string` 对象（`sprite_api.cpp` 里
// `BuildNativeString` 交出来的那一块），所以按 `const void*` 传 —— 与 `SpriteLoadFn` /
// `SpriteReplaceSpritesheetFn` 同一条口径（我们对布局的假设只有"全零 = 空短串"这一条，
// 内容由游戏自己的 `assign` 桩填，不去猜 libc++ 的字段）。
using SpriteIsOverlayPlayingFn = bool (*)(const void*, const void*);
using SpriteIsOverlayFinishedFn = bool (*)(const void*, const void*);
using SpriteIsEventTriggeredFn = bool (*)(const void*, const void*);
using SpriteWasEventTriggeredFn = bool (*)(const void*, const void*);
// `ANM2::Reset()`（`void Reset(ANM2*)`）—— 中文版 MCM 的 `filepathhelper.lua`
// 在探测 anm2 路径之后会调它（`anm2Tester:Reset()`，不在 pcall 里）。
using SpriteResetFn = void (*)(void*);
using SpriteRenderFn = void (*)(void*, const void*, const void*, const void*);
using SpriteRenderLayerFn = void (*)(void*, int, const void*, const void*, const void*);
using SpritePlayRandomFn = void (*)(void*, unsigned int);
using SpriteLoadFn = void (*)(void*, const void*, bool);
using SpriteLoadGraphicsFn = void (*)(void*);
using SpriteReplaceSpritesheetFn = void (*)(void*, int, const void*);
using LibcxxStringAssignFn = void* (*)(void*, const char*);
using GameOperatorDeleteFn = void (*)(void*);

// Font bindings (`KAGE::Graphics::Font`). 空指针表示"不可用"，handler 于是报 Lua 错误，
// 而不是调用未校验的地址。Font 对象本身不属于游戏：存储由本族的实现自己管，只有这些
// 入口点来自游戏。
[[nodiscard]] FontCtorFn FontCtorThunk() noexcept;
[[nodiscard]] FontDestructorFn FontDestructorThunk() noexcept;
[[nodiscard]] FontLoadFn FontLoadThunk() noexcept;
[[nodiscard]] FontUnloadFn FontUnloadThunk() noexcept;
[[nodiscard]] FontIsLoadedFn FontIsLoadedThunk() noexcept;
[[nodiscard]] FontGetStringWidthFn FontGetStringWidthThunk() noexcept;
[[nodiscard]] FontGetStringWidthUTF8Fn FontGetStringWidthUTF8Thunk() noexcept;
[[nodiscard]] FontGetLineHeightFn FontGetLineHeightThunk() noexcept;
[[nodiscard]] FontGetBaselineHeightFn FontGetBaselineHeightThunk() noexcept;
[[nodiscard]] FontGetCharacterWidthFn FontGetCharacterWidthThunk() noexcept;
[[nodiscard]] FontSetMissingCharacterFn FontSetMissingCharacterThunk() noexcept;
[[nodiscard]] FontDrawStringFn FontDrawStringThunk() noexcept;
[[nodiscard]] FontDrawStringScaledFn FontDrawStringScaledThunk() noexcept;
[[nodiscard]] FontDrawStringUTF8Fn FontDrawStringUTF8Thunk() noexcept;
[[nodiscard]] FontDrawStringScaledUTF8Fn FontDrawStringScaledUTF8Thunk() noexcept;

// Sprite 绑定（`IsaacRepentance::ANM2`）。空指针表示不可用，handler 会报错，而不是调用未校验的地址。
[[nodiscard]] SpriteCtorFn SpriteCtorThunk() noexcept;
[[nodiscard]] SpriteDestructorFn SpriteDestructorThunk() noexcept;
[[nodiscard]] SpritePlayFn SpritePlayThunk() noexcept;
[[nodiscard]] SpriteSetAnimationFn SpriteSetAnimationThunk() noexcept;
[[nodiscard]] SpriteSetFrameNamedFn SpriteSetFrameNamedThunk() noexcept;
[[nodiscard]] SpriteSetFrameFn SpriteSetFrameThunk() noexcept;
[[nodiscard]] SpriteGetFrameFn SpriteGetFrameThunk() noexcept;
[[nodiscard]] SpriteSetLayerFrameFn SpriteSetLayerFrameThunk() noexcept;
[[nodiscard]] SpriteGetLayerFrameFn SpriteGetLayerFrameThunk() noexcept;
[[nodiscard]] SpriteGetTexelFn SpriteGetTexelThunk() noexcept;
[[nodiscard]] SpriteUpdateFn SpriteUpdateThunk() noexcept;
[[nodiscard]] SpriteIsPlayingFn SpriteIsPlayingThunk() noexcept;
// overlay 三条的 thunk。
[[nodiscard]] SpritePlayOverlayFn SpritePlayOverlayThunk() noexcept;
[[nodiscard]] SpriteSetLastFrameFn SpriteSetLastFrameThunk() noexcept;
[[nodiscard]] SpriteSetOverlayFrameFn SpriteSetOverlayFrameThunk() noexcept;
// `Stop`。
[[nodiscard]] SpriteStopFn SpriteStopThunk() noexcept;
// 四条「按名字查询」的 thunk。
[[nodiscard]] SpriteIsOverlayPlayingFn SpriteIsOverlayPlayingThunk() noexcept;
[[nodiscard]] SpriteIsOverlayFinishedFn SpriteIsOverlayFinishedThunk() noexcept;
[[nodiscard]] SpriteIsEventTriggeredFn SpriteIsEventTriggeredThunk() noexcept;
[[nodiscard]] SpriteWasEventTriggeredFn SpriteWasEventTriggeredThunk() noexcept;
[[nodiscard]] SpriteIsFinishedFn SpriteIsFinishedThunk() noexcept;
[[nodiscard]] SpriteResetFn SpriteResetThunk() noexcept;
[[nodiscard]] SpriteRenderFn SpriteRenderThunk() noexcept;
[[nodiscard]] SpriteRenderLayerFn SpriteRenderLayerThunk() noexcept;
[[nodiscard]] SpritePlayRandomFn SpritePlayRandomThunk() noexcept;
[[nodiscard]] SpriteLoadFn SpriteLoadThunk() noexcept;
[[nodiscard]] SpriteLoadGraphicsFn SpriteLoadGraphicsThunk() noexcept;
[[nodiscard]] SpriteReplaceSpritesheetFn SpriteReplaceSpritesheetThunk() noexcept;
[[nodiscard]] LibcxxStringAssignFn LibcxxStringAssignThunk() noexcept;
// 游戏自己的 `operator delete(void*)`：释放游戏分配器给长路径分配的缓冲（见 `kGameOperatorDeleteOffset`）。
[[nodiscard]] GameOperatorDeleteFn GameOperatorDeleteThunk() noexcept;

// The ItemPool method guard still lives in `lua_runtime.cpp` next to the rest
// of the instruction checks; the family unit only needs the verdict.
[[nodiscard]] bool ValidateItemPoolGetCollectibleBinding(std::uintptr_t address) noexcept;


// --- Music and RNG call targets ------------------------------------------

// Resolving a Music call needs two things the family unit must not own yet:
// the callback's native Manager pointer and the expected instruction bytes of
// each method. Both live in `lua_runtime.cpp` (the Manager slot is written by
// the managed-callback dispatcher, the byte guards sit next to the other
// instruction checks), so the accessors return the verdict and, on success, the
// resolved Music object address. `false` means "native bindings are
// unavailable"; the handlers turn that into the same Lua error as before.
[[nodiscard]] bool ResolveMusicGetCurrentMusicId(std::uintptr_t method,
                                                 std::uintptr_t* music) noexcept;
[[nodiscard]] bool ResolveMusicPause(std::uintptr_t method, std::uintptr_t* music) noexcept;
[[nodiscard]] bool ResolveMusicResume(std::uintptr_t method, std::uintptr_t* music) noexcept;
// `MusicManager:UpdateVolume()` 的接收者解析（与上面三条同一个入口守卫机制）。
[[nodiscard]] bool ResolveMusicUpdateVolume(std::uintptr_t method,
                                            std::uintptr_t* music) noexcept;
// `MusicManager:Play(ID, Volume)` 的接收者解析（同上）。
[[nodiscard]] bool ResolveMusicPlay(std::uintptr_t method, std::uintptr_t* music) noexcept;

// `SFXManager:IsPlaying(ID)` 的接收者解析 ——
// **与上面 Music 那一族共用同一个 Manager**（"当前回调的 Manager"或"本帧 `Manager::Update` 的 self"），
// 只是子对象的偏移不同：`Manager + kManagerSoundEffectsOffset`（`0x364A8`，
// 反汇编证据见 `runtime_constants.hpp` 里那条常量）。`false` = "原生绑定不可用"，
// 处理器据此压与 PC 同类型的降级值（布尔 ⇒ `false`），**不报错**。
// 统一校验音效成员函数入口指纹与当前 Manager 内嵌接收者。
[[nodiscard]] bool ResolveSoundEffectsMethodForCall(std::uintptr_t method, const unsigned char* expected,
    std::size_t expectedLength, std::uintptr_t* soundEffects) noexcept;
[[nodiscard]] bool ResolveSoundEffectsForCall(std::uintptr_t method,
                                              std::uintptr_t* soundEffects) noexcept;

// `SFXManager:Play(...)` 的接收者解析 —— 与上一条同一个核心，
// 差别只有入口 16 字节指纹（`SoundEffects::Play` @ `0x4A2FD0` vs `IsPlaying` @ `0x4A38AC`）。
// 多一个出参 `failureCode`：0 = 成功；1 = 不在托管回调派发里 / 2 = Manager 或子对象读不到 /
// 3 = 方法地址或期望字节缺失 / 4 = 入口指纹不符（与 `g_MusicResolveFailure` 同一套语义）。
// 单独开出参而不写共享的 `g_MusicResolveFailure`：`IsPlaying` 与 `Play` 可能同帧都被调，
// 共用一格会让"最近一次失败"分不清是谁的（见 `music_api.cpp` 里 Play 的探针注释）。
// `false` = "原生绑定不可用"，Play 处理器据此安静地什么都不做（PC 的 `void`，不报错）。
[[nodiscard]] bool ResolveSoundEffectsPlayForCall(std::uintptr_t method,
                                                  std::uintptr_t* soundEffects,
                                                  std::uint32_t* failureCode) noexcept;

// `false` 上面的那四条为什么是 `false`。
//
// 以前它们只有一句 "native bindings are unavailable"，把三种完全不同的原因混在一起：
//   * 不在托管回调派发里（模组在文件作用域/非回调里调）；
//   * 拿不到 Manager（回调没带、本帧也没有）；
//   * 入口 16 字节指纹不符（**我们的偏移/期望字节写错了**，最值得怀疑的那一类）。
// 真机上只能靠猜 —— 2026-09-26 那次就为此白跑了一轮（真因是第一条的变体：`MC_POST_UPDATE`
// 的派发不带 Manager，而模组正是在 `MC_POST_UPDATE` 里调音乐）。现在把这句英文原因拼在
// 报错后面，**只影响报错文字**，判据一个字不变。
[[nodiscard]] const char* MusicResolveFailureReason() noexcept;

// `RNG:SetSeed` and `RNG:Next` only need the method guard verdict: the RNG
// object is the Lua userdata itself, not a native pointer.
[[nodiscard]] bool ValidateRngSetSeedBinding(std::uintptr_t address) noexcept;
[[nodiscard]] bool ValidateRngNextBinding(std::uintptr_t address) noexcept;
// `RNG::Random(uint)` / `RNG::Random()` 的入口指纹核对（16 字节，同上一族）。
[[nodiscard]] bool ValidateRngRandomUintBinding(std::uintptr_t address) noexcept;
[[nodiscard]] bool ValidateRngRandomBinding(std::uintptr_t address) noexcept;

// `KAGE::Input::ManagerBase` 上按按键号查询的三条入口。
// 这三条（连同同族的动作查询共四条）的头 32 字节完全相同 ⇒ 序言指纹只能证明"模块基址对"。
// 区分它们的是各自那条"取虚表槽"的指令（`entry+0xE0` 的 4 字节：本文件里 Pressed 与
// Triggered 各有自己的那 4 字节常量）⇒ 这两个校验器比对的是更严的判据（见实现处）。
[[nodiscard]] bool ValidateInputIsButtonPressedBinding(std::uintptr_t address) noexcept;
[[nodiscard]] bool ValidateInputGetButtonValueBinding(std::uintptr_t address) noexcept;

[[nodiscard]] isaac::runtime::CallbackRegistry& ManagedCallbackRegistry() noexcept;

// ---- `Level:GetStartingRoomIndex()` 的派生记账 ------------------------
//
// 模型：**本层第一次被看到的那个房间索引**就是"起始房间"（引擎里没有这个函数/字段的符号，
// 取证过程见 `level_start_room.hpp` 顶部与 `api_deviation.cpp` 的 0x03010011 那条）。
//
// * `NoteCurrentLocationForStartRoom()`：API 层在取值前调一次 —— 自己读一次"当前层 + 当前房间"
//   喂给记账，于是**不依赖**有没有模组登记帧事件族（那条路径有"没人听就整段跳过"的早退）。
// * `StartingRoomIndexForCurrentLevel()`：取当前层的起始房间索引；还没观察到任何一层时给
//   `LevelStartRoomTracker::kUnknownRoomIndex`（= -1，模组那边的比较会判成"不是起始房间"）。
void NoteCurrentLocationForStartRoom() noexcept;
[[nodiscard]] std::uint32_t StartingRoomIndexForCurrentLevel() noexcept;
[[nodiscard]] isaac::runtime::ModHandle RuntimeOwnerHandle() noexcept;

// 多模组（2026-09-16）：把 `ModHandle::ownerPacked` 还原成 domain 的 owner 句柄。
//
// 为什么要有它：`ModHandle` 的字段是打包过的（那个头不能依赖 domain 头），而
// `CallbackDescriptor::owner` 要的是 domain 类型。解包只在这一处做，调用方不必知道打包格式。
[[nodiscard]] isaac::runtime::ModHandle UnpackModOwner(std::uint32_t packed) noexcept;

// --- Lua 报错通道的加固（2026-09-12）-------------------------------------------------
//
// 背景：真机报告的"错误文本"一直不可信 —— `errorLength = 1` 而负载里却读出
// `"...ile name"` 之类的**残留**。原因是 `CaptureLuaErrorTop` 用 `lua_tolstring`
// 取值，而 **Lua 允许 `error(任何值)`**：错误值不是字符串时它什么都不记，长度与内容
// 就会不一致，报告侧读到上一条消息的残渣。
//
// 修法（两层）：
//   1. `RecordLuaErrorValue`：把"任意 Lua 值"转成可读文本再记录（字符串直接用；
//      数字/布尔/nil 用 `lua_tostring`/`lua_typename`；其余用 `luaL_tolstring`——
//      它接受**任意**值并保证产出字符串，且自己负责压栈/弹栈）。
//   2. 本头文件里把 `luaL_error` 改成"先记录整段消息、再真正抛错"的包装宏。
//      `luaL_error` 的消息就是最终文本（含 `file:line:` 前缀），所以这样记录下来的
//      就是**消息本体**，不再依赖 `lua_tostring` 的成功与否。
//
// 为什么宏写在头文件里：本项目有多个 TU 调用 `luaL_error`（约 34 处），逐个改容易漏。
// 宏只在**包含本头文件之后**生效，且用 `push_macro/pop_macro` 保证不泄漏。
// 已知不覆盖：直接调 `lua_error`（不走 `luaL_error`）的路径；本项目目前没有这种调用，
// 若以后出现，需要一并包装。
void RecordLuaErrorValue(lua_State* state) noexcept;
int ReportAndRecordLuaError(lua_State* state, const char* format, ...);

} // namespace LuaRuntime


// `luaL_error` 的包装：见上面 `ReportAndRecordLuaError` 的注释。
#pragma push_macro("luaL_error")
#undef luaL_error
#define luaL_error(state, ...) ::LuaRuntime::ReportAndRecordLuaError((state), __VA_ARGS__)
