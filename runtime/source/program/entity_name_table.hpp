#pragma once

// 由 `tools/generate_entity_name_table.py` 从 `tools/entity_name_source.txt` 生成 —— **不要手改**。
// 表本身是"本体 `entities2.xml` 的静态快照"，来源与拼法见生成器的文档头。
//
// 用途：`Isaac.GetEntityTypeByName(name)` / `GetEntityVariantByName(name)`
// （PC 契约 `tools/pc_contract_docs/Isaac.md:218/235`；消费方 MCM 的
// `scripts/modconfig.lua:260/261`）。

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

//: 一行 = 一个实体名。`nameOffset` 是它在名字块（`'\0'` 分隔）里的字节下标。
//:
//: `type` 用 `std::uint16_t`：本体的实体编号远小于 65535（最大约 `0x3DD`）。
//: `variant` 用 **`std::int16_t`** 而不是无符号 —— `GetEntityVariantByName` 查不到时要返回
//: `-1`（PC 契约 `Isaac.md:235`），用无符号就得额外走一条特例分支。
struct EntityNameEntry {
    std::uint32_t nameOffset;
    std::uint16_t type;
    std::int16_t variant;
};

//: 名字块（`'\0'` 分隔、按名字升序，与 `EntityNameEntries()` 一一对应）。
[[nodiscard]] const char* EntityNameBlob() noexcept;

//: 名字条目表（**按名字升序**，查找用二分）。`count` 通过出参给出。
[[nodiscard]] const EntityNameEntry* EntityNameEntries(std::size_t* count) noexcept;

} // namespace isaac::runtime
