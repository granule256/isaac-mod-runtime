#pragma once

// 数据驱动的引擎方法绑定。每条数据行描述接收者、参数、原生入口及返回类型，
// 共享处理器负责参数校验、入口指纹检查、调用和 Lua 返回值转换。
// AttachOwnerMethods 将数据行作为闭包上值，避免为每个 API 生成独立处理器。
// 需要自定义句柄、容器解析或动态选择签名的接口应使用专用处理器。

#include <cstddef>
#include <cstdint>

extern "C" {
#include "lua.h"
}

#include "interfaces/lua/field_api.hpp"

namespace isaac::runtime {

// EngineCallShape 是 kEngineCallShapes 数据表的索引。
// 参数和返回类型由描述符定义，实际调用由 EngineCallTrampoline 完成。
enum class EngineCallShape : std::uint8_t {
    Void0 = 0,   // `void (*)(this)`——例如 `EntityPlayer:AnimateHappy()`
    Void1 = 1,   // `void (*)(this, i32)`——例如 `EntityPlayer:AddCoins(int)`
    Void2 = 2,   // `void (*)(this, i32, i32)`——例如 `Game:ChangeRoom(int, int)`
    Int0 = 3,    // `i32 (*)(this)`——例如 `EntityPlayer:GetBlackHearts()`
    VoidFloat1 = 4,               // `void (*)(this, float)`——`RoomConfig_Spawn:PickEntry` 一类
    VoidIntIntIntHandleInt = 5,   // `void (*)(this, i32, i32, i32, EntityPlayer*, i32)`
    Bool0 = 6,                    // `bool (*)(this)`——例如 `Entity:IsFlying()`（无参、返回布尔）
                                  // ——`Game:StartRoomTransition(room, dir, anim, player, dim)`
    // 7 `void(this, i32)`，但参数要先过校验（`intGuard` 那一格说明校验什么）。
    // 适用：`EntityPlayer:AddNullCostume(int)` / `TryRemoveNullCostume(int)`
    // 收的是"null 服装编号"，编号无效时引擎会 `AddCostume(nullptr)` 解引用空指针（真机报告里
    // `Data Abort`、崩溃地址为零）—— 这一形状让共享处理器先把这种调用挡下、不往下调引擎。
    // 与 `Void1` 的 ABI 完全一样，差别只在"调之前多一道判定"。
    VoidNullId1 = 7,
    // 8 `i32(this, i32)` —— 加：`EntityPlayer:GetPill(int)` /
    // `GetCard(int)`（引擎 `Entity_Player::GetPill/GetCard(int) const`，EID 逐帧问）。
    // 在它之前"取一个整数参数、返回整数"只能手写处理器（`Int0` 只覆盖无参那一种）。
    Int1 = 8,
    // 9 `bool(this, i32)` —— 加：`EntityPlayer:HasPlayerForm(Form)`。
    Bool1 = 9,
    // 10 `void(this, u32& 入出参, u32& 入出参)` —— 加：
    // `EntityPlayer:GetGlyphOfBalanceDrop(variant, subtype)`。
    // 两个 Lua 参数既是入参又是出参：引擎把改写后的值写回我们造的槽；调用后共享处理器
    // 把两个槽读出来、压成一张两元表（返回种类 `U32PairTable`）。
    // ⇒ 本机制里第一个"引用出参 + 返回表"的形状。
    // PC 契约文档里查不到这条 API（它是 Repentogon 才有的，`tools/pc_contract_docs/EntityPlayer.md`
    // 里没有）⇒ Lua 侧的形状没有官方口径可对齐，唯一口径来自它唯一的消费者 EID：
    // `local t = player:GetGlyphOfBalanceDrop(Variant, SubType)` 之后读 `t[1]`（与 `-1` 比）
    // 与 `t[2]`（`features/eid_repentogon.lua:265`，仓库里有副本）。
    // 引擎侧的签名由反汇编证实：`void(this, uint&, uint&)`，只往 `x1`/`x2` 指向的槽写、
    // 唯一一个 `ret` 之前从不写 `w0`（的取证，见 `tools/lua_api_stub_ledger.json`）。
    Ref2U32Pair = 10,
    // 11 `bool(this, bool 可选)` —— 加：`Entity:IsActiveEnemy(bool includeDead)`。
    //
    // 为什么需要一种新形状、而不是直接复用 `Bool1`：这条 API 的尾部参数必须可以省略。
    // * MCM 不传（`modconfig.lua:206`：`entity:IsActiveEnemy()`）；
    // * `RepentancePlus/main.lua:697` 与 `IsaacOnTwitchReloaded/scripts/trinkets.lua:268`
    // 传布尔 `false` / `true`。
    // 而共享处理器原来要求"参数个数严格相等" ⇒ 0 参那条会直接报错、把整条模组回调摘掉。
    // 参数种类也必须是 `Bool` 而不是 `Int`：模组传的是 Lua 布尔，而 `IsIntegerArgument`
    // 走 `lua_isnumber` ⇒ 布尔会被判成"不是整数"而报错。
    //
    // `optionalArgumentCount` 那一格填 1 ⇒ "尾部 1 个参数可以不写"；省略时该寄存器保持 0
    // （= `includeDead == false`，正是 PC 的缺省值，取值证据见 `runtime_constants.hpp`
    // 的 `kEntityIsActiveEnemyOffset`：反汇编里 `includeDead` 直接以 `orr` 并入结果）。
    // 这段话里不能写成"字段名 = 数字"的样子：门禁
    // `test_engine_method_rows.shape_arity_table()` 用 `(\w+)\s*=\s*(\d+)` 扫这个枚举块，
    // 那种写法会被当成一个枚举值把整张形状表的编号挤错位（本次就是这么红的）。
    BoolOpt1 = 11,
    // 12 `void(this, i32, i32, bool)` —— 加：
    // `Room:RemoveGridEntity(int GridIndex, int PathTrail, boolean KeepDecoration)`
    // （PC 契约 `tools/pc_contract_docs/Room.md:725`）。第 3 个参数是 Lua 布尔
    // （语料实参：`BOIStageAPI15/.../roomHandler.lua` 的 `RemoveGridEntity(i, 0, false)`），
    // 而 `Void2` 只收两个整数、`VoidIntBool` 又少一格 ⇒ 需要这一种。
    VoidIntIntBool = 12,
    // 13 `bool(this, i32, i32, i32)`，尾部 1 个可省 ——
    // `Room:SetGridPath(int Index, int Value)`（PC 契约 `Room.md:795`）。
    // 文档只写 2 个参数，但引擎符号是 `SetGridPath(int, int, int)`（`_ZN…SetGridPathEiii`）
    // ⇒ 按符号取 3 格（G3 闸门：默认参数在 ABI 上照样占寄存器），
    // 语料只传 2 个（`shared.Room:SetGridPath(i, 0)`）⇒ 尾部 1 个可省、省略时保持 0。
    BoolIntIntInt = 13,
    // 14 `bool(this, i32, bool, bool)`，尾部 2 个可省 ——
    // `Room:DestroyGrid(int Index, boolean Immediate)`（PC 契约 `Room.md:63`）。
    // 符号 `_ZN…DestroyGridEibb` 是 3 格 ⇒ 按符号取；语料只传 1 个
    // （`IsaacOnTwitchReloaded/scripts/events.lua` 的 `room:DestroyGrid(ind)`）⇒ 尾部 2 个可省。
    BoolIntBoolBool = 14,
    // 15 `float(this)` —— `Level:GetPlanetariumChance()`
    // （PC 契约 `tools/pc_contract_docs/Level.md:187` 逐字 `float GetPlanetariumChance ( )`）。
    // 在这之前"无参、返回浮点"没有形状可用（`Int0` 取的是 `x0`、这条要取 `d0`）。
    Float0 = 15,
    // 16 `i32(this, bool, i32)` —— `Level:GetRandomRoomIndex(boolean IAmErrorRoom, int Seed)`
    // （PC 契约 `tools/pc_contract_docs/Level.md:198`）。第 1 个参数是 Lua 布尔
    // （语料实参：`MinimapAPI/.../main.lua` 的 `GetRandomRoomIndex(false, …)`）⇒ 必须 `Bool` 不是 `Int`。
    IntBoolInt = 16,
    // 17 `void(this, i32)`，尾部 1 个可省 ——
    // `MusicManager:DisableLayer(int)`（PC 契约 `tools/pc_contract_docs/MusicManager.md:47`；
    // 该参数带缺省值，文档写作 `LayerId` 缺省为 0）。
    // 这里的注释故意不写成「名字 = 数字」的形态：门禁
    // `test_engine_method_rows.shape_arity_table()` 用 `(\w+)\s*=\s*(\d+)` 扫这个枚举块，
    // 那种写法会被当成一个枚举值、把整张形状表的编号挤错位（本批真踩了一次）。
    // 与既有的 `Void1` 只差"可省"这一格：语料里 一个参数都不传
    // （`BOIStageAPI15/.../callbacks.lua` 的 `shared.Music:DisableLayer()`、
    // `MusicModCallback/.../repentance.lua` 同）⇒ 复用 `Void1` 会因为"参数个数严格相等"直接报错、
    // 把整条模组回调摘掉（正是`BoolOpt1` 那条教训）。
    VoidIntOpt1 = 17,
    // 18 `bool(this, i32)`，尾部 1 个可省 ——
    // `MusicManager:IsLayerEnabled(int)`（PC 契约 `MusicManager.md:87`；`LayerId` 带缺省值）。
    // 语料同样不传参数（`BOIStageAPI15/.../callbacks.lua` 的 `if shouldLayer and not shared.Music:IsLayerEnabled() then`）。
    BoolIntOpt1 = 18,
    // 19 `void(this, i32, bool)`，尾部 2 个可省 ——
    // `MusicManager:EnableLayer(int, boolean)`（PC 契约 `MusicManager.md:57`；
    // 两个参数都带缺省值，缺省都是 0/false）。语料不传参数（`shared.Music:EnableLayer()`）
    // ⇒ 省略时寄存器保持 0 恰好就是 PC 缺省。
    VoidIntBoolOpt2 = 19,
    // 20 `void(this, float, float)`，尾部 1 个可省 ——
    // `MusicManager:VolumeSlide(float, float)`（PC 契约 `MusicManager.md:130`；第 2 个参数带缺省值）。
    // 语料传 2 个（`musicmgr:VolumeSlide(0.1, 0.05)`），但既然有缺省就声明可省更稳
    // （省略时 `d1` 保持 0）。
    VoidFloatFloatOpt1 = 20,
    // 21 `void(this, i32, float)`，尾部 1 个可省 ——
    // `MusicManager:Crossfade(Music ID, float FadeRate)`（PC 契约 `MusicManager.md:35`，
    // 第 2 个参数带缺省值）。语料传 2 个（`MusicModCallback/scripts/mmc/repentance.lua:771`
    // 的 `musicmgr:Crossfade(correctedTrackNum(id), faderate)`）⇒ 省略时 `d1` 保持 0。
    // 引擎符号 `_ZN15IsaacRepentance5Music9CrossfadeENS_6eMusicEf` ⇒ `(this, i32, float)`。
    VoidIntFloatOpt1 = 21,
    // 22 `void(this, i32 × 5)` ——
    // `Room:SpawnGridEntity(int, GridEntityType, int, int, int)`（PC 契约 `Room.md:867`）。
    // 语料传满 5 个（`BOIStageAPI15/scripts/stageapi/room/roomHandler.lua:59` 的
    // `SpawnGridEntity(index, GridEntityType.GRID_WALL, 0, 1, 0)`）⇒ 全部必填。
    // 引擎符号 `_ZN15IsaacRepentance4Room15SpawnGridEntityEiNS_15eGridEntityTypeEjji`
    // ⇒ 5 个整数参数（第 3/4 个是 `uint`，ABI 上仍是 `x` 寄存器）。
// 2026-10-23更正：非模板函数mangled名称通常不包含返回类型，不能由其缺失断言void。
// NRO0x4525CC/0x45263C明确返回0/1，PC0x7AAA5C返回true；本入口保留原生bool。
    BoolIntIntIntIntInt = 22,
    // 23 `void(this, i32, bool, i32, bool)`，尾部 3 个可省 ——
    // `EntityPlayer:RemoveCollectible(CollectibleType, boolean, ActiveSlot, boolean)`
    // （PC 契约 `EntityPlayer.md:1588`）。
    // 语料只传 1 个（`IsaacOnTwitchReloaded/scripts/activeItems.lua:139` 的
    // `RemoveCollectible(Isaac.GetItemIdByName(...))`），而引擎符号是 4 格
    // ⇒ 尾部 3 个可省；省略时寄存器保持 0，而第 3 格的缺省 `ActiveSlot.SLOT_PRIMARY` 恰好是 0。
    // 引擎符号 `_ZN15IsaacRepentance13Entity_Player17RemoveCollectibleENS_16eCollectibleTypeEbib`。
    VoidIntBoolIntBoolOpt3 = 23,
    // 24 `bool(this, Vector2&, float)` —— `Room:IsPositionInRoom(Vector Pos, float Margin)`
    // （PC 契约 `Room.md:691`）。引擎符号是 `…ERKN4KAGE4Math7Vector2Ef` ⇒ 第 1 个参数是
    // `Vector2 const&`（引用 ⇒ 指针，走 `x` 寄存器），不是按值的 HFA。
    BoolVector2RefFloat = 24,
    // 25 `void(this, Vector2&, float, Entity*)` ——
    // `Game:CharmFart(Vector Position, float Radius, Entity Source)`（PC 契约 `Game.md:102`）。
    // 第 3 个参数是裸实体指针（`PNS_6EntityE`）⇒ 用既有的 `Handle` 种类（走 `x` 寄存器，
    // `nil` = 空指针）。
    VoidVector2RefFloatHandle = 25,
    // 26 `void(this, bool, i32, EntityPlayer*)` ——
    // `Game:MoveToRandomRoom(boolean IAmErrorRoom, int Seed, EntityPlayer Player)`
    // （PC 契约 `Game.md:424`）。三种参数种类都已在表里（`Bool` / `Int` / `Handle`），
    // 只是这个组合还没有行 ⇒ 这一条是"参数种类现成、只差一行描述符"。
    // 引擎符号 `_ZN15IsaacRepentance4Game16MoveToRandomRoomEbjPNS_13Entity_PlayerE`
    // ⇒ `(bool, i32, Entity_Player*)`；语料传满 3 个
    // （`BOIStageAPI15/scripts/stageapi/core/callbacks.lua:142` 的
    // `shared.Game:MoveToRandomRoom(false, shared.Room:GetSpawnSeed(), player)`）。
    VoidBoolIntHandle = 26,
    // 27 `bool(this, i32, bool, bool)`，尾部 2 个可省 ——
    // `ItemPool:RemoveCollectible(CollectibleType Collectible)`（PC 契约 `ItemPool.md:96`）。
    // PC 文档只写 1 个参数、引擎符号却是 3 格
    // （`_ZN15IsaacRepentance8ItemPool17RemoveCollectibleENS_16eCollectibleTypeEbb`）
    // ⇒ 按符号取形状（G3 口径：默认参数在 ABI 上照样占寄存器）。
    // 语料只传 1 个（`RepentancePlus/RepentancePlus/main.lua:474` 的
    // `itemPool:RemoveCollectible(collectibleType)`）⇒ 尾部 2 个可省、省略时保持 0。
    // 反汇编 `0x3C61F0` 证实：第 2 个 `bool` = "先做 ItemConfig 有效性判定"、
    // 第 3 个 `bool` = "只查不删"（dry-run）；两者取 0 恰好就是 PC 文档那句
    // 「移除并返回它是否本来在池里」的行为。返回值是 `bool`（`cset w0, eq`）。
    // 与的 `BoolIntBoolBool`（`Room:DestroyGrid`）参数种类一样、含义不同：
    // 那一条返回 `bool` 但 3 个参数全必填、且形参是 `(i32, bool, bool)`；
    // 这一条是 `(i32, bool, bool)` + 尾部 2 个可省 —— 复用前者会让"只传 1 个"的语料调用
    // 因参数个数不足直接报错、摘掉整条回调（`BoolOpt1` 那条教训的重演）。
    BoolIntBoolBoolOpt2 = 27,
    // 28 `bool(this, i32, i32, i32, i32)` ——
    // `EntityNPC:Morph(EntityType type, int Variant, int SubType, int ChampionColorIdx)`
    // （PC 契约 `tools/pc_contract_docs/EntityNPC.md:117` 逐字 `boolean Morph ( … )`）。
    // 引擎符号 `_ZN15IsaacRepentance10Entity_NPC5MorphENS_11eEntityTypeEjji` ⇒ 4 个整型参数
    // （`EntityType` 在 ABI 上就是 `i32`），返回布尔（`mov w0, w20`）。
    // 为什么复用不了既有的 `BoolIntIntInt`（`Room:SetGridPath`，只有 3 格）：这条有 4 格。
    BoolIntIntIntInt = 28,
    // 29 `void(this, i32, i32, i32, bool, bool, bool)`，尾部 3 个可省 ——
    // `EntityPickup:Morph(EntityType Type, int Variant, int SubType, boolean KeepPrice, boolean KeepSeed, boolean IgnoreModifiers)`
    // （PC 契约 `tools/pc_contract_docs/EntityPickup.md:40`；后 3 个布尔都带缺省值）。
    // 引擎符号 `_ZN15IsaacRepentance13Entity_Pickup5MorphENS_11eEntityTypeEjjbbb` ⇒ 3 个 `i32` + 3 个 `bool`。
    // 语料两种写法都有（3 参走缺省 / 6 参写全）⇒ 省略时寄存器保持 0 恰好就是 PC 的缺省 `false`；
    // 复用 `Void2` 那类会因为"参数个数严格相等"直接报错、把整条模组回调摘掉（的教训）。
    VoidIntIntIntBoolBoolBoolOpt3 = 29,
    // 30 `void(Vector2 const&, Entity*, Vector2 const&, bool, float)` ——
    // `EntityNPC.ThrowSpider(Vector Position, Entity Spawner, Vector TargetPos, boolean Big, float YOffset)`
    // （PC 契约 `tools/pc_contract_docs/EntityNPC.md:165`，逐字写着 `static const EntityNPC`）。
    // 引擎符号 `_ZN15IsaacRepentance10Entity_NPC11ThrowSpiderERKN4KAGE4Math7Vector2EPNS_6EntityES3_bf`
    // ⇒ 5 个形参、没有 `this`（契约 5 参 vs 符号 5 参，逐字对得上）。
    //
    // 这是本项目第一种"静态调用"（`EntityNPC.ThrowSpider(...)` 是点号直呼在类名上）：
    // AAPCS64 下没有 `this` 占 `x0`，于是五个形参自己排寄存器 ——
    // 整数/指针一路：`Vector2 const&`→`x0`、`Entity*`→`x1`、`Vector2 const&`→`x2`、`bool`→`w3`；
    // 浮点独立一路：`float`→`s0`。形状表里前 5 格就是按这个顺序写的。
    // ⇒ 这一档形状多了一个标记（`EngineCallShapeRow::staticCall`，见那一格），
    // 处理器据此不从栈上取接收者、`integers[0]` 也让给第一个实参。
    // 返回 `EntityNPC`（句柄）⇒ 用 `EngineReturnKind::EntityNpc`（同批新加）。
    StaticVoidVector2RefHandleVector2RefBoolFloat = 30,
    // 31 `void(int, Vector2 const&, float, int, Vector2 const&, Entity*, bool)` ——
    // `EntityLaser.ShootAngle(int Variant, Vector SourcePos, float AngleDegrees, int Timeout,
    // Vector PosOffset, Entity Source)`（PC 契约 `tools/pc_contract_docs/EntityLaser.md:146`，
    // 逐字 `static EntityLaser`）。
    // 引擎符号 `_ZN15IsaacRepentance12Entity_Laser10ShootAngleEjRKN4KAGE4Math7Vector2EfiS5_PNS_6EntityEb`
    // ⇒ 7 个形参、没有 `this`。契约写 6 个、符号 7 个 ⇒ 差的第 7 格是 `bool`；
    // 去读了 PC 那条绑定（`0x8C7550`）：它也收 7 个参数
    // （`movzx ecx, byte ptr [ebp + 0x20]` 就是第 7 格）并原样转发给 `Game::Spawn`
    // ⇒ PC 与 Switch 签名一致，差的只是 C++ 缺省值 ⇒ 按"尾部 1 个可省"处理
    // （`optionalArgumentCount 为 1`，省略时保持 0）。这正是批 282 当时排除它的那条理由，
    // 现在被推翻了（当时把"契约少写一个"当成了"引擎真的少一个"）。
    //
    // 这是第二种静态形状（`EntityNPC.ThrowSpider` 是第一种）：同样带
    // `EngineCallShapeRow::staticCall()` 标记 ⇒ 处理器不从栈上取接收者、`integers[0]` 让给第一个实参。
    // 实参映射（无 `this`）：`Variant`→`x0`、`SourcePos`→`x1`、`Timeout`→`x2`、`PosOffset`→`x3`、
    // `Source`→`x4`、第 7 个 `bool`→`w5`；浮点独立一路 `AngleDegrees`→`s0`。
    StaticIntVector2RefFloatIntVector2RefHandleBool = 31,
    // 32 `void(this, Vector2 const&, i32, Vector2 const&, bool, bool, Entity*, float)`，
    // 尾部 3 个可省 ——
    // `EntityPlayer:FireTechLaser(Vector Position, LaserOffset OffsetID, Vector Direction,
    // boolean LeftEye, boolean OneHit = false, Entity Source = nil, float DamageMultiplier 的缺省是 1)`
    // （PC 契约 `tools/pc_contract_docs/EntityPlayer.md:728`）。是实例方法（有 `this`）。
    // 引擎符号 `_ZN15IsaacRepentance13Entity_Player13FireTechLaserERKN4KAGE4Math7Vector2E
    // NS0_12eLaserOffsetES5_bbPNS_6EntityEf` @ `0x2B9020` ⇒ 7 个形参（`this` 之外），
    // 契约 7 参 = 符号 7 参（与 `ShootAngle` 那类不同：这一条没有"契约少写"的问题）。
    // 它是第一种用到 `EngineArgKind::FloatDefaultOne` 的形状：最后那一格
    // `DamageMultiplier` 的缺省是 `1` 而不是 `0` ⇒ 省略时必须填 `1.0`。
    // 语料那 1 处（`IsaacOnTwitchReloaded/scripts/events.lua:1828`）传 5 个
    // （省掉 `Source` 与 `DamageMultiplier`）⇒ 两条缺省都要生效。
    Vector2RefIntVector2RefBoolBoolHandleFloatOpt3 = 32,
    // 33 `void(this, i32, bool)`，尾部 1 个可省 ——
    // `EntityPlayer:ChangePlayerType(PlayerType)` 与 `EntityPlayer:DischargeActiveItem(ActiveSlot)`。
    //
    // 这两条在 PC 契约里各只写 1 个形参（`EntityPlayer.md:581` / `:642`），
    // 而引擎符号都是 2 格（`…ChangePlayerTypeENS_11ePlayerTypeEb` @ `0x2AACCC`、
    // `…DischargeActiveItemEib` @ `0x2B9540`，mangled 末尾的 `b` 就是那个 `bool`）
    // ⇒ 按 G3 口径"默认参数在 ABI 上照样占寄存器" 取 2 格、尾部 1 个可省。
    // 与既有的 `VoidIntBoolOpt2`（`MusicManager:EnableLayer`，尾部 2 个可省）不是同一个形状：
    // 那一条连第 1 格都能省（0 参调用合法），而这两条的第 1 格必填（语料都传了 1 个）
    // ⇒ 复用会让"一个参数都不传"也放行，与 PC 不一致。省参数个数的区间必须精确。
    // 省略的那一格保持 0 = PC 的缺省：`DischargeActiveItem` 的 `ActiveSlot` 缺省是
    // `SLOT_PRIMARY`（= 0）；`ChangePlayerType` 的 `bool` 在契约里根本没有、vanilla 文档
    // 里所有带缺省值的形参缺省都是 0/false/nil ⇒ 取 0。逐条的反汇编证据（含
    // "为什么对语料那两处是惰性的"）写在 `runtime_constants.hpp` 的段。
    VoidIntBoolOpt1 = 33,
    // 34 `void(this, Vector2 const&)` ——
    // `EntityFamiliar:FollowPosition(Vector Pos)`（PC 契约 `tools/pc_contract_docs/EntityFamiliar.md:70`）。
    //
    // 引擎真身 `Entity_Familiar::follow_position(Vector2 const&) @ 0xAFCC0`
    // （入口字 `0xD100C3FF`）—— `x1` 是指针（`Vector2 const&`）。
    // 这条推翻了的负结果（"符号在、但函数体从不读实参"）：见
    // `runtime_constants.hpp` 段的逐条路线说明（守卫成立支确实不用实参，
    // 但守卫不成立支 `0xAFD20` 的 `mov x0, x1` 用的就是原始实参）。
    // 形状本身不需要新机制：`EngineArgKind::Vector2Ref`早就把
    // "Lua `Vector` → 拷进我们栈上的槽 → 把槽地址放进 `x` 寄存器"做完了
    // ⇒ 本档只是"一个 `Vector2Ref` 参数 + 返回 `void`"这一种组合的纯数据行。
    VoidVector2Ref = 34,
    // 35 `bool(this, Vector2 const&, bool)` ——
    // `PathFinder:HasPathToPos(Vector Pos, boolean IgnorePoop)`
    // （PC 契约 `tools/pc_contract_docs/PathFinder.md:64`；本批 vendor 进来的那一页）。
    //
    // 引擎真身 `NPCAI_Pathfinder::HasPathToPos(Vector2 const&, bool) const @ 0x42F6CC`
    // （入口字 `0xA9BA7BFD`）—— `x1` 是指针（`Vector2 const&`）、`w2` 是布尔、返回 `w0`。
    // 形状本身不需要任何新机制：`EngineArgKind::Vector2Ref`与
    // `EngineArgKind::Bool`、`EngineReturnKind::Bool` 三样都早已存在 ——
    // 这一档只是它们的组合（此前一直没有人用到这个组合）⇒ 纯数据、0 代码。
    // 接收者是本批新开的 `FieldReceipt::PathFinder`（严格校验句柄类型）：
    // 这一条是调用，拿错对象当 `this` 会野读（理由见 `field_api.hpp` 那一档）。
    // 两个形参都必填（契约没写缺省、语料那 1 处两个都传）⇒ 可省个数是 0。
    BoolVector2RefBool = 35,
    // 2026-10-20：Level:AddCurse 的两个必填参数，保留Lua布尔真值。
    VoidIntBool = 36,
    // Seeds:SetStartSeed 接文档字符串，也保留现有数字重载。
    VoidSeed1 = 37,
    // PC main.lua:853-857：AddTrinket(id, value) 把省略/nil补true，false保持false，忽略额外参数。
    VoidIntBoolDefaultTrueOpt1 = 38,
    // PC void(this) binding reads only its receiver and ignores trailing Lua values.
    Void0IgnoreExtra = 39,
};

// 参数校验语义：形状用它声明"某个整数参数在调进去之前必须先验一遍"。
//
// 为什么放在形状里而不是每一行：`EngineMethodRow` 是 16 字节的满结构（没有空位），
// 而"要不要验"是签名语义的一部分（同一种 ABI 的不同用法）；形状行恰好有保留字节可用
// ⇒ 加一种校验只花一行描述符数据、0 字节代码，与"形状本身也是数据"同一口径。
enum class IntArgumentGuard : std::uint8_t {
    None = 0,             // 不校验（绝大多数行）
    ValidNullItemId = 1,  // 第 1 个整数参数必须是有效的 null 服装编号（见 `IsValidNullItemId`）
};

// 一个参数在 ABI 上属于哪一类（决定进 `x` 寄存器还是 `d` 寄存器、以及怎么从 Lua 栈上取值）。
enum class EngineArgKind : std::uint8_t {
    Int = 0,     // Lua 整数 → 下一个 `x` 寄存器
    Float = 1,   // Lua 数值 → 下一个 `d` 寄存器（与整数各自独立计数）
    Bool = 2,    // Lua 布尔 → 下一个 `x` 寄存器（0/1）
    Handle = 3,  // Lua 句柄（userdata）→ 引擎对象指针 → 下一个 `x` 寄存器；
                 // 传 `nil` 时按空指针（PC 的可选对象参数默认就是 nil）；校验方式见
                 // `EngineCallShapeRow::handleReceipt`
    // 批次 252（2026-10-01）：Lua 的 `Vector`（userdata，两个 float）→ 拷进我们自己的
    // 一个 8 字节槽 → 把槽的地址放进下一个 `x` 寄存器。
    //
    // 为什么是指针而不是按值：引擎里这几条收的都是 `Vector2 const&`
    // （mangled 名里的 `RKN4KAGE4Math7Vector2E`）⇒ ABI 上就是一个指针参数。
    // 这一条把原本以为要"扩跳板"的一整类（"Vector 进"）变成了纯数据：
    // `Room:IsPositionInRoom` / `Game:CharmFart` / `Game:SpawnParticles` /
    // `Room:FindFreeTilePosition`（后两条还各自带返回或更多参数）都能走既有跳板。
    // 槽是共享处理器里的函数内 `static` 数组（`vectorSlots`）：真实契约只要求
    // "调用期间有效"，而用局部数组会让"到底拷进去了没有"不可测（宿主测试只能在脚本跑完
    // 之后读，那时栈已经被复用）。static 只是把生命周期拉长，不影响引擎侧（`const&` 只读、
    // 且引擎调用在托管回调里同步发生、不会重入）。
    Vector2Ref = 4,
    // 5 —— 省略时要填 `1.0`（不是 `0`）的浮点参数。
    //
    // 背景：`optionalArgumentCount` 那一档的语义是"省略的寄存器保持 0"，它那一格的注释
    // 也写着"只有缺省值就是 0/false/空指针的参数能用这一格"。但 PC 契约里确实有
    // 缺省是非 0 的浮点参数 —— 典型是伤害倍率：
    // `EntityPlayer:FireTechLaser(…, boolean OneHit = false, Entity Source = nil,
    // float DamageMultiplier 的缺省是 1)`（`tools/pc_contract_docs/EntityPlayer.md:728`）。
    // 用 `Float` 那一档会把省略的 `DamageMultiplier` 填成 `0.0`（激光伤害变 0），那是真差异。
    //
    // ⇒ 做法：新增这一种参数种类。它被给出时与 `Float` 完全一样（Lua 数值 → 下一个 `d` 寄存器）；
    // 被省略时（只可能出现在尾部）共享处理器把那一格写成 `1.0`。
    // 实现见 `EngineMethodHandler` 里"补省略的尾部"那一段 —— 只多一个 `if`，
    // 而且对既有的形状一个字节都不改（它们的省略格照旧保持 0）。
    // 为什么不做成"手写处理器"：这条只有 1 处、本身没有算法，缺的只是"缺省值不是 0"
    // 这一个表达能力 ⇒ 补进机制比手写划算（手写 ≈ 190 字节代码，机制只多一个枚举值 + 几行）。
    FloatDefaultOne = 5,
    Seed = 6, // 字符串走原生String2Seed；数字直接保留原整数ABI。
    IntOrZero = 7, // PC脚本 value or 0：nil/false为0，其余保持整数校验。
    BoolDefaultTrue = 8, // PC脚本 value ~= false：只有布尔false为假，nil/省略为真。
};

// 返回值怎么解释（跳板把 `x0` 与 `d0` 都回填，这里只说读哪一个）。
enum class EngineReturnKind : std::uint8_t {
    Void = 0,
    Int = 1,    // `x0` 低 32 位按整数压回
    Bool = 2,   // `x0 != 0`
    Float = 3,  // `d0` 按浮点压回
    // 4 —— 加：不算 `x0`，而是把 `Ref2U32Pair` 那两个"出参槽"
    // 读回来、压成一张两元表（`{[1]=槽1, [2]=槽2}`）。本项目里第一个"返回表"的形状。
    //
    // 为什么这在跳板的能力边界之内：`engine_call_trampoline.hpp` 的边界管的是
    // "参数与返回值只能是标量（`x0`/`d0`）"，而那两个槽是我们自己栈上的内存、
    // 参数以"指针"的形式进 `x1`/`x2` —— 指针本来就属于跳板支持的整数组参数。
    // ⇒ 不需要动跳板，只要共享处理器在"调用前把参数换成槽地址、调用后把槽读出来组表"。
    U32PairTable = 4,
    // 5 —— 加：句柄返回。`x0` 是引擎交回的对象指针，
    // 按这一档的"哪种句柄"压成对应的 userdata（`PushEntityHandle`）。
    //
    // 为什么需要它：`EntityNPC.ThrowSpider` / `EntityPlayer:FireTear` / `EntityPlayer:FireTechLaser` /
    // `EntityLaser.ShootAngle` 这四条在 PC 上都返回一个句柄（`EntityNPC`/`EntityTear`/`EntityLaser`），
    // 而原来那 5 种只覆盖标量/表 ⇒ 照旧实现只能"什么都不返回"，与 PC 不一致。
    //
    // 为什么一种句柄一个枚举值（而不是"值 + 句柄类字段"）：`EngineCallShapeRow` 只剩
    // `reserved[2]` 可以借（`reserved[0]` 已被 `staticCall` 占掉），而一个 enum 值不占空间；
    // 真按"加字段"做会顶破 16 字节的 `static_assert`（= 涨价）。
    // 引擎返回空指针时压 `nil`（PC 口径：拿不到就 `nil`，不是报错）。
    EntityNpc = 5,
    // 6 —— 同上，但压的是 `EntityLaser` 句柄
    // （`EntityLaser.ShootAngle(...)` 的返回）。
    EntityLaser = 6,
};

// 一行描述符 = 一种签名（参数种类 + 返回种类）。16 字节只读数据、0 字节代码。
//
// 为什么参数上限是 8：AAPCS64 的寄存器参数就是 `x0..x7` 与 `d0..d7`；本项目的引擎方法
// 都落在这个范围内。超过 8 个（或需要栈上传参、结构体返回）的那类，继续手写。
struct EngineCallShapeRow {
    std::uint8_t argumentCount;        // Lua 侧参数个数（不含接收者），0..8
    EngineArgKind argumentKinds[8];    // 前 `argumentCount` 个有效
    EngineReturnKind returnKind;
    FieldReceipt handleReceipt;        // `Handle` 参数用哪套句柄校验（其余情况忽略）
    IntArgumentGuard intGuard;         // 整数参数校验语义（；`None` = 不校验）
    // 尾部几个参数可以不写（0 = 全部必填）。
    // 省略的那些寄存器保持 0 —— 所以只有"缺省值就是 0/false/空指针"的参数能用这一格
    // （`Entity:IsActiveEnemy(bool includeDead)` 的缺省就是 `false`）。
    // 它占的是原来 `reserved[4]` 的第一格：结构体仍是 16 字节，
    // 行体积（= 成本前提）没有任何变化，所以是"加能力不涨价"。
    std::uint8_t optionalArgumentCount;
    // 静态调用标记（`reserved[0] != 0`）。
    //
    // 到目前为止共享处理器无条件把 `integers[0]` 留给 `this`：
    // `int integerCount = 1;`，并按 `row->receipt` 从 Lua 栈上解析接收者。
    // 而静态成员函数（`EntityNPC.ThrowSpider(...)` 这种点号直呼在类名上的写法）
    // 根本没有 `this` —— 五个实参自己就排满 `x0..x3` 与 `s0`。
    //
    // ⇒ 这一格置 1 时：① 不从栈上取接收者（`receiverArguments = 0`）；
    // ② `integers[0]` 让给第一个实参（`integerCount` 从 0 起）；
    // ③ 跳过接收者解析那段（否则 `x0` 会被覆盖、且"接收者为 0"会被误判成降级）。
    // 用 `reserved[0]` ⇒ 结构体仍是 16 字节（下面那条 `static_assert` 管着）⇒ 加能力不涨价。
    std::uint8_t reserved[3];          // 凑满 16 字节（改结构体先看下面的 static_assert）

