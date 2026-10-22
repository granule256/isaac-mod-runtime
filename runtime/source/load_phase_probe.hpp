#pragma once

// ============================================================================
// 启动期"读模组"分段计时（批次 235，2026-09-30）
// ============================================================================
//
// **要回答的问题**：用户实测 —— 卡上放 `no-lua.on`（跳过读模组/Lua）时开场**零延迟**；
// 正常加载时**约 10 秒黑屏**（画面不动、声音继续）。⇒ 那 10 秒就在"读模组"这条路上，
// 而它整块跑在**游戏主线程的一帧里**（见 `hook_manager.cpp` 里 `LoadDefaultManifestModThroughService`
// 开头那段注释）。
//
// 但"在哪一段"必须量出来，不能猜：这条路上有六段性质完全不同的活。修法取决于哪一段占大头：
//   * 落在"跑模组脚本" ⇒ 分帧加载（每帧跑一个模组）；
//   * 落在"注册挂载点 / 喂 content" ⇒ 那段单独推迟或批量化；
//   * 落在"读 SD"本身 ⇒ 那是卡的速度，只能靠分帧把画面让出来。
//
// **口径**：只在 `DIAGNOSTIC_PROBES=1` 的包里编译（正式包零代价、零符号）。
// 宿主构建上 `RuntimePerfTick()` 恒 0 ⇒ 全是 0，门禁行为不变。
//
// **符号名**（读数工具按裸名直读，与 `g_ModLoadConfigs*` 那批同一个口径）：
//   `g_LoadPhaseMicros[8]`  各段耗时（微秒），下标见 `hook_manager.cpp` 的 `LoadPhase`
//   `g_LoadTotalMicros`     整个加载函数的总耗时（微秒）
//   `g_ModLoadMicros[16]`   每个模组"读入口脚本 + 执行它"的耗时（微秒）
//   `g_ModLoadCount`        上面那个数组里真正写了几个
//   `g_ModLoadTotal`        本次一共处理了几个模组

#if !defined(EXL_DIAGNOSTIC_PROBES)
#define EXL_DIAGNOSTIC_PROBES 0
#endif

#if EXL_DIAGNOSTIC_PROBES

#include <cstddef>
#include <cstdint>

//: `mod_load_service.cpp` 记一个模组的加载耗时（微秒）—— **按调用顺序追加**到
//: `g_ModLoadMicros[g_ModLoadCount++]`。**走函数调用**，不跨 TU 摸全局量
//: —— 那是项目里踩过的事故（跨 TU 热路径全局量走数据 GOT 槽，运行期槽是 0 ⇒ Data Abort）。
//: 定义在 `hook_manager.cpp`。
//:
//: ★ 批次 236：拆帧之后每次 `LoadAll` 只喂**一个**模组，所以这里不再按下标写、改成追加
//: （下标恒为 0 的话，那个数组永远只有第一格有值）。
extern "C" void IsaacRuntime_RecordModLoadMicros(std::uint32_t micros);

#endif  // EXL_DIAGNOSTIC_PROBES
