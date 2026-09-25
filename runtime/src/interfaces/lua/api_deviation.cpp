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
//
// =====================================================================================
// 偏离的**性质**（2026-09-21，批次 017：把"平台固有"与"我们的欠账"分开登记）
// =====================================================================================
//
// 为什么要有这一栏：台账原来只有 `kind`（Partial / Placeholder / NotInEngine —— 记的是"偏离长什么样"），
// 读者分不清一条偏离是**这台机器上永远消不掉**的，还是**我们还没做到**的。两者混在一起会出两种错判：
// 把欠账当平台限制（于是没人去修），或把平台限制当欠账（于是反复去做做不到的事）。
//
// 口径（写死、可逐条复核；判定时只看下面这几条，**不看** `kind`）：
//
//   * **platform（平台固有）** —— 同时满足：
//       ① PC 上确实有对应物（PC 文档里查得到它做什么）；
//       ② Switch 平台侧**没有可用底座**，或 PC 的语义**无法映射**过来
//          （PC 依赖的输入源/系统能力在这台机器上不存在，例如鼠标这种指向设备、调试控制台）；
//       ③ 已经**取证过"没有"**（是"查过、确认没有"，不是"我们还没查"）；
//       ④ 结论：继续做工作也消不掉，只能永久登记（正确处置 = 登记 + 不再重复投入）。
//       实例：`Input.GetMousePosition` / `Input.IsMouseBtnPressed`（Switch 没有鼠标这一输入源）、
//       `Isaac.ExecuteCommand`（Switch 没有控制台、也没有等价的命令通道）。
//
//   * **debt（我们的欠账）** —— 底座**存在或可定位**（引擎里有对应的字段/函数/数据结构，
//     或台账正文里已经写出了可执行的定位办法），只是我们**还没定位 / 还没实现 / 实现得偏保守**。
//     结论：**能还**；还清之后应当把这条从台账里删掉（098 那次消掉四条 `Room` 网格偏离就是这个形态）。
//     实例：`Options.HUDOffset`（偏移未定位）、`GridEntity:GetRNG` 之外的绝大多数占位条目。
//
//   * **design（主动保留的口径差异）** —— 两侧都做得到，但我们**有意**选了与 PC 不同的口径，
//     而且台账正文里明确写了"为什么不照着做"（复刻 PC 等于复刻它的未定义行为；或照着做会把引擎
//     内部指针交给模组、开出写已释放内存的口子）。结论：**不打算改**；要动它必须先改设计意图
//     （属于用户裁决，不属于工程欠账）。
//     实例：`Room:GetGridPath` 的越界口径（PC 越界直读相邻内存 = 没有语义的字节）、
//     `GridEntity:GetRNG` 返回快照而不是引擎 RNG 的引用。
//
// ★ 判定时**不看** `kind`：`kind` 记"偏离长什么样"，`nature` 记"这条能不能还"，两者可以不一致。
//   已知的一处不一致：`Sprite:GetTexel`（0x0D010012）的 `kind` 还写着 `NotInEngine`，
//   但实现 2026-09-12 起已经改成**直接调引擎的 `ANM2::GetTexel`**（`runtime_constants.hpp` 的
//   `kSpriteGetTexelOffset = 0xC074`）⇒ 性质是 `debt`（只剩"取不到入口/动画未建立"时的兜底）。
//   这次**只登记性质、不改 `kind` 与语义结论**，那处描述已过期一事写在
//   `dist/change-archive-20260921/017-deviation-nature-split/README.md` 里，等人复核。
//
// ★ 本批次**新增了 3 条 `platform` 条目**（`Input.GetMousePosition` 0x09010007、
//   `Input.IsMouseBtnPressed` 0x09010008、`Isaac.ExecuteCommand` 0x0E01002D）：它们的降级事实
//   此前只写在 `api_catalog.cpp` 的目录注释与实现注释里（原话就是"平台降级/平台限制"），
//   符合本表"只收代码注释里已经明确承认的偏离"的收表口径，却一直没被收进来 —— 于是"平台固有"
//   这一类在这张表里是空的，分栏也就没有意义。原因与后果照抄实现处注释，未新增任何语义判断。
//
// ★ 硬判据（门禁 `runtime/tests/contract/test_api_deviation.py` 钉住）：
//   每条必须写 `性质：<platform|debt|design>（<中文名>）——理由：<一行理由>`，
//   取值只能是上面三个、不许缺、不许出现第四个；三个取值**各自的条数**被钉住（只能降不能升，
//   照 `EXPECTED_*` 那套记账方式）。
constexpr ApiDeviation kApiDeviations[] = {
    // ---- `Options`（值型条目）------------------------------------------------
    {0x00020001,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Options.md:96 「#### float HUDOffset  {: .copyable aria-label='Variables' }」"
     "PC 的 `Options.HUDOffset` 从引擎选项结构里读；该偏移尚未定位，所以这里固定 1.0"
     "（与 EID 中文默认配置一致）。偏离后果：玩家在游戏里调过 HUD 偏移时，EID 描述的位置"
     "与 PC 不一致。"
     "性质：debt（我们的欠账）——理由：引擎里就是同一份 `Options` 结构，只是 HUD 偏移这一格还没定位；定位后换成字段直读即可，属能还的欠账。"
     "判据：runtime/tests/test_lua_isaac_table.py（钉\"是那个 1.0 归一化默认值\"；未钉\"玩家在游戏里调过 HUD 偏移之后的差异\"）。"},

    // ---- `Game` / `Seeds`（字段直读，偏移未定位）------------------------------
    {0x02010008,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Game.md:359 「GetSeeds」"
     "PC 的 `Game:GetSeeds()` 返回引擎的种子对象；Switch 的 `Game` 类没有 `GetSeeds` 方法，"
     "字段偏移尚未定位，所以这里返回一个值自洽的替代对象。偏离后果：EID 用它做"
     "`IsCustomRun()` 与缓存键判断，拿到的是自洽值而非引擎真值。"
     "性质：debt（我们的欠账）——理由：种子的真值在引擎里（同一局要能复现随机），台账写的是「字段偏移尚未定位」⇒ 可定位、可还。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（钉对象存在、字段可读、取值自洽；未钉与 PC 引擎种子对象的逐值一致）。"},
    {0x02010009,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Game.md:389 「#### int GetVictoryLap」"
     "同 `Game:GetSeeds`：PC 是字段直读，偏移未定位 ⇒ 这里返回固定值。"
     "偏离后果：EID 只在判断'胜利后'的少数分支上用到它。"
     "性质：debt（我们的欠账）——理由：同 `GetSeeds`：`Game` 里本来就有 victory lap 计数，缺的只是那个偏移 ⇒ 可定位、可还。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（钉返回类型与自洽取值；未钉与 PC 的逐值一致）。"},
    {0x0F010001,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Seeds.md:111 「#### boolean IsCustomRun」"
     "`Seeds:IsCustomRun()`（挑战局或带种子的局）在 Switch 上没有可 thunk 的访问器，"
     "字段偏移未定位 ⇒ 返回保守值。偏离后果：带种子/挑战局的少数描述分支可能不生效。"
     "性质：debt（我们的欠账）——理由：台账写「没有可 thunk 的访问器 + 字段偏移未定位」——是没找到，不是引擎里没有；`GetTexel` 那条「Switch 没有它」后来被证伪就是教训。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（钉不报错、返回布尔；未钉带种子/挑战局这一侧的语义）。"},
    {0x0F010002,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Seeds.md:78 「#### int GetStartSeed」"
     "`Seeds:GetStartSeed()` 是 EID 的缓存键，偏移未定位 ⇒ 返回自洽值。"
     "偏离后果：缓存键可能与 PC 不同（只影响缓存命中，不影响显示内容正确性）。"
     "性质：debt（我们的欠账）——理由：起始种子在引擎里必然存在（EID 拿它当缓存键），缺的只是字段偏移 ⇒ 可定位、可还。"
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
     "性质：debt（我们的欠账）——理由：引擎那两条查询都在（只差虚表槽），残留的 6 帧松手去抖与采样漏帧是**我们自选的口径**，台账里已写明将来怎么改、怎么复测 ⇒ 能还。"
     "判据：runtime/tests/test_input_action_edge.py（钉按帧语义与去抖的每一条：首帧不算边沿、"
     "同帧内同一个答案、**跨帧闪断期间不许多报**、真松手后再按才算新的一次、连点、分槽、重置）；"
     "runtime/tests/test_lua_input_binding_abi.py（端到端：按住→松开→再按住）。"},

    // 批次 017（2026-09-21）：以下两条**平台降级**此前只写在 `api_catalog.cpp` 的目录注释与
    // `input_api.cpp` 的实现注释里（原话就是"平台限制"），一直没被收进本表 —— 于是"平台固有"
    // 这一类在台账里是空的，分栏也就没有意义。本次照抄实现处的结论与后果，未新增语义判断。
    {0x09010007,
     ApiDeviationKind::NotInEngine,
     "PC 契约：tools/pc_contract_docs/Input.md:40 「#### [Vector](Vector.md) GetMousePosition ( boolean gameCoords )」"
     "PC 的 `Input.GetMousePosition(gameCoords)` 返回「当前鼠标指针的位置」（游戏坐标或渲染坐标，"
     "`Input.md:42`）；Switch 上没有鼠标这一输入源、也没有等价的指针输入层 ⇒ 我们恒返回 `(0,0)`，"
     "并且**绝不抛错**（GoodTrip 的 `scripts/control.lua:190` 每帧调它，抛错会让整条回调被派发器摘掉）。"
     "偏离后果：拿它当「鼠标这一帧动没动」的模组（GoodTrip 用「与上一帧距离平方 > 4」判）会一直得到"
     "「没动过」⇒ 鼠标拖拽 / 点地图图钉那类交互不会触发；只做手柄路径的功能不受影响。"
     "性质：platform（平台固有）——理由：Switch 上没有鼠标这一输入源，PC 的「指针屏幕坐标」在这台机器上"
     "没有对应物（用户点名的平台固有例子）⇒ 只能恒给 (0,0)，再怎么继续做工作也消不掉。"
     "判据：runtime/tests/test_goodtrip_batch_a.py（钉恒返回 `Vector(0,0)`、且只允许「参数个数不对」"
     "这一条抛错路径；未钉触摸屏/摇杆光标那种等价替代 —— 那属于新的输入层取证，不是本条的还账）。"},
    {0x09010008,
     ApiDeviationKind::NotInEngine,
     "PC 契约：tools/pc_contract_docs/Input.md:121 「#### boolean IsMouseBtnPressed ( [Mouse](enums/Mouse.md) button )」"
     "PC 的 `Input.IsMouseBtnPressed(Mouse)` 回答「某个鼠标键现在按着没有」（`Input.md:123` 列了左右键、"
     "滚轮、侧键）；Switch 上没有鼠标按键设备 ⇒ 我们恒返回 **false**，并照常校验参数形状。"
     "偏离后果：模组问「鼠标点了没有」永远得到 false ⇒ 鼠标点击类分支不触发（与「只做手柄路径」的既定"
     "决定一致）；不抛错是硬要求 —— 它被每帧的鼠标状态跟踪调用。"
     "性质：platform（平台固有）——理由：同 `GetMousePosition`，Switch 上没有鼠标按键这一设备，"
     "PC 的鼠标键语义无法映射 ⇒ 只能恒 false，做不掉。"
     "判据：runtime/tests/test_goodtrip_batch_a.py（钉恒 false 且参数经由 `CheckMouseButtonArguments` "
     "校验；未钉鼠标键的真实读数 —— 平台上不存在这个输入源）。"},
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
     "性质：debt（我们的欠账）——理由：台账自己给出了可执行的定位办法（真机读 `Game + 0x2155x` 那一片、在两种状态下各读一次）⇒ 底座可定位，属能还的欠账。"
     "判据：runtime/tests/test_level_start_room.py（钉跟踪语义的每一条分支与「读不到就不编造」；"
     "未钉真机上「引擎真值 == 我们记的值」这一半）。"},
    {0x03010003,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Level.md:142 「GetCurses」"
     "PC 的 `Level:GetCurses()` 是 `原始诅咒位 | 永久诅咒 & ~禁用诅咒` 三步合成；"
     "后两步的两个函数地址本轮未定位，所以只返回 `Level + 0x0C` 的原始位掩码。"
     "偏离后果：本局临时诅咒（`AddCurse`）读得到，而'永久诅咒'与'禁用诅咒'两侧的修正读不到。"
     "性质：debt（我们的欠账）——理由：PC 那两步合成调的是引擎自己的函数，我们在 Switch 镜像里没定位到那两个地址 —— 属「未定位」，不是「不存在」。"
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
     "性质：design（主动保留的口径差异）——理由：真值已实现，残留的越界口径是**我们主动选的**（PC 越界直读相邻内存 = 没有语义的字节，复刻它没有价值）⇒ 不打算改。"
     "判据：runtime/tests/test_lua_room_grid.py（钉越界口径：负数与 >= W*H 一律 0）、runtime/tests/test_room_grid_reachability.py（消费者视角：把这类网格喂给 EID 自己的寻路器，必须判出\"有路/没路\"）。"},
    // 0x04010007 `Room:GetGridEntity()` 的偏离**已于 2026-09-16 解除**：网格实体表定位到
    // `Room + 0x30`（证据见 `runtime_constants.hpp` 的 `kRoomGridEntityTableOffset`），
    // 现在返回真实的 `GridEntity` 句柄（`GridEntity:GetVariant()`/`GetType()` 同批落地）。
    // 记录保留在此，是为了"曾经登记过的偏离"有迹可循 —— 条目本身已从表里移除。

    // ---- `Sprite` ------------------------------------------------------------
    {0x0D010012,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Sprite.md:109 「GetTexel」"
     "★ 2026-09-21 更正（原写「Switch 的 `ANM2` 没有 `GetTexel`，真实像素链路未定位 ⇒ 常量实现」，"
     "那是 2026-09-12 之前的旧状态）：现在**直接调引擎自己的 `ANM2::GetTexel`**"
     "（`runtime_constants.hpp` 的 `kSpriteGetTexelOffset = 0xC074`；HFA 传参与 `KColor` 走 `x8` 的 ABI "
     "经 `analysis/stage150-sprite-abi/` 三重核对，`confidence = verified`），"
     "取不到入口 / 精灵不可读 / 当前动画尚未建立时才回落到**不透明白色**（`g_SpriteGetTexelFallbacks` 记数）。"
     "偏离后果：只在兜底那几条路径上拿不到真值 —— EID 的 `IsAltChoice()` 此时会把道具当成"
     "「赎罪线红问号底座」，只画问号、不写名字与效果（正常路径已用引擎真值）。"
     "性质：debt（我们的欠账）——理由：底座已定位且已接上，只剩兜底路径没消 ⇒ 能还。"
     "判据：runtime/tests/test_lua_sprite.py（钉调用形状与兜底取值；未钉「兜底永不发生」——那条要真机数据）。"},

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
     "性质：debt（我们的欠账）——理由：单位已与 PC 对齐（毫秒），残留的只是起点参照（PC 是「OS 启动起」）；我们的 tick 基准是不是开机时刻还没取证 ⇒ 先取证再判，属能还的欠账。"
     "判据：runtime/tests/test_lua_isaac_table.py（**睡 30 毫秒之后它至少涨 20** ——"
     "秒口径会得到 0，那条断言就是为此写的；另加单调不减）。"},

    // 批次 017（2026-09-21）：`Isaac.ExecuteCommand` 原记为**平台降级**（"Switch 没有控制台"）。
    // ★ 批次 121（2026-09-25）改口径：那条前提**不成立** —— 控制台类与全部命令实现一直在镜像里
    //   （`Console::RunCommand` 一个函数 0x6070 字节；引擎只是从不实例化它：构造/Init/Update/Render
    //   的入边全是 0）。运行时现在自己建一个实例喂命令，**并返回控制台输出的字符串**。
    //   剩下的偏离只剩两条我们自己的限制 ⇒ 性质从 `NotInEngine` 改成 `Partial`（只实现了 PC 语义的一部分）。
    {0x0E01002D,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Isaac.md:106 「#### string ExecuteCommand ( string command )」"
     "PC 的 `Isaac.ExecuteCommand(command)` 把一行命令交给**游戏内置的调试控制台**（`Isaac.md:108`），"
     "返回**控制台输出的字符串**。"
     "★ 批次 121 起我们也是真实现：运行时自己构造 `IsaacRepentance::Console` 实例并调它的 `RunCommand`"
     "（类与命令实现都在镜像里，只是引擎从不实例化它），返回值就是这一段新增的输出字符串。"
     "残留两条限制：① 命令**超过 127 字节**会被拒绝（跨模块字符串走的是我们手工拼的经典布局，"
     "长串的数据放在自己的静态缓冲里 —— 上限由缓冲定）；② **当前没有玩家**时拒绝执行。"
     "偏离后果：上面两条限制下命令不生效、且返回空串（不是报错）—— ① 长命令（例如一口气带很多参数的"
     "`spawn`）会静默不执行；② 标题画面/菜单里调用一律无效（PC 那一侧同样没有玩家，但它的控制台仍在跑）。"
     "已知实例：GoodTrip 的 `TAB + R` 快速重开（`scripts/control.lua:61` 的"
     "`Isaac.ExecuteCommand(\"restart\")`）在 041~120 期间必然无效，批次 121 起**应当**生效——"
     "但真机尚未验证（验证判据见下面第一条）。"
     "性质：debt（我们的欠账）——理由：两条限制都是**我们自己实现里**的（跨模块字符串布局的工作量、"
     "以及「引擎在玩家为空时会读空指针」这条外部约束），不是平台缺件 ⇒ 至少第一条能还。"
     "判据：runtime/tests/test_console_bridge.py（钉字符串布局与长度上限的行为、以及状态面字段数契约）；"
     "runtime/tests/test_stage85_instant_restart_pc_bindings.py（钉 PC 绑定表里确实有 `ExecuteCommand` "
     "这条注册 —— 即 PC 侧的对应物是真的存在的）。"},

    // ---- `Entity` / `EntityPlayer` 的占位成员 --------------------------------
    {0x0E010017,
     ApiDeviationKind::Placeholder,
     "PC 契约：文档里没有 `EntityPlayer.GetData` 这一条"
     "★ 2026-09-21 更正（原写「`ModData` 结构没有证据 ⇒ 恒 nil」，那是批次 2 的旧状态）："
     "批次 4 起 `EntityPlayer:GetData()` 返回 **Runtime 自管的稳定表**（同一实体每次拿到同一张，"
     "模组写进去的值读得出来 —— EID 就是靠 `entity:GetData()[str] = value` 存自己的东西），"
     "只有**无效/过期句柄**才给 nil。"
     "偏离后果：与 PC 的差别只剩「按实体挂 mod 数据」那一层的实现方式（PC 是引擎的 `ModData` 结构），"
     "语义上模组读写的表是稳定的；少数依赖 PC 侧 `ModData` 特殊行为的用法才会不同。"
     "性质：debt（我们的欠账）——理由：差的只是与 PC 那一层的对齐，底座与稳定表都已就位 ⇒ 能还。"
     "判据：runtime/tests/test_lua_entity_player.py（钉「返回 Runtime 自管的稳定表」与「同实体同表」；未钉 PC 的 `ModData` 结构语义）。"},
    {0x0E010025,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Entity.md:344 「#### table GetData」"
     "★ 2026-09-21 更正（原写「⇒ 恒 nil」，那是更早的旧状态）：现在返回 **Runtime 自管的稳定表**"
     "（引擎**没有**这个字段，见 `api_catalog.cpp` 的 `0x0025` 目录注释），只有无效/过期句柄才给 nil。"
     "偏离后果：同 `EntityPlayer:GetData` —— 模组拿到的是一张稳定可写的表，"
     "与 PC 的差别只在「引擎 `ModData` 结构」那一层。"
     "性质：debt（我们的欠账）——理由：同 `EntityPlayer:GetData`，差的只是与 PC 那层语义对齐 ⇒ 能还。"
     "判据：runtime/tests/test_lua_entity_query.py（钉「同一实体稳定同表」与调用不报错；未钉 PC 的 `ModData` 语义）。"},
    {0x0E01001D,
     ApiDeviationKind::Placeholder,
     "PC 契约：文档里没有 `ItemConfig.HasTags` 这一条"
     "`ItemConfig:HasTags()`：`Item` 的 tags 字段偏移未定位 ⇒ 恒 false。"
     "偏离后果：靠 tags 分支的少数条目描述不出现。"
     "性质：debt（我们的欠账）——理由：`Item` 的 tags 位是引擎自己的字段（PC 文档里就有 `HasTags`），缺的只是偏移 ⇒ 可定位、可还。"
     "判据：runtime/tests/test_lua_item_config.py（钉恒 false；未钉真实 tags 位 —— 字段偏移未定位）。"},
    {0x0E01001E,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/ItemConfig_Item.md:23 「#### boolean HasTags」"
     "`ItemConfig_Item:HasTags()`：`Item` 的 tags 字段偏移未定位 ⇒ 恒 false。"
     "偏离后果：靠 tags 分支的少数条目描述不出现。"
     "性质：debt（我们的欠账）——理由：与 `ItemConfig:HasTags` 是同一条字段偏移，属「还没定位」而不是平台上没有。"
     "判据：runtime/tests/test_lua_item_config.py（钉恒 false；同上，字段偏移未定位）。"},
    {0x0E010029,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/EntityPickup.md:35 「#### boolean IsShopItem」"
     "`EntityPickup:IsShopItem()`：'商店商品'的判据没有证据（只有 `ShopItemId` 这个候选字段）"
     "⇒ 恒 false。偏离后果：商店里卡片/药丸相关的一条描述判断会偏保守。"
     "性质：debt（我们的欠账）——理由：台账已点名候选字段（`ShopItemId`），缺的是「怎么算商店商品」这条判据的取证 ⇒ 还能查、能还。"
     "判据：runtime/tests/test_lua_entity_query.py（钉恒 false 与调用不报错；未钉真实\"商店商品\"判据）。"},
    {0x0E010030,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:1185 「GetPill」"
     "`EntityPlayer:GetPill()`：按槽位读口袋的引擎字段（口袋数组偏移）未定位 ⇒ 恒 0"
     "（PC 上'空口袋'本来就是 0，EID 按 `id ~= 0` 判）。"
     "偏离后果：口袋里有药丸时缺一条口袋描述，但不会造成错误结论。"
     "性质：debt（我们的欠账）——理由：口袋槽数组是引擎自己的字段（PC 就直读它），缺的只是那个偏移 ⇒ 可定位、可还。"
     "判据：runtime/tests/test_lua_entity_player.py（钉槽位参数口径与恒 0 的返回值；未钉真实口袋数组 —— 偏移未定位）。"},
    {0x0E010031,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:882 「GetCard」"
     "`EntityPlayer:GetCard()`：口袋数组偏移未定位 ⇒ 恒 0。"
     "偏离后果：口袋里有卡牌时缺一条口袋描述，但不会造成错误结论。"
     "性质：debt（我们的欠账）——理由：同 `GetPill`：口袋数组偏移未定位，属能还的欠账。"
     "判据：runtime/tests/test_lua_entity_player.py（同上：槽位口径 + 恒 0）。"},
    {0x0E010048,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:1131 「#### string GetName」"
     "`EntityPlayer:GetName()`：名字来自存档、偏移未定位 ⇒ 恒 nil"
     "（EID 只做字符串拼接，nil 会被 `tostring` 兜住）。"
     "偏离后果：依赖真实玩家名的显示会缺内容、或被写成 nil 字样；但不会报错、也不会给出错误结论。"
     "性质：debt（我们的欠账）——理由：台账写的是「名字来自存档、偏移未定位」——是没定位，不是 Switch 侧没有名字 ⇒ 先定位再判，属能还的欠账。"
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
     "性质：design（主动保留的口径差异）——理由：快照口径是**我们主动选的**（让模组长期持有引擎内部 RNG 指针 = 给它开一个写已释放内存的口子），台账明确写了「为什么这样选」且没有值得做的补法 ⇒ 不打算改。"
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
     "性质：debt（我们的欠账）——理由：那三个 `IsAvailable` 的函数本体在镜像里、我们也已经在调它，缺的是 flags 各 bit 的语义（可继续取证）⇒ 属「实现得偏保守」的欠账。"
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
