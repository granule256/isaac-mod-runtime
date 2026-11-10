#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime {

// A caller supplies individually verified readable mappings. Gaps and adjacent
// unrelated executable mappings never become part of a trusted module span.
struct SdkImage {
    struct Range { std::uintptr_t start{}; std::size_t size{}; bool executable{}; };
    std::uintptr_t base{};
    Range ranges[8]{};
    std::size_t count{};

    bool Contains(std::uintptr_t p, std::size_t n, bool execute = false) const noexcept {
        for (std::size_t i = 0; i < count && i < 8; ++i) {
            const auto& r = ranges[i];
            if ((!execute || r.executable) && p >= r.start &&
                p - r.start <= r.size && n <= r.size - (p - r.start)) return true;
        }
        return false;
    }

    template<class T> bool Read(std::uintptr_t p, T* out) const noexcept {
        if (!Contains(p, sizeof(T))) return false;
        std::memcpy(out, reinterpret_cast<const void*>(p), sizeof(T));
        return true;
    }

    bool Parse() noexcept {
        strings_ = symbols_ = 0; stringBytes_ = symbolCount_ = 0;
        std::uint32_t mod{}, magic{};
        std::int32_t offset{};
        if (!base || !Read(base + 4, &mod) || mod > 0x100000 ||
            base > UINTPTR_MAX - mod - 8 || !Read(base + mod, &magic) ||
            magic != 0x30444f4d || !Read(base + mod + 4, &offset)) return false;
        const auto delta = static_cast<std::int64_t>(mod) + offset;
        if (delta < 0 || static_cast<std::uint64_t>(delta) > UINTPTR_MAX - base) return false;
        const auto dynamic = base + static_cast<std::uintptr_t>(delta);
        std::uint64_t rawStrings{}, rawSymbols{}, rawHash{}, rawGnu{}, entrySize{};
        bool ended = false;
        for (unsigned i = 0; i < 256; ++i) {
            std::uint64_t tag{}, value{};
            if (dynamic > UINTPTR_MAX - i * 16 - 8 ||
                !Read(dynamic + i * 16, &tag) || !Read(dynamic + i * 16 + 8, &value)) return false;
            if (!tag) { ended = true; break; }
            if (tag == 4) rawHash = value;
            if (tag == 5) rawStrings = value;
            if (tag == 6) rawSymbols = value;
            if (tag == 10) stringBytes_ = value;
            if (tag == 11) entrySize = value;
            if (tag == 0x6ffffef5) rawGnu = value;
        }
        strings_ = Address(rawStrings); symbols_ = Address(rawSymbols);
        if (!ended || entrySize != 24 || !stringBytes_ || stringBytes_ > 0x1000000 ||
            !Contains(strings_, stringBytes_) || !Contains(symbols_, 24)) return false;
        const auto hash = Address(rawHash);
        if (rawHash) {
            std::uint32_t buckets{}, chains{};
            if (!hash || !Read(hash, &buckets) || !Read(hash + 4, &chains) || !buckets ||
                buckets > 0x100000 || !chains || chains > 0x100000 ||
                !Contains(hash, (static_cast<std::size_t>(buckets) + chains + 2) * 4)) return false;
            symbolCount_ = chains;
        } else {
            const auto gnu = Address(rawGnu);
            std::uint32_t buckets{}, first{}, bloom{}, shift{};
            if (!rawGnu || !gnu || !Read(gnu, &buckets) || !Read(gnu + 4, &first) ||
                !Read(gnu + 8, &bloom) || !Read(gnu + 12, &shift) || !buckets ||
                buckets > 0x100000 || !bloom || bloom > 0x100000 ||
                (bloom & (bloom - 1)) || shift >= 32 || first > 0x100000) return false;
            const auto table = gnu + 16 + static_cast<std::size_t>(bloom) * 8;
            const auto chains = table + static_cast<std::size_t>(buckets) * 4;
            if (!Contains(gnu, 16 + static_cast<std::size_t>(bloom) * 8) ||
                !Contains(table, static_cast<std::size_t>(buckets) * 4)) return false;
            std::uint32_t last{};
            for (unsigned i = 0; i < buckets; ++i) {
                std::uint32_t bucket{};
                if (!Read(table + i * 4, &bucket) ||
                    (bucket && (bucket < first || bucket >= 0x100000))) return false;
                if (bucket > last) last = bucket;
            }
            symbolCount_ = first;
            if (last) {
                bool terminated = false;
                for (unsigned i = last; i < 0x100000; ++i) {
                    std::uint32_t chain{};
                    if (!Read(chains + static_cast<std::size_t>(i - first) * 4, &chain)) return false;
                    if (chain & 1) { symbolCount_ = i + 1; terminated = true; break; }
                }
                if (!terminated) return false;
            }
        }
        return symbolCount_ && Contains(symbols_, symbolCount_ * 24);
    }

    std::uintptr_t FindFunction(const char* name) const noexcept {
        if (!name || !symbolCount_ || !Contains(symbols_, symbolCount_ * 24)) return 0;
        const auto length = std::strlen(name);
        for (std::size_t i = 1; i < symbolCount_; ++i) {
            const auto record = symbols_ + i * 24;
            std::uint32_t n{}; std::uint16_t section{}; std::uint8_t info{}; std::uint64_t value{};
            if (!Read(record, &n) || !Read(record + 4, &info) || !Read(record + 6, &section) ||
                !Read(record + 8, &value)) return 0;
            if (!section || (info & 15) != 2 || ((info >> 4) != 1 && (info >> 4) != 2) ||
                n >= stringBytes_ || length >= stringBytes_ - n || !value ||
                value > UINTPTR_MAX - base) continue;
            if (!Contains(base + value, 4, true)) continue;
            if (std::memcmp(reinterpret_cast<const void*>(strings_ + n), name, length + 1) == 0)
                return base + value;
        }
        return 0;
    }

    static bool ImportTargetAllowed(std::uintptr_t actual, std::uintptr_t resolved,
                                    std::uintptr_t verifiedResolver) noexcept {
        return actual && resolved && (actual == resolved || (verifiedResolver && actual == verifiedResolver));
    }

    static std::uintptr_t ImportSlot(std::uintptr_t pc, const std::uint32_t* code) noexcept {
        if (!code || (code[0] & 0x9f00001f) != 0x90000010 ||
            (code[1] & 0xffc003ff) != 0xf9400211 ||
            (code[2] & 0xffc003ff) != 0x91000210 || code[3] != 0xd61f0220) return 0;
        std::int64_t pages = ((code[0] >> 5) & 0x7ffff) << 2 | ((code[0] >> 29) & 3);
        if (pages & 0x100000) pages -= 0x200000;
        const auto page = static_cast<std::int64_t>(pc & ~std::uintptr_t{0xfff}) + pages * 4096;
        const auto load = ((code[1] >> 10) & 0xfff) * 8;
        const auto add = (code[2] >> 10) & 0xfff;
        if (page < 0 || load != add || static_cast<std::uint64_t>(page) > UINTPTR_MAX - load) return 0;
        return static_cast<std::uintptr_t>(page) + load;
    }

private:
    std::uintptr_t Address(std::uint64_t value) const noexcept {
        if (!value) return 0;
        if (Contains(value, 1)) return value;
        return value <= UINTPTR_MAX - base && Contains(base + value, 1) ? base + value : 0;
    }
    std::uintptr_t strings_{}, symbols_{};
    std::size_t stringBytes_{}, symbolCount_{};
};

} // namespace isaac::runtime
