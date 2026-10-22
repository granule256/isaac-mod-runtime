#include "interfaces/lua/api600_bindings.hpp"
#include "interfaces/lua/api600_containers.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include <array>
#include <cstddef>
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr char kSpawns[]="IsaacRuntime.RoomConfigSpawns";
constexpr char kEntries[]="IsaacRuntime.RoomConfigEntries";
constexpr char kOwner[]="IsaacRuntime.RoomConfigArrayOwner";
constexpr std::uintptr_t kParse=0x48f490;
constexpr std::array<std::uint8_t,16> kParseGuard={0xfd,0x43,0x02,0x91,0xfc,0x6f,0x0a,0xa9,0xfa,0x67,0x0b,0xa9,0xf8,0x5f,0x0c,0xa9};
constexpr std::uintptr_t kMirror=0x495248;
constexpr std::array<std::uint8_t,16> kMirrorGuard={0xf8,0x5f,0x03,0xa9,0xf6,0x57,0x04,0xa9,0xf4,0x4f,0x05,0xa9,0xf4,0x03,0x00,0xaa};
constexpr api100_native::Entry kLayouts[]={{kParse,kParseGuard.data()},{kMirror,kMirrorGuard.data()}};
api100_native::Cache g_Cache[2]{};
// 配置数组不是实体，owner保存module/Room/数组身份，不建立全局动态映射。
struct Owner {
 std::uintptr_t module,room,spawns,spawn,entries;
 std::uint16_t spawnCount;
 std::uint8_t entryCount;
};
struct Container {Owner owner;};
// The pointer remains the first field expected by existing Spawn/Entry consumers.
// Inline immutable owner metadata removes one userdata allocation per ArrayProxy Get.
struct View {void*object;Owner owner;};
static_assert(offsetof(View,object)==0);
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned offset){T value{};if(!engine_memory::ReadField(p,offset,&value,engine_memory::EngineMemoryReadable))luaL_error(L,"RoomConfig reference is not readable");return value;}
void Layout(lua_State*L){for(unsigned i=0;i<2;++i)static_cast<void>(api100_native::Resolve(L,kLayouts[i],g_Cache[i]));}
Owner Root(lua_State*L,std::uintptr_t room){Layout(L);Owner o{LuaRuntime::EngineModuleBase(),room,0,0,0,0,0};if(room){o.spawns=Read<std::uintptr_t>(L,room,0x50);o.spawnCount=Read<std::uint16_t>(L,room,0x58);}if(o.spawnCount&&!o.spawns)luaL_error(L,"RoomConfig spawn array is unavailable");return o;}
bool Contains(std::uintptr_t begin,unsigned count,unsigned stride,std::uintptr_t address){return begin&&address>=begin&&(address-begin)%stride==0&&(address-begin)/stride<count;}
void Check(lua_State*L,const Owner&o){
 if(!o.module||o.module!=LuaRuntime::EngineModuleBase())luaL_error(L,"RoomConfig reference module has changed");
 Layout(L);
 if(o.room&&(Read<std::uintptr_t>(L,o.room,0x50)!=o.spawns||Read<std::uint16_t>(L,o.room,0x58)!=o.spawnCount))luaL_error(L,"RoomConfig reference owner array has changed");
 if(o.spawn){if(!Contains(o.spawns,o.spawnCount,0x18,o.spawn))luaL_error(L,"RoomConfig reference owner is unavailable");if(Read<std::uintptr_t>(L,o.spawn,8)!=o.entries||Read<std::uint8_t>(L,o.spawn,0x10)!=o.entryCount)luaL_error(L,"RoomConfig entry reference owner array has changed");}
}
Owner Child(lua_State*L,const Owner&root,std::uintptr_t spawn){Owner o=root;o.spawn=spawn;o.entries=Read<std::uintptr_t>(L,spawn,8);o.entryCount=Read<std::uint8_t>(L,spawn,0x10);if(o.entryCount&&!o.entries)luaL_error(L,"RoomConfig entries array is unavailable");return o;}
void SetOwner(lua_State*L,int target,const Owner&o){target=lua_absindex(L,target);auto*p=static_cast<Owner*>(lua_newuserdata(L,sizeof(Owner)));*p=o;luaL_getmetatable(L,kOwner);lua_setmetatable(L,-2);lua_setuservalue(L,target);}
const Owner* ViewOwner(lua_State*L,int index){
 if((luaL_testudata(L,index,LuaRuntime::kRoomConfigSpawnMetatable)||luaL_testudata(L,index,LuaRuntime::kRoomConfigEntryMetatable))&&lua_rawlen(L,index)==sizeof(View))return &static_cast<const View*>(lua_touserdata(L,index))->owner;
 lua_getuservalue(L,index);const auto*p=static_cast<Owner*>(luaL_testudata(L,-1,kOwner));lua_pop(L,1);return p;}
void PushSpawn(lua_State*L,const Owner&o){auto*p=static_cast<View*>(lua_newuserdata(L,sizeof(View)));*p={engine_memory::AsObject(o.spawn),o};luaL_getmetatable(L,LuaRuntime::kRoomConfigSpawnMetatable);lua_setmetatable(L,-2);}
void PushEntry(lua_State*L,const Owner&o,std::uintptr_t entry){auto*p=static_cast<View*>(lua_newuserdata(L,sizeof(View)));*p={engine_memory::AsObject(entry),o};luaL_getmetatable(L,LuaRuntime::kRoomConfigEntryMetatable);lua_setmetatable(L,-2);}

