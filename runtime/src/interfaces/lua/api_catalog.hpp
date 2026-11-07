#pragma once

#include "domain/runtime/status.hpp"
#include "interfaces/lua/api_descriptor.hpp"

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

// Single source of truth for "which Lua APIs does this Runtime expose". The
// legacy runtime registered APIs inline; the catalog makes the list enumerable,
// comparable against the implementation and safe to generate docs from.
class ApiCatalog {
public:
    // 目录条数的结构性上限（2026-09-19 改）。
    //
    // 这里原来是一个手写的容量：128 → 160 → 192 → 224 → 256，五次都是"快撞线才抬"。
    // 2026-09-19 实测：目录已 248 条，只剩 8 个位置 —— 而越限的后果是 `Validate()` 把
    // 整张目录判为无效（真机上等于所有 API 全不挂）。一个"每加几条 API 就得有人来改"的
    // 数字，正是"以后陆续实现 API 会被架构束缚"的典型，而且它每次都在同一处栽跟头。
    //
    // 真正限制条数的是 id 的编码（`MakeId(域, ownerGroup, 序号)`）：域与 ownerGroup 各 8 位，
    // 序号 16 位 ⇒ 每个域最多 65535 条，而 `MakeId` 的 `std::uint16_t 序号` 形参由编译器
    // 保证字面量放得下。所以把上限钉在这个编码极限上 —— 它再也追不上人：
    // 要撞到它，得先撞到 16 位序号本身（那时编译器先报错）。
    //
    // 目录本身是"指向不可变表的视图"（`entries_` + `count_`），
    // 提高这个常量不花内存、不花代码（表的大小由 `kDefaultApis[]` 自己决定）。
    static constexpr std::size_t kCapacity = 0xFFFF;


    // The catalog is a view over an immutable table; building one never
    // allocates.
    constexpr ApiCatalog(const LuaApiDescriptor* entries, std::size_t count) noexcept
        : entries_(entries), count_(count) {}

    [[nodiscard]] static const ApiCatalog& Default() noexcept;

    [[nodiscard]] std::size_t Count() const noexcept { return count_; }
    [[nodiscard]] const LuaApiDescriptor* At(std::size_t index) const noexcept;
    [[nodiscard]] const LuaApiDescriptor* Find(std::uint32_t id) const noexcept;
    [[nodiscard]] const LuaApiDescriptor* Find(const char* owner, const char* name) const noexcept;

    // Rejects duplicate ids, duplicate owner+name pairs, empty names, overflow
    // of the capacity and ids whose domain byte does not match the domain.
    [[nodiscard]] Status Validate() const noexcept;

private:
    const LuaApiDescriptor* entries_{nullptr};
    std::size_t count_{0};
};

} // namespace isaac::runtime
