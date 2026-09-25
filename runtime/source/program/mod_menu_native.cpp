// 包装：让 `source/mod_menu_native.cpp` 进模块构建。
//
// **为什么必须有这个文件**（2026-09-23 批次 077 实测）：构建的源文件收集是
// `common.mk` 的 `MODULES := $(shell find $(ROOT_SOURCE) -mindepth 1 -maxdepth 1 -type d)`
// —— **只收 `source/` 的下一级子目录**，`source/` 自己不在里面 ⇒
// 顶层 `source/*.cpp` 不会进 `CPPFILES`，**既不会编译、也不报错**，
// 直到链接时才以"未定义符号"的形式炸出来（这一次就是：
// `未定义符号门禁失败：… EntryRelayMenuGameRenderCallback … ModMenuNativeInstall`）。
// 所以每个要进模块构建的顶层源文件都要在这里放一行 `#include`。
//
// 这条纪律项目里早就记过（`docs/交接文档-20260921-夜-…` 第四节第 5 条：
// "新源文件要补 `source/program/` 包装"），但**当时只是文档里的一句话** ⇒ 又踩了一次。
// ⇒ 现在由门禁 `runtime/tests/test_source_program_wrappers.py` 钉住：
// 顶层每个 `source/*.cpp` 要么有包装、要么在构建脚本里被显式收进去、要么在"不参与模块构建"
// 名单里写明理由 —— **不许再出现"加了文件、其实没编进去"这种静默形态**。
#include "../mod_menu_native.cpp"
