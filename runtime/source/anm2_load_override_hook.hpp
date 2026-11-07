#pragma once

#include <cstdint>

// 2026-10-25置顶更正：下面363批的原设计说明仅作历史保留，不能据其减活引用。
// 369真机已证伪“LayerData拷贝、释放安全”：LayerState实际引用缓存数据，强清会释放后使用。
// 当前中继仅回收引用已为0的条目；热切换须由native_game_resource_reload按原生所有权
// 先释放并重建存活消费者，再回收缓存，不准调用RemoveReference伪造零引用。

// ============================================================================
// `ANM2::Load` 入口中继 —— 让"模组覆盖本体资源"真正生效
// ============================================================================
//
// **要补的那一环**：引擎开机时自己就把 `gfx/ui/minimap1.anm2` 这类**共享路径**按"本体层"
// （`rp_patch/resources` 前缀）读进了动画缓存；我们的模组挂载点是约 5 秒后由 worker 追加的。
// `AnmCache::Load2` 的查找是"挂载点前缀 + 路径哈希、**第一个命中的键胜出**" ⇒ 之后每一次
// `Load`（包括 minimapi 自己那次）都命中那份本体旧条目、**连路径解析器都不问** ⇒ 模组自带的
// 那份永远赢不了。PC 上模组资源在引擎第一次加载之前就已经在挂载点里，所以 PC 没有这���现象。
//
// **本中继做的事**（只在"确实需要"时动手，其余情况一次前缀比较就返回）：
//   ① 从 libc++ 的 24 字节串里取出路径（短串内联在对象 +1，长串指针在对象 +16）；
//   ② 路径为空、或不是 `gfx/` 开头 ⇒ 直接跑原函数；
//   ③ 问引擎自己的解析器（`IContentManager::GetMountedFilePath`）这条路径现在归谁；
//   ④ 答的**不是**模组目录（`isaac_mods`）⇒ 直接跑原函数；
//   ⑤ 是模组目录 ⇒ **只读**遍历 `g_AnmCache`，找出"本条路径在别的挂载点前缀下的键"
//      （候选键由我们自己按挂载点表算，绝不遍历字符串）；命中且计数 > 0 ⇒ 用引擎自己的
//      `RemoveReference` 把它减到 0 ⇒ `FreeUnreferencedEntries()` 回收；
//   ⑥ 按原样调原函数 ⇒ 这次不命中 ⇒ `Preload2` 开文件 ⇒ 解析器给模组那份。
//
// **为什么作废是安全的**：命中缓存时 `Load2` 是把条目数据**拷进调用者的 ANM2**（贴图走
// `SmartPointer` 计数）⇒ 已经加载过的 ANM2 手里有自己的副本，作废缓存条目不会让它们悬空。
//
// **为什么必须先读计数**：`AnmCache::RemoveReference` 在计数为 0 时**先打日志再减**
// （`0x14E3C`–`0x14E5C`）⇒ 会下溢��� 0xFFFFFFFF。所以这里只在计数 > 0 时按读到的数减。

struct TargetModule;

