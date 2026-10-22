#include "interfaces/lua/api_deviation.hpp"

namespace isaac::runtime {
namespace {

// 每条都对应实现处的一段注释（"占位/未定位/语义偏差/恒假/常量实现"），这里只做汇总与索引。
// 顺序按 catalog id，方便与 `api_catalog.cpp` 对照
// （★ 例外：批次 128 那 27 条**恒值接口**作为一个整段追加在表末 —— 它们是同一件事的成批登记，
//   单独成段比拆散进各家族更好复核；段落开头有完整说明）。
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
    // 2026-10-09更正：HUDOffset真实字段及PC setter已恢复，旧偏离全文归档
    // dist/offline-repairs-20261009-hud-offset/api_deviation.cpp.before；不再作为现存欠账。


    // ---- `Game` / `Seeds`（字段直读）------------------------------------------------
    //
    // ★ 批次 195（2026-09-29）：这一族**四条偏离全部还清、条目删除** ——
    //   `Game:GetSeeds`（`0x02010008`）、`Game:GetVictoryLap`（`0x02010009`）、
    //   `Seeds:IsCustomRun`（`0x0F010001`）、`Seeds:GetStartSeed`（`0x0F010002`）。
    //   它们原来登记的都是"字段偏移尚未定位 ⇒ 返回自洽/固定值"（性质 `debt`，是**能还**的欠账）。
    //   偏移已经指令级定位（证据规格 `analysis/api-restore-game/spec.json`，逐条抄进
    //   `runtime_constants.hpp`）：
    //     * `Game:GetVictoryLap()` = `Game + 0x26FD50`（写它的就是 `Game::NextVictoryLap`，另有五个读者）；
    //     * `Seeds` 对象**内嵌**在 `Game + 0x25D40`；`GetStartSeed()` = `+0x25D44`（`Seeds+0x4`）、
    //       `IsCustomRun()` = `Game+0x25D40` 那一个字节（三处写 / 三处读互相印证）。
    //   ⇒ 四条现在读的都是引擎真值，条目从台账移除（这就是"还清"的形态，与批次 177 同例）。
    //   ⚠️ `Seeds:IsCustomRun()` 的**挑战局那一半仍是推断**（PC 文档写"挑战局或带种子的局"，
    //   而镜像里写那一字节的只有控制台 `seed`/角色选择输入/`StartDebug` 三处）⇒ 本轮**只读那个
    //   字节**，等真机三点读数（普通局 / 输入种子局 / 挑战局）钉死或推翻。那一半属"未取证"，
    //   不是"我们做了个别口径"⇒ 按纪律**不登记**为主动偏离（登记的是取舍，不是问号）。

