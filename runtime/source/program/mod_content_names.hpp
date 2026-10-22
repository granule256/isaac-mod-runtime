#pragma once

// 批次 404（2026-10-07）：`Isaac.Get*ByName` 一族里**"按名字查本体快照"**那几条的**运行时追加层**
// —— 把模组在 `content/items.xml` / `content/pocketitems.xml` 里声明的自定义名字，
// 按引擎喂入顺序补进"名字 → 编号"查询。
//
// ## 为什么需要它（与批次 401 的 `GetPlayerTypeByName` 同源）
//
// `Isaac.GetItemIdByName` / `GetTrinketIdByName` / `GetCardIdByName` 三条查的都是
// `runtime/source/program/isaac_name_tables.cpp` 里那张**本体契约快照**（由
// `tools/generate_isaac_name_tables.py` 从**本体** XML 生成）⇒ 模组自加的道具/饰品/卡
// 一律查成 `-1`（或 0）。
// 真机读数（批次 402 那一批）里 `Trinity/main.lua:67` 的
// `EntityPlayer:AddCollectible type is outside uint32 range` 就是它：
// `Isaac.GetItemIdByName("Mirror of Hearts")` 返回 `-1` ⇒ `AddCollectible(-1, 5)` 抛错
// ⇒ **整条 `MC_POST_PLAYER_INIT` 回调被摘掉** ⇒ Peter 拿不到那件道具。
//
// ## ★ 三条 id 规则（批次 404 逐条取证，见 `dist/change-archive-20261007/404-mod-name-tables/README.md`）
//
// 三条**共用同一个形状**（与玩家表 401 的那条同构）：
// > **模组条目 id = 本体该类条数 + 该条目在它所属模组那个 xml 里的同类出现顺序（0 基）；
// >   跨模组按引擎喂入顺序继续累加。**
//
// 但**本体条数**与**所在文件 / 识别标签**逐族不同，全部来自引擎自己的代码：
//
// | 族 | `Isaac.Get*ByName` | 文件 | 识别标签 | 本体条数（id 基准） | 证据 |
// | --- | --- | --- | --- | --- | --- |
// | 收藏品 | `GetItemIdByName` | `content/items.xml` | `<passive>`/`<active>`/`<familiar>` | **733** | `ItemConfig::Load @0x3B50E0` 序言 `mov w8,#0x2dd`(733) + `vector<Item*>::__append(733-count)` |
// | 饰品 | `GetTrinketIdByName` | `content/items.xml` | `<trinket>` | **190** | 同函数 `mov w8,#0xbe`(190)（+0x18 那条向量 = `ItemConfig::GetTrinket @0x3C0C9C` 读的那条） |
// | 卡牌 | `GetCardIdByName` | `content/pocketitems.xml` | `<card>`/`<rune>` | **98** | `ItemConfig::LoadPocketItems @0x3BE42C` 序言 `mov w8,#0x62`(98)（+0x48 = `ItemConfig::GetCard @0x3C0D14`） |
//
// 模组条目如何拿 id（同一函数的模组分支）：
// `ItemConfig::Load` 在 `x2(=ModEntry)!=0` 时**跳过**那两条 resize，然后对每条识别到的条目
// 把"当前向量条数"写进 `Item+0x4`（收藏品/饰品各自 +0x4）后 `push_back`；
// 卡牌同理写 `Card+0x0`。⇒ **模组条目 id = 该类向量当时的条数 = 本体条数 + 追加顺序。**
// ★ 模组 xml 里的 `id="N"` 属性对**模组条目**被忽略（收藏品/饰品被 size 覆盖；
//   卡牌同样被 size 覆盖），所以 Trinity 的 `id="0".."5"` 不会覆盖本体道具。
// ★ **饰品没有独立的 `trinkets.xml` / 卡牌也没有 `cards.xml`** —— 饰品与收藏品同在
//   `items.xml`（`<trinket>`），卡牌在 `pocketitems.xml`（`<card>`/`<rune>`）。
//   作业单里写的 `trinkets.xml` / `cards.xml` **不存在**，喂它们会一条都进不去（静默）。
//
// ## 不做的那一族（如实记账）
//
// `Isaac.GetEntityTypeByName` / `GetEntityVariantByName`（`entities2.xml`）**本批不做**：
// 它的 id 规则**不同** —— `EntityConfig::Load @0x68860` 把 `id`/`variant` 用 `atoi`
// **原样读入**（不是"本体条数 + 顺序"），但模组条目在 `0x6B41C` 起有一段**只对模组生效的
// 冲突避让**（type/variant 已被占用时自增 variant，某些 type 还自增 type）⇒ 最终值取决于
// **当时整张实体表的状态与喂入顺序**，无法只靠读一份 xml 复现（错一个就**静默**拿到错 type）。
// 详细证据与结论见批次 404 存档 README 的"没做的事"。
//
// ## ★★ 追加顺序必须与引擎的喂入顺序逐字一致
//
// 运行时**自己就是喂的那个人**（`runtime/source/mod_menu_native.cpp` 的 `LoadEngineModContent`，
// 表是 `runtime_constants.hpp` 的 `kModContentFeedSpecs`：第 1 项 = `items.xml`、
// 第 2 项 = `pocketitems.xml`）。本层**不自己排序**：调用方必须在**同一条喂入循环、
// 同一个模组下标顺序**上按 `items.xml` → `pocketitems.xml` 的次序喂。顺序错了 id 就错，
// 而且是**静默错**（拿到错道具、不报错）。
//
// ## 幂等与坏文件
//
// * **幂等靠 modKey + 文件别**：同一个 `(modKey, 文件)` 只接受**第一次**调用，重复调用原样
//   返回 0、不动表。键存储是固定容量的"短串 + 文件别"表。
// * **坏 XML 不抛错**：解析器是**容错扫描**（不是严格 XML 解析），认根标签 + 识别标签；
//   根缺失 / 标签截断 ⇒ 判 `Malformed`、该模组**整份跳过**并计数，**绝不**把别的条目挤错位置。
// * ★ **每条识别到的条目都让该族的 id 计数器 +1**（无论有没有名字、无论有没有存下）——
//   与引擎"往向量里追加一格"同语义；漏推进会让后面的条目整体错位（静默错）。

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

