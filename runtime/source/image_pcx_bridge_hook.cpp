// 贴图桥（`.pcx` 缺失时按需把同名 `.png` 转成 PCX 交给引擎）—— 独立实现文件。
//
// 2026-09-21 从 `hook_manager.cpp` 抽出来（评审第 2 条）：这段胶水自带状态（合成记录环形、
// 转码缓存、诊断结构体）并实现三条引擎入口回调，塞在 4000+ 行的 `hook_manager.cpp` 里既难读
// 也容易与挂点清单互相踩。抽出来后 `hook_manager.cpp` 只保留"注册 + 挂上绑定"两行。
//
// 交付点（来龙去脉见 `docs/评审-贴图桥架构与流程复盘-20260921.md`）：
//   ① `IContentManager::GetMountedFilePath`：`.pcx` 不在任何挂载点、但同名 `.png` 在时，
//      返回一条**合成的 `.pcx` 路径**，并记下 {完整合成路径 → 该 `.png` 的真实挂载路径}；
//   ② `ImagePcx::Load`：原函数打不开合成路径 ⇒ 兜底按**完整合成路径**查记录 → 只读记录里那条
//      **真实**路径 → 内存转 PCX → 调**对象自己的**内存版 Load（纯对象级、无锁）；
//   ③ `ImageManager::LoadImage` 文件版：**纯透传**（只计数），绝不回调贴图管理器。
//
// 三条硬纪律（都是真机事故换来的）：**不盲开路径**、**不在贴图管理器内部回调它自己**、
// **只读引擎自己解析成功过的路径**。

#include "image_pcx_bridge_hook.hpp"

#include "game_file_reader.hpp"
#include "application/mod/content_mount_service.hpp"  // 批次 360：自愈补挂要问"挂了几个模组"
#include "image_mount_query_watch.hpp"  // 批次 352：非 `.pcx` 查询的"按路径分桶"纯逻辑
#include "mod_resource_redirect.hpp"    // 批次 378：PC 的资源层重定向（模组清单顺序、dlc3 优先）
#include "notice_integrity_native.hpp"
#include "infrastructure/content/png_to_pcx_bridge.hpp"
#include "infrastructure/paths/pc_path_semantics.hpp"  // 批次 411：PC 的路径分隔符语义（`\` → `/`）
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "infrastructure/resources/engine_array.hpp"
#include "infrastructure/resources/small_caches.hpp"
#include "interfaces/lua/runtime_perf.hpp"  // 270-perf：分段计时用 `RuntimePerfTick()`（cntpct_el0）
#include "relay/smart_pointer_shim.hpp"

#include <atomic>
#include <cstring>
#include <utility>
#include <new>
#include "infrastructure/content/inflate_rows.hpp"
#include "infrastructure/resources/owned_bytes.hpp"
#if defined(__SWITCH__)
#include <malloc.h>
#include "program/setting.hpp"
#endif
// 外部链接：阶段失败与请求尺寸可从当前ELF点名读取。
std::uint32_t g_ImagePcxLastConversionFailure = 0;
std::uint32_t g_ImagePcxLastFailedPngBytes = 0;
using ImagePcxOwnedBytes = isaac::runtime::engine_resources::OwnedBytes;

