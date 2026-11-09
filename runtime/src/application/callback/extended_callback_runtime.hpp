#pragma once

#include "domain/callback/callback_descriptor.hpp"
#include <cstddef>

namespace isaac::runtime {

// A sorted view owned by the extension session. Original callback IDs retain
// their existing state/diagnostic layout. Sparse extension IDs need no holes.
// All access, including publication and teardown, is on the game thread.
struct ExtendedCallbackState {
    CallbackId id{};
    bool enabled{};
    std::uint32_t registrations{};
    std::uint32_t dispatches{};
};

inline ExtendedCallbackState* g_ExtendedCallbacks{};
inline std::size_t g_ExtendedCallbackCount{};
inline std::size_t g_ExtendedCallbackEnabledCount{};
inline bool g_ExtendedCallbackDelivery{};

inline ExtendedCallbackState* FindExtendedCallback(CallbackId id) noexcept {
    if(id<1000)return nullptr;
    std::size_t first{}, last=g_ExtendedCallbackCount;
    while (first<last) {
        const auto middle=first+(last-first)/2;
        if (g_ExtendedCallbacks[middle].id<id) first=middle+1;
        else last=middle;
    }
    return first<g_ExtendedCallbackCount&&g_ExtendedCallbacks[first].id==id
        ? &g_ExtendedCallbacks[first] : nullptr;
}

inline bool ExtendedCallbackEnabled(CallbackId id) noexcept {
    if(!g_ExtendedCallbackDelivery||!g_ExtendedCallbackEnabledCount)return false;
    const auto* entry=FindExtendedCallback(id);
    return entry&&entry->enabled;
}
inline std::size_t ExtendedCallbackCount() noexcept { return g_ExtendedCallbackCount; }
inline CallbackId ExtendedCallbackAt(std::size_t index) noexcept {
    return index<g_ExtendedCallbackCount ? g_ExtendedCallbacks[index].id : ~CallbackId{};
}
inline std::uint32_t ExtendedCallbackRegistrationCount(CallbackId id) noexcept {
    const auto* entry=FindExtendedCallback(id); return entry ? entry->registrations : 0;
}
inline std::uint32_t ExtendedCallbackDispatchCount(CallbackId id) noexcept {
    const auto* entry=FindExtendedCallback(id); return entry ? entry->dispatches : 0;
}
inline void ResetExtendedCallbackState() noexcept {
    g_ExtendedCallbackEnabledCount=0;
    for (std::size_t i=0;i<g_ExtendedCallbackCount;++i) {
        g_ExtendedCallbacks[i].enabled=false;
        g_ExtendedCallbacks[i].registrations=0;
    }
}
inline void ResetExtendedCallbackDispatchCounts() noexcept {
    for (std::size_t i=0;i<g_ExtendedCallbackCount;++i) g_ExtendedCallbacks[i].dispatches=0;
}

} // namespace isaac::runtime
