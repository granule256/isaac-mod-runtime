#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/api600_player.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "interfaces/lua/opaque_scalar_value.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace G=api600_player;
using Vec=LuaRuntime::VectorHandle;
constexpr char kTear[]="IsaacRuntime.TearParams";
constexpr char kMulti[]="IsaacRuntime.MultiShotParams";
constexpr char kPosVel[]="IsaacRuntime.PlayerTypesPosVel";
constexpr char kDesc[]="IsaacRuntime.ConstEntityDesc";
constexpr char kBabySkin[]="IsaacRuntime.BabySubTypeValue";
api100_native::Cache g_BabySkinLayout{};
void BabySkinLayout(lua_State* L) {
 // 原生init_baby_skin直接读Player+0x20e8；PC getter859540复制独立4B值。
 static constexpr std::uint8_t bytes[]={0x02,0xe8,0x60,0xb9,0x09,0xf1,0x8c,0x52,0x69,0x00,0xa0,0x72,0xf3,0x03,0x00,0xaa};
 static_cast<void>(api100_native::Resolve(L,{0x27b064,bytes},g_BabySkinLayout));
}
constexpr api100_native::Entry kLayouts[]={
 {G::kConstructorGuardOffset,G::kConstructorGuard.data()},
 {G::kInitGuardOffset,G::kInitGuard.data()},
 {G::kActiveGuardOffset,G::kActiveGuard.data()},
 {G::kShootGuardOffset,G::kShootGuard.data()},
 {G::kEvaluateGuardOffset,G::kEvaluateGuard.data()},
 {G::kWeaponGuardOffset,G::kWeaponGuard.data()}};
constexpr api100_native::Entry kNatives[]={
 {G::kTearGuardOffset,G::kTearGuard.data()},
 {G::kMultiGuardOffset,G::kMultiGuard.data()},
 {G::kPosVelGuardOffset,G::kPosVelGuard.data()},
 {G::kBombGuardOffset,G::kBombGuard.data()}};
