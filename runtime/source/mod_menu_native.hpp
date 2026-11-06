#pragma once

// **生产版**的「模组」那一行 + 模组页（2026-09-23，批次 076）。
//
// ## 这一批是什么
//
// 用户 2026-09-23 定案：把「模组那一行 + 模组页 + 中文字体接线」**整块**从探针搬进生产代码
// （规格：`docs/设计-模组页搬生产-20260923.md`）。为什么不能拆开搬：那一行的"显示"依赖覆盖层里
// 的 `gamemenu.anm2`（引擎自己画第六层 `Item6`），而"选中/按确认进模组页"与模组页本体是
// **同一套状态机与输入处理**；只搬一半的中间态要么"能选中但按确认没反应"，要么"那一行根本不出现"。
//
// **行为真值源**是探针 `runtime/source/probe/native_mods_menu_probe.cpp`（3021 行）：全部引擎偏移、
// 16 字节守卫、做法与踩过的坑都写在它的注释里，真机已经验收过一轮。本文件是"照它的行为重写一遍、
// 去掉诊断"，**不是复制粘贴**。四处刻意的差别（都在 `.cpp` 里逐条写明理由）：
//   1. 诊断字 → 一个**外部链接**的状态面结构体（`g_ModMenuState`，读数工具按它取）；
//   2. **不搬**探针里那两条"贴图路线"（内存版 `LoadImage`、磁盘版 `LoadImage`）——
//      075 之后那一行由引擎自己画，那两条已是死路（真机崩过），搬过去只会扩大风险面；
//   3. **不搬**探针里那段"把扩展字体装进引擎字体对象"的接线（077 搬过、真机推翻 ⇒ 078 撤掉）：
//      模组页用的是**按字节**的画字重载，换字体救不了中文，代价却是多 32MB 字图集；
//   4. 语言码**每帧都问**（077 是"一次定死"）：用户实测在选项页换语言是当场生效的，
//      而模组页那张纸是分语言的 ⇒ 变了就换布局 + 重新 `Init` 一次页面（只 `Init`、不 `ctor`）。
//
// ## 三个入口中继（生产走挂点登记表，不自己装）
//
// 探针在安装函数里自己调 `TryInstallEntryRelay`；生产版把这三个靶点登记进
// `domain/runtime/hook_catalog.hpp`（`MenuGameRender` / `MenuTitleRender` / `MenuManagerSetState`），
// 由 `HookInstallService` 统一安装。⇒ **探针构建里必须跳过这三条**（否则同一入口装第二次必然
// `EntryMismatch`，探针自己那套就失效了）：判据在 `hook_manager.cpp` 的 `SkipOptionalHooksPredicate`。
//
// ## 纪律（照 AGENTS.md 与探针）
//
//   * 每次调引擎前**逐字节核对入口指纹**；不符就只记失败码、**不调用**（绝不盲目跳地址）；
//   * **只改内存、不写文件** —— 唯一例外：离开模组页时调一次既有的 `ModMenuSaveToggles()`
//     （它写的是**游戏存档分区**，不是卡上的资源覆盖层）；
//   * 写回引擎的选中索引**永远夹在 0..4**；
//   * 判"引擎那份动画里有没有我们那一层"**只能读 `ANM2+0xB0` 的图层数**；
//   * 不搬假数据（生产里"一个模组都没发现"就是空表，绝不往玩家屏幕上写测试名）。

#include <cstdint>

// `TargetModule` 在全局命名空间（`runtime/source/module_finder.hpp`）。这里只取引用参数，
// 前向声明足够 —— 不引那个头文件，免得把模块扫描的依赖耦进来（与探针同一口径）。
struct TargetModule;

