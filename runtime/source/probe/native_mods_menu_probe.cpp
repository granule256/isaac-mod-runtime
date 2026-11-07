// 探针：能不能把游戏自己那套模组菜单叫出来。设计与用法见同名 .hpp。
//
// 本 TU 只在 `PROBE_BREAK=1` 且 `PROBE_BREAK_NATIVE_MODS_MENU=1` 时编译（生产包不含它）。

#include "native_mods_menu_probe.hpp"

#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_NATIVE_MODS_MENU

#include "application/callback/callback_dispatcher.hpp"  // 回调派发计数（关卡/房间事件）
#include "lua_runtime_state.hpp"  // `InputIsActionPressedThunk()`
#include "game_file_reader.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"  // `Original<>`（挂点记下的原函数入口）
#include "interfaces/lua/mod_menu_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
// 本批（072）用的是引擎的**按文件名**版 `LoadImage(char const* path, ...)`：它收的是
// `const char*`，所以**不需要** libc++ 字符串桥（上一批为 `ANM2::Load` 做过的那一处已在
// 本批回退）。
// `std::string`**（24 字节 SSO），而本模块编的是 libstdc++ ⇒ 路径串必须走这个桥。
// 那是全项目对 libc++ 字符串布局的**唯一**一处实测结论，探针直接用它、不另抄一套。
#include "mod_page_entries.hpp"
#include "mod_menu_entry_row.hpp"  // 这一列"多插一格"的算术（有宿主门禁）
#include "mod_page_nav.hpp"        // 模组页（状态 16）自己维护的那点算术（有宿主门禁）
#include "mod_page_runtime_sources.hpp"
#include "module_finder.hpp"
#include "relay/entry_relay.hpp"  // 入口中继（零占洞改目标函数入口 16 字节）
#include "relay/smart_pointer_shim.hpp"  // 五参内存版 `LoadImage` 的 16 字节返回值垫片
#include "runtime_constants.hpp"  // `kContentManager*` / `kGameOperatorDeleteArray*`

#include <array>
#include <cstdint>
#include <cstring>
#include <optional>

