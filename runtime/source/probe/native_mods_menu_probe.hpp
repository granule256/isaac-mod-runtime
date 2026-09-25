#pragma once

// 探针：**能不能把游戏自己那套模组菜单叫出来**（2026-09-21 晚，PC 式模组页可行性的第一问）。
//
// ## 为什么要有它（背景）
//
// 用户要"与 PC 一模一样的模组管理页，并且是主界面里新增的一项"。静态取证已经查清（见
// `docs/改动日志-20260921.md` 的 019 小节）：
//   * Switch 版二进制里**有完整的 `Menu_Mods`**（ctor/Init/Update/UpdateKeyPress/Render/
//     Reset 全在，`Init` 会加载 `gfx/ui/main menu/ModsMenu.anm2`），UI 资源在本体里也有
//     （`rp_patch/resources/gfx/ui/main menu/modsmenu.anm2`）；
//   * 但它是**彻底的死代码**：11 个方法既没有调用点、也没有 GOT 槽引用、也没有函数指针表；
//   * 状态机只有 16 个状态（0 空 + 1..15），逐格都对得上具体页面，**没有模组页那一格**。
//
// 所以只剩两个问题必须在真机上回答，本探针就是为它们写的：
//   Q1 状态机那 16 个状态在真机上分别是什么页面（静态表见 `.cpp` 的注释，用来核对）；
//   Q2 绕开状态机、我们自己调 `Menu_Mods::ctor/Init/Render`，页面能不能画出来？
//      （能画 ⇒ 即使没有状态格，也能"借原生页当壳 + 喂我们自己的数据"。）
//
// ## ★ 第二版（2026-09-21 深夜，第一版真机读数之后）
//
// 第一版把"手动画原生页"挂在 **ZR+ZL 组合键**上，真机结果是**一次都没命中**：诊断字里
// `presses/backPresses/manualMode` 全是 0，而 `managerOk=1`（= 更新中继确实在跑）。
// 原因不是探针没跑，而是**手柄序号猜错了** —— 项目自己的历史结论是"引擎只认玩家自己的
// controller 值（真机上出现过 33）"，而主菜单里根本没有玩家，0/1 一律不回应。
//
// ⇒ 第二版改成两条腿，**都不再依赖"猜对按键"**：
//   * **自动驱动**：只要 `g_MenuManager` 非空（= 已经在菜单里），就自动做一次 `ctor`+`Init`，
//     之后每帧 `Render`。⇒ 用户开机停在主菜单就能看到结果，一个键都不用按。
//   * **输入扫描**：每 8 帧扫一遍 `动作号 0..27 × 手柄号 0..63`，把"哪些动作被按住""哪些手柄号
//     答过'是'"记成掩码。⇒ 下次接按键就不必再猜；顺便验证"主菜单里到底哪个 controller 有效"。
//
// 组合键（ZR+ZL）与 ZR/ZL 单键仍然保留：它们走的是"**任一手柄号**答是"的并集判定，
// 所以这次只要那个号在扫描范围里就能生效（但自动驱动已经不依赖它们了）。
//
// ## 数据从哪来（静态已确认）
//
// `Menu_Mods::Init` 会把 `*(g_Manager + 0x36800)`（= 引擎自己的 ModManager 对象）存进
// `this+0x170`；`Update` 就在它上面翻转"启用"字节（`+0x138`），`Render` 从
// `g_Manager+0x36800` 的 begin/end 指针对算行数。⇒ **页面显示的是引擎自己的模组表**，
// 不是我们的清单。它到底有没有内容，是真机问题之一（读数里 `modListBytes` 那一格）。
// 引擎那张表**天生是空的**（`ModManager::Reset` 无调用者），所以那张纸上的内容一直是我们写进去的。
//
// ## ★ 第六版（2026-09-22 下午，批次 043）：条目改成**真实模组**
//
// 前五版喂的是三个写死的测试名（`PROBE-MOD-A/B/C`），验的是"页面能不能画、位置对不对"。
// 这一版换成**真的**：目录与开关取自运行时自己的模组发现结果（与 Lua 模组菜单同一份，
// 见 `interfaces/lua/mod_menu_api.hpp` 的读面访问器），显示名取每个目录 `metadata.xml` 的
// `<name>`（取不到退目录名，`mod_display_name.hpp`）。
//
// **读 `metadata.xml` 前必须先让引擎把路径解析成"它能打开的绝对路径"**（`GetMountedFilePath`）：
// `metadata.xml` 在 PC 上**是可选的**，而**拿没解析过的路径去读会直接崩游戏** ——
// `File::OpenRead` 不做挂载解析，把路径原样交给 `nn::fs::OpenFile`，形状不对那边就 `Abort`。
// 解析不到 ⇒ 那一行退目录名，**不是错误**。
// （2026-09-22 真机事故：先做"存在性检查"再把**同一条**路径交给读函数 ⇒ 进标题界面即崩。
//  复盘见 `docs/问题与解决记录.md` 续七十；修法就是"读解析出来的那条绝对路径"。）
//
// 真实数据一条都取不到时**退回那三个固定测试名**，并把它记进诊断字 [32]：
// 纸上出现 `PROBE-MOD-A` 是"真实数据没取到"的**信号**（不是渲染坏了那类现象）。
//
// ## 纪律
//
//   * 每次调引擎前**逐字节核对入口指纹**；不符就只记失败码、**不调用**（绝不盲目跳地址）；
//   * 只读单例、只写我们自己的诊断字；**不写任何文件、不碰 SD**；
//   * **不调 `ModManager::ListMods()`**（它在真机会中断，见 `docs/开发规范.md` 第 26 条）；
//   * 整个 TU 在 `PROBE_BREAK=0` 时被编译掉（生产包不含它）。

