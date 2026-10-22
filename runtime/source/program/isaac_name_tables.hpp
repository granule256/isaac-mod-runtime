#pragma once

// 由 `tools/generate_isaac_name_tables.py` 从 `tools/isaac_name_source/*.txt` 生成 —— **不要手改**。
// 表是「本体 XML + stringtable 的静态快照」，来源、拼法与已知偏离见生成器的文档头。
//
// 用途（PC 契约逐条见 `tools/pc_contract_docs/Isaac.md`）：
//   * `Isaac.GetItemIdByName`（tools/pc_contract_docs/Isaac.md:274）
//   * `Isaac.GetCardIdByName`（tools/pc_contract_docs/Isaac.md:148）
//   * `Isaac.GetPillEffectByName`（tools/pc_contract_docs/Isaac.md）
//   * `Isaac.GetPlayerTypeByName`（tools/pc_contract_docs/Isaac.md）
//   * `Isaac.GetChallengeIdByName`（tools/pc_contract_docs/Isaac.md:176）
//   * `Isaac.GetTrinketIdByName`（tools/pc_contract_docs/Isaac.md:457）
//
// ★ 为什么不用「遍历引擎的 ItemConfig 比名字」：Switch 叠加层里 `rp_patch/resources/items.xml`
//   的 960 条名字里 911 条是本地化键（`#THE_SAD_ONION_NAME`）⇒ 运行时 `ItemConfig_Item.Name`
//   读到的是**键**，拿 `Brimstone` 这种原文去比永远不中。

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

//: 名字表的选择器（下标就是 `kIsaacNameTables` 的位置，**只能在末尾追加**）。
enum class IsaacNameKind : std::uint8_t {
    Collectible = 0,
    Card = 1,
    PillEffect = 2,
    PlayerType = 3,
    Challenge = 4,
    Trinket = 5,
};

//: 一行 = 一个名字。`nameOffset` 是它在名字块（`'\0'` 分隔）里的字节下标。
//: `id` 用**有符号** —— 查不到时要返回 `-1`（PC 契约明文）。
//: `alternateId` 目前只服务 `Isaac.GetPlayerTypeByName(name, Tainted)`：
//: `players.xml` 里 id 21..40 是**堕落角色**、名字与本体（0..20）逐字重复 ⇒
//: 同一个名字存两格（本体 / 堕落）；其余表恒为 `-1`。
struct IsaacNameEntry {
    std::uint32_t nameOffset;
    std::int32_t id;
    std::int32_t alternateId;
};

//: 一张表 = 名字块 + 条目表 + 条数。
struct IsaacNameTable {
    const char* blob;
    const IsaacNameEntry* entries;
    std::size_t count;
};

//: 全部名字表（下标 = `IsaacNameKind` 的值）。`count` 通过出参给出。
[[nodiscard]] const IsaacNameTable* IsaacNameTables(std::size_t* count) noexcept;

//: 在 `kind` 那张表里按名字查编号（**逐字节比较**，与引擎/契约同一口径）。
//: `alternate` = true 时取 `alternateId`（目前只有角色表的堕落角色会用到）。
//: 命中返回编号，**未命中返回 `-1`**（PC 契约：这几条 API 找不到都是 `-1`，不是 `nil`）。
[[nodiscard]] std::int32_t LookupIsaacName(IsaacNameKind kind, const char* name,
                                           std::size_t length,
                                           bool alternate = false) noexcept;

} // namespace isaac::runtime