    // ---- `Input` -------------------------------------------------------------
    {0x09010004,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Input.md:73 「#### boolean IsActionTriggered」"
     "（正文 `:75`：引擎答「这一帧刚按下」；一次按下只答一次，同一个 update cycle 内问多少次都一样）。"
     "Switch 引擎里**没有**这个语义可以复用 —— 两条候选都用不了（批次 221 用 `tools/nro_disasm.py`"
     "反汇编本机镜像定案）：① `ManagerBase::IsActionTriggered @0x4F9A64` → 设备"
     "`InputDeviceBase::IsActionTriggered @0x4F775C` **只遍历该动作绑定的按钮**（全程不看模拟量）"
     "⇒ 摇杆推出来的方向动作在这条路上**永远为假**（批次 107 那次读数「`IsActionPressed` 为真、"
     "`IsActionTriggered` 一次都不真」就是这么来的；当年误判成「引擎的上升沿状态在模组的时机里是空的」）；"
     "② 设备 `InputDeviceBase::IsButtonTriggered @0x4F7558` 测的是数据成员 `+0x38`，而"
     "`InputDeviceBase::Poll @0x4F70B0` 每帧开头就是 `ldr x8,[x0,#0x30] ; str x8,[x0,#0x38]`"
     "⇒ `+0x38` = **上一帧**的按钮位图 ⇒ 它的语义是「连续两帧都按着」（引擎自己拿它做**连按**："
     "`Menu_Title::Update` / `Console::check_key_autorepeat`），不是 PC 的「刚按下」。另外 NX 本体"
     "**连模组回调系统都没有**（批次 151：整份镜像里 `AddCallback`/`RunCallback`/`MC_*` 出现 0 次）"
     "⇒ `MC_INPUT_ACTION` 当时也没有游戏侧派发点可接。 ★ 2026-10-07（批次 390）**已更正**：它现在**已接线**（挂 `KAGE::Input::ManagerBase::IsActionPressed/IsActionTriggered/GetActionValue` 三条入口中继 + `LuaRuntime::DispatchInputAction` 用返回值覆盖），见 `hook_catalog.hpp` 的 `ManagerIsAction*` 段。"
     " ★★ 2026-10-07（批次 392）**又纠正一处（会咬人的）**：Lua 的 `Input.*` 绑的 `0x3F9B6C`"
     "（符号 = `IsaacRepentance::Manager::IsActionPressed`）**尾跳**进上面那三条，而**引擎本体**"
     "（`Entity_Player::get_movement_input` / `control_shooting` / 各菜单）也走同一个符号 ⇒ 中继会"
     "**连带拦到 Lua 自己的读取**：MCM 菜单可见时那句「冻住角色」的 `return false` 把它自己的光标"
     "读输入也答成 false（用户报「摇杆推不动光标」）。修法 = 我们这侧走**直读壳**"
     "（`LuaRuntime::RawEngineInputQueryScope` + `lua_runtime.cpp` 的两个壳），中继见标记就跳过派发。"
     " ★ 2026-10-07（批次 393）：回调的 `buttonAction` 改成**模组（PC）口径**的号"
     "（`input_action_map.hpp` 的反表）—— 原先直接给**引擎内部号**；`ACTION_MAP=13` 两张表恰好同号"
     "（所以 minimapi 一直无恙），而 `16..23` 那段**整体错开 3**。"
     "⇒ 本 Runtime 改用**自己算的上升沿**，原语 = 引擎的 `IsActionPressed`（含模拟量，与 PC 同形）。"
     "★ 判据形状与 PC 对齐：**同一帧内同一个答案**（批次 109）、**一次按键只报一次**。"
     "★★ 批次 221（2026-09-30）**把「松手去抖窗口」整个删掉**（批次 110 加的、220 从 6 调到 20 的那个常量）："
     "那个窗口是**猜一个时长**，而它两侧都会咬人 —— 窗口小 ⇒ 引擎的「按住」在按着的时候断一下就"
     "被当成新手按下 ⇒ 用户报的「**一次输入 = 好多次**」；窗口大 ⇒ **真实松手再按**（间隔短于窗口）"
     "被并成一次 ⇒ 用户报的「**按着没反应**」。**2026-09-30 用户报的正是两侧同时存在**"
     "⇒ 说明「猜一个时长」这条路本身不成立，继续调数字只是把痛点来回挪。"
     "现在改成**引擎帧边界上的严格相邻帧差分**（只有 `本帧 == 上一次采样 + 1` 才算有历史）："
     "模组每帧都问（MCM 每帧问全部动作）⇒ 状态连续 ⇒ **不需要任何窗口**；"
     "某帧没问、或帧号回退 ⇒ **不报边沿**（保守那一侧，宁少报不误报）。"
     "同时把两个会产生「假闪断」的源头修掉：① 帧号改成**单一来源**"
     "（`CurrentInputFrame()`：只用引擎帧计数，**取消**「毫秒 ÷ 4」兜底 —— 两个刻度混用会让帧号往回跳，"
     "`frame - last` 的无符号减法溢出 ⇒ 误报边沿，这是批次 220 前最隐蔽的一条）；"
     "② 输入设备表**每帧只读一次**（原来每次查询都读，MCM 每帧 140 次查询 ⇒ 读失败会伪装成「按住闪断」）。"
     "★★ 批次 380（2026-10-06）：**把「必须严格相邻帧」（`本帧 == 上一次采样 + 1`）也取消**。"
     "真机读数量到游戏给**渲染回调**的次数比**更新回调**少：同一会话 `MC_POST_UPDATE` **46026** 次、"
     "`MC_POST_RENDER` **43519** 次（游戏侧入口计数同形：46605 / 44088）；跨两次读数算增量"
     "（真实游玩那段）：更新 6308 / 渲染 5966 ⇒ 比例 **0.946** ⇒ **约 5.4% 的更新帧没有渲染帧**。"
     "而帧号的**唯一真源**是「每派发一次 `MC_POST_UPDATE` 加一」⇒ **在渲染回调里每帧都问**的模组"
     "（MCM 的中文版就是）会遇到：按下发生在**没有渲染帧的那次更新**上，下一次问到时帧号已跳 2，"
     "批次 221 的判定就把这整次按下**吞掉**。PC 上不存在这个形状（PC 的更新与渲染在同一个 frame 成对发生）"
     "⇒ 「严格相邻帧」不是 PC 语义，而是**我们这套挂点结构的产物**被写进了判定。"
     "现在改成：**上一次采样到「没按住」、这一次「按住」就报**（`pressed && !held`），只保留"
     "「第一次采样不算边沿」这一条保守约束；判定**不再做任何帧号算术** ⇒ 帧号回退/跳变在结构上"
     "不可能再误报（帧号现在只用于诊断）。"
     "偏离后果：① 一次按键整段落在两次采样之间（按下与抬起都没被采到）会漏一帧；"
     "② 引擎的「按住」若真的在按着的时候断帧，会**如实多报**一次边沿 —— **不再用窗口掩盖**，"
     "要修的是源头（读数里的 `g_InputReleaseRunPeak` / `g_InputEdgeGapMin` 会把这种闪断量出来："
     "贴近 2~3 帧 ⇒ 闪断；几百帧 ⇒ 用户真松手）；"
     "③ **极少问** `IsButtonTriggered` 的模组（例如每个房间只问一次）可能拿到一次「迟到」的边沿 ——"
     "PC 的语义是「**这一次 update** 里刚按下」，我们的是「**自这个调用方上一次问过以来**刚按下」；"
     "对**每帧都问**的模组（契约要求的正常用法，MCM / EID / GoodTrip 都是）两者逐帧一致。"
     "性质：debt（我们的欠账）——理由：引擎侧确实没有这个语义（已取证），"
     "而「拿引擎的按住状态求相邻帧差分」是**我们自选的口径**，它与 PC 的差别只剩上面两条、且都可量。"
     "复测（每次动输入都要做）：① 菜单里摇杆推一下 = **一格**；② 快速连按**还能翻**。"
     // ★★ 批次 230（2026-09-30）：**动作号本身也要翻译** —— PC 的 `ButtonAction` 与 Switch 引擎的
     //   **内部**动作表不是同一张。PC 里 `ACTION_MENULEFT = 20`，而 Switch 引擎里 **20 = "菜单下"**
     //   ⇒ 原来把模组给的号**原样**递给引擎时，推摇杆"下"会让引擎把 `ACTION_MENULEFT(20)` 也答成
     //   "按住" ⇒ 中文版 MCM 的导航链（下 → 上 → 右 → **左**，后判覆盖前判）把"下"改写成"左"
     //   （用户 2026-09-30 实测："摇杆向下推不能正常向下选择"）。
     //   逐行证据与口径在 `interfaces/lua/input_action_map.hpp`（设备层按号直接取 @0x4F76A8、
     //   管理器层不翻译 @0x4F9920、引擎自己的菜单用 17..20 @0x40D770、默认按键表 `s_ButtonMap`、
     //   16 = `JOINMULTIPLAYER`（`SpawnCoPlayer` @0x43E700）、批次 222 的真机摇杆读数）。
     //   ★ Switch 引擎只有 24 个内部动作 ⇒ `FULLSCREEN(16)/MUTE(17)/RESTART(18)/MENURT(27)/
     //     EMOTES(30)/CONSOLE(32)` 这些 PC 才有的动作**由我们恒答 false / 0**（连引擎都不问）。
     //     这不是"把没按与没有混为一谈"：读数里的 `g_InputActionMapAbsent` 会把这种回答计数。
     //   本条覆盖**三条**入口（本条的 `IsActionTriggered`、以及 `Input.IsActionPressed` /
     //   `Input.GetActionValue` —— 它们都是同一条查询链）。
     //   偏离后果（新增这一条）：① 模组若用 PC 上存在、Switch 上不存在的动作号，会**恒得到
     //   false / 0**（不报错、不崩，只是那条分支不执行）；② 契约页在 24..29 上自己矛盾
     //   （`MENULB/MENULT`、`MENUTAB/MENUEX` 各占同一号），我们取"Switch 上真的存在的那一个"
     //   ⇒ 按 AB+ 口径把它们当扳机/`MENUEX` 用的模组会拿到**肩键/X**的答案（那三行碰不到方向四向，
     //   不会再现"下变左"这一类用户可见缺陷）。
     "判据：runtime/tests/test_input_action_translation.py"
     "（表逐行 + 消费者视角：推\"下\"必须让 `ACTION_MENUDOWN(23)` 为真、`ACTION_MENULEFT(20)` 为假，"
     "并反向自证\"不翻译时推下会被读成 LEFT\"）；"
     "判据：runtime/tests/test_input_action_edge.py（钉边沿语义的每一条：首帧不算边沿、同帧同答案、"
     "松开一帧再按就是新边沿、**隔帧期间发生的新按下要报出来**（批次 380：渲染帧比更新帧稀）、"
     "隔帧但仍按住不报、**帧号回退不误报**、分槽、间隔诊断、重置；"
     "并钉住「窗口没有被加回来」与「设备表每帧只读一次」）；"
     "★★★ 批次 381（2026-10-06）：**取消「由调用方询问节奏决定」这条最后的口径** —— 边沿改成"
     "「**引擎帧上的一次事件、只在那一帧有效**」。（旧口径为什么不行，见交接文档"
     "`docs/会话交接-20261006-一-输入边沿机制与批次380回归.md` §4.3：中文版 MCM 的"
     "`actionsDown/Up/Left/Right` 同时含移动动作与菜单动作，而 `inputhelper.lua` 的"
     "`MultipleActionTriggered` **碰到第一个为真的就 return** ⇒ 排在后面的动作号当帧不被问 ⇒"
     "批次 380 的「自上次询问以来」判定在下一帧把它认成新按下 ⇒ 光标再走一格（用户报的"
     "「一次推动走两格」）；`modconfig.lua:2259` 的 `MultipleButtonTriggered(ignoreActionButtons)`"
     "闸门同理 ⇒ 十字键又驱动了菜单。⇒ 批次 380 的判定**仍然让调用方节奏决定答案**，"
     "只是把「窗口」换成了「自上次询问以来」。）"
     "新语义（采样 + 纯读判定）：每帧在**帧号自增之后、派发回调之前**由 `SampleInputFrame()`"
     "主动采一次（钩子 = `isaac::runtime::SetFrameBoundaryHook`，由输入层在"
     "`ResetInputEdgeState()` 里装）；采样集合有界：按键号 0..17 全采、动作号 0..31 全采，"
     "× 设备表里**真实存在**的手柄 ＋一份「任意设备」（`0xFFFFFFFF`）聚合；"
     "**按键侧**直接用引擎对象里的 `+0x30`（本帧位图）/`+0x38`（上帧位图）算 `本帧 & ~上帧`"
     "⇒ 一次引擎调用都不用，天然与 PC 同形；**动作侧**每帧对每个动作号调一次引擎"
     "`IsActionPressed`，`prev` 由我们每帧存一份（与调用方无关）；"
     "判定 = 纯读：`Triggered = (记录的边沿帧号 == 当前帧号)`，**不做帧号算术、不做窗口、"
     "不做相邻帧要求**；同一帧内问多少次都一样，**下一帧一律 false**。"
     "A2（同批做、可拆）：`IsButtonPressed` / `IsActionPressed` 对采样集合内的"
     "(按键号/动作号, 设备) 也答**同一次采样的值**（PC 上「按住」与「边沿」本来就是同一次 Poll"
     "出来的）；采样记录缺这一帧时**回退现查**（不引入新风险）。若真机验收中 GoodTrip 地图 /"
     " MCM 长按连翻 / 控制台 `A+B` 长按任何一项出现变化，就把 A2 拆出去单独一批"
     "（A1 独立上卡）。"
     "偏离后果（批次 381 起）：① 采样集合之外的 (code, controller) 组合没有记录 ⇒ 按「没按」答"
     "（键盘码、越界号、Switch 上没有的动作号本来就是这个结果）；② 采样集合有界 ⇒ 每帧引擎调用"
     "约 32 次（真机 1 台手柄，动作侧 32 个号；按键侧 0 次），实测值由 `g_InputSampleCalls` 报出；"
     "③ 诊断量语义变了：`g_InputEdgeGapMin/Last` 现在是「相邻两次边沿隔了几帧」，"
     "`g_InputReleaseRunPeak` 现在是「最长连续没按住」。"
     "性质：debt（我们的欠账）——理由：引擎侧确实没有 PC 语义的「刚按下」（已取证），"
     "现在的偏离只剩**平台缺件**（键盘设备不存在、没有模拟扳机；★ 2026-10-07 批次 390 起 `MC_INPUT_ACTION`**已接线**、不再算缺件；★ 同日批次 392 给它补了「Lua 侧直读」、批次 393 补了「`buttonAction` 反译成模组口径的号」）"
     "与**采样有界**，且都可量。"
     "判据：runtime/tests/test_input_action_edge.py（已按新语义重写：同帧一致、下一帧 false、"
     "一次推动两个动作号的「走两格」回归、十字键闸门的回归、按住跨帧不报、首帧不算边沿、"
     "任意设备聚合、帧号跳变不误报、设备表失败答 false，以及**反向自证旧规则必须红**）。"
     "runtime/tests/test_lua_input_binding_abi.py（端到端：按住→松开→再按住）。"
     "★★★ 2026-10-07（批次 403）：**按键侧采样换源 —— 从「读设备对象 `+0x30`」改成「逐个问引擎」**。"
     "原因（真机读数定案）：`dist/gdb-read-20261007-1732-after-fire-stick.txt`（8523 帧、用户正在玩）"
     "里，按键 0/1/2/3（十字）与 4（A）、14（减号）的 `lastEdgeFrame` 是活的"
     "（5711/5687/5735/5758、1239、117），而 **5..13 与 15..17**（B/X/Y/L/ZL/两摇杆按下/R/ZR/+）"
     "**从未答过按住**、`g_InputButtonEdgeCounts` **一次都没报过**；而引擎自己对 code 13 能答 true"
     "（批次 380 = 查询时现问引擎，真机读到 `g_InputButtonEdgeCounts[13] = 3`、用户实测 MCM 能开）。"
     "★ 这是**按位位置的规律**（0..4 与 14 活、5..13 与 15+ 死），不是「用户按过哪些键」的规律"
     "⇒ **那一格不是引擎用的按键位图**。改法：采样器的按键侧改成对每台手柄的按键号 0..17"
     "**逐个问引擎**（`LuaRuntime::InputIsButtonPressedThunk()` + `ResolveButtonQuery(&manager,&method,…)`"
     "+ `LuaRuntime::ValidateInputIsButtonPressedBinding(method)` —— 与 `Input.IsButtonPressed` 的"
     "回退分支**同一枚入口**），再把 18 个布尔喂给 `g_ButtonEdge.SampleRow`。"
     "**判定语义一个字都没改**：第三个实参仍是 `nullptr`（边沿 = `InputFrameEdges` 按它自己上一帧的"
     "`held` 差分，一帧一份、与调用方询问节奏无关），`Triggered`/`Pressed` 仍纯读。"
     "这条**不动**上面「引擎侧没有 PC 语义的刚按下、改用我们自己的边沿表」的既有口径（那半原样有效）。"
     "偏离后果（新增这一条）：① 采样代价从「按键侧 0 次/帧」变成 `18 × 手柄数`，"
     "与动作侧相加后真机单手柄约 42..50（上限 50），由 `g_InputSampleCalls` 报出；"
     "② 采样解析不到引擎按键绑定 / 设备表读不到时，该帧按键侧**全答 false 并计失败**"
     "（`g_InputSampleFailures`），**绝不抛错**（该模块 `-fno-exceptions`）；"
     "③ `Input.IsButtonPressed` 的 A2 路径（本帧有采样记录 ⇒ 读采样里的 `held`）因此对"
     "B/X/Y/L/R/ZL/ZR/摇杆按下也**开始答对**（换源前那一段恒 false）；回退分支（`HasFrame` 不成立时"
     "现查引擎）原样保留。判据：runtime/tests/test_input_button_edge_source.py"
     "（源码级：`SampleInputFrame` 体内出现 `InputIsButtonPressedThunk` / `ValidateInputIsButtonPressedBinding`、"
     "且**不再出现** `kKageInputDeviceKeysCurrentOffset`；行为级：用假按键查询驱动**真实** `SampleInputFrame`，"
     "code 13 从「没按住」变「按住」的那一帧 `Triggered` 为真、下一帧为假）。"},