namespace isaac::runtime::bridge {

// 安装结果（读数用）：0 = 还没试过，1 = 装上了，2 = 没装上（失败码见下）。
void NoteAnm2LoadRelayInstalled(bool installed, unsigned failureCode) noexcept;

// 中继被调到的次数（每帧都可能有，所以只累加，不做别的）。
void NoteAnm2LoadRelayCallbackFired() noexcept;

// 最近一次"确实需要动手"的判定结果：
//   * `pathHash`   —— 最近一条"解析器答模组层"的路径哈希（DJB2，与引擎同一个算法）；
//   * `staleFound` —— 该路径在别的挂载点前缀下**确实找到了旧条目**的次数；
//   * `evicted`    —— 真正把旧条目计数清零并回收的次数；
//   * `resolverAsked` —— 问过解析器的次数（分母，用来区分"没走这条路"与"走了但没命中"）。
void NoteAnm2LoadOverrideDecision(std::uint32_t pathHash, bool staleFound, bool evicted) noexcept;
void NoteAnm2LoadResolverAsked() noexcept;

// 只读一次引擎那张内容挂载点表（`g_ContentMountPoints`），
// 回答"里面有没有 `isaac_mods` 前缀" —— 这是"我们提前挂的挂载点到底进了引擎的表没有"
// 的第一个直接判据（`g_EarlyMountState.mountListHadModPrefix` 就是它）。
//
// 为什么放在这个 TU：那条表每项 8 字节 `const char*` 的口径是 2026-10-05 用反汇编 + 设备
// 实测定案的（见 `.cpp` 里 `kMountPointEntrySize` 那一大段注释），读法（`ReadMountPointAt`）
// 也只该有一份 —— 提前挂载那一步直接调这里，不在别处再抄一遍。
// 读不到（槽为空 / 表为空 / 某一项读不出来）一律返回 false（"没看到"），不猜。
[[nodiscard]] bool EngineMountPointListHasModPrefix(const TargetModule& module) noexcept;

// 中继回调要用的引擎侧绑定视图（安装时核对一次，之后只读）。
// 只暴��回调需要的三样：解析器、内容管理器、引擎自己的 `delete[]`。
struct Anm2LoadBindingsView {
    char* (*getMounted)(void*, const char*);
    void* contentManager;
    void (*freePath)(void*);
};

// 取当前绑定视图（没准备好时三个字段全空 ⇒ 回调直接跑原函数）。
const Anm2LoadBindingsView& Anm2LoadBindings() noexcept;

// 回退入口（跑原函数用；安装成功后由 hook_manager 发布进来）。
std::uintptr_t Anm2LoadFallbackEntry() noexcept;

// 安装时准备引擎侧绑定；返回 false = 绑定不齐（回调将退化为"什么都不做"）。
bool PrepareAnm2LoadOverride(const TargetModule& module);

// 发布回退入口（安装成功后调用；必须在 `PrepareAnm2LoadOverride` 之前或之后都可，
// 但两者都完成回调才真正生效）。
void PublishAnm2LoadFallbackEntry(std::uintptr_t entry) noexcept;

// 快照（读数工具按符号读；字段顺序即内存顺序，改动必须同步 `tools/read_device_state_via_gdb.py`）。
struct Anm2LoadOverrideState {
    std::uint32_t relayState;       // 0 未试 1 已装 2 未装
    std::uint32_t relayFailure;     // 安装失败码（0 = 无）
    std::uint32_t callbackCount;    // 中继被调次数
    std::uint32_t resolverAsked;    // 问解析器次数
    std::uint32_t staleFound;       // 找到本体旧条目的次数
    std::uint32_t evicted;          // 真正作废并回收的次数
    std::uint32_t lastPathHash;     // 最近一条"答模组层"的路径哈希
    // 2026-10-05：这一格原来只是"对齐保留（恒 0）"。现在它装的是扫描现场的两个事实
    //   （读数里一眼可见，免得再出现"静默早退、什么都看不到"）：
    //     bit0 = 1 ⇒ 引擎那张挂载点表里**没见过任何模组前缀**（`isaac_mods`）：
    //                它是开机快照；此时"从挂载路径反推 owner 前缀"不成立，我们按"每个键都算压着模组"处理；
    //     bit1 = 1 ⇒ 出现过"同一路径本会话已作废过 ⇒ 跳过"的情况（防"每次加载都白开一次文件"的空转）。
    std::uint32_t mountListFlags;
    // 本条中继"第一次被调用"的时刻（`RuntimePerfTick()` 的低 32 位；0 = 还没被调过）。
    //
    // 为什么加它（钉真因，别再靠拼推断）：真机读数显示引擎在 **`Game::Init`（+4214.7 ms）**
    // 里就读了 `gfx/ui/minimap1.anm2`（`Game::Init+0x340` → `Minimap::Init` → `ANM2::Load`），
    // 而我们的 21 个生产挂点（含本条中继）是 worker 那 **5 秒等待结束之后（≈ +5752.7 ms）** 才装的
    // ⇒ 由此**推断**"那次读根本没走我们的中继"。这一格把推断变成可观测：
    //   * 与 `g_EarlyMountState.callbackFirstFiredTicks`（`Game::Init` 被调的时刻）**同源同单位**（1 ms = 19200 tick）
    //     ⇒ 两者一比就能回答"我们的中继是早于还是晚于 `Game::Init` 首次生效"；
    //   * 若 `callbackFirstTicks` **晚于** `Game::Init` 的时刻 ⇒ 推断被证实（治法是"把资源类中继提前装"）；
    //   * 若**早于** ⇒ 推断被证伪，得另找原因（别再往那个方向改）。
    //
    // 只取低 32 位：19.2 MHz 的计数器在开机约 223 秒内不会回绕，而本判据只看开机后头几秒
    //   ⇒ 够用；要跨更长时间窗比较时再改成两格 u64。
    std::uint32_t callbackFirstTicks;
    // 对齐保留（恒 0；将来加字段先用它，保持"结构体大小按 8 字节对齐"）。
    std::uint32_t reservedAlign;
};

// `mountListFlags` 的位（见上）。
inline constexpr std::uint32_t kMountListNoModPrefixBit = 1u;
inline constexpr std::uint32_t kMountListRepeatSkipBit = 2u;

Anm2LoadOverrideState Anm2LoadOverrideSnapshot() noexcept;

// 状态面本体（外部链接，读数工具按符号名读；字段顺序必须与上面结构体一致）。
extern Anm2LoadOverrideState g_Anm2LoadOverrideState;

}  // namespace isaac::runtime::bridge
