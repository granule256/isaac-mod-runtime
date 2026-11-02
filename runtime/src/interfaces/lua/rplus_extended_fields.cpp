#include "interfaces/lua/rplus_extended_fields.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace guards=extended_fields;
enum class Group:unsigned {Entity,Sprite,Familiar,Pickup,Effect,Tear,Projectile,Bomb,Player,Item,SetTarget,SetChild,SetHeight,Descriptor,SetParent,SetEntityRef,Count};
struct Cache {std::uintptr_t base{};bool valid{};};
Cache g_Guards[static_cast<unsigned>(Group::Count)]{};
constexpr std::uintptr_t kSetEntityRefEntry=0x11fb70;
constexpr std::array<std::uint8_t,16> kSetEntityRefGuard={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x1,0xa9,0xfd,0x3,0x0,0x91,0xf4,0x4f,0x2,0xa9};
#if !defined(__SWITCH__)
ExtendedFieldsNativeTestBindings g_Tests{};
#endif
template<std::size_t N>bool Guard(std::uintptr_t base,std::uintptr_t offset,const std::array<std::uint8_t,N>& bytes) {
 return base&&base<=UINTPTR_MAX-offset-N&&engine_memory::EngineMemoryReadable(base+offset,N)&&!std::memcmp(engine_memory::AsObject(base+offset),bytes.data(),N);
}
void Check(lua_State* state,Group group){
 const auto index=static_cast<unsigned>(group);
 if(index>=static_cast<unsigned>(Group::Count)){luaL_error(state,"invalid extended field guard group");return;}
 auto&cache=g_Guards[index];const auto base=LuaRuntime::EngineModuleBase();
 if(cache.base!=base){cache.base=base;
#define G(name,n) Guard(base,guards::k##name##n##Entry,guards::k##name##n##Guard)
 switch(group){
 case Group::Entity:cache.valid=G(Entity,0)&&G(Entity,1)&&G(Entity,2);break;
 case Group::Sprite:cache.valid=G(Sprite,0)&&G(Sprite,1)&&G(Sprite,2);break;
 case Group::Familiar:cache.valid=G(Familiar,0)&&G(Familiar,1)&&G(Familiar,2)&&G(Familiar,3)&&G(Familiar,4);break;
 case Group::Pickup:cache.valid=G(Pickup,0)&&G(Pickup,1)&&G(Pickup,2);break;
 case Group::Effect:cache.valid=G(Effect,0)&&G(Effect,1)&&G(Effect,2);break;
 case Group::Tear:cache.valid=G(Tear,0)&&G(Tear,1)&&G(Tear,2);break;
 case Group::Projectile:cache.valid=G(Projectile,0);break;
 case Group::Bomb:cache.valid=G(Bomb,0);break;
 case Group::Player:cache.valid=G(Player,0);break;
 case Group::Item:cache.valid=G(Item,0)&&G(Item,1);break;
 case Group::SetTarget:cache.valid=G(SetTarget,0);break;
 case Group::SetChild:cache.valid=G(SetChild,0);break;
 case Group::SetParent:cache.valid=G(SetParent,0);break;
 case Group::SetEntityRef:cache.valid=Guard(base,kSetEntityRefEntry,kSetEntityRefGuard);break;
 case Group::SetHeight:cache.valid=G(SetHeight,0);break;
 case Group::Descriptor:cache.valid=G(Descriptor,0);break;
 case Group::Count:cache.valid=false;break;
 }
#undef G
 }
 if(!cache.valid)luaL_error(state,"native extended field layout guard mismatch");
}
template<class T>T Read(lua_State* state,std::uintptr_t object,std::uintptr_t offset){T value{};
 if(!engine_memory::ReadField(object,offset,&value,engine_memory::EngineMemoryReadable))luaL_error(state,"native extended field is not readable");
 return value;}
template<class T>void Write(lua_State* state,std::uintptr_t object,std::uintptr_t offset,const T&value){
 if(!engine_memory::WriteField(object,offset,value,engine_memory::EngineMemoryWritable))luaL_error(state,"native extended field is not writable");}