namespace {

// 挂上来的两组绑定（地址由 `bridge::Attach` 给定；为空 = 没挂上，回调一律直接放弃）。
std::atomic<const GameFileReader::Bindings*> g_fileBindings{nullptr};
const GameFileReader::Bindings* FileBindings() noexcept {
    return g_fileBindings.load(std::memory_order_acquire);
}
std::atomic<const GameFileReader::ImagePcxBindings*> g_engineBindings{nullptr};
const GameFileReader::ImagePcxBindings* EngineBindings() noexcept {
    return g_engineBindings.load(std::memory_order_acquire);
}

// 贴图桥（`.pcx` 内存转码）的状态与诊断
// ─────────────────────────────────────────────────────────────────────────────
// 诊断集中成**一个固定布局的结构体**（2026-09-21 评审第四条）：
// 过去是一个个散落的全局符号，读数要逐个手写 mangled 名（这轮被坑过多次：名字猜错 = 门禁红、
// 布局挪动 = 读错值）。现在读数**只认这一个符号**，按固定偏移解析，字段增减都在这里看。
// 批次 353：**一条被主动探测的路径**的记录（固定布局，读数工具按偏移解析）。
// 4 个 u32 在前、两个定长字符串在后 ⇒ 大小 240 字节、没有内部填充（都是 4 字节对齐的成员）。
// ★ 布局一旦发布就不再动：要加东西只能往这个结构体尾部追加，并在读数工具里同步。
struct SharedPathProbeRecord {
    std::uint32_t runs;         // +0：探测跑了几次
    std::uint32_t modWins;      // +4：其中引擎答出**模组目录**的次数
    std::uint32_t lastModWin;   // +8：最近一次答模组目录吗（1/0）
    std::uint32_t firstModWin;  // +12：**第一次**答模组目录吗（1/0）—— 与 last 不一致 ⇒ 结果会变
    char query[64];             // +16：探测用的查询串
    char answer[160];           // +80：最近一次得到的回答原文
};

struct ImagePcxDiagnostics {
    std::uint32_t hookCalls;        // 透传挂点（ImageManager 文件版）被调用次数
    std::uint32_t originalOk;       // 其中原函数成功（即真 `.pcx` 正常加载）次数
    std::uint32_t syntheticPaths;   // 合成的 `.pcx` 路径条数
    std::uint32_t fallbackAttempts; // 进入兜底判定（原函数失败且请求是 `.pcx`）次数
    std::uint32_t ringMiss;         // 合成记录未命中 ⇒ 安全放弃次数
    std::uint32_t readOk;           // 按记录读到 `.png` 字节次数
    std::uint32_t cacheHits;        // 转码缓存命中次数（省掉"读 + 解压 + 转码"）
    std::uint32_t cacheConversions; // 实际执行转码次数
    std::uint32_t convertFailures;  // 转码失败次数
    std::uint32_t fedOk;            // 喂给引擎后拿到非空贴图次数
    std::uint32_t bindingMask;      // 依赖绑定逐靶点掩码（0 = 全过）
    std::uint32_t pngOverrideWins;  // ★ 模组 PNG 顶掉**本体已有** `.pcx` 的次数（2026-09-21 由 reserved 改）
    char lastRequestPath[128];      // 最近一次 `.pcx` 请求路径（全部调用，不分来源）
    char lastFallbackPath[128];     // 最近一次"进入兜底判定"的路径
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 270-perf（2026-10-02）：**取证字段，只往后加**（偏移被读数工具按固定位置解析）。
    //
    // 为什么要加：268（在 `ImageManager::LoadImage` 的中继里**把 `.pcx` 实参换成那条 `.png`**）
    // 上卡后真机读数**与没改一样**（`实际转码` 仍是 10），但**旧字段无法回答"那一步到底有没有执行"**
    // —— `lastRequestPath` 被两个中继共写、没有独立的分派计数。⇒ 先把"事实"变成数字：
    //   ① 268 那次换参数**发生了没有**（`loadImagePcxSuffix` / `loadImageSwaps`）；
    //   ② 兜底那 ~1 秒/张究竟花在"读 `.png` / 转码 / 喂引擎"的哪一步（三段 µs）。
    // 全是**冷路径**计数：`ImagePcx::Load` 整局只有个位数~几十次，计时只在真转码那条路上读两次
    // `cntpct_el0`，**不进每帧热路径**（与批次 262 把"每帧都跑"的诊断搬进门控那条纪律不冲突）。
    std::uint32_t pcxLoadCalls;        // `ImagePcx::Load` 中继被调用次数（含"原函数成功"那些）
    std::uint32_t loadImagePcxSuffix;  // `ImageManager::LoadImage` 中继接收的实参里以 `.pcx` 结尾的次数
    std::uint32_t loadImageSwaps;      // 其中真的把实参换成那条 `.png` 的次数（= 268 生效次数）
    std::uint32_t timedFallbacks;      // 做过分段计时的兜底次数（= 真转过码的那些）
    std::uint32_t readMicros;          // 累计：读 `.png` 字节（µs）
    std::uint32_t readMicrosMax;       // 单次最大（µs）
    std::uint32_t convertMicros;       // 累计：PNG→PCX 转码（µs）
    std::uint32_t convertMicrosMax;
    std::uint32_t feedMicros;          // 累计：喂给引擎的内存版 `Load`（µs）
    std::uint32_t feedMicrosMax;
    std::uint32_t fallbackMicros;      // 累计：整个兜底回调（µs，含上面三段）
    std::uint32_t fallbackMicrosMax;
    char lastLoadImagePath[128];       // `ImageManager::LoadImage` 中继最近一次的实参
                                       // （★ 与 `lastRequestPath` 分开记 —— 那个被两个中继共写，看不出是谁写的）
    char lastSwapFrom[128];            // 最近一次换参数：换前交给引擎的字符串
    char lastSwapTo[128];              // 最近一次换参数：换后交给引擎的字符串
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 271-perf（2026-10-02）：把"`Font::Load` 那 1 秒花在哪一段"变成可归属的数字。
    //
    // 为什么要加：270 已经定案**整条贴图兜底只有 36 ms**，但 `Font::Load` 平均 1017 ms / 次
    // ⇒ 那 1 秒**不是**我们转码花的。剩下的可能是：① 我们的图像层（`ImageManager::LoadImage`
    // 中继 + `ImagePcx::Load` 中继）；② 引擎自己（解析 / 文件调用 / CPU）。这两侧要靠**窗口归属**分开。
    //
    // 窗口 = `font_api.cpp` 的 `FontLoad` 在调引擎 `Font::Load` 前后包起来（`extern "C"` 两个函数，
    // 跨 TU 只走函数调用 —— 见 `interfaces/lua/runtime_perf.hpp` 顶部那条纪律）。
    std::uint32_t fontWindowCount;          // `Font:Load` 窗口开过几次
    std::uint32_t fontWindowMicros;         // 窗口累计时长（µs）= 引擎 `Font::Load` 的累计
    std::uint32_t fontWindowMicrosMax;      // 单次最长
    std::uint32_t fontWindowLoadImageCalls; // 窗口内 `ImageManager::LoadImage` 中继被调用次数
    std::uint32_t fontWindowLoadImageMicros;// 其中花在调原函数（含引擎自己的解码）上的累计 µs
    std::uint32_t fontWindowPcxLoadCalls;   // 窗口内 `ImagePcx::Load` 中继被调用次数
    std::uint32_t fontWindowPcxLoadMicros;  // 同上，累计 µs
    std::uint32_t fontLastGlyphCount;       // 从 Font 对象 +0x24 读到的**字形数**（偏移由反汇编推得，只读）
    std::uint32_t fontLastCharsSpan;        // 同上 +0x30（反汇编里 = 字形块大小 / 10，专给对账用）
    // 一次性"文件调用标定"：同一个文件，一次整块读 vs 多次 10 字节小读 —— 差值就是**每次调用的固定开销**。
    std::uint32_t calibState;               // 0 = 没跑，1 = 跑过，2 = 失败
    std::uint32_t calibOpenCalls;           // open+close 次数
    std::uint32_t calibOpenMicros;          // 这部分的累计 µs
    std::uint32_t calibReadCalls;           // 10 字节小读次数
    std::uint32_t calibReadMicros;          // 这部分的累计 µs
    std::uint32_t calibBytes;               // 标定用的文件大小
    std::uint32_t reserved271;              // 占位（字段只往后加，偏移一旦发布就不再动）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 272-perf（2026-10-02）：**让模组自带的 `.png` 也走我们这条转码路**（修法）+ 它的计数。
    //
    // 依据（271 读数 + 反汇编）：`Font::Load` 的 18.2 秒里 99.6% 花在 `ImageManager::LoadImage`
    // 的 40 次调用上，而页图是 `.png` ⇒ 引擎走 `ImagePng`（libpng）那条路，**平均 456 ms/次**；
    // 我们这条（读 `.png` + 解压 + RLE 成 PCX + 喂引擎）单次最大 11.2 ms。
    // 两条路都要做 `AllocateTexelBuffer`（引擎显存分配）⇒ 差的是 **PNG 解码**那一段。
    std::uint32_t pngArgCalls;      // `ImageManager::LoadImage` 中继收到 `.png` 实参的次数
    std::uint32_t pngRouted;        // 其中被我们改道去走 PCX 的（= 修法生效次数）
    std::uint32_t pngNotMod;        // 拒绝：解析出来不是模组文件
    std::uint32_t pngUnsupported;   // 拒绝：PNG 格式我们转码器不支持（原样放行给引擎）
    std::uint32_t pngRouteMicros;   // 改道本身的开销（解析挂载点 + 读头判格式）累计 µs
    std::uint32_t pngNoBindings;    // ★ 273-perf：绑定不全 ⇒ 改道没跑起来（272 就是栽在这条上）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 276-perf（2026-10-02）：把改道重做成"**绝不留下空页图**"（273 真机崩溃之后）。
    //
    // 273 的崩溃（`Data Abort @ 0x10`、`ImageBase::BeginBatch` 的 `this = 0`）说明了一条硬约束：
    // `Font::Load` 把 `ImageManager::LoadImage` 的返回值**直接存进页图数组** ⇒
    // **一次页图加载失败 = 留一个空页图 ⇒ 留到"第一次画字"那一刻才炸**。
    // ⇒ 这次两条防线，本段字段就是这两条防线的计数（**每一条都要能区分"没满足判据"和"压根没跑到"**）：
    //   ① **改道前先真转一遍**：我们转一次 3~7 ms；转成功才改道，转不动**一律原样放行给引擎**
    //      （引擎自己解 PNG，慢、但一定成功）⇒ 由 `pngTooLarge` / `pngProbeFail` 回答；
    //   ② **中继里保底重试**：改道之后没拿到图 ⇒ 用**引擎自己的原生 PNG 路**再走一遍
    //      ⇒ 由 `pngNativeRetry` / `pngNativeRetryOk` 回答（这两条**必须为 0**）。
    // 另外加 `feedFailures`：内存版 `Load` 返回 false 是"交付失败"的**直接证据**，
    // 273 的四个计数就是缺了它 —— 有它就一眼能看出"是哪一步没交付"。
    std::uint32_t pngTooLarge;      // 拒绝：解码尺寸超上限（按 IHDR 的 宽×高×通道 算）⇒ 原样放行
    std::uint32_t pngProbeFail;     // 拒绝：改道前的"真转一遍"失败（读不到 / 转不动）⇒ 原样放行
    std::uint32_t feedFailures;     // ★ 交付失败：引擎的内存版 `Load` 返回 false 的次数（>0 = 真的丢了图）
    std::uint32_t pngNativeRetry;   // ★ 改道后没拿到图 ⇒ 退回引擎原生 PNG 的次数（**必须为 0**）
    std::uint32_t pngNativeRetryOk; // 其中救回来了几次（`pngNativeRetry` > 它 = 真的没救回来）
    std::uint32_t pngProbeMicros;   // 改道前那次真转码的耗时（累计 µs；就是我们替引擎省掉的那笔钱）
    std::uint32_t pngProbeMicrosMax;
    std::uint32_t reserved276;      // 占位（字段只往后加，偏移一旦发布就不再动）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 277-perf（2026-10-02）：276 上卡读数换来的**两条修正**。
    //
    // 读数（`dist/gdb-read-20261002-155213.txt`）：改道 39/40 成功，但
    // **`退回原生 PNG 39 次、救回 39 次`** —— 一张都没送到；而且进局从 18.3 s 变 **24.2 s**
    // （每张页图既付了我们的转码 157 ms、又付了引擎的原生解码 456 ms）。
    //
    // 根因（结合 `ImageManager::LoadImage` 反汇编）：引擎拿到实参后的**第一件事**就是
    // `GetMountedFilePath(实参)`（0x4d2074），而那个 API **只认"虚拟路径"（相对路径）** ——
    // 我们 276 交上去的是从 `mounted` 拼出来的**绝对路径**（`rom:/isaac_mods/…`）
    // ⇒ 解析立刻答不上来 ⇒ `0x4d2078` 那条 `cbz` 直接跳到返回 ⇒ **交回空图**，
    // `ImagePcx::Load` 压根没被调（读数：窗口内 `ImagePcx::Load` **0 次**、`合成 .pcx 路径` 仍是 30 条）。
    // ⇒ 修正 = **合成路径按"引擎给我们的那种形式"造**（它给相对路径，我们就还它相对路径）。
    //
    // 为什么这次能一眼看出"没送到"：`pngNativeRetry` 这一条计数 —— 这是 276 加的防线二的副产物。
    // 但它**只能说明"没送到"，说不出"哪一步"**；所以本批把中继里那几个**静默返回空**的分支也做成计数
    // （`mountPngMiss` 就是本次的元凶）。
    std::uint32_t pngAbsReq;        // 收到的 `.png` 实参本身就以 `rom:/` 开头 ⇒ **不改道**（虚拟路径才解析得动）
    std::uint32_t pngProbeReadFail; // 改道前"真转一遍"里：读 `.png` 失败
    std::uint32_t pngProbeConvertFail;  // 改道前"真转一遍"里：转码失败
    std::uint32_t mountPcxCalls;    // 合成路径解析中继收到 `.pcx` 请求的次数（含模组自带的）
    std::uint32_t mountSynth;       // 其中成功"补位"（合成并交回一条路径）的次数
    std::uint32_t mountPngMiss;     // ★ 补位时连同名 `.png` 也没问到 ⇒ 返回空（**276 就是栽在这条上**）
    std::uint32_t mountModOwn;      // 模组自带 `.pcx`：原样交回（不补位）
    std::uint32_t reserved277;      // 占位（字段只往后加，偏移一旦发布就不再动）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 279-perf（2026-10-02）：**只改道大图** —— 修"开着 visible tinted rocks 时所有石头隐形"。
    //
    // 真机现象（用户实测、可复现）：该模组一开，**房间里所有石头隐形**（能炸、有碰撞）；关掉就正常。
    // 根因：石头由 `gfx/grid/grid_rock.anm2` 定帧，而那个 anm2 的精灵表写的是 **`.png`**
    //   （`Spritesheet Path="rocks_basement.png"`）。模组一开，这张表解析到**模组**的 `.png`
    //   ⇒ 落进 276 的"模组 `.png` 全改道" ⇒ 引擎按扩展名建的是 `ImagePcx` 而不是 `ImagePng`
    //   ⇒ **anm2 那条取精灵表的路径把它当空的用** ⇒ 整张石头表 = 空 ⇒ 所有石头隐形。
    //   （模组一关，这张表解析到**本体**文件、我们不改道 ⇒ 保持 `ImagePng` ⇒ 正常。）
    // ⇒ 修法不是"别改道"，而是"**只改道值得改道的**"：收益全在大图（引擎解 PNG 的成本随像素数走），
    //   256×256 的精灵表本来 ~1 ms、改道它几乎零收益却有真实风险。
    std::uint32_t pngTooSmall;      // ★ 拒绝改道：像素数不到下限（小精灵表走这类）⇒ 原样放行给引擎
    std::uint32_t pngSkippedPixels; // 最近一张因"太小"被放行的图的像素数（对账用：2048×2048 = 4194304）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★ 批次 351（2026-10-04）：**非 `.pcx` 的挂载查询**也要能量到 —— 取证用，只加计数、不改行为。
    //
    // 为什么加：minimapi 的 `IsBadLoad()`（`scripts/minimapapi/main.lua:1456-1462`）拿
    //   `Sprite:Load("gfx/ui/minimap1.anm2", true)` → `SetFrame("RoomUnvisited", 0)` →
    //   `SetLastFrame()` → 数 `GetFrame()`，**期望读到它自己在 `resources/gfx/ui/minimap1.anm2`
    //   里那份（`RoomUnvisited` = 1 帧）**；真机上却拿到 13 帧的**本体**那份 ⇒ 判 `badload`、
    //   在屏幕上打两行红字、**不画地图**（用户实测：没有 minimapi 的地图，只有原生 + GoodTrip 两张）。
    //   卡上那个文件**在**（2728 字节，与语料同大小）⇒ 问题是"模组那份没覆盖本体那份"。
    //   而 `.anm2` 这类**文件本身**走的正是本中继（`.pcx` 走的那条补位逻辑之外的分支）。
    //
    // 三个量分别回答三个问题：
    //   ① `mountOtherCalls`：非 `.pcx` 的查询**到底有没有**发生（若 `.anm2` 不走这条路，这里会是 0
    //      ⇒ 靶子错了，别在优先级上耗）；
    //   ② `mountAnm2Calls`：其中 `.anm2` 的次数；
    //   ③ `mountAnm2ModWins`：引擎对 `.anm2` 的**回答**里，有多少条指向**模组目录**
    //      （`IsModMountedPath`）—— 这一条就是"覆盖有没有生效"的直接读数。
    std::uint32_t mountOtherCalls;  // 896：非 `.pcx` 的挂载查询次数
    std::uint32_t mountAnm2Calls;   // 900：其中以 `.anm2` 结尾的次数
    std::uint32_t mountAnm2ModWins; // 904：其中引擎答出**模组目录**下路径的次数（= 覆盖生效）
    char lastAnm2Path[128];         // 908：最近一条 `.anm2` 查询路径
    char lastAnm2Answer[160];       // 1036：引擎对它的回答（空串 = 答不上来）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 批次 352（2026-10-04）：**按路径**记录 + **主动探测**那条共享路径。
    //
    // 351 的真机读数当场证明："全局计数判不了归属"（1342 次里 78 次 `.anm2`、19 次答模组目录，
    // 可这三类混在一起：模组独有 / 本体独有 / **两边都有**，而我们要问的正是第三类）。
    // ⇒ 本段的每一格都指向**一条具体路径**：
    //   ① `minimap*` 四格 = minimapi 的 `IsBadLoad()` 真正去读的那两条路径（`main.lua:1456-1462`）
    //      被"模组自己"问了几次、引擎答的是不是模组目录、最后一次的问答原文；
    //   ② `sharedProbe*` 四格 = **我们自己**主动问引擎一次 `gfx/ui/minimap1.anm2` 归谁 ——
    //      这一格不依赖"模组来不来问"，所以哪怕 minimapi 压根不走这条中继，它也答得出话。
    //      （第 1 次非 `.pcx` 查询时跑一次、之后每 512 次再跑一次；首次与末次分别留痕 ⇒
    //        "两次不一致"本身就是"解析结果随缓存/时序变"的直接证据。）
    //   ③ `mountOtherModWins` / `mountOtherNotMod` = 非 `.pcx` 查询的总账（模组目录 vs 其它）。
    std::uint32_t mountOtherModWins;   // 1196：非 `.pcx` 查询里，引擎答出**模组目录**的次数
    std::uint32_t mountOtherNotMod;    // 1200：其中答**非模组**的（本体那份，或答不上来 = 空）
    std::uint32_t minimap1Calls;       // 1204：最后一段是 `minimap1.anm2` 的查询次数
    std::uint32_t minimap1ModWins;     // 1208：其中引擎答出模组目录的次数
    std::uint32_t minimap2Calls;       // 1212：同上（`minimap2.anm2`）
    std::uint32_t minimap2ModWins;     // 1216
    char minimap1LastQuery[128];       // 1220：最近一次原始查询串
    char minimap1LastAnswer[160];      // 1348：引擎对它的回答原文
    char minimap2LastQuery[128];       // 1508
    char minimap2LastAnswer[160];      // 1636
    std::uint32_t sharedProbeRuns;     // 1796：我们主动探测跑了几次
    std::uint32_t sharedProbeModWin;   // 1800：最近一次探测：引擎答的是模组目录吗（1/0）
    std::uint32_t sharedProbeFirstModWin;  // 1804：**第一次**探测的同一个结论（对比用）
    char sharedProbeQuery[128];        // 1808：探测用的查询串
    char sharedProbeAnswer[160];       // 1936：最近一次探测得到的回答原文
    std::uint32_t reserved352;         // 2096：占位（字段只往后加，偏移一旦发布就不再动）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 批次 353（2026-10-04）：**回答"甲' 还是 乙'"的那三样**（352 的读数分不开它们）。
    //
    // 352 已经量到：`gfx/ui/minimap1.anm2` 被解析成了本体 `rom:/rp_patch/…`。但那只说明"没赢"，
    // 说明不了**为什么**没赢 —— 两种成因的修法完全不同：
    //   （甲'）解析顺序/优先级：本体那一层排在模组前面；
    //   （乙'）解析结果被**记住**了：这条路径在**模组挂载之前**就被本体 HUD 解析过。
    // 下面三样合起来就能把它们分开（详见 `image_mount_query_watch.hpp` 里那张"四条探测路径"的表）：
    //   ① `modMount*`   —— 我们到底登记了哪些模组目录（排掉"挂载根本没上"这个岔路）；
    //   ② `sharedPathProbes` —— **一组**性质不同的路径各自归谁（正对照 + 分层对照，见头文件）；
    //   ③ `otherRing*`  —— 最近 6 条非 `.pcx` 查询的"路径 + 回答"（352 只留了"最近一条"，不够）。
    std::uint32_t modMountCount;       // 2100：我们登记过的模组目录个数（上限 12）
    char modMountDirectories[12][48];  // 2104：目录名（`rom:/isaac_mods/mods/<目录>`，截断到 47 字符）
    std::uint32_t otherRingCount;      // 2680：非 `.pcx` 查询累计次数（环形写入的游标来源）
    char otherRingPath[6][88];         // 2684：环形历史 —— 最近 6 条查询的路径
    char otherRingAnswer[6][120];      // 3212：环形历史 —— 对它们的回答
    SharedPathProbeRecord sharedPathProbes[4];  // 3932：四条探测路径，各 240 字节
    std::uint32_t reserved353;         // 4892：占位（字段只往后加，偏移一旦发布就不再动）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 批次 354（2026-10-04）：**挂载到底成功没有**（353 的名单只记了"尝试过"，返回值被丢掉）。
    //
    // 353 的读数把范围缩到："模组独有的路径在 `GetMountedFilePath` 上直接答空"。⇒ 第一要务变成
    // 分清"挂载本身失败"与"挂载成功但解析器看不到"。这两张表与 `modMountDirectories` **同下标对齐**。
    std::uint32_t modMountStatus[12];      // 4896：每个模组的 `StatusCode` 数值（0 = Ok）
    std::uint32_t modMountFailedLeaf[12];  // 4944：失败落在 `kLeaves` 的哪个叶子（0xFFFFFFFF = 没有失败）
    std::uint32_t reserved354[2];          // 4992：占位（保住总大小 8 字节对齐）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 批次 356（2026-10-04）：**把"回声"与"真覆盖"分开** + **把时间轴切一刀**。
    //
    // ① `mountOtherModWinsReal`：354 读数里 `答出模组目录 = 78` 与 `其中 .anm2 = 78` **两次都恰好相等**
    //    （而 `.anm2` 里答模组的只有 19）。交叉核对已排除读串位 ⇒ 那多半是"**查询本身就是模组路径**
    //    （我们自己的模组页/清单解析拿 `isaac_mods/mods/…` 去问）被原样答回"。这一格只在
    //    **查询本身不是模组路径**时才计 —— 于是"回声"与"真覆盖"第一次有了两条不同的数。
    // ② `modMountTime*`：模组挂载**收尾那一刻**问一条模组独有的路径，单独留痕
    //    ⇒ 把"挂载当时就解析不到"与"挂载**之后**被清掉"分开（见头文件里那段注释）。
    std::uint32_t mountOtherModWinsReal;  // 5000：非 `.pcx` 查询里、**查询本身不是模组路径**而答出模组目录的次数
    std::uint32_t modMountTimeProbeRuns;  // 5004：挂载收尾那次检查点跑过几次
    std::uint32_t modMountTimeProbeModWin;// 5008：那次答的是不是模组目录（1/0）
    char modMountTimeProbeAnswer[160];    // 5012：那次得到的回答原文
    std::uint32_t reserved356;            // 5172：占位（字段只往后加，偏移一旦发布就不再动）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 批次 357（2026-10-04）：**"挂载点什么时候没的"切成多段 + 试一次重挂**。
    //
    // 356 的检查点已经把结论钉死：挂载收尾那一刻（叶子相对）**能**命中，游戏里**不能**。
    // 于是只剩两问：**在哪一段之间没的**、**重挂能不能救回来**。下面这几格就是这两问的落点。
    std::uint32_t mountVisibilityBitmap;  // 5176：bit i = 第 i 个检查点（见头文件的 0..3）答到了模组目录
    std::uint32_t mountCheckpointRuns;    // 5180：检查点一共跑过几次（0 次 ⇒ 这几格说明不了时间轴）
    std::uint32_t rebuildRelayInstalled;  // 5184：**重建挂载点中继装上没有**（1/0）——"没跑"≠"没装"
    std::uint32_t remountAttempted;       // 5188：试过重挂没有（1 = 调过 `RemountAll`，0 = 还没）
    std::uint32_t remountStatus;          // 5192：`RemountAll` 返回的 `StatusCode`（0 = Ok）
    std::uint32_t remountProbeModWin;     // 5196：重挂之后**立刻**再问一次的结果（1/0）
    char remountProbeAnswer[160];         // 5200：重挂之后那次问到的回答原文
    std::uint32_t reserved357[2];         // 5360：占位（保住总大小 8 字节对齐）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 批次 358（2026-10-04）：**重建挂载点中继"卡在哪一条"**。
    //
    // 357 的读数给出了元凶：`重建挂载点中继装上没有 = 否` —— 而它就是"引擎重建挂载点表之后把
    // 模组挂载点补回来"的那一环（`RebuildContentMountPoints()` 开头就是 `ClearMountPoints(false)`）。
    // 从此读数里那一格不再是"跑过 0 次"这种没法行动的信息，而是**失败码 + 现场字节**：
    // 一眼能分出"入口分支没打上（字节对不上）" / "代码洞桩不对" / "槽被占了"。
    std::uint32_t rebuildRelayVerifyFailure;  // 5368：失败码（码表见 hook_manager.cpp 里那张枚举）
    char rebuildRelayTargetBytes[16];         // 5372：目标处**实际**的 16 字节（读回来比对用）
    char rebuildRelayStubBytes[16];           // 5388：代码洞桩处**实际**的 16 字节
    std::uint32_t reserved358;                // 5404：占位（保住总大小 8 字节对齐）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 批次 359（2026-10-04）：**探针从死代码挪到活的那条路上**。
    //
    // 358 的读数（失败码 0、现场字节全 0）说明"那个安装函数压根没被调用过" —— 本地一查：
    // 挂点目录把 `RebuildMountPoints` 的后端定成 **`EntryRelay`**，真正在跑的是
    // `entry_relay_hook_adapter.cpp` 那条路；`exlaunch_hook_adapter.cpp` 里那一支是**死代码**。
    // ⇒ 357/358 记的"中继没装上"**测错了对象**，结论作废（日志里已更正）。
    // 下面三格才是活的：装没装上、失败码、**包装被调用了几次**。
    std::uint32_t entryRelayRebuildInstalled;  // 5408：入口中继（RebuildMountPoints）装上没有
    std::uint32_t entryRelayRebuildFailure;    // 5412：它的失败码（0 = 成功；非 0 见 entry_relay 的码表）
    std::uint32_t entryRelayRebuildCalls;      // 5416：**我们那层包装被调用了几次**
    std::uint32_t reserved359;                 // 5420：占位（保住总大小 8 字节对齐）
    // ★★★ 批次 360（2026-10-04）：**修法**（自愈补挂）的留痕。
    //   359 已证：引擎清表**不经过** `RebuildContentMountPoints` ⇒ 挂钩子永远救不了。
    //   于是改成"我们自己量、不在就补"（357 已实测证明补挂有效）。
    std::uint32_t remountWatchdogChecks;       // 5424：看门狗检查了几次（每次一条只读查询）
    std::uint32_t remountHealCount;            // 5428：**发现不在 ⇒ 补挂**发生了几次
    std::uint32_t reserved360[2];              // 5432：占位（保住总大小 8 字节对齐）
    // ─────────────────────────────────────────────────────────────────────────
    // ★★★ 批次 361（2026-10-04）：**按时间量**（每一格都带"当时的模组数"）+ 挂载后的重挂试验。
    //
    // 360 的读数推翻了 357/358 的结论：看门狗 43 次检查、**0 次发现丢失** ⇒ 挂载点一直在。
    // 病根是**我把位图当成时间序**（bit2 记在第 1 帧 = 还没挂的时候）⇒ 判据自己骗了自己。
    // 这一段的每一格都带上"当时的模组数"与自增序号，读数里再也不会混淆"没挂"与"丢了"。
    std::uint32_t probeSeq[4];                 // 5440：四条探测各自的序号（越大越晚）
    std::uint32_t probeModCount[4];            // 5456：**那一刻已登记的模组数**（0 = 这次不算数）
    std::uint32_t lateTrialTick;               // 5472：晚点试验跑在第几个 update 帧（0 = 还没跑）
    std::uint32_t lateSharedBeforeModWin;      // 5476：重挂**前**，共享路径答模组吗
    std::uint32_t lateSharedAfterModWin;       // 5480：重挂**后**，共享路径答模组吗
    std::uint32_t lateModOnlyAfterModWin;      // 5484：重挂后，模组独有路径答模组吗（对照）
    char lateSharedBeforeAnswer[160];          // 5488：重挂前共享路径的回答原文
    char lateSharedAfterAnswer[160];           // 5648：重挂后共享路径的回答原文
    // ★★★ 批次 411/412（2026-10-08）：**PC 路径分隔符归一化**（`\` → `/`）发生了几次。
    //   放在 361 的 `reserved361[2]` 里消费一格（**不挪任何已发布偏移、总大小不变** —— 占位槽就是干这个的）。
    //   ★★ 计数点是**批次 412 搬过来的那一层**（`EntryRelayImageManagerLoadFileCallback`，也就是
    //      `ImageManager::LoadImage`）—— 411 曾把归一化放在 `GetMountedFilePath`，真机读数**恒 0**
    //      （anm2 的精灵表路径不经过那里）⇒ 那一版等于修了一条走不到的路。详见 412 段注释。
    //   判据：选带 `\` 写精灵表路径的模组角色进局，这一格应 > 0；且**模组文件保持原样**时角色正常渲染。
    std::uint32_t pathSeparatorNormalized;     // 5808：把带 `\` 的入参归一化成 `/` 的次数（412）
    std::uint32_t reserved361;                 // 5812：仍留一格占位（保住总大小 8 字节对齐）
};
ImagePcxDiagnostics g_imagePcxDiag{};
// ★ 批次 352：把"结构体大小"钉在编译期 —— 读数工具按固定偏移解析，布局一挪就静默读错值。
//   （历史：351 是 1196 字节；本批在尾部追加，旧字段偏移**一格都没动**。）
//   （历史：351 = 1196；352 到 2100；353 到 4896；354 到 5000；356 到 5176；357 到 5368；
//     358 到 5408；359 到 5424；360 到 5440；361 到 5816；411 在 361 的占位槽里落了一格
//     —— **大小仍是 5816、旧偏移一格都没动**。）
static_assert(sizeof(ImagePcxDiagnostics) == 5816,
              "ImagePcxDiagnostics 的布局被改动过：新字段只能往尾部追加（偏移一旦发布就不再动），"
              "改了大小就要同步 tools/read_device_state_via_gdb.py 的读取长度与打印段");
static_assert(sizeof(SharedPathProbeRecord) == 240,
              "SharedPathProbeRecord 的布局被改动过：读数工具按 +0/+4/+8/+12/+16/+80 解析");

// ── 270-perf：分段计时的两个小工具（只在本文件的兜底路径上用）────────────────────
// `RuntimePerfTick()` 读的是 `cntpct_el0`（Tegra X1 上 19.2 MHz 的**物理**自由运行计数器）；
// 非设备构建恒返回 0 ⇒ `end <= begin` 成立 ⇒ 一律记 0，宿主行为完全不变。
[[nodiscard]] inline std::uint32_t ImagePcxMicrosSince(std::uint64_t begin) noexcept {
    const std::uint64_t end = isaac::runtime::RuntimePerfTick();
    if (end <= begin) {
        return 0;
    }
    const std::uint64_t ticksPerSecond = isaac::runtime::RuntimePerfTicksPerSecond();
    if (ticksPerSecond == 0) {
        return 0;
    }
    return static_cast<std::uint32_t>((end - begin) * 1000000ULL / ticksPerSecond);
}

inline void ImagePcxAccumulateMicros(std::uint32_t* total, std::uint32_t* maxValue,
                                     std::uint32_t value) noexcept {
    *total += value;
    if (value > *maxValue) {
        *maxValue = value;
    }
}

// 批次 352：诊断字符串搬运 —— 一律截断 + 补 `'\0'`（读数工具按定长数组解析）。
// 单独抽出来是为了"空指针一律写空串"，避免每处各写一遍 `strncpy` 时漏掉判空。
//
// ★★★ 批次 411（2026-10-08）：**两处都是真机量出来的，不是保守写法。**
//   ① `noinline`：411 把它从 `strncpy` 改成有界循环、又在调用点引入一块 4096 字节的入参缓冲
//      （编译器再无长度信息）⇒ GCC 在它的 ~10 个调用点全部**内联展开**：
//      `EntryRelayContentGetMountedFilePathCallback` 一个函数 **3108 → 21316 字节（+18 KiB）**。
//   ② **拷贝只许走 libc**（`strlen` + 有界 `memcpy`），**不许手写循环** —— 手写循环会被 GCC
//      按 `capacity` 做 `constprop` 克隆并**向量化展开**成 ~7 份、每份 1.3~1.6 KiB（再 +8 KiB）。
//      libc 调用没有可展开的循环体 ⇒ 这一段只占一份、几十字节。
//   ⇒ 判据：门禁 `test_batch411_path_separators.py::test_diag_copy_stays_out_of_line_and_uses_libc`。
__attribute__((noinline)) void ImagePcxCopyDiagString(char* destination, std::size_t capacity,
                                                      const char* source) noexcept {
    if (destination == nullptr || capacity == 0) {
        return;
    }
    if (source == nullptr) {
        destination[0] = '\0';
        return;
    }
    // 截断语义与原来的 `strncpy(dst, src, capacity - 1)` + 补 0 **逐字节相同**，
    // 只是把"长度"算清楚（原来那句在 411 的新缓冲下会触发 `-Werror=stringop-truncation`）。
    std::size_t length = std::strlen(source);
    if (length >= capacity) {
        length = capacity - 1;
    }
    if (length != 0) {
        std::memcpy(destination, source, length);
    }
    destination[length] = '\0';
}

// 批次 361：**这一刻已经登记了几个模组** —— 探测记上下文用（0 ⇒ 这次探测跑在挂载之前、不算数）。
// ★ 必须定义在**最前面**（匿名命名空间、所有使用者之前）：它被 `RunSharedPathProbes` 用到，
//   而那个函数在文件里出现得比桥命名空间那批函数早（上一版放错了位置，设备构建直接报
//   `not declared in this scope` + `defined but not used`）。
static std::uint32_t ModCountNow() noexcept {
    isaac::runtime::ContentMountService* service = isaac::runtime::SessionContentMountService();
    return service != nullptr ? static_cast<std::uint32_t>(service->mod_count()) : 0U;
}

// 批次 352/353：**主动探测**的周期，以及 353 的"最近 6 条查询"环形历史的槽数。
// 探测的**路径表**在 `image_mount_query_watch.hpp` 里（`kSharedPathProbeQueries`）——
// 放头文件是为了宿主门禁能直接核那张表（哪几条、各是什么性质），不必上真机。
constexpr std::uint32_t kSharedPathProbePeriod = 512;
constexpr std::size_t kOtherQueryRingSlots = 6;
// 批次 357：**"挂载点还在不在"的时间轴**用的那句查询（356/357 共用，前后可比）。
// 用**叶子相对**形式：minimapi 用的就是这种写法；而 356 的检查点已证"挂载收尾那一刻它有效"。
// 被问的文件（goodtripfixed 的 `resources/sprite/gt/gt_ui.anm2`）在 354 被证**真的在卡上**。
constexpr char kMountVisibilityQuery[] = "sprite/gt/gt_ui.anm2";
// 批次 361：探测的自增序号（用来给读数一个**与 bit 位无关**的时间参照）。
std::uint32_t g_pathProbeSequence = 0;

// 271-perf：`Font::Load` 窗口开关（`font_api.cpp` 通过本文件末尾那两个 `extern "C"` 函数开关）。
// 只做"是不是在窗口内"的判定，用来把文件/图像调用**归属**到那次字体加载上。
std::atomic<std::uint32_t> g_fontLoadWindow{0};
// 一次性标定：0 = 没跑，1 = 已在跑/跑过（用 exchange 抢，保证只跑一次）。
std::atomic<std::uint32_t> g_fontCalibClaimed{0};

// 271-perf：一次性标定"**一次文件调用值多少微秒**"。
//
// 做法是**同一个文件上的 A/B**：先把 10 字节一小块读 N 次（记时长），再整块读同样多的字节（记时长）。
// 两条路读的数据量一样，差别只有"切成了多少次调用" ⇒ 差值除以"多出来的调用次数"就是每次调用的固定开销。
// 为什么必须量：`Font::Load` 的字形/字距循环是"一个条目一次 `read`"（反汇编 0x4ce418），
// 而上万次小读到底是不是那 1 秒的来源，取决于"一次调用多少微秒"这个数 —— 没有它就只能猜。
void ImagePcxRunFileCallCalibrationOnce(const char* path) noexcept {
    if (g_fontCalibClaimed.exchange(1, std::memory_order_acq_rel) != 0) {
        return;  // 已经跑过或正在跑
    }
    if (path == nullptr || g_fileBindings == nullptr) {
        g_imagePcxDiag.calibState = 2;
        return;
    }
    const auto& b = *FileBindings();
    if (b.construct == nullptr || b.openRead == nullptr || b.getLength == nullptr ||
        b.read == nullptr || b.close == nullptr || b.destroy == nullptr) {
        g_imagePcxDiag.calibState = 2;
        return;
    }
    alignas(16) std::array<u8, kGameFileObjectSize> fileStorage{};
    // ── A) 纯"开 + 关"往返 × 200：这一组的成本里没有任何数据量。
    constexpr std::uint32_t kOpenCloseCalls = 200;
    const std::uint64_t openBeginTick = isaac::runtime::RuntimePerfTick();
    std::uint32_t openDone = 0;
    for (std::uint32_t i = 0; i < kOpenCloseCalls; ++i) {
        b.construct(fileStorage.data());
        const bool ok = b.openRead(fileStorage.data(), path);
        if (ok) {
            b.close(fileStorage.data());
            ++openDone;
        }
        b.destroy(fileStorage.data());
        if (!ok) {
            break;
        }
    }
    const std::uint32_t openMicros = ImagePcxMicrosSince(openBeginTick);
    // ── B) 一次 open，然后 10 字节一块读 N 次（与 `Font::Load` 字形循环同款形状）。
    std::uint32_t readCalls = 0;
    std::uint32_t readMicros = 0;
    std::uint32_t fileBytes = 0;
    b.construct(fileStorage.data());
    if (b.openRead(fileStorage.data(), path)) {
        const int length = b.getLength(fileStorage.data());
        if (length > 0) {
            fileBytes = static_cast<std::uint32_t>(length);
            constexpr std::uint32_t kMaxChunkReads = 2000;  // 有界：别在加载路径上停太久
            const std::uint32_t wanted =
                std::min<std::uint32_t>(fileBytes / 10u, kMaxChunkReads);
            alignas(16) u8 chunk[16];
            const std::uint64_t readBeginTick = isaac::runtime::RuntimePerfTick();
            for (std::uint32_t i = 0; i < wanted; ++i) {
                // ★ 274 修正：`read(obj, buf, elemSize, count)` 的返回值**语义不确定**
                //   （可能是"元素个数"，也可能是"字节数"）—— 271 里按"== 1"判，
                //   真机读数就成了"10 字节读 0 次"，标定白跑。这里只要求"读到了东西"。
                if (b.read(fileStorage.data(), chunk, 10, 1) <= 0) {
                    break;
                }
                ++readCalls;
            }
            readMicros = ImagePcxMicrosSince(readBeginTick);
        }
        b.close(fileStorage.data());
    }
    b.destroy(fileStorage.data());
    g_imagePcxDiag.calibOpenCalls = openDone;
    g_imagePcxDiag.calibOpenMicros = openMicros;
    g_imagePcxDiag.calibReadCalls = readCalls;
    g_imagePcxDiag.calibReadMicros = readMicros;
    g_imagePcxDiag.calibBytes = fileBytes;
    g_imagePcxDiag.calibState = 1;
}


// 合成记录环形：**完整合成路径 → 该 `.png` 的真实挂载路径**。
// `CreateCleanPath` 的大小写和分隔符变化允许等价，但模组目录身份不能丢失；
// 值用"合成时解析成功过的那条路径"，因此读它必然可开（这是三次 Abort 换来的纪律）。
// ★ 2026-09-29（批次 196）起容器改用共用设施 `FixedRingStore`（L3 资源层设计稿 §四）：
//   写入序仍由本文件那个 `std::atomic` 持有（"写入序是原子的"这条语义原样保留），
//   容器只管落槽与覆盖 —— 行为与原来的 `(++count - 1) % N` 逐条一致。
constexpr std::size_t kImagePcxSyntheticPathBytes = isaac::runtime::paths::kSeparatorQueryCapacity;
constexpr std::size_t kImagePcxSyntheticRingSize = 16;
struct ImagePcxSyntheticRecord {
    char pcxPath[kImagePcxSyntheticPathBytes]{};
    char requestPath[kImagePcxSyntheticPathBytes]{};
    char pngPath[kImagePcxSyntheticPathBytes]{};
};
isaac::runtime::engine_resources::FixedRingStore<ImagePcxSyntheticRecord,
                                                 kImagePcxSyntheticRingSize>
    g_ImagePcxSyntheticRing{};
std::atomic<std::uint32_t> g_ImagePcxSyntheticRingCount{0};

// 转码结果缓存（2026-09-21 评审第一条）：同一张 PNG 在真机上被问过 69 次、实际只读 10 次，
// 每次命中都要重走"读文件 + inflate + 转码"。键 = 该 `.png` 的真实挂载路径（含模组目录，
// 足以区分不同模组里的同名文件）；值是转好的 PCX 字节。LRU + 总字节预算（默认 8 MiB）。
// ★ 2026-09-29（批次 196）起改用共用设施 `BudgetedLruCache`：键保持"固定大小的值语义"
//   （不引入每个键一次堆分配），比较口径 = 原实现的 `strcmp` 全串比较。
// ★★★ 批次 266（2026-10-02）：**4 槽 / 8 MiB 太小，导致"缓存一次都没命中"** —— 真机读数
//   （`PERF_API_WRAPPER=1` 的诊断包）里的硬数字：
//     * `Font:Load` **18 次 / 合计 18300 ms / 平均 1017 ms**（≈1 秒/次）；
//     * 贴图桥本节自己的统计：**「读到 .png 10｜缓存命中 0｜实际转码 10」**；
//     * 被转的是中文大字体（最近路径 `mcm_cn_font/TeamMeatFont16Bold-0.png`）——
//       `mod_config_menu_cn` 的字体目录 **26 个 PNG / 合计 14.5 MB，单个最大 2.35 MB**
//       （成 PCX 同量级）⇒ 8 MiB 预算连两个都放不下、4 个槽更是一装就顶
//       ⇒ **一个工作集（MCM 的 7 个字体）永远装不进缓存** ⇒ 每次进局 `ReloadFont()`
//       都要把整套字体**重新 inflate + 重新转码**，这就是"进局 11.7 秒"的来源
//       （`MC_POST_PLAYER_INIT [模组菜单]` 4 次 / 平均 11.7 秒）。
//   ⇒ 本批把**槽数 4 → 32、总预算 8 MiB → 24 MiB**：槽的成本只是键（256 B/条 ⇒ 8 KB，可忽略）；
//     24 MiB 是为了**一次装下 MCM 那 7 个字体**，而**不**试图装下全部 26 个页面 —— 有界。
//     ★ 模块假堆已是 **128 MiB**（`program/setting.hpp` 的 `HeapSize`，批次 180 抬的），
//       所以这 24 MiB 有出处；真机若发现堆吃紧，把这两个数调回去即可（只有这一处）。
// ★★★ 2026-10-10（批次 422）：**真机上堆确实吃紧了，按上面那句话把它调回去** ——
//   局内读数：这个缓存**实占 30.88 MB**，而**整个会话只"实际转码 36 张 / 缓存命中 30 次"**。
//   ⇒ 先查清"为什么实占 30.88 MB > 当时 24 MiB 的预算"：**是缓存容器自己的 bug** ——
//     `BudgetedLruCache::ReserveSlot` 第一步是"有空槽就直接返回"，于是**预算只在
//     32 个槽全满之后才开始生效**（32 条 × 平均 0.97 MB = 30.88 MB，严丝合缝）。
//     已在 `src/infrastructure/resources/small_caches.hpp` 修正为"任一超限就淘汰"
//     （红绿夹具见 `tests/test_engine_array_owner.py::SmallCacheTests`）。
//   ⇒★ 修正之后**预算才是真预算**，所以这里可以放心把它压到工作集真正需要的量级。
//     量化依据（同一次读数的"兜底分段计时"）：**36 次转码累计 503.1 ms**（读 55.1 +
//     转 343.3 + 喂 99.1），即**命中一次只值约 14 ms**；而**兜底**整个会话只被进 66 次
//     （入口挂点被调 2734 次）⇒ 就算全部不命中，多花的也**不到 1 秒**。
//     ⇒ **旧注释里"装不下工作集 ⇒ 每次进局重转 ⇒ 11.7 秒"那个因果是错的**：
//       那 11.7 秒是 `MC_POST_PLAYER_INIT` 里引擎自己 `Font::Load` 的耗时
//       （18 次 / 18300 ms / 平均 1017 ms），跟这里重不重转无关。
//   ⇒ 本批取值：**先定 8 MiB / 16 槽，真机一验就发现它是错的** —— 见下。
// ★★★★ 2026-10-10（同一天，423 批）：**8 MiB 造成真实功能回退，改回 16 MiB**。
//   ★ 我把"未命中很便宜"算错了：那是拿 **421 那一次的 14 ms/次** 外推的，而
//     **单次转码成本根本不均匀**（取决于图的大小）。422 上卡真机读数：
//     `convertMicrosMax = 450.1 ms`、**单次兜底最大 = 607.8 ms**
//     （421 的 24 MiB 那版是 `85.3 / 110.3 ms`），而 `最近兜底路径` 正是
//     `mcm_cn_font/teammeatfont16bold_1.pcx` 那一族。
//   ★★ **根因是结构性的**：本文件用 `tools/png_to_pcx.py` 把 MCM 的 26 张字号 PNG
//     全部转了一遍量尺寸 —— **单张最大 `teammeatfont16bold_0.png` 转出来是 10.23 MiB**
//     （26 张合计 **59.2 MiB**）。而缓存的规则是"**单条超预算就不缓存**"
//     （`BudgetedLruCache::Insert` 的第一句 `if (bytes > budget_bytes_) return false;`）
//     ⇒ **只要预算小于单张最大值，那一张就永远进不了缓存，每次要用都得重转**（450~600 ms）。
//     ⇒ **取值判据应该是"预算 ≥ 单张最大值"，而不是"够不够装下工作集"** ——
//       8 MiB 恰好把最大的那一张结构性排除掉了。
//   ⇒ 本批取 **16 MiB / 32 槽**：16 MiB > 10.23 MiB（有余量装下那张 + 几张小图），
//     且**没有任何一张被结构性排除**；26 张合计 59.2 MiB 装不全是有意的（有界）。
//     期望真机 `[80]` ≤ 16 MiB ⇒ 相对修复前的 30.88 MB **仍省约 15 MB**，
//     同时 `convertMicrosMax` 应当回落到 ~100 ms 量级。
//   ★ 可证伪的验收（423 上卡时逐条核）：① `[80] ≤ 16 MiB`；② `convertMicrosMax` 与
//     单次兜底最大值**回到 ~100 ms 量级**（若仍 ~600 ms，说明还有更大的单张超预算）；
//     ③ `cacheHits` 相对转码次数的比例上升。
//   ★ 教训（写给后来人）：**"预算"这个词在这里有两个互相独立的下界** ——
//     ①要能装下循环工作集（命中率），②**必须大于单张最大值**（否则那张图被永远排除）。
//     只按 ① 估就会踩这个坑；估 ② 需要先知道**磁盘上图的真实尺寸**（这里量过才知道是 10.23 MiB）。
constexpr std::size_t kImagePcxCacheEntries = 32;
constexpr std::size_t kImagePcxCacheBudgetBytes = 16u * 1024u * 1024u;
struct ImagePcxCacheKey {
    char path[kImagePcxSyntheticPathBytes]{};
};
struct ImagePcxCacheKeyOps {
    static bool Equal(const ImagePcxCacheKey& a, const ImagePcxCacheKey& b) noexcept {
        return std::strcmp(a.path, b.path) == 0;
    }
};
struct ImagePcxCacheBytesOf {
    std::size_t operator()(const ImagePcxOwnedBytes& value) const noexcept { return value.size(); }
};
isaac::runtime::engine_resources::BudgetedLruCache<ImagePcxCacheKey, ImagePcxOwnedBytes,
                                                   kImagePcxCacheEntries, ImagePcxCacheKeyOps,
                                                   ImagePcxCacheBytesOf>
    g_ImagePcxCache(ImagePcxCacheBytesOf{}, kImagePcxCacheBudgetBytes);

// 完整路径比较：只容许 PC 的 ASCII 大小写与分隔符等价，不删目录或挂载前缀。
bool ImagePcxPathEquals(const char* a, const char* b) noexcept {
    if (a == nullptr || b == nullptr || a[0] == '\0' || b[0] == '\0') {
        return false;
    }
    for (;; ++a, ++b) {
        char ca = *a;
        char cb = *b;
        if (ca == '\\') ca = '/';
        if (cb == '\\') cb = '/';
        if (ca >= 'A' && ca <= 'Z') ca = static_cast<char>(ca - 'A' + 'a');
        if (cb >= 'A' && cb <= 'Z') cb = static_cast<char>(cb - 'A' + 'a');
        if (ca != cb) return false;
        if (ca == '\0') return true;
    }
}

// 原生 LoadImage 先用返回的挂载路径查缓存，未命中时却释放它并用原始请求调用 Load。
// 同一记录保存这两条完整路径；不删目录、不猜前缀、不退回最后文件名。
// 直接填写下一槽，避免在游戏线程栈上构造三条完整路径的临时记录。
void ImagePcxRememberPath(const char* pcxPath, const char* pngPath,
                         const char* requestPath = nullptr) noexcept {
    const std::size_t pcxLength = std::strlen(pcxPath);
    const std::size_t pngLength = std::strlen(pngPath);
    const std::size_t requestLength = requestPath != nullptr ? std::strlen(requestPath) : 0;
    if (pcxLength >= kImagePcxSyntheticPathBytes || pngLength >= kImagePcxSyntheticPathBytes ||
        requestLength >= kImagePcxSyntheticPathBytes) {
        return;  // 不登记截断路径：半条路径可能静默命中另一个模组。
    }
    const std::size_t slot = g_ImagePcxSyntheticRingCount++ % kImagePcxSyntheticRingSize;
    auto& record = g_ImagePcxSyntheticRing.at(slot);
    std::memcpy(record.pcxPath, pcxPath, pcxLength + 1);
    std::memcpy(record.pngPath, pngPath, pngLength + 1);
    if (requestLength != 0) std::memcpy(record.requestPath, requestPath, requestLength + 1);
    else record.requestPath[0] = '\0';
}

// 精确完整路径优先；同一完整路径重复登记时，从最新槽往回查。
const char* ImagePcxRingLookup(const char* path) noexcept {
    if (path == nullptr || path[0] == '\0') return nullptr;
    const std::uint32_t ringCount = g_ImagePcxSyntheticRingCount.load(std::memory_order_relaxed);
    const std::size_t scan = ringCount < kImagePcxSyntheticRingSize
                                 ? static_cast<std::size_t>(ringCount)
                                 : kImagePcxSyntheticRingSize;
    for (std::size_t age = 0; age < scan; ++age) {
        const auto& record = g_ImagePcxSyntheticRing.at((ringCount - 1U - age) % kImagePcxSyntheticRingSize);
        if (std::strcmp(record.pcxPath, path) == 0 ||
            std::strcmp(record.requestPath, path) == 0) return record.pngPath;
    }
    for (std::size_t age = 0; age < scan; ++age) {
        const auto& record = g_ImagePcxSyntheticRing.at((ringCount - 1U - age) % kImagePcxSyntheticRingSize);
        if (ImagePcxPathEquals(record.pcxPath, path) ||
            ImagePcxPathEquals(record.requestPath, path)) return record.pngPath;
    }
    return nullptr;
}

// 查缓存：命中返回该条目的 PCX 字节指针（有效到下一次插入为止），否则返回空。
const ImagePcxOwnedBytes* ImagePcxCacheLookup(const char* pngMounted) noexcept {
    ImagePcxCacheKey key{};
    std::strncpy(key.path, pngMounted, sizeof(key.path) - 1);
    return g_ImagePcxCache.Find(key);
}

// 插入缓存：按 LRU + 预算淘汰；单条超过预算则不缓存（宁可每次重转，也不撑爆堆）。
void ImagePcxCacheInsert(const char* pngMounted, std::uint8_t*& pcx, std::size_t size) {
    if(!pcx || !size || size>kImagePcxCacheBudgetBytes) return;
    ImagePcxCacheKey key{};
    std::strncpy(key.path,pngMounted,sizeof(key.path)-1);
    ImagePcxOwnedBytes value(pcx,size);
    pcx=nullptr;
    (void)g_ImagePcxCache.Insert(key,std::move(value));
}
// 仅缓存未命中时取堆统计，提前腾出最坏工作空间；不会每帧扫描空闲链。
void ImagePcxReserveWorkspace(std::uint64_t need) noexcept {
#if defined(__SWITCH__)
    const auto heap=mallinfo();
    const auto free=static_cast<std::uint64_t>(heap.fordblks>0?heap.fordblks:0);
    const auto arena=static_cast<std::uint64_t>(heap.arena>0?heap.arena:0);
    // newlib按需sbrk扩展；fordblks只覆盖已扩展部分，不是整个152MiB假堆余量。
    const auto expandable=exl::setting::HeapSize>arena?exl::setting::HeapSize-arena:0;
    const auto available=free+expandable;
    if(need>available) {
        const auto deficit=need-available;
        const auto used=g_ImagePcxCache.used_bytes();
        g_ImagePcxCache.TrimToBytes(deficit>=used?0:used-static_cast<size_t>(deficit));
    }
#else
    (void)need;
#endif
}
bool ImagePcxInflateRows(const uint8_t*,std::size_t,std::size_t,std::size_t,void*,
                         isaac::runtime::content::RowSink) noexcept;


// 把 `.png` 文件读进内存（照 `GameFileReader::ReadScript` 的既有流程：
// 构造 → 打开 → 取长 → 读 → 关 → 析构）。成功返回 true 并填 `out`；
// 任何一步失败返回 false（文件不存在 / 空 / 超 16 MiB / 读不满）。仅本 TU 使用。
namespace {
bool ReadPngFileForBridge(const char* pngPath, ImagePcxOwnedBytes* out) {
    if (g_fileBindings == nullptr) {
        return false;
    }
    const auto& b = *FileBindings();
    if (b.construct == nullptr || b.openRead == nullptr || b.getLength == nullptr ||
        b.read == nullptr || b.close == nullptr || b.destroy == nullptr) {
        return false;
    }
    alignas(16) std::array<u8, kGameFileObjectSize> fileStorage{};
    b.construct(fileStorage.data());
    if (!b.openRead(fileStorage.data(), pngPath)) {
        b.destroy(fileStorage.data());
        return false;
    }
    const int length = b.getLength(fileStorage.data());
    constexpr int kPngCap = 16 * 1024 * 1024;  // 贴图 Mod 单文件上限 16 MiB
    if (length <= 0 || length > kPngCap) {
        b.close(fileStorage.data());
        b.destroy(fileStorage.data());
        return false;
    }
    ImagePcxReserveWorkspace(static_cast<std::size_t>(length));
    if (!out->Resize(static_cast<std::size_t>(length))) {
        g_ImagePcxCache.TrimToBytes(0);
        if(!out->Resize(static_cast<std::size_t>(length))) {
            b.close(fileStorage.data()); b.destroy(fileStorage.data()); return false;
        }
    }
    const int bytesRead = b.read(fileStorage.data(), out->data(), 1, length);
    b.close(fileStorage.data());
    b.destroy(fileStorage.data());
    return bytesRead == length;
}
}  // namespace

bool ImagePcxConvert(const ImagePcxOwnedBytes& png,uint8_t** out,std::size_t* size) noexcept {
    if(png.size()>=33) {
        const auto be=[](const u8* p) { return (uint32_t(p[0])<<24)|(uint32_t(p[1])<<16)|(uint32_t(p[2])<<8)|p[3]; };
        const auto color=png.data()[25];
        const auto channels=color==6?4:color==2?3:color==4?2:1;
        // 只为首个输出块预留；后续实际分配失败沿用清缓存后重试一次的路径。
        const auto need=isaac::runtime::content::PngToPcxStreamingPeakUpperBound(png.size(),be(png.data()+16),channels,1);
        if(need<=isaac::runtime::content::kPngToPcxPeakBudgetBytes) ImagePcxReserveWorkspace(need);
    }
    isaac::runtime::content::PngToPcxFailure failure{};
    if(isaac::runtime::content::PngToPcxStreaming(png.data(),png.size(),&ImagePcxInflateRows,out,size,&failure)) return true;
    g_ImagePcxLastConversionFailure=static_cast<uint32_t>(failure);
    g_ImagePcxLastFailedPngBytes=static_cast<uint32_t>(png.size());
    if(failure!=isaac::runtime::content::PngToPcxFailure::Allocation) return false;
    // 总空闲不能代表连续空间；回收缓存后重试，真实失败仍由调用者记录，不能记为就绪。
    if(!g_ImagePcxCache.used_bytes()) return false;
    g_ImagePcxCache.TrimToBytes(0);
    return isaac::runtime::content::PngToPcxStreaming(png.data(),png.size(),&ImagePcxInflateRows,out,size);
}

// 贴图桥（2026-09-21）：引擎加载 `.pcx` 的最后一站。
//
// 入口中继契约：本回调**以 `ImagePcx::Load` 的身份**运行（`br` 尾调用，x0..x7 原样传入，
// `ret` 直接回到游戏调用方），所以**返回值也由本回调负责**，且**是否跑原函数由本回调决定**
// （直接调 `Original<>` 才是跑原函数）。顺序：
//   1. 先让原函数跑「`.pcx` 在」这条路径 —— 成功就直接返回，零开销、零副作用。
//   2. 失败时把路径末尾 `.pcx` 换成 `.png`，用 `g_DefaultManifestBindings` 探测/读取 Mod 资源。
//   3. 用注入的 `ImagePcxInflateOne`（包真实 zlib）把 PNG 转成 PCX 字节，喂内存版 `Load`。
//   4. 任一环节缺失/失败都退回 `false`（=「这次没加载到」），**绝不崩、绝不读卡**。
// ★ 返回值必须原样搬运：`KAGE::Graphics::ImagePcx::Load(const char*)` 返回 bool（x0 低 8 位），
//   声明成 void 会让引擎拿到垃圾值、把「加载失败」误判成成功或反之。
extern "C" bool EntryRelayImagePcxLoadCallback(void* self, const char* path) {
    using LoadFn = bool (*)(void*, const char*);
    const auto original = isaac::runtime::Original<LoadFn>(isaac::runtime::HookId::ImagePcxLoad);
    // ★★ 2026-10-04（真机崩溃 15:23 的第二道防线）：拿不到原函数就**只报"这次没加载到"**，
    //   绝不转调 —— 原函数入口为空时调它就是跳地址 0。根因已在 `entry_relay.cpp` 修掉。
    if (original == nullptr) {
        return false;
    }
    // 诊断：记下最近一次请求路径（不分来源；"进入兜底"的那条另记，见 lastFallbackPath）。
    ++g_imagePcxDiag.pcxLoadCalls;  // 270-perf：先记"中继一共被调了多少次"（含原函数成功的那些）
    if (path != nullptr) {
        std::strncpy(g_imagePcxDiag.lastRequestPath, path,
                     sizeof(g_imagePcxDiag.lastRequestPath) - 1);
        g_imagePcxDiag.lastRequestPath[sizeof(g_imagePcxDiag.lastRequestPath) - 1] = '\0';
    }
    // 原函数这条路不碰卡（只查内存里已挂的贴图），先试它。
    // 271-perf：若此刻在 `Font::Load` 窗口内，把这次调用与它花在引擎里的时间**归属**到那次字体加载。
    const bool inFontWindow = g_fontLoadWindow.load(std::memory_order_relaxed) != 0;
    std::uint64_t inWindowBeginTick = 0;
    if (inFontWindow) {
        ++g_imagePcxDiag.fontWindowPcxLoadCalls;
        inWindowBeginTick = isaac::runtime::RuntimePerfTick();
    }
    const bool pcxOriginalOk = original(self, path);
    if (inFontWindow) {
        g_imagePcxDiag.fontWindowPcxLoadMicros += ImagePcxMicrosSince(inWindowBeginTick);
    }
    if (pcxOriginalOk) {
        return true;
    }
    if (isaac::runtime::notice::integrity::IsOwnedNoticePath(path)) return false;
    // 兜底前置：路径必须是以 `.pcx` 结尾的字符串，且引擎入口/zlib 都已发布成功。
    if (path == nullptr || g_engineBindings == nullptr || g_fileBindings == nullptr ||
        EngineBindings()->inMemoryLoad == nullptr ||
        EngineBindings()->inflateInit2 == nullptr || EngineBindings()->inflate == nullptr ||
        EngineBindings()->inflateEnd == nullptr ||
        EngineBindings()->contentManager == nullptr ||
        EngineBindings()->operatorDeleteArray == nullptr) {
        return false;
    }
    const std::size_t pathLen = std::strlen(path);
    if (pathLen < 5 || !ImagePcxPathEquals(path + pathLen - 4, ".pcx")) {
        return false;  // 请求的不是 .pcx（理论上不该发生）
    }
    ++g_imagePcxDiag.fallbackAttempts;
    // 270-perf：整条兜底回调的起点（用来回答"这 ~1 秒是不是全在兜底里"）。
    const std::uint64_t fallbackBeginTick = isaac::runtime::RuntimePerfTick();
    if (path != nullptr) {
        std::strncpy(g_imagePcxDiag.lastFallbackPath, path,
                     sizeof(g_imagePcxDiag.lastFallbackPath) - 1);
        g_imagePcxDiag.lastFallbackPath[sizeof(g_imagePcxDiag.lastFallbackPath) - 1] = '\0';
    }
    // 构造同名 .png 路径（替换扩展名，容量留 1 字节余量）。
    constexpr std::size_t kPathBuf = 4096;
    char pngPath[kPathBuf];
    if (pathLen + 1 > kPathBuf) return false;
    std::memcpy(pngPath, path, pathLen);
    std::memcpy(pngPath + pathLen - 4, ".png", 4);
    pngPath[pathLen] = '\0';

    // ★ 读哪个路径：**只能用合成时记下来的那条**（它是当时解析成功过的绝对路径）。
    // 绝不能用"把收到的路径末尾换成 .png"自己拼——引擎传下来的路径**已经被它自己的
    // `CreateCleanPath` 清洗过**，拼出来的字符串和真实文件对不上 ⇒ `File::OpenRead`
    // 打开失败 ⇒ 引擎 Abort（真机 01789981130 / 01789981405 两次都栽在这条路上）。
    // 按完整合成路径匹配，只容许清洗产生的大小写和分隔符变化。
    const char* pngMounted = ImagePcxRingLookup(path);
    if (pngMounted == nullptr) {
        // 不是我们合成的请求（或记录已过期）：**什么都不做**，绝不"盲开"一条来源不明的路径。
        ++g_imagePcxDiag.ringMiss;
        return false;
    }
    // 缓存优先：命中就省掉"读文件 + inflate + 转码"三步（真机实测同一路径会被问很多次）。
    if (const ImagePcxOwnedBytes* cached = ImagePcxCacheLookup(pngMounted)) {
        ++g_imagePcxDiag.cacheHits;
        const bool loadedCached = EngineBindings()->inMemoryLoad(
            self, cached->data(), static_cast<std::uint32_t>(cached->size()), path);
        if (loadedCached) {
            ++g_imagePcxDiag.fedOk;
        } else {
            ++g_imagePcxDiag.feedFailures;  // ★ 276：交付失败的直接证据（引擎不收这块字节）
        }
        return loadedCached;
    }
    // 用已发布的文件读取绑定把 .png 读进内存（与 `GameFileReader::ReadScript` 同款流程）。
    const std::uint64_t readBeginTick = isaac::runtime::RuntimePerfTick();
    ImagePcxOwnedBytes pngBuf;
    if (!ReadPngFileForBridge(pngMounted, &pngBuf)) {
        return false;  // .png 读取失败：退回「没加载到」
    }
    const std::uint32_t readMicros = ImagePcxMicrosSince(readBeginTick);
    ++g_imagePcxDiag.readOk;
    // 271-perf：一次性标定"一次文件调用值多少微秒"（整会话只跑一次，结果记在 `calib*` 字段里）。
    ImagePcxRunFileCallCalibrationOnce(pngMounted);

    // 内存转码 + 喂内存版 Load。
    uint8_t* pcx = nullptr;
    std::size_t pcxSize = 0;
    ++g_imagePcxDiag.cacheConversions;
    const std::uint64_t convertBeginTick = isaac::runtime::RuntimePerfTick();
    const bool ok = ImagePcxConvert(pngBuf, &pcx, &pcxSize);
    const std::uint32_t convertMicros = ImagePcxMicrosSince(convertBeginTick);
    if (!ok || pcx == nullptr) {
        ++g_imagePcxDiag.convertFailures;
        return false;
    }
    const std::uint64_t feedBeginTick = isaac::runtime::RuntimePerfTick();
    const bool loaded =
        EngineBindings()->inMemoryLoad(self, pcx, static_cast<std::uint32_t>(pcxSize), path);
    const std::uint32_t feedMicros = ImagePcxMicrosSince(feedBeginTick);
    if (loaded) ImagePcxCacheInsert(pngMounted,pcx,pcxSize);
    delete[] pcx;
    if (loaded) {
        ++g_imagePcxDiag.fedOk;
    } else {
        ++g_imagePcxDiag.feedFailures;  // ★ 276：交付失败的直接证据（>0 就直接解释了"空页图"）
    }
    // 270-perf 记账：三段分别累加 + 整条兜底。
    ++g_imagePcxDiag.timedFallbacks;
    ImagePcxAccumulateMicros(&g_imagePcxDiag.readMicros, &g_imagePcxDiag.readMicrosMax, readMicros);
    ImagePcxAccumulateMicros(&g_imagePcxDiag.convertMicros, &g_imagePcxDiag.convertMicrosMax,
                             convertMicros);
    ImagePcxAccumulateMicros(&g_imagePcxDiag.feedMicros, &g_imagePcxDiag.feedMicrosMax, feedMicros);
    ImagePcxAccumulateMicros(&g_imagePcxDiag.fallbackMicros, &g_imagePcxDiag.fallbackMicrosMax,
                             ImagePcxMicrosSince(fallbackBeginTick));
    return loaded;
}

// 设备侧 zlib 包装：把三段 `z_stream` 流程（init2 + inflate(Z_FINISH) + end）包成
// `PngToPcx` 要的「一次性解压完整 zlib 流、写满 dest_len 才成功」形状。
//
// 标准 64 位 `z_stream` 布局（总长 112 = 0x70 字节），与 `inflateInit2_` 校验的
// `stream_size == 0x70`、内核 `version[0] == '1'` 一致：`version` 传 "1.1.4"。
// PNG 的 IDAT 是**带 zlib 头**的流，故 `windowBits = 15`（MAX_WBITS），不是 -15（raw deflate）。
struct ImagePcxZStream {
    void* next_in;             // +0
    std::uint32_t avail_in;    // +8
    std::uint32_t _pad0;       // +12（对齐 total_in 到 8）
    std::uint64_t total_in;    // +16
    void* next_out;            // +24
    std::uint32_t avail_out;   // +32
    std::uint32_t _pad1;       // +36
    std::uint64_t total_out;   // +40
    char* msg;                 // +48
    void* state;               // +56
    void* zalloc;              // +64
    void* zfree;               // +72
    void* opaque;              // +80
    std::int32_t data_type;    // +88
    std::uint32_t _pad2;       // +92
    std::uint64_t adler;       // +96
    std::uint64_t reserved;    // +104
};
static_assert(sizeof(ImagePcxZStream) == 112, "z_stream 必须是 112 字节");

bool ImagePcxInflateRows(const uint8_t* src,std::size_t length,std::size_t row,std::size_t rows,
                         void* context,isaac::runtime::content::RowSink sink) noexcept {
    if(!g_engineBindings) return false;
    const auto& b=*EngineBindings();
    if(!b.inflateInit2 || !b.inflate || !b.inflateEnd) return false;
    return isaac::runtime::content::InflateRows<ImagePcxZStream>(src,length,row,rows,context,sink,
        b.inflateInit2,b.inflate,b.inflateEnd,"1.1.4");
}

// 贴图桥 v2/v3 的挂点（`ImageManager::LoadImage` 文件版）——**已改为纯透传**。
//
// ★★ 2026-09-21 16:22 真机卡死教训：**不要在这个层次回调贴图管理器自己**。
// 该重载的内存版（`0x4d2654`）在"往贴图表插入"时要拿 `ImageManager+0x8` 的互斥锁，而我们的
// 回调本身就是从管理器自己的调用栈里进来的 ⇒ **自己锁死自己**（按一下键就卡死）。
// v4 起把字节的交付改到**文件层**（见 `EntryRelayContentGetMountedFilePathCallback` 与
// `EntryRelayImagePcxLoadCallback`），这个挂点只保留计数与透传，绝不再调引擎的管理器接口。
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wreturn-type-c-linkage"
#endif
// ── 272-perf：把模组自带的 `.png` 改道到我们这条转码路 ──────────────────────────────
//
// 只读 PNG 头 33 字节回答"我们的转码器能不能处理它"。三种结论分得开（诊断要能区分"没满足判据"
// 与"压根没跑到"）：
//   * `kUnreadable`  读不到 / 不是 PNG / 头不完整 ⇒ 原样放行给引擎；
//   * `kUnsupported` 位深不是 8 位、隔行、调色板（我们的转码器只支持 8bit 非隔行、颜色类型 0/2/4/6）
//                    ⇒ 原样放行给引擎；
//   * `kTooLarge`    **★ 276-perf 新增**：解码尺寸超上限 ⇒ 原样放行给引擎。
//   * `kOk`          可以改道。
//
// 为什么要有尺寸/峰值上限（276 起、**402 重算**）：转码器一次要**同时**活着好几块大缓冲
// （见 `png_to_pcx_bridge.hpp` 的峰值公式），而模块的假堆只有 **128 MiB**；分配失败会 `bad_alloc`
// （那是 `noexcept` 函数 ⇒ 直接 `terminate`）⇒ 宁可放行给引擎也别冒这个险。
// ★★★ 批次 402（2026-10-07 真机崩溃 `01791381539`）：旧口径（**只**算解码后 `(宽×通道+1)×高` ≤ 24 MiB）
//   有两个洞，真机上就是这么崩的（选模组角色进局、加载画面退回 HOME）：
//     ① **算少了**：真实峰值是 `2·文件 + 解码 + 2·行字节 + 4·宽 + 128 + 输出PCX`，其中
//        **输出 PCX 最坏 8 字节/像素**（每平面每像素 2 字节）≈ 解码量的 2 倍（RGBA）到 8 倍（灰度）；
//     ② **管错了地方**：本判据只在"`.png` 直改道"那条路（`RouteModPngThroughPcx`）上、且只拦
//        **改道前那次试转**；真正把进程带走的是**交付时那次转码**（`EntryRelayImagePcxLoadCallback`
//        的兜底，见本文件下面 `PngToPcx` 调用点）—— 它**不受本判据约束**。
//   ⇒ 现在口径 = 峰值上界（与 `PngToPcx` 用**同一个** `PngToPcxPeakUpperBound` + 同一个预算
//     `kPngToPcxPeakBudgetBytes`）；而交付那次的安全由 `PngToPcx` 自己的峰值闸门 + try/catch 兜底。
// 上限按 IHDR 的 宽×高×通道（+ 用文件长度）算，**不是**只看文件大小 —— 一张 2.4 MB 的 PNG 解出来可以是 16 MiB。
// 具体数字见下面 `kImagePcxPngMaxSide` 与公共头里的 `kPngToPcxPeakBudgetBytes`（64 MiB = 假堆的一半）。
enum class ImagePcxPngVerdict {
    kOk,
    kUnreadable,
    kUnsupported,
    kTooLarge,
    kTooSmall,
};

constexpr std::uint32_t kImagePcxPngMaxSide = 4096;
// ★★★ 279-perf：**只改道"大图"**（像素数下限）。为什么加这条（它是本批的主题）：
//
// 279 之前的改道是"凡是模组自带的 `.png` 都改道"。但**引擎里所有 `.anm2` 的精灵表都写成 `.png`**
// （实测：`rocks_basement.png`、EID 的 `eid_*.png`、GoodTrip 的 `gt_ui1.png` …），
// 于是**小精灵表也被改道** ⇒ 引擎按扩展名建的是 `ImagePcx` 而不是 `ImagePng`
// ⇒ **`anm2` 那条取精灵表的路径就把它们当空的用**（真机现象：**开着 `visible tinted rocks` 时所有石头隐形**，
//    关掉模组就正常 —— 因为那时这张表解析到的是**本体**文件、我们不改道）。
// 而**我们改道赚到的钱全部来自大图**：引擎自己解 PNG 的成本随像素数走（2048×2048 的字体页图 ≈456 ms/张），
// 256×256 的精灵表本来只要 ~1 ms ⇒ 改道它们**几乎零收益、却有真实风险**。
// ⇒ 阈值取 **1,048,576 像素（≈1024×1024）**：字体页图（2048×2048 = 4.19 M）照旧改道 ✓，
//    石头/图标那类小精灵表（256×256 = 65 k）**原样放行** ⇒ 回到"引擎自己解 PNG"的老行为。
constexpr std::uint64_t kImagePcxPngMinPixels = 1ull << 20;  // 1,048,576 像素

ImagePcxPngVerdict PngHeaderVerdictForBridge(const char* pngPath,
                                             std::uint64_t* outPixels) noexcept {
    if (outPixels != nullptr) {
        *outPixels = 0;
    }
    if (pngPath == nullptr || g_fileBindings == nullptr) {
        return ImagePcxPngVerdict::kUnreadable;
    }
    const auto& b = *FileBindings();
    if (b.construct == nullptr || b.openRead == nullptr || b.getLength == nullptr ||
        b.read == nullptr || b.close == nullptr || b.destroy == nullptr) {
        return ImagePcxPngVerdict::kUnreadable;
    }
    alignas(16) std::array<u8, kGameFileObjectSize> fileStorage{};
    std::array<u8, 33> head{};
    bool readOk = false;
    std::int64_t fileBytes = -1;
    b.construct(fileStorage.data());
    if (b.openRead(fileStorage.data(), pngPath)) {
        // ★ 402：峰值公式要用**真实文件长度**（`idat` 与调用方那份 PNG 都按文件大小计），
        //   不能只按 33 字节头估 —— 所以顺手取一次长度（同一把已打开的句柄，零额外开销）。
        fileBytes = b.getLength(fileStorage.data());
        readOk = b.read(fileStorage.data(), head.data(), 1, static_cast<int>(head.size())) ==
                 static_cast<int>(head.size());
        b.close(fileStorage.data());
    }
    b.destroy(fileStorage.data());
    if (!readOk) {
        return ImagePcxPngVerdict::kUnreadable;
    }
    // PNG 结构：签名 8 字节 + 块长 4 + "IHDR" 4 + 宽 4 + 高 4 + **位深(24)** + **颜色类型(25)** +
    //          压缩(26) + 滤波(27) + **隔行(28)** + CRC 4。
    static const u8 kSignature[8] = {0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A};
    if (std::memcmp(head.data(), kSignature, 8) != 0 ||
        std::memcmp(head.data() + 12, "IHDR", 4) != 0) {
        return ImagePcxPngVerdict::kUnreadable;
    }
    const u8 bitDepth = head[24];
    const u8 colorType = head[25];
    const u8 interlace = head[28];
    if (bitDepth != 8 || interlace != 0) {
        return ImagePcxPngVerdict::kUnsupported;
    }
    int channels = 0;
    switch (colorType) {
        case 0: channels = 1; break;  // 灰度
        case 2: channels = 3; break;  // RGB
        case 4: channels = 2; break;  // 灰度 + 透明
        case 6: channels = 4; break;  // RGBA
        default: return ImagePcxPngVerdict::kUnsupported;  // 调色板等
    }
    // ★ 276-perf：尺寸闸门。宽高是 IHDR 里的大端 32 位（偏移 16 / 20）。
    const std::uint64_t width = (static_cast<std::uint64_t>(head[16]) << 24) |
                                (static_cast<std::uint64_t>(head[17]) << 16) |
                                (static_cast<std::uint64_t>(head[18]) << 8) |
                                static_cast<std::uint64_t>(head[19]);
    const std::uint64_t height = (static_cast<std::uint64_t>(head[20]) << 24) |
                                 (static_cast<std::uint64_t>(head[21]) << 16) |
                                 (static_cast<std::uint64_t>(head[22]) << 8) |
                                 static_cast<std::uint64_t>(head[23]);
    if (width == 0 || height == 0 || width > kImagePcxPngMaxSide || height > kImagePcxPngMaxSide) {
        return ImagePcxPngVerdict::kTooLarge;
    }
    if (outPixels != nullptr) {
        *outPixels = width * height;
    }
    // ★ 279-perf：小图不改道（理由见上面 `kImagePcxPngMinPixels` 那段注释）。
    if (width * height < kImagePcxPngMinPixels) {
        return ImagePcxPngVerdict::kTooSmall;
    }
    // ★★★ 402：**峰值闸门**（不再是只看"解码后字节数"）。
    //   公式与 `PngToPcx` 里那道闸门**共用同一份**（`png_to_pcx_bridge.hpp`）⇒ 口径不会漂移：
    //   最坏峰值 = `2·文件 + 解码 + 2·行字节 + 4·宽 + 128 + 8·宽·高`（末项 = 输出 PCX 最坏 8 字节/像素）。
    //   超预算 ⇒ `kTooLarge`，**原样放行给引擎**（它自己解，慢但一定成功）。
    const std::uint64_t fileBytesForPeak =
        fileBytes > 0 ? static_cast<std::uint64_t>(fileBytes) : 0u;
    // 流式输出逐块守住同一个64MiB上限，不按16×像素预拒实际很小的字体页。
    const std::uint64_t peak = isaac::runtime::content::PngToPcxStreamingPeakUpperBound(
        fileBytesForPeak, width, static_cast<std::uint64_t>(channels), 1);
    if (peak > isaac::runtime::content::kPngToPcxPeakBudgetBytes) {
        return ImagePcxPngVerdict::kTooLarge;
    }
    return ImagePcxPngVerdict::kOk;
}

// 改道：模组自带的 `.png` → 交一条**合成的 `.pcx`** 给引擎，并把真实 `.png` 挂载路径写进环形记录。
// 于是引擎按扩展名建 `ImagePcx`、它自己的 `Load` 打不开合成路径、**我们那条现成的兜底**去读 `.png`
// + 转码 + 喂回引擎 —— 机制全部复用，不新增交付方式。
//
// 为什么必须在**中继的实参**上动手（268 的真机教训 + 本节反汇编复核）：
// `ImageManager::LoadImage` 是拿**它收到的那条路径**去 `CreateCleanPath` + `GetExtension` 分派的，
// 改 `GetMountedFilePath` 的返回值改变不了分派（267 就是这么失败的）。
const char* RouteModPngThroughPcx(const char* path) noexcept {
    namespace engine_resources = isaac::runtime::engine_resources;
    if (path == nullptr || g_engineBindings == nullptr || g_fileBindings == nullptr) {
        ++g_imagePcxDiag.pngNoBindings;  // 绑定不全：原样放行（272 就是栽在这条上）
        return path;
    }
    const std::size_t requestLen = std::strlen(path);
    if (requestLen < 5) {
        ++g_imagePcxDiag.pngNotMod;
        return path;
    }
    // ★★★ 277-perf 修正：**引擎只认"虚拟路径"（相对路径）**。
    //
    // 依据（276 上卡读数 + `ImageManager::LoadImage`@0x4d1fe4 反汇编）：引擎拿到实参后的第一件事是
    // `GetMountedFilePath(实参)`（0x4d2074），喂它一条**已经带挂载点前缀的绝对路径**（`rom:/…`）
    // 会直接解析失败 ⇒ `0x4d2078` 那条 `cbz` 跳到返回 ⇒ **交回空图**、`ImagePcx::Load` 压根没被调。
    // 真要遇到这种请求，改道也救不了它 ⇒ 原样放行（这条计数应当恒 0；有值说明引擎的行为变了）。
    if (std::strncmp(path, "rom:/", 5) == 0) {
        ++g_imagePcxDiag.pngAbsReq;
        return path;
    }
    const auto& b = *EngineBindings();
    // ★ 273-perf 修正（272 真机读数换来的）：**不要**从 `EngineBindings()->getMountedFilePath` 取解析器 ——
    // 那个字段从来没被填过（读数里"绑定指针 8 个里 1 个为空"，工具对 bit5 的标注就是"不再校验:钩子目标"）。
    // 挂载解析一直在用 `Original<>` 跳板（见本文件后面 `OriginalGetMountedFilePath()`），这里照做。
    using GetMountedFilePathFn = char* (*)(void*, const char*);
    const auto getMountedFilePath =
        isaac::runtime::Original<GetMountedFilePathFn>(
            isaac::runtime::HookId::ContentGetMountedFilePath);
    if (getMountedFilePath == nullptr || b.contentManager == nullptr ||
        b.operatorNewArray == nullptr || b.operatorDeleteArray == nullptr) {
        ++g_imagePcxDiag.pngNoBindings;  // 绑定不全：原样放行（下一轮读数要能看见这一条）
        return path;
    }
    const std::uint64_t beginTick = isaac::runtime::RuntimePerfTick();
    // ★★★ 批次 382（2026-10-06）：**先走 PC 的资源层重定向**。
    //
    // 为什么（真机读数定案，逐条证据见
    // `docs/分析-进局慢回归-批次378漏改贴图改道路径-20261006.md`）：
    // 批次 378 把"模组目录挂载"（给每个模组目录调引擎 `AddMountPoint`）整条撤掉、改成我们
    // 这条中继里的 `TryRedirectModResource` ⇒ 下面那个**原函数只认 `rom:/` 那一个应用根**，
    // 解析 `mcm_cn_font/…png` 这类**模组资源名必然失败** ⇒ 整条改道**一张都做不成**：
    // 真机读数 `收到 .png 实参 80 次｜★ 改道成功 0 次｜不是模组文件 80`
    //（277 修好那一版是 **60/60**）⇒ 进局从 4.5 秒回到 **8.9 秒**
    //（`MC_POST_PLAYER_INIT` 单次 920 ms → 8859 ms）。
    //
    // ★ 同一个文件里 `.pcx` 那条分支（`EntryRelayContentGetMountedFilePathCallback`）当时
    //   **已经**按 378 改过（见那里"批次 378 起'模组目录挂载'这条机制不存在了"的注释）
    //   ⇒ 这一处是**漏改**。写法与它逐字同形：**先问重定向、命中就用它的答案、未命中才落原函数**。
    //   重定向返回的是**引擎分配的**路径（形状与"模组目录被挂载"时**逐字节同形**，都是
    //   `rom:/isaac_mods/…`）⇒ 下面 `IsModMountedPath(mounted)` 那一步照旧成立。
    char* redirected = isaac::runtime::bridge::TryRedirectModResource(path, b.contentManager,
                                                                    getMountedFilePath,
                                                                    b.operatorDeleteArray);
    engine_resources::EngineArrayOwner mountedOwner(
        b.operatorDeleteArray,
        redirected != nullptr ? redirected : getMountedFilePath(b.contentManager, path));
    char* mounted = static_cast<char*>(mountedOwner.get());
    const char* result = path;
    if (mounted == nullptr) {
        ++g_imagePcxDiag.pngNotMod;  // 解析不出来：原样放行
    } else if (!isaac::runtime::bridge::IsModMountedPath(mounted)) {
        ++g_imagePcxDiag.pngNotMod;  // 不是模组文件（本体资源）：原样放行
    } else if (std::strlen(mounted) < 5) {
        ++g_imagePcxDiag.pngNotMod;
    } else {
            std::uint64_t pngPixels = 0;
            const ImagePcxPngVerdict verdict = PngHeaderVerdictForBridge(mounted, &pngPixels);
            if (verdict == ImagePcxPngVerdict::kTooLarge) {
                ++g_imagePcxDiag.pngTooLarge;  // ★ 276：解码尺寸超上限：原样放行给引擎
            } else if (verdict == ImagePcxPngVerdict::kTooSmall) {
                // ★★★ 279：**小图不放行改道** —— anm2 的精灵表都在这一类（石头表 256×256）。
                // 让引擎照旧自己解 PNG（它按 `.png` 建的是 `ImagePng`，anm2 认这个）。
                ++g_imagePcxDiag.pngTooSmall;
                g_imagePcxDiag.pngSkippedPixels = static_cast<std::uint32_t>(pngPixels);
            } else if (verdict != ImagePcxPngVerdict::kOk) {
                ++g_imagePcxDiag.pngUnsupported;  // 格式接不了 / 读不到：原样放行给引擎
            } else {
            // ★★★ 276-perf（273 真机崩溃换来的硬约束）：**改道之前先真转一遍**。
            //
            // 为什么：`Font::Load` 把 `LoadImage` 的返回值**直接存进页图数组** ⇒ 改道之后
            // 只要有一次没交付成功，就留下一个**空页图**，留到"第一次画字"那一刻崩
            // （273 的 `Data Abort @ 0x10` 就是这个）。⇒ 把"能不能交付"这个判断**提前**：
            // 转不动就**原样放行**给引擎 —— 引擎自己解，慢，但**页图一定加载成功**。
            //
            // ★ 277：转码缓存里已经有这张图的字节时**跳过这次真转**（同一张页图会被加载两遍 ——
            //   模组脚本期一遍、`MC_POST_PLAYER_INIT` 一遍 —— 命中就省掉一遍 157 ms）。
            bool probeOk = true;
            if (ImagePcxCacheLookup(mounted) == nullptr) {
                ImagePcxOwnedBytes pngBuf;
                uint8_t* pcx = nullptr;
                std::size_t pcxSize = 0;
                const std::uint64_t probeBeginTick = isaac::runtime::RuntimePerfTick();
                const bool readOk = ReadPngFileForBridge(mounted, &pngBuf);
                if (!readOk) {
                    ++g_imagePcxDiag.pngProbeReadFail;
                    probeOk = false;
                } else if (!ImagePcxConvert(pngBuf,&pcx,&pcxSize) ||
                           pcx == nullptr || pcxSize == 0) {
                    ++g_imagePcxDiag.pngProbeConvertFail;
                    probeOk = false;
                }
                ImagePcxAccumulateMicros(&g_imagePcxDiag.pngProbeMicros,
                                         &g_imagePcxDiag.pngProbeMicrosMax,
                                         ImagePcxMicrosSince(probeBeginTick));
                if (probeOk) {
                    ImagePcxCacheInsert(mounted, pcx, pcxSize);
                }
                delete[] pcx;
            }
            if (!probeOk) {
                ++g_imagePcxDiag.pngProbeFail;  // 转不动：原样放行给引擎（慢，但一定成功）
            } else {
                // ★★★ 277-perf 修正：**合成路径按"引擎给我们的那种形式"造** ——
                // 它给的是虚拟路径（相对），我们就还它一条虚拟路径（只换扩展名）。
                // 276 错在用了挂载解析**之后**的绝对路径（`rom:/…`）当合成路径 ⇒ 引擎第一步解析就失败。
                engine_resources::EngineArrayOwner syntheticOwner(
                    b.operatorDeleteArray, b.operatorNewArray(requestLen + 1));
                char* synthetic = static_cast<char*>(syntheticOwner.get());
                if (synthetic != nullptr) {
                    std::memcpy(synthetic, path, requestLen + 1);
                    std::memcpy(synthetic + requestLen - 4, ".pcx", 4);
                    // 键是交给引擎的完整路径，值是解析成功过的真实 PNG 路径。
                    ImagePcxRememberPath(synthetic, mounted);
                    ++g_imagePcxDiag.pngRouted;
                    result = static_cast<const char*>(syntheticOwner.Release());  // 交给引擎（它自己释放）
                }
            }
        }
    }
    g_imagePcxDiag.pngRouteMicros += ImagePcxMicrosSince(beginTick);
    return result;
}

// ── 批次 412（2026-10-08）：**PC 路径分隔符归一化**（`\` → `/`）—— 放在**图片路径被消费的那一层** ──
//
// ★★★ 411 的教训（真机读数）：411 把归一化放在 `IContentManager::GetMountedFilePath`，
//   理由是"那是路径解析的总闸"。上卡后读数里那一格**恒 0**：anm2 引用的**精灵表路径根本不经过它**
//   （`.anm2` 自己会经过 —— `lastAnm2Path` 有值；精灵表不会）。
//   ⇒ 结论：归一化必须落在**真正消费这个名字的那一层**，而不是"看起来像总闸"的那一层。
//
// 为什么是这条中继（`ImageManager::LoadImage`）：桥里 268 的真机教训 + 反汇编复核写得很清楚 ——
//   引擎拿到实参后的第一件事是 `CreateCleanPath` + `GetExtension` **按它分派**，
//   anm2 直接引 `.png` 的精灵表就是从这条路进来的（`pngArgCalls` 计的就是它）。
//
// 缓冲为什么用"长生命周期的小环形"：这个实参会被交给引擎（`original(self, path, …)`），
//   不能给栈缓冲（出函数即失效）。同族的既有做法见本文件上面那条"合成 `.pcx` 路径"用环形记录
//   保存长度生命周期字符串。用**多槽**是为了嵌套调用（一次加载里再触发一次加载）不互相踩。
namespace {
constexpr std::size_t kPathSeparatorRingSlots = 8;
char g_pathSeparatorRing[kPathSeparatorRingSlots][isaac::runtime::paths::kSeparatorQueryCapacity];
std::size_t g_pathSeparatorRingNext = 0;  // 只在游戏线程上动（与桥里其它状态同一条纪律）
}  // namespace

//: 入参里有 `\` ⇒ 返回一条**归一化后**的长生命周期副本；没有 ⇒ 原样返回入参（零拷贝）。
[[nodiscard]] const char* NormalizePathSeparatorsForEngine(const char* path) noexcept {
    if (!isaac::runtime::paths::HasWindowsSeparator(path)) {
        return path;
    }
    char* const slot = g_pathSeparatorRing[g_pathSeparatorRingNext % kPathSeparatorRingSlots];
    g_pathSeparatorRingNext += 1;
    const std::size_t written = isaac::runtime::paths::NormalizeSeparatorsInto(
        slot, isaac::runtime::paths::kSeparatorQueryCapacity, path);
    if (written == 0) {
        return path;  // 装不下（不可能：路径远短于 4096）⇒ 宁可不改，也不给半条路径
    }
    ++g_imagePcxDiag.pathSeparatorNormalized;
    return slot;
}

extern "C" isaac::runtime::relay::SmartPointerShim EntryRelayImageManagerLoadFileCallback(
    void* self, const char* rawPath, void* descriptor, int flag) {
    namespace relay = isaac::runtime::relay;
    using LoadFileFn = relay::SmartPointerShim (*)(void*, const char*, void*, int);
    const auto original =
        isaac::runtime::Original<LoadFileFn>(isaac::runtime::HookId::ImageManagerLoadFile);
    // ★★★ 批次 412：**在消费它的这一层归一化**（理由见上面那段注释）——
    //   形参改名 `rawPath`，下面整段沿用 `path`（函数体其余部分一个字没动）。
    const char* path = NormalizePathSeparatorsForEngine(rawPath);
    if (isaac::runtime::notice::integrity::IsOwnedNoticePath(path))
        return original ? original(self, path, descriptor, flag) : relay::SmartPointerShim{};
    ++g_imagePcxDiag.hookCalls;
    if (path != nullptr) {
        std::strncpy(g_imagePcxDiag.lastRequestPath, path,
                     sizeof(g_imagePcxDiag.lastRequestPath) - 1);
        g_imagePcxDiag.lastRequestPath[sizeof(g_imagePcxDiag.lastRequestPath) - 1] = '\0';
        // 270-perf：单独记一份"这个中继看到的实参"——`lastRequestPath` 被两个中继共写，
        // 上一轮就是因为它而分不清"`.png` 到底是哪一层传下来的"。
        std::strncpy(g_imagePcxDiag.lastLoadImagePath, path,
                     sizeof(g_imagePcxDiag.lastLoadImagePath) - 1);
        g_imagePcxDiag.lastLoadImagePath[sizeof(g_imagePcxDiag.lastLoadImagePath) - 1] = '\0';
    }
    // ★★★ 批次 268 的"把 `.pcx` 参数换成那条 `.png`"**已在批次 280 整体撤除** —— 它是真机回归的元凶。
    //
    // 268 当年想做的事：让引擎自己按 `.png` 分派、走它的原生 PNG 解码，省掉我们的转码。
    // ★★ 但**每一次"换参数"都让引擎交回空图**：换上去的是**绝对路径**（`rom:/isaac_mods/…`），
    //   而 `ImageManager::LoadImage` 拿到实参后的**第一件事**就是 `GetMountedFilePath(实参)`（`0x4d2074`），
    //   那个 API **只认虚拟路径（相对路径）** ⇒ `0x4d2078` 的 `cbz` 直接跳去返回 ⇒ **空镜像指针**。
    //   真机读数**两次都精确对上**：`挂点被调用 − 原函数成功 = 真换参数`
    //     （2120 − 2017 = 103 = 103；1290 − 1269 = 21 = 21）。
    // ★★ 后果（用户 2026-10-02 报的回归）：**模组"覆盖本体已有 `.pcx`"的那一类素材全部变成空图**——
    //   石头表 `gfx/grid/rocks_basement.pcx` 正是从这条路进来的 ⇒ **一张表空 = 房间内所有石头隐形**
    //   （能炸、有碰撞，因为碰撞与画图是两条路）。
    //   EID / GoodTrip 的精灵表是 anm2 **直接引 `.png`** 进来的，**不经过这里** ⇒ 一直正常
    //   （这条差异就是把范围压到这里的判据）。
    // ★ 撤掉之后，这类请求回到**既有的 `.pcx` 补位路**（2026-09-21 起验证过能用的那条）：
    //   解析器补位 → `ImagePcx::Load(相对 .pcx)` 打不开（它只查内存里**已挂**的贴图、不碰卡）
    //   → **我们的兜底**按环形记录读那张 `.png`、转码、喂回引擎 ⇒ 模组的图正常显示。
    // ⇒ 整段换参数代码删除。`loadImageSwaps` / `lastSwapFrom` / `lastSwapTo` 三个字段**保留但恒 0**
    //   （字段偏移一旦发布就不再动），读数工具的措辞已注明"268 已撤、应恒 0"。
    const char* effectivePath = path;
    bool routedModPng = false;
    if (path != nullptr) {
        const std::size_t pathLength = std::strlen(path);
        if (pathLength >= 5 && std::memcmp(path + pathLength - 4, ".pcx", 4) == 0) {
            ++g_imagePcxDiag.loadImagePcxSuffix;  // 270-perf：实参确实是 `.pcx` 的次数
            // ★ 280：**这里什么都不做**（原样透传给引擎）—— 268 的换参数已撤，理由见上。
        } else if (pathLength >= 5 && std::memcmp(path + pathLength - 4, ".png", 4) == 0) {
            // 272-perf：**模组自带的 `.png` 改道去走我们的转码路** —— 修法的入口。
            // 依据：引擎自己解 `.png`（libpng）平均 456 ms/次，我们那条转码路单次最大 11.2 ms。
            ++g_imagePcxDiag.pngArgCalls;
            effectivePath = RouteModPngThroughPcx(path);
            routedModPng = (effectivePath != path);
        }
    }
    // 271-perf：在 `Font::Load` 窗口内时，把这次加载与它在引擎里花的时间归属到那次字体加载。
    const auto loadWith = [&](const char* loadPath) -> relay::SmartPointerShim {
        if (g_fontLoadWindow.load(std::memory_order_relaxed) == 0) {
            return original(self, loadPath, descriptor, flag);
        }
        ++g_imagePcxDiag.fontWindowLoadImageCalls;
        const std::uint64_t beginTick = isaac::runtime::RuntimePerfTick();
        const relay::SmartPointerShim direct = original(self, loadPath, descriptor, flag);
        g_imagePcxDiag.fontWindowLoadImageMicros += ImagePcxMicrosSince(beginTick);
        return direct;
    };
    relay::SmartPointerShim result = loadWith(effectivePath);
    // ★★★ 276-perf：**改道的保底重试**（273 真机崩溃换来的第二道防线）。
    //
    // 为什么要它：改道只是"把参数换成合成 `.pcx` 路径"，能不能真拿到图取决于引擎里面
    // `ImagePcx::Load` 那一次交付（读挂载解析 / 找记录 / 喂内存版 `Load` 三道都可能失败）。
    // 而 `Font::Load` 把 `LoadImage` 的返回值**直接存进页图数组** ⇒ 只要有一次拿不到图，
    // 就留下一个**空页图**，留到"第一次画字"那一刻崩（`Data Abort @ 0x10`）。
    // ⇒ 拿不到就**用原始那条 `.png` 路径再走一遍引擎自己的原生 PNG 路**：慢（平均 456 ms），
    //   但那是**引擎原本就在走**的路 ⇒ 原来能加载成功的，这里一定也能成功。
    // ⇒ 于是在"我们这侧出了任何问题"的情形下，行为退化到**改道之前**，而不会退化到崩溃。
    //
    // 真机读数里 `pngNativeRetry` **必须为 0**（一有值就说明改道的交付链有问题，读数会直接点出来）。
    if (routedModPng && result.pointer == nullptr) {
        ++g_imagePcxDiag.pngNativeRetry;
        result = loadWith(path);
        if (result.pointer != nullptr) {
            ++g_imagePcxDiag.pngNativeRetryOk;
        }
    }
    if (result.pointer != nullptr) {
        ++g_imagePcxDiag.originalOk;
    }
    return result;
}
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

// 路径解析的原函数（入口中继的回退入口）：解析 `.png` 时用它 —— **不经过**本钩子的补位逻辑，
// 因此天然不会递归；也不需要"逐字节校验绑定"（挂点安装时已经核对过原版序言）。
using GetMountedFn = char* (*)(void*, const char*);
GetMountedFn OriginalGetMountedFilePath() noexcept {
    return isaac::runtime::Original<GetMountedFn>(
        isaac::runtime::HookId::ContentGetMountedFilePath);
}

// 批次 352/353：**主动探测一组路径**（表在 `image_mount_query_watch.hpp`）。
//
// 为什么要主动问：只记"消费者来问时答了什么"，那个 0 有两种相反的含义（**没被问到** / 被问到且答对了）。
// 主动问一次就消掉这个歧义 —— 无论模组走不走这条中继，读数都能答出"引擎此刻把这条路径解析给了谁"。
//
// 硬纪律（与 `.png` 那次探测同源）：**一律走原函数**（`original`），不能递归进我们自己的中继；
// 返回的串按引擎的 `operator delete[]` 归还（`EngineArrayOwner`）；**只读**，不写引擎任何状态。
void RunSharedPathProbes(void* self, GetMountedFn original) noexcept {
    namespace bridge_ns = isaac::runtime::bridge;
    for (std::size_t index = 0; index < bridge_ns::kSharedPathProbeQueries.size(); ++index) {
        const char* query = bridge_ns::kSharedPathProbeQueries[index];
        // 这里用**全限定名**：`engine_resources` 那个别名只在中继回调的函数体里声明过。
        isaac::runtime::engine_resources::EngineArrayOwner owner(
            EngineBindings()->operatorDeleteArray, original(self, query));
        const char* answer = static_cast<const char*>(owner.get());
        const bool modWin = bridge_ns::IsModMountedPath(answer);
        SharedPathProbeRecord& record = g_imagePcxDiag.sharedPathProbes[index];
        ++record.runs;
        if (record.runs == 1) {
            record.firstModWin = modWin ? 1U : 0U;  // ★ 与 last 对比 ⇒ "结果会不会变"
        }
        if (modWin) {
            ++record.modWins;
        }
        record.lastModWin = modWin ? 1U : 0U;
        ImagePcxCopyDiagString(record.query, sizeof(record.query), query);
        ImagePcxCopyDiagString(record.answer, sizeof(record.answer), answer);
        // ★ 批次 361：把"第几次探测 + 当时的模组数"一起记 —— 读数才不会再把"还没挂"当成"丢了"。
        g_imagePcxDiag.probeSeq[index] = ++g_pathProbeSequence;
        g_imagePcxDiag.probeModCount[index] = ModCountNow();
        // 352 那三格（单路径版）继续写：表里**第一条**就是它 ⇒ 旧口径不失效、两处读数可互校。
        if (index == 0) {
            ++g_imagePcxDiag.sharedProbeRuns;
            if (g_imagePcxDiag.sharedProbeRuns == 1) {
                g_imagePcxDiag.sharedProbeFirstModWin = modWin ? 1U : 0U;
            }
            g_imagePcxDiag.sharedProbeModWin = modWin ? 1U : 0U;
            ImagePcxCopyDiagString(g_imagePcxDiag.sharedProbeQuery,
                                   sizeof(g_imagePcxDiag.sharedProbeQuery), query);
            ImagePcxCopyDiagString(g_imagePcxDiag.sharedProbeAnswer,
                                   sizeof(g_imagePcxDiag.sharedProbeAnswer), answer);
        }
    }
}

// 贴图桥 v4（2026-09-21 晚）：`IContentManager::GetMountedFilePath` —— 在"文件层"补位。
//
// 引擎的文件版贴图加载在**创建贴图对象之前**就用它判断"文件在不在任何挂载点"；`.pcx` 不在
// 就直接返回空（这正是一路失败的根因）。这里在"`.pcx` 不在、但同名 `.png` 在"时，返回一条
// **合成的 `.pcx` 挂载路径**（=`.png` 的挂载路径换扩展名）：
//   * 引擎随后按"扩展名 pcx"建 `ImagePcx`、调它自己的文件版 `Load` ⇒ 我们已挂在
//     `ImagePcx::Load` 上的回调**这时才第一次能被调到**（v1 当年等不到的就是这个前提）；
//   * 那条回调里我们读 `.png`、转 PCX、调**对象自己的**内存版 `Load`（纯对象级、无锁），
//     引擎再自己完成缓存与登记 —— **全程不碰管理器，无重入、无自锁**。
// 合成路径必须用**游戏自己的 `operator new[]`** 分配：调用方会用 `_ZdaPv` 释放它。
// ★ 2026-09-21：`.pcx` 请求的**优先级**要跟 PC 一致 —— PC 模组的贴图是 PNG，
// 而它要覆盖的目标在本体（Switch 版）是**已存在的 `.pcx`**。
//
// 改前的行为：`original(path)` 只要答得出来（哪怕答的是**本体**那份 `.pcx`）就直接交回
// ⇒ 桥永远等不到 ⇒ 模组的 PNG **被静默忽略**（用户实例：`visible tinted rocks` 的
// 23 张 `gfx/grid/rocks_*.png`，而本体 `resources/gfx/grid/` 下就有 13 张同名 `.pcx`）。
//
// 改后的规则（三步）：
//   1. 先按原样问引擎（这一步同时给出"模组自带 `.pcx`"的情形）；
//   2. 若结果**是模组自己的文件** ⇒ 原样交回（**不抢**模组自己的 `.pcx`）；
//   3. 否则（没找到，或找到的是**本体**那份）⇒ 再问一次同名 `.png`：
//      问到 ⇒ 合成 `.pcx` 路径（与"模组自带新贴图"那条路完全一样，交给 `ImagePcx::Load` 转码）；
//      问不到 ⇒ 保持原结果（本体那份照旧用，或维持"文件不存在"）。
//
// 为什么"问得到 `.png`"就等于"这是模组的文件"：Switch 版本体资源**一个 `.png` 都没有**
// （本机整棵本体树 `find -name '*.png'` = 0）⇒ 只有模组会带 PNG。
//
// 代价：每次 `.pcx` 查询多一次挂载搜索（只在"结果不是模组文件"时才多）。诊断里有
// `pngOverrideWins` 计数，真机读数可以看它到底发生了多少次。
// （判据 `IsModMountedPath` 放在头文件里，宿主门禁 `test_png_override_priority.py` 直接测它。）
extern "C" char* EntryRelayContentGetMountedFilePathCallback(void* self, const char* path) {
    namespace engine_resources = isaac::runtime::engine_resources;
    const auto original = OriginalGetMountedFilePath();
    // ★★ 2026-10-04（真机崩溃 15:23）：**拿不到原函数就绝不转调。**
    //
    // 那次崩溃的现场是 `Instruction Abort`、`PC = 0`、`LR` 正好落在本函数里调 `original`
    // 的那一条指令上（`runtime + 0x9460`）—— 也就是"原函数入口是空指针，我们还是调了它"。
    // 根因已经在 `entry_relay.cpp` 里修掉（曾有一个"入口已改、原函数入口还没公布"的窗口），
    // 这一道判空是**第二道防线**：万一还有别的路径让它是 0，这里退化成"这条路径没挂载"
    // （交回空指针）—— 对调用方来说与"文件不存在"同义，**比整机崩掉好得多**。
    if (original == nullptr) {
        return nullptr;
    }
    if (isaac::runtime::notice::integrity::IsOwnedNoticePath(path)) return original(self, path);
    // ★★★ 批次 412（2026-10-08）：**归一化不放在这里** —— 411 就放在这里，真机读数那一格**恒 0**。
    //
    // 为什么（411 的实测教训）：`.anm2` 自己确实经过这个入口（`lastAnm2Path` 有值），
    //   但 **anm2 引用的精灵表路径不经过它** ⇒ 放在这里等于给一条走不到的路修栅栏。
    //   ⇒ 归一化搬到 `EntryRelayImageManagerLoadFileCallback`（`ImageManager::LoadImage` 那条中继，
    //     引擎拿它收到的实参去 `CreateCleanPath` + `GetExtension` 分派）——见本文件上面
    //     `NormalizePathSeparatorsForEngine` 那一段。
    // 这里保留 `path` 这个名字（形参原样），一行行为都不改。
    // ★★ 批次 378（2026-10-05）：**先问一遍 PC 的资源层重定向**。
    //
    // 这是"PC 那一环在 Switch 上的落点"：PC 的 `ModManager::GetModResourcePath @0x870460`
    // 按模组清单顺序取第一个启用的模组、先 `<模组>/resources-dlc3/<名>` 再 `<模组>/resources/<名>`；
    // 规则与取证见 `mod_resource_redirect.hpp` 与
    // `docs/分析-模组挂载机制与371没音乐定案-20261005.md`。
    //
    // 接入方式刻意取"**命中就把它的答案当成引擎的答案**"（而不是提前 return）：
    //   * 下面所有既有逻辑（`.pcx` 分支、`IsModMountedPath`、按路径监控、环形历史、主动探测）
    //     看到的仍旧是"引擎给的那条路径" ⇒ 与本批之前（模组目录被挂载时）**逐字节同形**；
    //   * 未命中时 `redirected == nullptr`，`original(self, path)` 照旧被问一次，
    //     本函数的行为与 375 之前完全一致。
    // 301: `mountedOwner` 归还的是引擎分配的那条路径 —— 命中时归还的是**探测出来**的那条
    //      （同样由引擎的 `operator new[]` 分配，`EngineArrayOwner` 用 `_ZdaPv` 释放 ✓）。
    char* redirected = nullptr;
    if (path != nullptr) {
        redirected = isaac::runtime::bridge::TryRedirectModResource(
            path, self, original,
            EngineBindings() != nullptr ? EngineBindings()->operatorDeleteArray : nullptr);
    }
    // 引擎分配、需要**我们**还回去的两种路径 —— 一律用 `EngineArrayOwner` 持有：
    // 提前 return 时由析构自动归还，交回引擎时显式 `Release()`。
    // ★ 2026-09-29（批次 196）起因：成功返回合成路径那条路**既没还也没交** `mounted`
    //   ⇒ 每次"模组 PNG 顶掉本体 `.pcx`"泄漏一条路径字符串。换成 RAII 之后这种"漏"写不出来。
    engine_resources::EngineArrayOwner mountedOwner(
        EngineBindings() != nullptr ? EngineBindings()->operatorDeleteArray : nullptr,
        redirected != nullptr ? redirected : original(self, path));
    char* mounted = static_cast<char*>(mountedOwner.get());
    if (path == nullptr) {
        return static_cast<char*>(mountedOwner.Release());
    }
    const std::size_t pathLen = std::strlen(path);
    if (pathLen < 5 || std::memcmp(path + pathLen - 4, ".pcx", 4) != 0) {
        // ★★ 批次 351（2026-10-04）：**非 `.pcx` 的查询也记一笔**（只读计数，不改行为）。
        // ★★★ 批次 352（2026-10-04）：从"全局计数"升级成"**按路径记**" —— 351 的真机读数证明
        //     全局计数判不了归属（模组独有 / 本体独有 / 两边都有 三类混在一起）；
        //     字段含义与理由见 `ImagePcxDiagnostics` 里 352 那一段。
        namespace bridge_ns = isaac::runtime::bridge;
        ++g_imagePcxDiag.mountOtherCalls;
        const bool answeredWithModPath = bridge_ns::IsModMountedPath(mounted);
        if (answeredWithModPath) {
            ++g_imagePcxDiag.mountOtherModWins;
            // ★ 批次 356：**排除回声** —— 查询本身就是模组路径时，答回模组路径是"原样答回"，
            //   不是"模组覆盖了本体"。只有查询**不是**模组路径却答出模组目录，才算真覆盖。
            if (!bridge_ns::IsModMountedPath(path)) {
                ++g_imagePcxDiag.mountOtherModWinsReal;
            }
        } else {
            ++g_imagePcxDiag.mountOtherNotMod;
        }
        if (pathLen >= 5 && std::memcmp(path + pathLen - 5, ".anm2", 5) == 0) {
            ++g_imagePcxDiag.mountAnm2Calls;
            if (answeredWithModPath) {
                ++g_imagePcxDiag.mountAnm2ModWins;
            }
            ImagePcxCopyDiagString(g_imagePcxDiag.lastAnm2Path,
                                   sizeof(g_imagePcxDiag.lastAnm2Path), path);
            ImagePcxCopyDiagString(g_imagePcxDiag.lastAnm2Answer,
                                   sizeof(g_imagePcxDiag.lastAnm2Answer), mounted);
        }
        // ★ 批次 352：两条被监视的路径 —— minimapi 的 `IsBadLoad()` 读的就是它们。
        const bridge_ns::MountQueryWatch watch = bridge_ns::ClassifyMountQueryPath(path);
        if (watch == bridge_ns::MountQueryWatch::Minimap1) {
            ++g_imagePcxDiag.minimap1Calls;
            if (answeredWithModPath) {
                ++g_imagePcxDiag.minimap1ModWins;
            }
            ImagePcxCopyDiagString(g_imagePcxDiag.minimap1LastQuery,
                                   sizeof(g_imagePcxDiag.minimap1LastQuery), path);
            ImagePcxCopyDiagString(g_imagePcxDiag.minimap1LastAnswer,
                                   sizeof(g_imagePcxDiag.minimap1LastAnswer), mounted);
        } else if (watch == bridge_ns::MountQueryWatch::Minimap2) {
            ++g_imagePcxDiag.minimap2Calls;
            if (answeredWithModPath) {
                ++g_imagePcxDiag.minimap2ModWins;
            }
            ImagePcxCopyDiagString(g_imagePcxDiag.minimap2LastQuery,
                                   sizeof(g_imagePcxDiag.minimap2LastQuery), path);
            ImagePcxCopyDiagString(g_imagePcxDiag.minimap2LastAnswer,
                                   sizeof(g_imagePcxDiag.minimap2LastAnswer), mounted);
        }
        // ★ 批次 353：**环形历史** —— 最近 6 条非 `.pcx` 查询的"路径 + 回答"。
        //   352 只留了"最近一条 `.anm2`"，看不出"到底有哪些路径在这条路上走"。
        {
            const std::size_t slot = g_imagePcxDiag.otherRingCount % kOtherQueryRingSlots;
            ImagePcxCopyDiagString(g_imagePcxDiag.otherRingPath[slot],
                                   sizeof(g_imagePcxDiag.otherRingPath[slot]), path);
            ImagePcxCopyDiagString(g_imagePcxDiag.otherRingAnswer[slot],
                                   sizeof(g_imagePcxDiag.otherRingAnswer[slot]), mounted);
            ++g_imagePcxDiag.otherRingCount;
        }
        // ★★ 批次 352/353：**主动探测一组路径** —— 不依赖"模组来不来问"，所以哪怕 minimapi
        //   压根不走这条中继，这几格也能答出"引擎此刻把哪种路径解析给了谁"。
        if (EngineBindings() != nullptr && EngineBindings()->operatorDeleteArray != nullptr &&
            bridge_ns::ShouldRunSharedPathProbe(g_imagePcxDiag.mountOtherCalls,
                                                kSharedPathProbePeriod)) {
            RunSharedPathProbes(self, original);
        }
        // ★ 批次 357：时间轴的最后一刀 —— **第一次非 `.pcx` 查询**（也就是游戏真正开始查资源之后的
        //   最早一个点）。与"挂载收尾 / 内容步收尾 / 第一个 update 回调"三刀合起来，
        //   就能把"挂载点什么时候没的"夹到某一对之间。
        if (g_imagePcxDiag.mountOtherCalls == 1) {
            bridge_ns::NoteMountVisibilityCheckpoint(3);
        }
        return static_cast<char*>(mountedOwner.Release());  // 只补 `.pcx` 这一类
    }
    ++g_imagePcxDiag.mountPcxCalls;  // ★ 277：这条中继真的有 `.pcx` 请求进来（"改道的交付链走到过这里"）
    if (isaac::runtime::bridge::IsModMountedPath(mounted)) {
        ++g_imagePcxDiag.mountModOwn;  // ★ 277：模组自带 `.pcx`
        return static_cast<char*>(mountedOwner.Release());  // 用它的，不做额外探测
    }
    if (g_engineBindings == nullptr ||
        EngineBindings()->operatorNewArray == nullptr ||
        EngineBindings()->operatorDeleteArray == nullptr) {
        return static_cast<char*>(mountedOwner.Release());  // 绑定不全：不动引擎的答案（至少把已有结果交回）
    }
    char pngPath[4096];
    if (pathLen + 1 > sizeof(pngPath)) return static_cast<char*>(mountedOwner.Release());
    std::memcpy(pngPath, path, pathLen);
    std::memcpy(pngPath + pathLen - 4, ".png", 4);
    pngPath[pathLen] = '\0';
    // 问 `.png`：**先走 PC 的资源层重定向**（批次 378 起"模组目录挂载"这条机制不存在了 ⇒
    // 模组那份 `.png` 只能由重定向给出），未命中再调**原函数**问一次
    // （原函数不经过本钩子的补位逻辑，天然不会递归）。
    char* pngRedirected = isaac::runtime::bridge::TryRedirectModResource(
        pngPath, self, original, EngineBindings()->operatorDeleteArray);
    engine_resources::EngineArrayOwner pngOwner(EngineBindings()->operatorDeleteArray,
                                                pngRedirected != nullptr
                                                    ? pngRedirected
                                                    : original(self, pngPath));
    char* pngMounted = static_cast<char*>(pngOwner.get());
    if (pngMounted == nullptr) {
        // ★★ 277-perf：这条分支过去是**静默**返回空的 —— 276 上卡那次"改道 39 张一张都没送到"
        // 就是栽在这里（我们当时交上去的是绝对路径 ⇒ 引擎拿它来问，这里解析 `.png` 也失败）。
        // ⇒ 现在它有自己的计数（`mountPngMiss`）。**这就是"探针要能区分没满足判据和压根没跑到"**。
        ++g_imagePcxDiag.mountPngMiss;
        return static_cast<char*>(mountedOwner.Release());  // `.png` 也没有：照旧（本体那份 `.pcx`，或"文件不存在"）
    }
    const std::size_t mountedLen = std::strlen(pngMounted);
    if (mountedLen < 5) {
        return static_cast<char*>(mountedOwner.Release());
    }
    // 我方分配、**交给引擎释放**的那一块 —— 显式 `Release()`（析构不再管它）。
    engine_resources::EngineArrayOwner syntheticOwner(EngineBindings()->operatorDeleteArray,
                                                      EngineBindings()->operatorNewArray(mountedLen + 1));
    char* synthetic = static_cast<char*>(syntheticOwner.get());
    if (synthetic == nullptr) {
        return static_cast<char*>(mountedOwner.Release());
    }
    std::memcpy(synthetic, pngMounted, mountedLen + 1);
    std::memcpy(synthetic + mountedLen - 4, ".pcx", 4);
    ImagePcxRememberPath(synthetic, pngMounted, path);
    ++g_imagePcxDiag.syntheticPaths;
    ++g_imagePcxDiag.mountSynth;  // ★ 277：这次"补位"真的合成并交回了一条路径
    if (mounted != nullptr) {
        // 走的是"模组 PNG 顶掉本体 `.pcx`"这条路（`mounted` 是本体那份，被我们让位了）。
        // ★ `mounted` 由 `mountedOwner` 在函数返回时归还 —— 这里只计数。
        ++g_imagePcxDiag.pngOverrideWins;
    }
    // `pngMounted` 由 `pngOwner` 析构归还；`mounted` 由 `mountedOwner` 析构归还；
    // 只有 `synthetic` 交给引擎（引擎拿到后自己释放）。
    return static_cast<char*>(syntheticOwner.Release());
}

} // namespace

