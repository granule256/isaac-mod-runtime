#pragma once

#include <cstddef>
#include <cstdint>

namespace isaac::runtime::damage {

inline constexpr std::size_t kEntityRefStorageSize = 0x30;
inline constexpr std::uintptr_t kWhitefireType = 33;
inline constexpr std::uintptr_t kWhitefireVariant = 4;
inline constexpr std::size_t kExtraSourceInlineCapacity = 16;
inline constexpr std::size_t kExtraSourceSpillCapacity = 64;
inline constexpr std::size_t kExtraSourceCapacity =
    kExtraSourceInlineCapacity + kExtraSourceSpillCapacity;

// Values observed at the native accepted-damage boundary. `sourceRef` and
// `extraSourceRef` point to EntityRef-shaped storage, never to a synthetic
// Entity pointer. A zero pointer means the callback argument is nil.
struct Values {
    std::uintptr_t entity{};
    float amount{};
    std::int32_t playerDamage{};
    std::uint64_t damageFlags{};
    std::uintptr_t sourceRef{};
    std::int32_t countdown{};
    std::uintptr_t extraSourceRef{};
    std::int32_t entityType{};
    std::uint32_t sourceType{};
    std::uint32_t sourceVariant{};
    bool player{};
    bool sourceReadable{};
    bool extraSourceReadable{};
    // A real extra source existed but could not be represented. Overflow is
    // the fixed-capacity failure; unreadable is a failed EntityRef snapshot.
    bool extraSourceOverflow{};
    bool extraSourceUnreadable{};
    bool legacyArguments{};
    std::uintptr_t extraSourceOverflowSource{};
};

// Per-call storage for the Source/ExtraSource EntityRef snapshots. The scope
// keeps the snapshots alive through the post-original callback.
class CallScope {
public:
    CallScope(std::uintptr_t entity, std::uintptr_t sourceRef, std::int32_t countdown,
              bool player = true) noexcept;
    ~CallScope() noexcept;
    CallScope(const CallScope&) = delete;
    CallScope& operator=(const CallScope&) = delete;
    CallScope(CallScope&&) = delete;
    CallScope& operator=(CallScope&&) = delete;

    [[nodiscard]] bool MarkAccepted(
        float amount, std::int32_t playerDamage, std::uint64_t damageFlags,
        std::uintptr_t sourceRef, std::int32_t countdown, std::uintptr_t extraSourceEntity,
        std::int32_t entityType, bool extraSourceOverflow = false,
        bool extraSourceUnreadable = false) noexcept;
    void FillValues(Values* output) const noexcept;
    [[nodiscard]] bool SetExtraSourceEntity(std::uintptr_t extraSourceEntity) noexcept;
    [[nodiscard]] const Values* Accepted() const noexcept;
    [[nodiscard]] bool TakeAccepted(Values* output) noexcept;
    [[nodiscard]] std::uintptr_t SourceRef() const noexcept;
    [[nodiscard]] std::uintptr_t OriginalSourceRef() const noexcept;
    [[nodiscard]] std::uintptr_t Entity() const noexcept;
    [[nodiscard]] std::int32_t Countdown() const noexcept;

    friend bool TakeCurrentAccepted(Values* output) noexcept;

private:
    CallScope* previous_{};
    Values values_{};
    bool accepted_{};
    bool extraSourcePrepared_{};
    std::uintptr_t originalSourceRef_{};
    std::uint8_t sourceStorage_[0x40]{};
    std::uint8_t extraSourceStorage_[0x40]{};
};

// Game-thread-only correlation table for native calls that pass a distinct
// extra source. Sixteen inline entries cover the normal nesting depth; the
// fixed spill region avoids a default heap allocation. Exhaustion is never
// represented as a missing extra source: Push returns false and the caller can
// query ExtraSourceOverflowedFor(sourceRef).
[[nodiscard]] bool PushExtraSource(std::uintptr_t sourceRef,
                                   std::uintptr_t extraSourceEntity) noexcept;
void PopExtraSource(std::uintptr_t sourceRef) noexcept;
[[nodiscard]] std::uintptr_t FindExtraSource(std::uintptr_t sourceRef) noexcept;
[[nodiscard]] std::uintptr_t FindExtraSource(std::uintptr_t sourceRef,
                                             bool* overflow) noexcept;
[[nodiscard]] bool ExtraSourceOverflowed() noexcept;
[[nodiscard]] bool ExtraSourceOverflowedFor(std::uintptr_t sourceRef) noexcept;
void ClearExtraSourceOverflow() noexcept;
// Builds the same complete 0x30-byte EntityRef snapshot used by EntityRef(entity).
// `storage` must remain alive for the duration of every consumer of the reference.
[[nodiscard]] bool BuildEntityReference(std::uintptr_t entity,
                                        std::uint8_t* storage) noexcept;

class ExtraSourceScope {
public:
    ExtraSourceScope(std::uintptr_t sourceRef, std::uintptr_t extraSourceEntity) noexcept;
    ~ExtraSourceScope() noexcept;
    ExtraSourceScope(const ExtraSourceScope&) = delete;
    ExtraSourceScope& operator=(const ExtraSourceScope&) = delete;
    ExtraSourceScope(ExtraSourceScope&&) = delete;
    ExtraSourceScope& operator=(ExtraSourceScope&&) = delete;

    [[nodiscard]] bool Valid() const noexcept { return valid_; }

private:
    std::uintptr_t sourceRef_{};
    bool valid_{};
};

[[nodiscard]] bool IsWhitefireSource(const Values& values) noexcept;
[[nodiscard]] CallScope* CurrentScope() noexcept;
[[nodiscard]] bool TakeCurrentAccepted(Values* output) noexcept;

#if !defined(__SWITCH__)
using HostReadableCheck = bool (*)(std::uintptr_t, std::size_t);
void SetHostReadableCheckForTest(HostReadableCheck check) noexcept;
#endif

}  // namespace isaac::runtime::damage