namespace isaac::runtime::probe {

// 诊断面（非匿名命名空间：读数工具按 mangled 名直接读它，与 `ImagePcxDiagnostics` 同一做法）。
// 布局固定，字段顺序不要改（要加就往后加），读数工具按偏移解析。
struct NativeModsMenuProbeState {
    std::uint32_t armed;
    std::uint32_t presses;
    std::uint32_t backPresses;
    std::uint32_t state;
    std::uint32_t manualMode;
    std::uint32_t initResult;
    std::uint32_t renderCalls;
    std::uint32_t lastFailure;
    std::uint32_t managerOk;
    std::uint32_t menuManagerOk;
    std::uint32_t modListBytes;
    std::uint32_t menuState;
    std::uint32_t heldActionMask;
    std::uint32_t heldControllerMask;
    std::uint32_t scanRounds;
    std::uint32_t modListPointersOk;
    std::uint32_t manualModsPtrOk;
    // 2026-09-22：坐标候选。页面位置该传什么，最省的办法是看"已经摆对了的页面"的坐标：
    // 每个页面对象头部就是它的 `Vector2`（`Menu_Title` 在 `+0`、`Menu_Mods` 在 `+8`）。
    // 这里把三个已知页面的头部两组 float **按原始 32 位**记下来（读数端再解成浮点），
    // 由"哪个值落在屏幕范围内"来定案，而不是继续猜或继续追反汇编。
    std::uint32_t titlePosX;
    std::uint32_t titlePosY;
    std::uint32_t optionsPosX;
    std::uint32_t optionsPosY;
    std::uint32_t keyConfigPosX;
    std::uint32_t keyConfigPosY;
    // 位置标定：当前用的是第几档（读数里报出来，用户只要说"第几档看着对"）
    // 已停用：标定失败了（六档都不对），根因是渲染上下文而不是位置。
    // 位置保留不动（往后加是纪律，删字段会让老读数整段错位），040 起恒为 0。
    std::uint32_t positionStep;
    // ---- 新增：在引擎自己的渲染上下文里画 ----
    std::uint32_t titleRelayState;    // [24] `Menu_Title::Render` 入口中继：0 未装 / 1 成功 / 2 失败
    std::uint32_t titleRelayFailure;  // [25] 原始失败码（0 无失败 / 1 地址非法 / 2 入口字节不符 /
                                      //      3 竞技场满 / 4 写回校验失败 / 5 入口含 PC 相对指令）
    std::uint32_t menuOffsetX;        // [26] `MenuManager+0x3c` 的 Vector2 X（页面空间→屏幕的偏移 X）
    std::uint32_t menuOffsetY;        // [27] 同上 Y
    // ---- 新增：把"页面空间被裁掉多少"算清楚 ----
    std::uint32_t screenWidth;        // [28] `IsaacRepentance::WIDTH`（float 位）
    std::uint32_t screenHeight;       // [29] `IsaacRepentance::HEIGHT`（float 位）
    // ---- 新增：本页实际被画在哪个页面坐标 ----
    std::uint32_t pageOriginX;        // [30] `偏移 + 本页位置 + 200`（= 传给 `ANM2::Render` 的那个点）
    std::uint32_t pageOriginY;        // [31] 目标值应是 (240, 72)：纸铺满页面框 [0,480]、上沿在顶端
    // ---- 新增：换成真实模组名（第 B 步）。语义见 `.hpp` 的同名注释。----
    std::uint32_t realSourceState;    // [32] 0 未试 / 1 用真实模组 / 2 退回固定测试名
    std::uint32_t realDirectoryCount; // [33] 发现到几个模组目录
    std::uint32_t realEnabledCount;   // [34] 其中几个是"开着"的
    std::uint32_t realEntryCount;     // [35] 真实条目实际造出几条
    std::uint32_t metadataReadOk;     // [36] `metadata.xml` 读成功次数（= 名字取自 `<name>` 的行数）
    std::uint32_t metadataReadFailed; // [37] 解析到挂载但读失败（异常）
    std::uint32_t metadataAbsent;     // [38] 没有挂载实体（正常 ⇒ 那一行退目录名）
    std::uint32_t metadataBindings;   // [39] 读文件那组绑定：0 没读 / 1 通过 / 2 没过
    std::uint32_t metadataResolveFn;  // [40] **挂载解析入口**（`GetMountedFilePath`）：0 没试
                                      //      / 1 用中继记下的原函数（正常）
                                      //      / 2 用守卫过的引擎入口（中继没装时才走）
                                      //      / 3 两条都没拿到 ⇒ 全部退目录名
    std::uint32_t metadataExistsForm; // [41] 路径形式位：位 0 带前缀就被认 / 位 1 去前缀才被认
    // ---- 新增：在"选择界面"那一列里插入"模组"那一行 ----
    std::uint32_t modRowRelayState;     // [42] `Menu_Game::Render` 入口中继：0 未装 / 1 装成功 / 2 失败
    std::uint32_t modRowRelayFailure;   // [43] 安装的原始失败码
    std::uint32_t modRowSlot;           // [44] 当前选中第几格（0..5；**3 = 我们那一格**）
    std::uint32_t modRowEngineIndex;    // [45] 写回给引擎的索引（**夹在 0..4**，绝不越界）
    std::uint32_t modRowCursorFrame;    // [46] 我们让光标用的帧号（= 格子号）
    std::uint32_t modRowUpPresses;      // [47] 我们自己的导航：往上按过几次
    std::uint32_t modRowDownPresses;    // [48] 往下按过几次
    std::uint32_t modRowConfirmPresses; // [49] 确认按过几次
    std::uint32_t modRowConfirmOnOurs;  // [50] 其中**落在我们那一格上**的次数（本批只记录，不接页面）
    std::uint32_t modRowRenderCalls;    // [51] 我们在那一屏画了几帧（0 = 门控没过 / 中继没装）
    std::uint32_t modRowOnOurs;         // [52] 1 = 当前光标就在我们那一格上
    std::uint32_t modRowLayersFn;       // [53] `ANM2::GetLayer` 跳板：0 没试 / 1 拿到 / 2 没拿到
    std::uint32_t modRowFontState;      // [54] 画字入口：0 没试 / 1 拿到 / 2 没拿到
    std::uint32_t modRowManagerOk;      // [55] 1 = 拿到了 `g_Manager`（字体对象在它里面）
    std::uint32_t modRowTextY;          // [56] 我们那行字画在哪个 y（原样 32 位 float）
    std::uint32_t modRowTop;            // [57] 那一格的屏幕上沿（原样 32 位 float）
    // ---- 新增：那一行到底"画了几次"（判定①"字看不见"用）----
    std::uint32_t modRowLabelDraws;     // [58] 那一行的**字**（退回用字体画时）画了几次
    std::uint32_t modRowCjkDraws;       // [59] 1 = 页面原点拿到了（0 ⇒ 字会画到屏幕角上）
    // ---- （2026-09-22 晚）新增：那一行改成贴图 ----
    // 用户要求"别的行是贴图，我们这一行也照它们的来" ⇒ 运行时自己把那张手绘贴图画上去。
    // 这五格就是"这条链通到哪一步"的全部判据。
    std::uint32_t modRowLanguageCode;   // [60] 游戏的语言码（两个字符原样：'z''h' ⇒ 0x0000687A）
    std::uint32_t modRowLanguageState;  // [61] 0 没试 / 1 拿到 / 2 入口守卫不过 / 3 单例空 /
                                        //      4 挑到的是 `en` 兜底（不是本语言）
    std::uint32_t modRowImageState;     // [62] 0 没试 / 1 贴图好了 / 2 入口守卫不过 /
                                        //      3 单例或描述符空 / 4 引擎返回了空指针 /
                                        //      5 语言还没定（等下一帧）
    std::uint32_t modRowSpriteDraws;    // [63] 那张贴图画了几帧（0 ⇒ 不是在退回画字，就是没画）
    std::uint32_t modRowSpriteOrigin;   // [64] 1 = 页面原点拿到了（0 ⇒ 坐标会算成页内绝对位置）
    std::uint32_t modRowImageAttempts;  // [65] 四种"路径形态"各自有没有拿到贴图（位 0..3）
    std::uint32_t modRowImageAttempt;   // [66] 实际用的是第几种（1..4；0 = 都没成）
    // ---- 第九版（2026-09-22 深夜，）：把"模组"那一格的确认键接上 ----
    //
    // 目标：照 PC 的做法进入引擎的**状态 16**（= 模组页），并让引擎自己的滑动/翻页音完成过渡。
    // 这一批的判据分三段：
    //   ① 进得去：`[68]` 状态 16 的帧数、`[69]` 拦截/进入次数、`[70]` Reset 那一跳过没过守卫；
    //   ② 页面活着：`[71]` 我们驱动了几帧、`[72]`/`[73]`/`[74]` = 页面对象里的
    //      选中项 / 按住计时 / "改过没有"（`Menu_Mods` 的 `+0x0`/`+0x4`/`+0x124`）；
    //   ③ 出得来：`[75]` 返回键次数（页面自己会调 `SetState(3)`）。
    // 另有三格是"环境"：模组总开关、状态 16 那一格的目标 Y、进入那一刻的视图偏移（用来判断
    // 引擎到底有没有滑）。
    std::uint32_t modsPageStateCode;    // [67] 我们用的状态号（应当恒 16；门禁钉住它的来历）
    std::uint32_t modsPageActive;       // [68] 1 = 当前由我们驱动模组页（= 引擎状态 16）
    std::uint32_t modsPageEnterCalls;   // [69] 进页面的次数（在那一格按确认）
    std::uint32_t modsPageResetState;   // [70] `Menu_Mods::Reset` 那一次：0 未试 / 1 调到 /
                                        //      2 入口守卫不符（版本不对）
    std::uint32_t modsPageDrivenFrames; // [71] 状态 16 期间我们驱动了几帧（Update 那一下）
    std::uint32_t modsPageSelected;     // [72] 页面对象 `+0x0`（当前选中第几个模组，0 起）
    std::uint32_t modsPageHoldTimer;    // [73] `+0x4`（按住计时；松手应归零）
    std::uint32_t modsPageEdited;       // [74] `+0x124`：1 = 这次进来改过开关（退出时要写清单）
    std::uint32_t modsPageTogglePresses;// [75] 我们自己接的确认（切换开关）次数
    std::uint32_t modsPageBackPresses;  // [76] 我们自己接的返回次数（返回走引擎的 `SetState(3)`）
    std::uint32_t modsPageRenderCalls;  // [77] 状态 16 期间画了几帧（0 ⇒ 只有状态门控那一环断了）
    std::uint32_t modsPageEntryCount;   // [78] 页面看到的模组条数（`end-begin`/8）
    std::uint32_t modsEnabledGate;      // [79] `g_Manager+0x36519`（模组总开关，原样一个字节）
    std::uint32_t modsPageScrollTargetY;// [80] `MenuManager+0x1AFF8C`：引擎给状态 16 的滚动目标
                                        //      （float 位；它是"状态 16 存在"的另一条证据）
    std::uint32_t modsPageOffsetYAtEnter;// [81] 进入那一刻的视图偏移 Y（float 位）——
                                        //      与 `[27]` 现场值比，就知道引擎有没有在滑
    // ---- 第十版（2026-09-22 深夜，）：把引擎的"模组总开关"置上 ----
    //
    // 真机读数（058 的第一次现场）发现 `g_Manager+0x36519` 是 **0**，而 `Menu_Mods::Render`
    // 在它为 0 时**只用一个颜色画所有行**（不读条目自己的 `+0x138`）⇒
    // "按确认切换开关"在屏幕上根本看不出来。进页面时把它置 1（与 PC 语义一致）。
    std::uint32_t modsGateWritten;      // [82] 1 = 我们把它置过（0 = 没读到 `g_Manager` 或还没进页面）
    std::uint32_t modsGateBefore;       // [83] 置之前它是什么（留证：它本来是 0 还是 1）
    // ---- 第十一版（2026-09-22 深夜，）："按了确认却没进模组页"要能一眼定位 ----
    //
    // 用户实测反馈：在「模组」那一格按确认，**跳到了统计页面**（引擎按它自己的索引 3 处理了）。
    // 说明"我们那一格的接管"中途退出了，而现场没有任何东西说明退在哪一步 —— 这几格就是为此加的。
    std::uint32_t modRowLastConfirmSlot; // [84] 最后一次确认按下时**我们**在第几格（0..5）
    std::uint32_t modEntryOutcome;       // [85] 接管那一下退在哪：
                                         //      0 没被调用（那次确认不在我们那一格）
                                         //      1 页面没准备好（`Init` 不是 ok，当场补做也没成）
                                         //      2 引擎状态不是 3（根本不在选择界面）
                                         //      3 走到 `SetState(16)` 且事后读到状态就是 16
                                         //      4 走到了 `SetState(16)` **但状态没变**（看 `[7]`）
    std::uint32_t modEntrySwallowed;     // [86] `MenuManager::SetState` 中继"替我们那一格挡掉"的次数
                                         //      （引擎想开统计/选项时被拦下 ⇒ 不会再跳错页面）
    std::uint32_t setStateRelayState;    // [87] `MenuManager::SetState` 入口中继：0 未装 / 1 装成 / 2 失败
    // ---- 第十二版（2026-09-23，）："我们调 SetState 到底调到了没"要有数 ----
    //
    // 的 bug 就是：装了 `SetState` 中继之后，`ApplyState` 里那句逐字节守卫必然失败
    // （入口 16 字节已被中继改写）⇒ `SetState` 根本没被调用，而失败码又被渲染回调每帧清掉 ⇒
    // 读数里"最近失败"是空的，现象只是"按了没反应"。这两格把"调到没调到"变成直接可读的数字。
    std::uint32_t applyStateCalls;        // [88] `ApplyState` 真正把 `SetState` 调出去的次数
    std::uint32_t applyStateGuardFailures; // [89] 因入口逐字节守卫不过而**没调**的次数
                                          //      （装了中继之后应当是 0；非 0 ⇒ 又走回了那条老路）
    // ---- 第十三版（2026-09-23，）：过渡动画 —— 纸"跟着画布走" ----
    std::uint32_t modsPageFixedY;        // [90] 进入页面后定下来的"本页位置 Y"（float 位）
    // ---- 第十四版（2026-09-23，）：位置"两个方向都跟着画布走"的自证 ----
    // 用户第二次反馈很具体：「速度很快就跳到了模组界面，其他的似乎没反应过来的感觉」
    // ⇒ 上一版只让 Y 跟着走、X 钉在屏幕中间 ⇒ 纸一开场就横向铺满屏幕。现在两个方向都跟着走。
    // 这三格用来证明"算出来的目标是对的"（不对的话纸会画到屏幕外或偏掉）：
    std::uint32_t modsPageTargetOffsetX; // [91] 我们算出的"状态 16 目标偏移"的 X（float 位）
    std::uint32_t modsPageSettledOffsetX;// [92] 画布停稳时**现场**偏移的 X（float 位）——
                                         //      与 `[91]` 逐值比，就知道那条公式对不对
    std::uint32_t modsPageCorrection;    // [93] 停稳后自证时的位置修正量（float 位，0 = 一次都不用修）
    // ---- 第十五版（2026-09-23，）：开关写回（走运行时既有的开关服务）----
    //
    // 用户 2026-09-22 裁定："退出模组页时写一次"。落盘位置是**游戏存档分区**
    // （`isaac-switch-mods-state.txt`，运行时既有的开关服务就是这么存的），
    // **绝不写 `romfs/` 里的 `manifest.json`** —— 那份清单在资源覆盖层里，运行期写它是雷区。
    std::uint32_t toggleSetCalls;        // [94] 页内改开关时调 `SetEnabled`（只改内存）的次数
    std::uint32_t toggleSetFailures;     // [95] 其中被拒/失败的次数（未知目录、服务没接上）
    std::uint32_t toggleSaveState;       // [96] 退出页面时那次落盘：0 没试 / 1 成功 / 2 失败
    // ---- 第十六版（2026-09-23，）：局内进出会把我们的贴图句柄废掉 ----
    //
    // 用户实测："有部分对局进去了再退出，只有「模组」那一行的字会消失，纸和其他行都在"，重启就好。
    // 根因：那一行的标签是**我们自己 `LoadImage` 加载的一张图**，而引擎在关卡资源加载时会
    // **把它从图片缓存里卸掉**；我们写成"加载一次就永久有效"（`image.pointer != nullptr` 就直接返回）
    // ⇒ 之后一直拿着失效句柄画，画不出来也不报错。
    // 现在用"是否在局内（`Game*` 有没有值）"的变化当信号：一变就作废句柄、下一帧重载一次。
    std::uint32_t modRowImageReloads;    // [97] 因"局内进出"而重载那一行贴图的次数
    std::uint32_t gamePresent;           // [98] `Game*` 有没有值（1 = 在局内）
    std::uint32_t levelEventCount;       // [99] `MC_POST_NEW_LEVEL` 派发过几次 —— **这一格是判据的留证**：
                                         //      它一变我们就把贴图句柄作废（上一版用 `Game*` 当判据一次都没触发）
    // ---- 第十八版（2026-09-23，）：那一行改用引擎的「按文件路径加载贴图」------------
    //
    // 为什么不是上一批那条 `ANM2::Load` + `ANM2::Render`：真机上它**崩了**，证据是
    // `Data Abort @ 0x0`，栈为「我们的绘制函数 → `ANM2::Render` → `AnimationLayer::RenderFrame`
    // → `GetSourceQuad`」（报告存在 `dist/crash-reports-20260923/`）。即：`.anm2` **找到了**
    // （否则 `ANM2+0x149` 为 0、我们根本不会去画），但里面那张精灵表没载进来 ⇒ 图层取图踩空。
    // 精灵表是引擎按 `<Spritesheet Path="mod_row_zh.png">` 去挂载点找 **`.png`** 的
    // （模组都是 `.png` 与同名 `.pcx` 都放），我们只放了 `.pcx` ⇒ 找不到 ⇒ 空表。
    //
    // ⇒ 本批改走引擎**同族的另一个入口**：`ImageManager::LoadImage(char const* path, ...)`
    //    （按文件名版：和我们一直在用的内存版同一个管理器、同一个返回值形状）。三条好处：
    //    ① 贴图是**磁盘文件背书的**（与所有模组同性质 ⇒ 关卡加载不会清掉它）；
    //    ② **图为空就不画** —— 这条路线在结构上不可能再崩（上一批的崩溃正是"画了空表"）；
    //    ③ 不需要 libc++ 字符串桥，也不用去碰生产代码里的挂载钩子。
    //
    // 这几格是"新路线通到哪一步"的全部判据：
    std::uint32_t modRowFileState;        // [100] 0 没试 / 1 装好（按文件加载可用）/
                                          //       2 入口守卫不过 / 3 管理器与顶点描述符还没取到 /
                                          //       4 所有候选都返回空（引擎没找到文件）/
                                          //       5 语言还没定（等下一帧）
    std::uint32_t modRowFileCandidate;    // [101] 命中的候选序号（1..8；0 = 一条都没成）
    std::uint32_t modRowFileHits;         // [102] 命中掩码（4 条路径 × flag 0/1 = 8 位）
    std::uint32_t modRowFileLoadCalls;    // [103] 文件版 `LoadImage` 调了几次（含失败候选与重读）
    std::uint32_t modRowFileDraws;        // [104] 用这张（磁盘来的）贴图画了几帧
    std::uint32_t modRowFileReloads;      // [105] 因关卡/房间事件**从磁盘重读**的次数
    std::uint32_t modRowFilePathLength;   // [106] 命中那条**路径的长度**（0 = 还没命中）
    std::uint32_t modRowFileFlag;         // [107] 命中那一次的 `flag` 取值（0 或 1）
    std::uint32_t modRowFileGuardState;   // [108] 入口守卫：0 没试 / 1 过 / 2 不过
    // ---- 第十八版（2026-09-23，）：那一行改由引擎自己画（用户定案 A 路线）----
    //
    // 为什么换路线：引擎自己的图层用 `ANM2::LayerState::SetSpriteSheet(SmartPointer<ImageBase>)`
    // 持有**真正的引用计数**（`ImageManager::s_image_reference_freed` 就是管理器对"引用被释放"
    // 的反应）；我们那份是 16 字节裸拷贝（`SmartPointerShim`：不加引用、也不释放）⇒ 管理器一放手，
    // 对象就被回收：显存缓冲清零、而对象内存还看着正常 —— 与现场读数逐条吻合。
    //
    // 做法（PC 版本来就有、Switch 版删掉了）：把 `Item6` 那一层按 PC 的数值补回
    // `gamemenu.anm2`（`tools/gamemenu_mod_row.py --emit-menu-anm2`），于是那一行由引擎自己的
    // **整页**渲染画出来（`Menu_Game::Render` 里只有一次 `ANM2::Render`），生命周期与其余五行同源。
    // 我们那几条兜底绘制**只在没有这一层时**才用（覆盖层没装/被回退时行为一字不变）。
    //
    // 判据就是引擎自己那份菜单动画的**图层数**（`ANM2+0xB0`，`GetLayer`/`Load` 都按它做上界）：
    std::uint32_t modRowNativeLayer;      // [109] 0 还没看 / 1 引擎那份动画里有第六层
                                          //       （那一行由引擎画，我们不画）/
                                          //       2 没有这一层（退回我们自己的兜底绘制）
};
NativeModsMenuProbeState g_NativeModsMenuProbeState{
    1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
// 值个数必须与字段个数一致（110）：多一个少一个都会让后面整段错位，而错位在读数里
// 表现为"某几格莫名非 0"。`runtime/tests/test_probe_state_layout.py` 会数一遍。

namespace {

// ─────────────────────────────────────────────────────────────────────────────
// 偏移与入口指纹（2026-09-21 从 `Repentance.nro` 逐字节取出，`tools/nro_disasm.py` 可复核）
// ─────────────────────────────────────────────────────────────────────────────
//
// 单例都是**经 GOT 槽的两级取值**，`Menu_Mods::Init` 的原话可作模板：
//
//     00410164  adrp x8, 0xaad000
//     00410168  ldr  x8, [x8, #0x1b0]   ; 槽 → &g_MenuManager（模块内 bss 0xABCD48）
//     0041016c  ldr  x0, [x8]           ; 再取一次才是 MenuManager*
//
// 槽号 0xAAD1B0 / 0xAAC648 都在重定位表里登记过（分别对应 `g_MenuManager` / `g_Manager`），
// 是加载器写进去的，所以这两条读法是"加载器保证"的，不是我们猜的。
constexpr std::uintptr_t kMenuManagerSlotOffset = 0xAAD1B0;
constexpr std::uintptr_t kManagerSlotOffset = 0xAAC648;
// `g_Manager` 里"引擎自己那份模组表"的偏移（与运行时的 `kManagerToModManagerOffset` 同一个数）。
constexpr std::uintptr_t kManagerModsOffset = 0x36800;
// `MenuManager::eState` 就在 `MenuManager+0x38`：`Update` 里是 `ldr w8,[x19,#0x38]`，
// `SetState` 结尾是 `str w19,[x20,#0x38]`。读数里顺手记一格，用来在真机上核对状态机的位置。
constexpr std::uintptr_t kMenuManagerStateOffset = 0x38;

// ── 第三版（2026-09-22）：**自己造条目喂给原生页** ──────────────────────────────
//
// `Menu_Mods::Render` 要的数据结构（静态已确认，见 `.hpp`）：
//   * `g_Manager + 0x36800` 起三个字 = `std::vector<条目指针>` 的 begin / end / cap；
//   * 每个条目 `+0x18` 是 libc++ `std::string`（**长串形态**：字节 0 的 bit0 = 1、
//     `+0x28` 处放 `char*`）、`+0x138` 启用位、`+0x13a` "旧版"位。
// 本版先用**固定测试名**验"能不能列出来、位置对不对"，不接清单（下一步再接 metadata.xml 的 `<name>`）。
constexpr std::uintptr_t kManagerModsVectorOffset = 0x36800;
// `Menu_Title` 是 `MenuManager` 的**内嵌成员**（`Update` 里是 `add x0, x19, #0x670`），
// 它的位置（Vector2，两个 float）就在成员开头 ⇒ 拿它当原生页的位置参数（第三版修"位置偏上"）。
constexpr std::uintptr_t kMenuTitleOffset = 0x670;
// 状态表里的另外两个页面（用来对照"摆对了的坐标"长什么样）。
constexpr std::uintptr_t kMenuOptionsOffset = 0x1AF1E8;
constexpr std::uintptr_t kMenuKeyConfigOffset = 0x1AF668;
// 条目：0x140 字节足够（用到的最高偏移是 0x13a），16 字节对齐。
constexpr std::uintptr_t kEntrySize = 0x140;
constexpr std::uintptr_t kEntryStringOffset = 0x18;  // libc++ std::string 起始
constexpr std::uintptr_t kEntryEnabledOffset = 0x138;
constexpr std::uintptr_t kEntryOldOffset = 0x13a;
constexpr std::uint32_t kProbeEntryCount = 3;

// 真实模组的条目（第 B 步）
//
// 容量与"一次最多加载几个模组"**同一个数**：能加载却放不下那种情况没有人会想到去查，
// 也不该出现（`mod_page_runtime_sources.hpp` 里的 `kModPageMaximumMods` 就是它）。
constexpr std::uint32_t kRealEntryCapacity = isaac::runtime::kModPageMaximumMods;
// 名字缓冲要两份：来源侧一份（`CollectModPageSources` 往里写显示名），条目侧一份
// （`BuildModPageEntries` 把名字抄进去，条目里的 `std::string` 从此指向它）。
// 放不下时两条路都是整体放弃（绝不写出半截结构）。
constexpr std::size_t kRealEntryNameBytes = 8192;
constexpr std::size_t kSourceNameBytes = 8192;
// 路径两种形式（带 `rom:/` 前缀 / 相对应用根）怎么试，由 `mod_page_runtime_sources.hpp` 的
// `ResolveModPagePath` 负责（那里有宿主门禁）；这里不再各写一份 `rom:/` 字面量。

// 页面共享的画布原点：`MenuManager+0x3c` 起的那两组 float。
// 证据：`Menu_Title::Render`（`0x41A598`）、`Menu_Save::Render`（`0x4154E4`）、
// `Menu_Game::Render`（`0x40E76C`）、`Menu_Mods::Render`（`0x41080C`）每一个都是
// `ldp w9, w8, [MenuManager, #0x3c]` 读出这两组 float，再与页面自己的位置相加。
// 也就是说"页面画在哪"= 这个偏移 + 页面自己的偏移 —— 上一轮从没读过它。
//
// 2026-09-22：这个偏移朝 `MenuManager::get_target_offset() @0x3FC834` 收敛，
// 而那个函数（反汇编逐条读出来的）算的是：
// s0 = WIDTH  - 480.0
// s1 = HEIGHT - 270.0
// Vector2(s0, s1) * 0.5        ⇒  ((画面宽-480)/2, (画面高-270)/2)
// 实测偏移是 (-27, -15) ⇒ 反解 画面 426×240（426/240 = 1.775，正好 16:9）。
// ⇒ 页面坐标空间是 480×270，而可见屏幕比它小、居中裁切：
// 可见区在页面坐标里 = x∈[27,453]、y∈[15,255]
// ⇒ 页面空间上边 15 格、左右各 27 格是屏幕外的。
// 这就解释了"纸偏上"：`Menu_Mods::Render` 把列表第一行画在页面 y = 偏移.y + 本页位置.y 处，
// 传 (0,0) 时它落在 y = -15 ⇒ 天生就有 15 格在屏幕上方，第一行被切掉。
constexpr std::uintptr_t kMenuManagerCanvasOffset = 0x3c;
// `IsaacRepentance::WIDTH` / `HEIGHT` 的 GOT 槽（`get_target_offset` 里就是这么取的：
// `adrp x8,0xaac000; ldr x8,[x8,#0x650]; ldr s0,[x8]` ⇒ 槽里放的是指向 float 的指针）。
constexpr std::uintptr_t kWidthSlotOffset = 0xAAC650;
constexpr std::uintptr_t kHeightSlotOffset = 0xAAC658;

// 把本页对齐成"一页该有的样子"
//
// **引擎自己的页面约定**（把五个页面的 ANM2 一起量出来的，脚本见存档 README）：
// `titlemenu` / `saveselectmenu` / `statsmenu` / `collectionmenu` / `keyconfigmenu` 的
// 内容**全部落在 x∈[0,480]**、y∈[0,270] 上下 ⇒ **页面原点 = 一个 480 宽页面的左上角**，
// 内容一律往右下铺（`titlemenu` 的背景就是 `480×272 @(0,0)`）。
//
// **而模组页这张纸的设计是"以原点为中心"的**（跟其它页面不一样）：
//   * 纸（`Background`）= `480×900 @(-240,-72)`，中心在原点、上沿在 -72；
//   * 列表条（`Piece1..5`）= `256×32`、pivot `(128,32)` ⇒ 横向也居中在原点；
//   * 涂鸦（`Sketch1..9`）横跨约 ±230。
// ⇒ `Menu_Mods::Render` 里那句 `+200`（反汇编 `0x410824`：`mov w8,#0x43480000` = 200.0f）
//   正是**把"居中"布局挪成"页面框"布局的那一下**。
//
// ⇒ 要让纸铺满页面框 `[0,480]`、上沿正好压在页面顶端，原点应当是 **(240, 72)**：
//   x：纸的中心 = 页面框中心 240；y：纸的上沿 = 页面框顶端 0（相对原点 -72 ⇒ 原点要在 72）。
// 上一版（041）只把"列表第一行"顶到可见区上沿 ⇒ 原点落在 (173, 15)：**横向偏左 67 格、
// 纵向偏上 57 格**（用户："纸位置还是有些偏"）。
constexpr float kPageBoxWidth = 480.0F;      // 一个页面框的宽（五个页面的 ANM2 一致）
constexpr float kModsSheetOffsetX = -240.0F;  // 纸相对原点的左上角 X（居中 ⇒ 半宽）
constexpr float kModsSheetOffsetY = -72.0F;   // 纸相对原点的左上角 Y
constexpr float kModsRenderExtraX = 200.0F;   // `Menu_Mods::Render` 自己加的那 200 格
// 模组页本页原点的目标（页面坐标）：横向 173、纵向 72。
//
// 173 是按 PC 引擎自己的公式换算出来的：
// 把 PC 的 `isaac-ng.exe`（PE32，32 位 —— 必须按 i386 反汇编，按 x86-64 解会得到一堆
// 看着像 RIP 相对的假地址）反汇编后，`MenuManager::Update` 里画布偏移的收敛目标写得很清楚：
// 目标 = ((屏幕宽 − 480)/2 + 家位置x , (屏幕高 − 270)/2 + 家位置y)
// 而 `MenuManager::Init` 给每个页面写的位置是 家位置取负，所以页面的最终原点
// = 偏移 + 位置 + 页面自己加的 (200,0) = 居中量 + (200,0)。
// * PC 的屏幕铺满整个 480×270 画布 ⇒ 居中量 = 0 ⇒ PC 上原点 = (200, 0)；
// * Switch 的屏幕只有 426×240 ⇒ 居中量 = ((426−480)/2, (240−270)/2) = (−27, −15)
// ⇒ 同一套布局换算到 Switch 上，横向应当是 200 − 27 = 173。
// PC 的家位置表也整张读出来了（见 `kModsPageTargetOriginX` 的推导记录）：
// 状态 16（模组页）= (1440, −290)，与 Switch 引擎里那张表逐格相同 ⇒ 格子没用错。
// 纵向仍取 72（真机验收过的值）：按上式的"居中量 + 0"应得 −15，
// 但那会让纸的上沿跑出屏幕外（实测 PC 上纸的上沿是有留白的）⇒ 纵向这一格的残差
// 尚未定性，以真机验收为准，不按公式硬套。
constexpr float kModsPageTargetOriginX = 173.0F;

// 在引擎自己的渲染上下文里画
//
// `MenuManager::Render @0x3FE7B4` 在调各页 `Render` **之前**先做了一整套准备：
// `PushRenderTarget()` → `SetRenderTargetTexture` → `g_Graphics->Clear()` → `SetBlendMode` →
// `LoadShader` → 背景 `FillQuad`，**然后**才 `add x0, x19, #0x670` + `bl Menu_Title::Render`
// （调用点 = 文件偏移 `0x3FE8AC`，`bl` 目标是 PLT 桩 `0x67D500`）。
// 我们上一版却在 `Present` 前中继里**带外**调 `Menu_Mods::Render` ⇒ 那套上下文不存在
// ⇒ 六档位置标定全部落空（这就是它的真正原因）。
//
// 做法：把 `Menu_Title::Render` 的**函数入口**（`0x41A574`）挂上入口中继，回调里先跑原函数
// （标题菜单照常画）、再在**同一上下文**里画我们的页。
// 为什么挂入口而不是改调用点：那个 `bl` 是整份模块里**唯一**引用 `Menu_Title::Render` 的地方
// （扫全部 `bl/b`：指向 PLT 桩 `0x67D500` 的只有 `0x3FE8AC` 一处；直接跳 `0x41A574` 的 0 处；
// 重定位表里指向 `0x41A574` 的引用 0 处）⇒ 语义相同，而入口中继不占游戏字节。
//
// ⚠️ 门控要**我们自己**做：`MenuManager::Render` 每帧**无条件**调用所有页面的 `Render`，
// 各页自己决定画不画（`Menu_Options::Render` 开头 `ldrb w8, [this]` 为 0 就整页跳过）。
// `Menu_Title::Render` 里**没有**任何状态判断，所以"离开标题画面就不出现"不会自动成立 ——
// 回调里按状态机（`MenuManager+0x38 == 1`）门控。
constexpr std::uintptr_t kMenuTitleRenderOffset = 0x41A574;
constexpr std::array<std::uint8_t, 16> kMenuTitleRenderExpected = {
    0xFF, 0x43, 0x01, 0xD1, 0xE9, 0x23, 0x01, 0x6D,
    0xF5, 0x1B, 0x00, 0xF9, 0xFD, 0x7B, 0x02, 0xA9,
};
// `MenuManager::eState` 的"标题画面"那一格。只有这一格才画我们的页。
constexpr std::uint32_t kTitleState = 1;
// `MenuManager::eState` 的"选择界面"那一格（`Menu_Game`）——的"模组"那一行只在这一格动手。
// 静态表：3 = Menu_Game（`MenuManager+0x813A0`），与 `Menu_Game::Update` 开头的 `cmp w8,#0x3` 互证。
constexpr std::uint32_t kGameMenuState = 3;

// 输入扫描范围（第二版）：`ButtonAction` 的号都小于 28；手柄号实测出现过 33，所以扫到 63。
constexpr std::uint32_t kScanActions = 28;
constexpr std::uint32_t kScanControllers = 64;
// 每 8 帧扫一轮（一轮 28×64 = 1792 次查询，摊到 8 帧上可以忽略）。按键是**按住**语义，
// 持续几十帧，所以 7.5 Hz 的采样不会漏。
constexpr std::uint32_t kScanEveryNthUpdate = 8;

// `void MenuManager::SetState(eState)`。
constexpr std::uintptr_t kSetStateOffset = 0x3FE4DC;
constexpr std::array<std::uint8_t, 16> kSetStateExpected = {
    0xFD, 0x7B, 0xBD, 0xA9, 0xF5, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF4, 0x4F, 0x02, 0xA9,
};

// `Menu_Mods::Menu_Mods()` / `Init(const KAGE::Math::Vector2&)` / `Render()`。
constexpr std::uintptr_t kMenuModsCtorOffset = 0x41008C;
constexpr std::array<std::uint8_t, 16> kMenuModsCtorExpected = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};
constexpr std::uintptr_t kMenuModsInitOffset = 0x4100C4;
constexpr std::array<std::uint8_t, 16> kMenuModsInitExpected = {
    0xFF, 0x43, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF5, 0x1B, 0x00, 0xF9,
};
constexpr std::uintptr_t kMenuModsRenderOffset = 0x4107C4;
constexpr std::array<std::uint8_t, 16> kMenuModsRenderExpected = {
    0xFF, 0x03, 0x06, 0xD1, 0xEC, 0x7B, 0x00, 0xFD,
    0xEB, 0x2B, 0x10, 0x6D, 0xE9, 0x23, 0x11, 0x6D,
};

// `Menu_Mods::Reset()`：进入模组页时调一次（把选中项归零、重新读一遍 ModManager 指针）。
// 引擎自己的 `MenuManager::SetState` 在切页时会替各页面做这件事，但**它没有状态 16 那一格**
// ⇒ 这一下得我们替它做（等价于 PC 的 `SetState(模组)` 里那次 `Reset`）。
constexpr std::uintptr_t kMenuModsResetOffset = 0x4101B4;
constexpr std::array<std::uint8_t, 16> kMenuModsResetExpected = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};

// `MenuManager::SetModsOffset(int)`：把"模组页那一格"的滚动目标写成"第 n 条"。
// 进页面时我们先调一次 `SetModsOffset(0)`，让那一格的 Y **立刻**变成确定值 ——
// 否则我们要等页面自己 `Render` 一次才拿得到它，而"算位置"就发生在那一帧之前。
// 用户 2026-09-23 实测："重启游戏后第一次点击模组跳转过去会有 1-2 秒的位置错位之后恢复"，
//   根因就是第一次进来时那一格还是 `Init` 留下的旧值（-290，而实际会是 -216，差 74 格）。
constexpr std::uintptr_t kSetModsOffsetOffset = 0x3FF6F4;
constexpr std::array<std::uint8_t, 16> kSetModsOffsetExpected = {
    0x3F, 0x14, 0x00, 0x71, 0x8A, 0x00, 0x00, 0x54,
    0x08, 0x6B, 0xB8, 0x52, 0x00, 0x01, 0x27, 0x1E,
};

// 模组总开关（PC 的"启用模组"）。`g_Manager` 上的一个字节：
// * `Menu_Mods::Render` 读它选颜色/分支（反汇编 `0x4109xx` 段）；
// * `Menu_Mods::Update` 拿它当输入门控（为 0 时那个页面会忽略所有按键）。
// 我们自己驱动页面时不需要它，但要把它读出来留证 ——
// 它是"这个页面在动画/配色上是不是按'已启用模组'那一套画"的判据。
constexpr std::uintptr_t kManagerModsEnabledOffset = 0x36519;

// `ButtonAction`：这两个键主菜单自己不用（它只认上下左右/A/B/START 之类），不会被抢走。
constexpr std::uint32_t kActionItem = 9;       // Switch 上的 ZR
constexpr std::uint32_t kActionPillCard = 10;  // Switch 上的 ZL

// `MenuManager::eState` 的上界。静态表（`Update` 的分发表，`cmp w8,#0xf` + 字节跳表）是
// 0..15，逐格都对得上具体页面：
// 1 Menu_Title(+0x670)   2 Menu_Save(+0x7d8)      3 Menu_Game(+0x813A0)
// 4 DailyChallenge(+0x817F0)  5 Character(+0x1A2658)  6 SpecialSeed(+0x1A3A70)
// 7 Challenge(+0x1A3C28) 8 Collection(+0x1A3DA8)  9 Stats(+0x1A40B0)
// 10 Options(+0x1AF1E8)  11 ControllerSelect(+0x1AF4E8) 12 KeyConfig(+0x1AF668)
// 13 Cutscenes(+0x1AF7D8) 14 Bestiary(+0x1AF940)  15 Custom_Challenge(+0x1AFDA0)
// 状态 0 走默认分支（什么都不做）。16 = 模组页这一格被 Switch 版从分派表里删掉了，
// 但引擎自己的数据（每个状态的槽位 `+0x1AFF08 + 状态*8`、`SetModsOffset` 写的 `+0x1AFF8C`
// 正好是第 16 格）与整个 `Menu_Mods` 都还在 ⇒ 就是照 PC 的做法走这一格。
constexpr std::uint32_t kLastState = 15;

// 失败码（写进诊断字 [7]，读数里一眼看出卡在哪一步）。
enum : std::uint32_t {
    kFailureNone = 0,
    kFailureInputUnavailable = 1,
    kFailureModuleNotFound = 2,
    kFailureSetStateGuard = 3,
    kFailureMenuManagerNull = 4,
    kFailureMenuModsGuard = 5,
    kFailureRenderGuard = 6,
    kFailureEntryBuild = 7,   // 条目没造出来
    kFailureManagerNull = 8,  // `g_Manager` 没读到（写条目的前置条件）   // 条目没造出来（名字区/参数不合法）⇒ 整体放弃，不让页面看到半截结构
    kFailureTitleRelayGuard = 9,  // `Menu_Title::Render` 入口 16 字节与期望不符（版本不对，不挂钩）
    kFailureModRowGuard = 10,     // `Menu_Game::Render` 入口 16 字节与期望不符（同上）
    kFailureMenuModsResetGuard = 11,  // `Menu_Mods::Reset` 入口 16 字节与期望不符
};

// `initResult` 的取值（诊断字 [5]）。
enum : std::uint32_t {
    kInitNotTried = 0,
    kInitOk = 1,
    kInitGuardMismatch = 2,
    kInitMenuManagerNull = 3,
    kInitModuleNotFound = 4,
};

// `realSourceState` 的取值（诊断字 [32]，）。
enum : std::uint32_t {
    kRealSourceNotTried = 0,
    kRealSourceReal = 1,      // 页面上是真实模组（发现结果 + `<name>`）
    kRealSourceFallback = 2,  // 真实数据没取到 ⇒ 退回那三个固定测试名
};

// `modRowFileState` 的取值（诊断字 [100]，）——"引擎按文件路径加载贴图"那条路的进度。
// 与内存那条路（[62]）同一套编号形状，便于对照读数。
enum : std::uint32_t {
    kFileRouteNotTried = 0,
    kFileRouteReady = 1,            // 装好：磁盘贴图已拿到，绘制优先用它
    kFileRouteGuardFailed = 2,      // 按文件名版 `LoadImage` 的入口 16 字节不符
    kFileRouteContextMissing = 3,   // 管理器指针/顶点描述符还没取到（内存那条路会先取）
    kFileRouteAllNull = 4,          // 四条路径 × 两种 flag 都试过，引擎给的全是空
    kFileRouteLanguagePending = 5,  // 语言还没定 ⇒ 等下一帧（不是失败）
};

// 手动模式的临时对象：`Menu_Mods` 是 `MenuManager` 的内嵌成员（大小未知），所以这里给一块
// 足够宽、**静态零初始化**的内存当壳。只在探针里这么干：生产路径永远用引擎自己那块对象。
// 静态已确认的布局：`+0x08` Vector2、`+0x10` ANM2、`+0x168` 字节、`+0x170` u64
// ⇒ 0x800 足够，且四者都落在零初始化内存里（与 `ctor` 的初始化效果一致）。
alignas(16) std::uint8_t g_ManualObject[0x800]{};
float g_ManualPosition[2] = {0.0F, 0.0F};  // `KAGE::Math::Vector2` = 两个 float

// 三个自造条目（名字固定）、它们的指针数组、以及名字缓冲。静态零初始化，不写堆。
// 条目数组与"名字"分开放：名字必须 NUL 结尾的 C 串（`Render` 只当 C 串用）。
alignas(16) std::uint8_t g_ProbeEntries[kProbeEntryCount][kEntrySize]{};
std::uintptr_t g_ProbeEntryPointers[kProbeEntryCount]{};
// `begin/end/cap` 三个字（8 字节对齐，`memcpy` 进引擎结构）。
alignas(8) std::uintptr_t g_ProbeVector[3]{};
// 名字副本（必须是我们自己拥有的稳定内存 —— 不能指向字面量）。
char g_ProbeNameArena[128]{};
std::uint32_t g_VectorWritten = 0;

// 逐字节核对一个引擎入口的 16 字节序言（核对通过才把地址交出去；不符就只是"不调用"）。
// 位置：起上移到这一节之前 —— 真实模组那一路要在 `TryPrepareModsVector` 里
// 校验 `File::Exists` 的入口，而这个函数原先定义在文件后半段。定义本身没有改。
bool Guarded(const TargetModule& module, std::uintptr_t offset,
             const std::array<std::uint8_t, 16>& expected, std::uintptr_t* address) {
    if (module.size < expected.size() || offset > module.size - expected.size()) {
        return false;
    }
    const std::uintptr_t candidate = module.base + offset;
    if (candidate < module.base || candidate + expected.size() > module.base + module.size) {
        return false;
    }
    if (std::memcmp(reinterpret_cast<const void*>(candidate), expected.data(),
                    expected.size()) != 0) {
        return false;
    }
    *address = candidate;
    return true;
}

// 单例的两级取值（槽 → 全局变量地址 → 值）。返回 false = 这条链不成立，不许再往下用。
// 定义在本文件后半段；的 `TryPrepareModsVector` 要拿它读 `g_Manager`，所以这里先声明。
bool ReadSingleton(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* out);

// 真实模组那一路的存储与来源（第 B 步）
//
// 与上面那套固定名**分开存放**：两条路各自有完整的条目数组与名字缓冲，谁也不用担心
// 被对方的半截状态污染（选哪一条只在 `TryPrepareModsVector` 里判一次）。
alignas(16) std::uint8_t g_RealEntries[kRealEntryCapacity][kEntrySize]{};
std::uintptr_t g_RealEntryPointers[kRealEntryCapacity]{};
alignas(8) std::uintptr_t g_RealVector[3]{};
isaac::runtime::ModPageEntrySource g_RealSources[kRealEntryCapacity]{};
char g_RealEntryNameArena[kRealEntryNameBytes]{};   // 条目里的字符串指向它
char g_RealSourceNameArena[kSourceNameBytes]{};     // 来源的 displayName 指向它
char g_RealMetadataScratch[isaac::runtime::kModPageMetadataCapacity]{};
char g_RealMetadataPath[isaac::runtime::kModPageMetadataPathCapacity]{};

// 真实那一路用到的引擎入口。
//
// 2026-09-22 事故后重写（续七十）：不再用"存在性检查 + 原样读"。
// 那条路在"输入形式不被 `nn::fs` 认"时会直接 Abort（`File::OpenRead` 不做挂载解析）。
// 现在只做一件事：让引擎把路径解析成它能打开的绝对路径，再把那一条交给读函数。
//
// 校验都是一次性的（第一次进 `TryPrepareModsVector` 时做），之后每帧不再重扫模块表。
struct RealSourceContext {
    GameFileReader::Bindings bindings{};
    bool bindingsOk{false};
    using GetMountedFn = char* (*)(void*, const char*);
    // `IContentManager::GetMountedFilePath`：返回堆上挂载绝对路径（空 = 不在任何挂载点）。
    GetMountedFn getMounted{nullptr};
    // `g_ContentManager` 对象指针（`base + 0xAAC748` 读一次就是它）。
    void* contentManager{nullptr};
    // 还那条堆路径用的 —— 必须用游戏自己的 `operator delete[]`。
    GameFileReader::GameOperatorDeleteArrayFn freePath{nullptr};
};
RealSourceContext g_RealSourceContext{};

// 目录来源：直接读 `mod_menu_api` 收下的那份"开机扫描发现到的模组"。
// 为什么不自已再列一次目录：那会变成两处各维护一份，用户在原生日志页上看到的名字与
// 自己的 Lua 模组菜单里看到的对不上时，没有人能判断哪一份是对的。
std::uint32_t ProvideRealDirectories(void* /*context*/, const char** out,
                                     std::uint32_t capacity) {
    const std::size_t count = isaac::runtime::ModMenuDiscoveredCount();
    if (count == 0) {
        return 0;
    }
    if (count > capacity) {
        return static_cast<std::uint32_t>(count);  // 装不下：如实报数，由调用方整体放弃
    }
    for (std::size_t index = 0; index < count; ++index) {
        const char* name = isaac::runtime::ModMenuDiscoveredDirectory(index);
        if (name == nullptr || name[0] == '\0') {
            return 0;
        }
        out[index] = name;
    }
    return static_cast<std::uint32_t>(count);
}

// 开关来源：就是那张纸右边"开着/关着"的依据（同一份数据源，见 `RuntimeMods.List()`）。
bool ProvideRealEnabled(void* /*context*/, const char* directory) {
    return isaac::runtime::ModMenuDiscoveredEnabled(directory);
}

// "把这个路径解析成引擎自己能打开的绝对路径" —— 绝不盲开的最后一步。
//
// 反汇编依据（`python3 tools/nro_disasm.py 0x4C2340 0x84`）：`GetMountedFilePath` 内部是
// `get_mount_point(path)` + `FileMap::Get` + `CreateCleanPath`，全程只查表、不开文件
// ⇒ 解析不到只是返回空，不会 Abort。两个引擎调用点（`ImageManager::LoadImage` 文件版
// `0x4D206C`、`File::Exists` `0x4CCCFC`）都证明 `g_ContentManager` 是
// `adrp 0xaac000; ldr x0,[x0,#0x748]` —— 读一次就是对象指针。
//
// 这一层只做"接引擎"；两种输入形式怎么试那套逻辑在
// `mod_page_runtime_sources.hpp` 的 `ResolveModPagePath` 里（那里有宿主门禁）。
bool ResolveMountedPath(void* context, const char* path, char* out, std::size_t capacity) {
    auto* source = static_cast<RealSourceContext*>(context);
    if (source == nullptr || source->getMounted == nullptr || source->contentManager == nullptr ||
        source->freePath == nullptr || path == nullptr || out == nullptr) {
        return false;
    }
    char* mounted = source->getMounted(source->contentManager, path);
    if (mounted == nullptr) {
        return false;  // 这条路径不在任何挂载点 ⇒ 正常（`metadata.xml` 本来就是可选的）
    }
    const std::size_t length = std::strlen(mounted);
    const bool fits = length + 1 <= capacity;
    if (fits) {
        std::memcpy(out, mounted, length + 1);
    }
    // 引擎用 `new[]` 分配的，**只能**用引擎的 `operator delete[]` 还。
    source->freePath(mounted);
    return fits;
}

bool ResolveMetadataPath(void* context, const char* path, char* resolved,
                         std::size_t capacity) {
    std::uint32_t form = 0;
    if (!isaac::runtime::ResolveModPagePath(path, &ResolveMountedPath, context, resolved, capacity,
                                            &form)) {
        ++g_NativeModsMenuProbeState.metadataAbsent;
        return false;
    }
    g_NativeModsMenuProbeState.metadataExistsForm |= form;
    return true;
}

// 真正把 `metadata.xml` 读进来（`GameFileReader::ReadTextFile`，与清单/脚本读取同一个入口）。
bool ReadMetadataText(void* context, const char* path, char* buffer, std::size_t capacity,
                      std::size_t* length) {
    const auto* source = static_cast<const RealSourceContext*>(context);
    if (source == nullptr || !source->bindingsOk || buffer == nullptr) {
        ++g_NativeModsMenuProbeState.metadataReadFailed;
        return false;
    }
    // `ReadTextFile` 只在"非诊断构建"或"stage 13"里存在（`game_file_reader.hpp` 的 `#if`）。
    // 探针本身不挑构建形状，所以这一块跟着它的可见性走：不可见时如实记一次"读失败"
    // ⇒ 所有名字退目录名，而不是编译不过（PROBE_BREAK 与 DIAGNOSTIC_STAGE 在 Makefile 里
    // 并没有互斥约束，所以这不是假想组合）。
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    const auto result = GameFileReader::ReadTextFile(
        source->bindings, path, reinterpret_cast<u8*>(buffer), capacity, length);
    if (result != GameFileReader::TextReadResult::Success) {
        ++g_NativeModsMenuProbeState.metadataReadFailed;
        return false;
    }
    ++g_NativeModsMenuProbeState.metadataReadOk;
    return true;
#else
    ++g_NativeModsMenuProbeState.metadataReadFailed;
    return false;
#endif
}

// 把"存在性判定 + 读文件"合成 `CollectRuntimeModPageSources` 要的那个 reader：
// 先解析（`ResolveThenRead` 的纪律），解析不过 ⇒ 绝不去读。
bool CollectMetadataText(void* context, const char* path, char* buffer, std::size_t capacity,
                         std::size_t* length) {
    auto* source = static_cast<RealSourceContext*>(context);
    if (source == nullptr) {
        return false;
    }
    char resolved[isaac::runtime::kModPageMetadataPathCapacity]{};
    if (isaac::runtime::MountedReadResult::Read !=
        isaac::runtime::ResolveThenRead(path, &ResolveMetadataPath, source, &ReadMetadataText,
                                        source, resolved, sizeof(resolved), buffer, capacity,
                                        length)) {
        return false;
    }
    return true;
}

// 真实那一路的引擎入口校验（只做一次）。返回是否具备"取真实模组名"的全部前提。
void PrepareRealSourceContext(const TargetModule& module) {
    if (g_NativeModsMenuProbeState.metadataBindings != 0) {
        return;  // 已经试过了（成功或失败都算试过 —— 不重复扫模块表）
    }
    g_NativeModsMenuProbeState.metadataBindings =
        GameFileReader::VerifyBindings(module, &g_RealSourceContext.bindings) ? 1U : 2U;
    g_RealSourceContext.bindingsOk = g_NativeModsMenuProbeState.metadataBindings == 1U;

    // ① 挂载解析入口：**优先用中继记下的原函数**。为什么不能逐字节守卫：这个函数的入口
    //    已经被我们自己的贴图桥改写成跳转了（`HookId::ContentGetMountedFilePath`），
    //    比原版序言必然失败（2026-09-21 真机掩码 0x20 就是这么来的）。
    //    中继没装（返回 0）时才退回"守卫过的引擎入口" —— 那种情况下入口是原版、守卫才有意义。
    auto getMounted = isaac::runtime::Original<RealSourceContext::GetMountedFn>(
        isaac::runtime::HookId::ContentGetMountedFilePath);
    if (getMounted != nullptr) {
        g_RealSourceContext.getMounted = getMounted;
        g_NativeModsMenuProbeState.metadataResolveFn = 1;
    } else {
        std::uintptr_t direct = 0;
        if (Guarded(module, kContentManagerGetMountedFilePathOffset,
                    kContentManagerGetMountedFilePathExpectedBytes, &direct)) {
            g_RealSourceContext.getMounted =
                reinterpret_cast<RealSourceContext::GetMountedFn>(direct);
            g_NativeModsMenuProbeState.metadataResolveFn = 2;
        } else {
            g_NativeModsMenuProbeState.metadataResolveFn = 3;
        }
    }

    // ② `g_ContentManager` 对象指针：`base + 0xAAC748` **读一次**就是它（两个引擎调用点互证）。
    {
        const auto slot = *reinterpret_cast<volatile const std::uintptr_t*>(
            module.base + kContentManagerGotSlotOffset);
        if (slot != 0 && (slot & 7u) == 0) {
            g_RealSourceContext.contentManager = reinterpret_cast<void*>(slot);
        } else {
            g_NativeModsMenuProbeState.metadataResolveFn = 3;
        }
    }

    // ③ 还内存用的"游戏的 `operator delete[]`"（`GetMountedFilePath` 的返回值是 `new[]` 出来的）。
    std::uintptr_t freePath = 0;
    if (Guarded(module, kGameOperatorDeleteArrayOffset, kGameOperatorDeleteArrayExpectedBytes,
                &freePath)) {
        g_RealSourceContext.freePath =
            reinterpret_cast<GameFileReader::GameOperatorDeleteArrayFn>(freePath);
    } else {
        g_NativeModsMenuProbeState.metadataResolveFn = 3;  // 拿不到就**不解析**（否则会漏内存）
    }
}

// 一帧最多试几次"等发现结果"（≈15 秒 @60fps）。
//
// 为什么要等：发现结果（`ModMenuPublishDiscovered`）是启动的模组加载填进去的，
// 而那是 worker 线程 —— 探针构建还专门给了它 5 秒启动延迟（`WORKER_STARTUP_DELAY_SECONDS=5`）。
// 而"`g_MenuManager` 非空"只说明菜单系统构造好了，不保证模组已经扫完。
// 不等的话，开机那一下会读到"0 个模组"并把固定测试名写死，而那张表只会写一次
// （`g_VectorWritten`）⇒ 整轮真机白跑。这是"看起来没模组"和"时序还没到"必须分开的那种坑。
constexpr std::uint32_t kRealAttemptLimit = 900;
std::uint32_t g_RealAttempts = 0;

// 试着把条目表准备好并把 `begin/end/cap` 写进 `g_Manager + 0x36800`。
//
// 返回 true = 表已经就绪（真实数据、或"等到上限仍没结果就退固定测试名"两条路都算），
// 这时才可以往下走 `ctor` + `Init`；返回 false = 还在等发现结果，这一帧什么都别做。
// 必须在 `Init` 之前写：`Init` 会把 begin 抄进 `对象+0x170`（`Update` 用它翻转启用位）。
// 布局本身由 `mod_page_entries.hpp` 负责（那里逐字节被宿主门禁钉住）—— 本函数只负责"接线"。
// 2026-09-22 修正（真机读数发现）：这里要的是 `g_Manager`，不是 `MenuManager`！
// `Menu_Mods::Render` 是从 `g_Manager + 0x36800` 读那张表的；我第一版把从 MenuManager GOT 槽
// 取到的指针传了进来 ⇒ 24 字节写到了 `MenuManager+0x36800` 这个与模组无关的字段，
// 而引擎那张表**依旧是空的** ⇒ 真机现象是"只有一张纸、一行名字都没有"。
//
// 数据源：真实模组优先（发现结果 + `metadata.xml` 的 `<name>`），
// 一条都取不到时退回第三版那三个固定测试名 —— **并把它记进诊断字 [32]**。
bool TryPrepareModsVector(const TargetModule& module) {
    if (g_VectorWritten != 0) {
        return true;
    }
    if (g_RealAttempts < kRealAttemptLimit) {
        ++g_RealAttempts;
    }
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kManagerSlotOffset, &manager)) {
        g_NativeModsMenuProbeState.lastFailure = kFailureManagerNull;
        return false;
    }
    PrepareRealSourceContext(module);
    isaac::runtime::ModPageRuntimeStats stats{};
    const std::uint32_t real = isaac::runtime::CollectRuntimeModPageSources(
        &g_RealSources[0], kRealEntryCapacity, &ProvideRealDirectories, nullptr,
        &ProvideRealEnabled, nullptr, &CollectMetadataText, &g_RealSourceContext,
        g_RealSourceNameArena, sizeof(g_RealSourceNameArena), g_RealMetadataPath,
        g_RealMetadataScratch, &stats);
    g_NativeModsMenuProbeState.realDirectoryCount = stats.directories;
    g_NativeModsMenuProbeState.realEnabledCount = stats.enabled;

    std::size_t nameBytes = 0;
    std::uint32_t wanted = 0;
    std::uint32_t built = 0;
    std::uintptr_t* vector = nullptr;
    if (real != 0) {
        wanted = real;
        built = isaac::runtime::BuildModPageEntries(
            &g_RealEntries[0][0], &g_RealEntryPointers[0], g_RealVector, wanted,
            &g_RealSources[0], g_RealEntryNameArena, sizeof(g_RealEntryNameArena), &nameBytes);
        vector = g_RealVector;
        g_NativeModsMenuProbeState.realSourceState = kRealSourceReal;
        g_NativeModsMenuProbeState.realEntryCount = built;
    }
    const bool realReady = built == wanted && wanted != 0;
    // 该等还是该退，由那个纯判定说了算（`DecideModPageSource`，宿主门禁逐条钉着）。
    switch (isaac::runtime::DecideModPageSource(realReady, stats.directories, g_RealAttempts,
                                                kRealAttemptLimit)) {
        case isaac::runtime::ModPageSourceDecision::Wait:
            // 发现结果还没出来（启动的模组扫描在 worker 线程上，探针构建还给了 5 秒延迟）
            // ⇒ 这一帧什么都别做。**绝不能**在这里写死那张表：它只会写一次。
            g_NativeModsMenuProbeState.realSourceState = kRealSourceNotTried;
            return false;
        case isaac::runtime::ModPageSourceDecision::Ready:
            break;
        case isaac::runtime::ModPageSourceDecision::Fallback:
            // 真实数据没取到（或条目没造全）⇒ **退回固定测试名**，并如实记下来。
            // 为什么保留这条退路：纸上出现 `PROBE-MOD-A` 是"真实数据没取到"的**信号**，
            // 而"纸上什么都没有"是另一种现象（渲染/位置那一层），两者不该混在一起看。
            g_NativeModsMenuProbeState.realSourceState = kRealSourceFallback;
            g_NativeModsMenuProbeState.realEntryCount = 0;
            {
                const isaac::runtime::ModPageEntrySource sources[kProbeEntryCount] = {
                    {"PROBE-MOD-A", true, false},
                    {"PROBE-MOD-B", false, false},
                    {"PROBE-MOD-C", true, true},
                };
                wanted = kProbeEntryCount;
                built = isaac::runtime::BuildModPageEntries(
                    &g_ProbeEntries[0][0], &g_ProbeEntryPointers[0], g_ProbeVector, wanted,
                    sources, g_ProbeNameArena, sizeof(g_ProbeNameArena), &nameBytes);
                vector = g_ProbeVector;
            }
            if (built != wanted) {
                g_NativeModsMenuProbeState.lastFailure = kFailureEntryBuild;
                return false;  // 制造失败就整体放弃：绝不让页面读到半截结构
            }
            break;
    }
    std::memcpy(reinterpret_cast<void*>(manager + kManagerModsVectorOffset), vector,
                sizeof(g_ProbeVector));
    g_VectorWritten = 1;
    return true;
}

