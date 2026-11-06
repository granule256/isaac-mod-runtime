#include "interfaces/lua/api700_grid.hpp"
#include "interfaces/lua/api600_world.hpp"
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/api500_world.guards.hpp"
#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include "mod_room_guards.hpp"
#include "room_descriptor_layout.hpp"
#include "interfaces/lua/opaque_scalar_value.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
enum class Kind : unsigned char {Int,UInt,Bool,Float,U16,U8,String,Bit,DoorVariant};
enum class Group : unsigned char {Grid,Door,Poop,Pit,Tnt,Spikes,RoomConfig,Descriptor,Pill,GridDesc};
struct Field {const char* name;unsigned offset;Kind kind;Group group;unsigned bit;};
constexpr Field kFields[]={
    {"State",0x10,Kind::UInt,Group::Grid,0},
    {"CollisionClass",0x40,Kind::Int,Group::Grid,0},
    {"Slot",0x1a0,Kind::Int,Group::Door,0},
    {"ExtraVisible",0x308,Kind::Bool,Group::Door,0},
    {"Busted",0x309,Kind::Bool,Group::Door,0},
    {"ReviveTimer",0x1a0,Kind::Int,Group::Poop,0},
    {"UnderPlayer",0x1c0,Kind::Bool,Group::Poop,0},
    {"HasLadder",0x1a0,Kind::Bool,Group::Pit,0},
    {"FrameCnt",0x1a0,Kind::Int,Group::Tnt,0},
    {"Timeout",0x1a0,Kind::Int,Group::Spikes,0},
    {"State",0x10,Kind::Int,Group::GridDesc,0},
    {"SpawnCount",0x14,Kind::Int,Group::GridDesc,0},
    {"SpawnSeed",0x18,Kind::UInt,Group::GridDesc,0},
    {"Initialized",0x20,Kind::Bool,Group::GridDesc,0},
    {"VariableSeed",0x24,Kind::UInt,Group::GridDesc,0},
    {"StageID",0x0,Kind::Int,Group::RoomConfig,0},
    {"Variant",0xc,Kind::UInt,Group::RoomConfig,0},
    {"OriginalVariant",0x78,Kind::UInt,Group::RoomConfig,0},
    {"Subtype",0x10,Kind::UInt,Group::RoomConfig,0},
    {"Name",0x18,Kind::String,Group::RoomConfig,0},
    {"Difficulty",0x30,Kind::Int,Group::RoomConfig,0},
    {"InitialWeight",0x34,Kind::Float,Group::RoomConfig,0},
    {"Weight",0x38,Kind::Float,Group::RoomConfig,0},
    {"SpawnCount",0x58,Kind::U16,Group::RoomConfig,0},
    {"Width",0x5a,Kind::U8,Group::RoomConfig,0},
    {"Height",0x5b,Kind::U8,Group::RoomConfig,0},
    {"DecorationSeed",0x64,Kind::UInt,Group::Descriptor,0},
    {"SpawnSeed",0x68,Kind::UInt,Group::Descriptor,0},
    {"AwardSeed",0x6c,Kind::UInt,Group::Descriptor,0},
    {"PressurePlatesTriggered",0x50,Kind::Bit,Group::Descriptor,1},
    {"SacrificeDone",0x50,Kind::Bit,Group::Descriptor,2},
    {"ChallengeDone",0x50,Kind::Bit,Group::Descriptor,3},
    {"SurpriseMiniboss",0x50,Kind::Bit,Group::Descriptor,4},
    {"HasWater",0x50,Kind::Bit,Group::Descriptor,5},
    {"NoReward",0x50,Kind::Bit,Group::Descriptor,7},
    {"Type",0x8,Kind::Int,Group::GridDesc,0},
    {"Variant",0xc,Kind::UInt,Group::GridDesc,0},
    {"VarData",0x1c,Kind::Int,Group::GridDesc,0},
    {"Type",0x8,Kind::Int,Group::RoomConfig,0},
    {"Shape",0x5c,Kind::Int,Group::RoomConfig,0},
    // PC828253登记eVariant；NS385fb8及play_animation384698/3846d0确认历史Variant。
    {"PreviousVariant",0x314,Kind::DoorVariant,Group::Door,0},
};
api100_native::Cache g_Caches[9]{};
constexpr char kDescMeta[]="IsaacRuntime.GridEntityDesc";
constexpr char kRoomMeta[]="IsaacRuntime.RoomConfigRoom";
constexpr char kDoorSetMeta[]="IsaacRuntime.DoorSetValue";
constexpr char kModeMeta[]="IsaacRuntime.RoomConfigModeValue";
constexpr char kDoorVariantMeta[]="IsaacRuntime.GridEntityDoorVariant";
api100_native::Cache g_AllowedDoorsLayout{};
void AllowedDoorsGuard(lua_State* L) {
 // precalc_allowed_doors从Data+0x40向Descriptor+0x20复制完整原生8B门集合。
 static constexpr std::uint8_t bytes[]={0x88,0x0a,0x40,0xf9,0xa8,0x15,0x00,0xb4,0x08,0x21,0x40,0xf9,0x88,0x12,0x00,0xf9};
 static_cast<void>(api100_native::Resolve(L,{0x3d680c,bytes},g_AllowedDoorsLayout));
}
bool IsAllowedDoors(const char* name) {
 return name && name[0]=='A' && name[1]=='l' && !std::strcmp(name,"AllowedDoors");
}
struct View {std::uintptr_t object,base,owner;};
void Guard(lua_State* L,Group group) {
    unsigned i=static_cast<unsigned>(group);
    if(group==Group::GridDesc)i=0;
    const auto& entry=api500_world::kLayouts[i];
    static_cast<void>(api100_native::Resolve(L,{entry.offset,entry.bytes.data()},g_Caches[i]));
}
constexpr std::uint32_t Hash(const char* p) {
    std::uint32_t h=2166136261U;
    while(*p)h=(h^static_cast<unsigned char>(*p++))*16777619U;
    return h;
}
const Field* Find(const char* name,Group group) {
    if(!name||!name[0]||!name[1])return nullptr;
    const unsigned prefix=(static_cast<unsigned char>(name[0])<<8)|static_cast<unsigned char>(name[1]);
    switch(prefix) {
    case 0x4177:
    case 0x4275:
    case 0x4368:
    case 0x436f:
    case 0x4465:
    case 0x4469:
    case 0x4578:
    case 0x4672:
    case 0x4861:
    case 0x4865:
    case 0x496e:
    case 0x4e61:
    case 0x4e6f:
    case 0x4f72:
    case 0x5072:
    case 0x5265:
    case 0x5361:
    case 0x5368:
    case 0x536c:
    case 0x5370:
    case 0x5374:
    case 0x5375:
    case 0x5469:
    case 0x5479:
    case 0x556e:
    case 0x5661:
    case 0x5765:
    case 0x5769:
        break;
    default:return nullptr;
    }
    const Field* field=nullptr;
    switch(Hash(name)) {
    case Hash("State"):
        if(group==Group::Grid)field=&kFields[0];
        if(group==Group::GridDesc)field=&kFields[10];
        break;
    case Hash("CollisionClass"):
        if(group==Group::Grid)field=&kFields[1];
        break;
    case Hash("Slot"):
        if(group==Group::Door)field=&kFields[2];
        break;
    case Hash("ExtraVisible"):
        if(group==Group::Door)field=&kFields[3];
        break;
    case Hash("Busted"):
        if(group==Group::Door)field=&kFields[4];
        break;
    case Hash("ReviveTimer"):
        if(group==Group::Poop)field=&kFields[5];
        break;
    case Hash("UnderPlayer"):
        if(group==Group::Poop)field=&kFields[6];
        break;
    case Hash("HasLadder"):
        if(group==Group::Pit)field=&kFields[7];
        break;
    case Hash("FrameCnt"):
        if(group==Group::Tnt)field=&kFields[8];
        break;
    case Hash("Timeout"):
        if(group==Group::Spikes)field=&kFields[9];
        break;
    case Hash("SpawnCount"):
        if(group==Group::GridDesc)field=&kFields[11];
        if(group==Group::RoomConfig)field=&kFields[23];
        break;
    case Hash("SpawnSeed"):
        if(group==Group::GridDesc)field=&kFields[12];
        if(group==Group::Descriptor)field=&kFields[27];
        break;
    case Hash("Initialized"):
        if(group==Group::GridDesc)field=&kFields[13];
        break;
    case Hash("VariableSeed"):
        if(group==Group::GridDesc)field=&kFields[14];
        break;
    case Hash("StageID"):
        if(group==Group::RoomConfig)field=&kFields[15];
        break;
    case Hash("Variant"):
        if(group==Group::RoomConfig)field=&kFields[16];
        if(group==Group::GridDesc)field=&kFields[36];
        break;
    case Hash("OriginalVariant"):
        if(group==Group::RoomConfig)field=&kFields[17];
        break;
    case Hash("Subtype"):
        if(group==Group::RoomConfig)field=&kFields[18];
        break;
    case Hash("Name"):
        if(group==Group::RoomConfig)field=&kFields[19];
        break;
    case Hash("Difficulty"):
        if(group==Group::RoomConfig)field=&kFields[20];
        break;
    case Hash("InitialWeight"):
        if(group==Group::RoomConfig)field=&kFields[21];
        break;
    case Hash("Weight"):
        if(group==Group::RoomConfig)field=&kFields[22];
        break;
    case Hash("Width"):
        if(group==Group::RoomConfig)field=&kFields[24];
        break;
    case Hash("Height"):
        if(group==Group::RoomConfig)field=&kFields[25];
        break;
    case Hash("DecorationSeed"):
        if(group==Group::Descriptor)field=&kFields[26];
        break;
    case Hash("AwardSeed"):
        if(group==Group::Descriptor)field=&kFields[28];
        break;
    case Hash("PressurePlatesTriggered"):
        if(group==Group::Descriptor)field=&kFields[29];
        break;
    case Hash("SacrificeDone"):
        if(group==Group::Descriptor)field=&kFields[30];
        break;
    case Hash("ChallengeDone"):
        if(group==Group::Descriptor)field=&kFields[31];
        break;
    case Hash("SurpriseMiniboss"):
        if(group==Group::Descriptor)field=&kFields[32];
        break;
    case Hash("HasWater"):
        if(group==Group::Descriptor)field=&kFields[33];
        break;
    case Hash("NoReward"):
        if(group==Group::Descriptor)field=&kFields[34];
        break;
    case Hash("Type"):
        if(group==Group::GridDesc)field=&kFields[35];
        if(group==Group::RoomConfig)field=&kFields[38];
        break;
    case Hash("VarData"):
        if(group==Group::GridDesc)field=&kFields[37];
        break;
    case Hash("Shape"):
        if(group==Group::RoomConfig)field=&kFields[39];
        break;
    case Hash("PreviousVariant"):
        if(group==Group::Door)field=&kFields[40];
        break;
    default:return nullptr;
    }
    return field&&!std::strcmp(name,field->name)?field:nullptr;
}

