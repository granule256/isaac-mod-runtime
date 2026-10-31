#include "interfaces/lua/api700_grid.hpp"
#include "interfaces/lua/api600_bindings.hpp"
#include "interfaces/lua/api200_bindings.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/api100_bindings.hpp"
#include "interfaces/lua/rplus_extended_fields.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/api_sequence_probe.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "interfaces/lua/engine_method_lookup.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"

#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"

#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstdlib>
#include <cstring>

// `svcQueryMemory`/`MemoryInfo`/`Perm_R` 只存在于设备侧（libnx）；宿主构建里可读性检查退化成
// "只排除空地址"。与 `isaac_api.cpp`/`game_api.cpp`/`remaining_api.cpp` 同一形态（那三个 TU
// 各自有一份同样的私有实现，本 TU 只为 `Sprite:GetAnimation()` 读动画名而需要它）。
#if defined(__SWITCH__)
#include "lib/nx/nx.h"
#endif

extern "C" {
#include <lauxlib.h>
#include "probe_gate.hpp"
}

namespace isaac::runtime {
namespace {

using LuaRuntime::ColorHandle;
using LuaRuntime::kColorMetatable;
using LuaRuntime::kSpriteMetatable;
using LuaRuntime::kSpriteSourceEngineEntity;
using LuaRuntime::kSpriteSourceEngineGridEntity;
using LuaRuntime::kSpriteSourceRuntimeOwned;
using LuaRuntime::SpriteHandle;
using LuaRuntime::VectorHandle;

constexpr char kSpriteOwner[] = "Sprite";
constexpr std::size_t kSpriteStorageSlack = kSpriteObjectAlignment;

// 引擎字段读取原语：先确认可读再 `memcpy`（指针猜错必须变成"读不到"而不是"读了就崩"）。
// 「这段地址可读吗」：**唯一实现在引擎内存访问层里**（2026-09-24 批次 102 收敛）。
// 此前四个 API 族各有一份逐字相同的拷贝（去掉注释后各 781 字符）；判决条件一条没改，
// 只是"实现在几处"从 4 变成了 1。**函数名保留** —— `test_lua_missing_members_batch028`
// 按这个名字核对四个手写处理器体里有没有做可读性检查。
bool IsEngineMemoryReadable(std::uintptr_t address, std::size_t length) noexcept {
    return isaac::runtime::engine_memory::EngineMemoryReadable(address, length);
}

// 2026-09-24（批次 114）：**实现搬进引擎内存访问层**（`engine_memory::ReadAt`）—— 本 TU 只剩一行
// 委托，与写侧的 `WriteEngine`、以及 `isaac_api.cpp` 里的同名原语同例。判据一条没改：
// 先可读、再取值；失败时**不写**出参。
template <typename T>
bool ReadEngine(std::uintptr_t address, T* value) noexcept {
    return engine_memory::ReadAt(address, value, &IsEngineMemoryReadable);
}

// 引擎字段**写**原语（2026-09-16，与上面的读原语成对；2026-09-24 批次 103 收敛进访问层）。
//
// 为什么不能直接 `*reinterpret_cast<float*>(address) = value`：这里的地址来自**引擎对象**
// （`ANM2`、`Entity_Player`），任何一次"猜错的地址"都会变成对别人的内存的破坏，而且是静默的。
// 所以写之前必须先确认"这一段内存**可写**"。判据与写缓存**都不在这个 TU 里了** ——
// 「这段地址可写吗」现在**唯一实现在引擎内存访问层里**（`EngineMemoryWritable`：按 `Perm_W`、
// 走**写**缓存；可读 `Perm_R` 绝不等于可写 `Perm_W`）。**函数名保留** ——
// 契约测试按这个名字核对两个可写 TU 都只是委托，实现只有一份。
bool IsEngineMemoryWritable(std::uintptr_t address, std::size_t length) noexcept {
    return isaac::runtime::engine_memory::EngineMemoryWritable(address, length);
}

// 唯一的引擎写入口。`WriteEngine` 这个名字在门禁里是**保留字**：契约测试
// `tests/contract/test_engine_write_channel.py` 要求 `runtime/src/interfaces/lua/` 下
// 任何"往引擎地址写"的地方都走这里，不许出现裸指针赋值或裸 `memcpy`。
// 体内那次 `memcpy` 也已搬进层（`engine_memory::WriteAt` ⇒ `WriteField`）——
// 全仓"往引擎写一个字段"的实现因此**只剩层里那一份**，本处只负责注入"可写"判定。
template <typename T>
bool WriteEngine(std::uintptr_t address, const T& value) noexcept {
    return isaac::runtime::engine_memory::WriteAt(address, value, &IsEngineMemoryWritable);
}

// --- 所有权与来源（批次 5）-----------------------------------------------------
//
// `SpriteHandle` 有两种来源，释放语义相反（详见 `lua_object_handles.hpp` 的注释）：
//
//   RuntimeOwned（Lua 的 `Sprite()`）—— 内存由本模块 `malloc`，`__gc` 必须 `~ANM2()` + `free`；
//   EngineEntity（`Entity:GetSprite()`）—— 内存是**引擎实体**的成员，`__gc` 什么都不做。
//
// ★ 这里只有一条纪律：**任何**访问都先走 `ResolveSpriteObject`，绝不再直接读 `handle->sprite`
// 去解引用。引擎实体随时可能随换房间/死亡消失，所以引擎来源的地址**每次重新算**（`owner` →
// 校验实体活着 → `owner + kEntitySpriteOffset`），句柄里缓存的地址只当身份。
void* ResolveSpriteObject(const SpriteHandle* handle) noexcept {
    if (handle == nullptr) {
        return nullptr;
    }
    if(handle->source==LuaRuntime::kSpriteSourceEngineGridExtra)return ResolveApi700GridSprite(handle);
    if (handle->source == kSpriteSourceEngineEntity) {
        const std::uintptr_t owner = engine_memory::AddressOf(handle->owner);
        // "还活着"的判据只有一份实现（`isaac_api.cpp` 的 `ValidatedEntity` 用的那条）：
        // vptr 仍落在 `Entity` 家族区间内且地址可读。
        if (!EntityLifetimeAlive(handle->lifetime) || !IsLiveEntityPointer(owner)) {
            return nullptr;
        }
        return engine_memory::AsObject(owner + kEntitySpriteOffset);
    }
    // 批次 298：网格实体借出的 sprite（`GridEntity:GetSprite()`）。**同一个形状**，
    // 只换存活判据与偏移 —— 网格实体随时可能被销毁（石头炸掉、换房间重建），
    // 所以每次访问都要重新算 `owner + kGridEntitySpriteOffset`。
    if (handle->source == kSpriteSourceEngineGridEntity) {
        const std::uintptr_t owner = engine_memory::AddressOf(handle->owner);
        if (!IsLiveGridEntityPointer(owner)) {
            return nullptr;
        }
        return engine_memory::AsObject(owner + kGridEntitySpriteOffset);
    }
    return handle->sprite;
}

// 动画名的字节上限。libc++ 的 `std::string` 可能是长串（数据在引擎堆上，指针来自引擎内存），
// 所以我们**不**做无界 `strlen`：逐字节确认可读、遇到 0 或到达上限就停。
constexpr std::size_t kAnimationNameCapacity = 64;

//: **文件名**的字节上限（批次 309）。比动画名宽：模组可以给出很长的 `gfx/...` 路径
//: （契约 `Sprite.md:79` 的例子是 `gfx/001.000_Player.anm2`，而模组自己的路径可能长得多）。
//: ★ 超限**不截断**（见 `ReadLibcxxStringAt` 的长度校验）：宁可答空串，也不答一个"看着像真的"
//:   被砍掉尾巴的文件名 —— 语料里 `customgrids.lua` 拿它当字典键，错键会静默走错分支。
constexpr std::size_t kFilenameCapacity = 256;

// --- `Sprite:GetTexel` 的探针（2026-09-12，动作一）-------------------------------
//
// 目的：`GetTexel` 是"EID 判赎罪线问号底座"的唯一依据，而它的调用约定（HFA 按值传）
// 是本轮唯一有风险的改动。真机上一轮结束后要能回答三个问题：
//   * 引擎入口到底被调到了几次（`calls`）；
//   * 有多少次因入口缺失或对象不可读而报错（历史符号 `fallbacks` 保留）；
//   * 最近一次真实读数长什么样（`lastWord` = 低 32 位 R、次 32 位 G，足以区分
//     "全 0（引擎说这里是空像素）"和"非 0（真读到了贴图颜色）"）。
std::atomic<std::uint32_t> g_SpriteGetTexelCalls{0};
std::atomic<std::uint32_t> g_SpriteGetTexelFallbacks{0};
std::atomic<std::uint32_t> g_SpriteGetTexelLastReason{0};
std::atomic<std::uint64_t> g_SpriteGetTexelLastWord{0};

// 保留失败次数与原因探针，但不再把失败伪装成白色像素。
int SpriteTexelError(lua_State* state, std::uint32_t reason, const char* message) {
    g_SpriteGetTexelFallbacks.fetch_add(1, std::memory_order_relaxed);
    g_SpriteGetTexelLastReason.store(reason, std::memory_order_relaxed);
    return luaL_error(state, "Sprite:GetTexel %s", message);
}

void RecordSpriteGetTexelForProbe(float red, float green, bool enginePath) noexcept {
    (void)red;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)green;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)enginePath;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    if (enginePath) {
        g_SpriteGetTexelCalls.fetch_add(1, std::memory_order_relaxed);
        std::uint32_t redBits = 0;
        std::uint32_t greenBits = 0;
        std::memcpy(&redBits, &red, sizeof(redBits));
        std::memcpy(&greenBits, &green, sizeof(greenBits));
        g_SpriteGetTexelLastWord.store((static_cast<std::uint64_t>(greenBits) << 32) | redBits,
                                       std::memory_order_relaxed);
    }
#endif  // EXL_DIAGNOSTIC_PROBES
}