    // 批次 017（2026-09-21）：以下两条**平台降级**此前只写在 `api_catalog.cpp` 的目录注释与
    // `input_api.cpp` 的实现注释里（原话就是"平台限制"），一直没被收进本表 —— 于是"平台固有"
    // 这一类在台账里是空的，分栏也就没有意义。本次照抄实现处的结论与后果，未新增语义判断。
    //
    // ★★ 批次 195（2026-09-29）：`0x09010007`（`Input.GetMousePosition`）**偏离已还清、条目删除**。
    //   它原来登记的是"`gameCoords` 参数被忽略，两种取值返回同一个值"（`debt`）。现在两种取值
    //   **都按 PC 语义**实现（PC 处理函数反汇编 + `Room[0x1938]` 反推）：
    //     * `gameCoords = false` ⇒ **窗口像素**（PC 的 "render coordinates" 就是窗口像素；
    //       Switch 上触摸面板与 framebuffer 同尺寸 ⇒ 原始触摸读数 0..1280）；
    //     * `gameCoords = true`  ⇒ **世界坐标** = `Isaac.ScreenToWorld(原始触摸读数)`
    //       （新增的 `0x0E01005F`）。
    //   ⇒ 模组那条经典组合 `Isaac.WorldToScreen(Input.GetMousePosition(true))` 现在**两侧都是真变换、
    //   互为逆运算**（旧实现是"两个恒等凑出来恰好对"，已随两条真实现一起消失）。
    //   ⚠️ 批次 193 的 `×0.375` 硬编码**是错的**：0.375 = 480/1280 是"画布"系数，而**掌机的渲染平面
    //   是 426×240**（系数 426/1280 = 0.3328，且 `s_OrthographicProjection*` / WIDTH / HEIGHT /
    //   POINTSCALE 都是**运行期全局**，`ResizeWindow` 会改）⇒ 一律不硬编码，运行期从引擎全局读。
    //   判据：`runtime/tests/test_touch_pointer.py`（含
    //   `test_the_world_coord_deviation_is_coupled_to_worldtoscreen` 的改写说明）、
    //   `runtime/tests/test_goodtrip_batch_a.py`。
    {0x09010008,
     ApiDeviationKind::NotInEngine,
     "PC 契约：tools/pc_contract_docs/Input.md:121 「#### boolean IsMouseBtnPressed ( [Mouse](enums/Mouse.md) button )」"
     "PC 的 `Input.IsMouseBtnPressed(Mouse)` 回答「**某一个**鼠标键现在按着没有」（`Input.md:123` 列了"
     "左右键、滚轮、侧键）。**现状（2026-09-28 批次 192 起）**：语义由用户定为「手指在屏幕上 = 左键"
     "按下」⇒ 只要屏幕上有手指就返回 **true**，没有就 false；参数仍照 PC 要求校验（`Mouse` 枚举）。"
     "偏离后果：**不区分是哪个键** —— 模组问右键 / 滚轮 / 侧键，得到的与问左键**同一个答案**"
     "（PC 上这几者是独立的）；把「右键按下」当成一个独立事件去分支的模组会误触发。"
     "不抛错是硬要求 —— 它被每帧的鼠标状态跟踪调用，抛错会让整条回调被派发器摘掉。"
     "性质：debt（我们的欠账）——理由：★ 2026-09-28 批次 192 **改档**（同 `GetMousePosition`）："
     "指针源已经有了（触摸屏），剩下的欠账是**把多个键位映射开**（触摸屏本身只给一个「按下」，"
     "要区分左右键得像 PC 那样另找输入源或约定手势），属还能继续做的工作、不是平台固有。"
     "判据：runtime/tests/test_touch_pointer.py、runtime/tests/test_goodtrip_batch_a.py。"},
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
    // ★ 批次 195（2026-09-29）：`0x03010003`（`Level:GetCurses`）偏离**已还清、条目删除** ——
    //   它原来登记的是"只返回 `Level + 0x0C` 的原始位，②③两步未定位"（`debt`）。现在三步都做了：
    //   `raw | Game::GetSpecialSeedPermanentCurses() & ~Game::GetSpecialSeedBannedCurses()`
    //   （引擎 `Level::GetCurses @ 0x3D57CC` 全体指令；两个访问器的偏移与 16 字节入口守卫
    //   仓库里本来就有，只是以前只被探针用）。普通局里两个访问器都返回 0 ⇒ 与旧值相同；
    //   带种子/挑战局里合成值会与 raw 不同 —— 那正是 EID 的 `hasCurseBlind()`（判 `0x40`）
    //   过去误判的那些局面。判据：`runtime/tests/test_lua_entity_query.py`（读的是 `Level + 0x0C`）
    //   + 真机读数的 `[14]` 那一行（`raw`/`permanent`/`banned`/两个访问器是否真的被调到）。
    //   ⚠️ 两个 callee 的**身份**仍是推断（文件镜像的 GOT 是惰性绑定桩，无法独立复核）——
    //   引用仓库既有证据（`runtime_constants.hpp` 那两条常量）。

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

    // 2026-10-15：0x0D010015的历史Partial条目已销账，原文保留在
    // dist/bossbar-restore-20261015/source-before/runtime/src/interfaces/lua/api_deviation.cpp。
    // Preload2解析DefaultAnimation，Load2复制至ANM2+0x18；现读真实字段，非表首近似。

    // ---- `Seeds`（批次 214：中文版 MCM 开菜单那条路上要的三条）----------------------
    // `Seeds:HasSeedEffect`（`0x0F010004`）是**真实现**（走引擎那棵 `std::set<eSeedEffect>` 的树查找），
    // 不在这里；下面两条是**按设计不生效的空实现**。
    {0x0F010005,
     ApiDeviationKind::NotInEngine,
     "PC 契约：文档里没有 `Seeds.AddSeedEffect` 这一条（两个 MCM 变体的 `OpenConfigMenu()` 都在调，"
     "但它是 REPENTOGON 加的；`tools/pc_contract_docs/Seeds.md` 里查不到）。"
     "引擎侧取证（2026-09-30 反汇编）：`Seeds` 里**生效中的种子效果**是一棵 `std::set<eSeedEffect>`"
     "（`Seeds + 0x58` 起，布局见 `kSeedsEffectTreeOffset` 那一族）——所以读取有真值来源；"
     "但引擎里**唯一**的增删入口吃的是**名字字符串**"
     "（`Seeds::AddSeedEffect(std::string) @0x4A1270` / `RemoveSeedEffect(std::string) @0x4A137C`），"
     "而「枚举 → 名字」的唯一函数 `Menu_SpecialSeed::GetSeedName(eSeedEffect) @0x417ADC` 读 `this+0x1a0`、"
     "是**非静态成员**（要一个 `Menu_SpecialSeed` 实例，我们拿不到），镜像里也搜不到那批名字串"
     "（`SEED_NO_HUD` / `NO HUD` 都没有）⇒ **没有可信的实现路径**，给空实现。"
     "偏离后果：调它之后**那个种子效果不会被加上**。"
     "为什么宁可不生效也不抛错：MCM 的 `OpenConfigMenu()` 里这一行**不在 `pcall` 里** ⇒ 抛错会把"
     "**开菜单那条路径当场打断**（症状与「菜单画不出来」完全一样）；而「没隐藏 HUD」只是一个视觉特性"
     "（MCM 同时还会调 `HUD:SetVisible(false)`，那条是真的）。"
     "不是静默假成功：调用次数记在探针 `g_SeedsEffectWriteAttempts` 上（读数工具会打印）。"
     "性质：platform（平台固有）——理由：能定位的底座都已经定位（枚举与树都在），"
     "缺的是「引擎里那条函数要一个我们取不到的实例、镜像里也没有那批字符串」⇒"
     "继续投入也消不掉，只能登记。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（宿主夹具里造一棵两结点红黑树，让 `HasSeedEffect` "
     "走遍四条查找路径；并断言这两条**不抛错**、参数形状仍要严、探针计数恰好 2）。"},
    {0x0F010006,
     ApiDeviationKind::NotInEngine,
     "PC 契约：文档里没有 `Seeds.RemoveSeedEffect` 这一条（同上，REPENTOGON 一侧）。"
     "依据与取舍逐条同 `0x0F010005`（增删在引擎里是同一个入口族、都吃名字字符串，"
     "`RemoveSeedEffect(std::string) @0x4A137C`）。"
     "偏离后果：调它之后**那个种子效果不会被摘掉**（MCM 的 `CloseConfigMenu()` 用它恢复 HUD）。"
     "性质：platform（平台固有）——理由：与上一条同源 —— 引擎里增删种子效果是同一个入口族、都吃"
     "名字字符串，而「枚举 → 名字」那条路同样断在「转换函数是非静态成员、镜像里也没有那批名字串」上"
     "⇒ 继续投入也消不掉，只能登记。"
     "判据：runtime/tests/test_lua_api_gap_batch3.py（与上一条同一组断言：不抛错、参数形状要严、"
     "探针计数恰好 2）。"},

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
     "★ 2026-10-10：127 字节人为限制已移除，短命令内联、长命令在同步调用期借用原输入指针，"
     "引擎先复制再分词，不跨模块释放；128 字节、1KiB、64KiB与嵌入NUL均由公共执行层模拟入口核实。"
     "残留限制：**当前没有玩家**时拒绝执行。"
     "偏离后果：标题画面/菜单里调用仍无效、且返回空串（不是报错）；"
     "PC 那一侧同样没有玩家，但它的控制台仍在跑。本批只销长度欠账，不代表整个API已完全与PC一致。"
     "已知实例：GoodTrip 的 `TAB + R` 快速重开（`scripts/control.lua:61` 的"
     "`Isaac.ExecuteCommand(\"restart\")`）在 041~120 期间必然无效，批次 121 起**应当**生效——"
     "但真机尚未验证（验证判据见下面第一条）。"
     "性质：debt（我们的欠账）——理由：无玩家限制来自本实现对引擎空玩家解引用的保护，不是平台缺件。"
     "旧记录全文保存在dist/console-long-command-20261010/api_deviation.cpp.before。"
     "判据：runtime/tests/test_console_long_commands.py（公共执行入口的长串、原文、生命周期与拒绝保护）；"
     "runtime/tests/test_console_bridge.py（钉字符串布局、有界复制助手与状态面字段数契约）；"
     "runtime/tests/test_stage85_instant_restart_pc_bindings.py（钉 PC 绑定表里确实有 `ExecuteCommand` "
     "这条注册 —— 即 PC 侧的对应物是真的存在的）。"},

