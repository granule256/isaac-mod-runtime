#pragma once

#include <cstddef>
#include <cstdint>

// ============================================================================
// PC 的资源层重定向 —— Switch 侧的落点与实现
// ============================================================================
//
// **它替代的是什么**：以前我们给每个模组目录调 `IContentManager::AddMountPoint`
// （六个叶子：`resources` / `resources/gfx` / `content` / `content/gfx` /
// `resources-dlc3` / `resources-dlc3/gfx`）。那是**我们自造的机制**，不是引擎的：
// 全镜像 `AddMountPoint` 只有 5 处调用（`RebuildContentMountPoints` ×2、
// `PerformLanguageSwitch` ×2、`IContentManager::Initialize` ×1），**没有一处与模组有关**。
// 它的三条偏差：
//   ① 优先级相反 —— 挂载点是**倒序**搜索（后注册者优先），PC 是**清单顺序**（第一命中赢）；
//   ② `content` 叶子的键空间就是**本体配置的裸名** ⇒ 本体请求的 `music.xml` 会被模组那份抢走
//      （模组那份没有 `id` ⇒ 音乐表 119 条全空 ⇒ 371 整局没有音乐、渲染族回调闸门不开）；
//   ③ 时机 —— 它必须在引擎第一次读之前挂上，于是我们又引入了"Game::Init 窗口里挂载"，
//      以及"引擎重建挂载表之后补挂"这一整套本不该存在的东西。
//
// **PC 的机制**（`isaac-ng.exe`，逐条反汇编取证见
// `docs/分析-模组挂载机制与371没音乐定案-20261005.md` §2）：`ModManager::GetModResourcePath
// @0x870460` —— 在**每次读资源之前**问一遍："哪个模组有这个文件？"
//   * 按模组清单顺序取**第一个启用**的模组（`0x8705B2 cmp byte [eax+0xfd],0`）；
//   * 先试 `<模组目录>/resources-dlc3/<名>`（`0x87066F` 的 `"-dlc3/"`），
//     再试 `<模组目录>/resources/<名>`（`0x870819`，`ModEntry+0x30`）；
//   * 命中即返回，都没有 ⇒ **原名回传**（`0x870AC5`）。
// PC 的**文件层完全不认识模组**：`FileSystem::Open 0x963120` / 挂载点解析 `0x964AA0` 里搜
// ModManager 一个命中都没有；`ListMods 0x870B40` 也只是把 `/resources/`、`/content/`
// 存进 `ModEntry+0x30`/`+0x48`，**不挂载**。
//
// **为什么落在 `IContentManager::GetMountedFilePath`（`0x4C2340`）**：Switch 版引擎把
// "资源名 → 文件路径"这一步**全部**收口在这一个函数上 —— 它的 8 个调用点正好是全部文件入口：
// `FileManager::Exists`（`0x4C3154`）、`FileManager::OpenRead`（`0x4C31C4`）、
// `FileManager::LoadArchiveFile`（`0x4C2B30`）、`File::Exists`（`0x4CCD04`）、
// `ImageBase::Load`（`0x4D002C`）、`ImageManager::LoadImage`（`0x4D2074`）、
// `VideoPlayer` ctor/Load（`0x520E18`/`0x520EB0`）。
// ⇒ 在这里实现 PC 的那条规则，等于把 PC 分散在 94 个加载点上的重定向**一次补全**
//   （贴图、anm2、字体、配置 XML、视频全在内），而且返回值的形状与"模组目录被挂载"时
//   **逐字节同形**（都是 `original()` 自己解析出来的 `rom:/isaac_mods/...` 路径）。
//
// **不新增钩子**：这个函数**本来就被我们钩着**（`HookId::ContentGetMountedFilePath`，
// 中继回调 `EntryRelayContentGetMountedFilePathCallback`，见 `image_pcx_bridge_hook.cpp`）。
// 本批只是在那条中继里**先问一次**本模块的规则。
//
// **已知偏离（如实记，不粉饰）**：
//   ① 模组清单的"启用"取自我们的清单/自动发现（`ResolvedManifestModBatch` 里只有启用的模组），
//      不是引擎自己那份（Switch 版的引擎侧模组列表本来就是死代码 —— `ListMods` 会读
//      `ModEntry+0x50`/`+0x48` 那两格，而它从来没被 EngineModLoader 填过）。
//   ② 本批**不做命中缓存**：PC 有（`0x870A15` 把命中写进缓存），代价是"未命中的请求要问完
//      所有模组"（PC 也一样）。先按规则正确性交付，缓存等真机读数给出调用量之后再谈。
//   ③ 形如 `rom:/...` 或 `isaac_mods/...` 的请求**直接跳过**（它们已经是解析过的形态，
//      不可能是"模组资源名"）。PC 没有这个前缀概念 ⇒ 这一步只在"我们自己喂进去的路径"上生效，
//      不会改变任何 PC 会走到的判定结果。