// 读 `ANM2+0x38` 指向的"当前动画名"。返回 false 表示"没有当前动画或读不到"（调用方回空串）。
//
// 读法与引擎自己的 `ANM2::IsPlaying(char const*)`（`private:kSpriteIsPlayingOffset`）逐条一致：对象指针为 0 → 无动画；
// 首字节最低位 = long 标志 → 长串取 `+0x10` 的数据指针、短串取 `+1` 的内联数据。
// 批次 214：把"读一个 libc++ `std::string`（含 SSO）"抽成可复用的一处实现 ——
// 中文版 MCM 要的 `Sprite:GetDefaultAnimationName()` 得读 **ANM2 动画表里某条记录的名字**，
// 与 `Sprite:GetAnimation()` 读 `ANM2+0x38` 是同一件事（同一套常量、同一套判据）。
bool ReadLibcxxStringAt(std::uintptr_t nameObject, char* out, std::size_t capacity) noexcept {
    if (nameObject == 0 || out == nullptr || capacity == 0) {
        return false;
    }
    std::uint8_t firstByte = 0;
    if (!ReadEngine(nameObject, &firstByte)) {
        return false;
    }
    std::uintptr_t data = 0;
    if ((firstByte & kLibcxxStringLongFlag) != 0) {
        std::uintptr_t pointer = 0;
        if (!ReadEngine(nameObject + kLibcxxStringDataOffset, &pointer) || pointer == 0) {
            return false;
        }
        data = pointer;
    } else {
        data = nameObject + kLibcxxStringShortDataOffset;
    }
    //: ★ 批次 309：先把 SSO 头里**声明的长度**读出来，再判"缓冲装得下吗" —— 装不下就**判读不到**
    //: （调用方会答空串），**不做静默截断**。原先这里把上限再夹一次 `kAnimationNameCapacity`，
    //: 于是"文件名比 63 字节长"会被静默砍尾巴，得到一个**看着像真的错值**（模组拿它当字典键
    //: 会静默走错分支 —— 本项目点名的"看起来像真值的错值"那一类）。
    //: ★ 口径与 `isaac_api.cpp` 的 `ResolveLibcxxString` 逐字一致：短串长度 = 首字节 >> 1、
    //:   长串长度在 `+0x8`（那里同样用字面量 `8`，见该函数）。
    std::size_t declared = 0;
    if ((firstByte & kLibcxxStringLongFlag) != 0) {
        std::uint64_t length = 0;
        if (!ReadEngine(nameObject + 8, &length)) {
            return false;
        }
        declared = static_cast<std::size_t>(length);
    } else {
        declared = static_cast<std::size_t>(firstByte >> 1);
    }
    if (declared == 0 || declared > capacity - 1) {
        return false;
    }
    //: 上限**由调用方给**（`GetAnimation` 传 64 字节的缓冲、`GetFilename` 传 256 字节）。
    const std::size_t limit = capacity - 1;
    std::size_t length = 0;
    while (length < limit) {
        char character = 0;
        if (!ReadEngine(data + length, &character)) {
            break;
        }
        if (character == '\0') {
            break;
        }
        out[length] = character;
        ++length;
    }
    out[length] = '\0';
    return length != 0;
}

bool ReadAnimationName(std::uintptr_t sprite, char* out, std::size_t capacity) noexcept {
    if (sprite == 0) {
        return false;
    }
    std::uintptr_t nameObject = 0;
    if (!ReadEngine(sprite + kSpriteAnimationNameOffset, &nameObject) || nameObject == 0) {
        return false;
    }
    return ReadLibcxxStringAt(nameObject, out, capacity);
}


// The native object belongs to this module, exactly like `Font`'s: the game only supplies the
// constructor/destructor entry points. Allocation mirrors the Font family (raw block, aligned
// pointer stored just in front of it so `__gc` can hand the original back to `free`).
void* AllocateSpriteStorage() noexcept {
    void* raw = std::malloc(kSpriteObjectSize + kSpriteStorageSlack);
    if (raw == nullptr) {
        return nullptr;
    }
    const std::uintptr_t rawAddress = reinterpret_cast<std::uintptr_t>(raw);
    const std::uintptr_t aligned =
        (rawAddress + sizeof(void*) + (kSpriteObjectAlignment - 1)) &
        ~(static_cast<std::uintptr_t>(kSpriteObjectAlignment) - 1);
    *reinterpret_cast<void**>(aligned - sizeof(void*)) = raw;
    return reinterpret_cast<void*>(aligned);
}

void ReleaseSpriteStorage(void* sprite) noexcept {
    if (sprite == nullptr) {
        return;
    }
    void* raw = *reinterpret_cast<void**>(reinterpret_cast<std::uintptr_t>(sprite) - sizeof(void*));
    std::free(raw);
}

int ResolveSprite(lua_State* state, const char* apiName, void** sprite) {
    auto* handle = static_cast<SpriteHandle*>(luaL_checkudata(state, 1, kSpriteMetatable));
    void* resolved = ResolveSpriteObject(handle);
    if (resolved == nullptr) {
        // 两种失效原因分开报，否则真机日志会把"实体没了"误读成"我们自己把 Sprite 释放了"。
        if (handle->source == kSpriteSourceEngineEntity) {
            return luaL_error(
                state, "%s: the engine entity this Sprite belongs to is no longer alive", apiName);
        }
        // 批次 298：网格实体那条同样把原因说清楚（否则真机日志会把"网格实体没了"
        // 误读成"我们自己把 Sprite 释放了"）。
        if (handle->source == kSpriteSourceEngineGridEntity) {
            return luaL_error(
                state, "%s: the engine grid entity this Sprite belongs to is no longer alive",
                apiName);
        }
        return luaL_error(state, "%s was called on a released Sprite", apiName);
    }
    *sprite = resolved;
    return 0;
}

// `Vector` 值类型（`KAGE::Math::Vector2`：8 字节 `{float X, float Y}`、无虚表）。三个渲染方法
// 都按引用收它，所以这里把 Lua 值的内存直接当参数传 —— 与引擎期望的形式完全一致。
VectorHandle* CheckVector(lua_State* state, int index) {
    return RequireVectorArgument(state,index);
}

// --- 批次 3：可写属性（`Scale`/`Color`/`FlipX`）与字段读取 ----------------------
//
// 为什么需要 `__index`/`__newindex`：`Sprite` 的 userdata 只有元表里的 `__gc` 与 `__index`
// 方法表；给 userdata 赋值而元表没有 `__newindex` 时，Lua 直接抛
// "attempt to index a userdata value"。EID 在**第一次画东西之前**就写这三个属性
// （`features/eid_api.lua:1368` 的 `spriteObj.Scale = ...` / `:1369` 的 `spriteObj.Color = ...`
// 在 `EID:renderIcon` 里，`main.lua:946`/`982` 的 `sprite.FlipX` 在 `EID:renderIndicator` 里），
// 所以这一条不做，第一次画字/画图必然报错。
//
// **2026-09-16 起：真的写进引擎对象**（此前只缓存）。
//
// 三个属性在 `ANM2` 里的落点是**取证定位**的，不是猜的 —— 证据链写在
// `runtime_constants.hpp` 的 `kSpriteScaleOffset` / `kSpriteColorOffset` / `kSpriteFlipXOffset`
// 上方（两条互不相同的证据：`ANM2::Reset` 写默认值、`ANM2::AnimationLayer::GetDestQuad`
// 在渲染时怎么读它们），以及 `ColorMod` 自身布局的三条（`Reset` / `SetTint` / `operator*=`）。
// 写入一律经 `WriteEngine<T>`（先确认该页可写再写），拿不到可写权限就**什么都不做**并记一次
// 拒绝计数 —— 猜地址写内存是这一类代码唯一不可接受的失败方式。
//
// 写入内容与 PC 的对应关系：
//   * `Scale` → `ANM2+0xDC` 的两个 float（`X@0xDC`、`Y@0xE0`）；
//   * `Color` → `ANM2+0xE8` 的 `ColorMod` 头 4 个 float（tint 的 R/G/B/A）加 `+0x10..+0x1C`
//     的染色四元组，+0x20..+0x28 是偏移量三元组（`Color` 的第 5/6/7 个分量）；
//   * `FlipX` → `ANM2+0x140` 的一个字节（0/1）。
//
// 允许的字段就是 PC 的这三个（大小写与 PC 一致）；其它字段名报错，避免把"拼错的属性名"
// 静默吞掉（与 `Vector`/`KColor` 的 `__newindex` 同一口径）。
constexpr char kSpriteScaleField[] = "Scale";
constexpr char kSpriteColorField[] = "Color";
constexpr char kSpriteFlipXField[] = "FlipX";

bool ReadVectorPair(lua_State* state, int index, float* x, float* y) {
    auto* vector = TryVectorArgument(state,index);
    if (vector == nullptr) {
        return false;
    }
    *x = vector->x;
    *y = vector->y;
    return true;
}

#if !defined(__SWITCH__)
SpritePropertyApplyHostImplementation g_PropertyApplyHostImplementation = nullptr;
#endif

// 把句柄里缓存的三个属性写进原生 `ANM2`。绘制路径（`Render`/`RenderLayer`）在调用引擎之前
// 无条件调用它，所以"渲染确实读到了 Mod 写的值"在设备上是由引擎自己保证的（`GetDestQuad`
// 直接读这些格子），在宿主上由 `runtime/tests/test_lua_sprite_write_channel.py` 断言字节变化。
//
// 只写"Mod 确实赋过值"的那些属性（`hasScale`/`hasColor`/`hasFlipX`）：没赋过值就不该动引擎
// 原有的值 —— 这正是 PC 的语义（PC 的 `Sprite` 是引擎对象本身，Mod 没写就没变）。
//
// 写入失败（该页不可写、地址算错）不抛 Lua 错误：绘制路径上抛错会打断整条回调，而"颜色没
// 画出来"比"描述整段消失"轻。失败只记一次拒绝计数（探针构建里可读）。
// 439 更正：上面的“绘制时无条件应用”和“写失败静默”是旧行为。现在只在赋值
// 时写本次属性，失败返回Lua错误；Render不回写缓存。偏移是+0x20/+0x24/+0x28。
enum class SpriteProperty { Scale, Color, FlipX };

bool ApplyCachedSpriteProperties(void* sprite, const SpriteHandle* handle,
                                 SpriteProperty property) noexcept {
    if (sprite == nullptr || handle == nullptr) {
        return false;
    }
    const std::uintptr_t base = engine_memory::AddressOf(sprite);
    if (handle->hasScale != 0 && property == SpriteProperty::Scale) {
        return WriteEngine<float>(base + kSpriteScaleOffset, handle->scaleX) &&
               WriteEngine<float>(base + kSpriteScaleOffset + sizeof(float), handle->scaleY);
    }
    if (handle->hasColor != 0 && property == SpriteProperty::Color) {
        const ColorHandle color{handle->colorRed, handle->colorGreen, handle->colorBlue,
                                handle->colorAlpha, handle->colorOffsetRed,
                                handle->colorOffsetGreen, handle->colorOffsetBlue};
        // PC setter@0x402370立即整44B覆盖；tint/colorize/shift布局由
        // kColorModTintOffset / kColorModColorizeOffset / kColorModShiftOffset断言固定。
        return WriteEngine<EngineColorMod>(base + kSpriteColorOffset,
                                          EngineColorModFromHandle(color));
    }
    if (handle->hasFlipX != 0 && property == SpriteProperty::FlipX) {
        return WriteEngine<std::uint8_t>(base + kSpriteFlipXOffset, handle->flipX);
    }
    return false;
}

// 保留宿主绘制观察入口；不把Lua视图缓存重新写回引擎。
void ObserveSpriteProperties(void* sprite, const SpriteHandle* handle) noexcept {
#if !defined(__SWITCH__)
    const SpritePropertyApplyHostImplementation apply = g_PropertyApplyHostImplementation;
    if (apply != nullptr) {
        apply(sprite, handle);
    }
#else
    static_cast<void>(sprite);
    static_cast<void>(handle);
#endif

}

// 把缓存的 `Scale` 压成一张 `{X, Y}` 表？不：PC 的 `Sprite.Scale` 读出来就是 `Vector`，
// 所以这里原样产出 `Vector` userdata（与 `EntityPlayer.Position` 同一做法：新对象，
// 不共享同一块 userdata）。
void PushCachedScale(lua_State* state, const SpriteHandle* handle) {
    void* sprite = ResolveSpriteObject(handle);
    VectorHandle value{};
    if (sprite == nullptr || !ReadEngine(engine_memory::AddressOf(sprite) +
                                         kSpriteScaleOffset, &value)) {
        luaL_error(state, "Sprite.Scale requires a readable live sprite");
        return;
    }
    PushLuaVector(state, value.x, value.y);
}

