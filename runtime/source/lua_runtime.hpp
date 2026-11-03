#pragma once
#include "raw_engine_input.hpp"
#include "domain/callback/use_item_result.hpp"

#include <cstddef>
#include <cstdint>
#include <array>

#include "common.hpp"
// 下面两个绑定记录的字段类型来自 `lua_runtime_state.hpp` 里那一份"引擎入口声明类型"
// （2026-09-17）：记录本身只是**搬运**——安装期把校验过的入口地址填进来，`Set*Bindings`
// 再逐个发布到原子槽；调用点用的是同一份类型，于是"声明的签名"与"调用的签名"不可能漂移。
#include "lua_runtime_state.hpp"
namespace isaac::runtime { struct ConsoleCommandView; }

#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
#include "game_file_reader.hpp"
#endif

namespace LuaRuntime {

enum class LuaInitResult : u32 {
    Success,
    StateCreateFailed,
    RuntimePreparationMemoryFailed,
    RuntimePreparationFailed,
    ScriptLoadFailed,
    ScriptRunFailed,
    MissingPostUpdateCallback,
};

LuaInitResult Initialize();
bool UnloadManifestMods() noexcept;
void DispatchExecuteCommand(const isaac::runtime::ConsoleCommandView&) noexcept;
LuaInitResult InitializeFromBuffer(const char* script, std::size_t length, const char* chunkName);
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
// 幂等建立共享Lua运行时，不额外注册菜单模组；函数名沿用历史接口。
LuaInitResult EnsureRuntimeWithMenu() noexcept;

LuaInitResult InitializeManifestMod(const char* entry, std::size_t entryLength,
                                    const char* chunkName, const char* modRoot,
                                    const GameFileReader::Bindings& bindings);
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
LuaInitResult InitializeStage13Mod(const char* entry, std::size_t entryLength,
                                  const char* chunkName, const char* modRoot,
                                  const GameFileReader::Bindings& bindings);
u32 RequireFailureDetail();
u64 RequireErrorTail();
#endif
#endif
u32 PreparationFailureDetail();
// Options与既有控制台共用开关；变化只挂待写，文件I/O仍由控制台帧点处理。
[[nodiscard]] bool DebugConsoleEnabled() noexcept;
void SetDebugConsoleEnabled(bool enabled) noexcept;
void SetGameBindings(uintptr_t ownerSlot, uintptr_t isPausedThunk);
void SetGameIsGreedModeBinding(uintptr_t method);
void SetLevelIsAscentBinding(uintptr_t method);
// 批次 8（2026-09-15）：`Level` 家族另外两个成员方法的入口地址。
//   一次发布，两个都是"可选能力"——任一个为 0 时对应 handler 报"绑定不可用"，
//   绝不返回编造的值（`Level:GetAbsoluteStage()` 编个 0 会让 Mod 以为"在第一层"）。
void SetLevelGetAbsoluteStageBinding(uintptr_t method);
// 2026-09-16：`Room:GetFrameCount()` 的引擎函数入口（`Room::GetFrameCount @ 0x470B0C`，
// 安装期用 16 字节守卫校验）。与 `SetLevelGetAbsoluteStageBinding` 同一形态：
// 0 = 不可用，handler 会明说"绑定不可用"，不编造帧数。
void SetRoomGetFrameCountBinding(uintptr_t method);
// 2026-09-21：`GridEntity::GetPosition() const @ 0x37E498`（PC 的 `GridEntity.Position`，
// `const Vector`）。与上一条同一形态：0 = 不可用，handler 报"绑定不可用"，**不编造坐标**。
// （读入口的 thunk 声明在 `lua_runtime_state.hpp`，与其它 thunk 一致：消费方是 `interfaces/lua` 的 TU。）
void SetGridEntityGetPositionBinding(uintptr_t method);
#if !defined(__SWITCH__)
// 宿主注入钩子（设备构建里不存在）：设备侧这条走"校验 16 字节入口 + 调引擎函数"，
// 宿主上没有引擎映像，所以用注入的实现替代。类型是"房间指针进、帧数出"。
using RoomFrameCountHostFunction = std::int32_t (*)(const void* room);
void SetRoomGetFrameCountHostFunction(RoomFrameCountHostFunction function) noexcept;
[[nodiscard]] RoomFrameCountHostFunction GetRoomGetFrameCountHostFunction() noexcept;
// 2026-09-21：`GridEntity.Position` 的宿主替身（设备构建里不存在这段）。
using GridEntityPositionHostFunction = void (*)(const void* entity, float* x, float* y);
void SetGridEntityGetPositionHostFunction(GridEntityPositionHostFunction function) noexcept;
[[nodiscard]] GridEntityPositionHostFunction GetGridEntityGetPositionHostFunction() noexcept;
#endif
// `Room:WorldToScreenPosition()` 用的引擎函数（PLT 桩）。宿主上由注入的实现替代。
[[nodiscard]] uintptr_t GetRenderPositionThunk() noexcept;
void SetGetRenderPositionBinding(uintptr_t method);
#if !defined(__SWITCH__)
using RenderPositionHostFunction = void (*)(const float* input, float* output, bool useCamera);
void SetGetRenderPositionHostFunction(RenderPositionHostFunction function) noexcept;
[[nodiscard]] RenderPositionHostFunction GetRenderPositionHostFunction() noexcept;
#endif
void SetLevelIsNextStageAvailableBinding(uintptr_t method);
void SetItemPoolGetCollectibleBinding(uintptr_t method);
void SetMusicBindings(uintptr_t getCurrentMusicId, uintptr_t pause, uintptr_t resume);
// 批次 137：`MusicManager:UpdateVolume()` 的**单方法绑定**（与 `SetLevelIsAscentBinding`
// 同一个形状：一次 release 存储、handler 一次 acquire 读 ⇒ 不会看到"半个已校验记录"）。
// 为什么单独一条而不并进 `SetMusicBindings`：那条已经是三参数记录、且有既有调用方与用例，
// 扩参会让"发布点漏发"这类历史教训重新出现；单方法发布点与其它可选能力同形。
void SetMusicUpdateVolumeBinding(uintptr_t method);
// 批次 138：`MusicManager:Play(ID, Volume)` 的单方法绑定（与 `SetMusicUpdateVolumeBinding` 同形）。
void SetMusicPlayBinding(uintptr_t method);

// Publishes the controller-input bindings resolved during Hook installation. Any of the
// three may be zero, and the handlers then report an unavailable binding rather than a
// fabricated reading.
void SetInputBindings(uintptr_t isActionPressed, uintptr_t isActionTriggered,
                      uintptr_t getActionValue);
//: 批次 195（2026-09-29）：**按键号**那三条查询的入口（`KAGE::Input::ManagerBase`）。
//:
//: 为什么**单独一条**而不并进 `SetInputBindings`：与 `SetRngRandomBindings` 同一条理由 ——
//: 上面那条已经是三参数记录、且有既有调用方与多个 harness 在按旧形状安装宿主实现，
//: 改签名会把它们一起卷进来。这三条按同一个"可选能力"口径发布：守卫不符只留 0，
//: handler 报"绑定不可用"，**绝不编一个 false/0.0** 把偏移写串伪装成"没按下"。
void SetInputButtonBindings(uintptr_t isButtonPressed, uintptr_t getButtonValue);
void SetRngBindings(uintptr_t setSeed, uintptr_t next);
// 批次 195（2026-09-29）：`RNG:RandomInt(Max)` / `RNG:RandomFloat()` 的两个入口。
//
// 为什么**单独一条**而不并进 `SetRngBindings`：与 `SetMusicPlayBinding` 同一条理由 ——
// 上面那条已经是两参数记录、且有既有调用方与两个 harness（`test_starterr_rng.py` /
// `test_lua_grid_rng_pill.py`）在按旧形状安装宿主实现，改签名会把它们一起卷进来。
// 两条新入口按同一个"可选能力"口径发布：守卫不符只留 0，handler 报"绑定不可用"，
// **绝不编一个随机数**。
void SetRngRandomBindings(uintptr_t randomUint, uintptr_t randomFloat);

// The `Font` family's native entry points, published as one record because an eleven-argument
// setter would be unreadable at the call site. Every field may stay zero: the Font handlers then
// report an unavailable binding instead of calling through a null pointer, and the family is an
// optional capability like the controller input bindings.
//
// The record holds the game module's addresses only. The storage for a Font instance is *not*
// part of this contract: `font_api.cpp` allocates and releases that block with this module's own
// `malloc`/`free` (see the comment there), which keeps the published record exactly equal to
// what `VerifyFontBindings` proved.
struct LuaFontBindings {
    FontCtorFn ctor{nullptr};
    FontDestructorFn destructor_{nullptr};  // `~Font()`; the audit shows it is a tail-jump to `Unload()`
    FontLoadFn load{nullptr};
    FontUnloadFn unload{nullptr};
    FontIsLoadedFn isLoaded{nullptr};
    FontGetStringWidthFn getStringWidth{nullptr};
    FontGetStringWidthUTF8Fn getStringWidthUTF8{nullptr};
    FontGetLineHeightFn getLineHeight{nullptr};
    FontGetBaselineHeightFn getBaselineHeight{nullptr};
    FontGetCharacterWidthFn getCharacterWidth{nullptr};
    FontSetMissingCharacterFn setMissingCharacter{nullptr};
    FontDrawStringFn drawString{nullptr};
    // 三个绘制变体（PC 同族的 `DrawStringScaled`/`DrawStringUTF8`/`DrawStringScaledUTF8`）。
    // 缩放走 s2/s3，其余参数与 `drawString` 一致；EID 用的是 `DrawStringScaledUTF8`。
    FontDrawStringScaledFn drawStringScaled{nullptr};
    FontDrawStringUTF8Fn drawStringUTF8{nullptr};
    FontDrawStringScaledUTF8Fn drawStringScaledUTF8{nullptr};
};
void SetFontBindings(const LuaFontBindings& bindings);
std::uint64_t FontBindingGeneration() noexcept;

// `Sprite`（引擎侧 `IsaacRepentance::ANM2`）第一步的入口集合：全部只收 `char const*` 与数值，
// 因此不涉及 libc++/libstdc++ 的 `std::string` ABI 差异（`Load`/`ReplaceSpritesheet` 需要那层桥，
// 放在第二步）。和 Font 一样：字段可以保持 0，handler 于是报“绑定不可用”，绝不调用未校验的地址。
struct LuaSpriteBindings {
    SpriteCtorFn ctor{nullptr};
    SpriteDestructorFn destructor_{nullptr};  // `~ANM2()`（D1）：析构成员但**不释放 this**
    SpritePlayFn play{nullptr};
    SpriteSetAnimationFn setAnimation{nullptr};
    SpriteSetFrameNamedFn setFrameNamed{nullptr};
    SpriteSetFrameFn setFrame{nullptr};
    SpriteGetFrameFn getFrame{nullptr};
    SpriteSetLayerFrameFn setLayerFrame{nullptr};
    SpriteGetLayerFrameFn getLayerFrame{nullptr};
    // `GetTexel(Vector2 samplePos, Vector2 renderPos, float alphaThreshold, int layerId)`：
    // **两个 `Vector2` 按值传**（AAPCS64 的 HFA 规则 → s0..s3 / 一般寄存器不必参与），
    // 返回 16 字节 `KColor` 走 x8 间接结果寄存器。ABI 解码见
    // `analysis/stage150-sprite-abi/<build>.json` 的 `records.sprite_get_texel.abi`
    // （confidence = verified，符号与 16 字节守卫都与 NRO 逐字节核对过）。
    SpriteGetTexelFn getTexel{nullptr};
    SpriteUpdateFn update{nullptr};
    SpriteIsPlayingFn isPlaying{nullptr};
    SpriteIsFinishedFn isFinished{nullptr};
    //: 批次 214：`ANM2::Reset()`（中文版 MCM 的 anm2 探测要用）。
    SpriteResetFn reset{nullptr};
    SpriteRenderFn render{nullptr};
    SpriteRenderLayerFn renderLayer{nullptr};
    SpritePlayRandomFn playRandom{nullptr};
    //: 批次 279：overlay 三条（语料里 `Sprite:PlayOverlay` 12 处、`SetLastFrame` 6 处、
    //: `SetOverlayFrame` 1 处）。
    SpritePlayOverlayFn playOverlay{nullptr};
    SpriteSetLastFrameFn setLastFrame{nullptr};
    SpriteSetOverlayFrameFn setOverlayFrame{nullptr};
    //: 批次 280：`ANM2::Stop()`（把动画停下）。
    SpriteStopFn stop{nullptr};
    //: 批次 283：四条「按名字查询」（语料 6 处，全在 `BOIStageAPI15`）。
    SpriteIsOverlayPlayingFn isOverlayPlaying{nullptr};
    SpriteIsOverlayFinishedFn isOverlayFinished{nullptr};
    SpriteIsEventTriggeredFn isEventTriggered{nullptr};
    SpriteWasEventTriggeredFn wasEventTriggered{nullptr};
    // 第二步：需要 libc++ `std::string` 的三个入口，外加借来代建字符串的
    // `basic_string::assign(char const*)`（游戏导入的 PLT 桩）。
    SpriteLoadFn load{nullptr};
    SpriteLoadGraphicsFn loadGraphics{nullptr};
    SpriteReplaceSpritesheetFn replaceSpritesheet{nullptr};
    LibcxxStringAssignFn libcxxStringAssign{nullptr};
    // 释放"落在堆上的长路径"要用**游戏自己的** `operator delete`（见 `kGameOperatorDeleteOffset`）。
    GameOperatorDeleteFn gameOperatorDelete{nullptr};
};
void SetSpriteBindings(const LuaSpriteBindings& bindings);

// --- 最近的 Lua 错误（环形历史）-------------------------------------------------------
//
// 批次 052 起有 8 格环形历史；批次 068 起每一格带上"**是哪个模组、哪条回调**报的"，
// 并且**同一条重复错误只占一格**（真机上遇到过一条每帧刷屏的错把 8 格全占满、
// 别人的错一条都进不来）。
//
// 这里只给宿主测试一个只读访问器：**调试桩不经过它** —— 工具是按符号直读那块内存的
// （`g_LuaErrorHistory`），所以访问器与内存布局必须保持一致（`static_assert` 钉着 128 字节/条）。
struct LuaErrorHistoryEntryView {
    std::uint32_t owner;       //: 模组句柄；0 = 不知道（例如加载期）
    std::uint32_t callbackId;  //: 回调 id；`kNoCallbackDispatched` = 不是回调路径
    char text[120];            //: NUL 结尾的错误文本
};

//: 把环形历史拷进 `output`（最多 `capacity` 条），返回**实际写了多少条**。
[[nodiscard]] std::size_t CopyLuaErrorHistory(LuaErrorHistoryEntryView* output,
                                             std::size_t capacity) noexcept;

void DispatchPostUpdate();
// 引擎侧的开局中继只记账、不在这里跑 Lua（它运行在 `Game::Start` 刚返回的那一刻，
// 那时候调用模组回调风险高）。真正的派发在下一帧的 `DispatchPostUpdate()` 里做。
// `isSave`：真 = 读档进游戏，假 = 新开一局（来自中继的事件种类）。
void NoteGameStarted(bool isSave) noexcept;
// ★ 批次 417：`LuaStateMemoryBytes()` 的声明**不在这里** —— 消费方
//   `mod_menu_native.cpp` 包含的是 `lua_runtime_state.hpp`，声明放那边（放这儿会
//   得到 `'LuaStateMemoryBytes' is not a member of 'LuaRuntime'`）。
void DispatchPostRender(uintptr_t manager);

// --- 批次 149（2026-09-26）：`MusicManager:` 一族"回调里拿不到 Manager"的兜底 -------------
//
// 为什么需要：`MusicManager:` 的每个方法都要一个 Manager 才能定位引擎的 `Music` 对象，
// 而那个 Manager 以前**只**来自"当前正在派发的那条回调"。可 `MC_POST_UPDATE` 的派发
// **不带** Manager（`LuaCallbackInvoker{0, false, true}`，那条例行字面量被
// `test_embedded_lua_runtime.py` 钉着）⇒ 模组在 `MC_POST_UPDATE` 里调
// `MusicManager():Play(...)` 时恒为空、整族报 "native bindings are unavailable"。
// 真机实例：The Specialist for Good Items 的"捡到四级物品放歌"（`main.lua:483/488/489`）
// 全在 `MC_POST_UPDATE`（`OnGameUpdate → OnPogMoment → DoCostume`）里。
//
// PC 的绑定层本来就不是"从回调里取 Manager"，而是读引擎自己的全局 Manager ⇒
// "回调里没有就用本帧的"比"报错"更接近 PC 语义；两者本来就是同一个 Manager 单例
// （每帧 `Manager::Update` / `Manager::Render` 收到的 `self`）。
//
// `provider` 返回**本帧的 Manager**（0 = 不知道）。由 `hook_manager.cpp` 在安装期发布
// （与 `SetSessionContentMountService` 同一处、同一条理由：模块初始化线程、主循环尚未开始）；
// 宿主夹具不发 ⇒ 取不到 ⇒ 行为与改动前逐字相同（宿主判据不受影响）。
void SetFrameManagerProvider(std::uintptr_t (*provider)()) noexcept;
// MC_PRE_GET_COLLECTIBLE（id 62）：挂在 `ItemPool::GetCollectible` 的入口中继里，
// **先于**原函数派发；返回值（若有）就是"这次该给的道具"，调用方据此跳过原函数。
std::uint64_t DispatchPreGetCollectible(void* itemPool, std::uint32_t itemPoolType,
                                        std::uint32_t seed, std::uint32_t noDecrease,
                                        std::uint32_t lastCollectibleType);
// --- 回调面补齐（2026-09-20 批次 102）：四个事件中继的派发入口 -------------------
//
// ★ 为什么不照"开局中继只记账、下一帧再派发"那条先例推迟（那条先例见上面 `NoteGameStarted`
// 的注释）：这四条**要么推不了、要么推了就不对**——
//   * `MC_PRE_USE_ITEM` 的返回值决定"要不要取消这次使用"，必须在引擎动手**之前**派发；
//   * `MC_PRE_GAME_EXIT` 之后没有"下一帧"（这一局正在结束），而 EID 唯一的存档点就在这里；
//   * 另外两条（USE_ITEM / USE_CARD / USE_PILL）是纯通知，PC 也是内联触发的，推迟只会让
//     "用过的东西进历史"晚一帧、并打乱与其它事件的先后。
// 风险用另外两条防线兜住：①每个函数都自己判"现在到底能不能派发"（`ShouldDispatchManagedCallbacks`）；
// ②回调里报错由派发器隔离（记进错误环形历史，不向上抛、不摘掉登记）。
void DispatchPreGameExit(bool shouldSave);
//: 返回 true = **拦下**这次使用（PC 的 `MC_PRE_USE_ITEM` 约定：任一条返回 true 即取消）。
[[nodiscard]] bool DispatchPreUseItem(std::uintptr_t player, std::int32_t collectibleType,
                                      std::int32_t useFlags, std::int32_t activeSlot,
                                      std::int32_t customVarData);
isaac::runtime::UseItemCallbackResult DispatchUseItem(std::uintptr_t player, std::int32_t collectibleType, std::int32_t useFlags,
                     std::int32_t activeSlot, std::int32_t customVarData);

// --- 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的派发入口 --------------------------------------
//
// 契约（`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md:347-367`）：**引擎每次轮询某个
// `ButtonAction` 时**触发一次（官方执行信息栏：**每秒约 1470 次**），实参 `(Entity, InputHook,
// ButtonAction)`；**返回非 nil 即覆盖**这次查询的结果（`GetActionValue` 的覆盖值是 0.0~1.0 的 float）。
// ⇒ 这是一条**在输入热路径上、每秒上千次**的入口，调用方（三条查询中继）必须**先看 `overridden`**，
//   只有它为真时才动返回值；平时的开销必须只剩"查一次登记数"。
struct InputActionOutcome {
    //: 有可用的覆盖值（第一条返回非 nil 的登记）。false = 照原样返回引擎的结果。
    bool overridden{false};
    //: `IS_ACTION_PRESSED(0)` / `IS_ACTION_TRIGGERED(1)` 的覆盖值。
    bool boolean{false};
    //: `GET_ACTION_VALUE(2)` 的覆盖值（已按 PC 契约夹到 0.0~1.0）。
    float value{0.0F};
};

// Entity由Manager高层原生实参直接传入，0必须保持nil；不能按controller猜玩家。
[[nodiscard]] InputActionOutcome DispatchInputAction(std::uint32_t action,
                                                     std::uint32_t controllerIndex,
                                                     std::int32_t inputHook,
                                                     std::uintptr_t entity);

// --- 批次 392（2026-10-07）：`Input` 类读取必须**绕开**上面那条覆盖 -----------------------------
//
// ★★★ 真机回归 + 反汇编定案：Lua 的 `Input.IsActionPressed/IsActionTriggered/GetActionValue`
// 绑的是 `0x3F9B6C/0x3F9B7C/0x3F9B8C`（符号 = `IsaacRepentance::Manager::IsAction*`），而这三条
// **尾跳**（`b`，不是 `bl`）进 `KAGE::Input::ManagerBase::IsAction*`（`0x4F9920/0x4F9A64/0x4F9BCC`）
// —— **正是批次 390 挂中继的那三条**（`tools/engine_symbol_signatures.json` 里该符号 offset = 0x4f9920）。
// 同一个符号另有 35/21/20 个调用点，含 `Entity_Player::get_movement_input` / `control_shooting` /
// 各菜单类自己的输入处理 ⇒ **我们这侧的读取与引擎自己的读取是同一次调用，在函数入口上区分不了**
// （部分原生请求传nil，移动/射击等请求传真实Entity*；高层中继保留这项差异）。
//
// 而 PC 契约（`analysis/isaacdocs-snapshot/docs/enums/ModCallbacks.md:355`）明写：
//   *"This callback will not affect any custom mod code that is reading user input via the
//   `Input` class."*
// ⇒ 不绕的后果（2026-10-07 真机复现）：MCM 菜单可见时对一切动作 `return false`（本意是冻住角色），
// 结果连**它自己的光标读输入**也被答成 false ⇒ 摇杆推不动光标。
//
// 形状：我们这侧每次查输入都进一次这个作用域；三条中继看到标记就**直接调原函数、不派发**。
// 用 RAII（构造置位 / 析构清除）而不是手工置位，是为了任何早退路径都不会把标记留成"卡住"
// —— 一旦卡住，**引擎自己的**读取也会失去覆盖（菜单开着还能走，那是更糟的回归）。
// ★ 计数式 ⇒ 嵌套安全：模组在自己的 `MC_INPUT_ACTION` 处理里再问 `Input.*` 时也走这里。


void DispatchUseCard(std::uintptr_t player, std::int32_t card, std::int32_t useFlags);
void DispatchUsePill(std::uintptr_t player, std::int32_t pillEffect, std::int32_t useFlags);
// 批次 103：`MC_PRE_PICKUP_COLLISION`（38）。返回 true = **不要跑原函数**
// （PC 的三态里 `true` 与 `false` 都不执行内部代码、只有 `nil` 才照常执行，所以这里合成一个
// "非 nil 即拦"。`PickupVariant` 是 PC 给这条回调的可选实参类型 ⇒ `filter` 传掉落物的变体）。
enum class CollisionOverride : std::int8_t { Continue = -1, Collide = 0, Ignore = 1 };
[[nodiscard]] CollisionOverride DispatchPreEntityCollision(std::uint32_t callbackId,
    std::uintptr_t entity, std::uintptr_t collider, bool low, std::int32_t filter);
[[nodiscard]] std::int32_t DispatchGetPillColor(std::uint32_t seed, std::int32_t selected);
[[nodiscard]] std::int32_t DispatchGetPillEffect(std::uint32_t color, std::int32_t selected);
// 66 原生消费者：0=不覆盖；非0=首个返回整数的低32位。RNG 是当批共享自有值快照。
[[nodiscard]] std::uint32_t DispatchGetTrinket(std::int32_t selected,
    const std::array<std::uint8_t,16>& rngSnapshot);
[[nodiscard]] bool DispatchPreEntityDevolve(std::uintptr_t entity);
[[nodiscard]] bool DispatchPreNpcUpdate(std::uintptr_t npc, std::int32_t entityType);
struct EntitySpawnOverride {
    bool present{false};
    std::int32_t type{0};
    std::uint32_t variant{0}, subType{0}, seed{0};
};
[[nodiscard]] EntitySpawnOverride DispatchPreEntitySpawn(std::int32_t type, std::uint32_t variant,
    std::uint32_t subType, const void* position, const void* velocity,
    std::uintptr_t spawner, std::uint32_t seed);
// 仅由Projectile正常完成尾部调用；同帧显式Update每次独立派发。
void DispatchPostProjectileInit(std::uintptr_t projectile);
void DispatchPostProjectileUpdate(std::uintptr_t projectile);
// Explicit Entity:Update only; projectile already dispatches at its native tail.
void DispatchPostManualEntityUpdate(std::uintptr_t entity);
void DispatchPostNpcRender(std::uintptr_t npc, const void* renderOffset);
[[nodiscard]] bool DispatchPrePickupCollision(std::uintptr_t pickup, std::uintptr_t collider,
                                             bool low, std::int32_t pickupVariant);
// 批次 104：`MC_PRE_ROOM_ENTITY_SPAWN`（71）。实参 = PC 的
// `(EntityType, Variant, SubType, GridIndex, Seed)`（PC 的 `Seed` 我们**有**：引擎用它构造
// `RNG(seed, ...)`，见 `runtime_constants.hpp` 的靶点注释）。
//
// `fieldsReadable`：那三个字段读不到时**不派发**（不编造 Type/Variant/SubType —— EID 拿它们
// 建索引，给错的比给不到更糟）。调用点（`room_spawn_entity` 的入口中继）负责传这个事实。
void DispatchPreRoomEntitySpawn(std::int32_t entityType, std::int32_t variant,
                                std::int32_t subType, std::int32_t gridIndex,
                                std::int32_t seed);
// 71内部边界使用；present只在最终表的1/2/3至少一个字段非nil时为真。
struct RoomEntitySpawnOverride {
    bool present{false};
    std::int32_t type{0};
    std::uint16_t variant{0}, subType{0};
};
[[nodiscard]] RoomEntitySpawnOverride DispatchPreRoomEntitySpawnModifying(
    std::int32_t type, std::uint16_t variant, std::uint16_t subType,
    std::uint32_t gridIndex, std::uint32_t seed);
// 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG`(11)。返回 **true = 不要跑原函数**
// （PC 契约：只有**返回 `false`** 才取消这次伤害；`true`/`nil` 都照常受伤）。
// `entityType` 是过滤器（PC 给这条回调的可选实参类型就是 `EntityType`）。
// `sourceRef` 是引擎那个 `EntityRef const&` 的地址（0 = 没有来源）；`damageFlags`/`countdownFrames`
// 按 PC 签名压整数。四条入口中继（基类 + 玩家/掉落物/槽位）共用这一个函数。
[[nodiscard]] bool DispatchEntityTakeDamage(std::uintptr_t entity, float amount,
                                            std::uint64_t damageFlags, std::uintptr_t sourceRef,
                                            std::int32_t countdownFrames, std::int32_t entityType);
// 批次 396（2026-10-07）：`MC_EVALUATE_CACHE`(8)。过滤器 = 本次要重算的那个 CacheFlag 位；
// 调用点把 `Entity_Player + 0x1958` 掩码逐位拆开、一位调一次（入口不带 CacheFlag 实参）。
void DispatchEvaluateCache(std::uintptr_t player, std::int32_t cacheFlag);
// 批次 397（2026-10-07）：补全回调（第 2 批）的三条 —— 实参一律照 PC 契约写。
//   * `MC_POST_ENTITY_KILL`(68)：`(Entity)`，过滤器 = `entityType`；
//   * `MC_POST_NPC_DEATH`(29)：`(EntityNPC)`，过滤器 = `entityType`；
//   * `MC_POST_GAME_END`(16)：`(bool IsGameOver)`，无过滤（★ 必须压布尔，见实现处的说明）。
void DispatchPostEntityKill(std::uintptr_t entity, std::int32_t entityType);
void DispatchPostNpcDeath(std::uintptr_t npc, std::int32_t entityType);
void DispatchPostGameEnd(bool isGameOver);
// `MC_POST_FIRE_TEAR`(61)：`(EntityTear)`，无过滤；实参 = `FireTear` 的返回值（泪弹指针）。
void DispatchPostFireTear(std::uintptr_t tear);
//: 调用点**先**读 `RoomConfig::Entry` 的前三个字段（`ReadRoomConfigEntryFields`）；
//: 读不到就**不要调**上面那个派发函数 —— 不编造 Type/Variant/SubType（EID 拿它们去建索引，
//: 给错的比给不到更糟；理由与 `runtime_constants.hpp` 里那段靶点证据同一节）。
// PC 文档：`MC_POST_GET_COLLECTIBLE` 在道具**已经选出来之后**触发，返回值可以替换它；
// 而"`MC_PRE_GET_COLLECTIBLE` 返回过非 nil"时本条**跳过**（由调用方判，见中继回调）。
std::uint64_t DispatchPostGetCollectible(void* itemPool, std::uint32_t itemPoolType,
                                         std::uint32_t seed, std::uint32_t decrease,
                                         std::uint32_t selectedCollectible);
#if !defined(EXL_DIAGNOSTIC_STAGE)
bool IsMusicReadyForDefaultCallback(uintptr_t manager);
#endif
bool IsReady();
// 仅已确认的游戏线程、Lua空闲时正常73卸载并关闭旧VM；失败保留旧VM供重试。
// 不建立新状态、不清持久化数据或引擎入口绑定；无状态时幂等成功。
[[nodiscard]] bool ShutdownForModReload() noexcept;
// 正常卸载通知已完成、正在lua_close时为true；原生借用setter此时不能新增Lua引用。
[[nodiscard]] bool ClosingForModReload() noexcept;
u32 PostUpdateCount();
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
u32 PostRenderCount();
u32 PostRenderPausedCount();
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17)
bool MusicDiagnosticCycleCompleted();
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
bool MusicDiagnosticCurrentId(u32* value);
#endif
bool TakeCallbackError();

