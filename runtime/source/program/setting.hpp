#pragma once

#include "common.hpp"

#define EXL_MODULE_NAME "exlaunch"

#define EXL_DEBUG
#define EXL_USE_FAKEHEAP

/*
#define EXL_SUPPORTS_REBOOTPAYLOAD
*/

namespace exl::setting {
    /* How large the fake .bss heap will be.
     *
     * 128 MiB（批次 180，2026-09-28：0x2000000 → 0x8000000）。这是**整个模块 malloc 的唯一来源**
     * （`EXL_USE_FAKEHEAP` ⇒ newlib 的 `fake_heap_start/end` 指向这块 .bss 数组），
     * 所以它同时是 Lua 状态的上限。真机报告 `01789202408` 里 Lua 报的
     * `LUA_ERRMEM`（"not enough memory"）就是它：EID 的 20 个语言包 × 两个版本
     * （ab+/rep）+ names/modular 一共约 10 MB 的源码，展开成 Lua 表与字符串后远超 2 MiB。
     *
     * 历史：0x40000 时 Font API 一装就满（一个 `KAGE::Graphics::Font` 是 0x20050 = 128 KiB），
     * 于是提到 2 MiB 并保留"至少 8 个 Font"的余量（`runtime/tests/test_runtime_constants.py`）；
     * 2026-09-12 按 Lua Mod 的真实需求再上一个量级到 32 MiB。
     * 该测试会同时断言"至少 8 个 Font"和"不小于 16 MiB"（只断言**下限**，抬高不撞门禁）。
     *
     * ★★ 为什么 2026-09-28 又抬（**这次不是靠猜，是靠读数**）：
     *   用户报"D6 刷出四级道具 ⇒ 跳舞模组卡一下然后人物模型消失或卡死"。
     *   取证（`dist/specialist-heap-exhaustion-20260928.md`）：
     *     * 舞装贴图要从 PNG 现转 PCX，链上**最大的一笔分配是一次性 4.62 MB 连续空间**
     *       （模组 23 张贴图里 22 张是 1288×940 RGBA，inflate 后缓冲都是 4,843,820 字节）；
     *     * 而真机历史读数里这块堆**已经顶到过墙**：`gdb-read-20260927-0100.txt` 报
     *       `arena = 32.0 MB`（整块假堆都被 malloc 领走）、**空闲只剩 2.2 MB**；
     *       `gdb-read-20260927-0005/0020/0035` 更狠 —— arena 才 19.2 MB 就**空闲 0.0 MB**。
     *       2.2 MB < 4.62 MB ⇒ 那一刻转码**算术上必然失败**；
     *     * 失败有两种表现（`PngToPcx` 是 `noexcept`，而里面多数分配会抛）：先失败那笔 4.62 MB 的
     *       ⇒ `std::bad_alloc` 逃出 `noexcept` ⇒ `std::terminate` ⇒ **卡死**；只失败最后那笔
     *       `nothrow` 的 ⇒ 转码返回失败 ⇒ 舞装贴图没装上 ⇒ **人物模型消失**。
     *       ⇒ 用户说的"模型消失**或者**卡死"正是同一条分配链的两种失败方式。
     *
     *   ⇒ 32 MiB 对一个"要现转 1288×940 贴图"的模块**不够**，所以抬到 128 MiB。
     *
     * ★ 抬多高有依据吗：**没有上游文档写的硬上限**（查过 Atmosphere 的加载器说明：
     *   只要求"把 exefs 里的各个 NSO 连续装进进程"，见 `misc/link.ld` 里那段查证记录）。
     *   这块 `.bss` 是 **NOBITS ⇒ 不占文件、只占进程内存**（实测 `subsdk9` 的 PT_LOAD[2]
     *   `filesz` 只有 0x16c90，而 `memsz` = 0x22ea000 = 34.9 MB）。
     *   ⇒ 本次同时把"进程到底还有多少内存"量出来（状态面 `[64]~[67]`）。
     *     ★ 2026-09-28 首次真机读数之后的**更正**（批次 181）：**那四格答不了"还能不能抬"**
     *     （`[64]`/`[65]` 两边几乎相等是常态，实测数字与结论见 `mod_menu_native.hpp` 里那段）；
     *     而"128 MiB 够不够"由**更直接的证据**回答了 —— 贴图桥 `实际转码 13 / 失败 0`、
     *     模块堆 arena 47.4 MB（> 旧的 32 MiB ⇒ 旧值必然装不下，这正是 D6 那个 bug 的根因）。
     *     详见 `docs/改动日志-20260928.md` §181。
     *
     * ★★★ 2026-10-08（批次 416）**试过抬到 256 MiB —— 真机上装不上，已回退**：
     *   判据同样是真机读数：用户报"模组 `whatsmydps` 每帧报 `Font could not allocate its native object`"，
     *   排查两批（414 固定块池 / 415 改走 Lua 分配器）之后拿到的是同一条：
     *     * 415 那次真机：**本模块堆 `空闲 5.2 MB / 已用 122.8 MB`**（总量 128 MiB）
     *       ⇒ **128 KiB 的请求要不到是必然** —— 既不是碎片、也不是 GC；
     *     * 415 顺便证明 GC 那一环已经修对（`g_FontStorageLive = 0`：Font 的块用完就归还；
     *       414 那版是 288 个常驻不还）。
     *   ⇒ 于是按"抬堆"这条老路试 **256 MiB**（`0x10000000`）：构建、门禁、上卡都通过，
     *     **但游戏起不来** —— 系统弹"由于发生错误，软件已关闭"，
     *     崩溃报告 `01791470579_010021c000b6a000.log`：`Type = User Break`、
     *     `Address = nnSdk + 0x3cd354`、`Break Size = 4`（加载期 `svcBreak`）。
     *   ★ **结论**：**一次 +128 MiB 的 `.bss` 跨度太大，这条路要小步走**（历史上是
     *     0x40000 → 2 MiB → 32 MiB → 128 MiB 的渐进）。**本批的值已回退到 128 MiB**，
     *     卡上也已回滚到 415（`subsdk9` 801972 / `40f28327…`）⇒ **当前状态是可用的**。
     *   ★ **下次要做的**：① 先读游戏的 **NPDM**（`tools/parse_npdm.py`）拿到进程内存预算，
     *     别再靠试；② 若还有余量就**小步抬**（例如先 `0xA000000` = 160 MiB）；
     *     ③ 另外确认 415 留下的 `空闲 5.2 MB` 是被什么吃掉的（EID 的语言包？转码缓冲？），
     *     因为"堆够大"与"谁在吃堆"是两件事。 */
    /* ★ 2026-10-09更正：上文415“live=0证明GC已修”和“128KiB分配失败必然不是GC/碎片”
     * 不能成立。旧量具live符号名错误，417原始字节根本不覆盖live；直接lua_Alloc不增加GCdebt。
     * 当前修复用完整userdata承载字体存储，真实Lua压力测试才证明自动GC可回收。
     * 缓存空槽跳过预算、转码重复复制也已修复；堆继续128MiB，不凭旧推断继续抬堆。 */
    // 2026-10-13集成更正：保留生产424/448的152MiB，避免旧静态基线退回128MiB。
    // 上述GC/流式转码修复仍成立；449按最终NSO映射补齐原生CPU预留，不再漏算模块占用。
    constexpr size_t HeapSize = 0x9800000;

    /* How large the JIT area will be for hooks. */
    constexpr size_t JitSize = 0x1000;

    /* How large the area will be inline hook pool. */
    constexpr size_t InlinePoolSize = 0x1000;

    /* How large the formatting buffer should be for logging. The buffer will be on the stack. */
    constexpr size_t LogBufferSize = 512;

    /* Sanity checks. */
    static_assert(ALIGN_UP(JitSize, PAGE_SIZE) == JitSize, "");
    static_assert(ALIGN_UP(InlinePoolSize, PAGE_SIZE) == InlinePoolSize, "");
}
