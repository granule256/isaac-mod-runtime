#pragma once

#include <cstddef>
#include <cstdint>
#include "domain/callback/managed_update_snapshot.hpp"

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// 全局 `Isaac` 表（引擎门面）。
//
// 这一族存在的理由很具体：PC Mod 的第一句常常是 `Isaac.GetItemConfig()`
// （EID 就是），而引擎数据（玩家实体、ItemConfig、`FindByType` ...）要等引擎结构偏移
// 定位后才能接。所以先把**表面**补齐，让 `Isaac.X()` 被调用时不报 Lua 错误：
//
//   * 真实现（读引擎/读 Runtime 自己的状态）：`GetFrameCount` / `GetTime` / `DebugString` /
//     `IsInGame` / `RunCallback`；批次 2 起 `GetPlayer`（引擎基址 → `Game*` →
//     `players` 向量 → `Entity_Player`，带 vptr 校验）；批次 2b 起 `GetItemConfig`
//     （`Manager + 0x36538` 的**内嵌** `ItemConfig`，只读视图）。三者拿不到都返回 nil；
//   * 安全 stub（返回安全默认值，每个成员每会话只在自己的输出通道上告警一次）：
//     其余成员，见 `isaac_api.cpp` 的 `Stub`。
//
// 表由家族自己建立并挂成全局：`lua_runtime.cpp` 只负责在 Mod 脚本运行前调用一次。
// 只读视图的元表（`Entity`/`EntityPlayer`/`ItemConfig`/`ItemConfig_Item`）同样由本 TU 建立
// （见 `RegisterIsaacApi`）。
[[nodiscard]] std::size_t RegisterIsaacApi(lua_State* state) noexcept;

// 把 Catalog 里 owner 为 `Isaac` 的方法挂到**栈顶的表**上（`RegisterIsaacApi` 的组成部分）。
// 单独导出是为了让契约测试能像其它家族一样核对绑定表与 Catalog 的 id 一致。
[[nodiscard]] std::size_t AttachIsaacMethods(lua_State* state) noexcept;

// 批次 340（2026-10-04）：`Game:Spawn(Type, Variant, Position, Velocity, Spawner, SubType, Seed)`。
// **为什么由 `isaac_api.hpp` 导出**：它和 `Isaac.Spawn` 共用同一份实现（都在 `isaac_api.cpp`），
// 而 `Game` 族的手写绑定表住在 `game_api.cpp`（另一个 TU）⇒ 必须从这里导出那一行绑定要有名字。
//
// ★★ 这条**不能走数据行**：引擎 `Game::SpawnEx` 的第 8 个形参**走栈**
// （`ldr w8,[x29,#0x60]`），而通用跳板只填 `x0..x7`/`d0..d7` ⇒ 栈上那格会是垃圾。
// 手写时由编译器按编译期签名把第 9 个参数量放到栈上 ✓。
[[nodiscard]] int GameSpawn(lua_State* state);

// 引擎 `Game` 的**玩家向量**（`std::vector<Entity_Player*>`）的解析结果。
//
// 为什么把它单独抽出来给 `game_api.cpp` 用：真机报告 `01789207110` 暴露的缺陷正是
// "同一个引擎事实被两条 API 各自解释了一遍" —— `Game:GetNumPlayers()` 读不到时降级答 **1**，
// 而 `Isaac.GetPlayer(0)` 读不到时诚实答 **nil**，于是 EID 的
// `for i = 0, game:GetNumPlayers() - 1 do local player = Isaac.GetPlayer(i) ... player.QueuedItem`
// （`features/eid_api.lua:2620-2625`）在玩家向量为空的那几帧索引 nil、报错、被派发器静默摘除。
// **两者对同一事实必须给出同一个答案**，所以判定与"是否可读"都只在这里做一次。
struct EnginePlayerArray {
    // 向量元素个数。`readable == false` 时它恒为 0，调用方**不得**把它当成"真的没有玩家"。
    std::size_t count{0};
    // 引擎侧的读取是否成功（基址/槽/`Game*`/向量首尾都可读且自洽）。
    bool readable{false};
};

// 解析引擎的玩家向量。`index` 用不到时传 0。任何一环不可读都返回 `readable == false`。
[[nodiscard]] EnginePlayerArray ResolveEnginePlayerArray() noexcept;

