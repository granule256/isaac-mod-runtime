#include "interfaces/lua/api_deviation.hpp"

namespace isaac::runtime {
namespace {

// 每条都对应实现处的一段注释（"占位/未定位/语义偏差/恒假/常量实现"），这里只做汇总与索引。
// 顺序按 catalog id，方便与 `api_catalog.cpp` 对照。
//
// ★★ 每条还**必须**写一行 `PC 契约：tools/pc_contract_docs/<页>:<行号> 「<原文片段>」`
//    （批次 111 起，门禁强制；那个目录是 PC 文档被引用页的逐字节副本、在仓库里）：
//    门禁 `test_api_deviation.py` 会回头核对那一页、那一行、以及片段是否真的在那一行里。
//    文档里确实没有这一条时写 `PC 契约：文档里没有 …`。
//    起因：107 那次**凭推断**断言了 PC 的语义（`Input.IsActionTriggered`），导致 107→109→110
//    三批在同一个 API 上返工。规矩与例子见 `docs/加一个Lua-API-的做法.md` 的"第 0 步"。
constexpr ApiDeviation kApiDeviations[] = {
    // ---- `Options`（值型条目）------------------------------------------------
    {0x00020001,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Options.md:96 「#### float HUDOffset  {: .copyable aria-label='Variables' }」"
     "PC 的 `Options.HUDOffset` 从引擎选项结构里读；该偏移尚未定位，所以这里固定 1.0"
     "（与 EID 中文默认配置一致）。偏离后果：玩家在游戏里调过 HUD 偏移时，EID 描述的位置"
     "与 PC 不一致。"
     "判据：runtime/tests/test_lua_isaac_table.py（钉\"是那个 1.0 归一化默认值\"；未钉\"玩家在游戏里调过 HUD 偏移之后的差异\"）。"},

    // ---- `Game` / `Seeds`（字段直读，偏移未定位）------------------------------
    {0x02010008,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Game.md:359 「GetSeeds」"
     "PC 的 `Game:GetSeeds()` 返回引擎的种子对象；Switch 的 `Game` 类没有 `GetSeeds` 方法，"
     "字段偏移尚未定位，所以这里返回一个值自洽的替代对象。偏离后果：EID 用它做"
     "`IsCustomRun()` 与缓存键判断，拿到的是自洽值而非引擎真值。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（钉对象存在、字段可读、取值自洽；未钉与 PC 引擎种子对象的逐值一致）。"},
    {0x02010009,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Game.md:389 「#### int GetVictoryLap」"
     "同 `Game:GetSeeds`：PC 是字段直读，偏移未定位 ⇒ 这里返回固定值。"
     "偏离后果：EID 只在判断'胜利后'的少数分支上用到它。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（钉返回类型与自洽取值；未钉与 PC 的逐值一致）。"},
    {0x0F010001,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Seeds.md:111 「#### boolean IsCustomRun」"
     "`Seeds:IsCustomRun()`（挑战局或带种子的局）在 Switch 上没有可 thunk 的访问器，"
     "字段偏移未定位 ⇒ 返回保守值。偏离后果：带种子/挑战局的少数描述分支可能不生效。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（钉不报错、返回布尔；未钉带种子/挑战局这一侧的语义）。"},
    {0x0F010002,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Seeds.md:78 「#### int GetStartSeed」"
     "`Seeds:GetStartSeed()` 是 EID 的缓存键，偏移未定位 ⇒ 返回自洽值。"
     "偏离后果：缓存键可能与 PC 不同（只影响缓存命中，不影响显示内容正确性）。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（钉返回数字、可当缓存键用；未钉与 PC 种子值一致）。"},

    // ---- `Input` -------------------------------------------------------------
    {0x09010004,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Input.md:73 「#### boolean IsActionTriggered」"
     "PC 的 `Input.IsActionTriggered` 由引擎算「这一帧刚按下」（文档 `Input.md:73`：一次按键只答一次，"
     "同一帧内问多少次都答 true）；Switch 上引擎那条路在我们跑到它的时机里**永远是假**"
     "（真机读数：动作 4/5/6/7/13 的「按住」为真、controller = 33，而「刚按下」一次都没真；"
     "反汇编显示两个引擎函数结构完全相同、只差虚函数槽 `vtable+0x48`(按住) 与 `+0x50`(刚按下)）"
     "⇒ 本 Runtime 改用**自己的上升沿**：拿已验证可用的 `IsActionPressed` 当原语。"
     "★ 判据形状与 PC 对齐：**同一帧内同一个答案**（批次 109）、**一次按键只报一次**。"
     "★ 批次 110 又加了**松手去抖**（连续 6 帧读到「没按住」才算松手）：真机上引擎的「按住」"
     "查询在按着的时候会**闪断**（109 的读数：动作 7 在**按住**期间被报了 **170** 次边沿，"
     "用户看到「长按不停翻页、速度忽快忽慢」）⇒ 不挡它就会把一次长按拆成很多次「刚按下」。"
     "偏离后果：剩余差别两条 —— ① 一次按键整段落在两帧的采样点之间（按下与抬起都没被采到）会漏；"
     "② 松手后 100 毫秒内又按下会被并成一次。"
     "★★ ② **已实测确认是缺陷、不是可以忽略的边角**（2026-09-20 用户报：「长按确实不会翻了、"
     "正常慢些按没问题，但**快速按就没有效果**」）：PC 上只受 EID 自己的 50 毫秒防抖限制，"
     "两次按键相隔 >50 毫秒就都能翻；我们多了这 6 帧（≈100 毫秒）的松手去抖 ⇒ "
     "**间隔 50~100 毫秒的连按会被吞**。"
     "**用户 2026-09-20 明确要求：先记录为缺陷、暂不调整行为。**"
     "将来要修时的办法与判据（已备好）：读数里「按住最长闪断」那一行给出引擎实际闪断几帧 —— "
     "若只有 1~2 帧，把 `ActionEdgeTracker::kReleaseFrames` 从 6 降到 2~3（≈33~50 毫秒），"
     "既挡得住闪断、又让快速按接近 PC 手感；降完必须复测「长按不许再连续翻页」。"
     "判据：runtime/tests/test_input_action_edge.py（钉按帧语义与去抖的每一条：首帧不算边沿、"
     "同帧内同一个答案、**跨帧闪断期间不许多报**、真松手后再按才算新的一次、连点、分槽、重置）；"
     "runtime/tests/test_lua_input_binding_abi.py（端到端：按住→松开→再按住）。"},
    {0x03010011,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Level.md:260 「#### int GetStartingRoomIndex」"
     "PC 的 `Level:GetStartingRoomIndex()` 返回当前层起始房间的 gridindex；Switch 的引擎里**没有**"
     "对应符号/字段（取证过程见 `runtime/source/level_start_room.hpp` 顶部：符号表、Ghidra 类型库、"
     "镜像字符串、`RoomDescriptor` 的 24 个标志、`RoomConfig::Room` 字段、`Level/Game` 的 0x215xx "
     "全镜像扫描都查过），所以这里给的是**派生值**：本层第一次被看到时玩家所在的房间索引。"
     "偏离后果：正常路径（开局或换层后第一次看到新层）与 PC 一致；**唯一已知会偏的情形**是"
     "运行时在「某一层中途」才加载（模组重载 / 换卡）时，会把「我们第一次看到的那个房间」当成起始房间"
     "⇒ EID 的 `hideInOverview`（起始房间才显示'角色'分类）在那一段会多显示一条分类。"
     "**取证后的替换方式**：真机上把 `Game + 0x2155x` 那一片（`0x21550`=当前 `Room*`、"
     "`0x21558`=当前房间索引、`0x21560`=当前维度，都是已知的真值）与相邻字段一起读回来、"
     "在「站在起始房间」与「走到别的房间」两种状态下各读一次，就能确定哪个字段是起始房间索引；"
     "定位后把 `StartingRoomIndexForCurrentLevel()` 换成那条字段直读即可。"
     "判据：runtime/tests/test_level_start_room.py（钉跟踪语义的每一条分支与「读不到就不编造」；"
     "未钉真机上「引擎真值 == 我们记的值」这一半）。"},
    {0x03010003,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Level.md:142 「GetCurses」"
     "PC 的 `Level:GetCurses()` 是 `原始诅咒位 | 永久诅咒 & ~禁用诅咒` 三步合成；"
     "后两步的两个函数地址本轮未定位，所以只返回 `Level + 0x0C` 的原始位掩码。"
     "偏离后果：本局临时诅咒（`AddCurse`）读得到，而'永久诅咒'与'禁用诅咒'两侧的修正读不到。"
     "判据：runtime/tests/test_lua_entity_query.py（钉\"读的是 Level + 0x0C 的原始位\"；**未**钉\"永久诅咒/禁用诅咒两步合成\"那一半 —— 那正是本条偏离）。"},

    // ---- `Room` 网格/寻路 ------------------------------------------------------
    //
    // ★ 2026-09-20（批次 098）：`GetGridWidth`(0x04010002)/`GetGridHeight`(0x04010003)/
    //   `GetGridSize`(0x04010004)/`GetGridIndex`(0x04010005) 四条偏离**已解除** ——
    //   网格尺寸字段（`Room + 0x14`/`+0x18`）、通行代价数组（`Room + 0xE98`）与格坐标换算
    //   （`GetGridIndex(Vector2) @ 0x459e3c`）都定位到了，现在读的是真值。
    //   **为什么必须改**：旧占位让 `GetGridPath` 恒返 1000（> EID 的 900 阈值）⇒ 地上每一颗
    //   药丸、每一张卡片都被判"够不到"、只画问号（用户可见缺陷）。证据与宿主判据见
    //   `runtime/src/interfaces/lua/remaining_api.cpp` 的批次 098 注释与
    //   `runtime/tests/test_lua_room_grid.py`、`tools/room_grid_reachability_probe.py`。
    //   记录保留在此，是为了"曾经登记过的偏离"有迹可循 —— 条目本身已从表里移除。
    {0x04010006,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Room.md:370 「#### int GetGridPath」"
     "`Room:GetGridPath(Index)`：真值已实现（读 `Room + 0xE98` 那张 int32 表，下标 `W*y + x`），"
     "唯一残留的偏离是**越界口径**：PC 的 Lua 访问器按下标直读，越界会读进相邻内存；"
     "我们越界（负数或 `>= W*H`）一律回答 0 —— 也就是引擎自己对越界坐标的答案"
     "（`Room::GetGridPath(int,int) @ 0x484120` 在参数越界时返回 0）。"
     "偏离后果：越界输入下 PC 会给出'没有语义的字节'，我们给 0（可走）；EID 只会用 "
     "`GetGridIndex` 算出来的合法下标来问，走不到这条差异上。"
     "判据：runtime/tests/test_lua_room_grid.py（钉越界口径：负数与 >= W*H 一律 0）、runtime/tests/test_room_grid_reachability.py（消费者视角：把这类网格喂给 EID 自己的寻路器，必须判出\"有路/没路\"）。"},
    // 0x04010007 `Room:GetGridEntity()` 的偏离**已于 2026-09-16 解除**：网格实体表定位到
    // `Room + 0x30`（证据见 `runtime_constants.hpp` 的 `kRoomGridEntityTableOffset`），
    // 现在返回真实的 `GridEntity` 句柄（`GridEntity:GetVariant()`/`GetType()` 同批落地）。
    // 记录保留在此，是为了"曾经登记过的偏离"有迹可循 —— 条目本身已从表里移除。

    // ---- `Sprite` ------------------------------------------------------------
    {0x0D010012,
     ApiDeviationKind::NotInEngine,
     "PC 契约：tools/pc_contract_docs/Sprite.md:109 「GetTexel」"
     "Switch 的 `ANM2` 没有 `GetTexel`，真实像素链路未定位 ⇒ 常量实现。"
     "偏离后果：EID 的 `IsAltChoice()` 逐像素比对拿不到真值（该分支退化为不启用）。"
     "判据：runtime/tests/test_lua_sprite.py（钉常量实现与调用形状；未钉真实像素链路 —— 引擎里那条链路尚未定位）。"},

    // ---- `Isaac` 门面 --------------------------------------------------------
    {0x0E010002,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Isaac.md:446 「#### int GetTime」"
     "PC 的 `Isaac.GetTime()` 是「自操作系统启动起的**毫秒**」（`Isaac.md:448`）；这里返回"
     "`cntpct_el0 / 19200` 的毫秒（`engine_memory_guard.hpp` 的 `EngineMillisecondsNow()`）。"
     "偏离后果：与 PC 的剩余差别只有 **epoch**（PC 是「OS 启动起」、我们是 Switch 的 tick 起点）"
     "—— 模组都是算差值（防抖、动画计时），语义完全一致；只有把 `GetTime()` 当**绝对时间戳**"
     "比较或存盘的用法会与 PC 不同（卡上四个模组都没有这种用法）。"
     "不声称与 PC 逐值相同。"
     "★ 这一条以前是「`GetFrameCount() / 30` 的**整数秒**」，单位差 1000 倍，后果不是"
     "「显示差一点」而是**把模组的逻辑闸死**：EID 的库存概况翻页判据是"
     "`Isaac.GetTime() - lastInputTime > 50`（**50 毫秒**防抖），秒口径下几乎永不成立"
     "⇒ 整段翻页逻辑不执行（模组侧明明已经收到 `IsActionTriggered` 的 true）。"
     "判据：runtime/tests/test_lua_isaac_table.py（**睡 30 毫秒之后它至少涨 20** ——"
     "秒口径会得到 0，那条断言就是为此写的；另加单调不减）。"},

    // ---- `Entity` / `EntityPlayer` 的占位成员 --------------------------------
    {0x0E010017,
     ApiDeviationKind::Placeholder,
     "PC 契约：文档里没有 `EntityPlayer.GetData` 这一条"
     "`EntityPlayer:GetData()`：`ModData` 结构没有证据 ⇒ 恒 nil（不是 stub 告警，是明确的'暂缺'）。"
     "偏离后果：依赖 mod 侧自定义数据的少数显示缺失，而不会给出错误内容。"
     "判据：runtime/tests/test_lua_entity_player.py（钉\"返回 Runtime 自管的稳定表\"；未钉 PC 的 `ModData` 结构语义）。"},
    {0x0E010025,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Entity.md:344 「#### table GetData」"
     "`Entity:GetData()`：`ModData` 结构没有证据 ⇒ 恒 nil。"
     "偏离后果：依赖 mod 自定义数据的少数显示缺失，而不会给出错误内容。"
     "判据：runtime/tests/test_lua_entity_query.py（钉恒 nil 的形状与调用不报错；未钉 PC 的 `ModData` 语义）。"},
    {0x0E01001D,
     ApiDeviationKind::Placeholder,
     "PC 契约：文档里没有 `ItemConfig.HasTags` 这一条"
     "`ItemConfig:HasTags()`：`Item` 的 tags 字段偏移未定位 ⇒ 恒 false。"
     "偏离后果：靠 tags 分支的少数条目描述不出现。"
     "判据：runtime/tests/test_lua_item_config.py（钉恒 false；未钉真实 tags 位 —— 字段偏移未定位）。"},
    {0x0E01001E,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/ItemConfig_Item.md:23 「#### boolean HasTags」"
     "`ItemConfig_Item:HasTags()`：`Item` 的 tags 字段偏移未定位 ⇒ 恒 false。"
     "偏离后果：靠 tags 分支的少数条目描述不出现。"
     "判据：runtime/tests/test_lua_item_config.py（钉恒 false；同上，字段偏移未定位）。"},
    {0x0E010029,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/EntityPickup.md:35 「#### boolean IsShopItem」"
     "`EntityPickup:IsShopItem()`：'商店商品'的判据没有证据（只有 `ShopItemId` 这个候选字段）"
     "⇒ 恒 false。偏离后果：商店里卡片/药丸相关的一条描述判断会偏保守。"
     "判据：runtime/tests/test_lua_entity_query.py（钉恒 false 与调用不报错；未钉真实\"商店商品\"判据）。"},
    {0x0E010030,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:1185 「GetPill」"
     "`EntityPlayer:GetPill()`：按槽位读口袋的引擎字段（口袋数组偏移）未定位 ⇒ 恒 0"
     "（PC 上'空口袋'本来就是 0，EID 按 `id ~= 0` 判）。"
     "偏离后果：口袋里有药丸时缺一条口袋描述，但不会造成错误结论。"
     "判据：runtime/tests/test_lua_entity_player.py（钉槽位参数口径与恒 0 的返回值；未钉真实口袋数组 —— 偏移未定位）。"},
    {0x0E010031,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:882 「GetCard」"
     "`EntityPlayer:GetCard()`：口袋数组偏移未定位 ⇒ 恒 0。"
     "偏离后果：口袋里有卡牌时缺一条口袋描述，但不会造成错误结论。"
     "判据：runtime/tests/test_lua_entity_player.py（同上：槽位口径 + 恒 0）。"},
    {0x0E010048,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:1131 「#### string GetName」"
     "`EntityPlayer:GetName()`：名字来自存档、偏移未定位 ⇒ 恒 nil"
     "（EID 只做字符串拼接，nil 会被 `tostring` 兜住）。"
     "偏离后果：依赖真实玩家名的显示会缺内容、或被写成 nil 字样；但不会报错、也不会给出错误结论。"
     "判据：runtime/tests/test_lua_entity_player.py（钉\"无参返回 nil 而不是报错\"；未钉真实玩家名 —— 偏移未定位）。"},
    // 批次 13（2026-09-16）新增。
    {0x0E010054,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/GridEntity.md:38 「GetRNG」"
     "`GridEntity:GetRNG()`：PC 返回引擎里那个 RNG 的**引用**（从返回对象上 `SetSeed`/`Next` "
     "会改到实体自己），这里返回的是**取到那一刻的 16 字节快照**。"
     "为什么这样选：网格实体随时会被销毁（石头被炸、尖刺被消耗、换房间重建），而本句柄只存实体"
     "地址、拿不到网格下标，做不到'每次访问重新解析并校验'；让 Lua 长期持有'引擎对象内部成员'"
     "的指针，等于把写已释放内存的口子开给模组。"
     "偏离后果：读语义与 PC 逐值相同（`GetSeed`/`Next`/`RandomInt` 在取到的那一刻完全一致，"
     "EID 的 `spikes:GetRNG():GetSeed()` 正属此类）；只有在'从返回的 RNG 上改状态、并期待实体"
     "跟着变'这种用法上才与 PC 不同 —— 那类用法目前没有任何模组在用。"
     "判据：runtime/tests/test_lua_grid_rng_pill.py（钉\"返回的是快照、在它上面 Next() 不动引擎内存\"这条语义本身，并同时证明 Next() 真的被调用过）。"},


    // ---- `ItemConfig_Item:IsAvailable()` 的 flags（2026-09-16，兼容层定义）------------------
    {0x0E010055,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/ItemConfig_Item.md:35 「#### boolean IsAvailable」"
     "`Item::IsAvailable(long flags, uint)` 的 `flags` 由我们定：bit1（成就解锁）+ bit2（tags/"
     "当前局阻挡）+ bit3（模组提供的物品）= `0xE`。原因：引擎里 `Item`/`Card`/`PillEffect` 三个 "
     "`IsAvailable` 在镜像中**没有任何调用点**（也不在虚表里），是 Switch 版编译掉 Lua API 后留下的"
     "死代码，参数无法从游戏自己的用法学到。取舍依据：PC 文档 `ItemConfig_Item.md:35-38` 把"
     "『没解锁』与『被 tags 挡掉』写在同一句里，所以这两条检查都要跑到；bit3 只在装了添加物品的"
     "模组时才有影响，打开它是为了不把模组道具误判成不可用。"
     "**未覆盖的 PC 语义**：bit0（按 `Type` 分流的主动/跟班/饰品专用检查）、第三个参数（反汇编里"
     "四个分支都没读到它，这里传 0）、以及各分支内部还有若干与楼层/贪心模式/特定道具 id 相关的"
     "特例条件 —— 我们没有逐条复现，只保证「这两类检查跑到」。"
     "偏离后果：极少数依赖『类型专用检查』或特例道具的道具，可用性判断与 PC 可能不同；"
     "EID 的用途（Spindown Dice / 背包合成跳过未解锁道具）不受影响。"
     "判据：runtime/tests/test_lua_item_config.py（钉三类 `IsAvailable` 形状、flags 口径与降级行为；未钉各分支内部的楼层/贪心模式特例）。"},
};

constexpr std::size_t kApiDeviationCount = sizeof(kApiDeviations) / sizeof(kApiDeviations[0]);

} // namespace

const ApiDeviation* FindApiDeviation(std::uint32_t id) noexcept {
    for (std::size_t index = 0; index < kApiDeviationCount; ++index) {
        if (kApiDeviations[index].id == id) {
            return &kApiDeviations[index];
        }
    }
    return nullptr;
}

std::size_t ApiDeviationCount() noexcept {
    return kApiDeviationCount;
}

const char* ToString(ApiDeviationKind kind) noexcept {
    switch (kind) {
    case ApiDeviationKind::Partial: return "partial";
    case ApiDeviationKind::Placeholder: return "placeholder";
    case ApiDeviationKind::NotInEngine: return "not-in-engine";
    }
    return "unknown";
}

} // namespace isaac::runtime
