#pragma once

// 数据驱动的字段读取绑定。共享处理器校验参数和接收者、检查内存可读性，
// 再按 FieldKind 读取并返回 Lua 值；失败时使用对应接口族的约定值。
// 字段偏移来自已验证的布局表，FieldApiRow 通过闭包上值传入处理器。
// 需要动态参数、复杂计算或原生函数调用的接口应使用专用处理器。

#include <cstddef>
#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

// 接收者从哪个族的 Lua 参数上解出来（决定用哪套句柄校验）。
enum class FieldReceipt : std::uint8_t {
    Entity = 0,          // `Entity`/`EntityPlayer`/`EntityPickup` 三张元表都接受
    EntityPlayer = 1,    // 必须是精确的 `Entity_Player` vptr
    ItemConfigItem = 2,  // `ItemConfig_Item`
    Level = 3,           // `Game`/`Level`（引擎里 Level 内嵌在 Game 起始处，解析链同一条）
    // `Room = 4`（2026-09-19，引擎方法数据行那一批要用）：**不从 Lua 栈上取**，
    // 而是解析"当前房间"（`ReadCurrentGameRoom`）。给 `Room:PlayMusic()` 这类
    // "没有参数、但需要 this = 当前房间"的方法用。语义上它仍是"接收者"，所以放在这套枚举里。
    Room = 4,
    // `Music = 5`（2026-09-30 ）：`MusicManager:*` 的接收者。也不从 Lua 栈上取。
    //
    // 为什么必须这么解：PC 的 `MusicManager()` 在我们这边返回的是一个**占位句柄**
    // （`CreateMusicHandle` 只放了一个保留字、不持引擎指针，见 `MusicHandle`），
    // 所以栈上那个 self 里**根本没有** `Music*`。引擎里 `Music` 是 `Manager` 内嵌的子对象
    // （`Manager + kManagerMusicOffset`）⇒ 与 `Room`（解析"当前房间"）同一口径：
    // 接收者是**算出来的**，不是从参数里拿的。
    //
    // 与 `ResolveMusicForCall`（`lua_runtime.cpp`，`Pause`/`Resume`/`Play`/`UpdateVolume` 用）
    // 拿到的是**同一个对象**：那条链的两跳是"当前回调的 Manager → 本帧 `Manager::Update` 的 self"，
    // 它自己的注释写明"两者是同一个单例"；这里走全局槽那条链
    // （`kGameManagerGlobalSlotOffset`，与 `Isaac:GetMusicIdByName` 同一条），
    // 好处是**不依赖"正在托管回调派发里"**这个前置条件。
    Music = 5,
    // `ItemPool = 6`（2026-10-01 ）：`ItemPool:*` 引擎方法数据行的接收者。
    // **也不从 Lua 栈上取**：`ItemPool` 句柄（`ItemPoolHandle`）与 `Room`/`Music` 同形 ——
    // 只有一个保留字节、**不持引擎指针**（方法每次从全局槽现查）。所以接收者按
    // `game_observer.hpp` 的 `ReadCurrentGameItemPool(GameOwnerSlot(), …)` 解析 ——
    // 与既有的手写 `GameGetItemPool` / `ItemPoolGetCollectible` **同一条链、同一份判据**。
    ItemPool = 6,
    // `RoomConfigData = 7`（2026-10-02 ）：`Room:` 族里字段住在房间配置对象里的那些
    // API 的接收者 —— 也就是 `Room → RoomDescriptor → RoomConfig::Room` 这条**固定的两跳指针链**
    // 的末端。**也不从 Lua 栈上取**：`RoomHandle` 与 `Room`/`Music`/`ItemPool` 同样是不持引擎
    // 指针的空壳，接收者只能算出来。
    //
    // 为什么需要"两跳"而不是像 `Room` 那样一跳就够：这一格的语义正是 PC 侧那条链。
    // PC 的 `Room:GetRoomShape()` 本体（`0x444C30`）就是
    //   `mov eax,[ecx+0x4]`（描述符）→ `test/je` → `mov eax,[eax+0x10]`（配置对象）→
    //   `test/je` → `mov eax,[eax+0x48]`（形状）→ `ret`，两跳都 NULL 时返回常量 1（1x1）。
    // Switch 侧同一个形状被 `Room::IsLShapedRoom() const @ 0x48453C` 用**逐字同形**的两跳读出来
    // （只是偏移各差 4/16 字节，见 `runtime_constants.hpp` 的段）。
    //
    // 两跳的偏移都是**已确认的布局常量**（`Room+0x8` = 描述符指针；描述符 `+0x10` = `Data`），
    // 不是这里现编的；`offset` 字段则相对**末端**那个对象算（`Data + 0x5C` = 形状）。
    RoomConfigData = 7,
    // `RoomDescriptor = 8`（2026-10-02 ）：`Room:` 族里字段住在房间描述符上的那些
    // API 的接收者 —— 也就是「当前房间 → `Room + 0x8` → `RoomDescriptor`」这**一跳**链的末端。
    // **也不从 Lua 栈上取**（同 `Room`/`RoomConfigData`：`RoomHandle` 是不持引擎指针的空壳）。
    //
    // 为什么单独收一个，而不是复用 `Room`/`RoomConfigData`：
    //   * 复用 `Room` 会读到 `Room` 自己同偏移上的别的东西（`Room + 0x50` 与描述符 `+0x50`
    //     是**两个不同**的字段）；
    //   * 复用 `RoomConfigData` 更远 —— 那个末端是 `RoomConfig::Room`，偏移要相对它算。
    // 本项目里"同名偏移落在不同基对象上"的例子不止一个（`Music+0x1D0` 与 `Backdrop+0x1D0`；
    // `Room+0x1D1C` 与 `Entity_Player+0x1D1C`）。**静默给错值比报错更糟**，所以宁多一个 receipt。
    //
    // 两条偏移都是**已确认的布局常量**（`kRoomDescriptorPointerOffset` = `Room+0x8`），
    // 不是这里现编的；行的 `offset` 相对**描述符**算（`+0x50` = `RoomDescriptor.Flags`）。
    RoomDescriptor = 8,
    // `GridEntity = 9`（2026-10-03 ）：`GridEntity:*` 引擎方法行（本批是两条虚函数：
    // `Destroy(bool)` / `PostInit()`）的接收者 —— **从 Lua 栈上取**，与 `Room` 那几档不同：
    // `Room:GetGridEntity(i)` 交回的是**真持引擎指针**的句柄（`GridEntityHandle` / `DoorHandle`
    // 里的 `entity`），所以直接读栈上那一个就行。
    //
    // 为什么要新开一档而不是复用 `Entity`：`GridEntity` 与 `Entity` 在引擎里是两棵独立的
    //   类型树**（各自的 vtable 区间**有重叠**，见 `kGridEntityVtableRangeBeginOffset` 那条注释），
    //   句柄也是两张不同的元表 ⇒ 复用 `Entity` 那份判据会把网格实体判成"不是实体"（反之亦然）。
    // 存活判据用 `IsLiveGridEntityPointer`（立的那一条），与手写路径同一份。
    GridEntity = 9,
    // `EntityFamiliar = 10`（2026-10-03 ）：`EntityFamiliar:*` 引擎方法行的接收者。
    // **从 Lua 栈上取**（与 `EntityPlayer` 同形）：`Entity:ToFamiliar()` 交回的是**真持引擎指针**
    // 的 `EntityHandle`，所以读栈上那一个就够。
    //
    // 为什么新开一档、不复用 `Entity`：这两条 API 是调用（不是读字段）。
    //   `Entity_Familiar::follow_parent()` 的**第一条字段访问**就是 `ldr x8,[x0,#0xf50]`，
    //   紧跟 `cbz x8` 之后**解引用**它 ⇒ 拿一个别的实体当 `this` 交进去会**野读**。
    //   而 `Entity` 那一档只做 vtable **区间**校验（区间里几十个子类都放行）⇒ 不够。
    //   本档要求**精确**的 `base + kEntityFamiliarVtableOffset` 且 `Type == ENTITY_FAMILIAR`
    //   （判据与 `Entity:ToFamiliar()` 的那条**同一份**实现：`ValidatedEntityFamiliar`）。
    //
    // 顺带说明为什么 `EntityNPC` 不用单开一档：它的两条字段行（`GetChampionColorIdx` /
    //   `GetBossColorIdx`）是**读** `Entity_NPC + 0xD0F`/`+0xD10` —— 看错类型只会读到别人的值
    //   （实体对象都够大、不会越界），不会顺着垃圾指针跑。**读与调的危险等级不同。**
    EntityFamiliar = 10,
    // `Seeds = 11`（2026-10-03 ）：`Seeds:*` 引擎方法行的接收者。
    // **不从 Lua 栈上取** —— `Seeds` 句柄（`SeedHandle`）与 `Room`/`Music`/`ItemPool` 同形：
    // 空壳、不持引擎指针，接收者每次从 `Game` 现算。
    //
    // 解析链 = `模块基址 → g_Game 全局槽 → Game* → Game + kGameSeedsObjectOffset`。
    // 前两跳**逐字复用** `FieldReceipt::Level` 那条（同一个全局槽、同一份判据），
    // 第三跳用布局常量 `kGameSeedsObjectOffset`（`Seeds` 在引擎里是 `Game` 的**内嵌子对象**、
    // 不是指针 ⇒ 取地址相加即可；常量与证据见 `runtime_constants.hpp` 的 `kGameSeedsObjectOffset`
    // 段，此处不复制第二份）。
    //
    // 为什么要新开一档而不是复用别档：`Seeds` 的方法（`GetStageSeed` / `GetNextSeed` /
    //   `SetStartSeed`）**没有 `Entity*`/`Room*` 那种栈上句柄可读** —— 此前它们只能**手写**
    //   （`game_api.cpp` 里那三条就是这么写的，注释也写明"先要有 `FieldReceipt::Seeds` 这一档"）。
    //   有了这一档，同族的后续方法都能落成 16 字节数据行。
    Seeds = 11,
    // `PathFinder = 12`（2026-10-04 ）：`PathFinder:*` 引擎方法行的接收者。
    // **从 Lua 栈上取**（与 `EntityPlayer`/`GridEntity` 同形）：`EntityNPC.Pathfinder` 属性
    // 交回的 `PathFinderHandle` 里**真持**那个内嵌子对象的地址（`Entity_NPC + 0x408`），
    // 所以读栈上那一个就够。
    //
    // 为什么要新开一档、不复用 `Entity`：本族这一条是调用（不是读字段）。
    //   `NPCAI_Pathfinder::HasPathToPos` 一进去就顺着 `this` 读一堆成员
    //   （反汇编里 `ldr w10,[x9,#0x310]` / `gdr x8,[x8,x20]` …）⇒ 拿一个别的对象当 `this`
    //   交进去是**野读**（比"读到别人的值"危险得多）。⇒ 用 `luaL_testudata(…, kPathFinderMetatable)`
    //   严格校验句柄类型（同 `EntityFamiliar` 那一档的理由）。
    PathFinder = 12,
    // `TemporaryEffects = 13`（2026-10-07 ）：`TemporaryEffects:*` 引擎方法行的接收者。
    // **从 Lua 栈上取**（与 `PathFinder`/`EntityFamiliar` 同形）：`EntityPlayer:GetEffects()`
    // 交回的 `TemporaryEffectsHandle` 里**真持**拥有它的 `Entity_Player` 地址 —— 容器是玩家
    // 的**内嵌子对象**（`player + kEntityPlayerTemporaryEffectsOffset` = `+0x18D8`）⇒
    // 先校验玩家 vptr（`IsEntityPlayer`）再做加法，换局后旧句柄自然失效。
    //
    // 为什么要新开一档、不复用 `EntityPlayer`：本族的行是调用（不是读字段）。
    //   `TemporaryEffects::HasEffect` 一进去就读 `[x0+0x21]`（冻结标志）与 `[x0+0x08]/[x0+0x10]`
    //   （向量的 begin/end），`AddEffect`/`RemoveEffect` **会改**那个容器 ⇒ 拿一个 `Entity_Player*`
    //   当 `this` 交进去，等于把玩家对象内部那几个偏移当向量来读/写 —— **野读写**（比"读到别人的
    //   值"危险得多）。⇒ 必须显式算成 `player + 0x18D8`，并用 `luaL_testudata(…,
    //   kTemporaryEffectsMetatable)` 严格校验句柄类型（同 `PathFinder` 那一档的理由）。
    TemporaryEffects = 13,
};