void PushCachedColor(lua_State* state, const SpriteHandle* handle) {
    void* sprite = ResolveSpriteObject(handle);
    EngineColorMod value{};
    if (sprite == nullptr || !ReadEngine(engine_memory::AddressOf(sprite) +
                                         kSpriteColorOffset, &value)) {
        luaL_error(state, "Sprite.Color requires a readable live sprite");
        return;
    }
    PushLuaColorFromEngineColorMod(state, value);
}

// `Render(position, topLeftClamp = Vector.Zero, bottomRightClamp = Vector.Zero)`；缺失的 clamp
// 用零向量补齐（PC 的默认值就是 `Vector.Zero`）。
int RequireClampVectors(lua_State* state, int firstIndex, VectorHandle** topLeft,
                        VectorHandle** bottomRight) {
    static VectorHandle zero{0.0f, 0.0f};
    const int argumentCount = lua_gettop(state);
    *topLeft = &zero;
    *bottomRight = &zero;
    if (argumentCount >= firstIndex + 1 && !lua_isnoneornil(state, firstIndex + 1)) {
        *topLeft = CheckVector(state, firstIndex + 1);
    }
    if (argumentCount >= firstIndex + 2 && !lua_isnoneornil(state, firstIndex + 2)) {
        *bottomRight = CheckVector(state, firstIndex + 2);
    }
    return 0;
}


// --- libc++ 字符串桥（第二步） -------------------------------------------------
//
// `ANM2::Load` 与 `ReplaceSpritesheet` 收 libc++ 的 `std::string const&`：24 字节 SSO 对象
// （`__short{size:7, long:1, data[23]}` / `__long{...}`），而本模块编的是 libstdc++（32 字节）——
// 两者的内存布局不同，直接传我们的 string 会读错。
//
// 做法：全零的 24 字节在 libc++ 里是**合法的空短串**（long 标志为 0、size 为 0），所以先把缓冲
// 清零，再借游戏自己导入的 `basic_string::assign(char const*)`（PLT 桩，守卫见
// `kLibcxxStringAssignOffset`）把路径填进去。这样我们对布局的假设只剩"全零 = 空串"这一条。
//
// **按路径缓存、暂不释放**：`assign` 对超过 SSO 容量的长路径会在游戏侧堆上分配一块缓冲，而释放
// 它需要知道 libc++ `__long` 的数据指针偏移与 long 标志位 —— 那个布局我们还没有实测，猜错就是踩
// 内存。所以这里按路径复用同一个 24 字节对象：每个**不同**路径最多留一份缓冲（有界，通常几十份），
// 绝不做"猜布局去 free"。探针已经把测量这个布局列入待办（掩码位），实测出来后可以补上正规释放。
constexpr std::size_t kLibcxxStringSize = 24;
constexpr std::size_t kStringPathCapacity = 192;
constexpr std::size_t kStringCacheEntries = 32;

struct CachedNativeString {
    char path[kStringPathCapacity];
    alignas(8) unsigned char object[kLibcxxStringSize];
    bool used;
};
CachedNativeString g_nativeStrings[kStringCacheEntries]{};

// 长路径（不满足 SSO）时，`assign` 会在**游戏侧**堆上分配缓冲。释放它必须用**游戏自己的**
// `operator delete`：本模块（`subsdk9`）有自己的 newlib 堆，用本模块的 `free` 会踩坏堆。
// 布局是实测的（探针掩码位 17/18）：数据指针在对象偏移 `kLibcxxStringDataOffset`，首字最低位
// 为 1 表示 long。拿不到游戏 `operator delete` 桩时**宁可不释放**（缓存本身有界，最多 32 条）。
void ReleaseNativeString(unsigned char* object) noexcept {
    if (object == nullptr) {
        return;
    }
    const LuaRuntime::GameOperatorDeleteFn deallocate = LuaRuntime::GameOperatorDeleteThunk();
    if (deallocate == 0) {
        return;
    }
    // 两处取值都走访问层（批次 114）：这个字符串对象是**引擎的**分配器给的（下面 `deallocate`
    // 就是它的 `operator delete`），所以读的是引擎内存里的字段，不再用裸指针算术 + 转换。
    std::uint64_t headerWord = 0;
    if (!engine_memory::LoadVerifiedAt(engine_memory::AddressOf(object), 0, &headerWord) ||
        (headerWord & 1ULL) == 0) {
        return;  // 短串：内容内联在对象里，没有堆缓冲
    }
    std::uintptr_t bufferAddress = 0;
    if (!engine_memory::LoadVerifiedAt(engine_memory::AddressOf(object) + kLibcxxStringDataOffset, 0,
                                       &bufferAddress) ||
        bufferAddress == 0) {
        return;
    }
    void* data = engine_memory::AsObject(bufferAddress);
    deallocate(data);
    std::memset(object, 0, kLibcxxStringSize);  // 复位成"空短串"，避免留下悬垂指针
}

// 返回一块已填好该路径的 libc++ 字符串对象；失败（路径过长、缓存满、绑定缺失）返回 nullptr。
// 缓存满时**先释放最旧一条**再复用（原来是直接失败；这条路径在真实 Mod 会话里也可能被走到）。
//
// ★ `allowEmpty`（2026-09-12，真机报告 `01789225234` 定案）：**空串是合法参数，不是错误**。
//
// 真机证据：那两份报告的负载里，错误文本残留片段是
// `Sprite:ReplaceSpritesheet could not build a native file name string`——
// 也就是说 EID 调 `ReplaceSpritesheet(layer, "")` 时我们**抛错拒绝了**。而空串在 PC 上完全合法：
// EID 的 `loadCustomSprites`（`eid_api.lua:1360` 附近）先用空串把某一层的自定义图集清掉，
// 再用真实路径替换。我们这里一抛错，**整条描述构建被打断**（派发器静默摘除回调），
// 表现就是"进到道具范围内什么都不显示"。
//
// 所以把"空串"从失败条件里摘出来，由调用方按语义决定是否允许：
//   * `Sprite:ReplaceSpritesheet` —— 允许（空串 = 清除该层的替换）；
//   * `Sprite:Load` —— 不允许（加载一个空路径没有意义，PC 也会失败）。
// 全零的 24 字节在 libc++ 里就是合法的空短串，所以"允许空串"这条路径不需要额外构造。
std::size_t g_nativeStringCursor = 0;

void* BuildNativeString(const char* path, bool allowEmpty) {
    if (path == nullptr) {
        return nullptr;
    }
    const std::size_t length = std::strlen(path);
    if (length == 0 && !allowEmpty) {
        return nullptr;
    }
    if (length + 1 > kStringPathCapacity) {
        return nullptr;
    }
    const LuaRuntime::LibcxxStringAssignFn assign = LuaRuntime::LibcxxStringAssignThunk();
    if (assign == 0) {
        return nullptr;
    }
    for (CachedNativeString& entry : g_nativeStrings) {
        if (entry.used && std::strcmp(entry.path, path) == 0) {
            return entry.object;
        }
    }
    for (CachedNativeString& entry : g_nativeStrings) {
        if (entry.used) {
            continue;
        }
        std::memset(entry.object, 0, sizeof(entry.object));
        assign(entry.object, path);
        std::memcpy(entry.path, path, length + 1);
        entry.used = true;
        return entry.object;
    }
    // 缓存满：按游标释放一条最旧的（含它可能持有的长路径缓冲），然后复用这一格。
    CachedNativeString& victim = g_nativeStrings[g_nativeStringCursor];
    g_nativeStringCursor = (g_nativeStringCursor + 1) % kStringCacheEntries;
    ReleaseNativeString(victim.object);
    std::memset(victim.object, 0, sizeof(victim.object));
    assign(victim.object, path);
    std::memcpy(victim.path, path, length + 1);
    victim.used = true;
    return victim.object;
}

// --- `Sprite:ReplaceSpritesheet` 的探针（2026-09-12 第六轮）------------------------
//
// 真机连续两轮都停在这个函数上，而 `BuildNativeString` 的三条失败路径（`path == nullptr`、
// 路径过长、`assign` 绑定缺失）返回的都是 nullptr，光看"失败"分不清是哪条。
// 这里把调用时的**文件名长度**与**前 8 字节**记下来：
//   * 长度 = 0xFFFFFFFF ⇒ 传进来的根本不是字符串（`lua_tostring` 返回 nullptr）；
//   * 长度 > 191        ⇒ 路径超容量；
//   * 长度正常          ⇒ 前 8 字节应当是可读路径（例如 `resources`），据此排除"值是垃圾"。
std::atomic<std::uint32_t> g_ReplaceSpritesheetNameLength{0};
std::atomic<std::uint64_t> g_ReplaceSpritesheetNameHead{0};
std::atomic<std::uint32_t> g_ReplaceSpritesheetCalls{0};

void RecordSpriteReplaceSpritesheetForProbe(std::uint32_t length, const char* name) noexcept {
    (void)length;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)name;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_ReplaceSpritesheetCalls.fetch_add(1, std::memory_order_relaxed);
    g_ReplaceSpritesheetNameLength.store(length, std::memory_order_relaxed);
    std::uint64_t head = 0;
    if (name != nullptr) {
        const std::size_t take = length < 8 ? length : 8;
        if (take != 0) {
            std::memcpy(&head, name, take);
        }
    }
    g_ReplaceSpritesheetNameHead.store(head, std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}

// --- 批次 283：四条「按名字查询」共用的参数处理 ----------------------------------
//
// 这四条的引擎签名统一是 `bool ANM2::Xxx(std::string const&) const` ⇒ 参数必须是
// **libc++ 的 24 字节 `std::string` 对象**（`BuildNativeString` 交出来的正是它）。
// ★ 与 overlay 那三条的差别就在这里：那三条挑的是 `char const*` 重载，而这四条
//   **dynsym 里只有 `std::string const&` 这一份**，没有可选的重载 ⇒ 桥是必需的，不是可选的。
// ★ `allowEmpty = true`：空名字是合法输入（引擎会返回 `false`），**不抛错** —— 与
//   `ReplaceSpritesheet` 对空串的口径一致，避免把调用方那条回调整条打断。
//
// ★★ `argumentOptional`（`IsOverlayPlaying` / `IsOverlayFinished` 专用）：
//   PC 给这两条各写了**两个重载**（`tools/pc_contract_docs/Sprite.md` 第 133/135 行与
//   140/142 行）：`(string AnimationName)` 与 `()`。省参数该怎么落，**不是猜的** ——
//   引擎那条入口对**空名字**有专门分支，两条正好互补：
//     * `IsOverlayPlaying`  @`0xAC04`：名字为空 ⇒ `mov w0, #1`（有 overlay 在播就为真）；
//     * `IsOverlayFinished` @`0xACF0`：名字为空 ⇒ `mov w0, #1`（没有 overlay 在播就为真）。
//   ⇒ 省参数时传空串，语义就是 PC 那个无参重载「当前有没有 overlay 在播」。
//   ★ 与既有的 `IsPlaying` / `IsFinished` 是**同一条口径**（那条注释里写着"真实 Mod 有省参数的
//     写法"，我们曾因为拒掉省参数而误伤过一个真机诊断）。
template <typename ThunkType>
int SpriteNameBooleanQuery(lua_State* state, const char* apiName, bool argumentOptional,
                           ThunkType thunk) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, apiName, &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    if (argumentCount > 2 || (argumentCount == 2 && lua_type(state, 2) != LUA_TSTRING)) {
        return luaL_error(state, "%s accepts at most one name", apiName);
    }
    if (!argumentOptional && argumentCount != 2) {
        return luaL_error(state, "%s needs a name", apiName);
    }
    const auto method = thunk();
    if (method == 0) {
        return luaL_error(state, "%s native binding is unavailable", apiName);
    }
    const char* text = argumentCount == 2 ? lua_tostring(state, 2) : "";
    void* name = BuildNativeString(text, true);
    if (name == nullptr) {
        return luaL_error(state, "%s could not build a native name string", apiName);
    }
    lua_pushboolean(state, method(sprite, name) ? 1 : 0);
    return 1;
}