// 玩家向量的**逐元素**解析：返回第 `index` 个 `Entity_Player*`，拿不到返回 0。
//
// 为什么单开这个入口：`Game:GetPlayer(index)` 与 `Isaac.GetPlayer(index)` 在 PC 上是**同一个函数**
// （`tools/pc_contract_docs/Game.md:340` 明文），而"什么算一个可用的玩家下标"（vptr 校验、空槽、
// 越界阶段码）只应该有一份实现 —— 真机 `01789207110` 的根因正是"同一个引擎事实被两条 API
// 各自解释一遍"。`Game:GetPlayer` 的**越界夹取**由调用方做（PC 正文里两条 API 的越界口径不同），
// 这里只负责"给定一个已夹好的下标，把玩家指针取出来"。
[[nodiscard]] std::uintptr_t ResolveEnginePlayerAt(std::size_t index) noexcept;

// `Entity_Player` 指针判据（`*(u64*)ptr == 模块基址 + Entity_Player vtable 偏移`）。
[[nodiscard]] bool IsEnginePlayerPointer(std::uintptr_t candidate) noexcept;

// 玩家解析的**原始读数**（探针用，见 `isaac_api.cpp` 的 `RecordEnginePlayerLookup`）。
//
// 为什么需要：真机报告 `01789208345`/`01789208403` 里 EID 反复在
// `features/eid_api.lua:2625` 索引 `player`（nil），而"到底哪一步返回了 nil"在 Lua 侧看不出来
// —— `Isaac.GetPlayer(0)` 的失败有 8 个可能阶段（基址/槽/`Game`/向量区间/长度/下标/空元素/vptr）。
// 把这个结构体报出来，一轮真机就能定位阶段，而不是再猜一轮。
struct EnginePlayerLookup {
    // 最后一次查询读到的**原始值**（语义随阶段变化，见下）：
    //   * 阶段 4：`firstElement` = 读到的向量 begin、`second` = 读到的向量 end；
    //   * 阶段 8：`firstElement` = 元素指针、`second` = 该元素的 vptr；
    //   * 其余阶段：全 0。
    std::uintptr_t firstElement{0};
    std::uintptr_t second{0};
    // 读到的向量元素个数（阶段 0 时有效）。
    std::uint32_t count{0};
    // `ResolveEnginePlayerBegin` 自己读到的 begin/end（读失败时记 `~0`，与"读到 0"区分开）。
    std::uintptr_t resolverBegin{0};
    std::uintptr_t resolverEnd{0};
    // 失败阶段：0 = 成功；1 = 基址不可用；2 = 槽不可读/为空；3 = `Game*` 为空；
    // 4 = 向量区间不可读或不自洽；5 = 元素个数超过上限；6 = 下标越界；7 = 元素为空指针；
    // 8 = vptr 不是 `Entity_Player`。
    std::uint32_t stage{0};
};

[[nodiscard]] EnginePlayerLookup LastEnginePlayerLookupForProbe() noexcept;

// 引擎玩家链的**逐阶段**读数（探针用）。`Isaac.GetPlayer` 的失败有 8 个可能阶段，而
// `EnginePlayerLookup.stage` 只报"最后一个失败的阶段"。真机报告 `01789209134` 里那个阶段码
// 是被后续成功查询覆盖过的，读不出根因；逐阶段一次性报出去才能一轮定位。
struct EnginePlayerChain {
    std::uintptr_t moduleBase{0};  // 模块基址（0 = 未发布）
    std::uintptr_t gameSlot{0};    // 槽里的指针变量地址（0 = 槽不可读/为空）
    std::uintptr_t game{0};        // `Game*`（0 = 未构造）
    std::uintptr_t begin{0};       // 玩家向量 begin
    std::uintptr_t end{0};         // 玩家向量 end
    std::uint32_t beginReadable{0};
    std::uint32_t endReadable{0};
};

[[nodiscard]] EnginePlayerChain ReadEnginePlayerChainForProbe() noexcept;

// `Isaac.FindInRadius` 的探针读数（语义与用途见 `isaac_api.cpp` 里 `g_FindInRadius*` 的注释）。
struct FindInRadiusProbe {
    std::uint32_t calls{0};        // 累计调用次数
    std::uint32_t results{0};      // **最后一次**查询返回的实体个数
    std::uint32_t live{0};         // 其中来自活表
    std::uint32_t players{0};      // 其中来自玩家向量
    std::uint32_t effects{0};      // 其中来自效果表
    std::uint32_t roomResolved{0}; // 最后那次查询时 Room* 是否拿到
    std::uint32_t fingerprintOk{0};// 最后那次查询时房间实体容器指纹是否匹配
    std::uint32_t lastMask{0};     // 最后一次的 EntityPartition 掩码
    std::uint32_t lastRadius{0};   // 最后一次的半径（float 位模式低 24 位）
};

