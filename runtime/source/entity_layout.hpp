#pragma once

// **本文件由 `tools/build_layout_table.py` 从 `tools/layout_tables/entity.json` 生成，请勿手改。**
//
// 每个常量都对应表里的一行，那一行带可复现证据（函数符号 + 指令地址）。
// 复核命令：`python3 tools/build_layout_table.py --table tools/layout_tables/entity.json --verify`
//
// 口径（与表的 `confidence` 一致）：
//   confirmed  —— 语义有独立锚点 ⇒ **可以**用于对外 API；
//   candidate  —— 偏移确定、名字只有间接依据 ⇒ 只作登记，不进 API；
//   structural —— 只说明结构，不声称字段名。

#include <cstdint>

namespace isaac::runtime::layout {

inline constexpr std::uint8_t kEntityBuildId[20] = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31, 0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7, 0x23, 0x88, 0xB2, 0xAB
};

// **这个实体当前「可见吗」**（PC 侧 `Entity:IsVisible()` 读的就是这一格，PC 在 `Entity+0x169`）。引擎自己按它决定**要不要画**：`Entity::Render` 与 `EntityList::RenderShadows` 读到 0 就直接跳过，`Camera::get_enemy_target` 也不会把看不见的实体当目标。（confirmed）
//   证据：0x00062514 —— **具名读者一**：`Entity::Render` 里 `ldrb w8,[x0,#0x1c1]` + 紧邻的 0x6251C `cbz w8, →函数尾` ⇒ **这一位为 0 时整个实体不画**（函数名即语义）
//   证据：0x00078210 —— **具名读者二**：`EntityList::RenderShadows` 逐个实体 `ldrb w8,[x0,#0x1c1]` + 0x78214 `cbz w8, →取下一个` ⇒ 不可见的实体连影子都不画
//   证据：0x00032bbc —— **具名读者三**：`Camera::get_enemy_target` 读它 ⇒ 摄像机不锁定看不见的敌人（这一格因此不只是「画不画」，而是引擎自己的可见性判据）
//   证据：0x000800a4 —— **具名写入方**：`Entity_Effect::Init` 把它**清零**（`strb wzr,[x19,#0x1c1]`）⇒ 新建的 Effect 初始不可见（之后由 `Entity_Effect::SetVisible` 一类打开）
//   证据：0x0007d8f4 —— 取值锚点：`Entity_Bomb::Update` 在 `ldrb w8,[x19,#0x1c1]` + `cbnz`（可见就跳过）之后走到 `mov w8,#4` 并把 4 写进 `[x19,#0x420]`（引信状态）⇒ 这一位为 0 时炸弹走的是「不可见」那条分支，4 是那条分支里的常量
inline constexpr std::uintptr_t kEntityVisibleOffset = 0x1C1;
inline constexpr std::uintptr_t kEntityVisibleWidth = 1;

// 这个实体还在不在当前房间的实体表里（PC 侧 `Entity:Exists()` 读的就是这一格，PC 在 `Entity+0x16A`）。契约散文（`Entity.md:322`）逐字写着：`Checks whether the entity is still spawned in the current room.` 引擎自己就这么用：`EntityList::Update` 读到 0 就跳过这个实体；`Entity::Remove()` 与析构函数把它清零；构造函数把它初始化成 0（还没进表）。（confirmed）
//   证据：0x00076848 —— **具名读者（最直接）**：`EntityList::Update` 对表里每个实体 `ldrb w8,[x22,#0x1c2]` + `cbnz w8, →继续处理`（为 0 就跳到 0x76898 跳过）⇒ 这一位就是「这个实体还算表里的一员吗」
//   证据：0x0005d3e4 —— **具名写入方**：`Entity::Remove()` 把它**清零**（`strb wzr,[x0,#0x1c2]`）—— 函数名就是「把实体从房间里摘掉」
//   证据：0x000588e8 —— **构造时初始化**：`Entity::Entity()` 把它清零（`strb wzr,[x19,#0x1c2]`）⇒ 新实体还没被放进实体表
//   证据：0x000589dc —— **析构时也读它**（`ldrb w8,[x0,#0x1c2]`，0x589EC 再清零）⇒ 与 `Remove` 同一段语义
//   证据：0x000589f4 —— 取值锚点（与 `IsDead` 那一对）：这一格为 0 的分支里紧接着 `mov w8,#1` 再写 `Entity+0x1C3` ⇒「实体离开实体表时，如果它还没死就把它标记成死了」（同一段代码在 `Entity::Remove` 的 0x5D3F0 逐字重复）—— 两位的耦合关系本身就是「Exists / IsDead」这一对的语义证据
inline constexpr std::uintptr_t kEntityExistsOffset = 0x1C2;
inline constexpr std::uintptr_t kEntityExistsWidth = 1;