Container* List(lua_State*L,const char*mt){auto*p=static_cast<Container*>(luaL_checkudata(L,1,mt));Check(L,p->owner);return p;}
int SpawnsGet(lua_State*L){const auto&o=List(L,kSpawns)->owner;const auto i=luaL_checkinteger(L,2);if(i<0||static_cast<std::uint64_t>(i)>=o.spawnCount){lua_pushnil(L);return 1;}const auto p=o.spawns+static_cast<std::uintptr_t>(i)*0x18;PushSpawn(L,Child(L,o,p));return 1;}
int SpawnsIndex(lua_State*L){const auto&o=List(L,kSpawns)->owner;const auto*n=lua_tostring(L,2);if(n&&!std::strcmp(n,"Size"))lua_pushinteger(L,o.spawnCount);else if(n&&!std::strcmp(n,"Get"))lua_pushcfunction(L,SpawnsGet);else lua_pushnil(L);return 1;}
int EntriesIndex(lua_State*L){const auto&o=List(L,kEntries)->owner;const auto*n=lua_tostring(L,2);if(n&&!std::strcmp(n,"Size"))lua_pushinteger(L,o.entryCount);else if(n&&!std::strcmp(n,"Get"))lua_pushcfunction(L,Api600RoomConfigEntriesGet);else lua_pushnil(L);return 1;}
void Register(lua_State*L,const char*mt,const char*name,lua_CFunction index,lua_CFunction len){
 luaL_newmetatable(L,mt);lua_pushcfunction(L,index);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api600RoomConfigReadOnly);lua_setfield(L,-2,"__newindex");
 lua_newtable(L);static_cast<void>(AttachApi600Methods(L,name));if(!std::strcmp(mt,kSpawns)){lua_pushcfunction(L,SpawnsGet);lua_setfield(L,-2,"Get");}
 lua_getfield(L,-1,"__len");if(lua_isnil(L,-1)){lua_pop(L,1);lua_pushcfunction(L,len);}lua_setfield(L,-3,"__len");lua_setfield(L,-2,"__methods");lua_pop(L,1);PublishNativeClass(L,name,mt);
 lua_getglobal(L,"CppContainer");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);}lua_getfield(L,-1,"ArrayProxy");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);}lua_getglobal(L,name);lua_setfield(L,-2,name);lua_setfield(L,-2,"ArrayProxy");lua_setglobal(L,"CppContainer");
}
}
int Api600RoomConfigReadOnly(lua_State*L){CheckApi600RoomConfigView(L,1);return luaL_error(L,"RoomConfig container reference is read-only");}
void RegisterApi600RoomConfigContainers(lua_State*L){luaL_newmetatable(L,kOwner);lua_pop(L,1);Register(L,kSpawns,"RoomConfigSpawns",SpawnsIndex,Api600RoomConfigSpawnsLen);Register(L,kEntries,"RoomConfigEntries",EntriesIndex,Api600RoomConfigEntriesLen);}
void PushApi600SpawnList(lua_State*L,std::uintptr_t roomData){const auto owner=Root(L,roomData);auto*p=static_cast<Container*>(lua_newuserdata(L,sizeof(Container)));p->owner=owner;luaL_getmetatable(L,kSpawns);lua_setmetatable(L,-2);}
int Api600RoomConfigSpawnsLen(lua_State*L){lua_pushinteger(L,List(L,kSpawns)->owner.spawnCount);return 1;}
int Api600RoomConfigEntriesLen(lua_State*L){lua_pushinteger(L,List(L,kEntries)->owner.entryCount);return 1;}
int Api600RoomConfigEntriesGet(lua_State*L){const auto&o=List(L,kEntries)->owner;const auto i=luaL_checkinteger(L,2);if(i<0||static_cast<std::uint64_t>(i)>=o.entryCount){lua_pushnil(L);return 1;}PushEntry(L,o,o.entries+static_cast<std::uintptr_t>(i)*0xc);return 1;}
void CheckApi600RoomConfigView(lua_State*L,int index){if(const auto*o=ViewOwner(L,index))Check(L,*o);}
void InheritApi600RoomConfigViewOwner(lua_State*L,int sourceIndex,int targetIndex){sourceIndex=lua_absindex(L,sourceIndex);targetIndex=lua_absindex(L,targetIndex);const auto*o=ViewOwner(L,sourceIndex);if(!o)return;Check(L,*o);const auto*entry=static_cast<LuaRuntime::RoomConfigEntryHandle*>(luaL_checkudata(L,targetIndex,LuaRuntime::kRoomConfigEntryMetatable));if(!Contains(o->entries,o->entryCount,0xc,engine_memory::AddressOf(entry->entry)))luaL_error(L,"RoomConfig entry result is outside owner array");SetOwner(L,targetIndex,*o);}
int TryPushApi600SpawnField(lua_State*L,int index,const char*key){
 if(!key||!key[0])return 0;
 // 新字段仅X/Y/En前缀；未命中不读owner、指纹、数组或分配。
 const bool x=key[0]=='X'&&!key[1],y=key[0]=='Y'&&!key[1];const bool entries=key[0]=='E'&&key[1]=='n'&&!std::strcmp(key,"Entries");if(!x&&!y&&!entries)return 0;
 const auto*p=static_cast<LuaRuntime::RoomConfigSpawnHandle*>(luaL_checkudata(L,index,LuaRuntime::kRoomConfigSpawnMetatable));CheckApi600RoomConfigView(L,index);Layout(L);const auto spawn=engine_memory::AddressOf(p->spawn);
 if(x||y){lua_pushinteger(L,Read<std::int16_t>(L,spawn,y?2:0));return 1;}
 const auto*parent=ViewOwner(L,index);if(!parent)return luaL_error(L,"RoomConfig entry reference owner metadata is unavailable");const auto owner=Child(L,*parent,spawn);auto*list=static_cast<Container*>(lua_newuserdata(L,sizeof(Container)));list->owner=owner;luaL_getmetatable(L,kEntries);lua_setmetatable(L,-2);return 1;
}
}
