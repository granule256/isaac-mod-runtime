#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
namespace isaac::runtime::use_item_boundary {
inline constexpr std::array<std::uint8_t,32> kBuildId={0x91,0xC7,0x3F,0xDD,0x57,0x50,0x61,0x31,0x8D,0x68,0x88,0x63,0x16,0xAF,0xEA,0xC7,0x23,0x88,0xB2,0xAB,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00};
struct Site {std::uintptr_t source,gate;std::uint32_t original;bool defaultDischarge;};
inline constexpr std::array<Site,5> kSites={{{0x30A19C,0x68CE60,0xB9595B69U,false},
 {0x30C728,0x68CE80,0xB9595B69U,false},{0x317318,0x68CEA0,0xB9595B69U,false},
 {0x31A80C,0x68CEC0,0xB94056E8U,true},{0x31A92C,0x68CEE0,0xB94056E8U,true}}};
// 原生BL的唯一续接点：Tammy激光、Flip替身；完整函数先核同才可热替换。
struct AnimationSite { std::uintptr_t source,veneer,plt; std::uint32_t original; std::array<std::uint8_t,16> pltGuard; };
inline constexpr std::array<AnimationSite,2> kAnimationSites={{{0x30EBB4,0x68CE00,0x672020,0x940D8D1BU,
    {0x70,0x21,0x00,0x90,0x11,0xBE,0x47,0xF9,0x10,0xE2,0x3D,0x91,0x20,0x02,0x1F,0xD6}},
    {0x30C5F4,0x68CE10,0x678870,0x940DB09FU,
    {0x50,0x21,0x00,0xD0,0x11,0xD2,0x41,0xF9,0x10,0x82,0x0E,0x91,0x20,0x02,0x1F,0xD6}}}};
inline constexpr std::uintptr_t kFunction=0x30653C,kLength=0x155D8;
inline constexpr std::uint64_t kFunctionHash=0x3C68692122942AACULL;
constexpr std::uint32_t Branch(std::uintptr_t from,std::uintptr_t to)noexcept{
 return 0x14000000U|(static_cast<std::uint32_t>(static_cast<std::int64_t>(to)-static_cast<std::int64_t>(from))/4U&0x3FFFFFFU);
}
inline bool ImageMatches(const std::uint8_t* image,std::size_t size)noexcept{
 if(!image||size<kFunction+kLength||size<0x68CF00||std::memcmp(image+0x40,kBuildId.data(),kBuildId.size()))return false;
 for(const auto& site:kSites){
  std::uint32_t actual{};std::memcpy(&actual,image+site.source,4);
  const std::array<std::uint32_t,6> gate={0x100000D0U,0xC8DFFE10U,0xB4000050U,0xD61F0200U,
      site.original,Branch(site.gate+20,site.source+4)};
  if(actual!=Branch(site.source,site.gate)||std::memcmp(image+site.gate,gate.data(),24))return false;
 }
 const std::array<std::uint8_t,16> empty{};
 for(const auto& site:kAnimationSites){
  std::uint32_t actual{};std::memcpy(&actual,image+site.source,4);
  if(actual!=site.original || std::memcmp(image+site.veneer,empty.data(),16) ||
     std::memcmp(image+site.plt,site.pltGuard.data(),16))return false;
 }
 std::uint64_t hash=14695981039346656037ULL;std::size_t next{};
 for(std::uintptr_t at=kFunction;at<kFunction+kLength;){
  if(next<kSites.size()&&at==kSites[next].source){
   const auto word=kSites[next++].original;
   for(unsigned i=0;i<4;++i)hash=(hash^static_cast<std::uint8_t>(word>>(i*8)))*1099511628211ULL;
   at+=4;
  }else hash=(hash^image[at++])*1099511628211ULL;
 }
 return hash==kFunctionHash;
}
}