// 这个实体死了吗（PC 侧 `Entity:IsDead()` 读的就是这一格，PC 在 `Entity+0x16B`）。决定性锚点：`Entity::Kill()` 把它置 1（幂等守卫：已经置着就直接返回），而契约散文（`Entity.md:502`）写着 `Kills the entity and makes a blood splat or gibs.` —— Switch 侧 `Entity::Kill` 的函数体最后正是尾调用 `Entity::BloodExplode()`（血花/肉块）⇒ 这一格就是「已死」本身。（confirmed）
//   证据：0x0005c8f4 —— 具名写入方 + 取值锚点：`Entity::Kill()` 里 `ldrb w8,[x0,#0x1c3]` + `cbnz`（已置就返回）之后 `mov w8,#1` + `strb w8,[x0,#0x1c3]`（0x5C8F8）⇒ 置 1 = 标记已死；紧接着取虚表槽 `[x8,#0x98]` 调用、再按类型决定是否尾调 `Entity::BloodExplode`（与契约那句 blood splat/gibs 对上）
//   证据：0x0005c8ec —— **同一函数的读侧**（`ldrb w8,[x0,#0x1c3]`）—— `Kill` 是幂等的：已经死过的实体直接返回，不会重复放血花
//   证据：0x0005d380 —— **死亡路径的读者**：`Entity::BloodExplode()`（血花/肉块）读它 ⇒ 与 `Kill` 同一件事的另一半
//   证据：0x0005c650 —— 第二处独立读者：`Entity::IsVulnerableEnemy`（我们自己落地的那条引擎方法）读它 ⇒ 死掉的实体不再是「可伤害的敌人」（否则模组会对尸体继续算伤害）
//   证据：0x0005d3e0 —— **`Entity::Remove` 读它并（若还没死）置 1**（0x5D3E0 读 + 0x5D3F4 写）⇒「摘掉一个还活着的实体 = 杀掉它」，与 `Exists` 那一格构成一对
inline constexpr std::uintptr_t kEntityIsDeadOffset = 0x1C3;
inline constexpr std::uintptr_t kEntityIsDeadWidth = 1;

// 决定能否飞过沟/石的运动层（派生量，不是 PC 的 Lua 字段）：`Entity::IsFlying()` 的判据字面就是『本字段 < 4』（confirmed）
//   证据：0x0005c744 —— 该函数唯一一条字段访问：`ldr w8, [x0, #0x1e0]`
//   证据：0x0005c748 —— `cmp w8, #0x4` + `cset w0, lo` ⇒ 『层号 < 4 就是能飞』，这个 4 是引擎自己的阈值 ⇒ 本字段是飞行层（`Entity_Player.CanFly` 只是它的来源，见 entity_player.json）
inline constexpr std::uintptr_t kEntityFlyingLayerOffset = 0x1E0;
inline constexpr std::uintptr_t kEntityFlyingLayerWidth = 4;