// `Menu_Title::Render` 的入口中继：原始入口（安装器给的回退地址）与"装过没有"。
std::uintptr_t g_TitleRelayOriginal = 0;
std::uint32_t g_TitleRelayTried = 0;
// `Menu_Mods::Render` 的地址，在 `TryInitManualPage` 里过一次入口守卫后缓存下来 ——
// 渲染回调每帧都要用它，不能每帧重扫一遍模块表。
std::uintptr_t g_MenuModsRender = 0;
// `MenuManager::SetState` 入口中继的"回退入口"（安装，起 `ApplyState` 也要用它）。
// 为什么它必须在这里声明：`ApplyState`（下面几百行）要用它来判断"该走中继还是走守卫直调"，
// 而中继装好之后入口 16 字节已被改写 ⇒ 逐字节守卫必然对不上（的 bug 就是这么来的）。
std::uintptr_t g_SetStateRelayOriginal = 0;
bool PublishProbeOriginal(std::uintptr_t original,void* opaque) noexcept {
    auto* slot=static_cast<std::uintptr_t*>(opaque);
    __atomic_store_n(slot,original,__ATOMIC_RELEASE);
    return true;
}

// 模组页"位置只定一次、之后跟着画布走"用的小状态机。
// 见 `NativeModsMenuProbeUpdate` 里那段位置的注释（为什么两个方向都跟着走、为什么第二帧才定）。
std::uint32_t g_ModsPagePositionSet = 0;
std::uint32_t g_ModsPageSettledFrames = 0;
std::uint32_t g_ModsPageStillFrames = 0;
std::uint32_t g_ModsPageCorrected = 0;
// 上一帧是否在模组页里 —— 用来识别"刚刚离开"这一刻（在那时落盘一次）。
std::uint32_t g_ModsPageWasActive = 0;
// 关卡/房间事件的回调号（就是 PC `ModCallbacks` 的数值，与读数工具那张表同一份口径；
// `runtime/tests/test_callback_dispatch_counters.py` 钉着那张表，抄错会被门禁红掉）。
constexpr std::size_t kCallbackPostNewLevel = 18;
constexpr std::size_t kCallbackPostNewRoom = 19;
// 上一帧看到的"关卡事件 / 房间事件"计数（任何一个变了 ⇒ 资源可能被换过一轮）。
std::uint32_t g_LevelEventCount = 0;
std::uint32_t g_RoomEventCount = 0;
// 那张贴图的缓存键（`LoadImage` 的 `name` 参数）每次重载都换一个。
//
// 为什么必须换：`LoadImage` 的第 5 个参数就是"对象自己的路径（缓存键 / GetFilePath）"——
// 用同一个名字再调一次，引擎把缓存里那个已经失效的条目原样还给我们（真机读数：
// `[97] = 1` 重载发生过、`[62] = ★贴图好了`、画了 3856 帧，可屏幕上一个字都没有）。
// ⇒ 换名字 = 缓存未命中 = 真的重新解码、重新建纹理。
std::uint32_t g_ModRowImageGeneration = 0;
char g_ModRowImageName[24] = "modrowg0.pcx";

float g_ModsPagePositionX = 0.0F;
float g_ModsPagePositionY = 0.0F;
float g_ModsPageTargetOffsetX = 0.0F;
float g_ModsPageTargetOffsetY = 0.0F;
float g_ModsPageLastOffsetX = 0.0F;
float g_ModsPageLastOffsetY = 0.0F;
// "算画布停稳"的帧数阈值（60 Hz 下 20 帧 ≈ 1/3 秒；转移动画本身约 0.5~0.9 秒）。
constexpr std::uint32_t kSettleFrames = 20;

// 把某个页面对象头部的两组 float 按原始位记进诊断字（读数端解成浮点看哪个是屏幕坐标）。
void RecordPagePosition(std::uintptr_t page, std::uint32_t* x, std::uint32_t* y) {
    if (x != nullptr) {
        std::memcpy(x, reinterpret_cast<const void*>(page), sizeof(*x));
    }
    if (y != nullptr) {
        std::memcpy(y, reinterpret_cast<const void*>(page + sizeof(*x)), sizeof(*y));
    }
}

// 原生页的位置：起不再借用别的页面坐标（实测三个页面头部都在 0 附近 ⇒ 位置不在
// 对象头部），固定给 `(0,0)`，理由写在 `TryInitManualPage` 里。这个读函数随之删掉。

// 上一帧的两个键：**自己算边沿**。引擎那份"刚按下"状态在我们跑到它的时候是空的
// （这条结论写在 `input_api.cpp` 里），所以沿用"按住"位图 + 自记状态。
std::uint32_t g_LastItem = 0;
std::uint32_t g_LastPillCard = 0;
std::uint32_t g_ComboLatched = 0;
// 自己的帧计数（只用来决定"该不该扫一轮输入"，与引擎帧计数无关）。
std::uint32_t g_UpdateCount = 0;
// 自动驱动只做一次（第二版）：理由见 `.hpp` 的"第二版"一节。
std::uint32_t g_AutoStarted = 0;

// 与 `input_api.cpp` 同一个调用形状（那处是权威）：第一个参数被跳板覆盖，动作号进 x1、
// 手柄号进 x2、第三个引擎参数（PC 的可选 `entity`）一律给空指针。
using ActionQueryFn = bool (*)(void*, std::uint32_t, std::uint32_t, void*);

// "任一控制器答'是'" —— 第二版的关键修正：不再假设手柄号是 0。
// 项目历史结论（2026-09-16 的 021）是"引擎只认玩家自己的 controller 值（实测出现过 33）"，
// 第一版就栽在这上面（真机读数里按键计数全 0，而更新中继确实在跑）。
//
// 第三版修正（2026-09-22，本轮静态查证）：游戏自己的菜单代码用的是 `0xFFFFFFFF`
// ——`Menu_Title::Update @0x41A4F0` 里是 `mov w2, #-1`（controller）+ `mov w1, #0xe`（动作
// MENUCONFIRM）再调 `IsActionPressed/IsButtonTriggered`。"任意手柄"这个值我们以前没用过，
// 而第二版的扫描范围只到 63 ⇒ 下一轮真机还会漏。现在把它单独问一次（并且只问一次，
// 因为它的语义是"任意"，不需要按手柄号循环）。
constexpr std::uint32_t kAnyController = 0xFFFFFFFFu;

bool HeldByAnyone(const ActionQueryFn query, std::uint32_t action) {
    if (query(nullptr, action, kAnyController, nullptr)) {
        return true;
    }
    for (std::uint32_t controller = 0; controller < kScanControllers; ++controller) {
        if (query(nullptr, action, controller, nullptr)) {
            return true;
        }
    }
    return false;
}

// 每 `kScanEveryNthUpdate` 帧扫一轮"动作号 × 手柄号"，把结果记成两张掩码。
// 这不是为了"让某个键生效"，而是为了下一次不必再猜：掩码直接告诉我们
// 哪些动作号会被按住、哪些手柄号会答"是"。
void ScanInput(const ActionQueryFn query) {
    std::uint32_t actions = 0;
    std::uint32_t controllers = 0;
    for (std::uint32_t action = 0; action < kScanActions; ++action) {
        // `0xFFFFFFFF`（任意手柄）单独问一次；答"是"就把它记在第 31 位，读数里一眼看得出来
        // （0..30 位留给真实手柄号）。
        if (query(nullptr, action, kAnyController, nullptr)) {
            actions |= 1u << action;
            controllers |= 1u << 31;
        }
        for (std::uint32_t controller = 0; controller < kScanControllers; ++controller) {
            if (!query(nullptr, action, controller, nullptr)) {
                continue;
            }
            actions |= 1u << action;
            if (controller < 32) {
                controllers |= 1u << controller;
            }
        }
    }
    g_NativeModsMenuProbeState.heldActionMask = actions;
    g_NativeModsMenuProbeState.heldControllerMask = controllers;
    ++g_NativeModsMenuProbeState.scanRounds;
}

// 读一个 GOT 槽里存的东西（= 加载器解析出来的地址）。槽本身必须落在模块映像内。
bool ReadSlot(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* value) {
    if (module.size < sizeof(std::uintptr_t) ||
        slotOffset > module.size - sizeof(std::uintptr_t)) {
        return false;
    }
    const std::uintptr_t slot = module.base + slotOffset;
    if (slot < module.base || slot + sizeof(std::uintptr_t) > module.base + module.size) {
        return false;
    }
    std::memcpy(value, reinterpret_cast<const void*>(slot), sizeof(*value));
    return true;
}

// 可见屏幕有多大（`IsaacRepentance::WIDTH` / `HEIGHT`）。
// GOT 槽里放的是指向 float 的指针（`get_target_offset` 里 `ldr x8,[x8,#0x650]; ldr s0,[x8]`），
// 所以这里读两步：槽 → 指针 → 那个 float。
// 为什么要它：页面坐标空间是 480×270，可见屏幕比它小、居中裁切 —— 可见区在页面坐标里是
// `x∈[-偏移.x, -偏移.x+画面宽]`、`y∈[-偏移.y, -偏移.y+画面高]`。算"第一行有没有被切"要用它。
void RecordScreenSize(const TargetModule& module) {
    const auto readFloatGlobal = [&module](std::uintptr_t slotOffset, std::uint32_t* out) {
        std::uintptr_t target = 0;
        if (!ReadSlot(module, slotOffset, &target) || target == 0) {
            return false;
        }
        float value = 0.0F;
        std::memcpy(&value, reinterpret_cast<const void*>(target), sizeof(value));
        std::memcpy(out, &value, sizeof(*out));
        return true;
    };
    if (!readFloatGlobal(kWidthSlotOffset, &g_NativeModsMenuProbeState.screenWidth)) {
        g_NativeModsMenuProbeState.screenWidth = 0;
    }
    if (!readFloatGlobal(kHeightSlotOffset, &g_NativeModsMenuProbeState.screenHeight)) {
        g_NativeModsMenuProbeState.screenHeight = 0;
    }
}

// 单例的两级取值（槽 → 全局变量地址 → 值）。返回 false = 这条链不成立，不许再往下用。
bool ReadSingleton(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* out) {
    std::uintptr_t global = 0;
    if (!ReadSlot(module, slotOffset, &global) || global == 0) {
        return false;
    }
    // 全局变量本身在模块的 bss 里（例如 `g_MenuManager` 在 0xABCD48），所以这里只做
    // 非空与对齐检查，不要求它落在映像内：超出映像尾部的那段正是 bss。
    if ((global & (sizeof(std::uintptr_t) - 1)) != 0) {
        return false;
    }
    std::uintptr_t value = 0;
    std::memcpy(&value, reinterpret_cast<const void*>(global), sizeof(value));
    if (value == 0) {
        return false;
    }
    *out = value;
    return true;
}

bool Edge(std::uint32_t* last, bool now) {
    const bool pressed = now && *last == 0;
    *last = now ? 1U : 0U;
    return pressed;
}

// 引擎自己那份模组表：`g_Manager + 0x36800` 的 begin/end 指针对（`Render` 用它算行数）。
// 只读这对指针，不碰任何一项（`ListMods()` 那种遍历在真机会中断）。
void RefreshEngineModList(const TargetModule& module) {
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kManagerSlotOffset, &manager)) {
        g_NativeModsMenuProbeState.managerOk = 0;
        g_NativeModsMenuProbeState.modListBytes = 0;
        return;
    }
    g_NativeModsMenuProbeState.managerOk = 1;
    const std::uintptr_t beginAddress = manager + kManagerModsOffset;
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    std::memcpy(&begin, reinterpret_cast<const void*>(beginAddress), sizeof(begin));
    std::memcpy(&end, reinterpret_cast<const void*>(beginAddress + sizeof(begin)), sizeof(end));
    // `begin`/`end` 该是一对合法指针（模块映像之外的那部分就是引擎自己堆上的模组表）。
    // 为什么要单独记这一格：如果两个值根本不像指针，那 [10] 的 0 不能读成"空表" ——
    // 那只说明我们对 `Manager+0x36800` 这个结构的解释不对，得回去重新看静态证据。
    const bool pointerLike = begin >= 0x1000 && end >= 0x1000 &&
                            (begin & 7u) == 0 && (end & 7u) == 0 && end >= begin;
    g_NativeModsMenuProbeState.modListPointersOk = pointerLike ? 1U : 0U;
    if (!pointerLike) {
        g_NativeModsMenuProbeState.modListBytes = 0;
        return;
    }
    const std::uintptr_t bytes = end - begin;
    g_NativeModsMenuProbeState.modListBytes =
        bytes > 0xFFFFFFFFULL ? 0xFFFFFFFFU : static_cast<std::uint32_t>(bytes);
}

