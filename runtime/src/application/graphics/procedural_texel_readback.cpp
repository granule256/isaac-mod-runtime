#include "application/graphics/procedural_texel_readback.hpp"
#include <limits>
namespace isaac::runtime {
ProceduralTexelResult PrepareProceduralItemReadback(
 std::uintptr_t manager,const ProceduralTexelBackend& backend) noexcept {
 ProceduralTexelResult result{};
 if(!backend.read||!backend.enable||!manager){result.failed=2;return result;}
 constexpr std::uintptr_t offsets[]{0x18,0x28};
 constexpr std::uint32_t dimensions[]{1024,512};
 for(unsigned i=0;i<2;++i){
  std::uintptr_t image{};std::uint64_t flags{};std::uint32_t width{},height{};
  if(manager>UINTPTR_MAX-offsets[i]||!backend.read(manager+offsets[i],&image,sizeof(image))){++result.failed;continue;}
  if(!image)continue; // Legal empty lifecycle state; do not invent a replacement image.
  if(image>UINTPTR_MAX-0x610||!backend.read(image+0x10,&flags,sizeof(flags))||
     !backend.read(image+0x51c,&width,sizeof(width))||!backend.read(image+0x520,&height,sizeof(height))||
     width!=dimensions[i]||height!=dimensions[i]||(flags&2U)==0){++result.failed;continue;}
  if((flags&0x10000U)==0){backend.enable(image,true);++result.enabled;}
  std::uintptr_t pixels{};
  if(!backend.read(image+0x10,&flags,sizeof(flags))||!backend.read(image+0x608,&pixels,sizeof(pixels))||
     (flags&0x10000U)==0||!pixels)++result.failed;
 }
 return result;
}
}