[[nodiscard]] FindInRadiusProbe FindInRadiusProbeSnapshot() noexcept;

// `Entity.Type`/`Variant`/`SubType` 的读取读数（探针）：EID 的 `hasDescription` 先用
// `type(entity) == "userdata"` 与 `entity.Type` 过滤候选实体，只有通过之后才会调
// `Entity:GetData`。真机显示 `GetData` 一次未被调用，所以这两个读数能分清
// "候选实体被 Type 过滤"与"hasDescription 压根没被调用"。
struct EntityFieldProbe {
    std::uint32_t typeReads{0};
    std::uint32_t lastType{0};
    std::uint32_t lastVariant{0};
    std::uint32_t lastSubType{0};
    // 以字符串键读实体字段的次数与最近一次的键名前 8 字节（EID 的 `getEntityData` 可能走这条）。
    std::uint32_t stringReads{0};
    std::uint64_t lastStringHead{0};
    // `Pickup.Touched` 的读数（2026-09-12，动作三）。EID 拿它当"摘掉隐瞒"的条件
    // （`eid_api.lua:3338`/`3340` 的 `not entity:ToPickup().Touched`），而**这个字段偏移本身
    // 还是"待真机确认"的猜测**（`kEntityPickupTouchedOffset`）。这里同时记三个数：
    //   * `touchedReads`/`touchedTrue` —— 读了多少次、其中为真的次数；
    //   * `lastTouchedRaw` —— 最近一次读到的**原始字节**（不是转成布尔之后的值），
    //     这样"偏移读错了、读到的是别的字节"也能分辨。
    std::uint32_t touchedReads{0};
    std::uint32_t touchedTrue{0};
    std::uint32_t lastTouchedRaw{0};
};

[[nodiscard]] EntityFieldProbe EntityFieldProbeSnapshot() noexcept;

// `Isaac.GetItemConfig()` 的探针（第八轮）：bit0 链路解析成功、bit1 向量可读、
// bit2 因"向量还没建立"而返回对象、bit3 因"参数非法"而返回 nil；bits8..31 调用次数。
[[nodiscard]] std::uint32_t GetItemConfigProbeSnapshot() noexcept;

// `Entity.FrameCount` 的探针读数：EID 的 `main.lua:1473` 判 `entity.FrameCount > 0`，
// 而过滤器链掩码显示它从不走到后面的 `EID:getEntityData` —— 只有该值恒 0 才会如此。
//   `reads`/`positive` 分别是读取次数与"结果 > 0"的次数；后三个是最后一次的原始值。
struct FrameCountProbe {
    std::uint32_t reads{0};
    std::uint32_t positive{0};
    std::uint32_t gameFrameCount{0};  // `[Game + 0x24F99C]`
    std::uint32_t spawnFrame{0};      // `[entity + 0x2F4]`
    std::uint32_t result{0};          // 两者之差
};

[[nodiscard]] FrameCountProbe FrameCountProbeSnapshot() noexcept;


// `Isaac.GetPlayer` 的成功/失败次数（原因 1：`EID.player` 依赖它）。
struct PlayerLookupProbe {
    std::uint32_t getPlayerSuccess{0};
    std::uint32_t getPlayerFailure{0};
};

[[nodiscard]] PlayerLookupProbe PlayerLookupProbeSnapshot() noexcept;

// `Isaac.CountEnemies()` 最后一次返回的个数（EID 用它 + `HideInBattle` 决定是否隐藏描述）。
[[nodiscard]] std::uint32_t LastCountEnemiesForProbe() noexcept;

