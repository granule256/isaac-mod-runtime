#pragma once

#include <array>
#include <cstdint>
#include "runtime_constants.hpp"

// Lua userdata handles and metatable names for the object API families.
//
// They live in the legacy source root (not under `runtime/src`) because the
// non-layered/probe builds do not have the layered include path, and because
// `lua_runtime.cpp` still owns the metatable registration. The family
// translation units own the handlers that create and validate these objects.
namespace LuaRuntime {
struct EntityLifetimeToken;

inline constexpr char kGameMetatable[] = "IsaacRuntime.Game";
inline constexpr char kLevelMetatable[] = "IsaacRuntime.Level";
inline constexpr char kItemPoolMetatable[] = "IsaacRuntime.ItemPool";
inline constexpr char kRoomMetatable[] = "IsaacRuntime.Room";
inline constexpr char kGridEntityMetatable[] = "IsaacRuntime.GridEntity";
//: `Room:GetDoor(slot)` 的返回值（同时是 `GridEntity`，见 `DoorHandle` 的说明）。
inline constexpr char kGridEntityDoorMetatable[] = "IsaacRuntime.GridEntityDoor";
// 地基二期新增（`Level` 的三个房间描述符 API 的返回值）。
inline constexpr char kRoomDescriptorMetatable[] = "IsaacRuntime.RoomDescriptor";
inline constexpr char kRoomDescriptorListMetatable[] = "IsaacRuntime.RoomDescriptorList";
inline constexpr char kSeedsMetatable[] = "IsaacRuntime.Seeds";
// `HUD`（批次 207，2026-09-29）：`Game:GetHUD()` 的返回值。PC 里它是**自己的一个对象类**
// （`HUD:IsVisible()` / `SetVisible(bool)`），所以有独立的 domain（`ApiDomain::Hud = 17`）
// 与独立的元表。
//
// 句柄**不持有地址**，与 `SeedHandle` 逐字同一条理由：`HUD` 是 `Game` 里**内嵌**的子对象
// （`Game* + 0xE8468`，引擎里不存在指向它的指针），而且要放进本文件那个"不许放存地址的结构体"
// 的区间（`RoomHandle`…`MusicHandle` 一带，契约门禁按源码窗口钉着）。每次访问按当前 `Game`
// 基址现算 ⇒ 换局/重建 `Game` 都不会拿到过期地址。
inline constexpr char kHudMetatable[] = "IsaacRuntime.HUD";
inline constexpr char kMusicMetatable[] = "IsaacRuntime.Music";
inline constexpr char kRngMetatable[] = "IsaacRuntime.RNG";
// 批次 065：`EntityRef`（PC 的值类型；引擎按引用读它，所以我们自己持有那块缓冲区）。
inline constexpr char kEntityRefMetatable[] = "IsaacRuntime.EntityRef";
inline constexpr char kFontMetatable[] = "IsaacRuntime.Font";
inline constexpr char kColorMetatable[] = "IsaacRuntime.KColor";
// PC's `Vector` is `KAGE::Math::Vector2`: 8 bytes `{float X, float Y}`, no vtable (audited in
// `analysis/stage150-sprite-abi/`). Like `KColor` it is a pure value type, so the handle stores
// the value itself -- no engine object, and nothing has to be published from the hook.
inline constexpr char kVectorMetatable[] = "IsaacRuntime.Vector";
// Lua 的 `Sprite` = 引擎的 `IsaacRepentance::ANM2`（stage150 审计的类身份判定）。对象尺寸由
// `tools/stage155_anm2_size_audit.py` 用两种独立方法定案为 `0x158`（见 `runtime_constants.hpp`）。
inline constexpr char kSpriteMetatable[] = "IsaacRuntime.Sprite";
// `Entity` / `EntityPlayer`（批次 2）：`Isaac.GetPlayer(i)` 返回的只读实体视图。PC 里
// `EntityPlayer` 继承 `Entity`，所以这里也建两张元表：`Entity` 承载基类字段与方法，
// `EntityPlayer` 通过 `__index` 回落到它（见 `interfaces/lua/isaac_api.cpp`）。
inline constexpr char kEntityMetatable[] = "IsaacRuntime.Entity";
inline constexpr char kEntityPlayerMetatable[] = "IsaacRuntime.EntityPlayer";
// `EntityPickup`（批次 4）：`Entity:ToPickup()` 的返回值，PC 里它是 `Entity` 的子类。
// 句柄体复用 `EntityHandle`（都是"一个原生实体指针"），字段（`Price`/`ShopItemId`/
// `OptionsPickupIndex`/`ForceBlind`/`Touched`）走它自己的 `__index`。判据是 `Type == 5`
// **且** vptr == `base + 0xA36E28`（`Entity_Pickup` 的 vtable 唯一），见 `isaac_api.cpp`。
inline constexpr char kEntityPickupMetatable[] = "IsaacRuntime.EntityPickup";
// `EntityProjectile`（批次 207，2026-09-29）：`Entity:ToProjectile()` 的返回值。
// 句柄体同样复用 `EntityHandle`（一个原生实体指针）。判据 = `Type == 9` **且**
// vptr == `base + 0xA37410`（就是 `_ZTVN15IsaacRepentance17Entity_ProjectileE` + 0x10），
// 与 `EntityPickup` 那一族同形，见 `isaac_api.cpp`。
// 它现在只有**一个**字段（`ProjectileFlags`，`+0x428`），没有自己的 catalog 行：
// 字段走 `__index`，方法回落到 `Entity`。
inline constexpr char kEntityProjectileMetatable[] = "IsaacRuntime.EntityProjectile";
//: 批次 281：`Entity:ToTear()` 的返回值（`EntityTear` 视图）。
inline constexpr char kEntityTearMetatable[] = "IsaacRuntime.EntityTear";
// 炸弹转换返回真实子类视图；IsFetus共享实体寿命与GetData，不复制原生对象。
inline constexpr char kEntityBombMetatable[] = "IsaacRuntime.EntityBomb";
//: 批次 282：`Entity:ToLaser()` 的返回值（`EntityLaser` 视图）。
inline constexpr char kEntityLaserMetatable[] = "IsaacRuntime.EntityLaser";
inline constexpr char kEntityKnifeMetatable[] = "IsaacRuntime.EntityKnife";
//: 批次 285（2026-10-02）：`Entity:ToNPC()` 的返回值（`EntityNPC` 视图）。
//: 在此之前 `ToNPC()` 压的是**基类 `Entity` 元表** ⇒ `EntityNPC` 页上的方法（`Morph` 等）
//: 没有地方挂。句柄体仍复用 `EntityHandle`（一个原生实体指针），身份判据是
//: `IsNpcFamilyEntity()`（"`Entity` 家族区间内、且不是那 13 个非 NPC 直接子类"—— 敌人的
//: vtable 有 49 个子类不在导出符号表里，所以不能按精确 vptr 判）。字段回落到 `Entity`。
inline constexpr char kEntityNPCMetatable[] = "IsaacRuntime.EntityNPC";
//: 批次 330（2026-10-03）：`Entity:ToFamiliar()` 的返回值（`EntityFamiliar` 视图）。
//: 在此之前 `ToFamiliar()` 压的是**基类 `Entity` 元表**（批次 9 起就是这样）⇒ `EntityFamiliar`
//: 页上的方法（`FollowParent` / `AddToFollowers` …）**没有地方挂**，
//: 语料里 `familiar:FollowParent()` 会报 "attempt to call a nil value"。
//: 句柄体仍复用 `EntityHandle`（一个原生实体指针），身份判据 = **精确**的
//: `base + kEntityFamiliarVtableOffset` 且 `Type == kEntityTypeFamiliar`（与 `Entity:ToFamiliar()`
//: 里那条判据**同一份**）。字段回落到 `Entity`（与 `EntityTear`/`EntityLaser`/`EntityNPC` 同形）。
inline constexpr char kEntityFamiliarMetatable[] = "IsaacRuntime.EntityFamiliar";
//: 批次 344（2026-10-04）：`EntityNPC.Pathfinder` 属性的返回值（`PathFinder` 视图）。
//: PC 里 `EntityNPC` 页上只有 `Pathfinder` 这一个 PathFinder 相关成员（`EntityNPC.md:208-210`），
//: 它交出的是 `NPCAI_Pathfinder` 对象（引擎里**内嵌**在 `Entity_NPC + 0x408`，不是指针成员）。
//: 句柄真持那个内嵌子对象的地址 ⇒ 身份判据就是"句柄类型对不对"
//: （`luaL_testudata(…, kPathFinderMetatable)`），**不做** vptr 校验 —— 内嵌子对象没有自己的 vptr。
//: ★ 只挂在 `EntityNPC` 上：`Entity_Familiar` 也内嵌一份（在 `+0x5F8`），但 PC 的
//:   `EntityFamiliar` 页里没有 `Pathfinder` 属性 ⇒ 不挂（多给 = 与 PC 不一致）。
inline constexpr char kPathFinderMetatable[] = "IsaacRuntime.PathFinder";
//: 批次 388（2026-10-07）：`EntityPlayer:GetEffects()` 的返回值（`TemporaryEffects` 视图）。
//: PC 里 `TemporaryEffects` 是**自己的一个对象类**（`TemporaryEffects.md`，17 个方法）。
//: 句柄存**拥有它的 `Entity_Player` 地址**（容器是 `Entity_Player + 0x18D8` 的内嵌子对象）——
//: 每次访问重新校验玩家 vptr 再把容器地址算回来，避免句柄跨帧后指向已消失的玩家。
inline constexpr char kTemporaryEffectsMetatable[] = "IsaacRuntime.TemporaryEffects";
// `ItemConfig` / `ItemConfig::Item`（批次 2b）：`Isaac.GetItemConfig()` 返回的只读配置视图。
// 两张元表：`ItemConfig` 承载 `GetCollectible`/`GetTrinket`/…，`ItemConfig_Item` 承载条目字段
// （`ID`/`Type`/`Name`/`Description`）与条目级方法（`HasTags`）。
inline constexpr char kItemConfigMetatable[] = "IsaacRuntime.ItemConfig";
inline constexpr char kItemConfigItemMetatable[] = "IsaacRuntime.ItemConfig_Item";

// The handle bodies are placeholders on purpose: the Lua layer must never hold
// a native Game/Level/Room pointer, so the object identity is resolved again
// inside each managed callback scope.
struct GameHandle {
    std::uint8_t reserved;
};

struct LevelHandle {
    std::uint8_t reserved;
};

struct ItemPoolHandle {
    std::uint8_t reserved;
};

struct RoomHandle {
    std::uint8_t reserved;
};

// `Seeds`（PC 的 `Game:GetSeeds()` 返回值）。句柄**不持有引擎指针**，只是"拿得到对象、
// 方法都在"的身份标记。
//
// ★ 批次 195（2026-09-29）更正：这里原来存着一份**自洽的常量快照**
//（`startSeed`/`customRun` 两个字段，理由是"`Seeds` 的字段偏移尚未定位"）。偏移已经定位 ——
// `Seeds` 对象**内嵌**在当前局对象里、基址是 `Game 基址 + 0x25D40`，`StartSeed` 在 `+0x04`、
// "自定义种子"标志在 `+0x00`（三处写 / 三处读互相印证，逐条见 `runtime_constants.hpp` 的
// `kGameSeedsObjectOffset`）——所以两个方法改成**调用时真读引擎**，那份快照字段随之删除
//（留着就是"两个真值源"）。
// 句柄本身仍然不带地址：与 `Game`/`Level`/`Room` 同一条约束（本区间不许放"存地址"的结构体，
// 门禁 `test_lua_level_getstage` / `test_lua_room_gettype` 按源码窗口钉着这一条），
// 而且 `Seeds` 是**内嵌**的、按当前局对象基址现算比缓存一个地址更安全。
struct SeedHandle {
    std::uint8_t reserved;
};

struct MusicHandle {
    std::uint8_t reserved;
};

// `HUD`（批次 207）：与 `SeedHandle` 同形 —— **不持有引擎指针**，只表示"拿得到对象、方法都在"。
// `Game:GetHUD()` 造它，两个方法每次按 `Game* + kGameHudObjectOffset` 现算 HUD 地址。
struct HudHandle {
    std::uint8_t reserved;
};

struct RngHandle {
    // RNG()自有状态；引擎返回的引用由resolver每次复核owner/容器后取地址。
    std::array<std::uint8_t, 16> storage{};
    using Resolver = std::uintptr_t (*)(const RngHandle*) noexcept;
    Resolver resolver = nullptr;
    std::uintptr_t owner = 0;
    std::uintptr_t container = 0;
    std::uintptr_t offset = 0;
    std::uintptr_t index = 0;
};

// Unlike every other handle in this file, `font` is not a game-owned pointer: it points at a
// `KAGE::Graphics::Font` that the Runtime itself allocated (`kFontObjectSize` bytes, 16-byte
// aligned) and that the Runtime must therefore release. `Game`/`Level`/`Room`/`Music` are
// resolved again inside each managed callback because the game owns those objects; a Font has
// no such owner, which is why this handle carries the instance and why `__gc` frees it.
//
// 批次 3 追加三个**颜色偏移**：PC 的 `Color(R,G,B,A,RO,GO,BO)` 重载
// （`analysis/isaacdocs-snapshot/docs/Color.md:27`），EID 的 `EID:renderIcon`
// （`features/eid_api.lua:1369`）用的就是七参形式。这三个值只保存在句柄里、不参与任何引擎调用
// （`font_api` 传给引擎的仍然是句柄起头的 16 字节 RGBA，与既有的"16 字节颜色"假设一致）；
// 好处是后三个参数不再被静默丢掉，而且整块内存都被初始化。
// `GridEntity`（批次 12，2026-09-16）：**持有引擎指针**（网格实体对象地址），
// 所以按本文件的约束摆在 `MusicHandle` 之后那一带（`RoomHandle`…`MusicHandle` 区间内
// 不许放带 `void*`/`uintptr_t` 的结构体 —— 那条约束是契约门禁在管的）。
//
// 为什么现在才加：`Room:GetGridEntity()` 过去是登记在案的"恒返回 nil"偏离（网格实体表未定位）。
// 2026-09-16 定位到表在 `Room + 0x30`（证据见 `runtime_constants.hpp` 的
// `kRoomGridEntityTableOffset`），于是这一族可以建起来了。
struct GridEntityHandle {
    void* entity;
};

// `GridEntity_Door`（批次 078，2026-09-19）：`Room:GetDoor(slot)` 的返回值。
//
// 为什么不复用 `GridEntityHandle`：门除了"引擎对象地址"还要记住**自己的槽位** ——
// `door.Position` 要靠它去问引擎（`Room::GetDoorSlotPosition(eDoorSlot)`）。
// 门在 PC 那边**同时是 `GridEntity`**（`door:GetType()`、`door.Desc`、`door.VarData` 都要能用），
// 所以它的元表 `__index` 会先按"门的字段"答，答不上再落到 `GridEntity` 的方法表。
struct DoorHandle {
    void* entity;
    std::int32_t slot;
    std::int32_t reserved;
};

// `PathFinder`（批次 344，2026-10-04）：`EntityNPC.Pathfinder` 属性的返回值。
// 存的就是内嵌子对象 `NPCAI_Pathfinder` 的地址（`Entity_NPC + 0x408`）—— `EntityHandle` 一族
// 同形（**持引擎指针**，所以按本文件的约束摆在 `MusicHandle` 之后）。
// ★ 引擎里这个对象没有自己的 vptr（是 `Entity_NPC` 的**内嵌成员**）⇒ 访问时没法靠 vptr 复核
//   "这个地址还是不是一个 PathFinder"；能做的只有句柄类型校验 + "底层地址非 0 且可读"。
//   与 PC 同一条已知口径：PC 也是把内部引用交出去、不做生命周期保护（引擎在回调之间重排/销毁
//   那个 NPC 时，旧句柄同样会失效）。
struct PathFinderHandle {
    void* pathfinder;
    // 2026-10-14：与NPC共享token；生产视图强持token，访问O(1)核拥有者。
    void* owner{};
    EntityLifetimeToken* lifetime{};
};

// `TemporaryEffects`（批次 388，2026-10-07）：`EntityPlayer:GetEffects()` 的返回值。
// 存**拥有它的 `Entity_Player` 地址**：容器是 `Entity_Player` 的**内嵌子对象**
// （`player + kEntityPlayerTemporaryEffectsOffset` = `+0x18D8`，不是指针成员）⇒
// 每次使用时重新校验玩家 vptr（`IsEntityPlayer`）再算容器地址，换局/玩家销毁后旧句柄
// 会自然失效，而不会解引用过期内存（与 `RoomDescriptorListHandle` 存 `level` 同一条理由）。
struct TemporaryEffectsHandle {
    void* player;
};

struct ColorHandle {
    float red;
    float green;
    float blue;
    float alpha;
    float offsetRed;
    float offsetGreen;
    float offsetBlue;
    // 完整ColorMod染色值；追加在旧七格之后，RGBA/offset旧成员偏移不变。
    float colorizeRed{};
    float colorizeGreen{};
    float colorizeBlue{};
    float colorizeAmount{};
};

// ★ 2026-10-09 更正上述 Font 所有权说明：句柄形状保持一个指针，原生对象
// 内存由另一个完整 userdata 承载，句柄通过 uservalue 强引用它；__gc 仅调用
// 引擎析构并解除引用，载荷由 Lua GC 释放，不再手工 free/调用 lua_Alloc。
struct FontHandle {
    void* font;
};

struct VectorHandle {
    float x;
    float y;
};

// 批次 065：`EntityRef = Entity::EntityRef` 的**裸缓冲区**（布局与证据见 `entity_ref_api.hpp`）。
// 没有独立字段：Lua 侧读 `Type`/`Variant`/`Entity` 时直接按引擎偏移从这块内存里读，
// 免得"句柄字段"与"交给引擎的字节"两份状态漂移（那正是最难查的一类 bug）。
struct EntityRefHandle {
    std::uint8_t storage[kEntityRefStorageSize];
};

// 与 `Font` 同类：`sprite` 指向本模块自己分配、也必须由本模块释放的 `ANM2`（`kSpriteObjectSize`
// 字节、16 字节对齐）；游戏只提供构造/析构入口，从不拥有这块内存。
//
// 批次 3 起这里还缓存 PC 的 `Sprite.Scale`/`Sprite.Color`/`Sprite.FlipX` 三个**可写属性**
// （EID 在 `features/eid_api.lua:1368`、`main.lua:949`/`1026` 直接给它们赋值）。这三项**只写进
// 本句柄**、不回写 `ANM2`：它们对应的对象偏移没有证据（见 `sprite_api.cpp` 的 `__newindex`
// 注释），而猜一个偏移写进我们自己分配的对象同样是踩内存。
//
// --- `source`：句柄**来源/所有权**标记（2026-09-12，批次 5 `Entity:GetSprite()`）-----------
//
// `Sprite` 句柄现在有两种来源，**释放语义完全相反**：
//
//   * `kSpriteSourceRuntimeOwned` —— Lua 的 `Sprite()` 构造出来的对象：内存由本模块
//     `malloc`、由引擎 ctor 构造，`__gc` 必须调 `~ANM2()` 再 `free`（原行为，不变）；
//   * `kSpriteSourceEngineEntity` —— `Entity:GetSprite()` 借出来的对象：它是**引擎实体内部的
//     成员**（`Entity + kEntitySpriteOffset`，实体自己拥有这块内存、自己负责析构）。
//     `__gc` **绝不能**调 `~ANM2()`、**绝不能** `free` —— 那会把引擎的实体对象拆掉/把一块
//     不是 malloc 基址的地址交给 `free`。
//   * `kSpriteSourceEngineGridEntity`（批次 298，2026-10-03）—— `GridEntity:GetSprite()` /
//     `GridEntityRock:GetSprite()` 借出来的对象：**同一个形状**，只是来源对象是**网格实体**
//     （`GridEntity + kGridEntitySpriteOffset` 那个内嵌 `ANM2`）⇒ 释放语义与上一条**完全一样**
//     （什么都不做），重新解析时的存活判据换成 `IsLiveGridEntityPointer`（网格实体随时可能
//     被销毁：石头炸掉、换房间重建）。
//
// 因此 `source` 是"析构时放不放手"的唯一依据，也是"每次访问要不要重新解析"的依据：
// 引擎对象随时可能随实体消失，所以 `owner`（来源实体指针）也要存下来，每次访问都
// **重新校验**实体仍然活着，再重新算出 `owner + kEntitySpriteOffset`（句柄里的 `sprite`
// 只当身份缓存，不作为解引用依据，避免句柄跨帧后指向已释放的实体）。
// ---- `RoomDescriptor` / `RoomDescriptorList`（地基二期，2026-09-15）--------------
//
// PC 的 `Level:GetCurrentRoomDesc()` / `GetRoomByIdx()` 返回 `RoomDescriptor`，
// `Level:GetRooms()` 返回 `RoomDescriptorList`（有 `.Size` 与 `:Get(i)`）。
//
// **字段偏移不是猜的**：来自布局表 + 真机行为验证（`tools/layout_tables/room_descriptor.json`，
// 每条都带可复核证据）：`+0x00` GridIndex、`+0x04` SafeGridIndex、`+0x08` ListIndex、
// `+0x10` Data（指向房间配置，其中 `Data+0x08` 是 Type）、`+0x4c` VisitedCount、`+0x50` Clear。
// 描述符数组**内联在 Level 对象里**：基址 `Level + 0x18`、步长 `0x100`、
// 元素个数在 `Level + 0x21510`（真机实测：11 个已分配槽位的 ListIndex 恰好是 0..10）。
//
// 句柄只存**描述符地址**（引擎拥有的内存，按 `SpriteHandle` 的先例用 `void*`），
// 不存字段快照 —— 这样 `Clear` 之类的状态变化
// 能被后续读取看到，而不是拿到一份过期拷贝。
struct RoomDescriptorHandle {
    void* descriptor;
};

// `Level:GetRooms()` 的返回值。句柄存 **Level(=Game) 地址**：`Size` 每次现读
// （房间会随探索增加），`:Get(i)` 再去数组里定位 —— 避免缓存出一个会过期的列表。
struct RoomDescriptorListHandle {
    void* level;
};

//: 批次 347（2026-10-04）：`RoomConfig::Spawn` 与 `RoomConfig::Entry` 两个视图。
//: 它们的**来源**是 `RoomDescriptor.Data.Spawns`（`RoomDescriptor_Data.Spawns`）：
//:   `Data + 0x50` = Spawn 数组首地址（步长 `0x18`）、`Data + 0x58` = 元素个数（**u16**）。
//: ★ 与 `RoomDescriptorHandle` 同形：句柄**真持**引擎内存地址（引擎拥有那块内存）⇒
//:   按本文件的约束摆在 `MusicHandle` 之后那一带。
//: ★ 这两个句柄**不加生命周期保护**（与 PC 一致：PC 交回的是指向配置对象内部的引用）；
//:   引擎在回调之间重排/销毁配置对象时旧句柄即失效 —— 已知口径，写在这里免得后人当缺陷查。
inline constexpr char kRoomConfigSpawnMetatable[] = "IsaacRuntime.RoomConfigSpawn";
inline constexpr char kRoomConfigEntryMetatable[] = "IsaacRuntime.RoomConfigEntry";

struct RoomConfigSpawnHandle {
    void* spawn;   // `RoomConfig::Spawn const*`（引擎拥有的内存）
};

struct RoomConfigEntryHandle {
    void* entry;   // `RoomConfig::Entry const*`（指向 `Entries` 数组内部）
};

struct EntityLifetimeToken;
struct SpriteHandle {
    void* sprite;
    // 仅 `kSpriteSourceEngineEntity` / `kSpriteSourceEngineGridEntity` 非空：
    // 借出这个 sprite 的引擎实体（或网格实体）地址。
    void* owner;
    std::uint8_t source;
    float scaleX;
    float scaleY;
    float colorRed;
    float colorGreen;
    float colorBlue;
    float colorAlpha;
    // `Color` 的第 5/6/7 个分量（`RO/GO/BO`）。2026-09-16 起随 tint 一起回写引擎：PC 的
    // `sprite.Color = Color(r,g,b,a,ro,go,bo)` 是**整体替换**，只写 tint 会把上一份偏移量留在
    // 引擎对象里（EID 传的是 `0,0,0`，留旧值就会出现它没要求过的颜色偏移）。
    float colorOffsetRed;
    float colorOffsetGreen;
    float colorOffsetBlue;
    std::uint8_t flipX;
    std::uint8_t hasScale;
    std::uint8_t hasColor;
    std::uint8_t hasFlipX;
    // 2026-10-14：实体借出Sprite强持同一个token；native D2退役后拒绝旧引用。
    EntityLifetimeToken* lifetime{};
};

// `SpriteHandle::source` 的取值（放在结构体之后，避免读取顺序上的疑问）。
inline constexpr std::uint8_t kSpriteSourceRuntimeOwned = 0;
inline constexpr std::uint8_t kSpriteSourceEngineEntity = 1;
//: 批次 298：来源是**网格实体**（`GridEntity:GetSprite()`）—— 释放语义与
//: `kSpriteSourceEngineEntity` 相同（都不放手），只有"重新解析时的存活判据 + 偏移"不同。
inline constexpr std::uint8_t kSpriteSourceEngineGridEntity = 2;

// `Entity` / `EntityPlayer`：**必须**保存原生指针 —— 与上面 `Game`/`Level`/`Room` 的占位句柄
// 不同，玩家 1 与玩家 2 只有指针能区分，而且 `EntityPlayer` 的方法（`HasCollectible`）本来
// 就要以 `this` 调用引擎方法。代价是句柄可能持有过期指针，所以每一次字段/方法访问都重新做
// 可读性 + vptr 校验，校验失败一律返回安全值而不是解引用（见 `interfaces/lua/isaac_api.cpp`）。
struct EntityLifetimeToken {
    std::uintptr_t entity{};
    bool alive{};
};
struct EntityHandle {
    void* entity;
    EntityLifetimeToken* lifetime{}; // userdata的uservalue强持token，D2退役后拒绝地址复用。
};

// `ItemConfig`：与 `EntityHandle` 同理，句柄必须保存原生地址 —— 但这里的地址是**内嵌对象**
// 的地址（`IC = Manager + kManagerItemConfigOffset`，加法，见 `runtime_constants.hpp`），
// 引擎里不存在指向它的指针。
//
// `items`/`count` 是**缓存**，只为让"每个句柄对应哪一份向量"可核对；**每一次**访问都会从
// 引擎基址重新解引用整条链路并重新读 begin/end，缓存的这两个值只用来判断"句柄是否已经过期"
// （换局、Manager 重建、ItemConfig 重新 `Init` 都会让它们与现场不一致）。
struct ItemConfigHandle {
    void* config;
    void* items;
    std::uint64_t count;
    // 句柄创建时"收藏品向量是否已经建立"（2026-09-12）。两种情况必须分开处理：
    //   * 创建时**向量还没建立**（`begin == 0`，真机报告 `01789226184`：EID 在加载期就取
    //     `Isaac.GetItemConfig()`）⇒ `items`/`count` 记为 0，访问时**允许现读**，
    //     否则这个句柄一开局就作废、EID 的 `EID.itemConfig` 直接变成死的；
    //   * 创建时向量**已经建立** ⇒ 沿用"begin/count 必须与现场一致"的过期判据
    //     （换局后 `ItemConfig::Init` 会重排向量，旧句柄必须自证过期）。
    std::uint32_t itemsWereReadable;
    std::uint32_t reserved;
};

// `ItemConfig::Item`：条目就是向量元素（反汇编证实 `ldr x0,[begin, w1, uxtw #3]`），所以
// 句柄存的是那个元素的地址，外加"它属于哪条向量的哪个下标"这三项身份信息。访问时重新解析
// 整条链路并核对"这条向量的 begin 没变、下标处的元素还是同一个地址"，而不是盲解引用一个
// 可能过期的指针（与 `EntityHandle` 的 vptr 校验同一风格）。
//
// `beginOffset` 必须存下来（而不是从 `kind` 反推）：`kind` 与向量的对应关系只对
// COLLECTIBLE(1)/TRINKET(2) 有证据，卡牌/药丸/无道具条目的编号没有；存偏移则与 kind 无关。
struct ItemConfigItemHandle {
    void* item;
    void* items;
    std::uint32_t beginOffset;
    std::uint32_t index;
};

} // namespace LuaRuntime

// 第七批：仅额外网格Sprite借用使用扩展userdata；SpriteHandle本身大小不变。
namespace LuaRuntime { inline constexpr std::uint8_t kSpriteSourceEngineGridExtra=3; }
