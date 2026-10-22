#pragma once
#include <cstdint>
namespace isaac::runtime {
struct UseItemCallbackResult {
    bool hasDischarge{};bool discharge{};
    bool hasRemove{};bool remove{};
    bool showAnimation{};
    // control_active_item @2CA438..47C消费low bit放电、bit8移除，保留其它原生位。
    constexpr std::uint64_t Apply(std::uint64_t native)const noexcept{
        if(hasDischarge)native=(native&~std::uint64_t{1})|static_cast<std::uint64_t>(discharge);
        if(hasRemove)native=(native&~std::uint64_t{0x100})|(static_cast<std::uint64_t>(remove)<<8);
        return native;
    }
};
}
