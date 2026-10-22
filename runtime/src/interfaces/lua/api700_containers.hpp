#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
// 非平凡复制确保AArch64返回对象经x8，而非普通POD的寄存器返回。
struct Api700EntityArray {alignas(8)unsigned char bytes[24]{};Api700EntityArray()=default;Api700EntityArray&operator=(const Api700EntityArray&)=default;Api700EntityArray(const Api700EntityArray&)noexcept;};
void RegisterApi700Containers(lua_State*);
int Api700LaserGetSamples(lua_State*);
int Api700LaserGetNonOptimizedSamples(lua_State*);
int Api700NPCQueryType(lua_State*);
int Api700NPCQuerySpawnerType(lua_State*);
int Api700NPCQueryGroup(lua_State*);
int Api700RoomGetEntities(lua_State*);
int Api700EntityListGet(lua_State*);
int Api700EntityListSize(lua_State*);
int Api700EntityListLen(lua_State*);
int Api700VectorListGet(lua_State*);
int Api700VectorListLen(lua_State*);
#if !defined(__SWITCH__)
void SetApi700ContainerNatives(const std::uintptr_t(&)[3])noexcept;
#endif
}