namespace isaac::runtime::bridge {

// 与 `kModManifestCapacity`（32）一致；本 TU 刻意**不包含应用层头文件**（耦合最小化）。
inline constexpr std::size_t kModResourceRedirectCapacity = 256;
// `isaac_mods/mods/`（17）+ 目录名容量（256）+ 结尾 `\0`。
inline constexpr std::size_t kModResourceRedirectRootCapacity = 288;
inline constexpr std::size_t kModResourceRedirectQueryCapacity = 192;
inline constexpr std::size_t kModResourceRedirectAnswerCapacity = 224;
inline constexpr std::uint32_t kModResourceRedirectNoMod = 0xFFFFFFFFu;

// 常驻状态面（读数工具按符号名 `g_ModResourceRedirectState` 读；字段顺序是契约）。
struct ModResourceRedirectState {
    std::uint32_t published;        // 1 = 模组清单已发布（发布之前重定向一律不做）
    std::uint32_t modCount;         // 已发布的模组个数
    std::uint32_t calls;            // 进入重定向的次数
    std::uint32_t hits;             // 其中命中模组的次数
    std::uint32_t dlc3Hits;         // 命中来自 `resources-dlc3/` 的次数
    std::uint32_t plainHits;        // 命中来自 `resources/` 的次数
    std::uint32_t lastHitMod;       // 最后一次命中来自第几个模组（`kModResourceRedirectNoMod` = 无）
    std::uint32_t skippedResolved;  // 因"已是解析过的形态"跳过的次数
    std::uint32_t skippedTooLong;   // 资源名超过诊断/候选容量的次数（跳过硬编码上限，见实现）
    std::uint32_t publishCount;     // 清单被发布过几次（每次发布都会换一代）
    char lastQuery[kModResourceRedirectQueryCapacity];
    char lastAnswer[kModResourceRedirectAnswerCapacity];
};
extern ModResourceRedirectState g_ModResourceRedirectState;

// 发布/清空"可重定向的模组清单"。**纯内存写、不调引擎**，所以可以在
// `Game::Init` 入口那一刀里安全地做（371 的拆因实验证明：那个窗口里"读清单"干净，
// 危害只在"调引擎的挂载接口"）。
//
// `modRoots` = 每个模组的**应用根相对**根目录（例：`isaac_mods/mods/EID`；
// 带 `rom:/` 前缀或结尾 `/` 都会被规范化掉）。顺序 = 清单顺序 = PC 的优先级顺序。
// `count` 超过容量时返回false，保留上一份完整名单；不截断。
bool PublishModResourceRedirectList(const char* const* modRoots, std::size_t count) noexcept;
void ClearModResourceRedirectList() noexcept;
[[nodiscard]] bool ModResourceRedirectListPublished() noexcept;

// 探测用的原函数签名：`IContentManager::GetMountedFilePath(char const*)`。
// 由调用方（贴图桥中继）传入，本模块**不自己解析绑定** —— 那边已经解析好了，
// 而且必须是**原函数**（绕过钩子）才不会递归。
using ProbeMountedFilePathFn = char* (*)(void*, const char*);
// 2026-10-14更正：原生FileMap只比32位hash，非空回答仍可能是别的文件。
// 完整候选路径不符时，必须用原分配器归还回答，再继续查；正常命中仍转移所有权。
using ReleaseMountedFilePathFn = void (*)(void*);

// PC 规则的一次查询：
//   命中 ⇒ 返回**引擎分配的**已解析路径（调用方按引擎约定用 `_ZdaPv` 归还），
//   未命中 / 清单未发布 / 参数不全 ⇒ 返回 `nullptr`（调用方照旧问引擎原函数）。
// `contentManager` = `g_ContentManager`（引擎自己的单例，中继的 `self` 就是它）。
char* TryRedirectModResource(const char* requestedPath, void* contentManager,
                             ProbeMountedFilePathFn probe,
                             ReleaseMountedFilePathFn release) noexcept;

}  // namespace isaac::runtime::bridge