// 本帧这个实体有没有撞到网格（墙/石头/坑）（u8，取值 0/1）。PC 侧 `Entity:CollidesWithGrid()` 读的就是这一格（PC 在 `Entity+0x188`；数值不许平移，两边 `Entity` 布局不同）。为什么能定案：镜像里 `Entity::CollideWithGrid` / `Entity::PlayerCollideWithGrid` 在整趟碰撞开始前先把它清 0，随后在各个『确实碰上了』的分支里各写一次 1；`Entity::Init` 里也清零 ⇒ 『本帧是否碰撞』这个语义由函数名 + 清/置两处同时钉住。读者是 `Entity::Update` 与一批 `Entity_*::Update` / `Entity_Familiar::ai_*`（撞墙后各自动作）。（confirmed）
//   证据：0x000598ec —— **初始化清零**：`strb wzr, [x19, #0x1ec]` —— 实体出生时这一格是 0
//   证据：0x0005a2b4 —— **语义锚点（函数名即语义）**：`Entity::CollideWithGrid` 开头 `tbnz w1,#0x0` 跳过、否则 `strb wzr, [x22, #0x1ec]`（**整趟碰撞开始前先清 0**）；随后在 7 个『确实碰上了』的分支里各写一次 1（`0x5a398` / `0x5a3f8` / `0x5a474` / `0x5a488` / `0x5a6f8` / `0x5ab9c`）
//   证据：0x0005b8d8 —— **同形的第二套**（玩家专用那条路）：`Entity::PlayerCollideWithGrid` 同样是『开头 `0x5b7f0` 清零 + 若干分支置 1』（`0x5b938` / `0x5b94c` / `0x5bdbc`）
//   证据：0x000600d8 —— **具名读者**：`ldrb w8, [x19, #0x1ec]` —— 实体的每帧更新里读它决定后续动作（同函数另一处 `0x60174`；另有 `Entity_Bomb::Update` / `Entity_Effect::Update` / `Entity_Familiar::ai_*` 等一批读者）
//   证据：0x0005a470 —— 命名 + 取值锚点：`mov w8, #0x1` 紧跟 `strb w8, [x22, #0x1ec]`（`0x5A474`）⇒ 『撞上了』就写常量 1（另有 `cset w8, ne` 形态的同款置位，见 access 条目）；而它所在的函数名字面就是 `CollideWithGrid` ⇒ 本格 = 『本帧这个实体有没有撞到网格』。开头还有一条反向锚点：`tbnz w1,#0x0` 跳过、否则 `strb wzr, [x22, #0x1ec]`（`0x5A2B4`）—— 整趟碰撞开始前先清 0。
inline constexpr std::uintptr_t kEntityCollidesWithGridOffset = 0x1EC;
inline constexpr std::uintptr_t kEntityCollidesWithGridWidth = 1;

// 这一帧的工作摩擦（`Entity + 0x340`，float）。引擎每帧把它乘进速度：`Entity::Update` 读它喂给 `TimeScaledFriction(friction, dt)`，再把结果乘进速度向量（`Entity + 0x334`）。与相邻的 `+0x33C`（原值）构成一对：`Entity::Init` 与 `Entity::Update` 都会把 `+0x33C` 拷进 `+0x340`，并按分支做一次 `× 0.95f` 的衰减。`Entity:MultiplyFriction(float)` 乘的就是这一格（PC 侧是 `Entity + 0x2c4`，不许平移）（confirmed）
//   证据：0x00060148 —— 取值锚点（摩擦衰减）：0x60144 `mov w8,#0x3333` 与本条 `movk w8,#0x3f73,lsl#16` 合成 0x3F733333 = 0.95f → 0x60150 `fmov s1,w8` → 0x60154 `fmul s0,s0,s1`（s0 来自 0x6014C `ldr s0,[x19,#0x33c]`）→ 0x6015C `str s0,[x19,#0x340]` ⇒ 这一格是「被衰减的摩擦」，不是普通标量
//   证据：0x0006026c —— 头号消费者：`ldr s0, [x19, #0x340]` → 0x60278 `bl TimeScaledFriction(friction, dt)`（dt 取自 0x60274 `ldr s1,[x19,#0x370]`）→ 0x6028C `Vector2::operator*=`（速度，x21 = `this+0x334`）⇒ 函数名即语义：这一格参与的是摩擦
//   证据：0x00059860 —— 建实体时 `ldr w8,[x19,#0x33c]` → 本条 `str w8,[x19,#0x340]`（0x59898 再写一次）⇒ `+0x33C` 是**原值**、本格是**本帧值**（一对）
//   证据：0x000602b8 —— 同一函数里的**复位**：`ldr w8,[x19,#0x33c]` → 本条 `str w8,[x19,#0x340]` ⇒ 每帧先复位成原值、再按分支衰减（`Entity_Bomb::Update` 等子类也各自读写本格）
inline constexpr std::uintptr_t kEntityFrictionOffset = 0x340;
inline constexpr std::uintptr_t kEntityFrictionWidth = 4;