void ApplyState(const TargetModule& module, std::uint32_t state) {
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kMenuManagerSlotOffset, &manager)) {
        g_NativeModsMenuProbeState.lastFailure = kFailureMenuManagerNull;
        return;
    }
    using SetStateFn = void (*)(void*, std::int32_t);
    // 2026-09-23 修正（，被真机读数逼出来的）：装了中继之后不能再走"逐字节守卫"那条路。
    //
    // 在 `MenuManager::SetState` 的入口装了中继（保险：引擎不许替我们那一格跳页），
    // 而中继会**改写入口那 16 字节**（换成 `ldr x16,#8; br x16; .quad 槽`）⇒ 下面那句
    // `Guarded(...)` 拿"原始 16 字节"去比**永远对不上** ⇒ 直接返回、`SetState` 根本没被调用。
    // 真机现象：用户按 13 次「模组」，`[69]` 进页面 13 次、`Reset` 也调到了（`[70]=1`），
    // 但 `[85] = 4`（状态没变）⇒ 页面一帧都没进去。
    //
    // 正确做法：装了中继就直接调中继给的**回退入口**（它内部先回放原序言、再跳回原函数第 5 条指令，
    // 与另外两个 Render 中继的用法完全一样）；没装中继才走"守卫 + 直接调"的老路。
    if (__atomic_load_n(&g_SetStateRelayOriginal,__ATOMIC_ACQUIRE) != 0) {
        ++g_NativeModsMenuProbeState.applyStateCalls;
        isaac::runtime::engine_call::AsFunction<SetStateFn>(__atomic_load_n(&g_SetStateRelayOriginal,__ATOMIC_ACQUIRE))(reinterpret_cast<void*>(manager),
                                                             static_cast<std::int32_t>(state));
        g_NativeModsMenuProbeState.lastFailure = kFailureNone;
        return;
    }
    std::uintptr_t setState = 0;
    if (!Guarded(module, kSetStateOffset, kSetStateExpected, &setState)) {
        ++g_NativeModsMenuProbeState.applyStateGuardFailures;
        g_NativeModsMenuProbeState.lastFailure = kFailureSetStateGuard;
        return;
    }
    ++g_NativeModsMenuProbeState.applyStateCalls;
    reinterpret_cast<SetStateFn>(setState)(reinterpret_cast<void*>(manager),
                                           static_cast<std::int32_t>(state));
    g_NativeModsMenuProbeState.lastFailure = kFailureNone;
}

// 手动模式开起来时的一次性 `ctor` + `Init`。放在 update 中继里做，不放 Present 前中继：
// `Init` 会加载 ANM2、还会调一次 `MenuManager::SetChallengeOffset`，不该插在渲染中途。
void TryInitManualPage(const TargetModule& module) {
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kMenuManagerSlotOffset, &manager)) {
        g_NativeModsMenuProbeState.menuManagerOk = 0;
        g_NativeModsMenuProbeState.lastFailure = kFailureMenuManagerNull;
        g_NativeModsMenuProbeState.initResult = kInitMenuManagerNull;
        return;
    }
    g_NativeModsMenuProbeState.menuManagerOk = 1;
    std::uintptr_t ctor = 0;
    std::uintptr_t init = 0;
    std::uintptr_t render = 0;
    if (!Guarded(module, kMenuModsCtorOffset, kMenuModsCtorExpected, &ctor) ||
        !Guarded(module, kMenuModsInitOffset, kMenuModsInitExpected, &init) ||
        !Guarded(module, kMenuModsRenderOffset, kMenuModsRenderExpected, &render)) {
        g_NativeModsMenuProbeState.lastFailure = kFailureMenuModsGuard;
        g_NativeModsMenuProbeState.initResult = kInitGuardMismatch;
        return;
    }
    g_MenuModsRender = render;  // 渲染回调每帧要用，先缓存（那里不再重扫模块表）
    using CtorFn = void (*)(void*);
    using InitFn = void (*)(void*, const float*);
    // 条目表由 `TryPrepareModsVector` 在**调用本函数之前**写好（那时才好判"再等等"）。
    // 单例不是同一个：条目写在 `g_Manager` 上（`Render` 读的就是它），
    // 位置取 `MenuManager`（`Menu_Title` 内嵌在它里面）—— 串了就是"只有一张纸、没有名字"。
    // 位置：`Init` 这里传 `(0,0)`，真正的摆放由每帧按 `MenuManager+0x3c` 反算后写进
    // 对象 `+0x8` 完成（见 `NativeModsMenuProbeUpdate` 里那段""）。两处都写一下，
    // 是因为 `Init` 会把参数抄进 `+0x8`，先给个干净初值。
    //
    // 依据（静态 + 反解）：`Menu_Mods::Render @0x4107C4` 自己算
    //     `屏幕位置 = MenuManager[0x3c] + 对象+8 + (200,0)`
    // 而 `MenuManager[0x3c]` 朝 `get_target_offset() = ((画面宽-480)/2, (画面高-270)/2)` 收敛
    // ⇒ 页面空间 480×270 比可见屏幕大、居中裁切（实测 426×240 ⇒ 上边 15 格在屏幕外）。
    // 传 0 的话列表第一行就落在页面 y=-15 ⇒ 被切。见 `kMenuManagerCanvasOffset` 的注释。
    g_ManualPosition[0] = 0.0F;
    g_ManualPosition[1] = 0.0F;
    reinterpret_cast<CtorFn>(ctor)(g_ManualObject);
    reinterpret_cast<InitFn>(init)(g_ManualObject, g_ManualPosition);
    // `Init` 的最后一步就是把 `*(g_Manager+0x36800)` 存进 `对象+0x170`（静态已确认）。
    // 读回来非空 ⇒ **我们这次调用真的进了函数体并跑到底**，而不是"跳进去什么都没发生"。
    std::uintptr_t mods = 0;
    std::memcpy(&mods, g_ManualObject + 0x170, sizeof(mods));
    g_NativeModsMenuProbeState.manualModsPtrOk = mods != 0 ? 1U : 0U;
    g_NativeModsMenuProbeState.initResult = kInitOk;
    g_NativeModsMenuProbeState.lastFailure = kFailureNone;
}

}  // namespace

// 在"选择界面"那一列里插入"模组"那一行
//
// 目标：`Menu_Game`（状态机第 3 格）那一屏的条目列里，在 **CHALLENGES 与 STATS 之间**多一格"模组"，
// 并且那一格**能被光标选中**。算术全在 `mod_menu_entry_row.hpp`（有宿主门禁），这里只负责接线。
//
// 三条引擎事实（都反汇编核过，见 `docs/设计-模组页-20260922.md` 补充节）：
//   ① `Menu_Game::Render`（`0x40E73C`）对每行做 `GetLayer(i); s0=[layer+0x48]; s0+=k; [layer+0x48]=s0`
//      ⇒ **`图层+0x48` 是每行自己的 Y 偏移，我们也能写**（这就是"把下面几行挪下去"的抓手）；
//   ② 光标帧由 `Menu_Game::Update` 设，**Render 自己不碰**；而我们的中继在 Render 入口
//      ⇒ **我们这一帧设的帧号，在本帧的绘制里一定生效**；
//   ③ 引擎只认 5 项（`cmp w8,#4`）。**我们绝不让索引越界**：索引夹在 0..4，
//      第 6 格（我们的最后一格）的光标靠"我们自己设帧号"实现 —— 所以不存在"越界查表"的风险。
//
// 我们**不隐藏任何一行**、也不改游戏一个字节的代码：只是把插点以下的两行临时下挪一格绘制出来。
constexpr std::uintptr_t kMenuGameRenderOffset = 0x40E73C;
constexpr std::array<std::uint8_t, 16> kMenuGameRenderExpected = {
    0xFF, 0x43, 0x05, 0xD1, 0xE8, 0x7B, 0x00, 0xFD,
    0xFC, 0x87, 0x00, 0xF9, 0xFD, 0xFB, 0x0F, 0xA9,
};
// `ANM2::GetLayer(int)` / `ANM2::SetLayerFrame(int,int)` 的跳板（引擎自己也是调这两个地址）。
constexpr std::uintptr_t kAnm2GetLayerStubOffset = 0x66FCB0;
constexpr std::array<std::uint8_t, 16> kAnm2GetLayerStubExpected = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0xE2, 0x46, 0xF9,
    0x10, 0x02, 0x37, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
constexpr std::uintptr_t kAnm2SetLayerFrameStubOffset = 0x670C20;
constexpr std::array<std::uint8_t, 16> kAnm2SetLayerFrameStubExpected = {
    0x70, 0x21, 0x00, 0xD0, 0x11, 0xBE, 0x42, 0xF9,
    0x10, 0xE2, 0x15, 0x91, 0x20, 0x02, 0x1F, 0xD6,
};
// 页面对象里的 ANM2（`Menu_Game::Render` 里 `add x21, x19, #0x10` 之后交给 `ANM2::Render`）。
constexpr std::uintptr_t kPageAnm2Offset = 0x10;
// ANM2 对象里的图层数（`int`）。证据：`ANM2::GetLayer(int)`（`0xA034`）与 `ANM2::Load`
// （`0xC970`）都读它当上界 —— `ldr w8,[x20,#0xb0]; cmp w8,w19; b.gt` 之后按
// `[x20,#0xa8] + index*0xB0` 取图层。所以"引擎怎么看有几层"的直接读数就是它，
// 不是我们的推断。⚠️ `GetLayer` 越界时不返回空指针（它只打一条日志、照样算出界地址），
// 所以判"有没有那一层"必须读这个计数，绝不能用 `GetLayer(12)` 是不是空来判。
constexpr std::uintptr_t kAnm2LayerCountOffset = 0xB0;
// 引擎自己那份菜单动画在"补回 `Item6`"之后的图层数（原版 12 层 + 我们补回去的那一层）。
// 补层工具与门禁见 `tools/gamemenu_mod_row.py --emit-menu-anm2`。
constexpr std::uint32_t kMenuGameLayerCountWithModRow = 13;

// （2026-09-22 晚）：那一行改成贴图要用的引擎入口
//
// 五条事实（都能从 `Repentance.nro` 逐字节复核；`tools/nro_symbols.py` 能按符号名查地址）：
//
//   ① `KAGE::Graphics::ImageManager` 单例：引擎自己取它就是
//      `adrp x0,0xaac000; ldr x0,[x0,#0x758]`（`Manager::load_fonts` 附近 `0x3F5238`）——
//      **只取一次**，读到的值**就是** `this` ⇒ 槽里放的就是对象地址；
//   ② 顶点格式描述符在槽 `0xaac6f8`（同一条指令流的下一条：`0x3F523C`）；
//   ③ `ImageManager::LoadImage(unsigned char const*, unsigned int, char const*, char const*,
//      VertexAttributeDescriptor*)` @`0x4d2654`（五个参数、`x8` 返回 16 字节 `SmartPointer`）。
//      **它不碰文件系统**：整条路径上的调用只有 `Util::Path::CreateCleanPath`、`strcmp`
//      （拿扩展名在三选一：`png`/`pcx`/`pic`）、`Util::HashDJB2`（缓存键）与互斥锁
//      ⇒ 把**内存里的贴图字节**交给它就行，不需要卡上有那个文件；
//   ④ `ImageBase::Render(DestinationQuad const&, Color const&)` @`0x4d0af8`（跳板，见上）；
//   ⑤ `DestinationQuad` 是 **32 字节**（四个 `Vector2` 角）。构造函数
//      `DestinationQuad(float const&,float const&,float const&,float const&)` @`0x4efb78`
//      反汇编读出来是：`(a,b)`→`+0`、`(c,b)`→`+8`、`(a,d)`→`+0x10`、`(c,d)`→`+0x18`
//      ⇒ 四个参数是 **left, top, right, bottom**，四个角按"左上、右上、左下、右下"摆。
constexpr std::uintptr_t kImageManagerSlotOffset = 0xAAC758;
constexpr std::uintptr_t kImageManagerDescriptorSlotOffset = 0xAAC6F8;
constexpr std::uintptr_t kImageManagerRenderQuadOffset = 0x4D0AF8;
// 守卫 = `ldr x8,[x0]; mov x3,x2; mov x4,x2; ldr x6,[x8,#0x150]; mov x5,x2; br x6`。
// ⚠️ 2026-09-22 晚修正：我第一版把第 4 条抄成了 `F9400D06`（真值是 `F9401506`，`0x0D`→`0x15`），
// 于是守卫不过 ⇒ 贴图一步都没走、退回用字画 ⇒ 真机上用户看到的是"英文的、正的、很大的 MODS"。
// 守卫本身是对的（它拦下了"拿去调一个没核过的地址"），错的是我抄的那 16 个字节。
constexpr std::array<std::uint8_t, 16> kImageManagerRenderQuadExpected = {
    0x08, 0x00, 0x40, 0xF9, 0xE3, 0x03, 0x02, 0xAA,
    0xE4, 0x03, 0x02, 0xAA, 0x06, 0x15, 0x40, 0xF9,
};
// 交给引擎的合成路径：一不用来开文件，只用来给引擎挑解码器（按扩展名）+ 当缓存键。
// 所以扩展名必须是 `.pcx`（我们的字节就是 PCX）。
constexpr char kModRowSpritePath[] = "mod_row_sprite.pcx";

// 2026-09-22 晚（第四轮）：这个函数的两个路径参数到底该写什么，第一版猜错了。
//
// 真机读数：`贴图 = 引擎返回了空指针` —— 说明守卫都过了、调用也发生了，但引擎交回一个空
// `SmartPointer`。把内存版反汇编读到底（`0x4d2654`）：
//
//     x3 → `Path::CreateCleanPath(...)`（0x4d26f0）→ 拿它的**返回值**去 strcmp 四个字面量
//          "png" / "pcx" / "pic" / "rgba"（0x4d2700..0x4d2740）
//          四个都不匹配 ⇒ 跳到 0x4d2848 ⇒ 收尾时 `stp xzr,xzr,[x19]` **把返回槽清零**
//     x4 → 存起来，稍后作为对象 `Load(data,size,path)` 的 path 传进去（0x4d286c）
//
// ⇒ **x3 要的是"扩展名"本身**（就是与 "pcx" 比的那一项），不是文件名；x4 才是那个名字。
//   第一版把两处都写成 `"mod_row_sprite.pcx"` ⇒ 拿整个文件名去比 "pcx" ⇒ 永远不匹配 ⇒ 空指针。
//
// 为了不再靠猜，这一版**一次试四种形态**并把结果记进诊断字（[65] 位图 / [66] 用了哪一种）。
constexpr char kModRowSpriteExtension[] = "pcx";
constexpr char kModRowSpriteName[] = "mod_row_sprite.pcx";

// 那一行改成引擎自己的「按路径加载」（`ANM2::Load`）
//
// ## 为什么（用户已批准的修法 1+2）
//
// 真机现象：跑过若干次对局/关卡加载之后，那一行**变透明** —— 绘制每帧照调（2590 帧）、
// 位置也对、对象非空，就是画不出来；用同一条**内存**路线重新加载，拿回来的仍然是一张
// 画不出来的图，重启才好。
//
// 根因：我们是全工程**唯一**"从内存加载贴图、并且用自造名字当缓存键"（`modrowg0.pcx` 这种）
// 的地方；引擎自己的行、以及所有模组（EID 等）都是**按磁盘路径**加载（`ANM2::Load`），
// 它们从不消失。关卡加载会清掉"没有磁盘文件背书的贴图"，我们那张就是被清掉的那一类。
//
// ⇒ 构建期把图落成真实文件（`tools/emit_mod_row_art.py`，`--tree` 直接写进部署包），
//   运行期走 `ANM2::Load(path, true)`（正是 `Sprite:Load` 与所有模组那条路）+ `ANM2::Render`。
//   内存那条路线**保留作兜底**，行为一字不改（见 `ModRowPrepareImage` / `ModRowDrawSprite`）。
//
// ## 逻辑路径与四条候选（顺序 = 优先级）
//
// 部署期落点（`tools/emit_mod_row_art.py --tree`）：
//   <romfs>/rp_patch/resources.<语言>/gfx/ui/main menu/isaac-switch/mod_row_<语言>.{anm2,pcx}
//   （英文用裸 `resources`；`--also-english-root` 会把同一批再往英文根复制一份）
//
// 但"引擎挂载根到底是**当前语言目录**还是**英文 `resources`**"**没有定论** ⇒ 真机上依次试
// 四条候选，哪条成记哪条（诊断字 [101]/[102]）。四条就是"四种根假设 × 两种写法"：
//   1. `gfx/ui/main menu/isaac-switch/mod_row_<语言>.anm2`        —— 根 = `rp_patch/resources.<语言>/`
//   2. 同上这条路径（**同一逻辑路径**）                            —— 根 = `rp_patch/resources/`（英文根）
//      为什么 #1 与 #2 字面完全相同：这两条**不是两条不同的路径**，而是两种**根假设**；
//      `--also-english-root` 把同一个文件在英文根下也放了一份 ⇒ 同一个逻辑路径在两种根下都能解析。
//      （同一条字符串再试一次没有额外信息，命中即停 ⇒ 实际只会读到一次成功。）
//   3. `rp_patch/resources.<语言>/gfx/ui/main menu/isaac-switch/mod_row_<语言>.anm2` —— 根 = romfs 根
//   4. `rp_patch/resources/gfx/ui/main menu/isaac-switch/mod_row_<语言>.anm2`       —— 同上但走英文目录
//
// ## 为什么"命中即停"
//
// 每次 `Load(path, true)` 都会解析 XML **并解码贴图**；既然 #1/#2 是同一串、且后两条只在
// 前两条失败时才有意义，那么继续试下去只会把同一件事做第二遍。停下来的代价是掩码里最多一位，
// 而那一位恰好就是"哪种根假设成立"—— 这正是要测的东西。
// 我们那些资源文件所在的目录（部署在 `romfs/rp_patch/resources[.<语言>]/gfx/ui/main menu/
// isaac-switch/` 下）。逻辑路径就是这一串：上一批已经证明引擎的挂载解析看得见这个目录
// —— `.anm2` 就是被它找到的（否则不会走到渲染，也就不会崩），没找到的只是 `.png`。
constexpr char kModRowFileDirectory[] = "gfx/ui/main menu/isaac-switch/";
constexpr char kModRowFilePrefix[] = "mod_row_";
constexpr char kModRowFileSuffix[] = ".pcx";
// 游戏 romfs 里那一层的目录名（引擎自己的资源就在 `rp_patch/` 下）。
constexpr char kModRowFileMountRoot[] = "rp_patch/";
// 路径缓冲（最长那条约 75 字符）。比引擎那边的容量宽裕，装不下就不截断、直接算失败。
constexpr std::size_t kModRowFilePathCapacity = 160;
// 候选路径条数（诊断字 [102] 的掩码就是按"路径数 × 2"算的）。
constexpr std::uint32_t kModRowFilePathCount = 4;
// 每条路径试两种 `flag`（那个 bool 的语义引擎没公开）⇒ 候选总数 = 路径数 × 2。
constexpr std::uint32_t kModRowFileCandidateCount = kModRowFilePathCount * 2;

// `Menu_Game` 页面对象在 `MenuManager` 里的偏移（状态表：state 3 = Menu_Game(+0x813A0)）。
constexpr std::uintptr_t kMenuGamePageOffsetInMenuManager = 0x813A0;
// 页面对象里的"当前选中项"（`Menu_Game::Update` 里 `str w8, [x19, #0x4]`）。
constexpr std::uintptr_t kPageSelectedIndexOffset = 0x4;
// 页面对象里自己的位置（`Menu_Game::Render` 里 `add x1, x0, #0x8` 之后与偏移相加）。
constexpr std::uintptr_t kPagePositionOffset = 0x8;
// 字体对象在 `g_Manager` 里的偏移（`Menu_Mods::Render` 画行用的就是它：`add x25, x8, #0x117120`）。
constexpr std::uintptr_t kManagerFontOffset = 0x117120;
// 上下键的动作号（`Menu_Game::Update` 里 `IsActionPressed(0x13 / 0x14, -1, 0)`）。
constexpr std::uint32_t kModRowActionUp = 0x13;
constexpr std::uint32_t kModRowActionDown = 0x14;
// 确认（`ACTION_MENUCONFIRM = 14`）。
//
// 2026-09-22 深夜修正：这里原来是 `0x0F`，那是错的 ——
// `0x0F` 在引擎的动作表里是 `ACTION_MENUBACK`（返回），不是确认。两条可复核的依据：
// ① `Menu_Title::Update @0x41A4F0`：`mov w1,#0xe` + `IsActionTriggered` ⇒ `SetState(2)`
// （标题上按确认进存档选择）；
// ② `Menu_Game::Update @0x40D5E0` 的"那一行确认"分支在 `0x40D730` 也是 `mov w1,#0xe`，
// 而 `0x40d890` 那处是 `mov w1,#0xf`（返回）；`Menu_Mods::Update` 同样
// "0xE = 切换开关、0xF = 返回（`SetState(3)`）"。
// 之所以一直没暴露：046 那批只记数、没接页面，而这一格从来没人按过（读数里恒 0）。
// ⇒ 本批把两个动作号分开记（诊断字 [75]/[76]），一按就知道哪个是哪个。
constexpr std::uint32_t kModRowActionConfirm = 0x0E;
// 返回（`ACTION_MENUBACK = 15`）。模组页里用它退出 —— 引擎自己那一页也是这么做的
// （`Menu_Mods::Update` 的反汇编：`IsActionTriggered(0xf)` ⇒ `SetState(3)`）。
constexpr std::uint32_t kModRowActionBack = 0x0F;
// 我们那一行的字。
//
// 2026-09-22 傍晚修正：必须用 ASCII。上一版是中文「模组」，真机一片空白 ——
// 根因是游戏自带字体没有中文字形（详见 `ModRowDrawLabel` 的注释与
// `docs/问题与解决记录.md` 续三十九）。周围五行烤在图里的字本来就是英文，
// 所以这一行也用英文：MODS。
constexpr char kModRowLabel[] = "MODS";
// 中文那一行（2026-09-22 傍晚第二版）：自己加载一份带中文字形的字体。
//
// 为什么必须自己加载：引擎的"中文字体"是按语言分支挑的
// （`Manager::load_language_fonts @0x3F4B10`：语言 2/0xb/0xd 才把
// `font/CJK/LanaPixel.fnt` 装进字体槽），而这台机器的游戏语言不是那几档
// ⇒ 我们手上那份"中等字体"（`Manager+0x117120`）就是纯 ASCII 的 `TeamMeatFont12`
// （解析 `.fnt` 得到：119 个字形、字号 16）⇒ 画中文只能是空白（真机已证实：红的「模组」看不见）。
//
// 用哪一份：`font/CJK/LanaPixel.fnt`。它放在 `rp_patch/resources/font/cjk/`（基础资源，
// 不带语言后缀 ⇒ 任何语言下都挂载得到），解析出来是字号 11 / 行高 13 / 19436 个字形（含中文）。
// 路径写成"内容挂载点相对名"（引擎自己的调用点就是这么写的，如 `font/terminus.fnt`）。
//
// 2026-09-22 傍晚第三版：换成 `font/TeamMeatFontExtended12.fnt`。
// 为什么不用 LanaPixel（上一版就是它，真机上被画成一个深色小方块）：
// 把两张图集都解出来逐像素看 ——
// * `rp_patch/resources/font/cjk/lanapixel_0.pcx`：笔画是白的，但背景是不透明黑
// （背景像素 `(0,0,0,255)`/`(0,0,0,77)`）⇒ 引擎按"颜色 × 贴图"画，整个字格就变成一块黑底，
// 笔画只是比黑稍亮 ⇒ 真机现象正是"深色小方块 + 浅色笔画"。
// * `rp_patch/resources.zh/font/teammeatfontextended12_0.pcx`：背景 `(0,0,0,0)` 透明、
// 笔画 `(255,255,255,255)` 白带 alpha —— 与引擎自己的 `teammeatfont12_0.pcx` 同格式 ✓，
// 而且这一族（TeamMeat）就是游戏菜单自己在用的字型，21368 个字形含中文。
// ⇒ 用它。顺带：LanaPixel 不再作为兜底（它只会画出黑方块，比"没有中文"更糟）——
// 装不上就退回引擎中等字体 + ASCII `MODS`。
constexpr char kCjkFontPath[] = "font/TeamMeatFontExtended12.fnt";
// 中文字体对象：`Font` 的对象尺寸由 `runtime_constants.hpp` 给出（0x20050，项目 Lua 侧
// `Font:Load` 用的就是同一个数），这里在 bss 里静态开一块、16 字节对齐。
alignas(16) std::uint8_t g_CjkFontStorage[kFontObjectSize]{};
constexpr char kModRowLabelCjk[] = "\xE6\xA8\xA1\xE7\xBB\x84";  // 模组
// 文本位置：x 对齐引擎自己那几行的文字左边（行图框 x≈185，烤的字在框内 +7 左右）。
constexpr float kModRowTextX = 192.0F;
// 相对"我们那一格的锚点"的偏移（锚点现在由生成器给：贴图顶 + 贴图内字顶）。
constexpr float kModRowTextYOffset = 0.0F;
// 万一布局还没定（语言没取到）时兜底用——就是 048 批真机验过的那个文字锚点。
constexpr float kModEntryTextYFallback = 124.0F;
// 字号：对着纸上那套窄体量出来的。把 `gamemenu.pcx` 解出来量墨迹：CHALLENGES 那格
// 46 宽 × 28 高、NEW RUN 61×29、STATS 74×34 ⇒ 纸上的字高约 28。
// 引擎字体 scale 1.0 时实测约 16 高（真机：y=134 画的字压到了 STATS 的内容顶 150）
// ⇒ 取 1.6（≈26），既接近纸上的字号，又能塞进我们那一行的 ~26 格。
// 字号不再手调：改成"对齐美术里那行字有多高"。
//
// 依据（把 `rp_patch/resources.zh/gfx/ui/main menu/gamemenu.pcx` 解出来逐行量"笔画"的包围盒）：
// 新游戏 29、继续游戏 34、挑战 28、统计数据 34、选项 25 ⇒ 那一列的中文字高约 28 格。
// 运行时用引擎自己的 `Font::GetLineHeight()` 取当前字体的行高，
// `缩放 = 28 / 行高`（LanaPixel 行高 13 ⇒ 2.15；引擎那份 TeamMeatFont12 行高 19 ⇒ 1.47）。
// ⇒ 换字体不用重调，这也是"别再一个个试"的落地方式。
constexpr float kModRowArtTextHeight = 28.0F;
// 万一行高拿不到（守卫不过）时的兜底缩放。
constexpr float kModRowTextScaleFallback = 2.0F;
// 对照那一次中文画在哪（纸的左上角空白处，不挡任何东西）。
constexpr float kModRowCjkX = 40.0F;
constexpr float kModRowCjkY = 45.0F;