api100_native::Cache g_Layouts[6]{},g_Natives[4]{};
#if !defined(__SWITCH__)
Api600PlayerNativeTestBindings g_Tests{};
#endif
void Guard(lua_State*L,unsigned n){static_cast<void>(api100_native::Resolve(L,kLayouts[n],g_Layouts[n]));}
void Layout(lua_State*L){Guard(L,0);Guard(L,1);}
template<class Fn>Fn Native(lua_State*L,unsigned n){
 const auto guarded=api100_native::Resolve(L,kNatives[n],g_Natives[n]);
#if !defined(__SWITCH__)
 if(g_Tests.methods[n])return engine_call::AsFunction<Fn>(g_Tests.methods[n]);
#endif
 return engine_call::AsFunction<Fn>(guarded-(n==3?0:16));
}
std::uintptr_t Player(lua_State*L,int index=1){
 luaL_checkudata(L,index,LuaRuntime::kEntityPlayerMetatable);
 const auto p=ResolveEngineReceiver(L,FieldReceipt::EntityPlayer,index);
 if(!p){luaL_error(L,"EntityPlayer reference is no longer available");}
 return p;
}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned o){T v{};if(!engine_memory::ReadField(p,o,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"api600 player field is not readable");return v;}
template<class T>void Write(lua_State*L,std::uintptr_t p,unsigned o,const T&v){if(!engine_memory::WriteField(p,o,v,engine_memory::EngineMemoryWritable))luaL_error(L,"api600 player field is not writable");}
std::int32_t Int(lua_State*L,int i){const auto u=static_cast<std::uint32_t>(luaL_checkinteger(L,i));std::int32_t s;std::memcpy(&s,&u,4);return s;}
int DefaultInt(lua_State*L,int i,int d){return lua_toboolean(L,i)?Int(L,i):d;}
bool Flags(lua_State*L,int i,BitSet128Value*v){if(ReadBitSet128(L,i,v))return true;if(lua_isinteger(L,i)){*v={static_cast<std::uint64_t>(lua_tointeger(L,i)),0};return true;}return false;}
template<class T>T At(const void*p,unsigned o){T v;std::memcpy(&v,static_cast<const unsigned char*>(p)+o,sizeof(v));return v;}
template<class T>void Put(void*p,unsigned o,const T&v){std::memcpy(static_cast<unsigned char*>(p)+o,&v,sizeof(v));}
template<class T>void PushOwned(lua_State*L,const char*mt,const T&v){auto*p=static_cast<T*>(lua_newuserdata(L,sizeof(T)));*p=v;luaL_getmetatable(L,mt);lua_setmetatable(L,-2);}
// 这些userdata内联保存完整NS值，不含借用包装头；身份只取其实际native存储。
std::uintptr_t TearIdentity(lua_State*L,int index)noexcept {
 if(lua_rawlen(L,index)!=sizeof(Api600TearParams))return 0;
 return engine_memory::AddressOf(static_cast<const Api600TearParams*>(lua_touserdata(L,index))->bytes);
}
std::uintptr_t MultiIdentity(lua_State*L,int index)noexcept {
 if(lua_rawlen(L,index)!=sizeof(Api600MultiShotParams))return 0;
 return engine_memory::AddressOf(static_cast<const Api600MultiShotParams*>(lua_touserdata(L,index))->bytes);
}
std::uintptr_t PosVelIdentity(lua_State*L,int index)noexcept {
 if(lua_rawlen(L,index)!=sizeof(Api600PosVel))return 0;
 return engine_memory::AddressOf(&static_cast<const Api600PosVel*>(lua_touserdata(L,index))->positionX);
}
enum class Kind:unsigned char{Int,Float,Color,Flags};
struct Field{const char*name;unsigned offset;Kind kind;};
constexpr Field kTearFields[]={
 {"TearVariant",0,Kind::Int},{"BombVariant",4,Kind::Int},{"TearColor",8,Kind::Color},
 {"TearFlags",0x38,Kind::Flags},{"TearDamage",0x48,Kind::Float},
 {"TearScale",0x4c,Kind::Float},{"TearHeight",0x50,Kind::Float}};
const Field* TearField(const char*n){if(n)for(const auto&f:kTearFields)if(!std::strcmp(n,f.name))return &f;return nullptr;}
int TearIndex(lua_State*L){const auto*p=luaL_checkudata(L,1,kTear);const auto*f=TearField(lua_tostring(L,2));if(!f){lua_pushnil(L);return 1;}
 switch(f->kind){case Kind::Int:lua_pushinteger(L,At<std::int32_t>(p,f->offset));break;case Kind::Float:lua_pushnumber(L,At<float>(p,f->offset));break;case Kind::Color:PushLuaColorFromEngineColorMod(L,At<EngineColorMod>(p,f->offset));break;case Kind::Flags:PushBitSet128(L,At<BitSet128Value>(p,f->offset));break;}return 1;}
int TearNewIndex(lua_State*L){auto*p=luaL_checkudata(L,1,kTear);const auto*f=TearField(lua_tostring(L,2));if(!f)return luaL_error(L,"unknown TearParams field");
 switch(f->kind){case Kind::Int:Put(p,f->offset,Int(L,3));break;case Kind::Float:Put(p,f->offset,static_cast<float>(luaL_checknumber(L,3)));break;case Kind::Color:{EngineColorMod c{};if(!FillEngineColorMod(L,3,&c))return luaL_argerror(L,3,"expected Color");Put(p,f->offset,c);break;}case Kind::Flags:{BitSet128Value b{};if(!Flags(L,3,&b))return luaL_argerror(L,3,"expected BitSet128 or integer");Put(p,f->offset,b);break;}}return 0;}
int OpaqueIndex(lua_State*L){luaL_checkudata(L,1,kMulti);return NativeClassMethodIndex(L);}
int OpaqueNewIndex(lua_State*L){luaL_checkudata(L,1,kMulti);return luaL_error(L,"MultiShotParams has no public writable fields");}
// Switch GetMultiShotParams writes backwards at +0x1d (Mom's Eye) and sideways at +0x1e (Loki's Horns).
int MultiShotFlag(lua_State*L,unsigned offset){
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 const auto*p=static_cast<const Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 lua_pushboolean(L,At<std::uint8_t>(p->bytes,offset)!=0);return 1;
}
int PosVelIndex(lua_State*L){const auto*p=static_cast<Api600PosVel*>(luaL_checkudata(L,1,kPosVel));const char*n=lua_tostring(L,2);if(n&&!std::strcmp(n,"Position"))PushLuaVector(L,p->positionX,p->positionY);else if(n&&!std::strcmp(n,"Velocity"))PushLuaVector(L,p->velocityX,p->velocityY);else lua_pushnil(L);return 1;}
int PosVelNewIndex(lua_State*L){auto*p=static_cast<Api600PosVel*>(luaL_checkudata(L,1,kPosVel));const char*n=lua_tostring(L,2);if(n&&!std::strcmp(n,"Position")){const auto v=*RequireVectorArgument(L,3);p->positionX=v.x;p->positionY=v.y;}else if(n&&!std::strcmp(n,"Velocity")){const auto v=*RequireVectorArgument(L,3);p->velocityX=v.x;p->velocityY=v.y;}else return luaL_error(L,"unknown PosVel field");return 0;}
struct DescRef{LuaRuntime::EntityLifetimeToken*lifetime;std::uintptr_t entity,base;};
struct DescValue{unsigned char bytes[28];};
// 公开消费与hash共享无抛错判据：先拒短userdata，再核token/base/真实player及原生28B范围。
std::uintptr_t DescAddress(lua_State*L,int index)noexcept {
 if(lua_rawlen(L,index)!=sizeof(DescRef))return 0;
 const auto*view=static_cast<const DescRef*>(lua_touserdata(L,index));
 const auto base=LuaRuntime::EngineModuleBase();
 if(!view->lifetime||!EntityLifetimeAlive(view->lifetime)||!base||view->base!=base||
    view->entity>UINTPTR_MAX-0x1d88||!IsLiveEntityPointer(view->entity))return 0;
 std::uintptr_t vtable{};std::uint32_t type{};
 if(base>UINTPTR_MAX-kEntityPlayerVtableOffset||
    !engine_memory::ReadField(view->entity,0,&vtable,engine_memory::EngineMemoryReadable)||
    vtable!=base+kEntityPlayerVtableOffset||
    !engine_memory::ReadField(view->entity,kEntityTypeOffset,&type,engine_memory::EngineMemoryReadable)||
    type!=kEntityTypePlayer)return 0;
 const auto address=view->entity+0x1d88;
 return engine_memory::EngineMemoryReadable(address,sizeof(DescValue))?address:0;
}
DescRef* Desc(lua_State*L,int i){auto*p=static_cast<DescRef*>(luaL_checkudata(L,i,kDesc));if(!DescAddress(L,i))luaL_error(L,"EntityDesc reference owner is no longer available");return p;}
int DescIndex(lua_State*L){static_cast<void>(Desc(L,1));lua_pushnil(L);return 1;}
int DescNewIndex(lua_State*L){static_cast<void>(Desc(L,1));return luaL_error(L,"EntityDesc has no public writable fields");}
void PushDesc(lua_State*L,std::uintptr_t p){auto*t=PushEntityLifetimeToken(L,p);const int token=lua_gettop(L);auto*v=static_cast<DescRef*>(lua_newuserdata(L,sizeof(DescRef)));*v={t,p,LuaRuntime::EngineModuleBase()};luaL_getmetatable(L,kDesc);lua_setmetatable(L,-2);lua_pushvalue(L,token);lua_setuservalue(L,-2);lua_remove(L,token);}
constexpr std::uint32_t Hash(const char*n){std::uint32_t h=2166136261U;while(*n)h=(h^static_cast<unsigned char>(*n++))*16777619U;return h;}
enum class PlayerField:unsigned char{None,Head,IBS,Samson,Color,Offset,Desc,Delay,BabySkin};
PlayerField Find(std::uintptr_t p,const char*n){
 if(!n||!n[0]||!n[1])return PlayerField::None;
 const unsigned prefix=(static_cast<unsigned>(static_cast<unsigned char>(n[0]))<<8)|static_cast<unsigned char>(n[1]);
 switch(prefix){case 0x4865:case 0x4942:case 0x5361:case 0x4c61:case 0x5465:case 0x4672:case 0x4669:case 0x4261:break;default:return PlayerField::None;}
 PlayerField f{};const char*expected{};
 switch(Hash(n)){
 case Hash("HeadFrameDelay"):f=PlayerField::Head;expected="HeadFrameDelay";break;
 case Hash("IBSCharge"):f=PlayerField::IBS;expected="IBSCharge";break;
 case Hash("SamsonBerserkCharge"):f=PlayerField::Samson;expected="SamsonBerserkCharge";break;
 case Hash("LaserColor"):f=PlayerField::Color;expected="LaserColor";break;
 case Hash("TearsOffset"):f=PlayerField::Offset;expected="TearsOffset";break;
 case Hash("FriendBallEnemy"):f=PlayerField::Desc;expected="FriendBallEnemy";break;
 case Hash("FireDelay"):f=PlayerField::Delay;expected="FireDelay";break;
 case Hash("BabySkin"):f=PlayerField::BabySkin;expected="BabySkin";break;
 default:return PlayerField::None;}
 if(std::strcmp(n,expected)||ClassifyCallbackEntity(p)!=CallbackEntityClass::Player){return PlayerField::None;}
 return f;
}
std::uintptr_t Weapon(lua_State*L,std::uintptr_t p){auto w=Read<std::uintptr_t>(L,p,0x1758);return w?w:Read<std::uintptr_t>(L,p,0x1760);}
void Type(lua_State*L,const char*mt,lua_CFunction index,lua_CFunction write,NativeObjectIdentityResolver identity){luaL_newmetatable(L,mt);if(!RegisterNativeObjectIdentity(L,-1,identity))luaL_error(L,"native identity resolver conflicts for %s",mt);lua_pushcfunction(L,index);lua_setfield(L,-2,"__index");lua_pushcfunction(L,write);lua_setfield(L,-2,"__newindex");lua_pop(L,1);}
}
int Api600MultiShotParamsIsShootingBackwards(lua_State*L){return MultiShotFlag(L,0x1d);}
int Api600MultiShotParamsIsShootingSideways(lua_State*L){return MultiShotFlag(L,0x1e);}
#if !defined(__SWITCH__)
void SetApi600PlayerNativeTestBindings(Api600PlayerNativeTestBindings v)noexcept{g_Tests=v;}
#endif
void RegisterApi600PlayerTypes(lua_State*L){
 Type(L,kTear,TearIndex,TearNewIndex,TearIdentity);PublishNativeClass(L,"TearParams",kTear);
 Type(L,kMulti,OpaqueIndex,OpaqueNewIndex,MultiIdentity);
 luaL_getmetatable(L,kMulti);lua_newtable(L);
 static_cast<void>(AttachOwnerMethods(L,"MultiShotParams",nullptr,0));
 lua_setfield(L,-2,"__methods");lua_pop(L,1);PublishNativeClass(L,"MultiShotParams",kMulti);
 Type(L,kPosVel,PosVelIndex,PosVelNewIndex,PosVelIdentity);PublishNativeClass(L,"PlayerTypesPosVel",kPosVel);
 Type(L,kDesc,DescIndex,DescNewIndex,DescAddress);PublishNativeClass(L,"EntityDesc",kDesc);
}
int TryPushApi600PlayerField(lua_State*L,std::uintptr_t p,const char*n){const auto f=Find(p,n);if(f==PlayerField::None)return 0;Layout(L);
 switch(f){case PlayerField::Head:Guard(L,3);lua_pushinteger(L,Read<std::int32_t>(L,p,0x16b0));break;
 case PlayerField::IBS:lua_pushnumber(L,Read<float>(L,p,0x2844));break;
 case PlayerField::Samson:lua_pushinteger(L,Read<std::int32_t>(L,p,0x2840));break;
 case PlayerField::Color:Guard(L,4);PushLuaColorFromEngineColorMod(L,Read<EngineColorMod>(L,p,0x1894));break;
 case PlayerField::Offset:PushEntityVectorReference(L,p,0x1a20);break;
 case PlayerField::Desc:Guard(L,3);PushDesc(L,p);break;
 case PlayerField::Delay:{Guard(L,3);Guard(L,5);const auto w=Weapon(L,p);lua_pushnumber(L,w?Read<float>(L,w,0x18):0);break;}
 case PlayerField::BabySkin:BabySkinLayout(L);PushOpaqueScalarValue(L,kBabySkin,"BabySubType",Read<std::int32_t>(L,p,0x20e8));break;
 case PlayerField::None:break;}return 1;}
