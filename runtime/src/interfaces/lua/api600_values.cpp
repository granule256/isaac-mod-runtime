#include "interfaces/lua/api600_values.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api400_params.hpp"
#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <array>
#include <cmath>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
struct Layout{std::uintptr_t offset;std::array<std::uint8_t,16> bytes;};
constexpr Layout kLayouts[]={
{0xac30,{0x8,0x34,0x40,0xf9,0x28,0x1,0x0,0xb4,0x9,0x10,0x42,0x39,0xe9,0x0,0x0,0x34}},
{0x9bf0,{0x8,0x40,0x42,0x39,0xf3,0x3,0x3,0xaa,0xf4,0x3,0x2,0xaa,0xf5,0x3,0x1,0xaa}},
};
api100_native::Cache g_Layouts[2]{};
std::uintptr_t Sprite(lua_State*L,unsigned g){const auto p=engine_memory::AddressOf(ResolveSpriteArgument(L,1));if(!p)luaL_error(L,"Sprite reference is no longer available");const auto&v=kLayouts[g];static_cast<void>(api100_native::Resolve(L,{v.offset,v.bytes.data()},g_Layouts[g]));return p;}
}
int Api600SpriteGetOverlayAnimation(lua_State*L){const auto p=Sprite(L,0);std::uintptr_t name{};if(!engine_memory::ReadField(p,0x68,&name,engine_memory::EngineMemoryReadable))return luaL_error(L,"Sprite overlay state is not readable");if(!name){lua_pushliteral(L,"");return 1;}return Api500PushConfigString(L,name);}
int Api600SpriteSetOverlayRenderPriority(lua_State*L){const auto p=Sprite(L,1);const auto value=static_cast<std::uint8_t>(lua_toboolean(L,2)!=0);if(!engine_memory::WriteField(p,0x90,value,engine_memory::EngineMemoryWritable))return luaL_error(L,"Sprite overlay priority is not writable");return 0;}
int Api600RandomVector(lua_State*L){
 // PC659290: one shared RNG u32, cast to f32, multiply 2^-32 and the f32 pi,
 // then double that f32 angle. The PC math wrappers widen to double and narrow.
 const auto random=Api400NextRandomU32(L);float angle=static_cast<float>(random)*0x1p-32F;
 angle*=3.1415927410125732421875F;angle+=angle;
 PushLuaVector(L,static_cast<float>(std::cos(static_cast<double>(angle))),static_cast<float>(std::sin(static_cast<double>(angle))));return 1;
}
}