struct ModRowContext {
    using GetLayerFn = void* (*)(void*, int);
    using SetLayerFrameFn = void (*)(void*, int, int);
    using DrawTextFn = void (*)(void*, const char*, float, float, float, float, const void*,
                                int, bool);
    using FontLoadFn = bool (*)(void*, const char*, const char*);
    using FontIsLoadedFn = bool (*)(const void*);
    using FontLineHeightFn = float (*)(const void*);
    // 五参内存版 `ImageManager::LoadImage`：只调用、不挂钩。
    // 签名与引擎一致（`SmartPointer<ImageBase>` 按 x8 返回 ⇒ 用仓库里的 `SmartPointerShim`）。
    using LoadImageMemoryFn = isaac::runtime::relay::SmartPointerShim (*)(
        void*, const std::uint8_t*, std::uint32_t, const char*, const char*, void*);
    // `ImageBase::Render(DestinationQuad const&, Color const&)` —— 是个跳板
    // （`ldr x8,[x0]; ldr x6,[x8,#0x150]; br x6`），所以只要 this + 两个指针。
    using RenderQuadFn = void (*)(void*, const void*, const void*);
    // ↓ 这五个是页面上原有的引擎入口与贴图那条路要用的（072 之前就在，误删过一次）。
    GetLayerFn getLayer{nullptr};
    SetLayerFrameFn setLayerFrame{nullptr};
    DrawTextFn drawText{nullptr};
    LoadImageMemoryFn loadImage{nullptr};
    RenderQuadFn renderQuad{nullptr};
    // ---- 引擎自己的"按文件名加载贴图"这条路（首选；内存那条退居兜底）----
    //
    // `ImageManager::LoadImage(char const* path, VertexAttributeDescriptor*, bool)`。
    // 权威签名照仓库里已有的中继回调（`entry_relay_hook_adapter.cpp` 的
    // `EntryRelayImageManagerLoadFileCallback(void* self, const char* path, void* descriptor,
    // int flag)`）—— 返回值形状与内存版一致（`SmartPointer<ImageBase>` 走 x8 ⇒ 用垫片）。
    // `flag` 的语义没有公开 ⇒ 两种取值都试，命中的那个记进诊断字 [107]。
    using LoadImageFileFn = isaac::runtime::relay::SmartPointerShim (*)(
        void*, const char*, void*, int);
    LoadImageFileFn loadImageFile{nullptr};
    // 磁盘来的那张贴图（引擎的 `SmartPointer`，16 字节）。空 = 不画（这条路线不崩）。
    isaac::runtime::relay::SmartPointerShim fileImage{};
    // 命中那条逻辑路径（关卡切换后按它从磁盘重读 —— 这正是它与内存路线的本质区别）。
    char filePath[kModRowFilePathCapacity] = {0};
    std::uint32_t fileFlag{0};
    // 新路线的状态（含义见诊断字 [100] 的注释）。
    std::uint32_t fileState{0};
    std::uint32_t fileCandidate{0};
    std::uint32_t fileHits{0};
    std::uint32_t fileGuardState{0};
    void* imageManager{nullptr};   // `*(游戏模块 + 0xAAC758)`（引擎自己就是这么取的）
    void* descriptor{nullptr};     // `*(游戏模块 + 0xAAC6F8)`（顶点格式描述符）
    // 我们那一行的贴图（引擎的 `SmartPointer`，16 字节；只加载一次、本进程一直持有）。
    isaac::runtime::relay::SmartPointerShim image{};
    // 挑中的那一套布局（按游戏语言码，见 `mod_row_generated.hpp`）。
    const isaac::runtime::ModRowLayout* layout{nullptr};
    // 语言码（两字符 + 结尾 0；用 `char` 数组是为了能直接与生成的表比）。
    char language[4] = {0, 0, 0, 0};
    std::uint32_t imageState{0};
    std::uint32_t imageAttempt{0};  // 第几种"路径形态"成功了（0 = 都没成）
    std::uint32_t languageState{0};
    // 带中文字形的那份字体（自己加载的）。`nullptr` = 没装上 ⇒ 退回引擎的中等字体 + ASCII。
    void* cjkFont{nullptr};
    ///: 取"当前字体画一行有多高"（用来把字号对齐美术，而不是手调）
    FontLineHeightFn lineHeight{nullptr};
    // 加载结果：0 没试 / 1 装上 / 2 入口守卫不过 / 3 引擎拒绝
    std::uint32_t cjkFontState{0};
    std::uintptr_t manager{0};  // `g_Manager`（字体对象嵌在它里面）
    std::uintptr_t menuManager{0};
    std::uint64_t renderOriginal{0};
};
ModRowContext g_ModRow{};
// 当前选中第几格（0..5，3 = 我们那一格）。进入那一屏时按引擎的索引初始化。
std::uint32_t g_ModRowSlot = 0;
std::uint32_t g_ModRowSlotInit = 0;
std::uint32_t g_ModRowLastUp = 0;
std::uint32_t g_ModRowLastDown = 0;
std::uint32_t g_ModRowLastConfirm = 0;
std::uint32_t g_ModRowConfirmOnOurs = 0;
// 从模组页回来时，光标要回到我们那一格（而不是按引擎索引换算出来的邻格）。
//
// 为什么需要它：我们那一格（slot 3）写回给引擎的索引是 3（`EngineIndexClampedForSlot`），
// 而"引擎索引 → 我们的格子"的换算是"≥ 我们的落点就 +1"（因为插进去的那一格占了原来的第 4 格）
// ⇒ 引擎索引 3 会被换成第 5 格（统计数据），光标就跑到隔壁去了。
// 往返一次本来是我们自己的页面，光标留在原地才是用户预期。
std::uint32_t g_ModRowRestoreOurs = 0;

// 引擎自己的「按路径加载 ANM2」这条路
//
// 设计与理由见 `kModRowAnm2Directory` 上方那一段。这里按"能被谁调用"分两组：
//   * 这一组（准备 / 重载 / 发诊断）**必须在这里** —— `ModRowInvalidateImageOnGameTransition`
//     与 `ModRowUpdate` 都在文件后半段，它们要用；
//   * 绘制那一组放在 `ModRowPageOrigin` 之后（它要实时算页面原点）。

// `ANM2::Render` 那条路要的动画名（就是我们生成的 `.anm2` 里唯一那个动画）。
constexpr char kModRowAnm2Animation[] = "Idle";

// 把新路线那几格诊断字发出去（只在状态变化时调，不在渲染回调里）。
void ModRowPublishFileImage() {
    g_NativeModsMenuProbeState.modRowFileState = g_ModRow.fileState;
    g_NativeModsMenuProbeState.modRowFileCandidate = g_ModRow.fileCandidate;
    g_NativeModsMenuProbeState.modRowFileHits = g_ModRow.fileHits;
    g_NativeModsMenuProbeState.modRowFileGuardState = g_ModRow.fileGuardState;
    g_NativeModsMenuProbeState.modRowFileFlag = g_ModRow.fileFlag;
    g_NativeModsMenuProbeState.modRowFilePathLength =
        static_cast<std::uint32_t>(std::strlen(g_ModRow.filePath));
}

// 往缓冲里追加一段。装不下就返回 false、绝不截断 —— 截断出来的路径"看起来像"却永远
// 解析不到，那种静默失败比当场报错难查得多（本项目在别的路径上吃过这个亏）。
bool ModRowAppendText(char* buffer, std::size_t capacity, std::size_t* used, const char* text) {
    if (buffer == nullptr || used == nullptr || text == nullptr) {
        return false;
    }
    const std::size_t length = std::strlen(text);
    if (*used + length + 1 > capacity) {
        return false;
    }
    std::memcpy(buffer + *used, text, length);
    *used += length;
    buffer[*used] = '\0';
    return true;
}

// 拼出候选逻辑路径（顺序 = 优先级）。`paths` 是 `[路径数][容量]` 的二维缓冲；
// 失败返回 false（不写出半截路径 —— 截断出来的路径"看起来像"却永远解析不到，
// 那种静默失败比当场报错难查得多，本项目在别的路径上吃过这个亏）。
bool ModRowBuildFileImagePaths(char paths[kModRowFilePathCount][kModRowFilePathCapacity]) {
    // 文件名的语言码：`g_ModRow.language` 是两字符 + 结尾 0（`ModRowResolveLanguage` 填的）。
    if (g_ModRow.language[0] == '\0') {
        return false;
    }
    // 语言资源目录名：英文是**裸 `resources`**，其余是 `resources.<码>`
    // （部署工具 `tools/emit_mod_row_art.py` 用的是同一套规则，两边必须一致）。
    char language_directory[16] = {0};
    std::size_t directory_used = 0;
    if (g_ModRow.language[0] == 'e' && g_ModRow.language[1] == 'n') {
        if (!ModRowAppendText(language_directory, sizeof(language_directory), &directory_used,
                              "resources")) {
            return false;
        }
    } else if (!ModRowAppendText(language_directory, sizeof(language_directory), &directory_used,
                                 "resources.")
               || !ModRowAppendText(language_directory, sizeof(language_directory), &directory_used,
                                    g_ModRow.language)) {
        return false;
    }
    // 尾部（四条路径共用）：`gfx/ui/main menu/isaac-switch/mod_row_<语言>.pcx`
    char tail[kModRowFilePathCapacity] = {0};
    std::size_t tail_used = 0;
    if (!ModRowAppendText(tail, sizeof(tail), &tail_used, kModRowFileDirectory)
        || !ModRowAppendText(tail, sizeof(tail), &tail_used, kModRowFilePrefix)
        || !ModRowAppendText(tail, sizeof(tail), &tail_used, g_ModRow.language)
        || !ModRowAppendText(tail, sizeof(tail), &tail_used, kModRowFileSuffix)) {
        return false;
    }
    // ① 引擎的常规**逻辑路径**（挂载解析看得见我们那个目录，见 `kModRowFileDirectory` 注释）。
    std::size_t used = 0;
    if (!ModRowAppendText(paths[0], kModRowFilePathCapacity, &used, tail)) {
        return false;
    }
    // ② 带 `rom:/` 前缀、指向**当前语言目录**的绝对路径。
    used = 0;
    if (!ModRowAppendText(paths[1], kModRowFilePathCapacity, &used, "rom:/")
        || !ModRowAppendText(paths[1], kModRowFilePathCapacity, &used, kModRowFileMountRoot)
        || !ModRowAppendText(paths[1], kModRowFilePathCapacity, &used, language_directory)
        || !ModRowAppendText(paths[1], kModRowFilePathCapacity, &used, "/")
        || !ModRowAppendText(paths[1], kModRowFilePathCapacity, &used, tail)) {
        return false;
    }
    // ③ 不带 `rom:/` 的挂载根相对路径（`rp_patch/resources.<语言>/...`）。
    used = 0;
    if (!ModRowAppendText(paths[2], kModRowFilePathCapacity, &used, kModRowFileMountRoot)
        || !ModRowAppendText(paths[2], kModRowFilePathCapacity, &used, language_directory)
        || !ModRowAppendText(paths[2], kModRowFilePathCapacity, &used, "/")
        || !ModRowAppendText(paths[2], kModRowFilePathCapacity, &used, tail)) {
        return false;
    }
    // ④ 同 ③，但走英文目录（覆盖层里那份副本）。
    used = 0;
    if (!ModRowAppendText(paths[3], kModRowFilePathCapacity, &used, kModRowFileMountRoot)
        || !ModRowAppendText(paths[3], kModRowFilePathCapacity, &used, "resources/")
        || !ModRowAppendText(paths[3], kModRowFilePathCapacity, &used, tail)) {
        return false;
    }
    return true;
}

// 装那条新路线：用引擎的按文件名版 `LoadImage` 把磁盘上的 `mod_row_<语言>.pcx` 载进来。
//
// 一次性：成功之后不再进；失败也不每帧重试（不刷日志、不折腾引擎）——但"语言还没定"
// 不算失败：主菜单可能比 `Manager::GetLanguageCode()` 那条链先出现，语言定下来要能继续走。
//
// 为什么"界面为空就不画"这条纪律这么重要：上一批（071）正是拿一张空的精灵表去画
// 才真机崩溃的。这里拿到的是"引擎自己给的贴图指针"，非空才用，空就落到内存兜底/画字。
bool ModRowPrepareFileImage(const TargetModule& module) {
    if (g_ModRow.fileState == kFileRouteReady) {
        return true;
    }
    if (g_ModRow.fileState != 0 && g_ModRow.fileState != kFileRouteLanguagePending) {
        return false;
    }
    if (g_ModRow.layout == nullptr || g_ModRow.languageState == 0) {
        g_ModRow.fileState = kFileRouteLanguagePending;  // 语言还没定 ⇒ 下一帧再说
        ModRowPublishFileImage();
        return false;
    }
    // 管理器指针与顶点描述符由内存那条路先取（调用点里 `ModRowPrepareImage` 排在前面）。
    if (g_ModRow.imageManager == nullptr || g_ModRow.descriptor == nullptr) {
        g_ModRow.fileState = kFileRouteContextMissing;
        ModRowPublishFileImage();
        return false;
    }
    if (g_ModRow.loadImageFile == nullptr) {
        // 贴图桥已挂这个入口：原版 16 字节被中继替换，必须使用安装时保存的原函数。
        auto loadImageFile = isaac::runtime::Original<ModRowContext::LoadImageFileFn>(
            isaac::runtime::HookId::ImageManagerLoadFile);
        if (loadImageFile != nullptr) {
            g_ModRow.loadImageFile = loadImageFile;
        } else {
            // 没装中继时入口未改写，才允许逐字节守卫后直接调用。
            std::uintptr_t address = 0;
            if (!Guarded(module, kImageManagerLoadFileOffset, kImageManagerLoadFileExpectedBytes,
                         &address)) {
                g_ModRow.fileState = kFileRouteGuardFailed;
                g_ModRow.fileGuardState = 2;
                ModRowPublishFileImage();
                return false;
            }
            g_ModRow.loadImageFile = reinterpret_cast<ModRowContext::LoadImageFileFn>(address);
        }
        g_ModRow.fileGuardState = 1;
    }
    char paths[kModRowFilePathCount][kModRowFilePathCapacity] = {};
    if (!ModRowBuildFileImagePaths(paths)) {
        g_ModRow.fileState = kFileRouteLanguagePending;  // 语言/路径还没就绪 ⇒ 下一帧再试
        ModRowPublishFileImage();
        return false;
    }
    std::uint32_t mask = 0;
    for (std::uint32_t path = 0; path < kModRowFilePathCount; ++path) {
        for (std::uint32_t flag = 0; flag < 2; ++flag) {
            ++g_NativeModsMenuProbeState.modRowFileLoadCalls;
            const isaac::runtime::relay::SmartPointerShim result =
                g_ModRow.loadImageFile(g_ModRow.imageManager, paths[path], g_ModRow.descriptor,
                                       static_cast<int>(flag));
            if (result.pointer == nullptr) {
                continue;  // 这条组合拿不到 ⇒ 试下一条
            }
            mask |= 1U << (path * 2 + flag);
            g_ModRow.fileImage = result;
            g_ModRow.fileFlag = flag;
            g_ModRow.fileCandidate = path * 2 + flag + 1;
            std::memcpy(g_ModRow.filePath, paths[path], std::strlen(paths[path]) + 1);
            break;
        }
        if (g_ModRow.fileImage.pointer != nullptr) {
            break;  // 命中即停：同一张图换条路径再载一遍没有意义
        }
    }
    g_ModRow.fileHits = mask;
    g_ModRow.fileState =
        g_ModRow.fileImage.pointer != nullptr ? kFileRouteReady : kFileRouteAllNull;
    ModRowPublishFileImage();
    return g_ModRow.fileState == kFileRouteReady;
}

// 关卡/房间切换之后从磁盘重新读一次同一个路径。
//
// 这就是这条路线与内存路线的本质区别：引擎自己管的那些贴图（它那五行、所有模组）
// 之所以从不消失，是因为它们背后有磁盘文件；关卡加载把"没有文件背书的贴图"清掉之后，
// 我们再从磁盘读一次就能拿回一张真的图（内存那条路重读拿回的还是失效对象）。
//
// 去重不在这里做 —— 调用点只在"关卡/房间事件计数变化"时调它 ⇒ 天然不会每帧重载。
void ModRowReloadFileImageFromDisk() {
    if (g_ModRow.fileState != kFileRouteReady || g_ModRow.loadImageFile == nullptr
        || g_ModRow.imageManager == nullptr || g_ModRow.descriptor == nullptr
        || g_ModRow.filePath[0] == '\0') {
        return;
    }
    ++g_NativeModsMenuProbeState.modRowFileLoadCalls;
    const isaac::runtime::relay::SmartPointerShim result =
        g_ModRow.loadImageFile(g_ModRow.imageManager, g_ModRow.filePath, g_ModRow.descriptor,
                               static_cast<int>(g_ModRow.fileFlag));
    ++g_NativeModsMenuProbeState.modRowFileReloads;
    if (result.pointer == nullptr) {
        // 重读都没拿到 ⇒ **清空**（而不是留着上一张）：留着就是"画一张引擎已经收回去的图"，
        // 正是这一整轮要根除的形态。清空之后绘制自动落到内存兜底 / 画字。
        g_ModRow.fileImage = isaac::runtime::relay::SmartPointerShim{};
        g_ModRow.fileState = kFileRouteAllNull;
    } else {
        g_ModRow.fileImage = result;
    }
    ModRowPublishFileImage();
}

// 局内进出会让引擎卸掉图片缓存里的条目 ⇒ 我们那张"标签贴图"的句柄会失效。
// 判据用 `Game*`（`runtime_constants.hpp` 的 `kGameOwnerGlobalSlotOffset`）每一次变化：
// 那意味着游戏刚进/刚出一局、关卡资源被加载过一轮 ⇒ 作废句柄，下一帧在那一屏重载一次。
// （为什么不能用"离开那一屏"当信号：进局内时 `MenuManager` 的状态停在 3 不变，
// 开关机菜单对象一直活着 ⇒ 那条路根本不会触发。）
void ModRowInvalidateImageOnGameTransition(const TargetModule& module) {
    std::uintptr_t game = 0;
    if (ReadSlot(module, kGameOwnerGlobalSlotOffset, &game)) {
        g_NativeModsMenuProbeState.gamePresent = game != 0 ? 1U : 0U;
    }
    // 2026-09-23 更正：上一版用"`Game*` 有没有值"当判据，真机一次都没触发
    // （读数 `[97] = 0`、而用户确实进过局）—— 因为**回到菜单时那个指针并不变 0**。
    // 现在改用**运行时自己的回调派发计数**：关卡/房间事件一发生它就变，
    // 而那正是"引擎加载了一批资源、把图片缓存里的东西挤掉"的时刻。
    const std::uint32_t levels = isaac::runtime::g_CallbackDispatchCounts[kCallbackPostNewLevel]
                                     .load(std::memory_order_relaxed);
    const std::uint32_t rooms = isaac::runtime::g_CallbackDispatchCounts[kCallbackPostNewRoom]
                                    .load(std::memory_order_relaxed);
    g_NativeModsMenuProbeState.levelEventCount = levels;
    if (levels == g_LevelEventCount && rooms == g_RoomEventCount) {
        return;
    }
    g_LevelEventCount = levels;
    g_RoomEventCount = rooms;
    if (g_ModRow.image.pointer != nullptr) {
        g_ModRow.image.pointer = nullptr;  // 作废 ⇒ 下一次 `ModRowPrepareImage` 会真的重载
        g_ModRow.imageState = 0;
        ++g_ModRowImageGeneration;         // 换缓存键（见 `g_ModRowImageName` 的注释）
        const std::uint32_t value = g_ModRowImageGeneration;
        char digits[12] = {};
        std::size_t used = 0;
        if (value == 0) {
            digits[used++] = '0';
        }
        char reversed[12] = {};
        std::size_t count = 0;
        for (std::uint32_t v = value; v != 0 && count < sizeof(reversed); v /= 10) {
            reversed[count++] = static_cast<char>('0' + (v % 10));
        }
        while (count > 0) {
            digits[used++] = reversed[--count];
        }
        const char prefix[] = "modrowg";
        const char suffix[] = ".pcx";
        std::size_t at = 0;
        for (; at + 1 < sizeof(g_ModRowImageName) && prefix[at] != '\0'; ++at) {
            g_ModRowImageName[at] = prefix[at];
        }
        for (std::size_t i = 0; i < used && at + 1 < sizeof(g_ModRowImageName); ++i) {
            g_ModRowImageName[at++] = digits[i];
        }
        for (std::size_t i = 0; suffix[i] != '\0' && at + 1 < sizeof(g_ModRowImageName); ++i) {
            g_ModRowImageName[at++] = suffix[i];
        }
        g_ModRowImageName[at] = '\0';
        ++g_NativeModsMenuProbeState.modRowImageReloads;
    }
    // 同一个触发点上，让 ANM2 那条路也从磁盘重读一次。
    // 与上面那一段的区别正是这一批的核心：内存版重读只拿到"另一个失效对象"（缓存键换了也一样），
    // 而按路径加载是从磁盘真的重新读一份 ⇒ 这是它不会消失的原因。
    // 只在"事件计数变化"这一刻调 ⇒ 天然去重（不会每帧重载）。
    ModRowReloadFileImageFromDisk();
}


// 模组页（引擎状态 16）那一边的输入边沿（与"我们那一格"那套分开记，
// 免得两个屏幕的边沿互相污染）。
std::uint32_t g_ModsPageLastUp = 0;
std::uint32_t g_ModsPageLastDown = 0;
std::uint32_t g_ModsPageLastConfirm = 0;
std::uint32_t g_ModsPageLastBack = 0;

// 进入模组页（定义在下面 —— `ModRowUpdate` 里"我们那一格的确认"要调它）。
// `query` 是输入查询（用来把"进页面那一刻还按着的那几个键"锁进边沿状态，见函数里的注释）。
void EnterModsPage(const TargetModule& module, const ActionQueryFn query);

// 取 ANM2 的某个图层对象；拿不到返回 nullptr（调用方必须判）。
void* ModRowLayer(std::uintptr_t anm2, std::uint32_t layer) {
    if (g_ModRow.getLayer == nullptr || anm2 == 0) {
        return nullptr;
    }
    return g_ModRow.getLayer(reinterpret_cast<void*>(anm2), static_cast<int>(layer));
}

// 给每一行的图层偏移加/减一个位移（Y 与 X 都加）。`sign` = +1 施加、-1 还原。
// 为什么要还原：引擎自己每帧也在往这个字段里加（那是它的排版手段），我们不还原就会一路漂下去。
// 每一行挪的量各不相同（见生成的 `rowShiftY` / `rowShiftX`）：插点以上三行上移、
// STATS 下移、OPTIONS 几乎不动 —— 上一批是"整体下挪 33"，把 OPTIONS 挤出了纸外。
// 2026-09-22 深夜：横向也照搬 PC（`rowShiftX`）—— 只搬 Y 的话「模组」会比上面那行挑战还靠左。
void ModRowShiftRows(std::uintptr_t anm2, float sign) {
    if (g_ModRow.layout == nullptr) {
        return;  // 语言还没定 ⇒ 一帧都不挪（比"照英文那套挪"安全）
    }
    for (std::uint32_t row = 0; row < isaac::runtime::kMenuGameEngineEntryCount; ++row) {
        void* object = ModRowLayer(anm2, isaac::runtime::kMenuGameFirstRowLayer + row);
        if (object == nullptr) {
            continue;
        }
        auto* base = reinterpret_cast<std::uint8_t*>(object);
        const float delta_x = isaac::runtime::MenuGameRowShiftXFor(*g_ModRow.layout, row) * sign;
        const float delta_y = isaac::runtime::MenuGameRowShiftFor(*g_ModRow.layout, row) * sign;
        // X 在 +0x48、Y 在 +0x4C（见 `mod_menu_entry_row.hpp` 里那条真机换来的结论）。
        auto shift = [base](std::uintptr_t field_offset, float delta) {
            if (delta == 0.0F) {
                return;
            }
            auto* field = base + field_offset;
            float value = 0.0F;
            std::memcpy(&value, field, sizeof(value));
            value += delta;
            std::memcpy(field, &value, sizeof(value));
        };
        shift(isaac::runtime::kAnm2LayerOffsetXField, delta_x);
        shift(isaac::runtime::kAnm2LayerOffsetYField, delta_y);
    }
}

