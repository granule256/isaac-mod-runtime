#include "interfaces/lua/api700_bindings.hpp"
#include "interfaces/lua/api700_options.hpp"
#include "interfaces/lua/api600_values.hpp"
#include "interfaces/lua/api600_game.hpp"
#include "interfaces/lua/api600_entityptr.hpp"
#include "interfaces/lua/api600_config.hpp"
#include "interfaces/lua/api600_containers.hpp"
#include "interfaces/lua/api600_bindings.hpp"
#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/api600_fields.hpp"
#include "interfaces/lua/api400_bindings.hpp"
#include "interfaces/lua/api400_seeds.hpp"
#include "interfaces/lua/api400_fields.hpp"
#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/api500_entities.hpp"
#include "interfaces/lua/api400_params.hpp"
#include "interfaces/lua/api300_bindings.hpp"
#include "interfaces/lua/api200_main.hpp"
#include "interfaces/lua/api200_bindings.hpp"
#include "interfaces/lua/api100_bindings.hpp"
#include "interfaces/lua/api100_strings.hpp"
#include "interfaces/lua/rplus_options.hpp"
#include "interfaces/lua/rplus_extended_fields.hpp"
#include "interfaces/lua/rplus_content_names.hpp"
#include "interfaces/lua/rplus_entity_fields.hpp"
#include "interfaces/lua/rplus_method_bindings.hpp"
#include "interfaces/lua/rplus_health_api.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/rplus_player_api.hpp"
// 批次 184：`AddressBitsForEngineArgument` 用 `std::memcpy` 做"地址 → 位模式"的转换
// （理由见那个函数上方的注释：门禁按 `reinterpret_cast` 字面记账，而这里不是碰引擎内存）。
#include <cstring>

#include "interfaces/lua/api_call_stats.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/object_pointer_identity.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "interfaces/lua/api_sequence_probe.hpp"
#include "interfaces/lua/engine_call_trampoline.hpp"
#include "interfaces/lua/entity_ref_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/engine_method_api.hpp"
#include "interfaces/lua/engine_method_lookup.hpp"
#if defined(__SWITCH__)
#include "infrastructure/relay/entry_relay_binding.hpp"
#endif
#include "interfaces/lua/hooked_engine_entry.hpp"
#include "infrastructure/relay/entry_relay_hook_adapter.hpp"
#include "game_observer.hpp"
#include "interfaces/lua/input_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"  // 引擎调用层（111：调引擎只在这里转换签名）
#include "infrastructure/console/console_panel.hpp"
#include "infrastructure/console/console_bridge.hpp"   // 游戏控制台（121：Isaac.ExecuteCommand 的真实现）
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/rng_api.hpp"
#include <type_traits>
#include "interfaces/lua/bitset128_api.hpp"

#include "interfaces/lua/mod_api.hpp"
#include "interfaces/lua/callback_table_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/native_state_fallback.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"
// 批次 207：`Isaac.GetEntityTypeByName/GetEntityVariantByName` 的名字表
// （`tools/generate_entity_name_table.py` 生成，来源与本批的取舍见生成器文档头）。
// `runtime/source` 在 include 路径上（`common.mk` 的 `-I$(ROOT_SOURCE)`），
// 与 `lua_runtime.cpp` 引 `program/doc_lua_enum_data.hpp` 同一条路。
#include "program/entity_name_table.hpp"
// 批次 240（2026-09-30）：`Isaac.Get*ByName` 名字表一族（收藏品 / 卡牌 / 药丸 / 角色 / 挑战）。
// 与上面那张实体名表同一条路：表由 `tools/generate_isaac_name_tables.py` 从
// `tools/isaac_name_source/*.txt`（**追踪在仓库里**）生成，源数据来自游戏 dump 的
// XML + `stringtable.sta`。为什么不能"遍历引擎的 ItemConfig 比名字"见生成器文档头。
#include "program/isaac_name_tables.hpp"
// 批次 401：`Isaac.GetPlayerTypeByName` 的**运行时追加层**（模组 `content/players.xml` 声明的
// 自定义角色）。静态表是本体契约快照，查不到模组角色；追加层在装载期按引擎喂入顺序补上。
#include "program/mod_player_names.hpp"
// 批次 404（2026-10-07）：`Isaac.GetItemIdByName` / `GetTrinketIdByName` / `GetCardIdByName`
// 三条的**运行时追加层**（模组 `content/items.xml` / `content/pocketitems.xml` 声明的自定义
// 道具 / 饰品 / 卡牌）。与 401 同构：静态表先查（本体优先），未命中再落到这里。
#include "program/mod_content_names.hpp"
// 批次 195：三条坐标变换的算术只有一份实现（`TransformWorldPosition` /
// `TransformScreenToWorldPosition`，与 `Room:WorldToScreenPosition` 共用）——
// 它住在 `remaining_api.cpp`（`Level`/`Room`/`ItemPool` 那个 TU），这里只声明。
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/vector_api.hpp"
// `Isaac.RenderScaledText` 的绘制本体在 `font_api.cpp`（字体句柄的生命周期、`Font:Load` 的
// 路径归一化、四个绘制变体与绘制探针都归那个 TU）：这里只做参数校验 + 转调。
#include "interfaces/lua/font_api.hpp"
// `Entity:GetSprite()` 的实现体在 `sprite_api.cpp`（`Sprite` 句柄的布局与所有权都在那里，
// 见 `lua_object_handles.hpp` 的 `SpriteHandle`）：这里只做实体校验 + 推入一个句柄。
#include "interfaces/lua/sprite_api.hpp"

#include "application/callback/callback_dispatcher.hpp"
#include "application/callback/callback_registry.hpp"
#include "domain/callback/callback_descriptor.hpp"

#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "infrastructure/call/managed_update_snapshot.hpp"
#include "lua_runtime_state.hpp"
#include "room_descriptor_layout.hpp"
#include "entity_layout.hpp"
// 批次 301（2026-10-03）：`CacheFlags` 那一行的偏移在**两处**各有一个具名常量（本文件用
// `runtime_constants.hpp` 的 `kEntityPlayerCacheFlagsOffset`，布局表生成物是
// `layout::kEntity_PlayerCacheFlagsOffset`）—— 同一个值写两遍迟早漂移 ⇒ 编译期钉死
// （与批次 293 对 `Entity` 三个字节的 `static_assert` 同一做法）。
#include "entity_player_layout.hpp"
#include "runtime_constants.hpp"

// `svcQueryMemory`/`MemoryInfo`/`Perm_R` 只存在于设备侧（libnx）。宿主构建没有它们，
// 可读性检查退化为保守版本，见 `IsEngineMemoryReadable`。
#if defined(__SWITCH__)
#include "lib/nx/nx.h"
#endif

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <atomic>
#include <cstring>
#include <limits>
#include <string>

extern "C" {
#include <lauxlib.h>
#include "probe_gate.hpp"
}

//: 引擎调用层的短别名（批次 111）：本文件里"把已核对过的地址变成可调用签名"只走它。
//: ★ 与 `tools/engine_offset_abi_report.py` 的关系：那个体检工具认"我们按哪个签名调"就看这次转换
//:   —— 它已支持"类型写在模板实参上"的拼法（`AsFunction<XxxFn>`），见批次 110 的修补。
namespace engine_call = isaac::runtime::engine_call;

namespace isaac::runtime {
int ExtendedItemConfigWrite(lua_State*);

// 批次 065：`Entity:TakeDamage` 的实现体住在文件后半段（它用到的几个校验助手在那之前才定义），
// 而绑定表 `kEntityHandlers` 在文件前半段的匿名命名空间里 —— 所以这一份声明必须放在
// **外部作用域**（放在匿名命名空间里会给它内部链接，定义对不上）。
[[nodiscard]] int EntityTakeDamage(lua_State* state);
// 批次 271（2026-10-02）：`needs_new_receiver` 桶头部三条（引擎里都有同名方法，见常量表注释）。
[[nodiscard]] int EntitySetColor(lua_State* state);
[[nodiscard]] int EntityAddCharmed(lua_State* state);
[[nodiscard]] int EntityPlayerUseActiveItem(lua_State* state);
// 批次 273（2026-10-02）：`needs_new_receiver` 桶里"参数全是标量/Vector/EntityRef"的 8 条
// （选批口径见 `runtime_constants.hpp` 的批次 273 段：只收"同名方法只有一个类有"的）。
[[nodiscard]] int EntityAddFreeze(lua_State* state);
[[nodiscard]] int EntityAddPoison(lua_State* state);
[[nodiscard]] int EntityPlayerAddBlueSpider(lua_State* state);
[[nodiscard]] int EntityPlayerAddGoldenHearts(lua_State* state);
[[nodiscard]] int EntityPlayerAddMinisaac(lua_State* state);
[[nodiscard]] int EntityPlayerAddPill(lua_State* state);
[[nodiscard]] int EntityPlayerAnimateAppear(lua_State* state);
[[nodiscard]] int EntityPlayerDropTrinket(lua_State* state);
// 批次 274（2026-10-02）：清桶批（选批口径见 `runtime_constants.hpp` 的批次 274 段）。
[[nodiscard]] int EntityAddFear(lua_State* state);
[[nodiscard]] int EntityAddHealth(lua_State* state);
[[nodiscard]] int EntityRemoveStatusEffects(lua_State* state);
[[nodiscard]] int EntityPlayerAddBoneHearts(lua_State* state);
[[nodiscard]] int EntityPlayerAddFriendlyDip(lua_State* state);
[[nodiscard]] int EntityPlayerAddPrettyFly(lua_State* state);
[[nodiscard]] int EntityPlayerAnimateTrapdoor(lua_State* state);
[[nodiscard]] int EntityPlayerCanPickSoulHearts(lua_State* state);
[[nodiscard]] int EntityPlayerDonateLuck(lua_State* state);
[[nodiscard]] int EntityPlayerRemoveGoldenBomb(lua_State* state);
[[nodiscard]] int EntityPlayerRemoveGoldenKey(lua_State* state);
// 批次 275（2026-10-02）：实体的**标志位读写**两条（`needs_forensics` 桶的头部）。
// ★ 这两条**不需要新偏移** —— 写的就是 `Entity:HasEntityFlags` 已经在用的那个 64 位标志字
//   （`kEntityFlagsOffset`）；语义来自 PC 绑定函数的反汇编（见实现处注释）。
[[nodiscard]] int EntityAddEntityFlags(lua_State* state);
[[nodiscard]] int EntityClearEntityFlags(lua_State* state);
// 批次 277（2026-10-02）：`Entity:GetEntityFlags()` —— 批次 275 那两条**写**侧的同族**读**侧
// （`field_row` 桶里那 1 处）。★ 同样不需要新偏移：读的就是 `kEntityFlagsOffset` 那一格。
[[nodiscard]] int EntityGetEntityFlags(lua_State* state);
// 批次 278（2026-10-02）：`EntityPlayer` 族 5 条（参数个数与引擎符号完全对齐的那一批，
// 选批口径见 `runtime_constants.hpp` 的批次 278 段）。
[[nodiscard]] int EntityPlayerThrowHeldEntity(lua_State* state);
[[nodiscard]] int EntityPlayerAddSwarmFlyOrbital(lua_State* state);
[[nodiscard]] int EntityPlayerAddItemWisp(lua_State* state);
[[nodiscard]] int EntityPlayerUsePill(lua_State* state);
[[nodiscard]] int EntityPlayerAddBlueFlies(lua_State* state);
// 批次 284（2026-10-02）：`EntityPlayer` 的两条 0 参布尔查询（选批口径与"更正批次 273 那句话"
// 的完整证据写在 `runtime_constants.hpp` 的批次 284 段）。
[[nodiscard]] int EntityPlayerIsHoldingItem(lua_State* state);
[[nodiscard]] int EntityPlayerIsExtraAnimationFinished(lua_State* state);
// 批次 328（2026-10-03）：`EntityPlayer:GetShootingInput()` / `GetShootingJoystick()`。
// ★★ 两条在 PC 上**共用同一份实现**（两个名字表项指向同一个 VA `0x741B00`）⇒ 这里也是
//   同一段代码的两张门面（定义在文件后半段的 `EntityPlayerShootingInputCommon`）。
// ★ 声明必须放在**这一块**（第 90 行的 `namespace isaac::runtime` 里、匿名命名空间之外），
//   与 `EntityTakeDamage` 那些兄弟一样 —— 放进下面的匿名命名空间会变成**内部链接**，
//   而定义在文件后半段（匿名命名空间之外）⇒ `-Wundefined-internal` 直接编译失败。
[[nodiscard]] int EntityPlayerGetShootingInput(lua_State* state);
[[nodiscard]] int EntityPlayerGetShootingJoystick(lua_State* state);
// 批次 332（2026-10-03）：`EntityPlayer:GetMovementJoystick()` —— 与上面两条**同型**
// （引擎返回 `Vector` 的 HFA ⇒ 手写；PC 侧 `GetMovementInput` 与它共用同一个绑定 VA `0x741880`，
//  而引擎里那个函数叫 `get_movement_input` —— **名字不一样，靠逐条对照函数体定案**）。
[[nodiscard]] int EntityPlayerGetMovementJoystick(lua_State* state);
// 批次 334（2026-10-03）：`EntityPlayer:CheckFamiliar(FamiliarVariant, TargetCount, RNG,
//  SourceItemConfigItem = nil, FamiliarSubType = -1)` —— 五个形参，后两个是**非 0 缺省值**
// （`nil` / `-1`）⇒ 数据行那条路缺两种表达能力 ⇒ 手写（账目与反汇编证据见
// `runtime_constants.hpp` 的批次 334 段）。**同样声明在这一块**（理由见上面 328 那段）。
[[nodiscard]] int EntityPlayerCheckFamiliar(lua_State* state);
// 批次 337（2026-10-04）：`EntityPlayer:FireTear(Position, Velocity, CanBeEye = true,
//  NoTractorBeam = false, CanTriggerStreakEnd = true, Source = nil, DamageMultiplier = 1)`
//  —— 契约 7 个形参、引擎只有 5 个（三个布尔被打包成一个 `u32` 位掩码，且 `Velocity`
//  是**按值**的 HFA）⇒ 数据行那条路缺两种表达能力 ⇒ 手写。
//  **同样声明在这一块**（理由见上面 328 那段）。★ 语料 **4 处**，全是 5 参写法。
[[nodiscard]] int EntityPlayerFireTear(lua_State* state);
// 批次 339（2026-10-04）：`EntityFamiliar:FireProjectile(Vector Dir)` —— 引擎真身
// `Entity_Familiar::fire_projectiles(Vector2 const&, bool)` @ `0xB06FC` **逐字存在**
// ⇒ 与 334/337 同一条路：手写转发（契约只有 1 个形参、引擎多一个隐藏 bool）。
// **同样声明在这一块**（理由见上面 328 那段）。★ 语料 1 处。
[[nodiscard]] int EntityFamiliarFireProjectile(lua_State* state);
int EntityFamiliarGetOrbitPosition(lua_State* state);
int EntityFamiliarRecalculateOrbitOffset(lua_State* state);
int EntityFamiliarAddToOrbit(lua_State* state);
int EntityFamiliarRemoveFromOrbit(lua_State* state);
// 批次 344（2026-10-04）：`EntityPlayer:AnimateCollectible(CollectibleType, AnimName?, SpriteAnimName?)`
//  —— **手写**，缺两种表达能力：① 字符串实参（`EngineArgKind` 没有这一档）；
//  ② 两个**非空字符串缺省**（`EngineCallShapeRow::optionalArgumentCount` 只表达"省略即 0"）。
//  ★★★ **缺省必须传字面串** `"Pickup"` / `"PlayerPickupSparkle"` —— 引擎把它们喂
//  `ANM2::Play(char const*, bool)`，那里对名字做 `strcmp`、**对 null 无检查** ⇒ 传 `nullptr`
//  会当场崩（证据见 `runtime_constants.hpp` 的 `kEntityPlayerAnimateCollectibleOffset` 段）。
//  ★ 引擎侧是**改名**的 `Entity_Player::AnimatePickup(eCollectibleType, …)`（同族 5 条重载）。
//  **同样声明在这一块**（理由见上面 328 那段）。
[[nodiscard]] int EntityPlayerAnimateCollectible(lua_State* state);
// 批次 346（2026-10-04）：`Entity:AddVelocity(Vector[, boolean IgnoreTimeScale])`（**20 处**）。
// ★★ **手写纯算法**（不调引擎）：Switch 侧**没有可调真身**（符号 0 命中 / NRO 原始字节 0 命中），
//   PC 绑定 `0x422B60` 的算式是 `friction = this[0x2c4]; if (friction == 0.0f) return;
//   k = bool ? 1.0f : this[0x2f4]; this[0x2b8] += (k*v.x)/friction; ...`
//   ⇒ 我们按同一算式直接读写三格（见 `runtime_constants.hpp` 的批次 346 段）。
//   ★ **不要**调 `TimeScaledFriction`：PC 的 `AddVelocity` 根本没调它，调了反而与 PC 不一致。
//   ★★ 这条**推翻了旧负结果**「两侧摩擦模型不同 ⇒ 不能做」（实为同一族，按 PC 算式复刻即一致）。
// **声明必须放在这一块**（`namespace isaac::runtime` 内、匿名命名空间**之外**）：放进匿名命名空间
// 会变成内部链接，而定义在文件后半段 ⇒ `-Wundefined-internal` 直接编译失败（见本块上方注释）。
[[nodiscard]] int EntityAddVelocity(lua_State* state);
// 批次 340（2026-10-04）：`Isaac.Spawn(...)` —— 见 `GameSpawn` 上方的说明。
int IsaacSpawn(lua_State* state);
// 批次 345（2026-10-04）：`Isaac.Explode(Vector pos, Entity source, float damage)`。
// ★★ **为什么手写**：引擎真身 `Game::BombExplosionEffects @ 0x355C68` 有 **9 个形参**
//   ⇒ **第 9 格 `bool` 走栈**（`ldrb w21,[x29,#0x60]`），而通用跳板只填 `x0..x7`/`d0..d7`、
//   **填不了栈**；且第 4 格是 16 字节**按值**的 `bitset128_t`（走 `x2:x3`）。
//   ⇒ 用 `AsFunction<BombExplosionEffectsFn>` 让编译器按签名把第 9 格放栈（与 340 的 `SpawnEx` 同路）。
// **同样声明在这一块**（理由见上面 328 那段）。★ 语料 **5 处**，全点号调用。
int IsaacExplode(lua_State* state);
//: 三条的取址助手（定义在文件后半段，与 `EntityTakeDamageMethod` 同一种接法）。
[[nodiscard]] std::uintptr_t EntitySetColorMethod() noexcept;
[[nodiscard]] std::uintptr_t EntityAddCharmedMethod() noexcept;
[[nodiscard]] std::uintptr_t EntityPlayerUseActiveItemMethod() noexcept;
//: 取"接收者实体"（接受 `Entity` / `Entity_Player` 两个元表）。
//: 返回 0 表示**句柄已失效**（已消失）—— 那种情况一律静默不做事，不报错。
//: "参数根本不是实体"是另一回事：那时直接报错（模组写错了，PC 也会报）。
[[nodiscard]] std::uintptr_t EntityReceiverOrError(lua_State* state, const char* api);
//: 批次 271 起的**共用**取址助手（定义在文件后半段，与 `EntityTakeDamageMethod` 同一种接法）：
//: 模块基址 + 偏移 + **16 字节入口原文**逐字节核对。批次 273 的八条也用它。
[[nodiscard]] std::uintptr_t EntityMethodByExpectedBytes(std::uintptr_t offset,
                                                        const std::array<u8, 16>& expected) noexcept;

//: 两个入口的取址助手（定义在文件后半段；`EntityTakeDamage` 要用）。
[[nodiscard]] std::uintptr_t EntityTakeDamageMethod() noexcept;
[[nodiscard]] std::uintptr_t EntityPlayerTakeDamageMethod() noexcept;

// **把我们自己 API 的报错消息也留证**（2026-09-12 第十一轮）。
//
// 背景：探针 `ISAACERR` 的"错误文本"只来自 `CaptureLuaErrorTop`（`lua_pcallk` 失败路径），
// 而**我们自己的 API 用 `luaL_error` 报的错不走那条路** —— 真机报告 `01789219353` 因此只给出
// 一个 `.`，无法定位是哪个 API、哪一句。
//
// 做法（2026-09-15 改）：**直接调 `luaL_error` 就行** —— `lua_runtime_state.hpp` 已经把它定义成宏，
// 转调独立编译的 `LuaRuntime::ReportAndRecordLuaError`，那条路径本身就是"先把整段消息记进探针
// 缓冲区（`RecordLuaErrorText`）、再真正抛错"，并且会带上 `file:line:` 位置前缀。
//
// ★ 这里原先有个**本 TU 私有的模板** `ReportApiError(...)`，做的是同一件事，已删除。原因很具体：
// 编译器把模板体在**每个调用点整个内联** —— 每次都在栈上建一个 256 字节缓冲区、清零、把消息拷
// 进去，再调 `RecordLuaErrorText`。实测 `IsaacGetFrameCount`（只做"检查参数个数 + 压一个整数"）
// 编出来 **152 字节**，其中绝大部分就是这段内联代码；改走宏那条路径后，调用点只剩
// "取字符串地址 + `bl`"。这是成本压缩最直接的一笔：API 还要成百上千地长，每个报错点省约 85 字节。

// 探针（2026-09-12 第九轮）：EID 的 `hasDescription`（`eid_api.lua:1065`）第一件事就是
// `EID:EntitySanityCheck(entity)` + `entity.Type`，只有在它返回真之后才会走到
// `EID:getEntityData`。真机读数显示 `Entity.GetData` **一次都没被调用**，所以要么
// `hasDescription` 的候选实体全是"没有 Type 的 udata"，要么它压根没被调用。
// 这两个读数（Type 字段被读取的次数 + 最近一次的值）能一次分开。
std::atomic<std::uint32_t> g_EntityTypeFieldReads{0};
std::atomic<std::uint32_t> g_LastEntityTypeValue{0};
std::atomic<std::uint32_t> g_LastEntityVariantValue{0};
std::atomic<std::uint32_t> g_LastEntitySubTypeValue{0};
// 以**字符串键**读取实体字段的次数（`entity.XXX` 的 XXX 不是已知整数/字段名时也会计数）。
// 用途：EID 的 `EID:getEntityData(entity, key)` 若走 `entity:GetData()`，我们会看到 `Entity.GetData`
// 位；若它走的是别的字段名，这里能看到"确实发生过字符串字段读取"。
std::atomic<std::uint32_t> g_EntityStringFieldReads{0};
std::atomic<std::uint64_t> g_LastEntityStringFieldHead{0};

// `Pickup.Touched` 的探针（2026-09-12，动作三）：EID 用它当"摘掉隐瞒"的条件
// （`eid_api.lua:3338`/`3340`），而这个字段的偏移本身还是"待真机确认"的猜测。
std::atomic<std::uint32_t> g_EntityPickupTouchedReads{0};
std::atomic<std::uint32_t> g_EntityPickupTouchedTrue{0};
std::atomic<std::uint32_t> g_LastEntityPickupTouchedRaw{0};

// 批次 212（2026-09-30）：**玩家字段写**的现场。为什么必须有它：字段写守卫是"**报错**"而不是
// "静默忽略"，所以**模组写了我们没实现的字段 ⇒ 整条回调当场中断**（MCM 的菜单就是这么画不出来的：
// 它在渲染回调里 `player.Velocity = vecZero`）。写完能不能画出来要靠眼睛，但"它到底写了什么、
// 有没有被我们拒绝"必须**不需要眼睛**就能读到 —— 就是这五个格子。
//   下标 0 = `Velocity`、1 = `Position`、2 = `ControlsEnabled`、3 = `ControlsCooldown`。
// ★ 批次 245（2026-10-01）：`4` → `6` —— 追加 `HitPoints`(4) / `MaxHitPoints`(5) 两个桶。
//   口径：**只能往后追加**，已有桶号不许改（读数工具与门禁都按桶号取）。
//   同步改的另外两处：`tools/read_device_state_via_gdb.py` 的 `write_names`/读取长度/
//   `known_hashes`，与 `runtime/tests/test_entity_field_write_probe.py`。
// ★ 批次 246（2026-10-01）：`6` → `7` —— 追加 `Scale`(6)。
// ★ 批次 405（2026-10-07）：`7` → `13` —— 追加六个战斗属性桶（顺序与 `EntityNewIndex` 的表一致）：
//   `7=MaxFireDelay`、`8=ShotSpeed`、`9=Damage`、`10=MoveSpeed`、`11=Luck`、`12=TearRange`。
std::atomic<std::uint32_t> g_EntityFieldWrites[25];
std::atomic<std::uint32_t> g_EntityFieldWriteRejected{0};
std::atomic<std::uint32_t> g_LastEntityFieldWriteName{0};  // 最近一次写的字段名（FNV-1a 32 位哈希）




// `Entity.FrameCount` 的探针读数（2026-09-12 第八轮；语义见该字段实现处的注释）。
std::atomic<std::uint32_t> g_FrameCountProbeReads{0};
std::atomic<std::uint32_t> g_FrameCountPositive{0};
std::atomic<std::uint32_t> g_LastGameFrameCount{0};
std::atomic<std::uint32_t> g_LastEntitySpawnFrame{0};
std::atomic<std::uint32_t> g_LastFrameCountResult{0};

// --- `Isaac.GetItemConfig()` 的探针（2026-09-12 第八轮）------------------------------
//
// 真机报告 `01789227137`：加载期"最后调用的 API"= 位 17（本函数），之后 EID 就断了，
// 但**我们到底返回了 nil 还是对象**从负载里看不出来（错误消息通道给的是 1 字节残留）。
// 这个探针把三种结局分别记下来：
//   bit0 链路解析成功（`ResolveItemConfig` 拿到了 ItemConfig 地址）
//   bit1 收藏品向量此刻可读
//   bit2 因为向量还没建立（`begin == 0`）而走了"返回对象"那条
//   bit3 因为参数明显非法（长度不是 8 的倍数 / 超上限）而返回 nil
//   bits8..31 调用次数（封顶 0xFFFFFF）
std::atomic<std::uint32_t> g_GetItemConfigProbe{0};

void RecordGetItemConfigForProbe(std::uint32_t flags) noexcept {
    (void)flags;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    std::uint32_t current = g_GetItemConfigProbe.load(std::memory_order_relaxed);
    std::uint32_t calls = (current >> 8) + 1;
    if (calls > 0xFFFFFFu) {
        calls = 0xFFFFFFu;
    }
    g_GetItemConfigProbe.store((calls << 8) | (flags & 0xFFu), std::memory_order_relaxed);
#endif  // EXL_DIAGNOSTIC_PROBES
}


std::uint32_t GetItemConfigProbeSnapshot() noexcept {
    return g_GetItemConfigProbe.load(std::memory_order_relaxed);
}

EntityFieldProbe EntityFieldProbeSnapshot() noexcept {
    // 见结构体注释：字符串键读取次数与最近一次键名（前 8 字节）。
    // （下面填的是同一个结构体的新字段）
    EntityFieldProbe probe{};
    probe.typeReads = g_EntityTypeFieldReads.load(std::memory_order_relaxed);
    probe.lastType = g_LastEntityTypeValue.load(std::memory_order_relaxed);
    probe.lastVariant = g_LastEntityVariantValue.load(std::memory_order_relaxed);
    probe.lastSubType = g_LastEntitySubTypeValue.load(std::memory_order_relaxed);
    probe.stringReads = g_EntityStringFieldReads.load(std::memory_order_relaxed);
    probe.lastStringHead = g_LastEntityStringFieldHead.load(std::memory_order_relaxed);
    probe.touchedReads = g_EntityPickupTouchedReads.load(std::memory_order_relaxed);
    probe.touchedTrue = g_EntityPickupTouchedTrue.load(std::memory_order_relaxed);
    probe.lastTouchedRaw = g_LastEntityPickupTouchedRaw.load(std::memory_order_relaxed);
    return probe;
}

FrameCountProbe FrameCountProbeSnapshot() noexcept {
    FrameCountProbe probe{};
    probe.reads = g_FrameCountProbeReads.load(std::memory_order_relaxed);
    probe.positive = g_FrameCountPositive.load(std::memory_order_relaxed);
    probe.gameFrameCount = g_LastGameFrameCount.load(std::memory_order_relaxed);
    probe.spawnFrame = g_LastEntitySpawnFrame.load(std::memory_order_relaxed);
    probe.result = g_LastFrameCountResult.load(std::memory_order_relaxed);
    return probe;
}

namespace {

using LuaRuntime::EngineModuleBase;
using LuaRuntime::EntityHandle;
using LuaRuntime::InManagedCallbackScope;
using LuaRuntime::ItemConfigHandle;
using LuaRuntime::ItemConfigItemHandle;
using LuaRuntime::kEntityMetatable;
using LuaRuntime::kEntityPickupMetatable;
using LuaRuntime::kEntityPlayerMetatable;
using LuaRuntime::kEntityProjectileMetatable;
using LuaRuntime::kEntityTearMetatable;
using LuaRuntime::kEntityBombMetatable;
using LuaRuntime::kEntityLaserMetatable;
using LuaRuntime::kEntityKnifeMetatable;
using LuaRuntime::kEntityNPCMetatable;
using LuaRuntime::kEntityFamiliarMetatable;
//: 批次 344（2026-10-04）：`EntityNPC.Pathfinder` 属性交回的 `PathFinder` 视图（元表 + 句柄）。
using LuaRuntime::kPathFinderMetatable;
using LuaRuntime::PathFinderHandle;
//: 批次 388（2026-10-07）：`EntityPlayer:GetEffects()` 的返回值（`TemporaryEffects` 视图）。
using LuaRuntime::kTemporaryEffectsMetatable;
using LuaRuntime::TemporaryEffectsHandle;
using LuaRuntime::kItemConfigItemMetatable;
using LuaRuntime::kItemConfigMetatable;
using LuaRuntime::kVectorMetatable;
using LuaRuntime::VectorHandle;

// 批次 195（2026-09-29）：`player.QueuedItem.Item` 要交回一个 `ItemConfig_Item` 句柄，而
// "把条目指针包成句柄"与"读一条 `ItemConfig` 向量"这两件事的实现在本文件**后面**的
// ItemConfig 段里（两处各写一份会漂移）⇒ 这里前置声明，定义仍在原处。
constexpr std::size_t kItemConfigMaximumItems = 4096;         // 733 的 5 倍余量
std::uintptr_t ResolveItemConfig(bool* chainResolved) noexcept;
//: 一条 `std::vector<ItemConfig::Item*>` 的只读视图（定义原本在下面的 ItemConfig 段，
//: 批次 195 起提到这里 —— `player.QueuedItem.Item` 要用同一个结构，两处各定义一份会漂移）。
struct ItemVectorView {
    std::uintptr_t begin;
    std::uintptr_t end;
    std::size_t count;
};
bool ReadItemVector(std::uintptr_t owner, std::uintptr_t beginOffset, std::uintptr_t endOffset,
                    ItemVectorView* view) noexcept;
void PushItemConfigItemHandle(lua_State* state, std::uintptr_t item, std::uintptr_t beginOffset,
                              std::uintptr_t itemsBegin, std::size_t index);
//: `player.QueuedItem.Item` 用的那段"按条目 `Type` 选向量、再线性找下标"逻辑（实现见
//: `PushQueuedItemTable`，紧跟 `PushEntityPlayerField` 之后）。
bool PushQueuedItemTable(lua_State* state, std::uintptr_t player);

int IsaacGetFrameCount(lua_State* state);
int IsaacGetTime(lua_State* state);
int IsaacDebugString(lua_State* state);
int IsaacIsInGame(lua_State* state);
int IsaacRunCallback(lua_State* state);
// 批次 268（2026-10-02）：`Isaac.RunCallbackWithParam`（同一族，多一个"过滤值"实参）。
int IsaacRunCallbackWithParam(lua_State* state);
int IsaacGetPlayer(lua_State* state);
int IsaacGetItemConfig(lua_State* state);
int IsaacFindByType(lua_State* state);
int IsaacFindInRadius(lua_State* state);
int IsaacCountEnemies(lua_State* state);
int IsaacCountBosses(lua_State* state);
// 批次 268（2026-10-02）：`Isaac.CountEntities`（调引擎 `EntityList::CountSpawned`，实现见文件后半）。
int IsaacCountEntities(lua_State* state);
// `Isaac.GetRoomEntities()`（批次 041，为 GoodTrip 补）。
int IsaacGetRoomEntities(lua_State* state);
// `Isaac.ExecuteCommand()`（批次 041：Switch 上没有控制台 ⇒ 明确降级，见实现处注释）。
int IsaacExecuteCommand(lua_State* state);
// `Isaac.GetCostumeIdByPath(path)`（批次 139：The Specialist for Good Items 的舞蹈服装要靠它反查 id）。
int IsaacGetCostumeIdByPath(lua_State* state);
// `Isaac.GetMusicIdByName(name)`（批次 148：同一个模组的"放歌"要靠它把曲目名换成引擎的曲目编号）。
int IsaacGetMusicIdByName(lua_State* state);
// 批次 207（2026-09-29）：`Isaac.GetScreenWidth()` / `GetScreenHeight()`（MCM 的界面摆位要用）。
int IsaacGetScreenWidth(lua_State* state);
int IsaacGetScreenHeight(lua_State* state);
// 批次 207（2026-09-29）：`Isaac.GetEntityTypeByName(name)` / `GetEntityVariantByName(name)`。
int IsaacGetEntityTypeByName(lua_State* state);
int IsaacGetEntityVariantByName(lua_State* state);
// 批次 240（2026-09-30）：名字表一族（消费方见各实现处的注释）。
int IsaacGetItemIdByName(lua_State* state);
int IsaacGetCardIdByName(lua_State* state);
int IsaacGetPillEffectByName(lua_State* state);
int IsaacGetPlayerTypeByName(lua_State* state);
int IsaacGetChallengeIdByName(lua_State* state);
int IsaacWorldToScreen(lua_State* state);
int IsaacWorldToRenderPosition(lua_State* state);
//: 批次 195 新增（catalog `0x0E01005F`）：PC 的 `Isaac.ScreenToWorld`。
//: ★ 规格建议的"Isaac 域空位 0x0014"**当时已被 `Entity:ToPlayer` 占用**（catalog 里 0x0001..0x005E
//:   连续无空洞）⇒ 按本项目既有习惯取 **max+1 = 0x005F**（"id 不复用"）。
int IsaacScreenToWorld(lua_State* state);
int IsaacGetPersistentGameData(lua_State* state);
int PersistentGameDataUnlocked(lua_State* state);
int PersistentGameDataGetBestiaryKillCount(lua_State* state);
int PersistentGameDataGetBestiaryDeathCount(lua_State* state);
int PersistentGameDataGetBestiaryEncounterCount(lua_State* state);
int PersistentGameDataAddBestiaryKill(lua_State* state);
int PersistentGameDataAddBossKilled(lua_State* state);
int PersistentGameDataIsBossKilled(lua_State* state);
int IsaacGetTrinketIdByName(lua_State* state);
int IsaacGetCallbacks(lua_State* state);
int IsaacLoadModData(lua_State* state);
int IsaacSaveModData(lua_State* state);
int IsaacRenderScaledText(lua_State* state);
// 批次 269（2026-10-02）：`Isaac.RenderText` / `Isaac.GetTextWidth` —— 与上面那条**同一份**
// 默认字体（契约 `Isaac.md:441` 明说 GetTextWidth 用的就是 RenderText 那个字体）。
int IsaacRenderText(lua_State* state);
int IsaacGetTextWidth(lua_State* state);
// 批次 261（2026-10-01，语料 API 恢复的 `glue_compose` 桶）：三条 PC 侧在"Lua 胶水层"实现的
// `Isaac` 全局表接口。★ `Isaac` 是**全局表**、模组一律按 `.` 调（`Isaac.GetChallenge()`）
// ⇒ 栈上**没有** `self`（与 `Game`/`Room` 的方法调用相反，别把两套口径混了）。
int IsaacGetChallenge(lua_State* state);
int IsaacConsoleOutput(lua_State* state);
// `Isaac.HasModData(modRef)` —— 声明在 `mod_api.hpp`、定义在 `mod_api.cpp`
//（那里才有 Mod 句柄与持久化），这里只挂绑定行。
// 批次 262：`Isaac.GetFreeNearPosition` / `Isaac.GridSpawn` —— **定义在 `remaining_api.cpp`**
//（格坐标换算、网格实体表、`Room::SpawnGridEntity` 的入口都住在那一个 TU 里），
// 声明由 `remaining_api.hpp` 带进来，这里只挂绑定行（`Isaac` 是全局表 ⇒ 按 `.` 调、栈上无 `self`）。
// 批次 265（2026-10-02，`glue_compose` 桶最大的一条）：`Isaac.GetSoundIdByName(name)` ——
// 与上面的 `IsaacGetMusicIdByName` 同一套（遍历 `Manager` 里那张表 + 比串 + 返回下标），
// 实现就在 `IsaacGetMusicIdByName` 后面。
int IsaacGetSoundIdByName(lua_State* state);

// Entity / EntityPlayer / EntityPickup
int EntityIndex(lua_State* state);
int EntityPlayerIndex(lua_State* state);
int EntityPickupIndex(lua_State* state);
// `EntityProjectile` 视图的 `__index`（批次 207）。
int EntityProjectileIndex(lua_State* state);
int EntityPickupIsShopItem(lua_State* state);
// `EntityPickup:CanReroll()`（批次 028，真实现：引擎方法 + 入口指纹）。
int EntityPickupCanReroll(lua_State* state);
int EntityToPlayer(lua_State* state);
int EntityToPickup(lua_State* state);
int EntityToFamiliar(lua_State* state);
// 批次 242（2026-09-30）：下转族（`ToNPC` / `ToTear` / `ToLaser` / `ToEffect` / `ToKnife`）。
int EntityToNpc(lua_State* state);
int EntityToTear(lua_State* state);
int EntityToBomb(lua_State* state);
int EntitySetSpriteFrame(lua_State* state);
int EntityTearResetSpriteScale(lua_State* state);
// 批次 281（2026-10-02）：`EntityTear` 视图 —— `Entity:ToTear()` 的返回值终于带上自己的元表，
// 于是 `EntityTear` 自己的方法（本批先接 `ChangeVariant`）能挂上去。此前压的是 `Entity` 元表
// ⇒ `t:ChangeVariant(...)` 报 "attempt to call a nil value"（语料 8 处）。
int EntityTearIndex(lua_State* state);
int EntityTearChangeVariant(lua_State* state);
// 批次 282（2026-10-02）：`EntityLaser` 视图 —— 照批次 281 给 `EntityTear` 立的那套六处接线
// 逐条复制。语料 `laser:SetActiveRotation(...)`（6 处）此前报 "attempt to call a nil value"，
// 根因同样是「`ToLaser()` 压的是 `Entity` 元表 ⇒ 它自己的方法没地方挂」。
int EntityLaserIndex(lua_State* state);
int EntityLaserSetActiveRotation(lua_State* state);
int EntityToLaser(lua_State* state);
int EntityToEffect(lua_State* state);
int EntityToKnife(lua_State* state);
// `Entity:ToProjectile()`（批次 207）：MCM 的 `modconfig.lua:220` 要用它换投射物视图。
int EntityToProjectile(lua_State* state);
// `EntityProjectile` 的字段分派（批次 207，只有 `ProjectileFlags` 一条）。
// 与 `PushEntityPickupField` 同形：由 `IndexEntity` 在 `EntityView::Projectile` 时调用，
// 定义在本文件后面（`IndexEntity` 之前只有这个声明）。
bool PushEntityProjectileField(lua_State* state, std::uintptr_t entity, const char* field);
int EntityGetData(lua_State* state);
int EntityGetSprite(lua_State* state);
int EntityPlayerHasCollectible(lua_State* state);
// `EntityPlayer:AddCollectible`（2026-09-14 新增，真实现）。声明与实现同在本单元（Isaac 家族）——
// 契约测试要求"家族方法体住在家族单元里、登记名与 catalog 的 id 一致"。
int EntityPlayerAddCollectible(lua_State* state);
// `EntityPlayer:AddCoins`（2026-09-18 新增，真实现）。同一族的第五条"直接调引擎方法"的接口，
// 接法与 `AddCollectible` 逐字相同（模块基址 + 偏移 + 4 字节入口指纹）。
// 为什么现在才做：**它是"给钱"的唯一通道** —— 写 `Coins` 字段那条路我们没开（字段写只认
// `ControlsCooldown`），也没有 `Isaac.Spawn`，而 `GetNumCoins` 此前是"恒返回 0"的桩。
// 批次 050（2026-09-19）：GoodTrip 真机上接着撞到的一批 `EntityPlayer` 引擎方法。
// `SetShootingCooldown` 缺了会让"打开地图后按方向键"那条路**在画图之前**报错
// （`scripts/control.lua:100` → 之后的 `draw_minimap_ui()` 不再执行）。
int EntityPlayerGetData(lua_State* state);
int EntityPlayerGetOtherTwin(lua_State* state);
int EntityPlayerGetEffectiveMaxHearts(lua_State* state);
// 批次 299（2026-10-03）：`EntityPlayer:HasFullHearts()`（语料 6 处）。
int EntityPlayerHasFullHearts(lua_State* state);
int EntityPlayerGetActiveItem(lua_State* state);
//: 批次 296（2026-10-03）：`EntityPlayer:GetActiveCharge(ActiveSlot = SLOT_PRIMARY)` —— 与
//: `GetActiveItem` **同一个槽位数组**（`kEntityPlayerActiveItemOffset` + `slot*0x1C`）的**下一个 4 字节**。
//: 引擎里没有同名访问器（`tools/mangled_impl_count.py GetActiveCharge` 得 0 个实现）⇒ 手写直读。
int EntityPlayerGetActiveCharge(lua_State* state);
// 批次 6（2026-09-12）：EID 在 update 回调里逐帧调用的一批 `EntityPlayer` 成员。缺任何一个，
// `player:X()` 就是 "attempt to call a nil value"，整条回调被派发器静默摘除（真机报告
// `01789210946` 的 `eid_api.lua:2606` 就是 `player:GetPill(0)`）。
// ★ 批次 177（2026-09-28）：`GetPill` / `GetCard` / `GetZodiacEffect` / `HasPlayerForm` /
//   `CanPickRedHearts` 已改成**引擎方法数据行**（`kEntityPlayerEngineRows`），不再有手写处理器
//   ⇒ 那五条在这里没有声明了。
int EntityPlayerGetMainTwin(lua_State* state);
int EntityPlayerGetCollectibleRNG(lua_State* state);
int EntityPlayerGetTrinketRNG(lua_State* state);
int EntityPlayerGetCardRNG(lua_State* state);
int EntityPlayerGetPillRNG(lua_State* state);
int EntityPlayerGetNumKeys(lua_State* state);
int EntityPlayerGetNumBombs(lua_State* state);
int EntityPlayerGetNumCoins(lua_State* state);
int EntityPlayerGetHearts(lua_State* state);
int EntityPlayerGetSoulCharge(lua_State* state);
int EntityPlayerGetBloodCharge(lua_State* state);
int EntityPlayerGetPoopMana(lua_State* state);
int EntityPlayerGetPoopSpell(lua_State* state);
int EntityPlayerGetModelingClayEffect(lua_State* state);
// `EntityPlayer:GetGlyphOfBalanceDrop` 的**声明已删**（批次 184）：它不再是手写处理器，
// 改走 `kEntityPlayerEngineRows` 里的数据行（形状 `Ref2U32Pair`）。
int EntityPlayerGetCollectibleNum(lua_State* state);
int EntityPlayerGetTrinketMultiplier(lua_State* state);
int EntityPlayerGetPlayerFormCounter(lua_State* state);
int EntityPlayerGetSmeltedTrinkets(lua_State* state);
int EntityPlayerGetEffects(lua_State* state);
int EntityPlayerGetName(lua_State* state);
int EntityPlayerHasTrinket(lua_State* state);
int EntityPlayerIsSubPlayer(lua_State* state);
int EntityPlayerGetTrinket(lua_State* state);

// `TemporaryEffects`（`EntityPlayer:GetEffects()` 的返回值）的手写方法（批次 388，2026-10-07）。
// 6 条 `Add*`/`Remove*` **手写**：PC 的缺省值是 `AddCostume = true` / `Count = 1`，
// 而数据行的 `optionalArgumentCount` 语义是"省略的寄存器保持 0"（只支持缺省就是 0/false 的参数）
// ⇒ 走数据行会把省略的参数变成 `false`/`0`（与 PC 相反）。其余 6 条无可选参数的走数据行。
// 5 条引擎侧形状还没齐的先做**不抛错占位**（逐条见实现处与 `api_deviation.cpp`）。
int TemporaryEffectsAddCollectibleEffect(lua_State* state);
int TemporaryEffectsAddTrinketEffect(lua_State* state);
int TemporaryEffectsAddNullEffect(lua_State* state);
int TemporaryEffectsRemoveCollectibleEffect(lua_State* state);
int TemporaryEffectsRemoveTrinketEffect(lua_State* state);
int TemporaryEffectsRemoveNullEffect(lua_State* state);
int TemporaryEffectsClearEffects(lua_State* state);
int TemporaryEffectsGetCollectibleEffect(lua_State* state);
int TemporaryEffectsGetNullEffect(lua_State* state);
int TemporaryEffectsGetTrinketEffect(lua_State* state);
int TemporaryEffectsGetEffectsList(lua_State* state);

// 全局函数（`GetPtrHash`）。
int GlobalGetPtrHash(lua_State* state);

// 会话级状态复位（`RegisterIsaacApi` 调用）。实体 ModData 表的存储在这里清空：
// 换 Lua 状态时那些 registry 引用随旧状态一起消失，所以**不能**在这里 `luaL_unref`。
void ResetEntityDataStore() noexcept;

// ItemConfig / ItemConfig_Item
int ItemConfigIndex(lua_State* state);
int ItemConfigItemIndex(lua_State* state);
int ItemConfigGetCollectible(lua_State* state);
int ItemConfigGetTrinket(lua_State* state);
// 批次 343（2026-10-04）：`ItemConfig:GetCollectibles()` / `GetTrinkets()`（各 1 处）——
// PC 侧分别返回 `userdata` 与 `ItemConfigList`（都是"列表对象"），我们返回一张
// `{Size, Get}` 表（语料只用到这两个面；`#` 不支持，已写进台账的边界栏）。
// 2026-10-09更正：现返回实时只读ItemConfigList userdata，支持Size/:Get/#。
int ItemConfigGetCollectibles(lua_State* state);
int ItemConfigGetTrinkets(lua_State* state);
int ItemConfigGetCard(lua_State* state);
int ItemConfigGetPillEffect(lua_State* state);
int ItemConfigIsCollectible(lua_State* state);
int ItemConfigHasTags(lua_State* state);
int ItemConfigItemHasTags(lua_State* state);
int ItemConfigItemIsCollectible(lua_State* state);
int ItemConfigItemIsAvailable(lua_State* state);
// 批次 241：`ItemConfig_Item:IsRune()`（PC 类名 `ItemConfig_Card`）—— 见实现处的注释。
int ItemConfigItemIsRune(lua_State* state);

// Catalog 的 id 与实现的对应关系。id 一旦分配不得复用（见 `api_descriptor.hpp`）。
int IsaacAddCallback(lua_State* state) {return CallCallbackTableApi(state,"AddCallback");}
int IsaacAddPriorityCallback(lua_State* state) {return CallCallbackTableApi(state,"AddPriorityCallback");}
int IsaacRemoveCallback(lua_State* state) {return CallCallbackTableApi(state,"RemoveCallback");}

constexpr LuaHandlerBinding kIsaacHandlers[] = {
    {0x0E011529, &isaac::runtime::IsaacGetRandomPosition},
    {0x0E01010E, &GetBuiltInCallbackState},
    {0x0E01010F, &SetBuiltInCallbackState},
    {0x0E010110, &IsaacAddCallback},
    {0x0E010111, &IsaacAddPriorityCallback},
    {0x0E010112, &IsaacRemoveCallback},
    {0x0E010001, &IsaacGetFrameCount},
    {0x0E010002, &IsaacGetTime},
    {0x0E010003, &IsaacDebugString},
    {0x0E010004, &IsaacIsInGame},
    {0x0E010005, &IsaacRunCallback},
    {0x0E010006, &IsaacGetPlayer},
    {0x0E010007, &IsaacGetItemConfig},
    {0x0E010008, &IsaacFindByType},
    {0x0E010009, &IsaacFindInRadius},
    {0x0E01000A, &IsaacCountEnemies},
    {0x0E01000B, &IsaacCountBosses},
    {0x0E01000C, &IsaacWorldToScreen},
    {0x0E01000D, &IsaacWorldToRenderPosition},
    // 批次 195：`Isaac.ScreenToWorld`（PC 有、我们此前没有；id 取域内 max+1，见前置声明处）。
    {0x0E01005F, &IsaacScreenToWorld},
    {0x0E01000E, &IsaacGetPersistentGameData},
    {0x0E01000F, &IsaacGetTrinketIdByName},
    {0x0E010010, &IsaacGetCallbacks},
    {0x0E010011, &IsaacLoadModData},
    {0x0E010012, &IsaacSaveModData},
    {0x0E010013, &IsaacRenderScaledText},
    // 批次 269（2026-10-02）：`blocked_decision` 桶的渲染两条（域内序号 0x0090/0x0091，
    // 取 Isaac 域 max+1）。两条都与 `RenderScaledText`（0x0013）**共用同一份运行时默认字体**。
    {0x0E010090, &IsaacRenderText},
    {0x0E010091, &IsaacGetTextWidth},
    // 批次 261（2026-10-01）：`glue_compose` 桶的三条（域内序号 0x0088/0x0089/0x008A，
    // 取 Isaac 域 max+1；域内序号到此为 0x0087）。
    {0x0E010088, &IsaacGetChallenge},
    {0x0E010089, &IsaacConsoleOutput},
    {0x0E01008A, &IsaacHasModData},
    // 批次 262（2026-10-01）：`glue_compose` 桶两条**由 Room 原语拼出来**的接口
    // （域内序号 0x008B/0x008C，取 Isaac 域 max+1；实现都在 `remaining_api.cpp`）。
    {0x0E01008B, &IsaacGetFreeNearPosition},
    {0x0E01008C, &IsaacGridSpawn},
    // 批次 265（2026-10-02）：`Isaac.GetSoundIdByName`（域内序号 0x008D，取 Isaac 域 max+1）。
    {0x0E01008D, &IsaacGetSoundIdByName},
    // 批次 268（2026-10-02）：`glue_compose` 桶剩下两条（域内序号 0x008E/0x008F，取 Isaac 域 max+1）。
    // `CountEntities` 直接转调引擎 `EntityList::CountSpawned`；`RunCallbackWithParam` 是本 Runtime
    // 自己那套命名回调的"带过滤值"变体（PC 侧那条函数不在基座 exe 里，判据与偏离见实现处注释）。
    {0x0E01008E, &IsaacCountEntities},
    {0x0E01008F, &IsaacRunCallbackWithParam},
    // 批次 041（GoodTrip）：`GetRoomEntities` 是真实现；`ExecuteCommand` 是**平台降级**
    //（Switch 没有控制台），两者的判据见各自实现处的注释。
    {0x0E01002C, &IsaacGetRoomEntities},
    {0x0E01002D, &IsaacExecuteCommand},
    // 批次 139（2026-09-26）：`Isaac.GetCostumeIdByPath(path)` —— The Specialist for Good Items
    // 在**文件作用域**就用它建 `danceCostumes`/`danceItems` 两张表（`main.lua:26/29`），
    // 缺它整个模组加载失败。实现见 `IsaacGetCostumeIdByPath`（遍历 null 道具向量比 `+0x88`）。
    {0x0E01005D, &IsaacGetCostumeIdByPath},
    // 批次 207（2026-09-29）：`Isaac.GetScreenWidth()` / `GetScreenHeight()` —— MCM 的
    // `scripts/screenhelper.lua:55/56` 用它们把界面按屏幕尺寸摆位（缺它那句在
    // `if REPENTANCE then` 支路里抛错，整个 `ScreenHelper` 初始化失败）。
    // 实现 = 读引擎 GOT 槽（与 `Isaac.WorldToScreen` 那份坐标算术**同一个**助手）。
    {0x0E010063, &IsaacGetScreenWidth},
    {0x0E010064, &IsaacGetScreenHeight},
    // 批次 207（2026-09-29）：`Isaac.GetEntityTypeByName(name)` / `GetEntityVariantByName(name)`
    // —— MCM 在 `PostGameStarted` 里查 `"Potato Dummy"`（`modconfig.lua:260/261`）。
    {0x0E010065, &IsaacGetEntityTypeByName},
    {0x0E010066, &IsaacGetEntityVariantByName},
    // 批次 240（2026-09-30）：名字表一族（语料模组适配第二波 C 批）。
    // 表源 `tools/isaac_name_source/*.txt` → `program/isaac_name_tables.*`；逐条契约见实现处。
    {0x0E010079, &IsaacGetItemIdByName},
    {0x0E01007A, &IsaacGetCardIdByName},
    {0x0E01007B, &IsaacGetPillEffectByName},
    {0x0E01007C, &IsaacGetPlayerTypeByName},
    {0x0E01007D, &IsaacGetChallengeIdByName},
    // 批次 148（2026-09-26）：`Isaac.GetMusicIdByName(name)` —— 同一个模组在
    // `main.lua:477/478/185/186` 用它把 `music.xml` 里的**曲目名**换成引擎的**曲目编号**，
    // 编号再喂给 `MusicManager():Play(id, 1)`。缺它就是那句
    // "attempt to call a nil value (field 'GetMusicIdByName')" ⇒ 整条 `MC_POST_UPDATE` 回调被摘掉。
    // id 取域内**下一个空号**（0x005D 已被 `GetCostumeIdByPath` 占用）——与 `AddCoins` 取 0x0056
    // 是同一条规则，见 `api_catalog.cpp` 里那一行的注释。
    {0x0E01005E, &IsaacGetMusicIdByName},
    // 批次 340（2026-10-04）：`Isaac.Spawn(...)`（**手写**：引擎 `Game::SpawnEx` 的第 8 个形参
    // **走栈**、通用跳板填不了；且 Lua 形参序与引擎不同 + 要现取非 0 随机种子）。
    {0x0E0100EC, &IsaacSpawn},
    // ---- 批次 345（2026-10-04）：`Isaac.Explode(pos, source, damage)`（**5 处** / 2 个模组）----
    // PC 契约 `tools/pc_contract_docs/Isaac.md:112`。真身 `Game::BombExplosionEffects @ 0x355C68`
    // （入口字 `0xD10443FF`）。★★ 9 个形参 ⇒ **第 9 格走栈**（`ldrb w21,[x29,#0x60]`）⇒ 手写；
    // 末尾 4 格是绑定常量 `f=1.0f / b=true / ul=4 / b2=false`，第 4 格是 16 字节按值的 `bitset128_t`
    // （传全 0，与 PC 绑定逐字节同）。逐格落位与证据见 `runtime_constants.hpp` 的批次 345 段。
    // 语料：`RepentancePlus/main.lua:2242`、`IsaacOnTwitchReloaded/scripts/passiveItems.lua:183/184/185/187`。
    {0x0E0100F8, &IsaacExplode},
};

// `EntityPlayer` 的成员（owner 独立）：`GetPlayerType`/`HasCollectible` 与 PC 的同名方法一一对应。
// 批次 3 补上 EID 渲染路径直接调用的四个：`GetOtherTwin`（单人恒 nil）、`GetEffectiveMaxHearts`、
// `GetSoulHearts`、`GetBrokenHearts`（三者读 `runtime_constants.hpp` 里定位到的字段，恒返回数字）。
constexpr LuaHandlerBinding kEntityPlayerHandlers[] = {
    {0x0E011010, &RPlusPlayerAddBlackHearts},
    {0x0E011011, &RPlusPlayerAddMaxHearts},
    {0x0E011012, &RPlusPlayerAddRottenHearts},
    {0x0E011013, &RPlusPlayerAddSoulHearts},
    {0x0E011014, &RPlusPlayerCanPickBlackHearts},
    {0x0E011015, &RPlusPlayerCanPickBoneHearts},
    {0x0E011016, &RPlusPlayerCanPickGoldenHearts},
    {0x0E011017, &RPlusPlayerCanPickRottenHearts},
    {0x0E011018, &RPlusPlayerGetGoldenHearts},
    {0x0E011019, &RPlusPlayerGetHeartLimit},
    {0x0E01101A, &RPlusPlayerGetRottenHearts},
    {0x0E01101B, &RPlusPlayerHasFullHeartsAndSoulHearts},
    {0x0E01101C, &RPlusPlayerIsBlackHeart},
    {0x0E01101D, &RPlusPlayerIsBoneHeart},
    {0x0E01101E, &RPlusPlayerRemoveBlackHeart},
    {0x0E01101F, &RPlusPlayerSetFullHearts},

    // CHAPI按PC真实玩家方法消费，原生效果/字段守卫见rplus_player_api。
    {0x0E011000, &RPlusPlayerGetSubPlayer},
    {0x0E011001, &RPlusPlayerGetDamageCooldown},
    {0x0E011002, &RPlusPlayerSetMinDamageCooldown},
    {0x0E011003, &RPlusPlayerResetDamageCooldown},
    {0x0E011004, &RPlusPlayerAddSoulCharge},
    {0x0E011005, &RPlusPlayerAddBloodCharge},
    {0x0E011006, &RPlusPlayerAddJarHearts},
    {0x0E011007, &RPlusPlayerGetJarHearts},

    {0x0E010015, &EntityPlayerHasCollectible},
    {0x0E01004E, &EntityPlayerAddCollectible},
    // 0x0056：`EntityPlayer:AddCoins`（2026-09-18）。id 取域内**下一个空号** ——
    // 与 `AddCollectible` 取 0x004E、`GetCollectibleCount` 取 0x004F 是同一条规则
    // （见 `api_catalog.cpp` 里那一行的注释；**别抄成 0x004F**，那个号已被占）。
    // 批次 050：id 取域内**下一个空号**（0x0056 之后连着的四个，见 `api_catalog.cpp` 的说明）。
    {0x0E010017, &EntityPlayerGetData},
    {0x0E01001F, &EntityPlayerGetOtherTwin},
    {0x0E010020, &EntityPlayerGetEffectiveMaxHearts},
    {0x0E010026, &EntityPlayerGetActiveItem},
    //: 批次 296（2026-10-03）：id 取域内**下一个空号**（`Isaac` 域当前 max = 0xCC，本批占 0xCD/0xCE/0xCF）。
    {0x0E0100CF, &EntityPlayerGetActiveCharge},
    // ---- 批次 299（2026-10-03）：`EntityPlayer:HasFullHearts()`（域内序号 0xD1）。
    // 手写：判据是「当前红心 ≥ 有效上限」，而有效上限要按玩家类型决定骨心算不算
    // （与既有的 `GetEffectiveMaxHearts()` **共用同一份实现**）。
    {0x0E0100D1, &EntityPlayerHasFullHearts},
    {0x0E010027, &EntityPlayerGetTrinket},
    // 批次 6：EID 逐帧调用的一批成员（安全默认值，语义与成熟度见各自的实现注释）。
    // ★ 批次 177（2026-09-28）：`GetPill`(0x0030) / `GetCard`(0x0031) 已从这里**移出** ——
    //   它们改走引擎方法数据行（`kEntityPlayerEngineRows`），不再是手写假桩。
    {0x0E010032, &EntityPlayerGetMainTwin},
    {0x0E010033, &EntityPlayerGetCollectibleRNG},
    {0x0E010034, &EntityPlayerGetTrinketRNG},
    {0x0E010035, &EntityPlayerGetCardRNG},
    {0x0E010036, &EntityPlayerGetPillRNG},
    {0x0E010037, &EntityPlayerGetNumKeys},
    {0x0E010038, &EntityPlayerGetNumBombs},
    {0x0E010039, &EntityPlayerGetNumCoins},
    {0x0E01003A, &EntityPlayerGetHearts},
    {0x0E01003C, &EntityPlayerGetSoulCharge},
    {0x0E01003D, &EntityPlayerGetBloodCharge},
    {0x0E01003E, &EntityPlayerGetPoopMana},
    {0x0E01003F, &EntityPlayerGetPoopSpell},
    {0x0E010041, &EntityPlayerGetModelingClayEffect},
    // 0x0E010042 不在这张表里：`GetGlyphOfBalanceDrop` 自批次 184 起走**数据行**
    // （`kEntityPlayerEngineRows` 里那一条，形状 `Ref2U32Pair`）。
    {0x0E010043, &EntityPlayerGetCollectibleNum},
    {0x0E010044, &EntityPlayerGetTrinketMultiplier},
    {0x0E010045, &EntityPlayerGetPlayerFormCounter},
    {0x0E010046, &EntityPlayerGetSmeltedTrinkets},
    {0x0E010047, &EntityPlayerGetEffects},
    {0x0E010048, &EntityPlayerGetName},
    {0x0E010049, &EntityPlayerHasTrinket},
    // 0x0E01004A（`EntityPlayer:HasGoldenBomb`）**不在这张表里** —— 批次 195（2026-09-29）起走
    // **字段数据行**（`kFieldApis` 里那一条，读 `Entity_Player + 0x16D9` 一个字节），
    // 旧的手写"恒 false"处理器已删除（它同时从 `tools/lua_api_stub_ledger.json` 销账）。
    {0x0E01004D, &EntityPlayerIsSubPlayer},
    // 批次 271（2026-10-02）：`EntityPlayer:UseActiveItem(Item, UseFlags=0, Slot=-1, CustomVarData=0)`
    // （域内序号 0x0094；引擎符号 `Entity_Player::UseActiveItem @ 0x30653C` 早就有常量，本批接上处理器）。
    // 契约页写清了三个缺省值（0 / -1 / 0）⇒ 照抄，不推断。
    {0x0E010094, &EntityPlayerUseActiveItem},
    // ---- 批次 273（2026-10-02）：EntityPlayer 族的六条（域内序号 0x97..0x9D）。
    // ★ 全部挂在**这张表**（owner `EntityPlayer`）—— 与批次 271 的教训一致：处理器表按目录行的
    //   owner 分发，挂在 `Entity` 表上就等于没挂（`__index` 的基类回落救不了）。
    {0x0E010097, &EntityPlayerAddBlueSpider},
    {0x0E010098, &EntityPlayerAddGoldenHearts},
    {0x0E010099, &EntityPlayerAddMinisaac},
    {0x0E01009A, &EntityPlayerAddPill},
    {0x0E01009B, &EntityPlayerAnimateAppear},
    {0x0E01009C, &EntityPlayerDropTrinket},
    // ---- 批次 274（2026-10-02）：EntityPlayer 族八条（域内序号 0xA1..0xA8）。
    {0x0E0100A1, &EntityPlayerAddBoneHearts},
    {0x0E0100A2, &EntityPlayerAddFriendlyDip},
    {0x0E0100A3, &EntityPlayerAddPrettyFly},
    {0x0E0100A4, &EntityPlayerAnimateTrapdoor},
    {0x0E0100A5, &EntityPlayerCanPickSoulHearts},
    {0x0E0100A6, &EntityPlayerDonateLuck},
    {0x0E0100A7, &EntityPlayerRemoveGoldenBomb},
    {0x0E0100A8, &EntityPlayerRemoveGoldenKey},
    // ---- 批次 278（2026-10-02）：EntityPlayer 族 5 条（域内序号 0xB4..0xB8）。
    // ★ 只收**引擎符号参数个数与契约页完全对齐**的那些（多一个尾参的没收，理由见常量段注释）。
    {0x0E0100B4, &EntityPlayerThrowHeldEntity},
    {0x0E0100B5, &EntityPlayerAddSwarmFlyOrbital},
    {0x0E0100B6, &EntityPlayerAddItemWisp},
    {0x0E0100B7, &EntityPlayerUsePill},
    {0x0E0100B8, &EntityPlayerAddBlueFlies},
    // ---- 批次 284（2026-10-02）：两条 0 参布尔查询（域内序号 0xBB、0xBC）。
    // ★ 选批口径与"更正批次 273 那句 Open/Close 有重写"的完整证据见 `runtime_constants.hpp` 批次 284 段。
    {0x0E0100BB, &EntityPlayerIsHoldingItem},
    {0x0E0100BC, &EntityPlayerIsExtraAnimationFinished},
    // ---- 批次 328（2026-10-03）：`EntityPlayer:GetShootingInput()` / `GetShootingJoystick()`
    //      （域内序号 0xE0 / 0xE1；语料合 **16 处** = 14 + 2，是清单里最大的一块）。
    // ★★ 两条在 **PC 上共用同一份实现**（名字表项指向同一个 VA `0x741B00`）⇒ 我们的两个处理器
    //   只是同一段代码的两张门面（错误消息里带各自的名字）。见 `runtime_constants.hpp` 批次 328 段。
    // ★ 引擎符号是 **snake_case** 的 `Entity_Player::get_shooting_input`（按 Lua 名查是 `no_symbol`）。
    {0x0E0100E0, &EntityPlayerGetShootingInput},
    {0x0E0100E1, &EntityPlayerGetShootingJoystick},
    // ---- 批次 332（2026-10-03）：`EntityPlayer:GetMovementJoystick()`（域内序号 0xE4；语料 4 处）----
    // ★ 与上面那两条**同型**（HFA 返回 ⇒ 手写）；★ 引擎里那个函数叫 `get_movement_input`
    //   —— **名字不一样**，靠逐条对照函数体定案（见 `runtime_constants.hpp` 批次 332 段）。
    {0x0E0100E4, &EntityPlayerGetMovementJoystick},
    {0x0E011008, &EntityPlayerGetMovementJoystick}, // PC GetMovementInput同原绑定741880。
    // ---- 批次 334（2026-10-03）：`EntityPlayer:CheckFamiliar(...)`（域内序号 0xE6；语料 **3 处**）----
    // ★ 引擎符号 `_ZN15IsaacRepentance13Entity_Player14check_familiarEjiRNS_3RNGEPKNS_10ItemConfig4ItemEi`
    //   @ `0x29AD94` ⇒ 五形参 `(u32, i32, RNG&, ItemConfig::Item const*, i32) → void`。
    // ★★ **后两个形参是"非 0 缺省值"**（`nil` / `-1`）⇒ 数据行那条路表达不了（见
    //   `runtime_constants.hpp` 批次 334 段的成本账）⇒ 手写处理器。
    // ★ 3 处语料调用全是 3 参写法 ⇒ 走这两个缺省值。
    {0x0E0100E6, &EntityPlayerCheckFamiliar},
    // ---- 批次 337（2026-10-04）：`EntityPlayer:FireTear(...)`（**4 处** / 3 个模组）----
    // PC 契约 `EntityPlayer.md:720`：`EntityTear FireTear(Vector Position, Vector Velocity,
    // boolean CanBeEye = true, boolean NoTractorBeam = false, boolean CanTriggerStreakEnd = true,
    // Entity Source = nil, float DamageMultiplier = 1)`。
    // ★★ **两个缺省值是 `true`** + 引擎把三个布尔**打包成一个 `u32`**、`Velocity` 还是**按值**的 HFA
    //   ⇒ 数据行那条路缺两种表达能力 ⇒ 手写（账目与逐条反汇编见 `runtime_constants.hpp` 批次 337 段）。
    {0x0E0100EA, &EntityPlayerFireTear},
    // ---- 批次 344（2026-10-04）：`EntityPlayer:AnimateCollectible(...)`（**2 处** / 2 个模组）----
    // PC 契约 `EntityPlayer.md:435`：`void AnimateCollectible(CollectibleType Collectible,
    // string AnimName = "Pickup", string SpriteAnimName = "PlayerPickupSparkle")`。
    // 引擎真身 = **改名**后的 `Entity_Player::AnimatePickup(eCollectibleType, char const*, char const*)
    // @ 0x2DD150`（入口字 `0xD10743FF`）⇒ 手写（字符串实参 + 非空字符串缺省；
    // ★ 缺省**必须传字面串**、不能传 null）。
    // 语料：`RepentancePlus/main.lua:1054`（1 参，走缺省）、
    //       `BOIStageAPI15/scripts/stageapi/core/callbacks.lua:144`（3 参）。
    {0x0E0100F6, &EntityPlayerAnimateCollectible},
};

// `Entity` 的成员（owner 独立）。批次 4 补上 `ToPickup`/`GetData`（id 0x0E010024/0x0E010025）；
// 批次 5 补上 `GetSprite`（id 0x0E01002A）；批次 065 补上 `TakeDamage`（id 0x0E01002F）。
constexpr LuaHandlerBinding kEntityHandlers[] = {
    // 批次 065：`Entity:TakeDamage`（GoodTrip 的诅咒房过路费要用；见实现处的口径说明）
    {0x0E01002F, &EntityTakeDamage},
    {0x0E010014, &EntityToPlayer},
    {0x0E010024, &EntityToPickup},
    {0x0E010051, &EntityToFamiliar},
    // 批次 242（2026-09-30）：**下转族** 5 条（判据与 `ToPlayer`/`ToPickup`/`ToFamiliar` 同形：
    // `vptr` 精确等于 `base + <类>VtableOffset`；对 `Entity_NPC` 为什么也成立见 `runtime_constants.hpp`）。
    {0x0E01007F, &EntityToNpc},
    {0x0E010080, &EntityToTear},
    {0x0E01011E, &EntitySetSpriteFrame},
    {0x0E01011F, &EntityToBomb},
    {0x0E010081, &EntityToLaser},
    {0x0E010082, &EntityToEffect},
    {0x0E010083, &EntityToKnife},
    // 批次 207（2026-09-29）：`Entity:ToProjectile()`。MCM 的 `RoomIsSafe()` 里
    // `entity:ToProjectile().ProjectileFlags` 那一句要用它（`modconfig.lua:220`）。
    {0x0E010062, &EntityToProjectile},
    {0x0E010025, &EntityGetData},
    {0x0E01002A, &EntityGetSprite},
    // ---- 批次 271（2026-10-02）：`needs_new_receiver` 桶头部三条（域内序号 0x92/0x93/0x94）。
    // 三条的引擎符号都逐字在 dynsym 里、且**都只有一份实现**（没有子类重写）⇒ 不需要"挑重载"。
    {0x0E010092, &EntitySetColor},
    {0x0E010093, &EntityAddCharmed},
    // ---- 批次 273（2026-10-02）：Entity 族的两个"状态施加"（域内序号 0x96、0x9E）。
    {0x0E010096, &EntityAddFreeze},
    {0x0E01009E, &EntityAddPoison},
    // ---- 批次 274（2026-10-02）：Entity 族三条（域内序号 0x9D、0x9F、0xA0）。
    {0x0E01009D, &EntityAddFear},
    {0x0E01009F, &EntityAddHealth},
    {0x0E0100A0, &EntityRemoveStatusEffects},
    // ---- 批次 275（2026-10-02）：实体标志位加/清（域内序号 0xA9、0xAA）。
    {0x0E0100A9, &EntityAddEntityFlags},
    {0x0E0100AA, &EntityClearEntityFlags},
    // ---- 批次 277（2026-10-02）：`GetEntityFlags`（域内序号 0xB3）—— 批次 275 两条的读侧兄弟。
    {0x0E0100B3, &EntityGetEntityFlags},
    // ---- 批次 346（2026-10-04）：`Entity:AddVelocity(Vector[, boolean])`（**20 处** / 1 个模组）----
    // PC 契约 `Entity.md:282`（ABP 一参）/ `:284`（Rep+ 两参，`IgnoreTimeScale` 缺省 `false`）。
    // PC 绑定 `0x422B60`：读 `+0x2c4` 摩擦（**精确 0 直接返回**）、按 bool 取 `1.0f` 或 `+0x2f4`、
    // 把 `(k*分量)/摩擦` 加到 `+0x2b8/+0x2bc`；**没有一个 `call`**（不调 `TimeScaledFriction`）。
    // ★★ Switch 侧**没有可调真身**（符号 0 命中 / 原始字节 0 命中）⇒ **手写纯算法**，
    //    直接读写 `+0x334/+0x338`（速度）、`+0x340`（摩擦）、`+0x370`（时间缩放，本批新增常量）。
    // ★ 语料 20 处**全是 1 参**写法 ⇒ 第 3 格可省。
    {0x0E0100F9, &EntityAddVelocity},
    // ★ `UseActiveItem` 挂在**玩家**表里（见 `kEntityPlayerHandlers`）—— 它的契约 owner 就是
    //   `EntityPlayer`。★ 这一格是**真机/宿主一起教会的**：一开始挂在这张 `Entity` 表上，
    //   宿主用例当场报 `attempt to call a nil value (method 'UseActiveItem')`
    //   ⇒ **处理器表按目录行的 owner 分发**，owner 对不上就等于没挂（而 `SetColor`/`AddCharmed`
    //   的 owner 是 `Entity`，所以它们挂在这张表上是对的、并且玩家能通过继承取到）。
};

// `ItemConfig` 的成员（owner 独立，与 `Entity`/`EntityPlayer` 同一形态：挂在元表的
// `__methods` 上）。`ItemConfig_Item` 的字段（`ID`/`Type`/`Name`/`Description`）走 `__index`，
// 不占 catalog 行也不占绑定行（与 `EntityPlayer` 的 `Position`/`Type` 同例）。
// `EntityPickup` 的成员（owner 独立）。批次 4 只有一条：`IsShopItem`。
constexpr LuaHandlerBinding kEntityPickupHandlers[] = {
    {0x0E010029, &EntityPickupIsShopItem},
    // 批次 028：`EntityPickup:CanReroll()`（域内取号：0x2B 是扫描出来的**第一个空号**，
    // 0x2A 之后到 0x30 之间是空洞 —— 别按"上一个 +1"猜）。
    // ⚠️ **必须登记在"这个 owner 自己的表"里**：实体方法按 owner 分表挂到各自的元表上
    // （`AttachEntityPickupMethods` 只读这张表）。2026-09-18 实测教训：我第一版把它放进
    // `EntityPlayer` 那张表 ⇒ 方法挂到了 `EntityPlayer` 元表上 ⇒ `pickup:CanReroll()` 是 nil
    // （探针的 `R=` 打印 `ERR`），而"处理器存在、目录行存在、门禁也过"——**三样都绿还是调不到**。
    {0x0E01002B, &EntityPickupCanReroll},
};

constexpr LuaHandlerBinding kPersistentGameDataHandlers[] = {
    {0x0E01010B, &PersistentGameDataUnlocked},
    {0x0E010113, &PersistentGameDataGetBestiaryKillCount},
    {0x0E010114, &PersistentGameDataGetBestiaryDeathCount},
    {0x0E010115, &PersistentGameDataGetBestiaryEncounterCount},
    {0x0E010116, &PersistentGameDataAddBestiaryKill},
    {0x0E010117, &PersistentGameDataAddBossKilled},
    {0x0E010118, &PersistentGameDataIsBossKilled},
};

constexpr LuaHandlerBinding kItemConfigHandlers[] = {
    {0x0E010018, &ItemConfigGetCollectible},
    {0x0E010019, &ItemConfigGetTrinket},
    {0x0E01001A, &ItemConfigGetCard},
    {0x0E01001B, &ItemConfigGetPillEffect},
    {0x0E01001C, &ItemConfigIsCollectible},
    {0x0E01001D, &ItemConfigHasTags},
    // ---- 批次 343（2026-10-04）：两张列表（各 1 处）----
    {0x0E0100F4, &ItemConfigGetCollectibles},
    {0x0E0100F5, &ItemConfigGetTrinkets},
};

constexpr LuaHandlerBinding kItemConfigItemHandlers[] = {
    {0x0E01001E, &ItemConfigItemHasTags},
    {0x0E010023, &ItemConfigItemIsCollectible},
    {0x0E010055, &ItemConfigItemIsAvailable},
    // 批次 242（2026-09-30）：`ItemConfig_Item:IsRune()`（id 取 Isaac 域 max+1 = 0x007E）。
    {0x0E01007E, &ItemConfigItemIsRune},
};

constexpr char kIsaacOwner[] = "Isaac";
constexpr char kEntityOwner[] = "Entity";
constexpr char kEntityPlayerOwner[] = "EntityPlayer";
constexpr char kEntityPickupOwner[] = "EntityPickup";
constexpr char kItemConfigOwner[] = "ItemConfig";
constexpr char kItemConfigItemOwner[] = "ItemConfig_Item";

template <typename Table>
constexpr std::size_t RowCount(const Table& table) noexcept {
    return sizeof(table) / sizeof(table[0]);
}

// `Isaac.RunCallback` 的递归上限。PC 版没有这个限制，但我们的派发是同步 Lua 调用，
// 一个回调再 `RunCallback` 它自己就会一直套下去；给一个小上限，越界直接报 Lua 错误。


// 安全 stub 的成员名单。数组下标即成员身份，告警文本单独传，所以新加一个 stub 只需加一行枚举，
// 不需要再写一遍"是否已经告警过"的判断。
//
// 注意：`GetPlayer` **已经不在这里**——批次 2 起它是真实现（读引擎内存），失败时返回 nil
// 而不是"安全默认值"，所以它既不属于 stub 告警名单，也不该有告警。`GetItemConfig` 同理
// （批次 2b 起是真实现：内嵌 `ItemConfig` 的只读视图），也从这份名单里移除了。
// `GetCallbacks` 批次 3 起同样是真实现（命名回调表 + `CallbackRegistry`），一并移除。
// 批次 4 再把 `FindByType`/`FindInRadius`/`CountEnemies` 移出名单：它们已经是真实现
// （房间实体容器遍历），拿不到容器时返回**空表/0**，那是"引擎数据读不到"而不是"未实现"，
// 留一行"未实现"告警会把前者误导成后者。
// `CountBosses` **留在名单里**：boss 判据（vtable 槽或实体字段）本轮没有任何证据，
// 见 `IsaacCountBosses` 的注释——它照旧返回 0 并告警一次。
    // 2026-09-18 批次 026：`CountBosses` / `LoadModData` / `SaveModData` / `RenderScaledText`
    // 四条**已改成真实现**（判据见各自实现处与 `runtime_constants.hpp`），
    // 因此从这份名单里删掉。
    //
    // ★ 2026-09-25 更正（批次 127）：这里原来是"**这里的枚举就是'还在桩里的那些'，与
    // `tools/lua_api_stub_ledger.json` 双向一致（门禁 `test_lua_api_stub_ledger` 盯着）**"——
    // **那句话当时是错的**：门禁核对的是"**源码里被检测器认出来的桩** ↔ 台账"，它从来没有读这个
    // 枚举。而这个枚举少了两条（`WorldToScreen` / `WorldToRenderPosition` 当时被判成真实现），
    // 台账也少了两条 —— 两边都没错，只是**都在漏**。现在判据补了"一层委托"之后三方对上了：
    // 这个枚举 = 台账里由 `IsaacWarnStubOnce`/`WarnStubOnce` 告警的那一组。
    // ⇒ **权威台账是 `tools/lua_api_stub_ledger.json`**（它从源码派生、由门禁双向钉住）；
    // 这个枚举只是"运行时要发一次告警"的那一份名单，不要把它当台账用。
    //
    // ★ 批次 195（2026-09-29）：`WorldToScreen` / `WorldToRenderPosition` 两条**从这份名单里删掉**
    //   —— 它们不再是恒等桩，而是真调引擎 `GetRenderPosition(pos, true)`（证据见
    //   `analysis/api-restore-transforms/spec.json`）。两条恒等实现与它们的告警一起删除，
    //   台账 `tools/lua_api_stub_ledger.json` 同步销账（门禁双向钉住）。
    // ★ 批次 404（2026-10-07）：`GetTrinketIdByName` 从这份名单里**删掉** —— 它不再是恒 0 桩，
    //   已是"本体饰品静态表 + 模组追加层"的真实现（见实现处的长注释与
    //   `tools/lua_api_stub_ledger.json` 的同步销账）。
// 单线程路径（Lua 只在托管回调里跑）上的普通全局：故意不用锁也不用原子——没有第二个线程
// 访问它，而本项目在真机上已经被 `thread_local` 坑过一次（见 `lua_runtime.cpp`）。
// 2026-10-09：最后一条恒值桩已恢复，退役的Stub枚举与告警状态全文另存PGD存档.before。


// 与 Lua `print` **同一个输出通道**的一行文本。
//
// `print` 是标准库函数（`lua_runtime.cpp` 用 `luaopen_base` 打开它），所以"复用同一个通道"
// 的唯一正确做法就是调用它本身：将来 Runtime 把 `print` 换成 SaltySD 日志时，
// `Isaac.DebugString` 与 stub 告警会一起跟着走，不需要在这里再维护第二条日志路径。
//
// 失败必须吞掉：脚本可能把 `print` 覆盖成别的东西，而 `DebugString`/stub 告警都不允许
// 把错误抛回 Mod（本轮的目标正是"被调用时不报 Lua 错误"）。
void EmitLine(lua_State* state, const char* text, std::size_t length) {
    if (state == nullptr || text == nullptr) {
        return;
    }
    lua_getglobal(state, "print");
    if (lua_type(state, -1) != LUA_TFUNCTION) {
        lua_pop(state, 1);
        return;
    }
    lua_pushlstring(state, text, length);
    if (lua_pcallk(state, 1, 0, 0, 0, nullptr) != LUA_OK) {
        lua_pop(state, 1);
    }
}

// 安全 stub 的告警：每个成员每会话只写一行。

void ResetSessionState() {

    ManagedFrameClock::Reset();
    // 回调派发计数也是"每会话"口径：不清的话新一次加载会读到上一次的累加值，
    // 而"有没有被派发过"这个判断就永远为真了（见 `callback_dispatcher.hpp` 的说明）。
    ResetCallbackDispatchCounters();
    ResetEntityDataStore();
    // 批次 107：`IsActionTriggered` 的上升沿表也是"每会话"口径。
    ResetInputEdgeState();
}

std::int64_t FrameCount() {
    // PC counts whole-game cycles, including paused and menu frames (~60 Hz).
    return static_cast<std::int64_t>(NativeFrameClock::Count());
}

void PushNil(lua_State* state) {
    lua_pushnil(state);
}

void PushZero(lua_State* state) {
    lua_pushinteger(state, 0);
}

// ★ 批次 195（2026-09-29）：`WorldToIdentity` 已删除 —— 它是 `Isaac.WorldToScreen` /
// `Isaac.WorldToRenderPosition` 两条恒等桩的实现，而两条现在都真调引擎
// （`TransformWorldPosition`，`remaining_api.cpp`）。留着它就是"没有调用者的函数"
// （`-Werror` 会拦），也会给下一个人一个"坐标变换可以恒等"的错样板。
// 它原来那句"返回一个同值的新 Vector（不复用调用方的 userdata）"仍然是对的口径，
// 现在的两条实现同样各自 `lua_newuserdata` 压一个新对象。

// --- 近似实现（有真实行为）-------------------------------------------------

int IsaacGetFrameCount(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Isaac.GetFrameCount accepts no arguments");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(FrameCount()));
    return 1;
}

// `Isaac.GetScreenWidth()` / `Isaac.GetScreenHeight()`（批次 207，2026-09-29）——
// MCM 的 `scripts/screenhelper.lua:55/56` 在 `if REPENTANCE then` 支路里用它拼界面尺寸
// （`ScreenHelper.GetScreenSize()` 是所有角落/居中摆位的地基）。
//
// PC 契约 `tools/pc_contract_docs/Isaac.md:419`（`#### float GetScreenWidth ( )`）与
// `:399`（`GetScreenHeight`）—— 返回 **float**（不是整数）。
//
// 底座就是引擎自己的 `IsaacRepentance::WIDTH` / `HEIGHT` 全局：GOT 槽 `0xAAC650` / `0xAAC658`，
// 读法是"槽 → 指针 → 那个 float"（**既有消费者**：`Isaac.WorldToScreen` 那一族的坐标算术读的
// 就是这两个槽，见 `remaining_api.hpp` 的 `ReadFloatGlobalSlot`）⇒ 本批不新增任何引擎偏移，
// 只是把已有的读取助手包成两个 Lua 方法。
//
// 退化：读不到（引擎还没起来 / `ResizeWindow` 还没跑）⇒ **返回 0.0，不报错**。
// 口径理由与同族一致：报错会把整条模组回调摘掉（比"值不对"严重得多）；而 0 在 MCM 那里
// 只表现为"界面贴在左上角"，不会崩。
int IsaacGetScreenWidth(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Isaac.GetScreenWidth accepts no arguments");
    }
    float width = 0.0F;
    if (!ReadFloatGlobalSlot(kIsaacScreenWidthSlotOffset, &width)) {
        width = 0.0F;
    }
    lua_pushnumber(state, static_cast<lua_Number>(width));
    return 1;
}

int IsaacGetScreenHeight(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Isaac.GetScreenHeight accepts no arguments");
    }
    float height = 0.0F;
    if (!ReadFloatGlobalSlot(kIsaacScreenHeightSlotOffset, &height)) {
        height = 0.0F;
    }
    lua_pushnumber(state, static_cast<lua_Number>(height));
    return 1;
}

// `Isaac.GetEntityTypeByName(name)` / `GetEntityVariantByName(name)`（批次 207，2026-09-29）——
// MCM 在 `PostGameStarted` 里查 `"Potato Dummy"`（`scripts/modconfig.lua:260/261`），
// 缺任意一条就是 "attempt to call a nil value"。
//
// PC 契约：`tools/pc_contract_docs/Isaac.md:218`（`#### int GetEntityTypeByName ( string Name )`，
// 找不到返回 **0**）、`:235`（`#### int GetEntityVariantByName ( string Name )`，找不到返回 **-1**）。
//
// 数据来自 `program/entity_name_table.hpp`（由 `tools/generate_entity_name_table.py` 从
// `tools/entity_name_source.txt` 生成；那份源文件是本体的 `entities2.xml` +
// `rp_patch/resources/entities2.xml` 的名字快照，来龙去脉见生成器的文档头）。
// 表按名字升序 ⇒ 这里二分。
//
// ★ 已知偏离（写在这里也写进 `api_deviation.cpp`）：模组在 `content/entities2.xml` 里新加的
//   实体名**看不见**（PC 看得到）。所以 `"Potato Dummy"` 在本体与我们都查不到（返回 0/-1），
//   与"没装那个模组时的 PC"一致 —— 这正是 MCM 那个 `if potatoType and potatoVariant > 0`
//   要防的情况。
//
// 参数不是字符串（含缺参）⇒ 按"查不到"处理（0 / -1），**不报错**：与同族"静默降级"一致。
//
//: 在生成的名字表里二分查找（表已按名字升序）。找不到返回 `nullptr`。
[[maybe_unused]] const EntityNameEntry* FindEntityNameEntry(const char* name) noexcept {
    std::size_t count = 0;
    const EntityNameEntry* entries = EntityNameEntries(&count);
    const char* blob = EntityNameBlob();
    if (name == nullptr || entries == nullptr || blob == nullptr || count == 0) {
        return nullptr;
    }
    std::size_t low = 0;
    std::size_t high = count;
    while (low < high) {
        const std::size_t middle = low + (high - low) / 2;
        const int order = std::strcmp(name, blob + entries[middle].nameOffset);
        if (order == 0) {
            return &entries[middle];
        }
        if (order < 0) {
            high = middle;
        } else {
            low = middle + 1;
        }
    }
    return nullptr;
}

int IsaacGetEntityTypeByName(lua_State* state) {
    return RuntimeGetEntityTypeByName(state);
}

int IsaacGetEntityVariantByName(lua_State* state) {
    return RuntimeGetEntityVariantByName(state);
}

// --- 批次 240（2026-09-30）：`Isaac.Get*ByName` 名字表一族 ---------------------------------
//
// 这 5 条在 PC 上都是"查本体 XML 建的内建表"（契约逐条见 `tools/pc_contract_docs/Isaac.md`），
// Switch 二进制里**没有对应函数**（库存工具把它们判成 `lua_glue_type`）⇒ 表由本仓库生成：
// `tools/isaac_name_source/*.txt`（**追踪在仓库里**）→ `program/isaac_name_tables.*`。
//
// ★ 为什么不能"遍历引擎的 `ItemConfig` 比名字"（看着更省事的那条路）：Switch 的 romfs 叠加层里
//   `rp_patch/resources/items.xml` 覆盖了 base 那份，而前者 **960 条名字里 911 条是本地化键**
//   （`#THE_SAD_ONION_NAME`）⇒ 运行时 `ItemConfig_Item.Name` 读到的是**键**，
//   拿 `"Brimstone"` 这种原文去比永远不中。所以只能自己建表、并把名字解析成本地化文本。
//
// 参数口径照抄同族的 `IsaacGetMusicIdByName` / `IsaacGetCostumeIdByPath`：PC 的绑定层用
// `luaL_checklstring`（数字会被 Lua 自动转成串）⇒ 我们**照抄**，不自己收紧成"必须是字符串"
// （比 PC 严会把本该发生的调用变成 Lua 报错、进而摘掉整条回调）。
//
// ★ 查不到一律返回 **`-1`**（这 5 条契约都这么写：`Isaac.md:150/178/282/308/354`）。
//   注意与**同族**的 `GetEntityTypeByName` 不同 —— 那一条查不到是 `0`、`GetEntityVariantByName`
//   才是 `-1`，别把口径串了。
//
// ★ 已知偏离（写在明处）：**只看得到本体 XML 里的名字**。模组在自己 `content/*.xml` 里加的东西
//   查不到（PC 查得到）—— 语料里 `IsaacOnTwitchReloaded` 传的 `"Kappa"`/`"Nightbot"` 就是它自己
//   加的道具 ⇒ 我们返回 `-1`，与"没装那个模组的 PC"一致。与 `GetEntityTypeByName` 的同名偏离同源。
//   ★ 更正（批次 401）：**`GetPlayerTypeByName` 已不再受这条限制** —— 模组 `content/players.xml`
//     声明的角色名由运行时追加层（`program/mod_player_names.*`）按引擎喂入顺序补上；
//     其余四条（道具 / 卡 / 药丸 / 挑战）仍只看本体快照。
int IsaacGetItemIdByName(lua_State* state) {
    // 契约 `tools/pc_contract_docs/Isaac.md:282`：
    // `CollectibleType GetItemIdByName ( string itemName )`，「Returns `-1` if no item with that name
    // could be found」（同页例子 `GetItemIdByName("Brimstone")` → 118）。
    // 消费方：`TBOI_Better-Voiding/bettervoiding_4444444444/main.lua`（`"Void"`/`"Abyss"`/
    // `"Genesis"`/`"Flip"`，全落在 `MC_PRE_USE_ITEM` 的回调登记参数上 ⇒ 缺它整条回调登记不上）。
    // ★ 批次 404：**先查静态表（本体优先）**，只有静态表未命中时才落到"模组道具追加层"。
    //   这样本体 717 条 id 逐值不变，追加的道具只可能出现在 733 之后（`kModContentNameIdBase`）。
    //   追加层由装载期 `IngestModContentXml` 按引擎喂入顺序填（见 `mod_content_names.hpp`）。
    std::size_t length = 0;
    const char* name = luaL_checklstring(state, 1, &length);
    std::int32_t id = LookupIsaacName(IsaacNameKind::Collectible, name, length);
    if (id < 0) {
        id = LookupModContentName(ModContentNameFamily::Collectible, name, length);  // 未命中仍是 -1
    }
    lua_pushinteger(state, id);
    return 1;
}

int IsaacGetCardIdByName(lua_State* state) {
    // 契约 `Isaac.md:148`：`Card GetCardIdByName ( string cardHudName )`，找不到 `-1`。
    // ★ 契约明写它匹配的是 `pocketitems.xml` 的 **`hud` 属性**（不是卡名），并自带一条
    //   "函数名有误导性 / 对本体卡牌不工作"的警告。实测本体 `pocketitems.xml` **一条 `hud=` 都没有**
    //   （0 处）⇒ 本表改用 `name` 属性，**这是一条有意偏离**，登记在 `api_deviation.cpp`。
    std::size_t length = 0;
    const char* name = luaL_checklstring(state, 1, &length);
    // ★ 批次 404：静态表（本体）未命中再落到"模组卡牌追加层"（本体优先，id 逐值不变）。
    std::int32_t id = LookupIsaacName(IsaacNameKind::Card, name, length);
    if (id < 0) {
        id = LookupModContentName(ModContentNameFamily::Card, name, length);
    }
    lua_pushinteger(state, id);
    return 1;
}

int IsaacGetPillEffectByName(lua_State* state) {
    return RuntimeGetPillEffectByName(state);
}

int IsaacGetPlayerTypeByName(lua_State* state) {
    // 契约 `Isaac.md:352/354`：
    // `PlayerType GetPlayerTypeByName ( string playerName , boolean Tainted = false )`，找不到 `-1`。
    // ★ 第二个参数取**堕落角色**：`players.xml` 里 id 21..40 与本体（0..20）**名字逐字重复**
    //   ⇒ 名字表那两格（`IsaacNameEntry::id` / `alternateId`）就是为它留的。
    //   `lua_toboolean` 对缺参返回 false ⇒ 正好等于契约的缺省 `false`。
    std::size_t length = 0;
    const char* name = luaL_checklstring(state, 1, &length);
    const bool tainted = lua_toboolean(state, 2) != 0;
    // ★ 批次 401 / 2026-10-29：**先查静态表（本体优先）**，静态表未命中才落到
    //   "模组角色追加层"。这样本体 41 个 id（0..40）逐值不变（要求②），
    //   追加的名字只可能出现在 41 之后（`kModPlayerTypeIdBase`）。
    //   追加层由装载期 `IngestModPlayersXml` 按**引擎喂入顺序**填（见 `mod_player_names.hpp`）。
    std::int32_t id = LookupIsaacName(IsaacNameKind::PlayerType, name, length, tainted);
    if (id < 0) {
        id = LookupModPlayerTypeName(name, length, tainted);  // 未命中仍是 -1（与契约同口径）
    }
    lua_pushinteger(state, id);
    return 1;
}

int IsaacGetChallengeIdByName(lua_State* state) {
    // 契约 `Isaac.md:176/178`：`Challenge GetChallengeIdByName ( string challengeName )`，
    // 找不到 `-1`，**大小写敏感**（同页例子 `"Aprils fool"` → 32 —— 注意就是小写 f）。
    std::size_t length = 0;
    const char* name = luaL_checklstring(state, 1, &length);
    lua_pushinteger(state, LookupIsaacName(IsaacNameKind::Challenge, name, length));
    return 1;
}

int IsaacGetTime(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Isaac.GetTime accepts no arguments");
    }
    // ★ 2026-09-20（批次 108）：**单位必须是毫秒**。PC 文档（`Isaac.md:448`）写明
    // `int GetTime()` = "milliseconds since the computer's operating system was started"。
    //
    // 以前这里是 `GetFrameCount() / 30` 的**整数秒** —— 单位差 1000 倍，而后果不是"显示差一点"：
    // EID 的库存概况翻页判据是 `Isaac.GetTime() - lastInputTime > 50`（**50 毫秒**防抖），
    // 秒口径下这条几乎永远不成立 ⇒ **整段翻页逻辑被闸住**（模组侧明明已经收到
    // `IsActionTriggered` 的 true）。真机读数 + 用户实测一起指到这里的（见 107/108 的存档）。
    //
    // 实现见 `engine_memory_guard.hpp` 的 `EngineMillisecondsNow()`（`cntpct_el0` / 19.2 MHz；
    // 宿主构建走 `steady_clock`）。与 PC 的剩余差别只有 **epoch**（PC 是"OS 启动起"，我们是
    // Switch 的 tick 起点）—— 模组都算差值，所以语义一致。
    lua_pushinteger(state, static_cast<lua_Integer>(isaac::runtime::EngineMillisecondsNow()));
    return 1;
}

int IsaacDebugString(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Isaac.DebugString accepts one string");
    }
    std::size_t length = 0;
    const char* text = luaL_checklstring(state, 1, &length);
    EmitLine(state, text, length);
    return 0;
}

int IsaacIsInGame(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Isaac.IsInGame accepts no arguments");
    }
    // 与各家族同一个判断：只有处在 Runtime 的托管回调作用域里，Lua 才"在游戏里"——
    // 那里的游戏对象才是可读的。
    lua_pushboolean(state, InManagedCallbackScope() ? 1 : 0);
    return 1;
}

// --- 批次 261（2026-10-01）：`glue_compose` 桶的三条 ---------------------------------------------
//
// 这一桶的判据（清单生成器给的）：PC 上这几条是**在 exe 的 Lua 绑定层里用现成原语拼出来**的
// （Switch 二进制的符号表里既没有同名自由函数、`Game`/`Manager` 里也没有同名成员）
// ⇒ 正确做法是**照 PC 文档的语义**用我们已有的原语拼，而不是去接一个不存在的引擎符号。

// `Isaac.ConsoleOutput(string text)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:42`
// `#### void ConsoleOutput ( string text )`，正文逐字「Prints a string into the Debug Console.」
//
// 我们这边的"Debug Console"就是**运行时自己的输出通道**（与 `Isaac.DebugString`
// （`Isaac.md:83`，同一件事的另一个名字）走的是同一条：`EmitLine` → Lua 的 `print`）。
// 为什么不另开一条：`print` 在我们的运行时里已经被接到控制台覆盖层（长按 A+B 那套），
// 模组的日志因此能真的**看得见**；再写一份"只进日志文件"的实现会让同一个 `Isaac` 表里
// 两个几乎同义的接口行为不一致。
//
// ★ 语义差异（记在这里，别丢）：PC 的输出会进游戏控制台的历史缓冲（打开控制台能翻到），
//   我们进的是**覆盖层**（约 3 秒后消失，见 `console_session.hpp` 的 `kOverlayHoldFrames`）。
//   两者的"看得见"这一点一致，**可回溯性**我们差一档 —— 这是平台侧的性质，不是这条 API 的语义。
int IsaacConsoleOutput(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Isaac.ConsoleOutput expects a string");
    }
    std::size_t length = 0;
    const char* text = luaL_checklstring(state, 1, &length);
    if (LuaRuntime::WriteActiveConsoleOutput(text,length)) return 0;
    static_cast<void>(console::AppendConsoleHistory(EngineModuleBase(),text,length));
    EmitLine(state, text, length);
    return 0;
}

// 用我们自己的回调注册表派发 `callbackId`，后续参数原样交给已注册的 Lua 函数。
//
// 没有注册者时安静返回（PC 版同样如此）；返回值一律丢弃——PC 的返回值语义依赖具体回调
// 种类，那些种类我们还没有派发点，装作实现反而是错的。
//
// **数字 id 的语义保持不变**（既有行为与测试依赖它）。**字符串名**（PC 的自定义回调名）
// 走另一条路：`RunNamedCallbacks` 按名字派发，并在第一个非 nil 返回值处停下、返回那个值
// —— 与 PC 文档一致（`analysis/isaacdocs-snapshot/docs/Isaac.md:579`：
// "Runs all callbacks added under callbackId, breaking on the first return and returning that
// value"）。EID 在**加载期的最后一行**就调用 `Isaac.RunCallback("EID_POST_LOAD")`
// （`main.lua:2030`），所以字符串形式必须是"能派发"而不是报错。
int IsaacRunCallback(lua_State* state) {
    return CallCallbackTableApi(state, "RunCallback");
}

// `Isaac.RunCallbackWithParam(callbackId, param, ...)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:584`
// （签名那一行只写了 `ModCallback|string callbackId`，**不完整**）。
//
// ★★ 完整的签名与语义取自**同源文档的另一次抓取**（`https://cuerzor.github.io/IsaacDocs/rep/Isaac.html`
//    的 `isaacguru` 中译，与我们快照同源、逐字对应）：
//      `void RunCallbackWithParam ( ModCallback|string callbackId, object param, ...)`
//      「执行所有**可选参数为 `param`** 的 `callbackId` 的 MOD 回调，会在第一个返回值出现时中断，
//        并使该函数返回该值。」
//    ⇒ `param` 是**注册时那个过滤值**（`Mod:AddCallback(id, fn, entityId)` 的第三个实参），
//    **不是**回调实参；它**不进**回调的参数表。判据链：
//      * 过滤匹配规则逐字来自 PC 的 Lua 胶水（REPENTOGON issue #336 引用了那一段）：
//        `__matchParams = function(a,b) return not a or not b or a == -1 or b == -1 or a == b end`；
//      * 语料里的调用形状印证它：`ChallengeAPI` 的订阅方是
//        `local function onChallengeStart(_mod, challenge, isContinue)`
//        （`goals/hooks/startingpills.lua:3`），而派发是
//        `Isaac.RunCallbackWithParam(名字, challenge.id, challenge, isContinue)`
//        （`scripts/challengeapi/callbacks.lua:24`）—— 若 `challenge.id` 被当实参传下去，
//        第二个形参收到的会是数字、`isContinue` 收到 `challenge` 表（恒真）⇒ 行为错。
//
// ★ 归属判定（这一条**不在基座 PC 的 exe 里**，与 `Isaac.CountEntities` 不同）：
//   `python3 tools/pc_exe_binding.py RunCallbackWithParam` ⇒ 名字表里没有这个名字；
//   `--list RunCallback` 只给 `_RunCallback`（那是引擎内部的另一个东西）；
//   整个 exe 里连 `RunCallbackWithParam` 这串字节都搜不到（0 处）。
//   同一族里 `Mod:AddCallback` / `RunCallback` 也不在 exe 里 —— 它们属于"字符串回调名"那套
//   由扩展层提供的能力。**但我们早就实现了 `Isaac.RunCallback`**（`0x0E010005`，批次 3 起）：
//   起因是 EID 在**加载期最后一行**就调 `Isaac.RunCallback("EID_POST_LOAD")`，缺它整个模组加载失败。
//   ⇒ 本 Runtime 早就有一份自己的命名回调注册表（`mod_api.cpp` 的 `RegisterNamedCallback`），
//   本条只是它的"带过滤值"变体，**没有新增机制、也没有假装引擎里有**。
//   ★ 与 `Isaac.RunCallback` 的**数字路径**有一处刻意不同：那条"调完所有登记、丢弃返回值"
//     （理由写在它的注释里：返回值语义依赖具体回调种类），而本条按契约在**第一个非 nil 返回值**
//     处停下并把它返回 —— 这正是本条的契约原文。数字 id 的调用语料里没有，行为归属清楚即可。
//
// ★ 已知未做（记在这里，不悄悄销账）：`Mod:AddPriorityCallback(字符串名, 优先级, fn)` 的
//   **优先级排序**对命名回调仍未生效（登记顺序 = 派发顺序）。影响面仅限"同一个字符串名下
//   混用默认优先级与 `LATE`/`EARLY`"的模组（语料里只有 `ChallengeAPI` 一家，
//   而它的两条处理函数都在同一个挑战开始钩子上、先后无所谓）。要做它得让命名回调表
//   在插入时按优先级定位，是独立的一批。
int IsaacRunCallbackWithParam(lua_State* state) {
    return CallCallbackTableApi(state, "RunCallbackWithParam");
}

// --- 引擎实体只读视图（批次 2）------------------------------------------------
//
// 偏移来源 = **反汇编定位 + 真机 verified**：常量表在 `runtime_constants.hpp`
// （全局槽 `0xAAC698`、玩家向量 `+0x25C50/+0x25C58`、字段偏移与 `Entity_Player` 的
// vptr `0xA37110`/尺寸 `0x2FA0`/`HasCollectible` `0x27D3F4`），并已由真机探针
// `IsaacModRuntime_ProbeEnginePlayers` 的崩溃报告（魔数 `ISAACGP1`）交叉验证：1 个玩家、
// `Type == 1`、`Variant == 0`、`SubType == 0`、`PlayerType == 0`（Isaac）、下标 0、
// 位置 `(80.0, 280.0)`、vptr 命中。所以这里按"已证事实"实现，不再重新验证偏移。
//
// **读是只读的；写只有一个入口**（2026-09-16 起）：`Position`/`Velocity`/`Size`/收藏品数组
// 这些字段仍然只读 —— 它们参与碰撞、AI、掉落与存档，写坏的症状是随机崩溃或存档损坏，
// 而"写哪些字段、什么时机写是安全的"目前只有 `ControlsCooldown` 一条有 PC 语义与引擎读点
// 双重支撑（见 `EntityNewIndex`）。其余写路径一律经 `WriteEngine`，且必须先确认该页可写。
// 「这段地址可读吗」：**唯一实现在引擎内存访问层里**（2026-09-24 批次 102 收敛）。
// 此前四个 API 族各有一份逐字相同的拷贝（去掉注释后各 781 字符）；判决条件一条没改，
// 只是"实现在几处"从 4 变成了 1。**函数名保留** —— `test_lua_missing_members_batch028`
// 按这个名字核对四个手写处理器体里有没有做可读性检查。
bool IsEngineMemoryReadable(std::uintptr_t address, std::size_t length) noexcept {
    return isaac::runtime::engine_memory::EngineMemoryReadable(address, length);
}

// 读一个引擎字段：先做可读性检查再按 `T` 取值。指针猜错时必须变成"读不到"而不是"读了就崩"。
//
// 2026-09-24（批次 113）：**实现搬进引擎内存访问层**（`engine_memory::ReadAt`）—— 本 TU 只剩一行
// 委托，与写侧的 `WriteEngine`、以及上面那份 `IsEngineMemoryReadable` 同例（保留名字是为了
// **几十个调用点**与既有门禁的稳定）。判据一条没改：先可读、再取值；失败时**不写**出参。
template <typename T>
bool ReadEngine(std::uintptr_t address, T* value) noexcept {
    return isaac::runtime::engine_memory::ReadAt(address, value, &IsEngineMemoryReadable);
}

// 写一个引擎字段（2026-09-16 新增，与上面的读原语成对；2026-09-24 批次 103 收敛进访问层）。
//
// 上面那段"本批次不提供任何写引擎内存的接口"的注释是批次 3 的口径，从**写通道**这一批起
// 被取代：现在**允许**写，但只有一个入口（`WriteEngine`）且必须先确认"这一页可写"。
//
// 判据与写缓存**都不在这个 TU 里了**：「这段地址可写吗」现在**唯一实现在引擎内存访问层里**
// （`EngineMemoryWritable`：按 `Perm_W`、走**写**缓存 —— 可读 `Perm_R` 不等于可写 `Perm_W`，
// 模块映像的代码段与只读数据段就是可读不可写）。**函数名保留** ——
// 契约测试按这个名字核对两个可写 TU 都只是委托，实现只有一份。
//
// 目前唯一的调用点是 `EntityPlayer.ControlsCooldown`（`EntityNewIndex`）—— EID 用它抑制输入。
// 其它字段**没有**写入口，理由与批次 3 相同：写参与碰撞/AI/掉落/存档的字段，症状是随机崩溃
// 或存档损坏，必须有证据才做。
bool IsEngineMemoryWritable(std::uintptr_t address, std::size_t length) noexcept {
    return isaac::runtime::engine_memory::EngineMemoryWritable(address, length);
}

// 写引擎字段的唯一入口：判定（注入上面那份可写判定）+ 落值，都落在访问层里。
template <typename T>
bool WriteEngine(std::uintptr_t address, const T& value) noexcept {
    return isaac::runtime::engine_memory::WriteAt(address, value, &IsEngineMemoryWritable);
}

// 玩家数量上限（`kEnginePlayerMaximumCount`）现在是共享常量（`runtime_constants.hpp`），
// 因为 `Game:GetNumPlayers`（`game_api.cpp`）用同一条向量做同一层保险。

// `*(u64*)candidate == base + kEntityPlayerVtableOffset` —— 判"这个指针真是一张 Entity_Player"
// 的最强判据（真机探针的 bit4 就是它，已命中）。
bool IsEntityPlayer(std::uintptr_t candidate) noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (candidate == 0 || base == 0 || base > UINTPTR_MAX - kEntityPlayerVtableOffset) {
        return false;
    }
    std::uintptr_t vtable = 0;
    if (!ReadEngine(candidate, &vtable)) {
        return false;
    }
    return vtable == base + kEntityPlayerVtableOffset;
}

// 引擎 `Game` 的玩家向量首尾（`Game + kGamePlayerArrayBeginOffset/EndOffset`）。
// 返回 0 表示"读不到"（基址未发布 / 槽不可读 / 槽为空 / `Game` 为空 / 向量不可读或不自洽）。
//
// 这是**唯一**一处做这件事的地方：`Isaac.GetPlayer` 与 `Game:GetNumPlayers` 都从这里取答案，
// 因此不可能再出现"一个说有 1 个玩家、另一个说玩家是 nil"（真机报告 `01789207110` 的缺陷）。
// `Isaac.FindInRadius` 的探针读数（2026-09-12）：描述文字一个字都没画出来，而
// `Font:DrawString*` 调用次数为 0 —— 说明 EID 的 `OnRender` 没走到绘制。它选描述的第一步就是
// `Isaac.FindInRadius(sourcePos, MaxDistance*40, searchPartitions)`（`main.lua:1466`），
// 所以"这个查询到底找出了几个实体"是下一个分界点：
//   * 查询恒返回空 ⇒ 问题在我们这边（房间指纹/分区掩码/半径判据）；
//   * 查询有结果而描述仍不出 ⇒ 问题在描述构建/选择。
// `Isaac.GetPlayer` 的成功/失败计数（原因 1）：EID 的 `EID.player` 依赖它；恒失败则
// `OnRender` 里的 `for ... in ipairs({ EID.player })` 一次都不执行，描述第一步永不发生。
std::atomic<std::uint32_t> g_GetPlayerSuccess{0};
std::atomic<std::uint32_t> g_GetPlayerFailure{0};
std::atomic<std::uint32_t> g_FindInRadiusCalls{0};
std::atomic<std::uint32_t> g_FindInRadiusResults{0};
std::atomic<std::uint32_t> g_FindInRadiusLive{0};
std::atomic<std::uint32_t> g_FindInRadiusPlayers{0};
std::atomic<std::uint32_t> g_FindInRadiusEffects{0};
std::atomic<std::uint32_t> g_FindInRadiusRoomOk{0};
std::atomic<std::uint32_t> g_FindInRadiusFingerprint{0};
std::atomic<std::uint32_t> g_FindInRadiusLastMask{0};
std::atomic<std::uint32_t> g_FindInRadiusLastRadius{0};



// 玩家查询的**阶段码**（探针读；语义见 `EnginePlayerLookup::stage` 的注释）。
std::atomic<std::uint32_t> g_EnginePlayerLookupStage{0};
std::atomic<std::uintptr_t> g_EnginePlayerLookupFirst{0};
std::atomic<std::uintptr_t> g_EnginePlayerLookupVtable{0};

std::atomic<std::uint32_t> g_EnginePlayerLookupCount{0};
// `ResolveEnginePlayerBegin` **自己**读到的 begin/end（探针用：与探针那一侧的读数对照，
// 才能分清"解析器读不到"与"探针读法不同"）。
std::atomic<std::uintptr_t> g_ResolverBegin{0};
std::atomic<std::uintptr_t> g_ResolverEnd{0};

void RecordEnginePlayerLookup(std::uint32_t stage, std::uintptr_t first,
                              std::uintptr_t second, std::uint32_t count = 0) noexcept {
    (void)stage;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)first;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)second;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
    (void)count;  // 批次 232：生产构建里这段被编译掉 ⇒ 参数必然用不上
#if EXL_DIAGNOSTIC_PROBES  // 批次 232 探针总开关（口径见 probe_gate.hpp）
    g_EnginePlayerLookupCount.store(count, std::memory_order_relaxed);
    g_EnginePlayerLookupVtable.store(second, std::memory_order_relaxed);
    g_EnginePlayerLookupFirst.store(first, std::memory_order_relaxed);
    g_EnginePlayerLookupStage.store(stage, std::memory_order_release);
#endif  // EXL_DIAGNOSTIC_PROBES
}

std::uintptr_t ResolveEntityPlayerBegin(std::uintptr_t* beginOut, std::size_t* countOut) noexcept {
    if (beginOut == nullptr || countOut == nullptr) {
        RecordEnginePlayerLookup(1, 0, 0);
        return 0;
    }
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameOwnerGlobalSlotOffset) {
        RecordEnginePlayerLookup(1, 0, 0);
        return 0;
    }
    // 两级解引用：槽里是**指针变量**，`*(u64*)槽` 才是 `Game*`。
    std::uintptr_t ownerSlot = 0;
    std::uintptr_t game = 0;
    if (!ReadEngine(base + kGameOwnerGlobalSlotOffset, &ownerSlot) || ownerSlot == 0) {
        RecordEnginePlayerLookup(2, 0, 0);
        return 0;
    }
    if (!ReadEngine(ownerSlot, &game) || game == 0 ||
        game > UINTPTR_MAX - kGamePlayerArrayEndOffset) {
        RecordEnginePlayerLookup(3, 0, 0);
        return 0;
    }
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    // **判据只用值本身，不用"那次读成功了吗"（2026-09-12 第四轮真机定案）**。
    //
    // 为什么：真机报告 `01789209282` 里，探针（另一个回调）**直接读同一个地址成功**，而
    // `Isaac.GetPlayer` 路径上那次读被 `ReadEngine` 判为失败 —— 同一个地址、同一帧，结论相反。
    // 说明 `ReadEngine` 的成功条件是**环境相关**的（它对 `__SWITCH__` 走 `svcQueryMemory` 的
    // 页属性检查，读不到只代表"这一刻不该读"，不代表"值不是 0"）。把它当作"内存里没有这个值"
    // 的证据，就会把默认构造的空向量误判成"读不到"。
    //
    // 于是这里改成纯值判据，而 `std::vector` 的默认构造形态（`begin == end == 0`）是**合法空向量**：
    //   * `begin == 0 && end == 0` → count = 0，readable = true（"确实没有玩家"，而不是"读不到"）；
    //   * `end >= begin` 且 `begin != 0` → 正常，count = (end - begin) / 8；
    //   * 其余（`begin == 0` 但 `end != 0`、或 `end < begin`）→ 区间不自洽，阶段 4。
    //
    // 这一条修正的直接后果：EID 的 `for i = 0, game:GetNumPlayers() - 1 do local player =
    // Isaac.GetPlayer(i) ... player.QueuedItem`（`features/eid_api.lua:2620-2625`）在"还没有
    // 玩家"的帧上不会再拿到 nil（循环次数为 0），也就不会再抛错、被派发器静默摘除。
    // 两次读的**返回值刻意不用**（见上）：值才是判据。
    const bool beginRead = ReadEngine(game + kGamePlayerArrayBeginOffset, &begin);
    const bool endRead = ReadEngine(game + kGamePlayerArrayEndOffset, &end);
    g_ResolverBegin.store(beginRead ? begin : ~static_cast<std::uintptr_t>(0),
                          std::memory_order_relaxed);
    g_ResolverEnd.store(endRead ? end : ~static_cast<std::uintptr_t>(0),
                        std::memory_order_relaxed);
    if (begin == 0 && end == 0) {
        // 合法空向量（也涵盖"两次读都没读到"这种最坏情形）：如实报 0 个玩家。
        // 宁可让 `Game:GetNumPlayers()` 答"没有玩家"（那时 `Isaac.GetPlayer(0)` 本来就是 nil），
        // 也不要答"有 1 个玩家"然后让 Mod 去索引一个 nil。
        *beginOut = 0;
        *countOut = 0;
        RecordEnginePlayerLookup(0, 0, 0, 0);
        return 0;
    }
    if (begin == 0 || end < begin) {
        RecordEnginePlayerLookup(4, begin, end);
        return 0;
    }
    const std::size_t count = static_cast<std::size_t>((end - begin) / sizeof(std::uintptr_t));
    if (count > kEnginePlayerMaximumCount) {
        RecordEnginePlayerLookup(5, 0, 0);
        return 0;
    }
    *beginOut = begin;
    *countOut = count;
    RecordEnginePlayerLookup(0, 0, 0, static_cast<std::uint32_t>(count));
    return begin;
}

// `Isaac.GetPlayer(index)` 的整条链路。返回 0 表示"拿不到"，调用方据此返回 nil：
// 向量读不到 / 下标越界 / 元素为空 / vptr 不匹配。
std::uintptr_t ResolveEntityPlayer(std::size_t index, bool fallbackFirst = false) noexcept {
    std::uintptr_t begin = 0;
    std::size_t count = 0;
    if (ResolveEntityPlayerBegin(&begin, &count) == 0) {
        return 0;  // 阶段码已由 ResolveEntityPlayerBegin 记录（1..5）
    }
    if (index >= count) {
        if (!fallbackFirst || count == 0) {
            RecordEnginePlayerLookup(6, 0, 0);
            return 0;
        }
        index = 0;
    }
    std::uintptr_t player = 0;
    std::uintptr_t vtable = 0;
    if (!ReadEngine(begin + index * sizeof(std::uintptr_t), &player) || player == 0) {
        RecordEnginePlayerLookup(7, 0, 0);
        return 0;
    }
    if (!ReadEngine(player, &vtable) || !IsEntityPlayer(player)) {
        // 这一档最值钱：元素存在、指针非空，但 vptr 不是 `Entity_Player`
        // （偏移不对 / 该槽放的是别的实体 / 内存还没写好）。把原始 vptr 报出来。
        RecordEnginePlayerLookup(8, player, vtable);
        return 0;
    }
    RecordEnginePlayerLookup(0, player, vtable);
    return player;
}

void PushEntityHandle(lua_State* state, std::uintptr_t entity, const char* metatable) {
    auto* token = isaac::runtime::PushEntityLifetimeToken(state, entity);
    const int tokenIndex = lua_gettop(state);
    auto* handle = static_cast<EntityHandle*>(lua_newuserdata(state, sizeof(EntityHandle)));
    handle->entity = engine_memory::AsObject(entity);
    handle->lifetime = token;
    lua_pushvalue(state, tokenIndex);
    lua_setuservalue(state, -2);
    luaL_getmetatable(state, metatable);
    lua_setmetatable(state, -2);
    lua_remove(state, tokenIndex);
}

// 前置声明：通用 `Entity` 判据定义在下面的"房间实体容器与查询"段（`ValidatedEntity` 要用它）。
bool IsEntityVtableInRange(std::uintptr_t vtable) noexcept;
bool IsEntityPointer(std::uintptr_t candidate) noexcept;

// 句柄 → 通过校验的实体指针（0 = 失效）。**每一次**访问都重做校验：句柄可能跨过换局/重开一局，
// 过期的原生指针绝不允许被解引用。
//
// 批次 4 起判据从"vptr == `Entity_Player`"放宽成**通用 `Entity`**：`vptr` 落在
// `[base + 0xA34F58, base + 0xA38230)`（`Entity` 家族的 vtable 区间，见 `runtime_constants.hpp`）。
// 之所以能放宽：句柄里的指针**只可能**来自实体容器遍历（`Isaac.FindInRadius`/`FindByType`）
// 或玩家向量的遍历结果（`Isaac.GetPlayer`），区间校验是第二道闸门而不是身份来源。
std::uintptr_t ValidatedEntity(const EntityHandle* handle) noexcept {
    if (handle == nullptr || !isaac::runtime::EntityLifetimeAlive(handle->lifetime)) {
        return 0;
    }
    const std::uintptr_t candidate = engine_memory::AddressOf(handle->entity);
    return IsEntityPointer(candidate) ? candidate : 0;
}

// `EntityPlayer` 专属方法（`HasCollectible`/`GetPlayerType`/血量/主动道具/饰品/`GetData`）
// 仍然要求**精确**的 `Entity_Player` vptr：区间校验只保证"这是一张 Entity"，把一张眼泪或
// 掉落物当玩家去读 `+0x16B8` 虽然不会越界，但拿到的是别人的字段。
std::uintptr_t ValidatedEntityPlayer(const EntityHandle* handle) noexcept {
    if (handle == nullptr || !isaac::runtime::EntityLifetimeAlive(handle->lifetime)) {
        return 0;
    }
    const std::uintptr_t candidate = engine_memory::AddressOf(handle->entity);
    return IsEntityPlayer(candidate) ? candidate : 0;
}

// `EntityFamiliar` 专属方法（`FollowParent` / `AddToFollowers`）的接收者判据 ——
// **精确**的 `base + kEntityFamiliarVtableOffset` **且** `Type == kEntityTypeFamiliar`。
//
// ★★ 为什么这里**必须**精确判、不能像 `Entity` 那一档只做区间校验：这两条是**调用**而不是读常量 ——
//   `Entity_Familiar::follow_parent()` 的**第一条字段访问**就是 `ldr x8, [x0, #0xf50]`，紧跟
//   `cbz x8` 之后**解引用**它（`ldr w9, [x8]`）⇒ 拿一个别的实体当 `this` 交进去，那一格是
//   "恰好落在对象内部的某个值"，很可能是个非空垃圾指针 ⇒ **野读**。
//   （读字段那类错类型只会读到别人的值，调函数那类会顺着垃圾指针跑出去。）
//
// ★ 判据与 `Entity:ToFamiliar()` 里那条**同一份**（批次 330 起两者共用这个函数）：
//   那边原来是就地写死的四行，本批抽出来 —— 同一件事不许有两份实现。
std::uintptr_t ValidatedEntityFamiliar(const EntityHandle* handle) noexcept {
    if (handle == nullptr || !isaac::runtime::EntityLifetimeAlive(handle->lifetime)) {
        return 0;
    }
    const std::uintptr_t candidate = engine_memory::AddressOf(handle->entity);
    const std::uintptr_t base = EngineModuleBase();
    std::uintptr_t vtable = 0;
    std::uint32_t type = 0;
    if (candidate == 0 || base == 0 || base > UINTPTR_MAX - kEntityFamiliarVtableOffset ||
        !ReadEngine(candidate, &vtable) || !ReadEngine(candidate + kEntityTypeOffset, &type)) {
        return 0;
    }
    return (type == kEntityTypeFamiliar && vtable == base + kEntityFamiliarVtableOffset)
               ? candidate
               : 0;
}

// 先验寿命由ValidatedEntity检查；具体子类再核真实vptr与Type，避免兄弟类字段/方法野读。
bool IsTypedEntity(std::uintptr_t entity, std::uintptr_t vtableOffset,
                   std::uint32_t expectedType) noexcept {
    const auto base = EngineModuleBase();
    std::uintptr_t vtable = 0;
    std::uint32_t type = 0;
    return entity != 0 && base != 0 && base <= UINTPTR_MAX - vtableOffset &&
           ReadEngine(entity, &vtable) && ReadEngine(entity + kEntityTypeOffset, &type) &&
           vtable == base + vtableOffset && type == expectedType;
}

std::uintptr_t ValidatedTypedEntity(const EntityHandle* handle, std::uintptr_t vtableOffset,
                                    std::uint32_t expectedType) noexcept {
    const auto entity = ValidatedEntity(handle);
    return IsTypedEntity(entity, vtableOffset, expectedType) ? entity : 0;
}

// `ToPlayer` / `ToPickup` / `GetData` 挂在 `Entity`（PC 就在基类上），但调用方拿到的通常是
// `EntityPlayer`/`EntityPickup` 视图，所以三张元表都要接受：只认一张会在 `player:ToPlayer()`
// 处误报。
//
// ★★ 2026-09-29 补上**第四张** `EntityProjectile`（批次 207 `Entity:ToProjectile()` 的返回值）。
//   缺它的后果（宿主行为测试 `runtime/tests/test_lua_api_gap_mcm.py` 抓到的**真缺陷**）：
//   `local p = entity:ToProjectile()` 之后，`p:ToProjectile()` **报错**
//   `expected an Entity, EntityPlayer or EntityPickup` —— 也就是说
//   `EntityToProjectile()` 里那段"已经是投射物视图 ⇒ `lua_pushvalue` 返回自己"的
//   身份相等分支**永远不可达**（`CheckEntityHandle` 先一步长跳出去了）。
//   影响面不止那一条：`EntityProjectile` 的 `__methods` 是空的、方法全回落到 `Entity`
//   （与 PC 的继承一致），而 `Entity` 那一族里**所有**走 `CheckEntityHandle` 的方法
//   （`ToPickup`/`ToPlayer`/`GetData`/`HasEntityFlags`/`IsActiveEnemy`…，共 20 余处）
//   在投射物视图上都会误报。PC 里 `EntityProjectile` 就是 `Entity` 的子类，
//   宽进来是纠正、不是放宽。
//
// 宽进来安全：四张元表的句柄体都是同一个 `EntityHandle`（"一个原生实体指针"），
// 真正的身份判据在后面 —— `ValidatedEntity`（`Entity` 家族的 vtable 区间）与
// `ValidatedEntityPlayer`（**精确**的 `Entity_Player` vptr）照旧逐次重做，
// 所以玩家专属字段不会因为这一句而串到别的实体上。
// 全部实体视图复用同一句柄布局，识别名单只能有一份。此处仅识别Lua userdata，
// 后续ValidatedEntity/Player必须先核token再碰引擎内存；不是实体返回空且不抛错。
EntityHandle* TryGetEntityHandle(lua_State* state, int index) noexcept {
    if (state == nullptr || index == 0) {
        return nullptr;
    }
    constexpr const char* metatables[] = {
        kEntityPlayerMetatable, kEntityMetatable, kEntityPickupMetatable,
        kEntityProjectileMetatable, kEntityTearMetatable, kEntityBombMetatable,
        kEntityLaserMetatable, kEntityKnifeMetatable, kEntityNPCMetatable, kEntityFamiliarMetatable,
    };
    // 玩家保留原来的短路径；其余视图在本次识别中共用真实元表。
    auto* handle = static_cast<EntityHandle*>(luaL_testudata(state, index, metatables[0]));
    if (handle != nullptr) return handle;
    handle = static_cast<EntityHandle*>(lua_touserdata(state, index));
    if (handle == nullptr) return nullptr;
    // registry 自带元方法时保留原探测次序，避免改变动态查找的副作用。
    if (lua_getmetatable(state, LUA_REGISTRYINDEX)) {
        lua_pop(state, 1);
    } else if (lua_getmetatable(state, index)) {
        for (std::size_t i = 1; i < sizeof(metatables) / sizeof(metatables[0]); ++i) {
            luaL_getmetatable(state, metatables[i]);
            const bool same = lua_rawequal(state, -1, -2) != 0;
            lua_pop(state, 1);
            if (same) {
                lua_pop(state, 1);
                return handle;
            }
        }
        lua_pop(state, 1);
        return nullptr;
    }
    // registry 带元方法时，每一步重新取对象元表，保留原查找的副作用。
    for (std::size_t i = 1; i < sizeof(metatables) / sizeof(metatables[0]); ++i) {
        if (auto* found = static_cast<EntityHandle*>(luaL_testudata(state, index, metatables[i]))) {
            return found;
        }
    }
    return nullptr;
}

EntityHandle* CheckEntityHandle(lua_State* state, int index) {
    auto* handle = TryGetEntityHandle(state, index);
    if (handle == nullptr) {
        luaL_error(state,
                   "expected an Entity, EntityPlayer, EntityPickup, EntityProjectile, EntityTear, "
                   "EntityLaser, EntityNPC, EntityBomb or EntityFamiliar");
        return nullptr;  // 不会到达：`luaL_error` 长跳到受保护调用
    }
    return handle;
}

// 读一个整型参数。**接受范围与 PC 的 `luaL_checkinteger` 一致**：整数、整值浮点（`57.0`）、
// 可转换的数字串都收，`1.5`/`"nope"`/缺参数都不收 —— 与 `ReadItemId` 同一口径。
//
// 为什么不能用"只认整数子类型"那个判据：Lua 5.3 里 `57.0` 是 **float**，该判据返回 false，
// 而 `lua_tointegerx` 会把它精确转成 57。Mod 写 `EntityPartition.ENEMY * 1.0` 或者把掩码
// 从配置里读出来（JSON 数字都是 float）都会踩到这条：判错就会安静地返回空表。
bool ReadIntegerArgument(lua_State* state, int index, lua_Integer* value) noexcept {
    if (value == nullptr || lua_gettop(state) < index) {
        return false;
    }
    int isNumber = 0;
    const lua_Integer converted = lua_tointegerx(state, index, &isNumber);
    if (isNumber == 0) {
        return false;
    }
    *value = converted;
    return true;
}

// --- 房间实体容器与查询（批次 4）-----------------------------------------------
//
// 全部偏移的出处 = `runtime_constants.hpp` 的"房间实体容器"段（2026-09-12 反汇编静态定位，
// `docs/问题与解决记录.md` 批次 4；`Room::AddEntity` 的 `add x0,x0,#0x1950` 是内嵌而非指针的铁证）。
// 五条纪律：
//
//   1. **只读**。这一整段不写引擎内存（唯一的写是 `GetData()` 自己那张 Lua 表）。
//   2. **每次都校验容器指纹**（`EL+0x50==0x4000 && EL+0x80==0x800 && EL+0xE0==0x8000`）。
//      三个容量都是固定常量、从不重分配，所以它们同时是"这段内存真是一张 `EntityList`"的
//      判据。指纹不匹配 → 返回**空结果**，不报错、不解引用。
//   3. **count 必须 <= 容量**，否则整张表作废（防止把垃圾当长度去遍历）。
//   4. **不缓存实体指针跨帧**：句柄里的地址只当身份，每次访问重做 vptr 校验。
//      （`GetData()` 的Lua表仅跟随真实实体寿命，见 `entity_lifetime.cpp`。）
//   5. 不调引擎的 `QueryRadius`/`QueryType`：它们的 sret 指向 `EL+0xD8` 的**单调 arena**，
//      不可重入、不可跨帧持有。自己遍历 `EL+0x78`（引擎 `collide`/`Update`/`CountType` 用的
//      同一张表）更稳。

// `Game*`：与 `Isaac.GetPlayer` **完全同一条链**（模块基址 + `kGameOwnerGlobalSlotOffset`
// 是 `g_Game` 的槽，槽里是**指针变量**，解一次才是 `Game*`）。0 = 拿不到。
std::uintptr_t ResolveGameAddress() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameOwnerGlobalSlotOffset) {
        return 0;
    }
    std::uintptr_t ownerSlot = 0;
    std::uintptr_t game = 0;
    if (!ReadEngine(base + kGameOwnerGlobalSlotOffset, &ownerSlot) || ownerSlot == 0 ||
        !ReadEngine(ownerSlot, &game) || game == 0) {
        return 0;
    }
    return game;
}

// `Isaac.GetChallenge()` —— PC 契约 `tools/pc_contract_docs/Isaac.md:171`
// `#### [Challenge](enums/Challenge.md) GetChallenge ( )`，正文逐字：
// 「Returns the ID of a challenge the player is currently in. **Returns 0 if the player is not
//  playing any challenge.**」
//
// 真值来源：`Game + 0x26FA88` 的那一格（`eChallenge` 枚举原值，int32）。偏移的取证在
// `runtime_constants.hpp` 的 `kGameChallengeOffset` 段，两条独立指令证据：
//   * `Game::Start(ePlayerType, eChallenge, …) @ 0x34E570` 的 `str w2,[x21]`（x21 = this+0x26FA88）
//     —— 把第 2 个**形参**直接写进去；
//   * `Game::GetChallengeParams() const @ 0x34EA9C` 的 `ldr w1,[x8]`（同样 this+0x26FA88）
//     后尾跳到 `Manager::GetChallengeParams(eChallenge)` —— 读出来当枚举传给挑战参数表。
// 另有 `Game::Init` 归零、`SaveState`/`RestoreState` 在 GameState+0x00 来回抄两条旁证。
//
// 语料用法（`MinimapAPI/scripts/minimapapi/main.lua:1446` 等 9 处）都是
// `Isaac.GetChallenge() == Challenge.CHALLENGE_APRILFOOLS` 这类**枚举比较** ⇒ 返回的就是这个原值。
//
// 失败降级（作业单第三节第 11 条）：拿不到 `Game` 或内存不可读 ⇒ 压 `0`
// —— 这正是契约原文里的"没在挑战局"那一个值，与 PC 一致，且**不抛错**。
int IsaacGetChallenge(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Isaac.GetChallenge accepts no arguments");
    }
    std::int32_t challenge = 0;
    const std::uintptr_t game = ResolveGameAddress();
    if (game != 0 && game <= UINTPTR_MAX - kGameChallengeOffset &&
        ReadEngine(game + kGameChallengeOffset, &challenge)) {
        lua_pushinteger(state, static_cast<lua_Integer>(challenge));
        return 1;
    }
    lua_pushinteger(state, 0);
    return 1;
}

// `Room*` = `*(u64*)(Game + 0x21550)`（`Level` 内嵌在 `Game` 起始处，这是 Level 的那个成员）。
std::uintptr_t ResolveRoom() noexcept {
    const std::uintptr_t game = ResolveGameAddress();
    if (game == 0 || game > UINTPTR_MAX - kGameRoomPointerOffset) {
        return 0;
    }
    std::uintptr_t room = 0;
    if (!ReadEngine(game + kGameRoomPointerOffset, &room)) {
        return 0;
    }
    return room;
}

// `EL+0x1950 + 相对偏移`：内嵌对象，所以是**加法**。
struct EntityTableSpec {
    std::uintptr_t beginOffset;
    std::uintptr_t capacityOffset;
    std::uintptr_t countOffset;
    std::uint32_t expectedCapacity;
};

// 活表（`EL+0x78`，cap 0x800）：房间内活动实体全集，枚举用它。
constexpr EntityTableSpec kLiveEntityTable{kEntityListLiveBeginOffset,
                                           kEntityListLiveCapacityOffset,
                                           kEntityListLiveCountOffset, kEntityListLiveCapacity};
// EFFECT 表（`EL+0xA8`，cap 0x4000）：`Type == 0x3E8` 走这张。
constexpr EntityTableSpec kEffectEntityTable{kEntityListEffectBeginOffset,
                                             kEntityListEffectCapacityOffset,
                                             kEntityListEffectCountOffset,
                                             kEntityListGeneralCapacity};

struct EntityTableView {
    std::uintptr_t begin{0};
    std::uint32_t count{0};
};

// 容器指纹：三个固定容量必须同时成立（顺序与 `docs/问题与解决记录.md` 一致）。
bool EntityListFingerprintMatches(std::uintptr_t list) noexcept {
    if (list == 0) {
        return false;
    }
    std::uint32_t generalCapacity = 0;
    std::uint32_t liveCapacity = 0;
    std::uint32_t arenaCapacity = 0;
    if (!ReadEngine(list + kEntityListGeneralCapacityOffset, &generalCapacity) ||
        !ReadEngine(list + kEntityListLiveCapacityOffset, &liveCapacity) ||
        !ReadEngine(list + kEntityListArenaCapacityOffset, &arenaCapacity)) {
        return false;
    }
    return generalCapacity == kEntityListGeneralCapacity &&
           liveCapacity == kEntityListLiveCapacity &&
           arenaCapacity == kEntityListArenaCapacity;
}

// 读一条 `Entity**` 表：先校验它自己的容量（指纹的一部分），再校验 `count <= cap`，
// 最后**一次**可读性检查覆盖整个元素数组（真机上 `svcQueryMemory` 是系统调用，逐个元素检查
// 会让一次全房间扫描变成上千次调用，所以元素读取用 `ReadEngineUnchecked`）。
bool ReadEntityTable(std::uintptr_t list, const EntityTableSpec& spec, EntityTableView* view) noexcept {
    if (list == 0 || view == nullptr || list > UINTPTR_MAX - spec.countOffset) {
        return false;
    }
    std::uint32_t capacity = 0;
    std::uint32_t count = 0;
    if (!ReadEngine(list + spec.capacityOffset, &capacity) ||
        capacity != spec.expectedCapacity ||
        !ReadEngine(list + spec.countOffset, &count) || count > capacity) {
        return false;
    }
    view->begin = 0;
    view->count = count;
    if (count == 0) {
        return true;
    }
    std::uintptr_t begin = 0;
    if (!ReadEngine(list + spec.beginOffset, &begin) || begin == 0 ||
        !IsEngineMemoryReadable(begin, static_cast<std::size_t>(count) * sizeof(std::uintptr_t))) {
        return false;
    }
    view->begin = begin;
    return true;
}

// 已经用一次可读性检查覆盖过整段时使用：只按 `T` 取值，不再重复系统调用。
//
// 2026-09-24（批次 113）：**实现搬进引擎内存访问层**（`engine_memory::LoadVerified`），本 TU 只剩
// 一行委托（与上面 `ReadEngine` 同例）。判据：`address == 0` 或出参为空 ⇒ **一个字节都不取**、
// 返回假 —— 原来那种形态会从地址 0 直接 `memcpy`；调用点都已经过整段核对，这里顺带把那种形态堵上。
template <typename T>
bool ReadEngineUnchecked(std::uintptr_t address, T* value) noexcept {
    return isaac::runtime::engine_memory::LoadVerified(address, value);
}

//: 那 13 个**已知非 NPC** 的 `Entity` 直接子类（含 `Entity` 本体）的 vtable 偏移。
//: 依据：按"长度前缀"正确解析嵌套名之后，`Entity` 的直接子类**恰好 13 个**，
//: 除 `Entity_NPC` 之外全在这里（见 `runtime_constants.hpp` 批次 243 段的注释）。
constexpr std::uintptr_t kNonNpcEntityVtables[] = {
    kEntityBaseVtableOffset,     kEntityBombVtableOffset,   kEntityDummyVtableOffset,
    kEntityEffectVtableOffset,   kEntityFamiliarVtableOffset, kEntityKnifeVtableOffset,
    kEntityLaserVtableOffset,    kEntityPickupVtableOffset, kEntityPlayerVtableOffset,
    kEntityProjectileVtableOffset, kEntitySlotVtableOffset, kEntityTearVtableOffset,
    kEntityTextVtableOffset,
};

//: **是不是 `Entity_NPC` 家族**（= `Entity` 家族区间内、且不是那 13 个已知非 NPC 直接子类）。
//: 三处共用：`Entity:ToNPC()` 的转型判据、`Scale` 字段的读写判据（`Scale` 只挂在 `EntityNPC` 页上，
//: `tools/pc_contract_docs/EntityNPC.md:225`）。**判据只有一份**，免得日后漂开。
bool IsNpcFamilyEntity(std::uintptr_t entity) noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (entity == 0 || base == 0) {
        return false;
    }
    std::uintptr_t vtable = 0;
    if (!ReadEngine(entity, &vtable) || !IsEntityVtableInRange(vtable)) {
        return false;
    }
    for (const std::uintptr_t offset : kNonNpcEntityVtables) {
        if (base <= UINTPTR_MAX - offset && vtable == base + offset) {
            return false;
        }
    }
    return true;
}

// `vptr` 是否落在 `Entity` 家族的 vtable 区间里。
bool IsEntityVtableInRange(std::uintptr_t vtable) noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || vtable == 0 || base > UINTPTR_MAX - kEntityVtableRangeEndOffset) {
        return false;
    }
    return vtable >= base + kEntityVtableRangeBeginOffset &&
           vtable < base + kEntityVtableRangeEndOffset;
}

// 通用 `Entity` 判据：`Type` 无关，只看 vptr 是否落在 `Entity` 家族的 vtable 区间里。
//
// 为什么这是安全的：`vtable` 是我们**先读出来**再比较的值，比较之前不解引用任何东西；
// 猜错的指针只会让 `vptr` 落在区间外而被拒。
bool IsEntityPointer(std::uintptr_t candidate) noexcept {
    if (candidate == 0) {
        return false;
    }
    std::uintptr_t vtable = 0;
    if (!ReadEngine(candidate, &vtable)) {
        return false;
    }
    return IsEntityVtableInRange(vtable);
}

// 扫描用的实体快照：**一次**可读性检查覆盖 `[entity, entity + 0x348)`，之后逐字段 `memcpy`。
struct EntitySnapshot {
    std::uintptr_t address{0};
    std::uintptr_t vtable{0};
    std::uint64_t flags{0};
    std::uint32_t type{0};
    std::uint32_t variant{0};
    std::uint32_t subType{0};
    std::uint32_t index{0};
    float x{0.0F};
    float y{0.0F};
    float size{0.0F};
};

bool CaptureEntityTypeSnapshot(std::uintptr_t address, EntitySnapshot* snapshot) noexcept {
    if (address == 0 || snapshot == nullptr ||
        !IsEngineMemoryReadable(address, kEntitySnapshotSpan)) {
        return false;
    }
    const auto field = [address](std::uintptr_t offset) noexcept {
        return address + offset;
    };
    std::uintptr_t vtable = 0;
    std::uint64_t flags = 0;
    if (!ReadEngineUnchecked(field(0), &vtable) || !ReadEngineUnchecked(field(kEntityFlagsOffset), &flags)) {
        return false;
    }
    if (!IsEntityVtableInRange(vtable)) {
        return false;
    }
    snapshot->address = address;
    snapshot->vtable = vtable;
    snapshot->flags = flags;
    static_cast<void>(ReadEngineUnchecked(field(kEntityTypeOffset), &snapshot->type));
    static_cast<void>(ReadEngineUnchecked(field(kEntityVariantOffset), &snapshot->variant));
    static_cast<void>(ReadEngineUnchecked(field(kEntitySubTypeOffset), &snapshot->subType));
    return true;
}

// `EntityFlag.FLAG_NO_QUERY`（`+0x1B8` bit46）：查询结果里必须跳过它。
bool EntityHasNoQueryFlag(const EntitySnapshot& snapshot) noexcept {
    return (snapshot.flags & (1ULL << kEntityFlagNoQueryBit)) != 0;
}

// PC `EntityPartition` 的位（`enums.lua:4489`；与引擎 `w2` 掩码逐位一致）。
constexpr std::uint32_t kPartitionFamiliar = 1U << 0;
constexpr std::uint32_t kPartitionBullet = 1U << 1;
constexpr std::uint32_t kPartitionTear = 1U << 2;
constexpr std::uint32_t kPartitionEnemy = 1U << 3;
constexpr std::uint32_t kPartitionPickup = 1U << 4;
constexpr std::uint32_t kPartitionPlayer = 1U << 5;
constexpr std::uint32_t kPartitionEffect = 1U << 6;
// 活表里"除了 PLAYER 之外的普通分区"。PLAYER 由玩家向量单独提供（引擎自己也不走 CellSpace）。
constexpr std::uint32_t kLiveTablePartitions =
    kPartitionFamiliar | kPartitionBullet | kPartitionTear | kPartitionEnemy | kPartitionPickup;

// 分类判据：逐条照抄引擎 `EntityList::collide()`（`0x77690`–`0x778a0` 的跳转表）。
std::uint32_t ClassifyEntity(const EntitySnapshot& snapshot) noexcept {
    const std::uint32_t type = snapshot.type;
    if (type == 2) return kPartitionTear;
    if (type == 3) return snapshot.variant == 0xEF ? kPartitionEnemy : kPartitionFamiliar;
    if (type == 8) return kPartitionTear;    // KNIFE
    if (type == 9) return kPartitionBullet;  // PROJECTILE
    if (type == 5 || type == 6) return kPartitionPickup;
    if (type == 4) return kPartitionEnemy;   // BOMB
    if (type == kEntityTypeEffect) return kPartitionEffect;
    if (type == kEntityTypePlayer) return kPartitionPlayer;
    if (type - kEntityEnemyTypeBase < kEntityEnemyTypeSpan) return kPartitionEnemy;
    return 0;
}

// NPC类型区间：用于实体分类；活敌人/战斗计数须读房间原生计数，不能套用此区间。
bool IsEnemyType(std::uint32_t type) noexcept {
    return type - kEntityEnemyTypeBase < kEntityEnemyTypeSpan;
}

// 半径判据（引擎原文）：`dist² < (radius + e.Size)²` —— **把实体 Size 加进半径**。
bool EntityMatchesRadius(const EntitySnapshot& snapshot, double x, double y,
                         double radius) noexcept {
    const double dx = static_cast<double>(snapshot.x) - x;
    const double dy = static_cast<double>(snapshot.y) - y;
    const double reach = radius + static_cast<double>(snapshot.size);
    return dx * dx + dy * dy < reach * reach;
}

// 一次查询最多返回多少条。正常房间里是几十条；这个上限只为"容器被写坏成 count == cap"
// 这类情形兜底（`EL+0x78` 的 cap 是 0x800，EFFECT 表是 0x4000）。
constexpr std::size_t kMaximumQueryResults = 4096;

// 批次 428：`g_QuerySeen` 从"线性扫描的名单"改成**开放寻址的哈希表**的键数组。
// 为什么：线性去重最坏是 4096² ≈ 1600 万次比较**每查询**，而 `Isaac:GetRoomEntities` 每秒 120 次、
// `Isaac:FindInRadius` 每秒 66 次（API 层归因实测）⇒ 房间实体一多就要真付这笔钱。
// 表长取 2 的幂且 = 2× 上限（负载 ≤ 0.5）⇒ 线性探测**必定**找得到空槽，不会绕不出去。
constexpr std::size_t kQueryDedupSlots = 8192;
static_assert((kQueryDedupSlots & (kQueryDedupSlots - 1)) == 0, "去重表长必须是 2 的幂");
static_assert(kQueryDedupSlots >= 2 * kMaximumQueryResults, "负载必须 ≤ 0.5");

std::uintptr_t g_QuerySeen[kQueryDedupSlots] = {};
//: 槽的**世代标签**：槽属于哪一次查询。★ 用它就不必在每次查询开头清 64 KB —— 只要
//: `g_QuerySeenEpoch` 一涨，上一代的槽全部视作空（这是本批唯一"为了性能引入的新状态"，
//: 所以回绕必须显式清表：`++epoch` 到 0 时两数组清零并置 1）。
std::uint32_t g_QuerySeenEpoch[kQueryDedupSlots] = {};
std::uint32_t g_QueryEpoch = 0;
std::size_t g_QuerySeenCount = 0;

//: 实体指针 → 槽号。指针是 8 字节对齐 ⇒ 先除掉低 3 位，再乘一个奇数做斐波那契散列，
//: 取高位那 13 位（= 8192 个槽）。**纯函数**（宿主可测，见 `test_query_dedup_hash.py`）。
[[nodiscard]] inline std::size_t QueryDedupSlot(std::uintptr_t entity) noexcept {
    const std::uint64_t mixed = (entity >> 3) * 0x9E3779B97F4A7C15ULL;
    return static_cast<std::size_t>(mixed >> 51) & (kQueryDedupSlots - 1);
}

// 批次 428：方法分派热路径的"已校验入口"缓存槽（见下面 `InvokeEngineRow` 的 else 支）。
// 只存**成功**的解析结果；按"模块基址 + 行偏移 + 入口指纹"核对，基址一变自动重判。
isaac::runtime::EngineEntrySlot g_EngineRowEntrySlot{};

// 每个查询开始时"翻一代"。去重表是**文件级**的（不是栈上的：8192 个 u64 放进
// 栈会占 64 KiB），而 Lua 只在托管回调里单线程执行，所以"每个查询前翻一代"就够了 ——
// 漏掉这一次会让**第二次**调用把上一次的结果当成自己的，直接返回空表。
void ResetQueryDedup() noexcept {
    ++g_QueryEpoch;
    if (g_QueryEpoch == 0) {              // 回绕：整表作废，清零后从 1 重新开始
        for (std::size_t index = 0; index < kQueryDedupSlots; ++index) {
            g_QuerySeen[index] = 0;
            g_QuerySeenEpoch[index] = 0;
        }
        g_QueryEpoch = 1;
    }
    g_QuerySeenCount = 0;
}

bool QueryRecordUnique(std::uintptr_t entity) noexcept {
    // 0 是"空槽"哨兵 ⇒ 指针为 0 一律不当唯一（调用方在入表前已经判过非 0；
    // 这里再挡一道是**口径不变**：原实现也会把 0 记进去，但那属于上游已经排除的输入）。
    if (entity == 0 || g_QuerySeenCount >= kMaximumQueryResults) {
        return false;
    }
    std::size_t slot = QueryDedupSlot(entity);
    for (std::size_t probe = 0; probe < kQueryDedupSlots; ++probe) {
        if (g_QuerySeenEpoch[slot] != g_QueryEpoch) {   // 空槽（本代没被写过）
            g_QuerySeen[slot] = entity;
            g_QuerySeenEpoch[slot] = g_QueryEpoch;
            ++g_QuerySeenCount;
            return true;
        }
        if (g_QuerySeen[slot] == entity) {
            return false;                                // 本代已见过
        }
        slot = (slot + 1) & (kQueryDedupSlots - 1);
    }
    return false;                                        // 负载 ≤ 0.5，理论上到不了
}

// 查询的推出状态：结果表在栈上的下标 + 已经写进去的条数。
struct QuerySink {
    lua_State* state{nullptr};
    int resultIndex{0};
    int emitted{0};
};

// 查询结果该给哪种视图：**玩家给 `EntityPlayer`、掉落物给 `EntityPickup`、其余给 `Entity`**。
//
// 为什么掉落物也要分视图（2026-09-18 实测）：PC 的 `Isaac.FindByType(5)` 返回的是
// **真正的类对象**，所以模组在查询结果上调 `EntityPickup` 的方法（`CanReroll`、`IsShopItem`…）是正常的；
// 而我们此前一律给基类 `Entity` ⇒ 那些方法在查询结果上**全是 nil**（探针的 `R=` 打出 `ERR` 就是这么来的）。
// 视图回落已在 `IndexEntity` 里落实：`EntityPickup` 先查自己的字段，再回落到 `Entity` 的
// ⇒ 换成它**不会**丢掉基类字段/方法（与 PC 的继承关系一致）。
const char* EntityViewMetatableForPointer(std::uintptr_t entity) noexcept {
    switch (ClassifyCallbackEntity(entity)) {
        case CallbackEntityClass::Player: return kEntityPlayerMetatable;
        case CallbackEntityClass::Pickup: return kEntityPickupMetatable;
        case CallbackEntityClass::Laser:
            return IsTypedEntity(entity,kEntityLaserVtableOffset,kEntityTypeLaser)
                       ? kEntityLaserMetatable : kEntityMetatable;
        case CallbackEntityClass::Projectile:
            return IsTypedEntity(entity,kEntityProjectileVtableOffset,kEntityTypeProjectile)
                       ? kEntityProjectileMetatable : kEntityMetatable;
        case CallbackEntityClass::Knife:
            return IsTypedEntity(entity,kEntityKnifeVtableOffset,kEntityTypeKnife)
                       ? kEntityKnifeMetatable : kEntityMetatable;
        case CallbackEntityClass::Bomb:
            return IsTypedEntity(entity, kEntityBombVtableOffset, kEntityTypeBomb)
                       ? kEntityBombMetatable : kEntityMetatable;
        case CallbackEntityClass::Tear:
            return IsTypedEntity(entity, kEntityTearVtableOffset, kEntityTypeTear)
                       ? kEntityTearMetatable : kEntityMetatable;
        case CallbackEntityClass::Npc:
            return IsNpcFamilyEntity(entity) ? kEntityNPCMetatable : kEntityMetatable;
        default: return kEntityMetatable;
    }
}

void PushQueryResult(QuerySink* sink, std::uintptr_t entity) {
    if (sink == nullptr || sink->state == nullptr ||
        sink->emitted >= static_cast<int>(kMaximumQueryResults) || !QueryRecordUnique(entity)) {
        return;
    }
    // 视图按实体类别选（见上面的 `EntityViewMetatableForPointer`）：PC 的查询返回的就是真类对象。
    PushEntityHandle(sink->state, entity, EntityViewMetatableForPointer(entity));
    lua_rawseti(sink->state, sink->resultIndex, ++sink->emitted);
}

// 遍历一张 `Entity**` 表，只把"vptr 落在 Entity 区间"的非空元素交给 `visit`。
template <bool ValidatePointer = true, typename Visit>
void ForEachEntityInTable(std::uintptr_t list, const EntityTableSpec& spec, Visit&& visit) {
    EntityTableView view{};
    if (!ReadEntityTable(list, spec, &view)) {
        return;
    }
    for (std::uint32_t index = 0; index < view.count; ++index) {
        std::uintptr_t entity = 0;
        if (!ReadEngineUnchecked(view.begin + static_cast<std::size_t>(index) * sizeof(std::uintptr_t),
                                 &entity)) {
            return;
        }
        if (entity != 0 && (!ValidatePointer || IsEntityPointer(entity))) {
            visit(entity);
        }
    }
}

// `Game + 0x25C50` 的 `std::vector<Entity_Player*>`（与 `Isaac.GetPlayer` 同一对偏移）。
// `PLAYER` 分区走这里，不走 CellSpace —— 与引擎 `QueryRadius` 的分支一致。
template <bool ValidatePointer = true, typename Visit>
void ForEachPlayerEntity(std::uintptr_t game, Visit&& visit) {
    if (game == 0 || game > UINTPTR_MAX - kGamePlayerArrayEndOffset) {
        return;
    }
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!ReadEngine(game + kGamePlayerArrayBeginOffset, &begin) ||
        !ReadEngine(game + kGamePlayerArrayEndOffset, &end) || begin == 0 || end < begin) {
        return;
    }
    const std::size_t count = static_cast<std::size_t>((end - begin) / sizeof(std::uintptr_t));
    if (count == 0 || count > kEnginePlayerMaximumCount ||
        !IsEngineMemoryReadable(begin, count * sizeof(std::uintptr_t))) {
        return;
    }
    for (std::size_t index = 0; index < count; ++index) {
        std::uintptr_t entity = 0;
        if (!ReadEngineUnchecked(begin + index * sizeof(std::uintptr_t), &entity)) {
            return;
        }
        if (entity != 0 && (!ValidatePointer || IsEntityPointer(entity))) {
            visit(entity);
        }
    }
}

// 2026-10-10：PC GetData只随真实entity生存，不以room/列表/生成帧或128槽LRU失效。
// 数据由Lua-owned lifetime token持有，真实Remove清data、D2退役token。
// 旧实现逐字保留dist/entity-lifecycle-static-20261010/isaac_api.cpp.before。
int PushEntityDataTable(lua_State* state, std::uintptr_t entity) {
    return isaac::runtime::PushEntityLifetimeData(state, entity);
}
void ResetEntityDataStore() noexcept {
    isaac::runtime::ResetEntityLifetimeState();
}

// Entity 的整型字段（偏移来自 `Entity::Init` 的存值形态与真机探针）。
//
// `signed32` 为 true 的字段按**有符号**读：PC 的 `EntityPlayer.ControllerIndex` 文档是
// `-1 = 键盘/无手柄`，按无符号读会把它变成 4294967295。其余字段（`Type`/`Variant`/…）
// 在引擎里就是无符号枚举值，保持原样。
struct EntityIntegerField {
    const char* name;
    std::uintptr_t offset;
    bool signed32;
};

// 基类字段。`Index`（`+0x30`）批次 4 起在这里：`Room::AddEntity` 的
// `str w8,[x1,#0x30]`（存的就是 `Room+0x1948` 的房间实体表序号）是 `Entity.Index` 的硬证据。
// 注意它与 `kEntityPlayerIndexOffset`（`0x19F0`，"玩家在 `players` 向量里的下标"）**不是**
// 同一个量：后者不再作为任何 Lua 字段暴露（PC 里没有对应成员），常量保留供诊断使用。
constexpr EntityIntegerField kEntityIntegerFields[] = {
    {"Type", kEntityTypeOffset, false},
    {"Variant", kEntityVariantOffset, false},
    {"SubType", kEntitySubTypeOffset, false},
    {"Index", kEntityIndexOffset, false},
    // `InitSeed`：EID 把它当表键（`main.lua:206`/`264`），nil 会变成 `table index is nil`。
    {"InitSeed", kEntityInitSeedOffset, false},
    // `DropSeed`（2026-09-16）：EID 用它拼抓娃娃机的掉落判定键
    // （`main.lua:1173/1174` 的 `crane.InitSeed.."Drop"..crane.DropSeed`）。
    // 偏移是硬的（实体唯一的 RNG 成员、种子字，见 `kEntityDropSeedOffset` 的注释）；
    // **"Lua 名就叫 DropSeed"是推断**（PC 名字块里 DropSeed 紧挨 GetDropRNG，且 InitSeed 另有 0x3E8）。
    // 它只被当键用，取到的是"当前种子/状态字"（取过随机数会变），不会影响判定逻辑本身。
    {"DropSeed", kEntityDropSeedOffset, false},
    // `SpawnerType` / `SpawnerVariant`（批次 399，2026-10-07）：**生成这个实体的那个实体**的
    // `Type` / `Variant`（PC 契约 `tools/pc_contract_docs/Entity.md:829` / `:834`）。
    // 偏移 = `+0x44` / `+0x48`，两条独立入口互证（`query_npcs_spawnertype` 的过滤比较、
    // `Game::Spawn` 生成时从 spawner 抄下来）—— 证据链全文在 `runtime_constants.hpp` 批次 399 段。
    // 与 `SpawnerEntity`（`+0x3A8` 那个指针，走 `PushEntityField` 的裸指针分支）是**同族三个字段**。
    {"SpawnerType", kEntitySpawnerTypeOffset, false},
    {"SpawnerVariant", kEntitySpawnerVariantOffset, false},
};

// 只有 `Entity_Player` 有的整型字段。
//
// `ControllerIndex`（`0x19EC`，批次 3）：EID 在 `EID:setPlayer()`（`main.lua:1076`）里写
// `EID.controllerIndexes[p.ControllerIndex] = 1` —— nil 会直接触发 "table index is nil"。
// 偏移来源见 `runtime_constants.hpp`（`Entity_Player::SetControllerIndex` 的第一条存值指令）。
// 名字分派的**快速预筛**（批次 262，B2 性能）：先用前两个字节否掉绝大多数候选，再调 strcmp。
// 为什么：字段分派是一条**从长到短**的 strcmp 链 —— 实测一次 `player.Luck` 要 14 次、
// 一次 `player:GetSprite()`（字段全部落空、最后才落到方法表）要 27 次；而模组每帧要读几百上千次。
// 前两个字节比较把"否"的成本从一次函数调用降到两条字节比较（`&&` 短路；名字为空或单字符时
// 在第 0 个字节就否掉，不会越界读）。
// ★ 它**只做"否"**：命中的判定仍然完全由后面的 `strcmp` 决定 ⇒ 对外行为逐字不变；
//   `std::strcmp(field, "名字")` 这个文本形态也原样保留（`tools/mod_api_gap_report.py` 靠它认"已实现"）。
inline bool NamePrefix2Matches(const char* name, const char* literal) noexcept {
    return name[0] == literal[0] && name[1] == literal[1];
}

// 玩家专属的 **float** 字段表（2026-09-16）。用"名字 → 偏移"的静态表形态 —— 枚举工具
// （`tools/eid_api_gap_report.py`）靠这种形态认"已实现"，散装 strcmp 会让它继续报缺口。
struct EntityFloatField {
    const char* name;
    std::uintptr_t offset;
};
constexpr EntityFloatField kEntityPlayerFloatFields[] = {
    // 四个都是 `Entity_Player` 上的战斗属性，EID 只在"安慰奖"描述里用（见调用处注释）。
    {"Damage", kEntityPlayerDamageOffset},
    {"MoveSpeed", kEntityPlayerMoveSpeedOffset},
    {"MaxFireDelay", kEntityPlayerMaxFireDelayOffset},
    // ★ 批次 405（2026-10-07）：补 `ShotSpeed`(+0x1838) —— 它紧挨 `MaxFireDelay`(+0x1834) 的高
    //   4 字节，PC 契约 `EntityPlayer.md:2035` 把它列为 `float` 变量
    //   （"Player stat - Only change this in a callback to MC_EVALUATE_CACHE"）⇒ 与另外五格同族，
    //   读/写都要按 float。写分支在 `EntityNewIndex`，本表这一条补的是**读**路径。
    //   偏移证据见 `runtime_constants.hpp` 的 `kEntityPlayerShotSpeedOffset` 注释。
    {"ShotSpeed", kEntityPlayerShotSpeedOffset},
    {"TearRange", kEntityPlayerTearRangeOffset},
    {"TearHeight", kEntityPlayerTearHeightOffset},
    {"TearFallingSpeed", kEntityPlayerTearFallingSpeedOffset},
    {"TearFallingAcceleration", kEntityPlayerTearFallingAccelerationOffset},
    // `Luck`（2026-10-01 更正，批次 257）：`Entity_Player + 0x1950`，**float**。
    // ★ 它原来是一条独立的 `strcmp` 分支，而且偏移写的是 `0x1920`（int32）——**两处都错**：
    //   0x1920 是 `Entity_Player::DonateLuck`（`0x2F9978`）里那个被**整数**加的计数器，
    //   而暂停菜单显示的那个幸运是 `0x1950` 的 float（`PauseScreen::Show @ 0x432930` 读它喂给
    //   `PlayerUtils::GetLuckRating(float)`）。用户报的"EID 显示的幸运与游戏自带的不一致"就是它。
    //   证据链写在 `runtime_constants.hpp` 的 `kEntityPlayerLuckOffset` 注释里。
    // ★ 顺带并入本表（项目口径）：字段用"名字 → 偏移"的**静态表**形态 ——
    //   `tools/mod_api_gap_report.py` 的 `load_implemented_fields()` 靠这个形态认"已实现"，
    //   散装 `strcmp` 虽然也认，但表形态更不容易被后续改动遗漏。
    {"Luck", kEntityPlayerLuckOffset},
};

constexpr EntityIntegerField kEntityPlayerIntegerFields[] = {
    {"PlayerType", kEntityPlayerTypeOffset, false},
    {"ControllerIndex", kEntityPlayerControllerIndexOffset, true},
    // `ControlsCooldown`（2026-09-16）：EID 读它判断"还能不能操作"，也会**写**它来抑制按键
    // （`eid_bagofcrafting.lua:877`、`eid_holdmapdesc.lua:669` 都是 `= 2`）。
    // 写入口见本单元的 `EntityNewIndex`（挂在 `EntityPlayer` 元表的 `__newindex` 上）。
    {"ControlsCooldown", kEntityPlayerControlsCooldownOffset, true},
};

// 字段名 → Lua 值。返回 false 表示"不是这个对象的字段"，让调用方继续找方法。
//
// 字段**不占 catalog 行**（与 `Vector` 的 `X`/`Y` 同例）：它们是 `__index` 里的名字，
// 没有独立的 `lua_CFunction`，Catalog 的门禁要求"登记的条目必须真的被注册"。
bool PushEntityField(lua_State* state, std::uintptr_t entity, const char* field, bool playerView) {
    if (playerView && std::strcmp(field, "TearColor") == 0 && IsEntityPlayer(entity)) {
        EngineColorMod color{};
        if (!ReadEngine(entity + kEntityPlayerTearColorOffset, &color)) return false;
        PushLuaColorFromEngineColorMod(state, color);
        return true;
    }

    if (std::strcmp(field, "TearFlags") == 0) {
        std::uintptr_t offset = 0, vtable = 0;
        if (IsEntityPlayer(entity)) { offset = kEntityPlayerTearFlagsOffset; }
        else if (ReadEngine(entity, &vtable) && vtable == EngineModuleBase() + kEntityTearVtableOffset) { offset = kEntityTearFlagsOffset; }
        if (offset != 0) {
            BitSet128Value value{};
            if (!ReadEngine(entity + offset, &value)) { return false; }
            PushBitSet128(state, value);
            return true;
        }
    }

    for (const EntityIntegerField& candidate : kEntityIntegerFields) {
        if (!NamePrefix2Matches(field, candidate.name) || std::strcmp(field, candidate.name) != 0) {
            continue;
        }
        if (candidate.signed32) {
            std::int32_t value = 0;
            if (!ReadEngine(entity + candidate.offset, &value)) {
                return false;
            }
            lua_pushinteger(state, static_cast<lua_Integer>(value));
            return true;
        }
        std::uint32_t value = 0;
        if (!ReadEngine(entity + candidate.offset, &value)) {
            return false;
        }
        if (std::strcmp(candidate.name, "Type") == 0) {
            g_EntityTypeFieldReads.fetch_add(1, std::memory_order_relaxed);
            g_LastEntityTypeValue.store(value, std::memory_order_relaxed);
        } else if (std::strcmp(candidate.name, "Variant") == 0) {
            g_LastEntityVariantValue.store(value, std::memory_order_relaxed);
        } else if (std::strcmp(candidate.name, "SubType") == 0) {
            g_LastEntitySubTypeValue.store(value, std::memory_order_relaxed);
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    // `Player`（2026-09-16）：**只有跟班有**这个字段（PC 的 `EntityFamiliar.Player` = 主人）。
    // 判据与 `Entity:ToFamiliar()` 完全一致（`Type == ENTITY_FAMILIAR(3)` 且 vptr 精确等于
    // `base + kEntityFamiliarVtableOffset`）—— 不满足就返回 false，落到上层给 nil
    // （PC 里别的实体本来就没有这个成员，不能给它编一个）。
    // EID 的用法：`wisp:ToFamiliar().Player`（`eid_api.lua:3069`）。
    if (NamePrefix2Matches(field, "Player") && std::strcmp(field, "Player") == 0) {
        const std::uintptr_t base = EngineModuleBase();
        std::uintptr_t vtable = 0;
        std::uint32_t type = 0;
        if (base == 0 || base > UINTPTR_MAX - kEntityFamiliarVtableOffset ||
            !ReadEngine(entity, &vtable) || !ReadEngine(entity + kEntityTypeOffset, &type) ||
            type != kEntityTypeFamiliar || vtable != base + kEntityFamiliarVtableOffset) {
            return false;
        }
        std::uintptr_t owner = 0;
        if (!ReadEngine(entity + kEntityFamiliarPlayerOffset, &owner)) {
            return false;
        }
        if (owner == 0) {
            lua_pushnil(state);
            return true;
        }
        PushEntityHandle(state, owner,
                         IsEntityPlayer(owner) ? kEntityPlayerMetatable : kEntityMetatable);
        return true;
    }
    // `Parent`（2026-09-16）：指针字段，指向父实体（跟班的主段、多段实体的主段…）。
    // PC 里 `nil` 表示"没有父"，所以指针为 0 时必须给 nil —— 给一个"空实体句柄"会让
    // EID 的 `player.Parent == nil`（`main.lua:1089`）判错。
    if (NamePrefix2Matches(field, "Parent") && std::strcmp(field, "Parent") == 0) {
        std::uintptr_t parent = 0;
        if (!ReadEngine(entity + kEntityParentOffset, &parent)) {
            return false;
        }
        if (parent == 0) {
            lua_pushnil(state);
            return true;
        }
        // 句柄要按**它自己**的类型给元表（父实体可能是玩家、跟班或任意实体），
        // 否则 `parent.Luck` 这类玩家字段会在错的元表上查不到。
        PushEntityHandle(state, parent,
                         IsEntityPlayer(parent) ? kEntityPlayerMetatable : kEntityMetatable);
        return true;
    }
    // `SpawnerEntity`（批次 399，2026-10-07）：**生成这个实体的那个实体**，偏移 `+0x3A8`，
    // 一个裸 `Entity*`（不是 `EntityRef`）。PC 契约 `tools/pc_contract_docs/Entity.md:824`
    // 带 `data-altreturn='nil'` ⇒ **指针为 0 时必须给 `nil`**（给空壳句柄会让模组判错"没有生成者"）。
    // 与 `Parent` 同形（同样的裸指针 + 同样的按自身类型给元表）。
    // ★ 为什么必须有它：语料 `Trinity/main.lua:129` 的 `tear.SpawnerEntity:ToPlayer()`
    //   在缺这一格时拿到 `nil` ⇒ 链式取值抛错 ⇒ 整条 `MC_POST_FIRE_TEAR` 回调被摘（真机实测）。
    // 证据见 `runtime_constants.hpp` 批次 268/399 段。
    if (NamePrefix2Matches(field, "SpawnerEntity") && std::strcmp(field, "SpawnerEntity") == 0) {
        std::uintptr_t spawner = 0;
        if (!ReadEngine(entity + kEntitySpawnerEntityOffset, &spawner)) {
            return false;
        }
        if (spawner == 0) {
            lua_pushnil(state);
            return true;
        }
        PushEntityHandle(state, spawner,
                         IsEntityPlayer(spawner) ? kEntityPlayerMetatable : kEntityMetatable);
        return true;
    }
    // `PositionOffset`（2026-09-16）：`Vector2`（两个 float）。EID 用它修正实体在屏幕上的位置
    // （`main.lua:924`）。读不到就返回 false ⇒ 上层给 nil（不编一个 0 向量）。
    if (NamePrefix2Matches(field, "PositionOffset") && std::strcmp(field, "PositionOffset") == 0) {
        // PC4121B0返回只读活引用，412190允许整体赋值；复用已有寿命/token视图。
        isaac::runtime::PushEntityVectorReference(state,entity,kEntityPositionOffsetOffset);
        return true;
    }
    if (playerView) {
        // ★ `player.Luck` 现在**走下面的 `kEntityPlayerFloatFields` 表**（2026-10-01，批次 257）。
        //   原来这里是一条独立分支、按 `int32` 读 `+0x1920` ⇒ 与游戏属性页显示的幸运对不上。
        //   真相：`+0x1920` 是 `DonateLuck` 的整数计数器，真正的 `Luck` 是 `+0x1950` 的 **float**。
        //   完整证据链见 `runtime_constants.hpp` 的 `kEntityPlayerLuckOffset` 注释。
        //   （"为什么必须实现"也记在那里：EID 在**逐帧渲染路径**上算 `EID.LuckFormulas[...](player.Luck)`，
        //    字段缺失 ⇒ Lua 拿到 `nil` ⇒ 算术抛错 ⇒ 那条渲染回调当场中断 ⇒ 该帧那片道具的描述全不画。）
        // 本表里的字段**全是 float**（偏移与证据见 `runtime_constants.hpp` 各常量注释）。
        // 其中四个战斗属性（2026-09-16）EID 只用它们做"安慰奖（Consolation Prize 644）"
        // 描述里的档位换算（`features/eid_modifiers.lua:461-464`），缺一个就是 `nil^0.56` 那种算术抛错。
        for (const EntityFloatField& candidate : kEntityPlayerFloatFields) {
            if (!NamePrefix2Matches(field, candidate.name) || std::strcmp(field, candidate.name) != 0) {
                continue;
            }
            float value = 0.0F;
            if (!ReadEngine(entity + candidate.offset, &value)) {
                return false;
            }
            lua_pushnumber(state, static_cast<lua_Number>(value));
            return true;
        }
        // `CanFly`（1 字节布尔，2026-09-16）：EID 用它决定要不要禁用"障碍物提示"（`main.lua:1193`）。
        if (NamePrefix2Matches(field, "CanFly") && std::strcmp(field, "CanFly") == 0) {
            std::uint8_t value = 0;
            if (!ReadEngine(entity + kEntityPlayerCanFlyOffset, &value)) {
                return false;
            }
            lua_pushboolean(state, value != 0 ? 1 : 0);
            return true;
        }
        // `ControlsEnabled`（1 字节布尔，批次 212）：PC 上"玩家能不能操作"的开关，MCM 打开菜单时
        // 会把它写成 false（`modconfig.lua:1632`，与 `player.Velocity = vecZero` 一起冻住玩家）。
        // **偏移锚点 = 引擎自己的 `PlayerManager::SetControlsEnabled @ 0x4422C0`**（见常量处的注释）。
        // 读与写都要有：只写不读的话，模组"写完再读回来"就会拿到 nil/旧值，行为与 PC 不一致。
        if (NamePrefix2Matches(field, "ControlsEnabled") && std::strcmp(field, "ControlsEnabled") == 0) {
            std::uint8_t value = 0;
            if (!ReadEngine(entity + kEntityPlayerControlsEnabledOffset, &value)) {
                return false;
            }
            lua_pushboolean(state, value != 0 ? 1 : 0);
            return true;
        }
        for (const EntityIntegerField& candidate : kEntityPlayerIntegerFields) {
            if (!NamePrefix2Matches(field, candidate.name) || std::strcmp(field, candidate.name) != 0) {
                continue;
            }
            if (candidate.signed32) {
                std::int32_t value = 0;
                if (!ReadEngine(entity + candidate.offset, &value)) {
                    return false;
                }
                lua_pushinteger(state, static_cast<lua_Integer>(value));
                return true;
            }
            std::uint32_t value = 0;
            if (!ReadEngine(entity + candidate.offset, &value)) {
                return false;
            }
            lua_pushinteger(state, static_cast<lua_Integer>(value));
            return true;
        }
        // `player.QueuedItem`（批次 6，2026-09-12；**批次 195 起是真读数**）：
        // EID 在**逐帧**路径上读它 14 次（`features/eid_api.lua:2625/2627/2631/...`、`main.lua` 多处）：
        //   `if player.QueuedItem then ... player.QueuedItem.Item ... end`、
        //   `not player.QueuedItem.Touched`（`:2638`）、`player.QueuedItem.Charge`。
        //
        // PC 语义（契约页 `tools/pc_contract_docs/EntityPlayer.md:2012`，正文 `:2016-2019`）：
        //   * `QueuedItem` **永远不是 nil**（没举着东西时也是一张表）；
        //   * `player.QueuedItem.Item` 在没举着东西时是 **nil**；
        //   * 只对收藏品与饰品有数据。字段按 `QueueItemData.md` 是
        //     `Item`（ItemConfig_Item）/`Charge`（int）/`Touched`（boolean）。
        //
        // ★ 旧实现返回**一张空表**：`Charge`/`Touched` 都是 nil ⇒ 模组写
        //   `player.QueuedItem.Charge > 0` 时抛 `attempt to compare nil with number`
        //   （派发器把整条回调摘掉）、写 `== false` 时恒不成立且不报错 —— 两种都是静默失效。
        //   现在按 `QueueItemData`（**内嵌**在 `Entity_Player + 0x1C38`，步长 0x18）真读：
        //   写/读/清三个独立函数给出同一组偏移，逐条见 `runtime_constants.hpp` 的
        //   `kEntityPlayerQueuedItemOffset`。
        if (NamePrefix2Matches(field, "QueuedItem") && std::strcmp(field, "QueuedItem") == 0) {
            return PushQueuedItemTable(state, entity);
        }
    }
    if (std::strcmp(field, "Friction") == 0) {
        float value = 0.0f;
        if (!ReadEngine(entity + kEntityFrictionOffset, &value)) return false;
        lua_pushnumber(state, value);
        return true;
    }
    if (std::strcmp(field, "Visible") == 0) {
        std::uint8_t value = 0;
        if (!ReadEngine(entity + kEntityVisibleOffset, &value)) return false;
        lua_pushboolean(state, value != 0);
        return true;
    }
    if (NamePrefix2Matches(field, "Size") && std::strcmp(field, "Size") == 0) {
        float radius = 0.0F;
        if (!ReadEngine(entity + kEntitySizeOffset, &radius)) {
            return false;
        }
        lua_pushnumber(state, static_cast<lua_Number>(radius));
        return true;
    }
    if (NamePrefix2Matches(field, "FrameCount") && std::strcmp(field, "FrameCount") == 0) {
        // `Entity::GetFrameCount()`（`0x5A210`）= `[Game + 0x24F99C] - [this + 0x2F4]`，
        // 两个 u32 相减（故意保留无符号回绕，与引擎逐位一致）。
        std::uint32_t now = 0;
        std::uint32_t spawn = 0;
        const std::uintptr_t game = ResolveGameAddress();
        // 探针（2026-09-12 第八轮）：EID 的 `main.lua:1473` 判 `entity.FrameCount > 0`，
        // 而过滤器链掩码显示它**从不**走到后面的 `EID:getEntityData` —— 只有 `FrameCount`
        // 恒 0 才会这样。这里把三个原始读数记下来（引擎帧计数 / 实体出生帧 / 差值），
        // 是"偏移不对"还是"Game 指针不对"就能一眼分开。
        g_FrameCountProbeReads.fetch_add(1, std::memory_order_relaxed);
        g_LastGameFrameCount.store(now, std::memory_order_relaxed);
        g_LastEntitySpawnFrame.store(spawn, std::memory_order_relaxed);
        if (game == 0 || !ReadEngine(game + kGameFrameCountOffset, &now) ||
            !ReadEngine(entity + kEntitySpawnFrameOffset, &spawn)) {
            // **恒返回数字**：EID 直接拿它做比较（`main.lua:1473` 的 `entity.FrameCount > 0`），
            // nil 会变成 "attempt to compare nil with number" 而打断整段渲染。
            PushZero(state);
            return true;
        }
        g_LastGameFrameCount.store(now, std::memory_order_relaxed);
        g_LastEntitySpawnFrame.store(spawn, std::memory_order_relaxed);
        g_LastFrameCountResult.store(now - spawn, std::memory_order_relaxed);
        if (now > spawn) {
            g_FrameCountPositive.fetch_add(1, std::memory_order_relaxed);
        }
        lua_pushinteger(state, static_cast<lua_Integer>(now - spawn));
        return true;
    }
    // `HitPoints` / `MaxHitPoints`（批次 245，2026-10-01）：`Entity` **基类**的两个 **float**
    // 字段（PC 契约 `Entity.md:750/774` 逐字写着 `float`）。
    // 取证与"为什么必须从 `AddHealth`/`HasMortalDamage` 入手、而不是 `TakeDamage`"：
    // 见 `runtime_constants.hpp` 的 `kEntityHitPointsOffset` 注释。
    // 它们是**基类**字段 ⇒ 对任何实体都读得出，不需要判类型（与 `Player`/`Scale` 那些不同）。
    if ((NamePrefix2Matches(field, "HitPoints") && std::strcmp(field, "HitPoints") == 0) || (NamePrefix2Matches(field, "MaxHitPoints") && std::strcmp(field, "MaxHitPoints") == 0)) {
        const std::uintptr_t offset = field[0] == 'H' ? kEntityHitPointsOffset
                                                      : kEntityMaxHitPointsOffset;
        float value = 0.0f;
        if (!ReadEngine(entity + offset, &value)) {
            return false;
        }
        lua_pushnumber(state, static_cast<lua_Number>(value));
        return true;
    }
    // `Scale`（批次 246，2026-10-01）：`EntityNPC.Scale`（**float**，契约 `EntityNPC.md:223/225`）。
    // ★ 它**只挂在 `EntityNPC` 页上**（不是 `Entity` 页）⇒ 先过 `IsNpcFamilyEntity`；
    //   掉落物/眼泪/激光那些实体上 PC 也没有这个字段 ⇒ 返回 false，上层给 nil。
    // 取证见 `runtime_constants.hpp` 的 `kEntityNpcScaleOffset`。
    if (NamePrefix2Matches(field, "Scale") && std::strcmp(field, "Scale") == 0) {
        if (!IsNpcFamilyEntity(entity)) {
            return false;
        }
        float value = 0.0f;
        if (!ReadEngine(entity + kEntityNpcScaleOffset, &value)) {
            return false;
        }
        lua_pushnumber(state, static_cast<lua_Number>(value));
        return true;
    }
    if ((NamePrefix2Matches(field, "Position") && std::strcmp(field, "Position") == 0) || (NamePrefix2Matches(field, "Velocity") && std::strcmp(field, "Velocity") == 0)) {
        // 批次 212：`Velocity` 也走这条（PC 侧同是 `Vector`）。为什么必须**读**也支持：
        // 模组会"写完再读回来"（MCM 就是 `player.Velocity = vecZero`；别的模组做
        // `v = player.Velocity; v.X = v.X * 0.5; player.Velocity = v`）——
        // 只有写没有读的话，那一步拿到 nil、`nil.X` 直接抛错 ⇒ 又是"整条回调被掐死"。
        const std::uintptr_t offset =
            field[0] == 'V' ? kEntityVelocityOffset : kEntityPositionOffset;
        float x = 0.0F;
        float y = 0.0F;
        if (!ReadEngine(entity + offset, &x) ||
            !ReadEngine(entity + offset + sizeof(float), &y)) {
            return false;
        }
        // 返回**新的** `Vector` userdata：把同一块 userdata 交出去（别名）会让 Mod 的
        // `player.Position.X = 1` 之类写法改到别人的值上；`Isaac.WorldToScreen` 同理。
        auto* vector = static_cast<VectorHandle*>(lua_newuserdata(state, sizeof(VectorHandle)));
        vector->x = x;
        vector->y = y;
        luaL_getmetatable(state, kVectorMetatable);
        lua_setmetatable(state, -2);
        return true;
    }
    return false;
}

// `player.QueuedItem` —— PC 的 `QueueItemData` 表（批次 195，2026-09-29 起是真读数）。
//
// 形状照 PC 契约（`tools/pc_contract_docs/EntityPlayer.md:2012` + `:2016-2019` 的正文，
// 字段清单见 `analysis/isaacdocs-snapshot/docs/QueueItemData.md`）：
//   * **永远返回一张表**（没举着东西时也是表，只是 `.Item == nil`）；
//   * `Charge` = int32（**恒给整数**，没举东西时是 0）；
//   * `Touched` = 布尔（`+0x0C` 那个字节非 0）；
//   * `Item` = `ItemConfig_Item` 句柄，指针为 0 **或**在 `ItemConfig` 的向量里找不到那一格时给 nil
//     （换局后向量会重排 ⇒ 找不到就安全降级，不报错）。
//
// 为什么必须给 `Charge`/`Touched` 真值（而不是继续给空表）：模组写的是
// `player.QueuedItem.Charge > 0`（EID `features/eid_api.lua:2631` 一带）与
// `not player.QueuedItem.Touched`（`:2638`）—— 空表下前者抛
// `attempt to compare nil with number`（**派发器把整条回调摘掉**），后者恒不成立且不报错。
//
// `VarData`（`+0x10`）引擎里有、PC 文档里**没有** ⇒ 不对外暴露（常量仍登记在
// `runtime_constants.hpp`，便于将来与 PC 的 `QueueItemData` 变动对照）。
// 复用真实ItemConfig向量校验；临时效果与QueuedItem均不能发布未经校验的条目指针。
bool PushValidatedItemConfigItem(lua_State* state, std::uintptr_t item) {
    if (item != 0 && item <= UINTPTR_MAX - kItemConfigItemTypeOffset) {
        std::uint32_t type = 0;
        if (ReadEngine(item + kItemConfigItemTypeOffset, &type)) {
            std::uintptr_t beginOffset = kItemConfigCollectibleBeginOffset;
            std::uintptr_t endOffset = kItemConfigCollectibleEndOffset;
            if (type == kItemTypeNull) {
                beginOffset = kItemConfigNullItemBeginOffset;
                endOffset = kItemConfigNullItemEndOffset;
            } else if (type == kItemTypeTrinket) {
                beginOffset = kItemConfigTrinketBeginOffset;
                endOffset = kItemConfigTrinketEndOffset;
            }
            const std::uintptr_t config = ResolveItemConfig(nullptr);
            ItemVectorView view{};
            // `ReadItemVector` 自己已经查过"长度是 8 的倍数、非空、有上限"，这里不重复判。
            if (config != 0 && ReadItemVector(config, beginOffset, endOffset, &view)) {
                for (std::size_t index = 0; index < view.count; ++index) {
                    std::uintptr_t candidate = 0;
                    if (!ReadEngine(view.begin + index * sizeof(std::uintptr_t), &candidate) ||
                        candidate != item) {
                        continue;
                    }
                    PushItemConfigItemHandle(state, item, beginOffset, view.begin, index);
                    return true;
                }
            }
        }
    }
    lua_pushnil(state);
    return false;
}

bool PushQueuedItemTable(lua_State* state, std::uintptr_t player) {
    if (player > UINTPTR_MAX - kEntityPlayerQueuedItemOffset) {
        return false;
    }
    std::uintptr_t item = 0;
    std::int32_t charge = 0;
    std::uint8_t touched = 0;
    const std::uintptr_t base = player + kEntityPlayerQueuedItemOffset;
    if (!ReadEngine(base + kQueuedItemDataItemOffset, &item) ||
        !ReadEngine(base + kQueuedItemDataChargeOffset, &charge) ||
        !ReadEngine(base + kQueuedItemDataTouchedOffset, &touched)) {
        return false;  // 读不到 ⇒ 让调用方按"不是这个字段"处理（上层给 nil）
    }
    lua_newtable(state);
    lua_pushinteger(state, static_cast<lua_Integer>(charge));
    lua_setfield(state, -2, "Charge");
    lua_pushboolean(state, touched != 0 ? 1 : 0);
    lua_setfield(state, -2, "Touched");
    static_cast<void>(PushValidatedItemConfigItem(state, item));
    lua_setfield(state, -2, "Item");
    return true;
}

// `EntityPickup` 的字段（偏移出处见 `runtime_constants.hpp` 的"批次 4"段）。
//
// 每次访问都**重做**"这真是一张 `Entity_Pickup`"的校验（`Type == 5` **且** vptr ==
// `base + 0xA36E28`）：`Entity_Pickup` 的 vtable 是唯一的，这两条同时成立才读它的字段。
//
// ★ `Touched`（`+0x560`）是**猜测**：`docs/问题与解决记录.md` 的"语义未定项"里明确写着
// "`Entity_Pickup+0x560` 是否为 `Touched` 待真机确认"。PC 的返回类型是 boolean，所以这里按
// u8 != 0 转成布尔；它是本批次唯一一条"没有铁证"的字段。
bool PushEntityPickupField(lua_State* state, std::uintptr_t entity, const char* field) {
    const std::uintptr_t base = EngineModuleBase();
    if (entity == 0 || base == 0 || base > UINTPTR_MAX - kEntityPickupVtableOffset) {
        return false;
    }
    std::uintptr_t vtable = 0;
    std::uint32_t type = 0;
    if (!ReadEngine(entity, &vtable) || !ReadEngine(entity + kEntityTypeOffset, &type) ||
        type != kEntityTypePickup || vtable != base + kEntityPickupVtableOffset) {
        return false;
    }
    if (std::strcmp(field, "Price") == 0 || std::strcmp(field, "ShopItemId") == 0 ||
        std::strcmp(field, "OptionsPickupIndex") == 0) {
        const std::uintptr_t offset = std::strcmp(field, "Price") == 0
                                          ? kEntityPickupPriceOffset
                                          : (std::strcmp(field, "ShopItemId") == 0
                                                 ? kEntityPickupShopItemIdOffset
                                                 : kEntityPickupOptionsIndexOffset);
        // 三个字段在引擎里都是 `int`；`ShopItemId` 的文档明确提到会用**负数**（-1）修 D6 重投，
        // 所以按有符号读。
        std::int32_t value = 0;
        if (!ReadEngine(entity + offset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    if (std::strcmp(field, "ForceBlind") == 0 || std::strcmp(field, "Touched") == 0) {
        const std::uintptr_t offset = std::strcmp(field, "ForceBlind") == 0
                                          ? kEntityPickupForceBlindOffset
                                          : kEntityPickupTouchedOffset;
        std::uint8_t value = 0;
        if (!ReadEngine(entity + offset, &value)) {
            return false;
        }
        // 探针：`Touched` 是"待真机确认"的偏移，而 EID 拿它当"摘掉隐瞒"的条件。
        // `ForceBlind` 不记（它不是本轮的问题点），只记 `Touched`。
        if (std::strcmp(field, "Touched") == 0) {
            g_EntityPickupTouchedReads.fetch_add(1, std::memory_order_relaxed);
            if (value != 0) {
                g_EntityPickupTouchedTrue.fetch_add(1, std::memory_order_relaxed);
            }
            g_LastEntityPickupTouchedRaw.store(value, std::memory_order_relaxed);
        }
        lua_pushboolean(state, value != 0 ? 1 : 0);
        return true;
    }
    return false;
}

// `PathFinder` 句柄（批次 344，2026-10-04）：把"内嵌的 `NPCAI_Pathfinder` 子对象地址"
// 包成一个 `IsaacRuntime.PathFinder` userdata。形状照抄 `PushEntityHandle` 的最简版：
// 空指针 ⇒ 压 `nil`（"拿不到对象就给 nil"，PC 的"不可用引用"口径），否则 `lua_newuserdata`
// + 设元表。**不做任何校验** —— 身份判据全在"用什么句柄"这一层（句柄类型 + 地址非 0）。
void PushPathFinderHandle(lua_State* state, std::uintptr_t pathfinder,std::uintptr_t owner) {
    if (pathfinder == 0) {
        lua_pushnil(state);
        return;
    }
    auto*token=PushEntityLifetimeToken(state,owner);const int tokenIndex=lua_gettop(state);
    auto* handle = static_cast<PathFinderHandle*>(lua_newuserdata(state, sizeof(PathFinderHandle)));
    handle->owner=engine_memory::AsObject(owner);handle->lifetime=token;
    lua_pushvalue(state,tokenIndex);lua_setuservalue(state,-2);
    handle->pathfinder = engine_memory::AsObject(pathfinder);
    luaL_getmetatable(state, kPathFinderMetatable);
    lua_setmetatable(state, -2);
    lua_remove(state,tokenIndex);
}

// `EntityNPC` 自己的字段（批次 344，2026-10-04）：目前**只有 `Pathfinder`** 一个键。
//
// ★ PC 的 `EntityNPC` 页（`tools/pc_contract_docs/EntityNPC.md:208-210`）里 PathFinder 相关的
//   成员就只有 `Pathfinder` 这一个属性 ⇒ **只答这一个键**，其余一律返回 `false` 让调用方
//   回落到共享的 `PushEntityField`（`npc.HitPoints` / `npc.Scale` 之类照旧能用）。
// ★ 失效句柄（`entity == 0`）时给 `nil`、并返回 `true`（"这个键存在、现在是空的"）—— 与
//   PC 的"空对象"口径一致，也不会让调用方再去 `Entity` 那边找一遍。
// ★ 这里**不重复做** NPC 身份校验：调用方 `IndexEntity` 已经在 `EntityView::Npc` 分支里
//   通过了 `ValidatedEntity(handle)`（vtable 区间校验）才走到这里。
bool PushEntityNpcField(lua_State* state, std::uintptr_t entity, const char* field) {
    if (std::strcmp(field, "Pathfinder") != 0) {
        return false;
    }
    if (entity == 0) {
        lua_pushnil(state);
        return true;
    }
    PushPathFinderHandle(state, entity + kEntityNpcPathfinderOffset,entity);
    return true;
}

// 方法表查找：先本类型的 `__methods`，`EntityPlayer` 再回落到 `Entity` 的（PC 里就是继承）。
bool PushMethodFrom(lua_State* state, const char* metatable, const char* field) {
    if (luaL_getmetatable(state, metatable) != LUA_TTABLE) {
        lua_pop(state, 1);
        return false;
    }
    lua_getfield(state, -1, "__methods");
    lua_remove(state, -2);
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        return false;
    }
    lua_getfield(state, -1, field);
    lua_remove(state, -2);
    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        return false;
    }
    return true;
}

// 视图身份：决定用哪套字段与方法表（`EntityPlayer`/`EntityPickup`/`EntityProjectile` 都回落到
// `Entity` 的方法表，与 PC 的继承关系一致），以及用哪一级句柄校验。
enum class EntityView : std::uint8_t { Base, Player, Pickup, Projectile, Tear, Laser, Npc, Familiar, Bomb, Knife };

const char* EntityViewMetatable(EntityView view) noexcept {
    if(view==EntityView::Knife)return kEntityKnifeMetatable;
    if (view == EntityView::Bomb) {
        return kEntityBombMetatable;
    }
    if (view == EntityView::Player) {
        return kEntityPlayerMetatable;
    }
    if (view == EntityView::Pickup) {
        return kEntityPickupMetatable;
    }
    if (view == EntityView::Projectile) {
        return kEntityProjectileMetatable;
    }
    //: 批次 281/282：`EntityTear` / `EntityLaser`。它们的**字段**没有自己的分派（走 `else` 分支
    //: 落到 `Entity` 的字段表），但**方法**挂在自己的元表上（`IndexEntity` 先查本视图元表、再回落）。
    if (view == EntityView::Tear) {
        return kEntityTearMetatable;
    }
    if (view == EntityView::Laser) {
        return kEntityLaserMetatable;
    }
    //: 批次 285：`EntityNPC`（`Entity:ToNPC()` 的返回值）—— 它自己的方法（`Morph`）挂在这张
    //: 元表上，字段仍回落到 `Entity`（与 `EntityTear`/`EntityLaser` 同一形态）。
    if (view == EntityView::Npc) {
        return kEntityNPCMetatable;
    }
    //: 批次 330：`EntityFamiliar`（`Entity:ToFamiliar()` 的返回值）—— 同一形态：自己的方法
    //: （`FollowParent`/`AddToFollowers`）挂在自己的元表上，字段回落到 `Entity`。
    return view == EntityView::Familiar ? kEntityFamiliarMetatable : kEntityMetatable;
}

bool IsFamiliarOrbitField(const char* field) noexcept {
    return field[0]=='O' && (std::strcmp(field,"OrbitDistance")==0 ||
        std::strcmp(field,"OrbitSpeed")==0 || std::strcmp(field,"OrbitLayer")==0);
}
int PushFamiliarOrbitField(lua_State* state,const EntityHandle* handle,const char* field) {
    const auto familiar = ValidatedEntityFamiliar(handle);
    if (familiar==0) return luaL_error(state,"EntityFamiliar.%s receiver is no longer available",field);
    if (std::strcmp(field,"OrbitDistance")==0) {
        std::array<float,2> value{};
        if (!ReadEngine(familiar+kEntityFamiliarOrbitDistanceOffset,&value))
            return luaL_error(state,"EntityFamiliar.OrbitDistance is not readable");
        // PC859E50 alloc userdata+8并复制字段两word：每次返回独立值，不借用实体内存。
        isaac::runtime::PushLuaVector(state,value[0],value[1]);
    } else if (std::strcmp(field,"OrbitSpeed")==0) {
        float value{};
        if (!ReadEngine(familiar+kEntityFamiliarOrbitSpeedOffset,&value))
            return luaL_error(state,"EntityFamiliar.OrbitSpeed is not readable");
        lua_pushnumber(state,value);
    } else {
        std::int32_t value{};
        if (!ReadEngine(familiar+kEntityFamiliarOrbitLayerOffset,&value))
            return luaL_error(state,"EntityFamiliar.OrbitLayer is not readable");
        lua_pushinteger(state,value);
    }
    return 1;
}
int IndexEntity(lua_State* state, EntityView view) {
    const char* metatable = EntityViewMetatable(view);
    // 模组包装基类 __index 后会把子类对象传回这里；基类接受全部实体视图，
    // 子类入口仍要求自身元表，后面的 token 与原生指针校验保持不变。
    auto* handle = view == EntityView::Base
                       ? CheckEntityHandle(state, 1)
                       : static_cast<EntityHandle*>(luaL_checkudata(state, 1, metatable));
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    const char* field = lua_tostring(state, 2);
    if (view == EntityView::Bomb && std::strcmp(field, "IsFetus") == 0) {
        const auto bomb = ValidatedTypedEntity(handle, kEntityBombVtableOffset, kEntityTypeBomb);
        std::uint8_t value = 0;
        if (bomb == 0 || !ReadEngine(bomb + kEntityBombIsFetusOffset, &value)) {
            return luaL_error(state, "EntityBomb.IsFetus receiver is no longer available");
        }
        lua_pushboolean(state, value != 0);
        return 1;
    }
    if (view == EntityView::Tear && std::strcmp(field, "Scale") == 0) {
        const auto tear = ValidatedTypedEntity(handle, kEntityTearVtableOffset, kEntityTypeTear);
        float value = 0;
        if (tear == 0 || !ReadEngine(tear + kEntityTearScaleOffset, &value)) {
            return luaL_error(state, "EntityTear.Scale receiver is no longer available");
        }
        lua_pushnumber(state, value);
        return 1;
    }
    if (IsFamiliarOrbitField(field)) return PushFamiliarOrbitField(state,handle,field);
    // 校验失败（伪造/过期句柄）时字段与方法都不给：返回 nil 比报错更接近 PC 的"空对象"，
    // 也不会让一个已经失效的引用把 Mod 直接打断。
    //
    // `EntityPlayer` 视图要求**精确**的 `Entity_Player` vptr（玩家专属字段/方法都在它上面），
    // `Entity`/`EntityPickup` 用 `Entity` 家族的 vtable 区间。
    const std::uintptr_t entity =
        view == EntityView::Player ? ValidatedEntityPlayer(handle) : ValidatedEntity(handle);
    // 这些键只属于方法表；仍实时查本类/基类，不能缓存第三方可覆写的方法。
    const bool methodOnly =
        (field[0] == 'G' && (std::strcmp(field, "GetData") == 0 ||
                              std::strcmp(field, "GetEffects") == 0 ||
                              std::strcmp(field, "GetSprite") == 0)) ||
        (field[0] == 'T' && std::strcmp(field, "ToPlayer") == 0) ||
        (field[0] == 'H' && (std::strcmp(field, "HasCollectible") == 0 ||
                              std::strcmp(field, "HasTrinket") == 0)) ||
        (field[0] == 'I' && std::strcmp(field, "IsDead") == 0);
    if (entity != 0 && !methodOnly) {
        // 三个身份字段无子类覆盖；复用原读取和计数，省去扩展字段的逐组探测。
        if (((field[0] == 'T' && std::strcmp(field, "Type") == 0) ||
             (field[0] == 'V' && std::strcmp(field, "Variant") == 0) ||
             (field[0] == 'S' && std::strcmp(field, "SubType") == 0)) &&
            PushEntityField(state, entity, field, view == EntityView::Player)) return 1;
        if(const int pushed=TryPushApi400EffectMethod(state,entity,field))return pushed;
        if(const int pushed=TryPushApi400EntityField(state,entity,field))return pushed;
        if(const int pushed=TryPushRPlusEntityField(state,entity,field))return pushed;
        if(const int pushed=TryPushExtendedEntityField(state,entity,field))return pushed;
        if(const int pushed=TryPushApi500EntityField(state,entity,field))return pushed;
        if(const int pushed=TryPushApi600EntityField(state,entity,field))return pushed;
        if(const int n=TryPushApi600ExtraEntityField(state,entity,field))return n;
        if(const int pushed=TryPushApi600PlayerField(state,entity,field))return pushed;
        bool pushed = false;
        if (view == EntityView::Pickup) {
            // `EntityPickup` 自己的字段优先，其次回落到 `Entity` 的（PC 里它就是 `Entity` 的子类）。
            pushed = PushEntityPickupField(state, entity, field) ||
                     PushEntityField(state, entity, field, false);
        } else if (view == EntityView::Projectile) {
            // 同上：`EntityProjectile` 自己的字段（目前只有 `ProjectileFlags`）优先，
            // 其次回落到 `Entity` 的。
            pushed = PushEntityProjectileField(state, entity, field) ||
                     PushEntityField(state, entity, field, false);
        } else if (view == EntityView::Npc) {
            // 批次 344（2026-10-04）：`EntityNPC` 自己的字段优先（目前只有 `Pathfinder`
            // 一个键 —— PC 的 `EntityNPC` 页里 PathFinder 相关成员就这一个），
            // 其余回落到共享的 `Entity` 字段函数（`HitPoints`/`Scale`/`Position` 照旧）。
            // ★ 与 `Pickup`/`Projectile` 那两个分支**逐字同形**。
            pushed = PushEntityNpcField(state, entity, field) ||
                     PushEntityField(state, entity, field, false);
        } else {
            pushed = PushEntityField(state, entity, field, view == EntityView::Player);
        }
        if (pushed) {
            return 1;
        }
    }
    g_EntityStringFieldReads.fetch_add(1, std::memory_order_relaxed);
    {
        std::uint64_t head = 0;
        for (std::size_t index = 0; index < 8 && field[index] != '\0'; ++index) {
            head |= static_cast<std::uint64_t>(static_cast<unsigned char>(field[index]))
                    << (8 * index);
        }
        g_LastEntityStringFieldHead.store(head, std::memory_order_relaxed);
    }
    if (PushMethodFrom(state, metatable, field)) {
        return 1;
    }
    if (view != EntityView::Base) {
        luaL_getmetatable(state,kEntityMetatable);lua_getfield(state,-1,"__index");
        if(lua_tocfunction(state,-1)!=EntityIndex) {
            lua_pushvalue(state,1);lua_pushvalue(state,2);lua_call(state,2,1);
            lua_remove(state,-2);return 1;
        }
        lua_pop(state,2);
        if(PushMethodFrom(state,kEntityMetatable,field))return 1;
    }
    lua_pushnil(state);
    return 1;
}

int EntityIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Base);
}

int EntityKnifeIndex(lua_State* state) {return IndexEntity(state,EntityView::Knife);}

int EntityBombIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Bomb);
}

int EntityPlayerIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Player);
}

int EntityPickupIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Pickup);
}

//: 批次 281：`EntityTear` 视图的 `__index`。
int EntityTearIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Tear);
}

//: 批次 282：`EntityLaser` 视图的 `__index`。
int EntityLaserIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Laser);
}

//: 批次 285：`EntityNPC` 视图的 `__index`（`Entity:ToNPC()` 的返回值）。
//: 与 `EntityTear`/`EntityLaser` 同一形态 —— 字段回落到 `Entity` 的（`IndexEntity` 的 else
//: 分支；`Scale` 那条由 `IsNpcFamilyEntity` 把关），方法先查本视图元表、再回落 `Entity`。
int EntityNpcIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Npc);
}

// `EntityFamiliar` 视图的 `__index`（批次 330）：先查本视图元表的方法表，答不上落到 `Entity`
// （字段与其余方法都回落）—— 与 `EntityNpcIndex` 逐字同形。
int EntityFamiliarIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Familiar);
}

// `PathFinder` 视图的 `__index`（批次 344，2026-10-04）：`EntityNPC.Pathfinder` 交回的句柄的
// 元表。它**不是实体**，所以不走 `IndexEntity` —— 照 `EntityNpcIndex` 的形态直接写：
// 先查本元表 `__methods`（目前只有 `HasPathToPos`），答不上给 `nil`
// （没有"基类 `Entity`"可回落：PC 里 `PathFinder` 是独立类型）。
// ★ 句柄类型不对（不是 `PathFinder` userdata）⇒ `luaL_checkudata` 报错 —— 那是调用方写错了。
int PathFinderIndex(lua_State* state) {
    luaL_checkudata(state, 1, kPathFinderMetatable);
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    if (PushMethodFrom(state, kPathFinderMetatable, lua_tostring(state, 2))) {
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

// `EntityProjectile` 视图的 `__index`（批次 207）：先答 `ProjectileFlags`，答不上落到 `Entity`。
int EntityProjectileIndex(lua_State* state) {
    return IndexEntity(state, EntityView::Projectile);
}

// --- 引擎字段**写**入口（2026-09-16 起；2026-09-30 批次 212 扩到四个字段）-------------
//
// 为什么需要它：PC 的 `EntityPlayer` 上有几个字段是**模组天天在写**的，我们拒写就等于把这些模组的
// **整条回调**掐死（守卫是"报错"，不是"静默忽略"）。两次真事故：
//   ① `ControlsCooldown`（2026-09-16）：EID 用它"吃掉"随后的按键
//      ——`features/eid_bagofcrafting.lua:877`、`features/eid_holdmapdesc.lua:669` 都是 `= 2`；
//   ② `Velocity` / `Position` / `ControlsEnabled`（2026-09-30）：MCM 打开菜单时冻住玩家 ——
//      `modconfig.lua:1625 player.Velocity = vecZero`、`:1630 player.Position = …`、
//      `:1632 player.ControlsEnabled = false`。第 1625 行抛错 ⇒ 渲染回调**每帧**中断
//      ⇒ 菜单永远画不出来（真机症状："按右摇杆 UI 不见了、但菜单一片空白、也没声音"）。
//
// 口径（三条，缺一条就会掉回"静默失真"或"掐死模组"）：
//   * **只有 `EntityPlayer` 视图能写**（别的实体仍然只读）；
//   * **只认这四个字段名**（偏移全部有引擎自己的读点/写点做锚点，见 `runtime_constants.hpp`）；
//     陌生字段名**仍然报错** —— 这是故意的（防止把拼错的字段名静默吞掉），
//     但被拒的次数记进探针（`g_EntityFieldWriteRejected`），下次读数就能看见是谁在写什么；
//   * 每处写入都经 `WriteEngine`（先确认这一页**可写**）。写不进去就报错，不静默失败：
//     实体地址刚通过 vptr + 可读性校验，写不进说明可写性判断本身出了问题，报错比"模组以为写上了、
//     其实没写"更好查。
//
// ⚠️ 写 `Position` / `Velocity` 会**直接参与碰撞、AI、掉落**（这是 PC 语义，模组就是这么用的：
//    冻住玩家 / 传送）—— 我们按 PC 原样放开，**不再做额外校验**；真出问题先看探针里是谁在写。
int EntityNewIndex(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_type(state, 2) != LUA_TSTRING) {
        return luaL_error(state, "EntityPlayer fields are written by name");
    }
    const char* field = lua_tostring(state, 2);
    if (std::strcmp(field, "IsFetus") == 0) {
        if (luaL_testudata(state, 1, kEntityBombMetatable) == nullptr) {
            return luaL_error(state, "IsFetus requires EntityBomb");
        }
        const auto bomb = ValidatedTypedEntity(handle, kEntityBombVtableOffset, kEntityTypeBomb);
        const auto value = static_cast<std::uint8_t>(lua_toboolean(state, 3) != 0);
        if (bomb == 0 || !WriteEngine(bomb + kEntityBombIsFetusOffset, value)) {
            return luaL_error(state, "EntityBomb.IsFetus receiver is no longer writable");
        }
        return 0;
    }
    if (std::strcmp(field, "Scale") == 0 &&
        luaL_testudata(state, 1, kEntityTearMetatable) != nullptr) {
        const auto tear = ValidatedTypedEntity(handle, kEntityTearVtableOffset, kEntityTypeTear);
        const float value = static_cast<float>(luaL_checknumber(state, 3));
        const auto method = EntityMethodByExpectedBytes(kEntityTearSetScaleOffset,
                                                       kEntityTearSetScaleExpectedBytes);
        if (tear == 0 || method == 0) {
            return luaL_error(state, "EntityTear.Scale native receiver or binding is unavailable");
        }
        using EntityTearSetScaleFn = void (*)(std::uintptr_t, float);
        engine_call::AsFunction<EntityTearSetScaleFn>(method)(tear, value);
        return 0;
    }
    if (IsFamiliarOrbitField(field)) {
        const auto familiar = ValidatedEntityFamiliar(handle);
        if (familiar==0) return luaL_error(state,"EntityFamiliar.%s receiver is no longer available",field);
        if (std::strcmp(field,"OrbitDistance")==0) {
            const auto* vector = RequireVectorArgument(state,3);
            const std::array<float,2> value{vector->x,vector->y};
            if (!WriteEngine(familiar+kEntityFamiliarOrbitDistanceOffset,value))
                return luaL_error(state,"EntityFamiliar.OrbitDistance is not writable");
        } else if (std::strcmp(field,"OrbitSpeed")==0) {
            const auto value = static_cast<float>(luaL_checknumber(state,3));
            if (!WriteEngine(familiar+kEntityFamiliarOrbitSpeedOffset,value))
                return luaL_error(state,"EntityFamiliar.OrbitSpeed is not writable");
        } else {
            const auto value = static_cast<std::int32_t>(static_cast<std::uint32_t>(luaL_checkinteger(state,3)));
            if (!WriteEngine(familiar+kEntityFamiliarOrbitLayerOffset,value))
                return luaL_error(state,"EntityFamiliar.OrbitLayer is not writable");
        }
        return 0;
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    if (entity == 0) {
        // 过期/伪造句柄：与读路径同一口径 —— 不报错、也不写（写一个失效地址才是真危险）。
        return 0;
    }
    if(TryWriteApi400EntityField(state,entity,field))return 0;
    if(TryWriteRPlusEntityField(state,entity,field))return 0;
    if(TryWriteExtendedEntityField(state,entity,field))return 0;
    if(TryWriteApi500EntityField(state,entity,field))return 0;
    if(TryWriteApi600EntityField(state,entity,field))return 0;
    if(TryWriteApi600ExtraEntityField(state,entity,field))return 0;
    if(TryWriteApi600PlayerField(state,entity,field))return 0;
    if (std::strcmp(field, "TearFlags") == 0) {
        BitSet128Value value{};
        if (!ReadBitSet128(state, 3, &value)) { return luaL_error(state, "TearFlags expects BitSet128"); }
        if (IsEntityPlayer(entity)) {
            if (!WriteEngine(entity + kEntityPlayerTearFlagsOffset, value)) { return luaL_error(state, "TearFlags is not writable"); }
            return 0;
        }
        std::uintptr_t vtable = 0;
        if (ReadEngine(entity, &vtable) && vtable == EngineModuleBase() + kEntityTearVtableOffset) {
            const auto method = EngineOffsetAddress<IsEngineMemoryReadable>(kEntityTearSetTearFlagsOffset);
            if (!EngineEntryOrRelayMatches<IsEngineMemoryReadable>(method,
                kEntityTearSetTearFlagsExpectedBytes.data(), kEntityTearSetTearFlagsExpectedBytes.size(), 0)) {
                return luaL_error(state, "EntityTear.TearFlags native bindings are unavailable");
            }
            std::uint64_t args[8] = {entity, value.low, value.high, 0, 0, 0, 0, 0};
            double floats[8] = {};std::uint64_t result = 0;double fresult = 0;
            EngineCallTrampoline(method, args, floats, &result, &fresult);
            return 0;
        }
        return luaL_error(state, "TearFlags requires EntityPlayer or EntityTear");
    }
    // 探针：记下"最近一次写的字段名"（FNV-1a 32 位；读数里按已知名字反查）+ 拒绝计数。
    std::uint32_t hash = 2166136261u;
    for (const char* cursor = field; *cursor != '\0'; ++cursor) {
        hash = (hash ^ static_cast<std::uint8_t>(*cursor)) * 16777619u;
    }
    g_LastEntityFieldWriteName.store(hash, std::memory_order_relaxed);
    const auto count_write = [](std::size_t index) {
        g_EntityFieldWrites[index].fetch_add(1, std::memory_order_relaxed);
    };
    if (std::strcmp(field, "TearColor") == 0) {
        if (!IsEntityPlayer(entity)) return luaL_error(state, "TearColor requires EntityPlayer");
        EngineColorMod color{};
        if (!FillEngineColorMod(state, 3, &color)) return luaL_error(state, "TearColor expects Color");
        if (!WriteEngine(entity + kEntityPlayerTearColorOffset, color))
            return luaL_error(state, "EntityPlayer.TearColor is not writable");
        count_write(24);
        return 0;
    }

    if (NamePrefix2Matches(field, "ControlsCooldown") && std::strcmp(field, "ControlsCooldown") == 0) {
        if (!IsEntityPlayer(entity)) return luaL_error(state, "ControlsCooldown requires EntityPlayer");
        const lua_Integer value = luaL_checkinteger(state, 3);
        const std::int32_t stored = static_cast<std::int32_t>(value);
        if (!WriteEngine<std::int32_t>(entity + kEntityPlayerControlsCooldownOffset, stored)) {
            return luaL_error(state, "EntityPlayer.ControlsCooldown is not writable on this object");
        }
        count_write(3);
        return 0;
    }
    if (NamePrefix2Matches(field, "ControlsEnabled") && std::strcmp(field, "ControlsEnabled") == 0) {
        if (!IsEntityPlayer(entity)) return luaL_error(state, "ControlsEnabled requires EntityPlayer");
        // bool（1 字节）—— 锚点 = 引擎自己的 `PlayerManager::SetControlsEnabled @ 0x4422C0`
        // 里的 `strb w9,[x10,#0x400]`（见 `runtime_constants.hpp`）。
        const std::uint8_t stored = lua_toboolean(state, 3) != 0 ? 1 : 0;
        if (!WriteEngine<std::uint8_t>(entity + kEntityPlayerControlsEnabledOffset, stored)) {
            return luaL_error(state, "EntityPlayer.ControlsEnabled is not writable on this object");
        }
        count_write(2);
        return 0;
    }
    // `HitPoints` / `MaxHitPoints`（批次 245，2026-10-01）：`Entity` **基类**的两个 **float**
    // 字段，直接按 float 写。语义与 PC 一致：写 `HitPoints` 就是改当前血量（引擎下一帧照常用它），
    // 写 `MaxHitPoints` 只改上限（**不**自动把当前血量夹进去 —— PC 的 `AddHealth` 才是夹的那个，
    // 见 `runtime_constants.hpp` 的取证）。
    // ★ 不判类型：这两个是**基类**字段（`Entity.md:750/774`），任何实体都有。
    if ((NamePrefix2Matches(field, "HitPoints") && std::strcmp(field, "HitPoints") == 0) || (NamePrefix2Matches(field, "MaxHitPoints") && std::strcmp(field, "MaxHitPoints") == 0)) {
        const std::uintptr_t offset = field[0] == 'H' ? kEntityHitPointsOffset
                                                      : kEntityMaxHitPointsOffset;
        const float value = static_cast<float>(luaL_checknumber(state, 3));
        if (!WriteEngine<float>(entity + offset, value)) {
            return luaL_error(state, "Entity HitPoints/MaxHitPoints is not writable on this object");
        }
        // 桶号 4/5 是本批新开的（口径：只能往后追加）。
        count_write(field[0] == 'H' ? 4u : 5u);
        return 0;
    }
    // `Scale`（批次 246，2026-10-01）：与读路径同一道判据（只在 NPC 家族上可写）。
    // ★ 写本格**不需要**顺手改 `Size`：引擎的 `Entity_NPC::Update` 每帧调 `update_sprite_scale()`
    //   把本格乘进 `Size`（取证见 `kEntityNpcScaleOffset`）⇒ 下一帧生效，与 PC 语义一致。
    if (NamePrefix2Matches(field, "Scale") && std::strcmp(field, "Scale") == 0) {
        if (!IsNpcFamilyEntity(entity)) {
            return luaL_error(state, "Entity.Scale is only writable on EntityNPC");
        }
        const float value = static_cast<float>(luaL_checknumber(state, 3));
        if (!WriteEngine<float>(entity + kEntityNpcScaleOffset, value)) {
            return luaL_error(state, "Entity.Scale is not writable on this object");
        }
        count_write(6u);  // 桶号 6（本批新开，口径：只能往后追加）
        return 0;
    }
    // 六个战斗属性（批次 405，2026-10-07）：`MaxFireDelay` / `ShotSpeed` / `Damage` / `MoveSpeed` /
    // `Luck` / `TearRange` —— **全部是 float**，PC 契约对它们反复写同一句：
    //   "Player stat - Only change this in a callback to MC_EVALUATE_CACHE."
    // 为什么必须放开：Trinity 在 `MC_EVALUATE_CACHE` 处理器里就写这几格（`main.lua:85` 的
    // `player.Damage`、`:116` 的 `MaxFireDelay`/`MoveSpeed`/`Luck`）；拒写 = 每次属性重算都抛错
    // ⇒ 那条回调被派发器摘掉 ⇒ 自定义角色的属性调整整块失效。
    // 每格的偏移证据（引擎自己的读点/写点）都在 `runtime_constants.hpp` 的同名常量注释里；
    // 这里**不留裸字面量偏移**（写点必须引用具名常量，见 `test_engine_write_channel`）。
    // ★ 表驱动只为少写重复分支；字段名仍逐个精确比较（拼错的名字照旧落到下面的拒写）。
    // ★ 桶号只能往后追加（口径同上面几格）：7..12。
    {
        struct PlayerStatWrite {
            const char* name;
            std::uintptr_t offset;
            std::size_t bucket;
        };
        static constexpr PlayerStatWrite kPlayerStatWrites[] = {
            {"MaxFireDelay", kEntityPlayerMaxFireDelayOffset, 7u},
            {"ShotSpeed", kEntityPlayerShotSpeedOffset, 8u},
            {"Damage", kEntityPlayerDamageOffset, 9u},
            {"MoveSpeed", kEntityPlayerMoveSpeedOffset, 10u},
            {"Luck", kEntityPlayerLuckOffset, 11u},
            {"TearRange", kEntityPlayerTearRangeOffset, 12u},
            {"TearHeight", kEntityPlayerTearHeightOffset, 21u},
            {"TearFallingSpeed", kEntityPlayerTearFallingSpeedOffset, 22u},
            {"TearFallingAcceleration", kEntityPlayerTearFallingAccelerationOffset, 23u},
        };
        for (const PlayerStatWrite& stat : kPlayerStatWrites) {
            if (std::strcmp(field, stat.name) != 0) {
                continue;
            }
            if (!IsEntityPlayer(entity)) return luaL_error(state, "%s requires EntityPlayer", stat.name);
            const float value = static_cast<float>(luaL_checknumber(state, 3));
            if (!WriteEngine<float>(entity + stat.offset, value)) {
                return luaL_error(state, "EntityPlayer.%s is not writable on this object", stat.name);
            }
            count_write(stat.bucket);
            return 0;
        }
    }
    // `Velocity` / `Position`：`KAGE::Math::Vector2` = 两个 float（与 Lua 的 `Vector` **同布局**
    // ——`vector_api.cpp` 的文件头有取证：8 字节、无 vtable）。所以按两个 `float` 写下去。
    if (std::strcmp(field, "Velocity") == 0 || std::strcmp(field, "Position") == 0 ||
        std::strcmp(field,"PositionOffset") == 0) {
        const bool velocity = field[0] == 'V';
        const bool renderOffset = std::strcmp(field,"PositionOffset")==0;
        const std::uintptr_t offset = velocity ? kEntityVelocityOffset : (renderOffset ? kEntityPositionOffsetOffset : kEntityPositionOffset);
        const std::size_t index = velocity ? 0u : 1u;
        auto* vector = RequireVectorArgument(state,3);
        const float* components = &vector->x;
        if (!WriteEngine<float>(entity + offset, components[0]) ||
            !WriteEngine<float>(entity + offset + sizeof(float), components[1])) {
            return luaL_error(state, "EntityPlayer velocity/position is not writable on this object");
        }
        if (!renderOffset) count_write(index);
        return 0;
    }
    // PC Entity.md的非const字段；只用已有真实消费链确认的偏移。
    struct CommonFloatWrite { const char* name; std::uintptr_t offset; std::size_t bucket; };
    static constexpr CommonFloatWrite commonFloats[] = {
        {"Size", kEntitySizeOffset, 13u}, {"Friction", kEntityFrictionOffset, 14u},
    };
    for (const auto& entry : commonFloats) {
        if (std::strcmp(field, entry.name) != 0) continue;
        const float value = static_cast<float>(luaL_checknumber(state, 3));
        if (!WriteEngine<float>(entity + entry.offset, value)) return luaL_error(state, "%s is not writable", field);
        count_write(entry.bucket);
        return 0;
    }
    if (std::strcmp(field, "Visible") == 0 || std::strcmp(field, "CanFly") == 0) {
        const bool canFly = field[0] == 'C';
        if (canFly && !IsEntityPlayer(entity)) return luaL_error(state, "CanFly requires EntityPlayer");
        const auto offset = canFly ? kEntityPlayerCanFlyOffset : kEntityVisibleOffset;
        const std::uint8_t value = lua_toboolean(state, 3) != 0 ? 1 : 0;
        if (!WriteEngine<std::uint8_t>(entity + offset, value)) return luaL_error(state, "%s is not writable", field);
        count_write(canFly ? 20u : 15u);
        return 0;
    }
    struct CommonIntegerWrite { const char* name; std::uintptr_t offset; std::size_t bucket; };
    static constexpr CommonIntegerWrite commonIntegers[] = {
        {"Variant", kEntityVariantOffset, 16u}, {"SubType", kEntitySubTypeOffset, 17u},
        {"SpawnerType", kEntitySpawnerTypeOffset, 18u}, {"SpawnerVariant", kEntitySpawnerVariantOffset, 19u},
    };
    for (const auto& entry : commonIntegers) {
        if (std::strcmp(field, entry.name) != 0) continue;
        const auto value = static_cast<std::uint32_t>(luaL_checkinteger(state, 3));
        if (!WriteEngine<std::uint32_t>(entity + entry.offset, value)) return luaL_error(state, "%s is not writable", field);
        count_write(entry.bucket);
        return 0;
    }
    g_EntityFieldWriteRejected.fetch_add(1, std::memory_order_relaxed);
    return luaL_error(state, "EntityPlayer fields are read-only except "
                             "Velocity/Position/HitPoints/MaxHitPoints/Scale(NPC only)/"
                             "ControlsEnabled/ControlsCooldown/"
                             "Damage/MoveSpeed/MaxFireDelay/ShotSpeed/Luck/TearRange/"
                             "Size/Friction/Visible/Variant/SubType/SpawnerType/SpawnerVariant/CanFly");
}

// --- Entity / EntityPlayer 方法 ----------------------------------------------

int EntityToPlayer(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Entity:ToPlayer accepts no arguments");
    }
    // PC 文档（`Entity.md:631`）："If the conversion is not successful, this function returns
    // `nil`"。批次 2 时只会交付出 `EntityPlayer`，所以无条件返回自身；批次 4 起
    // `Isaac.FindInRadius`/`FindByType` 会给出任意实体，这里必须真的判类型。
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    if (entity == 0) {
        // 不是 `Entity_Player`（含过期句柄）→ nil。
        PushNil(state);
        return 1;
    }
    if (luaL_testudata(state, 1, kEntityPlayerMetatable) != nullptr) {
        // 已经拿着 `EntityPlayer` 视图：PC 的 `EntityPlayer:ToPlayer()` 返回的**就是自己**，
        // 身份相等（`player:ToPlayer() == player`）必须成立。
        lua_pushvalue(state, 1);
        return 1;
    }
    // 拿着 `Entity` 视图但底层确实是玩家：换成 `EntityPlayer` 视图（PC 返回的是同一个对象，
    // 只是类型是 `EntityPlayer`）。
    PushEntityHandle(state, entity, kEntityPlayerMetatable);
    return 1;
}

// `Entity:ToPickup()`（批次 4）：PC 文档（`Entity.md:635`）"Used to cast an Entity object to an
// EntityPickup object... If the conversion is not successful, this function returns nil"。
// 判据两条同时成立：`Type == 5`（ENTITY_PICKUP）**且** vptr == `base + 0xA36E28`
// （`Entity_Pickup` 的 vtable 唯一，`docs/问题与解决记录.md` 批次 4 的小偏移表）。
int EntityToPickup(lua_State* state) {
    RecordFilterChain(2U);
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Entity:ToPickup accepts no arguments");
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    const std::uintptr_t base = EngineModuleBase();
    std::uintptr_t vtable = 0;
    std::uint32_t type = 0;
    if (entity == 0 || base == 0 || base > UINTPTR_MAX - kEntityPickupVtableOffset ||
        !ReadEngine(entity, &vtable) || !ReadEngine(entity + kEntityTypeOffset, &type) ||
        type != kEntityTypePickup || vtable != base + kEntityPickupVtableOffset) {
        PushNil(state);
        return 1;
    }
    PushEntityHandle(state, entity, kEntityPickupMetatable);
    return 1;
}

// `Entity:ToProjectile()`（批次 207，2026-09-29）：PC 契约 `Entity.md:651/653` ——
// `#### EntityProjectile ToProjectile ( )`，`data-altreturn='nil'`，正文 "Used to cast an
// Entity object to an EntityProjectile object… If the conversion is not successful, this function
// returns `nil`."
//
// 判据与 `EntityToPickup` 逐字同形（两条同时成立）：`Type == 9`（ENTITY_PROJECTILE）
// **且** vptr == `base + 0xA37410`（`Entity_Projectile` 的 vtable 唯一，见
// `runtime_constants.hpp` 的 `kEntityProjectileVtableOffset`）。
//
// 为什么 MCM 需要它：`modconfig.lua:220` 写的是
// `entity.Type == EntityType.ENTITY_PROJECTILE and entity:ToProjectile().ProjectileFlags
//  & ProjectileFlags.CANT_HIT_PLAYER ~= 1`（判"这发子弹会不会打到玩家"）。
// `ToProjectile` 返回 nil 时那半句立刻变 "attempt to index a nil value" ⇒ 整条
// `RoomIsSafe()` 抛错 ⇒ 菜单打不开。
int EntityToProjectile(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Entity:ToProjectile accepts no arguments");
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    const std::uintptr_t base = EngineModuleBase();
    std::uintptr_t vtable = 0;
    std::uint32_t type = 0;
    if (entity == 0 || base == 0 || base > UINTPTR_MAX - kEntityProjectileVtableOffset ||
        !ReadEngine(entity, &vtable) || !ReadEngine(entity + kEntityTypeOffset, &type) ||
        type != kEntityTypeProjectile || vtable != base + kEntityProjectileVtableOffset) {
        PushNil(state);
        return 1;
    }
    // 底层已经是投射物（拿着投射物视图再 `ToProjectile()`）⇒ PC 返回自己，身份相等必须成立。
    // ★ 这一支在 2026-09-29 之前是**死代码**：`CheckEntityHandle` 不认 `EntityProjectile`
    //   元表，走不到这里就先报错了。宿主行为测试抓到后已把第四张元表补进那个校验口
    //   （见 `CheckEntityHandle` 的注释）。
    if (luaL_testudata(state, 1, kEntityProjectileMetatable) != nullptr) {
        lua_pushvalue(state, 1);
        return 1;
    }
    PushEntityHandle(state, entity, kEntityProjectileMetatable);
    return 1;
}

// `EntityProjectile` 的字段（批次 207，2026-09-29）。目前只有一条：`ProjectileFlags`。
//
// 每次访问都**重做**"这真是一张 `Entity_Projectile`"的校验（`Type == 9` 且 vptr 精确相等），
// 与 `PushEntityPickupField` 同一口径 —— 句柄可能跨帧失效，缓存指针不可信。
//
// `ProjectileFlags` 在引擎里是 `int`（PC 契约 `EntityProjectile.md`），偏移 `+0x428`
// （取证见 `runtime_constants.hpp` 的 `kEntityProjectileFlagsOffset`）。
// ★ 按**有符号**读：`ProjectileFlags` 的最高位（bit31 = `CANT_HIT_PLAYER`）置位时，
//   无符号读会给出一个大正数，而 PC 的 Lua 侧拿到的是负整数 —— MCM 那句
//   `& ProjectileFlags.CANT_HIT_PLAYER` 在 Lua 的 64 位整数里对正负都成立，
//   但为了与 PC 的数值逐位一致（模组可能把整个值存下来比较），这里按 `int32` 读。
// 2026-10-25更正：上面32位/符号扩展说明是旧误判。固定PC getter
// 0x4126C0以edx:eax返回64位；NS写入/原生Update也消费完整64位。
// 保留旧说明作历史，实际按64位读取，避免高位延时标志被截断。
bool PushEntityProjectileField(lua_State* state, std::uintptr_t entity, const char* field) {
    if (std::strcmp(field, "ProjectileFlags") != 0) {
        return false;
    }
    const std::uintptr_t base = EngineModuleBase();
    if (entity == 0 || base == 0 || base > UINTPTR_MAX - kEntityProjectileVtableOffset) {
        return false;
    }
    std::uintptr_t vtable = 0;
    std::uint32_t type = 0;
    if (!ReadEngine(entity, &vtable) || !ReadEngine(entity + kEntityTypeOffset, &type) ||
        type != kEntityTypeProjectile || vtable != base + kEntityProjectileVtableOffset) {
        return false;
    }
    std::uint64_t flags = 0;
    if (!ReadEngine(entity + kEntityProjectileFlagsOffset, &flags)) {
        return false;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(flags));
    return true;
}

// `EntityPickup:IsShopItem()`（PC 契约 `EntityPickup.md:35`：`boolean IsShopItem()`）：
// **真实现，判据 = `Price != 0`**（2026-09-29 取证并落地；此前是恒 false 的安全 stub）。
//
// ★ 判据的取证（三条指令级互证 + 一条外部权威）：
//   1. **写入侧锚点（最硬）**：`Entity_Pickup::SetPrice(int price)` @ `0x26B1C8` 的**首条指令**
//      就是 `str w1, [x0, #0x564]` —— 函数名说的是 Price、参数直接落进 `+0x564`
//      ⇒ `Entity_Pickup.Price == +0x564`（PC 契约 `EntityPickup.md:80-82` 就是 `int Price`，
//      正文 "Price of the pickup in shops"）。
//   2. **读取侧**：`Entity_Pickup::CanPickupShopItem(Entity_Player*)` @ `0x271700` 反复读 `+0x564`
//      做价格分支，其中 `cmn w9, #0xa`（与 `-10` 比较）正对上 isaacscript `PickupPrice` 里的
//      `DEVIL_SACRIFICE_SPIKES = -10`。
//   3. **定价路径**：`Entity_Pickup::MakeShopItem(int slot)` @ `0x270FC4` 先读 `+0x564`，
//      `Price == 0` 才算「还没定价」，然后把槽位写进 `+0x56C`（`ShopItemId`）、
//      再把 `Room::GetShopItemPrice(...)` 的结果写回 `+0x564` —— 两个字段的分工一目了然。
//   4. **外部权威**：isaacscript 的 `PickupPrice` 枚举文档明写
//      "Pickup.Price will be equal to 0 for non-purchasable pickups"
//      ⇒ 非卖品 `Price` 恒为 0，`Price != 0` 就是「这是商店里卖的东西」。
//
// ★ 为什么**不是** `ShopItemId`（这正是当初卡住的误判点）：`+0x56C` 的语义是「商店列表里的
// 槽位下标」，`EntityPickup.md:93` 明说「新生成的收藏品默认 `ShopItemId == 0`」，而负数被当作
// 「给一个不参与 D6 重投的 id」用 ⇒ `0` 既可能是「不是商店商品」也可能是「列表第 0 项」，判不了。
//
// 为什么必须有这个名字：EID 在**卡片/药丸描述**路径上无条件调用它
// （`main.lua:1611`/`1636`：`closest:ToPickup():IsShopItem() and (...)`，`main.lua:926` 的指示箭头
// 路径、`features/eid_bagofcrafting.lua:935` 同理）。返回 nil 方法会让那一句变成
// "attempt to call a nil value (method 'IsShopItem')"，整段描述渲染直接中断。
// ★ 修好它之后，商店里「商品旁的描述该隐藏 / 该挪位置」才与 PC 一致（此前恒 false ⇒ 永远不隐藏）。
// `EntityPickup:CanReroll()`（PC 文档 `EntityPickup.md:25`：`boolean CanReroll()`）。
//
// 引擎方法 `Entity_Pickup::CanReroll() const` @ `0x26AFA8`（函数体很短：先看 `+0x1C3` 那个字节，
// 再按 `Type` 与一个区间比较），入口指纹 `0x39470C09`。
//
// 为什么这条值得接：EID 在链式调用里用它（`xxx:CanReroll()`），而候选 owner 是
// `EntityNPC`/`EntityPickup` 两个 —— 我们**只有** `EntityPickup` 视图（没有 `EntityNPC` 视图，
// 见 `kEntityPickupCanRerollOffset` 的注释），所以先补这一半；另一半等 `EntityNPC` 视图。
int EntityPickupCanReroll(lua_State* state) {
    RecordFilterChain(4U);
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPickup:CanReroll accepts no arguments");
    }
    // PC 837D70 uses the Pickup class registry, rejecting sibling Player/NPC self.
    // Check the lifetime before native memory; avoid a generic check plus a second vptr read.
    const std::uintptr_t entity = handle && isaac::runtime::EntityLifetimeAlive(handle->lifetime)
        ? engine_memory::AddressOf(handle->entity) : 0;
    if (!IsTypedEntity(entity,kEntityPickupVtableOffset,kEntityTypePickup)) {
        return luaL_error(state, "EntityPickup:CanReroll requires a live EntityPickup");
    }
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityPickupCanRerollOffset ||
        !IsEngineMemoryReadable(base + kEntityPickupCanRerollOffset, sizeof(std::uint32_t))) {
        return luaL_error(state, "EntityPickup:CanReroll native binding is unavailable");
    }
    std::uint32_t entryWord = 0;
    if (!ReadEngine(base + kEntityPickupCanRerollOffset, &entryWord) ||
        entryWord != kEntityPickupCanRerollEntryWord) {
        return luaL_error(state, "EntityPickup:CanReroll native binding does not match this build");
    }
    // 引擎签名：`bool (*)(const Entity_Pickup*)`（`this` 在 x0，布尔在 w0 返回）。
    using CanRerollFn = bool (*)(const void*);
    const bool canReroll = engine_call::AsFunction<CanRerollFn>(
        base + kEntityPickupCanRerollOffset)(engine_memory::AsObject(entity));
    lua_pushboolean(state, canReroll ? 1 : 0);
    return 1;
}

int EntityPickupIsShopItem(lua_State* state) {
    RecordFilterChain(4U);
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPickup:IsShopItem accepts no arguments");
    }
    // 真实现：`IsShopItem()` == `Price != 0`（判据的取证与三条互证见上方注释）。
    const std::uintptr_t entity = ValidatedEntity(handle);
    std::int32_t price = 0;
    // 句柄失效 / 偏移读不到 ⇒ 静默给 false（**不抛错**）：EID 在卡片/药丸描述路径上
    // **无条件**调用它，抛错会被派发器摘掉整条回调，比给 false 危险得多。
    if (entity == 0 || !ReadEngine(entity + kEntityPickupPriceOffset, &price)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    lua_pushboolean(state, price != 0 ? 1 : 0);
    return 1;
}

// --- 批次 242（2026-09-30）：**下转族** ----------------------------------------------------
//
// `Entity:ToNPC` / `ToTear` / `ToLaser` / `ToEffect` / `ToKnife`。这 5 条在 PC 上都是
// "把 `Entity` 转成具体子类，转不成就返回 `nil`"（`Entity.md:631/635/651…` 的同一句话），
// 与既有的 `ToPlayer`/`ToPickup`/`ToFamiliar`/`ToProjectile` 是**同一个族**。
//
// 判据与那 4 条**逐字同形**：`vptr` **精确等于** `base + <类>VtableOffset`。
// 对 `Entity_NPC` 为什么精确相等也成立（它名字像基类）：见 `runtime_constants.hpp`
// 批次 241 段 —— NRO 符号表里**全部 71 个** `_ZTVN15IsaacRepentance*` 里**一个敌人子类都没有**。
//
// 视图一律用**基类 `Entity` 元表** —— 与 `EntityToFamiliar` 同一条理由（那 5 类没有自己的元表，
// 而句柄方法表是**继承**的：`IndexEntity` 对所有非 Base 视图都回落到 `Entity` 元表）。
//
// ★★ 本批**只做"类型闸门"**，**不做**这些类自己的**字段/方法**：
//   语料在下转结果上真正要的是 `t:ToTear().TearFlags = …` / `c:ToNPC().HitPoints = …` /
//   `e:ToLaser():GetEndPoint()` —— 那分别需要**新的可写字段通道**与**新的引擎方法**，
//   是**另外的能力**（存档 README 的"已知欠账"里逐条列了）。⇒ 本批之后这些模组调用
//   **仍会在下一步失败**（`EntityNewIndex` 对未登记字段会报错）—— 别把"下转能用了"
//   误读成"这些模组的这段能跑"。
int PushEntityDowncast(lua_State* state, const char* api, std::uintptr_t vtableOffset,
                       bool useType, std::uint32_t expectedType,
                       EntityView view = EntityView::Base) {
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "%s accepts no arguments", api);
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    const std::uintptr_t base = EngineModuleBase();
    std::uintptr_t vtable = 0;
    if (entity == 0 || base == 0 || base > UINTPTR_MAX - vtableOffset ||
        !ReadEngine(entity, &vtable) || vtable != base + vtableOffset) {
        // PC 口径：转换失败返回 `nil`（不是报错）—— 模组普遍写 `if x:ToTear() then`。
        PushNil(state);
        return 1;
    }
    if (useType) {
        std::uint32_t type = 0;
        if (!ReadEngine(entity + kEntityTypeOffset, &type) || type != expectedType) {
            PushNil(state);
            return 1;
        }
    }
    //: 批次 281：视图参数决定压哪张元表（默认 `Entity`，与既有调用逐字一致）。
    PushEntityHandle(state, entity, EntityViewMetatable(view));
    return 1;
}

int EntityToNpc(lua_State* state) {
    // 契约 `tools/pc_contract_docs/Entity.md` 的 `#### EntityNPC ToNPC ( )`（转不成返回 nil）。
    //
    // ★★ 判据是**"`Entity` 家族区间内、且不是那 13 个非 NPC 直接子类"**，**不是**精确 vptr：
    //   批次 242 曾按"精确等于 `Entity_NPC` 的 vtable"实现，依据是"符号表里 71 个 `_ZTV` 没有
    //   敌人子类"—— **那个依据是错的**（`_ZTV` 只是导出的那部分）。按长度前缀正确解析后
    //   `Entity_NPC` 有 **49 个子类**（`_Beast`/`_Chimera`/`_Dogma`/`_Mother`/`_UltraWar`/
    //   `_VisageMask` …），它们的 vtable 不在符号表里 ⇒ 精确比对会让**所有 BOSS 都返回 nil**。
    //   本判据用"区间减排除"，那 49 个（以及将来新增的 NPC 子类）一样落在区间内、也不是这 13 个，
    //   所以能正确放行。
    //
    // ★ 为什么对 `Entity_NPC` 也不能看 `Type`：敌人的 `Type` **每个各不相同**
    //   （那正是 `EntityType.ENTITY_*` 的用法）⇒ 对它只有"类身份"这一个判据。
    // 消费方：`IsaacOnTwitchReloaded/scripts/helper.lua` 的 `c:ToNPC().MaxHitPoints = …`。
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Entity:ToNPC accepts no arguments");
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    if (!IsNpcFamilyEntity(entity)) {
        // 不是 NPC 家族（含失效句柄、以及 Bomb/Dummy/Slot/Tear/… 这些兄弟类）⇒ PC 的"转换失败"口径。
        PushNil(state);
        return 1;
    }
    //: 批次 285：命中后压 **`EntityNPC` 视图**（此前压基类 `Entity` 元表 ⇒ `EntityNPC` 页上的
    //: 方法如 `Morph` 没有地方挂，`npc:Morph(...)` 是 `attempt to call a nil value`）。
    //: 字段仍回落到 `Entity`（`IndexEntity` 的 else 分支）⇒ 老用法不退化。
    PushEntityHandle(state, entity, EntityViewMetatable(EntityView::Npc));
    return 1;
}

int EntityToTear(lua_State* state) {
    // 需求最集中的一条（语料 23 处）：`IsaacOnTwitchReloaded` 生成眼泪之后写
    // `t:ToTear().TearFlags = …` / `.Scale = …`（`scripts/passiveItems.lua`）。
    //: 批次 281：命中后压 **`EntityTear` 视图**（此前压 `Entity` 元表 ⇒ 它自己的方法取不到）。
    return PushEntityDowncast(state, "Entity:ToTear", kEntityTearVtableOffset, true, kEntityTypeTear,
                              EntityView::Tear);
}

int EntityToBomb(lua_State* state) {
    const auto bomb = ValidatedTypedEntity(CheckEntityHandle(state, 1),
                                          kEntityBombVtableOffset, kEntityTypeBomb);
    if (bomb == 0) {
        PushNil(state);
    } else {
        PushEntityHandle(state, bomb, kEntityBombMetatable);
    }
    return 1;
}

using EntitySetSpriteFrameFn = void (*)(std::uintptr_t, const char*, std::int32_t);
int EntitySetSpriteFrame(lua_State* state) {
    const char* name = luaL_checklstring(state, 2, nullptr);
    const auto frame = static_cast<std::int32_t>(static_cast<std::uint32_t>(luaL_checkinteger(state, 3)));
    const auto entity = ValidatedEntity(CheckEntityHandle(state, 1));
    const auto method = EntityMethodByExpectedBytes(kSpriteSetFrameNamedOffset,
                                                   kSpriteSetFrameNamedExpectedBytes);
    if (entity == 0 || method == 0) {
        return luaL_error(state, "Entity:SetSpriteFrame native receiver or binding is unavailable");
    }
    engine_call::AsFunction<EntitySetSpriteFrameFn>(method)(entity + kEntitySpriteOffset, name, frame);
    return 0;
}

using EntityTearResetSpriteScaleFn = void (*)(std::uintptr_t);
int EntityTearResetSpriteScale(lua_State* state) {
    const auto tear = ValidatedTypedEntity(CheckEntityHandle(state, 1),
                                          kEntityTearVtableOffset, kEntityTypeTear);
    const auto method = EntityMethodByExpectedBytes(kEntityTearResetSpriteScaleOffset,
                                                   kEntityTearResetSpriteScaleExpectedBytes);
    if (tear == 0 || method == 0) {
        return luaL_error(state, "EntityTear:ResetSpriteScale native receiver or binding is unavailable");
    }
    engine_call::AsFunction<EntityTearResetSpriteScaleFn>(method)(tear);
    return 0;
}

// `EntityTear:ChangeVariant(TearVariant NewVariant)` —— PC 契约 `tools/pc_contract_docs/EntityTear.md`，
// 语料 **8 处**（`t:ChangeVariant(TearVariant.COIN)` 这种：把一颗普通的眼泪变成金币泪/金属泪…）。
// 引擎入口 `Entity_Tear::ChangeVariant(int)` @ `0x3412D8`（arity **1** = 契约那一个参数 ✓；
// **同名方法只有一个类有**）。
//
// ★ 这条是**视图化的第一条**：它的接收者来自 `Entity:ToTear()`（批次 281 起压 `EntityTear` 视图），
//   在此之前 `t:ChangeVariant(...)` 会报 "attempt to call a nil value"（方法取不到）。
// 失败降级：拿不到实体（句柄失效）或入口对不上 ⇒ 什么都不做、不报错（PC 返回 `void`）。
int EntityTearChangeVariant(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 2 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state, "EntityTear:ChangeVariant expects a variant; got %d argument(s)",
                          stackTop - 1);
    }
    const std::int32_t variant = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityTear:ChangeVariant");
    const std::uintptr_t method = EntityMethodByExpectedBytes(
        kEntityTearChangeVariantOffset, kEntityTearChangeVariantExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityTearChangeVariantFn = void (*)(std::uintptr_t, std::int32_t);
    engine_call::AsFunction<EntityTearChangeVariantFn>(method)(entity, variant);
    return 0;
}

int EntityToLaser(lua_State* state) {
    // `IsaacOnTwitchReloaded/scripts/passiveItems.lua`：`e:ToLaser():GetEndPoint()`。
    //: 批次 282：命中后压 **`EntityLaser` 视图**（此前压 `Entity` 元表 ⇒ 它自己的方法取不到）。
    return PushEntityDowncast(state, "Entity:ToLaser", kEntityLaserVtableOffset, true, kEntityTypeLaser,
                              EntityView::Laser);
}

// `EntityLaser:SetActiveRotation(int Delay, float AngleDegrees, float RotationSpd, boolean TimeoutComplete)`
// —— PC 契约 `tools/pc_contract_docs/EntityLaser.md`，语料 **6 处**（`mlaser:SetActiveRotation(1, 999360, 2, true)`
// 这种：让激光绕轴自转）。
// 引擎入口 `Entity_Laser::SetActiveRotation(unsigned, float, float, bool)` @ `0xF7540`
// （arity **4** = 契约四个参数 ✓；**同名方法只有一个类有**）。
//
// ★ 接收者来自 `Entity:ToLaser()`（批次 282 起压 `EntityLaser` 视图）。
// 失败降级：拿不到实体（句柄失效）或入口对不上 ⇒ 什么都不做、不报错（PC 返回 `void`）。
int EntityLaserSetActiveRotation(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 5 || !IsIntegerArgument(state, 2) || !lua_isnumber(state, 3) ||
        !lua_isnumber(state, 4)) {
        return luaL_error(
            state,
            "EntityLaser:SetActiveRotation expects (Delay, AngleDegrees, RotationSpd, TimeoutComplete); "
            "got %d argument(s)",
            stackTop - 1);
    }
    const std::uint32_t delay = static_cast<std::uint32_t>(lua_tointegerx(state, 2, nullptr));
    const float angleDegrees = static_cast<float>(lua_tonumber(state, 3));
    const float rotationSpeed = static_cast<float>(lua_tonumber(state, 4));
    const bool timeoutComplete = lua_toboolean(state, 5) != 0;
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityLaser:SetActiveRotation");
    const std::uintptr_t method = EntityMethodByExpectedBytes(
        kEntityLaserSetActiveRotationOffset, kEntityLaserSetActiveRotationExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityLaserSetActiveRotationFn = void (*)(std::uintptr_t, std::uint32_t, float, float, bool);
    engine_call::AsFunction<EntityLaserSetActiveRotationFn>(method)(entity, delay, angleDegrees,
                                                                    rotationSpeed, timeoutComplete);
    return 0;
}

int EntityToEffect(lua_State* state) {
    // `Entity_Effect` 的 `Type` 是 **1000**（`kEntityTypeEffect`，不是 1..n 那个序列）。
    return PushEntityDowncast(state, "Entity:ToEffect", kEntityEffectVtableOffset, true,
                              kEntityTypeEffect);
}

int EntityToKnife(lua_State* state) {
    return PushEntityDowncast(state, "Entity:ToKnife", kEntityKnifeVtableOffset, true,
                              kEntityTypeKnife,EntityView::Knife);
}

// `Entity:GetData()`（批次 4）：引擎**没有**这个字段（三条独立否定证据见
// `docs/问题与解决记录.md`），所以由 Runtime 自管一张"与实体同生命周期"的 Lua 表。
// 同一实体（房间 epoch + 指针 + 生成帧 全同）**每次都拿到同一张表**，也就是说
// `entity:GetData()[k] = v` 写进去的东西下次读还在 —— 这正是 EID 的用法
// （`features/eid_api.lua:2219`/`2229`）。
//
// 与 PC 的差异写在 `PushEntityDataTable` 的注释里（换房间会让旧的表失效）。
// `Entity:ToFamiliar()`（批次 9）：PC 在**基类** `Entity` 上提供它，跟班返回 `EntityFamiliar`、
// 其它实体返回 nil。EID 用它把跟班从候选实体里挑出来。
//
// 判据与 `Entity:ToPickup()` 同一形态（两条都要求 vptr **精确**相等，避免把别的派生类当跟班）：
//   * `Type == ENTITY_FAMILIAR(3)`；
//   * `*(u64*)entity == base + kEntityFamiliarVtableOffset`。
// vtable 偏移的证据：符号表里 `_ZTVN15IsaacRepentance15Entity_FamiliarE` @ `0xA35718`，
// 加 `0x10`（跳过 offset-to-top 与 typeinfo 两个表头字）⇒ `0xA35728`；同一条规则在既有的
// `Entity_Player`（符号 `0xA37100` → 常量 `0xA37110`）与 `Entity_Pickup`（`0xA36E18` → `0xA36E28`）
// 上已经对过两次，互为交叉验证。
//
// 视图用 `Entity` 基类元表：我们目前没有 `EntityFamiliar` 专属元表，而 PC 里跟班的方法绝大部分
// 继承自 `Entity`；返回 nil 会让 EID 的筛选取不到跟班，返回基类视图至少语义正确。
int EntityToFamiliar(lua_State* state) {
    RecordFilterChain(6U);
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Entity:ToFamiliar accepts no arguments");
    }
    // ★ 批次 330（2026-10-03）：判据抽成 `ValidatedEntityFamiliar`（原来这里是就地写死的四行，
    //   现在与 `FieldReceipt::EntityFamiliar`（引擎方法行的接收者）**共用同一份**）。
    const std::uintptr_t entity = ValidatedEntityFamiliar(handle);
    if (entity == 0) {
        PushNil(state);
        return 1;
    }
    // ★★ 批次 330：改压 **`EntityFamiliar` 自己的元表**（此前是基类 `Entity` 元表）——
    //    不这么改，本批接上的 `FollowParent` / `AddToFollowers` 就**没有地方挂**：
    //    `IndexEntity` 先查本视图元表的 `__methods`、查不到才回落 `Entity`；
    //    压基类元表 ⇒ 模组的 `familiar:FollowParent()` 仍然 "attempt to call a nil value"。
    //    ★ 字段不受影响：`EntityView::Familiar` 的字段分派仍走 `else` 分支落到 `Entity` 的
    //    字段表（与 `EntityTear`/`EntityLaser`/`EntityNPC` 同一形态）⇒
    //    EID 的 `wisp:ToFamiliar().Player`（批 9 起就在用）照旧。
    PushEntityHandle(state, entity, kEntityFamiliarMetatable);
    return 1;
}

int EntityGetData(lua_State* state) {
    RecordFilterChain(0U);
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Entity:GetData accepts no arguments");
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    if (entity == 0) {
        // 过期/伪造句柄 → nil（EID 的判据就是 `entity:GetData() ~= nil`，见 `eid_api.lua:2218`）。
        PushNil(state);
        return 1;
    }
    return PushEntityDataTable(state, entity);
}

// `Entity:GetSprite()`（`Entity.md`）：PC 的 `Entity` 有一个 `Sprite` 成员，Lua 拿到的是它的
// 只读视图。Switch 版**没有** `GetSprite` 访问器符号 —— 因为这个成员是**内嵌对象**，访问器
// 会被内联成一句 `this + 偏移`（`docs/PC-Lua-API-对照清单.md:1449` 早就把这条判据写明了）。
//
// 偏移的定案证据在 `runtime_constants.hpp`（`kEntitySpriteOffset`）：`Entity::Entity()`
// 构造的就是 `this+0x50` 上的 `ANM2`，`Entity::Render()` 渲染的也是它，`Entity_Pickup::
// ReloadGraphics()` 给它换 spritesheet。
//
// 为什么必须有它：EID 的 `EID:IsAltChoice()`（`main.lua:216`）在**宝藏房**里对未拾取的底座调
// `pickup:GetSprite()`；缺了它就是 "attempt to call a nil value (method 'GetSprite')"，而那一句
// 在 `EID:OnRender()`（`main.lua:1312` 注册的 `MC_POST_RENDER`）里、整段没有 pcall，
// 于是**整个房间的描述渲染**都被打断。
//
// 所有权：交出去的 `Sprite` 句柄指向**引擎实体内部**的内存，所以它带
// `kSpriteSourceEngineEntity` 标记，`__gc` 不会析构/释放（见 `sprite_api.cpp`）；每次访问都会
// 重新校验这张实体还活着。
//
// 降级：拿不到实体（过期句柄 / 基址未发布）→ 返回 **nil**，不报错（与 `Entity:GetData()` 同一
// 口径）：报错会把整段描述渲染打断，而 nil 至少让 Mod 的 `if sprite then` 分支走另一条路。
int EntityGetSprite(lua_State* state) {
    RecordFilterChain(1U);
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Entity:GetSprite accepts no arguments");
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    if (entity == 0) {
        PushNil(state);
        return 1;
    }
    return PushEngineEntitySpriteHandle(state, engine_memory::AsObject(entity));
}

// `Entity_Player::HasCollectible(eCollectibleType, bool)`：模块内固定偏移，先确认那 4 字节可读，
// 读不到就说明基址不对，绝不能盲跳。ABI 与其它引擎方法一致（`x0 = this`、`w1 = id`、`w2 = bool`）。
std::uintptr_t HasCollectibleMethod() noexcept {
    // ★ 批次 428：这条**每秒被调约 4.5 万次**（API 层归因实测：Trinity 的 732 次/帧扫描）。
    //   两条判据（基址 + 可读）的结论只随**模块基址**变 ⇒ 交给 `EngineEntryAddressCached`
    //   把"已通过判据的地址"按基址记住；判据本身没有少做，只是结果不再每调用一次重算。
    static isaac::runtime::EngineEntrySlot slot{};   // 零初始化 ⇒ 不生成 __cxa_guard
    return isaac::runtime::EngineEntryAddressCached<IsEngineMemoryReadable>(
        slot, kEntityPlayerHasCollectibleOffset, 0);
}

// `Entity_Player::AddCollectible` 的地址：与 `HasCollectibleMethod` 同一种接法（模块基址 + 偏移），
// 但**多做一次入口指纹核对** —— 这个函数的调用会真的改变玩家状态，偏移一旦写错就会去调别的函数，
// 后果比"读到一个错值"严重得多；核对 4 字节的成本可以忽略。
std::uintptr_t AddCollectibleMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityPlayerAddCollectibleOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityPlayerAddCollectibleOffset;
    if (!IsEngineMemoryReadable(method, sizeof(std::uint32_t))) {
        return 0;
    }
    std::uint32_t entryWord = 0;
    if (!ReadEngine(method, &entryWord) ||
        entryWord != kEntityPlayerAddCollectibleEntryWord) {
        return 0;
    }
    return method;
}

// `ItemConfig::Item::IsAvailable(long, uint)` 的地址：模块基址 + 偏移，**调用前核对入口 4 字节**。
// 这条会真的去调引擎函数（`flags`/`this` 由我们给），偏移写错就会去调别的函数 ⇒ 指纹不是可选项。
std::uintptr_t ItemIsAvailableMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kItemConfigItemIsAvailableOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kItemConfigItemIsAvailableOffset;
    std::uint32_t entryWord = 0;
    if (!IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ||
        !ReadEngine(method, &entryWord) || entryWord != kItemConfigItemIsAvailableEntryWord) {
        return 0;
    }
    return method;
}

std::uintptr_t CardIsAvailableMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kItemConfigCardIsAvailableOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kItemConfigCardIsAvailableOffset;
    std::uint32_t entryWord = 0;
    if (!IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ||
        !ReadEngine(method, &entryWord) || entryWord != kItemConfigCardIsAvailableEntryWord) {
        return 0;
    }
    return method;
}

std::uintptr_t PillEffectIsAvailableMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kItemConfigPillEffectIsAvailableOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kItemConfigPillEffectIsAvailableOffset;
    std::uint32_t entryWord = 0;
    if (!IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ||
        !ReadEngine(method, &entryWord) || entryWord != kItemConfigPillEffectIsAvailableEntryWord) {
        return 0;
    }
    return method;
}

// 宿主侧注入实现的 `kind` 口径（0 = `Item`（带 flags）、1 = `Card`、2 = `PillEffect`）。
// （宿主实现指针必须定义在**使用它的 `Call*IsAvailable` 之前** —— 上面那次"定义放在
//  文件末尾、使用在前面"的直接后果就是 `use of undeclared identifier`。）
#if !defined(__SWITCH__)
ItemConfigIsAvailableHostImplementation g_ItemConfigIsAvailableHostImplementation = nullptr;
// 批次 241：`ItemConfig_Item:IsRune()` 的宿主缝（真机直读 `Card+0x58`，宿主没有引擎映像）。
ItemConfigCardIsRuneHostImplementation g_ItemConfigCardIsRuneHostImplementation = nullptr;
#endif

// ⚠️ 2026-09-17：这三条原来挤在一个 `CallItemConfigIsAvailable(method, entry, kind)` 里，
// 由**运行时的 `kind`** 在两条签名之间选（`if (kind == 0)` 走带 flags 的三参数、否则走无参）。
// 后果是**静态检查核不到**：ABI 体检无法确定"哪个偏移常量配哪份签名"（`Item` 与
// `Card`/`PillEffect` 的签名不同），这三条就一直是"没比过"。
// 现在按**引擎函数各拆一条**：每个偏移常量只对应一个调用点、一个转型 ⇒ 能被机器核对
// （见 `tools/engine_offset_abi_report.py` 的形态 E）。行为不变，语义也更直白：
// 条目的类别决定调哪个函数，而不是用一个整数中转。
bool CallItemIsAvailable(std::uintptr_t method, std::uintptr_t entry) {
#if defined(__SWITCH__)
    // `Item::IsAvailableEx(uint)`：x0 = 条目、x1 = flags（兼容层定义、已登记偏离）、
    // x2 = 0（反汇编里读到的四个分支都没用到第三个参数）。
    using ItemFn = bool (*)(void*, std::int64_t, std::uint32_t);
    return engine_call::AsFunction<ItemFn>(method)(engine_memory::AsObject(entry),
                                                   kItemIsAvailableFlags, 0);
#else
    static_cast<void>(method);
    const ItemConfigIsAvailableHostImplementation injected =
        g_ItemConfigIsAvailableHostImplementation;
    return injected != nullptr &&
           injected(0, engine_memory::AsObject(entry), kItemIsAvailableFlags);
#endif
}

// `Card::IsAvailable()`：无参（`x0` = 条目）。
bool CallCardIsAvailable(std::uintptr_t method, std::uintptr_t entry) {
#if defined(__SWITCH__)
    using NoArgFn = bool (*)(void*);
    return engine_call::AsFunction<NoArgFn>(method)(engine_memory::AsObject(entry));
#else
    static_cast<void>(method);
    const ItemConfigIsAvailableHostImplementation injected =
        g_ItemConfigIsAvailableHostImplementation;
    return injected != nullptr && injected(1, engine_memory::AsObject(entry), 0);
#endif
}

// `PillEffect::IsAvailable()`：与 `Card` 同一支（无参，宿主 `kind` = 2）。
bool CallPillEffectIsAvailable(std::uintptr_t method, std::uintptr_t entry) {
#if defined(__SWITCH__)
    using NoArgFn = bool (*)(void*);
    return engine_call::AsFunction<NoArgFn>(method)(engine_memory::AsObject(entry));
#else
    static_cast<void>(method);
    const ItemConfigIsAvailableHostImplementation injected =
        g_ItemConfigIsAvailableHostImplementation;
    return injected != nullptr && injected(2, engine_memory::AsObject(entry), 0);
#endif
}


#if !defined(__SWITCH__)
EntityPlayerHasCollectibleHostImplementation g_HasCollectibleHostImplementation = nullptr;
CurrentLanguageCodeHostImplementation g_CurrentLanguageCodeHostImplementation = nullptr;
// `g_ItemConfigIsAvailableHostImplementation` 定义在它的使用点之前（见 `ItemIsAvailableMethod` 之后）。
#endif

bool CallEntityPlayerHasCollectible(std::uintptr_t method, std::uintptr_t entity,
                                    std::uint32_t collectibleId, bool ignoreModifiers) {
#if defined(__SWITCH__)
    // 原生符号：`_ZNK15IsaacRepentance13Entity_Player14HasCollectibleENS_16eCollectibleTypeEb`
    // ⇒ `(eCollectibleType, bool)`。第二个参数**原样透传**给引擎（PC 语义就是那个
    // `ignoreModifiers`），不做我们自己的解释 —— 这样"传什么"与 PC 完全一致。
    using HasCollectibleFn = bool (*)(void*, std::uint32_t, std::uint32_t);
    return engine_call::AsFunction<HasCollectibleFn>(method)(
        engine_memory::AsObject(entity), collectibleId, ignoreModifiers ? 1U : 0U);
#else
    // 宿主构建没有引擎映像，也无法把一个 C++ 函数放到 `base + 0x27D3F4`，所以那一条 `bl` 由
    // 测试注入的实现顶替（声明见 `isaac_api.hpp`）。宿主仍然能验证"vptr 校验先于调用""参数就是
    // `this` 与 id""返回值原样变成 Lua 布尔"；设备构建不存在这条通路。
    static_cast<void>(method);
    const EntityPlayerHasCollectibleHostImplementation injected = g_HasCollectibleHostImplementation;
    return injected != nullptr &&
           injected(engine_memory::AsObject(entity), collectibleId, ignoreModifiers);
#endif
}

// 拿不到实体或拿不到方法时返回 false（PC 的返回值是布尔，`if player:HasCollectible(x) then`
// 在 Mod 里到处都是，报错会直接打断调用方；"没有这一件"是最安全的降级）。
int EntityPlayerAddCollectible(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    const int argumentCount = lua_gettop(state);
    // CustomHealthAPI forwards the optional Repentance+ pool argument even on
    // Repentance. This engine consumes the original five arguments only.
    if (argumentCount < 2 || argumentCount > 7 || !isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(
            state,
            "EntityPlayer:AddCollectible accepts (type[, charge[, force[, slot[, varData]]]])");
    }
    const lua_Integer type = lua_tointegerx(state, 2, nullptr);
    if (type < 0 || static_cast<std::uint64_t>(type) > std::numeric_limits<std::uint32_t>::max()) {
        // ★★ 2026-10-07（批次 404）：越界**不再抛错**，改成"安全 no-op"（压 `false`，与批次 398 的
        //    `EntityPlayerHasCollectible` 逐字同形）。
        //    为什么：模组里常见的写法是 `Isaac.GetItemIdByName("自定义道具")` —— 快照表 + 追加层都查不到
        //    时它给 **-1**，紧接着就喂给 `AddCollectible`。我们一抛错就被派发器**静默摘掉整条回调登记**
        //    （真机实测：`Trinity/main.lua:67`，报
        //    `EntityPlayer:AddCollectible type is outside uint32 range` —— 本批 404 的起因）。
        //    PC 契约（`tools/pc_contract_docs/EntityPlayer.md:137-139`）只写
        //    `void AddCollectible(CollectibleType Type, ...)`，**没有"越界报错"这一说**；项目既有口径
        //    （`runtime/tests/test_id_argument_policy.py` 表头）也是"参数是枚举 id 时不钉取值范围、
        //    越界在 PC 上是'没有'（nil / 0 / false）"。
        //    ⇒ 与"拿不到实例 / 拿不到方法"的早退分支同一口径：调用方 `if player:AddCollectible(...)`
        //    拿到 `false`，而回调留存。★ 计数：本 TU 没有 per-handler 计数设施，故与 398 一样以
        //    "`false` 这个可观测结果"为准，不另立计数器（避免造一条没人读的死代码）。
        lua_pushboolean(state, 0);
        return 1;
    }
    const lua_Integer charge = argumentCount >= 3 ? lua_tointegerx(state, 3, nullptr) : 0;
    const bool force = argumentCount >= 4 && lua_toboolean(state, 4) != 0;
    // 默认槽位必须是 `ActiveSlot.SLOT_PRIMARY = 0`（PC 文档的默认值）。2026-09-14 真机定位到：
    // 这里原先是 `-1`，于是 `player:AddCollectible(628, 0, true)`（不写 slot）会把**主动道具**
    // 放进一个不存在的槽位 —— 引擎仍把它记进"拥有列表"（`HasCollectible` 变 true），但**不装备**，
    // 玩家在主动道具槽里看不到、也用不了。表现极具迷惑性：既不报错、也不是没生效。
    const lua_Integer slot = argumentCount >= 5 ? lua_tointegerx(state, 5, nullptr) : 0;
    const lua_Integer varData = argumentCount >= 6 ? lua_tointegerx(state, 6, nullptr) : 0;
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    const std::uintptr_t method = AddCollectibleMethod();
    if (entity == 0 || method == 0) {
        // 实例或能力不可用时**保守返回 false**（与同族接口同一口径）：报错会摘掉整条回调。
        lua_pushboolean(state, 0);
        return 1;
    }
    using AddCollectibleFn = std::uint32_t (*)(std::uintptr_t, std::uint32_t, std::uint32_t,
                                               std::uint32_t, std::uint32_t, std::uint32_t);
    engine_call::AsFunction<AddCollectibleFn>(method)(
        entity, static_cast<std::uint32_t>(type), static_cast<std::uint32_t>(charge),
        force ? 1U : 0U, static_cast<std::uint32_t>(slot),
        static_cast<std::uint32_t>(varData));
    // 返回值取"**实际结果**"：调用后用 `HasCollectible`（同族、已实现的接口）复核一次。
    // 引擎那一层的返回类型没有从反汇编确认过，与其信寄存器里的值，不如用效果说话 ——
    // 参数顺序万一写错，这里会如实暴露成 false。
    const std::uintptr_t hasCollectible = HasCollectibleMethod();
    bool collected = false;
    if (hasCollectible != 0) {
        using HasCollectibleFn = std::uint32_t (*)(std::uintptr_t, std::uint32_t, std::uint32_t);
        collected =
            engine_call::AsFunction<HasCollectibleFn>(hasCollectible)(
                entity, static_cast<std::uint32_t>(type), 0U) != 0;
    }
    lua_pushboolean(state, collected ? 1 : 0);
    return 1;
}

// `EntityPlayer:AddCoins(int Amount)` —— PC 文档：`EntityPlayer.md` 的 `AddCoins ( int Amount )`，
// 返回类型 void（所以成功后**不压任何返回值**，与 PC 的 `player:AddCoins(5)` 语义一致）。
//
// 为什么走引擎函数而不是直接写 `EntityPlayer + 0x16E0`（那个字段我们已取证）：
// 引擎这一条会自己**夹到上限**（99，拥有某件收藏品时 999），并且**触发副作用**
// （`consumable_count_changed(1)` + HUD 第二屏刷新）。直接写字段的话，一是要自己实现夹取
// （漏了就写出一个显示不出来的金币数），二是 HUD 不会刷新 —— 那会让"模组改了钱但界面没变"
// 变成一个假的缺陷报告。PC 侧 `AddCoins` 走的也是引擎同一个函数。
int EntityPlayerHasCollectible(lua_State* state) {
    RecordApiSequenceSecondary(0U);
    auto* handle = CheckEntityHandle(state, 1);
    // PC 签名：`HasCollectible(CollectibleType, bool ignoreModifiers = false)`。
    // 第二个参数是**可选**的（EID 会传 `true`，见 `features/eid_api.lua:3004`）；
    // 只接受布尔或 nil（nil 等同缺省 false），给别的类型就报清楚 —— 不猜、不静默转换。
    // ⚠️ 注意 `f(a, nil)` 在 Lua 里 top 也是 3（nil 会被真的传进来），所以 nil 必须显式放行。
    const int argumentCount = lua_gettop(state);
    const int thirdType = argumentCount == 3 ? lua_type(state, 3) : LUA_TNIL;
    if ((argumentCount != 2 && argumentCount != 3) || !isaac::runtime::IsIntegerArgument(state, 2) ||
        (argumentCount == 3 && thirdType != LUA_TBOOLEAN && thirdType != LUA_TNIL)) {
        return luaL_error(state,
                          "EntityPlayer:HasCollectible accepts a collectible id and an optional "
                          "boolean (ignoreModifiers)");
    }
    const bool ignoreModifiers =
        argumentCount == 3 && thirdType == LUA_TBOOLEAN && lua_toboolean(state, 3) == 1;
    const lua_Integer requested = lua_tointegerx(state, 2, nullptr);
    if (requested < 0 ||
        static_cast<std::uint64_t>(requested) > std::numeric_limits<std::uint32_t>::max()) {
        // ★★ 2026-10-07（批次 398）：越界**返回 `false`，不再抛错**。
        // 为什么改：这是模组里的常见写法 —— `Isaac.GetItemIdByName("自定义道具")` 在
        // "道具有、但我们的快照表里查不到"时给 **-1**，紧接着就喂给 `HasCollectible`。
        // 抛错会被派发器**静默摘掉整条回调登记**（真机实测：`Trinity/main.lua:545`，
        // 报 `collectible id is outside uint32 range`）。
        // PC 契约（`tools/pc_contract_docs/EntityPlayer.md:1346`）只写
        // `boolean HasCollectible(CollectibleType Type, boolean IgnoreModifiers = false)`，
        // **没有"越界报错"这一说**；而"玩家没有这件道具"的答案本来就是 `false`。
        lua_pushboolean(state, 0);
        return 1;
    }
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    const std::uintptr_t method = HasCollectibleMethod();
    if (entity == 0 || method == 0) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const bool collected = CallEntityPlayerHasCollectible(
        method, entity, static_cast<std::uint32_t>(requested), ignoreModifiers);
    lua_pushboolean(state, collected ? 1 : 0);
    return 1;
}


// `EntityPlayer:GetData()`：批次 2 起它返回 nil（"ModData 结构还没有证据"），**批次 4 起
// 返回 Runtime 自管的那张表** —— EID 真的往它里面写（`features/eid_api.lua:2229`：
// `entity:GetData()[str] = value`），返回 nil 会让 EID 的实体数据通路整条失效。
// 同一个实体每次都拿到**同一张**表；与 PC 的差异见 `PushEntityDataTable` 的注释。
int EntityPlayerGetData(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:GetData accepts no arguments");
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    if (entity == 0) {
        PushNil(state);
        return 1;
    }
    return PushEntityDataTable(state, entity);
}

// `EntityPlayer:GetOtherTwin()`（批次 3）：PC 文档（`EntityPlayer.md:1172`）说只有
// 双人角色/多形态角色才有"另一个"（Jacob↔Esau、T.Forgotten↔T.Soul、T.Lazarus+Birthright）。
// **真机单人场景返回 nil** —— EID 的写法是 `p:GetOtherTwin() or p`（`main.lua:1072`）
// 与 `{ EID.player, EID.player:GetOtherTwin() }`（`main.lua:1075`），nil 正好是它期望的
// "没有另一个"；返回 self 反而会让 EID 把同一个玩家当两个人处理。
//
// 为什么现在不做真实现：要判"有没有 twin"必须先定位 `Entity_Player` 的分身指针
// （`+0x2460`/`+0x2580`/`+0x2588` 这几个在 `SetControllerIndex` 里出现过，但那是**传播**
// controller index 用的，不能推断它们是 twin），再判断 twin 的 vptr 与类型；本轮没有那份证据，
// 所以按"单人 nil"如实降级，并在报告里列为未实现。
// 2026-10-09更正：上面的未定位记录保留；配对字段现由init_twin及MergeTwins确证。
std::uintptr_t ReadPlayerTwin(std::uintptr_t player) noexcept {
    std::uintptr_t other = 0;
    return player != 0 && ReadEngine(player + kEntityPlayerTwinOffset, &other) &&
                   IsEntityPlayer(other) ? other : 0;
}

int EntityPlayerGetOtherTwin(lua_State* state) {
    auto* handle = static_cast<EntityHandle*>(luaL_checkudata(state, 1, kEntityPlayerMetatable));
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:GetOtherTwin accepts no arguments");
    }
    const auto other = ReadPlayerTwin(ValidatedEntityPlayer(handle));
    if (other == 0) { PushNil(state); return 1; }
    PushEntityHandle(state, other, kEntityPlayerMetatable);
    return 1;
}


// `EntityPlayer:GetEffectiveMaxHearts()`：**红心容器**（`+0x16B8`，半心为单位）加上
// **2 × 骨心**（`+0x2450`）—— 与引擎自己的 `Entity_Player::GetEffectiveMaxHearts()`
// （`0x27E8AC`）逐分支一致：当 `PlayerType <= 0x28` 且 `(1 << PlayerType)` 命中掩码
// `0x11883021410`（???/The Lost/Black Judas/The Soul/T.Judas/T.???/T.Lost/T.Forgotten/
// T.Bethany/T.Soul）时**只**返回红心容器。偏移与掩码的出处见 `runtime_constants.hpp`。
//: 批次 299 从 `GetEffectiveMaxHearts()` 里**抽出来的共享判据**（"判据只有一份"）：
//: `Entity_Player` 的**有效最大红心**（半心单位）= 红心容器 + 2×骨心；**但"骨心不计"的
//: 那些玩家类型只算容器**（掩码 `kEntityPlayerBoneHeartlessTypeMask`）。
//: 读不出来 ⇒ 返回 false（调用方各自决定降级值）。
[[nodiscard]] bool ReadEffectiveMaxHearts(std::uintptr_t entity, std::int64_t* value) noexcept {
    if (entity == 0 || value == nullptr) {
        return false;
    }
    std::uint32_t containers = 0;
    if (!ReadEngine(entity + kEntityPlayerRedHeartContainersOffset, &containers)) {
        return false;
    }
    std::int64_t total = static_cast<std::int64_t>(containers);
    std::uint32_t playerType = 0;
    bool countsBoneHearts = true;
    if (ReadEngine(entity + kEntityPlayerTypeOffset, &playerType) &&
        playerType <= kEntityPlayerMaximumTypeForBoneHearts) {
        countsBoneHearts =
            (kEntityPlayerBoneHeartlessTypeMask & (1ULL << playerType)) == 0;
    }
    std::uint32_t boneHearts = 0;
    if (countsBoneHearts && ReadEngine(entity + kEntityPlayerBoneHeartsOffset, &boneHearts)) {
        total += static_cast<std::int64_t>(boneHearts) * 2;
    }
    *value = total;
    return true;
}

int EntityPlayerGetEffectiveMaxHearts(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:GetEffectiveMaxHearts accepts no arguments");
    }
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    std::int64_t total = 0;
    if (!ReadEffectiveMaxHearts(entity, &total)) {
        PushZero(state);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(total));
    return 1;
}

// `EntityPlayer:HasFullHearts()`（`EntityPlayer.md:1357`，语料 6 处 / 1 个模组）。
//
// PC 侧绑定本体（`0x6B1B40`）先调一个**按玩家类型的跳表**（助手 `0x78CDC0`）拿到分类：
//   * 分类 1 或 2 ⇒ `[+0x1294] >= [+0x1290]`（**骨心不算**）；
//   * 其余（含"类型不在 4..0x28 范围内"）⇒ `[+0x1294] >= [+0x1290] + 2*[+0x1CA8]`。
// ★★ **那张跳表的输出集合与既有的 `kEntityPlayerBoneHeartlessTypeMask` 逐位相等**
//   （批次 299 从 PC 的 37 字节表 `0x78CE0C` 独立解出来对照，零差异）⇒ 判据与既有的
//   `EntityPlayer:GetEffectiveMaxHearts()` **完全是同一件事**：
//     `当前红心 >= 有效最大红心`
//   ⇒ 这里直接复用 `ReadEffectiveMaxHearts`，**不**再抄一份掩码逻辑（判据只有一份）。
//
// 降级：接收者不是玩家 / 读不到 ⇒ **false**（PC 返回 boolean；报错或给 nil 会把
// 模组的 `if p:HasFullHearts() then` 变成异常或假值，都比"答 false"糟）。
int EntityPlayerHasFullHearts(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:HasFullHearts accepts no arguments");
    }
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    std::uint32_t hearts = 0;
    std::int64_t maximum = 0;
    if (entity == 0 || !ReadEngine(entity + kEntityPlayerHeartsOffset, &hearts) ||
        !ReadEffectiveMaxHearts(entity, &maximum)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    lua_pushboolean(state, static_cast<std::int64_t>(hearts) >= maximum ? 1 : 0);
    return 1;
}



// 读一个 `Entity_Player` 无符号整数字段并压栈，读不出来时给 0。**恒返回数字**：
// EID 把主动道具/饰品/婴儿皮肤的结果直接拿去比较或当表键（`main.lua:1076` 那一类写法），
// nil 会变成 "attempt to compare/index a nil value"。
void PushPlayerUintOrZero(lua_State* state, const EntityHandle* handle, std::uintptr_t offset) {
    std::uint32_t value = 0;
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    if (entity != 0 && ReadEngine(entity + offset, &value)) {
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return;
    }
    PushZero(state);
}

// `EntityPlayer:GetActiveItem(ActiveSlot = SLOT_PRIMARY)`（批次 4）：PC 文档
// （`EntityPlayer.md:763`）"Returns the currently held item. Returns `0` when no item is held."
// 偏移 `+0x1964 + slot*0x1C`（`docs/问题与解决记录.md` 批次 4 的小偏移表；同一组里
// `+0x1968`/`+0x196C`/`+0x197C` 是充能/第二充能/最大充能，本批次**不**暴露它们）。
//
// 槽号：PC 的 `ActiveSlot` 0..3（`SLOT_PRIMARY`/`SLOT_SECONDARY`/`SLOT_POCKET`/`SLOT_POCKET2`）。
// 我们不复制"越界自动夹到 0"这种行为：槽号非整数或为负 → 0（"没有道具"）；槽号过大
// （≥ kEntityPlayerMaximumActiveSlots）→ 0，**不去读一个可能落在别的字段上的地址**。
constexpr lua_Integer kEntityPlayerMaximumActiveSlots = 4;

int EntityPlayerGetActiveItem(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    const int argumentCount = lua_gettop(state);
    if (argumentCount > 2) {
        return luaL_error(state, "EntityPlayer:GetActiveItem accepts an optional active slot");
    }
    lua_Integer slot = 0;
    if (argumentCount == 2 && !ReadIntegerArgument(state, 2, &slot)) {
        PushZero(state);
        return 1;
    }
    if (slot < 0 || slot >= kEntityPlayerMaximumActiveSlots) {
        PushZero(state);
        return 1;
    }
    static_cast<void>(PushPlayerUintOrZero(
        state, handle,
        kEntityPlayerActiveItemOffset +
            static_cast<std::uintptr_t>(slot) * kEntityPlayerActiveItemStride));
    return 1;
}

// `EntityPlayer:GetActiveCharge(ActiveSlot = SLOT_PRIMARY)`（批次 296，2026-10-03）：3 处 / 1 个模组
// （`Trinity/main.lua:252/272/817`）。
//
// PC 契约 `tools/pc_contract_docs/EntityPlayer.md:757` 是
// `int GetActiveCharge ( ActiveSlot ActiveSlot = ActiveSlot.SLOT_PRIMARY )`。
// PC 的绑定本体 @ `0x4F3F30` 只有四条指令（`tools/pc_exe_binding.py GetActiveCharge --disasm`）：
//     `mov edx,[ebp+8]`（槽位）→ `add edx,0xBE` → `lea eax,[8*edx]; sub eax,edx`（= `28*edx`）
//     → `mov eax,[ecx+4*eax]` —— 即 `this + 0x1C*(槽位+190)`，而 `0x1C*190 = 0x14C8`。
// ⇒ PC 的**元素布局**是 `{主动道具指针 @ +0, 充能 @ +4, …}`、步长 `0x1C`、槽位 0 的元素基址 `0x14C4`。
//
// ★ Switch 侧的**具名**证据（不是"照 PC 平移"）：
//   * 写入方 `Entity_Player::SetActiveCharge(int,int) @ 0x27F984` 里
//     `0x27F9AC mov w9,#0x1C` + `0x27F9B0 umaddl x9,w2,w9,x19`（`x9 = this + 0x1C*槽位`）→
//     `0x27FA54 add x27,x9,x10`（`x10 = 0x1968`）→ `0x27FAEC str w8,[x27]` 写**主充能**
//     （值 = `min(实参, GetActiveMaxCharge(槽位))`，见 `0x27FAE0 subs` + `0x27FAE8 csel`）、
//     `0x27FA58 add x26,x9,x12`（`x12 = 0x196C`）→ `0x27FAF8 str w9,[x26]` 写溢出充能。
//   * 读者 `Entity_Player::GetTotalActiveCharge(int) @ 0x29B43C`：
//     `0x29B454 smaddl x8,w1,w8,x0`（`w8 = 0x1C`）→ `0x29B458 ldr w10,[x8,#0x1968]` +
//     `0x29B45C ldr w8,[x8,#0x196C]` 然后两者相加 ⇒ 两格合起来才是"总充能"。
//   * 同一个元素的 `+0` 格（`0x1964`）**早就有**（`kEntityPlayerActiveItemOffset`，`GetActiveItem`
//     已在用；`0x27FA70 ldr w1,[x8,#0x1964]` 把它喂给 `ItemConfig::GetCollectible`）
//     ⇒ 「`GetActiveCharge` = 同一元素的 `+4`」有**同一个数组的既有消费方**做交叉印证。
// ★ 为什么取 `0x1968` 而不是 `0x196C`：PC 的 `GetActiveCharge` 读的是元素 `+4`（= `0x14C8`），
//   Switch 元素 `+4` = `0x1968`；两边的**元素内相对位置相同**（都是 `+4`），步长也相同（`0x1C`），
//   但基址数值不同（`0x14C4` vs `0x1964`）—— 这正是"相对顺序可印证、偏移不许平移"。
// ★ 降级档：PC 的绑定本体**没有**任何空指针/边界检查（无条件读），所以这里没有"照抄的降级值"；
//   我们沿用同族 `GetActiveItem` 的边界口径（槽位非整数/为负/越界 ⇒ 0，**不去读可能落在别的
//   字段上的地址**），句柄失效时 `PushPlayerUintOrZero` 也压 0 —— 而 0 正是"没有充能"。
int EntityPlayerGetActiveCharge(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    const int argumentCount = lua_gettop(state);
    if (argumentCount > 2) {
        return luaL_error(state, "EntityPlayer:GetActiveCharge accepts an optional active slot");
    }
    lua_Integer slot = 0;
    if (argumentCount == 2 && !ReadIntegerArgument(state, 2, &slot)) {
        PushZero(state);
        return 1;
    }
    if (slot < 0 || slot >= kEntityPlayerMaximumActiveSlots) {
        PushZero(state);
        return 1;
    }
    static_cast<void>(PushPlayerUintOrZero(
        state, handle,
        kEntityPlayerActiveItemChargeOffset +
            static_cast<std::uintptr_t>(slot) * kEntityPlayerActiveItemStride));
    return 1;
}

// `EntityPlayer:GetTrinket(int TrinketIndex)`（批次 4）：PC 文档（`EntityPlayer.md:1315`）
// "Gets the ID of the trinket the player is holding in the given trinketslot (0 or 1).
// Returns `0` when no trinket is held in the given slot."
// 偏移 `+0x1AB0 + slot*4`，**2 槽**；槽号越界返回 0（任务给定的口径，与 PC 不同：
// PC 越界行为没有文档，这里选择"不读越界地址"）。
int EntityPlayerGetTrinket(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    lua_Integer slot = 0;
    if (lua_gettop(state) != 2 || !ReadIntegerArgument(state, 2, &slot)) {
        return luaL_error(state, "EntityPlayer:GetTrinket accepts one trinket slot");
    }
    if (slot < 0 || static_cast<std::uint64_t>(slot) >= kEntityPlayerTrinketSlotCount) {
        PushZero(state);
        return 1;
    }
    PushPlayerUintOrZero(
        state, handle,
        kEntityPlayerTrinketOffset + static_cast<std::uintptr_t>(slot) * sizeof(std::uint32_t));
    return 1;
}

// --- 批次 6：EID 逐帧调用的一批 `EntityPlayer` 成员（安全默认值）-----------------
//
// 背景（真机报告 `01789210946`）：EID 的 update 回调里
// `features/eid_api.lua:2606` 写的是 `EID.PlayerHeldPill[i] = player:GetPill(0)`。
// 我们没实现 `GetPill` 时，这一句是 "attempt to call a nil value (method 'GetPill')"，
// 于是**整条 update 回调**抛错、被派发器静默摘除 —— 从此 EID 再也不更新、屏幕全空，
// 而游戏不崩。这类缺口的代价因此远大于"少一个数据"。
//
// 所以这一批的口径是：**先把名字补齐并返回类型正确的默认值**，让 EID 的调用链活下来；
// 具体数值/对象等引擎字段偏移定位后再逐个换成真实现（成熟度在 Catalog 里标 `Experimental`）。
// 默认值的选择规则：
//   * 返回"库存计数/等级"一类数字 → `0`（PC 在"没有"时就是 0，EID 全是算术与比较）；
//   * 返回"是否有/是不是"一类布尔 → `false`；
//   * 返回"可能为 nil 的对象或 id"（`GetPill`/`GetCard`/`GetMainTwin`/各 `*RNG`/`GetName`）
//     → `nil`。这几个在 PC 上本来就是"没有就是 nil"，EID 也按 nil 判（例如
//     `if player:GetMainTwin() then`），比编一个假对象安全。
//
// 参数检查沿用本文件既有写法：参数个数不符即 `luaL_error`（与 PC 的 Lua 报错行为一致，
// 也让 Mod 作者的笔误可见），但**缺数据不报错**。
namespace {

// 只做参数检查：这一批默认值都不依赖引擎读数。
bool EntityPlayerProbeNoArguments(lua_State* state, const char* name) {
    static_cast<void>(CheckEntityHandle(state, 1));
    if (lua_gettop(state) != 1) {
        luaL_error(state, "%s accepts no arguments", name);
        return false;
    }
    return true;
}

// 参数是**枚举 id**（不是槽位）的那一族：只钉"必须是一个整数"，**不钉取值范围**。
//
// 证据（2026-09-18 真机，可调用性探针撞出来的）：探针按 PC 文档调用
// `player:GetCollectibleRNG(1)`（1 = 洋葱），我们把它当槽位卡在 `[0, 0]` ⇒ 抛 Lua 错误。
// PC 文档快照里的签名是**枚举 id**（`analysis/isaacdocs-snapshot/docs/EntityPlayer.md`）：
//   * `RNG GetCollectibleRNG(CollectibleType ID)`（:903）
//   * `RNG GetTrinketRNG(TrinketType TrinketID)`（:1331）
//   * `RNG GetCardRNG(Card ID)`（:888）
//   * `RNG GetPillRNG(PillEffect ID)`（:1191）
//   * `bool HasTrinket(TrinketType TrinketID)`、`bool HasPlayerForm(PlayerForm)`、
//     `int GetPlayerFormCounter(PlayerForm)`
// 这些 id 空间里有上千个值（饰品、形态），"看起来像槽位"的上限写法会让**合法调用**抛错；
// 而回调里抛错会被派发器**静默摘掉整条回调**（现象：那个模组的某块功能整个不工作）。
// 越界在 PC 上不是错误，而是"没有"（nil / 0 / false）。
//
// 与 `GetCard`/`GetPill` 的槽位口径（下面那条注释）是**两条不同的规则**，别混：
// 那两条的参数在 PC 上确实是槽位（`GetCard(int SlotId)`），所以那里只钉整数、越界走"没有"；
// 这一族连"上限"都不存在，写上限就是错。
bool EntityPlayerProbeIdArgument(lua_State* state, const char* name,
                                 bool allowTrailingBoolean = false,
                                 lua_Integer* parsed = nullptr) {
    static_cast<void>(CheckEntityHandle(state, 1));
    lua_Integer value = 0;
    const int top = lua_gettop(state);
    // ★ 批次 130（2026-09-25）：`allowTrailingBoolean` 给 `HasTrinket` 用 —— PC 的签名是
    // `HasTrinket(TrinketType Type, boolean IgnoreModifiers = false)`，**第二个参数可省**。
    // 旧实现要求"正好一个参数" ⇒ 按 PC 写法传两个会抛 Lua 错误、整条回调被派发器静默摘掉。
    // 证据链（不是推测）：语料里的 `analysis/mod-corpus/TBOI_Better-Voiding/main.lua:508`/`762`
    // 就是 `playerEntity:HasTrinket(TrinketType.TRINKET_YOUR_SOUL, false)`。
    // 这与上面那条"别把 id 当槽位卡范围"是同一族纪律：**不许比 PC 严**。
    const bool trailingBooleanAccepted =
        top == 3 && allowTrailingBoolean && lua_isboolean(state, 3);
    if ((!trailingBooleanAccepted && top != 2) || !ReadIntegerArgument(state, 2, &value)) {
        luaL_error(state, "%s accepts one integer id", name);
        return false;
    }
    if (parsed != nullptr) {
        *parsed = value;   // 批次 133：给 `HasTrinket` 用（它要拿这个 id 去比对饰品槽）
    }
    return true;
}

// `EntityPlayer:GetPoopSpell` 的参数（批次 130）：PC 的签名是 `GetPoopSpell(int Position)`，
// 而旧实现要求**无参** ⇒ 按 PC 写法传位置参数会抛 Lua 错误、那条回调被静默摘掉（同上，我们比 PC 严）。
// 现在接受"零个或一个整数"：那个值暂时没被用到（字段未定位 ⇒ 恒 0，见 `api_deviation.cpp`
// 的 `0x0E01003F`），但**调用形状**必须跟 PC 走 —— 否则一次合法调用就被判成错误。
bool EntityPlayerProbeOptionalIntegerArgument(lua_State* state, const char* name) {
    static_cast<void>(CheckEntityHandle(state, 1));
    const int top = lua_gettop(state);
    if (top == 1) {
        return true;
    }
    lua_Integer value = 0;
    if (top != 2 || !ReadIntegerArgument(state, 2, &value)) {
        luaL_error(state, "%s accepts at most one integer", name);
        return false;
    }
    return true;
}

// ★ 批次 177（2026-09-28）：这里原本有 `EntityPlayerProbePocketSlot` 与 `GetPill`/`GetCard`
//   两个手写处理器。它们已经**整段删除** —— 那两条 API 改走引擎方法数据行
//   （`kEntityPlayerEngineRows` 里的 `0x0E010030`/`0x0E010031`，`EngineCallShape::Int1`），
//   值直接来自 `Entity_Player::GetPill(int)`@`0x2E8D80` / `GetCard(int)`@`0x2E8D58`。
//
//   为什么删而不是留：留着它就意味着"引擎里有、我们还自己写一遍"（正是 2026-09-27 用户点名的
//   那个毛病），而且那两条手写的返回值恒 0 —— EID 口袋里真放了药丸/卡牌时**永远缺一条描述**。
//
//   那条**槽位口径的证据链仍然成立**、也仍然必须守（只是现在由数据行保证）：越界槽位在 PC 上
//   不是错误、而是"没有"，所以**不许给参数加范围校验**。证据（真机报告 `01789218953`／
//   `01789219353`）：EID 的 `features/eid_api.lua:1866` 写
//   `for j = 0, (EID.isRepentance and 3 or 1) do ... player:GetCard(j)`（`eid_data.lua` 的
//   `Pocket1..Pocket4` 同样问到 3）；旧实现把它当成"槽位必须落在 [0,1]"，`j = 2` 时抛
//   `EntityPlayer:GetCard accepts one slot in [0, 1]` ⇒ 派发器**静默摘除整条 update 回调**
//   （屏幕上什么都没有、游戏不崩）。PC 文档（`analysis/isaacdocs-snapshot/docs/EntityPlayer.md:882`）
//   的签名 `GetCard(int SlotId)` 返回 `Card`、默认值 `0` —— 同样没有"越界即错误"这一说。
//   ⇒ 数据行的 `argumentCount = 1` + `IntArgumentGuard::None` 正是这个口径。

} // namespace

int EntityPlayerGetMainTwin(lua_State* state) {
    if (!EntityPlayerProbeNoArguments(state, "EntityPlayer:GetMainTwin")) {
        return 0;
    }
    // ★ 批次 132（2026-09-25，**真机实测修正**）：PC 的语义**不是**"单人恒 nil"。
    // PC 文档 `tools/pc_contract_docs/EntityPlayer.md:1050-1057` 逐条写明：
    //   * Jacob / Esau → Jacob；被遗忘者 / 其魂 → 被遗忘者；
    //   * 双子拉撒路 / 其尸体 → **它们自己**（带长子名分时才给双子拉撒路）；
    //   * **When called on any other character, returns that character.** ⇒ **普通角色返回自己**。
    //
    // 旧实现无条件 `PushNil`（注释还写着"PC 亦然"）—— 那句话是错的，而且后果很重：
    // EID 拼"长子名分"描述时写 `player:GetMainTwin():GetPlayerType()`（`eid_modifiers.lua:420`），
    // 拿到 nil 再取方法 ⇒ 抛 `attempt to index a nil value` ⇒ 派发器把**整条 MC_POST_RENDER
    // 回调摘掉**，于是"站在长子名分旁边 EID 不显示信息"。
    // 实测证据：`dist/gdb-read-20260925-after-130-inrun.txt`（读数里那条错误与它的 owner 归属）。
    //
    // ⇒ 现在返回**玩家自己**（身份相等：`player:GetMainTwin() == player`）。普通角色与"多形态角色
    // 返回自己"这两类都对；只有"双子族的另一侧要拿到主身"那几类仍不对（Jacob-as-Esau、
    // 被遗忘者的魂、带长子名分的双子拉撒路），继续登记在 `api_deviation.cpp` 的 `0x0E010032`。
    // 2026-10-09更正：真实PC选择配对中signed index较小者，equal仍返回自己。
    auto* handle = static_cast<EntityHandle*>(luaL_checkudata(state, 1, kEntityPlayerMetatable));
    const auto player = ValidatedEntityPlayer(handle);
    if (player == 0) { PushNil(state); return 1; }
    const auto other = ReadPlayerTwin(player);
    std::int32_t selfIndex = 0, otherIndex = 0;
    if (other != 0 && ReadEngine(player + kEntityPlayerIndexOffset, &selfIndex) &&
        ReadEngine(other + kEntityPlayerIndexOffset, &otherIndex) && otherIndex < selfIndex) {
        PushEntityHandle(state, other, kEntityPlayerMetatable);
    } else {
        lua_pushvalue(state, 1);
    }
    return 1;
}

// 四条 `Get*RNG`（批次 195，2026-09-29）：**共享一份实现**。
//
// PC 语义：`EntityPlayer:GetCollectibleRNG(CollectibleType)` / `GetTrinketRNG(TrinketType)` /
// `GetCardRNG(Card)` / `GetPillRNG(PillEffect)` 返回**那个道具自己的 RNG 对象**
// （契约页 `tools/pc_contract_docs/EntityPlayer.md:903/1331/888/1191`；`GetCollectibleRNG` 那节
// 还有返回值原文 `:904 "Gets the RNG object of a collectible."`）。引擎里**没有**这四个名字
// （200168 条符号全表扫过，只有 `ProceduralItemInventory::GetRNG(int)` —— 那个忽略 id、只给第 0 个），
// 但数据就在实体里：四张 `std::vector<RNG>`（元素 16 字节），begin 分别在
// `+0x1BB0 / +0x1BC8 / +0x1BE0 / +0x1BF8`，**索引就是枚举 id 本身**。
// 证据（消费者 + 越界文案两重，逐条见 `runtime_constants.hpp`）：
//   collectible ← `PlayerManager::FirstCollectibleOwner @ 0x4417AC`（`0x8A4B78` "…out of bounds!"）；
//   trinket     ← `PlayerManager::FirstTrinketOwner @ 0x441A68`（`0x8B2559`）；
//   pill        ← `Entity_Player::UsePill @ 0x2DFC04`（`0x8933F3`，且 `0x2DFCFC` 就是
//                 `_pillRNGs[id].Random(50)` —— 索引即 PillEffect）；
//   card        ← `Entity_Player::UseCard @ 0x2E9040`（`0x891503`，`0x2E909C` 是 `.Random(97)`）。
//
// **越界与负数一律 `nil`**（不复制越界内存、不抛错）。理由三条：① 引擎自己对越界是"打一句
// `… out of bounds!` 然后照样算 `begin + id*16`"（负数走 UXTW 变成巨大偏移）—— 复刻它等于把
// "没有语义的字节"当成模组的随机源，比 nil 更难发现；② 项目既定口径是 id 族越界 = "没有"
// （见 `EntityPlayerProbeIdArgument` 上方那段）；③ 抛错会摘掉整条回调。
//
// 元素个数**运行时算**（`(end - begin) / 16`）：`Init` 按一个全局对象里的源列表长度建表，
// 没有静态上限可引（已知下界：card 表 > 45）。
//
// ★ 交回 Lua 的是**调用瞬间那 16 字节的快照**（与 `GridEntity:GetRNG` 完全同形、同一段 push 路径），
//   不是引擎里那颗 RNG 的活引用 —— PC 给的是引用。这条差异登记在 `api_deviation.cpp`
//   （`0x0E010033`~`0x0E010036`，性质 `design`）。
// 四条共用**取数**这一段（参数校验仍由各条自己写：`test_id_argument_policy.py` 按名字逐条钉
// "必须用 `EntityPlayerProbeIdArgument`"这条口径，所以那四句要各自出现在各自的处理器里）。
// 返回 1（压了一个值：RNG 句柄或 nil）。
// 2026-10-09：返回引擎活引用，旧快照描述保留为历史。
std::uintptr_t ResolvePlayerRngReference(const LuaRuntime::RngHandle* rng) noexcept {
    std::uintptr_t players = 0;
    std::size_t count = 0;
    if (ResolveEntityPlayerBegin(&players, &count) == 0) { return 0; }
    bool found = false;
    for (std::size_t i = 0; i < count; ++i) {
        std::uintptr_t current = 0;
        if (ReadEngine(players + i * sizeof(std::uintptr_t), &current) && current == rng->owner) {
            found = true; break;
        }
    }
    std::uint8_t exists = 0;
    if (!found || !IsEntityPlayer(rng->owner) ||
        !ReadEngine(rng->owner + kEntityExistsOffset, &exists) || exists == 0) { return 0; }
    std::uintptr_t begin = 0, end = 0;
    if (!ReadEngine(rng->owner + rng->offset, &begin) ||
        !ReadEngine(rng->owner + rng->offset + 8, &end) || begin == 0 ||
        begin != rng->container || end < begin ||
        (end - begin) % kEntityPlayerRngVectorStride != 0 ||
        rng->index >= (end - begin) / kEntityPlayerRngVectorStride) { return 0; }
    return begin + rng->index * kEntityPlayerRngVectorStride;
}

std::uintptr_t ResolveEntityRngReference(const LuaRuntime::RngHandle* rng) noexcept {
    std::uint8_t exists = 0;
    return IsEntityPointer(rng->owner) && ReadEngine(rng->owner + kEntityExistsOffset, &exists) &&
                   exists != 0 && rng->owner <= UINTPTR_MAX - rng->offset
               ? rng->owner + rng->offset : 0;
}

int EntityPlayerPushRngVectorEntry(lua_State* state, lua_Integer id,
                                   std::uintptr_t beginOffset) {
    auto* handle = static_cast<EntityHandle*>(luaL_checkudata(state, 1, kEntityPlayerMetatable));
    const std::uintptr_t player = ValidatedEntityPlayer(handle);
    if (player == 0 || id < 0) {
        PushNil(state);
        return 1;
    }
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!ReadEngine(player + beginOffset, &begin) || !ReadEngine(player + beginOffset + 8, &end) ||
        begin == 0 || end < begin || (end - begin) % kEntityPlayerRngVectorStride != 0) {
        PushNil(state);
        return 1;
    }
    const std::uintptr_t count = (end - begin) / kEntityPlayerRngVectorStride;
    if (static_cast<std::uint64_t>(id) >= count) {
        PushNil(state);
        return 1;
    }
    const std::uintptr_t element = begin + static_cast<std::uintptr_t>(id) *
                                               kEntityPlayerRngVectorStride;
    if (element > UINTPTR_MAX - kRngObjectSize ||
        !IsEngineMemoryReadable(element, kRngObjectSize)) {
        PushNil(state);
        return 1;
    }
    // 「拷 16 字节 + 挂 `kRngMetatable`」与 `GridEntity:GetRNG`（`remaining_api.cpp`）逐句同形。
    auto* rng = static_cast<LuaRuntime::RngHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RngHandle)));
    *rng = {};
    rng->resolver = ResolvePlayerRngReference;
    rng->owner = player;
    rng->container = begin;
    rng->offset = beginOffset;
    rng->index = static_cast<std::uintptr_t>(id);
    luaL_getmetatable(state, LuaRuntime::kRngMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int EntityPlayerGetCollectibleRNG(lua_State* state) {
    lua_Integer id = 0;
    if (!EntityPlayerProbeIdArgument(state, "EntityPlayer:GetCollectibleRNG", false, &id)) {
        return 0;
    }
    return EntityPlayerPushRngVectorEntry(state, id, kEntityPlayerCollectibleRngVectorOffset);
}

int EntityPlayerGetTrinketRNG(lua_State* state) {
    lua_Integer id = 0;
    if (!EntityPlayerProbeIdArgument(state, "EntityPlayer:GetTrinketRNG", false, &id)) {
        return 0;
    }
    return EntityPlayerPushRngVectorEntry(state, id, kEntityPlayerTrinketRngVectorOffset);
}

int EntityPlayerGetCardRNG(lua_State* state) {
    lua_Integer id = 0;
    if (!EntityPlayerProbeIdArgument(state, "EntityPlayer:GetCardRNG", false, &id)) {
        return 0;
    }
    return EntityPlayerPushRngVectorEntry(state, id, kEntityPlayerCardRngVectorOffset);
}

int EntityPlayerGetPillRNG(lua_State* state) {
    lua_Integer id = 0;
    if (!EntityPlayerProbeIdArgument(state, "EntityPlayer:GetPillRNG", false, &id)) {
        return 0;
    }
    return EntityPlayerPushRngVectorEntry(state, id, kEntityPlayerPillRngVectorOffset);
}

// `EntityPlayer:GetNumKeys` / `GetNumBombs` / `GetSoulCharge` / `GetBloodCharge` 共用的实现
// （2026-09-18）。四个的 PC 形状完全一样："无参数、返回 int"，只是读的字段不同。
//
// **为什么抽成一处**：在此之前这四个都是 `PushZero` 的**恒返回 0 假桩**，而假读数的危害
// 与"套装恒 0/3"同类 —— 模组拿它们做算术会得到错误结论，且不报错。四份几乎一样的代码
// 各自漂移正是这类问题的温床，所以这里只留一份。
//
// 降级口径与 `EntityPlayer:GetNumCoins` 一致：**压 0，不压 nil**
// （PC 的返回类型是数字，模组普遍直接参与算术；nil 会把整条回调摘掉，降级不该比原状更糟）。
//
// ⚠️ 这四条目前是**手写读字段**。它们本该走 `field_api.hpp` 的"数据行"机制（0 字节代码），
// 但那条路要求偏移进 `tools/layout_tables/*.json` 的布局表；本批先按 `GetNumCoins` 的既有形状落地，
// 后续"整体迁"那一轮再把这几个偏移一起迁进布局表（届时四条会变成四行数据）。
int PushEntityPlayerCounter(lua_State* state, const char* apiName, std::uintptr_t offset) {
    if (!EntityPlayerProbeNoArguments(state, apiName)) {
        return 0;
    }
    auto* handle = CheckEntityHandle(state, 1);
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    std::uint32_t value = 0;
    if (entity == 0 || !ReadEngine(entity + offset, &value)) {
        value = 0;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

int EntityPlayerGetNumKeys(lua_State* state) {
    // 字段 `+0x16D4` 的取证见 `runtime_constants.hpp` 的 `kEntityPlayerKeysOffset`
    // （`AddKeys` 的取-加-夹-存四条指令）。
    return PushEntityPlayerCounter(state, "EntityPlayer:GetNumKeys", kEntityPlayerKeysOffset);
}

int EntityPlayerGetNumBombs(lua_State* state) {
    // 字段 `+0x16DC`：2026-09-18 夜**更正**（原写 `+0x16E4`，抄的是 `AddBombs` 里
    // `PlayerType == PLAYER_BLUEBABY_B` 那条特殊分支）。三条独立证据（引擎自己的消耗品路径）：
    // `store_consumable_data` 把金币/钥匙/**炸弹**依次存为 `ConsumableData+0x00/+0x04/+0x08`；
    // `sync_consumable_counts` 按位同步 bit0/bit1/**bit2**；`AddBombs` 常规路径夹到 99 并镜像给同伴。
    // 完整证据写在 `runtime_constants.hpp` 的 `kEntityPlayerBombsOffset` 注释里。
    return PushEntityPlayerCounter(state, "EntityPlayer:GetNumBombs", kEntityPlayerBombsOffset);
}

int EntityPlayerGetNumCoins(lua_State* state) {
    if (!EntityPlayerProbeNoArguments(state, "EntityPlayer:GetNumCoins")) {
        return 0;
    }
    // 2026-09-18：从"恒返回 0 的桩"改成**真实现**。偏移 `Entity_Player + 0x16E0` 的取证见
    // `runtime_constants.hpp` 的 `kEntityPlayerCoinsOffset`（`AddCoins` 的取-加-夹-存四条指令）。
    //
    // 为什么必须改：原来那个 0 不是"安全默认值"而是**假读数** —— 模组拿它判"钱够不够"会永远
    // 得到"不够"，拿它判"要不要补钱"会每帧都补。`GetNumKeys`/`GetNumBombs`/`GetHearts` 等同族
    // 成员目前仍是桩（各自的偏移还没有同等强度的证据），那几条等取证到位再改。
    auto* handle = CheckEntityHandle(state, 1);
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    std::uint32_t coins = 0;
    if (entity == 0 || !ReadEngine(entity + kEntityPlayerCoinsOffset, &coins)) {
        // 读不到时压 **0**（不是 nil）：PC 的返回类型是数字，模组普遍拿它直接做算术
        // （`if player:GetNumCoins() < 5 then`），给 nil 会把那种写法变成
        // "attempt to compare nil with number" 并摘掉整条回调 —— 降级不该比原状更糟。
        // 这一档只在"句柄失效/内存不可读"时出现（真机在局内读得到），所以它不是假读数。
        coins = 0;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(coins));
    return 1;
}

// `EntityPlayer:GetHearts()`（批次 195，2026-09-29：**从恒 0 的占位改成真读数**）。
//
// PC 契约 `tools/pc_contract_docs/EntityPlayer.md:1004`（正文 `:1006`）：
// "Returns the amount of red hearts the player has inside their heart containers and bone hearts.
//  1 unit is half a heart." —— **单位是半心**。
// 字段 `+0x16BC` 的三条独立证据（`update_red_hearts` 的 `asr #1` 定单位、`AddHearts` 的
// "容器 + 2×骨心"上限、`SetFullHearts` 写容器数）逐条见 `runtime_constants.hpp` 的
// `kEntityPlayerHeartsOffset`。
//
// ★ 为什么必须真读：EID `features/eid_itemprediction.lua:366` 写的是
//   `player:GetHearts() <= 1`（与 `CanPickRedHearts()` 并列）—— 恒 0 会让那条判断**永远为真**，
//   于是"能不能捡红心"的预测恒错（不报错、只是结论反了）。
int EntityPlayerGetHearts(lua_State* state) {
    return PushEntityPlayerCounter(state, "EntityPlayer:GetHearts", kEntityPlayerHeartsOffset);
}


int EntityPlayerGetSoulCharge(lua_State* state) {
    // 字段取证见 `runtime_constants.hpp` 的 `kEntityPlayerSoulChargeOffset`（`AddSoulCharge @ 0x27FD98` 的取-加-夹-存 + 尾调 `update_soul_charges(int)`。）。
    return PushEntityPlayerCounter(state, "EntityPlayer:GetSoulCharge", kEntityPlayerSoulChargeOffset);
}

int EntityPlayerGetBloodCharge(lua_State* state) {
    // 字段取证见 `runtime_constants.hpp` 的 `kEntityPlayerBloodChargeOffset`（`AddBloodCharge @ 0x27F5B0` 的取-加-夹-存 + 尾调 `update_blood_charges(int)`。）。
    return PushEntityPlayerCounter(state, "EntityPlayer:GetBloodCharge", kEntityPlayerBloodChargeOffset);
}

// `EntityPlayer:GetPoopMana()`（批次 195：**从恒 0 改成真读数**）。
// PC 契约 `EntityPlayer.md:1210`（正文 `:1212`）"Returns how many poop consumables the player is
// currently holding"；字段 `+0x269C` 的取证（`AddPoopMana` 的取-加-夹-存 + `GetMaxPoopMana` 的同一组
// 上限分支）见 `runtime_constants.hpp` 的 `kEntityPlayerPoopManaOffset`。
int EntityPlayerGetPoopMana(lua_State* state) {
    return PushEntityPlayerCounter(state, "EntityPlayer:GetPoopMana", kEntityPlayerPoopManaOffset);
}

// `EntityPlayer:GetPoopSpell(int Position)`（批次 195：**从恒 0 改成真读数**）。
//
// PC 契约 `EntityPlayer.md:1217`（正文 `:1219`）"Returns the poop spell at the given position in
// the player's spell queue"；队列 = `Entity_Player + 0x26A0` 的 **6 格 u8**（`UsePoopSpell` 的
// "取队首 + 整体左移 + 末格清零"、`CheckPoopSpellQueue` 的循环上界 6、HUD 直接取 `+0x26A5`），
// 逐条见 `runtime_constants.hpp` 的 `kEntityPlayerPoopSpellQueueOffset`。
//
// 参数口径（批次 130 起）：PC 的签名带 `int Position` ⇒ 按"零个或一个整数"收（比 PC 严会把
// `GetPoopSpell()` 这种写法变成 Lua 错误）；**缺省位置 = 0**（PC 上 Position 是必填，但"队首"
// 是最自然的缺省，且不会因此少读数据）。
//
// ★ **越界自己夹 [0,5]**：引擎三处访问都是编译期常量下标、运行时从不检查（`Position = 6` 会读到
//   `+0x26A6` —— 同一次 8 字节清零的邻接字节）。PC 没给越界口径 ⇒ 给 0（= SPELL_NONE，"没有法术"）。
int EntityPlayerGetPoopSpell(lua_State* state) {
    // 批次 130：PC 的签名带 `int Position` ⇒ 用"零个或一个整数"的口径（旧实现要求无参，比 PC 严）。
    // 这个助手的**调用写法被 `runtime/tests/test_id_argument_policy.py` 按原文钉住**，所以
    // 位置值在它校验通过之后再取（`lua_gettop == 2` 时那个参数一定是一个整数）。
    if (!EntityPlayerProbeOptionalIntegerArgument(state, "EntityPlayer:GetPoopSpell")) {
        return 0;
    }
    const lua_Integer position = lua_gettop(state) == 2 ? lua_tointeger(state, 2) : 0;
    auto* handle = static_cast<EntityHandle*>(luaL_checkudata(state, 1, kEntityPlayerMetatable));
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    if (entity == 0 || position < 0 ||
        static_cast<std::uint64_t>(position) >= kEntityPlayerPoopSpellQueueSlots) {
        PushZero(state);
        return 1;
    }
    std::uint8_t value = 0;
    if (!ReadEngine(entity + kEntityPlayerPoopSpellQueueOffset +
                        static_cast<std::uintptr_t>(position),
                    &value)) {
        PushZero(state);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

// ★ 批次 177（2026-09-28）：`EntityPlayerGetZodiacEffect` 已删除 ——
//   改走引擎方法数据行 `0x0E010040`（`Entity_Player::GetZodiacEffect()` @ `0x29A938`，
//   `EngineCallShape::Int0`）。
// `EntityPlayer:GetModelingClayEffect()`（批次 195：**从恒 0 改成真读数**）。
//
// PC 契约 `EntityPlayer.md:1091` —— **正文是空的**，形状只能从签名行读（返回 `CollectibleType`，
// 数字）。消费者 EID `features/eid_holdmapdesc.lua:400-402` 的用法是
// `local modelingClayItem = player:GetModelingClayEffect(); if modelingClayItem > 0 then` ⇒
// **必须是数字**（nil 会抛 `attempt to compare nil with number`、摘掉整条回调）。
// 字段 `+0x2730` 的决定性证据 = 存档字段 `GameStatePlayer+0x608` 与它是同一个值的存取两端，
// 而那格旁边的唯一字符串就是 "[warn] Invalid modeling clay effect %d"（见
// `runtime_constants.hpp` 的 `kEntityPlayerModelingClayEffectOffset`）。
int EntityPlayerGetModelingClayEffect(lua_State* state) {
    return PushEntityPlayerCounter(state, "EntityPlayer:GetModelingClayEffect",
                                   kEntityPlayerModelingClayEffectOffset);
}

// `EntityPlayer:GetGlyphOfBalanceDrop(variant, subtype)` 的手写"恒 0"桩**已在批次 184 删除** ——
// 它现在是 `kEntityPlayerEngineRows` 里的一行数据（形状 `Ref2U32Pair`，引擎 `0x2FE574`）。
// ★ 这里保留说明而不是让它无声消失，因为**那个桩的失败方式很不直观**：原实现是 `PushZero`
//   （返回数字 0），而消费者 EID 拿返回值当**一张表**读 —— `local t = player:GetGlyphOfBalanceDrop(...)`
//   之后 `t[1] ~= -1` 在 `t` 是数字时求值为 `nil ~= -1` = **真** ⇒ EID 会拿一个假 variant 去查
//   `PickupNames`，于是**不报错、只是永远显示错的掉落物**（典型的"假读数"）。

// `EntityPlayer:GetCollectibleNum(id[, ignoreModifiers])`
// —— 2026-09-14 从"恒 0 占位"改成**真读数**。
//
// 为什么必须真读：EID 的**套装/变身进度**（`EID:evaluateTransformationProgress`，
// `features/eid_api.lua`）正是靠它逐个道具累加；占位返回 0 会让进度**永远显示 `(0/3)`** ——
// 不报错、只是永远不对（用户实测："一直是 (0/3)"）。
//
// 数据来源：`Entity_Player` 的"每收藏品计数数组"——一对 `begin/end` 指针（元素为 32 位整数），
// 见 `runtime_constants.hpp` 的 `kEntityPlayerCollectibleBeginOffset/EndOffset`。
// 口径与同族一致：**任何一步不成立都保守返回 0**，绝不报错（报错会摘掉整条回调）。
int EntityPlayerGetCollectibleNum(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    const int argumentCount = lua_gettop(state);
    lua_Integer collectibleId = 0;
    if (argumentCount < 2 || argumentCount > 3 ||
        !ReadIntegerArgument(state, 2, &collectibleId)) {
        return luaL_error(
            state,
            "EntityPlayer:GetCollectibleNum accepts (collectible[, ignoreModifiers])");
    }
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    if (entity == 0 || collectibleId < 0 ||
        static_cast<std::uint64_t>(collectibleId) > std::numeric_limits<std::uint32_t>::max()) {
        PushZero(state);
        return 1;
    }
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!ReadEngine(entity + kEntityPlayerCollectibleBeginOffset, &begin) ||
        !ReadEngine(entity + kEntityPlayerCollectibleEndOffset, &end) || begin == 0 ||
        end <= begin || ((end - begin) % sizeof(std::uint32_t)) != 0) {
        PushZero(state);
        return 1;
    }
    const std::size_t count = static_cast<std::size_t>((end - begin) / sizeof(std::uint32_t));
    if (static_cast<std::uint64_t>(collectibleId) >= count) {
        PushZero(state);
        return 1;
    }
    std::uint32_t owned = 0;
    if (!ReadEngine(begin + static_cast<std::uintptr_t>(collectibleId) * sizeof(std::uint32_t),
                    &owned)) {
        PushZero(state);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(owned));
    return 1;
}

// `EntityPlayer:GetTrinketMultiplier(id)` —— 2026-09-14 从"恒 0 占位"改成**真读数**。
// PC 语义：该饰品在身上的**份数**（EID 的套装进度用它累加饰品贡献）。
// 数据来源：`Entity_Player` 的两个饰品槽（`kEntityPlayerTrinketOffset`，步长 4 字节）：
// 某个槽等于该 id 就 +1。槽读不到就跳过（保守，不报错）。
int EntityPlayerGetTrinketMultiplier(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    lua_Integer trinketId = 0;
    if (lua_gettop(state) != 2 || !ReadIntegerArgument(state, 2, &trinketId)) {
        return luaL_error(state, "EntityPlayer:GetTrinketMultiplier accepts one trinket id");
    }
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    if (entity == 0 || trinketId <= 0 ||
        static_cast<std::uint64_t>(trinketId) > std::numeric_limits<std::uint32_t>::max()) {
        PushZero(state);
        return 1;
    }
    lua_Integer multiplier = 0;
    for (std::size_t slot = 0; slot < kEntityPlayerTrinketSlotCount; ++slot) {
        std::uint32_t held = 0;
        if (!ReadEngine(entity + kEntityPlayerTrinketOffset + slot * sizeof(std::uint32_t),
                        &held)) {
            continue;
        }
        if (held == static_cast<std::uint32_t>(trinketId)) {
            multiplier += 1;
        }
    }
    lua_pushinteger(state, multiplier);
    return 1;
}

// `EntityPlayer:GetPlayerFormCounter(ePlayerForm)`（批次 195：**从恒 0 改成真读数**）。
//
// PC **官方文档里没有这条**（它是 Repentogon 扩展）⇒ 形状取自签名
// （`analysis/lua-api-inventory/inventory.json` 的 `int GetPlayerFormCounter(PlayerForm)`）
// 加上引擎自身的语义锚点：`Entity_Player::HasPlayerForm(form)` **就是**"计数器 > 2"
// （第 3 件才算成套）⇒ 计数器 = "该形态凑了几件"。
// 数组 = `Entity_Player + 0x1C54` 的 **15 个 int32**（存档连续复制 15 组给出长度），
// 逐条见 `runtime_constants.hpp` 的 `kEntityPlayerFormCountersOffset`。
//
// ★ **越界自己夹 [0,14]**：`increment_player_form_counter` / `HasPlayerForm` / `ClearPlayerForm`
//   三处都是直接索引、没有任何边界检查（`form = 15` 会读到 `+0x1C90`）。PC 没给越界口径 ⇒ 给 0。
// 参数口径：按 id 参数政策只要求"是一个整数"，不卡范围（钳制在实现里，不抛错）。
int EntityPlayerGetPlayerFormCounter(lua_State* state) {
    if (!EntityPlayerProbeIdArgument(state, "EntityPlayer:GetPlayerFormCounter", false, nullptr)) {
        return 0;
    }
    auto* handle = static_cast<EntityHandle*>(luaL_checkudata(state, 1, kEntityPlayerMetatable));
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    const lua_Integer form = lua_tointeger(state, 2);
    if (entity == 0 || form < 0 ||
        static_cast<std::uint64_t>(form) >= kEntityPlayerFormCounterCount) {
        PushZero(state);
        return 1;
    }
    std::int32_t value = 0;
    if (!ReadEngine(entity + kEntityPlayerFormCountersOffset +
                        static_cast<std::uintptr_t>(form) * sizeof(std::int32_t),
                    &value)) {
        PushZero(state);
        return 1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

struct SmeltedTrinketCounts { std::int16_t normal, golden; };
static_assert(sizeof(SmeltedTrinketCounts) == kSmeltedTrinketDescriptorBytes);
struct SmeltedTrinketView { std::uintptr_t begin; std::size_t count; };

std::uintptr_t RequireSmeltedPlayer(lua_State* state) {
    const auto player = ValidatedEntityPlayer(CheckEntityHandle(state,1));
    std::uint8_t exists=0;
    std::uintptr_t begin=0;
    std::size_t count=0;
    if (player == 0 || !engine_memory::ReadField(player,kEntityExistsOffset,&exists,&IsEngineMemoryReadable) ||
        exists == 0 || ResolveEntityPlayerBegin(&begin,&count) == 0) {
        luaL_error(state,"EntityPlayer:GetSmeltedTrinkets player is no longer available");
        return 0;
    }
    for (std::size_t i=0;i<count;++i) {
        std::uintptr_t candidate=0;
        if (!engine_memory::ReadField(begin,i*sizeof(std::uintptr_t),&candidate,&IsEngineMemoryReadable)) {
            luaL_error(state,"EntityPlayer:GetSmeltedTrinkets player collection is unavailable");
            return 0;
        }
        if (candidate == player) return player;
    }
    luaL_error(state,"EntityPlayer:GetSmeltedTrinkets player is no longer in the current collection");
    return 0;
}

SmeltedTrinketView ReadSmeltedTrinketsNow(lua_State* state) {
    const auto player=RequireSmeltedPlayer(state);
    std::uintptr_t begin=0,end=0,capacity=0;
    if (!engine_memory::ReadField(player,kEntityPlayerSmeltedTrinketBeginOffset,&begin,&IsEngineMemoryReadable) ||
        !engine_memory::ReadField(player,kEntityPlayerSmeltedTrinketEndOffset,&end,&IsEngineMemoryReadable) ||
        !engine_memory::ReadField(player,kEntityPlayerSmeltedTrinketCapacityOffset,&capacity,&IsEngineMemoryReadable) ||
        (begin == 0 && (end != 0 || capacity != 0)) || end < begin || capacity < end ||
        ((begin|end|capacity)&3) != 0 ||
        (end != begin && !IsEngineMemoryReadable(begin,end-begin))) {
        luaL_error(state,"EntityPlayer:GetSmeltedTrinkets native vector is unavailable or malformed");
        return {};
    }
    return {begin,static_cast<std::size_t>((end-begin)/kSmeltedTrinketDescriptorBytes)};
}

bool ValidSmeltedFilterId(lua_State* state,std::uint32_t id) {
    if (id == 0) return false;
    const auto config=ResolveItemConfig(nullptr);
    std::uintptr_t begin=0,end=0;
    if (config == 0 || !engine_memory::ReadField(config,kItemConfigTrinketBeginOffset,&begin,&IsEngineMemoryReadable) ||
        !engine_memory::ReadField(config,kItemConfigTrinketEndOffset,&end,&IsEngineMemoryReadable) ||
        (begin == 0 && end != 0) || end < begin || ((begin|end)&7) != 0 ||
        (end != begin && !IsEngineMemoryReadable(begin,end-begin))) {
        luaL_error(state,"EntityPlayer:GetSmeltedTrinkets trinket configuration is unavailable or malformed");
        return false;
    }
    if (id >= (end-begin)/sizeof(std::uintptr_t)) return false;
    std::uintptr_t item=0;
    if (!engine_memory::ReadField(begin,id*sizeof(std::uintptr_t),&item,&IsEngineMemoryReadable)) {
        luaL_error(state,"EntityPlayer:GetSmeltedTrinkets trinket configuration entry is unavailable");
        return false;
    }
    return item != 0;
}

void PushSmeltedTrinketCounts(lua_State* state,std::size_t id) {
    // 任何Lua分配/元方法可能改变原生对象；先重新核当前owner与向量，再读POD，
    // 不让原生指针/引用跨Lua分配存活。
    const auto view=ReadSmeltedTrinketsNow(state);
    SmeltedTrinketCounts counts{};
    if (id >= view.count || !engine_memory::ReadField(view.begin,id*kSmeltedTrinketDescriptorBytes,&counts,&IsEngineMemoryReadable)) {
        luaL_error(state,"EntityPlayer:GetSmeltedTrinkets descriptor is outside the current native vector");
        return;
    }
    lua_newtable(state);
    lua_pushinteger(state,counts.normal);lua_setfield(state,-2,"trinketAmount");
    lua_pushinteger(state,counts.golden);lua_setfield(state,-2,"goldenTrinketAmount");
}

int EntityPlayerGetSmeltedTrinkets(lua_State* state) {
    // REPENTOGON扩展；公开能力不代表整个REPENTOGON插件存在，不改变版本布尔。
    static_cast<void>(ReadSmeltedTrinketsNow(state));
    if (lua_type(state,2) == LUA_TTABLE) {
        // 0x7fff域的去重位图仅4KiB，平凡析构；Lua longjmp不跨std::set析构。
        std::uint64_t selected[512]{};
        const auto length=lua_rawlen(state,2);
        for (std::size_t i=1;i<=length;++i) {
            lua_pushinteger(state,static_cast<lua_Integer>(i));lua_gettable(state,2);
            if (lua_isnil(state,-1)) {lua_pop(state,1);break;}
            const auto id=static_cast<std::uint32_t>(luaL_checkinteger(state,-1))&0x7FFFU;
            if (ValidSmeltedFilterId(state,id)) selected[id/64]|=std::uint64_t{1}<<(id%64);
            lua_pop(state,1);
        }
        // 过滤表元方法完成之后再次核对象，即使空筛选也不掩盖对象失效。
        static_cast<void>(ReadSmeltedTrinketsNow(state));
        lua_newtable(state);
        for (std::uint32_t id=1;id<=0x7FFFU;++id) {
            if ((selected[id/64]&(std::uint64_t{1}<<(id%64))) == 0) continue;
            PushSmeltedTrinketCounts(state,id);lua_rawseti(state,-2,id);
        }
    } else {
        lua_newtable(state);
        for (std::size_t id=1;;++id) {
            const auto view=ReadSmeltedTrinketsNow(state);
            if (id >= view.count) break;
            PushSmeltedTrinketCounts(state,id);lua_rawseti(state,-2,static_cast<lua_Integer>(id));
        }
    }
    return 1;
}

// ===========================================================================
// `TemporaryEffects`（批次 388，2026-10-07）—— `EntityPlayer:GetEffects()` 的返回值
// ===========================================================================
//
// 背景：PC 的 `EntityPlayer:GetEffects()` 返回 `TemporaryEffects` 对象（`EntityPlayer.md:951`），
// 它挂着 17 个方法（逐字节契约副本 = `analysis/isaacdocs-snapshot/docs/TemporaryEffects.md`）。
// 我们此前**恒返回空表** ⇒ 模组 `player:GetEffects():HasCollectibleEffect(id)` 等于在空表上取
// 方法 ⇒ 抛 `attempt to call a nil value (method 'HasCollectibleEffect')` ⇒ **整条回调被派发器
// 静默摘掉**（minimapi 的小地图画不出来就是这么来的：`scripts/minimapapi/main.lua:2262`；
// EID `features/eid_itemprediction.lua:540` 是同一个写法）。
//
// 容器 = `Entity_Player + kEntityPlayerTemporaryEffectsOffset`（`+0x18D8`，**内嵌子对象**，
// 不是指针；三条独立函数的 `add x?,x?,#0x18d8` 互证，见 `runtime_constants.hpp` 该常量段）。
// 句柄（`TemporaryEffectsHandle`）存**拥有它的 `Entity_Player` 地址**，每次访问重新校验玩家
// vptr 再把容器地址算回来 ⇒ 换局/玩家销毁后旧句柄自然失效，不会解引用过期内存。
//
// 方法分工（为什么不是"全走数据行"）：
//   * 6 条**无可选参数**的（`Has*Effect` ×3、`Get*EffectNum` ×3）⇒ 引擎方法数据行
//     （`kTemporaryEffectsEngineRows`，`Bool1`/`Int1`）；
//   * 6 条 `Add*Effect`/`Remove*Effect` ⇒ **手写**（PC 缺省 `AddCostume=true` / `Count=1`，
//     而数据行的"省略=寄存器保持 0"表达不了非 0 缺省）；
//   * 5 条**引擎侧形状未齐**的（`ClearEffects` 的 `bool` 语义、三个返回 `TemporaryEffect`
//     对象的 `Get*Effect`、`GetEffectsList` 的向量代理）⇒ 不抛错占位，逐条登记在 `api_deviation.cpp`。

// 2026-10-09更正：上述5条占位已恢复，Clear默认false，三个只读效果查询与实时EffectList。

//: 解出 `TemporaryEffects*`（= `player + 0x18D8`）。句柄类型不对 / 玩家 vptr 失效 ⇒ 0
//: （调用方据此**静默降级**：void 方法什么都不做、返回标量的压安全值 —— **绝不报错**，
//: 报错会把整条模组回调摘掉，比"这一次没生效"严重得多）。
bool TemporaryEffectOwnerAlive(std::uintptr_t player,
        const LuaRuntime::EntityLifetimeToken* token,std::uintptr_t module) noexcept {
    return token && token->entity==player && EntityLifetimeAlive(token) && module==LuaRuntime::EngineModuleBase() &&
        player && player<=UINTPTR_MAX-kEntityPlayerTemporaryEffectsOffset-kTemporaryEffectsPlayerBackrefOffset &&
        IsEntityPlayer(player);
}
std::uintptr_t ResolveTemporaryEffectsReceiver(lua_State* state, int index) noexcept {
    if(lua_rawlen(state,index)!=sizeof(TemporaryEffectsHandle))return 0;
    auto* handle = static_cast<TemporaryEffectsHandle*>(
        luaL_testudata(state, index, kTemporaryEffectsMetatable));
    if (handle == nullptr || handle->player == nullptr) {
        return 0;
    }
    const std::uintptr_t player = engine_memory::AddressOf(handle->player);
    if (!TemporaryEffectOwnerAlive(player,handle->lifetime,handle->module)) {
        return 0;
    }
    return player + kEntityPlayerTemporaryEffectsOffset;
}

//: 把"拥有 `TemporaryEffects` 的玩家地址"包成一个 `IsaacRuntime.TemporaryEffects` userdata。
//: 形状照抄 `PushPathFinderHandle`：0 ⇒ 压 `nil`，否则 `lua_newuserdata` + 设元表。
void PushTemporaryEffectsHandle(lua_State* state, std::uintptr_t player) {
    if (player == 0) {
        lua_pushnil(state);
        return;
    }
    auto* token=PushEntityLifetimeToken(state,player);const int tokenIndex=lua_gettop(state);
    auto* handle = static_cast<TemporaryEffectsHandle*>(
        lua_newuserdata(state, sizeof(TemporaryEffectsHandle)));
    handle->player = engine_memory::AsObject(player);
    handle->lifetime=token;handle->module=LuaRuntime::EngineModuleBase();
    lua_pushvalue(state,tokenIndex);lua_setuservalue(state,-2);
    luaL_getmetatable(state, kTemporaryEffectsMetatable);
    lua_setmetatable(state, -2);
    lua_remove(state,tokenIndex);
}

//: `TemporaryEffects` 的 `__index`：它**只有方法、没有字段** ⇒ 直接去 `__methods` 里取。
int TemporaryEffectsIndex(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kTemporaryEffectsMetatable));
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    if (PushMethodFrom(state, kTemporaryEffectsMetatable, lua_tostring(state, 2))) {
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

//: 读一个"物品编号"参数（收藏品 / 饰品 / null 道具通用）：**只要求是个非负整数**，
//: 交给引擎去判合不合法（与 `EntityPlayerProbeIdArgument` 同口径）。
bool ReadTemporaryEffectId(lua_State* state, int index, std::uint32_t* out) noexcept {
    lua_Integer value = 0;
    if (out == nullptr || !ReadIntegerArgument(state, index, &value)) {
        return false;
    }
    if (value < 0 ||
        static_cast<std::uint64_t>(value) > std::numeric_limits<std::uint32_t>::max()) {
        return false;
    }
    *out = static_cast<std::uint32_t>(value);
    return true;
}

//: `Add*Effect` 三兄弟的共用体：`void(this, id(int32), addCostume(bool 缺省 true), count(u32 缺省 1))`。
//: 引擎真身 = `TemporaryEffects::AddEffect(eCollectibleType/eTrinketType/eNullItemID, bool, unsigned int)`。
int TemporaryEffectsAddEffect(lua_State* state, const char* label, std::uintptr_t offset,
                              std::uint32_t entryWord) {
    const std::uintptr_t self = ResolveTemporaryEffectsReceiver(state, 1);
    if (self == 0) {
        return 0;  // 接收者不可用 ⇒ 静默 no-op（void 返回），不报错
    }
    std::uint32_t id = 0;
    if (!ReadTemporaryEffectId(state, 2, &id)) {
        return luaL_error(state, "%s expects an integer id", label);
    }
    bool addCostume = true;  // PC 缺省 = true（`TemporaryEffects.md:23`）
    if (lua_gettop(state) >= 3 && !lua_isnoneornil(state, 3)) {
        addCostume = lua_toboolean(state, 3) != 0;
    }
    std::uint32_t count = 1;  // PC 缺省 = 1
    if (lua_gettop(state) >= 4 && !lua_isnoneornil(state, 4)) {
        if (!ReadTemporaryEffectId(state, 4, &count)) {
            return luaL_error(state, "%s expects an integer count", label);
        }
    }
    const std::uintptr_t method = EngineOffsetAddress<IsEngineMemoryReadable>(offset);
    if (!EngineEntryWordMatches(method, entryWord)) {
        return luaL_error(state, "%s native bindings are unavailable", label);
    }
    std::uint64_t integers[8] = {self,
                                 static_cast<std::uint64_t>(id),
                                 addCostume ? 1U : 0U,
                                 static_cast<std::uint64_t>(count),
                                 0,
                                 0,
                                 0,
                                 0};
    double floats[8] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    std::uint64_t integerResult = 0;
    double floatResult = 0.0;
    EngineCallTrampoline(method, integers, floats, &integerResult, &floatResult);
    return 0;
}

//: `Remove*Effect` 三兄弟的共用体：`void(this, id(int32), count(u32 缺省 1))`。
//: ★ PC 的 `Count = -1` 表示"移除全部"（`TemporaryEffects.md:116`）—— 按位原样传
//:   `(uint32)-1 = 0xFFFFFFFF`。2026-10-09取证：原生@0x4A6ADC无符号cmp，
//:   csel min(held,count)，再扣除并通知服装/缓存/房间；不能在Lua层手工清vector。
int TemporaryEffectsRemoveEffect(lua_State* state, const char* label, std::uintptr_t offset,
                                 std::uint32_t entryWord) {
    const std::uintptr_t self = ResolveTemporaryEffectsReceiver(state, 1);
    if (self == 0) {
        return 0;
    }
    std::uint32_t id = 0;
    if (!ReadTemporaryEffectId(state, 2, &id)) {
        return luaL_error(state, "%s expects an integer id", label);
    }
    std::uint32_t count = 1;
    if (lua_gettop(state) >= 3 && !lua_isnoneornil(state, 3)) {
        lua_Integer value = 0;
        if (!ReadIntegerArgument(state, 3, &value) || value < -1 ||
            value > std::numeric_limits<std::int32_t>::max()) {
            return luaL_error(state, "%s expects an integer count", label);
        }
        count = static_cast<std::uint32_t>(value);
    }
    const std::uintptr_t method = EngineOffsetAddress<IsEngineMemoryReadable>(offset);
    if (!EngineEntryWordMatches(method, entryWord)) {
        return luaL_error(state, "%s native bindings are unavailable", label);
    }
    std::uint64_t integers[8] = {
        self, static_cast<std::uint64_t>(id), static_cast<std::uint64_t>(count), 0, 0, 0, 0, 0};
    double floats[8] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    std::uint64_t integerResult = 0;
    double floatResult = 0.0;
    EngineCallTrampoline(method, integers, floats, &integerResult, &floatResult);
    return 0;
}

int TemporaryEffectsAddCollectibleEffect(lua_State* state) {
    return TemporaryEffectsAddEffect(state, "TemporaryEffects:AddCollectibleEffect",
                                     kTemporaryEffectsAddCollectibleEffectOffset,
                                     kTemporaryEffectsAddCollectibleEffectEntryWord);
}
int TemporaryEffectsAddTrinketEffect(lua_State* state) {
    return TemporaryEffectsAddEffect(state, "TemporaryEffects:AddTrinketEffect",
                                     kTemporaryEffectsAddTrinketEffectOffset,
                                     kTemporaryEffectsAddTrinketEffectEntryWord);
}
int TemporaryEffectsAddNullEffect(lua_State* state) {
    return TemporaryEffectsAddEffect(state, "TemporaryEffects:AddNullEffect",
                                     kTemporaryEffectsAddNullEffectOffset,
                                     kTemporaryEffectsAddNullEffectEntryWord);
}
int TemporaryEffectsRemoveCollectibleEffect(lua_State* state) {
    return TemporaryEffectsRemoveEffect(state, "TemporaryEffects:RemoveCollectibleEffect",
                                        kTemporaryEffectsRemoveCollectibleEffectOffset,
                                        kTemporaryEffectsRemoveCollectibleEffectEntryWord);
}
int TemporaryEffectsRemoveTrinketEffect(lua_State* state) {
    return TemporaryEffectsRemoveEffect(state, "TemporaryEffects:RemoveTrinketEffect",
                                        kTemporaryEffectsRemoveTrinketEffectOffset,
                                        kTemporaryEffectsRemoveTrinketEffectEntryWord);
}
int TemporaryEffectsRemoveNullEffect(lua_State* state) {
    return TemporaryEffectsRemoveEffect(state, "TemporaryEffects:RemoveNullEffect",
                                        kTemporaryEffectsRemoveNullEffectOffset,
                                        kTemporaryEffectsRemoveNullEffectEntryWord);
}

//: 查询方法的**参数个数**检查（`self` + `expectedIdArguments` 个整数参数）。
//: 接收者不可用（句柄失效 / 玩家没了）⇒ 返回 false，调用方**静默 no-op**（不报错）；
//: 参数个数/类型不对才报错（那是调用方写错，PC 上同样会报）。
bool CheckTemporaryEffectsCall(lua_State* state, const char* label, int expectedIdArguments) {
    if (ResolveTemporaryEffectsReceiver(state, 1) == 0) {
        return false;
    }
    if (lua_gettop(state) - 1 != expectedIdArguments) {
        luaL_error(state, "%s expects %d argument(s)", label, expectedIdArguments);
        return false;  // 不会到达
    }
    if (expectedIdArguments >= 1) {
        std::uint32_t ignored = 0;
        if (!ReadTemporaryEffectId(state, 2, &ignored)) {
            luaL_error(state, "%s expects an integer id", label);
            return false;  // 不会到达
        }
    }
    return true;
}

// PC返回的是const效果视图；每次读重新检查玩家、vector起点、下标与Item身份。
constexpr const char* kTemporaryEffectMetatable = "IsaacRuntime.TemporaryEffect";
constexpr const char* kEffectListMetatable = "IsaacRuntime.EffectList";
struct TemporaryEffectHandle {
    std::uintptr_t player;
    std::uintptr_t begin;
    std::uintptr_t item;
    std::size_t index;
    LuaRuntime::EntityLifetimeToken* lifetime;
    std::uintptr_t module;
};
struct EffectListHandle {
    std::uintptr_t player;
    LuaRuntime::EntityLifetimeToken* lifetime;
    std::uintptr_t module;
};
static_assert(sizeof(TemporaryEffectsHandle)==24 && sizeof(TemporaryEffectHandle)==48 && sizeof(EffectListHandle)==24);

bool ReadTemporaryEffectVector(std::uintptr_t player, ItemVectorView* view) noexcept {
    if (view == nullptr || !IsEntityPlayer(player) ||
        player > UINTPTR_MAX - kEntityPlayerTemporaryEffectsOffset - kTemporaryEffectsPlayerBackrefOffset) {
        return false;
    }
    const std::uintptr_t self = player + kEntityPlayerTemporaryEffectsOffset;
    std::uintptr_t begin = 0, end = 0;
    if (!ReadEngine(self + kTemporaryEffectsEffectListBeginOffset, &begin) ||
        !ReadEngine(self + kTemporaryEffectsEffectListEndOffset, &end) ||
        end < begin || (end - begin) % kTemporaryEffectsElementStride != 0 ||
        (begin == 0 && end != 0) ||
        (end != begin && !IsEngineMemoryReadable(begin, end - begin))) {
        return false;
    }
    *view = {begin, end, (end - begin) / kTemporaryEffectsElementStride};
    return true;
}

void PushTemporaryEffect(lua_State* state, std::uintptr_t player,
                         const ItemVectorView& view, std::size_t index) {
    std::uintptr_t item = 0;
    if (index >= view.count ||
        !ReadEngine(view.begin + index * kTemporaryEffectsElementStride, &item) || item == 0) {
        lua_pushnil(state);
        return;
    }
    auto* token=PushEntityLifetimeToken(state,player);const int tokenIndex=lua_gettop(state);
    auto* handle = static_cast<TemporaryEffectHandle*>(lua_newuserdata(state, sizeof(TemporaryEffectHandle)));
    *handle = {player, view.begin, item, index,token,LuaRuntime::EngineModuleBase()};
    lua_pushvalue(state,tokenIndex);lua_setuservalue(state,-2);
    luaL_getmetatable(state, kTemporaryEffectMetatable);
    lua_setmetatable(state, -2);
    lua_remove(state,tokenIndex);
}

std::uintptr_t ResolveTemporaryEffect(const TemporaryEffectHandle* handle) noexcept {
    ItemVectorView view{};
    if (handle == nullptr || !TemporaryEffectOwnerAlive(handle->player,handle->lifetime,handle->module) ||
        !ReadTemporaryEffectVector(handle->player, &view) ||
        view.begin != handle->begin || handle->index >= view.count) {
        return 0;
    }
    const std::uintptr_t entry = view.begin + handle->index * kTemporaryEffectsElementStride;
    std::uintptr_t item = 0;
    return ReadEngine(entry, &item) && item == handle->item ? entry : 0;
}

std::uintptr_t TemporaryEffectIdentity(lua_State* state,int index) noexcept {
    if(lua_rawlen(state,index)!=sizeof(TemporaryEffectHandle))return 0;
    auto*handle=static_cast<const TemporaryEffectHandle*>(luaL_testudata(state,index,kTemporaryEffectMetatable));
    return ResolveTemporaryEffect(handle);
}
std::uintptr_t EffectListAddress(const EffectListHandle* handle,ItemVectorView* view) noexcept {
    return handle && TemporaryEffectOwnerAlive(handle->player,handle->lifetime,handle->module) &&
        ReadTemporaryEffectVector(handle->player,view)
        ?handle->player+kEntityPlayerTemporaryEffectsOffset+kTemporaryEffectsEffectListBeginOffset:0;
}
std::uintptr_t EffectListIdentity(lua_State* state,int index) noexcept {
    if(lua_rawlen(state,index)!=sizeof(EffectListHandle))return 0;
    auto*handle=static_cast<const EffectListHandle*>(luaL_testudata(state,index,kEffectListMetatable));
    ItemVectorView view{};return EffectListAddress(handle,&view);
}

int ReadOnlyEffectWrite(lua_State* state) {
    return luaL_error(state, "temporary effect views are read-only");
}

int TemporaryEffectIndex(lua_State* state) {
    auto* handle = static_cast<TemporaryEffectHandle*>(luaL_checkudata(state, 1, kTemporaryEffectMetatable));
    const char* key = lua_type(state, 2) == LUA_TSTRING ? lua_tostring(state, 2) : nullptr;
    const std::uintptr_t entry = ResolveTemporaryEffect(handle);
    if (entry != 0 && key != nullptr) {
        if (std::strcmp(key, "Item") == 0) {
            static_cast<void>(PushValidatedItemConfigItem(state, handle->item));
            return 1;
        }
        std::int32_t value = 0;
        if (std::strcmp(key, "Count") == 0 && ReadEngine(entry + kTemporaryEffectCountOffset, &value)) {
            lua_pushinteger(state, value); return 1;
        }
        if (std::strcmp(key, "Cooldown") == 0 && ReadEngine(entry + kTemporaryEffectCooldownOffset, &value)) {
            lua_pushinteger(state, value); return 1;
        }
    }
    lua_pushnil(state);
    return 1;
}

int EffectListGet(lua_State* state) {
    auto* handle = static_cast<EffectListHandle*>(luaL_checkudata(state, 1, kEffectListMetatable));
    lua_Integer index = 0;
    if (lua_gettop(state) != 2 || !ReadIntegerArgument(state, 2, &index)) {
        return luaL_error(state, "EffectList:Get expects an integer index");
    }
    ItemVectorView view{};
    if (!EffectListAddress(handle, &view)) {
        return luaL_error(state, "EffectList is no longer available");
    }
    if (index < 0 || static_cast<std::uint64_t>(index) >= view.count) {
        return luaL_error(state, "EffectList index out of range");
    }
    PushTemporaryEffect(state, handle->player, view, static_cast<std::size_t>(index));
    return 1;
}

int EffectListLength(lua_State* state) {
    auto* handle = static_cast<EffectListHandle*>(luaL_checkudata(state, 1, kEffectListMetatable));
    ItemVectorView view{};
    if (!EffectListAddress(handle, &view)) {
        return luaL_error(state, "EffectList is no longer available");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(view.count));
    return 1;
}

int EffectListIndex(lua_State* state) {
    static_cast<void>(luaL_checkudata(state, 1, kEffectListMetatable));
    const char* key = lua_type(state, 2) == LUA_TSTRING ? lua_tostring(state, 2) : nullptr;
    if (key != nullptr && std::strcmp(key, "Size") == 0) { return EffectListLength(state); }
    if (key != nullptr && std::strcmp(key, "Get") == 0) { lua_pushcfunction(state, EffectListGet); return 1; }
    lua_pushnil(state);
    return 1;
}

int TemporaryEffectsClearEffects(lua_State* state) {
    const std::uintptr_t self = ResolveTemporaryEffectsReceiver(state, 1);
    if (self == 0) { return 0; }
    if (lua_gettop(state) > 2) {
        return luaL_error(state, "TemporaryEffects:ClearEffects accepts one optional boolean");
    }
    const std::uintptr_t method = EngineOffsetAddress<IsEngineMemoryReadable>(kTemporaryEffectsClearEffectsOffset);
    if (!EngineEntryOrRelayMatches<IsEngineMemoryReadable>(
            method, kTemporaryEffectsClearEffectsEntryBytes.data(), kTemporaryEffectsClearEffectsEntryBytes.size(), 0)) {
        return luaL_error(state, "TemporaryEffects:ClearEffects native bindings are unavailable");
    }
    // PC Lua thunk @0x846BC0 uses lua_toboolean(L,2): no argument/nil/false => false.
    std::uint64_t integers[8] = {self, lua_toboolean(state, 2) ? 1U : 0U, 0, 0, 0, 0, 0, 0};
    double floats[8] = {};
    std::uint64_t integerResult = 0;
    double floatResult = 0;
    EngineCallTrampoline(method, integers, floats, &integerResult, &floatResult);
    return 0;
}

int TemporaryEffectsGetEffect(lua_State* state, const char* label, std::uint32_t typeMask) {
    if (!CheckTemporaryEffectsCall(state, label, 1)) { return 0; }
    const std::uintptr_t self = ResolveTemporaryEffectsReceiver(state, 1);
    std::uint32_t id = 0;
    static_cast<void>(ReadTemporaryEffectId(state, 2, &id));
    std::uint8_t frozen = 0;
    ItemVectorView view{};
    const std::uintptr_t player = self - kEntityPlayerTemporaryEffectsOffset;
    if (ReadEngine(self + kTemporaryEffectsFrozenOffset, &frozen) && frozen == 0 &&
        ReadTemporaryEffectVector(player, &view)) {
        for (std::size_t index = 0; index < view.count; ++index) {
            std::uintptr_t item = 0;
            std::uint32_t type = 0, itemId = 0;
            if (ReadEngine(view.begin + index * kTemporaryEffectsElementStride, &item) &&
                item != 0 && item <= UINTPTR_MAX - kItemConfigItemIdOffset &&
                ReadEngine(item + kItemConfigItemTypeOffset, &type) && type < 32 &&
                (typeMask & (1U << type)) != 0 &&
                ReadEngine(item + kItemConfigItemIdOffset, &itemId) && itemId == id) {
                PushTemporaryEffect(state, player, view, index);
                return 1;
            }
        }
    }
    lua_pushnil(state);
    return 1;
}

int TemporaryEffectsGetCollectibleEffect(lua_State* state) {
    return TemporaryEffectsGetEffect(state, "TemporaryEffects:GetCollectibleEffect", 0x1AU);
}
int TemporaryEffectsGetNullEffect(lua_State* state) {
    return TemporaryEffectsGetEffect(state, "TemporaryEffects:GetNullEffect", 1U);
}
int TemporaryEffectsGetTrinketEffect(lua_State* state) {
    return TemporaryEffectsGetEffect(state, "TemporaryEffects:GetTrinketEffect", 4U);
}

int TemporaryEffectsGetEffectsList(lua_State* state) {
    if (!CheckTemporaryEffectsCall(state, "TemporaryEffects:GetEffectsList", 0)) { return 0; }
    const std::uintptr_t self = ResolveTemporaryEffectsReceiver(state, 1);
    const auto player=self-kEntityPlayerTemporaryEffectsOffset;
    auto*token=PushEntityLifetimeToken(state,player);const int tokenIndex=lua_gettop(state);
    auto* handle = static_cast<EffectListHandle*>(lua_newuserdata(state, sizeof(EffectListHandle)));
    *handle={player,token,LuaRuntime::EngineModuleBase()};
    lua_pushvalue(state,tokenIndex);lua_setuservalue(state,-2);
    luaL_getmetatable(state, kEffectListMetatable);
    lua_setmetatable(state, -2);
    lua_remove(state,tokenIndex);
    return 1;
}

int EntityPlayerGetEffects(lua_State* state) {
    auto* handle = CheckEntityHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:GetEffects accepts no arguments");
    }
    // ★ 批次 388（2026-10-07）：**不再返回空表** —— 返回带 17 个方法的 `TemporaryEffects`
    //   对象。取不到有效玩家（`ValidatedEntityPlayer` == 0）⇒ 压 `nil`（PC 的"不可用引用"口径）。
    //   正常路径（`Isaac.GetPlayer(i)` 交回的玩家句柄）一定拿得到。
    PushTemporaryEffectsHandle(state, ValidatedEntityPlayer(handle));
    return 1;
}

int EntityPlayerGetName(lua_State* state);

int EntityPlayerHasTrinket(lua_State* state) {
    // ★ 批次 133（2026-09-25，真机实测修正）：**旧实现恒 false** ⇒ EID 的"套装进度"里
    // **饰品类整条不计**（`features/eid_api.lua:2574`：`elseif 变体 == 饰品 and player:HasTrinket(id)
    // then progress += player:GetTrinketMultiplier(id)`）—— 用户报的"计数和实际不太一样"就是它。
    //
    // ★ 批次 195（2026-09-29）：**内部换成一次引擎调用** ——
    // `Entity_Player::HasTrinket(eTrinketType, bool) const @ 0x28D3B8`（入口 16 字节指纹见
    // `runtime_constants.hpp` 的 `kEntityPlayerHasTrinketOffset`）。
    // 为什么不继续自己扫两个饰品槽（批次 133 的做法）：引擎自己就实现了 PC 文档那两种口径，
    // 而我们的扫槽版差两处 ——
    //   ① **不看 `IgnoreModifiers`**：PC 文档 `EntityPlayer.md:1394` 明写"不带它时还会计入
    //      **由其它道具赋予的**饰品效果"（引擎那一支走 `GetTrinketMultiplier`，倍率 > 0 即真）；
    //   ② **不掩低位**：槽值低位 15 位才是饰品 id、高位是**金色**标志，我们逐位相等 ⇒
    //      **金色饰品答 false**（引擎是 `and w9,w9,#0x7fff` 再比）。
    //   ⇒ 直接调引擎比自己重写便宜且对。
    //
    // ★ 为什么不改成**数据行**（`EngineMethodRow`）：数据行按 `lua_gettop(state) !=
    //   receiverArguments + shape.argumentCount` **严格相等**校验参数个数，而 PC 的
    //   `IgnoreModifiers` **可省** ⇒ 做成两参会把 `player:HasTrinket(id)` 这种合法写法变成
    //   "expects 2 argument(s)"的 Lua 错误（比假值更糟）。**保留手写 handler**，
    //   参数口径继续由 `EntityPlayerProbeIdArgument(..., true, ...)` 表达。
    //
    // 降级：接收者无效 / id 不在 `uint32` 可表示范围内（含 0）⇒ `false` 且**不调引擎**
    // （引擎那条 `ignore=false` 支会拿 id 去问 `GetTrinketMultiplier`，负数是没取证过的入参；
    // 而 id = 0 是 `TRINKET_NONE`，PC 上同样恒假）。
    lua_Integer trinketId = 0;
    // 第三个实参（PC 的 `IgnoreModifiers`）可省 —— 传了也接受，见 `EntityPlayerProbeIdArgument`。
    if (!EntityPlayerProbeIdArgument(state, "EntityPlayer:HasTrinket", true, &trinketId)) {
        return 0;
    }
    const bool ignoreModifiers = lua_gettop(state) == 3 && lua_isboolean(state, 3) &&
                                 lua_toboolean(state, 3) != 0;
    auto* handle = static_cast<EntityHandle*>(luaL_checkudata(state, 1, kEntityPlayerMetatable));
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    if (entity == 0 || trinketId <= 0 ||
        static_cast<std::uint64_t>(trinketId) > std::numeric_limits<std::uint32_t>::max()) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const std::uintptr_t method = EngineOffsetAddress<IsEngineMemoryReadable>(
        kEntityPlayerHasTrinketOffset);
    if (!EngineEntryWordMatches(method, kEntityPlayerHasTrinketEntryWord)) {
        // 偏移/指纹对不上 ⇒ 报错，**不编一个 false**：假 false 会让 EID 的套装进度静默少算，
        // 那正是本条要修的形态。报错至少能在模组侧与读数里看见。
        return luaL_error(state, "EntityPlayer:HasTrinket native bindings are unavailable");
    }
    // ★ 2026-09-29（**回退过一次**）：这里**刻意用值数组跳板**，不写成 `AsFunction<HasTrinketFn>`：
    // 我先把调用点改成带声明类型的形态、想让 ABI 门禁真能核，结果**宿主夹具当场崩**
    // （`test_lua_entity_player` 与 `test_lua_entity_rng_and_fields` 的三个场景全是
    // `scenario valid exited with -10` = 被信号打断）。⇒ 回退到跳板，改用**台账**交代这条常量的性质。
    //
    // 台账：`tools/engine_abi_backlog.json` 里 `kEntityPlayerHasTrinketOffset` 记成 A 类
    // （真有消费者、但我们没有声明调用签名 ⇒ 目前工具核不到）—— 诚实记账，不假装核过。
    std::uint64_t integers[8] = {entity, static_cast<std::uint64_t>(trinketId),
                                 ignoreModifiers ? 1U : 0U, 0, 0, 0, 0, 0};
    double floats[8] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    std::uint64_t integerResult = 0;
    double floatResult = 0.0;
    EngineCallTrampoline(method, integers, floats, &integerResult, &floatResult);
    lua_pushboolean(state, integerResult != 0 ? 1 : 0);
    return 1;
}

// ★ 批次 177（2026-09-28）：`EntityPlayerHasPlayerForm` 与 `EntityPlayerCanPickRedHearts`
//   已删除 —— 分别改走引擎方法数据行 `0x0E01004B`（`Entity_Player::HasPlayerForm(ePlayerForm)`
//   @ `0x298510`，`EngineCallShape::Bool1`）与 `0x0E01004C`（`Entity_Player::CanPickRedHearts()`
//   @ `0x2FB6A4`，`EngineCallShape::Bool0`）。那两条以前恒 false，而
//   `CanPickRedHearts` 被 EID 的 `features/eid_itemprediction.lua:366` 用来判"满红心"
//   那一支预测 ⇒ 恒 false 时那一支永远不成立。
int EntityPlayerIsSubPlayer(lua_State* state) {
    if (!EntityPlayerProbeNoArguments(state, "EntityPlayer:IsSubPlayer")) {
        return 0;
    }
    // 2026-10-09：PC取玩家编号bit31，NS初始化副玩家也检查同一位。
    auto* handle = static_cast<EntityHandle*>(luaL_checkudata(state, 1, kEntityPlayerMetatable));
    const auto player = ValidatedEntityPlayer(handle);
    std::uint32_t index = 0;
    const bool readable = player != 0 && ReadEngine(player + kEntityPlayerIndexOffset, &index);
    lua_pushboolean(state, readable && (index & 0x80000000U) != 0 ? 1 : 0);
    return 1;
}


// --- ItemConfig 只读视图（批次 2b）-------------------------------------------
//
// 偏移来源 = **反汇编定位 + 真机现象逐位互证**（常量表与全部指令级证据在
// `runtime_constants.hpp` 的 ItemConfig 段）。三条纪律：
//
//   1. `IC = Manager + kManagerItemConfigOffset` 是**加法**：`ItemConfig` 内嵌在 `Manager` 里，
//      引擎中不存在指向它的指针。上一轮探针把 `*(M + 0x36538)`（其实是 `collectibles.begin()`）
//      当成了 `ItemConfig*`，这就是那次"条目指针为 0"的根因。
//   2. **每一次**访问都重新走完整条链路（基址 → `g_Manager` 槽 → `Manager*` → `IC` → 向量 →
//      条目）：句柄里的地址只当"身份"，不当"可用性"（换局/重开后 `ItemConfig::Init` 会重排向量）。
//   3. 任何一步不可读、长度非法、下标越界 → 返回 `nil`/`false`，**不抛 Lua 错误**：
//      `Isaac.GetItemConfig():GetCollectible(id)` 在 Mod 里"缺件"是常态。
//
// **只做只读**：本批次不提供任何写引擎内存的接口（PC 也没有：`ItemConfig` 的 Lua 侧是只读视图）。
// ★ `kItemConfigMaximumItems` 的定义在**本文件开头**（批次 195 起）—— `player.QueuedItem`
//   那一支比这里早，需要同一个上限；两处各写一份就会漂移。
constexpr std::size_t kItemConfigMaximumStringLength = 4096;  // libc++ 串的长度上限

// 读一条 `std::vector<ItemConfig::Item*>`。向量在 `IC` 上占相邻两个 u64（反汇编里每个 getter
// 的第一条指令都是 `ldp`），所以"步长 8 / 非空 / 有上限"这三条检查就是全部判据。
bool ReadItemVector(std::uintptr_t owner, std::uintptr_t beginOffset, std::uintptr_t endOffset,
                    ItemVectorView* view) noexcept {
    if (view == nullptr || beginOffset > endOffset || owner > UINTPTR_MAX - endOffset) {
        return false;
    }
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!ReadEngine(owner + beginOffset, &begin) || !ReadEngine(owner + endOffset, &end)) {
        return false;
    }
    if (begin == 0 || end <= begin || (end - begin) % sizeof(std::uintptr_t) != 0) {
        return false;
    }
    const std::size_t count = static_cast<std::size_t>((end - begin) / sizeof(std::uintptr_t));
    if (count > kItemConfigMaximumItems) {
        return false;
    }
    view->begin = begin;
    view->end = end;
    view->count = count;
    return true;
}

// 整条链路：基址 → `g_Manager` 槽 → `Manager*` → 内嵌 `ItemConfig`。返回 0 = **链路本身**
// 拿不到（基址未发布 / 槽不可读 / `Manager` 为空 / 偏移越界）。
//
// ★★ **2026-09-12 关键修正：不再把"收藏品向量此刻不可读"当成"拿不到 ItemConfig"。**
//
// 真机证据（报告 `01789226184`，模块指纹 `777E4394…` 与本地构建一致）：EID 的
// `main.lua:37` 是 `EID.itemConfig = Isaac.GetItemConfig()`，而那次会话的
// **"最后调用的 API" = 位 17（`Isaac.GetItemConfig`）、主掩码调用总数 = 1** ——
// 也就是说 EID 在**加载期**只调用了这一个 API，紧接着的
// `EID.itemConfig:GetCollectible(...)` 就断了。原因是旧实现要求"收藏品向量可读"
// （`begin != 0 && end > begin`），而在**主界面/还没开局**时那个向量还没建立
// （`begin == 0`）⇒ 我们返回 `nil` ⇒ EID 的下一次 `Index` 直接报
// `attempt to index a nil value`，且门面在返回前就返回了，**整个 EID 起不来**。
//
// PC 语义对照：`Isaac.GetItemConfig()` 返回引擎的 `ItemConfig` 单例，**永远不是 nil**
// （`analysis/isaacdocs-snapshot/docs/Isaac.md`）。所以：
//   * 这里只负责"对象拿得到拿不到"；
//   * "向量此刻有没有内容"交给**每次调用现读**的 getter（`ValidatedItemConfig` 已改成现读，
//     见它的注释），这样句柄也不会因为跨帧的向量重建而失效。
std::uintptr_t ResolveItemConfig(bool* chainResolved = nullptr) noexcept {
    if (chainResolved != nullptr) {
        *chainResolved = false;
    }
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameManagerGlobalSlotOffset) {
        return 0;
    }
    // 两级解引用：槽里是**指针变量**（`g_Manager` 自己的地址），解一次才是 `Manager*`。
    std::uintptr_t managerSlot = 0;
    std::uintptr_t manager = 0;
    if (!ReadEngine(base + kGameManagerGlobalSlotOffset, &managerSlot) || managerSlot == 0 ||
        !ReadEngine(managerSlot, &manager) || manager == 0 ||
        manager > UINTPTR_MAX - kManagerItemConfigOffset) {
        return 0;
    }
    if (chainResolved != nullptr) {
        *chainResolved = true;
    }
    return manager + kManagerItemConfigOffset;
}

void PushItemConfigHandle(lua_State* state, std::uintptr_t config, const ItemVectorView& view,
                         bool itemsWereReadable) {
    auto* handle = static_cast<ItemConfigHandle*>(lua_newuserdata(state, sizeof(ItemConfigHandle)));
    handle->config = engine_memory::AsObject(config);
    handle->items = engine_memory::AsObject(view.begin);
    handle->count = static_cast<std::uint64_t>(view.count);
    handle->itemsWereReadable = itemsWereReadable ? 1U : 0U;
    handle->reserved = 0;
    luaL_getmetatable(state, kItemConfigMetatable);
    lua_setmetatable(state, -2);
}

void PushItemConfigItemHandle(lua_State* state, std::uintptr_t item, std::uintptr_t beginOffset,
                              std::uintptr_t itemsBegin, std::size_t index) {
    auto* handle =
        static_cast<ItemConfigItemHandle*>(lua_newuserdata(state, sizeof(ItemConfigItemHandle)));
    handle->item = engine_memory::AsObject(item);
    handle->items = engine_memory::AsObject(itemsBegin);
    handle->beginOffset = static_cast<std::uint32_t>(beginOffset);
    handle->index = static_cast<std::uint32_t>(index);
    luaL_getmetatable(state, kItemConfigItemMetatable);
    lua_setmetatable(state, -2);
}

// PC GetItemConfig返回Manager内嵌单例。内部vector扩容/追加/重建不改变父对象身份；
// getter必须读取当前vector。具体Item/列表句柄仍按自己的元素/归属验证，不能混为一谈。
std::uintptr_t ValidatedItemConfig(const ItemConfigHandle* handle) noexcept {
    if (handle == nullptr) return 0;
    const std::uintptr_t config = ResolveItemConfig();
    return config != 0 && config == engine_memory::AddressOf(handle->config) ? config : 0;
}

// 条目句柄 → 通过校验的 `ItemConfig::Item*`（0 = 失效）。校验是"它仍然是这条向量的那个元素"，
// 而不是"这个地址看起来可读"：条目就是向量元素（`ldr x0,[begin, w1, uxtw #3]` 是反汇编里
// 四个 getter 的共同形态），所以这条判据同时覆盖了"换局后向量重排"与"指针被改坏"两种情况。
// 2026-10-18：原生 GetCollectible(0x3C0C50) 对负的32位ID转到
// Game+0x345F18；GetProceduralItem(0x448F38)取 vector[~id]->ItemConfig。
// 特殊来源沿用现有句柄大小；items保存所属Game，不因追加道具导致vector扩容而失效。
constexpr std::uint32_t kProceduralItemConfigOffset = UINT32_MAX;
bool ReadProceduralItem(std::uint32_t id, std::uintptr_t* item,
                        std::uintptr_t* owner) noexcept {
    if (item == nullptr || owner == nullptr || (id & 0x80000000U) == 0) return false;
    const std::uintptr_t game = ResolveGameAddress();
    if (game == 0 || game > UINTPTR_MAX - 0x345F20U) return false;
    ItemVectorView view{};
    const std::uint32_t index = ~id;
    std::uintptr_t descriptor = 0;
    if (!ReadItemVector(game, 0x345F18U, 0x345F20U, &view) || index >= view.count ||
        !ReadEngine(view.begin + static_cast<std::size_t>(index) * sizeof(std::uintptr_t),
                    &descriptor) || descriptor == 0 ||
        !ReadEngine(descriptor, item) || *item == 0) return false;
    *owner = game;
    return true;
}

std::uintptr_t ValidatedItem(const ItemConfigItemHandle* handle) noexcept {
    if (handle == nullptr) {
        return 0;
    }
    const std::uintptr_t config = ResolveItemConfig();
    const std::uintptr_t item = engine_memory::AddressOf(handle->item);
    // `beginOffset` 是 u32（句柄里存不下别的），所以"偏移 + 8"不会回绕；这里只拒 0 配置与空条目。
    if (config == 0 || item == 0) {
        return 0;
    }
    if (handle->beginOffset == kProceduralItemConfigOffset) {
        std::uintptr_t current = 0, owner = 0;
        return ReadProceduralItem(~handle->index, &current, &owner) && current == item &&
                       owner == engine_memory::AddressOf(handle->items) ? item : 0;
    }
    ItemVectorView view{};
    if (!ReadItemVector(config, handle->beginOffset, handle->beginOffset + sizeof(std::uintptr_t),
                        &view)) {
        return 0;
    }
    if (view.begin != engine_memory::AddressOf(handle->items) ||
        handle->index >= view.count) {
        return 0;
    }
    std::uintptr_t current = 0;
    if (!ReadEngine(view.begin + static_cast<std::size_t>(handle->index) * sizeof(std::uintptr_t),
                    &current)) {
        return 0;
    }
    return current == item ? item : 0;
}

// libc++ `std::string`（SSO）的**内容视图**（`data`/`size` 指向引擎内存里那串字节）。
//
// 布局（`ItemConfig::Item::GetDisplayName` 的 `ldrb w8,[x21,#0x8]!` + `lsr x9,x8,#1` 就是硬证据）：
//   * byte0 的 bit0 = `is_long`；
//   * 短串：data 内联在 `+0x01`、size = `byte0 >> 1`（libc++ 的 size 左移一位存放）；
//   * 长串：size 在 `+0x08`、data 指针在 `+0x10`。
// **不是 `const char*`** —— 上一版把它当 `const char*` 读，拿到的就是 SSO 头两个字节。
struct LibcxxStringView {
    std::uintptr_t data;
    std::size_t size;
};

// 读一个 libc++ `std::string` 的内容（**不做任何 Lua 操作**）。
//
// ★ 这是 SSO 口径的**唯一一份**实现：字段读取（`PushLibcxxString`）与
// `Isaac:GetCostumeIdByPath` 的逐字比对都走它 —— 两处各抄一份就会漂移，而这里漂移的后果是
// "比对口径与引擎不一致 ⇒ 返回 -1 ⇒ 模组拿 -1 去 `AddNullCostume` ⇒ 崩"（见 `isaac_api.cpp`
// 里 `IsaacGetCostumeIdByPath` 的注释与 `dist/specialist-costume-field-static.md` §E8）。
//
// 口径（与原 `PushLibcxxString` **逐行相同**，证据见该文件 §一）：
//   首字节 bit0 == 0 ⇒ **短串**（长度 = 首字节 >> 1，内容从字段 `+1` 起）；
//   bit0 == 1 ⇒ **长串**（长度在字段 `+0x8`、数据指针在字段 `+0x10`）。
// 空串：`allowEmpty` 为真时算"合法且为空"（`size == 0`），否则判读不到。
bool ResolveLibcxxString(std::uintptr_t object, bool allowEmpty, LibcxxStringView* view) noexcept {
    if (view == nullptr) {
        return false;
    }
    std::uint8_t first = 0;
    if (!ReadEngine(object, &first)) {
        return false;
    }
    std::uintptr_t data = 0;
    std::size_t size = 0;
    if ((first & 1U) != 0) {
        std::uint64_t length = 0;
        std::uintptr_t pointer = 0;
        if (!ReadEngine(object + 8, &length) || !ReadEngine(object + 0x10, &pointer)) {
            return false;
        }
        if (length == 0) {
            if (!allowEmpty) {
                return false;
            }
        } else {
            if (pointer == 0 || length > kItemConfigMaximumStringLength) {
                return false;
            }
            data = pointer;
            size = static_cast<std::size_t>(length);
        }
    } else {
        const std::size_t length = static_cast<std::size_t>(first >> 1);
        if (length == 0) {
            if (!allowEmpty) {
                return false;
            }
        } else {
            data = object + 1;
            size = length;
        }
    }
    if (size != 0 && !IsEngineMemoryReadable(data, size)) {
        return false;
    }
    view->data = data;
    view->size = size;
    return true;
}

// libc++ `std::string`（SSO）→ Lua 字符串。SSO 口径只有一份（`ResolveLibcxxString`），这里只负责压栈。
//
// `allowEmpty`：`Name`/`Description` 的空串仍按"读不到"处理（调用方当 nil），但
// `GfxFileName` 的空串是**合法值** —— PC 上它是普通 `std::string` 字段，空串表示"没有自定义图集"，
// 引擎自己的解析器也只对 `gfx` 属性做 `append`。EID 的
// `spriteDummy:ReplaceSpritesheet(1, item.GfxFileName)`（`features/eid_api.lua:1278`）就是这条语义：
// 拿到 nil 会被我们的参数校验拒绝并抛 Lua 错误，拿到 `""` 则是"清掉这一层"的正常调用。
bool PushLibcxxString(lua_State* state, std::uintptr_t object, bool allowEmpty = false) noexcept {
    LibcxxStringView view{};
    if (!ResolveLibcxxString(object, allowEmpty, &view)) {
        return false;
    }
    if (view.size == 0) {
        lua_pushliteral(state, "");
        return true;
    }
    // 字节原样交给 Lua（不假设 UTF-8）：Repentance 的 `Name`/`Description` 返回的是 `#KEY`
    // 形状的资源键，EID 这类 Mod 就是拿它去查字符串表的。
    lua_pushlstring(state, static_cast<const char*>(engine_memory::AsObject(view.data)), view.size);
    return true;
}

// `Isaac.GetCostumeIdByPath(string path)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:190`
// （同页 `:192` 明写"返回该服装的 CostumeID；**找不到返回 -1**"，还写明数据来自 `costumes2.xml`）。
//
// 语义（Switch 侧我们只主张这一条，见 `tools/api_definition_of_done.json` 的边界那一栏）：
// **遍历 null 道具向量**（`IC+0x30/+0x38`），取每个条目 `+0x88` 的 libc++ 串与入参**逐字节**比较，
// 命中 ⇒ 返回该条目 `+0x04`（≡ 它在向量里的下标，证据见 `runtime_constants.hpp` 的
// `kItemConfigItemNullCostumePathOffset` 注释）；未命中 ⇒ 返回 `-1`（契约明文）。
//
// ★ 为什么"逐字"而不是"路径归一化后比"：引擎写入侧只是 `memcpy(anm2root)` + `append(anm2path)`
//   （没有任何大小写/前后缀改写）⇒ 只有同一口径才比得上。差的后果是真实的：返回 `-1` 会让模组去调
//   `AddNullCostume(-1)`，而 `GetNullItem(-1)` 是空 ⇒ `AddCostume` 解引用空指针
//   （`dist/specialist-costume-field-static.md` §E8）⇒ **口径一致不是锦上添花**。
//
// ★ 已知边界（同时写进四栏台账）：**只搜 null 向量**。`costumes2.xml` 里
//   `type=passive/active/familiar/trinket` 的条目把路径挂在**收藏品/饰品**条目上
//   （`LoadCostumes` 的另一条分支），PC 那条 API 会不会也搜那几条向量，**Switch 二进制里查不到**
//   （PC 那半边在 exe 的绑定层）⇒ 本实现只覆盖"取 null 服装 id"这个用法（官方教程里这条 API 的
//   唯一用法，`analysis/isaacdocs-snapshot/docs/tutorials/AddingCostumesWithoutLUA.md:83`）。
//
// 参数口径：PC 的绑定层用 `luaL_checklstring`（数字会被 Lua 自动转成串）⇒ 我们**照抄它**，
// 不自己收紧成"必须是字符串"（比 PC 严会把本该发生的调用变成 Lua 报错、进而摘掉整条回调）。
// 这是本 API 里**唯一**没有反汇编/契约依据的一处，如实写在这里。
int IsaacGetCostumeIdByPath(lua_State* state) {
    std::size_t length = 0;
    const char* path = luaL_checklstring(state, 1, &length);
    lua_Integer result = -1;  // PC 契约：找不到就是 -1（不是 nil）
    const std::uintptr_t config = ResolveItemConfig();
    // 批次 141（2026-09-26）：这一格是"模组那 23 条到底在不在引擎的容器里"的直接证据。
    // `0xFFFFFFFF` = 那条链当时读不到（**不是**"容器空"）—— 两者必须能分开。
    std::uint32_t nullItemCount = 0xFFFFFFFFu;
    // 空串不可能命中任何条目（引擎侧 `AddCostume` 对空串也是"直接返回不做"），直接给 -1。
    if (config != 0 && length != 0) {
        ItemVectorView view{};
        if (ReadItemVector(config, kItemConfigNullItemBeginOffset, kItemConfigNullItemEndOffset,
                           &view)) {
            nullItemCount = static_cast<std::uint32_t>(view.count);
            for (std::size_t index = 0; index < view.count; ++index) {
                std::uintptr_t item = 0;
                if (!ReadEngine(view.begin + index * sizeof(std::uintptr_t), &item) || item == 0) {
                    continue;  // 空槽（引擎的向量里本来就有）
                }
                LibcxxStringView stored{};
                if (!ResolveLibcxxString(item + kItemConfigItemNullCostumePathOffset, false,
                                         &stored)) {
                    continue;  // 空串/读不到 ⇒ 这一条不可能是它
                }
                // 逐字节比较（**不**做大小写/前后缀归一化，与引擎写入侧逐条同口径）。
                // 地址 → 指针走 L1 层已有的 `engine_memory::AsObject`（层里"整数地址 → 不透明指针"
                // 的唯一一处转换），不在调用点再写一次 `reinterpret_cast`（冻结台账按文件计数、只许减）。
                if (stored.size != length ||
                    std::memcmp(engine_memory::AsObject(stored.data), path, length) != 0) {
                    continue;
                }
                std::uint32_t id = 0;
                if (ReadEngine(item + kItemConfigItemIdOffset, &id)) {
                    result = static_cast<lua_Integer>(id);
                    break;
                }
            }
        }
    }
    // 批次 141：把"查了几次 / 中没中 / 中的是几 / 容器里有几条"记进常驻计数器（住 bss、
    // 读数工具按符号直读）。模组在**文件作用域**就查这 23 条 ⇒ 一进游戏这几格就有值。
    RecordCostumePathLookup(result >= 0, static_cast<std::uint32_t>(result), nullItemCount);
    lua_pushinteger(state, result);
    return 1;
}

// `Manager*`：`ResolveItemConfig` 那条链的**前半段**（基址 → `g_Manager` 槽 → `Manager*`）。
// 单独抽出来是因为批次 148 的曲目表在 `Manager + kManagerMusicOffset` 上，与 `ItemConfig` 同一个
// `Manager`；两处各写一遍两级解引用就会漂移。返回 0 = 链路本身拿不到。
std::uintptr_t ResolveManagerAddress() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameManagerGlobalSlotOffset) {
        return 0;
    }
    std::uintptr_t managerSlot = 0;
    std::uintptr_t manager = 0;
    if (!ReadEngine(base + kGameManagerGlobalSlotOffset, &managerSlot) || managerSlot == 0 ||
        !ReadEngine(managerSlot, &manager)) {
        return 0;
    }
    return manager;
}

// 名字来自 EntityConfig::Player.name，原始 name 而非本地化显示名。
// GetPlayer @0x700CC 使用内嵌 vector<Player> (+0x18/+0x20)，步长0x178；
// InitPlayerSkin @0x27AAE4 从 Manager+0x36758 取同一个 EntityConfig。
int EntityPlayerGetName(lua_State* state) {
    if (!EntityPlayerProbeNoArguments(state, "EntityPlayer:GetName")) return 0;
    auto* handle = CheckEntityHandle(state, 1);
    const auto player = ValidatedEntityPlayer(handle);
    const auto manager = ResolveManagerAddress();
    std::int32_t type = -1;
    std::uintptr_t begin = 0, end = 0;
    if (player != 0 && manager != 0 &&
        manager <= UINTPTR_MAX - kManagerEntityConfigOffset - kEntityConfigPlayerArrayEndOffset &&
        ReadEngine(player + kEntityPlayerTypeOffset, &type) && type >= 0) {
        const auto config = manager + kManagerEntityConfigOffset;
        if (ReadEngine(config + kEntityConfigPlayerArrayBeginOffset, &begin) &&
            ReadEngine(config + kEntityConfigPlayerArrayEndOffset, &end) &&
            begin != 0 && end >= begin &&
            (end - begin) % kEntityConfigPlayerStride == 0 &&
            static_cast<std::uintptr_t>(type) < (end - begin) / kEntityConfigPlayerStride) {
            const auto row = begin + static_cast<std::uintptr_t>(type) * kEntityConfigPlayerStride;
            if (PushLibcxxString(state, row + kEntityConfigPlayerNameOffset, true)) return 1;
        }
    }
    PushNil(state);  // 失效句柄或配置不可读；正常角色不能走这一支。
    return 1;
}

// `Isaac.GetMusicIdByName(string musicName)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:290`
// （同页 `:292` 逐字：*"Returns the MusicID of a music track. (File: music.xml) Returns `-1` if no
// music with that name could be found."*，`:298` 的例子 `GetMusicIdByName("Title Screen")` → **61**）。
//
// ★ 为什么"编号 = 表内下标"（不是猜的，有两条静态证据）：
//   1. `Music::Play(eMusic, float) @ 0x427238` 就是 `条目 = *(Music + 0x3D8) + id * 0x70`
//      （`umaddl x21, w19, w10(0x70), x8`）⇒ 引擎自己把 id 当下标用；
//   2. 契约那个例子（`"Title Screen"` → 61）与内置 `music.xml` 的行序吻合 ⇒ 编号就是行序。
//   所以本实现遍历 `Music + 0x3D8` 的 `vector<Music::Entry>`（步长 `0x70`），
//   把每个条目**起点**那段 libc++ 串与入参逐字节比较，命中就返回**下标**。
//   名字字段为什么在条目起点：见 `runtime_constants.hpp` 的 `kMusicEntryNameStringOffset` 注释
//   （两条读路径都不碰 `+0x00..+0x1F`，而写路径把 `name` 属性 assign 进一段串）。
//
// ★ 边界（同时写进四栏台账）：
//   * 只认**逐字节相等**（与引擎写入侧同一口径：`LoadConfig` 只是把 `name` 属性原样存下来）；
//   * 表读不到 / 形状不对 ⇒ 返回 `-1`（契约里"找不到"的那一支），并把这**区分开**记进埋点
//     （`g_IsaacMusicIdTableCount == 0xFFFFFFFF` 表示"链读不到"，不是"表是空的"）。
//
// 参数口径与 `IsaacGetCostumeIdByPath` 一致：PC 的绑定层用 `luaL_checklstring`
// （数字会被 Lua 自动转成串）⇒ 我们照抄，不自己收紧成"必须是字符串"。
int IsaacGetMusicIdByName(lua_State* state) {
    std::size_t length = 0;
    const char* name = luaL_checklstring(state, 1, &length);
    std::int32_t result = -1;                  // PC 契约：找不到就是 -1（不是 nil）
    std::uint32_t tableCount = 0xFFFFFFFFu;    // "链读不到"（不是"表空"）
    const std::uintptr_t manager = ResolveManagerAddress();
    // 空串不可能命中任何曲目（引擎侧也不会有空名字的 track），直接给 -1。
    if (manager != 0 && manager <= UINTPTR_MAX - kManagerMusicOffset && length != 0) {
        const std::uintptr_t music = manager + kManagerMusicOffset;
        std::uintptr_t begin = 0;
        std::uintptr_t end = 0;
        if (ReadEngine(music + kMusicEntryVectorBeginOffset, &begin) &&
            ReadEngine(music + kMusicEntryVectorEndOffset, &end) && begin != 0 && end >= begin &&
            (end - begin) % kMusicEntrySize == 0) {
            const std::size_t count = (end - begin) / kMusicEntrySize;
            if (count <= kMusicEntryMaximumCount) {
                tableCount = static_cast<std::uint32_t>(count);
                for (std::size_t index = 0; index < count; ++index) {
                    const std::uintptr_t entry = begin + index * kMusicEntrySize;
                    LibcxxStringView stored{};
                    if (!ResolveLibcxxString(entry + kMusicEntryNameStringOffset, false, &stored)) {
                        continue;  // 空名字/读不到 ⇒ 这一条不可能是它
                    }
                    if (stored.size != length ||
                        std::memcmp(engine_memory::AsObject(stored.data), name, length) != 0) {
                        continue;
                    }
                    result = static_cast<std::int32_t>(index);
                    break;
                }
            }
        }
    }
    // 常驻埋点（住 bss、读数工具按裸名直读）：它回答"模组的 `content/music.xml` 进引擎了没有"
    // （`g_IsaacMusicIdTableCount` 119 = 没进，>119 = 进了）与"反查有没有用"。
    RecordMusicIdLookup(result, tableCount, name);
    lua_pushinteger(state, result);
    return 1;
}


// `Isaac.GetSoundIdByName(string soundName)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:424`
// （`#### [SoundEffect](enums/SoundEffect.md) GetSoundIdByName ( string soundName )`，正文逐字：
// *"Returns the SoundEffect of a sound based on its name. (File: sounds.xml) Returns `-1` if no
// sound with that name could be found."*）。
//
// 语料用法（`IsaacOnTwitchReloaded/scripts/sounds.lua:11` 起 8 条、`MusicModCallback`、
// `BOIStageAPI15`，共 29 处）都在**脚本顶层**就把名字换成编号存进自己的表：
// `sounds.list.bitsAppear = Isaac.GetSoundIdByName("BitsAppear")` ⇒ 缺它就是
// "attempt to call a nil value (field 'GetSoundIdByName')" ⇒ **整条回调被摘掉**。
//
// ★ 与 `IsaacGetMusicIdByName` **同一套做法**（同一个 `Manager`、同一种 `std::vector<T>`）：
//   遍历 `Manager + kManagerSoundEffectsOffset` 那张 `vector<SoundEffect>`（步长 `0x1F0`），
//   把每条 `+0x1D8` 的 libc++ 串与入参逐字节比较，命中返回**下标**。
//   偏移与"编号 == 下标"的证据全部写在 `runtime_constants.hpp` 的批次 265 段
//   （最强的一条：`SoundEffects::Play @ 0x4A2FD0` 自己就 `cmp count, id` —— 引擎把 id 当下标索引这张表）。
//
// ★ 边界（与曲目那条**完全一致**，同时写进四栏台账）：
//   * 只认**逐字节相等**（引擎写入侧 `LoadConfig` 只是把 `name` 属性原样 `assign` 进去）；
//   * 空串直接 -1（引擎侧不会有无名音效）；
//   * 表读不到 / 形状不对 ⇒ **-1**（契约里"找不到"的那一支），**不抛错**；
//   * 参数按 `luaL_checklstring`（数字会被 Lua 转成串）—— 与 PC 的绑定层同口径。
//
// ★ 本批**没有**为它新增埋点（曲目那条有 `RecordMusicIdLookup`）：那份埋点当初是为了回答
//   "模组的 `music.xml` 到底进引擎了没有"（批次 142–149c 的一个具体故障），而音效表这边
//   同一个问题可以用**一条控制台命令**问出来（拿模组自带的音效名反查，见作业单第九节的 V10）
//   ⇒ 不为它再开一份 bss 埋点与读数口径。
int IsaacGetSoundIdByName(lua_State* state) {
    std::size_t length = 0;
    const char* name = luaL_checklstring(state, 1, &length);
    std::int32_t result = -1;  // PC 契约：找不到就是 -1（不是 nil）
    const std::uintptr_t manager = ResolveManagerAddress();
    if (manager != 0 && manager <= UINTPTR_MAX - kManagerSoundEffectsOffset && length != 0) {
        const std::uintptr_t soundEffects = manager + kManagerSoundEffectsOffset;
        std::uintptr_t begin = 0;
        std::uintptr_t end = 0;
        if (ReadEngine(soundEffects + kSoundEffectVectorBeginOffset, &begin) &&
            ReadEngine(soundEffects + kSoundEffectVectorEndOffset, &end) && begin != 0 &&
            end >= begin && (end - begin) % kSoundEffectSize == 0) {
            const std::size_t count = (end - begin) / kSoundEffectSize;
            if (count <= kSoundEffectMaximumCount) {
                for (std::size_t index = 0; index < count; ++index) {
                    const std::uintptr_t entry = begin + index * kSoundEffectSize;
                    LibcxxStringView stored{};
                    if (!ResolveLibcxxString(entry + kSoundEffectNameStringOffset, false, &stored)) {
                        continue;  // 空名字/读不到 ⇒ 这一条不可能是它
                    }
                    if (stored.size != length ||
                        std::memcmp(engine_memory::AsObject(stored.data), name, length) != 0) {
                        continue;
                    }
                    result = static_cast<std::int32_t>(index);
                    break;
                }
            }
        }
    }
    lua_pushinteger(state, result);
    return 1;
}


// `ItemConfig_Item` 的字段。返回 false = "不是这个对象的字段或读不出来"，让调用方继续找方法。
//
// ★ `Type` = `+0x00` 是 PC 的 **`ItemType`**（`0/1/2/3/4 = NULL/PASSIVE/TRINKET/ACTIVE/FAMILIAR`），
// 不是"向量类别"：`items.xml` 的 `type` 属性就是被解析器原样写进这个字段的
// （`ItemConfig::Load` 的 `"passive"→1`/`"trinket"→2`/`"active"→3`/`"familiar"→4`/`"null"→0`，
// 逐条反汇编证据在 `runtime_constants.hpp` 的 `kItemConfigItemTypeOffset` 注释里）。
// 所以 EID 的 `descObj.ItemType = itemConfig.Type`（`features/eid_api.lua:782`）本来就是对的，
// 本批次**没有改这个偏移**，只把常量名与注释从"kind/类别"改成真实语义。
// 引擎侧**没有**另一个"这个条目属于哪条向量"的字段：向量身份来自它从哪条 `std::vector` 取出，
// 所以没有 `ItemKind` 这个名字可用（原先的 `1 = COLLECTIBLE` 是误读）。
bool PushItemField(lua_State* state, std::uintptr_t item, const char* field) noexcept {
    if (std::strcmp(field, "ID") == 0) {
        std::uint32_t value = 0;
        if (!ReadEngine(item + kItemConfigItemIdOffset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    if (std::strcmp(field, "Type") == 0) {
        std::uint32_t value = 0;
        if (!ReadEngine(item + kItemConfigItemTypeOffset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    if (std::strcmp(field, "Name") == 0) {
        return PushLibcxxString(state, item + kItemConfigItemNameOffset);
    }
    if (std::strcmp(field, "Description") == 0) {
        return PushLibcxxString(state, item + kItemConfigItemDescriptionOffset);
    }
    // `GfxFileName`：PC 文档里的 `string` 字段，EID 在
    // `features/eid_api.lua:1278` 把它直接喂给 `Sprite:ReplaceSpritesheet`。
    // 空串按合法值返回（见 `PushLibcxxString` 的 `allowEmpty` 注释）。
    if (std::strcmp(field, "GfxFileName") == 0) {
        return PushLibcxxString(state, item + kItemConfigItemGfxFileNameOffset, true);
    }
    // `Quality` / `CraftingQuality`（2026-09-16）：EID 靠它们显示道具品质
    // （`features/eid_api.lua:2702` → `main.lua:663` 的 `{{QualityN}}`）与做背包合成排序
    // （`eid_bagofcrafting.lua:393/407`）。缺了这两个字段的症状是**静默的**：`desc.Quality`
    // 为 nil 被 `and` 短路，品质图标直接不显示，既不报错也没有日志 —— 这正是"缺口账本
    // 只统计方法、字段从没被枚举过"留下的洞（见 `docs/错误复盘.md` 2026-09-16）。
    // 偏移证据见 `runtime_constants.hpp` 的 `kItemConfigItemQualityOffset` 注释。
    // 两个都是 32 位整数；`CraftingQuality` 在 `items.xml` 未指定时由引擎用 `Quality` 回填，
    // 所以这里**照读原值**，不自己编缺省（读不到时按"字段读不出来"降级成 nil，交给 Mod 的
    // `or` 兜底，与 PC 的 `item.CraftingQuality or item.Quality` 写法一致）。
    if (std::strcmp(field, "Quality") == 0) {
        std::uint32_t value = 0;
        if (!ReadEngine(item + kItemConfigItemQualityOffset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    if (std::strcmp(field, "CraftingQuality") == 0) {
        std::uint32_t value = 0;
        if (!ReadEngine(item + kItemConfigItemCraftingQualityOffset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    // 2026-09-16 第二批（字段缺口台账里的 planned 项，同在 `items.xml` 属性分派表上）：
    // `AchievementID` / `Tags` / `MaxCharges` / `ChargeType`。
    // 逐个的偏移依据见 `runtime_constants.hpp` 里那四个常量的注释（都是同一条链上的 `str`）。
    // **有符号 / 无符号是按 PC 文档定的，不是随手选的**：
    //   * `AchievementID` 文档写 int 且"默认可解锁时返回 -1"，EID 直接与 `-1` 比较
    //     （`features/eid_api.lua:2003`）⇒ 无符号读会让它永远不相等；
    //   * `MaxCharges` / `ChargeType` 也是 int ⇒ 有符号读（-1 这类哨兵值不丢）；
    //   * `Tags` 是**位掩码**（EID 用 `item.Tags & ItemConfig.TAG_QUEST`）⇒ 无符号读，
    //     第 31 位不会被符号扩展污染成"高 32 位全 1"。
    if (std::strcmp(field, "AchievementID") == 0) {
        std::int32_t value = 0;
        if (!ReadEngine(item + kItemConfigItemAchievementIdOffset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    if (std::strcmp(field, "Tags") == 0) {
        // ★ 批次 195（2026-09-29）：**8 字节无符号**读（`Item + 0xC0`）。
        // 原来的 4 字节读有两处错：① 偏移是 `0x58`（那是 items.xml 的 `maxhearts=`，不是 tags）；
        // ② 宽度只有 4 字节 ⇒ PC 的 `TAG_NO_EDEN`（`1<<32`）永远读不到。
        // 证据（写点唯一 + 三个读者 + 8 字节清零）逐条见 `runtime_constants.hpp` 的
        // `kItemConfigItemTagsOffset`。
        //
        // ★ 为什么按**无符号**推给 Lua：PC 文档写 `int`，但值是位掩码；第 31 位若按有符号读会被
        // 符号扩展污染、第 32 位会被截掉 —— EID/RepentancePlus 用的都是 `Tags & TAG_X` 这种位与。
        std::uint64_t value = 0;
        if (!ReadEngine(item + kItemConfigItemTagsOffset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    if (std::strcmp(field, "MaxCharges") == 0) {
        std::int32_t value = 0;
        if (!ReadEngine(item + kItemConfigItemMaxChargesOffset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    if (std::strcmp(field, "ChargeType") == 0) {
        std::int32_t value = 0;
        if (!ReadEngine(item + kItemConfigItemChargeTypeOffset, &value)) {
            return false;
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        return true;
    }
    // `Hidden`（2026-09-16，第三批）：PC 文档写的是 `boolean`，引擎里就是 `+0xB7` 的**一个字节**
    // （`ItemConfig::Item::IsAvailable` 第一条指令 `ldrb w8,[x0,#0xb7]`）⇒ 按字节读、压成布尔，
    // **不要**按 4 字节整数读（会把后面 3 个字节的无关内容当成真值）。
    // EID 的两处用法：`eid_api.lua:2008` 的 `if item.Hidden then`（隐藏道具不出描述）、
    // `eid_api.lua:1927` Spindown Dice 预测里的 `not item.Hidden`（缺这个字段时那一半恒真）。
    if (std::strcmp(field, "Hidden") == 0) {
        std::uint8_t value = 0;
        if (!ReadEngine(item + kItemConfigItemHiddenOffset, &value)) {
            return false;
        }
        lua_pushboolean(state, value != 0 ? 1 : 0);
        return true;
    }
    return false;
}

ItemConfigHandle* CheckItemConfigHandle(lua_State* state, int index) {
    return static_cast<ItemConfigHandle*>(luaL_checkudata(state, index, kItemConfigMetatable));
}

ItemConfigItemHandle* CheckItemConfigItemHandle(lua_State* state, int index) {
    return static_cast<ItemConfigItemHandle*>(
        luaL_checkudata(state, index, kItemConfigItemMetatable));
}

// `GetCollectible`/`GetTrinket`/`GetCard`/`GetPillEffect` 的共同实现：句柄校验 → 向量读取 →
// 下标边界 → 条目句柄。
//
// 负下标一律返回 nil：引擎的 `GetCollectible` 对 `id < 0` 会 `tbz w1,#0x1f` 转发到
// `ProceduralItemManager::GetProceduralItem`（`*(g_Game) + 0x345F18`），我们**不支持程序化道具**
// （那需要一整套 ProceduralItemManager 视图），所以直接 nil —— 编一个条目出来比返回 nil 更糟。
// 注意 `GetTrinket` 在引擎里是 `and w1, w1, #0x7fff`（负值会绕成正下标），我们**不复制**这个
// 行为：负 id 在这里同样是 nil。
// id 参数的解析口径：与 PC 的 `luaL_checkinteger` **同一接受范围**（整数、整值浮点如 `1.0`、
// 可转换的数字串都收；`1.5`/`'nope'`/缺参数都不收），区别只在**不收时返回 nil 而不是抛错**。
bool ReadItemId(lua_State* state, int index, lua_Integer* id) noexcept {
    if (id == nullptr || lua_gettop(state) < index) {
        return false;
    }
    int isNumber = 0;
    const lua_Integer value = lua_tointegerx(state, index, &isNumber);
    if (isNumber == 0) {
        return false;
    }
    *id = value;
    return true;
}

int ItemConfigGetEntry(lua_State* state, std::uintptr_t beginOffset, std::uintptr_t endOffset) {
    auto* handle = CheckItemConfigHandle(state, 1);
    lua_Integer requested = 0;
    const std::uintptr_t config =
        ReadItemId(state, 2, &requested) ? ValidatedItemConfig(handle) : 0;
    if (config == 0 || requested < 0) {
        RecordItemConfigResult(false);  // 探针：EID 的 hasDescription 会因为这里恒空而恒假
        lua_pushnil(state);
        return 1;
    }
    ItemVectorView view{};
    if (!ReadItemVector(config, beginOffset, endOffset, &view) ||
        static_cast<std::uint64_t>(requested) >= static_cast<std::uint64_t>(view.count)) {
        RecordItemConfigResult(false);
        lua_pushnil(state);
        return 1;
    }
    const std::size_t index = static_cast<std::size_t>(requested);
    std::uintptr_t item = 0;
    if (!ReadEngine(view.begin + index * sizeof(std::uintptr_t), &item) || item == 0) {
        RecordItemConfigResult(false);
        lua_pushnil(state);
        return 1;
    }
    RecordItemConfigResult(true);
    PushItemConfigItemHandle(state, item, beginOffset, view.begin, index);
    return 1;
}

int ItemConfigGetCollectible(lua_State* state) {
    RecordFilterChain(3U);  // 过滤器链：`ItemConfig.GetCollectible`
    auto* handle = CheckItemConfigHandle(state, 1);
    lua_Integer requested = 0;
    // PC thunk把Lua整数转换为32位int；同时接受实体字段暴露的u32表示。
    // 超出signed/u32 ID域的值仍按无效请求处理，不让64位值绕成已存在道具。
    if (ReadItemId(state, 2, &requested) && requested >= INT32_MIN &&
        requested <= static_cast<lua_Integer>(UINT32_MAX) &&
        (static_cast<std::uint32_t>(requested) & 0x80000000U) != 0) {
        std::uintptr_t item = 0, owner = 0;
        const auto id = static_cast<std::uint32_t>(requested);
        if (ValidatedItemConfig(handle) != 0 && ReadProceduralItem(id, &item, &owner)) {
            RecordItemConfigResult(true);
            PushItemConfigItemHandle(state, item, kProceduralItemConfigOffset, owner, ~id);
        } else {
            RecordItemConfigResult(false);
            lua_pushnil(state);
        }
        return 1;
    }
    return ItemConfigGetEntry(state, kItemConfigCollectibleBeginOffset,
                              kItemConfigCollectibleEndOffset);
}

// ---- 批次 343（2026-10-04）：两张"列表"（`GetCollectibles` / `GetTrinkets`）----------------
//
// PC 契约（`tools/pc_contract_docs/` 里**没有** `ItemConfig.md`；全文在
// `analysis/isaacdocs-snapshot/docs/ItemConfig.md`，而 `analysis/` 是 gitignore 的 ⇒
// 台账的 `contract` 栏引的是快照路径 + 行号，见那两行的说明）：
//   * `GetCollectibles()` 返回 **`userdata`**，正文**明说是 bug**（在这张 list 上 `Get()` 返回
//     不可用的 userdata），例子只用 `.Size`；
//   * `GetTrinkets()` 返回 `ItemConfigList`（userdata，带 `.Size` / `:Get(i)` / `#`）。
//
// ⇒ 我们返回一张 **`{Size = 条目数, Get = 函数}`** 的表：`.Size` 与 `:Get(i)` 与 PC **同形**
//   （语料**只用到 `Size`**：`IsaacOnTwitchReloaded/scripts/helper.lua:124` 与 `:149`、
//   `isaac-planetarium-chance/main.lua:14` 的 `.Size - 1`），但 `#` 不受支持（表没有数组部分）。
//   ★ 这一处差异（"表 vs 列表对象、且 `#` 不支持"）**已写进完成定义台账的边界栏**，不藏着。
//   ★ 为什么不建一个 Userdata 列表视图：那要新增句柄类型 + 元表 + 六到七处接线
//     （照批次 330 给 `EntityFamiliar` 建视图那笔账），而语料一个 `#` 都不用
//     ⇒ 先按最省的形状落地，等真有模组用 `#` 再升级（升级时只改这两个处理器）。

//: `Get(i)` 的处理器（i **0 基**，与 `ItemConfig:GetCollectible(i)` 同一口径）。
//: 三个上值：① `itemsBegin`（lightuserdata，向量首地址的位模式）、② `beginOffset`（整数）、
//: ③ `count`（整数）。★ 这是本项目第一处"用上值携带列表上下文"的处理器 ——
//: 之所以不放进注册表：这张表是**每次调用现造**的，上值随表一起被回收，不需要额外生命周期管理。
// 2026-10-09更正：上面的table方案已退役；PC真实列表是实时const userdata。
// PC注册0x816910：CppContainer.Vector.ItemConfigList，Size/#同调0x4174C0，
// Get的const thunk0x85FA60以luaL_checkinteger读取第2参，native0x843AE0按u32索引。
// 原生Get返回指针槽地址导致PC文档所述不可用userdata；这里保留可用条目句柄。
constexpr const char* kItemConfigListMetatable = "IsaacRuntime.ItemConfigList";
constexpr const char* kApi600CardListMetatable="IsaacRuntime.CardConfigList";
constexpr const char* kApi600PillListMetatable="IsaacRuntime.PillConfigList";
struct ItemConfigListHandle {
    std::uintptr_t config;
    std::uintptr_t beginOffset;
    std::uintptr_t endOffset;
};

ItemConfigListHandle* CheckConfigList(lua_State*L,int i){
 for(const char*mt:{kItemConfigListMetatable,kApi600CardListMetatable,kApi600PillListMetatable})if(auto*p=luaL_testudata(L,i,mt))return static_cast<ItemConfigListHandle*>(p);
 luaL_argerror(L,i,"ItemConfig list expected");return nullptr;
}
bool ReadItemConfigList(const ItemConfigListHandle* handle, ItemVectorView* view) noexcept {
    if (handle == nullptr || view == nullptr || handle->config == 0 ||
        ResolveItemConfig() != handle->config) { return false; }
    std::uintptr_t begin = 0, end = 0;
    if (!ReadEngine(handle->config + handle->beginOffset, &begin) ||
        !ReadEngine(handle->config + handle->endOffset, &end) || end < begin ||
        (begin == 0 && end != 0) || begin % alignof(std::uintptr_t) != 0 ||
        (end - begin) % sizeof(std::uintptr_t) != 0) { return false; }
    const std::size_t count = (end - begin) / sizeof(std::uintptr_t);
    if (count > kItemConfigMaximumItems) { return false; }
    *view = {begin, end, count};
    return true;
}

std::uintptr_t ConfigRootIdentity(lua_State* state,int index) noexcept {
    if(lua_rawlen(state,index)!=sizeof(ItemConfigHandle))return 0;
    return ValidatedItemConfig(static_cast<const ItemConfigHandle*>(lua_touserdata(state,index)));
}
std::uintptr_t ConfigListIdentity(lua_State* state,int index) noexcept {
    if(lua_rawlen(state,index)!=sizeof(ItemConfigListHandle))return 0;
    const auto*handle=static_cast<const ItemConfigListHandle*>(lua_touserdata(state,index));
    ItemVectorView view{};
    return ReadItemConfigList(handle,&view)&&handle->config<=UINTPTR_MAX-handle->beginOffset
        ?handle->config+handle->beginOffset:0;
}

int ItemConfigListGet(lua_State* state) {
    const auto* handle = CheckConfigList(state,1);
    const std::uint32_t index = static_cast<std::uint32_t>(luaL_checkinteger(state, 2));
    ItemVectorView view{};
    if (!ReadItemConfigList(handle, &view)) {
        return luaL_error(state, "ItemConfigList is no longer available");
    }
    if (index >= view.count) {
        return luaL_error(state, "ItemConfigList index out of range");
    }
    std::uintptr_t item = 0;
    if (!ReadEngine(view.begin + static_cast<std::size_t>(index) * sizeof(std::uintptr_t), &item)) {
        return luaL_error(state, "ItemConfigList entry is not readable");
    }
    if (item == 0) { lua_pushnil(state); return 1; }
    PushItemConfigItemHandle(state, item, handle->beginOffset, view.begin, index);
    return 1;
}

int ItemConfigListLength(lua_State* state) {
    const auto* handle = CheckConfigList(state,1);
    ItemVectorView view{};
    if (!ReadItemConfigList(handle, &view)) {
        return luaL_error(state, "ItemConfigList is no longer available");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(view.count));
    return 1;
}

int ItemConfigListIndex(lua_State* state) {
    static_cast<void>(CheckConfigList(state,1));
    const char* key = lua_tostring(state, 2);
    if (key != nullptr && std::strcmp(key, "Size") == 0) { return ItemConfigListLength(state); }
    if (key != nullptr && std::strcmp(key, "Get") == 0) { lua_pushcfunction(state, ItemConfigListGet); return 1; }
    lua_pushnil(state);
    return 1;
}

int ItemConfigListNewIndex(lua_State* state) {
    static_cast<void>(CheckConfigList(state,1));
    return luaL_error(state, "ItemConfigList is read-only");
}

int PushItemConfigList(lua_State* state, std::uintptr_t beginOffset, std::uintptr_t endOffset) {
    const auto* owner = CheckItemConfigHandle(state, 1);
    const std::uintptr_t config = ResolveItemConfig();
    if (config == 0 || config != engine_memory::AddressOf(owner->config)) {
        return luaL_error(state, "ItemConfig is no longer available");
    }
    auto* handle = static_cast<ItemConfigListHandle*>(lua_newuserdata(state, sizeof(ItemConfigListHandle)));
    *handle = {config, beginOffset, endOffset};
    luaL_getmetatable(state, beginOffset==kItemConfigCardBeginOffset?kApi600CardListMetatable:beginOffset==kItemConfigPillEffectBeginOffset?kApi600PillListMetatable:kItemConfigListMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int ItemConfigGetCollectibles(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ItemConfig:GetCollectibles accepts no arguments");
    }
    return PushItemConfigList(state, kItemConfigCollectibleBeginOffset,
                              kItemConfigCollectibleEndOffset);
}

int ItemConfigGetTrinkets(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ItemConfig:GetTrinkets accepts no arguments");
    }
    return PushItemConfigList(state, kItemConfigTrinketBeginOffset, kItemConfigTrinketEndOffset);
}

int ItemConfigGetTrinket(lua_State* state) {
    return ItemConfigGetEntry(state, kItemConfigTrinketBeginOffset, kItemConfigTrinketEndOffset);
}

int ItemConfigGetCard(lua_State* state) {
    return ItemConfigGetEntry(state, kItemConfigCardBeginOffset, kItemConfigCardEndOffset);
}

int ItemConfigGetPillEffect(lua_State* state) {
    return ItemConfigGetEntry(state, kItemConfigPillEffectBeginOffset,
                              kItemConfigPillEffectEndOffset);
}

// `ItemConfig:IsCollectible(id)`：**收藏品向量里存在这个条目，并且它的 `Type == ITEM_PASSIVE(1)`**。
//
// ★ 这是本实现自己的判据（PC 文档里只有 `ItemConfig_Item:IsCollectible()` 与静态的
// `ItemConfig.IsValidCollectible(id)`），**且它带着一个已知偏差**：`+0x00` 其实是 `ItemType`
// （见 `kItemConfigItemTypeOffset` 的证据），所以"要求 == 1"等价于**"必须是被动道具"**——
// 主动道具（`ITEM_ACTIVE == 3`）与跟班（`ITEM_FAMILIAR == 4`）会被判成 false。
// 引擎自己的 `ItemConfig::IsValidCollectible(eCollectibleType)`（`0x3C0D64`）只判"存在"。
//
// 为什么本批次**没改**它：这是已被验收的既有行为（`runtime/tests/test_lua_item_config.py`
// 的 `wrong_kind` 场景按"kind==1"断言），而 EID **不调用**它（EID 调的是条目级的
// `ItemConfig_Item:IsCollectible()`，见下面那个新实现），所以它不构成 EID 的阻断项。
// 是否把两者统一成"存在且 `Type != ITEM_NULL`"留给主线程决定（改动是一行判据 + 一个场景）。
//
// 我们**不调用**引擎方法：只读向量 + 一个字段即可判定，且宿主可测。
// 2026-10-09更正：PC Item::IsCollectible @0x59FCC0只认Type 1/3/4，
// 饰品2与未知类型均false；原“!=NULL”与“仅PASSIVE”两条判据均已证伪。
bool IsCollectibleItemType(std::uint32_t type) noexcept {
    return type == kItemTypePassive || type == kItemTypeActive || type == kItemTypeFamiliar;
}

int ItemConfigIsCollectible(lua_State* state) {
    auto* handle = CheckItemConfigHandle(state, 1);
    lua_Integer requested = 0;
    const bool argumentValid = ReadItemId(state, 2, &requested) && requested >= 0;
    const std::uintptr_t config = argumentValid ? ValidatedItemConfig(handle) : 0;
    bool exists = false;
    std::uint32_t type = kItemTypeNull;
    if (config != 0) {
        ItemVectorView view{};
        if (ReadItemVector(config, kItemConfigCollectibleBeginOffset,
                           kItemConfigCollectibleEndOffset, &view) &&
            static_cast<std::uint64_t>(requested) < static_cast<std::uint64_t>(view.count)) {
            std::uintptr_t item = 0;
            if (ReadEngine(view.begin + static_cast<std::size_t>(requested) * sizeof(std::uintptr_t),
                           &item) &&
                item != 0 && ReadEngine(item + kItemConfigItemTypeOffset, &type)) {
                exists = true;
            }
        }
    }
    lua_pushboolean(state, (exists && IsCollectibleItemType(type)) ? 1 : 0);
    return 1;
}

// `HasTags` 一族（批次 195，2026-09-29：**从"恒 false 的没证据桩"改成真实现**）。
//
// 口径 = **引擎自己三处同形**的"任一命中"：`(Tags & mask) != 0`
// （规格 `analysis/api-restore-itemconfig/spec.json` 的 `has_tags_semantics`）：
//   * `ItemConfig::IsTaggedCollectible @ 0x3C0E58`：`ldr x8,[x0,#0xc0]` + `tst x8,x19` + `cset w0,ne`；
//   * `ItemConfig::IsTaggedTrinket  @ 0x3C0EF0`：同一条口径（饰品向量元素上同一个 `+0xC0`）；
//   * `ItemConfig::GetTaggedItems  @ 0x3C1F2C/0x3C2014`：`tst x9,x23` + `b.eq <跳过这一条>`
//     —— 这是**引擎自己活着用的**那条（按 tag 位建每 tag 缓存向量）。
//
// ★ 为什么**不**改调引擎的 `ItemConfig::GetTaggedItems(u64)`：那个函数在入口做**单比特定位**
//   （`0x3C1E08..0x3C1E90`），掩码多于一位或为 0 会走错误分支 ⇒ 直接读字段最稳。
// ★ 掩码按 **64 位**收：`ItemConfig.TAG_NO_EDEN = 1<<32`，按 int32 截断会变成 0。
// ★ 参数不是整数 ⇒ 报 Lua 错误（与 PC 绑定层的 `luaL_checkinteger` 同形）；
//   条目句柄失效 / 字段读不到 ⇒ `false`（"不知道 ⇒ 没有这个标签"，绝不抛错）。
int ItemConfigItemHasTags(lua_State* state) {
    auto* handle = CheckItemConfigItemHandle(state, 1);
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "ItemConfig_Item:HasTags expects one tag mask");
    }
    lua_Integer mask = 0;
    if (!ReadItemId(state, 2, &mask)) {
        return luaL_error(state, "ItemConfig_Item:HasTags expects an integer tag mask");
    }
    const std::uintptr_t item = ValidatedItem(handle);
    std::uint64_t tags = 0;
    if (item == 0 || !ReadEngine(item + kItemConfigItemTagsOffset, &tags)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    lua_pushboolean(state, (tags & static_cast<std::uint64_t>(mask)) != 0 ? 1 : 0);
    return 1;
}

// `ItemConfig:HasTags(id, tags)` —— **我们自己的门面便捷形式**（PC 文档里没有这条：
// `tools/pc_contract_docs/` 下没有 `ItemConfig.md`，快照版也没有 HasTags）。
//
// 口径（由我们定义，写在这里以便复核）：`id` 按**收藏品向量**索引（与同族的
// `ItemConfig:IsCollectible(id)` / `ItemConfig:GetCollectible(id)` 同一条向量、同一个下标口径），
// 然后对那个条目做与上一条**完全相同**的位测试 —— 判据只有一份，两条不会漂。
// 越界 / 空槽 / 非整数 id ⇒ `false`（"这个下标上没有带该标签的条目"）。
int ItemConfigHasTags(lua_State* state) {
    auto* handle = CheckItemConfigHandle(state, 1);
    if (lua_gettop(state) != 3) {
        return luaL_error(state, "ItemConfig:HasTags expects an item id and a tag mask");
    }
    lua_Integer requested = 0;
    lua_Integer mask = 0;
    if (!ReadItemId(state, 2, &requested) || !ReadItemId(state, 3, &mask)) {
        return luaL_error(state, "ItemConfig:HasTags expects integer item id and tag mask");
    }
    const std::uintptr_t config = requested >= 0 ? ValidatedItemConfig(handle) : 0;
    std::uint64_t tags = 0;
    bool found = false;
    if (config != 0) {
        ItemVectorView view{};
        if (ReadItemVector(config, kItemConfigCollectibleBeginOffset,
                           kItemConfigCollectibleEndOffset, &view) &&
            static_cast<std::uint64_t>(requested) < static_cast<std::uint64_t>(view.count)) {
            std::uintptr_t item = 0;
            if (ReadEngine(view.begin + static_cast<std::size_t>(requested) * sizeof(std::uintptr_t),
                           &item) &&
                item != 0 && ReadEngine(item + kItemConfigItemTagsOffset, &tags)) {
                found = true;
            }
        }
    }
    lua_pushboolean(state, (found && (tags & static_cast<std::uint64_t>(mask)) != 0) ? 1 : 0);
    return 1;
}

// `ItemConfig_Item:IsCollectible()`（**无参**，批次 3）：PC 在**条目**上提供这个方法
// （`analysis/isaacdocs-snapshot/docs/ItemConfig_Item.md:42`："Returns if the item is a
// collectible"），EID 直接这么用：`EID.itemConfig:GetCollectible(id):IsCollectible()`
// （`main.lua:669`/`738`/`757`，都在描述文本/池子图标的构建路径上）。缺了它，那些语句会以
// "attempt to call a nil value (method 'IsCollectible')" 打断 `printDescription`。
//
// 判据与 `ItemConfig:IsCollectible(id)` 同源：**句柄仍然有效（条目就是那条向量的那个元素）
// 且 `Type != ITEM_NULL`**。句柄失效/条目为空 → false（"这个句柄不再指向一个收藏品"）。
int ItemConfigItemIsCollectible(lua_State* state) {
    auto* handle = CheckItemConfigItemHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ItemConfig_Item:IsCollectible accepts no arguments");
    }
    const std::uintptr_t item = ValidatedItem(handle);
    std::uint32_t type = kItemTypeNull;
    const bool readable = item != 0 && ReadEngine(item + kItemConfigItemTypeOffset, &type);
    lua_pushboolean(state, (readable && IsCollectibleItemType(type)) ? 1 : 0);
    return 1;
}

// `ItemConfig_Item:IsAvailable()`（批次"IsAvailable 一族"，2026-09-16）：EID 在
// `features/eid_api.lua:1988`、`:2013` 与 `eid_bagofcrafting.lua:826` 三处对**收藏品条目**
// 调它，用来判断"这件道具解锁了没有"（`EID:isCollectibleUnlocked`），进而决定 Spindown Dice
// 与背包合成要不要跳过它 —— 也是让 `AchievementID` / `Tags` 两个字段真正产生可见效果的关键。
//
// PC 契约（`analysis/isaacdocs-snapshot/docs/ItemConfig_Item.md:35-38`）：
// "true = 已解锁；false = 没解锁 **或被 tags 挡掉**"。
//
// 引擎侧对应**三个不同类的函数**，只能按"条目属于哪条向量"分派（句柄里就存着 `beginOffset`）：
//   收藏品 / 饰品 / 其他 `ItemConfig::Item` 条目 → `Item::IsAvailable(long flags, uint)`
//   卡牌条目                                   → `Card::IsAvailable()`
//   药丸条目                                   → `PillEffect::IsAvailable()`
// ⚠️ `flags` 取值是**我们的兼容层定义**（引擎里三个函数没有任何调用点，参数学不到），
// 依据见 `runtime_constants.hpp` 的 `kItemIsAvailableFlags` 注释，并在 `api_deviation.cpp` 登记。
// ⚠️ 2026-09-17 按镜像符号表补正：这个偏移上的原生符号是
// `ItemConfig::Item::IsAvailableEx(unsigned int)`（**一个** `uint` 参数），
// 与 PC 文档写的 `IsAvailable(long flags, uint)` 不同 —— 我们按 PC 契约传的 `x1 = flags`
// 与 `IsAvailableEx` 那一个参数位置一致，多传的 `x2` 引擎不读（反汇编四个分支都没用到）。
// 体检工具据此判"多给参数"（无害提示），见 `tools/engine_abi_backlog.json` 同目录的台账口径。
//
// 降级口径：句柄失效 / 方法拿不到（偏移或入口指纹不对）⇒ 返回 **false**（"这件不可用"）。
// 为什么不给 true：EID 拿 false 的行为是"跳过这件道具"，而给 true 会让未解锁的道具照样出现 ——
// 两种都是猜，但"少显示"比"多显示未解锁内容"更接近 PC 语义，且不会让 Spindown Dice 给出非法结果。
int ItemConfigItemIsAvailable(lua_State* state) {
    auto* handle = CheckItemConfigItemHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ItemConfig_Item:IsAvailable accepts no arguments");
    }
    const std::uintptr_t entry = ValidatedItem(handle);
    if (entry == 0) {
        lua_pushboolean(state, 0);
        return 1;
    }
    // 引擎侧对应**三个不同类的函数**（收藏品/饰品等 `Item` 条目带 flags、卡牌与药丸无参），
    // 条目属于哪条向量由句柄里的 `beginOffset` 决定。三条路径**各取各的地址、各按各的签名调** ——
    // 不再用一个 `kind` 整数在两条签名之间选（那个写法静态核不到 ABI，见 `CallItemIsAvailable` 上方注释）。
    if (handle->beginOffset == kItemConfigCardBeginOffset) {
        const std::uintptr_t method = CardIsAvailableMethod();
        lua_pushboolean(state, method != 0 && CallCardIsAvailable(method, entry) ? 1 : 0);
        return 1;
    }
    if (handle->beginOffset == kItemConfigPillEffectBeginOffset) {
        const std::uintptr_t method = PillEffectIsAvailableMethod();
        lua_pushboolean(state, method != 0 && CallPillEffectIsAvailable(method, entry) ? 1 : 0);
        return 1;
    }
    const std::uintptr_t method = ItemIsAvailableMethod();
    lua_pushboolean(state, method != 0 && CallItemIsAvailable(method, entry) ? 1 : 0);
    return 1;
}

// 批次 242（2026-09-30）：`ItemConfig_Item:IsRune()`（PC 的类名是 `ItemConfig_Card`，见 `isaac_api.hpp`）。
//
// ★ 为什么补：EID 有三处**无保护**地调 `EID.itemConfig:GetCard(id):IsRune()`
//   （`features/eid_bagofcrafting.lua:102`、`eid_itemprediction.lua:327`、`eid_modifiers.lua:1277`）
//   ⇒ 没有它时**每次走到那一行都抛 `attempt to call a nil value (method 'IsRune')`**。
//   真机读数（`dist/gdb-read-20260930-225414.txt`）：EID 的 `MC_POST_RENDER` 占全部托管回调时间的
//   **90%**（779 s / 863 s）、Lua 分配 **1.59 亿次**、采样桶溢出 154 万次 —— 就是"每帧抛错 + 拼错误
//   文本 + 环形记账 + 随后的 GC"这条路的形状；用户看到的正是"进 EID 配置页就卡到 20~30 帧"。
//
// 判据（引擎自己的那只手）：`ItemConfig::Card + 0x58` 是**卡类型**，引擎在 `UseActiveItem` 里
// 处理 `CLEAR_RUNE` 时就拿它跟 `2` 比（`kItemConfigCardTypeOffset` / `kItemConfigCardTypeRune`）。
// 只有**卡牌向量**里的条目才有"是不是符文"这件事 ⇒ 其它向量（药丸/收藏品/饰品）一律 false。
// 读不到就答 false（与 `IsAvailable` 同口径：宁少不多，且绝不抛错）。
int ItemConfigItemIsRune(lua_State* state) {
    auto* handle = CheckItemConfigItemHandle(state, 1);
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "ItemConfig_Card:IsRune accepts no arguments");
    }
    const std::uintptr_t entry = ValidatedItem(handle);
    if (entry == 0 || handle->beginOffset != kItemConfigCardBeginOffset) {
        lua_pushboolean(state, 0);
        return 1;
    }
#if !defined(__SWITCH__)
    if (g_ItemConfigCardIsRuneHostImplementation != nullptr) {
        lua_pushboolean(state, g_ItemConfigCardIsRuneHostImplementation(
                                  engine_memory::AsObject(entry)) ? 1 : 0);
        return 1;
    }
#endif
    std::int32_t cardType = 0;
    if (!IsEngineMemoryReadable(entry + kItemConfigCardTypeOffset, sizeof(cardType)) ||
        !ReadEngine(entry + kItemConfigCardTypeOffset, &cardType)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    lua_pushboolean(state, cardType == kItemConfigCardTypeRune ? 1 : 0);
    return 1;
}


// `__index`：方法 → nil（`ItemConfig` 没有字段，PC 同）。
//
// **方法不因句柄失效而消失**：`config:GetCollectible(id)` 在过期句柄上必须返回 nil，而不是让
// Mod 吃到 `attempt to call a nil value (method 'GetCollectible')` —— 后者更难排查。这与
// `Entity` 的 `HasCollectible` 同一口径：失效句柄上的方法仍然可调用，只是安静地降级。
int ItemConfigIndex(lua_State* state) {
    CheckItemConfigHandle(state, 1);
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    const char* field = lua_tostring(state, 2);
    if (PushMethodFrom(state, kItemConfigMetatable, field)) {
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

int ItemConfigItemIndex(lua_State* state) {
    auto* handle = CheckItemConfigItemHandle(state, 1);
    if (lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    const char* field = lua_tostring(state, 2);
    const std::uintptr_t item = ValidatedItem(handle);
    if(const int pushed=TryPushApi500ConfigField(state,item,handle->beginOffset,field))return pushed;
    if(item)if(const int pushed=TryPushExtendedItemConfigField(state,item,field))return pushed;
    // `MimicCharge`（2026-09-16）：**卡牌与胶囊各有一个**（`+0x64` / `+0x48`），收藏品/饰品没有。
    // 所以它不放在 `PushItemField`（那里只有"条目指针"，不知道是卡还是胶囊），而是放在这里
    // —— 句柄的 `beginOffset` 就是种类判据（与 `IsAvailable` 的分派同一条）。
    if (item != 0 && std::strcmp(field, "MimicCharge") == 0) {
        std::uintptr_t offset = 0;
        if (handle->beginOffset == kItemConfigCardBeginOffset) {
            offset = kItemConfigCardMimicChargeOffset;
        } else if (handle->beginOffset == kItemConfigPillEffectBeginOffset) {
            offset = kItemConfigPillEffectMimicChargeOffset;
        }
        if (offset != 0) {
            std::int32_t value = 0;
            if (!ReadEngine(item + offset, &value)) {
                lua_pushnil(state);
                return 1;
            }
            lua_pushinteger(state, static_cast<lua_Integer>(value));
            return 1;
        }
    }
    if (item != 0 && PushItemField(state, item, field)) {
        return 1;
    }
    if (PushMethodFrom(state, kItemConfigItemMetatable, field)) {
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

// `Isaac.GetItemConfig()`：PC 语义是"拿到引擎的 `ItemConfig` 单例"（EID 的第一句就是它）。
// 拿不到（基址未发布 / 槽不可读 / `Manager` 为空 / 向量非法 / 长度为 0）一律返回 nil，
// **不抛 Lua 错误** —— 与 `Isaac.GetPlayer` 同一口径。
// `Isaac.GetItemConfig()` 的三种结局（2026-09-12 定稿，与测试场景逐条对齐）：
//   * **整条链路拿不到**（基址未发布 / `g_Manager` 槽为 0 / 槽里是空指针）⇒ `nil`。
//     这是"引擎还没准备好"，Mod 必须能拿到 nil 并活下去；测试的 `no_base`/`slot_zero`/
//     `no_manager` 钉的就是这一条。
//   * **链路拿到了、只是收藏品向量此刻还没建立**（`begin == 0`，主界面/加载期）⇒ **返回对象**。
//     PC 上它永远不是 nil；真机报告 `01789226184` 证明 EID 在加载期就取它（`main.lua:37`），
//     返回 nil 会让下一句 `EID.itemConfig:GetCollectible(...)` 报
//     "attempt to index a nil value"，**整个 EID 起不来**。
//   * **链路拿到了、但向量参数明显非法**（长度不是 8 的倍数 / 超过上限）⇒ `nil`：
//     那是"偏移或内存坏了"的信号，编一个空对象只会把问题往后推。
int IsaacGetItemConfig(lua_State* state) {
    RecordApiSequence(17U);
    bool chainResolved = false;
    const std::uintptr_t config = ResolveItemConfig(&chainResolved);
    if (config == 0 || !chainResolved) {
        RecordGetItemConfigForProbe(0U);  // 链路拿不到 → 返回 nil
        lua_pushnil(state);
        return 1;
    }
    ItemVectorView view{};
    const bool itemsWereReadable =
        ReadItemVector(config, kItemConfigCollectibleBeginOffset, kItemConfigCollectibleEndOffset,
                       &view);
    std::uint32_t flags = 1U;  // bit0：链路解析成功
    if (itemsWereReadable) {
        flags |= 2U;  // bit1：向量此刻可读
    } else {
        // 区分"还没建立"（`begin == 0`，合法）与"参数非法"（长度/上限不对，视为坏内存）。
        std::uintptr_t begin = 0;
        std::uintptr_t end = 0;
        const bool vectorFieldsReadable =
            ReadEngine(config + kItemConfigCollectibleBeginOffset, &begin) &&
            ReadEngine(config + kItemConfigCollectibleEndOffset, &end);
        if (!vectorFieldsReadable || begin != 0) {
            RecordGetItemConfigForProbe(flags | 8U);  // bit3：参数非法 → 返回 nil
            lua_pushnil(state);
            return 1;
        }
        flags |= 4U;  // bit2：向量还没建立 → **返回对象**
    }
    RecordGetItemConfigForProbe(flags);
    PushItemConfigHandle(state, config, view, itemsWereReadable);
    return 1;
}

// `Isaac.GetPlayer(index)`：PC 语义是 **0 基**（0 = 玩家 1）。以下情况一律返回 nil，**不抛
// Lua 错误**（本轮的目标正是"被调用时不报错"）：下标越界、元素为空指针、vptr 不匹配、
// 内存不可读、基址尚未发布、参数不是整数或为负数。
int IsaacGetPlayer(lua_State* state) {
    RecordApiSequence(16U);
    std::int64_t index = 0;
    if (lua_gettop(state) >= 1) {
        if (!isaac::runtime::IsIntegerArgument(state, 1)) {
            lua_pushnil(state);
            return 1;
        }
        index = static_cast<std::int64_t>(lua_tointegerx(state, 1, nullptr));
    }
    // 固定PC非法索引回首玩家；复用原单次区间/单元素解析，不遍历整个玩家表。
    const std::uintptr_t player = ResolveEntityPlayer(static_cast<std::size_t>(index), true);
    if (player == 0) {
        g_GetPlayerFailure.fetch_add(1, std::memory_order_relaxed);
        lua_pushnil(state);
        return 1;
    }
    g_GetPlayerSuccess.fetch_add(1, std::memory_order_relaxed);
    PushEntityHandle(state, player, kEntityPlayerMetatable);
    return 1;
}

} // namespace

EnginePlayerArray ResolveEnginePlayerArray() noexcept {
    EnginePlayerArray result{};
    std::uintptr_t begin = 0;
    std::size_t count = 0;
    if (ResolveEntityPlayerBegin(&begin, &count) == 0) {
        return result;  // readable == false：调用方不得把它当成"真的没有玩家"
    }
    // 只发布一个“从头开始每个元素都通过 Entity_Player 校验”的有效前缀。换局/退房过渡期里，
    // `players` 容器的 begin/end 可能已经更新而元素槽尚未清空；如果这里照抄容器 count，
    // `Game:GetNumPlayers()` 会报 1，而 `Isaac.GetPlayer(0)` 已验证失败并返回 nil，EID 随即索引
    // nil。数量 API 与获取 API 必须共享同一个可调用契约，所以遇到首个无效元素就截断。
    std::size_t validCount = 0;
    for (std::size_t index = 0; index < count; ++index) {
        std::uintptr_t player = 0;
        std::uintptr_t vtable = 0;
        if (!ReadEngine(begin + index * sizeof(std::uintptr_t), &player) || player == 0 ||
            !ReadEngine(player, &vtable) || !IsEntityPlayer(player)) {
            break;
        }
        ++validCount;
    }
    result.count = validCount;
    result.readable = true;
    return result;
}

// 批次 140：把"逐元素取玩家"这条链开给 `game_api.cpp`（`Game:GetPlayer`）。
// `ResolveEntityPlayer` 就是 `Isaac.GetPlayer` 用的那一条（基址 → 槽 → `Game*` → 向量区间 →
// 下标 → vptr），所以两条 API 共用同一份判定与同一套阶段码 —— 与 `ResolveEnginePlayerArray`
// 被导出的理由完全相同（真机 `01789207110`：同一个引擎事实不许有第二份解释）。
std::uintptr_t ResolveEnginePlayerAt(std::size_t index) noexcept {
    return ResolveEntityPlayer(index);
}

bool IsEnginePlayerPointer(std::uintptr_t candidate) noexcept {
    return IsEntityPlayer(candidate);
}

// `Isaac.CountEnemies` 最后一次返回的个数（探针读；语义见该函数里的注释）。
std::atomic<std::uint32_t> g_LastCountEnemies{0};

std::uint32_t LastCountEnemiesForProbe() noexcept {
    return g_LastCountEnemies.load(std::memory_order_relaxed);
}

// `Isaac.FindInRadius` 的探针读数出口（语义见 `g_FindInRadius*` 的定义处）。
FindInRadiusProbe FindInRadiusProbeSnapshot() noexcept {
    FindInRadiusProbe probe{};
    probe.calls = g_FindInRadiusCalls.load(std::memory_order_relaxed);
    probe.results = g_FindInRadiusResults.load(std::memory_order_relaxed);
    probe.live = g_FindInRadiusLive.load(std::memory_order_relaxed);
    probe.players = g_FindInRadiusPlayers.load(std::memory_order_relaxed);
    probe.effects = g_FindInRadiusEffects.load(std::memory_order_relaxed);
    probe.roomResolved = g_FindInRadiusRoomOk.load(std::memory_order_relaxed);
    probe.fingerprintOk = g_FindInRadiusFingerprint.load(std::memory_order_relaxed);
    probe.lastMask = g_FindInRadiusLastMask.load(std::memory_order_relaxed);
    probe.lastRadius = g_FindInRadiusLastRadius.load(std::memory_order_relaxed);
    return probe;
}

EnginePlayerChain ReadEnginePlayerChainForProbe() noexcept {
    EnginePlayerChain chain{};
    chain.moduleBase = EngineModuleBase();
    if (chain.moduleBase == 0 || chain.moduleBase > UINTPTR_MAX - kGameOwnerGlobalSlotOffset) {
        return chain;
    }
    if (!ReadEngine(chain.moduleBase + kGameOwnerGlobalSlotOffset, &chain.gameSlot)) {
        chain.gameSlot = 0;
        return chain;
    }
    if (chain.gameSlot == 0 || !ReadEngine(chain.gameSlot, &chain.game)) {
        chain.game = 0;
        return chain;
    }
    if (chain.game > UINTPTR_MAX - kGamePlayerArrayEndOffset) {
        chain.game = 0;
        return chain;
    }
    chain.beginReadable = ReadEngine(chain.game + kGamePlayerArrayBeginOffset, &chain.begin) ? 1u : 0u;
    chain.endReadable = ReadEngine(chain.game + kGamePlayerArrayEndOffset, &chain.end) ? 1u : 0u;
    return chain;
}

EnginePlayerLookup LastEnginePlayerLookupForProbe() noexcept {
    EnginePlayerLookup result{};
    result.firstElement = g_EnginePlayerLookupFirst.load(std::memory_order_relaxed);
    result.second = g_EnginePlayerLookupVtable.load(std::memory_order_relaxed);
    result.count = g_EnginePlayerLookupCount.load(std::memory_order_relaxed);
    result.stage = g_EnginePlayerLookupStage.load(std::memory_order_acquire);
    result.resolverBegin = g_ResolverBegin.load(std::memory_order_relaxed);
    result.resolverEnd = g_ResolverEnd.load(std::memory_order_relaxed);
    return result;
}

namespace {

// --- 安全 stub（返回安全默认值，每成员每会话告警一次）-------------------------

// PC 返回的是一个集合；空表是最安全的近似——Mod 遍历它得到 0 个元素，而不是报错。
// --- 房间实体查询（批次 4，真实现）---------------------------------------------
//
// 两个查询都返回**Lua 数组**（整数键 `1..n`）。拿不到容器 / 指纹不匹配 / 参数不可用时返回
// **空表**，不抛 Lua 错误 —— 与 `Isaac.GetPlayer`/`GetItemConfig` 同一口径；`FindInRadius`
// 在 EID 里是**每帧**都调的（`main.lua:1466`），报错会直接打断渲染。

// 扫描一个实体并判断它是否命中"半径 + 分区掩码"。
bool EntityMatchesRadiusQuery(std::uintptr_t address, double x, double y, double radius,
                              std::uint32_t mask) {
    EntitySnapshot snapshot{};
    if (!CaptureEntityTypeSnapshot(address, &snapshot)) {
        return false;
    }
    if (EntityHasNoQueryFlag(snapshot)) {
        return false;
    }
    if ((ClassifyEntity(snapshot) & mask) == 0) {
        return false;
    }
    // 火焰碰撞会连续查询相同房间；先排除无关分区，再读空间字段。
    // TypeSnapshot 已核对整个实体跨度，半径判据不需要 Index。
    static_cast<void>(ReadEngineUnchecked(address + kEntityPositionOffset, &snapshot.x));
    static_cast<void>(ReadEngineUnchecked(address + kEntityPositionOffset + sizeof(float), &snapshot.y));
    static_cast<void>(ReadEngineUnchecked(address + kEntitySizeOffset, &snapshot.size));
    return EntityMatchesRadius(snapshot, x, y, radius);
}

// `Isaac.FindInRadius(Vector Position, float Radius, EntityPartition Partitions = 0xFFFFFFFF)`
// （`Isaac.md:125`）。分区 → 数据源：
//   * 普通分区（FAMILIAR/BULLET/TEAR/ENEMY/PICKUP）→ 活表 `EL+0x78`；
//   * PLAYER → `Game+0x25C50` 的玩家向量（引擎自己也不走 CellSpace）；
//   * EFFECT → `EL+0xA8` 表。
// 三段都过同一套半径/掩码判据，并用"已推出指针集合"去重（同一实体可能同时出现在玩家向量与
// 活表里）。**不排序**（PC 文档明说"not sorted by nearest first"，按实体加载顺序返回）。
int IsaacFindInRadius(lua_State* state) {
    RecordApiSequence(18U);
    const int argumentCount = lua_gettop(state);
    auto* position = TryVectorArgument(state,1);
    bool valid = position != nullptr && argumentCount >= 2 && argumentCount <= 3 &&
                 lua_isnumber(state, 2) != 0;
    double x = 0.0;
    double y = 0.0;
    double radius = 0.0;
    if (valid) {
        x = static_cast<double>(position->x);
        y = static_cast<double>(position->y);
        radius = static_cast<double>(lua_tonumber(state, 2));
        valid = std::isfinite(radius) && radius >= 0.0;
    }
    std::uint32_t mask = 0xFFFFFFFFU;  // PC 的默认值 = "全部分区"（`Isaac.md:125`）
    if (valid && argumentCount == 3) {
        lua_Integer requested = 0;
        if (!ReadIntegerArgument(state, 3, &requested)) {
            valid = false;
        } else {
            mask = static_cast<std::uint32_t>(requested);
        }
    }
    g_FindInRadiusCalls.fetch_add(1, std::memory_order_relaxed);
    g_FindInRadiusLastMask.store(mask, std::memory_order_relaxed);
    g_FindInRadiusLastRadius.store(
        static_cast<std::uint32_t>(radius) & 0xFFFFFFU, std::memory_order_relaxed);
    g_FindInRadiusResults.store(0, std::memory_order_relaxed);
    lua_newtable(state);
    const int resultIndex = lua_gettop(state);
    ResetQueryDedup();
    if (!valid || mask == 0) {
        return 1;
    }
    const std::uintptr_t room = ResolveRoom();
    g_FindInRadiusRoomOk.store(room != 0 ? 1U : 0U, std::memory_order_relaxed);
    if (room == 0 || !EntityListFingerprintMatches(room + kRoomEntityListOffset)) {
        g_FindInRadiusFingerprint.store(0, std::memory_order_relaxed);
        return 1;
    }
    g_FindInRadiusFingerprint.store(1, std::memory_order_relaxed);
    const std::uintptr_t list = room + kRoomEntityListOffset;
    QuerySink sink{state, resultIndex, 0};
    const auto consider = [&](std::uintptr_t entity) {
        if (EntityMatchesRadiusQuery(entity, x, y, radius, mask)) {
            PushQueryResult(&sink, entity);
        }
    };
    // 探针读数：三个数据源各自命中多少（`QuerySink::emitted` 是已写入 Lua 表的条数）。
    if ((mask & kLiveTablePartitions) != 0) {
        const int before = sink.emitted;
        // visitor 会核对实体可读性及 vptr，迭代器无需再验证同一指针。
        ForEachEntityInTable<false>(list, kLiveEntityTable, consider);
        g_FindInRadiusLive.store(static_cast<std::uint32_t>(sink.emitted - before),
                                 std::memory_order_relaxed);
    }
    if ((mask & kPartitionPlayer) != 0) {
        const int before = sink.emitted;
        ForEachPlayerEntity<false>(ResolveGameAddress(), consider);
        g_FindInRadiusPlayers.store(static_cast<std::uint32_t>(sink.emitted - before),
                                    std::memory_order_relaxed);
    }
    if ((mask & kPartitionEffect) != 0) {
        const int before = sink.emitted;
        ForEachEntityInTable<false>(list, kEffectEntityTable, consider);
        g_FindInRadiusEffects.store(static_cast<std::uint32_t>(sink.emitted - before),
                                    std::memory_order_relaxed);
    }
    g_FindInRadiusResults.store(static_cast<std::uint32_t>(sink.emitted),
                               std::memory_order_relaxed);
    return 1;
}

// `Isaac.FindByType(EntityType Type, int Variant = -1, int SubType = -1, boolean Cache = false,
// boolean IgnoreFriendly = false)`（`Isaac.md:118`）：`Variant`/`SubType` 传 -1 表示通配。
//
// ★ **第 4 个参数是 `Cache`，不是 `Nearest`。** AB+/旧文档把它写成 `Nearest`（"只返回最近
// 一个"），忏悔版（本 Runtime 的目标版本）已经改成纯粹的性能提示（`analysis/isaacdocs-snapshot/
// docs/Isaac.md:118`）。EID 就是按忏悔版写的：`Isaac.FindByType(5, 100, -1, true, false)`
// （`main.lua:366`/`826`/`1133`）要拿**房间里所有**收藏品底座，`EntityType.ENTITY_EFFECT`
// 那一组（`main.lua:1468`）要拿某个效果变体的**所有**实例。所以这里接受该参数但**忽略**它
// （我们每次都直接遍历，没有缓存可言），恒返回全部命中项 —— 按 `Nearest` 实现会让 EID
// 每个变体只剩一个实体，是明确的功能回退。
//
// 第 5 个参数 `IgnoreFriendly` 同样接受但忽略：判"友好"的旗标位没有任何证据
// （`Entity+0x1B8` 里只有 bit3/bit46 有解释），编一个判据比忽略它更糟。
//
// 排除 `FLAG_NO_QUERY`（`+0x1B8` bit46）：PC 文档（`Isaac.md:121`）"If an entity has
// EntityFlag.FLAG_NO_QUERY then it will be excluded from the results"。
int IsaacFindByType(lua_State* state) {
    RecordApiSequence(19U);
    const int argumentCount = lua_gettop(state);
    lua_Integer type = 0;
    lua_Integer variant = -1;
    lua_Integer subType = -1;
    bool valid = argumentCount >= 1 && argumentCount <= 5 &&
                 ReadIntegerArgument(state, 1, &type);
    if (valid && argumentCount >= 2) {
        valid = ReadIntegerArgument(state, 2, &variant);
    }
    if (valid && argumentCount >= 3) {
        valid = ReadIntegerArgument(state, 3, &subType);
    }
    lua_newtable(state);
    const int resultIndex = lua_gettop(state);
    ResetQueryDedup();
    // `type < 0` 永远不匹配（`Entity.Type` 是无符号枚举），与 PC 的比较语义一致。
    if (!valid || type < 0) {
        return 1;
    }
    const std::uintptr_t room = ResolveRoom();
    if (room == 0 || !EntityListFingerprintMatches(room + kRoomEntityListOffset)) {
        return 1;
    }
    const std::uintptr_t list = room + kRoomEntityListOffset;
    QuerySink sink{state, resultIndex, 0};
    const auto matches = [&](const EntitySnapshot& snapshot) {
        if (EntityHasNoQueryFlag(snapshot)) {
            return false;
        }
        if (static_cast<lua_Integer>(snapshot.type) != type) {
            return false;
        }
        if (variant >= 0 && static_cast<lua_Integer>(snapshot.variant) != variant) {
            return false;
        }
        if (subType >= 0 && static_cast<lua_Integer>(snapshot.subType) != subType) {
            return false;
        }
        return true;
    };
    const auto consider = [&](std::uintptr_t entity) {
        EntitySnapshot snapshot{};
        if (CaptureEntityTypeSnapshot(entity, &snapshot) && matches(snapshot)) {
            PushQueryResult(&sink, entity);
        }
    };
    // 三表去重；visitor已核对完整实体/vptr，跳过重复的入口校验。
    ForEachEntityInTable<false>(list, kLiveEntityTable, consider);
    ForEachPlayerEntity<false>(ResolveGameAddress(), consider);
    ForEachEntityInTable<false>(list, kEffectEntityTable, consider);
    return 1;
}

// PC CountEnemies @0x80D300 与 Room:GetAliveEnemiesCount 都读房间的活敌人计数对。
// 不能按NPC类型区间扫描：商店老板/火堆也在该区间，会误触EID HideInBattle。
int IsaacCountEnemies(lua_State* state) {
    RecordApiSequence(20U);
    std::int64_t count = 0;
    // 探针：EID 的 `OnRender` 用 `Isaac.CountEnemies() > 0`（配合 `HideInBattle`）决定是否提前
    // 返回；"描述一个字都没画"必须能看出这个读数是多少。
    struct CountRecorder {
        std::int64_t* target;
        ~CountRecorder() {
            g_LastCountEnemies.store(static_cast<std::uint32_t>(*target),
                                     std::memory_order_relaxed);
        }
    } recorder{&count};
    count = ReadRoomAliveCount(ResolveRoom(), kRoomAliveEnemiesCountOffset);
    lua_pushinteger(state, static_cast<lua_Integer>(count));
    return 1;
}

// PC CountBosses @0x80D330 与 Room:GetAliveBossesCount 读同一对原生Boss计数。
int IsaacCountBosses(lua_State* state) {
    RecordApiSequence(21U);
    lua_pushinteger(state, ReadRoomAliveCount(ResolveRoom(), kRoomAliveBossesCountOffset));
    return 1;
}

// `Isaac.CountEntities(Entity Spawner, EntityType Type = ENTITY_NULL, int Variant = -1,
// int SubType = -1)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:72`，正文 `:74-78` 逐字：
// *"Returns the number of entities in the current room that fulfill the specified requirements."*
// 外加三行参数说明（"Spawner ... can be `nil`" / "Type ... can be `EntityType.ENTITY_NULL`" /
// "Variant and Subtype ... can be `-1`"）。
//
// 语料用法（3 处 / 2 模组，都在回调里，都在**脚本顶层之外的真调用**）：
// `BOIStageAPI15/scripts/stageapi/core/callbacks.lua:2002`
// `Isaac.CountEntities(nil, ENTITY_EFFECT, HEAVEN_LIGHT_DOOR, 0) > 0`；
// `IsaacOnTwitchReloaded/scripts/events.lua:2734` 传**真实体**当生成者（`entity.FrameCount > 15 and
// Isaac.CountEntities(entity, ENTITY_ATTACKFLY, 0, 0) < 35`）；`:3076` 又是 `nil`。
//
// ★ 做法 = **直接调引擎那条成员函数**，不自己遍历实体表。这是本批最强的判据：
//   PC 的绑定函数（`tools/pc_exe_binding.py CountEntities` ⇒ 名字表项 `0x409B12` ⇒ VA `0x80D0D0`）
//   把 4 个实参读全之后只有**一次**成员调用（`this = *(g_Game+0x18190)+0x1218`、`call 0x416640`）；
//   Switch 侧同一个函数是 `EntityList::CountSpawned(Entity*, eEntityType, int, int)` @ **`0x7A1CC`**，
//   它的**通配语义**（`spawner == 0` / `type == 0` / `variant < 0` / `subtype < 0` 各跳过那一格）
//   与比较的四个字段（`+0x38`/`+0x3c`/`+0x40`/`+0x3a8`）逐条对上 PC 文档那三行说明 ——
//   逐行证据在 `runtime_constants.hpp` 的批次 268 段。自己再写一遍遍历就会引入
//   "我们的版本与引擎版本不一致"这个本项目栽过的坑（`Level:GetCurrentRoomDesc` 自造扫描那次）。
//
// ★ 两处**刻意不加工**：
//   ① `Type` 不做"负数直接判不匹配"（`Isaac.FindByType` 上有那一条）。PC 的绑定层不筛，
//      把值原样交给引擎，引擎的 `cmp w11, w2` 是无符号比较 ⇒ 负数自然永不匹配。我们不加
//      比 PC 更严的规则。
//   ② 参数个数只接受 1..4（第 1 格可以是 `nil`）。PC 的缺省值就是 `0 / -1 / -1`，
//      与"少给的那几格保持初始化值"一致，所以少传参数天然走缺省。
//
// ★ 降级（第 11 条纪律：读不到原生状态**不许抛 Lua 错误**）：房间解不出、容器指纹不对、
//   引擎入口不可用 ⇒ **返回 0**。0 是保守那一侧：模组写的都是 `> 0` / `< 35` 这类比较，
//   少报让"还没凑够"多发一轮（可恢复），多报会让它提前收手（不可逆）。
//   参数个数/类型不对仍然报错 —— 那是模组写错了，PC 上也会报。
int IsaacCountEntities(lua_State* state) {
    RecordApiSequence(22U);
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 1 || argumentCount > 4) {
        return luaL_error(state,
                          "Isaac.CountEntities accepts (Spawner[, Type[, Variant[, SubType]]])");
    }
    // 第 1 格：`nil` 是**合法**取值（语料三处里有两处这么写）⇒ 用不抛错的
    // `EntityPointerArgument`，而不是 `CheckEntityHandle`（后者对非句柄直接报错）。
    // 拿不到（nil / 不是句柄 / 指针已失效）就是 0 —— 正好是引擎那条"不看生成者"的取值。
    const std::uintptr_t spawner = EntityPointerArgument(state, 1);
    // 第 2..4 格：缺省值 = 引擎要的三个通配值。读法与 `ReadIntegerArgument` 同口径
    // （模组把枚举值从 JSON 读出来时是 float，`57.0` 必须收）。
    lua_Integer type = 0;
    lua_Integer variant = -1;
    lua_Integer subType = -1;
    if (argumentCount >= 2 && !lua_isnoneornil(state, 2) &&
        !ReadIntegerArgument(state, 2, &type)) {
        return luaL_error(state, "Isaac.CountEntities expects an integer Type");
    }
    if (argumentCount >= 3 && !lua_isnoneornil(state, 3) &&
        !ReadIntegerArgument(state, 3, &variant)) {
        return luaL_error(state, "Isaac.CountEntities expects an integer Variant");
    }
    if (argumentCount >= 4 && !lua_isnoneornil(state, 4) &&
        !ReadIntegerArgument(state, 4, &subType)) {
        return luaL_error(state, "Isaac.CountEntities expects an integer SubType");
    }
    const std::uintptr_t room = ResolveRoom();
    if (room == 0 || !EntityListFingerprintMatches(room + kRoomEntityListOffset)) {
        lua_pushinteger(state, 0);
        return 1;
    }
    const std::uintptr_t list = room + kRoomEntityListOffset;
    const std::uintptr_t method =
        EngineOffsetAddress<IsEngineMemoryReadable>(kEntityListCountSpawnedOffset);
    if (!EngineEntryWordMatches(method, kEntityListCountSpawnedEntryWord)) {
        // 偏移/指纹对不上 ⇒ 压 0（而不是报错）：这一条被模组写在**回调体**里，
        // 报错会把整条回调摘掉（最重的一档后果），而"数不到实体"的后果只是少报一轮。
        lua_pushinteger(state, 0);
        return 1;
    }
    // 跳板（`EngineCallTrampoline`）：`x0 = this`、`x1 = spawner`、`w2/w3/w4 = type/variant/subType`。
    // 用跳板而不是声明一个带类型的函数指针别名，与 `EntityPlayer:HasTrinket` 同一取舍
    // （那处的注释写清了理由）；本条常量在 `tools/engine_abi_backlog.json` 里按 A 类登记
    // （真有消费者、工具读不出我们声明的签名）。
    // ★ 三格按 `int32` 截断后再零扩展进 `uint64`：引擎读的是 `w2/w3/w4`，
    //   所以 `-1` 到那边就是 `0xFFFFFFFF`（= 它要的"通配"）。
    std::uint64_t integers[8] = {
        list,
        spawner,
        static_cast<std::uint64_t>(static_cast<std::int32_t>(type)),
        static_cast<std::uint64_t>(static_cast<std::int32_t>(variant)),
        static_cast<std::uint64_t>(static_cast<std::int32_t>(subType)),
        0,
        0,
        0,
    };
    double floats[8] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    std::uint64_t integerResult = 0;
    double floatResult = 0.0;
    EngineCallTrampoline(method, integers, floats, &integerResult, &floatResult);
    lua_pushinteger(state, static_cast<lua_Integer>(static_cast<std::int32_t>(integerResult)));
    return 1;
}

// --- 坐标变换（批次 195，2026-09-29）------------------------------------------------
//
// PC 契约（`tools/pc_contract_docs/Isaac.md:653` 与 `:638`）与引擎入口的逐条证据见
// `analysis/api-restore-transforms/spec.json`。要点：
//   * 两条 World* **不是恒等变换**（旧实现是 WorldToIdentity + 一次告警），
//     而是调引擎的 `GetRenderPosition(pos, true)`；差别**只有**后面加不加
//     `Room[0x1938] + Game[0x24F9B0]` 那两处偏移。
//   * 引擎调用的**量化**（`true`）不能省：PC 两条都量化（"整数或 .5"就是它的可见后果）。
//   * 算术只有一份实现（`TransformWorldPosition`，`remaining_api.cpp`）—— 与
//     `Room:WorldToScreenPosition` 共用，两处各写一份必然漂。
//
// 失败一律报 Lua 错误（PC 返回 Vector；编一个 (0,0) 会把东西画到屏幕左上角，
// 那是"看起来像是画了、只是位置错"的静默失败）。
int IsaacWorldToScreen(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Isaac.WorldToScreen expects a Vector");
    }
    auto* input = TryVectorArgument(state,1);
    if (input == nullptr) {
        return luaL_error(state, "Isaac.WorldToScreen expects a Vector");
    }
    float screen[2] = {input->x, input->y};
    if (!TransformWorldPosition(&input->x, screen, WorldTransformTarget::kScreen)) {
        return luaL_error(state, "Isaac.WorldToScreen native bindings are unavailable");
    }
    auto* result = static_cast<VectorHandle*>(lua_newuserdata(state, sizeof(VectorHandle)));
    result->x = screen[0];
    result->y = screen[1];
    luaL_getmetatable(state, kVectorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int IsaacWorldToRenderPosition(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Isaac.WorldToRenderPosition expects a Vector");
    }
    auto* input = TryVectorArgument(state,1);
    if (input == nullptr) {
        return luaL_error(state, "Isaac.WorldToRenderPosition expects a Vector");
    }
    float rendered[2] = {input->x, input->y};
    if (!TransformWorldPosition(&input->x, rendered, WorldTransformTarget::kRenderPosition)) {
        return luaL_error(state, "Isaac.WorldToRenderPosition native bindings are unavailable");
    }
    auto* result = static_cast<VectorHandle*>(lua_newuserdata(state, sizeof(VectorHandle)));
    result->x = rendered[0];
    result->y = rendered[1];
    luaL_getmetatable(state, kVectorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// `Isaac.ScreenToWorld(Vector)`（批次 195 新增，catalog `0x0E01005F`）。
//
// PC 契约：`tools/pc_contract_docs/Isaac.md:604` 签名 / `:606` 正文
// （"Transfers Screen (aka. Window coordinates) into World coordinates"）。
// 输入是**窗口像素**（PC 上就是 `Input.GetMousePosition(false)` 给的那一套）；
// Switch 上触摸面板与 framebuffer 同尺寸 ⇒ 原始触摸读数就是窗口像素。
//
// ★ 引擎里**没有**反向入口（穷举见规格的 `no_engine_screen_to_world`），PC 自己也是就地算 ⇒
//   我们照 PC 的算式算，`WIDTH`/`HEIGHT`/`POINTSCALE` 从引擎 GOT 槽**运行期**读。
//
// 退化口径照抄 PC：`g_Game == null`（主菜单/还没进局）或换算常量读不到 ⇒ **原样返回输入**。
// 这里**不报错** —— 它在标题界面会被模组调（`Input.GetMousePosition(true)` 每帧调），
// 报错会把整条回调摘掉，而"原样返回"与 PC 的空指针保护行为逐字一致。
int IsaacScreenToWorld(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Isaac.ScreenToWorld expects a Vector");
    }
    auto* input = TryVectorArgument(state,1);
    if (input == nullptr) {
        return luaL_error(state, "Isaac.ScreenToWorld expects a Vector");
    }
    float world[2] = {input->x, input->y};
    static_cast<void>(TransformScreenToWorldPosition(&input->x, world));
    auto* result = static_cast<VectorHandle*>(lua_newuserdata(state, sizeof(VectorHandle)));
    result->x = world[0];
    result->y = world[1];
    luaL_getmetatable(state, kVectorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

// REPENTOGON LuaPersistentGameData.cpp：getter返回Manager的真实PGD，
// Unlocked参数由luaL_checkinteger转int，查询仍由引擎执行，包括挑战/特殊局规则。
constexpr const char* kPersistentGameDataMetatable = "IsaacRuntime.PersistentGameData";
struct PersistentGameDataHandle { std::uintptr_t manager; };
std::uintptr_t PgdIdentity(lua_State*state,int index) noexcept {
    if(lua_rawlen(state,index)!=sizeof(PersistentGameDataHandle))return 0;
    const auto*handle=static_cast<const PersistentGameDataHandle*>(lua_touserdata(state,index));
    const auto manager=ResolveManagerAddress();
    if(!manager||handle->manager!=manager||manager>UINTPTR_MAX-kManagerPersistentGameDataObjectOffset)return 0;
    const auto address=manager+kManagerPersistentGameDataObjectOffset;
    return IsEngineMemoryReadable(address,sizeof(std::uintptr_t))?address:0;
}

int IsaacGetPersistentGameData(lua_State* state) {
    const auto manager = ResolveManagerAddress();
    if (manager == 0 || manager > UINTPTR_MAX - kManagerPersistentGameDataObjectOffset) {
        PushNil(state); return 1;
    }
    auto* handle = static_cast<PersistentGameDataHandle*>(lua_newuserdata(state, sizeof(PersistentGameDataHandle)));
    handle->manager = manager;
    luaL_getmetatable(state, kPersistentGameDataMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int PersistentGameDataUnlocked(lua_State* state) {
    const auto* handle = static_cast<PersistentGameDataHandle*>(
        luaL_checkudata(state, 1, kPersistentGameDataMetatable));
    const std::uint32_t achievement = static_cast<std::uint32_t>(luaL_checkinteger(state, 2));
    if (handle->manager == 0 || ResolveManagerAddress() != handle->manager ||
        handle->manager > UINTPTR_MAX - kManagerPersistentGameDataObjectOffset) {
        return luaL_error(state, "PersistentGameData is no longer available");
    }
    const auto method = EngineOffsetAddress<IsEngineMemoryReadable>(kPersistentGameDataUnlockedOffset);
    if (!EngineEntryOrRelayMatches<IsEngineMemoryReadable>(
        method, kPersistentGameDataUnlockedExpectedBytes.data(), kPersistentGameDataUnlockedExpectedBytes.size(), 0)) {
        return luaL_error(state, "PersistentGameData:Unlocked native bindings are unavailable");
    }
    std::uint64_t integers[8] = {handle->manager + kManagerPersistentGameDataObjectOffset, achievement, 0, 0, 0, 0, 0, 0};
    double floats[8] = {};
    std::uint64_t integerResult = 0;
    double floatResult = 0;
    EngineCallTrampoline(method, integers, floats, &integerResult, &floatResult);
    lua_pushboolean(state, integerResult != 0 ? 1 : 0);
    return 1;
}

// REPENTOGON实际绑定的三条图鉴查询都要求Type与Variant：luaL_checkinteger后转int。
// 原生函数自行读取EntityConfig并归一化图鉴条目，随后查询真实PGD树；不猜hash或存档表。
int PushPersistentBestiaryCount(lua_State* state, const char* name, std::uintptr_t offset,
                               const std::array<u8, 16>& expected) {
    const auto* handle = static_cast<PersistentGameDataHandle*>(
        luaL_checkudata(state, 1, kPersistentGameDataMetatable));
    const auto type = static_cast<std::uint32_t>(luaL_checkinteger(state, 2));
    const auto variant = static_cast<std::uint32_t>(luaL_checkinteger(state, 3));
    if (handle->manager == 0 || ResolveManagerAddress() != handle->manager ||
        handle->manager > UINTPTR_MAX - kManagerPersistentGameDataObjectOffset) {
        return luaL_error(state, "PersistentGameData is no longer available");
    }
    const auto method = EngineOffsetAddress<IsEngineMemoryReadable>(offset);
    if (!EngineEntryOrRelayMatches<IsEngineMemoryReadable>(method, expected.data(), expected.size(), 0)) {
        return luaL_error(state, "PersistentGameData:%s native bindings are unavailable", name);
    }
    std::uint64_t integers[8] = {handle->manager + kManagerPersistentGameDataObjectOffset,
                                type, variant, 0, 0, 0, 0, 0};
    double floats[8] = {};
    std::uint64_t result = 0;
    double floatResult = 0;
    EngineCallTrampoline(method, integers, floats, &result, &floatResult);
    lua_pushinteger(state, static_cast<std::int32_t>(static_cast<std::uint32_t>(result)));
    return 1;
}

int PersistentGameDataGetBestiaryKillCount(lua_State* state) {
    return PushPersistentBestiaryCount(state, "GetBestiaryKillCount",
        kPersistentGameDataBestiaryKillOffset, kPersistentGameDataBestiaryKillExpectedBytes);
}
int PersistentGameDataGetBestiaryDeathCount(lua_State* state) {
    return PushPersistentBestiaryCount(state, "GetBestiaryDeathCount",
        kPersistentGameDataBestiaryDeathOffset, kPersistentGameDataBestiaryDeathExpectedBytes);
}
int PersistentGameDataGetBestiaryEncounterCount(lua_State* state) {
    return PushPersistentBestiaryCount(state, "GetBestiaryEncounterCount",
        kPersistentGameDataBestiaryEncounterOffset, kPersistentGameDataBestiaryEncounterExpectedBytes);
}

// 2026-10-10：按固定REPENTOGON实际wrapper，AddBestiaryKill返回bool（原文档void保留并更正）。
// 两种写入都交给具名原函数，保留readonly、图鉴归一化、计数及解锁副作用。
std::uintptr_t RequireCurrentPersistentGameData(lua_State* state) {
    const auto* handle = static_cast<PersistentGameDataHandle*>(
        luaL_checkudata(state,1,kPersistentGameDataMetatable));
    if (handle->manager==0 || ResolveManagerAddress()!=handle->manager ||
        handle->manager>UINTPTR_MAX-kManagerPersistentGameDataObjectOffset) {
        luaL_error(state,"PersistentGameData is no longer available");
        return 0;
    }
    return handle->manager+kManagerPersistentGameDataObjectOffset;
}
std::uintptr_t RequirePersistentGameDataEntry(lua_State* state,const char* name,
    std::uintptr_t offset,const std::array<u8,16>& expected) {
    const auto method = EngineOffsetAddress<IsEngineMemoryReadable>(offset);
    if (!EngineEntryOrRelayMatches<IsEngineMemoryReadable>(method,expected.data(),expected.size(),0)) {
        luaL_error(state,"PersistentGameData:%s native bindings are unavailable",name);
        return 0;
    }
    return method;
}
int PersistentGameDataAddBestiaryKill(lua_State* state) {
    const auto object = RequireCurrentPersistentGameData(state);
    const auto type = static_cast<std::uint32_t>(luaL_checkinteger(state,2));
    const auto variant = static_cast<std::uint32_t>(luaL_optinteger(state,3,0));
    const auto method = RequirePersistentGameDataEntry(state,"AddBestiaryKill",
        kPersistentGameDataAddBestiaryKillOffset,kPersistentGameDataAddBestiaryKillExpectedBytes);
    std::uint64_t integers[8] = {object,type,variant,0,0,0,0,0};
    double floats[8]{};
    std::uint64_t result{};
    double floatResult{};
    EngineCallTrampoline(method,integers,floats,&result,&floatResult);
    lua_pushboolean(state,static_cast<std::uint32_t>(result)!=0);
    return 1;
}
std::uint32_t CheckPersistentBossId(lua_State* state,const char* name) {
    // wrapper先转int，再做1..103校验；不能把Lua的64位值直接按103截断拒绝。
    const auto boss = static_cast<std::int32_t>(static_cast<std::uint32_t>(luaL_checkinteger(state,2)));
    if (boss<1 || boss>103) {
        luaL_error(state,"bad argument #2 to '%s' (expected BossType between 1 and 103 inclusive, got %d)",name,boss);
        return 0;
    }
    return static_cast<std::uint32_t>(boss);
}
int PersistentGameDataAddBossKilled(lua_State* state) {
    const auto object = RequireCurrentPersistentGameData(state);
    const auto boss = CheckPersistentBossId(state,"AddBossKilled");
    const auto method = RequirePersistentGameDataEntry(state,"AddBossKilled",
        kPersistentGameDataAddBossOffset,kPersistentGameDataAddBossExpectedBytes);
    std::uint64_t integers[8] = {object,boss,0,0,0,0,0,0};
    double floats[8]{};
    std::uint64_t ignored{};
    double ignoredFloat{};
    EngineCallTrampoline(method,integers,floats,&ignored,&ignoredFloat);
    return 0;
}
int PersistentGameDataIsBossKilled(lua_State* state) {
    const auto object = RequireCurrentPersistentGameData(state);
    const auto boss = CheckPersistentBossId(state,"IsBossKilled");
    // AddBoss是这张真实byte表的写入/读取锚点；入口身份失效就不能沿用字段布局。
    static_cast<void>(RequirePersistentGameDataEntry(state,"IsBossKilled",
        kPersistentGameDataAddBossOffset,kPersistentGameDataAddBossExpectedBytes));
    std::uint8_t killed{};
    if (!engine_memory::ReadField(object,kPersistentGameDataBossKilledOffset+boss,&killed,
                                  IsEngineMemoryReadable)) {
        return luaL_error(state,"PersistentGameData:IsBossKilled data is no longer available");
    }
    lua_pushboolean(state,killed!=0);
    return 1;
}

// `Isaac.GetTrinketIdByName(string trinketName)`（批次 404，2026-10-07 起是**真实现**）。
//
// 历史：批次 240 只做了收藏品 / 卡牌 / 药丸 / 角色 / 挑战五条，**漏了饰品** —— 那时它是一个
// `WarnStubOnce` 空桩（`PushZero`），即 `GetTrinketIdByName("任意名字") == 0`（PC 契约是
// 找不到返回 `-1`）。
// 契约 `tools/pc_contract_docs/Isaac.md:457`：
// `TrinketType GetTrinketIdByName ( string trinketName )`，「Returns the TrinketType of a
// trinket based on its name. (**File: items.xml**) Returns `-1` if no trinket with that name
// could be found」（例子 `"Lucky Toe"` → 42）。
// ⇒ 本批补上本体静态表（`IsaacNameKind::Trinket`，由生成器从 `items.xml` 的 `<trinket>` 提取）
// **加上**同族的运行时追加层（模组 `content/items.xml` 的 `<trinket>`；`Trinity` 的
// `Maggie's Drawing` / `Old Credit Card` / `Fire Killer` 就是它，Mary 的
// `main.lua:64 AddTrinket(Isaa.GetTrinketIdByName("Maggie's Drawing"))` 靠它才能拿到真 id）。
// 静态表先查（本体优先，id 逐值不变），未命中再落到追加层；两者都未命中才是 `-1`。
int IsaacGetTrinketIdByName(lua_State* state) {
    std::size_t length = 0;
    const char* name = luaL_checklstring(state, 1, &length);
    std::int32_t id = LookupIsaacName(IsaacNameKind::Trinket, name, length);
    if (id < 0) {
        id = LookupModContentName(ModContentNameFamily::Trinket, name, length);
    }
    lua_pushinteger(state, id);
    return 1;
}

// `Isaac.GetRoomEntities()`（`Isaac.md:382`："Returns an iterable table containing **all entities
// in the room** at the time the function was called"）。
//
// **真实现**（2026-09-19 批次 041，为 GoodTrip 补）：它的语义与我们 `Isaac.FindByType`
// 那三段扫描完全一致（活表 + 玩家向量 + 效果表，并去重）—— PC 侧这一条本身是 Lua glue
// （`tools/build_lua_api_inventory.py` 把它归成 `lua_glue_type`），所以"照 PC 文档的语义实现"
// 而不是"接一个引擎符号"才是对的。
//
// 为什么 GoodTrip 需要它（`scripts/trip.lua:38/100`）：传送时要把**跟班一起带走**，
// 它遍历这个表挑出跟班与"主人是玩家"的实体。缺它 ⇒ 那一句直接索引 nil ⇒ 传送功能整块不工作。
//
// 降级口径与 `FindByType` 相同：拿不到房间/内存不可读 ⇒ 返回**空表**（不抛错）。
int IsaacGetRoomEntities(lua_State* state) {
    if (lua_gettop(state) != 0) {
        return luaL_error(state, "Isaac.GetRoomEntities accepts no arguments");
    }
    lua_newtable(state);
    const int resultIndex = lua_gettop(state);
    ResetQueryDedup();
    const std::uintptr_t room = ResolveRoom();
    if (room == 0 || !EntityListFingerprintMatches(room + kRoomEntityListOffset)) {
        return 1;
    }
    QuerySink sink{state, resultIndex, 0};
    const std::uintptr_t list = room + kRoomEntityListOffset;
    const auto consider = [&](std::uintptr_t entity) { PushQueryResult(&sink, entity); };
    ForEachEntityInTable(list, kLiveEntityTable, consider);
    ForEachPlayerEntity(ResolveGameAddress(), consider);
    ForEachEntityInTable(list, kEffectEntityTable, consider);
    return 1;
}

// `Isaac.ExecuteCommand(string command)`（PC：把一行命令交给游戏内置控制台，例如
// `Isaac.ExecuteCommand("restart")`；`Isaac.md` 的 ExecuteCommand 一节）。
//
// ★ 历史（041 起）：这里曾是**空桩** —— 当时的结论是"Switch 上没有控制台、也没有等价的命令通道"
//   （`Manager::IsDebuggingConsoleEnabled` 是 `mov w0,wzr; ret` 桩、`Console` 的方法全镜像零引用）。
//   那条结论**只说对了一半**：引擎确实不建、不驱动这个对象，**但类与命令实现都在**（续四十）。
//   ★ 2026-09-21 更正一句错话：这里原写"PC 上它的返回类型是 void，所以『没有返回值』与 PC 一致"，
//   **是错的** —— 契约原文 `tools/pc_contract_docs/Isaac.md:106` 写的是
//   `#### string ExecuteCommand ( string command )`：PC 返回**控制台输出的字符串**。
//   所以 041~120 那段时间我们与 PC 的差别有两条：① 命令不会生效；② **返回值类型不同**。
//   该偏离已按平台固有登记进 `api_deviation.cpp` 的 `0x0E01002D`（批次 121 起这条登记要改口径：
//   限制从"平台没有控制台"变成"命令长度上限 128 字节 / 没有玩家时拒绝执行"）。
//   ★ **2026-09-25（批次 121）起它是真实现**：那条"Switch 上没有控制台"的平台限制**不再成立**——
//   控制台类与全部命令实现一直都在镜像里（只是没被实例化、没接进循环），运行时现在自己建一个
//   `Console` 实例并把命令喂进去（见 `infrastructure/console/console_bridge.hpp` 的头注释，
//   取证过程见 `docs/问题与解决记录.md` 续四十 与当天记录）。
//
//   ★ 具体到那个已知实例：GoodTrip 的 `TAB + R` 快速重开（`scripts/control.lua:61` 的
//     `Isaac.ExecuteCommand("restart")`）在 041~120 期间**不会重开**（那时这条命令是空桩，
//     什么都不做）；批次 121 起命令真的进控制台了，`restart` 是否因此生效**必须在真机上验**
//     —— 别在验证之前就把它当能用（`restart` 会走 `Manager::RestartGame` 那条原版路径，
//     但那需要真机证据，不是看代码能推出来的）。
//
//   形状与 PC 对齐：**返回控制台输出的字符串**（契约原文 `tools/pc_contract_docs/Isaac.md:106`
//   写的是 `string ExecuteCommand(string command)`）。下面两种情况返回**空串**（不是 nil）：
//     * 引擎入口没解析出来（守卫不符 / 基址没发布）；
//     * 命令被拒（空命令 / 长度加 NUL 溢出 / 当前没有玩家 / 输出缓冲已满 / 抓到过对象越界写）。
//   ★ 2026-10-10：127 字节人为限制已移除，桥在同步调用期借用本 Lua 参数；参数仍根在栈上，
//     引擎先复制再分词，不持有输入。没有玩家的欠账保留，不能称整个 API 已完全与 PC 一致。
//   判据都记在控制台自己的状态面（`g_ConsoleState` 的 `lastStatus`）里，真机上可读 ⇒ 不靠猜。
//   ★ 没有玩家时**不调引擎**：引擎在第三参数为 null 时会自己去读 `Game + 0x25C50` 玩家列表的
//     第一个元素且**不判空**（见 `runtime_constants.hpp` 里 `kConsoleRunCommandOffset` 那段），
//     列表为空时那是读空指针。宁可返回空串。
int IsaacExecuteCommand(lua_State* state) {
    if (lua_gettop(state) != 1 || lua_type(state, 1) != LUA_TSTRING) {
        return luaL_error(state, "Isaac.ExecuteCommand accepts one string command");
    }
    std::size_t length = 0;
    const char* command = lua_tolstring(state, 1, &length);
    const std::uintptr_t base = EngineModuleBase();
    if (command == nullptr || base == 0) {
        lua_pushliteral(state, "");
        return 1;
    }
    // 入口解析结果按基址缓存（守卫在解析里逐条核对过；基址变了就重解析）。
    static console::EngineEntries entries{};
    static std::uintptr_t resolvedBase = 0;
    static bool resolved = false;
    if (!resolved || resolvedBase != base) {
        resolved = console::ResolveConsoleEntries(base, kGameModuleRangeCheckSize, &entries);
        resolvedBase = base;
    }
    if (!resolved) {
        lua_pushliteral(state, "");
        return 1;
    }
    // 结论码不用在这里分支：被拒时 `TakeLastOutput` 自然拿不到东西 ⇒ 下面返回空串。
    static_cast<void>(console::ExecuteCommand(entries, base, command, length));
    // 批次 436：控制台命令可能换房（"stage"/"goto" 之类）—— 让房间解析缓存立即失效，
    // 保证同一派发窗口里后续的查询拿到新房间。
    isaac::runtime::InvalidateCurrentRoomCache();
    const char* produced = nullptr;
    std::uint32_t producedLength = 0;
    if (console::TakeLastOutput(&produced, &producedLength)) {
        lua_pushlstring(state, produced, producedLength);
    } else {
        lua_pushliteral(state, "");
    }
    return 1;
}

// `Isaac.GetCallbacks(callbackId[, createIfMissing])`：PC 返回"登记在 callbackId 下的回调表"
// （`analysis/isaacdocs-snapshot/docs/Isaac.md:138`），条目是
// `{ Function = <回调函数>, Mod = <Mod 对象> }`。
//
// 批次 3 起是真实现：
//   * 字符串名 → 命名回调表（`Mod:AddCallback("SOMENAME", fn)` 登记的那些）。
//     EID 的 `features/eid_bagofcrafting_search.lua:49` 与
//     `features/eid_language_manager.lua:81` 就是这个用法；返回空表虽然"不报错"，但会让
//     EID 的名字转换回调永远收不到事件（静默功能缺失），所以这里如实返回。
//   * 数字 id → 我们自己的 `CallbackRegistry`（只含已登记的 (id, owner) 对）。
//
// **永远返回表**（没有登记时是空表）：PC 的同名调用返回 nil 会让 `pairs(...)` 直接报错，
// 而"没有回调"在 PC 上也是空表。第二个参数（`createIfMissing`）我们接受但忽略——
// 我们本来就会为缺失的名字返回一张空表。
// （本函数原先是安全 stub；批次 3 从 stub 名单里移除，见 `Stub` 枚举的注释。）
int IsaacGetCallbacks(lua_State* state) {
    return CallCallbackTableApi(state, "GetCallbacks");
}

// `Isaac.LoadModData(modRef)` / `Isaac.SaveModData(modRef, data)`（PC 文档 `Isaac.md:505,590`）。
//
// 这一层与 `Mod:LoadData()` / `Mod:SaveData(data)` 是**同一件事**：PC 上两组名字读写同一份
// "saveX.dat"，栈形状也一样（Mod 对象在 1、数据在 2）⇒ 直接转调 `mod_api.cpp` 里那两个
// 实现（`mod_api.hpp` 导出），不写第二份持久化逻辑（两份 = 以后必漂）。
//
// **为什么这条值得单独说**：EID 在 `OnGameStart` 里先判 `EID:HasData()`，为真就
// `json.decode(Isaac.LoadModData(EID))`（`main.lua:1873`）。旧的桩**一个值都不返回**（nil），
// 而运行时的 `json.decode` 是 `luaL_checklstring` ⇒ 拿到 nil 直接抛 Lua 错误 ⇒
// **EID 的配置加载当场中断**（不崩、屏幕上没提示，只留一行错误）：用户改过的 EID 设置
// 每次开局都加载不上。
int IsaacLoadModData(lua_State* state) {
    return isaac::runtime::ModLoadData(state);
}

int IsaacSaveModData(lua_State* state) {
    return isaac::runtime::ModSaveData(state);
}

// `Isaac.RenderScaledText(str, X, Y, ScaleX, ScaleY, R, G, B, A)`（`Isaac.md:545`：
// "Renders a scaled text on the Screen"，X/Y 是屏幕坐标，四个颜色分量在 [0,1]）。
//
// 旧实现是安全桩（只告警一次、什么都不画）：EID 的 HUD 调整预览与鼠标坐标调试用的就是它
// （`main.lua:1022/1023/1029`）⇒ 打开那些界面时"一个字都没有"（静默失效）。
//
// 绘制本体在 `font_api.cpp`（字体句柄与绘制探针都归那个 TU）。这里只做参数校验与转调：
// 校验完先把文本复制出来、把数值读进 C 变量，再清栈交给绘制侧（`Font()` 构造器要求空栈，
// 而且清栈后原来的 Lua 字符串可能被回收 —— 绘制那一步会分配内存）。
int IsaacRenderScaledText(lua_State* state) {
    if (lua_gettop(state) != 9 || !lua_isstring(state, 1)) {
        return luaL_error(state,
                          "Isaac.RenderScaledText accepts text, x, y, scaleX, scaleY, "
                          "red, green, blue, alpha");
    }
    for (int index = 2; index <= 9; ++index) {
        if (!lua_isnumber(state, index)) {
            return luaL_error(state,
                              "Isaac.RenderScaledText accepts text, x, y, scaleX, scaleY, "
                              "red, green, blue, alpha");
        }
    }
    std::size_t length = 0;
    const char* raw = lua_tolstring(state, 1, &length);
    const std::string text{raw, length};
    const float x = static_cast<float>(lua_tonumber(state, 2));
    const float y = static_cast<float>(lua_tonumber(state, 3));
    const float scaleX = static_cast<float>(lua_tonumber(state, 4));
    const float scaleY = static_cast<float>(lua_tonumber(state, 5));
    const float red = static_cast<float>(lua_tonumber(state, 6));
    const float green = static_cast<float>(lua_tonumber(state, 7));
    const float blue = static_cast<float>(lua_tonumber(state, 8));
    const float alpha = static_cast<float>(lua_tonumber(state, 9));
    lua_settop(state, 0);
    if (!isaac::runtime::DrawScaledTextWithDefaultFont(state, text.data(), text.size(), x, y,
                                                       scaleX, scaleY, red, green, blue, alpha)) {
        return luaL_error(state, "Isaac.RenderScaledText has no usable screen font");
    }
    return 0;
}

// `Isaac.RenderText(str, X, Y, R, G, B, A)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:561`，
// 正文 `:563` 逐字：「Renders a text with the default size on the Screen. X and Y coordinates need
// to be in screen coordinates ( x[0,~500) y [0,~350) ). R,G,B and A need to be between [0,1].」
//
// 与 `RenderScaledText` 的**唯一**差别就是"默认字号" —— 所以实现就是**同一个函数、缩放传 (1,1)**：
// 不是"另写一条绘制路径"，而是同一条路径换两个参数。★ 这也是本批刻意做的选择：PC 自己就是
// `RenderText` 转调带缩放的版本（同一套字体与度量），我们两处各写一份必然在换行/度量上漂。
//
// ★ 契约正文那句"需要是屏幕坐标"**不做夹取**：PC 不夹，多画到屏幕外就画到屏幕外；
// 我们加一条比 PC 严的规则会让"模组算出来的坐标略微越界"从"看不见"变成"报错摘回调"。
//
// 语料用法（10 处 / 4 模组：BOIStageAPI15、Enhanced-Boss-Bars、RepentancePlus、TBOI_Better-Voiding）
// 都在 `MC_POST_RENDER` 一类回调里，缺它的后果是"整条渲染回调被摘掉"（不是"少画几个字"）。
int IsaacRenderText(lua_State* state) {
    if (lua_gettop(state) != 7 || !lua_isstring(state, 1)) {
        return luaL_error(state, "Isaac.RenderText accepts text, x, y, red, green, blue, alpha");
    }
    for (int index = 2; index <= 7; ++index) {
        if (!lua_isnumber(state, index)) {
            return luaL_error(state,
                              "Isaac.RenderText accepts text, x, y, red, green, blue, alpha");
        }
    }
    // 先把文本复制出来、数值读进 C 变量再清栈：`Font()` 构造器要求空栈，而且清栈后原来的
    // Lua 字符串可能被 GC —— 绘制那一步会分配内存（与 `RenderScaledText` 同一条理由）。
    std::size_t length = 0;
    const char* raw = lua_tolstring(state, 1, &length);
    const std::string text{raw, length};
    const float x = static_cast<float>(lua_tonumber(state, 2));
    const float y = static_cast<float>(lua_tonumber(state, 3));
    const float red = static_cast<float>(lua_tonumber(state, 4));
    const float green = static_cast<float>(lua_tonumber(state, 5));
    const float blue = static_cast<float>(lua_tonumber(state, 6));
    const float alpha = static_cast<float>(lua_tonumber(state, 7));
    lua_settop(state, 0);
    // 契约说的是"默认字号" ⇒ 缩放就是 (1,1)，与 `RenderScaledText` 走同一条绘制路径。
    if (!isaac::runtime::DrawScaledTextWithDefaultFont(state, text.data(), text.size(), x, y, 1.0F,
                                                       1.0F, red, green, blue, alpha)) {
        // ★ 与 `RenderScaledText`（批次 026）**刻意不同**：那条没有字体时**报错**，这条**什么都不画**
        // 并记一笔回退探针。理由 = 第 11 条纪律「读不到原生状态不许抛 Lua 错误」：PC 上这条
        // 根本不会失败，而我们抛错会让**整条渲染回调被摘掉**（语料 10 处调用全在回调里）——
        // 代价是"这个模组的渲染全没了"，比"少画几个字"重得多。
        // （`RenderScaledText` 那条是 2026-10-01 那条纪律之前写的，它自己的门禁钉着"报错"
        //  这个现状；要统一口径应当连同它的门禁一起改，属独立的一批。）
        isaac::runtime::RecordNativeStateFallback(isaac::runtime::kFbIsaacRenderText);
    }
    return 0;
}

// `Isaac.GetTextWidth(str)` —— PC 契约 `tools/pc_contract_docs/Isaac.md:439`（返回 `int`），
// 正文 `:441` 逐字：「Returns the width of the given string in pixels based on the "terminus8"
// font (same font as used in Isaac.RenderText())」。
//
// ★ 契约正文点名的两件事都落在实现上：① 单位是**像素**、② 与 `RenderText` **同一个字体**
// ⇒ 所以这里复用运行时那份默认字体（`MeasureTextWithDefaultFont` 与绘制共用
// `PushDefaultScreenFont`），而不是另开一份 —— 两份字体会让"量出来"和"画出来"对不上。
//
// ★ 参数口径按 PC 的 `luaL_checklstring`（数字会被 Lua 转成串）—— 与 `Isaac.ConsoleOutput`
// 同一条，不自己收紧成"必须是字符串"。
//
// ★ 降级（第 11 条纪律：读不到原生状态**不许抛 Lua 错误**）：没有可用字体 /
// 引擎度量入口不可用 ⇒ 压 **-1**（不是 0、不是 nil）。理由：0 是"这段文字宽 0 像素"这个
// **有意义的答案**，模组会拿它算居中；-1 是数值型里唯一能被"看起来不对"识别的哨兵，
// 而抛错会把整条渲染回调摘掉（语料里 4 处调用全在回调内）。
int IsaacGetTextWidth(lua_State* state) {
    std::size_t length = 0;
    const char* raw = luaL_checklstring(state, 1, &length);
    // helper与Font构造要求空栈；先保有字符串，避免清栈后首次加载/GC使raw失效。
    const std::string text{raw, length};
    lua_settop(state, 0);
    int width = -1;
    if (!isaac::runtime::MeasureTextWithDefaultFont(state, text.data(), text.size(), &width)) {
        isaac::runtime::RecordNativeStateFallback(isaac::runtime::kFbIsaacGetTextWidth);
        width = -1;
    }
    lua_pushinteger(state, static_cast<lua_Integer>(width));
    return 1;
}

// --- 全局函数（批次 4）----------------------------------------------------------

// PC Random直接使用引擎全局RandomU32；保留[0,2^32)的全部整数，包括0。
int GlobalRandom(lua_State* state) {
    std::uint32_t value = 0;
    if (!TryEngineRandomU32(&value)) {
        return luaL_error(state, "Random native random source unavailable");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

// `GetPtrHash(object)`：PC 的"把对象指针变成稳定整数"（`GlobalFunctions.md:143`），
// EID 用它做实体身份比较（`main.lua:492`/`527`/`1473`、`features/eid_api.lua:2387`）。
//
// 实体保持原退役校验和快路径；非实体由各族真实对象解析处理，未知类型不伪造身份。
int GlobalGetPtrHash(lua_State* state) {
    RecordFilterChain(5U);
    // 固定PC 7FCA10只检查参数1是否userdata，忽略后续参数。
    if (!lua_isuserdata(state, 1)) {
        return luaL_error(state, "The parameter is not an user data!");
    }
    // 所有实体子类共享同一识别/lifetime入口，不能只识别三张旧元表。
    const auto* entity=TryGetEntityHandle(state,1);
    const auto pointer = entity ? ValidatedEntity(entity) : isaac::runtime::ResolveNonEntityPointerIdentity(state,1);
    lua_pushinteger(state, static_cast<lua_Integer>(pointer));
    return 1;
}

} // namespace

// ============================================================================
// 字段读取型 API：共享处理器 + 数据行（门禁三期成本压缩，机制说明见 `field_api.hpp`）
// ============================================================================
namespace {

//: 从 Lua 栈上第 `index` 个参数解出接收者对象地址（无效/不可读时返回 0）。
std::uintptr_t ResolveFieldReceipt(lua_State* state, FieldReceipt receipt, int index) {
    switch (receipt) {
        case FieldReceipt::Entity: {
            auto* handle = CheckEntityHandle(state, index);
            return ValidatedEntity(handle);
        }
        case FieldReceipt::EntityPlayer: {
            auto* handle = CheckEntityHandle(state, index);
            return ValidatedEntityPlayer(handle);
        }
        case FieldReceipt::EntityFamiliar: {
            // 批次 330（2026-10-03）：`EntityFamiliar:*` 引擎方法行（`FollowParent` /
            // `AddToFollowers`）的接收者 —— **从栈上取**（与 `EntityPlayer` 同形）：
            // `Entity:ToFamiliar()` 交回的是**真持引擎指针**的 `EntityHandle`。
            //
            // ★★ 为什么必须**精确**判（不能像 `Entity` 那一档只做 vtable 区间校验）：
            //   这两条是**调用**。`Entity_Familiar::follow_parent()` 一进去就
            //   `ldr x8,[x0,#0xf50]` 然后**解引用**它 ⇒ 拿别的实体当 `this` 交进去是**野读**
            //   （读字段那类最多读到别人的值，调函数那类会顺着垃圾指针跑出去）。
            //   ⇒ 判据用 `ValidatedEntityFamiliar`（精确 vptr + 类型），与 `ToFamiliar()` 同一份。
            //   ★ 这条也挡掉了"点号 + 显式 self"那种绕过元表containment的写法
            //     （`familiar.FollowParent(别的实体)`）—— 那种在 PC 上也是把 self 当熟悉体用。
            auto* handle = CheckEntityHandle(state, index);
            return ValidatedEntityFamiliar(handle);
        }
        case FieldReceipt::ItemConfigItem: {
            auto* handle = CheckItemConfigItemHandle(state, index);
            return ValidatedItem(handle);
        }
        case FieldReceipt::GridEntity: {
            // 批次 304（2026-10-03）：`GridEntity:*` 引擎方法行的接收者 —— **从栈上取**。
            // `Room:GetGridEntity(i)` 交回的句柄**真持**引擎指针（`GridEntityHandle`/`DoorHandle`
            // 里的 `entity`），所以与 `Room`/`Music`/`ItemPool` 那几档不同、不需要"算出来"。
            // ★ 判定分两级（与 `Entity` 那一档同形）：
            //   * 不是网格实体句柄 ⇒ `CheckGridEntityHandle` **报错**（参数类型写错了，PC 也会报）；
            //   * 是句柄但底层指针已失效（网格实体随时可能被销毁）⇒ 返回 0 ⇒ 共享处理器**静默降级**。
            void* handle = CheckGridEntityHandle(state, index);
            const std::uintptr_t candidate = engine_memory::AddressOf(handle);
            return IsLiveGridEntityPointer(candidate) ? candidate : 0;
        }
        case FieldReceipt::Room: {
            // 批次 051：`Room` 接收者**不从栈上取** —— 解析"当前房间"。
            // 只服务 `Room:PlayMusic()` 这类"无参数、this = 当前房间"的方法。
            void* room = nullptr;
            if (ReadCurrentGameRoom(LuaRuntime::GameOwnerSlot(), &room) !=
                    GameRoomObservation::Success ||
                room == nullptr) {
                return 0;
            }
            return engine_memory::AddressOf(room);
        }
        case FieldReceipt::RoomConfigData: {
            // 批次 290（2026-10-02）：`Room` 族里"字段住在房间配置对象里"的那些 API 的接收者
            // —— 「当前房间 → `RoomDescriptor*` → `RoomConfig::Room*`」这条**固定的两跳指针链**
            // 的末端。第一跳与 `FieldReceipt::Room` 逐字相同（同一份判据、同一个
            // `ReadCurrentGameRoom`），第二跳用布局表已确认的 `RoomDescriptor.Data`。
            //
            // 任何一环为空/不可读都返回 0 ⇒ 共享处理器按 `row->missing` **静默降级**
            // （本族给的是 1，与 PC 的 `mov eax,0x1` 逐字一致），**不报错** ——
            // 报错会把整条模组回调摘掉，比"这次答了个保守值"严重得多。
            void* room = nullptr;
            if (ReadCurrentGameRoom(LuaRuntime::GameOwnerSlot(), &room) !=
                    GameRoomObservation::Success ||
                room == nullptr) {
                return 0;
            }
            std::uintptr_t descriptor = 0;
            if (!engine_memory::LoadPointerAt(engine_memory::AddressOf(room),
                                              kRoomDescriptorPointerOffset, 0, &descriptor,
                                              &IsEngineMemoryReadable) ||
                descriptor == 0) {
                return 0;
            }
            std::uintptr_t data = 0;
            if (!engine_memory::LoadPointerAt(descriptor, layout::kRoomDescriptorDataOffset, 0, &data,
                                              &IsEngineMemoryReadable) ||
                data == 0) {
                return 0;
            }
            return data;
        }
        case FieldReceipt::RoomDescriptor: {
            // 批次 291（2026-10-02）：`Room` 族里"字段住在**描述符**上"的那些 API 的接收者
            // —— 「当前房间 → `Room + 0x8` → `RoomDescriptor`」这**一跳**链的末端。
            // 第一跳与 `FieldReceipt::Room` 逐字相同（同一份判据、同一个 `ReadCurrentGameRoom`），
            // 第二跳用布局表已确认的 `kRoomDescriptorPointerOffset`（`Room+0x8`，
            // 三条独立证据见 `runtime_constants.hpp` 该常量上方）。
            //
            // ★ 为什么不复用别的 receipt：
            //   * `Room` 的 `offset` 相对 `Room` 算 ⇒ 描述符的 `+0x50` 会落成 `Room+0x50`
            //     （那是另一个字段：`Room::update_mist` 等函数就在读 `Room+0x44`/`Room+0x50`
            //      一族的其它东西）⇒ **静默给错值**；
            //   * `RoomConfigData` 的末端是 `RoomConfig::Room`，比描述符还远一跳。
            //
            // 任一环为空/不可读都返回 0 ⇒ 共享处理器按 `row->missing` **静默降级**
            // （本族这两条给的是 `false`），**不报错** —— 报错会把整条模组回调摘掉。
            void* room = nullptr;
            if (ReadCurrentGameRoom(LuaRuntime::GameOwnerSlot(), &room) !=
                    GameRoomObservation::Success ||
                room == nullptr) {
                return 0;
            }
            std::uintptr_t descriptor = 0;
            if (!engine_memory::LoadPointerAt(engine_memory::AddressOf(room),
                                              kRoomDescriptorPointerOffset, 0, &descriptor,
                                              &IsEngineMemoryReadable) ||
                descriptor == 0) {
                return 0;
            }
            return descriptor;
        }
        case FieldReceipt::Level: {
            // `Level` 内嵌在 `Game` 起始处，解析链与 `Room`/描述符那条**逐字相同**：
            // `g_Game` 槽是"槽的地址"（指针变量）→ 解一次得 owner → 再解一次才是 `Game*`。
            // 少解一层会去读模块里的代码字节（真机探针上踩过同一个坑）。
            const std::uintptr_t moduleBase = EngineModuleBase();
            if (moduleBase == 0) {
                return 0;
            }
            // 两跳都走层（偏移算术 + 回绕检查 + 可读性判定 + 取值）。
            // `requiredAlignment = 0`：与原实现逐条一致 —— 它只查"回绕 + 该 8 字节可读"，
            // 没有对齐判据（槽是指针变量，按定义已对齐；这里不额外加原实现没有的条件）。
            std::uintptr_t owner = 0;
            if (!engine_memory::LoadPointerAt(moduleBase, kGameOwnerGlobalSlotOffset, 0, &owner,
                                              &IsEngineMemoryReadable) ||
                owner == 0) {
                return 0;
            }
            std::uintptr_t level = 0;
            if (!engine_memory::LoadPointerAt(owner, 0, 0, &level, &IsEngineMemoryReadable)) {
                return 0;
            }
            return level;
        }
        case FieldReceipt::Seeds: {
            // 批次 335（2026-10-03）：`Seeds:*` 引擎方法行的接收者 —— **不从 Lua 栈上取**。
            // `SeedHandle`（`Game:GetSeeds()` 的返回值）与 `Room`/`Music`/`ItemPool` 同形：
            // 空壳、不持引擎指针 ⇒ 接收者只能算出来。
            //
            // 解析链 = 「模块基址 → `g_Game` 全局槽 → `Game*` → `Game + kGameSeedsObjectOffset`」。
            // 前两跳**逐字复用** `FieldReceipt::Level` 那一段（同一个槽、同一份判据、同一份常量）；
            // 第三跳用布局常量 `kGameSeedsObjectOffset` —— `Seeds` 是 `Game` 的**内嵌子对象**
            // （`Seeds::Seeds @ 0x49CBD4` 的布局证据见 `runtime_constants.hpp` 的该常量段），
            // 所以是"取地址相加"，不是再解一次指针。
            //
            // 任一环为空/不可读都返回 0 ⇒ 共享处理器按 PC 语义**静默降级**（返回 void 就什么都不做），
            // **不报错** —— 报错会把整条模组回调摘掉，比"这一次没生效"严重得多。
            const std::uintptr_t moduleBase = EngineModuleBase();
            if (moduleBase == 0) {
                return 0;
            }
            std::uintptr_t owner = 0;
            if (!engine_memory::LoadPointerAt(moduleBase, kGameOwnerGlobalSlotOffset, 0, &owner,
                                              &IsEngineMemoryReadable) ||
                owner == 0) {
                return 0;
            }
            std::uintptr_t game = 0;
            if (!engine_memory::LoadPointerAt(owner, 0, 0, &game, &IsEngineMemoryReadable) ||
                game == 0) {
                return 0;
            }
            return game + kGameSeedsObjectOffset;
        }
        case FieldReceipt::PathFinder: {
            // 批次 344（2026-10-04）：`PathFinder:*` 引擎方法行（本批是 `HasPathToPos`）的接收者
            // —— **从 Lua 栈上取**（与 `EntityPlayer`/`GridEntity` 同形）：
            // `EntityNPC.Pathfinder` 属性交回的 `PathFinderHandle` 里**真持**那个内嵌子对象的
            // 地址（`Entity_NPC + 0x408`），所以读栈上那一个就够。
            //
            // ★★ 为什么要**严格**校验句柄类型（不能像 `Entity` 那一档只做 vtable 区间校验）：
            //   这一条是**调用**。`NPCAI_Pathfinder::HasPathToPos` 一进去就顺着 `this` 读一堆成员
            //   （反汇编里 `ldr w10,[x9,#0x310]` 之类）⇒ 拿一个别的对象当 `this` 交进去是**野读**。
            //   `PathFinder` 是 `Entity_NPC` 的**内嵌成员**（没有自己的 vptr），能做的判据只有
            //   "句柄类型对 + 底层地址非 0" ⇒ 用 `luaL_testudata` 严格判类型。
            //   ★ 不是 `PathFinder` 句柄 ⇒ 归零 ⇒ 共享处理器按 PC 语义**静默降级**
            //     （返回 `Bool` 就压 `false`）。**不报错** —— 报错会把整条模组回调摘掉。
            auto* handle =
                static_cast<PathFinderHandle*>(luaL_testudata(state, index, kPathFinderMetatable));
            if (handle == nullptr || handle->pathfinder == nullptr || !EntityLifetimeAlive(handle->lifetime) ||
                (handle->owner && !IsLiveEntityPointer(engine_memory::AddressOf(handle->owner)))) {
                return 0;
            }
            return engine_memory::AddressOf(handle->pathfinder);
        }
        case FieldReceipt::TemporaryEffects: {
            // 批次 388（2026-10-07）：`TemporaryEffects:*` 引擎方法数据行的接收者 ——
            // **从 Lua 栈上取**（与 `PathFinder` 同形）。句柄（`TemporaryEffectsHandle`）存的是
            // **拥有它的 `Entity_Player` 地址**；容器是玩家的**内嵌子对象**（`+0x18D8`）⇒
            // 先校验玩家 vptr（`IsEntityPlayer`）再取地址相加。换局/玩家销毁后旧句柄自然失效。
            //
            // ★★ 为什么**必须**新开一档、不复用 `EntityPlayer`：这一族的行是**调用**，
            //   `TemporaryEffects::HasEffect` 一进去就读 `[x0+0x21]` 与 `[x0+0x08]/[x0+0x10]`
            //   （向量的 begin/end），`AddEffect`/`RemoveEffect` **会改**那个容器 ⇒ 拿一个
            //   `Entity_Player*` 当 `this` 交进去 = 把玩家对象内部的那几个偏移当向量来读/写，
            //   是**野读写**（比"读到别人的值"严重得多）。⇒ 用 `luaL_testudata(…,
            //   kTemporaryEffectsMetatable)` 严格校验句柄类型（同 `PathFinder`/`EntityFamiliar`）。
            return ResolveTemporaryEffectsReceiver(state,index);
        }
        case FieldReceipt::Music: {
            // 批次 239（2026-09-30）：`MusicManager:*` 的接收者 —— **不从 Lua 栈上取**，
            // 而是"全局 Manager 槽 → `Manager + kManagerMusicOffset`"。
            // 与 `Isaac:GetMusicIdByName` 逐字同一条链、同一份常量（`ResolveManagerAddress()`
            // 就是那条链的前半段，它的注释写明"与 `ItemConfig` 同一个 `Manager`"）。
            //
            // ★ 为什么不读栈上那个 self：`MusicManager()` 在 Lua 里是**占位句柄**
            // （`CreateMusicHandle` 只放了一个保留字、不持引擎指针），栈上那个 userdata 里
            // 根本没有 `Music*`。所以接收者必须**算出来**，与 `Room`（解析"当前房间"）同一口径。
            //
            // 与 `ResolveMusicForCall`（`lua_runtime.cpp`）拿到的是**同一个对象**：那条链两跳
            // （当前回调的 Manager → 本帧 `Manager::Update` 的 self）的注释写明"两者是同一个单例"。
            // 走全局槽的好处是**不依赖"当前正在托管回调派发里"**这个前置条件。
            //
            // 读不到就返回 0 ⇒ 共享处理器按 PC 语义**静默降级**（返回 void 就什么都不做、
            // 返回整数就压 0），**不报错**：报错会把整条模组回调摘掉，比"这次没生效"严重得多。
            const std::uintptr_t manager = ResolveManagerAddress();
            if (manager == 0 || manager > UINTPTR_MAX - kManagerMusicOffset) {
                return 0;
            }
            const std::uintptr_t music = manager + kManagerMusicOffset;
            if (!IsEngineMemoryReadable(music, sizeof(std::uintptr_t))) {
                return 0;
            }
            return music;
        }
        case FieldReceipt::ItemPool: {
            // 2026-10-01 批次 254：`ItemPool:*` 引擎方法数据行的接收者 —— **不从 Lua 栈上取**。
            // `ItemPool` 句柄（`ItemPoolHandle`）与 `Room`/`Music` 同形：只有一个保留字节、
            // 不持引擎指针，所以接收者必须**算出来**。这里走 `game_observer.hpp` 的
            // `ReadCurrentGameItemPool`（"当前局对象的 ItemPool"那条链）—— 与既有的手写
            // `GameGetItemPool` / `ItemPoolGetCollectible` **同一条链、同一份判据**，
            // 不另写一份解析（两个真值源就会漂移）。
            //
            // 拿不到就返回 0 ⇒ 共享处理器按 PC 语义**静默降级**（返回 void 什么都不做、
            // 返回布尔压 false），**不报错**：报错会把整条模组回调摘掉。
            void* itemPool = nullptr;
            if (ReadCurrentGameItemPool(LuaRuntime::GameOwnerSlot(), &itemPool) !=
                    GameItemPoolObservation::Success ||
                itemPool == nullptr) {
                return 0;
            }
            return engine_memory::AddressOf(itemPool);
        }
    }
    return 0;
}

void PushMissingFieldValue(lua_State* state, FieldMissing missing) {
    switch (missing) {
        case FieldMissing::Nil:
            lua_pushnil(state);
            return;
        case FieldMissing::False:
            lua_pushboolean(state, 0);
            return;
        case FieldMissing::MinusOne:
            lua_pushinteger(state, -1);
            return;
        case FieldMissing::One:
            // 批次 290：PC 自己在这一格读不出来时答的是 1（`Room:GetRoomShape` 的
            // `0x444C42 mov eax,0x1`）—— 所以降级也要答 1，不能落到 `Zero`。
            lua_pushinteger(state, 1);
            return;
        case FieldMissing::Zero:
        default:
            PushZero(state);
            return;
    }
}

//: 批次 289（2026-10-02）：读不到时的降级。绝大多数 kind 直接按 `row->missing` 压
//: （0 / nil / false / −1），而 `Vector2Pair` **必须**压一个真正的 `Vector(0,0)`：
//:
//: 语料里这两条（`Room:GetTopLeftPos` / `GetBottomRightPos`，共 68 处）几乎第一件事就是取分量
//: （`r:GetTopLeftPos().Y + 10`、`Vector(room:GetTopLeftPos().X, i)`）—— 压 `nil` 会
//: `attempt to index a nil value`、压数字 `0` 会 `attempt to index a number value`，
//: 两种都会把整条模组回调摘掉，比"坐标是 (0,0)"严重得多。
//: 口径与批次 249/259 对 `Room` 位置类方法定的那条**逐字相同**：降级压零向量、**不压 nil**。
void PushMissingFieldValueForRow(lua_State* state, const FieldApiRow* row) {
    if (row->kind == FieldKind::Vector2Pair) {
        isaac::runtime::PushLuaVector(state, 0.0F, 0.0F);
        return;
    }
    if (row->kind == FieldKind::ColorModRead) {
        // 批次 343（2026-10-04）：`ColorModRead` 读不到时压一个**默认白** `Color`。
        // ★ 为什么不是 `nil`：`Entity:GetColor()` 的语料 4 处拿到返回值第一件事就是取分量
        //   （`copyColor` 的 `color.R`）或直接喂回 `SetColor` ⇒ 压 `nil` 会
        //   `attempt to index a nil value` / 参数闸报错，**把整条模组回调摘掉**
        //   —— 比"颜色是白的"严重得多（与 `Vector2Pair` 压 `Vector(0,0)` 同一族理由）。
        // ★ 默认白的口径与 `DefaultEngineColorMod()` 一致（tint 全 1、其余 0），
        //   也就是 PC 的 `Color.Default`。
        isaac::runtime::PushLuaColorFromEngineColorMod(
            state, isaac::runtime::DefaultEngineColorMod());
        return;
    }
    PushMissingFieldValue(state, row->missing);
}

//: `VectorCount` 的合理上限：正常容器（收藏品/饰品/卡片…）都是几十个元素的量级。
//: 超过它说明 begin/end 读到的不是一对真指针（内存不可信），按"读不到"降级而不是返回巨大数字。
constexpr std::uintptr_t kFieldVectorCountMaximum = 4096;

//: 批次 297：`BoolBitArrayOfArg` 的**元素个数护栏**（不是位号上限：位号上限 = 它 × 8 × 宽度）。
//: 两个真实用途都远小于它 —— `GameStateFlag` 有 53 个标志（宽度 1 ⇒ 需要 7 个字节）、
//: `LevelStateFlag` 有 24 个（宽度 8 ⇒ 需要 1 个字）⇒ 取 64 个元素（宽度 1 时 = 512 位、
//: 宽度 8 时 = 4096 位）既能容下未来新增的标志，又把"实参乱给"限制在离基址 ≤ 512 字节内。
constexpr std::uint64_t kFieldBitArrayMaximumElements = 64;

//: `Isaac` 族（含 `Entity`/`EntityPlayer`/`ItemConfig_Item`）的字段读取型 API。
//: **家族的绑定行必须住在自己的 TU 里**（契约门禁会逐条核对），所以 `Level` 的行表在
//: `remaining_api.cpp`（`kLevelFieldApis`）——共享处理器是同一个 `FieldApiHandler`。
//:
//: 每一行 = 一个 API，**0 字节代码**；手写同类方法实测 236–312 字节。
//: 只收"无参数、接收者+固定偏移、读不到按族约定降级"的形状；带参数或需要分支的（例如
//: `GetEffectiveMaxHearts` 要按 `PlayerType` 决定是否算骨心）继续手写，不硬塞。
constexpr FieldApiRow kFieldApis[] = {
    // `EntityPlayer:GetPlayerType()`：`+0x1738`。读不到给 nil（`== PlayerType.ISAAC` 在 nil
    // 上自然为假，假值会让 Mod 走进错误分支）；探针位 1 与原先手写实现保持一致。
    {0x0E010016, kEntityPlayerTypeOffset, 0, FieldKind::U32, FieldMissing::Nil,
     FieldReceipt::EntityPlayer, 1},
    // `EntityPlayer:GetSoulHearts()`：`+0x16C4`，半心为单位（PC 文档：1 单位 = 半颗心）。
    {0x0E010021, kEntityPlayerSoulHeartsOffset, 0, FieldKind::U32, FieldMissing::Zero,
     FieldReceipt::EntityPlayer, 0xFF},
    // `EntityPlayer:GetBrokenHearts()`：`+0x2470`。PC 文档明确它**不**翻倍。
    {0x0E010022, kEntityPlayerBrokenHeartsOffset, 0, FieldKind::U32, FieldMissing::Zero,
     FieldReceipt::EntityPlayer, 0xFF},
    // `EntityPlayer:GetMaxHearts()`：`+0x16B8`（红心**容器**，1 单位 = 半颗心容器 ——
    // PC 文档 `EntityPlayer.md` 的 `GetMaxHearts` 原文）。原先这里返回硬编码 0，
    // 属于"有实现但语义偏弱"，现在按已确认偏移真读。
    {0x0E01003B, kEntityPlayerRedHeartContainersOffset, 0, FieldKind::U32, FieldMissing::Zero,
     FieldReceipt::EntityPlayer, 0xFF},
    // `EntityPlayer:GetBabySkin()`：`+0x20E8`，**有符号**，非婴儿 = `-1`（读不到也给 -1：
    // 编一个非负值会让 Mod 走进"这是婴儿"的分支去查一套不存在的皮肤）。
    {0x0E010028, kEntityPlayerBabySkinOffset, 0, FieldKind::I32, FieldMissing::MinusOne,
     FieldReceipt::EntityPlayer, 0xFF},
    // --- 批次 7（2026-09-15）：EID 用到、而运行时里**完全没有**的两条 -----------------
    // `EntityPlayer:GetCollectibleCount()`：**按 id 的计数数组求和**（`+0x1AB8`/`+0x1AC0`
    // 是 begin/end 这一对指针，每格 4 字节 = "该收藏品有几件"）。
    //
    // ★ 这里原先按"容器格子数"实现，**真机验收当场证伪**（2026-09-16）：它返回 733，
    // 而 733 只是数组长度（Repentance 的收藏品 id 空间），玩家实际只有 1 件（D6，id 105）。
    // 口径依据：PC 侧另有一条 `EntityPlayer:GetCollectibleNum(id)`（按 id 数），
    // 本项目的它与这张数组的第 id 格同源 ⇒ `GetCollectibleCount()` 应当是**总件数**。
    {0x0E01004F, kEntityPlayerCollectibleBeginOffset, static_cast<std::uint32_t>(
         kEntityPlayerCollectibleEndOffset), FieldKind::SumU32Array, FieldMissing::Zero,
     FieldReceipt::EntityPlayer, 0xFF},
    // `ItemConfig_Item:IsTrinket()`：`Type == ITEM_TRINKET`（`kItemTypeTrinket = 2`）。
    // `offset2` 在这里是"要比较的常量"，不是第二个偏移 —— 见 `FieldKind::BoolEquals`。
    {0x0E010050, kItemConfigItemTypeOffset, kItemTypeTrinket, FieldKind::BoolEquals,
     FieldMissing::False, FieldReceipt::ItemConfigItem, 0xFF},
    // `EntityPlayer:HasGoldenBomb()`（批次 195，2026-09-29）：读 `Entity_Player + 0x16D9` 那**一个
    // 字节**。**取值锚点**是引擎自己的一对同名函数（`AddGoldenBomb @ 0x2FC3F0` 置 1 /
    // `RemoveGoldenBomb @ 0x2FC490` 清 0），且紧邻的 `0x16D8` 是"金钥匙"标志（写法逐字同形）
    // ⇒ 取值证据、不是"某处有个字节"。逐条指令见 `runtime_constants.hpp` 的
    // `kEntityPlayerGoldenBombFlagOffset`。
    // 读不到给 `false`（与 PC 的"没有"一致；旧实现是恒 false 的假桩，已销账）。
    {0x0E01004A, kEntityPlayerGoldenBombFlagOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::EntityPlayer, 0xFF},
    // `Entity:HasEntityFlags(int Flags)`（批次 207，2026-09-29）：MCM 用
    // `entity:HasEntityFlags(EntityFlag.FLAG_FRIENDLY)` 把友方从"危险"里排除
    // （`analysis/mod-corpus/isaac-mod-config-menu/scripts/modconfig.lua:207`）。
    //
    // 读的是 `Entity + 0x1B8` 那个 **64 位**实体标志字（既有两个消费者给过它：
    // `QueryRadius`/`FindByType` 用它判 bit46 `FLAG_NO_QUERY`、活表判据用它判 bit3，
    // 见 `runtime_constants.hpp` 的 `kEntityFlagsOffset`）。判据是"实参点到的位**全都**置着"
    // （PC 契约 `Entity.md:425/427` 的 "has **all** named EntityFlags set"），
    // 实现见 `FieldKind::U64FlagsAllSet` 那一支。
    // 读不到给 `false`（= "这些标志没有"，与 PC 的未置位一致）。
    {0x0E010061, kEntityFlagsOffset, 0, FieldKind::U64FlagsAllSet, FieldMissing::False,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 287（2026-10-02）：`EntityPlayer` 的"心数 / 金色钥匙"三条（都是只读字段）
    //
    // 三条在 Switch 镜像里**都没有同名函数**（按 mangled 长度前缀逐段解析，各 0 个实现）⇒ PC 上
    // 是内联/字段访问器，只能读字段。完整证据链（每条都是「PC 读点 + PC 写点 + Switch 写点」
    // 三方对应）写在 `runtime_constants.hpp` 的**批次 287 段**。
    //
    // `EntityPlayer:GetBoneHearts()` —— 契约 `EntityPlayer.md:866` 是 `int GetBoneHearts ( )`，
    // 正文 `:867` 明说「This is **not doubled** like the `EntityPlayer.GetMaxHearts` method is」
    // ⇒ 原样读 `+0x2450`、**不乘 2**（`GetEffectiveMaxHearts` 里那个 `lsl #1` 是**它**的事）。
    // 常量是批次 274 起的既有条目（`AddBoneHearts @ 0x27E380` 的强命中字段 + `GetEffectiveMaxHearts`
    // 的读点），本批只是补上消费方。读不到压 `0`（PC 上"没有骨心"就是 0）。
    {0x0E0100C3, kEntityPlayerBoneHeartsOffset, 0, FieldKind::U32, FieldMissing::Zero,
     FieldReceipt::EntityPlayer, 0xFF},
    // `EntityPlayer:GetEternalHearts()` —— 契约 `EntityPlayer.md:956` 是 `int GetEternalHearts ( )`。
    // 字段 `+0x16C0`：引擎自己的 `AddEternalHearts` 在它上面"取-加-夹-存"（两版同形），
    // 且 `StoreGameState`/`RestoreGameState` 与 `update_red_hearts` 都读写这一格。读不到压 `0`。
    {0x0E0100C4, kEntityPlayerEternalHeartsOffset, 0, FieldKind::U32, FieldMissing::Zero,
     FieldReceipt::EntityPlayer, 0xFF},
    // `EntityPlayer:HasGoldenKey()` —— 契约 `EntityPlayer.md:1372` 是 `boolean HasGoldenKey ( )`。
    // 读 `+0x16D8` 那**一个字节**，取值锚点是引擎自己的 `AddGoldenKey`/`RemoveGoldenKey` 一对
    // （置 1 / 清 0，两版写法逐字同形）⇒ 取值证据、不是"某处有个字节"。
    // 读不到压 `false`（与 PC 的"没有"一致）。与邻格 `+0x16D9` 的金炸弹标志同族。
    {0x0E0100C5, kEntityPlayerGoldenKeyFlagOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::EntityPlayer, 0xFF},
    // ---- 批次 288（2026-10-02）：`EntityPlayer` 的两个方向字段 ----
    // 契约 `EntityPlayer.md:994` 是 `Direction GetHeadDirection ( )`。PC 取值器 `0x427810` 与
    // `GetFireDirection` 的**相邻**（差 4 字节），Switch 侧由 `Weapon::SetHeadDirection` 直接写
    // `玩家+0x19FC`（同一函数还按这个值取头动画名）⇒ 取值锚点、不是"某处有个整数"。
    // `-1` 是 PC 的 `NO_DIRECTION`（引擎 `SetHeadDirection`/`SetAimDirection` 都允许 `-1`）
    // ⇒ 读不到压 `-1`，与 PC 的"没有方向"一致。
    {0x0E0100C6, kEntityPlayerHeadDirectionOffset, 0, FieldKind::I32, FieldMissing::MinusOne,
     FieldReceipt::EntityPlayer, 0xFF},
    // 契约 `EntityPlayer.md:968` 是 `Direction GetFireDirection ( )`。字段 `+0x1A00`：
    // 引擎 `SetAimDirection` 零向量时写入 `-1`、非零时写入 `get_movement_direction(向量)`
    // 的返回值；且该格**只有**瞄准/射击控制那一族写（头方向那格另有写点）⇒ 它是开火方向。
    {0x0E0100C7, kEntityPlayerFireDirectionOffset, 0, FieldKind::I32, FieldMissing::MinusOne,
     FieldReceipt::EntityPlayer, 0xFF},
    // ---- 批次 293（2026-10-03）：`Entity` 的**三个相邻状态字节**（合 32 处）----
    // 三条都是"读一个字节、非零即真"，接收者是 Lua 栈上的**实体句柄**（`FieldReceipt::Entity`）
    // ⇒ 零新机制、零新接收者。证据链（PC 三个相邻字节 + Switch 三格各自的具名消费者）见
    // `runtime_constants.hpp` 的批次 293 段；布局表 `tools/layout_tables/entity.json` 的
    // `Visible` / `Exists` / `IsDead` 三行（`--verify` 会重新反汇编逐条核对）。
    // ★ 降级档一律 `False`：三个量都按"读到 0 的口径"答（看不见 / 不在实体表里 / 没死），
    //   与 PC 上"读到 0"同值；句柄无效时也不会让模组对幽灵句柄动手。
    // 契约：`Entity.md` 的 320 / 466 / 491 行（`Exists` 那页还有一句散文，见对应行）。
    {0x0E0100C9, kEntityVisibleOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Entity, 0xFF},
    {0x0E0100CA, kEntityExistsOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Entity, 0xFF},
    {0x0E0100CB, kEntityIsDeadOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 315（2026-10-03）：`Entity:Die()`（**27 处 / 4 个模组** —— 剩余清单里最大的一条）----
    // 它是上面 `IsDead` 那**同一格的写侧**：往 `Entity + 0x1C3` 写**常量 1**（`FieldKind::BoolWriteConst`，
    // 与批次 305 的 `Music:Enable/Disable` 同形；不收实参、返回 0 个值）。
    //
    // ★★★ **本批推翻了交接 §4 的一条"别碰"**：那一节写「`Entity:Die` 已查明 dynsym 里 **0 个实现**
    //   ⇒ 别在这两条上花时间」。**"0 实现"只说明 Switch 侧没有同名函数（内联了），字段本身一定在** ——
    //   本批核 PC 侧两条绑定，逐字对上：
    //     `Entity:IsDead() @ 0x412350` = `movb 0x16b(%ecx), %al ; ret`   （读 PC `+0x16B`）
    //     `Entity:Die()    @ 0x436B60` = `movb $0x1, 0x16b(%ecx) ; ret`   （**写同一格** ⇒ 写 1）
    //   ⇒ PC 上 `Die` 与 `IsDead` **读写同一格**、各只有两条指令 ⇒ 这是一个**纯字段写**，
    //     不需要任何引擎函数、不需要新机制。
    //   ★ 另一条交叉印证：PC 的 `IsVisible @ 0x412360` 读 `+0x169`，与 `+0x16B` **相隔 2**；
    //     Switch 的 `kEntityVisibleOffset = 0x1C1` 与 `kEntityIsDeadOffset = 0x1C3` **同样相隔 2**
    //     （中间那格 `+0x16A` / `+0x1C2` 都是 `Exists`）⇒ 相对布局两边一致。
    //   ★ Switch 侧那一格早有**决定性证据**（批次 293 段）：`Entity::Kill() @ 0x05C8E8` 的函数体
    //     就是"读 `+0x1C3` → 已置着就返回（**幂等**）→ `mov w8,#1` → `strb`"，
    //     ⇒ "置 1 = 标记已死"由函数体与契约散文两头对上。
    //   ★★ 口径：我们**只写这一格**（= PC `Die` 逐字照做）。Switch 的 `Entity::Kill()` 额外立刻
    //     调虚表槽并可能 `BloodExplode`，**我们不复刻那一步**（PC 的 `Die` 也没做）——
    //     血/爆炸由引擎看到这一格后自行处理，与 PC 同。
    // 契约：`tools/pc_contract_docs/Entity.md:314`（`#### void Die ( )`）。
    {0x0E0100DA, kEntityIsDeadOffset, 1, FieldKind::BoolWriteConst, FieldMissing::False,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 296（2026-10-03）：`Entity_NPC` 的两个颜色索引（合 2 处 / 3 个模组）----
    // 两条都是"读一个 i32、按整数压回"，接收者是 Lua 栈上的实体句柄（`FieldReceipt::Entity`
    // —— `CheckEntityHandle` 在批次 285 就把 `kEntityNPCMetatable` 认进来了）⇒ 零新机制。
    // 证据链（具名写入方 `Init`/`MakeChampion`/`Morph`/`SetBossColorIdx` + 具名读者 +
    // 语义锚点）写在 `runtime_constants.hpp` 的批次 296 段；布局表
    // `tools/layout_tables/entity_npc.json`（本批新建，`struct: Entity_NPC`）的两行都是
    // `confirmed`（`--verify` 2 行 / 11 条证据全过）。
    // ★ 降级档一律 `MinusOne`：引擎自己的 `Entity_NPC::Init` 就把"没有配色"写成 `-1`
    //   （`mov w25,#-0x1` 分别落 `+0xD10` 与 `+0xD24`）⇒ 读不到时答 -1 与"读到构造默认值"同值；
    //   而语料正是按 `>= 0` 判"有没有色"（`Enhanced-Boss-Bars/main.lua:274/278`）⇒ 答 -1 只会让它
    //   走"没有色"的分支，不会让整条回调被摘。
    // 契约：`EntityNPC.md` 的 69（`GetBossColorIdx`）/ 77（`GetChampionColorIdx`）行。
    {0x0E0100CD, kEntityNpcChampionColorIdxOffset, 0, FieldKind::I32, FieldMissing::MinusOne,
     FieldReceipt::Entity, 0xFF},
    {0x0E0100CE, kEntityNpcBossColorIdxOffset, 0, FieldKind::I32, FieldMissing::MinusOne,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 314（2026-10-03）：`EntityNPC:IsChampion()`（1 处 / 1 个模组）----
    // 只读字段、走 `field_row`：`Entity_NPC + 0xD0F` 那**一个字节**（`FieldKind::Bool`，非 0 即真）。
    // 与上面两条色号是**同一批三格**（296 当时已把这一格的三个具名写入方锚定：`Init` 清 0、
    // `MakeChampion` / `Morph` 置 1，且**永远与冠军色号同批写**）。
    // ★★ 更正 296 的负结果：那一批说"PC 绑定是两个条件、少一半证据"—— 本批核名字表，
    //   `push 0x68F550` 全镜像 0 次引用（那不是这条 API 的绑定），**真绑定是 `0x68F580` =
    //   `movb 0xbb3(%ecx), %al; ret`（一条指令）**。更正与交叉印证写在 `runtime_constants.hpp`
    //   的批次 314 段。
    // 契约：`tools/pc_contract_docs/EntityNPC.md:93`。
    {0x0E0100D9, kEntityNpcChampionFlagOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 316（2026-10-03）：`Entity:GetDropRNG()`（3 处 / 2 个模组）----
    // 返回**被调用实体内嵌的那个 `RNG`**（契约 `tools/pc_contract_docs/Entity.md:377`；
    // `RNG.md:18` 也把它列进"RNG 从哪里来"的清单）。PC 的绑定本体（`0x412390`）就是
    // `lea eax,[ecx+0x334]; ret` —— **原样返回成员地址**，既不查表、也不调用引擎函数。
    //
    // ★★★ 偏移 = `Entity + 0x3D8`（**与既有 `Entity.DropSeed` 同一格**，不是新偏移）：
    //   实体基类**只有这一个 RNG 成员**，构造函数 `Entity::Entity @ 0x58978` 就在这一格上
    //   `add x0,x19,#0x3d8; bl RNG::RNG()`；出生 `Entity::Init @ 0x597E8` 又用同一格
    //   `add x21,x0,#0x3d8; bl RNG::SetSeed(seed, 30)`（`0x597FC mov w2,#0x1e`）。
    //   RNG 的种子就是对象头 4 字节 ⇒ "DropSeed 那一格"与"RNG 的起点"**本来就是同一地址**。
    // ★★ **两平台互相印证**：PC 的 `Entity.DropSeed @ 0x59FD60` = `mov eax,[ecx+0x334]`，
    //   而同页的 `Entity:GetDropRNG @ 0x412390` = `lea eax,[ecx+0x334]` —— 两条**指着同一格**；
    //   紧随的 setter（`0x59FD70`）又从 `0x334/0x338` 整片写回 ⇒ PC 上那 16 字节就是那个 RNG。
    //   Switch 的 `DropSeed`（`kEntityDropSeedOffset = 0x3D8`）与 RNG 起点**同样同址**
    //   （布局表 `tools/layout_tables/entity.json` 的 `DropSeed` 行本批升到 `confirmed`，
    //   `--verify` 5 条证据全过 ⇒ 命名不再是"推断"）。**数值仍不许平移**（两边偏移不同）。
    // ★ 形状 = 本批新开的 `FieldKind::RngSnapshot`（读整段 16 字节、压 `kRngMetatable` 句柄）；
    //   与手写的 `GridEntity:GetRNG` 及四条 `EntityPlayer:Get*RNG` 同为"**快照**而非活引用"
    //   （已登记的 `design` 偏离，见 `api_deviation.cpp`；读语义逐值相同）。
    // ★ 降级档 `Nil`：读不到时 PC 上也没有对象可给 ⇒ `GetDropRNG() == nil`；语料三处
    //   （`RepentancePlus/main.lua:1855`、`Trinity/main.lua:918/925`）都紧接着 `:RandomInt(...)`，
    //   压 nil 与 PC 上"拿不到"同值，**且不抛错**（不会把模组整条回调摘掉）。
    {0x0E0100DB, kEntityDropSeedOffset, 0, FieldKind::RngSnapshot, FieldMissing::Nil,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 301（2026-10-03）：`EntityPlayer:AddCacheFlags(CacheFlag)`（4 个模组 / 34 处）----
    // **本机制里第一条"读改写：把实参整段 OR 进一个 `u32` 字段"的行**（`FieldKind::U32OrWithArg`，
    // 返回 0 个值）。语义与 PC 的绑定本体逐字对应：`0x427800  or dword ptr [ecx+0x14b8], eax`
    // ⇒ `_cacheFlags |= 参数`（契约 `tools/pc_contract_docs/EntityPlayer.md:108/109`）。
    //
    // 偏移 `Entity_Player + 0x1958` 的完整取证（PC `_cacheFlags @ 0x14B8` 的对应关系、
    // `AddCollectible` 把道具的 `CacheFlags` 并进来、`EvaluateItems` 的逐位派发、
    // `DonateLuck` 置 `0x400`=CACHE_LUCK 的取值锚点）写在 `runtime_constants.hpp` 的
    // 批次 301 段；布局表 `tools/layout_tables/entity_player.json` 的 `CacheFlags` 行是
    // `confirmed`（`--verify` 3 条证据全过）。
    //
    // ★ `offset2` 在本 kind 里不用（写 0 —— 掩码来自实参，不是行里的常量）。
    // ★ 降级档写 `Zero` 只影响"有返回值的 kind"；本 kind 返回 0 个值，读不到/拿不到玩家时
    //   **什么都不写、也不抛错**（见 `RowReturnsNoValues`）。
    // ★ `probeBit` 用 `0xFF`（字段行没有入口指纹，与批次 287 起的惯例一致）。
    {0x0E0100D2, kEntityPlayerCacheFlagsOffset, 0, FieldKind::U32OrWithArg, FieldMissing::Zero,
     FieldReceipt::EntityPlayer, 0xFF},
    // ---- 批次 312（2026-10-03）：`EntityPlayer:IsCoopGhost()`（1 处 / 1 个模组）----
    // 契约 `tools/pc_contract_docs/EntityPlayer.md:1499`：`boolean IsCoopGhost ( )`，
    // 正文「if a player dies, they will return as a tiny ghost … returns true if the player
    // is a co-op ghost.」⇒ **读一个字节、按布尔压回**（`FieldKind::Bool` 正是"读一个字节、
    // 非 0 即真"，与 PC 绑定 `mov al, byte ptr [ecx+0x1f88]` 逐字对应）。
    //
    // 偏移 `Entity_Player + 0x284C` 的完整取证（PC 绑定 `0x6C4AF0` 读 `+0x1F88`；
    // Switch 侧三个具名写入方 `morph_to_coop_ghost`/`init_coop_ghost` 置 1、
    // `revive_coop_ghost` 清 0，加一个具名消费者 `PlayerManager::GetNumCoopPlayersAlive`
    // 用 `eor #1` 反向计数）写在 `runtime_constants.hpp` 的批次 312 段。
    //
    // ★ 端到端判据链（"行为与 PC 一致"）：`ReviveCoopPlayers` / `GetNumCoopPlayersAlive`
    //   与三个 morph/init/revive 入口共用同一格 ⇒ 这是"引擎自己怎么定义合作幽灵"那一格。
    // ★ 读不到压 `false`（与 PC 的"没有"一致；语料 `and not player:IsCoopGhost()` 在
    //   false 上自然放行，压 `nil` 会让整条判断抛错、摘掉模组回调）。
    {0x0E0100D8, kEntityPlayerCoopGhostFlagOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::EntityPlayer, 0xFF},
    // ---- 批次 333（2026-10-03）：`Entity:MultiplyFriction(float Value)`（1 处 / 1 个模组）----
    // 契约 `tools/pc_contract_docs/Entity.md:510`（只有签名、没有散文）。
    // PC 绑定本体（`0x5951D0`）= `movss xmm0,[ebp+8]` → `mulss xmm0,[ecx+0x2c4]` →
    // `movss [ecx+0x2c4],xmm0; ret 4` ⇒ **读改写一个 `float`**（判法四档第 ① 档：字段写）。
    // ★ 走**新开的** `FieldKind::FloatMultiplyArg`（本批第一条"浮点读改写"的字段行；
    //   既有 kind 都是整数/位/字节，覆盖不了"乘"）。它是**写侧** ⇒ 已列进 `RowReturnsNoValues`。
    // ★ 接收者是**基类 `Entity`**（API 挂在 `Entity` 页上，语料 `p:MultiplyFriction(1.2)` 传的是玩家
    //   —— 玩家也是 `Entity`）⇒ 与 `Entity:Kill` 那批同一档。
    // ★★ 偏移 `Entity + 0x340` 的定案（**为什么不是旁边的 `+0x33C`**）写在
    //   `runtime_constants.hpp` 的批次 333 段：那一格是**本帧的工作摩擦**（被喂给
    //   `TimeScaledFriction` 再乘进速度），而 `+0x33C` 是原值；★ 语料**每帧**调用
    //   （`events.lua:850` 的 `onUpdate`）⇒ 乘原值会指数级累积 ⇒ 取本帧值。
    // ★ 降级档写 `Zero` 只为满足行结构（本 kind **不返回值**，`missing` 用不上）。
    {0x0E0100E5, kEntityFrictionOffset, 0, FieldKind::FloatMultiplyArg, FieldMissing::Zero,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 336（2026-10-03 深夜）：`Entity:CollidesWithGrid()`（1 处 / 1 个模组）----
    // PC 契约 `tools/pc_contract_docs/Entity.md` 的 `CollidesWithGrid` 行：`#### boolean CollidesWithGrid ( )`。
    // PC 绑定本体（`0x641420`）= **`mov al,[ecx+0x188]; ret`** ⇒ 纯读一个字节（判法四档 ①档）
    // ⇒ 字段数据行，接收者是既有的 `FieldReceipt::Entity`（从栈上取实体句柄）。
    // ★ Switch 侧那一格 = **`Entity + 0x1EC`**（布局表 `entity.json` 的 `CollidesWithGrid` 行，
    //   `confirmed`）：`Entity::Init` 清零、`Entity::CollideWithGrid`/`PlayerCollideWithGrid`
    //   "整趟碰撞前清 0 + 各分支置 1"、`Entity::Update` 与一批 `Entity_*::Update` 读它
    //   ⇒ 三条独立证据写在 `runtime_constants.hpp` 的批次 336 段。
    // ★ 降级档 `False`（布尔类）；读不到实体时与 PC 的"没有碰撞"一致。
    {0x0E0100E9, kEntityCollidesWithGridOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 341（2026-10-04）：`Entity:IsInvincible()`（2 处 / 2 个模组）----
    // PC 契约 `tools/pc_contract_docs/Entity.md:486`：`#### boolean IsInvincible ( )`（只有签名）。
    // PC 绑定本体（`0x59FD50`）= **`mov al,[ecx+0x308]; ret`** ⇒ 纯读一个字节（判法四档 ①档）
    // ⇒ 字段数据行，接收者是既有的 `FieldReceipt::Entity`（从栈上取实体句柄）。
    // ★ Switch 侧那一格 = **`Entity + 0x384`**（布局表 `entity.json` 的 `IsInvincible` 行，
    //   `confirmed`）：具名写入方 `Entity_NPC_VisageMask::SetNoDamage(bool)` 直接 `strb`、
    //   `Entity::Init` 出生清零、`Entity::TakeDamage` / `Entity::IsVulnerableEnemy` 两条受击闸门
    //   ⇒ 三条独立证据 + 与 PC `+0x308` 的偏移对位（增量 `+0x7C`）写在 `runtime_constants.hpp`
    //   的批次 341 段。
    // ★ 降级档 `False`（布尔类）；读不到实体时与 PC 的"不无敌"一致。
    {0x0E0100ED, kEntityIsInvincibleOffset, 0, FieldKind::Bool, FieldMissing::False,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 341（2026-10-04）：`EntityLaser:SetMaxDistance(float Distance)`（1 处 / 1 个模组）----
    // PC 契约 `tools/pc_contract_docs/EntityLaser.md:126`：`#### void SetMaxDistance ( float Distance )`，
    // 正文 "Used to trim brimstone for Azazel (0 - off)"。
    // PC 绑定本体（`0x4275B0`）= `movss xmm0,[ebp+8]; movss [ecx+0x420],xmm0; ret 4`
    // ⇒ **把实参直接写进一个 float 字段**（判法四档 ①档的写侧）。
    // ★ 走**新开的** `FieldKind::FloatFromArg`（批次 341；既有写侧 kind 覆盖不了"浮点赋值"：
    //   `FloatMultiplyArg` 是 `*=`、`U32FromArg` 写的是整数的 32 位 ≠ float 位型）。
    // ★ Switch 侧那一格 = **`Entity_Laser + 0x4F8`**（布局表 `tools/layout_tables/entity_laser.json`
    //   的 `MaxDistance` 行，`confirmed`）：两条具名消费者（`update_laser` / `init_laser` 的
    //   "裁剪射程"）+ 一条具名写入方（`Weapon_Laser::shoot` 把"两控制点距离"写进来）。
    // ★ 接收者 = `FieldReceipt::Entity`：`Entity:ToLaser()` 交回的是**真持引擎指针**的
    //   `EntityHandle`（只是元表不同）；`CheckEntityHandle` 在批次 282 就把 `kEntityLaserMetatable`
    //   认进来了，`ValidatedEntity` 的 vtable 区间也把 `Entity_Laser` 包在内 ⇒ 这一档足够，
    //   不需要为"读一个字段"单开一种 receipt（★ 与 `EntityFamiliar` 那档不同：那条是**调用**）。
    // ★ 降级档写 `Zero` 只为满足行结构（本 kind **不返回值**，`missing` 用不上）。
    {0x0E0100EE, kEntityLaserMaxDistanceOffset, 0, FieldKind::FloatFromArg, FieldMissing::Zero,
     FieldReceipt::Entity, 0xFF},
    // ---- 批次 342（2026-10-04）：`EntityPlayer:StopExtraAnimation()`（1 处 / 1 个模组）----
    // PC 契约 `tools/pc_contract_docs/EntityPlayer.md:1760`：`#### void StopExtraAnimation ( )`。
    // PC 绑定本体（`0x57B1D0`）= 把两个相隔 2 的字节都清 0（PC 那两格是 `Entity_Player + 0x12E8`
    // / `+0x12EA`，中间的 `0x12E9` **明确跳过**）⇒ **写两格常量 0**。
    // ★ 走**新开的** `FieldKind::TwoByteConstZero`（批次 342；`BoolWriteConst` 的 `offset2`
    //   已被"要写的常量"占掉 ⇒ 没有位置放第二格的偏移；且"一行 = 一个 API" ⇒ 不能挂两行）。
    // ★ Switch 侧那两格 = `Entity_Player + 0x1710`（"正在播放"）/ `+0x1712`（"已结束"）
    //   （布局表 `tools/layout_tables/entity_player.json` 的两行，`confirmed`）：
    //   消费者 `IsExtraAnimationFinished @ 0x2B78C4`、写入者 `PlayExtraAnimation @ 0x2B0914`
    //   ⇒ 证据写在 `runtime_constants.hpp` 的批次 342 段。
    // ★★ 中间那格 `+0x1711` **不许碰**（PC 跳过它）—— 用例里有专门的反回归断言。
    // ★ 降级档写 `False` 只为满足行结构（本 kind **不返回值**，`missing` 用不上）。
    {0x0E0100F2, kEntityPlayerExtraAnimationPlayingOffset,
     static_cast<std::uint32_t>(kEntityPlayerExtraAnimationFinishedOffset),
     FieldKind::TwoByteConstZero, FieldMissing::False, FieldReceipt::EntityPlayer, 0xFF},
    // ---- 批次 343（2026-10-04）：`Entity:GetColor()`（4 处 / 3 个模组）----
    // PC 契约 `tools/pc_contract_docs/Entity.md:338`：`#### const [Color](Color.md) GetColor ( )`
    // —— **按值返回**（所以胶水层给 Lua 的是一个值拷贝）。
    // PC 绑定本体（`0x4F3DE0`）= **`lea eax,[ecx+0xE4]; ret`** ⇒ 纯"读内嵌对象地址"（判法四档 ①档）
    // ⇒ 字段数据行；接收者是既有的 `FieldReceipt::Entity`（`player:GetColor()` 经 `__index`
    // 回落到 `Entity` 页，与基类那一族方法同一条路）。
    // ★ Switch 侧那一格 = **`Entity + kEntityGetColorOffset`（`0x138`）** 的 44 字节 `ColorMod`
    //   （"当前/生效色"）：靠 **PC/Switch 的 `Entity::SetColor` 逐字同构**定案 —— 见
    //   `runtime_constants.hpp` 的批次 343 段（★★ 极易与 `+0x220` 那个"默认色"取错，
    //   用例把三格摆成互不相同的值来钉）。
    // ★ 走**新开的** `FieldKind::ColorModRead`（批次 343）：既有读侧 kind 没有一种能压出
    //   `Color` 句柄（`Vector2Pair` 压 `Vector`、`RngSnapshot` 压 `RNG` 且带偏离）。
    // ★ 降级档写 `Zero` 只为满足行结构：读不到时走 `PushMissingFieldValueForRow` 的
    //   **默认白**那一支（不报错、不压 nil）。
    {0x0E0100F3, kEntityGetColorOffset, 0, FieldKind::ColorModRead, FieldMissing::Zero,
     FieldReceipt::Entity, 0xFF},
};

//: 批次 293：`Entity` 那三个状态字节的偏移在**两处**各有一个具名常量 —— 本表用的住在
//: `runtime_constants.hpp`（字段行的门禁只认那里），布局表生成的 `layout::kEntity…Offset`
//: 服务别处。同一个值写两遍迟早漂移 ⇒ 编译期钉死（与批次 290/291/292 同一做法）。
static_assert(kEntityVisibleOffset == layout::kEntityVisibleOffset,
              "Visible 字节的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kEntityExistsOffset == layout::kEntityExistsOffset,
              "Exists 字节的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kEntityIsDeadOffset == layout::kEntityIsDeadOffset,
              "IsDead 字节的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 301（2026-10-03）：`CacheFlags`（`Entity_Player._cacheFlags`）同款 —— 字段行的门禁只认
//: `runtime_constants.hpp` 的常量，布局表生成物服务别处，两边必须一致（值写两遍 ⇒ 编译期钉死）。
static_assert(kEntityPlayerCacheFlagsOffset == layout::kEntity_PlayerCacheFlagsOffset,
              "CacheFlags 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 333（2026-10-03）：`Friction`（`Entity + 0x340`，本帧的工作摩擦）同款 —— 字段行用
//: `runtime_constants.hpp` 的常量，布局表生成物服务别处；值写两遍 ⇒ 编译期钉死不许漂移。
static_assert(kEntityFrictionOffset == layout::kEntityFrictionOffset,
              "Friction 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 336（2026-10-03）：`CollidesWithGrid`（`Entity + 0x1EC`）同款 —— 字段行用
//: `runtime_constants.hpp` 的常量，布局表生成物服务别处；值写两遍 ⇒ 编译期钉死不许漂移。
static_assert(kEntityCollidesWithGridOffset == layout::kEntityCollidesWithGridOffset,
              "CollidesWithGrid 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 341（2026-10-04）：`IsInvincible`（`Entity + 0x384`）同款 —— 字段行用
//: `runtime_constants.hpp` 的常量，布局表生成物服务别处；值写两遍 ⇒ 编译期钉死不许漂移。
static_assert(kEntityIsInvincibleOffset == layout::kEntityIsInvincibleOffset,
              "IsInvincible 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
//: 批次 342（2026-10-04）：`StopExtraAnimation` 那两格（`Entity_Player + 0x1710` / `+0x1712`）同款
//: —— 字段行用 `runtime_constants.hpp` 的常量，布局表生成物服务别处；值写两遍 ⇒ 编译期钉死不许漂移。
static_assert(kEntityPlayerExtraAnimationPlayingOffset ==
                  layout::kEntity_PlayerExtraAnimationPlayingOffset,
              "ExtraAnimationPlaying 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");
static_assert(kEntityPlayerExtraAnimationFinishedOffset ==
                  layout::kEntity_PlayerExtraAnimationFinishedOffset,
              "ExtraAnimationFinished 的偏移在 runtime_constants.hpp 与布局表生成物之间不一致");

} // namespace

const FieldApiRow* FieldApiRows(std::size_t* count) noexcept {
    if (count != nullptr) {
        *count = sizeof(kFieldApis) / sizeof(kFieldApis[0]);
    }
    return kFieldApis;
}

namespace {

//: 批次 055：**签名描述符表** —— `EngineCallShape` 的索引就是这张表的下标。
//:
//: 加一种签名组合 = 在这里加一行 16 字节数据（**0 字节代码**）：共享处理器按描述符里的
//: 参数种类把值装进两个数组，交给通用跳板 `EngineCallTrampoline` 按 AAPCS64 调进去。
//: 表的前四项与批次 051 的四个枚举值一一对应（`Void0`/`Void1`/`Void2`/`Int0`），
//: 所以老的行不用改 —— **顺序不能动**（枚举值就是下标）。
//: `Ref2U32Pair`（批次 184）用：把"**我们自己**内存里的一个地址"变成可以放进引擎调用
//: 整数参数数组的位模式。
//
// 为什么需要它：那个形状要传的是"我们自己栈上两个出参槽的地址"（引擎按 `uint&` 收），
// 而 `EngineCallTrampoline` 的整数参数数组是 `std::uint64_t`（指针与整数混在一个数组里）。
//
// ★ **为什么用 `memcpy` 而不是 `reinterpret_cast`**：本仓库的门禁
//   `runtime/tests/test_no_new_raw_engine_access.py` 按 `reinterpret_cast` 的**字面出现次数**
//   给"裸碰引擎"记账 —— 它挡的是"业务代码直接摆弄**引擎**内存"。而这里取的是**我们自己**的
//   栈变量地址，跟引擎内存无关。用 `memcpy` 表达"位模式转换"：① 符合标准（union 的
//   type punning 在严格 C++ 下是 UB，`memcpy` 不是）；② 不会让那个计数虚涨
//   （那条门禁的存量**只许减不许增**：改台账放宽它，比换个准确写法糟得多）。
inline std::uint64_t AddressBitsForEngineArgument(const void* address) noexcept {
    static_assert(sizeof(std::uint64_t) == sizeof(address), "指针必须是 64 位");
    std::uint64_t bits = 0;
    std::memcpy(&bits, &address, sizeof(bits));
    return bits;
}

constexpr EngineCallShapeRow kEngineCallShapes[] = {
    // 0 Void0：`void(this)`
    {0, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 1 Void1：`void(this, i32)`
    {1, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 2 Void2：`void(this, i32, i32)`
    {2, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 3 Int0：`i32(this)`
    {0, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Int, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 4 VoidFloat1：`void(this, float)`（浮点参数走 `d0`，与整数各自独立计数）
    {1, {EngineArgKind::Float, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 5 VoidIntIntIntHandleInt：`void(this, i32, i32, i32, EntityPlayer*, i32)`
    //   `Game:StartRoomTransition(room, direction, animation, player, dimension)`：
    //   第 4 个参数是**玩家句柄**（PC 默认 nil ⇒ 空指针 ⇒ 引擎用默认值），所以这一格是 `Handle`。
    {5, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Handle,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::EntityPlayer, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 6 Bool0：`bool(this)`（无参、返回布尔）——`Entity:IsFlying()`
    {0, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 7 VoidNullId1：ABI 与 Void1 相同，但**第 1 个参数必须先验成"有效的 null 服装编号"**
    //   （批次 141，2026-09-26）。`EntityPlayer:AddNullCostume(int)` / `TryRemoveNullCostume(int)`
    //   收的就是它：编号无效（`-1` / 越界 / 空槽）时引擎 `GetNullItem(id)` 返回空 ⇒
    //   `AddCostume(nullptr)` 解引用空指针（真机 `Data Abort`、`Address = 0`）。
    {1, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::ValidNullItemId, 0, {0, 0, 0}},
    // 8 Int1：`i32(this, i32)` —— 批次 177：`EntityPlayer:GetPill(int)` / `GetCard(int)`
    //   （引擎 `Entity_Player::GetPill` @ `0x2E8D80` / `GetCard` @ `0x2E8D58`）。
    {1, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Int, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 9 Bool1：`bool(this, i32)` —— 批次 177：`EntityPlayer:HasPlayerForm(Form)`
    //   （引擎 `Entity_Player::HasPlayerForm(ePlayerForm)` @ `0x298510`）。
    {1, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 10 Ref2U32Pair：`void(this, u32& 入出参, u32& 入出参)` —— 批次 184（2026-09-28）：
    //   `EntityPlayer:GetGlyphOfBalanceDrop(variant, subtype)`（引擎 @ `0x2FE574`）。
    //   两个参数**既是入参又是出参**。Lua 侧仍按普通整数收这两个参数（所以 `argumentCount`
    //   与 `argumentKinds` 跟 `Int` 形状逐字一样），差别**全在返回种类**：
    //   共享处理器在调用**前**把 `integers[1]/[2]` 换成"我们自己栈上那两个 u32 槽的地址"
    //   （槽里放 Lua 给的值当入参），调用**后**把槽读回来压成一张两元表。
    //   引擎侧签名由反汇编证实（只往 `x1`/`x2` 指向的槽写、`ret` 前不写 `w0`）；
    //   Lua 侧形状的唯一口径是消费者 EID（`features/eid_repentogon.lua:265`）。
    {2, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::U32PairTable, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 11 BoolOpt1：`bool(this, bool 可选)` —— 批次 207（2026-09-29）：
    //   `Entity:IsActiveEnemy(bool includeDead)`（引擎 @ `0x5F028`，见 `runtime_constants.hpp`）。
    //   ★ 两处与 `Bool1` 不同、也都是这条 API 必需的：
    //     ① 参数种类是 `Bool`（`Bool1` 是 `Int`）：模组传的是 Lua **布尔**
    //        （`RepentancePlus/main.lua:697` 传 `false`），而 `IsIntegerArgument` 走
    //        `lua_isnumber` ⇒ 布尔会被判成"不是整数"、整条回调被摘掉。
    //     ② 最后一格（`optionalArgumentCount`）= 1：MCM 一个参数都不传
    //        （`modconfig.lua:206`：`entity:IsActiveEnemy()`）⇒ 省略时 `x1` 保持 0，
    //        等于 `includeDead == false`，正是 PC 的缺省值。
    {1, {EngineArgKind::Bool, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 1, {0, 0, 0}},
    // ---- 批次 239（2026-09-30）：语料模组适配第二波 —— 9 种新形状（**纯数据、0 代码**）。
    // 形状名与逐条理由写在 `engine_method_api.hpp` 的 `EngineCallShape` 枚举处（那里是它们的定义点）。
    // 12 VoidIntIntBool：`void(this, i32, i32, bool)` —— `Room:RemoveGridEntity`
    {3, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Bool, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 13 BoolIntIntInt：`bool(this, i32, i32, i32)`，尾部 1 个可省 —— `Room:SetGridPath`
    {3, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 1, {0, 0, 0}},
    // 14 BoolIntBoolBool：`bool(this, i32, bool, bool)`，尾部 2 个可省 —— `Room:DestroyGrid`
    {3, {EngineArgKind::Int, EngineArgKind::Bool, EngineArgKind::Bool, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 2, {0, 0, 0}},
    // 15 Float0：`float(this)` —— `Level:GetPlanetariumChance`（返回走 `d0`）
    {0, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Float, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 16 IntBoolInt：`i32(this, bool, i32)` —— `Level:GetRandomRoomIndex`
    {2, {EngineArgKind::Bool, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Int, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 17 VoidIntOpt1：`void(this, [i32])`，尾部 1 个可省 —— `MusicManager:DisableLayer`
    {1, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 1, {0, 0, 0}},
    // 18 BoolIntOpt1：`bool(this, [i32])`，尾部 1 个可省 —— `MusicManager:IsLayerEnabled`
    {1, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 1, {0, 0, 0}},
    // 19 VoidIntBoolOpt2：`void(this, [i32, bool])`，尾部 2 个可省 —— `MusicManager:EnableLayer`
    {2, {EngineArgKind::Int, EngineArgKind::Bool, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 2, {0, 0, 0}},
    // 20 VoidFloatFloatOpt1：`void(this, float, [float])`，尾部 1 个可省 —— `MusicManager:VolumeSlide`
    {2, {EngineArgKind::Float, EngineArgKind::Float, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 1, {0, 0, 0}},
    // ---- 批次 252（2026-10-01）：3 种新形状（**纯数据、0 代码**）。
    // 形状名与逐条理由写在 `engine_method_api.hpp` 的 `EngineCallShape` 枚举处（定义点在那里）。
    // 21 VoidIntFloatOpt1：`void(this, i32, float)`，尾部 1 个可省 —— `MusicManager:Crossfade`
    {2, {EngineArgKind::Int, EngineArgKind::Float, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 1, {0, 0, 0}},
    // 22 BoolIntIntIntIntInt：`bool(this, i32×5)` —— `Room:SpawnGridEntity`
    {5, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 23 VoidIntBoolIntBoolOpt3：`void(this, i32, bool, i32, bool)`，尾部 3 个可省 ——
    // 固定PC main.lua:844..850：activeSlot or 0 / removeFromPlayerForm ~= false，额外Lua参数忽略。
    {4, {EngineArgKind::Int, EngineArgKind::Bool, EngineArgKind::IntOrZero, EngineArgKind::BoolDefaultTrue,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 3, {0, 1, 0}},
    // ---- 批次 253（2026-10-01）：2 种"带 `Vector2 const&` 参数"的形状。
    // ★ 这两条**不改跳板**：引用 ⇒ 指针 ⇒ 走 `x` 寄存器，本来就在跳板能力里
    //   （做法是把 Lua 的 Vector 拷进我们栈上的槽，再把槽地址当参数）。
    // 24 BoolVector2RefFloat：`bool(this, Vector2&, float)` —— `Room:IsPositionInRoom`
    {2, {EngineArgKind::Vector2Ref, EngineArgKind::Float, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 25 VoidVector2RefFloatHandle：`void(this, Vector2&, float, Entity*)` —— `Game:CharmFart`
    {3, {EngineArgKind::Vector2Ref, EngineArgKind::Float, EngineArgKind::Handle,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // ---- 批次 254（2026-10-01）：ItemPool 接收者 + 2 种新形状（**纯数据、0 代码**）。
    // 形状名与逐条理由写在 `engine_method_api.hpp` 的 `EngineCallShape` 枚举处（定义点在那里）。
    // 26 VoidBoolIntHandle：`void(this, bool, i32, EntityPlayer*)` —— `Game:MoveToRandomRoom`
    //   （PC 契约 `Game.md:424`）。三种参数种类都已在表里，只差这一行组合。
    {3, {EngineArgKind::Bool, EngineArgKind::Int, EngineArgKind::Handle, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::EntityPlayer, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 27 BoolIntBoolBoolOpt2：`bool(this, i32, bool, bool)`，尾部 2 个可省 ——
    //   `ItemPool:RemoveCollectible`（PC 契约 `ItemPool.md:96`；引擎符号 3 格、语料只传 1 个）。
    {3, {EngineArgKind::Int, EngineArgKind::Bool, EngineArgKind::Bool, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 2, {0, 0, 0}},
    // 28 BoolIntIntIntInt：`bool(this, i32, i32, i32, i32)` —— 批次 285：
    //   `EntityNPC:Morph(EntityType, int, int, int)`（PC 契约 `EntityNPC.md:117`；
    //   引擎符号 `_ZN…Entity_NPC5MorphENS_11eEntityTypeEjji` ⇒ 4 格；返回取 `x0`）。
    {4, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 29 VoidIntIntIntBoolBoolBoolOpt3：`void(this, i32, i32, i32, bool, bool, bool)`，
    //   尾部 3 个可省 —— 批次 285：`EntityPickup:Morph`（PC 契约 `EntityPickup.md:40`；
    //   引擎符号 `_ZN…Entity_Pickup5MorphENS_11eEntityTypeEjjbbb` ⇒ 3 个 `i32` + 3 个 `bool`；
    //   语料 3 参/6 参两种写法都有 ⇒ 省略的 3 个布尔保持 0 = PC 缺省 `false`）。
    {6, {EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Bool,
         EngineArgKind::Bool, EngineArgKind::Bool, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 3, {0, 0, 0}},
    // 30 StaticVoidVector2RefHandleVector2RefBoolFloat：**本项目的"静态调用"第一例** ——
    //   `EntityNPC.ThrowSpider(Vector Position, Entity Spawner, Vector TargetPos, boolean Big, float YOffset)`。
    //   ★ 参数顺序按 **AAPCS64 且没有 `this`** 排：整数/指针一路 `Vector2Ref→x0`、
    //     `Handle→x1`、`Vector2Ref→x2`、`Bool→w3`；浮点独立一路 `Float→s0`。
    //   ★ `handleReceipt = FieldReceipt::Entity`：第 2 个实参是 `Entity* Spawner`
    //     （语料里有一处传 `nil` —— `ResolveArgumentHandle` 对 nil 返回 0，正是"没有来源实体"）。
    //   ★ 返回 `EntityNPC` 句柄 ⇒ `EngineReturnKind::EntityNpc`。
    //   ★★ 最后一格 `{1, 0, 0}` = `reserved[0] = 1` = **静态调用**（结构体仍是 16 字节）。
    {5, {EngineArgKind::Vector2Ref, EngineArgKind::Handle, EngineArgKind::Vector2Ref,
         EngineArgKind::Bool, EngineArgKind::Float, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int},
     EngineReturnKind::EntityNpc, FieldReceipt::Entity, IntArgumentGuard::None, 0, {1, 0, 0}},
    // 31 StaticIntVector2RefFloatIntVector2RefHandleBool：`EntityLaser.ShootAngle(...)`（批次 325）。
    //   ★ kinds 按**源码顺序**列（处理器把整数与浮点**各自独立编号** ⇒ 顺序自然对上 AAPCS64）：
    //     `Variant`→`x0`、`SourcePos`→`x1`、`AngleDegrees`→`s0`、`Timeout`→`x2`、`PosOffset`→`x3`、
    //     `Source`→`x4`、第 7 个 `bool`→`w5`。
    //   ★ `optionalArgumentCount = 1`：契约只写 6 个参数（第 7 格是 C++ 缺省），
    //     语料 8 处**全部只传 6 个** ⇒ 省略时该寄存器保持 0（= 与 PC 绑定同一条口径；
    //     为什么"PC 也有第 7 格"见 `EngineCallShape` 那一档的注释）。
    //   ★ 最后 `{1, 0, 0}` = **静态调用**；返回 `EntityLaser` 句柄。
    {7, {EngineArgKind::Int, EngineArgKind::Vector2Ref, EngineArgKind::Float, EngineArgKind::Int,
         EngineArgKind::Vector2Ref, EngineArgKind::Handle, EngineArgKind::Bool,
         EngineArgKind::Int},
     EngineReturnKind::EntityLaser, FieldReceipt::Entity, IntArgumentGuard::None, 1, {1, 0, 0}},
    // 32 Vector2RefIntVector2RefBoolBoolHandleFloatOpt3：`EntityPlayer:FireTechLaser(...)`（批次 326）。
    //   ★ **实例方法**（`p:FireTechLaser(...)`），所以 `{1, 0, 0}` 里第一格是 **0**（不是静态）。
    //   ★★ 最后一格用 `EngineArgKind::FloatDefaultOne`：`DamageMultiplier` 的缺省是 **1**，
    //      省略时要填 `1.0`（`optionalArgumentCount = 3` —— 契约里 `OneHit`/`Source`/`DamageMultiplier`
    //      三个都带缺省；语料那 1 处传 5 个，两条缺省生效）。
    //   ★ kinds 按源码顺序排（整数与浮点各自独立编号）⇒ 自然对上 AAPCS64：
    //     `Position`→`x1`、`OffsetID`→`x2`、`Direction`→`x3`、`LeftEye`→`w4`、`OneHit`→`w5`、
    //     `Source`→`x6`；★ **浮点只有一路**：`DamageMultiplier`→`s0`
    //     （`Direction` 是 `Vector2 const&`，走指针 `x3`、不占浮点寄存器）。
    {7, {EngineArgKind::Vector2Ref, EngineArgKind::Int, EngineArgKind::Vector2Ref,
         EngineArgKind::Bool, EngineArgKind::Bool, EngineArgKind::Handle,
         EngineArgKind::FloatDefaultOne, EngineArgKind::Int},
     EngineReturnKind::EntityLaser, FieldReceipt::Entity, IntArgumentGuard::None, 3, {0, 0, 0}},
    // ---- 批次 335（2026-10-03）：1 种新形状（**纯数据、0 代码**）。
    // 形状名与逐条理由写在 `engine_method_api.hpp` 的 `EngineCallShape` 枚举处（定义点在那里）。
    // 33 VoidIntBoolOpt1：`void(this, i32, bool)`，尾部 1 个可省 ——
    //   `EntityPlayer:ChangePlayerType(PlayerType)` 与 `EntityPlayer:DischargeActiveItem(ActiveSlot)`。
    //   契约各只写 1 个形参、引擎符号都是 2 格 ⇒ 按符号取；省略的那一格保持 0 = PC 的缺省。
    {2, {EngineArgKind::Int, EngineArgKind::Bool, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::EntityPlayer, IntArgumentGuard::None, 1, {0, 0, 0}},
    // ---- 批次 341（2026-10-04）：1 种新形状（**纯数据、0 代码**）。
    // 形状名与逐条理由写在 `engine_method_api.hpp` 的 `EngineCallShape` 枚举处（定义点在那里）。
    // 34 VoidVector2Ref：`void(this, Vector2 const&)` —— `EntityFamiliar:FollowPosition(Vector Pos)`。
    //   ★ `EngineArgKind::Vector2Ref`（批次 252）已把"Lua `Vector` → 拷进我们栈上的 8 字节槽 →
    //     把**槽地址**放进 `x1`"做完了 ⇒ 本档不需要任何新机制，只是一行组合。
    //   ★ 接收者是 `FieldReceipt::EntityFamiliar`（批次 330 立的精确档：精确 vptr + 类型）
    //     —— `FollowPosition` 一进去就解引用 `[this+0xF50]`，拿错类当 `this` 会野读。
    {1, {EngineArgKind::Vector2Ref, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // ---- 批次 344（2026-10-04）：1 种新形状（**纯数据、0 代码**）。
    // 形状名与逐条理由写在 `engine_method_api.hpp` 的 `EngineCallShape` 枚举处（定义点在那里）。
    // 35 BoolVector2RefBool：`bool(this, Vector2 const&, bool)` ——
    //   `PathFinder:HasPathToPos(Vector Pos, boolean IgnorePoop)`（PC 契约 `PathFinder.md:64`）。
    //   ★ 三种零件（`Vector2Ref` / `Bool` 参数，`Bool` 返回）都早已存在 ⇒ 只是组合第一次出现。
    //   ★ 接收者是本批新开的 `FieldReceipt::PathFinder`（严格校验句柄类型：这一条是**调用**，
    //     拿错对象当 `this` 会野读）。★ 两个参数都必填 ⇒ 可省个数 0。
    {2, {EngineArgKind::Vector2Ref, EngineArgKind::Bool, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Bool, FieldReceipt::Entity, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 36：两个必填参数 (int, bool)，不误用可省参数的Music形状。
    {2, {EngineArgKind::Int, EngineArgKind::Bool, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Level, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 37：解析后仍调用已有SetStartSeed(unsigned)，字符串转换复用原生完整守卫。
    {1, {EngineArgKind::Seed, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::Seeds, IntArgumentGuard::None, 0, {0, 0, 0}},
    // 38：AddTrinket的PC包装使用 value or value == nil；已有BoolDefaultTrue按同一真值补参。
    // 尾参可省；reserved[1]使额外Lua参数像PC包装一样被忽略，不改变原生两参ABI。
    {2, {EngineArgKind::Int, EngineArgKind::BoolDefaultTrue, EngineArgKind::Int, EngineArgKind::Int,
         EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int, EngineArgKind::Int},
     EngineReturnKind::Void, FieldReceipt::EntityPlayer, IntArgumentGuard::None, 1, {0, 1, 0}},
};

//: ★★ 批次 338（2026-10-04）：跳板浮点槽的**两侧转换**（契约见 `engine_call_trampoline.hpp`）。
//:
//: 引擎里浮点形参的 mangled 末位是 `f` = **`float`** ⇒ AAPCS64 下它占 `sN` = `dN` 的**低 32 位**。
//: ⇒ 往槽里放的必须是 **f32 位型**（高 32 位填 0），**不是** `static_cast<double>(值)`。
//:
//: ★ 这条以前是错的（批次 338 修）：共享处理器写的是 `static_cast<double>(value)` ⇒ 引擎读
//: `s0`（低 32 位）拿到的是那个 double 的**低半**，对常见数值就是 `0.0f`
//: ⇒ **所有走数据行的浮点参数都传了错值**（`MusicManager:VolumeSlide` / `Room:IsPositionInRoom` /
//: `EntityLaser.ShootAngle` / `EntityPlayer:FireTechLaser` 的倍率 / `EntityNPC.ThrowSpider` 的 YOffset …）。
//: 为什么以前没被测出来：ABI 门禁（`test_engine_call_trampoline.py`）的假函数只用了 **`double`**
//: 形参，而三个批次用例断言的是"数值上的 double 中间表示"—— 两处都绕过了这条契约。
[[nodiscard]] inline double EngineFloatArgument(double value) noexcept {
    const float narrowed = static_cast<float>(value);
    std::uint32_t bits = 0;
    std::memcpy(&bits, &narrowed, sizeof(bits));
    const std::uint64_t wide = bits;
    double storage = 0.0;
    std::memcpy(&storage, &wide, sizeof(storage));
    return storage;
}

//: 返回侧同理：引擎在 `s0` 回 `float` ⇒ 读 `d0` 的**低 32 位**再按 `float` 解释。
[[nodiscard]] inline double EngineFloatResult(double raw) noexcept {
    std::uint64_t wide = 0;
    std::memcpy(&wide, &raw, sizeof(wide));
    const std::uint32_t bits = static_cast<std::uint32_t>(wide);
    float value = 0.0F;
    std::memcpy(&value, &bits, sizeof(value));
    return static_cast<double>(value);
}

//: `Handle` 类参数的解析：`nil` ⇒ 空指针（PC 的可选对象参数默认就是 nil，引擎侧就等于 `nullptr`）；
//: 其余走与字段接收者同一套句柄校验（类型不对时报错，与 PC 上"传错对象"的行为一致）。
std::uintptr_t ResolveArgumentHandle(lua_State* state, FieldReceipt receipt, int index) {
    if (lua_isnoneornil(state, index)) {
        return 0;
    }
    return ResolveFieldReceipt(state, receipt, index);
}


} // namespace

const EngineCallShapeRow* EngineCallShapeRows(std::size_t* count) noexcept {
    if (count != nullptr) {
        *count = sizeof(kEngineCallShapes) / sizeof(kEngineCallShapes[0]);
    }
    return kEngineCallShapes;
}

// --- 批次 069：数据行的"调用 / 静默降级"计数器（诊断面，见 `api_call_stats.hpp`） ------
//
// 这几格存在的唯一目的：**不再靠探针回答"这条 API 到底有没有被调到"**。
// 全部住 `bss`、加一条 API 也不多花一个字节；读数工具按符号直读。
extern "C" {
std::atomic<std::uint32_t> g_IsaacApiRowCalls{0};
std::atomic<std::uint32_t> g_IsaacApiRowLastCallId{0};
std::atomic<std::uint32_t> g_IsaacApiRowLastCallKind{0};
std::atomic<std::uint32_t> g_IsaacEngineRowCalls{0};
std::atomic<std::uint32_t> g_IsaacEngineRowRejectReceiver{0};
std::atomic<std::uint32_t> g_IsaacEngineRowRejectOffset{0};
std::atomic<std::uint32_t> g_IsaacEngineRowRejectEntry{0};
std::atomic<std::uint32_t> g_IsaacEngineRowLastRejectId{0};
std::atomic<std::uint32_t> g_IsaacEngineRowLastRejectReason{0};
// 批次 141（2026-09-26）：第 4 类降级（参数校验挡下）+ 服装查表 / 加摘服装的现场。
// 见 `api_call_stats.hpp` 里那一段的由来 —— 它们要回答的是"跳舞模组为什么崩在
// `AddCostume(nullptr)`"：模组那 23 条服装到底在不在容器里、查到的编号是几、挡下过几次。
std::atomic<std::uint32_t> g_IsaacEngineRowRejectGuard{0};
std::atomic<std::uint32_t> g_IsaacCostumePathCalls{0};
std::atomic<std::uint32_t> g_IsaacCostumePathHits{0};
std::atomic<std::uint32_t> g_IsaacCostumePathMisses{0};
std::atomic<std::uint32_t> g_IsaacCostumePathLastId{0};
std::atomic<std::uint32_t> g_IsaacCostumePathNullCount{0};
std::atomic<std::uint32_t> g_IsaacNullCostumeLastRequestedId{0};
std::atomic<std::uint32_t> g_IsaacNullCostumeGuardUnknown{0};
// 批次 148（2026-09-26）：曲目名反查（`Isaac.GetMusicIdByName`）的现场。
// ★ `g_IsaacMusicIdLastName` 是 **`extern "C"` 块里的裸名数组**（读数工具按名字直读），
//   与上面那几格同一个口径；定义处不给初始化值之外的东西，别拆出这个块。
std::atomic<std::uint32_t> g_IsaacMusicIdCalls{0};
std::atomic<std::uint32_t> g_IsaacMusicIdHits{0};
std::atomic<std::uint32_t> g_IsaacMusicIdLastResult{0};
std::atomic<std::uint32_t> g_IsaacMusicIdTableCount{0};
char g_IsaacMusicIdLastName[64] = {};
// 批次 154（2026-09-27）：`Music:Play` 的编号保险挡下一次（真机事故见 `api_call_stats.hpp` 那一格）。
std::atomic<std::uint32_t> g_MusicPlayGuardBlocked{0};
}

// `CheckNullItemId(id)`（批次 141）—— 见 `engine_method_api.hpp` 的声明处。
//
// 判据与 `IsaacGetCostumeIdByPath` 逐条同源：同一条 `ItemConfig` 解析链、同一对 begin/end 偏移、
// 同样的"条目指针非空"判定。`GetNullItem(id)` 是**纯下标取值**（批次 139 的反汇编证据）⇒
// "下标在范围内且那个槽里有条目"就等价于"引擎拿到非空指针、不会崩"。
//
// `id < 0` 必须先判：模组在查不到时会直接把 `-1` 喂进来（The Specialist for Good Items 的
// `main.lua:461/465`），而 `-1` 转成无符号会变成一个巨大的下标 ⇒ 越界判定本就该先做。
NullItemIdVerdict CheckNullItemId(std::int64_t id) noexcept {
    if (id < 0) {
        return NullItemIdVerdict::Invalid;
    }
    const std::uintptr_t config = ResolveItemConfig();
    if (config == 0) {
        return NullItemIdVerdict::Undecidable;
    }
    ItemVectorView view{};
    if (!ReadItemVector(config, kItemConfigNullItemBeginOffset, kItemConfigNullItemEndOffset,
                        &view)) {
        return NullItemIdVerdict::Undecidable;
    }
    const std::uint64_t index = static_cast<std::uint64_t>(id);
    if (index >= view.count) {
        return NullItemIdVerdict::Invalid;  // 越界：引擎那条路会拿到空指针
    }
    std::uintptr_t item = 0;
    if (!ReadEngine(view.begin + static_cast<std::uintptr_t>(index) * sizeof(std::uintptr_t),
                    &item)) {
        return NullItemIdVerdict::Undecidable;
    }
    return item != 0 ? NullItemIdVerdict::Valid : NullItemIdVerdict::Invalid;
}

// `CheckMusicId(id)`（批次 154，2026-09-27）—— 见 `engine_method_api.hpp` 的声明处。
//
// 判据与 `IsaacGetMusicIdByName` **同一条链、同一份常量**（两处各写一遍就会漂移，而漂移的后果
// 一边是"吞掉合法调用"、另一边是"挡不住崩溃"）：
//   * 曲目表 = `Music + 0x3D8` 那对 begin/end（`kMusicEntryVector*Offset`），步长 `0x70`；
//   * `Music::Play @ 0x427238` 就是 `条目 = *(Music + 0x3D8) + id * 0x70`（反汇编里的 `umaddl`，
//     立即数就是同一个 `kMusicEntrySize`）⇒ `0 <= id < 条数` 才不会读到向量外面去；
//   * 负数必须先判：`-1` 换算成"条目地址"是往表**前面**读 0x70 字节。
MusicIdVerdict CheckMusicId(std::int64_t id) noexcept {
    if (id < 0) {
        return MusicIdVerdict::Invalid;
    }
    const std::uintptr_t manager = ResolveManagerAddress();
    if (manager == 0 || manager > UINTPTR_MAX - kManagerMusicOffset) {
        return MusicIdVerdict::Undecidable;
    }
    const std::uintptr_t music = manager + kManagerMusicOffset;
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    if (!ReadEngine(music + kMusicEntryVectorBeginOffset, &begin) ||
        !ReadEngine(music + kMusicEntryVectorEndOffset, &end) || begin == 0 || end < begin ||
        (end - begin) % kMusicEntrySize != 0) {
        return MusicIdVerdict::Undecidable;
    }
    const std::size_t count = (end - begin) / kMusicEntrySize;
    if (count > kMusicEntryMaximumCount) {
        return MusicIdVerdict::Undecidable;  // 形状不对 ⇒ 不当"越界"判（那是读错了，不是编号有问题）
    }
    return static_cast<std::uint64_t>(id) < count ? MusicIdVerdict::Valid
                                                  : MusicIdVerdict::Invalid;
}

// --- 批次 051：引擎方法类 API 的**共享处理器**（数据行机制，见 `engine_method_api.hpp`） ----
// --- 批次 055：参数编组改成"按签名描述符 + 通用跳板"，于是新签名只花数据 ----
//
// 为什么要有它：一条"调引擎方法"的 API 原本要手写 ≈490 字节代码（入口守卫 224 + handler ~200），
// 而代码段当时只有 512 KiB、保留线 32 KiB ⇒ 想一次补几条就会**构建失败**（2026-09-19 实测）。
// 这里把"不变的流程"收成**一份**，每个 API 只剩一行 16 字节的数据：
// 于是"以后陆续实现 API"只剩数据成本，不再有代码成本。
//
// 判据与手写版逐字相同：接收者先校验、方法用"基址 + 偏移 + 入口 4 字节指纹"解析、
// 拿不到就按 PC 语义**静默降级**（void 什么都不做、整数压 0），**绝不报错**
// （报错会把整条模组回调摘掉，比"这次没生效"严重得多）。
int EngineMethodHandler(lua_State* state) {
    const auto* row =
        static_cast<const EngineMethodRow*>(lua_touserdata(state, lua_upvalueindex(1)));
    if (row == nullptr) {
        return luaL_error(state, "engine method row missing");
    }
    // 批次 093：同上，计时由挂载处的中央包装负责。
    if (row->probeBit != 0xFF) {
        RecordApiSequenceSecondary(row->probeBit);
    }
    // 批次 069：先记"被调到了"——以下任何一条 `luaL_error` 之后都不会再走到这里。
    isaac::runtime::RecordEngineRowCall(row->id);
    // 批次 436：同窗口内的换房 API —— 让"当前房间解析"的缓存立即失效（否则同一派发窗口里
    // 后续的查询会给旧房间）。id 取自 `game_api.cpp` 的 `kGameEngineRows`（`MakeId(ApiDomain::Game,
    // 1, 0x000A/0x000B)`），已用 `read_device_state_via_gdb.api_name` 实测核过。
    {
        constexpr std::uint32_t kGameChangeRoomId = 0x0201000AU;
        constexpr std::uint32_t kGameStartRoomTransitionId = 0x0201000BU;
        if (row->id == kGameChangeRoomId) {
            // 固定PC main.lua的dim or -1：省略/nil/false取当前维度，0保持；原生仍收完整两参。
            if (lua_gettop(state) < 2) {
                return luaL_error(state, "Game:ChangeRoom expects room index");
            }
            lua_settop(state, 3);
            if (lua_toboolean(state, 3) == 0) {
                lua_pushinteger(state, -1);
                lua_replace(state, 3);
            }
        }
        if (row->id == kGameStartRoomTransitionId) {
            // 固定PC main.lua补公开缺省；本运行时不加载整份启动包装，故在同一入口补齐。
            if (lua_gettop(state) < 3) {
                return luaL_error(state, "Game:StartRoomTransition expects room index and direction");
            }
            lua_settop(state, 6);
            if (lua_toboolean(state, 4) == 0) {
                lua_pushinteger(state, 0);  // WALK；Lua的0为真，显式0仍保留。
                lua_replace(state, 4);
            }
            if (lua_toboolean(state, 6) == 0) {
                lua_pushinteger(state, -1);
                lua_replace(state, 6);
            }
        }
        if (row->id == kGameChangeRoomId || row->id == kGameStartRoomTransitionId) {
            isaac::runtime::InvalidateCurrentRoomCache();
        }
    }
    // 消息按 catalog 里的 `owner:name` 现拼（与手写处理器同口径，只在出错路径上拼）。
    const LuaApiDescriptor* descriptor = ApiCatalog::Default().Find(row->id);
    const char* owner = descriptor != nullptr ? descriptor->owner : "?";
    const char* name = descriptor != nullptr ? descriptor->name : "?";
    std::size_t shapeCount = 0;
    const EngineCallShapeRow* shapes = EngineCallShapeRows(&shapeCount);
    const std::size_t shapeIndex = static_cast<std::size_t>(row->shape);
    if (shapes == nullptr || shapeIndex >= shapeCount) {
        return luaL_error(state, "%s:%s has an unsupported call shape", owner, name);
    }
    const EngineCallShapeRow& shape = shapes[shapeIndex];
    if (shape.argumentCount != row->argumentCount) {
        // 数据行自相矛盾：按错误的 ABI 调进去会踩坏引擎状态，所以这里**报错**而不是硬调。
        // 门禁（`test_engine_method_rows.py`）会在构建前就把这种情况拦下来。
        return luaL_error(state, "%s:%s row and call shape disagree on the argument count", owner,
                          name);
    }
    // 接收者：`Room` 不从栈上取（解析当前房间），其余都在第 1 个参数上。
    // ★★ 批次 324：**静态调用**（`EntityNPC.ThrowSpider(...)`）连"第 1 个参数"都没有 ——
    //   它没有 `this`，五个实参自己排满 `x0..x3` / `s0`（见 `EngineCallShapeRow::staticCall`）。
    int receiverArguments = shape.staticCall()
                                ? 0
                                : (row->receipt == FieldReceipt::Room ? 0 : 1);
    const int top = lua_gettop(state);
    const int maximumArguments = static_cast<int>(shape.argumentCount);
    if (!shape.staticCall() && row->receipt == FieldReceipt::Room &&
        luaL_testudata(state, 1, LuaRuntime::kRoomMetatable) != nullptr) {
        // ★ 批次 069 修正（宿主场景第一次真的按 PC 写法调用时暴露）：PC 模组一律写
        // `Game():GetRoom():PlayMusic()` —— 冒号调用会把 `self` 也压进栈，而这里原先只接受
        // `Room.PlayMusic()` 那种点号写法（栈上**没有** self）⇒ 真机上这条 API 一被调用就报
        // "Room:PlayMusic expects 0 argument(s)"，整条模组回调被打断（比"没生效"更糟）。
        // 2026-10-25：按真正的Room句柄识别self，省略可选尾参时也必须跳过它。
        receiverArguments = 1;
    }
    // 批次 207（2026-09-29）：**尾部 `optionalArgumentCount` 个参数可以不写**。
    // 只有"省略时寄存器保持 0 恰好就是 PC 缺省值"的参数才能这么声明（见形状表那一格）；
    // `Entity:IsActiveEnemy(bool includeDead)` 就是这一条（缺省 `false`）。
    const int minimumArguments = maximumArguments - static_cast<int>(shape.optionalArgumentCount);
    int providedArguments = top - receiverArguments;
    if (providedArguments > maximumArguments &&
        (shape.ignoresExtraArguments() || row->id == 0x0E01006FU)) {
        // PC AddHearts原绑定只读Hearts及可选Lua真值，其余尾参不参与调用。
        providedArguments = maximumArguments;
    }
    if (providedArguments < minimumArguments || providedArguments > maximumArguments) {
        if (shape.optionalArgumentCount != 0) {
            return luaL_error(state, "%s:%s expects at most %d argument(s)", owner, name,
                              maximumArguments);
        }
        return luaL_error(state, "%s:%s expects %d argument(s)", owner, name, maximumArguments);
    }
    // `integers[0]` 留给接收者（AAPCS64 的 `x0` = this），参数从 `integers[1]`/`floats[0]` 起排。
    std::uint64_t integers[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    double floats[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    int integerCount = shape.staticCall() ? 0 : 1;
    int floatCount = 0;
    // 批次 252：`Vector2Ref` 参数的槽 —— 引擎收的是 `Vector2 const&`，
    // 所以要把 Lua 的 Vector 拷进**我们自己的**槽、再把槽的地址当参数传。
    // ★ 用**函数内 `static`**（不是局部数组）：真实契约只要求"调用期间有效"，而局部数组在
    //   共享处理器返回后就失效了 —— 那会让"拷进去了没有"变得**不可测**（宿主测试只能在脚本
    //   跑完之后读，读到的是被复用过的栈）。`static` 把生命周期拉到进程，代价 8×8=64 字节 bss，
    //   且不受重入影响（引擎调用在托管回调里同步发生、不会重入）。
    struct Vector2Slot {
        float x;
        float y;
    };
    static Vector2Slot vectorSlots[8];
    int vectorSlotCount = 0;
    bool argumentsValid = true;
    // ★ 只搬**实际给出**的那些参数：省略的槽保持 0（= 形状里声明的缺省值）。
    for (int index = 0; index < providedArguments && argumentsValid; ++index) {
        const int stackIndex = receiverArguments + index + 1;
        switch (shape.argumentKinds[index]) {
            case EngineArgKind::Seed: {
                if (integerCount >= 8) { argumentsValid = false; break; }
                if (lua_type(state, stackIndex) == LUA_TSTRING) {
                    // 新的Lua调用帧让既有静态解析器从参数1读取字符串；原参数保持保活。
                    lua_pushcfunction(state, isaac::runtime::Api400SeedsString2Seed);
                    lua_pushvalue(state, stackIndex);
                    lua_call(state, 1, 1);
                    integers[integerCount++] = static_cast<std::uint32_t>(lua_tointeger(state, -1));
                    lua_pop(state, 1);
                } else if (isaac::runtime::IsIntegerArgument(state, stackIndex)) {
                    integers[integerCount++] = static_cast<std::uint64_t>(
                        static_cast<std::int64_t>(lua_tointeger(state, stackIndex)));
                } else {
                    argumentsValid = false;
                }
                break;
            }
            case EngineArgKind::IntOrZero:
                if (lua_isnoneornil(state,stackIndex) ||
                    (lua_isboolean(state,stackIndex) && !lua_toboolean(state,stackIndex))) {
                    if(integerCount>=8){argumentsValid=false;break;}
                    integers[integerCount++]=0;break;
                }
                [[fallthrough]];
            case EngineArgKind::Int: {
                if (!isaac::runtime::IsIntegerArgument(state, stackIndex) || integerCount >= 8) {
                    argumentsValid = false;
                    break;
                }
                integers[integerCount++] = static_cast<std::uint64_t>(
                    static_cast<std::int64_t>(lua_tointegerx(state, stackIndex, nullptr)));
                break;
            }
            case EngineArgKind::Float:
            // ★ 批次 326：`FloatDefaultOne` **被给出时**与 `Float` 完全一样
            //   （缺省值的差异只体现在"省略"那条路上，见下面补省略的那一段）。
            case EngineArgKind::FloatDefaultOne: {
                int isNumber = 0;
                const lua_Number value = lua_tonumberx(state, stackIndex, &isNumber);
                if (isNumber == 0 || floatCount >= 8) {
                    argumentsValid = false;
                    break;
                }
                floats[floatCount++] = EngineFloatArgument(value);
                break;
            }
            case EngineArgKind::BoolDefaultTrue:
                if(integerCount>=8){argumentsValid=false;break;}
                integers[integerCount++]=!lua_isboolean(state,stackIndex)||lua_toboolean(state,stackIndex)?1U:0U;
                break;
            case EngineArgKind::Bool: {
                if (integerCount >= 8) {
                    argumentsValid = false;
                    break;
                }
                integers[integerCount++] = lua_toboolean(state, stackIndex) != 0 ? 1u : 0u;
                break;
            }
            case EngineArgKind::Handle: {
                if (integerCount >= 8) {
                    argumentsValid = false;
                    break;
                }
                integers[integerCount++] =
                    static_cast<std::uint64_t>(ResolveArgumentHandle(state, shape.handleReceipt,
                                                                     stackIndex));
                break;
            }
            case EngineArgKind::Vector2Ref: {
                // 批次 252：引擎收的是 `Vector2 const&` ⇒ **传指针**（下一个 `x` 寄存器）。
                // 槽放在共享处理器自己的栈上：调用期间有效，`blr` 回来之后就没人再用了。
                if (integerCount >= 8 || vectorSlotCount >= 8) {
                    argumentsValid = false;
                    break;
                }
                auto* vector =
                    TryVectorArgument(state,stackIndex);
                if (vector == nullptr) {
                    argumentsValid = false;
                    break;
                }
                vectorSlots[vectorSlotCount].x = vector->x;
                vectorSlots[vectorSlotCount].y = vector->y;
                integers[integerCount++] =
                    AddressBitsForEngineArgument(&vectorSlots[vectorSlotCount]);
                ++vectorSlotCount;
                break;
            }
        }
    }
    // 批次 326（2026-10-03）：**补省略的尾部** —— 默认仍然是 0（与之前**一模一样**），
    // 但声明成 `EngineArgKind::FloatDefaultOne` 的那几格要填 `1.0`：
    // PC 契约里确实有"缺省不是 0"的浮点参数（`… float DamageMultiplier = 1`），
    // 而 `optionalArgumentCount` 那一档的语义是"省略的寄存器保持 0" ⇒ 只能靠这一种新参数种类表达。
    // ★ 省略的参数**只可能在尾部**（前面的都是"给出"的）⇒ 从 `providedArguments` 起扫即可。
    // ★ 每扫过一格**照样推进对应的计数器**（整数与浮点各自独立编号）：不推进的话，
    //   后面几格的寄存器位置会串（例如"两个浮点、省掉第一个"）。
    for (int index = providedArguments; index < maximumArguments && argumentsValid; ++index) {
        switch (shape.argumentKinds[index]) {
            case EngineArgKind::BoolDefaultTrue:
                if(integerCount>=8){argumentsValid=false;break;}
                integers[integerCount++]=1;break;
            case EngineArgKind::FloatDefaultOne:
                if (floatCount >= 8) {
                    argumentsValid = false;
                    break;
                }
                floats[floatCount++] = EngineFloatArgument(1.0);
                break;
            case EngineArgKind::Float:
                if (floatCount >= 8) {
                    argumentsValid = false;
                    break;
                }
                ++floatCount;               // 保持 0（数组本来就初始化成 0）
                break;
            case EngineArgKind::Vector2Ref:
            case EngineArgKind::Handle:
            case EngineArgKind::IntOrZero:
            case EngineArgKind::Bool:
            case EngineArgKind::Int:
            default:
                if (integerCount >= 8) {
                    argumentsValid = false;
                    break;
                }
                ++integerCount;             // 保持 0
                break;
        }
    }
    if (!argumentsValid) {
        return luaL_error(state, "%s:%s expects %d argument(s)", owner, name,
                          static_cast<int>(shape.argumentCount));
    }
    // ★★ 批次 324：静态调用**没有接收者** —— 连解析都不做（`ResolveFieldReceipt` 对静态行
    //   没有意义，而且解析失败会被后面那段当成"降级"记一笔、把这一行判成不可调）。
    const std::uintptr_t receiver =
        shape.staticCall() ? 0
                           : ResolveFieldReceipt(state, row->receipt, receiverArguments == 0 ? 0 : 1);
    if (!shape.staticCall()) {
        integers[0] = static_cast<std::uint64_t>(receiver);
    }
    // 批次 069：三种"静默降级"各自记账，这样"这条 API 调了却没生效"在设备上是**可区分的**
    // —— 接收者拿不到（句柄失效/不在回调里）、偏移解析不到（模块基址不对）、
    // 入口指纹不匹配（偏移写错，最值得怀疑的一类）。
    std::uintptr_t engineMethod = 0;
    bool callable = false;
    if (!shape.staticCall() && receiver == 0) {
        isaac::runtime::RecordEngineRowReject(
            row->id, isaac::runtime::EngineRowRejectReason::Receiver);
    } else if (IsEngineVtableRow(row->offset)) {
        // 批次 303（2026-10-03）：**按 vtable 槽号调用**（虚函数）—— 调哪一个实现取决于接收者的
        // 动态类型，只有运行期才知道，所以这一支不做"模块基址 + 固定偏移 + 入口指纹"，改成：
        //   vptr = [receiver]（对象首字），target = [vptr + 0x10 + 槽号*8]（Itanium vtable 布局）。
        // 行约定、槽号从哪来（**Switch 的 `_ZTV`，不许抄 PC 的**）与三条护栏都写在
        // `engine_method_api.hpp` 的 `kEngineVtableRowFlag` 那一段。
        // ★ 校验失败一律**不调、也不报错**，只记 `EngineRowRejectReason::Vtable`（与同族口径一致）。
        const std::uint32_t slot = row->offset & ~kEngineVtableRowFlag;
        std::uintptr_t vtable = 0;
        std::uintptr_t target = 0;
        const bool slotInRange = slot <= kEngineVtableMaximumSlot;
        if (!slotInRange ||
            !engine_memory::LoadPointerAt(receiver, 0, 0, &vtable, &IsEngineMemoryReadable) ||
            vtable == 0 ||
            !engine_memory::LoadPointerAt(
                vtable, static_cast<std::uintptr_t>(slot) * kEngineVtableSlotStride,
                0, &target, &IsEngineMemoryReadable) ||
            target == 0) {
            isaac::runtime::RecordEngineRowReject(
                row->id, isaac::runtime::EngineRowRejectReason::Vtable);
        } else {
            engineMethod = target;
            callable = true;
        }
    } else {
        // ★ 批次 428：这一支是**方法分派的热路径**（API 层归因实测：`EntityPlayer.__index`
        //   每秒 65,368 次、`EntityPlayer:HasCollectible` 44,744 次都从这里过）。两次守卫
        //   （基址原子读 + 可读性检查 + 入口 4 字节比对）在同一基址下结论恒定 ⇒ 记住结果。
        //   ★ 只缓存成功：判据没过时下面**照原样重跑一遍**并记 `RecordEngineRowReject`，
        //   所以"降级三原因"的计数口径与不缓存时完全一致。
        engineMethod = isaac::runtime::EngineEntryAddressCached<IsEngineMemoryReadable>(
            g_EngineRowEntrySlot, row->offset, row->entryWord);
        // 卡牌使用已安装5号入口中继；完整登记校验通过后仍调用公开入口。
        if (engineMethod == 0 && row->offset == kEntityPlayerUseCardOffset) {
            engineMethod = EntityMethodByExpectedBytes(kEntityPlayerUseCardOffset,
                                                       kEntityPlayerUseCardExpectedBytes);
        }
        if (engineMethod == 0 && row->offset == kEntityPlayerEvaluateItemsOffset) {
            engineMethod = EntityMethodByExpectedBytes(kEntityPlayerEvaluateItemsOffset,
                                                       kEntityPlayerEvaluateItemsExpectedBytes);
        }
        if (engineMethod == 0) {
            const std::uintptr_t address =
                isaac::runtime::EngineOffsetAddress<IsEngineMemoryReadable>(row->offset);
            if (address == 0) {
                isaac::runtime::RecordEngineRowReject(
                    row->id, isaac::runtime::EngineRowRejectReason::Offset);
            } else {
                isaac::runtime::RecordEngineRowReject(
                    row->id, isaac::runtime::EngineRowRejectReason::EntryWord);
            }
        } else {
            callable = true;
        }
    }    // 批次 141：这一形状的整数参数是"null 服装编号" ⇒ **无论后面挡不挡，先把它记下来**。
    // 读数的判读靠这一格："模组实际喂了什么"与"我们挡没挡"必须能对上（见 `api_call_stats.hpp`）。
    if (shape.intGuard == IntArgumentGuard::ValidNullItemId && shape.argumentCount >= 1) {
        isaac::runtime::RecordNullCostumeRequest(static_cast<std::int32_t>(integers[1]));
        // 编号无效（负数/越界/空槽）⇒ **主动不调引擎**：引擎那条路会 `GetNullItem(id)` 拿到空、
        // 再 `AddCostume(nullptr)` 解引用空指针（真机 `Data Abort`、`Address = 0`）。
        // ★ 这是**保险**、不是修复：挡下过几次记进 `g_IsaacEngineRowRejectGuard`，
        //   症状不会无声消失。判定不了时照原样放行，并记 `g_IsaacNullCostumeGuardUnknown`。
        switch (CheckNullItemId(static_cast<std::int64_t>(integers[1]))) {
            case NullItemIdVerdict::Invalid:
                isaac::runtime::RecordEngineRowReject(
                    row->id, isaac::runtime::EngineRowRejectReason::ArgumentGuard);
                callable = false;
                break;
            case NullItemIdVerdict::Undecidable:
                isaac::runtime::RecordNullCostumeGuardUnknown();
                break;
            case NullItemIdVerdict::Valid:
                break;
        }
    }
    // 批次 184：`Ref2U32Pair` 形状的"引用出参"。
    //   两个 Lua 参数先被搬进**这两个局部槽**（槽里就是入参初值），再把**槽的地址**写回
    //   `integers[1]/[2]` —— 引擎按 `void(this, uint&, uint&)` 收到 `x1`/`x2` 之后改写槽里的值。
    //   ★ 为什么用局部变量：引擎只在这一条调用期间用这两个地址，返回后我们立刻把值读走。
    //   ★ 为什么不用动跳板：槽是**我们自己栈上的内存**、以"指针"进整数组参数 ——
    //     `engine_call_trampoline.hpp` 的能力边界管的是"参数/返回值只能是标量"，
    //     指针本来就在它支持的范围内（它是出参→指针、不是结构体返回）。
    std::uint32_t refOut0 = 0;
    std::uint32_t refOut1 = 0;
    if (shape.returnKind == EngineReturnKind::U32PairTable && shape.argumentCount >= 2) {
        refOut0 = static_cast<std::uint32_t>(integers[1]);
        refOut1 = static_cast<std::uint32_t>(integers[2]);
        integers[1] = AddressBitsForEngineArgument(&refOut0);
        integers[2] = AddressBitsForEngineArgument(&refOut1);
    }
    std::uint64_t integerResult = 0;
    double floatResult = 0.0;
    if (callable) {
        ::EngineCallTrampoline(engineMethod, integers, floats, &integerResult,
                                             &floatResult);
        // PC Entity.Update includes its entity-family post-update callback.
        // Normal native frame dispatch remains independent; rejected calls do
        // not dispatch, and the projectile family keeps its existing tail relay.
        if (row->id == 0x0E01006BU) {
            LuaRuntime::DispatchPostManualEntityUpdate(static_cast<std::uintptr_t>(integers[0]));
        }
    }
    // PC 的返回是 int 时拿不到就压 0、是 boolean 就压 false、是 float 就压 0.0（**不压 nil**）：
    // 模组普遍拿返回值做算术或比较，nil 会变成 "attempt to compare nil with number" 把回调打断。
    switch (shape.returnKind) {
        case EngineReturnKind::Void:
            return 0;
        case EngineReturnKind::Bool:
            lua_pushboolean(state, integerResult != 0 ? 1 : 0);
            return 1;
        case EngineReturnKind::Float:
            lua_pushnumber(state, static_cast<lua_Number>(EngineFloatResult(floatResult)));
            return 1;
        case EngineReturnKind::EntityNpc:
            // 批次 324：**句柄返回** —— `x0` 是引擎交回的对象指针。
            // ★ 空指针 ⇒ 压 `nil`（PC 口径：拿不到就 `nil`，**不是**报错；模组普遍写
            //   `local n = EntityNPC.ThrowSpider(...); if n then ... end`）。
            //   ★ 这一格不能省：`PushEntityHandle` **不挡空指针**，包一个 `entity == 0`
            //     的句柄会让 `n ~= nil` 成立、之后每次访问都走"失效句柄"那条路。
            // ★ 拿不到引擎调用时（`callable == false`）`integerResult` 本来就是 0 ⇒ 同样压 `nil`，
            //   与同族"静默降级、不报错"一致。
            if (integerResult == 0) {
                PushNil(state);
                return 1;
            }
            PushEntityHandle(state, integerResult, kEntityNPCMetatable);
            return 1;
        case EngineReturnKind::EntityLaser:
            // 批次 325：同上，压 `EntityLaser` 句柄（`EntityLaser.ShootAngle(...)` 的返回）。
            if (integerResult == 0) {
                PushNil(state);
                return 1;
            }
            PushEntityHandle(state, integerResult, kEntityLaserMetatable);
            return 1;
        case EngineReturnKind::U32PairTable: {            // 引擎把改写后的两个值写回了槽 ⇒ 压成一张 `{[1]=v1, [2]=v2}` 的表。
            // ★ 消费者 EID 的读法（`features/eid_repentogon.lua:269`）是 `t[1] ~= -1` 才算"有掉落"，
            //   所以**引擎一次都没写时我们也要把入参原样回传**（槽的初值就是 Lua 给的值）——
            //   这一格绝对不能压 `nil`：模组拿它做 `~=` 比较会抛
            //   "attempt to compare nil with number"、把整条回调摘掉（比"值不对"更糟）。
            // ★ 调用没走到（`callable == false`）时同样压这两格：口径与同族一致 ——
            //   **静默降级、不报错**（拒绝原因已经记进 `RecordEngineRowReject` 的计数器）。
            lua_createtable(state, 2, 0);
            lua_pushinteger(state, static_cast<lua_Integer>(refOut0));
            lua_rawseti(state, -2, 1);
            lua_pushinteger(state, static_cast<lua_Integer>(refOut1));
            lua_rawseti(state, -2, 2);
            return 1;
        }
        case EngineReturnKind::Int:
        default:
            lua_pushinteger(state, static_cast<lua_Integer>(integerResult));
            return 1;
    }
}

//: 批次 301（2026-10-03）：**返回 0 个值**（PC 返回 `void`）的那几种 kind。
//:
//: 为什么单独抽一条：接收者解析不到时（句柄无效 / 拿不到当前房间 / 拿不到 `g_Game`），
//: 通用分支会压一个"降级值"并返回 **1** —— 那对**有返回值的** kind 是对的（`nil` 会让模组抛错），
//: 但对这三条**本来就返回 0 个值**的写侧 kind 是错的：
//: `select('#', p:AddCacheFlags(x))` 会从 0 变成 1（凭空多一个值）。
//: ⇒ 它们走这条早退分支，**什么都不做、也不返回值** —— 与 PC 的 `void` 一致。
//: （本批只补这一处；三条写侧 kind 的行为因此对齐。）
constexpr bool RowReturnsNoValues(FieldKind kind) noexcept {
    return kind == FieldKind::BoolBitWrite || kind == FieldKind::BoolBitArrayOfWriteArg ||
           kind == FieldKind::U32OrWithArg || kind == FieldKind::ColorModWrite ||
           kind == FieldKind::BoolWriteConst || kind == FieldKind::U32FromArg ||
           //: 批次 333（2026-10-03）：`FloatMultiplyArg`（`Entity:MultiplyFriction(Value)`）
           //: 也是写侧、也返回 0 个值 ⇒ **必须列在这里**，否则接收者解析不到时会凭空多压一个值
           //: （`select('#', e:MultiplyFriction(1.2))` 会从 0 变 1）。
           kind == FieldKind::FloatMultiplyArg ||
           //: 批次 341（2026-10-04）：`FloatFromArg`（`EntityLaser:SetMaxDistance(Distance)`）同款
           //: —— 写侧、返回 0 个值（`select('#', l:SetMaxDistance(40))` 必须是 0）。
           kind == FieldKind::FloatFromArg ||
           //: 批次 342（2026-10-04）：`FloatThenIntFromArgs`（`Game:Darken(Darkness, Timeout)`）
           //: 与 `TwoByteConstZero`（`EntityPlayer:StopExtraAnimation()`）也都是写侧、
           //: 都返回 0 个值 ⇒ **必须列在这里**。
           kind == FieldKind::FloatThenIntFromArgs || kind == FieldKind::TwoByteConstZero;
}

int FieldApiHandler(lua_State* state) {
    const auto* row =
        static_cast<const FieldApiRow*>(lua_touserdata(state, lua_upvalueindex(1)));
    if (row == nullptr) {
        return luaL_error(state, "field api row missing");
    }
    // 批次 093：计时改由**挂载处的中央包装**统一负责（见 `owner_binding.cpp` 的
    // `PushTimedHandler`）—— 在这里再记一笔就是重复计数。
    if (row->probeBit != 0xFF) {
        RecordApiSequenceSecondary(row->probeBit);
    }
    // 批次 069：与引擎方法行同口径，先记"被调到了"（字段行没有入口指纹，所以不记被拒）。
    isaac::runtime::RecordFieldRowCall(row->id);
    // 批次 207（2026-09-29）：`U64FlagsAllSet`（`Entity:HasEntityFlags(Flags)`）是第一条
    // **带参数**的字段行 —— 掩码由 Lua 给，所以这里要按 kind 决定"应收几个参数"。
    // 批次 292（2026-10-02）：`BoolBitWrite`（`Room:SetClear(...)`）是第二条 ——
    // 它也收一个实参，但**只闸个数、不闸类型**（理由见下面那段），且**不返回值**。
    // 其余 kind 照旧：**只收接收者**（多一个参数就是写错了，报错比硬读安全）。
    const bool wantsIntegerArgument = row->kind == FieldKind::U64FlagsAllSet ||
                                      row->kind == FieldKind::U32FromArg;
    const bool wantsBitWriteArgument = row->kind == FieldKind::BoolBitWrite;
    //: 批次 297（2026-10-03）：`BoolBitArrayOfArg`（`Game`/`Level:GetStateFlag(int Flag)`）
    //: 也要一个**整数**实参（标志号），而且和 `U64FlagsAllSet` 一样有"合不合法"的判据
    //: （两位的那条用同一个 `IsIntegerArgument`）。`BoolBitWrite` 仍旧**只闸个数不闸类型**。
    const bool wantsFlagIndexArgument = row->kind == FieldKind::BoolBitArrayOfArg;
    //: 批次 300（2026-10-03）：`BoolBitArrayOfWriteArg`（`Game`/`Level:SetStateFlag(Flag, Value)`）
    //: 收**两个**实参（整数标志号 + 位值）⇒ 栈上恰好 3 个值。标志号那条仍按整数闸
    //: （与两个读侧 kind 同一个 `IsIntegerArgument`）；位值按 Lua 真值语义取（同 `BoolBitWrite`）。
    const bool wantsBitArrayWriteArguments = row->kind == FieldKind::BoolBitArrayOfWriteArg;
    //: 批次 301（2026-10-03）：`U32OrWithArg`（`EntityPlayer:AddCacheFlags(CacheFlag)`）也收
    //: **一个整数**实参（要 OR 进去的掩码），与 `U64FlagsAllSet` 同一个 `IsIntegerArgument` 闸
    //: （PC 的绑定同样要求整数：`mov eax, [ebp+0x8]` 直接当掩码用）。
    const bool wantsOrMaskArgument = row->kind == FieldKind::U32OrWithArg;
    //: 批次 302（2026-10-03）：`ColorModWrite`（`Room:SetFloorColor` / `SetWallColor`）收的是
    //: **一个 `Color` 句柄**（userdata）—— 整数闸不能套用（`IsIntegerArgument` 会把 `Color`
    //: 判成不合法），所以它单开一支：只要那一格取得到 `Color` 句柄就放行。
    const bool wantsColorModArgument = row->kind == FieldKind::ColorModWrite;
    //: 批次 333（2026-10-03）：`FloatMultiplyArg`（`Entity:MultiplyFriction(Value)`）收**一个数值**
    //: 实参 —— 它**不套整数闸**（`Value` 是 float：模组传 `1.2` 是常态，`IsIntegerArgument` 会把它判成不合法），
    //: 改用 `lua_isnumber`（与 PC 的绑定本体一致：`movss xmm0,[ebp+0x8]` 直接当浮点用）。
    //: ★ 批次 341（2026-10-04）：`FloatFromArg`（`EntityLaser:SetMaxDistance(Distance)`）同一条口径
    //:   —— 也是"一个 float 实参、不套整数闸"（PC 绑定同为 `movss xmm0,[ebp+0x8]`）。
    const bool wantsNumberArgument =
        row->kind == FieldKind::FloatMultiplyArg || row->kind == FieldKind::FloatFromArg;
    //: 批次 342（2026-10-04）：`FloatThenIntFromArgs`（`Game:Darken(Darkness, Timeout)`）收
    //: **两个**实参 —— 第 1 格是**数值**（写给一个 `float` 字段）、第 2 格是**整数**（写给一个 `i32` 字段）。
    //: 所以它既不是"一个数值"那一档、也不是"两个整数"那一档，单开一支。
    const bool wantsFloatThenIntArguments = row->kind == FieldKind::FloatThenIntFromArgs;
    //: 栈上应有的值个数：只收接收者 = 1；收一个实参 = 2；收两个实参 = 3。
    const int expectedArgumentCount = (wantsBitArrayWriteArguments || wantsFloatThenIntArguments)
                                          ? 3
                                          : (wantsIntegerArgument || wantsBitWriteArgument ||
                                             wantsFlagIndexArgument || wantsOrMaskArgument ||
                                             wantsColorModArgument || wantsNumberArgument)
                                                ? 2
                                                : 1;
    //: 参数校验拆成"先个数、再类型"两段（批次 342 重构）：原来那串嵌套三元表达式在加了
    //: 「一个数值 + 一个整数」这一档之后已经读不清了，而**判据没有变**（逐支与原实现等价）。
    bool argumentsValid = lua_gettop(state) == expectedArgumentCount;
    if (argumentsValid) {
        if (wantsColorModArgument) {
            argumentsValid = luaL_testudata(state, 2, LuaRuntime::kColorMetatable) != nullptr;
        } else if (wantsFloatThenIntArguments) {
            //: 第 1 格**不套整数闸**（`0.5` 必须放行）；第 2 格套（PC 的 `Timeout` 是 int）。
            argumentsValid = lua_isnumber(state, 2) != 0 &&
                             isaac::runtime::IsIntegerArgument(state, 3);
        } else if (wantsNumberArgument) {
            argumentsValid = lua_isnumber(state, 2) != 0;
        } else if (wantsIntegerArgument || wantsFlagIndexArgument || wantsBitArrayWriteArguments ||
                   wantsOrMaskArgument) {
            argumentsValid = isaac::runtime::IsIntegerArgument(state, 2);
        }
    }
    if (!argumentsValid) {
        // 消息按 catalog 里的 `owner:name` 现拼，与手写处理器逐字一致
        // （例如 `"EntityPlayer:GetSoulHearts accepts no arguments"`）。只在出错路径上拼。
        const LuaApiDescriptor* descriptor = ApiCatalog::Default().Find(row->id);
        const char* owner = descriptor != nullptr ? descriptor->owner : "?";
        const char* name = descriptor != nullptr ? descriptor->name : "?";
        if (wantsBitArrayWriteArguments) {
            return luaL_error(state, "%s:%s expects an integer flag and a value", owner, name);
        }
        if (wantsFloatThenIntArguments) {
            return luaL_error(state, "%s:%s expects one number argument and one integer argument",
                              owner, name);
        }
        if (wantsColorModArgument) {
            return luaL_error(state, "%s:%s expects a Color", owner, name);
        }
        if (wantsNumberArgument) {
            return luaL_error(state, "%s:%s expects one number argument", owner, name);
        }
        if (wantsIntegerArgument || wantsFlagIndexArgument || wantsOrMaskArgument) {
            return luaL_error(state, "%s:%s expects one integer argument", owner, name);
        }
        if (wantsBitWriteArgument) {
            return luaL_error(state, "%s:%s expects one argument", owner, name);
        }
        return luaL_error(state, "%s:%s accepts no arguments", owner, name);
    }
    // 掩码 / 待写入的位值只在需要时取（其余 kind 不读第 2 个参数，取 0 也不影响）。
    // ★ 批次 301：`U32OrWithArg`（`AddCacheFlags`）要的就是这一份"整数掩码"⇒ 与
    //   `U64FlagsAllSet` 共用同一次取值（同一条 `IsIntegerArgument` 闸已经放行过）。
    const std::uint64_t flagMask =
        (wantsIntegerArgument || wantsOrMaskArgument)
            ? static_cast<std::uint64_t>(
                  static_cast<std::int64_t>(lua_tointegerx(state, 2, nullptr)))
            : 0;
    //: 批次 333：`FloatMultiplyArg` 的实参按**数值**取（`lua_tonumber` —— 与 PC 绑定本体的
    //: `movss xmm0, [ebp+0x8]` 同一口径：那一格本来就是个 `float`）。
    const float numericArgument =
        (wantsNumberArgument || wantsFloatThenIntArguments)
            ? static_cast<float>(lua_tonumber(state, 2))
            : 0.0F;
    //: 批次 342：`FloatThenIntFromArgs` 的**第 2 个实参**（整数，写给 `offset2` 那一格）。
    //: 与 `flagMask` 同一口径：取低 32 位（PC 的 `Darken` 把 `Timeout` 当 `int` 存）。
    const std::uint32_t secondIntegerArgument =
        wantsFloatThenIntArguments
            ? static_cast<std::uint32_t>(
                  static_cast<std::int64_t>(lua_tointegerx(state, 3, nullptr)))
            : 0U;
    // ★ `BoolBitWrite` 的实参**按 Lua 真值语义**取（`lua_toboolean`：只有 `false` / `nil`
    //   算假）—— 这正是 PC 那边的口径：绑定函数本体（`0x497800`）做的是
    //   `cmp byte ptr [ebp+0x8], 0; cmove`，那个字节由胶水层的布尔转换填进来，
    //   于是 `SetClear(false)` 清位、`SetClear(true)` 置位、而 **`SetClear(0)` 也是置位**
    //   （0 在 Lua 里为真）。写成"必须 LUA_TBOOLEAN 才放行"会比 PC 更严 ⇒ 会拒掉
    //   PC 上本来能用的写法。
    const bool bitWriteValue = wantsBitWriteArgument ? (lua_toboolean(state, 2) != 0) : false;
    //: 批次 297：`BoolBitArrayOfArg` 的实参（标志号）只在需要时取；负数走"读不到"降级。
    const std::int64_t flagIndex =
        (wantsFlagIndexArgument || wantsBitArrayWriteArguments)
            ? static_cast<std::int64_t>(lua_tointegerx(state, 2, nullptr))
            : 0;
    //: 位值（第 3 个实参）同样按 Lua 真值语义取 —— 与 `BoolBitWrite` 同一口径
    //: （PC 的胶水层也是这么转的：`SetStateFlag(..., 0)` 在 Lua 里为真 ⇒ 置位）。
    const bool bitArrayWriteValue =
        wantsBitArrayWriteArguments ? (lua_toboolean(state, 3) != 0) : false;
    const std::uintptr_t receiver = ResolveFieldReceipt(state, row->receipt, 1);
    if (receiver == 0) {
        // ★ 批次 301：返回 0 个值的 kind（三条写侧）在这里也返回 0 个值 —— 见 `RowReturnsNoValues`。
        if (RowReturnsNoValues(row->kind)) {
            return 0;
        }
        PushMissingFieldValueForRow(state, row);
        return 1;
    }
    switch (row->kind) {
        case FieldKind::I32: {
            std::int32_t value = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushinteger(state, static_cast<lua_Integer>(value));
            return 1;
        }
        case FieldKind::Bool: {
            std::uint8_t value = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushboolean(state, value != 0 ? 1 : 0);
            return 1;
        }
        case FieldKind::Sum2U32: {
            std::uint32_t first = 0;
            std::uint32_t second = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &first, &IsEngineMemoryReadable, 0) ||
                !engine_memory::ReadField(receiver, row->offset2, &second, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushinteger(state, static_cast<lua_Integer>(first + second));
            return 1;
        }
        case FieldKind::BoolEquals: {
            // `offset2` 在这里是"要比较的常量"（例如 `ITEM_TRINKET`），不是第二个偏移。
            std::uint32_t value = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushboolean(state, value == row->offset2 ? 1 : 0);
            return 1;
        }
        case FieldKind::VectorCount: {
            // `offset`/`offset2` 是一对 `T*`（begin/end），元素数是 `(end - begin) / sizeof(T)`。
            std::uintptr_t begin = 0;
            std::uintptr_t end = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &begin, &IsEngineMemoryReadable, 0) ||
                !engine_memory::ReadField(receiver, row->offset2, &end, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            // 空容器在引擎里就是 `begin == end`；`end < begin` 或跨度离谱说明内存不可信，
            // 一律按"读不到"降级 —— 编一个巨大数字会让 Mod 走进错误分支。
            if (end < begin) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            const std::uintptr_t span = end - begin;
            const std::uintptr_t stride = sizeof(std::uint32_t);
            if (span / stride > kFieldVectorCountMaximum) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushinteger(state, static_cast<lua_Integer>(span / stride));
            return 1;
        }
        case FieldKind::BoolNonZero: {
            // 读一个 `u32`，"非零即真"。`Level:IsAltStage()` 就是这一条：
            // PC 契约（`Level.md`）= "StageType 不是 STAGETYPE_ORIGINAL(0)"。
            std::uint32_t value = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushboolean(state, value != 0 ? 1 : 0);
            return 1;
        }
        case FieldKind::U64FlagsAllSet: {
            // `Entity:HasEntityFlags(Flags)`：读 `Entity + 0x1B8` 的 **64 位**实体标志字，
            // 判"实参点到的位**全都**置着"。
            //
            // PC 契约原文（`tools/pc_contract_docs/Entity.md:425/427`）：
            //   `#### boolean HasEntityFlags ( int Flags )`
            //   "Returns true if the entity has **all** named EntityFlags set."
            // ⇒ 判据必须是 `(字段 & 实参) == 实参`。写成 `!= 0`（"任意一位命中"）会让
            //   `HasEntityFlags(FLAG_FRIENDLY)` 对"友方 + 别的一堆位"之外的情况也答真，
            //   而 MCM 拿它当"这是不是友方"用（`modconfig.lua:207`）⇒ 会把该报的危险房间报成安全。
            std::uint64_t flags = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &flags, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushboolean(state, (flags & flagMask) == flagMask ? 1 : 0);
            return 1;
        }
        case FieldKind::SumU32Array: {
            // `offset`/`offset2` 是一对 `u32[]` 的 begin/end，把每一格**相加**。
            //
            // 为什么是求和而不是"数非零格子"：这张数组是"**按收藏品 id 的计数**"，
            // 而 PC 侧另有一条 `EntityPlayer:GetCollectibleNum(id)`（按 id 数）——
            // 本项目的 `GetCollectibleNum` 读的就是同一张数组的第 id 格。
            // 既然"按 id 的数量"已经有独立 API，`GetCollectibleCount()` 就应当是**总件数**。
            // 真机证据（2026-09-16）：D6（id 105）= 1、其余为 0 ⇒ 求和 = 1、非零格子也 = 1，
            // 两种口径在这个场景下同值；口径的选择依据是上面那条 PC 契约，不是这个数值。
            std::uintptr_t begin = 0;
            std::uintptr_t end = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &begin, &IsEngineMemoryReadable, 0) ||
                !engine_memory::ReadField(receiver, row->offset2, &end, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            if (begin == 0 || end < begin || ((end - begin) % sizeof(std::uint32_t)) != 0 ||
                (end - begin) / sizeof(std::uint32_t) > kFieldVectorCountMaximum) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            std::uint64_t total = 0;
            for (std::uintptr_t address = begin; address < end; address += sizeof(std::uint32_t)) {
                std::uint32_t value = 0;
                if (!engine_memory::ReadAt(address, &value, &IsEngineMemoryReadable)) {
                    PushMissingFieldValue(state, row->missing);
                    return 1;
                }
                total += value;
            }
            lua_pushinteger(state, static_cast<lua_Integer>(total));
            return 1;
        }
        case FieldKind::Vector2Pair: {
            // `offset`(X) / `offset2`(Y) 是同一个 `Vector2` 的两半，各 4 字节 float。
            // 两个分量**分别**判可读：只读到一半就返回"X 对、Y 是 0"的点，比整体降级更隐蔽。
            float x = 0.0F;
            float y = 0.0F;
            if (!engine_memory::ReadField(receiver, row->offset, &x, &IsEngineMemoryReadable, 0) ||
                !engine_memory::ReadField(receiver, row->offset2, &y, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValueForRow(state, row);
                return 1;
            }
            isaac::runtime::PushLuaVector(state, x, y);
            return 1;
        }
        case FieldKind::BoolBit: {
            // 批次 291（2026-10-02）：读一个 `u32` 位掩码，**单独测 `offset2` 那一位**。
            // 这一支的两个使用者是同一个字段（`RoomDescriptor.Flags`）的不同位：
            //   `Room:IsAmbushDone()` = bit3（`CHALLENGE_DONE`）、
            //   `Room:HasWaterPits()` = bit5（`HAS_WATER`）。
            // PC 侧的依据是那两条绑定函数本体里的 `shr eax,N` + `and al,1`
            // （`0x6DCE00` / `0x4F3EC0`），Switch 侧的具名消费者见 `runtime_constants.hpp`。
            //
            // ★ 不能拿 `BoolNonZero` 凑：这一格的低位（bit0 已清、bit1 压板、bit2 献祭…）
            //   在多数时刻是置着的 ⇒ "非零即真"会让 `IsAmbushDone()` 恒答 true。
            // ★ 位号越界（`offset2 >= 32`）不是"读不到"，是**表写错了** ⇒ 按读不到降级，
            //   不静默按 `& 0` 处理（那会恒答 false，与"表写错"这件事一样难查，但至少降级
            //   路径有记账）。
            std::uint32_t value = 0;
            if (row->offset2 >= 32 ||
                !engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushboolean(state, (value & (static_cast<std::uint32_t>(1) << row->offset2)) != 0 ? 1 : 0);
            return 1;
        }
        case FieldKind::BoolBitWrite: {
            // 批次 292（2026-10-02）：读改写一个 `u32` 位掩码的某一位，位值来自实参。
            // 唯一使用者 `Room:SetClear(boolean Clear)`：描述符 `Flags` 的 **bit0**
            // （PC 的 `0x497800` 就是 `and eax,-2` / `or ecx,1` / `cmove` 那套）。
            //
            // ★ 用 `WriteField`（先过 `IsEngineMemoryWritable` 再落值）而不是直接解引用：
            //   写错地址是"静默破坏别人的内存"（随机崩溃 / 存档损坏且事后无从归因），
            //   所以与 `Game`/`Entity`/`Sprite` 那几处写入口**同一形态**。
            // ★ 读不到 / 位号越界 ⇒ **什么都不写、也不抛错**（返回 0 个值）：PC 上不存在
            //   "写失败"这回事，而"报错摘掉整条模组回调"比"这次没生效"严重得多（批 250 定案）。
            // ★ 返回值：**0 个**（PC 返回 `void`）—— 本机制里第一条不返回值的 kind。
            if (row->offset2 >= 32) {
                return 0;
            }
            std::uint32_t value = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable, 0)) {
                return 0;
            }
            const std::uint32_t mask = static_cast<std::uint32_t>(1) << row->offset2;
            const std::uint32_t updated = bitWriteValue ? (value | mask) : (value & ~mask);
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, updated,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::BoolBitArrayOfArg: {
            // 批次 297（2026-10-03）：按**实参**（标志号）去位数组里取一位。
            // 两个使用者：`Game:GetStateFlag(int Flag)`（`Game+0x26FA50`，`offset2` = 1 ⇒
            // 每字节 8 个标志）与 `Level:GetStateFlag(int Flag)`（`Level+0x215F0` 的 `u64`，
            // `offset2` = 8 ⇒ 每 64 位 64 个标志）。取证见 `runtime_constants.hpp` 的批次 297 段。
            //
            // ★ 越界（`n < 0` 或超过"64 个元素"的护栏）按**读不到**降级：PC 那两条绑定
            //   **没有任何边界检查**（负数会右移出巨大下标、PC 自己读飞），我们不去读一个
            //   可能落在别的字段上的地址 —— 这与字段行既有的"降级不抛错"口径一致。
            // ★ `offset2` 不是 1/4/8 ⇒ 是**表写错了**，按读不到降级（与 `BoolBit` 的位号越界同处置）。
            const std::uint32_t width = row->offset2;
            const std::uint64_t bitsPerElement = 8ULL * width;
            const bool shapeKnown = (width == 1 || width == 4 || width == 8);
            if (shapeKnown && flagIndex >= 0 &&
                static_cast<std::uint64_t>(flagIndex) <
                    bitsPerElement * kFieldBitArrayMaximumElements) {
                const std::uint64_t element = static_cast<std::uint64_t>(flagIndex) / bitsPerElement;
                const std::uint64_t bit = static_cast<std::uint64_t>(flagIndex) % bitsPerElement;
                const std::uintptr_t address =
                    receiver + row->offset + static_cast<std::uintptr_t>(element) * width;
                std::uint64_t value = 0;
                bool readable = false;
                if (width == 8) {
                    readable = engine_memory::ReadAt(address, &value, &IsEngineMemoryReadable);
                } else if (width == 4) {
                    std::uint32_t narrow = 0;
                    readable = engine_memory::ReadAt(address, &narrow, &IsEngineMemoryReadable);
                    value = narrow;
                } else {
                    std::uint8_t narrow = 0;
                    readable = engine_memory::ReadAt(address, &narrow, &IsEngineMemoryReadable);
                    value = narrow;
                }
                if (readable) {
                    lua_pushboolean(state, ((value >> bit) & 1ULL) != 0 ? 1 : 0);
                    return 1;
                }
            }
            PushMissingFieldValue(state, row->missing);
            return 1;
        }
        case FieldKind::BoolBitArrayOfWriteArg: {
            // 批次 300（2026-10-03）：按**实参**给的标志号去位数组里**读改写那一位**。
            // 两个使用者：`Game:SetStateFlag(int Flag, boolean Value)`（`offset2` = 1 ⇒
            // 每字节 8 个标志）与 `Level:SetStateFlag(int Flag, boolean Value)`（`offset2` = 8 ⇒
            // 每 64 位 64 个标志）—— 与 297 那两个**读**侧是同一对数组，取证见
            // `runtime_constants.hpp` 的批次 297 段；PC 侧四条绑定（读/写 × Game/Level）也落在这两格上。
            //
            // ★ 写侧**一律走 `WriteAt`**（先过 `IsEngineMemoryWritable`）：写错地址是"静默破坏
            //   别人的内存"（随机崩溃 / 存档损坏且事后无从归因），比读错严重得多 ——
            //   与 `BoolBitWrite` / `SetClear` 同一形态（批次 250/292 定案）。
            // ★ 越界 / 表写错 ⇒ **什么都不写、也不抛错、返回 0 个值**：PC 那两条绑定同样没有
            //   边界检查，而"这次没生效"远好过"写飞"。
            const std::uint32_t width = row->offset2;
            const std::uint64_t bitsPerElement = 8ULL * width;
            const bool shapeKnown = (width == 1 || width == 4 || width == 8);
            if (shapeKnown && flagIndex >= 0 &&
                static_cast<std::uint64_t>(flagIndex) <
                    bitsPerElement * kFieldBitArrayMaximumElements) {
                const std::uint64_t element = static_cast<std::uint64_t>(flagIndex) / bitsPerElement;
                const std::uint64_t bit = static_cast<std::uint64_t>(flagIndex) % bitsPerElement;
                const std::uintptr_t address =
                    receiver + row->offset + static_cast<std::uintptr_t>(element) * width;
                std::uint64_t value = 0;
                bool readable = false;
                if (width == 8) {
                    readable = engine_memory::ReadAt(address, &value, &IsEngineMemoryReadable);
                } else if (width == 4) {
                    std::uint32_t narrow = 0;
                    readable = engine_memory::ReadAt(address, &narrow, &IsEngineMemoryReadable);
                    value = narrow;
                } else {
                    std::uint8_t narrow = 0;
                    readable = engine_memory::ReadAt(address, &narrow, &IsEngineMemoryReadable);
                    value = narrow;
                }
                if (readable) {
                    const std::uint64_t mask = 1ULL << bit;
                    const std::uint64_t updated =
                        bitArrayWriteValue ? (value | mask) : (value & ~mask);
                    if (width == 8) {
                        static_cast<void>(engine_memory::WriteAt(
                            address, updated, &IsEngineMemoryWritable));
                    } else if (width == 4) {
                        static_cast<void>(engine_memory::WriteAt(
                            address, static_cast<std::uint32_t>(updated & 0xFFFFFFFFULL),
                            &IsEngineMemoryWritable));
                    } else {
                        static_cast<void>(engine_memory::WriteAt(
                            address, static_cast<std::uint8_t>(updated & 0xFFULL),
                            &IsEngineMemoryWritable));
                    }
                }
            }
            return 0;
        }
        case FieldKind::U32OrWithArg: {
            // 批次 301（2026-10-03）：读改写一个 `u32` —— `字段 |= 实参`，返回 **0 个**值。
            // 唯一使用者 `EntityPlayer:AddCacheFlags(CacheFlag)`：`Entity_Player + 0x1958`
            // 的 `_cacheFlags`（PC 的绑定本体 `0x427800` 就是
            // `or dword ptr [ecx+0x14b8], eax`；取证见 `runtime_constants.hpp` 批次 301 段）。
            //
            // ★ 写侧一律走 `WriteField`（先过 `IsEngineMemoryWritable` 再落值）：写错地址是
            //   "静默破坏别人的内存"（随机崩溃 / 存档损坏且事后无从归因），比读错严重得多
            //   —— 与 `BoolBitWrite` / `BoolBitArrayOfWriteArg` 同一形态（批 250/292/300 定案）。
            // ★ 读不到 / 接收者解析不到 ⇒ **什么都不写、也不抛错**（返回 0 个值）：PC 上不存在
            //   "写失败"这回事，而"报错摘掉整条模组回调"比"这次没生效"严重得多。
            // ★ 只做"或"、不做别的：`AddCacheFlags` 的契约是"把这些位置上"，既有位**不许被清** ——
            //   用例专门在同一个字里摆别的位来抓"整格覆盖写"这类错法。
            std::uint32_t value = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable, 0)) {
                return 0;
            }
            const std::uint32_t updated =
                value | static_cast<std::uint32_t>(flagMask & 0xFFFFFFFFULL);
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, updated,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::FloatMultiplyArg: {
            // 批次 333（2026-10-03）：读改写一个 `float` —— `字段 *= 实参`，返回 **0 个**值。
            // 唯一使用者 `Entity:MultiplyFriction(float Value)`：`Entity + 0x340`（**本帧的工作摩擦**）。
            // PC 的绑定本体（`0x5951D0`）逐字：`movss xmm0,[ebp+0x8]` → `mulss xmm0,[ecx+0x2c4]`
            // → `movss [ecx+0x2c4],xmm0` → `ret 4`；契约 `Entity.md:510` 只有签名没有散文
            // ⇒ 语义由绑定本体定。
            //
            // ★★ **为什么是 `+0x340` 而不是它旁边那格 `+0x33C`**（两格是一对"原值 / 本帧值"）：
            //   ① `Entity::Update @ 0x6026C` 读 `+0x340` 喂给 `TimeScaledFriction(friction, dt)`、
            //      再把结果**乘进速度向量**（`+0x334`）⇒ 它才是"生效的那一格"；
            //   ② 同一函数 `0x6015C` 写 `+0x340 = [+0x33C] × 0.95f`（**摩擦衰减**）；
            //   ③ `Entity::Init @ 0x59860/0x59898` 把 `+0x33C` 拷进 `+0x340` ⇒ `+0x33C` 是原值；
            //   ④ ★ **语料是每帧调用**（`IsaacOnTwitchReloaded/scripts/events.lua:850` 在
            //      `onUpdate` 里 `p:MultiplyFriction(1.2)`）—— 乘**原值**会逐帧指数级累积，
            //      乘本帧值才是模组要的效果。⇒ 取 `+0x340`。
            //   取证细节见 `runtime_constants.hpp` 批次 333 段与布局表 `entity.json` 的 `Friction` 行。
            //
            // ★ 写侧一律走 `WriteField`（先过 `IsEngineMemoryWritable` 再落值）—— 与
            //   `U32OrWithArg`/`BoolBitWrite` 同一形态（批 250/292/301 定案）：写错地址是
            //   "静默破坏别人的内存"，比读错严重得多。
            // ★ 读不到 / 接收者解析不到 ⇒ **什么都不写、也不抛错**（返回 0 个值）。
            // ★ `u32 ↔ float` 的位转换用 `std::memcpy`（`reinterpret_cast` 在严格别名规则下是 UB）。
            std::uint32_t raw = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &raw, &IsEngineMemoryReadable, 0)) {
                return 0;
            }
            float value = 0.0F;
            std::memcpy(&value, &raw, sizeof(value));
            value *= numericArgument;
            std::uint32_t updated = 0;
            std::memcpy(&updated, &value, sizeof(updated));
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, updated,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::FloatFromArg: {
            // 批次 341（2026-10-04）：把一个 **`float` 字段**赋成**实参给的数值**、返回 **0 个**值。
            // 唯一使用者 `EntityLaser:SetMaxDistance(float Distance)`：PC 的绑定本体（`0x4275B0`）就是
            // `movss xmm0,[ebp+8]` + `movss [ecx+0x420],xmm0` + `ret 4`
            // ⇒ **赋值**（不是 `FloatMultiplyArg` 的 `*=`）。
            //
            // ★ 与 `FloatMultiplyArg` 正好是同一个 `float` 字段的两种写侧：
            //   那条读改写（`字段 *= 实参`）、这条直接赋值（`字段 = 实参`）。
            //   ★ 为什么**不能**用 `U32FromArg` 顶：那条写的是**整数**的 32 位
            //     （Lua `40` → `0x28`），而本格要的是 `40.0f` 的位型 `0x42200000`。
            // ★ 写侧一律走 `WriteField`（先过 `IsEngineMemoryWritable` 再落值）—— 与
            //   `U32OrWithArg` / `FloatMultiplyArg` 同一形态（批 250/292/301/333 定案）：
            //   写错地址是"静默破坏别人的内存"，比读错严重得多。
            // ★ 接收者解析不到 ⇒ **什么都不写、也不抛错**（返回 0 个值）；
            //   参数**个数与类型**在进 `switch` 之前已经闸过（`wantsNumberArgument`）。
            // ★ `float ↔ u32` 的位转换用 `std::memcpy`（`reinterpret_cast` 在严格别名规则下是 UB）。
            std::uint32_t bits = 0;
            std::memcpy(&bits, &numericArgument, sizeof(bits));
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, bits,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::FloatThenIntFromArgs: {
            // 批次 342（2026-10-04）：把**两个实参分别写进两个字段** —— 数值 → `offset`（float）、
            // 整数 → `offset2`（i32）。唯一使用者 `Game:Darken(float Darkness, int Timeout)`：
            // PC 的绑定本体（`0x432F60`）就是「把两个形参各存进一个成员」。
            // ★ 两格**不相邻**（Switch 上中间夹着 `0x24F9BC` 那个插值量）⇒ 必须两个独立偏移，
            //   不能用一条 `u64`/`u32` 掩盖（那会静默写坏中间那一格）。
            // ★ 写侧一律走 `WriteField`（先过 `IsEngineMemoryWritable`）—— 与同族写侧 kind 同形态。
            // ★ 读不到 / 判不出可写 / 接收者解析不到 ⇒ **什么都不写、也不抛错**（返回 0 个值）；
            //   参数**个数与类型**在进 `switch` 之前已经闸过（`wantsFloatThenIntArguments`）。
            // ★ `float ↔ u32` 的位转换用 `std::memcpy`（严格别名规则）。
            std::uint32_t floatBits = 0;
            std::memcpy(&floatBits, &numericArgument, sizeof(floatBits));
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, floatBits,
                                                        &IsEngineMemoryWritable, 0));
            static_cast<void>(engine_memory::WriteField(receiver, row->offset2,
                                                        secondIntegerArgument,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::TwoByteConstZero: {
            // 批次 342（2026-10-04）：把 `offset` 与 `offset2` **两格各写 1 字节常量 `0`**、
            // 返回 **0 个**值。唯一使用者 `EntityPlayer:StopExtraAnimation()`：
            // PC 的绑定本体（`0x57B1D0`）就是「把两个相隔 2 的字节都清 0」
            // （PC 那两格是 `+0x12E8` / `+0x12EA`，中间的 `0x12E9` **明确跳过**）。
            //
            // ★★ 为什么**必须逐字节写两格**、不许"往第一格写一个 `u16 = 0`"：
            //   那会**连带清掉中间那一字节**，而 PC 跳过它 ⇒ 与 PC 不一致
            //   （且那一格的用途在本镜像里未取证）。★ 这一条在用例里由
            //   「中间的 `+0x1711` 预置 `0xAB`、调完仍是 `0xAB`」钉住。
            // ★ 写侧走 `WriteField`（先过 `IsEngineMemoryWritable`）；写不进去 ⇒ 什么都不写、不抛错。
            const std::uint8_t zero = 0;
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, zero,
                                                        &IsEngineMemoryWritable, 0));
            static_cast<void>(engine_memory::WriteField(receiver, row->offset2, zero,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::ColorModRead: {
            // 批次 343（2026-10-04）：读 `offset` 处那 **44 字节 `ColorMod`**，
            // 压回一个 Lua `Color` 句柄（`kColorMetatable`）。唯一使用者 `Entity:GetColor()`
            // （PC 绑定 `0x4F3DE0` = `lea eax,[ecx+0xE4]; ret` ⇒ **按值返回**一个 `Color`）。
            //
            // ★ 映射只复用 `PushLuaColorFromEngineColorMod`（`engine_color_mod.hpp`，
            //   与 `FillEngineColorMod` 同住一份）——**不许**在这里再抄一遍对应关系。
            // ★ 一次读满 44 字节（`ReadField` 是按 `sizeof(T)` 取值的模板 ⇒ 传指针即整段读，
            //   可读性判定也是整段做的）。
            // ★ 读不到 ⇒ 走 `PushMissingFieldValueForRow` 的**默认白**那一支（不报错、不压 nil）。
            isaac::runtime::EngineColorMod value{};
            if (!engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable,
                                          0)) {
                PushMissingFieldValueForRow(state, row);
                return 1;
            }
            isaac::runtime::PushLuaColorFromEngineColorMod(state, value);
            return 1;
        }
        case FieldKind::BoolWriteConst: {
            // 批次 305（2026-10-03）：往一个**1 字节**字段写**常量**布尔（常量在 `row->offset2`）。
            // 三个使用者：`MusicManager:Disable()`（`offset2` = 0）、`Enable()`（= 1）——
            // PC 的绑定本体各只有一条 `mov byte ptr [ecx+0x328], 0/1`（**不收参数**）。
            // ★ 这一支**不进参数闸**（只收接收者，走默认的 `expectedArgumentCount == 1`）。
            // ★ 写侧走 `WriteField`（受保护写原语）；写不进去 ⇒ 什么都不写、也不抛错、返回 0 个值。
            // ★ `offset2` 不是 0/1 ⇒ 是**表写错了**：这里按"非 0 即 1"规范化（**不静默写别的字节值**），
            //   并把这一点写在这里，免得后人以为可以拿它当通用字节写。
            const std::uint8_t value = row->offset2 == 0 ? 0 : 1;
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, value,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::ColorModWrite: {
            // 批次 302（2026-10-03）：把实参（`Color` 句柄）转成 44 字节 `ColorMod` 整块写进 `字段`。
            // 两个使用者：`Room:SetFloorColor`（`Room + 0x7968`）与 `Room:SetWallColor`（`Room + 0x7994`）。
            // PC 的绑定本体就是"把 44 字节的实参整块拷到成员上"（`0x7A7ED0` / `0x7A7F10`，
            // `ret 0x2c`）⇒ 没有别的副作用；取证与"两格各喂给谁"见 `runtime_constants.hpp` 批次 302 段。
            //
            // ★ 映射只复用 `FillEngineColorMod`（`engine_color_mod.hpp`，批次 271 起是唯一一份）——
            //   本 kind **不许**再抄一遍"Color → ColorMod"。
            // ★ 写侧走 `WriteField`（44 字节整段过 `IsEngineMemoryWritable`）：写错地址是
            //   "静默破坏别人的内存"（与 `BoolBitWrite` / `U32OrWithArg` 同一形态）。
            // ★ 取不到 `Color` 句柄 / 判不出可写 ⇒ **什么都不写、也不抛错、返回 0 个值**。
            //   （参数**个数**与**类型**在进 `switch` 之前已经闸过 ⇒ 这里的失败只剩"内存不可写"。）
            EngineColorMod value{};
            if (!FillEngineColorMod(state, 2, &value)) {
                return 0;
            }
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, value,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::U32FromArg: {
            // 批次 308（2026-10-03）：往一个 **4 字节 u32** 字段写**实参给的整数**、返回 **0 个**值。
            // 唯一使用者 `GridEntity:SetType(eGridEntityType)`：PC 的绑定本体（`0x6DAD50`）就是
            // `mov eax,[ebp+8]` + `mov [ecx+0x4],eax` + `ret 0x4` —— **两条指令、不调引擎函数**。
            //
            // ★ 与 `BoolWriteConst`（写常量）正好是"写什么"的两个方向：那条的常量住在行里
            //   （`offset2`）、这条的值由调用方给。
            // ★ 只取**低 32 位**：PC 的 `mov [ecx+0x4],eax` 是 32 位存储 ⇒ 传 64 位的值
            //   等于传它的低半（与 `U32OrWithArg` 同一口径）。
            // ★ 写侧走 `WriteField`（先过 `IsEngineMemoryWritable`）：写错地址是"静默破坏别人的
            //   内存"，比读错严重得多（与 `BoolWriteConst` / `ColorModWrite` 同一形态）。
            // ★ 判不出可写 ⇒ **什么都不写、也不抛错、返回 0 个值**（PC 的返回类型就是 `void`）。
            const std::uint32_t value = static_cast<std::uint32_t>(flagMask & 0xFFFFFFFFULL);
            static_cast<void>(engine_memory::WriteField(receiver, row->offset, value,
                                                        &IsEngineMemoryWritable, 0));
            return 0;
        }
        case FieldKind::RngSnapshot: {
            // 批次 316（2026-10-03）：把 `offset` 处的 **16 字节 `RNG` 对象**读成快照、压一个
            // `kRngMetatable` 句柄。唯一使用者 `Entity:GetDropRNG()`（PC 绑定 `0x412390` =
            // `lea eax,[ecx+0x334]; ret` —— 原样返回实体内嵌那个 RNG 的地址，不查表不调函数）。
            //
            // ★ 与手写的 `GridEntity:GetRNG` / 四条 `EntityPlayer:Get*RNG` **逐句同形**
            //   （同一段 push 路径：`lua_newuserdata` → 整段 `LoadVerifiedAt` → 挂元表）。
            // ★ 存活判据分两步，与那几条一致：先 `receiver + offset` 不溢出，再按**整段
            //   `kRngObjectSize`** 问一次可读性 ⇒ 随后的整段拷贝不必逐字节再问（L1 `LoadVerifiedAt`）。
            // ★ 读不到 / 接收者无效 ⇒ 按 `missing` 降级（本批 `Nil`），**不抛错** ——
            //   与 PC 上"拿不到对象"同值，且不会把模组整条回调摘掉。
            const std::uintptr_t address = receiver + row->offset;
            if (receiver > UINTPTR_MAX - row->offset ||
                !IsEngineMemoryReadable(address, kRngObjectSize)) {
                PushMissingFieldValueForRow(state, row);
                return 1;
            }
            auto* rng = static_cast<LuaRuntime::RngHandle*>(
                lua_newuserdata(state, sizeof(LuaRuntime::RngHandle)));
            *rng = {};
            rng->resolver = ResolveEntityRngReference;
            rng->owner = receiver;
            rng->offset = row->offset;
            luaL_getmetatable(state, LuaRuntime::kRngMetatable);
            lua_setmetatable(state, -2);
            return 1;
        }
        case FieldKind::U32:
        default: {
            std::uint32_t value = 0;
            if (!engine_memory::ReadField(receiver, row->offset, &value, &IsEngineMemoryReadable, 0)) {
                PushMissingFieldValue(state, row->missing);
                return 1;
            }
            lua_pushinteger(state, static_cast<lua_Integer>(value));
            return 1;
        }
    }
}

// 引擎实体存活判据的导出实现（声明与理由见 `isaac_api.hpp`）：就是 `ValidatedEntity` 用的那一条，
// 不另写一份 —— `sprite_api.cpp` 的引擎实体 `Sprite` 句柄每次访问都要重新问一次。
bool IsLiveEntityPointer(std::uintptr_t candidate) noexcept {
    return IsEntityPointer(candidate);
}

// 批次 298：网格实体存活判据的导出实现（声明与理由见 `isaac_api.hpp`）。
// 与 `IsEntityPointer` 同形（先读 vptr 再比区间，比较前不解引用），只是区间换成
// `GridEntity` 家族的（见 `runtime_constants.hpp` 的批次 298 段：18 个具名 vtable 夹出）。
bool IsLiveGridEntityPointer(std::uintptr_t candidate) noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (candidate == 0 || base == 0) {
        return false;
    }
    std::uintptr_t vtable = 0;
    if (!ReadEngine(candidate, &vtable)) {
        return false;
    }
    if (base > UINTPTR_MAX - kGridEntityVtableRangeEndOffset) {
        return false;
    }
    return vtable >= base + kGridEntityVtableRangeBeginOffset &&
           vtable < base + kGridEntityVtableRangeEndOffset;
}

// 批次 304（2026-10-03）：从栈上取"网格实体句柄"里的引擎指针。
// ★ **判据只有这一份**：`remaining_api.cpp` 的 `GridEntityArgument`（手写处理器用）现在转发到这里，
//   `FieldReceipt::GridEntity`（数据行的接收者）也用它 —— 之前前者是"两张元表各测一次"的唯一一份，
//   数据行要用就得再抄一遍（本项目点名的"第二份判据"风险）。
// 接受两张元表：`GridEntity`（`GridEntityHandle`）与 `GridEntityDoor`（`DoorHandle`，
// 门多记一个自己的槽位 ⇒ 另一个结构体）。
void* GridEntityHandleArgument(lua_State* state, int index) noexcept {
    if (state == nullptr) {
        return nullptr;
    }
    if (void* raw = luaL_testudata(state, index, LuaRuntime::kGridEntityMetatable)) {
        return static_cast<LuaRuntime::GridEntityHandle*>(raw)->entity;
    }
    if (void* raw = luaL_testudata(state, index, LuaRuntime::kGridEntityDoorMetatable)) {
        return static_cast<LuaRuntime::DoorHandle*>(raw)->entity;
    }
    return nullptr;
}

void* CheckGridEntityHandle(lua_State* state, int index) {
    void* handle = GridEntityHandleArgument(state, index);
    if (handle == nullptr) {
        // 与 `CheckEntityHandle` 同口径：**参数类型写错了**就报错（PC 也会），而"底层指针已失效"
        // 才走降级（由调用方拿 `IsLiveGridEntityPointer` 判）。
        luaL_error(state, "expected a GridEntity (got %s)", luaL_typename(state, index));
    }
    return handle;
}

// 批次 065：`ReadEntityIdentity` 的导出实现（声明与理由见 `isaac_api.hpp`）。
bool ReadEntitySubType(std::uintptr_t entity, std::uint32_t* subtype) noexcept {
    return entity != 0 && subtype != nullptr && ReadEngine(entity + kEntitySubTypeOffset, subtype);
}

bool ReadEntityIdentity(std::uintptr_t entity, std::uint32_t* type,
                        std::uint32_t* variant) noexcept {
    if (entity == 0 || type == nullptr || variant == nullptr) {
        return false;
    }
    return ReadEngine(entity + kEntityTypeOffset, type) &&
           ReadEngine(entity + kEntityVariantOffset, variant);
}

// 批次 104：`RoomConfig::Entry` 的前三个字段。宽度按 `runtime_constants.hpp` 里那三行常量上方
// 记的证据（`Type` i32、`Variant`/`SubType` **i16**）—— 用 i16 读是刻意的：按 i32 读会把相邻的
// 两个字段拼成一个数（EID 拿变体/子类型去建索引，拼错的数会让它查错东西、还不报错）。
std::uint32_t EngineFrameCountNow() noexcept {
    const std::uintptr_t game = ResolveGameAddress();   // 与 `Game:GetFrameCount` 同一条解析链
    if (game == 0) {
        return 0;
    }
    std::uint32_t frames = 0;
    if (!ReadEngine(game + kGameFrameCountOffset, &frames)) {
        return 0;
    }
    return frames;
}

bool ReadRoomConfigEntryFields(std::uintptr_t entry, std::int32_t* type, std::int32_t* variant,
                               std::int32_t* subType) noexcept {
    if (entry == 0 || type == nullptr || variant == nullptr || subType == nullptr) {
        return false;
    }
    std::uint32_t rawType = 0;
    std::uint16_t rawVariant = 0;
    std::uint16_t rawSubType = 0;
    if (!ReadEngine(entry + kRoomConfigEntryTypeOffset, &rawType) ||
        !ReadEngine(entry + kRoomConfigEntryVariantOffset, &rawVariant) ||
        !ReadEngine(entry + kRoomConfigEntrySubTypeOffset, &rawSubType)) {
        return false;
    }
    *type = static_cast<std::int32_t>(rawType);
    *variant = static_cast<std::int32_t>(rawVariant);
    *subType = static_cast<std::int32_t>(rawSubType);
    return true;
}

// 批次 396（2026-10-07）：`MC_EVALUATE_CACHE` 的入口中继要自己读这张掩码（见头文件说明）。
bool ReadEntityPlayerCacheFlags(std::uintptr_t player, std::uint32_t* cacheFlags) noexcept {
    if (player == 0 || cacheFlags == nullptr) {
        return false;
    }
    std::uint32_t mask = 0;
    if (!ReadEngine(player + kEntityPlayerCacheFlagsOffset, &mask)) {
        return false;
    }
    *cacheFlags = mask;
    return true;
}


// `Entity:TakeDamage(Damage, DamageFlags, Source, CountdownFrames)`（批次 065）。
//
// **为什么手写而不是数据行**：签名里同时有 `float`、一个 **`EntityRef` 句柄**（按引用交给引擎）
// 与"按接收者种类选入口"这一步；数据行那套形状只覆盖"整数参数 + 标量返回"，硬塞会变成猜。
//
// **引擎侧**：`Entity::TakeDamage(float, EntityRef const&, int)` @ `0x5DCA4`，
// 玩家另有 `Entity_Player::TakeDamage(...)` @ `0x2A34D0`。PC 里它是虚函数，我们按"接收者是不是
// 玩家"二选一：玩家走玩家重载（血量/无敌帧/动画那一套都在这儿），其余走基类。
// **已知偏离**：非玩家子类自己的重载不会被执行（NPC/拾取物等），它们行为与基类一致的部分不受影响。
//
// ★★ 2026-09-19 修正（批次 071 的真机崩溃把这一条钉死了）：**`flags` 一直是引擎的第二个参数**。
//
// 批次 064 当时按"引擎只有 `(float, EntityRef const&, int)`"实现，于是既**忽略 flags**、
// 又按 3 个形参调用 —— 而真实签名（`tools/engine_symbol_signatures.json` 里本来就有，
// 真机崩溃报告的 mangled name 也逐字一致）是：
//
//   Entity::TakeDamage(float, unsigned long, Entity::EntityRef const&, int)
//   Entity_Player::TakeDamage(float, unsigned long, Entity::EntityRef const&, int)
//
// 后果分两步暴露，正好是一堂 ABI 课：
//   ① 批次 065~070：参数个数判据写错（要求栈深度 4）⇒ 真机上**每次调用都报错**，
//      引擎这一步根本没走到，所以"少一个参数"这件事被掩盖了；
//   ② 批次 071 修好判据之后，调用真的进了引擎 ⇒ 引擎按 `x2 = &EntityRef` 解引用，
//      而我们传进去的 `x2` 是 `countdown`（= 0）⇒ **空指针解引用，游戏直接 Data Abort**。
//      `dist/crash-20260919/01789813541_010021c000b6a000.log`：`Address: 0`、
//      PC = `Entity_Player::TakeDamage + 0x148`、X[24] = 该函数入口。
//
// 现在按真实签名调用：`(this, float damage, uint64 flags, const EntityRef* ref, int countdown)`。
int EntityTakeDamage(lua_State* state) {
    const auto* handle = CheckEntityHandle(state, 1);
    // ★ 批次 071 修正（真机 + 宿主双重暴露）：PC 的调用是
    // `entity:TakeDamage(damage, flags, source, countdown)` —— **冒号调用会把 `self` 也压进栈**，
    // 所以栈上是 **5** 个值。批次 065 这里写的是 `lua_gettop(state) != 4`，于是真机上
    // **每一次调用都直接报错**（GoodTrip `trip.lua:70` 的诅咒房过路费走不到引擎那一步），
    // 而且错误会把整条 `MC_POST_RENDER` 回调摘掉；更糟的是它在宿主上**没有任何用例覆盖**
    // （065 那批一条测试都没调用过这条 API），所以一路带到了卡上。
    // 现在的判据按"**参数个数**"而不是"栈深度"来写：`self` + 3 或 4 个实参（`countdown` 可省，
    // 与 PC 默认值 0 等价）。错误文本里带上实际拿到的个数 —— 下一次真机读数一眼就能看出来。
    const int stackTop = lua_gettop(state);
    if ((stackTop != 4 && stackTop != 5) || !lua_isnumber(state, 2) ||
        !IsIntegerArgument(state, 3) || (stackTop == 5 && !IsIntegerArgument(state, 5))) {
        return luaL_error(
            state,
            "Entity:TakeDamage expects (damage, flags, source, countdown); got %d argument(s)",
            stackTop - 1);
    }
    const std::uintptr_t entity = ValidatedEntity(handle);
    if (entity == 0) {
        lua_pushboolean(state, false);
        return 1;
    }
    // 引用：PC 的 `Source` 可以是 `EntityRef(...)`；`nil` 时给一个**全零的引用**
    // （= "没有来源"），这与 PC 的语义一致，而且引擎对空源实体有判空分支。
    static std::uint8_t emptyReference[kEntityRefStorageSize] = {};
    const void* reference = EntityRefBufferAt(state, 4);
    if (reference == nullptr) {
        if (!lua_isnoneornil(state, 4)) {
            return luaL_error(state, "Entity:TakeDamage expects an EntityRef as its third argument");
        }
        reference = emptyReference;
    }
    // `countdown`（PC 的 `CountdownFrames`）：省略时按 PC 的默认值 0 处理。
    const std::int32_t countdown =
        stackTop == 5 ? static_cast<std::int32_t>(lua_tointeger(state, 5)) : 0;
    // `flags`（PC 的 `DamageFlags`）：`unsigned long` —— PC 传进来的那个位掩码**原样交给引擎**
    // （`DAMAGE_CURSED_DOOR | DAMAGE_NO_PENALTIES` 这类语义由引擎自己解释，我们不再吞掉它）。
    const std::uint64_t flags =
        static_cast<std::uint64_t>(static_cast<std::int64_t>(lua_tointeger(state, 3)));
    // PC绑定0x8604E9经MSVC槽8虚调；NS全部实体经Itanium槽9（析构多一格）。
    // 复用现有基类句柄校验，再核动态槽目标及实际入口，不把NPC伤害误送基类实现。
    const std::uintptr_t base = EngineModuleBase();
    std::uintptr_t vtable = 0, method = 0;
    bool callable = base != 0 && ReadEngine(entity, &vtable) &&
                    vtable <= UINTPTR_MAX - 9 * sizeof(std::uintptr_t) &&
                    ReadEngine(vtable + 9 * sizeof(std::uintptr_t), &method);
    if (callable && method == base + kEntityTakeDamageOffset) {
        callable = VerifiedHookedEngineEntry(method, kEntityTakeDamageExpectedBytes,
            EntryRelayInstalled(HookId::EntityTakeDamage),
            EntryRelayFallbackEntry(HookId::EntityTakeDamage), &IsEngineMemoryReadable);
    } else if (callable && method == base + kEntityPlayerTakeDamageOffset) {
        callable = VerifiedHookedEngineEntry(method, kEntityPlayerTakeDamageExpectedBytes,
            EntryRelayInstalled(HookId::EntityPlayerTakeDamage),
            EntryRelayFallbackEntry(HookId::EntityPlayerTakeDamage), &IsEngineMemoryReadable);
    } else if (callable && method == base + kEntityPickupTakeDamageOffset) {
        callable = VerifiedHookedEngineEntry(method, kEntityPickupTakeDamageExpectedBytes,
            EntryRelayInstalled(HookId::EntityPickupTakeDamage),
            EntryRelayFallbackEntry(HookId::EntityPickupTakeDamage), &IsEngineMemoryReadable);
    } else if (callable && method == base + kEntitySlotTakeDamageOffset) {
        callable = VerifiedHookedEngineEntry(method, kEntitySlotTakeDamageExpectedBytes,
            EntryRelayInstalled(HookId::EntitySlotTakeDamage),
            EntryRelayFallbackEntry(HookId::EntitySlotTakeDamage), &IsEngineMemoryReadable);
    } else if (callable) {
        struct Guard { std::uintptr_t offset; std::uint32_t word; };
        // 固定NRO导出及_ZTV的ABS64核定；其余两个重载未安装入口中继。
        constexpr Guard guards[] = {{0x122224, 0xD10203FF}, {0xD8550, 0xD10203FF}};
        callable = false;
        for (const auto& guard : guards) {
            std::uint32_t word = 0;
            if (base <= UINTPTR_MAX - guard.offset && method == base + guard.offset &&
                ReadEngine(method, &word) && word == guard.word) {
                callable = true;
                break;
            }
        }
    }
    if (!callable) {
        lua_pushboolean(state, false);
        return 1;
    }
    std::uint64_t integers[8] = {entity, flags, AddressBitsForEngineArgument(reference),
                               static_cast<std::uint64_t>(static_cast<std::int64_t>(countdown))};
    double floats[8] = {EngineFloatArgument(lua_tonumber(state, 2))};
    std::uint64_t returned = 0;
    double ignored = 0;
    EngineCallTrampoline(method, integers, floats, &returned, &ignored);
    lua_pushboolean(state, (returned & 0xFFU) != 0);
    return 1;
}

// ---- 批次 328（2026-10-03）：`EntityPlayer:GetShootingInput()` / `GetShootingJoystick()` --------
//
// 两条 API 在 **PC 上共用同一份实现**（两个名字表项指向同一个 VA `0x741B00`，各跑一次
// `tools/pc_exe_binding.py` 即可复现）⇒ 我们这里也是同一段代码的两张门面
// （只有报错消息里的名字不同）。逐条证据见 `runtime_constants.hpp` 的批次 328 段。
//
// ★★★ 为什么**手写**而不是数据行：引擎返回 `KAGE::Math::Vector2`（两个 `float` 的 **HFA**，
//   按 AAPCS64 走 `s0`/`s1`），而通用跳板 `engine_call_trampoline.s` 只把 `x0` 与 `d0`
//   回填给调用方 ⇒ **机制内表达不了**。照 `Room:GetCenterPos()` 的先例，用一个"返回两个 float
//   的结构体"的函数指针类型，让编译器生成正确的 HFA 约定（`Room:GetCenterPos` 就是这么做的）。
//
// ★ 降级 = **压 `Vector(0, 0)`、不报错**（与 `Room:GetCenterPos` 同一口径）：报错会把整条模组
//   回调摘掉；压 `nil` 会让模组紧接着 `p:GetShootingInput().X` 抛 "attempt to index a nil value"
//   —— 同样是摘回调。答 `(0,0)` 只让那一次方向算成零。
struct EngineVector2Abi {
    float x;
    float y;
};
static_assert(sizeof(EngineVector2Abi)==8 && alignof(EngineVector2Abi)==alignof(float));
static_assert(offsetof(EngineVector2Abi,x)==0 && offsetof(EngineVector2Abi,y)==4);
static_assert(std::is_standard_layout_v<EngineVector2Abi> && std::is_trivially_copyable_v<EngineVector2Abi> &&
              std::is_aggregate_v<EngineVector2Abi> &&
              std::is_same_v<decltype(EngineVector2Abi::x),float> &&
              std::is_same_v<decltype(EngineVector2Abi::y),float>);
// 两float HFA返回在s0/s1；x1是8B临时值的引用，不使用x8间接返回或仅d0的通用跳板。
using EntityFamiliarGetOrbitPositionFn = EngineVector2Abi (*)(std::uintptr_t,const EngineVector2Abi*);

std::uintptr_t EntityPlayerShootingInputMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityPlayerGetShootingInputOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityPlayerGetShootingInputOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

//: 两条 API 的共同实现。`api` 只用于报错消息（PC 上两条就是同一份，我们保持一致）。
int EntityPlayerShootingInputCommon(lua_State* state, const char* api) {
    //: ★ 方法调用 ⇒ 栈上**恰好一个**值（`self`）。多给/少给都报错（PC 侧同样只收 0 个实参）。
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "%s accepts no arguments", api);
    }
    auto* handle = CheckEntityHandle(state, 1);
    //: 接收者必须是**精确的 `Entity_Player`**（与 `ValidatedEntityPlayer` 的既有判据同一份）——
    //: 拿一张眼泪/掉落物去调它虽不越界，但"调的是别人的方法"。
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    const std::uintptr_t method = entity != 0 ? EntityPlayerShootingInputMethod() : 0;
    //: ★ 入口首 4 字节核对（与全族同口径）：对不上就**静默降级、绝不盲跳**。
    if (entity == 0 || method == 0 ||
        !EngineEntryWordMatches(method, kEntityPlayerGetShootingInputEntryWord)) {
        isaac::runtime::PushLuaVector(state, 0.0F, 0.0F);
        return 1;
    }
    using EntityPlayerGetShootingInputFn = EngineVector2Abi (*)(std::uintptr_t);
    const EngineVector2Abi value =
        isaac::runtime::engine_call::AsFunction<EntityPlayerGetShootingInputFn>(method)(entity);
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}

// `EntityPlayer:GetShootingInput()` —— PC 契约 `EntityPlayer.md:1235`：
// "Returns a vector that corresponds to the shooting inputs that this player is **pressing**."
int EntityPlayerGetShootingInput(lua_State* state) {
    return EntityPlayerShootingInputCommon(state, "EntityPlayer:GetShootingInput");
}

// `EntityPlayer:GetShootingJoystick()` —— PC 契约 `EntityPlayer.md:1245`：
// "Returns a vector that corresponds to the shooting inputs that this player is **holding**.
//  See the image for the [GetShootingInput](#getshootinginput) method."
// ★ 两个名字在 PC 上指向**同一个绑定函数** ⇒ 这里是同一段代码（不是"以为差不多"）。
int EntityPlayerGetShootingJoystick(lua_State* state) {
    return EntityPlayerShootingInputCommon(state, "EntityPlayer:GetShootingJoystick");
}

// `EntityPlayer:GetMovementJoystick()`（批次 332，2026-10-03）—— PC 契约 `EntityPlayer.md:1106`：
// `#### [Vector](Vector.md) GetMovementJoystick ( )`（无参、返回 `Vector`）。
//
// ★★ 与上面那两条**同型**，所以复用同一套：接收者精确判 `Entity_Player`、入口首 4 字节核对、
//    HFA 返回用 `EngineVector2Abi`、失败压 `Vector(0, 0)` 不报错。
//
// ★★★ **这一条的难点是"名字对不上"**：PC 侧那个方法的确认名字是 `GetMovementJoystick`，
//   而引擎里对应的函数叫 `get_movement_input`（**`joystick` vs `input`**）——
//   符号表里既没有 `get_movement_joystick`、也没有 `GetMovementJoystick`
//   （329 那套"归一化名兜底"同样搜不到，因为名字本身不同）。
//   **定案只能靠函数体**：把 PC 绑定（`0x741880`）与 Switch `get_movement_input`（`0x2B0D9C`）
//   的检查逐条对齐 —— 玩家类型 `0x14`/`0x1d`/`0x26`、父指针 `[ptr+0x28]==1`、
//   `ControlsEnabled`、`ControlsCooldown`、**动作号 `0x0b`(11)** 的 `IsActionPressed`、
//   以及"未按下时走 `GetActionValue(0/1/2)` 累加"——**七条一一对应**（详见 `runtime_constants.hpp`
//   批次 332 段的对照表）。⇒ 这不是"名字像"，是**同一段逻辑**。
std::uintptr_t EntityPlayerMovementJoystickMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityPlayerGetMovementJoystickOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityPlayerGetMovementJoystickOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

int EntityPlayerGetMovementJoystick(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:GetMovementJoystick accepts no arguments");
    }
    auto* handle = CheckEntityHandle(state, 1);
    const std::uintptr_t entity = ValidatedEntityPlayer(handle);
    const std::uintptr_t method = entity != 0 ? EntityPlayerMovementJoystickMethod() : 0;
    if (entity == 0 || method == 0 ||
        !EngineEntryWordMatches(method, kEntityPlayerGetMovementJoystickEntryWord)) {
        //: 与 328 那两条同一口径：**压 `Vector(0, 0)`、不报错**（模组紧接着就 `.X`/`.Y`）。
        isaac::runtime::PushLuaVector(state, 0.0F, 0.0F);
        return 1;
    }
    using EntityPlayerGetMovementJoystickFn = EngineVector2Abi (*)(std::uintptr_t);
    const EngineVector2Abi value =
        isaac::runtime::engine_call::AsFunction<EntityPlayerGetMovementJoystickFn>(method)(entity);
    isaac::runtime::PushLuaVector(state, value.x, value.y);
    return 1;
}

// `EntityPlayer:CheckFamiliar(...)`（批次 334，2026-10-03）—— PC 契约 `EntityPlayer.md:591`：
//   `void CheckFamiliar(FamiliarVariant, int TargetCount, RNG rng,
//                       ItemConfigItem SourceItemConfigItem = nil, int FamiliarSubType = -1)`
// ⇒ **后两个形参带缺省值**，所以 Lua 侧 3 / 4 / 5 个实参都合法（语料那 3 处**全是 3 参**）。
//
// ★★★ **为什么手写**：账目在 `runtime_constants.hpp` 批次 334 段 —— 数据行那条路缺两种表达能力
//   （"把 Lua 的 RNG 句柄当 `RNG&` 传"、"省略时填 `-1` 的整数"），各 ≈ `+0x480` 字节；
//   手写 ≈ 300 字节 ⇒ 手写更省（与 328/332 同一笔账）。⇒ 形状表**零增长**。
//
// ★ 接收者与 RNG 都用**现成**的两套判据（不另立）：
//   * `ValidatedEntityPlayer`（精确 `Entity_Player` vptr）—— 「读还是调」那条规矩要求的：
//     这条是**调用**，拿别的实体当 this 会顺着垃圾指针跑出去；
//   * `LuaRuntime::RngHandle::storage.data()` —— 与 `Level:QueryRoomTypeIndex` 第 3 参**同一件东西**
//     （Lua 侧的 RNG 句柄本身就是 16 字节引擎 RNG 对象的裸存储）⇒ 引擎推进的就是那颗真 RNG。
std::uintptr_t EntityPlayerCheckFamiliarMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityPlayerCheckFamiliarOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityPlayerCheckFamiliarOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

int EntityPlayerCheckFamiliar(lua_State* state) {
    const int top = lua_gettop(state);
    // 冒号调用 ⇒ 栈上第 1 个是 `self`，后面 2..4 个是实参（3 参写法最常见）。
    if (top < 4 || top > 6) {
        return luaL_error(
            state,
            "EntityPlayer:CheckFamiliar expects a familiar variant, a target count, an RNG and "
            "optionally an item config item and a sub type");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state, "EntityPlayer:CheckFamiliar expects an integer familiar variant");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 3)) {
        return luaL_error(state, "EntityPlayer:CheckFamiliar expects an integer target count");
    }
    // 第 3 个参数是**必需的** `RNG`（契约里它没有缺省值）⇒ 不是 RNG 就报错（模组写错了）。
    auto* rng = static_cast<LuaRuntime::RngHandle*>(
        luaL_testudata(state, 4, LuaRuntime::kRngMetatable));
    if (rng == nullptr) {
        return luaL_error(state, "EntityPlayer:CheckFamiliar expects an RNG");
    }
    const lua_Integer familiarVariant = lua_tointegerx(state, 2, nullptr);
    const lua_Integer targetCount = lua_tointegerx(state, 3, nullptr);
    // 第 4 个（可选）`SourceItemConfigItem`：PC 缺省 `nil` ⇒ 空指针。给了就按 `ItemConfig_Item`
    // 句柄取指针（复用字段那套 `ResolveFieldReceipt`，不另立一份判据）。
    std::uintptr_t sourceItem = 0;
    if (top >= 5 && !lua_isnoneornil(state, 5)) {
        sourceItem = ResolveFieldReceipt(state, FieldReceipt::ItemConfigItem, 5);
        if (sourceItem == 0) {
            return luaL_error(state, "EntityPlayer:CheckFamiliar expects an item config item");
        }
    }
    // 第 5 个（可选）`FamiliarSubType`：PC 缺省 `-1`（★★ **不是 0** —— 引擎拿符号位分支，
    // 见 `runtime_constants.hpp` 批次 334 段 ⇒ 省略时必须真的是 -1）。
    lua_Integer subType = -1;
    if (top >= 6) {
        if (!isaac::runtime::IsIntegerArgument(state, 6)) {
            return luaL_error(state, "EntityPlayer:CheckFamiliar expects an integer sub type");
        }
        subType = lua_tointegerx(state, 6, nullptr);
    }
    auto* handle = CheckEntityHandle(state, 1);
    const std::uintptr_t player = ValidatedEntityPlayer(handle);
    const std::uintptr_t method = player != 0 ? EntityPlayerCheckFamiliarMethod() : 0;
    //: 入口首 4 字节核对（与全族同口径）：对不上就**静默降级、绝不盲跳**。
    if (player == 0 || method == 0 ||
        !EngineEntryWordMatches(method, kEntityPlayerCheckFamiliarEntryWord)) {
        return 0;  //: 返回 `void` ⇒ 什么都不做（不压值、不报错）。
    }
    using CheckFamiliarFn = void (*)(std::uintptr_t, std::uint32_t, std::int32_t, void*,
                                     std::uintptr_t, std::int32_t);
    isaac::runtime::engine_call::AsFunction<CheckFamiliarFn>(method)(
        player, static_cast<std::uint32_t>(familiarVariant),
        static_cast<std::int32_t>(targetCount), ResolveRngObject(state, rng, true), sourceItem,
        static_cast<std::int32_t>(subType));
    return 0;
}

// ---- 批次 337（2026-10-04）：`EntityPlayer:FireTear(...)` ------------------------------------
//
// **为什么手写**：契约 7 个形参、引擎只有 5 个，缺两种表达能力（**按值的 HFA 形参** +
// **两个缺省为 `true` 的布尔**）⇒ 按 326 的校准要 ≈ `+0x900` 字节；手写 ≈ 300 字节。
// 逐条证据（引擎 5 格的寄存器/浮点映射、flags 低三位的语义、为什么 `Velocity` 是按值）
// 全在 `runtime_constants.hpp` 的批次 337 段。
std::uintptr_t EntityPlayerFireTearMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityPlayerFireTearOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityPlayerFireTearOffset;
    std::uintptr_t installedFallback = 0;
#if defined(__SWITCH__)
    installedFallback = EntryRelayFallbackEntry(HookId::FireTear);
#endif
    // 主动射击继续走公开入口，以保留61号回调；只接受完整原件或本运行时登记的中继。
    return VerifiedHookedEngineEntry(method, kEntityPlayerFireTearExpectedBytes,
        installedFallback != 0, installedFallback, &IsEngineMemoryReadable) ? method : 0;
}

int EntityPlayerFireTear(lua_State* state) {
    const int top = lua_gettop(state);
    // 冒号调用 ⇒ 栈上第 1 个是 `self`，后面 2..8 个是实参（契约里后 5 个都带缺省）。
    if (top < 3 || top > 8) {
        return luaL_error(state,
                          "EntityPlayer:FireTear expects a position, a velocity and optionally "
                          "three booleans, a source entity and a damage multiplier");
    }
    auto* position = TryVectorArgument(state,2);
    if (position == nullptr) {
        return luaL_error(state, "EntityPlayer:FireTear expects a position vector");
    }
    auto* velocity = TryVectorArgument(state,3);
    if (velocity == nullptr) {
        return luaL_error(state, "EntityPlayer:FireTear expects a velocity vector");
    }
    //: 三个布尔：**只按 Lua 真值语义取**（PC 侧同样接受任何真/假值）。
    //: ★ 缺省值是 `true`/`false`/`true`（契约逐字）⇒ 不能按"省略即 false"填。
    auto booleanAt = [state, top](int index, bool fallback) -> bool {
        if (top < index || lua_isnoneornil(state, index)) {
            return fallback;
        }
        return lua_toboolean(state, index) != 0;
    };
    const bool canBeEye = booleanAt(4, true);
    const bool noTractorBeam = booleanAt(5, false);
    const bool canTriggerStreakEnd = booleanAt(6, true);
    //: ★ 位序见 `runtime_constants.hpp` 批次 337 段：bit1 = `NoTractorBeam`（**已由
    //: `TEAR_TRACTOR_BEAM` 清位证明**），bit0/bit2 按契约形参顺序取。
    const std::uint32_t flags = (canBeEye ? 0x1U : 0U) | (noTractorBeam ? 0x2U : 0U) |
                                (canTriggerStreakEnd ? 0x4U : 0U);
    //: 第 6 个（可选）`Source`：PC 缺省 `nil` ⇒ 空指针。给了就按 `Entity` 句柄取指针
    //: （复用字段那套 `ResolveFieldReceipt`，与 `CheckFamiliar` 对 `ItemConfig_Item` 同一做法）。
    std::uintptr_t source = 0;
    if (top >= 7 && !lua_isnoneornil(state, 7)) {
        source = ResolveFieldReceipt(state, FieldReceipt::Entity, 7);
        if (source == 0) {
            return luaL_error(state, "EntityPlayer:FireTear expects a source entity");
        }
    }
    //: 第 7 个（可选）`DamageMultiplier`：缺省 **1**（不是 0）。
    double damageMultiplier = 1.0;
    if (top >= 8) {
        if (!lua_isnumber(state, 8)) {
            return luaL_error(state, "EntityPlayer:FireTear expects a number damage multiplier");
        }
        damageMultiplier = lua_tonumber(state, 8);
    }
    auto* handle = CheckEntityHandle(state, 1);
    const std::uintptr_t player = ValidatedEntityPlayer(handle);
    const std::uintptr_t method = player != 0 ? EntityPlayerFireTearMethod() : 0;
    //: 入口首 4 字节核对（与全族同口径）：对不上就**不调引擎、也报错**，压 `nil` 回去
    //: （契约返回 `EntityTear`，PC 上"射不出来"同样给 nil；报错会摘掉整条模组回调）。
    // 2026-10-18：原件/登记中继的完整校验已在Method完成，不再以旧首字拒绝已安装中继。
    if (player == 0 || method == 0) {
        lua_pushnil(state);
        return 1;
    }
    //: ★ `Position` 是 `Vector2 const&`（传指针 ⇒ 需要一个**调用期间有效**的槽，用局部量）；
    //: ★ `Velocity` 是**按值的 HFA**（两个 float ⇒ `s0`/`s1`）⇒ 直接按结构体传。
    //: ★ 返回 `Entity_Tear*` ⇒ 按实体句柄压回。
    const EngineVector2Abi positionSlot{position->x, position->y};
    const EngineVector2Abi velocityValue{velocity->x, velocity->y};
    using FireTearFn = void* (*)(std::uintptr_t, const EngineVector2Abi*, EngineVector2Abi,
                                 std::uint32_t, std::uintptr_t, float);
    void* tear = isaac::runtime::engine_call::AsFunction<FireTearFn>(method)(
        player, &positionSlot, velocityValue, flags, source,
        static_cast<float>(damageMultiplier));
    if (tear == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    const auto tearAddress = engine_memory::AddressOf(tear);
    if (!IsTypedEntity(tearAddress, kEntityTearVtableOffset, kEntityTypeTear)) {
        return luaL_error(state, "EntityPlayer:FireTear returned an unavailable EntityTear");
    }
    PushEntityHandle(state, tearAddress, kEntityTearMetatable);
    return 1;
}

// ---- 批次 345（2026-10-04）：`Isaac.Explode(pos, source, damage)` ------------------------------
//
// PC 契约 `tools/pc_contract_docs/Isaac.md:112`；真身 `Game::BombExplosionEffects @ 0x355C68`
// （入口首 4 字节 `0xD10443FF` = `sub sp,sp,#0x110`），mangled:
//   `_ZN15IsaacRepentance4Game20BombExplosionEffectsERKN4KAGE4Math7Vector2EfNS_11bitset128_tERKNS_8ColorModEPNS_6EntityEfbmb`
// ★★ **为什么必须手写**：9 个形参 ⇒ 第 9 格 `bool` **走栈**（`ldrb w21,[x29,#0x60]`），
//    通用跳板只填 `x0..x7`/`d0..d7`、**填不了栈**；且 `bitset128_t` 是 16 字节**按值**聚合体。
//    逐格 AAPCS64、末尾 4 格常量、bitset 全 0 的证据见
//    `docs/取证-L组-两条手写处理器的可执行规格-20261004d.md` §A（N 组独立复核通过）。
// ★ 与 `IsaacSpawn`（批次 340）同一条路：`AsFunction<Fn>` 让**编译器**按签名把最后一格放栈。

//: 16 字节、非浮点聚合体 ⇒ AAPCS64 走两个通用寄存器 `x2:x3`（不是 HFA 的 `d0..d3`）。
//: ★ 定义必须让「16 字节 + 整数成员」成立：若编译器把它当 HFA（走 `d0..d3`）会**静默错位**
//:   ⇒ 下面那条 `static_assert` 把尺寸钉住（真机再核「真的爆了」）。
namespace {
struct Bitset128 {
    std::uint64_t lo;
    std::uint64_t hi;
};
static_assert(sizeof(Bitset128) == 16, "bitset128_t 必须是 16 字节按值（走 x2:x3）");
}  // namespace

std::uintptr_t GameBombExplosionEffectsMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameBombExplosionEffectsOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kGameBombExplosionEffectsOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

int IsaacExplode(lua_State* state) {
    // `Isaac.Explode(...)` 是**点号全局调用**（栈上没有 `self`）⇒ 恰好 3 个实参。
    if (lua_gettop(state) != 3) {
        return luaL_error(state,
                          "Isaac:Explode expects a position, a source entity and a damage number");
    }
    auto* position = TryVectorArgument(state,1);
    if (position == nullptr) {
        return luaL_error(state, "Isaac:Explode expects a position vector");
    }
    //: `source`：PC 绑定把它直接当 `Entity*` 透传（`nil` ⇒ 空指针，**不校验**）；
    //: 非 nil 就必须是实体句柄（与批次 337 `FireTear` 对可选 `Source` 同一做法）。
    //: ★ 这里用**不抛错**的 `EntityPointerArgument`（而不是 `ResolveFieldReceipt`）：
    //:   后者内部的 `CheckEntityHandle` 对"根本不是实体句柄"会**直接报错**，报的是那句
    //:   长长的共享消息 `expected an Entity, EntityPlayer, EntityPickup, …`；
    //:   而 L 组规格 §A.4① 明确要求这一格报**带本 API 名字**的
    //:   `Isaac:Explode expects a source entity`（与批次 324 `ThrowSpider` 的 `Spawner`
    //:   同一条取舍，那里也是"可选实体参数" ⇒ 用不抛错出口）。
    //:   ★ 两处行为差别只在**报错措辞**：非实体一律 0 ⇒ 下面报本 API 的名字。
    std::uintptr_t source = 0;
    if (!lua_isnoneornil(state, 2)) {
        source = EntityPointerArgument(state, 2);
        if (source == 0) {
            return luaL_error(state, "Isaac:Explode expects a source entity");
        }
    }
    if (!lua_isnumber(state, 3)) {
        return luaL_error(state, "Isaac:Explode expects a number damage");
    }
    const float damage = static_cast<float>(lua_tonumber(state, 3));
    //: `Game*`：`Isaac.Explode` 没有接收者 ⇒ 走 `FieldReceipt::Level` 那条链
    //: （模块基址 → `g_Game` 全局槽 → `Game*`），与 `SpawnEntityCommon` 逐字相同。
    const std::uintptr_t game = ResolveFieldReceipt(state, FieldReceipt::Level, 0);
    const std::uintptr_t method = game != 0 ? GameBombExplosionEffectsMethod() : 0;
    //: 入口首 4 字节核对（与全族同口径）：对不上就**不调引擎、不报错、不压值**
    //: （PC 返回 `void`，因此「这次没生效」比「报错摘掉整条模组回调」更接近 PC）。
    if (game == 0 || method == 0 ||
        !EngineEntryWordMatches(method, kGameBombExplosionEffectsEntryWord)) {
        return 0;
    }
    //: `pos` 是 `Vector2 const&` ⇒ 传我们自己栈上那个槽的地址（调用期间有效）。
    const EngineVector2Abi positionSlot{position->x, position->y};
    //: `cm`（`ColorMod const&`）= PC 绑定的白值：tint=(1,1,1,1)、其余全 0（复用现成 44 字节类型）。
    const EngineColorMod white = DefaultEngineColorMod();
    //: `tearFlags` = PC 绑定逐字节给的**全 0**（16 字节）。引擎把它当掩码 & 全局眼泪标志用；
    //: 全 0 ⇒ 无特殊标志，与 PC 同（证据见 `runtime_constants.hpp` 批次 345 段）。
    const Bitset128 tearFlags{0, 0};
    //: ★★ 10 格签名：`x0..x7` + `s0/s1` 用满后，**第 9 格 `b2` 由编译器放栈**。
    using BombExplosionEffectsFn = void (*)(
        std::uintptr_t,           // x0  this = Game*
        const EngineVector2Abi*,  // x1  pos
        float,                    // s0  damage
        Bitset128,                // x2:x3 tearFlags（16B 按值）
        const EngineColorMod*,    // x4  cm（ColorMod const&）
        std::uintptr_t,           // x5  source（Entity*，可空）
        float,                    // s1  f
        bool,                     // w6  b
        unsigned long,            // x7  ul
        bool);                    // 栈  b2
    isaac::runtime::engine_call::AsFunction<BombExplosionEffectsFn>(method)(
        game, &positionSlot, damage, tearFlags, &white, source,
        /*f=*/1.0F, /*b=*/true, /*ul=*/4UL, /*b2=*/false);
    return 0;  //: 契约返回 `void` ⇒ 压 0 个值。
}

// ---- 批次 344（2026-10-04）：`EntityPlayer:AnimateCollectible(Collectible, AnimName?, SpriteAnimName?)`
//
// PC 契约 `tools/pc_contract_docs/EntityPlayer.md:435`。真身 = **改名**后的
// `Entity_Player::AnimatePickup(eCollectibleType, char const*, char const*) @ 0x2DD150`
// （入口首 4 字节 `0xD10743FF` = `sub sp,sp,#0x1d0`），mangled:
//   `_ZN15IsaacRepentance13Entity_Player13AnimatePickupENS_16eCollectibleTypeEPKcS3_`
// ★★ **为什么必须手写**：① 字符串实参（`EngineArgKind` 里没有这一档）；
//    ② 两个**非空字符串缺省**（`EngineCallShapeRow::optionalArgumentCount` 只表达"省略即 0"）。
// ★★★ **缺省必须传字面串**：引擎把它们喂 `ANM2::Play(char const*, bool)`，那里对名字做 `strcmp`、
//    对 null **无检查** ⇒ 传 `nullptr` 会读 NULL 段、当场崩（证据见
//    `docs/取证-L组-两条手写处理器的可执行规格-20261004d.md` §B.2 与 N 组复核）。
// ★ 负数 `CollectibleType` **不加工**（引擎入口 `0x2DD1D0 tbnz w23,#0x1f` 就是 PC 那条
//    "程序化道具"分支的对应物）—— 加工就与 PC 不一致。
std::uintptr_t EntityPlayerAnimateCollectibleMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityPlayerAnimateCollectibleOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityPlayerAnimateCollectibleOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

int EntityPlayerAnimateCollectible(lua_State* state) {
    const int top = lua_gettop(state);
    //: 冒号调用 ⇒ 栈上第 1 个是 self，后 1..3 个是实参（语料 1 参 / 3 参两种都要放行）。
    if (top < 2 || top > 4) {
        return luaL_error(
            state,
            "EntityPlayer:AnimateCollectible expects a collectible and optionally an animation "
            "name and a sprite animation name");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 2)) {
        return luaL_error(state,
                          "EntityPlayer:AnimateCollectible expects an integer collectible");
    }
    const lua_Integer collectible = lua_tointegerx(state, 2, nullptr);
    //: 两个字符串缺省值**逐字**照契约；★ 缺省必须传字面串（不能传 null，见上方注释）。
    //: `luaL_optstring` 一次覆盖「缺席 / `nil` ⇒ 缺省」「数字转串」「其余报错」三种行为，
    //: 与 PC 的 `luaL_optstring` 口径逐字同。
    const char* animName = luaL_optstring(state, 3, "Pickup");
    const char* spriteAnimName = luaL_optstring(state, 4, "PlayerPickupSparkle");
    auto* handle = CheckEntityHandle(state, 1);
    const std::uintptr_t player = ValidatedEntityPlayer(handle);
    const std::uintptr_t method = player != 0 ? EntityPlayerAnimateCollectibleMethod() : 0;
    //: 入口首 4 字节核对（与全族同口径）：对不上就**静默降级**（不调、不报错、不压值）。
    if (player == 0 || method == 0 ||
        !EngineEntryWordMatches(method, kEntityPlayerAnimateCollectibleEntryWord)) {
        return 0;  //: 契约返回 `void`。
    }
    using AnimateCollectibleFn = void (*)(std::uintptr_t, std::int32_t, const char*, const char*);
    isaac::runtime::engine_call::AsFunction<AnimateCollectibleFn>(method)(
        player, static_cast<std::int32_t>(collectible), animName, spriteAnimName);
    return 0;  //: 契约返回 `void`。
}

// ---- 批次 339（2026-10-04）：`EntityFamiliar:FireProjectile(Vector Dir)` ------------------------
//
// 引擎真身逐字存在（`Entity_Familiar::fire_projectiles(Vector2 const&, bool)` @ `0xB06FC`）
// ⇒ 转发即可；逐条 ABI 与"那个隐藏 bool 传什么"的证据见 `runtime_constants.hpp` 的批次 339 段。
std::uintptr_t EntityFamiliarFireProjectileMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityFamiliarFireProjectileOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityFamiliarFireProjectileOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

int EntityFamiliarFireProjectile(lua_State* state) {
    //: 冒号调用 ⇒ 栈上恰好两个值（`self` + `Dir`）。多给/少给都报错。
    if (lua_gettop(state) != 2) {
        return luaL_error(state, "EntityFamiliar:FireProjectile expects a direction vector");
    }
    auto* direction = TryVectorArgument(state,2);
    if (direction == nullptr) {
        return luaL_error(state, "EntityFamiliar:FireProjectile expects a direction vector");
    }
    auto* handle = CheckEntityHandle(state, 1);
    const std::uintptr_t familiar = ValidatedEntityFamiliar(handle);
    const std::uintptr_t method = familiar != 0 ? EntityFamiliarFireProjectileMethod() : 0;
    //: 入口首 4 字节核对（与全族同口径）：对不上就**不调引擎、不报错**，压 `nil` 回去
    //: （契约返回 `EntityTear`；PC 上射不出来时同样是 `nil`）。
    if (familiar == 0 || method == 0 ||
        !EngineEntryWordMatches(method, kEntityFamiliarFireProjectileEntryWord)) {
        lua_pushnil(state);
        return 1;
    }
    //: ★ `Dir` 是 `Vector2 const&` ⇒ 传**我们自己栈上那个槽的地址**（调用期间有效）。
    //: ★ 引擎那个隐藏的 `bool`：按契约散文与引擎自身的调用点取 `false`（证据见常量处注释）。
    const EngineVector2Abi directionSlot{direction->x, direction->y};
    using FireProjectileFn = void* (*)(std::uintptr_t, const EngineVector2Abi*, bool);
    void* tear = isaac::runtime::engine_call::AsFunction<FireProjectileFn>(method)(
        familiar, &directionSlot, false);
    if (tear == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    PushEntityHandle(state, engine_memory::AddressOf(tear), kEntityTearMetatable);
    return 1;
}

std::uintptr_t RequireFamiliarOrbitReceiver(lua_State* state,const char* name) {
    const auto familiar = ValidatedEntityFamiliar(CheckEntityHandle(state,1));
    if (familiar==0) {
        luaL_error(state,"EntityFamiliar:%s receiver is no longer available",name);
        return 0;
    }
    return familiar;
}
std::uintptr_t RequireFamiliarOrbitMethod(lua_State* state,const char* name,
    std::uintptr_t offset,const std::array<u8,16>& expected) {
    const auto method = EntityMethodByExpectedBytes(offset,expected);
    if (method==0) {
        luaL_error(state,"EntityFamiliar:%s native bindings are unavailable",name);
        return 0;
    }
    return method;
}
int EntityFamiliarGetOrbitPosition(lua_State* state) {
    const auto familiar = RequireFamiliarOrbitReceiver(state,"GetOrbitPosition");
    const auto* position = RequireVectorArgument(state,2);
    const auto method = RequireFamiliarOrbitMethod(state,"GetOrbitPosition",
        kEntityFamiliarGetOrbitPositionOffset,kEntityFamiliarGetOrbitPositionExpectedBytes);
    const EngineVector2Abi input{position->x,position->y};
    // NS正常层尾支也返回原Pos，且其它分支会改缓存/动画；必须运行原函数，不能按文档伪造零。
    const auto result = engine_call::AsFunction<EntityFamiliarGetOrbitPositionFn>(method)(familiar,&input);
    isaac::runtime::PushLuaVector(state,result.x,result.y);
    return 1;
}
int EntityFamiliarRecalculateOrbitOffset(lua_State* state) {
    const auto familiar = RequireFamiliarOrbitReceiver(state,"RecalculateOrbitOffset");
    // 固定PC Lua thunk84BF60：lua_toboolean第3格，Layer checkinteger后取int低32，signed返回。
    const bool add = lua_toboolean(state,3)!=0;
    const auto layer = static_cast<std::int32_t>(static_cast<std::uint32_t>(luaL_checkinteger(state,2)));
    const auto method = RequireFamiliarOrbitMethod(state,"RecalculateOrbitOffset",
        kEntityFamiliarRecalculateOrbitOffsetOffset,kEntityFamiliarRecalculateOrbitOffsetExpectedBytes);
    using EntityFamiliarRecalculateOrbitOffsetFn = std::int32_t (*)(std::uintptr_t,std::int32_t,bool);
    const auto result = engine_call::AsFunction<EntityFamiliarRecalculateOrbitOffsetFn>(method)(familiar,layer,add);
    lua_pushinteger(state,result);
    return 1;
}
int EntityFamiliarAddToOrbit(lua_State* state) {
    const auto familiar = RequireFamiliarOrbitReceiver(state,"AddToOrbit");
    const auto layer = static_cast<std::int32_t>(static_cast<std::uint32_t>(luaL_checkinteger(state,2)));
    const auto method = RequireFamiliarOrbitMethod(state,"AddToOrbit",
        kEntityFamiliarAddToOrbitOffset,kEntityFamiliarAddToOrbitExpectedBytes);
    using EntityFamiliarAddToOrbitFn = void (*)(std::uintptr_t,std::int32_t);
    engine_call::AsFunction<EntityFamiliarAddToOrbitFn>(method)(familiar,layer);
    return 0;
}
int EntityFamiliarRemoveFromOrbit(lua_State* state) {
    const auto familiar = RequireFamiliarOrbitReceiver(state,"RemoveFromOrbit");
    const auto method = RequireFamiliarOrbitMethod(state,"RemoveFromOrbit",
        kEntityFamiliarRemoveFromOrbitOffset,kEntityFamiliarRemoveFromOrbitExpectedBytes);
    using EntityFamiliarRemoveFromOrbitFn = void (*)(std::uintptr_t);
    engine_call::AsFunction<EntityFamiliarRemoveFromOrbitFn>(method)(familiar);
    return 0;
}

// ---- 批次 340（2026-10-04）：`Game:Spawn(...)` / `Isaac.Spawn(...)` ---------------------------
//
// 共同实现：把 `(type, variant, &pos, &vel, spawner, subType, seed)` 转发给
// `Game::SpawnEx`（真身 `0x3540D0`）。逐条 ABI 与"为什么必须手写"见 `runtime_constants.hpp`
// 的批次 340 段（★ 第 8 个形参**走栈**，跳板填不了 ⇒ 数据行那条路不通）。
std::uintptr_t GameSpawnExMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameSpawnExOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kGameSpawnExOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

int SpawnEntityCommon(lua_State* state, std::int32_t type, std::int32_t variant,
                      VectorHandle* position, VectorHandle* velocity, std::uintptr_t spawner,
                      std::int32_t subType, std::int32_t seed) {
    const std::uintptr_t game = ResolveFieldReceipt(state, FieldReceipt::Level, 0);
    const std::uintptr_t method = game != 0 ? GameSpawnExMethod() : 0;
    std::uintptr_t installedFallback = 0;
#if defined(__SWITCH__)
    installedFallback = EntryRelayFallbackEntry(HookId::GameSpawnEx);
#endif
    // 原入口或已经登记的中继都可调用；完整指纹不符仍拒绝。
    if (game == 0 || method == 0 ||
        !EngineEntryOrRelayMatches<IsEngineMemoryReadable>(method, kGameSpawnExExpectedBytes.data(),
            kGameSpawnExExpectedBytes.size(), installedFallback)) {
        lua_pushnil(state);
        return 1;
    }
    //: 两个 `Vector` 都是 `Vector2 const&` ⇒ 传我们自己栈上那两个槽的地址。
    const EngineVector2Abi positionSlot{position->x, position->y};
    const EngineVector2Abi velocitySlot{velocity->x, velocity->y};
    //: ★ 9 格 = `this` + 8 个形参：`x0`/`w1`..`w7` 七格进寄存器，**第 8 个形参由编译器放栈**。
    using SpawnExFn = void* (*)(std::uintptr_t, std::int32_t, std::int32_t,
                                const EngineVector2Abi*, const EngineVector2Abi*, std::uintptr_t,
                                std::int32_t, std::int32_t, std::int32_t);
    void* entity = isaac::runtime::engine_call::AsFunction<SpawnExFn>(method)(
        game, type, variant, &positionSlot, &velocitySlot, spawner, subType, seed,
        /*forceSpawn=*/0);
    if (entity == nullptr) {
        lua_pushnil(state);
        return 1;
    }
    PushEntityHandle(state, engine_memory::AddressOf(entity),
                     EntityViewMetatableForPointer(engine_memory::AddressOf(entity)));
    return 1;
}

//: 读两个 `Vector` 实参（不合法就报错；报错消息带 API 名）。
bool SpawnVectorsAt(lua_State* state, const char* api, int positionIndex, int velocityIndex,
                    VectorHandle** position, VectorHandle** velocity) {
    *position = TryVectorArgument(state,positionIndex);
    *velocity = TryVectorArgument(state,velocityIndex);
    if (*position == nullptr || *velocity == nullptr) {
        luaL_error(state,
                   "%s expects a position vector and a velocity vector "
                   "(and optionally a spawner, a sub type and a seed)",
                   api);
        return false;
    }
    return true;
}

int GameSpawn(lua_State* state) {
    //: 契约 `Game.md:520` 的 7 个形参都**没有**缺省值 ⇒ 冒号调用时栈上恰好 8 个值。
    if (lua_gettop(state) != 8) {
        return luaL_error(state,
                          "Game:Spawn expects a type, a variant, a position, a velocity, a spawner, "
                          "a sub type and a seed");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 2) ||
        !isaac::runtime::IsIntegerArgument(state, 3)) {
        return luaL_error(state, "Game:Spawn expects an entity type and an integer variant");
    }
    VectorHandle* position = nullptr;
    VectorHandle* velocity = nullptr;
    if (!SpawnVectorsAt(state, "Game:Spawn", 4, 5, &position, &velocity)) {
        return 0;
    }
    const std::uintptr_t spawner = EntityPointerArgument(state, 6);
    if (!isaac::runtime::IsIntegerArgument(state, 7) ||
        !isaac::runtime::IsIntegerArgument(state, 8)) {
        return luaL_error(state, "Game:Spawn expects an integer sub type and an integer seed");
    }
    return SpawnEntityCommon(state,
                             static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr)),
                             static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr)), position,
                             velocity, spawner,
                             static_cast<std::int32_t>(lua_tointegerx(state, 7, nullptr)),
                             static_cast<std::int32_t>(lua_tointegerx(state, 8, nullptr)));
}

int IsaacSpawn(lua_State* state) {
    //: 全局函数（点号调用）⇒ 栈上恰好 6 个值；契约 `Isaac.md:621` 也没有缺省值。
    if (lua_gettop(state) != 6) {
        return luaL_error(state,
                          "Isaac.Spawn expects an entity type, a variant, a sub type, a position, "
                          "a velocity and a spawner");
    }
    if (!isaac::runtime::IsIntegerArgument(state, 1) ||
        !isaac::runtime::IsIntegerArgument(state, 2) ||
        !isaac::runtime::IsIntegerArgument(state, 3)) {
        return luaL_error(state,
                          "Isaac.Spawn expects an entity type, an integer variant and an integer "
                          "sub type");
    }
    //: ★ **形参序与引擎不同**：Lua 是 `(type, variant, subtype, pos, vel, spawner)`，
    //: 引擎是 `(type, variant, pos, vel, spawner, subtype, seed)` ⇒ 这里把 subtype 从第 3 位
    //: 挪到第 6 位。
    VectorHandle* position = nullptr;
    VectorHandle* velocity = nullptr;
    if (!SpawnVectorsAt(state, "Isaac.Spawn", 4, 5, &position, &velocity)) {
        return 0;
    }
    const std::uintptr_t spawner = EntityPointerArgument(state, 6);
    //: ★ 种子：契约明文「`Isaac.Spawn()` … spawns an entity with a random seed」，
    //: 并警告**种子 0 会让游戏崩** ⇒ 取引擎自己的 `RandomU32()`，**为 0 时兜底成 1**。
    std::int32_t seed = static_cast<std::int32_t>(isaac::runtime::EngineRandomU32());
    if (seed == 0) {
        seed = 1;
    }
    return SpawnEntityCommon(state,
                             static_cast<std::int32_t>(lua_tointegerx(state, 1, nullptr)),
                             static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr)), position,
                             velocity, spawner,
                             static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr)), seed);
}

// ---- 批次 271（2026-10-02）：`needs_new_receiver` 桶头部三条 ---------------------------------//
// 三条的来路都一样：**引擎里有同名方法**（用嵌套名解析器扫过全符号表：`SetColor` / `AddCharmed`
// 只在 `Entity`、`UseActiveItem` 只在 `Entity_Player`，**没有子类重写**）⇒ 不需要像 `TakeDamage`
// 那样在"基类 / 子类"之间二选一。三条的入口 16 字节原文都在 `runtime_constants.hpp`，
// 由下面的取址助手逐字节核对；对不上就**静默降级**，绝不盲跳。

// 取接收者实体（与 `EntityTakeDamage` 里那段逐字同形 —— 本批一次加了三条同形状的处理器，
// 所以抽出来，避免三份拷贝日后漂开）。
std::uintptr_t EntityReceiverOrError(lua_State* state, const char* api) {
    auto* handle = TryGetEntityHandle(state, 1);
    if (handle == nullptr) {
        luaL_error(state, "%s expects an entity", api);  // 抛错，不返回
        return 0;
    }
    const bool player = luaL_testudata(state, 1, kEntityPlayerMetatable) != nullptr;
    //: 句柄失效 ⇒ 0（调用方**什么都不做**）：PC 上对已消失实体调这些方法同样是空操作。
    return player ? ValidatedEntityPlayer(handle) : ValidatedEntity(handle);
}

// `Entity:SetColor(Color, Duration, Priority, Fadeout, Share)` —— PC 契约
// `tools/pc_contract_docs/Entity.md:542`，正文 `:544-546`：
// *"Set the colormask for the entity. This can be used to tint the sprites in different colors."*
// 与 *"``Share`` boolean will apply color to child entity."*
//
// 语料 **51 处**（全清单里单条调用点最多的一条），形状是
// `entity:SetColor(Color(r,g,b), 1, 1, false, false)`。
//
// ★ 尾部两个布尔**必须可省**：语料里还有 **3 参调用**
// （`tear:SetColor(redColor, -1, 0)`）⇒ 契约页那条固定 5 参的签名**不完整**。
//   ★ 缺省值取 `false`：契约页没写缺省值，而这两个是"特殊行为"开关（`Fadeout` 渐隐、
//   `Share` 把颜色传染给子实体），也就是"不做额外的事"⇒ `false`。
//   **这一条列进作业单第九节让真机确认（V20）** —— 它是本批唯一一处"缺省值靠推断"的地方，
//   写在偏离台账里比藏在代码里好。
//
// ★ 参数个数只接受 4..6（含 `self`）：**少算个数会让模组每一次调用都抛错**（批次 249 的形态），
//   而错误会把整条回调摘掉。
int EntitySetColor(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop < 4 || stackTop > 6) {
        return luaL_error(state,
                          "Entity:SetColor expects (Color, Duration, Priority[, Fadeout[, Share]]); "
                          "got %d argument(s)",
                          stackTop - 1);
    }
    //: 颜色：契约的 `Color.Default`（白色不透明）是缺省，所以先铺缺省再让实参覆盖。
    EngineColorMod color = isaac::runtime::DefaultEngineColorMod();
    if (!isaac::runtime::FillEngineColorMod(state, 2, &color)) {
        return luaL_error(state, "Entity:SetColor expects a Color as its first argument");
    }
    if (!IsIntegerArgument(state, 3) || !IsIntegerArgument(state, 4)) {
        return luaL_error(state, "Entity:SetColor expects integer duration and priority");
    }
    const std::int32_t duration = static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr));
    const std::int32_t priority = static_cast<std::int32_t>(lua_tointegerx(state, 4, nullptr));
    //: 缺省 `false`（见上面那段说明）；`lua_toboolean` 对 `nil`/缺省格都给 0，正是我们要的。
    const bool fadeout = stackTop >= 5 && lua_toboolean(state, 5) != 0;
    const bool share = stackTop >= 6 && lua_toboolean(state, 6) != 0;
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:SetColor");
    const std::uintptr_t method = EntitySetColorMethod();
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型就是 void）
    }
    //: ABI：`(this=x0, color=x1, duration=w2, priority=w3, fadeout=w4, share=w5)`
    //: —— 反汇编首四句 `mov w2x,wN` 给出的形状，见 `kEntitySetColorOffset` 的段注释。
    using EntitySetColorFn = void (*)(std::uintptr_t, const EngineColorMod*, std::int32_t,
                                      std::int32_t, bool, bool);
    engine_call::AsFunction<EntitySetColorFn>(method)(entity, &color, duration, priority, fadeout,
                                                      share);
    return 0;
}

// `Entity:AddCharmed(EntityRef sourceEntity, int Duration)` —— PC 契约
// `tools/pc_contract_docs/Entity.md` 同页（`AddCharmed` 那一行），语料 11 处。
//
// 引用参数用 `EntityRefBufferAt`（与 `Entity:TakeDamage` 的第三个参数**同一个助手**）：
// 它把 Lua 侧那个 `EntityRef` 句柄折算成引擎要的 64 字节缓冲区地址；给的不是 `EntityRef` 就报错
// （模组写错了）。`Duration` 契约里有缺省值 —— 语料全给满，这里保持必需（少给即参数个数不符）。
int EntityAddCharmed(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 3 || !IsIntegerArgument(state, 3)) {
        return luaL_error(state,
                          "Entity:AddCharmed expects (EntityRef, Duration); got %d argument(s)",
                          stackTop - 1);
    }
    const void* reference = EntityRefBufferAt(state, 2);
    if (reference == nullptr) {
        return luaL_error(state, "Entity:AddCharmed expects an EntityRef as its first argument");
    }
    const std::int32_t duration = static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:AddCharmed");
    const std::uintptr_t method = EntityAddCharmedMethod();
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityAddCharmedFn = void (*)(std::uintptr_t, const void*, std::int32_t);
    engine_call::AsFunction<EntityAddCharmedFn>(method)(entity, reference, duration);
    return 0;
}

// `EntityPlayer:UseActiveItem(...)` —— PC 契约 `tools/pc_contract_docs/EntityPlayer.md:1853`：
// `void UseActiveItem ( CollectibleType Item, UseFlags UseFlags = 0, ActiveSlot Slot = -1,
// int CustomVarData = 0 )`，语料 23 处。
//
// ★★ **契约页有两条重载，语料两条都用**（同页 `:1855` 那条是扩展层加的，7 个参数）：
//     基础四参：`(Item, UseFlags, Slot, CustomVarData)`
//     扩展七参：`(Item, ShowAnim=false, KeepActiveItem=false, AllowNonMainPlayer=true,
//                ToAddCostume=false, Slot=-1, CustomVarData=0)`
//   语料里 12 处是 5 参、13 处是 6 参（都是**扩展形**，第 2 个参数是布尔），
//   另有 2/3 参的是基础形（第 2 个参数是 `UseFlag.USE_NOANIM` 这种**数字**）。
//   ⇒ **按第 2 个参数的类型分派**（数字 = 基础形、布尔 = 扩展形）。
//   ★ 这一格如果只按基础形写（要求 2..5 个整数），语料里那 25 处扩展形调用会**每一次都抛错**
//     ⇒ 整条回调被摘掉。这正是批次 249 的形态，所以在宿主用例里专门钉了它。
//
// ★ 扩展形的四个布尔**在引擎那条入口上表达不了**（NS 引擎只有基础形的
//   `Entity_Player::UseActiveItem(eCollectibleType, unsigned, int, int)`，arity **4**）。
//   做法是把三个能一一对应的布尔折成 `UseFlag` 位 —— 用的是**引擎自己的词表**，
//   而且两个缺省正好对上（`ShowAnim=false` ↔ `USE_NOANIM`、`ToAddCostume=false` ↔ `USE_NOCOSTUME`、
//   `AllowNonMainPlayer=true` ↔ `USE_ALLOWNONMAIN`）：
//       `ShowAnim == false`      ⇒ `USE_NOANIM`     （1）
//       `ToAddCostume == false`  ⇒ `USE_NOCOSTUME`  （2）
//       `AllowNonMainPlayer`     ⇒ `USE_ALLOWNONMAIN`（8）
//   ★ `KeepActiveItem` **在 `UseFlag` 里没有对应位** ⇒ 表达不了（= 不消耗道具这一支做不到）。
//   ⇒ 整条已按 `Partial` 登记在 `api_deviation.cpp`（id `0x0E010094`），并进作业单第九节让真机确认。
//
// ★ 这条有**副作用**（真的用掉一次主动道具）：Item / Slot / CustomVarData 原样交给引擎，
//   不做任何补位或夹取 —— 语义（消耗充能、触发效果）全归引擎。
int EntityPlayerUseActiveItem(lua_State* state) {
    const int stackTop = lua_gettop(state);
    //: 栈顶最大是 `self` + 7（扩展形给满）= 8。
    if (stackTop < 2 || stackTop > 8) {
        return luaL_error(state,
                          "EntityPlayer:UseActiveItem expects (Item[, UseFlags[, Slot[, "
                          "CustomVarData]]]) or (Item[, ShowAnim[, KeepActiveItem[, "
                          "AllowNonMainPlayer[, ToAddCostume[, Slot[, CustomVarData]]]]]]); "
                          "got %d argument(s)",
                          stackTop - 1);
    }
    if (!IsIntegerArgument(state, 2)) {
        return luaL_error(state, "EntityPlayer:UseActiveItem expects an integer Item");
    }
    const std::int32_t item = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    std::uint32_t useFlags = 0;
    std::int32_t slot = -1;
    std::int32_t customVarData = 0;
    if (lua_type(state, 3) == LUA_TBOOLEAN) {
        //: 扩展七参形（契约同页 `:1855`，缺省值就是函数签名里写的那几个）。
        const bool showAnim = stackTop >= 3 ? lua_toboolean(state, 3) != 0 : false;
        const bool allowNonMainPlayer = stackTop >= 5 ? lua_toboolean(state, 5) != 0 : true;
        const bool toAddCostume = stackTop >= 6 ? lua_toboolean(state, 6) != 0 : false;
        //: `KeepActiveItem`（第 4 个）在 `UseFlag` 里没有对应位 ⇒ 读出来只用于下面那句注释里的
        //: 已知损失说明，不参与折算。（读出来是为了让"我们确实看过它"这件事在代码里可见。）
        const bool keepActiveItem = stackTop >= 4 && lua_toboolean(state, 4) != 0;
        static_cast<void>(keepActiveItem);
        if (stackTop >= 7 && !IsIntegerArgument(state, 7)) {
            return luaL_error(state, "EntityPlayer:UseActiveItem expects an integer Slot");
        }
        if (stackTop >= 8 && !IsIntegerArgument(state, 8)) {
            return luaL_error(state, "EntityPlayer:UseActiveItem expects an integer CustomVarData");
        }
        slot = stackTop >= 7 ? static_cast<std::int32_t>(lua_tointegerx(state, 7, nullptr)) : -1;
        customVarData = stackTop >= 8 ? static_cast<std::int32_t>(lua_tointegerx(state, 8, nullptr)) : 0;
        //: 三个布尔 → `UseFlag` 位（常量值取自本仓库自己的 `pc_lua_enum_data.cpp` 里的
        //: `UseFlag` 表：USE_NOANIM=1 / USE_NOCOSTUME=2 / USE_ALLOWNONMAIN=8）。
        if (!showAnim) {
            useFlags |= 1U;
        }
        if (!toAddCostume) {
            useFlags |= 2U;
        }
        if (allowNonMainPlayer) {
            useFlags |= 8U;
        }
    } else {
        //: 基础四参形（契约 `:1853`，三个缺省值都写在签名里：0 / -1 / 0）。
        //: 这一支最多 `self` + 4 —— 再多就既不是基础形（基础形只有 4 个参数），
        //: 也不是扩展形（扩展形的第 2 个参数是布尔）⇒ 报错是对的。
        if (stackTop > 5) {
            return luaL_error(state,
                              "EntityPlayer:UseActiveItem expects at most 4 arguments in the "
                              "4-argument form");
        }
        for (int index = 3; index <= stackTop; ++index) {
            if (!IsIntegerArgument(state, index)) {
                return luaL_error(state,
                                  "EntityPlayer:UseActiveItem expects integer UseFlags/Slot/"
                                  "CustomVarData in the 4-argument form");
            }
        }
        useFlags = stackTop >= 3 ? static_cast<std::uint32_t>(lua_tointegerx(state, 3, nullptr)) : 0U;
        slot = stackTop >= 4 ? static_cast<std::int32_t>(lua_tointegerx(state, 4, nullptr)) : -1;
        customVarData = stackTop >= 5 ? static_cast<std::int32_t>(lua_tointegerx(state, 5, nullptr)) : 0;
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:UseActiveItem");
    const std::uintptr_t method = EntityPlayerUseActiveItemMethod();
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型就是 void）
    }
    using EntityPlayerUseActiveItemFn = void (*)(std::uintptr_t, std::int32_t, std::uint32_t,
                                                 std::int32_t, std::int32_t);
    engine_call::AsFunction<EntityPlayerUseActiveItemFn>(method)(entity, item, useFlags, slot,
                                                                 customVarData);
    return 0;
}

// ---- 批次 273（2026-10-02）：`needs_new_receiver` 桶里参数最简单的一批 --------------------------
//
// 8 条的来路与批次 271 相同：引擎里有同名方法，而且**同名方法只有一个类有**（用嵌套名解析器扫过
// 全符号表 ⇒ 没有子类重写，不需要像 `Entity:TakeDamage` 那样"挑一个"）。
// 参数形态只有三种（标量 / `Vector` / `EntityRef`），所以共用两个小助手；
// 八条的引擎入口都走同一个 16 字节取址助手 `EntityMethodByExpectedBytes()`。
//
// 降级口径统一：**拿不到实体（句柄失效）或入口对不上 ⇒ 什么都不做、不报错**
// （那六条 PC 返回 `void`）；两条返回实体的（`AddBlueSpider` / `AddMinisaac`）在拿不到时压 `nil`
// —— 与 `Entity:ToPlayer()` 一族"转换/创建失败给 nil"同一口径，模组的 `if e then` 写法照样成立。

//: 读一个 `Vector` 实参（不是 `Vector` 就给 `nullptr`，由调用方报错）。
VectorHandle* VectorArgument(lua_State* state, int index) {
    return TryVectorArgument(state,index);
}

// `Entity:AddFreeze(EntityRef Source, int Duration)` —— PC 契约 `tools/pc_contract_docs/Entity.md`，
// 语料 2 处。引擎入口 `Entity::AddFreeze(EntityRef const&, int)` @ `0x5E358`。
int EntityAddFreeze(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 3 || !IsIntegerArgument(state, 3)) {
        return luaL_error(state, "Entity:AddFreeze expects (EntityRef, Duration); got %d argument(s)",
                          stackTop - 1);
    }
    const void* reference = EntityRefBufferAt(state, 2);
    if (reference == nullptr) {
        return luaL_error(state, "Entity:AddFreeze expects an EntityRef as its first argument");
    }
    const std::int32_t duration = static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:AddFreeze");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityAddFreezeOffset,
                                                              kEntityAddFreezeExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityAddFreezeFn = void (*)(std::uintptr_t, const void*, std::int32_t);
    engine_call::AsFunction<EntityAddFreezeFn>(method)(entity, reference, duration);
    return 0;
}

// `Entity:AddVelocity(Vector Velocity[, boolean IgnoreTimeScale = false])` —— 批次 346（2026-10-04）。
//
// PC 契约页 `tools/pc_contract_docs/Entity.md`：
//   `:282` = ABP 一参 `#### void AddVelocity ( [Vector](Vector.md) Velocity )`；
//   `:284` = Rep+ 两参（`IgnoreTimeScale` 缺省 `false`）—— Switch 上跑的就是 Repentance ⇒ 两参形态。
// 语料 **20 处**（清单按方法名聚合记 15 处；O 组 `grep` 实测 20）**全是 1 参**写法
// ⇒ 1 参必须放行（收错个数会让模组每次调用都抛错、整条回调被摘 —— 批次 249 的形态）。
//
// PC 绑定本体 VA `0x422B60`（逐条反汇编见 E 组 §2.2 / H 组 §2.1.2；O 组独立复核算式逐条正确）：
//   friction = this[0x2c4];  if (friction == 0.0f) return;      // ★ 零守卫：**精确 0** 才返回
//   k = IgnoreTimeScale ? 1.0f : this[0x2f4];                   // 时间缩放
//   this[0x2b8] += (k * v.x) / friction;                        // ★ 次序：先 k*v，再 /friction，再 +=
//   this[0x2bc] += (k * v.y) / friction;
//   ⇒ 全程**没有** max/min/abs/sqrt（无钳制）、**没有一个 `call`**（不调 `TimeScaledFriction`）。
//
// ★★ Switch 侧**没有可调真身**（符号 0 命中 / NRO 原始字节 0 命中）⇒ 按上面算式**直接读写三格**：
//    速度 `+0x334/+0x338`（`kEntityVelocityOffset`，已有）、摩擦 `+0x340`（`kEntityFrictionOffset`，已有）、
//    时间缩放 `+0x370`（**本批新增** `kEntityTimeScaleOffset`；量级由 H 组六条证据离线定案 = 常态 1.0f）。
// ★★ **`friction == 0.0f` 只挡精确相等**（MSVC 的 `ucomiss/test ah,0x44/jnp` 逐位推演）：
//    NaN 会**穿过**。C++ 里 `friction == 0.0F` 对 NaN 同样为 false ⇒ 行为逐位一致 ⇒ **不加 NaN 特判**。
// ★★ **读/写失败一律静默**（批次 250 定案：我们不许抛错）：PC 不会失败，读不到就当作"不做事"。
// ★ 本条**推翻旧负结果**「两侧摩擦模型不同 ⇒ 不能做」（331 记的）：复核证明是**同一族**，
//   按 PC 算式复刻即与 PC 一致（见 `runtime_constants.hpp` 的批次 346 段与 O 组报告）。
int EntityAddVelocity(lua_State* state) {
    const int stackTop = lua_gettop(state);
    //: 冒号调用 ⇒ 栈上第 1 个是 `self`，后面 1 或 2 个实参（第 3 个可省）。
    if (stackTop != 2 && stackTop != 3) {
        return luaL_error(state, "Entity:AddVelocity expects (Vector[, boolean]); got %d argument(s)",
                          stackTop - 1);
    }
    VectorHandle* velocity = VectorArgument(state, 2);
    if (velocity == nullptr) {
        return luaL_error(state, "Entity:AddVelocity expects a Vector");
    }
    //: 第 3 格可省（缺省 `false` = PC 的 `IgnoreTimeScale` 缺省）；给了就必须是布尔。
    bool ignoreTimeScale = false;
    if (stackTop == 3) {
        if (!lua_isboolean(state, 3)) {
            return luaL_error(state, "Entity:AddVelocity expects a boolean IgnoreTimeScale");
        }
        ignoreTimeScale = lua_toboolean(state, 3) != 0;
    }
    //: 接收者：`Entity` 族任意实体（PC 也允许对任意实体调）。句柄失效 ⇒ 返回 0 ⇒ 静默降级。
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:AddVelocity");
    if (entity == 0) {
        return 0;
    }
    float friction = 0.0F;
    if (!ReadEngine(entity + kEntityFrictionOffset, &friction)) {
        return 0;
    }
    if (friction == 0.0F) {
        return 0;  // ★ PC 零守卫：精确 0.0f ⇒ 什么都不写（NaN 穿过）
    }
    float k = 1.0F;  //: PC：`IgnoreTimeScale == true` 时用常量 1.0f
    if (!ignoreTimeScale) {
        if (!ReadEngine(entity + kEntityTimeScaleOffset, &k)) {
            return 0;
        }
    }
    float velocityX = 0.0F;
    float velocityY = 0.0F;
    if (!ReadEngine(entity + kEntityVelocityOffset, &velocityX) ||
        !ReadEngine(entity + kEntityVelocityOffset + sizeof(float), &velocityY)) {
        return 0;
    }
    //: 次序与 PC 逐条一致：先 `k*分量`，再 `/摩擦`，再 `+=`；括号钉死结合律。
    const float addX = (k * velocity->x) / friction;
    const float addY = (k * velocity->y) / friction;
    WriteEngine(entity + kEntityVelocityOffset, velocityX + addX);
    WriteEngine(entity + kEntityVelocityOffset + sizeof(float), velocityY + addY);
    return 0;  //: PC 返回 `void` ⇒ 0 个返回值。
}

// `Entity:AddPoison(EntityRef Source, int Duration, float Damage)` —— 同页契约，语料 2 处。
// 引擎入口 `Entity::AddPoison(EntityRef const&, int, float)` @ `0x5E5F8`。
int EntityAddPoison(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 4 || !IsIntegerArgument(state, 3) || !lua_isnumber(state, 4)) {
        return luaL_error(state,
                          "Entity:AddPoison expects (EntityRef, Duration, Damage); got %d argument(s)",
                          stackTop - 1);
    }
    const void* reference = EntityRefBufferAt(state, 2);
    if (reference == nullptr) {
        return luaL_error(state, "Entity:AddPoison expects an EntityRef as its first argument");
    }
    const std::int32_t duration = static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr));
    const float damage = static_cast<float>(lua_tonumber(state, 4));
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:AddPoison");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityAddPoisonOffset,
                                                              kEntityAddPoisonExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityAddPoisonFn = void (*)(std::uintptr_t, const void*, std::int32_t, float);
    engine_call::AsFunction<EntityAddPoisonFn>(method)(entity, reference, duration, damage);
    return 0;
}

// `EntityPlayer:AddGoldenHearts(int Hearts)` —— PC 契约 `EntityPlayer.md`，语料 2 处。
// 引擎入口 `Entity_Player::AddGoldenHearts(int)` @ `0x2FC924`。
int EntityPlayerAddGoldenHearts(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 2 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state, "EntityPlayer:AddGoldenHearts expects a heart count; got %d argument(s)",
                          stackTop - 1);
    }
    const std::int32_t hearts = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddGoldenHearts");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddGoldenHeartsOffset,
                                                             kEntityPlayerAddGoldenHeartsExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityPlayerAddGoldenHeartsFn = void (*)(std::uintptr_t, std::int32_t);
    engine_call::AsFunction<EntityPlayerAddGoldenHeartsFn>(method)(entity, hearts);
    return 0;
}

// `EntityPlayer:AddPill(PillColor Pill)` —— 同页契约，语料 2 处。
// 引擎入口 `Entity_Player::AddPill(ePillColor)` @ `0x2B0B80`。
// ★ 参数是枚举（`ePillColor`）⇒ 照 PC 的 `luaL_checkinteger` 口径收整数，**不**在 Lua 侧查表。
int EntityPlayerAddPill(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 2 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state, "EntityPlayer:AddPill expects a pill colour; got %d argument(s)",
                          stackTop - 1);
    }
    const std::int32_t pill = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddPill");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddPillOffset,
                                                             kEntityPlayerAddPillExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityPlayerAddPillFn = void (*)(std::uintptr_t, std::int32_t);
    engine_call::AsFunction<EntityPlayerAddPillFn>(method)(entity, pill);
    return 0;
}

// `EntityPlayer:AnimateAppear()` —— 同页契约，语料 2 处。
// 引擎入口 `Entity_Player::AnimateAppear()` @ `0x2E8184`（arity 0）。
// ★ 它的入口 16 字节与 `AddGoldenHearts` **完全相同**（同一个编译器 prologue）—— 区分靠偏移，
//   守卫只用来确认"这个地址上确实是我们要的那串指令"（见 `runtime_constants.hpp` 批次 273 段）。
int EntityPlayerAnimateAppear(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 1) {
        return luaL_error(state, "EntityPlayer:AnimateAppear accepts no arguments; got %d",
                          stackTop - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AnimateAppear");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAnimateAppearOffset,
                                                             kEntityPlayerAnimateAppearExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityPlayerAnimateAppearFn = void (*)(std::uintptr_t);
    engine_call::AsFunction<EntityPlayerAnimateAppearFn>(method)(entity);
    return 0;
}

// `EntityPlayer:DropTrinket(Vector DropPos, boolean ReplaceTick)` —— 同页契约，语料 2 处。
// 引擎入口 `Entity_Player::DropTrinket(Vector2 const&, bool)` @ `0x2A20D4`。
int EntityPlayerDropTrinket(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 3) {
        return luaL_error(state,
                          "EntityPlayer:DropTrinket expects (Vector, boolean); got %d argument(s)",
                          stackTop - 1);
    }
    VectorHandle* dropPosition = VectorArgument(state, 2);
    if (dropPosition == nullptr) {
        return luaL_error(state, "EntityPlayer:DropTrinket expects a Vector as its first argument");
    }
    const bool replaceTick = lua_toboolean(state, 3) != 0;
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:DropTrinket");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerDropTrinketOffset,
                                                             kEntityPlayerDropTrinketExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using EntityPlayerDropTrinketFn = void (*)(std::uintptr_t, const VectorHandle*, bool);
    engine_call::AsFunction<EntityPlayerDropTrinketFn>(method)(entity, dropPosition, replaceTick);
    return 0;
}

// `EntityPlayer:AddBlueSpider(Vector Position)` —— 同页契约（返回 `Entity`），语料 4 处。
// 引擎入口 `Entity_Player::AddBlueSpider(Vector2 const&)` @ `0x2FB40C`，返回值是**新实体指针**。
// ★ 交回 Lua 的句柄用 `Entity` 元表（与 `Entity:ToPlayer()` 一族同一口径）；
//   引擎返回 0（没造出来）时压 `nil`（模组普遍写 `if e then`）。
int EntityPlayerAddBlueSpider(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 2) {
        return luaL_error(state,
                          "EntityPlayer:AddBlueSpider expects a Vector; got %d argument(s)",
                          stackTop - 1);
    }
    VectorHandle* position = VectorArgument(state, 2);
    if (position == nullptr) {
        return luaL_error(state, "EntityPlayer:AddBlueSpider expects a Vector position");
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddBlueSpider");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddBlueSpiderOffset,
                                                             kEntityPlayerAddBlueSpiderExpectedBytes);
    if (entity == 0 || method == 0) {
        PushNil(state);
        return 1;
    }
    using EntityPlayerAddBlueSpiderFn = std::uintptr_t (*)(std::uintptr_t, const VectorHandle*);
    const std::uintptr_t created =
        engine_call::AsFunction<EntityPlayerAddBlueSpiderFn>(method)(entity, position);
    if (created == 0) {
        PushNil(state);
        return 1;
    }
    PushEntityHandle(state, created, kEntityMetatable);
    return 1;
}

// `EntityPlayer:AddMinisaac(Vector Position, boolean PlayAnim = true)` —— 同页契约
// （返回 `EntityFamiliar`），语料 2 处。★ 缺省值 `true` **写在契约签名里**，不是推断的。
// 引擎入口 `Entity_Player::AddMinisaac(Vector2 const&, bool)` @ `0x2AC1F4`。
// ★ 返回的实体同样用 `Entity` 元表交回（与 `Entity:ToFamiliar()` 的现实一致：那一条也是压
//   `Entity` 元表的句柄 —— 我们这套里"熟悉实体视图"就是基类视图）。
int EntityPlayerAddMinisaac(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop < 2 || stackTop > 3) {
        return luaL_error(state,
                          "EntityPlayer:AddMinisaac expects (Vector[, PlayAnim]); got %d argument(s)",
                          stackTop - 1);
    }
    VectorHandle* position = VectorArgument(state, 2);
    if (position == nullptr) {
        return luaL_error(state, "EntityPlayer:AddMinisaac expects a Vector position");
    }
    //: 契约缺省 `PlayAnim = true`。
    const bool playAnimation = stackTop >= 3 ? lua_toboolean(state, 3) != 0 : true;
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddMinisaac");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddMinisaacOffset,
                                                             kEntityPlayerAddMinisaacExpectedBytes);
    if (entity == 0 || method == 0) {
        PushNil(state);
        return 1;
    }
    using EntityPlayerAddMinisaacFn = std::uintptr_t (*)(std::uintptr_t, const VectorHandle*, bool);
    const std::uintptr_t created =
        engine_call::AsFunction<EntityPlayerAddMinisaacFn>(method)(entity, position, playAnimation);
    if (created == 0) {
        PushNil(state);
        return 1;
    }
    PushEntityHandle(state, created, kEntityMetatable);
    return 1;
}

// ---- 批次 278（2026-10-02）：`EntityPlayer` 族 5 条 ---------------------------------------------
//
// 形态与批次 273/274 同源（`EntityReceiverOrError` + `EntityMethodByExpectedBytes` + 静默降级），
// 只是这批里有一条带**实体参数**（`AddBlueFlies` 的 `Target`）⇒ 新增一个小助手 `EntityArgumentPointer()`。
// 返回实体的三条（`ThrowHeldEntity` / `AddSwarmFlyOrbital` / `AddItemWisp` / `AddBlueFlies`）
// 一律"压句柄或 `nil`"（与 `Entity:ToPlayer()` 一族同口径）。

//: 取一个 `Entity` 实参的**裸指针**。返回 `nullptr` 表示"这一格不是实体句柄"（由调用方报错）；
//: `*valid` 为 `false` 表示"是个实体句柄但已失效"（**不要**把它交给引擎 —— 那是个野指针）。
void* EntityArgumentPointer(lua_State* state, int index, bool* valid) {
    void* raw = luaL_testudata(state, index, kEntityMetatable);
    bool player = false;
    if (raw == nullptr) {
        raw = luaL_testudata(state, index, kEntityPlayerMetatable);
        player = true;
    }
    if (valid != nullptr) {
        *valid = false;
    }
    if (raw == nullptr) {
        return nullptr;
    }
    auto* handle = static_cast<EntityHandle*>(raw);
    const std::uintptr_t entity = player ? ValidatedEntityPlayer(handle) : ValidatedEntity(handle);
    if (entity == 0) {
        return nullptr;
    }
    if (valid != nullptr) {
        *valid = true;
    }
    return engine_memory::AsObject(entity);
}

// `EntityPlayer:ThrowHeldEntity(Vector Velocity)` —— PC 契约 `EntityPlayer.md`，语料 1 处。
// 引擎入口 `Entity_Player::ThrowHeldEntity(Vector2 const&)` @ `0x27C648`（arity 1 = 契约的参数个数 ✓）。
// 返回 `Entity`（扔出去的那个实体）⇒ 压句柄或 `nil`。
int EntityPlayerThrowHeldEntity(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 2) {
        return luaL_error(state,
                          "EntityPlayer:ThrowHeldEntity expects a Vector; got %d argument(s)",
                          stackTop - 1);
    }
    VectorHandle* velocity = VectorArgument(state, 2);
    if (velocity == nullptr) {
        return luaL_error(state, "EntityPlayer:ThrowHeldEntity expects a Vector velocity");
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:ThrowHeldEntity");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerThrowHeldEntityOffset,
                                                             kEntityPlayerThrowHeldEntityExpectedBytes);
    if (entity == 0 || method == 0) {
        PushNil(state);
        return 1;
    }
    using ThrowHeldEntityFn = std::uintptr_t (*)(std::uintptr_t, const VectorHandle*);
    const std::uintptr_t thrown =
        engine_call::AsFunction<ThrowHeldEntityFn>(method)(entity, velocity);
    if (thrown == 0) {
        PushNil(state);
        return 1;
    }
    PushEntityHandle(state, thrown, kEntityMetatable);
    return 1;
}

// `EntityPlayer:AddSwarmFlyOrbital(Vector Position)` —— 同页契约，语料 1 处。
// 引擎入口 `Entity_Player::AddSwarmFlyOrbital(Vector2 const&)` @ `0x28D510`（arity 1 ✓，返回 EntityFamiliar）。
int EntityPlayerAddSwarmFlyOrbital(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 2) {
        return luaL_error(state,
                          "EntityPlayer:AddSwarmFlyOrbital expects a Vector; got %d argument(s)",
                          stackTop - 1);
    }
    VectorHandle* position = VectorArgument(state, 2);
    if (position == nullptr) {
        return luaL_error(state, "EntityPlayer:AddSwarmFlyOrbital expects a Vector position");
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddSwarmFlyOrbital");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddSwarmFlyOrbitalOffset,
                                                             kEntityPlayerAddSwarmFlyOrbitalExpectedBytes);
    if (entity == 0 || method == 0) {
        PushNil(state);
        return 1;
    }
    using AddSwarmFlyOrbitalFn = std::uintptr_t (*)(std::uintptr_t, const VectorHandle*);
    const std::uintptr_t created =
        engine_call::AsFunction<AddSwarmFlyOrbitalFn>(method)(entity, position);
    if (created == 0) {
        PushNil(state);
        return 1;
    }
    PushEntityHandle(state, created, kEntityMetatable);
    return 1;
}

// `EntityPlayer:AddItemWisp(CollectibleType Collectible, Vector Position, boolean PlayAnim)` ——
// 同页契约，语料 4 处。引擎入口 `Entity_Player::AddItemWisp(int, Vector2 const&, bool)`
// @ `0x31DF50`（arity 3 = 契约三个参数 ✓）。返回 `EntityFamiliar` ⇒ 压句柄或 `nil`。
int EntityPlayerAddItemWisp(lua_State* state) {
    const int stackTop = lua_gettop(state);
    //: ★ 第三个参数在契约里有缺省值（`boolean AdjustOrbitLayer = false`）⇒ 收 3..4 个。
    if (stackTop < 3 || stackTop > 4 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state,
                          "EntityPlayer:AddItemWisp expects (Collectible, Vector[, PlayAnim]); "
                          "got %d argument(s)",
                          stackTop - 1);
    }
    VectorHandle* position = VectorArgument(state, 3);
    if (position == nullptr) {
        return luaL_error(state, "EntityPlayer:AddItemWisp expects a Vector position");
    }
    const std::int32_t collectible = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const bool playAnimation = stackTop >= 4 ? lua_toboolean(state, 4) != 0 : false;
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddItemWisp");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddItemWispOffset,
                                                             kEntityPlayerAddItemWispExpectedBytes);
    if (entity == 0 || method == 0) {
        PushNil(state);
        return 1;
    }
    using AddItemWispFn = std::uintptr_t (*)(std::uintptr_t, std::int32_t, const VectorHandle*, bool);
    const std::uintptr_t created = engine_call::AsFunction<AddItemWispFn>(method)(
        entity, collectible, position, playAnimation);
    if (created == 0) {
        PushNil(state);
        return 1;
    }
    PushEntityHandle(state, created, kEntityMetatable);
    return 1;
}

// `EntityPlayer:UsePill(PillEffect ID, PillColor PillColor, UseFlags Flags)` —— 同页契约，语料 1 处。
// 引擎入口 `Entity_Player::UsePill(ePillEffect, ePillColor, unsigned)` @ `0x2DFC04`（arity 3 ✓）。
// 三个都是枚举/位掩码 ⇒ 照 PC 的 `luaL_checkinteger` 口径收整数，**不**查表、不夹取值范围。
int EntityPlayerUsePill(lua_State* state) {
    const int stackTop = lua_gettop(state);
    //: ★ 第三个参数在契约里有缺省值（`UseFlags = 0`）⇒ 收 3..4 个。
    if (stackTop < 3 || stackTop > 4 || !IsIntegerArgument(state, 2) || !IsIntegerArgument(state, 3) ||
        (stackTop == 4 && !IsIntegerArgument(state, 4))) {
        return luaL_error(state,
                          "EntityPlayer:UsePill expects (PillEffect, PillColor[, UseFlags]); "
                          "got %d argument(s)",
                          stackTop - 1);
    }
    const std::int32_t effect = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::int32_t pillColor = static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr));
    const std::uint32_t useFlags =
        stackTop >= 4 ? static_cast<std::uint32_t>(lua_tointegerx(state, 4, nullptr)) : 0U;
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:UsePill");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerUsePillOffset,
                                                             kEntityPlayerUsePillExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;
    }
    using UsePillFn = void (*)(std::uintptr_t, std::int32_t, std::int32_t, std::uint32_t);
    engine_call::AsFunction<UsePillFn>(method)(entity, effect, pillColor, useFlags);
    return 0;
}

// `EntityPlayer:AddBlueFlies(int Amount, Vector Position, Entity Target)` —— 同页契约，语料 1 处。
// 引擎入口 `Entity_Player::AddBlueFlies(int, Vector2 const&, Entity*)` @ `0x27FC18`（arity 3 ✓）。
// ★ 这条是这批唯一带**实体参数**的：`Target` 必须是实体句柄；句柄失效时**静默降级**
//   （绝不把野指针交给引擎）。返回 `Entity` ⇒ 压句柄或 `nil`。
int EntityPlayerAddBlueFlies(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 4 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state,
                          "EntityPlayer:AddBlueFlies expects (Amount, Vector, Target); "
                          "got %d argument(s)",
                          stackTop - 1);
    }
    VectorHandle* position = VectorArgument(state, 3);
    if (position == nullptr) {
        return luaL_error(state, "EntityPlayer:AddBlueFlies expects a Vector position");
    }
    bool targetValid = false;
    void* target = EntityArgumentPointer(state, 4, &targetValid);
    if (target == nullptr && !targetValid) {
        //: 区分"不是实体句柄"（模组写错了 ⇒ 报错）与"句柄已失效"（⇒ 静默降级）。
        const bool isHandle = luaL_testudata(state, 4, kEntityMetatable) != nullptr ||
                              luaL_testudata(state, 4, kEntityPlayerMetatable) != nullptr;
        if (!isHandle) {
            return luaL_error(state, "EntityPlayer:AddBlueFlies expects an entity as its target");
        }
        PushNil(state);
        return 1;
    }
    const std::int32_t amount = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddBlueFlies");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddBlueFliesOffset,
                                                             kEntityPlayerAddBlueFliesExpectedBytes);
    if (entity == 0 || method == 0) {
        PushNil(state);
        return 1;
    }
    using AddBlueFliesFn = std::uintptr_t (*)(std::uintptr_t, std::int32_t, const VectorHandle*,
                                              void*);
    const std::uintptr_t created =
        engine_call::AsFunction<AddBlueFliesFn>(method)(entity, amount, position, target);
    if (created == 0) {
        PushNil(state);
        return 1;
    }
    PushEntityHandle(state, created, kEntityMetatable);
    return 1;
}

// ---- 批次 275（2026-10-02）：实体标志位的加/清两条 -------------------------------------------
//
// 这两条在 `needs_forensics` 桶里（符号表里**没有**同名函数）—— 因为它们在 PC 上就是**叶函数**：
// `isaac-ng.exe` 的绑定函数 VA `0x4122A0` 全文只有 5 条指令
// （`mov eax,[ebp+8]` / `or [ecx+0x160],eax` / `mov eax,[ebp+0xc]` / `or [ecx+0x164],eax` / `ret 8`），
// `ClearEntityFlags`（VA `0x4122C0`）是它的镜像（`not` + `and`）。
//
// ★ 两个关键读数：
//   ① `ret 0x8` + 两个栈槽 ⇒ PC 上这个参数是 **64 位整数**（32 位 x86 的调用约定把 64 位实参
//      拆成栈上两个 dword）⇒ 语义就是 `EntityFlags |= Flags` / `&= ~Flags`（**整体 64 位**），
//      不是"往两个独立字段各写一次"。
//   ② 字段本体我们**早就有确认证据**：`kEntityFlagsOffset`（`Entity + 0x1B8`，64 位）——
//      `Entity:HasEntityFlags` 一直用它，而且那条的注释里记着两个独立消费者
//      （`QueryRadius`/`FindByType` 判 bit46 `FLAG_NO_QUERY`、活表判据判 bit3）
//      ⇒ "PC 的 `+0x160` 与 Switch 的 `+0x1B8` 是同一个语义字段"这件事**已经定过了**，
//      本批不需要再取证偏移。
//
// ★★ **这是本文件里少见的一次"写引擎内存"**（此前 `Entity` 族只有读）。写与读的危险等级不同，
//    所以按 `game_api.cpp` 的 `HUD:SetVisible` 那一套：**先确认可读、再确认可写，判定不通过
//    就一个字节都不落**（`ReadEngine` / `WriteEngine` 两个助手本身就是这条纪律的实现）。
//    读-改-写在这里是安全的：这些 API 只在托管回调（主线程）里被调用，不会与引擎并发写同一格。

//: 读-改-写 `Entity + kEntityFlagsOffset` 那一格（`mutate` 接收当前值、返回新值）。
//: 返回 `false` 表示**这次没有真的写**（拿不到实体 / 读不到 / 不可写）—— 调用方据此静默降级。
//:
//: ★ 用**模板**而不是函数指针：掩码要带进去，捕获的 lambda 不能退化成函数指针
//:   （第一次写成 `std::uint64_t (*)(std::uint64_t)` 参数，编译期就红了）。
template <typename Mutator>
bool MutateEntityFlags(std::uintptr_t entity, Mutator mutate) noexcept {
    if (entity == 0) {
        return false;
    }
    std::uint64_t current = 0;
    if (!ReadEngine(entity + kEntityFlagsOffset, &current)) {
        return false;
    }
    return WriteEngine(entity + kEntityFlagsOffset, mutate(current));
}

// `Entity:AddEntityFlags(int Flags)` —— PC 契约 `tools/pc_contract_docs/Entity.md`，语料 28 处。
// 语义 = `EntityFlags |= Flags`（见上面的取证）。
int EntityAddEntityFlags(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 2 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Entity:AddEntityFlags expects a flags value; got %d argument(s)",
                          stackTop - 1);
    }
    //: ★ 掩码按**无符号 64 位**取（PC 的 `EntityFlag` 里有 `1 << 62` 这种位 ⇒ 不能走 int32）。
    const std::uint64_t flags =
        static_cast<std::uint64_t>(static_cast<std::int64_t>(lua_tointegerx(state, 2, nullptr)));
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:AddEntityFlags");
    static_cast<void>(MutateEntityFlags(entity, [flags](std::uint64_t current) {
        return current | flags;
    }));
    return 0;
}

// `Entity:GetEntityFlags()` —— PC 契约 `tools/pc_contract_docs/Entity.md` 的 `int GetEntityFlags ( )`。
//
// ★ 语义与字段两条证据都来自**同一个地方**（批次 272 查 `Entity:GetEntityFlags` 时就读到过）：
//   PC 的绑定函数 VA `0x4122E0` 全文是
//   `mov eax,[ecx+0x160]` / `mov edx,[ecx+0x164]` / `ret`
//   ⇒ **两个 dword 一起返回**，也就是那条 `ret 0x8` 的搭档：**它是一个 64 位值**，
//   与 `AddEntityFlags`/`ClearEntityFlags` 操作的是**同一格**（我们的 `kEntityFlagsOffset`）。
//   ★ 这一条原本被分在 `field_row` 桶（"引擎里没有同名访问器"）—— 现在读侧、写侧都在我们手里，
//     三兄弟（Get/Add/Clear）用的是同一格、同一套证据。
int EntityGetEntityFlags(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 1) {
        return luaL_error(state, "Entity:GetEntityFlags accepts no arguments; got %d",
                          stackTop - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:GetEntityFlags");
    std::uint64_t flags = 0;
    if (entity == 0 || !ReadEngine(entity + kEntityFlagsOffset, &flags)) {
        //: 数值型降级给 `0`（= "一个标志位都没有"），并按纪律记一笔探针。
        return PushNativeFallbackInteger(state, kFbEntityGetEntityFlags, 0);
    }
    lua_pushinteger(state, static_cast<lua_Integer>(flags));
    return 1;
}

// `Entity:ClearEntityFlags(int Flags)` —— 同页契约，语料 11 处。
// 语义 = `EntityFlags &= ~Flags`（PC 侧是 `not` + `and` 的镜像，见上面的取证）。
int EntityClearEntityFlags(lua_State* state) {
    const int stackTop = lua_gettop(state);
    if (stackTop != 2 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state, "Entity:ClearEntityFlags expects a flags value; got %d argument(s)",
                          stackTop - 1);
    }
    const std::uint64_t flags =
        static_cast<std::uint64_t>(static_cast<std::int64_t>(lua_tointegerx(state, 2, nullptr)));
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:ClearEntityFlags");
    static_cast<void>(MutateEntityFlags(entity, [flags](std::uint64_t current) {
        return current & ~flags;
    }));
    return 0;
}

// ---- 批次 274（2026-10-02）：清桶批 11 条
//
// ★★ **别名不能重名**：这里每个处理器用自己的 `using <名字>Fn = …`，**不许都写 `using Fn`** ——
//   `tools/engine_offset_abi_report.py` 的 `resolve_alias("Fn")` **只认第一个**，那样它会拿
//   第一个处理器的签名去比后面所有常量 ⇒ 报一堆假的 `float-mismatch`（本批真踩过一次）。（`Entity` 3 + `EntityPlayer` 8）----------------------
//
// 形态只有五种（0 参 / 1 个整数 / 1 个浮点 / `(EntityRef, int)` / `(int, Vector)`），
// 所以这里全部走同一套：`EntityReceiverOrError()` 取接收者 → `EntityMethodByExpectedBytes()`
// 核入口 16 字节 → 直调 → 失败静默降级。**没有一处新造助手**。
//
// ★ 两条与众不同的：`CanPickSoulHearts()` 返回布尔（降级给 `false` 并记探针）、
//   `AddFriendlyDip()` 返回 `EntityFamiliar`（与批次 273 的 `AddBlueSpider` 同一口径：压句柄
//   或 `nil`）。

// `Entity:AddFear(EntityRef Source, int Duration)` —— PC 契约
// `tools/pc_contract_docs/Entity.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityAddFearOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityAddFear(lua_State* state) {
    if (lua_gettop(state) != 3 || !IsIntegerArgument(state, 3)) {
        return luaL_error(state, "Entity:AddFear expects (EntityRef, Duration); got %d argument(s)",
                          lua_gettop(state) - 1);
    }
    const void* reference = EntityRefBufferAt(state, 2);
    if (reference == nullptr) {
        return luaL_error(state, "Entity:AddFear expects an EntityRef as its first argument");
    }
    const std::int32_t duration = static_cast<std::int32_t>(lua_tointegerx(state, 3, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:AddFear");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityAddFearOffset,
                                                            kEntityAddFearExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityAddFearFn = void (*)(std::uintptr_t, const void*, std::int32_t);
    engine_call::AsFunction<EntityAddFearFn>(method)(entity, reference, duration);
    return 0;
}

// `Entity:AddHealth(float HitPoints)` —— PC 契约
// `tools/pc_contract_docs/Entity.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityAddHealthOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityAddHealth(lua_State* state) {
    if (lua_gettop(state) != 2 || !lua_isnumber(state, 2)) {
        return luaL_error(state, "Entity:AddHealth expects a number; got %d argument(s)",
                          lua_gettop(state) - 1);
    }
    const float argument = static_cast<float>(lua_tonumber(state, 2));
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:AddHealth");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityAddHealthOffset,
                                                            kEntityAddHealthExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityAddHealthFn = void (*)(std::uintptr_t, float);
    engine_call::AsFunction<EntityAddHealthFn>(method)(entity, argument);
    return 0;
}

// `Entity:RemoveStatusEffects()` —— PC 契约
// `tools/pc_contract_docs/Entity.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityRemoveStatusEffectsOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityRemoveStatusEffects(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Entity:RemoveStatusEffects accepts no arguments; got %d",
                          lua_gettop(state) - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "Entity:RemoveStatusEffects");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityRemoveStatusEffectsOffset,
                                                            kEntityRemoveStatusEffectsExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityRemoveStatusEffectsFn = void (*)(std::uintptr_t);
    engine_call::AsFunction<EntityRemoveStatusEffectsFn>(method)(entity);
    return 0;
}

// `EntityPlayer:AddBoneHearts(int Hearts)` —— PC 契约
// `tools/pc_contract_docs/EntityPlayer.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityPlayerAddBoneHeartsOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityPlayerAddBoneHearts(lua_State* state) {
    if (lua_gettop(state) != 2 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state, "EntityPlayer:AddBoneHearts expects an integer; got %d argument(s)",
                          lua_gettop(state) - 1);
    }
    const std::int32_t argument = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddBoneHearts");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddBoneHeartsOffset,
                                                            kEntityPlayerAddBoneHeartsExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityPlayerAddBoneHeartsFn = void (*)(std::uintptr_t, std::int32_t);
    engine_call::AsFunction<EntityPlayerAddBoneHeartsFn>(method)(entity, argument);
    return 0;
}

// `EntityPlayer:AddFriendlyDip(int Subtype, Vector Position)` —— PC 契约
// `tools/pc_contract_docs/EntityPlayer.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityPlayerAddFriendlyDipOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityPlayerAddFriendlyDip(lua_State* state) {
    if (lua_gettop(state) != 3 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state, "EntityPlayer:AddFriendlyDip expects (int Subtype, Vector); got %d argument(s)",
                          lua_gettop(state) - 1);
    }
    VectorHandle* position = VectorArgument(state, 3);
    if (position == nullptr) {
        return luaL_error(state, "EntityPlayer:AddFriendlyDip expects a Vector position");
    }
    const std::int32_t subtype = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddFriendlyDip");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddFriendlyDipOffset,
                                                            kEntityPlayerAddFriendlyDipExpectedBytes);
    if (entity == 0 || method == 0) {
        PushNil(state);
        return 1;
    }
    using EntityPlayerAddFriendlyDipFn = std::uintptr_t (*)(std::uintptr_t, std::int32_t, const VectorHandle*);
    const std::uintptr_t created = engine_call::AsFunction<EntityPlayerAddFriendlyDipFn>(method)(entity, subtype, position);
    if (created == 0) {
        PushNil(state);
        return 1;
    }
    PushEntityHandle(state, created, kEntityFamiliarMetatable);
    return 1;
}

// `EntityPlayer:AddPrettyFly()` —— PC 契约
// `tools/pc_contract_docs/EntityPlayer.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityPlayerAddPrettyFlyOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityPlayerAddPrettyFly(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:AddPrettyFly accepts no arguments; got %d",
                          lua_gettop(state) - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AddPrettyFly");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAddPrettyFlyOffset,
                                                            kEntityPlayerAddPrettyFlyExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityPlayerAddPrettyFlyFn = void (*)(std::uintptr_t);
    engine_call::AsFunction<EntityPlayerAddPrettyFlyFn>(method)(entity);
    return 0;
}

// `EntityPlayer:AnimateTrapdoor()` —— PC 契约
// `tools/pc_contract_docs/EntityPlayer.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityPlayerAnimateTrapdoorOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityPlayerAnimateTrapdoor(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:AnimateTrapdoor accepts no arguments; got %d",
                          lua_gettop(state) - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:AnimateTrapdoor");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerAnimateTrapdoorOffset,
                                                            kEntityPlayerAnimateTrapdoorExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityPlayerAnimateTrapdoorFn = void (*)(std::uintptr_t);
    engine_call::AsFunction<EntityPlayerAnimateTrapdoorFn>(method)(entity);
    return 0;
}

// `EntityPlayer:CanPickSoulHearts()` —— PC 契约
// `tools/pc_contract_docs/EntityPlayer.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityPlayerCanPickSoulHeartsOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityPlayerCanPickSoulHearts(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:CanPickSoulHearts accepts no arguments; got %d",
                          lua_gettop(state) - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:CanPickSoulHearts");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerCanPickSoulHeartsOffset,
                                                            kEntityPlayerCanPickSoulHeartsExpectedBytes);
    if (entity == 0 || method == 0) {
        //: 布尔型降级给 `false`（= 「不能捡」，保守的那一边），并按纪律记一笔探针。
        return PushNativeFallbackBoolean(state, kFbEntityPlayerCanPickSoulHearts, false);
    }
    using EntityPlayerCanPickSoulHeartsFn = bool (*)(std::uintptr_t);
    lua_pushboolean(state, engine_call::AsFunction<EntityPlayerCanPickSoulHeartsFn>(method)(entity) ? 1 : 0);
    return 1;
}

// `EntityPlayer:IsHoldingItem()` —— PC 契约 `tools/pc_contract_docs/EntityPlayer.md`，语料 2 处。
// 引擎入口 `Entity_Player::IsHoldingItem() const` @ `0x2929D0`（arity 0 ✓ = 契约那 0 个参数；
// **只有一份实现** —— 用"扫全镜像 mangled 名字"核实过，见 `runtime_constants.hpp` 批次 284 段）。
// 降级：拿不到实体（句柄失效）或入口对不上 ⇒ 给 `false`（"没拿着东西"是保守的那一边）并记探针。
int EntityPlayerIsHoldingItem(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:IsHoldingItem accepts no arguments; got %d",
                          lua_gettop(state) - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:IsHoldingItem");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerIsHoldingItemOffset,
                                                             kEntityPlayerIsHoldingItemExpectedBytes);
    if (entity == 0 || method == 0) {
        return PushNativeFallbackBoolean(state, kFbEntityPlayerIsHoldingItem, false);
    }
    using EntityPlayerIsHoldingItemFn = bool (*)(std::uintptr_t);
    lua_pushboolean(state,
                    engine_call::AsFunction<EntityPlayerIsHoldingItemFn>(method)(entity) ? 1 : 0);
    return 1;
}

// `EntityPlayer:IsExtraAnimationFinished()` —— 同上契约页，语料 1 处。
// 引擎入口 `Entity_Player::IsExtraAnimationFinished() const` @ `0x2B78C4`（arity 0 ✓，只有一份实现）。
// ★ 它的起点是**裸代码**（`mov w8,#0x1710; add x8,x0,x8; ldrb w9,[x8]…`）—— 靠"前一条指令是别的
//   函数的 `bl`"确认了 0x2B78C4 是函数头（不是中段），证据写在 `runtime_constants.hpp` 那一段。
int EntityPlayerIsExtraAnimationFinished(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state,
                          "EntityPlayer:IsExtraAnimationFinished accepts no arguments; got %d",
                          lua_gettop(state) - 1);
    }
    const std::uintptr_t entity =
        EntityReceiverOrError(state, "EntityPlayer:IsExtraAnimationFinished");
    const std::uintptr_t method =
        EntityMethodByExpectedBytes(kEntityPlayerIsExtraAnimationFinishedOffset,
                                    kEntityPlayerIsExtraAnimationFinishedExpectedBytes);
    if (entity == 0 || method == 0) {
        return PushNativeFallbackBoolean(state, kFbEntityPlayerIsExtraAnimationFinished, false);
    }
    using EntityPlayerIsExtraAnimationFinishedFn = bool (*)(std::uintptr_t);
    lua_pushboolean(state, engine_call::AsFunction<EntityPlayerIsExtraAnimationFinishedFn>(method)(
                               entity) ?
                              1 :
                              0);
    return 1;
}

// `EntityPlayer:DonateLuck(int Luck)` —— PC 契约
// `tools/pc_contract_docs/EntityPlayer.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityPlayerDonateLuckOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityPlayerDonateLuck(lua_State* state) {
    if (lua_gettop(state) != 2 || !IsIntegerArgument(state, 2)) {
        return luaL_error(state, "EntityPlayer:DonateLuck expects an integer; got %d argument(s)",
                          lua_gettop(state) - 1);
    }
    const std::int32_t argument = static_cast<std::int32_t>(lua_tointegerx(state, 2, nullptr));
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:DonateLuck");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerDonateLuckOffset,
                                                            kEntityPlayerDonateLuckExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityPlayerDonateLuckFn = void (*)(std::uintptr_t, std::int32_t);
    engine_call::AsFunction<EntityPlayerDonateLuckFn>(method)(entity, argument);
    return 0;
}

// `EntityPlayer:RemoveGoldenBomb()` —— PC 契约
// `tools/pc_contract_docs/EntityPlayer.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityPlayerRemoveGoldenBombOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityPlayerRemoveGoldenBomb(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:RemoveGoldenBomb accepts no arguments; got %d",
                          lua_gettop(state) - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:RemoveGoldenBomb");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerRemoveGoldenBombOffset,
                                                            kEntityPlayerRemoveGoldenBombExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityPlayerRemoveGoldenBombFn = void (*)(std::uintptr_t);
    engine_call::AsFunction<EntityPlayerRemoveGoldenBombFn>(method)(entity);
    return 0;
}

// `EntityPlayer:RemoveGoldenKey()` —— PC 契约
// `tools/pc_contract_docs/EntityPlayer.md`，语料 1 处。引擎入口见 `runtime_constants.hpp` 的
// `kEntityPlayerRemoveGoldenKeyOffset` 段（选批口径与守卫来源写在那一段的开头）。
int EntityPlayerRemoveGoldenKey(lua_State* state) {
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "EntityPlayer:RemoveGoldenKey accepts no arguments; got %d",
                          lua_gettop(state) - 1);
    }
    const std::uintptr_t entity = EntityReceiverOrError(state, "EntityPlayer:RemoveGoldenKey");
    const std::uintptr_t method = EntityMethodByExpectedBytes(kEntityPlayerRemoveGoldenKeyOffset,
                                                            kEntityPlayerRemoveGoldenKeyExpectedBytes);
    if (entity == 0 || method == 0) {
        return 0;  // 降级：什么都不做、不报错（PC 的返回类型是 void）
    }
    using EntityPlayerRemoveGoldenKeyFn = void (*)(std::uintptr_t);
    engine_call::AsFunction<EntityPlayerRemoveGoldenKeyFn>(method)(entity);
    return 0;
}

// `Entity::TakeDamage` / `Entity_Player::TakeDamage` 的取址助手：与 `HasCollectibleMethod`
// 同一种接法（模块基址 + 偏移 + 可读性检查），并保持"常量出现在助手体内、结果经局部变量交给
// 调用点"这个形状 —— ABI 体检（`tools/engine_offset_abi_report.py`）靠这条链把常量与我们声明的
// 签名对上；写成别的形状它就读不出来（批次 065 实测过一次）。
std::uintptr_t EntityTakeDamageMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityTakeDamageOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityTakeDamageOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

std::uintptr_t EntityPlayerTakeDamageMethod() noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kEntityPlayerTakeDamageOffset) {
        return 0;
    }
    const std::uintptr_t method = base + kEntityPlayerTakeDamageOffset;
    return IsEngineMemoryReadable(method, sizeof(std::uint32_t)) ? method : 0;
}

// 批次 271 三条共同的取址助手（形状与上面两个同源，只是把守卫从 4 字节换成 **16 字节入口原文**）：
// 那三条在 API 清单里本来就带着 16 字节守卫，用整份原文比只比首个指令字强得多
// （`test_runtime_constants_against_nro` 还会把这三个数组与镜像逐字节对账 —— 批次 269 就是靠它
// 抓到我手抄错的一个字节）。
std::uintptr_t EntityMethodByExpectedBytes(std::uintptr_t offset,
                                           const std::array<u8, 16>& expected) noexcept {
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - offset) {
        return 0;
    }
    const std::uintptr_t method = base + offset;
    if ((method & 3) != 0 || !IsEngineMemoryReadable(method, expected.size())) {
        return 0;
    }
    if (engine_call::VerifyEntryBytes(method, expected.data(), expected.size(),
                                      &IsEngineMemoryReadable)) return method;
#if defined(__SWITCH__)
    // 只为这三条已知公开使用入口取登记记录；其它陌生字节继续拒绝。
    std::uintptr_t fallback = 0;
    if (offset == kEntityPlayerUseActiveItemOffset)
        fallback = EntryRelayFallbackEntry(HookId::UseActiveItem);
    else if (offset == kEntityPlayerUseCardOffset)
        fallback = EntryRelayFallbackEntry(HookId::UseCard);
    else if (offset == kEntityPlayerUsePillOffset)
        fallback = EntryRelayFallbackEntry(HookId::UsePill);
    else if (offset == kEntityPlayerEvaluateItemsOffset)
        fallback = EntryRelayFallbackEntry(HookId::EvaluateItems);
    if (fallback != 0 && VerifiedHookedEngineEntry(method, expected, true, fallback,
                                                   &IsEngineMemoryReadable)) return method;
#endif
    return 0;
}

std::uintptr_t EntitySetColorMethod() noexcept {
    return EntityMethodByExpectedBytes(kEntitySetColorOffset, kEntitySetColorExpectedBytes);
}

std::uintptr_t EntityAddCharmedMethod() noexcept {
    return EntityMethodByExpectedBytes(kEntityAddCharmedOffset, kEntityAddCharmedExpectedBytes);
}

std::uintptr_t EntityPlayerUseActiveItemMethod() noexcept {
    return EntityMethodByExpectedBytes(kEntityPlayerUseActiveItemOffset,
                                       kEntityPlayerUseActiveItemExpectedBytes);
}


std::size_t AttachIsaacMethods(lua_State* state) noexcept {
    return AttachApi700Methods(state,"Isaac") + AttachOwnerMethods(state, kIsaacOwner, kIsaacHandlers, RowCount(kIsaacHandlers));
}

//: 批次 063：`Entity` 族的**引擎方法数据行**（机制与成本说明见 `engine_method_api.hpp`）。
//: `EntityPlayer` 会继承基类方法（`IndexEntity()` 的回落），所以挂在基类上就够了。
constexpr EngineMethodRow kEntityEngineRows[] = {
    // `Entity:IsFlying()`：GoodTrip 的诅咒房判定（`trip.lua:90`）要用它。
    {0x0E01002E, kEntityIsFlyingOffset, kEntityIsFlyingEntryWord, FieldReceipt::Entity,
     EngineCallShape::Bool0, 0, 0xFF},
    // `Entity:IsActiveEnemy([bool includeDead])`（批次 207，2026-09-29）：MCM 的 `RoomIsSafe()`
    // 用它判"房间里有没有活敌人"（`modconfig.lua:206`，不传参；`RepentancePlus` 传 `false`）。
    // ★ 形状是 `BoolOpt1` 而不是 `Bool1`：尾部参数**可以省略**，省略时 `x1` 保持 0
    //   = `includeDead == false` = PC 的缺省值（反汇编里引擎自己不给缺省，见
    //   `runtime_constants.hpp` 的 `kEntityIsActiveEnemyOffset`）。
    {0x0E010060, kEntityIsActiveEnemyOffset, kEntityIsActiveEnemyEntryWord, FieldReceipt::Entity,
     EngineCallShape::BoolOpt1, 1, 0xFF},
    // ---- 批次 238：`Entity:IsBoss`（boolean IsBoss ( )）
    // 符号 `_ZNK15IsaacRepentance6Entity6IsBossEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    // ★★ 批次 319（2026-10-03）**改走虚调用**：PC 那条绑定（`0x86051B`）落在
    //    `mov eax,[ecx]; jmp [eax+0x48]` 跳板表里 ⇒ 它是**虚函数**（Switch 槽 19）。
    //    `Entity_NPC::IsBoss` 有覆盖 ⇒ 直调基类会跳过它。取证见 `runtime_constants.hpp` 的批次 319 段。
    {0x0E010067, MakeEngineVtableRowOffset(kEntityVtableIsBossSlot), 0, FieldReceipt::Entity,
     EngineCallShape::Bool0, 0, 0xFF},
    // ---- 批次 238：`Entity:IsEnemy`（boolean IsEnemy ( )）
    // 符号 `_ZNK15IsaacRepentance6Entity7IsEnemyEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    // ★ 批次 319 复核：PC 绑定（`0x684620`）**不在**跳板表里、Switch 的 vtable 里也没有 `IsEnemy` 槽
    //   ⇒ 它**不是**虚函数，直调是对的（同批四条里唯一不用改的一条）。
    {0x0E010068, kEntityIsEnemyOffset, kEntityIsEnemyEntryWord, FieldReceipt::Entity,
     EngineCallShape::Bool0, 0, 0xFF},
    // ---- 批次 238：`Entity:Kill`（void Kill ( )）
    // 符号 `_ZN15IsaacRepentance6Entity4KillEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    // ★★ 批次 319 **改走虚调用**：PC 绑定 `0x8604FD` = `mov eax,[ecx]; jmp [eax+0x24]`（跳板表）
    //    ⇒ 虚函数（Switch 槽 10）。`Entity_Familiar::Kill` 与 `Entity_NPC::Kill` 各有覆盖。
    {0x0E010069, MakeEngineVtableRowOffset(kEntityVtableKillSlot), 0, FieldReceipt::Entity,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 238：`Entity:Remove`（void Remove ( )）
    // 符号 `_ZN15IsaacRepentance6Entity6RemoveEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    // ★★ 批次 319 **改走虚调用**：PC 绑定 `0x860511` = `mov eax,[ecx]; jmp [eax+0x28]`（跳板表）
    //    ⇒ 虚函数（Switch 槽 11）。`Entity_Familiar::Remove` / `Entity_Pickup::Remove` 各有覆盖。
    {0x0E01006A, MakeEngineVtableRowOffset(kEntityVtableRemoveSlot), 0, FieldReceipt::Entity,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 238：`Entity:Update`（void Update ( )）
    // 符号 `_ZN15IsaacRepentance6Entity6UpdateEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    // ★★★ 批次 319 **改走虚调用** —— 四条里影响最大的一条：`Update` 在**每一个** `Entity` 派生类里
    //    都被覆盖（`Entity_Player`/`Entity_NPC`/`Entity_Tear`/`Entity_Bomb`…，`--find-all Update` 能看到），
    //    直调基类等于"手动更新实体"只做了基类那一半。PC 绑定 `0x860520` = `jmp [eax+0xc]`（跳板表）
    //    ⇒ 虚函数（Switch 槽 4）。
    {0x0E01006B, MakeEngineVtableRowOffset(kEntityVtableUpdateSlot), 0, FieldReceipt::Entity,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 286：`Entity:IsVulnerableEnemy`（boolean IsVulnerableEnemy ( )）★ 22 处，最大单条
    // 引擎符号 `_ZNK15IsaacRepentance6Entity17IsVulnerableEnemyEPS0_` @ `0x5C62C` —— **比契约多一个
    // `Entity*` 形参**。那个形参是"来源实体"，并且**只在非空时才被解引用**；PC 那个无参 Lua 重载
    // 传下去的就是**空指针**（取证链条写在 `runtime_constants.hpp` 的批次 286 段：PC 包装 `0x7FAE70`
    // 读 Lua 栈第 2 格、契约与官方示例都是 0 参 ⇒ 那格恒为 nil ⇒ 传 0）。
    // ★ 形状仍取 `Bool0`（`bool(this)`、0 个参数）是**故意**的：共享处理器把参数数组整块零初始化、
    //   只搬实际给出的参数 ⇒ 省略的 `x1` 保持 0，正好就是 PC 的缺省值。
    //   ⇒ 不需要新形状、0 字节代码；ABI 体检会报 `under`，理由登记在
    //   `tools/engine_abi_triage.json`（"引擎那个参数可以传 0 且我们的跳板会把寄存器清零"）。
    {0x0E0100C2, kEntityIsVulnerableEnemyOffset, kEntityIsVulnerableEnemyEntryWord,
     FieldReceipt::Entity, EngineCallShape::Bool0, 0, 0xFF},
    // ---- 批次 303（2026-10-03）：**第一条"按 vtable 槽号调用"的行** ----
    // `Entity:CanShutDoors()`（3 处 / 1 个模组）—— PC 契约 `Entity.md` 的 88 行。
    // ★ 它是**虚函数**：PC 的绑定本体不调某一个具体函数，而是
    //   `mov eax,[ecx]; jmp [eax+0x44]`（那张跳板表在 PC 镜像 `0x8604E0` 起）。
    //   ⇒ 哪一条实现要**看接收者的动态类型**（`Entity` 与 `Entity_NPC` 各有自己的实现，
    //     实测两者在各自的 `_ZTV` 里都占**同一个槽 18**）⇒ 必须按槽调，直调基类会**跳过子类行为**。
    // ★ 槽号从 **Switch 的 `_ZTVEntity`** 读出来（`vtable + 0x10 + 18*8`，靠 `R_AARCH64_ABS64`
    //   重定位 + 符号索引解），**不许照抄 PC 的**（PC 是第 17 条 —— 两边差一个析构槽）。
    //   取证与"怎么读"见 `runtime_constants.hpp` 的批次 303 段。
    // ★ 这种行**没有入口指纹**（目标运行期才知道）⇒ `entryWord` 写 0，处理器也不核它；
    //   护栏改成"两级指针可读 + 槽号有上界"，失败记 `EngineRowRejectReason::Vtable`。
    {0x0E0100D3, MakeEngineVtableRowOffset(kEntityVtableCanShutDoorsSlot), 0,
     FieldReceipt::Entity, EngineCallShape::Bool0, 0, 0xFF},
};
static_assert(RowCount(kEntityEngineRows) == 9,
              "行数与 id 段（0x002E + 0x0060 + 0x00C2 + 0x00D3）要一起改");

std::size_t AttachEntityMethods(lua_State* state) noexcept {
    // 批次 207：`Entity` 从这一批起也有了**字段行**（`Entity:HasEntityFlags(int)`，
    // 行在 `kFieldApis` 里）。`AttachOwnerMethods` 按 id 匹配，所以把整张表传进来没问题 ——
    // 不属于 `Entity` owner 的行自然一处也挂不上。
    std::size_t fieldApiCount = 0;
    const FieldApiRow* fieldApiRows = FieldApiRows(&fieldApiCount);
    return AttachApi700Methods(state,"Entity") + AttachApi400Methods(state,"Entity") + AttachApi200Methods(state,"Entity") + AttachApi100Methods(state,"Entity") + AttachRPlusMethods(state,"Entity") + AttachOwnerMethods(state, kEntityOwner, kEntityHandlers, RowCount(kEntityHandlers),
                              fieldApiRows, fieldApiCount, kEntityEngineRows,
                              RowCount(kEntityEngineRows));
}

//: 批次 051：`EntityPlayer` 的**引擎方法数据行**（机制与成本说明见 `engine_method_api.hpp`）。
//: 每个 API 只占这里 **16 字节只读数据、0 字节代码** —— 这就是"以后陆续实现 API
//: 不再撞代码段预算"的落点（老写法每条 ≈490 字节代码）。
constexpr EngineMethodRow kEntityPlayerEngineRows[] = {
    // 0x0056 `AddCoins(int)`（原手写实现已删，改走共享处理器）
    {0x0E010056, kEntityPlayerAddCoinsOffset, kEntityPlayerAddCoinsEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Void1, 1, 0xFF},
    // 0x0057 `SetShootingCooldown(int)`（GoodTrip"开地图后按方向键"那条路要用）
    {0x0E010057, kEntityPlayerSetShootingCooldownOffset, kEntityPlayerSetShootingCooldownEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Void1, 1, 0xFF},
    // 0x0058 / 0x0059 `AnimateHappy()` / `AnimateSad()`（GoodTrip 传送成功/失败时各一次）
    {0x0E010058, kEntityPlayerAnimateHappyOffset, kEntityPlayerAnimateHappyEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Void0, 0, 0xFF},
    {0x0E010059, kEntityPlayerAnimateSadOffset, kEntityPlayerAnimateSadEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Void0, 0, 0xFF},
    // 0x005A `GetBlackHearts()`（PC 名字）→ 引擎符号 `GetNumBlackHearts()`（const）
    {0x0E01005A, kEntityPlayerGetNumBlackHeartsOffset, kEntityPlayerGetNumBlackHeartsEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Int0, 0, 0xFF},
    // 0x005B `AddNullCostume(int NullId)`（批次 137，The Specialist for Good Items 的舞蹈段落要用）；
    // 引擎符号 `Entity_Player::AddNullCostume(ItemConfig::eNullItemID)` @ `0x291BBC`。
    // ABI 是 `void(this, i32)` ⇒ 复用 `Void1` 的寄存器形状；**但批次 141 起换成 `VoidNullId1`**：
    // 编号无效时引擎 `GetNullItem(id)` 拿到空 ⇒ `AddCostume(nullptr)` 解引用空指针
    // （2026-09-26 真机 `Data Abort`、`Address = 0`）⇒ 这一形状让共享处理器先把这种调用挡下。
    {0x0E01005B, kEntityPlayerAddNullCostumeOffset, kEntityPlayerAddNullCostumeEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::VoidNullId1, 1, 0xFF},
    // 0x005C `TryRemoveNullCostume(int NullId)`（批次 137，同一模组的"摘掉临时服装"那一半）；
    // 引擎符号 `Entity_Player::TryRemoveCostume(ItemConfig::eNullItemID)` @ `0x2F2170`
    // （`Entity_Player` 下三条 `TryRemoveCostume` 重载里 `eNullItemID` 那条，签名逐条对上）。
    // 同族、同风险（走同一个 null 服装容器）⇒ 同一形状、同一道校验。
    {0x0E01005C, kEntityPlayerTryRemoveNullCostumeOffset, kEntityPlayerTryRemoveNullCostumeEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::VoidNullId1, 1, 0xFF},
    // ---- 批次 177（2026-09-28）：审查第 3 遍那 5 条"引擎里有同名成员、我们却恒返回假值"的桩 ----
    // 从"手写假桩"换成这里的数据行：**每个 API 只花 16 字节只读数据、0 字节代码**，
    // 而且值来自引擎自己（不再是保守常量）。偏移/指纹/签名的逐条证据在 `runtime_constants.hpp`。
    // 0x0030 `GetPill(int)`（EID `features/eid_api.lua:2606` 逐帧调用）
    {0x0E010030, kEntityPlayerGetPillOffset, kEntityPlayerGetPillEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Int1, 1, 0xFF},
    // 0x0031 `GetCard(int)`（与 GetPill 成对，EID `eid_data.lua:91-116`）
    {0x0E010031, kEntityPlayerGetCardOffset, kEntityPlayerGetCardEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Int1, 1, 0xFF},
    // 0x0040 `GetZodiacEffect()`（PC `EntityPlayer.md:1341`；无参、返回整数 ⇒ 复用 Int0）
    {0x0E010040, kEntityPlayerGetZodiacEffectOffset, kEntityPlayerGetZodiacEffectEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Int0, 0, 0xFF},
    // 0x004B `HasPlayerForm(Form)`（PC `EntityPlayer.md:1382`；一个整数参数、返回布尔 ⇒ Bool1）
    {0x0E01004B, kEntityPlayerHasPlayerFormOffset, kEntityPlayerHasPlayerFormEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Bool1, 1, 0xFF},
    // 0x004C `CanPickRedHearts()`（PC `EntityPlayer.md:550`；无参、返回布尔 ⇒ Bool0）。
    // 真实调用点 = EID `features/eid_itemprediction.lua:366`（恒 false 会让"满红心"那一支永不成立）。
    {0x0E01004C, kEntityPlayerCanPickRedHeartsOffset, kEntityPlayerCanPickRedHeartsEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Bool0, 0, 0xFF},
    // 0x0042 `GetGlyphOfBalanceDrop(variant, subtype)`（★ PC 契约文档里**查不到**这条 ——
    //   它是 Repentogon 才有的 API；形状的唯一口径 = 消费者 EID：
    //   `features/eid_repentogon.lua:265` 收 2 个整数、读返回的 `t[1]`/`t[2]`）。
    //   引擎签名 `void(this, u32& 入出参, u32& 入出参)` ⇒ 批次 184 新增的 `Ref2U32Pair`
    //   （Lua 侧仍当"2 个整数参数"收，返回一张两元表）。**原手写"恒 0"桩已删**。
    {0x0E010042, kEntityPlayerGetGlyphOfBalanceDropOffset,
     kEntityPlayerGetGlyphOfBalanceDropEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Ref2U32Pair, 2, 0xFF},
    // ---- 批次 238：`EntityPlayer:AddBrokenHearts`（void AddBrokenHearts ( int BrokenHearts )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player15AddBrokenHeartsEi`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E01006C, kEntityPlayerAddBrokenHeartsOffset, kEntityPlayerAddBrokenHeartsEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void1, 1, 0xFF},
    // ---- 批次 238：`EntityPlayer:AddCard`（void AddCard ( [Card](enums/Card.md) ID )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player7AddCardENS_5eCardE`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E01006D, kEntityPlayerAddCardOffset, kEntityPlayerAddCardEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void1, 1, 0xFF},
    // ---- 批次 238：`EntityPlayer:AddEternalHearts`（void AddEternalHearts ( int EternalHearts )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player16AddEternalHeartsEi`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E01006E, kEntityPlayerAddEternalHeartsOffset, kEntityPlayerAddEternalHeartsEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void1, 1, 0xFF},
    // ---- 批次 238：`EntityPlayer:AddHearts`（void AddHearts ( int Hearts )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player9AddHeartsEib`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E01006F, kEntityPlayerAddHeartsOffset, kEntityPlayerAddHeartsEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::VoidIntBoolOpt1, 2, 0xFF},
    // ---- 批次 238：`EntityPlayer:AddTrinket`（void AddTrinket ( [TrinketType](enums/TrinketType.md) Type, boolean FirstTimePickingUp = true )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player10AddTrinketENS_12eTrinketTypeEb`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    // 2026-10-31更正：PC main.lua:853-857补省略/nil为true，第二参不能按必填整数解析。
    {0x0E010070, kEntityPlayerAddTrinketOffset, kEntityPlayerAddTrinketEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::VoidIntBoolDefaultTrueOpt1, 2, 0xFF},
    // ---- 批次 238：`EntityPlayer:EvaluateItems`（void EvaluateItems ( )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player13EvaluateItemsEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E010071, kEntityPlayerEvaluateItemsOffset, kEntityPlayerEvaluateItemsEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 238：`EntityPlayer:GetExtraLives`（int GetExtraLives ( )）
    // 符号 `_ZNK15IsaacRepentance13Entity_Player13GetExtraLivesEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E010072, kEntityPlayerGetExtraLivesOffset, kEntityPlayerGetExtraLivesEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Int0, 0, 0xFF},
    // ---- 批次 238：`EntityPlayer:NeedsCharge`（boolean NeedsCharge ( [ActiveSlot](enums/ActiveSlot.md) ActiveSlot = ActiveSlot.SLOT_PRIMARY )）
    // 符号 `_ZNK15IsaacRepentance13Entity_Player11NeedsChargeEi`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E010073, kEntityPlayerNeedsChargeOffset, kEntityPlayerNeedsChargeEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Bool1, 1, 0xFF},
    // ---- 批次 238：`EntityPlayer:Revive`（void Revive ( )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player6ReviveEv`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E010074, kEntityPlayerReviveOffset, kEntityPlayerReviveEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 238：`EntityPlayer:SetActiveCharge`（void SetActiveCharge ( int Charge, [ActiveSlot](enums/ActiveSlot.md) ActiveSlot = ActiveSlot.SLOT_PRIMARY )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player15SetActiveChargeEii`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E010075, kEntityPlayerSetActiveChargeOffset, kEntityPlayerSetActiveChargeEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void2, 2, 0xFF},
    // ---- 批次 238：`EntityPlayer:SetCard`（void SetCard ( int SlotId, [Card](enums/Card.md) ID )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player7SetCardEiNS_5eCardE`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E010076, kEntityPlayerSetCardOffset, kEntityPlayerSetCardEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void2, 2, 0xFF},
    // ---- 批次 238：`EntityPlayer:TryRemoveTrinket`（boolean TryRemoveTrinket ( [TrinketType](enums/TrinketType.md) Type )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player16TryRemoveTrinketENS_12eTrinketTypeE`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E010077, kEntityPlayerTryRemoveTrinketOffset, kEntityPlayerTryRemoveTrinketEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Bool1, 1, 0xFF},
    // ---- 批次 341（2026-10-04）：`EntityPlayer:TryRemoveTrinketCostume(TrinketType)`（1 处 / 1 个模组）----
    // PC 契约 `tools/pc_contract_docs/EntityPlayer.md:1838`：`void TryRemoveTrinketCostume ( TrinketType Trinket )`。
    // 引擎符号表里**没有** `TryRemoveTrinketCostume`（引擎按类型分派到同族的 `TryRemoveCostume` 重载）；
    // 三个重载里 `(eTrinketType)` 那条 @ `0x2A25B0` 与契约逐参对应 ⇒ 形状 = `Void1`（`void(this, i32)`），
    // 接收者 = `FieldReceipt::EntityPlayer`。★ 与上一条 `TryRemoveTrinket`（`Bool1`，返回 bool）**不同形状**：
    // 这条返回 `void`。★ 先例：`TryRemoveNullCostume` 用的就是同族另一条重载（`0x2F2170`，`VoidNullId1`）；
    // 本条**不需要** null-id 校验（饰品编号走 `GetTrinket`，不是 `GetNullItem` 那样会拿到空指针的容器）。
    // 逐条证据与保留项（PC 胶水多一层容器调用 ⇒ 挂真机项）见 `runtime_constants.hpp` 的批次 341 段。
    {0x0E0100EF, kEntityPlayerTryRemoveTrinketCostumeOffset,
     kEntityPlayerTryRemoveTrinketCostumeEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void1, 1, 0xFF},
    // ---- 批次 238：`EntityPlayer:UseCard`（void UseCard ( [Card](enums/Card.md) ID, [UseFlags](enums/UseFlag.md) UseFlags = 0 )）
    // 符号 `_ZN15IsaacRepentance13Entity_Player7UseCardENS_5eCardEj`；形状按符号参数表取（见 `runtime_constants.hpp` 的批次 238 段）。
    {0x0E010078, kEntityPlayerUseCardOffset, kEntityPlayerUseCardEntryWord, FieldReceipt::EntityPlayer,
     EngineCallShape::Void2, 2, 0xFF},
    // ---- 批次 252（2026-10-01）：`EntityPlayer:RemoveCollectible`
    //   （void RemoveCollectible ( CollectibleType Type, boolean IgnoreModifiers = false,
    //    ActiveSlot = ActiveSlot.SLOT_PRIMARY, boolean RemoveFromPlayerForm = true )）
    // PC 契约 `tools/pc_contract_docs/EntityPlayer.md:1588`。
    // ★ 引擎符号 4 格（`…eCollectibleTypeEbib`）而**语料只传 1 个**
    //   （`IsaacOnTwitchReloaded/scripts/activeItems.lua` 的 8 处 `p:RemoveCollectible(id)`）
    //   ⇒ 形状 `VoidIntBoolIntBoolOpt3`（尾部 3 个可省；PC脚本缺省语义见形状表，
    //   而第 3 格的缺省 `ActiveSlot.SLOT_PRIMARY` 恰好是 0）。
    // ★★ 清单把它记成 `ItemPool:RemoveCollectible`（同名、另一个 owner）—— 语料里的接收者
    //   是 **EntityPlayer**，按 owner 认才不会做错（见批次 250 的"按 owner 区分"纪律）。
    {0x0E010084, kEntityPlayerRemoveCollectibleOffset, kEntityPlayerRemoveCollectibleEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::VoidIntBoolIntBoolOpt3, 4, 0xFF},
    // ---- 批次 254（2026-10-01）：`EntityPlayer` 三条"形状与接收者都现成"的语料缺口 ----
    // ★★ 这三条在工作清单里被记成 `needs_new_receiver`（"差接收者视图"）——**那是误判**：
    //   清单的桶来自库存工具的 `thunk_readiness=needs_owner_instance`，而那个字段只认 7 个
    //   可达类（`Game`/`Level`/`Room`/`ItemPool`/`MusicManager`/`Manager`/`Music`），
    //   **`EntityPlayer` 不在其中** ⇒ 凡是 owner 是 `Entity`/`EntityPlayer` 的都落进这桶。
    //   实际 `FieldReceipt::EntityPlayer` 早已存在、这些形状也全是现成的 ⇒ 它们是**零成本数据行**。
    //   （判据：本文件上方 27 行同族数据行就是同一个接收者。）
    // 0x0085 `AddKeys(int Amount)`（PC `EntityPlayer.md:295`；负数表示移除）
    {0x0E010085, kEntityPlayerAddKeysOffset, kEntityPlayerAddKeysEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Void1, 1, 0xFF},
    // 0x0086 `AddGoldenKey()`（PC `EntityPlayer.md:262`；无参）
    {0x0E010086, kEntityPlayerAddGoldenKeyOffset, kEntityPlayerAddGoldenKeyEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Void0, 0, 0xFF},
    // 0x0087 `AddGoldenBomb()`（PC `EntityPlayer.md:244`；无参）
    {0x0E010087, kEntityPlayerAddGoldenBombOffset, kEntityPlayerAddGoldenBombEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 288（2026-10-02）：`EntityPlayer:GetMovementDirection()` ----
    // 契约 `EntityPlayer.md:1096` 是 `Direction GetMovementDirection ( )`（0 参）。
    // ★ 引擎符号是**小写加下划线**的 `Entity::get_movement_direction() const` @ `0x5C8AC`
    //   （不是 `GetMovementDirection` ⇒ 按名字精确匹配会得 0，这是"名字风格"的又一例）；
    //   它读 `Entity+0x334`/`+0x338` 两个 float，用**与带参重载逐条相同**的算法化成
    //   `eDirection` 后返回 int ⇒ 值域与 PC 的 `Direction` 表逐个相等，直接返回即可。
    {0x0E0100C8, kEntityGetMovementDirectionOffset, kEntityGetMovementDirectionEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::Int0, 0, 0xFF},    // ---- 批次 326（2026-10-03）：`EntityPlayer:FireTechLaser(...)`（1 处）----
    // ★ 尾部 3 个可省（契约里 `OneHit`/`Source`/`DamageMultiplier` 都带缺省）；
    //   **最后那一格用 `EngineArgKind::FloatDefaultOne`**（省略 ⇒ 1.0，不是 0）——
    //   这是本项目第一次用到那种参数种类（`DamageMultiplier` 的缺省是 1）。
    {0x0E0100DF, kEntityPlayerFireTechLaserOffset, kEntityPlayerFireTechLaserEntryWord,
     FieldReceipt::EntityPlayer,
     EngineCallShape::Vector2RefIntVector2RefBoolBoolHandleFloatOpt3, 7, 0xFF},
    // ---- 批次 335（2026-10-03）：交接第八份 §3「批 A」的两条（第三条 `Seeds:SetStartSeed`
    // 在 `game_api.cpp` 的 `kSeedsEngineRows` 里，因为接收者不同）。
    // 两条共用本批新开的形状 `EngineCallShape::VoidIntBoolOpt1`
    // （`void(this, i32, bool)`，尾部 1 个可省）：契约各写 1 个形参、引擎符号都是 2 格。
    // 0x00E7 `ChangePlayerType(PlayerType)` —— 语料 `RepentancePlus/RepentancePlus/main.lua:1008`
    // （`player:ChangePlayerType(PlayerType.PLAYER_EVE)`，只传 1 个）。
    // ★ 第 2 格那个 `bool` 对这次调用**是惰性的**：分支表要求 `PlayerType ∈ {16, 17}`
    //   （被遗忘者/灵魂）才看它，而语料传的是 `PLAYER_EVE`(5) ⇒ 取 0 与取 1 走同一条路。
    //   逐条反汇编见 `runtime_constants.hpp` 的批次 335 段（含 PC 侧 `0x78FF70` 的同形证据）。
    {0x0E0100E7, kEntityPlayerChangePlayerTypeOffset, kEntityPlayerChangePlayerTypeEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::VoidIntBoolOpt1, 2, 0xFF},
    // 0x00E8 `DischargeActiveItem(ActiveSlot = SLOT_PRIMARY)` —— 语料
    // `RepentancePlus/RepentancePlus/main.lua:2249`（`Player:DischargeActiveItem(ActiveSlot.SLOT_PRIMARY)`）。
    // 语义（`EntityPlayer.md:644`）：「把主动道具充能置 0、但不触发它的效果」。
    // ★ 第 2 格那个 `bool` **确实参与分支**（`0x2B9C54` 的 `tbnz w27,#0x0`）⇒ 取 0 是
    //   "契约只暴露 1 个形参 + vanilla 缺省一律是 0"这条口径，**不是**像上面那条一样被证明惰性；
    //   若真机发现 PC 那一格不是 0，这一行要单独改（真机项见作业单第九节）。
    {0x0E0100E8, kEntityPlayerDischargeActiveItemOffset, kEntityPlayerDischargeActiveItemEntryWord,
     FieldReceipt::EntityPlayer, EngineCallShape::VoidIntBoolOpt2, 2, 0xFF},
};
static_assert(RowCount(kEntityPlayerEngineRows) == 35,
              "行数与 id 段（0x0056~0x005C + 批次 177 的 0x0030/0x0031/0x0040/0x004B/0x004C "
              "+ 批次 184 的 0x0042 + 批次 252 的 0x0084 + 批次 254 的 0x0085~0x0087 "
              "+ 批次 288 的 0x00C8 + 批次 335 的 0x00E7/0x00E8）要一起改");

std::size_t AttachEntityPlayerMethods(lua_State* state) noexcept {
    std::size_t fieldApiCount = 0;
    return AttachApi700Methods(state,"EntityPlayer") + AttachApi600Methods(state,"EntityPlayer") + AttachApi400Methods(state,"EntityPlayer") + AttachApi300Methods(state,"EntityPlayer") + AttachApi200Methods(state,"EntityPlayer") + AttachApi100Methods(state,"EntityPlayer") + AttachRPlusMethods(state,"EntityPlayer") + AttachOwnerMethods(state, kEntityPlayerOwner, kEntityPlayerHandlers,
                              RowCount(kEntityPlayerHandlers), FieldApiRows(&fieldApiCount),
                              fieldApiCount, kEntityPlayerEngineRows,
                              RowCount(kEntityPlayerEngineRows));
}

//: 批次 285：`EntityPickup` 的引擎方法数据行（域内序号 0xC1）。
//: 与 `kEntityPlayerEngineRows` 同一形态 —— 与手写处理器表并存，一起交给 `AttachOwnerMethods`
//: （它先按手写绑定行匹配、匹配不到再按数据行挂，所以两者可以在同一个 owner 里共存）。
//: `Morph(EntityType Type, int Variant, int SubType, boolean KeepPrice, boolean KeepSeed,
//: boolean IgnoreModifiers)`（PC 契约 `tools/pc_contract_docs/EntityPickup.md:40`）。
//: ★ 形状声明"尾部 3 个可省"（契约里那 3 个布尔带缺省值）：语料里
//: `ChallengeAPI/.../polaroid_negative.lua:33` 只传 3 个、`CyclingItemsAPI/main.lua:392` 传 6 个 ——
//: 少声明一格就会让 3 参那条调用报错、摘掉整条模组回调。
constexpr EngineMethodRow kEntityPickupEngineRows[] = {
    {0x0E0100C1, kEntityPickupMorphOffset, kEntityPickupMorphEntryWord, FieldReceipt::Entity,
     EngineCallShape::VoidIntIntIntBoolBoolBoolOpt3, 6, 0xFF},
};

std::size_t AttachEntityPickupMethods(lua_State* state) noexcept {
    return AttachApi400Methods(state,"EntityPickup") + AttachApi100Methods(state,"EntityPickup") + AttachOwnerMethods(state, kEntityPickupOwner, kEntityPickupHandlers,
                              RowCount(kEntityPickupHandlers), nullptr, 0,
                              kEntityPickupEngineRows, RowCount(kEntityPickupEngineRows));
}

//: 批次 281：`EntityTear` 视图的方法表（域内序号 0xB9）。目前只有 `ChangeVariant` 一条 ——
//: 它是语料在这一族里唯一真正调用的方法（8 处）。
//: ★ 这张表挂在 `kEntityTearMetatable` 上，由 `IndexEntity(EntityView::Tear)` 先查它、
//:   查不到再回落 `Entity` 的方法表 ⇒ `tear:GetSprite()` 之类照样能用。
constexpr LuaHandlerBinding kEntityTearHandlers[] = {
    {0x0E0100B9, &EntityTearChangeVariant},
    {0x0E010120, &EntityTearResetSpriteScale},
};

std::size_t AttachEntityTearMethods(lua_State* state) noexcept {
    std::size_t fieldApiCount = 0;
    const FieldApiRow* fieldApiRows = FieldApiRows(&fieldApiCount);
    //: `EntityTear` 自己没有引擎方法数据行（`kEntityEngineRows`）⇒ 传空表；
    //: `AttachOwnerMethods` 只挂 id 匹配的行，属于别的 owner 的行一处也挂不上。
    return AttachApi400Methods(state,"EntityTear") + AttachApi300Methods(state,"EntityTear") + AttachApi200Methods(state,"EntityTear") + AttachRPlusMethods(state,"EntityTear") + AttachOwnerMethods(state, "EntityTear", kEntityTearHandlers,
                              RowCount(kEntityTearHandlers), fieldApiRows, fieldApiCount, nullptr,
                              0);
}

//: 批次 282：`EntityLaser` 视图的方法表（域内序号 0xBA）。
//: ★★ 上面那句"同族的 `ShootAngle` **不收**（引擎符号 7 参 vs 契约 6 参 ⇒ 按"参数个数对齐"规则排除）"
//:   在**批次 325（2026-10-03）被推翻**：那条规则当时是把"契约少写一个"当成了"引擎真的少一个"。
//:   实际去读 PC 那条绑定（`0x8C7550`）就看得出来——它**也收 7 个参数**：
//:     `movzx ecx, byte ptr [ebp + 0x20]` 读的正是第 7 格（`[ebp+0x8/0xc/0x10/0x14/0x18/0x1c/0x20]`
//:     七格），并且**原样转发**给 `Game::Spawn`（`push ecx`）⇒ **PC 与 Switch 的签名一致**，
//:   差的那一格只是 C++ 头文件里带缺省值 ⇒ 按"尾部 1 个可省、省略时保持 0"处理即可
//:   （与 `Room:SetGridPath(int,int,int)` 同一档）。
//: ★ 它是**静态方法**（`EntityLaser.ShootAngle(...)`，点号直呼在类名上）⇒ 走批次 324 立的
//:   "静态调用 + 句柄返回"，挂**全局 `EntityLaser` 表**（见 `AttachEntityLaserStatics`）。
constexpr LuaHandlerBinding kEntityLaserHandlers[] = {
    {0x0E0100BA, &EntityLaserSetActiveRotation},
};

std::size_t AttachEntityLaserMethods(lua_State* state) noexcept {
    std::size_t fieldApiCount = 0;
    const FieldApiRow* fieldApiRows = FieldApiRows(&fieldApiCount);
    return AttachApi700Methods(state,"EntityLaser") + AttachApi300Methods(state,"EntityLaser") + AttachRPlusMethods(state,"EntityLaser") + AttachOwnerMethods(state, "EntityLaser", kEntityLaserHandlers,
                              RowCount(kEntityLaserHandlers), fieldApiRows, fieldApiCount, nullptr,
                              0);
}

//: 把**静态行**发布成全局类表（`EntityNPC.ThrowSpider(...)` / `EntityLaser.ShootAngle(...)`）。
//: 照 `RegisterIsaacApi` 里 `ItemConfig` / `Isaac` 那两处的写法（`lua_newtable` → 填字段 → `lua_setglobal`）。
//: ★ 这里**有意**不走 `AttachOwnerMethods`：那一支按 owner 把**所有**行都挂上去，
//:   会把 `Morph` / `CanShutDoors` 这类实例方法也挂到全局表上（PC 没有这种写法）。
//: ★ 批次 324 为 `EntityNPC` 写、批次 325 抽成通用（`EntityLaser` 复用同一支）。
std::size_t AttachStaticOwnerTable(lua_State* state, const char* owner,
                                   const EngineMethodRow* rows, std::size_t count) noexcept {
    if (state == nullptr || owner == nullptr || rows == nullptr) {
        return 0;
    }
    const ApiCatalog& catalog = ApiCatalog::Default();
    std::size_t attached = 0;
    lua_newtable(state);
    for (std::size_t index = 0; index < count; ++index) {
        const EngineMethodRow& row = rows[index];
        const LuaApiDescriptor* descriptor = catalog.Find(row.id);
        if (descriptor == nullptr) {
            continue;
        }
        lua_pushlightuserdata(state, const_cast<EngineMethodRow*>(&row));
        PushHandler(state, &EngineMethodHandler, 1, row.id);
        lua_setfield(state, -2, descriptor->name);
        ++attached;
    }
    lua_setglobal(state, owner);
    return attached;
}

//: 批次 325（2026-10-03）：`EntityLaser` 的**静态方法**行（域内序号 0xDE）。
//: `EntityLaser.ShootAngle(int Variant, Vector SourcePos, float AngleDegrees, int Timeout,
//:  Vector PosOffset, Entity Source)` —— PC 契约 `tools/pc_contract_docs/EntityLaser.md:146`
//: （**逐字写着 `static EntityLaser`**）。
//: 语料 8 处（`IsaacOnTwitchReloaded`）：`EntityLaser.ShootAngle(1, Vector(x, i), 0, 5, Vector.Zero, p)`
//: 一类写法（**点号**、在类名上；6 个实参 —— 第 7 格走缺省）。
//: ★ 引擎符号 `_ZN15IsaacRepentance12Entity_Laser10ShootAngleEjRKN4KAGE4Math7Vector2EfiS5_PNS_6EntityEb`
//:   @ `0xF743C`：`ShootAngle(u32, Vector2 const&, float, int, Vector2 const&, Entity*, bool)`
//:   —— **没有 `this`**（静态），7 个形参。
//: ★★ 实参映射（AAPCS64、无 `this`）：整数/指针一路 `Variant`→`x0`、`SourcePos`→`x1`、
//:   `Timeout`→`x2`、`PosOffset`→`x3`、`Source`→`x4`、第 7 个 `bool`→`w5`；浮点独立一路
//:   `AngleDegrees`→`s0`。★ 形状表里就按**源码顺序**列 kinds（处理器把整数与浮点分别编号，
//:   顺序自然对上）。
//: ★ 返回 `EntityLaser` 句柄 ⇒ `EngineReturnKind::EntityLaser`。
constexpr EngineMethodRow kEntityLaserStaticRows[] = {
    {0x0E0100DE, kEntityLaserShootAngleOffset, kEntityLaserShootAngleEntryWord,
     FieldReceipt::Entity, EngineCallShape::StaticIntVector2RefFloatIntVector2RefHandleBool, 7,
     0xFF},
};
static_assert(RowCount(kEntityLaserStaticRows) == 1, "行数与 id 段（0x00DE）要一起改");

std::size_t AttachEntityLaserStatics(lua_State* state) noexcept {
    return AttachStaticOwnerTable(state, "EntityLaser", kEntityLaserStaticRows,
                                  RowCount(kEntityLaserStaticRows));
}

//: 批次 285：`EntityNPC` 视图的引擎方法数据行（域内序号 0xC0）。
//: `Entity:ToNPC()` 从本批起压 `kEntityNPCMetatable` ⇒ `npc:Morph(...)` 才取得到（此前
//: `ToNPC()` 压的是基类 `Entity` 元表，`Morph` 没有地方挂 ⇒ `attempt to call a nil value`）。
//: 目前只有 `Morph` 一条（`EntityNPC` 页上语料真正用得上的方法）。
//: ★ 字段仍回落到 `Entity`（`IndexEntity` 的 else 分支）⇒ `npc.HitPoints`/`npc.Scale` 不退化。
constexpr EngineMethodRow kEntityNPCEngineRows[] = {
    // 0xC0 `Morph(EntityType type, int Variant, int SubType, int ChampionColorIdx)`
    // （PC 契约 `EntityNPC.md:117`，返回 boolean）。
    {0x0E0100C0, kEntityNpcMorphOffset, kEntityNpcMorphEntryWord, FieldReceipt::Entity,
     EngineCallShape::BoolIntIntIntInt, 4, 0xFF},
    // ---- 批次 303（2026-10-03）：`EntityNPC:CanShutDoors()`（3 处 / 1 个模组）----
    // PC 契约 `EntityNPC.md` 里与 `Entity:CanShutDoors()` 是同一条语义（"这一格里的门能不能关"）。
    // ★ 与上一族那条**用同一个槽号 18** —— 但**必须单独一行**：`EntityNPC` 有自己的实现，
    //   而这一行挂在 `EntityNPC` 这个 owner 上（`AttachOwnerMethods` 按 id 匹配）。
    //   这也正是"按槽调用"的意义：同一行数据，`Entity`、`EntityNPC`、以及将来任何派生类的
    //   句柄调进来，拿到的都是**那个类的**实现。
    // ★ 读数是 `EngineRowRejectReason::Vtable`（与 `Entity` 那条共用一个判据）。
    {0x0E0100D4, MakeEngineVtableRowOffset(kEntityVtableCanShutDoorsSlot), 0,
     FieldReceipt::Entity, EngineCallShape::Bool0, 0, 0xFF},
};
static_assert(RowCount(kEntityNPCEngineRows) == 2,
              "行数与 id 段（0x00C0 + 0x00D4）要一起改");

// 原函数含目标缓存与不同敌人的选择行为，返回契约是Entity，并非固定玩家0。
using AgonyNpcTargetFn = std::uintptr_t (*)(std::uintptr_t);
int EntityNpcGetPlayerTarget(lua_State* state) {
    const auto npc=ValidatedEntity(CheckEntityHandle(state,1));
    if (!IsNpcFamilyEntity(npc)) return luaL_error(state,"EntityNPC:GetPlayerTarget receiver is no longer available");
    const auto method=EntityMethodByExpectedBytes(kEntityNpcGetPlayerTargetOffset,kEntityNpcGetPlayerTargetExpectedBytes);
    if (method==0) return luaL_error(state,"EntityNPC:GetPlayerTarget native bindings are unavailable");
    const auto entity=engine_call::AsFunction<AgonyNpcTargetFn>(method)(npc);
    if (entity==0) {PushNil(state);return 1;}
    if (!IsEntityPointer(entity)) return luaL_error(state,"EntityNPC:GetPlayerTarget returned an unavailable entity");
    PushEntityHandle(state,entity,kEntityMetatable);
    return 1;
}
// PC thunk84C3E0：四个数值必填，Loop走Lua真假；保留NPC原方法的冠军pitch与位置。
using EntityNpcPlaySoundFn = void (*)(std::uintptr_t, std::uint32_t, float, std::int32_t, bool, float);
int EntityNpcPlaySound(lua_State* state) {
    const auto id = static_cast<std::uint32_t>(luaL_checkinteger(state, 2));
    const float volume = static_cast<float>(luaL_checknumber(state, 3));
    const auto delay = static_cast<std::int32_t>(static_cast<std::uint32_t>(luaL_checkinteger(state, 4)));
    const bool loop = lua_toboolean(state, 5) != 0;
    const float pitch = static_cast<float>(luaL_checknumber(state, 6));
    const auto npc = ValidatedEntity(CheckEntityHandle(state, 1));
    const auto method = EntityMethodByExpectedBytes(kEntityNpcPlaySoundOffset,
                                                   kEntityNpcPlaySoundExpectedBytes);
    if (!IsNpcFamilyEntity(npc) || method == 0) {
        return luaL_error(state, "EntityNPC:PlaySound native receiver or binding is unavailable");
    }
    engine_call::AsFunction<EntityNpcPlaySoundFn>(method)(npc, id, volume, delay, loop, pitch);
    return 0;
}

// 24B classic libc++头仅在同步调用内借Lua串；两个参数有独立头，不跨std::string ABI/堆。
struct alignas(8) EntityAnimationStringAbi { unsigned char bytes[24]; };
static_assert(sizeof(EntityAnimationStringAbi) == 24 && alignof(EntityAnimationStringAbi) == 8);
using EntityNpcAnimWalkFrameFn = void (*)(std::uintptr_t, const EntityAnimationStringAbi*,
                                         const EntityAnimationStringAbi*, float);
int EntityNpcAnimWalkFrame(lua_State* state) {
    std::size_t horizontalSize = 0, verticalSize = 0;
    const char* horizontal = luaL_checklstring(state, 2, &horizontalSize);
    const char* vertical = luaL_checklstring(state, 3, &verticalSize);
    const float threshold = static_cast<float>(luaL_checknumber(state, 4));
    const auto npc = ValidatedEntity(CheckEntityHandle(state, 1));
    const auto method = EntityMethodByExpectedBytes(kEntityNpcAnimWalkFrameOffset,
                                                   kEntityNpcAnimWalkFrameExpectedBytes);
    if (!IsNpcFamilyEntity(npc) || method == 0) {
        return luaL_error(state, "EntityNPC:AnimWalkFrame native receiver or binding is unavailable");
    }
    EntityAnimationStringAbi horizontalHeader{}, verticalHeader{};
    if (!isaac::runtime::console::BuildBorrowedCommandString(horizontal, horizontalSize, horizontalHeader.bytes) ||
        !isaac::runtime::console::BuildBorrowedCommandString(vertical, verticalSize, verticalHeader.bytes)) {
        return luaL_error(state, "EntityNPC:AnimWalkFrame animation string is unavailable");
    }
    engine_call::AsFunction<EntityNpcAnimWalkFrameFn>(method)(npc, &horizontalHeader, &verticalHeader, threshold);
    return 0;
}

constexpr LuaHandlerBinding kEntityNpcQueryHandlers[]={
    {0x0E01011D,&EntityNpcGetPlayerTarget},
    {0x0E010121,&EntityNpcPlaySound},
    {0x0E010122,&EntityNpcAnimWalkFrame},
};

std::size_t AttachEntityNPCMethods(lua_State* state) noexcept {
    std::size_t fieldApiCount = 0;
    const FieldApiRow* fieldApiRows = FieldApiRows(&fieldApiCount);
    //: 与 `EntityTear`/`EntityLaser` 同形：把整张字段表传进来（按 id 匹配，不属于本 owner 的
    //: 一处也挂不上），手写绑定表传空 —— `EntityNPC` 现在只有引擎方法数据行。
    return AttachApi700Methods(state,"EntityNPC") + AttachApi400Methods(state,"EntityNPC") + AttachApi300Methods(state,"EntityNPC") + AttachOwnerMethods(state, "EntityNPC", kEntityNpcQueryHandlers, RowCount(kEntityNpcQueryHandlers), fieldApiRows, fieldApiCount,
                              kEntityNPCEngineRows, RowCount(kEntityNPCEngineRows));
}

//: 批次 324（2026-10-03）：`EntityNPC` 的**静态方法**行（域内序号 0xDD）。
//:
//: ★★ 为什么单开一张表、而不是塞进 `kEntityNPCEngineRows`：PC 上 `EntityNPC` 的**实例方法**
//:   挂在元表上（`npc:Morph(...)`），**静态方法**挂在**类表**上（`EntityNPC.ThrowSpider(...)`）。
//:   塞进同一张表会让 `AttachOwnerMethods` 顺手把它也挂到元表上 ⇒ `npc:ThrowSpider(...)`
//:   这种**PC 上不存在**的写法在我们这儿能跑，等于凭空多一条接口（也会掩盖模组的写法错误）。
//:   ⇒ 实例行归 `AttachEntityNPCMethods`，静态行走下面这个 `AttachEntityNPCStatics`。
//:   ★ 两张表都是**数据**，各自 16 字节一行，没有代码成本。
//:
//: `EntityNPC.ThrowSpider(Vector Position, Entity Spawner, Vector TargetPos, boolean Big, float YOffset)`
//:   —— PC 契约 `tools/pc_contract_docs/EntityNPC.md:165`（逐字 `static const EntityNPC`）。
//:   ★ 语料三处（`RepentancePlus/main.lua:2040/2061`、`IsaacOnTwitchReloaded/scripts/events.lua:1612`）
//:     都写 `EntityNPC.ThrowSpider(...)`（**点号**、在类名上）；其中一处 `Spawner` 传 `nil`、
//:     一处 `Big` 传 `nil` —— `Handle` 那条对 nil 返回 0、`Bool` 那条走 `lua_toboolean`（nil = false）。
constexpr EngineMethodRow kEntityNPCStaticRows[] = {
    {0x0E0100DD, kEntityNpcThrowSpiderOffset, kEntityNpcThrowSpiderEntryWord, FieldReceipt::Entity,
     EngineCallShape::StaticVoidVector2RefHandleVector2RefBoolFloat, 5, 0xFF},
};
static_assert(RowCount(kEntityNPCStaticRows) == 1, "行数与 id 段（0x00DD）要一起改");

std::size_t AttachEntityNPCStatics(lua_State* state) noexcept {
    return AttachStaticOwnerTable(state, "EntityNPC", kEntityNPCStaticRows,
                                  RowCount(kEntityNPCStaticRows));
}

//: 批次 330（2026-10-03）：`EntityFamiliar` 视图的引擎方法数据行（域内序号 0xE2、0xE3）。
//:
//: ★★ **本批的产出其实是"视图"本身**：`Entity:ToFamiliar()` 此前压的是**基类 `Entity` 元表**
//:   ⇒ `EntityFamiliar` 页上的方法没有地方挂，语料里 `familiar:FollowParent()`（`IsaacOnTwitchReloaded`
//:   2 处）与 `Familiar:AddToFollowers()`（`RepentancePlus` 2 处 + `IsaacOnTwitchReloaded` 1 处）
//:   都报 "attempt to call a nil value"、把整条回调摘掉。
//:   本批照**批次 285 给 `EntityNPC` 立的那一套**接线（新元表 + `EntityView::Familiar` +
//:   `CheckEntityHandle` 认它 + `ToFamiliar()` 改压新元表 + 注册处那一段）—— 六处一处不漏。
//:
//: 两条都是**无参、返回 `void`** ⇒ 复用现成的 `EngineCallShape::Void0`（**本批没有新形状**）。
//: 逐条取证（PC 绑定本体是算法 ⇒ 判法四档第②档；★ 连"两个名字有没有接反"都逐条核过）
//: 见 `runtime_constants.hpp` 的批次 330 段。
//:
//: ★ 接收者用**本批新开**的 `FieldReceipt::EntityFamiliar`（**精确** vptr + 类型）：
//:   这两条是**调用**，而 `follow_parent()` 一进去就解引用 `[this+0xf50]` ⇒ 拿错类的对象当
//:   `this` 会**野读**（读字段那类最多读到别人的值，危险等级不同）。
constexpr EngineMethodRow kEntityFamiliarEngineRows[] = {
    // 0xE2 `EntityFamiliar:FollowParent()`（PC 契约 `EntityFamiliar.md:65`）
    {0x0E0100E2, kEntityFamiliarFollowParentOffset, kEntityFamiliarFollowParentEntryWord,
     FieldReceipt::EntityFamiliar, EngineCallShape::Void0, 0, 0xFF},
    // 0xE3 `EntityFamiliar:AddToFollowers()`（PC 契约 `EntityFamiliar.md:47`）
    {0x0E0100E3, kEntityFamiliarAddToFollowersOffset, kEntityFamiliarAddToFollowersEntryWord,
     FieldReceipt::EntityFamiliar, EngineCallShape::Void0, 0, 0xFF},
    // ---- 批次 341（2026-10-04）：`EntityFamiliar:FollowPosition(Vector Pos)`（1 处 / 1 个模组）----
    // PC 契约 `tools/pc_contract_docs/EntityFamiliar.md:70`：`void FollowPosition ( Vector Pos )`。
    // 引擎真身 `Entity_Familiar::follow_position(Vector2 const&) @ 0xAFCC0`（入口字 `0xD100C3FF`），
    // `x1` = **指针**（`Vector2 const&`）⇒ 形状用本批新开的 `VoidVector2Ref`（纯数据、0 代码；
    // `EngineArgKind::Vector2Ref` 早在批次 252 就存在）。接收者仍是 `FieldReceipt::EntityFamiliar`
    // （精确 vptr + 类型）—— 与上面两条同一条理由：这**是调用**，函数一进去就解引用 `[this+0xF50]`。
    // ★★ 本条**推翻批次 331 的负结果**（"函数体从不读实参"）：守卫不成立支 `0xAFD20` 的
    //   `mov x0, x1` 用的就是原始实参 ⇒ 两条路与 PC 逐条同形。逐条路线见 `runtime_constants.hpp`
    //   的批次 341 段（含 331 的错因：只线性读了守卫成立支）。
    // 语料：`IsaacOnTwitchReloaded/scripts/mechanics.lua:705`（`value.entity:FollowPosition(lastFamPos)`）。
    {0x0E0100F0, kEntityFamiliarFollowPositionOffset, kEntityFamiliarFollowPositionEntryWord,
     FieldReceipt::EntityFamiliar, EngineCallShape::VoidVector2Ref, 1, 0xFF},
};
static_assert(RowCount(kEntityFamiliarEngineRows) == 3, "行数与 id 段（0x00E2/0x00E3/0x00F0）要一起改");

//: 批次 339（2026-10-04）：`EntityFamiliar` 的**手写绑定行**（此前是空的）。
//: `FireProjectile` 用 id 段的下一个空号 `0x00EB`（目录行见 `api_catalog.cpp`）。
constexpr LuaHandlerBinding kEntityFamiliarHandlers[] = {
    {0x0E0100EB, &EntityFamiliarFireProjectile},
    {0x0E010119, &EntityFamiliarGetOrbitPosition},
    {0x0E01011A, &EntityFamiliarRecalculateOrbitOffset},
    {0x0E01011B, &EntityFamiliarAddToOrbit},
    {0x0E01011C, &EntityFamiliarRemoveFromOrbit},
};

std::size_t AttachEntityFamiliarMethods(lua_State* state) noexcept {
    std::size_t fieldApiCount = 0;
    const FieldApiRow* fieldApiRows = FieldApiRows(&fieldApiCount);
    //: 与 `AttachEntityNPCMethods` 同形：整张字段表传进来（按 id 匹配，不属于本 owner 的
    //: 一处也挂不上）。
    //: ★ 批次 339：手写绑定表**不再留空** —— `FireProjectile` 是"引擎真身在、契约形参少一个"
    //:   那一类 ⇒ 手写转发（与 334 的 `CheckFamiliar`、337 的 `FireTear` 同一条路）。
    //: ★ 字段本身仍回落到 `Entity`（`IndexEntity` 的 `else` 分支）⇒ `familiar.Player`
    //:   （EID 从批次 9 起就在用）与其余基类方法照旧。
    return AttachApi200Methods(state,"EntityFamiliar") + AttachApi100Methods(state,"EntityFamiliar") + AttachOwnerMethods(state, "EntityFamiliar", kEntityFamiliarHandlers,
                              RowCount(kEntityFamiliarHandlers), fieldApiRows, fieldApiCount,
                              kEntityFamiliarEngineRows, RowCount(kEntityFamiliarEngineRows));
}

//: 批次 344（2026-10-04）：`PathFinder` 视图的引擎方法数据行（域内序号 0x00F7）。
//:
//: `PathFinder:HasPathToPos(Vector Pos, boolean IgnorePoop)`（1 处 / 1 个模组）：
//: `EntityNPC.Pathfinder:HasPathToPos(p.Position, false)`（`IsaacOnTwitchReloaded/scripts/events.lua:988`）。
//: PC 契约 `tools/pc_contract_docs/PathFinder.md:64`（本批逐字节 vendor 进来的那一页）。
//:
//: ★★ 本批的产出其实是**两件前置**：`FieldReceipt::PathFinder`（严格校验句柄类型）与本批新开的
//:   形状 `EngineCallShape::BoolVector2RefBool`（**纯数据、0 代码**），以及 `PathFinder` 视图本身
//:   （句柄 + 元表 + `__index` + 方法表）与 `EntityNPC` 的 `Pathfinder` 属性入口。
//: ★ 引擎真身 `NPCAI_Pathfinder::HasPathToPos(Vector2 const&, bool) const @ 0x42F6CC`
//:   （入口字 `0xA9BA7BFD`）—— 同族另有一条 **3 参**重载（`0x42FAFC`），**别抄错**。
//: ★ 接收者链 `Entity_NPC + 0x408` 的四条证据见 `runtime_constants.hpp` 的
//:   `kEntityNpcPathfinderOffset` 段。
constexpr EngineMethodRow kPathFinderEngineRows[] = {
    {0x0E0100F7, kPathFinderHasPathToPosOffset, kPathFinderHasPathToPosEntryWord,
     FieldReceipt::PathFinder, EngineCallShape::BoolVector2RefBool, 2, 0xFF},
};
static_assert(RowCount(kPathFinderEngineRows) == 1, "行数与 id 段（0x00F7）要一起改");

std::size_t AttachPathFinderMethods(lua_State* state) noexcept {
    //: `PathFinder` 没有字段行、也没有手写绑定（本批只有一条引擎方法数据行）。
    return AttachApi300Methods(state,"PathFinder") + AttachApi200Methods(state,"PathFinder") + AttachRPlusMethods(state,"PathFinder") + AttachOwnerMethods(state, "PathFinder", nullptr, 0, nullptr, 0, kPathFinderEngineRows,
                              RowCount(kPathFinderEngineRows));
}

// ---- `TemporaryEffects`（批次 388，2026-10-07）：`EntityPlayer:GetEffects()` 的返回值。----
//
// 17 个方法分两处挂：6 条无可选参数的走**数据行**（下面这张表），其余 11 条走**手写绑定表**。
// 两张表的 id 段：数据行 0x00FA..0x00FF、手写 0x0100..0x010A（Isaac 域，本批新占号段）。
// ★ 引擎真身全是 `Repentance.nro` 动态符号表里的 `TemporaryEffects::*`（见 `runtime_constants.hpp`
//   的 TemporaryEffects 段；那一族入口指纹很弱，只能证明"模块基址对"）。
constexpr EngineMethodRow kTemporaryEffectsEngineRows[] = {
    // `HasCollectibleEffect(CollectibleType)` → `TemporaryEffects::HasEffect(eCollectibleType) const`
    {0x0E0100FA, kTemporaryEffectsHasCollectibleEffectOffset,
     kTemporaryEffectsHasCollectibleEffectEntryWord, FieldReceipt::TemporaryEffects,
     EngineCallShape::Bool1, 1, 0xFF},
    // `HasTrinketEffect(TrinketType)` → `HasEffect(eTrinketType) const`
    {0x0E0100FB, kTemporaryEffectsHasTrinketEffectOffset,
     kTemporaryEffectsHasTrinketEffectEntryWord, FieldReceipt::TemporaryEffects,
     EngineCallShape::Bool1, 1, 0xFF},
    // `HasNullEffect(NullItemID)` → `HasEffect(ItemConfig::eNullItemID) const`
    {0x0E0100FC, kTemporaryEffectsHasNullEffectOffset, kTemporaryEffectsHasNullEffectEntryWord,
     FieldReceipt::TemporaryEffects, EngineCallShape::Bool1, 1, 0xFF},
    // `GetCollectibleEffectNum(CollectibleType)` → `GetEffectNum(eCollectibleType) const`
    {0x0E0100FD, kTemporaryEffectsGetCollectibleEffectNumOffset,
     kTemporaryEffectsGetCollectibleEffectNumEntryWord, FieldReceipt::TemporaryEffects,
     EngineCallShape::Int1, 1, 0xFF},
    // `GetTrinketEffectNum(TrinketType)` → `GetEffectNum(eTrinketType) const`
    {0x0E0100FE, kTemporaryEffectsGetTrinketEffectNumOffset,
     kTemporaryEffectsGetTrinketEffectNumEntryWord, FieldReceipt::TemporaryEffects,
     EngineCallShape::Int1, 1, 0xFF},
    // `GetNullEffectNum(NullItemID)` → `GetEffectNum(ItemConfig::eNullItemID) const`
    {0x0E0100FF, kTemporaryEffectsGetNullEffectNumOffset,
     kTemporaryEffectsGetNullEffectNumEntryWord, FieldReceipt::TemporaryEffects,
     EngineCallShape::Int1, 1, 0xFF},
};
static_assert(RowCount(kTemporaryEffectsEngineRows) == 6,
              "行数与 id 段（0x00FA..0x00FF）要一起改");

// 6 条 `Add*`/`Remove*`（手写：PC 缺省值 true/1，非 0）+ 5 条占位（引擎侧形状未齐）。
constexpr LuaHandlerBinding kTemporaryEffectsHandlers[] = {
    {0x0E010100, &TemporaryEffectsAddCollectibleEffect},
    {0x0E010101, &TemporaryEffectsAddTrinketEffect},
    {0x0E010102, &TemporaryEffectsAddNullEffect},
    {0x0E010103, &TemporaryEffectsRemoveCollectibleEffect},
    {0x0E010104, &TemporaryEffectsRemoveTrinketEffect},
    {0x0E010105, &TemporaryEffectsRemoveNullEffect},
    {0x0E010106, &TemporaryEffectsClearEffects},
    {0x0E010107, &TemporaryEffectsGetCollectibleEffect},
    {0x0E010108, &TemporaryEffectsGetNullEffect},
    {0x0E010109, &TemporaryEffectsGetTrinketEffect},
    {0x0E01010A, &TemporaryEffectsGetEffectsList},
};
static_assert(RowCount(kTemporaryEffectsHandlers) == 11,
              "行数与 id 段（0x0100..0x010A）要一起改");

std::size_t AttachTemporaryEffectsMethods(lua_State* state) noexcept {
    return AttachOwnerMethods(state, "TemporaryEffects", kTemporaryEffectsHandlers,
                              RowCount(kTemporaryEffectsHandlers), nullptr, 0,
                              kTemporaryEffectsEngineRows, RowCount(kTemporaryEffectsEngineRows));
}

std::size_t AttachItemConfigMethods(lua_State* state) noexcept {
    return AttachApi600Methods(state,"ItemConfig") + AttachApi300Methods(state,"ItemConfig") + AttachApi200Methods(state,"ItemConfig") + AttachOwnerMethods(state, kItemConfigOwner, kItemConfigHandlers,
                              RowCount(kItemConfigHandlers));
}

std::size_t AttachItemConfigItemMethods(lua_State* state) noexcept {
    std::size_t fieldApiCount = 0;
    // 同一张数据行表也挂给 `ItemConfig_Item` 族：绑定循环按 id 匹配，不会串族
    // （行里的 `receipt` 决定用哪套接收者校验）。
    return AttachApi600Methods(state,"ItemConfig_Item") + AttachOwnerMethods(state, kItemConfigItemOwner, kItemConfigItemHandlers,
                              RowCount(kItemConfigItemHandlers), FieldApiRows(&fieldApiCount),
                              fieldApiCount);
}

#if !defined(__SWITCH__)
void SetEntityPlayerHasCollectibleHostImplementation(
    EntityPlayerHasCollectibleHostImplementation function) noexcept {
    g_HasCollectibleHostImplementation = function;
}

void SetCurrentLanguageCodeHostImplementation(
    CurrentLanguageCodeHostImplementation function) noexcept {
    g_CurrentLanguageCodeHostImplementation = function;
}

void SetItemConfigIsAvailableHostImplementation(
    ItemConfigIsAvailableHostImplementation function) noexcept {
    g_ItemConfigIsAvailableHostImplementation = function;
}

void SetItemConfigCardIsRuneHostImplementation(
    ItemConfigCardIsRuneHostImplementation function) noexcept {
    g_ItemConfigCardIsRuneHostImplementation = function;
}
#endif

namespace {

// `Entity` / `EntityPlayer` / `EntityPickup` / `ItemConfig` / `ItemConfig_Item` 的元表。字段走
// `__index` 函数（字段名与方法名都在那里），方法表挂在元表的 `__methods` 上 —— 与 `Vector`
// 同一形态，理由相同：`__index` 必须是函数才能同时服务 `item.Name` 与 `item:HasTags(...)`。
//
// 这一段**建立元表**而不是像其它家族那样让 `lua_runtime.cpp` 建：本轮改动边界不允许再改旧 TU 的
// 注册区，所以家族入口自己建表（旧 TU 只调用 `RegisterIsaacApi`）。
// 全局 `ItemConfig` 表：PC 里它是一张**类表** —— `Isaac.GetItemConfig()` 给实例，而
// `ItemConfig.TAG_*` 是表上的常量（`Tags` 是位掩码）。
//
// 为什么必须补：EID 的 `features/eid_data.lua:1025` 第一件事就是
// `ItemConfig.TAG_GUPPY`，而我们此前只有实例元表、**没有这个全局**，于是整包加载在那一行
// 断掉（真机报告 `01789202729`：`...eid_data.lua:1025: attempt to index a nil value`）。
// EID 另外还用 `TAG_QUEST`/`TAG_NO_GREED`/`TAG_NO_CHALLENGE` 等（`main.lua:669`、`eid_api.lua:2031`）。
//
// 常量值直接取自 `analysis/isaacdocs-snapshot/docs/enums/ItemConfig.md`（`1 << N`），
// `runtime/tests/test_lua_item_config.py` 会拿那份文档逐条核对，防止这里抄错。
struct ItemConfigConstant {
    const char* name;
    std::uint32_t bit;
};

constexpr ItemConfigConstant kItemConfigTagConstants[] = {
    ItemConfigConstant{"TAG_DEAD", 0},
    ItemConfigConstant{"TAG_SYRINGE", 1},
    ItemConfigConstant{"TAG_MOM", 2},
    ItemConfigConstant{"TAG_TECH", 3},
    ItemConfigConstant{"TAG_BATTERY", 4},
    ItemConfigConstant{"TAG_GUPPY", 5},
    ItemConfigConstant{"TAG_FLY", 6},
    ItemConfigConstant{"TAG_BOB", 7},
    ItemConfigConstant{"TAG_MUSHROOM", 8},
    ItemConfigConstant{"TAG_BABY", 9},
    ItemConfigConstant{"TAG_ANGEL", 10},
    ItemConfigConstant{"TAG_DEVIL", 11},
    ItemConfigConstant{"TAG_POOP", 12},
    ItemConfigConstant{"TAG_BOOK", 13},
    ItemConfigConstant{"TAG_SPIDER", 14},
    ItemConfigConstant{"TAG_QUEST", 15},
    ItemConfigConstant{"TAG_MONSTER_MANUAL", 16},
    ItemConfigConstant{"TAG_NO_GREED", 17},
    ItemConfigConstant{"TAG_FOOD", 18},
    ItemConfigConstant{"TAG_TEARS_UP", 19},
    ItemConfigConstant{"TAG_OFFENSIVE", 20},
    ItemConfigConstant{"TAG_NO_KEEPER", 21},
    ItemConfigConstant{"TAG_NO_LOST_BR", 22},
    ItemConfigConstant{"TAG_STARS", 23},
    ItemConfigConstant{"TAG_SUMMONABLE", 24},
    ItemConfigConstant{"TAG_NO_CANTRIP", 25},
    ItemConfigConstant{"TAG_WISP", 26},
    ItemConfigConstant{"TAG_UNIQUE_FAMILIAR", 27},
    ItemConfigConstant{"TAG_NO_CHALLENGE", 28},
    ItemConfigConstant{"TAG_NO_DAILY", 29},
    ItemConfigConstant{"TAG_LAZ_SHARED", 30},
    ItemConfigConstant{"TAG_LAZ_SHARED_GLOBAL", 31},
    ItemConfigConstant{"TAG_NO_EDEN", 32},
};

void PublishItemConfigConstants(lua_State* state) {
    lua_newtable(state);
    lua_pushinteger(state,0);lua_setfield(state,-2,"CHARGE_NORMAL");
    lua_pushinteger(state,1);lua_setfield(state,-2,"CHARGE_TIMED");
    lua_pushinteger(state,2);lua_setfield(state,-2,"CHARGE_SPECIAL");
    for (const ItemConfigConstant& constant : kItemConfigTagConstants) {
        // `lua_Integer` 是 64 位，`1 << 32`（`TAG_NO_EDEN`）不会溢出。
        lua_pushinteger(state, static_cast<lua_Integer>(1) << constant.bit);
        lua_setfield(state, -2, constant.name);
    }
    lua_setglobal(state, "ItemConfig");
    PublishApi300Statics(state,"ItemConfig");
    lua_getglobal(state,"ItemConfig");
    const int itemConfig = lua_gettop(state);
    lua_pushcfunction(state,Api600ItemConfigShouldAddCostumeOnPickup);
    lua_setfield(state,itemConfig,"ShouldAddCostumeOnPickup");
    // PC 1.7.9b @804BE6/804BFD在ItemConfig命名空间中登记Config类，
    // 804C6A/804C92把两项静态函数放在该类；类关联实例的真实元表。
    // 仅初始化时创建类表，不增加每帧查表、分配或文件读取。
    lua_newtable(state);
    constexpr const char* methods[] = {"IsValidCollectible", "ShouldAddCostumeOnPickup"};
    for (const char* method : methods) {
        lua_getfield(state,itemConfig,method);
        lua_setfield(state,-2,method);
    }
    lua_newtable(state);
    luaL_getmetatable(state,kItemConfigMetatable);
    lua_setfield(state,-2,"__class");
    lua_setmetatable(state,-2);
    lua_setfield(state,itemConfig,"Config");
    lua_pop(state,1);
}

void RegisterViewMetatables(lua_State* state) {
    luaL_newmetatable(state, kPersistentGameDataMetatable);
    if(!RegisterNativeObjectIdentity(state,-1,PgdIdentity))
        luaL_error(state,"PersistentGameData identity resolver conflicts");
    lua_newtable(state);
    static_cast<void>(AttachOwnerMethods(state, "PersistentGameData", kPersistentGameDataHandlers,
                                        RowCount(kPersistentGameDataHandlers)));
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kEntityMetatable);
    lua_newtable(state);
    static_cast<void>(AttachEntityMethods(state));
    lua_setfield(state, -2, "__methods");
    // 批次 093：`Entity.__index` 是热路径（每次字段读/方法查找都过它）⇒ 单独特判。
    isaac::runtime::PushHandler(state, EntityIndex, 0,
                                     isaac::runtime::kPerfInternalIdEntityIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    luaL_newmetatable(state, kEntityPlayerMetatable);
    lua_newtable(state);
    static_cast<void>(AttachEntityPlayerMethods(state));
    lua_setfield(state, -2, "__methods");
    isaac::runtime::PushHandler(state, EntityPlayerIndex, 0,
                                     isaac::runtime::kPerfInternalIdEntityPlayerIndex);
    lua_setfield(state, -2, "__index");
    // 写入口（2026-09-16）：见 `EntityNewIndex` 的注释（目前只放行 `ControlsCooldown`）。
    // 历史误判：基类 `Entity` 的元表**故意没有** `__newindex` —— PC 里也没有可写的基类字段，
    // ★ 2026-10-09更正：PC Entity的Position/Velocity/HitPoints等可写；所有实体视图共享守卫写入口。
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    // `EntityPickup`（批次 4）：没有自己的 catalog 条目（它的成员只有字段），方法表留空，
    // `__index` 回落到 `Entity` 的（PC 里 `EntityPickup` 就是 `Entity` 的子类）。
    luaL_newmetatable(state, kEntityPickupMetatable);
    lua_newtable(state);
    static_cast<void>(AttachEntityPickupMethods(state));
    lua_setfield(state, -2, "__methods");
    isaac::runtime::PushHandler(state, EntityPickupIndex, 0,
                                     isaac::runtime::kPerfInternalIdEntityPickupIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    // `EntityProjectile`（批次 207，2026-09-29）：`Entity:ToProjectile()` 的返回值。
    // 与 `EntityPickup` 同一形态 —— 方法表留空（它现在没有自己的 catalog 方法），
    // `__index` 是函数：先答自己的字段（`ProjectileFlags`），答不上回落到 `Entity` 的。
    luaL_newmetatable(state, kEntityProjectileMetatable);
    lua_newtable(state);
    static_cast<void>(AttachApi400Methods(state,"EntityProjectile"));
    static_cast<void>(AttachRPlusMethods(state,"EntityProjectile"));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, EntityProjectileIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    // `EntityTear`（批次 281）：`Entity:ToTear()` 的返回值。
    // 与 `EntityProjectile` 同一形态 —— 字段回落到 `Entity` 的（走 `IndexEntity` 的 else 分支），
    // 方法先查本元表（目前一条 `ChangeVariant`）、再回落 `Entity`。
    luaL_newmetatable(state, kEntityTearMetatable);
    lua_newtable(state);
    static_cast<void>(AttachEntityTearMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, EntityTearIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    luaL_newmetatable(state, kEntityBombMetatable);
    lua_newtable(state);
    static_cast<void>(AttachRPlusMethods(state,"EntityBomb"));static_cast<void>(AttachApi300Methods(state,"EntityBomb"));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, EntityBombIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    // `EntityLaser`（批次 282）：`Entity:ToLaser()` 的返回值。与 `EntityTear` 同一形态。
    luaL_newmetatable(state,kEntityKnifeMetatable);
    lua_newtable(state);
    static_cast<void>(AttachApi400Methods(state,"EntityKnife"));static_cast<void>(AttachRPlusMethods(state,"EntityKnife"));
    static_cast<void>(AttachApi200Methods(state,"EntityKnife"));
    static_cast<void>(AttachApi300Methods(state,"EntityKnife"));
    lua_setfield(state,-2,"__methods");lua_pushcfunction(state,EntityKnifeIndex);
    lua_setfield(state,-2,"__index");lua_pushcfunction(state,EntityNewIndex);
    lua_setfield(state,-2,"__newindex");lua_pop(state,1);

    luaL_newmetatable(state, kEntityLaserMetatable);
    lua_newtable(state);
    static_cast<void>(AttachApi400Methods(state,"EntityLaser"));
    static_cast<void>(AttachEntityLaserMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, EntityLaserIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);
    // 批次 325：`EntityLaser` 的**静态方法**另建全局 `EntityLaser` 表
    // （`EntityLaser.ShootAngle(...)`）—— 理由见 `AttachStaticOwnerTable` 的注释。
    static_cast<void>(AttachEntityLaserStatics(state));

    // `EntityNPC`（批次 285）：`Entity:ToNPC()` 的返回值。与 `EntityTear`/`EntityLaser` 同一形态
    // —— 字段回落到 `Entity` 的（`IndexEntity` 的 else 分支），方法先查本元表（`Morph`）、
    // 再回落 `Entity`（所以 `npc:GetSprite()` 之类照样能用）。
    luaL_newmetatable(state, kEntityNPCMetatable);
    lua_newtable(state);
    static_cast<void>(AttachEntityNPCMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, EntityNpcIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);
    // 批次 324：**静态方法**另建全局 `EntityNPC` 表（`EntityNPC.ThrowSpider(...)`）——
    // 与上面那个元表分开，理由见 `AttachEntityNPCStatics` 的注释（实例方法/静态方法在 PC 上
    // 挂的地方本来就不同）。★ 在元表建好之后调：它只用 `lua_setglobal`，与元表无关，
    // 但放这里读起来最顺（两个都是 `EntityNPC` 面）。
    static_cast<void>(AttachEntityNPCStatics(state));

    // `EntityFamiliar`（批次 330）：`Entity:ToFamiliar()` 的返回值。与 `EntityNPC`/`EntityTear`/
    // `EntityLaser` **逐字同一形态** —— 字段回落到 `Entity` 的（`IndexEntity` 的 else 分支），
    // 方法先查本元表（`FollowParent`/`AddToFollowers`）、再回落 `Entity`
    // （所以 `familiar:GetSprite()` / `familiar.Player` 之类照旧能用）。
    // ★ 六处接线（照批次 285 的清单，一处都不能漏）：① 本块建元表；② `EntityView::Familiar`；
    //   ③ `EntityViewMetatable` 的分支；④ `EntityFamiliarIndex`；⑤ `CheckEntityHandle` 认它；
    //   ⑥ `EntityToFamiliar()` 改压它。
    luaL_newmetatable(state, kEntityFamiliarMetatable);
    lua_newtable(state);
    static_cast<void>(AttachEntityFamiliarMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, EntityFamiliarIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EntityNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    // `PathFinder`（批次 344，2026-10-04）：`EntityNPC.Pathfinder` 属性的返回值。
    // ★ 它与上面那几个视图**不同形**：不是"某个实体的下转视图"，而是 `Entity_NPC` 里**内嵌**
    //   的 `NPCAI_Pathfinder` 子对象（`Entity_NPC + 0x408`）⇒ 句柄自己持地址（`PathFinderHandle`），
    //   `__index` 也不走 `IndexEntity`（它没有 `Entity` 基类可回落，PC 里是独立类型）。
    // ★ 接线五处（照最小视图的成例）：① 本块建元表；② `kPathFinderMetatable`（头文件）；
    //   ③ `PathFinderIndex`；④ `PushPathFinderHandle`；⑤ `PushEntityNpcField` + `IndexEntity`
    //   的 `Npc` 分支（入口）。★ 少一处**不报错**，只是 `npc.Pathfinder` 恒 `nil` 或方法取不到。
    luaL_newmetatable(state, kPathFinderMetatable);
    lua_newtable(state);
    static_cast<void>(AttachPathFinderMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, PathFinderIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    // `TemporaryEffects`（批次 388，2026-10-07）：`EntityPlayer:GetEffects()` 的返回值。
    // ★ 与上面几个"下转视图"不同形：它不是某个实体的视图，而是一个**独立对象类**
    //   （PC 里 `TemporaryEffects` 自己一页、17 个方法）；句柄存拥有它的玩家地址，
    //   容器是 `Entity_Player` 的**内嵌子对象**（`+0x18D8`）。
    // ★ 接线四处（照最小视图的成例）：① 本块建元表；② `kTemporaryEffectsMetatable`（头文件）；
    //   ③ `TemporaryEffectsIndex`；④ `PushTemporaryEffectsHandle` + `EntityPlayerGetEffects`（入口）。
    //   少一处**不报错**，只是 `player:GetEffects()` 恒为 `nil` 或方法取不到。
    luaL_newmetatable(state, kTemporaryEffectsMetatable);
    lua_newtable(state);
    static_cast<void>(AttachTemporaryEffectsMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, TemporaryEffectsIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kTemporaryEffectMetatable);
    if(!RegisterNativeObjectIdentity(state,-1,TemporaryEffectIdentity))
        luaL_error(state,"TemporaryEffect identity resolver conflicts");
    lua_pushcfunction(state, TemporaryEffectIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, ReadOnlyEffectWrite);
    lua_setfield(state, -2, "__newindex");
    lua_pushliteral(state, "TemporaryEffect");
    lua_setfield(state, -2, "__type");
    lua_pushvalue(state, -1);
    lua_setfield(state, -2, "__class");
    lua_pop(state, 1);

    luaL_newmetatable(state, kEffectListMetatable);
    if(!RegisterNativeObjectIdentity(state,-1,EffectListIdentity))
        luaL_error(state,"EffectList identity resolver conflicts");
    lua_pushcfunction(state, EffectListIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, EffectListLength);
    lua_setfield(state, -2, "__len");
    lua_pushcfunction(state, ReadOnlyEffectWrite);
    lua_setfield(state, -2, "__newindex");
    lua_pushcfunction(state, EffectListGet);
    lua_setfield(state, -2, "Get");
    lua_pushliteral(state, "EffectList");
    lua_setfield(state, -2, "__type");
    lua_pushvalue(state, -1);
    lua_setfield(state, -2, "__class");
    lua_pop(state, 1);

    // 仅类元数据入口；这些原生视图没有公开构造器。
    for (const auto* name : {"TemporaryEffect", "EffectList"}) {
        lua_newtable(state);
        lua_newtable(state);
        luaL_getmetatable(state, std::strcmp(name, "TemporaryEffect") == 0 ? kTemporaryEffectMetatable : kEffectListMetatable);
        lua_setfield(state, -2, "__class");
        lua_setmetatable(state, -2);
        lua_setglobal(state, name);
    }

    // 类身份和原方法快照在任何作者包装前一次性发布，不创建伪实体。
    PublishNativeClass(state,"Entity",kEntityMetatable);
    for(const auto& cls : {std::pair<const char*,const char*>{"EntityPlayer",kEntityPlayerMetatable},
        {"EntityPickup",kEntityPickupMetatable},{"EntityProjectile",kEntityProjectileMetatable},
        {"EntityTear",kEntityTearMetatable},{"EntityBomb",kEntityBombMetatable},
        {"EntityLaser",kEntityLaserMetatable},{"EntityKnife",kEntityKnifeMetatable},{"EntityNPC",kEntityNPCMetatable},
        {"EntityFamiliar",kEntityFamiliarMetatable}}) {
        PublishNativeClass(state,cls.first,cls.second,kEntityMetatable);
    }
    PublishApi200Statics(state,"EntityFamiliar");
    PublishApi300Statics(state,"EntityEffect");
    RegisterApi400ProjectileParams(state);
    RegisterApi600PlayerTypes(state);
    RegisterApi600EntityPtr(state);
    RegisterApi600ConfigLists(state);
    RegisterApi600RoomConfigContainers(state);
    PublishApi400SeedsStatics(state);

    luaL_newmetatable(state, kItemConfigListMetatable);
    if(!RegisterNativeObjectIdentity(state,-1,ConfigListIdentity))
        luaL_error(state,"ItemConfig list identity resolver conflicts");
    lua_pushcfunction(state, ItemConfigListIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, ItemConfigListLength);
    lua_setfield(state, -2, "__len");
    lua_pushcfunction(state, ItemConfigListNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pop(state, 1);

    // PC实际全局路径：CppContainer.Vector.ItemConfigList，供类身份比较使用。
    lua_getglobal(state, "CppContainer");
    if (!lua_istable(state, -1)) { lua_pop(state, 1); lua_newtable(state); }
    lua_getfield(state, -1, "Vector");
    if (!lua_istable(state, -1)) { lua_pop(state, 1); lua_newtable(state); }
    lua_newtable(state);
    lua_newtable(state);
    luaL_getmetatable(state, kItemConfigListMetatable);
    lua_setfield(state, -2, "__class");
    lua_setmetatable(state, -2);
    lua_setfield(state, -2, "ItemConfigList");
    lua_setfield(state, -2, "Vector");
    lua_setglobal(state, "CppContainer");

    luaL_newmetatable(state, kItemConfigMetatable);
    if(!RegisterNativeObjectIdentity(state,-1,ConfigRootIdentity))
        luaL_error(state,"ItemConfig identity resolver conflicts");
    lua_newtable(state);
    static_cast<void>(AttachItemConfigMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, ItemConfigIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kItemConfigItemMetatable);
    lua_newtable(state);
    static_cast<void>(AttachItemConfigItemMethods(state));
    lua_setfield(state, -2, "__methods");
    lua_pushcfunction(state, ItemConfigItemIndex);
    // 部分配置数值在PC可写，仍使用真实条目身份和原字段写者。
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state,ExtendedItemConfigWrite);lua_setfield(state,-2,"__newindex");
    lua_pop(state, 1);
}

} // namespace

std::uintptr_t ResolveContentConfigRoot(bool entityConfig) noexcept {
    const auto items=ResolveItemConfig(nullptr);
    if(!entityConfig)return items;
    if(items<kManagerItemConfigOffset)return 0;
    const auto manager=items-kManagerItemConfigOffset;
    return manager<=UINTPTR_MAX-kManagerEntityConfigOffset?manager+kManagerEntityConfigOffset:0;
}

int Api500PushConfigString(lua_State*state,std::uintptr_t address) {
    if(!PushLibcxxString(state,address,true))lua_pushnil(state);
    return 1;
}

int ExtendedItemConfigWrite(lua_State* state) {
    const auto item=ItemConfigPointerArgument(state,1);const char* field=luaL_checkstring(state,2);
    const auto*handle=CheckItemConfigItemHandle(state,1);
    if(TryWriteApi500ConfigField(state,item,handle->beginOffset,field))return 0;
    if(item&&TryWriteExtendedItemConfigField(state,item,field))return 0;
    return luaL_error(state,"ItemConfigItem has no writable field named %s",field);
}

bool ResolveEngineStringView(std::uintptr_t object,EngineStringView* view) noexcept {
 if(!view)return false;
 LibcxxStringView value{};
 if(!ResolveLibcxxString(object,true,&value))return false;
 view->data=value.data;view->size=value.size;return true;
}

std::uintptr_t Api200ItemConfigReceiver(lua_State* state,int index) {
 auto*handle=CheckItemConfigHandle(state,index);
 const auto config=ValidatedItemConfig(handle);
 if(!config)luaL_error(state,"ItemConfig reference is no longer available");
 return config;
}
int Api200PushNullItemView(lua_State*state,std::uintptr_t item,std::int32_t index) {
 if(!item){lua_pushnil(state);return 1;}
 ItemVectorView view{};const auto config=ResolveItemConfig();
 if(index<0||!ReadItemVector(config,kItemConfigNullItemBeginOffset,kItemConfigNullItemEndOffset,&view)||
    static_cast<std::size_t>(index)>=view.count)
    return luaL_error(state,"ItemConfig native returned an unavailable null item");
 std::uintptr_t actual{};
 if(!ReadEngine(view.begin+static_cast<std::size_t>(index)*sizeof(std::uintptr_t),&actual)||actual!=item)
    return luaL_error(state,"ItemConfig native returned an unavailable null item");
 PushItemConfigItemHandle(state,item,kItemConfigNullItemBeginOffset,view.begin,static_cast<std::size_t>(index));return 1;
}

std::uintptr_t ResolveEngineReceiver(lua_State* state,FieldReceipt receipt,int index) {
    return ResolveFieldReceipt(state,receipt,index);
}

std::uintptr_t ItemConfigPointerArgument(lua_State* state,int index) noexcept {
    auto* item=static_cast<ItemConfigItemHandle*>(luaL_testudata(state,index,kItemConfigItemMetatable));
    return ValidatedItem(item);
}

std::size_t RegisterIsaacApi(lua_State* state) noexcept {
    if (state == nullptr) {
        return 0;
    }
    // 每个 Lua 状态创建时调用一次：stub 告警与帧计数都是"每会话"口径，在这里归零
    // （实体 `GetData` 的 Lua 表存储也在这里清空，见 `ResetEntityDataStore`）。
    ResetSessionState();
    // 只读视图的元表要先建好：`Isaac.GetPlayer` / `Isaac.GetItemConfig` 一旦返回 userdata，
    // 元表就必须已经存在。
    RegisterViewMetatables(state);
    // 全局 `GetPtrHash`：PC 的全局函数（`GlobalFunctions.md:143`），EID 在实体身份比较里用。
    // 它**不是**某个对象的方法，所以不进 `AttachOwnerMethods`（catalog 里 owner 是 `Global`）。
    // `Global:GetPtrHash` **有** catalog id（`MakeId(ApiDomain::Global, 1, 0x1F)`）
    // ⇒ 直接用真 id，读数里就能自动显示成 `Global:GetPtrHash`。
    isaac::runtime::PushHandler(state, GlobalGetPtrHash, 0, 0x0001001FU);
    lua_setglobal(state, "GetPtrHash");
    isaac::runtime::PushHandler(state, GlobalRandom, 0, 0x00010021U);
    lua_setglobal(state, "Random");
    PushHandler(state,Api600RandomVector,0,0x0001163AU);lua_setglobal(state,"RandomVector");
    // 全局 `ItemConfig` 常量表（`ItemConfig.TAG_*`）。理由见 `PublishItemConfigConstants`。
    PublishItemConfigConstants(state);
    lua_newtable(state);
    const std::size_t attached = AttachIsaacMethods(state);
    lua_setglobal(state, "Isaac");
    RegisterCoreObjectPointerIdentities(state);
    return attached;
}

namespace {

bool IsLanguageCodeByte(char value) noexcept {
    return (value >= 'a' && value <= 'z') || (value >= '0' && value <= '9') || value == '_';
}

bool ReadLanguageCodeString(std::uintptr_t address, char* output, std::size_t capacity) noexcept {
    if (address == 0 || output == nullptr || capacity < 2) {
        return false;
    }
    for (std::size_t index = 0; index + 1 < capacity; ++index) {
        char value = 0;
        if (!IsEngineMemoryReadable(address + index, sizeof(value))) {
            return false;
        }
        std::memcpy(&value, engine_memory::AsObject(address + index), sizeof(value));
        if (value == '\0') {
            output[index] = '\0';
            return index != 0;
        }
        if (!IsLanguageCodeByte(value)) {
            return false;
        }
        output[index] = value;
    }
    output[capacity - 1] = '\0';
    return output[0] != '\0';
}

bool ReadCurrentLanguageCode(char* output, std::size_t capacity) noexcept {
    if (output == nullptr || capacity < 2) {
        return false;
    }
#if !defined(__SWITCH__)
    if (g_CurrentLanguageCodeHostImplementation != nullptr) {
        const char* injected = g_CurrentLanguageCodeHostImplementation();
        if (injected == nullptr) {
            return false;
        }
        std::size_t length = 0;
        while (length + 1 < capacity && injected[length] != '\0' &&
               IsLanguageCodeByte(injected[length])) {
            output[length] = injected[length];
            ++length;
        }
        output[length] = '\0';
        return length != 0;
    }
#endif
    const std::uintptr_t base = EngineModuleBase();
    if (base == 0 || base > UINTPTR_MAX - kGameManagerGlobalSlotOffset ||
        base > UINTPTR_MAX - kManagerGetLanguageCodeOffset) {
        return false;
    }
    std::uintptr_t managerSlot = 0;
    std::uintptr_t manager = 0;
    if (!ReadEngine(base + kGameManagerGlobalSlotOffset, &managerSlot) || managerSlot == 0 ||
        !ReadEngine(managerSlot, &manager) || manager == 0) {
        return false;
    }
    const std::uintptr_t method = base + kManagerGetLanguageCodeOffset;
    std::array<u8, kManagerGetLanguageCodeExpectedBytes.size()> actual{};
    if (!ReadEngine(method, &actual) || actual != kManagerGetLanguageCodeExpectedBytes) {
        return false;
    }
    using GetLanguageCodeFn = const char* (*)(void*);
    const char* code =
        engine_call::AsFunction<GetLanguageCodeFn>(method)(engine_memory::AsObject(manager));
    return ReadLanguageCodeString(engine_memory::AddressOf(code), output, capacity);
}

} // namespace

namespace {

// PC getter0x832E50直读float；setter0x832E60的上限立即数0x3C23D70A是0.01，
// 与文档0..1不一致，但这是本项目实际PC映像。只复刻Lua setter，菜单仍由引擎按0..1调整。
std::uintptr_t CurrentHudOffsetAddress() noexcept {
    const auto manager = ResolveManagerAddress();
    return manager != 0 && manager <= UINTPTR_MAX - kManagerHudOffsetOffset
               ? manager + kManagerHudOffsetOffset : 0;
}

int OptionsNewIndex(lua_State* state) {
    const char* key = lua_tostring(state, 2);
    if (key != nullptr && std::strcmp(key, "DebugConsoleEnabled") == 0) {
        LuaRuntime::SetDebugConsoleEnabled(lua_toboolean(state, 3) != 0);
        return 0;
    }
    if(TryWriteApi700Option(state,key)){return 0;}
    if(TryWriteRuntimeOption(state,key)){return 0;}
    if (key != nullptr && std::strcmp(key, "FoundHUD") == 0) {
        const auto manager = ResolveManagerAddress();
        const std::uint8_t value = lua_toboolean(state, 3) != 0 ? 1U : 0U;
        if (manager == 0 || manager > UINTPTR_MAX - kManagerFoundHudOffset ||
            !WriteEngine(manager + kManagerFoundHudOffset, value)) {
            return luaL_error(state, "Options.FoundHUD is not writable");
        }
        return 0;
    }
    if (key != nullptr && std::strcmp(key, "HUDOffset") == 0) {
        float value = static_cast<float>(luaL_checknumber(state, 3));
        if (value < 0.0F) { value = 0.0F; }
        if (value > 0.01F) { value = 0.01F; }
        const auto address = CurrentHudOffsetAddress();
        if (address == 0 || !WriteEngine(address, value)) {
            return luaL_error(state, "Options.HUDOffset is not writable");
        }
        return 0;
    }
    lua_rawset(state, 1);
    return 0;
}

int OptionsIndex(lua_State* state) noexcept {
    const char* key = lua_tostring(state, 2);
    if (key != nullptr && std::strcmp(key, "DebugConsoleEnabled") == 0) {
        lua_pushboolean(state, LuaRuntime::DebugConsoleEnabled());
        return 1;
    }
    if(TryPushApi700Option(state,key)){return 1;}
    if(TryPushRuntimeOption(state,key)){return 1;}
    if (key != nullptr && std::strcmp(key, "FoundHUD") == 0) {
        const auto manager = ResolveManagerAddress();
        std::uint8_t value = 0;
        if (manager == 0 || manager > UINTPTR_MAX - kManagerFoundHudOffset ||
            !ReadEngine(manager + kManagerFoundHudOffset, &value)) {
            lua_pushnil(state);
            return 1;
        }
        lua_pushboolean(state, value != 0);
        return 1;
    }
    if (key != nullptr && std::strcmp(key, "HUDOffset") == 0) {
        float value = 0.0F;
        const auto address = CurrentHudOffsetAddress();
        if (address == 0 || !ReadEngine(address, &value)) { lua_pushnil(state); return 1; }
        lua_pushnumber(state, value);
        return 1;
    }
    if (key != nullptr && std::strcmp(key, "Language") == 0) {
        char languageCode[16] = {};
        if (!ReadCurrentLanguageCode(languageCode, sizeof(languageCode))) {
            std::memcpy(languageCode, "en", 3);
        }
        lua_pushstring(state, languageCode);
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

} // namespace

std::size_t RegisterOptionsTable(lua_State* state) noexcept {
    if (state == nullptr) {
        return 0;
    }
    lua_newtable(state);
    // PC 文档定义 `Options.HUDOffset` 为 0..1 的 float；EID 的定位公式以此为输入，默认 1.0
    // 表示不做额外偏移。此前误用 EID 配置里的 0..10 整数，导致描述被推到右下角。
    // 2026-10-09更正：上面的固定默认已退役，HUDOffset每次读取真实字段，写入也落回引擎。
    // 不在表内存同名键，避免绕开__index/__newindex变成影子配置。
    // `Language` 是只读动态字段：EID 在整个会话中会反复读取它，不能在初始化时缓存。
    // 引擎切换语言后，下一次 `Options.Language` 会重新调用 `Manager::GetLanguageCode()`。
    lua_newtable(state);
    lua_pushcfunction(state, OptionsIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, OptionsNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_setmetatable(state, -2);
    lua_setglobal(state, "Options");
    return 4;
}

#if !defined(__SWITCH__)
namespace { ManagedUpdateSnapshotReader g_ManagedUpdateSnapshotReader{}; }
void SetManagedUpdateSnapshotReaderForTest(ManagedUpdateSnapshotReader reader) noexcept {
    g_ManagedUpdateSnapshotReader = reader;
}
#endif

bool ShouldDispatchManagedUpdates(ManagedUpdateSnapshot* snapshot) noexcept {
    if (!snapshot) return false;
    *snapshot = {};
#if defined(__SWITCH__)
    if (!LuaRuntime::IsOnGameThread()) return false;
    return ReadNativeManagedUpdateSnapshot(ResolveGameAddress(), LuaRuntime::GameIsPausedThunk(),
        kGameFrameCountOffset, snapshot, &engine_memory::EngineMemoryReadable);
#else
    const auto paused = ObserveGameIsPaused(LuaRuntime::GameOwnerSlot(), LuaRuntime::GameIsPausedThunk());
    if (paused != GameIsPausedObservation::PausedFalse &&
        paused != GameIsPausedObservation::ThunkUnavailable) return false;
    // 宿主默认没有原生simulation；仅明确安装快照reader的场景参与同帧去重。
    if (!g_ManagedUpdateSnapshotReader) return true;
    return LuaRuntime::IsOnGameThread() && g_ManagedUpdateSnapshotReader(snapshot) && snapshot->game != 0;
#endif
}

bool ShouldDispatchManagedCallbacks() noexcept {
#if defined(__SWITCH__) && !defined(EXL_DIAGNOSTIC_STAGE)
    if (EngineModuleBase() == 0 || ResolveRoom() == 0) {
        return false;
    }
    // 退房过渡期会出现“room 仍非空、player 已经失效”的窗口。只检查 room 会让 EID 进入该
    // 窗口并拿到 nil player；必须同时要求至少一个可验证玩家。
    const EnginePlayerArray players = ResolveEnginePlayerArray();
    return players.readable && players.count != 0;
#else
    return true;
#endif
}

// `Isaac.GetPlayer` 的成功/失败计数（原因 1）：EID 的 `EID.player` 依赖它；恒失败则
// `OnRender` 里的 `for ... in ipairs({ EID.player })` 一次都不执行，描述的第一步永不发生。


PlayerLookupProbe PlayerLookupProbeSnapshot() noexcept {
    PlayerLookupProbe probe{};
    probe.getPlayerSuccess = g_GetPlayerSuccess.load(std::memory_order_relaxed);
    probe.getPlayerFailure = g_GetPlayerFailure.load(std::memory_order_relaxed);
    return probe;
}

// --- 每帧事件（回调面地基）需要的"游戏侧视图" ----------------------------------
//
// 这三个入口存在的唯一理由：`lua_runtime.cpp` 的每帧事件派发要知道"房间里现在有哪些实体、
// 其中哪些是掉落物、玩家是谁"，而这三件事的实现（vptr 校验、实体容器指纹、实体句柄与元表）
// 全归本 TU 所有。让派发侧自己再写一份，等于把"什么算一张活的 Entity"变成两份会漂移的实现
// —— `IsLiveEntityPointer` 当初被导出的理由完全一样。

void VisitRoomEntities(EntityVisitFn visit, void* context) noexcept {
    if (visit == nullptr) {
        return;
    }
    const std::uintptr_t room = ResolveRoom();
    if (room == 0 || !EntityListFingerprintMatches(room + kRoomEntityListOffset)) {
        return;
    }
    const std::uintptr_t list = room + kRoomEntityListOffset;
    // 枚举用"房间内活动实体全集"（`EL+0x78`）—— 与 `Isaac.GetRoomEntities` 同一张表。
    ForEachEntityInTable(list, kLiveEntityTable,
                         [visit, context](std::uintptr_t entity) { visit(context, entity); });
}

void VisitPlayerEntities(EntityVisitFn visit, void* context) noexcept {
    if (visit == nullptr) {
        return;
    }
    const std::uintptr_t game = ResolveGameAddress();
    if (game == 0) {
        return;
    }
    ForEachPlayerEntity(game, [visit, context](std::uintptr_t entity) { visit(context, entity); });
}

std::uintptr_t EntityPointerArgument(lua_State* state, int index) noexcept {
    if (state == nullptr || index <= 0) {
        return 0;
    }
    // 与CheckEntityHandle共用全部视图的识别入口；非实体/退役token返回0，不抛错。
    return ValidatedEntity(TryGetEntityHandle(state, index));
}

bool IsPickupEntity(std::uintptr_t candidate) noexcept {
    // 判据只有一份（实体分类那条）：这里改成转调，免得同一件事在两个地方各写一遍、日后漂开。
    return ClassifyCallbackEntity(candidate) == CallbackEntityClass::Pickup;
}

CallbackEntityClass ClassifyCallbackEntity(std::uintptr_t candidate,
                                          std::int64_t* callbackFilter) noexcept {
    // 分类只需要身份字段，保持一次范围/vptr校验，不读取位置、尺寸或容器下标。
    EntitySnapshot snapshot{};
    if (!CaptureEntityTypeSnapshot(candidate, &snapshot)) {
        return CallbackEntityClass::None;
    }
    // 复用分类快照：NPC按Type、刀按SubType、其它族按Variant过滤，不新增每回调内存查询。
    if (callbackFilter != nullptr) {
        *callbackFilter = snapshot.variant;
    }
    const std::uintptr_t base = EngineModuleBase();
    // 玩家 / 掉落物 / 跟班：PC 上这三类是**具体的 C++ 类**，所以判据必须是"`Type` 对得上
    // **且** vptr 精确等于那个类的 vtable"—— 与 `Entity:ToPlayer()` / `ToPickup()` /
    // `ToFamiliar()` 逐字一致。只比 `Type` 会把"某个子类把 Type 写成 1/5/3"误判。
    if (snapshot.type == kEntityTypePlayer && base != 0 &&
        base <= UINTPTR_MAX - kEntityPlayerVtableOffset &&
        snapshot.vtable == base + kEntityPlayerVtableOffset) {
        return CallbackEntityClass::Player;
    }
    if (snapshot.type == kEntityTypePickup && base != 0 &&
        base <= UINTPTR_MAX - kEntityPickupVtableOffset &&
        snapshot.vtable == base + kEntityPickupVtableOffset) {
        return CallbackEntityClass::Pickup;
    }
    if (snapshot.type == kEntityTypeFamiliar && base != 0 &&
        base <= UINTPTR_MAX - kEntityFamiliarVtableOffset &&
        snapshot.vtable == base + kEntityFamiliarVtableOffset) {
        return CallbackEntityClass::Familiar;
    }
    // 剩下这几类**没有各自的 vtable 常量**（没取证过），判据只能取 `Type`：这几个值在 PC 的
    // `EntityType` 枚举里各自只对应一个类（见 `runtime_constants.hpp` 里那几个常量的注释）。
    if (snapshot.type == kEntityTypeTear) return CallbackEntityClass::Tear;
    if (snapshot.type == kEntityTypeProjectile) return CallbackEntityClass::Projectile;
    if (snapshot.type == kEntityTypeLaser) return CallbackEntityClass::Laser;
    if (snapshot.type == kEntityTypeKnife) {
        if (callbackFilter != nullptr) {
            *callbackFilter = snapshot.subType;
        }
        return CallbackEntityClass::Knife;
    }
    if (snapshot.type == kEntityTypeEffect) return CallbackEntityClass::Effect;
    if (snapshot.type == kEntityTypeBomb) return CallbackEntityClass::Bomb;
    // 敌人：引擎自己的判据（`IsEnemy = (u32)(Type - 10) < 0x3DE`）。
    // 注意顺序：`1000`（效果）落在该区间之外，所以上面那条效果判断不会被抢走。
    if (IsEnemyType(snapshot.type)) {
        if (callbackFilter != nullptr) {
            *callbackFilter = snapshot.type;
        }
        return CallbackEntityClass::Npc;
    }
    // 其余（例如 `ENTITY_SLOT(6)`、`variant == 0xEF` 的特殊跟班以外的未分类类型）一律不派发。
    return CallbackEntityClass::None;
}

void PushEntityCallbackArgument(lua_State* state, std::uintptr_t entity) noexcept {
    if (state == nullptr) {
        return;
    }
    // 视图与查询结果同一种（`EntityViewMetatableForPointer`）：PC 的回调实参也是**真类对象**，
    // 所以玩家给 `EntityPlayer`、掉落物给 `EntityPickup`、其余给 `Entity`。
    // 视图不一致会让模组在回调里直接调不到类方法（`player:HasCollectible()`、
    // `pickup:IsShopItem()` 这类），而现象只是"方法不存在"。
    PushEntityHandle(state, entity, EntityViewMetatableForPointer(entity));
}

void PushCollectibleRngCallbackArgument(lua_State* state,std::uintptr_t player,std::int32_t item) {
    lua_pushcfunction(state,EntityPlayerGetCollectibleRNG);
    PushEntityHandle(state,player,kEntityPlayerMetatable);
    lua_pushinteger(state,item);
    lua_call(state,2,1);
}
void ApplyUseItemCallbackAnimation(lua_State* state,std::uintptr_t player,std::int32_t item){
    lua_pushcfunction(state,EntityPlayerAnimateCollectible);
    PushEntityHandle(state,player,kEntityPlayerMetatable);lua_pushinteger(state,item);
    lua_pushliteral(state,"UseItem");lua_pushliteral(state,"PlayerPickupSparkle");
    lua_call(state,4,0);
}

void ApplyUseItemNativeRemoval(lua_State* state,std::uintptr_t player,std::int32_t item){
    static constexpr const EngineMethodRow* row=[]() constexpr {
        for(const auto& entry:kEntityPlayerEngineRows)if(entry.id==0x0E010084U)return &entry;
        return static_cast<const EngineMethodRow*>(nullptr);
    }();
    static_assert(row->id==0x0E010084U,"RemoveCollectible绑定必须存在");
    lua_pushlightuserdata(state,const_cast<EngineMethodRow*>(row));
    lua_pushcclosure(state,EngineMethodHandler,1);
    PushEntityHandle(state,player,kEntityPlayerMetatable);
    lua_pushinteger(state,item);lua_pushboolean(state,false);lua_pushinteger(state,-1);lua_pushboolean(state,true);
    lua_call(state,5,0);
}


int Api600ItemConfigGetCards(lua_State*L){return PushItemConfigList(L,kItemConfigCardBeginOffset,kItemConfigCardEndOffset);}
int Api600ItemConfigGetPillEffects(lua_State*L){return PushItemConfigList(L,kItemConfigPillEffectBeginOffset,kItemConfigPillEffectEndOffset);}
int Api600ItemConfigGetNullItems(lua_State*L){return PushItemConfigList(L,kItemConfigNullItemBeginOffset,kItemConfigNullItemEndOffset);}
int Api600ItemConfigItemIsNull(lua_State*L){
 const auto*h=CheckItemConfigItemHandle(L,1);const auto p=ValidatedItem(h);
 if(!p||h->beginOffset==kItemConfigCardBeginOffset||h->beginOffset==kItemConfigPillEffectBeginOffset)return luaL_error(L,"ItemConfigItem reference is unavailable");
 std::uint32_t type{};if(!ReadEngine(p,&type))return luaL_error(L,"ItemConfigItem Type is not readable");lua_pushboolean(L,type==0);return 1;
}
int Api600ItemConfigShouldAddCostumeOnPickup(lua_State*L){
 int index=1;if(luaL_testudata(L,1,kItemConfigMetatable))index=2;
 if(lua_isnoneornil(L,index)){lua_pushboolean(L,false);return 1;}
 const auto*h=CheckItemConfigItemHandle(L,index);const auto p=ValidatedItem(h);
 if(!p||h->beginOffset==kItemConfigCardBeginOffset||h->beginOffset==kItemConfigPillEffectBeginOffset)return luaL_argerror(L,index,"live ItemConfigItem expected");
 // Reuse the confirmed AddCostumeOnPickup native field and its complete layout guard.
 return TryPushApi500ConfigField(L,p,h->beginOffset,"AddCostumeOnPickup");
}
int Api600CardConfigListGet(lua_State*L){luaL_checkudata(L,1,kApi600CardListMetatable);return ItemConfigListGet(L);}
int Api600CardConfigListLen(lua_State*L){luaL_checkudata(L,1,kApi600CardListMetatable);return ItemConfigListLength(L);}
int Api600PillConfigListGet(lua_State*L){luaL_checkudata(L,1,kApi600PillListMetatable);return ItemConfigListGet(L);}
int Api600PillConfigListLen(lua_State*L){luaL_checkudata(L,1,kApi600PillListMetatable);return ItemConfigListLength(L);}
int Api600ConfigListIndex(lua_State*L){
 static_cast<void>(CheckConfigList(L,1));const char*key=lua_tostring(L,2);
 if(key&&!std::strcmp(key,"Size"))return ItemConfigListLength(L);
 if(!lua_getmetatable(L,1)){lua_pushnil(L);return 1;}lua_getfield(L,-1,"__methods");lua_pushvalue(L,2);lua_rawget(L,-2);return 1;
}
void RegisterApi600ConfigLists(lua_State*L){
 for(const auto&row:{std::pair<const char*,const char*>{"CardConfigList",kApi600CardListMetatable},{"PillConfigList",kApi600PillListMetatable}}){
  luaL_newmetatable(L,row.second);if(!RegisterNativeObjectIdentity(L,-1,ConfigListIdentity))luaL_error(L,"config list identity resolver conflicts");lua_pushcfunction(L,Api600ConfigListIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,ItemConfigListNewIndex);lua_setfield(L,-2,"__newindex");
  lua_newtable(L);static_cast<void>(AttachApi600Methods(L,row.first));lua_getfield(L,-1,"__len");lua_setfield(L,-3,"__len");lua_setfield(L,-2,"__methods");lua_pushstring(L,row.first);lua_setfield(L,-2,"__type");lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");lua_pop(L,1);
  lua_getglobal(L,"CppContainer");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);}lua_getfield(L,-1,"Vector");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);}
  lua_newtable(L);lua_newtable(L);luaL_getmetatable(L,row.second);lua_setfield(L,-2,"__class");lua_setmetatable(L,-2);lua_setfield(L,-2,row.first);lua_setfield(L,-2,"Vector");lua_setglobal(L,"CppContainer");
 }
}

} // namespace isaac::runtime