// `Entity` / `EntityPlayer` 的方法表（owner 分别是 `Entity`、`EntityPlayer`，同样是
// `LuaHandlerBinding` + `AttachOwnerMethods` 模式）。它们挂在各自元表的 `__methods` 上；
// `EntityPlayer` 的 `__index` 会回落到 `Entity` 的方法表（PC 里就是继承）。
[[nodiscard]] std::size_t AttachEntityMethods(lua_State* state) noexcept;
[[nodiscard]] std::size_t AttachEntityPlayerMethods(lua_State* state) noexcept;
//: 批次 281：`EntityTear` 视图（`Entity:ToTear()` 的返回值）的方法表。
[[nodiscard]] std::size_t AttachEntityTearMethods(lua_State* state) noexcept;
//: 批次 282：`EntityLaser` 视图（`Entity:ToLaser()` 的返回值）的方法表。
[[nodiscard]] std::size_t AttachEntityLaserMethods(lua_State* state) noexcept;
// `EntityPickup` 的方法表（批次 4）：目前只有 `IsShopItem`（安全 stub，见 `isaac_api.cpp`）。
[[nodiscard]] std::size_t AttachEntityPickupMethods(lua_State* state) noexcept;

// `ItemConfig` / `ItemConfig_Item` 的方法表（批次 2b，同一个 `LuaHandlerBinding` +
// `AttachOwnerMethods` 模式，同样挂在各自元表的 `__methods` 上）。条目的字段
// （`ID`/`Type`/`Name`/`Description`）走 `__index`，与 `EntityPlayer` 的 `Position` 同例，
// 因此不占绑定行。
[[nodiscard]] std::size_t AttachItemConfigMethods(lua_State* state) noexcept;
[[nodiscard]] std::size_t AttachItemConfigItemMethods(lua_State* state) noexcept;

// 引擎实体存活判据（`vptr` 落在 `[base + kEntityVtableRangeBeginOffset, …End)` 的 `Entity`
// 家族区间内、且该地址可读）。
//
// 导出它的唯一理由：`sprite_api.cpp` 的 `Entity:GetSprite()` 句柄必须**每次访问**都重新确认
// "借出 sprite 的那个实体还活着"（见 `lua_object_handles.hpp` 的 `kSpriteSourceEngineEntity`），
// 而"什么算一张活的 Entity"只应该有一份实现 —— 就是 `isaac_api.cpp` 里 `ValidatedEntity` 用的
// 那一条。返回 `true` 表示可以安全地按 `Entity` 布局读它的字段。
[[nodiscard]] bool IsLiveEntityPointer(std::uintptr_t candidate) noexcept;

// 网格实体存活判据（`vptr` 落在 `[base + kGridEntityVtableRangeBeginOffset, …End)` 的
// `GridEntity` 家族区间内、且该地址可读）—— 批次 298（2026-10-03）。
//
// 与上面那条**同形、同一份理由**：`GridEntity:GetSprite()` 交出去的 `Sprite` 句柄指向
// **引擎网格实体内部**的内存（`GridEntity + 0x48` 那个内嵌 `ANM2`），所以每次访问都要重新确认
// "借出 sprite 的那个网格实体还在"。★ 两条判据**刻意分成两份**：`Entity` 与 `GridEntity` 的
// vtable 区间**有重叠**，合成一条会让"网格实体被当成实体"或反之——各自一份才好按类收紧。
[[nodiscard]] bool IsLiveGridEntityPointer(std::uintptr_t candidate) noexcept;

// 从栈上第 `index` 格取"网格实体句柄"里的引擎指针；不是那两张元表 ⇒ 返回 **nullptr**
// （**不抛错** —— 手写路径用它做"参数类型不对就退回 nil"）。批次 304（2026-10-03）从
// `remaining_api.cpp` 的 `GridEntityArgument` 提上来，为的是**只有一份判据**：
// 现在的两个使用者是"手写处理器（`GridEntity:GetVariant` 一族）"与"数据行的接收者解析
// （`FieldReceipt::GridEntity`）"，而它们住在**两个不同的 TU** 里。
//
// 接受两张元表：`IsaacRuntime.GridEntity`（`GridEntityHandle`）与 `IsaacRuntime.GridEntityDoor`
// （`DoorHandle` —— 门除了引擎指针还记着自己的槽位，所以是另一个结构体）。
[[nodiscard]] void* GridEntityHandleArgument(lua_State* state, int index) noexcept;

// 同上，但**不是网格实体句柄时直接抛 Lua 错误**（"参数类型写错了"，与 `CheckEntityHandle` 同口径）。
// 数据行的接收者解析用这一条：模组把一张表当 `self` 传进来时报错比静默降级更接近 PC。
[[nodiscard]] void* CheckGridEntityHandle(lua_State* state, int index);

