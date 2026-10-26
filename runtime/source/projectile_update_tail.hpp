#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
namespace isaac::runtime::projectile_tail {
// PC 636FAE->7FEC40；NS仅正常完成32744C，两个提前尾跳不经过本处。
// 见docs/剩余全部API测试修复实施计划-20261025.md；void退出边界，临时寄存器均已死。
inline constexpr std::uintptr_t kFunction=0x31F51C,kSize=0x8160,kSite=0x32744C;
inline constexpr std::uintptr_t kGate=0x68CCD0,kSlot=kGate+32;
inline constexpr std::uint32_t kOriginal=0x910603FFU;
inline constexpr std::uint32_t kBranch=0x140d9621U;
inline constexpr std::uint64_t kFunctionHash=0xde22012419af876cULL;
inline constexpr std::array<std::uint32_t,8> kGateWords={0x10000110U,0xc8dffe10U,0xb4000070U,0xaa1c03e0U,0xd63f0200U,0x910603ffU,0x17f269daU,0xd503201fU};
// 初始化尾部同一协议；此处x19仍为this，原LDP在回调后重放。
inline constexpr std::uintptr_t kInitFunction=0x31F154,kInitSize=0x194,kInitSite=0x31F2D8;
inline constexpr std::uintptr_t kInitGate=0x68CE20,kInitSlot=kInitGate+32;
inline constexpr std::uint32_t kInitOriginal=0xA9424FF4U,kInitBranch=0x140db6d2U;
inline constexpr std::uint64_t kInitHash=0xff56082df8f08286ULL;
inline constexpr std::array<std::uint32_t,8> kInitGateWords={0x10000110U,0xc8dffe10U,0xb4000070U,0xaa1303e0U,0xd63f0200U,0xa9424ff4U,0x17f24929U,0xd503201fU};
inline bool ImageMatches(const std::uint8_t* image,std::size_t size,bool initialize=false) noexcept {
 const auto function=initialize?kInitFunction:kFunction,length=initialize?kInitSize:kSize;
 const auto site=initialize?kInitSite:kSite,gate=initialize?kInitGate:kGate,slot=initialize?kInitSlot:kSlot;
 const auto original=initialize?kInitOriginal:kOriginal,branch=initialize?kInitBranch:kBranch;
 const auto& words=initialize?kInitGateWords:kGateWords;
 if(!image||size<function+length||size<slot+8)return false;
 std::uint32_t word{};std::memcpy(&word,image+site,4);
 if(word!=branch||std::memcmp(image+gate,words.data(),32))return false;
 std::uint64_t hash=14695981039346656037ULL;
 // 安装时一次性核完整原生函数；仅本补丁的单条B按原指令归一化，无堆副本。
 for(std::size_t i=0;i<length;++i){
  const auto at=function+i;
  const auto value=at>=site&&at<site+4?static_cast<std::uint8_t>(original>>((at-site)*8)):image[at];
  hash=(hash^value)*1099511628211ULL;
 }
 return hash==(initialize?kInitHash:kFunctionHash);
}
} // namespace isaac::runtime::projectile_tail