// 读什么、怎么读。
enum class FieldKind : std::uint8_t {
    U32 = 0,          // 无符号 32 位整数，按整数压回
    I32 = 1,          // 有符号 32 位整数（例如 `ControllerIndex`：`-1` 表示键鼠）
    Bool = 2,         // 读一个字节，按布尔压回
    Sum2U32 = 3,      // 两个 `u32` 字段相加（例如 `GetEffectiveMaxHearts` = 红心容器 + 骨心）
    BoolEquals = 4,   // 读一个 `u32`，与 `offset2` 里的常量比较后按布尔压回
                      // （例如 `ItemConfig_Item:IsTrinket()` = `Type == ITEM_TRINKET`）
    VectorCount = 5,  // `offset`/`offset2` 是一对 `T*` 的 begin/end，按元素数压回
    BoolNonZero = 7,  // 读一个 `u32`，"非零即真"（例如 `Level:IsAltStage()` = `StageType != 0`）
    SumU32Array = 6,  // `offset`/`offset2` 是一对 `u32[]` 的 begin/end，把各格**相加**后压回
                      // （例如 `EntityPlayer:GetCollectibleCount()`：每格是"该收藏品有几件"）
    // 8：读一个 `u64` 位掩码，与调用时传进来的那个整数
    // 按位与，判"实参里点到的位全都置着"⇒ 压布尔。`Entity:HasEntityFlags(int Flags)` 就是它。
    //
    // 为什么这是本机制里第一条"带参数的字段行"：判据是 `(字段 & 实参) == 实参`，
    // 掩码来自 Lua 而不是一个编译期常量 —— 所以 `BoolEquals`（与 `offset2` 里的常量比）覆盖不了。
    // PC 契约原文（`tools/pc_contract_docs/Entity.md:425/427`）是
    // "Returns true if the entity has all named EntityFlags set." ⇒ 是"全都要"、
    // 不是"任意一位命中"（后者写成 `(字段 & 实参) != 0`）。
    // 用 `== 实参` 还有一个附带好处：`Flags == 0` 时结果为真 —— 与 PC 的位运算定义一致
    // （空集"全都有"平凡成立），不是特例。
    // 参数要求：恰好一个整数（`EngineMethodHandler` 那种"严格个数"在这里也照办）。
    U64FlagsAllSet = 8,
    // 9：`offset` / `offset2` 是同一个 `Vector2` 的两半
    // （X 在 `offset`、Y 在 `offset2`，各 4 字节 float），压成一个真正的 Lua `Vector`
    // （`PushLuaVector` ⇒ userdata：`X`/`Y` 可读写、带 `:Length()` 等方法）。
    //
    // 为什么需要它：`Room:GetTopLeftPos()` / `GetBottomRightPos()` 返回 `Vector`，
    // 而语料的用法全是取分量（`r:GetTopLeftPos().Y + 10`、`Vector(room:GetTopLeftPos().X, i)`
    // 一类，共 68 处）⇒ 既不能压 `nil`、也不能压一张只有 X/Y 的普通表（那会丢掉
    // `:Length()`/运算符，与 PC 不一致）。
    //
    // 为什么不走引擎调用：引擎里没有同名访问器（PC 侧那两个方法本体就是原样返回成员），
    // Switch 侧连符号都没有 ⇒ 直读字段是唯一与 PC 等价的做法。也因此这条没有入口指纹
    // ⇒ 宿主测试能读到真值（与的字段行同理）。
    //
    // 参数要求与其余 kind 相同：恰好一个（接收者）。`Room` 族的接收者由"当前房间"解析、
    // 不从栈上取，所以栈上那一个就是冒号调用压进来的 `self`（语料全是冒号写法）。
    // 读不到时必须压 `Vector(0,0)` —— 见 `PushMissingFieldValueForRow` 的注释。
    Vector2Pair = 9,
    // 10：读一个 `u32` 位掩码，单独测 `offset2` 指定的那一位
    // （`offset2` 在这一支里是位号 0..31，既不是第二个偏移、也不是要比较的常量），压布尔。
    //
    // 为什么需要它：`Room:IsAmbushDone()` / `Room:HasWaterPits()` 读的是同一个 32 位位掩码
    // （`RoomDescriptor.Flags`）的不同位（bit3 = `CHALLENGE_DONE`、bit5 = `HAS_WATER`）。
    // 既有种类都覆盖不了：
    // * `BoolNonZero` 是"非零即真"，而这一格里 bit0（已清）/bit1/bit2…常年置着 ⇒ 恒真；
    // * `BoolEquals` 是"整个字 == 常量"，这一格同一时刻可能有多个位 ⇒ 恒假。
    // 所以必须按位测。PC 侧的依据就是那两个绑定函数本体里的 `shr eax,N` + `and al,1`。
    //
    // 参数要求与其余 kind 相同：恰好一个（接收者）；点号显式 self 也是 1 个 ⇒ 放行。
    BoolBit = 10,
    // 11：读改写一个 `u32` 位掩码的某一位 —— 位号来自
    // `offset2`，置/清由调用时传进来的那个布尔决定，写完压零个返回值。
    //
    // 为什么需要它：`Room:SetClear(boolean Clear)` 在 PC 上就是
    // 「读描述符 `Flags` → 按实参置/清 bit0 → 写回」（`0x497800`：
    // `mov edx,[ecx+4]` → `mov ecx,[edx+0x44]` → `and eax,-2` / `or ecx,1` /
    // `cmp byte [ebp+8],0` / `cmove` → `mov [edx+0x44], ecx`），契约
    // `tools/pc_contract_docs/Room.md:772` 的散文正好说明为什么要能清
    // （"Needed for Angel rooms so that the clear flag can be set to false when an Angel
    // spawns."）。它不是改走引擎自己的 `Room::TriggerClear(bool)` —— 那个函数
    // 除了置 bit0 还会自增描述符 `+0x56` 的计数、调 `ScoreSheet::AddClearedRoom`
    // 并触发一串结算，副作用远多于 PC 的 `SetClear`（照它实现会"静默多做一堆事"）。
    //
    // 参数要求：恰好两个（接收者 + 一个布尔）。返回值：0 个
    // （PC 返回 void）—— 这是本机制里第一条"不返回值"的 kind，所以共享处理器里
    // 有一处 `return 0` 的分支。
    BoolBitWrite = 11,
    // 12：按调用时传进来的那个整数去位数组里取一位，压布尔。
    //
    // `offset` = 位数组基址（相对接收者），`offset2` = 元素宽度（字节：1 / 4 / 8），
    // 实参 = 标志号 `n`。读法 = 第 `n / (8*宽度)` 个元素、第 `n % (8*宽度)` 位：
    // * 宽度 1 ⇒ `n>>3` 字节、`n&7` 位（`GameStateFlag`：`Game + 0x26FA50`）；
    // * 宽度 8 ⇒ `n>>6` 字、`n&63` 位（`LevelStateFlag`：`Level + 0x215F0` 的 `u64`）。
    //
    // 为什么需要它：`Game:GetStateFlag(int Flag)` / `Level:GetStateFlag(int Flag)` 的位号来自
    // Lua 实参，不是行里的常量 —— `BoolBit`（`offset2` 是常量位号）与 `BoolNonZero`
    // （整字非零）都覆盖不了；`U64FlagsAllSet` 虽然也吃实参，但它的判据是
    // "实参点到的位全都置着"（`(字段 & 实参) == 实参`），而这里是"第 n 位置没置"
    // （`(字段 >> n) & 1`）—— 两者在 n 只有一位时结果相同，但语义与用处不同
    // （`HasEntityFlags` 要的是"全都"，`GetStateFlag` 要的是"某一位"）。
    //
    // 两个偏移常量与"基址 + 标志号"的取证（四条具名函数里的位点位）见
    // `runtime_constants.hpp` 的段；PC 侧那两条绑定也是"字宽不同的位数组"
    // （Game 32 位字、Level 64 位字）⇒ 把宽度做成行参数正好对上。
    //
    // 参数要求：恰好两个（接收者 + 一个整数标志号）；越界（`n < 0` 或
    // `n >= 8*宽度*64`）按"读不到"降级 —— PC 没有任何边界检查（会读飞），
    // 我们不去读一个可能落在别的字段上的地址。
    BoolBitArrayOfArg = 12,
    // 13：`BoolBitArrayOfArg` 的写侧 —— 按调用时传进来的
    // 标志号去位数组里读改写那一位，位值来自第二个实参，返回值 0 个。
    //
    // `offset` = 位数组基址，`offset2` = 元素宽度（字节 1 / 4 / 8），
    // 两个实参 = `(标志号 n, 布尔值)`。与 `BoolBitWrite` 的关系正如 `BoolBitArrayOfArg`
    // 与 `BoolBit` 的关系：位号是实参而不是行里的常量。
    //
    // 两个使用者 = `Game:SetStateFlag(int Flag, boolean Value)`（`Game + 0x26FA50`，
    // 宽度 1）与 `Level:SetStateFlag(int Flag, boolean Value)`（`Level + 0x215F0` 的 `u64`，
    // 宽度 8）—— 与 297 那两个读侧 API 是同一对数组（PC 侧四条绑定也都落在同一对数组上：
    // `Game` 的 `0x1822C`（32 位字）与 `Level` 的 `0x1C3168`（64 位字））。
    //
    // 写侧必须走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`）：
    // 写错地址是"静默破坏别人的内存"，比读错严重得多（与 `BoolBitWrite` 同一形态）。
    // 越界（`n < 0` 或超过"64 个元素"的护栏）⇒ 什么都不写、也不抛错、返回 0 个值
    // （PC 那两条绑定也没有边界检查；"这次没生效"远好过"写飞"）。
    BoolBitArrayOfWriteArg = 13,
    // 14：读改写一个 `u32` 字段 —— 把它与调用时传进来的那个整数
    // 按位或（`字段 |= 实参`），写完压零个返回值。
    //
    // 为什么需要它：`EntityPlayer:AddCacheFlags(CacheFlag)` 在 PC 上就是
    // `or dword ptr [ecx+0x14b8], eax`（绑定本体 `0x427800`，语义毫无歧义：
    // 契约 `tools/pc_contract_docs/EntityPlayer.md:108/109` —— "Will reevaluate the cache
    // flags provided in the next cache reevaluation."）。既有种类都覆盖不了：
    // * `BoolBitWrite` 只会动一位（位号是行里的常量 `offset2`），而这里是"整段掩码 OR 进来"；
    // * `BoolBitArrayOfWriteArg` 的实参是标志号（去位数组里定位第 n 位），
    // 而这里的实参就是掩码本身（掩码可能有多位、且不做数组定位）。
    // ⇒ 语义上它与 `U64FlagsAllSet` 是"同一格的两个方向"：那条问"这些位都在吗"（`&` 后比），
    // 这条"把这些位置上"（`|` 后写回）。
    //
    // `offset` = 那个 `u32`（本批 `Entity_Player + 0x1958` = `_cacheFlags`，
    // 取证见 `runtime_constants.hpp` 段与布局表 `entity_player.json` 的 `CacheFlags` 行）。
    // `offset2` 在本 kind 里不用（写 0）。
    //
    // 写侧必须走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`）：写错地址是
    // "静默破坏别人的内存"（随机崩溃 / 存档损坏且事后无从归因），比读错严重得多
    // （与 `BoolBitWrite` / `BoolBitArrayOfWriteArg` 同一形态，批 250/292/300 定案）。
    // 参数要求：恰好两个（接收者 + 一个整数掩码）。掩码必须是整数
    // （`nil` / 字符串 / 非整值浮点都被拒 —— PC 的绑定也要求整数）。
    // 读不到 / 接收者解析不到 ⇒ 什么都不写、也不抛错、返回 0 个值
    // （PC 上不存在"写失败"这回事；"这次没生效"远好过"报错摘掉整条模组回调"，批 250 定案）。
    U32OrWithArg = 14,
    // 15：把第一个实参（Lua `Color` 句柄）转成 44 字节的 `ColorMod`，
    // 整块写进 `字段`（`offset` 处），写完压零个返回值。
    //
    // 为什么需要它：`Room:SetFloorColor(Color)` / `Room:SetWallColor(Color)` 在 PC 上就是
    // 「把 44 字节的实参整块拷到成员上」（绑定本体 `0x7A7ED0` / `0x7A7F10`：`add ecx,0x7188` /
    // `add ecx,0x71b4` 之后一串 `movups`/`movq`/`mov`，`ret 0x2c`），没有任何别的副作用。
    // 既有种类都覆盖不了：它们要么写整数（`U32OrWithArg`）、要么只动一位（`BoolBit*`），
    // 而这里要写一个44 字节的结构体、且实参是 userdata 而不是数字。
    //
    // 这里是第一条"实参是 `Color` 句柄"的字段行 ⇒ 共享处理器的参数闸要为它单开一支
    // （整数闸不能套用：`IsIntegerArgument` 会把 `Color` 判成不合法）。判据 = 那一格
    // `luaL_testudata(…, kColorMetatable)` 能取到句柄；取不到就报错（PC 的胶水层同样会拒）。
    //
    // 「`Color` → `ColorMod`」的映射只有一份（`engine_color_mod.hpp` 的
    // `FillEngineColorMod`，抽出来的）—— 本 kind 复用它，不许再抄一份。
    //
    // 写侧一律走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`，44 字节整段判定）：
    // 写错地址是"静默破坏别人的内存"。读不到 / 判不出可写 / 实参不是 `Color`
    // ⇒ 什么都不写、也不抛错（返回 0 个值；"这次没生效"远好过"报错摘掉整条模组回调"）。
    //
    // 参数要求：恰好两个（接收者 + 一个 `Color`）。`offset2` 在本 kind 里不用（写 0）。
    ColorModWrite = 15,
    // 16：往 `字段`（1 字节）写一个常量布尔 —— 常量住在
    // `offset2`（写 0 或 1），不收任何实参（只有接收者），写完压零个返回值。
    //
    // 为什么需要它：`MusicManager:Disable()` / `Enable()` 在 PC 上就是
    // `mov byte ptr [ecx+0x328], 0` / `…, 1`（绑定本体各一条指令，不收参数）。
    // 既有种类都覆盖不了：
    // * `Bool` 是读；
    // * `BoolBitWrite` / `BoolBitArrayOfWriteArg` 的位值来自实参（而这两条 API 没有实参）；
    // * `BoolEquals` 是拿 `offset2` 当比较常量（读侧）。
    // ⇒ 语义上它与 `BoolEquals` 正好成对：那条"与常量比后压布尔"，这条"把常量写进去"。
    //
    // `offset2` 只认 0 / 1（别的值按"表写错"处理 —— 见实现处：非 0 一律当 1，不静默写别的字节值）。
    // 写侧一律走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`）：写错地址是
    // "静默破坏别人的内存"（与同族写侧 kind 同一形态，批 250/292/300/301/302 定案）。
    BoolWriteConst = 16,
    // 17：往 `字段`（4 字节 u32）写实参给的整数（只取低 32 位），
    // 返回零个返回值。
    //
    // 为什么需要它：`GridEntity:SetType(eGridEntityType)` 在 PC 上就是
    // `mov eax,[ebp+8]` + `mov [ecx+0x4],eax`（绑定本体两条指令、不调引擎函数）
    // ⇒ 与 `BoolWriteConst`（写常量）正好是"写什么"的两个方向：
    // 那条的常量住在行里（`offset2`）、这条的值由调用方给。
    // 既有种类都覆盖不了：`U32OrWithArg` 是 `|=`（掩码语义，抹不掉旧位）、
    // `BoolWriteConst` 只写 0/1 的一个字节、其余写侧 kind 都是布尔语义。
    //
    // 参数要求：恰好两个（接收者 + 一个整数）；走 `IsIntegerArgument` 那一道闸
    // （与 `U64FlagsAllSet` / `U32OrWithArg` 同一个判据）。
    // 写侧一律走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`）：写错地址是
    // "静默破坏别人的内存"（与同族写侧 kind 同一形态，批 250/292/300/301/302/305 定案）。
    U32FromArg = 17,
    // 18：把 `offset` 处的 16 字节 `RNG` 对象读成一份快照，
    // 压回一个 Lua `RNG` 句柄（`kRngMetatable`）。参数只有接收者，返回 1 个值。
    //
    // 为什么需要它：`Entity:GetDropRNG()`（契约 `tools/pc_contract_docs/Entity.md:377`）在 PC 上
    // 就是 `lea eax,[ecx+0x334]; ret` —— 返回实体内嵌那个 `RNG` 的地址，既不查表也不调用引擎；
    // Switch 侧同一个 RNG 就在 `Entity + 0x3D8`（构造 `Entity::Entity @ 0x58978` 的
    // `add x0,x19,#0x3d8; bl RNG::RNG()`、出生 `Entity::Init @ 0x597E8` 的
    // `add x21,x0,#0x3d8; bl RNG::SetSeed(seed, 30)`）⇒ 直读这一格就是与 PC 逐字等价的做法。
    // 既有种类都覆盖不了：`Vector2Pair` 压的是 `Vector`（另一张元表），
    // 其余读侧 kind 压的是数字/布尔/表，没有一种能压出 `RNG` 句柄。
    //
    // 交回 Lua 的是调用瞬间那 16 字节的快照，不是引擎里那个 RNG 的活引用（PC 返回引用）——
    // 与 `GridEntity:GetRNG`（`0x0E010054`）及四条 `EntityPlayer:Get*RNG` 同一口径，
    // 已按项目规矩登记为偏离（`api_deviation.cpp`，性质 `design`）：
    // 读语义逐值相同（`GetSeed`/`Next`/`RandomInt` 在取到那一刻一致），
    // 差别只在"从返回对象上改状态会不会影响引擎"。
    //
    // `offset` 是那个 `RNG` 的起始地址（本批 = `Entity` 的 `+0x3D8`，
    // 也正是 `Entity.DropSeed` 那一格 —— RNG 的种子就是对象头 4 字节 ⇒ 两个名字同址）。
    // 读不到 / 接收者解析不到 ⇒ 按 `missing` 降级（本批 `Nil`：句柄类字段读不出来时
    // PC 上也没有对象可给，压 nil 与 `x == nil` 的判断一致）。
    // 写侧安全口径不适用（本 kind 只读，不写任何引擎内存）。
    // 2026-10-09更正：编号与旧名字保留兼容，现为经owner核验的原生活引用，旧快照说明是历史。
    RngSnapshot = 18,
    // 19：读改写一个 `float` 字段 —— 把它与调用时传进来的那个数值
    // 相乘（`字段 *= 实参`），写完压零个返回值。
    //
    // 为什么需要它：`Entity:MultiplyFriction(float Value)` 在 PC 上就是
    // `movss xmm0,[ebp+0x8]` → `mulss xmm0,[ecx+0x2c4]` → `movss [ecx+0x2c4],xmm0; ret 4`
    // （绑定本体 `0x5951D0`，语义毫无歧义：`Entity.md:510` 的 `void MultiplyFriction ( float Value )`，
    // 正文只有签名没有散文 ⇒ 语义由绑定本体定）。既有种类都覆盖不了：
    // * `U32OrWithArg` 是按位或（整数运算，不是浮点乘）；
    // * `ColorModWrite` 整块写 44 字节、`U32FromArg` 整格写；
    // * 所有 `Bool*` 都是位/字节级。
    // ⇒ 它是本项目第一条"浮点读改写"的字段行。
    //
    // `offset` = 那个 `float`（本批是 `Entity + 0x340` = 本帧的工作摩擦，
    // 取证见 `runtime_constants.hpp` 段与布局表 `entity.json` 的 `Friction` 行）。
    // `offset2` 在本 kind 里不用（写 0）。
    //
    // 写侧必须走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`）：
    // 写错地址是"静默破坏别人的内存"（随机崩溃 / 存档损坏且事后无从归因），比读错严重得多
    // （与 `BoolBitWrite` / `U32OrWithArg` 同一形态，批 250/292/301 定案）。
    // 参数要求：恰好两个（接收者 + 一个数值）。这一条不套整数闸 ——
    // `1.2` 这种非整值浮点必须放行（`IsIntegerArgument` 会拒掉，而 PC 的绑定直接当浮点用）。
    // 越界/读不到 / 接收者解析不到 ⇒ 什么都不写、也不抛错、返回 0 个值
    // （PC 上不存在"写失败"这回事；"这次没生效"远好过"报错摘掉整条模组回调"，批 250 定案）。
    // 别忘了把它列进 `isaac_api.cpp` 的 `RowReturnsNoValues`（写侧 kind 的集体口径）。
    FloatMultiplyArg = 19,
    // 20：把调用时传进来的那个数值直接写进一个 `float` 字段
    // （`字段 = 实参`，不是乘），写完压零个返回值。
    //
    // 为什么需要它：`EntityLaser:SetMaxDistance(float Distance)` 在 PC 上就是
    // `movss xmm0,[ebp+8]` → `movss [ecx+0x420],xmm0` → `ret 4`
    // （绑定本体 `0x4275B0`；契约 `tools/pc_contract_docs/EntityLaser.md:126` 的散文
    // "Used to trim brimstone for Azazel (0 - off)"）⇒ 赋值，不是读改写。
    // 既有种类都覆盖不了：
    // * `FloatMultiplyArg` 是 `*=`（读改写），赋值语义不同（同值重复调用会指数级累积）；
    // * `U32FromArg` 写的是整数的 32 位——把 Lua 的 `40` 写成 `0x28`，
    // 而本格要的是 `40.0f` 的位型 `0x42200000` ⇒ 位型完全不同，不能替代。
    // ⇒ 它与 `FloatMultiplyArg` 正好是"同一个 `float` 字段的两种写侧"。
    //
    // `offset` = 那个 `float`（本批是 `Entity_Laser + 0x4F8`，取证见 `runtime_constants.hpp`
    // 的段与布局表 `tools/layout_tables/entity_laser.json` 的 `MaxDistance` 行）。
    // `offset2` 在本 kind 里不用（写 0）。
    //
    // 写侧必须走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`）：
    // 写错地址是"静默破坏别人的内存"（随机崩溃 / 存档损坏且事后无从归因），比读错严重得多
    // （与 `BoolBitWrite` / `U32OrWithArg` / `FloatMultiplyArg` 同一形态，批 250/292/301/333 定案）。
    // 参数要求：恰好两个（接收者 + 一个数值）。与 `FloatMultiplyArg` 同一条口径 ——
    // 不套整数闸（`1.5` 这类非整值浮点必须放行）。
    // 读不到 / 判不出可写 / 接收者解析不到 ⇒ 什么都不写、也不抛错、返回 0 个值。
    // 别忘了把它列进 `isaac_api.cpp` 的 `RowReturnsNoValues`（写侧 kind 的集体口径）。
    FloatFromArg = 20,
    // 21：把两个实参分别写进两个字段 ——
    // 第 1 个实参（Lua 数值）→ `offset` 处的 `float`；第 2 个实参（Lua 整数）→ `offset2` 处的
    // `i32`。写完压零个返回值。
    //
    // 为什么需要它（本机制的表达力缺口）：`Game:Darken(float Darkness, int Timeout)` 在 PC 上
    // 就是「把两个形参各存进一个成员」（绑定本体 `0x432F60`，`__thiscall`，两个标量形参）。
    // 既有种类每一种都只能动一格：
    // * `FloatFromArg` / `FloatMultiplyArg` 只服务一个 float 字段；
    // * `U32FromArg` / `U32OrWithArg` 只服务一个 4 字节整数格；
    // * `BoolWriteConst` / `BoolBitWrite` 等是布尔/位语义、且只写一格。
    // ⇒ 「两实参写两格、且类型不同」只能新开一种。
    //
    // `offset` = 那个 `float`；`offset2` = 那个 `i32`。两格不必相邻（本批的两格中间就夹着
    // 第三个字段）—— 这正是把它做成"两个独立偏移"而不是"一条 u64"的理由。
    //
    // 写侧必须走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`）：写错地址是
    // "静默破坏别人的内存"（与同族写侧 kind 同一形态，批 250/292/301/333/341 定案）。
    // 参数要求：恰好三个（接收者 + 一个数值 + 一个整数）。
    // 第 1 格不套整数闸（`0.5` 这类非整值浮点必须放行）；第 2 格走 `IsIntegerArgument`。
    // 读不到 / 判不出可写 / 接收者解析不到 ⇒ 什么都不写、也不抛错、返回 0 个值。
    // 别忘了把它列进 `isaac_api.cpp` 的 `RowReturnsNoValues`。
    FloatThenIntFromArgs = 21,
    // 22：把 `offset` 与 `offset2` 两格各写 1 字节常量 `0`，
    // 不收任何实参（只有接收者），写完压零个返回值。
    //
    // 为什么需要它：`EntityPlayer:StopExtraAnimation()` 在 PC 上就是「把两个相邻间隔 2 的字节都清 0」
    // （绑定本体 `0x57B1D0`；PC 的两格是 `Entity_Player + 0x12E8` / `+0x12EA`，
    // 中间的 `0x12E9` PC 明确跳过）。而本机制里没有一种 kind 能写两格：
    // * `BoolWriteConst` 的 `offset2` 已被"要写的常量"占掉 ⇒ 没有位置再放第二格的偏移；
    // * 一条 `FieldApiRow` = 一个 API（`AttachOwnerMethods` 按 id 匹配）⇒ 不能让一个 API 挂两行。
    // ⇒ 新开这一种。常量恒为 0（本 API 两格都写 0）；将来真出现"两格写非 0 常量"再推广，
    // 现在不过度设计（那需要第三、第四个 32 位槽，会顶破 `FieldApiRow` 的 16 字节不变式）。
    //
    // 绝不允许用"往 `offset` 写一个 `u16 = 0`"来偷懒：那会连带清掉中间那一字节，
    // 而 PC 明确跳过它 ⇒ 与 PC 不一致（且那一格的用途未取证，风险更大）。必须逐字节写两格。
    // 写侧一律走 `engine_memory::WriteField`（先过 `IsEngineMemoryWritable`）。
    // 参数要求：恰好一个（接收者）；写不进去 ⇒ 什么都不写、也不抛错、返回 0 个值。
    // 别忘了把它列进 `isaac_api.cpp` 的 `RowReturnsNoValues`。
    TwoByteConstZero = 22,
    // 23：读一段 44 字节的引擎 `ColorMod`，压回一个 Lua `Color` 句柄
    // （`kColorMetatable`）。返回 1 个值（读侧，不进 `RowReturnsNoValues`）。
    //
    // 为什么需要它：`Entity:GetColor()` 在 PC 上按值返回一个 `Color`
    // （绑定本体 `0x4F3DE0` = `lea eax,[ecx+0xE4]; ret`），Switch 侧那一格是
    // `Entity + kEntityGetColorOffset`（`0x138`）的 44 字节 `ColorMod`。
    // 既有读侧 kind 没有一种能压出 `KColor`：
    // * `Vector2Pair` 压的是 `Vector`（另一张元表）、且只有 2 个 float；
    // * `RngSnapshot` 压的是 `kRngMetatable`、读 16 字节、且带"快照 vs 活引用"的登记偏离；
    // * 其余读侧 kind 压的都是数字/布尔/普通表。
    // ⇒ 新开这一种。它与 `ColorModWrite`（= 15，写侧）正好成对。
    //
    // 映射只复用 `engine_color_mod.hpp` 的 `PushLuaColorFromEngineColorMod`
    // （与 `FillEngineColorMod` 同住一份，"颜色映射只有一份"，的纪律）——
    // 不许在这里再抄一遍 `tint/shift` 的对应关系。
    // 不是偏离：压进去的是调用瞬间那 7 个 float 的值拷贝，与 PC 的"按值返回"逐值一致
    // （对照 `RngSnapshot` 那条登记过的"快照 vs 活引用"偏离 —— 本条没有）。
    // 读不到 / 接收者解析不到 ⇒ 走 `PushMissingFieldValueForRow` 的默认白那一支
    // （`tint=(1,1,1,1)`、偏移全 0）—— 不报错、也不压 `nil`：语料 4 处拿到返回值
    // 第一件事就是取分量或直接喂回 `SetColor`，压 `nil` 会把整条模组回调摘掉
    // （与 `Vector2Pair` 压 `Vector(0,0)` 同一族理由）。
    // `offset2` 在本 kind 里不用（写 0）。
    ColorModRead = 23,
};