// --- Handlers --------------------------------------------------------------

int SpriteLoad(lua_State* state);
int SpriteLoadGraphics(lua_State* state);
int SpriteReplaceSpritesheet(lua_State* state);
int SpritePlay(lua_State* state);
int SpriteSetAnimation(lua_State* state);
int SpriteSetFrame(lua_State* state);
int SpriteGetFrame(lua_State* state);
int SpriteGetOverlayFrame(lua_State* state);
int SpriteSetLayerFrame(lua_State* state);
int SpriteGetLayerFrame(lua_State* state);
int SpriteUpdate(lua_State* state);
int SpriteIsPlaying(lua_State* state);
int SpriteIsFinished(lua_State* state);
int SpritePlayRandom(lua_State* state);
// 批次 279（2026-10-02）：overlay 三条（`PlayOverlay` 12 处 / `SetLastFrame` 6 处 / `SetOverlayFrame` 1 处）。
// ★ 三条都走 `char const*` 重载，所以落在这张「只收 char const*/数值」的绑定表里（不需要 std::string 桥）。
int SpritePlayOverlay(lua_State* state);
int SpriteSetLastFrame(lua_State* state);
int SpriteSetOverlayFrame(lua_State* state);
// ★ 批次 280 的三条函数**定义在匿名命名空间之外**（那个 `}  // namespace` 在第 1139 行，
//   而它们在第 1266 行往后）⇒ 声明必须放在 `sprite_api.hpp` 的命名空间作用域里，
//   与 `SpriteGetAnimation` 同一条处理（在匿名命名空间里再声明一遍只会变成"另一个函数"、
//   链接期报 `has internal linkage but is not defined`。本批真踩过一次）。
int SpriteRender(lua_State* state);
int SpriteRenderLayer(lua_State* state);
int SpriteGetTexel(lua_State* state);
// `SpriteGetAnimation` 的声明在 `sprite_api.hpp`（定义也在**命名空间**作用域，不在匿名命名空间
// 里），这里刻意不重复声明：在匿名命名空间里再写一遍会变成"另一个函数"，绑定表引用到的那个
// 符号就没有定义了。

constexpr LuaHandlerBinding kSpriteHandlers[] = {
    {0x0D01000E, &SpriteLoad},
    {0x0D01000F, &SpriteLoadGraphics},
    {0x0D010010, &SpriteReplaceSpritesheet},
    {0x0D010001, &SpritePlay},
    {0x0D010002, &SpriteSetAnimation},
    // PC 的 `SetFrame` 有两个重载：`(int)` 与 `(string, int)`。注册表是按**名字**挂的，
    // 所以这里只留一个入口，由它看参数类型分派（与 PC 绑定层的做法一致）。
    {0x0D010003, &SpriteSetFrame},
    {0x0D010004, &SpriteGetFrame},
    {0x0D010020, &SpriteGetOverlayFrame},
    {0x0D010005, &SpriteSetLayerFrame},
    {0x0D010006, &SpriteGetLayerFrame},
    {0x0D010007, &SpriteUpdate},
    {0x0D010008, &SpriteIsPlaying},
    {0x0D010009, &SpriteIsFinished},
    {0x0D01000A, &SpritePlayRandom},
    {0x0D01000B, &SpriteRender},
    {0x0D01000C, &SpriteRenderLayer},
    // `GetTexel` 用 0x12：0x0D 已被 `IsLoaded` 占用（第一版误用同一个 id，Catalog 的
    // "id 唯一" 校验立刻失败 —— 这个门禁正是为了拦这种手抄错误）。
    {0x0D010012, &SpriteGetTexel},
    {0x0D01000D, &SpriteIsLoaded},
    // 批次 5：`Sprite:GetAnimation()`（纯读 `ANM2+0x38`，没有引擎调用）。
    {0x0D010011, &SpriteGetAnimation},
    // 批次 214：中文版 MCM 的 `filepathhelper.lua` 要的三条（缺任一条都会打断调用方回调）。
    {0x0D010013, &SpriteReset},
    {0x0D010014, &SpriteGetLayerCount},
    {0x0D010015, &SpriteGetDefaultAnimationName},
    // 批次 279：overlay 三条（取号 = 域内下一个空号 0x16/0x17/0x18）。
    {0x0D010016, &SpritePlayOverlay},
    {0x0D010017, &SpriteSetLastFrame},
    {0x0D010018, &SpriteSetOverlayFrame},
    // 批次 280：`GetDefaultAnimation` / `Stop`（取号 = 域内下一个空号 0x19/0x1A）。
    {0x0D010019, &SpriteGetDefaultAnimation},
    {0x0D01001A, &SpriteStop},
    // 批次 283：四条「按名字查询」（取号 = 域内下一个空号 0x1B/0x1C/0x1D/0x1E）。
    // ★ 这四条走 libc++ `std::string` 桥（引擎没有 `char const*` 重载），与 `Load` 同一族。
    {0x0D01001B, &SpriteIsOverlayPlaying},
    {0x0D01001C, &SpriteIsOverlayFinished},
    {0x0D01001D, &SpriteIsEventTriggered},
    {0x0D01001E, &SpriteWasEventTriggered},
    // 批次 309（2026-10-03）：`Sprite:GetFilename()`（取号 = 域内下一个空号 0x1F）。
    {0x0D01001F, &SpriteGetFilename},
};

// PC: `void Load(string ANM2Path, boolean LoadGraphics)`；引擎侧是
// `Load(std::string const&, bool)`（x1 = 字符串对象、w2 = 加载图形）。
int SpriteLoad(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:Load", &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 2 || argumentCount > 3 || lua_type(state, 2) != LUA_TSTRING ||
        (argumentCount == 3 && lua_type(state, 3) != LUA_TBOOLEAN)) {
        return luaL_error(state, "Sprite:Load accepts a path and an optional loadGraphics flag");
    }
    const LuaRuntime::SpriteLoadFn method = LuaRuntime::SpriteLoadThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:Load native binding is unavailable");
    }
    // `Load` 不接受空路径（PC 亦然），所以 `allowEmpty = false`。
    void* nativeString = BuildNativeString(lua_tostring(state, 2), false);
    if (nativeString == nullptr) {
        return luaL_error(state,
                          "Sprite:Load could not build a native path string (missing binding, "
                          "empty path or path too long)");
    }
    method(sprite, nativeString,
           argumentCount == 3 && lua_toboolean(state, 3) != 0);
    return 0;
}

// PC: `void LoadGraphics()` —— 用已经 `Load` 过的数据把图形载入 GPU。
int SpriteLoadGraphics(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:LoadGraphics", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:LoadGraphics accepts no arguments");
    }
    const LuaRuntime::SpriteLoadGraphicsFn method = LuaRuntime::SpriteLoadGraphicsThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:LoadGraphics native binding is unavailable");
    }
    method(sprite);
    return 0;
}

// PC: `void ReplaceSpritesheet(int LayerId, string PngFilename)`；引擎侧
// `ReplaceSpritesheet(int, std::string const&)`（w1 = 层号、x2 = 字符串对象）。
int SpriteReplaceSpritesheet(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:ReplaceSpritesheet", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 3 || !isaac::runtime::IsIntegerArgument(state, 2) || lua_type(state, 3) != LUA_TSTRING) {
        return luaL_error(state, "Sprite:ReplaceSpritesheet accepts a layer id and a file name");
    }
    const LuaRuntime::SpriteReplaceSpritesheetFn method = LuaRuntime::SpriteReplaceSpritesheetThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:ReplaceSpritesheet native binding is unavailable");
    }
    // `allowEmpty = true`：空串表示"清掉这一层的图集替换"，是 EID 的正常用法（见上面
    // `BuildNativeString` 的注释与真机报告 `01789225234`）。
    const char* fileName = lua_tostring(state, 3);
    // 探针（2026-09-12 第六轮）：真机连续两轮都停在这里，而**失败原因分不清**
    // （`path == nullptr` / 路径过长 / assign 绑定缺失，三者都返回 nullptr）。
    // 把"哪一条"和"路径长度 + 前 8 字节"记下来，下一次报告就能直接判。
    if (fileName != nullptr) {
        const std::size_t fileNameLength = std::strlen(fileName);
        RecordSpriteReplaceSpritesheetForProbe(static_cast<std::uint32_t>(fileNameLength), fileName);
    } else {
        RecordSpriteReplaceSpritesheetForProbe(0xFFFFFFFFu, nullptr);
    }
    void* nativeString = BuildNativeString(fileName, true);
    if (nativeString == nullptr) {
        // 三条失败路径分别报错，报告里一眼可辨（不再只给一句笼统的话）。
        if (fileName == nullptr) {
            return luaL_error(state, "Sprite:ReplaceSpritesheet got a nil file name");
        }
        if (std::strlen(fileName) + 1 > kStringPathCapacity) {
            return luaL_error(state,
                              "Sprite:ReplaceSpritesheet file name is longer than %d bytes",
                              static_cast<int>(kStringPathCapacity - 1));
        }
        return luaL_error(state,
                          "Sprite:ReplaceSpritesheet native string binding is unavailable");
    }
    method(sprite, static_cast<int>(lua_tointeger(state, 2)),
           nativeString);
    return 0;
}

int SpritePlay(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:Play", &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 2 || argumentCount > 3 || lua_type(state, 2) != LUA_TSTRING ||
        (argumentCount == 3 && lua_type(state, 3) != LUA_TBOOLEAN)) {
        return luaL_error(state, "Sprite:Play accepts an animation name and an optional force flag");
    }
    const LuaRuntime::SpritePlayFn method = LuaRuntime::SpritePlayThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:Play native binding is unavailable");
    }
    method(sprite, lua_tostring(state, 2),
           argumentCount == 3 && lua_toboolean(state, 3) != 0);
    return 0;
}

int SpriteSetAnimation(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:SetAnimation", &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 2 || argumentCount > 3 || lua_type(state, 2) != LUA_TSTRING ||
        (argumentCount == 3 && lua_type(state, 3) != LUA_TBOOLEAN)) {
        return luaL_error(state,
                          "Sprite:SetAnimation accepts an animation name and an optional reset flag");
    }
    const LuaRuntime::SpriteSetAnimationFn method = LuaRuntime::SpriteSetAnimationThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:SetAnimation native binding is unavailable");
    }
    // PC: `boolean SetAnimation(string AnimationName, boolean Reset = true)`.
    const bool reset = argumentCount == 3 ? lua_toboolean(state, 3) != 0 : true;
    lua_pushboolean(state, method(sprite, lua_tostring(state, 2),
                                  reset) ? 1 : 0);
    return 1;
}

