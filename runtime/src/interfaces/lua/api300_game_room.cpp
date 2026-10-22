#include "interfaces/lua/api300_game_room.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
#include <cmath>
#include "interfaces/lua/vector_api.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
enum class Operation:unsigned char{SetI32,I32,Inc,Zero,Count8,I32Number,F32,MaxPair,Positive};
struct Row {std::uintptr_t offset;Operation operation;};
constexpr Row kRows[]={
{0x26fa5c,Operation::SetI32},
{0x26fa60,Operation::Inc},
{0x26fa60,Operation::I32},
{0x26fa68,Operation::Inc},
{0x26fa68,Operation::I32},
{0x26fa6c,Operation::Inc},
{0x26fa6c,Operation::Zero},
{0x26fa6c,Operation::I32},
{0x26fa70,Operation::I32},
{0x26fa74,Operation::I32},
{0x26fa78,Operation::I32},
{0x26fa74,Operation::Zero},
{0x26fa78,Operation::Zero},
{0x2f002c,Operation::SetI32},
{0x2f0038,Operation::Count8},
{0x2f0020,Operation::SetI32},
{0x24f9ac,Operation::I32Number},
{0x24f9bc,Operation::F32},
{0x24f9c0,Operation::F32},
{0x2f0050,Operation::MaxPair},
{0x26fa38,Operation::Positive},
};
template<class T>__attribute__((noinline)) T Read(lua_State*L,std::uintptr_t p,std::uintptr_t o){T value{};if(!engine_memory::ReadField(p,o,&value,engine_memory::EngineMemoryReadable))luaL_error(L,"api300 Game field unavailable");return value;}
template<class T>__attribute__((noinline)) void Write(lua_State*L,std::uintptr_t p,std::uintptr_t o,const T&value){if(!engine_memory::WriteField(p,o,value,engine_memory::EngineMemoryWritable))luaL_error(L,"api300 Game field is not writable");}
std::int32_t Int(lua_State*L,int i){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(L,i));std::int32_t value{};std::memcpy(&value,&bits,4);return value;}
__attribute__((noinline)) int GameField(lua_State*L,unsigned index){
 luaL_checkudata(L,1,LuaRuntime::kGameMetatable);const auto p=ResolveEngineReceiver(L,FieldReceipt::Level,1);if(!p)return luaL_error(L,"Game reference is no longer available");const auto&r=kRows[index];
 switch(r.operation){
  case Operation::SetI32:{const auto value=Int(L,2);Write(L,p,r.offset,value);return 0;}
  case Operation::I32:lua_pushinteger(L,Read<std::int32_t>(L,p,r.offset));return 1;
  case Operation::Inc:{const auto old=Read<std::uint32_t>(L,p,r.offset);const auto value=old+std::uint32_t{1};Write(L,p,r.offset,value);return 0;}
  case Operation::Zero:Write(L,p,r.offset,std::uint32_t{0});return 0;
  case Operation::F32:lua_pushnumber(L,Read<float>(L,p,r.offset));return 1;
  case Operation::I32Number:lua_pushnumber(L,Read<std::int32_t>(L,p,r.offset));return 1;
  case Operation::Positive:lua_pushboolean(L,Read<std::int32_t>(L,p,r.offset)>0);return 1;
  case Operation::Count8:{struct Bounds{std::uintptr_t begin,end;};const auto bounds=Read<Bounds>(L,p,r.offset);if(bounds.end<bounds.begin||(bounds.end-bounds.begin)%8)return luaL_error(L,"encountered boss vector unavailable");const auto count=static_cast<std::uint32_t>((bounds.end-bounds.begin)/8);std::int32_t value{};std::memcpy(&value,&count,4);lua_pushinteger(L,value);return 1;}
  case Operation::MaxPair:{const auto input=Int(L,2);const auto old=Read<std::int32_t>(L,p,r.offset);const auto result=old>=input?old:input;struct Pair{std::int32_t remaining,total;};const Pair pair{result,result};Write(L,p,r.offset,pair);return 0;}
 }
 return luaL_error(L,"invalid api300 field operation");
}
}
int Api300GameSetLastDevilRoomStage(lua_State*L){return GameField(L,0);}
int Api300GameAddTreasureRoomsVisited(lua_State*L){return GameField(L,1);}
int Api300GameGetTreasureRoomVisitCount(lua_State*L){return GameField(L,2);}
int Api300GameAddStageWithoutHeartsPicked(lua_State*L){return GameField(L,3);}
int Api300GameGetStagesWithoutHeartsPicked(lua_State*L){return GameField(L,4);}
int Api300GameAddStageWithoutDamage(lua_State*L){return GameField(L,5);}
int Api300GameClearStagesWithoutDamage(lua_State*L){return GameField(L,6);}
int Api300GameGetStagesWithoutDamage(lua_State*L){return GameField(L,7);}
int Api300GameGetDevilRoomDeals(lua_State*L){return GameField(L,8);}
int Api300GameGetDonationModGreed(lua_State*L){return GameField(L,9);}
int Api300GameGetDonationModAngel(lua_State*L){return GameField(L,10);}
int Api300GameClearDonationModGreed(lua_State*L){return GameField(L,11);}
int Api300GameClearDonationModAngel(lua_State*L){return GameField(L,12);}
int Api300GameSetLastLevelWithDamage(lua_State*L){return GameField(L,13);}
int Api300GameGetNumEncounteredBosses(lua_State*L){return GameField(L,14);}
int Api300GameSetLastLevelWithoutHalfHp(lua_State*L){return GameField(L,15);}
int Api300GameGetScreenShakeCountdown(lua_State*L){return GameField(L,16);}
int Api300GameGetDarknessModifier(lua_State*L){return GameField(L,17);}
int Api300GameGetTargetDarkness(lua_State*L){return GameField(L,18);}
int Api300GameAddPixelation(lua_State*L){return GameField(L,19);}
int Api300GameHasHallucination(lua_State*L){return GameField(L,20);}
namespace {
enum class RoomOperation:unsigned char{Bool,Ten,I32,True,Vector,Set8,Set4,Get4,GridPath};
struct RoomRow{std::uintptr_t offset;RoomOperation operation;};
constexpr RoomRow kRoomRows[]={
{0x0,RoomOperation::Bool},
{0x1918,RoomOperation::Ten},
{0x1fc4,RoomOperation::I32},
{0x1940,RoomOperation::Bool},
{0x1940,RoomOperation::True},
{0x78ed,RoomOperation::Bool},
{0x7c78,RoomOperation::Vector},
{0x7c74,RoomOperation::True},
{0x1920,RoomOperation::True},
{0x8,RoomOperation::Set8},
{0x8,RoomOperation::Set4},
{0x8,RoomOperation::Get4},
{0xe98,RoomOperation::GridPath},
};
__attribute__((noinline)) int RoomField(lua_State*L,unsigned index){
 luaL_checkudata(L,1,LuaRuntime::kRoomMetatable);const auto room=ResolveEngineReceiver(L,FieldReceipt::Room,1);if(!room)return luaL_error(L,"Room reference is no longer available");const auto&r=kRoomRows[index];
 switch(r.operation){
  case RoomOperation::Bool:lua_pushboolean(L,Read<std::uint8_t>(L,room,r.offset)!=0);return 1;
  case RoomOperation::Ten:Write(L,room,r.offset,std::int32_t{10});return 0;
  case RoomOperation::I32:lua_pushinteger(L,Read<std::int32_t>(L,room,r.offset));return 1;
  case RoomOperation::True:Write(L,room,r.offset,std::uint8_t{1});return 0;
  case RoomOperation::Vector:{const auto v=Read<LuaRuntime::VectorHandle>(L,room,r.offset);PushLuaVector(L,v.x,v.y);return 1;}
  case RoomOperation::Set8:case RoomOperation::Set4:case RoomOperation::Get4:{const auto desc=Read<std::uintptr_t>(L,room,r.offset);if(!desc)return luaL_error(L,"Room descriptor unavailable");auto flags=Read<std::uint32_t>(L,desc,kRoomDescriptorFlagsOffset);const std::uint32_t mask=r.operation==RoomOperation::Set8?8U:4U;if(r.operation==RoomOperation::Get4){lua_pushboolean(L,(flags&mask)!=0);return 1;}const auto enabled=lua_toboolean(L,2)!=0;flags=enabled?(flags|mask):(flags&~mask);Write(L,desc,kRoomDescriptorFlagsOffset,flags);return 0;}
  case RoomOperation::GridPath:{const auto&position=*RequireVectorArgument(L,2);const float cx=(position.x-40.0F)/40.0F+0.5F;const float cy=(position.y-120.0F)/40.0F+0.5F;const auto width=Read<std::int32_t>(L,room,kRoomGridWidthOffset);const auto height=Read<std::int32_t>(L,room,kRoomGridHeightOffset);
   // PC cvttss2si produces INT_MIN for NaN/out-of-range, and the negative test returns0.
   if(!std::isfinite(cx)||!std::isfinite(cy)||cx<=-2147483648.0F||cx>=2147483648.0F||cy<=-2147483648.0F||cy>=2147483648.0F){lua_pushinteger(L,0);return 1;}
   const auto x=static_cast<std::int32_t>(cx),y=static_cast<std::int32_t>(cy);if(x<0||y<0||x>=width||y>=height){lua_pushinteger(L,0);return 1;}const auto grid=static_cast<std::int64_t>(width)*y+x;if(grid<0||grid>static_cast<std::int64_t>(INT32_MAX))return luaL_error(L,"Room grid path index unavailable");lua_pushinteger(L,Read<std::int32_t>(L,room,r.offset+static_cast<std::uintptr_t>(grid)*4));return 1;}
 }
 return luaL_error(L,"invalid api300 Room field operation");
}
}
int Api300RoomIsInitialized(lua_State*L){return RoomField(L,0);}
int Api300RoomKeepDoorsClosed(lua_State*L){return RoomField(L,1);}
int Api300RoomGetSecondBossID(lua_State*L){return RoomField(L,2);}
int Api300RoomGetRedHeartDamage(lua_State*L){return RoomField(L,3);}
int Api300RoomSetRedHeartDamage(lua_State*L){return RoomField(L,4);}
int Api300RoomHasTriggerPressurePlates(lua_State*L){return RoomField(L,5);}
int Api300RoomGetWaterCurrent(lua_State*L){return RoomField(L,6);}
int Api300RoomStopRain(lua_State*L){return RoomField(L,7);}
int Api300RoomSetCardAgainstHumanity(lua_State*L){return RoomField(L,8);}
int Api300RoomSetAmbushDone(lua_State*L){return RoomField(L,9);}
int Api300RoomSetSacrificeDone(lua_State*L){return RoomField(L,10);}
int Api300RoomIsSacrificeDone(lua_State*L){return RoomField(L,11);}
int Api300RoomGetGridPathFromPos(lua_State*L){return RoomField(L,12);}

}