//: 名字族（下标只用于内部数组；**与静态表 `IsaacNameKind` 的取值无关**）。
enum class ModContentNameFamily : std::uint8_t {
    Collectible = 0,  //: `items.xml` 的 `<passive>`/`<active>`/`<familiar>`
    Trinket = 1,      //: `items.xml` 的 `<trinket>`
    Card = 2,         //: `pocketitems.xml` 的 `<card>`/`<rune>`
    Count = 3,
};

//: 我们喂进追加层的"文件别"（一个文件可能喂出多个族 —— `items.xml` 同时喂收藏品与饰品）。
enum class ModContentFileKind : std::uint8_t {
    Items = 0,        //: `content/items.xml` → 收藏品 + 饰品
    PocketItems = 1,  //: `content/pocketitems.xml` → 卡牌
    Count = 2,
};

//: 各族 id 的基准 = 本体该类条数（**逐族取证**，见表头）。
//: 下标 = `ModContentNameFamily`。本体 id 逐值不变（追加只可能落在这些基准之后）。
inline constexpr std::int32_t kModContentNameIdBase[] = {
    733,  //: 收藏品：`ItemConfig::Load` 序言 `mov w8,#0x2dd`
    190,  //: 饰品：`ItemConfig::Load` 序言 `mov w8,#0xbe`
    98,   //: 卡牌：`ItemConfig::LoadPocketItems` 序言 `mov w8,#0x62`
};

//: 模组 `content/` 下的文件名（与 `kModContentFeedSpecs` 第 1/2 项逐字相同）。
inline constexpr char kModContentItemsFileName[] = "items.xml";
inline constexpr char kModContentPocketItemsFileName[] = "pocketitems.xml";