// 光标：帧号 = 我们的格子号（形状），位置 = 我们自己给的一个 Y 偏移。
// 那 6 帧的 y 是按原版六格画的（帧 y ≈ 格子框顶 + 33），格子动了就不能照用 ——
// 上一批"选项那行光标停不到"正是栽在这：我们照用第 6 帧，它的 y=236 已经在纸外面。
// `sign` = +1 施加（顺带设帧）、-1 还原。
void ModRowPlaceCursor(std::uintptr_t anm2, float sign) {
    void* object = ModRowLayer(anm2, isaac::runtime::kMenuGameCursorLayer);
    if (object == nullptr) {
        return;
    }
    if (g_ModRow.layout == nullptr) {
        return;
    }
    const float delta = isaac::runtime::CursorDeltaYForSlot(*g_ModRow.layout, g_ModRowSlot) * sign;
    auto* field =
        reinterpret_cast<std::uint8_t*>(object) + isaac::runtime::kAnm2LayerOffsetYField;
    float value = 0.0F;
    std::memcpy(&value, field, sizeof(value));
    value += delta;
    std::memcpy(field, &value, sizeof(value));
    if (sign > 0.0F && g_ModRow.setLayerFrame != nullptr) {
        g_ModRow.setLayerFrame(
            reinterpret_cast<void*>(anm2), static_cast<int>(isaac::runtime::kMenuGameCursorLayer),
            static_cast<int>(isaac::runtime::CursorFrameForSlot(*g_ModRow.layout, g_ModRowSlot)));
    }
}

// 画我们那一行。
//
// 2026-09-22 傍晚（本轮）：交付文案改成 ASCII "MODS"。
// 上一版画的是中文「模组」，真机上一片空白 —— 根因是游戏自带字体没有中文字形：
// `Manager::ReloadMediumFont @0x3F48F0` 只按语言在
// `TeamMeatFont12` / `TeamMeatFontExtended12` / `MPlus_12b` / `KR_MeatFont14` 之间选，
// 带中文字形的那几份只在 `rp_patch/resources.zh/font/` 下；
// 而项目自己的记录 `docs/问题与解决记录.md` 续三十九（2026-09-17）早就写过
// "游戏自带字体画中文等于空白"。周围那五行烤在图里的字本来就是英文 ⇒ 我们这一行也用英文。
// 字号按引擎自己在模组页画列表那套（scale 0.8/1.0），不再用上一版的 3.0。
// 算出这一页的 ANM2 原点（= 引擎自己交给 `ANM2::Render` 的那个位置）。
//
// 为什么必须实时算（2026-09-22 傍晚，用户指出参考系放错了）：
// 进这一屏时纸是"滑"进来的 —— 那个滑动就是 `MenuManager+0x3c` 这个偏移在朝目标值收敛。
// 纸与那些行图都是 ANM2 图层，它们的最终位置 = ANM2 原点 + 图层局部坐标；
// 而画字接口用的是绝对坐标 ⇒ 把局部坐标直接交给它，字就不跟着纸动
// （用户原话："纸是移动着出现的，而你的字直接瞬间出现在屏幕上"）。
//
// 引擎自己就是这么算的（`Menu_Game::Render` 反汇编 `0x40E760`~`0x40E784`）：
// x8 = g_MenuManager; x8 = *x8; ldp w9, w8, [x8, #0x3c]   ; 偏移
// x1 = this + 8                                            ; 页面自己的位置
// Vector2::operator+                                      ; ⇒ 原点
// 真机标定也印证了：把 `页面原点 + 那一行的局部坐标` 当绝对坐标画，落点与那一行基本重合
// （用户："红色的 1x 基本就在那个位置"）。
bool ModRowPageOrigin(std::uintptr_t page, float* out) {
    if (out == nullptr || page == 0 || g_ModRow.menuManager == 0) {
        return false;
    }
    float offset[2] = {0.0F, 0.0F};
    float position[2] = {0.0F, 0.0F};
    std::memcpy(offset,
                reinterpret_cast<const void*>(g_ModRow.menuManager + kMenuManagerCanvasOffset),
                sizeof(offset));
    std::memcpy(position, reinterpret_cast<const void*>(page + kPagePositionOffset),
                sizeof(position));
    out[0] = offset[0] + position[0];
    out[1] = offset[1] + position[1];
    return true;
}

// 定语言：调 `Manager::GetLanguageCode()`（两字符码），再按它挑一套生成的布局。
// 一次就定（语言在游戏里改不了、改了要重启）。
void ModRowResolveLanguage(const TargetModule& module) {
    if (g_ModRow.languageState != 0) {
        return;
    }
    if (g_ModRow.manager == 0) {
        g_ModRow.languageState = 3;
        return;
    }
    std::uintptr_t address = 0;
    if (!Guarded(module, kManagerGetLanguageCodeOffset, kManagerGetLanguageCodeExpectedBytes,
                 &address)) {
        g_ModRow.languageState = 2;
        return;
    }
    using GetLanguageCodeFn = const char* (*)(void*);
    const char* code = reinterpret_cast<GetLanguageCodeFn>(address)(
        reinterpret_cast<void*>(g_ModRow.manager));
    if (code == nullptr || code[0] == '\0') {
        g_ModRow.languageState = 3;
        return;
    }
    g_ModRow.language[0] = code[0];
    g_ModRow.language[1] = code[1];
    std::uint32_t packed = 0;
    std::memcpy(&packed, g_ModRow.language, sizeof(packed));  // 'z''h' ⇒ 0x0000687A
    g_NativeModsMenuProbeState.modRowLanguageCode = packed;
    g_ModRow.layout = isaac::runtime::ModRowLayoutForLanguage(g_ModRow.language);
    // 挑到 `en` 而语言码不是 `en` ⇒ 这个语言没有自己的美术（引擎那边也一样走基础资源）。
    const bool isEnglish = g_ModRow.language[0] == 'e' && g_ModRow.language[1] == 'n';
    const bool pickedEnglish = g_ModRow.layout->language[0] == 'e'
                               && g_ModRow.layout->language[1] == 'n';
    g_ModRow.languageState = (pickedEnglish && !isEnglish) ? 4U : 1U;
    g_NativeModsMenuProbeState.modRowLanguageState = g_ModRow.languageState;
}

// 把编进模块的那张 PCX 交给引擎的贴图管理器（只做一次，之后每帧只是 `Render`）。
//
// 为什么可以"不走文件"：见 `kImageManagerSlotOffset` 上面那段（内存版 `LoadImage` 的整条
// 路径不碰文件系统）。为什么只做一次：那个函数每次都新建一个贴图对象并写进
// 引擎的缓存表，每帧调一次就是每帧新建一张（真机上会立刻看出掉帧/内存涨）。
bool ModRowPrepareImage(const TargetModule& module) {
    if (g_ModRow.image.pointer != nullptr) {
        return true;
    }
    if (g_ModRow.imageState != 0) {
        return false;  // 已经失败过，不重试（不刷日志、不折腾引擎）
    }
    if (g_ModRow.layout == nullptr || g_ModRow.languageState == 0) {
        g_ModRow.imageState = 5;
        g_NativeModsMenuProbeState.modRowImageState = 5;
        return false;
    }
    if (g_ModRow.loadImage == nullptr) {
        std::uintptr_t address = 0;
        if (!Guarded(module, kImageManagerLoadMemoryOffset,
                     kImageManagerLoadMemoryExpectedBytes, &address)) {
            g_ModRow.imageState = 2;
            g_NativeModsMenuProbeState.modRowImageState = 2;
            return false;
        }
        g_ModRow.loadImage = reinterpret_cast<ModRowContext::LoadImageMemoryFn>(address);
    }
    if (g_ModRow.renderQuad == nullptr) {
        std::uintptr_t address = 0;
        if (!Guarded(module, kImageManagerRenderQuadOffset,
                     kImageManagerRenderQuadExpected, &address)) {
            g_ModRow.imageState = 2;
            g_NativeModsMenuProbeState.modRowImageState = 2;
            return false;
        }
        g_ModRow.renderQuad = reinterpret_cast<ModRowContext::RenderQuadFn>(address);
    }
    // 两个槽都是"加载器写进去的"（`Manager::load_fonts` 那条指令流里读的就是它们）：
    // 槽里的值**就是**要用的指针，不需要再取一次。
    std::uintptr_t manager = 0;
    std::uintptr_t descriptor = 0;
    std::memcpy(&manager, reinterpret_cast<const void*>(module.base + kImageManagerSlotOffset),
                sizeof(manager));
    std::memcpy(&descriptor,
                reinterpret_cast<const void*>(module.base + kImageManagerDescriptorSlotOffset),
                sizeof(descriptor));
    if (manager == 0 || (manager & 0x7U) != 0 || descriptor == 0) {
        g_ModRow.imageState = 3;
        g_NativeModsMenuProbeState.modRowImageState = 3;
        return false;
    }
    g_ModRow.imageManager = reinterpret_cast<void*>(manager);
    g_ModRow.descriptor = reinterpret_cast<void*>(descriptor);
    const isaac::runtime::ModRowSprite& sprite = g_ModRow.layout->sprite;
    // 四种"路径形态"依次试（见上面那段反汇编结论）；哪个成功就用哪个，并把结果记进诊断字。
    struct Attempt {
        const char* extension;  // 第二参数（x3）：拿去和 "pcx" 比的**扩展名**
        const char* name;       // 第三参数（x4）：对象自己的路径（缓存键 / GetFilePath）
    };
    const Attempt attempts[] = {
        {kModRowSpriteExtension, g_ModRowImageName},   // 按反汇编结论：x3 = 扩展名；名字是缓存键（每代换一个）
        {kModRowSpritePath, kModRowSpritePath},        // 第一版（已知空指针）
        {kModRowSpriteExtension, kModRowSpritePath},
        {"gfx/ui/main menu/mod_row.pcx", g_ModRowImageName},  // 万一 x3 要的是"清干净的路径"
    };
    std::uint32_t mask = 0;
    for (std::uint32_t index = 0; index < 4; ++index) {
        const isaac::runtime::relay::SmartPointerShim result =
            g_ModRow.loadImage(g_ModRow.imageManager, sprite.pcx, sprite.pcxBytes,
                               attempts[index].extension, attempts[index].name,
                               g_ModRow.descriptor);
        if (result.pointer != nullptr) {
            mask |= (1U << index);
        }
        if (g_ModRow.image.pointer == nullptr && result.pointer != nullptr) {
            g_ModRow.image = result;
            g_ModRow.imageAttempt = index + 1;
        }
    }
    g_NativeModsMenuProbeState.modRowImageAttempts = mask;
    g_NativeModsMenuProbeState.modRowImageAttempt = g_ModRow.imageAttempt;
    g_ModRow.imageState = g_ModRow.image.pointer != nullptr ? 1U : 4U;
    g_NativeModsMenuProbeState.modRowImageState = g_ModRow.imageState;
    return g_ModRow.imageState == 1U;
}

// 画我们那一行（贴图版）：位置 = 页面原点（实时算）+ 生成器量出来的页内落点。
//
// 为什么要实时算原点：进这一屏时纸是"滑"进来的（`MenuManager+0x3c` 朝目标值收敛），
// 贴图得跟着纸走 —— 与之前画字时同一条理由。
//
// 画的是哪张图？优先"引擎按文件名从磁盘载进来的那张"（诊断字 [100] == 1），否则回落到
// 内存那张（旧路线）。返回"到底画没画" —— 调用方据此决定要不要落到用字兜底。
// 空图绝不拿去画：上一批真机崩溃（`Data Abort @ 0x0`，`ANM2::Render` 里的空精灵表）就是
// "拿空的东西去画"造成的，这里用返回值把那条路堵死。
bool ModRowDrawSprite(std::uintptr_t page) {
    if (g_ModRow.renderQuad == nullptr || g_ModRow.layout == nullptr) {
        return false;
    }
    void* image = nullptr;
    bool fromDisk = false;
    if (g_ModRow.fileImage.pointer != nullptr) {
        image = g_ModRow.fileImage.pointer;
        fromDisk = true;
    } else if (g_ModRow.image.pointer != nullptr) {
        image = g_ModRow.image.pointer;
    } else {
        return false;  // 两张都没有 ⇒ 交给画字兜底
    }
    float origin[2] = {0.0F, 0.0F};
    const bool haveOrigin = ModRowPageOrigin(page, origin);
    g_NativeModsMenuProbeState.modRowSpriteOrigin = haveOrigin ? 1U : 0U;
    if (!haveOrigin) {
        return false;
    }
    const isaac::runtime::ModRowLayout& layout = *g_ModRow.layout;
    const float left = origin[0] + layout.spriteX;
    const float top = origin[1] + layout.spriteY;
    const float right = left + static_cast<float>(layout.sprite.width);
    const float bottom = top + static_cast<float>(layout.sprite.height);
    // 32 字节 = 左上 / 右上 / 左下 / 右下（`DestinationQuad` 的四个角，见上面的反汇编结论）。
    const float quad[8] = {left, top, right, top, left, bottom, right, bottom};
    const float color[4] = {1.0F, 1.0F, 1.0F, 1.0F};
    g_ModRow.renderQuad(image, quad, color);
    if (fromDisk) {
        ++g_NativeModsMenuProbeState.modRowFileDraws;  // [104]：磁盘那张图画了几帧
    }
    ++g_NativeModsMenuProbeState.modRowSpriteDraws;     // [63]：两条路合起来算"那一行的美术"
    std::memcpy(&g_NativeModsMenuProbeState.modRowTop, &top, sizeof(top));
    return true;
}
void ModRowDrawLabel(std::uintptr_t page) {
    if (g_ModRow.drawText == nullptr || g_ModRow.manager == 0) {
        return;
    }
    // 起：这一行优先用贴图（上面那个函数），本函数只是兜底
    //    （贴图那条链哪一步没通时，至少还有一行字，不会"整行消失"）。
    //    兜底一律用引擎自己的中等字体 + ASCII "MODS"：自己加载的中文字体留给下一步
    //    （模组页里的中文模组名）用，这里不再拿它冒险（LanaPixel 那次黑方块就是教训）。
    const bool useCjk = false;
    void* font = reinterpret_cast<void*>(g_ModRow.manager + kManagerFontOffset);
    const char* label = kModRowLabel;
    // 颜色照抄纸上烤的那套字：把 `gamemenu.pcx` 解出来取墨迹像素，最暗/最常见的是
    // `(55,43,45)`（深褐，不是纯黑）。上一版给的是 `(15,10,8)` ⇒ 真机上用户说
    // "字体明显比纸上的更黑"，就是这里。
    // 2026-09-22 晚（第三轮）：兜底那条路故意画成纯红。
    //   原因：用户连着两轮看到的是兜底画出来的字，而"贴图好了没有"从屏幕上分不出来
    //   （兜底用的深褐和纸上那支笔一个颜色）。红色只出现在"贴图没成"的时候 ⇒
    //   屏幕上看到**红色 MODS** = 贴图那条链还断着；看到**手绘的「模组」** = 好了。
    //   生产/正式版不会走这条兜底（贴图成了就不画它），探针构建里留着当信号。
    const float color[4] = {1.0F, 0.0F, 0.0F, 1.0F};
    // 位置 = 页面原点（实时算）+ 那一行的局部坐标 ⇒ 纸滑动时字跟着走。
    float origin[2] = {0.0F, 0.0F};
    const bool haveOrigin = ModRowPageOrigin(page, origin);
    // 位置改用**生成器算出来的那一格锚点**（引擎行 = 框顶；我们那一格 = 贴图顶），
    // 不再用写死的 `kModRowTextX`；字从锚点往里偏一点，让它落在贴图里字的位置上。
    const float x = origin[0] + kModRowTextX;
    float slotTop = kModEntryTextYFallback;
    if (g_ModRow.layout != nullptr) {
        // 兜底也要**画在贴图里字的位置上**：锚点是"贴图顶"，字从贴图内的 `inkTop` 起。
        slotTop = isaac::runtime::MenuGameSlotTop(*g_ModRow.layout, isaac::runtime::kModEntrySlot)
                  + static_cast<float>(g_ModRow.layout->sprite.inkTop);
    }
    const float y = origin[1] + slotTop + kModRowTextYOffset;
    // 缩放 = 量出来的字高 ÷ 当前字体的行高 —— 换字体自动适应，不用重调。
    //   ⚠️ 这里以前用的是"美术里那行字的**包围盒**高（28）"。那五行是**斜着写**的，
    //   包围盒高 = 字高×cos + 字宽×sin ⇒ 中文那五行量出来 25..34，而真字高只有约 22
    //   ⇒ 照包围盒缩放，画出来的字比周围大一圈（用户原话："仍然很大"）。
    float artHeight = kModRowArtTextHeight;
    if (g_ModRow.layout != nullptr && g_ModRow.layout->glyphHeight > 1.0F) {
        artHeight = g_ModRow.layout->glyphHeight;
    }
    float scale = kModRowTextScaleFallback;
    if (g_ModRow.lineHeight != nullptr) {
        const float lineHeight = g_ModRow.lineHeight(font);
        if (lineHeight > 1.0F && lineHeight < 200.0F) {
            scale = artHeight / lineHeight;
        }
    }
    g_ModRow.drawText(font, label, x, y, scale, scale, color, 0, false);
    ++g_NativeModsMenuProbeState.modRowLabelDraws;
    std::memcpy(&g_NativeModsMenuProbeState.modRowTextY, &y, sizeof(y));
    // [59] 位 0 = 页面原点拿到（拿不到就会把字画到屏幕角上）；位 1 = 中文字体装上；
    //      位 2..4 = 中文字体的加载状态码（1 装上 / 2 入口守卫不过 / 3 引擎拒绝）。
    g_NativeModsMenuProbeState.modRowCjkDraws =
        (haveOrigin ? 1U : 0U) | (useCjk ? 2U : 0U) | ((g_ModRow.cjkFontState & 0x7U) << 2);
}

// 接线用到的一次性校验（装入口中继之前做）。返回是否"能干活"。
void PrepareModRow(const TargetModule& module, std::uintptr_t manager, std::uintptr_t menuManager) {
    if (g_ModRow.manager == 0 && manager != 0) {
        g_ModRow.manager = manager;
        g_NativeModsMenuProbeState.modRowManagerOk = 1;
    }
    if (g_ModRow.menuManager == 0 && menuManager != 0) {
        g_ModRow.menuManager = menuManager;
    }
    if (g_ModRow.getLayer == nullptr) {
        std::uintptr_t address = 0;
        if (Guarded(module, kAnm2GetLayerStubOffset, kAnm2GetLayerStubExpected, &address)) {
            g_ModRow.getLayer = reinterpret_cast<ModRowContext::GetLayerFn>(address);
            g_NativeModsMenuProbeState.modRowLayersFn = 1;
        } else {
            g_NativeModsMenuProbeState.modRowLayersFn = 2;
        }
    }
    if (g_ModRow.setLayerFrame == nullptr) {
        std::uintptr_t address = 0;
        if (Guarded(module, kAnm2SetLayerFrameStubOffset, kAnm2SetLayerFrameStubExpected,
                    &address)) {
            g_ModRow.setLayerFrame = reinterpret_cast<ModRowContext::SetLayerFrameFn>(address);
        }
    }
    if (g_ModRow.drawText == nullptr) {
        std::uintptr_t address = 0;
        if (Guarded(module, kFontDrawStringScaledUTF8Offset,
                    kFontDrawStringScaledUTF8ExpectedBytes, &address)) {
            g_ModRow.drawText = reinterpret_cast<ModRowContext::DrawTextFn>(address);
            g_NativeModsMenuProbeState.modRowFontState = 1;
        } else {
            g_NativeModsMenuProbeState.modRowFontState = 2;
        }
    }
    if (g_ModRow.lineHeight == nullptr) {
        std::uintptr_t address = 0;
        if (Guarded(module, kFontGetLineHeightOffset, kFontGetLineHeightExpectedBytes, &address)) {
            g_ModRow.lineHeight = reinterpret_cast<ModRowContext::FontLineHeightFn>(address);
        }
    }
    // 自己加载一份带中文字形的字体（见 `kCjkFontPath` 的注释）。三个入口都要过守卫；
    //   任一步失败就保持 `cjkFont == nullptr`，那一行退回引擎字体 + ASCII（不会崩、不会空白）。
    if (g_ModRow.cjkFont == nullptr && g_ModRow.cjkFontState == 0) {
        std::uintptr_t ctor = 0;
        std::uintptr_t load = 0;
        std::uintptr_t isLoaded = 0;
        if (!Guarded(module, kFontCtorOffset, kFontCtorExpectedBytes,
                     &ctor) ||
            !Guarded(module, kFontLoadOffset, kFontLoadExpectedBytes,
                     &load) ||
            !Guarded(module, kFontIsLoadedOffset,
                     kFontIsLoadedExpectedBytes, &isLoaded)) {
            g_ModRow.cjkFontState = 2;  // 入口守卫不过（版本不对）
            return;
        }
        using CtorFn = void (*)(void*);
        reinterpret_cast<CtorFn>(ctor)(g_CjkFontStorage);
        const auto loadFn = reinterpret_cast<ModRowContext::FontLoadFn>(load);
        const bool accepted = loadFn(g_CjkFontStorage, kCjkFontPath, nullptr);
        const auto isLoadedFn = reinterpret_cast<ModRowContext::FontIsLoadedFn>(isLoaded);
        if (accepted && isLoadedFn(g_CjkFontStorage)) {
            g_ModRow.cjkFont = g_CjkFontStorage;
            g_ModRow.cjkFontState = 1;  // 装上了
        } else {
            g_ModRow.cjkFontState = 3;  // 引擎拒绝/没装上（路径或资源不对）
        }
    }
}

// 引擎自己那份菜单动画里有没有我们补回去的那一层（`Item6`）。
//
// 判据 = 图层数（`ANM2+0xB0`）。为什么不用 `GetLayer(12)` 是不是空：`ANM2::GetLayer(int)`
// 越界时不返回空指针 —— 它只打一条日志，然后照样按 `[ANM2+0xA8] + index*0xB0` 算出界地址
// （`0xA034` 的反汇编：`ldr w8,[x20,#0xb0]; cmp w8,w19; b.gt`，不满足就 `KAGE_LogMessage`
// 后继续往下算）。拿那个地址当图层用就是读越界内存。
bool ModRowHasNativeLayer(std::uintptr_t anm2) {
    if (anm2 == 0) {
        return false;
    }
    const auto count = *reinterpret_cast<const std::uint32_t*>(anm2 + kAnm2LayerCountOffset);
    const bool present = count >= kMenuGameLayerCountWithModRow;
    g_NativeModsMenuProbeState.modRowNativeLayer = present ? 1U : 2U;
    return present;
}

// `Menu_Game::Render` 入口中继的回调。形状：入口桩是尾调用（`br x16`），
// 所以本回调以 `Menu_Game::Render` 的身份运行、`ret` 直接回到游戏的调用方 ⇒ ABI 必须一致：`(this)`。
//
// 顺序（先挪行、再让引擎画、再还原）：
// 1) 按 `kMenuGameRowShiftY` 挪每一行（插点以上上移、STATS 下移 4、OPTIONS 不动）；
// 2) 光标：按格子设帧 + 加我们自己的 Y 偏移；
// 3) 跑原函数（它画的是"已经挪好的"5 行，以及我们补回去的那一层）；
// 4) 把光标与行偏移都还原（不还原会随帧累积）；
// 5) 只有在"引擎那份动画里没有我们那一层"时，才由我们兜底画（见 `ModRowHasNativeLayer`）。
extern "C" void ModRowMenuGameRenderRelayCallback(void* self) {
    using RenderFn = void (*)(void*);
    const auto original = isaac::runtime::engine_call::AsFunction<RenderFn>(__atomic_load_n(&g_ModRow.renderOriginal,__ATOMIC_ACQUIRE));
    if (original == nullptr) {
        return;
    }
    // 门控：只有"就在选择界面那一格"时才干活；其余时刻**纯透传**（与没挂钩逐帧等价）。
    const bool active = g_NativeModsMenuProbeState.menuState == kGameMenuState &&
                        g_NativeModsMenuProbeState.manualMode != 0 && self != nullptr;
    if (!active) {
        original(self);
        return;
    }
    const auto anm2 = reinterpret_cast<std::uintptr_t>(self) + kPageAnm2Offset;
    // 那一行现在是引擎自己那份菜单动画里的一层（补层工具把 PC 的 `Item6`
    //   补了回去）。有这一层 ⇒ 引擎在这次 `original(self)` 里就把它画了，我们**不许再画一遍**
    //   （画了就是两层叠在一起）。没有这一层（覆盖层没装/被回退）⇒ 行为与 072 一字不变。
    const bool nativeLayer = ModRowHasNativeLayer(anm2);
    ModRowShiftRows(anm2, 1.0F);
    ModRowPlaceCursor(anm2, 1.0F);  // 设帧 + 给光标一个我们自己的 Y 偏移
    original(self);
    ModRowPlaceCursor(anm2, -1.0F);
    ModRowShiftRows(anm2, -1.0F);
    if (nativeLayer) {
        ++g_NativeModsMenuProbeState.modRowRenderCalls;
        return;
    }
    // 绘制优先级：① 引擎按文件名从磁盘载进来的贴图（与所有模组同性质：
    //   图在磁盘上、生命周期由引擎管 ⇒ 关卡加载不会清掉它）；② 内存贴图（旧路线，行为一字不改）；
    //   ③ 用字画（最后兜底，保证"整行消失"永远不会再发生）。
    //   ① ② 都为空时绘制函数返回 false 并自动落到 ③ —— **空图绝不拿去画**。
    if (!ModRowDrawSprite(reinterpret_cast<std::uintptr_t>(self))) {
        ModRowDrawLabel(reinterpret_cast<std::uintptr_t>(self));
    }
    ++g_NativeModsMenuProbeState.modRowRenderCalls;
    // 渲染回调里不再清失败码 —— 上一版每帧都写 0，结果
    // "`ApplyState` 的守卫没过"这种真失败在读数里显示成"没有失败"，白花了一轮真机才定位。
}