bool TryWriteApi600PlayerField(lua_State*L,std::uintptr_t p,const char*n){const auto f=Find(p,n);if(f==PlayerField::None)return false;Layout(L);
 switch(f){case PlayerField::Head:Guard(L,3);Write(L,p,0x16b0,Int(L,3));break;
 case PlayerField::IBS:Write(L,p,0x2844,static_cast<float>(luaL_checknumber(L,3)));break;
 case PlayerField::Samson:Write(L,p,0x2840,Int(L,3));break;
 case PlayerField::Color:{Guard(L,4);EngineColorMod c{};if(!FillEngineColorMod(L,3,&c))luaL_argerror(L,3,"expected Color");Write(L,p,0x1894,c);break;}
 case PlayerField::Offset:Write(L,p,0x1a20,*RequireVectorArgument(L,3));break;
 case PlayerField::Desc:{Guard(L,3);const auto*source=Desc(L,3);Write(L,p,0x1d88,Read<DescValue>(L,source->entity,0x1d88));break;}
 case PlayerField::Delay:{Guard(L,3);Guard(L,5);const auto v=static_cast<float>(luaL_checknumber(L,3));const auto w=Weapon(L,p);if(w)Write(L,w,0x18,v);break;}
 case PlayerField::BabySkin:BabySkinLayout(L);Write(L,p,0x20e8,RequireOpaqueScalarValue<std::int32_t>(L,3,kBabySkin));break;
 case PlayerField::None:break;}return true;}
