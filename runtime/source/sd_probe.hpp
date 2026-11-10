#pragma once

// SD 卡可写能力探针（2026-11-09）。
//
// 背景：2026-09 的结论是"游戏进程里没有挂载真 SD 卡的入口"——`Repentance.nro`
// 的导入表里没有 `MountSdCard`，而我们自己那套 libnx 的文件服务在游戏进程里连
// `sm:` 都建不出来。星露谷（SSCL）那边验证出另一条路：
//
//   1. 给游戏自己的 NPDM 的 `FsAccessFlag` 置 bit21（SdCard）；
//   2. 不自己建文件服务会话，而是**在游戏自带的 nnSdk 模块里按名字找函数**
//      （`nn::fs::MountSdCard` 等），用它们挂载 SD 卡并读写。
//
// 这个探针就是来回答"以撒这边的第 2 条能不能成立、写到 SD 卡上能不能成"的。
// 它整份代码只在 `EXL_SD_PROBE` 打开时参与编译，默认运行时里一行都不存在。

#if defined(EXL_SD_PROBE)

namespace isaac::runtime::sdprobe {

// 每帧调一次（由 `ManagerUpdateHook::Callback` 在**游戏线程**上调用）。
// 内部自带"延迟 N 帧 + 只跑一次"的闸门，稳态下只是一个原子读。
void Tick() noexcept;

} // namespace isaac::runtime::sdprobe

#endif
