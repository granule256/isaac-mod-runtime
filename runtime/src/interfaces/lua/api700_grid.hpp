#pragma once
#include <cstdint>
struct lua_State;
namespace LuaRuntime {struct SpriteHandle;}
namespace isaac::runtime {
int TryPushApi700GridField(lua_State*,const char*);
bool TryWriteApi700GridField(lua_State*,const char*);
// 仅在游戏线程的受保护 Lua 桥内调用；可能抛 Lua 错误，调用方负责 pcall/恢复栈。
// root=nullptr 清全部；仅存活且仍指向所 pin Lua 串的对象恢复首次赋值前指针。
void RestorePressurePlateAnimationPins(lua_State*, const char* root);
// 原生析构 this 已由钩子确认，无需依赖当前 Room 槽位仍挂着该对象。
void ForgetPressurePlateAnimationPinBeforeDestroy(lua_State*, std::uintptr_t grid);
// 原生 writer 完成后调用，只释放已被原生覆盖的 pin，不写原生新值。
void RefreshPressurePlateAnimationPinAfterNativeWrite(lua_State*, std::uintptr_t grid);
bool HasPressurePlateAnimationPins() noexcept;
int Api700GridPoopReduceSpawnRate(lua_State*);
void* ResolveApi700GridSprite(const LuaRuntime::SpriteHandle*)noexcept;
#if !defined(__SWITCH__)
void SetApi700GridSpriteNatives(const std::uintptr_t(&)[3])noexcept;
#endif
}
