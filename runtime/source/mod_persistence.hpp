#pragma once
#include "ports/save_file_port.hpp"
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <memory>
#include <new>
#include <string_view>

namespace ModPersistence {
enum class Result { Success, Missing, Unavailable, Corrupt, TooLarge, IoFailure };
// 仅旧ISMODST2容器的格式上限；新独立文件按实际长度申请，不再共用这个额度。
constexpr std::size_t kMaximumFileSize = 16 * 1024;
constexpr std::size_t kMaximumRecordCount = 256;
namespace detail {
constexpr char kStateName[] = "isaac-mod-data.bin";
constexpr std::uint64_t kModDataKey = 0x6D6F642D64617461ULL;
constexpr std::uint8_t kStringType = 1;
constexpr std::size_t kRecordHeaderSize = 24;
constexpr std::size_t kHeaderSize = 48;
constexpr char kMagic[] = "ISMODST3";
inline bool HasFileApi() { return isaac::runtime::SessionSaveFilePort() != nullptr; }
struct Buffer {
    std::unique_ptr<std::uint8_t[]> bytes{};
    std::size_t length = 0;
};
struct Cache {
    Cache* next = nullptr;
    std::uint64_t namespaceId = 0;
    unsigned slot = 0;
    Buffer encoded{};
    std::uint64_t generation = 0;
    int bank = -1;
    bool loaded = false;
    bool exists = false;
};
// 常量初始化：运行时使用-nostartfiles，不能依赖全局容器动态初始化。
inline Cache* g_cache = nullptr;
inline Buffer* g_legacy = nullptr;
inline bool g_legacyLoaded = false;
inline Result g_legacyResult = Result::Missing;
inline isaac::runtime::ISaveFilePort* g_cacheProvider = nullptr;
inline std::uint64_t g_SkippedIdenticalWrites = 0;
inline std::uint64_t g_SkippedIdenticalBytes = 0;
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

inline void ClearCache() {
    while (g_cache != nullptr) {
        Cache* old = g_cache;
        g_cache = old->next;
        delete old;
    }
    g_cacheProvider = nullptr;
    delete g_legacy; g_legacy = nullptr;
    g_legacyLoaded = false; g_legacyResult = Result::Missing;
}
inline void FileName(std::uint64_t ns, unsigned slot, int bank, char (&name)[64]) {
    std::snprintf(name, sizeof(name), "isaac-mod-%016llx-s%u-%c.bin",
                  static_cast<unsigned long long>(ns), slot, bank == 0 ? 'a' : 'b');
}
inline Result ReadFile(std::string_view name, Buffer* output) {
    auto* storage = isaac::runtime::SessionSaveFilePort();
    if (storage == nullptr) return Result::Unavailable;
    std::size_t capacity = 0;
    auto status = storage->GetSize(name, &capacity);
    if (status.code() == isaac::runtime::StatusCode::NotFound) return Result::Missing;
    if (status.code() == isaac::runtime::StatusCode::Unsupported) capacity = kMaximumFileSize;
    else if (!status.ok()) return MapStatus(status);
    if (capacity > std::numeric_limits<std::uint32_t>::max()) return Result::TooLarge;
    Buffer file;
    file.bytes.reset(new (std::nothrow) std::uint8_t[capacity == 0 ? 1 : capacity]);
    if (!file.bytes) return Result::IoFailure;
    std::size_t actual = 0;
    status = storage->Read(name, reinterpret_cast<char*>(file.bytes.get()), capacity, &actual);
    if (status.code() == isaac::runtime::StatusCode::CapacityExceeded && actual > capacity) {
        if (actual > std::numeric_limits<std::uint32_t>::max()) return Result::TooLarge;
        capacity = actual;
        file.bytes.reset(new (std::nothrow) std::uint8_t[capacity]);
        if (!file.bytes) return Result::IoFailure;
        status = storage->Read(name, reinterpret_cast<char*>(file.bytes.get()), capacity, &actual);
    }
    if (!status.ok()) return MapStatus(status);
    if (actual > capacity) return Result::Corrupt;
    file.length = actual;
    *output = std::move(file);
    return Result::Success;
}
inline bool ValidateFile(const Buffer& file, std::uint64_t ns, unsigned slot) {
    const auto* p = file.bytes.get();
    return file.length >= kHeaderSize && std::memcmp(p, kMagic, 8) == 0 &&
           ReadU16(p+8) == 3 && ReadU16(p+10) == kHeaderSize &&
           ReadU64(p+20) == ns && ReadU32(p+28) == file.length-kHeaderSize &&
           ReadU32(p+32) <= 1 && ReadU32(p+36) == slot &&
           ReadU32(p+40) == Checksum(p+kHeaderSize,file.length-kHeaderSize) &&
           ReadU32(p+44) == Checksum(p,44) &&
           (ReadU32(p+32) == 0 || file.length == kHeaderSize);
}
inline Result ReadLegacy() {
    if(g_legacyLoaded) return g_legacyResult;
    Buffer legacy;
    const Result result=ReadFile(kStateName,&legacy);
    if(result==Result::Missing) {g_legacyLoaded=true;return g_legacyResult=Result::Missing;}
    if(result!=Result::Success) return result;
    const auto* p=legacy.bytes.get();
    if (legacy.length < 32 || legacy.length > kMaximumFileSize ||
        std::memcmp(p,"ISMODST2",8)!=0 || ReadU16(p+8)!=2 || ReadU16(p+10)!=32 ||
        ReadU32(p+20)>kMaximumRecordCount || ReadU32(p+24)!=legacy.length-32 ||
        ReadU32(p+28)!=Checksum(p+32,legacy.length-32)) return Result::Corrupt;
    g_legacy=new (std::nothrow) Buffer;
    if(!g_legacy) return Result::IoFailure;
    *g_legacy=std::move(legacy);g_legacyLoaded=true;g_legacyResult=Result::Success;
    return Result::Success;
}
inline Result ImportLegacy(Cache* cache) {
    const Result result = ReadLegacy();
    if (result == Result::Missing) {cache->loaded=true;return Result::Success;}
    if (result != Result::Success) return result;
    const Buffer& legacy=*g_legacy;
    const auto* p=legacy.bytes.get();
    // 全部记录先验证，不能看到目标记录就提前信任后面可能截断的容器。
    std::size_t offset=0, valueOffset=0, valueLength=0;
    bool found=false;
    const auto payloadLength=legacy.length-32;
    for (std::uint32_t i=0;i<ReadU32(p+20);++i) {
        std::size_t recordLength=0,len=0;std::uint64_t ns=0,key=0;std::uint8_t type=0;
        if (!RecordAt(p+32,payloadLength,offset,&recordLength,&ns,&key,&type,&len)) return Result::Corrupt;
        if(ns==cache->namespaceId && key==kModDataKey && type==kStringType) {
            found=true;valueOffset=32+offset+kRecordHeaderSize;valueLength=len;
        }
        offset+=recordLength;
    }
    if(offset!=payloadLength) return Result::Corrupt;
    if(found) {
        cache->encoded.bytes.reset(new (std::nothrow) std::uint8_t[kHeaderSize+valueLength]);
        if(!cache->encoded.bytes) return Result::IoFailure;
        cache->encoded.length=kHeaderSize+valueLength;
        if(valueLength) std::memcpy(cache->encoded.bytes.get()+kHeaderSize,p+valueOffset,valueLength);
        cache->exists=true;
    }
    cache->loaded=true;
    // 旧容器没有槽信息。仅作为只读历史源；新保存带真实槽名，不覆盖旧容器。
    return Result::Success;
}
inline Result LoadCache(Cache* cache) {
    if(cache->loaded) return Result::Success;
    Buffer banks[2]; Result results[2];
    for(int i=0;i<2;++i) {
        char name[64];FileName(cache->namespaceId,cache->slot,i,name);
        results[i]=ReadFile(name,&banks[i]);
        if(results[i]==Result::Success && !ValidateFile(banks[i],cache->namespaceId,cache->slot)) results[i]=Result::Corrupt;
        if(results[i]!=Result::Success && results[i]!=Result::Missing && results[i]!=Result::Corrupt) return results[i];
    }
    int bank=-1;
    if(results[0]==Result::Success) bank=0;
    if(results[1]==Result::Success && (bank<0 || ReadU64(banks[1].bytes.get()+12)>ReadU64(banks[0].bytes.get()+12))) bank=1;
    if(bank<0) {
        const auto result=ImportLegacy(cache);
        if((results[0]==Result::Corrupt || results[1]==Result::Corrupt) &&
           result==Result::Success && !cache->exists) {
            cache->loaded=false;return Result::Corrupt;
        }
        return result;
    }
    cache->generation=ReadU64(banks[bank].bytes.get()+12);
    cache->exists=ReadU32(banks[bank].bytes.get()+32)==0;
    cache->encoded=std::move(banks[bank]);cache->bank=bank;cache->loaded=true;
    return Result::Success;
}
inline Result GetCache(std::uint64_t namespaceId, Cache** output) {
    auto* storage=isaac::runtime::SessionSaveFilePort();
    if(storage==nullptr) return Result::Unavailable;
    if(g_cacheProvider!=storage) {ClearCache();g_cacheProvider=storage;}
    unsigned slot=0;
    const auto status=storage->GetSaveSlot(&slot);
    if(!status.ok()) return MapStatus(status);
    if(slot>3) return Result::IoFailure;
    Cache* cache=g_cache;
    while(cache && (cache->namespaceId!=namespaceId || cache->slot!=slot)) cache=cache->next;
    if(!cache) {
        cache=new (std::nothrow) Cache;
        if(!cache) return Result::IoFailure;
        cache->namespaceId=namespaceId;cache->slot=slot;cache->next=g_cache;g_cache=cache;
    }
    const Result loaded=LoadCache(cache);
    if(loaded==Result::Success) *output=cache;
    return loaded;
}
inline Result Rewrite(std::uint64_t namespaceId,const char* data,std::size_t length,bool remove) {
    if((data==nullptr && length!=0) || length>std::numeric_limits<std::uint32_t>::max()-kHeaderSize) return Result::TooLarge;
    Cache* cache=nullptr;const auto loaded=GetCache(namespaceId,&cache);
    if(loaded!=Result::Success) return loaded;
    if(remove && !cache->exists) return Result::Success;
    if(!remove && cache->exists && length==cache->encoded.length-kHeaderSize &&
        (length==0 || std::memcmp(cache->encoded.bytes.get()+kHeaderSize,data,length)==0)) {
        ++g_SkippedIdenticalWrites;g_SkippedIdenticalBytes+=length;return Result::Success;
    }
    if(cache->generation==std::numeric_limits<std::uint64_t>::max()) return Result::IoFailure;
    Buffer encoded;encoded.length=kHeaderSize+(remove?0:length);
    encoded.bytes.reset(new (std::nothrow) std::uint8_t[encoded.length]);
    if(!encoded.bytes) return Result::IoFailure;
    auto* p=encoded.bytes.get();std::memset(p,0,kHeaderSize);
    std::memcpy(p,kMagic,8);WriteU16(p+8,3);WriteU16(p+10,kHeaderSize);
    WriteU64(p+12,cache->generation+1);WriteU64(p+20,namespaceId);
    WriteU32(p+28,remove?0:static_cast<std::uint32_t>(length));WriteU32(p+32,remove?1:0);
    WriteU32(p+36,cache->slot);
    if(!remove && length) std::memcpy(p+kHeaderSize,data,length);
    WriteU32(p+40,Checksum(p+kHeaderSize,encoded.length-kHeaderSize));WriteU32(p+44,Checksum(p,44));
    const int bank=cache->bank==0?1:0;
    char name[64];FileName(namespaceId,cache->slot,bank,name);
    auto* storage=isaac::runtime::SessionSaveFilePort();
    if(storage==nullptr) return Result::Unavailable;
    // 覆盖旧的非当前代次，写入/flush/commit失败时不更新内存；当前成功代次始终保留。
    const auto status=storage->Write(name,std::string_view(reinterpret_cast<const char*>(p),encoded.length));
    if(!status.ok()) return MapStatus(status);
    cache->encoded=std::move(encoded);cache->generation+=1;cache->bank=bank;
    cache->exists=!remove;return Result::Success;
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

inline bool IsFileApiReady() { return detail::HasFileApi(); }
inline void ResetCacheForTesting() { detail::ClearCache(); }
inline Result SaveModData(std::uint64_t ns,const char* data,std::size_t length) {
    return detail::Rewrite(ns,data,length,false);
}
inline Result LoadModData(std::uint64_t ns,const char** data,std::size_t* length) {
    if(data==nullptr || length==nullptr) return Result::IoFailure;
    *data=nullptr;*length=0;
    detail::Cache* cache=nullptr;const auto result=detail::GetCache(ns,&cache);
    if(result!=Result::Success) return result;
    if(!cache->exists) return Result::Missing;
    *data=reinterpret_cast<const char*>(cache->encoded.bytes.get()+detail::kHeaderSize);
    *length=cache->encoded.length-detail::kHeaderSize;
    return Result::Success;
}
inline Result HasModData(std::uint64_t ns,bool* has) {
    if(has==nullptr) return Result::IoFailure;
    const char* data=nullptr;std::size_t length=0;
    const auto result=LoadModData(ns,&data,&length);
    if(result==Result::Success) {*has=true;return Result::Success;}
    if(result==Result::Missing) {*has = false;return Result::Success;}
    return result;
}
inline Result RemoveModData(std::uint64_t ns) {return detail::Rewrite(ns,nullptr,0,true);}
} // namespace ModPersistence
