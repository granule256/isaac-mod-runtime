#pragma once

#include <cstddef>
#include <cstring>

//: PC（Windows）的**路径分隔符语义**在 Switch 上的落点 —— 平台层，不是某个模组的补丁。
//:
//: ## 为什么要这一层
//:
//: Windows 的文件 API 把 `\` 与 `/` 当**同一个**分隔符（`C:\a/b` 合法）；POSIX 只认 `/`，
//: 而 `\` 在 POSIX 里是个**普通字符**（合法文件名的字节）。PC 上的模组是按 Windows 语义写的，
//: 于是同一份模组在 PC 能跑、在 Switch 上路径解析不到。
//:
//: 实证（2026-10-08，Trinity）：
//:   * 模组的 anm2 一律写 `Spritesheet Path="costumes_peter\character_009b_lazarus2hair.png"`；
//:   * **同目录里本体**的 anm2 一律写 `/`（`costumes/character_009b_lazarus2hair.png`）；
//:   * Switch 侧 `IContentManager::GetMountedFilePath` 拿带 `\` 的串去查挂载表 ⇒ 查不到
//:     ⇒ 那张精灵表解析不到 ⇒ 该层画不出来。真机现象：选 Trinity 的 Peter 进局，
//:     角色只剩一对眼睛（头/身两层都空）。
//:
//: ⇒ **修法是恢复平台语义**（入口把 `\` 归一化成 `/`，与 Windows 同形），**不是改模组文件**：
//: PC 上那份 mod 本来就不需要改。归一化一次、扫描一遍，之后下游（引擎原函数、我们的资源层
//: 重定向、`.pcx` 合成）看到的都是 POSIX 形状。
//:
//: ## 放在哪里用（有讲究）
//:
//: **只在"路径只用于查表、返回的是一条新路径"的入口用**（当前是
//: `IContentManager::GetMountedFilePath` 的中继）。理由：归一化的结果是一块**栈缓冲**——
//: 那个入口把入参当过即弃的键（返回的是引擎另分配的路径），栈缓冲在这一步之后不再被引用；
//: 而 `ImageManager::LoadImage` **可能把路径字符串存进贴图对象**里，那里传栈缓冲会变野指针。
//: 换句话说：**归一化放在"最靠近文件系统、且入参是临时键"的那一层。**
namespace isaac::runtime::paths {

//: 路径里有没有 Windows 分隔符（`\`）。空指针 ⇒ false。
[[nodiscard]] inline bool HasWindowsSeparator(const char* path) noexcept {
    return path != nullptr && std::strchr(path, '\\') != nullptr;
}

//: 把 `path` 里的 `\` 全部换成 `/` 写进 `out`（容量 `capacity`，含结尾 0）。
//: 返回写进去的字节数（不含结尾 0）；**装不下就返回 0 且一个字节都不写**
//: （宁可不改，也不给出半条路径 —— 半条路径比原样更坏，它会静默解析到别的文件）。
//: ★ 先量长度再写：宿主门禁第一条抓到的就是"边走边写"版本（返回 0 但缓冲已被改掉一半）。
[[nodiscard]] inline std::size_t NormalizeSeparatorsInto(char* out, std::size_t capacity,
                                                        const char* path) noexcept {
    if (out == nullptr || capacity == 0 || path == nullptr) {
        return 0;
    }
    const std::size_t length = std::strlen(path);
    if (length + 1 > capacity) {
        return 0;
    }
    for (std::size_t index = 0; index < length; ++index) {
        out[index] = (path[index] == '\\') ? '/' : path[index];
    }
    out[length] = '\0';
    return length;
}

//: 归一化用的缓冲长度（模组的 anm2 路径是相对路径、很短；4096 与桥里那条 `.png` 缓冲同量级）。
inline constexpr std::size_t kSeparatorQueryCapacity = 4096;

}  // namespace isaac::runtime::paths
