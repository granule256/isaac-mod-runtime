// 生产版：「模组」那一行 + 模组页（换字体那段接线已按真机结论撤掉）。设计与纪律见同名 `.hpp`。
//
// **行为真值源**：`runtime/source/probe/native_mods_menu_probe.cpp`（3021 行，真机验收过一轮）。
// 本文件按它的行为重写、去掉诊断，逐处保留"为什么这么做"的依据；几处刻意的差别写在 `.hpp` 里，
// 并在下面各自的位置重复一遍理由。
//
// 本 TU **不做编译期门控**：三个入口回调必须常编存在（`entry_relay_hook_adapter.cpp` 的
// `RegisterEntryRelayCallbacks` 无条件取它们的地址）。探针与生产的互斥在**安装**这一层：
// 探针构建里由 `hook_manager.cpp` 的 `SkipOptionalHooksPredicate` 跳过这三个挂点，
// 探针自己那套 `TryInstallEntryRelay` 照旧生效。
//
// ## 和引擎打交道的方式（2026-09-24 批次 105 建内存侧、批次 108 补齐调用侧）
//
// 本 TU 的**引擎读、引擎写、整数↔指针转换全部走引擎内存访问层**
// （`runtime/src/infrastructure/memory/engine_field_access.hpp`）：回绕检查、可读/可写判定、
// 取值与落值只在那一个地方发生，这里只写"读/写哪个对象的哪个偏移"。
//
// **"调一个引擎函数"走引擎调用层**（`runtime/src/infrastructure/call/engine_call_access.hpp`，
// 批次 108）：本 TU 的 `VerifiedEntry<Fn>(...)` 一次做完"范围 + 可读 + 逐字节核对序言 +
// 转成带签名的函数指针"，任一条不过就给 `nullptr`。**调用点里不再出现 `reinterpret_cast<签名>`**。
//
//   * 为什么（内存那一半）：诊断文档 `docs/架构诊断-框架为什么失效-20260924.md` 的结论 ——
//     一处**无守卫的写**把内存写坏 ⇒ 之后抛 C++ 异常时栈已坏 ⇒ libgcc 展开失败直接 `abort`
//     ⇒ **静默卡死**。访问层的存在意义就是让"写之前先确认可写"不可能被绕过。
//   * 为什么（调用那一半）：偏移写错会**调到别的函数头上**去改引擎状态，事后极难反查
//     ⇒ "逐字节核对通过才把地址交出去"必须收成**一个名字**，而不是每个调用点各自记得。
//   * **唯一刻意不迁的一处**：`char*` → libnx `u8*` 的类型别名转换
//     （`GameFileReader::ReadTextFile` 的实参）—— 它既不碰引擎内存、也不产生"能调的地址"。

#include "mod_menu_native.hpp"

#include "game_file_reader.hpp"
#include "application/mod/content_mount_service.hpp"     // `SessionContentMountService()`（[24] 那一格）
#include "domain/runtime/run_taint_marker.hpp"           // 批次 120：存档分区里那个"污染过"标记
#include "ports/save_file_port.hpp"                      // `SessionSaveFilePort()`（批次 120 的持久化）
#include "infrastructure/call/engine_call_access.hpp"    // 引擎调用层（108 起本 TU 调引擎都走它）
#include "infrastructure/memory/engine_field_access.hpp"  // 引擎内存访问层（105 起本 TU 的引擎读写都走它）
#include "infrastructure/relay/entry_relay_binding.hpp"  // `Original<>`（挂点记下的原函数入口）
#include "interfaces/lua/font_api.hpp"                   // `LastFontLoadWordForProbe()`（[25] 那一格）
#include "interfaces/lua/mod_menu_api.hpp"               // 发现结果 + 开关服务
#include "lua_runtime_state.hpp"                         // `InputIsActionPressedThunk()`
#include "mod_menu_entry_row.hpp"                        // 那一列"多插一格"的算术（有宿主门禁）
#include "mod_page_entries.hpp"                          // 条目布局（有宿主门禁）
#include "mod_page_nav.hpp"                              // 模组页自己的算术（有宿主门禁）
#include "mod_page_runtime_sources.hpp"                  // 发现结果 → 条目来源
#include "module_finder.hpp"                             // `FindTargetModule()`
#include "runtime_constants.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <optional>

// 挂载点重建中继的两个观测计数（[22]/[23] 那两格）。定义在
// `source/content/rebuild_content_mount_points_relay.cpp`，是 `extern "C"` 的具名函数
// （**只读**：它们只回一个计数，不改任何状态）。
extern "C" std::uint32_t IsaacModRuntime_RebuildContentMountPointsRelayFiredCount();
extern "C" std::uint32_t IsaacModRuntime_RebuildContentMountPointsRelayFailureCount();

//: 引擎内存访问层的短别名（批次 105）。只为调用点可读：调用点要写的是"哪个对象的哪个偏移"，
//: 一长串限定名会把那件事淹掉。**别名不改变层里的任何判定**（它只是同一个命名空间的另一个名字）。
namespace engine_memory = isaac::runtime::engine_memory;

//: 引擎调用层的短别名（批次 108），理由同上。调用点要写的是"调哪个引擎入口"。
namespace engine_call = isaac::runtime::engine_call;

namespace isaac::runtime::modmenu {

//: 状态面本体。**外部链接 + 固定符号名**：读数工具按裸名 `g_ModMenuState` 取它
//: （放进匿名命名空间就会让 `nm` 查不到 —— 2026-09-19 的 D6 事故）。字段顺序见 `.hpp`。
//:
//: ★★ 为什么用**块形式** `extern "C" { ... }` 而不是 `extern "C" State x = {...};`：
//: 后者在 gcc 下报 `'g_ModMenuState' initialized and declared 'extern'`，而本构建是 `-Werror`
//: ⇒ 直接编译失败（2026-09-23 批次 077 实测）。块形式同样给**C 语言链接**（符号名仍是裸名
//: `g_ModMenuState`，不带命名空间前缀、不做名称改编），但不会被判成那条告警 ——
//: **别改回去**。判据见 `runtime/tests/test_mod_menu_native_production.py`。
extern "C" {
State g_ModMenuState = {
    1,  // [0] armed：本功能编进来了（生产构建恒 1）
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0,  // [22]..[25]：2026-09-23 加的观测四格（每帧由 `ModMenuNativeUpdate` 填）
    0,           // [26] 开模组禁成就（每帧写 1；见常量那段注释）
    0, 0, 0, 0,  // [27]..[30]：metadata.xml 三种结果 + 开着的真实模组个数（每帧填）
    0,           // [31] 成就 #4（打过妈妈）解锁没（每帧问一次）
    0,           // [32] 成就位数组抽样（id 0..3 各一字节，自证位置）
    0,           // [33] 我们写进 `PersistentGameData+0x1` 的只读位（真正挡成就的那一位）
    0,           // [34] 每帧 +1 的计数器（证明我们的更新还在跑）
    0, 0, 0, 0, 0,  // [35]..[39]：成就闸门中继的调用/拦截/解锁/最后成就号/原函数缺失（2026-09-24 加）
    0,           // [40] 处于**启用状态**的真实模组个数（批次 107 加；判据就是它，见 `.hpp`）
    0, 0, 0, 0,  // [41]..[44]：发现清单自证四格（批次 116 加：条数 / 启用位图 / 加载位图 / 发现跑过没）
    0, 0, 0, 0, 0, 0,  // [45]..[50]：局内单向闩锁六格（批次 117 加：闩锁值 / 置位次数 /
                       //   清零次数 / 上次清零来源 / `GameExit` 被调到几次 / 闩锁可用否）
    0, 0, 0,           // [51]..[53]：批次 118 加：在一局里吗 / 边沿写位调用几次 / 边沿写位的结果
    0, 0,              // [54]..[55]：批次 119 加：出局时留存的污染 / 把留存接回来过几次
    0, 0,              // [56]..[57]：批次 120 加：存档分区里那个标记（我们认为它是几 / 读写失败几次）
};
}  // extern "C"

} // namespace isaac::runtime::modmenu

