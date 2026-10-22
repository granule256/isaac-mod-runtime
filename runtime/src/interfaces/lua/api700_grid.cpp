#include "interfaces/lua/api700_grid.hpp"
#include "interfaces/lua/api700_grid.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"
#include <cstring>
#if defined(__SWITCH__)
#include "pressure_plate_animation_hook.hpp"
#include "infrastructure/relay/entry_relay_hook_adapter.hpp"
#endif
#include <new>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
struct Owner{std::uintptr_t module,room,descriptor,grid;std::uint32_t slot;bool door;};
// 只有新借用类型分配尾部元数据；已有SpriteHandle没有扩容。
struct ExtraSprite{LuaRuntime::SpriteHandle base;Owner owner;unsigned offset;};
static_assert(offsetof(ExtraSprite,base)==0);
api100_native::Cache g_Cache[7]{};
#if !defined(__SWITCH__)
std::uintptr_t g_Natives[3]{};
#endif
template<class T>bool Read(std::uintptr_t p,std::uintptr_t offset,T*out){return engine_memory::ReadField(p,offset,out,engine_memory::EngineMemoryReadable);}
std::uintptr_t CurrentRoom(){void*room{};return ReadCurrentGameRoom(LuaRuntime::GameOwnerSlot(),&room)==GameRoomObservation::Success?engine_memory::AddressOf(room):0;}
bool Live(const Owner&o){if(!o.module||o.module!=LuaRuntime::EngineModuleBase()||CurrentRoom()!=o.room||!IsLiveGridEntityPointer(o.grid))return false;std::uintptr_t descriptor{},vptr{},member{};if(!Read(o.room,8,&descriptor)||descriptor!=o.descriptor||!Read(o.grid,0,&vptr))return false;
 if(o.door){std::int32_t slot{};if(vptr!=o.module+kGridEntity_DoorVtableOffset||o.slot>=8||!Read(o.grid,kGridEntityDoorSlotOffset,&slot)||slot!=static_cast<std::int32_t>(o.slot))return false;return Read(o.room,kRoomDoorObjectTableOffset+o.slot*8,&member)&&member==o.grid;}
 std::uint32_t index{},width{},height{};if(!Read(o.grid,kGridEntityGridIndexOffset,&index)||index!=o.slot||!Read(o.room,kRoomGridWidthOffset,&width)||!Read(o.room,kRoomGridHeightOffset,&height)||!width||!height||o.slot>=static_cast<std::uint64_t>(width)*height)return false;
 return Read(o.room,kRoomGridEntityTableOffset+static_cast<std::uintptr_t>(o.slot)*8,&member)&&member==o.grid;
}
Owner Grid(lua_State*L,std::uintptr_t expected,bool door){const auto p=ResolveEngineReceiver(L,FieldReceipt::GridEntity);if(!p){luaL_error(L,"GridEntity reference is unavailable");}std::uintptr_t vptr{};if(!Read(p,0,&vptr)||vptr!=LuaRuntime::EngineModuleBase()+expected){luaL_error(L,"GridEntity subclass does not match field");}
 Owner o{};o.module=LuaRuntime::EngineModuleBase();o.room=CurrentRoom();o.grid=p;o.door=door;if(!o.room||!Read(o.room,8,&o.descriptor)||!Read(p,door?kGridEntityDoorSlotOffset:kGridEntityGridIndexOffset,&o.slot)||!Live(o)){luaL_error(L,"GridEntity Room or slot reference is unavailable");}return o;
}
void Guard(lua_State*L,unsigned index){static_cast<void>(api100_native::Resolve(L,api700_grid::kEntries[index],g_Cache[index]));}
std::uintptr_t Native(lua_State*L,unsigned index){std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Natives[index];
#endif
 return api100_native::Resolve(L,api700_grid::kEntries[index+3],g_Cache[index+3],host);}