// 装 `Menu_Game::Render` 的入口中继（模块初始化线程上、游戏主循环尚未开始）。
void InstallModRowRenderRelay(const TargetModule& module) {
    if (g_NativeModsMenuProbeState.modRowRelayState == 1) {
        return;
    }
    std::uintptr_t target = 0;
    if (!Guarded(module, kMenuGameRenderOffset, kMenuGameRenderExpected, &target)) {
        g_NativeModsMenuProbeState.modRowRelayState = 2;
        g_NativeModsMenuProbeState.modRowRelayFailure = kFailureModRowGuard;
        g_NativeModsMenuProbeState.lastFailure = kFailureModRowGuard;
        return;
    }
    std::uintptr_t original = 0;
    const bool installed = isaac::runtime::relay::TryInstallEntryRelayWithPublisher(
        target, kMenuGameRenderExpected.data(),
        isaac::runtime::engine_call::AddressOfFunction(&ModRowMenuGameRenderRelayCallback),
        PublishProbeOriginal, &g_ModRow.renderOriginal, &original);
    g_NativeModsMenuProbeState.modRowRelayState = installed ? 1U : 2U;
    g_NativeModsMenuProbeState.modRowRelayFailure =
        installed ? 0U : isaac::runtime::relay::LastFailure();
    if (!installed) {
        g_NativeModsMenuProbeState.lastFailure = kFailureModRowGuard;
    }
}

// 每帧（在引擎自己的 `Manager::Update` 之前）：把"我们自己的导航"推进一格，
// 并把引擎的索引写成"夹在 0..4"的值（绝不让它越界）。
// 我们写、引擎也写 —— 但每帧都由我们覆盖一次，所以引擎自己的那次移动不会累积成两格。
// `MenuManager::SetState` 的入口中继：我们那一格的确认只归我们管。
//
// 为什么加它（2026-09-22 深夜，用户实测反馈）：在「模组」那一格按确认跳到了统计页面 ——
// 我们那一格借用引擎索引 3（= 统计那一行），而我们的接管一旦中途退出，引擎本帧就会拿索引 3
// 去 `SetState(9)`（统计）。页面上"跳错页"比"什么都不发生"更难解释，所以这里再加一道保险。
extern "C" void NativeModsMenuSetStateRelayCallback(void* self, std::int32_t state) {
    using SetStateFn = void (*)(void*, std::int32_t);
    const auto original = isaac::runtime::engine_call::AsFunction<SetStateFn>(__atomic_load_n(&g_SetStateRelayOriginal,__ATOMIC_ACQUIRE));
    if (original == nullptr) {
        return;
    }
    // 挡下来要同时满足三条：
    //   ① 当前就在"选择界面"（状态 3）；
    //   ② **我们的光标正停在自己那一格**（格子号 3）—— "统计数据/选项"那两行在我们这边是
    //      第 4/5 格，所以用户真去选它们时这一条不成立，**不会误伤**；
    //   ③ 引擎要去的正是"我们那一格之后"的那两页（统计 9 / 选项 10）——它按索引 3/4 的推断。
    if (g_ModRowSlot == isaac::runtime::kModEntrySlot &&
        g_NativeModsMenuProbeState.menuState == kGameMenuState &&
        (static_cast<std::uint32_t>(state) == 9U || static_cast<std::uint32_t>(state) == 10U)) {
        ++g_NativeModsMenuProbeState.modEntrySwallowed;
        return;  // 不调原函数 ⇒ 状态不变
    }
    original(self, state);
}

void InstallSetStateRelay(const TargetModule& module) {
    if (g_NativeModsMenuProbeState.setStateRelayState == 1) {
        return;
    }
    std::uintptr_t target = 0;
    if (!Guarded(module, kSetStateOffset, kSetStateExpected, &target)) {
        g_NativeModsMenuProbeState.setStateRelayState = 2;
        return;
    }
    std::uintptr_t original = 0;
    const bool installed = isaac::runtime::relay::TryInstallEntryRelayWithPublisher(
        target, kSetStateExpected.data(),
        isaac::runtime::engine_call::AddressOfFunction(&NativeModsMenuSetStateRelayCallback),
        PublishProbeOriginal, &g_SetStateRelayOriginal, &original);
    g_NativeModsMenuProbeState.setStateRelayState = installed ? 1U : 2U;
    if (!installed) {
        g_NativeModsMenuProbeState.lastFailure = kFailureSetStateGuard;
    }
}

void ModRowUpdate(const TargetModule& module, const ActionQueryFn query) {
    std::uintptr_t manager = 0;
    std::uintptr_t menuManager = 0;
    const bool haveManager = ReadSingleton(module, kManagerSlotOffset, &manager);
    const bool haveMenuManager = ReadSingleton(module, kMenuManagerSlotOffset, &menuManager);
    if (haveManager || haveMenuManager) {
        PrepareModRow(module, haveManager ? manager : 0, haveMenuManager ? menuManager : 0);
    }
    // 语言 → 布局：一次就定（语言在游戏里改不了）。定了之后才谈"挑哪套美术"。
    if (g_ModRow.manager != 0) {
        ModRowResolveLanguage(module);
    }
    if (!haveMenuManager || menuManager == 0) {
        g_ModRowSlotInit = 0;  // 离开菜单 ⇒ 下次进来重新取初值
        g_ModRowRestoreOurs = 0;  // 连菜单都离开了 ⇒ "回到我们那一格"这件事作废
        g_NativeModsMenuProbeState.modRowManagerOk = g_ModRow.manager != 0 ? 1U : 0U;
        return;
    }
    if (g_NativeModsMenuProbeState.menuState != kGameMenuState) {
        g_ModRowSlotInit = 0;
        return;
    }
    // 贴图在这里加载：**不在渲染回调里**。这一路跑在引擎主循环的"更新之前"，
    // 不在任何渲染批次中间 ⇒ 引擎建贴图对象的那些锁与状态都干净（避免重入）。
    ModRowPrepareImage(module);
    // 用引擎的"按文件名加载贴图"把磁盘上那张图载进来。放在内存那条之后
    // 只是"都在同一处准备"（管理器指针与顶点描述符正是内存那条路取的）；两条互不依赖：
    // 这条成了绘制就优先用它，没成则照旧走内存贴图（兜底，行为不变）。
    ModRowPrepareFileImage(module);
    const std::uintptr_t page = menuManager + kMenuGamePageOffsetInMenuManager;
    // 第一次进入那一屏：按引擎的**现有**索引初始化我们的格子（引擎索引 e ≥ 3 对应我们的 e+1，
    // 因为我们插进去的那一格占了引擎原来的第 4 格）。
    // 例外：从模组页回来时不换算，直接回到我们那一格（理由见 `g_ModRowRestoreOurs`）。
    if (g_ModRowSlotInit == 0) {
        if (g_ModRowRestoreOurs != 0) {
            g_ModRowRestoreOurs = 0;
            g_ModRowSlot = isaac::runtime::kModEntrySlot;
        } else {
            std::uint32_t engineIndex = 0;
            std::memcpy(&engineIndex, reinterpret_cast<const void*>(page + kPageSelectedIndexOffset),
                        sizeof(engineIndex));
            g_ModRowSlot = engineIndex < isaac::runtime::kModEntrySlot ? engineIndex
                                                                     : engineIndex + 1;
            if (g_ModRowSlot >= isaac::runtime::kMenuGameEntryCount) {
                g_ModRowSlot = isaac::runtime::kMenuGameEntryCount - 1;
            }
        }
        g_ModRowSlotInit = 1;
    }
    if (query != nullptr) {
        const bool up = HeldByAnyone(query, kModRowActionUp);
        const bool down = HeldByAnyone(query, kModRowActionDown);
        const bool confirm = HeldByAnyone(query, kModRowActionConfirm);
        if (Edge(&g_ModRowLastUp, up)) {
            g_ModRowSlot = isaac::runtime::AdvanceSlot(g_ModRowSlot, false);
            ++g_NativeModsMenuProbeState.modRowUpPresses;
        }
        if (Edge(&g_ModRowLastDown, down)) {
            g_ModRowSlot = isaac::runtime::AdvanceSlot(g_ModRowSlot, true);
            ++g_NativeModsMenuProbeState.modRowDownPresses;
        }
        if (Edge(&g_ModRowLastConfirm, confirm)) {
            ++g_NativeModsMenuProbeState.modRowConfirmPresses;
            // 把"按下那一刻我们在第几格"记下来 —— 用户反馈"按了模组却进了统计"，
            // 这一格就是判断"到底是格子记错、还是接管退出了"的第一手证据。
            g_NativeModsMenuProbeState.modRowLastConfirmSlot = g_ModRowSlot;
            if (g_ModRowSlot == isaac::runtime::kModEntrySlot) {
                ++g_ModRowConfirmOnOurs;
                // 确认接上了 —— 在我们那一格按确认 = 进模组页（引擎状态 16）。
                //
                // 为什么必须在这里（我们的更新回调里）就把状态切掉、而不是"等引擎自己处理"：
                // 本回调跑在引擎 `Manager::Update` **之前**，而引擎那一帧还会读一次同一个动作
                // （`Menu_Game::Update` 的确认分支）。我们那一格写回给引擎的索引是 3
                // （`EngineIndexClampedForSlot(3) == 3`）⇒ 引擎以为选中的是**统计数据**，
                // 它会 `SetState(9)`。**先切成 16**，引擎本帧的分派表（`cmp w8,#0xf`）就不会再去叫
                // `Menu_Game::Update` 了 —— 这一下同时完成了"进页面"和"吃掉那次确认"。
                EnterModsPage(module, query);
            }
        }
    }
    // 写回给引擎的是行号（`EngineRowForSlot`），不是"格子号夹一下" —— 2026-09-23 修正。
    //
    // 用户实测："统计和选项按了**都是设置**"。原因就在这一句：引擎的确认跳表按**它的行号**查
    // （行 3 = 统计 ⇒ `SetState(9)`；行 4 = 选项 ⇒ `SetState(10)`），而我们那一列是插过一格的
    // ⇒ 视觉上的"统计数据"（我们的第 4 格）在引擎那里必须是**行 3**。
    // 上一版用的是 `EngineIndexClampedForSlot`（把格子号夹到 0..4），它把第 4 格写成 4
    // ⇒ 引擎认为选中的是"选项" ⇒ 于是"统计按了是设置"。
    // 现在的映射（与 `EngineRowForSlot` 一致）：0/1/2 ⇒ 0/1/2、**3 与 4 ⇒ 3**、5 ⇒ 4。
    // 我们那一格（3）借用的就是行 3（统计）⇒ "按了模组却会走到统计"仍要靠**我们自己的接管**拦，
    // 以及那道 `SetState` 中继兜底。
    const std::uint32_t row = isaac::runtime::EngineRowForSlot(g_ModRowSlot);
    const std::uint32_t clamped =
        row < isaac::runtime::kMenuGameEngineEntryCount
            ? row
            : isaac::runtime::kMenuGameEngineEntryCount - 1;
    std::memcpy(reinterpret_cast<void*>(page + kPageSelectedIndexOffset), &clamped,
                sizeof(clamped));
    g_NativeModsMenuProbeState.modRowSlot = g_ModRowSlot;
    g_NativeModsMenuProbeState.modRowEngineIndex = clamped;
    if (g_ModRow.layout != nullptr) {
        g_NativeModsMenuProbeState.modRowCursorFrame =
            isaac::runtime::CursorFrameForSlot(*g_ModRow.layout, g_ModRowSlot);
    }
    g_NativeModsMenuProbeState.modRowOnOurs = g_ModRowSlot == isaac::runtime::kModEntrySlot ? 1U : 0U;
    g_NativeModsMenuProbeState.modRowConfirmOnOurs = g_ModRowConfirmOnOurs;
    if (g_ModRow.layout != nullptr) {
        const float top = isaac::runtime::MenuGameSlotTop(*g_ModRow.layout, g_ModRowSlot);
        std::memcpy(&g_NativeModsMenuProbeState.modRowTop, &top, sizeof(top));
    }
    g_NativeModsMenuProbeState.modRowManagerOk = g_ModRow.manager != 0 ? 1U : 0U;
}

// 把「模组」那一格的确认键接上（照 PC 的做法进引擎状态 16）
//
// ## 为什么是状态 16（不是我们自己造一个"子页面")
//
// PC 上"选模组"就是让引擎切到状态 16：`Menu_Game::Update` 的确认分支按"选中行"查跳表，
// 行 3（挑战与统计之间那一格，PC 的 `Item6`）⇒ `SetState(16)`；而状态 16 的位置槽
// （`MenuManager + 0x1AFF08 + 16*8`）至今存在、`SetModsOffset` 写的 `+0x1AFF8C` 正是它的 Y。
// 切过去时 `SetState` 自己会播翻页音（两个都非 0 的状态之间才播）。
//
// ## 为什么**不**调引擎的 `Menu_Mods::Update`
//
// 它会按确认时往模组目录写/删 `disable.it`（反汇编 `0x4105D4` 起），而卡上模组目录就在
// **romfs 覆盖层**里（`/atmosphere/contents/<title>/romfs/isaac_mods/mods/`）—— 那正是本项目
// 历史上"写覆盖层 ⇒ 下次启动装载阶段崩"的雷区。⇒ 页面只借引擎的 `Render`（含它自己调
// `SetModsOffset` 的滚动），输入与开关状态由我们维护（`mod_page_nav.hpp`，有宿主门禁）。

// 进入模组页：补上 Switch 版删掉的那一下（`Menu_Mods::Reset`），再走引擎自己的 `SetState(16)`。
void EnterModsPage(const TargetModule& module, const ActionQueryFn query) {
    using ResetFn = void (*)(void*);
    // 0) 前提：得在"选择界面"那一屏（否则说明这一下不是从我们那一格来的）。
    std::uintptr_t menuManager = 0;
    std::uint32_t engineState = 0;
    if (ReadSingleton(module, kMenuManagerSlotOffset, &menuManager) && menuManager != 0) {
        std::memcpy(&engineState, reinterpret_cast<const void*>(menuManager + kMenuManagerStateOffset),
                    sizeof(engineState));
    }
    if ((engineState & 0xFFFFU) != kGameMenuState) {
        g_NativeModsMenuProbeState.modEntryOutcome = 2;
        return;
    }
    // 1) 页面得是"已经 Init 过"的。没起来就**当场补做一次**，而不是像上一版那样直接放弃
    //    （那正是"按了确认却跳到统计页面"的一个可能原因：我们退出了，引擎就按它自己的索引去处理）。
    if (g_NativeModsMenuProbeState.initResult != kInitOk) {
        if (TryPrepareModsVector(module)) {
            TryInitManualPage(module);
        }
        if (g_NativeModsMenuProbeState.initResult != kInitOk) {
            g_NativeModsMenuProbeState.modEntryOutcome = 1;
            return;
        }
    }
    // 2) "归零"这一下**不再依赖引擎的 `Reset`**：那几个字段我们自己就能写。
    //    引擎的 `Reset` 只在守卫过得去时额外调一次（它还会重读一遍 ModManager 指针、播 "Main" 动画）。
    const std::uint32_t zero = 0;
    std::memcpy(reinterpret_cast<void*>(g_ManualObject + isaac::runtime::kModsSelectedElementOffset),
                &zero, sizeof(zero));
    std::memcpy(reinterpret_cast<void*>(g_ManualObject + isaac::runtime::kModsHoldTimerOffset), &zero,
                sizeof(zero));
    std::memcpy(reinterpret_cast<void*>(g_ManualObject + isaac::runtime::kModsEditedOffset), &zero,
                sizeof(zero));
    std::uintptr_t reset = 0;
    if (Guarded(module, kMenuModsResetOffset, kMenuModsResetExpected, &reset)) {
        reinterpret_cast<ResetFn>(reset)(g_ManualObject);
        g_NativeModsMenuProbeState.modsPageResetState = 1;
    } else {
        // 守卫不过只是"少做一次锦上添花"，**不是**不进去的理由（上一版就是在这里 return 的）。
        g_NativeModsMenuProbeState.modsPageResetState = 2;
    }
    // 先让"那一格的滚动值"变成确定值，再去算纸的位置。
    // 页面自己的 `Render` 每帧会调 `SetModsOffset(选中项)`，但那要等**下一帧**；
    // 而我们算位置就在这一帧之后 —— 不先调一次的话，第一次进来读到的还是 `Init` 的旧值
    // （-290 vs 实际 -216，差 74 格）⇒ 用户看到的就是"错位 1~2 秒之后才回到正确位置"。
    // 只改内存（写一格 + 置"画布在动"标志），与页面自己那一句完全同形。
    std::uintptr_t setModsOffset = 0;
    if (Guarded(module, kSetModsOffsetOffset, kSetModsOffsetExpected, &setModsOffset)) {
        using SetModsOffsetFn = void (*)(void*, int);
        reinterpret_cast<SetModsOffsetFn>(setModsOffset)(reinterpret_cast<void*>(menuManager), 0);
    }
    // 记下"进入那一刻"的视图偏移 Y：与现场的 `[27]` 一比，就知道引擎有没有在滑（过渡动画）。
    if (menuManager != 0) {
        std::memcpy(&g_NativeModsMenuProbeState.modsPageOffsetYAtEnter,
                    reinterpret_cast<const void*>(menuManager + kMenuManagerCanvasOffset + 4),
                    sizeof(std::uint32_t));
    }
    ++g_NativeModsMenuProbeState.modsPageEnterCalls;
    // 3) 交给引擎的状态机（= PC 的做法）。这一步**必须**发生：走到这里之后引擎本帧的分派表
    //    （`cmp w8,#0xf`）就不会再去叫 `Menu_Game::Update`，也就不会再拿我们那一格的索引 3 去开统计页。
    ApplyState(module, isaac::runtime::kModsPageState);
    // 4) 事后核对：状态到底变没变（这一格就是"进去没进去"的硬判据）。
    std::uint32_t after = 0;
    if (ReadSingleton(module, kMenuManagerSlotOffset, &menuManager) && menuManager != 0) {
        std::memcpy(&after, reinterpret_cast<const void*>(menuManager + kMenuManagerStateOffset),
                    sizeof(after));
    }
    g_NativeModsMenuProbeState.modEntryOutcome =
        isaac::runtime::ModPageIsActive(after & 0xFFFFU) ? 3U : 4U;
    // 回来时光标要落在我们那一格上（理由见 `g_ModRowRestoreOurs`）。
    g_ModRowRestoreOurs = 1;
    // 位置那套状态机（第二帧定位置、停稳后自证一次）每次进页面都要重来。
    g_ModsPagePositionSet = 0;
    g_ModsPageSettledFrames = 0;
    g_ModsPageStillFrames = 0;
    g_ModsPageCorrected = 0;
    g_ModsPageLastOffsetX = 0.0F;
    g_ModsPageLastOffsetY = 0.0F;

    // 把引擎的"模组总开关"置上。真机读数（058 的第一次现场）发现它是 0，
    // 而 `Menu_Mods::Render` 在它为 0 时**只用一个颜色画所有行**（不读条目自己的 `+0x138`）
    // ⇒ 不置它，"按确认切换开关"在屏幕上根本看不出来。
    // 理由与 PC 语义见 `kModsEnabledGateOn` 的注释；**只改内存**，不碰任何文件。
    std::uintptr_t managerForGate = 0;
    if (ReadSingleton(module, kManagerSlotOffset, &managerForGate) && managerForGate != 0) {
        std::uint8_t before = 0;
        std::memcpy(&before,
                    reinterpret_cast<const void*>(managerForGate + kManagerModsEnabledOffset),
                    sizeof(before));
        g_NativeModsMenuProbeState.modsGateBefore = before;
        const auto wanted = static_cast<std::uint8_t>(isaac::runtime::kModsEnabledGateOn);
        std::memcpy(reinterpret_cast<void*>(managerForGate + kManagerModsEnabledOffset), &wanted,
                    sizeof(wanted));
        g_NativeModsMenuProbeState.modsGateWritten = 1;
    }

    // 必须把输入边沿按"当前还按着的情况"锁上，否则页面第一帧就会误判一次新按下：
    // 进页面用的就是那个确认键（A），它现在**还按着**，而 `g_ModsPageLastConfirm` 还是 0
    // ⇒ 第一帧的 `Edge()` 会返回"刚按下" ⇒ **刚进去就顺手把第一个模组的开关翻掉了**。
    // 按住计时同理：若方向键是按着进来的，页面对象里的计时刚被 `Reset` 清零，第一帧也会走一格。
    bool directionHeld = false;
    if (query != nullptr) {
        const bool confirmHeld = HeldByAnyone(query, kModRowActionConfirm);
        const bool backHeld = HeldByAnyone(query, kModRowActionBack);
        const bool upHeld = HeldByAnyone(query, kModRowActionUp);
        const bool downHeld = HeldByAnyone(query, kModRowActionDown);
        g_ModsPageLastConfirm = isaac::runtime::ModPageLatchedEdge(confirmHeld);
        g_ModsPageLastBack = isaac::runtime::ModPageLatchedEdge(backHeld);
        g_ModsPageLastUp = isaac::runtime::ModPageLatchedEdge(upHeld);
        g_ModsPageLastDown = isaac::runtime::ModPageLatchedEdge(downHeld);
        directionHeld = upHeld || downHeld;
    }
    const std::uint32_t seed = isaac::runtime::ModPageHoldSeed(directionHeld);
    std::memcpy(reinterpret_cast<void*>(g_ManualObject + isaac::runtime::kModsHoldTimerOffset), &seed,
                sizeof(seed));
}