// Probe-facing read-only access to the Lua state, used to turn "did the Mod actually run"
// into machine evidence instead of an audible guess:
//   * `ReadLuaGlobalNumber` reads a global the Mod itself wrote (a progress marker);
//   * `RegisteredCallbackCount` reports how many callbacks of one id are still registered --
//     a Lua error inside a callback makes the dispatcher drop that callback, so a falling
//     count is how a swallowed error becomes visible.
[[nodiscard]] bool ReadLuaGlobalNumber(const char* name, double* value);

// 读 `<global>.<field>`：先 `lua_getglobal(global)`，再在**表上**取字段。
//
// 为什么需要它（2026-09-12 的教训）：探针用 `ReadLuaGlobalNumber("EID.GameRenderCount")`
// 连读两次都答"没有"，而同一份报告里 update/render 回调进入次数是 900/878 —— 两者不可能同真，
// 说明那条通道给不出可信结论。EID 的 `EID` 是一张表（`RegisterMod` 的返回值再加字段），
// 所以这里按"表 + 字段"取，并且把**取不到的原因**分成三种报出来：
//   1 = 全局不是表（`EID` 本身没建出来）
//   2 = 表里没有这个字段（值是 nil）
//   3 = 字段在但不是 number
//   0 = 成功（此时 `*value` 有效）
[[nodiscard]] std::uint32_t ReadLuaTableNumber(const char* globalName, const char* fieldName,
                                               double* value);
