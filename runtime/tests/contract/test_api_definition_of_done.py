"""门禁：每条 API 的**完成定义（Definition of Done）**必须交代清楚 —— 契约依据 / 边界判据 / 成熟度。

## 为什么要有它（2026-09-21，用户提出的问题）

"每条 API 到底和 PC 语义一致不一致"这件事，此前**没有"实现时就必须交代"的强制机制**：

* `api_catalog.cpp` 只说"这条 API 存在"；
* `api_deviation.cpp` 只记"**已经知道**与 PC 不同的那几条"（2026-09-21 批次 017 起为 **24** 条）；
* 成熟度台账只要求"**宣称真机验证过**的必须有依据"。

中间的空白是最大的那块：**新加一条 API 时，"它凭什么说自己是 PC 的那个语义"
（在 `tools/pc_contract_docs/` 的哪一页哪一行）与"边界/异常输入是什么口径、谁钉住"
两件事，没有任何地方逼着人写**。写成注释没人读，不写也没人问 ——
这正是 107→109→110 三批返工（凭推断断言 PC 语义）与 098 那次
（`Room:GetGridPath` 恒返常量、后果写错）的共同根因。

所以本门禁钉住，**基线之外**的每一个 catalog id 必须在
`tools/api_definition_of_done.json` 里有条目，且三件事齐备：

1. **契约依据**：页在仓库里、行号在范围内、`quote` **逐字落在那一行上**；
2. **边界判据**：写明输入形状（受控词表）+ 一个**真实存在**的测试文件，
   **且那个文件里真的提到这条 API**（否则"判据"是随手指的一个文件）；
3. **成熟度**：与 `api_catalog.cpp` 逐字一致，且新 API 要在
   `tools/api_maturity_evidence.json` 里登记（四态之一）。

## 基线 grandfather（不能一次全红）

台账里的 `baseline.ids` 是**门禁建立当时**那 252 条的快照，它们豁免（补了的照样逐条校验）。
基线**只读**：本测试把它的**条数与摘要**写死，防止两件事 ——
① 有人偷偷删 API（基线 ⊆ catalog 那条也会红）；② 把新 API 塞进基线来躲门禁
（`test_baseline_digest_pin_catches_an_api_planted_into_the_baseline` 专门讲这件事）。

## 口径只有一份

判据、解析与错误文案都在 `tools/api_definition_of_done.py`（门禁不重写一套正则）。
本测试另外核对两处**口径漂移**：域名表 vs `api_descriptor.hpp` 的枚举、
catalog 解析 vs `test_api_maturity_ledger` 的解析。

## 合成回归（"门禁真的会红"）

下面用一份**最小合成仓库**（自造 catalog + 自造台账 + 自造契约页 + 自造测试文件）
把每种缺项各跑一遍：三个负面对照（缺三件事 / 抄错行 / 判据文件不对）
加一个**正面对照**（三件事齐备时不许红 —— 否则门禁是不可用的）。
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.api_definition_of_done import (
    BOUNDARY_KINDS,
    DOMAIN_VALUES,
    baseline_digest,
    check,
    load_catalog,
    load_ledger,
)

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
DESCRIPTOR = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_descriptor.hpp"
LEDGER = ROOT / "tools" / "api_definition_of_done.json"

#: ★ 账本数字（改动时必须同步并在这上面补一行说明，见 CONTRIBUTING.md 第二节）。
#:
#: 基线条数：2026-09-21 建立本门禁时冻结 **252** 条（当时 `api_catalog.cpp` 的全部目录行）。
#: 这个数字**只该保持不变** —— 基线是"历史快照"，新 API 不许塞进来（要塞就是躲门禁）。
BASELINE_COUNT = 252

#: 基线集合的摘要（`baseline_digest()` = 排序后逐行拼接的 sha256 前 16 位）。
#: 光看条数挡不住"删一条老的、加一条新的"那种同数量替换 ⇒ 用摘要钉死内容。
BASELINE_DIGEST = "b7f97f652bd6e631"

#: 台账里已有条目的数量：2026-09-21 建账时 **4** 条（都是"够格当模板"的老 API：
#: `Room:GetGridPath` / `Isaac:GetTime` / `Input:IsActionTriggered` / `EntityPlayer:GetPill`）。
#: 这个数字**只增不减**：删条目要么是 API 被删（那要一起改基线），要么是有人想躲门禁。
#: 批次 137（2026-09-26）加了三行（The Specialist for Good Items 的"跳舞 + 放歌"）⇒ 4 → 7。
#: 批次 138（2026-09-26）再加一行（`MusicManager:Play` —— 同一模组放歌的主路径）⇒ 7 → 8。
#: 批次 139（2026-09-26）再加一行（`Isaac:GetCostumeIdByPath` —— 同一模组加载期就要用的服装反查）⇒ 8 → 9。
#: 批次 140（2026-09-26）再加一行（`Game:GetPlayer` —— 同一模组 `MC_POST_NEW_ROOM` 里取玩家）⇒ 9 → 10。
#: 批次 148（2026-09-26）再加一行（`Isaac:GetMusicIdByName` —— 同一模组"放歌"那半条路要用它
#: 把曲目名换成引擎编号）⇒ 10 → 11。
#: 批次 195（2026-09-29）再加两行：`RNG:RandomInt` / `RNG:RandomFloat` —— 本批把四条 `Get*RNG`
#: 从恒 nil 改成真句柄之后，链上最后一环就是这两条（语料里的 Trinity 写
#: `GetCollectibleRNG(BIRTHRIGHT):RandomFloat()`）。两条的契约栏写 `missing`
#: （`tools/pc_contract_docs/` 下没有 `RNG.md`，仓库里只有 `analysis/isaacdocs-snapshot/docs/RNG.md`）
#: ⇒ 11 → 13。
#: 批次 195（2026-09-29）再加一行：`Isaac:ScreenToWorld`（`0x0E01005F`）—— 本批把两条坐标变换
#: 从"恒等"改成真调引擎、并补上 PC 本来就有而我们一直缺的反向变换。它的真值来源是
#: **PC 的四步算式**（引擎里没有反向入口，PC 自己也是就地算），WIDTH/HEIGHT/POINTSCALE
#: 运行期从引擎 GOT 槽读 ⇒ 13 → 14。
#: 批次 207（2026-09-29）再加十一行（为 MCM 补的那一批）：`Entity:IsActiveEnemy` /
#: `Entity:HasEntityFlags` / `Entity:ToProjectile` / `Game:GetHUD` / `HUD:IsVisible` /
#: `HUD:SetVisible` / `Isaac:GetEntityTypeByName` / `Isaac:GetEntityVariantByName` /
#: `Isaac:GetScreenWidth` / `Isaac:GetScreenHeight` / `Room:IsClear` ⇒ 14 → 25。
#: （其中两条 `GetEntity*ByName` 的 `provenance.kind` 是 `lua_side` —— 那张实体名表是
#: **编译进去的静态快照**，引擎里没有这个东西；其余按 `engine_call` / `engine_field` 登记。）
#: ★★ 批次 230（2026-09-30）补六行（**补的是批次 214 的欠账，不是本批新增的 API**）：
#: `Seeds:HasSeedEffect` / `Seeds:AddSeedEffect` / `Seeds:RemoveSeedEffect` /
#: `Sprite:Reset` / `Sprite:GetLayerCount` / `Sprite:GetDefaultAnimationName`
#: —— 批次 214 加了这六条接口却**没写完成定义**，于是这条门禁在 HEAD 上就是红的
#: （本批 230 的 `--fast` 把它抓出来）。六条的证据都来自**当时已经落地的取证**：
#: `Seeds:HasSeedEffect` = `engine_call`（`kSeedsEffectTreeOffset` + 三个树结点偏移）、
#: `Add/RemoveSeedEffect` = `platform_absent`（偏离台账 `0x0F010005`/`0x0F010006`）、
#: `Sprite:Reset`/`GetLayerCount`/`GetDefaultAnimationName` = `engine_call`
#: （`kSpriteResetOffset` / `kSpriteAnm2Offset`+`kAnim2LayerCountOffset` /
#: `kAnim2AnimationArrayOffset`+`kAnim2AnimationCountOffset`+`kAnim2AnimationStride`），
#: 边界判据分别点名 `test_lua_api_gap_batch3.py` 与 `test_lua_sprite.py` ⇒ 25 → 31。
#:
#: ★★ 批次 239（2026-09-30）：31 → **77**。补齐的是**同一类漏账的第二次重犯**：
#:   批次 238（语料模组适配第一波）加了 **28** 条引擎方法数据行、**没有写完成定义**，
#:   而 238 自己的门禁清单里**没有 `api_definition_of_done` 这一项** ⇒ 它上线时就带着这条红，
#:   直到批次 239 把这道门禁列进必跑清单才发现。239 的 18 条一并补齐 ⇒ 31 + 46 = 77。
#:   （第一次是批次 214 的 6 条，在 230 被发现 —— 见上面那段注释；这说明
#:   "加 API 必须同时写完成定义"这条还没有被机械地钉在任何地方，只靠人记得跑这道门禁。）
#:   46 条的边界判据统一指向新加的 `contract/test_engine_row_api_surface.py`
#:   （它按 **Lua 名字**钉住"哪条数据行挂了哪条 API、用什么形状、允许几个参数"），
#:   成熟度一律 `Experimental`，依据写在 `docs/问题与解决记录.md` 的同名小节。
#: ★ 批次 240（2026-09-30）：77 → **82** —— 名字表一族的 5 条（`Isaac.Get*ByName`）同批补齐。
#: 批次 241（2026-09-30）：再加一行 —— `ItemConfig_Item:IsRune()`（`0x007E`；PC 的类名是
#: `ItemConfig_Card`，契约页 `tools/pc_contract_docs/ItemConfig_Card.md:29`；真值来源 = 直读
#: `ItemConfig::Card+0x58` 的「卡类型 == 2 ⇒ 符文」）⇒ 82 → 83。
#: ★ 批次 242（2026-09-30）：83 → **88** —— C 批剩项（下转族 5 条）同批补齐。
#: ★ 批次 249（2026-10-01）：88 → **91** —— Room 三个 Vector 方法同批补齐。
#: ★ 批次 252（2026-10-01）：91 → **96**（A 组 2 + B 组 3）；批次 253：96 → **98**
#: （`Room:IsPositionInRoom` / `Game:CharmFart`）—— 两条都同批补了完成定义。
#: ★ 批次 254（2026-10-01）：98 → **103** —— 语料 API 恢复的 5 条
#: （`Game:MoveToRandomRoom` / `ItemPool:RemoveCollectible` / `EntityPlayer:AddKeys` /
#: `AddGoldenKey` / `AddGoldenBomb`）同批补齐。
#: ★ 批次 259（2026-10-01）：103 → **107** —— `Room` 四条位置类方法
#: （`FindFreePickupSpawnPosition` / `GetClampedPosition` / `FindFreeTilePosition` /
#: `GetDoorSlotPosition`）同批补齐；四条的真值来源都是 `engine_call`（手写处理器直调引擎方法）。
#: ★ 批次 261（2026-10-01）：107 → **110** —— `glue_compose` 桶三条
#: （`Isaac:GetChallenge` = `engine_field`；`Isaac:ConsoleOutput` 与 `Isaac:HasModData` = `lua_side`）
#: 同批补齐。
#: ★ 批次 262（2026-10-01）：110 → **112** —— `Isaac:GetFreeNearPosition` / `Isaac:GridSpawn`
#: 同批补齐（两条的真值来源都是 `engine_call`：前者直调 `Room::FindFreePickupSpawnPosition`，
#: 后者由三条引擎原语拼出来）。
#: ★ 批次 265（2026-10-02）：112 → **113** —— `Isaac:GetSoundIdByName` 同批补齐
#: （真值来源 `engine_field`，字段行在新开的 `tools/layout_tables/sound_effect.json`）。
#: ★ 批次 267（2026-10-02）：113 → **114** —— `Game:SpawnParticles` 同批补齐
#: （真值来源 `engine_call`：手写处理器直调 `Game::SpawnParticles`）。
#: ★ 批次 268（2026-10-02）：114 → **116** —— `Isaac:CountEntities`（`engine_call`：直调
#: `EntityList::CountSpawned`）与 `Isaac:RunCallbackWithParam`（`lua_side`：本 Runtime 自己的
#: 命名回调表，PC 侧那条不在基座 exe 里）同批补齐。
#: ★ 批次 269（2026-10-02）：116 → **120** —— `blocked_decision` 桶的四条（`Isaac:RenderText` /
#: `Isaac:GetTextWidth` 真值来源 `lua_side`；`Room:GetRenderMode` / `Room:GetRenderSurfaceTopLeft`
#: 两条 `Placeholder`，真值来源记 `engine_constant` 并在 `api_deviation.cpp` 里登记）。
#: ★ 批次 270（2026-10-02）：120 → **121** —— `Level:QueryRoomTypeIndex`
#: （真值来源 `engine_call`：直调 `Level::QueryRoomTypeIndex @ 0x3E605C`）。
#: ★ 批次 271（2026-10-02）：121 → **124** —— `Entity:SetColor` / `Entity:AddCharmed` /
#: `EntityPlayer:UseActiveItem`（真值来源都是 `engine_call`：直调引擎同名方法）。
#: ★ 批次 272（2026-10-02）：124 → **125** —— `GridEntity:Init`
#: （真值来源 `engine_call`：直调 `GridEntity::Init(unsigned)` @ 0x37E438）。
#: ★ 批次 273（2026-10-02）：125 → **133** —— `needs_new_receiver` 桶里参数最简单的 8 条
#: （`Entity:AddFreeze/AddPoison` + 玩家族六条；真值来源都是 `engine_call`）。
#: ★ 批次 274（2026-10-02）：133 → **145** —— 清桶批 12 条（`Entity` 3 + `EntityPlayer` 8
#: + `Seeds:ForgetStageSeed`；真值来源都是 `engine_call`）。
#: ★ 批次 275（2026-10-02）：145 → **147** —— `Entity:AddEntityFlags` / `ClearEntityFlags`
#: （真值来源 `engine_field`：写的就是 `Entity:HasEntityFlags` 那一格 `Entity+0x1B8`）。
#: ★ 批次 276（2026-10-02）：147 → **155** —— `GridEntity:GetGridIndex` + 7 条子类转换
#: （转换真值来源 `engine_call`：vtable 判据；`GetGridIndex` 读 `+0x28` 的字段）。
#: ★ 批次 277（2026-10-02）：155 → **156** —— `Entity:GetEntityFlags`
#: （真值来源 `engine_call`：读 `kEntityFlagsOffset` 那一格，与 275 的两条写侧同格）。
#: ★ 批次 278（2026-10-02）：156 → **161** —— `EntityPlayer` 族 5 条
#: （选批硬要求 = 引擎符号的参数个数与契约页完全一致；真值来源都是 `engine_call`）。
#: ★ 批次 279（2026-10-02）：161 → **164** —— `Sprite` 的 overlay 三条
#: （`PlayOverlay` / `SetLastFrame` / `SetOverlayFrame`；真值来源 `engine_call`）。
#: ★ 批次 280（2026-10-02）：164 → **166** —— `Sprite:GetDefaultAnimation`（与 …Name 同源、
#: 共用一份读法）与 `Sprite:Stop`（`ANM2::Stop()` @ 0xA8E4）。
#: ★ 批次 281（2026-10-02）：166 → **167** —— `EntityTear:ChangeVariant`
#: （`EntityTear` **视图**的第一条方法；真值来源 `engine_call`）。
#: ★ 批次 282（2026-10-02）：167 → **168** —— `EntityLaser:SetActiveRotation`
#: （`EntityLaser` **视图**的第一条方法；真值来源 `engine_call`）。
#:   ★ 同族的 `ShootAngle` 故意不做（引擎符号 7 参 vs 契约 6 参）⇒ 它**不进**这张表。
#: ★ 批次 283（2026-10-02）：168 → **172** —— `Sprite` 的四条「按名字查询」
#: （`IsOverlayPlaying` / `IsOverlayFinished` / `IsEventTriggered` / `WasEventTriggered`；
#: 真值来源 `engine_call`，走 libc++ `std::string` 桥）。
#: ★ 批次 284（2026-10-02）：172 → **177** —— `EntityPlayer:IsHoldingItem` /
#: `IsExtraAnimationFinished` + `GridEntityDoor:Open` / `Close` / `IsTargetRoomArcade`
#: （全部 `engine_call`；同批更正了批次 273「门的两条有重写」那句错话）。
#: ★ 批次 285（2026-10-02）：177 → **179** —— `EntityNPC:Morph`（`EntityNPC` **视图**的第一条
#: 方法，`Entity:ToNPC()` 从本批起压它）与 `EntityPickup:Morph`（后者是语料里真正在调的那条：
#: 3 参与 6 参两种写法都有 ⇒ 形状声明"尾部 3 个可省"）。两条都是 `engine_call`。
#: ★ 批次 286（2026-10-02）：179 → **180** —— `Entity:IsVulnerableEnemy()`（`engine_call`；
#: 全项目单条调用点最多的一条，22 处）。★ 那一次的计数改了、**这段说明漏了**，本批（287）补记。
#: ★ 批次 287（2026-10-02）：180 → **183** —— `EntityPlayer` 的"心数 / 金色钥匙"三条
#: （`GetBoneHearts` / `GetEternalHearts` / `HasGoldenKey`；真值来源都是 `engine_call`，
#: 走**字段读取型数据行** —— 三条在引擎里都没有同名函数，只能直读一个已取证的偏移）。
#: ★ 批次 288（2026-10-02）：183 → **186** —— `EntityPlayer` 的"方向"三条。前两条
#: （`GetHeadDirection` / `GetFireDirection`）是 `engine_call`、走字段读取型数据行；
#: 第三条（`GetMovementDirection`）是**真的 `engine_call`**（引擎符号
#: `Entity::get_movement_direction() const` @ `0x5C8AC`，形状 `Int0`）。
#: ★ 批次 289（2026-10-02）：186 → **188** —— `Room:GetTopLeftPos()` / `GetBottomRightPos()`。
#: 两条都是 `engine_field`：引擎里**没有同名访问器**（PC 侧那两个方法本体就是原样返回成员，
#: Switch 侧连符号都没有）⇒ 直读 `Room+0x1C` / `Room+0x24` 两个 `Vector2`，
#: 布局表里那两行是 `confirmed`（见 `tools/layout_tables/room.json` 的 `TopLeft`/`BottomRight`）。
#: ★ 批次 290（2026-10-02）：188 → **189** —— `Room:GetRoomShape()`（`engine_field`，
#: 直读两跳链末端的形状）。★ 那一次的计数改了、**这段说明漏了**，本批（291）补记。
#: ★ 批次 291（2026-10-02）：189 → **193** —— `Room` 的四个只读状态量
#: （`GetBossID` / `IsFirstVisit` / `IsAmbushDone` / `HasWaterPits`）。四条都是 `engine_field`：
#: 引擎里都没有同名访问器 ⇒ 直读字段（前两条在 `Room` 上、后两条在描述符的 `Flags` 位掩码上，
#: 本批为此新收 `FieldReceipt::RoomDescriptor` 并新增 `FieldKind::BoolBit`）。
#: 前两条的布局表行（`Room.BossId` / `Room.FirstVisit`）是本批新写进 `room.json` 的 `confirmed`
#: 行 —— 按作业单 G4，字段偏移要**先升到 `confirmed`** 才允许进对外 API。
#: ★ 批次 292（2026-10-02）：193 → **195** —— `Room:GetBackdropType()`（`engine_field`，
#: 读内嵌 `Backdrop` 里的 `eBackdrop`）与 `Room:SetClear(boolean)`（`engine_field`，
#: 往描述符 `Flags` 的 bit0 **写**实参 —— 本台账第一条"写侧"条目；对应的
#: `FieldKind::BoolBitWrite` 是本机制第一条不返回值、有副作用的 kind）。
#: ★ 批次 293（2026-10-03）：195 → **198** —— `Entity:IsVisible()` / `Entity:Exists()` /
#: `Entity:IsDead()`（三条都是 `engine_field`：PC 侧那三个绑定本体就是
#: `mov al,[ecx+0x169/0x16A/0x16B]; ret`，Switch 侧三格各有具名消费者）。
#: ★ 批次 294（2026-10-03）：198 → **201** —— `Level:GetPreviousRoomIndex()` /
#: `Level:GetLastBossRoomListIndex()`（`engine_field`，`Level` 的两个房间索引）与
#: `GridEntityDoor:IsRoomType(RoomType)`（`engine_field`，读门自己的两个房型字段 ——
#: 本批为此新建了布局表 `tools/layout_tables/grid_entity_door.json`）。
#: ★ 批次 295（2026-10-03）：201 → **203** —— `Room:GetDecorationSeed()` / `Room:GetSpawnSeed()`
#: （`engine_field`，读描述符上的两个种子；降级档 `Zero` 是**照 PC 抄的**：PC 的绑定本体在
#: 描述符为空时直接返回 0）。
#: ★ 批次 296（2026-10-03）：203 → **206** —— `EntityNPC:GetChampionColorIdx()` /
#: `EntityNPC:GetBossColorIdx()`（都是 `engine_field`，读 `Entity_NPC` 的 `+0xD10`/`+0xD24`，
#: 本批为此新建布局表 `tools/layout_tables/entity_npc.json`）与
#: `EntityPlayer:GetActiveCharge(ActiveSlot = SLOT_PRIMARY)`（`engine_call` —— 手写处理器，
#: 复用既有的 `kEntityPlayerActiveItemChargeOffset`/`kEntityPlayerActiveItemStride`，
#: 布局表里没有对应行 ⇒ 沿用 `GetBoneHearts` 那一档）。
#: ★ 批次 297（2026-10-03）：206 → **208** —— `Game:GetStateFlag(int Flag)` /
#: `Level:GetStateFlag(int Flag)`（都是 `engine_call`：位数组基址不是布局表意义上的具名字段，
#: 且地址由 `movz`+`movk` 合成、布局表的 `access` 证据核不了 → 沿用批次 287 那一档）。
#: 本批同时配了 `GameStateFlag` / `LevelStateFlag` 两张枚举表。
#: ★ 批次 298（2026-10-03）：208 → **209** —— `GridEntity:GetSprite()`（`engine_call`：
#: 它交回一个 `Sprite` 句柄，指向 `GridEntity + 0x48` 那个内嵌 ANM2；内嵌对象在布局表里
#: 只能是 `candidate` ⇒ 走这一档）。
#: ★ 批次 299（2026-10-03）：209 → **210** —— `EntityPlayer:HasFullHearts()`（`engine_call`：
#: 有意义的量是「三格算出来的」有效上限，没有单一具名字段可指向；判据与既有的
#: `GetEffectiveMaxHearts()` 共用同一份实现）。
#: ★ 批次 300（2026-10-03）：210 → **212** —— `Game:SetStateFlag(int Flag, boolean Value)` 与
#: `Level:SetStateFlag(int Flag, boolean Value)`（297 那两条**读**侧的写侧；同一对数组、
#: 同一份取证，走新种类 `FieldKind::BoolBitArrayOfWriteArg`）。
#: ★ 批次 301（2026-10-03）：212 → **213** —— `EntityPlayer:AddCacheFlags(CacheFlag)`
#: （**第一**条 `engine_field` 的写侧：`Entity_Player + 0x1958` 的 `_cacheFlags`，
#: 布局表 `entity_player.json` 的 `CacheFlags` 行 `confirmed`；行是新种类
#: `FieldKind::U32OrWithArg`（读改写：`字段 |= 实参`，返回 0 个值）。
#: 同批还发了 `CacheFlag` 全局枚举表）。
#: ★ 批次 302（2026-10-03）：213 → **215** —— `Room:SetFloorColor(Color)` 与
#: `Room:SetWallColor(Color)`（两条 `engine_field` 的**结构体写**：`Room+0x7968` / `+0x7994`
#: 各一个 44 字节的 `ColorMod`，布局表 `room.json` 的 `FloorColorMod`/`WallColorMod` 两行
#: `confirmed`；行是新种类 `FieldKind::ColorModWrite`（实参是 `Color` 句柄、返回 0 个值）。
#: ★ 批次 303（2026-10-03）：215 → **217** —— `Entity:CanShutDoors()` 与 `EntityNPC:CanShutDoors()`
#: （**第一批"按 vtable 槽号调用"的引擎方法行**：`offset` 最高位置 1 = 虚调用、低 31 位 = 槽号；
#: 槽号 18 从 Switch 的 `_ZTV` 读出，`offsets` 里给的是 `kEntityVtableCanShutDoorsSlot`）。
#: ★ 批次 304（2026-10-03）：217 → **219** —— `GridEntity:Destroy(boolean)` 与 `GridEntity:PostInit()`
#: （两条 `engine_call`：`offsets` 给的是槽号常量 `kGridEntityVtableDestroySlot` / `…PostInitSlot`）。
#: ★ 批次 310（2026-10-03）：227 → **228** —— `Room:GetAliveBossesCount()`
#: ★ 批次 309：226 → 227 —— `Sprite:GetFilename()`
#: ★ 批次 308：225 → 226 —— `GridEntity:SetType(eGridEntityType)`
#: ★ 批次 307：224 → 225 —— `Room:GetGridEntityFromPos(Vector)`
#: ★ 批次 306：222 → 224 —— `Seeds:GetStageSeed()` / `GetNextSeed()`
#: ★ 批次 305：219 → 222 —— `MusicManager:Disable()` / `Enable()` / `IsEnabled()`
#: （三条 `engine_field`：`Music + 0x3F0` 那一格，布局表 `tools/layout_tables/music.json` 的
#: `Enabled` 行 `confirmed`）。
#: ★ 批次 312（2026-10-03）：229 → **230** —— `EntityPlayer:IsCoopGhost()`
#: （只读字段行：`Entity_Player + 0x284C` 那**一个字节**，`FieldKind::Bool`；取值锚点 =
#: `morph_to_coop_ghost` / `init_coop_ghost` 置 1、`revive_coop_ghost` 清 0、
#: `PlayerManager::GetNumCoopPlayersAlive` 反向计数 ⇒ 证据是 `engine_call`）。
#: ★ 批次 313（2026-10-03）：230 → **232** —— `Level:HasBossChallenge()` /
#: `Level:GetCanSeeEverything()`（两条只读字段行：`Level + 0x08` / `+0x11` 各**一个字节**，
#: `FieldKind::Bool`；偏移靠「Switch 的 `Level` 头部与 PC 逐格一致」（`+0x00`/`+0x04`/`+0x0C`
#: 三条两平台同值的锚点）+ `Level::StoreGameState`/`RestoreGameState` 存读这四格 +
#: `Level::try_display_room` 的透视分支自证语义 ⇒ 证据是 `engine_call`）。
#: ★ 批次 314（2026-10-03）：232 → **233** —— `EntityNPC:IsChampion()`
#: （只读字段行：`Entity_NPC + 0xD0F` 那**一个字节**，`FieldKind::Bool`；三个具名写入方
#: `Init` 清 0 / `MakeChampion` 置 1 / `Morph` 置 1、且**永远与冠军色号 `+0xD10` 同批写**；
#: ★ 本批同时更正 296 的一条负结果：PC 的真绑定是 `0x68F580`（一条指令），不是它记的
#: `0x68F550`（那个地址全镜像 0 次引用））。
#: ★ 批次 315（2026-10-03）：233 → **234** —— `Entity:Die()`
#: （**写侧**字段行：往 `Entity + 0x1C3` 写常量 **1**，`FieldKind::BoolWriteConst`；
#: ★★ 本批推翻交接 §4 的"0 实现 ⇒ 别碰"：PC 侧 `Die @ 0x436B60` = `movb $0x1,0x16b(%ecx); ret`
#: 与 `IsDead @ 0x412350` 的 `movb 0x16b(%ecx),%al` **读写同一格** ⇒ 纯字段写、不需要引擎函数）。
#: ★ 批次 316（2026-10-03）：234 → **235** —— `Entity:GetDropRNG()`
#: （只读字段行：把 `Entity + 0x3D8` 那 **16 字节 `RNG`** 读成快照、压 `kRngMetatable` 句柄 ⇒
#: 本批新开的 `FieldKind::RngSnapshot`；★ 偏移不是新取的 —— 它就是既有的 `Entity.DropSeed`
#: 那一格，实体基类只有这一个 RNG 成员、种子就是 RNG 对象头 4 字节 ⇒ 两者同址，
#: PC 侧 `DropSeed @ 0x59FD60` 与 `GetDropRNG @ 0x412390` 两条绑定**指着同一格**）。
#: ★ 批次 321（2026-10-03）：235 → **236** —— `GridEntity:Update()`
#: （按 vtable 槽号虚调用，槽 3；★★ 基类那格 `__cxa_pure_virtual`、每个派生类都在槽 3 覆盖它）。
#: ★ 批次 324（2026-10-03）：236 → **237** —— `EntityNPC.ThrowSpider(...)`
#: （★★★ 本项目第一条**静态调用**：点号直呼在类名上；同批加了「静态调用」标记与「句柄返回」两种能力）。
#: ★ 批次 325（2026-10-03）：237 → **238** —— `EntityLaser.ShootAngle(...)`
#: （静态调用 + 句柄返回，与 324 同一套能力；★ 推翻了批 282 的排除理由）。
#: ★ 批次 326（2026-10-03）：238 → **239** —— `EntityPlayer:FireTechLaser(...)`
#: （★ 第一次用 `EngineArgKind::FloatDefaultOne`：缺省是 1 的浮点参数）。
#: ★ 批次 327（2026-10-03）：239 → **240** —— `Room:IsDoorSlotAllowed(DoorSlot)`
#: （只读字段数据行：按 Lua 实参给的门位测 `RoomConfig::Room.Doors`（`Data+0x40`）的第 n 位；
#: **复用**既有的 `FieldKind::BoolBitArrayOfArg` 与 `FieldReceipt::RoomConfigData` ⇒ 0 字节代码）。
#: ★ 批次 328（2026-10-03）：240 → **242** —— `EntityPlayer:GetShootingInput()` /
#: `GetShootingJoystick()`（两条**手写处理器**：引擎返回 `Vector`（两个 float 的 HFA ⇒ `s0`/`s1`），
#: 通用跳板只回填 `x0`/`d0` ⇒ 表达不了；两条在 PC 上共用同一个绑定 VA `0x741B00`）。
#: ★ 批次 330（2026-10-03）：242 → **244** —— `EntityFamiliar:FollowParent()` /
#: `AddToFollowers()`（两条引擎方法行，无参/void；★ 本批真正的产出是给 `EntityFamiliar`
#: 建了自己的视图元表，否则方法没有地方挂）。
#: ★ 批次 332（2026-10-03）：244 → **245** —— `EntityPlayer:GetMovementJoystick()`
#: （手写处理器：引擎返回 `Vector`（HFA）⇒ 跳板表达不了；★ 引擎里那个函数叫
#: `get_movement_input`，**名字不一样**，靠逐条对照函数体定案）。
#: ★ 批次 333（2026-10-03）：245 → **246** —— `Entity:MultiplyFriction(float Value)`
#: （字段数据行，走**新开**的 `FieldKind::FloatMultiplyArg`：读改写 `Entity + 0x340` 那一格 float）。
#: ★ 批次 334（2026-10-03）：246 → **247** —— `EntityPlayer:CheckFamiliar(...)`
#: （手写处理器：5 个形参、后两个是**非 0 缺省值**（`nil`/`-1`）⇒ 数据行那条路缺两种表达能力）。
#: ★ 批次 335（2026-10-03）：247 → **250** —— 交接第八份 §3「批 A」的三条**引擎方法数据行**：
#: `EntityPlayer:ChangePlayerType(PlayerType)` / `EntityPlayer:DischargeActiveItem(ActiveSlot)`
#: （共用本批新开的形状 33 `VoidIntBoolOpt1` = `void(this, i32, bool)`、尾部 1 个可省：
#: 契约各写 1 个形参、引擎符号都是 2 格 ⇒ 按符号取）与 `Seeds:SetStartSeed(int)`
#: （形状 `Void1`；接收者是本批新开的 `FieldReceipt::Seeds` = `Game + kGameSeedsObjectOffset`）。
#: ★ 批次 336（2026-10-03 深夜）：250 → **252** —— 交接第八份 批 B/批 C 的"纯取证批"两条
#: **字段数据行**：`Room:GetTintedRockIdx()`（`Room+0xE90`，`I32`）与
#: `Entity:CollidesWithGrid()`（`Entity+0x1EC`，`Bool`）；两条都复用现成的
#: `FieldKind`/`FieldReceipt` ⇒ **0 字节代码**。
#: ★ 批次 337（2026-10-04 凌晨）：252 → **253** —— `EntityPlayer:FireTear(...)`
#: （**手写处理器**：契约 7 个形参、引擎 5 格 + **两个缺省 `true` 的布尔** + **按值 HFA**）。
#: ★ 批次 339（2026-10-04）：253 → **254** —— `EntityFamiliar:FireProjectile(Vector Dir)`
#: （**手写处理器**：引擎真身在、契约少一个隐藏 bool）。
#: ★ 批次 340（2026-10-04）：254 → **256** —— `Game:Spawn(...)` 与 `Isaac.Spawn(...)`
#: （**两条手写**：引擎第 8 个形参走栈 / `Isaac.Spawn` 形参序不同 + 随机种子）。
#: ★ 批次 341（2026-10-04）：256 → **260** —— 四条：
#: `Entity:IsInvincible()`（字段行，`Entity + 0x384`）、
#: `EntityLaser:SetMaxDistance(float)`（字段行，写 `Entity_Laser + 0x4F8`，新 kind `FloatFromArg`）、
#: `EntityPlayer:TryRemoveTrinketCostume(TrinketType)`（引擎方法行，`Void1`）、
#: `EntityFamiliar:FollowPosition(Vector Pos)`（引擎方法行，新形状 `VoidVector2Ref`）。
#: ★ 批次 342（2026-10-04）：260 → **263**（三条）；批次 343（2026-10-04）：263 → **266**
#: （三条）—— 这两批的逐条说明见各自的改动日志节。
#: ★ 批次 344（2026-10-04）：266 → **268** —— 两条：
#: `EntityPlayer:AnimateCollectible(Collectible, AnimName?, SpriteAnimName?)`
#: （**手写处理器**：字符串实参 + 两个**非空字符串缺省**；真身是**改名**后的
#: `Entity_Player::AnimatePickup(eCollectibleType, char const*, char const*) @ 0x2DD150`）
#: 与 `PathFinder:HasPathToPos(Vector Pos, boolean IgnorePoop)`（**引擎方法数据行**，
#: 本批新开 `FieldReceipt::PathFinder` + 形状 `BoolVector2RefBool`；真身
#: `NPCAI_Pathfinder::HasPathToPos(Vector2 const&, bool) const @ 0x42F6CC`）。
#: ★ 批次 345（2026-10-04）：268 → **269** —— 一条：
#: `Isaac.Explode(Vector pos, Entity source, float damage)`（**手写处理器**：引擎真身
#: `Game::BombExplosionEffects @ 0x355C68` 有 **9 个形参** ⇒ 第 9 格 `bool` **走栈**
#: （`ldrb w21,[x29,#0x60]`），通用跳板填不了；第 4 格是 16 字节**按值**的 `bitset128_t`）。
#: ★ 批次 346（2026-10-04）：269 → **270** —— 一条：
#: `Entity:AddVelocity(Vector[, boolean IgnoreTimeScale])`（**手写纯算法**：Switch 侧**没有可调真身**
#: ⇒ 按 PC 绑定 `0x422B60` 的算式直接读写「速度 `+0x334/+0x338` / 摩擦 `+0x340` / 时间缩放 `+0x370`」；
#: ★★ 本条**推翻旧负结果**「两侧摩擦模型不同 ⇒ 不能做」）。
#: ★ 批次 347（2026-10-04）：270 → **271** —— 一条：
#: `RoomConfigSpawn:PickEntry(float r)`（**手写处理器**：真身
#: `_ZNK15IsaacRepentance10RoomConfig5Spawn9PickEntryEf @ 0x494910`；连同 `Data.Spawns`
#: 换真容器 + 两个视图 + 一条 `Partial/design` 偏离）。
# 2026-10-10：PGD AddBestiaryKill/AddBossKilled/IsBossKilled三条，313→316。
# Agony跟班轨道四方法：316→320。
# 2026-10-10：GetData两条基线主动补DoD，加Agony原生三查询，320→325。
#: 2026-10-13追加健康16、方法35、HUD3、Color2、Options1：339→396。
# 2026-10-14追加100个方法：396→496。
# 第二批100追加：496→596。

# 第三批100追加：596→696，旧记录保留。
# 2026-10-15：追加Global:Random完整定义一行，696→697。
# 2026-10-15：追加Options:FoundHUD原生开关完整定义，697→698。
# 2026-10-16：第五批实际740条，第六批新增46条，最终786；旧历史注释保留。
# 2026-10-16：第七批新增43方法，786→829，18字段独立登记不混算。
EXPECTED_ROWS = 829


def _entry(sequence: str, name: str, maturity: str = "Experimental", domain: str = "Room",
           owner: str | None = None) -> str:
    """合成 catalog 里的一行（形状与真实 `api_catalog.cpp` 一致）。"""
    return (f'    {{MakeId(ApiDomain::{domain}, 1, {sequence}), ApiDomain::{domain}, '
            f'"{owner or domain}", "{name}", kV1, 0,\n'
            f'     ThreadAffinity::MainUpdate, ApiMaturity::{maturity}}},\n')


#: 合成契约页（行号是真数出来的：第 5 行就是新 API 那一行）。
SYNTHETIC_PAGE_LINES = [
    "# Room",
    "",
    "#### int GetGridPath ( int Index )",
    "",
    "#### int NewProbe ( int Index )",
]

#: 合成测试文件：必须**提到那条 API**（门禁按接口名/id 找）。
SYNTHETIC_TEST = "def test_new_probe_out_of_range():\n    # Room:NewProbe / 0x04010002 越界下标\n    pass\n"


def _synthetic_ledger(baseline_ids, rows) -> dict:
    return {
        "schema": 1,
        "note": ["合成台账（只给门禁自证用）"],
        "baseline": {"note": "合成", "count": len(baseline_ids), "ids": list(baseline_ids)},
        "rows": rows,
    }


class SyntheticRepoMixin:
    """搭一份最小合成仓库，供"门禁真的会红"的对照用（不依赖真实 catalog）。"""

    def synthetic_repo(self, *, rows=None, baseline_ids=None, maturity_rows=None,
                       test_files=None, extra_entries=None, page_lines=None) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="dod-synthetic-"))
        self.addCleanup(shutil.rmtree, directory, True)

        (directory / "runtime" / "src" / "interfaces" / "lua").mkdir(parents=True)
        (directory / "runtime" / "source").mkdir(parents=True)
        (directory / "runtime" / "tests").mkdir(parents=True)
        (directory / "tools" / "pc_contract_docs").mkdir(parents=True)

        # 偏移的权威落点（`provenance.kind` 是 engine_call/engine_field 时，证据必须落在它里面）。
        (directory / "runtime" / "source" / "runtime_constants.hpp").write_text(
            "inline constexpr uintptr_t kSyntheticProbeOffset = 0x1234;\n", encoding="utf-8")

        entries = [_entry("0x0001", "GetGridPath", "HostVerified")]
        entries.extend(extra_entries if extra_entries is not None else [_entry("0x0002", "NewProbe")])
        (directory / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp").write_text(
            "constexpr LuaApiDescriptor kDefaultApis[] = {\n" + "".join(entries) + "};\n",
            encoding="utf-8")

        (directory / "tools" / "pc_contract_docs" / "Room.md").write_text(
            "\n".join(page_lines if page_lines is not None else SYNTHETIC_PAGE_LINES) + "\n",
            encoding="utf-8")

        files = test_files if test_files is not None else {
            "runtime/tests/test_synthetic_probe.py": SYNTHETIC_TEST}
        for relative, content in files.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        (directory / "tools" / "api_maturity_evidence.json").write_text(
            json.dumps({"schema": 1, "rows": maturity_rows if maturity_rows is not None
                        else {"Room:NewProbe": {"maturity": "Experimental", "evidence": []}}},
                       ensure_ascii=False), encoding="utf-8")

        (directory / "tools" / "api_definition_of_done.json").write_text(
            json.dumps(_synthetic_ledger(
                baseline_ids if baseline_ids is not None else ["Room:GetGridPath"],
                rows if rows is not None else {"Room:NewProbe": complete_row()}),
                ensure_ascii=False), encoding="utf-8")
        return directory


def complete_row() -> dict:
    """一份**合格**的台账条（正面对照的基准）。"""
    return {
        "contract": {"page": "tools/pc_contract_docs/Room.md", "line": 5,
                     "quote": "#### int NewProbe ( int Index )"},
        "boundary": {"kind": "越界下标", "judgement": "runtime/tests/test_synthetic_probe.py",
                     "detail": "Index 越界（负数 / >= W*H）一律返回 0，不读越界内存"},
        # 第 4 栏（2026-09-25）：真值来源。用 engine_call —— 只要偏移能在
        # `runtime/source/runtime_constants.hpp` 里找到就算合格（合成仓库里放了那个常量）。
        "provenance": {"kind": "engine_call",
                       "detail": "调引擎自己的 Room::NewProbe（偏移见 kSyntheticProbeOffset）",
                       "offsets": ["kSyntheticProbeOffset"]},
        "maturity": "Experimental",
    }


class ApiDefinitionOfDoneTests(SyntheticRepoMixin, unittest.TestCase):
    # ------------------------------------------------------------------ 现仓库

    def test_ledger_is_shaped(self):
        self.assertTrue(LEDGER.is_file(), "缺少 tools/api_definition_of_done.json")
        ledger = load_ledger()
        self.assertEqual(ledger["schema"], 1)
        self.assertIn("baseline", ledger)
        self.assertIn("rows", ledger)

    def test_repository_passes_every_criterion(self):
        """★ 主判据：当前仓库必须整体通过（红就是有人加了 API 没交代）。"""
        report = check()
        self.assertEqual(report.errors, [], "完成定义门禁未通过：\n  - " + "\n  - ".join(report.errors))
        self.assertGreater(report.catalog_size, 200, "catalog 解析结果太少，门禁失去意义")

    def test_baseline_is_frozen(self):
        """基线**只读**：条数与摘要都被钉死。"""
        ledger = load_ledger()
        ids = ledger["baseline"]["ids"]
        self.assertEqual(len(ids), BASELINE_COUNT,
                         "基线条数变了。基线是历史快照，**不许增删** —— "
                         "新增 API 请填 completion rows，不要往 baseline 里塞。")
        self.assertEqual(ledger["baseline"]["count"], BASELINE_COUNT,
                         "baseline.count 与 BASELINE_COUNT 不一致")
        self.assertEqual(baseline_digest(ids), BASELINE_DIGEST,
                         "基线内容变了（同数量替换也算）。确认是「真的删了 API」再同步摘要并写清原因。")

    def test_every_baseline_api_still_exists(self):
        """不许偷偷删接口：基线里的每一条都还在 catalog 里。"""
        catalog = load_catalog()
        missing = sorted(set(load_ledger()["baseline"]["ids"]) - set(catalog))
        self.assertEqual(missing, [], f"基线里这些 API 从 catalog 消失了：{missing}")

    def test_registered_rows_are_really_checked(self):
        """台账里已有的条目**逐条真的被校验过**（否则这张台账就是装饰）。"""
        report = check()
        self.assertEqual(report.rows_checked, EXPECTED_ROWS,
                         "已登记条数变了（只增不减；减少说明有人删了条目）。")

    def test_new_apis_are_exactly_those_outside_the_baseline(self):
        report = check()
        baseline = set(load_ledger()["baseline"]["ids"])
        self.assertEqual(set(report.new_apis), set(load_catalog()) - baseline)

    # ------------------------------------------------------- 口径漂移的两处互证

    def test_domain_table_matches_the_cpp_enum(self):
        """工具里的域名表必须与 `api_descriptor.hpp` 的 `ApiDomain` 枚举一致（口径只有一份）。"""
        text = DESCRIPTOR.read_text(encoding="utf-8")
        block = re.search(r"enum class ApiDomain[^{]*\{(.*?)\};", text, re.S)
        self.assertIsNotNone(block, "api_descriptor.hpp 里没找到 ApiDomain 枚举")
        enum_values = {name: int(value) for name, value in
                       re.findall(r"(\w+)\s*=\s*(\d+)", block.group(1))}
        self.assertTrue(enum_values, "枚举解析结果为空 —— 解析口径过期了")
        self.assertEqual(DOMAIN_VALUES, enum_values,
                         "本工具的 DOMAIN_VALUES 与 C++ 枚举漂移了（新加域名要同步两处）")

    def test_catalog_parser_agrees_with_the_maturity_ledger_gate(self):
        """本工具解析 catalog 的结果，必须与成熟度门禁那套解析**逐条一致**。"""
        from runtime.tests.test_api_maturity_ledger import catalog_maturity

        mine = {key: entry.maturity for key, entry in load_catalog().items()}
        theirs = catalog_maturity()
        self.assertEqual(mine, theirs, "两套 catalog 解析口径漂移了（有一边正则过期）")

    # -------------------------------------------------------------- 合成负面对照

    def test_a_new_api_without_any_of_the_four_turns_red(self):
        """★ 主反面：新 API 什么也没交代 ⇒ **四件事**逐条点名。"""
        directory = self.synthetic_repo(rows={})
        report = check(root=directory)
        joined = "\n".join(report.errors)
        self.assertFalse(report.ok, "新 API 什么都没交代，门禁却绿了")
        self.assertIn("[新接口] Room:NewProbe", joined)
        for piece in ("契约依据", "边界判据", "真值来源", "成熟度"):
            self.assertIn(piece, joined, f"缺项里没有点名「{piece}」：\n{joined}")

    def test_a_complete_row_passes(self):
        """★ 正面对照：四件事齐备时**不许红** —— 否则这条门禁是不可用的。"""
        directory = self.synthetic_repo()
        report = check(root=directory)
        self.assertEqual(report.errors, [], "合格条目被误判：\n  - " + "\n  - ".join(report.errors))
        self.assertEqual(report.new_apis, ["Room:NewProbe"])

    # ------------------------------------------- 第 4 栏「真值来源」（2026-09-25 批次 127）

    def test_a_missing_provenance_turns_red(self):
        """只交代前三栏、不说返回值从哪来 ⇒ 红（这正是"能跑但语义和 PC 不同"的入口）。"""
        row = complete_row()
        row.pop("provenance")
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("真值来源", joined)
        self.assertIn("[新接口] Room:NewProbe", joined)

    def test_an_offset_that_is_not_in_the_constants_header_turns_red(self):
        """`engine_call` 的偏移证据必须在 `runtime_constants.hpp` 里真的找得到（凭记忆写 ⇒ 红）。"""
        row = complete_row()
        row["provenance"] = {"kind": "engine_call", "detail": "这个偏移是凭记忆写的，没有去头文件核对",
                             "offsets": ["kThisOffsetDoesNotExist"]}
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("kThisOffsetDoesNotExist", joined)
        self.assertIn("runtime_constants.hpp", joined)

    def test_engine_constant_without_a_deviation_entry_turns_red(self):
        """★ 本次加固的正题：承认"返回值不是引擎真值"就必须在偏离台账里登记。

        这条判据堵的是 `EntityPlayer:HasTrinket`（恒 false）/ `Isaac:WorldToScreen`（恒等变换）
        那一类：它们有目录行、能被调用、模组拿到假值，而"偏离必须登记"此前**全靠自觉**。
        """
        row = complete_row()
        row["provenance"] = {"kind": "engine_constant",
                             "detail": "引擎里拿不到这个值，恒返回 false 以保证模组能跑"}
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("api_deviation.cpp", joined)
        self.assertIn("0x04010002", joined)

    def test_a_wrong_contract_line_turns_red(self):
        """抄错行 / 凭记忆写一句：引文必须逐字落在那一行上。"""
        row = complete_row()
        row["contract"]["quote"] = "#### int NewProbe ( int Index, int Extra )"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        report = check(root=directory)
        joined = "\n".join(report.errors)
        self.assertIn("[契约依据] Room:NewProbe", joined)
        self.assertIn("引用与文档对不上", joined)

    def test_a_contract_line_out_of_range_turns_red(self):
        row = complete_row()
        row["contract"]["line"] = 999
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        self.assertIn("没有第 999 行", "\n".join(check(root=directory).errors))

    def test_a_citation_of_another_api_turns_red(self):
        """★ 抄**另一条 API**的那一行也过不去：引文里必须出现这条 API 的名字。

        为什么要有这一半：只核对"片段真的在那一行里"，随手抄邻居 API 的规格行也能过 ——
        那也是假通过（与 099 那次"关键词恰好出现"同一族）。
        """
        row = complete_row()
        row["contract"]["line"] = 3                     # 那是 `Room:GetGridPath` 的规格行
        row["contract"]["quote"] = "#### int GetGridPath ( int Index )"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("引文里没有出现这条 API 的名字", joined)

    def test_a_contract_page_outside_the_repo_turns_red(self):
        """契约源必须在仓库里 —— 指到 `analysis/`（gitignore）就是"对别人不可做"。"""
        row = complete_row()
        row["contract"]["page"] = "analysis/isaacdocs-snapshot/docs/Room.md"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("不在", joined)
        self.assertIn("analysis/", joined)

    def test_a_missing_judgement_file_turns_red(self):
        row = complete_row()
        row["boundary"]["judgement"] = "runtime/tests/test_does_not_exist.py"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        self.assertIn("判据指向不存在的测试文件",
                      "\n".join(check(root=directory).errors))

    def test_a_judgement_file_that_never_mentions_the_api_turns_red(self):
        """★ 反"随手指一个存在的测试文件"：那个文件里必须真的提到这条 API。"""
        row = complete_row()
        directory = self.synthetic_repo(
            rows={"Room:NewProbe": row},
            test_files={"runtime/tests/test_synthetic_probe.py": "def test_something_else():\n    pass\n"})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("找不到这条 API 的名字", joined)

    def test_an_unregistered_maturity_turns_red(self):
        directory = self.synthetic_repo(rows={"Room:NewProbe": complete_row()},
                                        maturity_rows={})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("api_maturity_evidence.json 里没有 Room:NewProbe 的条目", joined)

    def test_a_maturity_disagreeing_with_the_catalog_turns_red(self):
        row = complete_row()
        row["maturity"] = "HardwareVerified"      # catalog 里是 Experimental
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("[成熟度] Room:NewProbe", joined)
        self.assertIn("两边必须一起改", joined)

    def test_a_placeholder_boundary_turns_red(self):
        """占位式写法（`暂无`/`TODO`）等于没写。"""
        row = complete_row()
        row["boundary"]["detail"] = "暂无"
        row["boundary"]["kind"] = "随便写的形状"
        directory = self.synthetic_repo(rows={"Room:NewProbe": row})
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("不在受控词表里", joined)
        self.assertIn("不许占位", joined)
        self.assertTrue(BOUNDARY_KINDS, "受控词表不能是空的")

    def test_a_ledger_row_for_an_unknown_api_turns_red(self):
        """死账：台账里的 key 必须在 catalog 里真实存在。"""
        directory = self.synthetic_repo(rows={"Room:NewProbe": complete_row(),
                                              "Room:TypoName": complete_row()})
        self.assertIn("[死账]", "\n".join(check(root=directory).errors))

    def test_a_deleted_baseline_api_turns_red(self):
        directory = self.synthetic_repo(baseline_ids=["Room:GetGridPath", "Room:Vanished"])
        joined = "\n".join(check(root=directory).errors)
        self.assertIn("[基线]", joined)
        self.assertIn("Room:Vanished", joined)

    def test_baseline_digest_pin_catches_an_api_planted_into_the_baseline(self):
        """★ 反规避：把新 API 塞进基线，`check()` 确实会变绿 —— 所以基线被摘要钉死。

        这是这套设计里**唯一**的规避路径（不放宽基线就绕不过去），因此要显式证明它被堵住：
        合成的仓库里把 `Room:NewProbe` 放进 baseline，`check()` 不再报缺项；
        而真实台账的基线摘要与本测试里写死的 `BASELINE_DIGEST` 一比就对不上 ⇒ 门禁红。
        """
        directory = self.synthetic_repo(rows={}, baseline_ids=["Room:GetGridPath", "Room:NewProbe"])
        self.assertEqual(check(root=directory).errors, [],
                         "（预期）塞进基线后 check() 不再报缺项 —— 这正是要防的规避路径")

        planted = load_ledger()["baseline"]["ids"] + ["Room:NewProbe"]
        self.assertNotEqual(baseline_digest(planted), BASELINE_DIGEST,
                            "基线被塞进了新 API，摘要却没变 —— 摘要失去意义")
        self.assertEqual(baseline_digest(load_ledger()["baseline"]["ids"]), BASELINE_DIGEST)

    # ------------------------------------------------------------------- 进度

    def test_progress_is_reported(self):
        """只报进度、不判红：缺口数字一眼可见（回填的时候要用它）。"""
        report = check()
        by_owner: dict[str, int] = {}
        for key in report.gaps:
            owner = key.partition(":")[0]
            by_owner[owner] = by_owner.get(owner, 0) + 1
        print(f"\n[进度] catalog {report.catalog_size} 条 = 基线 {report.baseline_size} 条（豁免）"
              f" + 新接口 {len(report.new_apis)} 条；已交代 {report.rows_checked} 条；"
              f"**基线里还没交代的是 {len(report.gaps)} 条**"
              f"（{', '.join(f'{k} {v}' for k, v in sorted(by_owner.items(), key=lambda i: -i[1])[:6])} …）")
        # 缺口 = 基线 − **基线里**已交代的条数。
        # ★ 批次 137（2026-09-26）修正：原式写成 `baseline_size - rows_checked`，它隐含假设
        #   "台账里的每一条都在基线里" ⇒ **任何**新 API 一旦按文档流程填了 `rows`，这条进度断言
        #   就会红（`rows_checked` 把基线之外的新接口也算进去了）。算式改对，判据不变。
        ledger = load_ledger()
        baseline_ids = set(ledger["baseline"]["ids"])
        documented_baseline = len([key for key in ledger["rows"] if key in baseline_ids])
        self.assertEqual(len(report.gaps), report.baseline_size - documented_baseline)


if __name__ == "__main__":
    unittest.main()

# 2026-10-09：GetName与7个音效真实接口在本轮早先已追加8行，288→296；临时效果只改现有5行。

# 2026-10-09：PGD:Unlocked真实契约新增1行，296→297；基线未改。