    // 这一行是不是"静态调用"（没有 `this`）—— 见上面 `reserved[0]` 那段。
    [[nodiscard]] constexpr bool staticCall() const noexcept { return reserved[0] != 0U; }
    [[nodiscard]] constexpr bool ignoresExtraArguments() const noexcept { return reserved[1] != 0; }
};

static_assert(sizeof(EngineCallShapeRow) == 16,
              "EngineCallShapeRow 必须保持 16 字节（同 EngineMethodRow 的成本前提）");

// 一行 = 一个 API。字段顺序按"对齐后最小"排：4+4+4+1+1+1+1 = 16 字节。
// "按 vtable 槽号调用"的行约定。
//
// 背景：有一批引擎方法是虚函数（`Entity:CanShutDoors()` / `GridEntity:Destroy(bool)` /
// `GridEntity:PostInit()` …）—— 它们的 PC 绑定本体不调某一个具体函数，而是
// `mov eax,[ecx]; jmp [eax+偏移]`（PC 侧有一整张这样的跳板表在 `0x8604E0` 起）。
// 这类方法不能写成普通的引擎方法行：普通行按"模块基址 + 固定偏移 + 入口指纹"定位，
// 而虚函数要调哪一个实现取决于接收者的动态类型，运行期才知道。
//
// ⇒ 约定：`offset` 的最高位置 1 表示"这一行是虚调用"，低 31 位 = vtable 槽号。
// 真实引擎偏移都远小于 `0x10000000`，这个哨兵不会与它们相撞（`engine_offset_abi_report`
// 与签名台账里的偏移都在 `0x00xxxxxx` 量级）。
//
// 槽号必须从 Switch 镜像的 `_ZTV<类>` 里读（见 `runtime_constants.hpp` 的段
// 怎么读：槽 `i` 在 `vtable + 0x10 + i*8`，靠 `R_AARCH64_ABS64` 重定位 + 符号索引解出）。
// 不许照抄 PC 的槽号 —— 两边的 vtable 布局差一个析构槽（Itanium 在开头放两个析构变体、
// MSVC 只放一个）⇒ PC 的槽号通常比 Switch 小 1。实测：`CanShutDoors` PC 是第 17 条、
// Switch 是第 18 条。
//
// `entryWord`（入口指纹）在这种行里没有意义（目标运行期才知道）⇒ 写 0，
// 处理器也不做指纹核对；取而代之的护栏是：
// ① 槽号有上界（`kEngineVtableMaximumSlot`）；
// ② `[receiver]`（vptr）与 `[vptr + 0x10 + slot*8]`（目标）两级都必须可读且非 0；
// ③ 任一级失败 ⇒ 不调、也不报错，只记一条 `EngineRowRejectReason::Vtable`。
inline constexpr std::uint32_t kEngineVtableRowFlag = 0x80000000U;

// 槽号上界：引擎里最深的 vtable 也远不到 256 条（`Entity` 约 26 条、`GridEntity` 约 12 条）
// ⇒ 超过它一定是把行写错了（或者 vptr 读到的不是真 vtable），按"调不进去"处理。
inline constexpr std::uint32_t kEngineVtableMaximumSlot = 255U;

// 槽 i 在 `vptr + i*8`（`vptr` = 对象首字）——不要再加 `0x10`！
//
// 为什么：Itanium ABI 里 `_ZTV<类>` 符号指向的是 `[offset-to-top][typeinfo]` 那 16 字节
// （所以"槽 0"相对符号是 `+0x10`），而对象首字存的就是 `_ZTV + 0x10` ——
// 也就是槽 0 自己的地址。三条独立证据（常量值都在 `runtime_constants.hpp` 里取过证）：
//
// * `_ZTVEntity_NPC`  `0xA35DA8 + 0x10 = 0xA35DB8` = `kEntityNpcVtableOffset` ✓
// * `_ZTVGridEntity`  `0xA37880 + 0x10 = 0xA37890` = `kGridEntityVtableOffset` ✓
// * `_ZTVEntity`      `0xA34F48 + 0x10 = 0xA34F58` = `kEntityVtableRangeBeginOffset` ✓
// * 另有代码侧印证：`IsEntityPlayer()` 判的就是 `*(u64*)candidate == base + kEntityPlayerVtableOffset`
// —— 拿对象首字与那个常量直接相等比较，说明那个常量就是"对象首字该有的值"。
//
// 的第一版这里加了 `0x10`，于是读的是"槽号 + 2"那一格 ——
// 真机上 `CanShutDoors()`（槽 18）会去调槽 20 的 `IsValidTarget`（还少传一个实参）。
// 宿主用例当时没能发现：夹具是照着实现写的（引用了同一个 `kEngineVtableSlotsOffset`）
// ⇒ 两边一起漂。修正：实现改成 `+ i*8`，夹具改成按"对象首字 = 槽 0"独立推导
// （写 `vptr + 18*8`，不再引用机制自己的常量）。
inline constexpr std::uintptr_t kEngineVtableSlotStride = sizeof(std::uintptr_t);  // = 8

// 把槽号打包成行里的 `offset`（读的时候用 `& ~kEngineVtableRowFlag` 取回来）。
[[nodiscard]] constexpr std::uint32_t MakeEngineVtableRowOffset(std::uint32_t slot) noexcept {
    return kEngineVtableRowFlag | (slot & ~kEngineVtableRowFlag);
}

// 这一行的 `offset` 是不是"虚调用槽号"。
[[nodiscard]] constexpr bool IsEngineVtableRow(std::uint32_t offset) noexcept {
    return (offset & kEngineVtableRowFlag) != 0U;
}

struct EngineMethodRow {
    std::uint32_t id;             // catalog id（必须与 `api_catalog.cpp` 里那条对得上）
    std::uint32_t offset;         // 引擎方法相对模块基址的偏移
    std::uint32_t entryWord;      // 入口首 4 字节（小端整字），调用前核对
    FieldReceipt receipt;         // 接收者怎么解（复用字段那套：EntityPlayer / Level / Room …）
    EngineCallShape shape;        // 参数表 + 返回类型
    std::uint8_t argumentCount;   // Lua 侧应收的整数参数个数（不含接收者）
    std::uint8_t probeBit;        // `api_sequence_probe.hpp` 的位号；`0xFF` = 不记
};

// 一行必须正好 16 字节。这是这套机制的成本前提：行变大就会削弱
// "每个 API 只花一行数据"的结论。改结构体先看这条断言。
static_assert(sizeof(EngineMethodRow) == 16, "EngineMethodRow 必须保持 16 字节（见成本说明）");

// 引擎方法类的共享处理器。行通过闭包上值传入（见 `AttachOwnerMethods`）。
//
// 错误消息按 catalog 里的 `owner`/`name` 现拼（与手写处理器同口径）：拼消息只在出错路径上做，
// 稳态零成本。
//
// 拿不到接收者 / 拿不到方法 / 指纹不匹配时不报错（按 PC 语义降级：返回 void 就什么都不做、
// 返回整数就压 0）—— 报错会把整条模组回调摘掉，而那比"这一次没生效"严重得多。
[[nodiscard]] int EngineMethodHandler(lua_State* state);

// 取签名描述符表（`EngineCallShape` 的索引就是它的下标）。表定义在 `isaac_api.cpp` 的
// 匿名命名空间里，所以用访问器而不是 `extern` 数组。门禁按它核对"行里的参数个数与形状一致"。
[[nodiscard]] const EngineCallShapeRow* EngineCallShapeRows(std::size_t* count) noexcept;

// `IntArgumentGuard::ValidNullItemId` 的判定结果。
enum class NullItemIdVerdict : std::uint8_t {
    Valid = 0,        // 编号指向容器里的一个真实条目（引擎不会崩）
    Invalid = 1,      // 确认无效（负数 / 越界 / 空槽）⇒ 调用方应当挡下、不调引擎
    Undecidable = 2,  // 判定不了（`ItemConfig` 那条链当时读不到）⇒ 照 PC 那样子调进去
};

// 这个编号是否指向引擎的 null 服装容器里的一个真实条目（`ItemConfig::GetNullItem(id)`
// 会返回非空）—— 加。
//
// 判据与 `Isaac:GetCostumeIdByPath` 同一条链、同一份常量（实现放在同一处），两处各写一遍就会
// 漂移 —— 而漂移的后果是"我们以为无效、其实有效"（吞掉正常调用）或反过来（挡不住崩溃）。
//
// 返回 `Undecidable` 时调用方放行并计数（`g_IsaacNullCostumeGuardUnknown`，应当恒 0）：
// 宁可照 PC 那样子调进去，也不要因为我们自己读不到就把模组的合法调用吞掉。
[[nodiscard]] NullItemIdVerdict CheckNullItemId(std::int64_t id) noexcept;

// `Music:Play` / `MusicManager:Play` 的编号判定结果。
enum class MusicIdVerdict : std::uint8_t {
    Valid = 0,        // 编号指向曲目表里的一个真实条目（引擎不会崩）
    Invalid = 1,      // 确认无效（负数 / 越界）⇒ 调用方应当静默挡下、不调引擎
    Undecidable = 2,  // 判定不了（曲目表那条链当时读不到）⇒ 照 PC 那样子调进去并计数
};

// 这个编号能不能安全地喂给引擎的 `Music::Play(eMusic, float)` —— 加。
//
// 为什么必须有它（真机事故 `dist/crash-153-20260927-1121.log`）：引擎按
// `条目 = *(Music + 0x3D8) + id * 0x70` 取曲目（`Music::Play @ 0x427238` 的 `umaddl`），
// `id = -1` 就是读到表前面去 ⇒ `Data Abort`（`Fault Address = 0`，崩在 `Music::Play + 0x68`）。
//
// 与 PC 的有意偏离（写在明处，可被推翻）：`MusicManager.md:102` 那一页记着
// "ID 为负或越界时 PC 会崩游戏"，所以 `music_api.cpp` 里原来刻意不挡（"与 PC 一致"）。
// 但 PC 上模组拿到的编号不会是 `-1` —— 因为 PC 的模组 `content/music.xml` 在模组脚本
// 看到它之前就已经加载好了。我们这边会因为自己的加载时机而出现这个窗口 ⇒ 那是我们的缺口，
// 不该让玩家承担一次崩溃。所以这里挡：`Invalid` 静默跳过（不报 Lua 错，避免把整条回调摘掉）
// 并记 `g_MusicPlayGuardBlocked`；`Undecidable` 照旧放行并计数（宁可放行也不吞掉合法调用）。
[[nodiscard]] MusicIdVerdict CheckMusicId(std::int64_t id) noexcept;

} // namespace isaac::runtime