// 从栈上第 `index` 个实参取"活着的实体指针"；不是实体句柄、或底层指针已失效 ⇒ 返回 0。
//
// 为什么单开一个入口：PC 有若干签名里带**可空** `EntityPlayer` 的方法（例如
// `ItemPool:GetPillEffect(PillColor, EntityPlayer = nil)`），而那些方法的实现住在别的 TU
// （`remaining_api.cpp` 的 ItemPool 家族）。"什么算一个实体句柄"只应该有一份实现
// （就是这里 `CheckEntityHandle` + `ValidatedEntity` 那一对），所以这里给一个**不抛错**的出口：
// 拿不到就返回 0，由调用方决定是"传 nullptr 给引擎"还是报错。
[[nodiscard]] std::uintptr_t EntityPointerArgument(lua_State* state, int index) noexcept;

// 批次 065：读一个实体的 `Type`/`Variant`（`Entity + 0x38` / `+0x3C`，两张布局都是
// `confirmed` 的）。`EntityRef` 的替身缓冲区要用这两个值填 `+0x08`/`+0x00` 两格，
// 而"读引擎字段前先判可读"那套判据在 `isaac_api.cpp` 里才有一份，所以从这里导出。
// 任一字段读不到 ⇒ 返回 false（调用方按"留空"处理，不猜）。
[[nodiscard]] bool ReadEntitySubType(std::uintptr_t entity, std::uint32_t* subtype) noexcept;
[[nodiscard]] bool ReadEntityIdentity(std::uintptr_t entity, std::uint32_t* type,
                                      std::uint32_t* variant) noexcept;

// 批次 104：读 `RoomConfig::Entry` 的前三个字段（`Type`/`Variant`/`SubType`），
// 给 `Room::spawn_entity` 的入口中继用（`MC_PRE_ROOM_ENTITY_SPAWN` 的三个实参）。
// 偏移与**宽度**的依据（`Type` 是 i32、`Variant`/`SubType` 是 **i16**）写在
// `runtime_constants.hpp` 里那三行常量上方（两条独立的三连读证据）。
// 从 `isaac_api.cpp` 导出的理由与 `ReadEntityIdentity` 相同：**"读引擎字段前先判可读"那套判据
// 只有那一份实现**，别处再写一份就会漂。任一字段读不到 ⇒ 返回 false（调用方按"不编造值"处理）。
//: 引擎自己的帧计数（`Game + 0x24F99C`，`Game::Update` 每帧 +1；`Game:GetFrameCount` 读的
//: 就是它，指令级证据见 `runtime_constants.hpp`）。
//: 批次 109：`Input.IsActionTriggered` 的"按帧判上升沿"要用它当帧号 —— 读不到时返回 0，
//: 调用方自己退化成用毫秒时钟当序号（**不能让读失败变成"边沿永远不刷新"**）。
[[nodiscard]] std::uint32_t EngineFrameCountNow() noexcept;

[[nodiscard]] bool ReadRoomConfigEntryFields(std::uintptr_t entry, std::int32_t* type,
                                            std::int32_t* variant,
                                            std::int32_t* subType) noexcept;

// 批次 396（2026-10-07）：读 `Entity_Player` 的 CacheFlag 掩码（`Entity_Player + 0x1958`，
// 偏移与两条独立证据见 `runtime_constants.hpp` 的 `kEntityPlayerCacheFlagsOffset`）。
// 给 `MC_EVALUATE_CACHE` 的入口中继用：`EvaluateItems` 的入口**不带** CacheFlag 实参，
// 中继要自己快照这张掩码、逐位派发一次。从 `isaac_api.cpp` 导出的理由与
// `ReadEntityIdentity`/`ReadRoomConfigEntryFields` 相同：**"读引擎字段前先判可读"那套判据
// 只有那一份实现**。读不到 ⇒ 返回 false（调用方按"不派发"处理，不编造掩码）。
[[nodiscard]] bool ReadEntityPlayerCacheFlags(std::uintptr_t player,
                                              std::uint32_t* cacheFlags) noexcept;

