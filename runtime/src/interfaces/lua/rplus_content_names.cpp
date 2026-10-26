#include "interfaces/lua/rplus_content_names.hpp"
#include "interfaces/lua/rplus_content_names_guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include <array>
#include <cstring>
#include <memory>
#include <new>
#include <type_traits>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace guards=content_names;
enum class Family : std::uint8_t {Pill,Entity};
struct Entry {
    std::uint32_t hash{},offset{},length{},next{};
    std::int32_t type{},variant{},pill{};
    Family family{};std::uint8_t padding[3]{};
};
static_assert(sizeof(Entry)==32);
struct Cache {
    std::uint8_t* memory;
    std::uint32_t* buckets;Entry* entries;char* names;
    std::size_t capacity,count,nameCapacity,nameSize,bucketCount,bytes;
    std::uintptr_t itemRoot,entityRoot;
    bool ready;
};
static_assert(std::is_trivial_v<Cache> && std::is_standard_layout_v<Cache>);
// -nostartfiles：全局必须只需静态零初始化，不注册C++全局析构。
Cache g_Cache{};
bool g_RefreshPending{};
std::uint64_t g_Refreshes{};
#if !defined(__SWITCH__)
bool g_FailAllocation{};
#endif
struct TreeHeader {std::uintptr_t begin{},root{};std::size_t count{};};
struct Links {std::uintptr_t left{},right{},parent{};};
struct EntityPrefix {
    Links links;std::uint64_t colorPadding{};std::uint32_t key{},keyPadding{};
    std::int32_t type{},variant{},subtype{};std::uint32_t valuePadding{};
    std::array<std::uint8_t,24> name{};
};
static_assert(offsetof(EntityPrefix,type)==0x28 && offsetof(EntityPrefix,name)==0x38 && sizeof(EntityPrefix)==0x50);
struct PillPrefix {std::int32_t id{};std::uint32_t padding{};std::array<std::uint8_t,24> name{};};
static_assert(offsetof(PillPrefix,name)==8);
struct Name {std::uintptr_t data{};std::size_t size{};};
struct Roots {std::uintptr_t item{},entity{},pillBegin{},pillEnd{};TreeHeader tree{};};
template<class Value> bool Read(std::uintptr_t address,Value* output) noexcept {
    return engine_memory::ReadAt(address,output,engine_memory::EngineMemoryReadable);
}
template<std::size_t N> bool Guard(std::uintptr_t base,std::uintptr_t offset,const std::array<std::uint8_t,N>& bytes) noexcept {
    return base && base<=UINTPTR_MAX-offset-N && engine_memory::EngineMemoryReadable(base+offset,N) &&
        std::memcmp(engine_memory::AsObject(base+offset),bytes.data(),N)==0;
}
bool LayoutValid() noexcept {
    const auto base=LuaRuntime::EngineModuleBase();
    return Guard(base,guards::kPillVectorEntry,guards::kPillVectorGuard)&&
        Guard(base,guards::kPillNameEntry,guards::kPillNameGuard)&&
        Guard(base,guards::kEntityTreeEntry,guards::kEntityTreeGuard)&&
        Guard(base,guards::kEntityValueEntry,guards::kEntityValueGuard)&&
        Guard(base,guards::kEntityNameEntry,guards::kEntityNameGuard)&&
        Guard(base,guards::kEntitySizeEntry,guards::kEntitySizeGuard)&&
        Guard(base,guards::kEntityIdsEntry,guards::kEntityIdsGuard);
}
bool ReadRoots(Roots* output) noexcept {
    output->item=ResolveContentConfigRoot(false);output->entity=ResolveContentConfigRoot(true);
    if(!output->item||!output->entity||output->item>UINTPTR_MAX-0x68)return false;
    if(!Read(output->item+0x60,&output->pillBegin)||!Read(output->item+0x68,&output->pillEnd)||
       !Read(output->entity,&output->tree))return false;
    if(output->pillEnd<output->pillBegin||((output->pillEnd-output->pillBegin)&7))return false;
    if((output->pillBegin==0)!=(output->pillEnd==0))return false;
    const auto endNode=output->entity+8;
    if(output->tree.count==0)return output->tree.root==0&&(output->tree.begin==endNode||output->tree.begin==0);
    return output->tree.root && output->tree.begin && output->tree.begin!=endNode &&
        output->tree.count<=(SIZE_MAX-4)/4;
}
bool StringView(const std::array<std::uint8_t,24>& storage,std::uintptr_t object,Name* out) noexcept {
    if((storage[0]&1)==0){out->size=storage[0]>>1;
        if(out->size>22||object>UINTPTR_MAX-1)return false;
        out->data=object+1;
    }else{std::memcpy(&out->size,storage.data()+8,8);std::memcpy(&out->data,storage.data()+16,8);}
    return out->size<=UINT32_MAX && (out->size==0||engine_memory::EngineMemoryReadable(out->data,out->size));
}
bool NextNode(std::uintptr_t node,const Links& links,std::uintptr_t end,
    std::size_t* budget,std::uintptr_t* next) noexcept {
    if(links.right){auto child=links.right;
        while(true){if(*budget==0)return false;--*budget;
            Links value{};if(!Read(child,&value))return false;
            if(!value.left){*next=child;return true;}child=value.left;}
    }
    auto child=node;auto parent=links.parent;
    while(parent!=end){if(!parent||*budget==0)return false;--*budget;
        Links value{};if(!Read(parent,&value))return false;
        if(value.left==child){*next=parent;return true;}
        if(value.right!=child)return false;
        child=parent;parent=value.parent;
    }
    *next=end;return true;
}
template<class Visitor> bool WalkEntities(const Roots& roots,Visitor visit) noexcept {
    const auto end=roots.entity+8;
    if(roots.tree.count==0)return true;
    auto node=roots.tree.begin;std::size_t budget=roots.tree.count*4+4;
    for(std::size_t i=0;i<roots.tree.count;++i){
        if(!node||node==end||budget==0)return false;
        --budget;
        EntityPrefix value{};if(!Read(node,&value))return false;
        Name name{};if(!StringView(value.name,node+0x38,&name)||!visit(name,value.type,value.variant))return false;
        if(!NextNode(node,value.links,end,&budget,&node))return false;
    }
    return node==end;
}
template<class Visitor> bool WalkPills(const Roots& roots,Visitor visit) noexcept {
    // PC逆序遍历真实vector：同名后装槽优先，返回item.ID而非向量下标。
    for(auto position=roots.pillEnd;position>roots.pillBegin;){position-=8;
        std::uintptr_t item{};if(!Read(position,&item))return false;if(!item)continue;
        PillPrefix value{};if(!Read(item,&value))return false;
        Name name{};if(!StringView(value.name,item+8,&name)||!visit(name,value.id))return false;
    }
    return true;
}
std::uint32_t Hash(Family family,const char* name,std::size_t size) noexcept {
    std::uint32_t hash=2166136261U^static_cast<unsigned>(family);
    for(std::size_t i=0;i<size;++i){hash^=static_cast<unsigned char>(name[i]);hash*=16777619U;}
    return hash;
}
const Entry* Find(const Cache& cache,Family family,const char* name,std::size_t size,std::uint32_t hash) noexcept {
    for(auto slot=cache.buckets[hash&(cache.bucketCount-1)];slot;){
        const auto& entry=cache.entries[slot-1];
        if(entry.family==family&&entry.hash==hash&&entry.length==size&&
            (size==0||std::memcmp(cache.names+entry.offset,name,size)==0))return &entry;
        slot=entry.next;
    }
    return nullptr;
}
bool Insert(Cache& cache,Family family,const Name& name,std::int32_t type,std::int32_t variant,std::int32_t pill) noexcept {
    const auto* bytes=static_cast<const char*>(engine_memory::AsObject(name.data));
    const auto hash=Hash(family,bytes,name.size);
    if(Find(cache,family,bytes,name.size,hash))return true; // 首个按PC遍历顺序命中者保留。
    if(cache.count>=cache.capacity||name.size>cache.nameCapacity-cache.nameSize)return false;
    const auto bucket=hash&(cache.bucketCount-1);auto& entry=cache.entries[cache.count];
    entry={hash,static_cast<std::uint32_t>(cache.nameSize),static_cast<std::uint32_t>(name.size),
        cache.buckets[bucket],type,variant,pill,family,{0,0,0}};
    if(name.size)std::memcpy(cache.names+cache.nameSize,bytes,name.size);
    cache.nameSize+=name.size;cache.buckets[bucket]=static_cast<std::uint32_t>(++cache.count);return true;
}
const Entry* Lookup(lua_State* state,Family family) {
    std::size_t length{};const auto* name=luaL_checklstring(state,1,&length);
    // 只有明确配置变更才允许刷新；无缓存/未知根仍保持原错误，不能用轮询掩盖生命周期。
    if(g_RefreshPending && !RefreshRuntimeContentNames()) {
        luaL_error(state,"native content name cache refresh failed");return nullptr;
    }
    if(!g_Cache.ready){luaL_error(state,"native content name cache is not ready");return nullptr;}
    const auto item=ResolveContentConfigRoot(false);
    // 两配置根均由同一Manager固定内嵌；复核一次ItemConfig根即可避免重复Manager跳链。
    if(item!=g_Cache.itemRoot){g_Cache.ready=false;luaL_error(state,"native content configuration changed without refresh");return nullptr;}
    return Find(g_Cache,family,name,length,Hash(family,name,length));
}
}
void ClearRuntimeContentNames() noexcept {delete[] g_Cache.memory;g_Cache={};g_RefreshPending=false;}
void InvalidateRuntimeContentNames() noexcept {g_RefreshPending=true;}
bool RefreshRuntimeContentNames() noexcept {
    ClearRuntimeContentNames();++g_Refreshes;
    if(!LayoutValid())return false;
    Roots roots{};if(!ReadRoots(&roots))return false;
    const auto pills=(roots.pillEnd-roots.pillBegin)/8;
    if(roots.tree.count>UINT32_MAX||pills>UINT32_MAX-roots.tree.count)return false;
    const auto capacity=roots.tree.count+pills;
    std::size_t bytes{};
    const auto measure=[&bytes](const Name& name)noexcept{if(name.size>UINT32_MAX-bytes)return false;bytes+=name.size;return true;};
    if(!WalkPills(roots,[&](const Name& name,std::int32_t)noexcept{return measure(name);})||
       !WalkEntities(roots,[&](const Name& name,std::int32_t,std::int32_t)noexcept{return measure(name);}))return false;
    std::size_t buckets=1;
    if(capacity>SIZE_MAX/2)return false;
    while(buckets<capacity*2){if(buckets>SIZE_MAX/2)return false;buckets*=2;}
    if(buckets>SIZE_MAX/4||capacity>(SIZE_MAX-buckets*4)/sizeof(Entry))return false;
    const auto fixed=buckets*4+capacity*sizeof(Entry);
    if(bytes>SIZE_MAX-fixed)return false;
    const auto allocation=fixed+bytes;
#if !defined(__SWITCH__)
    if(g_FailAllocation)return false;
#endif
    std::unique_ptr<std::uint8_t[]> memory(new(std::nothrow)std::uint8_t[allocation]{});
    if(!memory)return false;
    Cache cache{};cache.memory=memory.get();
    cache.buckets=reinterpret_cast<std::uint32_t*>(memory.get());
    cache.entries=reinterpret_cast<Entry*>(memory.get()+buckets*4);
    cache.names=reinterpret_cast<char*>(memory.get()+fixed);
    cache.capacity=capacity;cache.nameCapacity=bytes;cache.bucketCount=buckets;cache.bytes=allocation;
    cache.itemRoot=roots.item;cache.entityRoot=roots.entity;
    if(!WalkPills(roots,[&](const Name& name,std::int32_t id)noexcept{return Insert(cache,Family::Pill,name,0,0,id);})||
       !WalkEntities(roots,[&](const Name& name,std::int32_t type,std::int32_t variant)noexcept{return Insert(cache,Family::Entity,name,type,variant,0);}))return false;
    Roots after{};if(!ReadRoots(&after)||after.item!=roots.item||after.entity!=roots.entity||
        after.pillBegin!=roots.pillBegin||after.pillEnd!=roots.pillEnd||
        std::memcmp(&after.tree,&roots.tree,sizeof(TreeHeader)))return false;
    cache.ready=true;g_Cache=cache;static_cast<void>(memory.release());return true;
}
int RuntimeGetPillEffectByName(lua_State* state){const auto* entry=Lookup(state,Family::Pill);lua_pushinteger(state,entry?entry->pill:-1);return 1;}
int RuntimeGetEntityTypeByName(lua_State* state){const auto* entry=Lookup(state,Family::Entity);lua_pushinteger(state,entry?entry->type:0);return 1;}
int RuntimeGetEntityVariantByName(lua_State* state){const auto* entry=Lookup(state,Family::Entity);lua_pushinteger(state,entry?entry->variant:-1);return 1;}
RuntimeContentNameStats RuntimeContentNameStatsSnapshot() noexcept {return {g_Cache.count,g_Cache.nameSize,g_Cache.bytes,g_Refreshes,g_Cache.ready};}
#if !defined(__SWITCH__)
void SetRuntimeContentNameAllocationFailureForTest(bool fail) noexcept {g_FailAllocation=fail;}
#endif
}
