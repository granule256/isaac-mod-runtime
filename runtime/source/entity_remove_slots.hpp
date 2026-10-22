#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
namespace isaac::runtime {
inline constexpr std::array<std::uintptr_t,11> kEntityRemovePointerOffsets={
    0xA34FB0,0xA350A0,0xA35198,0xA35290,0xA35BA0,0xA37168,
    0xA37468,0xA37560,0xA37690,0xA37788,0xA9F910,
};
struct EntityPointerIo {
    void* context{};
    std::uintptr_t (*load)(const void*,std::uintptr_t){};
    bool (*compareExchange)(void*,std::uintptr_t,std::uintptr_t,std::uintptr_t){};
};
enum class EntityPointerFailure {None,InvalidPlan,GuardMismatch,WriteFailed,RollbackFailed};
inline EntityPointerFailure InstallEntityPointerPlan(const EntityPointerIo& io,
    const std::array<std::uintptr_t,11>& sites,const std::array<std::uintptr_t,11>& originals,
    std::uintptr_t callback) noexcept {
    if (io.load==nullptr || io.compareExchange==nullptr || callback==0) return EntityPointerFailure::InvalidPlan;
    for (std::size_t i=0;i<sites.size();++i)
        if (io.load(io.context,sites[i])!=originals[i]) return EntityPointerFailure::GuardMismatch;
    std::size_t committed=0;
    for (std::size_t i=0;i<sites.size();++i) {
        const bool swapped=io.compareExchange(io.context,sites[i],originals[i],callback);
        if (swapped) ++committed;
        if (!swapped || io.load(io.context,sites[i])!=callback) {
            bool restored=true;
            while (committed!=0) {
                --committed;
                // 只恢复自己的callback值；陌生并发写入保留且报告回滚失败。
                const bool changed=io.compareExchange(io.context,sites[committed],callback,originals[committed]);
                if (!changed || io.load(io.context,sites[committed])!=originals[committed]) restored=false;
            }
            return restored?EntityPointerFailure::WriteFailed:EntityPointerFailure::RollbackFailed;
        }
    }
    return EntityPointerFailure::None;
}
}