std::int32_t Integer(lua_State*state){const auto low=static_cast<std::uint32_t>(luaL_checkinteger(state,3));std::int32_t value{};std::memcpy(&value,&low,4);return value;}
enum class Kind:std::uint8_t {None,Int,Float,Bool,Vector,Color,Target,Child,Height,Parent,UInt,EntityReference};
enum class Field:std::uint8_t {None,SpriteOffset,SpriteScale,Target,Child,DepthOffset,EntityCollisionClass,GridCollisionClass,SplatColor,FireCooldown,RoomClearCount,Hearts,IsFollower,Keys,State,Timeout,Wait,Charge,FallingSpeed,FallingAcceleration,Rotation,EffectHeight,Height,KnockbackMultiplier,ExplosionDamage,ItemHoldCooldown,Parent,Touched,EntityRef};
Field Name(const char*name){
 if(!name)return Field::None;
#define N(x) if(!std::strcmp(name,#x))return Field::x
 switch(name[0]){
 case 'S':N(SpriteOffset);N(SpriteScale);N(SplatColor);N(State);break;
 case 'T':N(Target);N(Timeout);N(Touched);break;
 case 'C':N(Child);N(Charge);break;
 case 'P':if(name[1]=='a'){N(Parent);}break;
 case 'D':N(DepthOffset);break;
 case 'E':N(EntityCollisionClass);N(ExplosionDamage);N(EntityRef);break;
 case 'G':N(GridCollisionClass);break;
 case 'F':N(FireCooldown);N(FallingSpeed);N(FallingAcceleration);break;
 case 'R':N(RoomClearCount);N(Rotation);break;
 case 'H':N(Hearts);N(Height);break;
 case 'I':N(IsFollower);N(ItemHoldCooldown);break;
 case 'K':N(Keys);N(KnockbackMultiplier);break;
 case 'W':N(Wait);break;
 case 'm':if(!std::strcmp(name,"m_Height"))return Field::EffectHeight;break;
 default:break;
 }
#undef N
 return Field::None;
}
struct Row {Kind kind{Kind::None};std::uintptr_t offset{};Group group{Group::Entity};};
Row Layout(std::uintptr_t entity,Field field){
 // 基类字段不分类；只有精确命中的专属字段才分类一次。
 switch(field){
 case Field::SpriteOffset:return {Kind::Vector,0x124,Group::Sprite};
 case Field::SpriteScale:return {Kind::Vector,0x12C,Group::Sprite};
 case Field::Target:return {Kind::Target,0x3A0,Group::Entity};
 case Field::Child:return {Kind::Child,0x398,Group::Entity};
 case Field::Parent:return {Kind::Parent,0x390,Group::Entity};
 case Field::DepthOffset:return {Kind::Float,0x32C,Group::Entity};
 case Field::EntityCollisionClass:return {Kind::Int,0x1E0,Group::Entity};
 case Field::GridCollisionClass:return {Kind::Int,0x1E4,Group::Entity};
 case Field::SplatColor:return {Kind::Color,0x24C,Group::Entity};
 default:break;
 }
 const auto type=ClassifyCallbackEntity(entity);
 if(type==CallbackEntityClass::Familiar){
 switch(field){
 case Field::FireCooldown:return {Kind::Int,0xD60,Group::Familiar};
 case Field::RoomClearCount:return {Kind::Int,0xD9C,Group::Familiar};
 case Field::Hearts:return {Kind::Int,0xD90,Group::Familiar};
 case Field::IsFollower:return {Kind::Bool,0xD88,Group::Familiar};
 case Field::Keys:return {Kind::Int,0xD94,Group::Familiar};
 case Field::State:return {Kind::Int,0xD98,Group::Familiar};
 default:break;
 }}
 if(type==CallbackEntityClass::Pickup){
 switch(field){
 // PC859860→7f8840零扩展；只更正Pickup.State，不改变其它族State。
 case Field::State:return {Kind::UInt,0x5B8,Group::Pickup};
 case Field::Touched:return {Kind::Bool,0x560,Group::Pickup};
 case Field::Timeout:return {Kind::Int,0x570,Group::Pickup};
 case Field::Wait:return {Kind::Int,0x574,Group::Pickup};
 case Field::Charge:return {Kind::Int,0x558,Group::Pickup};
 default:break;
 }}
 if(type==CallbackEntityClass::Effect){
 switch(field){
 case Field::FallingSpeed:return {Kind::Float,0x404,Group::Effect};
 case Field::FallingAcceleration:return {Kind::Float,0x408,Group::Effect};
 case Field::EffectHeight:return {Kind::Float,0x400,Group::Effect};
 case Field::State:return {Kind::Int,0x448,Group::Effect};
 case Field::Timeout:return {Kind::Int,0x454,Group::Effect};
 case Field::Rotation:return {Kind::Float,0x46C,Group::Effect};
 default:break;
 }}
 if(type==CallbackEntityClass::Tear){
 switch(field){
 case Field::Height:return {Kind::Height,0x400,Group::Tear};
 case Field::Rotation:return {Kind::Float,0x458,Group::Tear};
 case Field::KnockbackMultiplier:return {Kind::Float,0x460,Group::Tear};
 default:break;
 }}
 if(type==CallbackEntityClass::Projectile&&field==Field::Height)return {Kind::Float,0x400,Group::Projectile};
 // NPC+c20是注册到target回链树的EHandle，写侧不能把它当普通Entity*槽裸写。
 if(type==CallbackEntityClass::Npc&&field==Field::EntityRef)return {Kind::EntityReference,0xC20,Group::SetEntityRef};
 if(type==CallbackEntityClass::Bomb&&field==Field::ExplosionDamage)return {Kind::Float,0x408,Group::Bomb};
 if(type==CallbackEntityClass::Player&&field==Field::ItemHoldCooldown)return {Kind::Int,0x1D6C,Group::Player};
 return {};
}
int Push(lua_State*state,std::uintptr_t object,const Row&row){
 Check(state,row.group);
 switch(row.kind){
 case Kind::Int:lua_pushinteger(state,Read<std::int32_t>(state,object,row.offset));break;
 case Kind::UInt:lua_pushinteger(state,Read<std::uint32_t>(state,object,row.offset));break;
 case Kind::Float:case Kind::Height:lua_pushnumber(state,Read<float>(state,object,row.offset));break;
 case Kind::Bool:lua_pushboolean(state,Read<std::uint8_t>(state,object,row.offset)!=0);break;
 case Kind::Vector:{const auto value=Read<LuaRuntime::VectorHandle>(state,object,row.offset);PushLuaVector(state,value.x,value.y);break;}
 case Kind::Color:PushLuaColorFromEngineColorMod(state,Read<EngineColorMod>(state,object,row.offset));break;
 case Kind::Target:case Kind::Child:case Kind::Parent:{const auto p=Read<std::uintptr_t>(state,object,row.offset);if(!p)lua_pushnil(state);else PushEntityCallbackArgument(state,p);break;}
 case Kind::EntityReference:{const auto p=Read<std::uintptr_t>(state,object,row.offset);if(p&&IsLiveEntityPointer(p))PushEntityCallbackArgument(state,p);else lua_pushnil(state);break;}
 case Kind::None:return 0;
 }
 return 1;
}
bool Store(lua_State*state,std::uintptr_t object,const Row&row){
 Check(state,row.group);
 switch(row.kind){
 case Kind::Int:Write(state,object,row.offset,Integer(state));break;
 case Kind::UInt:Write(state,object,row.offset,static_cast<std::uint32_t>(Integer(state)));break;
 case Kind::Float:Write(state,object,row.offset,static_cast<float>(luaL_checknumber(state,3)));break;
 case Kind::Bool:Write(state,object,row.offset,static_cast<std::uint8_t>(lua_toboolean(state,3)!=0));break;
 case Kind::Vector:Write(state,object,row.offset,*RequireVectorArgument(state,3));break;
 case Kind::Color:{EngineColorMod value{};if(!FillEngineColorMod(state,3,&value))luaL_argerror(state,3,"Color expected");Write(state,object,row.offset,value);break;}
 case Kind::Target:case Kind::Child:case Kind::Parent:{std::uintptr_t target{};if(!lua_isnil(state,3)){target=EntityPointerArgument(state,3);if(!target)luaL_argerror(state,3,"live Entity or nil expected");}
  const bool parent=row.kind==Kind::Parent;
  if(parent)Check(state,Group::SetParent);
  using Fn=void(*)(void*,void*);Fn fn=nullptr;
#if !defined(__SWITCH__)
  fn=parent?g_Tests.setParent:(row.kind==Kind::Target?g_Tests.setTarget:g_Tests.setChild);
#endif
  if(!fn){const auto group=parent?Group::SetParent:(row.kind==Kind::Target?Group::SetTarget:Group::SetChild);if(!parent)Check(state,group);fn=engine_call::AsFunction<Fn>(LuaRuntime::EngineModuleBase()+(parent?guards::kSetParent0Entry:(row.kind==Kind::Target?guards::kSetTarget0Entry:guards::kSetChild0Entry)));}
  fn(engine_memory::AsObject(object),engine_memory::AsObject(target));break;}
 case Kind::Height:{const auto value=static_cast<float>(luaL_checknumber(state,3));using Fn=void(*)(void*,float);Fn fn=nullptr;
#if !defined(__SWITCH__)
 fn=g_Tests.setTearHeight;
#endif
 if(!fn){Check(state,Group::SetHeight);fn=engine_call::AsFunction<Fn>(LuaRuntime::EngineModuleBase()+guards::kSetHeight0Entry);}fn(engine_memory::AsObject(object),value);break;}
 case Kind::EntityReference:{std::uintptr_t target{};if(!lua_isnil(state,3)){target=EntityPointerArgument(state,3);if(!target)luaL_argerror(state,3,"live Entity or nil expected");}
  // Check已核完整16B入口；SetEntityRef负责旧弱引用注销和新目标回链注册，严禁预写+c20。
  using Fn=void(*)(void*,void*);engine_call::AsFunction<Fn>(LuaRuntime::EngineModuleBase()+kSetEntityRefEntry)(engine_memory::AsObject(object),engine_memory::AsObject(target));break;}
 case Kind::None:return false;
 }
 return true;
}
Row ItemRow(const char*name){
 if(!name)return {};
 if(name[0]=='S'&&!std::strcmp(name,"Special"))return {Kind::Bool,0xB4,Group::Item};
 if(name[0]!='A'||name[1]!='d'||name[2]!='d')return {};
 struct Item {const char*name;std::uintptr_t offset;};
 static constexpr Item fields[]={{"AddMaxHearts",0x58},{"AddHearts",0x5C},{"AddSoulHearts",0x60},{"AddBlackHearts",0x64},{"AddBombs",0x68},{"AddKeys",0x6C},{"AddCoins",0x70}};
 for(const auto&f:fields){if(!std::strcmp(name,f.name))return {Kind::Int,f.offset,Group::Item};}
 return {};
}
Row SpriteRow(const char*name){if(!name)return {};
 // ANM2::Reset @66E4 initializes this vector; GetDestQuad @9804 consumes it.
 // Both instructions are covered by the existing Sprite layout guards.
 if(name[0]=='O'&&!std::strcmp(name,"Offset"))return {Kind::Vector,0xD4,Group::Sprite};
 if(name[0]=='R'&&!std::strcmp(name,"Rotation"))return {Kind::Float,0xE4,Group::Sprite};
 return {};
}
std::uintptr_t Sprite(lua_State*state){const auto p=ResolveSpriteArgument(state,1);if(!p)luaL_error(state,"Sprite reference is no longer available");return engine_memory::AddressOf(p);}
std::uintptr_t Item(lua_State*state,std::uintptr_t item){const auto live=ItemConfigPointerArgument(state,1);if(!item||live!=item)luaL_error(state,"ItemConfigItem reference is no longer available");return live;}
}
#if !defined(__SWITCH__)
void SetExtendedFieldsNativeTestBindings(ExtendedFieldsNativeTestBindings value) noexcept {g_Tests=value;}
#endif
int TryPushExtendedEntityField(lua_State*state,std::uintptr_t entity,const char*name){const auto field=Name(name);if(field==Field::None)return 0;const auto row=Layout(entity,field);if(row.kind==Kind::None)return 0;
 // Touched保留原PickupRead及设备探针；此处只补同一已确认布局guard，写侧走下方共用Bool流程。
 if(field==Field::Touched){Check(state,row.group);return 0;}return Push(state,entity,row);}