[[nodiscard]] bool ReadLuaTableBoolean(const char* globalName, const char* fieldName,
                                       bool* value);
// 读 `<global>.<table>.<field>`（例如 `EID.Config.HideInBattle`）。语义与两级版本一致。
[[nodiscard]] std::uint32_t ReadLuaNestedNumber(const char* globalName, const char* tableName,
                                                const char* fieldName, double* value);
[[nodiscard]] bool ReadLuaNestedBoolean(const char* globalName, const char* tableName,
                                        const char* fieldName, bool* value);
// 读 `<global>.<field>` 是不是一张表（用来区分"字段不存在"与"字段是一张表"）。
[[nodiscard]] bool LuaTableFieldIsTable(const char* globalName, const char* fieldName);
[[nodiscard]] std::uint32_t RegisteredCallbackCount(std::uint32_t callbackId);
#if defined(EXL_PERSISTENCE_TRACE) || defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
u64 CallbackFailureDetail();
#endif

} // namespace LuaRuntime

namespace LuaRuntime {
// PC70参数按值，同一Lua派发批共享；取消采用Lua真值，不改引擎seed/position。
bool DispatchPreSpawnCleanAward(const std::array<std::uint8_t,16>& snapshot, float x, float y);
}

namespace LuaRuntime { void DispatchPostEntityRemove(std::uintptr_t entity, std::int32_t entityType); }

namespace LuaRuntime {
std::uint32_t DispatchPostCurseEval(std::uint32_t curses);
void DispatchPostPickupSelection(std::uintptr_t pickup,std::uint32_t* variant,std::uint32_t* subType);
}

namespace LuaRuntime {
bool IsOnGameThread() noexcept;
void ObserveGameThread() noexcept;
bool CanDispatchGetCard() noexcept;
std::uint32_t DispatchGetCard(void*,std::uint32_t,bool,bool,bool);
}

namespace isaac::runtime {struct ShaderProgramView;}
namespace LuaRuntime {bool FillShaderParameters(const isaac::runtime::ShaderProgramView&,float*,std::uintptr_t) noexcept;}

namespace LuaRuntime { void DispatchPressurePlateAnimationPinEvent(std::uintptr_t,bool beforeDestroy) noexcept; }

namespace LuaRuntime {
isaac::runtime::UseItemCallbackResult DispatchUseItemAtNativeBoundary(std::uintptr_t player,
    std::int32_t item,std::int32_t flags,std::int32_t slot,std::int32_t custom,
    std::uint64_t nativeResult,bool animationAllowed);
}