// 只在实际赋值时分配记录；原生 writer/析构/卸载事件清理，不做逐帧扫描。
constexpr std::uintptr_t kNextGreedAnimationOffset = 0x2f8;
char g_AnimationPinsKey;
std::uint32_t g_AnimationPinCount{};
constexpr char kAnimationPinMetatable[] = "Isaac.PressurePlateAnimationPin";
struct AnimationPin {
    Owner owner;
    std::uintptr_t originalNative;
    std::uintptr_t pinned;
    bool active;
};
void ReleasePin(AnimationPin* pin) noexcept {
    if (pin && pin->active) { pin->active = false; --g_AnimationPinCount; }
}
void RetirePin(lua_State* L, int index) {
    auto* pin = static_cast<AnimationPin*>(lua_touserdata(L, index));
    if (!pin) return;
    ReleasePin(pin);
    // 主动解除字符串引用，不让无效 record 的 __gc 多留住一轮大字符串。
    index = lua_absindex(L, index);
    lua_pushnil(L);
    lua_setuservalue(L, index);
}
int CollectAnimationPin(lua_State* L) {
    ReleasePin(static_cast<AnimationPin*>(lua_touserdata(L, 1)));
    return 0;
}
// 返回表的栈索引；userdata 的 __gc 让 lua_close 后快路径计数也归零。
int AnimationPins(lua_State* L, bool create) {
    lua_rawgetp(L, LUA_REGISTRYINDEX, &g_AnimationPinsKey);
    if (lua_isnil(L, -1) && create) {
        lua_pop(L, 1);
        lua_newtable(L);
        lua_pushvalue(L, -1);
        lua_rawsetp(L, LUA_REGISTRYINDEX, &g_AnimationPinsKey);
    }
    return lua_gettop(L);
}
bool PinOwnerLive(const AnimationPin& pin) {
    std::uintptr_t vptr{};
    return Live(pin.owner) && Read(pin.owner.grid, 0, &vptr) &&
           vptr == pin.owner.module + kGridEntity_PressurePlateVtableOffset;
}
void PushCallingModRoot(lua_State* L) {
    constexpr char prefix[] = "@rom:/isaac_mods/mods/";
    lua_Debug frame{};
    for (int depth = 1; lua_getstack(L, depth, &frame); ++depth) {
        if (!lua_getinfo(L, "S", &frame) || !frame.source ||
            std::strncmp(frame.source, prefix, sizeof(prefix)-1)) continue;
        const char* directory = frame.source + sizeof(prefix)-1;
        const char* slash = std::strchr(directory, '/');
        if (slash && slash != directory) {
            lua_pushlstring(L, frame.source + 1, static_cast<std::size_t>(slash - frame.source - 1));
            return;
        }
    }
    lua_pushnil(L); // 控制台不是最后加载的模组。
}
bool RootMatches(lua_State* L, int record, const char* root) {
    if (!root) return true;
    if (*root == '@') ++root;
    std::size_t length = std::strlen(root);
    while (length && root[length-1] == '/') --length;
    lua_getuservalue(L, record);
    lua_rawgeti(L, -1, 2);
    std::size_t savedLength{};
    const char* saved = lua_tolstring(L, -1, &savedLength);
    const bool matches = saved && length == savedLength && !std::memcmp(saved, root, length);
    lua_pop(L, 2);
    return matches;
}
void RestorePinnedNative(lua_State* L, AnimationPin* pin, bool beforeDestroy) {
    if (!pin || !pin->active || (!beforeDestroy && !PinOwnerLive(*pin))) return;
    std::uintptr_t current{};
    if (!Read(pin->owner.grid, kNextGreedAnimationOffset, &current))
        luaL_error(L, "GridEntityPressurePlate.NextGreedAnimation pointer is unreadable");
    if (current == pin->pinned && !engine_memory::WriteField(pin->owner.grid,
            kNextGreedAnimationOffset, pin->originalNative, engine_memory::EngineMemoryWritable))
        luaL_error(L, "GridEntityPressurePlate.NextGreedAnimation pointer is not writable");
}
int PushNextGreedAnimation(lua_State* L, const Owner& owner) {
    std::uintptr_t pointer{};
    if (!Read(owner.grid, kNextGreedAnimationOffset, &pointer))
        return luaL_error(L, "GridEntityPressurePlate.NextGreedAnimation pointer is unreadable");
    if (!pointer) { lua_pushnil(L); return 1; }
    // 与 PC lua_pushstring 一样以 NUL 结束；增量缓冲不设任意长度上限。
    // 每字节使用既有回绕/可读性检查，只在字段被读取时工作。
    luaL_Buffer buffer;
    luaL_buffinit(L, &buffer);
    std::size_t offset{};
    char chunk[128];
    for (;;) {
        std::size_t used{};
        while (used != sizeof(chunk)) {
            char character{};
            if (!Read(pointer, offset, &character))
                return luaL_error(L, "GridEntityPressurePlate.NextGreedAnimation string is unreadable");
            if (!character) {
                luaL_addlstring(&buffer, chunk, used);
                luaL_pushresult(&buffer);
                return 1;
            }
            chunk[used++] = character;
            if (offset == SIZE_MAX) return luaL_error(L, "NextGreedAnimation string exceeds address space");
            ++offset;
        }
        luaL_addlstring(&buffer, chunk, used);
    }
}
void WriteNextGreedAnimation(lua_State* L, const Owner& owner) {
#if defined(__SWITCH__)
    if(!PressurePlateDestructorHooksReady() || !EntryRelayInstalled(HookId::PressurePlateAnimationWriter))
        luaL_error(L,"NextGreedAnimation lifetime hooks are unavailable");
#endif
    std::uintptr_t current{};
    if (!Read(owner.grid, kNextGreedAnimationOffset, &current))
        luaL_error(L, "GridEntityPressurePlate.NextGreedAnimation pointer is unreadable");
    const int table = AnimationPins(L, true);
    lua_rawgetp(L, table, engine_memory::AsObject(owner.grid));
    const int oldIndex = lua_gettop(L);
    auto* old = static_cast<AnimationPin*>(lua_touserdata(L, oldIndex));
    if (lua_isnil(L, 3)) {
        const std::uintptr_t zero{};
        if (!engine_memory::WriteField(owner.grid, kNextGreedAnimationOffset, zero,
                                       engine_memory::EngineMemoryWritable))
            luaL_error(L, "GridEntityPressurePlate.NextGreedAnimation pointer is not writable");
        lua_pushnil(L);
        lua_rawsetp(L, table, engine_memory::AsObject(owner.grid));
        RetirePin(L, oldIndex);
        return;
    }
    // luaL_checklstring 与 PC 一致接受数字转换。先建立强引用，再发布原生指针。
    std::size_t length{};
    const char* text = luaL_checklstring(L, 3, &length);
    static_cast<void>(length);
    // 即使上次 OOM 中断了元表初始化，重试也必须补齐 __gc。
    static_cast<void>(luaL_newmetatable(L, kAnimationPinMetatable));
    lua_pushcfunction(L, CollectAnimationPin);
    lua_setfield(L, -2, "__gc");
    lua_pop(L, 1);
    auto* pin = new(lua_newuserdata(L, sizeof(AnimationPin))) AnimationPin{};
    pin->owner = owner;
    pin->originalNative = old && old->active && PinOwnerLive(*old) && current == old->pinned
                        ? old->originalNative : current;
    pin->pinned = engine_memory::AddressOf(text);
    luaL_getmetatable(L, kAnimationPinMetatable);
    lua_setmetatable(L, -2);
    const int record = lua_gettop(L);
    lua_newtable(L);
    lua_pushvalue(L, 3);
    lua_rawseti(L, -2, 1);
    PushCallingModRoot(L);
    lua_rawseti(L, -2, 2);
    lua_setuservalue(L, record);
    lua_pushvalue(L, record);
    lua_rawsetp(L, table, engine_memory::AsObject(owner.grid));
    if (!engine_memory::WriteField(owner.grid, kNextGreedAnimationOffset, pin->pinned,
                                   engine_memory::EngineMemoryWritable)) {
        lua_pushvalue(L, oldIndex);
        lua_rawsetp(L, table, engine_memory::AsObject(owner.grid));
        luaL_error(L, "GridEntityPressurePlate.NextGreedAnimation pointer is not writable");
    }
    pin->active = true;
    ++g_AnimationPinCount;
    RetirePin(L, oldIndex);
}
unsigned Field(const char*n){if(!n||!n[0])return 0;if(n[0]=='E'&&!std::strcmp(n,"ExtraSprite"))return 1;if(n[0]=='T'&&!std::strcmp(n,"TimerPlate"))return 2;if(n[0]=='N'&&!std::strcmp(n,"NextGreedAnimation"))return 3;return 0;}
Owner FieldOwner(lua_State*L,unsigned field){Guard(L,field==3?6:field-1);return Grid(L,field==1?kGridEntity_DoorVtableOffset:kGridEntity_PressurePlateVtableOffset,field==1);}
int PushSprite(lua_State*L,const Owner&o,unsigned offset){auto*v=new(lua_newuserdata(L,sizeof(ExtraSprite)))ExtraSprite{};v->owner=o;v->offset=offset;v->base.sprite=engine_memory::AsObject(o.grid+offset);v->base.owner=engine_memory::AsObject(o.grid);v->base.source=LuaRuntime::kSpriteSourceEngineGridExtra;v->base.scaleX=v->base.scaleY=1;v->base.colorRed=v->base.colorGreen=v->base.colorBlue=v->base.colorAlpha=1;luaL_getmetatable(L,LuaRuntime::kSpriteMetatable);lua_setmetatable(L,-2);lua_pushvalue(L,1);lua_setuservalue(L,-2);return 1;}
}
#if !defined(__SWITCH__)
void SetApi700GridSpriteNatives(const std::uintptr_t(&v)[3])noexcept{std::memcpy(g_Natives,v,sizeof(g_Natives));}
#endif
bool HasPressurePlateAnimationPins() noexcept { return g_AnimationPinCount != 0; }
void RestorePressurePlateAnimationPins(lua_State* L, const char* root) {
    const int top = lua_gettop(L);
    const int table = AnimationPins(L, false);
    if (!lua_istable(L, table)) { lua_settop(L, top); return; }
    lua_pushnil(L);
    while (lua_next(L, table)) {
        auto* pin = static_cast<AnimationPin*>(lua_touserdata(L, -1));
        if (pin && RootMatches(L, lua_gettop(L), root)) {
            RestorePinnedNative(L, pin, false);
            RetirePin(L, -1);
            lua_pushvalue(L, -2);
            lua_pushnil(L);
            lua_rawset(L, table);
        }
        lua_pop(L, 1);
    }
    lua_settop(L, top);
}
void ForgetPressurePlateAnimationPinBeforeDestroy(lua_State* L, std::uintptr_t grid) {
    const int top = lua_gettop(L);
    const int table = AnimationPins(L, false);
    if (lua_istable(L, table)) {
        lua_rawgetp(L, table, engine_memory::AsObject(grid));
        auto* pin = static_cast<AnimationPin*>(lua_touserdata(L, -1));
        RestorePinnedNative(L, pin, true);
        lua_pushnil(L);
        lua_rawsetp(L, table, engine_memory::AsObject(grid));
        RetirePin(L, -1);
    }
    lua_settop(L, top);
}
void RefreshPressurePlateAnimationPinAfterNativeWrite(lua_State* L, std::uintptr_t grid) {
    const int top = lua_gettop(L);
    const int table = AnimationPins(L, false);
    if (lua_istable(L, table)) {
        lua_rawgetp(L, table, engine_memory::AsObject(grid));
        auto* pin = static_cast<AnimationPin*>(lua_touserdata(L, -1));
        std::uintptr_t current{};
        if (pin && Read(grid, kNextGreedAnimationOffset, &current) && current != pin->pinned) {
            lua_pushnil(L);
            lua_rawsetp(L, table, engine_memory::AsObject(grid));
            RetirePin(L, -1);
        }
    }
    lua_settop(L, top);
}
void* ResolveApi700GridSprite(const LuaRuntime::SpriteHandle*base)noexcept{if(!base||base->source!=LuaRuntime::kSpriteSourceEngineGridExtra)return nullptr;const auto*v=reinterpret_cast<const ExtraSprite*>(base);if(!Live(v->owner))return nullptr;std::uintptr_t vptr{};if(!Read(v->owner.grid,0,&vptr)||vptr!=v->owner.module+(v->owner.door?kGridEntity_DoorVtableOffset:kGridEntity_PressurePlateVtableOffset))return nullptr;return engine_memory::AsObject(v->owner.grid+v->offset);}
int TryPushApi700GridField(lua_State*L,const char*n){const auto field=Field(n);if(!field)return 0;const auto owner=FieldOwner(L,field);if(field==3)return PushNextGreedAnimation(L,owner);return PushSprite(L,owner,field==1?0x1b0:0x1a0);}
bool TryWriteApi700GridField(lua_State*L,const char*n){const auto field=Field(n);if(!field)return false;const auto owner=FieldOwner(L,field);if(field==3){WriteNextGreedAnimation(L,owner);return true;}const auto destination=engine_memory::AsObject(owner.grid+(field==1?0x1b0:0x1a0));const auto source=ResolveSpriteArgument(L,3);
 // 三个入口与全部Lua参数先核完，再建立临时ANM2；之后没有可longjmp的Lua调用。
 const auto copy=engine_call::AsFunction<void(*)(void*,const void*)>(Native(L,0));const auto assign=engine_call::AsFunction<void*(*)(void*,void*)>(Native(L,1));const auto destroy=engine_call::AsFunction<void(*)(void*)>(Native(L,2));alignas(16)unsigned char temporary[kSpriteObjectSize]{};copy(temporary,source);static_cast<void>(assign(destination,temporary));destroy(temporary);return true;
}
int Api700GridPoopReduceSpawnRate(lua_State*L){Guard(L,2);const auto owner=Grid(L,kGridEntity_PoopVtableOffset,false);const std::uint32_t one=1;if(!engine_memory::WriteField(owner.grid,kGridEntityVarDataOffset,one,engine_memory::EngineMemoryWritable)){return luaL_error(L,"GridEntityPoop VarData is not writable");}return 0;}
}
