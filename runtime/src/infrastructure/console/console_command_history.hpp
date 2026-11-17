#pragma once

#include "infrastructure/console/console_bridge.hpp"
#include <string>

namespace isaac::runtime::console {

// Console+0x80 is deque<string> (24 bytes, 170 entries/block). The output
// history at +0x50 instead contains 48-byte HistoryEntry objects.
struct CommandHistoryView {
    std::uintptr_t map{}, mapEnd{};
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
    view.mapEnd=end;
    *out=view;
    return true;
}

inline bool CommandHistoryOffset(const CommandHistoryView& view,std::uint64_t* out) noexcept {
    if (!out) return false;
    if (!view.count) { *out=0;return true; }
    const auto object=engine_memory::AddressOf(Storage().consoleObject);
    std::uintptr_t map{},cursor{},block{};
    const auto readable=&engine_memory::EngineMemoryReadable;
    if (!engine_memory::ReadField(object,0xb0,&map,readable) ||
        !engine_memory::ReadField(object,0xb8,&cursor,readable) ||
        map<view.map || map>=view.mapEnd || (map-view.map)%8 ||
        !engine_memory::ReadAt(map,&block,readable) || cursor<block ||
        cursor-block>=170*24 || (cursor-block)%24)
        return false;
    const auto position=(map-view.map)/8*170+(cursor-block)/24;
    if (position<view.start || position-view.start>view.count) return false;
    *out=position-view.start;
    return true;
}

inline bool SetCommandHistoryOffset(const CommandHistoryView& view,std::uint64_t offset) noexcept {
    if (offset>view.count || view.start>UINT64_MAX-offset) return false;
    if (!view.count) return offset==0;
    const auto position=view.start+offset;
    const auto map=view.map+(position/170)*8;
    std::uintptr_t block{};
    if (map>=view.mapEnd ||
        !engine_memory::ReadAt(map,&block,&engine_memory::EngineMemoryReadable) || !block ||
        block>UINTPTR_MAX-(position%170)*24) return false;
    const auto cursor=block+(position%170)*24;
    const auto object=engine_memory::AddressOf(Storage().consoleObject);
    return engine_memory::WriteField(object,0xb0,map,&engine_memory::EngineMemoryWritable) &&
           engine_memory::WriteField(object,0xb8,cursor,&engine_memory::EngineMemoryWritable);
}

inline bool ReadCommandHistoryEntry(const CommandHistoryView& view,std::uint64_t index,
                                    std::string* out) noexcept {
    if (!out || index>=view.count || view.start>UINT64_MAX-index) return false;
    const auto position=view.start+index;
    std::uintptr_t block{};
    const auto readable=&engine_memory::EngineMemoryReadable;
    if (!engine_memory::ReadField(view.map,(position/170)*8,&block,readable) || !block) return false;
    std::array<unsigned char,kEngineStringBytes> header{};
    if (!engine_memory::ReadField(block,(position%170)*24,&header,readable)) return false;
    const auto length=EngineStringSize(header.data());
    const auto* text=EngineStringData(header.data());
    if (length>1024*1024 ||
        (!EngineStringIsLong(header.data()) && length>kCommandInlineCapacity) ||
        (length && (!text || !readable(engine_memory::AddressOf(text),length))) ||
        (length && std::memchr(text,0,length))) return false;
    try { out->assign(text,length); } catch (...) { return false; }
    return true;
}

} // namespace isaac::runtime::console
