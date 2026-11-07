#pragma once

#include <cstddef>
#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// 2026-10-16原件更正（下面旧记录完整保留，不能再按旧偏移实施）：
// 当前NS Game::BombDamage355380..3553BC构造并把sp+20作为TakeDamage的EntityRef参数。
// Type+0、Variant+4、SpawnerType+8、SpawnerVariant+C；Position+10、偏移Vector+18、
// 标志+20、源指针+28。PC80403B..804057的字段登记独立确认四个整数格，
// SpawnerType按signed32、SpawnerVariant按unsigned32。Lua两字段已补，旧Type/Variant排布纠正；
// Native输入转发前0x30字节，不再只复制三处。完整原件见dist/apis600-20261016。
// 构造前缀已静态验证，不等同于完整原生EntityRef引用树/销毁后地址复用已真机验收。
//
// ============================================================================
// `EntityRef`：PC 的"实体引用"值类型
// ============================================================================
//
// **为什么要有它**：GoodTrip 的诅咒房过路费（`scripts/trip.lua:70`）是
// `player:TakeDamage(n, flags, EntityRef(player), 0)` —— 它**随时**可能出现（穿过刺房就要付），
// 而那两句里 `EntityRef` 是我们原来完全没有的全局 ⇒ 报
// "attempt to call a nil value (global 'EntityRef')"，整条诅咒房传送断掉。
//
// **为什么按"裸缓冲区"实现**：引擎把它**按引用**读（`Entity::TakeDamage(float, EntityRef const&, int)`），
// 也就是说外壳下面是引擎自己的 `Entity::EntityRef` 结构体；我们只是**替 Lua 持有那块内存**。
// 因此布局必须与引擎一致，而布局是从消费者反推出来的（取证）：
//
//   * `+0x00`（4 字节）= `Variant`：
//     `Entity::AddFreeze(EntityRef const&, int)` @ `0x5E358` 把 `[x1,#0x0]` 与 1/3/8 比较；
//   * `+0x08`（4 字节）= `Type`：
//     `Entity::IgnoreEffectFromFriendly` @ `0x5DBC8` 用 `[x1,#0x8] == 1`（`ENTITY_PLAYER`）判"友方"；
//     `AddFreeze`/`AddPoison` @ `0x5E5F8` 同样拿它比 1/3；
//   * `+0x28`（8 字节）= **源实体指针**：
//     `Entity::compute_poison_damage` @ `0x5E2E8` 两处 `ldr x9,[x1,#0x28]`，且
//     `compute_status_effect_duration` @ `0x5E274` 取它之后沿 `[entity+0x3a8]` 走链、再读
//     `[entity+0x38]`（=`Entity::Type`）—— 当作 `Entity*` 用的证据最硬；
//   * 其余格子（`+0x10..+0x20` 等）**没有证据**：一律**清零**，不猜语义。
//     已知后果：依赖那些字段的引擎分支按"空值"处理（`+0x28` 为空指针时引擎自己会跳过源实体相关逻辑）。
//
// **还没做**：PC 的 `EntityRef` 还有 `Position`/`SubType` 等字段。等有证据再补；
// 现在多填一格错误的值比"留空"更危险。
//
// 缓冲区大小在 `runtime_constants.hpp`（`kEntityRefStorageSize`，对象尺寸都住那里）。

// `EntityRef(entity)`：PC 的构造器（无参时是"空引用"，`TakeDamage` 用它表示"没有来源"）。
[[nodiscard]] int CreateEntityRefHandle(lua_State* state);

// 元表的 `__index`：暴露 `Type` / `Variant` / `Entity` 三个字段（都从缓冲区里读）。
[[nodiscard]] int EntityRefIndex(lua_State* state);

// 取句柄里的缓冲区指针（`Entity:TakeDamage` 要把这个指针交给引擎）。
// 第 `index` 个实参不是 `EntityRef` 句柄 ⇒ 返回 `nullptr`（调用方决定降级方式）。
[[nodiscard]] void* EntityRefBufferAt(lua_State* state, int index) noexcept;

// 把引擎传给我们的 `Entity::EntityRef const&`（一个指针）变成
// Lua 侧的 `EntityRef` 句柄，用来当回调实参压栈（`MC_ENTITY_TAKE_DMG` 的第 4 个实参 `Source`）。
//
// 与 `CreateEntityRefHandle` 的差别：那个是从**实体指针**现造（只填 Entity/Type/Variant，
// 其余留空）；这个是从**引擎已经填好的引用**里搬 —— 只搬三个有证据的格子
// （`Variant@0x00` / `Type@0x08` / `Entity@0x28`，证据见上），其余仍清零（不猜）。
// `engineRef == 0` ⇒ 压一个空引用（全零），与 `EntityRef(nil)` 同义。
void PushEntityRefArgument(lua_State* state, std::uintptr_t engineRef) noexcept;

} // namespace isaac::runtime

// 拥有值的PC可写Position/IsFriendly/IsCharmed；const借用仍只读。
namespace isaac::runtime { [[nodiscard]] int EntityRefNewIndex(lua_State*); }

// 第七批原件追加：PC804057登记Position+10，getter856530返回Vector值副本、
// setter8565D0接受Vector整体赋值；PC80405E/65登记IsCharmed/IsFriendly，
// getter4A9690/48EFE0读+20位0/1，setter7FA4A0/7FA480只改相应位。
// 拥有值和回调快照可写三字段；GetLastDamageSource为独立const活视图，禁止写入。
// 原生EntityRefBufferAt优先核活视图，再沿用既有裸storage格式，不把视图解释为storage。
