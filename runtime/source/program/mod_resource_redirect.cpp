// 包装：让 `source/mod_resource_redirect.cpp` 进模块构建。
//
// **为什么必须有这个文件**（2026-09-23 批次 077 实测）：构建的源文件收集是
// `common.mk` 的 `MODULES := $(shell find $(ROOT_SOURCE) -mindepth 1 -maxdepth 1 -type d)`
// —— **只收 `source/` 的下一级子目录**，`source/` 自己不在里面 ⇒ 直接放在
// `source/` 根下的 `.cpp` **不会被编译**（真机表现：符号未定义、链接期被"未定义符号门禁"
// 拦下 —— 批次 378 实测就是这么发现的）。
//
// 与 `program/hook_manager.cpp`、`program/image_pcx_bridge_hook.cpp` 同一形状：
// 真文件在 `source/` 根下（读起来就在同级、方便对照），子目录里放一个只有 `#include` 的包装。
#include "../mod_resource_redirect.cpp"