// 状态 16 期间由我们驱动页面：导航（含按住重复）、切换开关、返回。
// 数据面：`g_Manager + 0x36800` 那张表（`begin/end/cap`，每项一个指针，条目里 `+0x138` 是启用位）
// —— 就是起我们自己喂进去的那张表，`Menu_Mods::Render` 画的也是它。
void ModsPageUpdate(const TargetModule& module, const ActionQueryFn query) {
    std::uintptr_t menuManager = 0;
    const bool haveMenuManager =
        ReadSingleton(module, kMenuManagerSlotOffset, &menuManager) && menuManager != 0;
    std::uint32_t engineState = 0;
    if (haveMenuManager) {
        std::memcpy(&engineState,
                    reinterpret_cast<const void*>(menuManager + kMenuManagerStateOffset),
                    sizeof(engineState));
        // 状态 16 那一格的目标 Y（引擎自己给的值）——顺带留证：它是"这一格真的存在"的另一条证据。
        std::memcpy(&g_NativeModsMenuProbeState.modsPageScrollTargetY,
                    reinterpret_cast<const void*>(menuManager + isaac::runtime::kMenuManagerModsScrollY),
                    sizeof(std::uint32_t));
    }
    // 模组总开关（`g_Manager+0x36519`）：**每帧都读**（不只进页面时），
    // 这样"进页面之前是 0、进去之后变 1"这件事在读数里直接看得见（的判据）。
    {
        std::uintptr_t managerForGate = 0;
        if (ReadSingleton(module, kManagerSlotOffset, &managerForGate) && managerForGate != 0) {
            std::uint8_t gate = 0;
            std::memcpy(&gate,
                        reinterpret_cast<const void*>(managerForGate + kManagerModsEnabledOffset),
                        sizeof(gate));
            g_NativeModsMenuProbeState.modsEnabledGate = gate;
        }
    }
    const bool active = haveMenuManager && isaac::runtime::ModPageIsActive(engineState & 0xFFFFU);
    g_NativeModsMenuProbeState.modsPageActive = active ? 1U : 0U;
    // 离开模组页（刚刚还在、现在不在了）且这次改过开关 ⇒ 落盘一次
    //（用户 2026-09-22 裁定："退出时写一次"）。写的是游戏存档分区，不是卡上的覆盖层。
    if (g_ModsPageWasActive != 0 && !active) {
        g_ModsPageWasActive = 0;
        std::uint32_t editedNow = 0;
        std::memcpy(&editedNow,
                    reinterpret_cast<const void*>(g_ManualObject + isaac::runtime::kModsEditedOffset),
                    sizeof(editedNow));
        if (editedNow != 0) {
            g_NativeModsMenuProbeState.toggleSaveState =
                isaac::runtime::ModMenuSaveToggles() ? 1U : 2U;
        }
    }
    if (active) {
        g_ModsPageWasActive = 1;
    }
    if (!active) {
        // 离开页面（引擎状态不再是我们切的 16）：边沿状态清零，下次进来从干净状态开始。
        g_ModsPageLastUp = 0;
        g_ModsPageLastDown = 0;
        g_ModsPageLastConfirm = 0;
        g_ModsPageLastBack = 0;
        return;
    }
    ++g_NativeModsMenuProbeState.modsPageDrivenFrames;

    // ── 数据面：条目表 ──────────────────────────────────────────────────────────────
    std::uintptr_t manager = 0;
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    std::uint32_t entryCount = 0;
    if (ReadSingleton(module, kManagerSlotOffset, &manager) && manager != 0) {
        std::memcpy(&begin, reinterpret_cast<const void*>(manager + kManagerModsVectorOffset),
                    sizeof(begin));
        std::memcpy(&end, reinterpret_cast<const void*>(manager + kManagerModsVectorOffset + 8),
                    sizeof(end));
        // 条数只接受"像话"的那一种（`begin` 是个真指针、`end-begin` 是 8 的倍数且不太大）。
        if (begin >= 0x1000 && end >= begin && ((end - begin) % 8) == 0 &&
            (end - begin) <= 8ULL * 4096ULL) {
            entryCount = static_cast<std::uint32_t>((end - begin) / 8);
        }
    }
    g_NativeModsMenuProbeState.modsPageEntryCount = entryCount;

    // ── 页面对象里的两个字段（选中项、按住计时）──────────────────────────────────────
    std::uint32_t selected = 0;
    std::uint32_t hold = 0;
    std::memcpy(&selected,
                reinterpret_cast<const void*>(g_ManualObject + isaac::runtime::kModsSelectedElementOffset),
                sizeof(selected));
    std::memcpy(&hold,
                reinterpret_cast<const void*>(g_ManualObject + isaac::runtime::kModsHoldTimerOffset),
                sizeof(hold));

    // ── 输入 ────────────────────────────────────────────────────────────────────────
    bool up = false;
    bool down = false;
    bool confirm = false;
    bool back = false;
    if (query != nullptr) {
        up = HeldByAnyone(query, kModRowActionUp);
        down = HeldByAnyone(query, kModRowActionDown);
        confirm = HeldByAnyone(query, kModRowActionConfirm);
        back = HeldByAnyone(query, kModRowActionBack);
    }
    const bool upEdge = Edge(&g_ModsPageLastUp, up);
    const bool downEdge = Edge(&g_ModsPageLastDown, down);
    // 节奏与引擎同形（`mod_page_nav.hpp`）：**判断用的是上一帧的计时值**，所以刚按下的那一帧
    // 立刻走一格（那时 `hold` 还是 0），之后要过 50 帧、再每 10 帧一格。
    // 顺序很重要：引擎是 `Update` 先看、`UpdateKeyPress` 后加，我们照这个顺序。
    if (upEdge || (up && isaac::runtime::ModPageHoldShouldMove(hold))) {
        selected = isaac::runtime::ModPageAdvance(selected, entryCount, false);
    }
    if (downEdge || (down && isaac::runtime::ModPageHoldShouldMove(hold))) {
        selected = isaac::runtime::ModPageAdvance(selected, entryCount, true);
    }
    hold = isaac::runtime::ModPageHoldNext(hold, up || down);
    std::memcpy(reinterpret_cast<void*>(g_ManualObject + isaac::runtime::kModsSelectedElementOffset),
                &selected, sizeof(selected));
    std::memcpy(reinterpret_cast<void*>(g_ManualObject + isaac::runtime::kModsHoldTimerOffset), &hold,
                sizeof(hold));

    // 确认 = 切换这一条的开关。**只改内存**（条目 `+0x138` 那一位），退出页面时才写清单
    // （用户 2026-09-22 裁定）⇒ 这一批**不碰 SD**。
    if (Edge(&g_ModsPageLastConfirm, confirm)) {
        ++g_NativeModsMenuProbeState.modsPageTogglePresses;
        if (entryCount > 0 && selected < entryCount) {
            std::uintptr_t entry = 0;
            std::memcpy(&entry,
                        reinterpret_cast<const void*>(begin + selected * sizeof(std::uintptr_t)),
                        sizeof(entry));
            if (entry >= 0x1000) {
                std::uint8_t enabled = 0;
                std::memcpy(&enabled,
                            reinterpret_cast<const void*>(entry + kEntryEnabledOffset),
                            sizeof(enabled));
                const std::uint8_t next =
                    static_cast<std::uint8_t>(isaac::runtime::ModPageToggleEnabled(enabled));
                std::memcpy(reinterpret_cast<void*>(entry + kEntryEnabledOffset), &next,
                            sizeof(next));
                const std::uint32_t edited = 1;
                std::memcpy(reinterpret_cast<void*>(g_ManualObject + isaac::runtime::kModsEditedOffset),
                            &edited, sizeof(edited));
                // 把这一下同时写进运行时既有的开关服务（只改内存、不落盘）。
                // 页面上那一栏读的就是它（`ModMenuDiscoveredEnabled`），所以两边永远是同一份口径。
                const char* directory = isaac::runtime::ModMenuDiscoveredDirectory(selected);
                ++g_NativeModsMenuProbeState.toggleSetCalls;
                if (!isaac::runtime::ModMenuSetEnabled(directory, next != 0)) {
                    ++g_NativeModsMenuProbeState.toggleSetFailures;
                }
            }
        }
    }
    // 返回 = 引擎自己的做法：`SetState(3)`（`Menu_Mods::Update` 就是这么做的）。
    // 这一步一执行，`MenuManager::Update` 本帧的分派就把 `Menu_Game::Update` 接回来了 ——
    // 也就是说"回到选择界面"完全走引擎的路径，我们不多写一行。
    if (Edge(&g_ModsPageLastBack, back)) {
        ++g_NativeModsMenuProbeState.modsPageBackPresses;
        ApplyState(module, kGameMenuState);
        return;
    }

    // ── 留证 ────────────────────────────────────────────────────────────────────────
    g_NativeModsMenuProbeState.modsPageSelected = selected;
    g_NativeModsMenuProbeState.modsPageHoldTimer = hold;
    std::uint32_t edited = 0;
    std::memcpy(&edited,
                reinterpret_cast<const void*>(g_ManualObject + isaac::runtime::kModsEditedOffset),
                sizeof(edited));
    g_NativeModsMenuProbeState.modsPageEdited = edited;
    g_NativeModsMenuProbeState.lastFailure = kFailureNone;
}

void NativeModsMenuProbeUpdate() noexcept {
    const std::optional<TargetModule> module = FindTargetModule();
    if (!module.has_value()) {
        g_NativeModsMenuProbeState.lastFailure = kFailureModuleNotFound;
        return;
    }
    ++g_UpdateCount;
    RefreshEngineModList(*module);

    // `g_MenuManager` 是手动 Init 的前置条件，每帧顺手记一格（它随菜单生命周期出现/消失），
    // 顺便把状态机当前状态（`MenuManager+0x38`）也记下来核对静态表。
    std::uintptr_t manager = 0;
    const bool menuManagerOk = ReadSingleton(*module, kMenuManagerSlotOffset, &manager);
    g_NativeModsMenuProbeState.menuManagerOk = menuManagerOk ? 1U : 0U;
    if (menuManagerOk && manager != 0) {
        RecordPagePosition(manager + kMenuTitleOffset, &g_NativeModsMenuProbeState.titlePosX,
                           &g_NativeModsMenuProbeState.titlePosY);
        RecordPagePosition(manager + kMenuOptionsOffset, &g_NativeModsMenuProbeState.optionsPosX,
                           &g_NativeModsMenuProbeState.optionsPosY);
        RecordPagePosition(manager + kMenuKeyConfigOffset, &g_NativeModsMenuProbeState.keyConfigPosX,
                           &g_NativeModsMenuProbeState.keyConfigPosY);
        std::uint32_t state = 0;
        std::memcpy(&state, reinterpret_cast<const void*>(manager + kMenuManagerStateOffset),
                    sizeof(state));
        g_NativeModsMenuProbeState.menuState = state & 0xFFFFU;
        // 页面空间 → 屏幕的偏移（`MenuManager+0x3c`），以及可见屏幕有多大（`WIDTH`/`HEIGHT`）。
        // 这两个数一起才能算出"页面空间被裁掉多少"（见 `kMenuManagerCanvasOffset` 的注释）。
        RecordPagePosition(manager + kMenuManagerCanvasOffset, &g_NativeModsMenuProbeState.menuOffsetX,
                           &g_NativeModsMenuProbeState.menuOffsetY);
        RecordScreenSize(*module);
        // 位置改成"两个方向都跟着画布走"（= 引擎自己的页面就是这么摆的）。
        //
        // 用户 2026-09-23 第二次反馈（很具体，直接指出错在哪）：
        //   「是那种速度很快就跳到了模组界面，其他的似乎没反应过来的感觉」
        // ⇒ 上一版（062）只让 **Y** 跟着画布走、**X 仍然钉在屏幕中间**，
        //   于是这一页**一开场就横向铺满屏幕**（纸 480 宽、始终对着屏幕中央），
        //   而背景那条菜单还在按画布速度慢慢往外滑 ⇒ 看起来就是"纸啪一下盖上来、别的没跟上"。
        //
        // 现在：**位置只定一次**（两个方向都定），之后一律不动 ⇒
        //   纸的屏幕位置 = 画布偏移 + 固定位置，**与引擎自己的页面同一个速度、同一套过渡**：
        //   开场时它整个在屏幕外（这一页的家在画布很右边），随画布滑动**从左侧滑进来**，
        //   停稳时正好落在已验收的 (240, 72)。
        //
        // 位置怎么定：引擎自己的约定是 `目标偏移 = 那一格 + 居中量`
        // （`MenuManager::Update` 对每个页面都算这一条：`this + 状态*8 + 0x1AFF08` 再与
        //  `get_target_offset() = ((宽-480)/2, (高-270)/2)` 相加；状态 1 与状态 3 上已与真机读数逐格吻合）。
        // 于是"画布停稳时纸落在目标原点" ⇔ `本页位置 = 目标原点 − (它自己加的 200,0) − 目标偏移`。
        //
        // 为什么"第二帧"才定：`Menu_Mods::Render` 每帧会调 `SetModsOffset(选中项)` 改写那一格的 Y，
        // 第一帧时它还可能是 `Init` 留下的旧值 ⇒ 定早了纸会摆错（差 74 格，肉眼可见）。
        // 第一帧的位置**保持原样**（1/60 秒，看不见）——比"先用钉住的旧办法画一帧再跳"干净。
        // 横向目标从"页面框正中(240)"改成按 PC 实测对齐的 160。
        //
        // 为什么改（2026-09-23）：用户反馈"位置不对"。拿两张截图用同一把尺子量
        // （以"纸的宽度 = 229 画布格（同一块美术，必然相同）"作标尺）：
        //   * PC 参照图：纸中心 ≈ 画布 x 180（整幅 441 格宽，说明那张图左右一共裁掉约 39 格）；
        //   * 我们的 NS 截图：纸中心 = 画布 x 269（可见区从画布 27 起算）。
        // ⇒ **横向偏右约 80~90 格**，纵向只差 10 格以内（保持 72 不动）。
        // 同时 PC 侧反汇编也印证了机制：`MenuManager::Init` 里给模组页摆位置是
        // "读页面家位置 → 取负 → 写进页面 Position"，而写进去的常量里含 **1440.0**
        // —— 与 Switch 引擎里"模组页那一格"的值一致（说明格子没用错）。
        // 剩下的横向差来自"引擎的画布偏移 + 页面自己加的 200"这两层，PC 那张截图裁过、
        // 绝对位置定不死 ⇒ 先按量到的差值移过去，再由真机确认一次。
        const float targetOriginX = kModsPageTargetOriginX;        // = 200 − 27（见常量注释）
        const float targetOriginY = -kModsSheetOffsetY;            // 72：纸的上沿压在页面顶端
        if (g_NativeModsMenuProbeState.menuState == isaac::runtime::kModsPageState) {
            float offset[2] = {0.0F, 0.0F};
            std::memcpy(offset, reinterpret_cast<const void*>(manager + kMenuManagerCanvasOffset),
                        sizeof(offset));
            if (g_ModsPagePositionSet == 0) {
                if (g_ModsPageSettledFrames++ >= 1) {
                    float slot[2] = {0.0F, 0.0F};
                    std::memcpy(slot,
                                reinterpret_cast<const void*>(
                                    manager + isaac::runtime::kMenuManagerStateSlotBase +
                                    isaac::runtime::kModsPageState * 8),
                                sizeof(slot));
                    float screen[2] = {0.0F, 0.0F};
                    std::memcpy(&screen[0], &g_NativeModsMenuProbeState.screenWidth, sizeof(float));
                    std::memcpy(&screen[1], &g_NativeModsMenuProbeState.screenHeight, sizeof(float));
                    const float centerX = (screen[0] - kPageBoxWidth) * 0.5F;
                    const float centerY = (screen[1] - 270.0F) * 0.5F;
                    g_ModsPageTargetOffsetX = slot[0] + centerX;
                    g_ModsPageTargetOffsetY = slot[1] + centerY;
                    g_ModsPagePositionX = targetOriginX - kModsRenderExtraX - g_ModsPageTargetOffsetX;
                    g_ModsPagePositionY = targetOriginY - g_ModsPageTargetOffsetY;
                    g_ModsPagePositionSet = 1;
                    std::memcpy(&g_NativeModsMenuProbeState.modsPageFixedY, &g_ModsPagePositionY,
                                sizeof(std::uint32_t));
                    std::memcpy(&g_NativeModsMenuProbeState.modsPageTargetOffsetX,
                                &g_ModsPageTargetOffsetX, sizeof(std::uint32_t));
                }
            } else {
                std::memcpy(g_ManualObject + 0x8, &g_ModsPagePositionX, sizeof(g_ModsPagePositionX));
                std::memcpy(g_ManualObject + 0x8 + sizeof(g_ModsPagePositionX), &g_ModsPagePositionY,
                            sizeof(g_ModsPagePositionY));
                // 兜底自证：等画布**停稳**之后核对一次"纸到底画在哪"（停稳 = 偏移连续若干帧没变）。
                const float deltaX = offset[0] - g_ModsPageLastOffsetX;
                const float deltaY = offset[1] - g_ModsPageLastOffsetY;
                const float moved = (deltaX < 0 ? -deltaX : deltaX) + (deltaY < 0 ? -deltaY : deltaY);
                g_ModsPageStillFrames = moved < 0.01F ? g_ModsPageStillFrames + 1 : 0;
                if (g_ModsPageStillFrames == kSettleFrames && g_ModsPageCorrected == 0) {
                    g_ModsPageCorrected = 1;
                    const float originX = offset[0] + g_ModsPagePositionX + kModsRenderExtraX;
                    const float originY = offset[1] + g_ModsPagePositionY;
                    const float fixX = targetOriginX - originX;
                    const float fixY = targetOriginY - originY;
                    const float fixSum = (fixX < 0 ? -fixX : fixX) + (fixY < 0 ? -fixY : fixY);
                    std::memcpy(&g_NativeModsMenuProbeState.modsPageSettledOffsetX, &offset[0],
                                sizeof(std::uint32_t));
                    std::memcpy(&g_NativeModsMenuProbeState.modsPageCorrection, &fixSum,
                                sizeof(std::uint32_t));
                    if (fixSum > 1.0F) {
                        // 只可能发生在那条公式算错的时候（例如"那一格的 X 不参与"）。
                        // 修正一次，让**静止位置**永远是对的；过渡动画的形状不变。
                        g_ModsPagePositionX += fixX;
                        g_ModsPagePositionY += fixY;
                    }
                }
                g_ModsPageLastOffsetX = offset[0];
                g_ModsPageLastOffsetY = offset[1];
            }
        }
        // 记下本页**实际**被画的点（= 偏移 + 本页位置 + 200）。
        // 起：它不再恒等于 (240,72)，而是过渡动画期间会动（Y 从屏幕上方滑到 72）
        // ⇒ 读数里这一格就是"动画在不在动"的直接证据。
        {
            float offset[2] = {0.0F, 0.0F};
            std::memcpy(offset, reinterpret_cast<const void*>(manager + kMenuManagerCanvasOffset),
                        sizeof(offset));
            float page[2] = {0.0F, 0.0F};
            std::memcpy(page, reinterpret_cast<const void*>(g_ManualObject + 0x8), sizeof(page));
            const float originX = offset[0] + page[0] + kModsRenderExtraX;
            const float originY = offset[1] + page[1];
            std::memcpy(&g_NativeModsMenuProbeState.pageOriginX, &originX, sizeof(originX));
            std::memcpy(&g_NativeModsMenuProbeState.pageOriginY, &originY, sizeof(originY));
        }
    }

    // 第二版：自动驱动。只要已经在菜单里（`g_MenuManager` 非空），就自己把原生页
    // 开起来 —— 第一版挂在组合键上，而"猜对按键"这件事本身就是风险（真机已证实会猜错）。
    if (menuManagerOk && g_AutoStarted == 0) {
        g_AutoStarted = 1;
        g_NativeModsMenuProbeState.manualMode = 1;
        g_NativeModsMenuProbeState.initResult = kInitNotTried;
        g_NativeModsMenuProbeState.renderCalls = 0;
    }
    // 推进"我们自己的那一格" + 把引擎索引夹回 0..4。
    // 位置：整体早于引擎自己的 `Manager::Update`（本回调在 `Orig` 之前）⇒ 我们写进去的索引这一帧就被读到。
    // 先按"局内进出"作废/重载那一行的贴图（在 `ModRowUpdate` 之前 ——
    // 后者门控在"选择界面"上，而进局内时状态**不变**，靠它自己的分支永远等不到这一刻）。
    ModRowInvalidateImageOnGameTransition(*module);
    {
        const std::uintptr_t thunkForRow = LuaRuntime::InputIsActionPressedThunk();
        if (thunkForRow != 0) {
            ModRowUpdate(*module, reinterpret_cast<ActionQueryFn>(thunkForRow));
        }
    }
    // 状态 16（模组页）期间由我们驱动那一页。与上面同一时机 —— 都在引擎
    // `Manager::Update` 之前，所以"我们这一帧切的状态"引擎这一帧就按新状态分派。
    {
        const std::uintptr_t thunkForPage = LuaRuntime::InputIsActionPressedThunk();
        if (thunkForPage != 0) {
            ModsPageUpdate(*module, reinterpret_cast<ActionQueryFn>(thunkForPage));
        }
    }
    g_NativeModsMenuProbeState.modsPageStateCode = isaac::runtime::kModsPageState;

    if (g_NativeModsMenuProbeState.manualMode == 1 &&
        g_NativeModsMenuProbeState.initResult == kInitNotTried &&
        TryPrepareModsVector(*module)) {
        // `TryPrepareModsVector` 会在"发现结果还没出来"时返回 false，把 `Init` 推到后面的帧 ——
        // 开机后主菜单可能比模组扫描先出现，而那张表只会写一次，赌错整轮真机就白跑了。
        TryInitManualPage(*module);
    }

    const std::uintptr_t thunk = LuaRuntime::InputIsActionPressedThunk();
    if (thunk == 0) {
        g_NativeModsMenuProbeState.lastFailure = kFailureInputUnavailable;
        return;
    }
    const auto query = reinterpret_cast<ActionQueryFn>(thunk);
    if (g_UpdateCount % kScanEveryNthUpdate == 0) {
        ScanInput(query);
    }

    // 组合键（ZR+ZL 同时按住，**任一手柄号**答是即算按下）⇒ 开关"手动画原生页"。
    // 自动驱动已经把它打开了，所以这里的作用是"能关掉 / 再打开"。
    const bool item = HeldByAnyone(query, kActionItem);
    const bool pill = HeldByAnyone(query, kActionPillCard);
    const bool itemEdge = Edge(&g_LastItem, item);
    const bool pillEdge = Edge(&g_LastPillCard, pill);

    if (item && pill) {
        if (g_ComboLatched == 0) {
            g_ComboLatched = 1;
            const std::uint32_t next = g_NativeModsMenuProbeState.manualMode == 0 ? 1U : 0U;
            g_NativeModsMenuProbeState.manualMode = next;
            g_NativeModsMenuProbeState.initResult = kInitNotTried;
            g_NativeModsMenuProbeState.renderCalls = 0;
        }
        return;
    }
    g_ComboLatched = 0;

    if (itemEdge) {
        const std::uint32_t next =
            (g_NativeModsMenuProbeState.state + 1U) % (kLastState + 1U);
        g_NativeModsMenuProbeState.state = next;
        ++g_NativeModsMenuProbeState.presses;
        ApplyState(*module, next);
        return;
    }
    if (pillEdge) {
        const std::uint32_t current = g_NativeModsMenuProbeState.state;
        const std::uint32_t next = current == 0 ? kLastState : current - 1U;
        g_NativeModsMenuProbeState.state = next;
        ++g_NativeModsMenuProbeState.backPresses;
        ApplyState(*module, next);
    }
}

// `Menu_Title::Render` 入口中继的回调。
//
// 形状：入口桩是尾调用（`br x16`），所以本回调以 `Menu_Title::Render` 的身份运行、
// `ret` 直接回到游戏的调用方 —— ABI 必须与目标一致：`(this)`，返回 void。
//
// 顺序（先跑原函数，再画我们的页）：这样我们的页画在标题菜单之上，而且 `MenuManager::Render`
// 后续那十几个页面的 `Render` 大多会因自己的可见位是 0 而整页跳过（各页自带门控）。
extern "C" void NativeModsMenuTitleRenderRelayCallback(void* self) {
    using RenderFn = void (*)(void*);
    const auto original = isaac::runtime::engine_call::AsFunction<RenderFn>(__atomic_load_n(&g_TitleRelayOriginal,__ATOMIC_ACQUIRE));
    if (original != nullptr) {
        original(self);  // 1) 标题菜单照常画（与没挂钩时逐帧等价）
    }
    // 2) 紧接着，在**同一渲染上下文**里画我们的原生页。
    if (g_NativeModsMenuProbeState.manualMode == 0 ||
        g_NativeModsMenuProbeState.initResult != kInitOk || g_MenuModsRender == 0) {
        return;
    }
    // ⚠️ 必须自己门控状态：`MenuManager::Render` 每帧无条件调所有页面，`Menu_Title::Render`
    // 自身没有状态判断 ⇒ 不门控的话"切到存档界面也照画"。验收判据之一是"离开标题画面不再出现"。
    //
    // 起多一处：状态 16（模组页）也要画。引擎自己的渲染清单里没有模组页
    // （`MenuManager::Render` 每帧调的 15 个页面里没有它），所以这一帧就是那个页面的唯一画手。
    // （用户要求）：「标题界面的那个模组界面可以去掉了」——
    // 入口已经接活（在「选择」界面按确认就进模组页），标题画面上那张"演示用"的纸就不再画了。
    // ⇒ 现在**只有状态 16 才画**。
    const std::uint32_t engineState = g_NativeModsMenuProbeState.menuState;
    const bool onModsPage = isaac::runtime::ModPageIsActive(engineState);
    if (!onModsPage) {
        return;
    }
    // 进页面第一帧先不画 —— 那时"位置"还没算出来（要等第一帧的 `Render`
    // 把引擎的滚动值写好才算得准），照旧位置画会闪一下（画在上一轮停稳的位置）。
    // 第一帧只显示背景那条菜单，正好是过渡刚开始该有的样子。
    if (g_ModsPagePositionSet == 0) {
        return;
    }
    reinterpret_cast<RenderFn>(g_MenuModsRender)(g_ManualObject);
    ++g_NativeModsMenuProbeState.renderCalls;
    if (onModsPage) {
        ++g_NativeModsMenuProbeState.modsPageRenderCalls;
    }
    // 渲染回调里不再清失败码 —— 上一版每帧都写 0，结果
    // "`ApplyState` 的守卫没过"这种真失败在读数里显示成"没有失败"，白花了一轮真机才定位。
}

namespace {

// 安装入口中继（模块初始化线程、游戏主循环尚未开始）。
// 逐字节比对入口 → 不符就只记失败码、一个字节都不写（判定由入口中继自己做，单一实现处）。
void InstallTitleRenderRelay(const TargetModule& module) {
    if (g_TitleRelayTried != 0) {
        return;
    }
    g_TitleRelayTried = 1;
    std::uintptr_t target = 0;
    if (!Guarded(module, kMenuTitleRenderOffset, kMenuTitleRenderExpected, &target)) {
        g_NativeModsMenuProbeState.titleRelayState = 2;
        g_NativeModsMenuProbeState.titleRelayFailure = kFailureTitleRelayGuard;
        g_NativeModsMenuProbeState.lastFailure = kFailureTitleRelayGuard;
        return;
    }
    const bool installed = isaac::runtime::relay::TryInstallEntryRelayWithPublisher(
        target, kMenuTitleRenderExpected.data(),
        isaac::runtime::engine_call::AddressOfFunction(&NativeModsMenuTitleRenderRelayCallback),
        PublishProbeOriginal, &g_TitleRelayOriginal);
    g_NativeModsMenuProbeState.titleRelayState = installed ? 1U : 2U;
    g_NativeModsMenuProbeState.titleRelayFailure =
        installed ? 0U : isaac::runtime::relay::LastFailure();
    if (!installed) {
        g_NativeModsMenuProbeState.lastFailure = kFailureTitleRelayGuard;
    }
}

}  // namespace

void NativeModsMenuProbeInstallRelay(const TargetModule& module) noexcept {
    InstallTitleRenderRelay(module);
    InstallModRowRenderRelay(module);
    // 我们那一格的确认只归我们管（引擎不许替我们去开统计/选项）。
    InstallSetStateRelay(module);
}

}  // namespace isaac::runtime::probe

#endif  // EXL_PROBE_BREAK && EXL_PROBE_BREAK_NATIVE_MODS_MENU