// 读不到（或接收者无效）时返回什么。按各族 PC 语义与既有实现选定，不许随手挑：
// 读不出来却编一个假值，会让 Mod 走进错误的判断分支。
enum class FieldMissing : std::uint8_t {
    Zero = 0,      // 压 0（计数器类：PC 上"没有"就是 0）
    Nil = 1,       // 压 nil（枚举/句柄类：`x == SomeEnum` 在 nil 上自然为假）
    False = 2,     // 压 false（布尔类）
    MinusOne = 3,  // 压 -1（"没有"在 PC 上就是 -1 的字段，例如 `GetBabySkin()` 非婴儿 = -1）
    // 4：压 1。给"读不到时 PC 自己会退化成 1"的字段用。
    //
    // 目前唯一的使用者 `Room:GetRoomShape()` 就是这么来的：PC 的绑定函数（`0x444C30`）在
    // 两跳指针链上有任何一环为 NULL 时跳到 `0x444C42 mov eax,0x1` —— 而 `RoomShape` 的
    // 1 就是 `ROOMSHAPE_1x1`（本项目自己的枚举表 `doc_lua_enum_data.cpp` 逐值如此）。
    // 换成 `Zero` 会答出"没有形状"（0 不在 `RoomShape` 表里），与 PC 不一致。
    One = 4,
};