// `Sprite:PlayOverlay(string AnimationName, boolean Force)` —— PC 契约 `tools/pc_contract_docs/Sprite.md:236`，
// 语料 **12 处**（IsaacOnTwitchReloaded 的进度条用它轮流播 overlay 动画；两种形状都出现：
// `PlayOverlay("Anim0", false)` 与 `PlayOverlay("Anim" .. sector, true)`）。
//
// 引擎入口 `ANM2::PlayOverlay(char const*, bool)` @ `private:kSpritePlayOverlayOffset`。★ 同一族还有一个
// `PlayOverlay(std::string const&, bool)` @ `0xA9E4` —— 我们**选 `char const*` 那个**，
// 与这张绑定表既有的策略一致（第一步只收 `char const*`/数值，避开 libc++ `std::string` 的 ABI 桥）。
int SpritePlayOverlay(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:PlayOverlay", &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    if (argumentCount != 3 || lua_type(state, 2) != LUA_TSTRING ||
        lua_type(state, 3) != LUA_TBOOLEAN) {
        return luaL_error(state, "Sprite:PlayOverlay accepts an animation name and a force flag");
    }
    const LuaRuntime::SpritePlayOverlayFn method = LuaRuntime::SpritePlayOverlayThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:PlayOverlay native binding is unavailable");
    }
    method(sprite, lua_tostring(state, 2), lua_toboolean(state, 3) != 0);
    return 0;
}

// `Sprite:SetLastFrame()` —— 同页契约 `:376`，语料 6 处（把当前动画钉在最后一帧，常见于"播完就停"）。
// 引擎入口 `ANM2::SetLastFrame()` @ `private:kSpriteSetLastFrameOffset`（无参）。
int SpriteSetLastFrame(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:SetLastFrame", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:SetLastFrame accepts no arguments");
    }
    const LuaRuntime::SpriteSetLastFrameFn method = LuaRuntime::SpriteSetLastFrameThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:SetLastFrame native binding is unavailable");
    }
    method(sprite);
    return 0;
}

// `Sprite:SetOverlayFrame(string AnimationName, int FrameNum)` —— 同页契约 `:396`，语料 1 处。
// 引擎入口 `ANM2::SetOverlayFrame(char const*, int)` @ `0xAEF8`（同样避开 `std::string` 重载）。
// ★ 帧号用 `IntegerArgumentAt`（接受 `3.0` 这类整值浮点）—— 与 `Sprite:SetFrame` 同一条理由：
//   Lua 的 `/` 永远产生浮点，用"只认整数子类型"会比 PC 严（2026-09-18 真机踩过）。
int SpriteSetOverlayFrame(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:SetOverlayFrame", &sprite); error != 0) {
        return error;
    }
    lua_Integer frameNumber = 0;
    if (lua_gettop(state) != 3 || lua_type(state, 2) != LUA_TSTRING ||
        !isaac::runtime::IntegerArgumentAt(state, 3, &frameNumber)) {
        return luaL_error(state, "Sprite:SetOverlayFrame accepts an animation name and a frame number");
    }
    const LuaRuntime::SpriteSetOverlayFrameFn method = LuaRuntime::SpriteSetOverlayFrameThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:SetOverlayFrame native binding is unavailable");
    }
    method(sprite, lua_tostring(state, 2), static_cast<int>(frameNumber));
    return 0;
}


// `Sprite:SetFrame(int)` 与 `Sprite:SetFrame(string, int)` 是 PC 的一对重载：按第二个参数的
// 类型分派到各自的原生入口。
int SpriteSetFrame(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:SetFrame", &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    lua_Integer frameNumber = 0;
    // ★ 帧号用"整值数"判据而不是"只认整数子类型"那个判据：PC 的绑定走 `luaL_checkinteger`，
    // 它接受 `3.0` 这类整值浮点，而 Lua 的 `/` **永远**产生浮点 ⇒ 用"只认整数子类型"会比 PC 严，
    // 模组只要把帧号算过一次除法就会在我们这里报错（2026-09-18 真机：EID 渲染药丸描述时
    // 被这条拒掉，屏幕上"什么信息都没有"）。判据与理由见 `lua_integer_argument.hpp`。
    if (argumentCount == 2 && isaac::runtime::IntegerArgumentAt(state, 2, &frameNumber)) {
        const LuaRuntime::SpriteSetFrameFn method = LuaRuntime::SpriteSetFrameThunk();
        if (method == 0) {
            return luaL_error(state, "Sprite:SetFrame native binding is unavailable");
        }
        method(sprite, static_cast<int>(frameNumber));
        return 0;
    }
    if (argumentCount == 3 && lua_type(state, 2) == LUA_TSTRING &&
        isaac::runtime::IntegerArgumentAt(state, 3, &frameNumber)) {
        const LuaRuntime::SpriteSetFrameNamedFn method = LuaRuntime::SpriteSetFrameNamedThunk();
        if (method == 0) {
            return luaL_error(state, "Sprite:SetFrame native binding is unavailable");
        }
        method(sprite, lua_tostring(state, 2), static_cast<int>(frameNumber));
        return 0;
    }
    // 报错里带上**实际拿到的类型**：下一次真机读数就能一眼看出模组到底传了什么
    // （2026-09-18 就是靠"错误文本带类型"这条纪律省掉一轮猜测）。
    return luaL_error(state,
                      "Sprite:SetFrame accepts a frame number or an animation name and a frame "
                      "number (got %s, %s)",
                      argumentCount >= 2 ? luaL_typename(state, 2) : "nothing",
                      argumentCount >= 3 ? luaL_typename(state, 3) : "nothing");
}

using AgonyOverlayFrameFn = std::int32_t (*)(void*);
int SpriteGetOverlayFrame(lua_State* state) {
    void* sprite=nullptr;
    if (const int error=ResolveSprite(state,"Sprite:GetOverlayFrame",&sprite); error!=0) return error;
    const auto method=EngineOffsetAddress<IsEngineMemoryReadable>(kSpriteGetOverlayFrameOffset);
    if (method==0 || !engine_call::VerifyEntryBytes(method,kSpriteGetOverlayFrameExpectedBytes.data(),
        kSpriteGetOverlayFrameExpectedBytes.size(),&IsEngineMemoryReadable))
        return luaL_error(state,"Sprite:GetOverlayFrame native bindings are unavailable");
    lua_pushinteger(state,engine_call::AsFunction<AgonyOverlayFrameFn>(method)(sprite));
    return 1;
}

int SpriteGetFrame(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:GetFrame", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:GetFrame accepts no arguments");
    }
    const LuaRuntime::SpriteGetFrameFn method = LuaRuntime::SpriteGetFrameThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:GetFrame native binding is unavailable");
    }
    lua_pushinteger(state, method(sprite));
    return 1;
}

int SpriteSetLayerFrame(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:SetLayerFrame", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 3 || !isaac::runtime::IsIntegerArgument(state, 2) || !isaac::runtime::IsIntegerArgument(state, 3)) {
        return luaL_error(state, "Sprite:SetLayerFrame accepts a layer id and a frame number");
    }
    const LuaRuntime::SpriteSetLayerFrameFn method = LuaRuntime::SpriteSetLayerFrameThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:SetLayerFrame native binding is unavailable");
    }
    method(sprite, static_cast<int>(lua_tointeger(state, 2)),
           static_cast<int>(lua_tointeger(state, 3)));
    return 0;
}

int SpriteGetLayerFrame(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:GetLayerFrame", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Sprite:GetLayerFrame accepts a layer id");
    }
    const LuaRuntime::SpriteGetLayerFrameFn method = LuaRuntime::SpriteGetLayerFrameThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:GetLayerFrame native binding is unavailable");
    }
    lua_pushinteger(state,
                    method(sprite, static_cast<int>(lua_tointeger(state, 2))));
    return 1;
}

int SpriteUpdate(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:Update", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:Update accepts no arguments");
    }
    const LuaRuntime::SpriteUpdateFn method = LuaRuntime::SpriteUpdateThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:Update native binding is unavailable");
    }
    method(sprite);
    return 0;
}

// PC 文档里 `IsPlaying` / `IsFinished` 的形参个数是 **[0, 1]**（见
// `analysis/lua-api-inventory/inventory.json`：`符号形参 1 / 文档形参 [0, 1]`），动画名可省。
// 引擎的 `ANM2::IsPlaying(char const*)` / `IsFinished(char const*)`（`private:kSpriteIsPlayingOffset` / `private:kSpriteIsFinishedOffset`）
// 对**空字符串**的语义正是"只问当前动画"：
//   `IsPlaying`：当前动画为空 → false；`[+0x54]`（在播标志）为 0 → false；`*name == 0` → true。
// 所以省掉动画名时传空串，和 PC 行为一致。2026-09-13 真机上测试 Mod 调 `sprite:IsPlaying()`
// 被这里拒掉（错误指纹 49 = `Sprite:IsPlaying accepts an animation name`），既误伤真机诊断，
// 也是真实的兼容性缺口（真实 Mod 有省参数的写法）。
constexpr char kAnyAnimationName[] = "";

int SpriteIsPlaying(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:IsPlaying", &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    if (argumentCount > 2 || (argumentCount == 2 && lua_type(state, 2) != LUA_TSTRING)) {
        return luaL_error(state, "Sprite:IsPlaying accepts an optional animation name");
    }
    const LuaRuntime::SpriteIsPlayingFn method = LuaRuntime::SpriteIsPlayingThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:IsPlaying native binding is unavailable");
    }
    const char* name = argumentCount == 2 ? lua_tostring(state, 2) : kAnyAnimationName;
    lua_pushboolean(state, method(sprite, name) ? 1 : 0);
    return 1;
}

int SpriteIsFinished(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:IsFinished", &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    if (argumentCount > 2 || (argumentCount == 2 && lua_type(state, 2) != LUA_TSTRING)) {
        return luaL_error(state, "Sprite:IsFinished accepts an optional animation name");
    }
    const LuaRuntime::SpriteIsFinishedFn method = LuaRuntime::SpriteIsFinishedThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:IsFinished native binding is unavailable");
    }
    const char* name = argumentCount == 2 ? lua_tostring(state, 2) : kAnyAnimationName;
    lua_pushboolean(state, method(sprite, name) ? 1 : 0);
    return 1;
}

int SpritePlayRandom(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:PlayRandom", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 2 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Sprite:PlayRandom accepts a seed");
    }
    const LuaRuntime::SpritePlayRandomFn method = LuaRuntime::SpritePlayRandomThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:PlayRandom native binding is unavailable");
    }
    method(
        sprite, static_cast<unsigned int>(lua_tointeger(state, 2)));
    return 0;
}

// PC: `void Render(Vector Position, Vector TopLeftClamp = Vector.Zero,
//                 Vector BottomRightClamp = Vector.Zero)`。
// 引擎侧的原型是三个 `Vector2 const&`，按引用传我们的 8 字节值类型正是它期望的形式。
int SpriteRender(lua_State* state) {
    RecordApiSequence(48U);
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:Render", &sprite); error != 0) {
        return error;
    }
    auto* handle = static_cast<SpriteHandle*>(luaL_checkudata(state, 1, kSpriteMetatable));
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 2 || argumentCount > 4) {
        return luaL_error(state, "Sprite:Render accepts a position and optional clamps");
    }
    VectorHandle* position = CheckVector(state, 2);
    VectorHandle* topLeft = nullptr;
    VectorHandle* bottomRight = nullptr;
    static_cast<void>(RequireClampVectors(state, 2, &topLeft, &bottomRight));
    const LuaRuntime::SpriteRenderFn method = LuaRuntime::SpriteRenderThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:Render native binding is unavailable");
    }
    // 绘制前先把 Mod 写的 Scale/Color/FlipX 交给应用入口（设备侧目前是空操作，
    // 见 `ApplyCachedSpriteProperties` 的注释）。
    ObserveSpriteProperties(sprite, handle);
    method(sprite, position, topLeft, bottomRight);
    return 0;
}

