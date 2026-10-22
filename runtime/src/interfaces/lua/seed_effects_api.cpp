#include "interfaces/lua/seed_effects_api.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr std::uint8_t kAllocateGuard[16]={0x70,0x21,0x0,0xd0,0x11,0x82,0x46,0xf9,0x10,0x2,0x34,0x91,0x20,0x2,0x1f,0xd6};
constexpr std::uint8_t kReleaseGuard[16]={0x70,0x21,0x0,0xd0,0x11,0x7a,0x46,0xf9,0x10,0xc2,0x33,0x91,0x20,0x2,0x1f,0xd6};
constexpr std::uint8_t kBalanceGuard[16]={0x3f,0x0,0x0,0xeb,0xe8,0x17,0x9f,0x1a,0x28,0x60,0x0,0x39,0x80,0x5,0x0,0x54};
constexpr std::uint8_t kRemoveGuard[16]={0x29,0x0,0x40,0xf9,0xea,0x3,0x1,0xaa,0xc9,0x0,0x0,0xb4,0x28,0x4,0x40,0xf9};
constexpr api100_native::Entry kEntries[]={
{0x66fb30,kAllocateGuard},{0x66fb10,kReleaseGuard},
{0x18a20,kBalanceGuard},{0x18620,kRemoveGuard}};
api100_native::Cache g_Caches[4]{};
#if !defined(__SWITCH__)
seed_effects::Bindings g_Host{};
#endif
bool Accessible(const void* p,std::size_t n){
 const auto a=engine_memory::AddressOf(p);
 return engine_memory::EngineMemoryReadable(a,n)&&engine_memory::EngineMemoryWritable(a,n);
}
}
#if !defined(__SWITCH__)
void SetSeedEffectNativeTestBindings(seed_effects::Bindings b)noexcept{g_Host=b;}
#endif
int MutateSeedEffect(lua_State* state,std::uintptr_t game,std::int32_t effect,bool add){
 if(!game)return 0;
 const auto address=engine_memory::FieldAddress(game,kGameSeedsObjectOffset+kSeedsEffectTreeOffset,
     sizeof(seed_effects::Tree),alignof(std::uintptr_t),engine_memory::EngineMemoryReadable);
 if(!address||!engine_memory::EngineMemoryWritable(address,sizeof(seed_effects::Tree)))
     return luaL_error(state,"seed effect tree unavailable");
 seed_effects::Bindings b{};
#if !defined(__SWITCH__)
 b=g_Host;
#endif
 const auto resolve=[&](unsigned index,auto function){
  return engine_call::AsFunction<decltype(function)>(api100_native::Resolve(
   state,kEntries[index],g_Caches[index],engine_call::AddressOfFunction(function)));
 };
 b.allocate=resolve(0,b.allocate);b.release=resolve(1,b.release);
 b.balance=resolve(2,b.balance);b.remove=resolve(3,b.remove);
 auto& tree=*static_cast<seed_effects::Tree*>(engine_memory::AsObject(address));
 if(!seed_effects::Write(tree,effect,add,b,Accessible))return luaL_error(state,"seed effect tree mutation failed");
 return 0;
}
}
