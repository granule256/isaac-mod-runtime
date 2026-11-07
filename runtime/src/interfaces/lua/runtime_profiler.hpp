#pragma once

// ============================================================================
// Lua 采样剖析器
// ============================================================================
//
// **为什么需要它**：088 之后我们把"运行时的家底"量准了 —— 物品旁边 EID 那条渲染回调
// 1050 µs/帧里，引擎画图约 80 µs、**我们全部接口的搬运约 147 µs**，剩下 **约 824 µs（79%）
// 在 EID 自己的 Lua 里**。可"在它自己的 Lua 里"就再也分不动了：按 API 分只能看到它调了我们
// 什么，看不到它自己算在哪。于是只能靠猜 —— 而 088 正好是一次猜错（估成 750 µs，实测 31 µs）。
//
// **做法**：用 Lua 自己的计数钩子（`lua_sethook` + `LUA_MASKCOUNT`）：每执行 N 条指令触发一次，
// 钩子里问"当前正在执行哪个函数"（`lua_getinfo("nSl")` 给出函数名 / 短文件名 / 行号），
// 落进固定张数的桶里。**这就是采样剖析器**：哪个函数拿到最多采样点，它就在吃时间。
//
// **代价**：钩子每 N 条指令跑一次，每次约 1 µs（`lua_getinfo` + 拷名字）。按 Switch 上 Lua
// 大致每秒两千万条指令估算，N = 4000 时约 5,000 次采样/秒、开销 **0.6%**；
// 而 Lua 只在托管回调里跑（每秒几毫秒）⇒ 折算到帧上可以忽略。
//
// **它能看见什么、看不见什么（很重要）**：
//   * 计数钩子只在**执行 Lua 指令**时触发 ⇒ 采样点**只落在 Lua 函数**上；
//   * 我们那些 C 侧的接口处理器（`GetData`/`FindInRadius`…）**不会被单独采样到**，
//     它们的时间会被算到"调用它的那个 Lua 函数"头上 —— 所以"某个 Lua 函数很贵"
//     这句话里**可能包含它调用的 C 接口的代价**。要看接口本身的代价，用 087/088 那张
//     "最贵的 API"表（两者互补）。
//
// **纪律**：钩子里**不许分配、不许调会分配/抛错的 Lua API**（`lua_getinfo` 只往调用方给的
// `lua_Debug` 里拷，安全）；桶满了只加"溢出"计数，**不覆盖已有样本**。

#include <cstddef>
#include <cstdint>

extern "C" {
struct lua_State;
struct lua_Debug;
}