// `Sprite:GetTexel(Vector SamplePos, Vector RenderPos, float AlphaThreshold, int LayerID = 0)`
//
// **为什么必须有这个名字**：EID 的 `IsAltChoice`（`main.lua:230-231`）用它逐像素比对
// "赎罪线问号底座"与目标底座的贴图 ——
//   `local qcolor = questionMarkSprite:GetTexel(Vector(i,j), nullVector, 1, 1)`
// 方法不存在时那一句是 "attempt to call a nil value"，整条回调在宝箱房里每帧报错、被派发器摘除。
//
// **2026-09-12 起改成真实读数**（此前是"恒返回不透明白色"的占位）：
// 占位让 EID 在**每一个**采样点上都得到"两个 sprite 一模一样"，于是它把**每个**底座道具
// 都当成"赎罪线红问号底座" → 走"隐瞒"那一支：只画那个小红问号、不写名字与效果。
// 这与真机现象（宝箱房底座道具只有问号、没有描述）逐字对上。
//
// 实现方式：**直接调引擎自己的 `ANM2::GetTexel`**（`kSpriteGetTexelOffset`），而不是自己去遍历
// `ANM2 → LayerState → SpriteSheet → ImageBase` 的像素链 —— 用游戏自己的答案回答游戏自己的问题。
//
// **调用约定（本轮唯一有风险的地方）**：AAPCS64 的 HFA 规则把两个 `KAGE::Math::Vector2`
// （各 2 个 float）放进 `s0..s3`，`float alphaThreshold` 进 `s4`，`int layerId` 进 `w1`；
// 返回值是 16 字节 `KColor`，走 **x8 间接结果寄存器**。证据：
// `analysis/stage150-sprite-abi/<build>.json` 的 `records.sprite_get_texel`
// （`confidence = verified`：符号、16 字节守卫、ABI 三重核对）。
// 2026-10-20 更正：用按值 HFA 和非平凡 Color 返回类型让编译器遵守 ABI，
// 完整追踪调用者保存寄存器，替代遗漏 clobber 的旧内联汇编。
// 状态是内嵌对象；无动画交给原生返回透明色，入口缺失或对象不可读则明确报错。
int SpriteGetTexel(lua_State* state) {
    RecordApiSequence(50U);
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:GetTexel", &sprite); error != 0) {
        return error;
    }
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 2 || argumentCount > 5) {
        return luaL_error(state, "Sprite:GetTexel accepts a sample position with optional "
                                 "render position, alpha threshold and layer id");
    }
    const VectorHandle* samplePos = CheckVector(state, 2);
    // PC 的默认值：`RenderPos = Vector.Zero`、`AlphaThreshold = 0`、`LayerID = 0`。
    // EID 传的 `nullVector` 正是零向量、阈值 1、层号 1（写死，不依赖默认值）。
    const VectorHandle defaultZero{0.0F, 0.0F};
    const VectorHandle* renderPos = argumentCount >= 3 ? CheckVector(state, 3) : &defaultZero;
    float alphaThreshold = 0.0F;
    if (argumentCount >= 4) {
        if (!lua_isnumber(state, 4)) {
            return luaL_error(state, "Sprite:GetTexel expects a number as the alpha threshold");
        }
        alphaThreshold = static_cast<float>(lua_tonumber(state, 4));
    }
    int layerId = 0;
    if (argumentCount >= 5) {
        if (!isaac::runtime::IsIntegerArgument(state, 5)) {
            return luaL_error(state, "Sprite:GetTexel expects an integer layer id");
        }
        layerId = static_cast<int>(lua_tointeger(state, 5));
    }

    const LuaRuntime::SpriteGetTexelFn method = LuaRuntime::SpriteGetTexelThunk();
    if (method == nullptr) {
        return SpriteTexelError(state, 1U, "native entry is unavailable");
    }
    // +0x60 overlay 与 +0x30 base 均是内嵌 AnimationState，不是待解引用指针。
    // 整个 ANM2 必须可读；动画有无由原生 state+8 判断，不能拦截合法空动画。
    const std::uintptr_t spriteAddress = engine_memory::AddressOf(sprite);
    if (!IsEngineMemoryReadable(spriteAddress, kSpriteObjectSize)) {
        return SpriteTexelError(state, 2U, "sprite object is unreadable");
    }
    const auto color = method(sprite, {samplePos->x, samplePos->y},
                              {renderPos->x, renderPos->y}, alphaThreshold, layerId);
    RecordSpriteGetTexelForProbe(color.red, color.green, true);
    auto* handle = static_cast<ColorHandle*>(lua_newuserdata(state, sizeof(ColorHandle)));
    *handle = {};
    handle->red = color.red;
    handle->green = color.green;
    handle->blue = color.blue;
    handle->alpha = color.alpha;
    handle->offsetRed = 0.0F;
    handle->offsetGreen = 0.0F;
    handle->offsetBlue = 0.0F;
    luaL_getmetatable(state, kColorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// PC: `void RenderLayer(int LayerId, Vector Position, Vector TopLeftClamp = Vector.Zero,
//                       Vector BottomRightClamp = Vector.Zero)`。
// 引擎侧 `RenderLayer(int, Vector2 const&, Vector2 const&, Vector2 const&)`：`w1` 是层号，
// 后面三个 `Vector2 const&` 走 x2/x3/x4。
int SpriteRenderLayer(lua_State* state) {
    RecordApiSequence(49U);
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:RenderLayer", &sprite); error != 0) {
        return error;
    }
    auto* handle = static_cast<SpriteHandle*>(luaL_checkudata(state, 1, kSpriteMetatable));
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 3 || argumentCount > 5 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state,
                          "Sprite:RenderLayer accepts a layer id, a position and optional clamps");
    }
    const int layerId = static_cast<int>(lua_tointeger(state, 2));
    VectorHandle* position = CheckVector(state, 3);
    VectorHandle* topLeft = nullptr;
    VectorHandle* bottomRight = nullptr;
    static_cast<void>(RequireClampVectors(state, 3, &topLeft, &bottomRight));
    const LuaRuntime::SpriteRenderLayerFn method = LuaRuntime::SpriteRenderLayerThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:RenderLayer native binding is unavailable");
    }
    // 与 `Sprite:Render` 同一步：绘制前把 Mod 写的三个属性交给应用入口。
    ObserveSpriteProperties(sprite, handle);
    method(sprite, layerId, position, topLeft, bottomRight);
    return 0;
}

}  // namespace

// --- 批次 283（2026-10-02）：`Sprite` 的四条「按名字查询」-------------------------------
//
// 引擎入口都在 `ANM2` 上，签名统一 `bool ANM2::Xxx(std::string const&) const`。
// ★ 这四条以前在 `BOIStageAPI15` 里报 `attempt to call a nil value`（共 6 处）。
//   它们的**接收者早就有**（`Sprite` 句柄与元表都在），缺的只是引擎入口本身 + libc++ 字符串那一跳。
//
// ★★ `IsOverlayPlaying` / `IsOverlayFinished` 与 `IsEventTriggered` / `WasEventTriggered`
//   是**两对孪生函数**，前 16 字节守卫两两**逐字节完全相同**。证据链、以及"凭什么说它们是
//   两个不同的函数"写在 `runtime_constants.hpp` 那一批常量上方 —— **那一段必须留着**：
//   不留的话，后来者只看守卫会以为这里配错了（两条一样的守卫指向两个不同偏移）。
int SpriteIsOverlayPlaying(lua_State* state) {
    // 省参数 = PC 的 `IsOverlayPlaying()` 重载（空名字 ⇒ 引擎在 `0xAC04` 直接给 true）。
    return SpriteNameBooleanQuery(state, "Sprite:IsOverlayPlaying", true,
                                  &LuaRuntime::SpriteIsOverlayPlayingThunk);
}

int SpriteIsOverlayFinished(lua_State* state) {
    return SpriteNameBooleanQuery(state, "Sprite:IsOverlayFinished", true,
                                  &LuaRuntime::SpriteIsOverlayFinishedThunk);
}

int SpriteIsEventTriggered(lua_State* state) {
    // ★ 这一条 PC **没有**无参重载（`Sprite.md` 只有 115 行那一份）⇒ 参数必给。
    return SpriteNameBooleanQuery(state, "Sprite:IsEventTriggered", false,
                                  &LuaRuntime::SpriteIsEventTriggeredThunk);
}

int SpriteWasEventTriggered(lua_State* state) {
    // ★ 同 `IsEventTriggered`：PC 只有 418 行那一份，没有无参重载。
    return SpriteNameBooleanQuery(state, "Sprite:WasEventTriggered", false,
                                  &LuaRuntime::SpriteWasEventTriggeredThunk);
}

int SpriteIsLoaded(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:IsLoaded", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:IsLoaded accepts no arguments");
    }
    // 引擎自己的"图形已加载"标志（`ANM2+0x149`）：不发明状态，直接读它。
    //
    // 走 `ReadEngine`（先确认可读）而不是裸解引用：引擎实体来源的 sprite 只要实体还在就必然
    // 可读，但"读不到"必须降级成 `false` 而不是崩在一条只读访问器里。
    std::uint8_t flag = 0;
    if (!ReadEngine(engine_memory::AddressOf(sprite) + kSpriteLoadedFlagOffset, &flag)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    lua_pushboolean(state, flag != 0 ? 1 : 0);
    return 1;
}

// `Entity:GetSprite()` 的句柄（批次 5）。调用方（`isaac_api.cpp` 的 `EntityGetSprite`）已经
// 用 `ValidatedEntity` 校验过 `entity`，这里只负责建句柄 + 打上**非拥有**标记。
int PushEngineEntitySpriteHandle(lua_State* state, void* entity) {
    if (entity == nullptr) {
        return luaL_error(state, "Entity:GetSprite requires a live entity");
    }
    auto* token=PushEntityLifetimeToken(state,engine_memory::AddressOf(entity));
    const int tokenIndex=lua_gettop(state);
    auto* handle = static_cast<SpriteHandle*>(lua_newuserdata(state, sizeof(SpriteHandle)));
    handle->lifetime=token;
    lua_pushvalue(state,tokenIndex);lua_setuservalue(state,-2);
    handle->sprite = engine_memory::AsObject(engine_memory::AddressOf(entity) +
                                             kEntitySpriteOffset);
    handle->owner = entity;
    handle->source = kSpriteSourceEngineEntity;
    // 三个缓存属性的初值与 PC 的对象默认值一致（与 `CreateSpriteHandle` 同一套理由）。
    handle->scaleX = 1.0F;
    handle->scaleY = 1.0F;
    handle->colorRed = 1.0F;
    handle->colorGreen = 1.0F;
    handle->colorBlue = 1.0F;
    handle->colorAlpha = 1.0F;
    handle->flipX = 0;
    handle->hasScale = 0;
    handle->hasColor = 0;
    handle->hasFlipX = 0;
    luaL_getmetatable(state, kSpriteMetatable);
    lua_setmetatable(state, -2);
    lua_remove(state,tokenIndex);
    return 1;
}

