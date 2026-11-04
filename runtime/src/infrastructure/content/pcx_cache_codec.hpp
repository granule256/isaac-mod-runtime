#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime::content {
namespace pcx_cache_detail {
inline constexpr std::size_t kHeader = 128;
struct Layout { std::size_t rows; std::size_t lineBytes; };
struct Span { std::size_t begin; std::size_t size; };

inline bool ReadLayout(const std::uint8_t* data, std::size_t size, Layout* out) noexcept {
    if (!data || size < kHeader || data[0] != 10 || data[2] != 1 ||
        data[3] != 8 || data[65] != 4) return false;
    const auto word = [data](std::size_t at) {
        return unsigned(data[at]) | (unsigned(data[at + 1]) << 8);
    };
    const auto top = word(6), bottom = word(10), lineBytes = word(66);
    if (bottom < top || lineBytes == 0 || word(8) < word(4) ||
        word(8) - word(4) + 1 > lineBytes) return false;
    *out = {std::size_t(bottom - top) + 1, lineBytes};
    return true;
}

inline bool ReadPlane(const std::uint8_t* data, std::size_t size, std::size_t lineBytes,
                      std::size_t* cursor, Span* span) noexcept {
    const auto begin = *cursor;
    std::size_t decoded = 0;
    while (decoded < lineBytes) {
        if (*cursor >= size) return false;
        const auto token = data[(*cursor)++];
        std::size_t count = 1;
        if ((token & 0xc0) == 0xc0) {
            count = token & 0x3f;
            if (!count || *cursor >= size) return false;
            ++*cursor;
        }
        if (count > lineBytes - decoded) return false;
        decoded += count;
    }
    *span = {begin, *cursor - begin};
    return true;
}

inline unsigned Reference(const std::uint8_t* data, const Span* spans, unsigned plane) noexcept {
    for (unsigned previous = 0; previous < plane; ++previous)
        if (spans[plane].size == spans[previous].size &&
            std::memcmp(data + spans[plane].begin, data + spans[previous].begin,
                        spans[plane].size) == 0) return previous;
    return plane;
}
} // namespace pcx_cache_detail

inline std::size_t MeasurePcxCachePlanes(const std::uint8_t* data, std::size_t size) noexcept {
    using namespace pcx_cache_detail;
    Layout layout{};
    if (!ReadLayout(data, size, &layout) || layout.rows > std::size_t(-1) - size) return 0;
    std::size_t source = kHeader, result = kHeader + layout.rows;
    for (std::size_t row = 0; row < layout.rows; ++row) {
        Span planes[4]{};
        for (auto& plane : planes)
            if (!ReadPlane(data, size, layout.lineBytes, &source, &plane)) return 0;
        for (unsigned plane = 0; plane < 4; ++plane)
            if (Reference(data, planes, plane) == plane) result += planes[plane].size;
    }
    return source == size ? result : 0;
}

// Internal cache representation: retain the PCX header and use one byte per row
// to reference identical encoded planes. Input and output must not overlap.
// Unpacking restores the exact original byte stream, including its RLE choices.
inline bool PackPcxCachePlanes(const std::uint8_t* data, std::size_t size,
                               std::uint8_t* output, std::size_t capacity,
                               std::size_t* written) noexcept {
    using namespace pcx_cache_detail;
    if (!written) return false;
    *written = 0;
    Layout layout{};
    if (!output || data == output || capacity < kHeader || !ReadLayout(data, size, &layout))
        return false;
    std::memcpy(output, data, kHeader);
    std::size_t source = kHeader, target = kHeader;
    for (std::size_t row = 0; row < layout.rows; ++row) {
        Span planes[4]{};
        for (auto& plane : planes)
            if (!ReadPlane(data, size, layout.lineBytes, &source, &plane)) return false;
        if (target == capacity) return false;
        const auto flagsAt = target++;
        std::uint8_t flags = 0;
        for (unsigned plane = 0; plane < 4; ++plane) {
            const unsigned reference = Reference(data, planes, plane);
            flags |= static_cast<std::uint8_t>(reference << (plane * 2));
            if (reference != plane) continue;
            if (planes[plane].size > capacity - target) return false;
            std::memcpy(output + target, data + planes[plane].begin, planes[plane].size);
            target += planes[plane].size;
        }
        output[flagsAt] = flags;
    }
    if (source != size) return false;
    *written = target;
    return true;
}

inline bool UnpackPcxCachePlanes(const std::uint8_t* data, std::size_t size,
                                 std::uint8_t* output, std::size_t originalSize) noexcept {
    using namespace pcx_cache_detail;
    Layout layout{};
    if (!output || data == output || originalSize < kHeader || !ReadLayout(data, size, &layout))
        return false;
    std::memcpy(output, data, kHeader);
    std::size_t source = kHeader, target = kHeader;
    for (std::size_t row = 0; row < layout.rows; ++row) {
        if (source == size) return false;
        const auto flags = data[source++];
        Span planes[4]{};
        for (unsigned plane = 0; plane < 4; ++plane) {
            const unsigned reference = (flags >> (plane * 2)) & 3;
            if (reference > plane) return false;
            const std::uint8_t* bytes;
            std::size_t count;
            if (reference == plane) {
                Span input{};
                if (!ReadPlane(data, size, layout.lineBytes, &source, &input)) return false;
                bytes = data + input.begin;
                count = input.size;
            } else {
                bytes = output + planes[reference].begin;
                count = planes[reference].size;
            }
            if (count > originalSize - target) return false;
            std::memcpy(output + target, bytes, count);
            planes[plane] = {target, count};
            target += count;
        }
    }
    return source == size && target == originalSize;
}
} // namespace isaac::runtime::content