namespace isaac::runtime {

// 有界字符串比较（两边都以结尾零收尾；被截断到字段宽度的名字视为同一个函数）。
[[nodiscard]] inline bool ProfileTextEquals(const char* left, const char* right) noexcept {
    if (left == nullptr || right == nullptr) {
        return false;
    }
    std::size_t index = 0;
    while (left[index] != '\0' && right[index] != '\0') {
        if (left[index] != right[index]) {
            return false;
        }
        ++index;
    }
    return left[index] == right[index];
}

// 有界拷贝，保留结尾（路径太长时留文件名而不是开头 —— 开头都是
// `rom:/isaac_mods/mods/` 这一样的前缀，从开头截会让不同文件撞成同一个名字）。
inline void ProfileCopyTextTail(char* destination, std::size_t size, const char* source) noexcept {
    if (destination == nullptr || size == 0) {
        return;
    }
    std::size_t length = 0;
    while (source != nullptr && source[length] != '\0') {
        ++length;
    }
    const std::size_t keep = (length + 1 < size) ? length : (size - 1);
    const std::size_t start = length - keep;
    for (std::size_t index = 0; index < keep; ++index) {
        destination[index] = source[start + index];
    }
    destination[keep] = '\0';
}

// 有界拷贝（保证以结尾零收尾）。
inline void ProfileCopyText(char* destination, std::size_t size, const char* source) noexcept {
    if (destination == nullptr || size == 0) {
        return;
    }
    std::size_t index = 0;
    while (source != nullptr && source[index] != '\0' && index + 1 < size) {
        destination[index] = source[index];
        ++index;
    }
    destination[index] = '\0';
}

// 一条采样桶。按 `(source, name)` 归并（无名函数用 `<匿名>` 合成一个名字），
// `line` 只记首次命中的行号，作为"代表性行号"展示。`hits == 0` 表示空桶。
struct RuntimePerfProfileBucket {
    std::uint32_t hits;    // 落在这一条上的采样点数
    std::int32_t line;     // 首次命中时的行号
    char name[24];         // 函数名（Lua 给的名字；无名时是合成的）
    char source[48];       // `short_src`（通常形如 `@rom:/isaac_mods/mods/.../main.lua`）
};                         // 80 字节

// 桶数。读数工具按 `个数 × 每项字节` 整块读，改这里要同步工具的常量（门禁核对）。
//
// 2026-09-20 第一次真机就撞上的教训：128 个桶会被"只命中一次"的条目瞬间占满
// （实测 128/128 占满、5,136 次采样溢出，热函数反而没位置）。所以除了把桶数提到 192，
// 还加了"淘汰命中最少的桶"的策略：新键进来时若没有空桶，就顶掉命中最少的那个
// （只在它的命中数 `<= kProfileEvictionMaximumHits` 时才顶，避免把已经热起来的函数挤掉）。
inline constexpr std::size_t kRuntimePerfProfileBucketCount = 192;

// 桶满后每次"顶掉最冷槽"都算一次 `overflow`（读数里会报）——它不再是"丢掉的样本"：
// 计数被继承了，所以 `各桶之和 == 总采样数` 始终成立。
// 保留这个常量是为了让"淘汰阈值"这个概念在读数与门禁里有名字（当前策略不再按阈值拒绝）。
inline constexpr std::uint32_t kProfileEvictionMaximumHits = 4;
inline constexpr std::size_t kRuntimePerfProfileBucketBytes = sizeof(RuntimePerfProfileBucket);

// 每多少条 Lua 指令采样一次。越小越准、开销越大：4000 大约 0.6%，
// 1000 大约 2.5%（要更细地看某一段时再临时调小）。
inline constexpr int kRuntimePerfProfileInstructionStep = 4000;

// 往桶里记一次采样（纯函数，设备侧与宿主门禁共用）。
//
// 行为（门禁逐条钉住）：① 同 `(source, name)` 累加；② `name` 为空时用 `<匿名>`；
// ③ 桶满时只加 `overflow`、不覆盖已有样本；④ `line` 只记首次值；
// ⑤ 返回是否落进了某个桶。
[[nodiscard]] inline bool RecordRuntimePerfProfileSample(
    RuntimePerfProfileBucket* buckets, std::size_t capacity,
    const char* source, const char* name, std::int32_t line,
    std::uint64_t* overflow) noexcept {
    if (buckets == nullptr || capacity == 0) {
        return false;
    }
    const char* effectiveName = (name != nullptr && name[0] != '\0') ? name : "<匿名>";
    const char* effectiveSource = (source != nullptr) ? source : "";
    RuntimePerfProfileBucket* spare = nullptr;
    for (std::size_t index = 0; index < capacity; ++index) {
        RuntimePerfProfileBucket& bucket = buckets[index];
        if (bucket.hits == 0) {
            if (spare == nullptr) {
                spare = &bucket;
            }
            continue;
        }
        if (ProfileTextEquals(bucket.name, effectiveName) &&
            ProfileTextEquals(bucket.source, effectiveSource)) {
            bucket.hits += 1;
            return true;
        }
    }
    if (spare == nullptr) {
        // 没有空桶：**Space-Saving** —— 顶掉命中最少的那个槽，并**继承它的计数 +1**。
        //
        // 2026-09-20 第二次真机撞的坑：第一版是"顶掉冷条目、新键从 1 开始"，
        // 结果被顶掉的那些计数**直接丢了** —— 实测 6,347 次采样里绝大多数这样蒸发，
        // 表里只剩一堆"1 次"的条目，"谁最热"照样答不出来。
        // 继承计数之后：**各桶之和 == 总采样数**（账永远对得上，百分比才可信），
        // 而且真热点一旦热起来就不会被顶掉（它自己会把计数滚上去）。
        // 代价是"被顶进来的条目计数偏高"（经典 Space-Saving 的已知偏差），
        // 所以读数里同时给出 `overflow`（被顶掉多少次）供判断。
        RuntimePerfProfileBucket* coldest = nullptr;
        for (std::size_t index = 0; index < capacity; ++index) {
            RuntimePerfProfileBucket& bucket = buckets[index];
            if (coldest == nullptr || bucket.hits < coldest->hits) {
                coldest = &bucket;
            }
        }
        if (coldest == nullptr) {
            if (overflow != nullptr) {
                *overflow += 1;
            }
            return false;
        }
        const std::uint32_t inherited = coldest->hits;
        if (overflow != nullptr) {
            *overflow += 1;
        }
        ProfileCopyText(coldest->name, sizeof(coldest->name), effectiveName);
        ProfileCopyTextTail(coldest->source, sizeof(coldest->source), effectiveSource);
        coldest->line = line;
        coldest->hits = inherited + 1;
        return true;
    }
    ProfileCopyText(spare->name, sizeof(spare->name), effectiveName);
    ProfileCopyTextTail(spare->source, sizeof(spare->source), effectiveSource);
    spare->line = line;
    spare->hits = 1;
    return true;
}

} // namespace isaac::runtime