// ── 271-perf：给 `font_api.cpp` 用的两个跨 TU 入口 ────────────────────────────────
// 纪律：跨 TU 的记账**只走函数调用**（PLT），不直接引用全局量 —— 后者会通过数据 GOT 取地址，
// 而那个槽在运行时是 0（见 `interfaces/lua/runtime_perf.hpp` 顶部的批次 081 事故）。
extern "C" void IsaacRuntime_FontLoadWindowBegin() noexcept {
    g_fontLoadWindow.store(1, std::memory_order_relaxed);
}

// `micros` = 这次 `Font::Load` 的时长；`glyphCount` / `charsSpan` = 从 Font 对象上读到的
// 字形数与"字形块大小/10"（偏移由 `Font::Load` 的反汇编推得，只读、不参与任何判断）。
extern "C" void IsaacRuntime_FontLoadWindowEnd(std::uint32_t micros, std::uint32_t glyphCount,
                                               std::uint32_t charsSpan) noexcept {
    g_fontLoadWindow.store(0, std::memory_order_relaxed);
    ++g_imagePcxDiag.fontWindowCount;
    ImagePcxAccumulateMicros(&g_imagePcxDiag.fontWindowMicros, &g_imagePcxDiag.fontWindowMicrosMax,
                             micros);
    g_imagePcxDiag.fontLastGlyphCount = glyphCount;
    g_imagePcxDiag.fontLastCharsSpan = charsSpan;
}