    // 2026-10-10：GetData两条历史占位欠账已按PC Remove/D2寿命还清。
    // 原逐字记录：dist/entity-lifecycle-static-20261010/api_deviation.cpp.before。
    // ★ 批次 195（2026-09-29）：`0x0E01001D`（`ItemConfig:HasTags`）与 `0x0E01001E`
    //   （`ItemConfig_Item:HasTags`）两条偏离**已还清、条目删除** —— 它们原来登记的是
    //   "tags 字段偏移未定位 ⇒ 恒 false"（`debt`，属"能还"），现在偏移确证在
    //   `ItemConfig::Item + 0xC0`（**u64、33 位**，写点唯一 + 三个读者 + 8 字节清零），
    //   口径 = 引擎自己三处同形的"任一命中" `(Tags & mask) != 0`。
    //   ⚠️ 旧常量指的 `+0x58` 其实是 items.xml 的 `maxhearts=` —— 见
    //   `runtime_constants.hpp` 的 `kItemConfigItemTagsOffset`（那里逐条写了证据）。
    //   判据：`runtime/tests/test_lua_item_config.py`（夹具在 `+0x58` 放诱饵、在 `+0xC0` 写 8 字节，
    //   并各钉一条"命中"与"不命中"）。
    // ★ 批次 201（2026-09-29）：`0x0E010029`（`EntityPickup:IsShopItem`）的偏离**已还清、条目删除**。
    //   它原来登记的是「'商店商品'的判据没有证据（只有 `ShopItemId` 这个候选字段）⇒ 恒 false」，
    //   性质 `debt`（属"能还"）。现在判据确证 = **`Price != 0`**（`Entity_Pickup + 0x564`）：
    //   ① `Entity_Pickup::SetPrice(int)` @ `0x26B1C8` 的**首条指令**就是 `str w1, [x0, #0x564]`；
    //   ② `CanPickupShopItem` @ `0x271700` 反复拿 `+0x564` 做价格分支（其中与 `-10` 比较正对上
    //      isaacscript `PickupPrice` 的 `DEVIL_SACRIFICE_SPIKES`）；
    //   ③ `MakeShopItem` @ `0x270FC4` 先读 `+0x564`（`Price == 0` 才算"还没定价"）、再写 `+0x56C`；
    //   ④ isaacscript `PickupPrice` 文档：非卖品 `Price` 恒为 0。
    //   ★ 当初卡住是**盯错了字段** —— `ShopItemId` 的默认值就是 0，判不了"是不是商店商品"。
    //   判据：`runtime/tests/test_lua_entity_query.py`（同一房间一个 `Price == 15` 的 pickup 必须答
    //   true、一个 `Price == 0` 的必须答 false ⇒ 同时挡掉"恒 false""恒 true""误用 `ShopItemId`"）。
    // ★ 批次 177（2026-09-28）：`0x0E010030`（`GetPill`）与 `0x0E010031`（`GetCard`）两条偏离
    //   **已还清、条目删除** —— 引擎里有同名成员函数（`Entity_Player::GetPill(int) const`
    //   @ `0x2E8D80` / `GetCard(int) const` @ `0x2E8D58`），现改走引擎方法数据行，值来自引擎自己。
    //   证据与口径见 `runtime_constants.hpp` 里那两条常量、与 `isaac_api.cpp` 的
    //   `kEntityPlayerEngineRows`；"旧假桩已删"由 `runtime/tests/test_id_argument_policy.py` 钉。
    // 2026-10-09：GetName 已改为引擎配置表真值；旧偏离逐字保存于本轮记录。
    // 批次 13（2026-09-16）新增。
    // 2026-10-09：0x0E010054已恢复原生RNG引用，旧快照记录全文归档rng-references/api_deviation.cpp.before。
    // 批次 316（2026-10-03）新增：与上面那条 `GridEntity:GetRNG` **同一条取舍**（快照 vs 活引用）。
    // 2026-10-09：0x0E0100DB已恢复原生RNG引用，旧快照记录全文归档rng-references/api_deviation.cpp.before。


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

    // =====================================================================================
    // 批次 128（2026-09-25）：**恒值接口**（"安全桩"）成批登记
    // =====================================================================================
    //
    // 起因（用户裁定「做前先确定实现流水线没问题」）：接口面有一批处理器**什么都不读、直接编一个值**
    // （恒 0 / 恒 false / 空表 / 恒 nil）。它们此前只写在实现处注释里、或只进
    // `tools/lua_api_stub_ledger.json` —— 而真机读数打印的「风险面」**只认这张台账**，
    // 于是"模组踩上去时现场看不见它"。098 的教训（`GetGridPath` 恒返 1000，台账登记过但
    // 后果那栏写错）说明：**进这张表**才是"会被看见"。
    //
    // 登记口径与前面各条一致：照抄实现处注释里已经承认的事实，**不新增语义判断**；每条都点名
    // 一个现存测试文件 —— 本轮同时把几处「只钉类型」的断言改成「钉住那个常量本身」
    // （证据与逐条说明见 `dist/change-archive-20260925/128-constant-value-api-registration/README.md`）。
    //
    // 性质一律 `debt`：这一批的共同点是**底座在引擎里（或可从存档/资源里取到），只是还没定位**，
    // 与 `platform` 那两条（鼠标）有本质区别 —— 那些是平台上真的没有。
    //
    // ★ 2026-09-25（批次 130）**已修**：本段登记时一并查见两处**比 PC 严**（抛错 ⇒ 派发器静默摘掉
    //   整条回调）—— `EntityPlayer:GetPoopSpell` 曾要求**无参**（PC 的签名带 `int Position`）、
    //   `EntityPlayer:HasTrinket` 曾要求**正好一个参数**（PC 的 `IgnoreModifiers` 可省；语料里的
    //   `analysis/mod-corpus/TBOI_Better-Voiding/main.lua:508`/`762` 就传了两个）。
    //   两处都改成"接受 PC 的可选参数"；`test_id_argument_policy.py` 同步加了
    //   `test_pc_optional_parameters_are_accepted`（用户批准动那条门禁的钉法：从"钉到闭合括号"
    //   改成"钉到参数起始处"+ 新增这条更强断言）。
    //   ⇒ 下面 `0x0E01003F` / `0x0E010049` 两条的正文只留"**值**仍是恒值"这一半偏离。

    // ---- `Input` 的三条按钮查询（批次 195：**手柄那半已是真值**，键盘那半是平台固有）---------
    //
    // 原来的登记是"这一类按钮查询没有可调用的引擎入口 —— 输入管理器实例还没定位"（`debt`）。
    // **那条前提已被 2026-09-29 的取证推翻**：`KAGE::Input::ManagerBase::IsButtonPressed/
    // IsButtonTriggered/GetButtonValue`（`0x4F9504` / `0x4F9648` / `0x4F97B0`）就在引擎里，
    // 单例槽 `0xAAC768`，而且**游戏自己就在用**（`Game::ProcessInput` 的 L+R+StickL+StickR 组合键、
    // `Menu_Title::Update`、`Console::check_key_autorepeat`，全部传 `deviceId = 0xFFFFFFFF`）。
    // 手柄按键号 0..15 与 PC 的 `Controller` 枚举**逐项相同** ⇒ 那半是**真值**。
    //
    // 剩下的偏离只有键盘那半：Switch 引擎里**没有键盘输入设备**
    // （`KAGE::Input` 的类全列只有 DeviceGamepad / DeviceTouchscreen / DeviceNX / ManagerBase /
    // Manager，`Manager::Initialize` 只 new 两个设备；唯一与键盘有关的是软键盘文本入口，
    // 它给的是文本不是按键状态）⇒ `Keyboard.KEY_*`（GLFW 键码，≥32）**没有真值来源**。
    // ★ 我们**不把键盘码原样透传**：引擎按 `button & 31` 取位，`KEY_SPACE(32)` 会撞上方向左、
    //   `KEY_R(82)` 撞到位 18（没人写）—— 透传等于**按一次空格就误报"左方向键按下了"**
    //   （模组自己都知道这个坑：InputHelper 写的是 `IsButtonTriggered(key) and not
    //   IsButtonTriggered(key % 32)`，`analysis/mod-corpus/isaac-mod-config-menu/scripts/inputhelper.lua:114`）。
    //   所以键盘码一律答 false / 0.0 —— 与 PC 上"那个键没被按"同形，绝不误报。
    //
    // ★ 参数形状（**必须与手柄那半同一批做**）：PC 的绑定层**接受第三个参数**（文档没写），
    //   而设备旁的 EID 确实传三个（`features/eid_bagofcrafting_search.lua:129` 的
    //   `Input.IsButtonTriggered(Keyboard.KEY_ESCAPE, 0, true)`、`:145` 等 7 处）⇒
    //   旧实现"恰好两个参数"会把这几条变成 `luaL_error`、派发器摘掉整条回调。现在收 2 或 3 个。
    {0x09010001,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Input.md:105 「#### boolean IsButtonTriggered ( [Keyboard](enums/Keyboard.md) button, int controllerId )」"
     "（正文 `:107`：某个键**这一帧刚按下**，且「问过一次就不再为真」）。"
     "**现状（批次 195 起）**：`button ∈ 0..17`（手柄按键，与 PC 的 `Controller` 枚举逐项相同）"
     "**真的调引擎**回答；`button ≥ 32`（`Keyboard.KEY_*` 的 GLFW 键码）一律 **false**。"
     "★ 批次 211（2026-09-30）起 `controllerId` 也过一张**映射表**：PC 的 `0`（键盘）⇒ 答 false、"
     "`1..4` ⇒ 引擎设备表里第 1..4 台手柄设备（真机 = `33`）、其它值原样透传（NS 原生用法）。"
     "口径与证据见 `runtime/source/pc_ns_input_device_map.hpp`。"
     "★ 另外：边沿不是引擎的 `+0x38` 语义（那是「上一帧也按着」，见下面 `InputDeviceBase` 的取证），"
     "而是我们自己的 `InputFrameEdges`（★ 更正（批次 381，2026-10-06）：原名 `ActionEdgeTracker`，"
     "现已改名，且改成「每帧在引擎帧边界采一次、判定纯读」——见 `input_edge.hpp` 第五节）"
     "—— 与 `IsActionTriggered` 同一处口径。"
     "偏离后果：用键盘**快捷键**的模组（`Keyboard.KEY_R` / `KEY_ESCAPE` 那类）在 Switch 上永远得到 "
     "false ⇒ 那条快捷键分支不执行（不报错、不崩，只是「没反应」）；而**用手柄按键号问的调用**"
     "（InputHelper 的 `Controller.BUTTON_A` 一族）拿到的是真值。"
     "性质：platform（平台固有）——理由：Switch 引擎里**确实没有键盘输入设备**"
     "（`KAGE::Input` 的类全列 + `Manager::Initialize` 只建触摸/手柄两个设备，已取证「没有」），"
     "键盘码没有真值来源；而手柄那半已经接上 ⇒ 属于「继续做工作也消不掉」的那一半。"
     "判据：runtime/tests/test_lua_neutral_keyboard_input.py（键盘码必答 false、参数个数不对要报错、"
     "2 或 3 个参数都要通过）；runtime/tests/test_touch_pointer.py。"},
    {0x09010002,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Input.md:89 「#### boolean IsButtonPressed ( [Keyboard](enums/Keyboard.md) button, int controllerId )」"
     "（正文 `:91`：按住期间一直为真）。**现状（批次 195 起）**：同 `IsButtonTriggered` —— "
     "手柄按键号 0..17 真调引擎、键盘码（≥32）一律 false；`controllerId` 同样过"
     "`pc_ns_input_device_map.hpp` 那张 PC→NS 映射表（批次 211）。"
     "偏离后果：靠键盘「按住」做连续动作（快进、连续翻页）的模组在 Switch 上永远得不到真值 ⇒ "
     "那条路径不工作（不报错、不崩）；用手柄按键号的调用拿到真值。"
     "性质：platform（平台固有）——理由：同 `IsButtonTriggered`：Switch 没有键盘设备（已取证「没有」），"
     "键盘码没有真值来源；手柄那半已接上。"
     "判据：runtime/tests/test_lua_neutral_keyboard_input.py（键盘码必答 false、参数形状）。"},
    {0x09010003,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Input.md:34 「#### float GetButtonValue ( [Keyboard](enums/Keyboard.md) button, int controllerId )」"
     "（正文 `:36` 只有一句「改用 GetActionValue」；单位从同页 `:23` 推：键盘恒 0/1、模拟量只对**手柄轴**有意义）。"
     "**现状（批次 195 起）**：手柄按键号真调引擎的 `ManagerBase::GetButtonValue`（浮点返回在 s0）；"
     "键盘码（≥32）一律 0.0；`controllerId` 同样过 PC→NS 映射表（批次 211）。"
     "偏离后果：拿它判「按得多深」的模组在键盘码上恒得 0（该分支不执行，拿 0 做乘法还会把结果一起归零）；"
     "手柄按键号上拿到引擎真值（有名字的按键都落在 0/1 分支 —— 模拟量那一档的按键号在引擎里对不上"
     "任何名字，见规格的 `reachability_problem`）。轴强度请用已实现的 `Input.GetActionValue`。"
     "性质：platform（平台固有）——理由：同 `IsButtonTriggered`：键盘码没有真值来源（Switch 无键盘设备）；"
     "手柄那半已接上。"
     "判据：runtime/tests/test_lua_neutral_keyboard_input.py（键盘码必答 0、参数形状）。"},

