#include "interfaces/lua/repentogon_item_overlay_api.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_sprite_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "program/xml_data_store.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr std::uintptr_t kOverlay = 0x25db0;
constexpr std::uintptr_t kSprite = 8;
constexpr std::uintptr_t kDelay = 0x1478;
constexpr std::uintptr_t kPlayer = 0x1480;
constexpr std::uintptr_t kMegaMush = 0x1488;
constexpr std::uint8_t kShowGuard[] = {
    0x3f,0xb8,0x00,0x71,0x88,0x0a,0x00,0x54,
    0xff,0x03,0x02,0xd1,0xfd,0x7b,0x02,0xa9};
api100_native::Cache g_ShowCache{};
#if !defined(__SWITCH__)
std::uintptr_t g_ShowTest{};
#endif
std::uintptr_t Overlay(lua_State* L) {
    if (!LuaRuntime::IsOnGameThread()) luaL_error(L,"ItemOverlay requires the game thread");
    std::uintptr_t slot{}, game{};
    if (!engine_memory::ReadAt(LuaRuntime::GameOwnerSlot(),&slot,engine_memory::EngineMemoryReadable) ||
        !slot || !engine_memory::ReadAt(slot,&game,engine_memory::EngineMemoryReadable) || !game ||
        game>UINTPTR_MAX-kOverlay-kMegaMush-kSpriteObjectSize ||
        !engine_memory::EngineMemoryReadable(game+kOverlay,kMegaMush+kSpriteObjectSize))
        luaL_error(L,"ItemOverlay game is unavailable");
    return game+kOverlay;
}
template<class T> T Read(lua_State* L,std::uintptr_t object,std::uintptr_t offset) {
    T value{};
    if (!engine_memory::ReadField(object,offset,&value,engine_memory::EngineMemoryReadable))
        luaL_error(L,"ItemOverlay state is unavailable");
    return value;
}
void PushSprite(lua_State* L,std::uintptr_t object) {
    if (!repentogon::HasSpriteValidator() || !repentogon::CallbackSpriteAlive(object))
        luaL_error(L,"ItemOverlay sprite lifetime is unavailable");
    PushCallbackSpriteHandle(L,object,LUA_NOREF);
    if (lua_isnil(L,-1)) luaL_error(L,"ItemOverlay sprite is unavailable");
}
void BeginMethod(lua_State* L,int sprite,const char* name) {
    lua_getfield(L,sprite,name);
    lua_pushvalue(L,sprite);
}
void Call0(lua_State* L,int sprite,const char* name) {
    BeginMethod(L,sprite,name);lua_call(L,1,0);
}
void PushPath(lua_State* L,const xml_data::XmlRecord& record,const xml_data::XmlAttribute& leaf) {
    const auto* root=record.FindAttribute("anm2root");
    lua_pushstring(L,root?root->value.c_str():"");
    lua_pushlstring(L,leaf.value.data(),leaf.value.size());lua_concat(L,2);
}
void CustomBook(lua_State* L,int sprite,const xml_data::XmlRecord& record) {
    if (const auto* anm=record.FindAttribute("anm2")) {
        BeginMethod(L,sprite,"Load");PushPath(L,record,*anm);lua_pushboolean(L,true);lua_call(L,3,0);
        Call0(L,sprite,"LoadGraphics");Call0(L,sprite,"Update");
    }
    if (const auto* gfx=record.FindAttribute("gfx")) {
        BeginMethod(L,sprite,"ReplaceSpritesheet");lua_pushinteger(L,0);PushPath(L,record,*gfx);lua_call(L,3,0);
        Call0(L,sprite,"LoadGraphics");Call0(L,sprite,"Update");
    }
    if (const auto* layers=record.FindChildren("layer")) {
        ApplyRepentogonXmlLayerTints(L,sprite,*layers);
        Call0(L,sprite,"LoadGraphics");Call0(L,sprite,"Update");
    }
    const auto* anim=record.FindAttribute("anim");
    BeginMethod(L,sprite,"Play");lua_pushstring(L,anim?anim->value.c_str():"Appear");
    lua_pushboolean(L,!anim);lua_call(L,3,0);
}
}

int RepentogonItemOverlayGetSprite(lua_State* L) {PushSprite(L,Overlay(L)+kSprite);return 1;}
int RepentogonItemOverlayGetMegaMushPlayerSprite(lua_State* L) {PushSprite(L,Overlay(L)+kMegaMush);return 1;}
int RepentogonItemOverlayGetOverlayID(lua_State* L) {lua_pushinteger(L,Read<std::int32_t>(L,Overlay(L),4));return 1;}
int RepentogonItemOverlayGetDelay(lua_State* L) {lua_pushinteger(L,Read<std::int32_t>(L,Overlay(L),kDelay));return 1;}
int RepentogonItemOverlayGetPlayer(lua_State* L) {
    const auto player=Read<std::uintptr_t>(L,Overlay(L),kPlayer);
    if (!player) {lua_pushnil(L);return 1;}
    if (!IsLiveEntityPointer(player)) return luaL_error(L,"ItemOverlay player is no longer available");
    PushEntityCallbackArgument(L,player);return 1;
}
int RepentogonItemOverlayShow(lua_State* L) {
    const auto overlay=Overlay(L);
    const int id=static_cast<int>(luaL_checkinteger(L,1));
    const int delay=static_cast<int>(luaL_optinteger(L,2,0));
    std::uintptr_t player{};
    // Preserve the pinned upstream wrapper's four-argument player-selection rule.
    if (lua_gettop(L)==4 && !lua_isnil(L,3)) {
        player=ResolveEngineReceiver(L,FieldReceipt::EntityPlayer,3);
        if (!player) return luaL_argerror(L,3,"EntityPlayer is no longer available");
    }
    const auto* record=id>46?xml_data::FindEntryById(xml_data::XmlNodeType::GiantBook,id):nullptr;
    luaL_checkstack(L,12,"ItemOverlay custom book");
    const auto entry=api100_native::Resolve(L,{0x3c5034,kShowGuard},g_ShowCache
#if !defined(__SWITCH__)
        ,g_ShowTest
#endif
    );
    const auto show=engine_call::AsFunction<void(*)(void*,int,int,void*)>(entry);
    show(engine_memory::AsObject(overlay),record?1:id,delay,engine_memory::AsObject(player));
    if (record) {
        if (!engine_memory::WriteField(overlay,4,id,engine_memory::EngineMemoryWritable))
            return luaL_error(L,"ItemOverlay ID is not writable");
        PushSprite(L,overlay+kSprite);
        CustomBook(L,lua_gettop(L),*record);
    }
    return 0;
}
int RegisterRepentogonItemOverlayApi(lua_State* L) {
    lua_newtable(L);static_cast<void>(AttachOwnerMethods(L,"ItemOverlay",nullptr,0));lua_setglobal(L,"ItemOverlay");return 0;
}
#if !defined(__SWITCH__)
void SetRepentogonItemOverlayNativeTestBinding(std::uintptr_t value) noexcept {g_ShowTest=value;g_ShowCache={};}
#endif
}
