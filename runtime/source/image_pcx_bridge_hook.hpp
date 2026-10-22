#pragma once

#include "game_file_reader.hpp"

#include <cstdint>
#include <cstring>

namespace isaac::runtime::bridge {

// 挂载解析出来的路径是不是**模组自己的文件**（`rom:/isaac_mods/…`）。
//
// 为什么需要它（2026-09-21，用户装的 `visible tinted rocks` 一个像素都不显示）：
// PC 模组的贴图是 PNG，而它要覆盖的目标在 Switch 版本体是**已存在的 `.pcx`**；
// 桥过去只要 `original(path)` 答得出来就直接交回 ⇒ 模组的 PNG **被静默忽略**。
// 新规则要区分"这个 `.pcx` 是模组自带的（那就用它）"与"这是本体那份（那就该让位给模组的 PNG）"，
// 判据就是这个路径形状。
//
// 依据：`IContentManager::GetMountedFilePath` 返回的是带 `rom:/` 前缀的完整挂载路径，
// 模组文件都在 `rom:/isaac_mods/` 下（Stage147 真机读数，见 `docs/问题与解决记录.md:4872`）。
[[nodiscard]] inline bool IsModMountedPath(const char* mounted) noexcept {
    constexpr char kModsRoot[] = "rom:/isaac_mods/";
    return mounted != nullptr && std::strncmp(mounted, kModsRoot, sizeof(kModsRoot) - 1) == 0;
}

// 把两组绑定交给贴图桥（安装期调用一次）。
//
//   * `fileBindings`   = 读文件那一组（用来读 `.png` 的字节）；
//   * `engineBindings` = 引擎入口那一组（对象级内存加载 / zlib / 路径解析 / 分配释放）。
//
// 传的是 `hook_manager.cpp` 里那两个**静态绑定对象的地址**：桥在回调里现读，
// 所以绑定之后被（重新）发布时不需要再通知，也不会有"拷贝过期"的问题。
// 任一为 nullptr 时桥处于"未挂上"状态：所有回调直接放弃（绝不盲开、绝不乱调引擎）。
// 441更正：生产准备服务现在传入自身持有的不可变快照；指针以release/acquire发布读取，
// 不再让读取中的消费者依赖外部加载缓冲的后续重填。
void Attach(const GameFileReader::Bindings* fileBindings,
            const GameFileReader::ImagePcxBindings* engineBindings) noexcept;

// 批次 353/354（2026-10-04）：把"我们实际登记了哪些模组目录、登记成没成功"记进诊断结构体
// （读数工具按固定偏移读）。
//
// 为什么需要它：minimapi 自带的 `resources/gfx/ui/minimap1.anm2` 没能覆盖本体那份，而 353 的读数
// 已经把范围缩小到"**模组独有的路径在 `GetMountedFilePath` 上直接答空**" —— 于是第一要务变成
// "**挂载到底成功没有、失败在哪个叶子**"。353 那版只记了"这个目录被尝试登记过"，
// 但调用点把 `RegisterMod` 的返回值**丢掉了**（`(void)…`）⇒ 记下的名单里
// **成功与失败混在一起**，说明不了问题。
//
// 本函数把三样一起记：目录名、`StatusCode` 的数值、**失败落在哪个叶子**（`0xFFFFFFFF` = 没有失败）。
// **只留痕，不改任何行为**；调用点在 `hook_manager.cpp` 的 `ManifestLoadStep::Mounts`。
void RecordModMountResult(const char* directory, unsigned statusCode, unsigned failedLeaf) noexcept;

// 批次 356（2026-10-04）：**"刚挂完就问一次"** —— 在模组挂载收尾那一刻，用引擎的路径解析问一条
// **模组独有**的路径，把回答单独留痕（`modMountTime*` 三格）。
//
// 为什么要它：354 的读数说"应用根相对能命中模组、叶子相对不能"，但**看不出**这是
// "挂载当时就解析不到"还是"挂载之后**后来**被清掉"（引擎的 `RebuildContentMountPoints()` 开头就是
// `ClearMountPoints(false)`，而本会话那个中继的计数是 0 —— 所以"中继装上"与"引擎初始化内容表"
// 谁先谁后，目前没有读数）。把这一问放在挂载收尾，就把时间轴切成了两段。
//
// 调用点在 `hook_manager.cpp` 的 `ManifestLoadStep::Mounts` 收尾（全部模组挂完那一下）。
// **只读**：走的是中继的**原函数**入口、返回串按引擎的 `operator delete[]` 归还，不改任何状态。
void ProbeMountVisibilityAfterMounting() noexcept;

// ── 批次 357（2026-10-04）：把"挂载点什么时候没的"切成多段 + 试一次重挂 ────────────────
//
// 356 的读数把结论钉死在"挂载收尾那一刻叶子相对**能**命中、游戏里**不能**" ⇒ 挂载点**中途消失**。
// 下面这几个入口就是为此加的（全部**只读**，只有 `TryRemount` 那条会调引擎的挂载器，且只调一次）：
//
//   * `NoteMountVisibilityCheckpoint(index)`：在**时间轴的不同点**用同一句查询（叶子相对）问一次，
//     把结果记成一位（`mountVisibilityBitmap` 的 bit index）。调用点：
//       0 = 模组挂载收尾｜1 = 内容步收尾｜2 = 第一个 update 回调｜3 = 第一次非 `.pcx` 查询
//     ⇒ 哪一段之间"有效"变"无效"，就是清理点所在的那一段。
//   * `NoteRebuildMountPointsRelayInstalled(ok)`：**重建挂载点中继装上没有** —— 346 起一直在读
//     "跑过 0 次"，但"没跑"与"没装"是两件事，必须分开。
//   * `NoteRemountResult(code)` + `ProbeMountVisibilityAfterRemount()`：在 update 帧上试一次
//     `RemountAll()`，随后**立刻**再问同一句 ⇒ 直接验证"重挂能不能让它回来"（修法的原型）。
//   * `NoteRebuildRelayVerifyDetail(code, target16, stub16, slotLow)`：357 证明那个中继**压根没装上**，
//     这一格把"**卡在哪一条**"与**现场 16 字节**一起留下（失败码表在 `hook_manager.cpp` 里）⇒
//     一眼分出"入口分支没打上" / "代码洞桩不对" / "槽被占了"。**只读。**
void NoteRebuildRelayVerifyDetail(unsigned failureCode, const void* target16,
                                  const void* stub16, unsigned slotLow32) noexcept;

// ── 批次 359（2026-10-04）：**把探针从死代码挪到活的那条路上** ─────────────────────
//
// 358 的读数给了"失败码 = 0、现场字节全 0" ⇒ 那说明**那个安装函数压根没被调用过**。
// 本地一查就明白了：挂点目录（`hook_catalog.hpp`）把 `RebuildMountPoints` 的后端定成
// **`EntryRelay`**，所以真正在跑的是 `entry_relay_hook_adapter.cpp` 里那条入口中继；
// `exlaunch_hook_adapter.cpp` 里的 `case HookId::RebuildMountPoints` **是死代码**。
// ⇒ 358（以及 357 的 `rebuildRelayInstalled`）**测的是一段永远不会执行的代码**，结论作废。
//   真正该记的是这三格（都在**活的**路径上）：
//   * `entryRelayRebuildInstalled` / `entryRelayRebuildFailure`：入口中继装上了没有、失败码多少；
//   * `entryRelayRebuildCalls`：**我们那层包装被调用了几次** —— 0 次就意味着
//     "引擎清空挂载点表**根本不经过** `RebuildContentMountPoints`"（那就不能在它身上挂钩子）。
void NoteRebuildMountPointsEntryRelay(bool installed, unsigned failureCode) noexcept;

// ── 批次 360（2026-10-04）：**修法** —— 让模组挂载点"自愈"地保持有效 ────────────────
//
// 359 的读数把 357 的结论钉死：入口中继**装上了**，但引擎**一次都不调**那个函数
// （包装调用 0 次）⇒ **引擎清空挂载点表根本不经过 `RebuildContentMountPoints`**。
// ⇒ 在这条路上挂钩子（不管入口中继还是 Stage-48 补丁）**永远救不了**。
//
// 而 357 已经实测证明：**补挂有效**（`RemountAll()` 之后再问同一句就命中了）。
// ⇒ 本函数就是那个修法：**先把"模组挂载点还在不在"量出来；不在就立刻补挂并复验**。
// 调用点在 `hook_manager.cpp` 的 update 回调：主循环第一帧补一次（那时引擎的内容表已定），
// 之后每固定若干帧检查一次 ⇒ **无论引擎用什么方式、在什么时候清表，模组挂载点都会被拉回来**。
//
// ★ 为什么这样是"与 PC 一致"而不是"凑合"：PC 上模组的 `resources/` 目录**始终是挂着的**，
//   引擎内部怎么重建自己的内容表都不影响它。这里做的正是把那件事**维持住**。
// ★ 只读 + 幂等：还在时**一个字节都不改**；只有量到"不在了"才调引擎的挂载器。
void EnsureModMountsAlive() noexcept;

// ── 批次 361（2026-10-04）：**修上一批的判据错误 + 在正确时刻量"共享路径归谁"** ─────────
//
// 360 的读数把上一批的结论推翻了：看门狗检查 **43 次、一次都没发现"模组挂载点丢失"**
// ⇒ 挂载之后再问"模组独有"的路径**一直答模组**。回头一看，问题出在**我把位图当成了时间序**：
//   * bit2 记在 **update 回调第 1 帧** —— 那一帧**模组还没挂**（挂载要等清单加载那几十帧跑完）
//     ⇒ "答空"是"**还没挂**"，不是"被清掉"；
//   * bit3 记在"第一次非 `.pcx` 查询"，那也发生在**开机早期、挂载之前**（引擎启动时就大量查字体/音乐）；
//   * 真正在挂载过程中记的 bit0/bit1 反而是**命中**。
// ⇒ "消失点在内容步收尾与第一个 update 之间"**站不住**；357 那句"重挂能救回来"也随之**不可信**。
//
// 于是真正没被回答的问题变成：**挂载确实在的情况下，一条"本体和模组都有"的共享路径归谁？**
// 而 352/353 那三次探测**全跑在挂载之前**，等于没量。
//
// 本批做三件事：
//   ① `RunSharedPathProbes` 每次探测**连"当时的模组数 + 一个自增序号"一起记**
//      ⇒ 读数能自己判断"这一次是不是跑在挂载之前"，不再犯同一个错；
//   ② `RunLateRemountTrial()`：在**挂载之后的已知晚点**（update 第 N 帧，且模组数 > 0）
//      对**共享路径**做一对"**重挂前 / 重挂后**"的测量，同时对"模组独有"路径也量一次；
//   ③ 这一对测量同时干两件事：**定性病根**（注册顺序？）与**验证修法**（把模组挂载点补到最后）。
void RunLateRemountTrial() noexcept;
void NoteRebuildMountPointsEntryRelayCallbackFired() noexcept;
void NoteMountVisibilityCheckpoint(unsigned index) noexcept;
void NoteRebuildMountPointsRelayInstalled(bool installed) noexcept;
void NoteRemountResult(unsigned statusCode) noexcept;
void ProbeMountVisibilityAfterRemount() noexcept;

// ── 批次 418（2026-10-09）：转码结果缓存的**实际占用**（只读；填状态面 `[80]`） ──────────
//
// 24 MiB 是那个缓存的**预算**，不是占用。417 的读数把"模块堆已用 120.8 MB"里的 Lua 侧
// （36.8 MB）分出来之后，剩下 ≈84 MB 归因不到任何一条代码缓冲 ⇒ 先把"带预算的缓存到底
// 驻留了多少"量出来。定义在 `image_pcx_bridge_hook.cpp`；调用点 = `mod_menu_native.cpp`
// 的 60 帧节拍。**不改变缓存行为**，也**不**要求调用方按对象偏移硬读 `used_bytes_`。
[[nodiscard]] std::uint32_t ImagePcxCacheUsedBytes() noexcept;

} // namespace isaac::runtime::bridge