namespace isaac::runtime::bridge {

void Attach(const GameFileReader::Bindings* fileBindings,
            const GameFileReader::ImagePcxBindings* engineBindings) noexcept {
    g_fileBindings.store(fileBindings, std::memory_order_release);
    g_engineBindings.store(engineBindings, std::memory_order_release);
}

// ── 批次 418（2026-10-09）：把那个转码结果缓存的**实际占用**读出来（只读，给读数用） ──────
//
// 为什么需要它：`kImagePcxCacheBudgetBytes` 是 **24 MiB 的预算**，不是"现在驻留了多少"。
// 417 的真机读数说"模块堆已用 120.8 MB、其中 Lua 状态 36.8 MB"，而剩下那 ≈84 MB
// **归因不到任何一条代码缓冲** —— 全镜像反汇编穷举下来，模块自己的堆分配点只有 6 个函数
// （`ImagePcxCacheInsert` / `ReadPngFileForBridge` / `PngToPcx` / `IsaacRenderText` /
// `IsaacRenderScaledText` / `CreateSpriteHandle`），常驻上限加起来不到 25 MiB。
// ⇒ 必须先把"这一类带预算的缓存到底驻留了多少"量出来，才能判断 84 MB 是"真实的分配/碎片"
// 还是"`mallinfo` 口径高估"。这一格就是那件事的第一步。
//
// ★★ 为什么走函数、**不**按符号偏移硬读 `used_bytes_`：那个偏移取决于 `BudgetedLruCache`
// 的结构体布局，而布局一变（加字段、换 `Value` 类型）偏移就漂 —— 硬编码偏移会**静默读错**，
// 而读数看起来完全正常（本项目在"判据里硬编码常量"上已经踩过：去抖窗口写死 6 那一次）。
// ★ 只在 60 帧节拍里调一次（见 `mod_menu_native.cpp` 的 `NoteHeapUsagePeriodically`），
// 不在每帧热路径上。
void ClearImagePcxConversionCache() noexcept {
    g_ImagePcxCache.TrimToBytes(0);
    g_ImagePcxSyntheticRingCount.store(0,std::memory_order_release);
}

std::uint32_t ImagePcxCacheUsedBytes() noexcept {
    const std::size_t used = g_ImagePcxCache.used_bytes();
    return used > 0xFFFFFFFFULL ? 0xFFFFFFFFu : static_cast<std::uint32_t>(used);
}

// 批次 353/354：把"我们登记了哪个模组目录、结果如何"记进诊断结构体（只留痕，不改行为）。
// 上限写死 12（卡上模组是 9 个量级）；满了就不再记，但 `modMountCount` **照样累加** ——
// 这样读数里"计数 > 名单里的条数"本身就是"有截断"的直接证据，不会悄悄丢信息。
// ★ 354：**目录名与状态按同一个下标对齐**，所以三张表永远能逐行对上（哪怕有截断）。
void RecordModMountResult(const char* directory, unsigned statusCode,
                          unsigned failedLeaf) noexcept {
    const std::uint32_t index = g_imagePcxDiag.modMountCount;
    ++g_imagePcxDiag.modMountCount;
    if (index >= 12) {
        return;
    }
    ImagePcxCopyDiagString(g_imagePcxDiag.modMountDirectories[index],
                           sizeof(g_imagePcxDiag.modMountDirectories[index]), directory);
    g_imagePcxDiag.modMountStatus[index] = static_cast<std::uint32_t>(statusCode);
    g_imagePcxDiag.modMountFailedLeaf[index] = static_cast<std::uint32_t>(failedLeaf);
}

// 批次 356/357：**同一个查询在多个时间点各问一次**（叶子相对形式）。
//
// 硬纪律（与 `.png` / 四条路径那两处探测同源）：一律走**原函数**入口、返回串按引擎的
// `operator delete[]` 归还、**只读**；入口中继还没装上（或绑定不全）时返回 false 并把
// 回答写成空串 —— 读数里靠 `runs` 分辨"没跑"与"跑了但没命中"，不硬凑。
// 批次 361：把"问哪一条"参数化（原来写死 `kMountVisibilityQuery`），供"共享路径"那几格复用。
static bool QueryPathNow(const char* query, char* answer, std::size_t capacity) noexcept {
    if (answer != nullptr && capacity != 0) {
        answer[0] = '\0';
    }
    if (query == nullptr || g_engineBindings == nullptr ||
        EngineBindings()->operatorDeleteArray == nullptr ||
        EngineBindings()->contentManager == nullptr) {
        return false;
    }
    const GetMountedFn original = OriginalGetMountedFilePath();
    if (original == nullptr) {
        return false;
    }
    isaac::runtime::engine_resources::EngineArrayOwner owner(
        EngineBindings()->operatorDeleteArray,
        original(EngineBindings()->contentManager, query));
    const char* got = static_cast<const char*>(owner.get());
    ImagePcxCopyDiagString(answer, capacity, got);
    return IsModMountedPath(got);
}

static bool QueryMountVisibilityNow(char* answer, std::size_t capacity) noexcept {
    return QueryPathNow(kMountVisibilityQuery, answer, capacity);
}


// 批次 356：**"刚挂完就问一次"**（时间轴的第一刀）—— 细节见头文件里那段注释。
void ProbeMountVisibilityAfterMounting() noexcept {
    const bool hit = QueryMountVisibilityNow(g_imagePcxDiag.modMountTimeProbeAnswer,
                                             sizeof(g_imagePcxDiag.modMountTimeProbeAnswer));
    ++g_imagePcxDiag.modMountTimeProbeRuns;
    g_imagePcxDiag.modMountTimeProbeModWin = hit ? 1U : 0U;
    // ★ 357：同一问也记进时间轴位图（bit 0 = 挂载收尾）。
    NoteMountVisibilityCheckpoint(0);
}

// 批次 357：**时间轴的其它几刀**（bit 0..3 的含义见头文件）。只读；重复调用是幂等的记一位。
void NoteMountVisibilityCheckpoint(unsigned index) noexcept {
    if (index >= 32) {
        return;
    }
    const bool hit = QueryMountVisibilityNow(nullptr, 0);
    ++g_imagePcxDiag.mountCheckpointRuns;
    if (hit) {
        g_imagePcxDiag.mountVisibilityBitmap |= (1U << index);
    }
}

// 批次 357：**重建挂载点中继装上没有** —— "跑过 0 次"与"没装上"是两件事，必须分开记。
void NoteRebuildMountPointsRelayInstalled(bool installed) noexcept {
    g_imagePcxDiag.rebuildRelayInstalled = installed ? 1U : 0U;
}

// 批次 357：重挂试过没有、返回什么。
void NoteRemountResult(unsigned statusCode) noexcept {
    g_imagePcxDiag.remountAttempted = 1U;
    g_imagePcxDiag.remountStatus = static_cast<std::uint32_t>(statusCode);
}

// 批次 358：重建挂载点中继的**失败码 + 现场字节**（只读；指针为 null 时那一段留空）。
void NoteRebuildRelayVerifyDetail(unsigned failureCode, const void* target16,
                                  const void* stub16, unsigned slotLow32) noexcept {
    g_imagePcxDiag.rebuildRelayVerifyFailure = static_cast<std::uint32_t>(failureCode);
    (void)slotLow32;  // 槽的状态由发布那一步的失败码表达，这里不重复记
    if (target16 != nullptr) {
        std::memcpy(g_imagePcxDiag.rebuildRelayTargetBytes, target16,
                    sizeof(g_imagePcxDiag.rebuildRelayTargetBytes));
    }
    if (stub16 != nullptr) {
        std::memcpy(g_imagePcxDiag.rebuildRelayStubBytes, stub16,
                    sizeof(g_imagePcxDiag.rebuildRelayStubBytes));
    }
}

// 批次 359：入口中继（`RebuildMountPoints` = 活的路径）的安装结果与失败码。
void NoteRebuildMountPointsEntryRelay(bool installed, unsigned failureCode) noexcept {
    g_imagePcxDiag.entryRelayRebuildInstalled = installed ? 1U : 0U;
    g_imagePcxDiag.entryRelayRebuildFailure = static_cast<std::uint32_t>(failureCode);
}

// 批次 359：我们那层"先跑原函数、再重挂"的包装被调用了几次（0 次 = 引擎清表不走这个函数）。
void NoteRebuildMountPointsEntryRelayCallbackFired() noexcept {
    ++g_imagePcxDiag.entryRelayRebuildCalls;
}

// 批次 361：**挂载之后的晚点试验** —— 一对"重挂前/重挂后"的测量，专门量**共享路径归谁**。
// 为什么要"重挂前"这一半：如果共享路径本来答本体、重挂后答模组 ⇒ 病根就是**注册顺序**
// （本体层在我们之后注册、压过了我们），而修法正是"在引擎初始化之后把模组挂载点补到最后"。
// ★ 只在模组数 > 0 时才跑（否则不置 done，留给下一帧再试）。
void RunLateRemountTrial() noexcept {
    if (g_imagePcxDiag.lateTrialTick != 0) {
        return;  // 只做一次
    }
    isaac::runtime::ContentMountService* service = isaac::runtime::SessionContentMountService();
    if (service == nullptr || service->mod_count() == 0) {
        return;  // 还没挂上 ⇒ 不置 done，下次再来
    }
    g_imagePcxDiag.lateTrialTick = g_pathProbeSequence + 1;  // 非 0 即"跑过了"（值只作参照）
    const char* sharedQuery = isaac::runtime::bridge::kSharedPathProbeQueries[2];  // 共享路径
    g_imagePcxDiag.lateSharedBeforeModWin =
        QueryPathNow(sharedQuery, g_imagePcxDiag.lateSharedBeforeAnswer,
                     sizeof(g_imagePcxDiag.lateSharedBeforeAnswer)) ? 1U : 0U;
    (void)service->RemountAll();  // ★ 无条件补挂一次（把模组挂载点补到"最后注册"）
    g_imagePcxDiag.lateSharedAfterModWin =
        QueryPathNow(sharedQuery, g_imagePcxDiag.lateSharedAfterAnswer,
                     sizeof(g_imagePcxDiag.lateSharedAfterAnswer)) ? 1U : 0U;
    g_imagePcxDiag.lateModOnlyAfterModWin = QueryMountVisibilityNow(nullptr, 0) ? 1U : 0U;
}

// 批次 357：**重挂之后立刻再问一次** —— 直接回答"重挂能不能让它回来"（修法的原型）。
void ProbeMountVisibilityAfterRemount() noexcept {
    const bool hit = QueryMountVisibilityNow(g_imagePcxDiag.remountProbeAnswer,
                                             sizeof(g_imagePcxDiag.remountProbeAnswer));
    g_imagePcxDiag.remountProbeModWin = hit ? 1U : 0U;
}

// 批次 360：**修法** —— 模组挂载点的自愈（细节见头文件里那段长注释）。
// 还在 ⇒ 什么都不做；不在 ⇒ 补挂一次并**立刻复验**（复验结果进 357 那几格）。
void EnsureModMountsAlive() noexcept {
    isaac::runtime::ContentMountService* service = isaac::runtime::SessionContentMountService();
    if (service == nullptr || service->mod_count() == 0) {
        return;  // 还没走到挂载那一步（或没有模组）⇒ 不越权
    }
    ++g_imagePcxDiag.remountWatchdogChecks;
    if (QueryMountVisibilityNow(nullptr, 0)) {
        return;  // ★ 还在 ⇒ **一个字节都不改**
    }
    const isaac::runtime::Status status = service->RemountAll();
    ++g_imagePcxDiag.remountHealCount;
    g_imagePcxDiag.remountAttempted = 1U;
    g_imagePcxDiag.remountStatus = static_cast<std::uint32_t>(status.code());
    ProbeMountVisibilityAfterRemount();  // 补挂之后**立刻**再问同一句
}

} // namespace isaac::runtime::bridge
