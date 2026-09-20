#pragma once

#include "ports/save_file_port.hpp"

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string_view>

namespace ModPersistence {

enum class Result {
    Success,
    Missing,
    Unavailable,
    Corrupt,
    TooLarge,
    IoFailure,
};

constexpr std::size_t kMaximumFileSize = 16 * 1024;
constexpr std::size_t kMaximumRecordCount = 256;

namespace detail {

constexpr char kMagic[] = "ISMODST2";
constexpr std::uint16_t kVersion = 2;
constexpr std::size_t kHeaderSize = 32;
constexpr std::size_t kRecordHeaderSize = 24;
constexpr std::uint8_t kStringType = 1;
//: 模组数据容器的文件名，**相对于游戏存档分区根**（旧值是一条 `sdmc:/SaltySD/...` 的绝对路径，
//: 那条依赖外部插件提供文件能力，2026-09-17 起废弃）。
constexpr char kStateName[] = "isaac-mod-data.bin";
constexpr std::uint64_t kModDataKey = 0x6D6F642D64617461ULL; // "mod-data"

// 文件能力**只有一条路**（2026-09-17 用户指令）：`isaac::runtime::SessionSaveFilePort()`
// —— 默认实现就是"游戏存档分区"（`EngineSaveFileAdapter`，直连 `nn::fs`）。
//
// 为什么不再保留"宿主插件注册 4 个裸函数"那条路：生产包里插件是关的（`SALTYNX_PLUGIN=0`），
// 那条路等于永远没有提供方 ⇒ `Mod:SaveData/LoadData` 与 `Isaac.SaveModData/LoadModData`
// 一直返回"不可用"（真机可见后果：EID 的设置读不回来）。**统一到一个端口**之后，
// 消费者不必再判"哪条路可用"，线程纪律也由端口实现统一负责（见 `EngineSaveFileAdapter` 的硬闸）。
//
// `Unavailable` 仍是一等状态：端口没接上时所有操作如实返回它，不静默失败。
inline bool HasFileApi() {
    return isaac::runtime::SessionSaveFilePort() != nullptr;
}

struct Cache {
    std::array<std::uint8_t, kMaximumFileSize> payload{};
    std::size_t payloadLength = 0;
    std::uint64_t generation = 0;
    bool loaded = false;
    bool exists = false;
};

inline Cache g_cache{};

inline void WriteU16(std::uint8_t* target, std::uint16_t value) {
    target[0] = static_cast<std::uint8_t>(value);
    target[1] = static_cast<std::uint8_t>(value >> 8);
}

inline void WriteU32(std::uint8_t* target, std::uint32_t value) {
    for (std::size_t index = 0; index < 4; ++index) {
        target[index] = static_cast<std::uint8_t>(value >> (index * 8));
    }
}

inline void WriteU64(std::uint8_t* target, std::uint64_t value) {
    for (std::size_t index = 0; index < 8; ++index) {
        target[index] = static_cast<std::uint8_t>(value >> (index * 8));
    }
}

inline std::uint16_t ReadU16(const std::uint8_t* source) {
    return static_cast<std::uint16_t>(source[0]) |
           (static_cast<std::uint16_t>(source[1]) << 8);
}

inline std::uint32_t ReadU32(const std::uint8_t* source) {
    std::uint32_t value = 0;
    for (std::size_t index = 0; index < 4; ++index) {
        value |= static_cast<std::uint32_t>(source[index]) << (index * 8);
    }
    return value;
}

inline std::uint64_t ReadU64(const std::uint8_t* source) {
    std::uint64_t value = 0;
    for (std::size_t index = 0; index < 8; ++index) {
        value |= static_cast<std::uint64_t>(source[index]) << (index * 8);
    }
    return value;
}

inline std::uint32_t Checksum(const std::uint8_t* bytes, std::size_t length) {
    std::uint32_t value = 2166136261U;
    for (std::size_t index = 0; index < length; ++index) {
        value ^= bytes[index];
        value *= 16777619U;
    }
    return value;
}

// 端口的状态码 → 本模块的结果码。`Unsupported`（没有提供方）单独映射成 `Unavailable`：
// 这是"能力缺失"，与"操作失败"必须能分开，调用方（含 Lua 侧）据此报不同的错。
inline Result MapStatus(isaac::runtime::Status status) {
    switch (status.code()) {
        case isaac::runtime::StatusCode::Ok:
            return Result::Success;
        case isaac::runtime::StatusCode::Unsupported:
            return Result::Unavailable;
        case isaac::runtime::StatusCode::NotFound:
            return Result::Missing;
        case isaac::runtime::StatusCode::Corrupted:
            return Result::Corrupt;
        case isaac::runtime::StatusCode::CapacityExceeded:
            return Result::TooLarge;
        case isaac::runtime::StatusCode::InvalidArgument:
        case isaac::runtime::StatusCode::InvalidState:
        case isaac::runtime::StatusCode::IoFailure:
        case isaac::runtime::StatusCode::Rejected:
            return Result::IoFailure;
    }
    return Result::IoFailure;
}

inline bool RecordAt(const std::uint8_t* payload, std::size_t payloadLength,
                     std::size_t offset, std::size_t* recordLength,
                     std::uint64_t* namespaceId, std::uint64_t* key,
                     std::uint8_t* type, std::size_t* valueLength) {
    if (offset > payloadLength || payloadLength - offset < kRecordHeaderSize) {
        return false;
    }
    const std::uint8_t* record = payload + offset;
    const std::size_t length = ReadU32(record + 20);
    if (length > payloadLength - offset - kRecordHeaderSize) {
        return false;
    }
    *recordLength = kRecordHeaderSize + length;
    *namespaceId = ReadU64(record);
    *key = ReadU64(record + 8);
    *type = record[16];
    *valueLength = length;
    return true;
}

inline Result LoadCache() {
    if (g_cache.loaded) {
        return Result::Success;
    }
    isaac::runtime::ISaveFilePort* storage = isaac::runtime::SessionSaveFilePort();
    if (storage == nullptr) {
        return Result::Unavailable;
    }

    std::array<std::uint8_t, kMaximumFileSize> encoded{};
    std::size_t bytes = 0;
    // 整文件读：名字**相对存档根**（旧的 `sdmc:/SaltySD/...` 路径不再使用 —— 游戏嘴里的
    // `sdmc:` 本来就是它自己的存档分区，见 `ports/save_file_port.hpp` 的说明）。
    const isaac::runtime::Status readStatus =
        storage->Read(kStateName, reinterpret_cast<char*>(encoded.data()), encoded.size(), &bytes);
    if (readStatus.code() == isaac::runtime::StatusCode::NotFound) {
        // 还没有数据：历史语义就是"成功 + exists=false"（第一次保存前就是这样），保持不动。
        g_cache.loaded = true;
        g_cache.exists = false;
        return Result::Success;
    }
    if (!readStatus.ok()) {
        return MapStatus(readStatus);
    }
    if (bytes < kHeaderSize || std::memcmp(encoded.data(), kMagic, sizeof(kMagic) - 1) != 0 ||
        ReadU16(encoded.data() + 8) != kVersion || ReadU16(encoded.data() + 10) != kHeaderSize) {
        return Result::Corrupt;
    }

    const std::uint32_t count = ReadU32(encoded.data() + 20);
    const std::size_t payloadLength = ReadU32(encoded.data() + 24);
    if (count > kMaximumRecordCount || payloadLength > kMaximumFileSize - kHeaderSize ||
        payloadLength != bytes - kHeaderSize ||
        ReadU32(encoded.data() + 28) != Checksum(encoded.data() + kHeaderSize, payloadLength)) {
        return Result::Corrupt;
    }

    std::size_t offset = 0;
    for (std::uint32_t index = 0; index < count; ++index) {
        std::size_t recordLength = 0;
        std::size_t valueLength = 0;
        std::uint64_t namespaceId = 0;
        std::uint64_t key = 0;
        std::uint8_t type = 0;
        if (!RecordAt(encoded.data() + kHeaderSize, payloadLength, offset, &recordLength,
                      &namespaceId, &key, &type, &valueLength)) {
            return Result::Corrupt;
        }
        offset += recordLength;
    }
    if (offset != payloadLength) {
        return Result::Corrupt;
    }

    std::memcpy(g_cache.payload.data(), encoded.data() + kHeaderSize, payloadLength);
    g_cache.payloadLength = payloadLength;
    g_cache.generation = ReadU64(encoded.data() + 12);
    g_cache.exists = true;
    g_cache.loaded = true;
    return Result::Success;
}

inline Result WriteCache(const std::uint8_t* payload, std::size_t payloadLength,
                         std::uint32_t recordCount) {
    if (payloadLength > kMaximumFileSize - kHeaderSize || recordCount > kMaximumRecordCount) {
        return Result::TooLarge;
    }
    std::array<std::uint8_t, kMaximumFileSize> encoded{};
    std::memcpy(encoded.data(), kMagic, sizeof(kMagic) - 1);
    WriteU16(encoded.data() + 8, kVersion);
    WriteU16(encoded.data() + 10, kHeaderSize);
    WriteU64(encoded.data() + 12, g_cache.generation + 1);
    WriteU32(encoded.data() + 20, recordCount);
    WriteU32(encoded.data() + 24, static_cast<std::uint32_t>(payloadLength));
    if (payloadLength != 0) {
        std::memcpy(encoded.data() + kHeaderSize, payload, payloadLength);
    }
    WriteU32(encoded.data() + 28, Checksum(encoded.data() + kHeaderSize, payloadLength));

    isaac::runtime::ISaveFilePort* storage = isaac::runtime::SessionSaveFilePort();
    if (storage == nullptr) {
        return Result::Unavailable;
    }
    const std::size_t totalLength = kHeaderSize + payloadLength;
    // 整文件写：适配器内部会 CreateFile / SetFileSize / Flush / **CommitSaveData**，
    // 所以"一次写 = 一次提交"，不存在写一半的中间状态。
    const isaac::runtime::Status writeStatus = storage->Write(
        kStateName, std::string_view(reinterpret_cast<const char*>(encoded.data()), totalLength));
    if (!writeStatus.ok()) {
        return MapStatus(writeStatus);
    }

    std::memcpy(g_cache.payload.data(), payload, payloadLength);
    g_cache.payloadLength = payloadLength;
    g_cache.generation += 1;
    g_cache.exists = true;
    g_cache.loaded = true;
    return Result::Success;
}

inline Result Rewrite(std::uint64_t namespaceId, const char* value, std::size_t valueLength,
                      bool remove) {
    const Result loaded = LoadCache();
    if (loaded != Result::Success) {
        return loaded;
    }
    std::array<std::uint8_t, kMaximumFileSize> rewritten{};
    std::size_t rewrittenLength = 0;
    std::uint32_t rewrittenCount = 0;
    bool matched = false;
    for (std::size_t offset = 0; offset < g_cache.payloadLength;) {
        std::size_t recordLength = 0;
        std::size_t existingValueLength = 0;
        std::uint64_t existingNamespace = 0;
        std::uint64_t existingKey = 0;
        std::uint8_t type = 0;
        if (!RecordAt(g_cache.payload.data(), g_cache.payloadLength, offset, &recordLength,
                      &existingNamespace, &existingKey, &type, &existingValueLength)) {
            return Result::Corrupt;
        }
        const bool replace = existingNamespace == namespaceId && existingKey == kModDataKey &&
                             type == kStringType;
        matched = matched || replace;
        if (!replace) {
            if (recordLength > rewritten.size() - rewrittenLength) {
                return Result::TooLarge;
            }
            std::memcpy(rewritten.data() + rewrittenLength, g_cache.payload.data() + offset,
                        recordLength);
            rewrittenLength += recordLength;
            ++rewrittenCount;
        }
        offset += recordLength;
    }
    if (remove && !matched) {
        return Result::Success;
    }
    if (!remove) {
        if (value == nullptr || rewrittenLength > rewritten.size() - kRecordHeaderSize ||
            valueLength > rewritten.size() - rewrittenLength - kRecordHeaderSize ||
            rewrittenCount == kMaximumRecordCount) {
            return Result::TooLarge;
        }
        std::uint8_t* record = rewritten.data() + rewrittenLength;
        WriteU64(record, namespaceId);
        WriteU64(record + 8, kModDataKey);
        record[16] = kStringType;
        record[17] = record[18] = record[19] = 0;
        WriteU32(record + 20, static_cast<std::uint32_t>(valueLength));
        if (valueLength != 0) {
            std::memcpy(record + kRecordHeaderSize, value, valueLength);
        }
        rewrittenLength += kRecordHeaderSize + valueLength;
        ++rewrittenCount;
    }
    return WriteCache(rewritten.data(), rewrittenLength, rewrittenCount);
}

} // namespace detail

inline std::uint64_t HashModNamespace(const char* name, std::size_t length) {
    std::uint64_t value = 14695981039346656037ULL;
    for (std::size_t index = 0; index < length; ++index) {
        value ^= static_cast<unsigned char>(name[index]);
        value *= 1099511628211ULL;
    }
    return value;
}

// 文件能力的**唯一注入点**现在在端口那一层：`isaac::runtime::SetSessionSaveFilePort()`。
// 本模块不再自己持有提供方指针 —— 这就是"解耦合"的具体含义：
//   * 消费者只问 `SessionSaveFilePort()`；
//   * 谁提供（存档分区适配器 / 测试用的假端口）由注入点决定，消费者无感。
// 传 nullptr = 明确撤销提供方（此后所有操作返回 `Unavailable`，是一等状态而不是沉默失败）。
inline bool IsFileApiReady() {
    return detail::HasFileApi();
}

inline void ResetCacheForTesting() {
    detail::g_cache = {};
}

inline Result SaveModData(std::uint64_t namespaceId, const char* data, std::size_t length) {
    return detail::Rewrite(namespaceId, data, length, false);
}

inline Result LoadModData(std::uint64_t namespaceId, const char** data, std::size_t* length) {
    if (data == nullptr || length == nullptr) {
        return Result::IoFailure;
    }
    const Result loaded = detail::LoadCache();
    if (loaded != Result::Success) {
        return loaded;
    }
    for (std::size_t offset = 0; offset < detail::g_cache.payloadLength;) {
        std::size_t recordLength = 0;
        std::size_t valueLength = 0;
        std::uint64_t recordNamespace = 0;
        std::uint64_t key = 0;
        std::uint8_t type = 0;
        if (!detail::RecordAt(detail::g_cache.payload.data(), detail::g_cache.payloadLength, offset,
                              &recordLength, &recordNamespace, &key, &type, &valueLength)) {
            return Result::Corrupt;
        }
        if (recordNamespace == namespaceId && key == detail::kModDataKey &&
            type == detail::kStringType) {
            *data = reinterpret_cast<const char*>(detail::g_cache.payload.data() + offset +
                                                  detail::kRecordHeaderSize);
            *length = valueLength;
            return Result::Success;
        }
        offset += recordLength;
    }
    *data = nullptr;
    *length = 0;
    return Result::Missing;
}

inline Result HasModData(std::uint64_t namespaceId, bool* has) {
    if (has == nullptr) {
        return Result::IoFailure;
    }
    const char* data = nullptr;
    std::size_t length = 0;
    const Result result = LoadModData(namespaceId, &data, &length);
    if (result == Result::Success) {
        *has = true;
        return Result::Success;
    }
    if (result == Result::Missing) {
        *has = false;
        return Result::Success;
    }
    return result;
}

inline Result RemoveModData(std::uint64_t namespaceId) {
    return detail::Rewrite(namespaceId, nullptr, 0, true);
}

} // namespace ModPersistence