// 当前血量（float，PC 的 `Entity.HitPoints`）。它不是挨打就立刻减 —— 契约 `tools/pc_contract_docs/Entity.md:754` 明写『要到下一帧才更新』，所以减血不在 `TakeDamage` 里（在 `TakeDamage` 里翻偏移翻不到，这是本项此前卡住的原因）。（confirmed）
//   证据：0x0005a24c —— `AddHealth(float)` 逐条就是 PC 那个同名 API：`ldr s1,[x0,#0x354]` 读本格 → `fadd s0,s1,s0` 加上入参 → 与 `+0x358`（上限）比较后用 `csel` 取小者 → `str w8,[x0,#0x354]` 写回本格。⇒ 本格是被读-改-写的『当前值』，`+0x358` 是它的上限。
//   证据：0x0005e264 —— `HasMortalDamage()`（20 字节）只有两条字段读：`ldr s0,[x0,#0x20]` 与 `ldr s1,[x0,#0x354]`，然后 `fcmp` + `cset w0,ge` ⇒ 『缓冲 >= 本格』。契约 `Entity.md:451` 逐字：buffered damage 够杀就 true ⇒ 本格是**血量**、`+0x20` 是**伤害缓冲**。
inline constexpr std::uintptr_t kEntityHitPointsOffset = 0x354;
inline constexpr std::uintptr_t kEntityHitPointsWidth = 4;

// 血量上限（**float**，PC 的 `Entity.MaxHitPoints`，契约 `Entity.md:774`）。写它只改上限、**不会**自动把当前血量夹进去（夹的动作在引擎的 `AddHealth` 里）。（confirmed）
//   证据：0x0005a258 —— 同一函数里 `ldr s1,[x0,#0x358]` 作为上限参与 `fcmp`，`add x8,x0,#0x358` 又取本格**地址**用于 `csel` ⇒ 它就是『加到不能再加』的那个上限。
//   证据：0x0005a260 —— 名字的来源是**引擎自己的夹取语义**：`AddHealth` 里 `+0x354`（当前值）与 `+0x358`（本格）一起进 `fcmp`，紧接着 `add x8, x0, #0x358` **取本格地址**参与 `csel`，决定写回"加上去的值"还是"本格的值" ⇒ 本格是「加不过去的上限」，与 PC 的 `float MaxHitPoints`（`Entity.md:774`）同名同义。
inline constexpr std::uintptr_t kEntityMaxHitPointsOffset = 0x358;
inline constexpr std::uintptr_t kEntityMaxHitPointsWidth = 4;

// 这个实体当前是否免伤（无敌）（u8，取值 0/1）。PC 侧 `Entity:IsInvincible()` 读的就是这一格（PC 在 `Entity+0x308`；数值不许平移，两边 `Entity` 布局不同）。为什么能定案（三方夹）：① 具名写入方：`Entity_NPC_VisageMask::SetNoDamage(bool)` 把 bool 形参（`ands w8,w1,#0x1` 归一）直接 `strb` 进本格；② 出生清零：`Entity::Init` 里 `strb wzr,[x19,#0x384]`（新实体默认不免伤）；③ 受击闸门：`Entity::TakeDamage` 与 `Entity::IsVulnerableEnemy` 都「`ldrb` 本格 → `cbnz` 就直接跳过伤害」，且 `TakeDamage` 里紧随其后判的 `+0x1C3` 正是本项目已 confirmed 的 `IsDead`（守卫顺序与 PC 侧 `0x6D3F52` 那条逐字同形）。偏移对位：本区 PC `0x2C4`…`0x308` 的增量恒为 `+0x7C`（`Friction`/`HitPoints`/`MaxHitPoints` 三个已 confirmed 行给出同一增量，且 `0x2D8→0x308` 与 `0x354→0x384` 跨度同为 `0x30`）⇒ PC `0x308` 唯一自洽落点 = `0x384`。（confirmed）
//   证据：0x0025d644 —— **具名写入方（函数名即语义）**：`strb w8, [x0, #0x384]` —— `SetNoDamage(bool)` 把形参直接写进本格 ⇒ 『设置免伤』写的就是它
//   证据：0x0025d640 —— **取值锚点**：紧邻上一条写入的 `ands w8, w1, #0x1` —— 形参按 `& 1` 归一成 0/1 再写 ⇒ 本格是布尔（0/1），不是位域里的某一位
//   证据：0x0005999c —— **出生清零（默认值锚点）**：`strb wzr, [x19, #0x384]` —— 实体出生时这一格是 0（默认不免伤）
//   证据：0x0005dd80 —— 受击闸门：`ldrb w9, [x19, #0x384]` 紧跟 `cbnz w9, skip` —— 本格非 0 就直接跳过伤害结算；紧随其后判的 `+0x1C3` 正是本表已 confirmed 的 `IsDead`，与 PC 侧 `0x6D3F52` 那条守卫同形同序
//   证据：0x0005c648 —— **第二读者（函数名即语义）**：`ldrb w9, [x0, #0x384]` + `cbnz w9, →false` —— `IsVulnerableEnemy`（契约 `Entity.md`：「return true for enemies that can be damaged」）里本格非 0 就判『不是可伤害的敌人』⇒ 本格为真 = 当前无敌/免伤
inline constexpr std::uintptr_t kEntityIsInvincibleOffset = 0x384;
inline constexpr std::uintptr_t kEntityIsInvincibleWidth = 1;