// 一行 = 一个 API。字段顺序按"对齐后最小"排：4+4+4+1+1+1+1 = 16 字节。
struct FieldApiRow {
    std::uint32_t id;        // catalog id（必须与 `api_catalog.cpp` 里那条对得上）
    std::uint32_t offset;    // 相对接收者对象的偏移（`Sum2U32` 时是第一个）
    std::uint32_t offset2;   // `Sum2U32` 的第二个偏移，其余 kind 忽略
    FieldKind kind;
    FieldMissing missing;
    FieldReceipt receipt;
    std::uint8_t probeBit;   // `api_sequence_probe.hpp` 的位号；`0xFF` = 不记
};

// 一行必须正好 16 字节（4+4+4+1+1+1+1，按对齐排好）。这是这套机制的成本前提：
// 行变大就会削弱"每个 API 只花一行数据"的结论。改结构体先看这条断言。
static_assert(sizeof(FieldApiRow) == 16, "FieldApiRow 必须保持 16 字节（见成本说明）");

// 取字段读取型 API 的总表（表本身定义在 `isaac_api.cpp` 的匿名命名空间里，所以用访问器
// 而不是 `extern` 数组 —— 两处同名会让编译器说"引用有歧义"）。
// 各族在各自的注册点把它传给 `AttachOwnerMethods`：绑定循环按 id 匹配，
// 所以一张表可以服务多个 owner（行里的 `receipt` 决定用哪套接收者校验）。
[[nodiscard]] const FieldApiRow* FieldApiRows(std::size_t* count) noexcept;

// 字段读取型 API 的共享处理器。行通过闭包上值传入（见 `AttachOwnerMethods`）。
//
// 错误消息按 catalog 里的 `owner`/`name` 现拼（例如 `"EntityPlayer:GetSoulHearts accepts
// no arguments"`），与手写处理器逐字一致；拼消息只在出错路径上做，稳态零成本。
[[nodiscard]] int FieldApiHandler(lua_State* state);

} // namespace isaac::runtime
