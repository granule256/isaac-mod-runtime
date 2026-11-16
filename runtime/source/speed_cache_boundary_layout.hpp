#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
namespace isaac::runtime::speed_cache_boundary {
inline constexpr std::array<std::uint8_t,32> kBuildId={0x91,0xC7,0x3F,0xDD,0x57,0x50,0x61,0x31,0x8D,0x68,0x88,0x63,0x16,0xAF,0xEA,0xC7,0x23,0x88,0xB2,0xAB,0,0,0,0,0,0,0,0,0,0,0,0};
// Fixed NRO dynamic symbol Entity_Player::EvaluateItems, including its cold tails.
inline constexpr std::uintptr_t kFunction=0x280804,kLength=0xC684;
inline constexpr std::uint64_t kFunctionHash=0xC00B3E9D53B78DFCULL;
// The cold active max charge relay changes only the instruction at 0x280d0c.
inline constexpr std::uint64_t kFunctionHashWithActiveMaxCharge=0xA7AD6FD2822A542AULL;
inline constexpr std::uintptr_t kSource=0x2857A8,kGate=0x68CF40;
inline constexpr std::uint32_t kOriginal=0x394002A8U;
constexpr std::uint32_t Branch(std::uintptr_t from,std::uintptr_t to) noexcept {
 return 0x14000000U|(static_cast<std::uint32_t>(static_cast<std::int64_t>(to)-static_cast<std::int64_t>(from))/4U&0x3FFFFFFU);
}
inline bool ImageMatches(const std::uint8_t* image,std::size_t size) noexcept {
 if(!image||size<kGate+32||size<kFunction+kLength||
    std::memcmp(image+0x40,kBuildId.data(),kBuildId.size()))return false;
 std::uint32_t source{};std::memcpy(&source,image+kSource,4);
 const std::array<std::uint32_t,6> gate={0x100000D0U,0xC8DFFE10U,0xB4000050U,0xD61F0200U,
    kOriginal,Branch(kGate+20,kSource+4)};
 if(source!=Branch(kSource,kGate)||std::memcmp(image+kGate,gate.data(),24))return false;
 std::uint64_t hash=14695981039346656037ULL;
 for(std::uintptr_t at=kFunction;at<kFunction+kLength;++at){
  const auto byte=at>=kSource&&at<kSource+4
      ?static_cast<std::uint8_t>(kOriginal>>((at-kSource)*8)):image[at];
  hash=(hash^byte)*1099511628211ULL;
 }
 return hash==kFunctionHash||hash==kFunctionHashWithActiveMaxCharge;
}
// PC 0x734511 dispatches CACHE_SPEED before its later 0.1..2 clamp. NS resumes
// at 0x2857AC (tear-flag test), reaching the native clamp at 0x28BE64..0x28BE8C.
// x16 has no read on either successor before a PLT clobbers it; the next inline
// x16 use (0x289CEC) first defines it with MOV x16,x13. x21 is the live cache mask.
}