int Api600EntityPlayerGetTearHitParams(lua_State*L){auto*p=engine_memory::AsObject(Player(L));const auto weapon=Int(L,2);const auto scale=lua_toboolean(L,3)?static_cast<float>(luaL_checknumber(L,3)):1.0F;const auto displacement=DefaultInt(L,4,1);std::uintptr_t source{};if(!lua_isnoneornil(L,5)){source=EntityPointerArgument(L,5);if(!source)luaL_argerror(L,5,"expected a live Entity or nil");}
 const auto value=Native<Api600TearParams(*)(void*,std::int32_t,float,std::int32_t,void*)>(L,0)(p,weapon,scale,displacement,engine_memory::AsObject(source));PushOwned(L,kTear,value);return 1;}
int Api600EntityPlayerGetMultiShotParams(lua_State*L){auto*p=engine_memory::AsObject(Player(L));const auto weapon=DefaultInt(L,2,1);const auto value=Native<Api600MultiShotParams(*)(void*,std::int32_t)>(L,1)(p,weapon);PushOwned(L,kMulti,value);return 1;}
int Api600MultiShotParamsGetNumTears(lua_State*L){
 if(lua_gettop(L)!=1)return luaL_error(L,"MultiShotParams:GetNumTears accepts no arguments");
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 const auto*p=static_cast<const Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 lua_pushinteger(L,At<std::int16_t>(p->bytes,kApi600MultiShotNumTearsOffset));return 1;
}
int Api600MultiShotParamsSetNumTears(lua_State*L){
 if(lua_gettop(L)!=2)return luaL_error(L,"MultiShotParams:SetNumTears accepts one integer");
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 auto*p=static_cast<Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 Put(p->bytes,kApi600MultiShotNumTearsOffset,static_cast<std::int16_t>(luaL_checkinteger(L,2)));return 0;
}
int Api600MultiShotParamsGetNumEyesActive(lua_State*L){
 if(lua_gettop(L)!=1)return luaL_error(L,"MultiShotParams:GetNumEyesActive accepts no arguments");
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 const auto*p=static_cast<const Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 lua_pushinteger(L,At<std::int32_t>(p->bytes,kApi600MultiShotNumEyesActiveOffset));return 1;
}
int Api600MultiShotParamsGetMultiEyeAngle(lua_State*L){
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 const auto*p=static_cast<const Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 lua_pushnumber(L,At<float>(p->bytes,kApi600MultiShotMultiEyeAngleOffset));return 1;
}
int Api600MultiShotParamsGetNumRandomDirTears(lua_State*L){
 if(lua_gettop(L)!=1)return luaL_error(L,"MultiShotParams:GetNumRandomDirTears accepts no arguments");
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 const auto*p=static_cast<const Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 lua_pushinteger(L,At<std::int16_t>(p->bytes,kApi600MultiShotNumRandomDirTearsOffset));return 1;
}
int Api600MultiShotParamsIsCrossEyed(lua_State*L){
 return MultiShotFlag(L,kApi600MultiShotIsCrossEyedOffset);
}
int Api600MultiShotParamsGetNumLanesPerEye(lua_State*L){
 if(lua_gettop(L)!=1)return luaL_error(L,"MultiShotParams:GetNumLanesPerEye accepts no arguments");
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 const auto*p=static_cast<const Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 lua_pushinteger(L,At<std::int16_t>(p->bytes,kApi600MultiShotNumLanesPerEyeOffset));return 1;
}
int Api600MultiShotParamsSetNumLanesPerEye(lua_State*L){
 if(lua_gettop(L)!=2)return luaL_error(L,"MultiShotParams:SetNumLanesPerEye accepts one integer");
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 auto*p=static_cast<Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 Put(p->bytes,kApi600MultiShotNumLanesPerEyeOffset,static_cast<std::int16_t>(luaL_checkinteger(L,2)));return 0;
}
int Api600MultiShotParamsGetSpreadAngle(lua_State*L){
 if(lua_gettop(L)!=2)return luaL_error(L,"MultiShotParams:GetSpreadAngle accepts one weapon type");
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 const auto*p=static_cast<const Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 const auto weapon=Int(L,2);float value{};
 switch(weapon){
  case 1:case 5:value=At<float>(p->bytes,kApi600MultiShotSpreadAngleTearsOffset);break;
  case 2:case 3:value=At<float>(p->bytes,kApi600MultiShotSpreadAngleLaserOffset);break;
  case 4:value=At<float>(p->bytes,kApi600MultiShotSpreadAngleKnifeOffset);break;
  case 9:case 14:value=At<float>(p->bytes,kApi600MultiShotSpreadAngleTechXOffset);break;
  case 10:case 11:value=At<float>(p->bytes,kApi600MultiShotSpreadAngleKnifeOffset)*3.0F;break;
  case 6:case 7:case 8:case 12:case 13:case 15:value=0.0F;break;
  default:return luaL_error(L,"WeaponTypes bigger 15 are not supported!");
 }
 lua_pushnumber(L,value);return 1;
}
int Api600MultiShotParamsSetSpreadAngle(lua_State*L){
 if(lua_gettop(L)!=3)return luaL_error(L,"MultiShotParams:SetSpreadAngle accepts a weapon type and angle");
 if(lua_rawlen(L,1)!=sizeof(Api600MultiShotParams))return luaL_argerror(L,1,"MultiShotParams expected");
 auto*p=static_cast<Api600MultiShotParams*>(luaL_checkudata(L,1,kMulti));
 const auto weapon=Int(L,2);const auto target=static_cast<float>(luaL_checknumber(L,3));
 switch(weapon){
  case 1:case 5:Put(p->bytes,kApi600MultiShotSpreadAngleTearsOffset,target);break;
  case 2:case 3:Put(p->bytes,kApi600MultiShotSpreadAngleLaserOffset,target);break;
  case 4:Put(p->bytes,kApi600MultiShotSpreadAngleKnifeOffset,target);break;
  case 9:case 14:Put(p->bytes,kApi600MultiShotSpreadAngleTechXOffset,target);break;
  case 10:case 11:Put(p->bytes,kApi600MultiShotSpreadAngleKnifeOffset,target/3.0F);break;
  case 6:case 7:case 8:case 12:case 13:case 15:
   return luaL_error(L,"The given WeaponType cant change its spread angle!");
  default:return luaL_error(L,"A WeaponType bigger 15 is not supported!");
 }
 if(At<std::int16_t>(p->bytes,kApi600MultiShotNumLanesPerEyeOffset)<2)
  Put(p->bytes,kApi600MultiShotNumLanesPerEyeOffset,static_cast<std::int16_t>(2));
 return 0;
}
bool PushApi600MultiShotParamsSnapshot(lua_State*L,const Api600MultiShotParams&value){
 if(!L)return false;
 PushOwned(L,kMulti,value);
 return true;
}
bool ReadApi600MultiShotParamsSnapshot(lua_State*L,int index,Api600MultiShotParams*value){
 if(!L||!value||lua_rawlen(L,index)!=sizeof(Api600MultiShotParams))return false;
 const auto*p=static_cast<const Api600MultiShotParams*>(luaL_testudata(L,index,kMulti));
 if(!p)return false;
 *value=*p;
 return true;
}
int Api600EntityPlayerGetMultiShotPositionVelocity(lua_State*L){
 // PC wrapper838140 has loop/weapon/vector/speed/params at1..5 and no receiver.
 // Also accept the documented colon shape without passing an invented this to NS.
 int first=1;if(luaL_testudata(L,1,LuaRuntime::kEntityPlayerMetatable)){static_cast<void>(Player(L));first=2;}
 const auto loop=Int(L,first);const auto weapon=Int(L,first+1);const auto direction=*RequireVectorArgument(L,first+2);const auto speed=static_cast<float>(luaL_checknumber(L,first+3));const auto*params=static_cast<Api600MultiShotParams*>(luaL_checkudata(L,first+4,kMulti));
 const auto value=Native<Api600PosVel(*)(std::int32_t,std::int32_t,Vec,float,Api600MultiShotParams)>(L,2)(loop,weapon,direction,speed,*params);PushOwned(L,kPosVel,value);return 1;}
