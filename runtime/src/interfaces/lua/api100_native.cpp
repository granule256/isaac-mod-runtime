#include "interfaces/lua/api100_native.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#if defined(__SWITCH__)
#include "interfaces/lua/hooked_engine_entry.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "runtime_constants.hpp"
#endif
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime::api100_native {
__attribute__((noinline)) std::uintptr_t Resolve(lua_State* state,const Entry& entry,
                                                Cache& cache,std::uintptr_t host) {
 const auto base=LuaRuntime::EngineModuleBase();
 if(cache.base!=base||!cache.valid){
  cache.base=base;
  cache.valid=base&&base<=UINTPTR_MAX-entry.offset-16&&
    engine_memory::EngineMemoryReadable(base+entry.offset,16)&&
    !std::memcmp(engine_memory::AsObject(base+entry.offset),entry.guard,16);
#if defined(__SWITCH__)
  // 仅对与入口中继重合的公开API补登记校验；成功缓存热路径不增加工作。
  if(!cache.valid && base && base<=UINTPTR_MAX-entry.offset-16) {
   std::uintptr_t fallback=0;
   if(entry.offset==kApi100ItemPoolGetPillOffset)
    fallback=EntryRelayFallbackEntry(HookId::ItemPoolGetPill);
   else if(entry.offset==kApi200GameEndOffset)
    fallback=EntryRelayFallbackEntry(HookId::GameEnd);
   else if(entry.offset==kApi200GameStartStageTransitionOffset)
    fallback=EntryRelayFallbackEntry(HookId::GameStartStageTransition);
   if(fallback) {
    std::array<std::uint8_t,16> original{};
    std::memcpy(original.data(),entry.guard,original.size());
    cache.valid=VerifiedHookedEngineEntry(base+entry.offset,original,true,fallback,
        &engine_memory::EngineMemoryReadable);
   }
  }
#endif
 }
 if(!cache.valid){luaL_error(state,"api100 native entry guard mismatch");return 0;}
#if !defined(__SWITCH__)
 if(host)return host;
#else
 static_cast<void>(host);
#endif
 return base+entry.offset;
}
}