#include <cstdint>

// `TargetModule` 在全局命名空间（`runtime/source/module_finder.hpp`）。这里只取引用参数，
// 前向声明足够 —— 不引那个头文件，免得把探针与模块扫描的依赖耦进来。
struct TargetModule;

namespace isaac::runtime::probe {

//: 诊断字（`IsaacModRuntime_NativeModsMenuProbeDiagnostics` 按固定顺序写出这些 u32）。
//: 读数工具按这些下标解析，**不要改顺序**（要加就往后加）。
struct NativeModsMenuProbeView {
    std::uint32_t armed;         // [0] 1 = 本探针编进来了（否则读数里恒 0）
    std::uint32_t presses;       // [1] ZR 按过几次（状态递增次数）
    std::uint32_t backPresses;   // [2] ZL 按过几次（状态递减次数）
    std::uint32_t state;         // [3] 当前试到的 `MenuManager::eState` 值（0..15）
    std::uint32_t manualMode;    // [4] 1 = 手动画原生页开着（第二版起由"菜单出现"自动打开）
    std::uint32_t initResult;    // [5] 手动 Init 的结果（0 未试 / 1 成功 / 2 入口守卫不符 /
                                 //     3 单例为空 / 4 模块找不到）
    std::uint32_t renderCalls;   // [6] 手动 `Menu_Mods::Render` 调了几次
    std::uint32_t lastFailure;   // [7] 最近一次失败码（0 = 没有；含义见 .cpp 的常量）
    std::uint32_t managerOk;     // [8] 1 = `g_Manager` 那句 GOT 槽读到的指针非空
    std::uint32_t menuManagerOk; // [9] 1 = `g_MenuManager` 非空（手动 Init 的前置条件）
    std::uint32_t modListBytes;  // [10] 引擎模组表 `end - begin` 的原始字节数（0 = 空表）
    std::uint32_t menuState;     // [11] 随手记的 `MenuManager+0x38`（= 状态机当前状态）
    // ---- 第二版新增（输入映射的实测结果，全部是"并集"口径）----
    std::uint32_t heldActionMask;     // [12] 扫描里被按住过的动作号位图（bit0..bit27）
    std::uint32_t heldControllerMask; // [13] 答过"是"的手柄号位图（bit0..bit31）
    std::uint32_t scanRounds;         // [14] 扫描跑了几轮（0 = 扫描没跑起来）
    std::uint32_t modListPointersOk;  // [15] 1 = 上面那对 begin/end 像合法指针（>=0x1000 且 8 对齐）
                                      //      ⇒ 0 而 [10] 也是 0 时，"空表"这个结论**不成立**
                                      //      （更可能是我们对 `Manager+0x36800` 那个结构的解释不对）
    std::uint32_t manualModsPtrOk;    // [16] 1 = `Init` 确实跑进函数体并把 ModManager 记进了
                                      //      `对象+0x170`（这是"我们的 Init 调用真的执行了"的硬证据）
    // ---- 第三版（2026-09-22，批次 036）新增：三个已知页面对象头部的坐标（原样 32 位）----
    // 用意：位置该传什么，最省的办法是看"已经摆对了的页面"的坐标。实测结果是三者都在 0 附近
    // ⇒ **位置不在对象头部**（这条结论直接推翻了"借 `Menu_Title` 的坐标"那条路子）。
    std::uint32_t titlePosX;          // [17] `Menu_Title` 内嵌成员（`MenuManager+0x670`）开头 float
    std::uint32_t titlePosY;          // [18]
    std::uint32_t optionsPosX;        // [19] `Menu_Options`（`MenuManager+0x1AF1E8`）
    std::uint32_t optionsPosY;        // [20]
    std::uint32_t keyConfigPosX;      // [21] `Menu_KeyConfig`（`MenuManager+0x1AF668`）
    std::uint32_t keyConfigPosY;      // [22]
    //: ★ 已停用（批次 040）：039 批次"六档 Y 标定"的档位号。标定**失败**（六档都不对），
    //: 根因是渲染上下文而不是位置（见 `docs/改动日志-20260922.md` 的 037 节）。
    //: 位置**保留不动**（往后加是纪律，删字段会让老读数整段错位），040 起恒为 0。
    std::uint32_t positionStep;       // [23]
    // ---- 第四版（2026-09-22，批次 040）新增：**在引擎的渲染上下文里画** ----
    std::uint32_t titleRelayState;    // [24] `Menu_Title::Render` 入口中继：0 未装 / 1 装成功 / 2 装失败
    std::uint32_t titleRelayFailure;  // [25] 上面那次安装的原始失败码（0 = 无失败；
                                      //      1 地址非法 / 2 入口 16 字节不符 / 3 竞技场满 /
                                      //      4 写回校验失败 / 5 入口含 PC 相对指令）
    std::uint32_t menuOffsetX;        // [26] `MenuManager+0x3c` 的 Vector2 X（原样 32 位）
    std::uint32_t menuOffsetY;        // [27] 同上 Y。这是**页面坐标空间 → 屏幕**的偏移：引擎自己
                                      //      每个页面 `Render` 里都做 `ldp w9, w8, [MenuManager, #0x3c]`
                                      //      再与页面自己的位置相加。
                                      //      ★ 它朝 `MenuManager::get_target_offset()` 收敛，而那个函数
                                      //      返回的是 `((画面宽-480)/2, (画面高-270)/2)`
                                      //      ⇒ **页面坐标空间是 480×270，可见屏幕比它小、居中裁切**。
    // ---- 第五版（2026-09-22，批次 041）新增：把"裁掉多少"算清楚 ----
    std::uint32_t screenWidth;        // [28] `IsaacRepentance::WIDTH`（原样 32 位 float）
    std::uint32_t screenHeight;       // [29] `IsaacRepentance::HEIGHT`
                                      //      反解：实测偏移 (-27,-15) ⇒ 426×240（正好 16:9）。
                                      //      ⇒ 可见区在页面坐标里是 x∈[27,453]、y∈[15,255]，
                                      //      页面空间的上边 15 格与左右各 27 格**是屏幕外的**。
    // ---- 第五版（2026-09-22，批次 042）新增：本页**实际**被画在哪个页面坐标 ----
    // （★ 这一节是 2026-09-23 补记的：批次 042 当时只写进了 `.cpp`，`.hpp` 这份
    //   "读数说明书"漏了两格，导致它后面所有下标都比真身**小 2** —— 新加的门禁
    //   `runtime/tests/test_probe_state_layout.py` 把这份漂移抓出来了。）
    std::uint32_t pageOriginX;        // [30] `偏移 + 本页位置 + 200`（= 传给 `ANM2::Render` 的那个点）
    std::uint32_t pageOriginY;        // [31] 目标值应是 (240, 72)：纸铺满页面框 [0,480]、上沿在顶端
    // ---- 第六版（2026-09-22，批次 043）新增：**换成真实模组名**（第 B 步）----
    //
    // 这一批只换数据源、不动渲染与位置。所以这十格就是"换成功了没有"的全部判据：
    // 前四格回答"条目是谁、有几条"，后六格回答"名字到底有没有从 `metadata.xml` 读到"。
    std::uint32_t realSourceState;    // [32] 0 还没试 / 1 ★ 用的是**真实模组**（发现结果 + `<name>`）
                                      //      / 2 真实数据没取到 ⇒ 退回那三个固定测试名 ——
                                      //      **页面上看到 `PROBE-MOD-A` 就是这个信号**，
                                      //      与"渲染坏了"（纸上什么都没有）是两件事。
    std::uint32_t realDirectoryCount; // [33] 运行时发现到几个模组目录（= 页面上该有几行）
    std::uint32_t realEnabledCount;   // [34] 其中几个是"开着"的（另外那几个走另一种颜色）
    std::uint32_t realEntryCount;     // [35] 真实条目实际造出几条（0 且 [32]=2 ⇒ 这一环断了）
    std::uint32_t metadataReadOk;     // [36] `metadata.xml` 读成功的次数 = 名字取自 `<name>` 的行数
    std::uint32_t metadataReadFailed; // [37] 解析到了挂载实体、但读失败（异常，值得查）
    std::uint32_t metadataAbsent;     // [38] 引擎说这个路径没有挂载实体 —— **正常情况**
                                      //      （`metadata.xml` 在 PC 上就是可选的）⇒ 那一行退目录名
    std::uint32_t metadataBindings;   // [39] 读文件那组绑定：0 没读 / 1 校验通过 / 2 没过
    std::uint32_t metadataResolveFn;  // [40] **挂载解析入口**（`GetMountedFilePath`）：
                                      //      0 没试 / 1 ★ 用中继记下的原函数（正常）
                                      //      / 2 用守卫过的引擎入口（中继没装时才走这条）
                                      //      / 3 两条都没拿到 ⇒ 全部退目录名
    std::uint32_t metadataExistsForm; // [41] **输入形式**（用位看，两种都出现过就两位都置）：
                                      //      位 0 = 带 `rom:/` 前缀的那种输入就被解析出来；
                                      //      位 1 = 去掉前缀才解析出来。
    // ---- 第七版（2026-09-22，批次 046）新增：在**选择界面那一列**里插入"模组"那一行 ----
    std::uint32_t modRowRelayState;     // [42] `Menu_Game::Render` 入口中继：0 未装 / 1 ★ 装成功 / 2 失败
    std::uint32_t modRowRelayFailure;   // [43] 那次安装的原始失败码
    std::uint32_t modRowSlot;           // [44] 当前选中第几格（0..5；**3 = 我们那一格**）
    std::uint32_t modRowEngineIndex;    // [45] 写回给**引擎**的索引（夹在 0..4 ⇒ 绝不让它越界）
    std::uint32_t modRowCursorFrame;    // [46] 我们让光标用的帧号（= 格子号；引擎索引到不了 5，靠这个实现）
    std::uint32_t modRowUpPresses;      // [47] 我们自己的导航：往上按过几次
    std::uint32_t modRowDownPresses;    // [48] 往下按过几次
    std::uint32_t modRowConfirmPresses; // [49] 确认按过几次
    std::uint32_t modRowConfirmOnOurs;  // [50] 其中落在**我们那一格**上的次数
                                      //      （本批只记录、不接页面：接页面是下一步）
    std::uint32_t modRowRenderCalls;    // [51] 我们在那一屏画了几帧（0 = 门控没过 / 中继没装）
    std::uint32_t modRowOnOurs;         // [52] 1 = 当前光标就在我们那一格上
    std::uint32_t modRowLayersFn;       // [53] `ANM2::GetLayer` 跳板：0 没试 / 1 ★ 拿到 / 2 没拿到
    std::uint32_t modRowFontState;      // [54] 画字入口：0 没试 / 1 ★ 拿到 / 2 没拿到
    std::uint32_t modRowManagerOk;      // [55] 1 = 拿到了 `g_Manager`（字体对象嵌在它里面）
    std::uint32_t modRowTextY;          // [56] 我们那行字画在哪个 y（原样 32 位 float）
    std::uint32_t modRowTop;            // [57] 那一格的屏幕上沿（原样 32 位 float）
    std::uint32_t modRowLabelDraws;     // [58] 我们那一行（ASCII "MODS"）画了几次
    std::uint32_t modRowCjkDraws;       // [59] 1 = 页面原点（偏移 + 页面自己的位置）拿到了；
                                      //      0 = 没拿到 ⇒ 字会画到屏幕角上
    // ---- 第八版（2026-09-22 晚，批次 055）：那一行改成**贴图** ----
    //
    // 这一版把"用字体画 MODS"换成"把游戏自己那支笔画的字**当贴图**画上去"：
    // 字是从**该语言自己的模组页美术**（`modsmenu.pcx` 标题纸带）里抠的，
    // 布局（每行挪多少、贴图落在哪、光标落点）全部由 `tools/gamemenu_mod_row.py`
    // 从该语言自己的 `gamemenu.anm2`/`gamemenu.pcx` 量出来，生成在
    // `runtime/source/mod_row_generated.hpp`（八个语言各一套）⇒ **运行时不手调任何数字**。
    //
    // 这五格是"这条链通到哪一步"的判据（贴图没画出来的话，看它们就知道断在哪：
    // 语言没定 / 入口守卫不过 / 单例空 / 引擎返回空 / 原点没拿到）。
    std::uint32_t modRowLanguageCode;   // [60] 游戏语言码（两字符原样：'z''h' ⇒ 0x0000687A）
    std::uint32_t modRowLanguageState;  // [61] 0 没试 / 1 ★ 拿到 / 2 入口守卫不过 / 3 单例空 /
                                        //      4 挑到的是 `en` 兜底（= 不是本语言的美术）
    std::uint32_t modRowImageState;     // [62] 0 没试 / 1 ★ 贴图好了 / 2 入口守卫不过 /
                                        //      3 单例或描述符空 / 4 引擎返回了空指针 /
                                        //      5 语言还没定（等下一帧）
    std::uint32_t modRowSpriteDraws;    // [63] 那一行的**美术**画了几帧 —— 内存版与 ANM2 版
                                        //      **合起来**记这一格（只记一条的话，换了路线之后
                                        //      读数会恒 0，被误读成"根本没画"）；
                                        //      0 ⇒ 没画：不是在退回画字，就是哪条路都没通
    std::uint32_t modRowSpriteOrigin;   // [64] 1 = 页面原点拿到了（0 ⇒ 贴图会画到页内绝对位置）
    std::uint32_t modRowImageAttempts;  // [65] 四种"路径形态"各自有没有拿到贴图（位 0..3）：
                                        //      位 0 = 按反汇编结论（x3 = 扩展名 "pcx"）
                                        //      位 1 = 第一版（x3 和 x4 都是文件名，已知空指针）
                                        //      位 2 = x3 = "pcx"、x4 = 文件名
                                        //      位 3 = x3 = 清干净的内容路径
    std::uint32_t modRowImageAttempt;   // [66] 实际用的是第几种（1..4；0 = 都没成）
    // ---- 第九版（2026-09-22 深夜，批次 058）：**把「模组」那一格的确认键接上** ----
    //
    // 目标（用户 2026-09-22 确认）：照 PC 的做法进入引擎的**状态 16**（模组页），
    // 并让引擎自己的翻页音/位置过渡完成跳转。这一批只做到"**能进能出**"：
    // 开关写回清单与模组页里的中文名各自另起一批。
    //
    // ★ 为什么不是"调引擎的 `Menu_Mods::Update`"：那个函数按确认会往模组目录写/删
    // `disable.it`，而卡上模组目录就在 romfs 覆盖层里（历史上"写覆盖层 ⇒ 下次启动崩"的雷区）
    // ⇒ 页面只借引擎的 `Render`，输入与开关状态由我们维护（`mod_page_nav.hpp`，有宿主门禁）。
    std::uint32_t modsPageStateCode;     // [67] 我们用的状态号（恒 16；来历见 `mod_page_nav.hpp`）
    std::uint32_t modsPageActive;        // [68] 1 = 当前由我们驱动模组页（= 引擎状态 16）
    std::uint32_t modsPageEnterCalls;    // [69] 进页面的次数（在那一格按确认）
    std::uint32_t modsPageResetState;    // [70] `Menu_Mods::Reset`：0 未试 / 1 ★ 调到 / 2 守卫不符
    std::uint32_t modsPageDrivenFrames;  // [71] 状态 16 期间驱动了几帧
    std::uint32_t modsPageSelected;      // [72] 页面 `+0x0`：当前选中第几个模组（0 起）
    std::uint32_t modsPageHoldTimer;     // [73] 页面 `+0x4`：按住计时（松手应归零）
    std::uint32_t modsPageEdited;        // [74] 页面 `+0x124`：1 = 这次进来改过开关
    std::uint32_t modsPageTogglePresses; // [75] 我们接的确认（切换开关）次数
    std::uint32_t modsPageBackPresses;   // [76] 我们接的返回次数（返回走引擎的 `SetState(3)`）
    std::uint32_t modsPageRenderCalls;   // [77] 状态 16 期间画了几帧
    std::uint32_t modsPageEntryCount;    // [78] 页面看到的模组条数
    std::uint32_t modsEnabledGate;       // [79] `g_Manager+0x36519`（模组总开关，一个字节）
    std::uint32_t modsPageScrollTargetY; // [80] `MenuManager+0x1AFF8C`：状态 16 的滚动目标（float 位）
    std::uint32_t modsPageOffsetYAtEnter; // [81] 进入那一刻的视图偏移 Y（float 位）——
                                          //      与现场 `[27]` 比，就知道引擎有没有在滑
    // ---- 第十版（2026-09-22 深夜，批次 059）：把引擎的"模组总开关"置上 ----
    //
    // 真机读数（058 的第一次现场）发现 `g_Manager+0x36519` 是 **0**，而 `Menu_Mods::Render`
    // 在它为 0 时**只用一个颜色画所有行**（根本不读条目自己的 `+0x138` 启用位）
    // ⇒ "按确认切换开关"在屏幕上**看不出来**。进页面时把它置 1（与 PC 的语义一致）。
    std::uint32_t modsGateWritten;       // [82] 1 = 我们把它置过（0 = 没读到 `g_Manager`）
    std::uint32_t modsGateBefore;        // [83] 置之前它是什么（留证：它本来是 0 还是 1）
    // ---- 第十一版（2026-09-22 深夜，批次 060）：**"按了确认却没进模组页"要能一眼定位** ----
    //
    // 用户实测反馈：在「模组」那一格按确认，**跳到了统计页面**（引擎按它自己的索引 3 处理了）。
    // 说明"我们那一格的接管"中途退出了；这几格就是"退在哪一步"的直接证据。
    std::uint32_t modRowLastConfirmSlot; // [84] 最后一次确认按下时**我们**在第几格（0..5）
    std::uint32_t modEntryOutcome;       // [85] 接管退在哪：0 没被调用 / 1 页面没准备好 /
                                         //      2 不在选择界面 / 3 ★ 进了状态 16 / 4 没进去
    std::uint32_t modEntrySwallowed;     // [86] `SetState` 中继替我们那一格挡掉的次数
    std::uint32_t setStateRelayState;    // [87] `SetState` 入口中继：0 未装 / 1 ★ 装成 / 2 失败
    // ---- 第十二版（2026-09-23，批次 061）：**"我们调 SetState 到底调到了没"要有数** ----
    // 批次 060 的 bug：装了中继后入口 16 字节被改写 ⇒ `ApplyState` 里逐字节守卫必然失败
    // ⇒ `SetState` 根本没被调用，而失败码又被渲染回调每帧清掉 ⇒ 现象只是"按了没反应"。
    std::uint32_t applyStateCalls;        // [88] `ApplyState` 真正把 `SetState` 调出去的次数
    std::uint32_t applyStateGuardFailures; // [89] 因入口逐字节守卫不过而**没调**的次数
    // ---- 第十三版（2026-09-23，批次 062）：过渡动画 —— 纸「跟着画布走」（只画在状态 16） ----
    std::uint32_t modsPageFixedY;        // [90] 进入页面后定下来的「本页位置 Y」（float 位）
    // ---- 第十四版（2026-09-23，批次 063）：位置「两个方向都跟着画布走」的自证 ----
    std::uint32_t modsPageTargetOffsetX;  // [91] 我们算出的「状态 16 目标偏移」X（float 位）
    std::uint32_t modsPageSettledOffsetX; // [92] 画布停稳时现场偏移的 X（float 位）——与 [91] 比
    std::uint32_t modsPageCorrection;     // [93] 停稳后自证时的位置修正量（float 位，0 = 没修）
    // ---- 第十五版（2026-09-23，批次 067）：开关写回（走运行时既有的开关服务）----
    // 落盘位置 = **游戏存档分区**（不是卡上的资源覆盖层）；时机 = 退出页面时一次（用户裁定）。
    std::uint32_t toggleSetCalls;         // [94] 页内改开关（只改内存）的次数
    std::uint32_t toggleSetFailures;      // [95] 其中被拒/失败的次数
    std::uint32_t toggleSaveState;        // [96] 退出时那次落盘：0 没试 / 1 ★ 成功 / 2 失败
    // ---- 第十六版（2026-09-23，批次 068/069）：关卡切换会废掉我们那一行的**内存**贴图句柄 ----
    // 用户实测：进过部分对局再退出，只有「模组」那一行的字消失（纸和其它行都在），重启即好。
    // 触发点（069 更正）：**关卡/房间事件的派发计数**变化 —— 068 用"`Game*` 有没有值"当判据，
    // 真机上一次都没触发（回到菜单时那个指针并不变 0）。
    std::uint32_t modRowImageReloads;     // [97] 因关卡/房间事件重载那一行**内存**贴图的次数
    std::uint32_t gamePresent;            // [98] `Game*` 有没有值（1 = 在局内；留证，不是判据）
    std::uint32_t levelEventCount;        // [99] `MC_POST_NEW_LEVEL` 派发过几次（判据留证）
    // ---- 第十七版（2026-09-23，批次 071）：那一行改成**引擎自己的「按路径加载」** ----
    //
    // 真机上"跑过若干次对局之后那一行变透明"的根因：我们是全工程**唯一**"从内存加载贴图、
    // 并且用自造名字当缓存键"的地方；引擎自己的行、以及所有模组（EID 等）都是**按磁盘路径**
    // 加载（`ANM2::Load`），它们从不会消失。关卡加载会清掉"没有磁盘文件背书的贴图"。
    //
    // ⇒ 构建期把图落成真实文件（`tools/emit_mod_row_art.py`，构建步骤挂在 `runtime/Makefile`
    //   的 `mod-row-art` 上），运行期改用引擎的**按文件名版**贴图加载
    //   `ImageManager::LoadImage(char const* path, ...)`（和我们一直在用的内存版同一个管理器、
    //   同一个返回值形状）。内存那条路线**保留作兜底**，行为一字不改。
    //
    // ★★ 为什么不是上一批（071）那条 `ANM2::Load` + `ANM2::Render`：**真机上它崩了**。
    //    崩溃报告 `dist/crash-reports-20260923/01790100127_010021c000b6a000.log` 里
    //    `Data Abort @ 0x0`，栈为「我们的绘制函数 → `ANM2::Render` → `AnimationLayer::RenderFrame`
    //    → `GetSourceQuad`」⇒ `.anm2` 找到了（否则我们根本不会去画），但精灵表没载进来：
    //    引擎按 `<Spritesheet Path="mod_row_zh.png">` 找的是 **`.png`**（模组都是 `.png` 与同名
    //    `.pcx` 都放），我们只放了 `.pcx`。**教训：空的东西绝不拿去画。**
    //
    // 这九格就是"新路线通到哪一步"的全部判据 —— 断了的话看它们就知道断在哪一步：
    // 管理器/守卫 → 四条候选路径 × 两种 flag 哪条命中 → 贴图到底拿到没有。
    std::uint32_t modRowFileState;        // [100] 0 没试 / 1 ★ 装好（绘制优先用它）/
                                          //       2 入口守卫不过 /
                                          //       3 管理器指针与顶点描述符还没取到 /
                                          //       4 所有候选都返回空（引擎没找到文件）/
                                          //       5 语言还没定（等下一帧，不是失败）
    std::uint32_t modRowFileCandidate;    // [101] 命中的候选序号（1..8；0 = 都没成）
    std::uint32_t modRowFileHits;         // [102] 命中掩码（4 条路径 × flag 0/1 = 8 位）
    std::uint32_t modRowFileLoadCalls;    // [103] 文件版 `LoadImage` 调了几次（含失败候选与重读）
    std::uint32_t modRowFileDraws;        // [104] 用这张（磁盘来的）贴图画了几帧
    std::uint32_t modRowFileReloads;      // [105] 因关卡/房间事件**从磁盘重读**的次数
                                          //       （★ 这一格就是"重读判据生效了"的留证）
    std::uint32_t modRowFilePathLength;   // [106] 命中那条**路径的长度**（0 = 还没命中）
    std::uint32_t modRowFileFlag;         // [107] 命中那一次的 `flag` 取值（0 或 1）
    std::uint32_t modRowFileGuardState;   // [108] 入口守卫：0 没试 / 1 过 / 2 不过
    // ---- 第十八版（2026-09-23，批次 075）：那一行**改由引擎自己画**（用户定案 A 路线）----
    //
    // 换路线的理由：引擎自己的图层用 `ANM2::LayerState::SetSpriteSheet(SmartPointer<ImageBase>)`
    // 持有**真正的引用计数**；我们那份是 16 字节裸拷贝（不加引用、也不释放）⇒ 管理器一放手，
    // 对象就被回收（显存缓冲清零、对象内存还看着正常）—— 与现场读数逐条吻合。
    //
    // 做法：把 PC 版**本来就有**、Switch 版删掉的 `Item6` 那一层按 PC 的数值补回
    // `gamemenu.anm2`（`tools/gamemenu_mod_row.py --emit-menu-anm2`，有逐字节门禁），
    // 于是那一行由引擎自己的**整页**渲染画出来，生命周期与其余五行同源；
    // 我们那几条兜底绘制只在**没有这一层**时才用（覆盖层没装/被回退时行为一字不变）。
    std::uint32_t modRowNativeLayer;      // [109] 0 还没看 / 1 ★ 引擎那份动画里有第六层
                                          //       （那一行由引擎画，我们不画）/
                                          //       2 没有这一层（退回我们自己的兜底绘制）
};

//: 更新中继每帧调一次（读输入、动状态；自动模式下在这里做一次 `Init`）。
void NativeModsMenuProbeUpdate() noexcept;
//: 安装时调一次（模块初始化线程、游戏主循环尚未开始）：在 `Menu_Title::Render` 的**函数入口**
//: 挂入口中继，让我们的原生页画在**引擎自己的渲染上下文**里。
//: 为什么挂函数入口而不是改那个调用点：`bl Menu_Title::Render`（文件偏移 `0x3FE8AC`）在整份
//: 游戏模块里是**唯一**引用它的一处（全模块扫 `bl/b` 只有这一处、直接跳 `0x41A574` 的 0 处、
//: 重定位表里指向它的引用 0 处 ⇒ 没有虚表/函数指针路径）⇒ 两者语义完全相同。而入口中继
//: **零占用游戏字节**、复用现成的逐字节守卫与失败码，也不必新增一份 IPS
//: （游戏映像的代码洞只剩 0x30 字节、零余量）。
void NativeModsMenuProbeInstallRelay(const TargetModule& module) noexcept;

} // namespace isaac::runtime::probe
