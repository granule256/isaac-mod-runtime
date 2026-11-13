#include "damage_context.hpp"

#include "infrastructure/memory/engine_field_access.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstring>

namespace isaac::runtime::damage {
namespace {

constexpr std::uintptr_t kRefTypeOffset = 0x00;
constexpr std::uintptr_t kRefVariantOffset = 0x04;
constexpr std::uintptr_t kRefSpawnerTypeOffset = 0x08;
constexpr std::uintptr_t kRefSpawnerVariantOffset = 0x0C;
constexpr std::uintptr_t kRefPositionOffset = 0x10;
constexpr std::uintptr_t kRefNativeOffsetOffset = 0x18;
constexpr std::uintptr_t kRefFlagsOffset = 0x20;
constexpr std::uintptr_t kRefEntityOffset = 0x28;
constexpr std::uintptr_t kEntityPositionOffset = 0x310;
constexpr std::uintptr_t kEntityNativeOffsetOffset = 0x334;

CallScope* g_CurrentScope{};

#if !defined(__SWITCH__)
HostReadableCheck g_HostReadableCheck{};
#endif

bool Readable(std::uintptr_t address, std::size_t length) noexcept {
#if defined(__SWITCH__)
    return engine_memory::EngineMemoryReadable(address, length);
#else
    return g_HostReadableCheck != nullptr && g_HostReadableCheck(address, length);
#endif
}

struct ExtraSourceEntry {
    std::uintptr_t sourceRef{};
    std::uintptr_t extraSourceEntity{};
};

std::array<ExtraSourceEntry, kExtraSourceCapacity> g_ExtraSources{};
std::size_t g_ExtraSourceCount{};
std::uintptr_t g_ExtraSourceOverflowSource{};

std::uintptr_t ReadRefEntity(std::uintptr_t sourceRef) noexcept {
    std::uintptr_t entity = 0;
    if (sourceRef == 0 ||
        !Readable(sourceRef + kRefEntityOffset, sizeof(entity))) {
        return 0;
    }
    std::memcpy(&entity, engine_memory::AsObject(sourceRef + kRefEntityOffset),
                sizeof(entity));
    return entity;
}

void SnapshotReference(std::uintptr_t sourceRef, std::uint8_t* storage,
                       bool* readable, std::uint32_t* type,
                       std::uint32_t* variant) noexcept {
    if (readable != nullptr) *readable = false;
    if (type != nullptr) *type = 0;
    if (variant != nullptr) *variant = 0;
    if (storage == nullptr) return;
    std::memset(storage, 0, 0x40);
    if (sourceRef == 0) {
        if (readable != nullptr) *readable = true;
        return;
    }
    if (!Readable(sourceRef, kEntityRefStorageSize)) {
        return;
    }
    std::memcpy(storage, engine_memory::AsObject(sourceRef), kEntityRefStorageSize);
    if (readable != nullptr) *readable = true;
    if (type != nullptr) {
        std::memcpy(type, storage + kRefTypeOffset, sizeof(*type));
    }
    if (variant != nullptr) {
        std::memcpy(variant, storage + kRefVariantOffset, sizeof(*variant));
    }
}

}  // namespace

CallScope::CallScope(std::uintptr_t entity, std::uintptr_t sourceRef,
                     std::int32_t countdown, bool player) noexcept
    : previous_(g_CurrentScope), originalSourceRef_(sourceRef) {
    g_CurrentScope = this;
    values_.entity = entity;
    values_.countdown = countdown;
    values_.player = player;
    SnapshotReference(sourceRef, sourceStorage_, &values_.sourceReadable,
                      &values_.sourceType, &values_.sourceVariant);
    values_.sourceRef = sourceRef != 0 && values_.sourceReadable
        ? engine_memory::AddressOf(sourceStorage_) : 0;
}

CallScope::~CallScope() noexcept {
    if (g_CurrentScope != this) __builtin_trap();
    g_CurrentScope = previous_;
}

bool CallScope::MarkAccepted(float amount, std::int32_t playerDamage,
                             std::uint64_t damageFlags, std::uintptr_t sourceRef,
                             std::int32_t countdown, std::uintptr_t extraSourceEntity,
                             std::int32_t entityType, bool extraSourceOverflow,
                             bool extraSourceUnreadable) noexcept {
    values_.amount = amount;
    values_.playerDamage = playerDamage;
    values_.damageFlags = damageFlags;
    values_.countdown = countdown;
    values_.entityType = entityType;
    values_.extraSourceOverflow = extraSourceOverflow;
    values_.extraSourceUnreadable = extraSourceUnreadable;
    originalSourceRef_ = sourceRef;
    values_.extraSourceOverflowSource = extraSourceOverflow ? sourceRef : 0;
    SnapshotReference(sourceRef, sourceStorage_, &values_.sourceReadable,
                      &values_.sourceType, &values_.sourceVariant);
    values_.sourceRef = sourceRef != 0 && values_.sourceReadable
        ? engine_memory::AddressOf(sourceStorage_) : 0;
    if (!extraSourcePrepared_ && extraSourceEntity != 0) {
        static_cast<void>(SetExtraSourceEntity(extraSourceEntity));
    }
    // MarkAccepted commits state; it must not recapture an existing extra
    // EntityRef after a pre callback morphed or removed that entity.
    values_.extraSourceOverflow = extraSourceOverflow || values_.extraSourceOverflow;
    values_.extraSourceUnreadable =
        extraSourceUnreadable || values_.extraSourceUnreadable;
    values_.extraSourceOverflowSource =
        (values_.extraSourceOverflow || values_.extraSourceUnreadable) ? sourceRef : 0;
    if (extraSourcePrepared_ && extraSourceEntity != 0 &&
        (!values_.extraSourceReadable ||
         ReadRefEntity(engine_memory::AddressOf(extraSourceStorage_)) !=
             extraSourceEntity)) {
        values_.extraSourceReadable = false;
        values_.extraSourceRef = 0;
        values_.extraSourceUnreadable = true;
        values_.extraSourceOverflowSource = sourceRef;
    }
    accepted_ = true;
    return true;
}

void CallScope::FillValues(Values* output) const noexcept {
    if (output != nullptr) *output = values_;
}

bool CallScope::SetExtraSourceEntity(std::uintptr_t extraSourceEntity) noexcept {
    extraSourcePrepared_ = true;
    std::memset(extraSourceStorage_, 0, sizeof(extraSourceStorage_));
    values_.extraSourceReadable = false;
    values_.extraSourceRef = 0;
    if (!BuildEntityReference(extraSourceEntity, extraSourceStorage_)) {
        values_.extraSourceUnreadable = extraSourceEntity != 0;
        values_.extraSourceOverflow = false;
        values_.extraSourceOverflowSource =
            extraSourceEntity != 0 ? originalSourceRef_ : 0;
        return false;
    }
    values_.extraSourceReadable = true;
    values_.extraSourceRef = engine_memory::AddressOf(extraSourceStorage_);
    values_.extraSourceOverflow = false;
    values_.extraSourceUnreadable = false;
    values_.extraSourceOverflowSource = 0;
    return true;
}

const Values* CallScope::Accepted() const noexcept {
    return accepted_ ? &values_ : nullptr;
}

bool CallScope::TakeAccepted(Values* output) noexcept {
    if (!accepted_ || output == nullptr) return false;
    *output = values_;
    accepted_ = false;
    return true;
}

std::uintptr_t CallScope::SourceRef() const noexcept {
    return values_.sourceRef;
}

std::uintptr_t CallScope::OriginalSourceRef() const noexcept {
    return originalSourceRef_;
}

std::uintptr_t CallScope::Entity() const noexcept {
    return values_.entity;
}

std::int32_t CallScope::Countdown() const noexcept {
    return values_.countdown;
}

bool PushExtraSource(std::uintptr_t sourceRef,
                     std::uintptr_t extraSourceEntity) noexcept {
    if (sourceRef == 0 || extraSourceEntity == 0) {
        return false;
    }
    const auto sourceEntity = ReadRefEntity(sourceRef);
    if (sourceEntity == 0) return false;
    if (sourceEntity == extraSourceEntity) return false;
    if (g_ExtraSourceOverflowSource == sourceRef) {
        g_ExtraSourceOverflowSource = 0;
    }
    if (g_ExtraSourceCount >= g_ExtraSources.size()) {
        g_ExtraSourceOverflowSource = sourceRef;
        return false;
    }
    g_ExtraSources[g_ExtraSourceCount++] = {sourceRef, extraSourceEntity};
    return true;
}

void PopExtraSource(std::uintptr_t sourceRef) noexcept {
    for (std::size_t i = g_ExtraSourceCount; i > 0; --i) {
        if (g_ExtraSources[i - 1].sourceRef != sourceRef) continue;
        for (std::size_t j = i; j < g_ExtraSourceCount; ++j) {
            g_ExtraSources[j - 1] = g_ExtraSources[j];
        }
        --g_ExtraSourceCount;
        return;
    }
}

std::uintptr_t FindExtraSource(std::uintptr_t sourceRef) noexcept {
    return FindExtraSource(sourceRef, nullptr);
}

std::uintptr_t FindExtraSource(std::uintptr_t sourceRef, bool* overflow) noexcept {
    if (overflow != nullptr) *overflow = false;
    if (sourceRef != 0 && g_ExtraSourceOverflowSource == sourceRef) {
        if (overflow != nullptr) *overflow = true;
        return 0;
    }
    if (sourceRef == 0) return 0;
    const auto sourceEntity = ReadRefEntity(sourceRef);
    for (std::size_t i = g_ExtraSourceCount; i > 0; --i) {
        const auto& entry = g_ExtraSources[i - 1];
        if (entry.sourceRef == sourceRef && entry.extraSourceEntity != sourceEntity) {
            return entry.extraSourceEntity;
        }
    }
    return 0;
}

bool ExtraSourceOverflowed() noexcept {
    return g_ExtraSourceOverflowSource != 0;
}

bool ExtraSourceOverflowedFor(std::uintptr_t sourceRef) noexcept {
    return sourceRef != 0 && g_ExtraSourceOverflowSource == sourceRef;
}

void ClearExtraSourceOverflow() noexcept {
    g_ExtraSourceOverflowSource = 0;
}

bool BuildEntityReference(std::uintptr_t entity, std::uint8_t* storage) noexcept {
    if (storage == nullptr) return false;
    std::memset(storage, 0, kEntityRefStorageSize);
    if (entity == 0) return false;
    std::uint32_t type = 0;
    std::uint32_t variant = 0;
    std::int32_t spawnerType = 0;
    std::uint32_t spawnerVariant = 0;
    std::uint64_t flags = 0;
    if (!Readable(entity + kEntityTypeOffset, sizeof(type)) ||
        !Readable(entity + kEntityVariantOffset, sizeof(variant)) ||
        !Readable(entity + kEntitySpawnerTypeOffset, sizeof(spawnerType)) ||
        !Readable(entity + kEntitySpawnerVariantOffset, sizeof(spawnerVariant)) ||
        !Readable(entity + kEntityPositionOffset, 2 * sizeof(std::uint32_t)) ||
        !Readable(entity + kEntityNativeOffsetOffset, 2 * sizeof(std::uint32_t)) ||
        !Readable(entity + kEntityFlagsOffset, sizeof(flags))) {
        return false;
    }
    std::memcpy(&type, engine_memory::AsObject(entity + kEntityTypeOffset), sizeof(type));
    std::memcpy(&variant, engine_memory::AsObject(entity + kEntityVariantOffset),
                sizeof(variant));
    std::memcpy(&spawnerType, engine_memory::AsObject(entity + kEntitySpawnerTypeOffset),
                sizeof(spawnerType));
    std::memcpy(&spawnerVariant,
                engine_memory::AsObject(entity + kEntitySpawnerVariantOffset),
                sizeof(spawnerVariant));
    std::memcpy(&flags, engine_memory::AsObject(entity + kEntityFlagsOffset), sizeof(flags));
    std::memcpy(storage + kRefTypeOffset, &type, sizeof(type));
    std::memcpy(storage + kRefVariantOffset, &variant, sizeof(variant));
    std::memcpy(storage + kRefSpawnerTypeOffset, &spawnerType, sizeof(spawnerType));
    std::memcpy(storage + kRefSpawnerVariantOffset, &spawnerVariant,
                sizeof(spawnerVariant));
    std::memcpy(storage + kRefPositionOffset,
                engine_memory::AsObject(entity + kEntityPositionOffset),
                2 * sizeof(std::uint32_t));
    std::memcpy(storage + kRefNativeOffsetOffset,
                engine_memory::AsObject(entity + kEntityNativeOffsetOffset),
                2 * sizeof(std::uint32_t));
    const auto refFlags = static_cast<std::uint32_t>(
        ((flags >> 8) & 1U) | ((flags >> 28) & 2U) | ((flags >> 52) & 4U));
    std::memcpy(storage + kRefFlagsOffset, &refFlags, sizeof(refFlags));
    std::memcpy(storage + kRefEntityOffset, &entity, sizeof(entity));
    return true;
}

ExtraSourceScope::ExtraSourceScope(std::uintptr_t sourceRef,
                                   std::uintptr_t extraSourceEntity) noexcept
    : sourceRef_(sourceRef),
      valid_(PushExtraSource(sourceRef, extraSourceEntity)) {}

ExtraSourceScope::~ExtraSourceScope() noexcept {
    if (valid_) PopExtraSource(sourceRef_);
}

bool IsWhitefireSource(const Values& values) noexcept {
    return values.player && values.sourceReadable && values.sourceType == kWhitefireType &&
           values.sourceVariant == kWhitefireVariant;
}

CallScope* CurrentScope() noexcept {
    return g_CurrentScope;
}

bool TakeCurrentAccepted(Values* output) noexcept {
    return g_CurrentScope != nullptr && g_CurrentScope->TakeAccepted(output);
}

#if !defined(__SWITCH__)
void SetHostReadableCheckForTest(HostReadableCheck check) noexcept {
    g_HostReadableCheck = check;
}
#endif

}  // namespace isaac::runtime::damage