template<class T>T Read(lua_State* L,std::uintptr_t p,unsigned offset) {
    T value{};
    if(!p||!engine_memory::ReadField(p,offset,&value,engine_memory::EngineMemoryReadable))
        luaL_error(L,"api500 world field is not readable");
    return value;
}
template<class T>void Write(lua_State* L,std::uintptr_t p,unsigned offset,T value) {
    if(!p||!engine_memory::WriteField(p,offset,value,engine_memory::EngineMemoryWritable))
        luaL_error(L,"api500 world field is not writable");
}
int Push(lua_State* L,std::uintptr_t p,const Field& field) {
    Guard(L,field.group);
    switch(field.kind) {
    case Kind::Int:lua_pushinteger(L,Read<std::int32_t>(L,p,field.offset));break;
    case Kind::UInt:lua_pushinteger(L,Read<std::uint32_t>(L,p,field.offset));break;
    case Kind::Bool:lua_pushboolean(L,Read<std::uint8_t>(L,p,field.offset)!=0);break;
    case Kind::Float:lua_pushnumber(L,Read<float>(L,p,field.offset));break;
    case Kind::U16:lua_pushinteger(L,Read<std::uint16_t>(L,p,field.offset));break;
    case Kind::U8:lua_pushinteger(L,Read<std::uint8_t>(L,p,field.offset));break;
    case Kind::String:return Api500PushConfigString(L,p+field.offset);
    case Kind::DoorVariant:PushOpaqueScalarValue(L,kDoorVariantMeta,"GridEntityDoor.eVariant",Read<std::uint32_t>(L,p,field.offset));break;
    case Kind::Bit:lua_pushboolean(L,(Read<std::uint32_t>(L,p,field.offset)&(1U<<field.bit))!=0);break;
    }
    return 1;
}
void Store(lua_State* L,std::uintptr_t p,const Field& field) {
    Guard(L,field.group);
    if(field.kind==Kind::DoorVariant){
        Write(L,p,field.offset,RequireOpaqueScalarValue<std::uint32_t>(L,3,kDoorVariantMeta));return;
    }
    if(field.kind==Kind::Bool) {
        Write(L,p,field.offset,static_cast<std::uint8_t>(lua_toboolean(L,3)!=0));return;
    }
    if(field.kind==Kind::Bit) {
        const auto old=Read<std::uint32_t>(L,p,field.offset),mask=1U<<field.bit;
        Write(L,p,field.offset,lua_toboolean(L,3)?old|mask:old&~mask);return;
    }
    const auto low=static_cast<std::uint32_t>(luaL_checkinteger(L,3));
    Write(L,p,field.offset,low);
}
std::uintptr_t Grid(lua_State* L,int index) {
    const auto p=engine_memory::AddressOf(GridEntityHandleArgument(L,index));
    if(!p||!IsLiveGridEntityPointer(p))luaL_error(L,"GridEntity reference is no longer available");
    return p;
}
Group GridGroup(lua_State* L,std::uintptr_t p) {
    const auto vptr=Read<std::uintptr_t>(L,p,0),base=LuaRuntime::EngineModuleBase();
    if(vptr==base+kGridEntity_DoorVtableOffset)return Group::Door;
    if(vptr==base+kGridEntity_PoopVtableOffset)return Group::Poop;
    if(vptr==base+kGridEntity_PitVtableOffset)return Group::Pit;
    if(vptr==base+kGridEntity_TNTVtableOffset)return Group::Tnt;
    if(vptr==base+kGridEntity_SpikesVtableOffset)return Group::Spikes;
    return Group::Grid;
}
bool GridCandidate(const char* name) {
    if(!name||!name[0]||!name[1])return false;
    switch((static_cast<unsigned char>(name[0])<<8)|static_cast<unsigned char>(name[1])) {
    case 0x5374:return !std::strcmp(name,"State");
    case 0x436f:return !std::strcmp(name,"CollisionClass");
    case 0x536c:return !std::strcmp(name,"Slot");
    case 0x4578:return !std::strcmp(name,"ExtraVisible");
    case 0x4275:return !std::strcmp(name,"Busted");
    case 0x5265:return !std::strcmp(name,"ReviveTimer");
    case 0x556e:return !std::strcmp(name,"UnderPlayer");
    case 0x4861:return !std::strcmp(name,"HasLadder");
    case 0x4672:return !std::strcmp(name,"FrameCnt");
    case 0x5469:return !std::strcmp(name,"Timeout");
    case 0x5072:return !std::strcmp(name,"PreviousVariant");
    default:return false;
    }
}
const Field* GridField(lua_State* L,std::uintptr_t p,const char* name) {
    if(!GridCandidate(name))return nullptr;
    if(const auto* base=Find(name,Group::Grid))return base;
    return Find(name,GridGroup(L,p));
}
std::uintptr_t TryDesc(lua_State* L,int index) noexcept {
    if(lua_rawlen(L,index)!=sizeof(View))return 0;
    const auto* view=static_cast<const View*>(luaL_testudata(L,index,kDescMeta));
    if(!view||!view->base||view->base!=LuaRuntime::EngineModuleBase())return 0;
    lua_getuservalue(L,index);const auto p=engine_memory::AddressOf(GridEntityHandleArgument(L,-1));lua_pop(L,1);
    if(!p||p!=view->object||!IsLiveGridEntityPointer(p))return 0;
    return p;
}
std::uintptr_t DescIdentity(lua_State*L,int index) noexcept {
    const auto p=TryDesc(L,index);
    // PC返回this+4的32B借用描述符；NS的完整描述符位于Grid+8。
    return p&&p<=UINTPTR_MAX-8&&engine_memory::EngineMemoryReadable(p+8,32)?p+8:0;
}
std::uintptr_t LiveDesc(lua_State* L) {
    luaL_checkudata(L,1,kDescMeta);const auto p=TryDesc(L,1);
    if(!p)luaL_error(L,"GridEntityDesc owner or module is no longer available");
    return p;
}
int DescIndex(lua_State* L) {
    const auto* name=lua_tostring(L,2);const auto* field=Find(name,Group::GridDesc);
    if(!field){lua_pushnil(L);return 1;}
    return Push(L,LiveDesc(L),*field);
}
int DescWrite(lua_State* L) {
    const auto* field=Find(luaL_checkstring(L,2),Group::GridDesc);
    if(!field)return luaL_error(L,"unknown GridEntityDesc field");
    Store(L,LiveDesc(L),*field);return 0;
}
constexpr std::uintptr_t kRoomSetOwnerTag=1;
// 两个低位只区分原生RoomSet与描述符的Data/OverrideData借用来源，不改变对象所有权。
constexpr std::uintptr_t kOverrideDataOwnerTag=2;
constexpr std::uintptr_t kRoomOwnerTags=3;
api100_native::Cache g_OverrideDataCaches[2]{};
void OverrideDataGuard(lua_State* L) {
    // Level::load_room 原生 +0x18 读/写点；与其它descriptor字段独立缓存。
    static constexpr std::uint8_t readBytes[]={0x97,0x0e,0x40,0xf9,0xd7,0x00,0x00,0xb4,0xe8,0x02,0x40,0xb9,0x88,0x00,0x00,0x35};
    static constexpr std::uint8_t writeBytes[]={0x97,0x0e,0x00,0xf9,0x21,0x57,0x40,0xb9,0xe0,0x03,0x1b,0xaa,0x22,0x5f,0x40,0xb9};
    static_cast<void>(api100_native::Resolve(L,{0x3d6edc,readBytes},g_OverrideDataCaches[0]));
    static_cast<void>(api100_native::Resolve(L,{0x3d707c,writeBytes},g_OverrideDataCaches[1]));
}
bool IsOverrideData(const char* name) {
    return name && name[0]=='O' && !std::strcmp(name,"OverrideData");
}
bool IsRoomSetMember(std::uintptr_t owner,std::uintptr_t object) {
    std::uintptr_t begin=0;
    std::uint32_t count=0;
    if(!engine_memory::ReadField(owner,0x18,&begin,engine_memory::EngineMemoryReadable) ||
       !engine_memory::ReadField(owner,0x20,&count,engine_memory::EngineMemoryReadable) ||
       begin==0 || object<begin)return false;
    const auto offset=object-begin;
    return offset%0x80==0 && offset/0x80<count &&
        engine_memory::EngineMemoryReadable(object,0x80);
}
std::uintptr_t RoomSetOwner(std::uintptr_t object) noexcept {
    std::uint32_t stage{},mode{};
    if(!engine_memory::ReadField(object,0,&stage,engine_memory::EngineMemoryReadable)||
       !engine_memory::ReadField(object,4,&mode,engine_memory::EngineMemoryReadable))return 0;
    // 固定NRO构造37个0x100字节阶段，每阶段两个0x48字节RoomSet。
    if(stage>=37 || mode>=2)return 0;
    const auto base=LuaRuntime::EngineModuleBase();
    std::uintptr_t slot=0,game=0;
    if(!engine_memory::ReadField(base,kGameOwnerGlobalSlotOffset,&slot,engine_memory::EngineMemoryReadable) ||
       slot==0 || !engine_memory::ReadAt(slot,&game,engine_memory::EngineMemoryReadable))return 0;
    const auto offset=mod_rooms::kGameRoomConfigOffset+stage*0x100+mode*0x48+0x68;
    if(game==0 || game>UINTPTR_MAX-offset)return 0;
    const auto owner=game+offset;
    return IsRoomSetMember(owner,object)?owner|kRoomSetOwnerTag:0;
}
std::uintptr_t TryRoom(lua_State* L,int index) noexcept {
    if(lua_rawlen(L,index)!=sizeof(View))return 0;
    const auto* view=static_cast<const View*>(luaL_testudata(L,index,kRoomMeta));
    if(!view||!view->base||view->base!=LuaRuntime::EngineModuleBase()||
       !view->object||!engine_memory::EngineMemoryReadable(view->object,0x80))return 0;
    if(view->owner&kRoomSetOwnerTag) {
        if(RoomSetOwner(view->object)!=view->owner)return 0;
    } else if(view->owner) {
        std::uintptr_t data{};
        if(!engine_memory::ReadField(view->owner&~kRoomOwnerTags,
             (view->owner&kOverrideDataOwnerTag)?0x18:0x10,&data,
             engine_memory::EngineMemoryReadable)||data!=view->object)return 0;
    }
    return view->object;
}
std::uintptr_t LiveRoom(lua_State* L,int index=1) {
    luaL_checkudata(L,index,kRoomMeta);const auto p=TryRoom(L,index);
    if(!p)luaL_error(L,"RoomConfigRoom owner or module is no longer available");
    return p;
}
int RoomIndex(lua_State* L) {
    const auto* name=lua_tostring(L,2);
    if(name && name[0]=='M' && !std::strcmp(name,"Mode")){Guard(L,Group::RoomConfig);PushOpaqueScalarValue(L,kModeMeta,"RoomConfigMode",Read<std::int32_t>(L,LiveRoom(L),4));return 1;}
    if(name&&!std::strcmp(name,"Doors")){Guard(L,Group::RoomConfig);lua_pushinteger(L,Read<std::uint32_t>(L,LiveRoom(L),0x40));return 1;}
    if(name&&!std::strcmp(name,"Spawns"))return Api500PushRoomSpawns(L,LiveRoom(L));
    const auto* field=Find(name,Group::RoomConfig);
    if(!field){lua_pushnil(L);return 1;}
    return Push(L,LiveRoom(L),*field);
}
int ReadOnly(lua_State* L) {return luaL_error(L,"RoomConfigRoom is read-only");}
void Metatable(lua_State* L,const char* name,const char* type,lua_CFunction index,lua_CFunction write) {
    if(luaL_newmetatable(L,name)) {
        lua_pushcfunction(L,index);lua_setfield(L,-2,"__index");
        lua_pushcfunction(L,write);lua_setfield(L,-2,"__newindex");
        lua_pushstring(L,type);lua_setfield(L,-2,"__type");
        lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");
        if(!RegisterNativeObjectIdentity(L,-1,!std::strcmp(name,kDescMeta)?DescIdentity:TryRoom))
            luaL_error(L,"RoomConfig/GridDesc identity resolver conflicts");
    }
    lua_setmetatable(L,-2);
}
}
int TryPushApi500GridField(lua_State* L,std::uintptr_t p,const char* name) {
    if(!GridCandidate(name))return 0;
    if(!IsLiveGridEntityPointer(p))return luaL_error(L,"GridEntity reference is no longer available");
    const auto* field=GridField(L,p,name);if(!field)return 0;
    return Push(L,p,*field);
}
int Api500GridNewIndex(lua_State* L) {
    const auto p=Grid(L,1);const auto* name=luaL_checkstring(L,2);
    if(TryWriteApi700GridField(L,name))return 0;
    const auto* field=GridField(L,p,name);
    if(!field){if(TryWriteApi600GridField(L,p,name))return 0;return luaL_error(L,"GridEntity has no writable field named %s",name);}
    Store(L,p,*field);return 0;
}
namespace {
const unsigned char kGridDescCacheKey{}, kGridDescCacheBaseKey{};
void PushGridDescCache(lua_State* L) {
    const auto base = LuaRuntime::EngineModuleBase();
    lua_rawgetp(L, LUA_REGISTRYINDEX, &kGridDescCacheBaseKey);
    const bool sameBase = engine_memory::AddressOf(lua_touserdata(L, -1)) == base;
    lua_pop(L, 1);
    lua_rawgetp(L, LUA_REGISTRYINDEX, &kGridDescCacheKey);
    if (sameBase && lua_istable(L, -1)) return;
    lua_pop(L, 1);
    // Borrowed views own no native memory. Weak values let the owner/view cycle
    // die normally; neither this map nor its lightuserdata keys pin a grid.
    lua_newtable(L);
    lua_createtable(L, 0, 1);
    lua_pushliteral(L, "v"); lua_setfield(L, -2, "__mode");
    lua_setmetatable(L, -2);
    lua_pushvalue(L, -1); lua_rawsetp(L, LUA_REGISTRYINDEX, &kGridDescCacheKey);
    lua_pushlightuserdata(L, engine_memory::AsObject(base));
    lua_rawsetp(L, LUA_REGISTRYINDEX, &kGridDescCacheBaseKey);
}
}
bool PushApi500GridDesc(lua_State* L,std::uintptr_t p) {
    if(!p)return false;
    if(!IsLiveGridEntityPointer(p))luaL_error(L,"GridEntityDesc owner is no longer available");
    // Cache per live owner userdata: Desc and GetSaveState share the same view.
    lua_getuservalue(L,1);
    if(luaL_testudata(L,-1,kDescMeta))return true;
    lua_pop(L,1);
    PushGridDescCache(L);
    const int cache = lua_gettop(L);
    lua_rawgetp(L, cache, engine_memory::AsObject(p));
    const auto* cached = static_cast<const View*>(luaL_testudata(L, -1, kDescMeta));
    // Private entries retain an immutable owner. Current p was checked above;
    // field/identity access still performs the complete TryDesc validation.
    if (cached && cached->object == p && cached->base == LuaRuntime::EngineModuleBase()) {
        lua_remove(L, cache);
        lua_pushvalue(L, -1); lua_setuservalue(L, 1);
        return true;
    }
    lua_pop(L, 1);
    auto* view=static_cast<View*>(lua_newuserdata(L,sizeof(View)));
    *view={p,LuaRuntime::EngineModuleBase(),0};
    lua_pushvalue(L,1);lua_setuservalue(L,-2);
    Metatable(L,kDescMeta,"GridEntityDesc",DescIndex,DescWrite);
    lua_pushvalue(L,-1);lua_setuservalue(L,1);
    lua_pushvalue(L, -1); lua_rawsetp(L, cache, engine_memory::AsObject(p));
    lua_remove(L, cache);
    return true;
}
void PushApi500RoomConfig(lua_State* L,std::uintptr_t p,std::uintptr_t owner) {
    // 原生配置属于RoomSet，不属于当前恰好引用它的可复用描述符槽。
    const auto set=RoomSetOwner(p);
    auto* view=static_cast<View*>(lua_newuserdata(L,sizeof(View)));
    *view={p,LuaRuntime::EngineModuleBase(),set?set:owner};
    lua_pushvalue(L,1);lua_setuservalue(L,-2);
    Metatable(L,kRoomMeta,"RoomConfigRoom",RoomIndex,ReadOnly);
}
int TryPushApi500DescriptorField(lua_State* L,std::uintptr_t p,const char* name) {
    if(IsAllowedDoors(name)) {
        if(!p){lua_pushnil(L);return 1;}
        AllowedDoorsGuard(L);
        PushOpaqueScalarValue(L,kDoorSetMeta,"DoorSet",Read<std::uint64_t>(L,p,0x20));return 1;
    }
    if(IsOverrideData(name)) {
        if(!p){lua_pushnil(L);return 1;}
        OverrideDataGuard(L);
        const auto data=Read<std::uintptr_t>(L,p,0x18);
        if(!data){lua_pushnil(L);return 1;}
        PushApi500RoomConfig(L,data,p|kOverrideDataOwnerTag);
        return 1;
    }
    const auto* field=Find(name,Group::Descriptor);if(!field)return 0;
    if(!p){lua_pushnil(L);return 1;}
    return Push(L,p,*field);
}
bool TryWriteApi500DescriptorField(lua_State* L,std::uintptr_t p,const char* name) {
    if(name && !std::strcmp(name,"Data")) {
        if(!p)luaL_error(L,"RoomDescriptor reference is no longer available");
        // PC setter @0x85CF10 borrows the native pointer (nil clears it).
        // RoomSet keeps ownership; OverrideData and descriptor flags stay intact.
        const std::uintptr_t data=lua_isnil(L,3)?0:LiveRoom(L,3);
        Write(L,p,layout::kRoomDescriptorDataOffset,data);
        return true;
    }
    // Legacy descriptor getters live in RoomDescriptorIndex. PC also exposes
    // these writable scalar slots; StageAPI needs them when installing a room.
    constexpr Field coreFields[]={
        {"GridIndex",layout::kRoomDescriptorGridIndexOffset,Kind::Int,Group::Descriptor,0},
        {"SafeGridIndex",layout::kRoomDescriptorSafeGridIndexOffset,Kind::Int,Group::Descriptor,0},
        {"ListIndex",0x8,Kind::Int,Group::Descriptor,0},
        {"DisplayFlags",layout::kRoomDescriptorDisplayFlagsOffset,Kind::UInt,Group::Descriptor,0},
        {"VisitedCount",layout::kRoomDescriptorVisitedCountOffset,Kind::Int,Group::Descriptor,0},
        {"Flags",layout::kRoomDescriptorFlagsOffset,Kind::UInt,Group::Descriptor,0},
        {"Clear",layout::kRoomDescriptorFlagsOffset,Kind::Bit,Group::Descriptor,0},
    };
    for(const auto& field:coreFields) {
        if(name && !std::strcmp(name,field.name)) {
            if(!p)luaL_error(L,"RoomDescriptor reference is no longer available");
            Store(L,p,field);
            return true;
        }
    }
    if(IsAllowedDoors(name)) {
        AllowedDoorsGuard(L);
        if(!p)luaL_error(L,"RoomDescriptor reference is no longer available");
        Write(L,p,0x20,RequireOpaqueScalarValue<std::uint64_t>(L,3,kDoorSetMeta));return true;
    }
    if(IsOverrideData(name)) {
        OverrideDataGuard(L);
        // PC setter只是借用RoomConfigRoom原生指针；不复制/释放、不更改Data或flags。
        const std::uintptr_t data=lua_isnil(L,3)?0:LiveRoom(L,3);
        Write(L,p,0x18,data);
        return true;
    }
    const auto* field=Find(name,Group::Descriptor);if(!field)return false;
    Store(L,p,*field);return true;
}
int Api500ItemPoolIdentifyPill(lua_State* L) {
    luaL_checkudata(L,1,LuaRuntime::kItemPoolMetatable);
    const auto color=static_cast<std::uint32_t>(luaL_checkinteger(L,2))&0x7ffU;
    const auto p=ResolveEngineReceiver(L,FieldReceipt::ItemPool,1);
    if(!p)return luaL_error(L,"ItemPool reference is unavailable");
    Guard(L,Group::Pill);
    Write(L,p,kItemPoolPillIdentifiedOffset+color,std::uint8_t{1});
    return 0;
}
}