// 实体自带 `RNG` 的对象头（16 字节 `kRngObjectSize`）—— 同时是种子/状态字（`RNG::Next` 把新状态写回对象头 4 字节 ⇒ 取过随机数就会变）。本行偏移 984 就是那个 `RNG` 的起始地址：`Entity:GetDropRNG()`（PC 契约 `Entity.md:377`）返回的正是这一格的地址。命名已由两平台各自的绑定逐字对上、不再是推断：PC 侧 `Entity.DropSeed @ 0x59FD60` = `mov eax,[ecx+0x334]`，而同一页的 `Entity:GetDropRNG @ 0x412390` = `lea eax,[ecx+0x334]` —— 两条指向同一格（PC 的 setter @ 0x59FD70 又从 `0x334/0x338` 整片写回 ⇒ 那 16 字节就是 RNG）；Switch 侧这一格的具名用途是 `RNG::SetSeed(seed, 30)`（`Entity::Init @ 0x597FC` 的 `mov w2,#0x1e`）。（confirmed）
//   证据：0x000597e8 —— **出生初始化**：`Entity::Init` 里 `add x21, x0, #0x3d8` 把这一格的地址交给紧随的 `RNG::SetSeed(uint,uint)`（0x5980C `bl 0x670970`），随后 0x59810 起再用同一地址调一次 ⇒ 这一格就是实体内嵌 RNG 的起点
//   证据：0x000597fc —— 取值锚点：`mov w2, #0x1e`（30）—— `RNG::SetSeed(seed, 用途)` 的第二个实参，这个常量把这一格与「随便某个整数格」区分开（同族：`Seeds` 的 RNG 用途是 39、描述符装饰种子是 35）
//   证据：0x00058978 —— 构造函数把 `this+0x3d8` 交给紧随的 0x58990 `bl 0x670930` = 导入符号 `_ZN15IsaacRepentance3RNGC1Ev`（`RNG::RNG()`）⇒ 这一格是**内嵌的 RNG 对象头**（实体基类只有这一个 RNG 成员）；出生时 `Entity::Init` 又用同一个 `this+0x3d8`（0x597E8 `add x21, x0, #0x3d8`）调 `RNG::SetSeed(unsigned, unsigned)`（0x5980C）设种子
//   证据：0x004550fc —— 存档按 **32 位**读它（0x455100 `str w8, [x19, #0x38]` 存进实体存档）；同函数 0x4550f4 存的是 `+0x3E8`（InitSeed），两者互证『这一格是 RNG 的种子字』
//   证据：0x004556ac —— 读档回灌：`add x0, x19, #0x3d8` 之后 `bl 0x670970` = `RNG::SetSeed(unsigned, unsigned)` ⇒ 这一格就是种子的落地位置
inline constexpr std::uintptr_t kEntityDropSeedOffset = 0x3D8;
inline constexpr std::uintptr_t kEntityDropSeedWidth = 4;

// 跟班所属的玩家实体指针（PC 的 `EntityFamiliar.Player`，`Entity_Player*`，可为 0）。⚠️ 引擎自己那几处读点都不判空，我们自己读之前必须先判 0（confirmed）
//   证据：0x000d8c98 —— `str x20, [x19, #0x400]` 把形参（`Entity_Player*`）写进这一格（同函数内另两处出口分支同址写入）
//   证据：0x000c0104 —— `ldr x0, [x0, #0x400]` 之后直接喂给『玩家的额外动画是否播完』⇒ 这一格指向的是玩家实体
//   证据：0x000d1184 —— 顺着这一格读出的指针，其 `+0x1738` 被当作 `Entity_Player.PlayerType` 读（0x1738 是本仓库已知的 PlayerType 偏移）⇒ 这一格存的是玩家实体，不是别的对象
inline constexpr std::uintptr_t kEntityFamiliarPlayerOffset = 0x400;
inline constexpr std::uintptr_t kEntityFamiliarPlayerWidth = 8;