    // ---- `Isaac` 的两条坐标变换：**批次 195（2026-09-29）已还清、条目删除** -------------
    // `0x0E01000C`（`WorldToScreen`）与 `0x0E01000D`（`WorldToRenderPosition`）原来登记的是
    // "恒等变换 + 相机参数未取证"（`debt`）。现在两条都**真调引擎** `GetRenderPosition(pos, true)`
    // （PLT 桩 `0x670FA0` + 16 字节入口守卫），差别只有"要不要再加 `Room[0x1938] + Game[0x24F9B0]`"
    // —— 与 PC 的两条处理函数逐项一致（PC 处理函数反汇编 + `Room::WorldToScreenPosition @ 0x489354`，
    // 逐条见 `analysis/api-restore-transforms/spec.json`）。
    // ★ 同一批还**新增**了 PC 上本来就有的 `Isaac.ScreenToWorld`（catalog `0x0E01005F`）。
    // 判据：`runtime/tests/test_lua_isaac_table.py`（参数校验 + 调用形状）、
    // `runtime/tests/test_touch_pointer.py`（`GetMousePosition(true)` 现在返回**世界坐标**，
    // 与 `WorldToScreen` 的配对关系随之改变）。
    // 2026-10-09：getter已返回真实PGD对象并支持Unlocked，旧记录全文归档PGD存档.before。
    // ★★ 批次 404（2026-10-07）：`Isaac.GetTrinketIdByName`（0x0E01000F）的偏离**已还清，按台账
    //   设计**删除**（见 `api_deviation.hpp` 文件头与本文档头的口径：'debt …还清之后应当把这条
    //   从台账里删掉'；098 那次消掉四条 `Room` 网格偏离就是同一形态）。
    //   原条目正文（"我们**恒返回 0**：那张名字→id 表在 PC 上是内建的，Switch 侧的对应数据未取证 …
    //   性质：debt …判据：test_lua_isaac_table.py（钉「恒 0」）"）描述的事实**已不成立**：
    //   本批补了本体饰品静态表（`isaac_name_source/trinkets.txt`，188 条，来自 `items.xml` 的
    //   `<trinket>`）**加上**同族的运行时追加层（`program/mod_content_names.*`），
    //   `Isaac.GetTrinketIdByName("Lucky Toe")` 现在返回 42（与 `Isaac.md:467` 的例子逐值一致）。
    //   ⇒ 本条**不是**修改旧文的语义结论，而是"这条偏离不存在了"的销账；条数与 `debt` 计数
    //   同步在 `test_api_deviation.py` 里 -1（旧文**逐字保留在本注释里**以备复核）。

    // ---- `EntityPlayer` 的恒值成员（这一族最大，20 条）-----------------------------
    // 2026-10-09：0x0E01001F真实配对/主身/副玩家规则已恢复；旧全文归档player-twins/api_deviation.cpp.before。
    // 2026-10-09：0x0E010032真实配对/主身/副玩家规则已恢复；旧全文归档player-twins/api_deviation.cpp.before。
    // ★ 批次 195（2026-09-29）：四条 `Get*RNG` 从"**恒 nil** 的占位"改成**真读数** ——
    //   数据就在实体里：四张 `std::vector<RNG>`（元素 16 字节）分别在
    //   `Entity_Player + 0x1BB0/0x1BC8/0x1BE0/0x1BF8`，索引就是枚举 id 本身；四条各有
    //   "消费者指令 + 该消费者引用的越界字符串"两重证据（规格 `analysis/api-restore-rng/spec.json`，
    //   逐条抄进 `runtime_constants.hpp`）。残留的偏离只有**快照口径**（下面四条同形），
    //   性质因此从 `debt`（"取法还没定位 ⇒ 能还"）改档为 `design`（主动保留的口径差异）。
    //   ★ 判据从"钉恒 nil"换成"钉快照语义 + 换 id 必须读到另一格"（见 `判据：` 那行）。
    // 2026-10-09：0x0E010033已恢复原生RNG引用，旧快照记录全文归档rng-references/api_deviation.cpp.before。
    // 2026-10-09：0x0E010034已恢复原生RNG引用，旧快照记录全文归档rng-references/api_deviation.cpp.before。
    // 2026-10-09：0x0E010035已恢复原生RNG引用，旧快照记录全文归档rng-references/api_deviation.cpp.before。
    // 2026-10-09：0x0E010036已恢复原生RNG引用，旧快照记录全文归档rng-references/api_deviation.cpp.before。
    // ★ 批次 195（2026-09-29）：`0x0E01003A`（`GetHearts`）/ `0x0E01003E`（`GetPoopMana`）/
    //   `0x0E01003F`（`GetPoopSpell`）三条偏离**已还清、条目删除**（销账，不是漏登记）——
    //   它们原来登记的都是"引擎里的字段还没定位 ⇒ 能还"（`debt`），现在字段都确证了：
    //     * `GetHearts`    → `Entity_Player + 0x16BC`（u32，**半心为单位**）；
    //     * `GetPoopMana`  → `+0x269C`；
    //     * `GetPoopSpell` → `+0x26A0` 的 6 格 u8（越界我们主动夹到 0）。
    //   逐条指令证据见 `runtime_constants.hpp` 里那三条常量与规格
    //   `analysis/api-restore-entityplayer-a/spec.json`；判据换成
    //   `runtime/tests/test_lua_entity_player.py` 的端到端读数（夹具写字面值、断言读得对）。
    // ★ 批次 177（2026-09-28）：`0x0E010040`（`GetZodiacEffect`）偏离**已还清、条目删除** ——
    //   引擎有 `Entity_Player::GetZodiacEffect() const` @ `0x29A938`，现走引擎方法数据行
    //   （`EngineCallShape::Int0`）。
    // ★ 批次 195（2026-09-29）：`0x0E010041`（`GetModelingClayEffect`）偏离**已还清、条目删除** ——
    //   它原来是"恒 0、字段未取证 ⇒ 能还"（`debt`），现在确证在 `Entity_Player + 0x2730`
    //   （存档字段 `GameStatePlayer+0x608` 与它是同一个值的存取两端，旁边唯一的字符串就是
    //   "[warn] Invalid modeling clay effect %d"）。证据见 `runtime_constants.hpp` 的
    //   `kEntityPlayerModelingClayEffectOffset` 与规格 `analysis/api-restore-entityplayer-a/spec.json`。
    // ★ 原 `{0x0E010042, ApiDeviationKind::Placeholder, …}`（`GetGlyphOfBalanceDrop` 恒 0）
    //   已在**批次 184（2026-09-28）删除** —— 它不再是"恒返回假值"：现在走
    //   `kEntityPlayerEngineRows` 的 `Ref2U32Pair` 数据行，真调引擎 `0x2FE574`、
    //   返回一张两元表（`{[1]=variant, [2]=subtype}`，口径见 `runtime_constants.hpp` 那条）。
    //   为什么留这行注释而不是直接抹掉：这条当年的偏离理由是"**能还**（派生值在引擎里，
    //   只是还没查）"，现在**还上了**。下一个人再看到 `0x0042` 要能知道"它已经不在台账里、
    //   是销账而不是漏登记"。
    // ★ 批次 195（2026-09-29）：`0x0E010045`（`GetPlayerFormCounter`）偏离**已还清、条目删除** ——
    //   它原来是"恒 0、字段未取证 ⇒ 能还"（`debt`），现在确证在 `Entity_Player + 0x1C54`
    //   的 **15 个 int32**（= `NUM_PLAYER_FORMS`；长度由 `RestoreGameState` 的 15 组连续复制证明，
    //   语义由 `HasPlayerForm` 的 `counter > 2` 定死）。越界我们主动夹 [0,14]。
    //   证据见 `runtime_constants.hpp` 的 `kEntityPlayerFormCountersOffset`。
    // 2026-10-09：0x0E010046恢复REPENTOGON实际可选筛选/全ID计数接口。
    // 旧占位及“空表比较安全”原文逐字归档docs/GetSmeltedTrinkets证据-20261009/。

