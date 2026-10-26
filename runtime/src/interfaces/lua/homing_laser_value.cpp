#include "interfaces/lua/homing_laser_value.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api400_fields.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "infrastructure/call/cpp_allocator_pair.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include <array>
#include <cstring>
#include <limits>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr char kMetatable[]="IsaacRuntime.HomingLaser";
constexpr std::uintptr_t kMember=0x458;
constexpr std::size_t kNativeSize=0x88;
constexpr std::uint64_t kMagic=0x484f4d494e475631ULL;
struct alignas(8) Native {unsigned char bytes[kNativeSize];};
struct Header {std::uintptr_t begin,end,capacity;};
struct Owned {Native value;std::size_t bytes;std::uint64_t magic;};
struct Vector {unsigned offset,stride;};
constexpr Vector kVectors[]={{0x20,8},{0x38,8},{0x50,8},{0x70,24}};
static_assert(sizeof(Native)==kNativeSize && sizeof(Header)==24 && sizeof(Owned)%8==0);
constexpr std::array<std::uint8_t,16> kCtor={253,123,190,169,243,11,0,249,253,3,0,145,243,3,0,170};
constexpr std::array<std::uint8_t,16> kVectorAssign={253,123,187,169,249,11,0,249,253,3,0,145,248,95,2,169};
constexpr std::array<std::uint8_t,16> kBezierAssign={253,123,187,169,250,103,1,169,253,3,0,145,248,95,2,169};
constexpr std::array<std::uint8_t,16> kMalloc={48,33,0,208,17,34,71,249,16,2,57,145,32,2,31,214};
constexpr std::array<std::uint8_t,16> kFree={48,33,0,208,17,22,71,249,16,162,56,145,32,2,31,214};
api100_native::Cache g_LayoutCaches[4]{},g_AllocatorCaches[2]{};
using Allocate=void*(*)(std::size_t);using Release=void(*)(void*);
struct Allocator {Allocate allocate;Release release;};
#if !defined(__SWITCH__)
Allocator g_TestAllocator{};
#endif
std::uintptr_t g_AllocatorBase{};bool g_AllocatorPairValid{};
void Guard(lua_State*L,bool write) {
    static_cast<void>(api100_native::Resolve(L,{api400_fields::kLaserEntry,api400_fields::kLaserGuard.data()},g_LayoutCaches[0]));
    static_cast<void>(api100_native::Resolve(L,{0x399f80,kCtor.data()},g_LayoutCaches[1]));
    if(write){
        // 两种原生assign的固定布局证明元素为可平凡复制的8B/24B；不调用会throw的分配分支。
        static_cast<void>(api100_native::Resolve(L,{0xf5540,kVectorAssign.data()},g_LayoutCaches[2]));
        static_cast<void>(api100_native::Resolve(L,{0xf56ac,kBezierAssign.data()},g_LayoutCaches[3]));
    }
}
Allocator GameAllocator(lua_State*L) {
    const auto base=LuaRuntime::EngineModuleBase();
    const auto allocate=api100_native::Resolve(L,{0x67fdb0,kMalloc.data()},g_AllocatorCaches[0]);
    const auto release=api100_native::Resolve(L,{0x67fd80,kFree.data()},g_AllocatorCaches[1]);
#if !defined(__SWITCH__)
    if(g_TestAllocator.allocate&&g_TestAllocator.release)return g_TestAllocator;
#endif
    if(g_AllocatorBase!=base||!g_AllocatorPairValid){
        g_AllocatorBase=base;std::uintptr_t n{},d{},a{},f{};
        g_AllocatorPairValid=base&&base<=UINTPTR_MAX-0xaa5e48&&
            engine_memory::ReadField(base,0xa9dd00,&n,engine_memory::EngineMemoryReadable)&&
            engine_memory::ReadField(base,0xa9dcf0,&d,engine_memory::EngineMemoryReadable)&&
            engine_memory::ReadField(base,0xaa5e40,&a,engine_memory::EngineMemoryReadable)&&
            engine_memory::ReadField(base,0xaa5e28,&f,engine_memory::EngineMemoryReadable)&&
            engine_call::CppAllocatorPairMatches(n,d,a,f,engine_memory::EngineMemoryReadable);
    }
    if(!g_AllocatorPairValid)luaL_error(L,"HomingLaser game allocator pair does not match this build");
    return {engine_call::AsFunction<Allocate>(allocate),engine_call::AsFunction<Release>(release)};
}
Header GetHeader(const Native&value,unsigned offset) noexcept {Header h{};std::memcpy(&h,value.bytes+offset,sizeof(h));return h;}
void SetHeader(Native*value,unsigned offset,const Header&h) noexcept {std::memcpy(value->bytes+offset,&h,sizeof(h));}
bool ReadNative(std::uintptr_t entity,Native*out) noexcept {
    return entity&&entity<=UINTPTR_MAX-kMember-kNativeSize&&
        engine_memory::ReadField(entity,kMember,out,engine_memory::EngineMemoryReadable);
}
bool VectorBytes(const Header&h,unsigned stride,std::size_t*bytes) noexcept {
    if(h.end<h.begin||h.capacity<h.end||(!h.begin&&(h.end||h.capacity))||
       (h.begin%4)||(h.end-h.begin)%stride||(h.capacity-h.begin)%stride)return false;
    *bytes=static_cast<std::size_t>(h.end-h.begin);
    return !*bytes||engine_memory::EngineMemoryReadable(h.begin,*bytes);
}
std::uintptr_t Identity(lua_State*L,int index) noexcept {
    const auto length=lua_rawlen(L,index);
    if(length<sizeof(Owned))return 0;
    const auto*o=static_cast<const Owned*>(lua_touserdata(L,index));
    if(!o||o->bytes!=length||o->magic!=kMagic)return 0;
    const auto storage=engine_memory::AddressOf(o);std::size_t cursor=sizeof(Owned);
    for(const auto&v:kVectors){
        const auto h=GetHeader(o->value,v.offset);
        if(!h.begin&&!h.end&&!h.capacity)continue;
        if(h.end<h.begin||h.capacity!=h.end||h.begin!=storage+cursor)return 0;
        const auto used=h.end-h.begin;
        if(used%v.stride||used>length-cursor)return 0;
        cursor+=used;
    }
    return cursor==length?storage:0;
}
void Metatable(lua_State*L) {
    if(luaL_newmetatable(L,kMetatable)){
        if(!RegisterNativeObjectIdentity(L,-1,Identity))luaL_error(L,"HomingLaser identity resolver conflicts");
        lua_pushliteral(L,"HomingLaser");lua_setfield(L,-2,"__type");
        lua_pushliteral(L,"HomingLaser");lua_setfield(L,-2,"__name");
        lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");
    }
    lua_pop(L,1);
}
const Owned* CheckOwned(lua_State*L,int index) {
    const auto*o=static_cast<const Owned*>(luaL_checkudata(L,index,kMetatable));
    if(!Identity(L,index))luaL_argerror(L,index,"complete owned HomingLaser value expected");
    return o;
}
}
int PushHomingLaserValue(lua_State*L,std::uintptr_t entity) {
    Guard(L,false);Metatable(L);Native source{};
    if(EntityPointerArgument(L,1)!=entity||!ReadNative(entity,&source))return luaL_error(L,"HomingLaser source is not readable");
    std::size_t lengths[4]{},total=sizeof(Owned);
    for(unsigned i=0;i<4;++i){
        if(!VectorBytes(GetHeader(source,kVectors[i].offset),kVectors[i].stride,&lengths[i])||
           lengths[i]>std::numeric_limits<std::size_t>::max()-total)
            return luaL_error(L,"HomingLaser source vector is invalid");
        total+=lengths[i];
    }
    auto*o=static_cast<Owned*>(lua_newuserdata(L,total));
    // Lua分配可能触发GC；复核真实owner与完整头，不能用分配前的过期借用数组。
    Native current{};
    if(EntityPointerArgument(L,1)!=entity||!ReadNative(entity,&current)||
       std::memcmp(&source,&current,sizeof(source)))return luaL_error(L,"HomingLaser source changed during allocation");
    *o={source,total,kMagic};std::size_t cursor=sizeof(Owned);
    for(unsigned i=0;i<4;++i){
        const auto h=GetHeader(source,kVectors[i].offset);Header copy{};
        if(lengths[i]){
            if(!engine_memory::EngineMemoryReadable(h.begin,lengths[i]))return luaL_error(L,"HomingLaser source vector changed");
            auto*dst=static_cast<unsigned char*>(static_cast<void*>(o))+cursor;
            std::memcpy(dst,engine_memory::AsObject(h.begin),lengths[i]);
            copy.begin=engine_memory::AddressOf(dst);copy.end=copy.capacity=copy.begin+lengths[i];cursor+=lengths[i];
        }
        SetHeader(&o->value,kVectors[i].offset,copy);
    }
    luaL_getmetatable(L,kMetatable);lua_setmetatable(L,-2);return 1;
}
void WriteHomingLaserValue(lua_State*L,std::uintptr_t entity,int index) {
    const auto*source=CheckOwned(L,index);Guard(L,true);Native target{};
    if(!ReadNative(entity,&target)||!engine_memory::EngineMemoryWritable(entity+kMember,kNativeSize))
        luaL_error(L,"HomingLaser target is no longer writable");
    Header before[4]{},after[4]{};std::size_t lengths[4]{};bool grow[4]{};
    for(unsigned i=0;i<4;++i){
        before[i]=GetHeader(target,kVectors[i].offset);const auto input=GetHeader(source->value,kVectors[i].offset);
        std::size_t oldBytes{};
        if(!VectorBytes(before[i],kVectors[i].stride,&oldBytes))luaL_error(L,"HomingLaser target vector is invalid");
        lengths[i]=static_cast<std::size_t>(input.end-input.begin);
        const auto capacity=before[i].capacity-before[i].begin;grow[i]=lengths[i]>capacity;
        if(!grow[i]&&lengths[i]&&!engine_memory::EngineMemoryWritable(before[i].begin,lengths[i]))
            luaL_error(L,"HomingLaser target vector is not writable");
        after[i]=before[i];
    }
    const auto allocator=GameAllocator(L);
    void*created[4]{};
    // 所有可能失败的游戏分配在任何目标写入之前完成。失败先逐件回收再Lua报错。
    for(unsigned i=0;i<4;++i)if(grow[i]){
        created[i]=allocator.allocate(lengths[i]);
        if(!created[i]){
            for(auto*p:created)if(p)allocator.release(p);
            luaL_error(L,"not enough memory for HomingLaser value");return;
        }
        after[i].begin=engine_memory::AddressOf(created[i]);
        after[i].capacity=after[i].begin+lengths[i];
    }
    Native result=source->value;
    for(unsigned i=0;i<4;++i){
        const auto input=GetHeader(source->value,kVectors[i].offset);
        if(lengths[i])std::memcpy(engine_memory::AsObject(after[i].begin),engine_memory::AsObject(input.begin),lengths[i]);
        after[i].end=after[i].begin+lengths[i];SetHeader(&result,kVectors[i].offset,after[i]);
    }
    // 已预检同一游戏线程的完整目标可写性；此后不调用Lua/分配，提交一次完整native值。
    if(!engine_memory::WriteField(entity,kMember,result,engine_memory::EngineMemoryWritable)){
        for(auto*p:created)if(p)allocator.release(p);
        luaL_error(L,"HomingLaser target changed before commit");return;
    }
    for(unsigned i=0;i<4;++i)if(grow[i]&&before[i].begin)allocator.release(engine_memory::AsObject(before[i].begin));
}
#if !defined(__SWITCH__)
void SetHomingLaserAllocatorTestBindings(Allocate allocate,Release release) noexcept {g_TestAllocator={allocate,release};}
#endif
}
