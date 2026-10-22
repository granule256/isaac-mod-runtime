"""`api_deviation.cpp` 那张"与 PC 语义的偏离"表的契约门禁。

## 为什么要有这张表、这条门禁

验收基准是三维：① 存在、② 语义、③ 派发时机。其中"② 语义不满足"必须**被标记出来**。
在此之前偏离只写在实现处的注释里 —— 注释不会被任何报告、清单或设备读数带出来，
于是"实现正确"和"实现但有已知偏离"就分不清，批量补齐 API 时更没法逐条收口。

本文件守住四件事：

1. **每条偏离的 id 都必须在 `api_catalog.cpp` 里真实存在**（否则是打错 id 的死账）；
2. **文本必须同时说清"差在哪"和"后果"**（没有后果说明的条目无法用于判断"要不要现在修"）；
3. **条数写死在测试里**：新增/删除都必须人工过一遍（与 `test_api_catalog` 的绑定行数
   是同一套记账方式）；
4. 同一 id 不得重复登记。

（与项目其它源码门禁同一形态：只做受控文本提取，不做 C++ 解析。）
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
DEVIATIONS = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_deviation.cpp"

#: 当前表里的条数。新增或删除偏离条目时**必须**同步这个数字并在上面补一行说明。
#:
#: 首次建立（2026-09-15，地基一期）共 22 条，来源是代码注释里**明确承认**偏离的地方：
#:   `Options.HUDOffset`（1）；`Game:GetSeeds`/`GetVictoryLap` 与 `Seeds:IsCustomRun`/
#:   `GetStartSeed`（4）；`Level:GetCurses`（1）；`Room` 网格与寻路六条（6）；
#:   `Sprite:GetTexel`（1）；`Isaac.GetTime`（1）；`Entity`/`EntityPlayer:GetData`（2）；
#:   `ItemConfig`/`ItemConfig_Item:HasTags`（2）；`EntityPickup:IsShopItem`（1）；
#:   `EntityPlayer:GetPill`/`GetCard`（2）；`EntityPlayer:GetName`（1）。
#:
#: **22 → 21（2026-09-16）**：`Room:GetGridEntity()`（`0x04010007`）的偏离**已解除** ——
#: 网格实体表定位到 `Room + 0x30`（证据见 `runtime_constants.hpp` 的
#: `kRoomGridEntityTableOffset`），现在返回真实句柄；`GridEntity:GetVariant()`/`GetType()`
#: 同批落地。这是**第一条第 ④ 类偏离被消掉**（不是"改成不承认"，而是真的实现出来了）。
#:
#: **21 → 22（2026-09-16，批次 13）**：新增 `GridEntity:GetRNG()`（`0x0E010054`）一条
#: `Partial` —— PC 返回引擎 RNG 的**引用**，我们交回的是**取到那一刻的 16 字节快照**
#: （理由见 `api_deviation.cpp` 那一整段：网格实体随时销毁，而句柄只存实体地址、拿不到网格
#: 下标，做不到"每次访问重新解析并校验"）。同批的 `ItemPool:IsPillIdentified`（`0x05010003`）
#: 与 `RNG:GetSeed`（`0x07010003`）都是真读引擎字段/自身句柄，**不**记偏离。
#:
#: **23 → 19（2026-09-20，批次 098）**：`Room` 网格族的四条偏离**被真正的实现消掉** ——
#: `GetGridWidth`（`0x04010002`）、`GetGridHeight`（`0x04010003`）、`GetGridSize`（`0x04010004`）、
#: `GetGridIndex`（`0x04010005`）。起因是**用户可见**缺陷：`GetGridPath` 恒返 1000
#: （> EID 的 900 阈值）⇒ 地上每一颗药丸、每一张卡片都被判"够不到"、只画问号。
#: 网格尺寸字段（`Room + 0x14`/`+0x18`）、通行代价数组（`Room + 0xE98`）与格坐标换算
#: （`Room::GetGridIndex(Vector2) @ 0x459e3c`）本轮全部定位，证据见 `runtime_constants.hpp`；
#: `GetGridPath`（`0x04010006`）由 `Placeholder` 降为 `Partial`（只剩"越界给 0 而不是越界读"
#: 这一条口径差异）。判据：`runtime/tests/test_lua_room_grid.py`、
#: `tools/room_grid_reachability_probe.py`。
#:
#: **21 → 24（2026-09-21，批次 017）**：补进三条**平台降级** —— `Input.GetMousePosition`（`0x09010007`）、
#: `Input.IsMouseBtnPressed`（`0x09010008`）、`Isaac.ExecuteCommand`（`0x0E01002D`）。
#: 它们的事实此前只写在 `api_catalog.cpp` 的目录注释与实现注释里（原话就是"平台降级 / 平台限制"），
#: 符合本表"只收代码注释里已经明确承认的偏离"的收表口径，却一直没被收进来 —— 于是台账里
#: **一条"平台固有"都没有**，"这条差异还能不能还"这个问题在表里就没有答案。
#: 本批给每条加了"性质"字段（见下文 `EXPECTED_PLATFORM` / `EXPECTED_DEBT` / `EXPECTED_DESIGN`），
#: 三条平台条目是本批唯一的**新增**（其余 21 条只加字段、正文的语义结论与判据一字未改）。
#: 起因与口径见 `dist/change-archive-20260921/017-deviation-nature-split/README.md`。
#:
#: **24 → 51（2026-09-25，批次 128）**：把接口面的**恒值处理器**（"安全桩"：什么都不读、
#: 直接编一个值）成批登记进来，一次 27 条 —— `Input` 三条按钮查询（`0x09010001`/`2`/`3`，
#: 恒 false/false/0）、`Isaac` 四条（`WorldToScreen`/`WorldToRenderPosition` 恒等变换、
#: `GetPersistentGameData`/`GetTrinketIdByName` 恒 0）、`EntityPlayer` 二十条
#: （`0x0E01001F`/`0x0E010032`~`0x0E010036`/`0x0E01003A`/`0x0E01003E`~`0x0E010041`/
#: `0x0E010045`~`0x0E010047`/`0x0E010049`~`0x0E01004D`）。
#:
#: **为什么必须补**：真机读数打印的「风险面」**只认这张台账** —— 而这批处理器此前的事实
#: 只写在实现处注释里、或只进 `tools/lua_api_stub_ledger.json`（那份台账在读数里不露面）
#: ⇒ 模组踩上去的时候现场看不见它。098 的教训（`GetGridPath` 恒返 1000，台账登记过、
#: 但后果那栏写错）说的正是"进这张表"才是"会被看见"。
#:
#: 同批把几处**只钉类型**的判据改成**钉住那个常量本身**（`test_lua_entity_player.py`
#: 的恒 0/恒 false/空表、`test_lua_isaac_table.py` 的恒等变换）—— 类型对不等于语义对。
#: 逐条证据与两处"我们比 PC 严"的登记（`GetPoopSpell` 的参数个数、`HasTrinket` 的可选第二参）
#: 见 `dist/change-archive-20260925/128-constant-value-api-registration/README.md`。
#:
#: **51 → 52（2026-09-26，批次 139）**：新增 `Isaac:GetCostumeIdByPath`（`0x0E01005D`）一条 `Partial`
#: —— 它本身是真实现（遍历 null 道具向量比 `+0x88`），登记的是"**只搜 null 向量**"这一处范围偏离：
#: `costumes2.xml` 里 `passive/active/familiar/trinket` 型的条目把路径挂在收藏品/饰品条目上，
#: 而 PC 会不会也搜那几条向量在 Switch 镜像里取证不到（那半边在 exe 的绑定层）。
#: 性质归 `platform`（见下面 `EXPECTED_PLATFORM` 的说明）。
#:
#: **52 → 53（2026-09-26，批次 140）**：新增 `Game:GetPlayer`（`0x0201000C`）一条 `Partial` ——
#: 它按 `Game.md:338`（`.alldlc`）正文实现（越界/负数 ⇒ 夹到最后一个玩家），登记的是
#: "与 `Isaac.GetPlayer` 的越界口径不一致"（同页 `:340` 说两者是同一个函数，而后者给 nil，
#: 又被两处门禁钉住 ⇒ 本轮有意不动）。归 `design`（见下）。
#: **53 → 55（2026-09-26，批次 141）**：新增 `EntityPlayer:AddNullCostume`（`0x0E01005B`）与
#: `EntityPlayer:TryRemoveNullCostume`（`0x0E01005C`）两条 `Partial` —— 它们本身是真实现
#: （引擎方法数据行），登记的是我们**主动加的一道参数校验**：编号无效（负数/越界/空槽）时
#: **不往引擎里调**。由来是真机崩溃（跳舞模组把 `GetCostumeIdByPath` 查不到的 `-1` 直接喂进来
#: ⇒ 引擎 `AddCostume(nullptr)` 解引用空指针）。归 `design`（见下）。
#:
#: **55 → 50（2026-09-28，批次 177）**：**还清 5 条、条目删除**（这是第一次"往下降"）——
#: 审查第 3 遍（`tools/lua_api_engine_reuse_scan.py` 的 `stub+engine` 档）查出这 5 条
#: "引擎里有同名成员函数、我们却恒返回假值"，于是从"手写假桩"改成**引擎方法数据行**：
#: `EntityPlayer:GetPill`（`0x0E010030`）/ `GetCard`（`0x0E010031`）/
#: `GetZodiacEffect`（`0x0E010040`）/ `HasPlayerForm`（`0x0E01004B`）/
#: `CanPickRedHearts`（`0x0E01004C`）。引擎侧地址与签名见 `runtime_constants.hpp` 里那五条常量，
#: "旧假桩真的删了"由 `runtime/tests/test_id_argument_policy.py` 钉（数据行在 + 处理器表里不在）。
#: ★ 口径提醒：这五条**新实现**还没上真机验收 ⇒ 只是"桩不再是假值"，不是"值已验真"。
#:
#: **50 → 49（2026-09-28，批次 184）**：`0x0E010042`（`EntityPlayer:GetGlyphOfBalanceDrop`）
#: 的条目删除 —— 它原来是 `Placeholder`（恒 0），现在走 `EngineCallShape::Ref2U32Pair` 数据行
#: 真调引擎 `0x2FE574`（理由与口径见 `runtime_constants.hpp` 里那条常量）。
#: ★ 这一条**没有 PC 契约可对齐**（Repentogon 才有的 API、`tools/pc_contract_docs/EntityPlayer.md`
#: 里查不到），所以形状是照**唯一消费者 EID 的调用方式**定的（`features/eid_repentogon.lua:265`）。
#: ★ **43 → 43 里的一次"大还账"（2026-09-29，批次 195）**：**还清 6 条、改档 4 条**
#: （总数 49 → 43，这是第二次"往下降"）——
#:   ① **删除 6 条**（都能还、都还上了）：
#:      `Game:GetSeeds`（`0x02010008`）/ `Game:GetVictoryLap`（`0x02010009`）/
#:      `Seeds:IsCustomRun`（`0x0F010001`）/ `Seeds:GetStartSeed`（`0x0F010002`）——
#:      四条字段偏移指令级定位（`Game+0x26FD50`、`Seeds` 内嵌在 `Game+0x25D40`、`+0x25D44`、`+0x25D40` 那一字节）；
#:      `EntityPlayer:HasGoldenBomb`（`0x0E01004A`）—— 改成字段数据行（`+0x16D9`，取值锚点
#:      `AddGoldenBomb`/`RemoveGoldenBomb`）；`EntityPlayer:HasTrinket`（`0x0E010049`）——
#:      改成一次引擎调用 `Entity_Player::HasTrinket @ 0x28D3B8`（引擎自己就实现了 PC 的两种口径，
#:      并在比较前 `and #0x7fff` ⇒ 旧实现"金色饰品答 false"随之消失）。
#:   ② **改档 4 条**（`debt` → `design`，条数不变）：四条 `Get*RNG`
#:      （`0x0E010033`~`0x0E010036`）从"**恒 nil** 的占位"改成**真读数**
#:      （`Entity_Player + 0x1BB0/0x1BC8/0x1BE0/0x1BF8` 四张 `vector<RNG>`，索引即枚举 id），
#:      残留的只有"交回的是快照而非引擎引用"这一条**我们主动选的**口径差异
#:      （与 `GridEntity:GetRNG` 的 `0x0E010054` 同例）⇒ 性质是 `design`。
#: 逐条证据见 `analysis/api-restore-game/spec.json`、`analysis/api-restore-rng/spec.json`、
#: `analysis/api-restore-entityplayer-b/spec.json`；判据换成消费者视角的
#: `runtime/tests/test_lua_entity_rng_and_fields.py`。
#: ⚠️ 与批次 177 同一句口径提醒：这几条**新实现还没上真机验收** —— 只是"不再是假值"。
#: **43 → 33（2026-09-29，批次 195）**：本批**还清 10 条**并把 3 条**改档**，逐条如下 ——
#:   * 删除 10 条（全部是 `debt`：登记理由都是"字段/偏移还没定位 ⇒ 能还"）：
#:     `0x0E01000C`/`0x0E01000D`（`Isaac.WorldToScreen`/`WorldToRenderPosition`，改成真调引擎
#:     `GetRenderPosition(pos, true)`，两条只差"要不要再加 `Room[0x1938] + Game[0x24F9B0]`"）；
#:     `0x0E01001D`/`0x0E01001E`（`HasTags` 两条，tags 位掩码确证在 `Item + 0xC0`（u64/33 位），
#:     口径 = "任一命中"）；`0x09010007`（`Input.GetMousePosition`，两种 `gameCoords` 都按 PC 语义
#:     实现：`false` = 窗口像素、`true` = 世界坐标 = `Isaac.ScreenToWorld(原始触摸读数)`）；
#:     `0x0E01003A`/`0x0E01003E`/`0x0E01003F`/`0x0E010041`/`0x0E010045`
#:     （`EntityPlayer` 组 A 的五条字段：`+0x16BC`/`+0x269C`/`+0x26A0`/`+0x2730`/`+0x1C54`）。
#:   * 改档 3 条（`debt` → `platform`）：`0x09010001`/`0x09010002`/`0x09010003`
#:     （`Input` 的三条按钮查询）—— **手柄那半接上了**（`KAGE::Input::ManagerBase` 的
#:     `0x4F9504`/`0x4F9648`/`0x4F97B0`，游戏自己在用），而**键盘那半没有真值来源**
#:     （Switch 引擎里确实没有键盘设备，已取证"没有"）；键盘码一律答 false/0.0，**不透传**
#:     （引擎按 `&31` 取位，透传会让 `KEY_SPACE` 撞上"方向左"）。
#:   ⇒ 33 = 20 `debt` + 9 `design` + 4 `platform`。
#: **33 → 32（2026-09-29，批次 195 同批）**：再还一条 —— `0x03010003`（`Level:GetCurses`）原来是
#: "只返回 `Level+0x0C` 的原始位、②③两步未定位"（`debt`），现在按引擎 `0x3D57CC` 的三步合成
#: 实现（`raw | permanent & ~banned`）。
#:   ⇒ 32 = 19 `debt` + 9 `design` + 4 `platform`。
#: **32 → 31（2026-09-29，批次 201）**：再还一条 —— `0x0E010029`（`EntityPickup:IsShopItem`）
#: 原来登记的是「'商店商品'的判据没有证据（只有 `ShopItemId` 这个候选字段）⇒ 恒 false」（`debt`），
#: 现在判据确证 = `Price != 0`（`Entity_Pickup + 0x564`，三条指令级互证 + isaacscript `PickupPrice`
#: 文档），实现在 `isaac_api.cpp` 的 `EntityPickupIsShopItem`。
#:   ⇒ 31 = 18 `debt` + 9 `design` + 4 `platform`。
#: **31 → 33（2026-09-29，批次 207）**：MCM 前置 API 带出**两条新的 `debt`**（不是改档，是新增）：
#:   * `0x0E010065`（`Isaac:GetEntityTypeByName`）—— 我们查的是构建期生成的 `entities2.xml` 静态
#:     快照，模组自己随包带的实体查不到（PC 查的是运行期合并后的表）；底座可定位 ⇒ `debt`；
#:   * `0x11010002`（`HUD:SetVisible`）—— 写的是 `HUD + 0xC53FA`，而全镜像里那一格
#:     **既没有写者、也没有初始化**（只有 `HUD::Render` 读它一次）⇒ `IsVisible()` 报真值没问题，
#:     但"开局那一刻是什么"不受保证；真机读一次就能销账 ⇒ `debt`。
#:   两条性质都是 `debt`（能还）⇒ 31 + 2 = 33 = 20 `debt` + 9 `design` + 4 `platform`。
#: **33 → 36（2026-09-30，批次 214）**：补齐两个 MCM 变体缺的 API 时带出**三条新的登记**（都是新增条目，
#: 不是改档）——这批开的几条 API 里有三条"实现方式与 PC 不同"，按收表口径必须登记：
#:   * `0x0F010005` / `0x0F010006`（`Seeds:AddSeedEffect` / `RemoveSeedEffect`）= `platform` ——
#:     引擎里唯一的增删入口吃**名字字符串**，而"枚举 → 名字"的唯一函数是非静态成员、拿不到实例，
#:     镜像里也没有那批名字串 ⇒ 继续投入也消不掉（取证见 `api_deviation.cpp` 那两条正文）；
#:   * `0x0D010015`（`Sprite:GetDefaultAnimationName`）= `design` —— 引擎里没有"默认动画名"这个字段，
#:     我们按"动画表第一条"回答（对唯一消费者中文版 MCM 等价，它只判非空）⇒ 主动选的口径。
#:   ⇒ 33 + 3 = 36 = 20 `debt` + 10 `design` + 6 `platform`。
#: ★ 批次 240（2026-09-30）：36 → **37** —— 加了 `Isaac.GetCardIdByName` 那条**有意偏离**
#: （PC 匹配 `pocketitems.xml` 的 `hud` 属性，而本体那份 XML 里 `hud` 有 0 处 ⇒ 我们改用 `name`）。
#: ★ 批次 269（2026-10-02）：37 → **39** —— `blocked_decision` 桶的渲染两条
#: （`0x04010024` `Room:GetRenderMode` / `0x04010025` `Room:GetRenderSurfaceTopLeft`）。
#: 两条都是 `Placeholder`：PC 侧各是一条 6 字节访问器（`Room+0x12BC` / `Room+0x11FC`），
#: 而 **Switch 侧的对应字段没有取证到**（取证过程与排除的假阳性逐条写在 `api_deviation.cpp` 里），
#: 所以给保守值而不是编一个像真值的常量。★ 为什么不干脆不实现：这两条的调用点都在模组回调体里，
#: 方法缺失会报 `attempt to call a nil value` ⇒ **整条回调被摘掉**，而 PC 上它们根本不会失败。
#: ★ 批次 271（2026-10-02）：39 → **40** —— `EntityPlayer:UseActiveItem`（`0x0E010094`）
#: 的两种重载：NS 引擎只有基础四参那条入口，扩展七参形的四个布尔在那儿没位置 ⇒
#: 我们按"名字一一对应"折算进 `UseFlag`（`USE_NOANIM`/`USE_NOCOSTUME`/`USE_ALLOWNONMAIN`），
#: 而 `KeepActiveItem` 没有对应位 ⇒ 表达不了。按 `Partial` 登记（性质 `design`）。
#: ★ 批次 316（2026-10-03）：40 → **41** —— `Entity:GetDropRNG`（`0x0E0100DB`）的快照语义
#: （与 `GridEntity:GetRNG` 同例，性质 `design` ⇒ 同批 `EXPECTED_DESIGN` 也 +1）。
#: ★ 批次 347（2026-10-04）：41 → **42**（`0x04010038` `RoomConfigSpawn:PickEntry`，性质 `design`）——
#:   `RoomConfig::Entry` 在 Switch 上是 12 字节（`Variant`/`SubType` 是 i16，PC 是 `int`）、
#:   `RoomConfigSpawn.X`/`.Y` 本批不做（只有 candidate 级证据）、`Spawns` 我们是普通表
#:   （PC 是带 `__len` 的 ArrayProxy）⇒ 三处**形态/宽度**差异合成一条（语义逐值相同）。
#: ★ 批次 388（2026-10-07）：42 → **46** —— `TemporaryEffects`（`EntityPlayer:GetEffects()` 的返回值）一族：
#:   ① **删** 1 条：`0x0E010047`（`EntityPlayer:GetEffects`）原来是"恒返回空表（无方法）⇒ 模组
#:      `GetEffects():HasCollectibleEffect(id)` 抛错摘回调"（性质 `debt`）—— 现在返回带 17 个方法的
#:      对象，**已还清**；
#:   ② **加** 5 条方法级占位（`0x0E010106`..`0x0E01010A`：`ClearEffects`、三个返回对象却给 `nil` 的
#:      `Get*Effect`、`GetEffectsList` 给空表），全是 `debt`。
#:   ⇒ 42 - 1 + 5 = 46。
#: ★ 批次 404（2026-10-07）：46 → **45** —— `Isaac.GetTrinketIdByName`（`0x0E01000F`，性质 `debt`）
#:   的偏离**已还清**：本批补了本体饰品静态表（`isaac_name_source/trinkets.txt`）＋同族运行时追加层
#:   （模组 `content/items.xml` 的 `<trinket>`），`Isaac.GetTrinketIdByName("Lucky Toe") == 42`
#:   （`Isaac.md:467` 的例子逐值一致）。按台账口径（"还清之后应当把这条从台账里删掉"）**删除**该条。
#:   ⇒ 46 - 1 = 45。判据：`runtime/tests/test_lua_batch404_mod_content_names.py`。
#: 2026-10-10：GetData实际寿命/Remove清理/D2退役已恢复，旧全文存dist/entity-lifecycle-static-20261010。
EXPECTED_DEVIATIONS = 24

#: **按性质分组的条数**（2026-09-21，批次 017 建立；口径逐字写在 `api_deviation.cpp` 文件头）：
#:
#:   * `platform`（平台固有）= PC 上有对应物、Switch 平台侧**没有可用底座或语义无法映射**，
#:     且**已经取证过"没有"** ⇒ 继续做工作也消不掉；
#:   * `debt`（我们的欠账）= 底座**存在或可定位**，只是还没定位 / 没实现 / 实现得偏保守 ⇒ **能还**；
#:   * `design`（主动保留的口径差异）= 两侧都做得到，但我们**有意**选了别的口径、且台账写明不打算改
#:     （复刻 PC 等于复刻它的未定义行为；或照着做会把引擎内部指针交给模组）⇒ 不改。
#:
#: **这三个数字都只能降不能升**（消掉一条偏离就把它改小，并在上面补一行说明为什么 —— 与
#: `EXPECTED_DEVIATIONS`、`EXPECTED_JUDGEMENT_GAPS` 同一套记账方式）。新增偏离时**必须**同时
#: 想清楚它属于哪一类：想不清楚就说明这条偏离还没调查到能判断"能不能还"的程度，别急着登记。
#:
#: **platform 3 → 2、debt 19 → 20（2026-09-25，批次 121）**：`Isaac.ExecuteCommand`（`0x0E01002D`）
#: 那条"平台固有"的**前提被推翻了** —— 当时记为"Switch 没有控制台"，而事实是**控制台类与全部
#: 命令实现都在镜像里**（引擎只是从不实例化它：构造/`Init`/`Update`/`Render`/`ShowKeyboard`
#: 的调用边全是 0）。运行时现在自己建一个 `Console` 实例并调它的 `RunCommand`，返回值也照 PC 契约
#: 给字符串（`Isaac.md:106`）。⇒ 它从"平台固有"变成"**能还的欠账**"：残留的两条限制
#: （命令长度上限 127 字节、没有玩家时拒绝执行）都是我们实现侧的。
#: 总数 `EXPECTED_DEVIATIONS` 不变（只是改了性质），判据：`runtime/tests/test_console_bridge.py`
#: 与 `dist/change-archive-20260925/121-console-bridge/README.md`。
#:
#: **debt 20 → 47（2026-09-25，批次 128）**：新登记的那 27 条**全是 `debt`** —— 它们的共同点是
#: "底座在引擎里（或可从存档/资源里取到），只是还没定位"，与 `platform` 有本质区别
#: （那一类是平台上真的没有东西可用：鼠标、系统时钟那类）。`platform` 与 `design` 两条不动。
#: ⚠️ 这条数字现在很大（47/51）不是坏消息：它说明"风险面"以前**大面积不可见**，而不是新出现了
#: 47 处缺陷 —— 每一条的修法都写在正文的"判据"与理由里，可以逐条还。
#:
#: **platform 2 → 3、总数 51 → 52（2026-09-26，批次 139）**：`Isaac:GetCostumeIdByPath` 的
#: "只搜 null 向量"归 `platform` —— 缺的那半边（PC 会不会也搜收藏品/饰品向量）**只能从 PC 的 exe
#: 绑定层取证**，而那份绑定层不在 Switch 镜像里（已取证"镜像里查不到"）⇒ 继续投入也消不掉，
#: 与 `debt` 有本质区别。理由与判据逐字写在 `api_deviation.cpp` 那一条里。
#:
#: **platform 3 → 1、debt 41 → 43（2026-09-28，批次 192）**：两条**改档**，不是新增、也不是删除 ——
#: `Input.GetMousePosition`（`0x09010007`）与 `Input.IsMouseBtnPressed`（`0x09010008`）原登记为
#: `platform`（"平台固有、再怎么继续做工作也消不掉"），**已被用户推翻**：
#: Switch 的**触摸屏**就是等价指针源，`hid` 的共享内存在游戏进程里本来就映射着 ⇒ 缺的不是权限、
#: 是没做 ⇒ 这正是 `debt` 的定义（**能还**）。本批把指针源接上了触摸屏；**坐标换算**与
#: **多键位区分**是这两条欠账里剩下的部分，逐条写在 `api_deviation.cpp` 的"理由"与"偏离后果"里。
#: ⚠️ 这条改动**只改性质、不改任何语义结论**；"原判据作废"的来历见 `docs/改动日志-20260928.md` §190。
#: **1 → 4（2026-09-29，批次 195）**：`Input` 的三条按钮查询（`0x09010001`~`0x09010003`）
#: 从 `debt` 改档进来 —— 原前提"引擎里没有按按键号查询的入口"已被取证推翻（入口在
#: `KAGE::Input::ManagerBase`，游戏自己就在用），但那三条**残留的键盘那半**在 Switch 上
#: 没有真值来源（引擎里确实没有键盘设备）⇒ 属"继续做工作也消不掉"。手柄那半已接上。
#: （原有的 1 条 = `0x0E01005D`，`Isaac.GetCostumeIdByPath` 只搜 null 向量。）
#: **4 → 6（2026-09-30，批次 214）**：新增两条 `platform` —— `Seeds:AddSeedEffect`（`0x0F010005`）
#: 与 `Seeds:RemoveSeedEffect`（`0x0F010006`）。它们不是"还没做"，是**引擎侧没有可信路径**：
#: 增删要"枚举 → 名字字符串"，而那个转换函数是 `Menu_SpecialSeed` 的非静态成员（拿不到实例），
#: 镜像里也搜不到那批名字串 ⇒ 继续投入也消不掉（详见 `api_deviation.cpp` 正文）。
EXPECTED_PLATFORM = 6
#: **debt 47 → 42（2026-09-28，批次 177）**：**还清 5 条**（这是第一次往下降，性质没变、条数减了）——
#: `EntityPlayer:GetPill` / `GetCard` / `GetZodiacEffect` / `HasPlayerForm` / `CanPickRedHearts`
#: 原本登记的都是"引擎里有现成成员函数、我们只是还没接上"（正是 `debt` 的定义：**能还**），
#: 现在接上了（改成引擎方法数据行）⇒ 条目删除。逐条证据见 `runtime_constants.hpp` 里那五条常量。
#:
#: **42 → 41（2026-09-28，批次 184）**：同上再还一条 ——
#: `EntityPlayer:GetGlyphOfBalanceDrop`（`0x0E010042`）原本登记的理由也是"能还"（派生值在引擎里），
#: 现在接上了（`Ref2U32Pair` 数据行，引擎 `0x2FE574`）。
#:
#: **41 → 43（2026-09-28，批次 192）**：由 `platform` **改档**进来两条（`0x09010007` / `0x09010008`，
#: 见上面 `EXPECTED_PLATFORM` 的说明）—— 总数不变，只是这两条从"消不掉"挪到"能还"。
#: **43 → 33（2026-09-29，批次 195）**：上一条说明里"删除的 6 条"全部来自 `debt`
#: （它们的登记理由都是"偏移/取法还没定位 ⇒ 能还"），还上之后就销账 ⇒ `debt` 从 43 降到 37；
#: 另有 4 条 `Get*RNG` 从 `debt` **改档**到 `design`（快照口径是我们主动选的）⇒ 37 - 4 = 33。
#: **33 → 20（2026-09-29，批次 195）**：上一条 `EXPECTED_DEVIATIONS` 的说明里那"删除 10 条 +
#: 改档 3 条"全部来自 `debt`（登记理由都是"偏移/取法还没定位 ⇒ 能还"），还上之后就销账 ⇒
#: 33 - 10 - 3 = 20；同批再还一条 `0x03010003`（见 `EXPECTED_DEVIATIONS`）⇒ 20 - 1 = 19。
#: **19 → 18（2026-09-29，批次 201）**：`0x0E010029`（`EntityPickup:IsShopItem`）还清销账
#: （理由见 `EXPECTED_DEVIATIONS` 的说明）⇒ 19 - 1 = 18。
#: **18 → 20（2026-09-29，批次 207）**：MCM 前置 API 带出两条新的 `debt`
#: （`0x0E010065` / `0x11010002`，理由见 `EXPECTED_DEVIATIONS` 的说明）⇒ 18 + 2 = 20。
#: **20 → 22（2026-10-02，批次 269）**：上面那两条 `Placeholder` 的登记理由都是
#: "字段确实在引擎里、只是没定位 ⇒ 取证到就能换成真读" ⇒ 属 `debt`（能还），不是 `design`/`platform`。
#: ★ 批次 388（2026-10-07）：22 → **26** —— 删 1 条 `debt`（`0x0E010047`，已还清）+ 加 5 条 `debt`
#:   （`TemporaryEffects` 的 5 条占位：底座都在，缺的是"那个 bool 的语义"或"返回对象那一族的形状"）⇒ 26。
#: ★ 批次 404（2026-10-07）：26 → **25** —— 删 1 条 `debt`（`0x0E01000F` `Isaac.GetTrinketIdByName`，
#:   已还清：本体静态表 + 模组追加层都落地了）⇒ 25。
EXPECTED_DEBT = 11
#: **design 2 → 3（2026-09-26，批次 140）**：`Game:GetPlayer` 与 `Isaac.GetPlayer` 的**越界口径不一致**
#: 归 `design`（主动保留）—— 越界夹到"最后一个"是 PC 正文（不是我们的取舍），不一致的另一半在
#: `Isaac.GetPlayer`（nil，被 `test_lua_entity_player.py:731/736` 与 `test_lua_isaac_table.py:480`
#: 钉住）；改它要动测试，按项目纪律先问用户 ⇒ 本轮**有意**不动，留作下一批的独立决定。
#:
#: **design 3 → 5（2026-09-26，批次 141）**：`AddNullCostume` / `TryRemoveNullCostume` 的
#: **参数校验**归 `design`：两侧都做得到，但我们**有意不复刻**"把无效编号原样交给引擎"这条
#: 未定义行为（复刻的代价是模组一传无效编号就把玩家的游戏崩掉 —— 真机已实测）。
#: 挡下次数与最后一次编号都进读数（`g_IsaacEngineRowRejectGuard` 等），不是无声吞掉。
#: **design 5 → 9（2026-09-29，批次 195）**：四条 `Get*RNG`（`0x0E010033`~`0x0E010036`）
#: 由 `debt` **改档**进来 —— 它们现在真的读引擎里那四张 `vector<RNG>`，残留的差异只有
#: "交回的是取到那一刻的 16 字节快照，而不是引擎里那颗 RNG 的活引用"（与 `GridEntity:GetRNG`
#: 的 `0x0E010054` 同一条取舍：让模组长期持有引擎对象内部成员的指针 = 给模组开一个写已释放
#: 内存的口子）⇒ 属"两侧都做得到、我们有意不这么做"的 `design`，不是欠账。
#: **9 → 10（2026-09-30，批次 214）**：新增一条 `design` —— `Sprite:GetDefaultAnimationName`
#: （`0x0D010015`）。引擎里**没有**"默认动画名"这个字段/访问器，我们按"动画表里第一条"回答；
#: 这是两侧都做得到、但替代口径由我们**主动选**的情形（REPENTOGON 的原口径在这台机器的引擎里
#: 不存在）⇒ 属 `design`，不是欠账。对唯一消费者（中文版 MCM 只判返回值非空）语义等价。
#: ★ 批次 240（2026-09-30）：10 → **11** —— `Isaac.GetCardIdByName` 那条（见 `EXPECTED_DEVIATIONS`）。
#: ★ 批次 316（2026-10-03）：12 → **13** —— `Entity:GetDropRNG`（`0x0E0100DB`）的**快照语义**，
#: 与 `GridEntity:GetRNG`（`0x0E010054`）及四条 `Get*RNG` **同一条取舍**（交回 16 字节快照而不是
#: 引擎里那颗 RNG 的活引用；理由同样是"不让模组长期持有引擎对象内部成员的指针"）⇒ 属 `design`。
#: ★ 批次 347（2026-10-04）：13 → **14**（同上那条：三处都是**能做到但有意不做**的选择）。
EXPECTED_DESIGN = 7

#: "判据：暂无（…）"的条数 —— **欠账**，只能降不能升。
#:
#: 2026-09-20（批次 099）建立这条记账方式时是 **0**：当天给 19 条全部补上了可执行判据
#: （每条点名一个仓库里真实存在的测试文件，并写明它钉住了什么、**哪一半没钉**）。
#: 以后新增偏离又一时给不出判据的，可以写"判据：暂无（理由…）"，但必须把这个数字 +1
#: 并在这段注释里说明 —— 让欠账有数字、有出处，而不是靠记性。
EXPECTED_JUDGEMENT_GAPS = 0

#: 写了「`PC 形状：` / `我们形状：`」两栏的条目数（批次 161 起）。新增一条就 +1，并在这里补一行说明。
#:
#: 2026-09-27（批次 161）建立时是 **9** —— 就是正文里写着「恒 nil」的全部条目：
#: `EntityPlayer:GetData`（`0x0E010017`）、`Entity:GetData`（`0x0E010025`）、
#: `EntityPlayer:GetName`（`0x0E010048`）、`EntityPlayer:GetOtherTwin`（`0x0E01001F`）、
#: `EntityPlayer:GetMainTwin`（`0x0E010032`）、`EntityPlayer:GetCollectibleRNG`（`0x0E010033`）、
#: `GetTrinketRNG`（`0x0E010034`）、`GetCardRNG`（`0x0E010035`）、`GetPillRNG`（`0x0E010036`）。
#: 其中**六条**是"PC 给对象、我们给 nil"（后果里必须点名"链式调用会抛错"），另外三条两侧形状一致。
#: 为什么要这个数字：漏写一栏不会红在别处 —— 它只会在模组链式调用抛错、整条回调被摘掉时才现身。
EXPECTED_SHAPE_ENTRIES = 0

#: 允许的偏离种类（与 `ApiDeviationKind` 一致）。
KINDS = {"Partial", "Placeholder", "NotInEngine"}


def catalog_ids(text: str) -> set[int]:
    """`api_catalog.cpp` 里所有条目的完整 id。

    只算 `MakeId(...)` 调用 —— 目录里每条 API 都这么写（这是该文件的既有约定，
    `test_api_catalog` 的"家族绑定 id 必须与 Catalog 一致"那条也依赖同一形状）。
    """
    ids = set()
    domain_values = {
        "Global": 0, "Mod": 1, "Game": 2, "Level": 3, "Room": 4, "ItemPool": 5,
        "Music": 6, "Rng": 7, "Persistence": 8, "Input": 9, "Diagnostic": 10,
        "Font": 11, "Vector": 12, "Sprite": 13, "Isaac": 14, "Seed": 15,
        # 批次 207（2026-09-29）：`Hud`（域 17，`Game:GetHUD()` 的返回值）。真值源是
        # `runtime/src/interfaces/lua/api_descriptor.hpp` 的 `ApiDomain`；漏了它会让
        # `0x11010002`（`HUD:SetVisible`）被当成"catalog 里不存在的 id"。
        "Hud": 17,
    }
    for match in re.finditer(
        r"MakeId\(ApiDomain::(\w+),\s*(\d+),\s*(0x[0-9A-Fa-f]+)\)", text
    ):
        domain, group, sequence = match.groups()
        if domain not in domain_values:
            continue
        ids.add((domain_values[domain] << 24) | (int(group) << 16) | int(sequence, 16))
    return ids


def deviation_entries(text: str) -> list[tuple[int, str, str]]:
    """从 `api_deviation.cpp` 提取 `(id, kind, 文本)`。

    解析口径**只有一份**，在 `tools/api_deviation_ledger.py`（读数的"风险面"那一段也用它，
    两边不许各写一套正则）。这里保留这个函数名只是为了不动既有调用方。
    """
    from tools.api_deviation_ledger import load_entries

    return [(entry.identifier, entry.kind, entry.text) for entry in load_entries(DEVIATIONS)]


class ApiDeviationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CATALOG.read_text(encoding="utf-8")
        cls.deviations = DEVIATIONS.read_text(encoding="utf-8")

    def test_every_deviation_points_at_a_real_catalog_entry(self):
        """id 必须在 catalog 里真实存在 —— 打错 id 就等于这条偏离没有任何人会看到。"""
        known = catalog_ids(self.catalog)
        self.assertGreater(len(known), 150, "catalog id 解析结果太少，门禁失去意义")
        unknown = [
            hex(identifier)
            for identifier, _, _ in deviation_entries(self.deviations)
            if identifier not in known
        ]
        self.assertEqual(unknown, [], f"偏离表里出现了 catalog 中不存在的 id：{unknown}")

    def test_kinds_are_known_values(self):
        kinds = {kind for _, kind, _ in deviation_entries(self.deviations)}
        self.assertTrue(kinds, "一条偏离都没解析到 —— 门禁失去意义")
        self.assertTrue(kinds <= KINDS, f"出现了未知的偏离种类：{sorted(kinds - KINDS)}")

    def test_each_entry_states_the_consequence(self):
        """每条都必须有**明确写出来的**"偏离后果：…"。

        ★ 2026-09-20（批次 099）为什么加强：原来的判据是"文本里出现'后果'/'只'/'不'之一"，
        而 `EntityPlayer:GetName()` 那条一个字都没写后果，却因为正文里有"EID **只**做字符串拼接"
        而**通过了** —— 关键词是顺带出现的，判据等于没判。改成要求台账里那个**固定标记**
        （`api_deviation_ledger.CONSEQUENCE_MARKER`）。这类"关键词恰好出现"的假通过，
        与 047 那次"布局表里有这一行就算已实现"是同一族。
        """
        from tools.api_deviation_ledger import CONSEQUENCE_MARKER, load_entries

        entries = load_entries(DEVIATIONS)
        self.assertGreater(len(entries), 10, "一条偏离都没解析到 —— 门禁失去意义")
        missing = [hex(entry.identifier) for entry in entries if not entry.has_consequence]
        self.assertEqual(missing, [],
                         f"这些偏离没有写'{CONSEQUENCE_MARKER}'：{missing}。"
                         "后果必须写清'模组会看到什么'，否则没人能判断要不要现在修。")
        for entry in entries:
            with self.subTest(id=hex(entry.identifier)):
                self.assertGreater(len(entry.consequence), 8,
                                   f"{hex(entry.identifier)} 的'偏离后果'太短，等于没写")
                self.assertNotIn("暂无", entry.consequence,
                                 f"{hex(entry.identifier)} 的后果是'暂无'式占位 —— 那等于没写")

    def test_each_entry_names_an_existing_judgement(self):
        """★ 每条必须给出"判据：<仓库里的测试文件>"，且那个文件真的存在。

        为什么（098 事故的直接教训）：`Room:GetGridPath` 那条偏离**登记过**，但后果那一栏写的是
        "不画路径提示"，真相是"藏掉整条描述" —— 没有判据就没有人会发现写错了。
        所以从现在起，每条偏离都要能回答"**这条偏离靠什么被钉住**"：

        * 判据必须点名至少一个 `tests/**.py`，且该文件**在当前仓库里存在**（改名/删掉会红）；
        * 确实还没有可执行判据的，必须写成"判据：暂无（理由…）"—— 那是**欠账**，
          条数被 `EXPECTED_JUDGEMENT_GAPS` 钉住，**只能降不能升**（与安全桩台账同一套记账方式）。
        """
        from tools.api_deviation_ledger import JUDGEMENT_MARKER, load_entries

        entries = load_entries(DEVIATIONS)
        gaps: list[str] = []
        for entry in entries:
            with self.subTest(id=hex(entry.identifier)):
                if entry.judgement_missing:
                    gaps.append(hex(entry.identifier))
                    continue
                paths = entry.judgement_paths
                self.assertTrue(
                    paths,
                    f"{hex(entry.identifier)} 的'{JUDGEMENT_MARKER}'里没有点名任何 tests/*.py："
                    f"{entry.judgement!r}")
                for relative in paths:
                    self.assertTrue(
                        (ROOT / relative).is_file(),
                        f"{hex(entry.identifier)} 的判据指向不存在的文件：{relative}")
        self.assertEqual(
            len(gaps), EXPECTED_JUDGEMENT_GAPS,
            f"'暂无判据'的偏离条数变了（现在 {len(gaps)} 条：{gaps}）。"
            "要么补上可执行判据，要么在 EXPECTED_JUDGEMENT_GAPS 上面写清为什么又多欠一条。")

    def test_every_entry_states_a_valid_nature(self):
        """★ 每条必须写清**性质**：`platform`（平台固有）/ `debt`（我们的欠账）/ `design`（主动保留）。

        为什么加这条（2026-09-21，批次 017）：台账原来只有"偏离长什么样"（`kind`），读者分不清一条
        偏离是**这台机器上永远消不掉**的，还是**我们还没做到**的 —— 前者登记完就该停止投入，后者
        应当排进待办、还清后把条目删掉。没有这一栏时，两种情况都会办错。

        ★ 口径（逐字写在 `api_deviation.cpp` 文件头，这里只钉"写了没有、取值合不合法"）：
          * `platform` = PC 上有对应物、Switch 平台侧**没有可用底座或语义无法映射**（鼠标、控制台），
            且**已经取证过"没有"**；
          * `debt` = 底座**存在或可定位**，只是还没定位 / 没实现 / 实现得偏保守 ⇒ **能还**；
          * `design` = 两侧都做得到，但我们**有意**选了别的口径且写明不打算改（复刻 PC 的未定义行为、
            或把引擎内部指针交给模组）⇒ 不改。

        "不许有未归类的条目"也在这里判：缺标记（空串）与取值写错都会红。
        """
        from tools.api_deviation_ledger import NATURE_MARKER, NATURES, load_entries

        entries = load_entries(DEVIATIONS)
        self.assertGreater(len(entries), 10, "一条偏离都没解析到 —— 门禁失去意义")
        unclassified = [hex(entry.identifier) for entry in entries if not entry.is_classified]
        self.assertEqual(
            unclassified, [],
            f"这些偏离没有合法的'{NATURE_MARKER}'取值（只能是 {list(NATURES)}）：{unclassified}。"
            "口径见 api_deviation.cpp 文件头；想不清楚属于哪一类，说明这条偏离还没调查到能判断"
            "'能不能还'的程度。")
        # 取值必须与括号里那个中文名对得上（防止只改取值、把名字留在原文里）。
        for entry in entries:
            with self.subTest(id=hex(entry.identifier)):
                self.assertTrue(
                    entry.nature_label,
                    f"{hex(entry.identifier)} 的性质取值 {entry.nature!r} 不在 {list(NATURES)} 里")
                self.assertIn(
                    f"{NATURE_MARKER}{entry.nature}（{entry.nature_label}）", entry.text,
                    f"{hex(entry.identifier)} 的性质标记形状不对：应当是"
                    f"'{NATURE_MARKER}{entry.nature}（{entry.nature_label}）——理由：…'")

    def test_each_entry_states_the_nature_reason(self):
        """★ 每条的性质后面必须跟**一行理由**：读者不看别处就明白为什么这么归类。

        与"偏离后果"同一条纪律（098 的教训）：光有分类标签没有理由，下一个人无法复核 ——
        他只能重新做一遍调查，或者干脆相信这个标签。
        """
        from tools.api_deviation_ledger import NATURE_REASON_MARKER, load_entries

        entries = load_entries(DEVIATIONS)
        missing = [hex(entry.identifier) for entry in entries if not entry.nature_reason]
        self.assertEqual(
            missing, [],
            f"这些偏离没有写'{NATURE_REASON_MARKER}'后面那行理由：{missing}")
        for entry in entries:
            with self.subTest(id=hex(entry.identifier)):
                self.assertGreater(
                    len(entry.nature_reason), 8,
                    f"{hex(entry.identifier)} 的性质理由太短，等于没写：{entry.nature_reason!r}")
                self.assertNotIn(
                    "暂无", entry.nature_reason,
                    f"{hex(entry.identifier)} 的性质理由是'暂无'式占位 —— 那等于没写")

    def test_nature_counts_are_pinned(self):
        """★ 三个性质的**条数**写死 —— 只能降不能升（照 `EXPECTED_*` 那套记账方式）。

        为什么连条数也要钉：`platform` 与 `debt` 的比值就是"这台机器上还有多少是**能还**的"，
        是排期的依据。数字松了就会出现"悄悄把一条欠账标成平台固有、于是没人再管它"这种漂移。
        消掉一条偏离（真的实现出来了）⇒ 把数字改小并补一行说明；新增 ⇒ 说明它为何属于这一类。
        """
        from tools.api_deviation_ledger import load_entries

        entries = load_entries(DEVIATIONS)
        counts: dict[str, int] = {}
        for entry in entries:
            counts[entry.nature] = counts.get(entry.nature, 0) + 1
        expected = {
            "platform": EXPECTED_PLATFORM,
            "debt": EXPECTED_DEBT,
            "design": EXPECTED_DESIGN,
        }
        self.assertEqual(
            counts, expected,
            f"按性质分组的条数变了（现在 {counts}，门禁钉的是 {expected}）。"
            "消掉一条欠账/改判一条性质时，请同步上面三个 EXPECTED_* 并在注释里写清为什么。")
        self.assertEqual(
            sum(expected.values()), EXPECTED_DEVIATIONS,
            "三个性质的条数之和必须等于 EXPECTED_DEVIATIONS —— 有条目没被算进任何一组")

    def test_no_duplicate_ids(self):
        identifiers = [identifier for identifier, _, _ in deviation_entries(self.deviations)]
        duplicates = sorted({value for value in identifiers if identifiers.count(value) > 1})
        self.assertEqual(duplicates, [], f"同一 id 被登记了多次：{[hex(v) for v in duplicates]}")

    def test_the_ledger_count_is_up_to_date(self):
        """条数写死 —— 新增/删除偏离时强制人工过一遍（与绑定行数同一套记账方式）。"""
        self.assertEqual(
            len(deviation_entries(self.deviations)),
            EXPECTED_DEVIATIONS,
            "偏离表的条数变了。请确认每条都写清了'差在哪 + 为什么 + 后果'，"
            "再同步 EXPECTED_DEVIATIONS 并在上面补一行说明。",
        )


class PcContractCitationTests(unittest.TestCase):
    """★ 每条偏离都必须引用 **PC 文档的原文**（批次 111，用户的直接要求）。

    ## 为什么加这条门禁

    2026-09-20 的 107→109→110 三批都在改**同一个** API（`Input.IsActionTriggered`），
    根因是 107 那次**凭推断断言了 PC 的语义**（注释里写着"PC 是同一帧内问多少次都答 true"，
    但**没有任何出处**），而不是去读仓库里本来就有的 PC 文档快照。三批的返工就是这个的账单。

    "以后先读文档"不能靠记性 ⇒ 做成**能红的门禁**：每条偏离（我们与 PC 不同的地方，也就是
    最需要契约的地方）都必须写出

        PC 契约：tools/pc_contract_docs/<页>.md:<行号> 「<原文片段>」

    而这条门禁会**回头核对**：那一页存在、那一行存在、而且那个片段**确实出现在那一行里**
    ⇒ 抄错行、抄错页、凭记忆写一句、都过不去。

    文档里**确实没有**这一条时，写 `PC 契约：文档里没有 <说明>` —— 明确写出来也算数
    （不许留空，也不许用"大概是这样"糊过去）。

    ## 契约页**必须待在仓库里**（批次 111 的嵌套门禁抓出来的）

    第一版引用的是 `analysis/isaacdocs-snapshot/docs/` —— 而 `analysis/` 是 **gitignore 的**，
    于是"只复制已跟踪文件再跑一遍"的嵌套套件（`test_game_file_reader_stage10`）里，
    这些页**根本不存在** ⇒ 所有引用当场失效。这与批次 048 撞 `RoomShape` 时是同一个教训：
    **契约源不在仓库里 = 这一类工作对任何其他人都不可做**。
    所以那 13 页被**逐字节**复制进 `tools/pc_contract_docs/`（带 `.gitattributes` 的 `* -text`），
    引用也改指向副本 —— 下面是"字节被改过就红"的钉子（改了要先核对上游、再来改这里）。
    """

    #: 契约页的**字节数**（跨机器/行尾都不会变；`gitattributes` 标了 `-text`）。
    CONTRACT_PAGE_SIZES = {
        "Entity.md": 37788,
        "EntityPickup.md": 6651,
        "EntityPlayer.md": 92938,
        "REPENTOGON_EntityPlayer.md": 88373,
        "Game.md": 28363,
        "GridEntity.md": 8270,
        "Input.md": 5525,
        "Isaac.md": 31975,
        "ItemConfig.md": 5750,
        "CppContainer_Vector_ItemConfigList.md": 1100,
        "ItemConfig_Item.md": 9616,
        "Level.md": 21972,
        "Options.md": 5783,
        #: 批次 347（2026-10-04）：`PickEntry` 那条偏离要引的两页 ——
        #: `RoomConfig_Entry.md`（PC 的类型是 `int`，而引擎里是 i16 ⇒ 符号扩展那条判据）与
        #: `CppContainer_ArrayProxy_RoomConfigSpawns.md`（PC 是 ArrayProxy、有 `__len`）。
        #: 两页都**逐字节**复制自 `analysis/isaacdocs-snapshot/docs/`、**不加 header**（引的是行号）。
        "RoomConfig_Entry.md": 1158,
        "CppContainer_ArrayProxy_RoomConfigSpawns.md": 1184,
        #: 批次 344（2026-10-04）：`PathFinder.md` —— 逐字节 vendor 自
        #: `analysis/isaacdocs-snapshot/docs/PathFinder.md`（**不加 header**：台账引的是行号）。
        "PathFinder.md": 4340,
        "Room.md": 48849,
        "Seeds.md": 7079,
        "Sprite.md": 19065,
    }

    def test_contract_pages_are_tracked_and_unchanged(self):
        for name, size in self.CONTRACT_PAGE_SIZES.items():
            with self.subTest(page=name):
                page = ROOT / "tools" / "pc_contract_docs" / name
                self.assertTrue(page.is_file(), f"缺契约页 {name}")
                self.assertEqual(page.stat().st_size, size,
                                 f"{name} 的字节数变了 —— 契约页被改动过，先核对上游再改这里")

    @classmethod
    def setUpClass(cls):
        cls.entries = deviation_entries(DEVIATIONS.read_text(encoding="utf-8"))

    def test_every_entry_states_the_pc_contract(self):
        marker = "PC 契约："
        missing = [f"0x{identifier:08X}" for identifier, _, text in self.entries
                   if marker not in text]
        self.assertEqual(missing, [],
                         f"这些偏离没有写'{marker}'：{missing}。\n"
                         "先读 `tools/pc_contract_docs/` 里那一页（PC 文档快照的逐字节副本），把原文与行号抄进来；\n"
                         "文档里确实没有这一条就写'PC 契约：文档里没有 …'（也要写明是什么）。")

    def test_citations_really_point_at_the_doc_text(self):
        """★ 关键：**回头核对**引用 —— 页要在、行要在、片段要真的在那一行里。"""
        pattern = re.compile(r'([^\s「」]+?):(\d+)(?:\s*「([^」]*)」)?')
        checked = 0
        for identifier, _, text in self.entries:
            match = re.search(r'PC 契约：(.*?)(?:"|$)', text, re.S)
            self.assertIsNotNone(match, f"0x{identifier:08X} 的'PC 契约：'后面是空的")
            body = match.group(1).strip()
            if body.startswith("文档里没有"):
                self.assertGreater(len(body), len("文档里没有"),
                                   f"0x{identifier:08X} 写了'文档里没有'但没说是什么")
                continue
            parsed = pattern.match(body)
            self.assertIsNotNone(parsed, f"0x{identifier:08X} 的契约引用格式不对：{body!r}")
            path_text, line_text, quote = parsed.groups()
            page = ROOT / path_text
            with self.subTest(entry=f"0x{identifier:08X}"):
                self.assertTrue(page.is_file(), f"{path_text} 不存在")
                lines = page.read_text(encoding="utf-8").splitlines()
                index = int(line_text)
                self.assertLessEqual(index, len(lines), f"{path_text} 没有第 {index} 行")
                line = lines[index - 1]
                if quote:
                    self.assertIn(quote, line,
                                  f"{path_text}:{index} 里没有「{quote}」—— 引用与文档对不上")
                checked += 1
        self.assertGreater(checked, 0, "一条带文档引用的契约都没有？先补起来")

    # ---- 形状两栏（批次 161）：条文在 AGENTS.md，这里是那条的判据 --------------

    def test_nil_returning_entries_state_both_shapes(self):
        """正文写「恒 nil」的条目**必须**写清"PC 给什么形状 / 我们给什么形状"。

        为什么（一次真机事故）：`EntityPlayer:GetMainTwin()` 曾恒 nil，而 PC 文档正文明写
        "其它任何角色 → 该角色自己" ⇒ EID 的 `player:GetMainTwin():GetPlayerType()` 在 nil 上取方法
        ⇒ 抛错 ⇒ **派发器把整条 `MC_POST_RENDER` 回调摘掉**。更糟的是当时的判据用 `value == nil`
        把这个**错误行为**钉死了。条文 2026-09-25（批次 132）就写进 `AGENTS.md`，但只落了条文、
        **没有判据** —— 这条就是补上的判据。
        """
        from tools.api_deviation_ledger import SHAPES, load_entries

        entries = load_entries(DEVIATIONS)
        needing = [entry for entry in entries if entry.mentions_nil_return]
        self.assertEqual(len(needing), 0, "GetData寿命修复后恒nil历史偏离已全部清偿；原文仍在各组before存档")
        missing = [
            hex(entry.identifier)
            for entry in needing
            if not (entry.has_pc_shape and entry.has_our_shape)
        ]
        self.assertEqual(missing, [],
                         f"这些条目正文写了「恒 nil」却没写清两侧形状：{missing}。"
                         "补一行『PC 形状：<nil|对象|数字|布尔|字符串> 我们形状：<…>』。")
        for entry in needing:
            with self.subTest(id=hex(entry.identifier)):
                self.assertIn(entry.pc_shape, SHAPES,
                              f"{hex(entry.identifier)} 的 `PC 形状` 取值不在词表里：{entry.pc_shape!r}")
                self.assertIn(entry.our_shape, SHAPES,
                              f"{hex(entry.identifier)} 的 `我们形状` 取值不在词表里：{entry.our_shape!r}")

    def test_object_shaped_pc_entries_name_the_chaining_trap(self):
        """`PC 形状` 不是 nil、而我们给 nil ⇒ 后果里**必须**点名"链式调用会抛错"。

        这一条是"判据要消费者视角"在**台账侧**的一半：模组会照 PC 的用法往下链，
        我们给 nil 时那一下不是"少显示点东西"，而是**抛错 + 整条回调被摘掉**（两者的严重程度差一个量级，
        098 那次"后果写错"就是这么来的）。
        """
        from tools.api_deviation_ledger import CHAINING_MARKER, load_entries

        entries = load_entries(DEVIATIONS)
        traps = [entry for entry in entries if entry.needs_chaining_warning]
        # ★ 2026-09-29（批次 195）：下界从 3 降到 1 —— 四条 `Get*RNG` 从"恒 nil"改成真返回
        # 对象句柄（`PC 形状：对象 我们形状：对象`），这条判据认出来的"会链到 nil 上"的条目
        # 因此从 **6 条掉到 2 条**（`EntityPlayer:GetName`、`GetOtherTwin`）。判据本身
        # （"PC 给对象/字符串、我们给 nil ⇒ 后果必须点名链式调用会抛错"）一个字没改，
        # 变的只是它还剩下几条能咬 —— 这里把下界跟着改小，并留下这条说明。
        self.assertEqual(len(traps), 0, "配对接口已返回对象，当前不应再有已登记的对象→nil链式陷阱")
        missing = [
            hex(entry.identifier) for entry in traps if CHAINING_MARKER not in entry.consequence
        ]
        self.assertEqual(missing, [],
                         f"这些条目 PC 给的是对象/字符串、我们给 nil，后果却没写"
                         f"「{CHAINING_MARKER}」：{missing}")

    def test_shaped_entries_count_is_pinned(self):
        """写了形状两栏的条数**写死**在这儿：新增/删除都要人工过一遍（与其它记账方式同一套）。"""
        from tools.api_deviation_ledger import load_entries

        entries = load_entries(DEVIATIONS)
        shaped = [entry for entry in entries if entry.has_pc_shape or entry.has_our_shape]
        self.assertEqual(
            len(shaped), EXPECTED_SHAPE_ENTRIES,
            "写了形状两栏的条数变了。请确认每条都填了 `PC 形状：`/`我们形状：`，"
            "并把这个数字同步到 `EXPECTED_SHAPE_ENTRIES`（上面那段注释里补一行说明）。",
        )
        for entry in shaped:
            with self.subTest(id=hex(entry.identifier)):
                self.assertTrue(entry.has_pc_shape and entry.has_our_shape,
                                f"{hex(entry.identifier)} 只写了形状两栏里的一栏 —— 两栏要成对写")


if __name__ == "__main__":
    unittest.main()

# 2026-10-09：GetName 不再恒 nil，偏离/欠账/形状各减一；GetOtherTwin仍需链式警告。

# 2026-10-09：临时效果五条占位恢复真实语义，44→39，debt24→19；旧记录另存逐字归档。

# 2026-10-09：HUDOffset真实字段读写解除1条debt，39→38/debt19→18，旧记录逐字归档。

# 2026-10-09：配对三条debt解除，38→35/debt18→15；两个对象形状偏离8→6，旧全文归档。

# 2026-10-09：6条RNG引用偏离恢复，34→28/design14→8；debt14不变，形状记录6→2。

# 2026-10-09：GetSmeltedTrinkets真实向量/扩展契约销账，28→27，debt14→13；旧源码逐字归档。

# 2026-10-15：GetDefaultAnimationName真实字段已确证并修复，25→24，design 8→7；历史原文与读数保留在dist/bossbar-restore-20261015。