    // ★ 批次 388（2026-10-07）：`0x0E010047`（`EntityPlayer:GetEffects`）偏离**已还清、条目删除** ——
    //   它原来是"**恒返回空表**（没有任何方法）⇒ 模组 `player:GetEffects():HasCollectibleEffect(id)`
    //   抛 `attempt to call a nil value` ⇒ 整条回调被派发器静默摘掉"（性质 debt / **能还**）。
    //   现在 `GetEffects()` 返回带 17 个方法的 `TemporaryEffects` 对象 —— 容器偏移（`Entity_Player + 0x18D8`）
    //   与 12 个引擎方法地址全在 `runtime_constants.hpp` 的 TemporaryEffects 段，实现见 `isaac_api.cpp`。
    //   ★ 剩下的 **5 条方法级占位单独登记**在本表末尾（`0x0E010106`..`0x0E01010A`）。
    //   为什么留这段注释而不是直接抹掉：下一个人再看到 `0x0E010047` 要能知道"它已经不在台账里、
    //   是**销账**而不是漏登记"（照 `0x0E010045` / `0x0E010046` 两条销账注释的先例）。
    // ★ 批次 195（2026-09-29）：`0x0E010049`（`EntityPlayer:HasTrinket`）与
    //   `0x0E01004A`（`EntityPlayer:HasGoldenBomb`）两条偏离**已还清、条目删除**。
    //   * `HasGoldenBomb`：从"恒 false 的假桩"改成**字段数据行** —— 读
    //     `Entity_Player + 0x16D9` 那一个字节；**取值锚点**是引擎自己的一对同名函数
    //     （`AddGoldenBomb @ 0x2FC3F0` 置 1 / `RemoveGoldenBomb @ 0x2FC490` 清 0），
    //     且紧邻的 `0x16D8` 是"金钥匙"标志（写法逐字同形）⇒ 读的是引擎真值。
    //   * `HasTrinket`：不再自己扫两个饰品槽，改为**一次引擎调用**
    //     `Entity_Player::HasTrinket(eTrinketType, bool) @ 0x28D3B8`（保留手写 handler ——
    //     PC 的第二个参数可省，而数据行按参数个数严格相等校验）。引擎那一支自己就实现了
    //     PC 文档的两种口径（`IgnoreModifiers=false` 走 `GetTrinketMultiplier`、`true` 扫槽）
    //     并在比较前 `and #0x7fff` ⇒ 旧实现"金色饰品答 false"与"读不到被道具赋予的饰品效果"
    //     两处偏差同时消失。
    //   ⚠️ 与批次 177 同一句口径提醒：这两条**新实现还没上真机验收** —— 只是"桩不再是假值"，
    //   不是"值已验真"（真机判据见 `analysis/api-restore-entityplayer-b/spec.json` 的 host/device 两栏）。
    //   `HasTrinket`/`HasGoldenBomb` 的"我们比 PC 严"那一半（参数个数）由
    //   `runtime/tests/test_id_argument_policy.py` 继续钉住。

    // ★ 批次 177（2026-09-28）：`0x0E01004B`（`HasPlayerForm`）偏离**已还清、条目删除** ——
    //   引擎有 `Entity_Player::HasPlayerForm(ePlayerForm) const` @ `0x298510`，现走引擎方法数据行
    //   （`EngineCallShape::Bool1`；一个整数参数、不做范围校验）。
    // ★ 批次 177（2026-09-28）：`0x0E01004C`（`CanPickRedHearts`）偏离**已还清、条目删除** ——
    //   引擎有 `Entity_Player::CanPickRedHearts()` @ `0x2FB6A4`（**非 const 成员**，ABI 上无差别），
    //   现走引擎方法数据行（`EngineCallShape::Bool0`）。真实调用点 = EID
    //   `features/eid_itemprediction.lua:366`（恒 false 时"满红心"那一支预测永远不成立）。
    // 2026-10-09：0x0E01004D真实配对/主身/副玩家规则已恢复；旧全文归档player-twins/api_deviation.cpp.before。

    // ---- `Isaac`（批次 139 新增一条：服装路径反查的**搜索范围**）--------------
    // `Isaac:GetCostumeIdByPath(path)`（0x0E01005D）本身是**真实现**（遍历 null 道具向量、
    // 比条目 `+0x88` 的 anm2 路径、返回 `+0x04`）；登记的是"只搜 null 向量"这一处**范围**偏离，
    // 定案与互证指令见 `runtime_constants.hpp` 的 `kItemConfigItemNullCostumePathOffset`
    // 与 `dist/specialist-costume-field-static.md`。
    {0x0E01005D,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Isaac.md:190 「#### int GetCostumeIdByPath ( string path )」"
     "PC 的 `Isaac:GetCostumeIdByPath(path)` 按 anm2 路径返回服装 id、找不到返回 **-1**（同页 :192 原文）。"
     "我们**只搜 null 道具向量**（`ItemConfig+0x30/+0x38`，即 `costumes2.xml` 里 `type=none` 的那些条目，"
     "本模组与官方教程用的就是这一类）。`costumes2.xml` 里 `type=passive/active/familiar/trinket` 的条目"
     "把路径挂在**收藏品/饰品条目**上（`ItemConfig::LoadCostumes @ 0x3B9448` 的另一条分支："
     "`0x3B9DF0` 取 `+0x00` 收藏品向量、`0x3BA154` 取 `+0x18` 饰品向量），而 **PC 那条 API 会不会也搜"
     "那几条向量，在 Switch 镜像里查不到**（那半边实现在 PC 的 exe 绑定层，本镜像里不存在）。"
     "偏离后果：拿内置/模组的 `passive/active/familiar/trinket` 型服装路径去问，我们答 **-1**"
     "（PC 可能给出真 id）⇒ 模组若把 -1 直接喂给 `AddNullCostume(-1)`，而 `GetNullItem(-1)` 是空 ⇒ "
     "`AddCostume` 解引用空指针（`dist/specialist-costume-field-static.md` §E8）；"
     "**取 null 服装 id 这个用法（本模组 + 官方教程）不受影响**。"
     "性质：platform（平台固有）——理由：这半边只能从 PC 的 exe 绑定层取证，而那份绑定层不在 Switch 镜像里"
     "（已取证『镜像里查不到』：`analysis/lua-api-inventory/inventory.json` 的 `Isaac:GetCostumeIdByPath` "
     "条目明写本镜像既没有同名自由函数、`Game`/`Manager` 里也没有同名成员）⇒ 继续投入也消不掉。"
     "判据：runtime/tests/test_lua_entity_player.py（消费者视角：假 ItemConfig 的 null 向量里放一条 "
     "`the/specialist_isaac.anm2` ⇒ 命中返回它的 id；收藏品条目上也放同一条路径 ⇒ 必须答 -1，"
     "把『只搜 null 向量』钉住）；runtime/tests/test_layout_table_item_config_item.py"
     "（那个字段的偏移证据可复现 + 与手写常量/台账对账）。"},

    // ---- `EntityPlayer` 的「null 服装」两条（批次 141，2026-09-26）------------------------
    // 它们本身是**真实现**（引擎方法数据行）；登记的是我们**主动加的一道参数校验**：编号无效时
    // **不往引擎里调**。由来是真机崩溃：The Specialist for Good Items 在跳舞时把
    // `Isaac.GetCostumeIdByPath(...)` 的结果直接喂进来，查不到时那个值是 `-1` ⇒ 引擎
    // `GetNullItem(-1)` 拿到空 ⇒ `AddCostume(nullptr)` 解引用空指针（崩在 `+0x3c`、
    // `Data Abort`、崩溃地址为零；`dist/specialist-crash-20260926.md`）。
    {0x0E01005B,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:337 "
     "「#### void AddNullCostume ( [NullItemID](enums/NullItemID.md) NullId )」"
     "（同页正文只给签名与参数类型，**没有**规定编号无效时会怎样）。"
     "我们这一条是真实现（引擎方法数据行，入口 `0x291BBC`），但**多了一道参数校验**：编号为负、"
     "越界、或指向空槽时**不往引擎里调**（这次调用被挡下，并记一次 `g_IsaacEngineRowRejectGuard`）。"
     "偏离后果：模组自己传了无效编号时，我们**什么都不做**（那一次换装不生效、不报错、也不崩）；"
     "PC 上同一次调用会把编号原样交给引擎（`GetNullItem(id)` 取到空指针再解引用 —— 那一步在 PC 侧"
     "无从取证，Switch 侧实测就是崩）。**合法编号的行为与 PC 完全一致**（引擎照常被调）。"
     "性质：design（主动保留的口径差异）——理由：两侧都做得到，但我们**有意不复刻**这条未定义行为"
     "（复刻的代价是模组一传无效编号就把玩家的游戏崩掉），且挡下次数在读数里看得见（不会无声消失）。"
     "判据：runtime/tests/test_lua_entity_player.py（消费者视角：假 null 服装容器里放有效条目 ⇒ "
     "有效编号照常调进引擎；`-1` / 越界 / 空槽 ⇒ 不报错、不崩、挡下计数各加一）。"},
    {0x0E01005C,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:1828 "
     "「#### void TryRemoveNullCostume ( [NullItemID](enums/NullItemID.md) NullId )」"
     "（同页正文只给签名，"
     "**没有**规定编号无效时会怎样）。我们这一条是真实现（引擎方法数据行，入口 `0x2F2170`），"
     "但**与 `AddNullCostume` 共用同一道参数校验**：编号为负、越界、或指向空槽时**不往引擎里调**。"
     "偏离后果：模组自己传了无效编号时，我们**什么都不做**（那一次「摘服装」不生效、不报错、也不崩）。"
     "★ 2026-09-29 更正（批次 195，**新证据**）：本条原来写的「PC 上同一次调用会把编号原样交给引擎"
     "（…Switch 侧实测就是崩）」**与事实不符** —— `Entity_Player::RemoveCostume(ItemConfig::Item const*) "
     "@ 0x2914E0` 的**第一条指令就是 `cbz x1, 0x29151C`**（指针为空 ⇒ 直接返回），"
     "而 `TryRemoveNullCostume @ 0x2F2170` 只是 `GetNullItem(id)` → `b RemoveCostume(...)`，"
     "自己没有别的校验 ⇒ **无效编号在引擎侧是安全的空操作，不会崩**。"
     "（同族的 `AddNullCostume` 才是真会崩的那一条：`AddCostume @ 0x290C38` 在 `0x290C74` "
     "`ldr w8,[x1]` **对第 1 实参没有任何空指针检查** —— 那条的登记见 `0x0E01005B`。）"
     "⇒ 所以本条挡下的**不是防崩、而是为了与本族口径一致**：两条 API 走同一个 null 服装容器、"
     "共用一道校验，挡下的次数同样进读数（`g_IsaacEngineRowRejectGuard`，不是无声吞掉）。"
     "**这是有意的选择，不是事实主张**：要它逐位与 PC 一致，把这一条换回普通 `Void1`（不再挡）即可，"
     "行为上不会有新的崩溃风险（见 `analysis/api-restore-entityplayer-b/spec.json` 的 (a)/(b) 两条路）。"
     "合法编号的行为与 PC 完全一致（引擎照常被调）。"
     "性质：design（主动保留的口径差异）——理由：两侧都做得到，我们**有意**让这一族共用一道校验"
     "（口径一致、挡下次数可观测）；本轮按\"改动最小、风险最低\"保留现状，只把那条**错误的事实描述**改对。"
     "判据：runtime/tests/test_lua_entity_player.py（消费者视角：无效编号不报错、不崩，"
     "挡下计数加一；有效编号照常调进引擎）。"},

