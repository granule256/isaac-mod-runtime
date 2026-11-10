#pragma once

#include "ports/save_file_port.hpp"
#include <cstdint>

namespace isaac::runtime {

struct SdFileApi {
    std::uint32_t (*create)(const char*, std::int64_t, int){};
    std::uint32_t (*open)(std::uint64_t*, const char*, int){};
    void (*close)(std::uint64_t){};
    std::uint32_t (*size)(std::int64_t*, std::uint64_t){};
    std::uint32_t (*read)(std::uint64_t*, std::uint64_t, std::int64_t, void*, std::size_t){};
    std::uint32_t (*write)(std::uint64_t, std::int64_t, const void*, std::size_t, const std::uint32_t*){};
    std::uint32_t (*flush)(std::uint64_t){};
    std::uint32_t (*remove)(const char*){};
    std::uint32_t (*rename)(const char*, const char*){};
};

// Owns only compatibility-layer files, not native game saves. The legacy port
// is read solely when an SD file is absent; SD errors never select older data.
class SdSaveFileAdapter final : public ISaveFilePort {
public:
    constexpr explicit SdSaveFileAdapter(ISaveFilePort& legacy) noexcept : legacy_(legacy) {}
    using ThreadCheck = bool (*)(void*);
    Status Configure(const SdFileApi&, const char* profileRoot, ThreadCheck, void*) noexcept;
    Status Read(std::string_view, char*, std::size_t, std::size_t*) noexcept override;
    Status GetSize(std::string_view, std::size_t*) noexcept override;
    Status GetSaveSlot(unsigned*) noexcept override;
    Status Write(std::string_view, std::string_view) noexcept override;
    Status Remove(std::string_view) noexcept override;
    Status Exists(const char*, bool*) noexcept override;

private:
    bool Allowed() const noexcept { return thread_ && thread_(context_); }
    bool Path(std::string_view, char*, const char* suffix = "") const noexcept;
    Status Recover(const char*) noexcept;
    Status Size(const char*, std::size_t*) noexcept;
    Status ReadPath(const char*, char*, std::size_t, std::size_t*) noexcept;
    Status WritePath(const char*, std::string_view) noexcept;
    Status Deleted(std::string_view, bool*) noexcept;
    ISaveFilePort& legacy_;
    SdFileApi api_{};
    char root_[160]{};
    ThreadCheck thread_{};
    void* context_{};
    alignas(0x1000) static char buffer_[0x4000];
};

} // namespace isaac::runtime