#if !defined(__SWITCH__)
// 宿主测试注入点。**设备构建（`-D__SWITCH__`）里不存在这个类型和这个函数。**
//
// 为什么需要它：`EntityPlayer:HasCollectible` 的设备实现是一条 `bl`
// `base + kEntityPlayerHasCollectibleOffset`，而宿主构建既没有引擎映像、也不可能把一个 C++
// 函数恰好放在那个地址上。注入点顶替的就是这一条 `bl`，让宿主测试仍然能验证真正容易写错的
// 那几段：vptr 校验必须先于调用、传给引擎的第一个参数就是实体指针、**两个**实参（id 与
// `ignoreModifiers`）与返回值原样往返。
//
// 2026-09-17：第二个参数补上 —— PC 的签名是 `HasCollectible(CollectibleType, bool ignoreModifiers)`，
// 原生符号 `_ZNK15IsaacRepentance13Entity_Player14HasCollectibleENS_16eCollectibleTypeEb`
// 也是 `(eCollectibleType, bool)`。EID 真的会传（`features/eid_api.lua:3004` 的
// `player:HasCollectible(itemID, true)`），此前我们只接受一个参数并直接报错。
using EntityPlayerHasCollectibleHostImplementation = bool (*)(void* entity,
                                                             std::uint32_t collectibleId,
                                                             bool ignoreModifiers);
void SetEntityPlayerHasCollectibleHostImplementation(
    EntityPlayerHasCollectibleHostImplementation function) noexcept;

using CurrentLanguageCodeHostImplementation = const char* (*)();
void SetCurrentLanguageCodeHostImplementation(
    CurrentLanguageCodeHostImplementation function) noexcept;

// `ItemConfig_Item:IsAvailable()` 按"条目属于哪条向量"去调**三个不同的引擎函数**
// （`Item` / `Card` / `PillEffect`）；宿主构建没有引擎映像，那三条 `bl` 由测试注入的实现顶替。
// `kind` 明确告诉测试"会去调哪一个"：0 = Item（带 flags）、1 = Card、2 = PillEffect。
using ItemConfigIsAvailableHostImplementation = bool (*)(int kind, void* entry, std::int64_t flags);
void SetItemConfigIsAvailableHostImplementation(
    ItemConfigIsAvailableHostImplementation function) noexcept;

// `ItemConfig_Item:IsRune()`（PC 的类名是 `ItemConfig_Card`）在真机上是**直读卡片条目的一格**
// （`ItemConfig::Card + 0x58` == 2 ⇒ 符文，见 `runtime_constants.hpp` 的 `kItemConfigCardTypeOffset`）。
// 宿主构建没有引擎映像 ⇒ 注入一个"给我这个条目的答案"的实现，让门禁能钉住 true/false 的映射。
using ItemConfigCardIsRuneHostImplementation = bool (*)(void* card);
void SetItemConfigCardIsRuneHostImplementation(
    ItemConfigCardIsRuneHostImplementation function) noexcept;
#endif

// 全局 `Options` 表。EID 只读 `HUDOffset` 与 `Language` 两个字段，缺了它们 EID 一加载就报错。
//
// 两个字段仍是从引擎选项结构读取的真实实现的替代品：`HUDOffset = 10` 对齐 EID 默认配置，
// `Language = "zh"` 对齐当前简体中文环境。它们是**值**而不是方法，因此 Catalog 里有条目、
// 绑定表里没有绑定行。
[[nodiscard]] std::size_t RegisterOptionsTable(lua_State* state) noexcept;

// Device-side gate for managed callbacks: menus and load transitions can leave a stale player
// vector behind. Do not dispatch until both the current room and a validated player exist.
[[nodiscard]] bool ShouldDispatchManagedCallbacks() noexcept;
// 仅普通更新使用：原生暂停/未知拒绝，并返回同一Game的原生simulation帧。
[[nodiscard]] bool ShouldDispatchManagedUpdates(ManagedUpdateSnapshot* snapshot) noexcept;
#if !defined(__SWITCH__)
using ManagedUpdateSnapshotReader = bool (*)(ManagedUpdateSnapshot*) noexcept;
void SetManagedUpdateSnapshotReaderForTest(ManagedUpdateSnapshotReader reader) noexcept;
#endif


// --- 每帧事件（回调面地基）需要的"游戏侧视图" ----------------------------------
//
// `lua_runtime.cpp` 的每帧事件派发（`MC_POST_NEW_ROOM`/`MC_POST_NEW_LEVEL`/
// `MC_POST_PICKUP_INIT`/`MC_POST_PICKUP_UPDATE`/`MC_POST_PLAYER_INIT`）要知道"房间里现在有哪些
// 实体、其中哪些是掉落物、玩家是谁"。这三件事的实现（vptr 校验、实体容器指纹、实体句柄与元表）
// 全归 `isaac_api.cpp` 所有，所以这里只开入口，不让派发侧再写第二份 —— 与 `IsLiveEntityPointer`
// 被导出的理由完全相同。
//
// 为什么用"访问器 + 上下文指针"而不是返回数组：每帧要把房间实体过一遍，实体数上限 0x800，
// 拷进临时数组只是白花内存带宽；`void* context` 让调用方自己带着状态（它只用来比较、不解引用）。
using EntityVisitFn = void (*)(void* context, std::uintptr_t entity);