    // 批次 140（2026-09-26）：`Game:GetPlayer(index)`（0x0201000C）—— **与 `Isaac.GetPlayer`
    // 的越界口径不一致**这一处（真机证据：The Specialist for Good Items 的 `main.lua:447`）。
    {0x0201000C,
     ApiDeviationKind::Partial,
     "★2026-10-16更正：固定PC原生0x412750及0x412792/0x4127A0明确非法索引返回首玩家；"
     "Isaac与Game两入口已统一此行为，原文把首/末差异归为DLC版本的结论错误。"
     "非整数/缺参的公开包装语义尚未据此全验；以下逐字保留旧判断作为历史，不再作为实现规范。"
     "PC 契约：tools/pc_contract_docs/Game.md:337 签名「#### EntityPlayer GetPlayer ( int Index )」"
     "（徽章 `.alldlc` = 全 DLC）+ 同页 `:338` 正文「If an index is given, that is not used, it will "
     "return the last player in the list.」。我们**按这一页正文实现**：下标越界（含负数）⇒ 夹到"
     "**最后一个玩家**；向量为空/读不到 ⇒ nil。"
     "偏离点是另一条：同页 `:340` 写「This function is the same as Isaac.GetPlayer()」，"
     "而我们的 `Isaac.GetPlayer` 对越界给 **nil**（既有行为，且被两处门禁钉住："
     "`test_lua_entity_player.py:731/736`、`test_lua_isaac_table.py:480`）⇒ 两个『同一个函数』的越界答案不一致。"
     "（附带记一笔：`Isaac.md:326` 徽章是 `.reporplus`、正文写『非法 id ⇒ 按 0 处理』，那是 **Repentance+** "
     "的行为，不属于我们跑的忏悔本体；Game.md 那条才是全 DLC。）"
     "偏离后果：模组用 `Game:GetPlayer(越界)` 会拿到**最后一个**玩家（与它在本版本 PC 上的行为一致 ⇒ 不伤它，"
     "The Specialist for Good Items 的 1 基循环正是靠这一条才拿到人），而用 `Isaac.GetPlayer(越界)` 拿到 nil —— "
     "两者对『还有没有第 n 个玩家』这种探测会给出不同答案。"
     "性质：design（主动保留的口径差异）——理由：越界给『最后一个』是 PC 正文，不是我们的取舍；不一致的另一半在"
     "`Isaac.GetPlayer`（它的 nil 已被两处门禁钉住，改它要动测试，按项目纪律先问用户）⇒ 本轮有意不动，"
     "把它作为**独立决定**留给下一批。"
     "判据：runtime/tests/test_lua_entity_player.py（消费者视角：单人局里 `game:GetPlayer(0)/(1)/(99)` "
     "必须给出**同一个**玩家、`(-1)` 同；无玩家场景里 `game:GetPlayer(0)` 必须 nil；参数不是整数 ⇒ nil "
     "且不抛 Lua 错误）。"},

    // ---- 批次 207（2026-09-29）：MCM 前置 API 带出来的两条 -------------------------
    {0x0E010065,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Isaac.md:218 「#### [EntityType](enums/EntityType.md) "
     "GetEntityTypeByName ( string entityName ) {: .copyable aria-label='Functions' }」"
     "PC 正文（`Isaac.md:220`）写明查的是 `entities2.xml`：『Returns the EntityType of an entity "
     "based on its name. (File: entities2.xml) Returns `0` if no entity with that name could be found.』"
     "（同族 `GetEntityVariantByName` 在 `Isaac.md:235`，找不到返回 `-1`。）"
     "我们查的是 `runtime/source/program/entity_name_table.cpp` 里那张**静态快照** ——"
     "由 PC 文档站的两份 `entities2.xml`（AB+ 基础表 + 忏悔补丁表）在构建期生成，"
     "输入与生成器都在仓库里（`tools/entity_name_source.txt` / `tools/generate_entity_name_table.py`）。"
     "偏离后果：模组**自己带来**的实体（它随模组附一份 `entities2.xml`、由引擎在装载期合并）在我们这张"
     "快照里没有 ⇒ `Isaac.GetEntityTypeByName(\"<模组自己的实体名>\")` 返回 `0`、"
     "`GetEntityVariantByName` 返回 `-1`（= PC 的『找不到』口径），而它在 PC 上能查到真值。"
     "本版本（忏悔本体）的实体、以及语料里 MCM 真正查过的那种『某个装了土豆假人的模组』的存在性探测"
     "都不受影响 —— MCM 的 `modconfig.lua:260/261` 就在 `if potatoType and potatoVariant > 0` 里"
     "把『查不到』当成『没装』处理。"
     "性质：debt（我们的欠账）——理由：底座存在且可定位（引擎自己有一张运行期实体配置表，"
     "`Manager` 里按 (id, variant) 存名字/条目），只是偏移还没取证；定位后改成真读即可。"
     "判据：runtime/tests/test_lua_isaac_table.py（钉\"快照表里查得到的那几条\"与\"查不到时 0 / -1\"；"
     "未钉\"模组自加实体在 PC 上查得到\"）。"},

    // ---- 批次 240（2026-09-30）：名字表一族里唯一一条**有意偏离** -------------------------
    // `GetCardIdByName` 的 PC 语义匹配的是 `pocketitems.xml` 里的 **`hud` 属性**，
    // 而实测本体那份 XML **一条 `hud=` 都没有**（0 处）⇒ 我们改用 `name` 属性。
    {0x0E01007A,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/Isaac.md:149 「Returns the [CardID](enums/Card.md) based on "
     "the \"hud\"-attribute defined in the \"pocketitems.xml\" file. Returns `-1` if no card with "
     "that \"hud\" attribute value could be found.」"
     "（同页 `:152` 还带一条警告：『The name of this function is misleading, this function will "
     "only work with the \"hud\"-attribute value of a card and not the name of a card.』）"
     "我们查的是 `runtime/source/program/isaac_name_tables.cpp` 里那张**静态快照**，"
     "而且用的是 `name` 属性、**不是 `hud` 属性**。"
     "偏离后果：① 对**本体卡牌**，PC 自己也查不到（契约 `:154` 明写『does not work for vanilla "
     "cards/runes, because they don't have the \"hud\" attribute』）⇒ 这一支双方一致（都返回 `-1`，"
     "而我们的表里本体卡牌是有名字的 ⇒ **我们比 PC 多查到**：`Isaac.GetCardIdByName(\"The Fool\")` "
     "在我们这儿返回 `1`、在 PC 上返回 `-1`）。② 对**模组自己加的卡**（它在 `content/pocketitems.xml` "
     "里写了 `hud`），我们查不到 ⇒ 返回 `-1`，与 PC 相反。"
     "性质：design（主动保留的口径差异）——理由：本体的 `pocketitems.xml` 里 `hud` 属性为 0 处，"
     "按 `hud` 建表等于建一张空表；而语料里对这条 API 的**唯一**引用是文档示例"
     "（`TBOI_Better-Voiding` 的 README/Readme.txt，**没有任何 `.lua` 真的调用它**），"
     "所以「把本体卡牌查得到」比「严格照 PC 返回 -1」对模组更有用。"
     "判据：runtime/tests/test_isaac_name_tables.py（钉住 `Chaos Card → 42` 这类本体条目；"
     "未钉\"PC 对本体卡牌返回 -1\"这条差异）。"},

    {0x11010002,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/HUD.md:56 「#### void SetVisible ( boolean Visible = false ) "
     "{: .copyable aria-label='Functions' }」"
     "（`HUD.md:57` 正文：『Turns the HUD on or off.』**注意 `HUD.md:55` 的徽章是 `.reporplus`** ——"
     "`Game:GetHUD()`（`Game.md:279`）与 `HUD:IsVisible()`（`HUD.md:41`）同；这三个是**忏悔+**才有的 API。）"
     "我们读写的字节是 `HUD + 0xC53FA`，也就是 `HUD::Render()` @ `0x3AC71C` 的**第一条有效判断**："
     "`ldrb w8, [x0, x8]` 后 `cbz w8, <函数收尾>` —— 那一字节为 0 时整块 HUD 不画"
     "（取证见 `runtime_constants.hpp` 的 `kHudVisibleFlagOffset`）。"
     "**这条偏离只在于『我们写了引擎从不写的一格』**：全镜像里构造出 `0xC53FA` 这个常量只有"
     "`HUD::Render` 自己那一处、而且是读；旁边那几格（`0xC53FB`/`0xC53FC`/`0xC5400`）分别被 "
     "`HUD::Init`/`HUD::Update` 写 ⇒ 这一格在我们跑的 `1.7.9b` 里**既没有写者、也没有初始化**。"
     "偏离后果：`HUD:IsVisible()` 报的就是那一格的真值（与引擎渲染路径同源，口径不会错），"
     "但开局那一刻它是什么**不受保证** —— 模组不能把『`IsVisible()` 返回 false』当作"
     "『玩家把血条关了』；而 `SetVisible(false)` 之后 HUD 一定不画、`SetVisible(true)` 之后一定画。"
     "性质：debt（我们的欠账）——理由：能还，且还法很便宜（真机读一次那一格、确认初值非 0，"
     "并把读数写进 `runtime_constants.hpp` 的这段注释）；在读到之前，"
     "`SetVisible` 是我们**唯一**一处会写引擎内存的非字段 API，所以实现里只在可写判定通过时才落值。"
     "判据：runtime/tests/contract/test_api_catalog.py（钉\"`HUD` 家族的两条绑定行落在 `game_api.cpp`、"
     "id 与目录一致\"）；未钉\"那一格的引擎初值\"——那要靠真机读数，属未取证，不是主动取舍。"},

