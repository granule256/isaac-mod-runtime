#pragma once
#include <atomic>
#include <cstdint>

struct TargetModule;

namespace isaac::runtime::notice::integrity {
// Only the game thread performs reads. Consumers use one published state load.
inline constexpr unsigned kUnchecked = 0, kChecking = 1, kValid = 2, kBlocked = 3;
#if defined(__SWITCH__) && !defined(EXL_DIAGNOSTIC_STAGE) && !defined(EXL_STARTUP_PROBE_STAGE)
extern std::atomic<unsigned> g_ValidationState;
inline bool RuntimeAllowed() noexcept {
    return g_ValidationState.load(std::memory_order_acquire) == kValid;
}
inline bool Blocked() noexcept {
    return g_ValidationState.load(std::memory_order_acquire) == kBlocked;
}
bool Ensure(const TargetModule&) noexcept;
bool VerifyLocale(unsigned language) noexcept;
#else
inline bool RuntimeAllowed() noexcept { return true; }
inline bool Blocked() noexcept { return false; }
inline bool Ensure(const TargetModule&) noexcept { return true; }
inline bool VerifyLocale(unsigned) noexcept { return true; }
#endif

// This namespace belongs to the runtime rather than PC mod resource overrides.
// Fold the same ASCII case and separators as the existing redirect resolver.
inline bool IsOwnedNoticePath(const char* path) noexcept {
    if (!path) return false;
    const auto canonical = [](unsigned char value) {
        if (value == '\\') value = '/';
        if (value >= 'A' && value <= 'Z') value += 'a' - 'A';
        return value;
    };
    const auto consume = [&](const char* text) {
        const char* cursor = path;
        while (*text) {
            if (!*cursor || canonical(static_cast<unsigned char>(*cursor)) != static_cast<unsigned char>(*text))
                return false;
            ++cursor; ++text;
        }
        path = cursor;
        return true;
    };
    consume("rom:/");
    consume("rp_patch/");
    if (consume("resources")) {
        if (*path == '.') {
            if (!path[1] || !path[2] || canonical(static_cast<unsigned char>(path[3])) != '/') return false;
            path += 3;
        }
        if (!consume("/")) return false;
    }
    constexpr char prefix[] = "gfx/ui/main menu/isaac-switch/nnotice";
    for (unsigned i = 0; i < sizeof(prefix) - 1; ++i) {
        const unsigned char value = canonical(static_cast<unsigned char>(path[i]));
        if (!value) return false;
        if (value != static_cast<unsigned char>(prefix[i])) return false;
    }
    const char after = path[sizeof(prefix) - 1];
    return after == '_' || after == '.';
}
}

// state/failure/entry/check-count/bytes-low/bytes-high/micros-low/package-runs/
// locale-runs/last-fs-result/last-fs-operation/manifest-count/micros-high/
// blocked-load-attempts/error-frames/reserved.
extern "C" std::uint32_t g_NoticeIntegrityState[16];