int Api600EntityPlayerGetActiveSubCharge(lua_State*L){const auto p=Player(L);const auto slot=DefaultInt(L,2,0);if(slot<0||slot>3)luaL_argerror(L,2,"active slot must be in range 0..3");Layout(L);Guard(L,2);lua_pushinteger(L,Read<std::int32_t>(L,p,0x1970+static_cast<unsigned>(slot)*0x1c));return 1;}
int Api600EntityPlayerAreOpposingShootDirectionsPressed(lua_State*L){const auto p=Player(L);Layout(L);Guard(L,3);lua_pushboolean(L,Read<std::uint8_t>(L,p,0x1a0c)!=0);return 1;}
int Api600EntityPlayerHasWeaponType(lua_State*L){const auto p=Player(L);const auto weapon=Int(L,2);if(weapon<0||weapon>=16)luaL_argerror(L,2,"weapon type must be in range 0..15");Layout(L);Guard(L,4);lua_pushboolean(L,Read<std::uint8_t>(L,p,0x1780+static_cast<unsigned>(weapon))!=0);return 1;}
int Api600EntityPlayerGetBombVariant(lua_State*L){auto*p=engine_memory::AsObject(Player(L));BitSet128Value flags{};if(!Flags(L,2,&flags))luaL_argerror(L,2,"expected BitSet128 or integer");const bool rocket=lua_toboolean(L,3)!=0;lua_pushinteger(L,Native<std::int32_t(*)(void*,BitSet128Value,bool)>(L,3)(p,flags,rocket));return 1;}
}

namespace isaac::runtime {
std::uintptr_t Api600EntityDescArgument(lua_State*L,int index){const auto*view=Desc(L,index);Guard(L,3);const auto address=view->entity+0x1d88;if(!engine_memory::EngineMemoryReadable(address,sizeof(DescValue)))luaL_error(L,"EntityDesc reference is not readable");return address;}
}
