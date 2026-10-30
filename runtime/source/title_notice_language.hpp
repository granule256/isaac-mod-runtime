#pragma once
#include <cstdint>

namespace isaac::runtime::notice {
inline constexpr unsigned kNoLanguage = UINT32_MAX;
inline constexpr char kNoticeLanguages[][3] = {"en", "de", "es", "fr", "jp", "kr", "ru", "zh"};

constexpr unsigned LanguageIndex(const char* code) noexcept {
    if (!code || !code[0] || !code[1]) return 0;
    const char first = code[0], second = code[1];
    if (first == 'j' && second == 'a') return 4;
    if (first == 'k' && second == 'o') return 5;
    for (unsigned i = 0; i < 8; ++i)
        if (first == kNoticeLanguages[i][0] && second == kNoticeLanguages[i][1]) return i;
    return 0;
}

// The exact native lifecycle is shared with the host harness. Only one locale
// is alive: destroy the old objects before allocating the next atlas, and clean
// partially loaded objects on failure. Idle frames perform one index comparison.
struct ResourceCycle {
    static constexpr unsigned kSprites = 5;
    unsigned language{kNoLanguage}, failedLanguage{kNoLanguage}, constructed{}, generation{};

    template<class Operations>
    void Release(Operations& operations) noexcept {
        while (constructed) operations.Destroy(--constructed);
        language = kNoLanguage;
    }

    template<class Operations>
    bool Select(unsigned wanted, Operations& operations) noexcept {
        if (language == wanted) return true;
        if (failedLanguage == wanted || !operations.BindingsReady()) return false;
        Release(operations);
        operations.AssignPath(wanted);
        for (unsigned i = 0; i < kSprites; ++i) {
            operations.Construct(i);
            ++constructed;
            if (!operations.Load(i)) {
                Release(operations);
                failedLanguage = wanted;
                return false;
            }
        }
        language = wanted;
        failedLanguage = kNoLanguage;
        ++generation;
        return true;
    }
};
}