    // ---- `Room` 的渲染两条（批次 269）----------------------------------------
    {0x04010024,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Room.md:468 「#### [RenderMode](enums/RenderMode.md) GetRenderMode ( ) {: .copyable aria-label='Functions' }」"
     "（正文 `:469`：返回一个 RenderMode，用来按上下文区分渲染方式，例如水面反射）。"
     "PC 侧它就是一条 6 字节访问器（`tools/pc_exe_binding.py GetRenderMode` ⇒ 绑定函数 VA `0x422DB0` = "
     "`mov eax,[ecx+0x12BC]; ret`），即 `Room + 0x12BC` 那个字。"
     "**Switch 侧的偏移没有取证到**：符号表里 `eRenderMode` 只出现在 `EntityList::RenderStart(eRenderMode)` "
     "的参数上；`RenderStart` 在整份镜像里没有一处直接 `bl`（扫过全镜像的 BL 立即数）；"
     "而 PC 的偏移**不能平移**过来 —— PC 是 32 位、Switch 是 64 位，同一个 `RenderScrollOffset` "
     "在 PC 是 `0x1204`、在 Switch 是 `0x1938`，差值本身就说明两边成员布局不同。"
     "⇒ 这里固定返回 `RenderMode.RENDER_NORMAL`（`1`）。"
     "偏离后果：**有水/反射的房间里**，模组（BOIStageAPI15 的自定义门高亮）会多画一层 —— 因为它按 "
     "`GetRenderMode() == RENDER_NORMAL` 决定要不要画。干燥房间（绝大多数）与 PC 同结论。"
     "★ 为什么给值而不是不给：这条 API 的调用点在 `MC_POST_EFFECT_RENDER` 回调体里，方法缺失会让"
     "**整条回调被摘掉**（`attempt to call a nil value`），那比\"多画一层\"重得多。"
     "性质：debt（我们的欠账）——理由：字段确实存在于引擎里，只是这一格没定位；取证到就能换成真读。"
     "判据：runtime/tests/test_lua_room_render_placeholders.py（钉\"返回 1 且不报错\"与\"参数闸门\"；"
     "未钉\"真机上的实际渲染模式\"——那要靠真机读数，属未取证，不是主动取舍）。"},
    {0x04010025,
     ApiDeviationKind::Placeholder,
     "PC 契约：tools/pc_contract_docs/Room.md:478 「#### const [Vector](Vector.md) GetRenderSurfaceTopLeft ( ) {: .copyable aria-label='Functions' }」"
     "（正文 `:479`：地板与墙壁贴图将会被渲染到的那个位置）。"
     "PC 侧同样是一条访问器（VA `0x68F4E0` = `lea eax,[ecx+0x11fc]; ret`，返回 `Room + 0x11FC` 那个 Vector 的地址；"
     "它与同页的 `GetRenderScrollOffset`（`+0x1204`）相邻）。"
     "**Switch 侧没有取证到**：① 符号表里没有 `RenderSurface`/`SurfaceTopLeft` 任何形式的名字；"
     "② 按\"与滚动偏移相邻 8 字节\"的假设去扫 `Room + 0x1930` 的访存点，命中处**全部属于 `Entity_Player`**"
     "（现场有 `sync_consumable_counts(Entity_Player*, …)` / `ProceduralItemInventory::RestoreGameState` / "
     "`CreateWeapon` 三个独立佐证）⇒ 那是一次假阳性，已排除；"
     "③ `Room::WorldToScreenPosition @ 0x489354` 只碰 `0x1938`，邻域里没有第二个 Vector 字段。"
     "⇒ 这里返回**零向量**。**刻意不编一个\"看起来像真值\"的常量**：那会让模组拿到一份静默偏掉的"
     "屏幕尺寸，而假读数正是本项目忌讳最重的一类。"
     "偏离后果：模组的 `StageAPI.GetScreenBottomRight()` 会得到 `(442,286)`（而不是屏幕右下角附近），"
     "它算出来的 `GetScreenScale()` 约 0.92 ⇒ 该模组按屏幕尺寸摆放的自定义 UI 会略小、略偏。"
     "★ 为什么给值而不是不给：同一段代码在 `misc.lua:40`，方法缺失会让调用它的每个回调抛错并中断。"
     "性质：debt（我们的欠账）——理由：字段存在于引擎里，只是没定位；取证到就能换成真读。"
     "判据：runtime/tests/test_lua_room_render_placeholders.py（钉\"返回 Vector(0,0) 且不报错\"与\"参数闸门\"）。"},

    // ---- 批次 271：`EntityPlayer:UseActiveItem` 的两种重载 ----
    {0x0E010094,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/EntityPlayer.md:1853 "
     "「#### void UseActiveItem ( [CollectibleType](enums/CollectibleType.md) Item, "
     "[UseFlags](enums/UseFlag.md) UseFlags = 0, [ActiveSlot](enums/ActiveSlot.md) Slot = -1, "
     "int CustomVarData = 0 ) {: .copyable aria-label='Functions' }」，"
     "同页 `:1855` 还有一条**扩展层加的七参重载**"
     "「(Item, boolean ShowAnim = false, boolean KeepActiveItem = false, "
     "boolean AllowNonMainPlayer = true, boolean ToAddCostume = false, ActiveSlot Slot = -1, "
     "int CustomVarData = 0)」——**语料两条都用**（12 处 5 参 + 13 处 6 参是扩展形，"
     "另有 2/3 参的基础形）⇒ 处理器**按第 2 个参数的类型分派**（数字 = 基础形、布尔 = 扩展形）。"
     "偏离在这一处：**NS 引擎只有基础形那条入口**"
     "（`Entity_Player::UseActiveItem(eCollectibleType, unsigned, int, int)`，arity **4** ⇒ "
     "扩展形的四个布尔在那儿没有位置）。我们的折算办法是把三个能一一对应的布尔折进 "
     "`UseFlag`（引擎自己的词表，两个缺省正好对上）：`ShowAnim == false` ⇒ `USE_NOANIM`(1)、"
     "`ToAddCostume == false` ⇒ `USE_NOCOSTUME`(2)、`AllowNonMainPlayer` ⇒ `USE_ALLOWNONMAIN`(8)"
     "（常量值取自本仓库 `program/pc_lua_enum_data.cpp` 的 `UseFlag` 表）。"
     "偏离后果：① **`KeepActiveItem` 在 `UseFlag` 里没有对应位 ⇒ 表达不了** —— 扩展层用它表达"
     "『这次不消耗道具』，我们做不到（会照常消耗）；语料里这一格全是 `false`，现有调用点不受影响。"
     "② 折算本身是**我们的选择**（不是 PC 真值）：若那三个布尔在扩展层里另有实现方式，"
     "个别调用的动画/装扮表现会不同。"
     "性质：design（主动保留的口径差异）——理由：不折算就得**抛错**，而那会让语料里 25 处扩展形"
     "调用每一次都失败并摘掉整条回调（批次 249 的形态）；两害相权取『按名字对应折算 + 登记』"
     "⇒ 这是我们主动选的口径，不打算改。"
     "判据：runtime/tests/test_lua_entity_methods_batch271.py（钉『两种形态都收得下』、"
     "『基础形最多 4 个参数』、『扩展形第 8 格之外不收』；未钉『引擎那一步真的执行了什么』——"
     "那要靠真机读数，见作业单第九节 V21）。"},

    // ---- `RoomConfigSpawn:PickEntry`（批次 347，2026-10-04）--------------------------------
    {0x04010038,
     ApiDeviationKind::Partial,
     "PC 契约：tools/pc_contract_docs/RoomConfig_Spawn.md:28 「#### const [RoomConfig Entry](RoomConfig_Entry.md) PickEntry ( float r ) {: .copyable aria-label='Functions' }」"
     "（同页 `:29` 正文：`r is a value between 0 and 1`）；条目字段的类型见 "
     "tools/pc_contract_docs/RoomConfig_Entry.md:36 「#### int Variant  {: .copyable aria-label='Variables' }」"
     "（`Type`/`Weight` 在同页 `:31`/`:41`）；容器形态见 "
     "tools/pc_contract_docs/CppContainer_ArrayProxy_RoomConfigSpawns.md:25 "
     "「#### int __len ( ) {: .copyable aria-label='Operators' }」。"
     "本条的**语义与 PC 逐值相同**（加权选取的算式由引擎自己执行，我们只是转发），"
     "偏离只在三处**形态/宽度**上，三处都是本批主动选择的：① `RoomConfig::Entry` 在 Switch 上是 "
     "**12 字节**（PC 16 字节）：`Variant`/`SubType` 是 **i16**，PC 是 `int` ⇒ 按 i16 **符号扩展**"
     "读（`0xFFFF` ⇒ `-1`，与 PC 一致），但**超出 i16 取值范围的数无法表达**（域内一致）；"
     "② `RoomConfigSpawn.X` / `.Y`（PC 有）**本批未做** ⇒ 模组读 `spawn.X` 得 `nil`"
     "（Switch 侧那两个偏移 `+0x00`/`+0x02` 只有 `candidate` 级证据 —— 两处消费者按 `(Y+1)*W+X+1` "
     "当网格坐标用，但**没有任何具名访问器** ⇒ 按本项目置信度口径不对外）；"
     "③ `RoomDescriptor.Data.Spawns` 在我们这里是**普通表**（`Size` + `Get`），PC 是 "
     "`RoomConfigSpawns`（ArrayProxy，还有 `__len`）⇒ 模组写 `#spawnList` 与 PC 不同。"
     "偏离后果：只用 `Size`/`Get`/`PickEntry`/`Variant`/`SubType`/`Weight`/`Type` 的模组（语料两处"
     "都是这样）与 PC 完全一致；用 `spawn.X`、`#spawnList`、或把 `Variant` 超出 i16 的模组会与我们"
     "这里的取值不同。"
     "性质：design（主动保留的口径差异）——理由：三处都是**能做到但有意不做**的选择 —— "
     "① 按 i16 符号扩展是与 PC 逐值一致的那条路（零扩展反而会产生真差异）；"
     "② `X`/`Y` 要落地必须先补一条具名消费者证据（现在只有间接证据）；"
     "③ 做 `__len` 要给这张表挂元表、而语料与 PC 例子都只用 `Size`/`Get` ⇒ 收益与风险不成比例。"
     "不打算改。"
     "判据：runtime/tests/test_lua_batch347_roomconfig_pickentry.py（钉『`Spawns.Size` 与 `:Get(i)` "
     "的边界』『`Variant`/`SubType` 的 `0xFFFF` 读成 `-1`』『`Get` 越界/负数给 nil』"
     "『`Data == 0` 时 `Size == 0`、`Get(0) == nil`』『接收者类型闸门』；"
     "未钉『真机上 `Size` 与真实房间生成表条数一致』与『引擎真的答出了加权条目』——那要靠真机读数，"
     "见作业单第九节）。"},
    // 2026-10-09：五条占位已实现；旧条目逐字保存在
    // docs/临时效果旧台账逐字归档-20261009.md。Clear默认false；Get返回const视图。

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