namespace isaac::runtime::modmenu {
// 本体STB加载成功后的原生模组房间收尾；仅在同一游戏线程调用。
void LoadEngineModRoomsAfterStage(void* config, int stage, int mode) noexcept;
void LoadEngineModItemPools(void* pool) noexcept;
extern std::uint32_t g_ModRoomLoadState[8];

//: **常驻状态面**：真机读数的抓手（读数工具 `tools/read_device_state_via_gdb.py` 按名字取这个符号）。
//:
//: ★★ 两条纪律（都不是风格问题）：
//:   1. **必须外部链接**：`extern "C"` + 固定符号名 `g_ModMenuState`。放进匿名命名空间的话
//:      `nm` 查不到（2026-09-19 的 D6 事故），读数就只能报"读不到"；
//:   2. **字段顺序即读数工具的下标，加字段只能往后加**：删字段/插字段会让老读数整段错位，
//:      而错位在读数里表现为"某几格莫名非 0"，比报错难查得多。
//:
//: 全部字段都是 `std::uint32_t`（浮点按**位模式**存，读数端再解成浮点）。
struct State {
    std::uint32_t armed;             // [0]  1 = 本功能编进来了（生产构建恒 1）
    std::uint32_t relayInstalled;    // [1]  三个入口中继的安装结果位图：
                                     //      bit0 `Menu_Game::Render` / bit1 `Menu_Title::Render`
                                     //      / bit2 `MenuManager::SetState`（0b111 = 三个都装上）
    std::uint32_t failure;           // [2]  最近一次失败码（0 = 没有；枚举见 .cpp，与探针同一套语义）
    std::uint32_t rowOwner;          // [3]  那一行的归属：1 = 引擎在画（覆盖层生效）
                                     //      / 2 = 我们在兜底画
    std::uint32_t rowDrawFrames;     // [4]  我们**真的画出了东西**的帧数
                                     //      （★ 引擎在画时必须恒 0 —— 画了就是两层叠在一起）
    std::uint32_t rowFallbackFrames; // [5]  我们走了兜底绘制这条路的帧数
                                     //      （含"字体没拿到 ⇒ 什么都没画"的那些帧，所以 ≥ [4]）
    std::uint32_t languageCode;      // [6]  语言码（四字符打包，与探针同口径：'z''h' ⇒ 0x0000687A）
    std::uint32_t slot;              // [7]  当前格子（0..5，**3 = 我们那一格**）
    std::uint32_t engineIndex;       // [8]  写回引擎的**行号**（必须恒在 0..4）
    std::uint32_t confirmOnOurs;     // [9]  确认落在我们那一格上的次数
    std::uint32_t pageEnterCalls;    // [10] 模组页进过几次
    std::uint32_t pageBackCalls;     // [11] 模组页返回过几次
    std::uint32_t pageDrivenFrames;  // [12] 模组页被我们驱动的帧数
    std::uint32_t entryCount;        // [13] 条目数（页面上该有几行）。
                                     //      ★ 批次 126 起**含下标 0 那一行**（控制台总开关）⇒
                                     //      比"发现到的模组数"多 1；模组显示成第 2 行起。
    std::uint32_t selectedEntry;     // [14] 当前选中项
    std::uint32_t toggleSaveState;   // [15] 开关写回结果（0 没写 / 1 成功 / 2 失败）
    std::uint32_t fontObjectWrites;  // [16] 我们**改写过几次引擎自己的字体对象**（`g_Manager + 0x117120`）。
                                     //      ★ 077 曾把一份带中文字形的扩展字体装进去换中文；
                                     //      真机证明那一页用的是**按字节**的画字重载
                                     //      （`Font::DrawStringScaled`，一个字节当一个字形编号）
                                     //      ⇒ 换字体救不了中文，代价还多 32MB 字图集 ⇒ 078 整个撤掉。
                                     //      ⇒ 这一格**恒 0**，它的意义就是"这条纪律还在"。
                                     //      （字段名与编号都保持 077 的位置不动：编号只能往后加。）
    std::uint32_t setStateSwallowed; // [17] `SetState` 中继挡下过几次（保险生效的计数）
    std::uint32_t pageOriginX;       // [18] 页面原点 X（浮点位模式）
    std::uint32_t pageOriginY;       // [19] 页面原点 Y（浮点位模式）
    std::uint32_t languageSwitches;  // [20] 语言码**变过**几次（0 = 没换过语言）
                                     //      ★ 用户在选项页里换语言是当场生效的 ⇒ 我们每帧问一次
                                     //      语言码，变了就换布局 + 重载模组页那张纸（它是分语言的）。
    std::uint32_t pageReloads;       // [21] 因"语言变了"重新载入过模组页几次（`Menu_Mods::Init`）
                                     //      ★ 重载本身只换得了**贴图**；动画**排版**是引擎按路径哈希
                                     //      缓存的（路径串一样分不出语言）⇒ 还得照引擎协议做那三步
                                     //      （Pre 放开引用 → `AnmCache::FreeUnreferenced*` 回收 → Post 重载），
                                     //      **083 起已在做、真机三条全过**。079 曾被 080 以"把 EID 的
                                     //      信息显示搞坏了"为由撤回，但**那是误判**（真凶是 082 修的
                                     //      "换语言后丢 Mod 挂载点"）⇒ 别再按旧说法"退回不做"（见 `.cpp` 那段历史）
    // ---- [22]..[25]：2026-09-23 定位"换语言后 EID 坏掉"时加的观测（**只读**，不改引擎行为）----
    std::uint32_t mountRelayFired;      // [22] 引擎重建挂载点表之后，我们那个"重新挂回去"的中继跑过几次。
                                        //      ★ 它应当跟着重建次数一起涨；恒 0 = 中继没装上或没被调到。
    std::uint32_t mountRelayFailures;   // [23] 上面那些次里 `RemountAll()` 报错几次（**必须恒 0**）
    std::uint32_t mountServicePublished; // [24] 1 = 会话内容挂载服务**已发布**（中继拿得到实例）。
                                         //      ★ 这一格就是 2026-09-23 那个 bug 的判据：
                                         //      `SetSessionContentMountService(...)` 以前**从没被调用**
                                         //      ⇒ 指针恒空 ⇒ 重建之后**一个 Mod 挂载点都不恢复**
                                         //      ⇒ 换语言后 EID 的字体文件打不开（详见 `.cpp`）。
    // ---- [25]..[32]：2026-09-23 加的观测（**只读**，不改引擎行为）----
    //
    // ★★ 这些格子的**顺序就是读数工具的下标契约**（`read_device_state_via_gdb.py` 按号打印）。
    //    2026-09-23 我自己在这里踩过一次：加新格子时"插在锚点之前"，把后面所有下标都往后挪了，
    //    结果读数里每一行都读到了**别的格子**（"成就已解锁=是"其实读的是"禁成就那一格"），
    //    连着几轮的解读全部作废。⇒ 加格子**只能往后追加**，且顺序由门禁钉住
    //    （`test_state_surface_field_order_is_pinned`）。
    std::uint32_t lastFontLoadWord;     // [25] 最后一次 `Font:Load` 的打包结果（`font_api.cpp` 的
                                        //      `LastFontLoadWordForProbe`）：bit0 = 引擎接受了、
                                        //      bit1 = 是干净的挂载相对名、bits8..15 = 路径长度、
                                        //      bits16..47 = 路径前 4 字节。
    std::uint32_t achievementsDisallowed; // [26] 1 = 按 PC 规则**本局该禁**成就
                                          //      （判据 = 有真实模组**实际加载** 且 成就 #4 未解锁）。
                                          //      ★ 2026-09-24 批次 098 起它只是**查询结果**（给读数看），
                                          //      我们不再往引擎里写任何字节 —— 真正落地由
                                          //      `SetReadOnly` 入口中继那一步完成。
    std::uint32_t metadataRootRelativeHits; // [27] 用**应用根相对名**解析 `metadata.xml` 成功几次
                                            //      （现在的口径，应当 > 0）
    std::uint32_t metadataPrefixedHits;     // [28] 只有带 `rom:/` 前缀那种成了几次（> 0 ⇒ 口径要调）
    std::uint32_t metadataMisses;           // [29] 两种都没解析到几次（那几行会退成**目录名**）
    std::uint32_t activeRealMods;           // [30] 运行层**实际加载**的真实模组个数
                                            //      （不含运行时自身与它自带的菜单模组）
                                            //      ★ 它参与决定 [26]：0 ⇒ 不锁成就。
                                            //      口径 = `ModMenuActiveCount()`（启动时 `ModMenuMarkActive`
                                            //      标出来的那批）。2026-09-24 用户选定"按实际加载算"，
                                            //      不再按模组页开关的持久状态算（关掉开关要重启游戏才生效）。
    std::uint32_t wombAchievementUnlocked;  // [31] 1 = **成就 #4 已解锁**（= 打过妈妈，解锁"子宫"那一章）
                                            //      ★ PC 那条规则的第二半：`有模组开着 && !这一格` ⇒ 锁成就。
                                            //      取值方式 = **直接读持久位**（`Manager+0x18+0x28+4`）——
                                            //      **不许**调 `Unlocked()`（它掺了本局状态，087 的教训）。
    std::uint32_t achievementSample;        // [32] 成就位数组的抽样（`PersistentGameData+0x28` 起 4 字节，
                                            //      id 0..3 各占一字节）—— **读数里自证位置没读错**：
                                            //      这一格只应出现 0/1；出现别的值说明偏移不对。
    std::uint32_t persistentReadOnly;       // [33] 我们写进 `PersistentGameData+0x1` 的"只读/不许解锁成就"位
                                            //      ★★ **这才是真正挡住成就的那一位**：`TryUnlock` 只查它
                                            //      （`0x4393E8`：`ldrb w8,[x0,#1]; cbnz → 拒绝解锁`），
                                            //      而 Switch 移植版把这条链掐断了（那个设置器是空实现、
                                            //      `check_game_data_modified` 是死代码）⇒ 真机上它**恒为 0**。
    std::uint32_t drivenFrames;             // [34] **每帧 +1 的计数器** —— 唯一能证明"我们的每帧更新
                                            //      还在跑"的一格。★ 2026-09-23 的教训：状态面里那些
                                            //      "看起来对"的值**可能全是旧的**（写进去之后再没更新过），
                                            //      光看它们分不清"代码在写、引擎又清了"和"代码根本没在跑"。
                                            //      判据：隔几秒读两次，这一格必须**在涨**。
    // ---- [35]..[39]：成就闸门的五格计数（2026-09-24 批次 097 加、098 改接新挂点）----
    //
    // ★ 批次 098 起闸门挂在 `PersistentGameData::SetReadOnly`（唯一写只读位的地方）上，
    //   所以这五格的含义随之改成"那道关卡被走到没有、是谁让它锁的"：
    //   ① [35] 恒 0 ⇒ 引擎开局根本没调 `SetReadOnly`（闸门位置不对）；
    //   ② [36] 涨 = 引擎自己本来就要锁（特殊种子 / 挑战局）；[37] 涨 = 我们按 PC 规则抬成锁；
    //   ③ [38] = 最后一次真正写下去的值（1 = 本局不给成就），[39] = 1 ⇒ 拿不到回退入口。
    //   （097 时它们是"拦 `TryUnlock`"那套的计数，那套已按用户裁定撤掉。）
    std::uint32_t setReadOnlyCalls;         // [35] 闸门中继**被调到**几次（`SetReadOnly` 入口）
    std::uint32_t setReadOnlyEngineLocked;  // [36] 上面那些次里，**引擎原参数就是"锁"**几次
    std::uint32_t setReadOnlyForcedByPc;    // [37] 上面那些次里，**我们按 PC 规则抬成"锁"**几次
    std::uint32_t setReadOnlyLastValue;     // [38] 最后一次**真正写下去**的值（1 = 本局不给成就）
    std::uint32_t setReadOnlyOriginalMissing; // [39] 1 = 出现过"拿不到回退入口"（此时我们**什么都不写**
                                            //      ⇒ 退回 Switch 原生行为，宁可不禁也不误禁）
    // ---- [40]：2026-09-24 批次 107 加（判据口径改成 PC 语义之后必须能分开看）----
    std::uint32_t enabledRealMods;          // [40] 处于**启用状态**的真实模组个数（口径 = 模组页开关那一份，
                                            //      **不看有没有重启**）。
                                            //      ★★ 「该不该禁成就」的判据自批次 107 起就是它 ——
                                            //      与 PC 的 `ModManager::AchievementsLocked()` 同口径
                                            //      （走模组列表里**每一项的启用位**）。
                                            //      ★ 为什么必须与 [30] 分开：两者回答不同的问题 ——
                                            //      [30] 是"本局开机时**真的加载了**几个"，
                                            //      这一格是"**现在开着**几个"。真机实测（批次 107 的由来）：
                                            //      开关打开但还没重启时 [30] = 0 而这一格 = 1，
                                            //      用 [30] 当判据就会**漏判**（开着模组进局却照样给成就）。
    // ---- [41]..[44]：2026-09-24 批次 116 加的"发现清单自证"四格 ----------------------
    //
    // 为什么加这四格：批次 107 的判据吃的是"发现清单 × 启用位"，而待修记录里出现过一对
    // **互相矛盾的读数** —— `[40] 启用状态 = 0`，可 `ModToggleService::Load()` 的原话是
    // "第一次运行：没有状态就是**全都开着**"（那时 [40] 应当 ≥ 1）。光看 [30]/[40] 这两个
    // **汇总数**分不出到底是哪一种：
    //   * [41] == 0 且 [44] == 1 ⇒ **发现了但一条都没有**（判据永远看不到模组）；
    //   * [41] == 0 且 [44] == 0 ⇒ **发现这一步根本没跑到**（`ModMenuPublishDiscovered` 没被调）；
    //   * [41] > 0 且 [42] == 0 ⇒ 每一条都被开关服务判成"关闭"（状态文件写着全禁用）；
    //   * [43] 用来与真机现实对账：模组确实在跑时它必须非 0（否则"清单里有名字"这一条是假的）。
    std::uint32_t discoveredRealMods;       // [41] 发现清单里的真实模组**条数**
                                            //      （口径 = `ModMenuDiscoveredCount()`，与 [30]/[40] 同一份清单）
    std::uint32_t discoveredEnabledMask;    // [42] bit i = 清单里第 i 条**现在开着**
                                            //      （开关服务 `IsEnabled`；清单容量 32 ⇒ 一个 u32 位图正好）
    std::uint32_t discoveredActiveMask;     // [43] bit i = 清单里第 i 条**本局开机时真的加载了**
                                            //      （与 [30] 同一批，位图的意义是能看出**是哪几条**）
    std::uint32_t discoveryDone;            // [44] 1 = 模组发现**已经出过结果**
                                            //      （`ModMenuPublishDiscovered` 调过一次就是 1）。
                                            //      ★ 与 [41] 合起来才能区分"发现了但没有"
                                            //      与"发现这一步根本没跑到"（这两种的处置完全不同）。
    // ---- [45]..[50]：2026-09-25 批次 117 加的「局内单向闩锁」六格 ----------------------
    //
    // 用户要的语义（2026-09-24 原话的意思）：**一局之内**，只要出现过"没打过妈腿
    // 且开着模组"，那么**即使之后把模组关掉，这一局也一直禁成就**。
    // ★ 这比 PC 严（PC 是开局问一次、之后不动），是用户在两个方案里明确选的"局内单向"。
    //   口径：闩锁**只吃开关状态**（与 [40] 同一个真源 = `ModToggleService`），
    //   与"本局实际加载过几个"（[30]）无关。
    std::uint32_t runLatch;                 // [45] 闩锁当前值（1 = 这一局锁着成就）
                                            //      ★ 判据本身（`AchievementsShouldBeBlockedFor`）就短接在它上面。
    std::uint32_t runLatchSets;             // [46] 本会话闩锁**置位**过几次（0→1 的次数）
                                            //      ★ 出现 0→1 的那一帧我们会**主动**写一次只读位
                                            //      （否则"中途开启模组"这一局引擎不会再写它）
    std::uint32_t runLatchResets;           // [47] 本会话闩锁**清零**过几次（= 我们看到的"局边界"次数）
    std::uint32_t runLatchResetSource;      // [48] 上一次**局边界**的种类（见 `RunBoundaryKind`）：
                                            //      1 = 开新局（真清零）/ 2 = 继续同一份存档（接回留存）
                                            //      / 3 = 出局（把闩锁留成"留存"）
                                            //      ★ 为什么要有它：三种边界的处置**不同**，
                                            //      现场分不清是哪种时无法判断"清零点有没有生效"。
    std::uint32_t gameExitCalls;            // [49] `GameExit` 入口中继**被调到**几次
                                            //      ★ 这一格是"清零点确实会在退出时触发"的**证据**：
                                            //      恒 0 ⇒ 那个挂点没装上或没被走到（而闩锁的清零
                                            //      就少了一路，见 `.cpp` 里 `RunLatchArmed` 那段）。
    std::uint32_t runLatchArmed;            // [50] 1 = **闩锁生效**；0 = 因 `GameExit` 挂点缺席而**停用**
                                            //      ★ 为什么要有这条降级：`GameStart` 是 `Game::Start`
                                            //      **返回之后**才回调我们的，而引擎那次写只读位在
                                            //      `Game::Start` **体内** ⇒ 只靠它清零时，上一局的闩锁
                                            //      会渗进新局（真机现象 = "关着模组的新局照样不给成就"）。
                                            //      `GameExit` 严格早于下一局的任何写位，能堵住它；
                                            //      它缺席时**宁可退回批次 107 的实时判据**（比 PC 松），
                                            //      也不要出现"误锁"。
    // ---- [51]..[53]：2026-09-25 批次 118 加的三格（117 的**第一次真机读数**暴露的缺陷）----
    //
    // 那次读数的现场：人还在**主菜单**（`[3]` 引擎在画那一行、`[13]` 条目 5 条、`[35]` 引擎
    // 一次没调过 `SetReadOnly`、`[47]/[49]` 都没动过），可闩锁**已经被置位**（`[45]=1 / [46]=1`）
    // ⇒ "开机时开着模组、进局前把模组关掉"这一局会被误锁，而用户在开工单里明确选的是"**不锁**"
    // （裁定①）。根因 = 观察点没有"在一局里吗"这道闸门。
    std::uint32_t runInProgress;            // [51] 1 = 现在在**一局里**（`GameStart` 之后、`GameExit` 之前）
                                            //      ★ 闩锁**只在一局里观察**：不在一局里时"开着模组"
                                            //      什么都不代表（那只是菜单上的开关状态）。
                                            //      这一格就是现场判断"闩锁为什么没置位"的答案：
                                            //      0 = 不在局里（还没开局/已回菜单），1 = 在局里但条件不成立。
    std::uint32_t runLatchEdgeWrites;       // [52] 边沿（0→1）时**试着**主动写只读位几次
                                            //      （含"拿不到回退入口所以没写成"的那些次数）
    std::uint32_t runLatchEdgeWriteResult;  // [53] 上一次边沿写位的结果：
                                            //      0 = 还没试过
                                            //      1 = 写了、且**写后当场读回确认是 1**（★ 最想要的值）
                                            //      2 = 拿不到回退入口 ⇒ 什么都没写（降级，不会误禁）
                                            //      3 = 写了但读回**不是 1**（⇒ 那个地址不对，
                                            //          或写下去被立刻清了 —— 要按"偏移/时机"查）
    // ---- [54]..[55]：2026-09-25 批次 119 加的两格（用户裁定"继续同一份存档也算同一局"）----
    std::uint32_t runLatchCarriedOver;      // [54] **留存**：出局那一刻闩锁是几（1 = 这一份存档
                                            //      在这一局里被污染过）。下一次"继续"会把它接回来。
                                            //      ★ 为什么要"留存"而不是让闩锁一直亮着：开新局时
                                            //      引擎那次写只读位发生在我们清闩锁**之前**
                                            //      （在 `Game::Start` 体内）⇒ 若不清掉留存，
                                            //      "关掉模组后开新局"会被**误锁**（违反用户选的裁定①）。
    std::uint32_t runLatchResumes;          // [55] 把留存接回来过几次（= 用户做过的"退出→继续"次数）
                                            //      ★ 接回来时**必须补写一次锁**：引擎那次开局写位
                                            //      在我们接回来之前就发生了，不补写就等于没生效。
    // ---- [56]..[57]：2026-09-25 批次 120 加的两格（用户裁定"比 PC 严"：**跨重启**也保持）----
    //
    // 上面那颗闩锁只在内存里，**重启游戏/主机就没了**。用户 2026-09-25 明确要跨重启：
    // "这一份存档只要在妈腿未解锁时用过模组，之后关掉模组、甚至重启，都继续禁成就，直到开新局"。
    // ⇒ 把标记写进**存档分区**里一个专属小文件（`isaac-runtime-run-taint.txt`，
    //   与 `isaac-switch-mods-state.txt` 同一种做法，**不碰**引擎的存档结构体）。
    // ★ 它不是 PC 的原样（PC 是开局那一刻的实时查询，不持久化任何"污染"标记）——
    //   这是用户选定的"比 PC 严"的自有语义，见 `domain/runtime/run_taint_marker.hpp` 的文件头。
    std::uint32_t taintFileState;           // [56] 我们认为**文件里**现在是什么：0 = 还不知道
                                            //      / 1 = 污染过 / 2 = 干净
                                            //      ★ 置位那一帧会写 1；开新局会写 0（清掉）。
    std::uint32_t taintFileFailures;        // [57] 读/写那个文件**失败**过几次（含端口不可用）
                                            //      ★ 必须恒 0 才说明"这条路是好的"；
                                            //      读失败按**干净**处理（fail-open：宁可不禁也不误禁）
    // 批次 135（2026-09-26）加的两格：**本模块自己的堆**还剩多少 / 用了多少字节。
    // 由来：`PngToPcx` 的转码峰值曾撞满堆 ⇒ `std::bad_alloc` ⇒ 崩溃（2026-09-25 无声卡死 /
    // 09-26 崩溃报告）。有了这两格，"是不是堆撞满"在现场直接可读，不用再靠推断。
    // 口径 = newlib `mallinfo()`（`arena` = 堆总量、`fordblks` = 其中空闲）；每 60 帧更新一次。
    std::uint32_t heapFreeBytes;            // [58] 空闲字节数（0 = 宿主构建或还没采到）
    std::uint32_t heapUsedBytes;            // [59] 已用字节数 = `arena - fordblks`
    // 批次 153（2026-09-27）加的一格：**"把模组 content 喂给引擎"这件事是从哪个时机跑起来的**。
    //   0 = 还没跑过；1 = **模组脚本执行之前**（正确时机）；2 = 进模组页那一刻（兼容兜底）。
    // 为什么必须能从读数里分开：真机已经证明【时机】才是成败关键 —— 148b 那次喂成功了（容器
    // 132 → 155），但模组的 `danceCostumes` 早就在它自己的 Lua 文件一加载时查成了 `-1`
    // （43 次查询、0 次命中），再也没查第二次 ⇒ 服装照样不换。没有这一格，
    // "喂成功了但喂晚了"与"压根没喂"在读数里长得一样。
    std::uint32_t modEngineTrigger;         // [60] 见上（1 = 模组脚本之前 / 2 = 进模组页 / 3 = 每帧重试）
    // 批次 154（2026-09-27）加的一格：**"模组脚本之前"那一次**走到了哪一步。
    // ★ 值域（批次 155 把"跑完"与"喂进去了"分开，154 那一版**误导过一次**）：
    //   0 = 没跑过 / 1 = 两个入口已解析 / **2 = 跑完且容器涨了（真喂进去了）**
    //   / 3 = 失败 / **4 = 跑完了但两个容器一条没涨**（文件没打开 / 路径不对 / 挂载没就绪）。
    // 为什么要单独留：`g_ModEngineScanStage` 会被后面的重试覆盖 ⇒ "早期那次到底成没成"读不出来；
    // 而"服装编号是模组在自己 Lua 文件里查死的"⇒ 只有"早期那次真喂进去了"才可能有舞。
    std::uint32_t modEngineEarlyStage;      // [61] 见上
    // 批次 159（2026-09-27）加的两格：**引擎说"继续游戏"现在可不可选**。
    // 由来：没有可继续的局时，引擎自己会跳过那一项、并把行图画成灰帧；而我们这一列是
    // 自己驱动光标的（插了一格）⇒ 不照抄那条规则，光标就能停在灰项上、按确认就"进局即死"。
    // 口径与引擎**逐条一致**：`Manager + 0x2B688` 的两个字节**任一个非 0** ⇒ 可选。
    // 没有这两格就分不清"引擎说不可选、我们按不可选处理了"与"我们压根没读到"。
    std::uint32_t continueAvailable;        // [62] 1 = 可选 / 0 = 不可选 / **2 = 读不到**
                                            //      （读不到按"可选"处理：宁可保持旧行为，也不
                                            //       把用户锁在"继续游戏"外面）
    std::uint32_t continueSkipped;          // [63] 因为它不可选而**跳过**它的次数
                                            //      （0 ⇒ 这条规则一次都没生效过，或者那一局
                                            //       一直有可继续的局）
    // 批次 180（2026-09-28）加的四格：**这个进程一共还有多少内存**。
    //
    // 由来：用户报"D6 刷出四级道具 ⇒ 跳舞模组卡一下然后人物模型消失或卡死"，取证结论是
    // **我们模块自己的堆撞墙**（`dist/specialist-heap-exhaustion-20260928.md`：转码单笔要 4.62 MB
    // 连续空间，而真机读数里 `arena = 32.0 MB`、空闲只剩 2.2 MB）。本批把 `HeapSize`
    // 32 MiB → 128 MiB（`program/setting.hpp`），但**"128 MiB 装不装得下"没有任何上游文档可依**
    // ⇒ 与其猜，不如把这四个数读出来：
    //   * `[64]` 进程可用内存总量、`[65]` 已用（`svcGetInfo` 的 6 / 7）；
    //   * `[66]` 进程内存管理池总量、`[67]` 其中已用（同上的 16 / 17）。
    // 用途：给**以后**任何"要不要再抬 / 再省内存"的决策留一个现场数字
    // （本项目在"堆够不够"这件事上已经猜错过不止一次）。
    //
    // ★★ 2026-09-28 真机读数之后的**更正**（批次 181）：当初加这几格时以为它"能判 128 MiB
    //   之后的余量够不够"，**这条期望没兑现** —— 实测 `[64] = 3189.0 MB` / `[65] = 3188.0 MB`
    //   （该口径下"余量"只剩 1.0 MB），而**同一刻游戏完全正常**（贴图桥 `实际转码 13 / 失败 0`、
    //   模块堆 arena 47.4 MB）。
    //   ⇒ `UsedMemorySize` 更接近"整个应用内存池已被提交"的量，**两边几乎相等是常态**
    //     ⇒ **这两个数答不了"堆还能不能再抬"**（要判断只能抬了之后看能不能开机）。
    //   `[66]`/`[67]` 恒 0 也不是错误：那是"系统资源池"，普通 Application 不使用它。
    //   ⇒ 所以这几格**只作记录**、不作判据：给将来任何"内存到底去哪了"的疑问留现场数字。
    //
    // ★ 口径与哨兵：`svcGetInfo` 失败时存 **`0xFFFFFFFF`**（与服装查表那几格同一个约定）——
    //   "调用失败"与"真的只有 0 字节"必须能分开，否则读到一个 0 会让人以为"内存耗尽了"。
    // ★ 每 60 帧采一次（与 `[58]/[59]` 同一次调用里做，见 `.cpp` 的 `NoteHeapUsagePeriodically`）。
    std::uint32_t processTotalMemoryBytes;      // [64] 进程可用内存总量（0xFFFFFFFF = 调用失败）
    std::uint32_t processUsedMemoryBytes;       // [65] 进程已用内存（同上）
    std::uint32_t systemResourceTotalBytes;     // [66] 进程内存管理池总量（同上）
    std::uint32_t systemResourceUsedBytes;      // [67] 其中已用（同上）
    // ---- [68]..[73]：批次 378（2026-10-05）加的六格 —— "逐模组喂 content"补到引擎的 16 项 ----
    //
    // 由来：Switch 版引擎自己那条路（`ModManager::LoadConfigs @ 0x41E388`）在这版镜像里**从不执行**
    // ⇒ 模组的 `content/*.xml` 要我们自己喂。本批之前只喂 2 个（`costumes2.xml` / `music.xml`），
    // 本批补齐到引擎那 16 项（14 个文件 + `LoadCustomResources` + `PostLoadMods`）。
    // ⇒ 必须能从读数里回答三件事，否则下一轮出问题还是只能猜：
    //   ① **16 项入口有没有全部解析到**（任一解析失败 ⇒ 那一项的内容就是不进引擎的，且**不报错**）；
    //   ② 到底调了多少次（每模组 × 16，或"重试导致重复喂"都从这里一眼看出）；
    //   ③ 真条目构造了几个、`PostLoadMods` 收尾了没有（收尾**只允许一次**）。
    // ★ 为什么跟在**最后**而不是紧挨 `[60]/[61]` 那两个 `modEngine*` 格：字段顺序就是读数工具的
    //   下标契约（见上面的纪律 2）—— 插在中间会让 `[62]` 以后每一格整体错位，
    //   而错位在读数里表现为"某几格莫名非 0"，比报错难查得多。
    std::uint32_t modEngineLoadersResolved;   // [68] **位掩码**：bit i = 表里第 i 项入口解析成功
                                              //      （16 字节序言**与**该行自己的 4 字节判别式都过）。
                                              //      bit0..13 = 14 个 content 文件、bit14 = `LoadCustomResources`、
                                              //      bit15 = `PostLoadMods`（行号见 `runtime_constants.hpp`
                                              //      的 `kModContentFeedSpecs`）。
                                              //      ★ 全部 16 位应当恒为 0xFFFF（解析失败**不报错**，
                                              //      只表现为"那个文件的内容不进引擎"）。
    std::uint32_t modEngineLoaderFailures;    // [69] 上一位的**补码**（便于读数一眼看出缺哪几项）：
                                              //      bit0..15 = 解析失败的那几项；
                                              //      ★ bit16 = `ModEntry::ctor` 解析失败（它**不在**表里，
                                              //      单独占一位）—— 那位一亮，所有带 `ModEntry*` 的项
                                              //      （8 个）都会被跳过（引擎那个参数不能传空指针：
                                              //      空指针会让 `type="none"` 的条目一条都不加）；
                                              //      ★ bit17 = `std::string::assign` 那条 **PLT 桩**解析失败
                                              //      （同样不在表里）—— 那位一亮，真条目的 `+0x48`/`+0x60`
                                              //      填不上 ⇒ `LoadCustomResources` 找不到模组自己的资源
                                              //      （`GetContentPath` 读的就是 `+0x48`），其余 15 项不受影响。
    std::uint32_t modEngineContentCalls;      // [70] 14 项加载器**一共被调了几次**（累加；
                                              //      含 `costumes2.xml` / `music.xml` 那条专用路的每一次调用，
                                              //      它是"两种路径口径各试一次"⇒ 那两个文件最多算 2 次）
    std::uint32_t modEnginePostLoadModsCalls; // [71] `EntityConfig::PostLoadMods()` 调了几次。
                                              //      **正常 = 1**（引擎在循环外只调一次；本批用一次性闩锁保证，
                                              //      多调一次等于拿一份没收尾的配置去收尾）
    std::uint32_t modEngineCustomResourceCalls;  // [72] `ModEntry::LoadCustomResources()` 调了几次。
                                              //      **正常 = 启用的模组数**（引擎每个模组第一个调它）
    std::uint32_t modEngineRealEntryBuilds;   // [73] 用引擎构造器造的**真 `ModEntry`** 有几个。
                                              //      **正常 = 启用的模组数**（按下标惰性构造一次、之后复用）。
                                              //      ★ 为什么不复用那个 0x140 字节的替身：`LoadCustomResources`
                                              //      会写 `+0x140` 起的 13 个 `ANM2`（到 `+0x1008`），
                                              //      替身装不下 ⇒ 那是越界写（见 `runtime_constants.hpp`）
    std::uint32_t modEngineDefaultAnm2Loads;  // [74] ★ 批次 409（2026-10-08）：`ANM2::Load(
                                              //      "gfx/ui/mod_defaults.anm2", true)` 在
                                              //      `Manager+kManagerToModManagerOffset+0x368`
                                              //      上被我们调了几次。**正常 = 1**（引擎那条
                                              //      `ModManager::LoadConfigs` 尾部只跑一次；本仓由
                                              //      `LoadModManagerDefaultAnm2Once` 在那同一个一次性
                                              //      闩锁里做）。**0 = 那一步没做** ⇒ 暂停屏画
                                              //      模组道具（id ≥ 733）时会写 `0x80` 崩
                                              //      （真机 2026-10-08 13:45 实测）。
    // 批次 417（2026-10-08）加的一格 —— ★ **追加在末尾**：本结构体只许往后加字段，
    //   插在中间会让老读数件按偏移解析时把 [60]..[74] 全部错位（技能 §3 的硬规矩）。
    //   内容 = **Lua 状态自己占了多少字节**。由来：415 的真机读数说本模块堆
    //   "已用 122.8 MB / 空闲 5.2 MB"，而"这 122 MB 是谁吃的"当时只能猜。有了这一格就能把
    //   **Lua 侧**（模组的表/字符串 —— EID 的语言包光源码就有 8 MB）与**其它**（`malloc` 出来的：
    //   Font 块、贴图转码缓冲、挂载表、名字层…）分开：**其它 = [59] − 本格**。
    //   口径 = `LuaRuntime::LuaStateMemoryBytes()`（`lua_gc` 的 GCCOUNT + GCCOUNTB）；
    //   只在宿主构建或还没采到时为 0（与 [58]/[59] 同一个 60 帧节拍）。
    std::uint32_t luaStateBytes;              // [75] Lua 状态自己的内存（字节）
    // 批次 418（2026-10-09）加的五格 —— ★ **追加在末尾**（同一个规矩：只许往后加）。
    //
    // 由来：批次 417 只把"已用 120.8 MB"拆成"Lua 侧 36.8 MB + 其它 ≈84 MB"，而"那 84 MB 是谁"
    // 归因不到任何一条代码缓冲 —— 对 417 的生产 ELF 做**全镜像反汇编穷举**（抓所有
    // `bl/b` 到 `malloc/realloc/calloc/operator new/new[]` 的调用点并归函数）之后，
    // 模块自己的堆分配点只有 6 个函数（`ImagePcxCacheInsert` / `ReadPngFileForBridge` /
    // `PngToPcx` / `IsaacRenderText` / `IsaacRenderScaledText` / `CreateSpriteHandle`），
    // 它们的**常驻上限加起来不到 25 MiB** ⇒ "84 MB 是我们自己的缓冲"这个前提**很可能是伪的**。
    //
    // ⇒ 下面四格 `mallinfo` 账目就是用来**把两种可能分开**的（判读表见读数工具那一段）：
    //      [76] = `mallinfo().uordblks`（分配器自认**已分配**的字节数）
    //             ⇒ 与 [59]（`arena − fordblks`）一比：**几乎相等** = [59] 没高估，
    //                84 MB 是真实的分配；**远小于** [59] = 口径高估，是量具问题。
    //      [77] = `mallinfo().ordblks`（**空闲块个数**）—— 碎片程度的直接读数
    //             （有一个独立的、非 mallinfo 来源的观测是"8115 个碎块"，这两处可以互相印证）。
    //      [78] = `mallinfo().hblks`（mmap 区个数；newlib 的 dlmalloc 走 `sbrk`，**正常恒 0**）。
    //      [79] = `mallinfo().keepcost`（**堆顶那块空闲**的字节数 = 能归还给系统的那部分）
    //             ⇒ 它很小而 [58] 不小 = 释放的块**无法与堆顶合并** ⇒ 只增不减 + 碎片。
    //   ★ 与 [58]/[59] **同一个 `mallinfo()` 调用**取出来（不多扫一遍空闲链表），
    //     同一个 60 帧节拍 ⇒ 五格天然是同一时刻的读数，可以互相减。
    //   ★ 失败/不可用一律写 0（宿主构建没有这个口径；门禁不据此断言真值）。
    std::uint32_t heapAllocatedBytes;         // [76] `mallinfo().uordblks`：分配器自认已分配的字节
    std::uint32_t heapFreeChunkCount;         // [77] `mallinfo().ordblks`：**空闲块个数**（碎片读数）
    std::uint32_t heapMmappedRegions;         // [78] `mallinfo().hblks`：mmap 区个数（newlib 下恒 0）
    std::uint32_t heapTopFreeBytes;           // [79] `mallinfo().keepcost`：堆顶那块空闲的字节数
    // 批次 418：贴图桥转码结果缓存的**实际占用**（不是它的**预算** —— 预算按"任一时点
    // 都可能被容器淘汰回额度内"来理解；具体数值看 `image_pcx_bridge_hook.cpp` 的
    // `kImagePcxCacheBudgetBytes`，**不在这里重复写死**，免得两处数值各说各话）。
    // 口径 = `bridge::ImagePcxCacheUsedBytes()`（走函数，**不**按对象偏移硬读 —— 偏移会随
    // `BudgetedLruCache` 的布局漂，硬编码会静默读错）。同一个 60 帧节拍。
    std::uint32_t imagePcxCacheUsedBytes;     // [80] 贴图桥缓存当前驻留了多少字节
    // 批次 420（2026-10-10）加的五格 —— ★ **追加在末尾**（同一个规矩：只许往后加）。
    //
    // 由来：批次 416 把 `HeapSize` 抬到 256 MiB 时真机装不上（加载期 `nn::diag::Abort`，
    // 崩溃报告 `01791470579…` 已归档在 `dist/change-archive-20261008/416-heap-256mib/`），
    // 它的栈显示是**游戏自己**在 `nv::InitializeGraphics`（向系统要那块图形内存）里
    // 要不到 ⇒ 自己 abort。⇒ 我们缺一个"**这个进程到底还剩多少内存**"的现场数字：
    //   * `[64]`/`[65]`（`TotalMemorySize`/`UsedMemorySize`）实测**几乎相等** ⇒ 答不了"还剩多少"；
    //   * 本批补的是内核另外两组口径：
    //     - `InfoType_TotalNonSystemMemorySize`(21) / `UsedNonSystemMemorySize`(22)
    //       = **不含"进程内存管理池"**的进程可用 / 已用（6.0.0+）；
    //     - `svcGetSystemInfo(Total/UsedPhysicalMemorySize, PhysicalMemoryInfo_Application, …)`
    //       = **分配给"应用"那一档的物理内存**总量 / 已用 —— 这才是"整机分给游戏的分额"。
    //   ⇒ ★★ **`svcGetSystemInfo` 这条路被真机否掉了**：本批第一次上卡（880319）当场
    //      崩 —— 崩溃报告 `01791635311_010021c000b6a000.log` 报
    //      `Type = Undefined System Call`、`Svc Id = 0x6f`、`PC = runtime + 0x9901c`
    //      ⇒ **在用户态的 Application 里 `svcGetSystemInfo` 根本不存在**，一调就死。
    //      ⇒ 本批**只保留 `svcGetInfo` 的两格**（它同样答得了"还剩多少"）：
    //   ⇒ 本批要回答的问题：**进程可用（不含系统池）余量 = `[81]` − `[82]`**，
    //     并与 `[64]`/`[65]`（**含**系统池、实测恒几乎相等）对照。
    //   ★ 与 `[58]`/`[59]` 同一个 60 帧节拍；失败一律存 `0xFFFFFFFF` 哨兵
    //     （"调用失败"与"真的是 0 字节"必须能分开 —— 与服装查表那几格同一个约定）。
    //   ★ **只读、只记录**：没有任何行为跟着这两格变。
    std::uint32_t processTotalNonSystemBytes; // [81] 进程可用（不含系统池），`svcGetInfo` 21
    std::uint32_t processUsedNonSystemBytes;  // [82] 进程已用（不含系统池），`svcGetInfo` 22
    // 批次 420（续，2026-10-10）：★ **真正能回答"还剩多少"的那条路 —— resource limit**。
    // 口径来自 Atmosphère 内核源码（取证见 `docs/分析-用户态查可用内存-20261010.md`）：
    //   * `svcGetInfo(InfoType_ResourceLimit = 9, handle = **INVALID_HANDLE**, 0)` ⇒ 拿本进程的
    //     resource limit 句柄（★ `handle` 必须传 **0**，内核写着 `R_UNLESS(handle == InvalidHandle, …)`）；
    //   * `svcGetResourceLimitLimitValue`(svc 0x30) / `CurrentValue`(0x31)，
    //     `which = LimitableResource_Memory = 0` ⇒ 得到"内存配额上限"与"当前已用"；
    //   * **还剩多少 = `[83]` − `[84]`** —— 内核自己的 `KResourceLimit::GetFreeValue` 就是这么算的
    //     （`kern_k_process.cpp` 的 `GetTotalUserPhysicalMemorySize` 用的正是它；
    //      `InfoType_FreeThreadCount` 的实现也写成 `limit - current`）。
    // ★ 三个调用**都没有权限检查**（`kern_svc_resource_limit.cpp:28-54`、`kern_svc_info.cpp:201-225`）
    //   —— 与 `svcGetSystemInfo`（用户态是未定义 svc 0x6f）完全不同。
    // ★ 失败/超 4 GiB/句柄为空一律存 `0xFFFFFFFF` 哨兵（"调用失败"与"真的是 0"必须能分开）。
    // ★ 只读、只记录；没有任何行为跟着这两格变。
    std::uint32_t resourceLimitMemoryBytes;   // [83] 内存配额上限（`lim - cur` 的 `lim`）
    std::uint32_t resourceMemoryUsedBytes;    // [84] 内存配额当前已用（`lim - cur` 的 `cur`）
    // 批次 421（2026-10-10）：★ **用户点名要"内存占用 / 可用余量"** —— 遍历 libnx 的 API 后
    // 定为 **`svcQueryMemory`(0x06) 逐段扫地址空间、按 `MemType` 分类求和**（取证见
    // `docs/分析-用户态查可用内存-20261010.md`）。**这才是"看得见的内存占用"**：`InfoType`
    // 6/7/21/22 都退化成"池的总量"、`svcGetSystemInfo` 在用户态是未定义 svc、`svcGetInfo`
    // 的区域大小那几格（3/5/13）在 Application 上直接调用失败。
    //   ★ 单位 = **KiB**（不是字节）：第一版用字节 ⇒ "所有已映射"**直接溢出 u32 格**
    //     （说明 > 4 GiB）⇒ 换 KiB 后 u32 能装到 4 TiB，够用。
    //   ★ **一次扫，只做一次**（一次扫要几千次 svc 调用，绝不能每帧做）。
    //   ★ 口径：`[89]` = **"私有/真实占用"合计**（`Normal`+`Heap`+代码+`Mapped`+其它
    //     非 `Io`/非 `SharedMem`/非 `Unmapped`）—— **游戏本体 + 我们的兼容层 + 模组
    //     都在这份里**（兼容层与模组的 `malloc` 用的就是游戏的堆/映射）；
    //     `[90]` = 所有"非 Unmapped"合计（含 IO 与共享 ⇒ 它明显大于 `[89]`）。
    //   ★ 失败 / 超 4 TiB 一律 `0xFFFFFFFF` 哨兵。
    std::uint32_t memNormalKiB;               // [85] `MemType_Normal`（KiB）
    std::uint32_t memHeapKiB;                 // [86] `MemType_Heap`（KiB）
    std::uint32_t memCodeKiB;                 // [87] `CodeStatic` + `CodeMutable`（KiB）
    std::uint32_t memMappedKiB;               // [88] `MappedMemory`+`ThreadLocal`+`TransferMem`+`ProcessMem`（KiB）
    std::uint32_t memPrivateKiB;              // [89] ★ **私有/真实占用合计**（KiB）——含游戏+兼容层+模组
    // ★★ 2026-10-10（批次 424）：**原来这里还有 [90] `memMappedTotalKiB`（所有"非 Unmapped"合计），
    //   已删除** —— 实测它**恒为哨兵 `0xFFFFFFFF`**（"IO / 保留区"的**虚拟地址范围**是 TiB 量级，
    //   KiB 单位下必然溢出 u32）⇒ **那一格没有意义，留着只会让读数里多一个误导性的数**。
    //   ★ 它是**最后一格**，所以删除**不影响前面任何字段的编号**（本项目"只往后加"的规矩不受影响）。
};

//: 状态面本体。**定义在 `.cpp` 里、外部链接**（理由见 `State` 的注释）。
extern "C" State g_ModMenuState;

//: 安装时调一次（模块初始化线程、游戏主循环尚未开始）：
//: 逐字节核对我们要**直接调用**的那些引擎入口（`Menu_Mods` 的五个方法、`ANM2` 两个跳板、
//: `Font` 三个入口、`Manager::GetLanguageCode`、读文件那组绑定…），并把三个入口中继的安装结果
//: 记进状态面 [1]。核对不过只是"不调用"，一个字节都不写。
//: 为什么放在这里而不是每帧懒做：此处仍在模块初始化线程上、游戏主循环尚未开始（与
//: `PublishManagerEngineBindings` 同一条理由），失败会当场记进状态面，而不是在循环里悄悄降级。
void ModMenuNativeInstall(const TargetModule& module) noexcept;

//: 每帧调一次（在引擎自己的 `Manager::Update` **之前**）：推进"我们那一格的导航"、
//: 驱动模组页（状态 16）。位置 = 引擎分派之前，所以我们这一帧写进去的状态/索引引擎这一帧就按它走。
void ModMenuNativeUpdate() noexcept;

//: ★★ 批次 153（2026-09-27）：**在模组脚本执行之前**把模组的 `content/`（皮肤 + 音乐）喂给引擎。
//:
//: 为什么必须在那个时机（真机证据，不是推断）：PC 的模组惯例是在**文件作用域**就用
//: `Isaac.GetCostumeIdByPath` 把服装编号建成表（官方教程的写法），而编号一旦建成就**不会再查**。
//: 我们原来只在"进模组页那一刻"喂 —— 那时模组的表早就填成 `-1` 了
//: （真机读数：容器 132 → 155 说明喂成功了，但同一次读数里 `GetCostumeIdByPath` 43 次调用
//: **0 次命中**、查的时候容器只有 132 ⇒ 喂晚了）。
//:
//: 调用点 = `hook_manager.cpp` 的 `LoadDefaultManifestModThroughService()` 里、
//: **注册完各模组的资源挂载点之后、`service.LoadAll(...)`（跑模组脚本）之前**。
//: ★ 156 才挪到这里：155 及以前放在 `InitializeDefaultManifestMod(...)` 之前 —— 那**太早了**，
//: 那时我们的模组列表还没发布、模组的内容目录也还没注册 ⇒ 那一次**什么都没做**
//: （真机 `[61] = 4`、加载器一次都没被调用），而它照样被记成"跑完了"。
//: 只要这条链上还有"进模组页"与"每帧重试"两条兜底，放错位置不会崩，但**舞会一直出不来**。
void LoadEngineModContentBeforeModScripts() noexcept;
// PC式重载：预检不破坏旧环境；静态条目由运行时析构，菜单表不交给引擎delete。
void NoteModToggleSaveResult(bool saved) noexcept;
[[nodiscard]] bool PreflightEngineModReload() noexcept;
[[nodiscard]] bool WaitEngineGraphicsForModReload() noexcept;
[[nodiscard]] bool ReleaseEngineModsForReload() noexcept;
[[nodiscard]] bool BeginEngineModContentCycle(bool reload) noexcept;
[[nodiscard]] bool LoadEngineModContentForMod(const char* root) noexcept;
[[nodiscard]] bool FinishEngineModContentCycle() noexcept;
[[nodiscard]] bool FinishEngineModReload() noexcept;


//: 判定「按 PC 规则，本局是不是不该给成就」—— 给入口中继 `PersistentGameDataSetReadOnly` 用。
//: 规则 = 带符号的 `AfterbirthPlus.nro` 里 `ModManager::AchievementsLocked()` **一比一**：
//:   **「有真实模组实际加载」且「成就 #4（打过妈妈）未解锁」⇒ 该禁**；其余一律不锁。
//: ★ 2026-09-24 批次 098 撤掉了原来的 **fail-closed**（"模组发现还没出结果就按有模组算"）——
//:   那是我们自创的，会在开机那几秒把**该给的**成就也吞掉，正是用户报的"关着模组也不给成就"的形状。
//:   现在只认**实际加载结果**（`ModMenuActiveCount()`，启动时就有，不存在"还没扫完"）。
//: ★ 不看是哪一个成就（批次 096 撤掉 093 给 #4 开的豁免）：妈腿成就本身也不豁免 ——
//:   关掉模组之后本函数一律返回 false，所以不会锁死。
//: 参数 = `PersistentGameData*`（用来读成就 #4 的持久位）。
[[nodiscard]] bool AchievementsShouldBeBlockedFor(void* persistentGameData) noexcept;

// ---- 局内单向闩锁（2026-09-25 批次 117 建、118 加"只在一局里观察"、119 加"跨继续留存"）----
//
// 它解决的问题：PC 的判据是"开局那一刻问一次"，所以"进局之后才把模组打开"这件事
// PC 根本不看（那一局照样给成就）。用户要的是**局内单向**：一局之内只要出现过
// "没打过妈腿 且 开着模组"，这一局就一直禁，**之后把模组关掉也不解除**。
//
// ★★ 批次 119（用户 2026-09-25 裁定）：**"继续同一份存档"算同一局**。
//    用户能做的"中途改开关"只有一条路：退出到主菜单改（我们的模组页只在主菜单能打开，
//    一局里 `g_MenuManager` 不存在、那一页驱动不起来）⇒ 若"退出即清零"，
//    "中途开启后又关掉仍锁"这条**永远观察不到**。所以：
//      * 出局（`GameExit`）⇒ 把闩锁**留成"留存"**（不清成"这一份存档是干净的"）；
//      * 继续（`LoadSave`）⇒ 把留存**接回来**，并在下一帧**补写一次锁**
//        （引擎那次开局写位发生在我们接回来之前，在 `Game::StartFromSavedState` 体内）；
//      * 开新局（`NewRun`）⇒ **真正清掉**（裁定①：进局前关掉模组 ⇒ 这一局不锁）。
//    ★ 为什么不让闩锁直接亮到"开新局"再清：开新局那次写也发生在我们之前 ⇒
//      不清留存的话，"关掉模组后开新局"会被**误锁**（正是用户在 116 那批报过的形状）。

//: 一条**局边界**的种类。写进状态面 [48]：三种边界的处置**不同**，
//: 现场分不清是哪种时无法判断"清零点有没有生效"。
enum class RunBoundaryKind {
    None = 0,      //: 还没遇到过局边界
    NewRun = 1,    //: 开新局（`Game::Start`）⇒ **真清零**（含留存）
    LoadSave = 2,  //: 继续同一份存档（`Game::StartFromSavedState`）⇒ 把留存**接回来**
    GameExit = 3,  //: 离开一局（退出流程一开始就触发）⇒ 把闩锁**留成留存**
};

//: ★★ 闩锁的**纯算术**（宿主门禁直接测它，见 `runtime/tests/test_achievement_run_latch.py`）：
//: 条件成立过就一直是 `true`，只有 `NoteNewRun` 会把状态放回 `false` —— **单向**。
//: 为什么抽成独立函数：语义里最容易写错的一条就是"关掉之后又变回去"，
//: 而这条错误在真机上看起来和"判据没生效"一模一样，只有纯逻辑门禁能一秒分清楚。
[[nodiscard]] inline bool RunLatchNextState(bool conditionHolds, bool latched) noexcept {
    return latched || conditionHolds;
}

//: 每帧（以及中继里）观察一次：条件成立 ⇒ 单向置位。返回"这一下是不是发生了 0→1"
//: —— 那一下的调用方要**主动把只读位写下去**（见 `.cpp` 里 `UpdateAchievementDisallow`）。
//:
//: ★★ **只在一局里观察**（批次 118）：不在一局里时"开着模组"什么都不代表 ——
//: 那只是主菜单上的开关状态。没有这道闸门时，开机后在菜单上就会被置位，
//: 于是"进局前把模组关掉"的那一局会被误锁（用户开工单里的裁定①明确要求"不锁"）；
//: 117 的第一次真机读数正是这个形状（`[45]=1` 而 `[35]` 从没被调到过 ⇒ 还没进过任何一局）。
//:
//: ★★ **继续同一份存档时也要返回一次 `true`**（批次 119）：那一下代表"把出局时的留存接回来"，
//: 调用方据此**补写一次锁** —— 引擎那次写发生在我们接回来之前，不补写就等于没生效。
[[nodiscard]] bool ObserveRunLatch(bool conditionHolds) noexcept;

//: 一条**局边界**到了。做什么**由 `kind` 决定**（见上面那段）：
//: `GameExit` ⇒ 闩锁转成留存；`LoadSave` ⇒ 留存变成"待接回"；`NewRun` ⇒ 真清零。
//: ★ 这个映射只留在这里一处；放到调用点会变成"三处各自记得"，
//: 而漂移的表现是"有时不锁、有时误锁"，最难查（见状态面 [51] 那段）。
//: 由 `GameExit` 中继与 `GameStart` 中继调。
void NoteNewRun(RunBoundaryKind kind) noexcept;

//: 闩锁当前的置位状态（**判据短接在它上面**）。
[[nodiscard]] bool RunLatchLatched() noexcept;

//: 闩锁是不是**可用**。由安装时判定：`GameExit` 挂点缺席 ⇒ 不用闩锁（退回实时判据）。
//: 理由见状态面 [50] 那一格：出局那一路缺席时，闸门会一直是"在局里"、留存也永远更新不了。
void NoteRunLatchArmed(bool armed) noexcept;
[[nodiscard]] bool RunLatchArmed() noexcept;

} // namespace isaac::runtime::modmenu

// 2026-10-23：游戏线程扫描时统一排序并发布；菜单随后只用缓存。
namespace isaac::runtime { struct ResolvedManifestModBatch; }
namespace isaac::runtime::modmenu {
[[nodiscard]] bool SortAndPublishDiscoveredMods(const TargetModule& module,
                                               ResolvedManifestModBatch& batch) noexcept;
}