namespace {

using isaac::runtime::modmenu::g_ModMenuState;

// ─────────────────────────────────────────────────────────────────────────────
// 偏移与入口指纹
// ─────────────────────────────────────────────────────────────────────────────
//
// 来源：探针 `native_mods_menu_probe.cpp`（逐字节照搬，一个数字都没改）。
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
//: `g_Manager` 里"引擎自己那份模组表"的偏移（与 `kManagerToModManagerOffset` 同一个数）。
constexpr std::uintptr_t kManagerModsVectorOffset = 0x36800;
//: 模组总开关（PC 的"启用模组"）：`g_Manager` 上的一个字节。`Menu_Mods::Render` 读它选颜色；
//: 为 0 时它**只用一个颜色画所有行**（不读条目自己的启用位）⇒ 切换开关在屏幕上看不出来。
constexpr std::uintptr_t kManagerModsEnabledOffset = 0x36519;

// ── 「开模组 ⇒ 禁成就」（2026-09-23 批次 084，取证后实现）────────────────────────
//
// `g_Manager + 0x36D4D` 的一个字节 = **本局不给成就**（1 = 禁、0 = 允许）。逐字节证据：
//   * `Game::StartDebug`（`0x34FAF0`）：`mov w10,#1` → `mov/movk w11,#0x36D4D`
//     → `strb w10,[x0,x9]` ⇒ **调试局把这一位置 1**（调试局不给成就，符合直觉）；
//   * `Manager::check_game_data_modified()`（`0x3FA980`，整个函数只有三行）：
//     `mov/movk w8,#0x36D4D` → `strb wzr,[x0,x8]` ⇒ **无条件写 0**。
//     ⇒ **Switch 移植版把"游戏数据被改过"这项检查砍成了恒假**（PC 上它会因为"开了模组"
//       而置 1）⇒ 所以现在模组开着也照样给成就。
//   * **读它的四处**（都在开局那一刻，抄进本局状态）：
//     `Game::Start`（`0x34E584`）、`Game::StartDailyChallenge`（`0x34EB88`）、
//     `Game::RestoreState`（`0x34F12C`）、`Game::StartFromRerunState`（`0x34F714`）
//     —— 全是 `ldrb w?, [x?, x9]` 形式，且都在函数开头附近。
//   ⇒ 我们只要**在每次开局之前**把它置 1 就行；这里选择**每帧写一次**（一个字节的代价，
//     免去"谁什么时候会把它清回 0"这个不确定问题）。
//   * 引擎自带的 `Manager::AchievementUnlocksDisallowed(bool)`（`0x3FA978`）我们**不调**：
//     它是个空实现（`mov w0,wzr; ret`），真正写这一位的代码在它后面那个函数里；
//     而 `Game::AchievementUnlocksDisallowed()`（`0x34EAA8`）问的是 **Seeds**（特殊种子），
//     与模组无关 —— 两条都不是我们要的语义。
//
// **策略（用户 2026-09-23 定案：最忠实 PC）**：**只要这个运行时在跑（= 用了模组）就置 1**。
// 代价要说清楚：**这样就用不了成就了** —— 这正是 PC 的语义，也是这条功能的意义。
constexpr std::uintptr_t kManagerAchievementsDisallowedOffset = 0x36D4D;

// ── 「打完妈妈之前用模组 ⇒ 锁成就」：**一比一照 PC 的判据**（2026-09-23 批次 086）──────
//
// 用户口径（原话的意思）："PC 上打完妈腿**前**使用模组的话无法解锁成就，打完过后使用模组
// 都不会有什么影响"。**去 PC 那边查证过，用户是对的**：
//
// * PC/Afterbirth+ 里那条判据是 `ModManager::AchievementsLocked()` —— 逐条反汇编
//   （`AfterbirthPlus.nro` 有符号，`0x250CB8`）：
//   ```
//   遍历模组列表（`this+0x60` 的 begin/end）：任一模组的 `+0x121` 字节非 0 ⇒ 进入下面这支
//       读 `g_Manager` → `*(g_Manager)` → `add x0, x8, #0x18`（= **PersistentGameData 嵌在
//       `Manager+0x18`**）→ `mov w1, #4` → `bl PersistentGameData::Unlocked(eAchievement)`
//       → `eor w8, w0, #1` ⇒ **返回 `!Unlocked(4)`**
//   列表为空 ⇒ 返回 0（没有模组就不锁）
//   ```
//   ⇒ **PC 的规则 = "有任意模组开着" 且 "成就 #4 未解锁" ⇒ 锁成就。**
// * **成就 #4 是什么**：`resources/achievements.xml` 里 id=4 =
//   `You unlocked "The Womb" -Chapter 4- Mother sleeps` ⇒ **打过妈妈（解锁"子宫"那一章）**。
//   ⇒ 与用户说的"打完妈腿"**完全对上**。
//
// **Switch 侧要用的入口**（都在 `Repentance.nro` 里，逐字节核过）：
//   * `g_Manager` 的 GOT 槽 `0xAAC648`（= 我们已有的 `kManagerSlotOffset`）；
//   * `PersistentGameData` 嵌在 **`Manager + 0x18`**（证据：`0x3C10D4` 那段
//     `ldr x8,[x8,#0x648]; ldr x8,[x8]; add x0,x8,#0x18; bl Unlocked`）；
//   * `PersistentGameData::Unlocked(eAchievement)` @ `0x439654`（x0 = `Manager+0x18`，
//     w1 = 成就号，返回 w0 = bool）。
constexpr std::uintptr_t kManagerPersistentGameDataOffset = 0x18;
//: 成就解锁位在 `PersistentGameData + 0x28`，**按成就号逐字节索引**
//: （证据：`Unlocked` 自己的实现 `0x439678`：`add x8,x0,x8; ldrb w8,[x8,#0x28]`）。
constexpr std::uintptr_t kPersistentAchievementArrayOffset = 0x28;
//: ★★ 为什么**不调 `PersistentGameData::Unlocked()`**：它不是"历史上有没有解锁过"的纯查询 ——
//: 持久位为 0 时它会再去看**本局**的状态（`0x43968C` 起：读 `Game+0x26FA8D` 的 word 与字节，
//: 非 0 就照样返回 true）。2026-09-23 真机实测过这一点：用户存档里成就 #4 的持久字节是 **0**
//: （没打过妈妈），而 `Unlocked(4)` 返回 **true** ⇒ 我们那版判据判反了、成就照给。
//: PC 的 `AchievementsLocked()` 是在**开局那一刻**问的（那时本局状态还没建立）⇒ 等价于直接读持久位。
//: ⇒ 这里直接读那个字节，**并且把数组抽样也记进读数**（`[32]`）自证位置没读错。
constexpr std::uintptr_t kPersistentAchievementArrayOffsetProbe = 0x28;
//: 成就 #4 = `You unlocked "The Womb" -Chapter 4- Mother sleeps` ⇒ **打过妈妈**。
constexpr std::uint32_t kAchievementWomb = 4;
//: ★★ **真正的判据**：`PersistentGameData + 0x1` 那个字节 = "只读/不许解锁成就"。
//:
//: 为什么它才是判据（2026-09-23 真机定位，之前几版都没打到点上）：
//:   * `PersistentGameData::TryUnlock(eAchievement)`（`0x4393D0`）**只查两个东西**：
//:     `ldrb w8,[x0,#0x1]; cbnz w8 → 直接返回不解锁`（+0x1 非 0 ⇒ 拒绝），
//:     以及"这一位是不是已经解锁了"。**它不看 `Manager+0x36D4D`**。
//:   * 而 `Manager+0x36D4D` 只在**开局那一刻**被 `Game::Start` 抄进本局状态（`Seeds+0x8`），
//:     之后 `Game::Start` 再根据"本局该不该禁"去调 `PersistentGameData::SetReadOnly(bool)`
//:     （`0x34E6F0`，`w1=1` 的那条路 = 禁）。
//:   * **Switch 移植版把这条链掐断了**：`Manager::AchievementUnlocksDisallowed(bool)` 是**空实现**
//:     （`0x3FA978` = `mov w0,wzr; ret`），`Manager::check_game_data_modified()` 又**无条件写 0**
//:     且**没有任何调用点**（死代码）⇒ 真机上那个只读位**永远是 0**。
//:   * 真机实证：`Game::AddShopVisits`（`0x35AF84`，买东西触发的那条）**直接尾调用**
//:     `TryUnlock(成就 #379)`，中间**没有任何"禁不禁"的检查**；而现场读数里
//:     `PersistentGameData+0x1 = 0` ⇒ 照样解锁（用户 2026-09-23 复现的那次）。
//:   ⇒ 所以除了写 `Manager+0x36D4D`（保留，它与 PC 的链一致、也无害），**还必须把这个只读位设上**。
//:
//: 安全性：`PersistentGameData::Save()`（`0x433E44`）读的是 `this+0x10` 的位、**不是这一位**
//: ⇒ 设它**不会锁掉存档**，只挡住"新解锁成就"。
constexpr std::uintptr_t kPersistentReadOnlyOffset = 0x1;
//: `PersistentGameData::Unlocked(eAchievement)` 的入口 + 16 字节守卫。
constexpr std::uintptr_t kPersistentGameDataUnlockedOffset = 0x439654;
constexpr std::array<std::uint8_t, 16> kPersistentGameDataUnlockedExpected = {
    0x3F, 0x08, 0x00, 0x31, 0x80, 0x00, 0x00, 0x54,
    0x41, 0x01, 0xF8, 0x37, 0x3F, 0xF4, 0x09, 0x71,
};
//: 字体对象在 `g_Manager` 里的偏移（`Menu_Mods::Render` 画每一行的 `"%d.%s"` 用的就是它：
//: 反汇编里 `add x25, x8, #0x117120`）。**本批起只读不写**（见下面"引擎字体对象"那一段注释）。
constexpr std::uintptr_t kManagerFontOffset = 0x117120;
//: `MenuManager::eState` 在 `MenuManager+0x38`（`Update` 里 `ldr w8,[x19,#0x38]`）。
constexpr std::uintptr_t kMenuManagerStateOffset = 0x38;
//: 页面**共享的画布原点**：`MenuManager+0x3c` 起的那两组 float。引擎每个页面 `Render` 都是
//: `ldp w9, w8, [MenuManager, #0x3c]` 读出这两组 float，再与页面自己的位置相加
//: ⇒ "页面画在哪" = 这个偏移 + 页面自己的偏移。它朝 `get_target_offset()` 收敛，而那个函数算的是
//: `((画面宽-480)/2, (画面高-270)/2)` ⇒ **页面坐标空间是 480×270，可见屏幕比它小、居中裁切**。
constexpr std::uintptr_t kMenuManagerCanvasOffset = 0x3c;
//: `IsaacRepentance::WIDTH` / `HEIGHT` 的 GOT 槽（`get_target_offset` 里就是这么取的：
//: `adrp x8,0xaac000; ldr x8,[x8,#0x650]; ldr s0,[x8]` ⇒ 槽里放的是**指向 float 的指针**）。
constexpr std::uintptr_t kWidthSlotOffset = 0xAAC650;
constexpr std::uintptr_t kHeightSlotOffset = 0xAAC658;

// ── 那一列（选择界面）：`Menu_Game` 那一屏 ─────────────────────────────────────
//
// 三条引擎事实（都反汇编核过）：
//   ① `Menu_Game::Render` 对每行做 `GetLayer(i); s0=[layer+0x48]; s0+=k; [layer+0x48]=s0`
//      ⇒ **`图层+0x48` 是每行自己的 X 偏移、`+0x4C` 是 Y**，我们也能写（"把下面几行挪下去"的抓手）；
//   ② 光标帧由 `Menu_Game::Update` 设，**Render 自己不碰**；而我们的中继在 Render 入口
//      ⇒ **我们这一帧设的帧号，在本帧的绘制里一定生效**；
//   ③ 引擎只认 5 项（`cmp w8,#4`）。**我们绝不让索引越界**：写回的是**行号**、再夹在 0..4，
//      第 6 格（我们最后一格）的光标靠"我们自己设帧号"实现 —— 所以不存在"越界查表"的风险。
constexpr std::uintptr_t kMenuGamePageOffsetInMenuManager = 0x813A0;
constexpr std::uintptr_t kPageSelectedIndexOffset = 0x4;
constexpr std::uintptr_t kPagePositionOffset = 0x8;
//: 页面对象里的 ANM2（`Menu_Game::Render` 里 `add x21, x19, #0x10` 之后交给 `ANM2::Render`）。
constexpr std::uintptr_t kPageAnm2Offset = 0x10;
//: ANM2 对象里的**图层数**（`int`）。证据：`ANM2::GetLayer(int)` 与 `ANM2::Load` 都读它当上界
//: （`ldr w8,[x20,#0xb0]; cmp w8,w19; b.gt` 之后按 `[x20,#0xa8] + index*0xB0` 取图层）。
//: ⚠️ **`GetLayer` 越界时不返回空指针**（它只打一条日志、照样算出界地址），所以判"有没有那一层"
//: 必须读这个计数，**绝不能**用 `GetLayer(12)` 是不是空来判 —— 那是读越界内存。
constexpr std::uintptr_t kAnm2LayerCountOffset = 0xB0;
//: 引擎自己那份菜单动画在"补回 `Item6`"之后的图层数（原版 12 层 + 我们补回去的那一层）。
//: 补层工具与门禁见 `tools/gamemenu_mod_row.py --emit-menu-anm2`。
constexpr std::uint32_t kMenuGameLayerCountWithModRow = 13;
//: `MenuManager::eState` 的"选择界面"那一格（`Menu_Game`）。
//: 静态表：3 = Menu_Game（`MenuManager+0x813A0`），与 `Menu_Game::Update` 开头的 `cmp w8,#0x3` 互证。
constexpr std::uint32_t kGameMenuState = 3;
//: 引擎确认键跳表里"我们那一格之后"的那两页（用来做保险：见 `SetState` 中继）。
//: 静态表：9 = Stats、10 = Options。
constexpr std::uint32_t kStatsState = 9;
constexpr std::uint32_t kOptionsState = 10;

// ── 动作号 ────────────────────────────────────────────────────────────────────
//
// `0x13`/`0x14` 是 `Menu_Game::Update` 里上下键用的动作号（`IsActionPressed(0x13/0x14, -1, 0)`）。
// `0x0E` = `ACTION_MENUCONFIRM`、`0x0F` = `ACTION_MENUBACK`（两条可复核的依据：
// `Menu_Title::Update @0x41A4F0` 里 `mov w1,#0xe` ⇒ `SetState(2)`；`Menu_Game::Update` 的
// "那一行确认"分支在 `0x40D730` 也是 `mov w1,#0xe`，而 `0x40d890` 处是 `mov w1,#0xf`）。
// ⚠️ 探针第一版把确认写成了 `0x0F`（那是返回），一直没暴露是因为当时只记数、没接页面。
constexpr std::uint32_t kActionUp = 0x13;
constexpr std::uint32_t kActionDown = 0x14;
constexpr std::uint32_t kActionConfirm = 0x0E;
constexpr std::uint32_t kActionBack = 0x0F;
//: "任一控制器答'是'"：游戏自己的菜单代码用的就是这个值（`Menu_Title::Update @0x41A4F0`
//: 里是 `mov w2, #-1`）。**不能只问手柄号 0** —— 真机上出现过 33（项目历史结论）。
constexpr std::uint32_t kAnyController = 0xFFFFFFFFu;
constexpr std::uint32_t kScanControllers = 64;

//: 兜底那一行画什么。**必须用 ASCII**：游戏自带字体没有中文字形（探针实测：画中文一片空白），
//: 而周围五行烤在图里的字本来就是英文。带中文字形的那份字体留给**模组页里的模组名**用。
constexpr char kModRowLabel[] = "MODS";
//: 兜底那行字的颜色 = **纸上烤的那套字**的墨色（把 `gamemenu.pcx` 解出来取墨迹像素，最暗/最常见
//: 的是 `(55,43,45)` 深褐，不是纯黑）。
//: ★ 探针里这一处是**纯红**：那是探针的信号（屏幕上看到红色 MODS = 贴图那条链还断着），
//:   而生产版走兜底是**正常形态**（覆盖层没装/被回退），颜色必须与纸上的字一致，红色是错的。
constexpr float kModRowTextColor[4] = {55.0F / 255.0F, 43.0F / 255.0F, 45.0F / 255.0F, 1.0F};
//: 兜底字的位置：x 对齐引擎自己那几行的文字左边（行图框 x≈185，烤的字在框内 +7 左右）。
constexpr float kModRowTextX = 192.0F;
//: 万一布局还没定（语言没取到）时的文字锚点 —— 048 批真机验过的那个值。
constexpr float kModEntryTextYFallback = 124.0F;
//: 字号 = **量出来的字高** ÷ 当前字体的行高（换字体自动适应，不用手调）。
//: 兜底用的"美术里那行字高"：中文那一列量出来约 28 格。
constexpr float kModRowArtTextHeight = 28.0F;
//: 行高拿不到（守卫不过）时的兜底缩放。
constexpr float kModRowTextScaleFallback = 2.0F;

// ── 模组页（引擎状态 16）──────────────────────────────────────────────────────
//
// **为什么是状态 16**：PC 上"选模组"就是让引擎切到状态 16；Switch 版只把这一格从
// `MenuManager::Update` 的分派表（0..15）与 `MenuManager::Render` 的页面清单里删了，
// 页面代码（`Menu_Mods` 六个方法）与资源都还在（证据见 `mod_page_nav.hpp` 的注释）。
//
// **为什么自己维护输入、不调引擎的 `Menu_Mods::Update`**：它按确认会往模组目录写/删
// `disable.it`，而卡上模组目录就在 **romfs 覆盖层**里 —— 那正是"写覆盖层 ⇒ 下次启动崩"的雷区。
// ⇒ 页面只借引擎的 `Render`，输入与开关状态由我们维护（`mod_page_nav.hpp`，有宿主门禁）。
//
// 条目表要的数据结构（静态已确认，见 `mod_page_entries.hpp`）：
//   * `g_Manager + 0x36800` 起三个字 = `std::vector<条目指针>` 的 begin / end / cap；
//   * 每个条目 `+0x18` 是 libc++ `std::string`（长串形态）、`+0x138` 启用位、`+0x13a` "旧版"位。
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
//: `Menu_Mods::Reset()`：进入模组页时调一次（把选中项归零、重读 ModManager 指针）。
//: 引擎自己的 `MenuManager::SetState` 切页时会替各页面做这件事，但**它没有状态 16 那一格**
//: ⇒ 这一下得我们替它做（等价于 PC 的 `SetState(模组)` 里那次 `Reset`）。
constexpr std::uintptr_t kMenuModsResetOffset = 0x4101B4;
constexpr std::array<std::uint8_t, 16> kMenuModsResetExpected = {
    0xFD, 0x7B, 0xBE, 0xA9, 0xF3, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF3, 0x03, 0x00, 0xAA,
};

// ── 换语言：**不能照抄引擎那套全局回收**（2026-09-23 批次 079 → 079b 撤回）──────────────
//
// 引擎里确实有一整套换语言协议 —— `PerformLanguageSwitch(eLanguage)`（`0x3B39C0`），顺序：
//   ① `MenuManager::PreLanguageSwitch()`（对每个页面调 `页面::PreLanguageSwitch()`，紧接着 `页面::Reset()`）
//   ② `AnmCache::FreeUnreferencedImages()` + `AnmCache::FreeUnreferencedEntries()`
//   ③ `Manager::SetLanguage(eLanguage)`（重建语言挂载点）
//   ④ `MenuManager::PostLanguageSwitch()`（对每个页面调 `页面::PostLanguageSwitch()`）
//   ⑤ `Manager/Game::PostLanguageSwitch()` + `MenuManager::ResetCharacterMenu()`
// 而 `Menu_Mods` 自己也有这两个钩子：`PreLanguageSwitch`（`0x41021C`）= `add x0,x0,#0x10; b ANM2::Reset`；
// `PostLanguageSwitch`（`0x410224`）= 与 `Init` 同一套重新加载（不碰构造函数、不动页面位置）。
// 另外 `g_AnmCache` 是 `std::__1::map<uint32_t, Entry2>`、键 = `AnmCache::FNHash(路径串)`（`0xF4E8`）
// = **路径串一样就分不出语言**，这就是"换语言后排版不跟着换"的根因（贴图会跟着换，因为
// `load_graphics` 每次都按当前挂载层重新解析精灵表）。
//
// ★★ **但第②步在我们的环境里不能调。** 079 试过（照抄三步：Pre → 两个 FreeUnreferenced → Post），
// 真机结果：模组页那个键盘图标的位置**修好了**，可是**EID 的信息显示被搞坏了** ——
// 用户原话"只要语言更换过进入游戏，EID 的信息显示就有问题，大部分信息都没有，
// 只有一个很浅的图标在闪烁"。机理：那两个函数按"引用计数为 0 就释放"办事，而**我们这一侧
// 有"引擎的引用计数看不见的持有人"**（Lua `Sprite` 家族与贴图桥的 shim；项目里已经记过一次
// `Game::Exit → AnmCache::FreeUnreferencedImages → 堆 free 断言`，见 `lua_runtime.hpp` 顶部那段），
// 于是引擎把 EID 还在用的贴图/动画当成"没人引用"给放掉了。
// ⇒ **代价对比是明确的**：EID 是实际功能，图标位置只是"同一次开机内换语言"才看得见的观感问题
//   ⇒ 撤掉那一步（079b）。留在这一段的目的是：**下一个人别再试同一个坑**；
//   真要修，得先把我们这侧的 shim 引用计数做对（或另找一条不放全局水的方法），
//   细节与判据见 `docs/改动日志-20260923.md` 的 079 与 `dist/change-archive-20260923/079-…/README.md`。
//: `MenuManager::SetModsOffset(int)`：把"模组页那一格"的滚动目标写成"第 n 条"。
//: 进页面时先调一次 `SetModsOffset(0)`，让那一格的 Y **立刻**变成确定值 —— 否则要等页面自己
//: `Render` 一次才拿得到它，而"算位置"就发生在那一帧之前。
//: ★ 真机实测（探针批次 064）：不先调的话，重启后第一次进来会**错位 1~2 秒**（读到 `Init` 的旧值
//:   -290，而实际是 -216，差 74 格）。
//: `Menu_Mods::PreLanguageSwitch()`（`0x41021C`）= `add x0,x0,#0x10; b ANM2::Reset` ——
//: **放开**这份动画（还掉缓存引用、清掉路径串、放掉图层持有的贴图引用）。
//: `Menu_Mods::PostLanguageSwitch()`（`0x410224`）= 按**当前**语言重新 `Load` + `Play("Main")` + …，
//: 与 `Init` 同一套动作，只是**不碰构造函数、也不动页面位置**。
constexpr std::uintptr_t kMenuModsPreLanguageSwitchOffset = 0x41021C;
constexpr std::array<std::uint8_t, 16> kMenuModsPreLanguageSwitchExpected = {
    0x00, 0x40, 0x00, 0x91, 0xBC, 0x7F, 0x09, 0x14,
    0xFF, 0x03, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
};
constexpr std::uintptr_t kMenuModsPostLanguageSwitchOffset = 0x410224;
constexpr std::array<std::uint8_t, 16> kMenuModsPostLanguageSwitchExpected = {
    0xFF, 0x03, 0x01, 0xD1, 0xFD, 0x7B, 0x02, 0xA9,
    0xFD, 0x83, 0x00, 0x91, 0xF4, 0x4F, 0x03, 0xA9,
};
//: `AnmCache::FreeUnreferencedEntries()`（`0x14F64`）/ `FreeUnreferencedImages()`（`0x156B4`）：
//: 回收"没人引用"的动画条目 / 贴图。★ 这两个是**全局**的，只在"照引擎自己的换语言协议"时调，
//: 而且调之前必须先把本页的引用放开（`PreLanguageSwitch`），否则清不掉那份旧语言的动画数据。
constexpr std::uintptr_t kAnmCacheFreeUnreferencedEntriesOffset = 0x14F64;
constexpr std::array<std::uint8_t, 16> kAnmCacheFreeUnreferencedEntriesExpected = {
    0xFD, 0x7B, 0xBC, 0xA9, 0xF7, 0x0B, 0x00, 0xF9,
    0xFD, 0x03, 0x00, 0x91, 0xF6, 0x57, 0x02, 0xA9,
};
constexpr std::uintptr_t kAnmCacheFreeUnreferencedImagesOffset = 0x156B4;
constexpr std::array<std::uint8_t, 16> kAnmCacheFreeUnreferencedImagesExpected = {
    0xFD, 0x7B, 0xBB, 0xA9, 0xFA, 0x67, 0x01, 0xA9,
    0xFD, 0x03, 0x00, 0x91, 0xF8, 0x5F, 0x02, 0xA9,
};
//: `g_AnmCache` 的 GOT 槽（`0xAAC6A0`）：**读一次就是对象地址**（引擎自己的写法是
//: `adrp x0,0xaac000; ldr x0,[x0,#0x6a0]` 之后直接当 `this` 用，只有一次取值）。
constexpr std::uintptr_t kAnmCacheSlotOffset = 0xAAC6A0;
constexpr std::uintptr_t kSetModsOffsetOffset = 0x3FF6F4;
constexpr std::array<std::uint8_t, 16> kSetModsOffsetExpected = {
    0x3F, 0x14, 0x00, 0x71, 0x8A, 0x00, 0x00, 0x54,
    0x08, 0x6B, 0xB8, 0x52, 0x00, 0x01, 0x27, 0x1E,
};

// ── ANM2 两个跳板 ─────────────────────────────────────────────────────────────
//
// `ANM2::GetLayer(int)` / `ANM2::SetLayerFrame(int,int)` 的**跳板**（引擎自己也是调这两个地址）。
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

// ── 引擎字体对象：**本批确认不再动它**（2026-09-23，批次 078）─────────────────────
//
// 077 曾把一份带中文字形的扩展字体（`font/…Extended12.fnt`，TeamMeat 字面的扩展版）
// 装进**引擎自己的**字体对象（`g_Manager + 0x117120`，也就是 `Menu_Mods::Render` 画每一行时用的那份），
// 为的是让中文模组名能画出来。**真机验收推翻了这个前提**：
// `Menu_Mods::Render`（`0x4107C4`）用的是**按字节**的那个重载 `Font::DrawStringScaled(char const*…)`
// —— 它把字符串里**每个字节**当一个字形编号；中文在 UTF-8 里是 3 字节、每字节 ≥ 0x80
// ⇒ 只会画出 3 个毫不相干的字形。引擎另有一套 UTF-8 家族（`DrawStringScaledUTF8` /
// `GetStringWidthUTF8`，先转 UTF-16），而**模组页没用它** ⇒ **换字体救不了中文**。
// 代价却是真的：多加载一份 2048×2048 × 2 页的字图集（约 32MB），观感也会变
// （换成扩展版后点阵画得略细，用户当场就看出来了）。
//
// ⇒ 本批**整个撤掉**换字体那段接线：这个对象现在只被**读**
// （兜底画字时取行高，见 `DrawRowLabel`），**一个字节都不写**。
// 中文模组名的问题改为"等真有中文名模组时单独立项"（见交接文档第五节 C）。
// 状态面里 `fontObjectWrites` 那一格就是这条纪律的载体：它数"我们改写过几次引擎字体对象"，恒 0。
//
// ⚠️ 路径仍然不许用 `font/CJK/LanaPixel.fnt`：它的图集背景是不透明黑，真机上被画成黑方块
// （探针第一版实测），比"没有中文"更糟。

// ── 页面摆放（探针批次 042/063/066 的结论）────────────────────────────────────
//
// **引擎自己的页面约定**：`titlemenu`/`saveselectmenu`/`statsmenu`/… 的内容全部落在
// `x∈[0,480]`、`y∈[0,270]` ⇒ **页面原点 = 一个 480 宽页面的左上角**。
// 而模组页那张纸的设计是**以原点为中心**的：纸 = `480×900 @(-240,-72)`；`Menu_Mods::Render`
// 里那句 `+200`（`mov w8,#0x43480000` = 200.0f）正是"把居中布局挪成页面框布局的那一下"。
// ⇒ 要让纸铺满页面框、上沿压在页面顶端，原点应当是 **(240, 72)**。
//
// ★★ 横向 173 = **按 PC 引擎自己的公式换算出来的**：把 PC 的 `isaac-ng.exe`（PE32，32 位）
// 反汇编后，画布偏移的收敛目标写得很清楚：`((屏幕宽−480)/2 + 家位置x, …)`，而 `MenuManager::Init`
// 给每个页面写的位置是**家位置取负** ⇒ 页面最终原点 = 居中量 + (200,0)。
//   * PC 屏幕铺满整个 480×270 画布 ⇒ 居中量 0 ⇒ 原点 (200,0)；
//   * Switch 屏幕只有 426×240 ⇒ 居中量 ((426−480)/2, (240−270)/2) = (−27,−15)
//     ⇒ 同一套布局换算到 Switch 上，横向应当是 200 − 27 = **173**。
// 纵向仍取 72（批次 042/056 真机验收过的值）：按公式应得 −15，但那会让纸的上沿跑出屏幕外
// ⇒ 纵向这一格的残差尚未定性，**以真机验收为准，不按公式硬套**。
constexpr float kPageBoxWidth = 480.0F;
constexpr float kModsSheetOffsetY = -72.0F;   // 纸相对原点的左上角 Y
constexpr float kModsRenderExtraX = 200.0F;   // `Menu_Mods::Render` 自己加的那 200 格
constexpr float kModsPageTargetOriginX = 173.0F;
//: "算画布停稳"的帧数阈值（60 Hz 下 20 帧 ≈ 1/3 秒；转移动画本身约 0.5~0.9 秒）。
constexpr std::uint32_t kSettleFrames = 20;

// ── 条目来源 ──────────────────────────────────────────────────────────────────
//
// 容量与"一次最多加载几个模组"**同一个数**：能加载却放不下那种情况没有人会想到去查，
// 也不该出现（`mod_page_runtime_sources.hpp` 里的 `kModPageMaximumMods` 就是它）。
constexpr std::uint32_t kEntryCapacity = isaac::runtime::kModPageMaximumMods;
//: 名字缓冲要**两份**：来源侧一份（`CollectModPageSources` 往里写显示名），条目侧一份
//: （`BuildModPageEntries` 把名字抄进去，条目里的 `std::string` 从此指向它）。
//: 放不下时两条路都是**整体放弃**（绝不写出半截结构）。
constexpr std::size_t kEntryNameBytes = 8192;
constexpr std::size_t kSourceNameBytes = 8192;
//: 一帧最多试几次"等发现结果"（≈15 秒 @60fps）。
//:
//: **为什么要等**：发现结果（`ModMenuPublishDiscovered`）是**启动的模组加载**填进去的，
//: 而那是 worker 线程（构建还专门给了它 5 秒启动延迟）。而"`g_MenuManager` 非空"只说明菜单
//: 系统构造好了，**不保证模组已经扫完**。不等的话会读到"0 个模组"，而那张表只会写一次。
constexpr std::uint32_t kPrepareAttemptLimit = 900;

// 失败码（写进状态面 [2]，读数里一眼看出卡在哪一步）。**与探针同一套语义**。
enum : std::uint32_t {
    kFailureNone = 0,
    kFailureInputUnavailable = 1,
    kFailureModuleNotFound = 2,
    kFailureSetStateGuard = 3,
    kFailureMenuManagerNull = 4,
    kFailureMenuModsGuard = 5,
    kFailureRenderGuard = 6,
    kFailureEntryBuild = 7,       // 条目没造出来
    kFailureManagerNull = 8,      // `g_Manager` 没读到（写条目的前置条件）
    kFailureTitleRelayGuard = 9,  // `Menu_Title::Render` 入口与期望不符（版本不对）
    kFailureModRowGuard = 10,     // `Menu_Game::Render` 入口与期望不符（同上）
    kFailureMenuModsResetGuard = 11,  // `Menu_Mods::Reset` 入口与期望不符
    kFailureLanguageSwitchGuard = 12,  // 换语言那三下的入口（或 `&g_AnmCache`）对不上 ⇒ 不调用
};

// `pageInitState` 的取值。
enum : std::uint32_t {
    kInitNotTried = 0,
    kInitOk = 1,
    kInitGuardMismatch = 2,
    kInitMenuManagerNull = 3,
};

// ── 上下文 ────────────────────────────────────────────────────────────────────

//: `Menu_Mods` 的**静态壳**。
//:
//: 为什么需要它：`Menu_Mods` 是 `MenuManager` 的**内嵌成员**，而它的偏移与大小都没有定论
//: （状态表里那 17 格是"位置/滚动"槽，不是页面对象）。探针用一块**静态零初始化**的内存当壳、
//: 在上面调 `ctor` + `Init` + `Render`，真机跑通了 ⇒ 生产版照用同一形状。
//: 静态已确认的布局：`+0x00` 选中项、`+0x04` 按住计时、`+0x08` Vector2、`+0x10` ANM2、
//: `+0x124` "改过没有"、`+0x170` ModManager ⇒ 0x800 足够，且都落在零初始化内存里。
alignas(16) std::uint8_t g_ModsObject[0x800]{};
float g_ModsPosition[2] = {0.0F, 0.0F};  // `KAGE::Math::Vector2` = 两个 float

//: 条目存储：条目数组、指针数组、`begin/end/cap` 三个字、名字缓冲。**静态零初始化，不写堆**。
alignas(16) std::uint8_t g_Entries[kEntryCapacity][isaac::runtime::kModPageEntryStride]{};
std::uintptr_t g_EntryPointers[kEntryCapacity]{};
alignas(8) std::uintptr_t g_EntryVector[3]{};
isaac::runtime::ModPageEntrySource g_Sources[kEntryCapacity]{};
char g_EntryNameArena[kEntryNameBytes]{};    // 条目里的字符串指向它
char g_SourceNameArena[kSourceNameBytes]{};  // 来源的 displayName 指向它
char g_MetadataScratch[isaac::runtime::kModPageMetadataCapacity]{};
char g_MetadataPath[isaac::runtime::kModPageMetadataPathCapacity]{};

//: 一次性核对过的引擎入口与运行时指针。
struct Context {
    using GetLayerFn = void* (*)(void*, int);
    using SetLayerFrameFn = void (*)(void*, int, int);
    using DrawTextFn = void (*)(void*, const char*, float, float, float, float, const void*, int,
                                bool);
    using FontLineHeightFn = float (*)(const void*);
    using GetLanguageCodeFn = const char* (*)(void*);
    using CtorFn = void (*)(void*);
    using InitFn = void (*)(void*, const float*);
    using RenderFn = void (*)(void*);
    using ResetFn = void (*)(void*);
    using SetModsOffsetFn = void (*)(void*, int);

