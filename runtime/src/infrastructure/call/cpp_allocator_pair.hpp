#pragma once
#include "infrastructure/memory/engine_field_access.hpp"
#include <array>
#include <cstdint>
namespace isaac::runtime::engine_call {
namespace allocator_pair_detail {
inline bool BranchTarget(std::uintptr_t pc,std::uint32_t word,bool link,std::uintptr_t*target) noexcept {
    if((word&0xfc000000U)!=(link?0x94000000U:0x14000000U))return false;
    const auto imm=static_cast<std::int64_t>(static_cast<std::int32_t>(word<<6))>>4;
    if(imm<0){const auto delta=static_cast<std::uint64_t>(-imm);if(pc<delta)return false;*target=pc-delta;}
    else{const auto delta=static_cast<std::uint64_t>(imm);if(pc>UINTPTR_MAX-delta)return false;*target=pc+delta;}
    return true;
}
inline std::uintptr_t PltTarget(std::uintptr_t pc,engine_memory::ReadableCheck readable) noexcept {
    std::array<std::uint32_t,4> words{};
    if(!engine_memory::ReadAt(pc,&words,readable)||(words[0]&0x9f00001fU)!=0x90000010U||
       (words[1]&0xffc003ffU)!=0xf9400211U||(words[2]&0xffc003ffU)!=0x91000210U||
       words[3]!=0xd61f0220U)return 0;
    const auto loadOffset=static_cast<std::uint64_t>((words[1]>>10)&0xfffU)*8;
    if(loadOffset!=((words[2]>>10)&0xfffU))return 0;
    const std::uint32_t bits=(((words[0]>>5)&0x7ffffU)<<2)|((words[0]>>29)&3U);
    const auto pages=static_cast<std::int64_t>(static_cast<std::int32_t>(bits<<11))>>11;
    const auto page=pc&~std::uintptr_t{0xfff};std::uintptr_t got{};
    if(pages<0){const auto delta=static_cast<std::uint64_t>(-pages)*4096;if(page<delta)return 0;got=page-delta;}
    else{const auto delta=static_cast<std::uint64_t>(pages)*4096;if(page>UINTPTR_MAX-delta)return 0;got=page+delta;}
    if(got>UINTPTR_MAX-loadOffset)return 0;
    std::uintptr_t target{};return engine_memory::ReadAt(got+loadOffset,&target,readable)?target:0;
}
}
// 固定SDK的operator new调用malloc，delete尾跳free；核实际导入目标相同后才允许
// 以nonthrow malloc分配交给C++容器、以后由该delete释放的缓冲。无分配或内核调用。
inline bool CppAllocatorPairMatches(std::uintptr_t newEntry,std::uintptr_t deleteEntry,
        std::uintptr_t mallocEntry,std::uintptr_t freeEntry,
        engine_memory::ReadableCheck readable) noexcept {
    if(!newEntry||!deleteEntry||!mallocEntry||!freeEntry||newEntry>UINTPTR_MAX-28)return false;
    constexpr std::array<std::uint32_t,6> prefix={0xa9be7bfdU,0xf9000bf3U,0x910003fdU,0xf100001fU,0x9a9f1413U,0xaa1303e0U};
    std::array<std::uint32_t,7> code{};std::uint32_t deletion{};
    if(!engine_memory::ReadAt(newEntry,&code,readable)||!engine_memory::ReadAt(deleteEntry,&deletion,readable))return false;
    for(unsigned i=0;i<prefix.size();++i)if(code[i]!=prefix[i])return false;
    std::uintptr_t allocateStub{},freeStub{};
    return allocator_pair_detail::BranchTarget(newEntry+24,code[6],true,&allocateStub)&&
        allocator_pair_detail::BranchTarget(deleteEntry,deletion,false,&freeStub)&&
        allocator_pair_detail::PltTarget(allocateStub,readable)==mallocEntry&&
        allocator_pair_detail::PltTarget(freeStub,readable)==freeEntry;
}
}
