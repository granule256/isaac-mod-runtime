// `Isaac.GetPlayerTypeByName` 的运行时追加层 —— 实现。
// 语义、id 规则、顺序约束、幂等与坏文件的处置**全部**写在同名 `.hpp` 的文件头，这里只写实现细节。
//
// 为什么不用 `std::map` / 动态分配：本模块 `-nostartfiles`，函数里带动态初始化的 `static`
//   会在 `__cxa_guard_*` 上自旋（黑屏有声不崩，见门禁 `test_no_static_guard_init.py`）。
//   这里一切状态都是**文件作用域的 POD**（零初始化或常量初始化 ⇒ 无静态守卫）。
// 为什么不用 `<string>` / `strlen`：追加层只在启动喂入时写几十条，线性扫足够；
//   存储用"名字池 + 定长条目"（与 `isaac_name_tables` 的 blob+entries 同一形状），
//   于是它**不拥有堆**，也就不可能因为分配失败而半途丢掉一条名字（那会让后面的 id 整体错位）。

#include "program/mod_player_names.hpp"

#include <cstring>

namespace isaac::runtime {
namespace {

// 名字池 / 条目表 / 幂等键表的容量。都取到"远超任何真实模组"的量：
// 取小了的后果是静默的（后面的名字进不了表），所以宁可多留。
constexpr std::uint32_t kMaxNameBytes = 8192;
constexpr std::uint32_t kMaxEntries = 512;
constexpr std::uint32_t kMaxModKeys = 64;         // = 引擎模组上限 32 的两倍
constexpr std::size_t kMaxModKeyLength = 96;
constexpr std::uint32_t kMaxPlayersPerMod = 256;  // 一个模组最多解析这么多条

struct Entry {
    std::uint32_t nameOffset;  // 在名字池里的字节下标
    std::int32_t id;
    bool tainted;
};

// 全部状态（文件作用域 POD）：零初始化，或带常量初始化 ⇒ 不会有 `__cxa_guard_*`。
char g_NamePool[kMaxNameBytes] = {};
std::uint32_t g_NameUsed = 0;
Entry g_Entries[kMaxEntries] = {};
std::uint32_t g_EntryCount = 0;
char g_ModKeys[kMaxModKeys][kMaxModKeyLength] = {};
std::uint32_t g_ModKeyCount = 0;
// 下一个 id。基准 = 本体 41 条之后（`LoadPlayers` 序言 `mov w8,#0x29`）。
// 每解析到一条有效 `<player>`（名字非空）就 +1 —— 与引擎往向量里追加一格的语义一致；
// 即使某条因容量限制没存下来，也要 +1，否则后面的名字会整体错位（静默错）。
std::int32_t g_NextId = kModPlayerTypeIdBase;
ModPlayerNameStats g_Stats = {};

// 标签名里允许的字符（用来切分"属性名"）。
bool IsTagNameChar(char c) noexcept {
    return c != ' ' && c != '\t' && c != '\r' && c != '\n' && c != '/' && c != '>' && c != '=';
}

bool IsSpace(char c) noexcept {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}

// 在 `[from, length)` 里找第一个 `<name`，且紧随其后是分隔符（空白 / `/` / `>`）。
// 返回 `<` 的下标；找不到返回 `length`（哨兵）。`<players` 不会被 `<player` 命中
// （`s` 不是分隔符），这条区分是必须的 —— 否则根标签自己会被当成一条玩家。
std::size_t FindTag(const char* xml, std::size_t from, std::size_t length, const char* name,
                    std::size_t nameLength) noexcept {
    if (nameLength == 0 || length < nameLength + 2) {
        return length;
    }
    for (std::size_t i = from; i + 1 + nameLength <= length; ++i) {
        if (xml[i] != '<') {
            continue;
        }
        if (std::memcmp(xml + i + 1, name, nameLength) != 0) {
            continue;
        }
        const char following = i + 1 + nameLength < length ? xml[i + 1 + nameLength] : '\0';
        if (following == '\0' || following == '/' || following == '>' || IsSpace(following)) {
            return i;
        }
    }
    return length;
}

// 从 `<`（下标 `start`）起找该标签的 `>`（跳过引号内的 `>`）。找到返回 true 并给 `*tagEnd`。
bool FindTagEnd(const char* xml, std::size_t start, std::size_t length,
                std::size_t* tagEnd) noexcept {
    char quote = '\0';
    for (std::size_t i = start + 1; i < length; ++i) {
        const char c = xml[i];
        if (quote != '\0') {
            if (c == quote) {
                quote = '\0';
            }
            continue;
        }
        if (c == '"' || c == '\'') {
            quote = c;
            continue;
        }
        if (c == '>') {
            *tagEnd = i;
            return true;
        }
    }
    return false;
}

// 从标签内容里取一个属性的值（去引号）。`nameStart` = 标签名首字符（`<` 的后一格）。
// 只处理最常见的 `名字 = "值"` / `名字 = '值'` / `名字 = 值`；找不到返回 false。
bool ExtractAttribute(const char* xml, std::size_t nameStart, std::size_t tagEnd,
                      const char* attribute, std::size_t attributeLength, const char** value,
                      std::size_t* valueLength) noexcept {
    std::size_t i = nameStart;
    while (i < tagEnd && IsTagNameChar(xml[i])) {  // 跳过标签名（player）
        ++i;
    }
    while (i < tagEnd) {
        while (i < tagEnd && (IsSpace(xml[i]) || xml[i] == '/')) {
            ++i;
        }
        if (i >= tagEnd) {
            break;
        }
        const std::size_t nameBegin = i;
        while (i < tagEnd && IsTagNameChar(xml[i])) {
            ++i;
        }
        const std::size_t nameLength = i - nameBegin;
        while (i < tagEnd && IsSpace(xml[i])) {
            ++i;
        }
        if (i >= tagEnd || xml[i] != '=') {
            continue;  // 布尔属性 / 垃圾字符：跳过，继续找下一个属性名
        }
        ++i;
        while (i < tagEnd && IsSpace(xml[i])) {
            ++i;
        }
        if (i >= tagEnd) {
            break;
        }
        const char quote = xml[i];
        const bool quoted = quote == '"' || quote == '\'';
        if (quoted) {
            ++i;
        }
        const std::size_t valueBegin = i;
        while (i < tagEnd && (quoted ? xml[i] != quote : !IsSpace(xml[i]))) {
            ++i;
        }
        const std::size_t length = i - valueBegin;
        if (nameLength == attributeLength &&
            std::memcmp(xml + nameBegin, attribute, attributeLength) == 0) {
            *value = xml + valueBegin;
            *valueLength = length;
            return true;
        }
        if (quoted && i < tagEnd) {
            ++i;  // 跳过闭引号
        }
    }
    return false;
}

// 把一条名字存进池与条目表；存不下返回 false（并计一次溢出）。
bool StoreName(const ModPlayerName& name, std::int32_t id) noexcept {
    if (g_EntryCount >= kMaxEntries || g_NameUsed + name.length + 1 > kMaxNameBytes) {
        ++g_Stats.capacityOverflow;
        return false;
    }
    const std::uint32_t offset = g_NameUsed;
    std::memcpy(g_NamePool + offset, name.name, name.length);
    g_NamePool[offset + name.length] = '\0';
    g_NameUsed += static_cast<std::uint32_t>(name.length) + 1;
    g_Entries[g_EntryCount].nameOffset = offset;
    g_Entries[g_EntryCount].id = id;
    g_Entries[g_EntryCount].tainted = name.tainted;
    ++g_EntryCount;
    return true;
}

} // namespace

std::uint32_t ParseModPlayersXml(const char* xml, std::size_t length, ModPlayerName* out,
                                 std::uint32_t capacity, bool* malformed,
                                 std::uint32_t* skipped) noexcept {
    if (malformed != nullptr) {
        *malformed = false;
    }
    if (skipped != nullptr) {
        *skipped = 0;
    }
    if (xml == nullptr || length == 0) {
        if (malformed != nullptr) {
            *malformed = true;
        }
        return 0;
    }

    std::size_t position = 0;
    // UTF-8 BOM（模组把文件存成"带 BOM"很常见）—— 不跳过的话根标签会被判缺失。
    if (length >= 3 && static_cast<unsigned char>(xml[0]) == 0xEF &&
        static_cast<unsigned char>(xml[1]) == 0xBB && static_cast<unsigned char>(xml[2]) == 0xBF) {
        position = 3;
    }

    const std::size_t root = FindTag(xml, position, length, "players", 7);
    std::size_t rootEnd = 0;
    if (root == length || !FindTagEnd(xml, root, length, &rootEnd)) {
        if (malformed != nullptr) {
            *malformed = true;  // 不是 players.xml 的形状 / 根标签截断
        }
        return 0;
    }

    std::uint32_t stored = 0;
    std::uint32_t skipCount = 0;
    std::size_t cursor = rootEnd + 1;
    while (true) {
        const std::size_t tag = FindTag(xml, cursor, length, "player", 6);
        if (tag == length) {
            break;
        }
        std::size_t tagEnd = 0;
        if (!FindTagEnd(xml, tag, length, &tagEnd)) {
            if (malformed != nullptr) {
                *malformed = true;  // `<player` 标签截断
            }
            return 0;
        }
        const char* value = nullptr;
        std::size_t valueLength = 0;
        if (ExtractAttribute(xml, tag + 1, tagEnd, "name", 4, &value, &valueLength) &&
            value != nullptr && valueLength > 0) {
            if (out != nullptr && stored < capacity) {
                out[stored].name = value;
                out[stored].length = valueLength;
                const char* parent = nullptr;
                std::size_t parentLength = 0;
                out[stored].tainted =
                    ExtractAttribute(xml, tag + 1, tagEnd, "bSkinParent", 11,
                                     &parent, &parentLength) && parentLength > 0;
            }
            ++stored;  // 计数不受 capacity 限制：调用方要按"引擎会追加几格"推进 id
        } else {
            ++skipCount;  // name 缺失 / 为空 ⇒ 跳过这一条（绝不占 id）
        }
        cursor = tagEnd + 1;
    }

    if (skipped != nullptr) {
        *skipped = skipCount;
    }
    return stored;
}

std::uint32_t IngestModPlayersXml(const char* modKey, const char* xml,
                                  std::size_t length) noexcept {
    // 幂等键不能为空 —— 没有键就无法保证"同名模组喂两次不追加两次"，宁可不加。
    if (modKey == nullptr || modKey[0] == '\0') {
        ++g_Stats.malformedMods;
        return 0;
    }
    // 幂等：同一个 modKey 只接受第一次调用（键表满也不能破例 —— 那时宁可不加）。
    for (std::uint32_t i = 0; i < g_ModKeyCount; ++i) {
        if (std::strcmp(g_ModKeys[i], modKey) == 0) {
            ++g_Stats.duplicateMods;
            return 0;
        }
    }
    if (g_ModKeyCount >= kMaxModKeys) {
        ++g_Stats.capacityOverflow;
        return 0;
    }
    const std::size_t keyLength = std::strlen(modKey);
    if (keyLength + 1 > kMaxModKeyLength) {
        ++g_Stats.capacityOverflow;
        return 0;
    }
    std::memcpy(g_ModKeys[g_ModKeyCount], modKey, keyLength + 1);
    ++g_ModKeyCount;
    ++g_Stats.fedMods;

    ModPlayerName names[kMaxPlayersPerMod];
    bool malformed = false;
    std::uint32_t skipCount = 0;
    const std::uint32_t count =
        ParseModPlayersXml(xml, length, names, kMaxPlayersPerMod, &malformed, &skipCount);
    g_Stats.skippedEntries += skipCount;
    if (malformed) {
        ++g_Stats.malformedMods;
        return 0;  // 坏文件 ⇒ 跳过该模组（不追加、不打乱别的名字的位置）
    }

    std::uint32_t appended = 0;
    for (std::uint32_t index = 0; index < count; ++index) {
        bool stored = false;
        if (index < kMaxPlayersPerMod) {
            stored = StoreName(names[index], g_NextId);
        } else {
            ++g_Stats.capacityOverflow;  // 名字太多、out 装不下（正常不会发生）
        }
        if (stored) {
            ++appended;
        }
        ++g_NextId;  // 无论存没存，都占一个 id（与引擎"往向量里追加一格"一致）
    }
    g_Stats.appended += appended;
    return appended;
}

std::int32_t LookupModPlayerTypeName(const char* name, std::size_t length,
                                   bool tainted) noexcept {
    if (name == nullptr || length == 0) {
        return -1;
    }
    for (std::uint32_t i = g_EntryCount; i > 0; --i) {
        const auto& entry = g_Entries[i - 1];
        if (entry.tainted != tainted) {
            continue;
        }
        const char* const candidate = g_NamePool + entry.nameOffset;
        if (std::strlen(candidate) == length && std::memcmp(candidate, name, length) == 0) {
            return entry.id;
        }
    }
    return -1;  // 未命中：与静态表同口径（PC 契约这几条找不到都是 -1）
}

const ModPlayerNameStats& ModPlayerNameStatistics() noexcept {
    return g_Stats;
}

void NoteModPlayerNameReadFailure() noexcept {
    ++g_Stats.readFailures;
}

void ClearModPlayerNames() noexcept {
    std::memset(g_NamePool, 0, sizeof(g_NamePool));
    g_NameUsed = 0;
    std::memset(g_Entries, 0, sizeof(g_Entries));
    g_EntryCount = 0;
    std::memset(g_ModKeys, 0, sizeof(g_ModKeys));
    g_ModKeyCount = 0;
    g_NextId = kModPlayerTypeIdBase;
    g_Stats = {};
}

void ResetModPlayerNamesForTests() noexcept { ClearModPlayerNames(); }

} // namespace isaac::runtime