// `GridEntity:GetSprite()` / `GridEntityRock:GetSprite()` 的句柄（批次 298）。
// 与 `PushEngineEntitySpriteHandle` **逐字同形**，只有两处不同：
//   * `kGridEntitySpriteOffset`（`0x48`，网格实体的内嵌 ANM2）；
//   * `kSpriteSourceEngineGridEntity`（`ResolveSpriteObject` 据此换用网格实体的存活判据）。
// ★ 调用方（`remaining_api.cpp` 的 `GridEntityGetSprite`）已经用 `IsLiveGridEntityPointer`
//   校验过句柄。
int PushEngineGridEntitySpriteHandle(lua_State* state, void* gridEntity) {
    if (gridEntity == nullptr) {
        return luaL_error(state, "GridEntity:GetSprite requires a live grid entity");
    }
    auto* handle = static_cast<SpriteHandle*>(lua_newuserdata(state, sizeof(SpriteHandle)));
    handle->lifetime=nullptr;
    handle->sprite = engine_memory::AsObject(engine_memory::AddressOf(gridEntity) +
                                             kGridEntitySpriteOffset);
    handle->owner = gridEntity;
    handle->source = kSpriteSourceEngineGridEntity;
    // 三个缓存属性的初值与 `Entity:GetSprite()` / `Sprite()` 同一套（PC 的对象默认值）。
    handle->scaleX = 1.0F;
    handle->scaleY = 1.0F;
    handle->colorRed = 1.0F;
    handle->colorGreen = 1.0F;
    handle->colorBlue = 1.0F;
    handle->colorAlpha = 1.0F;
    handle->flipX = 0;
    handle->hasScale = 0;
    handle->hasColor = 0;
    handle->hasFlipX = 0;
    luaL_getmetatable(state, kSpriteMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int CreateSpriteHandle(lua_State* state) {
    // Lua5.3关闭时不再终结__gc新建的对象，必须在申请原生所有者之前拒绝。
    if (LuaRuntime::ClosingForModReload()) {
        return luaL_error(state, "Sprite cannot allocate native resources during mod reload shutdown");
    }
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Sprite accepts no arguments");
    }
    const LuaRuntime::SpriteCtorFn ctor = LuaRuntime::SpriteCtorThunk();
    const LuaRuntime::SpriteDestructorFn destructorMethod = LuaRuntime::SpriteDestructorThunk();
    if (ctor == 0 || destructorMethod == 0) {
        return luaL_error(state, "Sprite native binding is unavailable");
    }
    auto* handle = static_cast<SpriteHandle*>(lua_newuserdata(state, sizeof(SpriteHandle)));
    handle->lifetime=nullptr;
    handle->sprite = nullptr;
    // 三个缓存属性的初值与 PC 的对象默认值一致：Scale = (1,1)、Color = 白、
    // FlipX = false。`has*` 标志只用来区分"Mod 写过"与"没写过"（`__index` 据此决定
    // 是否返回缓存；两者取值相同，所以即使 Mod 从不写，读到的也是 PC 的默认形状）。
    handle->scaleX = 1.0F;
    handle->scaleY = 1.0F;
    handle->colorRed = 1.0F;
    handle->colorGreen = 1.0F;
    handle->colorBlue = 1.0F;
    handle->colorAlpha = 1.0F;
    handle->flipX = 0;
    handle->hasScale = 0;
    handle->hasColor = 0;
    handle->hasFlipX = 0;
    void* sprite = AllocateSpriteStorage();
    if (sprite == nullptr) {
        return luaL_error(state, "Sprite could not allocate its native object");
    }
    ctor(sprite);
    handle->sprite = sprite;
    // Lua 的 `Sprite()` 建出来的对象由**本模块**拥有：`__gc` 会析构并释放它。
    handle->owner = nullptr;
    handle->source = kSpriteSourceRuntimeOwned;
    luaL_getmetatable(state, kSpriteMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// PC 的 `Sprite:GetAnimation()`：**纯读**，不调引擎。
//
// 读的是 `ANM2+0x38`（指向当前动画名的 libc++ `std::string`），证据 = 引擎自己的
// `ANM2::IsPlaying(char const*)` 就是这么读的（`runtime_constants.hpp` 的
// `kSpriteAnimationNameOffset`）。没有当前动画（指针为 0）或读不到时返回**空串**：
// PC 的返回类型是 string，nil 会让 Mod 的 `name ~= "Idle"` 比较直接报
// "attempt to compare nil with string"；空串与两者都不相等，走的正是 EID 的"不隐藏描述"分支。
int SpriteGetAnimation(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:GetAnimation", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:GetAnimation accepts no arguments");
    }
    std::array<char, kAnimationNameCapacity> name{};
    if (!ReadAnimationName(engine_memory::AddressOf(sprite), name.data(), name.size())) {
        lua_pushliteral(state, "");
        return 1;
    }
    lua_pushstring(state, name.data());
    return 1;
}

// `Sprite:GetFilename()` —— 契约 `tools/pc_contract_docs/Sprite.md:68/70`
// （`#### string GetFilename ( )`；同页 `:79` 的例子逐字给出返回值形如 `gfx/001.000_Player.anm2`）。
//
// ★★ **它就是一个字段读**：文件名住在 `Sprite + kSpriteFilenameOffset`（`+0x08`）那个
//    libc++ `std::string` 里 —— 两处具名证据见 `runtime_constants.hpp` 的同名常量段：
//      ① `Sprite::LoadAnimationsFile(char const*, char const*) @ 0x4A48B4`：`add x0, x0, #0x8`
//         + `bl std::string::assign(char const*)` ⇒ 传进来的路径**整串**落在 `+0x08`；
//      ② 构造函数 `Sprite::Sprite() @ 0x4A4658` 的 `stp x8, xzr, [x0]` 把 `+0x08` 清成空串。
// ★ 读法**复用**本文件里唯一那份 `ReadLibcxxStringAt`（libc++ SSO 口径只有一份），
//   不另抄一遍短串/长串的判断。
//
// ★★ **读不到 / 没加载过 ⇒ 返回空串 `""`，不是 nil**：PC 的返回类型是 `string`，而语料里
//   `customgrids.lua:547` 正是拿 `sprite:GetFilename() == ""` 判"这个 Sprite 还没加载"、
//   `callbacks.lua:292` 拿它当**字典键**（`t[nil]` 会直接报错 ⇒ 整条回调被摘掉）。
//   这与 `Sprite:GetAnimation()` 的降级口径**逐条相同**。
// ★ 2026-10-23更正：前述+8来自不同Sprite类；Lua Sprite是ANM2，文件名在+0。
// 复用同一SSO读取，无新缓存；依据ANM2::Load0xC9C4以及短/长串真机原生布局。
int SpriteGetFilename(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:GetFilename", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:GetFilename accepts no arguments");
    }
    std::array<char, kFilenameCapacity> name{};
    if (!ReadLibcxxStringAt(engine_memory::AddressOf(sprite) + kSpriteFilenameOffset, name.data(),
                            name.size())) {
        lua_pushliteral(state, "");
        return 1;
    }
    lua_pushstring(state, name.data());
    return 1;
}

int SpriteGetDefaultAnimationName(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:GetDefaultAnimationName", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:GetDefaultAnimationName accepts no arguments");
    }
    PushSpriteDefaultAnimationName(state, sprite);
    return 1;
}

// `Sprite:GetDefaultAnimation()` —— PC 契约 `Sprite.md:36`，语料 **5 处**。
// ★ 契约页在 `GetDefaultAnimationName` 那段里明说两者"seems to be the same"
//   （原文见上面那个助手的注释）⇒ 这里**转调同一份读法**，不另写一遍。
int SpriteGetDefaultAnimation(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:GetDefaultAnimation", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:GetDefaultAnimation accepts no arguments");
    }
    PushSpriteDefaultAnimationName(state, sprite);
    return 1;
}

// `Sprite:Stop()` —— PC 契约 `Sprite.md:406`，语料 1 处。
// 引擎入口 `ANM2::Stop()` @ `private:kSpriteStopOffset`（无参）。同族的 overlay 停下是另一个入口
// （`ANM2::StopOverlay()` @ `0xABA8`，本批不收 —— 它不在待办清单里）。
int SpriteStop(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:Stop", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:Stop accepts no arguments");
    }
    const LuaRuntime::SpriteStopFn method = LuaRuntime::SpriteStopThunk();
    if (method == 0) {
        return luaL_error(state, "Sprite:Stop native binding is unavailable");
    }
    method(sprite);
    return 0;
}

// ---------------------------------------------------------------------------
// 批次 214（2026-09-30）：中文版 MCM（`!!Mod Config Menu Chinese`，工坊 2494192799）要用的三条
// ---------------------------------------------------------------------------
//
// 它新增的 `scripts/filepathhelper.lua` 用这三条判断"这条路径是不是一个真 anm2"
// （`anm2Tester:GetDefaultAnimationName() ~= "" or anm2Tester:GetLayerCount() > 0`，
//  紧接着 `anm2Tester:Reset()`）——它靠这个给**中文字体**找资源路径。
// ★ 那三行**不在 `pcall` 里**（只有 `Load` 被包着）⇒ 缺任何一条都会抛错、把调用方整条回调打断
//   （症状与"菜单画不出来"完全一样）。所以这三条必须齐。
//
// ★ 这三条 PC 的**文档里没有**（`mod_api_gap_report` 报 `PC 状态=unknown`）——
//   它们是 **REPENTOGON** 一侧的 API。语义按引擎自己的实现取证（见各条注释）。

// `Sprite:Reset()` = 原版ANM2::Reset @0x65B8；旧0x4A4724属于不同的Sprite类。
int SpriteReset(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:Reset", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:Reset accepts no arguments");
    }
    const LuaRuntime::SpriteResetFn reset = LuaRuntime::SpriteResetThunk();
    if (reset == nullptr) {
        // 缺少真实入口不能冒充已重置；与其它Sprite方法一致返回明确Lua错误。
        return luaL_error(state,"Sprite:Reset native binding is unavailable");
    }
    reset(sprite);
    return 0;
}

// `Sprite:GetLayerCount()` —— 引擎自己判 layer 越界时读的那一格（`ANM2+0xB0`）：
// `ANM2::GetLayerFrame @private:kSpriteGetLayerFrameOffset` 就是 `ldr x9,[x19,#0x30]`（Sprite 里的 ANM2 指针）
// 再 `ldr w9,[x9,#0xb0]` 与 layer 比较。没有 ANM2（没 Load 过）⇒ 0。
int SpriteGetLayerCount(lua_State* state) {
    void* sprite = nullptr;
    if (const int error = ResolveSprite(state, "Sprite:GetLayerCount", &sprite); error != 0) {
        return error;
    }
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Sprite:GetLayerCount accepts no arguments");
    }
    const std::uintptr_t base = engine_memory::AddressOf(sprite);
    std::uintptr_t anm2 = 0;
    std::uint32_t layers = 0;
    if (!ReadEngine(base + kSpriteAnm2Offset, &anm2) || anm2 == 0 ||
        !ReadEngine(anm2 + kAnim2LayerCountOffset, &layers)) {
        lua_pushinteger(state, 0);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(layers));
    return 1;
}