// 遍历当前房间的**活动实体全集**（`EntityList+0x78`，与 `Isaac.GetRoomEntities` 同一张表），
// 只把通过 vptr 校验的非空实体交给 `visit`。房间拿不到或容器指纹不符时**一个都不遍历**
// （宁可这次不派发，也不把一整段垃圾当实体表）。
void VisitRoomEntities(EntityVisitFn visit, void* context) noexcept;

// 遍历玩家的 `std::vector<Entity_Player*>`（与 `Isaac.GetPlayer` 同一对偏移）。
void VisitPlayerEntities(EntityVisitFn visit, void* context) noexcept;

// 该实体是不是掉落物。判据与 `Entity:ToPickup()` 完全相同：`Type == ENTITY_PICKUP(5)`
// **且** vptr 精确等于 `Entity_Pickup` 的 vtable —— 只比 `Type` 会把子类误判成掉落物。
[[nodiscard]] bool IsPickupEntity(std::uintptr_t candidate) noexcept;

// 把一个实体压栈成回调实参（与 `Isaac.GetRoomEntities()` 给出的句柄同一种视图：
// 玩家实体给 `EntityPlayer` 元表，其余给 `Entity`）。模组把回调参数直接当实体用，
// 视图不一致会让 `player:HasCollectible()` 这类调用在回调里失败。
void PushEntityCallbackArgument(lua_State* state, std::uintptr_t entity) noexcept;
// 在调用者的Lua保护桥内压真实道具RNG，复用玩家/容器寿命验证。
void PushCollectibleRngCallbackArgument(lua_State*,std::uintptr_t player,std::int32_t item);

// --- 实体族回调（2026-09-18）需要的"这个实体属于哪一类" ---------------------------
//
// `MC_*_UPDATE` / `MC_*_RENDER` / `MC_*_INIT` 这一族回调在 PC 上**按实体的 C++ 类**触发
// （眼泪、弹射物、激光、刀、炸弹、效果、跟班、敌人、玩家、掉落物各有一套）。判据（vptr 区间
// 校验、精确 vtable 比较、`EntityType` 取值）全部归 `isaac_api.cpp` 所有，所以这里只开**一个**
// 入口 —— 派发侧不许自己再写一份类型判据（本项目已经因为"两份判据会漂"吃过亏）。
enum class CallbackEntityClass : std::uint32_t {
    None = 0,
    Npc,
    Familiar,
    Tear,
    Projectile,
    Laser,
    Knife,
    Effect,
    Bomb,
    Player,
    Pickup,
};

// 分类判据逐条写在实现处。判不出（指针不合法 / vptr 不在 `Entity` 家族区间 / 类型不属于上面
// 任何一类，例如 `ENTITY_SLOT(6)`）一律返回 `None` —— 宁可这次不派发，也不猜。
[[nodiscard]] CallbackEntityClass ClassifyCallbackEntity(std::uintptr_t candidate,
                                                       std::int64_t* callbackFilter = nullptr) noexcept;

} // namespace isaac::runtime

namespace isaac::runtime {
// 重用配置向量身份校验，供HUD的玩家/道具重载消费，失效句柄返回0。
std::uintptr_t ItemConfigPointerArgument(lua_State*,int) noexcept;
}

namespace isaac::runtime {
enum class FieldReceipt : std::uint8_t;
// 所有API共用既有接收者判据；不会在扩展模块另造Game/Room/实体地址链。
std::uintptr_t ResolveEngineReceiver(lua_State*,FieldReceipt,int index=1);
}

namespace isaac::runtime {std::uintptr_t ResolveContentConfigRoot(bool entityConfig) noexcept;}

namespace isaac::runtime {void ApplyUseItemCallbackAnimation(lua_State*,std::uintptr_t,std::int32_t);}

namespace isaac::runtime {void ApplyUseItemNativeRemoval(lua_State*,std::uintptr_t,std::int32_t);}