bool TryWriteExtendedEntityField(lua_State*state,std::uintptr_t entity,const char*name){const auto field=Name(name);if(field==Field::None)return false;const auto row=Layout(entity,field);return row.kind!=Kind::None&&Store(state,entity,row);}
int TryPushExtendedItemConfigField(lua_State*state,std::uintptr_t item,const char*name){const auto row=ItemRow(name);return row.kind==Kind::None?0:Push(state,Item(state,item),row);}
bool TryWriteExtendedItemConfigField(lua_State*state,std::uintptr_t item,const char*name){const auto row=ItemRow(name);return row.kind!=Kind::None&&Store(state,Item(state,item),row);}
int TryPushExtendedSpriteField(lua_State*state,const char*name){const auto row=SpriteRow(name);return row.kind==Kind::None?0:Push(state,Sprite(state),row);}
bool TryWriteExtendedSpriteField(lua_State*state,const char*name){const auto row=SpriteRow(name);return row.kind!=Kind::None&&Store(state,Sprite(state),row);}
int TryPushExtendedRoomDescriptorField(lua_State*state,std::uintptr_t descriptor,const char*name){
 if(!name||name[0]!='S'||std::strcmp(name,"ShopItemDiscountIdx"))return 0;
 Check(state,Group::Descriptor);if(!descriptor)luaL_error(state,"RoomDescriptor reference is no longer available");
 lua_pushinteger(state,Read<std::int16_t>(state,descriptor,0xF2));return 1;
}
bool TryWriteExtendedRoomDescriptorField(lua_State*state,std::uintptr_t descriptor,const char*name){
 if(!name||name[0]!='S'||std::strcmp(name,"ShopItemDiscountIdx"))return false;
 Check(state,Group::Descriptor);if(!descriptor)luaL_error(state,"RoomDescriptor reference is no longer available");
 const auto low=static_cast<std::uint16_t>(Integer(state));std::int16_t value{};std::memcpy(&value,&low,2);Write(state,descriptor,0xF2,value);return true;
}
}