// `Sprite:GetDefaultAnimationName()` —— REPENTOGON 语义：ANM2 的"默认动画"名字。
// ★ 引擎里**没有**这条函数，也没有专门的"默认动画名"字段可用（`ANM2::SetAnimation` 找不到名字时
//   只打日志、不回落）⇒ 我们按**动画表里第一条**（`ANM2+0x98` 数组、`+0xA0` 个数、步长 `0x150`，
//   名字是该记录开头那个 libc++ `std::string`）回答，并在偏离台账里写明这条口径。
//   对调用方（`filepathhelper` 只判"非空"）来说两者等价：能 Load 出动画表就非空。
//: 读"当前 anm2 的默认动画名"（= 动画表**第一条**的名字）。批次 280 抽出来共用：
//: 契约页 `Sprite.md:54-56` 在 `GetDefaultAnimationName` 下面直接写着
//: 「Returns the `DefaultAnimation` value from the currently loaded anm2 file.」
//: 「This function seems to be the same as `GetDefaultAnimation()`.」
//: ⇒ `Sprite:GetDefaultAnimation()` 与它**是同一件东西**，两处必须用同一份读法（否则日后会漂开）。
void PushSpriteDefaultAnimationName(lua_State* state, void* sprite) {
    const std::uintptr_t base = engine_memory::AddressOf(sprite);
    std::array<char, kAnimationNameCapacity> name{};
    // 2026-10-15：上方“默认=第一条”的旧推断已被Load2/Preload2和真机读数否定。
    // 原字段保留XML声明值；直接读取，不重读资源，也不受Play/SetFrame改变当前动画影响。
    if (base == 0 || !ReadLibcxxStringAt(base + kSpriteDefaultAnimationNameOffset,
                                      name.data(), name.size())) {
        lua_pushliteral(state, "");
        return;
    }
    lua_pushstring(state, name.data());
    return;
}

// 439 更正：属性读取原生对象；下方保留的PushCached命名是历史名称。
// `__index`：先读取三个属性，再落到元表 `__methods` 里的方法（与 `Vector` 同一形态：
// `__index` 必须是函数才能同时服务字段与方法）。
void* TryResolveSpriteArgument(lua_State* state,int index) noexcept {
    auto* handle=static_cast<SpriteHandle*>(luaL_testudata(state,index,kSpriteMetatable));
    if (!handle || lua_rawlen(state,index)<sizeof(SpriteHandle)) return nullptr;
    void* sprite=ResolveSpriteObject(handle);
    return sprite && IsEngineMemoryReadable(engine_memory::AddressOf(sprite),kSpriteObjectSize)?sprite:nullptr;
}

void* ResolveSpriteArgument(lua_State* state,int index) {
    auto* handle=static_cast<SpriteHandle*>(luaL_checkudata(state,index,kSpriteMetatable));
    void* sprite=ResolveSpriteObject(handle);
    if(!sprite)luaL_error(state,"Sprite reference is no longer available");
    return sprite;
}

int SpriteIndex(lua_State* state) {
    auto* handle = static_cast<SpriteHandle*>(luaL_checkudata(state, 1, kSpriteMetatable));
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    const char* field = lua_tostring(state, 2);
    if(const int pushed=TryPushExtendedSpriteField(state,field))return pushed;
    if(std::strcmp(field,"PlaybackSpeed")==0) {
        void* sprite=ResolveSpriteObject(handle);float value{};
        if(!sprite || !ReadEngine(engine_memory::AddressOf(sprite)+kSpritePlaybackSpeedOffset,&value))
            return luaL_error(state,"Sprite.PlaybackSpeed requires a readable live sprite");
        lua_pushnumber(state,value);return 1;
    }
    if (std::strcmp(field, kSpriteScaleField) == 0) {
        PushCachedScale(state, handle);
        return 1;
    }
    if (std::strcmp(field, kSpriteColorField) == 0) {
        PushCachedColor(state, handle);
        return 1;
    }
    if (std::strcmp(field, kSpriteFlipXField) == 0) {
        void* sprite = ResolveSpriteObject(handle);
        std::uint8_t value = 0;
        if (sprite == nullptr || !ReadEngine(engine_memory::AddressOf(sprite) +
                                             kSpriteFlipXOffset, &value)) {
            return luaL_error(state, "Sprite.FlipX requires a readable live sprite");
        }
        lua_pushboolean(state, value != 0);
        return 1;
    }
    if (luaL_getmetatable(state, kSpriteMetatable) != LUA_TTABLE) {
        lua_pushnil(state);
        return 1;
    }
    lua_getfield(state, -1, "__methods");
    lua_remove(state, -2);
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_pushnil(state);
        return 1;
    }
    lua_getfield(state, -1, field);
    lua_remove(state, -2);
    return 1;
}

// `__newindex`：三个可写属性（大小写与 PC 一致）。
//
// 类型不对时**报错**（与 `Vector.X`/`KColor.Red` 一致）：把 `sprite.FlipX = 1` 这种写法
// 静默接受会让 Mod 的笔误变成"看起来生效了其实没有"。未知字段名同样报错 —— 这一批只承诺
// PC 的这三个属性，多接受一个没实现的名字等于撒谎。
int SpriteNewIndex(lua_State* state) {
    auto* handle = static_cast<SpriteHandle*>(luaL_checkudata(state, 1, kSpriteMetatable));
    if (lua_type(state, 2) != LUA_TSTRING) {
        return luaL_error(state, "Sprite fields are Scale, Color and FlipX");
    }
    const char* field = lua_tostring(state, 2);
    if(TryWriteExtendedSpriteField(state,field))return 0;
    if(std::strcmp(field,"PlaybackSpeed")==0) {
        const float value=static_cast<float>(luaL_checknumber(state,3));
        void* sprite=ResolveSpriteObject(handle);
        if(!sprite || !WriteEngine(engine_memory::AddressOf(sprite)+kSpritePlaybackSpeedOffset,value))
            return luaL_error(state,"Sprite.PlaybackSpeed requires a writable live sprite");
        return 0;
    }
    if (std::strcmp(field, kSpriteScaleField) == 0) {
        float x = 0.0F;
        float y = 0.0F;
        if (!ReadVectorPair(state, 3, &x, &y)) {
            return luaL_error(state, "Sprite.Scale must be a Vector");
        }
        handle->scaleX = x;
        handle->scaleY = y;
        handle->hasScale = 1;
        if (!ApplyCachedSpriteProperties(ResolveSpriteObject(handle), handle,
                                          SpriteProperty::Scale)) {
            return luaL_error(state, "Sprite.Scale requires a writable live sprite");
        }
        return 0;
    }
    if (std::strcmp(field, kSpriteColorField) == 0) {
        auto* color = TryColorArgument(state, 3);
        if (color == nullptr) {
            return luaL_error(state, "Sprite.Color must be a KColor");
        }
        handle->colorRed = color->red;
        handle->colorGreen = color->green;
        handle->colorBlue = color->blue;
        handle->colorAlpha = color->alpha;
        handle->colorOffsetRed = color->offsetRed;
        handle->colorOffsetGreen = color->offsetGreen;
        handle->colorOffsetBlue = color->offsetBlue;
        handle->hasColor = 1;
        void* sprite=ResolveSpriteObject(handle);
        if (!sprite || !WriteEngine(engine_memory::AddressOf(sprite)+kSpriteColorOffset,
                                   EngineColorModFromHandle(*color))) {
            return luaL_error(state, "Sprite.Color requires a writable live sprite");
        }
        return 0;
    }
    if (std::strcmp(field, kSpriteFlipXField) == 0) {
        if (lua_type(state, 3) != LUA_TBOOLEAN) {
            return luaL_error(state, "Sprite.FlipX must be a boolean");
        }
        handle->flipX = lua_toboolean(state, 3) != 0 ? 1 : 0;
        handle->hasFlipX = 1;
        if (!ApplyCachedSpriteProperties(ResolveSpriteObject(handle), handle,
                                          SpriteProperty::FlipX)) {
            return luaL_error(state, "Sprite.FlipX requires a writable live sprite");
        }
        return 0;
    }
    return luaL_error(state, "Sprite has no writable field named %s", field);
}

#if !defined(__SWITCH__)
void SetSpritePropertyApplyHostImplementation(
    SpritePropertyApplyHostImplementation function) noexcept {
    g_PropertyApplyHostImplementation = function;
}
#endif

int DestroySpriteHandle(lua_State* state) {
    auto* handle = static_cast<SpriteHandle*>(luaL_checkudata(state, 1, kSpriteMetatable));
    // ★ 引擎实体借出的 `Sprite`（`Entity:GetSprite()`）：这块 `ANM2` 是**引擎实体的成员**，
    // 不是本模块分配的。所以这里**什么都不做** —— 既不调 `~ANM2()`（那会把引擎对象的成员拆掉），
    // 也不 `free`（`handle->sprite` 不是 malloc 基址，`ReleaseSpriteStorage` 会把
    // `sprite-8` 里的字节当指针去 free）。
    //
    // 为什么"什么都不做"是对的：`__gc` 只在 Lua 已经无法再引用这个 userdata 时才跑，所以
    // "释放后句柄还能用"不会带来任何可观察行为；反过来，真实的实体 sprite 只能由引擎释放。
    // 这条分支就是所有权标记存在的唯一理由（去掉它 = 每次 GC 都踩一次引擎内存）。
    if (handle->source == kSpriteSourceEngineEntity ||
        handle->source == kSpriteSourceEngineGridEntity ||
        handle->source == LuaRuntime::kSpriteSourceEngineGridExtra) {
        return 0;
    }
    if (handle->sprite == nullptr) {
        return 0;  // 幂等：`__gc` 可能被显式 `collectgarbage()` 触发两次
    }
    const LuaRuntime::SpriteDestructorFn destructorMethod = LuaRuntime::SpriteDestructorThunk();
    if (destructorMethod != 0) {
        // `~ANM2()`（D1）只析构成员、**不释放内存** —— 内存由本模块分配，所以随后自己 free。
        destructorMethod(handle->sprite);
    }
    ReleaseSpriteStorage(handle->sprite);
    handle->sprite = nullptr;
    return 0;
}

std::size_t AttachSpriteMethods(lua_State* state) noexcept {
    return AttachApi600Methods(state,"Sprite") + AttachApi200Methods(state,"Sprite") + AttachApi100Methods(state,"Sprite") + AttachOwnerMethods(state, kSpriteOwner, kSpriteHandlers,
                              sizeof(kSpriteHandlers) / sizeof(kSpriteHandlers[0]));
}

// 探针读取口（见 `sprite_api.hpp`）：定义在具名命名空间中，`content_mount_point_probe.cpp`
// 才能链到它；匿名命名空间里的那几个 `std::atomic` 仍只在本 TU 可见。
void SpriteGetTexelProbeSnapshot(std::uint32_t* calls, std::uint32_t* fallbacks,
                                 std::uint32_t* reason, std::uint64_t* lastWord) noexcept {
    if (calls != nullptr) *calls = g_SpriteGetTexelCalls.load(std::memory_order_relaxed);
    if (fallbacks != nullptr) *fallbacks = g_SpriteGetTexelFallbacks.load(std::memory_order_relaxed);
    if (reason != nullptr) *reason = g_SpriteGetTexelLastReason.load(std::memory_order_relaxed);
    if (lastWord != nullptr) *lastWord = g_SpriteGetTexelLastWord.load(std::memory_order_relaxed);
}

SpriteReplaceSpritesheetProbe SpriteReplaceSpritesheetProbeSnapshot() noexcept {
    SpriteReplaceSpritesheetProbe view{};
    view.calls = g_ReplaceSpritesheetCalls.load(std::memory_order_relaxed);
    view.nameLength = g_ReplaceSpritesheetNameLength.load(std::memory_order_relaxed);
    view.nameHead = g_ReplaceSpritesheetNameHead.load(std::memory_order_relaxed);
    return view;
}

} // namespace isaac::runtime