// Entity 基类内嵌的主 ANM2（PC 的 `Entity:GetSprite()`）。Entity 单继承、基类子对象在偏移 0，所以所有 `Entity_*`（含 `Entity_Player`/`Entity_Pickup`）的这个 sprite 都在同一偏移。candidate：命名靠『引擎自己把 this+0x50 交给 ANM2 的成员函数』这条形态，没有取值锚点（candidate）
//   证据：0x0006252c —— `add x0, x19, #0x50` 之后紧接 `bl 0x6721d0`；该目标是导入符号 `_ZN15IsaacRepentance4ANM212BeginBatchesEv`（ANM2::BeginBatches）⇒ 引擎自己就把 this+0x50 当 ANM2 用
//   证据：0x0006257c —— 同一函数里真正画 sprite 那一步：`add x0, x19, #0x50` 之后 `bl 0x66fcf0` = 导入符号 `ANM2::Render(Vector2 const&, Vector2 const&, Vector2 const&)`（对照：紧随其后的 0x62538 用的是 `+0x320` 位置偏移，两者不是同一个量）
//   证据：0x000625cc —— 另一个函数（`Entity::PostRender`）里同样 `add x0, x20, #0x50` 后 `bl 0x6721e0` = 导入符号 `ANM2::EndBatches()` —— 两处不同函数互相印证同一个偏移
inline constexpr std::uintptr_t kEntitySpriteOffset = 0x50;
inline constexpr std::uintptr_t kEntitySpriteWidth = 8;

// 叠加在 `Position`(0x310) 上的绘制/逻辑位置偏移（Vector2，两个 float）。candidate：偏移与形态确定，但**命名是推断** —— 项目记录里已辨析过『0x320 与 Position(0x310)、插值旧位置(0x318) 连续构造、并被引擎当位置偏移用，所以判为 PositionOffset，不要拿它当 SpriteOffset』（candidate）
//   证据：0x00062538 —— `add x1, x19, #0x320` 作为第 2 个实参、`add x0, x19, #0x310`（Position）作为第 1 个实参，一起交给 `KAGE::Math::Vector2::operator+`（0x66ff50）⇒ 引擎渲染时算的是 Position + 本字段
//   证据：0x000598a8 —— 出生初始化：`add x0, x19, #0x320` 把该字段交给 0x598B8 `bl 0x66ff80` = `KAGE::Math::Vector2::operator=`（赋初值）
//   证据：0x002d9520 —— 玩家 sprite 渲染：先把整 16 字节 `[x19+0x320]` 存栈 → 临时置零 → 画完再还原 ⇒ 它是『画的时候才叠加』的偏移，不是位置本身
inline constexpr std::uintptr_t kEntityPositionOffsetOffset = 0x320;
inline constexpr std::uintptr_t kEntityPositionOffsetWidth = 16;

// 父实体指针（PC 的 `Entity.Parent`；多段实体的主段、跟班的主人、分段子段的回指都用它，0 表示没有父）。candidate：命名依据是引擎自己的三处符号名（`GetLastParent` 沿本格上溯、`SetParent` 写本格、`ClearReferences` 置 0），但没有被机器复核的取值常量（candidate）
//   证据：0x00058bec —— `ldr x0, [x0, #0x390]` + `cbnz` 循环：沿这一格一路往上找『没有父的那个实体』⇒ 它是父指针，且 0 是合法取值
//   证据：0x0005917c —— `add x21, x0, #0x390` 把该字段地址留在 x21，函数出口 0x59234 `str x19, [x21]` 把形参（新父）写进去；同函数还维护『父 + 0x3B8 的子集合』
//   证据：0x000599a8 —— 出生初始化 `str xzr, [x19, #0x390]`（按 8 字节清零）⇒ 与『0 是合法取值』一致
inline constexpr std::uintptr_t kEntityParentOffset = 0x390;
inline constexpr std::uintptr_t kEntityParentWidth = 8;

// 对外 API 只允许读这些字段（`confidence == confirmed`）。
// 当前可用：FlyingLayer、DropSeed、FamiliarPlayer、HitPoints、MaxHitPoints、Visible、Exists、IsDead、Friction、CollidesWithGrid、IsInvincible

} // namespace isaac::runtime::layout
