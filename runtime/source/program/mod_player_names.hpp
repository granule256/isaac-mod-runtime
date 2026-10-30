#pragma once

// 批次 401（2026-10-07）：`Isaac.GetPlayerTypeByName` 的**运行时追加层** —— 把模组在
// 自己 `content/players.xml` 里声明的自定义角色名接进"名字 → id"查询。
//
// ## 为什么需要它
//
// `Isaac.GetPlayerTypeByName` 走的静态表（`runtime/source/program/isaac_name_tables.cpp`，
// 由 `tools/generate_isaac_name_tables.py` 从**本体** XML + stringtable 生成）只含本体 41 个 id
// ⇒ 模组角色（Trinity 的 Mary / Peter / Isaiah）查回来是 `-1`
// ⇒ `Trinity/main.lua:59` 起 `player:GetPlayerType() == <模组角色 id>` 全部早退
// ⇒ 角色专属逻辑**静默失效**（不报错、不崩）。
// 静态表是"本体契约快照"，**不许改**（改它等于动 PC 契约）；要加的是这一层**运行时可变的追加层**。
//
// ## id 规则（批次 399 已取证定案，本批直接采信、不重新反汇编）
//
// > **模组角色 id = 41 + 该角色在它所属模组 `players.xml` 里的 `<player>` 出现顺序（0 基）；
// >   跨模组按 ModManager 喂入顺序继续累加。**
//
// 证据链见 `docs/改动日志-20261007.md` §十七与批次 399 存档；关键两条：
// `EntityConfig::GetPlayer @0x700CC` 的 `umaddl x0,w1,#0x178,x8`（id 空间 = 向量下标）；
// `LoadPlayers @0x6DC54` 序言 `mov w8,#0x29`(41) ⇒ 本体固定 41 格（0..40），模组从 41 起。
//
// ## ★★ 追加顺序必须与引擎的喂入顺序逐字一致
//
// 运行时**自己就是喂的那个人**（`runtime/source/mod_menu_native.cpp` 的 `LoadEngineModContent`，
// 表是 `runtime_constants.hpp` 的 `kModContentFeedSpecs`，第 10 项 = `players.xml`）。
// 本层**不自己排序**：调用方必须在**同一条喂入循环、同一个模组下标顺序**上调用
// `IngestModPlayersXml`。顺序错了 id 就错，而且是**静默错**（按错角色判类型、不报错）。
//
// ## 幂等与坏文件
//
// * **幂等靠 modKey**（= 模组目录名）：同一个 key 只接受**第一次**调用，重复调用原样返回 0、
//   不动表 —— 对应"同一次启动里同名模组被喂两次（或重载）"。键的存储是固定容量的短串表。
// * **坏 XML 不抛错**：解析器是**容错扫描**（不是严格 XML 解析），只认 `<players>` 根与
//   `<player ...>` 标签；根缺失 / 标签截断 ⇒ 判 `Malformed`、跳过该模组并**计数**。
//   `name` 属性缺失/为空 ⇒ 跳过该条并计数。**绝不**因为一个坏文件把别的名字挤错位置。

#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

//: 模组角色 id 的基准：本体 41 条（id 0..40）之后从 41 起（`LoadPlayers` 序言 `#0x29`）。
inline constexpr std::int32_t kModPlayerTypeIdBase = 41;

//: 模组 `content/` 下声明角色的文件名（与 `kModContentFeedSpecs` 第 10 行逐字相同）。
inline constexpr char kModPlayersFileName[] = "players.xml";

//: 一个模组 `players.xml` 里一条 `<player>` 的 `name` 属性（**指向输入文本的切片**，不拥有）。
struct ModPlayerName {
    const char* name;
    std::size_t length;
    bool tainted;  // 非空 bSkinParent：按自己的 name 查询，不能隐式改用父角色名。
};

//: 追加层的可读诊断计数（读数 / 门禁按它判"坏在哪一层"）。
struct ModPlayerNameStats {
    std::uint32_t fedMods;          //: 真正被接受（非重复）的模组喂入次数
    std::uint32_t appended;         //: 追加进表的名字条数
    std::uint32_t duplicateMods;    //: 因幂等被整份忽略的重复喂入次数（**正常 >0 也无害**）
    std::uint32_t malformedMods;    //: 解析失败（Malformed）的模组数
    std::uint32_t skippedEntries;   //: `name` 缺失/为空被跳过的 `<player>` 条数
    std::uint32_t readFailures;     //: 调用方读文件失败（解析挂载失败 / 读取失败）的次数
    std::uint32_t capacityOverflow; //: 表满而**没有存下**、但仍然占了一个 id 的条数（正常恒 0）
};

//: 解析一个 `players.xml` 文本：把每个 `<player>` 的 `name` 属性按**出现顺序**写进 `out`
//: （最多 `capacity` 条，切片指向 `xml`，调用方保证 `xml` 在结果使用期间有效）。
//:
//: 返回解析到的条数（不含被跳过的空名条目）。判据：
//:   * `*malformed` = true ⇒ 文本不是 `players.xml` 形状（找不到 `<players>` 根 / 标签截断）；
//:   * `*skipped` = `name` 缺失或为空的 `<player>` 条数。
//: 这是一个**纯函数**（不碰全局状态），宿主门禁直接测它。
[[nodiscard]] std::uint32_t ParseModPlayersXml(const char* xml, std::size_t length,
                                               ModPlayerName* out, std::uint32_t capacity,
                                               bool* malformed, std::uint32_t* skipped) noexcept;

//: 解析 + 追加一步到位（宿主门禁按它测顺序 / 幂等 / 坏 XML 三条）。`modKey` = 模组目录名
//: （幂等键，不能为空）。返回本次真正追加的条数。
[[nodiscard]] std::uint32_t IngestModPlayersXml(const char* modKey, const char* xml,
                                                std::size_t length) noexcept;

//: 按名字及普通/堕落分类查；同名同分类取后加载者（PC 0x80BEB0 逆序扫描）。
//: ★ 调用方必须**先查静态表**（本体优先，id 0..40 逐值不变），静态表未命中才落到这里。
[[nodiscard]] std::int32_t LookupModPlayerTypeName(const char* name, std::size_t length,
                                                bool tainted = false) noexcept;

//: 追加层的诊断计数。
[[nodiscard]] const ModPlayerNameStats& ModPlayerNameStatistics() noexcept;

//: 调用方读文件失败时记一次（解析挂载失败 / 读取失败 ⇒ 这个模组的名字进不了表）。
void NoteModPlayerNameReadFailure() noexcept;

//: 清空追加层与全部计数（宿主门禁 / 重载用；生产路径不调用）。
// 正常重载清空上一轮追加索引，测试接口复用同一实现。
void ClearModPlayerNames() noexcept;
void ResetModPlayerNamesForTests() noexcept;

} // namespace isaac::runtime
