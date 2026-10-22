#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/api500_config.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr LuaHandlerBinding kApi500CardBindings[]={{0x0E011600,&Api500ItemConfigCardIsCard}};
enum class Family:unsigned char{Item,Card,Pill,Costume};
enum class Kind:unsigned char{Int,UInt,Short,Bool,String,Costume,Method};
struct Field{const char*name;unsigned offset;Kind kind;Family family;unsigned guard;};
constexpr Field kFields[]={
{"CacheFlags",0x54,Kind::UInt,Family::Item,0},
{"MaxCooldown",0x78,Kind::Int,Family::Item,1},
{"DevilPrice",0x7c,Kind::Short,Family::Item,2},
{"ShopPrice",0x7e,Kind::Short,Family::Item,3},
{"InitCharge",0xd0,Kind::Int,Family::Item,4},
{"PassiveCache",0xb5,Kind::Bool,Family::Item,5},
{"AddCostumeOnPickup",0xb6,Kind::Bool,Family::Item,6},
{"PersistentEffect",0xb8,Kind::Bool,Family::Item,7},
{"ClearEffectsOnRemove",0xb9,Kind::Bool,Family::Item,8},
{"Costume",0x80,Kind::Costume,Family::Item,9},
{"HudAnim",0x38,Kind::String,Family::Card,10},
{"GreedModeAllowed",0x50,Kind::Bool,Family::Card,11},
{"PickupSubtype",0x54,Kind::UInt,Family::Card,12},
{"CardType",0x58,Kind::Int,Family::Card,12},
{"AnnouncerVoice",0x5c,Kind::Int,Family::Card,13},
{"AnnouncerDelay",0x60,Kind::Int,Family::Card,13},
{"IsCard",0x58,Kind::Method,Family::Card,12},
{"GreedModeAllowed",0x38,Kind::Bool,Family::Pill,14},
{"AnnouncerVoice",0x3c,Kind::Int,Family::Pill,15},
{"AnnouncerVoiceSuper",0x40,Kind::Int,Family::Pill,15},
{"AnnouncerDelay",0x44,Kind::Int,Family::Pill,16},
{"ID",0x0,Kind::Int,Family::Costume,9},
{"Anm2Path",0x8,Kind::String,Family::Costume,9},
{"Priority",0x20,Kind::Int,Family::Costume,17},
{"HasOverlay",0x24,Kind::Bool,Family::Costume,17},
{"IsFlying",0x25,Kind::Bool,Family::Costume,17},
{"HasSkinAlt",0x26,Kind::Bool,Family::Costume,17},
{"OverwriteColor",0x2c,Kind::Bool,Family::Costume,17},
{"ID",0x0,Kind::Int,Family::Card,18},
{"AchievementID",0x4,Kind::Int,Family::Card,18},
{"ID",0x0,Kind::Int,Family::Pill,19},
{"AchievementID",0x4,Kind::Int,Family::Pill,19},
};
api100_native::Cache g_Cache[sizeof(api500_config::kGuards)/sizeof(api500_config::kGuards[0])]{};
#if !defined(__SWITCH__)
Api500ConfigStringAssignment g_StringAssignment{};
#endif
constexpr char kCostumeMetatable[]="IsaacRuntime.ItemConfig_Costume";
struct CostumeHandle{std::uintptr_t item;std::uintptr_t base;};
constexpr std::uint32_t Hash(const char*s){std::uint32_t h=2166136261U;while(*s)h=(h^static_cast<unsigned char>(*s++))*16777619U;return h;}
bool Candidate(const char*name){if(!name||!name[0]||!name[1])return false;
 const auto prefix=(static_cast<unsigned char>(name[0])<<8)|static_cast<unsigned char>(name[1]);
 switch(prefix){
case 0x4163:
case 0x4164:
case 0x416e:
case 0x4361:
case 0x436c:
case 0x436f:
case 0x4465:
case 0x4772:
case 0x4861:
case 0x4875:
case 0x4944:
case 0x496e:
case 0x4973:
case 0x4d61:
case 0x4f76:
case 0x5061:
case 0x5065:
case 0x5069:
case 0x5072:
case 0x5368:
 break;default:return false;}
 switch(Hash(name)){
case Hash("AchievementID"):return !std::strcmp(name,"AchievementID");
case Hash("AddCostumeOnPickup"):return !std::strcmp(name,"AddCostumeOnPickup");
case Hash("Anm2Path"):return !std::strcmp(name,"Anm2Path");
case Hash("AnnouncerDelay"):return !std::strcmp(name,"AnnouncerDelay");
case Hash("AnnouncerVoice"):return !std::strcmp(name,"AnnouncerVoice");
case Hash("AnnouncerVoiceSuper"):return !std::strcmp(name,"AnnouncerVoiceSuper");
case Hash("CacheFlags"):return !std::strcmp(name,"CacheFlags");
case Hash("CardType"):return !std::strcmp(name,"CardType");
case Hash("ClearEffectsOnRemove"):return !std::strcmp(name,"ClearEffectsOnRemove");
case Hash("Costume"):return !std::strcmp(name,"Costume");
case Hash("DevilPrice"):return !std::strcmp(name,"DevilPrice");
case Hash("GreedModeAllowed"):return !std::strcmp(name,"GreedModeAllowed");
case Hash("HasOverlay"):return !std::strcmp(name,"HasOverlay");
case Hash("HasSkinAlt"):return !std::strcmp(name,"HasSkinAlt");
case Hash("HudAnim"):return !std::strcmp(name,"HudAnim");
case Hash("ID"):return !std::strcmp(name,"ID");
case Hash("InitCharge"):return !std::strcmp(name,"InitCharge");
case Hash("IsCard"):return !std::strcmp(name,"IsCard");
case Hash("IsFlying"):return !std::strcmp(name,"IsFlying");
case Hash("MaxCooldown"):return !std::strcmp(name,"MaxCooldown");
case Hash("OverwriteColor"):return !std::strcmp(name,"OverwriteColor");
case Hash("PassiveCache"):return !std::strcmp(name,"PassiveCache");
case Hash("PersistentEffect"):return !std::strcmp(name,"PersistentEffect");
case Hash("PickupSubtype"):return !std::strcmp(name,"PickupSubtype");
case Hash("Priority"):return !std::strcmp(name,"Priority");
case Hash("ShopPrice"):return !std::strcmp(name,"ShopPrice");
default:return false;}}
Family Type(std::uint32_t begin){return begin==0x48?Family::Card:begin==0x60?Family::Pill:Family::Item;}
const Field*Find(const char*name,Family family){if(!Candidate(name))return nullptr;for(const auto&f:kFields)if(f.family==family&&!std::strcmp(name,f.name))return &f;return nullptr;}
void Check(lua_State*L,const Field&f){const auto&g=api500_config::kGuards[f.guard];api100_native::Resolve(L,{g.offset,g.bytes.data()},g_Cache[f.guard]);}
std::uintptr_t Live(lua_State*L,std::uintptr_t p){if(!p||ItemConfigPointerArgument(L,1)!=p)luaL_error(L,"ItemConfig reference is no longer available");return p;}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned o){T v{};if(!engine_memory::ReadField(p,o,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"ItemConfig native field is unreadable");return v;}
template<class T>void Store(lua_State*L,std::uintptr_t p,unsigned o,T v){if(!engine_memory::WriteField(p,o,v,engine_memory::EngineMemoryWritable))luaL_error(L,"ItemConfig native field is not writable");}
// 调用游戏自己的libc++赋值函数，临时长串只借用Lua字节，不拥有或释放源内存。
// 不把运行时所用C++标准库的std::string对象跨ABI交给游戏。
void AssignString(lua_State*L,std::uintptr_t address){
 std::size_t length{};const auto*text=luaL_checklstring(L,3,&length);
 struct BorrowedString{std::uint64_t capacity,length;const char*data;};
 const BorrowedString source{(static_cast<std::uint64_t>(length)+1U)|1U,length,text};
 if(!engine_memory::EngineMemoryWritable(address,24))luaL_error(L,"ItemConfig native string is not writable");
 static api100_native::Cache cache{};
 const api100_native::Entry entry{api500_config::kStringAssignOffset,api500_config::kStringAssignGuard.data()};
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=engine_call::AddressOfFunction(g_StringAssignment);
#endif
 const auto target=api100_native::Resolve(L,entry,cache,host);
#if !defined(__SWITCH__)
 if(!host)luaL_error(L,"ItemConfig string assignment host binding unavailable");
#endif
 engine_call::AsFunction<void*(*)(void*,const void*)>(target)(engine_memory::AsObject(address),&source);
}
std::uintptr_t Costume(lua_State*L){
 auto*h=static_cast<CostumeHandle*>(luaL_checkudata(L,1,kCostumeMetatable));
 if(h->base!=LuaRuntime::EngineModuleBase())luaL_error(L,"Costume reference belongs to an old module");
 lua_getuservalue(L,1);const auto item=ItemConfigPointerArgument(L,-1);lua_pop(L,1);
 if(!item||item!=h->item)luaL_error(L,"Costume reference is no longer available");
 return item+0x80;
}
int Push(lua_State*L,std::uintptr_t p,const Field&f){Check(L,f);switch(f.kind){
 case Kind::Int:lua_pushinteger(L,Read<std::int32_t>(L,p,f.offset));break;
 case Kind::UInt:lua_pushinteger(L,Read<std::uint32_t>(L,p,f.offset));break;
 case Kind::Short:lua_pushinteger(L,Read<std::int16_t>(L,p,f.offset));break;
 case Kind::Bool:lua_pushboolean(L,Read<std::uint8_t>(L,p,f.offset)!=0);break;
 case Kind::String:return Api500PushConfigString(L,p+f.offset);
 default:lua_pushnil(L);break;}return 1;}
bool Write(lua_State*L,std::uintptr_t p,const Field&f){Check(L,f);
 if(f.kind==Kind::Costume||f.kind==Kind::Method){luaL_error(L,"ItemConfig field is read-only");return true;}
 if(f.kind==Kind::String){AssignString(L,p+f.offset);return true;}
 if(f.kind==Kind::Bool){Store<std::uint8_t>(L,p,f.offset,lua_toboolean(L,3)?1:0);return true;}
 const auto low=static_cast<std::uint32_t>(luaL_checkinteger(L,3));std::int32_t value{};std::memcpy(&value,&low,4);
 if(f.kind==Kind::Short){const auto bits=static_cast<std::uint16_t>(low);std::int16_t narrow{};std::memcpy(&narrow,&bits,2);Store(L,p,f.offset,narrow);}
 else if(f.kind==Kind::UInt)Store(L,p,f.offset,low);else Store(L,p,f.offset,value);
 return true;
}
int CostumeIndex(lua_State*L){if(lua_type(L,2)!=LUA_TSTRING){lua_pushnil(L);return 1;}const auto*f=Find(lua_tostring(L,2),Family::Costume);if(!f){lua_pushnil(L);return 1;}return Push(L,Costume(L),*f);}
int CostumeNewIndex(lua_State*L){const auto*name=luaL_checkstring(L,2);const auto*f=Find(name,Family::Costume);if(!f)return luaL_error(L,"unknown Costume field");Write(L,Costume(L),*f);return 0;}
int PushCostume(lua_State*L,std::uintptr_t p,const Field&f){
 Check(L,f);auto*h=static_cast<CostumeHandle*>(lua_newuserdata(L,sizeof(CostumeHandle)));*h={p,LuaRuntime::EngineModuleBase()};
 lua_pushvalue(L,1);lua_setuservalue(L,-2);
 if(luaL_newmetatable(L,kCostumeMetatable)){
  lua_pushcfunction(L,CostumeIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,CostumeNewIndex);lua_setfield(L,-2,"__newindex");
  lua_pushliteral(L,"ItemConfigCostume");lua_setfield(L,-2,"__name");lua_pushliteral(L,"ItemConfigCostume");lua_setfield(L,-2,"__type");lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");
 }
 lua_setmetatable(L,-2);return 1;
}
}
#if !defined(__SWITCH__)
void SetApi500ConfigStringAssignmentForTesting(Api500ConfigStringAssignment fn) noexcept{g_StringAssignment=fn;}
#endif
int Api500ItemConfigCardIsCard(lua_State*L){
 auto*h=static_cast<LuaRuntime::ItemConfigItemHandle*>(luaL_checkudata(L,1,LuaRuntime::kItemConfigItemMetatable));
 if(h->beginOffset!=0x48)return luaL_argerror(L,1,"ItemConfigCard expected");
 const auto p=Live(L,ItemConfigPointerArgument(L,1));const auto*f=Find("CardType",Family::Card);Check(L,*f);
 const auto type=Read<std::int32_t>(L,p,0x58);lua_pushboolean(L,type==0||type==1||type==3||type==5);return 1;
}
void Api500AssignConfigString(lua_State*L,std::uintptr_t address){AssignString(L,address);}
int TryPushApi500ConfigField(lua_State*L,std::uintptr_t item,std::uint32_t begin,const char*name){
 const auto*f=Find(name,Type(begin));if(!f)return 0;const auto p=Live(L,item);
 if(f->kind==Kind::Costume)return PushCostume(L,p,*f);
 if(f->kind==Kind::Method){PushHandler(L,kApi500CardBindings[0].handler,0,kApi500CardBindings[0].id);return 1;}
 return Push(L,p,*f);
}
bool TryWriteApi500ConfigField(lua_State*L,std::uintptr_t item,std::uint32_t begin,const char*name){
 const auto*f=Find(name,Type(begin));if(!f)return false;return Write(L,Live(L,item),*f);
}
}