    GetLayerFn getLayer{nullptr};
    SetLayerFrameFn setLayerFrame{nullptr};
    DrawTextFn drawText{nullptr};
    FontLineHeightFn lineHeight{nullptr};
    //: `Manager::GetLanguageCode()`：按语言码挑那一套生成的美术布局。
    GetLanguageCodeFn getLanguageCode{nullptr};
    CtorFn modsCtor{nullptr};
    InitFn modsInit{nullptr};
    RenderFn modsRender{nullptr};
    ResetFn modsReset{nullptr};
    SetModsOffsetFn setModsOffset{nullptr};
    //: 换语言那三下（照引擎 `PerformLanguageSwitch` 对每个页面的做法，见 `ReloadPageForLanguage`）。
    using PageHookFn = void (*)(void*);
    using AnmCacheFreeFn = void (*)(void*);
    PageHookFn modsPreLanguageSwitch{nullptr};
    PageHookFn modsPostLanguageSwitch{nullptr};
    AnmCacheFreeFn freeUnreferencedEntries{nullptr};
    AnmCacheFreeFn freeUnreferencedImages{nullptr};
    //: 读 `metadata.xml` 那组绑定（`GameFileReader::ReadTextFile`）。
    GameFileReader::Bindings fileBindings{};
    bool fileBindingsOk{false};
    //: `metadata.xml` 三种结果各几次（**读数用**：判断"名字为什么退成了目录名"）。
    //: `rootRelative` = 用应用根相对名解析成功（现在的口径）；`prefixed` = 只有带 `rom:/` 那种成了；
    //: `misses` = 两种都没解析到（那一行会退成目录名）。
    std::uint32_t metadataRootRelativeHits{0};
    std::uint32_t metadataPrefixedHits{0};
    std::uint32_t metadataMisses{0};
    //: 本次开机**实际加载**的**真实模组**（`mods/` 里那些，不含运行时自带的菜单模组）个数。
    //: 口径 = `ModMenuActiveCount()`（启动时 `ModMenuMarkActive` 标出来的那批）。
    //: ★ 2026-09-24 批次 107 起它只作**诊断**用（判据改看下面那个"启用状态"的）。
    std::uint32_t activeRealMods{0};
    //: 处于**启用状态**的真实模组个数（口径 = 模组页开关那一份，**不看有没有重启**）。
    //: ★ 2026-09-24 批次 107 起「该不该禁成就」的判据就是它 —— 与 PC 的
    //: `ModManager::AchievementsLocked()` 同口径（走列表里每一项的启用位）。
    std::uint32_t enabledRealMods{0};
    // ---- 批次 116 加的"发现清单自证"四格（发布进状态面 [41]..[44]，一一对应）----
    // 为什么要有它们：上面两个只是**汇总数**，而待修记录里 `[40] = 0` 与"开关服务读不出来时
    // 本该默认全都开着"是矛盾的 —— 汇总数分不出"清单是空的 / 每一条都被判成关闭 /
    // 发现这一步根本没跑到"，而这三者的处置完全不同（见状态面 `.hpp` 那一段的判读表）。
    std::uint32_t discoveredRealMods{0};
    std::uint32_t discoveredEnabledMask{0};
    std::uint32_t discoveredActiveMask{0};
    std::uint32_t discoveryDone{0};
    std::uint32_t wombAchievementUnlocked{0};
    std::uint32_t achievementsReadOnly{0};
    //: 成就位数组的抽样（`PersistentGameData+0x28` 起 4 个字节）—— 读数里自证位置没读错。
    std::uint32_t achievementSample{0};
    //: `IContentManager::GetMountedFilePath`：返回堆上挂载绝对路径（空 = 不在任何挂载点）。
    //: **优先用中继记下的原函数**：这个函数的入口已经被我们自己的贴图桥改写成跳转了，
    //: 比原版序言必然失败（2026-09-21 真机掩码 0x20 就是这么来的）。
    using GetMountedFn = char* (*)(void*, const char*);
    GetMountedFn getMounted{nullptr};
    //: `g_ContentManager` 对象指针（`base + 0xAAC748` **读一次**就是它）。
    void* contentManager{nullptr};
    //: 还那条堆路径用的 —— **必须用游戏自己的 `operator delete[]`**。
    GameFileReader::GameOperatorDeleteArrayFn freePath{nullptr};
    //: 运行时值（每帧刷新）。
    std::uintptr_t manager{0};       // `g_Manager`（字体对象嵌在它里面）
    std::uintptr_t menuManager{0};   // `g_MenuManager`
    std::uint32_t menuState{0};      // `MenuManager+0x38`（渲染回调靠它门控）
    float screenWidth{0.0F};
    float screenHeight{0.0F};
    //: 挑中的那一套布局（按游戏语言码，见 `mod_row_generated.hpp`）。
    const isaac::runtime::ModRowLayout* layout{nullptr};
    char language[4] = {0, 0, 0, 0};
    //: 语言码是不是已经读到过至少一次 —— 有了它，"`language` 变了"才有意义（第一次不算变）。
    std::uint32_t languageSeen{0};
    //: 1 = 语言变过、等模组页**不显示**时把页面动画按新语言重载一次（见 `ReloadPageForLanguage`）。
    std::uint32_t pageReloadPending{0};
    std::uint32_t languageState{0};  // 0 没试 / 1 ★ 拿到 / 2 入口守卫不过 / 3 单例空 /
                                     // 4 挑到的是 `en` 兜底（不是本语言的美术）
    std::uint32_t entryGuardState{0};  // 0 没试 / 1 ★ 全部过 / 2 有入口不符（不调用）
    std::uint32_t pageInitState{kInitNotTried};
    std::uint32_t prepareAttempts{0};
    std::uint32_t vectorWritten{0};
    std::uint32_t writtenDirectories{0};
    //: 页面位置那套小状态机（批次 063：位置只定一次、之后跟着画布走）。
    std::uint32_t positionSet{0};
    std::uint32_t settledFrames{0};
    std::uint32_t stillFrames{0};
    std::uint32_t corrected{0};
    float positionX{0.0F};
    float positionY{0.0F};
    float targetOffsetX{0.0F};
    float targetOffsetY{0.0F};
    float lastOffsetX{0.0F};
    float lastOffsetY{0.0F};
    //: 上一帧是否在模组页里 —— 用来识别"**刚刚离开**"这一刻（在那时落盘一次）。
    std::uint32_t pageWasActive{0};
};
Context g_Menu{};

//: 当前选中第几格（0..5，3 = 我们那一格）。进入那一屏时按引擎的行号初始化。
std::uint32_t g_Slot = 0;
std::uint32_t g_SlotInit = 0;
//: 从模组页回来时，光标要回到**我们那一格**（而不是按引擎行号换算出来的邻格）。
//:
//: 为什么需要它：我们那一格（slot 3）写回给引擎的行号是 **3**（`EngineRowForSlot(3) == 3`），
//: 而"引擎行号 → 我们的格子"的换算是"≥ 我们的落点就 +1"（插进去的那一格占了原来的第 4 格）
//: ⇒ 引擎行号 3 会被换成**第 5 格（统计数据）**，光标就跑到隔壁去了。
std::uint32_t g_RestoreOurs = 0;
//: 上一帧的按键状态（**自己算边沿**）：引擎那份"刚按下"状态在我们跑到它的时候是空的
//: （结论写在 `input_api.cpp` 里），所以沿用"按住"位图 + 自记状态。
std::uint32_t g_LastUp = 0;
std::uint32_t g_LastDown = 0;
std::uint32_t g_LastConfirm = 0;
//: 模组页那一边的边沿（与"我们那一格"那套分开记，免得两个屏幕互相污染）。
std::uint32_t g_PageLastUp = 0;
std::uint32_t g_PageLastDown = 0;
std::uint32_t g_PageLastConfirm = 0;
std::uint32_t g_PageLastBack = 0;

//: 与 `input_api.cpp` 同一个调用形状（那处是权威）：第一个参数被跳板覆盖，动作号进 x1、
//: 手柄号进 x2、第三个引擎参数（PC 的可选 `entity`）一律给空指针。
using ActionQueryFn = bool (*)(void*, std::uint32_t, std::uint32_t, void*);

// ─────────────────────────────────────────────────────────────────────────────
// 基础工具
// ─────────────────────────────────────────────────────────────────────────────

//: 解析一个引擎入口 ⇒ **直接得到带签名的可调用指针**（批次 108 起本 TU 唯一的入口解析形状）。
//:
//: 三件事一次做完：范围判据、可读判据、16 字节序言的**逐字节核对**，全在引擎调用层
//: （`engine_call::ResolveFunction`）；这里只回答"我们要调的是哪个入口"。
//: 任一条不成立 ⇒ `nullptr` —— **绝不把没核对过的地址变成能调的东西**。
//:
//: `ok` 是**累积**语义（原来 `Guarded(...) && ok` 那个形状）：给了一串入口要一起核对时，
//: 只要有一条不过，后面的入口**一律不给**（免得"半套入口"被拿去用）。传 `nullptr` 表示只要这一个。
template <typename Fn>
Fn VerifiedEntry(const TargetModule& module, std::uintptr_t offset,
                 const std::array<std::uint8_t, 16>& expected, bool* ok = nullptr) {
    const Fn entry = engine_call::ResolveFunction<Fn>(
        module.base, module.size, offset, expected, &engine_memory::EngineMemoryReadable);
    if (ok == nullptr) {
        return entry;
    }
    *ok = entry != nullptr && *ok;
    return *ok ? entry : nullptr;
}

//: 读一个 GOT 槽里存的东西（= 加载器解析出来的地址）。槽本身必须落在模块映像内。
bool ReadSlot(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* value) {
    if (module.size < sizeof(std::uintptr_t) ||
        slotOffset > module.size - sizeof(std::uintptr_t)) {
        return false;
    }
    const std::uintptr_t slot = module.base + slotOffset;
    if (slot < module.base || slot + sizeof(std::uintptr_t) > module.base + module.size) {
        return false;
    }
    // 取值走访问层（候选地址仍由上面那两条范围判据先筛过一遍 —— 两条都要留着：
    // 范围判据拦的是"偏移本身就不对的调用"，可读判定拦的是"这段映射压根不在"）。
    return engine_memory::ReadAt(slot, value, &engine_memory::EngineMemoryReadable);
}

//: 单例的两级取值（槽 → 全局变量地址 → 值）。返回 false = 这条链不成立，**不许再往下用**。
bool ReadSingleton(const TargetModule& module, std::uintptr_t slotOffset, std::uintptr_t* out) {
    std::uintptr_t global = 0;
    if (!ReadSlot(module, slotOffset, &global) || global == 0) {
        return false;
    }
    // 全局变量本身在模块的 bss 里（例如 `g_MenuManager` 在 0xABCD48），所以这里只做
    // 非空与对齐检查，不要求它落在映像内：超出映像尾部的那段正是 bss。
    // ★ 批次 105：取值改走访问层，于是多一道"这 8 字节可读吗"。bss 是普通的**可读写**映射，
    //   这一道必然通过 —— 它挡的是"读到一段没映射的地址"（那种形态原来会直接崩）。
    if ((global & (sizeof(std::uintptr_t) - 1)) != 0) {
        return false;
    }
    std::uintptr_t value = 0;
    if (!engine_memory::ReadAt(global, &value, &engine_memory::EngineMemoryReadable)) {
        return false;
    }
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

//: "任一控制器答'是'" —— **不再假设手柄号是 0**（项目历史结论：真机上出现过 33），
//: 并且单独问一次 `0xFFFFFFFF`（游戏自己的菜单代码用的就是这个值，语义是"任意"）。
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

//: 可见屏幕有多大（`IsaacRepentance::WIDTH` / `HEIGHT`）。
//: GOT 槽里放的是**指向 float 的指针**（`get_target_offset` 里 `ldr x8,[x8,#0x650]; ldr s0,[x8]`），
//: 所以这里读两步：槽 → 指针 → 那个 float。
//: 为什么要它：页面坐标空间是 480×270，可见屏幕比它小、居中裁切 —— 算"纸该摆在哪"要用它。
void RefreshScreenSize(const TargetModule& module) {
    const auto readFloatGlobal = [&module](std::uintptr_t slotOffset, float* out) {
        std::uintptr_t target = 0;
        if (!ReadSlot(module, slotOffset, &target) || target == 0) {
            return false;
        }
        float value = 0.0F;
        if (!engine_memory::ReadAt(target, &value, &engine_memory::EngineMemoryReadable)) {
            return false;
        }
        *out = value;
        return true;
    };
    if (!readFloatGlobal(kWidthSlotOffset, &g_Menu.screenWidth)) {
        g_Menu.screenWidth = 0.0F;
    }
    if (!readFloatGlobal(kHeightSlotOffset, &g_Menu.screenHeight)) {
        g_Menu.screenHeight = 0.0F;
    }
}

//: 读 `MenuManager+0x38`（状态机当前状态）。
std::uint32_t ReadMenuState(std::uintptr_t menuManager) {
    if (menuManager == 0) {
        return 0;
    }
    std::uint32_t state = 0;
    if (!engine_memory::ReadField(menuManager, kMenuManagerStateOffset, &state,
                                  &engine_memory::EngineMemoryReadable, 0)) {
        // 读不到 ⇒ 报"状态 0"（= 不在任何菜单页）。原来会照读、拿垃圾值去比 —— 那正是
        // `EnterModsPage` 那条"必须就在选择界面"的前置判据最怕的东西。
        return 0;
    }
    return state & 0xFFFFU;
}

// ─────────────────────────────────────────────────────────────────────────────
// 条目来源（发现结果 + `metadata.xml` 的 `<name>`）
// ─────────────────────────────────────────────────────────────────────────────

//: 目录来源：直接读 `mod_menu_api` 收下的那份"开机扫描发现到的模组"。
//: 为什么不自已再列一次目录：那会变成两处各维护一份，用户在原生日志页上看到的名字与
//: 自己的 Lua 模组菜单里看到的对不上时，没有人能判断哪一份是对的。
std::uint32_t ProvideDirectories(void* /*context*/, const char** out, std::uint32_t capacity) {
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

//: 开关来源：就是那张纸右边"开着/关着"的依据（同一份数据源，见 `RuntimeMods.List()`）。
bool ProvideEnabled(void* /*context*/, const char* directory) {
    return isaac::runtime::ModMenuDiscoveredEnabled(directory);
}

//: "把这个路径解析成引擎自己能打开的绝对路径" —— **绝不盲开**的最后一步。
//:
//: ★ 反汇编依据：`GetMountedFilePath` 内部是 `get_mount_point(path)` + `FileMap::Get` +
//: `CreateCleanPath`，**全程只查表、不开文件** ⇒ 解析不到只是返回空，不会 Abort。
bool ResolveMountedPath(void* context, const char* path, char* out, std::size_t capacity) {
    auto* source = static_cast<Context*>(context);
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

//: 真正把 `metadata.xml` 读进来（`GameFileReader::ReadTextFile`，与清单/脚本读取同一个入口）。
bool ReadMetadataText(void* context, const char* path, char* buffer, std::size_t capacity,
                      std::size_t* length) {
    const auto* source = static_cast<const Context*>(context);
    if (source == nullptr || !source->fileBindingsOk || buffer == nullptr) {
        return false;
    }
    // `ReadTextFile` 只在"非诊断构建"或"stage 13"里存在（`game_file_reader.hpp` 的 `#if`）。
    // 本 TU 在诊断构建里也编译 ⇒ 这一块跟着它的可见性走：不可见时如实返回"读不到"
    // ⇒ 所有名字退目录名，而不是编译不过。
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
    // 这里那个 `reinterpret_cast<u8*>` 是 `char*` → libnx `u8*` 的**类型别名转换**
    // （`GameFileReader::ReadTextFile` 的参数类型如此），不碰引擎内存 ⇒ 不走访问层。
    const auto result = GameFileReader::ReadTextFile(
        source->fileBindings, path, reinterpret_cast<u8*>(buffer), capacity, length);
    return result == GameFileReader::TextReadResult::Success;
#else
    (void)path;
    (void)capacity;
    (void)length;
    return false;
#endif
}

//: 把"挂载解析 + 读文件"合成 `CollectRuntimeModPageSources` 要的那个 reader：
//: 先解析（`ResolveThenRead` 的纪律），解析不过 ⇒ **绝不**去读。
//: ★ 2026-09-22 真机事故换来的：`File::OpenRead` 对"打开失败"是直接 Abort，而它**不做挂载解析**
//: ⇒ "先问存在性、再拿同一条路径去读"这个写法会崩游戏。这里读的永远是**解析出来的那条绝对路径**。
bool CollectMetadataText(void* context, const char* path, char* buffer, std::size_t capacity,
                         std::size_t* length) {
    auto* source = static_cast<Context*>(context);
    if (source == nullptr || path == nullptr) {
        return false;
    }
    char resolved[isaac::runtime::kModPageMetadataPathCapacity]{};
    // ① **应用根相对名**（现在的口径，见 `mod_page_sources.hpp` 里那段）：
    //    引擎的挂载解析只认这种形式；带 `rom:/` 前缀那种它答不出来（2026-09-22 实测）。
    if (isaac::runtime::MountedReadResult::Read ==
        isaac::runtime::ResolveThenRead(path, &ResolveMountedPath, source, &ReadMetadataText, source,
                                        resolved, sizeof(resolved), buffer, capacity, length)) {
        ++g_Menu.metadataRootRelativeHits;
        return true;
    }
    // ② 兜底：把带 `rom:/` 前缀那种也试一次（旧口径）。**两种都试是为了把不确定性变成读数** ——
    //    哪一条成了记在状态面 [28] 上，下次真机一眼看得出解析口径对不对，不必再猜。
    const std::size_t lengthWithoutPrefix = std::strlen(path);
    if (lengthWithoutPrefix + 6 < sizeof(resolved)) {
        char prefixed[isaac::runtime::kModPageMetadataPathCapacity]{};
        std::memcpy(prefixed, "rom:/", 5);
        std::memcpy(prefixed + 5, path, lengthWithoutPrefix + 1);
        if (isaac::runtime::MountedReadResult::Read ==
            isaac::runtime::ResolveThenRead(prefixed, &ResolveMountedPath, source, &ReadMetadataText,
                                            source, resolved, sizeof(resolved), buffer, capacity,
                                            length)) {
            ++g_Menu.metadataPrefixedHits;
            return true;
        }
    }
    ++g_Menu.metadataMisses;
    return false;
}

//: 条目来源的引擎入口校验（只做一次）。返回是否具备"取真实模组名"的全部前提。
//:
//: ★ 两个函数指针（`getMounted` / `freePath`）都经 `VerifiedEntry` 拿 —— 批次 108 起
//:   "核对 + 转成可调用签名"是**引擎调用层**的一个名字（`engine_call::ResolveFunction`），
//:   调用点不再自己 `reinterpret_cast`。原来的范围/逐字节判据一条没改，只是搬进了层。
void PrepareSourceContext(const TargetModule& module) {
    g_Menu.fileBindingsOk = GameFileReader::VerifyBindings(module, &g_Menu.fileBindings);
    // ① 挂载解析入口：优先用中继记下的原函数（理由见 `Context::getMounted`）。
    //    中继没装时才退回"守卫过的引擎入口" —— 那种情况下入口是原版、守卫才有意义。
    auto getMounted =
        isaac::runtime::Original<Context::GetMountedFn>(isaac::runtime::HookId::ContentGetMountedFilePath);
    if (getMounted != nullptr) {
        g_Menu.getMounted = getMounted;
    } else if (const auto direct = VerifiedEntry<Context::GetMountedFn>(
                   module, kContentManagerGetMountedFilePathOffset,
                   kContentManagerGetMountedFilePathExpectedBytes);
               direct != nullptr) {
        // 核对不过就**保持原值**（原实现也是"不赋值"，不是"赋空"）—— 这里逐条同义。
        g_Menu.getMounted = direct;
    }
    // ② `g_ContentManager` 对象指针：`base + 0xAAC748` **读一次**就是它
    //    （两个引擎调用点互证；`GameFileReader::VerifyImagePcxBindings` 也是这么读的）。
    //    ★ 批次 105：原来是 `volatile` 裸解引用 —— 换成访问层的取值（层内是 `memcpy`，
    //      同样"真读一次内存"、不会被折成常量），并多一道"这 8 字节可读吗"。
    {
        std::uintptr_t slot = 0;
        if (engine_memory::ReadAt(module.base + kContentManagerGotSlotOffset, &slot,
                                  &engine_memory::EngineMemoryReadable) &&
            slot != 0 && (slot & 7u) == 0) {
            g_Menu.contentManager = engine_memory::AsObject(slot);
        }
    }
    // ③ 还内存用的"游戏的 `operator delete[]`"（`GetMountedFilePath` 的返回值是 `new[]` 出来的）。
    if (const auto freePath = VerifiedEntry<GameFileReader::GameOperatorDeleteArrayFn>(
            module, kGameOperatorDeleteArrayOffset, kGameOperatorDeleteArrayExpectedBytes);
        freePath != nullptr) {
        g_Menu.freePath = freePath;
    }
    // 任一条拿不到 ⇒ 解析回调自己会返回 false（`ResolveMountedPath` 的前置检查），
    // 结果是"所有名字退目录名"—— 那是**正常降级**，不是错误。
}

//: 试着把条目表准备好并把 `begin/end/cap` 写进 `g_Manager + 0x36800`。
//:
//: 返回 true = 表已经就绪（可以往下走 `ctor` + `Init`）；false = 还在等发现结果、或没有模组。
//: **必须在 `Init` 之前写**：`Init` 会把 begin 抄进 `对象+0x170`。
//: 布局本身由 `mod_page_entries.hpp` 负责（那里逐字节被宿主门禁钉住）—— 本函数只负责"接线"。
//:
//: ★ 与探针的唯一差别（规格第二节：**不搬假数据**）：探针在"真实数据取不到"时会退回三个写死的
//:   测试名当信号；生产里**一个模组都没发现就是空表** —— 绝不往玩家屏幕上写假名字。
//:   （那三个字面量**故意不写在这里**：门禁按整段子串判定"生产代码里不许出现固定测试名"，
//:    注释里出现也会红。只改措辞、不放宽断言 —— 真写进去照样红。）
bool TryPrepareModsVector() {
    if (g_Menu.vectorWritten != 0) {
        return true;
    }
    if (g_Menu.manager == 0) {
        g_ModMenuState.failure = kFailureManagerNull;
        return false;
    }
    if (g_Menu.prepareAttempts < kPrepareAttemptLimit) {
        ++g_Menu.prepareAttempts;
    }
    isaac::runtime::ModPageRuntimeStats stats{};
    const std::uint32_t found = isaac::runtime::CollectRuntimeModPageSources(
        &g_Sources[0], kEntryCapacity, &ProvideDirectories, nullptr, &ProvideEnabled, nullptr,
        &CollectMetadataText, &g_Menu, g_SourceNameArena, sizeof(g_SourceNameArena),
        g_MetadataPath, g_MetadataScratch, &stats);
    std::size_t nameBytes = 0;
    std::uint32_t built = 0;
    if (found != 0) {
        built = isaac::runtime::BuildModPageEntries(&g_Entries[0][0], &g_EntryPointers[0],
                                                    g_EntryVector, found, &g_Sources[0],
                                                    g_EntryNameArena, sizeof(g_EntryNameArena),
                                                    &nameBytes);
    }
    const bool ready = built == found && found != 0;
    // 该等还是该退，由那个纯判定说了算（`DecideModPageSource`，宿主门禁逐条钉着）。
    switch (isaac::runtime::DecideModPageSource(ready, stats.directories, g_Menu.prepareAttempts,
                                                kPrepareAttemptLimit)) {
        case isaac::runtime::ModPageSourceDecision::Wait:
            // 发现结果还没出来（启动的模组扫描在 worker 线程上，构建还给了它 5 秒延迟）
            // ⇒ 这一帧什么都别做。**绝不能**在这里写死那张表：它只会写一次。
            return false;
        case isaac::runtime::ModPageSourceDecision::Ready:
            break;
        case isaac::runtime::ModPageSourceDecision::Fallback:
            // 真没有模组（或条目没造全）⇒ 写一张**空表**：页面照样进得去、只是 0 行。
            // 为什么不学探针退固定测试名：那会往玩家屏幕上写假名字（规格明令不搬）。
            if (built != found) {
                g_ModMenuState.failure = kFailureEntryBuild;
            }
            g_EntryVector[0] = 0;
            g_EntryVector[1] = 0;
            g_EntryVector[2] = 0;
            break;
    }
    // ★ 写入前**读旧值**（留证：引擎那张表天生是空的 —— `ModManager::Reset` 无调用者、
    //   `ListMods` 只有它一个调用者）。这里不因为"旧值非空"就放弃写入：那会让页面显示引擎的
    //   （空名）条目而不是真实模组，与验收判据冲突；而这 24 字节是**死代码**的字段，
    //   覆盖它不会丢任何活数据（规格第七节的风险对策就是这条）。
    {
        std::uintptr_t oldBegin = 0;
        std::uintptr_t oldEnd = 0;
        const bool oldReadBegin =
            engine_memory::ReadField(g_Menu.manager, kManagerModsVectorOffset, &oldBegin,
                                     &engine_memory::EngineMemoryReadable, 0);
        const bool oldReadEnd =
            engine_memory::ReadField(g_Menu.manager, kManagerModsVectorOffset + 8, &oldEnd,
                                     &engine_memory::EngineMemoryReadable, 0);
        // 旧值是"一对像话的指针"说明引擎真的在用它 ⇒ 记进失败码，便于现场分诊
        // （探针的 `modListPointersOk` 同一口径；不阻断写入）。
        // 读不到就**不许**说它像指针（那会把"读不到"误报成"引擎在用"）。
        const bool pointerLike = oldReadBegin && oldReadEnd && oldBegin >= 0x1000 &&
                                 oldEnd >= oldBegin && (oldBegin & 7u) == 0 &&
                                 (oldEnd & 7u) == 0 && oldEnd > oldBegin;
        if (pointerLike) {
            g_ModMenuState.failure = kFailureEntryBuild;
        }
    }
    // ★ 批次 105：这一处**必须**先过"可写"判定 —— 它写的正是引擎自己的模组表（`g_Manager + 0x36800`），
    //   "一处无守卫的写把内存写坏"那类事故就长在这个形状上。写不进去 = 表还是引擎原来那份空表
    //   ⇒ 如实记失败码并报"没就绪"，**不许**声称已就绪（那会让页面显示引擎的空条目）。
    //   （原来的裸 `memcpy` 在"不可写"时是把进程直接写崩。）
    if (!engine_memory::WriteField(g_Menu.manager, kManagerModsVectorOffset, g_EntryVector,
                                   &engine_memory::EngineMemoryWritable, 0)) {
        g_ModMenuState.failure = kFailureEntryBuild;
        return false;
    }
    g_Menu.vectorWritten = 1;
    g_Menu.writtenDirectories = stats.directories;
    g_ModMenuState.entryCount = static_cast<std::uint32_t>((built == found) ? found : 0);
    return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// 那一行的算术（纯逻辑在 `mod_menu_entry_row.hpp`，这里只接线）
// ─────────────────────────────────────────────────────────────────────────────

//: 取 ANM2 的某个图层对象；拿不到返回 nullptr（调用方必须判）。
void* LayerOf(std::uintptr_t anm2, std::uint32_t layer) {
    if (g_Menu.getLayer == nullptr || anm2 == 0) {
        return nullptr;
    }
    return g_Menu.getLayer(engine_memory::AsObject(anm2), static_cast<int>(layer));
}

//: 引擎自己那份菜单动画里有没有我们补回去的那一层（`Item6`）。
//:
//: 判据 = **图层数**（`ANM2+0xB0`）。为什么不用 `GetLayer(12)` 是不是空：`ANM2::GetLayer(int)`
//: 越界时**不返回空指针** —— 它只打一条日志，然后照样按 `[ANM2+0xA8] + index*0xB0` 算出界地址。
//: 拿那个地址当图层用就是读越界内存。
bool HasNativeLayer(std::uintptr_t anm2) {
    if (anm2 == 0) {
        return false;
    }
    std::uint32_t count = 0;
    const bool read =
        engine_memory::ReadField(anm2, kAnm2LayerCountOffset, &count,
                                 &engine_memory::EngineMemoryReadable, 0);
    // 读不到图层数 ⇒ 当作"没有我们那一层"（⇒ 走兜底绘制）。比"照读一个越界值再拿它判断"安全。
    const bool present = read && count >= kMenuGameLayerCountWithModRow;
    g_ModMenuState.rowOwner = present ? 1U : 2U;
    return present;
}

//: 给每一行的图层偏移加/减一个位移（X 与 Y 都加）。`sign` = +1 施加、-1 还原。
//: 为什么要还原：引擎自己每帧也在往这个字段里加（那是它的排版手段），我们不还原就会一路漂下去。
//: 每一行挪的量**各不相同**（见生成的 `rowShiftY` / `rowShiftX`）：插点以上三行上移、STATS 下移、
//: OPTIONS 几乎不动。横向也照搬 PC（只搬 Y 的话「模组」会比上面那行挑战还靠左）。
void ShiftRows(std::uintptr_t anm2, float sign) {
    if (g_Menu.layout == nullptr) {
        return;  // 语言还没定 ⇒ 一帧都不挪（比"照英文那套挪"安全）
    }
    for (std::uint32_t row = 0; row < isaac::runtime::kMenuGameEngineEntryCount; ++row) {
        void* object = LayerOf(anm2, isaac::runtime::kMenuGameFirstRowLayer + row);
        if (object == nullptr) {
            continue;
        }
        const auto base = engine_memory::AddressOf(object);
        const float delta_x =
            isaac::runtime::MenuGameRowShiftXFor(*g_Menu.layout, row) * sign;
        const float delta_y = isaac::runtime::MenuGameRowShiftFor(*g_Menu.layout, row) * sign;
        // X 在 `+0x48`、Y 在 `+0x4C`（见 `mod_menu_entry_row.hpp` 里那条真机换来的结论）。
        // 读-改-写都走访问层：读要过"可读"、写要过"可写"（原来是裸 memcpy，两个都不查）。
        auto shift = [base](std::uintptr_t field_offset, float delta) {
            if (delta == 0.0F) {
                return;
            }
            const std::uintptr_t field = base + field_offset;
            float value = 0.0F;
            if (!engine_memory::ReadAt(field, &value, &engine_memory::EngineMemoryReadable)) {
                return;  // 读不到 ⇒ 一个字节都不写（比"照加一个数再写回去"安全）
            }
            value += delta;
            (void)engine_memory::WriteAt(field, value, &engine_memory::EngineMemoryWritable);
        };
        shift(isaac::runtime::kAnm2LayerOffsetXField, delta_x);
        shift(isaac::runtime::kAnm2LayerOffsetYField, delta_y);
    }
}

//: 光标：帧号 = 生成器给的帧（**不是格子号**），位置 = 我们自己给的一个 Y 偏移。
//: 那几帧的 y 是按**原版**那几格画的（帧 y ≈ 格子框顶 + 33），格子动了就不能照用 ——
//: 探针"选项那行光标停不到"正是栽在这：照用第 6 帧，它的 y=236 已经在纸外面。
//: `sign` = +1 施加（顺带设帧）、-1 还原。
void PlaceCursor(std::uintptr_t anm2, float sign) {
    void* object = LayerOf(anm2, isaac::runtime::kMenuGameCursorLayer);
    if (object == nullptr || g_Menu.layout == nullptr) {
        return;
    }
    const float delta = isaac::runtime::CursorDeltaYForSlot(*g_Menu.layout, g_Slot) * sign;
    const std::uintptr_t field =
        engine_memory::AddressOf(object) + isaac::runtime::kAnm2LayerOffsetYField;
    float value = 0.0F;
    if (engine_memory::ReadAt(field, &value, &engine_memory::EngineMemoryReadable)) {
        value += delta;
        (void)engine_memory::WriteAt(field, value, &engine_memory::EngineMemoryWritable);
    }
    if (sign > 0.0F && g_Menu.setLayerFrame != nullptr) {
        g_Menu.setLayerFrame(engine_memory::AsObject(anm2),
                             static_cast<int>(isaac::runtime::kMenuGameCursorLayer),
                             static_cast<int>(
                                 isaac::runtime::CursorFrameForSlot(*g_Menu.layout, g_Slot)));
    }
}

//: 算出**这一页的 ANM2 原点**（= 引擎自己交给 `ANM2::Render` 的那个位置）。
//:
//: 为什么必须**实时**算：进这一屏时纸是"滑"进来的 —— 那个滑动就是 `MenuManager+0x3c`
//: 这个偏移在朝目标值收敛。纸与那些行图都是 ANM2 图层，它们的最终位置 = **ANM2 原点 +
//: 图层局部坐标**；而画字接口用的是绝对坐标 ⇒ 把局部坐标直接交给它，字就**不跟着纸动**。
//: 引擎自己就是这么算的（`Menu_Game::Render` 反汇编 `0x40E760`~`0x40E784`）：
//:     x8 = g_MenuManager; x8 = *x8; ldp w9, w8, [x8, #0x3c]   ; 偏移
//:     x1 = this + 8                                            ; 页面自己的位置
//:     Vector2::operator+                                      ; ⇒ 原点
bool PageOrigin(std::uintptr_t page, float* out) {
    if (out == nullptr || page == 0 || g_Menu.menuManager == 0) {
        return false;
    }
    float offset[2] = {0.0F, 0.0F};
    float position[2] = {0.0F, 0.0F};
    // ★ 这里必须写 `&offset` / `&position`：`ReadField` 的出参是引用形参（`T* const&`），
    //   传裸数组**编译不过** —— 那段历史与判据见 `engine_field_access.hpp` 里 `ReadField` 那一段。
    if (!engine_memory::ReadField(g_Menu.menuManager, kMenuManagerCanvasOffset, &offset,
                                  &engine_memory::EngineMemoryReadable, 0) ||
        !engine_memory::ReadField(page, kPagePositionOffset, &position,
                                  &engine_memory::EngineMemoryReadable, 0)) {
        // 两段读不到 ⇒ **不假装原点算出来了**（画出去会落在屏幕角上）。
        return false;
    }
    out[0] = offset[0] + position[0];
    out[1] = offset[1] + position[1];
    return true;
}

//: 画我们那一行（**兜底**，只有"引擎那份动画里没有我们那一层"时才走）。
//:
//: ★ 与探针的唯一差别：探针这里有三条路（磁盘贴图 → 内存贴图 → 画字），生产版**只留画字**。
//:   为什么：075 之后那一行由引擎自己画，那两条贴图路线已是死路（真机崩过：`Data Abort @ 0x0`，
//:   栈为 `ANM2::Render → AnimationLayer::RenderFrame → GetSourceQuad`，原因是拿了一张**空**的
//:   精灵表去画）。搬过去只会扩大风险面。
//: ★ 但"**空的东西绝不拿去画**"这条判据要保住：拿不到字体/布局/原点时返回 false 并**什么都不画**。
//:   返回值就是那条判据的载体 —— 调用方据此决定要不要记"我们画出了东西"。
bool DrawRowLabel(std::uintptr_t page) {
    if (g_Menu.drawText == nullptr || g_Menu.manager == 0 || g_Menu.layout == nullptr) {
        return false;
    }
    void* font = engine_memory::AsObject(g_Menu.manager + kManagerFontOffset);
    float origin[2] = {0.0F, 0.0F};
    if (!PageOrigin(page, origin)) {
        return false;  // 原点拿不到 ⇒ 画出去会落在屏幕角上，宁可不画
    }
    const float x = origin[0] + kModRowTextX;
    // 锚点 = 生成器算出来的那一格顶（引擎行 = 框顶；我们那一格 = 贴图顶），字从贴图内的
    // `inkTop` 起 —— 与周围五行落在同一水平线上。
    float slotTop = kModEntryTextYFallback;
    if (g_Menu.layout != nullptr) {
        slotTop = isaac::runtime::MenuGameSlotTop(*g_Menu.layout, isaac::runtime::kModEntrySlot) +
                  static_cast<float>(g_Menu.layout->sprite.inkTop);
    }
    const float y = origin[1] + slotTop;
    // 缩放 = **量出来的字高** ÷ 当前字体的行高 —— 换字体自动适应，不用重调。
    // ⚠️ 用的是 `glyphHeight`（真字高）而不是美术里那行字的**包围盒**高：那五行是斜着写的，
    //   包围盒高 = 字高×cos + 字宽×sin ⇒ 照包围盒缩放，画出来的字比周围大一圈。
    float artHeight = kModRowArtTextHeight;
    if (g_Menu.layout->glyphHeight > 1.0F) {
        artHeight = g_Menu.layout->glyphHeight;
    }
    float scale = kModRowTextScaleFallback;
    if (g_Menu.lineHeight != nullptr) {
        const float lineHeight = g_Menu.lineHeight(font);
        if (lineHeight > 1.0F && lineHeight < 200.0F) {
            scale = artHeight / lineHeight;
        }
    }
    g_Menu.drawText(font, kModRowLabel, x, y, scale, scale, kModRowTextColor, 0, false);
    return true;
}

//: 定语言：调 `Manager::GetLanguageCode()`（两字符码），再按它挑一套生成的布局。
//:
//: ★ **每帧都问一次**（2026-09-23 批次 078 改）：原来这里"一次就定死"，理由是
//: "语言在游戏里改不了、改了要重启"。用户实测推翻了这个前提 ——
//: **在选项页里换语言是当场生效的**：其它界面的文字与美术都跟着换，只有我们这一页
//: 还挂着旧语言那张纸（那张纸是分语言的，见 `ReloadPageForLanguage`）。
//: `Manager::GetLanguageCode()` 只是一次读，代价可以忽略；语言码没变就一个字节都不写。
void ResolveLanguage() {
    if (g_Menu.manager == 0 || g_Menu.getLanguageCode == nullptr) {
        // 拿不到就**不定**（每帧都会再问一次）：宁可让布局晚一帧就位，也不要定错一套美术。
        if (g_Menu.languageSeen == 0) {
            g_Menu.languageState = 3;
        }
        return;
    }
    const char* code =
        g_Menu.getLanguageCode(engine_memory::AsObject(g_Menu.manager));
    if (code == nullptr || code[0] == '\0') {
        if (g_Menu.languageSeen == 0) {
            g_Menu.languageState = 3;
        }
        return;
    }
    // 绝大多数帧走这一条：语言码没变（一次比较，"变了才动手"）。
    if (g_Menu.languageSeen != 0 && code[0] == g_Menu.language[0] &&
        code[1] == g_Menu.language[1]) {
        return;
    }
    const bool changed = g_Menu.languageSeen != 0;
    g_Menu.language[0] = code[0];
    g_Menu.language[1] = code[1];
    std::uint32_t packed = 0;
    std::memcpy(&packed, g_Menu.language, sizeof(packed));  // 'z''h' ⇒ 0x0000687A
    g_ModMenuState.languageCode = packed;
    g_Menu.layout = isaac::runtime::ModRowLayoutForLanguage(g_Menu.language);
    g_Menu.languageSeen = 1;
    // 挑到 `en` 而语言码不是 `en` ⇒ 这个语言没有自己的美术（引擎那边也一样走基础资源）。
    const bool isEnglish = g_Menu.language[0] == 'e' && g_Menu.language[1] == 'n';
    const bool pickedEnglish = g_Menu.layout->language[0] == 'e' &&
                               g_Menu.layout->language[1] == 'n';
    g_Menu.languageState = (pickedEnglish && !isEnglish) ? 4U : 1U;
    if (changed) {
        // 语言变了：那一列的挪位量、以及模组页那张纸**都**要换成新语言的。
        // 布局上面已经换了；页面动画的换法见 `ReloadPageForLanguage`（它不能在这里做 ——
        // 这里只是"发现变了"，重载要挑页面不显示的时刻）。
        ++g_ModMenuState.languageSwitches;
        g_Menu.pageReloadPending = 1;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 模组页（引擎状态 16）
// ─────────────────────────────────────────────────────────────────────────────

//: 语言变了 ⇒ 把模组页的动画按新语言重载一次（那张纸、以及右上那行提示的**贴图**都烤在图里）。
//:
//: ★ 只重跑 `Init`、**绝不重跑 `ctor`**：`ctor` 会在活对象上重新构造内嵌的 ANM2
//:   （`add x0,x19,#0x10; bl ANM2::ANM2()`）⇒ 旧动画的缓存引用**没人还**，白漏一份。
//:   引擎自己的 `PostLanguageSwitch` 也不碰构造函数 —— 这一点我们和它一致。
//:
//: ★★ **已知的不足（079 试过、已撤回）**：这一招只能换**贴图**（`load_graphics` 会按当前挂载层
//:   重新解析精灵表），**换不动动画排版** —— `g_AnmCache` 按**路径哈希**缓存（`FNHash`，`0xF4E8`），
//:   路径串一样就分不出语言，所以同一路径的动画数据永远是**开机那次解析**的那份。
//:   引擎自己的 `PerformLanguageSwitch` 是靠"放开引用 → `AnmCache::FreeUnreferenced*` 回收 → 重新加载"
//:   把排版换过来的；079 照抄了那三步，结果**把 EID 的信息显示搞坏了**（引擎把我们这侧
//:   shim 借用的贴图/动画当成"没人引用"给放掉了）⇒ 那一步**不能调**，退回现在这一版。
//:   完整过程见 `docs/改动日志-20260923.md` 的 079，以及文件上半部分那段注释。
//:   ⇒ 影响面：**同一次开机内换过语言**时，这张纸上的贴图会跟着换、那个键盘图标的位置还是
//:   开机语言那份（**重启一次即正确**）。
//:
//: 时机：**每帧更新里**（引擎 `Manager::Update` 之前、不在任何渲染批次中间），
//: 而且只在模组页**当前没显示**时动手 —— 页面正画着的时候换它的动画没有意义。
//: 语言只能在选项页里改，所以正常情况下这一刻页面本来就是关着的；万一不是（将来有别的入口），
//: 就等它关了再换：`pageReloadPending` 一直挂着，不会丢。
void ReloadPageForLanguage(const TargetModule& module) {
    if (g_Menu.pageReloadPending == 0) {
        return;
    }
    if (isaac::runtime::ModPageIsActive(g_Menu.menuState)) {
        return;  // 页面正显示 ⇒ 等它关了再换（不丢：标志还挂着）
    }
    g_Menu.pageReloadPending = 0;
    if (g_Menu.pageInitState != kInitOk) {
        return;  // 页面还没建过（或建失败）⇒ 下次进页面本来就会按新语言 `Init`，不必重复
    }
    if (g_Menu.modsPreLanguageSwitch == nullptr || g_Menu.modsPostLanguageSwitch == nullptr ||
        g_Menu.freeUnreferencedEntries == nullptr || g_Menu.freeUnreferencedImages == nullptr) {
        g_ModMenuState.failure = kFailureLanguageSwitchGuard;
        return;  // 有入口没通过逐字节核对 ⇒ **一次都不调用**（绝不盲目跳地址）
    }
    std::uintptr_t anmCache = 0;
    if (!ReadSlot(module, kAnmCacheSlotOffset, &anmCache) || anmCache == 0) {
        g_ModMenuState.failure = kFailureLanguageSwitchGuard;
        return;
    }
    // ① 放开（`ANM2::Reset` 在里面）—— 这一步之后页面暂时是"空"的，所以上面先要求它没在显示。
    g_Menu.modsPreLanguageSwitch(g_ModsObject);
    // ② 回收没人引用的贴图与动画数据（顺序与引擎一致：先图后条目）。
    g_Menu.freeUnreferencedImages(engine_memory::AsObject(anmCache));
    g_Menu.freeUnreferencedEntries(engine_memory::AsObject(anmCache));
    // ③ 按当前语言重新加载（引擎自己的 `PostLanguageSwitch`：`Load` + `Play("Main")` + …）。
    g_Menu.modsPostLanguageSwitch(g_ModsObject);
    ++g_ModMenuState.pageReloads;
    // 位置那套状态机跟着重来一遍：`Reset`/`Load` 会清掉页面自己的位置与动画状态，
    // 不重置的话这一帧会按"上一次算出来的位置"画（那一套是给旧动画算的）。
    g_Menu.positionSet = 0;
    g_Menu.settledFrames = 0;
    g_Menu.stillFrames = 0;
    g_Menu.corrected = 0;
    g_Menu.lastOffsetX = 0.0F;
    g_Menu.lastOffsetY = 0.0F;
}

//: 走引擎自己的状态机切状态。**必须走中继记下的原函数**：装了 `SetState` 中继之后入口
//: 16 字节已被改写，逐字节守卫必然对不上（探针批次 060 的 bug 就是这么来的：现象只是"按了没反应"）。
//: 没装中继（`Original` 为空）才走"守卫 + 直接调"的老路。
void ApplyState(const TargetModule& module, std::uint32_t state) {
    using SetStateFn = void (*)(void*, std::int32_t);
    const auto original =
        isaac::runtime::Original<SetStateFn>(isaac::runtime::HookId::MenuManagerSetState);
    if (original != nullptr) {
        original(engine_memory::AsObject(g_Menu.menuManager), static_cast<std::int32_t>(state));
        g_ModMenuState.failure = kFailureNone;
        return;
    }
    // 批次 108：核对与"转成可调用签名"一起由引擎调用层完成 —— 核对不过就是 `nullptr`。
    const auto setState = VerifiedEntry<SetStateFn>(module, kMenuManagerSetStateOffset,
                                                    kMenuManagerSetStateExpectedBytes);
    if (setState == nullptr) {
        g_ModMenuState.failure = kFailureSetStateGuard;
        return;
    }
    setState(engine_memory::AsObject(g_Menu.menuManager), static_cast<std::int32_t>(state));
    g_ModMenuState.failure = kFailureNone;
}

//: 一次性 `ctor` + `Init`（`Menu_Mods` 的静态壳）。
//: 位置先给 `(0,0)`：真正的摆放由**每帧**按 `MenuManager+0x3c` 反算后写进对象 `+0x8` 完成。
void InitManualPage() {
    if (g_Menu.menuManager == 0) {
        g_Menu.pageInitState = kInitMenuManagerNull;
        g_ModMenuState.failure = kFailureMenuManagerNull;
        return;
    }
    if (g_Menu.modsCtor == nullptr || g_Menu.modsInit == nullptr || g_Menu.modsRender == nullptr) {
        g_Menu.pageInitState = kInitGuardMismatch;
        g_ModMenuState.failure = kFailureMenuModsGuard;
        return;
    }
    g_ModsPosition[0] = 0.0F;
    g_ModsPosition[1] = 0.0F;
    g_Menu.modsCtor(g_ModsObject);
    g_Menu.modsInit(g_ModsObject, g_ModsPosition);
    g_Menu.pageInitState = kInitOk;
    g_ModMenuState.failure = kFailureNone;
}

//: 进模组页：补上 Switch 版删掉的那一下（`Menu_Mods::Reset`），再走引擎自己的 `SetState(16)`。
void EnterModsPage(const TargetModule& module, const ActionQueryFn query) {
    // 0) 前提：得在"选择界面"那一屏（否则说明这一下不是从我们那一格来的）。
    if ((ReadMenuState(g_Menu.menuManager)) != kGameMenuState) {
        return;
    }
    // 1) 页面得是"已经 Init 过"的。没起来就**当场补做一次**，而不是直接放弃
    //    （那正是"按了确认却跳到统计页面"的一个可能原因：我们退出了，引擎就按它自己的索引去处理）。
    if (g_Menu.pageInitState != kInitOk) {
        if (TryPrepareModsVector()) {
            InitManualPage();
        }
        if (g_Menu.pageInitState != kInitOk) {
            return;
        }
    }
    // 2) "归零"这一下**不再依赖引擎的 `Reset`**：那几个字段我们自己就能写。
    //    引擎的 `Reset` 只在守卫过得去时额外调一次（它还会重读一遍 ModManager 指针、播 "Main" 动画）。
    const std::uint32_t zero = 0;
    // ★ `g_ModsObject` 是**我们自己的**静态壳（文件上半部分：`Menu_Mods` 的内嵌成员没有定论，
    //   探针用一块静态内存当壳、真机跑通了），不是引擎对象 —— 但它的那几个字段是**交给引擎当
    //   `this` 用**的，所以照样走访问层：本 TU 里"算地址 + 读/写"只有一条路，读代码的人不必
    //   分辨"这一处的目标是谁"。代价是每次多一次可写判定（我们自己的 bss，判定恒通过）。
    const std::uintptr_t modsObject = engine_memory::AddressOf(g_ModsObject);
    (void)engine_memory::WriteField(modsObject, isaac::runtime::kModsSelectedElementOffset, zero,
                                    &engine_memory::EngineMemoryWritable, 0);
    (void)engine_memory::WriteField(modsObject, isaac::runtime::kModsHoldTimerOffset, zero,
                                    &engine_memory::EngineMemoryWritable, 0);
    (void)engine_memory::WriteField(modsObject, isaac::runtime::kModsEditedOffset, zero,
                                    &engine_memory::EngineMemoryWritable, 0);
    if (g_Menu.modsReset != nullptr) {
        g_Menu.modsReset(g_ModsObject);
    } else {
        // 守卫不过只是"少做一次锦上添花"，**不是**不进去的理由。
        g_ModMenuState.failure = kFailureMenuModsResetGuard;
    }
    // 4) 先让"那一格的滚动值"变成确定值，再去算纸的位置（见 `kSetModsOffsetOffset` 的注释：
    //    不先调一次的话，第一次进来读到的还是 `Init` 的旧值，用户看到"错位 1~2 秒"）。
    if (g_Menu.setModsOffset != nullptr) {
        g_Menu.setModsOffset(engine_memory::AsObject(g_Menu.menuManager), 0);
    }
    ++g_ModMenuState.pageEnterCalls;
    // 5) 交给引擎的状态机（= PC 的做法）。这一步**必须**发生：走到这里之后引擎本帧的分派表
    //    （`cmp w8,#0xf`）就不会再去叫 `Menu_Game::Update`，也就不会再拿我们那一格的行号去开统计页。
    ApplyState(module, isaac::runtime::kModsPageState);
    // 6) 回来时光标要落在我们那一格上（理由见 `g_RestoreOurs`）。
    g_RestoreOurs = 1;
    // 7) 位置那套状态机（第二帧定位置、停稳后自证一次）每次进页面都要重来。
    g_Menu.positionSet = 0;
    g_Menu.settledFrames = 0;
    g_Menu.stillFrames = 0;
    g_Menu.corrected = 0;
    g_Menu.lastOffsetX = 0.0F;
    g_Menu.lastOffsetY = 0.0F;
    // 8) 把引擎的"模组总开关"置上。真机读数（探针批次 058）发现它是 **0**，而 `Menu_Mods::Render`
    //    在它为 0 时**只用一个颜色画所有行**（不读条目自己的 `+0x138`）⇒ 不置它，
    //    "按确认切换开关"在屏幕上根本看不出来。**只改内存**，不碰任何文件。
    if (g_Menu.manager != 0) {
        const auto wanted = static_cast<std::uint8_t>(isaac::runtime::kModsEnabledGateOn);
        // 写引擎自己的一个字节 ⇒ 走访问层（先确认可写）。写不进去只是"颜色不变"，
        // 页面照样进得去 ⇒ 不报失败码、也不改判据。
        (void)engine_memory::WriteField(g_Menu.manager, kManagerModsEnabledOffset, wanted,
                                        &engine_memory::EngineMemoryWritable, 0);
    }
    // 8) ★★ 必须把输入边沿按"**当前**还按着的情况"锁上，否则页面第一帧就会误判一次新按下：
    //    进页面用的就是那个确认键（A），它现在**还按着**，而上一帧状态是 0 ⇒ 第一帧的 `Edge()`
    //    会返回"刚按下" ⇒ **刚进去就顺手把第一个模组的开关翻掉了**。按住计时同理。
    bool directionHeld = false;
    if (query != nullptr) {
        const bool confirmHeld = HeldByAnyone(query, kActionConfirm);
        const bool backHeld = HeldByAnyone(query, kActionBack);
        const bool upHeld = HeldByAnyone(query, kActionUp);
        const bool downHeld = HeldByAnyone(query, kActionDown);
        g_PageLastConfirm = isaac::runtime::ModPageLatchedEdge(confirmHeld);
        g_PageLastBack = isaac::runtime::ModPageLatchedEdge(backHeld);
        g_PageLastUp = isaac::runtime::ModPageLatchedEdge(upHeld);
        g_PageLastDown = isaac::runtime::ModPageLatchedEdge(downHeld);
        directionHeld = upHeld || downHeld;
    }
    const std::uint32_t seed = isaac::runtime::ModPageHoldSeed(directionHeld);
    (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                    isaac::runtime::kModsHoldTimerOffset, seed,
                                    &engine_memory::EngineMemoryWritable, 0);
}

//: 状态 16 期间由我们驱动页面：导航（含按住重复）、切换开关、返回。
//: 数据面：`g_Manager + 0x36800` 那张表（`begin/end/cap`，每项一个指针，条目里 `+0x138` 是启用位）。
void ModsPageUpdate(const TargetModule& module, const ActionQueryFn query) {
    const bool active = isaac::runtime::ModPageIsActive(g_Menu.menuState);
    // ★ **离开模组页**（刚刚还在、现在不在了）且这次改过开关 ⇒ 落盘一次
    //（用户 2026-09-22 裁定："退出时写一次"）。写的是**游戏存档分区**，不是卡上的覆盖层。
    if (g_Menu.pageWasActive != 0 && !active) {
        g_Menu.pageWasActive = 0;
        std::uint32_t edited = 0;
        // 读不到就当作"没改过"（= 不落盘）：宁可少写一次盘，也不要凭一个猜出来的值去写存档。
        const bool editedRead =
            engine_memory::ReadField(engine_memory::AddressOf(g_ModsObject),
                                     isaac::runtime::kModsEditedOffset, &edited,
                                     &engine_memory::EngineMemoryReadable, 0);
        if (isaac::runtime::ModPageShouldPersist(editedRead && edited != 0)) {
            g_ModMenuState.toggleSaveState = isaac::runtime::ModMenuSaveToggles() ? 1U : 2U;
        }
        ++g_ModMenuState.pageBackCalls;
        // ★★ 2026-09-23 修：**边沿状态只在"真的离开这一页"那一刻清零**，不在这里之外的
        //    任何 `!active` 帧清（下面那个早退分支以前就是这么干的，是个真 bug）。
        //
        // 真机现象（用户 2026-09-23 报）：**每次进模组页，第一个模组的开关都会自己翻一次。**
        // 机制（同一帧的先后顺序）：
        //   ① `ModRowUpdate` 里我们那一格的确认 ⇒ `EnterModsPage()`，它把四个边沿
        //      **按"当前还按着的情况"锁上**（`ModPageLatchedEdge`，进页面用的就是 A 键、
        //      此刻还按着）⇒ 目的正是"下一帧不许把它当成新按下"；
        //   ② **同一帧**接着跑 `ModsPageUpdate`：`g_Menu.menuState` 是这一帧**开头**读的，
        //      那时还没切到 16 ⇒ `active == false` ⇒ 走了下面那个早退分支、**把刚锁上的清零**；
        //   ③ 下一帧状态已是 16、`active == true`，而 A 还按着、上一帧记的是 0
        //      ⇒ `Edge()` 返回"刚按下" ⇒ 顺手把第一条的开关翻掉。
        // ⇒ 清零只属于"离开这一页"这个动作，不能顺手放在"当前不在这一页"上。
        g_PageLastUp = 0;
        g_PageLastDown = 0;
        g_PageLastConfirm = 0;
        g_PageLastBack = 0;
    }
    if (!active) {
        // 当前不在这一页（含"刚切进来、状态还是上一帧那份"那一帧）：**什么都不动**。
        // 尤其**不许清边沿状态** —— 理由见上面那段（清了就会在进页面后第一帧误判一次确认）。
        return;
    }
    g_Menu.pageWasActive = 1;
    ++g_ModMenuState.pageDrivenFrames;

    // ── 数据面：条目表 ──────────────────────────────────────────────────────────────
    std::uintptr_t begin = 0;
    std::uintptr_t end = 0;
    std::uint32_t entryCount = 0;
    if (g_Menu.manager != 0) {
        (void)engine_memory::ReadField(g_Menu.manager, kManagerModsVectorOffset, &begin,
                                       &engine_memory::EngineMemoryReadable, 0);
        (void)engine_memory::ReadField(g_Menu.manager, kManagerModsVectorOffset + 8, &end,
                                       &engine_memory::EngineMemoryReadable, 0);
        // 条数只接受"像话"的那一种（`begin` 是个真指针、`end-begin` 是 8 的倍数且不太大）。
        if (begin >= 0x1000 && end >= begin && ((end - begin) % 8) == 0 &&
            (end - begin) <= 8ULL * 4096ULL) {
            entryCount = static_cast<std::uint32_t>((end - begin) / 8);
        }
    }
    g_ModMenuState.entryCount = entryCount;

    // ── 页面对象里的两个字段（选中项、按住计时）──────────────────────────────────────
    std::uint32_t selected = 0;
    std::uint32_t hold = 0;
    (void)engine_memory::ReadField(engine_memory::AddressOf(g_ModsObject),
                                   isaac::runtime::kModsSelectedElementOffset, &selected,
                                   &engine_memory::EngineMemoryReadable, 0);
    (void)engine_memory::ReadField(engine_memory::AddressOf(g_ModsObject),
                                   isaac::runtime::kModsHoldTimerOffset, &hold,
                                   &engine_memory::EngineMemoryReadable, 0);

    // ── 输入 ────────────────────────────────────────────────────────────────────────
    bool up = false;
    bool down = false;
    bool confirm = false;
    bool back = false;
    if (query != nullptr) {
        up = HeldByAnyone(query, kActionUp);
        down = HeldByAnyone(query, kActionDown);
        confirm = HeldByAnyone(query, kActionConfirm);
        back = HeldByAnyone(query, kActionBack);
    }
    const bool upEdge = Edge(&g_PageLastUp, up);
    const bool downEdge = Edge(&g_PageLastDown, down);
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
    (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                    isaac::runtime::kModsSelectedElementOffset, selected,
                                    &engine_memory::EngineMemoryWritable, 0);
    (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                    isaac::runtime::kModsHoldTimerOffset, hold,
                                    &engine_memory::EngineMemoryWritable, 0);

    // 确认 = 切换这一条的开关。**只改内存**（条目 `+0x138` 那一位），退出页面时才落盘。
    if (Edge(&g_PageLastConfirm, confirm)) {
        if (entryCount > 0 && selected < entryCount) {
            std::uintptr_t entry = 0;
            // `begin + 选中项*8` 是"表里第几个指针"的**算好的地址** ⇒ 用 `ReadAt`
            // （它不查对齐，与原实现的裸 memcpy 判据一致）。
            (void)engine_memory::ReadAt(begin + selected * sizeof(std::uintptr_t), &entry,
                                        &engine_memory::EngineMemoryReadable);
            if (entry >= 0x1000) {
                std::uint8_t enabled = 0;
                (void)engine_memory::ReadField(entry,
                                               isaac::runtime::kModPageEntryEnabledOffset, &enabled,
                                               &engine_memory::EngineMemoryReadable, 0);
                const std::uint8_t next = static_cast<std::uint8_t>(
                    isaac::runtime::ModPageToggleEnabled(enabled));
                (void)engine_memory::WriteField(entry, isaac::runtime::kModPageEntryEnabledOffset,
                                                next, &engine_memory::EngineMemoryWritable, 0);
                const std::uint32_t edited = 1;
                (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                                isaac::runtime::kModsEditedOffset, edited,
                                                &engine_memory::EngineMemoryWritable, 0);
                // 把这一下**同时**写进运行时既有的开关服务（只改内存、不落盘）。
                // 页面上那一栏读的就是它（`ModMenuDiscoveredEnabled`），所以两边永远是同一份口径。
                const char* directory = isaac::runtime::ModMenuDiscoveredDirectory(selected);
                (void)isaac::runtime::ModMenuSetEnabled(directory, next != 0);
            }
        }
    }
    // 返回 = 引擎自己的做法：`SetState(3)`（`Menu_Mods::Update` 就是这么做的）。
    // 这一步一执行，`MenuManager::Update` 本帧的分派就把 `Menu_Game::Update` 接回来了 ——
    // 也就是说"回到选择界面"完全走引擎的路径，我们不多写一行。
    if (Edge(&g_PageLastBack, back)) {
        ApplyState(module, kGameMenuState);
        return;
    }
    g_ModMenuState.selectedEntry = selected;
    g_ModMenuState.failure = kFailureNone;
}

//: 每帧推进"我们那一格的导航"，并把引擎的**行号**写回 `页面+0x4`。
//:
//: 我们写、引擎也写 —— 但每帧都由我们覆盖一次，所以引擎自己的那次移动不会累积成两格。
void ModRowUpdate(const TargetModule& module, const ActionQueryFn query) {
    const std::uintptr_t page = g_Menu.menuManager + kMenuGamePageOffsetInMenuManager;
    // 第一次进入那一屏：按引擎的**现有**行号初始化我们的格子（引擎行 e ≥ 3 对应我们的 e+1，
    // 因为我们插进去的那一格占了引擎原来的第 4 格）。
    // ★ 例外：**从模组页回来**时不换算，直接回到我们那一格（理由见 `g_RestoreOurs`）。
    if (g_SlotInit == 0) {
        if (g_RestoreOurs != 0) {
            g_RestoreOurs = 0;
            g_Slot = isaac::runtime::kModEntrySlot;
        } else {
            std::uint32_t engineIndex = 0;
            (void)engine_memory::ReadField(page, kPageSelectedIndexOffset, &engineIndex,
                                           &engine_memory::EngineMemoryReadable, 0);
            g_Slot = engineIndex < isaac::runtime::kModEntrySlot ? engineIndex : engineIndex + 1;
            if (g_Slot >= isaac::runtime::kMenuGameEntryCount) {
                g_Slot = isaac::runtime::kMenuGameEntryCount - 1;
            }
        }
        g_SlotInit = 1;
    }
    if (query != nullptr) {
        const bool up = HeldByAnyone(query, kActionUp);
        const bool down = HeldByAnyone(query, kActionDown);
        const bool confirm = HeldByAnyone(query, kActionConfirm);
        if (Edge(&g_LastUp, up)) {
            g_Slot = isaac::runtime::AdvanceSlot(g_Slot, false);
        }
        if (Edge(&g_LastDown, down)) {
            g_Slot = isaac::runtime::AdvanceSlot(g_Slot, true);
        }
        if (Edge(&g_LastConfirm, confirm)) {
            if (g_Slot == isaac::runtime::kModEntrySlot) {
                ++g_ModMenuState.confirmOnOurs;
                // ★ **在我们那一格按确认 = 进模组页**（引擎状态 16）。为什么必须在这里
                //   （我们的更新回调里）就把状态切掉、而不是"等引擎自己处理"：本回调跑在引擎
                //   `Manager::Update` **之前**，而引擎那一帧还会读一次同一个动作
                //   （`Menu_Game::Update` 的确认分支）。我们那一格写回给引擎的行号是 3
                //   （= 统计那一行）⇒ 引擎会 `SetState(9)`。**先切成 16**，引擎本帧的分派表
                //   （`cmp w8,#0xf`）就不会再去叫 `Menu_Game::Update` 了 ——
                //   这一下同时完成了"进页面"和"吃掉那次确认"。
                EnterModsPage(module, query);
            }
            // 其余格子**什么都不做**：让引擎自己处理它那五格。
        }
    }
    // ★★ 写回给引擎的是**行号**（`EngineRowForSlot`），不是"把格子号夹一下" —— 2026-09-23 修正。
    //
    // 用户实测："统计和选项按了**都是设置**"。原因就在这一句：引擎的确认跳表按**它的行号**查
    // （行 3 = 统计 ⇒ `SetState(9)`；行 4 = 选项 ⇒ `SetState(10)`），而我们那一列是插过一格的
    // ⇒ 视觉上的"统计数据"（我们的第 4 格）在引擎那里必须是**行 3**。
    // 用 `EngineIndexClampedForSlot`（把格子号夹到 0..4）会把第 4 格写成 4 ⇒ 引擎认为选中的是
    // "选项" ⇒ 于是"统计按了是设置"。
    // 现在的映射（与 `EngineRowForSlot` 一致）：0/1/2 ⇒ 0/1/2、**3 与 4 ⇒ 3**、5 ⇒ 4。
    // 我们那一格（3）借用的就是行 3（统计）⇒ "按了模组却会走到统计"仍要靠**我们自己的接管**拦，
    // 以及 `SetState` 中继那道保险兜底。
    // 再夹一次上界：`EngineRowForSlot` 对非法格子返回的是"引擎行数"（越界值）⇒ 必须夹回 0..4。
    const std::uint32_t row = isaac::runtime::EngineRowForSlot(g_Slot);
    const std::uint32_t clamped =
        row < isaac::runtime::kMenuGameEngineEntryCount ? row
                                                        : isaac::runtime::kMenuGameEngineEntryCount - 1;
    // 写回引擎：**必须**先过"可写"判定 —— 这一处每帧都写引擎的页面对象，
    // 正是"无守卫的写把内存写坏"那类事故的形状。
    (void)engine_memory::WriteField(page, kPageSelectedIndexOffset, clamped,
                                    &engine_memory::EngineMemoryWritable, 0);
    g_ModMenuState.slot = g_Slot;
    g_ModMenuState.engineIndex = clamped;
}

//: 模组页的位置：**只定一次、之后跟着画布走**（= 引擎自己的页面就是这么摆的）。
//:
//: 用户 2026-09-23 第二次反馈（很具体，直接指出错在哪）：
//:   「是那种速度很快就跳到了模组界面，其他的似乎没反应过来的感觉」
//: ⇒ 上一版只让 **Y** 跟着画布走、**X 仍然钉在屏幕中间**，于是这一页**一开场就横向铺满屏幕**，
//:   而背景那条菜单还在按画布速度慢慢往外滑 ⇒ 看起来就是"纸啪一下盖上来、别的没跟上"。
//:
//: 现在：**位置只定一次**（两个方向都定），之后一律不动 ⇒ 纸的屏幕位置 = 画布偏移 + 固定位置，
//: 与引擎自己的页面同一个速度、同一套过渡：开场时它整个在屏幕外（这一页的家在画布很右边），
//: 随画布滑动**从左侧滑进来**，停稳时正好落在已验收的 (173, 72)。
//:
//: 位置怎么定：引擎自己的约定是 `目标偏移 = 那一格 + 居中量`（`MenuManager::Update` 对每个页面
//: 都算这一条：`this + 状态*8 + 0x1AFF08` 再与 `get_target_offset()` 相加）。
//: 于是"画布停稳时纸落在目标原点" ⇔ `本页位置 = 目标原点 − (它自己加的 200,0) − 目标偏移`。
//:
//: 为什么"第二帧"才定：`Menu_Mods::Render` 每帧会调 `SetModsOffset(选中项)` 改写那一格的 Y，
//: 第一帧时它还可能是 `Init` 留下的旧值 ⇒ 定早了纸会摆错（差 74 格，肉眼可见）。
void UpdatePagePosition(std::uintptr_t menuManager) {
    const float targetOriginX = kModsPageTargetOriginX;  // 173：= 200 − 27（见常量注释）
    const float targetOriginY = -kModsSheetOffsetY;      // 72：纸的上沿压在页面顶端
    float offset[2] = {0.0F, 0.0F};
    (void)engine_memory::ReadField(menuManager, kMenuManagerCanvasOffset, &offset,
                                   &engine_memory::EngineMemoryReadable, 0);
    if (g_Menu.positionSet == 0) {
        if (g_Menu.settledFrames++ >= 1) {
            float slot[2] = {0.0F, 0.0F};
            // 那一格自己的偏移（`状态*8`，见 `kMenuManagerStateSlotBase` 的注释）⇒ 地址已经算好，
            // 用 `ReadField(base, 偏移, …)` 一次读出那 8 字节。★ 传 `&slot`：两个 float **一起**读
            // （传裸数组编译不过 —— 见 `engine_field_access.hpp` 里 `ReadField` 那一段；批次 105
            //  就是在这里栽的：只读到 X、Y 留在 0，整页纵向偏出视野）。
            (void)engine_memory::ReadField(menuManager,
                                           isaac::runtime::kMenuManagerStateSlotBase +
                                               isaac::runtime::kModsPageState * 8,
                                           &slot, &engine_memory::EngineMemoryReadable, 0);
            const float centerX = (g_Menu.screenWidth - kPageBoxWidth) * 0.5F;
            const float centerY = (g_Menu.screenHeight - 270.0F) * 0.5F;
            g_Menu.targetOffsetX = slot[0] + centerX;
            g_Menu.targetOffsetY = slot[1] + centerY;
            g_Menu.positionX = targetOriginX - kModsRenderExtraX - g_Menu.targetOffsetX;
            g_Menu.positionY = targetOriginY - g_Menu.targetOffsetY;
            g_Menu.positionSet = 1;
        }
        return;
    }
    (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject), kPagePositionOffset,
                                    g_Menu.positionX, &engine_memory::EngineMemoryWritable, 0);
    (void)engine_memory::WriteField(engine_memory::AddressOf(g_ModsObject),
                                    kPagePositionOffset + sizeof(g_Menu.positionX),
                                    g_Menu.positionY, &engine_memory::EngineMemoryWritable, 0);
    // 兜底自证：等画布**停稳**之后核对一次"纸到底画在哪"（停稳 = 偏移连续若干帧没变）。
    // 偏差 > 1 格只可能发生在那条公式算错的时候（例如"那一格的 X 不参与"）⇒ 修正一次，
    // 让**静止位置**永远是对的；过渡动画的形状不变。
    const float deltaX = offset[0] - g_Menu.lastOffsetX;
    const float deltaY = offset[1] - g_Menu.lastOffsetY;
    const float moved = (deltaX < 0 ? -deltaX : deltaX) + (deltaY < 0 ? -deltaY : deltaY);
    g_Menu.stillFrames = moved < 0.01F ? g_Menu.stillFrames + 1 : 0;
    if (g_Menu.stillFrames == kSettleFrames && g_Menu.corrected == 0) {
        g_Menu.corrected = 1;
        const float originX = offset[0] + g_Menu.positionX + kModsRenderExtraX;
        const float originY = offset[1] + g_Menu.positionY;
        const float fixX = targetOriginX - originX;
        const float fixY = targetOriginY - originY;
        const float fixSum = (fixX < 0 ? -fixX : fixX) + (fixY < 0 ? -fixY : fixY);
        if (fixSum > 1.0F) {
            g_Menu.positionX += fixX;
            g_Menu.positionY += fixY;
        }
    }
    g_Menu.lastOffsetX = offset[0];
    g_Menu.lastOffsetY = offset[1];
}

//: 一次性核对我们要**直接调用**的那些引擎入口（安装时做，模块初始化线程）。
//:
//: ★ 批次 108 起，这里每一条都是"解析 + 核对 + 转成可调用签名"一步（`VerifiedEntry`），
//:   三件事全在**引擎调用层**；调用点里不再出现 `reinterpret_cast<Context::XxxFn>`。
//:   `ok` 的**累积语义一个字没改**：任一条核对不过，后面的入口一律拿不到（`nullptr`）。
void VerifyEntries(const TargetModule& module) {
    bool ok = true;
    g_Menu.modsCtor = VerifiedEntry<Context::CtorFn>(module, kMenuModsCtorOffset,
                                                     kMenuModsCtorExpected, &ok);
    g_Menu.modsInit = VerifiedEntry<Context::InitFn>(module, kMenuModsInitOffset,
                                                     kMenuModsInitExpected, &ok);
    g_Menu.modsRender = VerifiedEntry<Context::RenderFn>(module, kMenuModsRenderOffset,
                                                         kMenuModsRenderExpected, &ok);
    g_Menu.modsReset = VerifiedEntry<Context::ResetFn>(module, kMenuModsResetOffset,
                                                       kMenuModsResetExpected, &ok);
    g_Menu.setModsOffset = VerifiedEntry<Context::SetModsOffsetFn>(module, kSetModsOffsetOffset,
                                                                   kSetModsOffsetExpected, &ok);
    // 换语言那三下（引擎 `PerformLanguageSwitch` 对每个页面做的同一套动作）。
    g_Menu.modsPreLanguageSwitch =
        VerifiedEntry<Context::PageHookFn>(module, kMenuModsPreLanguageSwitchOffset,
                                           kMenuModsPreLanguageSwitchExpected, &ok);
    g_Menu.modsPostLanguageSwitch =
        VerifiedEntry<Context::PageHookFn>(module, kMenuModsPostLanguageSwitchOffset,
                                           kMenuModsPostLanguageSwitchExpected, &ok);
    g_Menu.freeUnreferencedImages =
        VerifiedEntry<Context::AnmCacheFreeFn>(module, kAnmCacheFreeUnreferencedImagesOffset,
                                               kAnmCacheFreeUnreferencedImagesExpected, &ok);
    g_Menu.freeUnreferencedEntries =
        VerifiedEntry<Context::AnmCacheFreeFn>(module, kAnmCacheFreeUnreferencedEntriesOffset,
                                               kAnmCacheFreeUnreferencedEntriesExpected, &ok);
    g_Menu.getLayer = VerifiedEntry<Context::GetLayerFn>(module, kAnm2GetLayerStubOffset,
                                                         kAnm2GetLayerStubExpected, &ok);
    g_Menu.setLayerFrame = VerifiedEntry<Context::SetLayerFrameFn>(
        module, kAnm2SetLayerFrameStubOffset, kAnm2SetLayerFrameStubExpected, &ok);
    g_Menu.drawText = VerifiedEntry<Context::DrawTextFn>(
        module, kFontDrawStringScaledUTF8Offset, kFontDrawStringScaledUTF8ExpectedBytes, &ok);
    g_Menu.lineHeight = VerifiedEntry<Context::FontLineHeightFn>(
        module, kFontGetLineHeightOffset, kFontGetLineHeightExpectedBytes, &ok);
    // ★ 这里**故意没有** `Font::Load` / `IsLoaded` 两段：本批撤掉了换字体那段接线
    //   （真机结论：那一页按字节画字，换字体救不了中文；见文件上半部分那段注释）。
    g_Menu.getLanguageCode = VerifiedEntry<Context::GetLanguageCodeFn>(
        module, kManagerGetLanguageCodeOffset, kManagerGetLanguageCodeExpectedBytes, &ok);
    g_Menu.entryGuardState = ok ? 1U : 2U;
    if (!ok) {
        // 逐字节不符 ⇒ **一个字节都不写、一次都不调用**（绝不盲目跳地址）。
        g_ModMenuState.failure = kFailureMenuModsGuard;
    }
}

}  // namespace

// ─────────────────────────────────────────────────────────────────────────────
// 三个入口中继的回调
//
// 形状：入口桩是**尾调用**（`br x16`），所以回调以目标函数的身份运行、`ret` 直接回到游戏的
// 调用方 ⇒ ABI 必须与目标一致（`(this)` / `(this, int)`），返回 void。
// ─────────────────────────────────────────────────────────────────────────────

//: `Menu_Game::Render`：那一列里多一格「模组」。
//:
//: 顺序（**先挪行、再让引擎画、再还原**）：
//:   1) 按生成表挪每一行（插点以上上移、STATS 下移、OPTIONS 几乎不动；X 也照搬 PC）；
//:   2) 光标：按格子设帧 + 加我们自己的 Y 偏移；
//:   3) 跑原函数（它画的是"已经挪好的"5 行，**以及我们补回去的那一层**）；
//:   4) 把光标与行偏移都还原（不还原会随帧累积）；
//:   5) 只有在"引擎那份动画里没有我们那一层"时，才由我们兜底画。
extern "C" void EntryRelayMenuGameRenderCallback(void* self) {
    using RenderFn = void (*)(void*);
    const auto original =
        isaac::runtime::Original<RenderFn>(isaac::runtime::HookId::MenuGameRender);
    if (original == nullptr) {
        return;
    }
    // 门控：只有"就在选择界面那一格"时才干活；其余时刻**纯透传**（与没挂钩逐帧等价）。
    const bool active = g_Menu.menuState == kGameMenuState && self != nullptr;
    if (!active) {
        original(self);
        return;
    }
    const auto anm2 = engine_memory::AddressOf(self) + kPageAnm2Offset;
    // ★ 那一行现在是**引擎自己那份菜单动画里的一层**（补层工具把 PC 的 `Item6` 补了回去）。
    //   有这一层 ⇒ 引擎在这次 `original(self)` 里就把它画了，我们**不许再画一遍**
    //   （画了就是两层叠在一起）。没有这一层（覆盖层没装/被回退）⇒ 由我们兜底。
    const bool nativeLayer = HasNativeLayer(anm2);
    ShiftRows(anm2, 1.0F);
    PlaceCursor(anm2, 1.0F);  // 设帧 + 给光标一个我们自己的 Y 偏移
    original(self);
    PlaceCursor(anm2, -1.0F);
    ShiftRows(anm2, -1.0F);
    if (nativeLayer) {
        return;  // ★ 有那一层就绝不再画
    }
    ++g_ModMenuState.rowFallbackFrames;
    if (DrawRowLabel(engine_memory::AddressOf(self))) {
        ++g_ModMenuState.rowDrawFrames;
    }
    // ★ 这里**不清失败码**（探针批次 061 的教训）：每帧写 0 会让"守卫没过"这种真失败
    //   在读数里显示成"没有失败"，白花一轮真机才定位。
}

//: `Menu_Title::Render`：模组页（状态 16）的**唯一**画手。
//:
//: 为什么借这一趟：`MenuManager::Render` 在调各页 `Render` **之前**先做了一整套准备
//: （`PushRenderTarget` → `SetRenderTargetTexture` → `Clear` → `SetBlendMode` → `LoadShader`
//: → 背景 `FillQuad`），**然后**才调 `Menu_Title::Render`。而引擎的渲染清单里**没有**模组页
//: ⇒ 我们只能在别人的渲染上下文里画，这一趟是唯一能用的。
//:
//: 顺序（先跑原函数，再画我们的页）：这样我们的页画在标题菜单**之上**，而且 `MenuManager::Render`
//: 后续那十几个页面的 `Render` 大多会因自己的可见位是 0 而整页跳过（各页自带门控）。
extern "C" void EntryRelayMenuTitleRenderCallback(void* self) {
    using RenderFn = void (*)(void*);
    const auto original =
        isaac::runtime::Original<RenderFn>(isaac::runtime::HookId::MenuTitleRender);
    if (original != nullptr) {
        original(self);  // 1) 标题菜单照常画（与没挂钩时逐帧等价）
    }
    // 2) 紧接着，在**同一渲染上下文**里画我们的原生页。
    if (g_Menu.pageInitState != kInitOk || g_Menu.modsRender == nullptr) {
        return;
    }
    // ⚠️ 必须自己门控状态：`MenuManager::Render` 每帧无条件调所有页面，`Menu_Title::Render`
    // 自身没有状态判断 ⇒ 不门控的话"切到存档界面也照画"。
    // 只有状态 16 才画（引擎的渲染清单里没有模组页 ⇒ 这一帧就是那个页面的唯一画手）。
    if (!isaac::runtime::ModPageIsActive(g_Menu.menuState)) {
        return;
    }
    // ★ 进页面**第一帧先不画** —— 那时"位置"还没算出来（要等第一帧的 `Render` 把引擎的滚动值
    //   写好才算得准），照旧位置画会闪一下（画在上一轮停稳的位置）。
    //   第一帧只显示背景那条菜单，正好是过渡刚开始该有的样子。
    if (g_Menu.positionSet == 0) {
        return;
    }
    g_Menu.modsRender(g_ModsObject);
}

//: `MenuManager::SetState`：**我们那一格的确认只归我们管**（保险）。
//:
//: 为什么加它（用户 2026-09-22 实测反馈）：在「模组」那一格按确认**跳到了统计页面** ——
//: 我们那一格借用引擎行号 3（= 统计那一行），而我们的接管一旦中途退出，引擎本帧就会拿行号 3
//: 去 `SetState(9)`（统计）。**页面上"跳错页"比"什么都不发生"更难解释**，所以再加一道保险。
extern "C" void EntryRelayMenuManagerSetStateCallback(void* self, std::int32_t state) {
    using SetStateFn = void (*)(void*, std::int32_t);
    const auto original =
        isaac::runtime::Original<SetStateFn>(isaac::runtime::HookId::MenuManagerSetState);
    if (original == nullptr) {
        return;
    }
    // 挡下来要同时满足三条：
    //   ① 当前就在"选择界面"（状态 3）；
    //   ② **我们的光标正停在自己那一格**（格子号 3）—— "统计数据/选项"那两行在我们这边是
    //      第 4/5 格，所以用户真去选它们时这一条不成立，**不会误伤**；
    //   ③ 引擎要去的正是"我们那一格之后"的那两页（统计 9 / 选项 10）——它按行号 3/4 的推断。
    if (g_Slot == isaac::runtime::kModEntrySlot && g_Menu.menuState == kGameMenuState &&
        (static_cast<std::uint32_t>(state) == kStatsState ||
         static_cast<std::uint32_t>(state) == kOptionsState)) {
        ++g_ModMenuState.setStateSwallowed;
        return;  // 不调原函数 ⇒ 状态不变
    }
    original(self, state);
}

namespace isaac::runtime::modmenu {

void ModMenuNativeInstall(const TargetModule& module) noexcept {
    g_ModMenuState.armed = 1;
    // 三个入口中继是**挂点登记表**装的（`HookInstallService` 按 `kHookCatalog` 逐个装）⇒
    // 这里只把"装没装上"记进状态面 [1]。判据用挂点记下的回退入口是否非空：
    // 装上了就一定有回退入口（入口被改写成跳转，原函数只能从槽里取）。
    std::uint32_t bits = 0;
    if (isaac::runtime::Original<void (*)(void*)>(HookId::MenuGameRender) != nullptr) {
        bits |= 1U << 0;
    }
    if (isaac::runtime::Original<void (*)(void*)>(HookId::MenuTitleRender) != nullptr) {
        bits |= 1U << 1;
    }
    if (isaac::runtime::Original<void (*)(void*, std::int32_t)>(HookId::MenuManagerSetState) !=
        nullptr) {
        bits |= 1U << 2;
    }
    g_ModMenuState.relayInstalled = bits;
    // ★★ 批次 117：局内单向闩锁**要不要启用**，判据是 `GameExit` 挂点装上了没有。
    //   为什么必须有这条降级（而不是无条件启用）：`GameStart` 是 `Game::Start` **返回之后**
    //   才回调我们的，而引擎那次写只读位在 `Game::Start` **体内** ⇒ 只靠它清零时，
    //   上一局留下的闩锁会渗进新局（真机现象 = "关着模组的新局照样不给成就"，
    //   正是用户最早报的形状）。`GameExit` 在退出流程一开始就触发，**严格早于下一局的
    //   任何写位**，能把那条路堵死。它缺失时宁可退回批次 107 的实时判据（比 PC 松），
    //   也不要出现"误锁"。这一格记在状态面 [50]，现场一眼看得出闩锁有没有被停用。
    NoteRunLatchArmed(
        isaac::runtime::Original<void (*)(void*, std::uint32_t)>(HookId::GameExit) != nullptr);
    // 一次性核对我们要直接调用的引擎入口（此处仍在模块初始化线程上、游戏主循环尚未开始）。
    VerifyEntries(module);
    // 条目来源那几条（读文件绑定 / 挂载解析 / 还内存的 delete[]）也在这里备好。
    PrepareSourceContext(module);
}

// ── 局内单向闩锁（2026-09-25 批次 117）─────────────────────────────────────────
//
// 设计与"为什么需要它"见 `.hpp` 的「局内单向闩锁」那一段。这里只写**谁改它**：
//   * 只有 `ObserveRunLatch` 能把它抬到 1（单向，条件成立过就一直 1）；
//   * 只有 `NoteNewRun` 能把它放回 0（局边界：离开一局 / 新开一局 / 读档）；
//   * **没有第三处**改它 —— "关掉模组之后仍然是 1"能成立，靠的全部机制就是这一条。
namespace {
bool g_RunLatchLatched = false;
bool g_RunLatchArmed = false;
//: 现在是不是**在一局里**（`GameStart` 之后、`GameExit` 之前）。由 `NoteNewRun` 按来源维护。
//: ★★ 为什么闩锁必须吃这一格（批次 118，117 的第一次真机读数暴露的缺陷）：
//:   开机后在**主菜单**上"开着模组 + 妈腿没解锁"同样成立，于是 117 的闩锁在菜单上就被置位了
//:   ⇒ "进局前把模组关掉"的那一局会被误锁，而用户开工单里的裁定①明确要求"不锁"。
//:   在菜单上"开着模组"什么都不代表 —— 它只是开关状态，不是"这一局用过模组"。
bool g_RunLatchInRun = false;
//: **留存**（批次 119）：出局那一刻闩锁是几。下一次"继续同一份存档"会把它接回来 ——
//: 用户的裁定是"继续同一份存档算同一局"，而他改开关的唯一途径就是退出到主菜单改
//: （模组页在一局里打不开）⇒ 不把污染留存下来，"中途开启后又关掉仍锁"就永远看不到。
bool g_RunLatchCarriedOver = false;
//: 出局时的留存**等着被接回**（下一次观察点会把它当成一次"0→1 边沿"）。
//: 为什么要等：接回来要有 `PersistentGameData*` 才能补写只读位，而"一条局边界到了"这件事
//: 是在 `GameStart` 中继里发生的（那里只有 `Game*`，没有持久数据指针）⇒ 交给下一帧的观察点。
bool g_RunLatchResumePending = false;
// ---- 批次 120：存档分区里那个"污染过"标记（用户裁定"比 PC 严"：跨重启也要保持）----
//
// 上面那颗闩锁只在内存里，**重启就没了**；用户要的是跨重启 ⇒ 落一个专属小文件
// （`isaac-runtime-run-taint.txt`，与 `isaac-switch-mods-state.txt` 同一种做法，不碰引擎的存档结构体）。
// 三个状态与两个"待办"：
//: 我们认为**文件里**现在是什么（`[56]`）：0 还不知道 / 1 污染过 / 2 干净。
std::uint32_t g_TaintFileState = 0;
//: 局边界要求"读一次文件"（"继续同一份存档"时要先知道上一局有没有污染过）。
//: ★ 由 `NoteNewRun(LoadSave)` 挂上，**在每帧的观察点里做掉**（那里是游戏线程）——
//:   绝不在开局中继里做 I/O（那时还在引擎的开局序列里，做 I/O 风险高）。
bool g_TaintFileReadPending = false;
//: 局边界要求"把文件写成某个值"（开新局 ⇒ 清掉；置位 ⇒ 写上 1）。
bool g_TaintFileWritePending = false;
bool g_TaintFileWriteValue = false;
}  // namespace

//: `[56]` 的取值口径（与 `.hpp` 那段是同一份）。
constexpr std::uint32_t kTaintFileUnknown = 0;
constexpr std::uint32_t kTaintFileTainted = 1;
constexpr std::uint32_t kTaintFileClean = 2;

//: 读那个文件，更新"我们认为它是几"。**只在游戏线程上调**（端口的实现自己也会拒绝别的线程）。
//:
//: 三条纪律（都来自 `run_taint_marker.hpp` 与 `mod_persistence.hpp` 的既有口径）：
//:   * 文件不存在 ⇒ **干净**（不是错误：第一次运行就是这样）；
//:   * 读失败 / 端口不可用 ⇒ 停在"还不知道"并**记一次失败**（`[57]`），**不置位**（fail-open）；
//:   * 读到"污染过" ⇒ 顺手把"待接回"挂上 —— 这就是**跨重启**那条路的入口（见 `.hpp` 的 [54] 段）。
void ReadRunTaintFile() noexcept {
    isaac::runtime::ISaveFilePort* storage = isaac::runtime::SessionSaveFilePort();
    if (storage == nullptr) {
        ++g_ModMenuState.taintFileFailures;  // 端口还没接上：如实记，不静默
        return;
    }
    std::array<char, isaac::runtime::kRunTaintMaximumBytes + 64> text{};
    std::size_t bytes = 0;
    const isaac::runtime::Status status = storage->Read(
        isaac::runtime::kRunTaintFileName, text.data(), text.size(), &bytes);
    if (status.code() == isaac::runtime::StatusCode::NotFound) {
        g_TaintFileState = kTaintFileClean;
        return;
    }
    if (!status.ok() || bytes > text.size()) {
        ++g_ModMenuState.taintFileFailures;
        return;
    }
    g_TaintFileState = isaac::runtime::ParseRunTaint(std::string_view(text.data(), bytes))
                           ? kTaintFileTainted
                           : kTaintFileClean;
    if (g_TaintFileState == kTaintFileTainted) {
        // 上一局（可能是上一次开机那一局）污染过 ⇒ 这一次"继续"也要把它接回来。
        g_RunLatchResumePending = true;
    }
}

//: 把标记写进那个文件（`tainted=true` 或 `false`）。成功/失败都记进 `[56]`/`[57]`，不静默。
void WriteRunTaintFile(bool tainted) noexcept {
    isaac::runtime::ISaveFilePort* storage = isaac::runtime::SessionSaveFilePort();
    if (storage == nullptr) {
        ++g_ModMenuState.taintFileFailures;
        return;
    }
    std::array<char, isaac::runtime::kRunTaintMaximumBytes> text{};
    const std::size_t length =
        isaac::runtime::SerializeRunTaint(tainted, text.data(), text.size());
    if (length == 0) {
        ++g_ModMenuState.taintFileFailures;  // 放不下 ⇒ 不写半截（与端口的口径一致）
        return;
    }
    const isaac::runtime::Status status = storage->Write(
        isaac::runtime::kRunTaintFileName, std::string_view(text.data(), length));
    if (!status.ok()) {
        ++g_ModMenuState.taintFileFailures;
        return;
    }
    g_TaintFileState = tainted ? kTaintFileTainted : kTaintFileClean;
}

//: 每帧一次：把局边界挂上的"读/写"做掉，并把 `[56]` 发布出去。
//: ★ 位置在 `UpdateAchievementDisallow` 的**最开头**（游戏线程、且与菜单/局内状态无关）。
void RunTaintFileTick() noexcept {
    if (g_TaintFileReadPending) {
        g_TaintFileReadPending = false;
        ReadRunTaintFile();
    }
    if (g_TaintFileWritePending) {
        g_TaintFileWritePending = false;
        WriteRunTaintFile(g_TaintFileWriteValue);
    }
    g_ModMenuState.taintFileState = g_TaintFileState;
}

bool ObserveRunLatch(bool conditionHolds) noexcept {
    if (!g_RunLatchArmed) {
        return false;  // 闩锁停用（`GameExit` 挂点缺席）⇒ 完全退回批次 107 的实时判据
    }
    if (!g_RunLatchInRun) {
        // 不在一局里 ⇒ **不观察**（菜单上的开关状态不代表"这一局开过模组"）。
        // 这一条是批次 118 加的：117 没有它，于是开机后在菜单上就置了位（真机读数 [45]=1
        // 而 [35] 从未被调到 ⇒ 还没进过任何一局）。
        return false;
    }
    if (g_RunLatchResumePending) {
        // ★★ 批次 119：**继续同一份存档** —— 把出局时留存的污染接回来，并**当成一次置位边沿**
        //    返回 true ⇒ 调用方（`UpdateAchievementDisallow`，那里拿得到持久数据指针）
        //    会**补写一次锁**。为什么必须补写：引擎那次开局写位发生在
        //    `Game::StartFromSavedState` **体内**，而我们把留存接回来是在它**返回之后**
        //    ⇒ 不补写就等于这一局没锁上（用户要的"中途开启后又关掉仍锁"就落不了地）。
        g_RunLatchResumePending = false;
        g_RunLatchLatched = true;
        g_ModMenuState.runLatch = 1;
        ++g_ModMenuState.runLatchSets;
        ++g_ModMenuState.runLatchResumes;
        return true;
    }
    const bool next = RunLatchNextState(conditionHolds, g_RunLatchLatched);
    if (next == g_RunLatchLatched) {
        return false;
    }
    g_RunLatchLatched = next;
    g_ModMenuState.runLatch = 1;
    ++g_ModMenuState.runLatchSets;
    return true;  // 0→1：调用方要**主动**把只读位写下去（那一局引擎不会再写它）
}

void NoteNewRun(RunBoundaryKind kind) noexcept {
    g_ModMenuState.runLatchResetSource = static_cast<std::uint32_t>(kind);
    // ★★ 三种局边界的处置**不同**（批次 119，用户裁定"继续同一份存档算同一局"）
    //    —— 这个映射只留在这里一处；放到调用点就会变成"三处各自记得"，
    //    而漂移的表现是"有时不锁、有时误锁"，最难查。
    switch (kind) {
        case RunBoundaryKind::GameExit:
            // 出局：把闩锁**留成留存**（而不是清成"这一份存档是干净的"）。
            // ★ 为什么不在出局时清掉：用户能改开关的唯一时机就是出局之后，
            //   清了就永远看不到"中途开启后又关掉仍锁"。
            g_RunLatchCarriedOver = g_RunLatchLatched;
            g_RunLatchResumePending = false;
            g_RunLatchInRun = false;
            break;
        case RunBoundaryKind::LoadSave:
            // 继续同一份存档 = **同一局** ⇒ 把留存接回来（下一帧观察点会补写一次锁）。
            // ★ 留存接回之后就消费掉：下一次出局会按那一刻的闩锁重新留存。
            g_RunLatchResumePending = g_RunLatchCarriedOver;
            g_RunLatchCarriedOver = false;
            g_RunLatchInRun = true;
            // ★★ 批次 120：**还要问一次存档分区里那个文件** —— 跨重启就靠它：
            //    上一次开机那一局污染过的话，内存里已经没有留存了，只有文件知道。
            //    I/O 挂到"待办"、由下一帧的观察点做（绝不在这个中继里做）。
            g_TaintFileReadPending = true;
            break;
        case RunBoundaryKind::NewRun:
        default:
            // 开新局：**真正清掉**（含留存）—— 裁定①：进局前关掉模组 ⇒ 这一局不锁。
            // ★ 必须连留存一起清：开新局那次写只读位发生在 `Game::Start` 体内、
            //   早于这条通知 ⇒ 留存不清就会把新局**误锁**。
            g_RunLatchCarriedOver = false;
            g_RunLatchResumePending = false;
            g_RunLatchInRun = true;
            // ★★ 批次 120：新局是"污染"的**终点** ⇒ 把存档分区里那个标记也清掉。
            //    写失败不致命（下次开新局还会试），但**必须记进 `[57]`**，不许静默。
            g_TaintFileWritePending = true;
            g_TaintFileWriteValue = false;
            break;
    }
    if (kind != RunBoundaryKind::LoadSave) {
        // "把闩锁归 0"这件事只在出局与开新局发生（继续那一支不清，它只是把留存接回来）。
        g_RunLatchLatched = false;
        g_ModMenuState.runLatch = 0;
        ++g_ModMenuState.runLatchResets;
    }
    g_ModMenuState.runLatchCarriedOver = g_RunLatchCarriedOver ? 1U : 0U;
    g_ModMenuState.runInProgress = g_RunLatchInRun ? 1U : 0U;
}

bool RunLatchLatched() noexcept { return g_RunLatchLatched; }

void NoteRunLatchArmed(bool armed) noexcept {
    g_RunLatchArmed = armed;
    g_ModMenuState.runLatchArmed = armed ? 1U : 0U;
    if (!armed) {
        g_RunLatchLatched = false;
        // 停用时把留存与"待接回"一起清掉：它们只在闩锁生效时才有意义，
        // 留着会让下一次误判（"为什么 [54] 是 1 而什么都不锁"）。
        g_RunLatchCarriedOver = false;
        g_RunLatchResumePending = false;
        g_ModMenuState.runLatch = 0;
        g_ModMenuState.runLatchCarriedOver = 0;
    }
}

//: 主动把"本局不给成就"那一位写下去（批次 117 的**边沿动作**）。
//:
//: 为什么必须走引擎自己的 `SetReadOnly`、而不是直接写 `PersistentGameData+0x1`：
//:   ① 那是全镜像**唯一**写它的地方（098 的取证），跟着它走 = 跟着引擎的既有约定；
//:   ② 098 的纪律钉着"我们不许把那个偏移当写目标"（门禁按 `kPersistentReadOnlyOffset,`
//:      这个形状判），直接写会红，而且会绕开引擎自己的记账。
//: 拿不到回退入口 ⇒ **什么都不做**：与中继里那条降级同方向（宁可不禁，也不误禁）。
//:
//: ★ 批次 118：加了两格记账（`[52]` 试了几次 / `[53]` 结果）。为什么非加不可 ——
//:   117 的第一次真机读数里"闩锁置位过 1 次、可只读位读出来还是 0"，
//:   而当时**没有任何格子**能分清"没写进去"与"写进去了又被清掉"，
//:   于是只能靠推断。现在写完**当场读回**，把这件事变成一条可以直接看见的事实。
constexpr std::uint32_t kEdgeWriteVerified = 1;    // [53] 写了、且写后读回确认是 1
constexpr std::uint32_t kEdgeWriteNoOriginal = 2;  // [53] 拿不到回退入口 ⇒ 什么都没写
constexpr std::uint32_t kEdgeWriteNotVisible = 3;  // [53] 写了但读回**不是 1**

void WriteAchievementReadOnly(void* persistentGameData) noexcept {
    using SetReadOnlyFn = void (*)(void*, bool);
    ++g_ModMenuState.runLatchEdgeWrites;
    const auto original = isaac::runtime::Original<SetReadOnlyFn>(
        isaac::runtime::HookId::PersistentGameDataSetReadOnly);
    if (original == nullptr) {
        g_ModMenuState.runLatchEdgeWriteResult = kEdgeWriteNoOriginal;
        return;
    }
    original(persistentGameData, true);
    // 写完当场读回（写法上先算地址、再用 `ReadAt`，理由见上面 ② 那条：别让门禁把这一句
    // 当成"写目标"）。
    const std::uintptr_t address =
        engine_memory::AddressOf(persistentGameData) + kPersistentReadOnlyOffset;
    std::uint8_t value = 0;
    const bool readBackOk =
        engine_memory::ReadAt(address, &value, &engine_memory::EngineMemoryReadable);
    g_ModMenuState.runLatchEdgeWriteResult =
        (readBackOk && value != 0) ? kEdgeWriteVerified : kEdgeWriteNotVisible;
}

bool AchievementsShouldBeBlockedFor(void* persistentGameData) noexcept {
    // ★★ 2026-09-25 批次 117：**先看局内单向闩锁** —— 本局里出现过"开着模组 且 妈腿未解锁"
    //    就一直锁，之后把模组关掉也**不解除**（用户要的语义，见 `.hpp` 那段）。
    //    ★ 下面那套实时口径保留，作为"闩锁还没被置位时"的答案：引擎开局那次调用正落在这一支上
    //    （因此"刚清完零"这一瞬不会漏判），而"中途开启模组"由每帧观察点置位后再由这里短接。
    if (RunLatchLatched()) {
        return true;
    }
    // 规则 = PC 的 `ModManager::AchievementsLocked()` **一比一**（2026-09-24 批次 098 取证；
    // 逐条反汇编见 `runtime_constants.hpp` 的 `SetReadOnly` 那一段）：
    //   ① 模组列表为空 ⇒ 不锁；
    //   ② 任一模组启用 ⇒ 读 `PersistentGameData::Unlocked(4)` 取反
    //      ⇒ 「有模组开着 且 成就 #4（打过妈妈）未解锁」= 锁。
    //
    // ★ ① 用**处于"启用状态"**的真实模组数（`ModMenuEnabledCount()`；口径 = 模组页开关那一份，
    //   与页面上看到的一致，**不看有没有重启**）。
    //   ★★ 2026-09-24 批次 107 改成这一条（用户实测后裁定"按 PC 口径"）：原来的口径是
    //   `ModMenuActiveCount()`（**本局开机时真的加载了几个**），而模组是**开机那一刻**按
    //   存档里的开关过滤后加载的 ⇒ "开关开了但还没重启就进局"时它是 0 ⇒ **漏判**
    //   （真机实测：开着模组进局却照样给成就）。PC 的 `ModManager::AchievementsLocked()`
    //   走的是**列表里每一项的启用位**，界面上一开就变、不需要重启 ⇒ 那才是 PC 语义。
    //   ⇒ 顺带也是对的：**开关关掉**（哪怕本局还加载着）⇒ 不锁，与 PC 一致。
    //   （097 之前那种 fail-closed"发现没出结果就按有模组算"仍然不许回来：那是我们自创的，
    //    会在开机那几秒把**该给的**成就也吞掉。）
    if (isaac::runtime::ModMenuEnabledCount() == 0) {
        return false;
    }
    // ★ 这里**不看**是哪一个成就（批次 096 撤掉 093 给 #4 开的豁免）：妈腿成就本身也不豁免 ——
    //   关掉模组之后本函数一律返回 false，所以不会锁死。
    // ② 打过妈妈没：**直接读持久位**（`PersistentGameData+0x28+成就号`，成就 #4 = 打过妈妈）。
    //    拿不到持久数据 ⇒ 按"没打过"（= 锁）—— 与 PC 同方向（读不到存档也不会放行成就）。
    if (persistentGameData == nullptr) {
        return true;
    }
    std::uint8_t wombByte = 0;
    if (!engine_memory::ReadField(
            engine_memory::AddressOf(persistentGameData),
            kPersistentAchievementArrayOffset + kAchievementWomb, &wombByte,
            &engine_memory::EngineMemoryReadable, 0)) {
        return true;  // 读不到 ⇒ 同"没打过"（= 锁）：与上面那条同方向
    }
    return wombByte == 0;
}

// ── 「开模组 ⇒ 禁成就」：**必须每帧都跑，而且在任何游戏状态下都要跑** ──────────────
//
// ★★ 为什么把它单独抽出来、并在 `ModMenuNativeUpdate` 的**最开头**调用
//    （2026-09-23 真机定位到的根因，这一条是整个"禁成就"一直不生效的原因）：
//
//    `ModMenuNativeUpdate` 里有一道**很早的早退** —— `g_MenuManager`（菜单管理器）
//    "随菜单生命周期出现/消失"（那行注释的原话），**读不到就直接 `return`**。
//    而**在一局游戏里菜单管理器根本不存在** ⇒ 那道早退会命中 ⇒ 原本放在它后面的
//    "写禁成就那两位"**一整局都不会执行**。
//    偏偏 `Game::Start` 是在**开局那一刻**把只读位清成 0 的（`SetReadOnly(false)`）
//    ⇒ 那一局从头到尾都允许成就 ⇒ 用户看到的"成就照样弹"。
//
//    真机读数正是这个形状：真内存 `Manager+0x36D4D = 1`（进局前写下的、没人清），
//    但 `PersistentGameData+0x1 = 0`（开局被清之后**再没写过**），
//    而状态面里那些"看起来对"的值全是**进局前**那一帧的旧值。
//
//    ⇒ 修法就是这一处：**把它挪到早退之前**，让它与菜单/局内状态无关地每帧执行。
void UpdateAchievementDisallow(const TargetModule& module) {
    // ★★ 批次 120：先做掉"局边界"挂上的存档分区 I/O（读/写那个"污染过"标记）。
    //   位置选在这里有两个理由：
    //     ① 这是**游戏线程**（端口的实现只允许游戏线程操作存档分区）；
    //     ② 它与菜单/局内状态无关 ⇒ 放在下面那道早退**之前**，不会被"菜单管理器不存在"挡住。
    RunTaintFileTick();
    std::uintptr_t manager = 0;
    if (!ReadSingleton(module, kManagerSlotOffset, &manager) || manager == 0) {
        return;
    }
    g_Menu.manager = manager;
    // 「开模组 ⇒ 禁成就」的**查询结果**（读数用）—— 规则与 PC 的 `ModManager::AchievementsLocked()`
    // 一比一：**有真实模组实际加载** 且 成就 #4（打过妈妈）未解锁 ⇒ 该禁；其余一律不锁。
    // ★★ 2026-09-24 批次 098：这里**只算、只记**，一个引擎字节都不写 —— 真正落地在
    //    `SetReadOnly` 入口中继那一步（`hook_manager.cpp`）。闸门从 `TryUnlock` 挪到那里，
    //    因为 `TryUnlock` 只是**查**只读位，`SetReadOnly` 才是**写**它的地方（全镜像唯一）。
    // ★★ 2026-09-24 批次 107（用户裁定"按 PC 口径"）：判据从"**实际加载**的那批"改成
    //    "**处于启用状态**的那批"（`ModMenuEnabledCount`）—— 理由与实测见
    //    `AchievementsShouldBeBlockedFor` 里那一段。这一格同时记下**两个**数（启用 / 实际加载），
    //    因为"读不出到底是哪一种"正是上次定位时最费时间的地方。
    {
        // ★★ 2026-09-24 批次 107：这两格**必须分开记**（它们回答的是不同的问题，
        //    混成一个正是"开着模组进局却照样给成就"那次读不出来的原因）：
        //    * `enabledRealMods` = **处于启用状态**的（判据用的就是它，PC 口径）；
        //    * `activeRealMods`  = 本局**开机时真的加载了**几个（诊断用）。
        const auto active = static_cast<std::uint32_t>(isaac::runtime::ModMenuActiveCount());
        const auto enabled = static_cast<std::uint32_t>(isaac::runtime::ModMenuEnabledCount());
        g_Menu.activeRealMods = active;
        g_Menu.enabledRealMods = enabled;
        // ★ 批次 116：把"发现清单"的自证四格填上（见状态面 `.hpp` 的 [41]..[44]）。
        //   为什么非要有它们：上面那两个是**汇总数**，而待修记录里出现过"`[40] = 0` 但
        //   开关服务读不出来时本该默认全都开着"这种矛盾 —— 只看得汇总数分不出是
        //   "状态文件写着全禁用"、"清单是空的"，还是"发现这一步根本没跑到"，而这三者的处置不同。
        {
            const isaac::runtime::ModMenuDiscoveredReading discovered =
                isaac::runtime::ModMenuDiscoveredForReading();
            g_Menu.discoveredRealMods = discovered.count;
            g_Menu.discoveredEnabledMask = discovered.enabledMask;
            g_Menu.discoveredActiveMask = discovered.activeMask;
            g_Menu.discoveryDone = isaac::runtime::ModMenuDiscoveryDone() ? 1U : 0U;
        }
        bool wombUnlocked = false;
        // ★ 批次 117：把"成就那一段读到没有"提到外层 —— 闩锁的置位判据要**正面证据**
        //   （"读不到持久位"不能当成"没打过妈腿"去置位，那会变成 fail-closed：
        //   红线是"闩锁只许由正向证据置位"，见 `.hpp`）。
        bool achievementBitsOk = false;
        std::uint32_t achievementSample = 0;
        if (g_Menu.manager != 0) {
            // 一次读 8 个字节就够：抽样要 0..3，成就 #4（`kAchievementWomb`）落在同一个块里
            // （那个数组从 `PersistentGameData+0x28` 起、**按成就号逐字节索引**）。
            std::array<std::uint8_t, 8> bits{};
            achievementBitsOk = engine_memory::ReadField(
                g_Menu.manager,
                kManagerPersistentGameDataOffset + kPersistentAchievementArrayOffset, &bits,
                &engine_memory::EngineMemoryReadable, 0);
            // 抽样 0..3（读出来应当全是 0/1 —— 读数里用来自证"位置没读错"）。
            // ★ 读不到就全 0：读数里一眼看得出"这一段没读到"，比留着上一次的旧值不容易误读。
            achievementSample =
                achievementBitsOk ? (static_cast<std::uint32_t>(bits[0]) |
                                     (static_cast<std::uint32_t>(bits[1]) << 8) |
                                     (static_cast<std::uint32_t>(bits[2]) << 16) |
                                     (static_cast<std::uint32_t>(bits[3]) << 24))
                                  : 0U;
            wombUnlocked = achievementBitsOk && bits[kAchievementWomb] != 0;
        }
        g_Menu.achievementSample = achievementSample;
        g_Menu.wombAchievementUnlocked = wombUnlocked ? 1U : 0U;
        // ★★ 批次 117：**局内单向闩锁的每帧观察点**，同时也是"中途开启模组"那一下的**边沿写位点**。
        //
        // 为什么观察放在这里（而不是只放在中继里）：本次更新**在一局里也跑**（理由见本函数
        // 上方那段），而"玩家在局内把模组打开"这件事**只有在这里才看得到** ——
        // 引擎那次写只读位早在开局就发生过了（那 24 个调用点全在开局路径上），不会再来第二次。
        //
        // 判据（**只认正向证据**）：真实模组处于启用状态 **且** 成就那一段**确实读到了**
        // 且成就 #4 未解锁。读不到那一位时**不置位、也不写** —— 这既守住了"不许 fail-closed"
        // 的红线，也避免在开局头几帧（存档还没建好）把成就误锁。
        if (ObserveRunLatch(enabled != 0 && achievementBitsOk && !wombUnlocked)) {
            // 0→1 那一下：把只读位**主动**写下去。不写就等于"中途开启模组"这一局没生效
            // （引擎不会再写它，而中继只在引擎调用时才机会）。
            WriteAchievementReadOnly(engine_memory::AsObject(
                g_Menu.manager + kManagerPersistentGameDataOffset));
            // ★★ 批次 120：把这个"污染"记进**存档分区** —— 跨重启那条路就靠这个文件
            //    （内存里的闩锁/留存都会随重启消失）。文件里已经是"污染过"时不重复写：
            //    "继续"接回来的那一次正是这种情形（刚读过它就是 1）。
            if (g_TaintFileState != kTaintFileTainted) {
                WriteRunTaintFile(true);
            }
        }
        if (g_Menu.manager != 0) {
            // 只读位仍**被读**（它是现场真值，也是 `TryUnlock` 唯一查的东西）—— 但**不写**。
            // 写法上先算出地址再用 `ReadAt`：本文件那条门禁按 `kPersistentReadOnlyOffset,` 这个
            // 形状判"有没有人拿它当**写目标**"（写点必然把它当参数、后面跟逗号）—— 别改成那种形状。
            const std::uintptr_t readOnlyAddress =
                g_Menu.manager + kManagerPersistentGameDataOffset + kPersistentReadOnlyOffset;
            std::uint8_t readOnlyValue = 0;
            const bool readOnlyOk = engine_memory::ReadAt(readOnlyAddress, &readOnlyValue,
                                                          &engine_memory::EngineMemoryReadable);
            g_Menu.achievementsReadOnly = (readOnlyOk && readOnlyValue != 0) ? 1U : 0U;
            // ★★ 查出来的"该不该禁"必须与**判据本身**同一个口径 ——
            //    否则读数会告诉你"不该禁"，而闸门那边其实是按另一个数在判，等于读数说谎。
            //    ★ 批次 117 起那个口径里多了**闩锁**那一层（`RunLatchLatched()`）：本局里出现过
            //    "开着模组 且 妈腿未解锁"就一直是 1，所以"关了模组仍然该禁"这件事在读数里
            //    也看得见（否则现场会以为什么都没发生）。
            g_ModMenuState.achievementsDisallowed = static_cast<std::uint32_t>(
                (RunLatchLatched() || (enabled != 0 && !wombUnlocked)) ? 1U : 0U);
            // 这几格也**跟着每帧填**（不能留在函数尾部 —— 尾部在"一局里"根本不会执行，
            // 读数就会是进局前的旧值，这正是 2026-09-23 那几轮读不懂现场的原因之一）。
            g_ModMenuState.activeRealMods = g_Menu.activeRealMods;
            g_ModMenuState.enabledRealMods = g_Menu.enabledRealMods;
            // 批次 116：发现清单自证四格 —— 与上面两格**同一处发布**（分两处填必然漂）。
            g_ModMenuState.discoveredRealMods = g_Menu.discoveredRealMods;
            g_ModMenuState.discoveredEnabledMask = g_Menu.discoveredEnabledMask;
            g_ModMenuState.discoveredActiveMask = g_Menu.discoveredActiveMask;
            g_ModMenuState.discoveryDone = g_Menu.discoveryDone;
            g_ModMenuState.wombAchievementUnlocked = g_Menu.wombAchievementUnlocked;
            g_ModMenuState.achievementSample = g_Menu.achievementSample;
            g_ModMenuState.persistentReadOnly = g_Menu.achievementsReadOnly;
        }
    }
}

void ModMenuNativeUpdate() noexcept {
#if defined(EXL_DIAGNOSTIC_STAGE)
    // ★ 诊断阶段构建的行为**一个字都不变**（那些构建是别的调查在用的）：这里直接什么都不做
    // —— 连一次引擎读都不发生，与"调用点不调"完全等价。
    //
    // ★★ 为什么守卫放在**函数体开头**而不是 `hook_manager.cpp` 的调用点：
    // `runtime/tests/test_stage118_managed_file_write_diagnostic.py` 用
    // `#if !defined(EXL_DIAGNOSTIC_STAGE)` 当**切片结束符**去取 `ManagerUpdateHook::Callback`
    // 那一段（它要确认那里有一句"跑原函数"），在调用点再插一条同样的条件会让它切早、
    // 把那一句切出去 ⇒ 那条既有门禁会红（2026-09-23 批次 077 实测）。
    // 放这里效果相同、也不动别的门禁的解析口径 —— **别挪回调用点**。
    return;
#endif
    const std::optional<TargetModule> module = FindTargetModule();
    if (!module.has_value()) {
        g_ModMenuState.failure = kFailureModuleNotFound;
        return;
    }
    // ★★ 这两件事必须在**任何游戏状态下**都执行 —— 尤其"在一局里"（那时菜单管理器不存在，
    //    下面那道早退会命中）。理由见 `UpdateAchievementDisallow` 上方那段。
    UpdateAchievementDisallow(*module);
    ++g_ModMenuState.drivenFrames;  // [34] 每帧 +1：唯一能证明"我们还在跑"的一格
    // `g_MenuManager` 是这一切的前置条件（它随菜单生命周期出现/消失）。
    std::uintptr_t menuManager = 0;
    if (!ReadSingleton(*module, kMenuManagerSlotOffset, &menuManager) || menuManager == 0) {
        g_SlotInit = 0;        // 离开菜单 ⇒ 下次进来重新取初值
        g_RestoreOurs = 0;     // 连菜单都离开了 ⇒ "回到我们那一格"这件事作废
        g_Menu.menuManager = 0;
        g_Menu.menuState = 0;
        g_Menu.pageWasActive = 0;
        return;
    }
    g_Menu.menuManager = menuManager;
    g_Menu.menuState = ReadMenuState(menuManager);
    // `g_Manager`（条目表与字体对象都在它里面）与可见屏幕尺寸：每帧顺手刷新。
    std::uintptr_t manager = 0;
    if (ReadSingleton(*module, kManagerSlotOffset, &manager)) {
        g_Menu.manager = manager;
    }
    RefreshScreenSize(*module);
    ResolveLanguage();
    // 语言变了 ⇒ 把模组页按新语言重载一次（贴图会跟着换；**排版的不足**见函数注释）。
    // ★ 放在这里（每帧更新、引擎 `Manager::Update` 之前）而不是渲染回调里：那一下会 `ANM2::Load`，
    //   不能在渲染批次中间动引擎对象。页面当前没显示时才会真的动手（见函数注释）。
    ReloadPageForLanguage(*module);

    const std::uintptr_t thunk = LuaRuntime::InputIsActionPressedThunk();
    if (thunk == 0) {
        g_ModMenuState.failure = kFailureInputUnavailable;
        return;
    }
    // 这个 thunk 是运行时自己解析好、记下来的（不是"模块基址 + 偏移"）⇒ 只需转换一次签名：
    // 走引擎调用层的 `AsFunction`（批次 108），调用点里不留 `reinterpret_cast`。
    const auto query = engine_call::AsFunction<ActionQueryFn>(thunk);

    // 页面的一次性 `ctor` + `Init`：**在菜单一出现时就做**（探针的"自动驱动"同一形状）。
    // 为什么要提前做而不是等用户按确认：条目表要**等发现结果**（最多 900 帧），而 `Init` 必须
    // 在表写好之后 —— 等到按键那一刻再做，用户会看到"按了没反应"。此处不在任何渲染批次中间，
    // 引擎建贴图/ANM2 的那些锁与状态都干净（避免重入）。
    if (g_Menu.pageInitState == kInitNotTried && TryPrepareModsVector()) {
        InitManualPage();
    }
    // 发现结果后来才到（启动扫描比菜单慢）：表只在"目录数变了"时重写一次。
    // ★ 这里**不重跑 `ctor`/`Init`**：页面对象已经建好（`Init` 会把 ANM2 载进来），重跑等于
    //   再加载一份。`Menu_Mods::Render` 每帧都从 `g_Manager+0x36800` 现读 begin/end ⇒
    //   换表立刻生效，不需要重建页面。
    if (g_Menu.vectorWritten != 0 &&
        g_Menu.writtenDirectories != isaac::runtime::ModMenuDiscoveredCount()) {
        g_Menu.vectorWritten = 0;
        g_Menu.prepareAttempts = 0;
        TryPrepareModsVector();
    }

    if (g_Menu.menuState == kGameMenuState) {
        ModRowUpdate(*module, query);
    } else {
        g_SlotInit = 0;  // 离开那一屏 ⇒ 下次进来重新按引擎行号取初值
    }
    // 模组页（状态 16）期间由我们驱动那一页。与上面同一时机 —— 都在引擎 `Manager::Update`
    // 之前，所以"我们这一帧切的状态"引擎这一帧就按新状态分派。
    ModsPageUpdate(*module, query);
    // 位置：只在状态 16 里算/写（`Menu_Mods::Render` 每帧会改写那一格的 Y）。
    if (isaac::runtime::ModPageIsActive(g_Menu.menuState)) {
        UpdatePagePosition(menuManager);
    }
    // 留证：本页**实际**被画的点（= 偏移 + 本页位置 + 200）。过渡期间它会动（纸跟着画布滑），
    // 停稳后应当是 (173, 72) ⇒ 读数里这一格就是"动画在不在动 / 摆对了没有"的直接证据。
    {
        float offset[2] = {0.0F, 0.0F};
        float page[2] = {0.0F, 0.0F};
        const bool observed =
            engine_memory::ReadField(menuManager, kMenuManagerCanvasOffset, &offset,
                                     &engine_memory::EngineMemoryReadable, 0) &&
            engine_memory::ReadField(engine_memory::AddressOf(g_ModsObject), kPagePositionOffset,
                                     &page, &engine_memory::EngineMemoryReadable, 0);
        // 读不到就把这两格写成 0：那是个**一眼看得出不对**的值（正常是 (173, 72)），
        // 比留下上一次的旧值更不容易被当成"当前现场"。
        const float originX = observed ? offset[0] + page[0] + kModsRenderExtraX : 0.0F;
        const float originY = observed ? offset[1] + page[1] : 0.0F;
        std::memcpy(&g_ModMenuState.pageOriginX, &originX, sizeof(originX));
        std::memcpy(&g_ModMenuState.pageOriginY, &originY, sizeof(originY));
    }
    // ---- [22]..[25]：2026-09-23 定位"换语言后 EID 坏掉"用的观测（**只读**，不动引擎）----
    //
    // 为什么要这几格：那条 bug 的根因是"引擎重建挂载点表之后，我们没能把 Mod 的挂载点挂回去"
    // （`SetSessionContentMountService` 从来没被调用 ⇒ 中继拿不到实例）。有了这几格，
    // 真机读数就能直接回答"中继跑没跑、恢复成功没、字体为什么没装上"，不用再猜。
    g_ModMenuState.mountRelayFired =
        IsaacModRuntime_RebuildContentMountPointsRelayFiredCount();
    g_ModMenuState.mountRelayFailures =
        IsaacModRuntime_RebuildContentMountPointsRelayFailureCount();
    g_ModMenuState.mountServicePublished =
        isaac::runtime::SessionContentMountService() != nullptr ? 1U : 0U;
    g_ModMenuState.lastFontLoadWord = isaac::runtime::LastFontLoadWordForProbe();
    // [27]..[30]：`metadata.xml` 三种结果与"真实模组"个数（2026-09-23 批次 085）
    g_ModMenuState.metadataRootRelativeHits = g_Menu.metadataRootRelativeHits;
    g_ModMenuState.metadataPrefixedHits = g_Menu.metadataPrefixedHits;
    g_ModMenuState.metadataMisses = g_Menu.metadataMisses;
}

} // namespace isaac::runtime::modmenu
