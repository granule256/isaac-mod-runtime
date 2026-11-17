#pragma once

#include "infrastructure/console/console_bridge.hpp"

namespace isaac::runtime::console {

// Console+0x80 is deque<string> (24 bytes, 170 entries/block). The output
// history at +0x50 instead contains 48-byte HistoryEntry objects.
struct CommandHistoryView {
    std::uintptr_t map{};
    std::uint64_t start{}, count{};
};

inline bool ReadCommandHistoryView(const void* object, CommandHistoryView* out) noexcept {
    if (!object || !out) return false;
    CommandHistoryView view{};
    std::uintptr_t end{};
    const auto address=engine_memory::AddressOf(object);
    const auto readable=&engine_memory::EngineMemoryReadable;
    if (!engine_memory::ReadField(address,0x88,&view.map,readable) ||
        !engine_memory::ReadField(address,0x90,&end,readable) ||
        !engine_memory::ReadField(address,0xa0,&view.start,readable) ||
        !engine_memory::ReadField(address,0xa8,&view.count,readable)) return false;
    if (view.count && (!view.map || end<view.map ||
        (end-view.map)%sizeof(std::uintptr_t) || view.start>UINT64_MAX-view.count ||
        (view.start+view.count-1)/170>=(end-view.map)/sizeof(std::uintptr_t))) return false;
    *out=view;
    return true;
}

inline bool CopyCommandHistoryEntry(const CommandHistoryView& view,std::uint64_t index,
                                    char* out,std::size_t capacity) noexcept {
    if (!out || !capacity || index>=view.count || view.start>UINT64_MAX-index) return false;
    const auto position=view.start+index;
    std::uintptr_t block{};
    const auto readable=&engine_memory::EngineMemoryReadable;
    if (!engine_memory::ReadField(view.map,(position/170)*sizeof(block),&block,readable) ||
        !block) return false;
    std::array<unsigned char,kEngineStringBytes> header{};
    if (!engine_memory::ReadField(block,(position%170)*kEngineStringBytes,&header,readable))
        return false;
    const auto length=EngineStringSize(header.data());
    if (length>=capacity || (!EngineStringIsLong(header.data()) && length>kCommandInlineCapacity))
        return false;
    const auto* text=EngineStringData(header.data());
    if (length && (!text || !readable(engine_memory::AddressOf(text),length))) return false;
    if (length) std::memcpy(out,text,length);
    out[length]=0;
    return std::memchr(out,0,length)==nullptr;
}

} // namespace isaac::runtime::console