//: 一条解析结果：族 + 名字切片（**指向输入文本**，不拥有）。
struct ModContentName {
    ModContentNameFamily family;
    const char* name;   //: 可能为空（`name` 属性缺失/为空 ⇒ 仍占 id、但不进表）
    std::size_t length;
};

//: 追加层的可读诊断计数（读数 / 门禁按它判"坏在哪一层"）。
struct ModContentNameStats {
    std::uint32_t fedFiles;         //: 真正被接受（非重复）的文件喂入次数
    std::uint32_t stored;           //: 存进表的名字条数（有名字且容量够）
    std::uint32_t consumedIds;      //: 推进的 id 总数（含没存下的）
    std::uint32_t duplicateFiles;   //: 因幂等被整份忽略的重复喂入次数（**正常 >0 也无害**）
    std::uint32_t malformedFiles;   //: 解析失败（Malformed）的文件数
    std::uint32_t skippedEntries;   //: **不占 id**被跳过的条目数（目前只有"显式负 id 的卡牌"）
    std::uint32_t unnamedEntries;   //: 识别到但名字缺失/为空、**占 id 但没进表**的条数
    std::uint32_t readFailures;     //: 调用方读文件失败（解析挂载失败 / 读取失败）的次数
    std::uint32_t capacityOverflow; //: 表满而**没有存下**、但仍推进了 id 的条数（正常恒 0）
};

//: 解析一份 `items.xml` 文本：把 `<passive>`/`<active>`/`<familiar>` 归收藏品、
//: `<trinket>` 归饰品，按**出现顺序**写进 `out`（切片指向 `xml`，调用方保证其有效期）。
//: 返回解析到的条数。`*malformed` = true ⇒ 不是 `items.xml` 形状（根缺失 / 标签截断）；
//: `*skipped` = 不占 id 被跳过的条数（`items.xml` 目前恒 0）。**纯函数**（宿主门禁直接测）。
[[nodiscard]] std::uint32_t ParseModItemsXml(const char* xml, std::size_t length,
                                             ModContentName* out, std::uint32_t capacity,
                                             bool* malformed, std::uint32_t* skipped) noexcept;

//: 解析一份 `pocketitems.xml` 文本：`<card>`/`<rune>` 归卡牌（`<pilleffect>` 等忽略）。
//: ★ 卡牌的形状**多一条判据**：显式 `id` 为负的条目引擎会**跳过**（既不占 id 也不进表）
//: —— 见 `ItemConfig::LoadPocketItems @0x3BEE08` 的 `tbnz w25,#0x1f`（w25 = atoi(id)）。
[[nodiscard]] std::uint32_t ParseModPocketItemsXml(const char* xml, std::size_t length,
                                                   ModContentName* out, std::uint32_t capacity,
                                                   bool* malformed,
                                                   std::uint32_t* skipped) noexcept;

//: 解析 + 追加一步到位（宿主门禁按它测顺序 / 幂等 / 坏 XML / 各族独立推进）。
//: `modKey` = 模组目录名（幂等键，不能为空）。返回本次真正存下的条数。
[[nodiscard]] std::uint32_t IngestModContentXml(ModContentFileKind file, const char* modKey,
                                                const char* xml, std::size_t length) noexcept;

//: 按族查（**非本体** —— 本体优先由调用方先查静态表）。命中返回 id，未命中返回 `-1`。
[[nodiscard]] std::int32_t LookupModContentName(ModContentNameFamily family, const char* name,
                                                std::size_t length) noexcept;

//: 追加层的诊断计数。
[[nodiscard]] const ModContentNameStats& ModContentNameStatistics() noexcept;

//: 调用方读文件失败时记一次（解析挂载失败 / 读取失败 ⇒ 这个模组的名字进不了表）。
void NoteModContentNameReadFailure() noexcept;

//: 清空追加层与全部计数（宿主门禁 / 重载用；生产路径不调用）。
void ResetModContentNamesForTests() noexcept;

} // namespace isaac::runtime
